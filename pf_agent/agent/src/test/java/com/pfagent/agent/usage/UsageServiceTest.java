package com.pfagent.agent.usage;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * 用量汇总、时区边界与费用预测：预测 = 本月已用 + 最近 7 个自然日（含今天）
 * 日均 × 今天之后剩余天数；空档日按 0 计入分母，历史不足 7 天按实际天数；
 * 无历史时等于已用。预测的每日查询必须与 totals 使用同一 owner/conversation 过滤。
 */
class UsageServiceTest {

    private static final String ZONE = "Asia/Shanghai";

    /** 2026-11-13 10:00 Asia/Shanghai */
    private static final Instant NOW = Instant.parse("2026-11-13T02:00:00Z");
    /** 2026-11-01 00:00 Asia/Shanghai */
    private static final Instant MONTH_START = Instant.parse("2026-10-31T16:00:00Z");

    private UsageQueryDao dao;
    private UsageService service;

    @BeforeEach
    void setUp() {
        dao = mock(UsageQueryDao.class);
        service = new UsageService(dao, Clock.fixed(NOW, ZoneOffset.UTC), ZONE);
    }

    @Test
    void monthSummaryAggregatesTotalsAndForecastsFromLastSevenDays() {
        when(dao.totals(MONTH_START, NOW, null, null)).thenReturn(
                new UsageQueryDao.Totals(3, 300L, 150L, 450L, money("30"), "CNY", 1));
        when(dao.daily(MONTH_START, NOW, ZONE, null, null)).thenReturn(List.of(
                new UsageQueryDao.DayCost("2026-11-01", money("3")),
                new UsageQueryDao.DayCost("2026-11-02", money("3")),
                new UsageQueryDao.DayCost("2026-11-03", money("3")),
                new UsageQueryDao.DayCost("2026-11-04", money("3")),
                new UsageQueryDao.DayCost("2026-11-05", money("3")),
                new UsageQueryDao.DayCost("2026-11-06", money("3")),
                new UsageQueryDao.DayCost("2026-11-07", money("1")),
                new UsageQueryDao.DayCost("2026-11-08", money("2")),
                new UsageQueryDao.DayCost("2026-11-09", money("3")),
                new UsageQueryDao.DayCost("2026-11-10", null),
                new UsageQueryDao.DayCost("2026-11-11", money("1")),
                new UsageQueryDao.DayCost("2026-11-12", money("2")),
                new UsageQueryDao.DayCost("2026-11-13", money("3"))));

        UsageSummaryResponse summary = service.summarize("month", "day", null, null, "owner");

        assertThat(summary.range()).isEqualTo("month");
        assertThat(summary.groupBy()).isEqualTo("day");
        assertThat(summary.scope()).isEqualTo("owner");
        assertThat(summary.timezone()).isEqualTo(ZONE);
        assertThat(summary.from()).isEqualTo(MONTH_START);
        assertThat(summary.to()).isEqualTo(NOW);
        assertThat(summary.totals().calls()).isEqualTo(3);
        assertThat(summary.totals().promptTokens()).isEqualTo(300L);
        assertThat(summary.totals().cost()).isEqualByComparingTo("30");
        assertThat(summary.totals().missingUsageCount()).isEqualTo(1);

        // 分母固定为最近 7 个自然日（11-07..11-13），11-10 无成本按 0 计入：
        // (1+2+3+0+1+2+3) / 7 = 12/7 = 1.714286/天；剩余 17 天（11-14..11-30）
        assertThat(summary.forecast().windowDays()).isEqualTo(7);
        assertThat(summary.forecast().dataDays()).isEqualTo(6);
        assertThat(summary.forecast().dailyAverageCost()).isEqualByComparingTo("1.714286");
        assertThat(summary.forecast().remainingDays()).isEqualTo(17);
        assertThat(summary.forecast().monthToDateCost()).isEqualByComparingTo("30");
        assertThat(summary.forecast().predictedMonthCost()).isEqualByComparingTo("59.142862");
        assertThat(summary.forecast().formula()).contains("最近 7 个自然日").contains("无成本日按 0 计入");
    }

