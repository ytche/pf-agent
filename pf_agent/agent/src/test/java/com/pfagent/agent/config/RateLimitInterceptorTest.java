package com.pfagent.agent.config;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.entry;

/**
 * RateLimitInterceptor 单元测试（F-010 按 IP 固定窗口限频）
 *
 * 拦截器经 @ConditionalOnProperty 装配，这里手动 new + 反射注入 @Value 字段与
 * ObjectMapper（不拉 Spring 上下文）。窗口用真实系统分钟，跨窗口模拟通过直接改写
 * 内部 map 条目为上一分钟实现——不依赖 sleep 等待真实窗口翻转。
 */
class RateLimitInterceptorTest {

    private static final String IP = "203.0.113.7";

    private RateLimitInterceptor interceptor;

    @BeforeEach
    void setUp() {
        interceptor = new RateLimitInterceptor();
        ReflectionTestUtils.setField(interceptor, "perMinute", 2);
        ReflectionTestUtils.setField(interceptor, "objectMapper", new ObjectMapper());
    }

    /** 窗口内第 per-minute 次放行，第 per-minute+1 次 429 */
    @Test
    void allowsWithinWindowAndRejectsExceedingRequest() throws Exception {
        assertThat(handle(IP)).isTrue();
        assertThat(handle(IP)).isTrue();
        assertThat(handle(IP)).isFalse();
    }

    /** 超限 429 + JSON 错误体：error/message/retryAfterSeconds 三字段齐全 */
    @Test
    void exceedingRequestReturns429WithErrorBody() throws Exception {
        handle(IP);
        handle(IP);
        MockHttpServletResponse response = handleResponse(IP);

        assertThat(response.getStatus()).isEqualTo(429);
        assertThat(response.getContentType()).contains("application/json");
        Map<String, Object> body = new ObjectMapper().readValue(
                response.getContentAsString(), new TypeReference<>() {});
        assertThat(body).contains(
                entry("error", "rate_limited"),
                entry("message", "请求过于频繁，请稍后再试"));
        assertThat(((Number) body.get("retryAfterSeconds")).intValue()).isGreaterThanOrEqualTo(1);
    }

    /** 不同 IP 独立计数互不影响 */
    @Test
    void countsArePerIp() throws Exception {
        assertThat(handle(IP)).isTrue();
        assertThat(handle(IP)).isTrue();
        assertThat(handle(IP)).isFalse();

        // 另一 IP 自己的窗口从 1 开始，不受前一个 IP 已超限影响
        assertThat(handle("198.51.100.9")).isTrue();
        assertThat(handle("198.51.100.9")).isTrue();
    }

    /** 窗口翻到下一分钟即重置：上一分钟超限的 IP 恢复放行 */
    @Test
    void windowResetOnNextMinute() throws Exception {
        handle(IP);
        handle(IP);
        assertThat(handle(IP)).isFalse();

        // 模拟时钟前进：把该 IP 窗口起始改写为上一分钟（等价窗口翻转）
        long oldWindow = nowWindowStart() - 1;
        ConcurrentHashMap<String, long[]> counts = windowCounts();
        counts.put(IP, new long[]{oldWindow, 2});

        // 新窗口从 1 重新计：第 1、2 发放行，第 3 发才超限
        assertThat(handle(IP)).isTrue();
        assertThat(handle(IP)).isTrue();
        assertThat(handle(IP)).isFalse();
    }

    /** trust-forwarded-for=true：同 XFF 首跳共享配额（代理后取真实客户端） */
    @Test
    void trustsForwardedForWhenEnabled() throws Exception {
        ReflectionTestUtils.setField(interceptor, "trustForwardedFor", true);

        // 同一 XFF 首跳、不同直连地址 → 按 XFF 计，第 3 次超限
        assertThat(handleWithForwarded(IP, "198.51.100.1")).isTrue();
        assertThat(handleWithForwarded("192.0.2.1", "198.51.100.1")).isTrue();
        assertThat(handleWithForwarded(IP, "198.51.100.1")).isFalse();
    }

    /** trust-forwarded-for=false（默认）：忽略 XFF，各按直连地址独立计数 */
    @Test
    void ignoresForwardedForWhenDisabled() throws Exception {
        handleWithForwarded(IP, "198.51.100.1");
        handleWithForwarded(IP, "198.51.100.1");
        handleWithForwarded(IP, "198.51.100.1");
        // 同直连 IP 连发 3 次，即使 XFF 相同也超限 → 计数走 remoteAddr
        assertThat(handleWithForwarded(IP, "198.51.100.1")).isFalse();
    }

    /** 惰性清理：过期窗口条目（非当前分钟）被移除，当前分钟条目保留 */
    @Test
    void cleanupRemovesExpiredWindowsOnly() throws Exception {
        ConcurrentHashMap<String, long[]> counts = windowCounts();
        counts.put("expired-ip", new long[]{nowWindowStart() - 5, 1});
        counts.put(IP, new long[]{nowWindowStart(), 1});

        ReflectionTestUtils.invokeMethod(interceptor, "cleanupExpiredWindows");

        assertThat(counts).containsOnlyKeys(IP);
    }

    private boolean handle(String ip) throws Exception {
        return interceptor.preHandle(request(ip), new MockHttpServletResponse(), new Object());
    }

    private boolean handleWithForwarded(String remoteAddr, String forwardedFor) throws Exception {
        MockHttpServletRequest request = request(remoteAddr);
        request.addHeader("X-Forwarded-For", forwardedFor);
        return interceptor.preHandle(request, new MockHttpServletResponse(), new Object());
    }

    private MockHttpServletResponse handleResponse(String ip) throws Exception {
        MockHttpServletResponse response = new MockHttpServletResponse();
        interceptor.preHandle(request(ip), response, new Object());
        return response;
    }

    private static MockHttpServletRequest request(String ip) {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/chat");
        request.setRemoteAddr(ip);
        return request;
    }

    @SuppressWarnings("unchecked")
    private ConcurrentHashMap<String, long[]> windowCounts() {
        return (ConcurrentHashMap<String, long[]>) ReflectionTestUtils.getField(interceptor, "windowCounts");
    }

    private static long nowWindowStart() {
        return System.currentTimeMillis() / 1_000 / 60;
    }
}
