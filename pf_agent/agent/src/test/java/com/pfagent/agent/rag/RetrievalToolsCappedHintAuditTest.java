package com.pfagent.agent.rag;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.when;

/**
 * AKN015-T1/T3 返修复验用例（tester 独立补充）
 *
 * 覆盖点（coder 新增用例未覆盖或断言不足的部分）：
 *  - 诚实版文案「绝不出现『共 N 条』」用负向正则全局断言（coder 只断言 doesNotContain 具体字面量）
 *  - capped 边界内翻页第 2 页的区间/next_offset 一致性（不变量：终点 == next_offset == offset+展示行数）
 *  - capped 末页（无字符截断）→ 只给收窄、不给 has_more/next_offset
 *  - capped + 越界 / uncapped + 越界 / offset>0 且 totalCount==0（真无数据）三态分叉
 *  - 4 参兼容构造（capped=false）不引入新文案
 *  - 跨模块 all：totalCount 可 > cap 时保留正确区间，并把 cap 表述为单库检索上限（AKN-018）
 */
@ExtendWith(MockitoExtension.class)
class RetrievalToolsCappedHintAuditTest {

    private static final Pattern TOTAL_CLAIM = Pattern.compile("共 \\d+ 条");
    private static final Pattern RANGE = Pattern.compile("本次返回第 (\\d+)~(\\d+) 条");
    private static final Pattern NEXT_OFFSET = Pattern.compile("query\\.offset=(\\d+)");
    private static final Pattern NUMBERED_LINE = Pattern.compile("(?m)^\\d+\\. ");

    @Mock
    private SearchService searchService;
    @Mock
    private SourceCollector collector;

    // ---------- T1：诚实版文案 ----------

    @Test
    @DisplayName("capped 首屏（字符截断）：三要素齐全 + 无『共 N 条』假总数 + 区间/next_offset 自洽")
    void cappedFirstPageIsHonestAndSelfConsistent() {
        stubPaged(new SearchService.PagedResult(docs(500), 500, 0, 500, true, 500));

        String result = tools(4000).searchByMetadata("spell", query(0, 500));

        assertThat(result).contains("已达检索上限 500 条", "实际命中可能更多");
        assertThat(result).contains("has_more=true");
        // 负向断言：任何"共 N 条"形态都不得出现（含"共 500 条"及其它总数措辞）
        assertThat(TOTAL_CLAIM.matcher(result).find()).as("capped 不得出现『共 N 条』").isFalse();

        int shown = numberedLines(result);
        assertThat(shown).isBetween(1, 499);
        assertThat(hintStart(result)).isEqualTo(1);
        assertThat(hintEnd(result)).isEqualTo(shown);
        assertThat(hintNextOffset(result)).isEqualTo(shown);
        assertThat(hintNextOffset(result)).isLessThanOrEqualTo(500);
    }

    @Test
    @DisplayName("capped 边界内第 2 页（limit=200）：区间 201~400、next_offset=400，不越过上限")
    void cappedSecondPageWithinLimit() {
        stubPaged(new SearchService.PagedResult(docs(200), 500, 200, 200, true, 500));

        String result = tools(200000).searchByMetadata("spell", query(200, 200));

        assertThat(result).contains("本次返回第 201~400 条", "query.offset=400");
        assertThat(TOTAL_CLAIM.matcher(result).find()).isFalse();
    }

    @Test
    @DisplayName("capped 且已到上限末页（整页展示、无字符截断）：只给收窄，不给 has_more/next_offset")
    void cappedLastPageOnlyAdvisesNarrowing() {
        stubPaged(new SearchService.PagedResult(docs(20), 500, 480, 20, true, 500));

        String result = tools(4000).searchByMetadata("spell", query(480, 20));

        assertThat(result).contains("已达检索上限 500 条", "本工具最多只能取前 500 条", "请收窄过滤条件");
        assertThat(result).doesNotContain("has_more", "query.offset");
        assertThat(TOTAL_CLAIM.matcher(result).find()).isFalse();
    }

    // ---------- T3：越界三态 ----------

    @Test
    @DisplayName("T3 uncapped 越界：告知『已翻完全部结果（共 N 条）』，不复用『无命中』")
    void offsetBeyondUncappedTotalReportsExhausted() {
        stubPaged(new SearchService.PagedResult(List.of(), 143, 143, 50));

        String result = tools(4000).searchByMetadata("spell", query(143, 50));

        assertThat(result).contains("已翻完全部结果（共 143 条）");
        assertThat(result).doesNotContain("无命中");
    }

