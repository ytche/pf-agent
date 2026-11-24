package com.pfagent.agent.admin;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.forwardedUrl;

class AdminPageControllerTest {

    private final MockMvc mockMvc = MockMvcBuilders
            .standaloneSetup(new AdminPageController())
            .build();

    @Test
    void forwardsBothAdminPathsToStaticPage() throws Exception {
        mockMvc.perform(get("/admin")).andExpect(forwardedUrl("/admin.html"));
        mockMvc.perform(get("/admin/")).andExpect(forwardedUrl("/admin.html"));
    }

    @Test
    void staticPageExists() {
        assertThat(getClass().getResource("/static/admin.html")).isNotNull();
    }
}
