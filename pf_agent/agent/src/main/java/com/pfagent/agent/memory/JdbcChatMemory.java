package com.pfagent.agent.memory;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * JDBC 模式 ChatMemory 兼容入口（pf.chat.memory=jdbc）
 *
 * 历史行为由 {@link JdbcConversationStore} 承担；本类只把既有 ChatMemory 调用委托到
 * 统一 Store，不形成第二份写入逻辑，也不再自动创建缺失的父会话。
 */
@Component
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
public class JdbcChatMemory extends StoreChatMemory {
}
