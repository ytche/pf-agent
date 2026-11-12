package com.pfagent.agent.memory;

import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * JDBC 版 ConversationStore 契约验证（@DataJpaTest + H2，SP7 既有切片的延续）
 *
 * 关闭 Flyway（V1/V7 为 PG 方言），由 Hibernate 按实体注解 create-drop 建表；
 * 真 PostgreSQL 16 的迁移/JSONB/FK/删号 SET NULL 由 PostgresV7MigrationTest 覆盖。
 */
@DataJpaTest(properties = {
        "spring.flyway.enabled=false",
        "spring.jpa.hibernate.ddl-auto=create-drop"})
class JdbcConversationStoreContractTest extends ConversationStoreContractTest {

    @Autowired
    private ChatConversationRepository conversationRepository;
    @Autowired
    private ChatMessageRepository messageRepository;

    @BeforeEach
    void setUp() {
        // 契约测试由 JDBC 实现直接调用仓库（store 手工构造、无 Spring 事务代理），
        // 各用例共享 H2 schema，进入前清表保证用例独立。
        messageRepository.deleteAll();
        conversationRepository.deleteAll();
        JdbcConversationStore jdbc = new JdbcConversationStore();
        ReflectionTestUtils.setField(jdbc, "conversationRepository", conversationRepository);
        ReflectionTestUtils.setField(jdbc, "messageRepository", messageRepository);
        ReflectionTestUtils.setField(jdbc, "historyRounds", 20);
        store = jdbc;
    }
}
