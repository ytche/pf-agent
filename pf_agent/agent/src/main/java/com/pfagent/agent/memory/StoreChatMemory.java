package com.pfagent.agent.memory;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.beans.factory.annotation.Autowired;

import java.util.ArrayList;
import java.util.List;

/**
 * ChatMemory 兼容适配基类（F-020 实施 Spec §5.2）
 *
 * 用统一 {@link ConversationStore} 承载历史读取与写入，不再保留第二份会话写入逻辑。
 * 追加时先显式检查父会话：父行缺失只记 WARN 并跳过，绝不自动重建已删除会话。
 *
 * 降级语义沿用 SP1 D6：读写异常在此吞掉并记 WARN——兼容入口的存储故障不打断
 * 问答主链路；ChatService 的正式写入路径由 ConversationStore 直接表达结果。
 * 该适配只覆盖既有 ChatMemory 接口的调用方；问答追加与重新生成直接走 Store，
 * 来源快照等完整语义只在那里产生。
 */
public abstract class StoreChatMemory implements ChatMemory {

    private static final Logger log = LoggerFactory.getLogger(StoreChatMemory.class);

    @Autowired
    protected ConversationStore conversationStore;

    @Override
    public void add(String conversationId, List<Message> messages) {
        if (conversationId == null || messages == null || messages.isEmpty()) {
            return;
        }
        try {
            if (conversationStore.getConversation(conversationId).isEmpty()) {
                log.warn("会话 {} 已不存在，跳过 ChatMemory 兼容写入（不自动重建父会话）", conversationId);
                return;
            }
            for (int i = 0; i + 1 < messages.size(); i += 2) {
                Message user = messages.get(i);
                Message assistant = messages.get(i + 1);
                if (!(user instanceof UserMessage) || !(assistant instanceof AssistantMessage)) {
                    continue;
                }
                conversationStore.appendRound(conversationId, user.getText(), assistant.getText(),
                        null, false, java.time.Instant.now());
            }
        } catch (RuntimeException e) {
            log.warn("会话 {} ChatMemory 兼容写入失败，本轮对话不受影响: {}",
                    conversationId, e.getMessage());
        }
    }

    @Override
    public List<Message> get(String conversationId, int lastN) {
        if (lastN <= 0) {
            return List.of();
        }
        try {
            List<Message> messages = new ArrayList<>();
            for (ConversationStore.StoredMessage row : conversationStore.history(conversationId, lastN)) {
                switch (row.role()) {
                    case "user" -> messages.add(new UserMessage(row.content()));
                    case "assistant" -> messages.add(new AssistantMessage(row.content()));
                    default -> {
                        // 非 user/assistant 不进入模型上下文
                    }
                }
            }
            return messages;
        } catch (RuntimeException e) {
            log.warn("会话 {} ChatMemory 兼容读取失败，按空历史处理: {}",
                    conversationId, e.getMessage());
            return List.of();
        }
    }

    @Override
    public void clear(String conversationId) {
        try {
            conversationStore.deleteConversation(conversationId);
        } catch (RuntimeException e) {
            log.warn("会话 {} ChatMemory 兼容清理失败: {}", conversationId, e.getMessage());
        }
    }
}
