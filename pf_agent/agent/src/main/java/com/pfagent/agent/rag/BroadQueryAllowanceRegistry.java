package com.pfagent.agent.rag;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 会话级宽查询放行指纹（AKN-024 / AKN-027）
 *
 * F-026 的 allowBroadQuery 由模型自行声明，服务端不保存放行状态，模型可能在同一会话
 * 换模块/换书后继续沿用放行。本类按 conversationId 在内存保存宽查询指纹及其确认状态，
 * 只有通过确认边界校验的放行声明才执行检索；否则退回收窄建议并更新指纹。
 *
 * 指纹口径只按 module + book：limit/offset/sortBy/sortOrder/allowBroadQuery 以及其他
 * 过滤条件都不参与（同书同模块内增删其他条件不再要求确认）。书集合用去重排序后的列表，
 * 避免 filters/orFilters 的输入顺序影响匹配。
 *
 * 状态分两层（AKN-027 修复；原实现每会话只存一个 Entry，同轮用不同 module/book 试探
 * 会互相覆盖，导致待确认建议与已确认边界都绑定到模型「最后一次试探」上）：
 *  - {@link #confirmed}：已由后续真实用户轮次确认的指纹集合。已确认指纹不会被其他指纹的
 *    建议/驳回清掉，因此确认轮内外的换模块探测不会打断已确认范围的分页；
 *  - {@link #suggested}：被驳回的宽条件指纹（待确认建议），按指纹分别保存。模型在同一轮
 *    对 rule/all、不同书多次试探时，各指纹互不覆盖，下一轮用户确认命中任意一个建议即可放行。
 *
 * 确认边界（保持 M38 已验收语义）：
 *  - 同一 requestId 不能确认自己记录的建议；regenerate 不具备确认资格；
 *  - 缺失 requestId 视为无法证明是后续用户轮次，保守拒绝且不落建议；
 *  - 请求序号小于会话已处理序号的旧请求，只返回拒绝，不写回任何状态。
 *
 * 确认资格只来自「本会话中被门禁驳回过的 module+book」：模型按 PromptBuilder 契约在首次
 * 宽查询时以 allowBroadQuery=false（缺省）调用对应 gated 工具，工具层据此登记真实
 * 指纹并返回收窄建议；用户下一真实轮次的放行声明命中该指纹才可确认。仅凭回答文本给出
 * 建议不产生任何确认资格（AKN-027 评审：纯建议文本出口会让未建议的新范围被直接放行，
 * 也会跨越普通轮次残留），因此本类不再接受任何「上一轮只给了建议」的旁路标记。
 *
 * 并发一致性：所有门禁决策走 {@link #authorize}，在会话 key 的 {@code compute} 内一次性
 * 完成「读取状态 → 校验 → 确认/记录建议」；旧请求不能基于过期快照写回。
 *
 * 状态只存内存、随进程重启失效，不做持久化；每会话的指纹集合有上限，超出后按最久未用
 * 淘汰，避免异常模型行为无限增长。
 */
@Component
public class BroadQueryAllowanceRegistry {

    /** 每会话最多保留的已确认 / 待确认指纹数（module+book 组合实际很少） */
    private static final int MAX_FINGERPRINTS = 8;

    /** conversationId → 该会话的放行状态 */
    private final Map<String, ConversationState> conversations = new ConcurrentHashMap<>();

    /** 读取某会话最近一次判定涉及的指纹（无记录返回 empty；测试与诊断用） */
    public Optional<Fingerprint> find(String conversationId) {
        if (conversationId == null || conversationId.isBlank()) {
            return Optional.empty();
        }
        ConversationState state = conversations.get(conversationId);
        return state == null ? Optional.empty() : Optional.ofNullable(state.lastFingerprint);
    }

    /**
     * 原子门禁决策：按会话 key 校验放行声明并写入确认或待确认建议。
     *
     * 判定规则：
     *  - 指纹已确认 → 放行（含 regenerate 与同条件翻页）；
     *  - 该指纹有待确认建议，且当前是后续真实用户轮次（requestId 不同）→ 确认放行；
     *  - 其余声明放行 → 拒绝并记录该指纹的待确认建议（仅真实用户轮次落建议）；
     *  - 未声明放行 → 拒绝并记录建议（已确认指纹不重复记录）；
     *  - 请求序号早于会话已处理序号 → 旧请求的过期判定，不写回任何状态。
     *
     * @param declaredAllowed      模型是否声明 allowBroadQuery=true
     * @param confirmationEligible 当前请求是否为真实新用户轮次（regenerate=false）
     * @param requestSequence      请求开始时分配的全局单调序号
     * @return true=允许执行并标记已确认；false=拒绝（必要时记录待确认建议）
     */
    public boolean authorize(String conversationId, Fingerprint fingerprint, String requestId,
            boolean declaredAllowed, boolean confirmationEligible, long requestSequence) {
        if (conversationId == null || conversationId.isBlank() || fingerprint == null) {
            return false;
        }
        AtomicBoolean allowed = new AtomicBoolean(false);
        conversations.compute(conversationId, (key, existing) -> {
            ConversationState state = existing == null ? new ConversationState() : existing;
            if (requestSequence < state.lastSequence) {
                // 旧请求：不能确认、不能记录建议，也不能恢复旧指纹
                return state;
            }
            state.lastFingerprint = fingerprint;
            boolean eligibleTurn = confirmationEligible
                    && requestId != null && !requestId.isBlank();
            if (declaredAllowed) {
                Suggestion suggestion = state.suggested.get(fingerprint);
                boolean confirmed = state.confirmed.containsKey(fingerprint);
                boolean suggestionMatches = suggestion != null && eligibleTurn
                        && suggestion.requestSequence() < requestSequence
                        && !requestId.equals(suggestion.requestId());
                if (confirmed || suggestionMatches) {
                    state.confirmed.put(fingerprint, requestSequence);
                    state.suggested.remove(fingerprint);
                    state.lastSequence = requestSequence;
                    allowed.set(true);
                    return state;
                }
            }
            if (eligibleTurn && !state.confirmed.containsKey(fingerprint)) {
                state.suggested.put(fingerprint, new Suggestion(requestId, requestSequence));
            }
            state.lastSequence = requestSequence;
            return state;
        });
        return allowed.get();
    }

    /** 清除某会话指纹（会话删除/测试隔离用） */
    public void clear(String conversationId) {
        if (conversationId != null) {
            conversations.remove(conversationId);
        }
    }

    /** 会话级放行状态：已确认指纹、待确认建议、最近处理序号与「上一轮只给了建议」标记 */
    private static final class ConversationState {

        /** 指纹 → 确认时的请求序号（访问序 LRU，超出上限淘汰最久未用） */
        private final Map<Fingerprint, Long> confirmed =
                new LinkedHashMap<>(16, 0.75f, true) {
                    @Override
                    protected boolean removeEldestEntry(Map.Entry<Fingerprint, Long> eldest) {
                        return size() > MAX_FINGERPRINTS;
                    }
                };

        /** 指纹 → 待确认建议（记录建议来源请求，确认时要求 requestId 不同且序号更晚） */
        private final Map<Fingerprint, Suggestion> suggested =
                new LinkedHashMap<>(16, 0.75f, true) {
                    @Override
                    protected boolean removeEldestEntry(Map.Entry<Fingerprint, Suggestion> eldest) {
                        return size() > MAX_FINGERPRINTS;
                    }
                };

        /** 已处理的最大请求序号：更旧的请求只能被拒绝，不能写回 */
        private long lastSequence;

        /** 最近一次判定涉及的指纹（find 诊断用） */
        private Fingerprint lastFingerprint;
    }

    private record Suggestion(String requestId, long requestSequence) {
    }

    /**
     * 宽查询指纹：module + 归一化书集合。
     *
     * @param module    工具入参模块（searchByMetadata 可能是 all）
     * @param filters   AND 条件（取 book）
     * @param orFilters OR 条件（取 book 候选值）
     */
    public record Fingerprint(String module, List<String> books) {

        public Fingerprint {
            module = module == null ? "" : module;
            books = normalizeBooks(books);
        }

        /** 从两类查询参数对象的 filters/orFilters 提取书集合 */
        public static Fingerprint of(String module, Map<String, String> filters,
                Map<String, List<String>> orFilters) {
            List<String> books = new ArrayList<>();
            if (filters != null && filters.get("book") != null) {
                books.add(filters.get("book"));
            }
            if (orFilters != null && orFilters.get("book") != null) {
                books.addAll(orFilters.get("book"));
            }
            return new Fingerprint(module, books);
        }

        /** 去空白、去重、排序（书集合语义与输入顺序无关） */
        private static List<String> normalizeBooks(List<String> raw) {
            if (raw == null) {
                return List.of();
            }
            return raw.stream()
                    .filter(v -> v != null && !v.isBlank())
                    .map(String::trim)
                    .distinct()
                    .sorted()
                    .toList();
        }
    }
}
