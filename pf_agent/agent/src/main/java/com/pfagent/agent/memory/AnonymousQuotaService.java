package com.pfagent.agent.memory;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * F-011 匿名会话轮次配额（pf.quota.enabled=true 时装配；F-020 起两种存储统一读 Store）
 *
 * 匿名用户每个会话的累计生成尝试上限（默认 20），普通问答与重新生成共用；
 * 超限由调用方在调用模型前返回 429（fail-fast，零 token 成本）。
 *
 * 计数语义（F-020 实施 Spec §6/§7）：读 chat_conversation.generation_attempts
 * 累计列——普通问答与重新生成在实际调用模型前 +1，模型调用已发生即便失败也保留，
 * 避免失败重试绕过成本护栏。它不等于对话轮数；既有会话在 V7 迁移时按 total_rounds 回填。
 * memory 模式由 InMemoryConversationStore 提供同一计数。
 *
 * 错误处理：配额查询异常在此吞掉返回 0（放行）——配额是成本护栏，不因配额侧故障
 * 挡住问答主链路；query 失败记 warn 供排查。
 */
@Component
@ConditionalOnProperty(name = "pf.quota.enabled", havingValue = "true")
public class AnonymousQuotaService {

    private static final Logger log = LoggerFactory.getLogger(AnonymousQuotaService.class);

    @Value("${pf.quota.anonymous-rounds:20}")
    private int anonymousRounds;
    @Autowired
    private ConversationStore conversationStore;

    /** 会话已用生成尝试次数（累计、不裁剪）；会话不存在或查询失败返回 0 */
    public int getUsedRounds(String conversationId) {
        try {
            return conversationStore.generationAttempts(conversationId);
        } catch (RuntimeException e) {
            log.warn("会话 {} 配额计数读取失败，按 0 放行: {}", conversationId, e.getMessage());
            return 0;
        }
    }

    /** 已用尝试次数是否达到配额上限（>= anonymousRounds，超限 429 由调用方处理） */
    public boolean isExceeded(String conversationId) {
        return getUsedRounds(conversationId) >= anonymousRounds;
    }

    /** 匿名配额上限（供响应文案与配置展示） */
    public int getAnonymousRounds() {
        return anonymousRounds;
    }
}
