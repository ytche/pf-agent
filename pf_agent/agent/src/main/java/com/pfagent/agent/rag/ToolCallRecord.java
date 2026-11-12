package com.pfagent.agent.rag;

/**
 * 单次工具调用快照（F-006 工具调用计数 / AKN-023 请求级耗时埋点）
 *
 * 一次问答中每执行一个 LLM 工具调用产生一条记录，供复盘 Agent 检索行为：
 * 走了哪些工具、参数是否合理、耗时与成败。以 JSONL 一行落盘，
 * 由 qa/tool_calls_report.py 聚合分析。
 *
 * AKN-023 起工具记录带 {@code requestId} 归属到一次问答；请求级耗时（总耗时 /
 * LLM 调用次数与累计耗时）不重复写在这里，而是每次问答单独写一条
 * {@code recordType=request_summary} 的摘要记录（见 {@link ToolCallTracker.RequestSummary}），
 * 避免分析脚本按工具行重复累计。旧 JSONL 记录没有 requestId，脚本按
 * conversationId + question 回退分组，保持向后兼容。
 *
 * @param id             记录 ID（tc- 前缀 + 毫秒时间戳 + 随机后缀）
 * @param requestId      请求分组 ID（req- 前缀；同一次问答的工具记录共享，旧记录可为 null）
 * @param conversationId 会话 ID（一次 ask() 一个；同会话多次问答靠 requestId 区分）
 * @param question       用户原始问题（复盘上下文，与 data_gaps 同口径）
 * @param toolName       工具名（vectorSearch / searchByMetadata / reportDataGap）
 * @param arguments      LLM 生成的工具参数 JSON（含用户检索词，复盘 LLM 决策）
 * @param success        执行是否成功（catch 到异常为 false）
 * @param durationMs     执行耗时（毫秒，System.nanoTime 计时）
 * @param resultChars    工具返回结果字符数（反应喂给 LLM 的信息量）
 * @param round          手动工具循环轮次（第几轮发起）
 * @param timestamp      秒精度 ISO 时间戳（与分析脚本对齐）
 */
public record ToolCallRecord(
        String id,
        String requestId,
        String conversationId,
        String question,
        String toolName,
        String arguments,
        boolean success,
        long durationMs,
        int resultChars,
        int round,
        String timestamp) {

    /** 兼容构造：AKN-023 之前的 10 字段调用方（无请求分组 ID，落盘时 requestId 为 null） */
    public ToolCallRecord(String id, String conversationId, String question, String toolName,
                          String arguments, boolean success, long durationMs, int resultChars,
                          int round, String timestamp) {
        this(id, null, conversationId, question, toolName, arguments, success, durationMs,
                resultChars, round, timestamp);
    }
}
