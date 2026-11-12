package com.pfagent.agent.conversation;

import java.util.List;

/** 账号会话分批列表；nextCursor 为 null 表示没有更多 */
public record ConversationPageResponse(List<ConversationSummary> items, String nextCursor) {
}
