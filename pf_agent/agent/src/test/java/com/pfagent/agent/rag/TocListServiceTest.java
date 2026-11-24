package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import com.pfagent.agent.rag.TocListService.TocEntry;
import com.pfagent.agent.rag.TocListService.TocNode;
import com.pfagent.agent.rag.TocListService.TocOverview;
import com.pfagent.agent.rag.TocListService.TocPage;
import com.pfagent.agent.rag.TocListService.TocPathStats;
import com.pfagent.agent.rag.TocListService.TocResult;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * TocListService 单元测试（F-008，批 A Task 7）
 *
 * 覆盖：四模块 + all 汇总；分段前缀（装备不命中装备附录）；
 * 空前缀根目录概览；分页/越界保留 total；模块不可用降级；
 * spell 条目路径来自条目自身 chunk join 而非列表页 source_toc_path；
 * 空路径条目不丢弃（pathStats 计入 empty）。
 */
class TocListServiceTest {

    @TempDir
    Path tempDir;

    // ---------- 分段匹配 ----------

    @Test
    void matchesIsSegmentAware() {
        assertThat(TocListService.matches("职业 → 核心职业 → 牧师 → 法术列表", "职业 → 核心职业")).isTrue();
        assertThat(TocListService.matches("职业 → 核心职业 → 牧师 → 法术列表",
                "职业 → 核心职业 → 牧师")).isTrue();
        assertThat(TocListService.matches("核心规则书 → 装备 → 武器", "核心规则书 → 装备")).isTrue();
        assertThat(TocListService.matches("核心规则书 → 装备附录", "核心规则书 → 装备")).isFalse();
        assertThat(TocListService.matches("核心规则书 → 装备", "")).isTrue();
        assertThat(TocListService.matches("", "核心规则书")).isFalse();
        // 末尾分隔符清理：前缀尾部箭头不参与匹配
        assertThat(TocListService.matches("核心规则书 → 装备", "核心规则书 → 装备 →")).isTrue();
    }

    // ---------- 四模块 + all ----------

    @Test
    void listsFourModulesAndAll() throws Exception {
        TocListService service = loadedAll();

        TocPage feat = page(service.listByToc("feat", "专长", 50, 0));
        assertThat(feat.total()).isEqualTo(3);
        assertThat(feat.items()).extracting(TocEntry::name)
                .containsExactlyInAnyOrder("双武器攻击", "闪避", "领导力");
        assertThat(feat.items()).allSatisfy(e -> {
            assertThat(e.module()).isEqualTo("feat");
            assertThat(e.componentType()).isEqualTo("feat");
            assertThat(e.tocPath()).startsWith("专长 → ");
        });

        TocPage race = page(service.listByToc("race", "种族", 50, 0));
        assertThat(race.total()).isEqualTo(2);
        assertThat(race.items()).extracting(TocEntry::name).containsExactlyInAnyOrder("矮人", "精灵");

        TocPage equipment = page(service.listByToc("equipment", "核心规则书 → 装备", 50, 0));
        assertThat(equipment.total()).isEqualTo(2);
        assertThat(equipment.items()).extracting(TocEntry::chunkId)
                .containsExactlyInAnyOrder("equip_1", "equip_2");

        TocPage spell = page(service.listByToc("spell", "法术", 50, 0));
        assertThat(spell.total()).isEqualTo(2);
        assertThat(spell.items()).extracting(TocEntry::name).containsExactlyInAnyOrder("燃烧之手", "祝福术");
        assertThat(spell.items()).allSatisfy(e -> assertThat(e.module()).isEqualTo("spell"));

        // all：同一前缀跨模块汇总（此处仅装备命中）
        TocPage all = page(service.listByToc("all", "核心规则书", 50, 0));
        assertThat(all.total()).isEqualTo(3);
        assertThat(all.items()).extracting(TocEntry::module).containsOnly("equipment");
    }

