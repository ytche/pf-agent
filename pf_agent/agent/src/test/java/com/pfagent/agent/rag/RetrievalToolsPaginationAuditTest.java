package com.pfagent.agent.rag;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

/**
 * AKN-015 分页元数据补全 —— 测试层独立审计用例（tester 补充，非 coder 用例）
 *
 * 补的是 coder 新增 5 个用例的覆盖盲区：
 *  - 第二页（offset≠0）提示里的区间与 next_offset 是否随 offset 前移（coder 用例只覆盖 offset=0）
 *  - 字符截断时 next_offset 必须等于"实际展示条数 + offset"，而不是 0 或 limit（coder 用例只做
 *    containsPattern("query.offset=\\d+")，恒真，next_offset 退化为 0 也能通过 → 会无限翻页）
 *  - 最后一页完整展示 → 无提示；hasMore 边界（offset+size == totalCount、offset 越界）
 *  - 旧 Map 重载（非 @Tool）分页提示的兼容行为
 */
@ExtendWith(MockitoExtension.class)
class RetrievalToolsPaginationAuditTest {

    private static final Pattern RANGE = Pattern.compile("本次返回第 (\\d+)~(\\d+) 条");
    private static final Pattern NEXT_OFFSET = Pattern.compile("query\\.offset=(\\d+)");
    private static final Pattern NUMBERED_LINE = Pattern.compile("(?m)^\\d+\\. ");

    @Mock
    private SearchService searchService;
    @Mock
    private SourceCollector collector;

    // ---------- 1. offset≠0：第二页提示 ----------

    @Test
    @DisplayName("第二页（offset=10/limit=10/total=30，无字符截断）：区间 11~20，next_offset=20")
    void secondPageHintRangeAndNextOffsetFollowOffset() {
        stubPaged("spell", docs(10), 30, 10, 10);

        String result = tools(100000).searchByMetadata("spell", query());

        assertThat(result).contains("共 30 条", "has_more=true");
        assertThat(result).contains("本次返回第 11~20 条");
        assertThat(result).contains("query.offset=20");
    }

    @Test
    @DisplayName("最后一页完整展示（offset=20/total=30/page=10）：不出现分页提示")
    void lastPageCompleteHasNoHint() {
        stubPaged("spell", docs(10), 30, 20, 10);

        String result = tools(100000).searchByMetadata("spell", query());

        assertThat(result).doesNotContain("has_more");
        assertThat(result).doesNotContain("query.offset");
        assertThat(numberedLines(result)).isEqualTo(10);
    }

    @Test
    @DisplayName("单页恰好返回全部（offset=0/limit=5/total=5）：不出现分页提示")
    void exactSinglePageHasNoHint() {
        stubPaged("spell", docs(5), 5, 0, 5);

        String result = tools(100000).searchByMetadata("spell", query());

        assertThat(result).doesNotContain("has_more");
        assertThat(numberedLines(result)).isEqualTo(5);
    }

    // ---------- 2. 字符截断：提示内部一致性（强断言，替代 coder 的恒真正则） ----------

    @Test
    @DisplayName("字符截断（第一页）：区间起点=offset+1，终点=next_offset，next_offset>0 且=展示条数")
    void charTruncatedFirstPageHintInternallyConsistent() {
        stubPaged("spell", docs(10), 10, 0, 10);

        String result = tools(1500, 260).searchByMetadata("spell", query());

        int shown = numberedLines(result);
        assertThat(shown).isBetween(1, 9);   // 确实发生了字符截断
        assertThat(hintStart(result)).isEqualTo(1);
        assertThat(hintEnd(result)).isEqualTo(shown);           // 终点 = 实际展示条数
        assertThat(hintNextOffset(result)).isEqualTo(shown);    // next_offset 前进，不能是 0
        assertThat(result).contains("共 10 条", "has_more=true");
    }

