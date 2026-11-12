package com.pfagent.agent.memory;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * JdbcChatMemory 兼容适配测试（F-020 实施 Spec §5.2）
 *
 * ChatMemory 只作为既有接口的兼容入口，读写全部委托统一 ConversationStore：
 * - 父会话缺失时跳过写入并告警，绝不自动重建已删除会话；
 * - 消息读取与 20 轮裁剪语义以 Store 为准（本测试用内存 Store 执行同一契约，
 *   JDBC 具体实现由 ConversationStoreContractTest 覆盖）。
 */
class JdbcChatMemoryTest {

    private InMemoryConversationStore store;
    private JdbcChatMemory memory;

    @BeforeEach
    void setUp() {
        store = new InMemoryConversationStore();
        ReflectionTestUtils.setField(store, "historyRounds", 20);
        memory = new JdbcChatMemory();
        ReflectionTestUtils.setField(memory, "conversationStore", store);
    }

    /** 新会话必须先显式创建：适配层不得自动重建父行 */
    @Test
    void addDoesNotCreateMissingParentConversation() {
        memory.add("missing-cid", round(1));

        assertThat(store.getConversation("missing-cid")).isEmpty();
        assertThat(memory.get("missing-cid", 20)).isEmpty();
    }

    /** 父行存在时 add 委托 Store，get 按旧→新返回完整对 */
    @Test
    void addThenGetDelegatesToStore() {
        String cid = "cid-1";
        store.createConversation(cid, null, Instant.now());
        memory.add(cid, round(1));
        memory.add(cid, round(2));

        List<Message> history = memory.get(cid, 100);

        assertThat(history).hasSize(4);
        assertThat(((UserMessage) history.get(0)).getText()).isEqualTo("u1");
        assertThat(((AssistantMessage) history.get(3)).getText()).isEqualTo("a2");
        assertThat(store.getConversation(cid).orElseThrow().messageRounds()).isEqualTo(2);
    }

    /** get 的 lastN 只取最近 N 条（含跨轮截断） */
    @Test
    void getWithLastNReturnsMostRecentSlice() {
        String cid = "cid-2";
        store.createConversation(cid, null, Instant.now());
        memory.add(cid, round(1));
        memory.add(cid, round(2));
        memory.add(cid, round(3));

        List<Message> recent = memory.get(cid, 2);

        assertThat(recent).hasSize(2);
        assertThat(((UserMessage) recent.get(0)).getText()).isEqualTo("u3");
        assertThat(((AssistantMessage) recent.get(1)).getText()).isEqualTo("a3");
    }

    /** lastN ≤ 0 不查询直接返回空 */
    @Test
    void getWithNonPositiveLastNReturnsEmpty() {
        assertThat(memory.get("anything", 0)).isEmpty();
        assertThat(memory.get("anything", -1)).isEmpty();
    }

    /** 非 user/assistant 消息不进入 Store 历史 */
    @Test
    void addSkipsNonUserAssistantPair() {
        String cid = "cid-3";
        store.createConversation(cid, null, Instant.now());
        memory.add(cid, List.of(new SystemMessage("sys"), new SystemMessage("sys2")));

        assertThat(memory.get(cid, 10)).isEmpty();
    }

    /** clear 委托 Store 永久删除会话 */
    @Test
    void clearDeletesConversation() {
        String cid = "cid-4";
        store.createConversation(cid, null, Instant.now());
        memory.add(cid, round(1));

        memory.clear(cid);

        assertThat(store.getConversation(cid)).isEmpty();
        assertThat(memory.get(cid, 10)).isEmpty();
    }

    /** 第 21 轮起旧轮被裁剪，库内只保留最近 20 轮 */
    @Test
    void keepsOnlyRecentTwentyRounds() {
        String cid = "cid-5";
        store.createConversation(cid, null, Instant.now());
        for (int i = 1; i <= 21; i++) {
            memory.add(cid, round(i));
        }

        List<Message> history = memory.get(cid, 100);

        assertThat(history).hasSize(40);
        assertThat(((UserMessage) history.get(0)).getText()).isEqualTo("u2");
        assertThat(((AssistantMessage) history.get(39)).getText()).isEqualTo("a21");
    }

    private static List<Message> round(int n) {
        return List.of(new UserMessage("u" + n), new AssistantMessage("a" + n));
    }
}
