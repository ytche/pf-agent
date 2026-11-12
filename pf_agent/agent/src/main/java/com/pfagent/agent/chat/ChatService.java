package com.pfagent.agent.chat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pfagent.agent.conversation.ConversationAccessGuard;
import com.pfagent.agent.conversation.ConversationConflictException;
import com.pfagent.agent.conversation.ConversationDeletedException;
import com.pfagent.agent.conversation.ConversationQuotaExceededException;
import com.pfagent.agent.memory.AnonymousQuotaService;
import com.pfagent.agent.memory.ConversationStore;
import com.pfagent.agent.rag.PromptBuilder;
import com.pfagent.agent.rag.RetrievalTools;
import com.pfagent.agent.rag.SourceCollector;
import com.pfagent.agent.rag.TextSanitizer;
import com.pfagent.agent.rag.ToolCallRecorder;
import com.pfagent.agent.rag.ToolCallRecord;
import com.pfagent.agent.rag.ToolCallTracker;
import com.pfagent.agent.util.MapUtil;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.messages.AbstractMessage;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.ToolResponseMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.document.Document;
import org.springframework.ai.model.tool.DefaultToolCallingChatOptions;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.ToolCallbacks;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 核心问答服务 — 手动工具循环编排（设计 §8/§9）
 *
 * 检索改由 LLM 通过 3 个 @Tool 驱动，ChatService 不再预检索：
 *   - 每轮把 history（system + 注入前文 + user）交给 ChatClient，注册工具 schema
 *   - {@code internalToolExecutionEnabled(false)} 关闭框架自动执行 → 循环交给我们
 *   - 有 tool_call 则手动经 callbacksByName 执行，结果以 ToolResponseMessage 拼回
 *     history，进入下一轮；无 tool_call 则当前文本即最终回答
 *
 * 防线（双层中的主防线）：
 *   - maxToolRounds：循环轮次上限，超限强制收敛作答（与 maxHistoryChars 对称，不再抛 500）
 *   - maxHistoryChars：history 总字符上限，超限不再抛异常，而是强制 LLM 收敛作答（不再调工具）
 *   - 未注册工具名：框架级错误，LLM 无法自愈 → 直接抛
 *
 * 会话持久化（F-020 实施 Spec §5/§7）：模型历史读取与问答写入统一经
 * {@link ConversationStore}；ChatMemory 仅作兼容适配，不再有第二份写入逻辑。
 * 普通问答与重新生成都在调用模型前先过匿名配额并累计 generation_attempts
 * （失败也保留计数）；助手消息保存 cited-only 过滤与编号重映射后的来源快照。
 * 父会话删除后一律不自动重建：追加返回 PARENT_MISSING 时抛
 * {@link ConversationDeletedException}（410）。
 */
@Service
public class ChatService {

    private static final Logger log = LoggerFactory.getLogger(ChatService.class);

    /** LLM 空内容兜底（v1.5 C4） */
    private static final String EMPTY_ANSWER_FALLBACK = "（模型未返回回答内容，请重试）";

    /** 上下文超限时的强制收敛指令：让 LLM 基于已有结果直接作答，不再调工具 */
    private static final String CONVERGE_HINT =
            "检索上下文已达上限，请基于以上检索结果直接给出最终回答，不要再调用任何工具。"
            + "若数据不足以回答，请如实说明数据缺失。";

    /**
     * SP4 D5 + F-014：回答中的来源编号标记（group 1 为 # 后到闭合括号前的原始内容，用于判定合法性）。
     * 接受半角 [#N] 与全角/混用形态：［＃N］、[＃N]、［#N］，编号数字可为全角；输出一律重写为半角 [#N]。
     * 只匹配闭合形态：越界/畸形判定见 filterCitedSources；未闭合的 "[#"/"［＃" 按普通文本保留（登记已知语义）。
     */
    private static final Pattern CITATION_MARK =
            Pattern.compile("[\\[［][#＃]([^\\]］]*)[\\]］]");

