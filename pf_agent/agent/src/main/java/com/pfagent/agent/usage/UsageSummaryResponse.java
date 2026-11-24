package com.pfagent.agent.usage;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

/**
 * /api/usage/summary 响应（F-009 设计 §5）。
 *
 * token/cost 为 null 表示该范围内没有可汇总数据（usage 缺失或价目缺失），
 * 与 0 区分；missingUsageCount 单独提示缺失的调用次数。
 * forecast 描述本月已用与预测口径，formula 是给前端直接展示的公式说明。
 */
public record UsageSummaryResponse(
        String range,
        String groupBy,
        String scope,
        String timezone,
        String formula,
        Instant from,
        Instant to,
        Totals totals,
        List<Group> groups,
        Forecast forecast) {

    public record Totals(long calls, Long promptTokens, Long completionTokens, Long totalTokens,
                         BigDecimal cost, String currency, long missingUsageCount) {
    }

    public record Group(String key, String label, long calls, Long promptTokens,
                        Long completionTokens, Long totalTokens, BigDecimal cost,
                        long missingUsageCount) {
    }

    /**
     * @param windowDays         日均分母：min(7, 本月已过天数)，无成本日按 0 计入
     * @param dataDays           窗口内实际有成本数据的天数（仅供展示，不参与分母）
     */
    public record Forecast(String timezone, BigDecimal monthToDateCost, BigDecimal dailyAverageCost,
                           int windowDays, int dataDays, int remainingDays,
                           BigDecimal predictedMonthCost, String formula) {
    }
}
