package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import ch.qos.logback.core.read.ListAppender;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * ClassTableService 单元测试（J5 F-019，D3）
 *
 * 覆盖加载 + 查询契约：
 *  - 加载成功：规范职业映射 + 覆盖/缺口名单（coverage.parsed/missing）
 *  - resolve：自身索引（规范名/别名/英文大小写）+ 二级兜底（SpellListService.resolve）；
 *    未知/空/空白返回 null
 *  - formatRow：单行 BAB/豁免/特殊/每日法术位；spells null 环位省略；无法术表无 spells 段
 *  - formatTable：level 省略=全表（max_level 行）
 *  - provenanceDocument：searchService 为 null（单测）→ 降级合成 Document 且含 chunk_id/doc_id
 *  - 缺文件 / 解析失败降级：isAvailable=false、查询返回可读空态、不抛异常
 *  - 未知字段容错（bab_attacks/extras/stats 等被 ignoreUnknown 忽略）
 */
class ClassTableServiceTest {

    @TempDir
    Path tempDir;

    /** 加载成功：职业映射 + 缺口名单；未知字段（bab_attacks/extras/stats）被容错忽略 */
    @Test
    void loadBuildsClassesAndMissingList() throws Exception {
        ClassTableService service = loaded(Fixtures.validJson());

        assertThat(service.isAvailable()).isTrue();
        // knownClasses 为 Unicode 码点序（战 U+6218 < 法 U+6CD5 < 牧 U+7267 < 骑 U+9A91），非拼音序
        assertThat(service.knownClasses()).containsExactly("战士", "法师", "牧师", "骑将");
        assertThat(service.missingClasses()).containsExactly("催眠师");
        assertThat(service.maxLevel("法师")).isEqualTo(20);
        assertThat(service.hasSpellTable("法师")).isTrue();
        assertThat(service.hasSpellTable("战士")).isFalse();
    }

    /** resolve：规范名/自身别名（含英文大小写混用）命中；未知名返回 null；trim 生效 */
    @Test
    void resolveViaOwnIndexIncludingLowercaseEnglish() throws Exception {
        ClassTableService service = loaded(Fixtures.validJson());

        assertThat(service.resolve("法师")).isEqualTo("法师");
        assertThat(service.resolve("  法师  ")).isEqualTo("法师");
        assertThat(service.resolve("WIZARD")).isEqualTo("法师");
        assertThat(service.resolve("wizard")).isEqualTo("法师");
        assertThat(service.resolve("魔战士")).isNull();
    }

    /** QA-J5-1：coverage.resolved_via 消费——「骑士」经映射解析到收录键「骑将」 */
    @Test
    void resolveConsumesResolvedViaMapping() throws Exception {
        ClassTableService service = loaded(Fixtures.validJson());

        assertThat(service.resolve("骑士")).isEqualTo("骑将");
        // 规范键自身仍直查
        assertThat(service.resolve("骑将")).isEqualTo("骑将");
        // resolved_via 目标不在 classes 内 → 不硬匹配，返回 null
        assertThat(service.resolve("不存在的映射")).isNull();
    }

