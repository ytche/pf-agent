package com.pfagent.agent.usage;

import com.pfagent.agent.admin.AdminService;
import com.pfagent.agent.config.AuthInterceptor;
import com.pfagent.agent.conversation.ConversationAccessGuard;
import com.pfagent.agent.conversation.ConversationExceptionHandler;
import com.pfagent.agent.conversation.ConversationNotFoundException;
import com.pfagent.agent.memory.ConversationStore;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * /api/usage/summary HTTP 面：管理员全局 / 普通用户仅自己 / 匿名仅当前会话，
 * 越权一律拒绝且不泄露他人数据。
 */
class UsageControllerTest {

    private static final String CID = "00000000-0000-0000-0000-000000000001";

    private UsageService service;
    private AdminService adminService;
    private ConversationAccessGuard guard;
    private MockMvc mvc;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        service = mock(UsageService.class);
        adminService = mock(AdminService.class);
        guard = mock(ConversationAccessGuard.class);
        ObjectProvider<UsageService> serviceProvider = mock(ObjectProvider.class);
        ObjectProvider<AdminService> adminProvider = mock(ObjectProvider.class);
        when(serviceProvider.getIfAvailable()).thenReturn(service);
        when(adminProvider.getIfAvailable()).thenReturn(adminService);
        when(service.summarize(anyString(), anyString(), any(), any(), anyString()))
                .thenReturn(sample("owner"));

