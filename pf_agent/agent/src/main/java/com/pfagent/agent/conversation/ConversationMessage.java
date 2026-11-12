package com.pfagent.agent.conversation;

import com.pfagent.agent.chat.ChatResponse;

import java.time.Instant;
import java.util.List;

/**
 * 会话消息（前端冻结契约 Message）。
 *
 * sources 为当轮 cited-only 引用快照；null 表示历史消息未保存来源，前端降级提示
 * “历史来源未保存”，不伪造来源。completedAt 仅助手消息有值。
 */
public record ConversationMessage(
        long id,
        int seq,
        String role,
        String content,
        List<ChatResponse.SourceRef> sources,
        boolean gapReported,
        Instant createdAt,
        Instant completedAt) {
}
