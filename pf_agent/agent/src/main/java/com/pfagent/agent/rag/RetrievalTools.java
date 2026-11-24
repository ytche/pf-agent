package com.pfagent.agent.rag;

import com.pfagent.agent.telemetry.QueryGateEventService.Reason;
import org.springframework.ai.document.Document;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * LLM 工具面：三个底层检索方法（设计 §3）
 *
 * 原则：只给底层方法，字段名/字段值由 LLM 自己构造——工具描述即"数据库 schema"。
 * 全部方法返回字符串（喂给 LLM 的紧凑结果），命中时把完整 Document 交给
 * SourceCollector，供 ChatResponse.sources 前端溯源折叠区展示。
 *
 * 错误处理对齐 v1.5 B1：参数不合法（未知模块/未知字段）返回**可读提示**而非抛异常，
 * 让 LLM 在下一轮自纠；无结果返回空列表"[]"，由 LLM 决定转 vectorSearch 或
 * reportDataGap。
 */
@Component
public class RetrievalTools {

    private static final List<String> VALID_MODULES = List.of(
            "spell", "class", "feat", "race", "trait", "equipment", "skill", "rule");

    /** AKN-023：同模块批量取文去重后的单次 ID 上限 */
    private static final int BATCH_ENTRY_MAX_IDS = 10;
    /** AKN-023：批量取文总输出（含分段分隔符与超限提示）的字符上限 */
    private static final int BATCH_ENTRY_RESULT_CHARS = 24000;
    /** AKN-023：批量条目之间的分隔符（也是超限提示前可能追加的 suffix） */
    private static final String BATCH_ENTRY_SEPARATOR = "\n\n---\n\n";
    /** AKN-023：预算时预留的来源编号（含换行标签）字符数 */
    private static final int SOURCE_ID_RESERVE_CHARS = 32;

    @Autowired
    private SearchService searchService;
    @Autowired
    private SourceCollector collector;
    @Autowired
    private DataGapRecorder recorder;
    @Autowired
    private FilterTranslator filterTranslator;
    @Autowired
    private SpellListService spellListService;
    @Autowired
    private ClassTableService classTableService;
    @Autowired
    private RuleTableService ruleTableService;
    @Autowired
    private ListExportService listExportService;
    /** F-008：四模块目录查询门面（spell/feat/race/equipment 统一目录前缀过滤） */
    @Autowired
    private TocListService tocListService;
    /** F-026：工具护栏事件写入（尽力写入，未装配/无上下文/写失败均不影响主流程） */
    @Autowired(required = false)
    private QueryGateEventRecorder queryGateEventRecorder;
    /** AKN-024：当前请求会话上下文（ThreadLocal，由 ChatService.begin 注入，不引入全局状态） */
    @Autowired(required = false)
    private ToolCallTracker toolCallTracker;
    /** AKN-024：会话级宽查询放行指纹（内存、重启失效） */
    @Autowired(required = false)
    private BroadQueryAllowanceRegistry broadQueryAllowanceRegistry;
    @Value("${pf.search.vector-result-chars:1500}")
    private int vectorResultChars;
    @Value("${pf.search.metadata-result-chars:4000}")
    private int metadataResultChars;
    /** J1：getEntryById 完整原文的字符上限保护（防 oversize chunk 爆上下文） */
    @Value("${pf.search.entry-result-chars:8000}")
    private int entryResultChars;
    /** J2：searchByMetadata 增强版默认返回条数（上限另受 enumeration-top-k 约束） */
    @Value("${pf.search.metadata-default-limit:50}")
    private int metadataDefaultLimit;
    /** J3：listDataGaps 默认返回条数（工具层上限 100） */
    @Value("${pf.gaps.list-default-limit:20}")
    private int gapsListDefaultLimit;
    @Autowired
    private EntryResolver entryResolver;
    /** J6：getEntryLinks 每层链接的展示条数上限（防职业被法术反向引用刷屏） */
    @Value("${pf.search.entry-links-max-per-section:20}")
    private int entryLinksMaxPerSection;
    /** B4：listEntries 默认返回条数 */
    @Value("${pf.list-exports.default-limit:50}")
    private int listExportsDefaultLimit;
    /** B4：listEntries 单次硬上限 */
    @Value("${pf.list-exports.max-limit:200}")
    private int listExportsMaxLimit;

    private static final List<String> SORT_FIELDS = List.of("title", "level", "book");
    private static final List<String> SORT_ORDERS = List.of("asc", "desc");

    /**
     * 元数据过滤检索（增强版，SP8a J2）：AND 精确 + OR 组 + 范围比较 + 排序 + 分页 + 跨模块。
     * 过滤条件全部收敛在 query 参数对象中；字段名错误返回可用字段清单让 LLM 自纠；
     * 无结果返回固定回退引导（先放宽再转 vectorSearch，勿直接 reportDataGap）。
     */
    @Tool(description = """
            按元数据精确过滤规则库，返回命中条目的紧凑列表。支持 AND/OR/范围比较/排序/分页/跨模块。
            模块 module: "spell"(法术) / "class"(职业特性) / "feat"(专长) / "race"(种族) /
              "trait"(背景特性) / "equipment"(装备) / "skill"(技能) / "rule"(规则) /
              "all"(全部模块跨库查询)
            模块语义边界:
              - class: 职业特性/职业变体、角色升级、兼职(Multiclassing)、职业成长
              - rule: 战斗动作/状态效果/环境/移动等通用游戏规则
              - spell/feat/race/trait/equipment/skill: 对应具体条目
            过滤条件 query（参数对象，字段均可空，但至少提供一个）:
              - filters: 字段名→字段值，多条件为 AND 精确匹配（如 {school:"咒法系"}）
              - orFilters: 组内 OR，同一字段多个候选值任一命中
                （如 {book:["CRB","APG"]} = 来源 CRB 或 APG）
              - gte / lte: 范围比较下限/上限，值按字符串数字比较
                （如 spell 的 {level:"3"} 表 ≥3 环）
              - sortBy: "title"|"level"|"book"，可空=默认序；sortOrder: "asc"|"desc"，默认 asc
              - limit: 返回条数（默认 50）；offset: 跳过条数（默认 0）
              - allowBroadQuery: 布尔，默认 false。仅当用户已明确确认「仍按原范围查询」时设 true；
                无业务条件或仅 book 条件未放行会返回收窄建议而不执行检索，同一逻辑查询每页都需携带；
                服务端按会话记录 module+book 放行指纹，换模块或换书后需重新向用户确认；
                同一轮内或重新生成时重试不会自动放行，需等用户下一轮明确确认
            宽查询纪律:
              - 用户问「所有/全部/各类」等可能覆盖大量条目的问题时，先以 allowBroadQuery=false
                （缺省）调用本工具登记真实 module+book：query 只带用户提到的书条件，未提书就留空；
                工具会返回收窄建议，再据其向用户说明范围可能很大，给出 2~4 个有效收窄示例
                （不能只是把宽词换个说法）、概览选项和「仍按原范围查询」选项
              - 同一轮内不要改用 allowBroadQuery=true 重试（同轮不能确认自己刚登记的范围），
                必须等用户下一轮明确确认；工具返回的收窄建议不是「查询无结果」或「数据缺失」
              - 具体主题/职业/环级/具体条目/书+主题等小范围问题正常调用，不触发门禁
            法术模块可用字段:
              title / school / subschool / className / level(须配合 className) / book
            职业模块可用字段: className / archetypeName / featureSubtype / componentType / book / title
            种族模块可用字段: book / componentType / title / raceName(中文种族名) / raceNameEn(英文种族名)
              按种族列举特性/替换特性时一次一个种族，必须带 raceName 或 raceNameEn，
              并加 componentType（普通特性 race_trait / 替换特性 alt_trait）；全种族特性先收窄。
              raceNameEn 只精确匹配已知英文原词，缺失/变体需改用中文 raceName 或补查，
              不得把部分命中当作全量。
              例如阿斯托莫伊人种族特性 → {module:"race", query:{filters:{raceName:"阿斯托莫伊人", componentType:"race_trait"}}}
            其余模块可用字段: book / componentType / title
            用法纪律:
              - 过滤条件从宽到窄，一次只加一个条件；orFilters 用于"多本书/多个值任一命中"，
                不要用它代替枚举
              - level 比较（gte/lte/orFilters）必须配合 filters.className 指定职业，
                如 {filters:{className:"女巫"}, gte:{level:"3"}}
              - 无结果时先放宽条件或改用 vectorSearch，确认数据缺失再 reportDataGap
            示例: 女巫3环以上法术 → {module:"spell", query:{filters:{className:"女巫"}, gte:{level:"3"}}}
                  CRB或APG的专长 → {module:"feat", query:{orFilters:{book:["CRB","APG"]}}}
            字段名错误时返回可用字段清单。查询无结果返回空列表与回退建议。
            """)
    public String searchByMetadata(
            @ToolParam(description = "数据模块: spell/class/feat/race/trait/equipment/skill/rule，或 all 跨模块") String module,
            @ToolParam(description = "过滤参数对象: filters(AND)/orFilters(OR)/gte/lte(范围)/sortBy/sortOrder/limit/offset/allowBroadQuery") MetadataSearchQuery query) {
        if (module == null || (!"all".equals(module) && !VALID_MODULES.contains(module))) {
            return "未知模块: " + module + "，可用模块: spell(法术)/class(职业特性)/feat(专长)/race(种族)/trait(背景特性)/equipment(装备)/skill(技能)/rule(规则)/all(全部)";
        }
        List<String> available = availableFields(module);
        // F-026：参数校验先于门禁判定——非法字段/非法排序/非法 level 组合在门禁前返回，
        // 不产生 BLOCKED/ALLOWED 事件；放行字段不能修正非法输入。
        if (query != null) {
            List<String> unknown = new ArrayList<>();
            if (query.getFilters() != null) {
                query.getFilters().keySet().stream().filter(f -> !available.contains(f)).forEach(unknown::add);
            }
            if (query.getOrFilters() != null) {
                query.getOrFilters().keySet().stream().filter(f -> !available.contains(f)).forEach(unknown::add);
            }
            if (query.getGte() != null) {
                query.getGte().keySet().stream().filter(f -> !available.contains(f)).forEach(unknown::add);
            }
            if (query.getLte() != null) {
                query.getLte().keySet().stream().filter(f -> !available.contains(f)).forEach(unknown::add);
            }
            if (!unknown.isEmpty()) {
                return "未知过滤字段: " + unknown.stream().distinct().toList() + "，可用字段: " + available;
            }
            if ("spell".equals(module) && queryHasLevelCondition(query)
                    && (query.getFilters() == null || query.getFilters().get("className") == null
                            || query.getFilters().get("className").isBlank())) {
                return "level 比较（gte/lte/orFilters）必须配合 filters.className 指定职业，"
                        + "如 query={filters:{className:\"女巫\"}, gte:{level:\"3\"}}";
            }
            if (query.getSortBy() != null && !query.getSortBy().isBlank() && !SORT_FIELDS.contains(query.getSortBy())) {
                return "未知排序字段: " + query.getSortBy() + "，可用值: " + SORT_FIELDS;
            }
            if (query.getSortOrder() != null && !query.getSortOrder().isBlank()
                    && !SORT_ORDERS.contains(query.getSortOrder())) {
                return "未知排序方向: " + query.getSortOrder() + "，可用值: " + SORT_ORDERS;
            }
        }
        // F-026 工具护栏：无业务条件或仅来源书时，未放行不执行条目检索（返回收窄建议），
        // 放行后执行（含无条件分页）。每次判定各记一行 BLOCKED / ALLOWED 事件。
        Reason gateReason = BroadQueryGuard.metadataReason(query);
        if (gateReason != null) {
            AllowanceDecision decision = resolveBroadQueryAllowance(module,
                    query != null && query.isBroadQueryAllowed(),
                    query == null ? null : query.getFilters(),
                    query == null ? null : query.getOrFilters());
            if (!decision.allowed()) {
                recordGateBlocked("searchByMetadata", module,
                        decision.fingerprintMismatch() ? Reason.FINGERPRINT_MISMATCH : gateReason, query);
                return BroadQueryGuard.blockedMessage("searchByMetadata", module, gateReason, available);
            }
            recordGateAllowed("searchByMetadata", module, gateReason, query);
        }
        if (query.getLimit() == null) {
            query.setLimit(metadataDefaultLimit);
        }
        if (query.getOffset() == null) {
            query.setOffset(0);
        }
        SearchService.PagedResult paged;
        try {
            paged = searchService.searchByMetadataPaged(module, query);
        } catch (IllegalArgumentException e) {
            // 防御：SearchService 对非法模块的兜底，正常路径（已校验）不会到这
            return e.getMessage();
        }
        List<Document> docs = paged.page();
        if (docs.isEmpty()) {
            if (paged.offset() > 0 && paged.totalCount() > 0) {
                if (paged.capped()) {
                    if ("all".equals(module)) {
                        return "已翻完当前跨模块合并结果（本次可返回 " + paged.totalCount()
                                + " 条；至少一个模块已达单库检索上限 " + paged.cap()
                                + " 条，实际命中可能更多），请收窄过滤条件（如 book/level/title）后继续";
                    }
                    return "已翻完工具可返回的前 " + paged.totalCount()
                            + " 条（已达检索上限，实际命中可能更多），请收窄过滤条件（如 book/level/title）后继续";
                }
                return "已翻完全部结果（共 " + paged.totalCount() + " 条）";
            }
            return "无命中。建议：减少一个过滤条件（如去掉 book）或改用 vectorSearch；确认数据缺失再 reportDataGap";
        }
        SourceCollector.AddResult added = collector.addWithLimit(docs);
        return formatCompact(docs, added, "all".equals(module), paged, module) + guardHint(added);
    }

