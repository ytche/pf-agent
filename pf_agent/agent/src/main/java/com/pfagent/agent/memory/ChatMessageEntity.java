package com.pfagent.agent.memory;

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
 * 会话消息实体（chat_message 表）
 *
 * 只落 [user, assistant] 对（一轮两条，seq 递增）；工具调用中间态不落库，对齐现有
 * L1 记忆语义。conversationId 以普通列存（不做对象关联）；clear 由 JdbcChatMemory
 * 或 ConversationStore 显式整会话删除（外键 ON DELETE CASCADE 在生产作兜底）。
 *
 * F-020 起 assistant 行保存当轮 cited-only 过滤并重映射后的完整来源快照
 * （sources JSONB，null = 历史消息未保存）与 gap_reported 标记。
 */
@Entity
@Table(name = "chat_message")
public class ChatMessageEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "conversation_id", nullable = false, length = 36)
    private String conversationId;

    @Column(name = "seq", nullable = false)
    private Integer seq;

    @Column(name = "role", nullable = false, length = 10)
    private String role;

    // 不用 @Lob：String→VARCHAR 类型码与 V1 schema 的 TEXT 一致，validate 才过；
    // @Lob 映射 CLOB→期望 oid 列，与 TEXT 冲突启动即挂（内容长度由 schema TEXT 保证）
    @Column(name = "content", nullable = false)
    private String content;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    /** assistant 消息的当轮来源快照（JSON 数组文本）；null = 历史消息未保存来源 */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "sources")
    private String sources;

    @Column(name = "gap_reported", nullable = false)
    private boolean gapReported;

    /** JPA 无参构造 */
    protected ChatMessageEntity() {
    }

    public ChatMessageEntity(String conversationId, Integer seq, String role, String content, Instant createdAt) {
        this(conversationId, seq, role, content, createdAt, null, false);
    }

    public ChatMessageEntity(String conversationId, Integer seq, String role, String content, Instant createdAt,
                             String sources, boolean gapReported) {
        this.conversationId = conversationId;
        this.seq = seq;
        this.role = role;
        this.content = content;
        this.createdAt = createdAt;
        this.sources = sources;
        this.gapReported = gapReported;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getConversationId() {
        return conversationId;
    }

    public void setConversationId(String conversationId) {
        this.conversationId = conversationId;
    }

    public Integer getSeq() {
        return seq;
    }

    public void setSeq(Integer seq) {
        this.seq = seq;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }

    public String getSources() {
        return sources;
    }

    public void setSources(String sources) {
        this.sources = sources;
    }

    public boolean isGapReported() {
        return gapReported;
    }

    public void setGapReported(boolean gapReported) {
        this.gapReported = gapReported;
    }
}
