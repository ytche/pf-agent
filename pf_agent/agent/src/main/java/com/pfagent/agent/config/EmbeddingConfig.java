package com.pfagent.agent.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.MetadataMode;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.openai.OpenAiEmbeddingModel;
import org.springframework.ai.openai.OpenAiEmbeddingOptions;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.support.RetryTemplate;

/**
 * embedding 双通道配置（SP5 D1~D7）
 *
 * 单一组合 Bean {@code queryEmbeddingModel} 对消费方（VectorStoreConfig 8 个 store）
 * 完全透明：配置端决定主/备通道与是否兜底，消费方只认这一个 Bean，不感知通道细节。
 *
 * 通道链决策（D2/D6）：
 *  - primary=ollama（默认）且未启用 fallback → 直接暴露本地模型（裸主通道，零包装，
 *    行为与 SP5 前逐字一致：无 cloud Bean、无维度自检、无新增网络调用）；
 *  - primary=ollama + fallback-enabled → Fallback(ollama, cloud)，本地挂时降级云端；
 *  - primary=cloud → 主云端；fallback-enabled 未显式设置时按 D6 默认 true；
 *  - fallback-enabled=false → 裸主通道。
 * cloud 参与（主或备）而 base-url / api-key 缺失 → 启动 fail-fast（D3：api-key 只经
 * 环境变量 {@code PF_EMBEDDING_CLOUD_API_KEY} 注入，严禁入库，日志不含 key）。
 *
 * 维度自检（D5）：cloud 参与时启动对 cloud 通道执行一次 {@code embed("维度探测")}，
 * 断言维度 == 1024（本地 bge-m3 向量库维度，模型一致性约束见决策记录 §关键技术约束：
 * 换模型 = 重建 ~600MB 向量库，禁止）。不符 fail-fast，防「检索全废但服务照起」。
 *
 * 观测（D7）：启动日志打印生效通道链；每次降级由 FallbackEmbeddingModel 记 WARN。
 */
@Configuration
public class EmbeddingConfig {

    private static final Logger log = LoggerFactory.getLogger(EmbeddingConfig.class);

    /** 本地 bge-m3 向量库维度（8 个 vector_store_*.json 均由本地 bge-m3 构建，1024 维）——D5 探测对齐值 */
    static final int BGE_M3_DIMENSIONS = 1024;
    /** D5 启动维度探测文本（非空串，避免个别 embedding 服务对空输入 400）；包可见供单测 stub 对齐 */
    static final String DIMENSION_PROBE_TEXT = "维度探测";

    @Value("${pf.embedding.primary:ollama}")
    private String primary;
    /** 三态：显式 false/true 覆盖 D6 默认；空串（未显式设置）→ primary=cloud 默认 true、ollama 默认 false */
    @Value("${pf.embedding.fallback-enabled:}")
    private String fallbackEnabledRaw;
    @Value("${pf.embedding.cloud.base-url:}")
    private String cloudBaseUrl;
    @Value("${pf.embedding.cloud.api-key:}")
    private String cloudApiKey;
    @Value("${pf.embedding.cloud.model:BAAI/bge-m3}")
    private String cloudModel;

    /**
     * 组合 Bean：按 D2/D6 矩阵决定通道链，VectorStoreConfig 8 处 store 唯一引用点。
     *
     * @param ollamaEmbeddingModel 本地 bge-m3（OllamaAutoConfiguration 产物）
     * @param retryTemplate        Spring AI retry（max-attempts=1，超时不放大，与 fallback 语义兼容）
     */
    @Bean
    public EmbeddingModel queryEmbeddingModel(
            @Qualifier("ollamaEmbeddingModel") EmbeddingModel ollamaEmbeddingModel,
            ObjectProvider<RetryTemplate> retryTemplate) {
        boolean cloudIsPrimary = cloudPrimary();
        boolean fallback = fallbackEnabled(cloudIsPrimary);
        boolean cloudActive = cloudIsPrimary || fallback;
        if (!cloudActive) {
            // D6 行1：默认 ollama 单通道——裸主通道返回，零包装、无 cloud 装配、无自检、无网络新增
            log.info("embedding 通道链: primary=ollama（默认单通道，fallback 未启用）");
            return ollamaEmbeddingModel;
        }
        requireCloudConfig(); // 先校验再建通道（fail-fast 早于任何网络调用）
        EmbeddingModel cloud = buildCloudEmbeddingModel(retryTemplate.getIfAvailable());
        assertBgeM3Dimensions(cloud); // D5 启动维度自检
        if (cloudIsPrimary) {
            log.info("embedding 通道链: primary=cloud[{}], fallback={}", cloudModel, fallback ? "ollama" : "无");
            return compose(cloud, fallback ? ollamaEmbeddingModel : null, "cloud", "ollama");
        }
        log.info("embedding 通道链: primary=ollama, fallback=cloud[{}]", cloudModel);
        return compose(ollamaEmbeddingModel, cloud, "ollama", "cloud");
    }

