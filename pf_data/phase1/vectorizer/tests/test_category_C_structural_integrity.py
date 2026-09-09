"""
C 类：结构变换不破坏原有层级关系

测试目标：
  - normalize 前后法术数不变
  - 字段标签归一化不丢失数据行
  - 描述文本不混入字段表
  - 结构变换不丢失文本内容

溯源于 Bug 004：不变量契约可阻止回归
"""

import pytest
from vectorizer.formats.spell import SpellFormat


class TestStructuralIntegrity:
    """结构变换不破坏原有层级关系"""

    def test_normalize_preserves_spell_count(self, spell_format: SpellFormat, sample_crb_text: str):
        """normalize 不改变法术数量"""
        items_before = spell_format.split_into_items(sample_crb_text)
        normalized = spell_format.normalize(sample_crb_text)
        items_after = spell_format.split_into_items(normalized)
        assert len(items_before) == len(items_after), (
            f"normalize 前后法术数不一致: {len(items_before)} → {len(items_after)}"
        )

    def test_non_field_lines_preserved(self, spell_format: SpellFormat, sample_um_text: str):
        """字段标签归一化不丢失非字段行"""
        normalized = spell_format.normalize(sample_um_text)
        items = spell_format.split_into_items(normalized)
        for item in items:
            text = item["text"]
            # 描述文本未被丢弃
            assert "描述" in text or "你" in text, f"描述文本可能丢失: {text[:100]}"

    def test_descriptive_text_not_mixed_with_fields(self, spell_format: SpellFormat, sample_crb_text: str):
        """描述文本不混入字段表中"""
        normalized = spell_format.normalize(sample_crb_text)
        items = spell_format.split_into_items(normalized)
        for item in items:
            text = item["text"]
            # 确保描述内容不含有未解析的管道表格符号（过多 | 表示结构残留）
            pipe_count = text.count("|")
            # 描述中可能仍有少量 |，但不应有完整表格行
            has_table_row = any(line.strip().startswith("|") and line.strip().endswith("|")
                                for line in text.splitlines())
            assert not has_table_row, f"描述中残留管道表格行: {text[:200]}"

    def test_normalize_does_not_remove_lines(self, spell_format: SpellFormat, sample_acg_text: str):
        """normalize 不无故删除内容行"""
        original_lines = [l for l in sample_acg_text.splitlines() if l.strip()]
        normalized = spell_format.normalize(sample_acg_text)
        normalized_lines = [l for l in normalized.splitlines() if l.strip()]
        # 归一化可能合并行，但不应减少到 < 50%
        assert len(normalized_lines) >= len(original_lines) * 0.5, (
            f"normalize 后行数从 {len(original_lines)} 减少到 {len(normalized_lines)}"
        )
