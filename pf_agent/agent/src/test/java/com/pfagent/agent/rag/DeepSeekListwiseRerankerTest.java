package com.pfagent.agent.rag;

import com.pfagent.agent.rag.DeepSeekListwiseReranker.Candidate;
import com.pfagent.agent.rag.DeepSeekRerankHttpClient.RerankResult;
import com.pfagent.agent.telemetry.UsageRecorder;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.same;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * F-016 listwise 重排单测：合法排序、缺项补位、未知/重复 id、非法 JSON、
 * 调用异常与超时回退、用量记录、无工具调用。
 *
 * <p>Task 14 修复后重排走 {@link DeepSeekRerankHttpClient}（原生 java.net.http），
 * 本类 mock 传输层客户端；HTTP 细节（状态码/超时/JSON）由
 * {@code DeepSeekRerankHttpClientTest} 用 mock HttpClient 覆盖。
 */
@ExtendWith(MockitoExtension.class)
class DeepSeekListwiseRerankerTest {

    @Mock
    private DeepSeekRerankHttpClient httpClient;
    @Mock
    private UsageRecorder usageRecorder;

    @Test
    void legalOrderIsAppliedAndTruncatedToTopN() {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");
        Candidate c = candidate("c", "C");
        when(httpClient.complete(any(), any())).thenReturn(result("[\"c\",\"a\",\"b\"]"));

        List<Document> result = reranker(Duration.ofSeconds(2))
                .rerank("问题", List.of(a, b, c), 2);

        assertThat(result).containsExactly(c.document(), a.document());
    }

    @Test
    void missingCandidatesBackfilledInOriginalOrder() {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");
        Candidate c = candidate("c", "C");
        Candidate d = candidate("d", "D");
        when(httpClient.complete(any(), any())).thenReturn(result("[\"c\"]"));

        List<Document> result = reranker(Duration.ofSeconds(2))
                .rerank("问题", List.of(a, b, c, d), 3);

        assertThat(result).containsExactly(c.document(), a.document(), b.document());
    }

    @Test
    void unknownIdFallsBackEntirely() {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");
        Candidate c = candidate("c", "C");
        when(httpClient.complete(any(), any())).thenReturn(result("[\"b\",\"ghost\"]"));

        List<Document> result = reranker(Duration.ofSeconds(2))
                .rerank("问题", List.of(a, b, c), 2);

        assertThat(result).containsExactly(a.document(), b.document());
    }

    @Test
    void duplicateIdFallsBackEntirely() {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");
        Candidate c = candidate("c", "C");
        when(httpClient.complete(any(), any())).thenReturn(result("[\"b\",\"b\"]"));

        List<Document> result = reranker(Duration.ofSeconds(2))
                .rerank("问题", List.of(a, b, c), 2);

        assertThat(result).containsExactly(a.document(), b.document());
    }

    @Test
    void invalidJsonFallsBackEntirely() {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");
        Candidate c = candidate("c", "C");
        when(httpClient.complete(any(), any())).thenReturn(result("排名是 b 然后 a"));

        List<Document> result = reranker(Duration.ofSeconds(2))
                .rerank("问题", List.of(a, b, c), 2);

        assertThat(result).containsExactly(a.document(), b.document());
    }

    @Test
    void emptyArrayFallsBackEntirely() {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");
        when(httpClient.complete(any(), any())).thenReturn(result("[]"));

        List<Document> result = reranker(Duration.ofSeconds(2))
                .rerank("问题", List.of(a, b), 1);

        assertThat(result).containsExactly(a.document());
    }

    @Test
    void candidatesNotExceedingTopNSkipCall() {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");

        List<Document> result = reranker(Duration.ofSeconds(2))
                .rerank("问题", List.of(a, b), 2);

        assertThat(result).containsExactly(a.document(), b.document());
        verify(httpClient, never()).complete(any(), any());
    }

    @Test
    void callExceptionFallsBackEntirely() {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");
        Candidate c = candidate("c", "C");
        when(httpClient.complete(any(), any())).thenThrow(new IllegalStateException("boom"));

        List<Document> result = reranker(Duration.ofSeconds(2))
                .rerank("问题", List.of(a, b, c), 2);

        assertThat(result).containsExactly(a.document(), b.document());
        verify(usageRecorder, never()).record(any(), any(), any(), anyLong());
    }