    /**
     * 元数据精确过滤（旧签名，无 @Tool）：仅供内部/既有测试兼容，行为与旧实现一致
     * （无结果返回空列表"[]"，不回退引导）。新调用走 query 参数对象版本。
     */
    public String searchByMetadata(String module, Map<String, String> filters) {
        if (module == null || !VALID_MODULES.contains(module)) {
            return "未知模块: " + module + "，可用模块: spell(法术)/class(职业特性)/feat(专长)/race(种族)/trait(背景特性)/equipment(装备)/skill(技能)/rule(规则)";
        }
        List<String> available = filterTranslator.availableFields(module);
        List<String> unknown = (filters == null ? Map.<String, String>of() : filters).keySet().stream()
                .filter(field -> !available.contains(field))
                .toList();
        if (!unknown.isEmpty()) {
            return "未知过滤字段: " + unknown + "，可用字段: " + available;
        }
        List<Document> docs;
        try {
            docs = searchService.searchByMetadata(module, filters == null ? Map.of() : filters);
        } catch (IllegalArgumentException e) {
            // 防御：SearchService 对非法模块的兜底，正常路径（已校验）不会到这
            return e.getMessage();
        }
        if (docs.isEmpty()) {
            return "[]";
        }
        SourceCollector.AddResult added = collector.addWithLimit(docs);
        return formatCompact(docs, added, false,
                new SearchService.PagedResult(docs, docs.size(), 0, docs.size()), module)
                + guardHint(added);
    }

    /**
     * 目录路径浏览（F-008）：按分段前缀查询 spell/feat/race/equipment 的清单条目。
     * 空前缀返回根层目录概览；非空前缀返回条目页（含 chunk_id/total/hasMore/
     * capped=false 与上级目录提示），只对当前展示页挂真实来源并遵守请求级来源护栏。
     * 路径分隔符与 chunk 元数据一致为 " → "，匹配按分段（"装备"不命中"装备附录"）。
     */
    @Tool(description = """
            按目录路径浏览四模块权威清单（spell/feat/race/equipment）。
            何时用：用户按目录/章节/来源书定位条目（如「核心规则书 → 装备里有哪些武器」
            「专长 → 战斗专长」），或不确定具体条目名、需要先看目录分支时。
            何时不用：已知条目名要点查用 resolveEntry/keywordSearch；元数据过滤用
            searchByMetadata；专长/种族/装备全清单枚举用 listEntries；法术按职业环级
            枚举用 getSpellList。
            module: "spell"(法术) / "feat"(专长) / "race"(种族) / "equipment"(装备) /
              "all"(全部，跨模块汇总)
            tocPrefix: 完整目录前缀，分段分隔符为 " → "（如 "核心规则书 → 装备"）；
              空前缀返回目录概览（各一级节点及其条目数），不伪装成条目页。
            limit: 每页条数（默认 50）；offset: 跳过条数（默认 0，可翻页）。
            返回条目页含 name/来源书/chunk_id/目录路径与 total/hasMore/capped=false，
            只对当前展示页挂来源编号 [#N]；未命中返回可用上级目录提示，
            不要据此判定数据缺失或调用 reportDataGap。
            """)
    public String listByToc(
            @ToolParam(description = "模块: spell(法术)/feat(专长)/race(种族)/equipment(装备)/all(全部)") String module,
            @ToolParam(required = false,
                    description = "完整目录前缀，分段分隔符为 \" → \"；省略或空串返回目录概览") String tocPrefix,
            @ToolParam(required = false, description = "每页条数，默认 50") Integer limit,
            @ToolParam(required = false, description = "跳过条数，默认 0") Integer offset) {
        String key = module == null || module.isBlank() ? "all" : module.trim();
        if (!"all".equals(key) && !TocListService.MODULES.contains(key)) {
            return "未知模块: " + module
                    + "，可用模块: spell(法术)/feat(专长)/race(种族)/equipment(装备)/all(全部)"
                    + "（当前可用: " + String.join("/", tocListService.knownModules()) + "）";
        }
        if (!"all".equals(key) && !tocListService.knownModules().contains(key)) {
            return "「" + key + "」目录清单暂不可用（清单未加载或解析失败），可用模块: "
                    + String.join("/", tocListService.knownModules())
                    + "；也可改用 listEntries/getSpellList/searchByMetadata 查询该模块。";
        }
        TocListService.TocResult result = tocListService.listByToc(key, tocPrefix, limit, offset);
        if (result instanceof TocListService.TocOverview overview) {
            return formatTocOverview(key, overview);
        }
        if (result instanceof TocListService.TocPage page) {
            return formatTocPage(key, tocPrefix, page);
        }
        return "目录查询无结果，请用空前缀查看目录概览后重试；不要据此判定数据缺失。";
    }

    /** 目录概览（空前缀）：一级节点 + 计数，不挂来源、不伪装成条目页 */
    private String formatTocOverview(String module, TocListService.TocOverview overview) {
        StringBuilder sb = new StringBuilder("目录概览（根层一级节点，按 module/tocPrefix 收窄）：\n");
        if (overview.nodes().isEmpty()) {
            sb.append("（当前没有可用的目录路径：清单未加载或条目缺少 toc_path；")
                    .append("可改用 listEntries/getSpellList 按模块查看，或提供更具体的目录前缀）");
            return sb.toString();
        }
        boolean crossModule = "all".equals(module);
        for (TocListService.TocNode node : overview.nodes()) {
            if (crossModule) {
                sb.append("- [").append(node.module()).append("] ");
            } else {
                sb.append("- ");
            }
            sb.append(node.segment()).append("（").append(node.count()).append(" 条）\n");
        }
        String example = overview.nodes().get(0).segment();
        sb.append("共 ").append(overview.nodes().size()).append(" 个一级节点，覆盖 ")
                .append(overview.total()).append(" 条有目录路径的条目。")
                .append("请从上述节点继续（如 tocPrefix=\"").append(example).append("\"）；")
                .append("概览不含条目正文与来源编号。");
        return sb.toString();
    }

    /** 目录条目页：分页元数据 + 仅展示页挂来源；未命中给上级目录提示 */
    private String formatTocPage(String module, String tocPrefix, TocListService.TocPage page) {
        boolean crossModule = "all".equals(module);
        if (page.items().isEmpty()) {
            StringBuilder sb = new StringBuilder();
            if (page.total() > 0) {
                sb.append("无条目可展示：共 ").append(page.total()).append(" 条命中，但 offset=")
                        .append(page.offset()).append(" 越界（limit=").append(page.limit())
                        .append("），请减小 offset 翻页。");
            } else {
                sb.append("未命中目录前缀「").append(tocPrefix == null ? "" : tocPrefix.trim()).append("」。");
            }
            List<String> ancestors = tocListService.ancestorPrefixes(module, tocPrefix);
            if (!ancestors.isEmpty()) {
                sb.append("\n可用上级目录: ");
                for (int i = 0; i < ancestors.size(); i++) {
                    if (i > 0) {
                        sb.append("；");
                    }
                    sb.append('「').append(ancestors.get(i)).append('」');
                }
                sb.append("（由近及远）。也可用空前缀查看目录概览。");
            } else {
                sb.append("可先用空前缀查看目录概览，或减少一层目录后重试；不要据此判定数据缺失。");
            }
            return sb.toString();
        }
        List<Document> docs = new ArrayList<>(page.items().size());
        for (TocListService.TocEntry entry : page.items()) {
            docs.add(tocProvenanceDocument(entry));
        }
        SourceCollector.AddResult added = collector.addWithLimit(docs);
        StringBuilder sb = new StringBuilder();
        int shown = 0;
        for (int i = 0; i < page.items().size(); i++) {
            Integer id = sourceNumber(added, i);
            if (id == null) {
                continue;
            }
            TocListService.TocEntry entry = page.items().get(i);
            shown++;
            sb.append(shown).append(". ");
            if (crossModule) {
                sb.append("[模块:").append(entry.module()).append("] ");
            }
            sb.append(entry.name());
            if (entry.book() != null && !entry.book().isBlank() && !"?".equals(entry.book())) {
                sb.append(" [").append(entry.book()).append(']');
            }
            sb.append(" | chunk_id: ")
                    .append(entry.chunkId() == null || entry.chunkId().isBlank() ? "—" : entry.chunkId())
                    .append(" | 目录: ").append(entry.tocPath())
                    .append(" [#").append(id).append("]\n");
        }
        int nextOffset = page.offset() + page.items().size();
        sb.append("（total=").append(page.total())
                .append("，hasMore=").append(page.hasMore())
                .append("，capped=false；本次展示 ").append(shown).append(" 条");
        if (page.hasMore()) {
            sb.append("；续取：保持 module/tocPrefix 不变，offset=").append(nextOffset);
        }
        sb.append("）");
        List<String> ancestors = tocListService.ancestorPrefixes(module, tocPrefix);
        if (!ancestors.isEmpty()) {
            sb.append("\n上级目录: ").append(String.join("；", ancestors))
                    .append("（如需更宽范围可回退一级）");
        }
        return sb.append(guardHint(added)).toString();
    }

    /** 目录条目溯源：真实 chunk 点查；未命中按既有规则降级合成 Document（[#N] 不缺席） */
    private Document tocProvenanceDocument(TocListService.TocEntry entry) {
        if (searchService != null && entry.chunkId() != null && !entry.chunkId().isBlank()) {
            Document doc = searchService.getByChunkId(entry.module(), entry.chunkId());
            if (doc != null) {
                return doc;
            }
        }
        Map<String, Object> meta = new HashMap<>();
        meta.put("title", entry.name());
        if (entry.book() != null && !entry.book().isBlank()) {
            meta.put("book_name_cn", entry.book());
        }
        if (entry.chunkId() != null && !entry.chunkId().isBlank()) {
            meta.put("chunk_id", entry.chunkId());
        }
        meta.put("toc_path", entry.tocPath());
        return Document.builder()
                .text("「" + entry.name() + "」清单条目（目录：" + entry.tocPath()
                        + "；向量库未检索到对应原文 chunk，可用 vectorSearch 检索该条目原文）")
                .metadata(meta)
                .build();
    }

    /**
     * 按条目名跨模块点查（SP8c J6）：拿到"见 XX"里的名字（或用户口语名）、
     * 不知道条目在哪个模块时用我精确解析。大小写不敏感、支持别名。
     * 唯一命中返回条目的 module/title/来源/chunk_id 并挂溯源；
     * 多义返回候选清单（module/title/书/chunk_id），可再带 module 参数调用消歧；
     * 查无此名返回空结果提示（转 vectorSearch 或 reportDataGap）。
     */
    @Tool(description = """
            按条目名跨模块精确解析（法术/专长/种族/装备/技能/规则/职业特性均可用）。
            当拿到条目名但不知道它在哪个模块、或要确认条目是否存在时使用——
            如"见 XX 法术/专长"中的名字、用户口语给出的条目名。大小写不敏感、支持别名。
            name: 条目中文名或别名；module: 可选模块消歧，已知条目类型时必须传入。
            命中唯一时返回 module/title/来源书/chunk_id（已挂来源编号，
            可继续 getEntryById 拿原文）；多义时返回候选清单（带 module 再调一次消歧）；
            查无此名时如实告知并建议改用 vectorSearch。需要引用链（变体/前置/谁引用了它）用 getEntryLinks。
            """)
    public String resolveEntry(
            @ToolParam(description = "条目名或别名，如 火球术") String name,
            @ToolParam(required = false, description = "可选模块消歧: spell/class/feat/race/trait/equipment/skill/rule") String module) {
        return resolveEntryInternal(name, module);
    }

    public String resolveEntry(String name) {
        return resolveEntry(name, null);
    }