    @Test
    @DisplayName("字符截断（第二页）：起点=offset+1，终点=offset+展示条数，next_offset=终点")
    void charTruncatedSecondPageHintInternallyConsistent() {
        stubPaged("spell", docs(10), 20, 10, 10);

        String result = tools(1500, 260).searchByMetadata("spell", query());

        int shown = numberedLines(result);
        assertThat(shown).isBetween(1, 9);
        assertThat(hintStart(result)).isEqualTo(11);
        assertThat(hintEnd(result)).isEqualTo(10 + shown);
        assertThat(hintNextOffset(result)).isEqualTo(10 + shown);
        assertThat(result).contains("共 20 条");
    }

    @Test
    @DisplayName("字符截断且当页即末页（offset=10/total=15/page=5）：提示只指向页内剩余条目")
    void charTruncatedOnLastPageStillHintsRemainingItems() {
        stubPaged("spell", docs(5), 15, 10, 5);

        String result = tools(1500, 200).searchByMetadata("spell", query());

        int shown = numberedLines(result);
        assertThat(shown).isBetween(1, 4);
        assertThat(hintNextOffset(result)).isEqualTo(10 + shown); // 续取仍在最后一个 offset 段内
        assertThat(hintNextOffset(result)).isLessThan(15);
    }

    // ---------- 3. 旧 Map 重载（非 @Tool）兼容性 ----------

    @Test
    @DisplayName("旧 Map 重载：结果完整时不带分页提示（与旧行为兼容）")
    void legacyMapOverloadCompleteResultHasNoHint() {
        when(searchService.searchByMetadata(eq("spell"), anyMap()))
                .thenReturn(docs(2));
        stubAddSequential();

        String result = tools(150000).searchByMetadata("spell", Map.of("book", "CRB"));

        assertThat(result).contains("法术1", "法术2");
        assertThat(result).doesNotContain("has_more");
        assertThat(result).doesNotContain("query.offset");
    }

    @Test
    @DisplayName("旧 Map 重载：字符截断时 next_offset 从展示条数继续（totalCount=当页大小，不误报总数）")
    void legacyMapOverloadCharTruncatedNextOffsetResumesFromShown() {
        when(searchService.searchByMetadata(eq("spell"), anyMap()))
                .thenReturn(docs(50));
        stubAddSequential();

        String result = tools(150000, 300).searchByMetadata("spell", Map.of("book", "CRB"));

        int shown = numberedLines(result);
        assertThat(shown).isBetween(1, 49);
        assertThat(result).contains("共 50 条");  // 旧重载 totalCount = 当页大小（无分页语义）
        assertThat(hintNextOffset(result)).isEqualTo(shown);
        assertThat(hintStart(result)).isEqualTo(1);
    }

    // ---------- 4. hasMore() 边界 ----------

    @Test
    @DisplayName("hasMore 边界：offset+page==total 为 false；越界 offset 不抛异常且为 false")
    void hasMoreBoundaries() {
        assertThat(paged(docs(10), 10, 0, 10).hasMore()).isFalse();
        assertThat(paged(docs(10), 30, 20, 10).hasMore()).isFalse();
        assertThat(paged(docs(10), 30, 10, 10).hasMore()).isTrue();
        assertThat(paged(docs(1), 30, 10, 10).hasMore()).isTrue();
        assertThat(paged(List.of(), 30, 30, 10).hasMore()).isFalse();   // offset 越界（==total）
        assertThat(paged(List.of(), 30, 40, 10).hasMore()).isFalse();   // offset 越界（>total）
        assertThat(paged(List.of(), 0, 0, 10).hasMore()).isFalse();     // 空结果
    }

    @Test
    @DisplayName("负 offset 被钳制为 0：提示区间从第 1 条开始（不出现 第 0~ 或负号）")
    void negativeOffsetClampedToZeroInHint() {
        stubPaged("spell", docs(3), 10, 0, 3);  // service 钳制后回传 offset=0（模拟负 offset 入参）

        String result = tools(100000).searchByMetadata("spell", query());

        assertThat(result).contains("本次返回第 1~3 条");
        assertThat(result).doesNotContain("第 0~");
        assertThat(result).doesNotContain("第 -");
    }

    // ---------- 5. 缺陷回归 ----------

