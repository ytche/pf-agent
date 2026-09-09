package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.mockito.ArgumentCaptor;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
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

    @Mock
    private SearchService searchService;
    @Mock
    private SourceCollector collector;
    @Mock
    private DataGapRecorder recorder;
    @Mock
    private SpellListService spellListService;

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

        assertThat(result).contains("结果过多", "收窄过滤");
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

    /** reportDataGap 记录缺口并标记 gap */
    @Test
    void reportDataGapRecordsAndMarksGap() {
        String result = tools(1500).reportDataGap("女巫的XX变体规则", "{className:女巫}", "查不到该变体");

        verify(recorder).record("女巫的XX变体规则", "{className:女巫}", "查不到该变体");
        verify(collector).markGapReported();
        assertThat(result).contains("已记录");
    }

    // ---------- getSpellList（SP3 F-007） ----------

    /** 别名归一命中：resolve 归一到规范职业，formatLevel 输出紧凑清单，列表页挂溯源 */
    @Test
    void getSpellListAliasResolvesAndCollectsListPage() {
        when(spellListService.isAvailable()).thenReturn(true);
        when(spellListService.resolve("诗人")).thenReturn("吟游诗人");
        when(spellListService.formatLevel("吟游诗人", 2, 100000))
                .thenReturn("「吟游诗人」2 环法术（共 1 条）：\n1. 移除恐惧（Remove Fear） [CRB]");
        Document listPage = Document.builder().text("吟游诗人法术列表")
                .metadata(Map.of("title", "吟游诗人法术列表", "tocPath", "职业 → 核心职业 → 吟游诗人 → 法术列表"))
                .build();
        when(spellListService.listPageDocument("吟游诗人")).thenReturn(listPage);
        stubAddSequential();

        String result = tools(1500).getSpellList("诗人", 2);

        assertThat(result).contains("「吟游诗人」2 环法术", "移除恐惧");
        assertThat(result).contains("本清单来源 [#1]");   // SP4 D2：清单末尾单来源编号
        // 别名归一后按规范名查询，而非原输入
        verify(spellListService).formatLevel("吟游诗人", 2, 100000);
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

        String result = tools(1500).getSpellList("死灵法师", 1);

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

        String result = tools(1500).getSpellList("法师", null);

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

        String result = tools(1500).getSpellList("法师", 12);

        assertThat(result).contains("环级须在 0~9 之间", "823 条");
        assertThat(result).contains("本清单来源 [#1]");   // 越界提示后仍挂概览来源
        verify(spellListService, never()).formatLevel(anyString(), anyInt(), anyInt());
    }

    /** className 为空：提示提供职业名，不收集 */
    @Test
    void getSpellListBlankClassNamePromptsForClass() {
        when(spellListService.isAvailable()).thenReturn(true);
        when(spellListService.knownClasses()).thenReturn(List.of("法师", "吟游诗人"));

        String result = tools(1500).getSpellList("   ", 1);

        assertThat(result).contains("请提供职业名", "法师", "吟游诗人");
        verify(spellListService, never()).resolve(anyString());
        verifyNoInteractions(collector);
    }

    /** 清单不可用（数据文件未加载）：返回提示且零查询/零收集 */
    @Test
    void getSpellListUnavailableReturnsHintWithoutQuery() {
        when(spellListService.isAvailable()).thenReturn(false);

        String result = tools(1500).getSpellList("法师", 1);

        assertThat(result).contains("不可用", "searchByMetadata");
        verify(spellListService, never()).resolve(anyString());
        verify(spellListService, never()).formatLevel(anyString(), anyInt(), anyInt());
        verifyNoInteractions(collector);
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

    private RetrievalTools tools(int vectorResultChars, int metadataResultChars) {
        RetrievalTools t = new RetrievalTools();
        ReflectionTestUtils.setField(t, "searchService", searchService);
        ReflectionTestUtils.setField(t, "collector", collector);
        ReflectionTestUtils.setField(t, "recorder", recorder);
        ReflectionTestUtils.setField(t, "filterTranslator", new FilterTranslator());
        ReflectionTestUtils.setField(t, "spellListService", spellListService);
        ReflectionTestUtils.setField(t, "vectorResultChars", vectorResultChars);
        ReflectionTestUtils.setField(t, "metadataResultChars", metadataResultChars);
        return t;
    }

    private Document spellDoc(String title, Map<String, Object> meta) {
        return Document.builder().text("正文内容").metadata(meta).build();
    }

    // ---------- searchByMetadata ----------
}
