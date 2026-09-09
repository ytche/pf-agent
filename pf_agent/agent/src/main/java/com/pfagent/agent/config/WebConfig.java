package com.pfagent.agent.config;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Web 配置 — 注册拦截器
 *
 * 注册顺序 Auth → RateLimit：各自独立 preHandle，先后不敏感。限频拦截器按
 * pf.rate-limit.enabled 条件装配，absent 时 ObjectProvider 为空跳过注册（默认关闭 =
 * 零行为变化）。addPathPatterns("/api/chat") 为精确匹配——/api/chat/feedback 等子路径
 * 不在限频范围（非目标，仅拦问答主入口）。
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Autowired
    private AuthInterceptor authInterceptor;
    @Autowired
    private ObjectProvider<RateLimitInterceptor> rateLimitInterceptor;

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(authInterceptor)
                // 健康检查不需要登录
                .excludePathPatterns("/api/health");
        // F-010 按 IP 限频（仅 /api/chat；feedback/health 不限）
        rateLimitInterceptor.ifAvailable(interceptor ->
                registry.addInterceptor(interceptor).addPathPatterns("/api/chat"));
    }
}
