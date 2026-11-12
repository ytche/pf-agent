package com.pfagent.agent.telemetry;

import org.springframework.data.jpa.repository.JpaRepository;

/**
 * 查询门禁事件仓储（query_gate_event，F-026 设计 §8）
 *
 * 写路径是尽力写入的单行追加（无业务读取需求），故只需 JpaRepository 的默认能力；
 * 分析侧按 created_at / conversation_id 索引直接在 SQL 查询，不在 Java 侧暴露读接口。
 */
public interface QueryGateEventRepository extends JpaRepository<QueryGateEventEntity, Long> {
}
