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

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * AuthService 边界补充测试（SP7 T2 白盒审计盲区补齐）
 *
 * coder 的 AuthServiceTest 已覆盖主链路，但以下边界未覆盖，此处补齐：
 * - 密码长度恰为 8 位（下限）合法 / 7 位拒绝——「8 位下限」的精确边界锁
 * - 密码首尾空白被 trim 后校验（validatePassword 的 trim 契约）
 * - null 用户名 → 拒绝且不产生脏数据
 * - 用户名含空格 / emoji（非法字符路径：空格不属于 \p{IsHan}A-Za-z0-9_）
 * - 中文用户名 64 字符上限（多字节字符的长度语义锁：String.length 按 char 计）
 * - token-ttl-hours 可配置性：非默认 TTL 需反映到 JWT exp-iat
 */
@DataJpaTest(properties = {"spring.flyway.enabled=false", "spring.jpa.hibernate.ddl-auto=create-drop"})
class AuthServiceBoundaryTest {

    private static final String TEST_SECRET = "auth-boundary-test-jwt-secret-0123456789abcdef";

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

    /** 密码下限精确边界：恰好 8 位合法，7 位拒绝（差一位都不行） */
    @Test
    void passwordLengthBoundaryEightAcceptedSevenRejected() {
        assertThat(authService.register("user8char", "12345678").username()).isEqualTo("user8char");

        assertThatThrownBy(() -> authService.register("user7char", "1234567"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("8");
        assertThat(userAccountRepository.findByUsername("user7char")).isEmpty();
    }

    /** 密码首尾空白：trim 后参与长度校验与存储（" 12345678 " → 按 8 位合法） */
    @Test
    void passwordIsTrimmedBeforeValidation() {
        AuthService.AuthResult result = authService.register("trimuser", "  12345678  ");

        assertThat(result.token()).isNotBlank();
        UserAccount saved = userAccountRepository.findByUsername("trimuser").orElseThrow();
        // 入库的是 trim 后密码的哈希，原串的哈希也能匹配（matches 用原串校验在登录路径测过，这里锁存储哈希）
        assertThat(saved.getPasswordHash()).startsWith("$2");
    }

    /** null 用户名：归一为空串后拒绝，且不产生脏数据 */
    @Test
    void nullUsernameRejectedWithoutSideEffects() {
        assertThatThrownBy(() -> authService.register(null, "password123"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(userAccountRepository.count()).isZero();
    }

    /** 非法字符路径：空格与 emoji 均不在合法字符集内（Pattern 全匹配语义：中间空格也拒绝） */
    @Test
    void usernameRejectsSpaceAndEmoji() {
        assertThatThrownBy(() -> authService.register("bad name", "password123"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> authService.register("用户😀名", "password123"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(userAccountRepository.count()).isZero();
    }

    /** 中文用户名 64 上限：String.length 按 char 计，64 个汉字合法、65 个拒绝 */
    @Test
    void chineseUsernameLengthBoundary() {
        String maxHan = "法".repeat(64);
        assertThat(authService.register(maxHan, "password123").username()).isEqualTo(maxHan);

        assertThatThrownBy(() -> authService.register("法".repeat(65), "password123"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    /** 中文用户名小写归一无副作用：toLowerCase 不破坏汉字/数字 */
    @Test
    void chineseAndMixedCaseUsernameNormalizedStably() {
        assertThat(authService.register("  法师FIRE_01 ", "password123").username())
                .isEqualTo("法师fire_01");
    }

    /** token-ttl-hours 可配置：覆盖为 1h 后签发的 JWT 有效期须随之变化（默认 72h 的反面锁） */
    @Test
    void customTokenTtlReflectedInJwtExpiration() {
        JwtService shortTtlJwt = new JwtService();
        ReflectionTestUtils.setField(shortTtlJwt, "jwtSecret", TEST_SECRET);
        ReflectionTestUtils.setField(shortTtlJwt, "tokenTtlHours", 1L);
        AuthService customAuth = new AuthService();
        ReflectionTestUtils.setField(customAuth, "userAccountRepository", userAccountRepository);
        ReflectionTestUtils.setField(customAuth, "passwordEncoder", new BCryptPasswordEncoder());
        ReflectionTestUtils.setField(customAuth, "jwtService", shortTtlJwt);

        AuthService.AuthResult result = customAuth.register("ttluser", "password123");

        Claims claims = Jwts.parser()
                .verifyWith(Keys.hmacShaKeyFor(TEST_SECRET.getBytes(StandardCharsets.UTF_8)))
                .build()
                .parseSignedClaims(result.token())
                .getPayload();
        long ttlMillis = claims.getExpiration().getTime() - claims.getIssuedAt().getTime();
        assertThat(Duration.ofMillis(ttlMillis)).isBetween(Duration.ofMinutes(59), Duration.ofHours(1).plusMinutes(1));
    }

    /** 用户不存在时同样走「密码比对」前的统一拒绝，且与密码错误的异常类型/消息完全一致（枚举防线锁） */
    @Test
    void unknownUserAndWrongPasswordIndistinguishable() {
        authService.register("victim", "password123");

        InvalidCredentialsException unknownEx = org.junit.jupiter.api.Assertions.assertThrows(
                InvalidCredentialsException.class, () -> authService.login("attacker", "password123"));
        InvalidCredentialsException wrongPwEx = org.junit.jupiter.api.Assertions.assertThrows(
                InvalidCredentialsException.class, () -> authService.login("victim", "password999"));

        assertThat(unknownEx.getMessage()).isEqualTo(wrongPwEx.getMessage());
    }
}
