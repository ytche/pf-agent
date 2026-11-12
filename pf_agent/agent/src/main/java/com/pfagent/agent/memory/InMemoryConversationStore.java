package com.pfagent.agent.memory;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;

/**
 * 内存版统一会话存储（pf.chat.memory=memory，F-020 实施 Spec §5）
 *
 * 提供与 JDBC 实现完全一致的接口与语义（含引用快照、20 轮裁剪、认领与
 * generation_attempts 配额计数），但数据只在本次进程运行期有效，重启后清空。
 * 登录/认领/跨设备能力本身依赖用户表，memory 模式不可用（AuthProperties 已拦截）。
 */
@Component
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "memory", matchIfMissing = true)
public class InMemoryConversationStore implements ConversationStore {

    private static final int MAX_PAGE_SIZE = 100;
    private static final int DEFAULT_TITLE_LENGTH = 30;

    private final Map<String, InMemoryConversation> conversations = new LinkedHashMap<>();
    private final AtomicLong messageIds = new AtomicLong();

    @Autowired
    @org.springframework.beans.factory.annotation.Value("${pf.chat.history-rounds:20}")
    private int historyRounds;

    @Override
    public synchronized ConversationView createConversation(String id, Long ownerUserId, Instant now) {
        InMemoryConversation conversation = conversations.computeIfAbsent(id,
                key -> new InMemoryConversation(key, now, ownerUserId));
        return conversation.view();
    }

    @Override
    public synchronized Optional<ConversationView> getConversation(String id) {
        return Optional.ofNullable(conversations.get(id)).map(InMemoryConversation::view);
    }

    @Override
    public synchronized ConversationPage listOwnedConversations(Long ownerUserId, String cursor, int limit) {
        int size = limit <= 0 ? 30 : Math.min(limit, MAX_PAGE_SIZE);
        int requested = parseCursor(cursor);
        int offset = (requested / size) * size;
        List<ConversationView> all = conversations.values().stream()
                .filter(c -> ownerUserId != null && ownerUserId.equals(c.ownerUserId) && c.messageRounds > 0)
                .sorted(Comparator.comparing((InMemoryConversation c) -> c.pinned).reversed()
                        .thenComparing((InMemoryConversation c) -> c.lastActiveAt, Comparator.reverseOrder())
                        .thenComparing(c -> c.id, Comparator.reverseOrder()))
                .map(InMemoryConversation::view)
                .toList();
        if (offset >= all.size()) {
            return new ConversationPage(List.of(), null);
        }
        List<ConversationView> items = all.subList(offset, Math.min(offset + size, all.size()));
        int next = offset + items.size();
        return new ConversationPage(List.copyOf(items), next < all.size() ? Integer.toString(next) : null);
    }

    @Override
    public synchronized List<ConversationView> lookupConversations(List<String> ids) {
        if (ids == null) {
            return List.of();
        }
        List<ConversationView> views = new ArrayList<>();
        for (String id : ids.stream().filter(i -> i != null && !i.isBlank()).distinct().toList()) {
            InMemoryConversation conversation = conversations.get(id);
            if (conversation != null && conversation.ownerUserId == null && conversation.messageRounds > 0) {
                views.add(conversation.view());
            }
        }
        return views;
    }

    @Override
    public synchronized boolean renameConversation(String id, String title) {
        InMemoryConversation conversation = conversations.get(id);
        if (conversation == null) {
            return false;
        }
        conversation.title = title;
        return true;
    }

    @Override
    public synchronized boolean setPinned(String id, boolean pinned) {
        InMemoryConversation conversation = conversations.get(id);
        if (conversation == null) {
            return false;
        }
        conversation.pinned = pinned;
        return true;
    }

    @Override
    public synchronized boolean deleteConversation(String id) {
        return conversations.remove(id) != null;
    }

    @Override
    public synchronized ClaimStatus claimConversation(String id, Long ownerUserId) {
        InMemoryConversation conversation = conversations.get(id);
        if (conversation == null) {
            return ClaimStatus.NOT_FOUND;
        }
        if (conversation.ownerUserId == null) {
            conversation.ownerUserId = ownerUserId;
            return ClaimStatus.CLAIMED;
        }
        return ownerUserId.equals(conversation.ownerUserId)
                ? ClaimStatus.ALREADY_OWNER
                : ClaimStatus.OWNED_BY_OTHER;
    }

    @Override
    public synchronized List<StoredMessage> history(String id, int lastMessages) {
        if (lastMessages <= 0) {
            return List.of();
        }
        InMemoryConversation conversation = conversations.get(id);
        if (conversation == null) {
            return List.of();
        }
        List<StoredMessage> messages = conversation.messages;
        int from = Math.max(0, messages.size() - lastMessages);
        return List.copyOf(messages.subList(from, messages.size()));
    }

