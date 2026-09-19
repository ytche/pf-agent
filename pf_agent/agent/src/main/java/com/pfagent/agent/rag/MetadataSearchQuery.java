package com.pfagent.agent.rag;

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

    /** AND 精确条件：{school:"咒法系"}（沿用旧 filters 语义，可空） */
    private Map<String, String> filters;
    /** 组内 OR：{book:["CRB","APG"]}（同一字段多个候选值任一命中，可空） */
    private Map<String, List<String>> orFilters;
    /** 比较下限：{level:"3"}（值按字符串数字比较，可空） */
    private Map<String, String> gte;
    /** 比较上限（可空） */
    private Map<String, String> lte;
    /** 排序字段：title|level|book，可空=默认序 */
    private String sortBy;
    /** 排序方向：asc|desc，默认 asc（可空） */
    private String sortOrder;
    /** 返回条数上限，默认 pf.search.metadata-default-limit（50），上限受 enumeration-top-k 约束 */
    private Integer limit;
    /** 跳过的条数，默认 0（可空） */
    private Integer offset;

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
        this.gte = gte;
    }

    public Map<String, String> getLte() {
        return lte;
    }

    public void setLte(Map<String, String> lte) {
        this.lte = lte;
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

    /** 是否至少带一个过滤条件（filters/orFilters/gte/lte 任一非空） */
    public boolean hasAnyCondition() {
        return notEmpty(filters) || notEmpty(orFilters) || notEmpty(gte) || notEmpty(lte);
    }

    private static boolean notEmpty(Map<?, ?> map) {
        return map != null && !map.isEmpty();
    }
}
