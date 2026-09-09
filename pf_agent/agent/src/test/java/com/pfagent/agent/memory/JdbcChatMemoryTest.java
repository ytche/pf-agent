package com.pfagent.agent.memory;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * JdbcChatMemory 集成测试（@DataJpaTest + H2 内嵌库，SP1 T5）
 *
 * 用真实 Repository + Hibernate 建表验证读/写/清理语义与 F-005 20 轮裁剪边界。
 * JdbcChatMemory 是 @Component，slice 测试不自动装配，此处手动 new + 反射注入真仓库。
 *
 * 关闭 Flyway：V1__init.sql 是 PG 方言（TIMESTAMPTZ 等），H2 内嵌库跑不了；
 * 改由 Hibernate 按实体注解 create-drop 建表（表结构对齐——clear 显式删消息，
 * 不依赖 PG 外键级联，见 JdbcChatMemory.doClear）。
 *
 * 覆盖裁剪窗口制关键不变量：裁剪删除最小 seq 后 count ≠ max seq（seq 分配须以
 * max seq 为起点、窗口从 seq 最旧侧推进），这是把「count 当 max seq」会撞行/超轮的
 * 回归锁。
 */
@DataJpaTest(properties = "spring.flyway.enabled=false")
class JdbcChatMemoryTest {

    @Autowired
    private ChatMessageRepository messageRepository;
    @Autowired
    private ChatConversationRepository conversationRepository;
    @Autowired
    private PlatformTransactionManager transactionManager;

    private ChatMemory memory;

    @BeforeEach
    void setUp() {
        memory = new JdbcChatMemory();
        ReflectionTestUtils.setField(memory, "messageRepository", messageRepository);
        ReflectionTestUtils.setField(memory, "conversationRepository", conversationRepository);
        ReflectionTestUtils.setField(memory, "historyRounds", 20);
        ReflectionTestUtils.setField(memory, "transactionTemplate", new TransactionTemplate(transactionManager));
    }

    /** add 若干轮后 get 按旧→新返回完整对 */
    @Test
    void addThenGetReturnsAllRoundsInOrder() {
        String cid = UUID.randomUUID().toString();
        memory.add(cid, round(1));
        memory.add(cid, round(2));
        memory.add(cid, round(3));

        List<Message> history = memory.get(cid, 100);

        assertThat(history).hasSize(6);
        assertThat(((UserMessage) history.get(0)).getText()).isEqualTo("u1");
        assertThat(((AssistantMessage) history.get(1)).getText()).isEqualTo("a1");
        assertThat(((AssistantMessage) history.get(5)).getText()).isEqualTo("a3");
    }

    /** get 未知会话返回空（等价新会话） */
    @Test
    void getOnUnknownConversationReturnsEmpty() {
        List<Message> history = memory.get(UUID.randomUUID().toString(), 20);

        assertThat(history).isEmpty();
    }

    /** get 的 lastN 只取最近 N 条（含跨轮截断），旧→新顺序不变 */
    @Test
    void getWithLastNReturnsMostRecentSlice() {
        String cid = UUID.randomUUID().toString();
        memory.add(cid, round(1));
        memory.add(cid, round(2));
        memory.add(cid, round(3));

        List<Message> recent = memory.get(cid, 2);

        assertThat(recent).hasSize(2);
        assertThat(((UserMessage) recent.get(0)).getText()).isEqualTo("u3");
        assertThat(((AssistantMessage) recent.get(1)).getText()).isEqualTo("a3");
    }

    /** lastN ≤ 0 时不查库直接返回空 */
    @Test
    void getWithNonPositiveLastNReturnsEmpty() {
        String cid = UUID.randomUUID().toString();
        memory.add(cid, round(1));

        assertThat(memory.get(cid, 0)).isEmpty();
        assertThat(memory.get(cid, -1)).isEmpty();
    }

