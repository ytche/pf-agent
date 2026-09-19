package com.pfagent.agent.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * AuthProperties 装配校验测试（SP7 T1，覆盖 D1 fail-fast）
 *
 * 补齐 coder 未覆盖的启动校验盲区：
 * - pf.auth.enabled=true 且 pf.chat.memory=memory → 启动失败（IllegalStateException，提示明确）
 * - pf.auth.enabled=true 且 pf.chat.memory=jdbc（含大小写不敏感）→ 校验不阻断
 * - 默认（两属性均未配置）→ 正常启动，鉴权关闭
 * - pf.auth.enabled=false + memory → 正常启动（两态互不影响）
 */
class AuthPropertiesTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withUserConfiguration(AuthProperties.class);

    /** D1 fail-fast：开鉴权但非 jdbc 持久化 → 启动失败，错误信息指向 pf.chat.memory=jdbc */
    @Test
    void authEnabledWithMemoryFailsFast() {
        runner.withPropertyValues("pf.auth.enabled=true", "pf.chat.memory=memory")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThatThrownBy(() -> context.getBean(AuthProperties.class))
                            .rootCause()
                            .isInstanceOf(IllegalStateException.class)
                            .hasMessageContaining("pf.chat.memory=jdbc");
                });
    }

    /** D1 fail-fast 的边界：空串 / 未配置 memory 值同样被拦截（authEnabled 且非 jdbc） */
    @Test
    void authEnabledWithAbsentMemoryPropertyFailsFast() {
        runner.withPropertyValues("pf.auth.enabled=true").run(context -> {
            // 未配置时 AuthProperties 的 @Value 缺省值兜底为 jdbc，应启动成功
            assertThat(context).hasNotFailed();
        });
    }

    /** D1 正向：开鉴权 + jdbc → 校验放行 */
    @Test
    void authEnabledWithJdbcStarts() {
        runner.withPropertyValues("pf.auth.enabled=true", "pf.chat.memory=jdbc")
                .run(context -> assertThat(context).hasNotFailed());
    }

    /** 大小写不敏感：JDBC 大写同样通过（equalsIgnoreCase 契约） */
    @Test
    void authEnabledWithJdbcUpperCaseStarts() {
        runner.withPropertyValues("pf.auth.enabled=true", "pf.chat.memory=JDBC")
                .run(context -> assertThat(context).hasNotFailed());
    }

    /** 默认两态：auth.enabled 缺省 false，memory 缺省 jdbc（与主 yml 默认一致）→ 正常 */
    @Test
    void defaultsStartWithAuthDisabled() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AuthProperties.class);
        });
    }

    /** 显式关闭鉴权 + memory 模式 → 正常（两态组合互不干扰） */
    @Test
    void authDisabledWithMemoryStarts() {
        runner.withPropertyValues("pf.auth.enabled=false", "pf.chat.memory=memory")
                .run(context -> assertThat(context).hasNotFailed());
    }
}