    @Test
    void forecastWithoutHistoryEqualsMonthToDate() {
        when(dao.totals(MONTH_START, NOW, null, null)).thenReturn(
                new UsageQueryDao.Totals(1, 10L, 5L, 15L, money("12.5"), "CNY", 0));
        when(dao.daily(MONTH_START, NOW, ZONE, null, null)).thenReturn(List.of());

        UsageSummaryResponse summary = service.summarize("month", "day", null, null, "owner");

        assertThat(summary.forecast().dataDays()).isZero();
        assertThat(summary.forecast().windowDays()).isEqualTo(7);
        assertThat(summary.forecast().dailyAverageCost()).isEqualByComparingTo("0");
        assertThat(summary.forecast().predictedMonthCost()).isEqualByComparingTo("12.5");
    }

    /** 窗口内空档日（无记录/无成本）按 0 计入分母，而不是只除以有数据的天数 */
    @Test
    void forecastCountsZeroCostGapDaysInDenominator() {
        when(dao.totals(MONTH_START, NOW, null, null)).thenReturn(
                new UsageQueryDao.Totals(2, 1L, 1L, 2L, money("10"), "CNY", 0));
        when(dao.daily(MONTH_START, NOW, ZONE, null, null)).thenReturn(List.of(
                new UsageQueryDao.DayCost("2026-11-01", money("4")),
                new UsageQueryDao.DayCost("2026-11-12", money("2")),
                new UsageQueryDao.DayCost("2026-11-13", money("4"))));

        UsageSummaryResponse summary = service.summarize("month", "day", null, null, "owner");

        // 11-07..11-11 无记录按 0；(2+4)/7 = 0.857143/天 × 17 = 14.571431，加本月已用 10
        assertThat(summary.forecast().windowDays()).isEqualTo(7);
        assertThat(summary.forecast().dataDays()).isEqualTo(2);
        assertThat(summary.forecast().dailyAverageCost()).isEqualByComparingTo("0.857143");
        assertThat(summary.forecast().predictedMonthCost()).isEqualByComparingTo("24.571431");
    }

    @Test
    void monthBoundaryUsesShanhaiMidnightNotUtc() {
        Instant startOfMonthLocalMidnight = Instant.parse("2026-10-31T16:30:00Z");
        service = new UsageService(dao, Clock.fixed(startOfMonthLocalMidnight, ZoneOffset.UTC), ZONE);
        when(dao.totals(MONTH_START, startOfMonthLocalMidnight, null, null))
                .thenReturn(new UsageQueryDao.Totals(0, null, null, null, null, null, 0));
        when(dao.daily(MONTH_START, startOfMonthLocalMidnight, ZONE, null, null)).thenReturn(List.of());

        service.summarize("month", "day", null, null, "owner");

        verify(dao).totals(eq(MONTH_START), eq(startOfMonthLocalMidnight), isNull(), isNull());
    }

    @Test
    void todayRangeStartsAtLocalMidnight() {
        Instant todayStart = Instant.parse("2026-11-12T16:00:00Z");
        when(dao.totals(todayStart, NOW, null, null)).thenReturn(
                new UsageQueryDao.Totals(1, 1L, 1L, 2L, money("1"), "CNY", 0));
        when(dao.daily(MONTH_START, NOW, ZONE, null, null)).thenReturn(List.of());

        UsageSummaryResponse summary = service.summarize("today", "day", null, null, "owner");

        assertThat(summary.from()).isEqualTo(todayStart);
        verify(dao).totals(eq(todayStart), eq(NOW), isNull(), isNull());
    }

    @Test
    void allRangeHasNoLowerBound() {
        when(dao.totals(null, NOW, null, null)).thenReturn(
                new UsageQueryDao.Totals(0, null, null, null, null, null, 0));
        when(dao.daily(MONTH_START, NOW, ZONE, null, null)).thenReturn(List.of());

        UsageSummaryResponse summary = service.summarize("all", "day", null, null, "global");

        assertThat(summary.from()).isNull();
    }

