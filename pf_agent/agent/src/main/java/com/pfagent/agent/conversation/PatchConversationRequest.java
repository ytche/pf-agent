package com.pfagent.agent.conversation;

/** 重命名 / 置顶：字段缺省表示不修改 */
public record PatchConversationRequest(String title, Boolean pinned) {
}
