package com.pfagent.agent.chat;

import com.pfagent.agent.memory.AnonymousQuotaService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ChatController 单元测试（v1.5 B6 扩展 + 错误标注闭环 + SP2 F-011 匿名配额）
 *
 * 覆盖 POST /api/chat 请求→响应：
 *  - conversationId 透传（请求带 → 响应回带；请求缺 → service 生成）
 *  - gapReported / sources 字段随响应返回
 *  - service 抛异常时异常上抛（由 Spring 框架转 500，前端提示稍后重试）
 *
 * 覆盖 POST /api/chat/feedback：
 *  - 委托 FeedbackRecorder 入库，成功返回 200 + ok=true + 记录 id
 *  - 未入库（DB 不可用/写入失败）返回 503 + ok=false + 降级原因，不谎报成功
 *
 * SP2 F-011 配额（默认关闭 → ObjectProvider 空跳过检查，故既有用例行为不变）：
 *  - 配额开启 + 达上限：429 + quota_exceeded JSON，chatService.ask 不被调用（fail-fast）
 *  - 配额开启 + 未达上限 / 新会话（无 conversationId）：正常放行
 */
@ExtendWith(MockitoExtension.class)
class ChatControllerTest {

    @Mock
    private ChatService chatService;

    @Mock
    private FeedbackRecorder feedbackRecorder;

    @Mock
    private ObjectProvider<AnonymousQuotaService> quotaServiceProvider;

    @Mock
    private AnonymousQuotaService quotaService;

    @InjectMocks
    private ChatController controller;

    /** 委托问答服务并透传 conversationId */
    @Test
    void chatDelegatesAndPassesConversationId() {
        ChatResponse expected = new ChatResponse("答", List.of(), false, "cid-x");
        when(chatService.ask("问题", "cid-x", null)).thenReturn(expected);

        ChatResponse resp = chatBody(new ChatRequest("问题", "cid-x"));

        assertThat(resp).isSameAs(expected);
        verify(chatService).ask("问题", "cid-x", null);
    }

    /** 请求缺 conversationId 时透传 null 由 service 生成 */
    @Test
    void chatMissingConversationIdDelegatesToServiceGeneration() {
        ChatResponse expected = new ChatResponse("答", List.of(), false, "gen-uuid");
        when(chatService.ask("问题", null, null)).thenReturn(expected);

        ChatResponse resp = chatBody(new ChatRequest("问题", null));

        assertThat(resp.conversationId()).isEqualTo("gen-uuid");
        verify(chatService).ask("问题", null, null);
    }

    /** 响应含 gapReported 与 sources 字段 */
    @Test
    void chatResponseContainsGapReportedAndSources() {
        ChatResponse.SourceRef src = new ChatResponse.SourceRef("核心规则书 (CRB)", "法术 > 火球术", "spell_CRB_0001", "正文");
        ChatResponse expected = new ChatResponse("答", List.of(src), true, "cid");
        when(chatService.ask(anyString(), any(), any())).thenReturn(expected);

        ChatResponse resp = chatBody(new ChatRequest("q", "cid"));

        assertThat(resp.gapReported()).isTrue();
        assertThat(resp.sources()).containsExactly(src);
    }

    /** service 抛异常时异常上抛，由框架转 500（如 LLM 调用未注册工具） */
    @Test
    void chatServiceExceptionPropagatesForFramework500() {
        when(chatService.ask(anyString(), any(), any()))
                .thenThrow(new IllegalStateException("LLM 调用了未注册的工具: hack_tool"));

        assertThatThrownBy(() -> controller.chat(null, new ChatRequest("q", null)))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("未注册的工具");
    }

    /** F-011：配额开启且已用轮数未达上限 → 正常放行走问答 */
    @Test
    void quotaEnabledUnderLimitAllowsChat() {
        when(quotaServiceProvider.getIfAvailable()).thenReturn(quotaService);
        when(quotaService.isExceeded("cid-x")).thenReturn(false);
        ChatResponse expected = new ChatResponse("答", List.of(), false, "cid-x");
        when(chatService.ask("问题", "cid-x", null)).thenReturn(expected);

        ChatResponse resp = chatBody(new ChatRequest("问题", "cid-x"));

        assertThat(resp).isSameAs(expected);
        verify(chatService).ask("问题", "cid-x", null);
    }

