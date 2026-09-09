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
}
