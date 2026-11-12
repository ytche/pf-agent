package com.pfagent.agent.rag;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pfagent.agent.telemetry.QueryGateEventService;
import com.pfagent.agent.telemetry.QueryGateEventService.EventType;
import com.pfagent.agent.telemetry.QueryGateEventService.QueryGateEvent;
import com.pfagent.agent.telemetry.QueryGateEventService.Reason;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.Optional;

/**
 * 查询门禁事件记录器（F-026 设计 §8）
 *
 * 工具护栏每次判定（BLOCKED / ALLOWED）落一行 query_gate_event，供分析门禁触发形态
 * 与放行翻页；conversationId / question 取 {@link ToolCallTracker} 的请求上下文，
 * 不接受 LLM 工具参数，也不保存回答正文或来源快照。
 *
 * 降级（设计 §8.3）：遥测是尽力写入，任何一环失败都不改变工具结果、不阻断问答——
 * 无请求上下文（未 begin 的单测/管理直调）直接跳过且不写空会话事件；持久化服务未装配
 * （memory 模式）或写库异常只记 WARN。JDBC 实现由 telemetry lane 提供，故用
 * {@link ObjectProvider} 取，取不到即视为未装配。
 */
@Component
public class QueryGateEventRecorder {

    private static final Logger log = LoggerFactory.getLogger(QueryGateEventRecorder.class);

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Autowired
    private ObjectProvider<QueryGateEventService> serviceProvider;

    @Autowired
    private ToolCallTracker toolCallTracker;

    /** 记录一次「宽条件未放行 → 条目检索被拦截」事件 */
    public boolean recordBlocked(String toolName, String module, Reason reason, Object query) {
        return record(toolName, module, EventType.BLOCKED, reason, query);
    }

    /** 记录一次「宽条件已放行 → 允许执行」事件（同一逻辑查询的后续翻页也各记一行） */
    public boolean recordAllowed(String toolName, String module, Reason reason, Object query) {
        return record(toolName, module, EventType.ALLOWED, reason, query);
    }

    /**
     * 记录一行门禁事件。
     *
     * @return true = 已交给持久化服务且未抛异常；false = 跳过或降级（无上下文 / 未装配 /
     *         序列化失败 / 写库异常），调用方无需据此改变工具结果
     */
    public boolean record(String toolName, String module, EventType eventType, Reason reason, Object query) {
        if (toolName == null || eventType == null || reason == null) {
            log.warn("[QueryGate] 门禁事件字段缺失，跳过: tool={} type={} reason={}", toolName, eventType, reason);
            return false;
        }
        Optional<ToolCallTracker.RequestContext> context = toolCallTracker.currentContext();
        if (context.isEmpty()) {
            log.debug("[QueryGate] 无请求上下文（未 begin），跳过门禁事件: tool={} type={}", toolName, eventType);
            return false;
        }
        QueryGateEventService service = serviceProvider.getIfAvailable();
        if (service == null) {
            log.warn("[QueryGate] 持久化服务未装配（pf.chat.memory != jdbc），门禁事件未入库: tool={} type={}",
                    toolName, eventType);
            return false;
        }
        String queryJson;
        try {
            queryJson = objectMapper.writeValueAsString(query);
        } catch (Exception e) {
            log.warn("[QueryGate] 查询参数序列化失败，跳过门禁事件: tool={} type={}", toolName, eventType, e);
            return false;
        }
        ToolCallTracker.RequestContext ctx = context.get();
        try {
            service.persist(new QueryGateEvent(ctx.conversationId(), ctx.question(), toolName, module,
                    eventType, reason, queryJson, Instant.now()));
            return true;
        } catch (RuntimeException e) {
            log.warn("[QueryGate] 门禁事件入库失败（不影响主流程）: tool={} type={}", toolName, eventType, e);
            return false;
        }
    }
}
