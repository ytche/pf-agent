"""
E 类：推断通道 fallback 生效

测试目标：
  - 文件名无线索时从正文推断（descriptor/school 识别）
  - 正文无信号时返回空 + 记录（不崩溃）
  - 学派简称归一化（咒法 → 咒法系）

溯源于 KN002/003/005：推断双通道（breadcrumb → 正文 fallback）
"""

import pytest
from vectorizer.formats.spell import SpellFormat


class TestSubtypeFallback:
    """推断通道 fallback"""

    def test_school_normalization(self):
        """学派简称 → 全称归一化"""
        assert SpellFormat.parse_school_abbreviation("咒法") == "咒法系"
        assert SpellFormat.parse_school_abbreviation("变化") == "变化系"
        assert SpellFormat.parse_school_abbreviation("死灵") == "死灵系"
        assert SpellFormat.parse_school_abbreviation("塑能") == "塑能系"
        assert SpellFormat.parse_school_abbreviation("咒法系") == "咒法系"  # 幂等

    def test_spell_level_parsing(self):
        """环位字符串解析"""
        result = SpellFormat.parse_spell_level("魔战士 2, 术士/法师 2")
        assert len(result) == 2
        assert result[0] == {"class": "魔战士", "level": 2}
        assert result[1] == {"class": "术士/法师", "level": 2}

    def test_spell_level_single(self):
        """纯数字环位"""
        result = SpellFormat.parse_spell_level("3")
        assert result == [{"class": None, "level": 3}]

    def test_spell_level_empty(self):
        """空环位返回空列表"""
        assert SpellFormat.parse_spell_level("") == []
        assert SpellFormat.parse_spell_level(None) == []

    def test_spell_level_fullwidth_comma(self):
        """全角逗号分隔的环位（ACG 格式）"""
        result = SpellFormat.parse_spell_level("炼金术士 2，术士/法师 2，女巫 2")
        assert len(result) == 3
        assert result[0] == {"class": "炼金术士", "level": 2}
        assert result[1] == {"class": "术士/法师", "level": 2}
        assert result[2] == {"class": "女巫", "level": 2}

    def test_spell_level_multiline(self):
        """换行分隔的环位值（ACG 跨行格式）"""
        result = SpellFormat.parse_spell_level("炼金术士 2, 术士/法师 \n2")
        assert len(result) == 2
        assert result[0] == {"class": "炼金术士", "level": 2}
        assert result[1] == {"class": "术士/法师", "level": 2}

    def test_descriptor_parsing(self):
        """描述符标签提取"""
        text = "该法术造成 [酸] 伤害，以及 [火] 的额外效果"
        result = SpellFormat.parse_descriptors(text)
        assert "acid" in result
        assert "fire" in result

    def test_descriptor_empty(self):
        """无描述符时返回空列表"""
        text = "这是一个普通法术描述"
        result = SpellFormat.parse_descriptors(text)
        assert result == []


class TestCRBPipeTableFieldExtraction:
    """CRB 多行管道表格 → 字段提取综合测试"""

    CRB_MULTILINE_SAMPLE = (
        "**强酸箭 (Acid Arrow)**\n"
        "| 学派              \n"
        "       咒法系 \n"
        "       (创造) [酸]\n"
        "       环位              \n"
        "       魔战士 2, \n"
        "       术士/法师 \n"
        "       2\n"
        "       施法时间       \n"
        "       标准动作\n"
        "       法术抗力       \n"
        "       否 |\n"
        "| --- |\n"
    )

    def test_multiline_pipe_table_merge(self, spell_format: SpellFormat):
        """多行管道表格被正确合并为单行"""
        normalized = spell_format.normalize(self.CRB_MULTILINE_SAMPLE)
        promoted = spell_format.promote(normalized)
        items = spell_format.split_into_items(promoted)
        assert len(items) == 1
        assert "**学派：** 咒法系 (创造) [酸]" in items[0]["text"]
        assert "**环位：** 魔战士 2, 术士/法师 2" in items[0]["text"]
        assert "**法术抗力：** 否" in items[0]["text"]

    def test_multiline_pipe_table_school_extracted(self, spell_format: SpellFormat):
        """多行管道表格合并后能正确提取学派"""
        from vectorizer.processors.spell import SpellProcessor
        from vectorizer.sources.providers import SourceResolver, ALL_PROVIDERS

        resolver = SourceResolver(ALL_PROVIDERS)
        proc = SpellProcessor(resolver)

        normalized = spell_format.normalize(self.CRB_MULTILINE_SAMPLE)
        promoted = spell_format.promote(normalized)
        items = spell_format.split_into_items(promoted)

        assert len(items) == 1
        school = proc._infer_school(items[0])
        assert school.startswith("咒法系")
        level = proc._infer_level(items[0])
        assert len(level) >= 2
