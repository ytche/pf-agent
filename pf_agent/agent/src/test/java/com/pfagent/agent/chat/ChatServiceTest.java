package com.pfagent.agent.chat;

import com.pfagent.agent.rag.DataGapRecorder;
import com.pfagent.agent.rag.FilterTranslator;
import com.pfagent.agent.rag.PromptBuilder;
import com.pfagent.agent.rag.RetrievalTools;
import com.pfagent.agent.rag.SearchService;
import com.pfagent.agent.rag.SourceCollector;
import com.pfagent.agent.rag.ToolCallRecorder;
import com.pfagent.agent.rag.ToolCallRecord;
import com.pfagent.agent.rag.ToolCallTracker;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.ToolResponseMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.model.Generation;
import org.springframework.ai.document.Document;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ChatService 单元测试 — 手动工具循环编排（设计 §8/§9）
 *
 * 覆盖：
 *  - 无工具调用 → 直接返回回答 + 回存 ChatMemory
 *  - 有工具调用 → callbacksByName 手动执行 → ToolResponseMessage 拼回 history → 下轮
 *  - maxRounds 超限 / 上下文超限 → 强制收敛作答；未注册工具 → 抛 IllegalStateException
 *  - conversationId：空 → 生成 UUID；传入 → 透传
 *  - reportDataGap 工具 → gapReported 透出；sources 来自 SourceCollector 汇总
 *  - LLM 空内容兜底；历史从 ChatMemory 注入（system 最前）
 */
@ExtendWith(MockitoExtension.class)
class ChatServiceTest {

    @Mock
    private ChatClient chatClient;
    @Mock
    private ChatClient.ChatClientRequestSpec requestSpec;
    @Mock
    private ChatClient.CallResponseSpec callResponseSpec;
    @Mock
    private SearchService searchService;
    @Mock
    private DataGapRecorder recorder;
    @Mock
    private ChatMemory chatMemory;
    @Mock
    private ToolCallRecorder toolCallRecorder;

    private final SourceCollector collector = new SourceCollector();
    private final ToolCallTracker toolCallTracker = new ToolCallTracker();
    private final PromptBuilder promptBuilder = new PromptBuilder();
    private final FilterTranslator translator = new FilterTranslator();
    private RetrievalTools retrievalTools;

    @BeforeEach
    void setUp() {
        retrievalTools = new RetrievalTools();
        ReflectionTestUtils.setField(retrievalTools, "searchService", searchService);
        ReflectionTestUtils.setField(retrievalTools, "collector", collector);
        ReflectionTestUtils.setField(retrievalTools, "recorder", recorder);
        ReflectionTestUtils.setField(retrievalTools, "filterTranslator", translator);
        ReflectionTestUtils.setField(retrievalTools, "vectorResultChars", 100);
        // fluent 链 lenient：个别用例（异常路径）不走完整链，宽松避免 UnnecessaryStubbing
        lenient().when(chatClient.prompt()).thenReturn(requestSpec);
        lenient().when(requestSpec.messages(anyList())).thenReturn(requestSpec);
        // tools(ToolCallbackProvider...)：ToolCallback[] 协变匹配；显式类型避免 List<> 重载歧义
        lenient().when(requestSpec.tools(any(ToolCallback[].class))).thenReturn(requestSpec);
        lenient().when(requestSpec.options(any())).thenReturn(requestSpec);
        lenient().when(requestSpec.call()).thenReturn(callResponseSpec);
    }

    /** 无工具调用的单轮问答：直接返回回答并回存 ChatMemory */
    @Test
    void askSingleRoundNoToolReturnsAnswerAndStoresMemory() {
        when(callResponseSpec.chatResponse()).thenReturn(answer("火球术射程为 400 英尺"));

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术射程？", "cid-1");

        assertThat(resp.answer()).isEqualTo("火球术射程为 400 英尺");
        assertThat(resp.conversationId()).isEqualTo("cid-1");
        assertThat(resp.gapReported()).isFalse();
        assertThat(resp.sources()).isEmpty();
        verify(chatMemory).get("cid-1", 20);
        verify(chatMemory).add(eq("cid-1"), anyList());
    }

