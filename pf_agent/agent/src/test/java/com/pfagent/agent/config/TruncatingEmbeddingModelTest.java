package com.pfagent.agent.config;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.document.Document;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.embedding.EmbeddingRequest;
import org.springframework.ai.embedding.EmbeddingResponse;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * TruncatingEmbeddingModel 单元测试
 *
 * 验证超长输入截断到 maxChars、null 文本兜底为空串，
 * 且截断仅作用于向量化输入（Document 全文不在此层修改）。
 */
@ExtendWith(MockitoExtension.class)
class TruncatingEmbeddingModelTest {

    @Mock
    private EmbeddingModel delegate;

    /** 超长文本截断后转发给底层模型 */
    @Test
    void callTruncatesOversizedText() {
        TruncatingEmbeddingModel model = model();
        when(delegate.call(any(EmbeddingRequest.class))).thenReturn(new EmbeddingResponse(List.of()));

        model.call(new EmbeddingRequest(List.of("short", "x".repeat(30)), null));

        ArgumentCaptor<EmbeddingRequest> captor = ArgumentCaptor.forClass(EmbeddingRequest.class);
        verify(delegate).call(captor.capture());
        List<String> truncated = captor.getValue().getInstructions();
        assertThat(truncated).hasSize(2);
        assertThat(truncated.get(0)).isEqualTo("short");      // 未超长保持原样
        assertThat(truncated.get(1)).hasSize(10);             // 超长截断
    }

    /** 调用时转发 options */
    @Test
    void callForwardsOptions() {
        TruncatingEmbeddingModel model = model();
        when(delegate.call(any(EmbeddingRequest.class))).thenReturn(new EmbeddingResponse(List.of()));

        model.call(new EmbeddingRequest(List.of("t"), null));

        ArgumentCaptor<EmbeddingRequest> captor = ArgumentCaptor.forClass(EmbeddingRequest.class);
        verify(delegate).call(captor.capture());
        assertThat(captor.getValue().getOptions()).isNull();
    }

    /** embed 的 document 文本超长时截断后委托底层模型 */
    @Test
    void embedDocumentTruncatesThenDelegates() {
        TruncatingEmbeddingModel model = model();
        when(delegate.embed(anyString())).thenReturn(new float[]{1f, 2f});

        float[] result = model.embed(Document.builder().text("x".repeat(25)).build());

        assertThat(result).containsExactly(1f, 2f);
        ArgumentCaptor<String> captor = ArgumentCaptor.forClass(String.class);
        verify(delegate).embed(captor.capture());
        assertThat(captor.getValue()).hasSize(10);
    }

    /** embed 的字符串未超长时不截断 */
    @Test
    void embedStringUnderLimitNotTruncated() {
        TruncatingEmbeddingModel model = model();
        when(delegate.embed(anyString())).thenReturn(new float[]{0f});

        model.embed("abc");

        verify(delegate).embed("abc");
    }

    /** embed 的 null 文本按空串处理 */
    @Test
    void embedNullTextHandledAsEmpty() {
        TruncatingEmbeddingModel model = model();
        when(delegate.embed(anyString())).thenReturn(new float[]{0f});

        model.embed((String) null);

        verify(delegate).embed("");
    }

    /** embedForResponse 对每条内容逐条截断 */
    @Test
    void embedForResponseTruncatesEachItem() {
        TruncatingEmbeddingModel model = model();
        when(delegate.embedForResponse(anyList())).thenReturn(new EmbeddingResponse(List.of()));

        model.embedForResponse(List.of("a".repeat(20), "ok"));

        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<String>> captor = ArgumentCaptor.forClass(List.class);
        verify(delegate).embedForResponse(captor.capture());
        assertThat(captor.getValue().get(0)).hasSize(10);
        assertThat(captor.getValue().get(1)).isEqualTo("ok");
    }

    /** dimensions 委托底层模型 */
    @Test
    void dimensionsDelegatesToUnderlyingModel() {
        TruncatingEmbeddingModel model = model();
        when(delegate.dimensions()).thenReturn(1024);

        assertThat(model.dimensions()).isEqualTo(1024);
    }

    /** 用 10 字符的极短上限，便于构造超长样例 */
    private TruncatingEmbeddingModel model() {
        return new TruncatingEmbeddingModel(delegate, 10);
    }
}
