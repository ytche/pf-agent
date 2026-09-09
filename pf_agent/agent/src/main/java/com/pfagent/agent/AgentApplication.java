package com.pfagent.agent;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.data.jpa.JpaRepositoriesAutoConfiguration;
import org.springframework.boot.autoconfigure.flyway.FlywayAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceTransactionManagerAutoConfiguration;
import org.springframework.boot.autoconfigure.orm.jpa.HibernateJpaAutoConfiguration;

@SpringBootApplication(exclude = {
        // SP1（可选数据库）：默认内存模式不碰数据库。不排除时，加了 starter-data-jpa 且 classpath
        // 无嵌入式库（H2 仅 test）会导致未配 datasource 的启动直接失败。
        // jdbc 模式（pf.chat.memory=jdbc）由 JdbcDataConfig 按官方 auto-config 拉回，见该类。
        DataSourceAutoConfiguration.class,
        DataSourceTransactionManagerAutoConfiguration.class,
        HibernateJpaAutoConfiguration.class,
        FlywayAutoConfiguration.class,
        JpaRepositoriesAutoConfiguration.class
})
public class AgentApplication {

    public static void main(String[] args) {
        SpringApplication.run(AgentApplication.class, args);
    }
}
