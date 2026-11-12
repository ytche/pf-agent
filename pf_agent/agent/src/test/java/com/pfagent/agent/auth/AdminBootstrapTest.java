package com.pfagent.agent.auth;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.util.ReflectionTestUtils;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

/**
 * AdminBootstrap 集成测试（F-023，@DataJpaTest + H2 内嵌库）
 *
 * 锁定初始 admin 引导的三条路径：
 *  - 配置了 PF_ADMIN_PASSWORD 且无同名账号 → 创建 role=admin，密码 BCrypt 落库
 *  - 同名账号已存在 → 跳过，绝不覆盖既有密码/角色（幂等）
 *  - 未配置密码 → 不创建（不产生脏数据）
 */
@DataJpaTest(properties = {"spring.flyway.enabled=false", "spring.jpa.hibernate.ddl-auto=create-drop"})
class AdminBootstrapTest {

    @Autowired
    private UserAccountRepository userAccountRepository;

    private final PasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    private AdminBootstrap bootstrap;

    @BeforeEach
    void setUp() {
        bootstrap = new AdminBootstrap();
        ReflectionTestUtils.setField(bootstrap, "userAccountRepository", userAccountRepository);
        ReflectionTestUtils.setField(bootstrap, "passwordEncoder", passwordEncoder);
        ReflectionTestUtils.setField(bootstrap, "adminUsername", "admin");
        ReflectionTestUtils.setField(bootstrap, "adminPassword", "admin-secret-123");
    }

    /** 首启创建：admin 账号存在、role=admin、密码为 BCrypt 哈希且可校验 */
    @Test
    void createsAdminOnFirstRun() {
        bootstrap.run(null);

        UserAccount admin = userAccountRepository.findByUsername("admin").orElseThrow();
        assertThat(admin.getRole()).isEqualTo(UserAccount.ROLE_ADMIN);
        assertThat(admin.getPasswordHash()).startsWith("$2").isNotEqualTo("admin-secret-123");
        assertThat(passwordEncoder.matches("admin-secret-123", admin.getPasswordHash())).isTrue();
        assertThat(admin.getCreatedAt()).isNotNull();
    }

    /** 幂等且不覆盖：已存在同名账号（普通用户）时跳过，不提升为 admin、不改密码 */
    @Test
    void doesNotOverwriteExistingAccount() {
        UserAccount existing = new UserAccount("admin", "$2existing-hash", java.time.Instant.now(),
                UserAccount.ROLE_USER);
        userAccountRepository.save(existing);

        bootstrap.run(null);

        UserAccount after = userAccountRepository.findByUsername("admin").orElseThrow();
        assertThat(after.getRole()).isEqualTo(UserAccount.ROLE_USER);
        assertThat(after.getPasswordHash()).isEqualTo("$2existing-hash");
        assertThat(userAccountRepository.count()).isEqualTo(1);
    }

    /** 未配置密码：不创建任何账号 */
    @Test
    void skipsWhenPasswordNotConfigured() {
        ReflectionTestUtils.setField(bootstrap, "adminPassword", "  ");

        bootstrap.run(null);

        assertThat(userAccountRepository.findByUsername("admin")).isEmpty();
        assertThat(userAccountRepository.count()).isZero();
    }

    /** 过短密码：只 WARN 跳过，不抛异常、不建号（不合规环境变量不得阻断应用启动） */
    @Test
    void skipsWhenPasswordTooShortWithoutFailingStartup() {
        ReflectionTestUtils.setField(bootstrap, "adminPassword", "short");

        assertThatCode(() -> bootstrap.run(null)).doesNotThrowAnyException();

        assertThat(userAccountRepository.findByUsername("admin")).isEmpty();
        assertThat(userAccountRepository.count()).isZero();
    }

    /** 用户名可配置：非默认 admin 用户名同样创建 */
    @Test
    void usesConfiguredUsername() {
        ReflectionTestUtils.setField(bootstrap, "adminUsername", "root_admin");

        bootstrap.run(null);

        assertThat(userAccountRepository.findByUsername("root_admin")).isPresent();
        assertThat(userAccountRepository.findByUsername("root_admin").orElseThrow().getRole())
                .isEqualTo(UserAccount.ROLE_ADMIN);
    }
}