    @Test
    void equipmentPrefixStopsAtSegmentBoundary() throws Exception {
        TocListService service = loadedAll();

        TocPage page = page(service.listByToc("equipment", "核心规则书 → 装备", 50, 0));

        assertThat(page.items()).extracting(TocEntry::name)
                .containsExactlyInAnyOrder("长剑", "链甲")
                .doesNotContain("匕首附录");
        assertThat(page.total()).isEqualTo(2);
    }

    // ---------- 空前缀概览 ----------

    @Test
    void emptyPrefixReturnsRootOverview() throws Exception {
        TocListService service = loadedAll();

        TocOverview overview = overview(service.listByToc("all", "  ", 50, 0));

        assertThat(overview.nodes()).extracting(TocNode::segment)
                .contains("专长", "种族", "核心规则书", "法术");
        TocNode equipmentRoot = overview.nodes().stream()
                .filter(n -> "equipment".equals(n.module()) && "核心规则书".equals(n.segment()))
                .findFirst().orElseThrow();
        // 装备 3 条有路径条目（空路径条目不进入目录概览）
        assertThat(equipmentRoot.count()).isEqualTo(3);
        // 空路径不计入概览，但计入 pathStats（见 pathStatsCountsEmptyPaths）
        assertThat(overview.total()).isEqualTo(10);

        TocOverview featOnly = overview(service.listByToc("feat", "", 50, 0));
        assertThat(featOnly.nodes()).extracting(TocNode::segment).containsExactly("专长");
        assertThat(featOnly.nodes().get(0).count()).isEqualTo(3);
    }

    // ---------- 分页 / 越界 ----------

    @Test
    void paginatesAndKeepsTotalOnOutOfRange() throws Exception {
        TocListService service = loadedAll();

        TocPage first = page(service.listByToc("feat", "专长 → 战斗专长", 1, 0));
        assertThat(first.total()).isEqualTo(2);
        assertThat(first.items()).hasSize(1);
        assertThat(first.offset()).isZero();
        assertThat(first.limit()).isEqualTo(1);
        assertThat(first.hasMore()).isTrue();
        assertThat(first.capped()).isFalse();

        TocPage second = page(service.listByToc("feat", "专长 → 战斗专长", 1, 1));
        assertThat(second.items()).hasSize(1);
        assertThat(second.hasMore()).isFalse();

        TocPage outOfRange = page(service.listByToc("feat", "专长 → 战斗专长", 50, 99));
        assertThat(outOfRange.items()).isEmpty();
        assertThat(outOfRange.total()).isEqualTo(2);
        assertThat(outOfRange.hasMore()).isFalse();
        assertThat(outOfRange.capped()).isFalse();

        TocPage defaults = page(service.listByToc("feat", "专长", null, null));
        assertThat(defaults.limit()).isEqualTo(50);
        assertThat(defaults.offset()).isZero();
        assertThat(defaults.items()).hasSize(3);

        // limit=0 不得产生零步进翻页：钳为 1
        TocPage zeroLimit = page(service.listByToc("feat", "专长", 0, 0));
        assertThat(zeroLimit.limit()).isEqualTo(1);
        assertThat(zeroLimit.items()).hasSize(1);
        assertThat(zeroLimit.offset() + zeroLimit.items().size()).isEqualTo(1);
    }

    // ---------- 降级 ----------

    @Test
    void unavailableModuleDegradesWithoutAffectingOthers() throws Exception {
        ListExportService listService = loadedListExport(true, false);
        SpellListService spellService = spellService(tempDir.resolve("missing-spell.json").toString(),
                tempDir.resolve("missing-union.json").toString());
        TocListService service = toc(listService, spellService);

        TocPage equipment = page(service.listByToc("equipment", "核心规则书 → 装备", 50, 0));
        assertThat(equipment.items()).isEmpty();
        assertThat(equipment.total()).isZero();

        TocPage spell = page(service.listByToc("spell", "法术", 50, 0));
        assertThat(spell.items()).isEmpty();
        assertThat(spell.total()).isZero();

        TocPage feat = page(service.listByToc("feat", "专长", 50, 0));
        assertThat(feat.total()).isEqualTo(3);

        TocOverview overview = overview(service.listByToc("all", "", 50, 0));
        assertThat(overview.nodes()).extracting(TocNode::module)
                .containsOnly("feat", "race");
        TocPathStats equipmentStats = service.pathStats("equipment");
        assertThat(equipmentStats.rawTotal()).isZero();
        assertThat(equipmentStats.uniqueTotal()).isZero();
        assertThat(service.knownModules()).containsExactly("feat", "race");

        // 未知模块：空结果，且可用模块仍可提示
        TocPage unknown = page(service.listByToc("nope", "专长", 50, 0));
        assertThat(unknown.items()).isEmpty();
        assertThat(unknown.total()).isZero();
    }

