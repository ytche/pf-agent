package com.pfagent.agent.usage;

import com.pfagent.agent.admin.AdminService;
import com.pfagent.agent.config.AuthInterceptor;
import com.pfagent.agent.conversation.ConversationAccessGuard;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;
import java.util.Set;
import java.util.UUID;

/**
 * 用量与费用汇总接口（F-009 设计 §5）。
 *
 * GET /api/usage/summary?range=today|month|all&groupBy=day|conversation|owner
 *      &conversationId=...&ownerId=...
 *
 * 权限（后端强约束，不依赖前端隐藏）：
 *  - 匿名：必须提供当前 conversationId 且经统一的会话可读校验，只能看该会话；
 *  - 登录用户：自动限定 owner_id=自己，禁止 groupBy=owner，忽略 ownerId 参数；
 *  - 管理员：默认全局，可 groupBy=owner 或按 ownerId 过滤。
 * 越权/不可读的会话统一按会话规则的 404/403 处理，不返回他人汇总。
 *
 * memory 模式没有 usage 表：UsageService 未装配 → 503 usage_unavailable。
 */
@RestController
@RequestMapping("/api")
public class UsageController {

    private static final Set<String> RANGES = Set.of("today", "month", "all");
    private static final Set<String> GROUPS = Set.of("day", "conversation", "owner");

    private final ObjectProvider<UsageService> usageServiceProvider;
    private final ObjectProvider<AdminService> adminServiceProvider;
    private final ConversationAccessGuard accessGuard;

    public UsageController(ObjectProvider<UsageService> usageServiceProvider,
                           ObjectProvider<AdminService> adminServiceProvider,
                           ConversationAccessGuard accessGuard) {
        this.usageServiceProvider = usageServiceProvider;
        this.adminServiceProvider = adminServiceProvider;
        this.accessGuard = accessGuard;
    }

    @GetMapping("/usage/summary")
    public ResponseEntity<?> summary(
            @RequestAttribute(value = AuthInterceptor.USER_ID_ATTRIBUTE, required = false) Long userId,
            @RequestAttribute(value = AuthInterceptor.USERNAME_ATTRIBUTE, required = false) String username,
            @RequestParam(defaultValue = "month") String range,
            @RequestParam(defaultValue = "day") String groupBy,
            @RequestParam(required = false) Long ownerId,
            @RequestParam(required = false) String conversationId) {
        UsageService service = usageServiceProvider.getIfAvailable();
        if (service == null) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(Map.of(
                    "error", "usage_unavailable",
                    "message", "用量统计不可用：内存模式没有 usage_record 表"));
        }
        if (!RANGES.contains(range)) {
            throw new IllegalArgumentException("range 仅支持 today|month|all");
        }
        if (!GROUPS.contains(groupBy)) {
            throw new IllegalArgumentException("groupBy 仅支持 day|conversation|owner");
        }

        boolean admin = isAdmin(userId, username);
        Long effectiveOwnerId = null;
        String effectiveConversationId = null;
        String scope;
        if (userId == null) {
            // 匿名：只能看当前会话；必须提供且经统一可读校验（不泄露他人会话是否存在）
            if ("owner".equals(groupBy)) {
                return ownerGroupForbidden();
            }
            if (conversationId == null || conversationId.isBlank()) {
                throw new IllegalArgumentException("匿名查询必须提供 conversationId");
            }
            effectiveConversationId = requireConversationId(conversationId);
            accessGuard.requireReadable(effectiveConversationId, null);
            scope = "conversation";
        } else if (admin) {
            effectiveOwnerId = ownerId;
            scope = ownerId == null ? "global" : "owner";
        } else {
            if ("owner".equals(groupBy)) {
                return ownerGroupForbidden();
            }
            // 普通用户自动限定自己，忽略客户端传入的 ownerId/conversationId
            effectiveOwnerId = userId;
            scope = "owner";
        }

        return ResponseEntity.ok(service.summarize(range, groupBy, effectiveOwnerId,
                effectiveConversationId, scope));
    }

    private boolean isAdmin(Long userId, String username) {
        if (userId == null || username == null) {
            return false;
        }
        AdminService adminService = adminServiceProvider.getIfAvailable();
        return adminService != null && adminService.isAdmin(username);
    }

    /** 匿名会话 ID 必须为标准 UUID；格式错误按非法请求处理，不落到查询层 */
    private static String requireConversationId(String conversationId) {
        String trimmed = conversationId.trim();
        try {
            UUID.fromString(trimmed);
        } catch (IllegalArgumentException e) {
            throw new IllegalArgumentException("conversationId 格式非法");
        }
        return trimmed;
    }

    private static ResponseEntity<Map<String, String>> ownerGroupForbidden() {
        return ResponseEntity.status(HttpStatus.FORBIDDEN).body(Map.of(
                "error", "usage_owner_group_forbidden",
                "message", "仅管理员可按用户分组查看用量"));
    }
}
