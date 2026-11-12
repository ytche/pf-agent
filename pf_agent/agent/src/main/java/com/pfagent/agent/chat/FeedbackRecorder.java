package com.pfagent.agent.chat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pfagent.agent.telemetry.ErrorAnnotationEntity;
import com.pfagent.agent.telemetry.ErrorAnnotationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;

/**
 * 错误标注记录器（错误标注闭环，F-021 起入库）
 *
 * 前端「标错」按钮提交一条用户反馈，落 error_annotation 表一行，
 * 供 qa/annotations_report.py 按 errorType 聚类分析，驱动 prompt/检索策略迭代。
 * sources 存 JSONB 回答快照，分析时可精确复现错误现场。
 *
 * 降级（用户拍板 2026-09-24）：DB 不可用（memory 模式）时**不写文件、不谎报成功**——
 * 不再保留 JSONL 双写兼容，record 返回 ok=false（降级原因 db_unavailable）；写库异常
 * 同样返回 ok=false（write_failed），不再吞掉失败仍给 id。标注是尽力而为的遥测，
 * 失败不抛异常拖垮前端交互，但结果必须如实回传。
 *
 * 入参校验在写库之前（错误类型/会话 ID 超出列宽时先拒），故不会把「客户端入参非法」
 * 记成服务端降级 write_failed：这类返回 ok=false + reason=invalid_input，由
 * ChatController 回 400（服务端 503 只留给真实的库问题）。
 *
 * 数据库访问收在 {@link ErrorAnnotationService}（编程式事务），本类只管
 * 快照组装、入参校验与降级语义；服务 bean 仅在 pf.chat.memory=jdbc 时装配，故用
 * ObjectProvider 取，取不到即 memory 模式。
 */
@Component
public class FeedbackRecorder {

    private static final Logger log = LoggerFactory.getLogger(FeedbackRecorder.class);

    /** 与 error_annotation.error_type varchar(32) 对齐 */
    private static final int MAX_ERROR_TYPE_LENGTH = 32;
    /** 与 error_annotation.conversation_id varchar(36) 对齐 */
    private static final int MAX_CONVERSATION_ID_LENGTH = 36;

    @Autowired
    private ObjectProvider<ErrorAnnotationService> annotationServiceProvider;

    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * 记录一条错误标注（入库），返回写入结果
     *
     * 记录含 question/answer/sources 回答快照。返回 ok=false 时表示未入库，
     * 调用方（ChatController）据 reason 返回 400（入参非法）或 503（库不可用/写失败），
     * 前端提示重试而非「已记录」。
     */
    public FeedbackResponse record(FeedbackRequest request) {
        String invalidField = invalidField(request);
        if (invalidField != null) {
            log.warn("[Feedback] 标注入参非法，未入库: {}", invalidField);
            return FeedbackResponse.failed(FeedbackResponse.REASON_INVALID_INPUT);
        }
        String id = generateId();
        ErrorAnnotationService service = annotationServiceProvider.getIfAvailable();
        if (service == null) {
            log.warn("[Feedback] 数据库未装配（pf.chat.memory != jdbc），标注未入库也不落文件: id={}", id);
            return FeedbackResponse.failed(FeedbackResponse.REASON_DB_UNAVAILABLE);
        }
        try {
            service.persistIfAbsent(toEntity(id, request));
            return FeedbackResponse.persisted(id);
        } catch (RuntimeException e) {
            log.error("[Feedback] 错误标注入库失败: id={}", id, e);
            return FeedbackResponse.failed(FeedbackResponse.REASON_WRITE_FAILED);
        }
    }

    /** 入参校验：超出列宽的字段名（用于日志），全部合法返回 null */
    private static String invalidField(FeedbackRequest request) {
        if (request.errorType() != null && request.errorType().length() > MAX_ERROR_TYPE_LENGTH) {
            return "errorType 长度 " + request.errorType().length() + " 超过 " + MAX_ERROR_TYPE_LENGTH;
        }
        if (request.conversationId() != null && request.conversationId().length() > MAX_CONVERSATION_ID_LENGTH) {
            return "conversationId 长度 " + request.conversationId().length()
                    + " 超过 " + MAX_CONVERSATION_ID_LENGTH;
        }
        return null;
    }

    /** 请求快照 → 实体行（sources 序列化为 JSON 文本存 JSONB 列） */
    private ErrorAnnotationEntity toEntity(String id, FeedbackRequest request) {
        return new ErrorAnnotationEntity(
                id,
                request.conversationId(),
                request.question(),
                request.answer(),
                writeSources(request.sources()),
                request.errorType(),
                request.correction(),
                request.comment(),
                Instant.now());
    }

    /**
     * sources 序列化为 JSON 文本（空列表仍是 "[]"，null 才是 SQL NULL，与旧 JSONL 口径一致）。
     * 序列化异常降级为 null 并记 warn：来源快照缺失不应连带丢掉整条标注。
     */
    private String writeSources(List<ChatResponse.SourceRef> sources) {
        if (sources == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(sources);
        } catch (Exception e) {
            log.warn("[Feedback] sources 序列化失败，本条标注的来源快照置空: {}", e.getMessage());
            return null;
        }
    }

    /** ann- 前缀 + 毫秒时间戳 + 随机后缀，单机并发下唯一，作为表主键 */
    private String generateId() {
        return "ann-" + System.currentTimeMillis()
                + "-" + ThreadLocalRandom.current().nextInt(1000, 10000);
    }
}