    /** QA-J5-2：别名撞车时首登记优先并输出 warn 日志 */
    @Test
    void aliasCollisionKeepsFirstRegistrationAndWarns() throws Exception {
        ch.qos.logback.classic.Logger logger =
                (ch.qos.logback.classic.Logger) org.slf4j.LoggerFactory.getLogger(ClassTableService.class);
        ListAppender<ch.qos.logback.classic.spi.ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            ClassTableService service = loaded(Fixtures.collidingAliasesJson());

            // 撞名别名「剑士」首登记优先（指向战士），后注册的法师不覆盖
            assertThat(service.resolve("剑士")).isEqualTo("战士");
            assertThat(appender.list)
                    .anyMatch(e -> e.getFormattedMessage().contains("别名撞名") && e.getFormattedMessage().contains("剑士"));
        } finally {
            logger.detachAppender(appender);
        }
    }

    /** resolve null / 空白返回 null（不抛） */
    @Test
    void resolveNullAndBlankReturnsNull() throws Exception {
        ClassTableService service = loaded(Fixtures.validJson());

        assertThat(service.resolve(null)).isNull();
        assertThat(service.resolve("  ")).isNull();
    }

    /** 二级兜底：自身索引 miss 时借 SpellListService.resolve 解析"诗人"→吟游诗人 */
    @Test
    void resolveFallsBackToSpellListService() throws Exception {
        SpellListService spellListService = new SpellListService() {
            @Override
            public String resolve(String className) {
                return "诗人".equals(className) ? "吟游诗人" : null;
            }
        };
        ClassTableService service = loaded(Fixtures.validJsonWithBard());
        ReflectionTestUtils.setField(service, "spellListService", spellListService);

        assertThat(service.resolve("诗人")).isEqualTo("吟游诗人");
        // 兜底结果不在 classes 内 → 未知
        assertThat(service.resolve("不存在")).isNull();
    }

    /** formatRow：单行含 BAB/豁免/特殊/每日法术位；数值与 fixture 逐字段一致 */
    @Test
    void formatRowReturnsAllFieldsMatchingFixture() throws Exception {
        ClassTableService service = loaded(Fixtures.validJson());

        String row = service.formatRow("法师", 2);

        assertThat(row).contains("「法师」等级 2", "BAB +1", "强韧 +0", "反射 +0", "意志 +3");
        assertThat(row).contains("特殊：无");
        assertThat(row).contains("每日法术：0环4、1环2");
    }

    /** formatRow：特殊能力列表逐条列出 */
    @Test
    void formatRowListsSpecialAbilities() throws Exception {
        ClassTableService service = loaded(Fixtures.validJson());

        String row = service.formatRow("法师", 1);

        assertThat(row).contains("特殊：奥术联结、法术学派、戏法、抄写卷轴");
    }

    /** formatRow：spells 中 null 环位省略（不输出 "—环—"）；全 null 时给占位 */
    @Test
    void formatRowOmitsNullSpellSlots() throws Exception {
        ClassTableService service = loaded(Fixtures.validJson());

        String row = service.formatRow("法师", 1);

        assertThat(row).contains("1环1");
        assertThat(row).doesNotContain("9环");
    }

    /** formatRow：无法术表职业（战士）不输出每日法术段 */
    @Test
    void formatRowNoSpellTableOmitsSpells() throws Exception {
        ClassTableService service = loaded(Fixtures.validJson());

        String row = service.formatRow("战士", 5);

        assertThat(row).contains("「战士」等级 5", "BAB +5");
        assertThat(row).doesNotContain("每日法术");
    }

    /** formatRow：领域加值字符串（牧师 "4+1"）按原文透出，不做计算 */
    @Test
    void formatRowPassesThroughDomainBonusSpellStrings() throws Exception {
        ClassTableService service = loaded(Fixtures.validJson());

        String row = service.formatRow("牧师", 20);

        assertThat(row).contains("每日法术：1环4+1、2环4+1", "9环4+1");
    }

    /** formatTable：level 省略=全表（max_level 行，每行带等级号） */
    @Test
    void formatTableReturnsAllLevels() throws Exception {
        ClassTableService service = loaded(Fixtures.validJson());

        String table = service.formatTable("法师");

        assertThat(table).contains("「法师」成长表（1~20 级）");
        assertThat(table.lines().filter(l -> l.contains("「法师」等级 ")).count()).isEqualTo(20);
    }

    /** provenanceDocument：searchService 未注入（点查不可用）→ 降级合成 Document 含统一溯源键 */
    @Test
    void provenanceDocumentFallsBackToSyntheticDoc() throws Exception {
        ClassTableService service = loaded(Fixtures.validJson());

        Document doc = service.provenanceDocument("法师");

        assertThat(doc.getMetadata().get("title")).isEqualTo("法师职业成长表");
        assertThat(doc.getMetadata().get("chunk_id")).isEqualTo("class_page_66_0001");
        assertThat(doc.getMetadata().get("doc_id")).isEqualTo("核心职业/法师/page_66.md");
        assertThat(doc.getText()).contains("法师职业成长表");
    }

    /** 文件缺失降级：isAvailable=false、查询可读空态、不抛异常 */
    @Test
    void missingFileDegradesGracefully() {
        ClassTableService service = service(tempDir.resolve("nope.json").toString());

        service.load();

        assertThat(service.isAvailable()).isFalse();
        assertThat(service.knownClasses()).isEmpty();
        assertThat(service.resolve("法师")).isNull();
        assertThat(service.formatRow("法师", 1)).contains("尚未加载");
        assertThat(service.formatTable("法师")).contains("尚未加载");
        assertThat(service.provenanceDocument("法师").getText()).isEmpty();
    }

    /** 解析失败降级：文件存在但 JSON 非法 → available=false，不抛 */
    @Test
    void malformedFileDegradesGracefully() throws Exception {
        Path bad = tempDir.resolve("bad.json");
        Files.writeString(bad, "{ this is not json ", StandardCharsets.UTF_8);
        ClassTableService service = service(bad.toString());

        service.load();

        assertThat(service.isAvailable()).isFalse();
        assertThat(service.resolve("法师")).isNull();
    }

    /** 构造已加载指定 JSON 文本的 service */
    private ClassTableService loaded(String json) throws Exception {
        Path file = tempDir.resolve("class_tables.json");
        Files.writeString(file, json, StandardCharsets.UTF_8);
        ClassTableService service = service(file.toString());
        service.load();
        return service;
    }

    private ClassTableService service(String filePath) {
        ClassTableService service = new ClassTableService();
        ReflectionTestUtils.setField(service, "filePath", filePath);
        return service;
    }

    /** class_tables.json 结构 fixture（真实 snake_case 键 + 字符串等级键 + 未知字段容错） */
    static final class Fixtures {

        static String validJson() {
            return """
                    {
                      "version": "1.0",
                      "generated_from": "职业概览页 成长表（测试 fixture）",
                      "classes": {
                        "法师": {
                          "aliases": ["Wizard"],
                          "source_chunk_id": "class_page_66_0001",
                          "source_doc_id": "核心职业/法师/page_66.md",
                          "max_level": 20,
                          "has_spell_table": true,
                          "spell_levels": 9,
                          "levels": {
                            "1": {"bab": "+0", "bab_attacks": [0], "fort": "+0", "ref": "+0", "will": "+2",
                                  "special": ["奥术联结", "法术学派", "戏法", "抄写卷轴"],
                                  "spells": {"0": 3, "1": 1, "2": null, "3": null, "4": null, "5": null, "6": null, "7": null, "8": null, "9": null},
                                  "extras": {}},
                            "2": {"bab": "+1", "bab_attacks": [1], "fort": "+0", "ref": "+0", "will": "+3",
                                  "spells": {"0": 4, "1": 2, "2": null, "3": null, "4": null, "5": null, "6": null, "7": null, "8": null, "9": null}}
                          }
                        },
                        "战士": {
                          "aliases": ["Fighter"],
                          "source_chunk_id": "class_page_56_0001",
                          "source_doc_id": "核心职业/战士/page_56.md",
                          "max_level": 20,
                          "has_spell_table": false,
                          "levels": {
                            "5": {"bab": "+5", "bab_attacks": [5], "fort": "+4", "ref": "+1", "will": "+1"}
                          }
                        },
                        "牧师": {
                          "source_chunk_id": "class_page_40_0001",
                          "source_doc_id": "核心职业/牧师/page_40.md",
                          "max_level": 20,
                          "has_spell_table": true,
                          "levels": {
                            "20": {"bab": "+15", "fort": "+12", "ref": "+6", "will": "+12",
                                   "spells": {"1": "4+1", "2": "4+1", "3": "4+1", "4": "4+1", "5": "4+1",
                                              "6": "4+1", "7": "4+1", "8": "4+1", "9": "4+1"}}
                          }
                        },
                        "骑将": {
                          "source_chunk_id": "class_page_49_0001",
                          "source_doc_id": "进阶职业/骑将/page_49.md",
                          "max_level": 20,
                          "has_spell_table": false,
                          "levels": {
                            "1": {"bab": "+1", "fort": "+2", "ref": "+0", "will": "+0"}
                          }
                        }
                      },
                      "coverage": {
                        "parsed": ["法师", "战士", "骑将"],
                        "missing": [{"class": "催眠师", "reason": "class_overview 无成长表", "doc_id": "基础职业/催眠师/page_94.md"}],
                        "resolved_via": {"骑士": "骑将"},
                        "stats": {"total": 70}
                      }
                    }
                    """;
        }

        /** 两个职业共用别名「剑士」的撞车 fixture（首注册=战士优先，法师撞名被忽略） */
        static String collidingAliasesJson() {
            return """
                    {
                      "version": "1.0",
                      "classes": {
                        "战士": {
                          "aliases": ["剑士"],
                          "source_chunk_id": "class_page_56_0001",
                          "source_doc_id": "核心职业/战士/page_56.md",
                          "max_level": 20,
                          "has_spell_table": false,
                          "levels": {
                            "1": {"bab": "+1", "fort": "+2", "ref": "+0", "will": "+0"}
                          }
                        },
                        "法师": {
                          "aliases": ["剑士"],
                          "source_chunk_id": "class_page_66_0001",
                          "source_doc_id": "核心职业/法师/page_66.md",
                          "max_level": 20,
                          "has_spell_table": true,
                          "levels": {
                            "1": {"bab": "+0", "fort": "+0", "ref": "+0", "will": "+2"}
                          }
                        }
                      },
                      "coverage": {"parsed": ["战士", "法师"], "missing": []}
                    }
                    """;
        }

        static String validJsonWithBard() {            return """
                    {
                      "version": "1.0",
                      "classes": {
                        "吟游诗人": {
                          "source_chunk_id": "class_page_38_0001",
                          "source_doc_id": "核心职业/吟游诗人/page_38.md",
                          "max_level": 20,
                          "has_spell_table": true,
                          "levels": {
                            "1": {"bab": "+0", "fort": "+0", "ref": "+2", "will": "+2",
                                  "spells": {"0": 2, "1": null}}
                          }
                        }
                      },
                      "coverage": {"parsed": ["吟游诗人"], "missing": []}
                    }
                    """;
        }
    }
}
