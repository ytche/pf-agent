package com.pfagent.agent.usage;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * 用量汇总与费用预测（F-009 设计 §5）。
 *
 * 日/月边界固定按应用时区（默认 Asia/Shanghai）换算，接口返回该时区；
 * 预测 = 本月已用 + 最近 7 个自然日（含今天）日均 × 今天之后剩余天数。
 * 日均分母为 min(7, 本月已过天数)：窗口内无成本日按 0 计入，历史不足 7 天按实际天数；
 * 无历史时预测值等于本月已用。时区在构造期解析，配置非法时启动即失败。
 *
 * 聚合 SQL 在 {@link UsageQueryDao}；本类只做边界换算、预测与分组标签，
 * 不把 null（无数据）折算成 0。
 */
@Service
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
public class UsageService {

    /** 仅用于页面说明，接口原样返回 */
    public static final String FORECAST_FORMULA =
            "预测 = 本月已用 + 最近 7 个自然日（含今天）日均 × 今天之后剩余天数；"
                    + "无成本日按 0 计入，历史不足 7 天按实际天数，无历史时等于本月已用";

    private static final Set<String> RANGES = Set.of("today", "month", "all");
    private static final Set<String> GROUPS = Set.of("day", "conversation", "owner");
    private static final int FORECAST_WINDOW_DAYS = 7;
    private static final int COST_SCALE = 6;

    private final UsageQueryDao queryDao;
    private final Clock clock;
    private final String timezone;
    private final ZoneId zone;

    public UsageService(UsageQueryDao queryDao, Clock clock,
                        @Value("${pf.usage.timezone:Asia/Shanghai}") String timezone) {
        this.queryDao = queryDao;
        this.clock = clock;
        this.timezone = timezone;
        // fail-fast：非法时区在启动装配期暴露，而不是等到第一次查询
        this.zone = ZoneId.of(timezone);
    }

    /**
     * @param range          today | month | all
     * @param groupBy        day | conversation | owner
     * @param ownerId        已由调用方按权限确定的用户过滤（null = 不按用户过滤）
     * @param conversationId 已由调用方校验可读的会话过滤（null = 不按会话过滤）
     * @param scope          调用方权限范围：global / owner / conversation
     */
    public UsageSummaryResponse summarize(String range, String groupBy, Long ownerId,
                                          String conversationId, String scope) {
        if (!RANGES.contains(range)) {
            throw new IllegalArgumentException("range 仅支持 today|month|all");
        }
        if (!GROUPS.contains(groupBy)) {
            throw new IllegalArgumentException("groupBy 仅支持 day|conversation|owner");
        }

        Instant now = clock.instant();
        ZonedDateTime localNow = ZonedDateTime.ofInstant(now, zone);
        LocalDate today = localNow.toLocalDate();
        Instant monthStart = today.withDayOfMonth(1).atStartOfDay(zone).toInstant();
        Instant rangeFrom = switch (range) {
            case "today" -> today.atStartOfDay(zone).toInstant();
            case "month" -> monthStart;
            default -> null;
        };

        UsageQueryDao.Totals totals = queryDao.totals(rangeFrom, now, ownerId, conversationId);
        List<UsageSummaryResponse.Group> groups = switch (groupBy) {
            case "day" -> dayGroups(rangeFrom, now, zone, ownerId, conversationId);
            case "conversation" -> conversationGroups(rangeFrom, now, ownerId, conversationId);
            default -> ownerGroups(rangeFrom, now, ownerId, conversationId);
        };

        return new UsageSummaryResponse(range, groupBy, scope, timezone, FORECAST_FORMULA,
                rangeFrom, now, toResponseTotals(totals), groups,
                forecast(monthStart, now, today, zone, totals, range, ownerId, conversationId));
    }

    private List<UsageSummaryResponse.Group> dayGroups(Instant from, Instant to, ZoneId zone,
                                                       Long ownerId, String conversationId) {
        List<UsageSummaryResponse.Group> groups = new ArrayList<>();
        for (UsageQueryDao.Bucket bucket : queryDao.byDay(from, to, zone.getId(), ownerId, conversationId)) {
            String key = bucket.key() == null ? "unknown" : bucket.key();
            groups.add(new UsageSummaryResponse.Group(key, key, bucket.calls(),
                    bucket.promptTokens(), bucket.completionTokens(), bucket.totalTokens(),
                    bucket.cost(), bucket.missingUsageCount()));
        }
        return groups;
    }

