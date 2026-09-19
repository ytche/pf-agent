package com.pfagent.agent.rag;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * FilterTranslator 单元测试
 *
 * 验证逻辑字段 → 扁平 metadata 键翻译（设计 §5.1 表）：
 *  spell: className+level → spell_level_<职业>；className 单独 → has_spell_<职业>；
 *         title/school/subschool 直通；book → book_abbreviation
 *  class: className → class_name 等 1:1 映射
 *  未知字段丢弃；模块非法返回空列表
 */
class FilterTranslatorTest {

    private final FilterTranslator translator = new FilterTranslator();

    /** spell 的 className 加 level 翻译为 spell_level 职业 */
    @Test
    void spellClassNameWithLevelMapsToSpellLevel() {
        List<FilterField> out = translator.translate("spell", Map.of("className", "女巫", "level", "1"));

        assertThat(out).containsExactly(new FilterField("spell_level_女巫", "1"));
    }

    /** spell 仅 className 时翻译为 has_spell 职业 */
    @Test
    void spellClassNameAloneMapsToHasSpell() {
        List<FilterField> out = translator.translate("spell", Map.of("className", "女巫"));

        assertThat(out).containsExactly(new FilterField("has_spell_女巫", "true"));
    }

    /** spell 的 level 无 className 时丢弃 */
    @Test
    void spellLevelWithoutClassNameDropped() {
        List<FilterField> out = translator.translate("spell", Map.of("level", "1"));

        assertThat(out).isEmpty();
    }

    /** spell 多条件 AND 含 school/subschool/book */
    @Test
    void spellMultiConditionAndIncludesSchoolSubschoolBook() {
        List<FilterField> out = translator.translate("spell", Map.of(
                "school", "咒法系",
                "subschool", "创造",
                "book", "CRB"));

        assertThat(out).containsExactlyInAnyOrder(
                new FilterField("school", "咒法系"),
                new FilterField("subschool", "创造"),
                new FilterField("book_abbreviation", "CRB"));
    }

    /** spell 未知字段丢弃 */
    @Test
    void spellUnknownFieldDropped() {
        List<FilterField> out = translator.translate("spell", Map.of("foo", "bar", "school", "咒法系"));

        assertThat(out).containsExactly(new FilterField("school", "咒法系"));
    }

    /** class 字段 1 对 1 映射 */
    @Test
    void classFieldsMappedOneToOne() {
        List<FilterField> out = translator.translate("class", Map.of(
                "className", "女巫",
                "archetypeName", "变形师",
                "featureSubtype", "hex",
                "componentType", "class_feature",
                "book", "APG"));

        assertThat(out).containsExactlyInAnyOrder(
                new FilterField("class_name", "女巫"),
                new FilterField("archetype_name", "变形师"),
                new FilterField("feature_subtype", "hex"),
                new FilterField("component_type", "class_feature"),
                new FilterField("book_abbreviation", "APG"));
    }

    /** 非法模块返回空列表 */
    @Test
    void invalidModuleReturnsEmptyList() {
        assertThat(translator.translate("monster", Map.of("className", "女巫"))).isEmpty();
    }

    /** spell 职业名含括号变体时原样拼键 */
    @Test
    void spellParenthesizedClassNameKeyedAsIs() {
        List<FilterField> out = translator.translate("spell", Map.of("className", "召唤师（Unchained）", "level", "4"));

        assertThat(out).containsExactly(new FilterField("spell_level_召唤师（Unchained）", "4"));
    }

    /** standard 字段 1 对 1 映射 */
    @Test
    void standardFieldsMappedOneToOne() {
        // 六个标准模块共用同一映射：book → book_abbreviation，componentType → component_type
        for (String module : List.of("feat", "race", "trait", "equipment", "skill", "rule")) {
            List<FilterField> out = translator.translate(module, Map.of(
                    "book", "CRB", "componentType", "feat"));

            assertThat(out).containsExactlyInAnyOrder(
                    new FilterField("book_abbreviation", "CRB"),
                    new FilterField("component_type", "feat"));
        }
    }

    /** standard 未知字段丢弃 */
    @Test
    void standardUnknownFieldDropped() {
        List<FilterField> out = translator.translate("feat", Map.of("foo", "bar", "book", "CRB"));

        assertThat(out).containsExactly(new FilterField("book_abbreviation", "CRB"));
    }

    /** availableFields 对 spell 与 class 返回各自字段清单（P0-B2：class 补 title 精确过滤） */
    @Test
    void availableFieldsSpellAndClassReturnRespectiveLists() {
        assertThat(translator.availableFields("spell"))
                .containsExactly("title", "school", "subschool", "className", "level", "book");
        assertThat(translator.availableFields("class"))
                .containsExactly("className", "archetypeName", "featureSubtype", "componentType", "book", "title");
    }