    @Test
    @DisplayName("T3 capped 越界：告知『已翻完工具可返回的前 N 条』+ 已达上限 + 收窄，且不给假总数")
    void offsetBeyondCappedTotalReportsExhaustedHonestly() {
        stubPaged(new SearchService.PagedResult(List.of(), 500, 500, 50, true, 500));

        String result = tools(4000).searchByMetadata("spell", query(500, 50));

        assertThat(result).contains("已翻完", "已达检索上限", "实际命中可能更多", "请收窄过滤条件");
        assertThat(result).doesNotContain("无命中");
        assertThat(TOTAL_CLAIM.matcher(result).find()).isFalse();
    }

    @Test
    @DisplayName("真无数据（totalCount=0）即使带了 offset 也走『无命中』引导，不得误报已翻完")
    void emptyResultWithOffsetStillNoHit() {
        stubPaged(new SearchService.PagedResult(List.of(), 0, 5, 50));

        String result = tools(4000).searchByMetadata("spell", query(5, 50));

        assertThat(result).contains("无命中");
        assertThat(result).doesNotContain("已翻完");
    }

    // ---------- 向后兼容 ----------

    @Test
    @DisplayName("4 参兼容构造（capped=false）：文案仍是旧版『共 N 条』形态，不引入诚实版文案")
    void legacyFourArgConstructorBehavesAsBefore() {
        stubPaged(new SearchService.PagedResult(docs(5), 10, 0, 5));

        String result = tools(4000).searchByMetadata("spell", query(0, 5));

        assertThat(result).contains("…（共 10 条，本次返回第 1~5 条，has_more=true；续取：保持其他参数不变，query.offset=5）");
        assertThat(result).doesNotContain("已达检索上限", "实际命中可能更多");
    }

    // ---------- 跨模块 capped 回归（AKN-018） ----------

    @Test
    void crossModuleCappedTotalBeyondCapShouldNotClaimCapBoundary() {
        // all 模块：spell 库原始命中 500（capped），class 库 3 条 → merged totalCount=503
        stubPaged("all", new SearchService.PagedResult(docs(3), 503, 500, 500, true, 500));

        String result = tools(4000).searchByMetadata("all", query(500, 500));

        assertThat(result).contains("至少一个模块已达单库检索上限 500 条", "实际命中可能更多",
                "本次返回第 501~503 条", "当前跨模块合并结果已全部展示");
        assertThat(result).doesNotContain("本工具最多只能取前 500 条");
    }

    @Test
    void crossModuleCappedOffsetOverflowShouldDescribeMergedResult() {
        stubPaged("all", new SearchService.PagedResult(List.of(), 503, 503, 500, true, 500));

        String result = tools(4000).searchByMetadata("all", query(503, 500));

        assertThat(result).contains("已翻完当前跨模块合并结果", "本次可返回 503 条",
                "至少一个模块已达单库检索上限 500 条", "实际命中可能更多", "请收窄过滤条件");
        assertThat(result).doesNotContain("已翻完工具可返回的前 503 条", "最多只能取前 500 条");
    }

    @Test
    void cappedTruncatedLastPageShouldPreferContinuationOverNarrowing() {
        stubPaged(new SearchService.PagedResult(docs(100), 500, 400, 100, true, 500));

        String result = tools(260).searchByMetadata("spell", query(400, 100));

        int shown = numberedLines(result);
        assertThat(shown).isBetween(1, 99);
        // 页内还有未展示条目时只给续取（offset=400+shown），不同时劝收窄
        assertThat(result).doesNotContain("请收窄过滤条件");
        assertThat(result).contains("has_more=true");
        assertThat(hintNextOffset(result)).isEqualTo(400 + shown);
    }

    // ---------- T2 返修补测（coder 未覆盖） ----------

    @Test
    @DisplayName("T2 + capped：shown==0 走 getEntryById 引导，且不出现任何假总数/续取字段")
    void zeroShownWithCappedGivesEntryGuidanceWithoutFakeTotal() {
        stubPaged(new SearchService.PagedResult(docs(500), 500, 0, 500, true, 500));

        String result = tools(10).searchByMetadata("spell", query(0, 500));

        assertThat(result).contains("本页无条目可展示", "getEntryById(module=\"spell\"",
                "不要用相同 offset 重复翻页");
        assertThat(result).doesNotContain("query.offset", "has_more", "本次返回");
        assertThat(TOTAL_CLAIM.matcher(result).find()).as("不得出现『共 N 条』").isFalse();
        assertThat(RANGE.matcher(result).find()).as("不得出现『第 X~Y 条』区间").isFalse();
    }

