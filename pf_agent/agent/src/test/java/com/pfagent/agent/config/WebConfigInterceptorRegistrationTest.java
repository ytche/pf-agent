package com.pfagent.agent.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.handler.MappedInterceptor;

import java.util.function.Consumer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

/**
 * WebConfig 拦截器注册范围测试（SP7 T3 白盒审计补充）
 *
 * coder 改动了 addInterceptors 的路径注册（鉴权只拦 /api/chat、/api/chat/feedback；
 * 限频扩到 /api/auth/**）但无测试锁定。注册分支是确定性逻辑（限频拦截器缺席则
 * 不注册），此处用真实 InterceptorRegistry 捕获注册结果，锁路径范围：
 * - 鉴权：只注册 /api/chat 与 /api/chat/feedback（/api/auth/**、/api/health 不在内）
 * - 限频：拦截器缺席（默认关）时不注册；存在时覆盖 /api/chat + /api/auth/**
 */
@SuppressWarnings("unchecked")
class WebConfigInterceptorRegistrationTest {

    private final AuthInterceptor authInterceptor = mock(AuthInterceptor.class);

    private WebConfig webConfig(ObjectProvider<RateLimitInterceptor> rateLimitProvider) {
        WebConfig webConfig = new WebConfig();
        ReflectionTestUtils.setField(webConfig, "authInterceptor", authInterceptor);
        ReflectionTestUtils.setField(webConfig, "rateLimitInterceptor", rateLimitProvider);
        return webConfig;
    }

    @SuppressWarnings("unchecked")
    private static java.util.List<org.springframework.web.servlet.HandlerInterceptor> interceptors(InterceptorRegistry registry) {
        return (java.util.List<org.springframework.web.servlet.HandlerInterceptor>)
                ReflectionTestUtils.invokeMethod(registry, "getInterceptors");
    }

    private static MappedInterceptor findMapped(InterceptorRegistry registry, Object interceptor) {
        return interceptors(registry).stream()
                .filter(MappedInterceptor.class::isInstance)
                .map(MappedInterceptor.class::cast)
                .filter(m -> m.getInterceptor() == interceptor)
                .findFirst()
                .orElseThrow(() -> new AssertionError("目标拦截器未注册: " + interceptor));
    }

    @Test
    void authInterceptorRegisteredOnlyForChatPaths() {
        ObjectProvider<RateLimitInterceptor> absentRateLimit = mock(ObjectProvider.class);
        InterceptorRegistry registry = new InterceptorRegistry();

        webConfig(absentRateLimit).addInterceptors(registry);

        MappedInterceptor mapped = findMapped(registry, authInterceptor);
        assertThat(mapped.getPathPatterns())
                .containsExactlyInAnyOrder("/api/chat", "/api/chat/feedback");
        // 豁免路径（D5）：/api/auth/**、/api/health、静态资源不在鉴权范围
        assertThat(mapped.getPathPatterns()).noneMatch(p -> p.startsWith("/api/auth"));
    }

    @Test
    void rateLimitInterceptorAbsentNotRegistered() {
        ObjectProvider<RateLimitInterceptor> absentRateLimit = mock(ObjectProvider.class);
        InterceptorRegistry registry = new InterceptorRegistry();

        webConfig(absentRateLimit).addInterceptors(registry);

        // 默认关 = 零行为变化：限频分支不注册任何拦截器
        verify(absentRateLimit).ifAvailable(any());
        assertThat(interceptors(registry)).hasSize(1);
    }

    @Test
    void rateLimitInterceptorRegisteredWithChatAndAuthPaths() {
        RateLimitInterceptor rateLimit = mock(RateLimitInterceptor.class);
        ObjectProvider<RateLimitInterceptor> presentRateLimit = mock(ObjectProvider.class);
        doAnswer(inv -> {
            inv.<Consumer<RateLimitInterceptor>>getArgument(0).accept(rateLimit);
            return null;
        }).when(presentRateLimit).ifAvailable(any());
        InterceptorRegistry registry = new InterceptorRegistry();

        webConfig(presentRateLimit).addInterceptors(registry);

        MappedInterceptor mapped = findMapped(registry, rateLimit);
        assertThat(mapped.getPathPatterns())
                .containsExactlyInAnyOrder("/api/chat", "/api/auth/**");
        // /api/chat/feedback 仍不受限频（与注释一致）
        assertThat(mapped.getPathPatterns()).doesNotContain("/api/chat/feedback");
    }

    @Test
    void rateLimitInterceptorAbsentLeavesRegistryWithoutRateLimitBean() {
        ObjectProvider<RateLimitInterceptor> absentRateLimit = mock(ObjectProvider.class);
        InterceptorRegistry registry = new InterceptorRegistry();

        webConfig(absentRateLimit).addInterceptors(registry);

        verify(absentRateLimit, never()).getIfAvailable();
        assertThat(interceptors(registry).stream()
                .filter(MappedInterceptor.class::isInstance)
                .map(MappedInterceptor.class::cast)
                .map(MappedInterceptor::getInterceptor))
                .allMatch(i -> i == authInterceptor);
    }
}
