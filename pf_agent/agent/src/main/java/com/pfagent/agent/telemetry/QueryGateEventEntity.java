package com.pfagent.agent.telemetry;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;

/**
 * 查询门禁事件实体（query_gate_event 表，F-026 设计 §8）
 *
 * 工具层每次 BLOCKED / ALLOWED 判定一行：conversationId / question 来自
 * ToolCallTracker 的请求上下文，queryJson 是当次查询参数的 JSON（业务条件 +
 * offset/limit/sort），不保存回答正文或来源快照。
 *
 * eventType/reason 直接以落库口径字符串保存（BLOCKED / ALLOWED、
 * no_conditions / book_only），与 {@link QueryGateEventService} 的枚举名和
 * {@code Reason.value()} 对应，避免枚举名与设计文档字段值（下划线形）不一致。
 *
 * query_json 用 JSONB：与 V6 迁移一致；@JdbcTypeCode(SqlTypes.JSON) 让 Hibernate
 * 按方言给出列类型（PG jsonb / H2 json），同 ErrorAnnotationEntity.sources。
 */
@Entity
@Table(name = "query_gate_event")
public class QueryGateEventEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "conversation_id", length = 36)
    private String conversationId;

    @Column(name = "question")
    private String question;

    @Column(name = "tool_name", nullable = false, length = 64)
    private String toolName;

    @Column(name = "module", length = 32)
    private String module;

    @Column(name = "event_type", nullable = false, length = 16)
    private String eventType;

    @Column(name = "reason", nullable = false, length = 32)
    private String reason;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "query_json")
    private String queryJson;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    /** JPA 无参构造 */
    protected QueryGateEventEntity() {
    }

    public QueryGateEventEntity(String conversationId, String question, String toolName, String module,
                                String eventType, String reason, String queryJson, Instant createdAt) {
        this.conversationId = conversationId;
        this.question = question;
        this.toolName = toolName;
        this.module = module;
        this.eventType = eventType;
        this.reason = reason;
        this.queryJson = queryJson;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getConversationId() {
        return conversationId;
    }

    public String getQuestion() {
        return question;
    }

    public String getToolName() {
        return toolName;
    }

    public String getModule() {
        return module;
    }

    public String getEventType() {
        return eventType;
    }

    public String getReason() {
        return reason;
    }

    public String getQueryJson() {
        return queryJson;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
