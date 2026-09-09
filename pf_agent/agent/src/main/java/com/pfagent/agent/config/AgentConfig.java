package com.pfagent.agent.config;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.memory.InMemoryChatMemory;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.SimpleClientHttpRequestFactory;

import java.time.Duration;

/**
 * Agent 配置
 *
 * - ChatClient：无 defaultAdvisors，历史由 ChatService 手动管理（v1.4 §9.3）
 * - ChatMemory：L1 会话记忆；pf.chat.memory=memory 用内存实现（默认），=jdbc 用 JdbcChatMemory
 *   （PostgreSQL 持久化，SP1），装配互斥
 * - ClientHttpRequestFactory：LLM 调用读超时（辅助防线，主防线是应用层轮次上限）
 */
@Configuration
public class AgentConfig {

    @Bean
    public ChatClient chatClient(OpenAiChatModel chatModel) {
        return ChatClient.builder(chatModel).build();
    }

    /**
     * L1 会话记忆：内存实现（默认，pf.chat.memory=memory 或未配置）。
     * 单用户本地场景够用；跨重启续会话时改用 pf.chat.memory=jdbc（JdbcChatMemory）。
     */
    @Bean
    @ConditionalOnProperty(name = "pf.chat.memory", havingValue = "memory", matchIfMissing = true)
    public InMemoryChatMemory inMemoryChatMemory() {
        return new InMemoryChatMemory();
    }

    /**
     * LLM 调用超时（连接 + 读）。单次调用超过 chat-timeout 直接失败，
     * 避免慢调用长时间占用线程；配合应用层 max-tool-rounds 构成双层防线。
     */
    @Bean
    public ClientHttpRequestFactory clientHttpRequestFactory(
            @Value("${pf.search.chat-timeout:60s}") Duration timeout) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(timeout);
        factory.setReadTimeout(timeout);
        return factory;
    }
}
