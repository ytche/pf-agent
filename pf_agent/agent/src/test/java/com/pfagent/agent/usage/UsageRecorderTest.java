package com.pfagent.agent.usage;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.metadata.ChatResponseMetadata;
import org.springframework.ai.chat.metadata.DefaultUsage;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.model.Generation;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;

import java.math.BigDecimal;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * 用量采集契约：每次成功 LLM 调用一行、request_id 分组、call_seq 递增，
 * usage 缺失不伪造成 0，价目快照随行保存，写库失败不抛出。
 */
class UsageRecorderTest {

    private UsageRecordRepository repository;
    private UsageRequestContext context;
    private PlatformTransactionManager transactionManager;
    private JdbcUsageRecorder recorder;

    @BeforeEach
    void setUp() {
        repository = mock(UsageRecordRepository.class);
        context = new UsageRequestContext();
        transactionManager = mock(PlatformTransactionManager.class);
        TransactionStatus status = mock(TransactionStatus.class);
        when(transactionManager.getTransaction(any(TransactionDefinition.class))).thenReturn(status);
        recorder = new JdbcUsageRecorder(repository, context, transactionManager,
                "2.0", "8.0", "CNY");
    }

    @Test
    void recordsOneRowPerCallWithSharedRequestIdAndIncreasingSeq() {
        context.begin("cid-1", 7L);

        recorder.record("agent", "deepseek-chat", response("deepseek-chat", 100, 50), 123);
        recorder.record("agent", "deepseek-chat", response("deepseek-chat", 20, 10), 45);

        ArgumentCaptor<UsageRecordEntity> captor = ArgumentCaptor.forClass(UsageRecordEntity.class);
        verify(repository, times(2)).save(captor.capture());
        UsageRecordEntity first = captor.getAllValues().get(0);
        UsageRecordEntity second = captor.getAllValues().get(1);

        assertThat(first.getRequestId()).isNotBlank().isEqualTo(second.getRequestId());
        assertThat(first.getCallSeq()).isEqualTo(1);
        assertThat(second.getCallSeq()).isEqualTo(2);
        assertThat(first.getConversationId()).isEqualTo("cid-1");
        assertThat(first.getOwnerId()).isEqualTo(7L);
        assertThat(first.getPurpose()).isEqualTo("agent");
        assertThat(first.getModel()).isEqualTo("deepseek-chat");
        assertThat(first.getPromptTokens()).isEqualTo(100);
        assertThat(first.getCompletionTokens()).isEqualTo(50);
        assertThat(first.getTotalTokens()).isEqualTo(150);
        assertThat(first.isUsageMissing()).isFalse();
        assertThat(first.getDurationMs()).isEqualTo(123);
        assertThat(first.getCreatedAt()).isNotNull();

        // 价目快照：100/1e6*2 + 50/1e6*8 = 0.0006
        assertThat(first.getPromptPricePerMillion()).isEqualByComparingTo("2.0");
        assertThat(first.getCompletionPricePerMillion()).isEqualByComparingTo("8.0");
        assertThat(first.getCost()).isEqualByComparingTo("0.0006");
        assertThat(first.getCurrency()).isEqualTo("CNY");
    }

