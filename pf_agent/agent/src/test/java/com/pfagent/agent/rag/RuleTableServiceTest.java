package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * RuleTableService 单元测试（KN221，spec D8~D11）
 *
 * 覆盖加载与查询契约（夹具按 M44 交付的 rule_tables.json version=1.0 结构编写）：
 *  - 加载：tables 对象字典（键=table_id）、分 layout 计数
 *  - find：table_id 精确 > chunk_id（同 chunk 多表全返回）> 表名精确 > 子串模糊；
 *    多命中不猜、空/未知返回空；空表题只能按 table_id/chunk_id 查
 *  - formatTable：standard 表头 + 20 行上限 + 总行数；row 兼容 5/5级/第5行；
 *    任意单元格匹配；行未命中给可用行键；header_inferred 提示
 *  - formatTable：flattened 只返回原文行并标降级，不伪造表头/列级值
 *  - provenanceDocument：真实 chunk 优先；点查未命中/未注入降级合成并保留 chunk_id/doc_id
 *  - 产物缺失/解析失败：available=false，不炸启动
 */
class RuleTableServiceTest {

    @TempDir
    Path tempDir;

    /** 加载：表字典 + 分 layout 计数（standard 5 / flattened 2 / no_separator 1） */
    @Test
    void loadBuildsTablesAndIndexes() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());

        assertThat(service.isAvailable()).isTrue();
        assertThat(service.tableCount()).isEqualTo(8);
        assertThat(service.allTables().stream().map(RuleTableService.RuleTable::layout))
                .containsExactly("standard", "standard", "standard", "standard", "standard",
                        "flattened", "flattened", "no_separator");
    }

    /** table_id 精确命中：唯一返回，不受同名表影响 */
    @Test
    void findByIdIsExactAndUnique() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());

        List<RuleTableService.RuleTable> hits = service.find("rule_page_299_0000#t1");

        assertThat(hits).hasSize(1);
        assertThat(hits.get(0).title()).isEqualTo("动物伙伴基本数据");
        assertThat(hits.get(0).rowCount()).isEqualTo(20);
    }

    /** chunk_id 命中：同 chunk 多表全部返回（由工具要求消歧），不猜第一张 */
    @Test
    void findByChunkIdReturnsAllTablesInChunk() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());

        List<RuleTableService.RuleTable> hits = service.find("rule_page_299_0000");

        assertThat(hits).extracting(RuleTableService.RuleTable::tableId)
                .containsExactly("rule_page_299_0000#t1", "rule_page_299_0000#t2");
    }

    /** 表名精确（title/caption）命中；空白与全半角差异经归一化后仍命中 */
    @Test
    void findByExactTitleWithNormalization() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());

        assertThat(service.find("动物伙伴基本数据")).hasSize(1);
        assertThat(service.find("  动物伙伴基本数据  ")).hasSize(1);
        // 带「表：」前缀的提问形态 → 子串模糊（全角冒号归一后 query 包含表名）
        assertThat(service.find("表：动物伙伴基本数据")).hasSize(1);
    }

    /** 同名表精确命中多张 → 全部返回（歧义候选），不猜 */
    @Test
    void findAmbiguousTitleReturnsAllCandidates() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());

        List<RuleTableService.RuleTable> hits = service.find("状态数值表");

        assertThat(hits).hasSize(2);
        assertThat(hits).extracting(RuleTableService.RuleTable::chunkId)
                .containsExactly("rule_page_120_0000", "rule_page_121_0000");
    }

    /** 子串模糊：命中多张同主题表，全部返回候选 */
    @Test
    void findFuzzySubstringReturnsCandidates() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());

        List<RuleTableService.RuleTable> hits = service.find("动物伙伴");

        assertThat(hits).extracting(RuleTableService.RuleTable::tableId)
                .containsExactly("rule_page_299_0000#t1", "rule_page_299_0000#t2");
    }

    /** 空表题（空壳/断行表）不能被空串或短单字模糊命中；table_id 仍可查 */
    @Test
    void emptyTitleIsOnlyReachableByTableId() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());

        assertThat(service.find("")).isEmpty();
        assertThat(service.find("  ")).isEmpty();
        assertThat(service.find("表")).isEmpty();
        assertThat(service.find("rule_page_999_0000#t1")).hasSize(1);
        assertThat(service.formatTable(service.find("rule_page_999_0000#t1").get(0), null))
                .contains("(无表题)", "rule_page_999_0000#t1");
    }

    /** 未收录表名返回空（工具据此给可读提示，不编造） */
    @Test
    void findUnknownReturnsEmpty() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());

        assertThat(service.find("不存在的表")).isEmpty();
        assertThat(service.find(null)).isEmpty();
    }

    /** standard 无 row：表头 + 全部 20 行 + 总行数；不越界展示第 21 行 */
    @Test
    void formatStandardWithoutRowListsHeaderAndAllRows() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());
        RuleTableService.RuleTable table = service.find("rule_page_299_0000#t1").get(0);

        String text = service.formatTable(table, null);

        assertThat(text).contains("layout=standard", "共 20 行", "表头: 等级 |  | HD |  | BAB");
        assertThat(text).contains("行 1: 1 |  | 1 |  | +0");
        assertThat(text).contains("行 5: 5 |  | 5 |  | +3");
        assertThat(text).contains("行 20:");
        assertThat(text).doesNotContain("行 21:");
    }

    /** 超过 20 行时截断并提示总行数与取行方式 */
    @Test
    void formatStandardCapsAtTwentyRowsAndHintsTotal() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());
        RuleTableService.RuleTable table = service.find("rule_page_130_0000#t1").get(0);

        String text = service.formatTable(table, null);

        assertThat(text).contains("行 20:");
        assertThat(text).doesNotContain("行 21:");
        assertThat(text).contains("共 25 行，仅展示前 20 行", "row=\"5\"");
    }

    /** row 兼容 5 / 5级 / 第5行：都只返回第 5 行且 HD=5、BAB=+3（spec §6 验收） */
    @Test
    void formatStandardRowAcceptsLevelAndOrdinalForms() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());
        RuleTableService.RuleTable table = service.find("rule_page_299_0000#t1").get(0);

        for (String row : List.of("5", "5级", "第5行", " 第 5 行 ")) {
            String text = service.formatTable(table, row);
            assertThat(text).contains("命中 1 行", "行 5: 5 |  | 5 |  | +3")
                    .as("row=%s", row);
        }
    }

    /** row 首列未命中时按任意单元格匹配（+3 命中 BAB 列，第 4/5 行均为 +3） */
    @Test
    void formatStandardRowFallsBackToAnyCell() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());
        RuleTableService.RuleTable table = service.find("rule_page_299_0000#t1").get(0);

        String text = service.formatTable(table, "+3");

        assertThat(text).contains("命中 2 行", "行 4:", "行 5:");
    }

    /** row 未命中：如实说明 + 表头 + 可用行键，不编造数值 */
    @Test
    void formatStandardRowMissShowsAvailableKeys() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());
        RuleTableService.RuleTable table = service.find("rule_page_299_0000#t1").get(0);

        String text = service.formatTable(table, "99");

        assertThat(text).contains("未找到与 row=\"99\" 匹配的行", "表头:");
        assertThat(text).contains("可用行键（前 20 行首列）: 1、2、3");
        assertThat(text).doesNotContain("行 99:");
    }

    /** no_separator：表头按首行推断，返回时显式提示 */
    @Test
    void formatNoSeparatorMarksInferredHeader() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());
        RuleTableService.RuleTable table = service.find("rule_page_140_0000#t1").get(0);

        String text = service.formatTable(table, "2");

        assertThat(text).contains("layout=no_separator", "表头: 甲 | 乙",
                "表头按首行推断", "命中 1 行", "行 2: 2 | 乙2");
    }

    /** flattened 无 row：只返回原文行并标降级，不伪造表头/列级值 */
    @Test
    void formatFlattenedReturnsRawLinesWithDegradationNote() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());
        RuleTableService.RuleTable table = service.find("rule_page_644_0000#t1").get(0);

        String text = service.formatTable(table, null);

        assertThat(text).contains("layout=flattened", "无法可靠还原列结构", "不承诺列级对应");
        assertThat(text).contains("| 生命骰 | 能量抗力 | 伤害减免 |");
        assertThat(text).doesNotContain("表头:");
    }

    /** flattened 数字 row：按表内原文行号取行（第 1 行为分隔行也如实返回） */
    @Test
    void formatFlattenedNumericRowSelectsRawLine() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());
        RuleTableService.RuleTable table = service.find("rule_page_644_0000#t1").get(0);

        assertThat(service.formatTable(table, "1")).contains("行 1: | 生命骰 | 能量抗力 | 伤害减免 |");
        assertThat(service.formatTable(table, "2")).contains("行 2: | --- | --- | --- |");
        assertThat(service.formatTable(table, "9")).contains("超出该表原文行数（共 2 行）");
    }

    /** flattened 文本 row：按原文内容匹配并保留降级说明 */
    @Test
    void formatFlattenedTextRowMatchesRawContent() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());
        RuleTableService.RuleTable table = service.find("rule_page_644_0000#t1").get(0);

        String text = service.formatTable(table, "能量抗力");

        assertThat(text).contains("无法可靠还原列结构", "原文匹配 1 行", "| 生命骰 | 能量抗力 | 伤害减免 |");
    }

    /** 歧义候选清单包含 table_id/chunk_id/layout/行数，并给消歧指引 */
    @Test
    void formatCandidatesListsIdentityForDisambiguation() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());
        List<RuleTableService.RuleTable> hits = service.find("状态数值表");

        String text = service.formatCandidates("状态数值表", hits);

        assertThat(text).contains("命中 2 张表", "请改用 table_id 或 chunk_id");
        assertThat(text).contains("rule_page_120_0000#t1", "layout:standard", "1 行");
        assertThat(text).contains("rule_page_121_0000#t1");
    }

    /** 溯源：点查命中真实 chunk 时原样返回（不合成） */
    @Test
    void provenanceDocumentPrefersRealChunk() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());
        SearchService searchService = mock(SearchService.class);
        ReflectionTestUtils.setField(service, "searchService", searchService);
        Document real = Document.builder().text("真实原文")
                .metadata(Map.of("chunk_id", "rule_page_299_0000")).build();
        when(searchService.getByChunkId("rule", "rule_page_299_0000")).thenReturn(real);

        Document doc = service.provenanceDocument(service.find("rule_page_299_0000#t1").get(0));

        assertThat(doc).isSameAs(real);
    }

    /** 溯源：点查未命中 → 合成 Document 含 title/chunk_id/doc_id/table_id 与原文行 */
    @Test
    void provenanceDocumentFallsBackToSyntheticDoc() throws Exception {
        RuleTableService service = loaded(Fixtures.validJson());
        SearchService searchService = mock(SearchService.class);
        ReflectionTestUtils.setField(service, "searchService", searchService);
        when(searchService.getByChunkId("rule", "rule_page_299_0000")).thenReturn(null);

        Document doc = service.provenanceDocument(service.find("rule_page_299_0000#t1").get(0));

        assertThat(doc.getMetadata().get("title")).isEqualTo("动物伙伴基本数据");
        assertThat(doc.getMetadata().get("chunk_id")).isEqualTo("rule_page_299_0000");
        assertThat(doc.getMetadata().get("doc_id")).isEqualTo("page_299");
        assertThat(doc.getMetadata().get("table_id")).isEqualTo("rule_page_299_0000#t1");
        assertThat(doc.getText()).contains("| 表：动物伙伴基本数据 |");
    }

    /** 文件缺失降级：available=false、查询空、不抛 */
    @Test
    void missingFileDegradesGracefully() {
        RuleTableService service = service(tempDir.resolve("nope.json").toString());

        service.load();

        assertThat(service.isAvailable()).isFalse();
        assertThat(service.tableCount()).isZero();
        assertThat(service.find("动物伙伴基本数据")).isEmpty();
    }

    /** 解析失败降级：available=false，不抛 */
    @Test
    void malformedFileDegradesGracefully() throws Exception {
        Path bad = tempDir.resolve("bad.json");
        Files.writeString(bad, "{ not json ", StandardCharsets.UTF_8);
        RuleTableService service = service(bad.toString());

        service.load();

        assertThat(service.isAvailable()).isFalse();
        assertThat(service.find("x")).isEmpty();
    }

    private RuleTableService loaded(String json) throws Exception {
        Path file = tempDir.resolve("rule_tables.json");
        Files.writeString(file, json, StandardCharsets.UTF_8);
        RuleTableService service = service(file.toString());
        service.load();
        return service;
    }

    private RuleTableService service(String filePath) {
        RuleTableService service = new RuleTableService();
        ReflectionTestUtils.setField(service, "filePath", filePath);
        return service;
    }

    /** rule_tables.json version=1.0 结构 fixture（M44 契约：tables 为对象字典） */
    static final class Fixtures {

        static String validJson() {
            return """
                    {
                      "version": "1.0",
                      "category": "rule",
                      "generated_at": "2026-11-12T00:00:00Z",
                      "generated_from": "vectorizer/output/规则/chunks.jsonl",
                      "source_fingerprint": "0000000000000000000000000000000000000000000000000000000000000000",
                      "table_id_index_base": 1,
                      "counts": {"tables": 8, "chunks": 7},
                      "tables": {
                        "rule_page_299_0000#t1": {
                          "table_id": "rule_page_299_0000#t1",
                          "chunk_id": "rule_page_299_0000",
                          "doc_id": "page_299",
                          "index": 1,
                          "layout": "standard",
                          "caption": "动物伙伴基本数据",
                          "title": "动物伙伴基本数据",
                          "headers": ["等级", "", "HD", "", "BAB"],
                          "rows": %s,
                          "header_inferred": false,
                          "row_count": 20,
                          "line_start": 3,
                          "line_end": 24,
                          "raw_lines": ["| 表：动物伙伴基本数据 |", "| --- |", "| 等级 |  | HD |  | BAB |"]
                        },
                        "rule_page_299_0000#t2": {
                          "table_id": "rule_page_299_0000#t2",
                          "chunk_id": "rule_page_299_0000",
                          "doc_id": "page_299",
                          "index": 2,
                          "layout": "standard",
                          "caption": "",
                          "title": "动物伙伴进阶数据",
                          "headers": ["等级", "特殊"],
                          "rows": [["1", "追击"], ["2", "多重攻击"]],
                          "header_inferred": false,
                          "row_count": 2,
                          "line_start": 30,
                          "line_end": 33,
                          "raw_lines": ["| 等级 | 特殊 |", "| --- | --- |"]
                        },
                        "rule_page_120_0000#t1": {
                          "table_id": "rule_page_120_0000#t1",
                          "chunk_id": "rule_page_120_0000",
                          "doc_id": "page_120",
                          "index": 1,
                          "layout": "standard",
                          "caption": "",
                          "title": "状态数值表",
                          "headers": ["状态", "效果"],
                          "rows": [["眩晕", "无法行动"]],
                          "header_inferred": false,
                          "row_count": 1,
                          "line_start": 5,
                          "line_end": 8,
                          "raw_lines": ["| 状态 | 效果 |", "| --- | --- |", "| 眩晕 | 无法行动 |"]
                        },
                        "rule_page_121_0000#t1": {
                          "table_id": "rule_page_121_0000#t1",
                          "chunk_id": "rule_page_121_0000",
                          "doc_id": "page_121",
                          "index": 1,
                          "layout": "standard",
                          "caption": "",
                          "title": "状态数值表",
                          "headers": ["状态", "效果"],
                          "rows": [["目盲", "失去敏捷加值"]],
                          "header_inferred": false,
                          "row_count": 1,
                          "line_start": 2,
                          "line_end": 5,
                          "raw_lines": ["| 状态 | 效果 |", "| --- | --- |", "| 目盲 | 失去敏捷加值 |"]
                        },
                        "rule_page_130_0000#t1": {
                          "table_id": "rule_page_130_0000#t1",
                          "chunk_id": "rule_page_130_0000",
                          "doc_id": "page_130",
                          "index": 1,
                          "layout": "standard",
                          "caption": "",
                          "title": "大型数值表",
                          "headers": ["行号", "数值"],
                          "rows": %s,
                          "header_inferred": false,
                          "row_count": 25,
                          "line_start": 4,
                          "line_end": 31,
                          "raw_lines": ["| 行号 | 数值 |", "| --- | --- |"]
                        },
                        "rule_page_644_0000#t1": {
                          "table_id": "rule_page_644_0000#t1",
                          "chunk_id": "rule_page_644_0000",
                          "doc_id": "page_644",
                          "index": 1,
                          "layout": "flattened",
                          "caption": "",
                          "title": "生命骰",
                          "headers": [],
                          "rows": [],
                          "header_inferred": false,
                          "row_count": 2,
                          "line_start": 6,
                          "line_end": 7,
                          "raw_lines": ["| 生命骰 | 能量抗力 | 伤害减免 |", "| --- | --- | --- |"]
                        },
                        "rule_page_999_0000#t1": {
                          "table_id": "rule_page_999_0000#t1",
                          "chunk_id": "rule_page_999_0000",
                          "doc_id": "page_999",
                          "index": 1,
                          "layout": "flattened",
                          "caption": "",
                          "title": "",
                          "headers": [],
                          "rows": [],
                          "header_inferred": false,
                          "row_count": 0,
                          "line_start": 9,
                          "line_end": 10,
                          "raw_lines": ["|  |  |", "| --- | --- |"]
                        },
                        "rule_page_140_0000#t1": {
                          "table_id": "rule_page_140_0000#t1",
                          "chunk_id": "rule_page_140_0000",
                          "doc_id": "page_140",
                          "index": 1,
                          "layout": "no_separator",
                          "caption": "",
                          "title": "甲",
                          "headers": ["甲", "乙"],
                          "rows": [["1", "乙1"], ["2", "乙2"]],
                          "header_inferred": true,
                          "row_count": 2,
                          "line_start": 2,
                          "line_end": 5,
                          "raw_lines": ["| 甲 | 乙 |", "| 1 | 乙1 |", "| 2 | 乙2 |"]
                        }
                      }
                    }
                    """.formatted(animalRowsJson(), bigRowsJson());
        }

        private static String animalRowsJson() {
            List<String> rows = new ArrayList<>();
            for (int level = 1; level <= 20; level++) {
                int bab = (int) Math.floor(level * 3 / 4.0);
                rows.add("[\"" + level + "\", \"\", \"" + level + "\", \"\", \"+" + bab + "\"]");
            }
            return "[" + String.join(", ", rows) + "]";
        }

        private static String bigRowsJson() {
            List<String> rows = new ArrayList<>();
            for (int i = 1; i <= 25; i++) {
                rows.add("[\"" + i + "\", \"" + (i * 10) + "\"]");
            }
            return "[" + String.join(", ", rows) + "]";
        }
    }
}
