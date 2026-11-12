package com.pfagent.agent.conversation;

import com.pfagent.agent.memory.ConversationStore;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * 会话归属访问规则（F-020 实施 Spec §8.2）
 */
class ConversationAccessGuardTest {

    private final ConversationStore store = mock(ConversationStore.class);
    private final ConversationAccessGuard guard = new ConversationAccessGuard(store);

    @Test
    void anonymousCanReadAnonymousConversationByUuid() {
        when(store.getConversation("c1")).thenReturn(Optional.of(view("c1", null)));

        assertThat(guard.requireReadable("c1", null).id()).isEqualTo("c1");
    }

    @Test
    void authenticatedReadingAnonymousConversationIsForbiddenUntilClaim() {
        when(store.getConversation("c1")).thenReturn(Optional.of(view("c1", null)));

        assertThatThrownBy(() -> guard.requireReadable("c1", 7L))
                .isInstanceOf(ConversationForbiddenException.class);
    }

    @Test
    void ownerCanReadOwnConversation() {
        when(store.getConversation("c1")).thenReturn(Optional.of(view("c1", 7L)));

        assertThat(guard.requireReadable("c1", 7L).id()).isEqualTo("c1");
    }

    @Test
    void otherAccountAndAnonymousGetNotFoundForOwnedConversation() {
        when(store.getConversation("c1")).thenReturn(Optional.of(view("c1", 7L)));

        assertThatThrownBy(() -> guard.requireReadable("c1", 8L))
                .isInstanceOf(ConversationNotFoundException.class);
        assertThatThrownBy(() -> guard.requireReadable("c1", null))
                .isInstanceOf(ConversationNotFoundException.class);
    }

    @Test
    void unknownConversationIsNotFound() {
        when(store.getConversation("ghost")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> guard.requireReadable("ghost", null))
                .isInstanceOf(ConversationNotFoundException.class);
    }

    private static ConversationStore.ConversationView view(String id, Long owner) {
        return new ConversationStore.ConversationView(id, null, false, owner, 0, 0, 0,
                Instant.EPOCH, Instant.EPOCH);
    }
}
