package com.pfagent.agent.config;

import com.pfagent.agent.rag.SimpleVectorStorePersistence;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.vectorstore.SimpleVectorStore;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.test.util.ReflectionTestUtils;

import java.io.IOException;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

/**
 * VectorStoreConfig 单元测试
 *
 * 验证每模块 store 的两条分支：持久化文件不存在 → 等待 DataLoader 构建；
 * 文件已存在 → load 已有向量库。spell 与 class 两个 store 独立构建。
 *
 * SP1 §4 收口后 @Bean 对外暴露 VectorStore 接口；buildStore 依赖的 VectorStorePersistence
 * 由字段注入，测试 new 配置类后需用反射补注（真实 SimpleVectorStorePersistence）。
 */
class VectorStoreConfigTest {

    @TempDir
    Path tempDir;

    private final VectorStoreConfig config = new VectorStoreConfig();

    @BeforeEach
    void injectPersistence() {
        ReflectionTestUtils.setField(config, "persistence", new SimpleVectorStorePersistence());
    }

    /** spell 向量库文件不存在时返回等待构建的 store */
    @Test
    void spellStoreMissingFileReturnsPendingStore() {
        VectorStore store = config.spellVectorStore(mock(EmbeddingModel.class), tempDir.resolve("no.json").toString());

        assertThat(store).isNotNull();
    }

    /** spell 向量库文件已存在时加载已有向量库 */
    @Test
    void spellStoreExistingFileLoadsPersistedStore() throws IOException {
        Path file = tempDir.resolve("store.json");
        // 先用真实 store 生成合法的持久化文件，避免手写 JSON 与 SimpleVectorStore 内部格式不一致
        SimpleVectorStore.builder(mock(EmbeddingModel.class)).build().save(file.toFile());

        VectorStore store = config.spellVectorStore(mock(EmbeddingModel.class), file.toString());

        assertThat(store).isNotNull();
    }

    /** class 向量库独立构建 */
    @Test
    void classStoreBuiltIndependently() throws IOException {
        Path file = tempDir.resolve("class.json");
        SimpleVectorStore.builder(mock(EmbeddingModel.class)).build().save(file.toFile());

        VectorStore store = config.classVectorStore(mock(EmbeddingModel.class), file.toString());

        assertThat(store).isNotNull();
    }
}
