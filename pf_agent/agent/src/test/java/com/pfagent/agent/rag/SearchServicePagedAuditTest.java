package com.pfagent.agent.rag;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.SimpleVectorStore;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

/**
 * AKN-015 分页元数据补全 —— SearchService.searchByMetadataPaged 独立审计用例（tester 补充）
 *
 * 覆盖 coder 未覆盖的分页边界：offset 越界 / 负 offset 钳制 / limit 上限钳制后
 * totalCount 与 offset 回传的一致性 / 旧签名委托。
 */
@ExtendWith(MockitoExtension.class)
class SearchServicePagedAuditTest {

    @Mock
    private SimpleVectorStore spellStore;
    @Mock
    private SimpleVectorStore classStore;
    @Mock
    private SimpleVectorStore featStore;
    @Mock
    private SimpleVectorStore raceStore;
    @Mock
    private SimpleVectorStore traitStore;
    @Mock
    private SimpleVectorStore equipmentStore;
    @Mock
    private SimpleVectorStore skillStore;
    @Mock
    private SimpleVectorStore ruleStore;

    @Test
    @DisplayName("offset 越界（==totalCount）：当页为空但 totalCount 保留，hasMore=false")
    void offsetEqualsTotalCountYieldsEmptyPageWithTotalKept() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(docs(3));

        SearchService.PagedResult r = service().searchByMetadataPaged("spell", query(3, 3));