    /** 非 user/assistant 消息（system/tool）不落库：本轮只落 user/assistant 两条 */
    @Test
    void addSkipsSystemMessage() {
        String cid = UUID.randomUUID().toString();
        memory.add(cid, List.of(new UserMessage("问"), new SystemMessage("sys"), new AssistantMessage("答")));

        assertThat(memory.get(cid, 10)).hasSize(2);
        assertThat(messageRepository.countByConversationId(cid)).isEqualTo(2);
    }

    /** add 会新建会话并维护 lastActiveAt / messageRounds / totalRounds 冗余字段 */
    @Test
    void addUpdatesConversationMetadata() {
        String cid = UUID.randomUUID().toString();
        memory.add(cid, round(1));
        memory.add(cid, round(2));
        memory.add(cid, round(3));

        ChatConversationEntity conv = conversationRepository.findById(cid).orElseThrow();
        assertThat(conv.getMessageRounds()).isEqualTo(3);
        assertThat(conv.getTotalRounds()).isEqualTo(3);
        assertThat(conv.getCreatedAt()).isNotNull();
        assertThat(conv.getLastActiveAt()).isNotNull();
    }

    /** clear 显式删消息与会话（不依赖外键级联）：清空后 get 空、两表无残留 */
    @Test
    void clearRemovesConversationAndMessages() {
        String cid = UUID.randomUUID().toString();
        memory.add(cid, round(1));
        memory.add(cid, round(2));

        memory.clear(cid);

        assertThat(memory.get(cid, 10)).isEmpty();
        assertThat(messageRepository.countByConversationId(cid)).isZero();
        assertThat(conversationRepository.existsById(cid)).isFalse();
    }

    /** F-005 边界：满 20 轮（40 条）不裁剪，第 21 轮触发裁剪且恰好保留 20 轮 */
    @Test
    void trimStartsWhenExceedingHistoryRounds() {
        String cid = UUID.randomUUID().toString();
        for (int i = 1; i <= 20; i++) {
            memory.add(cid, round(i));
        }
        assertThat(messageRepository.countByConversationId(cid)).isEqualTo(40);

        memory.add(cid, round(21));

        assertThat(messageRepository.countByConversationId(cid)).isEqualTo(40);
        ChatConversationEntity conv = conversationRepository.findById(cid).orElseThrow();
        assertThat(conv.getMessageRounds()).isEqualTo(20);
        // SP2 F-011：total_rounds 累计不受 F-005 裁剪影响——message_rounds 钉在 20，
        // total_rounds 仍如实累计到 21（裁剪只删旧消息、不回写累计列）
        assertThat(conv.getTotalRounds()).isEqualTo(21);
        // 第 1 轮（seq 1,2）被裁掉，历史从第 2 轮开始
        List<Message> history = memory.get(cid, 200);
        assertThat(history).hasSize(40);
        assertThat(((UserMessage) history.get(0)).getText()).isEqualTo("u2");
        assertThat(((AssistantMessage) history.get(39)).getText()).isEqualTo("a21");
    }

    /** 裁剪后 seq 留下空洞，后续 add 不得复用 seq：窗口继续从 seq 最旧侧推进，恒 20 轮 */
    @Test
    void trimAdvancesWindowOnFurtherAdds() {
        String cid = UUID.randomUUID().toString();
        for (int i = 1; i <= 21; i++) {
            memory.add(cid, round(i));
        }
        memory.add(cid, round(22));

        assertThat(messageRepository.countByConversationId(cid)).isEqualTo(40);
        List<Message> history = memory.get(cid, 200);
        assertThat(history).hasSize(40);
        // 第 2 轮（seq 3,4）被裁掉，窗口推进到第 3 轮起；若无 max-seq 起点复用会撞 seq 导致 > 40
        assertThat(((UserMessage) history.get(0)).getText()).isEqualTo("u3");
        assertThat(((AssistantMessage) history.get(39)).getText()).isEqualTo("a22");
    }

    /** 一轮 = user + assistant 两条；roundN 第 N 轮文本用 uN/aN 标记便于断言裁剪窗口 */
    private static List<Message> round(int n) {
        return List.of(new UserMessage("u" + n), new AssistantMessage("a" + n));
    }
}
