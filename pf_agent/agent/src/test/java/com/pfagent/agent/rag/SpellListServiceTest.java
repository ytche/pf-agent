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

        // B1 分页补口：截断话术=真实总数/返回区间/has_more/续取 offset（旧「仅展示前」话术退役）
        assertThat(list).contains("共 3 条，本次返回第 1~", "has_more=true",
                "续取：保持其他参数不变，offset=");
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

    private SpellListService service(String filePath, String unionFilePath) {
        SpellListService service = service(filePath);
        ReflectionTestUtils.setField(service, "unionFilePath", unionFilePath);
        return service;
    }

    // ---------- B1 union 合并读取（方案_B1法术派生补充清单_20261029，F-007 口径化） ----------

    /** union 加载成功：derived 条目并入单环清单（〔派生〕标注，计数=官方+派生） */
    @Test
    void unionMergesDerivedEntriesWithMarker() throws Exception {
        Path file = tempDir.resolve("spell_lists.json");
        Files.writeString(file, Fixtures.validJson(), StandardCharsets.UTF_8);
        Path union = tempDir.resolve("spell_lists_union.json");
        Files.writeString(union, Fixtures.unionJson(), StandardCharsets.UTF_8);
        SpellListService service = service(file.toString(), union.toString());
        service.load();

        assertThat(service.isAvailable()).isTrue();
        assertThat(service.isUnionAvailable()).isTrue();
        String list = service.formatLevel("法师", 1, 10_000);
        // 官方 3 条 + 派生 2 条；派生行带〔派生〕标注（B1 D1 source 标注）
        assertThat(list).contains("「法师」1 环法术（共 5 条）", WIZARD_LEVEL_1_LINE_1);
        assertThat(list).contains("4. 法师密派生（Wizard Secret） [APG]〔派生〕");
        assertThat(list).contains("5. 法师广派生（Wizard Wide） [UM]〔派生〕");
        assertThat(list).doesNotContain("官方同条目");  // official_list 条目不重复并入
    }

    /** union 缺失（B1 降级策略 Q3）：WARN 降级，仅官方清单，不 FAIL */
    @Test
    void unionMissingDegradesToOfficialOnly() throws Exception {
        Path file = tempDir.resolve("spell_lists.json");
        Files.writeString(file, Fixtures.validJson(), StandardCharsets.UTF_8);
        SpellListService service = service(file.toString(), tempDir.resolve("nope.json").toString());
        service.load();

        assertThat(service.isAvailable()).isTrue();
        assertThat(service.isUnionAvailable()).isFalse();
        assertThat(service.formatLevel("法师", 1, 10_000))
                .contains("「法师」1 环法术（共 3 条）", WIZARD_LEVEL_1_LINE_1);
    }

    // ---------- B1 分页（与 J2 searchByMetadata 同构，AKN-015 文案风格） ----------

    /** 分页窗口拼接：offset=0/2/4 三页拿全 5 条，每页 footer 给真实总数与续取 */
    @Test
    void paginationPagesCoverAllEntries() throws Exception {
        SpellListService service = loadedWithUnion();  // 法师 1 环 = 3 官方 + 2 派生

        String p1 = service.formatLevel("法师", 1, 10_000, 0, 2);
        assertThat(p1).contains("1. 燃烧之手", "2. 魔法警报",
                "共 5 条，本次返回第 1~2 条", "has_more=true",
                "续取：保持其他参数不变，offset=2");
        assertThat(p1).doesNotContain("3. 七彩喷射");

        String p2 = service.formatLevel("法师", 1, 10_000, 2, 2);
        assertThat(p2).contains("3. 七彩喷射", "4. 法师密派生",
                "本次返回第 3~4 条", "has_more=true", "offset=4");

        String p3 = service.formatLevel("法师", 1, 10_000, 4, 2);
        assertThat(p3).contains("5. 法师广派生");
        assertThat(p3).contains("已翻完全部结果（共 5 条）");
        assertThat(p3).doesNotContain("has_more=true");  // 末页无假 has_more
    }

    /** offset 越界：可读提示，不抛异常、不假总数 */
    @Test
    void paginationOffsetOutOfRangeReturnsReadableHint() throws Exception {
        SpellListService service = loadedWithUnion();
        String r = service.formatLevel("法师", 1, 10_000, 5, 2);
        assertThat(r).contains("共 5 条", "offset=5 越界", "请减小 offset 翻页");
    }

    /** offset 为负钳制为 0（与 J2 钳制注记风格一致） */
    @Test
    void paginationNegativeOffsetClampsToZero() throws Exception {
        SpellListService service = loadedWithUnion();
        String r = service.formatLevel("法师", 1, 10_000, -3, 2);
        assertThat(r).contains("1. 燃烧之手", "本次返回第 1~2 条");
    }

    /** 文案无假总数：footer 的「共 N 条」与概览行一致（levelTotal 口径） */
    @Test
    void paginationFooterTotalMatchesLevelTotal() throws Exception {
        SpellListService service = loadedWithUnion();
        assertThat(service.levelTotal("法师", 1)).isEqualTo(5);
        String r = service.formatLevel("法师", 1, 10_000, 0, 50);
        assertThat(r).contains("共 5 条", "已翻完全部结果（共 5 条）");
    }

    /** 默认行为不变：不传 offset/limit 全量未截断时 footer 零变化 */
    @Test
    void defaultNoPaginationKeepsLegacyOutput() throws Exception {
        SpellListService service = loadedWithUnion();
        String r = service.formatLevel("法师", 1, 10_000);
        assertThat(r).contains("「法师」1 环法术（共 5 条）", "5. 法师广派生");
        assertThat(r).doesNotContain("has_more", "续取", "已翻完全部结果");
    }

    private SpellListService loadedWithUnion() throws Exception {
        Path file = tempDir.resolve("spell_lists.json");
        Files.writeString(file, Fixtures.validJson(), StandardCharsets.UTF_8);
        Path union = tempDir.resolve("spell_lists_union.json");
        Files.writeString(union, Fixtures.unionJson(), StandardCharsets.UTF_8);
        SpellListService service = service(file.toString(), union.toString());
        service.load();
        return service;
    }

    // ---------- F-025 union 1.1 折叠清单直读 ----------

    /**
     * 评审 r1-P1 回归基线：最小合法 1.1（官方条目 chunk_id 显式 null、顶层 matched_by
     * 省略、派生条目全镜像）必须直读成功——后续无效用例都以它为变异底本。
     */
    @Test
    void union11MinimalValidBaselineReadsFolded() throws Exception {
        SpellListService service = loadedWithUnion11(Fixtures.union11MinimalJson());

        assertThat(service.isUnionAvailable()).isTrue();
        assertThat(service.isUnionFoldedPath()).isTrue();
        assertThat(service.formatLevel("法师", 1, 10_000)).contains("共 2 条");
    }

    /**
     * 评审 r2-P1：数据 lane 真实 1.1 形态——官方条目顶层与官方 source 均无
     * level_evidence 键（spec §6.2 只要求派生来源保存该字段），必须直读折叠清单。
     */
    @Test
    void union11OfficialWithoutLevelEvidenceKeyReadsFolded() throws Exception {
        SpellListService service = loadedWithUnion11(Fixtures.union11RealShapeJson());

        assertThat(service.isUnionAvailable()).isTrue();
        assertThat(service.isUnionFoldedPath()).isTrue();
        String list = service.formatLevel("法师", 1, 10_000);
        assertThat(list).contains("「法师」1 环法术（共 2 条）", "1. 魔法警报（Alarm） [CRB]");
        assertThat(list).contains("2. 法师密派生（Wizard Secret） [APG]〔派生〕");
    }

    /** 评审 r2-P1：union 文件内容为 JSON null → WARN 降级，不 NPE 炸 @PostConstruct */
    @Test
    void union11RootNullDegrades() throws Exception {
        SpellListService service = loadedWithUnion11("null");

        assertThat(service.isAvailable()).isTrue();
        assertThat(service.isUnionAvailable()).isFalse();
        assertThat(service.formatLevel("法师", 1, 10_000))
                .contains("「法师」1 环法术（共 3 条）", WIZARD_LEVEL_1_LINE_1);
    }

    /** 评审 r2-P1：union 文件为空（构建中断的截断产物）→ WARN 降级，不 NPE */
    @Test
    void union11EmptyFileDegrades() throws Exception {
        SpellListService service = loadedWithUnion11("");

        assertThat(service.isAvailable()).isTrue();
        assertThat(service.isUnionAvailable()).isFalse();
        assertThat(service.formatLevel("法师", 1, 10_000)).contains("共 3 条");
    }

    /** 评审 r2-P1：union 根节点为非对象数组 → WARN 降级，不抛 */
    @Test
    void union11RootArrayDegrades() throws Exception {
        SpellListService service = loadedWithUnion11("[]");

        assertThat(service.isUnionAvailable()).isFalse();
        assertThat(service.formatLevel("法师", 1, 10_000)).contains("共 3 条");
    }

    /** 评审 r2-P2：union 1.1 缺官方清单职业（版本错配）→ 无效 1.1 WARN 降级 */
    @Test
    void union11MissingOfficialClassCoverageDegrades() throws Exception {
        ch.qos.logback.classic.Logger logger = (ch.qos.logback.classic.Logger)
                org.slf4j.LoggerFactory.getLogger(SpellListService.class);
        ch.qos.logback.core.read.ListAppender<ch.qos.logback.classic.spi.ILoggingEvent> appender =
                new ch.qos.logback.core.read.ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            // 只有 法师，缺官方清单中的 吟游诗人/召唤师(掉链子)
            SpellListService service = loadedWithUnion11("{\"version\":\"1.1\",\"classes\":"
                    + "{\"法师\":{\"levels\":" + Fixtures.emptyLevels() + "}}}");

            assertThat(service.isUnionAvailable()).isFalse();
            assertThat(service.formatLevel("法师", 1, 10_000)).contains("共 3 条");
            assertThat(appender.list).anyMatch(e ->
                    e.getLevel() == ch.qos.logback.classic.Level.WARN
                            && e.getFormattedMessage().contains("无效 1.1"));
        } finally {
            logger.detachAppender(appender);
        }
    }

    /** 评审 r2-P2：union 1.1 职业缺官方 0~9 环键（版本错配）→ 无效 1.1 降级 */
    @Test
    void union11MissingLevelCoverageDegrades() throws Exception {
        // 法师 缺 "9" 环键，其余职业齐全
        String json = "{\"version\":\"1.1\",\"classes\":{"
                + "\"法师\":{\"levels\":{\"0\":[],\"1\":[],\"2\":[],\"3\":[],\"4\":[],"
                + "\"5\":[],\"6\":[],\"7\":[],\"8\":[]}},"
                + "\"吟游诗人\":{\"levels\":" + Fixtures.emptyLevels() + "},"
                + "\"召唤师(掉链子)\":{\"levels\":" + Fixtures.emptyLevels() + "}}}";
        assertInvalid11Degrades(json);
    }

    /** 评审 r1-P1：1.1 缺 classes 键 → 无效产物 WARN 降级官方清单（不炸启动） */
    @Test
    void union11MissingClassesKeyDegrades() throws Exception {
        assertInvalid11Degrades("{\"version\":\"1.1\"}");
    }

    /** 评审 r1-P1：1.1 classes 为 JSON null → 无效产物降级 */
    @Test
    void union11NullClassesDegrades() throws Exception {
        assertInvalid11Degrades("{\"version\":\"1.1\",\"classes\":null}");
    }

    /** 评审 r1-P1：1.1 职业缺 levels 键 → 无效产物降级 */
    @Test
    void union11ClassMissingLevelsKeyDegrades() throws Exception {
        assertInvalid11Degrades("{\"version\":\"1.1\",\"classes\":{\"法师\":{}}}");
    }

    /** 评审 r1-P1：1.1 levels 为 JSON null → 无效产物降级 */
    @Test
    void union11NullLevelsDegrades() throws Exception {
        assertInvalid11Degrades("{\"version\":\"1.1\",\"classes\":{\"法师\":{\"levels\":null}}}");
    }

    /** 评审 r1-P1：1.1 levels 列表含 null 元素 → 无效产物降级 */
    @Test
    void union11NullEntryElementDegrades() throws Exception {
        assertInvalid11Degrades("{\"version\":\"1.1\",\"classes\":{\"法师\":{\"levels\":{\"1\":[null]}}}}");
    }

    /** 评审 r1-P1：1.1 条目 sources 为 JSON null → 无效产物降级 */
    @Test
    void union11EntryNullSourcesDegrades() throws Exception {
        String json = Fixtures.union11MinimalJson().replace(
                "{\"cn\":\"魔法警报\",\"en\":\"Alarm\",\"book\":\"CRB\",\"chunk_id\":null,"
                        + "\"source\":\"official_list\",\"level_evidence\":null,\"sources\":["
                        + "{\"book\":\"CRB\",\"chunk_id\":null,\"source\":\"official_list\","
                        + "\"level_evidence\":null,\"matched_by\":\"official_primary\"}]}",
                "{\"cn\":\"魔法警报\",\"en\":\"Alarm\",\"book\":\"CRB\",\"chunk_id\":null,"
                        + "\"source\":\"official_list\",\"level_evidence\":null,\"sources\":null}");
        assertInvalid11Degrades(json);
    }

    /** 评审 r1-P1：1.1 sources 列表含 null 元素 → 无效产物降级 */
    @Test
    void union11NullSourceElementDegrades() throws Exception {
        String json = Fixtures.union11MinimalJson().replace(
                "\"sources\":[{\"book\":\"CRB\",\"chunk_id\":null",
                "\"sources\":[null,{\"book\":\"CRB\",\"chunk_id\":null");
        assertInvalid11Degrades(json);
    }

    /** 评审 r1-P1：1.1 source 空白（非缺键）→ 无效产物降级 */
    @Test
    void union11BlankSourceFieldDegrades() throws Exception {
        String json = Fixtures.union11MinimalJson().replace(
                "{\"book\":\"CRB\",\"chunk_id\":null,\"source\":\"official_list\","
                        + "\"level_evidence\":null,\"matched_by\":\"official_primary\"}",
                "{\"book\":\"CRB\",\"chunk_id\":null,\"source\":\"  \","
                        + "\"level_evidence\":null,\"matched_by\":\"official_primary\"}");
        assertInvalid11Degrades(json);
    }

    /** 评审 r1-P1：1.1 matched_by 空白/缺键 → 无效产物降级 */
    @Test
    void union11BlankOrMissingMatchedByDegrades() throws Exception {
        String blank = Fixtures.union11MinimalJson().replace(
                "\"matched_by\":\"official_primary\"}",
                "\"matched_by\":\"\"}");
        assertInvalid11Degrades(blank);
        String missing = Fixtures.union11MinimalJson().replace(
                ",\"matched_by\":\"official_primary\"}",
                "}");
        assertInvalid11Degrades(missing);
    }

    /** 评审 r1-P1：1.1 派生来源 chunk_id 空白 → 无效产物降级 */
    @Test
    void union11DerivedBlankChunkIdDegrades() throws Exception {
        String json = Fixtures.union11MinimalJson().replace(
                "{\"book\":\"APG\",\"chunk_id\":\"spell_x\",\"source\":\"derived\"",
                "{\"book\":\"APG\",\"chunk_id\":\"\",\"source\":\"derived\"");
        assertInvalid11Degrades(json);
    }

    /** 评审 r1-P1：1.1 官方来源缺 chunk_id 键（键必须存在，显式 null 才合法）→ 降级 */
    @Test
    void union11OfficialSourceMissingChunkIdKeyDegrades() throws Exception {
        String json = Fixtures.union11MinimalJson().replace(
                "{\"book\":\"CRB\",\"chunk_id\":null,\"source\":\"official_list\","
                        + "\"level_evidence\":null,\"matched_by\":\"official_primary\"}",
                "{\"book\":\"CRB\",\"source\":\"official_list\","
                        + "\"level_evidence\":null,\"matched_by\":\"official_primary\"}");
        assertInvalid11Degrades(json);
    }

    /** 评审 r1-P1：1.1 主来源镜像——level_evidence/matched_by/chunk_id/source/book 任一的顶层值与主来源不符 → 降级 */
    @Test
    void union11PrimaryMirrorMismatchDegrades() throws Exception {
        // 派生条目顶层 level_evidence 与主来源不符
        assertInvalid11Degrades(Fixtures.union11MinimalJson().replace(
                "\"level_evidence\":\"spell_level: 法师 1\",\"matched_by\":\"derived_new\",\"sources\"",
                "\"level_evidence\":\"spell_level: 法师 2\",\"matched_by\":\"derived_new\",\"sources\""));
        // 派生条目顶层 matched_by 与主来源不符
        assertInvalid11Degrades(Fixtures.union11MinimalJson().replace(
                "\"matched_by\":\"derived_new\",\"sources\"",
                "\"matched_by\":\"derived_en\",\"sources\""));
        // 派生条目顶层 chunk_id 与主来源不符（只改顶层，锚定 en 前缀保证唯一）
        assertInvalid11Degrades(Fixtures.union11MinimalJson().replace(
                "\"en\":\"Wizard Secret\",\"book\":\"APG\",\"chunk_id\":\"spell_x\"",
                "\"en\":\"Wizard Secret\",\"book\":\"APG\",\"chunk_id\":\"spell_y\""));
        // 官方条目顶层 source 与主来源不符
        assertInvalid11Degrades(Fixtures.union11MinimalJson().replace(
                "\"chunk_id\":null,\"source\":\"official_list\",\"level_evidence\":null,"
                        + "\"sources\":[{\"book\":\"CRB\"",
                "\"chunk_id\":null,\"source\":\"derived\",\"level_evidence\":null,"
                        + "\"sources\":[{\"book\":\"CRB\""));
        // 官方条目顶层 book 与主来源不符
        assertInvalid11Degrades(Fixtures.union11MinimalJson().replace(
                "{\"cn\":\"魔法警报\",\"en\":\"Alarm\",\"book\":\"CRB\"",
                "{\"cn\":\"魔法警报\",\"en\":\"Alarm\",\"book\":\"APG\""));
    }

    /** 评审 r1-P1：1.1 派生主条目顶层缺 matched_by 键（仅官方主条目可省略）→ 降级 */
    @Test
    void union11DerivedTopLevelMissingMatchedByDegrades() throws Exception {
        String json = Fixtures.union11MinimalJson().replace(
                "\"source\":\"derived\",\"level_evidence\":\"spell_level: 法师 1\",\"matched_by\":\"derived_new\",\"sources\"",
                "\"source\":\"derived\",\"level_evidence\":\"spell_level: 法师 1\",\"sources\"");
        assertInvalid11Degrades(json);
    }

    /** 评审 r1-P1：无效 1.1 降级必须打 WARN 且官方清单不受影响（不静默清空） */
    @Test
    void union11InvalidDegradesWithWarnAndKeepsOfficial() throws Exception {
        ch.qos.logback.classic.Logger logger = (ch.qos.logback.classic.Logger)
                org.slf4j.LoggerFactory.getLogger(SpellListService.class);
        ch.qos.logback.core.read.ListAppender<ch.qos.logback.classic.spi.ILoggingEvent> appender =
                new ch.qos.logback.core.read.ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            SpellListService service = loadedWithUnion11(
                    "{\"version\":\"1.1\",\"classes\":{\"法师\":{\"levels\":{\"1\":[null]}}}}");

            assertThat(service.isAvailable()).isTrue();
            assertThat(service.isUnionAvailable()).isFalse();
            assertThat(service.formatLevel("法师", 1, 10_000)).contains("共 3 条", WIZARD_LEVEL_1_LINE_1);
            assertThat(appender.list).anyMatch(e ->
                    e.getLevel() == ch.qos.logback.classic.Level.WARN
                            && e.getFormattedMessage().contains("无效 1.1"));
        } finally {
            logger.detachAppender(appender);
        }
    }

    /** 评审 r1-P2：缺 version 字段按 1.0 兼容读取并打 WARN（不依赖显式 "1.0"） */
    @Test
    void unionNoVersionCompatTreatsAs10AndWarns() throws Exception {
        String noVersion = Fixtures.unionJson().replace("\"version\":\"1.0\",", "");
        ch.qos.logback.classic.Logger logger = (ch.qos.logback.classic.Logger)
                org.slf4j.LoggerFactory.getLogger(SpellListService.class);
        ch.qos.logback.core.read.ListAppender<ch.qos.logback.classic.spi.ILoggingEvent> appender =
                new ch.qos.logback.core.read.ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            SpellListService service = loadedWithUnion11(noVersion);

            assertThat(service.isUnionAvailable()).isTrue();
            assertThat(service.isUnionFoldedPath()).isFalse();
            assertThat(service.formatLevel("法师", 1, 10_000)).contains("共 5 条");
            assertThat(appender.list).anyMatch(e ->
                    e.getLevel() == ch.qos.logback.classic.Level.WARN
                            && e.getFormattedMessage().contains("1.0"));
        } finally {
            logger.detachAppender(appender);
        }
    }

    /** 1.1 直读：折叠完整条目序列不再叠加官方清单；多书缩写去重展示、派生标记随主来源 */
    @Test
    void union11ReadsFoldedEntriesDirectly() throws Exception {
        SpellListService service = loadedWithUnion11();

        assertThat(service.isUnionAvailable()).isTrue();
        assertThat(service.isUnionFoldedPath()).isTrue();
        String list = service.formatLevel("法师", 1, 10_000);
        // 4 条=3 官方主条目 + 1 纯派生主条目；官方不再重复并入（旧路径为 3+过滤后派生）
        assertThat(list).contains("「法师」1 环法术（共 4 条）");
        // 官方主条目合并派生来源：全来源书 [PSP 主来源在前/COMP]，不带〔派生〕
        assertThat(list).contains("1. 燃烧之手（Burning Hands） [CRB/COMP]");
        assertThat(countOccurrences(list, "燃烧之手")).isEqualTo(1);
        assertThat(list).contains("4. 法师密派生（Wizard Secret） [APG/UM]〔派生〕");
        // APG 出现两次仅展示一次（保序去重）
        assertThat(list).doesNotContain("[APG/UM/APG]");
        // 只有主来源 derived 的条目带〔派生〕：全表仅 1 处
        assertThat(countOccurrences(list, "〔派生〕")).isEqualTo(1);
    }

    /** 1.1 口径统一：levelTotal/概览/分页 footer 同为折叠后不同法术数，分页可翻全 */
    @Test
    void union11TotalsUnifyOverviewTotalAndPagination() throws Exception {
        SpellListService service = loadedWithUnion11();

        assertThat(service.levelTotal("法师", 1)).isEqualTo(4);
        String overview = service.levelOverview("法师");
        assertThat(overview).contains("0~9 环 5 条法术", "0环 1 条", "1环 4 条");

        String p1 = service.formatLevel("法师", 1, 10_000, 0, 3);
        assertThat(p1).contains("共 4 条，本次返回第 1~3 条", "has_more=true",
                "续取：保持其他参数不变，offset=3");
        String p2 = service.formatLevel("法师", 1, 10_000, 3, 3);
        assertThat(p2).contains("4. 法师密派生", "已翻完全部结果（共 4 条）");
        assertThat(p2).doesNotContain("has_more=true");
    }

    /** 1.1 条目缺 sources：视为无效产物，降级为仅官方清单 */
    @Test
    void union11MissingSourcesDegradesToOfficialOnly() throws Exception {
        SpellListService service = loadedWithUnion11("""
                {"version":"1.1","classes":{"法师":{"levels":{"1":[
                  {"cn":"法师密派生","en":"Wizard Secret","book":"APG","chunk_id":"spell_x",
                   "source":"derived","level_evidence":"spell_level: 法师 1","matched_by":"derived_new"}
                ]}}}}
                """);

        assertThat(service.isUnionAvailable()).isFalse();
        assertThat(service.formatLevel("法师", 1, 10_000))
                .contains("「法师」1 环法术（共 3 条）", WIZARD_LEVEL_1_LINE_1);
    }

    /** 1.1 主来源镜像不一致（首个 source 的 book 与顶层 book 不符）：无效产物降级 */
    @Test
    void union11MirrorMismatchDegradesToOfficialOnly() throws Exception {
        String json = Fixtures.union11Json().replaceFirst(
                "\\{\"book\":\"CRB\",\"chunk_id\":null,\"source\":\"official_list\","
                        + "\\s*\"level_evidence\": null,\"matched_by\":\"official_primary\"\\}",
                "{\"book\":\"APG\",\"chunk_id\":null,\"source\":\"official_list\","
                        + "\"level_evidence\": null,\"matched_by\":\"official_primary\"}");
        SpellListService service = loadedWithUnion11(json);

        assertThat(service.isUnionAvailable()).isFalse();
        assertThat(service.formatLevel("法师", 1, 10_000)).contains("共 3 条");
    }

    /** 1.1 派生来源缺 chunk_id：无效产物降级 */
    @Test
    void union11DerivedSourceMissingChunkDegrades() throws Exception {
        String json = Fixtures.union11Json().replaceFirst(
                "\\{\"book\":\"COMP\",\"chunk_id\":\"spell_page_1155_0002\"",
                "{\"book\":\"COMP\",\"chunk_id\":null");
        SpellListService service = loadedWithUnion11(json);

        assertThat(service.isUnionAvailable()).isFalse();
        assertThat(service.formatLevel("法师", 1, 10_000)).contains("共 3 条");
    }

    /** 未知更高版本：不按 1.1 猜测解析，降级为仅官方清单 */
    @Test
    void unionUnknownVersionDegradesToOfficialOnly() throws Exception {
        SpellListService service = loadedWithUnion11(
                Fixtures.union11Json().replace("\"version\":\"1.1\"", "\"version\":\"1.2\""));

        assertThat(service.isUnionAvailable()).isFalse();
        assertThat(service.formatLevel("法师", 1, 10_000)).contains("共 3 条");
    }

    /** union JSON 畸形（KN-247 QA-3）：WARN 降级，仅官方清单，不炸启动 */
    @Test
    void unionMalformedDegradesToOfficialOnly() throws Exception {
        Path file = tempDir.resolve("spell_lists.json");
        Files.writeString(file, Fixtures.validJson(), StandardCharsets.UTF_8);
        Path union = tempDir.resolve("spell_lists_union.json");
        Files.writeString(union, "{ not json ", StandardCharsets.UTF_8);
        SpellListService service = service(file.toString(), union.toString());
        service.load();

        assertThat(service.isAvailable()).isTrue();
        assertThat(service.isUnionAvailable()).isFalse();
        assertThat(service.formatLevel("法师", 1, 10_000)).contains("共 3 条");
    }

    /** 1.0 固化产物兼容：仍走官方+derived 旧口径并 WARN（unionAvailable=true、非折叠路径） */
    @Test
    void union10CompatibilityKeepsLegacyBehavior() throws Exception {
        ch.qos.logback.classic.Logger logger = (ch.qos.logback.classic.Logger)
                org.slf4j.LoggerFactory.getLogger(SpellListService.class);
        ch.qos.logback.core.read.ListAppender<ch.qos.logback.classic.spi.ILoggingEvent> appender =
                new ch.qos.logback.core.read.ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        try {
            SpellListService service = loadedWithUnion();

            assertThat(service.isUnionAvailable()).isTrue();
            assertThat(service.isUnionFoldedPath()).isFalse();
            assertThat(service.formatLevel("法师", 1, 10_000)).contains("共 5 条");
            assertThat(service.levelTotal("法师", 1)).isEqualTo(5);
            assertThat(appender.list).anyMatch(e ->
                    e.getLevel() == ch.qos.logback.classic.Level.WARN
                            && e.getFormattedMessage().contains("1.0"));
        } finally {
            logger.detachAppender(appender);
        }
    }

    /** 评审 r1-P1：无效 1.1 统一断言——WARN 降级、官方清单不受影响、不炸启动 */
    private void assertInvalid11Degrades(String unionJson) throws Exception {
        SpellListService service = loadedWithUnion11(unionJson);

        assertThat(service.isAvailable()).isTrue();
        assertThat(service.isUnionAvailable()).isFalse();
        assertThat(service.isUnionFoldedPath()).isFalse();
        assertThat(service.formatLevel("法师", 1, 10_000))
                .contains("「法师」1 环法术（共 3 条）", WIZARD_LEVEL_1_LINE_1);
    }

    private SpellListService loadedWithUnion11() throws Exception {
        return loadedWithUnion11(Fixtures.union11Json());
    }

    private SpellListService loadedWithUnion11(String unionJson) throws Exception {
        Path file = tempDir.resolve("spell_lists.json");
        Files.writeString(file, Fixtures.validJson(), StandardCharsets.UTF_8);
        Path union = tempDir.resolve("spell_lists_union.json");
        Files.writeString(union, unionJson, StandardCharsets.UTF_8);
        SpellListService service = service(file.toString(), union.toString());
        service.load();
        return service;
    }

    private static int countOccurrences(String text, String sub) {
        int count = 0;
        for (int i = text.indexOf(sub); i >= 0; i = text.indexOf(sub, i + sub.length())) {
            count++;
        }
        return count;
    }

    /** spell_lists.json 结构 fixture（真实 snake_case 键 + 字符串环级键） */
    static final class Fixtures {
        /**
         * 评审 r1-P1 回归底本：最小合法 union 1.1（单行 JSON，便于字面量变异）——
         * 官方条目 chunk_id 显式 null、顶层 matched_by 省略（官方例外）；
         * 派生条目顶层全镜像（含 matched_by）。共 2 条折叠条目。
         * 评审 r2-P2：补齐全职业与 0~9 环键，满足覆盖率校验（其余环级为空）。
         */
        static String union11MinimalJson() {
            return "{\"version\":\"1.1\",\"classes\":{"
                    + "\"法师\":{\"levels\":{\"0\":[],\"1\":["
                    + "{\"cn\":\"魔法警报\",\"en\":\"Alarm\",\"book\":\"CRB\",\"chunk_id\":null,"
                    + "\"source\":\"official_list\",\"level_evidence\":null,\"sources\":["
                    + "{\"book\":\"CRB\",\"chunk_id\":null,\"source\":\"official_list\","
                    + "\"level_evidence\":null,\"matched_by\":\"official_primary\"}]},"
                    + "{\"cn\":\"法师密派生\",\"en\":\"Wizard Secret\",\"book\":\"APG\",\"chunk_id\":\"spell_x\","
                    + "\"source\":\"derived\",\"level_evidence\":\"spell_level: 法师 1\",\"matched_by\":\"derived_new\","
                    + "\"sources\":["
                    + "{\"book\":\"APG\",\"chunk_id\":\"spell_x\",\"source\":\"derived\","
                    + "\"level_evidence\":\"spell_level: 法师 1\",\"matched_by\":\"derived_new\"}]}"
                    + "],\"2\":[],\"3\":[],\"4\":[],\"5\":[],\"6\":[],\"7\":[],\"8\":[],\"9\":[]}},"
                    + "\"吟游诗人\":{\"levels\":" + emptyLevels() + "},"
                    + "\"召唤师(掉链子)\":{\"levels\":" + emptyLevels() + "}}}";
        }

        /** 0~9 环全空 levels 片段（覆盖率基线：官方清单 3 职业齐全） */
        static String emptyLevels() {
            return "{\"0\":[],\"1\":[],\"2\":[],\"3\":[],\"4\":[],"
                    + "\"5\":[],\"6\":[],\"7\":[],\"8\":[],\"9\":[]}";
        }

        /**
         * 评审 r2-P1：数据 lane b2fb2f8 真实 1.1 导出形态——官方条目顶层只写
         * cn/en/book/chunk_id/source/sources，官方 source 只写
         * book/chunk_id/source/matched_by，两侧都不含 level_evidence 键；
         * 派生条目照常保存 level_evidence 与顶层 matched_by。
         */
        static String union11RealShapeJson() {
            return "{\"version\":\"1.1\",\"classes\":{"
                    + "\"法师\":{\"levels\":{\"0\":[],\"1\":["
                    + "{\"cn\":\"魔法警报\",\"en\":\"Alarm\",\"book\":\"CRB\",\"chunk_id\":null,"
                    + "\"source\":\"official_list\",\"sources\":["
                    + "{\"book\":\"CRB\",\"chunk_id\":null,\"source\":\"official_list\","
                    + "\"matched_by\":\"official_primary\"}]},"
                    + "{\"cn\":\"法师密派生\",\"en\":\"Wizard Secret\",\"book\":\"APG\",\"chunk_id\":\"spell_x\","
                    + "\"source\":\"derived\",\"level_evidence\":\"spell_level: 法师 1\",\"matched_by\":\"derived_new\","
                    + "\"sources\":["
                    + "{\"book\":\"APG\",\"chunk_id\":\"spell_x\",\"source\":\"derived\","
                    + "\"level_evidence\":\"spell_level: 法师 1\",\"matched_by\":\"derived_new\"}]}"
                    + "],\"2\":[],\"3\":[],\"4\":[],\"5\":[],\"6\":[],\"7\":[],\"8\":[],\"9\":[]}},"
                    + "\"吟游诗人\":{\"levels\":" + emptyLevels() + "},"
                    + "\"召唤师(掉链子)\":{\"levels\":" + emptyLevels() + "}}}";
        }

        /**
         * union 1.1 fixture（F-025 折叠清单）：法师 0/1 环完整折叠序列——
         * 燃烧之手为官方主条目（合并 COMP 派生来源，多书缩写 [CRB/COMP]）；
         * 法师密派生为纯派生主条目（APG/UM/APG 三来源，书缩写保序去重 [APG/UM]）。
         */
        static String union11Json() {
            return """
                    {"version":"1.1","classes":{
                      "法师":{"levels":{
                        "0":[
                          {"cn":"提升抗力","en":"Resistance","book":"CRB","chunk_id":"spell_Spell CRB_0454",
                           "source":"official_list","level_evidence": null,"sources":[
                             {"book":"CRB","chunk_id":"spell_Spell CRB_0454","source":"official_list",
                              "level_evidence": null,"matched_by":"official_primary"}]}
                        ],
                        "1":[
                          {"cn":"燃烧之手","en":"Burning Hands","book":"CRB","chunk_id":null,
                           "source":"official_list","level_evidence": null,"sources":[
                             {"book":"CRB","chunk_id":null,"source":"official_list",
                              "level_evidence": null,"matched_by":"official_primary"},
                             {"book":"COMP","chunk_id":"spell_page_1155_0002","source":"derived",
                              "level_evidence":"spell_level: 法师 1","matched_by":"official_cn_and_en"}]},
                          {"cn":"魔法警报","en":"Alarm","book":"CRB","chunk_id":"spell_Spell CRB_0005",
                           "source":"official_list","level_evidence": null,"sources":[
                             {"book":"CRB","chunk_id":"spell_Spell CRB_0005","source":"official_list",
                              "level_evidence": null,"matched_by":"official_primary"}]},
                          {"cn":"七彩喷射","en":"Color Spray","book":"CRB","chunk_id":null,
                           "source":"official_list","level_evidence": null,"sources":[
                             {"book":"CRB","chunk_id":null,"source":"official_list",
                              "level_evidence": null,"matched_by":"official_primary"}]},
                          {"cn":"法师密派生","en":"Wizard Secret","book":"APG","chunk_id":"spell_x",
                           "source":"derived","level_evidence":"spell_level: 法师 1","matched_by":"derived_new",
                           "sources":[
                             {"book":"APG","chunk_id":"spell_x","source":"derived",
                              "level_evidence":"spell_level: 法师 1","matched_by":"derived_new"},
                             {"book":"UM","chunk_id":"spell_z","source":"derived",
                              "level_evidence":"spell_level: 法师 1","matched_by":"derived_en"},
                             {"book":"APG","chunk_id":"spell_x2","source":"derived",
                              "level_evidence":"spell_level: 法师 1","matched_by":"derived_cn"}]}
                        ],
                        "2":[],"3":[],"4":[],"5":[],"6":[],"7":[],"8":[],"9":[]
                      }},
                      "吟游诗人":{"levels":{"0":[],"1":[],"2":[],"3":[],"4":[],
                        "5":[],"6":[],"7":[],"8":[],"9":[]}},
                      "召唤师(掉链子)":{"levels":{"0":[],"1":[],"2":[],"3":[],"4":[],
                        "5":[],"6":[],"7":[],"8":[],"9":[]}}
                    }}
                    """;
        }

        /** union fixture：法师 1 环 2 派生 + 1 条 official_list（应被过滤不重复并） */
        static String unionJson() {
            return """
                    {"version":"1.0","classes":{
                      "法师":{"levels":{"1":[
                        {"cn":"法师密派生","en":"Wizard Secret","book":"APG",
                         "chunk_id":"spell_x","source":"derived",
                         "level_evidence":"spell_level: 法师 1","matched_by":"derived_new"},
                        {"cn":"法师广派生","en":"Wizard Wide","book":"UM",
                         "chunk_id":"spell_y","source":"derived",
                         "level_evidence":"spell_level: 法师 1","matched_by":"derived_new"},
                        {"cn":"燃烧之手","en":"Burning Hands","book":"CRB",
                         "chunk_id":"spell_Spell CRB_0057","source":"official_list"}
                      ]}}
                    }}
                    """;
        }

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