    /** 工具调用后手动执行，ToolResponseMessage 拼回 history，第二轮拿到回答 */
    @Test
    void askToolCallExecutedAndAppendedToHistoryForSecondRound() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术射程\",\"module\":\"spell\"}"),
                answer("射程 400 英尺"));
        Document doc = Document.builder().text("正文").metadata(Map.of("title", "火球术")).build();
        when(searchService.search("火球术射程", "spell")).thenReturn(List.of(doc));

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术射程？", "cid");

        assertThat(resp.answer()).isEqualTo("射程 400 英尺");
        // 工具结果作为 ToolResponseMessage 拼回第二轮 history
        ArgumentCaptor<List<Message>> captor = ArgumentCaptor.forClass(List.class);
        verify(requestSpec, times(2)).messages(captor.capture());
        List<Message> secondRound = captor.getAllValues().get(1);
        assertThat(secondRound).anyMatch(m -> m instanceof ToolResponseMessage);
        assertThat(secondRound).last().isInstanceOf(ToolResponseMessage.class);
        verify(chatMemory).add(eq("cid"), anyList());
    }

    // ---------- 防线：循环超限 / 上下文超限 / 未注册工具 ----------

    /** 工具循环超过 maxRounds 上限 → 强制收敛作答（不再抛 500） */
    @Test
    void askToolLoopExceedingMaxRoundsForcesConvergeAnswer() {
        // 前 maxRounds 轮永远返回工具调用，永不自然收敛
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"q\",\"module\":\"spell\"}"),
                toolCall("vectorSearch", "{\"question\":\"q\",\"module\":\"spell\"}"),
                answer("收敛回答"));   // forceAnswer 的无工具调用返回最终回答
        when(searchService.search(anyString(), anyString())).thenReturn(List.of());

        ChatResponse resp = chatService(2, 50000, 20).ask("q", "cid");

        assertThat(resp.answer()).isEqualTo("收敛回答");
    }

    /** 首轮历史即超限（system+user 超上限）→ 强制无工具作答，不再硬抛异常 */
    @Test
    void askContextOverflowForcesConvergeAnswer() {
        when(callResponseSpec.chatResponse()).thenReturn(answer("收敛回答"));

        ChatResponse resp = chatService(15, 10, 20).ask("q", "cid");

        assertThat(resp.answer()).isEqualTo("收敛回答");
    }

    /** 工具结果累积使历史超限时，下一轮强制收敛作答（修复漏算后真正触发，而非硬抛 500） */
    @Test
    void askToolResultsOverflowForcesConvergeAnswer() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"q\",\"module\":\"spell\"}"),
                answer("收敛回答"));
        Document doc = Document.builder().text("x".repeat(10000)).metadata(Map.of("title", "t")).build();
        when(searchService.search(anyString(), anyString())).thenReturn(List.of(doc));

        ChatResponse resp = chatService(15, 5000, 20).ask("q", "cid");

        assertThat(resp.answer()).isEqualTo("收敛回答");
    }

    /** historyChars 正确统计 ToolResponseMessage 的工具结果字符（修复 getText 漏算 bug） */
    @Test
    void historyCharsCountsToolResponseData() {
        ChatService s = chatService(15, 50000, 20);
        String toolData = "工具返回的结果内容";
        List<Message> history = List.of(
                new SystemMessage("系统提示"),
                new UserMessage("问题"),
                new ToolResponseMessage(List.of(
                        new ToolResponseMessage.ToolResponse("id-1", "vectorSearch", toolData))));

        Long chars = (Long) ReflectionTestUtils.invokeMethod(s, "historyChars", history);

        assertThat(chars).isEqualTo((long) ("系统提示".length() + "问题".length() + toolData.length()));
    }

    /** LLM 调用未注册的工具时抛异常 */
    @Test
    void askUnregisteredToolCallThrows() {
        when(callResponseSpec.chatResponse()).thenReturn(toolCall("hack_tool", "{}"));

        assertThatThrownBy(() -> chatService(15, 50000, 20).ask("q", "cid"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("未注册的工具");
    }

    // ---------- conversationId ----------

    /** conversationId 为空时生成新 UUID */
    @Test
    void askBlankConversationIdGeneratesNewUuid() {
        when(callResponseSpec.chatResponse()).thenReturn(answer("答"));

        ChatResponse resp = chatService(15, 50000, 20).ask("q", null);

        // Java 17 无 UUID.regexPattern()，用标准格式正则校验
        assertThat(resp.conversationId())
                .matches("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");
        verify(chatMemory).get(anyString(), anyInt());
    }

    /** 传入 conversationId 时透传、不回生成 */
    @Test
    void askProvidedConversationIdPassedThrough() {
        when(callResponseSpec.chatResponse()).thenReturn(answer("答"));

        ChatResponse resp = chatService(15, 50000, 20).ask("q", "cid-x");

        assertThat(resp.conversationId()).isEqualTo("cid-x");
        verify(chatMemory).get("cid-x", 20);
    }

    // ---------- gap / sources / 兜底 / 历史注入 ----------

    /** reportDataGap 工具记录缺口并标记 gapReported */
    @Test
    void askReportDataGapRecordsGapAndMarksReported() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("reportDataGap", "{\"question\":\"女巫的XX\",\"attemptedFilters\":\"{}\",\"reason\":\"缺数据\"}"),
                answer("抱歉缺少相关知识"));

        ChatResponse resp = chatService(15, 50000, 20).ask("女巫的XX？", "cid");

        assertThat(resp.gapReported()).isTrue();
        assertThat(resp.answer()).isEqualTo("抱歉缺少相关知识");
        verify(recorder).record("女巫的XX", "{}", "缺数据");
    }

    /** 工具命中来源后汇总进响应 sources */
    @Test
    void askToolHitSourcesMergedIntoSources() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术射程\",\"module\":\"spell\"}"),
                answer("射程 400 英尺"));
        Document doc = Document.builder().text("法术正文")
                .metadata(Map.of("book_name_cn", "核心规则书", "book_abbreviation", "CRB",
                        "tocPath", "法术 > 火球术", "chunk_id", "spell_CRB_0001"))
                .build();
        when(searchService.search("火球术射程", "spell")).thenReturn(List.of(doc));

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术射程？", "cid");

        assertThat(resp.sources()).hasSize(1);
        ChatResponse.SourceRef source = resp.sources().get(0);
        assertThat(source.book()).isEqualTo("核心规则书 (CRB)");
        assertThat(source.tocPath()).isEqualTo("法术 > 火球术");
        assertThat(source.chunkId()).isEqualTo("spell_CRB_0001");
        assertThat(source.content()).isEqualTo("法术正文");
    }

    /** KN207：SourceRef.content 剥离仓库内部整理路径行（数据侧保留，仅展示层剥离） */
    @Test
    void askSourceRefContentStripsInternalSourceLine() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"亡灵杀手特性\",\"module\":\"spell\"}"),
                answer("特性说明"));
        Document doc = Document.builder()
                .text("> 来源：亡灵杀手手册（Undead Slayer's Handbook），页码见原书，未整理 → 亡灵杀手手册 → 法术\n法术正文")
                .metadata(Map.of("book_name_cn", "亡灵杀手手册", "book_abbreviation", "USH",
                        "tocPath", "法术 > 亡灵杀手", "chunk_id", "spell_USH_0001"))
                .build();
        when(searchService.search("亡灵杀手特性", "spell")).thenReturn(List.of(doc));

        ChatResponse resp = chatService(15, 50000, 20).ask("亡灵杀手特性？", "cid");

        assertThat(resp.sources()).hasSize(1);
        ChatResponse.SourceRef source = resp.sources().get(0);
        assertThat(source.content()).doesNotContain("未整理 →");
        assertThat(source.content()).doesNotContain("> 来源：亡灵杀手手册");
        assertThat(source.content()).contains("法术正文");
    }

    /** LLM 返回空内容时兜底提示 */
    @Test
    void askBlankAnswerFallsBackToHint() {
        when(callResponseSpec.chatResponse()).thenReturn(answer(""));

        ChatResponse resp = chatService(15, 50000, 20).ask("q", "cid");

        assertThat(resp.answer()).isEqualTo("（模型未返回回答内容，请重试）");
    }

    /** 历史来自 ChatMemory 注入且在 system 消息之后 */
    @Test
    void askHistoryInjectedFromMemoryAfterSystem() {
        when(chatMemory.get("cid", 20)).thenReturn(List.of(new UserMessage("上轮问题")));
        when(callResponseSpec.chatResponse()).thenReturn(answer("答"));

        chatService(15, 50000, 20).ask("本轮问题", "cid");

        ArgumentCaptor<List<Message>> captor = ArgumentCaptor.forClass(List.class);
        verify(requestSpec).messages(captor.capture());
        List<Message> history = captor.getValue();
        assertThat(history).hasSize(3);
        assertThat(history.get(0)).isInstanceOf(SystemMessage.class);   // ① system 最前
        assertThat(history.get(1)).isInstanceOf(UserMessage.class);     // ② 前文
        assertThat(((UserMessage) history.get(1)).getText()).isEqualTo("上轮问题");
        assertThat(history.get(2)).isInstanceOf(UserMessage.class);     // ③ 当前问题
        assertThat(((UserMessage) history.get(2)).getText()).isEqualTo("本轮问题");
    }

    // ---------- F-006 工具调用计数 ----------

    /** 有工具调用：executeTools 记录每条调用明细，出口 flush 落盘 */
    @Test
    void askWithToolCallsRecordsEachCallAndFlushes() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术射程\",\"module\":\"spell\"}"),
                answer("射程 400 英尺"));
        Document doc = Document.builder().text("正文").metadata(Map.of("title", "火球术")).build();
        when(searchService.search("火球术射程", "spell")).thenReturn(List.of(doc));

        chatService(15, 50000, 20).ask("火球术射程？", "cid");

        ArgumentCaptor<List<ToolCallRecord>> captor = ArgumentCaptor.forClass(List.class);
        verify(toolCallRecorder).flush(captor.capture());
        List<ToolCallRecord> records = captor.getValue();
        assertThat(records).hasSize(1);
        ToolCallRecord r = records.get(0);
        assertThat(r.toolName()).isEqualTo("vectorSearch");
        assertThat(r.arguments()).contains("火球术射程");
        assertThat(r.conversationId()).isEqualTo("cid");
        assertThat(r.question()).isEqualTo("火球术射程？");
        assertThat(r.success()).isTrue();
        assertThat(r.round()).isZero();
        assertThat(r.durationMs()).isGreaterThanOrEqualTo(0);
        assertThat(r.resultChars()).isGreaterThan(0);
        assertThat(r.id()).startsWith("tc-");
    }

    /** 工具执行失败：仍记录（success=false，耗时=失败前耗时），不中断回答 */
    @Test
    void askToolCallFailureStillRecordedWithSuccessFalse() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"q\",\"module\":\"spell\"}"),
                answer("回答"));
        when(searchService.search(anyString(), anyString()))
                .thenThrow(new RuntimeException("store 损坏"));

        ChatResponse resp = chatService(15, 50000, 20).ask("q", "cid");

        assertThat(resp.answer()).isEqualTo("回答"); // 失败不中断：错误信息喂给 LLM 自纠
        ArgumentCaptor<List<ToolCallRecord>> captor = ArgumentCaptor.forClass(List.class);
        verify(toolCallRecorder).flush(captor.capture());
        assertThat(captor.getValue().get(0).success()).isFalse();
        assertThat(captor.getValue().get(0).toolName()).isEqualTo("vectorSearch");
    }

    /** 无工具调用：不落盘（无工具调用则无观测数据，复盘只看有检索的问答） */
    @Test
    void askWithoutToolCallsDoesNotFlush() {
        when(callResponseSpec.chatResponse()).thenReturn(answer("火球术射程为 400 英尺"));

        chatService(15, 50000, 20).ask("火球术射程？", "cid");

        verify(toolCallRecorder, never()).flush(anyList());
    }

    // ---------- SP4 D5：越界/畸形来源编号剥离 ----------

    /** 合法编号保留、越界编号（N > sources 数）剥离但句子本身保留 */
    @Test
    void askStripsOutOfRangeCitationButKeepsSentence() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术射程\",\"module\":\"spell\"}"),
                answer("火球术射程 400 英尺[#2]，依据规则[#1]。"));   // 仅 1 条来源，#2 越界
        Document doc = Document.builder().text("正文").metadata(Map.of("title", "火球术", "chunk_id", "c1")).build();
        when(searchService.search("火球术射程", "spell")).thenReturn(List.of(doc));

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术射程？", "cid");

        assertThat(resp.sources()).hasSize(1);
        assertThat(resp.answer()).isEqualTo("火球术射程 400 英尺，依据规则[#1]。");
    }

    /** 畸形（0 / 空 / 含字母）编号标记剥离，保留正文 */
    @Test
    void askStripsMalformedAndZeroCitations() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术射程\",\"module\":\"spell\"}"),
                answer("见[#0]与[#abc]说明[#]。"));   // 1 条来源：0 越界、abc 非数字、空 body
        Document doc = Document.builder().text("正文").metadata(Map.of("title", "火球术", "chunk_id", "c1")).build();
        when(searchService.search("火球术射程", "spell")).thenReturn(List.of(doc));

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术射程？", "cid");

        assertThat(resp.answer()).isEqualTo("见与说明。");
    }

    /** 合法编号连写 [#1][#2] 原样保留、不重排不补插 */
    @Test
    void askKeepsValidCitationsUntouched() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术\",\"module\":\"spell\"}"),
                answer("火球术射程[#1]；大火球[#2]。"));
        Document d1 = Document.builder().text("正文1").metadata(Map.of("title", "火球术", "chunk_id", "c1")).build();
        Document d2 = Document.builder().text("正文2").metadata(Map.of("title", "大火球", "chunk_id", "c2")).build();
        when(searchService.search("火球术", "spell")).thenReturn(List.of(d1, d2));

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术？", "cid");

        assertThat(resp.sources()).hasSize(2);
        assertThat(resp.answer()).isEqualTo("火球术射程[#1]；大火球[#2]。");
    }

    /** 无来源（空 sources）：回答中的全部编号标记剥离（防错挂孤立编号） */
    @Test
    void askNoSourcesStripsAllCitations() {
        when(callResponseSpec.chatResponse()).thenReturn(answer("查无依据[#1]，请参考其他资料"));

        ChatResponse resp = chatService(15, 50000, 20).ask("查不到的问题", "cid");

        assertThat(resp.sources()).isEmpty();
        assertThat(resp.answer()).isEqualTo("查无依据，请参考其他资料");
    }

    private ChatService chatService(int maxRounds, int maxHistoryChars, int historySize) {
        ChatService s = new ChatService();
        ReflectionTestUtils.setField(s, "chatClient", chatClient);
        ReflectionTestUtils.setField(s, "promptBuilder", promptBuilder);
        ReflectionTestUtils.setField(s, "chatMemory", chatMemory);
        ReflectionTestUtils.setField(s, "sourceCollector", collector);
        ReflectionTestUtils.setField(s, "retrievalTools", retrievalTools);
        ReflectionTestUtils.setField(s, "toolCallTracker", toolCallTracker);
        ReflectionTestUtils.setField(s, "toolCallRecorder", toolCallRecorder);
        ReflectionTestUtils.setField(s, "maxToolRounds", maxRounds);
        ReflectionTestUtils.setField(s, "maxHistoryChars", maxHistoryChars);
        ReflectionTestUtils.setField(s, "historySize", historySize);
        s.initToolRegistry();
        return s;
    }

    /** 无工具调用的 LLM 响应 */
    private org.springframework.ai.chat.model.ChatResponse answer(String text) {
        return new org.springframework.ai.chat.model.ChatResponse(
                List.of(new Generation(new AssistantMessage(text))));
    }

    /** 含单个工具调用的 LLM 响应 */
    private org.springframework.ai.chat.model.ChatResponse toolCall(String name, String args) {
        return new org.springframework.ai.chat.model.ChatResponse(List.of(new Generation(
                new AssistantMessage(null, Map.of(),
                        List.of(new AssistantMessage.ToolCall("call-1", "function", name, args))))));
    }

    // ---------- 基础链路 ----------
}
