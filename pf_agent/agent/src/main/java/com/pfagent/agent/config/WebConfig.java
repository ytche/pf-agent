package com.pfagent.agent.config;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Web 配置 — 注册拦截器
 *
 * 注册顺序 Auth → RateLimit：各自独立 preHandle，先后不敏感。鉴权拦截器只拦
 * /api/chat、/api/chat/feedback 与 /api/conversations/**——/api/auth/**、/api/health、
 * 静态资源与 / 天然不在拦截范围（豁免由路径注册保证）；pf.auth.enabled=false（默认）
 * 时 preHandle 全放行，enabled=true 时无 token 匿名放行、非法 token 401。
 *
 * 限频拦截器（SP2 F-010）按 pf.rate-limit.enabled 条件装配，absent 时 ObjectProvider
 * 为空跳过注册（默认关闭 = 零行为变化）。SP7 T3 起拦截范围纳入 /api/auth/**（§5 风险表：
 * 注册接口防刷库，开关同源）；F-020 起会话 API 全部纳入鉴权与限频；/api/chat/feedback 不限。
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Autowired
    private AuthInterceptor authInterceptor;
    @Autowired
    private ObjectProvider<RateLimitInterceptor> rateLimitInterceptor;

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // SP7 D5 + F-020：鉴权覆盖问答主入口、反馈与全部会话接口；/api/auth/** 全豁免
        registry.addInterceptor(authInterceptor)
                .addPathPatterns("/api/chat", "/api/chat/feedback", "/api/conversations/**");
        // F-010 按 IP 限频：/api/chat + /api/auth/**（SP7 防注册刷库）+ 会话接口（F-020）
        rateLimitInterceptor.ifAvailable(interceptor ->
                registry.addInterceptor(interceptor)
                        .addPathPatterns("/api/chat", "/api/auth/**", "/api/conversations/**"));
    }
}
