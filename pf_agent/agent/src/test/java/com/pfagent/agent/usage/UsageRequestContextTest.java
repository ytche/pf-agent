package com.pfagent.agent.usage;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 请求级用量上下文：ThreadLocal 并发隔离、同线程二次 begin 重置、finally clear 幂等。
 */
class UsageRequestContextTest {

    private final UsageRequestContext context = new UsageRequestContext();
    private final ExecutorService executor = Executors.newFixedThreadPool(2);

    @AfterEach
    void tearDown() {
        executor.shutdownNow();
    }

    @Test
    void secondBeginOnSameThreadStartsNewRequestAtSeqOne() {
        context.begin("cid-1", 7L);
        UsageRequestContext.CallScope first = context.nextCall().orElseThrow();
        UsageRequestContext.CallScope secondCall = context.nextCall().orElseThrow();

        context.begin("cid-2", 8L);
        UsageRequestContext.CallScope afterBegin = context.nextCall().orElseThrow();

        assertThat(first.requestId()).isNotBlank();
        assertThat(secondCall.requestId()).isEqualTo(first.requestId());
        assertThat(secondCall.callSeq()).isEqualTo(2);

        assertThat(afterBegin.requestId()).isNotEqualTo(first.requestId());
        assertThat(afterBegin.callSeq()).isEqualTo(1);
        assertThat(afterBegin.conversationId()).isEqualTo("cid-2");
        assertThat(afterBegin.ownerId()).isEqualTo(8L);
    }

    @Test
    void clearIsIdempotentAndRemovesThreadLocal() {
        context.begin("cid", 1L);
        context.clear();
        context.clear();

        assertThat(context.peek()).isEmpty();
        assertThat(context.nextCall()).isEmpty();
    }

    @Test
    void twoThreadsDoNotShareRequestState() throws Exception {
        List<UsageRequestContext.CallScope> scopes = new CopyOnWriteArrayList<>();
        CountDownLatch bothStarted = new CountDownLatch(2);
        CountDownLatch bothRecorded = new CountDownLatch(2);

        Runnable workerA = () -> recordOnThread("cid-a", 1L, scopes, bothStarted, bothRecorded);
        Runnable workerB = () -> recordOnThread("cid-b", 2L, scopes, bothStarted, bothRecorded);
        executor.submit(workerA);
        executor.submit(workerB);

        assertThat(bothStarted.await(5, TimeUnit.SECONDS)).isTrue();
        assertThat(bothRecorded.await(5, TimeUnit.SECONDS)).isTrue();
        executor.shutdown();
        assertThat(executor.awaitTermination(5, TimeUnit.SECONDS)).isTrue();

        UsageRequestContext.CallScope scopeA = scopes.stream()
                .filter(scope -> "cid-a".equals(scope.conversationId())).findFirst().orElseThrow();
        UsageRequestContext.CallScope scopeB = scopes.stream()
                .filter(scope -> "cid-b".equals(scope.conversationId())).findFirst().orElseThrow();
        assertThat(scopeA.requestId()).isNotEqualTo(scopeB.requestId());
        assertThat(scopeA.callSeq()).isEqualTo(1);
        assertThat(scopeB.callSeq()).isEqualTo(1);
        assertThat(scopeA.ownerId()).isEqualTo(1L);
        assertThat(scopeB.ownerId()).isEqualTo(2L);
    }

    private void recordOnThread(String cid, Long ownerId, List<UsageRequestContext.CallScope> scopes,
                                CountDownLatch bothStarted, CountDownLatch bothRecorded) {
        try {
            context.begin(cid, ownerId);
            bothStarted.countDown();
            bothStarted.await(5, TimeUnit.SECONDS);
            scopes.add(context.nextCall().orElseThrow());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } finally {
            context.clear();
            bothRecorded.countDown();
        }
    }
}
