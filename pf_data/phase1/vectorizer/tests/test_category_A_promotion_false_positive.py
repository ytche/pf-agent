"""
A 类：不该提升的文本不被提升为 heading

测试目标：
  - 书标题（**UM**, **极限魔法**）不被提升为法术名
  - 字母索引（**A**）不被提升
  - 字段标签（**学派**, **环位**）不被识别为法术名

溯源于 Bug 005：字段标签/lore 章节/表格残留被误提升
"""

import pytest
from vectorizer.formats.spell import SpellFormat


class TestPromotionFalsePositive:
    """不该提升的文本不被提升"""

    @pytest.mark.parametrize("text,expected_count", [
        # 字母索引不被提升（**A** 后无括号英文名）
        ("**A**\n\n**强酸箭 (Acid Arrow)**\n", 1),
        # 字段标签不被提升
        ("**学派** 咒法系\n**环位** 术士/法师 2\n", 0),
        # 纯书标题段落（无括号英文名的不提升）
        ("**极限魔法** 这是介绍文字\n**强酸箭 (Acid Arrow)**\n", 1),
        # 数字/缩写索引不被提升
        ("**UM**\n\n**强酸箭 (Acid Arrow)**\n", 1),
    ])
    def test_non_spell_not_promoted(self, spell_format: SpellFormat, text: str, expected_count: int):
        """非法术文本不应被 split_into_items 识别"""
        items = spell_format.split_into_items(text)
        assert len(items) == expected_count, (
            f"预期 {expected_count} 个条目，实际 {len(items)} 个"
        )
