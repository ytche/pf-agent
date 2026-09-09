package com.pfagent.agent.memory;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;

/**
 * 会话实体（chat_conversation 表）
 *
 * 一次问答会话一行；id 即后端生成的 conversationId（UUID 字符串）。
 * message_rounds 为 F-005 保留轮数（会被裁剪钉在上限）；total_rounds 为会话生命周期
 * 累计轮数（F-005 只删旧消息不回写它），是 SP2 匿名每会话配额（F-011）的真实依据。
 */
@Entity
@Table(name = "chat_conversation")
public class ChatConversationEntity {

    @Id
    @Column(name = "id", nullable = false, length = 36)
    private String id;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "last_active_at", nullable = false)
    private Instant lastActiveAt;

    @Column(name = "message_rounds", nullable = false)
    private Integer messageRounds;

    @Column(name = "total_rounds", nullable = false)
    private Integer totalRounds;

    /** JPA 无参构造 */
    protected ChatConversationEntity() {
    }

    /** 新建会话（created_at 与 last_active_at 同为当前时刻，轮数列初始 0） */
    public ChatConversationEntity(String id, Instant createdAt) {
        this.id = id;
        this.createdAt = createdAt;
        this.lastActiveAt = createdAt;
        this.messageRounds = 0;
        this.totalRounds = 0;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }

    public Instant getLastActiveAt() {
        return lastActiveAt;
    }

    public void setLastActiveAt(Instant lastActiveAt) {
        this.lastActiveAt = lastActiveAt;
    }

    public Integer getMessageRounds() {
        return messageRounds;
    }

    public void setMessageRounds(Integer messageRounds) {
        this.messageRounds = messageRounds;
    }

    public Integer getTotalRounds() {
        return totalRounds;
    }

    public void setTotalRounds(Integer totalRounds) {
        this.totalRounds = totalRounds;
    }
}