    @Test
    void ownerAndConversationFiltersArePassedThrough() {
        when(dao.totals(any(), any(), eq(7L), isNull())).thenReturn(
                new UsageQueryDao.Totals(1, 1L, 1L, 2L, money("1"), "CNY", 0));
        when(dao.totals(any(), any(), isNull(), eq("cid-1"))).thenReturn(
                new UsageQueryDao.Totals(1, 1L, 1L, 2L, money("1"), "CNY", 0));
        when(dao.daily(any(), any(), anyString(), any(), any())).thenReturn(List.of());

        service.summarize("month", "day", 7L, null, "owner");
        service.summarize("month", "conversation", null, "cid-1", "conversation");

        verify(dao).totals(eq(MONTH_START), eq(NOW), eq(7L), isNull());
        verify(dao).totals(eq(MONTH_START), eq(NOW), isNull(), eq("cid-1"));
        // 预测的每日查询必须带同样的 owner/conversation 过滤，避免个人预测混入全站费用
        verify(dao).daily(eq(MONTH_START), eq(NOW), eq(ZONE), eq(7L), isNull());
        verify(dao).daily(eq(MONTH_START), eq(NOW), eq(ZONE), isNull(), eq("cid-1"));
    }

    @Test
    void groupByOwnerReturnsPerOwnerGroups() {
        when(dao.totals(any(), any(), isNull(), isNull())).thenReturn(
                new UsageQueryDao.Totals(3, 3L, 3L, 6L, money("6"), "CNY", 0));
        when(dao.daily(any(), any(), anyString(), any(), any())).thenReturn(List.of());
        when(dao.byOwner(MONTH_START, NOW, null, null)).thenReturn(List.of(
                new UsageQueryDao.OwnerBucket(7L, "alice", 2, 2L, 2L, 4L, money("4"), 0),
                new UsageQueryDao.OwnerBucket(null, null, 1, 1L, 1L, 2L, money("2"), 0)));

        UsageSummaryResponse summary = service.summarize("month", "owner", null, null, "global");

        assertThat(summary.groups()).hasSize(2);
        assertThat(summary.groups().get(0).key()).isEqualTo("7");
        assertThat(summary.groups().get(0).label()).isEqualTo("alice");
        assertThat(summary.groups().get(0).cost()).isEqualByComparingTo("4");
        assertThat(summary.groups().get(1).key()).isEqualTo("anonymous");
        assertThat(summary.groups().get(1).label()).isEqualTo("匿名");
    }

    /** 历史不足 7 天（今天 3 号）：分母按实际 3 天 */
    @Test
    void forecastUsesActualDaysWhenMonthHasFewerThanSevenDays() {
        Instant thirdDay = Instant.parse("2026-11-03T02:00:00Z");
        service = new UsageService(dao, Clock.fixed(thirdDay, ZoneOffset.UTC), ZONE);
        when(dao.totals(MONTH_START, thirdDay, null, null)).thenReturn(
                new UsageQueryDao.Totals(2, 1L, 1L, 2L, money("3"), "CNY", 0));
        when(dao.daily(MONTH_START, thirdDay, ZONE, null, null)).thenReturn(List.of(
                new UsageQueryDao.DayCost("2026-11-01", money("1")),
                new UsageQueryDao.DayCost("2026-11-02", null),
                new UsageQueryDao.DayCost("2026-11-03", money("2"))));

        UsageSummaryResponse summary = service.summarize("month", "day", null, null, "owner");

        // (1+0+2)/3 = 1/天，剩余 27 天：3 + 27 = 30
        assertThat(summary.forecast().windowDays()).isEqualTo(3);
        assertThat(summary.forecast().dailyAverageCost()).isEqualByComparingTo("1");
        assertThat(summary.forecast().predictedMonthCost()).isEqualByComparingTo("30");
    }

