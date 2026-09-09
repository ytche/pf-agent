package com.pfagent.agent.config;

import org.springframework.ai.document.Document;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.embedding.EmbeddingRequest;
import org.springframework.ai.embedding.EmbeddingResponse;

import java.util.List;

/**
 * 截断型 EmbeddingModel 包装器
 *
 * 背景：nomic-embed-text 的上下文窗口为 2048 token，法术库中少数超长
 * chunk（12 条，最长 4.3 万字符）会触发 Ollama 400 错误。包装器在向量化
 * 时把输入截断到安全长度，但 Document 全文（text）保持不变——截断只影响
 * 相似度检索的向量质量（关键字段集中在开头，影响很小），来源展示与 prompt
 * 仍使用完整文本。
 */
public class TruncatingEmbeddingModel implements EmbeddingModel {

    private final EmbeddingModel delegate;
    private final int maxChars;

    public TruncatingEmbeddingModel(EmbeddingModel delegate, int maxChars) {
        this.delegate = delegate;
        this.maxChars = maxChars;
    }

    @Override
    public EmbeddingResponse call(EmbeddingRequest request) {
        List<String> truncated = request.getInstructions().stream()
                .map(this::truncate)
                .toList();
        return delegate.call(new EmbeddingRequest(truncated, request.getOptions()));
    }

    @Override
    public float[] embed(Document document) {
        return delegate.embed(truncate(document.getText()));
    }

    @Override
    public float[] embed(String text) {
        return delegate.embed(truncate(text));
    }

    @Override
    public EmbeddingResponse embedForResponse(List<String> texts) {
        return delegate.embedForResponse(texts.stream().map(this::truncate).toList());
    }

    @Override
    public int dimensions() {
        return delegate.dimensions();
    }

    private String truncate(String text) {
        if (text == null) {
            return "";
        }
        return text.length() <= maxChars ? text : text.substring(0, maxChars);
    }
}
