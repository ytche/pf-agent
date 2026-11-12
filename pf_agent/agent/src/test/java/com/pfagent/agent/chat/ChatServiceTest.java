package com.pfagent.agent.chat;

import com.pfagent.agent.conversation.ConversationAccessGuard;
import com.pfagent.agent.conversation.ConversationConflictException;
import com.pfagent.agent.conversation.ConversationDeletedException;
import com.pfagent.agent.conversation.ConversationQuotaExceededException;
import com.pfagent.agent.memory.AnonymousQuotaService;
import com.pfagent.agent.memory.ConversationStore;
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
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.ToolResponseMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.ai.chat.model.Generation;
import org.springframework.ai.document.Document;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.IntStream;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.spy;
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
    private ConversationStore conversationStore;
    @Mock
    private ConversationAccessGuard accessGuard;
    @Mock
    private ObjectProvider<AnonymousQuotaService> quotaServiceProvider;
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
        ConversationStore.ConversationView view = new ConversationStore.ConversationView(
                "cid", null, false, null, 0, 0, 0, Instant.EPOCH, Instant.EPOCH);
        lenient().when(accessGuard.requireReadable(anyString(), any())).thenReturn(view);
        lenient().when(conversationStore.history(anyString(), anyInt())).thenReturn(List.of());
        lenient().when(conversationStore.incrementGenerationAttempts(anyString())).thenReturn(1);
        lenient().when(conversationStore.createConversation(anyString(), any(), any()))
                .thenAnswer(inv -> new ConversationStore.ConversationView(
                        inv.getArgument(0), null, false, inv.getArgument(1), 0, 0, 0,
                        Instant.EPOCH, Instant.EPOCH));
        lenient().when(conversationStore.appendRound(anyString(), anyString(), anyString(),
                        nullable(String.class), anyBoolean(), any()))
                .thenAnswer(inv -> new ConversationStore.AppendResult(
                        ConversationStore.AppendStatus.OK,
                        new ConversationStore.StoredMessage(1L, 2, "assistant",
                                inv.getArgument(2), inv.getArgument(3), inv.getArgument(4),
                                inv.getArgument(5))));
    }

    private static <T> T nullable(Class<T> type) {
        return org.mockito.ArgumentMatchers.nullable(type);
    }

    /** AKN-024：普通 ask 是真实新用户轮次，具备宽查询确认资格 */
    @Test
    void askBeginsConfirmableUserTurn() {
        when(callResponseSpec.chatResponse()).thenReturn(answer("答"));
        ToolCallTracker spyTracker = spy(new ToolCallTracker());
        ChatService service = chatService(15, 50000, 20);
        ReflectionTestUtils.setField(service, "toolCallTracker", spyTracker);

        service.ask("q", "cid");

        verify(spyTracker).begin("cid", "q");
        verify(spyTracker, never()).beginRegenerate(anyString(), anyString());
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
        verify(conversationStore).history("cid-1", 20);
        verify(conversationStore).appendRound(eq("cid-1"), eq("火球术射程？"),
                eq("火球术射程为 400 英尺"), nullable(String.class), eq(false), any());
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
        verify(conversationStore).appendRound(eq("cid"), anyString(), anyString(),
                nullable(String.class), eq(false), any());
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
        verify(conversationStore).history(anyString(), anyInt());
        verify(conversationStore).createConversation(anyString(), org.mockito.ArgumentMatchers.isNull(), any());
    }

    /** 传入 conversationId 时透传、不回生成 */
    @Test
    void askProvidedConversationIdPassedThrough() {
        when(callResponseSpec.chatResponse()).thenReturn(answer("答"));

        ChatResponse resp = chatService(15, 50000, 20).ask("q", "cid-x");

        assertThat(resp.conversationId()).isEqualTo("cid-x");
        verify(accessGuard).requireReadable("cid-x", null);
        verify(conversationStore).history("cid-x", 20);
    }

    // ---------- gap / sources / 兜底 / 历史注入 ----------

    /** reportDataGap 工具记录缺口并标记 gapReported */
    @Test
    void askReportDataGapRecordsGapAndMarksReported() {
        when(recorder.record("女巫的XX", "{}", "缺数据")).thenReturn(true);
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
                answer("射程 400 英尺[#1]"));
        Document doc = Document.builder().text("法术正文")
                .metadata(Map.of("book_name_cn", "核心规则书", "book_abbreviation", "CRB",
                        "tocPath", "法术 > 火球术", "chunk_id", "spell_CRB_0001"))
                .build();
        when(searchService.search("火球术射程", "spell")).thenReturn(List.of(doc));

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术射程？", "cid");

        assertThat(resp.sources()).hasSize(1);
        ChatResponse.SourceRef source = resp.sources().get(0);
        assertThat(source.book()).isEqualTo("核心规则书 (CRB)");
        assertThat(source.bookNameCn()).isEqualTo("核心规则书");
        assertThat(source.bookAbbreviation()).isEqualTo("CRB");
        assertThat(source.tocPath()).isEqualTo("法术 > 火球术");
        assertThat(source.chunkId()).isEqualTo("spell_CRB_0001");
        assertThat(source.content()).isEqualTo("法术正文");
    }

    /** 官方/未知来源无书名元数据：结构化字段为空，book 兼容字段同样为空 */
    @Test
    void askSourceWithoutBookMetadataLeavesStructuredFieldsEmpty() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"官方勘误\",\"module\":\"spell\"}"),
                answer("官方说明[#1]"));
        Document doc = Document.builder().text("官方正文")
                .metadata(Map.of("chunk_id", "official_1"))
                .build();
        when(searchService.search("官方勘误", "spell")).thenReturn(List.of(doc));

        ChatResponse resp = chatService(15, 50000, 20).ask("官方勘误？", "cid");

        ChatResponse.SourceRef source = resp.sources().get(0);
        assertThat(source.book()).isEmpty();
        assertThat(source.bookNameCn()).isEmpty();
        assertThat(source.bookAbbreviation()).isEmpty();
    }

    /** 旧 JSONB 快照只有 book/tocPath/chunkId/content：Jackson 反序列化后结构化字段为 null，旧字段可读 */
    @Test
    void sourceRefReadsLegacySnapshotWithoutStructuredBookFields() throws Exception {
        String legacyJson = "{\"book\":\"核心规则书 (CRB)\",\"tocPath\":\"法术\",\"chunkId\":\"c1\",\"content\":\"正文\"}";

        ChatResponse.SourceRef ref = new com.fasterxml.jackson.databind.ObjectMapper()
                .readValue(legacyJson, ChatResponse.SourceRef.class);

        assertThat(ref.book()).isEqualTo("核心规则书 (CRB)");
        assertThat(ref.bookNameCn()).isNull();
        assertThat(ref.bookAbbreviation()).isNull();
        assertThat(ref.title()).isNull();
        assertThat(ref.tocPath()).isEqualTo("法术");
        assertThat(ref.chunkId()).isEqualTo("c1");
        assertThat(ref.content()).isEqualTo("正文");
    }

    /** KN207：SourceRef.content 剥离仓库内部整理路径行（数据侧保留，仅展示层剥离） */
    @Test
    void askSourceRefContentStripsInternalSourceLine() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"亡灵杀手特性\",\"module\":\"spell\"}"),
                answer("特性说明[#1]"));
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
        // 空 title 的正文兜底必须基于已清洗 content，内部来源行不得重新出现在展示标题
        assertThat(source.title()).isEqualTo("法术正文");
        assertThat(source.title()).doesNotContain("来源：");
        assertThat(source.title()).doesNotContain("未整理 →");
        // 展示层兜底不回调改写原始 Document
        assertThat(doc.getText()).contains("未整理 →");
    }

    /** F-002 / KN-204：空 title → 展示标题取正文首个有效行（去表格/Markdown 符号），tocPath 原样 */
    @Test
    void askSourceRefBlankTitleFallsBackToFirstBodyLine() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"追逐\",\"module\":\"rule\"}"),
                answer("追逐规则[#1]"));
        Document doc = Document.builder()
                .text("| --- | --- |\n|  |\n**追逐与休整**\n正文")
                .metadata(Map.of("title", "", "tocPath", "规则 > 追逐", "chunk_id", "rule_chase_0001"))
                .build();
        when(searchService.search("追逐", "rule")).thenReturn(List.of(doc));

        ChatResponse resp = chatService(15, 50000, 20).ask("追逐怎么跑？", "cid");

        ChatResponse.SourceRef source = resp.sources().get(0);
        assertThat(source.title()).isEqualTo("追逐与休整");
        assertThat(source.tocPath()).isEqualTo("规则 > 追逐");
        assertThat(source.content()).contains("正文");
    }

    /** F-002 / KN-219：非空长 title 展示时截断 60 字加省略号，去尾冒号 */
    @Test
    void askSourceRefLongAndColonTitleIsTrimmedForDisplay() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"长标题\",\"module\":\"rule\"}"),
                answer("规则[#1]"));
        String longTitle = "长".repeat(80) + "：";
        Document doc = Document.builder()
                .text("正文")
                .metadata(Map.of("title", longTitle, "tocPath", "规则 > 长标题", "chunk_id", "rule_long_0001"))
                .build();
        when(searchService.search("长标题", "rule")).thenReturn(List.of(doc));

        ChatResponse resp = chatService(15, 50000, 20).ask("长标题？", "cid");

        assertThat(resp.sources().get(0).title()).isEqualTo("长".repeat(60) + "…");
    }

    /** F-002：正文无有效文本时展示标题回退 tocPath 末段，tocPath 本身不改写 */
    @Test
    void askSourceRefNoMeaningfulBodyFallsBackToLastTocSegment() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"休整期\",\"module\":\"rule\"}"),
                answer("休整规则[#1]"));
        Document doc = Document.builder()
                .text("| --- | --- |\n\n***")
                .metadata(Map.of("title", " ", "tocPath", "规则 → 战斗 → 追逐与休整",
                        "chunk_id", "rule_rest_0001"))
                .build();
        when(searchService.search("休整期", "rule")).thenReturn(List.of(doc));

        ChatResponse resp = chatService(15, 50000, 20).ask("休整期做什么？", "cid");

        assertThat(resp.sources().get(0).title()).isEqualTo("追逐与休整");
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
        when(conversationStore.history("cid", 20)).thenReturn(List.of(
                new ConversationStore.StoredMessage(1L, 1, "user", "上轮问题", null, false, Instant.EPOCH)));
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

    /** AKN-023：工具记录带 requestId，请求级耗时只写一条 request_summary（字段名对齐 M34 脚本） */
    @Test
    void askRecordsRequestIdOnToolCallsAndWritesOneRequestSummary() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术射程\",\"module\":\"spell\"}"),
                answer("射程 400 英尺"));
        Document doc = Document.builder().text("正文").metadata(Map.of("title", "火球术")).build();
        when(searchService.search("火球术射程", "spell")).thenReturn(List.of(doc));

        chatService(15, 50000, 20).ask("火球术射程？", "cid");

        ArgumentCaptor<List<ToolCallRecord>> calls = ArgumentCaptor.forClass(List.class);
        ArgumentCaptor<ToolCallTracker.RequestSummary> summaryCaptor =
                ArgumentCaptor.forClass(ToolCallTracker.RequestSummary.class);
        verify(toolCallRecorder).flush(calls.capture());
        verify(toolCallRecorder).flushRequestSummary(summaryCaptor.capture());

        ToolCallTracker.RequestSummary summary = summaryCaptor.getValue();
        assertThat(summary.recordType()).isEqualTo("request_summary");
        assertThat(summary.llmCallCount()).isEqualTo(2); // 工具轮 + 最终回答轮
        assertThat(summary.llmDurationMs()).isGreaterThanOrEqualTo(0);
        assertThat(summary.totalDurationMs()).isGreaterThanOrEqualTo(0);
        assertThat(summary.toolCallCount()).isEqualTo(1);
        assertThat(summary.toolRounds()).isEqualTo(1);
        assertThat(calls.getValue()).allSatisfy(r ->
                assertThat(r.requestId()).isEqualTo(summary.requestId()));
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

    /** 无工具调用也必须写一条 request_summary（AKN-023），但不伪造工具调用记录 */
    @Test
    void askWithoutToolCallsWritesOnlyRequestSummary() {
        when(callResponseSpec.chatResponse()).thenReturn(answer("火球术射程为 400 英尺"));

        chatService(15, 50000, 20).ask("火球术射程？", "cid");

        verify(toolCallRecorder, never()).flush(anyList());
        ArgumentCaptor<ToolCallTracker.RequestSummary> captor =
                ArgumentCaptor.forClass(ToolCallTracker.RequestSummary.class);
        verify(toolCallRecorder).flushRequestSummary(captor.capture());
        assertThat(captor.getValue().llmCallCount()).isEqualTo(1);
        assertThat(captor.getValue().toolCallCount()).isZero();
    }

    /** 同会话两次问答：requestId 不同，报告可分开统计；工具记录归属各自请求 */
    @Test
    void askSameConversationTwiceEmitsDistinctRequestIds() {
        when(callResponseSpec.chatResponse()).thenReturn(
                answer("第一轮"), answer("第二轮"));

        ChatService service = chatService(15, 50000, 20);
        service.ask("问题一？", "cid");
        service.ask("问题二？", "cid");

        ArgumentCaptor<ToolCallTracker.RequestSummary> captor =
                ArgumentCaptor.forClass(ToolCallTracker.RequestSummary.class);
        verify(toolCallRecorder, times(2)).flushRequestSummary(captor.capture());
        assertThat(captor.getAllValues()).extracting(ToolCallTracker.RequestSummary::conversationId)
                .containsOnly("cid");
        assertThat(captor.getAllValues()).extracting(ToolCallTracker.RequestSummary::requestId)
                .doesNotHaveDuplicates();
    }

    // ---------- 引用治理试点（2026-10）：sources 只保留被引用条目 + 编号重映射；含 SP4 D5 越界/畸形剥离 ----------

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

    /** 未引用的来源删除不返回；正文 [#N] 按新下标重映射（保留项保原相对顺序） */
    @Test
    void askFiltersUnreferencedSourcesAndRemapsCitations() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术\",\"module\":\"spell\"}"),
                answer("甲[#1]；丙[#3]。"));   // 3 条来源只引用第 1、3 条
        Document d1 = Document.builder().text("正文1").metadata(Map.of("title", "甲", "chunk_id", "c1")).build();
        Document d2 = Document.builder().text("正文2").metadata(Map.of("title", "乙", "chunk_id", "c2")).build();
        Document d3 = Document.builder().text("正文3").metadata(Map.of("title", "丙", "chunk_id", "c3")).build();
        when(searchService.search("火球术", "spell")).thenReturn(List.of(d1, d2, d3));

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术？", "cid");

        // 只保留第 1、3 条，原相对顺序不变；第 3 条重映射为新下标 2
        assertThat(resp.sources()).extracting(ChatResponse.SourceRef::chunkId)
                .containsExactly("c1", "c3");
        assertThat(resp.answer()).isEqualTo("甲[#1]；丙[#2]。");
    }

    /** 引用乱序（先引后条）：来源仍按原相对顺序排列，正文标记按新下标改写 */
    @Test
    void askOutOfOrderCitationsKeepOriginalSourceOrder() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术\",\"module\":\"spell\"}"),
                answer("丙[#3]；甲[#1]。"));   // 先引第 3 条再引第 1 条
        Document d1 = Document.builder().text("正文1").metadata(Map.of("title", "甲", "chunk_id", "c1")).build();
        Document d2 = Document.builder().text("正文2").metadata(Map.of("title", "乙", "chunk_id", "c2")).build();
        Document d3 = Document.builder().text("正文3").metadata(Map.of("title", "丙", "chunk_id", "c3")).build();
        when(searchService.search("火球术", "spell")).thenReturn(List.of(d1, d2, d3));

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术？", "cid");

        assertThat(resp.sources()).extracting(ChatResponse.SourceRef::chunkId)
                .containsExactly("c1", "c3");
        assertThat(resp.answer()).isEqualTo("丙[#2]；甲[#1]。");
    }

    /** 重复引用同一来源：去重保留一条，正文所有该标记重映射为同一新下标 */
    @Test
    void askDuplicateCitationsRemapToSingleSource() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术\",\"module\":\"spell\"}"),
                answer("乙[#2]；又证乙[#2]。"));
        Document d1 = Document.builder().text("正文1").metadata(Map.of("title", "甲", "chunk_id", "c1")).build();
        Document d2 = Document.builder().text("正文2").metadata(Map.of("title", "乙", "chunk_id", "c2")).build();
        when(searchService.search("火球术", "spell")).thenReturn(List.of(d1, d2));

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术？", "cid");

        assertThat(resp.sources()).extracting(ChatResponse.SourceRef::chunkId).containsExactly("c2");
        assertThat(resp.answer()).isEqualTo("乙[#1]；又证乙[#1]。");
    }

    /** 正文无任何编号标记：全部来源视为未引用，sources 置空，正文原样 */
    @Test
    void askNoCitationDropsAllSources() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术\",\"module\":\"spell\"}"),
                answer("没有编号的回答。"));
        Document d1 = Document.builder().text("正文1").metadata(Map.of("title", "甲", "chunk_id", "c1")).build();
        Document d2 = Document.builder().text("正文2").metadata(Map.of("title", "乙", "chunk_id", "c2")).build();
        when(searchService.search("火球术", "spell")).thenReturn(List.of(d1, d2));

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术？", "cid");

        assertThat(resp.sources()).isEmpty();
        assertThat(resp.answer()).isEqualTo("没有编号的回答。");
    }



    /** 保存的 sources 快照 = cited-only 过滤与编号重映射后的当轮响应来源 */
    @Test
    void askPersistsCitedOnlySnapshotOfCurrentAnswer() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术\",\"module\":\"spell\"}"),
                answer("只看第二条 [#2]"));
        Document d1 = Document.builder().text("正文甲").metadata(Map.of("book_name_cn", "甲书", "chunk_id", "c1")).build();
        Document d2 = Document.builder().text("正文乙").metadata(Map.of("book_name_cn", "乙书", "chunk_id", "c2")).build();
        when(searchService.search("火球术", "spell")).thenReturn(List.of(d1, d2));
        ArgumentCaptor<String> sourcesJson = ArgumentCaptor.forClass(String.class);

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术？", "cid");

        assertThat(resp.answer()).isEqualTo("只看第二条 [#1]");
        assertThat(resp.sources()).hasSize(1);
        verify(conversationStore).appendRound(eq("cid"), anyString(), eq("只看第二条 [#1]"),
                sourcesJson.capture(), eq(false), any());
        assertThat(sourcesJson.getValue()).contains("乙书").doesNotContain("甲书");
        assertThat(sourcesJson.getValue()).contains("\"bookNameCn\":\"乙书\"");
    }

    // ---------- F-014 全角/混用引用标记：统一识别，输出重写为半角 [#N] ----------

    /** 全角括号 + 全角井号 + 全角数字：识别为合法引用，正文重写为半角 [#N] */
    @Test
    void askRecognizesFullWidthCitationsAndNormalizesOutput() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术\",\"module\":\"spell\"}"),
                answer("甲［＃１］；乙［＃２］。"));
        Document d1 = Document.builder().text("正文1").metadata(Map.of("title", "甲", "chunk_id", "c1")).build();
        Document d2 = Document.builder().text("正文2").metadata(Map.of("title", "乙", "chunk_id", "c2")).build();
        when(searchService.search("火球术", "spell")).thenReturn(List.of(d1, d2));

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术？", "cid");

        assertThat(resp.sources()).extracting(ChatResponse.SourceRef::chunkId).containsExactly("c1", "c2");
        assertThat(resp.answer()).isEqualTo("甲[#1]；乙[#2]。");
    }

    /** 半角/全角括号、井号、数字混用均按同一口径识别，输出统一半角 */
    @Test
    void askRecognizesMixedWidthCitationVariants() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术\",\"module\":\"spell\"}"),
                answer("甲［#1］；乙[＃2]；丙［＃３］。"));
        Document d1 = Document.builder().text("正文1").metadata(Map.of("title", "甲", "chunk_id", "c1")).build();
        Document d2 = Document.builder().text("正文2").metadata(Map.of("title", "乙", "chunk_id", "c2")).build();
        Document d3 = Document.builder().text("正文3").metadata(Map.of("title", "丙", "chunk_id", "c3")).build();
        when(searchService.search("火球术", "spell")).thenReturn(List.of(d1, d2, d3));

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术？", "cid");

        assertThat(resp.sources()).extracting(ChatResponse.SourceRef::chunkId)
                .containsExactly("c1", "c2", "c3");
        assertThat(resp.answer()).isEqualTo("甲[#1]；乙[#2]；丙[#3]。");
    }

    /** 多位全角数字/全角与半角数字混排：按数值解析（１２ 与 １2 都等于 12），重映射后去重 */
    @Test
    void askNormalizesMultiDigitFullWidthAndMixedDigits() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术\",\"module\":\"spell\"}"),
                answer("整条［＃１２］；混排［＃１2］。"));
        List<Document> docs = IntStream.rangeClosed(1, 12)
                .mapToObj(i -> Document.builder().text("正文" + i)
                        .metadata(Map.of("title", "条目" + i, "chunk_id", "c" + i)).build())
                .toList();
        when(searchService.search("火球术", "spell")).thenReturn(docs);

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术？", "cid");

        assertThat(resp.sources()).extracting(ChatResponse.SourceRef::chunkId).containsExactly("c12");
        assertThat(resp.answer()).isEqualTo("整条[#1]；混排[#1]。");
    }

    /** 全角越界/畸形标记（0 / 非数字 / 空 body / 越界）与半角一致剥离，合法标记保留并半角化 */
    @Test
    void askStripsOutOfRangeAndMalformedFullWidthCitations() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术\",\"module\":\"spell\"}"),
                answer("见［＃０］与［＃abc］说明［＃］，另［＃２］，依据［＃１］。"));
        Document doc = Document.builder().text("正文").metadata(Map.of("title", "甲", "chunk_id", "c1")).build();
        when(searchService.search("火球术", "spell")).thenReturn(List.of(doc));

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术？", "cid");

        assertThat(resp.sources()).extracting(ChatResponse.SourceRef::chunkId).containsExactly("c1");
        assertThat(resp.answer()).isEqualTo("见与说明，另，依据[#1]。");
    }

    /** 无来源时全角标记同样全部剥离，sources=[] */
    @Test
    void askNoSourcesStripsFullWidthCitations() {
        when(callResponseSpec.chatResponse()).thenReturn(answer("查无依据［＃１］，请参考其他资料"));

        ChatResponse resp = chatService(15, 50000, 20).ask("查不到的问题", "cid");

        assertThat(resp.sources()).isEmpty();
        assertThat(resp.answer()).isEqualTo("查无依据，请参考其他资料");
    }

    /** 快照保存的是全角识别、重映射后的半角正文与 cited-only 来源 */
    @Test
    void askPersistsRemappedFullWidthCitationSnapshot() {
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"火球术\",\"module\":\"spell\"}"),
                answer("只看第二条［＃２］"));
        Document d1 = Document.builder().text("正文甲").metadata(Map.of("book_name_cn", "甲书", "chunk_id", "c1")).build();
        Document d2 = Document.builder().text("正文乙").metadata(Map.of("book_name_cn", "乙书", "chunk_id", "c2")).build();
        when(searchService.search("火球术", "spell")).thenReturn(List.of(d1, d2));
        ArgumentCaptor<String> sourcesJson = ArgumentCaptor.forClass(String.class);

        ChatResponse resp = chatService(15, 50000, 20).ask("火球术？", "cid");

        assertThat(resp.answer()).isEqualTo("只看第二条[#1]");
        verify(conversationStore).appendRound(eq("cid"), anyString(), eq("只看第二条[#1]"),
                sourcesJson.capture(), eq(false), any());
        assertThat(sourcesJson.getValue()).contains("乙书").doesNotContain("甲书");
    }

    /** 重新生成路径同样先做全角识别与重映射再落快照 */
    @Test
    void regenerateNormalizesFullWidthCitationAndPersistsRemappedAnswer() {
        ConversationStore.StoredMessage user = new ConversationStore.StoredMessage(
                4L, 1, "user", "q1", null, false, Instant.EPOCH);
        ConversationStore.StoredMessage oldAssistant = new ConversationStore.StoredMessage(
                5L, 2, "assistant", "old", "[]", false, Instant.EPOCH);
        when(conversationStore.lastRound("cid")).thenReturn(Optional.of(
                new ConversationStore.LastRound(1, "q1", oldAssistant)));
        when(conversationStore.history("cid", 21)).thenReturn(List.of(user, oldAssistant));
        ArgumentCaptor<String> sourcesJson = ArgumentCaptor.forClass(String.class);
        when(conversationStore.replaceLastAssistant(eq("cid"), eq(2), anyString(),
                sourcesJson.capture(), anyBoolean(), any()))
                .thenAnswer(inv -> new ConversationStore.ReplaceResult(
                        ConversationStore.ReplaceStatus.OK,
                        new ConversationStore.StoredMessage(5L, 2, "assistant", inv.getArgument(2),
                                inv.getArgument(3), inv.getArgument(4), inv.getArgument(5))));
        when(callResponseSpec.chatResponse()).thenReturn(
                toolCall("vectorSearch", "{\"question\":\"q1\",\"module\":\"spell\"}"),
                answer("重答［＃１］"));
        Document doc = Document.builder().text("正文甲")
                .metadata(Map.of("book_name_cn", "甲书", "chunk_id", "c1")).build();
        when(searchService.search("q1", "spell")).thenReturn(List.of(doc));

        ChatService.RegenerateResult result = chatService(15, 50000, 20).regenerate("cid", null, 2);

        assertThat(result.answer()).isEqualTo("重答[#1]");
        assertThat(result.sources()).extracting(ChatResponse.SourceRef::chunkId).containsExactly("c1");
        verify(conversationStore).replaceLastAssistant(eq("cid"), eq(2), eq("重答[#1]"),
                sourcesJson.capture(), eq(false), any());
        assertThat(sourcesJson.getValue()).contains("甲书");
    }

    /** 请求期间会话被删除：晚到结果丢弃，抛 410 语义且不重建父行 */
    @Test
    void askLateDeleteReturnsDeletedWithoutRecreating() {
        when(callResponseSpec.chatResponse()).thenReturn(answer("late answer"));
        when(conversationStore.appendRound(anyString(), anyString(), anyString(),
                nullable(String.class), anyBoolean(), any()))
                .thenReturn(new ConversationStore.AppendResult(
                        ConversationStore.AppendStatus.PARENT_MISSING, null));

        assertThatThrownBy(() -> chatService(15, 50000, 20).ask("q", "cid"))
                .isInstanceOf(ConversationDeletedException.class);
        verify(conversationStore, never()).createConversation(anyString(), any(), any());
    }

    // ---------- F-020 重新生成 ----------

    /** 重新生成替换最后助手消息：不追加轮次、模型历史不含旧回答、保持消息 ID */
    @Test
    void regenerateReplacesLastAssistantWithoutAppendingRound() {
        ConversationStore.StoredMessage user = new ConversationStore.StoredMessage(
                4L, 1, "user", "q1", null, false, Instant.EPOCH);
        ConversationStore.StoredMessage oldAssistant = new ConversationStore.StoredMessage(
                5L, 2, "assistant", "old", "[]", false, Instant.EPOCH);
        when(conversationStore.lastRound("cid")).thenReturn(Optional.of(
                new ConversationStore.LastRound(1, "q1", oldAssistant)));
        when(conversationStore.history("cid", 21)).thenReturn(List.of(user, oldAssistant));
        when(conversationStore.replaceLastAssistant(eq("cid"), eq(2), anyString(),
                nullable(String.class), anyBoolean(), any()))
                .thenAnswer(inv -> new ConversationStore.ReplaceResult(
                        ConversationStore.ReplaceStatus.OK,
                        new ConversationStore.StoredMessage(5L, 2, "assistant", inv.getArgument(2),
                                inv.getArgument(3), inv.getArgument(4), inv.getArgument(5))));
        when(callResponseSpec.chatResponse()).thenReturn(answer("new answer"));

        ChatService.RegenerateResult result = chatService(15, 50000, 20).regenerate("cid", null, 2);

        assertThat(result.answer()).isEqualTo("new answer");
        assertThat(result.messageId()).isEqualTo(5L);
        assertThat(result.messageSeq()).isEqualTo(2);
        verify(conversationStore, never()).appendRound(anyString(), anyString(), anyString(),
                any(), anyBoolean(), any());
        verify(conversationStore).incrementGenerationAttempts("cid");
        ArgumentCaptor<List<Message>> captor = ArgumentCaptor.forClass(List.class);
        verify(requestSpec).messages(captor.capture());
        assertThat(captor.getValue()).noneMatch(m -> "old".equals(m.getText()));
    }

    /** AKN-024：regenerate 不是新用户轮次，必须走不可确认入口，不能凭新 requestId 自我放行 */
    @Test
    void regenerateBeginsNonConfirmableUserTurn() {
        ConversationStore.StoredMessage user = new ConversationStore.StoredMessage(
                4L, 1, "user", "q1", null, false, Instant.EPOCH);
        ConversationStore.StoredMessage oldAssistant = new ConversationStore.StoredMessage(
                5L, 2, "assistant", "old", "[]", false, Instant.EPOCH);
        when(conversationStore.lastRound("cid")).thenReturn(Optional.of(
                new ConversationStore.LastRound(1, "q1", oldAssistant)));
        when(conversationStore.history("cid", 21)).thenReturn(List.of(user, oldAssistant));
        when(conversationStore.replaceLastAssistant(eq("cid"), eq(2), anyString(),
                nullable(String.class), anyBoolean(), any()))
                .thenAnswer(inv -> new ConversationStore.ReplaceResult(
                        ConversationStore.ReplaceStatus.OK,
                        new ConversationStore.StoredMessage(5L, 2, "assistant", inv.getArgument(2),
                                inv.getArgument(3), inv.getArgument(4), inv.getArgument(5))));
        when(callResponseSpec.chatResponse()).thenReturn(answer("new answer"));
        ToolCallTracker spyTracker = spy(new ToolCallTracker());
        ChatService service = chatService(15, 50000, 20);
        ReflectionTestUtils.setField(service, "toolCallTracker", spyTracker);

        service.regenerate("cid", null, 2);

        verify(spyTracker).beginRegenerate("cid", "q1");
        verify(spyTracker, never()).begin(anyString(), anyString());
    }

    /** expectedLastSeq 与当前最后助手消息不符 → 409，且不调用模型、不增加尝试 */
    @Test
    void regenerateStaleExpectedSeqConflictsBeforeModelCall() {
        ConversationStore.StoredMessage oldAssistant = new ConversationStore.StoredMessage(
                5L, 2, "assistant", "old", "[]", false, Instant.EPOCH);
        when(conversationStore.lastRound("cid")).thenReturn(Optional.of(
                new ConversationStore.LastRound(1, "q1", oldAssistant)));

        assertThatThrownBy(() -> chatService(15, 50000, 20).regenerate("cid", null, 1))
                .isInstanceOf(ConversationConflictException.class);
        verify(conversationStore, never()).incrementGenerationAttempts(anyString());
        verify(conversationStore, never()).replaceLastAssistant(anyString(), anyInt(), anyString(),
                any(), anyBoolean(), any());
    }

    /** 模型已生成但替换时发现父会话被删除 → 410，晚到结果丢弃 */
    @Test
    void regenerateParentMissingAfterModelReturnsDeleted() {
        ConversationStore.StoredMessage oldAssistant = new ConversationStore.StoredMessage(
                5L, 2, "assistant", "old", "[]", false, Instant.EPOCH);
        when(conversationStore.lastRound("cid")).thenReturn(Optional.of(
                new ConversationStore.LastRound(1, "q1", oldAssistant)));
        when(conversationStore.replaceLastAssistant(eq("cid"), eq(2), anyString(),
                any(), anyBoolean(), any()))
                .thenReturn(new ConversationStore.ReplaceResult(
                        ConversationStore.ReplaceStatus.PARENT_MISSING, null));
        when(callResponseSpec.chatResponse()).thenReturn(answer("late"));

        assertThatThrownBy(() -> chatService(15, 50000, 20).regenerate("cid", null, 2))
                .isInstanceOf(ConversationDeletedException.class);
    }

    /** 模型失败保留旧回答：不调用替换写入 */
    @Test
    void regenerateModelFailureKeepsOldAnswer() {
        ConversationStore.StoredMessage oldAssistant = new ConversationStore.StoredMessage(
                5L, 2, "assistant", "old", "[]", false, Instant.EPOCH);
        when(conversationStore.lastRound("cid")).thenReturn(Optional.of(
                new ConversationStore.LastRound(1, "q1", oldAssistant)));
        when(callResponseSpec.chatResponse()).thenThrow(new IllegalStateException("LLM down"));

        assertThatThrownBy(() -> chatService(15, 50000, 20).regenerate("cid", null, 2))
                .isInstanceOf(IllegalStateException.class);
        verify(conversationStore, never()).replaceLastAssistant(anyString(), anyInt(), anyString(),
                any(), anyBoolean(), any());
    }

    /** 配额超限在模型调用前返回 429 语义，且不累计尝试 */
    @Test
    void regenerateQuotaExceededBeforeModelCall() {
        ConversationStore.StoredMessage oldAssistant = new ConversationStore.StoredMessage(
                5L, 2, "assistant", "old", "[]", false, Instant.EPOCH);
        when(conversationStore.lastRound("cid")).thenReturn(Optional.of(
                new ConversationStore.LastRound(1, "q1", oldAssistant)));
        AnonymousQuotaService quota = org.mockito.Mockito.mock(AnonymousQuotaService.class);
        when(quota.isExceeded("cid")).thenReturn(true);
        when(quota.getAnonymousRounds()).thenReturn(20);
        when(quotaServiceProvider.getIfAvailable()).thenReturn(quota);

        assertThatThrownBy(() -> chatService(15, 50000, 20).regenerate("cid", null, 2))
                .isInstanceOf(ConversationQuotaExceededException.class);
        verify(conversationStore, never()).incrementGenerationAttempts(anyString());
    }

    private ChatService chatService(int maxRounds, int maxHistoryChars, int historySize) {
        ChatService s = new ChatService();
        ReflectionTestUtils.setField(s, "chatClient", chatClient);
        ReflectionTestUtils.setField(s, "promptBuilder", promptBuilder);
        ReflectionTestUtils.setField(s, "conversationStore", conversationStore);
        ReflectionTestUtils.setField(s, "accessGuard", accessGuard);
        ReflectionTestUtils.setField(s, "quotaServiceProvider", quotaServiceProvider);
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
