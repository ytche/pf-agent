package com.pfagent.agent;

import com.pfagent.agent.rag.ClassDataLoader;
import com.pfagent.agent.rag.EquipmentDataLoader;
import com.pfagent.agent.rag.FeatDataLoader;
import com.pfagent.agent.rag.RaceDataLoader;
import com.pfagent.agent.rag.RuleDataLoader;
import com.pfagent.agent.rag.SkillDataLoader;
import com.pfagent.agent.rag.SpellDataLoader;
import com.pfagent.agent.rag.TraitDataLoader;
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.memory.InMemoryChatMemory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.client.ClientHttpRequestFactory;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class AgentApplicationTests {

    // 数据加载器用 mock 隔离：真实导入（法术/职业向量库构建）依赖本地 Ollama 且耗时
    // 数十分钟，不属于 contextLoads 的验证范围（导入逻辑由 ChunkImporterTest /
    // SpellDataLoaderTest 单独覆盖），避免单元测试被数据构建阻塞。
    @MockBean
    private ClassDataLoader classDataLoader;
    @MockBean
    private SpellDataLoader spellDataLoader;
    // 六个标准模块 DataLoader 同样用 mock 隔离：store 首次缺失时会真实导入
    // 22K chunks 并做 embedding（Ollama BGE-M3，数分钟以上），不属于 contextLoads
    // 的验证范围，避免集成测试被数据构建阻塞。
    @MockBean
    private FeatDataLoader featDataLoader;
    @MockBean
    private RaceDataLoader raceDataLoader;
    @MockBean
    private TraitDataLoader traitDataLoader;
    @MockBean
    private EquipmentDataLoader equipmentDataLoader;
    @MockBean
    private SkillDataLoader skillDataLoader;
    @MockBean
    private RuleDataLoader ruleDataLoader;

    @Autowired
    private InMemoryChatMemory chatMemory;
    @Autowired
    private ClientHttpRequestFactory clientHttpRequestFactory;

    @Test
    void contextLoads() {
        // 验证 Spring 上下文能正常启动（含双向量库 bean、检索服务、Web 层装配）
    }

    /** 验证 Spring 上下文装配了 L1 会话记忆（ChatMemory）与 LLM 调用超时 ClientHttpRequestFactory */
    @Test
    void contextLoadsAssemblesChatMemoryAndTimeoutClient() {
        // 设计 §13：L1 会话记忆 + LLM 调用超时（双层防线辅助层）
        assertThat(chatMemory).isNotNull();
        assertThat(clientHttpRequestFactory).isNotNull();
    }
}