    @Test
    @DisplayName("T2 + 跨模块 all：getEntryById 的 module 取自首条 pf_module（不是 all）")
    void zeroShownCrossModuleResolvesRealModule() {
        List<Document> page = new ArrayList<>();
        for (int i = 1; i <= 3; i++) {
            page.add(Document.builder().text("正文").metadata(Map.of("title", "猛力攻击",
                    "chunk_id", "feat-" + i, "pf_module", "feat")).build());
        }
        when(searchService.searchByMetadataPaged(eq("all"), any(MetadataSearchQuery.class)))
                .thenReturn(new SearchService.PagedResult(page, 3, 40, 50));
        lenient().when(collector.add(any())).thenReturn(List.of(1, 2, 3));

        String result = tools(10).searchByMetadata("all", query(40, 50));

        assertThat(result).contains("本页从第 41 条起", "getEntryById(module=\"feat\"",
                "chunkId=\"feat-1\"");
        assertThat(result).doesNotContain("module=\"all\"");
    }

    // ---------- harness ----------

    private MetadataSearchQuery query(int offset, int limit) {
        MetadataSearchQuery q = new MetadataSearchQuery();
        q.setFilters(Map.of("book", "CRB"));
        // F-026：仅书宽查询，需显式放行才能继续覆盖原有翻页/上限断言
        q.setAllowBroadQuery(true);
        q.setOffset(offset);
        q.setLimit(limit);
        return q;
    }

    private void stubPaged(SearchService.PagedResult paged) {
        stubPaged("spell", paged);
    }

    private void stubPaged(String module, SearchService.PagedResult paged) {
        when(searchService.searchByMetadataPaged(eq(module), any(MetadataSearchQuery.class)))
                .thenReturn(paged);
        lenient().when(collector.add(any())).thenAnswer(inv -> {
            List<Document> arg = inv.getArgument(0);
            List<Integer> seq = new ArrayList<>(arg.size());
            for (int n = 1; n <= arg.size(); n++) {
                seq.add(n);
            }
            return seq;
        });
    }

    private List<Document> docs(int n) {
        List<Document> list = new ArrayList<>();
        for (int i = 1; i <= n; i++) {
            list.add(Document.builder().text("正文").metadata(Map.of("title", "法术" + i,
                    "book_abbreviation", "CRB", "chunk_id", "spell-" + i)).build());
        }
        return list;
    }

    private RetrievalTools tools(int metadataResultChars) {
        RetrievalTools t = new RetrievalTools();
        ReflectionTestUtils.setField(t, "searchService", searchService);
        ReflectionTestUtils.setField(t, "collector", collector);
        ReflectionTestUtils.setField(t, "filterTranslator", new FilterTranslator());
        ReflectionTestUtils.setField(t, "vectorResultChars", 1500);
        ReflectionTestUtils.setField(t, "metadataResultChars", metadataResultChars);
        ReflectionTestUtils.setField(t, "entryResultChars", 8000);
        ReflectionTestUtils.setField(t, "metadataDefaultLimit", 50);
        ReflectionTestUtils.setField(t, "gapsListDefaultLimit", 20);
        return t;
    }

    private int numberedLines(String text) {
        Matcher m = NUMBERED_LINE.matcher(text);
        int count = 0;
        while (m.find()) {
            count++;
        }
        return count;
    }

    private int hintStart(String text) {
        Matcher m = RANGE.matcher(text);
        assertThat(m.find()).as("应存在区间提示").isTrue();
        return Integer.parseInt(m.group(1));
    }

    private int hintEnd(String text) {
        Matcher m = RANGE.matcher(text);
        assertThat(m.find()).as("应存在区间提示").isTrue();
        return Integer.parseInt(m.group(2));
    }

    private int hintNextOffset(String text) {
        Matcher m = NEXT_OFFSET.matcher(text);
        assertThat(m.find()).as("应存在 next_offset 提示").isTrue();
        return Integer.parseInt(m.group(1));
    }
}
