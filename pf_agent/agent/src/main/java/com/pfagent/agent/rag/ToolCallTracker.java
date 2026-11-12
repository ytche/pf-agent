package com.pfagent.agent.rag;

import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 请求级工具调用追踪器（F-006 / AKN-023）
 *
 * 与 SourceCollector 同型：ChatService 是单例、并发请求互不污染，用 ThreadLocal
 * 收集「本请求（一次 ask()）」的全部工具调用明细与分段耗时。ChatService 入口 begin()，
 * 每个工具执行后 record()，每次 LLM 调用后 recordLlmCall()，出口 drain() 取走明细
 * 交给 ToolCallRecorder 落盘，summary() 交给 ToolCallRecorder 写请求级摘要并打日志。
 *
 * 耗时口径（AKN-023，只测量不优化）：
 *  - totalDurationMs：begin → 出口的墙钟耗时，含 LLM、工具与落库；
 *  - llmCallCount / llmDurationMs：LLM 调用次数与端到端累计耗时（含网络，
 *    无法再拆分服务端耗时）；
 *  - toolCallCount / toolTotalMs / toolRounds：工具调用次数、执行段耗时之和与轮数。
 *
 * 请求分组：begin() 生成唯一 requestId（同会话多次问答不混淆），工具明细只带
 * requestId；请求级耗时只写在 {@link RequestSummary} 一条摘要里，不重复到每条工具行。
 *
 * 仅在记录，不落盘——落盘职责归 ToolCallRecorder（关注点分离，
 * tracker 保持纯内存可测）。
 */
@Component
public class ToolCallTracker {

    /** 秒精度 ISO 时间戳（与分析脚本/FeedbackRecorder 对齐） */
    private static final DateTimeFormatter TIMESTAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

    /** 请求级摘要记录类型（qa/tool_calls_report.py 据此排除工具统计） */
    public static final String REQUEST_SUMMARY_TYPE = "request_summary";

    /** 全局单调请求序号：用于门禁判定「旧请求」不得覆盖新状态（与并发调度顺序无关） */
    private static final AtomicLong REQUEST_SEQUENCE = new AtomicLong();

    /** 本请求的会话上下文 + 调用明细；未 begin 时为 null（record 安全忽略） */
    private final ThreadLocal<SessionState> current = new ThreadLocal<>();

    /** 单个工具调用的原始明细（requestId 在 drain 时统一补齐） */
    private record CallDetail(String id, String toolName, String arguments, boolean success,
                              long durationMs, int resultChars, int round, String timestamp) {
    }

    /** 本请求的可变追踪状态 */
    private static final class SessionState {
        private final String requestId = generateRequestId();
        private final long requestSequence = REQUEST_SEQUENCE.incrementAndGet();
        private final String conversationId;
        private final String question;
        private final boolean confirmationEligible;
        private final long startNanos = System.nanoTime();
        private final List<CallDetail> calls = new ArrayList<>();
        private final Set<Integer> toolRounds = new LinkedHashSet<>();
        private int llmCallCount;
        private long llmDurationMs;
        private long toolTotalMs;

        private SessionState(String conversationId, String question, boolean confirmationEligible) {
            this.conversationId = conversationId;
            this.question = question;
            this.confirmationEligible = confirmationEligible;
        }

        private long elapsedMs() {
            return (System.nanoTime() - startNanos) / 1_000_000;
        }

        private RequestSummary toSummary() {
            return new RequestSummary(REQUEST_SUMMARY_TYPE, requestId, conversationId, question,
                    LocalDateTime.now().format(TIMESTAMP), elapsedMs(), llmCallCount, llmDurationMs,
                    calls.size(), toolTotalMs, toolRounds.size());
        }

        private ToolCallRecord toRecord(CallDetail call) {
            return new ToolCallRecord(call.id(), requestId, conversationId, question, call.toolName(),
                    call.arguments(), call.success(), call.durationMs(), call.resultChars(),
                    call.round(), call.timestamp());
        }
    }

    /**
     * 请求级耗时摘要（AKN-023）：每次问答一条，写入 tool_calls.jsonl 供
     * qa/tool_calls_report.py 按请求聚合；字段名对齐已合并 M34 的
     * totalDurationMs / llmCallCount / llmDurationMs。
     */
    public record RequestSummary(String recordType, String requestId, String conversationId,
                                 String question, String timestamp, long totalDurationMs,
                                 int llmCallCount, long llmDurationMs, int toolCallCount,
                                 long toolTotalMs, int toolRounds) {
    }

