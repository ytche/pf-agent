package com.pfagent.agent.conversation;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

/**
 * 根路径 SPA 入口（F-020 实施 Spec §4.2）
 *
 * 前端 hash 路由只需要一个入口页：显式 forward 到构建产物
 * classpath:/static/dist/index.html，不依赖「/ 自动命中静态目录」的假设；
 * 刷新 /#/c/{id} 仍是同一页面，不需要 history 路由 fallback。
 */
@Controller
public class SpaForwardController {

    @GetMapping({"/", "/index.html"})
    public String forwardToSpa() {
        return "forward:/dist/index.html";
    }
}
