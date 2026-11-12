package com.pfagent.agent.auth;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;

/**
 * 用户域服务（SP7 T2 / D2 + D4 的 service 侧）
 *
 * 注册：归一用户名 → 格式校验（3~64 字符，字母/数字/下划线/中文）→ 唯一性校验
 * → BCrypt 入库 → 注册即签发 JWT（注册即登录）。登录：校验凭证 → 更新
 * last_login_at → 签发 JWT。nickname 缺省兜底为 username。
 * 注册用户角色固定为 {@link UserAccount#ROLE_USER}（管理员由 AdminBootstrap / admin 后台创建）。
 * 用户名/密码规则与 admin 建号共用 {@link Credentials}。
 *
 * 只在 jdbc 模式装配：用户表在 PG（Flyway V3）；memory 模式下无数据层，
 * 且 pf.auth.enabled=true + memory 已被 AuthProperties 启动校验拦截。
 */
@Service
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
public class AuthService {

    @Autowired
    private UserAccountRepository userAccountRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    @Autowired
    private JwtService jwtService;

    /** 注册即登录：返回签发结果（token + 用户标识），异常语义见 UsernameTakenException / IllegalArgumentException */
    @Transactional
    public AuthResult register(String rawUsername, String rawPassword) {
        String username = Credentials.normalizeUsername(rawUsername);
        String password = Credentials.validatePassword(rawPassword);
        if (userAccountRepository.findByUsername(username).isPresent()) {
            throw new UsernameTakenException(username);
        }
        UserAccount user = new UserAccount(username, passwordEncoder.encode(password), Instant.now(),
                UserAccount.ROLE_USER);
        userAccountRepository.save(user);
        return issue(user);
    }

    /** 登录：校验凭证（不区分用户不存在/密码错误），更新 last_login_at 并签发 JWT */
    @Transactional
    public AuthResult login(String rawUsername, String rawPassword) {
        String username = Credentials.normalizeUsername(rawUsername);
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

    private AuthResult issue(UserAccount user) {
        return new AuthResult(jwtService.issueToken(user), user.getId(), user.getUsername(),
                user.getNickname() == null ? user.getUsername() : user.getNickname());
    }

    /** 注册/登录的统一出参：token + 用户标识（T3 的 AuthController 直接包装返回） */
    public record AuthResult(String token, Long uid, String username, String nickname) {
    }
}