    // ---------- spell 条目路径 ----------

    @Test
    void spellEntriesUseOwnChunkPathNotListPage() throws Exception {
        TocListService service = loadedAll();

        TocPage page = page(service.listByToc("spell", "法术 → 奥术", 50, 0));

        assertThat(page.total()).isEqualTo(1);
        TocEntry entry = page.items().get(0);
        assertThat(entry.name()).isEqualTo("燃烧之手");
        assertThat(entry.chunkId()).isEqualTo("spell_c1");
        assertThat(entry.tocPath()).isEqualTo("法术 → 奥术 → 1环 → 燃烧之手");
        // 列表页 source_toc_path 不冒充条目路径
        assertThat(entry.tocPath()).doesNotContain("法术列表");
        assertThat(page.items()).extracting(TocEntry::tocPath).noneMatch(p -> p.contains("法术列表"));

        // 空路径条目保留并计入 raw 统计（不丢弃）；门面去重后 uniqueTotal 单独报告
        TocPathStats stats = service.pathStats("spell");
        assertThat(stats.rawTotal()).isEqualTo(4);
        assertThat(stats.uniqueTotal()).isEqualTo(4);
        assertThat(stats.nonEmptyPath()).isEqualTo(2);
        assertThat(stats.emptyPath()).isEqualTo(2);
        // 空路径条目不可被任何非空前缀命中
        assertThat(page.items()).allSatisfy(item -> assertThat(item.tocPath()).isNotEmpty());
        assertThat(TocListService.matches("", "法术")).isFalse();
    }

    @Test
    void crossClassDuplicateKeepsNonEmptyTocPath() throws Exception {
        Path spellFile = write("spell_lists.json", Fixtures.spellDuplicateChunkJson());
        SpellListService spellService = spellService(spellFile.toString(),
                tempDir.resolve("no-union.json").toString());
        TocListService service = toc(null, spellService);

        TocPage page = page(service.listByToc("spell", "法术 → 神术", 50, 0));

        assertThat(page.total()).isEqualTo(1);
        assertThat(page.items().get(0).chunkId()).isEqualTo("spell_dup");
        assertThat(page.items().get(0).tocPath()).isEqualTo("法术 → 神术 → 1环 → 重复法术");
        // raw=2（跨职业两行），unique=1（同 chunk 去重）；去重保留非空路径
        TocPathStats stats = service.pathStats("spell");
        assertThat(stats.rawTotal()).isEqualTo(2);
        assertThat(stats.uniqueTotal()).isEqualTo(1);
        assertThat(stats.nonEmptyPath()).isEqualTo(1);
        assertThat(stats.emptyPath()).isEqualTo(1);
    }

    @Test
    void spellListPageSourceTocPathUnchanged() throws Exception {
        Path spellFile = write("spell_lists.json", Fixtures.spellOfficialJson());
        SpellListService spellService = spellService(spellFile.toString(),
                tempDir.resolve("no-union.json").toString());

        Document doc = spellService.listPageDocument("法师");
        assertThat(doc.getMetadata().get("tocPath")).isEqualTo("职业 → 核心职业 → 法师 → 法术列表");

        TocListService service = toc(null, spellService);
        assertThat(page(service.listByToc("spell", "法术", 50, 0)).items())
                .extracting(TocEntry::tocPath)
                .noneMatch(path -> path.contains("法术列表"));
    }

