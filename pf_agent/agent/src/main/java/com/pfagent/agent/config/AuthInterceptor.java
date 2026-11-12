package com.pfagent.agent.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pfagent.agent.auth.JwtService;
import com.pfagent.agent.conversation.RequestIdentityResolver;
import com.pfagent.agent.conversation.UnauthorizedException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.io.IOException;
import java.util.Map;
import java.util.Optional;

/**
 * 登录鉴权拦截器（SP7 T3 / D5；F-020 实施 Spec §8.1 调整匿名语义）
 *
 * pf.auth.enabled=false（默认）：全放行，零行为变化（开源自部署无摩擦）。
 * pf.auth.enabled=true：拦截 WebConfig 注册的 /api/chat、/api/chat/feedback 与
 * /api/conversations/**（/api/auth/**、/api/health、静态资源天然不在拦截范围）：
 * - 完全没有 Authorization 头 → 标记匿名并放行（用户明确的语义调整：开启认证不再
 *   代表强制登录；IP 限频与匿名配额继续生效）；
 * - 非法、过期或结构错误的 token → 401 unauthorized，绝不静默降级为匿名；
 * - 有效 Bearer JWT → 把 username / uid 放入 request attribute
 *   （{@link #USERNAME_ATTRIBUTE} / {@link #USER_ID_ATTRIBUTE}），供会话归属使用。
 *
 * 身份解析复用 {@link RequestIdentityResolver}，与 /api/auth/me 等既有入口同一语义。
 */
@Component
public class AuthInterceptor implements HandlerInterceptor {

    /** 解析出的登录名在 request attribute 中的键 */
    public static final String USERNAME_ATTRIBUTE = "pfAuthUsername";
    /** 解析出的账号主键在 request attribute 中的键（会话 owner 使用） */
    public static final String USER_ID_ATTRIBUTE = "pfAuthUserId";

    @Autowired
    private AuthProperties authProperties;

    @Autowired
    private RequestIdentityResolver identityResolver;

    @Autowired
    private ObjectMapper objectMapper;

    @Override
    public boolean preHandle(HttpServletRequest request,
                             HttpServletResponse response,
                             Object handler) throws IOException {
        if (!authProperties.isAuthEnabled()) {
            return true;
        }
        Optional<JwtService.JwtPrincipal> principal;
        try {
            principal = identityResolver.resolve(request.getHeader("Authorization"));
        } catch (UnauthorizedException ex) {
            writeUnauthorized(response);
            return false;
        }
        principal.ifPresent(p -> {
            request.setAttribute(USERNAME_ATTRIBUTE, p.username());
            request.setAttribute(USER_ID_ATTRIBUTE, p.uid());
        });
        // 无 token 的匿名请求放行；非法 token 已在上方统一 401
        return true;
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