    /** F-011：配额开启且会话达上限 → 429 quota_exceeded，fail-fast 不触发 LLM */
    @Test
    void quotaEnabledOverLimitReturns429AndSkipsAsk() {
        when(quotaServiceProvider.getIfAvailable()).thenReturn(quotaService);
        when(quotaService.isExceeded("cid-x")).thenReturn(true);
        when(quotaService.getAnonymousRounds()).thenReturn(20);

        ResponseEntity<?> resp = controller.chat(null, new ChatRequest("问题", "cid-x"));

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.TOO_MANY_REQUESTS);
        @SuppressWarnings("unchecked")
        Map<String, Object> body = (Map<String, Object>) resp.getBody();
        assertThat(body).containsEntry("error", "quota_exceeded");
        assertThat((String) body.get("message")).contains("20 轮");
        verify(chatService, never()).ask(anyString(), any(), any());
    }

    /** F-011：新会话（无 conversationId）即使配额服务存在也直接放行、不做计数查询 */
    @Test
    void quotaEnabledNewConversationWithoutIdPassesThrough() {
        when(quotaServiceProvider.getIfAvailable()).thenReturn(quotaService);
        ChatResponse expected = new ChatResponse("答", List.of(), false, "gen-uuid");
        when(chatService.ask("问题", null, null)).thenReturn(expected);

        ChatResponse resp = chatBody(new ChatRequest("问题", null));

        assertThat(resp).isSameAs(expected);
        verify(quotaService, never()).isExceeded(anyString());
    }

    /** F-020：登录用户请求把 uid 透传给 service，用于会话 owner 写入与归属校验 */
    @Test
    void chatPassesAuthenticatedUserIdToService() {
        ChatResponse expected = new ChatResponse("答", List.of(), false, "cid", 11L, 2, java.time.Instant.EPOCH);
        when(chatService.ask("问题", "cid", 7L)).thenReturn(expected);

        ChatResponse resp = (ChatResponse) controller.chat(7L, new ChatRequest("问题", "cid")).getBody();

        assertThat(resp.messageId()).isEqualTo(11L);
        verify(chatService).ask("问题", "cid", 7L);
    }

    /** 健康检查返回健康提示 */
    @Test
    void healthReturnsOkMessage() {

        assertThat(controller.health()).isEqualTo("OK — PF Agent is running");
    }

    /** 错误标注委托记录器入库，返回 200 + ok=true + 记录 id */
    @Test
    void feedbackDelegatesToRecorderAndReturnsOkWithId() {
        FeedbackRequest req = new FeedbackRequest("cid", "q", "a", List.of(), "事实错误", "c", "m");
        when(feedbackRecorder.record(req)).thenReturn(FeedbackResponse.persisted("ann-123456-7890"));

        ResponseEntity<FeedbackResponse> resp = controller.feedback(req);

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(resp.getBody().ok()).isTrue();
        assertThat(resp.getBody().id()).isEqualTo("ann-123456-7890");
        assertThat(resp.getBody().reason()).isNull();
        verify(feedbackRecorder).record(req);
    }

    /** sources 为空且可选字段缺省时委托记录器仍正常 */
    @Test
    void feedbackWithoutOptionalFieldsStillDelegates() {
        FeedbackRequest req = new FeedbackRequest("cid", "q", "a", List.of(), "结构差", null, null);
        when(feedbackRecorder.record(req)).thenReturn(FeedbackResponse.persisted("ann-x"));

        ResponseEntity<FeedbackResponse> resp = controller.feedback(req);

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(resp.getBody().ok()).isTrue();
        verify(feedbackRecorder).record(req);
    }

    /** 未入库（DB 不可用/写入失败）→ 503 + ok=false + 降级原因 + 无 id，不谎报成功 */
    @Test
    void feedbackNotPersistedReturns503WithDegradedMarker() {
        FeedbackRequest req = new FeedbackRequest("cid", "q", "a", List.of(), "事实错误", null, null);
        when(feedbackRecorder.record(req)).thenReturn(FeedbackResponse.failed(FeedbackResponse.REASON_DB_UNAVAILABLE));

        ResponseEntity<FeedbackResponse> resp = controller.feedback(req);

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(resp.getBody().ok()).isFalse();
        assertThat(resp.getBody().id()).isNull();
        assertThat(resp.getBody().reason()).isEqualTo(FeedbackResponse.REASON_DB_UNAVAILABLE);
    }

    /** 入参非法（字段超长）→ 400（客户端问题），不归为服务端 503 */
    @Test
    void feedbackInvalidInputReturns400() {
        FeedbackRequest req = new FeedbackRequest("cid", "q", "a", List.of(), "x".repeat(64), null, null);
        when(feedbackRecorder.record(req)).thenReturn(FeedbackResponse.failed(FeedbackResponse.REASON_INVALID_INPUT));

        ResponseEntity<FeedbackResponse> resp = controller.feedback(req);

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(resp.getBody().ok()).isFalse();
        assertThat(resp.getBody().reason()).isEqualTo(FeedbackResponse.REASON_INVALID_INPUT);
    }

    /** chat 200 响应取 ChatResponse body（返回类型已改 ResponseEntity<?> 以容纳 429 JSON） */
    private ChatResponse chatBody(ChatRequest request) {
        return (ChatResponse) controller.chat(null, request).getBody();
    }
}
