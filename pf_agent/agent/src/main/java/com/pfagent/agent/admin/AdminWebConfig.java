package com.pfagent.agent.admin;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * 管理后台 Web 配置（F-023）
 *
 * 把 {@link AdminInterceptor} 注册到 {@code /api/admin/**}。单独成类（不复用 config.WebConfig）
 * 以保持 admin 模块自包含：admin 路由的身份/角色校验只由本拦截器负责，与 /api/chat 的
 * AuthInterceptor 互不影响。Spring 会自动收集所有 WebMvcConfigurer bean。
 */
@Configuration
public class AdminWebConfig implements WebMvcConfigurer {

    @Autowired
    private AdminInterceptor adminInterceptor;

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(adminInterceptor).addPathPatterns("/api/admin/**");
    }
}
