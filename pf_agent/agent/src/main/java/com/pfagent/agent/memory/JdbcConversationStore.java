package com.pfagent.agent.memory;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * JDBC 版统一会话存储（pf.chat.memory=jdbc，F-020 实施 Spec §5）
 *
 * 追加/替换先显式检查父行：父会话不存在返回 PARENT_MISSING，绝不自动重建已删除会话
 * （替换 V1 时代 JdbcChatMemory.doAdd 的 orElseGet 自动建父行分支）。追加一轮在同一
 * 事务内完成：user/assistant 两行 + seq 递增 + 20 轮窗口裁剪 + 标题/活跃时间/轮数维护；
 * 助手行保存当轮 cited-only 来源快照与 gap 标记，裁剪时随行删除，不留下孤儿快照。
 */
@Component
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
public class JdbcConversationStore implements ConversationStore {

    /** 分页硬上限：防止客户端用超大 limit 拉全表 */
    static final int MAX_PAGE_SIZE = 100;
    /** 默认标题长度（首条问题前 N 字，终态设计 §4.3 的 20～30 字区间） */
    private static final int DEFAULT_TITLE_LENGTH = 30;

    @Autowired
    private ChatConversationRepository conversationRepository;
    @Autowired
    private ChatMessageRepository messageRepository;
    @Value("${pf.chat.history-rounds:20}")
    private int historyRounds;

