package com.pfagent.agent.conversation;

import com.pfagent.agent.memory.ConversationStore;
import org.springframework.stereotype.Component;

/**
 * 会话访问规则（F-020 实施 Spec §8.2）
 *
 * - 匿名会话（owner 为空）：匿名请求凭不可猜测 UUID 访问；已登录用户访问返回 403，
 *   必须显式认领，不在读取时自动转移归属；
 * - 有 owner 的会话：仅所属账号可访问；匿名或其他账号统一 404，避免泄露
 *   「该 UUID 已存在且被认领」；
 * - 从不存在的会话：404。
 */
@Component
public class ConversationAccessGuard {

    private final ConversationStore store;

    public ConversationAccessGuard(ConversationStore store) {
        this.store = store;
    }

    /** 读取/修改/问答/重新生成/删除统一的访问判定 */
    public ConversationStore.ConversationView requireReadable(String conversationId, Long callerUserId) {
        ConversationStore.ConversationView view = store.getConversation(conversationId)
                .orElseThrow(() -> new ConversationNotFoundException(conversationId));
        if (view.ownerUserId() == null) {
            if (callerUserId != null) {
                throw new ConversationForbiddenException();
            }
            return view;
        }
        if (!view.ownerUserId().equals(callerUserId)) {
            throw new ConversationNotFoundException(conversationId);
        }
        return view;
    }
}
