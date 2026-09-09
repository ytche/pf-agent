package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.springframework.ai.document.Document;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * SourceCollector 单元测试
 *
 * 覆盖请求级来源收集（设计 §6）：
 *  - begin/add/drain 生命周期：多步查询工具命中多次的来源统一进入折叠区
 *  - v1.5（B4）按 chunk_id 去重（AKN-008 修正：原按 doc_id 页面级去重，同页多 chunk
 *    只保留先到者，title 过滤精确命中的锚点被 vectorSearch 同页邻居挤出）：
 *    同一 chunk 多步命中只进一次，同 doc_id 不同 chunk 全部保留
 *  - gap 标记：markGapReported / wasGapReported（请求级 ThreadLocal 隔离）
 *  - 防御：未 begin 时 drain 返回空、add(null) 安全
 */
class SourceCollectorTest {

    private final SourceCollector collector = new SourceCollector();

    /** begin 后 add 再 drain：按 chunk_id 去重，同 doc_id 不同 chunk 全保留 */
    @Test
    void beginAddDrainDeduplicatesByChunkId() {
        Document a = doc("page_a", "chunk_a", "a");
        Document a2 = doc("page_a", "chunk_a2", "a 另一个 chunk 命中"); // 同 doc_id 不同 chunk_id → 保留
        Document sameChunk = doc("page_a", "chunk_a", "a 同 chunk 命中"); // 同 chunk_id → 去重
        Document b = doc("page_b", "chunk_b", "b");

        collector.begin();
        collector.add(List.of(a, a2, sameChunk));
        collector.add(List.of(b));

        List<Document> drained = collector.drain();
        assertThat(drained).hasSize(3);
        assertThat(drained.get(0).getText()).isEqualTo("a");                // LinkedHashMap 保序，先到者胜
        assertThat(drained.get(1).getText()).isEqualTo("a 另一个 chunk 命中");
        assertThat(drained.get(2).getText()).isEqualTo("b");
    }

    /** 缺 chunk_id 的 doc（如手工构造）兜底 doc_id 键，不 null 合并；同 doc_id 合并为同号 */
    @Test
    void docsMissingChunkIdFallbackToDocIdKey() {
        Document a = doc("page_x", "x");
        Document b = doc("page_y", "y");

        collector.begin();
        assertThat(collector.add(List.of(a, b))).containsExactly(1, 2);

        List<Document> drained = collector.drain();
        assertThat(drained).hasSize(2);
    }

    // ---------- SP4 D1：来源编号分配 ----------

    /** 新键按首次出现序分配递增编号（1-based），返回列表与入参等长 */
    @Test
    void addAssignsIncreasingNumbersToNewKeys() {
        collector.begin();
        List<Integer> first = collector.add(List.of(doc("page_a", "chunk_a", "a"), doc("page_a", "chunk_b", "b")));
        List<Integer> second = collector.add(List.of(doc("page_c", "chunk_c", "c")));

        assertThat(first).containsExactly(1, 2);
        assertThat(second).containsExactly(3);
    }

    /** 重复 key（同 chunk_id）返回既有编号、不占新号；缺 chunk_id 兜底 doc_id 同理 */
    @Test
    void addReturnsSameNumberForDuplicateKey() {
        collector.begin();
        Document a = doc("page_a", "chunk_a", "a");
        Document sameChunk = doc("page_a", "chunk_a", "a 同 chunk 命中");
        Document fallbackDocId = doc("page_x", "x 无 chunk_id");

        List<Integer> ids = collector.add(List.of(a, sameChunk, fallbackDocId, doc("page_x", "x 同 doc_id")));

        assertThat(ids).containsExactly(1, 1, 2, 2);
        assertThat(collector.drain()).extracting(Document::getText)
                .containsExactly("a", "x 无 chunk_id");  // 重复键保留首次命中
    }

    /** 编号在跨轮之间重置（每请求从 1 重新分配，互不污染） */
    @Test
    void numbersRestartPerRequestRound() {
        collector.begin();
        assertThat(collector.add(List.of(doc("page_a", "chunk_a", "a")))).containsExactly(1);
        collector.drain();

        collector.begin();
        assertThat(collector.add(List.of(doc("page_b", "chunk_b", "b")))).containsExactly(1);
    }

    /** 编号序 = drain 序（D7）：先 add 的编号小，drain 输出与编号一一对齐 */
    @Test
    void numberOrderMatchesDrainOrder() {
        collector.begin();
        collector.add(List.of(doc("page_a", "chunk_a", "a")));
        List<Integer> ids = collector.add(List.of(doc("page_b", "chunk_b", "b"), doc("page_a", "chunk_a", "a 重复")));

        assertThat(ids).containsExactly(2, 1);          // b 新键=2，a 重复=1
        assertThat(collector.drain()).extracting(Document::getText)
                .containsExactly("a", "b");              // drain 第 N 条 = 编号 N（1-based）
    }

    /** drain 后再 begin 不互相污染（请求级隔离） */
    @Test
    void drainThenBeginIsolatedPerRequest() {
        collector.begin();
        collector.add(List.of(doc("page_x", "x")));
        collector.drain();

        collector.begin();
        collector.add(List.of(doc("page_y", "y")));

        List<Document> drained = collector.drain();
        assertThat(drained).extracting(Document::getText).containsExactly("y");
    }

    /** add null 时安全不抛异常并返回空编号列表 */
    @Test
    void addNullIsSafe() {
        collector.begin();
        assertThat(collector.add(null)).isEmpty();
        assertThat(collector.drain()).isEmpty();
    }

    /** 未 begin 时 drain 返回空列表 */
    @Test
    void drainWithoutBeginReturnsEmptyList() {
        assertThat(collector.drain()).isEmpty();
    }

    /** 未 begin 时 add 返回空编号列表（防御，不收集） */
    @Test
    void addWithoutBeginReturnsEmptyNumbers() {
        assertThat(collector.add(List.of(doc("page_x", "x")))).isEmpty();
        assertThat(collector.drain()).isEmpty();
    }

    /** 默认状态未标记 gap */
    @Test
    void defaultStateNotMarkedGap() {
        assertThat(collector.wasGapReported()).isFalse();
    }

    /** markGapReported 后 gap 标记为 true */
    @Test
    void markGapReportedFlipsFlag() {
        collector.begin();
        collector.markGapReported();
        assertThat(collector.wasGapReported()).isTrue();
    }

    /** gap 标记按请求级隔离 */
    @Test
    void gapFlagIsolatedPerRequest() {
        collector.begin();
        collector.markGapReported();
        collector.drain();
        assertThat(collector.wasGapReported()).isFalse(); // drain 后本请求状态清空
    }

    /** clear 清空请求状态，异常路径兜底 */
    @Test
    void clearResetsRequestStateForErrorFallback() {
        collector.begin();
        collector.add(List.of(doc("page_x", "x")));
        collector.markGapReported();

        collector.clear();

        assertThat(collector.wasGapReported()).isFalse();
        assertThat(collector.drain()).isEmpty(); // current 已清空
    }

    private Document doc(String docId, String text) {
        return doc(docId, null, text);
    }

    private Document doc(String docId, String chunkId, String text) {
        Map<String, Object> md = new java.util.HashMap<>();
        md.put("doc_id", docId);
        if (chunkId != null) {
            md.put("chunk_id", chunkId);
        }
        return Document.builder().text(text).metadata(md).build();
    }
}
