package com.pfagent.agent.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pfagent.agent.auth.JwtService;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.io.IOException;
import java.util.Map;

/**
 * 登录鉴权拦截器（SP7 T3 / D5）
 *
 * pf.auth.enabled=false（默认）：全放行，零行为变化（开源自部署无摩擦）。
 * pf.auth.enabled=true：仅拦截 WebConfig 注册的 /api/chat、/api/chat/feedback
 * （/api/auth/**、/api/health、静态资源天然不在拦截范围），校验
 * {@code Authorization: Bearer <jwt>}：签名/有效期校验失败或无头一律 401 +
 * {error: "unauthorized"}；成功则把 username 放入 request attribute
 * （{@link #USERNAME_ATTRIBUTE}），供将来按用户配额/会话隔离消费——本轮 ChatService
 * 不消费，不改变现有会话行为（D5）。
 */
@Component
public class AuthInterceptor implements HandlerInterceptor {

    /** 解析出的登录名在 request attribute 中的键（ChatService 暂不消费，留给按用户维度扩展） */
    public static final String USERNAME_ATTRIBUTE = "pfAuthUsername";

    @Autowired
    private AuthProperties authProperties;

    @Autowired
    private JwtService jwtService;

    @Autowired
    private ObjectMapper objectMapper;

    @Override
    public boolean preHandle(HttpServletRequest request,
                             HttpServletResponse response,
                             Object handler) throws IOException {
        if (!authProperties.isAuthEnabled()) {
            return true;
        }
        JwtService.JwtPrincipal principal = resolvePrincipal(request.getHeader("Authorization"));
        if (principal == null) {
            writeUnauthorized(response);
            return false;
        }
        request.setAttribute(USERNAME_ATTRIBUTE, principal.username());
        return true;
    }

    /** 从 Authorization: Bearer <jwt> 解析身份；缺失/伪造/过期/结构非法一律返回 null */
    private JwtService.JwtPrincipal resolvePrincipal(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            return null;
        }
        try {
            return jwtService.parseToken(authorization.substring("Bearer ".length()).trim());
        } catch (JwtException | IllegalArgumentException ex) {
            return null; // 统一按无效凭证处理
        }
    }

    /** 写 401 + JSON 错误体（D5：与匿名配额 429 quota_exceeded 结构区分，前端分别引导） */
    private void writeUnauthorized(HttpServletResponse response) throws IOException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        objectMapper.writeValue(response.getWriter(), Map.of(
                "error", "unauthorized",
                "message", "缺少或无效的身份凭证，请重新登录"));
    }
}
