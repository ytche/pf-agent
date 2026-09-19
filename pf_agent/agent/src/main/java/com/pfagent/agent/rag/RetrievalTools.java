package com.pfagent.agent.rag;

import org.springframework.ai.document.Document;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

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
            法术模块可用字段:
              title / school / subschool / className / level(须配合 className) / book
            职业模块可用字段: className / archetypeName / featureSubtype / componentType / book / title
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
            @ToolParam(description = "过滤参数对象: filters(AND)/orFilters(OR)/gte/lte(范围)/sortBy/sortOrder/limit/offset") MetadataSearchQuery query) {
        if (module == null || (!"all".equals(module) && !VALID_MODULES.contains(module))) {
            return "未知模块: " + module + "，可用模块: spell(法术)/class(职业特性)/feat(专长)/race(种族)/trait(背景特性)/equipment(装备)/skill(技能)/rule(规则)/all(全部)";
        }
        if (query == null || !query.hasAnyCondition()) {
            return "请提供至少一个过滤条件（query 的 filters/orFilters/gte/lte 至少一个非空），不允许多条件为空的全库查询";
        }
        List<String> available = availableFields(module);
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
        if (query.getLimit() == null) {
            query.setLimit(metadataDefaultLimit);
        }
        if (query.getOffset() == null) {
            query.setOffset(0);
        }
        List<Document> docs;
        try {
            docs = searchService.searchByMetadata(module, query);
        } catch (IllegalArgumentException e) {
            // 防御：SearchService 对非法模块的兜底，正常路径（已校验）不会到这
            return e.getMessage();
        }
        if (docs.isEmpty()) {
            return "无命中。建议：减少一个过滤条件（如去掉 book）或改用 vectorSearch；确认数据缺失再 reportDataGap";
        }
        List<Integer> ids = collector.add(docs);
        return formatCompact(docs, ids, "all".equals(module));
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
        List<Integer> ids = collector.add(docs);
        return formatCompact(docs, ids, false);
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
            name: 条目中文名或别名。命中唯一时返回 module/title/来源书/chunk_id（已挂来源编号，
            可继续 getEntryById 拿原文）；多义时返回候选清单（带 module 再调一次消歧）；
            查无此名时如实告知并建议改用 vectorSearch。需要引用链（变体/前置/谁引用了它）用 getEntryLinks。
            """)
    public String resolveEntry(
            @ToolParam(description = "条目名或别名，如 火球术") String name) {
        return resolveEntryInternal(name, null);
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
        List<Integer> ids = collector.add(docs);
        Map<String, Integer> idByChunkKey = new HashMap<>();
        for (int i = 0; i < docs.size(); i++) {
            idByChunkKey.put(fetchedRefs.get(i).module() + "|" + fetchedRefs.get(i).chunkId(), ids.get(i));
        }
        StringBuilder sb = new StringBuilder();
        if (!exact.isEmpty()) {
            sb.append("存在精确同名条目（亦可用 resolveEntry 解析）：")
                    .append(exact.stream().map(EntryResolver.EntryRef::title).distinct().toList()).append('\n');
        }
        sb.append("命中 ").append(candidates.size()).append(" 个候选（按精确>前缀>子串、短名优先排序）：\n");
        int i = 1;
        for (EntryResolver.EntryRef ref : candidates) {
            sb.append(i++).append(". ").append(refLine(ref, idByChunkKey)).append('\n');
        }
        sb.append("（用 getEntryById 按 chunk_id 取原文；命中过多可用 module 参数收窄）");
        return sb.toString();
    }

    /**
     * 按 (module, chunk_id) 点查完整原文（SP8a J1）。
     * 拿到 vectorSearch/searchByMetadata 命中但需要完整原文（全文条款、表格）时使用；
     * 超长条目截断到 pf.search.entry-result-chars（默认 8000），可用 vectorSearch 定位子片段。
     */
    @Tool(description = """
            按 chunk_id 点查条目的完整原文（绕过片段截断）。当 vectorSearch/searchByMetadata
            的命中片段不够用、需要完整全文（如全文条款、表格、长条目）时使用。
            module: 数据模块（同 searchByMetadata）；chunkId: 必须来自此前工具返回结果中的
            chunk_id 字段。超长条目会截断（上限 pf.search.entry-result-chars，默认 8000），
            需要子片段时可再用 vectorSearch。
            """)
    public String getEntryById(
            @ToolParam(description = "数据模块: spell/class/feat/race/trait/equipment/skill/rule") String module,
            @ToolParam(description = "条目 chunk_id，必须来自此前检索工具返回结果的 chunk_id 字段") String chunkId) {
        if (module == null || !VALID_MODULES.contains(module)) {
            return "未知模块: " + module + "，可用模块: spell(法术)/class(职业特性)/feat(专长)/race(种族)/trait(背景特性)/equipment(装备)/skill(技能)/rule(规则)";
        }
        if (chunkId == null || chunkId.isBlank()) {
            return "请提供 chunkId（来自 vectorSearch/searchByMetadata 返回结果中的 chunk_id 字段）";
        }
        Document doc = searchService.getByChunkId(module, chunkId);
        if (doc == null) {
            return "该 (module=" + module + ", chunkId=" + chunkId + ") 无匹配条目，chunk_id 需来自检索结果";
        }
        List<Integer> ids = collector.add(List.of(doc));
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
        if (!ids.isEmpty()) {
            sb.append("\n\n来源编号 [#").append(ids.get(0)).append(']');
        }
        return sb.toString();
    }

    /**
     * 列出已报告的数据缺口（SP8a J3，只读）：调用 reportDataGap 前查重，避免重复上报。
     * 最新在前，limit 默认 pf.gaps.list-default-limit（20）、上限 100；keyword 对
     * question/reason 子串匹配（可空）；单行损坏自动跳过。
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
        List<DataGapRecorder.GapEntry> gaps = recorder.listGaps(effective, keyword);
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
        List<Integer> ids = collector.add(docs);
        return formatFragments(docs, ids);
    }

    /**
     * 数据缺口报告：全部检索手段都无法回答时记录，供后续优化。
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
        recorder.record(question, attemptedFilters, reason);
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
            """)
    public String getSpellList(
            @ToolParam(description = "职业中文名，如 法师/吟游诗人，支持常见别名") String className,
            @ToolParam(description = "法术环级 0~9；省略则返回该职业各环级条目数概览") Integer level) {
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
        List<Integer> ids = collector.add(List.of(spellListService.listPageDocument(canonical)));
        String sourceLine = ids.isEmpty() ? "" : "\n\n本清单来源 [#" + ids.get(0) + "]";
        if (level == null) {
            return spellListService.levelOverview(canonical) + sourceLine;
        }
        if (level < 0 || level > 9) {
            return "环级须在 0~9 之间（0 为戏法/祷念）。" + spellListService.levelOverview(canonical) + sourceLine;
        }
        return spellListService.formatLevel(canonical, level, metadataResultChars) + sourceLine;
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
            List<Integer> ids = collector.add(List.of(doc));
            if (!ids.isEmpty()) {
                sb.append("\n\n来源编号 [#").append(ids.get(0)).append(']');
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
        List<Integer> ids = collector.add(docs);
        Map<String, Integer> idByChunkKey = new HashMap<>();
        for (int i = 0; i < docs.size(); i++) {
            idByChunkKey.put(fetchedRefs.get(i).module() + "|" + fetchedRefs.get(i).chunkId(), ids.get(i));
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
        if (links.base() != null) {
            sb.append("基础法术: ").append(refLine(links.base(), idByChunkKey)).append('\n');
        }
        appendRefSection(sb, "变体", links.variants(), idByChunkKey);
        appendLinkSection(sb, "引用它的", links.referencedBy(), idByChunkKey);
        appendLinkSection(sb, "它引用的", links.references(), idByChunkKey);
        if (links.base() == null && links.variants().isEmpty()
                && links.referencedBy().isEmpty() && links.references().isEmpty()) {
            sb.append("（该条目暂无已结构化的引用关系：Layer 0 仅覆盖神话变体/专长前置/职业环级表，"
                    + "文本内的「见 XX」引用不在覆盖范围）");
        } else {
            sb.append("（只展示能精确解析的引用；可用 getEntryById 按 chunk_id 取原文）");
        }
        return sb.toString();
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
     *  结果字符超 metadata-result-chars 时截断并提示收窄过滤，防海量结果淹没 LLM（F-002 复盘：
     *  {book:"CRB"} 宽过滤单次返回 26K 字符导致工具循环超限）。截断只影响喂给 LLM 的字符串，
     *  完整 Document 已在调用方交 SourceCollector，溯源不受影响。
     *  SP4 D2：每条紧凑行行尾标注来源编号 [#N]（编号 = collector.add 返回，按 doc 一一对应）；
     *  被截断未展示的条目不标注——文本只出现 ≤ sources 数的编号，天然不越界。
     *  J1/J2：行内补 chunk_id 供 getEntryById 点查；crossModule 时行首补模块名。 */
    private String formatCompact(List<Document> docs, List<Integer> ids, boolean crossModule) {
        StringBuilder sb = new StringBuilder();
        int i = 1;
        int shown = 0;
        for (Document doc : docs) {
            String line = i + ". "
                    + (crossModule ? "[模块:" + value(doc, "pf_module") + "] " : "")
                    + value(doc, "title")
                    + " | 学派:" + value(doc, "school")
                    + " | 子学派:" + value(doc, "subschool")
                    + " | 来源:" + value(doc, "book_abbreviation")
                    + " | 环位:" + spellLevels(doc)
                    + " | chunk_id:" + value(doc, "chunk_id")
                    + " [#" + ids.get(i - 1) + "]\n";
            if (sb.length() + line.length() > metadataResultChars) {
                break;
            }
            sb.append(line);
            shown++;
            i++;
        }
        if (shown < docs.size()) {
            sb.append("…（结果过多，仅展示前 ").append(shown).append(" 条 / 共 ")
                    .append(docs.size()).append(" 条，请收窄过滤条件，如增加 title/level 等字段）");
        }
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
    private String formatFragments(List<Document> docs, List<Integer> ids) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < docs.size(); i++) {
            Document doc = docs.get(i);
            sb.append("[#").append(ids.get(i)).append("] --- 片段 ").append(i + 1).append(" ---\n");
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
