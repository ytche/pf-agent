package com.pfagent.agent.config;

import org.junit.jupiter.api.Test;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.openai.OpenAiEmbeddingModel;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.test.util.ReflectionTestUtils;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * EmbeddingConfig 双通道矩阵单测（SP5 T2，覆盖 D2/D3/D5/D6）
 *
 * 离线策略：cloud 参与（主/备）的完整 Bean 链（校验 → 建通道 → 维度自检 → 矩阵
 * 组合）经匿名子类覆写 {@code buildCloudEmbeddingModel} 为 stub 模型后全链路可测——
 * stub 对 {@code DIMENSION_PROBE_TEXT} 返回 1024 维即通过 D5 自检，真实云端不触网。
 * 真实 {@link OpenAiEmbeddingModel} 仅做构造冒烟（构造函数不触网）。
 */
class EmbeddingConfigTest {

    private static final String STUB_BASE_URL = "https://api.example.com";
    private static final String STUB_API_KEY = "sk-test-not-real";

    /** D6 行1：默认 ollama 单通道 → 裸主通道返回（零包装，无需任何云配置即可通过） */
    @Test
    void ollamaPrimaryWithoutFallbackReturnsBareOllamaModel() {
        EmbeddingModel ollama = mock(EmbeddingModel.class);
        EmbeddingConfig config = stubCloudConfig("ollama", "", "", "", mock(EmbeddingModel.class));

        EmbeddingModel result = assemble(config, ollama);

        // 返回同一实例 = 未包 Fallback 包装器；云配置为空也未触发 fail-fast，即 cloud 未参与
        assertThat(result).isSameAs(ollama);
    }

    /** D6 行2：ollama 主 + fallback=true → Fallback(ollama, cloud)，本地挂降级云端 */
    @Test
    void ollamaPrimaryWithFallbackBacksUpWithCloud() {
        EmbeddingModel ollama = mock(EmbeddingModel.class);
        EmbeddingModel cloud = cloudBgeM3Stub();
        EmbeddingConfig config = stubCloudConfig("ollama", "true", STUB_BASE_URL, STUB_API_KEY, cloud);

        EmbeddingModel result = assemble(config, ollama);

        assertThat(result).isInstanceOf(FallbackEmbeddingModel.class);
        assertThat(ReflectionTestUtils.getField(result, "primary")).isSameAs(ollama);
        assertThat(ReflectionTestUtils.getField(result, "fallback")).isSameAs(cloud);
        when(ollama.embed("火球")).thenThrow(new RuntimeException("Ollama down"));
        when(cloud.embed("火球")).thenReturn(new float[]{1f, 2f});
        assertThat(result.embed("火球")).containsExactly(1f, 2f); // 本地挂 → 走 cloud 兜底
    }

    /** D6 行3：cloud 主 + fallback 未显式设置 → 默认 true → Fallback(cloud, ollama)，云端挂降本地 */
    @Test
    void cloudPrimaryDefaultsToFallbackOllama() {
        EmbeddingModel ollama = mock(EmbeddingModel.class);
        EmbeddingModel cloud = cloudBgeM3Stub();
        EmbeddingConfig config = stubCloudConfig("cloud", "", STUB_BASE_URL, STUB_API_KEY, cloud);

        EmbeddingModel result = assemble(config, ollama);

        assertThat(result).isInstanceOf(FallbackEmbeddingModel.class);
        assertThat(ReflectionTestUtils.getField(result, "primary")).isSameAs(cloud);
        assertThat(ReflectionTestUtils.getField(result, "fallback")).isSameAs(ollama);
        when(cloud.embed("火球")).thenThrow(new RuntimeException("cloud 500"));
        when(ollama.embed("火球")).thenReturn(new float[]{3f, 4f});
        assertThat(result.embed("火球")).containsExactly(3f, 4f); // 云端挂 → 走 ollama 兜底
    }

    /** D6 行4：cloud 主 + fallback=false → 裸 cloud（托管极简部署），仍过维度自检 */
    @Test
    void cloudPrimaryWithFallbackDisabledReturnsBareCloudModel() {
        EmbeddingModel cloud = cloudBgeM3Stub();
        EmbeddingConfig config = stubCloudConfig("cloud", "false", STUB_BASE_URL, STUB_API_KEY, cloud);

        EmbeddingModel result = assemble(config, mock(EmbeddingModel.class));

        assertThat(result).isSameAs(cloud); // 裸 cloud：D5 自检已通过（无异常），未包包装器
    }

    /** D3：cloud 主而 api-key 为空 → 启动 fail-fast，错误提示指向环境变量（不静默回退） */
    @Test
    void cloudPrimaryWithoutApiKeyFailsFast() {
        EmbeddingConfig config = stubCloudConfig("cloud", "", STUB_BASE_URL, "", mock(EmbeddingModel.class));

        assertThatThrownBy(() -> assemble(config, mock(EmbeddingModel.class)))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("PF_EMBEDDING_CLOUD_API_KEY");
    }

