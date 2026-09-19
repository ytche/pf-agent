package com.pfagent.agent.auth;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.Locale;
import java.util.regex.Pattern;

/**
 * 用户域服务（SP7 T2 / D2 + D4 的 service 侧）
 *
 * 注册：归一用户名 → 格式校验（3~64 字符，字母/数字/下划线/中文）→ 唯一性校验
 * → BCrypt 入库 → 注册即签发 JWT（注册即登录）。登录：校验凭证 → 更新
 * last_login_at → 签发 JWT。nickname 缺省兜底为 username。
 *
 * 只在 jdbc 模式装配：用户表在 PG（Flyway V3）；memory 模式下无数据层，
 * 且 pf.auth.enabled=true + memory 已被 AuthProperties 启动校验拦截。
 */
@Service
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
public class AuthService {

    /** 登录名合法字符：字母 / 数字 / 下划线 / 中文（归一后 3~64 字符） */
    private static final Pattern USERNAME_PATTERN = Pattern.compile("[\\p{IsHan}A-Za-z0-9_]{3,64}");

    @Autowired
    private UserAccountRepository userAccountRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    @Autowired
    private JwtService jwtService;

    /** 注册即登录：返回签发结果（token + 用户标识），异常语义见 UsernameTakenException / IllegalArgumentException */
    @Transactional
    public AuthResult register(String rawUsername, String rawPassword) {
        String username = normalizeUsername(rawUsername);
        String password = validatePassword(rawPassword);
        if (userAccountRepository.findByUsername(username).isPresent()) {
            throw new UsernameTakenException(username);
        }
        UserAccount user = new UserAccount(username, passwordEncoder.encode(password), Instant.now());
        userAccountRepository.save(user);
        return issue(user);
    }

    /** 登录：校验凭证（不区分用户不存在/密码错误），更新 last_login_at 并签发 JWT */
    @Transactional
    public AuthResult login(String rawUsername, String rawPassword) {
        String username = normalizeUsername(rawUsername);
        UserAccount user = userAccountRepository.findByUsername(username)
                .orElseThrow(InvalidCredentialsException::new);
        if (!passwordEncoder.matches(rawPassword == null ? "" : rawPassword, user.getPasswordHash())) {
            throw new InvalidCredentialsException();
        }
        user.setLastLoginAt(Instant.now());
        userAccountRepository.save(user);
        return issue(user);
    }

    /** 当前用户：/api/auth/me 按 token 中的 username 查库（用户已删则视同凭证无效） */
    public UserAccount me(String username) {
        return userAccountRepository.findByUsername(username)
                .orElseThrow(InvalidCredentialsException::new);
    }

    /** 归一登录名：去首尾空白 + 小写（大小写不敏感由应用层归一，D2）并做格式校验 */
    static String normalizeUsername(String rawUsername) {
        String username = rawUsername == null ? "" : rawUsername.trim().toLowerCase(Locale.ROOT);
        if (!USERNAME_PATTERN.matcher(username).matches()) {
            throw new IllegalArgumentException(
                    "用户名须为 3~64 字符的字母、数字、下划线或中文: " + username);
        }
        return username;
    }

    /** 校验密码强度（D4：≥8 位），返回去首尾空白后的密码 */
    private static String validatePassword(String rawPassword) {
        String password = rawPassword == null ? "" : rawPassword.trim();
        if (password.length() < 8) {
            throw new IllegalArgumentException("密码至少 8 位");
        }
        return password;
    }

    private AuthResult issue(UserAccount user) {
        return new AuthResult(jwtService.issueToken(user), user.getId(), user.getUsername(),
                user.getNickname() == null ? user.getUsername() : user.getNickname());
    }

    /** 注册/登录的统一出参：token + 用户标识（T3 的 AuthController 直接包装返回） */
    public record AuthResult(String token, Long uid, String username, String nickname) {
    }
}
