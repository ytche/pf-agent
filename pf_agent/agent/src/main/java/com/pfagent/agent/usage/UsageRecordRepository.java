package com.pfagent.agent.usage;

import org.springframework.data.jpa.repository.JpaRepository;

/**
 * 用量明细仓储（usage_record，F-009）。
 *
 * 写路径是尽力写入的单行追加；读路径是聚合查询，走 {@link UsageQueryDao} 的原生 SQL，
 * 不在 JPA 里表达按应用时区分桶的聚合。
 */
public interface UsageRecordRepository extends JpaRepository<UsageRecordEntity, Long> {
}
