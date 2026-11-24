package com.pfagent.agent.usage;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

/**
 * 用量明细聚合查询（usage_record，F-009 设计 §5）。
 *
 * 汇总在 SQL 完成：token 的 {@code sum()} 天然排除 null，费用只汇总可计费记录
 * （cost 非空），缺失用量用 {@code count(*) filter (where usage_missing)} 单独计数。
 * 日/月分桶使用数据库侧 {@code timezone(zone, created_at)}，时区由应用配置传入，
 * 避免 JVM 时区差异导致跨日/跨月边界漂移。
 *
 * token/cost 的 null 表示「无可用数据」，与 0 区分：查询结果原样保留 null。
 */
@Repository
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
public class UsageQueryDao {

    /** 区间合计；null 字段 = 该区间没有可汇总的数据 */
    public record Totals(long calls, Long promptTokens, Long completionTokens, Long totalTokens,
                         BigDecimal cost, String currency, long missingUsageCount) {
    }

    /** 普通分组桶（day / conversation） */
    public record Bucket(String key, long calls, Long promptTokens, Long completionTokens,
                         Long totalTokens, BigDecimal cost, long missingUsageCount) {
    }

    /** 按用户分组桶（owner 可能为空 = 匿名会话） */
    public record OwnerBucket(Long ownerId, String username, long calls,
                              Long promptTokens, Long completionTokens, Long totalTokens,
                              BigDecimal cost, long missingUsageCount) {
    }

    /** 某自然日的可计费费用（cost 为 null = 当日无可计费记录） */
    public record DayCost(String day, BigDecimal cost) {
    }

    private final JdbcTemplate jdbc;

    public UsageQueryDao(DataSource dataSource) {
        this.jdbc = new JdbcTemplate(dataSource);
    }

    public Totals totals(Instant from, Instant to, Long ownerId, String conversationId) {
        Filter filter = new Filter().range(from, to).owner(ownerId).conversation(conversationId);
        String sql = "select count(*) as calls,"
                + " sum(prompt_tokens) as prompt_tokens,"
                + " sum(completion_tokens) as completion_tokens,"
                + " sum(total_tokens) as total_tokens,"
                + " sum(cost) as cost,"
                + " min(currency) filter (where cost is not null) as currency,"
                + " count(*) filter (where usage_missing) as missing_usage"
                + " from usage_record" + filter.where();
        return jdbc.queryForObject(sql, (rs, rowNum) -> new Totals(
                rs.getLong("calls"),
                nullableLong(rs, "prompt_tokens"),
                nullableLong(rs, "completion_tokens"),
                nullableLong(rs, "total_tokens"),
                rs.getBigDecimal("cost"),
                rs.getString("currency"),
                rs.getLong("missing_usage")), filter.args().toArray());
    }

    public List<Bucket> byDay(Instant from, Instant to, String zone,
                              Long ownerId, String conversationId) {
        Filter filter = new Filter().range(from, to).owner(ownerId).conversation(conversationId);
        String sql = "select to_char(timezone(?, created_at), 'YYYY-MM-DD') as bucket,"
                + bucketAggregates()
                + " from usage_record" + filter.where()
                + " group by 1 order by 1";
        Object[] args = prepend(zone, filter.args());
        return jdbc.query(sql, (rs, rowNum) -> new Bucket(
                rs.getString("bucket"), rs.getLong("calls"),
                nullableLong(rs, "prompt_tokens"), nullableLong(rs, "completion_tokens"),
                nullableLong(rs, "total_tokens"), rs.getBigDecimal("cost"),
                rs.getLong("missing_usage")), args);
    }

    public List<Bucket> byConversation(Instant from, Instant to, Long ownerId, String conversationId) {
        Filter filter = new Filter().range(from, to).owner(ownerId).conversation(conversationId);
        String sql = "select conversation_id as bucket,"
                + bucketAggregates()
                + " from usage_record" + filter.where()
                + " group by conversation_id order by 1";
        return jdbc.query(sql, (rs, rowNum) -> new Bucket(
                rs.getString("bucket"), rs.getLong("calls"),
                nullableLong(rs, "prompt_tokens"), nullableLong(rs, "completion_tokens"),
                nullableLong(rs, "total_tokens"), rs.getBigDecimal("cost"),
                rs.getLong("missing_usage")), filter.args().toArray());
    }

