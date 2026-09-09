package com.pfagent.agent.config;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

/**
 * AuthInterceptor 单元测试
 *
 * 当前为登录鉴权占位实现，约定直接放行；接入真实鉴权后
 * 在此补充 token 校验分支的测试。
 */
class AuthInterceptorTest {

    /** 占位阶段 preHandle 直接放行 */
    @Test
    void preHandlePassesThroughInPlaceholderPhase() {
        AuthInterceptor interceptor = new AuthInterceptor();

        boolean allowed = interceptor.preHandle(
                mock(HttpServletRequest.class),
                mock(HttpServletResponse.class),
                new Object());

        assertThat(allowed).isTrue();
    }
}
