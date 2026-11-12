package com.pfagent.agent.conversation;

import java.util.List;

/** 登录后显式认领本机匿名会话 */
public record ClaimRequest(List<String> conversationIds) {
}
