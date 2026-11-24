package com.pfagent.agent.rag;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.pfagent.agent.telemetry.UsageRecorder;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.metadata.ChatResponseMetadata;
import org.springframework.ai.chat.metadata.DefaultUsage;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.document.Document;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * F-016 语义检索二阶段 listwise 重排。
 *
 * <p>对已按 {@code rankedScore} 排序的语义检索候选（默认前 50）调用独立 DeepSeek
 * （无工具、低温度、单次调用），只要求返回候选 id 的有序列表，再取前 N（默认 15）。
 * 任何超时、异常或非法结果都整体回退到输入候选的原始顺序（即现有 rankedScore
 * top-N），不阻断问答。
 *
 * <p>非法结果口径：未知 id、重复 id、非 JSON、空数组。合法但未列全的候选按原输入
 * 顺序补位，最终仍截断到 topN。候选数不超过 topN 时不发起调用。
 *
 * <p>配置项（代码默认值，application.yml 由统一集成任务处理）：
 * <ul>
 *   <li>{@code pf.search.rerank-enabled=true}（SearchService 读取）</li>
 *   <li>{@code pf.search.rerank-candidates=50}（SearchService 读取）</li>
 *   <li>{@code pf.search.rerank-top-n=15}（SearchService 读取）</li>
 *   <li>{@code pf.search.rerank-summary-chars=300}</li>
 *   <li>{@code pf.search.rerank-timeout=8s}（executor future 等待上限）</li>
 *   <li>{@code pf.search.rerank-http-timeout=20s}（原生 HTTP 请求超时）</li>
 *   <li>{@code pf.search.rerank-model=deepseek-flash}</li>
 *   <li>{@code pf.search.rerank-concurrency=4} / {@code rerank-queue-capacity=16}</li>
 * </ul>
 *
 * <p>传输层改为 {@link DeepSeekRerankHttpClient}（java.net.http），不再经过
 * {@code OpenAiChatModel}：真实实例中 Spring AI 客户端调用不可控地超时，而直接
 * HTTP 调用同 key/模型正常返回。
 */
@Service
public class DeepSeekListwiseReranker {

    private static final Logger log = LoggerFactory.getLogger(DeepSeekListwiseReranker.class);

    private static final String SYSTEM_PROMPT = """
            你是检索结果相关性重排器。给定用户问题和候选片段，按与问题的相关性从高到低排序候选。
            只输出候选 id 组成的非空 JSON 数组，至少返回前 15 个候选（不足则全部列出）；
            不要输出解释、编号、空数组或其他字段。不得调用任何工具。
            """;

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    /** 重排候选：id 为稳定 chunk 标识，其余字段用于让模型判断相关性。 */
    public record Candidate(String id, String title, String module, String book,
                            String summary, Document document) {
    }

    /** F-016：重排专用原生 DeepSeek HTTP 传输层（不经过 OpenAiChatModel）。 */
    @Autowired
    private DeepSeekRerankHttpClient httpClient;

    /** F-009 用量采集；基线可能尚未提供实现，缺失时静默跳过。 */
    @Autowired(required = false)
    private UsageRecorder usageRecorder;

    @Value("${pf.search.rerank-summary-chars:300}")
    private int summaryChars = 300;

    @Value("${pf.search.rerank-timeout:8s}")
    private Duration timeout = Duration.ofSeconds(8);

    @Value("${pf.search.rerank-model:deepseek-flash}")
    private String defaultModel = "deepseek-flash";

    /** 重排并发上限；重排线程池固定大小，队列有界，打满时直接回退。 */
    @Value("${pf.search.rerank-concurrency:4}")
    private int concurrency = 4;

    @Value("${pf.search.rerank-queue-capacity:16}")
    private int queueCapacity = 16;

    private volatile ExecutorService executor;
    private final AtomicBoolean missingRecorderWarned = new AtomicBoolean(false);

    @PostConstruct
    void warnIfUsageRecorderMissing() {
        if (usageRecorder == null) {
            warnMissingUsageRecorder();
        }
    }

