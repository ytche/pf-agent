package com.pfagent.agent.usage;

import com.pfagent.agent.chat.ChatService;
import com.pfagent.agent.conversation.ConversationAccessGuard;
import com.pfagent.agent.memory.AnonymousQuotaService;
import com.pfagent.agent.memory.ConversationStore;
import com.pfagent.agent.rag.DataGapRecorder;
import com.pfagent.agent.rag.FilterTranslator;
import com.pfagent.agent.rag.PromptBuilder;
import com.pfagent.agent.rag.RetrievalTools;
import com.pfagent.agent.rag.SearchService;
import com.pfagent.agent.rag.SourceCollector;
import com.pfagent.agent.rag.ToolCallRecorder;
import com.pfagent.agent.rag.ToolCallTracker;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.metadata.ChatResponseMetadata;
import org.springframework.ai.chat.metadata.DefaultUsage;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.model.Generation;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.nullable;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ChatService 用量采集落点：一次问答内每次成功 LLM 调用各一行（工具轮 + 最终回答），
 * forceAnswer 与 regenerate 同样覆盖；usage 缺失不伪造成 0。
 */
@ExtendWith(MockitoExtension.class)
class ChatServiceUsageCaptureTest {

    @Mock
    private ChatClient chatClient;
    @Mock
    private ChatClient.ChatClientRequestSpec requestSpec;
    @Mock
    private ChatClient.CallResponseSpec callResponseSpec;
    @Mock
    private SearchService searchService;
    @Mock
    private DataGapRecorder dataGapRecorder;
    @Mock
    private ConversationStore conversationStore;
    @Mock
    private ConversationAccessGuard accessGuard;
    @Mock
    private ObjectProvider<AnonymousQuotaService> quotaServiceProvider;
    @Mock
    private ToolCallRecorder toolCallRecorder;

    private final SourceCollector collector = new SourceCollector();
    private final ToolCallTracker tracker = new ToolCallTracker();
    private final UsageRequestContext usageContext = new UsageRequestContext();
    private UsageRecordRepository repository;
    private JdbcUsageRecorder recorder;
    private RetrievalTools retrievalTools;

    @BeforeEach
    void setUp() {
        repository = mock(UsageRecordRepository.class);
        PlatformTransactionManager transactionManager = mock(PlatformTransactionManager.class);
        lenient().when(transactionManager.getTransaction(any(TransactionDefinition.class)))
                .thenReturn(mock(TransactionStatus.class));
        recorder = new JdbcUsageRecorder(repository, usageContext, transactionManager, "2.0", "8.0", "CNY");

        retrievalTools = new RetrievalTools();
        ReflectionTestUtils.setField(retrievalTools, "searchService", searchService);
        ReflectionTestUtils.setField(retrievalTools, "collector", collector);
        ReflectionTestUtils.setField(retrievalTools, "recorder", dataGapRecorder);
        ReflectionTestUtils.setField(retrievalTools, "filterTranslator", new FilterTranslator());
        ReflectionTestUtils.setField(retrievalTools, "vectorResultChars", 100);

        lenient().when(chatClient.prompt()).thenReturn(requestSpec);
        lenient().when(requestSpec.messages(anyList())).thenReturn(requestSpec);
        lenient().when(requestSpec.tools(any(ToolCallback[].class))).thenReturn(requestSpec);
        lenient().when(requestSpec.options(any())).thenReturn(requestSpec);
        lenient().when(requestSpec.call()).thenReturn(callResponseSpec);
        when(conversationStore.history(anyString(), anyInt())).thenReturn(List.of());
        when(conversationStore.incrementGenerationAttempts(anyString())).thenReturn(1);
        when(accessGuard.requireReadable(anyString(), any())).thenReturn(new ConversationStore.ConversationView(
                "cid", null, false, 7L, 0, 0, 0, Instant.EPOCH, Instant.EPOCH));
        lenient().when(conversationStore.appendRound(anyString(), anyString(), anyString(),
                        nullable(String.class), anyBoolean(), any()))
                .thenAnswer(inv -> new ConversationStore.AppendResult(
                        ConversationStore.AppendStatus.OK,
                        new ConversationStore.StoredMessage(1L, 2, "assistant", "a", "[]",
                                false, Instant.EPOCH)));
    }

