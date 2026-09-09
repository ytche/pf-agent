package com.pfagent.agent.memory;

import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * AnonymousQuotaService 单元测试（F-011 匿名会话配额，两种存储统一计数）
 *
 * 计数语义（D4）：jdbc 读 total_rounds 累计列；memory 按全量消息条数 / 2 现算——
 * 都是「累计轮、不裁剪」，配额不受 F-005 保留轮数影响。手动 new + 反射注入字段
 * （@ConditionalOnProperty bean 不进单元测试上下文）。
 */
class AnonymousQuotaServiceTest {

    private static final int LIMIT = 20;
    private static final String CID = "conv-quota-1";

    /** jdbc 路径：读 total_rounds 累计列（会话已存在、累计 25 轮 → 超限） */
    @Test
    void jdbcPathCountsTotalRounds() {
        ChatConversationEntity entity = new ChatConversationEntity(CID, Instant.now());
        entity.setTotalRounds(25);
        ChatConversationRepository repo = jdbcRepositoryReturning(Optional.of(entity));

        AnonymousQuotaService service = service(null, repo);

        assertThat(service.getUsedRounds(CID)).isEqualTo(25);
        assertThat(service.isExceeded(CID)).isTrue();
    }

    /** jdbc 路径：会话不存在（新会话首次回带 ID 但尚未落库）→ 0、不超限 */
    @Test
    void jdbcPathUnknownConversationCountsZero() {
        ChatConversationRepository repo = jdbcRepositoryReturning(Optional.empty());

        AnonymousQuotaService service = service(null, repo);

        assertThat(service.getUsedRounds(CID)).isZero();
        assertThat(service.isExceeded(CID)).isFalse();
    }

    /** memory 路径：无裁剪，全量消息条数 / 2 = 累计轮（40 条 = 20 轮 = 恰好到上限） */
    @Test
    void memoryPathCountsMessagePairsAndBoundaryAtLimit() {
        ChatMemory memory = memoryReturning(roundsAsMessages(19)); // 38 条 = 19 轮，未达上限

        AnonymousQuotaService service = service(memory, null);

        assertThat(service.getUsedRounds(CID)).isEqualTo(19);
        assertThat(service.isExceeded(CID)).isFalse();

        // 补到 20 轮（40 条）→ 恰好达上限：下一次（第 21 轮）请求被拒
        ChatMemory fullMemory = memoryReturning(roundsAsMessages(20));
        AnonymousQuotaService fullService = service(fullMemory, null);

        assertThat(fullService.getUsedRounds(CID)).isEqualTo(20);
        assertThat(fullService.isExceeded(CID)).isTrue();
    }

    /** memory 路径用上限常量验证边界（LIMIT=20 时 used=20 → 超限） */
    @Test
    void isExceededBoundaryAtAnonymousRounds() {
        ChatMemory memory = memoryReturning(roundsAsMessages(LIMIT));
        AnonymousQuotaService service = service(memory, null);

        assertThat(service.isExceeded(CID)).isTrue();
    }

    /** 配额计数查询异常降级为 0（放行）——配额是护栏，不因故障挡住问答主链路 */
    @Test
    void repositoryFailureCountsZeroAndDoesNotThrow() {
        ChatConversationRepository repo = mock(ChatConversationRepository.class);
        when(repo.findById(CID)).thenThrow(new IllegalStateException("DB down"));

        AnonymousQuotaService service = service(null, repo);

        assertThat(service.getUsedRounds(CID)).isZero();
        assertThat(service.isExceeded(CID)).isFalse();
    }

    /** 配额上限 getter 返回配置值（响应文案拼「N 轮」用） */
    @Test
    void exposesAnonymousRoundsLimit() {
        AnonymousQuotaService service = service(null, null);

        assertThat(service.getAnonymousRounds()).isEqualTo(LIMIT);
    }

    /** 构造被测服务：repo 非 null → jdbc 路径；null → memory 路径（ObjectProvider 返回空） */
    private static AnonymousQuotaService service(ChatMemory memory, ChatConversationRepository repository) {
        AnonymousQuotaService service = new AnonymousQuotaService();
        ReflectionTestUtils.setField(service, "anonymousRounds", LIMIT);
        ReflectionTestUtils.setField(service, "chatMemory", memory);
        @SuppressWarnings("unchecked")
        ObjectProvider<ChatConversationRepository> provider = mock(ObjectProvider.class);
        when(provider.getIfAvailable()).thenReturn(repository);
        ReflectionTestUtils.setField(service, "conversationRepositoryProvider", provider);
        return service;
    }

    private static ChatConversationRepository jdbcRepositoryReturning(Optional<ChatConversationEntity> result) {
        ChatConversationRepository repo = mock(ChatConversationRepository.class);
        when(repo.findById(CID)).thenReturn(result);
        return repo;
    }

    private static ChatMemory memoryReturning(List<Message> messages) {
        ChatMemory memory = mock(ChatMemory.class);
        when(memory.get(eq(CID), anyInt())).thenReturn(messages);
        return memory;
    }

    /** rounds 轮 → rounds*2 条消息（user/assistant 对），服务只取 size 故内容随意 */
    private static List<Message> roundsAsMessages(int rounds) {
        List<Message> messages = new ArrayList<>();
        for (int i = 0; i < rounds; i++) {
            messages.add(new UserMessage("u" + i));
            messages.add(new UserMessage("a" + i));
        }
        return messages;
    }
}
