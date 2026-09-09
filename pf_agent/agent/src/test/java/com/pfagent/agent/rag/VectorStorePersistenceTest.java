package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.ai.document.Document;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.SimpleVectorStore;
import org.springframework.ai.vectorstore.VectorStore;

import java.nio.file.Path;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * VectorStorePersistence 边界测试（SP1 T5）
 *
 * T4 收口后 load/save 从 store 实例方法迁移到 SimpleVectorStorePersistence；
 * 验证语义不变：save 建父目录落盘、loadIfExists 还原可检索内容、文件缺失不抛、
 * 非 SimpleVectorStore 实现静默跳过。
 */
class VectorStorePersistenceTest {

    @TempDir
    Path tempDir;

    private final VectorStorePersistence persistence = new SimpleVectorStorePersistence();

    /** save 自动建父目录并落盘；loadIfExists 到新 store 后可检索出相同内容 */
    @Test
    void saveThenLoadRestoresDocuments() {
        SimpleVectorStore source = SimpleVectorStore.builder(embeddingModel()).build();
        source.add(List.of(doc("火球术说明"), doc("治疗术说明")));

        Path storeFile = tempDir.resolve("nested/dir/store.json"); // 父目录不存在，应自动创建
        persistence.save(source, storeFile.toString());

        assertThat(storeFile).exists();

        SimpleVectorStore loaded = SimpleVectorStore.builder(embeddingModel()).build();
        persistence.loadIfExists(loaded, storeFile.toString());

        List<Document> hits = loaded.similaritySearch(
                SearchRequest.builder().query("任意查询").topK(5).build());
        assertThat(hits).extracting(Document::getText)
                .containsExactlyInAnyOrder("火球术说明", "治疗术说明");
    }

    /** 持久化文件不存在：loadIfExists 静默返回（等 DataLoader 构建），store 仍可正常使用 */
    @Test
    void loadIfExistsMissingFileDoesNotThrow() {
        SimpleVectorStore store = SimpleVectorStore.builder(embeddingModel()).build();

        assertThatCode(() -> persistence.loadIfExists(
                store, tempDir.resolve("absent.json").toString()))
                .doesNotThrowAnyException();

        // 文件缺失的 store 可继续 add 新数据，不因「未加载」处于坏状态
        assertThatCode(() -> store.add(List.of(doc("追加内容")))).doesNotThrowAnyException();
    }

    /** 非 SimpleVectorStore 实现（如 mock 的其它 VectorStore）：save/load 静默跳过不抛 */
    @Test
    void nonSimpleVectorStorePersistenceIsNoOp() {
        VectorStore other = mock(VectorStore.class);
        Path file = tempDir.resolve("other.json");

        assertThatCode(() -> persistence.save(other, file.toString())).doesNotThrowAnyException();
        assertThat(file).doesNotExist();

        assertThatCode(() -> persistence.loadIfExists(other, file.toString()))
                .doesNotThrowAnyException();
    }

    /** 固定一维向量：add 时 doc 嵌入、检索时 query 嵌入都返回它，余弦 = 1，命中全部 */
    private static EmbeddingModel embeddingModel() {
        EmbeddingModel model = mock(EmbeddingModel.class);
        when(model.embed(any(Document.class))).thenReturn(new float[]{1.0f});
        when(model.embed(anyString())).thenReturn(new float[]{1.0f});
        when(model.dimensions()).thenReturn(1);
        return model;
    }

    private static Document doc(String text) {
        return Document.builder().text(text).build();
    }
}
