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
 * 累计轮数（F-005 只删旧消息不回写它）；generation_attempts 为 F-020 匿名配额依据，
 * 累计普通问答与重新生成的模型调用尝试（失败也计数），不等于对话轮数。
 *
 * F-020 起 owner_user_id 为空表示匿名会话（凭 UUID 能力访问），认领后写入账号 ID；
 * 删号由 V7 外键 ON DELETE SET NULL 转为匿名，不删除会话。
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

    @Column(name = "title", length = 200)
    private String title;

    @Column(name = "pinned", nullable = false)
    private boolean pinned;

    @Column(name = "owner_user_id")
    private Long ownerUserId;

    @Column(name = "generation_attempts", nullable = false)
    private Integer generationAttempts;

    /** JPA 无参构造 */
    protected ChatConversationEntity() {
    }

    /** 新建会话（created_at 与 last_active_at 同为当前时刻，各计数列初始 0） */
    public ChatConversationEntity(String id, Instant createdAt) {
        this(id, createdAt, null);
    }

    /** 新建会话并可指定账号归属（登录用户新建问答自动写入 owner） */
    public ChatConversationEntity(String id, Instant createdAt, Long ownerUserId) {
        this.id = id;
        this.createdAt = createdAt;
        this.lastActiveAt = createdAt;
        this.messageRounds = 0;
        this.totalRounds = 0;
        this.generationAttempts = 0;
        this.pinned = false;
        this.ownerUserId = ownerUserId;
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

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public boolean isPinned() {
        return pinned;
    }

    public void setPinned(boolean pinned) {
        this.pinned = pinned;
    }

    public Long getOwnerUserId() {
        return ownerUserId;
    }

    public void setOwnerUserId(Long ownerUserId) {
        this.ownerUserId = ownerUserId;
    }

    public Integer getGenerationAttempts() {
        return generationAttempts;
    }

    public void setGenerationAttempts(Integer generationAttempts) {
        this.generationAttempts = generationAttempts;
    }
}
