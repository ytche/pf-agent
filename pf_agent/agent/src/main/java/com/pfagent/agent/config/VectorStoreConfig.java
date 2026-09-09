package com.pfagent.agent.config;

import com.pfagent.agent.rag.VectorStorePersistence;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.vectorstore.SimpleVectorStore;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 向量库配置
 *
 * 每个数据模块（法术/职业等八个）一个独立向量库：
 *  - 模块解耦，重建/替换某一模块的数据不牵连其他模块
 *  - 各自持久化为独立 JSON，重启时直接加载
 *  - 检索侧按模块独立召回后合并（见 SearchService）
 *
 * 对外 bean 暴露 {@link VectorStore} 接口类型（SP1 §4 收口），消费方不感知具体实现
 * （当前是 SimpleVectorStore）；文件加载/落盘走 {@code VectorStorePersistence}。
 *
 * 注意：工程同时引入 openai(DeepSeek chat) 与 ollama(本地 embedding) 两个 starter，
 * 存在多个 EmbeddingModel Bean。8 个 store 统一消费 {@link EmbeddingConfig} 产出的
 * 组合 Bean {@code queryEmbeddingModel}（SP5 双通道：默认 ollama 单通道裸返回、
 * 可选 cloud 托管 bge-m3 主/备 + 启动维度自检对齐本地 1024 维向量库），消费方零
 * 感知通道细节；不用 @Qualifier 会因多候选注入歧义。
 */
@Configuration
public class VectorStoreConfig {

    /**
     * embedding 输入的最大字符数。
     *
     * bge-m3 上下文 8192 token，但中文在 XLM-RoBERTa tokenizer 下约 1.2–1.5
     * token/字（生僻字与标点膨胀），6000 字符的混合文本实测会超限（5843 成功、
     * 6000 失败）。降到 5000 保留足够余量；截断只影响向量质量，Document 全文不变。
     */
    private static final int MAX_EMBED_CHARS = 5000;

    @Autowired
    private VectorStorePersistence persistence;

    @Bean
    public VectorStore spellVectorStore(
            @Qualifier("queryEmbeddingModel") EmbeddingModel embeddingModel,
            @Value("${pf.stores.spell-file-path}") String path) {
        return buildStore(embeddingModel, path);
    }

    @Bean
    public VectorStore classVectorStore(
            @Qualifier("queryEmbeddingModel") EmbeddingModel embeddingModel,
            @Value("${pf.stores.class-file-path}") String path) {
        return buildStore(embeddingModel, path);
    }

    // ---- 六个标准模块（专长/种族/背景特性/装备/技能/规则）----
    // 共用统一行模型 StandardChunk + StandardChunkMapper，每个模块一个独立向量库：
    // 模块解耦，重建/替换某一模块的数据不牵连其他模块。

    @Bean
    public VectorStore featVectorStore(
            @Qualifier("queryEmbeddingModel") EmbeddingModel embeddingModel,
            @Value("${pf.stores.feat-file-path}") String path) {
        return buildStore(embeddingModel, path);
    }

    @Bean
    public VectorStore raceVectorStore(
            @Qualifier("queryEmbeddingModel") EmbeddingModel embeddingModel,
            @Value("${pf.stores.race-file-path}") String path) {
        return buildStore(embeddingModel, path);
    }

    @Bean
    public VectorStore traitVectorStore(
            @Qualifier("queryEmbeddingModel") EmbeddingModel embeddingModel,
            @Value("${pf.stores.trait-file-path}") String path) {
        return buildStore(embeddingModel, path);
    }

    @Bean
    public VectorStore equipmentVectorStore(
            @Qualifier("queryEmbeddingModel") EmbeddingModel embeddingModel,
            @Value("${pf.stores.equipment-file-path}") String path) {
        return buildStore(embeddingModel, path);
    }

    @Bean
    public VectorStore skillVectorStore(
            @Qualifier("queryEmbeddingModel") EmbeddingModel embeddingModel,
            @Value("${pf.stores.skill-file-path}") String path) {
        return buildStore(embeddingModel, path);
    }

    @Bean
    public VectorStore ruleVectorStore(
            @Qualifier("queryEmbeddingModel") EmbeddingModel embeddingModel,
            @Value("${pf.stores.rule-file-path}") String path) {
        return buildStore(embeddingModel, path);
    }

    /**
     * 构建单模块向量库：文件存在则加载，否则等待对应 DataLoader 构建
     */
    private VectorStore buildStore(EmbeddingModel embeddingModel, String path) {
        // 包装截断逻辑：向量化输入超长时截断，避免 Ollama 400 错误（Document 全文保留）
        EmbeddingModel safeEmbedding = new TruncatingEmbeddingModel(embeddingModel, MAX_EMBED_CHARS);
        VectorStore store = SimpleVectorStore.builder(safeEmbedding).build();
        // 文件持久化隔离到 VectorStorePersistence（VectorStore 接口无 load/save 方法）
        persistence.loadIfExists(store, path);
        return store;
    }
}
