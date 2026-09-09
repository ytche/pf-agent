package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * ToolCallTracker 单元测试（F-006 工具调用计数）
 *
 * 覆盖：begin/record/drain 生命周期、未 begin 安全忽略、drain 清空、
 * ThreadLocal 并发隔离（ChatService 单例多请求互不污染）。
 */
class ToolCallTrackerTest {

    @Test
    void recordAppendsToSessionContextAndDrainReturnsAll() {
        ToolCallTracker tracker = new ToolCallTracker();
        tracker.begin("cid-1", "火球术射程？");

        tracker.record("vectorSearch", "{\"module\":\"spell\"}", true, 12, 150, 0);
        tracker.record("searchByMetadata", "{\"module\":\"spell\"}", false, 3, 30, 1);

        List<ToolCallRecord> records = tracker.drain();
        assertThat(records).hasSize(2);

        ToolCallRecord first = records.get(0);
        assertThat(first.conversationId()).isEqualTo("cid-1");
        assertThat(first.question()).isEqualTo("火球术射程？");
        assertThat(first.toolName()).isEqualTo("vectorSearch");
        assertThat(first.arguments()).isEqualTo("{\"module\":\"spell\"}");
        assertThat(first.success()).isTrue();
        assertThat(first.durationMs()).isEqualTo(12);
        assertThat(first.resultChars()).isEqualTo(150);
        assertThat(first.round()).isEqualTo(0);
        assertThat(first.id()).startsWith("tc-");
        assertThat(first.timestamp()).isNotBlank();

        ToolCallRecord second = records.get(1);
        assertThat(second.toolName()).isEqualTo("searchByMetadata");
        assertThat(second.success()).isFalse();
        assertThat(second.round()).isEqualTo(1);
    }

    @Test
    void recordWithoutBeginIsIgnoredSafely() {
        ToolCallTracker tracker = new ToolCallTracker();

        tracker.record("vectorSearch", "{}", true, 1, 1, 0);

        assertThat(tracker.drain()).isEmpty();
        assertThat(tracker.hasCalls()).isFalse();
    }

    @Test
    void drainClearsSessionState() {
        ToolCallTracker tracker = new ToolCallTracker();
        tracker.begin("cid", "q");
        tracker.record("vectorSearch", "{}", true, 1, 1, 0);

        assertThat(tracker.drain()).hasSize(1);
        assertThat(tracker.drain()).isEmpty();
        assertThat(tracker.hasCalls()).isFalse();
    }

    @Test
    void hasCallsReflectsCurrentSession() {
        ToolCallTracker tracker = new ToolCallTracker();
        assertThat(tracker.hasCalls()).isFalse();

        tracker.begin("cid", "q");
        assertThat(tracker.hasCalls()).isFalse();

        tracker.record("vectorSearch", "{}", true, 1, 1, 0);
        assertThat(tracker.hasCalls()).isTrue();
    }

    @Test
    void clearIsIdempotent() {
        ToolCallTracker tracker = new ToolCallTracker();
        tracker.begin("cid", "q");
        tracker.record("vectorSearch", "{}", true, 1, 1, 0);

        tracker.clear();
        assertThat(tracker.drain()).isEmpty();

        tracker.clear(); // 幂等：二次 clear 不抛
    }

    /** ThreadLocal 隔离：单例 ChatService 并发多请求时各记录各的，互不污染 */
    @Test
    void concurrentSessionsDoNotPolluteEachOther() throws Exception {
        ToolCallTracker tracker = new ToolCallTracker();
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);

        Future<List<ToolCallRecord>> f1 = pool.submit(() -> {
            start.await();
            tracker.begin("cid-A", "问题A");
            tracker.record("vectorSearch", "{\"q\":\"A\"}", true, 1, 1, 0);
            return tracker.drain();
        });
        Future<List<ToolCallRecord>> f2 = pool.submit(() -> {
            start.await();
            tracker.begin("cid-B", "问题B");
            tracker.record("searchByMetadata", "{\"q\":\"B\"}", true, 2, 2, 0);
            tracker.record("vectorSearch", "{\"q\":\"B2\"}", false, 3, 3, 1);
            return tracker.drain();
        });

        start.countDown();
        List<ToolCallRecord> r1 = f1.get(5, TimeUnit.SECONDS);
        List<ToolCallRecord> r2 = f2.get(5, TimeUnit.SECONDS);
        pool.shutdownNow();

        assertThat(r1).hasSize(1);
        assertThat(r1.get(0).conversationId()).isEqualTo("cid-A");
        assertThat(r1.get(0).toolName()).isEqualTo("vectorSearch");

        assertThat(r2).hasSize(2);
        assertThat(r2).extracting(ToolCallRecord::conversationId)
                .containsOnly("cid-B");
        assertThat(r2.get(1).success()).isFalse();
    }
}
