package com.pfagent.agent.conversation;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pfagent.agent.memory.ConversationStore;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.time.Instant;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 会话 HTTP 面：路由、错误码与 204 语义（F-020 实施 Spec §7；前端冻结契约 §5）
 */
class ConversationControllerTest {

    private final ConversationStore store = mock(ConversationStore.class);
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        ConversationAccessGuard guard = new ConversationAccessGuard(store);
        ConversationService service = new ConversationService();
        org.springframework.test.util.ReflectionTestUtils.setField(service, "conversationStore", store);
        org.springframework.test.util.ReflectionTestUtils.setField(service, "accessGuard", guard);
        org.springframework.test.util.ReflectionTestUtils.setField(service, "chatService", mock(com.pfagent.agent.chat.ChatService.class));
        org.springframework.test.util.ReflectionTestUtils.setField(service, "objectMapper", new ObjectMapper());
        org.springframework.test.util.ReflectionTestUtils.setField(service, "historyRounds", 20);
        org.springframework.test.util.ReflectionTestUtils.setField(service, "defaultPageSize", 30);
        mvc = MockMvcBuilders.standaloneSetup(new ConversationController(service))
                .setControllerAdvice(new ConversationExceptionHandler())
                .build();
    }

    /** 账号列表必须登录：匿名 401 unauthorized */
    @Test
    void anonymousListReturns401() throws Exception {
        mvc.perform(get("/api/conversations"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error").value("unauthorized"));
    }

    /** 从未存在/不可见 → 404 conversation_not_found，不伪装成已删除 */
    @Test
    void unknownConversationReturns404() throws Exception {
        when(store.getConversation(anyString())).thenReturn(java.util.Optional.empty());

        mvc.perform(get("/api/conversations/ghost"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("conversation_not_found"));
    }

    /** 匿名访问 owner 为空的会话成功，返回摘要 + 空消息列表 */
    @Test
    void anonymousReadsAnonymousConversation() throws Exception {
        when(store.getConversation("c1")).thenReturn(java.util.Optional.of(
                new ConversationStore.ConversationView("c1", null, false, null, 0, 0, 0,
                        Instant.EPOCH, Instant.EPOCH)));

        mvc.perform(get("/api/conversations/c1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("c1"))
                .andExpect(jsonPath("$.messages").isEmpty());
    }

    /** 登录访问未认领匿名会话 → 403 forbidden（必须显式认领） */
    @Test
    void authenticatedReadingAnonymousGets403() throws Exception {
        when(store.getConversation("c1")).thenReturn(java.util.Optional.of(
                new ConversationStore.ConversationView("c1", null, false, null, 0, 0, 0,
                        Instant.EPOCH, Instant.EPOCH)));

        mvc.perform(get("/api/conversations/c1").requestAttr("pfAuthUserId", 7L))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error").value("forbidden"));
    }

    /** 删除成功返回 204 无响应体 */
    @Test
    void deleteReturns204() throws Exception {
        when(store.getConversation("c1")).thenReturn(java.util.Optional.of(
                new ConversationStore.ConversationView("c1", null, false, null, 0, 0, 0,
                        Instant.EPOCH, Instant.EPOCH)));

        mvc.perform(delete("/api/conversations/c1"))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""));
    }

    /** lookup 只返回 owner 为空的会话 */
    @Test
    void lookupReturnsItems() throws Exception {
        when(store.lookupConversations(java.util.List.of("c1"))).thenReturn(java.util.List.of(
                new ConversationStore.ConversationView("c1", null, false, null, 1, 1, 1,
                        Instant.EPOCH, Instant.EPOCH)));

        mvc.perform(post("/api/conversations/lookup")
                        .contentType("application/json")
                        .content("{\"ids\":[\"c1\"]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].id").value("c1"));
    }
}