    @Autowired
    private ChatClient chatClient;
    @Autowired
    private PromptBuilder promptBuilder;
    @Autowired
    private ConversationStore conversationStore;
    @Autowired
    private ConversationAccessGuard accessGuard;
    @Autowired
    private SourceCollector sourceCollector;
    @Autowired
    private RetrievalTools retrievalTools;
    @Autowired
    private ToolCallTracker toolCallTracker;
    @Autowired
    private ToolCallRecorder toolCallRecorder;
    @Autowired
    private ObjectProvider<AnonymousQuotaService> quotaServiceProvider;
    @Value("${pf.search.max-tool-rounds:10}")
    private int maxToolRounds;
    @Value("${pf.search.max-history-chars:50000}")
    private int maxHistoryChars;
    @Value("${pf.memory.history-size:20}")
    private int historySize;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private Map<String, ToolCallback> callbacksByName;

    /** 规则问答（匿名，兼容旧入口） */
    public ChatResponse ask(String question, String conversationId) {
        return ask(question, conversationId, null);
    }

    /**
     * 规则问答（手动工具循环）
     *
     * @param question       用户自然语言问题
     * @param conversationId 会话 ID；为空则生成新 UUID
     * @param ownerUserId    当前登录用户主键；匿名请求为 null（登录用户新建会话自动写入 owner）
     * @return LLM 回答 + cited-only 来源快照 + gap 标记 + 会话与助手消息定位
     */
    public ChatResponse ask(String question, String conversationId, Long ownerUserId) {
        boolean freshConversation = conversationId == null || conversationId.isBlank();
        String cid = freshConversation ? UUID.randomUUID().toString() : conversationId;
        log.info("收到问题: {} (会话 {})", question, cid);
        if (freshConversation) {
            conversationStore.createConversation(cid, ownerUserId, Instant.now());
        } else {
            accessGuard.requireReadable(cid, ownerUserId);
        }
        ensureQuotaAllowed(cid);
        if (conversationStore.incrementGenerationAttempts(cid) == 0) {
            throw new ConversationDeletedException(cid);
        }

        sourceCollector.begin();
        toolCallTracker.begin(cid, question);
        try {
            List<Message> history = buildInitialHistory(cid, question);
            AssistantMessage assistant = runAgent(history);
            AnswerResult result = buildAnswer(assistant.getText(), question);
            ConversationStore.AppendResult append;
            try {
                append = conversationStore.appendRound(
                        cid, question, result.answer(), serializeSources(result.sources()),
                        result.gapReported(), Instant.now());
            } catch (RuntimeException e) {
                // 对齐 SP1 D6：存储故障不打断问答主链路，本轮回答照常返回（不带消息定位）
                log.warn("会话 {} 问答落库失败，本轮回答照常返回但未持久化: {}", cid, e.getMessage());
                return new ChatResponse(result.answer(), result.sources(), result.gapReported(), cid);
            }
            if (append.status() == ConversationStore.AppendStatus.PARENT_MISSING) {
                log.warn("会话 {} 在生成本轮回答期间被删除，晚到结果已丢弃", cid);
                throw new ConversationDeletedException(cid);
            }
            return new ChatResponse(
                    result.answer(), result.sources(), result.gapReported(), cid,
                    append.assistant().id(), append.assistant().seq(), append.assistant().createdAt());
        } finally {
            // F-006：有工具调用则落盘（异常路径也落盘已产生的部分记录，不丢观测数据）
            // AKN-023：请求级摘要先取（drain 会清空状态）；无工具调用也写摘要，日志与 JSONL 同口径
            ToolCallTracker.RequestSummary requestSummary = toolCallTracker.summary().orElse(null);
            List<ToolCallRecord> toolCalls = toolCallTracker.drain();
            if (!toolCalls.isEmpty()) {
                toolCallRecorder.flush(toolCalls);
            }
            if (requestSummary != null) {
                toolCallRecorder.flushRequestSummary(requestSummary);
                logRequestTiming(requestSummary);
            }
            sourceCollector.clear(); // 异常路径兜底，防 ThreadLocal 残留
        }
    }

