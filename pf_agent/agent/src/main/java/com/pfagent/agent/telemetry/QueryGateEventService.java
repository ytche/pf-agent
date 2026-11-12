package com.pfagent.agent.telemetry;

import java.time.Instant;

/**
 * 查询门禁事件持久化接口（F-026 设计 §8）
 *
 * 只承载「实际到达工具层」的两类事件：{@link EventType#BLOCKED}（宽条件未放行，
 * 条目检索被拦截）与 {@link EventType#ALLOWED}（宽条件携带 allowBroadQuery=true，
 * 允许执行）。模型直接给出的提示词层建议、非宽条件正常查询、轻量概览都不写本接口。
 *
 * 本接口是并行实施 lane 的公共契约：工具 lane 只依赖
 * {@code QueryGateEventRecorder}；JDBC lane 提供实现（仅在 pf.chat.memory=jdbc 时
 * 装配，见 {@code JdbcQueryGateEventService}），双方不得各自修改本契约。
 */
public interface QueryGateEventService {

    /**
     * 写入一行门禁事件。
     *
     * 写库失败由实现以 RuntimeException 抛出，调用方（QueryGateEventRecorder）降级为
     * 只记日志、不阻断问答。返回值无意义：事件是尽力写入的遥测，不是业务结果。
     */
    void persist(QueryGateEvent event);

    /** 门禁事件类型（落库口径为枚举名 BLOCKED / ALLOWED） */
    enum EventType {
        /** 宽条件未放行，条目检索被拦截 */
        BLOCKED,
        /** 宽条件已放行，允许执行 */
        ALLOWED
    }

    /** 触发工具护栏的最低宽条件形态 */
    enum Reason {
        /** 无有效业务条件（仅分页/排序参数也按此形态） */
        NO_CONDITIONS("no_conditions"),
        /** 仅来源书条件（book 或 orFilters.book） */
        BOOK_ONLY("book_only"),
        /** AKN-024：会话内放行指纹（module+book）不匹配，allowBroadQuery=true 被驳回 */
        FINGERPRINT_MISMATCH("fingerprint_mismatch");

        private final String value;

        Reason(String value) {
            this.value = value;
        }

        /** 落库口径（query_gate_event.reason），与设计文档字段值一致 */
        public String value() {
            return this.value;
        }
    }

    /**
     * 一条门禁事件，字段对齐 query_gate_event 表。
     *
     * conversationId / question 只能来自 ToolCallTracker 的请求上下文，不允许 LLM 在
     * 工具参数中伪造；queryJson 是当前查询参数（业务条件 + offset/limit/sort）的 JSON，
     * 不保存回答正文或来源快照。
     */
    record QueryGateEvent(
            String conversationId,
            String question,
            String toolName,
            String module,
            EventType eventType,
            Reason reason,
            String queryJson,
            Instant createdAt) {
    }
}
