package com.pfagent.agent.conversation;

import java.util.List;

/** 匿名 lookup 响应：只含 owner 为空的会话 */
public record LookupResponse(List<ConversationSummary> items) {
}