    @Test
    void spellUnionEntriesResolvePathByChunkId() throws Exception {
        Path spellFile = write("spell_lists.json", Fixtures.spellOfficialJson());
        Path unionFile = write("spell_lists_union.json", Fixtures.union11Json());
        SpellListService spellService = spellService(spellFile.toString(), unionFile.toString());
        TocListService service = toc(null, spellService);

        TocPage page = page(service.listByToc("spell", "法术 → 奥术", 50, 0));

        assertThat(page.total()).isEqualTo(1);
        assertThat(page.items().get(0).name()).isEqualTo("燃烧之手");
        // union 折叠条目按自身 chunk_id 回连官方清单条目 toc_path
        assertThat(page.items().get(0).tocPath()).isEqualTo("法术 → 奥术 → 1环 → 燃烧之手");

        // union 派生条目无可用路径：保留为空、计入 empty
        TocPathStats stats = service.pathStats("spell");
        assertThat(stats.rawTotal()).isEqualTo(2);
        assertThat(stats.uniqueTotal()).isEqualTo(2);
        assertThat(stats.nonEmptyPath()).isEqualTo(1);
        assertThat(stats.emptyPath()).isEqualTo(1);
    }

    @Test
    void unionOwnTocPathWinsOverOfficialRejoin() throws Exception {
        Path spellFile = write("spell_lists.json", Fixtures.spellOfficialJson());
        Path unionFile = write("spell_lists_union.json",
                Fixtures.union11JsonWithOwnTocPath("法术 → 秘法 → 1环 → 燃烧之手"));
        SpellListService spellService = spellService(spellFile.toString(), unionFile.toString());
        TocListService service = toc(null, spellService);

        TocPage page = page(service.listByToc("spell", "法术 → 秘法", 50, 0));

        assertThat(page.total()).isEqualTo(1);
        assertThat(page.items().get(0).tocPath()).isEqualTo("法术 → 秘法 → 1环 → 燃烧之手");
        // 官方回连路径未被采用
        assertThat(page(service.listByToc("spell", "法术 → 奥术", 50, 0)).total()).isZero();
    }

    // ---------- 未命中 / 统计 ----------

    @Test
    void unmatchedPrefixReturnsEmptyPageAndAncestorHint() throws Exception {
        TocListService service = loadedAll();

        TocPage page = page(service.listByToc("equipment", "核心规则书 → 装备 → 不存在", 50, 0));
        assertThat(page.items()).isEmpty();
        assertThat(page.total()).isZero();

        assertThat(service.ancestorPrefixes("equipment", "核心规则书 → 装备 → 不存在"))
                .containsExactly("核心规则书 → 装备", "核心规则书");
    }

    @Test
    void pathStatsCountsEmptyPaths() throws Exception {
        TocListService service = loadedAll();

        TocPathStats feat = service.pathStats("feat");
        assertThat(feat.rawTotal()).isEqualTo(4);
        assertThat(feat.uniqueTotal()).isEqualTo(4);
        assertThat(feat.nonEmptyPath()).isEqualTo(3);
        assertThat(feat.emptyPath()).isEqualTo(1);

        TocPathStats all = service.pathStats("all");
        assertThat(all.rawTotal()).isEqualTo(4 + 2 + 4 + 4);
        assertThat(all.uniqueTotal()).isEqualTo(4 + 2 + 4 + 4);
        assertThat(all.nonEmptyPath() + all.emptyPath()).isEqualTo(all.rawTotal());
        assertThat(all.emptyPath()).isEqualTo(1 + 0 + 1 + 2);
    }

    // ---------- 畸形产物 ----------

