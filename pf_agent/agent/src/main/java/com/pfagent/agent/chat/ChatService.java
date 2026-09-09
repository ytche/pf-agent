package com.pfagent.agent.chat;

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
import org.springframework.ai.chat.memory.ChatMemory;
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
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
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
 * 记忆（L1，手动 ChatMemory）：请求入口注入前文、出口只回存 [user, assistant]
 * 问答对（工具调用消息不入记忆，后续回合重新调工具）。
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
     * SP4 D5：回答中的来源编号标记形态 [#N]（group 1 为 # 后到 ] 前的原始内容，用于判定合法性）。
     * 只匹配闭合形态：越界/畸形判定见 stripInvalidCitations；未闭合的 "[#" 按普通文本保留（登记已知语义）。
     */
    private static final Pattern CITATION_MARK = Pattern.compile("\\[#([^\\]]*)]");

    @Autowired
    private ChatClient chatClient;
    @Autowired
    private PromptBuilder promptBuilder;
    @Autowired
    private ChatMemory chatMemory;
    @Autowired
    private SourceCollector sourceCollector;
    @Autowired
    private RetrievalTools retrievalTools;
    @Autowired
    private ToolCallTracker toolCallTracker;
    @Autowired
    private ToolCallRecorder toolCallRecorder;
    @Value("${pf.search.max-tool-rounds:10}")
    private int maxToolRounds;
    @Value("${pf.search.max-history-chars:50000}")
    private int maxHistoryChars;
    @Value("${pf.memory.history-size:20}")
    private int historySize;
    private Map<String, ToolCallback> callbacksByName;

    /**
     * 规则问答（手动工具循环）
     *
     * @param question       用户自然语言问题
     * @param conversationId 会话 ID；为空则生成新 UUID
     * @return LLM 回答 + 来源列表 + gap 标记 + conversationId
     */
    public ChatResponse ask(String question, String conversationId) {
        String cid = (conversationId == null || conversationId.isBlank())
                ? UUID.randomUUID().toString()
                : conversationId;
        log.info("收到问题: {} (会话 {})", question, cid);
        sourceCollector.begin();
        toolCallTracker.begin(cid, question);
        try {
            List<Message> history = buildInitialHistory(cid, question);

            for (int round = 0; round < maxToolRounds; round++) {
                if (historyChars(history) > maxHistoryChars) {
                    // 上下文超限：不再允许工具调用，强制 LLM 基于已有检索结果收敛作答
                    return finish(question, forceAnswer(history), cid);
                }

                org.springframework.ai.chat.model.ChatResponse resp = callModel(history);
                AssistantMessage assistant = resp.getResult().getOutput();
                history.add(assistant); // 本轮 assistant（tool_call 或最终回答）

                if (!resp.hasToolCalls()) {
                    return finish(question, assistant, cid);
                }

                history.add(new ToolResponseMessage(executeTools(assistant, round)));
            }
            // 轮次超限：不再抛 500，而是强制收敛作答（与上下文超限对称，F-002 复盘）
            return finish(question, forceAnswer(history), cid);
        } finally {
            // F-006：有工具调用则落盘（异常路径也落盘已产生的部分记录，不丢观测数据）
            List<ToolCallRecord> toolCalls = toolCallTracker.drain();
            if (!toolCalls.isEmpty()) {
                toolCallRecorder.flush(toolCalls);
            }
            sourceCollector.clear(); // 异常路径兜底，防 ThreadLocal 残留
        }
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
        history.addAll(chatMemory.get(cid, historySize));
        history.add(new UserMessage(question));
        return history;
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
        return chatClient.prompt()
                .messages(List.copyOf(history))
                .tools(callbacksByName.values().toArray(new ToolCallback[0])) // 每轮注册工具 schema
                .options(DefaultToolCallingChatOptions.builder()
                        .internalToolExecutionEnabled(false)
                        .build())
                .call()
                .chatResponse();
    }

    /** 上下文超限收敛：追加「基于已有结果作答」指令后，用无工具调用让 LLM 直接给出最终回答 */
    private AssistantMessage forceAnswer(List<Message> history) {
        history.add(new SystemMessage(CONVERGE_HINT));
        return chatClient.prompt()
                .messages(List.copyOf(history))
                .call()
                .chatResponse()
                .getResult()
                .getOutput();
    }

    /**
     * 收尾：空回答兜底 → 记忆回存 → 组装响应。
     * 仅回存 user + 最终回答（工具调用消息不入记忆，后续回合重新调工具）。
     */
    private ChatResponse finish(String question, AssistantMessage assistant, String cid) {
        String answer = (assistant.getText() == null || assistant.getText().isBlank())
                ? EMPTY_ANSWER_FALLBACK
                : assistant.getText();
        chatMemory.add(cid, List.of(new UserMessage(question), assistant));
        return buildResponse(answer, cid, question);
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

    /** 组装响应：先读 gap 标记再 drain（drain 会清空请求状态）；SP4 D5：组装前剥离越界来源编号 */
    private ChatResponse buildResponse(String answer, String cid, String question) {
        boolean gapReported = sourceCollector.wasGapReported();
        List<ChatResponse.SourceRef> sources = sourceCollector.drain().stream()
                .map(this::toSourceRef)
                .toList();
        String cleaned = stripInvalidCitations(answer, sources, question);
        return new ChatResponse(cleaned, sources, gapReported, cid);
    }

    /**
     * SP4 D5：后端兜底剥离回答中越界/畸形来源编号标记 [#N]。
     * 1<=N<=sources.size() 的合法编号原样保留；越界（含 0）或畸形（非纯数字，如空/含字母）
     * 标记从正文移除、保留句子本身，并记 WARN（question 摘要 + 被剥标记）。不重排、不补插、
     * 不改 sources 顺序——LLM 漏标时后端不替它补号（非目标，来源折叠区照常展示）。
     */
    private String stripInvalidCitations(String answer, List<ChatResponse.SourceRef> sources, String question) {
        if (answer == null || answer.indexOf("[#") < 0) {
            return answer;
        }
        StringBuilder sb = new StringBuilder();
        Matcher m = CITATION_MARK.matcher(answer);
        int last = 0;
        int maxN = sources.size();
        List<String> stripped = new ArrayList<>();
        while (m.find()) {
            sb.append(answer, last, m.start());
            String body = m.group(1);
            boolean valid = false;
            // 纯数字且位长 ≤9（int 上限内）才 parse；超长数字串（含溢出）直接判畸形剥除，防 NumberFormatException
            if (body.matches("\\d+") && body.length() <= 9) {
                int n = Integer.parseInt(body);
                valid = n >= 1 && n <= maxN;
            }
            if (valid) {
                sb.append(m.group());
            } else {
                stripped.add(m.group());
            }
            last = m.end();
        }
        sb.append(answer, last, answer.length());
        if (!stripped.isEmpty()) {
            log.warn("剥离越界/畸形来源编号 {}（来源上限 {}）— 问题摘要: {}",
                    stripped, maxN, summarize(question));
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

    /** Document → 来源引用（供前端展示"来源书/路径/内容"） */
    private ChatResponse.SourceRef toSourceRef(Document doc) {
        var meta = doc.getMetadata();
        String book = MapUtil.str(meta, "book_name_cn");
        String abbr = MapUtil.str(meta, "book_abbreviation");
        if (!book.isBlank() && !abbr.isBlank() && !book.equals(abbr)) {
            book = book + " (" + abbr + ")";
        }
        String tocPath = MapUtil.str(meta, "tocPath");
        String chunkId = MapUtil.str(meta, "chunk_id");
        // KN207：SourceRef 内容剥离仓库内部整理路径行（数据侧保留，仅展示层剥离）
        return new ChatResponse.SourceRef(book, tocPath, chunkId,
                TextSanitizer.stripInternalSourceLine(doc.getText()));
    }

}
