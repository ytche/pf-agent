package com.pfagent.agent.admin;

import com.pfagent.agent.auth.Credentials;
import com.pfagent.agent.auth.InvalidCredentialsException;
import com.pfagent.agent.auth.UserAccount;
import com.pfagent.agent.auth.UserAccountRepository;
import com.pfagent.agent.auth.UsernameTakenException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.domain.Sort;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * 管理后台用户域服务（F-023）
 *
 * 提供 admin 界面所需的用户增删改查与自助改密，复用 AuthService 的用户名/密码规则
 * （{@link Credentials}）与 BCrypt 编码。所有写操作受自保护约束：不得删除或降级
 * 最后一个 admin（{@link #deleteUser} / {@link #updateRole}）。
 *
 * 本服务不做权限判定——角色守卫在 {@link AdminInterceptor}（HTTP 层）完成，此处只保证
 * 业务规则（含自保护），便于单元测试直接驱动。
 *
 * 自保护的并发正确性：删除/降级 admin 前先经 {@code lockByRoleOrderedById} 对全部 admin
 * 行加悲观写锁（SELECT ... FOR UPDATE，按 id 升序取锁避免死锁），再在锁内重新计数。并发
 * 事务在此串行化，后到者阻塞至先到者提交后重新读取，因此「两个 admin 同时互删」不会再
 * 双双放行导致管理员归零。
 *
 * 只在 jdbc 模式装配（用户表在 PG）；memory 模式下 admin 端点经 ObjectProvider 判空
 * 返回 503 admin_unavailable。
 */
@Service
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
public class AdminService {

    /** 允许的角色集合 */
    private static final Set<String> ROLES = Set.of(UserAccount.ROLE_USER, UserAccount.ROLE_ADMIN);

    @Autowired
    private UserAccountRepository userAccountRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    /** 该登录名是否为管理员（role=admin）；用户不存在返回 false */
    @Transactional(readOnly = true)
    public boolean isAdmin(String username) {
        if (username == null) {
            return false;
        }
        return userAccountRepository.findByUsername(username)
                .map(u -> UserAccount.ROLE_ADMIN.equals(u.getRole()))
                .orElse(false);
    }

    /** 用户列表（按 id 升序），不含密码哈希 */
    @Transactional(readOnly = true)
    public List<UserView> listUsers() {
        return userAccountRepository.findAll(Sort.by(Sort.Direction.ASC, "id")).stream()
                .map(UserView::of)
                .toList();
    }

    /** 新建用户（可指定角色）：用户名/密码规则与注册一致；重名 → UsernameTakenException */
    @Transactional
    public UserView createUser(String rawUsername, String rawPassword, String rawRole) {
        String username = Credentials.normalizeUsername(rawUsername);
        String password = Credentials.validatePassword(rawPassword);
        String role = normalizeRole(rawRole);
        if (userAccountRepository.findByUsername(username).isPresent()) {
            throw new UsernameTakenException(username);
        }
        UserAccount user = new UserAccount(username, passwordEncoder.encode(password), Instant.now(), role);
        return UserView.of(userAccountRepository.save(user));
    }

    /** 修改用户角色；把最后一个 admin 降级为 user 时拒绝（自保护，锁内判定，见类注释） */
    @Transactional
    public UserView updateRole(Long id, String rawRole) {
        String role = normalizeRole(rawRole);
        UserAccount user = requireUser(id);
        if (UserAccount.ROLE_ADMIN.equals(user.getRole())
                && !UserAccount.ROLE_ADMIN.equals(role)
                && lockAdminCount() <= 1) {
            throw new LastAdminException();
        }
        user.setRole(role);
        return UserView.of(userAccountRepository.save(user));
    }

    /** 重置指定用户密码（admin 操作，无需原密码） */
    @Transactional
    public void resetPassword(Long id, String rawPassword) {
        String password = Credentials.validatePassword(rawPassword);
        UserAccount user = requireUser(id);
        user.setPasswordHash(passwordEncoder.encode(password));
        userAccountRepository.save(user);
    }

    /** 删除用户；删除最后一个 admin 时拒绝（自保护，锁内判定，见类注释） */
    @Transactional
    public void deleteUser(Long id) {
        UserAccount user = requireUser(id);
        if (UserAccount.ROLE_ADMIN.equals(user.getRole()) && lockAdminCount() <= 1) {
            throw new LastAdminException();
        }
        userAccountRepository.delete(user);
    }

    /** 当前登录管理员自助改密：校验原密码（错则 InvalidCredentialsException）后 BCrypt 重写 */
    @Transactional
    public void changeOwnPassword(String username, String currentPassword, String newPassword) {
        UserAccount user = userAccountRepository.findByUsername(username)
                .orElseThrow(InvalidCredentialsException::new);
        if (!passwordEncoder.matches(currentPassword == null ? "" : currentPassword, user.getPasswordHash())) {
            throw new InvalidCredentialsException();
        }
        String password = Credentials.validatePassword(newPassword);
        user.setPasswordHash(passwordEncoder.encode(password));
        userAccountRepository.save(user);
    }

    /**
     * 对全部 admin 行加悲观写锁（按 id 升序）后返回当前管理员数。
     * 自保护判定必须经此方法：并发删除/降级在此串行化，锁内读到的是已提交的真实数量。
     */
    private long lockAdminCount() {
        return userAccountRepository.lockByRoleOrderedById(UserAccount.ROLE_ADMIN).size();
    }

    private UserAccount requireUser(Long id) {
        if (id == null) {
            throw new UserNotFoundException("用户 id 不能为空");
        }
        return userAccountRepository.findById(id).orElseThrow(() -> new UserNotFoundException(id));
    }

    /** 归一角色：缺省 user，仅接受 user / admin */
    private static String normalizeRole(String rawRole) {
        String role = rawRole == null ? UserAccount.ROLE_USER : rawRole.trim().toLowerCase(Locale.ROOT);
        if (!ROLES.contains(role)) {
            throw new IllegalArgumentException("角色只能是 user 或 admin: " + rawRole);
        }
        return role;
    }

    /**
     * 用户对外视图（禁止序列化实体，避免泄露 passwordHash）。
     * nickname 缺省兜底为 username（与 /api/auth/me 一致）。
     */
    public record UserView(Long id, String username, String nickname, String role,
                           Instant createdAt, Instant lastLoginAt) {

        static UserView of(UserAccount user) {
            return new UserView(
                    user.getId(),
                    user.getUsername(),
                    user.getNickname() == null ? user.getUsername() : user.getNickname(),
                    user.getRole(),
                    user.getCreatedAt(),
                    user.getLastLoginAt());
        }
    }
}
