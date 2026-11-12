package com.pfagent.agent.admin;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pfagent.agent.auth.JwtService;
import com.pfagent.agent.config.AuthProperties;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import java.io.IOException;
import java.util.Map;

/**
 * 管理后台路由守卫（F-023），注册于 {@code /api/admin/**}（见 {@link AdminWebConfig}）
 *
 * 守卫顺序（任一不满足即拒绝，均不进入 controller）：
 * 1. pf.auth.enabled=false → 403 admin_disabled：管理后台随鉴权体系开关，关闭鉴权时
 *    必须显式拒绝 admin 路由，绝不裸奔（裸奔 = 任何人可增删用户）。
 * 2. 无 / 非法 / 过期 JWT → 401 unauthorized。
 * 3. 数据层缺席（memory 模式无用户表）→ 503 admin_unavailable。
 * 4. 已登录但非 admin（role!=admin）→ 403 forbidden。
 * 通过则把管理员登录名写入 request attribute（{@link #ADMIN_USERNAME_ATTRIBUTE}），
 * 供 controller 执行「改自己的密码」等操作。
 *
 * 与 AuthInterceptor 独立：/api/admin/** 不在鉴权拦截器路径内（其只拦 /api/chat*），
 * 管理后台的身份校验完全由本拦截器负责。
 */
@Component
public class AdminInterceptor implements HandlerInterceptor {

    /** 解析出的管理员登录名在 request attribute 中的键 */
    public static final String ADMIN_USERNAME_ATTRIBUTE = "pfAdminUsername";

    @Autowired
    private AuthProperties authProperties;

    @Autowired
    private JwtService jwtService;

    @Autowired
    private ObjectProvider<AdminService> adminServiceProvider;

    @Autowired
    private ObjectMapper objectMapper;

    @Override
    public boolean preHandle(HttpServletRequest request,
                             HttpServletResponse response,
                             Object handler) throws IOException {
        if (!authProperties.isAuthEnabled()) {
            writeError(response, HttpServletResponse.SC_FORBIDDEN, "admin_disabled",
                    "管理后台未启用：pf.auth.enabled=false 时 admin 路由一律拒绝");
            return false;
        }
        JwtService.JwtPrincipal principal = resolvePrincipal(request.getHeader("Authorization"));
        if (principal == null) {
            writeError(response, HttpServletResponse.SC_UNAUTHORIZED, "unauthorized",
                    "缺少或无效的身份凭证，请重新登录");
            return false;
        }
        AdminService adminService = adminServiceProvider.getIfAvailable();
        if (adminService == null) {
            writeError(response, HttpServletResponse.SC_SERVICE_UNAVAILABLE, "admin_unavailable",
                    "管理后台不可用：pf.chat.memory=memory 时无用户表");
            return false;
        }
        if (!adminService.isAdmin(principal.username())) {
            writeError(response, HttpServletResponse.SC_FORBIDDEN, "forbidden", "需要管理员权限");
            return false;
        }
        request.setAttribute(ADMIN_USERNAME_ATTRIBUTE, principal.username());
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
            return null;
        }
    }

    private void writeError(HttpServletResponse response, int status, String error, String message)
            throws IOException {
        response.setStatus(status);
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        objectMapper.writeValue(response.getWriter(), Map.of("error", error, "message", message));
    }
}
