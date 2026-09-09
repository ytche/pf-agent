package com.pfagent.agent.rag;

import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

/**
 * 请求级工具调用追踪器（F-006）
 *
 * 与 SourceCollector 同型：ChatService 是单例、并发请求互不污染，用 ThreadLocal
 * 收集「本请求（一次 ask()）」的全部工具调用明细。ChatService 入口 begin()，
 * 每个工具执行后 record()，出口 drain() 取走交给 ToolCallRecorder 落盘。
 *
 * 仅在记录工具调用明细，不落盘——落盘职责归 ToolCallRecorder（关注点分离，
 * tracker 保持纯内存可测）。
 */
@Component
public class ToolCallTracker {

    /** 秒精度 ISO 时间戳（与分析脚本/FeedbackRecorder 对齐） */
    private static final DateTimeFormatter TIMESTAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

    /** 本请求的会话上下文 + 调用明细；未 begin 时为 null（record 安全忽略） */
    private final ThreadLocal<SessionState> current = new ThreadLocal<>();

    private record SessionState(String conversationId, String question, List<ToolCallRecord> calls) {
    }

    /** 请求入口：初始化本请求的追踪状态（记录上下文供后续每条调用复用） */
    public void begin(String conversationId, String question) {
        current.set(new SessionState(conversationId, question, new ArrayList<>()));
    }

    /**
     * 记录一次工具调用。未 begin（如无追踪上下文）时安全忽略。
     * id/timestamp 在此统一生成，conversationId/question 取本请求上下文。
     */
    public void record(String toolName, String arguments, boolean success,
                       long durationMs, int resultChars, int round) {
        SessionState st = current.get();
        if (st == null) {
            return;
        }
        st.calls().add(new ToolCallRecord(
                generateId(), st.conversationId(), st.question(), toolName,
                arguments, success, durationMs, resultChars, round,
                LocalDateTime.now().format(TIMESTAMP)));
    }

    /** 请求出口：取走全部调用明细并清空请求状态（未 begin 返回空列表） */
    public List<ToolCallRecord> drain() {
        SessionState st = current.get();
        if (st == null) {
            return List.of();
        }
        current.remove();
        return List.copyOf(st.calls());
    }

    /** 本请求是否已有工具调用（ChatService 据此决定是否落盘） */
    public boolean hasCalls() {
        SessionState st = current.get();
        return st != null && !st.calls().isEmpty();
    }

    /** 清空请求状态（异常路径兜底，幂等；drain() 已清空） */
    public void clear() {
        current.remove();
    }

    /** tc- 前缀 + 毫秒时间戳 + 随机后缀，单机并发下唯一 */
    private String generateId() {
        return "tc-" + System.currentTimeMillis()
                + "-" + ThreadLocalRandom.current().nextInt(1000, 10000);
    }
}
