package com.pfagent.agent.conversation;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.pfagent.agent.chat.ChatResponse;
import com.pfagent.agent.chat.ChatService;
import com.pfagent.agent.memory.ConversationStore;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * 会话 API 业务编排（F-020 实施 Spec §8；前端冻结契约字段）
 *
 * 覆盖：账号列表必须登录、匿名 lookup、详情引用快照组装、PATCH 校验、
 * 认领结果分类（claimed/alreadyOwned/rejected）、重新生成响应映射。
 */
class ConversationServiceTest {

    private final ConversationStore store = mock(ConversationStore.class);
    private final ConversationAccessGuard guard = mock(ConversationAccessGuard.class);
    private final ChatService chatService = mock(ChatService.class);
    private ConversationService service;

    @BeforeEach
    void setUp() {
        service = new ConversationService();
        ReflectionTestUtils.setField(service, "conversationStore", store);
        ReflectionTestUtils.setField(service, "accessGuard", guard);
        ReflectionTestUtils.setField(service, "chatService", chatService);
        ReflectionTestUtils.setField(service, "objectMapper", new ObjectMapper());
        ReflectionTestUtils.setField(service, "historyRounds", 20);
        ReflectionTestUtils.setField(service, "defaultPageSize", 30);
    }

    @Test
    void createWritesOwnerAndReturnsEmptySummary() {
        when(store.createConversation(anyString(), eq(7L), any())).thenAnswer(inv ->
                new ConversationStore.ConversationView(inv.getArgument(0), null, false, 7L,
                        0, 0, 0, inv.getArgument(2), inv.getArgument(2)));

        ConversationSummary summary = service.create(7L);

        assertThat(summary.id()).isNotBlank();
        assertThat(summary.messageRounds()).isZero();
        verify(store).createConversation(summary.id(), 7L, summary.createdAt());
    }

    @Test
    void listRequiresLogin() {
        assertThatThrownBy(() -> service.list(null, null, 30))
                .isInstanceOf(UnauthorizedException.class);
        verify(store, never()).listOwnedConversations(any(), any(), anyInt());
    }

    @Test
    void listReturnsFrozenPageShape() {
        when(store.listOwnedConversations(7L, "30", 30)).thenReturn(
                new ConversationStore.ConversationPage(List.of(view("c1", 7L)), "60"));

        ConversationPageResponse page = service.list(7L, "30", 30);

        assertThat(page.items()).extracting(ConversationSummary::id).containsExactly("c1");
        assertThat(page.nextCursor()).isEqualTo("60");
    }

    @Test
    void lookupDelegatesDistinctIds() {
        when(store.lookupConversations(List.of("a", "b"))).thenReturn(List.of(view("a", null)));

        LookupResponse response = service.lookup(List.of("a", "b", "a", " "));

        assertThat(response.items()).extracting(ConversationSummary::id).containsExactly("a");
    }

    @Test
    void detailAssemblesMessagesWithOwnSourcesAndCompletedAt() {
        when(guard.requireReadable("c1", null)).thenReturn(view("c1", null));
        when(store.getConversation("c1")).thenReturn(Optional.of(view("c1", null)));
        when(store.history("c1", 40)).thenReturn(List.of(
                new ConversationStore.StoredMessage(1L, 1, "user", "q", null, false, Instant.EPOCH),
                new ConversationStore.StoredMessage(2L, 2, "assistant", "a",
                        "[{\"book\":\"CRB\",\"tocPath\":\"p\",\"chunkId\":\"c\",\"content\":\"x\"}]",
                        true, Instant.EPOCH.plusSeconds(1))));

        ConversationDetail detail = service.detail("c1", null);

        assertThat(detail.messages()).hasSize(2);
        ConversationMessage user = detail.messages().get(0);
        assertThat(user.sources()).isNull();
        assertThat(user.completedAt()).isNull();
        ConversationMessage assistant = detail.messages().get(1);
        assertThat(assistant.sources()).hasSize(1);
        assertThat(assistant.sources().get(0).book()).isEqualTo("CRB");
        assertThat(assistant.gapReported()).isTrue();
        assertThat(assistant.completedAt()).isEqualTo(Instant.EPOCH.plusSeconds(1));
    }

    @Test
    void patchValidatesTitleLengthAndAppliesFields() {
        when(guard.requireReadable("c1", 7L)).thenReturn(view("c1", 7L));
        when(store.getConversation("c1")).thenReturn(Optional.of(view("c1", 7L)));

        service.patch("c1", 7L, new PatchConversationRequest("新标题", true));

        verify(store).renameConversation("c1", "新标题");
        verify(store).setPinned("c1", true);

        assertThatThrownBy(() -> service.patch("c1", 7L,
                new PatchConversationRequest("x".repeat(201), null)))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void claimClassifiesClaimedAlreadyOwnedAndRejected() {
        when(store.claimConversation("a", 7L)).thenReturn(ConversationStore.ClaimStatus.CLAIMED);
        when(store.claimConversation("b", 7L)).thenReturn(ConversationStore.ClaimStatus.ALREADY_OWNER);
        when(store.claimConversation("c", 7L)).thenReturn(ConversationStore.ClaimStatus.OWNED_BY_OTHER);
        when(store.claimConversation("d", 7L)).thenReturn(ConversationStore.ClaimStatus.NOT_FOUND);

        ClaimResponse response = service.claim(7L, List.of("a", "b", "c", "d"));

        assertThat(response.claimed()).containsExactly("a");
        assertThat(response.alreadyOwned()).containsExactly("b");
        assertThat(response.rejected()).containsExactly("c", "d");
    }

    @Test
    void claimRequiresLogin() {
        assertThatThrownBy(() -> service.claim(null, List.of("a")))
                .isInstanceOf(UnauthorizedException.class);
    }

    @Test
    void deleteUsesAccessGuardThenStore() {
        when(guard.requireReadable("c1", 7L)).thenReturn(view("c1", 7L));

        service.delete("c1", 7L);

        ArgumentCaptor<String> captor = ArgumentCaptor.forClass(String.class);
        verify(store).deleteConversation(captor.capture());
        assertThat(captor.getValue()).isEqualTo("c1");
    }

    @Test
    void regenerateMapsChatServiceResultToChatAnswer() {
        when(chatService.regenerate("c1", 7L, 2)).thenReturn(new ChatService.RegenerateResult(
                "c1", 9L, 2, "答", List.of(new ChatResponse.SourceRef("CRB", "p", "c", "x")),
                true, Instant.EPOCH));

        ChatResponse response = service.regenerate("c1", 7L, 2);

        assertThat(response.answer()).isEqualTo("答");
        assertThat(response.messageId()).isEqualTo(9L);
        assertThat(response.messageSeq()).isEqualTo(2);
        assertThat(response.completedAt()).isEqualTo(Instant.EPOCH);
        assertThat(response.gapReported()).isTrue();
    }

    private static ConversationStore.ConversationView view(String id, Long owner) {
        return new ConversationStore.ConversationView(id, null, false, owner, 0, 0, 0,
                Instant.EPOCH, Instant.EPOCH);
    }
}
