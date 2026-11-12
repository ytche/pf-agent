package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * ClassTableService 边界与盲区补充测试（QA 白盒审计追加，2026-09-22）
 *
 * 审计 coder 19 条测试后的补充覆盖：
 *  - 别名冲突：两个职业别名互相串（buildAliasIndex putIfAbsent 首登记优先）的行为固化
 *  - 溯源点查未命中降级：searchService.getByChunkId 返回 null → 合成 Document 仍含
 *    chunk_id/doc_id（且由 RetrievalTools 统一进 SourceCollector）
 *  - 溯源点查命中：真实 chunk 原样返回
 *  - coverage.resolved_via 的键查询行为：resolve() 消费 resolved_via 做跨键解析
 *    （骑士→骑将），目标不在 classes 内不硬匹配（QA-J5-1 修复后契约）
 *  - spells 环位键数值排序（"10" 须排在 "9" 后，非字典序）
 *  - 稀疏 levels（max_level=20 但只有部分等级键）时 formatTable 不抛异常
 */
class ClassTableServiceBoundaryTest {

    @TempDir
    Path tempDir;

    // ---------- 别名冲突 ----------

    /** 后加载职业的别名与先加载职业规范名撞车：putIfAbsent 首登记优先，不互相串 */
    @Test
    void aliasConflictCanonicalNameWinsForFirstRegistered() throws Exception {
        String json = """
                {
                  "classes": {
                    "战士": {"max_level": 20, "has_spell_table": false,
                             "levels": {"1": {"bab": "+1"}}},
                    "战斗士": {"aliases": ["战士"], "max_level": 20, "has_spell_table": false,
                               "levels": {"1": {"bab": "+0"}}}
                  },
                  "coverage": {"parsed": ["战士", "战斗士"], "missing": []}
                }
                """;
        ClassTableService service = loaded(json);

        // JSON 序：战士先登记；"战斗士"的别名"战士"被 putIfAbsent 忽略 → 不串
        assertThat(service.resolve("战士")).isEqualTo("战士");
        assertThat(service.resolve("战斗士")).isEqualTo("战斗士");
        assertThat(service.formatRow("战士", 1)).contains("BAB +1");
    }

    /** 两个职业抢同一英文别名（大小写折叠后撞车）：先登记者优先，行为固化 */
    @Test
    void aliasConflictSharedEnglishAliasFirstWins() throws Exception {
        String json = """
                {
                  "classes": {
                    "法师": {"aliases": ["Mage"], "max_level": 20, "has_spell_table": true,
                             "levels": {"1": {"bab": "+0", "spells": {"0": 3}}}},
                    "术士": {"aliases": ["mage"], "max_level": 20, "has_spell_table": true,
                             "levels": {"1": {"bab": "+0", "spells": {"0": 4}}}}
                  },
                  "coverage": {"parsed": ["法师", "术士"], "missing": []}
                }
                """;
        ClassTableService service = loaded(json);

        assertThat(service.resolve("MAGE")).isEqualTo("法师");   // 小写登记先到法师
        assertThat(service.resolve("术士")).isEqualTo("术士");   // 规范名自身不受影响
    }

    // ---------- 溯源降级 ----------

    /** 点查命中：getByChunkId 返回真实 chunk 时原样返回（不包一层合成） */
    @Test
    void provenanceReturnsRealChunkWhenLookupHits() throws Exception {
        ClassTableService service = loaded(Fixtures.minimalJson());
        SearchService searchService = mock(SearchService.class);
        ReflectionTestUtils.setField(service, "searchService", searchService);
        Document real = Document.builder().text("表：法师 原文").metadata(java.util.Map.of("title", "表：法师")).build();
        when(searchService.getByChunkId("class", "class_page_66_0001")).thenReturn(real);

        Document doc = service.provenanceDocument("法师");

        assertThat(doc).isSameAs(real);
        verify(searchService).getByChunkId("class", "class_page_66_0001");
    }

    /** 点查未命中（向量库版本错位）：warn + 合成 Document 仍带 chunk_id/doc_id，供 SourceCollector 挂 [#N] */
    @Test
    void provenanceFallsBackToSyntheticDocWhenLookupMisses() throws Exception {
        ClassTableService service = loaded(Fixtures.minimalJson());
        SearchService searchService = mock(SearchService.class);
        ReflectionTestUtils.setField(service, "searchService", searchService);
        when(searchService.getByChunkId("class", "class_page_66_0001")).thenReturn(null);

        Document doc = service.provenanceDocument("法师");

        assertThat(doc.getMetadata().get("title")).isEqualTo("法师职业成长表");
        assertThat(doc.getMetadata().get("chunk_id")).isEqualTo("class_page_66_0001");
        assertThat(doc.getMetadata().get("doc_id")).isEqualTo("核心职业/法师/page_66.md");
        assertThat(doc.getText()).contains("向量库未检索到");
    }

