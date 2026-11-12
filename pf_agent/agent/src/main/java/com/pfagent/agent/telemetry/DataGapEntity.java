package com.pfagent.agent.telemetry;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;

/**
 * 数据缺口实体（data_gap 表，F-021）
 *
 * reportDataGap 工具上报的一条检索无结果记录，字段对齐原 JSONL 行（DataGapRecorder）。
 * 原 JSONL 行没有 id，表侧用 BIGSERIAL 合成代理键；dedup_key 是内容 + 时间戳的
 * SHA-256，用于「迁移导入可重复执行不产生重复」与写库幂等（同秒同内容视为同一缺口）。
 */
@Entity
@Table(name = "data_gap")
public class DataGapEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "dedup_key", nullable = false, length = 64)
    private String dedupKey;

    @Column(name = "question", nullable = false)
    private String question;

    @Column(name = "attempted_filters")
    private String attemptedFilters;

    @Column(name = "reason")
    private String reason;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    /** JPA 无参构造 */
    protected DataGapEntity() {
    }

    public DataGapEntity(String dedupKey, String question, String attemptedFilters, String reason,
                         Instant createdAt) {
        this.dedupKey = dedupKey;
        this.question = question;
        this.attemptedFilters = attemptedFilters;
        this.reason = reason;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getDedupKey() {
        return dedupKey;
    }

    public String getQuestion() {
        return question;
    }

    public String getAttemptedFilters() {
        return attemptedFilters;
    }

    public String getReason() {
        return reason;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
