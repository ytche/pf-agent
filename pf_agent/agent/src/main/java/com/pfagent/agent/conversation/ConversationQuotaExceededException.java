package com.pfagent.agent.conversation;

/** 匿名会话生成尝试已用完（普通问答与重新生成共用同一配额），返回 429。 */
public class ConversationQuotaExceededException extends RuntimeException {

    private final int limit;

    public ConversationQuotaExceededException(int limit) {
        super("本会话免费额度已用完（" + limit + " 轮）。请开启新会话继续提问。");
        this.limit = limit;
    }

    public int getLimit() {
        return limit;
    }
}
