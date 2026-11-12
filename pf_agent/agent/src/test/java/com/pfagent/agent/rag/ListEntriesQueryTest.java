package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/** ListEntriesQuery 参数对象单测（B4）：hasAnyCondition 边界（keyword/filters/orFilters 计数，分页排序不计） */
class ListEntriesQueryTest {

    @Test
    void nullQueryHasNoCondition() {
        assertThat(new ListEntriesQuery(null, null, null, null, null, null).hasAnyCondition()).isFalse();
    }

    @Test
    void limitOffsetSortByAloneAreNotConditions() {
        ListEntriesQuery query = new ListEntriesQuery(null, null, null, 10, 5, "book");
        assertThat(query.hasAnyCondition()).isFalse();
    }

    @Test
    void blankKeywordIsNotACondition() {
        assertThat(new ListEntriesQuery("  ", null, null, null, null, null).hasAnyCondition()).isFalse();
    }

    @Test
    void keywordIsACondition() {
        assertThat(new ListEntriesQuery("火球", null, null, null, null, null).hasAnyCondition()).isTrue();
    }

    @Test
    void filtersAndOrFiltersAreConditions() {
        assertThat(new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null).hasAnyCondition()).isTrue();
        assertThat(new ListEntriesQuery(null, null, Map.of("book", List.of("CRB")), null, null, null)
                .hasAnyCondition()).isTrue();
    }

    @Test
    void emptyMapsAreNotConditions() {
        assertThat(new ListEntriesQuery(null, Map.of(), Map.of(), null, null, null).hasAnyCondition()).isFalse();
    }

    /** F-026：allowBroadQuery 不计入 hasAnyCondition，三态缺省/显式 false 均为未放行 */
    @Test
    void allowBroadQueryDoesNotCountAsConditionAndIsTriState() {
        ListEntriesQuery absent = new ListEntriesQuery(null, null, null, null, null, null);
        ListEntriesQuery explicitFalse = new ListEntriesQuery(null, null, null, null, null, null, false);
        ListEntriesQuery explicitTrue = new ListEntriesQuery(null, null, null, null, null, null, true);

        assertThat(absent.hasAnyCondition()).isFalse();
        assertThat(explicitFalse.hasAnyCondition()).isFalse();
        assertThat(explicitTrue.hasAnyCondition()).isFalse();
        assertThat(absent.isBroadQueryAllowed()).isFalse();
        assertThat(explicitFalse.isBroadQueryAllowed()).isFalse();
        assertThat(explicitTrue.isBroadQueryAllowed()).isTrue();
    }

    /** AKN-025：sortOrder 是展示参数，不计入业务条件；缺省 null 由服务层按 asc 处理 */
    @Test
    void sortOrderDoesNotCountAsCondition() {
        ListEntriesQuery query = new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null,
                "price", null, "desc");

        assertThat(query.sortOrder()).isEqualTo("desc");
        assertThat(query.isBroadQueryAllowed()).isFalse();
        assertThat(query.hasAnyCondition()).isTrue();
    }

    /** F-026：仅书 + 放行仍不算业务条件变化（hasAnyCondition 只看业务条件） */
    @Test
    void allowBroadQueryLeavesBookConditionSemanticsUnchanged() {
        ListEntriesQuery query = new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null, true);

        assertThat(query.hasAnyCondition()).isTrue();
        assertThat(query.isBroadQueryAllowed()).isTrue();
    }
}
