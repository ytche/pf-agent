package com.pfagent.agent.config;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * 登录鉴权拦截器（占位）
 *
 * 当前阶段直接放行；后续接入微信小程序登录后，在此实现：
 *  - 校验 token（小程序 wx.login → 后端换取 session / JWT）
 *  - 从请求头提取凭证，解析用户身份放入上下文
 *  - 校验失败返回 401
 */
@Component
public class AuthInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(HttpServletRequest request,
                             HttpServletResponse response,
                             Object handler) {
        // TODO: 登录拦截逻辑 — 见类注释
        return true;
    }
}
