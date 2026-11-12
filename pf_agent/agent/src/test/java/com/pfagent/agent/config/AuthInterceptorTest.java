package com.pfagent.agent.config;

import com.pfagent.agent.auth.JwtService;
import com.pfagent.agent.conversation.RequestIdentityResolver;
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
import org.springframework.test.util.ReflectionTestUtils;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * AuthInterceptor 单元测试（SP7 T3 / D5）
 *
 * 覆盖鉴权开关两态：
 *  - pf.auth.enabled=false（默认）：无 token 也全放行，不触达 JwtService（零行为变化）
 *  - pf.auth.enabled=true：完全没有 Authorization 头 → 匿名放行（F-020 语义调整）；
 *    非 Bearer / 伪造 / 过期 token → 401 + {error:"unauthorized"}，不得静默降级为匿名；
 *    有效 token → 放行并写入 username / uid request attribute
 *
 * /api/auth/**、/api/health、静态资源的豁免由 WebConfig 的路径注册保证
 * （只注册 /api/chat、/api/chat/feedback），不在拦截器内重复判断。
 */
@ExtendWith(MockitoExtension.class)
class AuthInterceptorTest {

    private static final String TEST_SECRET = "auth-interceptor-test-jwt-secret-0123456789";

    @Mock
    private AuthProperties authProperties;

    @Mock
    private HttpServletRequest request;

    @Mock
    private HttpServletResponse response;

    @InjectMocks
    private AuthInterceptor interceptor;

    private final StringWriter responseBody = new StringWriter();

    @BeforeEach
    void setUp() throws Exception {
        JwtService jwtService = new JwtService();
        ReflectionTestUtils.setField(jwtService, "jwtSecret", TEST_SECRET);
        ReflectionTestUtils.setField(jwtService, "tokenTtlHours", 72L);
        RequestIdentityResolver resolver = new RequestIdentityResolver();
        ReflectionTestUtils.setField(resolver, "jwtService", jwtService);
        ReflectionTestUtils.setField(interceptor, "identityResolver", resolver);
        ReflectionTestUtils.setField(interceptor, "objectMapper", new com.fasterxml.jackson.databind.ObjectMapper());
        // lenient：只有写 401 的失败路径才用到 writer，放行路径用不到（严格校验会报 unnecessary stubbing）
        lenient().when(response.getWriter()).thenReturn(new PrintWriter(responseBody));
    }

    /** 开关关闭（默认）：无 token 直接放行，不写 401、不写 attribute（现状不变） */
    @Test
    void disabledAuthAllowsRequestWithoutToken() throws Exception {
        when(authProperties.isAuthEnabled()).thenReturn(false);

        boolean allowed = interceptor.preHandle(request, response, new Object());

        assertThat(allowed).isTrue();
        verify(response, never()).setStatus(org.mockito.ArgumentMatchers.anyInt());
        verify(request, never()).setAttribute(org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.any());
    }

    /** 开关开启：完全没有 Authorization 头 → 匿名放行（不再强制登录） */
    @Test
    void enabledAuthAllowsMissingHeaderAsAnonymous() throws Exception {
        when(authProperties.isAuthEnabled()).thenReturn(true);
        when(request.getHeader("Authorization")).thenReturn(null);

        boolean allowed = interceptor.preHandle(request, response, new Object());

        assertThat(allowed).isTrue();
        verify(request, never()).setAttribute(org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.any());
    }

    /** 开关开启：空白 Authorization 头按匿名处理 */
    @Test
    void enabledAuthAllowsBlankHeaderAsAnonymous() throws Exception {
        when(authProperties.isAuthEnabled()).thenReturn(true);
        when(request.getHeader("Authorization")).thenReturn("  ");

        boolean allowed = interceptor.preHandle(request, response, new Object());

        assertThat(allowed).isTrue();
    }

    /** 开关开启：非 Bearer 头 → 401 */
    @Test
    void enabledAuthRejectsNonBearerScheme() throws Exception {
        when(authProperties.isAuthEnabled()).thenReturn(true);
        when(request.getHeader("Authorization")).thenReturn("Basic dXNlcjpwYXNz");

        boolean allowed = interceptor.preHandle(request, response, new Object());

        assertThat(allowed).isFalse();
        assertThat(responseBody.toString()).contains("unauthorized");
    }

    /** 开关开启：伪造 token（签名不匹配）→ 401 */
    @Test
    void enabledAuthRejectsForgedToken() throws Exception {
        when(authProperties.isAuthEnabled()).thenReturn(true);
        String forged = signWith("attacker-forged-token-secret-00000000000", "mallory", 1L,
                Instant.now(), Duration.ofHours(1));
        when(request.getHeader("Authorization")).thenReturn("Bearer " + forged);

        boolean allowed = interceptor.preHandle(request, response, new Object());

        assertThat(allowed).isFalse();
        assertThat(responseBody.toString()).contains("unauthorized");
        verify(request, never()).setAttribute(org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.any());
    }

    /** 开关开启：过期 token → 401 */
    @Test
    void enabledAuthRejectsExpiredToken() throws Exception {
        when(authProperties.isAuthEnabled()).thenReturn(true);
        String expired = signWith(TEST_SECRET, "alice", 1L,
                Instant.now().minus(Duration.ofHours(2)), Duration.ofHours(1));
        when(request.getHeader("Authorization")).thenReturn("Bearer " + expired);

        boolean allowed = interceptor.preHandle(request, response, new Object());

        assertThat(allowed).isFalse();
        assertThat(responseBody.toString()).contains("unauthorized");
    }

    /** 开关开启：有效 token → 放行并写入 username request attribute（ChatService 暂不消费） */
    @Test
    void enabledAuthAllowsValidTokenAndSetsAttribute() throws Exception {
        when(authProperties.isAuthEnabled()).thenReturn(true);
        String valid = signWith(TEST_SECRET, "alice", 1L, Instant.now(), Duration.ofHours(72));
        when(request.getHeader("Authorization")).thenReturn("Bearer " + valid);

        boolean allowed = interceptor.preHandle(request, response, new Object());

        assertThat(allowed).isTrue();
        verify(request).setAttribute(AuthInterceptor.USERNAME_ATTRIBUTE, "alice");
        verify(request).setAttribute(AuthInterceptor.USER_ID_ATTRIBUTE, 1L);
    }

    /** 用指定密钥/有效期签一个测试 token */
    private static String signWith(String secret, String username, Long uid,
                                   Instant issuedAt, Duration ttl) {
        return Jwts.builder()
                .subject(username)
                .claim("uid", uid)
                .issuedAt(Date.from(issuedAt))
                .expiration(Date.from(issuedAt.plus(ttl)))
                .signWith(Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8)))
                .compact();
    }
}
