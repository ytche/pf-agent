package com.pfagent.agent.rag;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import com.pfagent.agent.telemetry.QueryGateEventService.Reason;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.mockito.ArgumentCaptor;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * RetrievalTools 单元测试（设计 §3）
 *
 * 覆盖三个 @Tool 的 LLM 侧行为契约：
 *  - searchByMetadata：合法 → 紧凑列表 + 收集来源；未知字段 → 返回可用字段清单
 *    （LLM 自纠）；非法模块 → 错误提示；无结果 → 空列表"[]"
 *  - vectorSearch：按模块路由语义检索，正文截断到 vector-result-chars，
 *    完整 Document 仍进 SourceCollector（v1.5 B2：截断只影响上下文体积）
 *  - reportDataGap：记录缺口 + 标记 gapReported
 *  - SP4 D2：命中结果返回文本携带来源编号 [#N]（紧凑行尾 / 片段头 / 清单末尾来源行），
 *    编号来自 collector.add 返回值（stubAddSequential 模拟递增分配）
 */
@ExtendWith(MockitoExtension.class)
class RetrievalToolsTest {

    private static final Pattern HINT_RANGE = Pattern.compile("本次返回第 (\\d+)~(\\d+) 条");
    private static final Pattern HINT_NEXT_OFFSET = Pattern.compile("query\\.offset=(\\d+)");
    private static final Pattern NUMBERED_LINE = Pattern.compile("(?m)^\\d+\\. ");

    @Mock
    private SearchService searchService;
    @Mock
    private SourceCollector collector;
    @Mock
    private DataGapRecorder recorder;
    @Mock
    private SpellListService spellListService;
    @Mock
    private ClassTableService classTableService;
    @Mock
    private QueryGateEventRecorder queryGateEventRecorder;

    /** AKN-024：会话级放行指纹 */
    private final ToolCallTracker toolCallTracker = new ToolCallTracker();
    private final BroadQueryAllowanceRegistry allowanceRegistry = new BroadQueryAllowanceRegistry();

    /** 合法字段返回紧凑列表并收集来源 */
    @Test
    void searchByMetadataValidFieldsReturnsCompactListAndCollects() {
        Document doc = spellDoc("火球术", Map.of(
                "title", "火球术",
                "school", "咒法系",
                "subschool", "创造",
                "book_abbreviation", "CRB",
                "spell_level_女巫", "1",
                "spell_level_德鲁伊", "1"));
        when(searchService.searchByMetadata(eq("spell"), anyMap())).thenReturn(List.of(doc));
        stubAddSequential();

        String result = tools(1500).searchByMetadata("spell", Map.of("className", "女巫"));

        assertThat(result).contains("火球术", "咒法系", "CRB", "女巫1环", "德鲁伊1环");
        assertThat(result).contains(" [#1]");    // SP4 D2：紧凑行行尾带来源编号
        verify(collector).add(any());
    }

    /** 未知字段返回可用字段清单、不查询 */
    @Test
    void searchByMetadataUnknownFieldsListsAvailableWithoutQuery() {
        String result = tools(1500).searchByMetadata("spell", Map.of("foo", "bar"));

        assertThat(result).contains("未知过滤字段", "className", "school");
        verifyNoInteractions(searchService);
        verifyNoInteractions(collector);
    }

    /** 非法模块返回错误提示 */
    @Test
    void searchByMetadataInvalidModuleReturnsErrorHint() {
        String result = tools(1500).searchByMetadata("monster", Map.of("className", "女巫"));

        assertThat(result).contains("未知模块", "spell");
        verifyNoInteractions(searchService);
        verifyNoInteractions(collector);
    }

    /** 无结果时返回空列表、不收集来源 */
    @Test
    void searchByMetadataNoResultsReturnsEmptyWithoutCollecting() {
        when(searchService.searchByMetadata(eq("spell"), anyMap())).thenReturn(List.of());

        String result = tools(1500).searchByMetadata("spell", Map.of("school", "咒法系"));

        assertThat(result).isEqualTo("[]");
        verifyNoInteractions(collector);
    }

    /** 结果过多时紧凑列表截断到字符上限，但完整 doc 仍进 SourceCollector（截断只影响 LLM 侧） */
    @Test
    void searchByMetadataManyResultsTruncatedToCharCapButCollectsAll() {
        List<Document> docs = new ArrayList<>();
        for (int i = 1; i <= 200; i++) {
            docs.add(spellDoc("法术" + i, Map.of("title", "法术" + i, "book_abbreviation", "CRB")));
        }
        when(searchService.searchByMetadata(eq("spell"), anyMap())).thenReturn(docs);
        stubAddSequential();

        String result = tools(1500, 200).searchByMetadata("spell", Map.of("book", "CRB"));

        assertThat(result).contains("共 200 条", "has_more=true", "query.offset=");
        assertThat(result).doesNotContain("法术200");     // 末尾条目已被截断
        assertThat(result).contains("[#1]");              // 展示条目标注编号
        assertThat(result).doesNotContain("[#200]");      // SP4 D2：被截断条目不标注 → 编号不越界
        ArgumentCaptor<List<Document>> captor = ArgumentCaptor.forClass(List.class);
        verify(collector).add(captor.capture());
        assertThat(captor.getValue()).hasSize(200);        // 溯源仍收集完整 200 条
    }

    // ---------- vectorSearch ----------

    /** 合法模块返回含截断正文的片段并收集来源 */
    @Test
    void vectorSearchValidModuleReturnsTruncatedSnippetAndCollects() {
        Document doc = spellDoc("火球术", Map.of(
                "title", "火球术",
                "book_name_cn", "核心规则书",
                "book_abbreviation", "CRB"));
        String longText = "a".repeat(300);
        Document doc2 = Document.builder().text(longText)
                .metadata(Map.of("title", "大火球", "book_abbreviation", "CRB")).build();
        when(searchService.search(eq("火球术射程"), eq("spell"))).thenReturn(List.of(doc, doc2));
        stubAddSequential();

        String result = tools(100).vectorSearch("火球术射程", "spell");

        assertThat(result).contains("--- 片段 1 ---", "标题: 火球术", "来源: 核心规则书 (CRB)");
        assertThat(result).contains("[#2] --- 片段 2");         // SP4 D2：片段头前缀编号
        assertThat(result).contains("…");                       // 超长正文已截断
        assertThat(result).doesNotContain("a".repeat(200));     // 100 字符限制生效
        verify(collector).add(any());
    }

    /** KN207：正文含仓库内部整理路径行时，片段内容剥离该行后再截断展示 */
    @Test
    void vectorSearchFragmentStripsInternalSourceLine() {
        Document doc = Document.builder()
                .text("> 来源：亡灵杀手手册（Undead Slayer's Handbook），页码见原书，未整理 → 亡灵杀手手册 → 法术\n生效条件正文")
                .metadata(Map.of("title", "亡灵杀手", "book_name_cn", "亡灵杀手手册", "book_abbreviation", "USH"))
                .build();
        when(searchService.search(eq("亡灵杀手特性"), eq("spell"))).thenReturn(List.of(doc));
        stubAddSequential();

        String result = tools(1500).vectorSearch("亡灵杀手特性", "spell");

        assertThat(result).doesNotContain("未整理 →");
        assertThat(result).contains("生效条件正文");   // 上下文保留
        assertThat(result).contains("来源: 亡灵杀手手册 (USH)");
        assertThat(result).contains("[#1]");           // SP4 D2：片段头编号
        verify(collector).add(any());
    }

    /** 非法模块返回错误提示 */
    @Test
    void vectorSearchInvalidModuleReturnsErrorHint() {
        String result = tools(1500).vectorSearch("火球术射程", "monster");

        assertThat(result).contains("未知模块");
        verifyNoInteractions(searchService);
        verifyNoInteractions(collector);
    }

    /** feat 模块按模块路由检索 */
    @Test
    void vectorSearchFeatModuleRoutesByModule() {
        Document doc = Document.builder().text("猛力攻击先决条件")
                .metadata(Map.of("title", "猛力攻击", "book_name_cn", "核心规则书", "book_abbreviation", "CRB"))
                .build();
        when(searchService.search(eq("猛力攻击先决条件"), eq("feat"))).thenReturn(List.of(doc));
        stubAddSequential();

        String result = tools(1500).vectorSearch("猛力攻击先决条件", "feat");

        assertThat(result).contains("猛力攻击", "CRB");
        verify(searchService).search(eq("猛力攻击先决条件"), eq("feat"));
        verify(collector).add(any());
    }

    /** feat 模块过滤检索并收集来源 */
    @Test
    void searchByMetadataFeatModuleFiltersAndCollects() {
        Document doc = spellDoc("猛力攻击", Map.of(
                "title", "猛力攻击",
                "book_abbreviation", "CRB",
                "component_type", "feat"));
        when(searchService.searchByMetadata(eq("feat"), anyMap())).thenReturn(List.of(doc));
        stubAddSequential();

        String result = tools(1500).searchByMetadata("feat", Map.of("book", "CRB", "componentType", "feat"));

        assertThat(result).contains("猛力攻击", "CRB");
        assertThat(result).contains(" [#1]");
        verify(collector).add(any());
    }

    /** P0-B2：feat 的 title 过滤不再返回「未知过滤字段」，正常路由查询（LLM 已知道确切条目名） */
    @Test
    void searchByMetadataTitleFieldAcceptedForFeatModule() {
        Document doc = spellDoc("精通擒抱", Map.of(
                "title", "精通擒抱",
                "book_abbreviation", "CRB",
                "component_type", "feat"));
        when(searchService.searchByMetadata(eq("feat"), anyMap())).thenReturn(List.of(doc));
        stubAddSequential();

        String result = tools(1500).searchByMetadata("feat", Map.of("title", "精通擒抱"));

        assertThat(result).doesNotContain("未知过滤字段");
        assertThat(result).contains("精通擒抱", "CRB");
        verify(searchService).searchByMetadata(eq("feat"), eq(Map.of("title", "精通擒抱")));
        verify(collector).add(any());
    }

    // ---------- reportDataGap ----------

    /** reportDataGap 记录缺口并标记 gap（入库成功路径） */
    @Test
    void reportDataGapRecordsAndMarksGap() {
        when(recorder.record("女巫的XX变体规则", "{className:女巫}", "查不到该变体")).thenReturn(true);

        String result = tools(1500).reportDataGap("女巫的XX变体规则", "{className:女巫}", "查不到该变体");

        verify(recorder).record("女巫的XX变体规则", "{className:女巫}", "查不到该变体");
        verify(collector).markGapReported();
        assertThat(result).contains("已记录");
    }

    /** F-021：缺口未入库（DB 不可用/写失败）→ 不置 gapReported，回话据实说明未记录 */
    @Test
    void reportDataGapNotPersistedDoesNotClaimRecorded() {
        when(recorder.record("女巫的XX变体规则", "{className:女巫}", "查不到该变体")).thenReturn(false);

        String result = tools(1500).reportDataGap("女巫的XX变体规则", "{className:女巫}", "查不到该变体");

        assertThat(result).contains("未能记录").doesNotContain("已记录数据缺口");
        verify(collector, never()).markGapReported();
    }

    // ---------- getSpellList（SP3 F-007） ----------

    /** 别名归一命中：resolve 归一到规范职业，formatLevel 输出紧凑清单，列表页挂溯源 */
    @Test
    void getSpellListAliasResolvesAndCollectsListPage() {
        when(spellListService.isAvailable()).thenReturn(true);
        when(spellListService.resolve("诗人")).thenReturn("吟游诗人");
        when(spellListService.formatLevel("吟游诗人", 2, 100000, null, null))
                .thenReturn("「吟游诗人」2 环法术（共 1 条）：\n1. 移除恐惧（Remove Fear） [CRB]");
        Document listPage = Document.builder().text("吟游诗人法术列表")
                .metadata(Map.of("title", "吟游诗人法术列表", "tocPath", "职业 → 核心职业 → 吟游诗人 → 法术列表"))
                .build();
        when(spellListService.listPageDocument("吟游诗人")).thenReturn(listPage);
        stubAddSequential();

        String result = tools(1500).getSpellList("诗人", 2, null, null);

        assertThat(result).contains("「吟游诗人」2 环法术", "移除恐惧");
        assertThat(result).contains("本清单来源 [#1]");   // SP4 D2：清单末尾单来源编号
        // 别名归一后按规范名查询，而非原输入
        verify(spellListService).formatLevel("吟游诗人", 2, 100000, null, null);
        ArgumentCaptor<List<Document>> captor = ArgumentCaptor.forClass(List.class);
        verify(collector).add(captor.capture());
        assertThat(captor.getValue()).containsExactly(listPage);
    }

    /** F-025：折叠清单多书缩写行照常透传，SourceCollector 仍只收列表页单来源 */
    @Test
    void getSpellListFoldedDisplayStillCollectsOnlyListPage() {
        when(spellListService.isAvailable()).thenReturn(true);
        when(spellListService.resolve("女巫")).thenReturn("女巫");
        when(spellListService.formatLevel("女巫", 1, 100000, null, null))
                .thenReturn("「女巫」1 环法术（共 2 条）：\n"
                        + "1. 精确施法（Sure Casting） [PSP/COMP]\n"
                        + "2. 法师密派生（Wizard Secret） [APG/UM]〔派生〕");
        Document listPage = Document.builder().text("女巫法术列表")
                .metadata(Map.of("title", "女巫法术列表")).build();
        when(spellListService.listPageDocument("女巫")).thenReturn(listPage);
        stubAddSequential();

        String result = tools(1500).getSpellList("女巫", 1, null, null);

        assertThat(result).contains("[PSP/COMP]", "[APG/UM]〔派生〕", "本清单来源 [#1]");
        ArgumentCaptor<List<Document>> captor = ArgumentCaptor.forClass(List.class);
        verify(collector).add(captor.capture());
        assertThat(captor.getValue()).containsExactly(listPage);
    }

    /** 未知职业：返回可用职业清单让 LLM 自纠，不收集来源 */
    @Test
    void getSpellListUnknownClassReturnsSelfCorrection() {
        when(spellListService.isAvailable()).thenReturn(true);
        when(spellListService.resolve("死灵法师")).thenReturn(null);
        when(spellListService.knownClasses()).thenReturn(List.of("法师", "吟游诗人"));

        String result = tools(1500).getSpellList("死灵法师", 1, null, null);

        assertThat(result).contains("未知职业", "死灵法师", "法师", "吟游诗人");
        verifyNoInteractions(collector);
    }

    /** level 为空：返回各环级概览并提示（不塞全表），列表页仍挂溯源 */
    @Test
    void getSpellListNullLevelReturnsOverview() {
        when(spellListService.isAvailable()).thenReturn(true);
        when(spellListService.resolve("法师")).thenReturn("法师");
        when(spellListService.levelOverview("法师"))
                .thenReturn("「法师」共收录 823 条。请指定环级（0~9）查看清单，如 level=1。");
        when(spellListService.listPageDocument("法师"))
                .thenReturn(Document.builder().text("法师法术列表").metadata(Map.of("title", "法师法术列表")).build());
        stubAddSequential();

        String result = tools(1500).getSpellList("法师", null, null, null);

        assertThat(result).contains("823 条", "请指定环级");
        assertThat(result).contains("本清单来源 [#1]");   // 概览也挂来源编号
        verify(spellListService).levelOverview("法师");
        verify(spellListService, never()).formatLevel(anyString(), anyInt(), anyInt());
        verify(collector).add(any());
    }

    /** level 越界：提示合法范围 + 概览，不抛异常 */
    @Test
    void getSpellListOutOfRangeLevelReturnsHintAndOverview() {
        when(spellListService.isAvailable()).thenReturn(true);
        when(spellListService.resolve("法师")).thenReturn("法师");
        when(spellListService.levelOverview("法师")).thenReturn("「法师」共收录 823 条");
        when(spellListService.listPageDocument("法师"))
                .thenReturn(Document.builder().text("法师法术列表").metadata(Map.of("title", "法师法术列表")).build());
        stubAddSequential();

        String result = tools(1500).getSpellList("法师", 12, null, null);

        assertThat(result).contains("环级须在 0~9 之间", "823 条");
        assertThat(result).contains("本清单来源 [#1]");   // 越界提示后仍挂概览来源
        verify(spellListService, never()).formatLevel(anyString(), anyInt(), anyInt());
    }

    /** className 为空：提示提供职业名，不收集 */
    @Test
    void getSpellListBlankClassNamePromptsForClass() {
        when(spellListService.isAvailable()).thenReturn(true);
        when(spellListService.knownClasses()).thenReturn(List.of("法师", "吟游诗人"));

        String result = tools(1500).getSpellList("   ", 1, null, null);

        assertThat(result).contains("请提供职业名", "法师", "吟游诗人");
        verify(spellListService, never()).resolve(anyString());
        verifyNoInteractions(collector);
    }

    // ---------- getClassTable（J5 F-019） ----------

    /** 正常路径：别名归一 + 单行成长表 + 溯源编号 */
    @Test
    void getClassTableAliasResolvesRowAndCollectsProvenance() {
        when(classTableService.isAvailable()).thenReturn(true);
        when(classTableService.resolve("Wizard")).thenReturn("法师");
        when(classTableService.maxLevel("法师")).thenReturn(20);
        when(classTableService.formatRow("法师", 5))
                .thenReturn("「法师」等级 5：BAB +2 | 强韧 +1 | 反射 +1 | 意志 +4 | 特殊：无\n每日法术：0环4、1环3、2环2、3环1");
        Document provenance = Document.builder().text("法师成长表原文")
                .metadata(Map.of("title", "表：法师", "chunk_id", "class_page_66_0001")).build();
        when(classTableService.provenanceDocument("法师")).thenReturn(provenance);
        stubAddSequential();

        String result = tools(1500).getClassTable("Wizard", 5);

        assertThat(result).contains("「法师」等级 5", "BAB +2", "意志 +4", "每日法术：0环4、1环3");
        assertThat(result).contains("来源编号 [#1]");
        verify(collector).add(any());
    }

    /** level 省略：返回全表并挂溯源 */
    @Test
    void getClassTableNullLevelReturnsFullTable() {
        when(classTableService.isAvailable()).thenReturn(true);
        when(classTableService.resolve("战士")).thenReturn("战士");
        when(classTableService.maxLevel("战士")).thenReturn(20);
        when(classTableService.formatTable("战士")).thenReturn("「战士」成长表（1~20 级）：\n…20 行…");
        when(classTableService.provenanceDocument("战士"))
                .thenReturn(Document.builder().text("战士成长表原文").metadata(Map.of("title", "表：战士")).build());
        stubAddSequential();

        String result = tools(1500).getClassTable("战士", null);

        assertThat(result).contains("「战士」成长表（1~20 级）");
        verify(classTableService).formatTable("战士");
        verify(classTableService, never()).formatRow(anyString(), anyInt());
        assertThat(result).contains("来源编号 [#1]");
    }

    /** level 越界：提示等级范围 + 全表，不抛异常 */
    @Test
    void getClassTableOutOfRangeLevelReturnsHintAndRange() {
        when(classTableService.isAvailable()).thenReturn(true);
        when(classTableService.resolve("法师")).thenReturn("法师");
        when(classTableService.maxLevel("法师")).thenReturn(20);
        when(classTableService.formatTable("法师")).thenReturn("「法师」成长表（1~20 级）");
        when(classTableService.provenanceDocument("法师"))
                .thenReturn(Document.builder().text("法师成长表原文").metadata(Map.of("title", "表：法师")).build());
        stubAddSequential();

        String result = tools(1500).getClassTable("法师", 25);

        assertThat(result).contains("越界", "1~20");
        verify(classTableService, never()).formatRow(anyString(), anyInt());
    }

    /** coverage.missing 名单内职业：诚实缺口文案 + vectorSearch 回退建议，不编造数值 */
    @Test
    void getClassTableMissingCoverageReturnsHonestGap() {
        when(classTableService.isAvailable()).thenReturn(true);
        when(classTableService.resolve("催眠师")).thenReturn(null);
        when(classTableService.missingClasses()).thenReturn(List.of("催眠师"));
        when(classTableService.knownClasses()).thenReturn(List.of("法师", "战士"));

        String result = tools(1500).getClassTable("催眠师", 5);

        assertThat(result).contains("尚未整理", "vectorSearch", "reportDataGap");
        assertThat(result).doesNotContain("BAB");
        verifyNoInteractions(collector);
    }

    /** 完全未知职业：返回可用职业清单 */
    @Test
    void getClassTableUnknownClassReturnsKnownList() {
        when(classTableService.isAvailable()).thenReturn(true);
        when(classTableService.resolve("死灵法师")).thenReturn(null);
        when(classTableService.missingClasses()).thenReturn(List.of());
        when(classTableService.knownClasses()).thenReturn(List.of("法师", "战士"));

        String result = tools(1500).getClassTable("死灵法师", 5);

        assertThat(result).contains("未知职业", "法师", "战士");
        verifyNoInteractions(collector);
    }

    /** 降级：class_tables.json 未加载 → 提示改用 vectorSearch，零查询零收集 */
    @Test
    void getClassTableUnavailableReturnsDegradeHint() {
        when(classTableService.isAvailable()).thenReturn(false);

        String result = tools(1500).getClassTable("法师", 5);

        assertThat(result).contains("不可用", "vectorSearch");
        verify(classTableService, never()).resolve(anyString());
        verifyNoInteractions(collector);
    }

    /** 清单不可用（数据文件未加载）：返回提示且零查询/零收集 */
    @Test
    void getSpellListUnavailableReturnsHintWithoutQuery() {
        when(spellListService.isAvailable()).thenReturn(false);

        String result = tools(1500).getSpellList("法师", 1, null, null);

        assertThat(result).contains("不可用", "searchByMetadata");
        verify(spellListService, never()).resolve(anyString());
        verify(spellListService, never()).formatLevel(anyString(), anyInt(), anyInt());
        verifyNoInteractions(collector);
    }

    // ---------- searchByMetadata 增强版（SP8a J2，参数对象） ----------

    /** 合法 orFilters 查询：透传参数对象、紧凑列表含 chunk_id、limit 默认 50 */
    @Test
    void searchByMetadataQueryOrFiltersPassesQueryAndDefaultsLimit() {
        Document doc = spellDoc("猛力攻击", Map.of(
                "title", "猛力攻击", "book_abbreviation", "CRB", "chunk_id", "feat-1"));
        when(searchService.searchByMetadataPaged(eq("feat"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(doc), 1, 0, 50));
        stubAddSequential();
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setOrFilters(Map.of("book", List.of("CRB", "APG")));
        query.setAllowBroadQuery(true);

        String result = tools(1500).searchByMetadata("feat", query);

        assertThat(result).contains("猛力攻击", "chunk_id:feat-1", " [#1]");
        verify(collector).add(any());
        ArgumentCaptor<MetadataSearchQuery> captor = ArgumentCaptor.forClass(MetadataSearchQuery.class);
        verify(searchService).searchByMetadataPaged(eq("feat"), captor.capture());
        assertThat(captor.getValue().getLimit()).isEqualTo(50);   // 默认 limit 已注入
        assertThat(captor.getValue().getOffset()).isZero();
    }

    /** 显式 limit/offset 透传不被默认值覆盖（翻页参数原样到达 SearchService） */
    @Test
    void searchByMetadataQueryExplicitLimitOffsetPassedThrough() {
        Document doc = spellDoc("猛力攻击", Map.of(
                "title", "猛力攻击", "book_abbreviation", "CRB", "chunk_id", "feat-1"));
        when(searchService.searchByMetadataPaged(eq("feat"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(doc), 21, 20, 10));
        stubAddSequential();
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("book", "CRB"));
        query.setAllowBroadQuery(true);
        query.setLimit(10);
        query.setOffset(20);

        String result = tools(1500).searchByMetadata("feat", query);

        assertThat(result).contains("猛力攻击");
        ArgumentCaptor<MetadataSearchQuery> captor = ArgumentCaptor.forClass(MetadataSearchQuery.class);
        verify(searchService).searchByMetadataPaged(eq("feat"), captor.capture());
        assertThat(captor.getValue().getLimit()).isEqualTo(10);  // 显式值不被默认 50 覆盖
        assertThat(captor.getValue().getOffset()).isEqualTo(20); // 显式值不被默认 0 覆盖
    }

    /** 分页元数据（字符截断）：提示带真实总数 + has_more + 动态 next_offset（AKN-015 修复） */
    @Test
    void searchByMetadataCharTruncatedHintCarriesTotalAndNextOffset() {
        List<Document> docs = new ArrayList<>();
        for (int i = 1; i <= 10; i++) {
            docs.add(spellDoc("法术" + i, Map.of("title", "法术" + i, "book_abbreviation", "CRB")));
        }
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(docs, 10, 0, 200));
        stubAddSequential();
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("book", "CRB"));
        query.setAllowBroadQuery(true);
        query.setLimit(200);

        String result = tools(1500, 260).searchByMetadata("spell", query);

        int shown = numberedLines(result);
        assertThat(shown).isBetween(1, 9);                         // 确实发生了字符截断
        assertThat(result).contains("共 10 条", "has_more=true");
        assertThat(hintStart(result)).isEqualTo(1);
        assertThat(hintEnd(result)).isEqualTo(shown);
        assertThat(hintNextOffset(result)).isEqualTo(shown).isGreaterThan(0);  // 不能退化为 0
        assertThat(result).doesNotContain("收窄过滤");
    }

    /** 分页元数据（limit 静默截断）：无字符截断但 has_more 时也必须给提示（原缺陷：拿到当页就以为完事） */
    @Test
    void searchByMetadataLimitTruncatedWithoutCharCapAlsoHints() {
        List<Document> docs = new ArrayList<>();
        for (int i = 1; i <= 3; i++) {
            docs.add(spellDoc("法术" + i, Map.of("title", "法术" + i, "book_abbreviation", "CRB")));
        }
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(docs, 10, 0, 3));
        stubAddSequential();
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("book", "CRB"));
        query.setAllowBroadQuery(true);

        String result = tools(1500).searchByMetadata("spell", query);

        assertThat(result).contains("法术3");                      // 当页 3 条全部展示（无字符截断）
        assertThat(result).contains("共 10 条", "本次返回第 1~3 条", "has_more=true", "query.offset=3");
    }

    /** 结果完整（无更多页）：不出现分页提示 */
    @Test
    void searchByMetadataCompleteResultHasNoPaginationHint() {
        Document doc = spellDoc("猛力攻击", Map.of(
                "title", "猛力攻击", "book_abbreviation", "CRB", "chunk_id", "feat-1"));
        when(searchService.searchByMetadataPaged(eq("feat"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(doc), 1, 0, 50));
        stubAddSequential();
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("book", "CRB"));
        query.setAllowBroadQuery(true);

        String result = tools(1500).searchByMetadata("feat", query);

        assertThat(result).contains("猛力攻击");
        assertThat(result).doesNotContain("has_more", "query.offset");
    }

    /** 触达检索上限（cap 边界）：不得再输出假总数，改诚实版提示（AKN015-T1） */
    @Test
    void searchByMetadataCappedAtLimitReportsHonestHintAtBoundary() {
        List<Document> docs = docs(500);
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(docs, 500, 0, 500, true, 500));
        stubAddSequential();
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("book", "COMP"));
        query.setAllowBroadQuery(true);
        query.setLimit(500);

        String result = tools(1500).searchByMetadata("spell", query);

        assertThat(numberedLines(result)).isEqualTo(500);
        assertThat(result).contains("已达检索上限 500 条", "实际命中可能更多", "请收窄过滤条件");
        assertThat(result).doesNotContain("共 500 条", "query.offset");
    }

    /** 上限边界 + 字符截断：仍有未展示条目 → 只给页内续取，不再同时劝收窄（AKN015-T9） */
    @Test
    void searchByMetadataCappedBoundaryWithCharTruncationPrefersContinuation() {
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(docs(500), 500, 0, 500, true, 500));
        stubAddSequential();
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("school", "变化系"));
        query.setLimit(500);

        String result = tools(1500, 260).searchByMetadata("spell", query);

        int shown = numberedLines(result);
        assertThat(shown).isBetween(1, 499);
        assertThat(result).contains("已达检索上限 500 条", "实际命中可能更多", "has_more=true",
                "query.offset=" + shown);
        assertThat(result).doesNotContain("请收窄过滤条件", "共 500 条");
    }

    /** 检索上限内仍可翻页：诚实前缀 + has_more + next_offset，next_offset 不越过上限（AKN015-T1） */
    @Test
    void searchByMetadataCappedWithinLimitStillPaginatesHonestly() {
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(
                        new SearchService.PagedResult(docs(200), 500, 0, 200, true, 500),
                        new SearchService.PagedResult(docs(200), 500, 200, 200, true, 500));
        stubAddSequential();
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("school", "变化系"));
        query.setLimit(200);

        String first = tools(1500).searchByMetadata("spell", query);
        assertThat(first).contains("已达检索上限 500 条", "本次返回第 1~200 条",
                "has_more=true", "query.offset=200");
        assertThat(first).doesNotContain("共 500 条", "请收窄过滤");

        String second = tools(1500).searchByMetadata("spell", query);
        assertThat(second).contains("本次返回第 201~400 条", "query.offset=400");
        assertThat(second).doesNotContain("共 500 条");
    }

    /** offset 越界（已翻完）：不得复用"无命中"，应告知已翻完全部结果（AKN015-T3） */
    @Test
    void searchByMetadataOffsetBeyondTotalReportsExhaustedInsteadOfNoHit() {
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(), 5, 5, 10));
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("book", "CRB"));
        query.setAllowBroadQuery(true);
        query.setOffset(5);

        String result = tools(1500).searchByMetadata("spell", query);

        assertThat(result).contains("已翻完全部结果", "共 5 条");
        assertThat(result).doesNotContain("无命中");
    }

    /** offset 越界且触达检索上限：告知已翻完工具可返回部分，并提示收窄（AKN015-T1+T3） */
    @Test
    void searchByMetadataOffsetBeyondCappedTotalReportsExhaustedHonestly() {
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(), 500, 500, 50, true, 500));
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("book", "COMP"));
        query.setAllowBroadQuery(true);
        query.setOffset(500);

        String result = tools(1500).searchByMetadata("spell", query);

        assertThat(result).contains("已翻完", "已达检索上限", "实际命中可能更多", "请收窄过滤条件");
        assertThat(result).doesNotContain("无命中");
    }

    /** query 为 null 或全空：返回宽查询护栏建议（no_conditions），不执行条目检索 */
    @Test
    void searchByMetadataQueryNullOrEmptyReturnsGuardSuggestionWithoutQuery() {
        String nullQuery = tools(1500).searchByMetadata("spell", (MetadataSearchQuery) null);
        assertThat(nullQuery).contains("宽查询护栏", "未执行条目检索", "no_conditions", "allowBroadQuery=true");
        assertThat(nullQuery).contains("不要据此调用 reportDataGap");

        String emptyQuery = tools(1500).searchByMetadata("spell", new MetadataSearchQuery());
        assertThat(emptyQuery).contains("宽查询护栏", "no_conditions", "有效业务收窄");

        verifyNoInteractions(searchService);
        verifyNoInteractions(collector);
    }

    // ---------- F-026 宽查询门禁 ----------

    /** 仅书条件未放行：不执行检索，返回护栏建议并记录 BLOCKED(book_only) */
    @Test
    void searchByMetadataBookOnlyWithoutAllowIsBlockedAndRecordsBlocked() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("book", "CRB"));

        String result = tools(1500).searchByMetadata("spell", query);

        assertThat(result).contains("宽查询护栏", "未执行条目检索", "book_only", "allowBroadQuery=true");
        assertThat(result).contains("可用业务条件字段", "className", "school");
        verifyNoInteractions(searchService);
        verifyNoInteractions(collector);
        verify(queryGateEventRecorder).recordBlocked("searchByMetadata", "spell", Reason.BOOK_ONLY, query);
        verify(queryGateEventRecorder, never()).recordAllowed(any(), any(), any(), any());
    }

    /** 显式 allowBroadQuery=false 与缺省同义：仍拦截 */
    @Test
    void searchByMetadataExplicitFalseStillBlocked() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setOrFilters(Map.of("book", List.of("CRB", "APG")));
        query.setAllowBroadQuery(false);

        String result = tools(1500).searchByMetadata("feat", query);

        assertThat(result).contains("宽查询护栏", "book_only");
        verifyNoInteractions(searchService);
        verify(queryGateEventRecorder).recordBlocked("searchByMetadata", "feat", Reason.BOOK_ONLY, query);
    }

    /** 仅书 + allowBroadQuery=true：放行执行，记录 ALLOWED(book_only)；同条件下一页仍放行 */
    @Test
    void searchByMetadataBookOnlyAllowedExecutesAndRecordsAllowedPerPage() {
        Document doc = spellDoc("火球术", Map.of("title", "火球术", "book_abbreviation", "CRB", "chunk_id", "spell-1"));
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(doc), 1, 0, 50));
        stubAddSequential();
        MetadataSearchQuery first = new MetadataSearchQuery();
        first.setFilters(Map.of("book", "CRB"));
        first.setAllowBroadQuery(true);
        MetadataSearchQuery second = new MetadataSearchQuery();
        second.setFilters(Map.of("book", "CRB"));
        second.setAllowBroadQuery(true);
        second.setOffset(50);

        String page1 = tools(1500).searchByMetadata("spell", first);

        assertThat(page1).contains("火球术", " [#1]");
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(doc), 51, 50, 50));
        tools(1500).searchByMetadata("spell", second);

        verify(queryGateEventRecorder).recordAllowed("searchByMetadata", "spell", Reason.BOOK_ONLY, first);
        verify(queryGateEventRecorder).recordAllowed("searchByMetadata", "spell", Reason.BOOK_ONLY, second);
        verify(queryGateEventRecorder, never()).recordBlocked(any(), any(), any(), any());
    }

    /** 无业务条件 + allowBroadQuery=true：放行无条件查询，记录 ALLOWED(no_conditions)，默认 limit/offset 注入 */
    @Test
    void searchByMetadataNoConditionsAllowedRunsUnconditionalQuery() {
        Document doc = spellDoc("法术一", Map.of("title", "法术一", "book_abbreviation", "CRB", "chunk_id", "spell-1"));
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(doc), 1, 0, 50));
        stubAddSequential();
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setAllowBroadQuery(true);

        String result = tools(1500).searchByMetadata("spell", query);

        assertThat(result).contains("法术一");
        org.mockito.ArgumentCaptor<MetadataSearchQuery> captor =
                org.mockito.ArgumentCaptor.forClass(MetadataSearchQuery.class);
        verify(searchService).searchByMetadataPaged(eq("spell"), captor.capture());
        assertThat(captor.getValue().getLimit()).isEqualTo(50);
        assertThat(captor.getValue().getOffset()).isZero();
        verify(queryGateEventRecorder).recordAllowed("searchByMetadata", "spell", Reason.NO_CONDITIONS, query);
    }

    /** 书 + 主题等有效业务条件：工具护栏不拦截，也不记录门禁事件 */
    @Test
    void searchByMetadataNarrowQueryDoesNotRecordGateEvent() {
        Document doc = spellDoc("火球术", Map.of("title", "火球术", "school", "咒法系", "book_abbreviation", "CRB"));
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(doc), 1, 0, 50));
        stubAddSequential();
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("book", "CRB", "school", "咒法系"));

        String result = tools(1500).searchByMetadata("spell", query);

        assertThat(result).contains("火球术");
        verifyNoInteractions(queryGateEventRecorder);
    }

    /** 参数校验先于门禁：非法输入即使 allowBroadQuery=true 也返回校验错误且不产生事件 */
    @Test
    void searchByMetadataInvalidInputBeforeGateProducesNoEvent() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("book", "CRB"));
        query.setLte(Map.of("foo", "x"));
        query.setAllowBroadQuery(true);

        String result = tools(1500).searchByMetadata("feat", query);

        assertThat(result).contains("未知过滤字段", "foo");
        verifyNoInteractions(searchService);
        verifyNoInteractions(queryGateEventRecorder);
    }

    /** 同一无业务条件查询的翻页每页各记一行 ALLOWED（offset 可区分） */
    @Test
    void searchByMetadataNoConditionsAllowedRecordsOneEventPerPage() {
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(), 0, 0, 50));
        MetadataSearchQuery first = new MetadataSearchQuery();
        first.setAllowBroadQuery(true);
        MetadataSearchQuery second = new MetadataSearchQuery();
        second.setAllowBroadQuery(true);
        second.setOffset(50);

        tools(1500).searchByMetadata("spell", first);
        tools(1500).searchByMetadata("spell", second);

        verify(queryGateEventRecorder).recordAllowed("searchByMetadata", "spell", Reason.NO_CONDITIONS, first);
        verify(queryGateEventRecorder).recordAllowed("searchByMetadata", "spell", Reason.NO_CONDITIONS, second);
    }

    /** AKN-024：同会话同 module+book 放行；换书驳回（searchByMetadata 同样走指纹校验） */
    @Test
    void sessionFingerprintRejectsBookChangeForSearchByMetadata() {
        when(searchService.searchByMetadataPaged(eq("rule"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(), 0, 0, 50));
        toolCallTracker.begin("cid-meta-fp", "CRB 所有规则");

        MetadataSearchQuery initial = new MetadataSearchQuery();
        initial.setFilters(Map.of("book", "CRB"));
        assertThat(sessionTools(1500).searchByMetadata("rule", initial)).contains("宽查询护栏");

        toolCallTracker.begin("cid-meta-fp", "仍按 CRB 原范围查询");
        MetadataSearchQuery same = new MetadataSearchQuery();
        same.setFilters(Map.of("book", "CRB"));
        same.setAllowBroadQuery(true);
        assertThat(sessionTools(1500).searchByMetadata("rule", same)).doesNotContain("宽查询护栏");

        MetadataSearchQuery changed = new MetadataSearchQuery();
        changed.setFilters(Map.of("book", "APG"));
        changed.setAllowBroadQuery(true);
        assertThat(sessionTools(1500).searchByMetadata("rule", changed)).contains("宽查询护栏");
        verify(queryGateEventRecorder)
                .recordBlocked("searchByMetadata", "rule", Reason.FINGERPRINT_MISMATCH, changed);
        verify(searchService, times(1)).searchByMetadataPaged(eq("rule"), any(MetadataSearchQuery.class));
    }

    /** AKN-024 同轮重试：searchByMetadata 驳回后同一 requestId 再次 allow=true 不得自我放行 */
    @Test
    void sessionFingerprintBlocksSameRequestRetryForSearchByMetadata() {
        when(searchService.searchByMetadataPaged(eq("rule"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(), 0, 0, 50));
        toolCallTracker.begin("cid-meta-retry", "CRB 所有规则");

        MetadataSearchQuery initial = new MetadataSearchQuery();
        initial.setFilters(Map.of("book", "CRB"));
        assertThat(sessionTools(1500).searchByMetadata("rule", initial)).contains("宽查询护栏");

        MetadataSearchQuery retry = new MetadataSearchQuery();
        retry.setFilters(Map.of("book", "CRB"));
        retry.setAllowBroadQuery(true);
        assertThat(sessionTools(1500).searchByMetadata("rule", retry)).contains("宽查询护栏");
        assertThat(sessionTools(1500).searchByMetadata("rule", retry)).contains("宽查询护栏");
        verify(searchService, never()).searchByMetadataPaged(eq("rule"), any(MetadataSearchQuery.class));
        verify(queryGateEventRecorder, times(2))
                .recordBlocked("searchByMetadata", "rule", Reason.FINGERPRINT_MISMATCH, retry);

        toolCallTracker.begin("cid-meta-retry", "仍按 CRB 原范围查询");
        assertThat(sessionTools(1500).searchByMetadata("rule", retry)).doesNotContain("宽查询护栏");
        verify(searchService, times(1)).searchByMetadataPaged(eq("rule"), any(MetadataSearchQuery.class));
    }

    /** AKN-024 regenerate：没有新用户轮次，不得凭新 requestId 放行待确认指纹 */
    @Test
    void sessionFingerprintBlocksRegenerateConfirmationForSearchByMetadata() {
        when(searchService.searchByMetadataPaged(eq("rule"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(), 0, 0, 50));
        toolCallTracker.begin("cid-meta-regen", "CRB 所有规则");

        MetadataSearchQuery initial = new MetadataSearchQuery();
        initial.setFilters(Map.of("book", "CRB"));
        assertThat(sessionTools(1500).searchByMetadata("rule", initial)).contains("宽查询护栏");

        MetadataSearchQuery retry = new MetadataSearchQuery();
        retry.setFilters(Map.of("book", "CRB"));
        retry.setAllowBroadQuery(true);
        toolCallTracker.beginRegenerate("cid-meta-regen", "CRB 所有规则");
        assertThat(sessionTools(1500).searchByMetadata("rule", retry)).contains("宽查询护栏");
        verify(searchService, never()).searchByMetadataPaged(eq("rule"), any(MetadataSearchQuery.class));

        toolCallTracker.begin("cid-meta-regen", "仍按 CRB 原范围查询");
        assertThat(sessionTools(1500).searchByMetadata("rule", retry)).doesNotContain("宽查询护栏");
        verify(searchService, times(1)).searchByMetadataPaged(eq("rule"), any(MetadataSearchQuery.class));
    }

    /**
     * AKN-027 回归（PromptBuilder 契约）：首次宽查询以 allowBroadQuery=false 调用 gated
     * 工具登记真实 module+book（被驳回），用户下一轮「仍按原范围查询」时才真正执行；
     * 同轮换 module 探测被驳回但不得打断已确认范围，下一轮确认后探测建议可放行。
     */
    @Test
    void akn027FirstBroadQueryRegistersFingerprintThenNextTurnConfirms() {
        when(searchService.searchByMetadataPaged(anyString(), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(), 0, 0, 50));

        // turn1：按契约以 allow=false 登记范围（真实模型此前跳过这一步导致确认不可达）
        toolCallTracker.begin("cid-akn027", "CRB 里所有类型的规则条目。");
        MetadataSearchQuery register = new MetadataSearchQuery();
        register.setFilters(Map.of("book", "CRB"));
        assertThat(sessionTools(1500).searchByMetadata("rule", register))
                .contains("宽查询护栏");

        // turn2：用户确认 → 原建议范围（rule + CRB）真正执行
        toolCallTracker.begin("cid-akn027", "仍按原范围查询。");
        MetadataSearchQuery original = ruleCrbQuery();
        assertThat(sessionTools(1500).searchByMetadata("rule", original))
                .doesNotContain("宽查询护栏");
        verify(queryGateEventRecorder)
                .recordAllowed("searchByMetadata", "rule", Reason.BOOK_ONLY, original);

        // 同轮换 module 探测：驳回，但不得清掉已确认的 rule 边界
        MetadataSearchQuery allCrb = new MetadataSearchQuery();
        allCrb.setFilters(Map.of("book", "CRB"));
        allCrb.setAllowBroadQuery(true);
        assertThat(sessionTools(1500).searchByMetadata("all", allCrb)).contains("宽查询护栏");
        assertThat(sessionTools(1500).searchByMetadata("rule", original))
                .doesNotContain("宽查询护栏");
        verify(queryGateEventRecorder)
                .recordBlocked("searchByMetadata", "all", Reason.FINGERPRINT_MISMATCH, allCrb);
        verify(searchService, times(2))
                .searchByMetadataPaged(eq("rule"), any(MetadataSearchQuery.class));

        // turn3：用户再次确认 → turn2 探测留下的 all+CRB 建议可被确认
        toolCallTracker.begin("cid-akn027", "仍按原范围查询。");
        assertThat(sessionTools(1500).searchByMetadata("all", allCrb))
                .doesNotContain("宽查询护栏");
        verify(searchService)
                .searchByMetadataPaged(eq("all"), any(MetadataSearchQuery.class));
    }

    /** AKN-027：没有工具层登记、仅文本建议后直接换模块，allow 声明必须驳回并留建议 */
    @Test
    void akn027ChangedModuleNeedsOwnSuggestionAndConfirmation() {
        when(searchService.searchByMetadataPaged(anyString(), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(), 0, 0, 50));

        toolCallTracker.begin("cid-akn027-module", "CRB 里所有类型的规则条目。");
        MetadataSearchQuery register = new MetadataSearchQuery();
        register.setFilters(Map.of("book", "CRB"));
        sessionTools(1500).searchByMetadata("rule", register);

        // 下一用户轮次直接换模块声明 allow：无 feat+CRB 建议 → 驳回（留建议）
        toolCallTracker.begin("cid-akn027-module", "CRB 所有专长，完整列出。");
        MetadataSearchQuery featCrb = new MetadataSearchQuery();
        featCrb.setFilters(Map.of("book", "CRB"));
        featCrb.setAllowBroadQuery(true);
        assertThat(sessionTools(1500).searchByMetadata("feat", featCrb)).contains("宽查询护栏");

        // 再下一真实用户轮次确认后才执行
        toolCallTracker.begin("cid-akn027-module", "仍按原范围查询。");
        assertThat(sessionTools(1500).searchByMetadata("feat", featCrb))
                .doesNotContain("宽查询护栏");
    }

    private static MetadataSearchQuery ruleCrbQuery() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("book", "CRB"));
        query.setAllowBroadQuery(true);
        return query;
    }

    /** allowBroadQuery 三态反序列化：缺省/false 均未放行，true 才放行（两参数对象同口径） */
    @Test
    void allowBroadQueryTriStateDeserializesForBothQueryObjects() throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        String absentJson = "{\"filters\":{\"book\":\"CRB\"}}";
        String falseJson = "{\"filters\":{\"book\":\"CRB\"},\"allowBroadQuery\":false}";
        String trueJson = "{\"filters\":{\"book\":\"CRB\"},\"allowBroadQuery\":true}";

        assertThat(mapper.readValue(absentJson, MetadataSearchQuery.class).isBroadQueryAllowed()).isFalse();
        assertThat(mapper.readValue(falseJson, MetadataSearchQuery.class).isBroadQueryAllowed()).isFalse();
        assertThat(mapper.readValue(trueJson, MetadataSearchQuery.class).isBroadQueryAllowed()).isTrue();

        assertThat(mapper.readValue(absentJson, ListEntriesQuery.class).isBroadQueryAllowed()).isFalse();
        assertThat(mapper.readValue(falseJson, ListEntriesQuery.class).isBroadQueryAllowed()).isFalse();
        assertThat(mapper.readValue(trueJson, ListEntriesQuery.class).isBroadQueryAllowed()).isTrue();
        // 放行字段不影响业务条件判定
        assertThat(mapper.readValue(trueJson, MetadataSearchQuery.class).hasAnyCondition()).isTrue();
        assertThat(mapper.readValue(trueJson, ListEntriesQuery.class).hasAnyCondition()).isTrue();
    }

    /** query 含未知字段：返回可用字段清单让 LLM 自纠（白名单防线不破） */
    @Test
    void searchByMetadataQueryUnknownFieldListsAvailableWithoutQuery() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("foo", "bar"));

        String result = tools(1500).searchByMetadata("spell", query);

        assertThat(result).contains("未知过滤字段", "foo", "className", "school");
        verifyNoInteractions(searchService);
    }

    /** orFilters 里的未知字段同样触发字段清单自纠 */
    @Test
    void searchByMetadataQueryUnknownOrFieldListsAvailableWithoutQuery() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setOrFilters(Map.of("foo", List.of("a", "b")));

        String result = tools(1500).searchByMetadata("spell", query);

        assertThat(result).contains("未知过滤字段", "foo", "className", "school");
        verifyNoInteractions(searchService);
    }

    /** spell 的 level 比较缺 className：返回组合键提示 */
    @Test
    void searchByMetadataQueryLevelComparisonWithoutClassNameReturnsHint() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setGte(Map.of("level", "3"));

        String result = tools(1500).searchByMetadata("spell", query);

        assertThat(result).contains("level 比较", "className");
        verifyNoInteractions(searchService);
    }

    /** 非法 sortBy/sortOrder：返回可用值清单 */
    @Test
    void searchByMetadataQueryInvalidSortReturnsAvailableValues() {
        MetadataSearchQuery badSortBy = new MetadataSearchQuery();
        badSortBy.setFilters(Map.of("book", "CRB"));
        badSortBy.setSortBy("name");
        assertThat(tools(1500).searchByMetadata("feat", badSortBy))
                .contains("未知排序字段", "title", "level", "book");

        MetadataSearchQuery badOrder = new MetadataSearchQuery();
        badOrder.setFilters(Map.of("book", "CRB"));
        badOrder.setSortOrder("up");
        assertThat(tools(1500).searchByMetadata("feat", badOrder))
                .contains("未知排序方向", "asc", "desc");
        verifyNoInteractions(searchService);
    }

    /** 空结果：返回固定回退引导文案（不自动改写查询） */
    @Test
    void searchByMetadataQueryNoResultsReturnsFallbackGuidance() {
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(), 0, 0, 50));
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("school", "咒法系"));

        String result = tools(1500).searchByMetadata("spell", query);

        assertThat(result).contains("无命中", "减少一个过滤条件", "vectorSearch", "reportDataGap");
        verifyNoInteractions(collector);
    }

    /** module="all"：紧凑列表行首标注模块名 */
    @Test
    void searchByMetadataQueryAllModulePrefixesModuleName() {
        Document doc = Document.builder().text("正文")
                .metadata(Map.of("title", "猛力攻击", "book_abbreviation", "CRB",
                        "chunk_id", "feat-9", "pf_module", "feat")).build();
        when(searchService.searchByMetadataPaged(eq("all"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(List.of(doc), 1, 0, 50));
        stubAddSequential();
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("title", "猛力攻击"));

        String result = tools(1500).searchByMetadata("all", query);

        assertThat(result).contains("[模块:feat]", "猛力攻击");
        verify(collector).add(any());
    }

    /** vectorSearch 片段头补充 chunk_id 字段（J1 点查入参来源） */
    @Test
    void vectorSearchFragmentIncludesChunkId() {
        Document doc = spellDoc("火球术", Map.of(
                "title", "火球术", "book_name_cn", "核心规则书",
                "book_abbreviation", "CRB", "chunk_id", "spell-42"));
        when(searchService.search(eq("火球术射程"), eq("spell"))).thenReturn(List.of(doc));
        stubAddSequential();

        String result = tools(1500).vectorSearch("火球术射程", "spell");

        assertThat(result).contains("chunk_id: spell-42");
    }

    // ---------- getEntryById（SP8a J1） ----------

    /** 命中：返回完整原文 + 元信息 + 来源编号，交 SourceCollector 溯源 */
    @Test
    void getEntryByIdHitReturnsFullTextAndCollects() {
        Document doc = Document.builder().text("火球术完整规则原文")
                .metadata(Map.of("title", "火球术", "book_name_cn", "核心规则书",
                        "book_abbreviation", "CRB")).build();
        when(searchService.getByChunkId("spell", "spell-1")).thenReturn(doc);
        stubAddSequential();

        String result = tools(1500).getEntryById("spell", "spell-1");

        assertThat(result).contains("标题: 火球术", "来源: 核心规则书 (CRB)",
                "模块: spell", "chunk_id: spell-1", "火球术完整规则原文", "[#1]");
        verify(collector).add(any());
    }

    /** 未命中：返回可读提示，不收集来源 */
    @Test
    void getEntryByIdMissReturnsHintWithoutCollecting() {
        when(searchService.getByChunkId("spell", "nope")).thenReturn(null);

        String result = tools(1500).getEntryById("spell", "nope");

        assertThat(result).contains("无匹配条目", "chunk_id 需来自检索结果");
        verifyNoInteractions(collector);
    }

    /** 非法模块与空 chunkId：返回可读提示，不查询 */
    @Test
    void getEntryByIdInvalidArgsReturnHintsWithoutQuery() {
        assertThat(tools(1500).getEntryById("monster", "x")).contains("未知模块");
        assertThat(tools(1500).getEntryById("spell", "  ")).contains("chunkId");
        verifyNoInteractions(searchService);
        verifyNoInteractions(collector);
    }

    /** 超长条目截断到 entry-result-chars 并提示（风险缓解：防 oversize chunk 爆上下文） */
    @Test
    void getEntryByIdOversizeTextTruncatedWithHint() {
        Document doc = Document.builder().text("a".repeat(300))
                .metadata(Map.of("title", "法术索引表", "book_abbreviation", "CRB")).build();
        when(searchService.getByChunkId("spell", "big")).thenReturn(doc);
        stubAddSequential();
        RetrievalTools t = tools(1500);
        ReflectionTestUtils.setField(t, "entryResultChars", 100);

        String result = t.getEntryById("spell", "big");

        assertThat(result).contains("已截断", "100 字符", "vectorSearch");
        assertThat(result).doesNotContain("a".repeat(200));
    }

    // ---------- listDataGaps（SP8a J3） ----------

    /** 默认 limit 走配置（20），输出最新在前的紧凑列表 */
    @Test
    void listDataGapsDefaultLimitUsesConfigAndFormatsLines() {
        List<DataGapRecorder.GapEntry> gaps = List.of(
                new DataGapRecorder.GapEntry("2026-09-18T10:00:00", "女巫的XX规则", "查不到该变体"));
        when(recorder.listGaps(20, null)).thenReturn(DataGapRecorder.GapQueryResult.of(gaps));

        String result = tools(1500).listDataGaps(null, null);

        assertThat(result).contains("最新在前", "2026-09-18T10:00:00", "女巫的XX规则", "查不到该变体");
        verify(recorder).listGaps(20, null);
    }

    /** limit 超 100 收敛到 100；keyword 透传 */
    @Test
    void listDataGapsLimitCappedAndKeywordPassed() {
        when(recorder.listGaps(100, "女巫")).thenReturn(DataGapRecorder.GapQueryResult.of(List.of()));

        String result = tools(1500).listDataGaps(500, "女巫");

        assertThat(result).contains("暂无匹配");
        verify(recorder).listGaps(100, "女巫");
    }

    /** 无记录：返回固定提示 */
    @Test
    void listDataGapsEmptyReturnsHint() {
        when(recorder.listGaps(20, null)).thenReturn(DataGapRecorder.GapQueryResult.of(List.of()));

        String result = tools(1500).listDataGaps(null, null);

        assertThat(result).contains("暂无数据缺口记录");
    }

    /** F-021 读侧诚实：库不可用（未装配/读取失败）不得说成「暂无记录」，否则 LLM 会误判无重复缺口 */
    @Test
    void listDataGapsUnavailableDatabaseReportsUnavailable() {
        when(recorder.listGaps(20, null)).thenReturn(DataGapRecorder.GapQueryResult.unavailable());

        String result = tools(1500).listDataGaps(null, null);

        assertThat(result).contains("库不可用").doesNotContain("暂无数据缺口记录");
    }

    /** J1 截断边界：正文恰好等于 entry-result-chars（8000）时不截断、无提示 */
    @Test
    void getEntryByIdTextExactlyAtCharLimitNotTruncated() {
        String text = "正".repeat(8000);
        Document doc = Document.builder().text(text)
                .metadata(Map.of("title", "长条目", "book_abbreviation", "CRB")).build();
        when(searchService.getByChunkId("spell", "edge")).thenReturn(doc);
        stubAddSequential();

        String result = tools(1500).getEntryById("spell", "edge");

        assertThat(result).contains("正".repeat(8000));
        assertThat(result).doesNotContain("已截断");
    }

    /** J1 截断边界：正文超出上限 1 字符即截断并提示（末尾标记被截掉） */
    @Test
    void getEntryByIdTextOneOverCharLimitTruncated() {
        String text = "正".repeat(8000) + "ENDMARKER";
        Document doc = Document.builder().text(text)
                .metadata(Map.of("title", "长条目", "book_abbreviation", "CRB")).build();
        when(searchService.getByChunkId("spell", "edge")).thenReturn(doc);
        stubAddSequential();

        String result = tools(1500).getEntryById("spell", "edge");

        assertThat(result).contains("已截断", "8000 字符");
        assertThat(result).doesNotContain("ENDMARKER");
    }

    /** J2 自纠：orFilters 里带 level 但无 className，同样返回组合键提示 */
    @Test
    void searchByMetadataQueryOrLevelWithoutClassNameReturnsHint() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setOrFilters(Map.of("level", List.of("1", "2")));

        String result = tools(1500).searchByMetadata("spell", query);

        assertThat(result).contains("level 比较", "className");
        verifyNoInteractions(searchService);
    }

    /** J2 自纠：lte 里的未知字段同样触发字段清单（不只 filters/orFilters/gte） */
    @Test
    void searchByMetadataQueryUnknownLteFieldListsAvailableWithoutQuery() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("book", "CRB"));
        query.setAllowBroadQuery(true);
        query.setLte(Map.of("foo", "x"));

        String result = tools(1500).searchByMetadata("feat", query);

        assertThat(result).contains("未知过滤字段", "foo");
        verifyNoInteractions(searchService);
    }

    /** J3 limit 钳制下界：0 或负数收敛到 1，不向下透传 */
    @Test
    void listDataGapsLimitBelowOneClampedToOne() {
        when(recorder.listGaps(1, null)).thenReturn(DataGapRecorder.GapQueryResult.of(List.of()));

        tools(1500).listDataGaps(0, null);

        verify(recorder).listGaps(1, null);
    }

    private List<Document> docs(int n) {
        List<Document> list = new ArrayList<>();
        for (int i = 1; i <= n; i++) {
            list.add(spellDoc("法术" + i, Map.of("title", "法术" + i,
                    "book_abbreviation", "CRB", "chunk_id", "spell-" + i)));
        }
        return list;
    }

    private int numberedLines(String text) {
        Matcher m = NUMBERED_LINE.matcher(text);
        int count = 0;
        while (m.find()) {
            count++;
        }
        return count;
    }

    private int hintStart(String text) {
        Matcher m = HINT_RANGE.matcher(text);
        assertThat(m.find()).as("应存在分页提示").isTrue();
        return Integer.parseInt(m.group(1));
    }

    private int hintEnd(String text) {
        Matcher m = HINT_RANGE.matcher(text);
        assertThat(m.find()).as("应存在分页提示").isTrue();
        return Integer.parseInt(m.group(2));
    }

    private int hintNextOffset(String text) {
        Matcher m = HINT_NEXT_OFFSET.matcher(text);
        assertThat(m.find()).as("应存在 next_offset 提示").isTrue();
        return Integer.parseInt(m.group(1));
    }

    /**
     * stub collector.add 返回与入参等长的递增编号（1..n），模拟真实 SourceCollector 的
     * 编号分配——formatCompact/formatFragments 消费该返回值做 [#N] 注入（SP4 D2）。
     */
    private void stubAddSequential() {
        when(collector.add(any())).thenAnswer(inv -> {
            List<Document> docs = inv.getArgument(0);
            List<Integer> sequential = new ArrayList<>(docs.size());
            for (int n = 1; n <= docs.size(); n++) {
                sequential.add(n);
            }
            return sequential;
        });
    }

    private RetrievalTools tools(int vectorResultChars) {
        return tools(vectorResultChars, 100000); // 默认超大字符上限，不触发截断
    }

    /** AKN-024：带请求上下文与指纹注册表的工具实例（同测试内多次调用共享会话状态） */
    private RetrievalTools sessionTools(int vectorResultChars) {
        RetrievalTools tools = tools(vectorResultChars);
        ReflectionTestUtils.setField(tools, "toolCallTracker", toolCallTracker);
        ReflectionTestUtils.setField(tools, "broadQueryAllowanceRegistry", allowanceRegistry);
        return tools;
    }

    private RetrievalTools tools(int vectorResultChars, int metadataResultChars) {
        RetrievalTools t = new RetrievalTools();
        ReflectionTestUtils.setField(t, "searchService", searchService);
        ReflectionTestUtils.setField(t, "collector", collector);
        ReflectionTestUtils.setField(t, "recorder", recorder);
        ReflectionTestUtils.setField(t, "filterTranslator", new FilterTranslator());
        ReflectionTestUtils.setField(t, "spellListService", spellListService);
        ReflectionTestUtils.setField(t, "classTableService", classTableService);
        ReflectionTestUtils.setField(t, "queryGateEventRecorder", queryGateEventRecorder);
        ReflectionTestUtils.setField(t, "vectorResultChars", vectorResultChars);
        ReflectionTestUtils.setField(t, "metadataResultChars", metadataResultChars);
        ReflectionTestUtils.setField(t, "entryResultChars", 8000);
        ReflectionTestUtils.setField(t, "metadataDefaultLimit", 50);
        ReflectionTestUtils.setField(t, "gapsListDefaultLimit", 20);
        return t;
    }

    private Document spellDoc(String title, Map<String, Object> meta) {
        return Document.builder().text("正文内容").metadata(meta).build();
    }

    // ---------- searchByMetadata ----------
}
