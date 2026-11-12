package com.pfagent.agent.memory;

import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatNoException;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * ChatMemory 兼容适配降级路径单测（SP1 D6；F-020 改为委托 ConversationStore）
 *
 * 验证兼容入口的存储故障不打断问答主链路：写失败吞掉并告警、读失败按空历史处理、
 * 清理失败吞掉。正式问答写入由 ChatService 直接经 Store，不依赖此降级。
 */
class JdbcChatMemoryFallbackTest {

    private final JdbcChatMemory memory = new JdbcChatMemory();

    /** 写（add）抛 RuntimeException 时不向上抛，主链路不受影响 */
    @Test
    void addWriteFailureIsSwallowed() {
        ConversationStore store = mock(ConversationStore.class);
        when(store.getConversation(anyString())).thenThrow(new RuntimeException("db down"));
        ReflectionTestUtils.setField(memory, "conversationStore", store);

        assertThatNoException().isThrownBy(() ->
                memory.add("cid", List.of(new UserMessage("hi"), new org.springframework.ai.chat.messages.AssistantMessage("ok"))));
    }

    /** 读（get）抛 RuntimeException 时按空历史处理，不向上抛 */
    @Test
    void getReadFailureReturnsEmptyHistory() {
        ConversationStore store = mock(ConversationStore.class);
        when(store.history(anyString(), anyInt())).thenThrow(new RuntimeException("db down"));
        ReflectionTestUtils.setField(memory, "conversationStore", store);

        List<Message> history = memory.get("cid", 20);

        assertThat(history).isEmpty();
    }

    /** clear 抛 RuntimeException 时吞掉，不向上抛 */
    @Test
    void clearFailureIsSwallowed() {
        ConversationStore store = mock(ConversationStore.class);
        when(store.deleteConversation(anyString())).thenThrow(new RuntimeException("db down"));
        ReflectionTestUtils.setField(memory, "conversationStore", store);

        assertThatNoException().isThrownBy(() -> memory.clear("cid"));
    }
}
