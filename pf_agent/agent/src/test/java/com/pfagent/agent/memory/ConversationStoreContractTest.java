package com.pfagent.agent.memory;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 统一 ConversationStore 契约测试（F-020 实施 Spec §5/§11.2）
 *
 * JDBC 与内存两种实现跑同一组断言：会话 CRUD/lookup/claim/history/append/replace、
 * 20 轮裁剪、引用快照、generation_attempts 与删除后不重建父行。
 */
abstract class ConversationStoreContractTest {

    protected ConversationStore store;

    private static Instant at(int seconds) {
        return Instant.parse("2026-11-11T00:00:00Z").plusSeconds(seconds);
    }

    @Test
    void createAndGetConversationStartsEmptyAndInvisible() {
        store.createConversation("c1", null, at(0));

        ConversationStore.ConversationView view = store.getConversation("c1").orElseThrow();
        assertThat(view.messageRounds()).isZero();
        assertThat(view.totalRounds()).isZero();
        assertThat(view.generationAttempts()).isZero();
        assertThat(view.pinned()).isFalse();
        assertThat(view.title()).isNull();
        assertThat(store.listOwnedConversations(null, null, 30).items()).isEmpty();
    }

    @Test
    void appendRoundStoresPairSnapshotAndDefaultTitle() {
        store.createConversation("c1", null, at(0));

        ConversationStore.AppendResult result = store.appendRound(
                "c1", "火球术的射程是多少？请给出规则书原文与目录路径以便核对。",
                "400 英尺 [#1]", "[{\"book\":\"CRB\",\"tocPath\":\"法术\",\"content\":\"正文\"}]",
                true, at(1));

        assertThat(result.status()).isEqualTo(ConversationStore.AppendStatus.OK);
        assertThat(result.assistant().seq()).isEqualTo(2);
        assertThat(result.assistant().sourcesJson()).contains("\"book\":\"CRB\"");
        assertThat(result.assistant().gapReported()).isTrue();

        List<ConversationStore.StoredMessage> history = store.history("c1", 100);
        assertThat(history).hasSize(2);
        assertThat(history.get(0).role()).isEqualTo("user");
        assertThat(history.get(1).role()).isEqualTo("assistant");
        assertThat(history.get(1).content()).isEqualTo("400 英尺 [#1]");

        ConversationStore.ConversationView view = store.getConversation("c1").orElseThrow();
        assertThat(view.messageRounds()).isEqualTo(1);
        assertThat(view.totalRounds()).isEqualTo(1);
        assertThat(view.title()).hasSizeLessThanOrEqualTo(30);
        assertThat(view.title()).startsWith("火球术的射程是多少");
    }

    @Test
    void appendToMissingParentReturnsMissingAndDoesNotRecreate() {
        ConversationStore.AppendResult result = store.appendRound(
                "ghost", "q", "a", null, false, at(0));

        assertThat(result.status()).isEqualTo(ConversationStore.AppendStatus.PARENT_MISSING);
        assertThat(store.getConversation("ghost")).isEmpty();
        assertThat(store.history("ghost", 10)).isEmpty();
    }

    @Test
    void trimmingKeepsOnlyRecentTwentyRoundsIncludingSnapshots() {
        store.createConversation("c1", null, at(0));
        for (int i = 1; i <= 25; i++) {
            store.appendRound("c1", "q" + i, "a" + i, "[]", false, at(i));
        }

        List<ConversationStore.StoredMessage> history = store.history("c1", 100);
        assertThat(history).hasSize(40);
        assertThat(history.get(0).content()).isEqualTo("q6");
        assertThat(history.get(39).content()).isEqualTo("a25");

        ConversationStore.ConversationView view = store.getConversation("c1").orElseThrow();
        assertThat(view.messageRounds()).isEqualTo(20);
        assertThat(view.totalRounds()).isEqualTo(25);
    }

