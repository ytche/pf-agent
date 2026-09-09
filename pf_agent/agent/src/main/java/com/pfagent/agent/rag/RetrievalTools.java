package com.pfagent.agent.rag;

import org.springframework.ai.document.Document;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

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

    /**
     * 元数据精确过滤（枚举式），返回命中条目紧凑列表。
     * 字段名错误返回可用字段清单让 LLM 自纠；无结果返回"[]"。
     */
    @Tool(description = """
            按元数据精确过滤指定模块的规则库，返回命中条目的紧凑列表。
            模块 module: "spell"(法术) / "class"(职业特性) / "feat"(专长) / "race"(种族) /
              "trait"(背景特性) / "equipment"(装备) / "skill"(技能) / "rule"(规则)
            模块语义边界:
              - class: 职业特性/职业变体、角色升级、兼职(Multiclassing)、职业成长
                （这些在 class 模块，不在 rule）
              - rule: 战斗动作/状态效果/环境/移动等通用游戏规则
              - spell/feat/race/trait/equipment/skill: 对应具体条目
              - 拿不准模块时用 vectorSearch 的 module:"all"
            过滤条件 filters: 字段名→字段值 映射，多条件为 AND，值需精确匹配。

            法术模块可用字段:
              title(法术名) / school(学派如"咒法系") / subschool(子学派) /
              className(职业名，如"女巫") / level(环数1-9，须配合className) /
              book(来源书缩写，如 CRB)
            职业模块可用字段:
              className(职业名) / archetypeName(变体名) / featureSubtype(特性子类型，
              如 hex/patron/grand_hex) / componentType(class_overview|class_feature|
              class_archetype) / book(来源书缩写)
            其余模块(专长/种族/背景特性/装备/技能/规则)可用字段:
              title(条目名，精确匹配，如"精通擒抱") / book(来源书缩写，如 CRB) /
              componentType(条目组件类型，如 feat|feat_index、race_trait|alt_trait|
              fcb_entry、trait|trait_flaw、gear|weapon|armor|wondrous_item、
              skill|skill_task|skill_rule、rule_section|rule_table|rule_entry)

            示例: 女巫1环法术 → {module:"spell", filters:{className:"女巫", level:"1"}}
                  咒法系法术  → {module:"spell", filters:{school:"咒法系"}}
                  按名查专长  → {module:"feat", filters:{title:"精通擒抱"}}
                  专长来源CRB → {module:"feat", filters:{book:"CRB"}}
            字段名错误时返回可用字段清单。查询无结果返回空列表。
            """)
    public String searchByMetadata(
            @ToolParam(description = "数据模块: spell(法术) / class(职业特性+角色升级/兼职) / feat(专长) / race(种族) / trait(背景特性) / equipment(装备) / skill(技能) / rule(通用规则) / 拿不准模块时用 vectorSearch 的 all") String module,
            @ToolParam(description = "过滤条件: 字段名→字段值映射，多条件为 AND") Map<String, String> filters) {
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
        return formatCompact(docs, ids);
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

    /** 枚举式结果的紧凑摘要：标题 + 学派/子学派 + 来源 + 各职业环数 + 来源编号。
     *  结果字符超 metadata-result-chars 时截断并提示收窄过滤，防海量结果淹没 LLM（F-002 复盘：
     *  {book:"CRB"} 宽过滤单次返回 26K 字符导致工具循环超限）。截断只影响喂给 LLM 的字符串，
     *  完整 Document 已在调用方交 SourceCollector，溯源不受影响。
     *  SP4 D2：每条紧凑行行尾标注来源编号 [#N]（编号 = collector.add 返回，按 doc 一一对应）；
     *  被截断未展示的条目不标注——文本只出现 ≤ sources 数的编号，天然不越界。 */
    private String formatCompact(List<Document> docs, List<Integer> ids) {
        StringBuilder sb = new StringBuilder();
        int i = 1;
        int shown = 0;
        for (Document doc : docs) {
            String line = i + ". " + value(doc, "title")
                    + " | 学派:" + value(doc, "school")
                    + " | 子学派:" + value(doc, "subschool")
                    + " | 来源:" + value(doc, "book_abbreviation")
                    + " | 环位:" + spellLevels(doc)
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
            sb.append("来源: ").append(value(doc, "book_name_cn"))
                    .append(" (").append(value(doc, "book_abbreviation")).append(")\n");
            // KN207：先剥展示层噪声行再截断，避免截断后残留「未整理 →」半行
            sb.append("内容: ")
                    .append(truncate(TextSanitizer.stripInternalSourceLine(doc.getText()), vectorResultChars))
                    .append('\n');
        }
        return sb.toString();
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
