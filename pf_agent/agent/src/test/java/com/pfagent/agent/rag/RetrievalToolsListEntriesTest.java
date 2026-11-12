package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import com.pfagent.agent.telemetry.QueryGateEventService.Reason;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * listEntries 工具边界测试（B4）
 *
 * 覆盖方案验收要点：
 *  - 未知模块返回可用模块清单；模块未加载返回降级提示
 *  - 无条件（query null / 全 null）返回统计概览
 *  - filters 字段名非法返回该模块可用字段清单；sortBy 非法返回可用值
 *  - limit>200 钳制为 200 并在返回头部注明；limit<1 钳制为 1
 *  - 无命中返回回退引导（放宽/转 vectorSearch，不 reportDataGap）；offset 越界提示翻页
 *  - 有条件：逐行格式 + 来源编号 [#N]；截断时截断行不挂编号并提示翻页
 *  - 溯源：展示的条目经 provenanceDocuments 点查进 SourceCollector
 */
@ExtendWith(MockitoExtension.class)
class RetrievalToolsListEntriesTest {

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
    private ListExportService listExportService;
    @Mock
    private QueryGateEventRecorder queryGateEventRecorder;

    /** AKN-024：会话级放行指纹（同测试内多次 tools() 调用共享） */
    private final ToolCallTracker toolCallTracker = new ToolCallTracker();
    private final BroadQueryAllowanceRegistry allowanceRegistry = new BroadQueryAllowanceRegistry();

    @Test
    void unknownModuleReturnsAvailableModules() {
        String result = tools().listEntries("spell", null);

        assertThat(result).contains("未知模块", "feat(专长)/race(种族)/equipment(装备)");
    }

    @Test
    void nullModuleReturnsAvailableModules() {
        String result = tools().listEntries(null, null);

        assertThat(result).contains("未知模块");
    }

    @Test
    void unavailableModuleReturnsDegradationHint() {
        when(listExportService.isAvailable("feat")).thenReturn(false);

        String result = tools().listEntries("feat", null);

        assertThat(result).contains("暂不可用", "feat_lists.json 未加载", "searchByMetadata");
    }

    @Test
    void noConditionReturnsOverview() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.overview("feat")).thenReturn("「专长」权威清单共 4080 条");

        String result = tools().listEntries("feat", null);

        assertThat(result).isEqualTo("「专长」权威清单共 4080 条");
    }

    @Test
    void blankQueryReturnsOverview() {
        when(listExportService.isAvailable("race")).thenReturn(true);
        when(listExportService.overview("race")).thenReturn("「种族」权威清单共 111 条");

        String result = tools().listEntries("race", new ListEntriesQuery(null, null, null, null, null, null));

        assertThat(result).isEqualTo("「种族」权威清单共 111 条");
        // 轻量概览不记门禁事件
        verifyNoInteractions(queryGateEventRecorder);
    }

    // ---------- F-026 宽查询门禁 ----------

    /** 仅分页/排序参数按无业务条件处理：未放行仍返回概览，不检索、不记事件 */
    @Test
    void paginationOnlyQueryReturnsOverviewWithoutSearchOrEvent() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.overview("feat")).thenReturn("「专长」权威清单共 4080 条");

        String result = tools().listEntries("feat",
                new ListEntriesQuery(null, null, null, 10, 20, "book"));

        assertThat(result).isEqualTo("「专长」权威清单共 4080 条");
        verify(listExportService, never()).search(any(), any(), anyInt(), anyInt());
        verifyNoInteractions(queryGateEventRecorder);
    }

    /** 无业务条件 + allowBroadQuery=true：记录 ALLOWED(no_conditions) 并执行无条件分页查询 */
    @Test
    void noConditionsAllowedExecutesUnconditionalSearchAndRecordsAllowed() {
        ListEntriesQuery query = new ListEntriesQuery(null, null, null, null, null, null, true);
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.search(eq("feat"), eq(query), eq(50), eq(0)))
                .thenReturn(page(List.of(), 0));

        String result = tools().listEntries("feat", query);

        assertThat(result).contains("无命中");
        verify(listExportService, never()).overview("feat");
        verify(queryGateEventRecorder).recordAllowed("listEntries", "feat", Reason.NO_CONDITIONS, query);
        verify(queryGateEventRecorder, never()).recordBlocked(any(), any(), any(), any());
    }

    /** 仅书条件未放行：不执行条目检索，返回护栏建议并记录 BLOCKED(book_only) */
    @Test
    void bookOnlyWithoutAllowIsBlockedAndRecordsBlocked() {
        ListEntriesQuery query = new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null);
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.availableFilterFields("feat"))
                .thenReturn(List.of("featType", "book", "hasPrerequisites"));

        String result = tools().listEntries("feat", query);

        assertThat(result).contains("宽查询护栏", "未执行条目检索", "book_only", "allowBroadQuery=true");
        assertThat(result).contains("featType", "数量概览");
        verify(listExportService, never()).search(any(), any(), anyInt(), anyInt());
        verify(queryGateEventRecorder).recordBlocked("listEntries", "feat", Reason.BOOK_ONLY, query);
    }

    /** 多书 OR 同样属于仅书形态：未放行拦截 */
    @Test
    void multiBookOrWithoutAllowIsBlocked() {
        ListEntriesQuery query = new ListEntriesQuery(null, null,
                Map.of("book", List.of("CRB", "APG")), null, null, null);
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.availableFilterFields("feat")).thenReturn(List.of("featType", "book"));

        String result = tools().listEntries("feat", query);

        assertThat(result).contains("宽查询护栏", "book_only");
        verify(listExportService, never()).search(any(), any(), anyInt(), anyInt());
    }

    /** 仅书 + allowBroadQuery=true：放行执行并记录 ALLOWED(book_only) */
    @Test
    void bookOnlyAllowedExecutesAndRecordsAllowed() {
        ListExportService.ListEntry dodge = entry("闪避");
        ListEntriesQuery query = new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null, true);
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.search(eq("feat"), eq(query), eq(50), eq(0)))
                .thenReturn(page(List.of(dodge), 1));
        when(listExportService.entryLine(eq("feat"), eq(1), eq(dodge), eq(true)))
                .thenReturn("1. 闪避（Dodge）[CRB] | 类别:战斗 | chunk_id: c1");
        when(listExportService.provenanceDocuments("feat", List.of(dodge)))
                .thenReturn(List.of(Document.builder().text("t").metadata(Map.of("title", "闪避")).build()));
        when(collector.add(any())).thenReturn(List.of(1));

        String result = tools().listEntries("feat", query);

        assertThat(result).contains("1. 闪避（Dodge）[CRB]");
        verify(queryGateEventRecorder).recordAllowed("listEntries", "feat", Reason.BOOK_ONLY, query);
    }

    /** keyword-only 是有效业务条件：不触发门禁、不记事件 */
    @Test
    void keywordOnlyQuerySkipsGateAndRecordsNothing() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.search(eq("feat"), any(), eq(50), eq(0)))
                .thenReturn(page(List.of(), 0));

        String result = tools().listEntries("feat",
                new ListEntriesQuery("火球", null, null, null, null, null));

        assertThat(result).contains("无命中");
        verifyNoInteractions(queryGateEventRecorder);
    }

    /** 参数校验先于门禁：非法排序即使 allowBroadQuery=true 也返回校验错误且无事件 */
    @Test
    void invalidSortBeforeGateProducesNoEvent() {
        ListEntriesQuery query = new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, "price", true);
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());

        String result = tools().listEntries("feat", query);

        assertThat(result).contains("未知排序字段: price");
        verify(listExportService, never()).search(any(), any(), anyInt(), anyInt());
        verifyNoInteractions(queryGateEventRecorder);
    }

    @Test
    void unknownFilterFieldReturnsAvailableFields() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any()))
                .thenReturn(java.util.Set.of("slot"));
        when(listExportService.availableFilterFields("feat"))
                .thenReturn(List.of("featType", "book", "hasPrerequisites"));

        String result = tools().listEntries("feat",
                new ListEntriesQuery(null, Map.of("slot", "手部"), null, null, null, null));

        assertThat(result).contains("未知过滤字段", "[featType, book, hasPrerequisites]");
    }

    @Test
    void unknownSortByReturnsAvailableValues() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());

        String result = tools().listEntries("feat",
                new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, "price"));

        assertThat(result).contains("未知排序字段: price", "[name, book]");
    }

    /** B4-QA-1：hasPrerequisites 传非布尔值（"yes"/"1"）返回自纠提示，不再静默落入 false 分支 */
    @Test
    void nonBooleanHasPrerequisitesReturnsSelfCorrectionHint() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());

        String result = tools().listEntries("feat",
                new ListEntriesQuery(null, Map.of("hasPrerequisites", "yes"), null, null, null, null));

        assertThat(result).contains("非法过滤值: hasPrerequisites", "可用值: [\"true\", \"false\"]");
    }

    /** B4-QA-1：orFilters.hasPrerequisites 组内混入非法值同样自纠 */
    @Test
    void nonBooleanHasPrerequisitesInOrFiltersReturnsHint() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());

        String result = tools().listEntries("feat",
                new ListEntriesQuery(null, null, Map.of("hasPrerequisites", List.of("true", "1")), null, null, null));

        assertThat(result).contains("非法过滤值: hasPrerequisites", "[\"true\", \"false\"]");
    }

    /** B4-QA-1："true"/"false"（含大小写变体）仍为合法值，不走自纠分支 */
    @Test
    void booleanHasPrerequisitesPassesValidation() {
        ListExportService.ListEntry dodge = entry("闪避");
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.search(eq("feat"), any(), eq(50), eq(0)))
                .thenReturn(page(List.of(dodge), 1));
        when(listExportService.entryLine(eq("feat"), eq(1), eq(dodge), eq(true)))
                .thenReturn("1. 闪避（Dodge）[CRB] | 类别:战斗 | chunk_id: c1");
        when(listExportService.provenanceDocuments("feat", List.of(dodge)))
                .thenReturn(List.of(Document.builder().text("t").metadata(Map.of("title", "闪避")).build()));
        when(collector.add(any())).thenReturn(List.of(1));

        String result = tools().listEntries("feat",
                new ListEntriesQuery(null, Map.of("hasPrerequisites", "TRUE"), null, null, null, null));

        assertThat(result).contains("1. 闪避（Dodge）[CRB]");
        assertThat(result).doesNotContain("非法过滤值");
    }

    /** B4-QA-2：filters 空串过滤值返回自纠提示，不再静默匹配空字段 */
    @Test
    void blankFilterValueReturnsSelfCorrectionHint() {
        when(listExportService.isAvailable("race")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("race"), any())).thenReturn(java.util.Set.of());

        String result = tools().listEntries("race",
                new ListEntriesQuery(null, Map.of("size", ""), null, null, null, null));

        assertThat(result).contains("过滤值为空: [size]", "非空过滤值");
    }

    /** B4-QA-2：orFilters 组内空串值同样自纠 */
    @Test
    void blankOrFilterValueReturnsSelfCorrectionHint() {
        when(listExportService.isAvailable("race")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("race"), any())).thenReturn(java.util.Set.of());

        String result = tools().listEntries("race", new ListEntriesQuery(null, null,
                Map.of("raceGroup", List.of("元素", " ")), null, null, null));

        assertThat(result).contains("过滤值为空: [raceGroup]");
    }

    /** B4-QA-3：offset 为负钳制为 0 并在头部注明（与 limit 钳制注记风格一致） */
    @Test
    void negativeOffsetIsClampedToZeroAndNoted() {
        ListExportService.ListEntry dodge = entry("闪避");
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.search(eq("feat"), any(), eq(50), eq(0)))
                .thenReturn(page(List.of(dodge), 1));
        when(listExportService.entryLine(eq("feat"), eq(1), eq(dodge), eq(true)))
                .thenReturn("1. 闪避（Dodge）[CRB] | 类别:战斗 | chunk_id: c1");
        when(listExportService.provenanceDocuments("feat", List.of(dodge)))
                .thenReturn(List.of(Document.builder().text("t").metadata(Map.of("title", "闪避")).build()));
        when(collector.add(any())).thenReturn(List.of(1));

        String result = tools().listEntries("feat",
                new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, -5, null, true));

        assertThat(result).startsWith("（offset 为负，已钳制为 0）\n");
        assertThat(result).contains("1. 闪避（Dodge）[CRB]");
    }

    @Test
    void limitAboveMaxIsClampedAndNoted() {
        ListExportService.ListEntry dodge = entry("闪避");
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.search(eq("feat"), any(), eq(200), eq(0)))
                .thenReturn(page(List.of(dodge), 1));
        when(listExportService.entryLine(eq("feat"), eq(1), eq(dodge), eq(true)))
                .thenReturn("1. 闪避（Dodge）[CRB] | 类别:战斗 | chunk_id: c1");
        when(listExportService.provenanceDocuments("feat", List.of(dodge)))
                .thenReturn(List.of(Document.builder().text("t").metadata(Map.of("title", "闪避")).build()));
        when(collector.add(any())).thenReturn(List.of(1));

        String result = tools().listEntries("feat",
                new ListEntriesQuery(null, Map.of("book", "CRB"), null, 999, null, null, true));

        assertThat(result).startsWith("（limit 超出上限，已钳制为 200）");
    }

    @Test
    void limitBelowOneIsClampedAndNoted() {
        ListExportService.ListEntry dodge = entry("闪避");
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.search(eq("feat"), any(), eq(1), eq(0)))
                .thenReturn(page(List.of(dodge), 5));
        when(listExportService.entryLine(eq("feat"), eq(1), eq(dodge), eq(true)))
                .thenReturn("1. 闪避（Dodge）[CRB] | 类别:战斗 | chunk_id: c1");
        when(listExportService.provenanceDocuments("feat", List.of(dodge)))
                .thenReturn(List.of(Document.builder().text("t").metadata(Map.of("title", "闪避")).build()));
        when(collector.add(any())).thenReturn(List.of(1));

        String result = tools().listEntries("feat",
                new ListEntriesQuery(null, Map.of("book", "CRB"), null, 0, null, null, true));

        assertThat(result).startsWith("（limit 小于 1，已钳制为 1）");
    }

    @Test
    void noHitReturnsFallbackHint() {
        when(listExportService.isAvailable("race")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("race"), any())).thenReturn(java.util.Set.of());
        when(listExportService.search(eq("race"), any(), anyInt(), anyInt()))
                .thenReturn(page(List.of(), 0));

        String result = tools().listEntries("race",
                new ListEntriesQuery("不存在的东西", null, null, null, null, null));

        assertThat(result).contains("无命中", "放宽过滤条件", "vectorSearch", "reportDataGap");
    }

    @Test
    void offsetOverflowReturnsPaginationHint() {
        when(listExportService.isAvailable("equipment")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("equipment"), any())).thenReturn(java.util.Set.of());
        when(listExportService.search(eq("equipment"), any(), anyInt(), eq(100)))
                .thenReturn(page(List.of(), 2675));

        String result = tools().listEntries("equipment",
                new ListEntriesQuery(null, Map.of("componentType", "gear"), null, 50, 100, null));

        assertThat(result).contains("offset=100 越界", "共 2675 条", "请减小 offset");
    }

    @Test
    void conditionalQueryReturnsLinesWithSourceTags() {
        ListExportService.ListEntry dodge = entry("闪避");
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.search(eq("feat"), any(), eq(50), eq(0)))
                .thenReturn(page(List.of(dodge), 1));
        when(listExportService.entryLine(eq("feat"), eq(1), eq(dodge), eq(true)))
                .thenReturn("1. 闪避（Dodge）[CRB] | 类别:战斗 | chunk_id: feat_page_1_0001");
        Document doc = Document.builder().text("t").metadata(Map.of("title", "闪避")).build();
        when(listExportService.provenanceDocuments("feat", List.of(dodge))).thenReturn(List.of(doc));
        when(collector.add(any())).thenReturn(List.of(3));

        String result = tools().listEntries("feat",
                new ListEntriesQuery(null, Map.of("featType", "战斗"), null, null, null, null));

        assertThat(result).isEqualTo("1. 闪避（Dodge）[CRB] | 类别:战斗 | chunk_id: feat_page_1_0001 [#3]\n");
        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<Document>> captor = ArgumentCaptor.forClass(List.class);
        verify(collector).add(captor.capture());
        assertThat(captor.getValue()).containsExactly(doc);
    }

    @Test
    void truncatedResultOmitsTagsOnTruncatedLinesAndHintsPagination() {
        ListExportService.ListEntry first = entry("条目一");
        ListExportService.ListEntry second = entry("条目二");
        ListExportService.ListEntry third = entry("条目三");
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.search(eq("feat"), any(), eq(50), eq(0)))
                .thenReturn(page(List.of(first, second, third), 3));
        when(listExportService.entryLine(eq("feat"), eq(1), eq(first), eq(true)))
                .thenReturn("1. 条目一（A）[CRB] | 类别:战斗 | chunk_id: c1");
        when(listExportService.entryLine(eq("feat"), eq(2), eq(second), eq(true)))
                .thenReturn("2. 条目二（B）[CRB] | 类别:战斗 | chunk_id: c2");
        Document doc1 = Document.builder().text("t").metadata(Map.of("title", "条目一")).build();
        // 字符预算只容下第一行：第二行超预算截断，截断行不挂 [#N]、不进溯源点查
        when(listExportService.provenanceDocuments("feat", List.of(first))).thenReturn(List.of(doc1));
        when(collector.add(any())).thenReturn(List.of(1));

        String result = toolsWithSmallBudget().listEntries("feat",
                new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null, true));

        assertThat(result).contains("1. 条目一（A）[CRB] | 类别:战斗 | chunk_id: c1 [#1]\n");
        assertThat(result).contains("结果过多，仅展示前 1 条 / 共 3 条命中", "offset 翻页");
        assertThat(result).doesNotContain("条目二", "条目三", "[#2]", "[#3]");
        verify(listExportService, never()).provenanceDocuments(eq("feat"), eq(List.of(second)));
    }

    // ---------- AKN-025 price 排序 ----------

    /** equipment 开放 price 排序（映射 price_gp），desc 可用；不再报未知排序字段 */
    @Test
    void equipmentPriceSortIsAccepted() {
        when(listExportService.isAvailable("equipment")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("equipment"), any())).thenReturn(java.util.Set.of());
        when(listExportService.hasPriceData("equipment")).thenReturn(true);
        when(listExportService.search(eq("equipment"), any(), eq(50), eq(0))).thenReturn(page(List.of(), 0));

        String result = tools().listEntries("equipment",
                new ListEntriesQuery(null, Map.of("price_min", "1"), null, null, null, "price", null, "desc"));

        assertThat(result).contains("无命中");
        verify(listExportService).search(eq("equipment"), any(), eq(50), eq(0));
    }

    /** feat 模块不开放 price 排序（保持原可用值） */
    @Test
    void featPriceSortStillRejected() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());

        String result = tools().listEntries("feat",
                new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, "price"));

        assertThat(result).contains("未知排序字段: price", "[name, book]");
        verify(listExportService, never()).search(any(), any(), anyInt(), anyInt());
    }

    /** 旧版清单无 price_gp：拒绝 price 排序并提示，不静默给出错误排序 */
    @Test
    void legacyEquipmentWithoutPriceGpRejectsPriceSortWithHint() {
        when(listExportService.isAvailable("equipment")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("equipment"), any())).thenReturn(java.util.Set.of());
        when(listExportService.hasPriceData("equipment")).thenReturn(false);

        String result = tools().listEntries("equipment",
                new ListEntriesQuery(null, null, null, null, null, "price"));

        assertThat(result).contains("price_gp", "旧版", "不支持");
        verify(listExportService, never()).search(any(), any(), anyInt(), anyInt());
    }

    @Test
    void invalidSortOrderReturnsAvailableValues() {
        when(listExportService.isAvailable("equipment")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("equipment"), any())).thenReturn(java.util.Set.of());

        String result = tools().listEntries("equipment",
                new ListEntriesQuery(null, null, null, null, null, "price", null, "sideways"));

        assertThat(result).contains("未知排序方向: sideways", "[asc, desc]");
        verify(listExportService, never()).search(any(), any(), anyInt(), anyInt());
    }

    @Test
    void nonNumericPriceRangeReturnsHint() {
        when(listExportService.isAvailable("equipment")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("equipment"), any())).thenReturn(java.util.Set.of());

        String result = tools().listEntries("equipment",
                new ListEntriesQuery(null, Map.of("price_min", "便宜"), null, null, null, null));

        assertThat(result).contains("price_min", "整数", "gp");
        verify(listExportService, never()).search(any(), any(), anyInt(), anyInt());
    }

    // ---------- AKN-024 会话级放行指纹 ----------

    /** 同会话同 module+book：首次拦截记录指纹，后续 allow=true 放行；换书驳回并更新指纹 */
    @Test
    void fingerprintAllowsSameModuleAndBookAndRejectsChangedBook() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.availableFilterFields("feat")).thenReturn(List.of("featType", "book"));
        when(listExportService.search(eq("feat"), any(), eq(50), eq(0))).thenReturn(page(List.of(), 0));
        toolCallTracker.begin("cid-fp-book", "CRB 所有专长");

        ListEntriesQuery initial = new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null);
        assertThat(tools().listEntries("feat", initial)).contains("宽查询护栏");

        // 后续用户轮次确认原范围（新 requestId）才放行
        toolCallTracker.begin("cid-fp-book", "仍按 CRB 原范围查询");
        ListEntriesQuery same = new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null, true);
        assertThat(tools().listEntries("feat", same)).contains("无命中");
        verify(listExportService, times(1)).search(eq("feat"), any(), eq(50), eq(0));

        ListEntriesQuery changedBook = new ListEntriesQuery(null, Map.of("book", "APG"), null, null, null, null, true);
        assertThat(tools().listEntries("feat", changedBook)).contains("宽查询护栏");
        verify(listExportService, times(1)).search(eq("feat"), any(), eq(50), eq(0));
        verify(queryGateEventRecorder).recordBlocked("listEntries", "feat", Reason.FINGERPRINT_MISMATCH, changedBook);
    }

    /** AKN-024 同轮重试：驳回后同一 requestId 内再次 allow=true 不得自我放行，后续用户轮次才放行 */
    @Test
    void fingerprintRejectsSameRequestRetryAndAllowsOnlyNextTurn() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.availableFilterFields("feat")).thenReturn(List.of("book"));
        when(listExportService.search(eq("feat"), any(), eq(50), eq(0))).thenReturn(page(List.of(), 0));
        toolCallTracker.begin("cid-fp-retry", "CRB 所有专长");

        tools().listEntries("feat", new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null));

        ListEntriesQuery retry = new ListEntriesQuery(
                null, Map.of("book", "CRB"), null, null, null, null, true);
        assertThat(tools().listEntries("feat", retry)).contains("宽查询护栏");
        verify(listExportService, never()).search(any(), any(), anyInt(), anyInt());
        verify(queryGateEventRecorder)
                .recordBlocked("listEntries", "feat", Reason.FINGERPRINT_MISMATCH, retry);

        // 同一 requestId 再试一次仍不得放行（模型重试不等于用户确认）
        assertThat(tools().listEntries("feat", retry)).contains("宽查询护栏");
        verify(listExportService, never()).search(any(), any(), anyInt(), anyInt());

        // 后续用户轮次（新 requestId）携带一致指纹才放行
        toolCallTracker.begin("cid-fp-retry", "仍按 CRB 原范围查询");
        assertThat(tools().listEntries("feat", retry)).doesNotContain("宽查询护栏");
        verify(listExportService, times(1)).search(eq("feat"), any(), eq(50), eq(0));
    }

    /** AKN-024 换模块：同轮重试不得自我放行，下一用户轮次确认新模块后才放行 */
    @Test
    void fingerprintRejectsSameRequestModuleSwitchRetryUntilNextTurn() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.isAvailable("equipment")).thenReturn(true);
        when(listExportService.unknownFilterFields(any(), any())).thenReturn(java.util.Set.of());
        when(listExportService.availableFilterFields(any())).thenReturn(List.of("book"));
        when(listExportService.search(eq("equipment"), any(), eq(50), eq(0))).thenReturn(page(List.of(), 0));
        toolCallTracker.begin("cid-fp-switch", "CRB 所有专长");

        tools().listEntries("feat", new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null));

        ListEntriesQuery equipment = new ListEntriesQuery(
                null, Map.of("book", "CRB"), null, null, null, null, true);
        assertThat(tools().listEntries("equipment", equipment)).contains("宽查询护栏");
        // 同一 requestId 内重试同一新模块：指纹虽已更新，但仍属同轮自我放行
        assertThat(tools().listEntries("equipment", equipment)).contains("宽查询护栏");
        verify(listExportService, never()).search(any(), any(), anyInt(), anyInt());

        toolCallTracker.begin("cid-fp-switch", "仍按 CRB 查装备清单");
        assertThat(tools().listEntries("equipment", equipment)).doesNotContain("宽查询护栏");
        verify(listExportService, times(1)).search(eq("equipment"), any(), eq(50), eq(0));
    }

    /** AKN-024 regenerate：没有新用户确认，不得凭新 requestId 放行待确认指纹 */
    @Test
    void regenerateCannotConfirmPendingFingerprint() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.availableFilterFields("feat")).thenReturn(List.of("book"));
        when(listExportService.search(eq("feat"), any(), eq(50), eq(0))).thenReturn(page(List.of(), 0));
        toolCallTracker.begin("cid-fp-regen", "CRB 所有专长");

        tools().listEntries("feat", new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null));

        ListEntriesQuery retry = new ListEntriesQuery(
                null, Map.of("book", "CRB"), null, null, null, null, true);
        toolCallTracker.beginRegenerate("cid-fp-regen", "CRB 所有专长");
        assertThat(tools().listEntries("feat", retry)).contains("宽查询护栏");
        // 再次 regenerate：requestId 又变了，但依然没有新用户轮次
        toolCallTracker.beginRegenerate("cid-fp-regen", "CRB 所有专长");
        assertThat(tools().listEntries("feat", retry)).contains("宽查询护栏");
        verify(listExportService, never()).search(any(), any(), anyInt(), anyInt());

        // 真实新用户轮次才可确认
        toolCallTracker.begin("cid-fp-regen", "仍按 CRB 原范围查询");
        assertThat(tools().listEntries("feat", retry)).doesNotContain("宽查询护栏");
        verify(listExportService, times(1)).search(eq("feat"), any(), eq(50), eq(0));
    }

    /** AKN-024 regenerate：已由真实用户轮次确认的边界可以沿用，不重复拦截 */
    @Test
    void regenerateContinuesPreviouslyConfirmedFingerprint() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.availableFilterFields("feat")).thenReturn(List.of("book"));
        when(listExportService.search(eq("feat"), any(), eq(50), eq(0))).thenReturn(page(List.of(), 0));
        ListEntriesQuery allowed = new ListEntriesQuery(
                null, Map.of("book", "CRB"), null, null, null, null, true);
        toolCallTracker.begin("cid-fp-regen-ok", "CRB 所有专长");
        tools().listEntries("feat", new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null));

        toolCallTracker.begin("cid-fp-regen-ok", "仍按 CRB 原范围查询");
        assertThat(tools().listEntries("feat", allowed)).doesNotContain("宽查询护栏");

        toolCallTracker.beginRegenerate("cid-fp-regen-ok", "CRB 所有专长");
        assertThat(tools().listEntries("feat", allowed)).doesNotContain("宽查询护栏");

        verify(listExportService, times(2)).search(eq("feat"), any(), eq(50), eq(0));
        verify(queryGateEventRecorder, never())
                .recordBlocked(eq("listEntries"), eq("feat"), eq(Reason.FINGERPRINT_MISMATCH), any());
    }

    /** 同会话换模块驳回（fingerprint 只按 module+book） */
    @Test
    void fingerprintRejectsChangedModule() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.isAvailable("equipment")).thenReturn(true);
        when(listExportService.unknownFilterFields(any(), any())).thenReturn(java.util.Set.of());
        when(listExportService.availableFilterFields(any()))
                .thenReturn(List.of("book"));
        toolCallTracker.begin("cid-fp-module", "CRB 所有专长");

        tools().listEntries("feat", new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null));
        ListEntriesQuery equipment = new ListEntriesQuery(
                null, Map.of("book", "CRB"), null, null, null, null, true);

        assertThat(tools().listEntries("equipment", equipment)).contains("宽查询护栏");
        verify(listExportService, never()).search(eq("equipment"), any(), anyInt(), anyInt());
        verify(queryGateEventRecorder)
                .recordBlocked("listEntries", "equipment", Reason.FINGERPRINT_MISMATCH, equipment);
    }

    /** 同条件翻页（offset 不同）仍放行：offset/limit/sort 不参与指纹 */
    @Test
    void fingerprintAllowsSameConditionPagination() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.search(eq("feat"), any(), eq(50), anyInt())).thenReturn(page(List.of(), 0));
        toolCallTracker.begin("cid-fp-page", "CRB 所有专长");

        tools().listEntries("feat", new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null));

        // 用户确认后的后续轮次：同条件翻页（新 requestId）仍放行
        toolCallTracker.begin("cid-fp-page", "仍按 CRB 原范围继续翻页");
        tools().listEntries("feat", new ListEntriesQuery(
                null, Map.of("book", "CRB"), null, 50, 0, "book", true, "desc"));
        tools().listEntries("feat", new ListEntriesQuery(
                null, Map.of("book", "CRB"), null, 50, 50, "name", true, "asc"));

        verify(listExportService, times(2)).search(eq("feat"), any(), eq(50), anyInt());
        verify(queryGateEventRecorder, never())
                .recordBlocked(eq("listEntries"), eq("feat"), eq(Reason.FINGERPRINT_MISMATCH), any());
    }

    /** 无会话上下文：不保存也不校验指纹，沿用 allowBroadQuery 声明（与 F-026 一致） */
    @Test
    void fingerprintWithoutRequestContextFallsBackToDeclaredAllowance() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.search(eq("feat"), any(), eq(50), eq(0))).thenReturn(page(List.of(), 0));

        ListEntriesQuery query = new ListEntriesQuery(
                null, Map.of("book", "CRB"), null, null, null, null, true);

        assertThat(tools().listEntries("feat", query)).contains("无命中");
        verify(queryGateEventRecorder)
                .recordAllowed("listEntries", "feat", Reason.BOOK_ONLY, query);
    }

    /** 指纹按会话隔离：另一会话的同 module+book 不能沿用 */
    @Test
    void fingerprintIsIsolatedPerConversation() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.availableFilterFields("feat")).thenReturn(List.of("book"));
        toolCallTracker.begin("cid-fp-a", "CRB 所有专长");
        tools().listEntries("feat", new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null));

        toolCallTracker.begin("cid-fp-b", "新会话");
        ListEntriesQuery query = new ListEntriesQuery(
                null, Map.of("book", "CRB"), null, null, null, null, true);

        assertThat(tools().listEntries("feat", query)).contains("宽查询护栏");
        verify(listExportService, never()).search(any(), any(), anyInt(), anyInt());
    }

    /** 首次无条件查询返回概览时记录空书指纹，同会话后续放行不受影响 */
    @Test
    void fingerprintRecordsNoConditionOverviewForLaterAllowance() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.overview("feat")).thenReturn("「专长」权威清单共 4080 条");
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.search(eq("feat"), any(), eq(50), eq(0))).thenReturn(page(List.of(), 0));
        toolCallTracker.begin("cid-fp-empty", "全部专长");

        assertThat(tools().listEntries("feat", new ListEntriesQuery(null, null, null, null, null, null)))
                .isEqualTo("「专长」权威清单共 4080 条");
        ListEntriesQuery allowed = new ListEntriesQuery(null, null, null, null, null, null, true);

        toolCallTracker.begin("cid-fp-empty", "仍按原范围查询");
        assertThat(tools().listEntries("feat", allowed)).contains("无命中");
        verify(queryGateEventRecorder)
                .recordAllowed("listEntries", "feat", Reason.NO_CONDITIONS, allowed);
    }

    /** query==null 首次概览同样记录空书指纹：同会话空条件 allow=true 应直接放行（不多一次往返） */
    @Test
    void fingerprintRecordsNullQueryOverviewForLaterAllowance() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.overview("feat")).thenReturn("「专长」权威清单共 4080 条");
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.search(eq("feat"), any(), eq(50), eq(0))).thenReturn(page(List.of(), 0));
        toolCallTracker.begin("cid-fp-null", "全部专长");

        assertThat(tools().listEntries("feat", null)).isEqualTo("「专长」权威清单共 4080 条");
        // 普通概览仍是轻量响应，不写门禁事件
        verifyNoInteractions(queryGateEventRecorder);

        ListEntriesQuery allowed = new ListEntriesQuery(null, null, null, null, null, null, true);
        toolCallTracker.begin("cid-fp-null", "仍按原范围查询");
        assertThat(tools().listEntries("feat", allowed)).contains("无命中");
        verify(queryGateEventRecorder)
                .recordAllowed("listEntries", "feat", Reason.NO_CONDITIONS, allowed);
    }

    /** 已有 module+book 指纹后切到无条件 allow=true：mismatch 必须记 BLOCKED 事件，再返回概览 */
    @Test
    void fingerprintMismatchFromBookToNoConditionsRecordsBlocked() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any())).thenReturn(java.util.Set.of());
        when(listExportService.availableFilterFields("feat")).thenReturn(List.of("book"));
        when(listExportService.overview("feat")).thenReturn("「专长」权威清单共 4080 条");
        toolCallTracker.begin("cid-fp-to-empty", "CRB 所有专长");

        tools().listEntries("feat", new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null));
        ListEntriesQuery noConditions = new ListEntriesQuery(null, null, null, null, null, null, true);

        assertThat(tools().listEntries("feat", noConditions)).isEqualTo("「专长」权威清单共 4080 条");
        verify(queryGateEventRecorder)
                .recordBlocked("listEntries", "feat", Reason.FINGERPRINT_MISMATCH, noConditions);
    }

    private RetrievalTools tools() {
        return toolsWithBudget(4000);
    }

    private RetrievalTools toolsWithSmallBudget() {
        // 预算只容下第一行（36 字符 + 换行），第二行起截断
        return toolsWithBudget(50);
    }

    private RetrievalTools toolsWithBudget(int metadataResultChars) {
        RetrievalTools tools = new RetrievalTools();
        ReflectionTestUtils.setField(tools, "searchService", searchService);
        ReflectionTestUtils.setField(tools, "collector", collector);
        ReflectionTestUtils.setField(tools, "recorder", recorder);
        ReflectionTestUtils.setField(tools, "spellListService", spellListService);
        ReflectionTestUtils.setField(tools, "classTableService", classTableService);
        ReflectionTestUtils.setField(tools, "listExportService", listExportService);
        ReflectionTestUtils.setField(tools, "queryGateEventRecorder", queryGateEventRecorder);
        ReflectionTestUtils.setField(tools, "toolCallTracker", toolCallTracker);
        ReflectionTestUtils.setField(tools, "broadQueryAllowanceRegistry", allowanceRegistry);
        ReflectionTestUtils.setField(tools, "metadataResultChars", metadataResultChars);
        ReflectionTestUtils.setField(tools, "listExportsDefaultLimit", 50);
        ReflectionTestUtils.setField(tools, "listExportsMaxLimit", 200);
        return tools;
    }

    private ListExportService.EntryPage page(List<ListExportService.ListEntry> entries, int total) {
        return new ListExportService.EntryPage(entries, total);
    }

    private ListExportService.ListEntry entry(String name) {
        return new ListExportService.ListEntry(name, "", "CRB", "核心规则书", "feat",
                "chunk_" + name, "doc", List.<String>of(), List.of("战斗"), "",
                null, null, null, null, null, null, null, null, null, null);
    }
}
