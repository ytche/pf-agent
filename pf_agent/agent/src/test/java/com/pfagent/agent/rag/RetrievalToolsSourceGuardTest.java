package com.pfagent.agent.rag;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;
import org.yaml.snakeyaml.Yaml;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

/**
 * 请求级来源护栏接入测试（F-016，批 A Task 14）
 *
 * 使用真实 SourceCollector（不同上限）验证工具层：
 *  - 被护栏拒绝的 doc 既不出现在工具文本，也不进入 sources；
 *  - 文本 [#N] 与 drain() 第 N 条一一对齐；
 *  - 各来源工具在 dropped>0 时追加收窄/体积提示，且不置 gapReported；
 *  - getEntryById 单条超预算返回明确超限提示，不输出正文；
 *  - application.yml 的重排/护栏/用量配置键可注入且与代码默认值一致。
 */
@ExtendWith(MockitoExtension.class)
class RetrievalToolsSourceGuardTest {

    @Mock
    private SearchService searchService;
    @Mock
    private DataGapRecorder recorder;
    @Mock
    private ListExportService listExportService;
    @Mock
    private SpellListService spellListService;
    @Mock
    private ClassTableService classTableService;
    @Mock
    private RuleTableService ruleTableService;
    @Mock
    private EntryResolver entryResolver;

    private SourceCollector collector;

    @BeforeEach
    void setUp() {
        collector = new SourceCollector(2, 1_000_000);
        collector.begin();
    }

    // ---------- 检索类工具 ----------

    @Test
    void searchByMetadataDropsThirdDocFromOutputAndSources() {
        List<Document> docs = docs("spell", 3);
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(docs, 3, 0, 3));

        String result = tools().searchByMetadata("spell", metadataQuery());

