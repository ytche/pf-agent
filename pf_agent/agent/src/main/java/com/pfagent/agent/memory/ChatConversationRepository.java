package com.pfagent.agent.memory;

import org.springframework.data.jpa.repository.JpaRepository;

/**
 * 会话仓储（chat_conversation）
 *
 * 主键即 conversationId（String UUID）。clear 由 JdbcChatMemory 显式先删消息再删会话；
 * schema 侧外键 ON DELETE CASCADE 仍在，作生产环境兜底。
 */
public interface ChatConversationRepository extends JpaRepository<ChatConversationEntity, String> {
}