    /**
     * 重新生成最后一轮（F-020 实施 Spec §7.1）
     *
     * 只替换最后一条助手消息的正文、来源、缺口标记与完成时间，保持原消息 ID 与位置；
     * 不追加用户消息、不增加对话轮数。模型历史不包含即将被替换的旧助手回答。
     * expectedLastSeq 与 role=assistant 是终端条件：期间出现新消息或最后消息已变化
     * 返回 409；父会话已删除返回 410；失败不写入任何新内容。
     */
    public RegenerateResult regenerate(String conversationId, Long ownerUserId, Integer expectedLastSeq) {
        accessGuard.requireReadable(conversationId, ownerUserId);
        ConversationStore.LastRound lastRound = conversationStore.lastRound(conversationId)
                .orElseThrow(ConversationConflictException::new);
        int expected = expectedLastSeq == null ? lastRound.assistant().seq() : expectedLastSeq;
        if (lastRound.assistant().seq() != expected) {
            throw new ConversationConflictException();
        }
        ensureQuotaAllowed(conversationId);
        if (conversationStore.incrementGenerationAttempts(conversationId) == 0) {
            throw new ConversationDeletedException(conversationId);
        }

        sourceCollector.begin();
        // AKN-024：regenerate 没有新的用户轮次/范围确认，不能获得宽查询确认资格
        toolCallTracker.beginRegenerate(conversationId, lastRound.question());
        try {
            List<Message> history = buildRegenerateHistory(conversationId);
            AssistantMessage assistant = runAgent(history);
            AnswerResult result = buildAnswer(assistant.getText(), lastRound.question());
            ConversationStore.ReplaceResult replaced = conversationStore.replaceLastAssistant(
                    conversationId, expected, result.answer(), serializeSources(result.sources()),
                    result.gapReported(), Instant.now());
            if (replaced.status() == ConversationStore.ReplaceStatus.PARENT_MISSING) {
                log.warn("会话 {} 在重新生成期间被删除，晚到结果已丢弃", conversationId);
                throw new ConversationDeletedException(conversationId);
            }
            if (replaced.status() == ConversationStore.ReplaceStatus.CONFLICT) {
                throw new ConversationConflictException();
            }
            return new RegenerateResult(conversationId, replaced.assistant().id(),
                    replaced.assistant().seq(), result.answer(), result.sources(),
                    result.gapReported(), replaced.assistant().createdAt());
        } finally {
            // AKN-023：重新生成同样写请求级摘要并打日志（含网络），与 JSONL 同口径
            ToolCallTracker.RequestSummary requestSummary = toolCallTracker.summary().orElse(null);
            List<ToolCallRecord> toolCalls = toolCallTracker.drain();
            if (!toolCalls.isEmpty()) {
                toolCallRecorder.flush(toolCalls);
            }
            if (requestSummary != null) {
                toolCallRecorder.flushRequestSummary(requestSummary);
                logRequestTiming(requestSummary);
            }
            sourceCollector.clear();
        }
    }

    /** 重新生成结果：messageId 与重新生成前保持一致 */
    public record RegenerateResult(String conversationId, long messageId, int messageSeq, String answer,
                                   List<ChatResponse.SourceRef> sources, boolean gapReported,
                                   Instant completedAt) {
    }

    /** 工具注册表：@Tool 方法 → name → ToolCallback（手动循环按名查找执行）。依赖注入完成后组装。 */
    @PostConstruct
    void initToolRegistry() {
        Map<String, ToolCallback> map = new HashMap<>();
        for (ToolCallback cb : ToolCallbacks.from(retrievalTools)) {
            map.put(cb.getToolDefinition().name(), cb);
        }
        this.callbacksByName = Map.copyOf(map);
    }

