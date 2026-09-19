package com.pfagent.agent.config;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import org.springframework.ai.autoconfigure.ollama.OllamaAutoConfiguration;
import org.springframework.ai.ollama.api.OllamaApi;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.convert.ApplicationConversionService;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

import java.net.InetSocketAddress;
import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * embedding 客户端超时单测（AKN-010）
 *
 * 覆盖：
 *  - 配置绑定：pf.embedding.read-timeout / connect-timeout 自定义值与默认值（120s/10s）
 *    经 ApplicationContextRunner 断言真实落到 OllamaApi 底层 request factory 上
 *  - Bean 装配：EmbeddingConfig 的 OllamaApi 覆盖 OllamaAutoConfiguration 产物
 *    （自动装配 @ConditionalOnMissingBean 回退），ollamaEmbeddingModel 链不受影响
 *  - 超时行为：本地 HttpServer 延迟响应，断言读超时触发 ResourceAccessException
 *    且在服务器休眠时长内返回（即真超时而非挂死后才失败）——超时可触发 Fallback 降级
 */
class EmbeddingTimeoutTest {

    private static final Duration CUSTOM_READ = Duration.ofSeconds(42);
    private static final Duration CUSTOM_CONNECT = Duration.ofSeconds(7);

    /** 自定义超时值绑定：经上下文装配后落到 OllamaApi 的 RestClient request factory */
    @Test
    void customTimeoutsBindToOllamaApiRequestFactory() {
        contextRunner("42s", "7s").run(ctx -> {
            assertThat(ctx).hasSingleBean(OllamaApi.class);
            assertOllamaApiTimeouts(ctx.getBean(OllamaApi.class), CUSTOM_READ, CUSTOM_CONNECT);
        });
    }

    /** 默认超时值：未配置时 read=120s / connect=10s（代码默认值兜底） */
    @Test
    void defaultTimeoutsApplyWhenNotConfigured() {
        contextRunner(null, null).run(ctx -> {
            assertThat(ctx).hasSingleBean(OllamaApi.class);
            assertOllamaApiTimeouts(ctx.getBean(OllamaApi.class), Duration.ofSeconds(120), Duration.ofSeconds(10));
        });
    }

    /** 超时行为：慢服务器（休眠 2s）在 200ms 读超时触发 ResourceAccessException，且远早于休眠结束 */
    @Test
    void readTimeoutFiresAgainstSlowServer() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(0), 0);
        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(2000); // 远超客户端读超时
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            int port = server.getAddress().getPort();
            ClientHttpRequestFactory factory = EmbeddingConfig.embeddingRequestFactory(
                    Duration.ofMillis(200), Duration.ofMillis(200));
            RestClient client = RestClient.builder().requestFactory(factory).build();

            long startNanos = System.nanoTime();
            assertThatThrownBy(() -> client.post()
                    .uri("http://localhost:" + port + "/slow")
                    .body("ping")
                    .retrieve()
                    .toBodilessEntity())
                    .isInstanceOf(ResourceAccessException.class); // 超时包装为 ResourceAccessException → 可触发 Fallback 降级
            // 必须在服务器休眠结束（2s）前返回，证明是真超时而非等待挂死
            assertThat(Duration.ofNanos(System.nanoTime() - startNanos)).isLessThan(Duration.ofSeconds(2));
        } finally {
            server.stop(0);
        }
    }

    /** 断连快速失败：连接超时对不可达端口立即生效（不做无界 TCP 连接等待） */
    @Test
    void connectTimeoutFiresForUnroutableHost() {        ClientHttpRequestFactory factory = EmbeddingConfig.embeddingRequestFactory(
                Duration.ofMillis(300), Duration.ofSeconds(1));
        RestClient client = RestClient.builder().requestFactory(factory).build();

        long startNanos = System.nanoTime();
        // 保留段地址（TEST-NET-1）无路由，SYN 无响应：连接超时兜底，不做无界等待
        assertThatThrownBy(() -> client.post()
                .uri("http://192.0.2.1:11434/api/embeddings")
                .body("ping")
                .retrieve()
                .toBodilessEntity())
                .isInstanceOf(ResourceAccessException.class);
        assertThat(Duration.ofNanos(System.nanoTime() - startNanos)).isLessThan(Duration.ofSeconds(30));
    }

    /** Bean 依赖链（QA 补测）：自动装配的 ollamaEmbeddingModel 确实消费 EmbeddingConfig
     *  覆盖注册的 OllamaApi 实例——超时配置经 @ConditionalOnMissingBean 接管真正落到
     *  检索/导入实际使用的 embedding 模型上，而非只换掉一个无人引用的孤儿 Bean */
    @Test
    void ollamaEmbeddingModelConsumesOverriddenOllamaApi() {
        contextRunner(null, null).run(ctx -> {
            OllamaApi api = ctx.getBean(OllamaApi.class);
            Object model = ctx.getBean("ollamaEmbeddingModel");
            assertThat(model).isNotNull();
            assertThat(ReflectionTestUtils.getField(model, "ollamaApi")).isSameAs(api);
        });
    }

    /** 装配 EmbeddingConfig + Ollama 自动装配的上下文（ollama 指向本机默认值即可，装配不触网） */
    private ApplicationContextRunner contextRunner(String readTimeout, String connectTimeout) {
        ApplicationContextRunner runner = new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(OllamaAutoConfiguration.class))
                .withUserConfiguration(EmbeddingConfig.class)
                // ApplicationContextRunner 是裸 GenericApplicationContext，需显式注册 Boot
                // 转换服务，@Value Duration（"42s"）才能绑定（真实 Boot 应用自动具备）
                .withInitializer(ctx -> ctx.getBeanFactory()
                        .setConversionService(new ApplicationConversionService()))
                .withPropertyValues("spring.ai.ollama.base-url=http://localhost:11434");
        if (readTimeout != null) {
            runner = runner.withPropertyValues("pf.embedding.read-timeout=" + readTimeout);
        }
        if (connectTimeout != null) {
            runner = runner.withPropertyValues("pf.embedding.connect-timeout=" + connectTimeout);
        }
        return runner;
    }

    /** 断言 OllamaApi 底层 RestClient 使用 SimpleClientHttpRequestFactory 且超时值正确（内部按毫秒 int 存） */
    private void assertOllamaApiTimeouts(OllamaApi api, Duration readTimeout, Duration connectTimeout) {
        RestClient restClient = (RestClient) ReflectionTestUtils.getField(api, "restClient");
        assertThat(restClient).isNotNull();
        ClientHttpRequestFactory requestFactory =
                (ClientHttpRequestFactory) ReflectionTestUtils.getField(restClient, "clientRequestFactory");
        assertThat(requestFactory).isInstanceOf(SimpleClientHttpRequestFactory.class);
        assertThat(ReflectionTestUtils.getField(requestFactory, "readTimeout")).isEqualTo((int) readTimeout.toMillis());
        assertThat(ReflectionTestUtils.getField(requestFactory, "connectTimeout")).isEqualTo((int) connectTimeout.toMillis());
    }
}