    @Test
    void replaceLastAssistantUpdatesFieldsWithoutChangingRounds() {
        store.createConversation("c1", null, at(0));
        store.appendRound("c1", "q1", "old", "[\"old\"]", false, at(1));
        int expectedSeq = store.lastRound("c1").orElseThrow().assistant().seq();
        long oldId = store.lastRound("c1").orElseThrow().assistant().id();

        ConversationStore.ReplaceResult replaced = store.replaceLastAssistant(
                "c1", expectedSeq, "new [#1]", "[{\"book\":\"CRB\"}]", true, at(2));

        assertThat(replaced.status()).isEqualTo(ConversationStore.ReplaceStatus.OK);
        assertThat(replaced.assistant().id()).isEqualTo(oldId);
        assertThat(replaced.assistant().seq()).isEqualTo(expectedSeq);
        assertThat(replaced.assistant().content()).isEqualTo("new [#1]");
        assertThat(replaced.assistant().gapReported()).isTrue();
        assertThat(store.history("c1", 10)).hasSize(2);
        assertThat(store.getConversation("c1").orElseThrow().totalRounds()).isEqualTo(1);
    }

    @Test
    void replaceWithStaleSeqConflictsAndKeepsContent() {
        store.createConversation("c1", null, at(0));
        store.appendRound("c1", "q1", "a1", "[]", false, at(1));
        int staleSeq = store.lastRound("c1").orElseThrow().assistant().seq();
        store.appendRound("c1", "q2", "a2", "[]", false, at(2));

        ConversationStore.ReplaceResult replaced = store.replaceLastAssistant(
                "c1", staleSeq, "overwrite", "[]", false, at(3));

        assertThat(replaced.status()).isEqualTo(ConversationStore.ReplaceStatus.CONFLICT);
        assertThat(store.history("c1", 10)).extracting(ConversationStore.StoredMessage::content)
                .containsExactly("q1", "a1", "q2", "a2");
    }

    @Test
    void replaceAfterDeleteReturnsParentMissing() {
        store.createConversation("c1", null, at(0));
        store.appendRound("c1", "q", "a", "[]", false, at(1));
        int seq = store.lastRound("c1").orElseThrow().assistant().seq();
        store.deleteConversation("c1");

        ConversationStore.ReplaceResult replaced = store.replaceLastAssistant(
                "c1", seq, "late", "[]", false, at(2));

        assertThat(replaced.status()).isEqualTo(ConversationStore.ReplaceStatus.PARENT_MISSING);
        assertThat(store.getConversation("c1")).isEmpty();
    }

    @Test
    void generationAttemptsAccumulateIndependentlyOfRounds() {
        store.createConversation("c1", null, at(0));
        store.appendRound("c1", "q", "a", "[]", false, at(1));

        assertThat(store.incrementGenerationAttempts("c1")).isEqualTo(1);
        assertThat(store.incrementGenerationAttempts("c1")).isEqualTo(2);
        assertThat(store.generationAttempts("c1")).isEqualTo(2);
        assertThat(store.getConversation("c1").orElseThrow().totalRounds()).isEqualTo(1);
        assertThat(store.incrementGenerationAttempts("ghost")).isZero();
    }

    @Test
    void claimOnlyAnonymousConversationsAndIsIdempotent() {
        store.createConversation("c1", null, at(0));

        assertThat(store.claimConversation("c1", 7L)).isEqualTo(ConversationStore.ClaimStatus.CLAIMED);
        assertThat(store.claimConversation("c1", 7L)).isEqualTo(ConversationStore.ClaimStatus.ALREADY_OWNER);
        assertThat(store.claimConversation("c1", 8L)).isEqualTo(ConversationStore.ClaimStatus.OWNED_BY_OTHER);
        assertThat(store.claimConversation("ghost", 7L)).isEqualTo(ConversationStore.ClaimStatus.NOT_FOUND);
        assertThat(store.getConversation("c1").orElseThrow().ownerUserId()).isEqualTo(7L);
    }

