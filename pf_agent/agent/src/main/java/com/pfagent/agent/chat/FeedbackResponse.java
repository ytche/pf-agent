package com.pfagent.agent.chat;

/**
 * 错误标注提交响应 — ok 固定 true（追加式遥测，写入失败内部吞掉仅记日志），
 * id 为本次标注生成的记录 ID，供前端/后续分析定位。
 */
public record FeedbackResponse(boolean ok, String id) {
}
