package com.pfagent.agent.conversation;

import com.pfagent.agent.memory.ConversationStore;

import java.time.Instant;

/** 会话摘要（前端冻结契约 ConversationSummary） */
public record ConversationSummary(
        String id,
        String title,
        boolean pinned,
        Instant createdAt,
        Instant updatedAt,
        int messageRounds) {

    static ConversationSummary from(ConversationStore.ConversationView view) {
        return new ConversationSummary(view.id(), view.title(), view.pinned(),
                view.createdAt(), view.lastActiveAt(), view.messageRounds());
    }
}
