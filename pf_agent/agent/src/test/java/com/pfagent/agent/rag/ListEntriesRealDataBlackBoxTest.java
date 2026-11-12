package com.pfagent.agent.rag;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

/**
 * listEntries 真实 D2 产物黑盒测试（B4，QA 补充）
 *
 * 不 mock ListExportService，直接加载 vectorizer/output 下真实
 * feat/race/equipment_lists.json（6866 条），以使用者视角验证：
 * 概览统计与数据侧 stats 一致、过滤/keyword/分页真实命中数、
 * 工具层截断/钳制/自纠/溯源降级。真实产物缺失时整体跳过（assumeTrue）。
 */
class ListEntriesRealDataBlackBoxTest {

    private static final Path BASE = Path.of("../../pf_data/phase1/vectorizer/output");
    private static final Path FEAT = BASE.resolve("专长/feat_lists.json");
    private static final Path RACE = BASE.resolve("种族/race_lists.json");
    private static final Path EQUIPMENT = BASE.resolve("装备/equipment_lists.json");

    @TempDir
    Path tempDir;

    private ListExportService service;
    private SearchService searchService;
    private RetrievalTools tools;

    @BeforeEach
    void setUp() throws Exception {
        org.junit.jupiter.api.Assumptions.assumeTrue(Files.exists(FEAT) && Files.exists(RACE) && Files.exists(EQUIPMENT),
                "真实 D2 清单产物不存在，跳过黑盒测试");
        // 通过 @TempDir 符号链接引用真实产物，走与生产一致的 load() 通路
        Path featLink = tempDir.resolve("feat_lists.json");
        Path raceLink = tempDir.resolve("race_lists.json");
        Path equipLink = tempDir.resolve("equipment_lists.json");
        Files.createSymbolicLink(featLink, FEAT.toAbsolutePath());
        Files.createSymbolicLink(raceLink, RACE.toAbsolutePath());
        Files.createSymbolicLink(equipLink, EQUIPMENT.toAbsolutePath());

        service = new ListExportService();
        ReflectionTestUtils.setField(service, "featFilePath", featLink.toString());
        ReflectionTestUtils.setField(service, "raceFilePath", raceLink.toString());
        ReflectionTestUtils.setField(service, "equipmentFilePath", equipLink.toString());
        // 向量库点查一律未命中 → 验证降级合成 Document 通路（[#N] 不缺席）
        searchService = mock(SearchService.class);
        ReflectionTestUtils.setField(service, "searchService", searchService);
        service.load();

        tools = new RetrievalTools();
        SourceCollector collector = new SourceCollector();
        collector.begin();
        ReflectionTestUtils.setField(tools, "searchService", searchService);
        ReflectionTestUtils.setField(tools, "collector", collector);
        ReflectionTestUtils.setField(tools, "recorder", mock(DataGapRecorder.class));
        ReflectionTestUtils.setField(tools, "spellListService", mock(SpellListService.class));
        ReflectionTestUtils.setField(tools, "classTableService", mock(ClassTableService.class));
        ReflectionTestUtils.setField(tools, "listExportService", service);
        ReflectionTestUtils.setField(tools, "metadataResultChars", 4000);
        ReflectionTestUtils.setField(tools, "listExportsDefaultLimit", 50);
        ReflectionTestUtils.setField(tools, "listExportsMaxLimit", 200);
    }

    // ---------- 概览 ----------

    @Test
    void overviewMatchesDataSideStats() {
        assertThat(service.overview("feat")).contains("「专长」权威清单共 4080 条", "战斗 1392", "团队 223");
        assertThat(service.overview("race")).contains("「种族」权威清单共 111 条", "概述 111");
        assertThat(service.overview("equipment")).contains("「装备」权威清单共 2681 条", "gear 2428", "weapon 143", "armor 110");
    }

    @Test
    void equipmentOverviewCapsBooksAtTwenty() {
        // 装备 by_book 实测 70 种书 > OVERVIEW_BOOK_CAP 20
        assertThat(service.overview("equipment")).contains("其余 50 种书");
    }

