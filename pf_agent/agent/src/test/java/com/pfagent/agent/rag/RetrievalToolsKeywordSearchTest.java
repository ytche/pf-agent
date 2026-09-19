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

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * RetrievalTools 的 SP8d 工具单元测试（keywordSearch）
 *
 * 覆盖 LLM 侧行为契约：
 *  - 命中：候选清单按序输出（module/title/书/chunk_id），逐条挂来源编号；
 *    存在精确同名条目时先行提示（与 resolveEntry 边界区分）
 *  - 查无命中：回退文案（转 vectorSearch/searchByMetadata，勿直接 reportDataGap）
 *  - 空术语/未知模块：参数自纠提示
 *  - 索引关闭：固定提示（与 resolveEntry 一致）
 */
@ExtendWith(MockitoExtension.class)
class RetrievalToolsKeywordSearchTest {

    @Mock
    private SearchService searchService;
    @Mock
    private SourceCollector collector;
    @Mock
    private DataGapRecorder recorder;
    @Mock
    private SpellListService spellListService;
    @Mock
    private EntryResolver entryResolver;

    private static final EntryResolver.EntryRef FIREBALL =
            new EntryResolver.EntryRef("spell", "spell_001", "火球术", "核心规则书", "CRB");
    private static final EntryResolver.EntryRef FIREBALL_MYTHIC =
            new EntryResolver.EntryRef("spell", "spell_002", "火球术（神话）", "神话冒险", "MA");

