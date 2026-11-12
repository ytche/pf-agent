package com.pfagent.agent.admin;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.handler.MappedInterceptor;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * AdminWebConfig 拦截器注册范围测试（F-023）
 *
 * 用真实 InterceptorRegistry 捕获注册结果，锁 AdminInterceptor 只覆盖 /api/admin/**，
 * 不侵入 /api/auth、/api/chat 等既有路径。
 */
@SuppressWarnings("unchecked")
class AdminWebConfigTest {

    private static MappedInterceptor findMapped(InterceptorRegistry registry, Object interceptor) {
        List<org.springframework.web.servlet.HandlerInterceptor> interceptors =
                (List<org.springframework.web.servlet.HandlerInterceptor>)
                        ReflectionTestUtils.invokeMethod(registry, "getInterceptors");
        return interceptors.stream()
                .filter(MappedInterceptor.class::isInstance)
                .map(MappedInterceptor.class::cast)
                .filter(m -> m.getInterceptor() == interceptor)
                .findFirst()
                .orElseThrow(() -> new AssertionError("目标拦截器未注册: " + interceptor));
    }

    @Test
    void registersAdminInterceptorForAdminPaths() {
        AdminInterceptor adminInterceptor = Mockito.mock(AdminInterceptor.class);
        AdminWebConfig config = new AdminWebConfig();
        ReflectionTestUtils.setField(config, "adminInterceptor", adminInterceptor);
        InterceptorRegistry registry = new InterceptorRegistry();

        config.addInterceptors(registry);

        MappedInterceptor mapped = findMapped(registry, adminInterceptor);
        assertThat(mapped.getPathPatterns()).containsExactly("/api/admin/**");
    }
}