    @Override
    @Transactional
    public ConversationView createConversation(String id, Long ownerUserId, Instant now) {
        ChatConversationEntity entity = new ChatConversationEntity(id, now, ownerUserId);
        return toView(conversationRepository.save(entity));
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<ConversationView> getConversation(String id) {
        return conversationRepository.findById(id).map(JdbcConversationStore::toView);
    }

    @Override
    @Transactional(readOnly = true)
    public ConversationPage listOwnedConversations(Long ownerUserId, String cursor, int limit) {
        int size = clampLimit(limit);
        int requested = parseCursor(cursor);
        int page = requested / size;
        int offset = page * size;
        List<ConversationView> items = conversationRepository
                .findVisibleByOwner(ownerUserId, PageRequest.of(page, size))
                .stream().map(JdbcConversationStore::toView).toList();
        long total = conversationRepository.countVisibleByOwner(ownerUserId);
        long next = (long) offset + items.size();
        String nextCursor = !items.isEmpty() && next < total ? Long.toString(next) : null;
        return new ConversationPage(items, nextCursor);
    }

    @Override
    @Transactional(readOnly = true)
    public List<ConversationView> lookupConversations(List<String> ids) {
        if (ids == null || ids.isEmpty()) {
            return List.of();
        }
        List<String> distinct = ids.stream().filter(id -> id != null && !id.isBlank()).distinct().toList();
        if (distinct.isEmpty()) {
            return List.of();
        }
        Map<String, ChatConversationEntity> byId = conversationRepository.findAllById(distinct).stream()
                .collect(Collectors.toMap(ChatConversationEntity::getId, Function.identity()));
        List<ConversationView> views = new ArrayList<>();
        for (String id : distinct) {
            ChatConversationEntity entity = byId.get(id);
            if (entity != null && entity.getOwnerUserId() == null
                    && entity.getMessageRounds() != null && entity.getMessageRounds() > 0) {
                views.add(toView(entity));
            }
        }
        return views;
    }

    @Override
    @Transactional
    public boolean renameConversation(String id, String title) {
        return conversationRepository.findById(id).map(entity -> {
            entity.setTitle(title);
            conversationRepository.save(entity);
            return true;
        }).orElse(false);
    }

    @Override
    @Transactional
    public boolean setPinned(String id, boolean pinned) {
        return conversationRepository.findById(id).map(entity -> {
            entity.setPinned(pinned);
            conversationRepository.save(entity);
            return true;
        }).orElse(false);
    }

    @Override
    @Transactional
    public boolean deleteConversation(String id) {
        if (!conversationRepository.existsById(id)) {
            return false;
        }
        messageRepository.deleteByConversationId(id);
        conversationRepository.deleteById(id);
        return true;
    }

    @Override
    @Transactional
    public ClaimStatus claimConversation(String id, Long ownerUserId) {
        if (conversationRepository.claimAnonymous(id, ownerUserId) > 0) {
            return ClaimStatus.CLAIMED;
        }
        return conversationRepository.findById(id)
                .map(entity -> ownerUserId.equals(entity.getOwnerUserId())
                        ? ClaimStatus.ALREADY_OWNER
                        : ClaimStatus.OWNED_BY_OTHER)
                .orElse(ClaimStatus.NOT_FOUND);
    }

    @Override
    @Transactional(readOnly = true)
    public List<StoredMessage> history(String id, int lastMessages) {
        if (lastMessages <= 0) {
            return List.of();
        }
        List<ChatMessageEntity> all = messageRepository.findByConversationIdOrderBySeqAsc(id);
        List<ChatMessageEntity> recent = all.size() > lastMessages
                ? all.subList(all.size() - lastMessages, all.size())
                : all;
        return recent.stream().map(JdbcConversationStore::toMessage).toList();
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<LastRound> lastRound(String id) {
        List<ChatMessageEntity> all = messageRepository.findByConversationIdOrderBySeqAsc(id);
        if (all.size() < 2) {
            return Optional.empty();
        }
        ChatMessageEntity assistant = all.get(all.size() - 1);
        ChatMessageEntity user = all.get(all.size() - 2);
        if (!"assistant".equals(assistant.getRole()) || !"user".equals(user.getRole())) {
            return Optional.empty();
        }
        return Optional.of(new LastRound(user.getSeq(), user.getContent(), toMessage(assistant)));
    }

    @Override
    @Transactional
    public AppendResult appendRound(String id, String question, String answer,
                                    String sourcesJson, boolean gapReported, Instant now) {
        Optional<ChatConversationEntity> found = conversationRepository.findById(id);
        if (found.isEmpty()) {
            return new AppendResult(AppendStatus.PARENT_MISSING, null);
        }
        ChatConversationEntity conversation = found.get();
        int lastSeq = messageRepository.findTopByConversationIdOrderBySeqDesc(id)
                .map(ChatMessageEntity::getSeq)
                .orElse(0);
        ChatMessageEntity userRow = new ChatMessageEntity(id, lastSeq + 1, "user", question, now);
        ChatMessageEntity assistantRow = new ChatMessageEntity(
                id, lastSeq + 2, "assistant", answer, now, sourcesJson, gapReported);
        messageRepository.saveAll(List.of(userRow, assistantRow));

        int maxSeq = lastSeq + 2;
        if ((long) maxSeq > (long) historyRounds * 2) {
            messageRepository.deleteByConversationIdAndSeqLessThanEqual(id, maxSeq - historyRounds * 2);
        }

        conversation.setLastActiveAt(now);
        conversation.setMessageRounds(Math.min(historyRounds, conversation.getMessageRounds() + 1));
        conversation.setTotalRounds(conversation.getTotalRounds() + 1);
        if (conversation.getTitle() == null || conversation.getTitle().isBlank()) {
            conversation.setTitle(defaultTitle(question));
        }
        conversationRepository.save(conversation);
        return new AppendResult(AppendStatus.OK, toMessage(assistantRow));
    }

    @Override
    @Transactional
    public ReplaceResult replaceLastAssistant(String id, int expectedAssistantSeq, String answer,
                                              String sourcesJson, boolean gapReported, Instant now) {
        Optional<ChatConversationEntity> found = conversationRepository.findById(id);
        if (found.isEmpty()) {
            return new ReplaceResult(ReplaceStatus.PARENT_MISSING, null);
        }
        int lastSeq = messageRepository.findTopByConversationIdOrderBySeqDesc(id)
                .map(ChatMessageEntity::getSeq)
                .orElse(-1);
        if (lastSeq != expectedAssistantSeq) {
            return new ReplaceResult(ReplaceStatus.CONFLICT, null);
        }
        int updated = messageRepository.replaceAssistantMessage(
                id, expectedAssistantSeq, answer, sourcesJson, gapReported, now);
        if (updated == 0) {
            return new ReplaceResult(ReplaceStatus.CONFLICT, null);
        }
        ChatConversationEntity conversation = found.get();
        conversation.setLastActiveAt(now);
        conversationRepository.save(conversation);
        ChatMessageEntity row = messageRepository.findByConversationIdOrderBySeqAsc(id).stream()
                .filter(m -> m.getSeq() == expectedAssistantSeq)
                .findFirst()
                .orElseThrow();
        return new ReplaceResult(ReplaceStatus.OK, toMessage(row));
    }

    @Override
    @Transactional
    public int incrementGenerationAttempts(String id) {
        if (conversationRepository.incrementGenerationAttempts(id) == 0) {
            return 0;
        }
        return generationAttempts(id);
    }

    @Override
    @Transactional(readOnly = true)
    public int generationAttempts(String id) {
        return conversationRepository.findById(id)
                .map(entity -> entity.getGenerationAttempts() == null ? 0 : entity.getGenerationAttempts())
                .orElse(0);
    }

    @Override
    @Transactional(readOnly = true)
    public long countOwnedConversations(Long ownerUserId) {
        return conversationRepository.countVisibleByOwner(ownerUserId);
    }

    /** 光标 = 下一页偏移（本实现生成的是 limit 的整数倍；非法/负数按 0 处理） */
    private static int parseCursor(String cursor) {
        if (cursor == null || cursor.isBlank()) {
            return 0;
        }
        try {
            int value = Integer.parseInt(cursor.trim());
            return Math.max(value, 0);
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    private static int clampLimit(int limit) {
        if (limit <= 0) {
            return 30;
        }
        return Math.min(limit, MAX_PAGE_SIZE);
    }

    private static String defaultTitle(String question) {
        if (question == null) {
            return null;
        }
        String trimmed = question.strip();
        if (trimmed.length() <= DEFAULT_TITLE_LENGTH) {
            return trimmed;
        }
        return trimmed.substring(0, DEFAULT_TITLE_LENGTH);
    }

    static ConversationView toView(ChatConversationEntity entity) {
        return new ConversationView(
                entity.getId(),
                entity.getTitle(),
                entity.isPinned(),
                entity.getOwnerUserId(),
                entity.getMessageRounds() == null ? 0 : entity.getMessageRounds(),
                entity.getTotalRounds() == null ? 0 : entity.getTotalRounds(),
                entity.getGenerationAttempts() == null ? 0 : entity.getGenerationAttempts(),
                entity.getCreatedAt(),
                entity.getLastActiveAt());
    }

    static StoredMessage toMessage(ChatMessageEntity entity) {
        return new StoredMessage(
                entity.getId(),
                entity.getSeq(),
                entity.getRole(),
                entity.getContent(),
                entity.getSources(),
                entity.isGapReported(),
                entity.getCreatedAt());
    }
}