    @Override
    public synchronized Optional<LastRound> lastRound(String id) {
        InMemoryConversation conversation = conversations.get(id);
        if (conversation == null || conversation.messages.size() < 2) {
            return Optional.empty();
        }
        StoredMessage assistant = conversation.messages.get(conversation.messages.size() - 1);
        StoredMessage user = conversation.messages.get(conversation.messages.size() - 2);
        if (!"assistant".equals(assistant.role()) || !"user".equals(user.role())) {
            return Optional.empty();
        }
        return Optional.of(new LastRound(user.seq(), user.content(), assistant));
    }

    @Override
    public synchronized AppendResult appendRound(String id, String question, String answer,
                                                 String sourcesJson, boolean gapReported, Instant now) {
        InMemoryConversation conversation = conversations.get(id);
        if (conversation == null) {
            return new AppendResult(AppendStatus.PARENT_MISSING, null);
        }
        int lastSeq = conversation.messages.isEmpty()
                ? 0 : conversation.messages.get(conversation.messages.size() - 1).seq();
        StoredMessage user = new StoredMessage(
                messageIds.incrementAndGet(), lastSeq + 1, "user", question, null, false, now);
        StoredMessage assistant = new StoredMessage(
                messageIds.incrementAndGet(), lastSeq + 2, "assistant", answer, sourcesJson, gapReported, now);
        conversation.messages.add(user);
        conversation.messages.add(assistant);
        while (conversation.messages.size() > historyRounds * 2) {
            conversation.messages.remove(0);
        }
        conversation.messageRounds = Math.min(historyRounds, conversation.messageRounds + 1);
        conversation.totalRounds++;
        conversation.lastActiveAt = now;
        if (conversation.title == null || conversation.title.isBlank()) {
            conversation.title = defaultTitle(question);
        }
        return new AppendResult(AppendStatus.OK, assistant);
    }

    @Override
    public synchronized ReplaceResult replaceLastAssistant(String id, int expectedAssistantSeq, String answer,
                                                           String sourcesJson, boolean gapReported, Instant now) {
        InMemoryConversation conversation = conversations.get(id);
        if (conversation == null) {
            return new ReplaceResult(ReplaceStatus.PARENT_MISSING, null);
        }
        if (conversation.messages.isEmpty()) {
            return new ReplaceResult(ReplaceStatus.CONFLICT, null);
        }
        int lastIndex = conversation.messages.size() - 1;
        StoredMessage last = conversation.messages.get(lastIndex);
        if (last.seq() != expectedAssistantSeq || !"assistant".equals(last.role())) {
            return new ReplaceResult(ReplaceStatus.CONFLICT, null);
        }
        StoredMessage replaced = new StoredMessage(
                last.id(), last.seq(), "assistant", answer, sourcesJson, gapReported, now);
        conversation.messages.set(lastIndex, replaced);
        conversation.lastActiveAt = now;
        return new ReplaceResult(ReplaceStatus.OK, replaced);
    }

    @Override
    public synchronized int incrementGenerationAttempts(String id) {
        InMemoryConversation conversation = conversations.get(id);
        if (conversation == null) {
            return 0;
        }
        return ++conversation.generationAttempts;
    }

    @Override
    public synchronized int generationAttempts(String id) {
        InMemoryConversation conversation = conversations.get(id);
        return conversation == null ? 0 : conversation.generationAttempts;
    }

    @Override
    public synchronized long countOwnedConversations(Long ownerUserId) {
        return conversations.values().stream()
                .filter(c -> ownerUserId != null && ownerUserId.equals(c.ownerUserId) && c.messageRounds > 0)
                .count();
    }

    private static int parseCursor(String cursor) {
        if (cursor == null || cursor.isBlank()) {
            return 0;
        }
        try {
            return Math.max(Integer.parseInt(cursor.trim()), 0);
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    private static String defaultTitle(String question) {
        if (question == null) {
            return null;
        }
        String trimmed = question.strip();
        return trimmed.length() <= DEFAULT_TITLE_LENGTH ? trimmed : trimmed.substring(0, DEFAULT_TITLE_LENGTH);
    }

    private static final class InMemoryConversation {
        private final String id;
        private final Instant createdAt;
        private Instant lastActiveAt;
        private String title;
        private boolean pinned;
        private Long ownerUserId;
        private int messageRounds;
        private int totalRounds;
        private int generationAttempts;
        private final List<StoredMessage> messages = new ArrayList<>();

        private InMemoryConversation(String id, Instant now, Long ownerUserId) {
            this.id = id;
            this.createdAt = now;
            this.lastActiveAt = now;
            this.ownerUserId = ownerUserId;
        }

        private ConversationView view() {
            return new ConversationView(id, title, pinned, ownerUserId, messageRounds, totalRounds,
                    generationAttempts, createdAt, lastActiveAt);
        }
    }
}
