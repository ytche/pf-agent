package com.pfagent.agent.auth;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;

/**
 * 初始 admin 账号引导（F-023）
 *
 * 管理后台需要一个人工可达的管理员入口，但配置文件明文密码已被用户否决（2026-09-24）。
 * 做法：初始密码只经环境变量 PF_ADMIN_PASSWORD 注入（yml: pf.auth.admin-password），
 * 首次启动幂等创建 admin 账号（role=admin，BCrypt 哈希入 user_account）。
 *
 * 幂等与不覆盖：按 {@code pf.auth.admin-username}（默认 admin）查库，账号已存在则跳过，
 * 绝不覆盖既有账号（含其密码/角色）——改密交由 admin 界面「改密」端点完成。
 * 未配置 PF_ADMIN_PASSWORD 时不创建，仅 WARN 提示（admin 界面将无可用管理员）。
 * 配置了但过短（不满足密码策略）同样只 WARN 跳过、不建号——避免一个不合规的环境变量
 * 让整个应用启动失败（与「未配置」同级处理，错配不应升级为启动阻断）。
 *
 * 只在 jdbc 模式装配（用户表在 PG）；启动即在 ApplicationRunner 阶段执行，晚于 Flyway 迁移。
 */
@Component
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
public class AdminBootstrap implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(AdminBootstrap.class);

    @Autowired
    private UserAccountRepository userAccountRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    /** 初始 admin 用户名（可在 yml 覆盖） */
    @Value("${pf.auth.admin-username:admin}")
    private String adminUsername;

    /** 初始 admin 密码：只经 env PF_ADMIN_PASSWORD 注入，缺省空 = 不创建 */
    @Value("${pf.auth.admin-password:}")
    private String adminPassword;

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        String username = Credentials.normalizeUsername(adminUsername);
        if (userAccountRepository.findByUsername(username).isPresent()) {
            log.info("admin 账号已存在，跳过初始化（不覆盖）: {}", username);
            return;
        }
        if (adminPassword == null || adminPassword.isBlank()) {
            log.warn("未配置 PF_ADMIN_PASSWORD，跳过初始 admin 创建；管理后台将无可用管理员。"
                    + "如需启用请设置环境变量 PF_ADMIN_PASSWORD 后重启。");
            return;
        }
        String password;
        try {
            password = Credentials.validatePassword(adminPassword);
        } catch (IllegalArgumentException ex) {
            log.warn("PF_ADMIN_PASSWORD 不满足密码策略（至少 {} 位），跳过初始 admin 创建；"
                    + "管理后台将无可用管理员。请设置合规密码后重启。详情: {}",
                    Credentials.MIN_PASSWORD_LENGTH, ex.getMessage());
            return;
        }
        UserAccount admin = new UserAccount(username, passwordEncoder.encode(password), Instant.now(),
                UserAccount.ROLE_ADMIN);
        userAccountRepository.save(admin);
        log.info("已创建初始 admin 账号: {}（role=admin）", username);
    }
}
