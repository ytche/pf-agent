package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * ListExportService 单元测试（B4，D2）
 *
 * 覆盖方案验收要点：
 *  - 三模块加载成功：available/knownModules/total；未知字段（sections/excluded/stats 等）容错
 *  - 单文件缺失/损坏：仅该模块 available=false，其余模块正常
 *  - 无条件概览：total + 模块维度统计 + by_book 统计
 *  - 过滤正确性：feat featType/orFilters.featType/book/hasPrerequisites；
 *    race raceGroup/size/bioType；equipment componentType/slot/book
 *  - keyword：中文/英文/别名子串（大小写混用、全半角混用）；未命中返回空页
 *  - 排序：name 默认；book 按书再按名；分页 offset/limit
 *  - entryLine：feat 类别/前置（无前置省略）；race 分组/体型/速度 + ≤20 条附 ability_adj/senses；
 *    equipment 类型/价格/重量；book="?" 展示未知来源
 *  - 溯源：searchService 命中挂真实 chunk；未命中/未注入降级合成 Document 含 chunk_id/doc_id
 *  - 缺可选字段（prerequisites_raw 为 null / chunk_id 为 null）不抛异常
 */
class ListExportServiceTest {

    @TempDir
    Path tempDir;

    @Test
    void loadsAllThreeModules() throws Exception {
        ListExportService service = loadedAll();

        assertThat(service.isAvailable("feat")).isTrue();
        assertThat(service.isAvailable("race")).isTrue();
        assertThat(service.isAvailable("equipment")).isTrue();
        assertThat(service.knownModules()).containsExactly("feat", "race", "equipment");
        assertThat(service.total("feat")).isEqualTo(3);
        assertThat(service.total("race")).isEqualTo(2);
        assertThat(service.total("equipment")).isEqualTo(3);
    }

    @Test
    void missingFileDegradesOnlyThatModule() throws Exception {
        write("feat_lists.json", Fixtures.featJson());
        write("equipment_lists.json", Fixtures.equipmentJson());
        ListExportService service = service(tempDir.resolve("feat_lists.json").toString(),
                tempDir.resolve("nope.json").toString(),
                tempDir.resolve("equipment_lists.json").toString());

        service.load();

        assertThat(service.isAvailable("feat")).isTrue();
        assertThat(service.isAvailable("race")).isFalse();
        assertThat(service.isAvailable("equipment")).isTrue();
        assertThat(service.overview("race")).contains("共 0 条");
    }

    @Test
    void malformedFileDegradesOnlyThatModule() throws Exception {
        write("feat_lists.json", "{ not json ");
        write("race_lists.json", Fixtures.raceJson());
        write("equipment_lists.json", Fixtures.equipmentJson());
        ListExportService service = service(tempDir.resolve("feat_lists.json").toString(),
                tempDir.resolve("race_lists.json").toString(),
                tempDir.resolve("equipment_lists.json").toString());

        service.load();

        assertThat(service.isAvailable("feat")).isFalse();
        assertThat(service.isAvailable("race")).isTrue();
        assertThat(service.search("race", new ListEntriesQuery(null, Map.of("size", "中型"), null, null, null, null),
                50, 0).total()).isEqualTo(2);
    }

    @Test
    void overviewShowsStatsAndBookBreakdown() throws Exception {
        ListExportService service = loadedAll();

        String feat = service.overview("feat");
        assertThat(feat).contains("「专长」权威清单共 3 条", "按专长类别：战斗 2、团队 1", "CRB 2、APG 1");
        assertThat(feat).contains("请提供 keyword 或过滤条件");

        String race = service.overview("race");
        assertThat(race).contains("「种族」权威清单共 2 条", "未知来源 2", "按种族分组");

        String equipment = service.overview("equipment");
        assertThat(equipment).contains("「装备」权威清单共 3 条", "weapon 2、gear 1");
    }