    @Test
    void nullEntryIsFilteredWithoutDroppingModule() throws Exception {
        ListExportService listService = loadListExport(new ListExportService(),
                Fixtures.featJsonWithNullEntry(), Fixtures.raceJson(), Fixtures.equipmentJson());
        TocListService service = toc(listService, spellService(
                tempDir.resolve("missing-spell.json").toString(),
                tempDir.resolve("missing-union.json").toString()));

        TocPage feat = page(service.listByToc("feat", "专长", 50, 0));

        assertThat(feat.total()).isEqualTo(1);
        assertThat(feat.items().get(0).name()).isEqualTo("双武器攻击");
        assertThat(service.pathStats("feat").rawTotal()).isEqualTo(1);
        // 其他模块不受影响
        assertThat(page(service.listByToc("equipment", "核心规则书 → 装备", 50, 0)).total()).isEqualTo(2);
    }

    @Test
    void malformedSpellLevelsDegradeWithoutThrowing() throws Exception {
        Path spellFile = write("spell_lists.json", Fixtures.spellJsonWithMalformedLevels());
        SpellListService spellService = spellService(spellFile.toString(),
                tempDir.resolve("missing-union.json").toString());
        TocListService service = toc(null, spellService);

        assertThat(spellService.isAvailable()).isTrue();
        TocPage page = page(service.listByToc("spell", "法术", 50, 0));
        assertThat(page.items()).isEmpty();
        assertThat(page.total()).isZero();
        assertThat(service.pathStats("spell").rawTotal()).isZero();
    }

    @Test
    void runtimeFailureInOneModuleDegradesOnlyThatModule() throws Exception {
        ListExportService boom = new ListExportService() {
            @Override
            public List<ListExportService.ListEntry> entries(String module) {
                if ("feat".equals(module)) {
                    throw new IllegalStateException("boom");
                }
                return super.entries(module);
            }
        };
        loadListExport(boom, Fixtures.featJson(), Fixtures.raceJson(), Fixtures.equipmentJson());
        TocListService service = toc(boom, null);

        TocPage feat = page(service.listByToc("feat", "专长", 50, 0));
        assertThat(feat.items()).isEmpty();
        assertThat(feat.total()).isZero();

        assertThat(page(service.listByToc("race", "种族", 50, 0)).total()).isEqualTo(2);
        assertThat(page(service.listByToc("equipment", "核心规则书 → 装备", 50, 0)).total()).isEqualTo(2);
        assertThat(service.pathStats("feat").rawTotal()).isZero();
    }

    // ---------- fixtures ----------

    private TocListService loadedAll() throws Exception {
        return toc(loadedListExport(true, true),
                spellService(write("spell_lists.json", Fixtures.spellOfficialJson()).toString(),
                        tempDir.resolve("no-union.json").toString()));
    }

    private ListExportService loadedListExport(boolean race, boolean equipment)
            throws Exception {
        return loadListExport(new ListExportService(), Fixtures.featJson(),
                race ? Fixtures.raceJson() : null,
                equipment ? Fixtures.equipmentJson() : null);
    }

    private ListExportService loadListExport(ListExportService service,
                                             String featJson, String raceJson, String equipmentJson)
            throws Exception {
        Path featFile = write("feat_lists.json", featJson);
        Path raceFile = raceJson == null ? tempDir.resolve("missing-race.json")
                : write("race_lists.json", raceJson);
        Path equipmentFile = equipmentJson == null ? tempDir.resolve("missing-equipment.json")
                : write("equipment_lists.json", equipmentJson);
        ReflectionTestUtils.setField(service, "featFilePath", featFile.toString());
        ReflectionTestUtils.setField(service, "raceFilePath", raceFile.toString());
        ReflectionTestUtils.setField(service, "equipmentFilePath", equipmentFile.toString());
        service.load();
        return service;
    }

    private TocListService toc(ListExportService listService, SpellListService spellService) {
        TocListService service = new TocListService();
        if (listService != null) {
            ReflectionTestUtils.setField(service, "listExportService", listService);
        }
        if (spellService != null) {
            ReflectionTestUtils.setField(service, "spellListService", spellService);
        }
        service.rebuildIndex();
        return service;
    }

    private SpellListService spellService(String filePath, String unionFilePath) {
        SpellListService service = new SpellListService();
        ReflectionTestUtils.setField(service, "filePath", filePath);
        ReflectionTestUtils.setField(service, "unionFilePath", unionFilePath);
        service.load();
        return service;
    }

