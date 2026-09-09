package com.pfagent.agent.memory;

import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * JDBC 会话记忆（pf.chat.memory=jdbc 时装配，SP1 D4）
 *
 * 把 Spring AI {@link ChatMemory} 落到 PostgreSQL 两张表（chat_conversation / chat_message），
 * 实现会话跨重启保留（F-003）与轮数限制（F-005）。只落 [user, assistant] 对，工具调用
 * 中间态不落库，对齐现有 InMemoryChatMemory 语义。
 *
 * 错误处理（SP1 D6）：读写异常在此吞掉并记 warn——写失败本轮照常返回、读失败按空历史
 * 处理，保证会话记忆故障不打断问答主链路；真正连不上库由启动期 fail-fast 兜底。
 * 用编程式事务（TransactionTemplate）而非 @Transactional：注解事务的提交期异常在代理层
 * 抛出、方法内部无法捕获，会穿透到 ChatService；编程式事务把「写入 + 更新会话 + 裁剪」
 * 的整段回滚/提交异常都包在 try 内，才能在内部完成降级。
 */
@Component
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
public class JdbcChatMemory implements ChatMemory {

    private static final Logger log = LoggerFactory.getLogger(JdbcChatMemory.class);
    private static final String ROLE_USER = "user";
    private static final String ROLE_ASSISTANT = "assistant";

    @Autowired
    private ChatMessageRepository messageRepository;
    @Autowired
    private ChatConversationRepository conversationRepository;
    @Autowired
    private PlatformTransactionManager transactionManager;
    @Value("${pf.chat.history-rounds:20}")
    private int historyRounds;

    /** 编程式事务模板（见类注释：为何不用 @Transactional） */
    private TransactionTemplate transactionTemplate;

    @Override
    public void add(String conversationId, List<Message> messages) {
        try {
            // 编程式事务：写入/更新/裁剪同事务；内部异常被 TransactionTemplate 回滚后在此捕获
            transactionTemplate.executeWithoutResult(status -> doAdd(conversationId, messages));
        } catch (RuntimeException e) {
            log.warn("会话 {} 历史写入失败，本轮对话不受影响（该轮上下文不落库）: {}",
                    conversationId, e.getMessage());
        }
    }

    @Override
    public void clear(String conversationId) {
        try {
            transactionTemplate.executeWithoutResult(status -> doClear(conversationId));
        } catch (RuntimeException e) {
            log.warn("会话 {} 历史清理失败: {}", conversationId, e.getMessage());
        }
    }

    @Override
    public List<Message> get(String conversationId, int lastN) {
        if (lastN <= 0) {
            return List.of();
        }
        try {
            List<ChatMessageEntity> all = messageRepository.findByConversationIdOrderBySeqAsc(conversationId);
            if (all.isEmpty()) {
                return List.of();
            }
            List<ChatMessageEntity> recent =
                    all.size() > lastN ? all.subList(all.size() - lastN, all.size()) : all;
            return recent.stream().map(JdbcChatMemory::toMessage).filter(Objects::nonNull).toList();
        } catch (RuntimeException e) {
            log.warn("会话 {} 历史读取失败，按空历史处理（等价新会话）: {}", conversationId, e.getMessage());
            return List.of();
        }
    }

    /** 实体行还原为 Spring AI 消息（仅 user/assistant；未知角色返回 null 由调用方跳过） */
    private static Message toMessage(ChatMessageEntity row) {
        return switch (row.getRole()) {
            case ROLE_USER -> new UserMessage(row.getContent());
            case ROLE_ASSISTANT -> new AssistantMessage(row.getContent());
            default -> null;
        };
    }

    /** 消息类型归一为表内 role 值；非 user/assistant（system/tool 等）返回 null 不落库 */
    private static String toRole(Message message) {
        if (message instanceof UserMessage) {
            return ROLE_USER;
        }
        if (message instanceof AssistantMessage) {
            return ROLE_ASSISTANT;
        }
        return null;
    }

    @PostConstruct
    private void init() {
        this.transactionTemplate = new TransactionTemplate(transactionManager);
    }

    /**
     * 事务内执行写入：追加消息 → 超 historyRounds 轮裁剪最旧轮 → 刷新会话活跃时间与轮数。
     * 消息 seq 从现有最大（= 条数，因从 1 连续分配）之后递增；轮数 = 保留消息条数 / 2。
     * 新会话必须先落父行再写消息：chat_message 外键指向 chat_conversation，saveAll 消息时
     * 若父行尚未持久化会违反 FK（H2 由 Hibernate 建表无 FK，测试测不出，真 PG 兜底）。
     */
    private void doAdd(String conversationId, List<Message> messages) {
        Instant now = Instant.now();
        ChatConversationEntity conversation = conversationRepository.findById(conversationId)
                .orElseGet(() -> conversationRepository.save(new ChatConversationEntity(conversationId, now)));

        long base = messageRepository.countByConversationId(conversationId);
        // seq 分配以现有最大 seq 为起点：裁剪会删最小 seq 留下空洞，count ≠ max seq，
        // 若以 count 为起点会复用已存在的 seq 撞行
        int seq = messageRepository.findTopByConversationIdOrderBySeqDesc(conversationId)
                .map(ChatMessageEntity::getSeq)
                .orElse(0);
        List<ChatMessageEntity> rows = new ArrayList<>(messages.size());
        for (Message message : messages) {
            String role = toRole(message);
            if (role == null) {
                log.warn("会话 {} 跳过非 user/assistant 类型消息（{}）", conversationId,
                        message.getClass().getSimpleName());
                continue;
            }
            rows.add(new ChatMessageEntity(conversationId, ++seq, role, message.getText(), now));
        }
        if (!rows.isEmpty()) {
            messageRepository.saveAll(rows);
        }

        // F-005 裁剪：保留最近 historyRounds 轮 = 2 * historyRounds 条消息。
        // 窗口制删除 seq ≤ (本次末 seq − 上限)：即便历史留有空洞，下一轮继续从 seq 最旧侧
        // 推进窗口，库内恒保留最近 seq 的 2*historyRounds 条，无空洞下等价于删最旧多余轮。
        long total = base + rows.size();
        if (total > (long) historyRounds * 2) {
            messageRepository.deleteByConversationIdAndSeqLessThanEqual(
                    conversationId, seq - historyRounds * 2);
            total = (long) historyRounds * 2;
        }

        conversation.setLastActiveAt(now);
        conversation.setMessageRounds((int) (total / 2));
        // SP2 匿名配额（F-011）依据：total_rounds 累计会话生命周期轮数、永不裁剪。
        // 裁剪只删旧消息并收紧 message_rounds（钉在 historyRounds 上限），而累计值必须
        // 只增不减，故独立于上方 total 的裁剪收窄逻辑，按本轮新增消息对累加。
        conversation.setTotalRounds(conversation.getTotalRounds() + rows.size() / 2);
        conversationRepository.save(conversation);
    }

    /**
     * 事务内清空会话：先显式删消息再删会话行。
     * 不依赖 DB 外键级联（H2/PG 行为一致），schema 侧 CASCADE 仅作生产兜底。
     */
    private void doClear(String conversationId) {
        if (!conversationRepository.existsById(conversationId)) {
            return;
        }
        messageRepository.deleteByConversationId(conversationId);
        conversationRepository.deleteById(conversationId);
    }
}
