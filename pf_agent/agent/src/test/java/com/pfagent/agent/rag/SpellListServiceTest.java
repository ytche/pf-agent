package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * SpellListService 单元测试（SP3 F-007，T3）
 *
 * 覆盖 D4 加载 + D5 查询契约：
 *  - 加载成功：规范职业映射 + 别名索引（含自身/变体/全角括号变体）
 *  - resolve：别名归一；未知/空/空白返回 null
 *  - levelOverview：各环级条目数概览 + 指定环级提示
 *  - formatLevel：单环紧凑清单（中文名（英文） [书]）；空环返回「共 0 条」；
 *    超 maxChars 截断并提示（复用 metadata-result-chars 护栏语义）
 *  - listPageDocument：溯源 Document metadata 对齐统一溯源键
 *  - 缺文件 / 解析失败降级：isAvailable=false、查询返回可读空态、不抛异常
 *
 * fixture 为真实 snake_case JSON 文本（levels 键字符串 "0"~"9"），验证
 * record 组件 camelCase 经 @JsonProperty 正确映射，非绕过 JSON 直造对象。
 */
class SpellListServiceTest {

    private static final String WIZARD_LEVEL_1_LINE_1 = "1. 燃烧之手（Burning Hands） [CRB]";

    @TempDir
    Path tempDir;

    /** 加载成功：规范职业映射 + 别名索引（含别名自身、变体、全角括号） */
    @Test
    void loadBuildsClassesAndAliasIndex() throws Exception {
        SpellListService service = loaded(Fixtures.validJson());

        assertThat(service.isAvailable()).isTrue();
        // knownClasses 为 Unicode 码点序（召<吟<法），非拼音序
        assertThat(service.knownClasses()).containsExactly("召唤师(掉链子)", "吟游诗人", "法师");
        // 自身
        assertThat(service.resolve("法师")).isEqualTo("法师");
        // 别名变体
        assertThat(service.resolve("诗人")).isEqualTo("吟游诗人");
        assertThat(service.resolve("游吟诗人")).isEqualTo("吟游诗人");
        // 全角括号变体（召唤师 掉链子 页面目录用全角括号，规范键为半角）
        assertThat(service.resolve("召唤师（掉链子）")).isEqualTo("召唤师(掉链子)");
        // 未知
        assertThat(service.resolve("战士")).isNull();
        assertThat(service.resolve("奥术师")).isNull();
    }

    /** resolve 对 null / 空 / 纯空白输入返回 null（不抛） */
    @Test
    void resolveNullAndBlankReturnsNull() throws Exception {
        SpellListService service = loaded(Fixtures.validJson());

        assertThat(service.resolve(null)).isNull();
        assertThat(service.resolve("  ")).isNull();
        assertThat(service.resolve("")).isNull();
    }

    /** levelOverview：返回各环级条目数概览 + 指定环级提示（不塞全表进上下文） */
    @Test
    void levelOverviewListsCountsPerLevelAndPromptsLevel() throws Exception {
        SpellListService service = loaded(Fixtures.validJson());

        String overview = service.levelOverview("法师");

        assertThat(overview).contains("「法师」", "4 条法术", "1环 3 条", "0环 1 条", "2环 0 条", "level=0");
    }

    /** formatLevel：合法环级返回「序号. 中文名（英文） [书]」紧凑行 */
    @Test
    void formatLevelReturnsCompactEntries() throws Exception {
        SpellListService service = loaded(Fixtures.validJson());

        String list = service.formatLevel("法师", 1, 10_000);

        assertThat(list).contains("「法师」1 环法术（共 3 条）", WIZARD_LEVEL_1_LINE_1);
        assertThat(list).doesNotContain("0 环");
    }

    /** formatLevel：空环级（有环键无条目）返回「共 0 条」而非报错 */
    @Test
    void formatLevelEmptyLevelReturnsZeroCount() throws Exception {
        SpellListService service = loaded(Fixtures.validJson());

        String list = service.formatLevel("法师", 9, 10_000);

        assertThat(list).contains("9 环法术（共 0 条）");
    }

    /** formatLevel：结果超 maxChars 截断并提示，尾部条目不溢出（复用 metadata-result-chars 护栏） */
    @Test
    void formatLevelTruncatesWhenOverCharCap() throws Exception {
        SpellListService service = loaded(Fixtures.validJson());

        String list = service.formatLevel("法师", 1, 50);

        assertThat(list).contains("仅展示前");
        assertThat(list).contains("共 3 条");
        assertThat(list).doesNotContain("3. 七彩喷射"); // 超长尾部被截断
    }

