package com.pfagent.agent.rag;

import java.util.List;
import java.util.Map;

/**
 * listEntries 的过滤/分页参数对象（B4，2026-09-23 拍板）
 *
 * 一个 @Tool 方法不摊多参数：keyword/过滤/分页/排序全部收敛为本 record，
 * 由 Jackson 反序列化驱动（Spring AI 从 record 生成工具 schema）。
 * 全字段可空；keyword/filters/orFilters 全空时工具层返回该模块统计概览。
 *
 * keyword 独立字段而非 filter：三模块通用且是子串语义（大小写不敏感、全半角容错），
 * 与 filters 的 AND 精确匹配语义不同。filters/orFilters 的键为模块可用字段名
 * （featType/raceGroup/componentType/book 等），值统一字符串（原文值精确比对）；
 * filters 组内 AND、orFilters 组内 OR。
 *
 * F-026：新增 allowBroadQuery 三态放行声明（null/false = 未放行，true = 用户明确确认后
 * 按原范围查询）；它不是业务过滤条件，不计入 {@link #hasAnyCondition()}。同一业务条件的
 * 每页都要携带，业务条件变化后需重新判断。
 */
public record ListEntriesQuery(
        /** name/name_en/aliases 子串（大小写不敏感、全半角容错），可空 */
        String keyword,
        /** AND 精确匹配：{featType:"战斗"}；可用字段随模块，字段名错误返回可用字段清单 */
        Map<String, String> filters,
        /** 组内 OR：{book:["CRB","APG"]} */
        Map<String, List<String>> orFilters,
        /** 返回条数，默认 pf.list-exports.default-limit（50），硬上限 pf.list-exports.max-limit（200） */
        Integer limit,
        /** 跳过条数，默认 0 */
        Integer offset,
        /** 排序字段："name"（默认，unicode 序）| "book"（按书再按名）| "price"（仅 equipment，按 price_gp） */
        String sortBy,
        /** 宽查询放行声明（null/false = 未放行；true = 用户明确确认后按原范围查询） */
        Boolean allowBroadQuery,
        /** 排序方向："asc"（默认）| "desc"；仅对 sortBy 生效，不计入业务条件 */
        String sortOrder) {

    /**
     * 兼容构造（F-026 之前的 6 参调用）：allowBroadQuery/sortOrder 缺省为 null（未放行/升序）。
     * 有意放行的用例必须显式传 true。
     */
    public ListEntriesQuery(String keyword, Map<String, String> filters,
            Map<String, List<String>> orFilters, Integer limit, Integer offset, String sortBy) {
        this(keyword, filters, orFilters, limit, offset, sortBy, null, null);
    }

    /** F-026 兼容构造（7 参）：sortOrder 缺省为 null（asc）；AKN-025 新调用请用 8 参构造 */
    public ListEntriesQuery(String keyword, Map<String, String> filters,
            Map<String, List<String>> orFilters, Integer limit, Integer offset, String sortBy,
            Boolean allowBroadQuery) {
        this(keyword, filters, orFilters, limit, offset, sortBy, allowBroadQuery, null);
    }

    /** 是否带至少一个枚举条件（keyword/filters/orFilters 任一非空）；limit/offset/sortBy/allowBroadQuery 不计 */
    public boolean hasAnyCondition() {
        return keyword != null && !keyword.isBlank()
                || filters != null && !filters.isEmpty()
                || orFilters != null && !orFilters.isEmpty();
    }

    /** 是否已由用户明确放行宽查询（仅 Boolean.TRUE 视为放行，null/false 均未放行） */
    public boolean isBroadQueryAllowed() {
        return Boolean.TRUE.equals(allowBroadQuery);
    }
}