    // ---------- 过滤（命中数与数据侧 python 聚合一致） ----------

    @Test
    void featFiltersMatchDataSideAggregation() {
        assertThat(service.search("feat", q(Map.of("featType", "战斗")), 5000, 0).total()).isEqualTo(1392);
        assertThat(service.search("feat", q(Map.of("hasPrerequisites", "true")), 5000, 0).total()).isEqualTo(3386);
        assertThat(service.search("feat", q(Map.of("hasPrerequisites", "false")), 5000, 0).total())
                .isEqualTo(4080 - 3386);
    }

    @Test
    void raceAndEquipmentFiltersMatchDataSideAggregation() {
        assertThat(service.search("race", q(Map.of("size", "中型")), 5000, 0).total()).isEqualTo(29);
        assertThat(service.search("race", q(Map.of("size", "小型")), 5000, 0).total()).isEqualTo(8);
        assertThat(service.search("equipment", q(Map.of("componentType", "weapon", "book", "CRB")), 5000, 0).total())
                .isEqualTo(16);
        assertThat(service.search("equipment", q(Map.of("componentType", "armor")), 5000, 0).total()).isEqualTo(110);
    }

    @Test
    void orFiltersBookGroupIsOrWithinGroup() {
        int crb = service.search("equipment", q(Map.of("componentType", "weapon", "book", "CRB")), 5000, 0).total();
        int apg = service.search("equipment", q(Map.of("componentType", "weapon", "book", "APG")), 5000, 0).total();
        ListExportService.EntryPage orPage = service.search("equipment",
                new ListEntriesQuery(null, Map.of("componentType", "weapon"),
                        Map.of("book", List.of("CRB", "APG")), null, null, null),
                5000, 0);
        assertThat(orPage.total()).isEqualTo(crb + apg);
    }

    // ---------- keyword ----------

    @Test
    void keywordMatchesRealDataCounts() {
        assertThat(service.search("feat", new ListEntriesQuery("武器", null, null, null, null, null), 5000, 0).total())
                .isEqualTo(64);
        assertThat(service.search("feat", new ListEntriesQuery("dodge", null, null, null, null, null), 5000, 0).total())
                .isEqualTo(13);
    }

    @Test
    void keywordFullWidthMatchesHalfWidthData() {
        // 真实数据为半角 "dodge"，全角检索词须命中（NFKC 归一）
        assertThat(service.search("feat", new ListEntriesQuery("ｄｏｄｇｅ", null, null, null, null, null), 5000, 0)
                .total()).isEqualTo(13);
    }

    // ---------- 分页边界 ----------

    @Test
    void paginationBoundariesOnRealFeatList() {
        ListExportService.EntryPage last = service.search("feat",
                new ListEntriesQuery(null, null, null, null, null, null), 10, 4079);
        assertThat(last.total()).isEqualTo(4080);
        assertThat(last.entries()).hasSize(1);

        ListExportService.EntryPage overflow = service.search("feat",
                new ListEntriesQuery(null, null, null, null, null, null), 50, 5000);
        assertThat(overflow.total()).isEqualTo(4080);
        assertThat(overflow.entries()).isEmpty();

        // 服务层负 offset 钳制为 0 不抛异常
        ListExportService.EntryPage negative = service.search("feat",
                new ListEntriesQuery(null, null, null, null, null, null), 3, -5);
        assertThat(negative.entries()).hasSize(3);
    }

    // ---------- 工具层端到端（真实 service + 降级溯源） ----------

    @Test
    void toolEndToEndConditionalQueryWithFallbackProvenance() {
        String result = tools.listEntries("feat", new ListEntriesQuery("武器", null, null, 5, null, null));

        assertThat(result).doesNotContain("无命中");
        // 行格式：序号. 名（en）[书] | 属性 | chunk_id: xxx [#N]
        assertThat(result).containsPattern("\\d+\\. .+\\[.+\\].*\\| chunk_id: .+\\s\\[#\\d+\\]");
        // 点查未命中降级合成，[#N] 不缺席
        assertThat(result).contains("[#");
        // 仅展示 5 条但命中 64 条 → 翻页提示
        assertThat(result).contains("共 64 条命中", "offset 翻页");
    }