    /**
     * 构造 cloud 通道（托管 bge-m3，OpenAI 兼容 embeddings）。
     *
     * 独立于 spring.ai.openai.*（那是 DeepSeek chat 的 base-url，本通道不复用其配置）；
     * 手工构造 {@link OpenAiEmbeddingModel}，OpenAiApi 只做客户端装配，此处不触网
     * （网络仅发生在实际 embed 调用）。protected 为可覆写 seam——单测继承本类替换为
     * stub 模型，即可离线验证 cloud 参与时的完整通道链（维度自检 + 兜底组合）。
     */
    protected EmbeddingModel buildCloudEmbeddingModel(RetryTemplate retryTemplate) {
        OpenAiApi api = new OpenAiApi(cloudBaseUrl.trim(), cloudApiKey.trim());
        OpenAiEmbeddingOptions options = OpenAiEmbeddingOptions.builder().model(cloudModel.trim()).build();
        if (retryTemplate != null) {
            return new OpenAiEmbeddingModel(api, MetadataMode.EMBED, options, retryTemplate);
        }
        return new OpenAiEmbeddingModel(api, MetadataMode.EMBED, options);
    }

    /**
     * D5 启动维度自检：cloud 通道嵌入一次探测文本，断言维度 == 本地 bge-m3 库维度。
     * 不符 → fail-fast（启动失败并提示核对 model），防「向量库 1024 维 / 云通道异维，
     * 检索全废但服务照起」。探测文本非空，避免空输入被部分服务 400。
     */
    static void assertBgeM3Dimensions(EmbeddingModel cloud) {
        float[] probe = cloud.embed(DIMENSION_PROBE_TEXT);
        int actual = probe == null ? -1 : probe.length;
        if (actual != BGE_M3_DIMENSIONS) {
            throw new IllegalStateException("云通道 embedding 实际维度=" + actual + "，与本地 bge-m3 向量库维度 "
                    + BGE_M3_DIMENSIONS + " 不一致。模型一致性约束：换模型=重建向量库，请确认"
                    + " pf.embedding.cloud.model=BAAI/bge-m3");
        }
    }

    /**
     * 通道链组合：backup 为 null → 裸主通道（fallback-enabled=false，零包装）；
     * 否则包 {@link FallbackEmbeddingModel}（主通道失败自动降级备通道）。
     */
    static EmbeddingModel compose(EmbeddingModel main, EmbeddingModel backup,
                                  String mainName, String backupName) {
        if (backup == null) {
            return main;
        }
        return new FallbackEmbeddingModel(main, backup, mainName, backupName);
    }

    private boolean cloudPrimary() {
        return "cloud".equalsIgnoreCase(primary.trim());
    }

    private boolean fallbackEnabled(boolean cloudIsPrimary) {
        if (fallbackEnabledRaw != null && !fallbackEnabledRaw.isBlank()) {
            return Boolean.parseBoolean(fallbackEnabledRaw.trim());
        }
        // D6：未显式设置时 primary=cloud 默认启用 fallback（防云端单点），ollama 默认不启用（零行为变化）
        return cloudIsPrimary;
    }

    /** D3：cloud 参与（主或备）而 base-url / api-key 缺失 → 启动 fail-fast，报清晰错误，不静默回退 */
    private void requireCloudConfig() {
        if (cloudBaseUrl == null || cloudBaseUrl.isBlank()) {
            throw new IllegalStateException("pf.embedding 启用了 cloud 通道（primary/fallback）但未配置"
                    + " pf.embedding.cloud.base-url");
        }
        if (cloudApiKey == null || cloudApiKey.isBlank()) {
            throw new IllegalStateException("pf.embedding 的 cloud 通道参与（primary/fallback）但 api-key 为空："
                    + "请设置环境变量 PF_EMBEDDING_CLOUD_API_KEY——只经 env 注入，严禁写入 yml/代码/日志");
        }
    }
}