    /** 构建初始 history：system 最前（v1.5 A2）+ 注入前文 + 当前问题 */
    private List<Message> buildInitialHistory(String cid, String question) {
        List<Message> history = new ArrayList<>();
        history.add(new SystemMessage(promptBuilder.buildSystemPrompt()));
        history.addAll(toMessages(conversationStore.history(cid, historySize)));
        history.add(new UserMessage(question));
        return history;
    }

    /**
     * 重新生成的模型历史：最近历史去掉最后一条（即将被替换的助手回答），
     * 末尾保留最后用户问题，不再追加重复问题。
     */
    private List<Message> buildRegenerateHistory(String cid) {
        List<ConversationStore.StoredMessage> stored =
                new ArrayList<>(conversationStore.history(cid, historySize + 1));
        if (!stored.isEmpty() && "assistant".equals(stored.get(stored.size() - 1).role())) {
            stored.remove(stored.size() - 1);
        }
        List<Message> history = new ArrayList<>();
        history.add(new SystemMessage(promptBuilder.buildSystemPrompt()));
        history.addAll(toMessages(stored));
        return history;
    }

    /** 存储消息 → Spring AI 消息（仅 user/assistant；未知角色跳过） */
    private static List<Message> toMessages(List<ConversationStore.StoredMessage> stored) {
        List<Message> messages = new ArrayList<>(stored.size());
        for (ConversationStore.StoredMessage row : stored) {
            switch (row.role()) {
                case "user" -> messages.add(new UserMessage(row.content()));
                case "assistant" -> messages.add(new AssistantMessage(row.content()));
                default -> {
                    // 非 user/assistant 不进入模型上下文
                }
            }
        }
        return messages;
    }

    /** 模型调用前统一匿名配额检查：普通问答与重新生成不得绕过（超限 429，零 token 成本） */
    private void ensureQuotaAllowed(String conversationId) {
        AnonymousQuotaService quotaService = quotaServiceProvider.getIfAvailable();
        if (quotaService != null && quotaService.isExceeded(conversationId)) {
            throw new ConversationQuotaExceededException(quotaService.getAnonymousRounds());
        }
    }

    /** 执行手动工具循环，返回最终 AssistantMessage（正常收敛或强制收敛） */
    private AssistantMessage runAgent(List<Message> history) {
        for (int round = 0; round < maxToolRounds; round++) {
            if (historyChars(history) > maxHistoryChars) {
                // 上下文超限：不再允许工具调用，强制 LLM 基于已有检索结果收敛作答
                return forceAnswer(history);
            }
            org.springframework.ai.chat.model.ChatResponse resp = callModel(history);
            AssistantMessage assistant = resp.getResult().getOutput();
            history.add(assistant); // 本轮 assistant（tool_call 或最终回答）
            if (!resp.hasToolCalls()) {
                return assistant;
            }
            history.add(new ToolResponseMessage(executeTools(assistant, round)));
        }
        // 轮次超限：不再抛 500，而是强制收敛作答（与上下文超限对称，F-002 复盘）
        return forceAnswer(history);
    }

    /**
     * 单轮 LLM 调用。返回完整响应而非 AssistantMessage，调用方需用
     * {@code resp.hasToolCalls()} 判定走「最终回答」还是「工具执行」分支。
     *
     * 两个关键选项的"为什么"：
     *  - messages 传快照副本：发送的是"本轮调用时点"的内容，避免客户端延迟序列化
     *    读到后续追加的 assistant/tool 消息（测试以捕获副本验证每轮边界）
     *  - internalToolExecutionEnabled(false)：关闭框架自动执行，工具循环交给我们手动编排
     */
    private org.springframework.ai.chat.model.ChatResponse callModel(List<Message> history) {
        long start = System.nanoTime();
        try {
            return chatClient.prompt()
                    .messages(List.copyOf(history))
                    .tools(callbacksByName.values().toArray(new ToolCallback[0])) // 每轮注册工具 schema
                    .options(DefaultToolCallingChatOptions.builder()
                            .internalToolExecutionEnabled(false)
                            .build())
                    .call()
                    .chatResponse();
        } finally {
            // AKN-023：LLM 调用端到端耗时（含网络），失败路径也计入
            toolCallTracker.recordLlmCall((System.nanoTime() - start) / 1_000_000);
        }
    }

