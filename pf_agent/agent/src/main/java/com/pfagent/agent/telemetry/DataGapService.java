package com.pfagent.agent.telemetry;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.List;

/**
 * 数据缺口服务（data_gap 表读写，F-021）
 *
 * 只负责持久化：写用编程式事务（TransactionTemplate，理由同 JdbcChatMemory——注解事务的
 * 提交期异常在代理层抛出、调用方无法在内部捕获降级），读用仓储默认只读事务。
 *
 * 幂等（dedup_key 唯一）：同一「时间戳（秒精度）+ question + attemptedFilters + reason」
 * 只落一行。时间戳取秒精度是为了与旧 JSONL 写入口径一致（同秒同内容视为同一缺口），
 * 也让迁移导入可重复执行不产生重复行。
 *
 * 仅在 pf.chat.memory=jdbc 时装配：memory 模式没有 DataSource/仓储 bean，
 * 缺少该条件会让 bean 装配失败（memory 模式的行为由调用方 DataGapRecorder 降级）。
 */
@Component
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
public class DataGapService {

    /** 秒精度 ISO 时间戳（去重键与展示口径都以此为准，对齐旧 JSONL） */
    private static final DateTimeFormatter TIMESTAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

    @Autowired
    private DataGapRepository repository;
    @Autowired
    private PlatformTransactionManager transactionManager;

    private TransactionTemplate transactionTemplate;

    @PostConstruct
    private void init() {
        this.transactionTemplate = new TransactionTemplate(transactionManager);
    }

    /**
     * 幂等写入一条数据缺口
     *
     * @return true = 新插入；false = 同内容同秒的重复（库内已有，未新增行）
     */
    public boolean persist(String question, String attemptedFilters, String reason, Instant createdAt) {
        String dedupKey = dedupKey(createdAt, question, attemptedFilters, reason);
        Boolean inserted = transactionTemplate.execute(status -> {
            if (repository.existsByDedupKey(dedupKey)) {
                return false;
            }
            repository.save(new DataGapEntity(dedupKey, question, attemptedFilters, reason, createdAt));
            return true;
        });
        return Boolean.TRUE.equals(inserted);
    }

    /**
     * 读取最新在前的缺口记录（limit 收敛由调用方负责）
     *
     * @param keyword 对 question/reason 子串匹配，空/空白 = 不过滤
     */
    public List<DataGapEntity> list(int limit, String keyword) {
        if (limit <= 0) {
            return List.of();
        }
        Pageable page = PageRequest.of(0, limit);
        return keyword == null || keyword.isBlank()
                ? repository.findByOrderByCreatedAtDescIdDesc(page)
                : repository.searchByKeyword(keyword, page);
    }

    /**
     * 去重键：秒精度本地时间戳 + question/attemptedFilters/reason 的 SHA-256。
     * 时间戳按系统时区格式化——与旧 JSONL 的 LocalDateTime 写入口径一致。
     */
    private static String dedupKey(Instant createdAt, String question, String attemptedFilters, String reason) {
        String timestamp = TIMESTAMP.format(createdAt.atZone(ZoneId.systemDefault()));
        return TelemetryDigest.sha256Hex(timestamp, question, attemptedFilters, reason);
    }
}