        UsageController controller = new UsageController(serviceProvider, adminProvider, guard);
        mvc = MockMvcBuilders.standaloneSetup(controller)
                .setControllerAdvice(new ConversationExceptionHandler())
                .build();
    }

    @Test
    void anonymousWithoutConversationIsRejected() throws Exception {
        mvc.perform(get("/api/usage/summary"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("invalid_request"));

        verify(service, never()).summarize(anyString(), anyString(), any(), any(), anyString());
    }

    @Test
    void anonymousWithMalformedConversationIsRejected() throws Exception {
        mvc.perform(get("/api/usage/summary").param("conversationId", "not-a-uuid"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("invalid_request"));
    }

    @Test
    void anonymousOnlySeesCurrentConversation() throws Exception {
        when(guard.requireReadable(CID, null)).thenReturn(view());
        when(service.summarize("month", "day", null, CID, "conversation"))
                .thenReturn(sample("conversation"));

        mvc.perform(get("/api/usage/summary").param("conversationId", CID))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.scope").value("conversation"))
                .andExpect(jsonPath("$.timezone").value("Asia/Shanghai"));

        verify(service).summarize("month", "day", null, CID, "conversation");
    }

    @Test
    void anonymousCannotEnumerateOthersConversation() throws Exception {
        when(guard.requireReadable(CID, null)).thenThrow(new ConversationNotFoundException(CID));

        mvc.perform(get("/api/usage/summary").param("conversationId", CID))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("conversation_not_found"))
                .andExpect(jsonPath("$.totals").doesNotExist());
    }

    @Test
    void anonymousCannotGroupByOwner() throws Exception {
        when(guard.requireReadable(CID, null)).thenReturn(view());

        mvc.perform(get("/api/usage/summary")
                        .param("conversationId", CID)
                        .param("groupBy", "owner"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error").value("usage_owner_group_forbidden"));
    }

    @Test
    void regularUserIsScopedToOwnOwnerAndCannotGroupByOwner() throws Exception {
        when(adminService.isAdmin("bob")).thenReturn(false);
        when(service.summarize("month", "day", 7L, null, "owner")).thenReturn(sample("owner"));

        mvc.perform(get("/api/usage/summary")
                        .requestAttr(AuthInterceptor.USER_ID_ATTRIBUTE, 7L)
                        .requestAttr(AuthInterceptor.USERNAME_ATTRIBUTE, "bob"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.scope").value("owner"));

        verify(service).summarize("month", "day", 7L, null, "owner");

        mvc.perform(get("/api/usage/summary")
                        .requestAttr(AuthInterceptor.USER_ID_ATTRIBUTE, 7L)
                        .requestAttr(AuthInterceptor.USERNAME_ATTRIBUTE, "bob")
                        .param("groupBy", "owner")
                        .param("ownerId", "9"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error").value("usage_owner_group_forbidden"));
    }

    @Test
    void regularUserCannotReadOthersOwnerId() throws Exception {
        when(adminService.isAdmin("bob")).thenReturn(false);

        mvc.perform(get("/api/usage/summary")
                        .requestAttr(AuthInterceptor.USER_ID_ATTRIBUTE, 7L)
                        .requestAttr(AuthInterceptor.USERNAME_ATTRIBUTE, "bob")
                        .param("ownerId", "9"))
                .andExpect(status().isOk());

        verify(service).summarize("month", "day", 7L, null, "owner");
    }

    @Test
    void adminSeesGlobalAndCanGroupByOwner() throws Exception {
        when(adminService.isAdmin("root")).thenReturn(true);
        when(service.summarize("month", "owner", null, null, "global"))
                .thenReturn(sample("global"));

        mvc.perform(get("/api/usage/summary")
                        .requestAttr(AuthInterceptor.USER_ID_ATTRIBUTE, 1L)
                        .requestAttr(AuthInterceptor.USERNAME_ATTRIBUTE, "root")
                        .param("groupBy", "owner"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.scope").value("global"));

        verify(service).summarize("month", "owner", null, null, "global");
    }

    @Test
    void adminCanFilterByOwnerId() throws Exception {
        when(adminService.isAdmin("root")).thenReturn(true);
        when(service.summarize("month", "day", 9L, null, "owner")).thenReturn(sample("owner"));

        mvc.perform(get("/api/usage/summary")
                        .requestAttr(AuthInterceptor.USER_ID_ATTRIBUTE, 1L)
                        .requestAttr(AuthInterceptor.USERNAME_ATTRIBUTE, "root")
                        .param("ownerId", "9"))
                .andExpect(status().isOk());

        verify(service).summarize("month", "day", 9L, null, "owner");
    }

    @Test
    void usageUnavailableInMemoryModeReturns503() throws Exception {
        ObjectProvider<UsageService> empty = mock(ObjectProvider.class);
        when(empty.getIfAvailable()).thenReturn(null);
        ObjectProvider<AdminService> adminProvider = mock(ObjectProvider.class);
        UsageController controller = new UsageController(empty, adminProvider, guard);
        MockMvc standalone = MockMvcBuilders.standaloneSetup(controller)
                .setControllerAdvice(new ConversationExceptionHandler())
                .build();

        standalone.perform(get("/api/usage/summary").requestAttr(AuthInterceptor.USER_ID_ATTRIBUTE, 7L))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error").value("usage_unavailable"));
    }

    @Test
    void invalidRangeIsRejected() throws Exception {
        mvc.perform(get("/api/usage/summary")
                        .requestAttr(AuthInterceptor.USER_ID_ATTRIBUTE, 7L)
                        .param("range", "week"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("invalid_request"));
    }

    private static ConversationStore.ConversationView view() {
        return new ConversationStore.ConversationView(CID, null, false, null, 1, 1, 1,
                Instant.EPOCH, Instant.EPOCH);
    }

    private static UsageSummaryResponse sample(String scope) {
        return new UsageSummaryResponse(
                "month", "day", scope, "Asia/Shanghai", "预测公式说明",
                Instant.parse("2026-10-31T16:00:00Z"), Instant.parse("2026-11-13T02:00:00Z"),
                new UsageSummaryResponse.Totals(2, 100L, 50L, 150L, new BigDecimal("0.5"), "CNY", 0),
                List.of(),
                new UsageSummaryResponse.Forecast("Asia/Shanghai", new BigDecimal("0.5"),
                        new BigDecimal("0.1"), 7, 5, 17, new BigDecimal("2.2"), "预测公式说明"));
    }
}