    /** 上下文超限收敛：追加「基于已有结果作答」指令后，用无工具调用让 LLM 直接给出最终回答 */
    private AssistantMessage forceAnswer(List<Message> history) {
        history.add(new SystemMessage(CONVERGE_HINT));
        long start = System.nanoTime();
        try {
            return chatClient.prompt()
                    .messages(List.copyOf(history))
                    .call()
                    .chatResponse()
                    .getResult()
                    .getOutput();
        } finally {
            // AKN-023：强制收敛作答也是一次 LLM 调用，计入次数与累计耗时
            toolCallTracker.recordLlmCall((System.nanoTime() - start) / 1_000_000);
        }
    }

    /**
     * 手动执行本轮的全部工具调用。两个异常分支的"为什么"：
     *  - 未注册工具名：框架级错误，LLM 无法自愈 → 直接抛
     *  - 参数解析/执行失败（v1.5 B1）：不中断请求，作为工具结果返回，LLM 自纠后重试
     */
    private List<ToolResponseMessage.ToolResponse> executeTools(AssistantMessage assistant, int round) {
        List<ToolResponseMessage.ToolResponse> toolResults = new ArrayList<>();
        for (AssistantMessage.ToolCall tc : assistant.getToolCalls()) {
            ToolCallback callback = callbacksByName.get(tc.name());
            if (callback == null) {
                throw new IllegalStateException("LLM 调用了未注册的工具: " + tc.name());
            }
            // F-006 工具调用计数：nanoTime 包住执行段，成功/失败都记录（耗时=失败前耗时）
            long start = System.nanoTime();
            String result;
            boolean success = true;
            try {
                result = callback.call(tc.arguments());
            } catch (Exception e) {
                success = false;
                log.warn("工具 {} 执行失败: {}", tc.name(), e.getMessage());
                result = "工具执行失败: " + e.getMessage()
                        + "。请检查字段名与值格式后重试，可用字段见工具描述。";
            }
            long durationMs = (System.nanoTime() - start) / 1_000_000;
            toolCallTracker.record(tc.name(), tc.arguments(), success, durationMs,
                    result.length(), round);
            toolResults.add(new ToolResponseMessage.ToolResponse(tc.id(), tc.name(), result));
        }
        return toolResults;
    }

    /** history 字符数：ToolResponseMessage 统计各条工具结果，其余统计文本。
     *  原 v1.5 B3 用 getText() 漏算工具结果（ToolResponseMessage 未覆写 getText，textContent 恒空），
     *  导致 maxHistoryChars 上限失效、只能靠 15 轮硬兜底抛 500；此处修正统计口径。 */
    private long historyChars(List<Message> history) {
        long chars = 0;
        for (Message m : history) {
            if (m instanceof ToolResponseMessage trm) {
                chars += trm.getResponses().stream()
                        .mapToLong(r -> r.responseData() == null ? 0 : r.responseData().length())
                        .sum();
            } else if (m instanceof AbstractMessage am && am.getText() != null) {
                chars += am.getText().length();
            }
        }
        return chars;
    }

    /** 单轮回答结果：正文 + cited-only 来源 + gap 标记 */
    private record AnswerResult(String answer, List<ChatResponse.SourceRef> sources, boolean gapReported) {
    }

    /** 组装回答：空内容兜底 → 先读 gap 标记再 drain（drain 会清空请求状态）→ 引用治理 */
    private AnswerResult buildAnswer(String rawAnswer, String question) {
        String answer = (rawAnswer == null || rawAnswer.isBlank()) ? EMPTY_ANSWER_FALLBACK : rawAnswer;
        boolean gapReported = sourceCollector.wasGapReported();
        List<ChatResponse.SourceRef> allSources = sourceCollector.drain().stream()
                .map(this::toSourceRef)
                .toList();
        CitedResult cited = filterCitedSources(answer, allSources, question);
        return new AnswerResult(cited.answer(), cited.sources(), gapReported);
    }

