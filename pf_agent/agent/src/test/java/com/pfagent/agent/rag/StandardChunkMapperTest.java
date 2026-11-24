package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.springframework.ai.document.Document;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * StandardChunkMapper 单元测试
 *
 * 验证六个标准模块（专长/种族/背景特性/装备/技能/规则）共用的统一映射：
 * 顶部字段 1:1 → metadata 对齐统一来源约定；chm_toc_path → tocPath 溯源路径；
 * aliases 合并为逗号分隔；null 字段安全兜底。
 */
class StandardChunkMapperTest {

    private final StandardChunkMapper mapper = new StandardChunkMapper();

    /** 对齐统一来源字段并保留模块通用元数据 */
    @Test
    void toDocumentAlignsSourceKeepsGenericMetadata() {
        StandardChunk c = new StandardChunk(
                "feat_page_1_0000", "page_1", "专长", "feat", "猛力攻击（Power Attack）", "猛力攻击正文",
                "CRB", "核心规则书", "Core Rulebook", 75, "专长 → 战斗专长",
                List.of("猛力攻击", "PA"), Map.of("feat_type", "战斗"), Map.of());

        Document doc = mapper.toDocument(c);

        assertThat(doc.getText()).isEqualTo("猛力攻击正文");
        Map<String, Object> meta = doc.getMetadata();
        assertThat(meta.get("chunk_id")).isEqualTo("feat_page_1_0000");
        assertThat(meta.get("doc_id")).isEqualTo("page_1");
        assertThat(meta.get("category")).isEqualTo("专长");
        assertThat(meta.get("component_type")).isEqualTo("feat");
        assertThat(meta.get("title")).isEqualTo("猛力攻击（Power Attack）");
        assertThat(meta.get("book_name_cn")).isEqualTo("核心规则书");
        assertThat(meta.get("book_name_en")).isEqualTo("Core Rulebook");
        assertThat(meta.get("book_abbreviation")).isEqualTo("CRB");
        assertThat(meta.get("tocPath")).isEqualTo("专长 → 战斗专长");
        assertThat(meta.get("aliases")).isEqualTo("猛力攻击, PA");
    }

    /** chmTocPath 缺失时回退为 docId 加 title 拼接 */
    @Test
    void toDocumentMissingTocPathFallsBackToDocIdTitle() {
        StandardChunk c = new StandardChunk(
                "c1", "page_9", "规则", "rule_section", "腐化（Corruption）", "正文",
                "HA", "恐怖冒险", "Horror Adventures", 75, null, null, null, null);

        Document doc = mapper.toDocument(c);

        assertThat(doc.getMetadata().get("tocPath")).isEqualTo("page_9 > 腐化（Corruption）");
    }

    /** 背景特性 nested trait_type 扁平化为逗号字符串；空 list 显式空串 */
    @Test
    void toDocumentFlattensTraitTypeAndKeepsEmptyForMissingType() {
        StandardChunk filled = new StandardChunk(
                "trait_1", "page_1", "trait", "trait", "纵火狂", "正文",
                "QaC", "任务与战役", "Quests and Campaigns", 50, "未整理 → 任务与战役 → 背景特性",
                List.of("Firebug"), Map.of("trait_type", List.of("战斗")), Map.of());
        StandardChunk empty = new StandardChunk(
                "trait_2", "page_2", "trait", "trait", "规避意外", "正文",
                "ISG", "内海诸神", "Inner Sea Gods", 50, "未整理 → 内海诸神ISG → 背景特性",
                List.of(), Map.of("trait_type", List.of()), Map.of());

        assertThat(mapper.toDocument(filled).getMetadata().get("trait_type")).isEqualTo("战斗");
        assertThat(mapper.toDocument(empty).getMetadata().get("trait_type")).isEqualTo("");
    }

    @Test
    void toDocumentFlattensRaceNames() {
        StandardChunk c = new StandardChunk(
                "race_page_812_0002", "page_812", "race", "race_trait", "属性调整", "正文",
                "?", "未知来源", "Unknown", 0, "种族 → 怪物种族 → 阿斯托莫伊人",
                List.of("Astomoi"), Map.of("race_name", "阿斯托莫伊人", "race_name_en", "Astomoi"), Map.of());

        Map<String, Object> metadata = mapper.toDocument(c).getMetadata();

        assertThat(metadata.get("race_name")).isEqualTo("阿斯托莫伊人");
        assertThat(metadata.get("race_name_en")).isEqualTo("Astomoi");
    }

    @Test
    void toDocumentSkipsBlankRaceNames() {
        StandardChunk c = new StandardChunk(
                "race_1", "page_1", "race", "race_intro", "空名", "正文",
                "?", "未知来源", "Unknown", 0, "种族 → 空名",
                List.of(), Map.of("race_name", "", "race_name_en", "Astomoi"), Map.of());

        Map<String, Object> metadata = mapper.toDocument(c).getMetadata();

        assertThat(metadata).doesNotContainKey("race_name");
        assertThat(metadata.get("race_name_en")).isEqualTo("Astomoi");
    }

    /** null 字段安全兜底 */
    @Test
    void toDocumentNullFieldsFallbackSafely() {
        StandardChunk c = new StandardChunk(
                null, null, null, null, null, null, null, null, null, null, null, null, null, null);

        Document doc = mapper.toDocument(c);

        assertThat(doc.getText()).isEqualTo("");
        assertThat(doc.getMetadata().get("tocPath")).isEqualTo(" > ");
        assertThat(doc.getMetadata().get("aliases")).isEqualTo("");
    }

    /** AKN-022：record 组件改驼峰后，JSONL 的下划线键仍能正确反序列化 */
    @Test
    void deserializesLegacyUnderscoreJsonKeys() throws Exception {
        String json = """
                {"chunk_id":"c1","doc_id":"page_1","category":"专长","component_type":"feat",
                 "title":"猛力攻击","text":"正文","book_abbreviation":"CRB",
                 "book_name_cn":"核心规则书","book_name_en":"Core Rulebook",
                 "source_confidence":75,"chm_toc_path":"专长 → 战斗专长",
                 "aliases":["猛力攻击"],"metadata":{"feat_type":"战斗"},"extra":{}}
                """;

        StandardChunk c = new com.fasterxml.jackson.databind.ObjectMapper()
                .readValue(json, StandardChunk.class);

        assertThat(c.chunkId()).isEqualTo("c1");
        assertThat(c.docId()).isEqualTo("page_1");
        assertThat(c.componentType()).isEqualTo("feat");
        assertThat(c.bookAbbreviation()).isEqualTo("CRB");
        assertThat(c.bookNameCn()).isEqualTo("核心规则书");
        assertThat(c.bookNameEn()).isEqualTo("Core Rulebook");
        assertThat(c.sourceConfidence()).isEqualTo(75);
        assertThat(c.chmTocPath()).isEqualTo("专长 → 战斗专长");
        assertThat(c.aliases()).containsExactly("猛力攻击");
    }
}