    /** 管理员 groupBy=owner 且按 ownerId 过滤：groups 与 totals 使用同一过滤条件 */
    @Test
    void ownerGroupsRespectOwnerIdFilterAndMatchTotals() {
        when(dao.totals(MONTH_START, NOW, 7L, null)).thenReturn(
                new UsageQueryDao.Totals(2, 2L, 2L, 4L, money("4"), "CNY", 0));
        when(dao.daily(MONTH_START, NOW, ZONE, 7L, null)).thenReturn(List.of(
                new UsageQueryDao.DayCost("2026-11-13", money("4"))));
        when(dao.byOwner(MONTH_START, NOW, 7L, null)).thenReturn(List.of(
                new UsageQueryDao.OwnerBucket(7L, "alice", 2, 2L, 2L, 4L, money("4"), 0)));

        UsageSummaryResponse summary = service.summarize("month", "owner", 7L, null, "owner");

        assertThat(summary.groups()).hasSize(1);
        BigDecimal groupCost = summary.groups().stream()
                .map(UsageSummaryResponse.Group::cost)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        assertThat(groupCost).isEqualByComparingTo(summary.totals().cost());
        assertThat(summary.forecast().monthToDateCost()).isEqualByComparingTo(summary.totals().cost());
    }

    /** groupBy=owner 与 conversationId 组合：groups 也必须带会话过滤，与 totals 一致 */
    @Test
    void ownerGroupsRespectConversationFilterAndMatchTotals() {
        when(dao.totals(MONTH_START, NOW, null, "cid-1")).thenReturn(
                new UsageQueryDao.Totals(1, 1L, 1L, 2L, money("2"), "CNY", 0));
        when(dao.daily(MONTH_START, NOW, ZONE, null, "cid-1")).thenReturn(List.of(
                new UsageQueryDao.DayCost("2026-11-13", money("2"))));
        when(dao.byOwner(MONTH_START, NOW, null, "cid-1")).thenReturn(List.of(
                new UsageQueryDao.OwnerBucket(7L, "alice", 1, 1L, 1L, 2L, money("2"), 0)));

        UsageSummaryResponse summary = service.summarize("month", "owner", null, "cid-1", "conversation");

        assertThat(summary.groups()).hasSize(1);
        assertThat(summary.groups().get(0).cost()).isEqualByComparingTo(summary.totals().cost());
        verify(dao).byOwner(eq(MONTH_START), eq(NOW), isNull(), eq("cid-1"));
    }

    @Test
    void invalidTimezoneFailsFastAtConstruction() {
        assertThat(org.assertj.core.api.Assertions.catchThrowable(
                () -> new UsageService(dao, Clock.fixed(NOW, ZoneOffset.UTC), "Not/AZone")))
                .isInstanceOf(java.time.DateTimeException.class);
    }

    @Test
    void nullTotalsAreNotCoercedToZero() {
        when(dao.totals(any(), any(), isNull(), isNull())).thenReturn(
                new UsageQueryDao.Totals(2, null, null, null, null, null, 2));
        when(dao.daily(any(), any(), anyString(), any(), any())).thenReturn(List.of());

        UsageSummaryResponse summary = service.summarize("month", "day", null, null, "global");

        assertThat(summary.totals().promptTokens()).isNull();
        assertThat(summary.totals().completionTokens()).isNull();
        assertThat(summary.totals().totalTokens()).isNull();
        assertThat(summary.totals().cost()).isNull();
        assertThat(summary.totals().missingUsageCount()).isEqualTo(2);
        assertThat(summary.forecast().predictedMonthCost()).isNull();
    }

    @Test
    void invalidRangeOrGroupByIsRejected() {
        assertThat(org.assertj.core.api.Assertions.catchThrowable(
                () -> service.summarize("week", "day", null, null, "global")))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(org.assertj.core.api.Assertions.catchThrowable(
                () -> service.summarize("month", "model", null, null, "global")))
                .isInstanceOf(IllegalArgumentException.class);
    }

    private static BigDecimal money(String value) {
        return new BigDecimal(value);
    }
}
