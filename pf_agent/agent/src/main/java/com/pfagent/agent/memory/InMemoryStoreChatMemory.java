package com.pfagent.agent.memory;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

/**
 * 内存模式 ChatMemory 兼容入口（pf.chat.memory=memory）
 *
 * 与 JDBC 模式同一套契约，底层复用 {@link InMemoryConversationStore}，重启后清空。
 * 标 @Primary 覆盖 AgentConfig 中的裸 InMemoryChatMemory 兜底 bean，保证历史读取
 * 与统一 Store 的写入一致（否则会出现「写 Store、读空内存」的分裂）。
 */
@Component
@Primary
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "memory", matchIfMissing = true)
public class InMemoryStoreChatMemory extends StoreChatMemory {
}
