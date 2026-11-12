package com.pfagent.agent.admin;

import com.pfagent.agent.auth.JwtService;
import com.pfagent.agent.config.AuthProperties;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.test.util.ReflectionTestUtils;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * AdminInterceptor 单元测试（F-023）
 *
 * 覆盖 /api/admin/** 的四道守卫：
 *  - pf.auth.enabled=false → 403 admin_disabled（显式拒绝，绝不裸奔）
 *  - 无 / 非法 token → 401 unauthorized
 *  - 数据层缺席（memory 模式）→ 503 admin_unavailable
 *  - 已登录但非 admin → 403 forbidden；admin → 放行并写 username attribute
 */
@ExtendWith(MockitoExtension.class)
class AdminInterceptorTest {

    private static final String TEST_SECRET = "admin-interceptor-test-jwt-secret-0123456789";

    @Mock
    private AuthProperties authProperties;

    @Mock
    private ObjectProvider<AdminService> adminServiceProvider;

    @Mock
    private AdminService adminService;

    @Mock
    private HttpServletRequest request;

    @Mock
    private HttpServletResponse response;

    @InjectMocks
    private AdminInterceptor interceptor;

    private final StringWriter responseBody = new StringWriter();

    @BeforeEach
    void setUp() throws Exception {
        JwtService jwtService = new JwtService();
        ReflectionTestUtils.setField(jwtService, "jwtSecret", TEST_SECRET);
        ReflectionTestUtils.setField(jwtService, "tokenTtlHours", 72L);
        ReflectionTestUtils.setField(interceptor, "jwtService", jwtService);
        ReflectionTestUtils.setField(interceptor, "objectMapper", new com.fasterxml.jackson.databind.ObjectMapper());
        lenient().when(response.getWriter()).thenReturn(new PrintWriter(responseBody));
    }

    /** pf.auth.enabled=false：admin 路由一律 403 admin_disabled，不解析 token */
    @Test
    void disabledAuthRejectsAdminRoute() throws Exception {
        when(authProperties.isAuthEnabled()).thenReturn(false);

        boolean allowed = interceptor.preHandle(request, response, new Object());

        assertThat(allowed).isFalse();
        verify(response).setStatus(HttpServletResponse.SC_FORBIDDEN);
        assertThat(responseBody.toString()).contains("\"error\":\"admin_disabled\"");
        verify(request, never()).setAttribute(anyString(), any());
    }

    /** 开启鉴权但无 Authorization 头 → 401 unauthorized */
    @Test
    void missingHeaderRejectedWith401() throws Exception {
        when(authProperties.isAuthEnabled()).thenReturn(true);
        when(request.getHeader("Authorization")).thenReturn(null);

        boolean allowed = interceptor.preHandle(request, response, new Object());

        assertThat(allowed).isFalse();
        verify(response).setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        assertThat(responseBody.toString()).contains("unauthorized");
    }

    /** 数据层缺席（memory 模式）：有效 token 也 503 admin_unavailable */
    @Test
    void absentServiceRejectedWith503() throws Exception {
        when(authProperties.isAuthEnabled()).thenReturn(true);
        when(request.getHeader("Authorization")).thenReturn("Bearer " + validToken("alice"));
        when(adminServiceProvider.getIfAvailable()).thenReturn(null);

        boolean allowed = interceptor.preHandle(request, response, new Object());

        assertThat(allowed).isFalse();
        verify(response).setStatus(HttpServletResponse.SC_SERVICE_UNAVAILABLE);
        assertThat(responseBody.toString()).contains("admin_unavailable");
    }

    /** 已登录但非 admin → 403 forbidden */
    @Test
    void nonAdminRejectedWith403() throws Exception {
        when(authProperties.isAuthEnabled()).thenReturn(true);
        when(request.getHeader("Authorization")).thenReturn("Bearer " + validToken("joe"));
        when(adminServiceProvider.getIfAvailable()).thenReturn(adminService);
        when(adminService.isAdmin("joe")).thenReturn(false);

        boolean allowed = interceptor.preHandle(request, response, new Object());

        assertThat(allowed).isFalse();
        verify(response).setStatus(HttpServletResponse.SC_FORBIDDEN);
        assertThat(responseBody.toString()).contains("\"error\":\"forbidden\"");
        verify(request, never()).setAttribute(anyString(), any());
    }

    /** admin → 放行并写入 username attribute */
    @Test
    void adminAllowedAndAttributeSet() throws Exception {
        when(authProperties.isAuthEnabled()).thenReturn(true);
        when(request.getHeader("Authorization")).thenReturn("Bearer " + validToken("boss"));
        when(adminServiceProvider.getIfAvailable()).thenReturn(adminService);
        when(adminService.isAdmin("boss")).thenReturn(true);

        boolean allowed = interceptor.preHandle(request, response, new Object());

        assertThat(allowed).isTrue();
        verify(request).setAttribute(AdminInterceptor.ADMIN_USERNAME_ATTRIBUTE, "boss");
        verify(response, never()).setStatus(anyInt());
    }

    /** 伪造 token（签名不匹配）→ 401 */
    @Test
    void forgedTokenRejectedWith401() throws Exception {
        when(authProperties.isAuthEnabled()).thenReturn(true);
        String forged = Jwts.builder().subject("mallory").claim("uid", 1L)
                .issuedAt(Date.from(Instant.now())).expiration(Date.from(Instant.now().plus(Duration.ofHours(1))))
                .signWith(Keys.hmacShaKeyFor("attacker-forged-secret-000000000000000".getBytes(StandardCharsets.UTF_8)))
                .compact();
        when(request.getHeader("Authorization")).thenReturn("Bearer " + forged);

        boolean allowed = interceptor.preHandle(request, response, new Object());

        assertThat(allowed).isFalse();
        assertThat(responseBody.toString()).contains("unauthorized");
    }

    private static String validToken(String username) {
        return Jwts.builder().subject(username).claim("uid", 1L)
                .issuedAt(Date.from(Instant.now())).expiration(Date.from(Instant.now().plus(Duration.ofHours(72))))
                .signWith(Keys.hmacShaKeyFor(TEST_SECRET.getBytes(StandardCharsets.UTF_8)))
                .compact();
    }
}
