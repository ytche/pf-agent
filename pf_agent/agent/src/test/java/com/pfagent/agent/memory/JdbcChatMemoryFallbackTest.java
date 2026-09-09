package com.pfagent.agent.memory;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.List;
import java.util.function.Consumer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatNoException;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * JdbcChatMemory 降级路径单测（SP1 D6，SP1 T5）
 *
 * 不启动上下文：直接 mock 依赖，验证会话记忆故障不打断问答主链路——
 * 写失败本轮照常（warn 后吞掉）、读失败按空历史处理、清理失败吞掉。
 */
@ExtendWith(MockitoExtension.class)
class JdbcChatMemoryFallbackTest {

    private final JdbcChatMemory memory = new JdbcChatMemory();

    /** 写（add）抛 RuntimeException 时不向上抛，主链路不受影响 */
    @Test
    void addWriteFailureIsSwallowed() {
        TransactionTemplate tx = mock(TransactionTemplate.class);
        doThrow(new RuntimeException("db down")).when(tx).executeWithoutResult(any(Consumer.class));
        ReflectionTestUtils.setField(memory, "transactionTemplate", tx);

        assertThatNoException().isThrownBy(() ->
                memory.add("cid", List.of(new UserMessage("hi"))));
        verify(tx).executeWithoutResult(any(Consumer.class));
    }

    /** 读（get）抛 RuntimeException 时按空历史处理，不向上抛 */
    @Test
    void getReadFailureReturnsEmptyHistory() {
        ChatMessageRepository repo = mock(ChatMessageRepository.class);
        when(repo.findByConversationIdOrderBySeqAsc(anyString()))
                .thenThrow(new RuntimeException("db down"));
        ReflectionTestUtils.setField(memory, "messageRepository", repo);

        List<Message> history = memory.get("cid", 20);

        assertThat(history).isEmpty();
    }

    /** clear 抛 RuntimeException 时吞掉，不向上抛 */
    @Test
    void clearFailureIsSwallowed() {
        TransactionTemplate tx = mock(TransactionTemplate.class);
        doThrow(new RuntimeException("db down")).when(tx).executeWithoutResult(any(Consumer.class));
        ReflectionTestUtils.setField(memory, "transactionTemplate", tx);

        assertThatNoException().isThrownBy(() -> memory.clear("cid"));
        verify(tx).executeWithoutResult(any(Consumer.class));
    }
}
