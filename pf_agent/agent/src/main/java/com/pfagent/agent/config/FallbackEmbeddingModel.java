package com.pfagent.agent.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.document.Document;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.embedding.EmbeddingRequest;
import org.springframework.ai.embedding.EmbeddingResponse;

import java.util.List;
import java.util.function.Supplier;

/**
 * 双通道 embedding：主通道失败 → 降级备通道（SP5 D4）。
 *
 * 背景：查询向量化历史单通道硬绑本地 Ollama（进程挂 / 无 GPU → 检索全废）。
 * 本类把「主通道成功零开销直传、失败降级备通道」的语义包成一层，对消费方
 * （TruncatingEmbeddingModel / SimpleVectorStore）完全透明。
 *
 * 兜底语义：
 *  - 逐次调用降级，不记状态、不做熔断——主通道恢复后下次调用自动回主；
 *  - 每次降级记一条 WARN（含主通道名 + 异常摘要，不含任何 key/token）；
 *  - 双通道同挂：主通道 WARN 后，备通道异常原样上抛（不吞错、不循环）。
 *
 * 覆写面与 {@link TruncatingEmbeddingModel} 一致（call / embed(Document) /
 * embed(String) / embedForResponse / dimensions），保证任意入口都被兜底包裹。
 * 模型一致性约束（决策记录 §关键技术约束）：云通道只能选托管版 bge-m3，
 * 维度必须与本地向量库（1024）一致——装配侧（EmbeddingConfig）启动自检。
 */
public class FallbackEmbeddingModel implements EmbeddingModel {

    private static final Logger log = LoggerFactory.getLogger(FallbackEmbeddingModel.class);

    private final EmbeddingModel primary;
    private final EmbeddingModel fallback;
    private final String primaryName;
    private final String fallbackName;

    /**
     * dimensions() 结果缓存（0 = 未初始化哨兵）。
     *
     * Spring AI 观测链路每次 similaritySearch 都会调 dimensions() 构建观测上下文，若不缓存，
     * cloud 主健康时每次检索多一次云端 API 往返（验收 P2）。首次经主/备兜底解析成功后写缓存；
     * volatile 保证跨线程可见——多线程首并发各解析一次无害（主/备同 bge-m3，维度恒定 1024）。
     * 用 0 作哨兵安全：embedding 维度现实不可能为 0（D5 启动已断言 1024）。
     */
    private volatile int cachedDimensions = 0;

    public FallbackEmbeddingModel(EmbeddingModel primary, EmbeddingModel fallback,
                                  String primaryName, String fallbackName) {
        this.primary = primary;
        this.fallback = fallback;
        this.primaryName = primaryName;
        this.fallbackName = fallbackName;
    }

    @Override
    public EmbeddingResponse call(EmbeddingRequest request) {
        return withFallback(() -> primary.call(request), () -> fallback.call(request), "call");
    }

    @Override
    public float[] embed(Document document) {
        return withFallback(() -> primary.embed(document), () -> fallback.embed(document), "embed(Document)");
    }

    @Override
    public float[] embed(String text) {
        return withFallback(() -> primary.embed(text), () -> fallback.embed(text), "embed");
    }

    @Override
    public EmbeddingResponse embedForResponse(List<String> texts) {
        return withFallback(() -> primary.embedForResponse(texts),
                () -> fallback.embedForResponse(texts), "embedForResponse");
    }

    /**
     * 维度：主通道失败 → 备通道（两通道同为 bge-m3=1024，EmbeddingConfig D5 启动已断言，
     * 降级语义安全）；双挂 → 备通道异常上抛。
     *
     * V5 验收 R1 修复：原「裸委托主通道」被 Spring AI 观测链路击穿——每次 similaritySearch
     * 先经 createObservationContextBuilder 调 dimensions()（AbstractEmbeddingModel 默认实现
     * = 实时 embed 一次探测），主通道挂时异常在此抛出、根本到不了有兜底的 embed 路径，
     * 检索全废且无降级 WARN。现纳入 withFallback（主失败记 WARN 降备），并缓存结果
     * （观测链路每次检索都调，不缓存则主健康时每次多一次云端探测往返）。
     */
    @Override
    public int dimensions() {
        int cached = cachedDimensions;
        if (cached != 0) {
            return cached;
        }
        Integer resolved = withFallback(() -> primary.dimensions(), () -> fallback.dimensions(), "dimensions");
        cachedDimensions = resolved;
        return resolved;
    }

    /**
     * 统一兜底执行：主通道成功直传（零开销）；失败记 WARN 后改走备通道。
     * 备通道再失败则其异常自然上抛——双失败即整体失败，符合「双通道同挂才抛错」。
     */
    private <T> T withFallback(Supplier<T> primaryOp, Supplier<T> fallbackOp, String operation) {
        try {
            return primaryOp.get();
        } catch (RuntimeException e) {
            log.warn("embedding 主通道 {} 调用 {} 失败，降级 {}：{}",
                    primaryName, operation, fallbackName, e.getMessage());
            return fallbackOp.get();
        }
    }
}