    /** 引用快照序列化为 JSON 文本（空列表 = "[]"，序列化失败降级 null 并记 WARN） */
    private String serializeSources(List<ChatResponse.SourceRef> sources) {
        try {
            return objectMapper.writeValueAsString(sources == null ? List.of() : sources);
        } catch (Exception e) {
            log.warn("来源快照序列化失败，本条助手消息的来源置空: {}", e.getMessage());
            return null;
        }
    }

    /** filterCitedSources 的产物：重映射后的正文 + 只含被引用条目的来源列表 */
    private record CitedResult(String answer, List<ChatResponse.SourceRef> sources) {
    }

    /**
     * 引用治理试点（2026-10-01 用户拍板）：sources 只保留正文引用标记实际引用的条目，
     * 未引用条目删除不返回；正文中的标记按新下标重映射改写成半角 [#N]。
     *
     * 口径（维持 SP4 原定义，不扩到「参考了也算」）：
     *  - 标记形态接受半角 [#N] 与全角/混用形态（［＃N］、[＃N]、［#N］，数字可为全角），
     *    统一识别；输出一律半角 [#N]，不保留原始全角形态。
     *  - 有效引用 = 正文里纯数字且 1<=N<=原 sources 数的标记；越界（含 0）/畸形（非纯数字）
     *    标记从正文剥离、保留句子本身（SP4 D5 原行为，记 WARN）。
     *  - 保留来源保持原相对顺序（即原编号升序），新下标 = 保留序位次（1-based）；
     *    正文标记同步改写成新下标，编号 N ↔ sources 第 N 条的对齐不破坏。
     *  - 无有效引用（含正文无任何标记）时 sources=[]，前端自然不显示来源区；ChatResponse 结构不变。
     *
     * 已知代价（用户知情）：评测 score_citation 判「期望 chunk 是否出现在 sources」，
     * 硬过滤会让未被正文引用的 anchor 掉分（离线快照 easy-22 anchor idx63、medium-17 idx704）。
     */
    private CitedResult filterCitedSources(String answer, List<ChatResponse.SourceRef> sources, String question) {
        if (answer == null) {
            return new CitedResult(null, List.of());
        }
        int maxN = sources.size();

        // 第一遍：判定每个 [#N] 合法性，收集被引用的合法编号（去重、保首次出现），越界/畸形标记记下供日志
        LinkedHashSet<Integer> cited = new LinkedHashSet<>();
        List<String> stripped = new ArrayList<>();
        Matcher m = CITATION_MARK.matcher(answer);
        while (m.find()) {
            Integer n = parseCitation(m.group(1), maxN);
            if (n == null) {
                stripped.add(m.group());
            } else {
                cited.add(n);
            }
        }
        if (!stripped.isEmpty()) {
            log.warn("剥离越界/畸形来源编号 {}（来源上限 {}）— 问题摘要: {}",
                    stripped, maxN, summarize(question));
        }

        // 无有效引用：sources 置空，正文剥离全部 [#N] 标记（正文无标记时 replaceAll 为恒等）
        if (cited.isEmpty()) {
            return new CitedResult(CITATION_MARK.matcher(answer).replaceAll(""), List.of());
        }

        // 保留来源 + 旧编号 → 新下标 映射（原相对顺序 = 原编号升序）
        List<ChatResponse.SourceRef> kept = new ArrayList<>(cited.size());
        Map<Integer, Integer> remap = new HashMap<>();
        for (int old = 1; old <= maxN; old++) {
            if (cited.contains(old)) {
                kept.add(sources.get(old - 1));
                remap.put(old, kept.size());
            }
        }

        // 第二遍：重写正文——合法标记换新下标，越界/畸形标记剥离
        StringBuilder sb = new StringBuilder(answer.length());
        Matcher w = CITATION_MARK.matcher(answer);
        int last = 0;
        while (w.find()) {
            sb.append(answer, last, w.start());
            Integer n = parseCitation(w.group(1), maxN);
            if (n != null) {
                sb.append("[#").append(remap.get(n)).append(']');
            }
            last = w.end();
        }
        sb.append(answer, last, answer.length());
        return new CitedResult(sb.toString(), List.copyOf(kept));
    }

