package com.pfagent.agent.config;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.flyway.FlywayAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.orm.jpa.HibernateJpaAutoConfiguration;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.transaction.annotation.EnableTransactionManagement;

/**
 * JDBC 数据层配置（pf.chat.memory=jdbc 时装配，SP1 D2/D7）
 *
 * 默认内存模式（pf.chat.memory=memory）由 AgentApplication 排除全部数据层自动配置，
 * 让应用完全不碰数据库、行为等同现状；本类在 jdbc 模式下手动拉回官方数据层 auto-config：
 * DataSource（读 spring.datasource.*）、JPA/EntityManagerFactory、Flyway（执行 V1__init.sql）。
 * 事务管理器由 HibernateJpaAutoConfiguration 引入的 JPA 事务配置提供。
 *
 * 若 jdbc 模式配了但连接串错误/连不上 → DataSource/Hibernate/Flyway 启动即失败（fail-fast，
 * D6），不做静默降级。migration 类仓库只扫 memory 包（会话持久化相关）。
 */
@Configuration
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
@Import({
        DataSourceAutoConfiguration.class,
        HibernateJpaAutoConfiguration.class,
        FlywayAutoConfiguration.class
})
@EnableJpaRepositories(basePackages = "com.pfagent.agent.memory")
@EnableTransactionManagement
public class JdbcDataConfig {
}