    /**
     * 条目三层引用链（SP8c J6 Layer 0）：基础/变体（神话法术 base_spell 解析）、
     * 引用它的（专长 prerequisites 反查 + 法术环级表反向）、它引用的
     * （prerequisites 解析出的条目 + 职业环级表）。每条给 title/module/书/chunk_id 并挂溯源；
     * 解析不到的引用不展示（Layer 0 只覆盖已结构化的 metadata 关系，文本"见 XX"引用未覆盖）。
     */
    @Tool(description = """
            条目引用链查询：拿到条目名、需要它的关联条目时使用——基础/变体形态
            （如神话法术的基础法术）、前置专长/前置条件解析出的条目、哪些条目引用了它
            （专长前置反查、法术环级表反向）。name: 条目名或别名（大小写不敏感）；
            module: 可选，模块名消歧（多义时返回候选清单）。
            每条链接给 title/module/来源书/chunk_id（已挂来源编号，可继续 getEntryById 拿原文）。
            只输出能精确解析的引用，解析不到的边不展示；查无此名返回提示。
            """)
    public String getEntryLinks(
            @ToolParam(description = "条目名或别名") String name,
            @ToolParam(required = false, description = "可选模块消歧: spell/class/feat/race/trait/equipment/skill/rule") String module) {
        if (!entryResolver.isEnabled()) {
            return ENTRY_RESOLVER_DISABLED_HINT;
        }
        if (module != null && !module.isBlank() && !VALID_MODULES.contains(module)) {
            return "未知模块: " + module + "，可用模块: spell(法术)/class(职业特性)/feat(专长)/race(种族)/trait(背景特性)/equipment(装备)/skill(技能)/rule(规则)";
        }
        List<EntryResolver.EntryRef> candidates = resolveCandidates(name, module);
        if (candidates.isEmpty()) {
            return "未找到条目「" + name + "」。建议：改用 vectorSearch 语义检索；"
                    + "确认数据缺失再 reportDataGap（可选带 module 参数收窄候选）";
        }
        if (candidates.size() > 1) {
            return formatAmbiguous(name, candidates);
        }
        return formatEntryLinks(candidates.get(0));
    }

    /**
     * 条目名子串匹配（SP8d J7 keywordSearch v1）：title/alias 双向子串检索。
     * 当用户给出确切条目名/专有名词但 resolveEntry 查无此名、或 vectorSearch 语义
     * 检索漏召回精确术语时用我兜底；描述性问题仍走 vectorSearch。
     * 排序：精确命中 > 前缀命中 > 子串命中、短 title 优先，上限
     * pf.search.entry-resolver-max-results（默认 20）。每条给 module/title/来源书/
     * chunk_id 并挂溯源，拿到 chunk_id 后用 getEntryById 取原文。
     */
    @Tool(description = """
            按条目名/术语做 title 与别名的子串匹配（法术/专长/种族/装备/技能/规则/职业特性均可用）。
            何时用：用户给出确切条目名或专有名词、resolveEntry 精确解析查无此名，
            或 vectorSearch 语义检索漏召回该术语时兜底。何时不用：描述性/机制类问题
            走 vectorSearch，元数据过滤走 searchByMetadata。
            term: 条目名或术语片段（大小写不敏感、支持全半角混用）；module: 可选模块收窄。
            返回按「精确 > 前缀 > 子串、短名优先」排序的候选清单（module/title/来源书/chunk_id，
            已挂来源编号）；命中后用 getEntryById 按 chunk_id 取原文。
            恰有精确同名条目时会先行提示（等价于 resolveEntry 的解析结果）。
            """)
    public String keywordSearch(
            @ToolParam(description = "条目名或术语片段，如 火球") String term,
            @ToolParam(required = false, description = "可选模块收窄: spell/class/feat/race/trait/equipment/skill/rule") String module) {
        if (!entryResolver.isEnabled()) {
            return ENTRY_RESOLVER_DISABLED_HINT;
        }
        if (term == null || term.isBlank()) {
            return "请提供检索术语（term），如 keywordSearch(term=\"火球\")";
        }
        if (module != null && !module.isBlank() && !VALID_MODULES.contains(module)) {
            return "未知模块: " + module + "，可用模块: spell(法术)/class(职业特性)/feat(专长)/race(种族)/trait(背景特性)/equipment(装备)/skill(技能)/rule(规则)";
        }
        List<EntryResolver.EntryRef> candidates = entryResolver.substringSearch(term, module);
        if (candidates.isEmpty()) {
            return "未找到包含「" + term + "」的条目（title/别名子串均无命中）。建议："
                    + "改用 vectorSearch 语义检索或 searchByMetadata 元数据过滤；"
                    + "确认数据缺失再 reportDataGap（可选带 module 参数收窄范围）";
        }
        return formatKeywordHits(term, module, candidates);
    }

    /** keywordSearch 命中清单：可选精确同名提示 + 逐条 module/title/书/chunk_id + 来源编号 */
    private String formatKeywordHits(String term, String module, List<EntryResolver.EntryRef> candidates) {
        List<EntryResolver.EntryRef> exact = entryResolver.resolve(term, module);
        List<Document> docs = new ArrayList<>();
        List<EntryResolver.EntryRef> fetchedRefs = new ArrayList<>();
        for (EntryResolver.EntryRef ref : candidates) {
            Document doc = searchService.getByChunkId(ref.module(), ref.chunkId());
            if (doc != null) {
                docs.add(doc);
                fetchedRefs.add(ref);
            }
        }
        SourceCollector.AddResult added = collector.addWithLimit(docs);
        Map<String, Integer> idByChunkKey = new HashMap<>();
        Set<String> droppedKeys = new HashSet<>();
        for (int i = 0; i < docs.size(); i++) {
            EntryResolver.EntryRef ref = fetchedRefs.get(i);
            Integer id = sourceNumber(added, i);
            if (id == null) {
                droppedKeys.add(ref.module() + "|" + ref.chunkId());
            } else {
                idByChunkKey.put(ref.module() + "|" + ref.chunkId(), id);
            }
        }
        StringBuilder sb = new StringBuilder();
        if (!exact.isEmpty()) {
            sb.append("存在精确同名条目（亦可用 resolveEntry 解析）：")
                    .append(exact.stream().map(EntryResolver.EntryRef::title).distinct().toList()).append('\n');
        }
        sb.append("命中 ").append(candidates.size()).append(" 个候选（按精确>前缀>子串、短名优先排序）：\n");
        int i = 1;
        for (EntryResolver.EntryRef ref : candidates) {
            if (droppedKeys.contains(ref.module() + "|" + ref.chunkId())) {
                continue;   // 护栏拒绝的条目不进入工具输出
            }
            sb.append(i++).append(". ").append(refLine(ref, idByChunkKey)).append('\n');
        }
        sb.append("（用 getEntryById 按 chunk_id 取原文；命中过多可用 module 参数收窄）");
        return sb.append(guardHint(added)).toString();
    }

    /**
     * 既有两参入口（无 @Tool）：保留给 Java 调用方，委托三参实现。
     * 模块校验与空参提示保持原顺序；标题型章节展开语义与三参一致。
     */
    public String getEntryById(String module, String chunkId) {
        if (module == null || !VALID_MODULES.contains(module)) {
            return getEntryById(module, chunkId, null);
        }
        if (chunkId == null || chunkId.isBlank()) {
            return "请提供 chunkId（来自 vectorSearch/searchByMetadata 返回结果中的 chunk_id 字段）";
        }
        return getEntryById(module, chunkId, null);
    }

    /**
     * 按 (module, chunk_id) 点查完整原文（SP8a J1）；AKN-023 扩展为同模块批量取文。
     * 单条：提供 chunkId、不提供 chunkIds；批量：提供 chunkIds、不提供 chunkId。
     * 拿到 vectorSearch/searchByMetadata 命中但需要完整原文（全文条款、表格）时使用；
     * 超长条目截断到 pf.search.entry-result-chars（默认 8000），可用 vectorSearch 定位子片段。
     * 批量按输入顺序去重、最多 BATCH_ENTRY_MAX_IDS 条，总输出受 BATCH_ENTRY_RESULT_CHARS 约束；
     * 未实际展示的条目不写入 SourceCollector。
     */
    @Tool(description = """
            按 chunk_id 点查条目的完整原文（绕过片段截断）。当 vectorSearch/searchByMetadata
            的命中片段不够用、需要完整全文（如全文条款、表格、长条目）时使用。
            module: 数据模块（同 searchByMetadata）。
            单条：chunkId 必须来自此前工具返回结果中的 chunk_id 字段。
            批量：chunkIds 为同模块多个 chunk_id（按输入顺序去重，最多 10 条），用于一次取回
            多个条目原文；chunkId 与 chunkIds 只能二选一，批量时传 chunkId=null。
            若点中的 chunk 正文只有标题，且同 doc_id + tocPath 章节为 2~10 条，
            单条或显式批量都会自动展开章节条目；批量展开后与其他指定 ID 去重，
            子条目不递归展开。完整展开后直接基于已取回内容作答。
            大章节或达到检索上限时不自动展开；未展开、未返回 ID 或内容不足时，
            按提示继续分批或定向检索，不得声称已取得完整章节。
            超长条目会截断（上限 pf.search.entry-result-chars，默认 8000），需要子片段时可再用
            vectorSearch。批量输出以分隔线分段，总长受单次预算约束；预算不足时明确列出本次
            未返回的 ID，请缩小批量后分批重试。
            """)
    public String getEntryById(
            @ToolParam(description = "数据模块: spell/class/feat/race/trait/equipment/skill/rule") String module,
            @ToolParam(required = false,
                    description = "单条条目 chunk_id，必须来自此前检索工具返回结果的 chunk_id 字段；与 chunkIds 二选一") String chunkId,
            @ToolParam(required = false,
                    description = "批量条目 chunk_id 列表（同模块，按输入顺序去重，最多 10 条）；与 chunkId 二选一") List<String> chunkIds) {
        if (module == null || !VALID_MODULES.contains(module)) {
            return "未知模块: " + module + "，可用模块: spell(法术)/class(职业特性)/feat(专长)/race(种族)/trait(背景特性)/equipment(装备)/skill(技能)/rule(规则)";
        }
        if (chunkId != null && chunkIds != null) {
            return "chunkId 与 chunkIds 只能提供一个，请二选一后重试";
        }
        if (chunkId == null && chunkIds == null) {
            return "请至少提供 chunkId 或 chunkIds 之一（来自检索结果中的 chunk_id 字段）";
        }
        if (chunkId != null) {
            if (chunkId.isBlank()) {
                return "请提供 chunkId（来自 vectorSearch/searchByMetadata 返回结果中的 chunk_id 字段）";
            }
            EntryLoadResult load = loadEntry(module, chunkId);
            SearchService.DocumentSection section = headingSection(module, load.doc());
            if (section != null) {
                if (section.capped()) {
                    return collectAndFormatEntry(load, module, chunkId)
                            + "\n\n（同章节达到检索上限，未自动展开；请用 vectorSearch 定向检索子条目，"
                            + "不要声称已取得完整章节）";
                }
                if (section.documents().size() > BATCH_ENTRY_MAX_IDS) {
                    return collectAndFormatEntry(load, module, chunkId)
                            + "\n\n（同页 " + section.documents().size() + " 条，超过 10 条自动展开上限，"
                            + "未自动展开；请用 chunkIds 分批取文或 vectorSearch 定向检索）";
                }
                if (section.documents().size() > 1) {
                    List<String> sectionIds = section.documents().stream().map(this::entryChunkId).toList();
                    List<EntryLoadResult> preloaded = section.documents().stream()
                            .map(doc -> new EntryLoadResult(doc, null))
                            .toList();
                    return formatEntryBatch(module, sectionIds, preloaded);
                }
            }
            return collectAndFormatEntry(load, module, chunkId);
        }
        if (chunkIds.isEmpty()) {
            return "chunkIds 至少需要提供 1 条 ID（来自检索结果中的 chunk_id 字段）";
        }
        Set<String> deduped = new LinkedHashSet<>();
        for (String raw : chunkIds) {
            if (raw == null || raw.isBlank()) {
                return "chunkIds 中包含空白 ID，请提供来自检索结果中的非空 chunk_id";
            }
            deduped.add(raw.trim());
        }
        List<String> ids = new ArrayList<>(deduped);
        if (ids.size() > BATCH_ENTRY_MAX_IDS) {
            return "chunkIds 去重后最多 10 条，本次为 " + ids.size() + " 条，请缩小批量后分批重试";
        }
        Map<String, EntryLoadResult> expanded = new LinkedHashMap<>();
        for (String id : ids) {
            EntryLoadResult load = loadEntry(module, id);
            SearchService.DocumentSection section = headingSection(module, load.doc());
            if (section != null && !section.capped()
                    && section.documents().size() > 1
                    && section.documents().size() <= BATCH_ENTRY_MAX_IDS) {
                for (Document doc : section.documents()) {
                    expanded.putIfAbsent(entryChunkId(doc), new EntryLoadResult(doc, null));
                }
            } else {
                expanded.putIfAbsent(id, load);
            }
        }
        if (expanded.size() > BATCH_ENTRY_MAX_IDS) {
            return "chunkIds 展开后超过 10 条（本次为 " + expanded.size()
                    + " 条），请缩小批量或分批取文，避免未返回条目被误认为完整章节";
        }
        return formatEntryBatch(module, List.copyOf(expanded.keySet()),
                List.copyOf(expanded.values()));
    }