    /** AKN015-T2（已修）：shown==0 时不再输出退化区间/原地 offset，改引导 getEntryById */
    @Test
    void zeroShownShouldNotEmitDegenerateRangeAndStuckOffset() {
        stubPaged("spell", docs(10), 10, 0, 10);

        // metadataResultChars 小于单行长度 → 一条都展示不出来
        String result = tools(1500, 10).searchByMetadata("spell", query());

        assertThat(result).contains("本页无条目可展示", "getEntryById", "chunkId=\"spell-1\"",
                "offset=0", "limit=10");
        assertThat(result).doesNotContainPattern("第 \\d+~\\d+ 条");
        assertThat(result).doesNotContain("query.offset", "has_more", "本次返回");
    }

    @Test
    void offsetBeyondTotalShouldTellExhaustedInsteadOfNoHit() {
        when(searchService.searchByMetadataPaged(eq("spell"), any(MetadataSearchQuery.class)))
                .thenReturn(paged(List.of(), 5, 5, 10));

        String result = tools(150000).searchByMetadata("spell", query());

        assertThat(result).doesNotContain("无命中");   // 当前实现返回"无命中。建议：减少一个过滤条件…"
        assertThat(result).contains("已翻完", "共 5 条");
    }

    // ---------- harness ----------

    private MetadataSearchQuery query() {
        MetadataSearchQuery q = new MetadataSearchQuery();
        q.setFilters(Map.of("book", "CRB"));
        // F-026：仅书宽查询，需显式放行才能继续覆盖原有翻页断言
        q.setAllowBroadQuery(true);
        q.setLimit(10);
        q.setOffset(0);
        return q;
    }

    private void stubPaged(String module, List<Document> page, int total, int offset, int limit) {
        when(searchService.searchByMetadataPaged(eq(module), any(MetadataSearchQuery.class)))
                .thenReturn(paged(page, total, offset, limit));
        stubAddSequential();
    }

    private SearchService.PagedResult paged(List<Document> page, int total, int offset, int limit) {
        return new SearchService.PagedResult(page, total, offset, limit);
    }

    private List<Document> docs(int n) {
        List<Document> list = new ArrayList<>();
        for (int i = 1; i <= n; i++) {
            list.add(Document.builder().text("正文")
                    .metadata(Map.of("title", "法术" + i, "book_abbreviation", "CRB",
                            "chunk_id", "spell-" + i))
                    .build());
        }
        return list;
    }

    private void stubAddSequential() {
        when(collector.add(any())).thenAnswer(inv -> {
            List<Document> docs = inv.getArgument(0);
            List<Integer> seq = new ArrayList<>(docs.size());
            for (int n = 1; n <= docs.size(); n++) {
                seq.add(n);
            }
            return seq;
        });
    }

    private RetrievalTools tools(int metadataResultChars) {
        return tools(1500, metadataResultChars);
    }

    private RetrievalTools tools(int vectorResultChars, int metadataResultChars) {
        RetrievalTools t = new RetrievalTools();
        ReflectionTestUtils.setField(t, "searchService", searchService);
        ReflectionTestUtils.setField(t, "collector", collector);
        ReflectionTestUtils.setField(t, "filterTranslator", new FilterTranslator());
        ReflectionTestUtils.setField(t, "vectorResultChars", vectorResultChars);
        ReflectionTestUtils.setField(t, "metadataResultChars", metadataResultChars);
        ReflectionTestUtils.setField(t, "entryResultChars", 8000);
        ReflectionTestUtils.setField(t, "metadataDefaultLimit", 50);
        ReflectionTestUtils.setField(t, "gapsListDefaultLimit", 20);
        return t;
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
        Matcher m = RANGE.matcher(text);
        assertThat(m.find()).as("应存在分页提示").isTrue();
        return Integer.parseInt(m.group(1));
    }

    private int hintEnd(String text) {
        Matcher m = RANGE.matcher(text);
        assertThat(m.find()).as("应存在分页提示").isTrue();
        return Integer.parseInt(m.group(2));
    }

    private int hintNextOffset(String text) {
        Matcher m = NEXT_OFFSET.matcher(text);
        assertThat(m.find()).as("应存在 next_offset 提示").isTrue();
        return Integer.parseInt(m.group(1));
    }
}
