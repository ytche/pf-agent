package com.pfagent.agent.telemetry;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 错误标注服务（error_annotation 表写入，F-021）
 *
 * 只负责持久化：写用编程式事务（TransactionTemplate，理由同 JdbcChatMemory——注解事务的
 * 提交期异常在代理层抛出、调用方无法在内部捕获降级）。记录 ID 由调用方（FeedbackRecorder）
 * 生成并在实体里带上，故写入是「按主键幂等」：同 id 已存在即跳过，迁移导入可重复执行。
 *
 * 仅在 pf.chat.memory=jdbc 时装配：memory 模式没有 DataSource/仓储 bean，
 * 缺少该条件会让 bean 装配失败（memory 模式的行为由调用方 FeedbackRecorder 降级）。
 */
@Component
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
public class ErrorAnnotationService {

    @Autowired
    private ErrorAnnotationRepository repository;
    @Autowired
    private PlatformTransactionManager transactionManager;

    private TransactionTemplate transactionTemplate;

    @PostConstruct
    private void init() {
        this.transactionTemplate = new TransactionTemplate(transactionManager);
    }

    /**
     * 幂等写入一条错误标注
     *
     * @return true = 新插入；false = 该 id 已存在（未新增行）
     */
    public boolean persistIfAbsent(ErrorAnnotationEntity annotation) {
        Boolean inserted = transactionTemplate.execute(status -> {
            if (repository.existsById(annotation.getId())) {
                return false;
            }
            repository.save(annotation);
            return true;
        });
        return Boolean.TRUE.equals(inserted);
    }
}
