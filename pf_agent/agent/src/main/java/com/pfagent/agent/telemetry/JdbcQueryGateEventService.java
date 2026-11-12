package com.pfagent.agent.telemetry;

import com.pfagent.agent.telemetry.QueryGateEventService.QueryGateEvent;
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;

/**
 * JDBC 查询门禁事件服务（query_gate_event 表写入，F-026 设计 §8.3）
 *
 * 实现 {@link QueryGateEventService} 公共契约，只负责把工具层判定落库：
 * 每次 BLOCKED / ALLOWED 一行，会话/问题来自请求上下文，query_json 存当次参数。
 *
 * 用编程式事务（TransactionTemplate，理由同 JdbcChatMemory/DataGapService：注解事务的
 * 提交期异常在代理层抛出、调用方无法在内部捕获降级）。本类不吞异常：写库失败按契约
 * 以 RuntimeException 抛给 {@code QueryGateEventRecorder}，由它只记 WARN，门禁建议、
 * 拦截、放行和查询主流程继续。
 *
 * 仅在 pf.chat.memory=jdbc 时装配：memory 模式没有 DataSource/仓储 bean，缺少该条件
 * 会让 bean 装配失败；memory 模式下 recorder 取不到服务即视为未装配并降级。
 */
@Component
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
public class JdbcQueryGateEventService implements QueryGateEventService {

    @Autowired
    private QueryGateEventRepository repository;
    @Autowired
    private PlatformTransactionManager transactionManager;

    /** 编程式事务模板（见类注释：为何不用 @Transactional） */
    private TransactionTemplate transactionTemplate;

    @PostConstruct
    private void init() {
        this.transactionTemplate = new TransactionTemplate(transactionManager);
    }

    @Override
    public void persist(QueryGateEvent event) {
        Instant createdAt = event.createdAt() == null ? Instant.now() : event.createdAt();
        transactionTemplate.executeWithoutResult(status -> repository.save(new QueryGateEventEntity(
                event.conversationId(),
                event.question(),
                event.toolName(),
                event.module(),
                event.eventType().name(),
                event.reason().value(),
                event.queryJson(),
                createdAt)));
    }
}