    /**
     * 解析引用编号：先把全角数字 ０-９ 归一为半角，再要求纯数字、位长 ≤9（int 上限内）
     * 且 1<=N<=maxN 才返回编号，否则返回 null（越界/畸形）。
     * 超长数字串（含溢出）直接判畸形剥除，防 NumberFormatException（SP4 D5 原判定）。
     */
    private Integer parseCitation(String body, int maxN) {
        String digits = toHalfWidthDigits(body);
        if (digits.matches("\\d+") && digits.length() <= 9) {
            int n = Integer.parseInt(digits);
            if (n >= 1 && n <= maxN) {
                return n;
            }
        }
        return null;
    }

    /** 全角数字 ０-９（U+FF10..U+FF19）转半角；其余字符原样保留，避免扩大既有合法性口径 */
    private static String toHalfWidthDigits(String body) {
        StringBuilder sb = new StringBuilder(body.length());
        for (int i = 0; i < body.length(); i++) {
            char c = body.charAt(i);
            sb.append(c >= '０' && c <= '９' ? (char) ('0' + (c - '０')) : c);
        }
        return sb.toString();
    }

    /** question 摘要（WARN 用）：超长截断到 30 字符，避免刷屏日志 */
    private String summarize(String text) {
        if (text == null) {
            return "";
        }
        return text.length() <= 30 ? text : text.substring(0, 30) + "…";
    }

    /** Document → 来源引用（供前端展示"来源书/路径/内容"；book 保留合并展示名兼容旧客户端）
     *
     * F-002 / KN-204 / KN-219：title 是展示标题兜底值（空 title → 已清洗正文的首个有效行 /
     * tocPath 末段），只在此组装处生成；正文兜底与卡片 content 用同一份 KN207 清洗结果，
     * 避免内部来源行从标题回流。tocPath、content 与检索匹配用的原始 title 元数据均不改写。 */
    private ChatResponse.SourceRef toSourceRef(Document doc) {
        var meta = doc.getMetadata();
        String bookNameCn = MapUtil.str(meta, "book_name_cn");
        String bookAbbreviation = MapUtil.str(meta, "book_abbreviation");
        String book = bookNameCn;
        if (!bookNameCn.isBlank() && !bookAbbreviation.isBlank() && !bookNameCn.equals(bookAbbreviation)) {
            book = bookNameCn + " (" + bookAbbreviation + ")";
        }
        String tocPath = MapUtil.str(meta, "tocPath");
        String chunkId = MapUtil.str(meta, "chunk_id");
        // KN207：SourceRef 内容剥离仓库内部整理路径行（数据侧保留，仅展示层剥离）
        String content = TextSanitizer.stripInternalSourceLine(doc.getText());
        return new ChatResponse.SourceRef(book, bookNameCn, bookAbbreviation,
                SourceTitleFormatter.displayTitle(MapUtil.str(meta, "title"), content, tocPath),
                tocPath, chunkId, content);
    }

    /** AKN-023 请求级耗时日志：总耗时、LLM 调用次数与累计端到端耗时（含网络）、工具耗时与轮次 */
    private void logRequestTiming(ToolCallTracker.RequestSummary summary) {
        log.info("[AKN-023] 会话 {} 请求 {} 问答耗时: 总 {}ms，LLM {} 次累计 {}ms（端到端，含网络），"
                        + "工具 {} 次累计 {}ms，工具轮次 {} — 问题: {}",
                summary.conversationId(), summary.requestId(), summary.totalDurationMs(),
                summary.llmCallCount(), summary.llmDurationMs(), summary.toolCallCount(),
                summary.toolTotalMs(), summary.toolRounds(), summarize(summary.question()));
    }

}
