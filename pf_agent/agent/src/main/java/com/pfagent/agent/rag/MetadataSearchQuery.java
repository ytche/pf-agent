package com.pfagent.agent.rag;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * searchByMetadata 增强版的过滤参数对象（SP8a J2，2026-09-18 拍板）
 *
 * 一个 @Tool 方法不摊多参数：or/范围/排序/分页全部收敛为本对象，由 Jackson
 * 反序列化驱动（Spring AI 从 POJO 生成工具 schema，必填仅 module+query）。
 * 所有字段可空；全部为空时工具层返回"请提供至少一个过滤条件"可读提示。
 *
 * filters/orFilters/gte/lte 的键均为逻辑字段名（title/school/book/className…），
 * 由 FilterTranslator 翻译为扁平 metadata 键——LLM 永不接触 FilterExpression 字符串。
 */
public class MetadataSearchQuery {

    /**
     * gte/lte 的私有载体类型（非 API，仅 field 声明用）。
     *
     * Spring AI 1.0.0-M6 的 JsonSchemaGenerator.generateForMethodInput 对每个参数单独
     * 生成 schema 再内联进 properties；victools 对同一泛型类型在文档内出现 ≥2 次时会把它
     * 提升为 #/$defs/... 并在引用处写 $ref，而 $defs 实际嵌在该参数节点下，导致引用悬空
     * （DeepSeek 400 Invalid schema: Pointer '/$defs/Map_String.String_' does not exist）。
     * filters/gte/lte 原本都是 Map<String,String>（一个参数对象内出现 3 次）触发该 bug；
     * 让 gte/lte 各用独立载体子类型后，每种复杂类型在单个参数对象内只出现一次，全部内联，
     * 不再产生 $defs/$ref。getter/setter 仍暴露 Map<String,String>，对外 API 与行为不变。
     * 回归测试 {@link RetrievalToolsToolSchemaTest} 断言所有 @Tool schema 无悬空 $ref。
     */
    static final class GteMap extends LinkedHashMap<String, String> {
    }

    static final class LteMap extends LinkedHashMap<String, String> {
    }

    /** AND 精确条件：{school:"咒法系"}（沿用旧 filters 语义，可空） */
    private Map<String, String> filters;
    /** 组内 OR：{book:["CRB","APG"]}（同一字段多个候选值任一命中，可空） */
    private Map<String, List<String>> orFilters;
    /** 比较下限：{level:"3"}（值按字符串数字比较，可空） */
    private GteMap gte;
    /** 比较上限（可空） */
    private LteMap lte;
    /** 排序字段：title|level|book，可空=默认序 */
    private String sortBy;
    /** 排序方向：asc|desc，默认 asc（可空） */
    private String sortOrder;
    /** 返回条数上限，默认 pf.search.metadata-default-limit（50），上限受 enumeration-top-k 约束 */
    private Integer limit;
    /** 跳过的条数，默认 0（可空） */
    private Integer offset;
    /**
     * 宽查询放行声明（F-026）：null/false = 未放行；true = 用户明确确认后按原范围查询。
     * 不是业务过滤条件，不计入 {@link #hasAnyCondition()}；同一业务条件的每页都要携带，
     * 业务条件变化后需重新判断。
     */
    private Boolean allowBroadQuery;

    public Map<String, String> getFilters() {
        return filters;
    }

    public void setFilters(Map<String, String> filters) {
        this.filters = filters;
    }

    public Map<String, List<String>> getOrFilters() {
        return orFilters;
    }

    public void setOrFilters(Map<String, List<String>> orFilters) {
        this.orFilters = orFilters;
    }

    public Map<String, String> getGte() {
        return gte;
    }

    public void setGte(Map<String, String> gte) {
        if (gte == null) {
            this.gte = null;
            return;
        }
        this.gte = new GteMap();
        this.gte.putAll(gte);
    }

    public Map<String, String> getLte() {
        return lte;
    }

    public void setLte(Map<String, String> lte) {
        if (lte == null) {
            this.lte = null;
            return;
        }
        this.lte = new LteMap();
        this.lte.putAll(lte);
    }

    public String getSortBy() {
        return sortBy;
    }

    public void setSortBy(String sortBy) {
        this.sortBy = sortBy;
    }

    public String getSortOrder() {
        return sortOrder;
    }

    public void setSortOrder(String sortOrder) {
        this.sortOrder = sortOrder;
    }

    public Integer getLimit() {
        return limit;
    }

    public void setLimit(Integer limit) {
        this.limit = limit;
    }

    public Integer getOffset() {
        return offset;
    }

    public void setOffset(Integer offset) {
        this.offset = offset;
    }

    public Boolean getAllowBroadQuery() {
        return allowBroadQuery;
    }

    public void setAllowBroadQuery(Boolean allowBroadQuery) {
        this.allowBroadQuery = allowBroadQuery;
    }

    /** 是否已由用户明确放行宽查询（仅 Boolean.TRUE 视为放行，null/false 均未放行） */
    public boolean isBroadQueryAllowed() {
        return Boolean.TRUE.equals(allowBroadQuery);
    }

    /** 是否至少带一个过滤条件（filters/orFilters/gte/lte 任一非空） */
    public boolean hasAnyCondition() {
        return notEmpty(filters) || notEmpty(orFilters) || notEmpty(gte) || notEmpty(lte);
    }

    private static boolean notEmpty(Map<?, ?> map) {
        return map != null && !map.isEmpty();
    }
}