    @Test
    void toolRejectsUnknownModuleAndUnknownFilterField() {
        assertThat(tools.listEntries("spell", null)).contains("未知模块", "feat(专长)/race(种族)/equipment(装备)");
        assertThat(tools.listEntries("feat", new ListEntriesQuery(null, Map.of("price", "100"), null, null, null, null)))
                .contains("未知过滤字段", "[featType, book, hasPrerequisites]");
        assertThat(tools.listEntries("feat", new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, "price")))
                .contains("未知排序字段");
    }

    @Test
    void toolClampsLimitBeyondBoundsOnRealData() {
        String over = tools.listEntries("feat", new ListEntriesQuery(null, Map.of("featType", "战斗"), null, 201, null, null));
        assertThat(over).startsWith("（limit 超出上限，已钳制为 200）");
        assertThat(over).contains("共 1392 条命中");

        String zero = tools.listEntries("feat", new ListEntriesQuery(null, Map.of("featType", "战斗"), null, 0, null, null));
        assertThat(zero).startsWith("（limit 小于 1，已钳制为 1）");

        // limit=1 合法边界：不钳制、无钳制注记
        String one = tools.listEntries("feat", new ListEntriesQuery(null, Map.of("featType", "战斗"), null, 1, null, null));
        assertThat(one).doesNotStartWith("（limit");
        assertThat(one).contains("共 1392 条命中");
    }

    @Test
    void toolTruncatesLongResultWithoutTagsOnTruncatedPart() {
        // featType=战斗 1392 条、默认 limit=50，4000 字符预算只容约 25 行 → 截断 + 翻页提示
        String result = tools.listEntries("feat", new ListEntriesQuery(null, Map.of("featType", "战斗"), null, null, null, null));

        assertThat(result).contains("结果过多，仅展示前");
        assertThat(result).contains("共 1392 条命中", "offset 翻页");
        // 截断提示之后的部分不再有个别行（整体行数 < 50）
        int lineCount = result.lines().filter(l -> l.matches("\\d+\\. .*")).toList().size();
        assertThat(lineCount).isLessThan(50).isGreaterThan(5);
    }

    @Test
    void toolOffsetOverflowReturnsPaginationHintOnRealData() {
        String result = tools.listEntries("feat",
                new ListEntriesQuery(null, Map.of("featType", "战斗"), null, 50, 2000, null));
        assertThat(result).contains("无命中", "共 1392 条命中", "offset=2000 越界");
    }

    @Test
    void toolUnconditionalReturnsOverviewOnRealData() {
        assertThat(tools.listEntries("equipment", null)).contains("「装备」权威清单共 2681 条");
        assertThat(tools.listEntries("race", new ListEntriesQuery(null, null, null, null, null, null)))
                .contains("「种族」权威清单共 111 条");
    }

    // ---------- 边界行为实测（供报告记录，非验收断言） ----------

    @Test
    void edgeHasPrerequisitesNonBooleanValueIsTreatedAsFalse() {
        // 实测：hasPrerequisites="yes" 落入 false 分支（按无前置匹配），不报错也不报字段值非法
        assertThat(service.search("feat", q(Map.of("hasPrerequisites", "yes")), 5000, 0).total())
                .isEqualTo(4080 - 3386);
    }

    @Test
    void edgeEmptyFilterValueMatchesBlankFields() {
        // 实测：race size="" 精确匹配数据侧 74 条空 size（空串等于空串）
        assertThat(service.search("race", q(Map.of("size", "")), 5000, 0).total()).isEqualTo(74);
    }

    private static ListEntriesQuery q(Map<String, String> filters) {
        return new ListEntriesQuery(null, filters, null, null, null, null);
    }
}