    private String formatEntryBatch(String module, List<String> ids,
                                    List<EntryLoadResult> preloaded) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < ids.size(); i++) {
            String id = ids.get(i);
            EntryLoadResult load = preloaded.isEmpty() ? loadEntry(module, id) : preloaded.get(i);
            String separator = out.length() == 0 ? "" : BATCH_ENTRY_SEPARATOR;
            String overflowHint = batchOverflowHint(ids.subList(i, ids.size()));
            int estimated = estimatedEntryChars(load, module, id);
            // 为 append 之后所有可能的 break suffix 预留空间：分隔符 + 剩余 ID 提示。
            // 每次成功 append 后都满足 out + SEP + hint(i) <= 上限，因此后续任一 break
            // 追加 separator + overflowHint 都不会超限（提示不被截断）。
            int futureSuffix = BATCH_ENTRY_SEPARATOR.length() + overflowHint.length();
            if (i >= BATCH_ENTRY_MAX_IDS || out.length() + separator.length() + estimated + futureSuffix
                    > BATCH_ENTRY_RESULT_CHARS) {
                // 条数或字符预算不足：本条及其后条目均未展示，必须明确列出，且不写入 SourceCollector
                out.append(separator).append(overflowHint);
                break;
            }
            out.append(separator).append(collectAndFormatEntry(load, module, id));
        }
        return out.toString();
    }

    private SearchService.DocumentSection headingSection(String module, Document doc) {
        if (doc == null || !isHeadingOnly(doc)) {
            return null;
        }
        String docId = value(doc, "doc_id");
        String tocPath = value(doc, "tocPath");
        if (docId.isBlank() || tocPath.isBlank()) {
            return null;
        }
        return searchService.getByDocId(module, docId, tocPath);
    }

    private boolean isHeadingOnly(Document doc) {
        String text = doc.getText() == null ? "" : doc.getText().replaceAll("[\\s\\u3000]+", "");
        String title = value(doc, "title").replaceAll("[\\s\\u3000]+", "");
        return !title.isEmpty() && text.equals(title);
    }

    private String entryChunkId(Document doc) {
        String chunkId = value(doc, "chunk_id");
        return chunkId.isBlank() ? doc.getId() : chunkId;
    }

    /**
     * 列出已报告的数据缺口（SP8a J3，只读）：调用 reportDataGap 前查重，避免重复上报。
     * 最新在前，limit 默认 pf.gaps.list-default-limit（20）、上限 100；keyword 对
     * question/reason 子串匹配（可空）。F-021 起读 data_gap 表；库不可用与「无记录」分别回话
     * （不把库故障说成「暂无记录」，否则 LLM 会据此判定没有重复缺口）。
     */
    @Tool(description = """
            列出已报告的数据缺口记录（只读）。调用 reportDataGap 之前先用我查重，
            若已有相同/相近缺口记录则不必重复上报。
            limit: 返回条数，默认 20，上限 100；keyword: 按 question/reason 子串过滤，可空。
            返回最新在前的「时间 | question | reason」列表。
            """)
    public String listDataGaps(
            @ToolParam(required = false, description = "返回条数，默认 20，上限 100") Integer limit,
            @ToolParam(required = false, description = "按 question/reason 子串过滤，可空") String keyword) {
        int effective = limit == null ? gapsListDefaultLimit : Math.min(Math.max(limit, 1), 100);
        DataGapRecorder.GapQueryResult result = recorder.listGaps(effective, keyword);
        if (!result.available()) {
            return "数据缺口库不可用（持久化未装配或读取失败），无法查重。";
        }
        List<DataGapRecorder.GapEntry> gaps = result.gaps();
        if (gaps.isEmpty()) {
            return keyword == null || keyword.isBlank()
                    ? "暂无数据缺口记录"
                    : "暂无匹配 keyword=" + keyword + " 的数据缺口记录";
        }
        StringBuilder sb = new StringBuilder("数据缺口记录（最新在前，共 ").append(gaps.size()).append(" 条）：\n");
        for (DataGapRecorder.GapEntry gap : gaps) {
            sb.append(formatGapLine(gap)).append('\n');
        }
        return sb.toString();
    }

    /**
     * 语义检索，返回相似度最高的规则片段（正文截断到 vector-result-chars）。
     * 完整原文由 SourceCollector 留给前端溯源，不影响工具返回的紧凑度。
     */
    @Tool(description = """
            语义检索规则原文。用于：查具体规则细节（如"火球术的射程"）、
            不知道精确元数据字段、元数据过滤无结果时。
            question: 检索问题；module: "spell"(法术) / "class"(职业) / "feat"(专长) /
              "race"(种族) / "trait"(背景特性) / "equipment"(装备) / "skill"(技能) /
              "rule"(规则) / "all"(全部)
            模块语义边界:
              - class: 职业特性/职业变体，以及角色升级、兼职(Multiclassing)、升级时
                生命值/法术位/BAB 成长（在「职业 → 角色升级」，不在 rule）
              - rule: 战斗动作/状态效果/环境/移动等通用游戏规则
              - spell/feat/race/trait/equipment/skill: 对应具体条目
            拿不准模块时先用 module:"all"，据命中结果的 tocPath（目录路径）再定向。
            返回相似度最高的若干条规则片段（单条正文截断到 pf.search.vector-result-chars，
            默认 1500 字符，超出部分省略），完整原文见前端来源折叠区。
            """)
    public String vectorSearch(
            @ToolParam(description = "检索问题描述") String question,
            @ToolParam(description = "数据模块: spell(法术) / class(职业特性+角色升级/兼职) / feat(专长) / race(种族) / trait(背景特性) / equipment(装备) / skill(技能) / rule(通用规则) / all(全部，拿不准时用)") String module) {
        if (module == null || (!"all".equals(module) && !VALID_MODULES.contains(module))) {
            return "未知模块: " + module + "，可用模块: spell(法术)/class(职业)/feat(专长)/race(种族)/trait(背景特性)/equipment(装备)/skill(技能)/rule(规则)/all(全部)";
        }
        List<Document> docs = searchService.search(question == null ? "" : question, module);
        if (docs.isEmpty()) {
            return "[]";
        }
        SourceCollector.AddResult added = collector.addWithLimit(docs);
        return formatFragments(docs, added) + guardHint(added);
    }

    /**
     * 数据缺口报告：全部检索手段都无法回答时记录，供后续优化。
     *
     * F-021：record 返回 false（DB 不可用/写入失败）时不算已记录——不置 gapReported、
     * 回话如实说明未记录，避免把「没落库」谎报成「已记录待优化」。
     */
    @Tool(description = """
            数据缺口报告：当 searchByMetadata / vectorSearch 都无法找到回答
            用户问题所需的规则数据时调用，把问题记录下来供后续优化。
            question: 用户原始问题；attemptedFilters: 已尝试的过滤条件(JSON字符串，可空)；
            reason: 缺什么数据（如"找不到女巫的XX规则"）。
            记录后如实告知用户缺少相关知识。
            """)
    public String reportDataGap(
            @ToolParam(description = "用户原始问题") String question,
            @ToolParam(description = "已尝试的过滤条件，JSON 字符串，可空") String attemptedFilters,
            @ToolParam(description = "缺什么数据") String reason) {
        boolean persisted = recorder.record(question, attemptedFilters, reason);
        if (!persisted) {
            return "数据缺口未能记录（持久化不可用）。请如实告知用户缺少相关知识。";
        }
        collector.markGapReported();
        return "已记录数据缺口：question=" + question + "，attemptedFilters=" + attemptedFilters
                + "，reason=" + reason + "。请如实告知用户缺少相关知识。";
    }

    /**
     * 枚举某职业某环级法术的权威清单（SP3 F-007，D5）。直查数据侧预整理的
     * spell_lists.json——枚举式问题不再依赖 searchByMetadata（spell_level 元数据
     * 缺失率 35% + 职业名脏变体不可靠）。命中后把该职业的列表页作为溯源 Document
     * 交 SourceCollector（单个法术不逐条挂溯源，列表页即权威出处）。
     */
    @Tool(description = """
            列举某职业某环级法术的权威完整清单。当用户问「XX职业N环法术有哪些」这类
            枚举式问题时优先用我，比 searchByMetadata 更全更准（官方列表页直查，
            不受 spell_level 元数据缺失与职业名变体影响）。
            className: 职业中文名，支持别名（诗人/游吟诗人→吟游诗人、圣武士→圣骑士等）；
            level: 环级 0~9，可省略（省略时返回该职业各环级条目数概览，不会一次塞全表）。
            未知职业返回可用职业清单。已知职业返回「序号. 中文名（English） [书]」紧凑清单。
            结果过多自动截断并给真实总数/返回区间/has_more/续取 offset（与 searchByMetadata
            翻页同构）；也可用 offset/limit 主动翻页，翻到末页提示「已翻完全部结果」。
            覆盖口径（B1，2026-10-29 拍板）：五书线 20 职业返回 清单页五书（CRB/APG/UM/UC/ACG）
            ∪ 库侧 spell_level 派生条目（全库书范围，含〔派生〕标注——派生覆盖受 spell_level
            空率 10.1% 残留限制，非全库完整枚举）；唤魂师/秘学士/通灵者/异能者/催眠师五职业
            仅官方清单（OA 清单页跨 20+ 书，不派生）。条目数不等于全库法术总数，
            需要穷尽时请说明口径并用 searchByMetadata 补查。
            去重口径（F-025）：union 1.1 产物内同一职业同一环级每个法术只出现一次，
            同一法术的全部来源书以缩写并列展示（如 [PSP/COMP]）；仅主来源为派生的条目
            带〔派生〕标注，官方主条目合并派生来源后不标注；「共 N 条」= 折叠后的
            不同法术数，概览/清单/分页 footer 同口径。
            """)
    public String getSpellList(
            @ToolParam(description = "职业中文名，如 法师/吟游诗人，支持常见别名") String className,
            @ToolParam(description = "法术环级 0~9；省略则返回该职业各环级条目数概览") Integer level,
            @ToolParam(description = "跳过的条目数（默认 0，可翻页；与 J2 searchByMetadata 同构。"
                    + "结果被截断时按提示续取：保持其他参数不变，offset=提示值）") Integer offset,
            @ToolParam(description = "返回条数上限（默认单次展示上限内全量；配合 offset 翻页）") Integer limit) {
        if (!spellListService.isAvailable()) {
            return "职业法术列表清单暂不可用（spell_lists.json 未加载），请改用 searchByMetadata 查询。";
        }
        if (className == null || className.isBlank()) {
            return "请提供职业名（className），如 getSpellList(className=\"法师\")。可用职业: "
                    + String.join("、", spellListService.knownClasses());
        }
        String canonical = spellListService.resolve(className);
        if (canonical == null) {
            return "未知职业: " + className + "，可用职业: " + String.join("、", spellListService.knownClasses())
                    + "（支持常见别名，如 诗人→吟游诗人、圣武士→圣骑士）";
        }
        // 命中职业：概览与单环清单都源自列表页，统一挂溯源（D5：列表页即权威出处）；
        // SP4 D2：清单单来源，只在末尾挂一行编号，不逐条挂号
        SourceCollector.AddResult added = collector.addWithLimit(
                List.of(spellListService.listPageDocument(canonical)));
        if (singleSourceRejected(added)) {
            return singleSourceRejectedHint("「" + canonical + "」法术清单");
        }
        String sourceLine = singleSourceLine(added, "本清单来源");
        if (level == null) {
            return spellListService.levelOverview(canonical) + sourceLine;
        }
        if (level < 0 || level > 9) {
            return "环级须在 0~9 之间（0 为戏法/祷念）。" + spellListService.levelOverview(canonical) + sourceLine;
        }
        return spellListService.formatLevel(canonical, level, metadataResultChars, offset, limit)
                + sourceLine;
    }

    /**
     * 职业成长表查表（J5，F-019）：输入职业+等级，直接返回 BAB/强韧/反射/意志豁免/
     * 特殊能力/每日法术位——派生数值的唯一权威入口，LLM 禁止按公式自行计算。
     * 直查数据侧 class_tables.json，优于让 LLM 回忆或推算成长数值。
     * className: 职业名（中文/英文/俗称，支持别名，如 诗人→吟游诗人）；
     * level: 等级 1~20，可省略（省略=返回该职业 1~max_level 全表）。
     * 何时不用：法术清单枚举走 getSpellList；机制解释（"为什么法师 BAB 低"）与
     * 兼职 BAB 合成规则走 vectorSearch；职业特性正文走 searchByMetadata/getEntryById。
     * 未覆盖职业如实告知并引导 vectorSearch，绝不编造数值。
     */
    @Tool(description = """
            查职业成长表：当用户问「XX职业N级的 BAB/基本攻击加值、强韧/反射/意志豁免、
            每日法术位、特殊能力」这类按等级的派生数值时必须用我查表，禁止按公式自行计算。
            直查数据侧预整理的成长表（官方「表：XX」逐行），比 LLM 推算可靠。
            className: 职业名，支持别名（中文/英文/俗称，如 诗人→吟游诗人、圣武士→圣骑士）；
            level: 等级，可省略（省略=返回该职业 1~20 全表，每行含 BAB/三项豁免/特殊/每日法术位）。
            何时不用：法术清单枚举走 getSpellList；机制解释（"为什么法师 BAB 低""兼职怎么合成"）
            与兼职规则走 vectorSearch；职业特性/变体正文走 searchByMetadata/getEntryById。
            未知职业返回可用职业清单；数据侧未覆盖的职业如实告知并建议 vectorSearch，绝不编造数值。
            """)
    public String getClassTable(
            @ToolParam(description = "职业名，如 法师/战士/吟游诗人，支持常见别名") String className,
            @ToolParam(required = false, description = "等级 1~20；省略则返回该职业全表") Integer level) {
        if (!classTableService.isAvailable()) {
            return "职业成长表暂不可用（class_tables.json 未加载），请改用 vectorSearch 检索职业成长规则。";
        }
        if (className == null || className.isBlank()) {
            return "请提供职业名（className），如 getClassTable(className=\"法师\")。可用职业: "
                    + String.join("、", classTableService.knownClasses());
        }
        String canonical = classTableService.resolve(className);
        if (canonical == null) {
            if (classTableService.missingClasses().contains(className.trim())) {
                return "「" + className.trim() + "」的成长表数据侧尚未整理（已登记缺失清单），"
                        + "可改用 vectorSearch 检索该职业成长规则原文，或确认后 reportDataGap。"
                        + "已收录职业: " + String.join("、", classTableService.knownClasses());
            }
            return "未知职业: " + className + "，可用职业: " + String.join("、", classTableService.knownClasses())
                    + "（支持常见别名，如 诗人→吟游诗人、圣武士→圣骑士）";
        }
        // 命中职业：成长表行统一挂真实 chunk 溯源（点查未命中时服务内降级合成，[#N] 不缺席）
        SourceCollector.AddResult added = collector.addWithLimit(
                List.of(classTableService.provenanceDocument(canonical)));
        if (singleSourceRejected(added)) {
            return singleSourceRejectedHint("「" + canonical + "」职业成长表");
        }
        String sourceLine = singleSourceLine(added, "来源编号");
        int maxLevel = classTableService.maxLevel(canonical);
        if (level == null) {
            return classTableService.formatTable(canonical) + sourceLine;
        }
        if (level < 1 || level > maxLevel) {
            return "「" + canonical + "」成长表覆盖等级 1~" + maxLevel + "，level=" + level + " 越界。"
                    + classTableService.formatTable(canonical) + sourceLine;
        }
        return classTableService.formatRow(canonical, level) + sourceLine;
    }

    /**
     * 规则内嵌表格查表（KN221，spec D8）：按表名/table_id/chunk_id 定位规则正文里的
     * 表格，可选按行键取行。standard/flattened/no_separator 的 layout 差异显式告知；
     * flattened 只返回原文行、不伪造列级结构。命中表挂 chunk 溯源（点查未命中服务内
     * 降级合成，[#N] 不缺席）；模糊多命中返回候选要求用 table_id/chunk_id 消歧。
     * 数值/等级类表格问题必须查表，LLM 禁止自行推算。
     */
    @Tool(description = """
            查规则原文中的内嵌表格（如动物伙伴基本数据、状态/环境数值表、装备表等）。
            当用户问某张表里某一行/某个等级的数值时必须用我查表，禁止自行推算、插值或
            凭记忆复原表格内容。
            table: 表名/表题/table_id/chunk_id，如 "动物伙伴基本数据" 或
              "rule_page_299_0000#t1" 或 "rule_page_299_0000"。
            row: 可选行键，如 "5" / "5级" / "第5行"（standard 表按首个非空单元格匹配，
              再按任意单元格匹配；flattened 表按原文行号或原文内容匹配）。
            返回表头 + 最多 20 行（无 row 时）或命中行（有 row 时），末尾附来源编号。
            layout=flattened 的表分隔行位置不规范，只承诺原文行、不承诺列级对应，
              引用时按原文表述，不要臆测列值。
            表名模糊命中多张表时返回候选清单（table_id/chunk_id），请改用 table_id 或
              chunk_id 精确定位后重试；未收录表名会如实告知并给检索建议，不要编造表格。
            何时不用：机制解释/散文规则走 vectorSearch；条目正文走 getEntryById；
              职业成长表数值走 getClassTable；法术清单走 getSpellList。
            示例: getRuleTable(table="动物伙伴基本数据", row="5")
            """)
    public String getRuleTable(
            @ToolParam(description = "表名/表题/table_id/chunk_id，如 动物伙伴基本数据") String table,
            @ToolParam(required = false,
                    description = "可选行键，如 5 / 5级 / 第5行；省略则返回表头 + 前 20 行") String row) {
        if (!ruleTableService.isAvailable()) {
            return "规则表格数据暂不可用（rule_tables.json 未加载），"
                    + "请改用 vectorSearch 或 getEntryById 检索规则原文。";
        }
        if (table == null || table.isBlank()) {
            return "请提供表名或 table_id（如 getRuleTable(table=\"动物伙伴基本数据\", row=\"5\")），"
                    + "可用 searchByMetadata(module=\"rule\") 或 vectorSearch 先定位规则表格所在条目。";
        }
        List<RuleTableService.RuleTable> matches = ruleTableService.find(table);
        if (matches.isEmpty()) {
            return "未收录表名「" + table.trim() + "」。建议：用 searchByMetadata(module=\"rule\") "
                    + "或 vectorSearch 检索包含该表的规则原文后，用其中 chunk_id 作为 table 参数重试；"
                    + "确认数据缺失再 reportDataGap。不要编造表格数值。";
        }
        if (matches.size() > 1) {
            return ruleTableService.formatCandidates(table, matches);
        }
        RuleTableService.RuleTable matched = matches.get(0);
        SourceCollector.AddResult added = collector.addWithLimit(
                List.of(ruleTableService.provenanceDocument(matched)));
        if (singleSourceRejected(added)) {
            return singleSourceRejectedHint("表「" + matched.title() + "」");
        }
        String sourceLine = singleSourceLine(added, "来源编号");
        return ruleTableService.formatTable(matched, row) + sourceLine;
    }

    /**
     * 专长/种族/装备权威清单枚举（B4，D2）：直查数据侧预整理的完整清单 JSON，
     * 不受向量库元数据缺失影响（对齐 getSpellList 的 spell_level 35% 缺失先例）。
     * 无条件查询返回统计概览（防 4080 条全量刷屏）；有条件逐行返回并挂 [#N] 溯源。
     */
    @Tool(description = """
            枚举专长/种族/装备的权威完整清单。当用户问「XX有哪些/全部/清单」这类
            权威枚举式问题、或按来源书/类别/关键词数清单时必须用我，直查数据侧预整理的
            完整清单（不受向量库元数据缺失影响，比 searchByMetadata 拼结果更全更准）。
            module: "feat"(专长) / "race"(种族) / "equipment"(装备)。
            query（参数对象，全字段可空）:
              - keyword: 名称/英文名/别名子串（大小写不敏感、全半角容错）
              - filters: 字段→值 AND 精确匹配；orFilters: 组内 OR（如 book:["CRB","APG"]）
              - limit: 返回条数（默认 50，上限 200）；offset: 跳过条数（默认 0，可翻页）
              - sortBy: "name"(默认) | "book" | "price"(仅 equipment，按 price_gp 排序)
              - sortOrder: "asc"(默认) | "desc"；price 降序可直接回答「最贵」类问题
              - allowBroadQuery: 布尔，默认 false。仅当用户已明确确认「仍按原范围查询」时设 true；
                仅 book 条件未放行会返回收窄建议而不检索，同一逻辑查询每页都需携带；
                服务端按会话记录 module+book 放行指纹，换模块或换书后需重新向用户确认；
                同一轮内或重新生成时重试不会自动放行，需等用户下一轮明确确认
            价格口径（仅 equipment）:
              - price 原文单位 gp；排序/区间过滤使用数值 price_gp（整数 gp）
              - 仅统计有明确标价的条目（price_gp 非空）；无标价条目保留但排序时始终排最后，
                不参与「最高价/最低价」结论；旧版清单无 price_gp 时 price 排序会被拒绝并提示
            宽查询纪律:
              - 用户问「某书所有/全部专长/种族/装备」等宽问题，先以 allowBroadQuery=false
                （缺省）调用本工具登记真实 module+book（query 只带用户提到的书条件；
                filters:{book:"…"}，未提书就留空），再据返回的收窄建议向用户说明范围、
                给出 2~4 个有效收窄示例（如书+类别/部位/关键词）、概览选项和原范围继续选项
              - 同一轮内不要改用 allowBroadQuery=true 重试（同轮不能确认自己刚登记的范围），
                必须等用户下一轮明确确认；工具返回的收窄建议不是「查询无结果」或「数据缺失」
              - 小范围问题（具体类别/部位/关键词/具体条目）正常调用，不触发门禁
            各模块可用 filters 字段:
              - feat: featType（专长类别，如 战斗/团队）、book、hasPrerequisites("true"/"false")
              - race: raceGroup（种族分组）、size（体型，如 中型）、bioType、book
              - equipment: componentType、slot、book、price_min/price_max（整数 gp 区间，
                仅命中 price_gp 非空的条目，如 {price_min:"1000", price_max:"235000"}）
            无条件（query 空或全 null）返回该模块统计概览 + 收窄引导，不会一次塞全表。
            过滤值须为非空字符串；hasPrerequisites 只接受 "true"/"false"。
            字段名错误时返回该模块可用字段清单。结果过长自动截断并提示用 offset 翻页。
            何时不用：单个条目的效果/规则细节走 vectorSearch/getEntryById；
            法术清单枚举走 getSpellList；职业成长数值走 getClassTable；
            元数据关系反查走 searchByMetadata/getEntryLinks。
            """)
    public String listEntries(
            @ToolParam(description = "清单模块: feat(专长) / race(种族) / equipment(装备)") String module,
            @ToolParam(required = false,
                    description = "过滤/分页参数对象，全字段可空。无条件时返回该模块统计概览；allowBroadQuery=true 表示用户已确认按原范围查询") ListEntriesQuery query) {
        if (module == null || !ListExportService.MODULES.contains(module)) {
            return "未知模块: " + module + "，可用模块: feat(专长)/race(种族)/equipment(装备)";
        }
        if (!listExportService.isAvailable(module)) {
            return "「" + module + "」清单暂不可用（" + module + "_lists.json 未加载），请改用 searchByMetadata 查询。";
        }
        if (query == null) {
            // AKN-024：query==null 与全空对象同为 NO_CONDITIONS，首次概览也要记录空书指纹，
            // 否则后续空条件 allow=true 会因无记录被多驳回一次；概览本身仍不写门禁事件。
            resolveBroadQueryAllowance(module, false, null, null);
            return listExportService.overview(module);
        }
        // F-026：参数校验先于门禁判定——非法字段/空值/非法布尔值/非法排序在门禁前返回，
        // 不产生 BLOCKED/ALLOWED 事件；放行字段不能修正非法输入。
        java.util.Set<String> unknown = listExportService.unknownFilterFields(module, query);
        if (!unknown.isEmpty()) {
            return "未知过滤字段: " + unknown + "，可用字段: " + listExportService.availableFilterFields(module);
        }
        // B4-QA-2：空串过滤值视为无效条件（静默匹配空字段会产生假命中），自纠提示
        List<String> blankFields = new ArrayList<>();
        if (query.filters() != null) {
            query.filters().forEach((k, v) -> {
                if (v == null || v.isBlank()) {
                    blankFields.add(k);
                }
            });
        }
        if (query.orFilters() != null) {
            query.orFilters().forEach((k, vs) -> {
                if (vs != null && vs.stream().anyMatch(v -> v == null || v.isBlank())) {
                    blankFields.add(k);
                }
            });
        }
        if (!blankFields.isEmpty()) {
            return "过滤值为空: " + blankFields.stream().distinct().toList()
                    + "，请提供非空过滤值或去掉该条件";
        }
        // B4-QA-1：hasPrerequisites 只接受 "true"/"false"（对齐 sortBy 校验先例），
        // 非法值不再静默落入 false 分支
        List<String> boolValues = new ArrayList<>();
        if (query.filters() != null && query.filters().containsKey("hasPrerequisites")) {
            boolValues.add(query.filters().get("hasPrerequisites"));
        }
        if (query.orFilters() != null && query.orFilters().containsKey("hasPrerequisites")) {
            List<String> vs = query.orFilters().get("hasPrerequisites");
            if (vs != null) {
                boolValues.addAll(vs);
            }
        }
        if (!boolValues.isEmpty() && boolValues.stream().anyMatch(v -> !isBooleanLiteral(v))) {
            return "非法过滤值: hasPrerequisites=" + boolValues
                    + "，可用值: [\"true\", \"false\"]（true=有前置条件，false=无前置条件）";
        }
        // AKN-025：price 排序仅装备模块开放（映射 price_gp）；其余模块保持 name/book
        List<String> sortFields = "equipment".equals(module) ? List.of("name", "book", "price") : List.of("name", "book");
        if (query.sortBy() != null && !query.sortBy().isBlank()
                && !sortFields.contains(query.sortBy())) {
            return "未知排序字段: " + query.sortBy() + "，可用值: " + sortFields;
        }
        if (query.sortOrder() != null && !query.sortOrder().isBlank()
                && !SORT_ORDERS.contains(query.sortOrder())) {
            return "未知排序方向: " + query.sortOrder() + "，可用值: " + SORT_ORDERS;
        }
        List<String> priceValues = priceFilterValues(query);
        if (priceValues.stream().anyMatch(v -> !isIntegerLiteral(v))) {
            return "非法过滤值: price_min/price_max=" + priceValues
                    + "，须为整数 gp（如 price_min=\"1000\"，仅统计有明确标价的条目）";
        }
        boolean priceQuery = "price".equals(query.sortBy()) || hasPriceRange(query);
        if (priceQuery && !listExportService.hasPriceData(module)) {
            return "「" + module + "」清单为旧版（无 price_gp 字段），暂不支持 price 排序/价格区间过滤；"
                    + "请改用 name/book 排序，或重新导出带 price_gp 的清单。";
        }
        // F-026 工具护栏：listEntries 无业务条件且未放行时保持现有统计概览（轻量概览不记
        // 门禁事件）；仅书条件未放行返回护栏建议；放行后执行（含无条件分页）。
        // AKN-024：放行声明还需通过会话级 module+book 指纹校验；不一致退回收窄建议。
        Reason gateReason = BroadQueryGuard.listEntriesReason(query);
        if (gateReason != null) {
            AllowanceDecision decision = resolveBroadQueryAllowance(module, query.isBroadQueryAllowed(),
                    query.filters(), query.orFilters());
            if (!decision.allowed()) {
                if (gateReason == Reason.NO_CONDITIONS) {
                    // 普通未声明的概览保持轻量不写事件；但明确的指纹不匹配驳回必须留痕。
                    if (decision.fingerprintMismatch()) {
                        recordGateBlocked("listEntries", module, Reason.FINGERPRINT_MISMATCH, query);
                    }
                    return listExportService.overview(module);
                }
                recordGateBlocked("listEntries", module,
                        decision.fingerprintMismatch() ? Reason.FINGERPRINT_MISMATCH : gateReason, query);
                return BroadQueryGuard.blockedMessage("listEntries", module, gateReason,
                        listExportService.availableFilterFields(module));
            }
            recordGateAllowed("listEntries", module, gateReason, query);
        }
        int limit = query.limit() == null ? listExportsDefaultLimit : query.limit();
        String clampNote = "";
        if (limit > listExportsMaxLimit) {
            limit = listExportsMaxLimit;
            clampNote = "（limit 超出上限，已钳制为 " + listExportsMaxLimit + "）\n";
        } else if (limit < 1) {
            limit = 1;
            clampNote = "（limit 小于 1，已钳制为 1）\n";
        }
        // B4-QA-3：offset 为负钳制为 0 并注明（与 limit 钳制注记风格一致）
        int offset = query.offset() == null ? 0 : query.offset();
        if (offset < 0) {
            offset = 0;
            clampNote += "（offset 为负，已钳制为 0）\n";
        }
        ListExportService.EntryPage page = listExportService.search(module, query, limit, offset);
        if (page.entries().isEmpty()) {
            if (page.total() > 0) {
                return "无命中：共 " + page.total() + " 条命中，但 offset=" + offset
                        + " 越界（limit=" + limit + "），请减小 offset 翻页。";
            }
            return "无命中。建议：放宽过滤条件（如去掉 book）或改用 vectorSearch；确认数据缺失再 reportDataGap";
        }
        return clampNote + formatEntryList(module, page, offset, limit);
    }

    /** hasPrerequisites 合法值："true"/"false"（大小写不敏感）；其余值（"yes"/"1"/"是" 等）非法 */
    private static boolean isBooleanLiteral(String value) {
        return "true".equalsIgnoreCase(value) || "false".equalsIgnoreCase(value);
    }

    /** 价格区间过滤值（filters/orFilters 中的 price_min/price_max），工具层先行校验为整数 gp */
    private static List<String> priceFilterValues(ListEntriesQuery query) {
        List<String> values = new ArrayList<>();
        if (query.filters() != null) {
            for (String field : List.of("price_min", "price_max")) {
                String value = query.filters().get(field);
                if (value != null) {
                    values.add(value);
                }
            }
        }
        if (query.orFilters() != null) {
            for (String field : List.of("price_min", "price_max")) {
                List<String> group = query.orFilters().get(field);
                if (group != null) {
                    values.addAll(group);
                }
            }
        }
        return values;
    }

    private static boolean hasPriceRange(ListEntriesQuery query) {
        return query.filters() != null && (query.filters().containsKey("price_min")
                || query.filters().containsKey("price_max"))
                || query.orFilters() != null && (query.orFilters().containsKey("price_min")
                || query.orFilters().containsKey("price_max"));
    }

    private static boolean isIntegerLiteral(String value) {
        if (value == null || value.isBlank()) {
            return false;
        }
        try {
            Long.parseLong(value.trim());
            return true;
        } catch (NumberFormatException e) {
            return false;
        }
    }

    /**
     * AKN-024 宽查询放行判定：声明放行后还需通过会话级 module+book 指纹校验。
     *
     * 无请求上下文或指纹机制未装配（单测/管理直调）时沿用 F-026 的声明式行为；
     * 有会话上下文时由 {@link BroadQueryAllowanceRegistry#authorize} 在会话 key 上
     * 原子完成「校验 + 确认/记录建议」：
     *  - 已由真实用户轮次确认的指纹，任何请求（含 regenerate）都可沿用，且不会被
     *    同轮/后续的换模块探测清掉（同条件翻页不受影响）；
     *  - 各指纹的待确认建议分别保存，只接受后续用户轮次（普通 ask 且 requestId 不同）
     *    确认，同轮内多次不同指纹试探不会互相覆盖；regenerate 不能把建议升级为放行；
     *  - 旧请求（requestSequence 更小）的过期判定不会覆盖更新状态；
     *  - 拒绝时记录/更新该指纹的待确认建议并退回收窄建议。
     *
     * 确认资格只来自工具层真实登记的指纹：PromptBuilder 要求首次宽查询以
     * allowBroadQuery=false 调用对应工具登记 module+book；仅回答文本里的建议不产生
     * 任何放行资格。
     */
    private AllowanceDecision resolveBroadQueryAllowance(String module, boolean declaredAllowed,
            Map<String, String> filters, Map<String, List<String>> orFilters) {
        BroadQueryAllowanceRegistry.Fingerprint fingerprint =
                BroadQueryAllowanceRegistry.Fingerprint.of(module, filters, orFilters);
        Optional<ToolCallTracker.RequestContext> context = toolCallTracker == null
                ? Optional.empty()
                : toolCallTracker.currentContext();
        String conversationId = context.map(ToolCallTracker.RequestContext::conversationId).orElse(null);
        String requestId = context.map(ToolCallTracker.RequestContext::requestId).orElse(null);
        boolean confirmationEligible = context
                .map(ToolCallTracker.RequestContext::confirmationEligible)
                .orElse(false);
        long requestSequence = context.map(ToolCallTracker.RequestContext::requestSequence).orElse(0L);
        if (conversationId == null || broadQueryAllowanceRegistry == null) {
            return new AllowanceDecision(declaredAllowed, false);
        }
        boolean allowed = broadQueryAllowanceRegistry.authorize(conversationId, fingerprint,
                requestId, declaredAllowed, confirmationEligible, requestSequence);
        return new AllowanceDecision(allowed, !allowed && declaredAllowed);
    }

    /**
     * 放行判定结果：allowed=是否执行；fingerprintMismatch=声明放行但被驳回
     * （指纹不一致、同轮重试，或 regenerate 试图确认待确认建议）。
     */
    private record AllowanceDecision(boolean allowed, boolean fingerprintMismatch) {
    }

    /** F-026：记录 BLOCKED 事件（尽力写入；recorder 未装配/无请求上下文/写失败均不影响结果） */
    private void recordGateBlocked(String toolName, String module, Reason reason, Object query) {
        if (queryGateEventRecorder != null) {
            queryGateEventRecorder.recordBlocked(toolName, module, reason, query);
        }
    }

    /** F-026：记录 ALLOWED 事件（同一逻辑查询的每页各记一行） */
    private void recordGateAllowed(String toolName, String module, Reason reason, Object query) {
        if (queryGateEventRecorder != null) {
            queryGateEventRecorder.recordAllowed(toolName, module, reason, query);
        }
    }

    /** listEntries 命中列表：逐行紧凑格式 + 截断护栏（截断行不挂 [#N]）+ 批量溯源点查 */
    private String formatEntryList(String module, ListExportService.EntryPage page, int offset, int limit) {
        boolean detailed = page.total() <= 20;
        // 第一遍：按字符预算截断出实际展示的行（截断行不挂来源编号，对齐 formatCompact 惯例）
        List<ListExportService.ListEntry> shown = new ArrayList<>();
        int budget = metadataResultChars;
        for (ListExportService.ListEntry entry : page.entries()) {
            String line = listExportService.entryLine(module, offset + 1 + shown.size(), entry, detailed);
            if (line.length() + 1 > budget) {
                break;
            }
            budget -= line.length() + 1;
            shown.add(entry);
        }
        // 第二遍：只对展示的条目批量点查溯源（未命中服务内降级合成，[#N] 不缺席）
        List<Document> docs = listExportService.provenanceDocuments(module, shown);
        SourceCollector.AddResult added = collector.addWithLimit(docs);
        StringBuilder sb = new StringBuilder();
        int displayed = 0;
        for (int j = 0; j < shown.size(); j++) {
            Integer id = sourceNumber(added, j);
            if (id == null) {
                continue;   // 护栏拒绝的条目不进入工具输出
            }
            sb.append(listExportService.entryLine(module, offset + 1 + j, shown.get(j), detailed))
                    .append(" [#").append(id).append(']').append('\n');
            displayed++;
        }
        if (displayed == 0 && !shown.isEmpty() && added.truncated()) {
            return "本页 " + shown.size() + " 条命中均因请求级来源护栏未保留，未展示任何行、"
                    + "也不分配来源编号。请收窄过滤条件或减少 limit 后重试；"
                    + "这不是数据缺失，不要因此 reportDataGap。";
        }
        if (displayed < page.total()) {
            sb.append("…（结果过多，仅展示前 ").append(displayed).append(" 条 / 共 ")
                    .append(page.total()).append(" 条命中，请用 offset 翻页（当前 offset=")
                    .append(offset).append("，limit=").append(limit)
                    .append("）或收窄过滤条件）");
        }
        return sb.append(guardHint(added)).toString();
    }

    /** J6/SP8d：EntryResolver 关闭时 resolveEntry/getEntryLinks/keywordSearch 的固定提示 */
    private static final String ENTRY_RESOLVER_DISABLED_HINT =
            "条目名解析索引未启用（pf.search.entry-resolver-enabled=false），请改用 vectorSearch/searchByMetadata 检索。";

    /** resolveEntry 公共路径：开关/空名/多义/唯一命中（命中挂溯源） */
    private String resolveEntryInternal(String name, String module) {
        if (!entryResolver.isEnabled()) {
            return ENTRY_RESOLVER_DISABLED_HINT;
        }
        if (name == null || name.isBlank()) {
            return "请提供条目名（name），如 resolveEntry(name=\"火球术\"）";
        }
        List<EntryResolver.EntryRef> candidates = resolveCandidates(name, module);
        if (candidates.isEmpty()) {
            return "未找到条目「" + name + "」。建议：改用 vectorSearch 语义检索；"
                    + "确认数据缺失再 reportDataGap（可选带 module 参数收窄候选）";
        }
        if (candidates.size() > 1) {
            return formatAmbiguous(name, candidates);
        }
        EntryResolver.EntryRef ref = candidates.get(0);
        Document doc = searchService.getByChunkId(ref.module(), ref.chunkId());
        Integer sourceId = null;
        if (doc != null) {
            SourceCollector.AddResult added = collector.addWithLimit(List.of(doc));
            if (singleSourceRejected(added)) {
                // 被护栏拒绝的候选不得输出条目元数据行，避免模型据未溯源的命中作答
                return singleSourceRejectedHint("条目「" + ref.title() + "」");
            }
            sourceId = sourceNumber(added, 0);
        }
        StringBuilder sb = new StringBuilder();
        sb.append("条目: ").append(ref.title()).append(" [模块:").append(ref.module()).append(']');
        if (ref.bookNameCn() != null && !ref.bookNameCn().isBlank()) {
            sb.append(" 来源:").append(ref.bookNameCn());
            if (ref.bookAbbreviation() != null && !ref.bookAbbreviation().isBlank()) {
                sb.append('(').append(ref.bookAbbreviation()).append(')');
            }
        }
        sb.append("\nchunk_id: ").append(ref.chunkId());
        if (doc != null) {
            if (sourceId != null) {
                sb.append("\n\n来源编号 [#").append(sourceId).append(']');
            }
        } else {
            sb.append("\n（向量库中未检索到该 chunk 原文，可用 getEntryLinks 查关联条目）");
        }
        return sb.toString();
    }

    /** 名归一解析候选（module 非空时收窄） */
    private List<EntryResolver.EntryRef> resolveCandidates(String name, String module) {
        if (module != null && !module.isBlank() && !VALID_MODULES.contains(module)) {
            return List.of();
        }
        return entryResolver.resolve(name, module);
    }

    /** 多义候选清单：title/module/书/chunk_id，提示带 module 消歧 */
    private String formatAmbiguous(String name, List<EntryResolver.EntryRef> candidates) {
        StringBuilder sb = new StringBuilder("条目「").append(name).append("」有 ")
                .append(candidates.size()).append(" 个候选：\n");
        int i = 1;
        for (EntryResolver.EntryRef ref : candidates) {
            sb.append(i++).append(". [模块:").append(ref.module()).append("] ").append(ref.title());
            if (ref.bookAbbreviation() != null && !ref.bookAbbreviation().isBlank()) {
                sb.append(" | 来源:").append(ref.bookAbbreviation());
            }
            sb.append(" | chunk_id:").append(ref.chunkId()).append('\n');
        }
        sb.append("请用 module 参数（如 getEntryLinks(name=\"…\", module=\"spell\")）收窄后重试。");
        return sb.toString();
    }

    /** 三层链接格式化：条目自身 + 基础/变体 + 引用它的 + 它引用的，逐条挂来源编号 */
    private String formatEntryLinks(EntryResolver.EntryRef ref) {
        EntryResolver.EntryLinks links = entryResolver.linksOf(ref);
        // 汇总需挂溯源的条目：自身 + 基础 + 变体 + 两层链接目标，逐条经向量库点查交 SourceCollector
        List<EntryResolver.EntryRef> toFetch = new ArrayList<>();
        toFetch.add(links.entry());
        if (links.base() != null) {
            toFetch.add(links.base());
        }
        toFetch.addAll(links.variants());
        links.referencedBy().forEach(link -> toFetch.add(link.target()));
        links.references().forEach(link -> toFetch.add(link.target()));
        List<Document> docs = new ArrayList<>();
        List<EntryResolver.EntryRef> fetchedRefs = new ArrayList<>();
        for (EntryResolver.EntryRef target : toFetch) {
            Document doc = searchService.getByChunkId(target.module(), target.chunkId());
            if (doc != null) {
                docs.add(doc);
                fetchedRefs.add(target);
            }
        }
        SourceCollector.AddResult added = collector.addWithLimit(docs);
        Map<String, Integer> idByChunkKey = new HashMap<>();
        Set<String> droppedKeys = new HashSet<>();
        for (int i = 0; i < docs.size(); i++) {
            Integer id = sourceNumber(added, i);
            String key = refKey(fetchedRefs.get(i));
            if (id != null) {
                idByChunkKey.put(key, id);
            } else {
                droppedKeys.add(key);
            }
        }
        if (!docs.isEmpty() && idByChunkKey.isEmpty()) {
            // 全部来源均被拒（重复键会拿到既有编号，不计入拒绝）
            return singleSourceRejectedHint("条目「" + ref.title() + "」及其引用链");
        }
        StringBuilder sb = new StringBuilder();
        sb.append("条目: ").append(ref.title()).append(" [模块:").append(ref.module()).append(']');
        if (ref.bookNameCn() != null && !ref.bookNameCn().isBlank()) {
            sb.append(" 来源:").append(ref.bookNameCn());
            if (ref.bookAbbreviation() != null && !ref.bookAbbreviation().isBlank()) {
                sb.append('(').append(ref.bookAbbreviation()).append(')');
            }
        }
        sb.append("\nchunk_id: ").append(ref.chunkId()).append(sourceTag(idByChunkKey, ref)).append('\n');
        if (links.base() != null && !droppedKeys.contains(refKey(links.base()))) {
            sb.append("基础法术: ").append(refLine(links.base(), idByChunkKey)).append('\n');
        }
        appendRefSection(sb, "变体", keepAccepted(links.variants(), droppedKeys), idByChunkKey);
        appendLinkSection(sb, "引用它的", keepAcceptedLinks(links.referencedBy(), droppedKeys), idByChunkKey);
        appendLinkSection(sb, "它引用的", keepAcceptedLinks(links.references(), droppedKeys), idByChunkKey);
        if (links.base() == null && links.variants().isEmpty()
                && links.referencedBy().isEmpty() && links.references().isEmpty()) {
            sb.append("（该条目暂无已结构化的引用关系：Layer 0 仅覆盖神话变体/专长前置/职业环级表，"
                    + "文本内的「见 XX」引用不在覆盖范围）");
        } else {
            sb.append("（只展示能精确解析的引用；可用 getEntryById 按 chunk_id 取原文）");
        }
        return sb.append(guardHint(added)).toString();
    }

    /** 引用它的/它引用的 段：带关系说明的链接行，超上限截断 */
    private void appendLinkSection(StringBuilder sb, String title, List<EntryResolver.EntryLink> links,
            Map<String, Integer> idByChunkKey) {
        if (links.isEmpty()) {
            return;
        }
        sb.append(title).append(':');
        appendCapped(sb, links.size(), i -> "  \n- " + linkLine(links.get(i), idByChunkKey));
        sb.append('\n');
    }

    /** 基础/变体段（无关系说明的纯条目列表），超上限截断 */
    private void appendRefSection(StringBuilder sb, String title, List<EntryResolver.EntryRef> refs,
            Map<String, Integer> idByChunkKey) {
        if (refs.isEmpty()) {
            return;
        }
        sb.append(title).append(':');
        appendCapped(sb, refs.size(), i -> "  \n- " + refLine(refs.get(i), idByChunkKey));
        sb.append('\n');
    }

    /** 段内截断公共逻辑：只输出前 entryLinksMaxPerSection 条，超出附计数提示 */
    private void appendCapped(StringBuilder sb, int total, java.util.function.IntFunction<String> lineOf) {
        int shown = Math.min(total, entryLinksMaxPerSection);
        for (int i = 0; i < shown; i++) {
            sb.append(lineOf.apply(i));
        }
        if (total > shown) {
            sb.append("  \n- …（共 ").append(total).append(" 条，仅展示前 ").append(shown).append(" 条）");
        }
    }

    /** 链接行：title [module] 书 chunk_id 关系说明 [#N] */
    private String linkLine(EntryResolver.EntryLink link, Map<String, Integer> idByChunkKey) {
        EntryResolver.EntryRef target = link.target();
        String line = refLine(target, idByChunkKey);
        return link.note() == null || link.note().isBlank() ? line : line + "（" + link.note() + "）";
    }

    /** 条目行：title [module] 书 chunk_id [#N] */
    private String refLine(EntryResolver.EntryRef ref, Map<String, Integer> idByChunkKey) {
        StringBuilder sb = new StringBuilder(ref.title())
                .append(" [模块:").append(ref.module()).append(']');
        if (ref.bookAbbreviation() != null && !ref.bookAbbreviation().isBlank()) {
            sb.append(" 来源:").append(ref.bookAbbreviation());
        }
        sb.append(" chunk_id:").append(ref.chunkId()).append(sourceTag(idByChunkKey, ref));
        return sb.toString();
    }

    /** 来源编号标注：命中溯源返回 [#N]，未命中不标注（编号不越界，SP4 D2 惯例） */
    private String sourceTag(Map<String, Integer> idByChunkKey, EntryResolver.EntryRef ref) {
        Integer id = idByChunkKey.get(ref.module() + "|" + ref.chunkId());
        return id == null ? "" : " [#" + id + "]";
    }

    /** 枚举式结果的紧凑摘要：标题 + 学派/子学派 + 来源 + 各职业环数 + chunk_id + 来源编号。
     *  结果字符超 metadata-result-chars 时截断，并在"还有更多未展示结果"时附分页元数据提示
     *  （真实总数 / has_more / 续取 offset），防海量结果淹没 LLM（F-002 复盘：
     *  {book:"CRB"} 宽过滤单次返回 26K 字符导致工具循环超限）。截断只影响喂给 LLM 的字符串，
     *  完整 Document 已在调用方交 SourceCollector，溯源不受影响。
     *  SP4 D2：每条紧凑行行尾标注来源编号 [#N]（编号 = collector.add 返回，按 doc 一一对应）；
     *  被截断未展示的条目不标注——文本只出现 ≤ sources 数的编号，天然不越界。
     *  J1/J2：行内补 chunk_id 供 getEntryById 点查；crossModule 时行首补模块名。
     *  AKN015-T1：检索上限（enumerationTopK）触达时不再输出假总数，改用诚实版提示；
     *  上限内的翻页照常给 has_more/next_offset（next_offset 不会越过上限）。
     *  AKN015-T2：shown==0（首条即超字符上限）时不给续取指引，改用 getEntryById 取完整原文；
     *  AKN015-T9：capped 话术按"是否还有未展示条目"唯一决定——有则只续取，无则只劝收窄。 */
    private String formatCompact(List<Document> docs, SourceCollector.AddResult added,
            boolean crossModule, SearchService.PagedResult paged, String module) {
        int totalCount = paged.totalCount();
        int offset = paged.offset();
        StringBuilder sb = new StringBuilder();
        int index = 0;
        int shown = 0;
        int acceptedInPage = 0;
        Document firstAccepted = null;
        for (Document doc : docs) {
            Integer id = sourceNumber(added, index++);
            if (id == null) {
                continue;   // 护栏拒绝的条目不进入工具输出，也不挂编号
            }
            acceptedInPage++;
            if (firstAccepted == null) {
                firstAccepted = doc;
            }
            String line = (shown + 1) + ". "
                    + (crossModule ? "[模块:" + value(doc, "pf_module") + "] " : "")
                    + value(doc, "title")
                    + " | 学派:" + value(doc, "school")
                    + " | 子学派:" + value(doc, "subschool")
                    + " | 来源:" + value(doc, "book_abbreviation")
                    + " | 环位:" + spellLevels(doc)
                    + " | chunk_id:" + value(doc, "chunk_id")
                    + " [#" + id + "]\n";
            if (sb.length() + line.length() > metadataResultChars) {
                break;
            }
            sb.append(line);
            shown++;
        }
        boolean truncatedInPage = shown < acceptedInPage;
        boolean moreResults = paged.hasMore();
        if (shown == 0) {
            if (firstAccepted == null) {
                // 整页都被请求级护栏拒绝：不给续取/假总数，只说明裁剪与收窄方向
                return "…（本页 " + docs.size() + " 条命中均因请求级来源护栏未保留，未展示也未分配编号；"
                        + "请收窄过滤条件或减少模块范围后重试，这不是数据缺失）";
            }
            // 首条即超出字符预算：续取 offset 不会前进，绝不能给翻页指引（AKN015-T2）
            String targetModule = "all".equals(module) ? value(firstAccepted, "pf_module") : module;
            String firstChunkId = value(firstAccepted, "chunk_id");
            sb.append("…（本页从第 ").append(offset + 1)
                    .append(" 条起的内容超出单次展示字符上限，本页无条目可展示；");
            if (!firstChunkId.isBlank() && !targetModule.isBlank()) {
                sb.append("请使用 getEntryById(module=\"").append(targetModule)
                        .append("\", chunkId=\"").append(firstChunkId).append("\") 获取完整原文，");
            } else {
                sb.append("请使用 getEntryById 按条目 ID（chunk_id）获取完整原文，");
            }
            sb.append("或收窄过滤条件后重试，不要重复请求同一页");
            if (paged.capped()) {
                // AKN-021：shown==0 分支不能吞掉 capped 信息；只说明上限，不给假总数。
                sb.append("；另，");
                if (crossModule) {
                    sb.append("至少一个模块已达单库检索上限 ");
                } else {
                    sb.append("本次检索已达单库上限 ");
                }
                sb.append(paged.cap()).append(" 条（实际命中可能更多），请收窄过滤条件");
            }
            sb.append("）");
            return sb.toString();
        }
        if (!truncatedInPage && !moreResults && !paged.capped()) {
            return sb.toString();
        }
        if (paged.capped()) {
            // totalCount 只是单库上限截断后的合并条数，绝不能当真实总数输出（AKN015-T1）
            sb.append("…（");
            if (crossModule) {
                sb.append("至少一个模块已达单库检索上限 ");
            } else {
                sb.append("已达检索上限 ");
            }
            sb.append(paged.cap())
                    .append(" 条（实际命中可能更多），本次返回第 ").append(offset + 1)
                    .append("~").append(offset + shown).append(" 条");
            // 话术按"是否还有未展示条目"唯一决定：有则只给续取，无则只给收窄（AKN015-T9）
            if (truncatedInPage || moreResults) {
                sb.append("，has_more=true；续取：保持其他参数不变，query.offset=")
                        .append(offset + shown);
            } else if (crossModule) {
                sb.append("；当前跨模块合并结果已全部展示，请收窄过滤条件以获取触顶模块的后续结果");
            } else {
                sb.append("；本工具最多只能取前 ").append(paged.cap())
                        .append(" 条，请收窄过滤条件（如 book/level/title）后继续");
            }
            sb.append("）");
            return sb.toString();
        }
        // 截断提示必须带分页元数据（业界 MCP 分页惯例）：真实总数 + has_more + 续取 offset，
        // 否则模型在"总数未知 + 无下一步指引"下会编造补齐（AKN-015）
        sb.append("…（共 ").append(totalCount)
                .append(" 条，本次返回第 ").append(offset + 1)
                .append("~").append(offset + shown)
                .append(" 条，has_more=true；续取：保持其他参数不变，query.offset=")
                .append(offset + shown).append("）");
        return sb.toString();
    }

    /** 汇总 metadata 中 spell_level_<职业> 扁平键 → "女巫1环、德鲁伊1环"；无则显示横线 */
    private String spellLevels(Document doc) {
        List<String> parts = doc.getMetadata().entrySet().stream()
                .filter(entry -> entry.getKey().startsWith("spell_level_"))
                .sorted(Map.Entry.comparingByKey())
                .map(entry -> entry.getKey().substring("spell_level_".length()) + entry.getValue() + "环")
                .toList();
        return parts.isEmpty() ? "—" : String.join("、", parts);
    }

    /** 语义检索片段的正文截断格式；SP4 D2：每个片段分隔行标注来源编号 [#N]（按 doc 一一对应） */
    private String formatFragments(List<Document> docs, SourceCollector.AddResult added) {
        StringBuilder sb = new StringBuilder();
        int shown = 0;
        for (int i = 0; i < docs.size(); i++) {
            Integer id = sourceNumber(added, i);
            if (id == null) {
                continue;   // 护栏拒绝的片段不进入工具输出
            }
            Document doc = docs.get(i);
            shown++;
            sb.append("[#").append(id).append("] --- 片段 ").append(shown).append(" ---\n");
            sb.append("标题: ").append(value(doc, "title")).append('\n');
            sb.append("chunk_id: ").append(value(doc, "chunk_id")).append('\n');
            sb.append("来源: ").append(value(doc, "book_name_cn"))
                    .append(" (").append(value(doc, "book_abbreviation")).append(")\n");
            // KN207：先剥展示层噪声行再截断，避免截断后残留「未整理 →」半行
            sb.append("内容: ")
                    .append(truncate(TextSanitizer.stripInternalSourceLine(doc.getText()), vectorResultChars))
                    .append('\n');
        }
        return sb.toString();
    }

    /** query 是否带 level 的范围/OR 条件（spell 组合键须配合 className 的判定用） */
    private boolean queryHasLevelCondition(MetadataSearchQuery query) {
        boolean gteLte = (query.getGte() != null && query.getGte().containsKey("level"))
                || (query.getLte() != null && query.getLte().containsKey("level"));
        boolean or = query.getOrFilters() != null && query.getOrFilters().containsKey("level");
        return gteLte || or;
    }

    /** 模块可用字段清单；"all" 时取八模块字段并集（保序去重） */
    private List<String> availableFields(String module) {
        if (!"all".equals(module)) {
            return filterTranslator.availableFields(module);
        }
        List<String> union = new ArrayList<>();
        for (String m : VALID_MODULES) {
            for (String field : filterTranslator.availableFields(m)) {
                if (!union.contains(field)) {
                    union.add(field);
                }
            }
        }
        return union;
    }

    /** 缺口记录单行紧凑格式：「时间 | question | reason」，每行 ≤120 字符截断 */
    private String formatGapLine(DataGapRecorder.GapEntry gap) {
        String question = gap.question().length() > 60 ? gap.question().substring(0, 60) + "…" : gap.question();
        String reason = gap.reason().length() > 40 ? gap.reason().substring(0, 40) + "…" : gap.reason();
        String line = gap.timestamp() + " | " + question + " | " + reason;
        return line.length() > 120 ? line.substring(0, 120) + "…" : line;
    }

    /**
     * 入参第 index 条对应的来源编号；被请求级护栏拒绝或未收集时返回 null。
     * 编号 N ↔ SourceCollector.drain() 第 N 条（1-based），调用方只能给非 null 位置标注 [#N]。
     */
    private Integer sourceNumber(SourceCollector.AddResult added, int index) {
        if (added == null || added.idsByInput() == null || index < 0 || index >= added.idsByInput().size()) {
            return null;
        }
        return added.idsByInput().get(index);
    }

    /**
     * 请求级来源护栏提示（F-016）：仅在本次调用有来源被拒时追加。
     * 护栏截断不是数据缺口——不触发 reportDataGap，只提示收窄条件/减少范围。
     */
    private String guardHint(SourceCollector.AddResult added) {
        if (added == null || !added.truncated()) {
            return "";
        }
        StringBuilder sb = new StringBuilder("\n\n（请求级来源护栏：本请求已保留 ")
                .append(added.retainedTotal()).append(" 条来源，本次因");
        if (added.droppedByCount() > 0) {
            sb.append("数量上限");
        }
        if (added.droppedByCount() > 0 && added.droppedByBytes() > 0) {
            sb.append('与');
        }
        if (added.droppedByBytes() > 0) {
            sb.append("正文体积上限（pf.search.max-sources-bytes）");
        }
        sb.append("丢弃 ").append(added.droppedCount())
                .append(" 条；被丢弃条目不展示、不分配来源编号。请收窄过滤条件或减少模块范围后继续，")
                .append("这不是数据缺失，不要因此 reportDataGap）");
        return sb.toString();
    }

    /** AKN-023：点查结果——命中 Document 或可读未命中错误，二者其一非空 */
    private record EntryLoadResult(Document doc, String error) {
    }

    /** 第一阶段：只查原文，不触碰 SourceCollector（未确定展示的条目不得提前写入来源） */
    private EntryLoadResult loadEntry(String module, String chunkId) {
        Document doc = searchService.getByChunkId(module, chunkId);
        if (doc == null) {
            return new EntryLoadResult(null,
                    "该 (module=" + module + ", chunkId=" + chunkId + ") 无匹配条目，chunk_id 需来自检索结果");
        }
        return new EntryLoadResult(doc, null);
    }

    /**
     * 第二阶段：确定该条可展示后收集来源并格式化。
     * 错误原样返回；护栏拒绝返回明确提示（此时 addWithLimit 未收下该条，不污染来源）。
     */
    private String collectAndFormatEntry(EntryLoadResult load, String module, String chunkId) {
        if (load.error() != null) {
            return load.error();
        }
        Document doc = load.doc();
        SourceCollector.AddResult added = collector.addWithLimit(List.of(doc));
        if (added.truncated()) {
            return sourceGuardMessage(doc, chunkId);
        }
        return formatEntry(doc, module, chunkId, sourceNumber(added, 0));
    }

    /** 单条/批量共用的原始格式（标题/来源/模块/chunk_id/正文/截断提示[/[#N]]） */
    private String formatEntry(Document doc, String module, String chunkId, Integer sourceId) {
        String text = TextSanitizer.stripInternalSourceLine(doc.getText());
        StringBuilder sb = new StringBuilder();
        sb.append("标题: ").append(value(doc, "title")).append('\n');
        sb.append("来源: ").append(value(doc, "book_name_cn"))
                .append(" (").append(value(doc, "book_abbreviation")).append(")\n");
        sb.append("模块: ").append(module).append('\n');
        sb.append("chunk_id: ").append(chunkId).append('\n');
        sb.append("正文:\n");
        if (text.length() > entryResultChars) {
            sb.append(text, 0, entryResultChars).append('…').append('\n');
            sb.append("（条目过长已截断到 ").append(entryResultChars)
                    .append(" 字符，可用 vectorSearch 定位子片段）");
        } else {
            sb.append(text);
        }
        if (sourceId != null) {
            sb.append("\n\n来源编号 [#").append(sourceId).append(']');
        }
        return sb.toString();
    }

    /** 请求级来源护栏拒绝单条时的明确提示（保留原“体积上限”短语，兼容既有断言） */
    private String sourceGuardMessage(Document doc, String chunkId) {
        return "条目「" + value(doc, "title") + "」(chunk_id=" + chunkId + ") 的正文超出本请求"
                + "来源体积上限（pf.search.max-sources-bytes）或来源数量上限"
                + "（pf.search.max-sources-per-request），未返回正文、也未分配来源编号。"
                + "请改用 vectorSearch 定位该条目的子片段，或在新请求中单独点查；"
                + "这是请求级来源护栏截断，不是数据缺失，不要因此 reportDataGap。";
    }

    /**
     * 批量预算估算：错误取文案长度；doc 会被来源护栏拒绝时只按护栏提示估算；
     * 可收下时按正常格式 + 来源编号预留估算。
     */
    private int estimatedEntryChars(EntryLoadResult load, String module, String chunkId) {
        if (load.error() != null) {
            return load.error().length();
        }
        Document doc = load.doc();
        if (!collector.canRetain(doc)) {
            return sourceGuardMessage(doc, chunkId).length();
        }
        return formatEntry(doc, module, chunkId, null).length() + SOURCE_ID_RESERVE_CHARS;
    }

    /** 批量超预算提示：列出全部本次未返回 ID，提示缩小批量，不静默丢弃 */
    private String batchOverflowHint(List<String> remainingIds) {
        return "本次未返回以下 " + remainingIds.size() + " 条 ID（超出单次批量条数或字符预算）："
                + remainingIds + "。请缩小批量（每次最多 " + BATCH_ENTRY_MAX_IDS
                + " 条，且总正文不宜过长）后分批重试；这些条目未写入本次来源。";
    }

    /** 单条来源行（清单/成长表/表格）：仅当该条被收下时返回 "\\n\\n<label> [#N]" */
    private String singleSourceLine(SourceCollector.AddResult added, String label) {
        Integer id = sourceNumber(added, 0);
        return id == null ? "" : "\n\n" + label + " [#" + id + "]";
    }

    /** 单来源工具（清单/成长表/表格/点查）的唯一来源是否被护栏拒绝 */
    private boolean singleSourceRejected(SourceCollector.AddResult added) {
        return added != null && added.truncated() && sourceNumber(added, 0) == null;
    }

    /**
     * 单来源被拒时的统一回复：不输出正文/表格/条目元数据，只说明护栏截断与收窄方向。
     * 护栏截断不是数据缺口，不触发 reportDataGap。
     */
    private String singleSourceRejectedHint(String what) {
        return what + "的来源未能纳入本请求（请求级来源数量/体积上限已满），"
                + "已停止返回其正文/表格/条目信息。请缩小查询范围（减少条目或指定更窄条件），"
                + "或在新请求中重试；这不是数据缺失，不要因此 reportDataGap。";
    }

    /** 引用链条目键：module + chunk_id（与来源编号 map 同一把尺） */
    private static String refKey(EntryResolver.EntryRef ref) {
        return ref.module() + "|" + ref.chunkId();
    }

    /** 过滤被护栏拒绝的变体/基础条目引用 */
    private static List<EntryResolver.EntryRef> keepAccepted(List<EntryResolver.EntryRef> refs,
            Set<String> droppedKeys) {
        return refs.stream().filter(ref -> !droppedKeys.contains(refKey(ref))).toList();
    }

    /** 过滤被护栏拒绝的链接目标 */
    private static List<EntryResolver.EntryLink> keepAcceptedLinks(List<EntryResolver.EntryLink> links,
            Set<String> droppedKeys) {
        return links.stream()
                .filter(link -> !droppedKeys.contains(refKey(link.target())))
                .toList();
    }

    /** 正文截断：超长时保留前 max 字符并追加省略号 */
    private String truncate(String text, int max) {
        if (text == null) {
            return "";
        }
        if (text.length() <= max) {
            return text;
        }
        return text.substring(0, max) + "…";
    }

    /** 从 metadata 安全取值，缺失返回空串 */
    private String value(Document doc, String key) {
        Object v = doc.getMetadata().get(key);
        return v == null ? "" : v.toString();
    }
}
