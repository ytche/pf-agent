package com.pfagent.agent.conversation;

/** 已登录用户读取 owner 为空的匿名会话：必须走显式认领，不在读取时自动转移归属（403）。 */
public class ConversationForbiddenException extends RuntimeException {

    public ConversationForbiddenException() {
        super("该会话尚未认领到当前账号，请先认领后再访问");
    }
}
