package com.pfagent.agent.admin;

import com.pfagent.agent.auth.InvalidCredentialsException;
import com.pfagent.agent.auth.UserAccount;
import com.pfagent.agent.auth.UserAccountRepository;
import com.pfagent.agent.auth.UsernameTakenException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * AdminService 集成测试（F-023，@DataJpaTest + H2 内嵌库）
 *
 * 覆盖 admin 后台用户域业务规则：
 *  - 增：用户名/密码规则与注册一致，重名 409 语义，角色归一
 *  - 查：列表按 id 升序；isAdmin 判定
 *  - 改：改角色、重置密码
 *  - 删：删除用户
 *  - 自保护：不得删除/降级最后一个 admin
 *  - 自助改密：原密码校验（错则 InvalidCredentialsException）+ BCrypt 重写
 */
@DataJpaTest(properties = {"spring.flyway.enabled=false", "spring.jpa.hibernate.ddl-auto=create-drop"})
class AdminServiceTest {

    @Autowired
    private UserAccountRepository userAccountRepository;

    private final PasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    private AdminService adminService;

    @BeforeEach
    void setUp() {
        adminService = new AdminService();
        ReflectionTestUtils.setField(adminService, "userAccountRepository", userAccountRepository);
        ReflectionTestUtils.setField(adminService, "passwordEncoder", passwordEncoder);
    }

    private UserAccount seed(String username, String role) {
        return userAccountRepository.save(
                new UserAccount(username, passwordEncoder.encode("password123"), Instant.now(), role));
    }

    /** isAdmin：仅 role=admin 为真；普通用户与不存在用户为假 */
    @Test
    void isAdminReflectsRole() {
        seed("boss", UserAccount.ROLE_ADMIN);
        seed("joe", UserAccount.ROLE_USER);

        assertThat(adminService.isAdmin("boss")).isTrue();
        assertThat(adminService.isAdmin("joe")).isFalse();
        assertThat(adminService.isAdmin("ghost")).isFalse();
        assertThat(adminService.isAdmin(null)).isFalse();
    }

    /** 新建用户：角色归一（缺省 user / 大写 ADMIN），密码 BCrypt 落库 */
    @Test
    void createUserNormalizesAndHashes() {
        AdminService.UserView user = adminService.createUser("  Alice ", "password123", null);
        assertThat(user.username()).isEqualTo("alice");
        assertThat(user.role()).isEqualTo(UserAccount.ROLE_USER);
        assertThat(user.nickname()).isEqualTo("alice");

        AdminService.UserView admin = adminService.createUser("Root", "password123", "ADMIN");
        assertThat(admin.role()).isEqualTo(UserAccount.ROLE_ADMIN);

        UserAccount stored = userAccountRepository.findByUsername("alice").orElseThrow();
        assertThat(stored.getPasswordHash()).startsWith("$2").isNotEqualTo("password123");
    }

    /** 新建用户重名：拒绝 */
    @Test
    void createUserRejectsDuplicate() {
        seed("bob", UserAccount.ROLE_USER);
        assertThatThrownBy(() -> adminService.createUser("Bob", "password123", null))
                .isInstanceOf(UsernameTakenException.class);
    }

    /** 新建用户非法参数：弱密码 / 非法角色 */
    @Test
    void createUserRejectsInvalidInput() {
        assertThatThrownBy(() -> adminService.createUser("carol", "short", null))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> adminService.createUser("carol", "password123", "superuser"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    /** 列表按 id 升序，且不含密码哈希字段（UserView 无该字段） */
    @Test
    void listUsersOrderedById() {
        seed("u1", UserAccount.ROLE_USER);
        seed("u2", UserAccount.ROLE_USER);
        List<AdminService.UserView> users = adminService.listUsers();

        assertThat(users).extracting(AdminService.UserView::username).containsExactly("u1", "u2");
        assertThat(users.get(0).id()).isLessThan(users.get(1).id());
    }

    /** 改角色成功；重置密码后旧密码失效 */
    @Test
    void updateRoleAndResetPassword() {
        UserAccount user = seed("dave", UserAccount.ROLE_USER);
        seed("boss", UserAccount.ROLE_ADMIN);

        AdminService.UserView promoted = adminService.updateRole(user.getId(), "admin");
        assertThat(promoted.role()).isEqualTo(UserAccount.ROLE_ADMIN);

        adminService.resetPassword(user.getId(), "new-password-9");
        UserAccount stored = userAccountRepository.findById(user.getId()).orElseThrow();
        assertThat(passwordEncoder.matches("new-password-9", stored.getPasswordHash())).isTrue();
        assertThat(passwordEncoder.matches("password123", stored.getPasswordHash())).isFalse();
    }

    /** 自保护：降级最后一个 admin 被拒 */
    @Test
    void updateRoleRejectsDemotingLastAdmin() {
        UserAccount onlyAdmin = seed("solo", UserAccount.ROLE_ADMIN);

        assertThatThrownBy(() -> adminService.updateRole(onlyAdmin.getId(), "user"))
                .isInstanceOf(LastAdminException.class);
        assertThat(userAccountRepository.findById(onlyAdmin.getId()).orElseThrow().getRole())
                .isEqualTo(UserAccount.ROLE_ADMIN);
    }

    /** 有两个 admin 时可降级其一 */
    @Test
    void updateRoleAllowsDemotionWhenAnotherAdminExists() {
        UserAccount a = seed("a", UserAccount.ROLE_ADMIN);
        seed("b", UserAccount.ROLE_ADMIN);

        assertThat(adminService.updateRole(a.getId(), "user").role()).isEqualTo(UserAccount.ROLE_USER);
    }

    /** 删除用户成功 */
    @Test
    void deleteUserRemoves() {
        UserAccount user = seed("erin", UserAccount.ROLE_USER);
        adminService.deleteUser(user.getId());
        assertThat(userAccountRepository.findById(user.getId())).isEmpty();
    }

    /** 自保护：删除最后一个 admin 被拒 */
    @Test
    void deleteRejectsLastAdmin() {
        UserAccount onlyAdmin = seed("solo", UserAccount.ROLE_ADMIN);
        assertThatThrownBy(() -> adminService.deleteUser(onlyAdmin.getId()))
                .isInstanceOf(LastAdminException.class);
        assertThat(userAccountRepository.findById(onlyAdmin.getId())).isPresent();
    }

    /** 删除不存在用户：404 语义 */
    @Test
    void deleteRejectsUnknownUser() {
        assertThatThrownBy(() -> adminService.deleteUser(999L))
                .isInstanceOf(UserNotFoundException.class);
    }

    /** 自助改密：原密码正确则 BCrypt 重写；原密码错误拒绝 */
    @Test
    void changeOwnPasswordChecksCurrent() {
        seed("admin1", UserAccount.ROLE_ADMIN);

        assertThatThrownBy(() -> adminService.changeOwnPassword("admin1", "wrong-pass", "new-password-9"))
                .isInstanceOf(InvalidCredentialsException.class);

        adminService.changeOwnPassword("admin1", "password123", "new-password-9");
        UserAccount stored = userAccountRepository.findByUsername("admin1").orElseThrow();
        assertThat(passwordEncoder.matches("new-password-9", stored.getPasswordHash())).isTrue();
    }
}