        assertThat(r.page()).isEmpty();
        assertThat(r.totalCount()).isEqualTo(3);
        assertThat(r.offset()).isEqualTo(3);
        assertThat(r.hasMore()).isFalse();
    }

    @Test
    @DisplayName("offset 越界（> totalCount）：不抛异常，offset 原样回传，hasMore=false")
    void offsetBeyondTotalCountYieldsEmptyPage() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(docs(3));

        SearchService.PagedResult r = service().searchByMetadataPaged("spell", query(99, 3));

        assertThat(r.page()).isEmpty();
        assertThat(r.totalCount()).isEqualTo(3);
        assertThat(r.offset()).isEqualTo(99);
        assertThat(r.hasMore()).isFalse();
    }

    @Test
    @DisplayName("负 offset 钳制为 0：当页从首条开始，offset 回传 0（工具层据此拼『第 1~N 条』）")
    void negativeOffsetClamped() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(docs(3));

        SearchService.PagedResult r = service().searchByMetadataPaged("spell", query(-5, 2));

        assertThat(r.offset()).isZero();
        assertThat(r.page()).hasSize(2);
        assertThat(title(r.page().get(0))).isEqualTo("A");
        assertThat(r.hasMore()).isTrue();
    }

    @Test
    @DisplayName("limit 超 enumerationTopK 被钳制，但 totalCount 不受钳制影响（真实总数）")
    void limitClampedButTotalCountUnaffected() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(docs(3));

        SearchService.PagedResult r = service().searchByMetadataPaged("spell", query(0, 10000));

        assertThat(r.limit()).isEqualTo(500);   // enumerationTopK
        assertThat(r.page()).hasSize(3);
        assertThat(r.totalCount()).isEqualTo(3);
        assertThat(r.hasMore()).isFalse();
    }

    @Test
    @DisplayName("limit<=0 钳制为 1（不返回空页），totalCount 仍为完整结果数")
    void nonPositiveLimitClampedToOne() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(docs(3));

        SearchService.PagedResult r = service().searchByMetadataPaged("spell", query(0, 0));

        assertThat(r.limit()).isEqualTo(1);
        assertThat(r.page()).hasSize(1);
        assertThat(r.totalCount()).isEqualTo(3);
        assertThat(r.hasMore()).isTrue();
    }

    @Test
    @DisplayName("旧签名 searchByMetadata 委托 paged：返回值与 page() 完全一致（行为兼容）")
    void legacySignatureDelegatesToPaged() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(docs(3));

        List<Document> legacy = service().searchByMetadata("spell", query(0, 2));
        SearchService.PagedResult paged = service().searchByMetadataPaged("spell", query(0, 2));

        assertThat(legacy).isEqualTo(paged.page());
        assertThat(legacy).hasSize(2);
    }

    @Test
    @DisplayName("空结果：totalCount=0，page 空，hasMore=false")
    void emptyResultHasZeroTotal() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(List.of());

        SearchService.PagedResult r = service().searchByMetadataPaged("spell", query(0, 50));

        assertThat(r.totalCount()).isZero();
        assertThat(r.page()).isEmpty();
        assertThat(r.hasMore()).isFalse();
    }

    // ---------- AKN015-T1 返修：capped 识别语义 ----------

    @Test
    @DisplayName("capped 边界：原始命中 499 → capped=false；500 → capped=true 且 cap=500")
    void cappedFlagBoundaryAt499And500() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(hitDocs(499, 0));
        SearchService.PagedResult below = service().searchByMetadataPaged("spell", query(0, 500));
        assertThat(below.capped()).isFalse();
        assertThat(below.totalCount()).isEqualTo(499);

        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(hitDocs(500, 0));
        SearchService.PagedResult at = service().searchByMetadataPaged("spell", query(0, 500));
        assertThat(at.capped()).isTrue();
        assertThat(at.cap()).isEqualTo(500);
        assertThat(at.totalCount()).isEqualTo(500);
    }

    @Test
    @DisplayName("capped 判定在 bookFilter/去重之前：原始 500 命中被书过滤后 totalCount<cap，仍标 capped（保守，不给假总数）")
    void cappedDetectedBeforeBookFilter() {
        // 300 条 book="?"（黑名单剔除） + 200 条 book="CRB" → 原始命中 500 触达上限，
        // 过滤后仅 200 条可返回；判定在过滤前 → capped=true（宁可说"可能更多"，也不谎报精确总数）
        List<Document> hits = new java.util.ArrayList<>();
        hits.addAll(hitDocs(300, 0, "?"));
        hits.addAll(hitDocs(200, 400, "CRB"));
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(hits);

        SearchService.PagedResult r = service().searchByMetadataPaged("spell", query(0, 500));

        assertThat(r.capped()).isTrue();
        assertThat(r.cap()).isEqualTo(500);
        assertThat(r.totalCount()).isEqualTo(200);   // 过滤后条数 < cap
        assertThat(r.page()).hasSize(200);
        assertThat(r.hasMore()).isFalse();
    }

    @Test
    @DisplayName("跨库：任一 store 原始命中达上限即 capped（其它库结果很少也不掩盖截断）")
    void cappedIfAnyStoreSaturates() {
        when(spellStore.similaritySearch(any(SearchRequest.class))).thenReturn(hitDocs(500, 0));
        when(classStore.similaritySearch(any(SearchRequest.class))).thenReturn(hitDocs(3, 0));

        SearchService.PagedResult r = service().searchByMetadataPaged("all", query(0, 500));

        assertThat(r.capped()).isTrue();
        assertThat(r.totalCount()).isEqualTo(503);   // merged 可 > cap
        assertThat(r.page()).hasSize(500);           // 单次返回仍受 limit(=cap) 约束
    }

    @Test
    @DisplayName("4 参兼容构造：capped=false、cap=0，hasMore 语义不变")
    void legacyConstructorDefaults() {
        SearchService.PagedResult r = new SearchService.PagedResult(docs(2), 3, 0, 2);
        assertThat(r.capped()).isFalse();
        assertThat(r.cap()).isZero();
        assertThat(r.hasMore()).isTrue();
    }

    // ---------- harness ----------

    private List<Document> hitDocs(int n, int start) {
        return hitDocs(n, start, "CRB");
    }

    private List<Document> hitDocs(int n, int start, String book) {
        List<Document> list = new java.util.ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            list.add(Document.builder().text("正文").score(0.9)
                    .metadata(Map.of("title", "T" + (start + i), "chunk_id", "c" + (start + i),
                            "book_abbreviation", book))
                    .build());
        }
        return list;
    }

    private MetadataSearchQuery query(int offset, int limit) {
        MetadataSearchQuery q = new MetadataSearchQuery();
        q.setFilters(Map.of("book", "CRB"));
        q.setOffset(offset);
        q.setLimit(limit);
        q.setSortBy("title");
        q.setSortOrder("asc");
        return q;
    }

    private List<Document> docs(int n) {
        String[] titles = {"C", "A", "B", "D", "E"};
        List<Document> list = new java.util.ArrayList<>();
        for (int i = 0; i < n; i++) {
            list.add(Document.builder().text("正文")
                    .score(0.9 - i * 0.01)
                    .metadata(Map.of("title", titles[i % titles.length], "chunk_id", "c" + i,
                            "book_abbreviation", "CRB"))
                    .build());
        }
        return list;
    }

    private String title(Document d) {
        return String.valueOf(d.getMetadata().get("title"));
    }

    private SearchService service() {
        SearchService s = new SearchService();
        ReflectionTestUtils.setField(s, "spellStore", spellStore);
        ReflectionTestUtils.setField(s, "classStore", classStore);
        ReflectionTestUtils.setField(s, "featStore", featStore);
        ReflectionTestUtils.setField(s, "raceStore", raceStore);
        ReflectionTestUtils.setField(s, "traitStore", traitStore);
        ReflectionTestUtils.setField(s, "equipmentStore", equipmentStore);
        ReflectionTestUtils.setField(s, "skillStore", skillStore);
        ReflectionTestUtils.setField(s, "ruleStore", ruleStore);
        ReflectionTestUtils.setField(s, "filterTranslator", new FilterTranslator());
        BookFilter bookFilter = new BookFilter();
        ReflectionTestUtils.setField(bookFilter, "enabled", true);
        ReflectionTestUtils.setField(bookFilter, "mode", "blacklist");
        ReflectionTestUtils.setField(bookFilter, "books", List.of("?"));
        ReflectionTestUtils.setField(bookFilter, "unknownBookKeep", true);
        ReflectionTestUtils.setField(s, "bookFilter", bookFilter);
        ReflectionTestUtils.setField(s, "topK", 2);
        ReflectionTestUtils.setField(s, "similarityThreshold", 0.5);
        ReflectionTestUtils.setField(s, "enumerationTopK", 500);
        ReflectionTestUtils.setField(s, "classBaseBonus", 0.03);
        ReflectionTestUtils.setField(s, "classExtraCandidates", 3);
        ReflectionTestUtils.setField(s, "introPenalty", 0.03);
        ReflectionTestUtils.setField(s, "filterBlankText", true);
        ReflectionTestUtils.setField(s, "oversizePenalty", 0.02);
        ReflectionTestUtils.setField(s, "oversizeThreshold", 5000);
        ReflectionTestUtils.setField(s, "rerankExtraCandidates", 0);
        ReflectionTestUtils.setField(s, "titleMatchBoost", 0.0);
        ReflectionTestUtils.setField(s, "titleBoostStopwords", List.of());
        s.initStores();
        return s;
    }
}
