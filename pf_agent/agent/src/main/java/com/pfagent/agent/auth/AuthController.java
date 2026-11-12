package com.pfagent.agent.auth;

import com.pfagent.agent.config.AuthProperties;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 鉴权接口（SP7 T3 / D4 + D6）：{@code /api/auth/**} 全豁免鉴权拦截器。
 *
 * - POST /api/auth/register：注册即登录，返回 JWT（D4）；F-023 起受注册开关控制，
 *   关闭时 403 registration_closed
 * - POST /api/auth/login：登录，返回 JWT
 * - GET  /api/auth/me：带 token 返回当前用户信息（前端恢复登录态用）
 * - GET  /api/auth/status：返回 {enabled, registrationEnabled}，前端启动时据此决定
 *   是否显示登录/注册入口（D6 + F-023）
 *
 * 错误码语义化（D4）：username_taken / invalid_credentials / invalid_request
 * 对应 409 / 401 / 400，错误体统一 {error: "..."}（可加 message），前端直接消费。
 * F-023 追加 registration_closed → 403。
 *
 * AuthService 仅在 jdbc 模式装配（memory 模式无用户表，AuthProperties 已拦截
 * auth.enabled=true + memory 的组合）；此处经 ObjectProvider 注入，auth 接口在
 * memory 模式返回 503 auth_unavailable，enabled 与否的默认行为不受影响。
 * AppSettingService 同理经 ObjectProvider 注入：memory 模式无配置表，注册开关
 * 回退到 yml 默认值。
 */
@RestController
@RequestMapping("/api/auth")
public class AuthController {

    @Autowired
    private AuthProperties authProperties;

    @Autowired
    private JwtService jwtService;

    @Autowired
    private ObjectProvider<AuthService> authServiceProvider;

    @Autowired
    private ObjectProvider<AppSettingService> appSettingServiceProvider;

    /** 注册开关默认值（memory 模式无配置表时的兜底；与 yml / V5 种子一致） */
    @Value("${pf.auth.registration-enabled:true}")
    private boolean registrationEnabledDefault;

    /** 会话记忆实现（jdbc/memory）：status 据此暴露 memoryMode，供前端提示临时模式 */
    @Value("${pf.chat.memory:jdbc}")
    private String chatMemory;

    /** 注册即登录：成功 200 返回 token + 用户标识；注册开关关闭时 403 registration_closed */
    @PostMapping("/register")
    public ResponseEntity<?> register(@RequestBody AuthBody body) {
        if (!isRegistrationEnabled()) {
            throw new RegistrationClosedException();
        }
        AuthService.AuthResult result = requireAuthService().register(body.username(), body.password());
        return ResponseEntity.ok(result);
    }

    /** 登录：成功 200 返回 token + 用户标识 */
    @PostMapping("/login")
    public ResponseEntity<?> login(@RequestBody AuthBody body) {
        AuthService.AuthResult result = requireAuthService().login(body.username(), body.password());
        return ResponseEntity.ok(result);
    }

    /** 当前用户：Bearer token 有效则返回用户信息，否则 401 unauthorized */
    @GetMapping("/me")
    public ResponseEntity<?> me(@RequestHeader(value = "Authorization", required = false) String authorization) {
        JwtService.JwtPrincipal principal = resolvePrincipal(authorization);
        if (principal == null) {
            return unauthorized();
        }
        UserAccount user = requireAuthService().me(principal.username());
        return ResponseEntity.ok(Map.of(
                "uid", user.getId(),
                "username", user.getUsername(),
                "nickname", user.getNickname() == null ? user.getUsername() : user.getNickname()));
    }

    /** 鉴权/注册开关探测：前端启动时据此决定是否显示登录/注册入口（D6 + F-023） */
    @GetMapping("/status")
    public Map<String, Object> status() {
        Map<String, Object> status = new LinkedHashMap<>();
        status.put("enabled", authProperties.isAuthEnabled());
        status.put("registrationEnabled", isRegistrationEnabled());
        status.put("memoryMode", chatMemory != null && !"jdbc".equalsIgnoreCase(chatMemory.trim()));
        return status;
    }

    /** 注册入口是否开放：jdbc 模式读 app_setting（缺行回退 yml 默认），memory 模式回退 yml 默认 */
    private boolean isRegistrationEnabled() {
        AppSettingService appSettingService = appSettingServiceProvider.getIfAvailable();
        return appSettingService == null ? registrationEnabledDefault : appSettingService.isRegistrationEnabled();
    }

    /** UsernameTakenException → 409 username_taken（D4） */
    @ExceptionHandler(UsernameTakenException.class)
    public ResponseEntity<?> handleUsernameTaken(UsernameTakenException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("error", "username_taken", "message", ex.getMessage()));
    }

    /** RegistrationClosedException → 403 registration_closed（F-023 注册开关） */
    @ExceptionHandler(RegistrationClosedException.class)
    public ResponseEntity<?> handleRegistrationClosed(RegistrationClosedException ex) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(Map.of("error", "registration_closed", "message", ex.getMessage()));
    }

    /** InvalidCredentialsException → 401 invalid_credentials（D4） */
    @ExceptionHandler(InvalidCredentialsException.class)
    public ResponseEntity<?> handleInvalidCredentials(InvalidCredentialsException ex) {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "invalid_credentials", "message", ex.getMessage()));
    }

    /** 参数校验失败（弱密码/非法用户名等）→ 400 invalid_request（D4） */
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<?> handleInvalidRequest(IllegalArgumentException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(Map.of("error", "invalid_request", "message", ex.getMessage()));
    }

    /** 数据层缺席（memory 模式误调 auth 接口）→ 503 auth_unavailable（SP7 验收挂起项①用户拍板） */
    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<?> handleAuthUnavailable(IllegalStateException ex) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("error", "auth_unavailable", "message", ex.getMessage()));
    }

    /** 从 Authorization: Bearer <jwt> 解析身份；缺失/非法/过期一律返回 null（由调用方转 401） */
    private JwtService.JwtPrincipal resolvePrincipal(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            return null;
        }
        try {
            return jwtService.parseToken(authorization.substring("Bearer ".length()).trim());
        } catch (io.jsonwebtoken.JwtException | IllegalArgumentException ex) {
            return null;
        }
    }

    private ResponseEntity<?> unauthorized() {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "unauthorized"));
    }

    private AuthService requireAuthService() {
        AuthService authService = authServiceProvider.getIfAvailable();
        if (authService == null) {
            throw new IllegalStateException(
                    "鉴权接口不可用：pf.chat.memory=memory 时无用户表，请将 pf.chat.memory 设为 jdbc");
        }
        return authService;
    }

    /** register/login 共用请求体：username + password */
    public record AuthBody(String username, String password) {
    }
}
