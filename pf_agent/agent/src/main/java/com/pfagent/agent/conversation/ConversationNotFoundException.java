package com.pfagent.agent.conversation;

/** 会话从未存在或对当前身份不可见（统一 404，避免泄露 UUID 已被他人认领）。 */
public class ConversationNotFoundException extends RuntimeException {

    public ConversationNotFoundException(String conversationId) {
        super("会话不存在: " + conversationId);
    }
}