    /** 职业本身未收录：合成仅含 title 的空 text Document，不抛 */
    @Test
    void provenanceUnknownClassReturnsTitleOnlyDoc() throws Exception {
        ClassTableService service = loaded(Fixtures.minimalJson());

        Document doc = service.provenanceDocument("不存在的职业");

        assertThat(doc.getMetadata().get("title")).isEqualTo("不存在的职业职业成长表");
        assertThat(doc.getText()).isEmpty();
    }

    // ---------- coverage.resolved_via 行为 ----------

    /** resolved_via 被 resolve 消费（QA-J5-1 修复后契约）：骑士→骑将 命中收录键；
     *  映射目标不在 classes 内（召唤师(掉链子)→召唤师）不硬匹配，且不进 missingClasses */
    @Test
    void resolvedViaKeysAreConsumedByResolve() throws Exception {
        String json = """
                {
                  "classes": {
                    "骑将": {"max_level": 20, "has_spell_table": false,
                             "levels": {"1": {"bab": "+1"}}}
                  },
                  "coverage": {
                    "parsed": ["骑将"],
                    "missing": [],
                    "resolved_via": {"骑士": "骑将", "召唤师(掉链子)": "召唤师"}
                  }
                }
                """;
        ClassTableService service = loaded(json);

        assertThat(service.resolve("骑士")).isEqualTo("骑将");   // resolved_via 消费：跨键解析命中
        assertThat(service.resolve("骑将")).isEqualTo("骑将");   // 规范名本身可查
        assertThat(service.resolve("召唤师(掉链子)")).isNull(); // 目标不在 classes → 不硬匹配
        assertThat(service.missingClasses()).doesNotContain("骑士"); // 也不在缺口名单
    }

    // ---------- spells 排序与稀疏等级 ----------

    /** 环位键按数值排序："10" 排在 "9" 之后（字典序会排反） */
    @Test
    void formatSpellsSortsRingsNumericallyNotLexicographically() throws Exception {
        String json = """
                {
                  "classes": {
                    "法师": {"max_level": 20, "has_spell_table": true,
                             "levels": {"20": {"bab": "+10", "spells": {"9": 2, "10": 1, "2": 4}}}}
                  },
                  "coverage": {"parsed": ["法师"], "missing": []}
                }
                """;
        ClassTableService service = loaded(json);

        String row = service.formatRow("法师", 20);

        int i2 = row.indexOf("2环4");
        int i9 = row.indexOf("9环2");
        int i10 = row.indexOf("10环1");
        assertThat(i2).isGreaterThan(-1);
        assertThat(i2).isLessThan(i9);
        assertThat(i9).isLessThan(i10);
    }

    /** 稀疏 levels（max_level=20 仅 2 个等级键）：formatTable 逐行给占位文案，不抛异常 */
    @Test
    void formatTableWithSparseLevelsDoesNotThrow() throws Exception {
        String json = """
                {
                  "classes": {
                    "战士": {"max_level": 3, "has_spell_table": false,
                             "levels": {"2": {"bab": "+2"}}}
                  },
                  "coverage": {"parsed": ["战士"], "missing": []}
                }
                """;
        ClassTableService service = loaded(json);

        String table = service.formatTable("战士");

        assertThat(table).contains("「战士」成长表（1~3 级）");
        assertThat(table).contains("等级 1 无成长表数据");
        assertThat(table).contains("「战士」等级 2", "BAB +2");
        assertThat(table).contains("等级 3 无成长表数据");
    }

    // ---------- helpers ----------

    private ClassTableService loaded(String json) throws Exception {
        Path file = tempDir.resolve("class_tables.json");
        Files.writeString(file, json, StandardCharsets.UTF_8);
        ClassTableService service = new ClassTableService();
        ReflectionTestUtils.setField(service, "filePath", file.toString());
        service.load();
        return service;
    }

    static final class Fixtures {
        static String minimalJson() {
            return """
                    {
                      "classes": {
                        "法师": {
                          "source_chunk_id": "class_page_66_0001",
                          "source_doc_id": "核心职业/法师/page_66.md",
                          "max_level": 20,
                          "has_spell_table": true,
                          "levels": {"1": {"bab": "+0", "spells": {"0": 3}}}
                        }
                      },
                      "coverage": {"parsed": ["法师"], "missing": []}
                    }
                    """;
        }
    }
}