    @Test
    void timeoutCancelsTaskAndLeavesNoBacklog() throws Exception {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean completed = new AtomicBoolean(false);
        when(httpClient.complete(any(), any())).thenAnswer(invocation -> {
            started.countDown();
            release.await(5, TimeUnit.SECONDS);
            completed.set(true);
            return result("[\"b\",\"a\"]");
        });
        DeepSeekListwiseReranker reranker = reranker(Duration.ofMillis(500));

        long begin = System.nanoTime();
        List<Document> result = reranker.rerank("问题", List.of(a, b), 1);
        long elapsedMs = (System.nanoTime() - begin) / 1_000_000;

        assertThat(result).containsExactly(a.document());
        assertThat(elapsedMs).isLessThan(1500);
        assertThat(started.await(1, TimeUnit.SECONDS)).isTrue();
        assertThat(completed).isFalse(); // 超时后 future.cancel(true) 中断任务，任务未完成
        assertThat(waitForIdle(reranker)).isTrue(); // 线程池无积压
        verify(usageRecorder, never()).record(any(), any(), any(), anyLong());
    }

    @Test
    void interruptFallsBackAndCancelsTask() throws Exception {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicReference<List<Document>> result = new AtomicReference<>();
        when(httpClient.complete(any(), any())).thenAnswer(invocation -> {
            started.countDown();
            release.await(5, TimeUnit.SECONDS);
            return result("[\"b\",\"a\"]");
        });
        DeepSeekListwiseReranker reranker = reranker(Duration.ofSeconds(5));

        Thread caller = new Thread(() -> result.set(reranker.rerank("问题", List.of(a, b), 1)));
        caller.start();
        assertThat(started.await(1, TimeUnit.SECONDS)).isTrue();
        caller.interrupt();
        caller.join(2000);

        assertThat(caller.isAlive()).isFalse();
        assertThat(result.get()).containsExactly(a.document());
        assertThat(waitForIdle(reranker)).isTrue();
    }

    @Test
    void rejectedExecutionFallsBack() {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");
        DeepSeekListwiseReranker reranker = reranker(Duration.ofSeconds(2));
        ExecutorService rejecting = mock(ExecutorService.class);
        when(rejecting.isShutdown()).thenReturn(false);
        when(rejecting.submit(any(java.util.concurrent.Callable.class)))
                .thenThrow(new RejectedExecutionException("queue full"));
        ReflectionTestUtils.setField(reranker, "executor", rejecting);

        List<Document> result = reranker.rerank("问题", List.of(a, b), 1);

        assertThat(result).containsExactly(a.document());
        verify(httpClient, never()).complete(any(), any());
    }

    @Test
    void successfulCallRecordsRerankUsageWithTokensAndDuration() {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");
        Candidate c = candidate("c", "C");
        when(httpClient.complete(any(), any()))
                .thenReturn(new RerankResult("[\"b\",\"a\"]", "deepseek-flash", 120, 30, 150, 42L));

        reranker(Duration.ofSeconds(2)).rerank("问题", List.of(a, b, c), 2);

        ArgumentCaptor<ChatResponse> captor = ArgumentCaptor.forClass(ChatResponse.class);
        verify(usageRecorder).record(eq("rerank"), eq("deepseek-flash"), captor.capture(), anyLong());
        ChatResponse recorded = captor.getValue();
        assertThat(recorded.getMetadata().getModel()).isEqualTo("deepseek-flash");
        assertThat(recorded.getMetadata().getUsage().getPromptTokens()).isEqualTo(120);
        assertThat(recorded.getMetadata().getUsage().getCompletionTokens()).isEqualTo(30);
        assertThat(recorded.getMetadata().getUsage().getTotalTokens()).isEqualTo(150);
    }

