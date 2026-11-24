package com.pfagent.agent.usage;

import com.pfagent.agent.telemetry.UsageRecorder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.metadata.ChatResponseMetadata;
import org.springframework.ai.chat.metadata.Usage;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

/**
 * JDBC 用量采集（usage_record 表，F-009 设计 §4）。
 *
 * 每次成功返回的 LLM 调用写一行：request_id 来自 {@link UsageRequestContext}，
 * call_seq 在请求内递增；token 取 {@code ChatResponse.metadata.usage}，缺失时保持 null
 * 并置 usage_missing=true，绝不伪造成 0。价目由配置提供并随行保存快照，后续改价
 * 不回写历史；缺价目时 cost=null。
 *
 * 写库失败只记 WARN，不向调用方抛出：用量是遥测，不得阻断问答主链路。
 * 用 REQUIRES_NEW 独立事务，避免与会话主数据事务互相拖累。
 *
 * 仅在 pf.chat.memory=jdbc 时装配；memory 模式由 {@link NoopUsageRecorder} 占位。
 */
@Component
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
public class JdbcUsageRecorder implements UsageRecorder {

    private static final Logger log = LoggerFactory.getLogger(JdbcUsageRecorder.class);

    private static final BigDecimal MILLION = BigDecimal.valueOf(1_000_000);
    private static final MathContext COST_CONTEXT = new MathContext(18, RoundingMode.HALF_UP);
    private static final int COST_SCALE = 6;

    private final UsageRecordRepository repository;
    private final UsageRequestContext context;
    private final TransactionTemplate transactionTemplate;
    private final BigDecimal promptPrice;
    private final BigDecimal completionPrice;
    private final String currency;

    public JdbcUsageRecorder(UsageRecordRepository repository,
                             UsageRequestContext context,
                             PlatformTransactionManager transactionManager,
                             @Value("${pf.usage.prompt-price-per-million:2.0}") String promptPrice,
                             @Value("${pf.usage.completion-price-per-million:8.0}") String completionPrice,
                             @Value("${pf.usage.currency:CNY}") String currency) {
        this.repository = repository;
        this.context = context;
        this.transactionTemplate = new TransactionTemplate(transactionManager);
        this.transactionTemplate.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        this.promptPrice = parsePrice(promptPrice);
        this.completionPrice = parsePrice(completionPrice);
        this.currency = currency == null || currency.isBlank() ? "CNY" : currency.trim();
        log.info("用量价目已生效：输入 {}/百万 token，输出 {}/百万 token，币种 {}",
                this.promptPrice == null ? "未配置" : this.promptPrice.toPlainString(),
                this.completionPrice == null ? "未配置" : this.completionPrice.toPlainString(),
                this.currency);
    }

    @Override
    public void record(String purpose, String model, ChatResponse response, long durationMs) {
        try {
            UsageRequestContext.CallScope scope = context.nextCall()
                    .orElseGet(() -> {
                        // 未 begin 的兜底调用：仍记录事实，但 WARN 以便发现漏建请求上下文
                        log.warn("用量采集缺少请求上下文（purpose={}），按单次调用兜底记录，"
                                + "会话/所有者/请求分组不可用", purpose);
                        return new UsageRequestContext.CallScope(
                                UUID.randomUUID().toString(), 1, null, null);
                    });

            Usage usage = usageOf(response);
            Integer promptTokens = usage == null ? null : usage.getPromptTokens();
            Integer completionTokens = usage == null ? null : usage.getCompletionTokens();
            Integer totalTokens = usage == null ? null : usage.getTotalTokens();
            boolean usageMissing = promptTokens == null && completionTokens == null && totalTokens == null;

            if (usageMissing) {
                promptTokens = null;
                completionTokens = null;
                totalTokens = null;
            }
            BigDecimal cost = usageMissing ? null : cost(promptTokens, completionTokens);

            UsageRecordEntity entity = new UsageRecordEntity(
                    scope.requestId(), scope.callSeq(), scope.conversationId(), scope.ownerId(),
                    purpose == null || purpose.isBlank() ? "agent" : purpose,
                    modelOf(response, model),
                    promptTokens, completionTokens, totalTokens, usageMissing,
                    promptPrice, completionPrice, cost, currency,
                    Math.max(durationMs, 0), Instant.now());
            transactionTemplate.executeWithoutResult(status -> repository.save(entity));
        } catch (RuntimeException e) {
            // 用量写入失败不得阻断问答；保留 WARN 供运维发现（设计 §4.6）
            log.warn("用量记录写入失败（不影响本轮问答）: {}", e.getMessage());
        }
    }

    /** ChatResponse.metadata 可能为空（测试/降级响应）：视为 usage 缺失 */
    private static Usage usageOf(ChatResponse response) {
        if (response == null) {
            return null;
        }
        ChatResponseMetadata metadata = response.getMetadata();
        if (metadata == null) {
            return null;
        }
        Usage usage = metadata.getUsage();
        // Spring AI 在无 usage 时可能返回 EmptyUsage，其 token 为 0；不得当成真实零用量
        return usage instanceof org.springframework.ai.chat.metadata.EmptyUsage ? null : usage;
    }

    /** 模型标识优先用调用方传入值（ChatService 已取实际响应模型），缺失时退回响应元数据 */
    private static String modelOf(ChatResponse response, String fallback) {
        if (fallback != null && !fallback.isBlank()) {
            return fallback;
        }
        if (response != null && response.getMetadata() != null) {
            String model = response.getMetadata().getModel();
            if (model != null && !model.isBlank()) {
                return model;
            }
        }
        return "unknown";
    }

    /** 费用 = 输入 token/百万 * 输入单价 + 输出 token/百万 * 输出单价；缺价目返回 null */
    private BigDecimal cost(Integer promptTokens, Integer completionTokens) {
        if (promptPrice == null || completionPrice == null) {
            return null;
        }
        BigDecimal prompt = BigDecimal.valueOf(promptTokens == null ? 0 : promptTokens)
                .multiply(promptPrice).divide(MILLION, COST_CONTEXT);
        BigDecimal completion = BigDecimal.valueOf(completionTokens == null ? 0 : completionTokens)
                .multiply(completionPrice).divide(MILLION, COST_CONTEXT);
        return prompt.add(completion).setScale(COST_SCALE, RoundingMode.HALF_UP);
    }

    /** 空白/null 视为未配置价目（cost=null），不把 0 当免费 */
    private static BigDecimal parsePrice(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return new BigDecimal(raw.trim());
        } catch (NumberFormatException e) {
            log.warn("价目配置无法解析为数字，按未配置处理: {}", raw);
            return null;
        }
    }

    /** 供测试/诊断读取生效价目 */
    public Optional<BigDecimal> promptPrice() {
        return Optional.ofNullable(promptPrice);
    }

    public Optional<BigDecimal> completionPrice() {
        return Optional.ofNullable(completionPrice);
    }
}
