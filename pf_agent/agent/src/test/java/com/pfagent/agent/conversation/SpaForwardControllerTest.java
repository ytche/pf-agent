package com.pfagent.agent.conversation;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.forwardedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 根路径 SPA forward（F-020 实施 Spec §4.2）
 *
 * 显式 forward 到 dist/index.html，不依赖「/ 自动命中静态目录」；hash 路由刷新仍回到同一页面。
 */
class SpaForwardControllerTest {

    @Test
    void rootForwardsToDistIndex() throws Exception {
        MockMvc mvc = MockMvcBuilders.standaloneSetup(new SpaForwardController()).build();

        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(forwardedUrl("/dist/index.html"));
    }
}
