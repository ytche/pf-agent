package com.pfagent.agent.admin;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

/**
 * 管理后台页面入口（F-023）。
 *
 * <p>页面是独立的 static/admin.html，不进入 Vue SPA；显式 forward 避免依赖
 * 静态目录对 /admin/ 的默认欢迎页匹配。接口仍由 AdminInterceptor 守卫。
 */
@Controller
public class AdminPageController {

    @GetMapping({"/admin", "/admin/"})
    public String adminPage() {
        return "forward:/admin.html";
    }
}
