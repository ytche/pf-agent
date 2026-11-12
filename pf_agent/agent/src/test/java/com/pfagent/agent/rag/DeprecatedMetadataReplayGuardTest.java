package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FilterType;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;

import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * DeprecatedMetadataReplayGuard 单元与集成测试（DVG-001 清偿）
 *
 * 闸口长期保留、只读不写库：
 *  - 旧配置 pf.stores.metadata-replay=true：装配并在启动时 fail-fast，异常含退役说明与
 *    DEPLOYMENT 全量重灌指引
 *  - 配置缺失 / false：不装配，零行为变化
 *  - 最高优先级：先于任一 DataLoader runner 执行，guard 抛异常后后续 runner 不再执行
 */
class DeprecatedMetadataReplayGuardTest {

    /** guard 本身：run() 抛明确异常，含退役说明与重灌指引 */
    @Test
    void runFailsFastWithRetirementGuidance() {
        DeprecatedMetadataReplayGuard guard = new DeprecatedMetadataReplayGuard();

        assertThatThrownBy(() -> guard.run())
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("SpellMetadataReplayTool 已删除")
                .hasMessageContaining("pf.stores.metadata-replay=true 不再受支持")
                .hasMessageContaining("docs/DEPLOYMENT.md")
                .hasMessageContaining("不要直接修改 vector_store JSON");
    }

    /** 门控接线：仅旧配置显式 true 时装配（havingValue="true"，缺省不装配） */
    @Test
    void conditionalWiringMatchesLegacyProperty() {
        ConditionalOnProperty conditional =
                DeprecatedMetadataReplayGuard.class.getAnnotation(ConditionalOnProperty.class);

        assertThat(conditional).isNotNull();
        assertThat(conditional.name()).containsExactly("pf.stores.metadata-replay");
        assertThat(conditional.havingValue()).isEqualTo("true");
    }

    /** 执行顺序：@Order(HIGHEST_PRECEDENCE)，先于所有默认序 runner */
    @Test
    void hasHighestPrecedenceOrder() {
        Order order = DeprecatedMetadataReplayGuard.class.getAnnotation(Order.class);

        assertThat(order).isNotNull();
        assertThat(order.value()).isEqualTo(Ordered.HIGHEST_PRECEDENCE);
    }

    /** 配置缺失：不装配闸口，正常启动 */
    @Test
    void absentPropertyDoesNotAssembleGuard() {
        new ApplicationContextRunner()
                .withUserConfiguration(GuardTestConfig.class)
                .run(context -> assertThat(context).doesNotHaveBean(DeprecatedMetadataReplayGuard.class));
    }

    /** 配置 false：不装配闸口，正常启动 */
    @Test
    void falsePropertyDoesNotAssembleGuard() {
        new ApplicationContextRunner()
                .withUserConfiguration(GuardTestConfig.class)
                .withPropertyValues("pf.stores.metadata-replay=false")
                .run(context -> assertThat(context).doesNotHaveBean(DeprecatedMetadataReplayGuard.class));
    }

    /** 集成：旧配置 true 真实启动失败；guard 先于 DataLoader 执行，其后 runner 全部未执行 */
    @Test
    void legacyTrueFailsStartupBeforeAnyDataLoaderRunner() {
        GuardTestConfig.EXECUTION.clear();

        assertThatThrownBy(() -> new SpringApplicationBuilder(GuardTestConfig.class)
                .web(WebApplicationType.NONE)
                .properties("pf.stores.metadata-replay=true")
                .run())
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("SpellMetadataReplayTool 已删除");

        // guard 抛异常（rootCause 即其退役说明）后，模拟 DataLoader 的后续 runner 一律未执行
        assertThat(GuardTestConfig.EXECUTION).isEmpty();
    }

    /** 最小配置：经组件扫描装配闸口（使 @ConditionalOnProperty 生效）+ 两个模拟 DataLoader 的顺序记录 spy runner */
    @Configuration
    @ComponentScan(basePackages = "com.pfagent.agent.rag",
            useDefaultFilters = false,
            includeFilters = @ComponentScan.Filter(
                    type = FilterType.ASSIGNABLE_TYPE, classes = DeprecatedMetadataReplayGuard.class))
    static class GuardTestConfig {

        /** 执行顺序记录（guard 抛异常后应停在 "guard"） */
        static final List<String> EXECUTION = new ArrayList<>();

        /** 模拟 DataLoader：默认序（最低优先级族），正常执行则记名 */
        @Bean
        CommandLineLoaderStub spellDataLoaderStub() {
            return new CommandLineLoaderStub("spellDataLoader");
        }

        /** 模拟第二个 DataLoader */
        @Bean
        CommandLineLoaderStub classDataLoaderStub() {
            return new CommandLineLoaderStub("classDataLoader");
        }
    }

    /** 顺序记录 runner：被调用即向 EXECUTION 追加名字 */
    static class CommandLineLoaderStub implements CommandLineRunner {

        private final String name;

        CommandLineLoaderStub(String name) {
            this.name = name;
        }

        @Override
        public void run(String... args) {
            GuardTestConfig.EXECUTION.add(name);
        }
    }
}
