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

    // ---------- F-016：请求级来源数量与字节护栏 ----------

    /** 第 51 个唯一来源不编号、不进入 sources；已保留的 50 条编号连续 */
    @Test
    void addWithLimitKeepsAtMostFiftyUniqueSources() {
        List<Document> docs = new java.util.ArrayList<>();
        for (int i = 0; i < 51; i++) {
            docs.add(doc("page_" + i, "chunk_" + i, "text-" + i));
        }

        collector.begin();
        SourceCollector.AddResult result = collector.addWithLimit(docs);

        assertThat(result.acceptedDocs()).hasSize(50);
        assertThat(result.ids()).hasSize(50);
        assertThat(result.ids().get(49)).isEqualTo(50);   // 编号连续，第 50 条 = 50
        assertThat(result.droppedCount()).isEqualTo(1);
        assertThat(result.truncated()).isTrue();
        assertThat(collector.drain()).hasSize(50);
    }

    /** 重复键返回既有编号、不占名额：60 个入参中 10 个重复，50 个唯一全部保留 */
    @Test
    void duplicateKeysDoNotConsumeQuota() {
        collector.begin();
        List<Document> docs = new java.util.ArrayList<>();
        for (int i = 0; i < 50; i++) {
            docs.add(doc("page_" + i, "chunk_" + i, "text-" + i));
        }
        for (int i = 0; i < 10; i++) {              // 重复首批 10 个键
            docs.add(doc("page_" + i, "chunk_" + i, "text-" + i + "-again"));
        }

        SourceCollector.AddResult result = collector.addWithLimit(docs);

        assertThat(result.acceptedDocs()).hasSize(50);
        assertThat(result.droppedCount()).isZero();
        assertThat(result.truncated()).isFalse();
        assertThat(result.ids()).hasSize(60);        // 重复入参同样拿到既有编号
        assertThat(result.ids().subList(50, 60)).containsExactly(1, 2, 3, 4, 5, 6, 7, 8, 9, 10);
        assertThat(collector.drain()).hasSize(50);
    }

    /** 数量已满时后续唯一来源被拒，重复键仍返回既有编号 */
    @Test
    void onceFullNewKeysDroppedButDuplicatesStillNumbered() {
        collector.begin();
        List<Document> first = new java.util.ArrayList<>();
        for (int i = 0; i < 50; i++) {
            first.add(doc("page_" + i, "chunk_" + i, "text-" + i));
        }
        collector.addWithLimit(first);

        SourceCollector.AddResult result = collector.addWithLimit(
                List.of(doc("page_new", "chunk_new", "new"), doc("page_0", "chunk_0", "dup")));

        assertThat(result.ids()).containsExactly(1);
        assertThat(result.acceptedDocs()).isEmpty();
        assertThat(result.droppedCount()).isEqualTo(1);
        assertThat(result.truncated()).isTrue();
        assertThat(collector.drain()).hasSize(50);
    }

    /** 体积按 UTF-8 字节计：100 个中文字 = 300 字节，预算 300 只保留第一条 */
    @Test
    void utf8BytesCountedForChineseText() {
        String chinese = "中".repeat(100);          // 300 UTF-8 字节
        assertThat(chinese.getBytes(java.nio.charset.StandardCharsets.UTF_8)).hasSize(300);

        collector.begin();
        SourceCollector.AddResult result = collector.addWithLimit(
                List.of(doc("page_a", "chunk_a", chinese), doc("page_b", "chunk_b", chinese)),
                50, 300);

        assertThat(result.ids()).containsExactly(1);
        assertThat(result.droppedCount()).isEqualTo(1);
        assertThat(result.truncated()).isTrue();
        assertThat(collector.drain()).extracting(Document::getText).containsExactly(chinese);

        // 边界：剩余预算刚好放得下另一条 300 字节正文
        collector.begin();
        SourceCollector.AddResult exact = collector.addWithLimit(
                List.of(doc("page_c", "chunk_c", chinese), doc("page_d", "chunk_d", chinese)),
                50, 600);
        assertThat(exact.ids()).containsExactly(1, 2);
        assertThat(exact.droppedCount()).isZero();
    }

    /** 单条正文超过剩余预算不保留，后续较小的正文仍可继续占用剩余预算 */
    @Test
    void singleDocOverRemainingBudgetIsDropped() {
        collector.begin();
        SourceCollector.AddResult result = collector.addWithLimit(
                List.of(doc("page_big", "chunk_big", "12345678901"),   // 11 字节 > 预算 10
                        doc("page_small", "chunk_small", "ok")),
                50, 10);

        assertThat(result.ids()).containsExactly(1);     // big 被拒后小正文成为第 1 条，编号仍从 1 连续
        assertThat(result.droppedCount()).isEqualTo(1);
        assertThat(result.acceptedDocs()).extracting(Document::getText).containsExactly("ok");
        assertThat(collector.drain()).extracting(Document::getText).containsExactly("ok");
    }

    /** 超限裁掉中间一条时，编号仍连续且 drain 第 N 条 = 编号 N */
    @Test
    void numberingStaysContiguousAfterDroppedDoc() {
        collector.begin();
        SourceCollector.AddResult result = collector.addWithLimit(
                List.of(doc("page_a", "chunk_a", "1"),
                        doc("page_b", "chunk_b", "12345"),   // 超预算
                        doc("page_c", "chunk_c", "2")),
                50, 2);

        assertThat(result.ids()).containsExactly(1, 2);
        assertThat(collector.drain()).extracting(Document::getText).containsExactly("1", "2");
    }

    /** 并发两请求互不污染：各自的名额、字节与编号独立 */
    @Test
    void concurrentRequestsAreIsolated() throws Exception {
        int docsPerRequest = 50;
        java.util.concurrent.ExecutorService pool = java.util.concurrent.Executors.newFixedThreadPool(2);
        java.util.concurrent.CyclicBarrier barrier = new java.util.concurrent.CyclicBarrier(2);
        try {
            java.util.concurrent.Future<SourceCollector.AddResult> a = pool.submit(() -> {
                collector.begin();
                barrier.await();
                List<Document> docs = new java.util.ArrayList<>();
                for (int i = 0; i < docsPerRequest; i++) {
                    docs.add(doc("a_" + i, "a_chunk_" + i, "a-text-" + i));
                }
                SourceCollector.AddResult r = collector.addWithLimit(docs, docsPerRequest, 10_000);
                barrier.await();
                assertThat(collector.drain()).hasSize(docsPerRequest);
                return r;
            });
            java.util.concurrent.Future<SourceCollector.AddResult> b = pool.submit(() -> {
                collector.begin();
                barrier.await();
                SourceCollector.AddResult r = collector.addWithLimit(
                        List.of(doc("b_0", "b_chunk_0", "x"), doc("b_1", "b_chunk_1", "y")));
                barrier.await();
                assertThat(collector.drain()).hasSize(2);
                return r;
            });

            assertThat(a.get(10, java.util.concurrent.TimeUnit.SECONDS).ids()).hasSize(50);
            SourceCollector.AddResult rb = b.get(10, java.util.concurrent.TimeUnit.SECONDS);
            assertThat(rb.ids()).containsExactly(1, 2);
            assertThat(rb.droppedCount()).isZero();
        } finally {
            pool.shutdownNow();
        }
    }

    /** 护栏截断不是数据缺口：不置 gapReported，显式标记仍生效 */
    @Test
    void truncationDoesNotMarkGap() {
        collector.begin();
        collector.addWithLimit(List.of(doc("page_a", "chunk_a", "1"), doc("page_b", "chunk_b", "2")),
                1, 1_000_000);

        assertThat(collector.wasGapReported()).isFalse();
        collector.markGapReported();
        assertThat(collector.wasGapReported()).isTrue();
    }

    /** 旧 add() 走无上限路径：行为与改造前一致（不限 50 条） */
    @Test
    void addDelegatesToUnlimitedPath() {
        List<Document> docs = new java.util.ArrayList<>();
        for (int i = 0; i < 60; i++) {
            docs.add(doc("page_" + i, "chunk_" + i, "text-" + i));
        }

        collector.begin();
        List<Integer> ids = collector.add(docs);

        assertThat(ids).hasSize(60);
        assertThat(ids.get(59)).isEqualTo(60);
        assertThat(collector.drain()).hasSize(60);
    }

    /** 未 begin 时 addWithLimit 安全：不收集、不抛异常 */
    @Test
    void addWithLimitWithoutBeginIsSafe() {
        SourceCollector.AddResult result = collector.addWithLimit(List.of(doc("page_x", "x")));

        assertThat(result.acceptedDocs()).isEmpty();
        assertThat(result.ids()).isEmpty();
        assertThat(result.droppedCount()).isZero();
        assertThat(result.truncated()).isFalse();
        assertThat(collector.drain()).isEmpty();
    }

    // ---------- F-016 复核：AddResult 可驱动工具裁剪 + 配置化默认上限 ----------

    /** 入参等长的 idsByInput：被拒位置为 null，其余为编号；acceptedDocs 与首次成功项对齐 */
    @Test
    void idsByInputMarksRejectedPositionsWithNull() {
        collector.begin();
        Document a = doc("page_a", "chunk_a", "1");
        Document b = doc("page_b", "chunk_b", "12345");   // 超预算
        Document c = doc("page_c", "chunk_c", "2");
        Document d = doc("page_d", "chunk_d", "3");       // 数量/预算外

        SourceCollector.AddResult result = collector.addWithLimit(
                List.of(a, doc("page_a", "chunk_a", "dup"), b, c, d), 2, 3);

        assertThat(result.idsByInput()).hasSize(5);
        assertThat(result.idsByInput().get(0)).isEqualTo(1);   // a
        assertThat(result.idsByInput().get(1)).isEqualTo(1);   // 重复键
        assertThat(result.idsByInput().get(2)).isNull();       // b 超字节
        assertThat(result.idsByInput().get(3)).isEqualTo(2);   // c
        assertThat(result.idsByInput().get(4)).isNull();       // d 超数量
        assertThat(result.acceptedDocs()).extracting(Document::getText).containsExactly("1", "2");
        assertThat(result.ids()).containsExactly(1, 1, 2);      // 兼容视图：过滤 null
    }

    /** 拒绝原因分项计数，droppedCount 为两者之和 */
    @Test
    void droppedReasonCountsAreSeparated() {
        collector.begin();
        SourceCollector.AddResult result = collector.addWithLimit(
                List.of(doc("p_a", "c_a", "1"),        // 收下
                        doc("p_b", "c_b", "123456"),   // 超字节
                        doc("p_c", "c_c", "2"),        // 收下（剩余预算 1）
                        doc("p_d", "c_d", "34")),      // 超字节（2 > 剩余 1）
                50, 3);

        assertThat(result.droppedByBytes()).isEqualTo(2);
        assertThat(result.droppedByCount()).isZero();
        assertThat(result.droppedCount()).isEqualTo(2);
        assertThat(result.retainedTotal()).isEqualTo(2);
    }

    /** 默认配置入口使用 50 条 / 2MB 常量 */
    @Test
    void defaultLimitsAreFiftyDocsAndTwoMegabytes() {
        assertThat(SourceCollector.DEFAULT_MAX_DOCS).isEqualTo(50);
        assertThat(SourceCollector.DEFAULT_MAX_SOURCES_BYTES).isEqualTo(2L * 1024 * 1024);

        List<Document> docs = new java.util.ArrayList<>();
        for (int i = 0; i < 51; i++) {
            docs.add(doc("page_" + i, "chunk_" + i, "t" + i));
        }
        collector.begin();
        SourceCollector.AddResult result = collector.addWithLimit(docs);
        assertThat(result.acceptedDocs()).hasSize(50);
        assertThat(result.droppedByCount()).isEqualTo(1);
    }

    /** 配置注入的数量上限生效（addWithLimit(docs) 走注入值） */
    @Test
    void configuredDocLimitIsUsedByDefaultEntry() {
        SourceCollector configured = new SourceCollector(2, 1_000_000);
        configured.begin();
        SourceCollector.AddResult result = configured.addWithLimit(
                List.of(doc("page_a", "chunk_a", "a"),
                        doc("page_b", "chunk_b", "b"),
                        doc("page_c", "chunk_c", "c")));

        assertThat(result.acceptedDocs()).hasSize(2);
        assertThat(result.droppedByCount()).isEqualTo(1);
        assertThat(configured.drain()).hasSize(2);
    }

    /** 字节预算跨两次调用累计：第一次占满后第二次同大小正文被拒 */
    @Test
    void byteBudgetAccumulatesAcrossCalls() {
        String sixBytes = "中文";  // 6 UTF-8 字节，预算 10

        collector.begin();
        SourceCollector.AddResult first = collector.addWithLimit(
                List.of(doc("page_a", "chunk_a", sixBytes)), 50, 10);
        SourceCollector.AddResult second = collector.addWithLimit(
                List.of(doc("page_b", "chunk_b", sixBytes)), 50, 10);

        assertThat(first.acceptedDocs()).hasSize(1);
        assertThat(second.droppedByBytes()).isEqualTo(1);
        assertThat(second.retainedTotal()).isEqualTo(1);
        assertThat(collector.drain()).hasSize(1);
    }

    /** 重复键不重复计字节：同键二次传入既不收下也不消耗预算 */
    @Test
    void duplicateKeysDoNotDoubleCountBytes() {
        String sixBytes = "中文";  // 预算 6，刚好一条

        collector.begin();
        SourceCollector.AddResult result = collector.addWithLimit(
                List.of(doc("page_a", "chunk_a", sixBytes),
                        doc("page_a", "chunk_a", sixBytes),
                        doc("page_b", "chunk_b", "x")), 50, 6);

        assertThat(result.idsByInput()).containsExactly(1, 1, null);
        assertThat(result.droppedByBytes()).isEqualTo(1);
        assertThat(result.retainedTotal()).isEqualTo(1);
    }

    /** 正文为 null 计 0 字节，仍可被收下；后续正文正常占用预算 */
    @Test
    void nullTextCountsZeroBytes() {
        Document nullText = org.mockito.Mockito.mock(Document.class);
        org.mockito.Mockito.when(nullText.getText()).thenReturn(null);
        org.mockito.Mockito.when(nullText.getMetadata())
                .thenReturn(Map.of("doc_id", "page_null", "chunk_id", "chunk_null"));

        collector.begin();
        SourceCollector.AddResult result = collector.addWithLimit(
                List.of(nullText, doc("page_x", "chunk_x", "ab")), 50, 1);

        assertThat(result.idsByInput()).containsExactly(1, null);
        assertThat(result.droppedByBytes()).isEqualTo(1);
        assertThat(result.retainedTotal()).isEqualTo(1);
    }

    /** 并发两请求各自紧字节预算：互不借用、互不污染 */
    @Test
    void concurrentRequestsWithTightByteBudgetsAreIsolated() throws Exception {
        java.util.concurrent.ExecutorService pool = java.util.concurrent.Executors.newFixedThreadPool(2);
        java.util.concurrent.CyclicBarrier barrier = new java.util.concurrent.CyclicBarrier(2);
        try {
            java.util.concurrent.Callable<SourceCollector.AddResult> task = () -> {
                collector.begin();
                barrier.await();
                SourceCollector.AddResult r = collector.addWithLimit(
                        List.of(doc("p1", "c1", "中"), doc("p2", "c2", "文"), doc("p3", "c3", "字")),
                        50, 6);
                SourceCollector.AddResult second = collector.addWithLimit(
                        List.of(doc("p4", "c4", "文")), 50, 6);
                assertThat(collector.drain()).hasSize(2);
                assertThat(second.droppedByBytes()).isEqualTo(1);  // 若污染则可能 0 或 2
                return r;
            };
            java.util.concurrent.Future<SourceCollector.AddResult> f1 = pool.submit(task);
            java.util.concurrent.Future<SourceCollector.AddResult> f2 = pool.submit(task);

            for (java.util.concurrent.Future<SourceCollector.AddResult> f : List.of(f1, f2)) {
                SourceCollector.AddResult r = f.get(10, java.util.concurrent.TimeUnit.SECONDS);
                assertThat(r.retainedTotal()).isEqualTo(2);
                assertThat(r.droppedByBytes()).isEqualTo(1);
                assertThat(r.idsByInput()).containsExactly(1, 2, null);
            }
        } finally {
            pool.shutdownNow();
        }
    }

    /** 新结果字段默认值：未 begin 时 retainedTotal=0、无拒绝 */
    @Test
    void addWithLimitWithoutBeginReturnsEmptyAddResult() {
        SourceCollector.AddResult result = collector.addWithLimit(List.of(doc("page_x", "x")));

        assertThat(result.idsByInput()).isEmpty();
        assertThat(result.droppedByCount()).isZero();
        assertThat(result.droppedByBytes()).isZero();
        assertThat(result.retainedTotal()).isZero();
        assertThat(result.truncated()).isFalse();
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
