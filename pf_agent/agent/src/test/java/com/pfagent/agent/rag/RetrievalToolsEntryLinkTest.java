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
 * RetrievalTools 的 J6 工具单元测试（resolveEntry / getEntryLinks）
 *
 * 覆盖 LLM 侧行为契约：
 *  - resolveEntry：唯一命中 → 条目详情 + 挂溯源；多义 → 候选清单（不挂溯源）；
 *    查无此名 → 空结果提示；空名 → 参数提示；索引关闭 → 固定提示
 *  - getEntryLinks：三层链接输出（基础/变体、引用它的、它引用的）逐条挂来源编号；
 *    解析不到的边不出现；无链接层时附说明；未知模块/多义/关闭的提示路径
 */
@ExtendWith(MockitoExtension.class)
class RetrievalToolsEntryLinkTest {

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
    private static final EntryResolver.EntryRef DODGE =
            new EntryResolver.EntryRef("feat", "feat_001", "闪避", "核心规则书", "CRB");

    /** resolveEntry 唯一命中：返回 module/title/书/chunk_id 并挂来源编号 */
    @Test
    void resolveEntrySingleHitReturnsDetailsAndCollects() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.resolve("火球术", null)).thenReturn(List.of(FIREBALL));
        when(searchService.getByChunkId("spell", "spell_001"))
                .thenReturn(doc("spell_001", "火球术"));
        stubAddSequential();

        String result = tools().resolveEntry("火球术");

        assertThat(result).contains("火球术", "spell", "核心规则书(CRB)", "spell_001", "[#1]");
        verify(collector).add(any());
    }

    /** resolveEntry 多义：返回候选清单（含模块/书/chunk_id），不挂溯源 */
    @Test
    void resolveEntryAmbiguousReturnsCandidatesWithoutCollecting() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.resolve("冲锋", null)).thenReturn(List.of(FIREBALL, DODGE));

        String result = tools().resolveEntry("冲锋");

        assertThat(result).contains("2 个候选", "module", "chunk_id", "收窄");
        verifyNoInteractions(collector);
    }

    /** resolveEntry 查无此名：提示转 vectorSearch */
    @Test
    void resolveEntryNoHitReturnsHint() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.resolve("查无此名", null)).thenReturn(List.of());

        String result = tools().resolveEntry("查无此名");

        assertThat(result).contains("未找到条目", "vectorSearch");
        verifyNoInteractions(collector);
    }

    /** resolveEntry 空名：参数提示 */
    @Test
    void resolveEntryBlankNameReturnsHint() {
        when(entryResolver.isEnabled()).thenReturn(true);

        String result = tools().resolveEntry("  ");

        assertThat(result).contains("请提供条目名");
        verifyNoInteractions(collector);
    }

    /** resolveEntry 索引关闭：固定提示，不触碰检索 */
    @Test
    void resolveEntryDisabledReturnsFixedHint() {
        when(entryResolver.isEnabled()).thenReturn(false);

        String result = tools().resolveEntry("火球术");

        assertThat(result).contains("未启用", "entry-resolver-enabled=false");
        verifyNoInteractions(collector);
        verify(entryResolver, never()).resolve(anyString(), any());
    }

    /** getEntryLinks 全层输出：基础/变体/引用它的/它引用的，逐条挂来源编号 */
    @Test
    void getEntryLinksReturnsAllLayersWithSourceTags() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.resolve("火球术（神话）", null)).thenReturn(List.of(FIREBALL_MYTHIC));
        EntryResolver.EntryLinks links = new EntryResolver.EntryLinks(
                FIREBALL_MYTHIC, FIREBALL, List.of(),
                List.of(new EntryResolver.EntryLink(DODGE, "神话专长前置")),
                List.of(new EntryResolver.EntryLink(FIREBALL, "基础法术")));
        when(entryResolver.linksOf(FIREBALL_MYTHIC)).thenReturn(links);
        when(searchService.getByChunkId(anyString(), anyString()))
                .thenAnswer(inv -> doc(inv.getArgument(1), "正文"));
        stubAddSequential();

        String result = tools().getEntryLinks("火球术（神话）", null);

        assertThat(result).contains("基础法术: ", "火球术", "spell_001");
        assertThat(result).contains("引用它的:", "闪避", "feat_001", "神话专长前置");
        assertThat(result).contains("它引用的:", "基础法术");
        assertThat(result).contains("[#1]", "[#3]", "[#4]");
        verify(collector).add(any());
    }

    /** getEntryLinks 解析不到的边不出现：linksOf 只给已解析边，输出原样透传 */
    @Test
    void getEntryLinksOmitsNothingExtraBeyondResolverLinks() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.resolve("闪避", null)).thenReturn(List.of(DODGE));
        when(entryResolver.linksOf(DODGE)).thenReturn(new EntryResolver.EntryLinks(
                DODGE, null, List.of(), List.of(), List.of()));
        when(searchService.getByChunkId("feat", "feat_001")).thenReturn(doc("feat_001", "闪避正文"));
        stubAddSequential();

        String result = tools().getEntryLinks("闪避", null);

        assertThat(result).contains("闪避", "feat_001", "暂无已结构化的引用关系");
        assertThat(result).doesNotContain("基础法术:", "引用它的:", "它引用的:");
    }

    /** getEntryLinks 多义时返回候选清单 */
    @Test
    void getEntryLinksAmbiguousReturnsCandidates() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.resolve("冲锋", "feat")).thenReturn(List.of(FIREBALL, DODGE));

        String result = tools().getEntryLinks("冲锋", "feat");

        assertThat(result).contains("2 个候选");
    }

    /** getEntryLinks 未知模块：错误提示自纠 */
    @Test
    void getEntryLinksUnknownModuleReturnsHint() {
        when(entryResolver.isEnabled()).thenReturn(true);

        String result = tools().getEntryLinks("火球术", "monster");

        assertThat(result).contains("未知模块", "spell");
    }

    /** getEntryLinks 索引关闭：固定提示 */
    @Test
    void getEntryLinksDisabledReturnsFixedHint() {
        when(entryResolver.isEnabled()).thenReturn(false);

        String result = tools().getEntryLinks("火球术", null);

        assertThat(result).contains("未启用");
    }

    /** 反查刷屏防护：单条链接超上限截断并附计数 */
    @Test
    void getEntryLinksCapsOversizedSection() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.resolve("法师", null)).thenReturn(
                List.of(new EntryResolver.EntryRef("class", "class_001", "法师", "核心规则书", "CRB")));
        EntryResolver.EntryRef wizard = new EntryResolver.EntryRef("class", "class_001", "法师", "核心规则书", "CRB");
        List<EntryResolver.EntryLink> spells = new ArrayList<>();
        for (int i = 1; i <= 30; i++) {
            spells.add(new EntryResolver.EntryLink(
                    new EntryResolver.EntryRef("spell", "spell_" + i, "法术" + i, "CRB", "CRB"), i + " 环法术列表"));
        }
        when(entryResolver.linksOf(wizard)).thenReturn(new EntryResolver.EntryLinks(
                wizard, null, List.of(), spells, List.of()));
        when(searchService.getByChunkId(anyString(), anyString()))
                .thenAnswer(inv -> doc(inv.getArgument(1), "正文"));
        stubAddSequential();

        String result = tools().getEntryLinks("法师", null);

        assertThat(result).contains("仅展示前 20 条", "共 30 条");
        assertThat(result).doesNotContain("spell_21 |", "法术21 ");
    }

    /** resolveEntry 唯一命中但向量库无该 chunk：提示原文缺失，不挂溯源 */
    @Test
    void resolveEntryMissingDocReportsHintWithoutCollecting() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.resolve("火球术", null)).thenReturn(List.of(FIREBALL));
        when(searchService.getByChunkId("spell", "spell_001")).thenReturn(null);

        String result = tools().resolveEntry("火球术");

        assertThat(result).contains("未检索到该 chunk 原文", "getEntryLinks");
        verifyNoInteractions(collector);
    }

    /** resolveEntry 空名（null）参数提示 */
    @Test
    void resolveEntryNullNameReturnsHint() {
        when(entryResolver.isEnabled()).thenReturn(true);

        String result = tools().resolveEntry(null);

        assertThat(result).contains("请提供条目名");
    }

    /** getEntryLinks 条数恰为上限：不截断、不附计数提示 */
    @Test
    void getEntryLinksExactlyAtCapShowsNoTruncation() {
        when(entryResolver.isEnabled()).thenReturn(true);
        EntryResolver.EntryRef wizard = new EntryResolver.EntryRef("class", "class_001", "法师", "核心规则书", "CRB");
        when(entryResolver.resolve("法师", null)).thenReturn(List.of(wizard));
        List<EntryResolver.EntryLink> spells = new ArrayList<>();
        for (int i = 1; i <= 20; i++) {
            spells.add(new EntryResolver.EntryLink(
                    new EntryResolver.EntryRef("spell", "spell_" + i, "法术" + i, "CRB", "CRB"), i + " 环法术列表"));
        }
        when(entryResolver.linksOf(wizard)).thenReturn(new EntryResolver.EntryLinks(
                wizard, null, List.of(), spells, List.of()));
        when(searchService.getByChunkId(anyString(), anyString()))
                .thenAnswer(inv -> doc(inv.getArgument(1), "正文"));
        stubAddSequential();

        String result = tools().getEntryLinks("法师", null);

        assertThat(result).contains("spell_20");
        assertThat(result).doesNotContain("仅展示前");
    }

    /** getEntryLinks 唯一命中但向量库无原文：条目行无来源编号，仍输出链接与尾部声明 */
    @Test
    void getEntryLinksMissingDocsStillOutputsLinksWithTailNote() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.resolve("火球术（神话）", null)).thenReturn(List.of(FIREBALL_MYTHIC));
        when(entryResolver.linksOf(FIREBALL_MYTHIC)).thenReturn(new EntryResolver.EntryLinks(
                FIREBALL_MYTHIC, FIREBALL, List.of(), List.of(), List.of()));
        when(searchService.getByChunkId(anyString(), anyString())).thenReturn(null);

        String result = tools().getEntryLinks("火球术（神话）", null);

        assertThat(result).contains("基础法术: ", "火球术", "只展示能精确解析的引用");
        assertThat(result).doesNotContain("[#");
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

    private Document doc(String chunkId, String text) {
        return Document.builder().text(text)
                .metadata(Map.of("chunk_id", chunkId, "title", "条目")).build();
    }
}
