package com.pfagent.agent.usage;

import org.springframework.stereotype.Component;

import java.util.Optional;
import java.util.UUID;

/**
 * 请求级用量上下文（F-009 设计 §4.2）。
 *
 * ChatService 是单例、Web 请求并发执行：request_id、call_seq、会话与所有者只能放在
 * ThreadLocal，禁止用实例字段串请求。入口 begin()，退出 finally clear()；
 * 每次 LLM 调用成功返回时 nextCall() 取走递增序号。
 *
 * 与 ToolCallTracker 同型（请求分组 + finally 清理），但独立维护：用量上下文还会
 * 被后续 F-016 重排调用复用，不能依赖工具追踪的 begin/beginRegenerate 语义。
 */
@Component
public class UsageRequestContext {

    /** 调用方拿到的只读快照（callSeq 已递增） */
    public record CallScope(String requestId, int callSeq, String conversationId, Long ownerId) {
    }

    private static final class State {
        private final String requestId = UUID.randomUUID().toString();
        private final String conversationId;
        private final Long ownerId;
        private int callSeq;

        private State(String conversationId, Long ownerId) {
            this.conversationId = conversationId;
            this.ownerId = ownerId;
        }
    }

    private final ThreadLocal<State> current = new ThreadLocal<>();

    /** 请求入口：一次用户问答/regenerate 一个新 request_id，call_seq 从 1 开始 */
    public void begin(String conversationId, Long ownerId) {
        current.set(new State(conversationId, ownerId));
    }

    /** 当前请求的下一调用序号；未 begin（单测直调/管理直调）时返回 empty */
    public Optional<CallScope> nextCall() {
        State state = current.get();
        if (state == null) {
            return Optional.empty();
        }
        state.callSeq++;
        return Optional.of(new CallScope(state.requestId, state.callSeq,
                state.conversationId, state.ownerId));
    }

    /** 只读查看当前请求（不递增序号），未 begin 时 empty */
    public Optional<CallScope> peek() {
        State state = current.get();
        return state == null ? Optional.empty()
                : Optional.of(new CallScope(state.requestId, state.callSeq,
                state.conversationId, state.ownerId));
    }

    /** 请求出口兜底清理（幂等），异常路径也不得残留 */
    public void clear() {
        current.remove();
    }
}
