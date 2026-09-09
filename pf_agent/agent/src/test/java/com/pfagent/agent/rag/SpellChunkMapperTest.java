package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;
import org.springframework.ai.document.Document;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * SpellChunkMapper 单元测试
 *
 * 验证法术 chunk → Document 的映射：文本进 text，来源/目录/别名进
 * 统一约定 metadata，null 字段安全兜底。
 */
class SpellChunkMapperTest {

    private final SpellChunkMapper mapper = new SpellChunkMapper();

    /** 映射文本与来源追溯 metadata */
    @Test
    void toDocumentMapsTextAndSourceTraceabilityMetadata() {
        SpellChunk c = new SpellChunk(
                "spell_CRB_0001", "法术 > 火球术", "spell", "spell", "火球术", "火球术正文",
                "CRB", "核心规则书", "Core Rulebook", 1, List.of("火球"), Map.of(), Map.of());

        Document doc = mapper.toDocument(c);

        assertThat(doc.getText()).isEqualTo("火球术正文");
        Map<String, Object> meta = doc.getMetadata();
        assertThat(meta.get("chunk_id")).isEqualTo("spell_CRB_0001");
        assertThat(meta.get("title")).isEqualTo("火球术");
        assertThat(meta.get("book_name_cn")).isEqualTo("核心规则书");
        assertThat(meta.get("book_abbreviation")).isEqualTo("CRB");
        assertThat(meta.get("tocPath")).isEqualTo("法术 > 火球术 > 火球术");
        assertThat(meta.get("aliases")).isEqualTo("火球");
    }

    /** aliases 与 text 为 null 时安全兜底 */
    @Test
    void toDocumentNullAliasesAndTextFallbackSafely() {
        SpellChunk c = new SpellChunk(
                "c1", "d1", "spell", "spell", "t", null,
                "CRB", "核心规则书", "CRB", 1, null, Map.of(), Map.of());

        Document doc = mapper.toDocument(c);

        assertThat(doc.getText()).isEqualTo("");
        assertThat(doc.getMetadata().get("aliases")).isEqualTo("");
    }

    /** spellLevel 展开为扁平键，值统一为 String */
    @Test
    void toDocumentSpellLevelFlattenedToStringKeys() {
        Map<String, Object> meta = Map.of(
                "school", "咒法系",
                "subschool", "创造",
                "spell_level", List.of(
                        Map.of("class", "德鲁伊", "level", 1),
                        Map.of("class", "女巫", "level", 1),
                        Map.of("class", "法师", "level", 1)));
        SpellChunk c = new SpellChunk(
                "s1", "d1", "spell", "spell", "火球术", "正文",
                "CRB", "核心规则书", "Core Rulebook", 1, null, meta, Map.of());

        Document doc = mapper.toDocument(c);
        Map<String, Object> m = doc.getMetadata();

        // school / subschool 直接透传
        assertThat(m.get("school")).isEqualTo("咒法系");
        assertThat(m.get("subschool")).isEqualTo("创造");
        // spell_level 展开：环数 → spell_level_<职业>，值为 String（SimpleVectorStore 过滤类型一致）
        assertThat(m.get("spell_level_德鲁伊")).isEqualTo("1");
        assertThat(m.get("spell_level_女巫")).isEqualTo("1");
        assertThat(m.get("spell_level_法师")).isEqualTo("1");
        // 存在性键
        assertThat(m.get("has_spell_德鲁伊")).isEqualTo("true");
        assertThat(m.get("has_spell_女巫")).isEqualTo("true");
        assertThat(m.get("has_spell_法师")).isEqualTo("true");
    }

    /** 无 spell_level 时不生成扁平键 */
    @Test
    void toDocumentWithoutSpellLevelOmitsFlatKeys() {
        SpellChunk c = new SpellChunk(
                "s1", "d1", "spell", "spell", "无等级法术", "正文",
                "CRB", "核心规则书", "Core Rulebook", 1, null,
                Map.of("school", "预言系"), Map.of());

        Document doc = mapper.toDocument(c);
        Map<String, Object> m = doc.getMetadata();

        assertThat(m.get("school")).isEqualTo("预言系");
        assertThat(m).doesNotContainKey("has_spell_女巫");
        assertThat(m).doesNotContainKey("spell_level_女巫");
    }

    /** spellLevel 含括号变体职业时按原样展开 */
    @Test
    void toDocumentSpellLevelParenthesizedVariantsExpandedAsIs() {
        Map<String, Object> meta = Map.of(
                "spell_level", List.of(
                        Map.of("class", "召唤师（Unchained）", "level", 4),
                        Map.of("class", "召唤师", "level", 4)));
        SpellChunk c = new SpellChunk(
                "s1", "d1", "spell", "spell", "召唤怪物", "正文",
                "CRB", "核心规则书", "Core Rulebook", 1, null, meta, Map.of());

        Document doc = mapper.toDocument(c);
        Map<String, Object> m = doc.getMetadata();

        // 原样展开，键名含全角括号职业名；脏名问题另行登记 KN（k3 修源数据）
        assertThat(m.get("spell_level_召唤师（Unchained）")).isEqualTo("4");
        assertThat(m.get("spell_level_召唤师")).isEqualTo("4");
    }

    /** metadata 为 null 时安全兜底 */
    @Test
    void toDocumentNullMetadataFallbackSafely() {
        SpellChunk c = new SpellChunk(
                "s1", "d1", "spell", "spell", "t", "正文",
                "CRB", "核心规则书", "Core Rulebook", 1, null, null, Map.of());

        Document doc = mapper.toDocument(c);

        assertThat(doc.getText()).isEqualTo("正文");
        assertThat(doc.getMetadata()).doesNotContainKey("school");
    }
}