    @Test
    void recordsEveryLlmCallOfOneRequestWithSameRequestIdAndIncreasingSeq() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术射程\",\"module\":\"spell\"}", 100, 50),
                answer("射程 400 英尺", 20, 10));
        when(searchService.search("火球术射程", "spell")).thenReturn(List.of());

        chatService(15, 50000).ask("火球术射程？", "cid", 7L);

        ArgumentCaptor<UsageRecordEntity> captor = ArgumentCaptor.forClass(UsageRecordEntity.class);
        verify(repository, org.mockito.Mockito.times(2)).save(captor.capture());
        List<UsageRecordEntity> rows = captor.getAllValues();
        assertThat(rows.get(0).getRequestId()).isEqualTo(rows.get(1).getRequestId());
        assertThat(rows.get(0).getCallSeq()).isEqualTo(1);
        assertThat(rows.get(1).getCallSeq()).isEqualTo(2);
        assertThat(rows.get(0).getPurpose()).isEqualTo("agent");
        assertThat(rows.get(0).getConversationId()).isEqualTo("cid");
        assertThat(rows.get(0).getOwnerId()).isEqualTo(7L);
        assertThat(rows.get(0).getPromptTokens()).isEqualTo(100);
        assertThat(rows.get(0).getCompletionTokens()).isEqualTo(50);
        assertThat(rows.get(1).getPromptTokens()).isEqualTo(20);
        assertThat(rows.get(1).getCompletionTokens()).isEqualTo(10);
        assertThat(rows.get(0).getCost()).isEqualByComparingTo(new BigDecimal("0.0006"));
        assertThat(rows.get(1).getCost()).isEqualByComparingTo(new BigDecimal("0.00012"));
        // 请求出口清理上下文，ThreadLocal 不串请求
        assertThat(usageContext.peek()).isEmpty();
    }

    @Test
    void forceAnswerIsRecordedWithItsOwnPurpose() {
        when(callResponseSpec.chatResponse()).thenReturn(answer("收敛回答", 7, 3));

        // maxToolRounds=0 → 首轮即走强制收敛
        chatService(0, 50000).ask("q", "cid", null);

        ArgumentCaptor<UsageRecordEntity> captor = ArgumentCaptor.forClass(UsageRecordEntity.class);
        verify(repository).save(captor.capture());
        assertThat(captor.getValue().getPurpose()).isEqualTo("force_answer");
        assertThat(captor.getValue().getPromptTokens()).isEqualTo(7);
        assertThat(captor.getValue().getOwnerId()).isNull();
        assertThat(usageContext.peek()).isEmpty();
    }

    @Test
    void regenerateIsRecorded() {
        ConversationStore.StoredMessage oldAssistant = new ConversationStore.StoredMessage(
                5L, 2, "assistant", "old", "[]", false, Instant.EPOCH);
        when(conversationStore.lastRound("cid")).thenReturn(Optional.of(
                new ConversationStore.LastRound(1, "q1", oldAssistant)));
        when(conversationStore.replaceLastAssistant(eq("cid"), eq(2), anyString(),
                any(), anyBoolean(), any())).thenReturn(new ConversationStore.ReplaceResult(
                        ConversationStore.ReplaceStatus.OK, oldAssistant));
        when(callResponseSpec.chatResponse()).thenReturn(answer("新回答", 4, 2));

        chatService(15, 50000).regenerate("cid", 7L, 2);

        ArgumentCaptor<UsageRecordEntity> captor = ArgumentCaptor.forClass(UsageRecordEntity.class);
        verify(repository).save(captor.capture());
        assertThat(captor.getValue().getPurpose()).isEqualTo("agent");
        assertThat(captor.getValue().getConversationId()).isEqualTo("cid");
        assertThat(captor.getValue().getPromptTokens()).isEqualTo(4);
        assertThat(usageContext.peek()).isEmpty();
    }

    @Test
    void recordsTwoToolRoundsAndFinalAnswerAsSeqOneTwoThree() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"q1\",\"module\":\"spell\"}", 10, 5),
                toolCall("vectorSearch", "{\"question\":\"q2\",\"module\":\"spell\"}", 20, 10),
                answer("最终回答", 30, 15));
        when(searchService.search(anyString(), anyString())).thenReturn(List.of());

        chatService(15, 50000).ask("两轮工具？", "cid", 7L);

        ArgumentCaptor<UsageRecordEntity> captor = ArgumentCaptor.forClass(UsageRecordEntity.class);
        verify(repository, times(3)).save(captor.capture());
        List<UsageRecordEntity> rows = captor.getAllValues();
        assertThat(rows).extracting(UsageRecordEntity::getCallSeq).containsExactly(1, 2, 3);
        assertThat(rows).extracting(UsageRecordEntity::getRequestId)
                .containsOnly(rows.get(0).getRequestId());
        assertThat(rows).extracting(UsageRecordEntity::getPromptTokens).containsExactly(10, 20, 30);
    }

    @Test
    void repositoryFailureDoesNotBreakAnswer() {
        when(callResponseSpec.chatResponse()).thenReturn(answer("照常回答", 5, 5));
        when(repository.save(any())).thenThrow(new IllegalStateException("db down"));

        var result = chatService(15, 50000).ask("q", "cid", null);

        assertThat(result.answer()).isEqualTo("照常回答");
        verify(repository).save(any());
    }

    @Test
    void failedModelCallRecordsNoUsageRow() {
        when(callResponseSpec.chatResponse()).thenThrow(new IllegalStateException("LLM down"));

        org.assertj.core.api.Assertions.assertThatThrownBy(
                        () -> chatService(15, 50000).ask("q", "cid", null))
                .isInstanceOf(IllegalStateException.class);

        verify(repository, never()).save(any());
        assertThat(usageContext.peek()).isEmpty();
    }

    @Test
    void missingUsageIsRecordedAsMissingWithoutFakeCost() {
        when(callResponseSpec.chatResponse()).thenReturn(withoutUsage("deepseek-chat"));

        chatService(15, 50000).ask("q", "cid", null);

        ArgumentCaptor<UsageRecordEntity> captor = ArgumentCaptor.forClass(UsageRecordEntity.class);
        verify(repository).save(captor.capture());
        assertThat(captor.getValue().isUsageMissing()).isTrue();
        assertThat(captor.getValue().getPromptTokens()).isNull();
        assertThat(captor.getValue().getCost()).isNull();
    }

    private ChatService chatService(int maxRounds, int maxHistoryChars) {
        ChatService service = new ChatService();
        ReflectionTestUtils.setField(service, "chatClient", chatClient);
        ReflectionTestUtils.setField(service, "promptBuilder", new PromptBuilder());
        ReflectionTestUtils.setField(service, "conversationStore", conversationStore);
        ReflectionTestUtils.setField(service, "accessGuard", accessGuard);
        ReflectionTestUtils.setField(service, "quotaServiceProvider", quotaServiceProvider);
        ReflectionTestUtils.setField(service, "sourceCollector", collector);
        ReflectionTestUtils.setField(service, "retrievalTools", retrievalTools);
        ReflectionTestUtils.setField(service, "toolCallTracker", tracker);
        ReflectionTestUtils.setField(service, "toolCallRecorder", toolCallRecorder);
        ReflectionTestUtils.setField(service, "usageRecorder", recorder);
        ReflectionTestUtils.setField(service, "usageRequestContext", usageContext);
        ReflectionTestUtils.setField(service, "usageModel", "deepseek-chat");
        ReflectionTestUtils.setField(service, "maxToolRounds", maxRounds);
        ReflectionTestUtils.setField(service, "maxHistoryChars", maxHistoryChars);
        ReflectionTestUtils.setField(service, "historySize", 20);
        ReflectionTestUtils.invokeMethod(service, "initToolRegistry");
        return service;
    }

    private static ChatResponse answer(String text, int prompt, int completion) {
        return response(new AssistantMessage(text), prompt, completion);
    }

    private static ChatResponse toolCall(String name, String args, int prompt, int completion) {
        return response(new AssistantMessage(null, Map.of(),
                List.of(new AssistantMessage.ToolCall("call-1", "function", name, args))),
                prompt, completion);
    }

    private static ChatResponse response(AssistantMessage message, int prompt, int completion) {
        ChatResponseMetadata metadata = ChatResponseMetadata.builder()
                .model("deepseek-chat")
                .usage(new DefaultUsage(prompt, completion, prompt + completion))
                .build();
        return new ChatResponse(List.of(new Generation(message)), metadata);
    }

    private static ChatResponse withoutUsage(String model) {
        return new ChatResponse(List.of(new Generation(new AssistantMessage("答"))),
                ChatResponseMetadata.builder().model(model).build());
    }
}
