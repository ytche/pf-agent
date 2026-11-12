package com.pfagent.agent.memory;

import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * AnonymousQuotaService 单元测试（F-011 匿名会话配额；F-020 起两种存储统一读 Store）
 *
 * 计数语义：generation_attempts 累计普通问答与重新生成的实际模型调用尝试，
 * 不受 20 轮裁剪影响；查询异常降级为 0 放行（配额是成本护栏，不挡主链路）。
 */
class AnonymousQuotaServiceTest {

    private static final int LIMIT = 20;
    private static final String CID = "conv-quota-1";

    /** 读 Store 的 generation_attempts（25 次尝试 → 超限） */
    @Test
    void countsGenerationAttemptsFromStore() {
        ConversationStore store = mock(ConversationStore.class);
        when(store.generationAttempts(CID)).thenReturn(25);

        AnonymousQuotaService service = service(store);

        assertThat(service.getUsedRounds(CID)).isEqualTo(25);
        assertThat(service.isExceeded(CID)).isTrue();
    }

    /** Store 无该会话（新会话尚未落库）→ 0、不超限 */
    @Test
    void unknownConversationCountsZero() {
        ConversationStore store = mock(ConversationStore.class);
        when(store.generationAttempts(CID)).thenReturn(0);

        AnonymousQuotaService service = service(store);

        assertThat(service.getUsedRounds(CID)).isZero();
        assertThat(service.isExceeded(CID)).isFalse();
    }

    /** 边界：used == limit → 超限（下一次请求被拒） */
    @Test
    void isExceededBoundaryAtAnonymousRounds() {
        ConversationStore store = mock(ConversationStore.class);
        when(store.generationAttempts(CID)).thenReturn(LIMIT);

        AnonymousQuotaService service = service(store);

        assertThat(service.isExceeded(CID)).isTrue();
    }

    /** 配额计数查询异常降级为 0（放行）——配额是护栏，不因故障挡住问答主链路 */
    @Test
    void storeFailureCountsZeroAndDoesNotThrow() {
        ConversationStore store = mock(ConversationStore.class);
        when(store.generationAttempts(CID)).thenThrow(new IllegalStateException("DB down"));

        AnonymousQuotaService service = service(store);

        assertThat(service.getUsedRounds(CID)).isZero();
        assertThat(service.isExceeded(CID)).isFalse();
    }

    /** 配额上限 getter 返回配置值（响应文案拼「N 轮」用） */
    @Test
    void exposesAnonymousRoundsLimit() {
        AnonymousQuotaService service = service(mock(ConversationStore.class));

        assertThat(service.getAnonymousRounds()).isEqualTo(LIMIT);
    }

    private static AnonymousQuotaService service(ConversationStore store) {
        AnonymousQuotaService service = new AnonymousQuotaService();
        ReflectionTestUtils.setField(service, "anonymousRounds", LIMIT);
        ReflectionTestUtils.setField(service, "conversationStore", store);
        return service;
    }
}