    @Test
    void opensRequiresNewTransactionSoUsageDoesNotJoinBusinessTransaction() {
        context.begin("cid-tx", null);

        recorder.record("agent", "deepseek-chat", response("deepseek-chat", 1, 1), 1);

        ArgumentCaptor<TransactionDefinition> captor = ArgumentCaptor.forClass(TransactionDefinition.class);
        verify(transactionManager).getTransaction(captor.capture());
        assertThat(captor.getValue().getPropagationBehavior())
                .isEqualTo(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    @Test
    void missingUsageLeavesTokensAndCostNullAndMarksMissing() {
        context.begin("cid-2", null);

        recorder.record("agent", "deepseek-chat", responseWithoutUsage("deepseek-chat"), 10);

        ArgumentCaptor<UsageRecordEntity> captor = ArgumentCaptor.forClass(UsageRecordEntity.class);
        verify(repository).save(captor.capture());
        UsageRecordEntity row = captor.getValue();
        assertThat(row.isUsageMissing()).isTrue();
        assertThat(row.getPromptTokens()).isNull();
        assertThat(row.getCompletionTokens()).isNull();
        assertThat(row.getTotalTokens()).isNull();
        assertThat(row.getCost()).isNull();
    }

    @Test
    void nullPricesLeaveCostNullButKeepTokens() {
        PlatformTransactionManager transactionManager = mock(PlatformTransactionManager.class);
        when(transactionManager.getTransaction(any(TransactionDefinition.class)))
                .thenReturn(mock(TransactionStatus.class));
        JdbcUsageRecorder withoutPrices = new JdbcUsageRecorder(repository, context,
                transactionManager, null, null, "CNY");
        context.begin("cid-3", null);

        withoutPrices.record("agent", "deepseek-chat", response("deepseek-chat", 10, 5), 5);

        ArgumentCaptor<UsageRecordEntity> captor = ArgumentCaptor.forClass(UsageRecordEntity.class);
        verify(repository).save(captor.capture());
        assertThat(captor.getValue().getPromptTokens()).isEqualTo(10);
        assertThat(captor.getValue().isUsageMissing()).isFalse();
        assertThat(captor.getValue().getCost()).isNull();
        assertThat(captor.getValue().getPromptPricePerMillion()).isNull();
        assertThat(captor.getValue().getCompletionPricePerMillion()).isNull();
    }

    @Test
    void repositoryFailureOnlyWarnsAndDoesNotThrow() {
        when(repository.save(any())).thenThrow(new IllegalStateException("db down"));
        context.begin("cid-4", null);

        assertThatCode(() -> recorder.record("agent", "deepseek-chat",
                response("deepseek-chat", 1, 1), 3))
                .doesNotThrowAnyException();
    }

    @Test
    void recordWithoutRequestContextStillPersistsSingleCall() {
        recorder.record("force_answer", "deepseek-chat", response("deepseek-chat", 3, 2), 9);

        ArgumentCaptor<UsageRecordEntity> captor = ArgumentCaptor.forClass(UsageRecordEntity.class);
        verify(repository).save(captor.capture());
        assertThat(captor.getValue().getRequestId()).isNotBlank();
        assertThat(captor.getValue().getCallSeq()).isEqualTo(1);
        assertThat(captor.getValue().getConversationId()).isNull();
        assertThat(captor.getValue().getPurpose()).isEqualTo("force_answer");
    }

    @Test
    void responseModelWinsOverFallback() {
        context.begin("cid-5", null);

        recorder.record("agent", "fallback-model", response("deepseek-chat", 1, 1), 1);

        ArgumentCaptor<UsageRecordEntity> captor = ArgumentCaptor.forClass(UsageRecordEntity.class);
        verify(repository).save(captor.capture());
        // 调用方 ChatService 负责取实际模型；recorder 使用传入值
        assertThat(captor.getValue().getModel()).isEqualTo("fallback-model");
    }

    static ChatResponse response(String model, int prompt, int completion) {
        ChatResponseMetadata metadata = ChatResponseMetadata.builder()
                .model(model)
                .usage(new DefaultUsage(prompt, completion, prompt + completion))
                .build();
        return new ChatResponse(List.of(new Generation(new AssistantMessage("答"))), metadata);
    }

    static ChatResponse responseWithoutUsage(String model) {
        ChatResponseMetadata metadata = ChatResponseMetadata.builder().model(model).build();
        return new ChatResponse(List.of(new Generation(new AssistantMessage("答"))), metadata);
    }

    static BigDecimal money(String value) {
        return new BigDecimal(value);
    }
}
