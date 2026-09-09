package com.pfagent.agent.chat;

import com.pfagent.agent.memory.AnonymousQuotaService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * 问答 REST API
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
     */
    @PostMapping("/chat")
    public ResponseEntity<?> chat(@RequestBody ChatRequest request) {
        AnonymousQuotaService quotaService = quotaServiceProvider.getIfAvailable();
        String conversationId = request.conversationId();
        if (quotaService != null && conversationId != null && !conversationId.isBlank()
                && quotaService.isExceeded(conversationId)) {
            return ResponseEntity.status(429).body(Map.of(
                    "error", "quota_exceeded",
                    "message", "本会话免费额度已用完（" + quotaService.getAnonymousRounds()
                            + " 轮）。请开启新会话继续提问。"));
        }
        return ResponseEntity.ok(chatService.ask(request.question(), conversationId));
    }

    /**
     * 错误标注接口（错误标注闭环）
     *
     * POST /api/chat/feedback
     * Body: { "conversationId": "...", "question": "...", "answer": "...",
     *         "sources": [{book,tocPath,content}], "errorType": "事实错误",
     *         "correction": "...", "comment": "..." }
     * 前端「标错」按钮提交，追加写入 annotations JSONL 供分析脚本聚类，返回记录 ID。
     */
    @PostMapping("/chat/feedback")
    public FeedbackResponse feedback(@RequestBody FeedbackRequest request) {
        String id = feedbackRecorder.record(request);
        return new FeedbackResponse(true, id);
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
