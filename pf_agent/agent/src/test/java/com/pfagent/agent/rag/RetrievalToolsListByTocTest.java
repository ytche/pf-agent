package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * listByToc 工具测试（F-008，批 A Task 14）
 *
 * 覆盖：四模块 + all、空前缀目录概览、非空前缀分页条目、offset 越界、
 * 未命中给上级目录提示、未知/不可用模块提示、只对展示页挂真实来源、
 * 点查未命中时降级合成来源仍保持 chunk_id 与 [#N] 对齐。
 */
@ExtendWith(MockitoExtension.class)
class RetrievalToolsListByTocTest {

    @Mock
    private TocListService tocListService;
    @Mock
    private SearchService searchService;
    @Mock
    private SourceCollector collector;

    private static final List<String> ALL_MODULES = List.of("spell", "feat", "race", "equipment");

    // ---------- 概览 ----------

    @Test
    void emptyPrefixReturnsRootOverviewWithoutSources() {
        when(tocListService.listByToc("all", "", 50, 0)).thenReturn(new TocListService.TocOverview(
                List.of(new TocListService.TocNode("spell", "法术", 12),
                        new TocListService.TocNode("equipment", "核心规则书", 30)), 42));

        String result = tools().listByToc("all", "", 50, 0);

        assertThat(result).contains("目录概览", "[spell] 法术（12 条）", "[equipment] 核心规则书（30 条）")
                .contains("共 2 个一级节点", "覆盖 42 条", "tocPrefix=\"法术\"");
        assertThat(result).doesNotContain("[#");
        verifyNoInteractions(collector);
    }

    @Test
    void overviewWithoutPathShowsHonestHint() {
        when(tocListService.knownModules()).thenReturn(List.of("feat"));
        when(tocListService.listByToc("feat", null, null, null))
                .thenReturn(new TocListService.TocOverview(List.of(), 0));

        String result = tools().listByToc("feat", null, null, null);

        assertThat(result).contains("当前没有可用的目录路径", "toc_path", "listEntries/getSpellList");
        verifyNoInteractions(collector);
    }

    // ---------- 条目页 ----------

    @Test
    void nonEmptyPrefixReturnsPagedItemsWithAlignedSources() {
        List<TocListService.TocEntry> items = List.of(
                new TocListService.TocEntry("feat", "闪避", "CRB", "feat", "feat_1", "专长 → 战斗专长"),
                new TocListService.TocEntry("feat", "双武器攻击", "CRB", "feat", "feat_2", "专长 → 战斗专长"));
        when(tocListService.knownModules()).thenReturn(ALL_MODULES);
        when(tocListService.listByToc("feat", "专长 → 战斗专长", 50, 0))
                .thenReturn(new TocListService.TocPage(items, 2, 0, 50));
        when(tocListService.ancestorPrefixes("feat", "专长 → 战斗专长")).thenReturn(List.of("专长"));
        when(searchService.getByChunkId("feat", "feat_1")).thenReturn(doc("feat_1", "闪避原文"));
        when(searchService.getByChunkId("feat", "feat_2")).thenReturn(doc("feat_2", "双武器攻击原文"));
        CollectorStubs.stubIds(collector, List.of(1, 2));

        String result = tools().listByToc("feat", "专长 → 战斗专长", 50, 0);

        assertThat(result).contains("1. 闪避 [CRB]", "chunk_id: feat_1", "目录: 专长 → 战斗专长", "[#1]");
        assertThat(result).contains("2. 双武器攻击", "chunk_id: feat_2", "[#2]");
        assertThat(result).contains("total=2", "hasMore=false", "capped=false");
        assertThat(result).contains("上级目录: 专长");
    }

    @Test
    void allModuleAddsModulePrefixPerItem() {
        List<TocListService.TocEntry> items = List.of(
                new TocListService.TocEntry("spell", "燃烧之手", "CRB", "spell", "spell_1", "法术 → 奥术"),
                new TocListService.TocEntry("equipment", "长剑", "CRB", "equipment", "equip_1", "核心规则书 → 装备"));
        when(tocListService.listByToc("all", "核心规则书", 10, 0))
                .thenReturn(new TocListService.TocPage(items, 2, 0, 10));
        when(tocListService.ancestorPrefixes("all", "核心规则书")).thenReturn(List.of());
        when(searchService.getByChunkId("spell", "spell_1")).thenReturn(doc("spell_1", "燃烧之手原文"));
        when(searchService.getByChunkId("equipment", "equip_1")).thenReturn(doc("equip_1", "长剑原文"));
        CollectorStubs.stubIds(collector, List.of(1, 2));

        String result = tools().listByToc("all", "核心规则书", 10, 0);

        assertThat(result).contains("[模块:spell] 燃烧之手", "[模块:equipment] 长剑");
    }

    @Test
    void secondPageCarriesHasMoreAndNextOffset() {
        List<TocListService.TocEntry> items = List.of(
                new TocListService.TocEntry("feat", "闪避", "CRB", "feat", "feat_1", "专长 → 战斗专长"));
        when(tocListService.knownModules()).thenReturn(ALL_MODULES);
        when(tocListService.listByToc("feat", "专长 → 战斗专长", 1, 0))
                .thenReturn(new TocListService.TocPage(items, 2, 0, 1));
        when(tocListService.ancestorPrefixes("feat", "专长 → 战斗专长")).thenReturn(List.of("专长"));
        when(searchService.getByChunkId("feat", "feat_1")).thenReturn(doc("feat_1", "闪避原文"));
        CollectorStubs.stubIds(collector, List.of(1));

        String result = tools().listByToc("feat", "专长 → 战斗专长", 1, 0);

        assertThat(result).contains("hasMore=true", "offset=1", "total=2");
    }

    @Test
    void offsetBeyondTotalKeepsRealTotalAndHints() {
        when(tocListService.knownModules()).thenReturn(ALL_MODULES);
        when(tocListService.listByToc("feat", "专长", 50, 99))
                .thenReturn(new TocListService.TocPage(List.of(), 5, 99, 50));
        when(tocListService.ancestorPrefixes("feat", "专长")).thenReturn(List.of());

        String result = tools().listByToc("feat", "专长", 50, 99);

        assertThat(result).contains("共 5 条命中", "offset=99 越界", "减小 offset");
        verifyNoInteractions(collector);
    }

    @Test
    void unmatchedPrefixShowsAncestorHints() {
        when(tocListService.knownModules()).thenReturn(ALL_MODULES);
        when(tocListService.listByToc("equipment", "核心规则书 → 装备 → 不存在", 50, 0))
                .thenReturn(new TocListService.TocPage(List.of(), 0, 0, 50));
        when(tocListService.ancestorPrefixes("equipment", "核心规则书 → 装备 → 不存在"))
                .thenReturn(List.of("核心规则书 → 装备", "核心规则书"));

        String result = tools().listByToc("equipment", "核心规则书 → 装备 → 不存在", 50, 0);

        assertThat(result).contains("未命中目录前缀", "可用上级目录",
                "「核心规则书 → 装备」", "「核心规则书」");
        verifyNoInteractions(collector);
    }

    // ---------- 模块校验 / 降级 ----------

    @Test
    void unknownModuleListsAvailableModules() {
        when(tocListService.knownModules()).thenReturn(List.of("spell", "feat"));

        String result = tools().listByToc("trait", "专长", 50, 0);

        assertThat(result).contains("未知模块", "spell(法术)/feat(专长)/race(种族)/equipment(装备)/all(全部)",
                "当前可用: spell/feat");
        verifyNoInteractions(collector);
    }

    @Test
    void unavailableModuleDegradesWithHint() {
        when(tocListService.knownModules()).thenReturn(List.of("spell", "feat"));

        String result = tools().listByToc("equipment", "核心规则书 → 装备", 50, 0);

        assertThat(result).contains("目录清单暂不可用", "listEntries/getSpellList/searchByMetadata");
        verifyNoInteractions(collector);
    }

    // ---------- 来源降级 / 对齐 ----------

    @Test
    void missingChunkFallsBackToSyntheticSourceKeepingChunkId() {
        List<TocListService.TocEntry> items = List.of(
                new TocListService.TocEntry("feat", "领导力", "CRB", "feat", "feat_missing", "专长 → 通用专长"));
        when(tocListService.knownModules()).thenReturn(ALL_MODULES);
        when(tocListService.listByToc("feat", "专长 → 通用专长", 50, 0))
                .thenReturn(new TocListService.TocPage(items, 1, 0, 50));
        when(tocListService.ancestorPrefixes("feat", "专长 → 通用专长")).thenReturn(List.of("专长"));
        when(searchService.getByChunkId("feat", "feat_missing")).thenReturn(null);
        CollectorStubs.stubIds(collector, List.of(1));

        String result = tools().listByToc("feat", "专长 → 通用专长", 50, 0);

        assertThat(result).contains("领导力", "chunk_id: feat_missing", "[#1]");
        org.mockito.ArgumentCaptor<List<Document>> captor = org.mockito.ArgumentCaptor.forClass(List.class);
        verify(collector).addWithLimit(captor.capture());
        assertThat(captor.getValue()).hasSize(1);
        assertThat(captor.getValue().get(0).getMetadata().get("chunk_id")).isEqualTo("feat_missing");
        assertThat(captor.getValue().get(0).getMetadata().get("toc_path")).isEqualTo("专长 → 通用专长");
    }

    @Test
    void droppedItemsAreOmittedFromOutputAndHintAppears() {
        List<TocListService.TocEntry> items = List.of(
                new TocListService.TocEntry("feat", "闪避", "CRB", "feat", "feat_1", "专长 → 战斗专长"),
                new TocListService.TocEntry("feat", "领导力", "CRB", "feat", "feat_2", "专长 → 战斗专长"));
        when(tocListService.knownModules()).thenReturn(ALL_MODULES);
        when(tocListService.listByToc("feat", "专长 → 战斗专长", 50, 0))
                .thenReturn(new TocListService.TocPage(items, 2, 0, 50));
        when(tocListService.ancestorPrefixes("feat", "专长 → 战斗专长")).thenReturn(List.of("专长"));
        when(searchService.getByChunkId("feat", "feat_1")).thenReturn(doc("feat_1", "闪避原文"));
        when(searchService.getByChunkId("feat", "feat_2")).thenReturn(doc("feat_2", "领导力原文"));
        CollectorStubs.stubIds(collector, java.util.Arrays.asList(1, null));

        String result = tools().listByToc("feat", "专长 → 战斗专长", 50, 0);

        assertThat(result).contains("闪避", "[#1]", "请求级来源护栏", "丢弃 1 条");
        assertThat(result).doesNotContain("领导力", "[#2]");
    }

    private Document doc(String chunkId, String text) {
        return Document.builder().text(text)
                .metadata(Map.of("chunk_id", chunkId, "title", text)).build();
    }

    private RetrievalTools tools() {
        RetrievalTools tools = new RetrievalTools();
        ReflectionTestUtils.setField(tools, "tocListService", tocListService);
        ReflectionTestUtils.setField(tools, "searchService", searchService);
        ReflectionTestUtils.setField(tools, "collector", collector);
        ReflectionTestUtils.setField(tools, "filterTranslator", new FilterTranslator());
        return tools;
    }
}