    public List<OwnerBucket> byOwner(Instant from, Instant to, Long ownerId, String conversationId) {
        Filter filter = new Filter().range(from, to).owner(ownerId).conversation(conversationId);
        String sql = "select u.owner_id as bucket_id, a.username as username,"
                + bucketAggregates()
                + " from usage_record u left join user_account a on a.id = u.owner_id"
                + filter.where().replace("created_at", "u.created_at")
                + " group by u.owner_id, a.username order by sum(u.cost) desc nulls last, u.owner_id";
        return jdbc.query(sql, (rs, rowNum) -> new OwnerBucket(
                nullableLong(rs, "bucket_id"), rs.getString("username"), rs.getLong("calls"),
                nullableLong(rs, "prompt_tokens"), nullableLong(rs, "completion_tokens"),
                nullableLong(rs, "total_tokens"), rs.getBigDecimal("cost"),
                rs.getLong("missing_usage")), filter.args().toArray());
    }

    public List<DayCost> daily(Instant from, Instant to, String zone,
                              Long ownerId, String conversationId) {
        Filter filter = new Filter().range(from, to).owner(ownerId).conversation(conversationId);
        String sql = "select to_char(timezone(?, created_at), 'YYYY-MM-DD') as day, sum(cost) as cost"
                + " from usage_record" + filter.where() + " group by 1 order by 1";
        Object[] args = prepend(zone, filter.args());
        return jdbc.query(sql, (rs, rowNum) ->
                new DayCost(rs.getString("day"), rs.getBigDecimal("cost")), args);
    }

    /** 各分组共用的聚合列（列名与 Totals 一致，便于同一套 RowMapper 读取） */
    private static String bucketAggregates() {
        return " count(*) as calls,"
                + " sum(prompt_tokens) as prompt_tokens,"
                + " sum(completion_tokens) as completion_tokens,"
                + " sum(total_tokens) as total_tokens,"
                + " sum(cost) as cost,"
                + " count(*) filter (where usage_missing) as missing_usage";
    }

    private static Long nullableLong(ResultSet rs, String column) throws SQLException {
        Object value = rs.getObject(column);
        return value == null ? null : ((Number) value).longValue();
    }

    private static Object[] prepend(Object first, List<Object> rest) {
        List<Object> args = new ArrayList<>(rest.size() + 1);
        args.add(first);
        args.addAll(rest);
        return args.toArray();
    }

    /** 动态 where 构造：区间必带 to，from/owner/conversation 可选 */
    private static final class Filter {
        private final StringBuilder where = new StringBuilder(" where created_at < ?");
        private final List<Object> args = new ArrayList<>();

        private Filter() {
        }

        Filter range(Instant from, Instant to) {
            if (from == null) {
                args.add(timestamp(to));
                return this;
            }
            where.setLength(0);
            where.append(" where created_at >= ? and created_at < ?");
            args.add(timestamp(from));
            args.add(timestamp(to));
            return this;
        }

        /** 以 UTC OffsetDateTime 绑定 timestamptz：不依赖 JVM 默认时区，避免与 DB 时区漂移 */
        private static OffsetDateTime timestamp(Instant instant) {
            return OffsetDateTime.ofInstant(instant, ZoneOffset.UTC);
        }

        Filter owner(Long ownerId) {
            if (ownerId != null) {
                where.append(" and owner_id = ?");
                args.add(ownerId);
            }
            return this;
        }

        Filter conversation(String conversationId) {
            if (conversationId != null && !conversationId.isBlank()) {
                where.append(" and conversation_id = ?");
                args.add(conversationId);
            }
            return this;
        }

        String where() {
            return where.toString();
        }

        List<Object> args() {
            return args;
        }
    }
}
