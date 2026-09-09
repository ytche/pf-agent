package com.pfagent.agent.memory;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * F-011 匿名会话轮次配额（pf.quota.enabled=true 时装配）
 *
 * 匿名用户每会话累计轮数上限（默认 20 轮），超限由 ChatController 在调用 LLM 前返回
 * 429（fail-fast，零 token 成本）。新会话（无 conversationId）不受限——计数只针对已
 * 存在会话，判空在 controller 层。
 *
 * 计数语义（D4，两种存储统一 = 累计轮数、不裁剪）：
 * - jdbc 模式：读 chat_conversation.total_rounds 累计列——message_rounds 会被 F-005
 *   裁剪钉在上限，不能作配额依据（SP1 V1 注释的错误假设，V2 迁移修正）；由
 *   ChatConversationRepository 是否可装配判存储路径，存储细节不外泄。
 * - memory 模式：InMemoryChatMemory 不裁剪，全量消息条数 / 2 即会话累计轮数。
 *
 * 错误处理对齐 JdbcChatMemory：配额查询异常在此吞掉返回 0（放行）——配额是成本护栏，
 * 不因配额侧故障挡住问答主链路；query 失败记 warn 供排查。
 */
@Component
@ConditionalOnProperty(name = "pf.quota.enabled", havingValue = "true")
public class AnonymousQuotaService {

    private static final Logger log = LoggerFactory.getLogger(AnonymousQuotaService.class);

    @Value("${pf.quota.anonymous-rounds:20}")
    private int anonymousRounds;
    @Autowired
    private ChatMemory chatMemory;
    @Autowired
    private ObjectProvider<ChatConversationRepository> conversationRepositoryProvider;

    /** 会话已用轮数（累计、不裁剪）；会话不存在或查询失败返回 0 */
    public int getUsedRounds(String conversationId) {
        try {
            ChatConversationRepository repository = conversationRepositoryProvider.getIfAvailable();
            if (repository != null) {
                // jdbc：total_rounds 由 JdbcChatMemory.doAdd 每轮累加、永不被 F-005 裁剪；
                // 列 NOT NULL 但旧数据防御性兜底（理论不会触发）
                return repository.findById(conversationId)
                        .map(entity -> entity.getTotalRounds() == null ? 0 : entity.getTotalRounds())
                        .orElse(0);
            }
            // memory：无裁剪，全部消息条数对（user+assistant）即累计轮数
            return chatMemory.get(conversationId, Integer.MAX_VALUE).size() / 2;
        } catch (RuntimeException e) {
            log.warn("会话 {} 配额计数读取失败，按 0 放行: {}", conversationId, e.getMessage());
            return 0;
        }
    }

    /** 已用轮数是否达到配额上限（>= anonymousRounds，超限 429 由调用方处理） */
    public boolean isExceeded(String conversationId) {
        return getUsedRounds(conversationId) >= anonymousRounds;
    }

    /** 匿名配额上限（供响应文案与配置展示） */
    public int getAnonymousRounds() {
        return anonymousRounds;
    }
}
