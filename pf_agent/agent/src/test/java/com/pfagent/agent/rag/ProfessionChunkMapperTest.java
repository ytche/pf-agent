package com.pfagent.agent.rag;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.ai.document.Document;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * ProfessionChunkMapper 单元测试
 *
 * 验证职业 StandardChunk → Document 映射：复用 StandardChunkMapper 统一映射
 * （来源书 / tocPath / title 对齐溯源约定），并把 nested metadata 的职业字段扁平化
 * 为顶层键 class_name / archetype_name / feature_subtype（FilterTranslator.translateClass
 * 结构化过滤的目标键）。约半数 chunk 无 archetype_name / feature_subtype（class_overview /
 * 基础职业 feature 不挂变体），缺省键须安全跳过——null 变体是本测试的必测项。
 */
class ProfessionChunkMapperTest {

    private final ProfessionChunkMapper mapper = new ProfessionChunkMapper();

    /** 注入基础映射器（生产环境由 Spring @Autowired 注入） */
    @BeforeEach
    void setUp() {
        ReflectionTestUtils.setField(mapper, "baseMapper", new StandardChunkMapper());
    }

    /** 基础映射保留 + 三职业字段扁平化为顶层键 */
    @Test
    void toDocumentFlattensProfessionFieldsKeepingBaseMapping() {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("class_name", "女巫");
        metadata.put("archetype_name", "hedge_witch");
        metadata.put("feature_subtype", "hex");
        StandardChunk c = new StandardChunk(
                "prof_31_0003", "page_31", "职业", "class_feature", "巫术（Hex）", "巫术正文",
                "CRB", "核心规则书", "Core Rulebook", 80, "职业 → 女巫",
                List.of("女巫", "Witch"), metadata, Map.of());

        Document doc = mapper.toDocument(c);

        assertThat(doc.getText()).isEqualTo("巫术正文");
        Map<String, Object> meta = doc.getMetadata();
        // 基础映射（StandardChunkMapper 统一约定）保留
        assertThat(meta.get("chunk_id")).isEqualTo("prof_31_0003");
        assertThat(meta.get("book_name_cn")).isEqualTo("核心规则书");
        assertThat(meta.get("book_name_en")).isEqualTo("Core Rulebook");
        assertThat(meta.get("book_abbreviation")).isEqualTo("CRB");
        assertThat(meta.get("tocPath")).isEqualTo("职业 → 女巫");
        assertThat(meta.get("title")).isEqualTo("巫术（Hex）");
        assertThat(meta.get("aliases")).isEqualTo("女巫, Witch");
        // 职业扁平键
        assertThat(meta.get("class_name")).isEqualTo("女巫");
        assertThat(meta.get("archetype_name")).isEqualTo("hedge_witch");
        assertThat(meta.get("feature_subtype")).isEqualTo("hex");
    }

    /** metadata 为 null（约半数 chunk 无变体字段）时职业键全部安全跳过 */
    @Test
    void toDocumentNullMetadataSkipsProfessionKeys() {
        StandardChunk c = new StandardChunk(
                "prof_1_0000", "page_1", "职业", "class_overview", "圣骑士（Paladin）", "圣骑士正文",
                "CRB", "核心规则书", "Core Rulebook", 80, "职业 → 核心职业 → 圣骑士",
                null, null, null);

        Document doc = mapper.toDocument(c);

        assertThat(doc.getText()).isEqualTo("圣骑士正文");
        Map<String, Object> meta = doc.getMetadata();
        assertThat(meta.get("class_name")).isNull();
        assertThat(meta.get("archetype_name")).isNull();
        assertThat(meta.get("feature_subtype")).isNull();
        // 基础映射不受影响
        assertThat(meta.get("book_name_cn")).isEqualTo("核心规则书");
    }

    /** 仅含 class_name（基础职业 feature 不挂变体）时缺失键安全跳过 */
    @Test
    void toDocumentPartialMetadataSkipsMissingKeys() {
        StandardChunk c = new StandardChunk(
                "prof_2_0001", "page_2", "职业", "class_feature", "兽群直觉（Group Intuition）", "正文",
                "KIS", "王者之书", "Kobold Quarterly", 75, "职业 → 核心职业 → 猎人",
                List.of(), Map.of("class_name", "猎人"), Map.of());

        Document doc = mapper.toDocument(c);

        Map<String, Object> meta = doc.getMetadata();
        assertThat(meta.get("class_name")).isEqualTo("猎人");
        assertThat(meta.get("archetype_name")).isNull();
        assertThat(meta.get("feature_subtype")).isNull();
    }
}
