package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 宽查询放行指纹注册表单测（AKN-024 / AKN-027）
 *
 * 指纹口径只按 module + book：同书同模块内 filters/orFilters 的其他条件、分页排序和
 * allowBroadQuery 都不参与；书集合排序去重，避免输入顺序影响匹配。状态按会话隔离，
 * 重启/删除会话后自然失效（不持久化）。
 *
 * 确认边界：已确认指纹与各指纹的待确认建议分开保存，都连同产生它们的 requestId /
 * 请求序号。同一请求不能确认自己刚记录的建议；regenerate 不具备确认资格，即使
 * requestId 不同也不能把待确认建议变成放行，只能沿用已确认边界。同轮内不同 module/book
 * 的多次试探不会互相覆盖（AKN-027）。
 *
 * 确认资格只来自工具层真实登记的指纹：模型按 PromptBuilder 契约在首次宽查询时以
 * allowBroadQuery=false 调用 gated 工具，工具层记录 module+book；仅回答文本里的建议、
 * 或间隔的普通轮次都不会产生任何确认资格（M39 评审 p1：不接受纯建议文本出口）。
 *
 * 并发边界：{@link BroadQueryAllowanceRegistry#authorize} 在会话 key 的 compute 内完成
 * 「校验当前状态 + 写入确认/建议」的完整状态转换。请求序号小于会话已处理序号的旧请求
 * 不得确认或恢复旧指纹，也不能覆盖新状态。
 */
class BroadQueryAllowanceRegistryTest {

    private final BroadQueryAllowanceRegistry registry = new BroadQueryAllowanceRegistry();

    @Test
    void fingerprintContainsModuleAndSortedDistinctBooks() {
        BroadQueryAllowanceRegistry.Fingerprint fingerprint = BroadQueryAllowanceRegistry.Fingerprint.of(
                "feat", Map.of("book", " CRB "), Map.of("book", List.of("APG", "CRB", "APG")));

        assertThat(fingerprint.module()).isEqualTo("feat");
        assertThat(fingerprint.books()).containsExactly("APG", "CRB");
    }

    @Test
    void authorizeOnlySameModuleAndBookSetFromLaterUserTurn() {
        BroadQueryAllowanceRegistry.Fingerprint crb = fingerprint("feat", "CRB");
        assertThat(registry.authorize("cid", crb, "req-1", false, true, 1)).isFalse();
        assertThat(registry.authorize("cid", BroadQueryAllowanceRegistry.Fingerprint.of(
                "feat", null, Map.of("book", List.of("CRB"))), "req-2", true, true, 2)).isTrue();

        assertThat(registry.authorize("cid-apg", crb, "req-1", false, true, 1)).isFalse();
        assertThat(registry.authorize("cid-apg", fingerprint("feat", "APG"), "req-2", true, true, 2)).isFalse();

        assertThat(registry.authorize("cid-module", crb, "req-1", false, true, 1)).isFalse();
        assertThat(registry.authorize("cid-module", fingerprint("equipment", "CRB"),
                "req-2", true, true, 2)).isFalse();

        assertThat(registry.authorize("other-cid", crb, "req-2", true, true, 2)).isFalse();
    }

    /** AKN-024 同轮自我放行：同一 requestId 不能确认自己刚记录的建议 */
    @Test
    void sameRequestCannotConfirmFingerprintItJustRecorded() {
        BroadQueryAllowanceRegistry.Fingerprint fingerprint = fingerprint("feat", "CRB");
        assertThat(registry.authorize("cid", fingerprint, "req-1", false, true, 1)).isFalse();

        assertThat(registry.authorize("cid", fingerprint, "req-1", true, true, 1)).isFalse();
        assertThat(registry.authorize("cid", fingerprint, "req-2", true, true, 2)).isTrue();
    }

    /** AKN-024 regenerate：没有新用户轮次，不得凭新 requestId 确认待确认建议 */
    @Test
    void regenerateCannotConfirmPendingSuggestion() {
        BroadQueryAllowanceRegistry.Fingerprint fingerprint = fingerprint("feat", "CRB");
        assertThat(registry.authorize("cid", fingerprint, "req-1", false, true, 1)).isFalse();

        assertThat(registry.authorize("cid", fingerprint, "req-2", true, false, 2)).isFalse();
        assertThat(registry.authorize("cid", fingerprint, "req-3", true, false, 3)).isFalse();
    }

    /** AKN-024 regenerate：已由真实用户轮次确认的边界可以沿用，不重复拦截 */
    @Test
    void regenerateContinuesPreviouslyConfirmedFingerprint() {
        BroadQueryAllowanceRegistry.Fingerprint fingerprint = fingerprint("feat", "CRB");
        assertThat(registry.authorize("cid", fingerprint, "req-1", false, true, 1)).isFalse();
        assertThat(registry.authorize("cid", fingerprint, "req-2", true, true, 2)).isTrue();

        assertThat(registry.authorize("cid", fingerprint, "req-3", true, false, 3)).isTrue();
        assertThat(registry.authorize("cid", fingerprint, "req-4", true, true, 4)).isTrue();
    }

    /** regenerate 的失败重试也不能把待确认建议升级为已确认 */
    @Test
    void blockedRegenerateRetryStaysPending() {
        BroadQueryAllowanceRegistry.Fingerprint fingerprint = fingerprint("feat", "CRB");
        assertThat(registry.authorize("cid", fingerprint, "req-1", false, true, 1)).isFalse();
        assertThat(registry.authorize("cid", fingerprint, "req-2", true, false, 2)).isFalse();
        assertThat(registry.authorize("cid", fingerprint, "req-3", true, false, 3)).isFalse();
    }

    /** 后续用户轮次也必须指纹一致，不能凭「新请求」字样放行换模块/换书 */
    @Test
    void laterUserTurnStillRequiresMatchingFingerprint() {
        assertThat(registry.authorize("cid", fingerprint("feat", "CRB"),
                "req-1", false, true, 1)).isFalse();

        assertThat(registry.authorize("cid", fingerprint("feat", "APG"),
                "req-2", true, true, 2)).isFalse();
    }

    /** 缺失 requestId 无法证明是后续用户轮次，一律不放行（保守拒绝） */
    @Test
    void missingRequestIdNeverMatches() {
        BroadQueryAllowanceRegistry.Fingerprint fingerprint = fingerprint("feat", "CRB");
        assertThat(registry.authorize("cid", fingerprint, "req-1", false, true, 1)).isFalse();

        assertThat(registry.authorize("cid", fingerprint, null, true, true, 2)).isFalse();
        assertThat(registry.authorize("cid", fingerprint, " ", true, true, 3)).isFalse();
        assertThat(registry.authorize("cid", fingerprint, "req-4", true, false, 4)).isFalse();
    }

    @Test
    void eachSuggestedFingerprintCanBeConfirmedByLaterTurn() {
        assertThat(registry.authorize("cid", fingerprint("feat", "CRB"),
                "req-1", false, true, 1)).isFalse();
        assertThat(registry.authorize("cid", fingerprint("equipment", "APG"),
                "req-2", false, true, 2)).isFalse();

        assertThat(registry.find("cid")).contains(fingerprint("equipment", "APG"));
        // AKN-027：同轮/跨轮的多个试探各留各的建议，旧建议不会被后来者覆盖掉
        assertThat(registry.authorize("cid", fingerprint("feat", "CRB"),
                "req-3", true, true, 3)).isTrue();
        assertThat(registry.authorize("cid", fingerprint("equipment", "APG"),
                "req-4", true, true, 4)).isTrue();
    }

    /**
     * AKN-027 评审 p1 回归：上一轮只有文本建议（没有任何 gated 工具调用）时，注册表没有
     * 任何确认资格；下一轮真实用户的 allow=true 必须被驳回并登记建议，而不能直接执行。
     */
    @Test
    void adviceTextAloneGrantsNoConfirmation() {
        BroadQueryAllowanceRegistry.Fingerprint ruleCrb = fingerprint("rule", "CRB");
        assertThat(registry.authorize("cid", ruleCrb, "req-2", true, true, 2)).isFalse();
        // 被驳回时登记了 rule+CRB 的建议后，真正的下一轮确认才放行
        assertThat(registry.authorize("cid", ruleCrb, "req-3", true, true, 3)).isTrue();
    }

    /** 纯建议后直接换模块/换书：目标指纹从未登记，必须驳回并重新给建议 */
    @Test
    void adviceTextDoesNotPermitChangedModuleOrBook() {
        assertThat(registry.authorize("cid", fingerprint("rule", "CRB"),
                "req-1", false, true, 1)).isFalse();

        // 下一真实用户轮次直接换模块 / 换书：无该指纹建议，不得放行
        assertThat(registry.authorize("cid", fingerprint("feat", "CRB"),
                "req-2", true, true, 2)).isFalse();
        assertThat(registry.authorize("cid", fingerprint("rule", "APG"),
                "req-3", true, true, 3)).isFalse();
        // 原建议范围仍可确认
        assertThat(registry.authorize("cid", fingerprint("rule", "CRB"),
                "req-4", true, true, 4)).isTrue();
    }

    /** 间隔普通轮次（无任何门禁判定）不会扩大确认资格，旧的待确认建议也不跨范围生效 */
    @Test
    void interveningNormalTurnsDoNotGrantConfirmation() {
        assertThat(registry.authorize("cid", fingerprint("equipment", "CRB"),
                "req-1", false, true, 1)).isFalse();

        // req-2/req-3 是普通问答轮：没有 gated 调用，注册表看不到任何判定
        assertThat(registry.authorize("cid", fingerprint("feat", "APG"),
                "req-4", true, true, 4)).isFalse();
        assertThat(registry.authorize("cid", fingerprint("equipment", "APG"),
                "req-5", true, true, 5)).isFalse();
        // 只有原建议指纹能在后续轮次被确认
        assertThat(registry.authorize("cid", fingerprint("equipment", "CRB"),
                "req-6", true, true, 6)).isTrue();
    }

    /**
     * AKN-027 主因 2（真实 gate4_diag 序列）：确认轮内先放行 rule+CRB，再探测 all+CRB，
     * 不得清掉 rule 的已确认状态；后续 rule 同条件翻页必须仍然放行。
     */
    @Test
    void sameTurnVariantProbeDoesNotEraseConfirmedScope() {
        BroadQueryAllowanceRegistry.Fingerprint ruleCrb = fingerprint("rule", "CRB");
        BroadQueryAllowanceRegistry.Fingerprint allCrb = fingerprint("all", "CRB");

        assertThat(registry.authorize("cid", ruleCrb, "req-1", false, true, 1)).isFalse();
        assertThat(registry.authorize("cid", ruleCrb, "req-2", true, true, 2)).isTrue();
        assertThat(registry.authorize("cid", allCrb, "req-2", true, true, 2)).isFalse();
        assertThat(registry.authorize("cid", ruleCrb, "req-2", true, true, 2)).isTrue();

        // 下一轮用户确认 all+CRB：此前的探测建议仍然有效
        assertThat(registry.authorize("cid", allCrb, "req-3", true, true, 3)).isTrue();
    }

    /** 同轮先记录 rule 建议、再探测 all：后者的驳回不得覆盖前者的待确认建议 */
    @Test
    void sameTurnVariantProbeDoesNotReplaceSuggestion() {
        BroadQueryAllowanceRegistry.Fingerprint ruleCrb = fingerprint("rule", "CRB");
        assertThat(registry.authorize("cid", ruleCrb, "req-1", false, true, 1)).isFalse();
        assertThat(registry.authorize("cid", fingerprint("all", "CRB"),
                "req-1", false, true, 1)).isFalse();

        assertThat(registry.authorize("cid", ruleCrb, "req-2", true, true, 2)).isTrue();
    }

    @Test
    void newSuggestionKeepsPreviouslyConfirmedFingerprint() {
        BroadQueryAllowanceRegistry.Fingerprint confirmed = fingerprint("feat", "CRB");
        assertThat(registry.authorize("cid", confirmed, "req-1", false, true, 1)).isFalse();
        assertThat(registry.authorize("cid", confirmed, "req-2", true, true, 2)).isTrue();

        BroadQueryAllowanceRegistry.Fingerprint next = fingerprint("equipment", "CRB");
        assertThat(registry.authorize("cid", next, "req-3", false, true, 3)).isFalse();
        // AKN-027：新建议不再清掉已确认边界——否则换模块探测会打断已确认范围的分页，
        // 且真实模型确认轮内的换模块试探会让原建议永远无法被下一轮确认。
        assertThat(registry.authorize("cid", confirmed, "req-4", true, false, 4)).isTrue();
        // 新指纹仍必须由后续用户轮次确认，换模块不能沿用旧放行
        assertThat(registry.authorize("cid", next, "req-5", true, false, 5)).isFalse();
        assertThat(registry.authorize("cid", next, "req-6", true, true, 6)).isTrue();
    }

    /**
     * 可控交错：旧请求（序号 2）在新建议 B（序号 3）写入后才完成判定。
     * 旧判定不得确认/恢复 A，也不得覆盖 B；B 仍可被后续用户轮次确认。
     */
    @Test
    void staleRequestCannotConfirmOrRestoreFingerprintAfterNewSuggestion() {
        BroadQueryAllowanceRegistry.Fingerprint a = fingerprint("feat", "CRB");
        BroadQueryAllowanceRegistry.Fingerprint b = fingerprint("equipment", "APG");

        assertThat(registry.authorize("cid", a, "req-1", false, true, 1)).isFalse();   // A 待确认
        assertThat(registry.authorize("cid", b, "req-3", false, true, 3)).isFalse();   // 新建议 B

        // 旧 req-2 的过期判定此刻才到达：既不能确认 A，也不能把 A 写回
        assertThat(registry.authorize("cid", a, "req-2", true, true, 2)).isFalse();
        assertThat(registry.find("cid")).contains(b);
        // B 仍保持待确认，可被后续用户轮次确认（证明旧请求未破坏新状态）
        assertThat(registry.authorize("cid", b, "req-5", true, true, 5)).isTrue();
    }

    /** 并发下序号更大的新建议始终胜出，旧请求不能留下已确认的旧指纹 */
    @Test
    void concurrentStaleConfirmationCannotOverrideNewerSuggestion() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            for (int i = 0; i < 20; i++) {
                String cid = "cid-concurrent-" + i;
                String suffix = String.valueOf(i);
                BroadQueryAllowanceRegistry.Fingerprint a = fingerprint("feat", "CRB");
                BroadQueryAllowanceRegistry.Fingerprint b = fingerprint("equipment", "APG");
                assertThat(registry.authorize(cid, a, "req-1-" + suffix, false, true, 1)).isFalse();

                CountDownLatch start = new CountDownLatch(1);
                Future<Boolean> staleConfirm = pool.submit(() -> {
                    start.await();
                    return registry.authorize(cid, a, "req-2-" + suffix, true, true, 2);
                });
                Future<Boolean> newSuggestion = pool.submit(() -> {
                    start.await();
                    return registry.authorize(cid, b, "req-3-" + suffix, false, true, 3);
                });
                start.countDown();

                // 两种调度都必须收敛到 B：旧请求不能留下已确认的 A
                staleConfirm.get(5, TimeUnit.SECONDS);
                assertThat(newSuggestion.get(5, TimeUnit.SECONDS)).isFalse();
                assertThat(registry.find(cid)).contains(b);
                // 序号更大的新建议 B 始终胜出，且仍可被后续用户轮次确认
                assertThat(registry.authorize(cid, b, "req-9-" + suffix, true, true, 9)).isTrue();
            }
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void blankBookValuesAreIgnored() {
        BroadQueryAllowanceRegistry.Fingerprint fingerprint = BroadQueryAllowanceRegistry.Fingerprint.of(
                "feat", Map.of("book", " "), Map.of("book", List.of("", "CRB")));

        assertThat(fingerprint.books()).containsExactly("CRB");
    }

    private static BroadQueryAllowanceRegistry.Fingerprint fingerprint(String module, String book) {
        return BroadQueryAllowanceRegistry.Fingerprint.of(module, Map.of("book", book), null);
    }
}
