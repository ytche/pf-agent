"""
B 类：该提升的文本被正确提升为 heading

测试目标：
  - 管道表格格式的法术名被正确识别
  - Bold 标签格式的法术名被正确识别
  - 冒号标签格式的法术名被正确识别
  - AONPRD 格式的法术名被正确识别
  - 无 ** 包裹的法术名（UC/MTT 格式）被正确识别
  - 全角括号 → 半角括号归一化后仍正确识别

溯源于 Bug 001：图片前缀标题漏判
"""

import pytest
from vectorizer.formats.spell import SpellFormat


class TestPromotionFalseNegative:
    """该提升的文本被正确识别"""

    def test_crb_pipe_table_parsed(self, spell_format: SpellFormat, sample_crb_text: str):
        """变体 A — 管道表格法术名被正确提取"""
        normalized = spell_format.normalize(sample_crb_text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "强酸箭" in names, f"未找到强酸箭，找到: {names}"
        assert "酸雾术" in names, f"未找到酸雾术，找到: {names}"

    def test_um_bold_label_parsed(self, spell_format: SpellFormat, sample_um_text: str):
        """变体 B — Bold 标签法术名被正确提取"""
        normalized = spell_format.normalize(sample_um_text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "酸液喷发" in names, f"未找到酸液喷发，找到: {names}"

    def test_acg_colon_label_parsed(self, spell_format: SpellFormat, sample_acg_text: str):
        """变体 C — 冒号标签法术名被正确提取（含全角括号归一化）"""
        normalized = spell_format.normalize(sample_acg_text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "凝胶之血" in names, f"未找到凝胶之血，找到: {names}"

    def test_aonprd_format_parsed(self, spell_format: SpellFormat, sample_aonprd_text: str):
        """变体 D — AONPRD 格式法术名被正确提取"""
        normalized = spell_format.normalize(sample_aonprd_text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "流血打击" in names, f"未找到流血打击，找到: {names}"

    def test_mtt_format_parsed(self, spell_format: SpellFormat, sample_mtt_text: str):
        """变体 F — MT T 格式法术名从 ## 提取"""
        normalized = spell_format.normalize(sample_mtt_text)
        items = spell_format.split_into_items(normalized)
        names = [it["name"] for it in items]
        assert "战术突破" in names, f"未找到战术突破，找到: {names}"

    @pytest.mark.parametrize("variant_name,fixture_attr", [
        ("crb", "sample_crb_text"),
        ("um", "sample_um_text"),
        ("acg", "sample_acg_text"),
        ("aonprd", "sample_aonprd_text"),
    ])
    def test_all_variants_yield_spell_name(self, request, spell_format: SpellFormat, variant_name: str, fixture_attr: str):
        """所有格式变体都能提取出法术名（非空）"""
        text = request.getfixturevalue(fixture_attr)
        normalized = spell_format.normalize(text)
        items = spell_format.split_into_items(normalized)
        assert len(items) >= 1, f"{variant_name}: 未提取到任何法术条目"
        for it in items:
            assert it["name"], f"{variant_name}: 法术名为空"
            assert it["name_en"], f"{variant_name}: 英文名为空"
