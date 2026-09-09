package com.pfagent.agent.config;

import com.pfagent.agent.memory.ChatConversationRepository;
import com.pfagent.agent.memory.ChatMessageRepository;
import com.pfagent.agent.memory.JdbcChatMemory;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.memory.InMemoryChatMemory;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.boot.convert.ApplicationConversionService;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.core.convert.ConversionService;
import org.springframework.transaction.PlatformTransactionManager;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

/**
 * ChatMemory 装配切换测试（SP1 D4，SP1 T5）
 *
 * 用 ApplicationContextRunner 加载 AgentConfig + JdbcChatMemory，验证 pf.chat.memory
 * 三种取值装配出正确实现且互斥：
 * - 未配置 / memory → InMemoryChatMemory（默认内存模式，不碰数据库）
 * - jdbc → JdbcChatMemory（会话持久化；这里仅验装配，Repository/事务均 mock）
 */
class ChatMemoryAutoConfigurationTest {

    /** 未配置 pf.chat.memory（缺省）→ 内存实现 */
    @Test
    void memoryIsDefaultWhenPropertyAbsent() {
        runner().run(context ->
                assertThat(context.getBean(ChatMemory.class)).isInstanceOf(InMemoryChatMemory.class));
    }

    /** pf.chat.memory=memory → 内存实现，且不装配 JdbcChatMemory */
    @Test
    void memoryWhenPropertyExplicit() {
        runner().withPropertyValues("pf.chat.memory=memory").run(context -> {
            assertThat(context.getBean(ChatMemory.class)).isInstanceOf(InMemoryChatMemory.class);
            assertThat(context.getBeansOfType(JdbcChatMemory.class)).isEmpty();
        });
    }

    /** pf.chat.memory=jdbc → JdbcChatMemory，内存实现不装配（互斥） */
    @Test
    void jdbcWhenPropertyIsJdbc() {
        runner().withPropertyValues("pf.chat.memory=jdbc").run(context -> {
            assertThat(context.getBean(ChatMemory.class)).isInstanceOf(JdbcChatMemory.class);
            assertThat(context.getBeansOfType(InMemoryChatMemory.class)).isEmpty();
        });
    }

    private ApplicationContextRunner runner() {
        return new ApplicationContextRunner()
                .withUserConfiguration(AgentConfig.class, JdbcChatMemory.class)
                // Runner 不加载 Boot 自动配置，AgentConfig.clientHttpRequestFactory 的
                // @Value "60s"→Duration 需 Boot 的 ApplicationConversionService 才能转
                .withBean(ConversionService.class, ApplicationConversionService::getSharedInstance)
                .withBean(OpenAiChatModel.class, () -> mock(OpenAiChatModel.class))
                .withBean(ChatMessageRepository.class, () -> mock(ChatMessageRepository.class))
                .withBean(ChatConversationRepository.class, () -> mock(ChatConversationRepository.class))
                .withBean(PlatformTransactionManager.class, () -> mock(PlatformTransactionManager.class));
    }
}