    private List<UsageSummaryResponse.Group> conversationGroups(Instant from, Instant to,
                                                                Long ownerId, String conversationId) {
        List<UsageSummaryResponse.Group> groups = new ArrayList<>();
        for (UsageQueryDao.Bucket bucket : queryDao.byConversation(from, to, ownerId, conversationId)) {
            String key = bucket.key() == null ? "unknown" : bucket.key();
            String label = bucket.key() == null ? "未知会话" : bucket.key();
            groups.add(new UsageSummaryResponse.Group(key, label, bucket.calls(),
                    bucket.promptTokens(), bucket.completionTokens(), bucket.totalTokens(),
                    bucket.cost(), bucket.missingUsageCount()));
        }
        return groups;
    }

    private List<UsageSummaryResponse.Group> ownerGroups(Instant from, Instant to, Long ownerId,
                                                          String conversationId) {
        List<UsageSummaryResponse.Group> groups = new ArrayList<>();
        for (UsageQueryDao.OwnerBucket bucket : queryDao.byOwner(from, to, ownerId, conversationId)) {
            String key = bucket.ownerId() == null ? "anonymous" : String.valueOf(bucket.ownerId());
            String label;
            if (bucket.ownerId() == null) {
                label = "匿名";
            } else {
                label = bucket.username() == null || bucket.username().isBlank()
                        ? "用户 #" + bucket.ownerId()
                        : bucket.username();
            }
            groups.add(new UsageSummaryResponse.Group(key, label, bucket.calls(),
                    bucket.promptTokens(), bucket.completionTokens(), bucket.totalTokens(),
                    bucket.cost(), bucket.missingUsageCount()));
        }
        return groups;
    }

    /**
     * 本月预测：以当月的每日费用（含空档日）推导本月已用、最近 7 天日均和剩余天数。
     *
     * 日均分母 = min(7, 本月已过天数)：最近 7 个自然日里没有成本的日子按 0 计入，
     * 只有历史不足 7 天（今天在 1～6 号）时才按实际天数；无历史时预测值等于本月已用。
     * 每日查询与 totals 使用相同的 owner/conversation 过滤，个人/匿名预测不会混入他人费用。
     */
    private UsageSummaryResponse.Forecast forecast(Instant monthStart, Instant now, LocalDate today,
                                                   ZoneId zone, UsageQueryDao.Totals totals,
                                                   String range, Long ownerId, String conversationId) {
        List<UsageQueryDao.DayCost> days =
                queryDao.daily(monthStart, now, zone.getId(), ownerId, conversationId);
        BigDecimal monthCost = null;
        boolean anyBillableDay = false;
        for (UsageQueryDao.DayCost day : days) {
            if (day.cost() != null) {
                anyBillableDay = true;
                monthCost = monthCost == null ? day.cost() : monthCost.add(day.cost());
            }
        }
        if (!anyBillableDay && "month".equals(range)) {
            monthCost = totals.cost();
        }

        int windowDays = Math.min(FORECAST_WINDOW_DAYS, today.getDayOfMonth());
        LocalDate windowStart = today.minusDays(windowDays - 1L);
        BigDecimal windowCost = null;
        int dataDays = 0;
        for (UsageQueryDao.DayCost day : days) {
            if (day.cost() == null || day.day() == null) {
                continue;
            }
            LocalDate date;
            try {
                date = LocalDate.parse(day.day());
            } catch (RuntimeException e) {
                continue;
            }
            if (date.isBefore(windowStart) || date.isAfter(today)) {
                continue;
            }
            windowCost = windowCost == null ? day.cost() : windowCost.add(day.cost());
            dataDays++;
        }

        BigDecimal dailyAverage = monthCost == null ? null
                : (windowCost == null ? BigDecimal.ZERO : windowCost)
                        .divide(BigDecimal.valueOf(windowDays), COST_SCALE, RoundingMode.HALF_UP);
        int remainingDays = today.lengthOfMonth() - today.getDayOfMonth();
        BigDecimal predicted = monthCost == null || dailyAverage == null ? monthCost
                : monthCost.add(dailyAverage.multiply(BigDecimal.valueOf(remainingDays)));

        return new UsageSummaryResponse.Forecast(timezone, monthCost, dailyAverage, windowDays,
                dataDays, remainingDays, predicted, FORECAST_FORMULA);
    }

    private static UsageSummaryResponse.Totals toResponseTotals(UsageQueryDao.Totals totals) {
        return new UsageSummaryResponse.Totals(totals.calls(), totals.promptTokens(),
                totals.completionTokens(), totals.totalTokens(), totals.cost(),
                totals.currency(), totals.missingUsageCount());
    }
}
