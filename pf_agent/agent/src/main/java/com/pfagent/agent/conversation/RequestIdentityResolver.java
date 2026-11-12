package com.pfagent.agent.conversation;

import com.pfagent.agent.auth.JwtService;
import io.jsonwebtoken.JwtException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.util.Optional;

/**
 * 共享认证身份解析（F-020 实施 Spec §8.1）
 *
 * 供 AuthInterceptor 与需要身份的业务接口复用同一套语义：
 * - 完全没有 Authorization 头 → 匿名（返回 empty），由调用方按匿名能力处理；
 * - Bearer JWT 有效 → 当前用户；
 * - 非法、过期、结构错误或非 Bearer 头 → 抛 {@link UnauthorizedException}（401），
 *   绝不静默降级为匿名。
 */
@Component
public class RequestIdentityResolver {

    private static final String BEARER_PREFIX = "Bearer ";

    @Autowired
    private JwtService jwtService;

    /** 解析请求身份；无 Authorization 头返回 empty（匿名） */
    public Optional<JwtService.JwtPrincipal> resolve(String authorization) {
        if (authorization == null || authorization.isBlank()) {
            return Optional.empty();
        }
        if (!authorization.startsWith(BEARER_PREFIX)) {
            throw new UnauthorizedException();
        }
        String token = authorization.substring(BEARER_PREFIX.length()).trim();
        if (token.isEmpty()) {
            throw new UnauthorizedException();
        }
        try {
            return Optional.of(jwtService.parseToken(token));
        } catch (JwtException | IllegalArgumentException ex) {
            throw new UnauthorizedException();
        }
    }
}
