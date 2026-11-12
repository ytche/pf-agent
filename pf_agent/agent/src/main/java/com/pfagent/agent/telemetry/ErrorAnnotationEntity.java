package com.pfagent.agent.telemetry;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;

/**
 * 错误标注实体（error_annotation 表，F-021）
 *
 * 前端「标错」提交的一条用户反馈：question/answer/sources 是回答当时的快照，
 * 分析时无需依赖会话历史即可复现错误现场。字段对齐原 JSONL 行（FeedbackRecorder）。
 *
 * sources 用 JSONB 列存原始来源数组文本（应用层 ObjectMapper 序列化，读侧是
 * qa/annotations_report.py，Java 无读通路）；@JdbcTypeCode(SqlTypes.JSON) 让
 * Hibernate 按方言给出列类型（PG jsonb / H2 json），与 V4 迁移建的 jsonb 一致。
 */
@Entity
@Table(name = "error_annotation")
public class ErrorAnnotationEntity {

    @Id
    @Column(name = "id", nullable = false, length = 64)
    private String id;

    @Column(name = "conversation_id", length = 36)
    private String conversationId;

    @Column(name = "question")
    private String question;

    @Column(name = "answer")
    private String answer;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "sources")
    private String sources;

    @Column(name = "error_type", length = 32)
    private String errorType;

    @Column(name = "correction")
    private String correction;

    @Column(name = "comment")
    private String comment;

    /** 闭环跟踪状态，写入时固定「待分析」（与原 JSONL 行为一致） */
    @Column(name = "resolution", nullable = false, length = 32)
    private String resolution;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    /** JPA 无参构造 */
    protected ErrorAnnotationEntity() {
    }

    public ErrorAnnotationEntity(String id, String conversationId, String question, String answer,
                                 String sources, String errorType, String correction, String comment,
                                 Instant createdAt) {
        this.id = id;
        this.conversationId = conversationId;
        this.question = question;
        this.answer = answer;
        this.sources = sources;
        this.errorType = errorType;
        this.correction = correction;
        this.comment = comment;
        this.resolution = "待分析";
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public String getConversationId() {
        return conversationId;
    }

    public String getQuestion() {
        return question;
    }

    public String getAnswer() {
        return answer;
    }

    public String getSources() {
        return sources;
    }

    public String getErrorType() {
        return errorType;
    }

    public String getCorrection() {
        return correction;
    }

    public String getComment() {
        return comment;
    }

    public String getResolution() {
        return resolution;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