    /** 命中：按序输出 module/title/书/chunk_id，逐条挂来源编号 */
    @Test
    void keywordSearchHitsReturnOrderedCandidatesWithSourceTags() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.substringSearch("火球", null)).thenReturn(List.of(FIREBALL, FIREBALL_MYTHIC));
        when(entryResolver.resolve("火球", null)).thenReturn(List.of());
        when(searchService.getByChunkId(anyString(), anyString()))
                .thenAnswer(inv -> doc(inv.getArgument(1)));
        stubAddSequential();

        String result = tools().keywordSearch("火球", null);

        assertThat(result).contains("命中 2 个候选", "火球术", "spell_001", "火球术（神话）", "spell_002");
        assertThat(result).contains("来源:CRB", "[#1]", "[#2]");
        assertThat(result.indexOf("spell_001")).isLessThan(result.indexOf("spell_002"));
        assertThat(result).contains("getEntryById");
        verify(collector).add(any());
    }

    /** 存在精确同名条目：先行提示（resolveEntry 等价路径），与纯子串命中区分 */
    @Test
    void keywordSearchWithExactNamesShowsExactHint() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.substringSearch("火球术", null)).thenReturn(List.of(FIREBALL, FIREBALL_MYTHIC));
        when(entryResolver.resolve("火球术", null)).thenReturn(List.of(FIREBALL));
        when(searchService.getByChunkId(anyString(), anyString()))
                .thenAnswer(inv -> doc(inv.getArgument(1)));
        stubAddSequential();

        String result = tools().keywordSearch("火球术", null);

        assertThat(result).contains("精确同名条目", "resolveEntry", "火球术");
    }

    /** 纯子串命中（无精确同名）：不出现精确提示 */
    @Test
    void keywordSearchWithoutExactNamesOmitsExactHint() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.substringSearch("火球", null)).thenReturn(List.of(FIREBALL, FIREBALL_MYTHIC));
        when(entryResolver.resolve("火球", null)).thenReturn(List.of());
        when(searchService.getByChunkId(anyString(), anyString()))
                .thenAnswer(inv -> doc(inv.getArgument(1)));
        stubAddSequential();

        String result = tools().keywordSearch("火球", null);

        assertThat(result).doesNotContain("精确同名条目");
    }

    /** module 参数透传给解析器 */
    @Test
    void keywordSearchPassesModuleFilterThrough() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.substringSearch("火球", "spell")).thenReturn(List.of(FIREBALL));
        when(entryResolver.resolve("火球", "spell")).thenReturn(List.of());
        when(searchService.getByChunkId("spell", "spell_001")).thenReturn(doc("spell_001"));
        stubAddSequential();

        String result = tools().keywordSearch("火球", "spell");

        assertThat(result).contains("spell_001");
        verify(entryResolver).substringSearch("火球", "spell");
    }

    /** 查无命中：回退文案，不挂溯源 */
    @Test
    void keywordSearchNoHitReturnsFallbackHint() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.substringSearch("查无此名", null)).thenReturn(List.of());

        String result = tools().keywordSearch("查无此名", null);

        assertThat(result).contains("未找到包含", "查无此名", "vectorSearch", "searchByMetadata", "reportDataGap");
        verifyNoInteractions(collector);
    }

    /** 空术语：参数提示 */
    @Test
    void keywordSearchBlankTermReturnsHint() {
        when(entryResolver.isEnabled()).thenReturn(true);

        String result = tools().keywordSearch("  ", null);

        assertThat(result).contains("请提供检索术语");
        verify(entryResolver, never()).substringSearch(anyString(), any());
    }

    /** 未知模块：错误提示自纠 */
    @Test
    void keywordSearchUnknownModuleReturnsHint() {
        when(entryResolver.isEnabled()).thenReturn(true);

        String result = tools().keywordSearch("火球", "monster");

        assertThat(result).contains("未知模块", "spell");
    }

    /** 索引关闭：固定提示，与 resolveEntry 一致 */
    @Test
    void keywordSearchDisabledReturnsFixedHint() {
        when(entryResolver.isEnabled()).thenReturn(false);

        String result = tools().keywordSearch("火球", null);

        assertThat(result).contains("未启用", "entry-resolver-enabled=false");
        verifyNoInteractions(collector);
        verify(entryResolver, never()).substringSearch(anyString(), any());
    }

    /** 向量库缺原文的候选：不挂号但不中断清单 */
    @Test
    void keywordSearchMissingDocSkipsSourceTagButKeepsLine() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.substringSearch("火球", null)).thenReturn(List.of(FIREBALL));
        when(entryResolver.resolve("火球", null)).thenReturn(List.of());
        when(searchService.getByChunkId("spell", "spell_001")).thenReturn(null);
        when(collector.add(any())).thenReturn(List.of());

        String result = tools().keywordSearch("火球", null);

        assertThat(result).contains("火球术", "spell_001");
        assertThat(result).doesNotContain("[#");
    }

    /** 索引关闭：resolveEntry/getEntryLinks/keywordSearch 三工具返回同一段固定提示 */
    @Test
    void disabledHintIdenticalAcrossAllThreeEntryTools() {
        when(entryResolver.isEnabled()).thenReturn(false);

        String resolve = tools().resolveEntry("火球术");
        String links = tools().getEntryLinks("火球术", null);
        String keyword = tools().keywordSearch("火球", null);

        assertThat(links).isEqualTo(resolve);
        assertThat(keyword).isEqualTo(resolve);
    }

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

    private RetrievalTools tools() {
        RetrievalTools t = new RetrievalTools();
        ReflectionTestUtils.setField(t, "searchService", searchService);
        ReflectionTestUtils.setField(t, "collector", collector);
        ReflectionTestUtils.setField(t, "recorder", recorder);
        ReflectionTestUtils.setField(t, "filterTranslator", new FilterTranslator());
        ReflectionTestUtils.setField(t, "spellListService", spellListService);
        ReflectionTestUtils.setField(t, "entryResolver", entryResolver);
        ReflectionTestUtils.setField(t, "vectorResultChars", 1500);
        ReflectionTestUtils.setField(t, "metadataResultChars", 4000);
        ReflectionTestUtils.setField(t, "entryResultChars", 8000);
        ReflectionTestUtils.setField(t, "metadataDefaultLimit", 50);
        ReflectionTestUtils.setField(t, "gapsListDefaultLimit", 20);
        ReflectionTestUtils.setField(t, "entryLinksMaxPerSection", 20);
        return t;
    }

    private Document doc(String chunkId) {
        return Document.builder().text("正文")
                .metadata(Map.of("chunk_id", chunkId, "title", "条目")).build();
    }
}
