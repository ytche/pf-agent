package com.pfagent.agent.config;

import org.junit.jupiter.api.Test;
import org.springframework.ai.document.Document;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.embedding.EmbeddingRequest;
import org.springframework.ai.embedding.EmbeddingResponse;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * FallbackEmbeddingModel 单测（SP5 D4）
 *
 * 三分支：主通道成功 → 直传备通道不触；主通道异常 → 记 WARN 降级备通道；
 * 双通道同挂 → 备通道异常上抛（不吞错）。
 * 入口面：call / embed(Document) / embed(String) / embedForResponse 均被兜底包裹；
 * dimensions()（V5 R1 修复）同样纳入兜底——主失败降备，结果缓存避免观测链路
 * 每次检索的重复探测（首次解析后不再触主通道）。
 */
class FallbackEmbeddingModelTest {

    private final EmbeddingModel primary = mock(EmbeddingModel.class);
    private final EmbeddingModel fallback = mock(EmbeddingModel.class);
    private final FallbackEmbeddingModel model =
            new FallbackEmbeddingModel(primary, fallback, "ollama", "cloud");

    /** 主通道成功 → 直接返回主通道结果，备通道零调用（主成功零开销直传） */
    @Test
    void embedReturnsPrimaryWhenPrimarySucceeds() {
        when(primary.embed("火球")).thenReturn(new float[]{1f, 2f});
        when(fallback.embed("火球")).thenReturn(new float[]{9f, 9f});

        float[] result = model.embed("火球");

        assertThat(result).containsExactly(1f, 2f);
        verify(fallback, never()).embed("火球");
    }

    /** 主通道异常 → 降级备通道返回其结果 */
    @Test
    void embedFallsBackToSecondaryWhenPrimaryThrows() {
        when(primary.embed("火球")).thenThrow(new RuntimeException("Ollama down"));
        when(fallback.embed("火球")).thenReturn(new float[]{3f, 4f});

        float[] result = model.embed("火球");

        assertThat(result).containsExactly(3f, 4f);
        verify(primary).embed("火球");
    }

    /** 双通道同挂 → 备通道异常上抛（不吞错、不循环） */
    @Test
    void embedPropagatesWhenBothChannelsFail() {
        when(primary.embed("火球")).thenThrow(new RuntimeException("Ollama down"));
        when(fallback.embed("火球")).thenThrow(new RuntimeException("cloud 400"));

        assertThatThrownBy(() -> model.embed("火球"))
                .isInstanceOf(RuntimeException.class)
                .hasMessage("cloud 400");
    }

    /** embed(Document) 入口同样兜底（SimpleVectorStore.add 走此路径） */
    @Test
    void embedDocumentFallsBackOnPrimaryFailure() {
        Document doc = new Document("火球术正文");
        when(primary.embed(doc)).thenThrow(new RuntimeException("Ollama down"));
        when(fallback.embed(doc)).thenReturn(new float[]{5f, 6f});

        float[] result = model.embed(doc);

        assertThat(result).containsExactly(5f, 6f);
    }

    /** embedForResponse 批量入口兜底（Tools 侧批量 query 向量场景） */
    @Test
    void embedForResponseFallsBackOnPrimaryFailure() {
        EmbeddingResponse secondary = mock(EmbeddingResponse.class);
        when(primary.embedForResponse(List.of("a"))).thenThrow(new RuntimeException("Ollama down"));
        when(fallback.embedForResponse(List.of("a"))).thenReturn(secondary);

        EmbeddingResponse result = model.embedForResponse(List.of("a"));

        assertThat(result).isSameAs(secondary);
    }

    /** call(EmbeddingRequest) 兜底 */
    @Test
    void callFallsBackOnPrimaryFailure() {
        EmbeddingRequest req = new EmbeddingRequest(List.of("a"), null);
        EmbeddingResponse secondary = mock(EmbeddingResponse.class);
        when(primary.call(req)).thenThrow(new RuntimeException("Ollama down"));
        when(fallback.call(req)).thenReturn(secondary);

        EmbeddingResponse result = model.call(req);

        assertThat(result).isSameAs(secondary);
    }

    /** dimensions 健康基线：主通道成功 → 返回主维度，备通道零调用 */
    @Test
    void dimensionsReturnsPrimaryWhenPrimarySucceeds() {
        when(primary.dimensions()).thenReturn(1024);
        when(fallback.dimensions()).thenReturn(512);

        assertThat(model.dimensions()).isEqualTo(1024);
        verify(fallback, never()).dimensions();
    }

    /** V5 R1：dimensions 主通道异常 → 降级备通道（Spring AI 观测链路每次检索先调 dimensions，须可兜底） */
    @Test
    void dimensionsFallsBackToSecondaryWhenPrimaryThrows() {
        when(primary.dimensions()).thenThrow(new RuntimeException("cloud down"));
        when(fallback.dimensions()).thenReturn(1024);

        assertThat(model.dimensions()).isEqualTo(1024);
        verify(fallback).dimensions();
    }

    /** V5 R1：dimensions 结果缓存——二次调用直接返回缓存，不再触主通道（观测链路每检索必调，须零网络往返） */
    @Test
    void dimensionsResultIsCachedAfterFirstResolution() {
        when(primary.dimensions()).thenReturn(1024);
        when(fallback.dimensions()).thenReturn(512);

        assertThat(model.dimensions()).isEqualTo(1024);
        assertThat(model.dimensions()).isEqualTo(1024);
        verify(primary, times(1)).dimensions();
        verify(fallback, never()).dimensions();
    }

    /** V5 R1：dimensions 双通道同挂 → 备通道异常上抛（不吞错、不循环） */
    @Test
    void dimensionsPropagatesWhenBothChannelsFail() {
        when(primary.dimensions()).thenThrow(new RuntimeException("cloud down"));
        when(fallback.dimensions()).thenThrow(new RuntimeException("ollama down"));

        assertThatThrownBy(() -> model.dimensions())
                .isInstanceOf(RuntimeException.class)
                .hasMessage("ollama down");
    }
}
