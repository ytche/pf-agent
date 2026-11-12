package com.pfagent.agent.rag;

import com.pfagent.agent.telemetry.QueryGateEventService.Reason;

import java.util.List;
import java.util.Map;

/**
 * 宽查询工具护栏判定与建议文案（F-026 设计 §6、§7）
 *
 * 只判定设计确认的「最低宽条件形态」：
 *  - {@link Reason#NO_CONDITIONS}：无有效业务条件（仅分页/排序参数也按此形态）；
 *  - {@link Reason#BOOK_ONLY}：仅来源书条件（单书、多书 OR 或两者组合）。
 *
 * 书与任一其他业务条件（keyword/主题/类别/职业/环级等）组合后不属于工具硬护栏形态，
 * limit/offset/sortBy 只是展示参数，不计入业务条件。allowBroadQuery 也不计入
 * {@code hasAnyCondition()} 且不参与本判定——它只是用户确认后的放行声明。
 *
 * 判定是纯函数，参数校验（非法模块/未知字段/空过滤值/非法分页排序）由工具层先行
 * 返回，校验失败不进入本判定，因此不会产生 BLOCKED/ALLOWED 事件。
 */
public final class BroadQueryGuard {

    /** listEntries 的 keyword 为条目名子串，属于有效业务条件 */
    private static final String BOOK_FIELD = "book";

    private BroadQueryGuard() {
    }

    /**
     * searchByMetadata 的宽条件形态。
     *
     * @return {@link Reason#NO_CONDITIONS} / {@link Reason#BOOK_ONLY}；非宽条件返回 null
     */
    public static Reason metadataReason(MetadataSearchQuery query) {
        if (query == null || !query.hasAnyCondition()) {
            return Reason.NO_CONDITIONS;
        }
        boolean onlyBookKeys = keysAreOnlyBook(query.getFilters())
                && keysAreOnlyBook(query.getOrFilters());
        boolean hasBookKey = hasKeys(query.getFilters()) || hasKeys(query.getOrFilters());
        boolean hasNonBookCondition = notEmpty(query.getGte()) || notEmpty(query.getLte());
        if (onlyBookKeys && hasBookKey && !hasNonBookCondition) {
            return Reason.BOOK_ONLY;
        }
        return null;
    }

    /**
     * listEntries 的宽条件形态。
     *
     * 非空白 keyword（含 keyword-only）是有效业务条件，不按关键词长度猜测语义宽度；
     * 空白 keyword 已在工具层按无效条件处理。
     *
     * @return {@link Reason#NO_CONDITIONS} / {@link Reason#BOOK_ONLY}；非宽条件返回 null
     */
    public static Reason listEntriesReason(ListEntriesQuery query) {
        if (query == null || !query.hasAnyCondition()) {
            return Reason.NO_CONDITIONS;
        }
        if (query.keyword() != null && !query.keyword().isBlank()) {
            return null;
        }
        boolean onlyBookKeys = keysAreOnlyBook(query.filters())
                && keysAreOnlyBook(query.orFilters());
        boolean hasBookKey = hasKeys(query.filters()) || hasKeys(query.orFilters());
        return onlyBookKeys && hasBookKey ? Reason.BOOK_ONLY : null;
    }

    /**
     * 未放行宽条件的工具结果：明确「未执行条目检索」、触发原因、可补充的业务条件、
     * 有效收窄示例、概览入口与「仍按原范围查询」的放行方式。
     *
     * 文案禁止被理解成「查询无结果」或「数据缺失」——护栏结果不触发 reportDataGap。
     *
     * @param toolName        工具名（searchByMetadata / listEntries）
     * @param module          当前模块（含 all）
     * @param reason          判定原因
     * @param availableFields 该模块可用业务条件字段（可为空列表）
     */
    public static String blockedMessage(String toolName, String module, Reason reason,
            List<String> availableFields) {
        StringBuilder sb = new StringBuilder();
        sb.append("（宽查询护栏：本次未执行条目检索）\n");
        sb.append("触发原因: ").append(reason.value()).append(reason == Reason.NO_CONDITIONS
                ? "（没有有效业务收窄条件，仅分页/排序参数也算无业务条件）"
                : "（只有来源书条件）").append('\n');
        if (reason == Reason.NO_CONDITIONS) {
            sb.append("无业务条件会扫描整库，结果数量可能远超单库检索上限 500 条。");
        } else {
            sb.append("仅按来源书检索会覆盖该书全部条目，范围仍可能很大。");
        }
        sb.append("请先向用户说明范围可能很大，并给出 2~4 个与原问题相关、可直接照抄的收窄示例；例如：\n");
        for (String example : examples(toolName, module)) {
            sb.append("  - ").append(example).append('\n');
        }
        if (hasOverviewOption(toolName, module)) {
            sb.append("也可先查看该模块的数量概览，不要用检索上限内的条数冒充真实总数。\n");
        }
        sb.append("若用户已明确选择「仍按原范围查询」，携带 query.allowBroadQuery=true 重试；")
                .append("同一业务条件的后续每页都要携带该字段，业务条件改变后需重新判断。\n");
        sb.append("该结果不是「查询无结果」，也不是「数据缺失」，不要据此调用 reportDataGap。");
        if (availableFields != null && !availableFields.isEmpty()) {
            sb.append("\n可用业务条件字段: ").append(availableFields);
        }
        return sb.toString();
    }

