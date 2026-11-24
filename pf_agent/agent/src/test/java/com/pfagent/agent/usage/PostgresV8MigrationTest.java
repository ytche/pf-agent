package com.pfagent.agent.usage;

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
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * V8 usage_record 迁移在 PostgreSQL 16 上的真实行为（不用 H2 代替）。
 *
 * 验证：表与字段齐全、不可空/可空口径正确、usage 缺失不写 0、三个查询索引存在、
 * Hibernate 实体校验通过（等价 ddl-auto=validate），并用 {@link UsageQueryDao}
 * 的真实 SQL 核对聚合（token 求和排除 null、费用只汇总可计费记录）。
 */
@Testcontainers
class PostgresV8MigrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16-alpine");

    private static final Instant T0 = Instant.parse("2026-11-01T00:00:00Z");

    @Test
    void v8CreatesUsageRecordSchemaIndexesAndAggregates() throws Exception {
        migrate();

        try (Connection conn = connect()) {
            assertFlywayHistoryHasV8(conn);
            assertColumns(conn);
            assertUsageRowsPersist(conn);
        }

        assertUniqueAndCheckConstraints();
        assertDaoAggregates();
        assertServiceForecastScopedToOwnerAndConversation();
        validateHibernateSchema();
    }

    private static final String CID_OTHER = "00000000-0000-0000-0000-000000000003";

    private void migrate() {
        Flyway flyway = Flyway.configure()
                .dataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())
                .target(MigrationVersion.LATEST)
                .load();
        flyway.migrate();
    }

    private static Connection connect() throws SQLException {
        return POSTGRES.createConnection("");
    }

    private static void assertFlywayHistoryHasV8(Connection conn) throws SQLException {
        try (Statement st = conn.createStatement();
             ResultSet rs = st.executeQuery(
                     "select version from flyway_schema_history where success order by installed_rank")) {
            StringBuilder versions = new StringBuilder();
            while (rs.next()) {
                versions.append(rs.getString(1)).append(',');
            }
            assertThat(versions.toString()).contains("8,");
        }
    }

    private static void assertColumns(Connection conn) throws SQLException {
        Map<String, String> columns = new java.util.LinkedHashMap<>();
        try (PreparedStatement ps = conn.prepareStatement(
                "select column_name, is_nullable from information_schema.columns"
                        + " where table_name = 'usage_record'")) {
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    columns.put(rs.getString(1), rs.getString(2));
                }
            }
        }
        assertThat(columns).containsKeys(
                "id", "request_id", "call_seq", "conversation_id", "owner_id", "purpose", "model",
                "prompt_tokens", "completion_tokens", "total_tokens", "usage_missing",
                "prompt_price_per_million", "completion_price_per_million", "cost", "currency",
                "duration_ms", "created_at");
        assertThat(columns.get("prompt_tokens")).isEqualTo("YES");
        assertThat(columns.get("completion_tokens")).isEqualTo("YES");
        assertThat(columns.get("total_tokens")).isEqualTo("YES");
        assertThat(columns.get("cost")).isEqualTo("YES");
        assertThat(columns.get("owner_id")).isEqualTo("YES");
        assertThat(columns.get("conversation_id")).isEqualTo("YES");
        assertThat(columns.get("request_id")).isEqualTo("NO");
        assertThat(columns.get("usage_missing")).isEqualTo("NO");
        assertThat(columns.get("created_at")).isEqualTo("NO");

        List<String> indexes = new JdbcTemplate(dataSource()).queryForList(
                "select indexname from pg_indexes where tablename = 'usage_record'", String.class);
        assertThat(indexes).contains(
                "idx_usage_record_created_at",
                "idx_usage_record_request_id",
                "idx_usage_record_conversation_id",
                "idx_usage_record_owner_id");
    }

    /** (request_id, call_seq) 唯一 + call_seq >= 1：同一请求内序号不得重复或从 0 开始 */
    private static void assertUniqueAndCheckConstraints() {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource());
        String indexDef = jdbc.queryForObject(
                "select indexdef from pg_indexes where indexname = 'idx_usage_record_request_id'",
                String.class);
        assertThat(indexDef).containsIgnoringCase("unique");
        Integer checks = jdbc.queryForObject(
                "select count(*) from pg_constraint where conname = 'ck_usage_record_call_seq'",
                Integer.class);
        assertThat(checks).isEqualTo(1);

        String duplicateSql = "insert into usage_record (request_id, call_seq, purpose, model,"
                + " usage_missing, currency, duration_ms, created_at)"
                + " values (?, ?, 'agent', 'deepseek-chat', true, 'CNY', 0, ?)";
        assertThatThrownBy(() -> jdbc.update(duplicateSql, "req-1", 1,
                utc(T0.plusSeconds(30))))
                .isInstanceOf(org.springframework.dao.DuplicateKeyException.class);
        assertThatThrownBy(() -> jdbc.update(duplicateSql, "req-check", 0,
                utc(T0.plusSeconds(30))))
                .isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);
    }

    private static java.time.OffsetDateTime utc(Instant instant) {
        return java.time.OffsetDateTime.ofInstant(instant, ZoneOffset.UTC);
    }

    private static void assertUsageRowsPersist(Connection conn) throws SQLException {
        String sql = "insert into usage_record (request_id, call_seq, conversation_id, owner_id,"
                + " purpose, model, prompt_tokens, completion_tokens, total_tokens, usage_missing,"
                + " prompt_price_per_million, completion_price_per_million, cost, currency,"
                + " duration_ms, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            // 完整用量：token 与费用齐全
            bind(ps, "req-1", 1, "cid-1", 7L, "agent", 100, 50, 150, false,
                    "2.0", "8.0", "0.0006", 120, T0);
            ps.executeUpdate();
            // 工具轮第二次调用：同 request_id 不同 call_seq
            bind(ps, "req-1", 2, "cid-1", 7L, "agent", 20, 10, 30, false,
                    "2.0", "8.0", "0.00012", 80, T0.plusSeconds(3));
            ps.executeUpdate();
            // 另一用户 + 另一会话：用于验证预测/聚合的 owner 与 conversation 过滤
            bind(ps, "req-3", 1, CID_OTHER, 8L, "agent", 10, 5, 15, false,
                    "2.0", "8.0", "0.00006", 30, T0.plusSeconds(20));
            ps.executeUpdate();
            bind(ps, "req-3", 2, CID_OTHER, 8L, "agent", 10, 0, 10, false,
                    "2.0", "8.0", "0.00002", 15, T0.plusSeconds(25));
            ps.executeUpdate();
            // usage 缺失：token/cost 必须为 null，不得写 0
            try (PreparedStatement missing = conn.prepareStatement(sql)) {
                missing.setString(1, "req-2");
                missing.setInt(2, 1);
                missing.setString(3, CID_ANON);
                missing.setNull(4, java.sql.Types.BIGINT);
                missing.setString(5, "force_answer");
                missing.setString(6, "deepseek-chat");
                for (int i = 7; i <= 13; i++) {
                    missing.setNull(i, i == 10 ? java.sql.Types.BOOLEAN : java.sql.Types.NUMERIC);
                }
                // 10 是 usage_missing（非空）
                missing.setBoolean(10, true);
                missing.setString(14, "CNY");
                missing.setLong(15, 5);
                missing.setTimestamp(16, Timestamp.from(T0.plusSeconds(10)));
                missing.executeUpdate();
            }
        }

        try (PreparedStatement ps = conn.prepareStatement(
                "select prompt_tokens, cost from usage_record where request_id = 'req-2'")) {
            try (ResultSet rs = ps.executeQuery()) {
                assertThat(rs.next()).isTrue();
                assertThat(rs.getObject("prompt_tokens")).isNull();
                assertThat(rs.getObject("cost")).isNull();
            }
        }
    }

    private static void bind(PreparedStatement ps, String requestId, int seq, String cid, Long ownerId,
                             String purpose, int prompt, int completion, int total, boolean missing,
                             String promptPrice, String completionPrice, String cost, long durationMs,
                             Instant createdAt) throws SQLException {
        ps.setString(1, requestId);
        ps.setInt(2, seq);
        ps.setString(3, cid);
        ps.setLong(4, ownerId);
        ps.setString(5, purpose);
        ps.setString(6, "deepseek-chat");
        ps.setInt(7, prompt);
        ps.setInt(8, completion);
        ps.setInt(9, total);
        ps.setBoolean(10, missing);
        ps.setBigDecimal(11, new BigDecimal(promptPrice));
        ps.setBigDecimal(12, new BigDecimal(completionPrice));
        ps.setBigDecimal(13, new BigDecimal(cost));
        ps.setString(14, "CNY");
        ps.setLong(15, durationMs);
        ps.setTimestamp(16, Timestamp.from(createdAt));
    }

    /** 真实 SQL 聚合：token 求和排除 null，费用只汇总可计费记录，缺失计数单列 */
    private static void assertDaoAggregates() {
        UsageQueryDao dao = new UsageQueryDao(dataSource());

        UsageQueryDao.Totals totals = dao.totals(null, T0.plusSeconds(60), null, null);
        assertThat(totals.calls()).isEqualTo(5);
        assertThat(totals.promptTokens()).isEqualTo(140L);
        assertThat(totals.completionTokens()).isEqualTo(65L);
        assertThat(totals.totalTokens()).isEqualTo(205L);
        assertThat(totals.cost()).isEqualByComparingTo("0.0008");
        assertThat(totals.missingUsageCount()).isEqualTo(1);

        UsageQueryDao.Totals conversation = dao.totals(null, T0.plusSeconds(60), null, CID_ANON);
        assertThat(conversation.calls()).isEqualTo(1);
        assertThat(conversation.cost()).isNull();

        List<UsageQueryDao.Bucket> byConversation = dao.byConversation(null, T0.plusSeconds(60), null, null);
        assertThat(byConversation).extracting(UsageQueryDao.Bucket::key)
                .containsExactlyInAnyOrder("cid-1", CID_ANON, CID_OTHER);

        // 按应用时区分桶：2026-11-01 00:00 UTC = 上海 08:00，仍属同一天
        List<UsageQueryDao.Bucket> byDay = dao.byDay(null, T0.plusSeconds(60), "Asia/Shanghai", null, null);
        assertThat(byDay).hasSize(1);
        assertThat(byDay.get(0).key()).isEqualTo("2026-11-01");
        assertThat(byDay.get(0).calls()).isEqualTo(5);

        // 按 owner 聚合：7 号用户可计费 0.00072，匿名行 cost 为 null 且仍计入调用次数
        List<UsageQueryDao.OwnerBucket> byOwner = dao.byOwner(null, T0.plusSeconds(60), null, null);
        assertThat(byOwner).hasSize(3);
        assertThat(byOwner).anySatisfy(bucket -> {
            assertThat(bucket.ownerId()).isEqualTo(7L);
            assertThat(bucket.cost()).isEqualByComparingTo("0.00072");
            assertThat(bucket.calls()).isEqualTo(2);
        });
        assertThat(byOwner).anySatisfy(bucket -> {
            assertThat(bucket.ownerId()).isEqualTo(8L);
            assertThat(bucket.cost()).isEqualByComparingTo("0.00008");
            assertThat(bucket.calls()).isEqualTo(2);
        });
        assertThat(byOwner).anySatisfy(bucket -> {
            assertThat(bucket.ownerId()).isNull();
            assertThat(bucket.cost()).isNull();
            assertThat(bucket.missingUsageCount()).isEqualTo(1);
        });

        // ownerId 过滤：管理员按用户查看时 groups 与 totals 同口径
        List<UsageQueryDao.OwnerBucket> only7 = dao.byOwner(null, T0.plusSeconds(60), 7L, null);
        assertThat(only7).hasSize(1);
        assertThat(only7.get(0).ownerId()).isEqualTo(7L);
        assertThat(only7.get(0).cost()).isEqualByComparingTo("0.00072");
    }

    /**
     * P0 权限证据：预测的每日查询使用与 totals 相同的 owner/conversation 过滤。
     * 固定时钟为 2026-11-01 上海时间，当月区间覆盖 T0 的全部数据。
     */
    private static void assertServiceForecastScopedToOwnerAndConversation() {
        UsageQueryDao dao = new UsageQueryDao(dataSource());
        Clock clock = Clock.fixed(T0.plusSeconds(300), ZoneOffset.UTC);
        UsageService service = new UsageService(dao, clock, "Asia/Shanghai");

        UsageSummaryResponse owner7 = service.summarize("month", "day", 7L, null, "owner");
        assertThat(owner7.totals().calls()).isEqualTo(2);
        assertThat(owner7.totals().cost()).isEqualByComparingTo("0.00072");
        // 个人预测只能基于自己的费用：本月已用 == 个人 totals.cost
        assertThat(owner7.forecast().monthToDateCost()).isEqualByComparingTo(owner7.totals().cost());

        UsageSummaryResponse owner8 = service.summarize("month", "day", 8L, null, "owner");
        assertThat(owner8.totals().calls()).isEqualTo(2);
        assertThat(owner8.forecast().monthToDateCost()).isEqualByComparingTo(owner8.totals().cost());

        UsageSummaryResponse anonymous = service.summarize("month", "day", null, CID_ANON, "conversation");
        assertThat(anonymous.totals().calls()).isEqualTo(1);
        assertThat(anonymous.totals().cost()).isNull();
        // 匿名只含当前会话：缺失用量不折算成 0，预测等于该会话已用（同为 null）
        assertThat(anonymous.forecast().monthToDateCost()).isNull();
        assertThat(anonymous.forecast().predictedMonthCost()).isNull();
    }

    private static void validateHibernateSchema() {
        DataSource dataSource = dataSource();
        StandardServiceRegistry registry = new StandardServiceRegistryBuilder()
                .applySetting(AvailableSettings.DATASOURCE, dataSource)
                .applySetting(AvailableSettings.DIALECT, "org.hibernate.dialect.PostgreSQLDialect")
                .build();
        try {
            Metadata metadata = new MetadataSources(registry)
                    .addAnnotatedClass(UsageRecordEntity.class)
                    .buildMetadata();
            ExceptionHandler handler = exception -> {
                throw exception;
            };
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
                    return handler;
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

    private static final String CID_ANON = "00000000-0000-0000-0000-000000000002";
}