    @Test
    void featFiltersByFeatTypeOrBookAndHasPrerequisites() throws Exception {
        ListExportService service = loadedAll();

        assertThat(names(service.search("feat",
                new ListEntriesQuery(null, Map.of("featType", "战斗"), null, null, null, null), 50, 0)))
                .containsExactly("双武器攻击", "闪避");
        assertThat(names(service.search("feat",
                new ListEntriesQuery(null, Map.of("hasPrerequisites", "true"), null, null, null, null), 50, 0)))
                .containsExactly("双武器攻击", "领导力");
        assertThat(names(service.search("feat",
                new ListEntriesQuery(null, Map.of("hasPrerequisites", "false"), null, null, null, null), 50, 0)))
                .containsExactly("闪避");
        // orFilters.featType 多值 OR + filters.book AND 组合（领导力在 APG）
        ListExportService.EntryPage page = service.search("feat", new ListEntriesQuery(null,
                Map.of("book", "APG"), Map.of("featType", List.of("团队", "一般")), null, null, null), 50, 0);
        assertThat(names(page)).containsExactly("领导力");
    }

    @Test
    void raceFiltersByGroupSizeAndBioType() throws Exception {
        ListExportService service = loadedAll();

        assertThat(names(service.search("race",
                new ListEntriesQuery(null, Map.of("raceGroup", "元素"), null, null, null, null), 50, 0)))
                .containsExactly("精灵");
        assertThat(names(service.search("race",
                new ListEntriesQuery(null, Map.of("size", "中型"), null, null, null, null), 50, 0)))
                .containsExactly("矮人", "精灵");
        assertThat(names(service.search("race",
                new ListEntriesQuery(null, Map.of("bioType", "精类"), null, null, null, null), 50, 0)))
                .containsExactly("精灵");
    }