    /** 该工具/模块是否已有轻量数量概览入口（listEntries 的 feat/race/equipment） */
    private static boolean hasOverviewOption(String toolName, String module) {
        if ("listEntries".equals(toolName)) {
            return true;
        }
        return "all".equals(module) || List.of("feat", "race", "equipment").contains(module);
    }

    /** 可直接照抄的收窄示例（保持与原问题相关的有效业务收窄，而非仅换一个宽词） */
    private static List<String> examples(String toolName, String module) {
        if ("listEntries".equals(toolName)) {
            return switch (module == null ? "" : module) {
                case "race" -> List.of(
                        "query={filters:{raceGroup:\"元素\"}}（种族分组）",
                        "query={filters:{book:\"CRB\", size:\"中型\"}}（书+体型）",
                        "query={filters:{book:\"CRB\", bioType:\"精类\"}}（书+生物类型）",
                        "query={keyword:\"精灵\"}（名称子串）");
                case "equipment" -> List.of(
                        "query={filters:{book:\"CRB\", componentType:\"weapon\"}}（书+装备类型）",
                        "query={filters:{slot:\"肩部\"}}（装备部位）",
                        "query={keyword:\"治疗药水\"}（名称子串）");
                default -> List.of(
                        "query={filters:{featType:\"战斗\"}}（专长类别）",
                        "query={filters:{book:\"CRB\", featType:\"团队\"}}（书+类别）",
                        "query={filters:{book:\"CRB\", hasPrerequisites:\"false\"}}（书+无前置）",
                        "query={keyword:\"闪避\"}（名称子串）");
            };
        }
        return switch (module == null ? "" : module) {
            case "spell" -> List.of(
                    "module=\"spell\", query={filters:{className:\"女巫\"}, gte:{level:\"3\"}}（职业+环级）",
                    "module=\"spell\", query={filters:{school:\"咒法系\"}}（学派）",
                    "module=\"spell\", query={filters:{book:\"CRB\", school:\"防护系\"}}（书+学派）",
                    "module=\"spell\", query={filters:{title:\"火球术\"}}（具体条目）");
            case "class" -> List.of(
                    "module=\"class\", query={filters:{className:\"战士\"}}（职业）",
                    "module=\"class\", query={filters:{book:\"CRB\", className:\"法师\"}}（书+职业）",
                    "module=\"class\", query={filters:{title:\"奥术联结\"}}（具体条目）");
            case "feat", "race", "equipment" -> List.of(
                    "改用 listEntries(module=\"" + module + "\", query={filters:{book:\"CRB\", 类别字段:\"具体值\"}}) 枚举清单",
                    "module=\"" + module + "\", query={filters:{title:\"具体条目名\"}}（具体条目）",
                    "module=\"" + module + "\", query={orFilters:{book:[\"CRB\",\"APG\"]}, filters:{title:\"具体条目名\"}}");
            case "all" -> List.of(
                    "先指定具体 module（如 module=\"rule\"）再按 title/book 收窄",
                    "module=\"rule\", query={filters:{book:\"CRB\", title:\"具体条目名\"}}",
                    "module=\"spell\", query={filters:{className:\"女巫\"}, gte:{level:\"3\"}}");
            default -> List.of(
                    "query={filters:{title:\"具体条目名\"}}（具体条目）",
                    "query={filters:{book:\"CRB\", title:\"具体条目名\"}}（书+条目）",
                    "query={orFilters:{book:[\"CRB\",\"APG\"]}, filters:{title:\"具体条目名\"}}（多书+条目）");
        };
    }

    /** 映射键是否只含来源书字段（空映射返回 true，由 hasKeys 另行确认确有条件） */
    private static boolean keysAreOnlyBook(Map<?, ?> conditions) {
        if (conditions == null || conditions.isEmpty()) {
            return true;
        }
        return conditions.keySet().stream().allMatch(BOOK_FIELD::equals);
    }

    private static boolean hasKeys(Map<?, ?> conditions) {
        return conditions != null && !conditions.isEmpty();
    }

    private static boolean notEmpty(Map<?, ?> map) {
        return map != null && !map.isEmpty();
    }
}
