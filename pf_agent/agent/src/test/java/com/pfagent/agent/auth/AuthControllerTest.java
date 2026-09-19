package com.pfagent.agent.auth;

import com.pfagent.agent.config.AuthProperties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.time.Instant;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * AuthController 单元测试（SP7 T3 / D4 + D6）
 *
 * 覆盖 /api/auth/** 四个端点的请求→响应与错误码语义映射：
 *  - register/login：200 返回 token；username_taken→409、invalid_credentials→401、
 *    invalid_request→400，错误体统一 {error: ...}
 *  - me：带有效 token 返回用户信息；无头/非法 token 401 unauthorized（不触达 service）
 *  - status：两态 {enabled: true/false}（D6 前端探测）
 */
@ExtendWith(MockitoExtension.class)
class AuthControllerTest {

    @Mock
    private AuthProperties authProperties;

    @Mock
    private JwtService jwtService;

    @Mock
    private ObjectProvider<AuthService> authServiceProvider;

    @Mock
    private AuthService authService;

    @InjectMocks
    private AuthController controller;

    /** register 成功：透传参数，200 返回签发结果 */
    @Test
    void registerDelegatesAndReturnsToken() {
        AuthService.AuthResult result = new AuthService.AuthResult("jwt-1", 7L, "alice", "alice");
        when(authServiceProvider.getIfAvailable()).thenReturn(authService);
        when(authService.register(" alice ", "password123")).thenReturn(result);

        ResponseEntity<?> resp = controller.register(new AuthController.AuthBody(" alice ", "password123"));

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(resp.getBody()).isSameAs(result);
        verify(authService).register(" alice ", "password123");
    }

    /** 注册重名：service 抛 UsernameTakenException（无 MVC 派发时直接上抛，由全局 @ExceptionHandler 转 409） */
    @Test
    void registerDuplicateThrowsUsernameTaken() {
        when(authServiceProvider.getIfAvailable()).thenReturn(authService);
        when(authService.register("alice", "password123")).thenThrow(new UsernameTakenException("alice"));

        assertThatThrownBy(() -> controller.register(new AuthController.AuthBody("alice", "password123")))
                .isInstanceOf(UsernameTakenException.class);
    }

    /** 注册弱密码：service 抛 IllegalArgumentException（@ExceptionHandler 转 400 invalid_request） */
    @Test
    void registerWeakPasswordThrowsInvalidRequest() {
        when(authServiceProvider.getIfAvailable()).thenReturn(authService);
        when(authService.register("alice", "short")).thenThrow(new IllegalArgumentException("密码至少 8 位"));

        assertThatThrownBy(() -> controller.register(new AuthController.AuthBody("alice", "short")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("8");
    }

    /** login 成功：200 返回签发结果；错误凭证：service 抛 InvalidCredentialsException（@ExceptionHandler 转 401） */
    @Test
    void loginSuccessAndInvalidCredentials() {
        when(authServiceProvider.getIfAvailable()).thenReturn(authService);
        AuthService.AuthResult result = new AuthService.AuthResult("jwt-2", 9L, "bob", "bob");
        when(authService.login("bob", "password123")).thenReturn(result);

        ResponseEntity<?> ok = controller.login(new AuthController.AuthBody("bob", "password123"));
        assertThat(ok.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(ok.getBody()).isSameAs(result);

        when(authService.login("bob", "wrong-pass")).thenThrow(new InvalidCredentialsException());
        assertThatThrownBy(() -> controller.login(new AuthController.AuthBody("bob", "wrong-pass")))
                .isInstanceOf(InvalidCredentialsException.class);
    }

    /** @ExceptionHandler 语义映射（D4）：409 username_taken / 401 invalid_credentials / 400 invalid_request / 503 auth_unavailable */
    @Test
    void exceptionHandlersMapToSemanticStatusAndErrorCode() {
        ResponseEntity<?> taken = controller.handleUsernameTaken(new UsernameTakenException("alice"));
        assertThat(taken.getStatusCode()).isEqualTo(HttpStatus.CONFLICT);
        assertThat(errorCode(taken)).isEqualTo("username_taken");

        ResponseEntity<?> badCreds = controller.handleInvalidCredentials(new InvalidCredentialsException());
        assertThat(badCreds.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(errorCode(badCreds)).isEqualTo("invalid_credentials");

        ResponseEntity<?> invalid = controller.handleInvalidRequest(new IllegalArgumentException("密码至少 8 位"));
        assertThat(invalid.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(errorCode(invalid)).isEqualTo("invalid_request");

        ResponseEntity<?> unavailable = controller.handleAuthUnavailable(new IllegalStateException("鉴权接口不可用"));
        assertThat(unavailable.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(errorCode(unavailable)).isEqualTo("auth_unavailable");
    }

    /** me：有效 token → 200 返回用户信息（nickname 兜底 username） */
    @Test
    @SuppressWarnings("unchecked")
    void meWithValidTokenReturnsUserInfo() {
        when(authServiceProvider.getIfAvailable()).thenReturn(authService);
        when(jwtService.parseToken("jwt-ok")).thenReturn(new JwtService.JwtPrincipal("carol", 3L));
        UserAccount user = new UserAccount("carol", "$2hash", Instant.now());
        org.springframework.test.util.ReflectionTestUtils.setField(user, "id", 3L);
        when(authService.me("carol")).thenReturn(user);

        ResponseEntity<?> resp = controller.me("Bearer jwt-ok");

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        Map<String, Object> body = (Map<String, Object>) resp.getBody();
        assertThat(body).containsEntry("uid", 3L).containsEntry("username", "carol").containsEntry("nickname", "carol");
    }

    /** me：无头 / 伪造 / 过期 token → 401 unauthorized，且不触达 service */
    @Test
    void meWithoutOrInvalidTokenReturns401() {
        ResponseEntity<?> noHeader = controller.me(null);
        assertThat(noHeader.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(errorCode(noHeader)).isEqualTo("unauthorized");

        when(jwtService.parseToken("bad-jwt")).thenThrow(new io.jsonwebtoken.security.SignatureException("伪造"));
        ResponseEntity<?> forged = controller.me("Bearer bad-jwt");
        assertThat(forged.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(errorCode(forged)).isEqualTo("unauthorized");

        verify(authServiceProvider, never()).getIfAvailable();
    }

    /** status：鉴权开/关两态（D6 前端探测） */
    @Test
    void statusReflectsAuthEnabledFlag() {
        when(authProperties.isAuthEnabled()).thenReturn(true);
        assertThat(controller.status()).containsEntry("enabled", true);

        when(authProperties.isAuthEnabled()).thenReturn(false);
        assertThat(controller.status()).containsEntry("enabled", false);
    }

    /** memory 模式（AuthService 缺席）：register 抛 IllegalStateException，经 handleAuthUnavailable 映射 503 auth_unavailable（见 exceptionHandlersMapToSemanticStatusAndErrorCode），不误判 409/401 */
    @Test
    void registerWithoutJdbcDataLayerFailsExplicitly() {
        when(authServiceProvider.getIfAvailable()).thenReturn(null);

        assertThatThrownBy(() -> controller.register(new AuthController.AuthBody("alice", "password123")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("pf.chat.memory");
    }

    private String errorCode(ResponseEntity<?> resp) {
        return (String) ((Map<String, Object>) resp.getBody()).get("error");
    }
}
