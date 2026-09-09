package com.pfagent.agent.rag;

/**
 * 单次工具调用快照（F-006 工具调用计数）
 *
 * 一次问答中每执行一个 LLM 工具调用产生一条记录，供复盘 Agent 检索行为：
 * 走了哪些工具、参数是否合理、耗时与成败。以 JSONL 一行落盘，
 * 由 qa/tool_calls_report.py 聚合分析。
 *
 * @param id            记录 ID（tc- 前缀 + 毫秒时间戳 + 随机后缀）
 * @param conversationId 会话 ID（一次 ask() 一个）
 * @param question      用户原始问题（复盘上下文，与 data_gaps 同口径）
 * @param toolName      工具名（vectorSearch / searchByMetadata / reportDataGap）
 * @param arguments     LLM 生成的工具参数 JSON（含用户检索词，复盘 LLM 决策）
 * @param success       执行是否成功（catch 到异常为 false）
 * @param durationMs    执行耗时（毫秒，System.nanoTime 计时）
 * @param resultChars   工具返回结果字符数（反应喂给 LLM 的信息量）
 * @param round         手动工具循环轮次（第几轮发起）
 * @param timestamp     秒精度 ISO 时间戳（与分析脚本对齐）
 */
public record ToolCallRecord(
        String id,
        String conversationId,
        String question,
        String toolName,
        String arguments,
        boolean success,
        long durationMs,
        int resultChars,
        int round,
        String timestamp) {
}
