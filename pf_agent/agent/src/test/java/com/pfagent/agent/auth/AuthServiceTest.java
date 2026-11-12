package com.pfagent.agent.auth;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * AuthService 集成测试（@DataJpaTest + H2 内嵌库，SP7 T2）
 *
 * 用真实 UserAccountRepository + Hibernate 建表（create-drop，同 JdbcChatMemoryTest 的
 * 豁免方式）验证注册/登录/JWT 签发链路：归一化边界、唯一性、BCrypt 落库、
 * last_login_at 更新与 JWT payload 内容。AuthService/JwtService 是手动 new +
 * 反射注入（slice 测试不自动装配），PasswordEncoder 用真实 BCrypt（哈希行为即被测对象）。
 */
@DataJpaTest(properties = {"spring.flyway.enabled=false", "spring.jpa.hibernate.ddl-auto=create-drop"})
class AuthServiceTest {

    private static final String TEST_SECRET = "auth-service-test-jwt-secret-0123456789abcdef";

    @Autowired
    private UserAccountRepository userAccountRepository;

    private AuthService authService;

    @BeforeEach
    void setUp() {
        JwtService jwtService = new JwtService();
        ReflectionTestUtils.setField(jwtService, "jwtSecret", TEST_SECRET);
        ReflectionTestUtils.setField(jwtService, "tokenTtlHours", 72L);
        authService = new AuthService();
        ReflectionTestUtils.setField(authService, "userAccountRepository", userAccountRepository);
        ReflectionTestUtils.setField(authService, "passwordEncoder", new BCryptPasswordEncoder());
        ReflectionTestUtils.setField(authService, "jwtService", jwtService);
    }

    /** 注册成功：返回 token + 用户标识，密码 BCrypt 入库（无明文），nickname 兜底为 username */
    @Test
    void registerSavesUserWithHashedPasswordAndIssuesToken() {
        AuthService.AuthResult result = authService.register("  Alice_一号  ", "password123");

        assertThat(result.token()).isNotBlank();
        assertThat(result.username()).isEqualTo("alice_一号");
        assertThat(result.nickname()).isEqualTo("alice_一号");

        UserAccount saved = userAccountRepository.findByUsername("alice_一号").orElseThrow();
        assertThat(saved.getId()).isEqualTo(result.uid());
        assertThat(saved.getPasswordHash()).startsWith("$2").isNotEqualTo("password123");
        assertThat(saved.getRole()).isEqualTo(UserAccount.ROLE_USER);
        assertThat(saved.getCreatedAt()).isNotNull();
        assertThat(saved.getLastLoginAt()).isNull();
    }

    /** 用户名重复：归一（去空白 + 小写）后撞库即拒绝 */
    @Test
    void registerRejectsDuplicateUsernameAfterNormalization() {
        authService.register("Alice", "password123");

        assertThatThrownBy(() -> authService.register("  ALICE ", "password456"))
                .isInstanceOf(UsernameTakenException.class);
    }

    /** 弱密码（<8 位）拒绝；null/空白密码同样拒绝 */
    @Test
    void registerRejectsWeakPassword() {
        assertThatThrownBy(() -> authService.register("bob", "short"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("8");
        assertThatThrownBy(() -> authService.register("bob", null))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(userAccountRepository.findByUsername("bob")).isEmpty();
    }

    /** 归一化边界：3 字符下限与 64 字符上限合法，超长/非法字符拒绝 */
    @Test
    void registerNormalizesUsernameBoundaries() {
        assertThat(authService.register(" abc ", "password123").username()).isEqualTo("abc");
        String maxLen = "x".repeat(64);
        assertThat(authService.register(maxLen, "password123").username()).isEqualTo(maxLen);

        assertThatThrownBy(() -> authService.register("ab", "password123"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> authService.register("x".repeat(65), "password123"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> authService.register("bad!name", "password123"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    /** 登录成功：更新 last_login_at 并签发 token；大小写/空白不敏感 */
    @Test
    void loginUpdatesLastLoginAtAndIssuesToken() {
        authService.register("carol", "password123");

        AuthService.AuthResult result = authService.login(" CAROL ", "password123");

        assertThat(result.token()).isNotBlank();
        Optional<UserAccount> user = userAccountRepository.findByUsername("carol");
        assertThat(user).isPresent();
        assertThat(user.get().getLastLoginAt()).isNotNull();
    }

    /** 错误密码 / 不存在用户统一报 InvalidCredentialsException（不区分两种失败） */
    @Test
    void loginRejectsWrongPasswordAndUnknownUser() {
        authService.register("dave", "password123");

        assertThatThrownBy(() -> authService.login("dave", "wrong-password"))
                .isInstanceOf(InvalidCredentialsException.class);
        assertThatThrownBy(() -> authService.login("nobody", "password123"))
                .isInstanceOf(InvalidCredentialsException.class);
    }

    /** 登录失败不更新 last_login_at */
    @Test
    void failedLoginLeavesLastLoginAtUntouched() {
        authService.register("erin", "password123");
        authService.login("erin", "password123");
        Instant afterFirstLogin = userAccountRepository.findByUsername("erin").orElseThrow().getLastLoginAt();

        assertThatThrownBy(() -> authService.login("erin", "wrong-password"))
                .isInstanceOf(InvalidCredentialsException.class);
        assertThat(userAccountRepository.findByUsername("erin").orElseThrow().getLastLoginAt())
                .isEqualTo(afterFirstLogin);
    }

    /** JWT payload：sub=归一后 username、uid=用户主键、有效期 ≈72h、HS256 可解析 */
    @Test
    void issuedJwtContainsExpectedPayload() {
        AuthService.AuthResult result = authService.register("frank", "password123");

        Claims claims = Jwts.parser()
                .verifyWith(Keys.hmacShaKeyFor(TEST_SECRET.getBytes(StandardCharsets.UTF_8)))
                .build()
                .parseSignedClaims(result.token())
                .getPayload();

        assertThat(claims.getSubject()).isEqualTo("frank");
        assertThat(claims.get("uid", Long.class)).isEqualTo(result.uid());
        long ttlMillis = claims.getExpiration().getTime() - claims.getIssuedAt().getTime();
        assertThat(Duration.ofMillis(ttlMillis)).isBetween(Duration.ofHours(71), Duration.ofHours(73));
        // issuedAt/expiration 为真实时间戳
        assertThat(claims.getIssuedAt()).isBeforeOrEqualTo(new Date());
    }
}