    /**
     * 本请求的只读上下文（requestId + 请求序号 + 会话 ID + 请求级问题 + 确认资格），
     * 供请求级遥测与宽查询门禁取用。
     *
     * requestId 每次 begin 生成，用于请求分组；requestSequence 全局单调递增，
     * 用于门禁丢弃「旧请求」的过期写回；confirmationEligible 表示这是否是真实
     * 新用户轮次，决定该请求能否确认宽查询指纹（regenerate 不是新用户轮次）。
     */
    public record RequestContext(String requestId, long requestSequence, String conversationId,
                                 String question, boolean confirmationEligible) {
    }

    /** 普通问答入口：真实新用户轮次，具备宽查询确认资格 */
    public void begin(String conversationId, String question) {
        begin(conversationId, question, true);
    }

    /**
     * 重新生成入口（F-020）：沿用同一用户轮次，没有新的用户消息或范围确认，
     * 因此不具备宽查询确认资格；requestId 仍独立生成，保持工具记录/耗时分组语义不变。
     */
    public void beginRegenerate(String conversationId, String question) {
        begin(conversationId, question, false);
    }

    private void begin(String conversationId, String question, boolean confirmationEligible) {
        current.set(new SessionState(conversationId, question, confirmationEligible));
    }

    /**
     * 记录一次 LLM 调用耗时（端到端墙钟，含网络）。未 begin（如单测直调）时安全忽略。
     * 次数与累计耗时进入请求级摘要，不重复写入每条工具记录。
     */
    public void recordLlmCall(long durationMs) {
        SessionState st = current.get();
        if (st == null || durationMs < 0) {
            return;
        }
        st.llmCallCount++;
        st.llmDurationMs += durationMs;
    }

    /**
     * 当前请求的耗时摘要（只读快照）。
     *
     * 未 begin（单测直调、管理直调等没有请求上下文）时返回 empty，调用方应跳过
     * 请求级输出而不是写一条空会话事件。须在 drain() 之前调用——drain 会清空请求状态。
     */
    public Optional<RequestSummary> summary() {
        SessionState st = current.get();
        return st == null ? Optional.empty() : Optional.of(st.toSummary());
    }

    /**
     * 当前请求的只读上下文。
     *
     * 未 begin（单测直调、管理直调等没有请求上下文）时返回 empty，调用方应跳过请求级
     * 写入而不是写一条空会话事件；这些字段不允许 LLM 通过工具参数伪造。
     */
    public Optional<RequestContext> currentContext() {
        SessionState st = current.get();
        return st == null
                ? Optional.empty()
                : Optional.of(new RequestContext(st.requestId, st.requestSequence,
                        st.conversationId, st.question, st.confirmationEligible));
    }

    /**
     * 记录一次工具调用。未 begin（如无追踪上下文）时安全忽略。
     * id/timestamp 在此统一生成，conversationId/question/requestId 取本请求上下文。
     */
    public void record(String toolName, String arguments, boolean success,
                       long durationMs, int resultChars, int round) {
        SessionState st = current.get();
        if (st == null) {
            return;
        }
        st.calls.add(new CallDetail(generateId(), toolName, arguments, success, durationMs,
                resultChars, round, LocalDateTime.now().format(TIMESTAMP)));
        st.toolTotalMs += durationMs;
        st.toolRounds.add(round);
    }

    /** 请求出口：取走全部调用明细（已附带 requestId）并清空请求状态（未 begin 返回空列表） */
    public List<ToolCallRecord> drain() {
        SessionState st = current.get();
        if (st == null) {
            return List.of();
        }
        current.remove();
        List<ToolCallRecord> records = new ArrayList<>(st.calls.size());
        for (CallDetail call : st.calls) {
            records.add(st.toRecord(call));
        }
        return List.copyOf(records);
    }

    /** 本请求是否已有工具调用（ChatService 据此决定是否写工具明细记录） */
    public boolean hasCalls() {
        SessionState st = current.get();
        return st != null && !st.calls.isEmpty();
    }

    /** 清空请求状态（异常路径兜底，幂等；drain() 已清空） */
    public void clear() {
        current.remove();
    }

    /** req- 前缀 + 毫秒时间戳 + 随机后缀：同会话多次问答的请求分组键 */
    private static String generateRequestId() {
        return "req-" + System.currentTimeMillis()
                + "-" + ThreadLocalRandom.current().nextInt(1000, 10000);
    }

    /** tc- 前缀 + 毫秒时间戳 + 随机后缀，单机并发下唯一 */
    private String generateId() {
        return "tc-" + System.currentTimeMillis()
                + "-" + ThreadLocalRandom.current().nextInt(1000, 10000);
    }
}
