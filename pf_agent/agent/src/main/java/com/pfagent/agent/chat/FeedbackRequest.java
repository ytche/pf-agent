package com.pfagent.agent.chat;

import java.util.List;

/**
 * 错误标注请求 — 前端「标错」按钮提交的用户反馈
 *
 * question/answer/sources 是回答当时的内容快照：分析时无需依赖会话历史，
 * 可直接复现「Agent 当时看了哪些 chunk 却答错了」，定位是 prompt 还是检索问题。
 * errorType 取值：事实错误 / 检索漏召回 / 编造来源 / 答非所问 / 结构差。
 */
public record FeedbackRequest(
        String conversationId,
        String question,
        String answer,
        List<ChatResponse.SourceRef> sources,
        String errorType,
        String correction,
        String comment
) {
}