    /**
     * 对候选执行 listwise 重排并返回最终 topN。
     *
     * @param question   用户问题
     * @param candidates 已按 rankedScore 降序的候选（id 稳定即可，不要求全局唯一）
     * @param topN       最终保留条数
     * @return 重排后的 Document；任何失败都返回输入顺序的 topN
     */
    public List<Document> rerank(String question, List<Candidate> candidates, int topN) {
        if (candidates == null || candidates.isEmpty()) {
            return List.of();
        }
        int limit = Math.max(1, topN);
        List<Candidate> orderedInput = List.copyOf(candidates);
        List<Document> fallback = orderedInput.stream()
                .limit(limit)
                .map(Candidate::document)
                .toList();
        if (orderedInput.size() <= limit) {
            return fallback; // 无需重排，避免无意义 LLM 调用
        }

        Map<String, Candidate> byId = normalize(orderedInput);
        long start = System.nanoTime();
        DeepSeekRerankHttpClient.RerankResult response;
        try {
            response = callWithTimeout(question, byId);
        } catch (TimeoutException e) {
            return fallback("timeout", orderedInput.size(), elapsedMs(start), e, fallback);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return fallback("interrupted", orderedInput.size(), elapsedMs(start), e, fallback);
        } catch (RejectedExecutionException e) {
            return fallback("rejected", orderedInput.size(), elapsedMs(start), e, fallback);
        } catch (ExecutionException e) {
            return fallback("exception", orderedInput.size(), elapsedMs(start), e, fallback);
        } catch (RuntimeException e) {
            return fallback("runtime_exception", orderedInput.size(), elapsedMs(start), e, fallback);
        }
        // TODO(F-016): 连续失败熔断（本请求内禁用重排）需请求级上下文，暂不实现；当前按次回退。

        long durationMs = elapsedMs(start);
        if (response == null) {
            return fallback("empty_response", orderedInput.size(), durationMs, null, fallback);
        }
        recordUsage(response, durationMs);

        List<Candidate> ordered = parseOrder(response.content(), byId);
        if (ordered == null) {
            return fallback("illegal_result", orderedInput.size(), durationMs, null, fallback);
        }
        log.info("[F-016] rerank_success candidateCount={} resultCount={} durationMs={}",
                orderedInput.size(), Math.min(limit, ordered.size()), durationMs);
        return ordered.stream().limit(limit).map(Candidate::document).toList();
    }

    private List<Document> fallback(String reason, int candidateCount, long durationMs,
                                    Throwable error, List<Document> fallback) {
        log.warn("[F-016] rerank_fallback reason={} candidateCount={} durationMs={} error={}",
                reason, candidateCount, durationMs, error == null ? "" : rootMessage(error));
        return fallback;
    }

    private long elapsedMs(long startNanos) {
        return (System.nanoTime() - startNanos) / 1_000_000;
    }

    private DeepSeekRerankHttpClient.RerankResult callWithTimeout(String question,
            Map<String, Candidate> candidates)
            throws InterruptedException, ExecutionException, TimeoutException {
        String userPayload = buildUserPayload(question, candidates);
        Future<DeepSeekRerankHttpClient.RerankResult> future = null;
        try {
            future = executor().submit(() -> httpClient.complete(SYSTEM_PROMPT, userPayload));
            return future.get(timeout.toMillis(), TimeUnit.MILLISECONDS);
        } finally {
            if (future != null && !future.isDone()) {
                future.cancel(true); // 超时/中断兜底取消，避免任务继续占用重排线程
            }
        }
    }

    /** 固定大小 + 有界队列的重排线程池；默认 4 并发 / 16 排队，打满即拒绝并回退。 */
    private ExecutorService executor() {
        ExecutorService current = executor;
        if (current != null && !current.isShutdown()) {
            return current;
        }
        synchronized (this) {
            if (executor == null || executor.isShutdown()) {
                int poolSize = Math.max(1, concurrency);
                int capacity = Math.max(1, queueCapacity);
                executor = new ThreadPoolExecutor(
                        poolSize, poolSize, 0L, TimeUnit.MILLISECONDS,
                        new ArrayBlockingQueue<>(capacity),
                        runnable -> {
                            Thread thread = new Thread(runnable, "pf-rerank-llm");
                            thread.setDaemon(true);
                            return thread;
                        });
            }
            return executor;
        }
    }

    /**
     * 解析并校验模型输出。
     *
     * @return 合法时返回「模型顺序 + 原顺序补位」的完整候选列表；非法返回 null
     */
    private List<Candidate> parseOrder(String content, Map<String, Candidate> byId) {
        List<String> ids = extractIds(content);
        if (ids == null || ids.isEmpty()) {
            return null;
        }
        Set<String> seen = new HashSet<>();
        List<Candidate> ordered = new ArrayList<>(byId.size());
        for (String id : ids) {
            if (!byId.containsKey(id) || !seen.add(id)) {
                return null; // 未知 id / 重复 id：整体非法
            }
            ordered.add(byId.get(id));
        }
        for (Candidate candidate : byId.values()) {
            if (ordered.stream().noneMatch(item -> item == candidate)) {
                ordered.add(candidate); // 合法缺项：按原 rankedScore 顺序补位
            }
        }
        return ordered;
    }

