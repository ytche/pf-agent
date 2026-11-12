package com.pfagent.agent.conversation;

import com.pfagent.agent.chat.ChatResponse;
import com.pfagent.agent.config.AuthInterceptor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 会话 REST API（F-020 实施 Spec §7.1；字段与前端冻结契约一致）
 *
 * 身份来自 AuthInterceptor 写入的 request attribute：无 token 为匿名（userId=null），
 * 有效 JWT 为当前账号。归属与可见性规则由 ConversationService/AccessGuard 统一执行。
 */
@RestController
@RequestMapping("/api/conversations")
public class ConversationController {

    private final ConversationService conversationService;

    public ConversationController(ConversationService conversationService) {
        this.conversationService = conversationService;
    }

    /** 创建空白会话（空会话不进入历史列表） */
    @PostMapping
    public ConversationSummary create(
            @RequestAttribute(value = AuthInterceptor.USER_ID_ATTRIBUTE, required = false) Long userId) {
        return conversationService.create(userId);
    }

    /** 登录用户分批读取账号会话：置顶优先、其余最近活跃倒序 */
    @GetMapping
    public ConversationPageResponse list(
            @RequestAttribute(value = AuthInterceptor.USER_ID_ATTRIBUTE, required = false) Long userId,
            @RequestParam(required = false) String cursor,
            @RequestParam(defaultValue = "30") int limit) {
        return conversationService.list(userId, cursor, limit);
    }

    /** 匿名本机批量读取（只返回 owner 为空的会话） */
    @PostMapping("/lookup")
    public LookupResponse lookup(@RequestBody LookupRequest request) {
        return conversationService.lookup(request == null ? null : request.ids());
    }

    /** 登录后显式认领本机匿名会话 */
    @PostMapping("/claim")
    public ClaimResponse claim(
            @RequestAttribute(value = AuthInterceptor.USER_ID_ATTRIBUTE, required = false) Long userId,
            @RequestBody ClaimRequest request) {
        return conversationService.claim(userId, request == null ? null : request.conversationIds());
    }

    /** 读取会话及最近 20 轮消息与引用快照 */
    @GetMapping("/{id}")
    public ConversationDetail detail(
            @RequestAttribute(value = AuthInterceptor.USER_ID_ATTRIBUTE, required = false) Long userId,
            @PathVariable String id) {
        return conversationService.detail(id, userId);
    }

    /** 重命名或修改置顶状态 */
    @PatchMapping("/{id}")
    public ConversationSummary patch(
            @RequestAttribute(value = AuthInterceptor.USER_ID_ATTRIBUTE, required = false) Long userId,
            @PathVariable String id,
            @RequestBody PatchConversationRequest request) {
        return conversationService.patch(id, userId, request);
    }

    /** 永久删除会话及消息 */
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(
            @RequestAttribute(value = AuthInterceptor.USER_ID_ATTRIBUTE, required = false) Long userId,
            @PathVariable String id) {
        conversationService.delete(id, userId);
        return ResponseEntity.noContent().build();
    }

    /** 重新生成最后一轮并替换助手消息（保持原消息 ID，不增加轮数） */
    @PostMapping("/{id}/regenerate")
    public ChatResponse regenerate(
            @RequestAttribute(value = AuthInterceptor.USER_ID_ATTRIBUTE, required = false) Long userId,
            @PathVariable String id,
            @RequestBody(required = false) RegenerateRequest request) {
        return conversationService.regenerate(id, userId,
                request == null ? null : request.expectedLastSeq());
    }
}
