package com.pfagent.agent.usage;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * 一次成功返回的 DeepSeek LLM 调用（usage_record 表，F-009 设计 §3）。
 *
 * token 字段与 cost 允许为 null：usage 缺失或价目缺失时不得伪造成 0，
 * 由 usageMissing 标记调用事实。价目字段是采集时的快照，后续改价不回写历史。
 */
@Entity
@Table(name = "usage_record")
public class UsageRecordEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "request_id", nullable = false, length = 64)
    private String requestId;

    @Column(name = "call_seq", nullable = false)
    private int callSeq;

    @Column(name = "conversation_id", length = 36)
    private String conversationId;

    @Column(name = "owner_id")
    private Long ownerId;

    @Column(name = "purpose", nullable = false, length = 32)
    private String purpose;

    @Column(name = "model", nullable = false, length = 64)
    private String model;

    @Column(name = "prompt_tokens")
    private Integer promptTokens;

    @Column(name = "completion_tokens")
    private Integer completionTokens;

    @Column(name = "total_tokens")
    private Integer totalTokens;

    @Column(name = "usage_missing", nullable = false)
    private boolean usageMissing;

    @Column(name = "prompt_price_per_million", precision = 18, scale = 6)
    private BigDecimal promptPricePerMillion;

    @Column(name = "completion_price_per_million", precision = 18, scale = 6)
    private BigDecimal completionPricePerMillion;

    @Column(name = "cost", precision = 18, scale = 6)
    private BigDecimal cost;

    @Column(name = "currency", nullable = false, length = 8)
    private String currency;

    @Column(name = "duration_ms", nullable = false)
    private long durationMs;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected UsageRecordEntity() {
    }

    public UsageRecordEntity(String requestId, int callSeq, String conversationId, Long ownerId,
                             String purpose, String model, Integer promptTokens, Integer completionTokens,
                             Integer totalTokens, boolean usageMissing,
                             BigDecimal promptPricePerMillion, BigDecimal completionPricePerMillion,
                             BigDecimal cost, String currency, long durationMs, Instant createdAt) {
        this.requestId = requestId;
        this.callSeq = callSeq;
        this.conversationId = conversationId;
        this.ownerId = ownerId;
        this.purpose = purpose;
        this.model = model;
        this.promptTokens = promptTokens;
        this.completionTokens = completionTokens;
        this.totalTokens = totalTokens;
        this.usageMissing = usageMissing;
        this.promptPricePerMillion = promptPricePerMillion;
        this.completionPricePerMillion = completionPricePerMillion;
        this.cost = cost;
        this.currency = currency;
        this.durationMs = durationMs;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getRequestId() {
        return requestId;
    }

    public int getCallSeq() {
        return callSeq;
    }

    public String getConversationId() {
        return conversationId;
    }

    public Long getOwnerId() {
        return ownerId;
    }

    public String getPurpose() {
        return purpose;
    }

    public String getModel() {
        return model;
    }

    public Integer getPromptTokens() {
        return promptTokens;
    }

    public Integer getCompletionTokens() {
        return completionTokens;
    }

    public Integer getTotalTokens() {
        return totalTokens;
    }

    public boolean isUsageMissing() {
        return usageMissing;
    }

    public BigDecimal getPromptPricePerMillion() {
        return promptPricePerMillion;
    }

    public BigDecimal getCompletionPricePerMillion() {
        return completionPricePerMillion;
    }

    public BigDecimal getCost() {
        return cost;
    }

    public String getCurrency() {
        return currency;
    }

    public long getDurationMs() {
        return durationMs;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
