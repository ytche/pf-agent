package com.pfagent.agent.memory;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

/**
 * 统一会话事实源（F-020 实施 Spec §5）
 *
 * 会话 CRUD、账号分页、匿名 lookup、认领、模型历史读取、追加问答与引用快照、
 * 替换最后一条助手消息、20 轮裁剪与配额计数全部经此接口完成。JDBC 与内存各一实现，
 * 同一套语义；ChatMemory 只作为兼容适配委托到本接口，不再形成第二份写入逻辑。
 *
 * 存储层只表达事实与结果枚举，不抛 HTTP 语义异常；归属/授权判定由调用方
 * （ConversationAccessGuard / ConversationService）负责。
 */
public interface ConversationStore {

    /** 会话摘要（账号列表、lookup、详情共用） */
    record ConversationView(
            String id,
            String title,
            boolean pinned,
            Long ownerUserId,
            int messageRounds,
            int totalRounds,
            int generationAttempts,
            Instant createdAt,
            Instant lastActiveAt) {
    }

    /** 已落库消息（sourcesJson 为当轮引用快照 JSON；null = 历史消息未保存来源） */
    record StoredMessage(
            long id,
            int seq,
            String role,
            String content,
            String sourcesJson,
            boolean gapReported,
            Instant createdAt) {
    }

    /** 分页结果：nextCursor 为 null 表示没有更多 */
    record ConversationPage(List<ConversationView> items, String nextCursor) {
    }

    /** 最后一轮（重新生成读取最后用户问题，模型历史排除待替换的旧助手回答） */
    record LastRound(int userSeq, String question, StoredMessage assistant) {
    }

    enum AppendStatus { OK, PARENT_MISSING }

    record AppendResult(AppendStatus status, StoredMessage assistant) {
    }

    enum ReplaceStatus { OK, PARENT_MISSING, CONFLICT }

    record ReplaceResult(ReplaceStatus status, StoredMessage assistant) {
    }

    enum ClaimStatus { CLAIMED, ALREADY_OWNER, OWNED_BY_OTHER, NOT_FOUND }

    /** 新建会话行（空会话 message_rounds=0，不在历史列表可见） */
    ConversationView createConversation(String id, Long ownerUserId, Instant now);

    Optional<ConversationView> getConversation(String id);

    /** 账号会话分批读取：置顶优先、最近活跃倒序，只含 message_rounds > 0 */
    ConversationPage listOwnedConversations(Long ownerUserId, String cursor, int limit);

    /**
     * 匿名能力 lookup：只返回 owner 为空的会话（认领后即从本机匿名结果移除）；
     * 按请求 ids 顺序返回，忽略不存在/空会话。
     */
    List<ConversationView> lookupConversations(List<String> ids);

    boolean renameConversation(String id, String title);

    boolean setPinned(String id, boolean pinned);

    /** 硬删除会话及全部消息（含引用快照） */
    boolean deleteConversation(String id);

    ClaimStatus claimConversation(String id, Long ownerUserId);

    /** 最近 lastMessages 条消息（旧 → 新），用于模型历史与详情读取 */
    List<StoredMessage> history(String id, int lastMessages);

    Optional<LastRound> lastRound(String id);

    /**
     * 追加一轮完整问答：父会话必须已存在（不存在返回 PARENT_MISSING，绝不自动重建）；
     * 首轮成功时以问题前 30 字生成默认标题；助手行保存 cited-only 来源快照与 gap 标记。
     */
    AppendResult appendRound(String id, String question, String answer,
                             String sourcesJson, boolean gapReported, Instant now);

    /**
     * 替换最后一条助手消息：必须带 expectedAssistantSeq 且当前最后一条仍是该助手消息，
     * 否则 CONFLICT；父会话已删除返回 PARENT_MISSING；不改变轮数。
     */
    ReplaceResult replaceLastAssistant(String id, int expectedAssistantSeq, String answer,
                                       String sourcesJson, boolean gapReported, Instant now);

    /** 模型调用前累计生成尝试；父行缺失返回 0（不重建） */
    int incrementGenerationAttempts(String id);

    /** 当前累计生成尝试次数；会话不存在返回 0 */
    int generationAttempts(String id);

    /** 账号会话总数（分页 nextCursor 判定用） */
    long countOwnedConversations(Long ownerUserId);
}