    private Path write(String name, String json) throws Exception {
        Path file = tempDir.resolve(name);
        Files.writeString(file, json, StandardCharsets.UTF_8);
        return file;
    }

    private static TocPage page(TocResult result) {
        assertThat(result).isInstanceOf(TocPage.class);
        return (TocPage) result;
    }

    private static TocOverview overview(TocResult result) {
        assertThat(result).isInstanceOf(TocOverview.class);
        return (TocOverview) result;
    }

    static final class Fixtures {

        static String featJson() {
            return """
                    {"category":"feat","entries":[
                      {"name":"双武器攻击","book":"CRB","component_type":"feat",
                       "chunk_id":"feat_1","toc_path":"专长 → 战斗专长"},
                      {"name":"闪避","book":"CRB","component_type":"feat",
                       "chunk_id":"feat_2","toc_path":"专长 → 战斗专长"},
                      {"name":"领导力","book":"APG","component_type":"feat",
                       "chunk_id":"feat_3","toc_path":"专长 → 团队专长"},
                      {"name":"无路径专长","book":"APG","component_type":"feat",
                       "chunk_id":"feat_4","toc_path":""}
                    ]}
                    """;
        }

        static String featJsonWithNullEntry() {
            return """
                    {"category":"feat","entries":[
                      null,
                      {"name":"双武器攻击","book":"CRB","component_type":"feat",
                       "chunk_id":"feat_1","toc_path":"专长 → 战斗专长"}
                    ]}
                    """;
        }

        static String raceJson() {
            return """
                    {"category":"race","entries":[
                      {"name":"矮人","book":"CRB","component_type":"race_overview",
                       "chunk_id":"race_1","toc_path":"种族 → 核心种族 → 矮人"},
                      {"name":"精灵","book":"CRB","component_type":"race_overview",
                       "chunk_id":"race_2","toc_path":"种族 → 核心种族 → 精灵"}
                    ]}
                    """;
        }

        static String equipmentJson() {
            return """
                    {"category":"equipment","entries":[
                      {"name":"长剑","book":"CRB","component_type":"weapon",
                       "chunk_id":"equip_1","toc_path":"核心规则书 → 装备 → 武器"},
                      {"name":"链甲","book":"CRB","component_type":"armor",
                       "chunk_id":"equip_2","toc_path":"核心规则书 → 装备 → 防具"},
                      {"name":"匕首附录","book":"CRB","component_type":"weapon",
                       "chunk_id":"equip_3","toc_path":"核心规则书 → 装备附录 → 武器"},
                      {"name":"无路径装备","book":"CRB","component_type":"weapon",
                       "chunk_id":"equip_4","toc_path":""}
                    ]}
                    """;
        }

        static String spellOfficialJson() {
            return """
                    {"version":"1.0","classes":{
                      "法师":{
                        "aliases":[],"source_page":"核心职业/法师/page_65.md",
                        "source_toc_path":"职业 → 核心职业 → 法师 → 法术列表",
                        "source_excerpt":"法师法术列表","list_chunk_id":"spell_page_65_0001",
                        "levels":{
                          "1":[
                            {"cn":"燃烧之手","en":"Burning Hands","book":"CRB",
                             "chunk_id":"spell_c1","toc_path":"法术 → 奥术 → 1环 → 燃烧之手"},
                            {"cn":"魔法警报","en":"Alarm","book":"CRB",
                             "chunk_id":"spell_c2","toc_path":""},
                            {"cn":"七彩喷射","en":"Color Spray","book":"CRB",
                             "chunk_id":null,"toc_path":""}
                          ]
                        }
                      },
                      "牧师":{
                        "aliases":[],"source_page":"核心职业/牧师/page_40.md",
                        "source_toc_path":"职业 → 核心职业 → 牧师 → 法术列表",
                        "source_excerpt":"牧师法术列表","list_chunk_id":"spell_page_40_0001",
                        "levels":{
                          "1":[
                            {"cn":"祝福术","en":"Bless","book":"CRB",
                             "chunk_id":"spell_c3","toc_path":"法术 → 神术 → 1环 → 祝福术"}
                          ]
                        }
                      }
                    }}
                    """;
        }