    /** listPageDocument：溯源 Document 含统一键（book/tocPath/source_excerpt） */
    @Test
    void listPageDocumentCarriesProvenanceMetadata() throws Exception {
        SpellListService service = loaded(Fixtures.validJson());

        Document doc = service.listPageDocument("法师");

        assertThat(doc.getMetadata().get("title")).isEqualTo("法师法术列表");
        assertThat(doc.getMetadata().get("book_name_cn")).isEqualTo("法师法术列表");
        assertThat(doc.getMetadata().get("tocPath")).isEqualTo("职业 → 核心职业 → 法师 → 法术列表");
        assertThat(doc.getMetadata().get("doc_id")).isEqualTo("核心职业/法师/page_65.md");
        assertThat(doc.getMetadata().get("chunk_id")).isEqualTo("spell_page_65_0001");
        assertThat(doc.getText()).contains("术士和法师法术列表", "共 4 条");
    }

    /** list_chunk_id 为 null 时溯源 Document 不设 chunk_id 键（drain 走 doc_id 兜底） */
    @Test
    void listPageDocumentOmitsChunkIdWhenListChunkNull() throws Exception {
        SpellListService service = loaded(Fixtures.validJson());

        Document doc = service.listPageDocument("吟游诗人");

        assertThat(doc.getMetadata()).doesNotContainKey("chunk_id");
        assertThat(doc.getMetadata().get("doc_id")).isEqualTo("核心职业/吟游诗人/page_39.md");
    }

    /** 文件缺失降级：isAvailable=false、查询返回可读空态、不抛异常 */
    @Test
    void missingFileDegradesGracefully() {
        SpellListService service = service(tempDir.resolve("nope.json").toString());

        service.load();

        assertThat(service.isAvailable()).isFalse();
        assertThat(service.knownClasses()).isEmpty();
        assertThat(service.resolve("法师")).isNull();
        assertThat(service.levelOverview("法师")).contains("尚未加载");
        assertThat(service.formatLevel("法师", 1, 10_000)).contains("尚未加载");
        // listPageDocument 防御：不抛，返回仅含 title 的空 Document
        assertThat(service.listPageDocument("法师").getText()).isEmpty();
    }

    /** 解析失败降级：文件存在但 JSON 非法 → available=false，不抛 */
    @Test
    void malformedFileDegradesGracefully() throws Exception {
        Path bad = tempDir.resolve("bad.json");
        Files.writeString(bad, "{ this is not json ", StandardCharsets.UTF_8);
        SpellListService service = service(bad.toString());

        service.load();

        assertThat(service.isAvailable()).isFalse();
        assertThat(service.resolve("法师")).isNull();
    }

    /** 构造已加载指定 JSON 文本的 service */
    private SpellListService loaded(String json) throws Exception {
        Path file = tempDir.resolve("spell_lists.json");
        Files.writeString(file, json, StandardCharsets.UTF_8);
        SpellListService service = service(file.toString());
        service.load();
        return service;
    }

    private SpellListService service(String filePath) {
        SpellListService service = new SpellListService();
        ReflectionTestUtils.setField(service, "filePath", filePath);
        return service;
    }

    /** spell_lists.json 结构 fixture（真实 snake_case 键 + 字符串环级键） */
    static final class Fixtures {
        static String validJson() {
            return """
                    {
                      "version": "1.0",
                      "generated_from": "职业列表页 27 路径（测试 fixture）",
                      "classes": {
                        "法师": {
                          "aliases": [],
                          "source_page": "核心职业/法师/page_65.md",
                          "source_toc_path": "职业 → 核心职业 → 法师 → 法术列表",
                          "source_excerpt": "术士和法师法术列表；本职业收录 0~9 环法术共 4 条",
                          "list_chunk_id": "spell_page_65_0001",
                          "levels": {
                            "0": [{"cn": "提升抗力", "en": "Resistance", "book": "CRB", "chunk_id": "spell_Spell CRB_0454"}],
                            "1": [
                              {"cn": "燃烧之手", "en": "Burning Hands", "book": "CRB", "chunk_id": "spell_Spell CRB_0007"},
                              {"cn": "魔法警报", "en": "Alarm", "book": "CRB", "chunk_id": "spell_Spell CRB_0005"},
                              {"cn": "七彩喷射", "en": "Color Spray", "book": "CRB", "chunk_id": null}
                            ],
                            "2": [],
                            "3": [],
                            "4": [],
                            "5": [],
                            "6": [],
                            "7": [],
                            "8": [],
                            "9": []
                          }
                        },
                        "吟游诗人": {
                          "aliases": ["诗人", "游吟诗人"],
                          "source_page": "核心职业/吟游诗人/page_39.md",
                          "source_toc_path": "职业 → 核心职业 → 吟游诗人 → 法术列表",
                          "source_excerpt": "吟游诗人法术列表；本职业收录 0~9 环法术共 1 条",
                          "list_chunk_id": null,
                          "levels": {}
                        },
                        "召唤师(掉链子)": {
                          "aliases": ["召唤师（掉链子）", "召唤师掉链子"],
                          "source_page": "掉链子（Unchained）/召唤师/page_248.md",
                          "source_toc_path": "职业 → 掉链子（Unchained） → 召唤师 → 法术列表",
                          "source_excerpt": "召唤师（Summoner）法术列表",
                          "list_chunk_id": "class_page_248_0001",
                          "levels": {}
                        }
                      }
                    }
                    """;
        }
    }
}
