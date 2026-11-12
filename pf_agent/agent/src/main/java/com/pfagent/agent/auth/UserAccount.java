package com.pfagent.agent.auth;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;

/**
 * 用户实体（user_account 表，SP7 T2 / Flyway V3；F-023 增加 role 列，Flyway V5）
 *
 * 最小用户域：登录名归一后入库（应用层去首尾空白 + 小写，PG UNIQUE 本身大小写敏感），
 * 密码只存 BCrypt 哈希；nickname 可空，展示层缺省兜底为 username。
 * role 区分普通用户（user，默认）与管理员（admin），由 F-023 admin 后台消费。
 */
@Entity
@Table(name = "user_account")
public class UserAccount {

    /** 普通用户角色（默认） */
    public static final String ROLE_USER = "user";
    /** 管理员角色 */
    public static final String ROLE_ADMIN = "admin";

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "username", nullable = false, unique = true, length = 64)
    private String username;

    @Column(name = "password_hash", nullable = false, length = 72)
    private String passwordHash;

    @Column(name = "nickname", length = 64)
    private String nickname;

    @Column(name = "role", nullable = false, length = 16)
    private String role = ROLE_USER;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "last_login_at")
    private Instant lastLoginAt;

    /** JPA 无参构造 */
    protected UserAccount() {
    }

    public UserAccount(String username, String passwordHash, Instant createdAt) {
        this(username, passwordHash, createdAt, ROLE_USER);
    }

    public UserAccount(String username, String passwordHash, Instant createdAt, String role) {
        this.username = username;
        this.passwordHash = passwordHash;
        this.createdAt = createdAt;
        this.role = role == null ? ROLE_USER : role;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public void setPasswordHash(String passwordHash) {
        this.passwordHash = passwordHash;
    }

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role == null ? ROLE_USER : role;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }

    public Instant getLastLoginAt() {
        return lastLoginAt;
    }

    public void setLastLoginAt(Instant lastLoginAt) {
        this.lastLoginAt = lastLoginAt;
    }
}
