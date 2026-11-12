package com.pfagent.agent.memory;

import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationVersion;
import org.hibernate.boot.Metadata;
import org.hibernate.boot.MetadataSources;
import org.hibernate.boot.registry.StandardServiceRegistry;
import org.hibernate.boot.registry.StandardServiceRegistryBuilder;
import org.hibernate.cfg.AvailableSettings;
import org.hibernate.tool.schema.spi.ContributableMatcher;
import org.hibernate.tool.schema.spi.ExceptionHandler;
import org.hibernate.tool.schema.spi.ExecutionOptions;
import org.hibernate.tool.schema.spi.SchemaManagementTool;
import org.junit.jupiter.api.Test;
import org.postgresql.ds.PGSimpleDataSource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * V5→V6→V7 迁移与 PostgreSQL 16 真实行为验证（F-020 实施 Spec §6.3）
 *
 * 不用 H2 代替：Flyway 迁移脚本与 JSONB、外键、删号 SET NULL 都是 PG 方言行为。
 * 步骤：先迁移到 V5 写入存量会话/消息/账号 → 再迁移到最新（V6、V7）→ 断言存量数据
 * 不丢失、默认值与回填正确、JSONB 可读写、FK 与 ON DELETE SET NULL 生效，最后用
 * Hibernate SchemaManagementTool 对实体做 validate（等价 ddl-auto=validate）。
 */
