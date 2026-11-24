package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * F-016 重排 HTTP 传输层单测：mock HttpClient，覆盖成功解析、超时、非 200、
 * 非法/缺字段 JSON、usage 缺失、请求体与鉴权头。测试不触碰真实网络，也不打印 api-key。
 */
@ExtendWith(MockitoExtension.class)
class DeepSeekRerankHttpClientTest {

    private static final String SUCCESS_BODY = """
            {"model":"deepseek-flash",
             "choices":[{"message":{"role":"assistant","content":"[\\"b\\",\\"a\\"]"}}],
             "usage":{"prompt_tokens":120,"completion_tokens":30,"total_tokens":150}}
            """;

    @Mock
    private HttpClient httpClient;
    @Mock
    private HttpResponse<String> httpResponse;

    @Test
    void successfulResponseParsesContentUsageAndDuration() throws Exception {
        stubResponse(200, SUCCESS_BODY);

        DeepSeekRerankHttpClient.RerankResult result = client(Duration.ofSeconds(20))
                .complete("system", "{\"question\":\"q\"}");

        assertThat(result.content()).isEqualTo("[\"b\",\"a\"]");
        assertThat(result.model()).isEqualTo("deepseek-flash");
        assertThat(result.promptTokens()).isEqualTo(120);
        assertThat(result.completionTokens()).isEqualTo(30);
        assertThat(result.totalTokens()).isEqualTo(150);
        assertThat(result.hasUsage()).isTrue();
        assertThat(result.durationMs()).isGreaterThanOrEqualTo(0);
    }

    @Test
    void requestUsesConfiguredEndpointTimeoutAndBearerHeader() throws Exception {
        stubResponse(200, SUCCESS_BODY);

        client(Duration.ofSeconds(20)).complete("system", "user");

        ArgumentCaptor<HttpRequest> captor = ArgumentCaptor.forClass(HttpRequest.class);
        verify(httpClient).send(captor.capture(), any(HttpResponse.BodyHandler.class));
        HttpRequest request = captor.getValue();
        assertThat(request.uri()).isEqualTo(URI.create("https://api.deepseek.com/chat/completions"));
        assertThat(request.timeout()).contains(Duration.ofSeconds(20));
        assertThat(request.headers().firstValue("Authorization")).contains("Bearer sk-secret");
        assertThat(request.headers().firstValue("Content-Type")).contains("application/json");
    }

    @Test
    void requestBodyCarriesModelMessagesAndZeroTemperature() {
        DeepSeekRerankHttpClient client = client(Duration.ofSeconds(20));

        String body = client.buildRequestBody("系统提示", "{\"question\":\"女巫\"}");

        assertThat(body).contains("\"model\":\"deepseek-flash\"")
                .contains("\"role\":\"system\"").contains("系统提示")
                .contains("\"role\":\"user\"").contains("女巫")
                .contains("\"temperature\":0")
                .doesNotContain("tools")
                .doesNotContain("sk-secret");
    }

    @Test
    void timeoutThrowsRerankHttpException() throws Exception {
        when(httpClient.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
                .thenThrow(new HttpTimeoutException("timed out"));

        assertThatThrownBy(() -> client(Duration.ofSeconds(20)).complete("system", "user"))
                .isInstanceOf(DeepSeekRerankHttpClient.RerankHttpException.class)
                .hasMessageContaining("超时")
                .hasMessageNotContaining("sk-secret");
    }

    @Test
    void non200ThrowsWithStatusAndBodyButNotApiKey() throws Exception {
        stubResponse(429, "{\"error\":\"rate limit\"}");

        assertThatThrownBy(() -> client(Duration.ofSeconds(20)).complete("system", "user"))
                .isInstanceOf(DeepSeekRerankHttpClient.RerankHttpException.class)
                .hasMessageContaining("HTTP 429")
                .hasMessageContaining("rate limit")
                .hasMessageNotContaining("sk-secret");
    }

    @Test
    void invalidJsonThrowsRerankHttpException() throws Exception {
        stubResponse(200, "not-json");

        assertThatThrownBy(() -> client(Duration.ofSeconds(20)).complete("system", "user"))
                .isInstanceOf(DeepSeekRerankHttpClient.RerankHttpException.class)
                .hasMessageContaining("不是合法 JSON");
    }

    @Test
    void missingContentThrowsRerankHttpException() throws Exception {
        stubResponse(200, "{\"choices\":[]}");

        assertThatThrownBy(() -> client(Duration.ofSeconds(20)).complete("system", "user"))
                .isInstanceOf(DeepSeekRerankHttpClient.RerankHttpException.class)
                .hasMessageContaining("缺少 choices[0].message.content");
    }

    @Test
    void missingUsageYieldsNullTokensButStillReturnsContent() throws Exception {
        stubResponse(200, "{\"choices\":[{\"message\":{\"content\":\"[\\\"a\\\"]\"}}]}");

        DeepSeekRerankHttpClient.RerankResult result = client(Duration.ofSeconds(20))
                .complete("system", "user");

        assertThat(result.content()).isEqualTo("[\"a\"]");
        assertThat(result.hasUsage()).isFalse();
        assertThat(result.promptTokens()).isNull();
        assertThat(result.completionTokens()).isNull();
        assertThat(result.totalTokens()).isNull();
    }

    @Test
    void missingApiKeyFailsWithoutSendingRequest() {
        DeepSeekRerankHttpClient client = new DeepSeekRerankHttpClient(
                httpClient, "https://api.deepseek.com", "", "deepseek-flash", Duration.ofSeconds(5));

        assertThatThrownBy(() -> client.complete("system", "user"))
                .isInstanceOf(DeepSeekRerankHttpClient.RerankHttpException.class)
                .hasMessageContaining("api-key 未配置");
        verifyNoInteractions(httpClient);
    }

    private void stubResponse(int status, String body) throws Exception {
        when(httpResponse.statusCode()).thenReturn(status);
        when(httpResponse.body()).thenReturn(body);
        when(httpClient.send(any(HttpRequest.class), any(HttpResponse.BodyHandler.class)))
                .thenReturn(httpResponse);
    }

    private DeepSeekRerankHttpClient client(Duration timeout) {
        return new DeepSeekRerankHttpClient(
                httpClient, "https://api.deepseek.com/", "sk-secret", "deepseek-flash", timeout);
    }
}
