package com.pfagent.agent.chat;

/**
 * 对话请求
 *
 * @param question       用户问题
 * @param conversationId 会话 ID（前端存 localStorage；后端收到空值则生成新会话）
 */
public record ChatRequest(String question, String conversationId) {
}
