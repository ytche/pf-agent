package com.pfagent.agent.usage;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.transaction.PlatformTransactionManager;

import javax.sql.DataSource;
import java.time.Clock;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

/**
 * 用量 bean 装配切换：memory 模式 no-op、jdbc 模式落库实现与查询服务，
 * 两者互斥（同一模式只有一个 UsageRecorder）。
 */
class UsageWiringTest {

    @Test
    void memoryModeOnlyProvidesNoopRecorder() {
        runner().withPropertyValues("pf.chat.memory=memory").run(context -> {
            assertThat(context).hasSingleBean(com.pfagent.agent.telemetry.UsageRecorder.class);
            assertThat(context.getBean(com.pfagent.agent.telemetry.UsageRecorder.class))
                    .isInstanceOf(NoopUsageRecorder.class);
            assertThat(context).doesNotHaveBean(UsageService.class);
            assertThat(context).doesNotHaveBean(UsageQueryDao.class);
        });
    }

    @Test
    void jdbcModeWiresRecorderAndQueryService() {
        runner().withPropertyValues("pf.chat.memory=jdbc").run(context -> {
            assertThat(context).hasSingleBean(com.pfagent.agent.telemetry.UsageRecorder.class);
            assertThat(context.getBean(com.pfagent.agent.telemetry.UsageRecorder.class))
                    .isInstanceOf(JdbcUsageRecorder.class);
            assertThat(context).hasSingleBean(UsageService.class);
            assertThat(context).hasSingleBean(UsageQueryDao.class);
            assertThat(context).hasSingleBean(UsageRequestContext.class);
        });
    }

    private ApplicationContextRunner runner() {
        return new ApplicationContextRunner()
                .withUserConfiguration(JdbcUsageRecorder.class, NoopUsageRecorder.class,
                        UsageQueryDao.class, UsageService.class, UsageRequestContext.class)
                .withBean(DataSource.class, () -> mock(DataSource.class))
                .withBean(PlatformTransactionManager.class, () -> mock(PlatformTransactionManager.class))
                .withBean(UsageRecordRepository.class, () -> mock(UsageRecordRepository.class))
                .withBean(Clock.class, Clock::systemUTC);
    }
}