@Testcontainers
class PostgresV7MigrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16-alpine");

    private static final String CONVERSATION_ID = "00000000-0000-0000-0000-000000000001";

    @Test
    void upgradesV5ThroughV6ToV7WithBackfillJsonbAndForeignKeys() throws Exception {
        migrate(MigrationVersion.fromVersion("5"));

        long userId;
        try (Connection conn = connect()) {
            try (PreparedStatement ps = conn.prepareStatement(
                    "insert into chat_conversation"
                            + " (id, created_at, last_active_at, message_rounds, total_rounds)"
                            + " values (?, now(), now(), 20, 25)")) {
                ps.setString(1, CONVERSATION_ID);
                ps.executeUpdate();
            }
            try (PreparedStatement ps = conn.prepareStatement(
                    "insert into chat_message (conversation_id, seq, role, content, created_at)"
                            + " values (?, ?, ?, ?, now())")) {
                ps.setString(1, CONVERSATION_ID);
                ps.setInt(2, 1);
                ps.setString(3, "user");
                ps.setString(4, "旧问题");
                ps.executeUpdate();
                ps.setInt(2, 2);
                ps.setString(3, "assistant");
                ps.setString(4, "旧回答");
                ps.executeUpdate();
            }
            userId = insertUser(conn, "legacy-user");
        }

        migrate(MigrationVersion.LATEST);

        try (Connection conn = connect()) {
            assertFlywayHistoryHasV6AndV7(conn);
            assertLegacyConversationBackfilled(conn);
            assertLegacyMessageDefaults(conn);
            assertJsonbRoundTrip(conn);
            assertDeleteUserSetsOwnerNull(conn, userId);
            assertMessageForeignKey(conn);
        }

        validateHibernateSchema();
    }

    private void migrate(MigrationVersion target) {
        Flyway flyway = Flyway.configure()
                .dataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())
                .target(target)
                .load();
        flyway.migrate();
    }

    private static Connection connect() throws SQLException {
        return POSTGRES.createConnection("");
    }

    private static long insertUser(Connection conn, String username) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(
                "insert into user_account (username, password_hash, created_at)"
                        + " values (?, 'x', now()) returning id")) {
            ps.setString(1, username);
            try (ResultSet rs = ps.executeQuery()) {
                rs.next();
                return rs.getLong(1);
            }
        }
    }

    private static void assertFlywayHistoryHasV6AndV7(Connection conn) throws SQLException {
        try (Statement st = conn.createStatement();
             ResultSet rs = st.executeQuery(
                     "select version from flyway_schema_history where success order by installed_rank")) {
            StringBuilder versions = new StringBuilder();
            while (rs.next()) {
                versions.append(rs.getString(1)).append(',');
            }
            assertThat(versions.toString()).contains("6,", "7,");
        }
    }

    private static void assertLegacyConversationBackfilled(Connection conn) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(
                "select generation_attempts, pinned, title, owner_user_id, total_rounds, message_rounds"
                        + " from chat_conversation where id = ?")) {
            ps.setString(1, CONVERSATION_ID);
            try (ResultSet rs = ps.executeQuery()) {
                assertThat(rs.next()).isTrue();
                assertThat(rs.getInt("generation_attempts")).isEqualTo(25);
                assertThat(rs.getBoolean("pinned")).isFalse();
                assertThat(rs.getString("title")).isNull();
                assertThat(rs.getObject("owner_user_id")).isNull();
                assertThat(rs.getInt("total_rounds")).isEqualTo(25);
                assertThat(rs.getInt("message_rounds")).isEqualTo(20);
            }
        }
        // 存量消息不丢失
        try (PreparedStatement ps = conn.prepareStatement(
                "select count(*) from chat_message where conversation_id = ?")) {
            ps.setString(1, CONVERSATION_ID);
            try (ResultSet rs = ps.executeQuery()) {
                rs.next();
                assertThat(rs.getInt(1)).isEqualTo(2);
            }
        }
    }

    private static void assertLegacyMessageDefaults(Connection conn) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(
                "select sources, gap_reported from chat_message where conversation_id = ? order by seq")) {
            ps.setString(1, CONVERSATION_ID);
            try (ResultSet rs = ps.executeQuery()) {
                assertThat(rs.next()).isTrue();
                assertThat(rs.getObject("sources")).isNull();
                assertThat(rs.getBoolean("gap_reported")).isFalse();
                assertThat(rs.next()).isTrue();
                assertThat(rs.getObject("sources")).isNull();
                assertThat(rs.getBoolean("gap_reported")).isFalse();
            }
        }
    }

    private static void assertJsonbRoundTrip(Connection conn) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(
                "update chat_message set sources = ?::jsonb, gap_reported = true"
                        + " where conversation_id = ? and seq = 2")) {
            ps.setString(1, "[{\"book\":\"核心规则书\",\"tocPath\":\"法术 > 火球术\","
                    + "\"chunkId\":\"spell_CRB_0001\",\"content\":\"400 英尺\"}]");
            ps.setString(2, CONVERSATION_ID);
            assertThat(ps.executeUpdate()).isEqualTo(1);
        }
        try (PreparedStatement ps = conn.prepareStatement(
                "select sources->0->>'book', sources->0->>'chunkId', gap_reported"
                        + " from chat_message where conversation_id = ? and seq = 2")) {
            ps.setString(1, CONVERSATION_ID);
            try (ResultSet rs = ps.executeQuery()) {
                rs.next();
                assertThat(rs.getString(1)).isEqualTo("核心规则书");
                assertThat(rs.getString(2)).isEqualTo("spell_CRB_0001");
                assertThat(rs.getBoolean(3)).isTrue();
            }
        }
    }

    private static void assertDeleteUserSetsOwnerNull(Connection conn, long userId) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(
                "update chat_conversation set owner_user_id = ? where id = ?")) {
            ps.setLong(1, userId);
            ps.setString(2, CONVERSATION_ID);
            ps.executeUpdate();
        }
        try (PreparedStatement ps = conn.prepareStatement("delete from user_account where id = ?")) {
            ps.setLong(1, userId);
            ps.executeUpdate();
        }
        try (PreparedStatement ps = conn.prepareStatement(
                "select owner_user_id from chat_conversation where id = ?")) {
            ps.setString(1, CONVERSATION_ID);
            try (ResultSet rs = ps.executeQuery()) {
                rs.next();
                assertThat(rs.getObject("owner_user_id")).isNull();
            }
        }
    }

    private static void assertMessageForeignKey(Connection conn) {
        assertThatThrownBy(() -> {
            try (PreparedStatement ps = conn.prepareStatement(
                    "insert into chat_message (conversation_id, seq, role, content, created_at)"
                            + " values ('no-such-conversation', 1, 'user', 'x', now())")) {
                ps.executeUpdate();
            }
        }).isInstanceOf(SQLException.class);
    }

    /** 等价 ddl-auto=validate：实体注解与 V7 真实 schema 对不上时此处失败 */
    private static void validateHibernateSchema() {
        DataSource dataSource = dataSource();
        StandardServiceRegistry registry = new StandardServiceRegistryBuilder()
                .applySetting(AvailableSettings.DATASOURCE, dataSource)
                .applySetting(AvailableSettings.DIALECT, "org.hibernate.dialect.PostgreSQLDialect")
                .build();
        try {
            Metadata metadata = new MetadataSources(registry)
                    .addAnnotatedClass(ChatConversationEntity.class)
                    .addAnnotatedClass(ChatMessageEntity.class)
                    .buildMetadata();
            ExecutionOptions options = new ExecutionOptions() {
                @Override
                public Map<String, Object> getConfigurationValues() {
                    return Map.of();
                }

                @Override
                public boolean shouldManageNamespaces() {
                    return false;
                }

                @Override
                public ExceptionHandler getExceptionHandler() {
                    return exception -> {
                        throw exception;
                    };
                }
            };
            SchemaManagementTool tool = registry.getService(SchemaManagementTool.class);
            tool.getSchemaValidator(Map.of()).doValidation(metadata, options, ContributableMatcher.ALL);
        } finally {
            StandardServiceRegistryBuilder.destroy(registry);
        }
    }

    private static DataSource dataSource() {
        PGSimpleDataSource ds = new PGSimpleDataSource();
        ds.setUrl(POSTGRES.getJdbcUrl());
        ds.setUser(POSTGRES.getUsername());
        ds.setPassword(POSTGRES.getPassword());
        return ds;
    }
}
