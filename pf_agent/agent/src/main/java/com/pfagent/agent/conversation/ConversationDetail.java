package com.pfagent.agent.conversation;

import java.time.Instant;
import java.util.List;

/** 会话详情：摘要 + 最近 20 轮消息（按 seq 升序） */
public record ConversationDetail(
        String id,
        String title,
        boolean pinned,
        Instant createdAt,
        Instant updatedAt,
        int messageRounds,
        List<ConversationMessage> messages) {

    static ConversationDetail from(ConversationSummary summary, List<ConversationMessage> messages) {
        return new ConversationDetail(summary.id(), summary.title(), summary.pinned(),
                summary.createdAt(), summary.updatedAt(), summary.messageRounds(), messages);
    }
}