    /** D3：cloud 参与而 base-url 为空 → 启动 fail-fast */
    @Test
    void cloudActiveWithoutBaseUrlFailsFast() {
        EmbeddingConfig config = stubCloudConfig("cloud", "", "", STUB_API_KEY, mock(EmbeddingModel.class));

        assertThatThrownBy(() -> assemble(config, mock(EmbeddingModel.class)))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("cloud.base-url");
    }

    /** D3：ollama 主 + fallback=true（备 cloud）而 api-key 为空 → 同样 fail-fast */
    @Test
    void ollamaWithFallbackRequiresCloudApiKey() {
        EmbeddingConfig config = stubCloudConfig("ollama", "true", STUB_BASE_URL, "", mock(EmbeddingModel.class));

        assertThatThrownBy(() -> assemble(config, mock(EmbeddingModel.class)))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("PF_EMBEDDING_CLOUD_API_KEY");
    }

    /** D5：维度自检 1024 维 → 通过（不抛） */
    @Test
    void dimensionProbeAcceptsBgeM31024Dims() {
        EmbeddingModel cloud = mock(EmbeddingModel.class);
        when(cloud.embed(EmbeddingConfig.DIMENSION_PROBE_TEXT)).thenReturn(new float[1024]);

        assertThatCode(() -> EmbeddingConfig.assertBgeM3Dimensions(cloud)).doesNotThrowAnyException();
    }

    /** D5：维度 ≠ 1024 → fail-fast，错误提示指向模型一致性约束（防异维检索全废但服务照起） */
    @Test
    void dimensionProbeRejectsNon1024Dims() {
        EmbeddingModel cloud = mock(EmbeddingModel.class);
        when(cloud.embed(anyString())).thenReturn(new float[512]);

        assertThatThrownBy(() -> EmbeddingConfig.assertBgeM3Dimensions(cloud))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("1024")
                .hasMessageContaining("BAAI/bge-m3");
    }

    /** D3：真实云通道装配冒烟——OpenAiApi 仅客户端装配，构造函数不触网，retry 可选 */
    @Test
    void buildCloudEmbeddingModelConstructsOpenAiModelOffline() {
        EmbeddingConfig config = new EmbeddingConfig();
        ReflectionTestUtils.setField(config, "cloudBaseUrl", STUB_BASE_URL);
        ReflectionTestUtils.setField(config, "cloudApiKey", STUB_API_KEY);
        ReflectionTestUtils.setField(config, "cloudModel", "BAAI/bge-m3");

        EmbeddingModel withRetry = config.buildCloudEmbeddingModel(mock(RetryTemplate.class));
        EmbeddingModel withoutRetry = config.buildCloudEmbeddingModel(null);

        assertThat(withRetry).isInstanceOf(OpenAiEmbeddingModel.class);
        assertThat(withoutRetry).isInstanceOf(OpenAiEmbeddingModel.class);
    }

    private EmbeddingConfig stubCloudConfig(String primary, String fallbackRaw, String baseUrl,
                                            String apiKey, EmbeddingModel cloudStub) {
        EmbeddingConfig config = new EmbeddingConfig() {
            @Override
            protected EmbeddingModel buildCloudEmbeddingModel(RetryTemplate retryTemplate) {
                return cloudStub;
            }
        };
        ReflectionTestUtils.setField(config, "primary", primary);
        ReflectionTestUtils.setField(config, "fallbackEnabledRaw", fallbackRaw);
        ReflectionTestUtils.setField(config, "cloudBaseUrl", baseUrl);
        ReflectionTestUtils.setField(config, "cloudApiKey", apiKey);
        ReflectionTestUtils.setField(config, "cloudModel", "BAAI/bge-m3");
        return config;
    }

    /** 维度自检通过的 cloud stub：仅对 D5 探测文本返回 1024 维，其余调用未 stub（返回 null） */
    private EmbeddingModel cloudBgeM3Stub() {
        EmbeddingModel cloud = mock(EmbeddingModel.class);
        when(cloud.embed(EmbeddingConfig.DIMENSION_PROBE_TEXT)).thenReturn(new float[1024]);
        return cloud;
    }

    /** 触发 Bean 组合链；retry 用 mock（getIfAvailable 默认 null，stub 覆写忽略该参数） */
    private EmbeddingModel assemble(EmbeddingConfig config, EmbeddingModel ollama) {
        ObjectProvider<RetryTemplate> retryProvider = mock(ObjectProvider.class);
        return config.queryEmbeddingModel(ollama, retryProvider);
    }
}
