package com.pfagent.agent.auth;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

/**
 * JWT 签发（SP7 T2 / D3）
 *
 * HS256 无状态签名，为将来微服务拆分铺路：用户服务签发的 JWT 各服务可独立校验
 * （届时换密钥/公钥即可过渡）。payload 只放 sub=username 与 uid，有效期默认 72h。
 *
 * 密钥经 pf.auth.jwt-secret（env PF_AUTH_JWT_SECRET）注入；默认值仅为开发兜底，
 * pf.auth.enabled=true 且仍为默认值时由 AuthProperties 打 WARN（不阻断）。
 * token 的解析/校验在 T3 随 AuthInterceptor 接线时落地。
 */
@Component
public class JwtService {

    /** 开发默认密钥（与 AuthProperties.DEFAULT_JWT_SECRET 保持一致，仅本地跑通用） */
    static final String DEFAULT_JWT_SECRET = "pf-agent-dev-jwt-secret-change-me";

    @Value("${pf.auth.jwt-secret:" + DEFAULT_JWT_SECRET + "}")
    private String jwtSecret;

    @Value("${pf.auth.token-ttl-hours:72}")
    private long tokenTtlHours;

    /** 签发登录态 JWT：sub=username，claim uid=用户主键，HS256 签名 */
    public String issueToken(UserAccount user) {
        Instant now = Instant.now();
        return Jwts.builder()
                .subject(user.getUsername())
                .claim("uid", user.getId())
                .issuedAt(Date.from(now))
                .expiration(Date.from(now.plus(Duration.ofHours(tokenTtlHours))))
                .signWith(secretKey())
                .compact();
    }

    /**
     * 解析并校验 JWT（签名 + 有效期），提取登录身份。
     *
     * 签名校验失败、token 过期或结构非法时抛 {@link io.jsonwebtoken.JwtException}，
     * 由调用方（AuthInterceptor / AuthController）统一转 401。
     */
    public JwtPrincipal parseToken(String token) {
        Claims claims = Jwts.parser()
                .verifyWith(secretKey())
                .build()
                .parseSignedClaims(token)
                .getPayload();
        return new JwtPrincipal(claims.getSubject(), claims.get("uid", Long.class));
    }

    /** 解析出的登录身份：username（sub）+ 用户主键（uid claim） */
    public record JwtPrincipal(String username, Long uid) {
    }

    private SecretKey secretKey() {
        return Keys.hmacShaKeyFor(jwtSecret.getBytes(StandardCharsets.UTF_8));
    }
}
