package com.pfagent.agent.rag;

import com.pfagent.agent.telemetry.DataGapEntity;
import com.pfagent.agent.telemetry.DataGapService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.List;

/**
 * 数据缺口记录器（设计 §7，F-021 起入库）
 *
 * 检索无结果时 reportDataGap 工具落 data_gap 表一行，供后续脚本/查询分析驱动工具面/数据迭代。
 *
 * 降级（用户拍板 2026-09-24）：DB 不可用（memory 模式）时**不写文件、不谎报成功**——
 * record 返回 false，调用方（RetrievalTools.reportDataGap）据实回话；读取返回
 * {@link GapQueryResult#unavailable()}，「库不可用」与「没有记录」在读取侧也严格区分
 * （旧实现两种情况都回空列表，LLM 会把「查不到库」当成「无重复缺口」）。写库异常同样
 * 返回 false，不再只记日志。
 *
 * 数据库访问收在 {@link DataGapService}（编程式事务 + dedup_key 幂等）；服务 bean 仅在
 * pf.chat.memory=jdbc 时装配，故用 ObjectProvider 取，取不到即 memory 模式。
 */
@Component
public class DataGapRecorder {

    private static final Logger log = LoggerFactory.getLogger(DataGapRecorder.class);

    /** 秒精度 ISO 时间戳（展示/分析口径，对齐旧 JSONL） */
    private static final DateTimeFormatter TIMESTAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

    @Autowired
    private ObjectProvider<DataGapService> gapServiceProvider;

    /**
     * 读取最近的数据缺口记录（只读）
     *
     * 最新在前，命中数达到 limit 即截断（limit 收敛由调用方负责）；keyword 非空时对
     * question/reason 做子串匹配。库不可用/读取异常时返回 {@link GapQueryResult#unavailable()}
     * 而非空列表——缺口读取是辅助通路，不抛异常拖垮主链路，但必须让调用方区分
     * 「查不到库」与「库里没有记录」。
     *
     * @param limit   返回条数上限（调用方已做默认与上限收敛）
     * @param keyword 匹配 question/reason 的子串，可空
     * @return 查询结果（available=false 表示库不可用；available=true 时 gaps 可能为空）
     */
    public GapQueryResult listGaps(int limit, String keyword) {
        DataGapService service = gapServiceProvider.getIfAvailable();
        if (service == null) {
            log.warn("[DataGap] 数据库未装配（pf.chat.memory != jdbc），数据缺口不可读");
            return GapQueryResult.unavailable();
        }
        if (limit <= 0) {
            return GapQueryResult.of(List.of());
        }
        try {
            return GapQueryResult.of(service.list(limit, keyword).stream().map(DataGapRecorder::toEntry).toList());
        } catch (RuntimeException e) {
            log.error("[DataGap] 读取数据缺口失败", e);
            return GapQueryResult.unavailable();
        }
    }

    /** 一条数据缺口记录（读取侧视图：秒精度时间戳 + 问题 + 原因） */
    public record GapEntry(String timestamp, String question, String reason) {
    }

    /**
     * 缺口读取结果：available 区分「库不可用」（false）与「库可用但无记录」（true + 空列表）。
     * 调用方（RetrievalTools.listDataGaps）据此回不同的工具文案，不把库故障说成「暂无记录」。
     */
    public record GapQueryResult(boolean available, List<GapEntry> gaps) {

        /** 库可用（gaps 可能为空列表） */
        public static GapQueryResult of(List<GapEntry> gaps) {
            return new GapQueryResult(true, gaps);
        }

        /** 库不可用（未装配/读取失败）：与「无记录」区分 */
        public static GapQueryResult unavailable() {
            return new GapQueryResult(false, List.of());
        }
    }

    /**
     * 记录一条数据缺口（入库）
     *
     * 同「时间戳（秒）+ 问题 + 过滤条件 + 原因」在库内已有记录时不重复插入（dedup_key 幂等），
     * 但该缺口确实已在库中，故同样返回 true（调用方回话「已记录」属实）。
     *
     * @return true = 已记录（新插入或库内已有同内容记录）；false = 未记录（数据库不可用/写入失败）
     */
    public boolean record(String question, String attemptedFilters, String reason) {
        DataGapService service = gapServiceProvider.getIfAvailable();
        if (service == null) {
            log.warn("[DataGap] 数据库未装配（pf.chat.memory != jdbc），缺口未入库也不落文件: question={}", question);
            return false;
        }
        try {
            service.persist(question, attemptedFilters, reason, Instant.now());
            return true;
        } catch (RuntimeException e) {
            log.error("[DataGap] 数据缺口入库失败: question={}", question, e);
            return false;
        }
    }

    /** 实体行 → 读取侧视图（时间戳格式化为秒精度 ISO，与旧 JSONL 输出口径一致） */
    private static GapEntry toEntry(DataGapEntity gap) {
        return new GapEntry(
                TIMESTAMP.format(gap.getCreatedAt().atZone(ZoneId.systemDefault())),
                gap.getQuestion(),
                gap.getReason());
    }
}
