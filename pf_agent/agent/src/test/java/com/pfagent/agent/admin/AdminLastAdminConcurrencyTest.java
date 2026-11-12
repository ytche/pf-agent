package com.pfagent.agent.admin;

import com.pfagent.agent.auth.UserAccount;
import com.pfagent.agent.auth.UserAccountRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 「不得删除/降级最后一个 admin」自保护的并发正确性测试（F-023，评审 p2-1）
 *
 * 背景：自保护判定若只是「先计数、再删除」，并发下两个 admin 各删对方会双双读到 2、
 * 双双放行，最终管理员归零。修复后 AdminService 在判定前对全部 admin 行加悲观写锁
 * （{@code SELECT ... FOR UPDATE}，按 id 升序），并发事务串行化。
 *
 * 本测试用真实 DataSource + 真实事务代理（{@code @Import(AdminService.class)} 使
 * {@code @Transactional} 生效），两个线程在同一起跑线同时发起删除/降级，断言无论
 * 怎样交错，最终都恰好保留 1 个 admin（不会归零）。测试方法用
 * {@code NOT_SUPPORTED} 关闭测试托管事务，使两个线程各自开启真实事务、提交可见。
 *
 * 用独立 H2 库并显式放大 LOCK_TIMEOUT，避免被测事务短暂阻塞后到者时触发锁超时。
 */
@DataJpaTest(properties = {
        "spring.flyway.enabled=false",
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "pf.chat.memory=jdbc",
        "spring.datasource.url=jdbc:h2:mem:m6adminconc;LOCK_TIMEOUT=30000",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password="
})
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import({AdminService.class, AdminLastAdminConcurrencyTest.TestBeans.class})
class AdminLastAdminConcurrencyTest {

    @TestConfiguration
    static class TestBeans {
        @Bean
        PasswordEncoder passwordEncoder() {
            return new BCryptPasswordEncoder();
        }
    }

    @Autowired
    private AdminService adminService;

    @Autowired
    private UserAccountRepository userAccountRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    /** 两个 admin 并删对方：最终恰好剩 1 个 admin（修复前会双双放行 → 归零） */
    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void concurrentDeleteOfAdminsNeverEmptiesAdminSet() throws Exception {
        userAccountRepository.deleteAll();
        UserAccount a = seedAdmin("admin_a");
        UserAccount b = seedAdmin("admin_b");

        List<String> outcomes = runConcurrently(List.of(
                () -> adminService.deleteUser(a.getId()),
                () -> adminService.deleteUser(b.getId())));

        assertThat(outcomes).doesNotContain("ERROR");
        assertThat(outcomes).containsExactlyInAnyOrder("OK", "REJECTED");
        assertThat(userAccountRepository.countByRole(UserAccount.ROLE_ADMIN)).isEqualTo(1);

        userAccountRepository.deleteAll();
    }

    /** 两个 admin 并降级对方：最终恰好剩 1 个 admin */
    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void concurrentDemotionOfAdminsNeverEmptiesAdminSet() throws Exception {
        userAccountRepository.deleteAll();
        UserAccount a = seedAdmin("admin_c");
        UserAccount b = seedAdmin("admin_d");

        List<String> outcomes = runConcurrently(List.of(
                () -> adminService.updateRole(a.getId(), UserAccount.ROLE_USER),
                () -> adminService.updateRole(b.getId(), UserAccount.ROLE_USER)));

        assertThat(outcomes).doesNotContain("ERROR");
        assertThat(outcomes).containsExactlyInAnyOrder("OK", "REJECTED");
        assertThat(userAccountRepository.countByRole(UserAccount.ROLE_ADMIN)).isEqualTo(1);

        userAccountRepository.deleteAll();
    }

    private UserAccount seedAdmin(String username) {
        return userAccountRepository.save(
                new UserAccount(username, passwordEncoder.encode("password123"), Instant.now(),
                        UserAccount.ROLE_ADMIN));
    }

    /** 让 tasks 尽量同时起跑，返回每个任务的 "OK" / "REJECTED" / "ERROR:..." 结果 */
    private List<String> runConcurrently(List<Runnable> tasks) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(tasks.size());
        CountDownLatch ready = new CountDownLatch(tasks.size());
        CountDownLatch go = new CountDownLatch(1);
        List<Future<String>> futures = new ArrayList<>();
        try {
            for (Runnable task : tasks) {
                futures.add(pool.submit(() -> {
                    ready.countDown();
                    go.await();
                    try {
                        task.run();
                        return "OK";
                    } catch (LastAdminException ex) {
                        return "REJECTED";
                    } catch (Exception ex) {
                        return "ERROR:" + ex.getClass().getSimpleName();
                    }
                }));
            }
            ready.await();
            go.countDown();
            List<String> outcomes = new ArrayList<>();
            for (Future<String> future : futures) {
                outcomes.add(future.get(30, TimeUnit.SECONDS));
            }
            return outcomes;
        } finally {
            pool.shutdownNow();
        }
    }
}
