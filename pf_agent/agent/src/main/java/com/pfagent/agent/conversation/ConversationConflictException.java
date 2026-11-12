package com.pfagent.agent.conversation;

/** 重新生成期间出现新消息或最后一条消息已变化（expectedLastSeq 不匹配），返回 409。 */
public class ConversationConflictException extends RuntimeException {

    public ConversationConflictException() {
        super("会话内容已变化，请重新打开会话后再试");
    }

    public ConversationConflictException(String message) {
        super(message);
    }
}
