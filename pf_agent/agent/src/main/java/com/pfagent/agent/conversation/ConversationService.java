package com.pfagent.agent.conversation;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pfagent.agent.chat.ChatResponse;
import com.pfagent.agent.chat.ChatService;
import com.pfagent.agent.memory.ConversationStore;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * 会话业务编排（F-020 实施 Spec §5/§8，前端冻结契约见 frontend/docs/api-contract.md）
 *
 * 只做归属/访问判定、DTO 组装与重新生成编排；会话事实与快照全部落 ConversationStore。
 * 访问规则统一由 {@link ConversationAccessGuard} 执行：匿名凭 UUID 访问 owner 为空的会话，
 * 登录访问未认领会话 403，他账号/匿名访问已认领会话 404。
 */
@Service
public class ConversationService {

    private static final Logger log = LoggerFactory.getLogger(ConversationService.class);
    /** 单次 lookup/claim 的 ID 上限，防超大请求 */
    private static final int MAX_IDS_PER_REQUEST = 100;
    /** title 列宽（V7 VARCHAR(200)） */
    private static final int MAX_TITLE_LENGTH = 200;

    @Autowired
    private ConversationStore conversationStore;
    @Autowired
    private ConversationAccessGuard accessGuard;
    @Autowired
    private ChatService chatService;
    @Autowired
    private ObjectMapper objectMapper;
    @Value("${pf.chat.history-rounds:20}")
    private int historyRounds;
    @Value("${pf.conversation.default-page-size:30}")
    private int defaultPageSize;

    /** 新建空白会话；messageRounds=0 时不进入历史列表。登录用户自动写入 owner。 */
    public ConversationSummary create(Long userId) {
        String id = UUID.randomUUID().toString();
        return ConversationSummary.from(
                conversationStore.createConversation(id, userId, Instant.now()));
    }

    /** 账号会话分批读取：必须登录；置顶优先、其余最近活跃倒序 */
    public ConversationPageResponse list(Long userId, String cursor, int limit) {
        if (userId == null) {
            throw new UnauthorizedException();
        }
        int size = limit <= 0 ? defaultPageSize : limit;
        ConversationStore.ConversationPage page =
                conversationStore.listOwnedConversations(userId, cursor, size);
        return new ConversationPageResponse(page.items().stream()
                .map(ConversationSummary::from).toList(), page.nextCursor());
    }

    /** 匿名本机 lookup：只返回 owner 为空的会话（认领后自动移除），按请求顺序 */
    public LookupResponse lookup(List<String> ids) {
        List<ConversationSummary> items = conversationStore.lookupConversations(checkedIds(ids))
                .stream().map(ConversationSummary::from).toList();
        return new LookupResponse(items);
    }

    /** 读取会话及最近 20 轮消息与引用快照 */
    public ConversationDetail detail(String conversationId, Long userId) {
        accessGuard.requireReadable(conversationId, userId);
        List<ConversationMessage> messages = conversationStore
                .history(conversationId, historyRounds * 2).stream()
                .map(this::toMessage).toList();
        ConversationStore.ConversationView view = conversationStore.getConversation(conversationId)
                .orElseThrow(() -> new ConversationNotFoundException(conversationId));
        return ConversationDetail.from(ConversationSummary.from(view), messages);
    }

    /** 重命名或修改置顶状态 */
    public ConversationSummary patch(String conversationId, Long userId, PatchConversationRequest request) {
        accessGuard.requireReadable(conversationId, userId);
        if (request != null && request.title() != null) {
            conversationStore.renameConversation(conversationId, normalizeTitle(request.title()));
        }
        if (request != null && request.pinned() != null) {
            conversationStore.setPinned(conversationId, request.pinned());
        }
        return ConversationSummary.from(conversationStore.getConversation(conversationId)
                .orElseThrow(() -> new ConversationDeletedException(conversationId)));
    }

    /** 永久删除会话及全部消息（含引用快照） */
    public void delete(String conversationId, Long userId) {
        accessGuard.requireReadable(conversationId, userId);
        conversationStore.deleteConversation(conversationId);
    }

    /** 登录后显式认领本机匿名会话：只认领 owner 为空的会话，重复认领幂等 */
    public ClaimResponse claim(Long userId, List<String> ids) {
        if (userId == null) {
            throw new UnauthorizedException();
        }
        List<String> claimed = new ArrayList<>();
        List<String> alreadyOwned = new ArrayList<>();
        List<String> rejected = new ArrayList<>();
        for (String id : checkedIds(ids)) {
            switch (conversationStore.claimConversation(id, userId)) {
                case CLAIMED -> claimed.add(id);
                case ALREADY_OWNER -> alreadyOwned.add(id);
                case OWNED_BY_OTHER, NOT_FOUND -> rejected.add(id);
            }
        }
        return new ClaimResponse(claimed, alreadyOwned, rejected);
    }

    /** 重新生成最后一轮并替换助手消息（不增加对话轮数） */
    public ChatResponse regenerate(String conversationId, Long userId, Integer expectedLastSeq) {
        ChatService.RegenerateResult result =
                chatService.regenerate(conversationId, userId, expectedLastSeq);
        return new ChatResponse(result.answer(), result.sources(), result.gapReported(),
                result.conversationId(), result.messageId(), result.messageSeq(), result.completedAt());
    }

    /** 消息行 → API DTO：解析引用快照 JSON（null 保持 null，损坏时降级 null 并记 WARN） */
    private ConversationMessage toMessage(ConversationStore.StoredMessage row) {
        Long id = row.id();
        return new ConversationMessage(id, row.seq(), row.role(), row.content(),
                parseSources(row.sourcesJson()), row.gapReported(), row.createdAt(),
                "assistant".equals(row.role()) ? row.createdAt() : null);
    }

    private List<ChatResponse.SourceRef> parseSources(String sourcesJson) {
        if (sourcesJson == null) {
            return null;
        }
        try {
            return objectMapper.readValue(sourcesJson, new TypeReference<List<ChatResponse.SourceRef>>() {
            });
        } catch (Exception e) {
            log.warn("历史消息来源快照解析失败，按未保存降级: {}", e.getMessage());
            return null;
        }
    }

    private static List<String> checkedIds(List<String> ids) {
        if (ids == null) {
            return List.of();
        }
        List<String> distinct = ids.stream()
                .filter(id -> id != null && !id.isBlank())
                .map(String::trim)
                .distinct()
                .toList();
        if (distinct.size() > MAX_IDS_PER_REQUEST) {
            throw new IllegalArgumentException("单次最多提交 " + MAX_IDS_PER_REQUEST + " 个会话 ID");
        }
        return distinct;
    }

    private static String normalizeTitle(String title) {
        String trimmed = title.strip();
        if (trimmed.length() > MAX_TITLE_LENGTH) {
            throw new IllegalArgumentException("title 长度不能超过 " + MAX_TITLE_LENGTH);
        }
        return trimmed.isEmpty() ? null : trimmed;
    }
}