    /** 候选 id 归一化为输出中真正使用的唯一 id（重复输入 id 追加序号，保持可映射）。 */
    private Map<String, Candidate> normalize(List<Candidate> candidates) {
        Map<String, Candidate> byId = new LinkedHashMap<>();
        for (int i = 0; i < candidates.size(); i++) {
            Candidate candidate = candidates.get(i);
            String base = candidate.id() == null || candidate.id().isBlank()
                    ? "c" + i
                    : candidate.id();
            String id = base;
            int suffix = 2;
            while (byId.containsKey(id)) {
                id = base + "#" + suffix++;
            }
            byId.put(id, candidate);
        }
        return byId;
    }

    /** 从 JSON 数组或 {"ids": [...]} 中提取字符串列表；格式非法返回 null。 */
    private List<String> extractIds(String content) {
        if (content == null || content.isBlank()) {
            return null;
        }
        String text = stripCodeFence(content.trim());
        try {
            JsonNode root = OBJECT_MAPPER.readTree(text);
            JsonNode array = root;
            if (root.isObject() && root.has("ids")) {
                array = root.get("ids");
            }
            if (array == null || !array.isArray()) {
                return null;
            }
            List<String> ids = new ArrayList<>(array.size());
            for (JsonNode node : array) {
                if (!node.isTextual() || node.asText().isBlank()) {
                    return null;
                }
                ids.add(node.asText());
            }
            return ids;
        } catch (Exception e) {
            return null;
        }
    }

    private String stripCodeFence(String text) {
        if (!text.startsWith("```")) {
            return text;
        }
        int firstNewline = text.indexOf('\n');
        if (firstNewline < 0) {
            return text;
        }
        String body = text.substring(firstNewline + 1);
        int fence = body.lastIndexOf("```");
        return fence >= 0 ? body.substring(0, fence).trim() : body.trim();
    }

    private String buildUserPayload(String question, Map<String, Candidate> candidates) {
        List<Map<String, String>> items = new ArrayList<>(candidates.size());
        for (Map.Entry<String, Candidate> entry : candidates.entrySet()) {
            Candidate candidate = entry.getValue();
            items.add(Map.of(
                    "id", entry.getKey(),
                    "title", nullToEmpty(candidate.title()),
                    "module", nullToEmpty(candidate.module()),
                    "book", nullToEmpty(candidate.book()),
                    "summary", truncate(nullToEmpty(candidate.summary()), Math.max(0, summaryChars))));
        }
        try {
            return OBJECT_MAPPER.writeValueAsString(Map.of(
                    "question", nullToEmpty(question),
                    "candidates", items));
        } catch (Exception e) {
            throw new IllegalStateException("重排输入序列化失败", e);
        }
    }

    private void recordUsage(DeepSeekRerankHttpClient.RerankResult result, long durationMs) {
        if (usageRecorder == null) {
            warnMissingUsageRecorder();
            return;
        }
        try {
            String model = result.model() == null || result.model().isBlank()
                    ? defaultModel : result.model();
            usageRecorder.record("rerank", model, toChatResponse(result, model), durationMs);
        } catch (RuntimeException e) {
            log.warn("[F-016] rerank_usage_record_failed durationMs={} error={}",
                    durationMs, e.toString());
        }
    }

    /**
     * 把原生 HTTP 结果适配成 F-009 采集接口需要的 ChatResponse：只填 model 与 usage，
     * 不含 generations（用量记录只读 metadata）；usage 缺失时 metadata 不带 Usage，
     * JdbcUsageRecorder 会按 usage_missing 记录调用与耗时。
     */
    private ChatResponse toChatResponse(DeepSeekRerankHttpClient.RerankResult result, String model) {
        ChatResponseMetadata.Builder metadata = ChatResponseMetadata.builder().model(model);
        if (result.hasUsage()) {
            metadata.usage(new DefaultUsage(
                    defaultIfNull(result.promptTokens()),
                    defaultIfNull(result.completionTokens()),
                    defaultIfNull(result.totalTokens())));
        }
        return new ChatResponse(List.of(), metadata.build());
    }

    private static Integer defaultIfNull(Integer value) {
        return value == null ? 0 : value;
    }

    private void warnMissingUsageRecorder() {
        if (missingRecorderWarned.compareAndSet(false, true)) {
            log.warn("[F-016] rerank_usage_recorder_missing：未装配 UsageRecorder，"
                    + "重排调用不会写入 F-009 用量采集");
        }
    }

    private String truncate(String text, int maxChars) {
        return text.length() <= maxChars ? text : text.substring(0, maxChars);
    }

    private String nullToEmpty(String text) {
        return text == null ? "" : text;
    }

    private String rootMessage(Throwable e) {
        Throwable cause = e.getCause() == null ? e : e.getCause();
        return cause.toString();
    }

    @PreDestroy
    void shutdown() {
        ExecutorService current = executor;
        if (current != null) {
            current.shutdownNow();
        }
    }
}