        assertThat(result).contains("法术1", "法术2", "[#1]", "[#2]", "请求级来源护栏", "丢弃 1 条");
        assertThat(result).doesNotContain("法术3", "[#3]");
        assertThat(collector.drain()).extracting(Document::getText)
                .containsExactly("法术1", "法术2");
        assertThat(collector.wasGapReported()).isFalse();
    }

    @Test
    void vectorSearchDropsOverLimitFragment() {
        when(searchService.search("火球", "spell")).thenReturn(docs("spell", 3));

        String result = tools().vectorSearch("火球", "spell");

        assertThat(result).contains("片段 1", "法术1", "片段 2", "法术2", "请求级来源护栏");
        assertThat(result).doesNotContain("法术3", "片段 3", "[#3]");
        assertThat(collector.drain()).hasSize(2);
    }

    @Test
    void keywordSearchOmitsDroppedCandidateAndKeepsNumberingAligned() {
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.substringSearch("法术", null)).thenReturn(List.of(
                ref("spell", "c1", "法术一"), ref("spell", "c2", "法术二"), ref("spell", "c3", "法术三")));
        when(entryResolver.resolve("法术", null)).thenReturn(List.of());
        when(searchService.getByChunkId("spell", "c1")).thenReturn(doc("c1", "法术一"));
        when(searchService.getByChunkId("spell", "c2")).thenReturn(doc("c2", "法术二"));
        when(searchService.getByChunkId("spell", "c3")).thenReturn(doc("c3", "法术三"));

        String result = tools().keywordSearch("法术", null);

        assertThat(result).contains("法术一", "[#1]", "法术二", "[#2]", "请求级来源护栏");
        assertThat(result).doesNotContain("法术三", "[#3]");
        assertThat(collector.drain()).extracting(Document::getText)
                .containsExactly("法术一", "法术二");
    }

    // ---------- 点查 / 清单类工具 ----------

    @Test
    void getEntryByIdOverBudgetReturnsExplicitLimitHintWithoutBody() {
        collector = new SourceCollector(50, 10);   // 10 字节预算
        collector.begin();
        String body = "中".repeat(40);             // 120 UTF-8 字节
        when(searchService.getByChunkId("spell", "big")).thenReturn(
                Document.builder().text(body).metadata(Map.of("chunk_id", "big", "title", "大火球")).build());

        String result = tools().getEntryById("spell", "big");

        assertThat(result).contains("超出本请求来源体积上限", "max-sources-bytes", "未返回正文", "不是数据缺失");
        assertThat(result).doesNotContain(body);
        assertThat(collector.drain()).isEmpty();
    }

    @Test
    void getEntryByIdAlignedNumberWhenAccepted() {
        Document doc = Document.builder().text("正文")
                .metadata(Map.of("chunk_id", "ok", "title", "火球术",
                        "book_name_cn", "核心规则书", "book_abbreviation", "CRB")).build();
        when(searchService.getByChunkId("spell", "ok")).thenReturn(doc);

        String result = tools().getEntryById("spell", "ok");

        assertThat(result).contains("正文", "来源编号 [#1]");
        assertThat(collector.drain()).containsExactly(doc);
    }

    @Test
    void getSpellListProvenanceDroppedWhenBudgetExhausted() {
        prefillCollector();
        when(spellListService.isAvailable()).thenReturn(true);
        when(spellListService.resolve("法师")).thenReturn("法师");
        when(spellListService.listPageDocument("法师")).thenReturn(doc("spell_page", "列表页"));

        String result = tools().getSpellList("法师", 1, null, null);

        assertThat(result).contains("已停止返回其正文/表格/条目信息", "这不是数据缺失");
        assertThat(result).doesNotContain("燃烧之手", "本清单来源 [#");
        assertThat(collector.wasGapReported()).isFalse();
    }

    @Test
    void getClassTableProvenanceDroppedWhenBudgetExhausted() {
        prefillCollector();
        when(classTableService.isAvailable()).thenReturn(true);
        when(classTableService.resolve("法师")).thenReturn("法师");
        when(classTableService.provenanceDocument("法师")).thenReturn(doc("class_page", "成长表页"));

        String result = tools().getClassTable("法师", 1);

        assertThat(result).contains("已停止返回其正文/表格/条目信息", "这不是数据缺失");
        assertThat(result).doesNotContain("1 级：BAB +0", "来源编号 [#");
    }

    @Test
    void getRuleTableProvenanceDroppedWhenBudgetExhausted() {
        prefillCollector();
        RuleTableService.RuleTable table = new RuleTableService.RuleTable(
                "t1", "rule_c1", "rule_doc", 1, "standard", "表1", "动物伙伴",
                List.of("等级"), List.of(List.of("1")), false, 1, 1, 1, List.of("1"));
        when(ruleTableService.isAvailable()).thenReturn(true);
        when(ruleTableService.find("动物伙伴")).thenReturn(List.of(table));
        when(ruleTableService.provenanceDocument(table)).thenReturn(doc("rule_c1", "规则表页"));

        String result = tools().getRuleTable("动物伙伴", null);

        assertThat(result).contains("已停止返回其正文/表格/条目信息", "这不是数据缺失");
        assertThat(result).doesNotContain("表头: 等级", "来源编号 [#");
    }

    @Test
    void listEntriesOmitsDroppedRowsAndKeepsIdsAligned() {
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any(ListEntriesQuery.class))).thenReturn(Set.of());
        List<ListExportService.ListEntry> entries = List.of(
                entry("甲", "feat_1"), entry("乙", "feat_2"), entry("丙", "feat_3"));
        when(listExportService.search(eq("feat"), any(ListEntriesQuery.class), eq(3), eq(0)))
                .thenReturn(new ListExportService.EntryPage(entries, 3));
        when(listExportService.entryLine(eq("feat"), anyInt(), any(), eq(true)))
                .thenAnswer(inv -> {
                    ListExportService.ListEntry e = inv.getArgument(2);
                    return inv.getArgument(1) + ". " + e.name();
                });
        when(listExportService.provenanceDocuments("feat", entries))
                .thenReturn(List.of(doc("feat_1", "甲原文"), doc("feat_2", "乙原文"), doc("feat_3", "丙原文")));
        ListEntriesQuery query = new ListEntriesQuery(null, Map.of("book", "CRB"), null, 3, 0, "name", true, null);

        String result = tools().listEntries("feat", query);

        assertThat(result).contains("甲", "[#1]", "乙", "[#2]", "请求级来源护栏");
        assertThat(result).doesNotContain("丙", "[#3]");
        assertThat(collector.drain()).extracting(Document::getText)
                .containsExactly("甲原文", "乙原文");
    }

    @Test
    void listEntriesAllRowsRejectedReturnsHintWithoutAnyRows() {
        prefillCollector();
        when(listExportService.isAvailable("feat")).thenReturn(true);
        when(listExportService.unknownFilterFields(eq("feat"), any(ListEntriesQuery.class))).thenReturn(Set.of());
        List<ListExportService.ListEntry> entries = List.of(
                entry("甲", "feat_1"), entry("乙", "feat_2"), entry("丙", "feat_3"));
        when(listExportService.search(eq("feat"), any(ListEntriesQuery.class), eq(3), eq(0)))
                .thenReturn(new ListExportService.EntryPage(entries, 3));
        when(listExportService.entryLine(eq("feat"), anyInt(), any(), eq(true)))
                .thenAnswer(inv -> inv.getArgument(1) + ". " + ((ListExportService.ListEntry) inv.getArgument(2)).name());
        when(listExportService.provenanceDocuments("feat", entries))
                .thenReturn(List.of(doc("feat_1", "甲原文"), doc("feat_2", "乙原文"), doc("feat_3", "丙原文")));
        ListEntriesQuery query = new ListEntriesQuery(null, Map.of("book", "CRB"), null, 3, 0, "name", true, null);

        String result = tools().listEntries("feat", query);

        assertThat(result).contains("均因请求级来源护栏未保留", "未展示任何行", "这不是数据缺失");
        assertThat(result).doesNotContain("甲", "乙", "丙", "[#");
        assertThat(collector.wasGapReported()).isFalse();
    }

    @Test
    void resolveEntryRejectedOmitsEntryMetadataAndHintAppears() {
        prefillCollector();
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.resolve("火球术", null)).thenReturn(List.of(ref("spell", "c1", "火球术")));
        when(searchService.getByChunkId("spell", "c1")).thenReturn(doc("c1", "火球术原文"));

        String result = tools().resolveEntry("火球术");

        assertThat(result).contains("已停止返回其正文/表格/条目信息", "这不是数据缺失");
        assertThat(result).doesNotContain("条目:", "chunk_id:", "来源编号 [#");
        assertThat(collector.wasGapReported()).isFalse();
    }

    @Test
    void getEntryLinksAllRejectedReturnsHintWithoutLinkMetadata() {
        prefillCollector();
        EntryResolver.EntryRef self = ref("spell", "c1", "火球术");
        EntryResolver.EntryLinks links = new EntryResolver.EntryLinks(
                self, null, List.of(), List.of(), List.of());
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.resolve("火球术", null)).thenReturn(List.of(self));
        when(entryResolver.linksOf(self)).thenReturn(links);
        when(searchService.getByChunkId("spell", "c1")).thenReturn(doc("c1", "火球术原文"));

        String result = tools().getEntryLinks("火球术", null);

        assertThat(result).contains("已停止返回其正文/表格/条目信息", "这不是数据缺失");
        assertThat(result).doesNotContain("chunk_id:", "基础法术:", "[#");
        assertThat(collector.wasGapReported()).isFalse();
    }

    @Test
    void getEntryLinksOmitsRejectedLinkTargetsAndKeepsAcceptedNumbering() {
        EntryResolver.EntryRef self = ref("spell", "c1", "火球术");
        EntryResolver.EntryRef base = ref("spell", "c2", "燃烧之手");
        EntryResolver.EntryRef rejected = ref("feat", "f1", "闪避");
        EntryResolver.EntryLinks links = new EntryResolver.EntryLinks(
                self, base, List.of(), List.of(new EntryResolver.EntryLink(rejected, "前置专长")), List.of());
        when(entryResolver.isEnabled()).thenReturn(true);
        when(entryResolver.resolve("火球术", null)).thenReturn(List.of(self));
        when(entryResolver.linksOf(self)).thenReturn(links);
        when(searchService.getByChunkId("spell", "c1")).thenReturn(doc("c1", "火球术原文"));
        when(searchService.getByChunkId("spell", "c2")).thenReturn(doc("c2", "燃烧之手原文"));
        when(searchService.getByChunkId("feat", "f1")).thenReturn(doc("f1", "闪避原文"));

        String result = tools().getEntryLinks("火球术", null);

        assertThat(result).contains("火球术", "[#1]", "燃烧之手", "[#2]", "请求级来源护栏");
        assertThat(result).doesNotContain("闪避", "前置专长", "[#3]", "引用它的:");
        assertThat(collector.drain()).extracting(Document::getText)
                .containsExactly("火球术原文", "燃烧之手原文");
    }

    // ---------- 配置 ----------

    @Test
    @SuppressWarnings("unchecked")
    void applicationYmlUsesEmptyDefaultBookBlacklist() {
        try (InputStream in = getClass().getClassLoader().getResourceAsStream("application.yml")) {
            assertThat(in).as("application.yml 应在测试 classpath 中").isNotNull();
            Map<String, Object> root = new Yaml().load(in);
            Map<String, Object> pf = (Map<String, Object>) root.get("pf");
            Map<String, Object> search = (Map<String, Object>) pf.get("search");
            Map<String, Object> bookFilter = (Map<String, Object>) search.get("book-filter");

            assertThat((List<Object>) bookFilter.get("books")).isEmpty();
            assertThat(bookFilter.get("unknown-book-keep")).isEqualTo(true);
        } catch (java.io.IOException e) {
            throw new IllegalStateException(e);
        }
    }

    @Test
    @SuppressWarnings("unchecked")
    void applicationYmlCarriesRerankGuardAndUsageKeys() {
        try (InputStream in = getClass().getClassLoader().getResourceAsStream("application.yml")) {
            assertThat(in).as("application.yml 应在测试 classpath 中").isNotNull();
            Map<String, Object> root = new Yaml().load(in);
            Map<String, Object> pf = (Map<String, Object>) root.get("pf");
            Map<String, Object> search = (Map<String, Object>) pf.get("search");
            Map<String, Object> usage = (Map<String, Object>) pf.get("usage");

            assertThat(search).containsEntry("top-k", 15)
                    .containsEntry("rerank-enabled", true) // thinking 关闭后 50 候选约 3.4s
                    .containsEntry("rerank-candidates", 50)
                    .containsEntry("rerank-top-n", 15)
                    .containsEntry("rerank-summary-chars", 300)
                    .containsEntry("rerank-timeout", "8s")
                    .containsEntry("rerank-model", "deepseek-flash")
                    .containsEntry("rerank-concurrency", 4)
                    .containsEntry("rerank-queue-capacity", 16)
                    .containsEntry("max-sources-per-request", 50)
                    .containsEntry("max-sources-bytes", 2097152);

            assertThat(usage).containsEntry("prompt-price-per-million", 2.0)
                    .containsEntry("completion-price-per-million", 8.0)
                    .containsEntry("currency", "CNY")
                    .containsEntry("timezone", "Asia/Shanghai");
        } catch (java.io.IOException e) {
            throw new IllegalStateException(e);
        }
    }

    // ---------- harness ----------

    private void prefillCollector() {
        collector.addWithLimit(List.of(doc("pre_1", "预占1"), doc("pre_2", "预占2")));
        assertThat(collector.wasGapReported()).isFalse();
    }

    private MetadataSearchQuery metadataQuery() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("book", "CRB"));
        query.setAllowBroadQuery(true);
        query.setLimit(3);
        query.setOffset(0);
        return query;
    }

    private List<Document> docs(String module, int n) {
        List<Document> docs = new ArrayList<>();
        for (int i = 1; i <= n; i++) {
            docs.add(Document.builder().text("法术" + i)
                    .metadata(Map.of("title", "法术" + i, "chunk_id", module + "-" + i,
                            "book_abbreviation", "CRB", "pf_module", module)).build());
        }
        return docs;
    }

    private Document doc(String chunkId, String text) {
        return Document.builder().text(text)
                .metadata(Map.of("chunk_id", chunkId, "title", text)).build();
    }

    private EntryResolver.EntryRef ref(String module, String chunkId, String title) {
        return new EntryResolver.EntryRef(module, chunkId, title, "核心规则书", "CRB");
    }

    private ListExportService.ListEntry entry(String name, String chunkId) {
        return new ListExportService.ListEntry(name, null, "CRB", "核心规则书", "feat",
                chunkId, "doc_" + chunkId, null, List.of(), null, null, null, null,
                null, null, null, null, null, null, null, null);
    }

    private RetrievalTools tools() {
        RetrievalTools tools = new RetrievalTools();
        ReflectionTestUtils.setField(tools, "searchService", searchService);
        ReflectionTestUtils.setField(tools, "collector", collector);
        ReflectionTestUtils.setField(tools, "recorder", recorder);
        ReflectionTestUtils.setField(tools, "filterTranslator", new FilterTranslator());
        ReflectionTestUtils.setField(tools, "listExportService", listExportService);
        ReflectionTestUtils.setField(tools, "spellListService", spellListService);
        ReflectionTestUtils.setField(tools, "classTableService", classTableService);
        ReflectionTestUtils.setField(tools, "ruleTableService", ruleTableService);
        ReflectionTestUtils.setField(tools, "entryResolver", entryResolver);
        ReflectionTestUtils.setField(tools, "vectorResultChars", 1500);
        ReflectionTestUtils.setField(tools, "metadataResultChars", 4000);
        ReflectionTestUtils.setField(tools, "entryResultChars", 8000);
        ReflectionTestUtils.setField(tools, "metadataDefaultLimit", 50);
        ReflectionTestUtils.setField(tools, "listExportsDefaultLimit", 50);
        ReflectionTestUtils.setField(tools, "listExportsMaxLimit", 200);
        ReflectionTestUtils.setField(tools, "gapsListDefaultLimit", 20);
        return tools;
    }
}