    @Test
    void equipmentFiltersByComponentTypeSlotAndBook() throws Exception {
        ListExportService service = loadedAll();

        assertThat(names(service.search("equipment",
                new ListEntriesQuery(null, Map.of("componentType", "weapon"), null, null, null, null), 50, 0)))
                .containsExactly("镭武器", "长剑");
        assertThat(names(service.search("equipment",
                new ListEntriesQuery(null, Map.of("slot", "手部"), null, null, null, null), 50, 0)))
                .containsExactly("铁手套");
        assertThat(names(service.search("equipment",
                new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null), 50, 0)))
                .containsExactly("铁手套", "长剑");
    }

    @Test
    void keywordMatchesCnEnAndAliasesCaseAndWidthInsensitive() throws Exception {
        ListExportService service = loadedAll();

        // 中文子串
        assertThat(names(service.search("feat",
                new ListEntriesQuery("武器", null, null, null, null, null), 50, 0)))
                .containsExactly("双武器攻击");
        // 英文大小写混用（fixture 别名全大写）
        assertThat(names(service.search("feat",
                new ListEntriesQuery("dodge", null, null, null, null, null), 50, 0)))
                .containsExactly("闪避");
        // 全半角混用：全角括号与大小写
        assertThat(names(service.search("equipment",
                new ListEntriesQuery("ｒａｄｉｕｍ", null, null, null, null, null), 50, 0)))
                .containsExactly("镭武器");
        // 未命中：空页且 total=0
        ListExportService.EntryPage miss = service.search("race",
                new ListEntriesQuery("不存在的东西", null, null, null, null, null), 50, 0);
        assertThat(miss.entries()).isEmpty();
        assertThat(miss.total()).isZero();
    }

    @Test
    void sortByNameDefaultAndByBookThenName() throws Exception {
        ListExportService service = loadedAll();

        assertThat(names(service.search("equipment",
                new ListEntriesQuery(null, null, null, null, null, null), 50, 0)))
                .containsExactly("铁手套", "镭武器", "长剑");
        assertThat(names(service.search("equipment",
                new ListEntriesQuery(null, null, null, null, null, "book"), 50, 0)))
                .containsExactly("铁手套", "长剑", "镭武器");
    }

    @Test
    void equipmentPriceSortAscendingAndDescendingPutsNullLast() throws Exception {
        ListExportService service = loadedPriceEquipment();

        assertThat(names(service.search("equipment",
                new ListEntriesQuery(null, null, null, null, null, "price", null, "asc"), 50, 0)))
                .containsExactly("低价药水", "中价戒指", "力量法杖", "无价神器");
        assertThat(names(service.search("equipment",
                new ListEntriesQuery(null, null, null, null, null, "price", null, "desc"), 50, 0)))
                .containsExactly("力量法杖", "中价戒指", "低价药水", "无价神器");
        // sortOrder 缺省 = asc
        assertThat(names(service.search("equipment",
                new ListEntriesQuery(null, null, null, null, null, "price"), 50, 0)))
                .containsExactly("低价药水", "中价戒指", "力量法杖", "无价神器");
    }

    @Test
    void equipmentPriceRangeFiltersExcludeNullPrice() throws Exception {
        ListExportService service = loadedPriceEquipment();

        assertThat(names(service.search("equipment", new ListEntriesQuery(null,
                Map.of("price_min", "1000", "price_max", "235000"), null, null, null, null), 50, 0)))
                .containsExactly("中价戒指", "力量法杖");
        assertThat(names(service.search("equipment", new ListEntriesQuery(null,
                Map.of("price_min", "1001"), null, null, null, null), 50, 0)))
                .containsExactly("力量法杖");
        assertThat(names(service.search("equipment", new ListEntriesQuery(null,
                Map.of("price_max", "10"), null, null, null, null), 50, 0)))
                .containsExactly("低价药水");
    }

    @Test
    void priceGpParsedFromSnakeCaseAndLegacyFileDetected() throws Exception {
        ListExportService priced = loadedPriceEquipment();
        assertThat(priced.hasPriceData("equipment")).isTrue();
        assertThat(priced.search("equipment",
                new ListEntriesQuery("力量法杖", null, null, null, null, null), 50, 0)
                .entries().get(0).priceGp()).isEqualTo(235000);

        // 旧版清单（无 price_gp）：明确判定为不支持 price 能力，不静默给错误排序
        ListExportService legacy = loadedAll();
        assertThat(legacy.hasPriceData("equipment")).isFalse();
    }

    @Test
    void paginationOffsetAndLimit() throws Exception {
        ListExportService service = loadedAll();

        ListExportService.EntryPage page = service.search("equipment",
                new ListEntriesQuery(null, null, null, 2, 1, null), 2, 1);
        assertThat(page.total()).isEqualTo(3);
        assertThat(names(page)).containsExactly("镭武器", "长剑");
        // offset 越界：空页但 total 保留
        ListExportService.EntryPage overflow = service.search("equipment",
                new ListEntriesQuery(null, null, null, null, null, null), 50, 10);
        assertThat(overflow.entries()).isEmpty();
        assertThat(overflow.total()).isEqualTo(3);
    }

    @Test
    void unknownFilterFieldsReportedPerModule() throws Exception {
        ListExportService service = loadedAll();

        assertThat(service.availableFilterFields("feat")).containsExactly("featType", "book", "hasPrerequisites");
        assertThat(service.availableFilterFields("race")).containsExactly("raceGroup", "size", "bioType", "book");
        assertThat(service.availableFilterFields("equipment"))
                .containsExactly("componentType", "slot", "book", "price_min", "price_max");
        Set<String> unknown = service.unknownFilterFields("feat",
                new ListEntriesQuery(null, Map.of("slot", "手部"), Map.of("raceGroup", List.of("元素")), null, null, null));
        assertThat(unknown).containsExactly("slot", "raceGroup");
        assertThat(service.unknownFilterFields("feat",
                new ListEntriesQuery(null, Map.of("book", "CRB"), null, null, null, null))).isEmpty();
    }

    @Test
    void featEntryLineShowsCategoryPrerequisitesAndChunkId() throws Exception {
        ListExportService service = loadedAll();
        ListExportService.ListEntry entry = service.search("feat",
                new ListEntriesQuery("双武器", null, null, null, null, null), 50, 0).entries().get(0);

        String line = service.entryLine("feat", 1, entry, false);

        assertThat(line).isEqualTo("1. 双武器攻击（Two-Weapon Fighting）[CRB]"
                + " | 类别:战斗 | 前置:敏捷15 | chunk_id: feat_page_1_0000");
    }

    @Test
    void featEntryLineOmitsEmptyPrerequisites() throws Exception {
        ListExportService service = loadedAll();
        ListExportService.ListEntry entry = service.search("feat",
                new ListEntriesQuery("闪避", null, null, null, null, null), 50, 0).entries().get(0);

        String line = service.entryLine("feat", 1, entry, false);

        assertThat(line).contains("类别:战斗");
        assertThat(line).doesNotContain("前置");
    }

    @Test
    void raceEntryLineShowsGroupSizeSpeedAndDetailedAdjSenses() throws Exception {
        ListExportService service = loadedAll();
        ListExportService.ListEntry entry = service.search("race",
                new ListEntriesQuery("矮人", null, null, null, null, null), 50, 0).entries().get(0);

        String brief = service.entryLine("race", 1, entry, false);
        assertThat(brief).contains("1. 矮人（Dwarves）[未知来源]",
                "分组:概述", "体型:中型", "速度:20尺", "chunk_id: race_page_10_0000");
        assertThat(brief).doesNotContain("属性调整", "感官");

        String detailed = service.entryLine("race", 1, entry, true);
        assertThat(detailed).contains("属性调整:+2体质，+2感知，-2魅力", "感官:黑暗视觉60尺");
    }

    @Test
    void equipmentEntryLineShowsTypePriceWeight() throws Exception {
        ListExportService service = loadedAll();
        ListExportService.ListEntry entry = service.search("equipment",
                new ListEntriesQuery("镭武器", null, null, null, null, null), 50, 0).entries().get(0);

        String line = service.entryLine("equipment", 1, entry, false);

        assertThat(line).contains("1. 镭武器（Radium Weapon）[WS]",
                "类型:weapon", "价格:6,500 gp", "重量:12", "chunk_id: equipment_ws_0000");
    }

    @Test
    void nullOptionalFieldsDoNotThrow() throws Exception {
        write("feat_lists.json", Fixtures.featJsonWithNullOptionals());
        write("race_lists.json", Fixtures.raceJson());
        write("equipment_lists.json", Fixtures.equipmentJson());
        ListExportService service = service(tempDir.resolve("feat_lists.json").toString(),
                tempDir.resolve("race_lists.json").toString(),
                tempDir.resolve("equipment_lists.json").toString());
        service.load();

        ListExportService.EntryPage page = service.search("feat",
                new ListEntriesQuery(null, Map.of("hasPrerequisites", "false"), null, null, null, null), 50, 0);
        assertThat(page.total()).isEqualTo(2);
        String line = service.entryLine("feat", 1, page.entries().get(0), false);
        assertThat(line).doesNotContain("类别:", "| 前置", "chunk_id:");
        // chunk_id 为 null：降级合成 Document 不抛异常
        List<Document> docs = service.provenanceDocuments("feat", page.entries());
        assertThat(docs).hasSize(2);
        assertThat(docs.get(0).getMetadata().get("title")).isNotNull();
    }

    @Test
    void provenanceFetchesRealChunkOnHit() throws Exception {
        ListExportService service = loadedAll();
        SearchService searchService = mock(SearchService.class);
        Document real = Document.builder().text("原文").metadata(Map.of("chunk_id", "feat_page_1_0000")).build();
        when(searchService.getByChunkId("feat", "feat_page_1_0000")).thenReturn(real);
        ReflectionTestUtils.setField(service, "searchService", searchService);

        ListExportService.ListEntry entry = service.search("feat",
                new ListEntriesQuery("双武器", null, null, null, null, null), 50, 0).entries().get(0);
        List<Document> docs = service.provenanceDocuments("feat", List.of(entry));

        assertThat(docs).containsExactly(real);
    }

    @Test
    void provenanceFallsBackToSyntheticDocOnMiss() throws Exception {
        ListExportService service = loadedAll();
        SearchService searchService = mock(SearchService.class);
        when(searchService.getByChunkId("feat", "feat_page_1_0000")).thenReturn(null);
        ReflectionTestUtils.setField(service, "searchService", searchService);

        ListExportService.ListEntry entry = service.search("feat",
                new ListEntriesQuery("双武器", null, null, null, null, null), 50, 0).entries().get(0);
        List<Document> docs = service.provenanceDocuments("feat", List.of(entry));

        assertThat(docs).hasSize(1);
        assertThat(docs.get(0).getMetadata().get("title")).isEqualTo("双武器攻击");
        assertThat(docs.get(0).getMetadata().get("chunk_id")).isEqualTo("feat_page_1_0000");
        assertThat(docs.get(0).getMetadata().get("doc_id")).isEqualTo("page_1");
        assertThat(docs.get(0).getText()).contains("双武器攻击");
    }

    @Test
    void provenanceFallsBackWhenSearchServiceNotInjected() throws Exception {
        ListExportService service = loadedAll();
        ListExportService.ListEntry entry = service.search("feat",
                new ListEntriesQuery("双武器", null, null, null, null, null), 50, 0).entries().get(0);

        List<Document> docs = service.provenanceDocuments("feat", List.of(entry));

        assertThat(docs).hasSize(1);
        assertThat(docs.get(0).getMetadata().get("chunk_id")).isEqualTo("feat_page_1_0000");
    }

    private ListExportService loadedAll() throws Exception {
        write("feat_lists.json", Fixtures.featJson());
        write("race_lists.json", Fixtures.raceJson());
        write("equipment_lists.json", Fixtures.equipmentJson());
        ListExportService service = service(tempDir.resolve("feat_lists.json").toString(),
                tempDir.resolve("race_lists.json").toString(),
                tempDir.resolve("equipment_lists.json").toString());
        service.load();
        return service;
    }

    /** 装备 price_gp 夹具：含无标价条目（price_gp=null），验证 null 恒排最后与范围过滤 */
    private ListExportService loadedPriceEquipment() throws Exception {
        write("feat_lists.json", Fixtures.featJson());
        write("race_lists.json", Fixtures.raceJson());
        write("equipment_lists.json", Fixtures.equipmentPriceJson());
        ListExportService service = service(tempDir.resolve("feat_lists.json").toString(),
                tempDir.resolve("race_lists.json").toString(),
                tempDir.resolve("equipment_lists.json").toString());
        service.load();
        return service;
    }

    private void write(String name, String json) throws Exception {
        Files.writeString(tempDir.resolve(name), json, StandardCharsets.UTF_8);
    }

    private ListExportService service(String featPath, String racePath, String equipmentPath) {
        ListExportService service = new ListExportService();
        ReflectionTestUtils.setField(service, "featFilePath", featPath);
        ReflectionTestUtils.setField(service, "raceFilePath", racePath);
        ReflectionTestUtils.setField(service, "equipmentFilePath", equipmentPath);
        return service;
    }

    private static List<String> names(ListExportService.EntryPage page) {
        return page.entries().stream().map(ListExportService.ListEntry::name).toList();
    }

    /** 三模块 *_lists.json fixture（真实 snake_case 键 + 未知顶层字段容错 + 缺可选字段） */
    static final class Fixtures {

        static String featJson() {
            return """
                    {
                      "version": "1.0",
                      "generated_from": "vectorizer/output/专长/chunks.jsonl",
                      "source_fingerprint": "sha256:feat-test",
                      "category": "feat",
                      "excluded_component_types": [],
                      "entries": [
                        {"name": "双武器攻击", "name_en": "Two-Weapon Fighting", "book": "CRB",
                         "book_name_cn": "核心规则书", "component_type": "feat",
                         "chunk_id": "feat_page_1_0000", "doc_id": "page_1",
                         "aliases": ["TWO-WEAPON FIGHTING"], "prerequisites_raw": "敏捷15",
                         "feat_type": ["战斗"]},
                        {"name": "闪避", "name_en": "Dodge", "book": "CRB",
                         "book_name_cn": "核心规则书", "component_type": "feat",
                         "chunk_id": "feat_page_1_0001", "doc_id": "page_1",
                         "aliases": ["DODGE"], "prerequisites_raw": "", "feat_type": ["战斗"]},
                        {"name": "领导力", "name_en": "Leadership", "book": "APG",
                         "book_name_cn": "进阶玩家指南", "component_type": "feat",
                         "chunk_id": "feat_page_2_0000", "doc_id": "page_2",
                         "aliases": ["LEADERSHIP"], "prerequisites_raw": "角色等级7",
                         "feat_type": ["团队"]}
                      ],
                      "stats": {"total": 3, "by_book": {"CRB": 2, "APG": 1},
                                "by_component_type": {"feat": 3}, "chunk_id_null": 0}
                    }
                    """;
        }

        static String raceJson() {
            return """
                    {
                      "version": "1.0",
                      "source_fingerprint": "sha256:race-test",
                      "category": "race",
                      "entries": [
                        {"name": "矮人", "name_en": "Dwarves", "book": "?",
                         "book_name_cn": "未知来源", "component_type": "race_overview",
                         "chunk_id": "race_page_10_0000", "doc_id": "page_10",
                         "aliases": ["Dwarves"], "race_group": "概述",
                         "ability_adj": "+2体质，+2感知，-2魅力", "bio_type": "类人生物",
                         "size": "中型", "speed": "20尺", "senses": "黑暗视觉60尺"},
                        {"name": "精灵", "name_en": "Elves", "book": "?",
                         "book_name_cn": "未知来源", "component_type": "race_overview",
                         "chunk_id": "race_page_11_0000", "doc_id": "page_11",
                         "aliases": ["Elves"], "race_group": "元素",
                         "ability_adj": "+2敏捷，+2智力，-2体质", "bio_type": "精类",
                         "size": "中型", "speed": "30尺", "senses": "低光视觉"}
                      ],
                      "stats": {"total": 2, "by_book": {"?": 2}, "chunk_id_null": 0}
                    }
                    """;
        }

        static String equipmentJson() {
            return """
                    {
                      "version": "1.0",
                      "source_fingerprint": "sha256:equipment-test",
                      "category": "equipment",
                      "sections": [{"id": "equipment_intro"}],
                      "entries": [
                        {"name": "长剑", "name_en": "Longsword", "book": "CRB",
                         "book_name_cn": "核心规则书", "component_type": "weapon",
                         "chunk_id": "equipment_crb_0000", "doc_id": "CRB_武器",
                         "aliases": ["Longsword"], "price": "15 gp", "weight": "4", "slot": ""},
                        {"name": "镭武器", "name_en": "Radium Weapon", "book": "WS",
                         "book_name_cn": "PF官方漫画Worldscape", "component_type": "weapon",
                         "chunk_id": "equipment_ws_0000", "doc_id": "Worldscape_新武器",
                         "aliases": ["Radium Weapon"], "price": "6,500 gp", "weight": "12", "slot": ""},
                        {"name": "铁手套", "name_en": "Gauntlet", "book": "CRB",
                         "book_name_cn": "核心规则书", "component_type": "gear",
                         "chunk_id": "equipment_crb_0001", "doc_id": "CRB_冒险装备",
                         "aliases": ["Gauntlet"], "price": "2 gp", "weight": "1", "slot": "手部"}
                      ],
                      "stats": {"total": 3, "by_book": {"CRB": 2, "WS": 1}, "chunk_id_null": 0}
                    }
                    """;
        }

        /** AKN-025 跨侧固定夹具：力量法杖 price_gp=235000、chunk_id=equipment_page_222_0000 */
        static String equipmentPriceJson() {
            return """
                    {
                      "version": "1.0",
                      "source_fingerprint": "sha256:equipment-price-test",
                      "category": "equipment",
                      "entries": [
                        {"name": "低价药水", "name_en": "Cheap Potion", "book": "CRB",
                         "book_name_cn": "核心规则书", "component_type": "potion",
                         "chunk_id": "equipment_page_200_0000", "doc_id": "page_200",
                         "aliases": ["Cheap Potion"], "price": "10 gp", "price_gp": 10,
                         "weight": "0.5", "slot": ""},
                        {"name": "中价戒指", "name_en": "Mid Ring", "book": "CRB",
                         "book_name_cn": "核心规则书", "component_type": "ring",
                         "chunk_id": "equipment_page_210_0000", "doc_id": "page_210",
                         "aliases": ["Mid Ring"], "price": "1,000 gp", "price_gp": 1000,
                         "weight": "", "slot": "戒指"},
                        {"name": "力量法杖", "name_en": "Staff of Power", "book": "CRB",
                         "book_name_cn": "核心规则书", "component_type": "staff",
                         "chunk_id": "equipment_page_222_0000", "doc_id": "page_222",
                         "aliases": ["Staff of Power"], "price": "235,000 gp", "price_gp": 235000,
                         "weight": "10", "slot": ""},
                        {"name": "无价神器", "name_en": "Priceless Artifact", "book": "CRB",
                         "book_name_cn": "核心规则书", "component_type": "artifact",
                         "chunk_id": "equipment_page_230_0000", "doc_id": "page_230",
                         "aliases": ["Priceless Artifact"], "price": "—", "price_gp": null,
                         "weight": "", "slot": ""}
                      ],
                      "stats": {"total": 4, "by_book": {"CRB": 4}, "chunk_id_null": 0}
                    }
                    """;
        }

        static String featJsonWithNullOptionals() {
            return """
                    {
                      "version": "1.0",
                      "category": "feat",
                      "entries": [
                        {"name": "无前置专长", "name_en": "", "book": "CRB",
                         "book_name_cn": "核心规则书", "component_type": "feat",
                         "chunk_id": null, "doc_id": "page_9",
                         "aliases": [], "prerequisites_raw": null, "feat_type": []},
                        {"name": "普通专长", "book": "CRB", "component_type": "feat",
                         "doc_id": "page_9", "feat_type": null}
                      ],
                      "stats": {"total": 2, "chunk_id_null": 1}
                    }
                    """;
        }
    }
}