    /** availableFields 对六个标准模块返回通用字段（P0-B2：补 title 条目名精确过滤） */
    @Test
    void availableFieldsStandardModulesReturnCommonFields() {
        for (String module : List.of("feat", "race", "trait", "equipment", "skill", "rule")) {
            assertThat(translator.availableFields(module)).containsExactly("book", "componentType", "title");
        }
    }

    /** P0-B2：六个标准模块的 title 逻辑字段 1:1 映射到扁平 title 键 */
    @Test
    void standardTitleMapsToTitle() {
        for (String module : List.of("feat", "race", "trait", "equipment", "skill", "rule")) {
            List<FilterField> out = translator.translate(module, Map.of("title", "精通擒抱"));

            assertThat(out).containsExactly(new FilterField("title", "精通擒抱"));
        }
    }

    /** P0-B2：class 模块的 title 逻辑字段 1:1 映射到扁平 title 键 */
    @Test
    void classTitleMapsToTitle() {
        List<FilterField> out = translator.translate("class", Map.of("title", "牧师"));

        assertThat(out).containsExactly(new FilterField("title", "牧师"));
    }

    /** availableFields 对非法模块返回空列表 */
    @Test
    void availableFieldsInvalidModuleReturnsEmptyList() {
        assertThat(translator.availableFields("monster")).isEmpty();
    }

    // ---------- SP8a J2：translateQuery（or/范围比较） ----------

    /** translateQuery 的 filters 沿用旧 AND 语义（className+level 组合键） */
    @Test
    void translateQueryFiltersReuseAndSemantics() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("className", "女巫", "level", "3"));

        FilterTranslator.TranslatedQuery out = translator.translateQuery("spell", query);

        assertThat(out.eq()).containsExactly(new FilterField("spell_level_女巫", "3"));
        assertThat(out.or()).isEmpty();
        assertThat(out.gte()).isEmpty();
        assertThat(out.lte()).isEmpty();
    }

    /** orFilters 单字段多值翻译为一个 OR 组（扁平键 + 候选值列表） */
    @Test
    void translateQueryOrFiltersBuildsOrGroup() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setOrFilters(Map.of("book", List.of("CRB", "APG")));

        FilterTranslator.TranslatedQuery out = translator.translateQuery("feat", query);

        assertThat(out.or()).hasSize(1);
        assertThat(out.or().get(0).alternatives()).containsExactlyInAnyOrder(
                new FilterField("book_abbreviation", "CRB"),
                new FilterField("book_abbreviation", "APG"));
    }

    /** gte/lte 范围比较：spell level 带 className 走组合键 */
    @Test
    void translateQueryGteLteLevelWithClassNameUsesComboKey() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setFilters(Map.of("className", "女巫"));
        query.setGte(Map.of("level", "3"));
        query.setLte(Map.of("level", "5"));

        FilterTranslator.TranslatedQuery out = translator.translateQuery("spell", query);

        assertThat(out.gte()).containsExactly(new FilterField("spell_level_女巫", "3"));
        assertThat(out.lte()).containsExactly(new FilterField("spell_level_女巫", "5"));
    }

    /** gte/lte 的 level 缺 className 时丢弃（工具层已返回可读提示） */
    @Test
    void translateQueryLevelComparisonWithoutClassNameDropped() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setGte(Map.of("level", "3"));

        FilterTranslator.TranslatedQuery out = translator.translateQuery("spell", query);

        assertThat(out.gte()).isEmpty();
        assertThat(out.isEmpty()).isTrue();
    }

    /** 标准模块的范围比较 1:1 映射；未知字段丢弃 */
    @Test
    void translateQueryStandardModuleComparisonsAndUnknownDropped() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setOrFilters(Map.of("book", List.of("CRB"), "foo", List.of("x")));

        FilterTranslator.TranslatedQuery out = translator.translateQuery("rule", query);

        assertThat(out.or()).hasSize(1);
        assertThat(out.or().get(0).alternatives())
                .containsExactly(new FilterField("book_abbreviation", "CRB"));
    }

    /** spell 的 orFilters className 每值翻译为 has_spell 键（OR 组多键） */
    @Test
    void translateQueryOrClassNamesSpellBuildsHasSpellGroup() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setOrFilters(Map.of("className", List.of("女巫", "法师")));

        FilterTranslator.TranslatedQuery out = translator.translateQuery("spell", query);

        assertThat(out.or().get(0).alternatives()).containsExactlyInAnyOrder(
                new FilterField("has_spell_女巫", "true"),
                new FilterField("has_spell_法师", "true"));
    }

    /** spell 的 orFilters level 缺 className 时丢弃（TranslatedQuery 整体为空） */
    @Test
    void translateQueryOrLevelWithoutClassNameDropped() {
        MetadataSearchQuery query = new MetadataSearchQuery();
        query.setOrFilters(Map.of("level", List.of("1", "2")));

        FilterTranslator.TranslatedQuery out = translator.translateQuery("spell", query);

        assertThat(out.or()).isEmpty();
        assertThat(out.isEmpty()).isTrue();
    }
}