    @Test
    void lookupReturnsOnlyAnonymousVisibleConversationsInRequestOrder() {
        store.createConversation("c1", null, at(0));
        store.appendRound("c1", "q1", "a1", "[]", false, at(1));
        store.createConversation("c2", null, at(0));
        store.appendRound("c2", "q2", "a2", "[]", false, at(2));
        store.claimConversation("c2", 7L);
        store.createConversation("empty", null, at(3));

        List<ConversationStore.ConversationView> found =
                store.lookupConversations(List.of("c2", "c1", "empty", "ghost"));

        assertThat(found).extracting(ConversationStore.ConversationView::id).containsExactly("c1");
    }

    @Test
    void ownedListIsPinnedFirstThenRecentWithPagination() {
        for (int i = 1; i <= 4; i++) {
            store.createConversation("c" + i, 7L, at(i));
            store.appendRound("c" + i, "q" + i, "a" + i, "[]", false, at(10 + i));
        }
        store.createConversation("empty", 7L, at(20));
        store.createConversation("other", 8L, at(20));
        store.appendRound("other", "q", "a", "[]", false, at(21));
        store.setPinned("c2", true);

        ConversationStore.ConversationPage first = store.listOwnedConversations(7L, null, 2);
        assertThat(first.items()).extracting(ConversationStore.ConversationView::id)
                .containsExactly("c2", "c4");
        assertThat(first.nextCursor()).isNotNull();

        ConversationStore.ConversationPage second =
                store.listOwnedConversations(7L, first.nextCursor(), 2);
        assertThat(second.items()).extracting(ConversationStore.ConversationView::id)
                .containsExactly("c3", "c1");
        assertThat(second.nextCursor()).isNull();
    }

    @Test
    void renamePinAndDeleteConversation() {
        store.createConversation("c1", null, at(0));
        store.appendRound("c1", "q", "a", "[]", false, at(1));

        assertThat(store.renameConversation("c1", "我的会话")).isTrue();
        assertThat(store.setPinned("c1", true)).isTrue();
        ConversationStore.ConversationView view = store.getConversation("c1").orElseThrow();
        assertThat(view.title()).isEqualTo("我的会话");
        assertThat(view.pinned()).isTrue();

        assertThat(store.deleteConversation("c1")).isTrue();
        assertThat(store.getConversation("c1")).isEmpty();
        assertThat(store.history("c1", 10)).isEmpty();
        assertThat(store.lastRound("c1")).isEmpty();
        assertThat(store.deleteConversation("c1")).isFalse();
    }

    @Test
    void lastRoundReturnsLastQuestionAndAssistant() {
        store.createConversation("c1", null, at(0));
        store.appendRound("c1", "q1", "a1", "[]", false, at(1));
        store.appendRound("c1", "q2", "a2", "[]", false, at(2));

        ConversationStore.LastRound last = store.lastRound("c1").orElseThrow();
        assertThat(last.question()).isEqualTo("q2");
        assertThat(last.assistant().content()).isEqualTo("a2");
    }

    @Test
    void historyLimitReturnsMostRecentMessagesInOrder() {
        store.createConversation("c1", null, at(0));
        for (int i = 1; i <= 3; i++) {
            store.appendRound("c1", "q" + i, "a" + i, "[]", false, at(i));
        }

        List<ConversationStore.StoredMessage> recent = store.history("c1", 2);

        assertThat(recent).extracting(ConversationStore.StoredMessage::content)
                .containsExactly("q3", "a3");
        assertThat(store.history("c1", 0)).isEmpty();
        assertThat(store.history("ghost", 10)).isEmpty();
    }

    @Test
    void sourcesNullForLegacyStyleMessages() {
        store.createConversation("c1", null, at(0));
        ConversationStore.AppendResult result =
                store.appendRound("c1", "q", "a", null, false, at(1));

        assertThat(result.assistant().sourcesJson()).isNull();
        Optional<ConversationStore.StoredMessage> assistant = store.history("c1", 10).stream()
                .filter(m -> "assistant".equals(m.role())).findFirst();
        assertThat(assistant).isPresent();
        assertThat(assistant.orElseThrow().sourcesJson()).isNull();
    }
}
