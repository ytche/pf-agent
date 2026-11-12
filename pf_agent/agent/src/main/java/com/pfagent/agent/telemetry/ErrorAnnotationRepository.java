package com.pfagent.agent.telemetry;

import org.springframework.data.jpa.repository.JpaRepository;

/**
 * 错误标注仓储（error_annotation，F-021）
 *
 * 主键即记录 ID（ann- 前缀，应用层生成），无业务查询：Java 侧只写不读，
 * 分析读取由 qa/annotations_report.py 直连库完成。
 */
public interface ErrorAnnotationRepository extends JpaRepository<ErrorAnnotationEntity, String> {
}
