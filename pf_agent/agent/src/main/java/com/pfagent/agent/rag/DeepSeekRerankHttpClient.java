package com.pfagent.agent.rag;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * F-016 重排专用 DeepSeek HTTP 传输层。
 *
 * <p>不使用 Spring AI {@code OpenAiChatModel}：实测该实例下同 key/模型经 Spring AI
 * 每次 listwise 调用均超时，而直接 POST DeepSeek API 50×300 字符约 2.7s，故重排改用
 * 最小原生 {@link HttpClient} 调用，绕开不可控的客户端延迟。
 *
 * <p>请求固定为 {@code {model, messages:[system,user], temperature:0}}；只读取
 * {@code choices[0].message.content} 与 {@code usage} 计数。api-key 只放
 * Authorization 头，任何日志/异常消息都不输出密钥。
 */
@Component
public class DeepSeekRerankHttpClient {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    /** 单次重排 HTTP 结果：正文 + 用量 + 实测耗时。 */
    public record RerankResult(String content, String model, Integer promptTokens,
                               Integer completionTokens, Integer totalTokens, long durationMs) {

        public boolean hasUsage() {
            return promptTokens != null || completionTokens != null || totalTokens != null;
        }
    }

    /** 重排 HTTP 调用失败（配置/网络/超时/非 200/响应不可解析）；由重排器统一回退。 */
    public static class RerankHttpException extends RuntimeException {
        public RerankHttpException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    private final HttpClient httpClient;
    private final String baseUrl;
    private final String apiKey;
    private final String model;
    private final Duration httpTimeout;

    @Autowired
    public DeepSeekRerankHttpClient(
            @Value("${spring.ai.openai.base-url:https://api.deepseek.com}") String baseUrl,
            @Value("${spring.ai.openai.api-key:}") String apiKey,
            @Value("${pf.search.rerank-model:deepseek-flash}") String model,
            @Value("${pf.search.rerank-http-timeout:20s}") Duration httpTimeout) {
        this(newHttpClient(httpTimeout), baseUrl, apiKey, model, httpTimeout);
    }

    /** 测试入口：注入 HttpClient transport 与固定配置。 */
    DeepSeekRerankHttpClient(HttpClient httpClient, String baseUrl, String apiKey,
                             String model, Duration httpTimeout) {
        this.httpClient = httpClient;
        this.baseUrl = baseUrl == null || baseUrl.isBlank()
                ? "https://api.deepseek.com" : baseUrl.trim();
        this.apiKey = apiKey == null ? "" : apiKey.trim();
        this.model = model == null || model.isBlank() ? "deepseek-flash" : model.trim();
        this.httpTimeout = httpTimeout == null || httpTimeout.isNegative() || httpTimeout.isZero()
                ? Duration.ofSeconds(20) : httpTimeout;
    }

    private static HttpClient newHttpClient(Duration timeout) {
        return HttpClient.newBuilder()
                .connectTimeout(timeout == null || timeout.isZero() || timeout.isNegative()
                        ? Duration.ofSeconds(20) : timeout)
                .build();
    }

    /**
     * 调用 DeepSeek /chat/completions 并解析首条内容与 usage。
     *
     * @throws RerankHttpException 配置缺失、超时、网络异常、非 200 或响应结构不可解析
     */
    public RerankResult complete(String systemPrompt, String userPayload) {
        if (apiKey.isBlank()) {
            throw new RerankHttpException("DeepSeek api-key 未配置（spring.ai.openai.api-key）", null);
        }
        String body = buildRequestBody(systemPrompt, userPayload);
        HttpRequest request = HttpRequest.newBuilder(endpoint())
                .timeout(httpTimeout)
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .header("Authorization", "Bearer " + apiKey)
                .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                .build();
        long start = System.nanoTime();
        HttpResponse<String> response;
        try {
            response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        } catch (HttpTimeoutException e) {
            throw new RerankHttpException("DeepSeek 重排请求超时（" + httpTimeout + "）", e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RerankHttpException("DeepSeek 重排请求被中断", e);
        } catch (IOException e) {
            throw new RerankHttpException("DeepSeek 重排请求失败", e);
        }
        long durationMs = (System.nanoTime() - start) / 1_000_000;
        if (response.statusCode() != 200) {
            throw new RerankHttpException("DeepSeek 重排返回 HTTP " + response.statusCode()
                    + "（响应体最多 200 字：" + abbreviate(response.body(), 200) + "）", null);
        }
        return parseResponse(response.body(), durationMs);
    }

    /** 请求体构造（包级可见，供单测断言 model/messages/temperature）。 */
    String buildRequestBody(String systemPrompt, String userPayload) {
        try {
            return OBJECT_MAPPER.writeValueAsString(Map.of(
                    "model", model,
                    "messages", List.of(
                            Map.of("role", "system", "content", nullToEmpty(systemPrompt)),
                            Map.of("role", "user", "content", nullToEmpty(userPayload))),
                    "temperature", 0,
                    "thinking", Map.of("type", "disabled")));
        } catch (Exception e) {
            throw new RerankHttpException("重排请求序列化失败", e);
        }
    }

    private RerankResult parseResponse(String body, long durationMs) {
        JsonNode root;
        try {
            root = OBJECT_MAPPER.readTree(body);
        } catch (Exception e) {
            throw new RerankHttpException("DeepSeek 重排响应不是合法 JSON", e);
        }
        JsonNode contentNode = root.path("choices").path(0).path("message").path("content");
        if (!contentNode.isTextual() || contentNode.asText().isBlank()) {
            throw new RerankHttpException("DeepSeek 重排响应缺少 choices[0].message.content", null);
        }
        String responseModel = root.path("model").asText(null);
        JsonNode usage = root.path("usage");
        Integer promptTokens = intOrNull(usage, "prompt_tokens");
        Integer completionTokens = intOrNull(usage, "completion_tokens");
        Integer totalTokens = intOrNull(usage, "total_tokens");
        return new RerankResult(contentNode.asText(), responseModel, promptTokens,
                completionTokens, totalTokens, durationMs);
    }

    private static Integer intOrNull(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isNumber() ? value.asInt() : null;
    }

    private URI endpoint() {
        String base = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        return URI.create(base + "/chat/completions");
    }

    private static String abbreviate(String text, int max) {
        if (text == null) {
            return "";
        }
        return text.length() <= max ? text : text.substring(0, max) + "…";
    }

    private static String nullToEmpty(String text) {
        return text == null ? "" : text;
    }
}