    @Test
    void usageMissingStillRecordsCallWithDuration() {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");
        when(httpClient.complete(any(), any()))
                .thenReturn(new RerankResult("[\"a\"]", "", null, null, null, 10L));

        reranker(Duration.ofSeconds(2)).rerank("问题", List.of(a, b), 1);

        ArgumentCaptor<ChatResponse> captor = ArgumentCaptor.forClass(ChatResponse.class);
        verify(usageRecorder).record(eq("rerank"), eq("deepseek-flash"), captor.capture(), anyLong());
        assertThat(captor.getValue().getMetadata().getModel()).isEqualTo("deepseek-flash");
    }

    @Test
    void illegalJsonStillRecordsSuccessfulCallUsage() {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");
        when(httpClient.complete(any(), any())).thenReturn(result("不是 JSON"));

        reranker(Duration.ofSeconds(2)).rerank("问题", List.of(a, b), 1);

        verify(usageRecorder).record(eq("rerank"), eq("deepseek-flash"), any(ChatResponse.class), anyLong());
    }

    @Test
    void promptCarriesQuestionAndCandidatesWithoutTools() {
        Candidate a = candidate("a", "A");
        Candidate b = candidate("b", "B");
        when(httpClient.complete(any(), any())).thenReturn(result("[\"a\"]"));
        DeepSeekListwiseReranker reranker = reranker(Duration.ofSeconds(2));

        reranker.rerank("女巫法术", List.of(a, b), 1);

        ArgumentCaptor<String> systemCaptor = ArgumentCaptor.forClass(String.class);
        ArgumentCaptor<String> userCaptor = ArgumentCaptor.forClass(String.class);
        verify(httpClient).complete(systemCaptor.capture(), userCaptor.capture());
        assertThat(systemCaptor.getValue()).contains("相关性重排器", "不得调用任何工具");
        String payload = userCaptor.getValue();
        assertThat(payload)
                .contains("\"question\":\"女巫法术\"")
                .contains("\"id\":\"a\"")
                .contains("\"title\":\"A\"")
                .contains("\"module\":\"spell\"")
                .contains("\"book\":\"CRB\"")
                .doesNotContain("tools");
    }

    @Test
    void defaultConfigurationKeepsBoundedPoolAndTimeout() {
        DeepSeekListwiseReranker reranker = new DeepSeekListwiseReranker();

        assertThat(ReflectionTestUtils.getField(reranker, "timeout")).isEqualTo(Duration.ofSeconds(8));
        assertThat(ReflectionTestUtils.getField(reranker, "summaryChars")).isEqualTo(300);
        assertThat(ReflectionTestUtils.getField(reranker, "concurrency")).isEqualTo(4);
        assertThat(ReflectionTestUtils.getField(reranker, "queueCapacity")).isEqualTo(16);
        assertThat(ReflectionTestUtils.getField(reranker, "defaultModel")).isEqualTo("deepseek-flash");
    }

    private boolean waitForIdle(DeepSeekListwiseReranker reranker) throws InterruptedException {
        ThreadPoolExecutor pool = (ThreadPoolExecutor) ReflectionTestUtils.getField(reranker, "executor");
        if (pool == null) {
            return true;
        }
        long deadline = System.currentTimeMillis() + 2000;
        while (System.currentTimeMillis() < deadline) {
            if (pool.getActiveCount() == 0 && pool.getQueue().isEmpty()) {
                return true;
            }
            Thread.sleep(20);
        }
        return false;
    }

    private DeepSeekListwiseReranker reranker(Duration timeout) {
        DeepSeekListwiseReranker reranker = new DeepSeekListwiseReranker();
        ReflectionTestUtils.setField(reranker, "httpClient", httpClient);
        ReflectionTestUtils.setField(reranker, "usageRecorder", usageRecorder);
        ReflectionTestUtils.setField(reranker, "summaryChars", 300);
        ReflectionTestUtils.setField(reranker, "timeout", timeout);
        ReflectionTestUtils.setField(reranker, "defaultModel", "deepseek-flash");
        return reranker;
    }

    private Candidate candidate(String id, String title) {
        Document doc = Document.builder()
                .text(title + " 的正文")
                .metadata(Map.of("chunk_id", id))
                .score(0.9)
                .build();
        return new DeepSeekListwiseReranker.Candidate(id, title, "spell", "CRB",
                doc.getText(), doc);
    }

    private RerankResult result(String content) {
        return new RerankResult(content, "deepseek-flash", 10, 5, 15, 20L);
    }
}
