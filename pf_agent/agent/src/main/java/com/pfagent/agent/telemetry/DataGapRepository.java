package com.pfagent.agent.telemetry;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

/**
 * 数据缺口仓储（data_gap，F-021）
 *
 * dedup_key 唯一约束是幂等写入/迁移的落点（先 existsByDedupKey 查再插，单机写路径无并发压力）。
 * 读取按 created_at 倒序（最新在前），同秒并列时以 id 倒序稳定排序——迁移导入按文件顺序
 * 递增 id，故与旧 JSONL「追加顺序即时间顺序」的读取口径一致。
 */
public interface DataGapRepository extends JpaRepository<DataGapEntity, Long> {

    /** 去重键是否已存在（写库与迁移导入的幂等判据） */
    boolean existsByDedupKey(String dedupKey);

    /** 最新在前的缺口记录（keyword 为空时用，limit 由 Pageable 承载） */
    List<DataGapEntity> findByOrderByCreatedAtDescIdDesc(Pageable pageable);

    /** keyword 对 question/reason 子串匹配后最新在前（like 对 null 列不命中，与原文件口径一致） */
    @Query("select g from DataGapEntity g "
            + "where g.question like concat('%', :keyword, '%') or g.reason like concat('%', :keyword, '%') "
            + "order by g.createdAt desc, g.id desc")
    List<DataGapEntity> searchByKeyword(@Param("keyword") String keyword, Pageable pageable);
}
