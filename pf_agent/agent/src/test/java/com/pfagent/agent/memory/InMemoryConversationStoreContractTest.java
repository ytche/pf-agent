package com.pfagent.agent.memory;

import org.junit.jupiter.api.BeforeEach;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * 内存版 ConversationStore 契约验证（与 JDBC 实现同一套断言）
 */
class InMemoryConversationStoreContractTest extends ConversationStoreContractTest {

    @BeforeEach
    void setUp() {
        InMemoryConversationStore inMemory = new InMemoryConversationStore();
        ReflectionTestUtils.setField(inMemory, "historyRounds", 20);
        store = inMemory;
    }
}
