package com.pfagent.agent.conversation;

/** 请求期间会话被删除：晚到结果丢弃并返回 410，不得重建父会话。 */
public class ConversationDeletedException extends RuntimeException {

    public ConversationDeletedException(String conversationId) {
        super("会话已被删除，本次结果已丢弃: " + conversationId);
    }
}
