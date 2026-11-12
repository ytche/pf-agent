package com.pfagent.agent.chat;

import com.pfagent.agent.config.AuthInterceptor;
import com.pfagent.agent.memory.AnonymousQuotaService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 问答 REST API
 *
 * F-020 起：身份来自 AuthInterceptor 的 request attribute（无 token 匿名、非法 JWT 401），
 * 登录用户新建会话自动写入 owner；匿名会话配额改读统一 ConversationStore 的
 * generation_attempts（普通问答与重新生成共用）。响应在原四字段上追加可选
 * messageId / messageSeq / completedAt。
 */
@RestController
@RequestMapping("/api")
public class ChatController {

    @Autowired
    private ChatService chatService;

    @Autowired
    private FeedbackRecorder feedbackRecorder;

    /** 匿名会话配额（pf.quota.enabled=true 才装配；默认关闭时 ObjectProvider 为空跳过检查） */
    @Autowired
    private ObjectProvider<AnonymousQuotaService> quotaServiceProvider;

    /**
     * 规则问答接口
     *
     * POST /api/chat
     * Body: { "question": "顺势斩会对多个目标触发借机攻击吗？", "conversationId": "..." }
     * conversationId 为空时后端生成新会话 ID，随响应返回。
     *
     * F-011 匿名配额检查在 service.ask 之前（D6）：已存在会话用尽配额返回 429，
     * 新会话（无 conversationId）直接放行——fail-fast，超配额不触发 LLM 零 token 成本。
     * F-020：chatService 内部在实际调用模型前再次检查并累计 generation_attempts，
     * 两处语义一致，避免重新生成等其他入口绕过成本护栏。
     */
    @PostMapping("/chat")
    public ResponseEntity<?> chat(
            @RequestAttribute(value = AuthInterceptor.USER_ID_ATTRIBUTE, required = false) Long userId,
            @RequestBody ChatRequest request) {
        AnonymousQuotaService quotaService = quotaServiceProvider.getIfAvailable();
        String conversationId = request.conversationId();
        if (quotaService != null && conversationId != null && !conversationId.isBlank()
                && quotaService.isExceeded(conversationId)) {
            return ResponseEntity.status(429).body(Map.of(
                    "error", "quota_exceeded",
                    "message", "本会话免费额度已用完（" + quotaService.getAnonymousRounds()
                            + " 轮）。请开启新会话继续提问。"));
        }
        return ResponseEntity.ok(chatService.ask(request.question(), conversationId, userId));
    }

    /**
     * 错误标注接口（错误标注闭环，F-021 入库）
     *
     * POST /api/chat/feedback
     * Body: { "conversationId": "...", "question": "...", "answer": "...",
     *         "sources": [{book,tocPath,content}], "errorType": "事实错误",
     *         "correction": "...", "comment": "..." }
     * 前端「标错」按钮提交，写入 error_annotation 表供分析脚本聚类，返回记录 ID。
     * 未入库时按原因分档：入参非法（字段超长）→ 400；库不可用/写入失败 → 503；
     * 两者都 ok=false + reason，不谎报成功（前端按非 2xx 提示失败）。
     */
    @PostMapping("/chat/feedback")
    public ResponseEntity<FeedbackResponse> feedback(@RequestBody FeedbackRequest request) {
        FeedbackResponse response = feedbackRecorder.record(request);
        if (response.ok()) {
            return ResponseEntity.ok(response);
        }
        return FeedbackResponse.REASON_INVALID_INPUT.equals(response.reason())
                ? ResponseEntity.badRequest().body(response)
                : ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(response);
    }

    /**
     * 健康检查
     *
     * GET /api/health
     */
    @GetMapping("/health")
    public String health() {
        return "OK — PF Agent is running";
    }
}