        /** 同一 chunk_id 跨职业出现：法师行路径为空，牧师行有路径（去重应保留非空）。 */
        static String spellDuplicateChunkJson() {
            return """
                    {"version":"1.0","classes":{
                      "法师":{
                        "aliases":[],"source_page":"核心职业/法师/page_65.md",
                        "source_toc_path":"职业 → 核心职业 → 法师 → 法术列表",
                        "levels":{"1":[
                          {"cn":"重复法术","en":"Duplicate","book":"CRB",
                           "chunk_id":"spell_dup","toc_path":""}
                        ]}
                      },
                      "牧师":{
                        "aliases":[],"source_page":"核心职业/牧师/page_40.md",
                        "source_toc_path":"职业 → 核心职业 → 牧师 → 法术列表",
                        "levels":{"1":[
                          {"cn":"重复法术","en":"Duplicate","book":"CRB",
                           "chunk_id":"spell_dup","toc_path":"法术 → 神术 → 1环 → 重复法术"}
                        ]}
                      }
                    }}
                    """;
        }

        /** 可解析但畸形：levels 值 null、环级数组含 null 元素，加载不得抛异常。 */
        static String spellJsonWithMalformedLevels() {
            return """
                    {"version":"1.0","classes":{
                      "法师":{
                        "aliases":[],"source_page":"核心职业/法师/page_65.md",
                        "source_toc_path":"职业 → 核心职业 → 法师 → 法术列表",
                        "levels":{"1":[null],"2":null}
                      }
                    }}
                    """;
        }

        /** union 1.1：官方条目按 chunk_id 回连官方清单 toc_path；派生条目无路径。 */
        static String union11Json() {
            return union11Json(null);
        }

        /** union 1.1：官方条目自带 toc_path，应优先于官方清单回连值。 */
        static String union11JsonWithOwnTocPath(String tocPath) {
            return union11Json(tocPath);
        }

        private static String union11Json(String officialTocPath) {
            String tocField = officialTocPath == null ? ""
                    : "\"toc_path\":" + quote(officialTocPath) + ",";
            String official = """
                    {"cn":"燃烧之手","en":"Burning Hands","book":"CRB","chunk_id":"spell_c1",
                     %s
                     "source":"official_list",
                     "sources":[{"book":"CRB","chunk_id":"spell_c1","source":"official_list",
                                 "matched_by":"title"}]}""".formatted(tocField);
            String derived = """
                    {"cn":"法师密派生","en":"Wizard Secret","book":"APG","chunk_id":"spell_d1",
                     "source":"derived","level_evidence":"spell_level: 法师 1",
                     "matched_by":"derived_new",
                     "sources":[{"book":"APG","chunk_id":"spell_d1","source":"derived",
                                 "level_evidence":"spell_level: 法师 1",
                                 "matched_by":"derived_new"}]}""";
            StringBuilder sb = new StringBuilder(
                    "{\"version\":\"1.1\",\"classes\":{\"法师\":{"
                            + "\"source_page\":\"核心职业/法师/page_65.md\",\"aliases\":[],"
                            + "\"official_list\":true,\"levels\":{");
            appendLevels(sb, official, derived);
            sb.append("}},\"牧师\":{"
                            + "\"source_page\":\"核心职业/牧师/page_40.md\",\"aliases\":[],"
                            + "\"official_list\":true,\"levels\":{");
            appendLevels(sb, null, null);
            sb.append("}}}}");
            return sb.toString();
        }

        private static String quote(String value) {
            return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
        }

        private static void appendLevels(StringBuilder sb, String official, String derived) {
            for (int level = 0; level <= 9; level++) {
                sb.append('"').append(level).append("\":[");
                if (level == 1 && official != null) {
                    sb.append(official).append(',').append(derived);
                }
                sb.append(']');
                if (level < 9) {
                    sb.append(',');
                }
            }
        }
    }
}
