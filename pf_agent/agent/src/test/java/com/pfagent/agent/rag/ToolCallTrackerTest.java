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

    /** 请求上下文只读访问：未 begin 时为空（调用方据此跳过请求级写入） */
    @Test
    void currentContextIsEmptyWithoutBegin() {
        ToolCallTracker tracker = new ToolCallTracker();

        assertThat(tracker.currentContext()).isEmpty();
    }

    /** begin 后可取到会话 ID 与请求级问题，供门禁事件等请求级遥测复用 */
    @Test
    void currentContextExposesSessionConversationAndQuestion() {
        ToolCallTracker tracker = new ToolCallTracker();
        tracker.begin("cid-ctx", "CRB 所有专长");

        assertThat(tracker.currentContext()).hasValueSatisfying(ctx -> {
            assertThat(ctx.conversationId()).isEqualTo("cid-ctx");
            assertThat(ctx.question()).isEqualTo("CRB 所有专长");
            assertThat(ctx.requestId()).isNotBlank();
            assertThat(ctx.confirmationEligible()).isTrue();
            assertThat(ctx.requestSequence()).isPositive();
        });
    }

    /** AKN-024：regenerate 没有新用户轮次，不具备宽查询确认资格；requestId/序号仍独立生成 */
    @Test
    void beginRegenerateIsNotConfirmationEligibleButKeepsFreshRequestId() {
        ToolCallTracker tracker = new ToolCallTracker();
        tracker.begin("cid-regen", "CRB 所有专长");
        String askRequestId = tracker.currentContext().orElseThrow().requestId();
        long askSequence = tracker.currentContext().orElseThrow().requestSequence();

        tracker.beginRegenerate("cid-regen", "CRB 所有专长");

        assertThat(tracker.currentContext()).hasValueSatisfying(ctx -> {
            assertThat(ctx.conversationId()).isEqualTo("cid-regen");
            assertThat(ctx.question()).isEqualTo("CRB 所有专长");
            assertThat(ctx.confirmationEligible()).isFalse();
            assertThat(ctx.requestId()).isNotBlank().isNotEqualTo(askRequestId);
            assertThat(ctx.requestSequence()).isGreaterThan(askSequence);
        });
    }

    /** drain / clear 之后上下文随之清空，不把上一请求的会话泄漏给下一次写入 */
    @Test
    void currentContextIsEmptyAfterDrainOrClear() {
        ToolCallTracker tracker = new ToolCallTracker();

        tracker.begin("cid-drain", "q1");
        tracker.drain();
        assertThat(tracker.currentContext()).isEmpty();

        tracker.begin("cid-clear", "q2");
        tracker.clear();
        assertThat(tracker.currentContext()).isEmpty();
    }

    /** AKN-023：LLM 调用次数与端到端累计耗时（含网络）按请求累计，字段名对齐 M34 分析脚本 */
    @Test
    void recordLlmCallAccumulatesCountAndDuration() {
        ToolCallTracker tracker = new ToolCallTracker();
        tracker.begin("cid-1", "武僧清规有哪些内容");

        tracker.recordLlmCall(1200);
        tracker.recordLlmCall(800);

        ToolCallTracker.RequestSummary summary = tracker.summary().orElseThrow();
        assertThat(summary.recordType()).isEqualTo("request_summary");
        assertThat(summary.requestId()).startsWith("req-");
        assertThat(summary.conversationId()).isEqualTo("cid-1");
        assertThat(summary.question()).isEqualTo("武僧清规有哪些内容");
        assertThat(summary.llmCallCount()).isEqualTo(2);
        assertThat(summary.llmDurationMs()).isEqualTo(2000);
        assertThat(summary.totalDurationMs()).isGreaterThanOrEqualTo(0);
        assertThat(summary.timestamp()).isNotBlank();
    }

    /** 工具调用次数/累计耗时/轮次汇总：轮次按去重计（同轮多个工具算一轮） */
    @Test
    void summaryAggregatesToolCallsAndRounds() {
        ToolCallTracker tracker = new ToolCallTracker();
        tracker.begin("cid-1", "q");

        tracker.record("vectorSearch", "{}", true, 5, 10, 0);
        tracker.record("searchByMetadata", "{}", true, 7, 10, 0);
        tracker.record("reportDataGap", "{}", true, 1, 10, 1);

        ToolCallTracker.RequestSummary summary = tracker.summary().orElseThrow();
        assertThat(summary.toolCallCount()).isEqualTo(3);
        assertThat(summary.toolTotalMs()).isEqualTo(13);
        assertThat(summary.toolRounds()).isEqualTo(2);
    }

    /** 工具记录只带 requestId 分组键；请求级耗时只在摘要记录里出现一次（不重复写行） */
    @Test
    void drainAttachesRequestIdToEveryRecord() {
        ToolCallTracker tracker = new ToolCallTracker();
        tracker.begin("cid-1", "q");
        tracker.recordLlmCall(100);
        tracker.recordLlmCall(200);
        tracker.record("vectorSearch", "{}", true, 12, 10, 0);
        tracker.record("searchByMetadata", "{}", false, 8, 10, 1);
        String requestId = tracker.summary().orElseThrow().requestId();

        List<ToolCallRecord> records = tracker.drain();

        assertThat(records).hasSize(2);
        assertThat(records).allSatisfy(r -> assertThat(r.requestId()).isEqualTo(requestId));
    }

    /** 同一会话的两次问答必须拿到不同 requestId，报告据此分开统计；AKN-024 门禁据此区分同轮重试与后续轮次 */
    @Test
    void beginGeneratesDistinctRequestIdsPerRequest() {
        ToolCallTracker tracker = new ToolCallTracker();
        tracker.begin("cid-1", "q");
        String first = tracker.summary().orElseThrow().requestId();
        tracker.drain();
        tracker.begin("cid-1", "q");
        String second = tracker.summary().orElseThrow().requestId();

        assertThat(first).isNotEqualTo(second);
    }

    /** 无工具调用也可取请求级耗时汇总（如 LLM 直接作答的问答） */
    @Test
    void summaryIsAvailableWithoutToolCalls() {
        ToolCallTracker tracker = new ToolCallTracker();
        tracker.begin("cid-1", "q");
        tracker.recordLlmCall(500);

        ToolCallTracker.RequestSummary summary = tracker.summary().orElseThrow();
        assertThat(summary.llmCallCount()).isEqualTo(1);
        assertThat(summary.llmDurationMs()).isEqualTo(500);
        assertThat(summary.toolCallCount()).isZero();
        assertThat(summary.toolRounds()).isZero();
        assertThat(tracker.drain()).isEmpty();
    }

    /** 未 begin / drain 后：summary 为空，调用方跳过请求级输出而不是写空会话事件 */
    @Test
    void summaryIsEmptyWithoutSessionOrAfterDrain() {
        ToolCallTracker tracker = new ToolCallTracker();
        assertThat(tracker.summary()).isEmpty();

        tracker.recordLlmCall(10);
        assertThat(tracker.summary()).isEmpty();

        tracker.begin("cid-1", "q");
        tracker.drain();
        assertThat(tracker.summary()).isEmpty();
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
