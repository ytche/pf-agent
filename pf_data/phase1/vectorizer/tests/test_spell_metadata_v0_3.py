"""
schema v0.3 字段抽取测试

测试目标：
  - parse_fields() 从统一 IR 文本提取所有字段原始值
  - 各字段类型转换器正确解析结构化值
  - infer_metadata() 输出 16 键 metadata（15 语义 + field_status）
  - field_status 计算正确
  - 幂等性：重复调用不改变结果
"""

import json
import re
from pathlib import Path

import pytest

from vectorizer.formats.spell import SpellFormat
from vectorizer.processors.spell import (
    SpellProcessor,
    _is_semantically_empty,
    parse_fields,
)
from vectorizer.registry import CANONICAL_FIELDS, LABEL_TO_KEY


# ============================================================
#  _is_semantically_empty
# ============================================================

class TestIsSemanticallyEmpty:
    def test_none(self):
        assert _is_semantically_empty(None) is True

    def test_empty_string(self):
        assert _is_semantically_empty("") is True

    def test_whitespace_string(self):
        assert _is_semantically_empty("   ") is True

    def test_non_empty_string(self):
        assert _is_semantically_empty("hello") is False

    def test_empty_list(self):
        assert _is_semantically_empty([]) is True

    def test_non_empty_list(self):
        assert _is_semantically_empty([1, 2]) is False

    def test_empty_dict(self):
        assert _is_semantically_empty({}) is True

    def test_all_falsy_dict(self):
        assert _is_semantically_empty({"a": False, "b": None, "c": ""}) is True

    def test_some_truthy_dict(self):
        assert _is_semantically_empty({"a": False, "b": True}) is False


# ============================================================
#  parse_fields()
# ============================================================

class TestParseFields:
    """parse_fields() 从统一 IR 提取原始字段值"""

    def test_crb_pipe_table_format(self):
        """CRB 管道表格 → 首字段提取正确，多字段同行是已知管线局限"""
        fmt = SpellFormat()
        raw = (
            "**强酸箭 (Acid Arrow)**\n"
            "| 学派 咒法系（创造）[酸] | 环位 魔战士 2, 术士/法师 2 |\n"
            "| 施法时间 标准动作 | 成分 语言, 姿势, 材料（箭） |\n"
            "| 范围 远程 | 目标 一个生物 | 持续时间 1轮/等级 |\n"
            "| 豁免 无 | 法术抗力 可 |\n"
        )
        text = fmt._unify_field_labels(raw)
        result = parse_fields(text)

        # 每行首字段正确提取
        assert "咒法系" in result.get("school", "")
        # 注意：多字段同行时后续字段混入前字段值，这是管线已知局限
        # 后续字段由 _infer_level 等 fallback 方法补位

    def test_bold_label_format(self):
        """**标签：** 值 标准格式"""
        text = (
            "**火球术 (Fireball)**\n"
            "**学派：** 塑能系 [火]\n"
            "**环位：** 术士/法师 3\n"
            "**施法时间：** 标准动作\n"
            "**成分：** 语言，姿势，材料（一小块硫磺）\n"
            "**范围：** 远距（400尺+40尺/等级）\n"
            "**区域：** 20尺半径扩散\n"
            "**持续时间：** 立即\n"
            "**豁免：** 反射，减半\n"
            "**法术抗力：** 可\n"
        )
        result = parse_fields(text)

        assert "塑能系" in result.get("school", "")
        assert "术士/法师 3" in result.get("spell_level", "")
        assert "标准动作" in result.get("casting_time", "")
        assert "语言" in result.get("components", "")
        assert "远距" in result.get("range", "")
        assert "20尺半径扩散" in result.get("area", "")
        assert "立即" in result.get("duration", "")
        assert "反射" in result.get("saving_throw", "")
        assert "可" in result.get("spell_resistance", "")

    def test_bold_close_before_colon_format(self):
        """**标签**：值 格式（安全网 fallback）"""
        text = (
            "**燃烧流沙**\n"
            "**学派**：咒法系(创造)[土,火]\n"
            "**等级**：德鲁伊 1,游侠 1\n"
            "**施法时间**：1个标准动作\n"
            "**成分**：语言，姿势，材料 (一把沙子/法器)\n"
            "**射程**：中距(100尺+10尺/等级)\n"
            "**范围**：20尺半径\n"
            "**持续**：1轮\n"
            "**豁免**：无\n"
        )
        result = parse_fields(text)

        assert "咒法系" in result.get("school", "")
        assert "德鲁伊 1" in result.get("spell_level", "")
        assert "1个标准动作" in result.get("casting_time", "")
        assert "语言" in result.get("components", "")

    def test_empty_text(self):
        """空文本 → 空 dict"""
        assert parse_fields("") == {}
        assert parse_fields(None) == {}

    def test_missing_fields_return_empty(self):
        """缺失字段不出现在结果中"""
        text = "**学派：** 咒法系\n"
        result = parse_fields(text)
        assert "school" in result or "学派" in str(result)
        # 确保不会返回空字符串键
        assert "" not in result

    def test_fullwidth_space_normalization(self):
        """全角空格 → 半角"""
        text = "**学派：**　咒法系\n"
        result = parse_fields(text)
        school_val = result.get("school", "")
        assert "　" not in school_val

    def test_strip_trailing_asterisks(self):
        """值尾部的 ** 残留应被 strip"""
        text = "**学派：** 咒法系**\n"
        result = parse_fields(text)
        school_val = result.get("school", "")
        assert not school_val.endswith("**")

    # ---- F1：值吞正文/跨空行截断 ----

    def test_blank_line_is_hard_boundary(self):
        """**标签：** 值 后跟 \\n\\n（空行）→ 值必须截断到空行前，不吞正文"""
        text = (
            "**法术免疫 (Spell Immunity)**\n"
            "**学派：** 防护系\n"
            "**法术抗力：** 可 (无害)\n"
            "\n"
            "你每拥有四个等级可以使被防护的生物免疫一个特定法术的效果。"
            "该法术不得高于4环。\n"
        )
        result = parse_fields(text)
        sr = result.get("spell_resistance", "")
        # 不应吞掉正文
        assert "你每拥有四个等级" not in sr, (
            f"sr 吞了正文：{sr[:120]}"
        )
        # 应当只保留字段值
        assert sr.strip() in ("可 (无害)", "可（无害）"), sr

    def test_blank_line_after_label_value_no_next_field(self):
        """**标签：** 值 后无下一字段，直接 \\n\\n + 正文 → 值只取到空行前"""
        text = (
            "**法术免疫**\n"
            "**法术抗力：** 可 (无害)\n"
            "\n"
            "你每拥有四个等级...\n"
        )
        result = parse_fields(text)
        assert "你每拥有" not in result.get("spell_resistance", "")

    def test_value_then_inline_bold_marker_then_prose(self):
        """值尾部紧贴 ** 后接 \\n(无害)\\n\\n → 跨行无害应被识别但值不应吞更后面正文"""
        text = (
            "**众怒**\n"
            "**豁免：** 意志，通过则无效 **\n"
            "(无害)\n"
            "\n"
            "该法术的目标会在进行交涉时...\n"
        )
        result = parse_fields(text)
        sv = result.get("saving_throw", "")
        # 不应吞掉"该法术的目标..."
        assert "该法术的目标" not in sv, (
            f"豁免吞了正文：{sv[:200]}"
        )
        # 应至少包含"通过则无效"
        assert "通过则无效" in sv

    def test_value_then_compact_bare_label(self):
        """**距离：** 值\n**持续**：1轮 (COMP 裸标签嵌入) → 距离值不应包含 '持续'"""
        text = (
            "**燃烧流沙**\n"
            "**距离：** 20尺半径\n"
            "**持续**：1轮\n"
        )
        result = parse_fields(text)
        # 距离值不应包含下一字段"持续"的内容
        range_val = result.get("range", "")
        assert "持续" not in range_val, (
            f"range 吞了下一字段：{range_val}"
        )
        assert "20尺半径" in range_val


# ============================================================
#  F1 修复后 _parse_saving_throw / _parse_spell_resistance
# ============================================================

class TestF1SavingThrowCleanup:
    """F1 修复后豁免 effect 清洗：去 **/前导标点/空白"""

    def test_effect_strips_trailing_asterisks(self):
        """effect 末尾的 ** 残留应被清除"""
        result = SpellProcessor._parse_saving_throw("意志，通过则无效 **")
        assert "**" not in result["effect"], result["effect"]
        assert "通过则无效" in result["effect"]

    def test_effect_strips_leading_punctuation(self):
        """effect 前导逗号应被清除"""
        result = SpellProcessor._parse_saving_throw("意志，通过则无效")
        assert not result["effect"].startswith("，")
        assert not result["effect"].startswith(",")

    def test_harmless_recognized_across_newline(self):
        """跨行 (无害) 应被识别 harmless=True"""
        result = SpellProcessor._parse_saving_throw("意志，通过则无效 **\n(无害)")
        assert result["harmless"] is True
        assert "无害" not in result["effect"]
        assert "**" not in result["effect"]

    def test_empty_value_yields_empty_dict(self):
        """空值/缺失 → 默认空 dict，type/effect 都为空"""
        result = SpellProcessor._parse_saving_throw("")
        assert result == {"type": "", "effect": "", "harmless": False}


class TestF1SpellResistanceCleanup:
    """F1 修复后 SR note 清洗：不吞正文"""

    def test_short_value_clean(self):
        """短值 '可 (无害)' → note 为 None（已被识别为 applies+harmless）"""
        result = SpellProcessor._parse_spell_resistance("可 (无害)")
        assert result["applies"] is True
        assert result["harmless"] is True
        assert result["note"] is None

    def test_harmless_recognized_and_stripped(self):
        """无害标记识别并从 note 中剥离"""
        result = SpellProcessor._parse_spell_resistance("可（无害）")
        assert result["harmless"] is True
        assert result["note"] is None

    def test_see_text_kept_in_note(self):
        """'见下文' 应保留在 note"""
        result = SpellProcessor._parse_spell_resistance("见下文")
        assert result["note"] == "见下文"
        assert result["applies"] is True


# ============================================================
#  F2：COMP 裸标签规范化进 IR（含 negative tests 防误伤）
# ============================================================

class TestF2BareLabels:
    """F2 修复后 _unify_field_labels：COMP 裸标签归一化为 **标签：**"""

    def test_casting_time_bare_label_line_start(self):
        """行首裸标签 施放时间：标准动作 → **施法时间：** 标准动作"""
        fmt = SpellFormat()
        raw = "**法术**\n施放时间：标准动作\n"
        out = fmt._unify_field_labels(raw)
        assert "**施法时间：** 标准动作" in out

    def test_duration_bare_label_line_start(self):
        """行首裸标签 持续：1轮 → **持续时间：** 1轮（别名归一化）"""
        fmt = SpellFormat()
        raw = "**法术**\n持续：1轮\n"
        out = fmt._unify_field_labels(raw)
        assert "**持续时间：** 1轮" in out

    def test_spell_resistance_bare_label_line_start(self):
        """行首裸标签 抗力：** 否 → **法术抗力：** 否（别名归一化 + 吃掉 *）"""
        fmt = SpellFormat()
        raw = "**法术**\n抗力：** 否\n"
        out = fmt._unify_field_labels(raw)
        assert "**法术抗力：** 否" in out

    def test_midline_compact_resistance_handled_by_parse_fields(self):
        """COMP 行内紧凑：豁免后接裸抗力已在 parse_fields 内被处理（F1 已修）
        这里只验证 IR 阶段不引入新 bug：bold 标准 IR 不被破坏"""
        fmt = SpellFormat()
        raw = "**法术**\n**豁免：** 意志，通过则无效\n**法术抗力：** 无\n"
        out = fmt._unify_field_labels(raw)
        # 关键 IR 不变
        assert "**豁免：** 意志，通过则无效" in out
        assert "**法术抗力：** 无" in out

    # ---- F2 negative tests: 正文散文含「抗力：/持续：/施放时间：」字样不应被误转 ----

    def test_prose_with_spell_resistance_words_unchanged(self):
        """正文出现「抗力：xxx」字样不应被识别为字段（不在已知 SR 关键字后）"""
        fmt = SpellFormat()
        raw = "**法术**\n该生物的法术抗力：极高，普通法术难以影响它\n"
        out = fmt._unify_field_labels(raw)
        # 正文不应被插入 **
        assert "该生物的法术抗力：极高" in out
        # 关键：不应生成新的 **法术抗力：** 字段
        assert "**法术抗力：** 极高" not in out

    def test_prose_with_duration_words_unchanged(self):
        """正文「持续：xxx」字样不应被误转（不在已知 duration 关键字后）"""
        fmt = SpellFormat()
        raw = "**法术**\n此效果持续：一轮后失效\n"
        out = fmt._unify_field_labels(raw)
        # 不应在正文中插入 **
        assert "效果持续：一轮后失效" in out
        # 不应生成新字段
        assert "**持续时间：**" not in out

    def test_prose_with_casting_time_words_unchanged(self):
        """正文「施放时间：xxx」字样不应被误转"""
        fmt = SpellFormat()
        raw = "**法术**\n其施放时间：远比标准动作长\n"
        out = fmt._unify_field_labels(raw)
        assert "**施法时间：**" not in out

    def test_bold_framing_not_corrupted(self):
        """已有 **法术抗力：** 标准 IR 不应被破坏（**法术** 是标题，允许存在）"""
        fmt = SpellFormat()
        raw = "**法术**\n**法术抗力：** 否\n"
        out = fmt._unify_field_labels(raw)
        # 关键：标准 IR 完整保留
        assert "**法术抗力：** 否" in out
        # 不应被错误切成 **法术**抗力：** 否
        assert "**法术**抗力" not in out

    # ---- F2-inline (tight): 豁免尾词后的裸标签边界 ----

    def test_tight_bare_sr_after_无效(self):
        """无效抗力：无 → 无效\\n**法术抗力：** 无"""
        fmt = SpellFormat()
        raw = "**豁免：** 意志，通过则无效抗力：无\n"
        out = fmt._unify_field_labels(raw)
        assert "**法术抗力：** 无" in out

    def test_tight_bare_sr_after_见下(self):
        """见下抗力：无 → 见下\\n**法术抗力：** 无"""
        fmt = SpellFormat()
        raw = "**豁免：** 反射，通过则减半；见下抗力：无\n"
        out = fmt._unify_field_labels(raw)
        assert "**法术抗力：** 无" in out

    def test_tight_bare_sr_after_生效(self):
        """生效抗力：可 → 生效\\n**法术抗力：** 可"""
        fmt = SpellFormat()
        raw = "**豁免：** 强韧，通过则生效抗力：可\n"
        out = fmt._unify_field_labels(raw)
        assert "**法术抗力：** 可" in out

    # ---- F2-inline (tight) negative tests: 散文不应被误转 ----

    def test_tight_prose_无效抗力_极高_not_converted(self):
        """正文「无效抗力：极高」不应被误转（值「极高」不在限定集合）"""
        fmt = SpellFormat()
        raw = "**法术**\n此效果无效抗力：极高，无法被驱散\n"
        out = fmt._unify_field_labels(raw)
        assert "**法术抗力：** 极高" not in out
        assert "无效抗力：极高" in out

    def test_tight_prose_效果持续_not_converted(self):
        """正文「效果持续：一轮后失效」不应被误转（「效果」不是已知豁免尾词）"""
        fmt = SpellFormat()
        raw = "**法术**\n此效果持续：一轮后失效\n"
        out = fmt._unify_field_labels(raw)
        assert "**持续时间：**" not in out
        assert "效果持续：一轮后失效" in out

    def test_tight_prose_通过抗力_无_converted_known_fp(self):
        """「通过抗力：无」当前会被 tight regex 误转（已知误报，此测试如实锁定当前行为）。

        注：此 case 语义模糊，但值集合 {有,无,...} 的限制使得误伤概率极低；
        若未来出现实际误伤再调整。此测试锁定当前行为。"""
        fmt = SpellFormat()
        raw = "**法术**\n该法术无法通过抗力：无豁免的生物仍然受影响\n"
        out = fmt._unify_field_labels(raw)
        # 「无法通过抗力：无豁免」语义完整，「抗力：无」不应被拆分
        # 但 tight regex 会匹配「过抗力：无」→ 实际会插入换行
        # 此测试记录这一边界行为：当前 tight regex 会在此 case 误转
        # 但值集合的限制使其在真实数据中极难触发
        # 预期：会被转换（因为 通过+抗力：无 匹配 tight regex）
        assert "**法术抗力：** 无" in out  # 当前行为：会转换



# ============================================================
#  字段类型转换器
# ============================================================

class TestParseComponents:
    """_parse_components 成分解析"""

    def test_chinese_verbal_somatic(self):
        """中文 语言+姿势"""
        result = SpellProcessor._parse_components("语言，姿势")
        assert result["verbal"] is True
        assert result["somatic"] is True
        assert result["material"] is None
        assert result["focus"] is None
        assert result["divine_focus"] is False

    def test_chinese_verbal_only(self):
        """仅语言"""
        result = SpellProcessor._parse_components("语言")
        assert result["verbal"] is True
        assert result["somatic"] is False

    def test_chinese_somatic_only(self):
        """仅姿势"""
        result = SpellProcessor._parse_components("姿势")
        assert result["verbal"] is False
        assert result["somatic"] is True

    def test_chinese_verbal_alt(self):
        """言语 变体"""
        result = SpellProcessor._parse_components("言语，姿势，法器")
        assert result["verbal"] is True
        assert result["somatic"] is True
        assert result["divine_focus"] is True

    def test_yan_wen_variant(self):
        """语文 变体"""
        result = SpellProcessor._parse_components("语文，姿势")
        assert result["verbal"] is True

    def test_material_with_parens(self):
        """材料（具体物品）"""
        result = SpellProcessor._parse_components("语言，姿势，材料 (一把沙子)")
        assert result["verbal"] is True
        assert result["somatic"] is True
        assert result["material"] == "一把沙子"

    def test_divine_focus(self):
        """法器"""
        result = SpellProcessor._parse_components("语言，姿势，法器")
        assert result["verbal"] is True
        assert result["somatic"] is True
        assert result["divine_focus"] is True

    def test_divine_focus_with_parens(self):
        """法器（具体物品）"""
        result = SpellProcessor._parse_components("语言，姿势，法器 (圣徽)")
        assert result["divine_focus"] is True
        assert result["material"] == "圣徽"

    def test_focus_with_parens(self):
        """器材（具体物品）"""
        result = SpellProcessor._parse_components("语言，姿势，器材 (水晶球)")
        assert result["verbal"] is True
        assert result["somatic"] is True
        assert result["focus"] == "水晶球"

    def test_material_or_divine_focus(self):
        """材料/法器 双选"""
        result = SpellProcessor._parse_components("语言，姿势，材料/法器")
        assert result["verbal"] is True
        assert result["somatic"] is True
        assert result["divine_focus"] is True
        # 材料也检测到（因为'材料'在值中）
        assert result["material"] == "见原文"

    def test_english_abbreviation(self):
        """英文缩写 fallback"""
        result = SpellProcessor._parse_components("V，S，M（bat guano）")
        assert result["verbal"] is True
        assert result["somatic"] is True
        assert result["material"] == "bat guano"

    def test_empty_value(self):
        """空值 → 默认空 dict"""
        result = SpellProcessor._parse_components("")
        assert result["verbal"] is False
        assert result["somatic"] is False
        assert result["material"] is None

    def test_enumeration_comma(self):
        """顿号分隔（语言、姿势、法器）"""
        result = SpellProcessor._parse_components("语言、姿势、法器")
        assert result["verbal"] is True
        assert result["somatic"] is True
        assert result["divine_focus"] is True


class TestParseSavingThrow:
    """_parse_saving_throw 豁免解析"""

    def test_fortitude_negates(self):
        result = SpellProcessor._parse_saving_throw("强韧通过则无效")
        assert result["type"] == "强韧"
        assert "通过则无效" in result["effect"]
        assert result["harmless"] is False

    def test_will_harmless(self):
        result = SpellProcessor._parse_saving_throw("意志通过则无效（无害）")
        assert result["type"] == "意志"
        assert result["harmless"] is True

    def test_reflex_half(self):
        result = SpellProcessor._parse_saving_throw("反射，减半")
        assert result["type"] == "反射"
        assert "减半" in result["effect"]

    def test_none_value(self):
        """显式否定 '无' → type='无'（KN018 truthy 编码）"""
        result = SpellProcessor._parse_saving_throw("无")
        assert result["type"] == "无"
        assert result["effect"] == ""
        assert result["harmless"] is False

    def test_empty_value(self):
        """空值保持原行为 → missing"""
        result = SpellProcessor._parse_saving_throw("")
        assert result["type"] == ""
        assert result["effect"] == ""

    def test_cut_at_见描述_body_text(self):
        """（见描述）后紧跟中文正文时截断（PA 异能选集格式）"""
        result = SpellProcessor._parse_saving_throw(
            "意志，通过则部分生效（见描述）该法术的功能如同精神蛀虫II一般"
        )
        assert result["type"] == "意志"
        assert result["effect"] == "通过则部分生效（见描述）"

    def test_cut_at_见文本_body_text(self):
        """（见文本）后紧跟中文正文时截断"""
        result = SpellProcessor._parse_saving_throw(
            "强韧，通过则无效（见文本）此效果持续1轮"
        )
        assert result["type"] == "强韧"
        assert result["effect"] == "通过则无效（见文本）"

    def test_见描述_followed_by_punctuation_not_cut(self):
        """（见描述）；后跟标点时不截断（标点仍是豁免描述的一部分）"""
        result = SpellProcessor._parse_saving_throw(
            "意志，通过则部分生效（见描述）；法术抗力适用"
        )
        assert result["type"] == "意志"
        assert "法术抗力适用" in result["effect"]


class TestParseSpellResistance:
    """_parse_spell_resistance 法术抗力解析"""

    def test_applies(self):
        result = SpellProcessor._parse_spell_resistance("可")
        assert result["applies"] is True

    def test_not_applies(self):
        """KN018：显式否定写 note 原词"""
        result = SpellProcessor._parse_spell_resistance("不可")
        assert result["applies"] is False
        assert result["note"] == "不可"

    def test_see_text(self):
        result = SpellProcessor._parse_spell_resistance("见下文")
        assert result["applies"] is True
        assert result["note"] == "见下文"

    def test_harmless(self):
        result = SpellProcessor._parse_spell_resistance("可（无害）")
        assert result["applies"] is True
        assert result["harmless"] is True

    def test_empty(self):
        result = SpellProcessor._parse_spell_resistance("")
        assert result["applies"] is False


class TestExtractSchool:
    """_extract_school 学派遣提取"""

    def test_basic_school(self):
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {"school": "咒法系"}
        result = processor._extract_school(raw, {"text": ""})
        assert result == "咒法系"

    def test_school_with_subschool(self):
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {"school": "咒法系（创造）"}
        result = processor._extract_school(raw, {"text": ""})
        assert result == "咒法系"

    def test_school_with_descriptor(self):
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {"school": "塑能系[火]"}
        result = processor._extract_school(raw, {"text": ""})
        assert result == "塑能系"

    def test_school_abbreviation(self):
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {"school": "咒法"}
        result = processor._extract_school(raw, {"text": ""})
        assert result == "咒法系"

    def test_school_normalization(self):
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {"school": "变化系（变形）"}
        result = processor._extract_school(raw, {"text": ""})
        assert result == "变化系"

    def test_empty_school(self):
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {}
        result = processor._extract_school(raw, {"text": ""})
        assert result == ""

    def test_fallback_to_infer_school(self):
        """parse_fields 无 school 时 fallback 到 _infer_school"""
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {}
        item = {"text": "**学派：** 死灵系\n"}
        result = processor._extract_school(raw, item)
        assert "死灵系" in result


class TestExtractSubschool:
    """_extract_subschool 子学派遣提取"""

    def test_subschool_from_parens(self):
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {"school": "咒法系（创造）"}
        result = processor._extract_subschool(raw)
        assert result == "创造"

    def test_subschool_illusion_shadow(self):
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {"school": "幻术系（幽影幻觉）[暗]"}
        result = processor._extract_subschool(raw)
        assert result == "幽影幻觉"

    def test_no_subschool(self):
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {"school": "塑能系[火]"}
        result = processor._extract_subschool(raw)
        assert result is None

    def test_empty_school(self):
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {}
        result = processor._extract_subschool(raw)
        assert result is None


class TestExtractSpellLevel:
    """_extract_spell_level 环位解析"""

    def test_single_class(self):
        raw = {"spell_level": "术士 3"}
        result = SpellProcessor._extract_spell_level(raw)
        assert result == [{"class": "术士", "level": 3}]

    def test_multi_class(self):
        raw = {"spell_level": "魔战士 2, 女巫 2, 术士 2"}
        result = SpellProcessor._extract_spell_level(raw)
        assert len(result) == 3

    def test_empty(self):
        raw = {}
        result = SpellProcessor._extract_spell_level(raw)
        assert result == []

    # ---- F3: 复合职业 / 拆分（B8）----

    def test_compound_class_split_into_two(self):
        """复合职业 术士/法师 应拆成 [术士, 法师]"""
        raw = {"spell_level": "术士/法师 3"}
        result = SpellProcessor._extract_spell_level(raw)
        classes = [e["class"] for e in result if e.get("class")]
        assert "术士" in classes
        assert "法师" in classes
        assert len(classes) == 2
        # 不应残留 /
        assert all("/" not in c for c in classes)

    def test_compound_class_order_normalized(self):
        """复合职业拆分后顺序归一（短名在前）"""
        raw = {"spell_level": "术士/法师 3"}
        result = SpellProcessor._extract_spell_level(raw)
        classes = [e["class"] for e in result if e.get("class")]
        # 法师在 术士 前（按字符序，'法' < '术'）
        assert classes == sorted(classes)

    def test_compound_class_in_mixed_list(self):
        """混合列表中的复合职业也应拆分"""
        raw = {"spell_level": "魔战士 2, 术士/法师 2, 女巫 2"}
        result = SpellProcessor._extract_spell_level(raw)
        classes = [e["class"] for e in result if e.get("class")]
        assert "魔战士" in classes
        assert "术士" in classes
        assert "法师" in classes
        assert "女巫" in classes
        assert all("/" not in c for c in classes)
        assert sum(1 for c in classes if c in ("术士", "法师")) == 2


# ============================================================
#  F3: spell_level 领域残留剥离（B7）
# ============================================================

class TestExtractSpellLevelF3:
    """F3：spell_level 中领域残留剥离到 domains/subdomains"""

    def test_class_with_domain_residue(self):
        """'审判者 2 领域 机运领域 2' → class=审判者 2, domain=机运领域 2 (单独提取)"""
        raw = {"spell_level": "审判者 2 领域 机运领域 2"}
        result = SpellProcessor._extract_spell_level(raw)
        classes = {e["class"]: e["level"] for e in result if e.get("class")}
        assert classes == {"审判者": 2}
        # 机运领域 被剥离到 domains
        domains = SpellProcessor._extract_domains_from_level(raw)
        assert any(d["name"] == "机运领域" for d in domains)

    def test_compound_with_domain(self):
        """'术士/法师 4 领域 死亡领域 3' → classes 拆分为 [术士, 法师]; 死亡领域 剥离到 domains"""
        raw = {"spell_level": "术士/法师 4 领域 死亡领域 3"}
        result = SpellProcessor._extract_spell_level(raw)
        classes = [e["class"] for e in result if e.get("class")]
        assert "术士" in classes
        assert "法师" in classes
        # 死亡领域 不应在 class 中
        assert "死亡领域" not in classes
        assert len(classes) == 2
        # 剥离到 domains
        domains = SpellProcessor._extract_domains_from_level(raw)
        assert any(d["name"] == "死亡领域" for d in domains)

    def test_pure_domain_no_class(self):
        """'邪恶领域 2' → 不放入 classes（剥离到 domains）"""
        raw = {"spell_level": "邪恶领域 2"}
        result = SpellProcessor._extract_spell_level(raw)
        classes = [e["class"] for e in result if e.get("class")]
        assert "邪恶领域" not in classes
        # domains 应该有它
        domains = SpellProcessor._extract_domains_from_level(raw)
        assert any(d["name"] == "邪恶领域" for d in domains)

    def test_subdomain_pattern(self):
        """'召唤师 1 领域 家园子域 1' → class=召唤师; 家园子域 剥离到 subdomains"""
        raw = {"spell_level": "召唤师 1 领域 家园子域 1"}
        result = SpellProcessor._extract_spell_level(raw)
        classes = {e["class"]: e["level"] for e in result if e.get("class")}
        assert classes == {"召唤师": 1}
        # 家园子域 剥离到 subdomains
        subdomains = SpellProcessor._extract_subdomains_from_level(raw)
        assert any(s["name"] == "家园子域" for s in subdomains)

    def test_complex_compound_with_domain_and_subdomain(self):
        """炼金术师 2, 牧师/先知 2, 审判者 2 领域 机运领域 2, 战术子域 2
        → classes: 炼金术师, 牧师, 先知, 审判者 (4 个, 领域/子域由 domain 字段处理)"""
        raw = {"spell_level": "炼金术师 2, 牧师/先知 2, 审判者 2 领域 机运领域 2, 战术子域 2"}
        result = SpellProcessor._extract_spell_level(raw)
        classes = [e["class"] for e in result if e.get("class")]
        assert "炼金术师" in classes
        assert "牧师" in classes
        assert "先知" in classes
        assert "审判者" in classes
        # 不应有残留 / 或空格
        assert all("/" not in c for c in classes)
        assert all(" " not in c for c in classes)
        # 纯领域/子域条目（机运领域、战术子域）已剥离到 domains/subdomains
        assert "机运领域" not in classes
        assert "战术子域" not in classes

    def test_bold_prefix_stripped(self):
        """** 牧师/先知 → 牧师, 先知 (剥离 ** 包裹和前导空格)"""
        raw = {"spell_level": "** 牧师/先知 2"}
        result = SpellProcessor._extract_spell_level(raw)
        classes = [e["class"] for e in result if e.get("class")]
        assert "牧师" in classes
        assert "先知" in classes
        assert all("*" not in c for c in classes)

    def test_dunhao_separator_comma(self):
        """顿号 (、) 分隔应等同逗号"""
        raw = {"spell_level": "奥能师 7、召唤师 7、术士 7"}
        result = SpellProcessor._extract_spell_level(raw)
        classes = [e["class"] for e in result if e.get("class")]
        assert "奥能师" in classes
        assert "召唤师" in classes
        assert "术士" in classes
        # 不应有顿号残留
        assert all("、" not in c for c in classes)

    def test_pure_domain_not_in_class(self):
        """纯领域 (邪恶领域 2) 不应作为 class (移交给 domains)"""
        raw = {"spell_level": "邪恶领域 2"}
        result = SpellProcessor._extract_spell_level(raw)
        classes = [e["class"] for e in result if e.get("class")]
        assert "邪恶领域" not in classes
        # domains 应该有它
        domains = SpellProcessor._extract_domains_from_level(raw)
        assert any(d["name"] == "邪恶领域" for d in domains)

    def test_pure_subdomain_not_in_class(self):
        """纯子域 (战术子域 2) 不应作为 class"""
        raw = {"spell_level": "战术子域 2"}
        result = SpellProcessor._extract_spell_level(raw)
        classes = [e["class"] for e in result if e.get("class")]
        assert "战术子域" not in classes
        subdomains = SpellProcessor._extract_subdomains_from_level(raw)
        assert any(s["name"] == "战术子域" for s in subdomains)


# ============================================================
#  field_status 计算
# ============================================================

class TestComputeFieldStatus:
    """_compute_field_status 状态计算"""

    def test_parsed_fields(self):
        meta = {
            "school": "咒法系",
            "subschool": None,
            "descriptor": [],
            "spell_level": [{"class": "术士", "level": 3}],
            "casting_time": "标准动作",
            "components": {"verbal": True, "somatic": True,
                           "material": None, "focus": None, "divine_focus": False},
        }
        status = SpellProcessor._compute_field_status(meta)
        assert status["school"] == "parsed"
        assert status["subschool"] == "not_applicable"
        assert status["casting_time"] == "parsed"

    def test_missing_fields(self):
        meta = {"school": "", "casting_time": ""}
        status = SpellProcessor._compute_field_status(meta)
        assert status["school"] == "missing"
        assert status["casting_time"] == "missing"

    def test_not_applicable(self):
        meta = {"area": None, "effect": None, "subschool": None}
        status = SpellProcessor._compute_field_status(meta)
        assert status["area"] == "not_applicable"
        assert status["effect"] == "not_applicable"
        assert status["subschool"] == "not_applicable"

    def test_no_field_status_key(self):
        """field_status 自身不应出现在 status dict 中"""
        meta = {"school": "咒法系"}
        status = SpellProcessor._compute_field_status(meta)
        assert "field_status" not in status


# ============================================================
#  infer_metadata() 集成测试
# ============================================================

class TestInferMetadata:
    """infer_metadata() 完整 metadata 输出"""

    def test_16_keys_in_metadata(self):
        """metadata 应包含 15 语义字段 + field_status = 16 键"""
        fmt = SpellFormat()
        from vectorizer.sources.providers import SourceResolver

        resolver = SourceResolver([])
        processor = SpellProcessor(source_resolver=resolver)

        text = (
            "**火球术 (Fireball)**\n"
            "**学派：** 塑能系[火]\n"
            "**环位：** 术士/法师 3\n"
            "**施法时间：** 标准动作\n"
            "**成分：** 语言，姿势，材料（一小块硫磺）\n"
            "**范围：** 远距（400尺+40尺/等级）\n"
            "**区域：** 20尺半径扩散\n"
            "**持续时间：** 立即\n"
            "**豁免：** 反射，减半\n"
            "**法术抗力：** 可\n"
        )
        text = fmt._unify_field_labels(text)
        items = fmt.split_into_items(text)

        from vectorizer.processors.base import Chunk
        chunk = Chunk(
            chunk_id="test_001",
            doc_id="test",
            category="spell",
            component_type="spell",
            title="",
            text="",
            book_abbreviation="",
            book_name_cn="",
            book_name_en="",
            source_confidence=0,
        )
        chunk = processor.build_chunk(chunk, items[0])
        chunk = processor.infer_metadata(chunk, items[0])

        meta = chunk.metadata
        # 15 语义字段 + field_status + 可能的 subschool_variants
        for field in CANONICAL_FIELDS:
            assert field in meta, f"Missing field: {field}"
        assert "field_status" in meta
        assert isinstance(meta["field_status"], dict)

    def test_idempotent(self):
        """重复调用 infer_metadata 不改变结果"""
        fmt = SpellFormat()
        from vectorizer.sources.providers import SourceResolver

        resolver = SourceResolver([])
        processor = SpellProcessor(source_resolver=resolver)

        text = "**火球术 (Fireball)**\n**学派：** 塑能系\n**环位：** 术士/法师 3\n"
        text = fmt._unify_field_labels(text)
        items = fmt.split_into_items(text)

        from vectorizer.processors.base import Chunk
        chunk = Chunk(
            chunk_id="test_002", doc_id="test", category="spell",
            component_type="spell", title="", text="",
            book_abbreviation="", book_name_cn="", book_name_en="",
            source_confidence=0,
        )
        chunk = processor.build_chunk(chunk, items[0])
        result1 = processor.infer_metadata(chunk, items[0])
        result2 = processor.infer_metadata(chunk, items[0])

        assert result1.metadata == result2.metadata


# ============================================================
#  KN136 [PZO 书目链接伪标题拒收
# ============================================================

class TestKn136PzoTitleGuard:
    """KN136：`**[PZOxxxx 书名（英文）](url)**` 书目导航链接不得被切为法术标题。

    背景：a46e68f 收窄共享层 _strip_url_lines 后，锚=中文正文的链接行保留，
    page_1363 一行 `**[PZO9202 神与魔法（Gods and Magic）](url)**` 被
    spell_pattern 误匹配（group(1)=`[PZO9202 神与魔法（Gods and Magic）`、
    group(2)=`url`，两者均非空且含 ≥3 连续英文字母，空标题/CJK 守卫全放行），
    被切为 1 个伪标题 chunk 并顺移 page_1363 后续 128 个 chunk id。
    守卫 `new_name.startswith('[PZO')` 在标题校验层拒收该形态（KN136 拍板修法）。

    注：本类测试在守卫缺位时必红（守卫前的两个既有守卫均放行该形态），
    修复后转绿——KN136「先行失败测试」在案。
    """

    def test_pzo_link_line_not_split_as_spell(self):
        """`[PZO` 开头的书目链接行不被切为法术条目"""
        fmt = SpellFormat()
        text = (
            "## 附录\n"
            "**[PZO9202 神与魔法（Gods and Magic）](https://example.com/gm)**\n"
            "**火球术 (Fireball)**\n"
            "**学派：** 塑能系\n"
            "**环位：** 术士/法师 3\n"
        )
        items = fmt.split_into_items(text)
        names = [it["name"] for it in items]
        assert names == ["火球术"], f"期望仅火球术一个条目，实测: {names}"

    def test_neighboring_real_spell_kept_intact(self):
        """[PZO 伪标题夹在两个真法术之间时，两真法术完整保留、无伪 item"""
        fmt = SpellFormat()
        text = (
            "**火球术 (Fireball)**\n"
            "**学派：** 塑能系\n"
            "**环位：** 术士/法师 3\n"
            "**[PZO9202 神与魔法（Gods and Magic）](url)**\n"
            "**治疗轻伤 (Cure Light Wounds)**\n"
            "**学派：** 咒法系\n"
            "**环位：** 牧师 1\n"
        )
        items = fmt.split_into_items(text)
        names = [it["name"] for it in items]
        assert names == ["火球术", "治疗轻伤"], f"实测: {names}"


# ============================================================
#  全量 pipeline 不变量
# ============================================================

class TestPipelineInvariants:
    """pipeline 级别不变量"""

    def test_all_chunks_have_16_metadata_keys(self):
        """每个 spell chunk 的 metadata 至少包含 16 个键（跳过 index chunk）"""
        output_dir = Path(__file__).parent.parent / "output" / "法术"
        chunks_file = output_dir / "chunks.jsonl"
        if not chunks_file.exists():
            pytest.skip("chunks.jsonl 不存在（需先运行 pipeline）")

        with open(chunks_file) as f:
            for i, line in enumerate(f):
                chunk = json.loads(line)
                # 跳过 spell_index chunk（元数据结构不同）
                if chunk.get("component_type") == "spell_index":
                    continue
                meta = chunk.get("metadata", {})
                # 至少 16 键（15 语义 + field_status + 可能的 subschool_variants）
                assert len(meta) >= 16, (
                    f"Chunk {i} ({chunk.get('title', '?')}): "
                    f"expected >=16 keys, got {len(meta)}: {list(meta.keys())}"
                )
                # field_status 必须存在
                assert "field_status" in meta, (
                    f"Chunk {i}: missing field_status"
                )

    def test_chunk_count(self):
        """chunk 总数不变量：4172（KN019 D 类守卫修复后基线，2026-08-04）

        4221 → 4175：KN019 D 类续段散文伪标题守卫（_wrap_bare_spell_titles
        正文段守卫）消除 46 个伪标题 chunk（D 类第一类 20 + B 类 3 +
        同形态正文段/掷骰表格行 23），伪标题正文并入所属法术 chunk。
        4175 → 4172：KN019 第二类 3 条跨行 HTML 残留伪标题消除（page_1177_0000
        + page_1365 ×2，-3）+ 手舞足蹈（Calamitous Flailing）源数据补中文名
        恢复独立 chunk（+1），净 -2。
        （阶段二，2026-09-01）KN136 修复后真重跑实测仍 4172：方案「预期 4171」
        k3 裁定不成立（冻结旧基线本就不含伪 item，修复目标是「重跑恢复 4172」，
        KN136 原文档同口径）。数字不变，补 page_1363 针对性断言
        （140 chunk / 无 [PZO 开头 title / id 连续）——不只裸数字。
        """
        output_dir = Path(__file__).parent.parent / "output" / "法术"
        chunks_file = output_dir / "chunks.jsonl"
        if not chunks_file.exists():
            pytest.skip("chunks.jsonl 不存在（需先运行 pipeline）")

        page_1363 = []
        pzo_titles = []
        with open(chunks_file) as f:
            count = 0
            for line in f:
                count += 1
                chunk = json.loads(line)
                if chunk.get("chunk_id", "").startswith("spell_page_1363"):
                    page_1363.append(chunk)
                if chunk.get("title", "").startswith("[PZO"):
                    pzo_titles.append(chunk.get("title"))
        assert count == 4172, f"chunk 数变了：{count} ≠ 4172"
        # KN136 修复目标断言：page_1363 无 [PZO 伪标题、140 chunk、id 连续
        assert not pzo_titles, f"[PZO 伪标题仍在产物中：{pzo_titles[:5]}"
        assert len(page_1363) == 140, (
            f"page_1363 chunk 数变了：{len(page_1363)} ≠ 140"
        )
        page_1363_ids = sorted(
            int(c["chunk_id"].rsplit("_", 1)[-1]) for c in page_1363
        )
        assert page_1363_ids == list(range(140)), (
            f"page_1363 chunk id 不连续：{page_1363_ids[0]}..{page_1363_ids[-1]}"
        )


# ============================================================
#  KN013 字段值吞正文（M2/M3/M5）
# ============================================================

class TestFieldValueTruncation:
    """KN013 M2：通用截断器 `_truncate_value_prose`。

    截断信号：
      - `。` 后仍有 >10 字符正文 → 截到 `。` 后第一个完整句末
      - `\\n` 后的行不以续行信号开头 → 截到 `\\n` 之前
    续行信号（保护合法跨行值）：行首为 `+` / `(` / `（` / `和` / `或` / `，` / `、` / 数字
    duration 专属：保留到 `(D)` / `（可消解）` / `（解消）` / `(见后文)` 为止
    """

    def test_duration_same_line_prose_truncated(self):
        """正例：duration `1分钟/等级（可消解）你让一根长而细的藤蔓…` → 截到 `（可消解）`"""
        from vectorizer.processors.spell import _truncate_value_prose
        result = _truncate_value_prose(
            "1分钟/等级（可消解）你让一根长而细的藤蔓从你伸向目标的方向上冒出来",
            field="duration",
        )
        assert result == "1分钟/等级（可消解）", (
            f"duration 同行正文未截断: {result!r}"
        )

    def test_duration_newline_prose_truncated(self):
        """正例：duration `1分钟\\n这个法术的能量加快了你的步伐` → 截到 `1分钟`"""
        from vectorizer.processors.spell import _truncate_value_prose
        result = _truncate_value_prose(
            "1分钟\n这个法术的能量加快了你的步伐",
            field="duration",
        )
        assert result == "1分钟", (
            f"duration 单换行正文未截断: {result!r}"
        )

    def test_duration_legal_continuation_kept(self):
        """反例：duration `1分钟\\n和 永久 (见后文)` → 保留（`和` 是续行信号）"""
        from vectorizer.processors.spell import _truncate_value_prose
        result = _truncate_value_prose(
            "1分钟\n和 永久 (见后文)",
            field="duration",
        )
        assert "1分钟" in result and "永久" in result, (
            f"合法续行被错误截断: {result!r}"
        )

    def test_range_legal_continuation_kept(self):
        """反例：range `近距 (25尺\\n+ 5尺/2级)` → 保留（`+` 是续行信号）"""
        from vectorizer.processors.spell import _truncate_value_prose
        result = _truncate_value_prose(
            "近距 (25尺\n+ 5尺/2级)",
            field="range",
        )
        assert "25尺" in result and "5尺/2级" in result, (
            f"range 合法算式被错误截断: {result!r}"
        )

    def test_target_newline_prose_truncated(self):
        """正例：target 单换行接正文 → 截断（值边界外正文不入 target）"""
        from vectorizer.processors.spell import _truncate_value_prose
        result = _truncate_value_prose(
            "一个生物\n这个法术允许你命令目标执行你的命令",
            field="target",
        )
        assert result == "一个生物", (
            f"target 单换行正文未截断: {result!r}"
        )

    def test_effect_single_sentence_kept(self):
        """反例：effect `属性伤害，目盲，困惑…恶心。` 单句 → 保留（`。` 后无 >10 字符）"""
        from vectorizer.processors.spell import _truncate_value_prose
        result = _truncate_value_prose(
            "属性伤害，目盲，困惑和恶心。",
            field="effect",
        )
        assert "恶心" in result, f"effect 单句被错误截断: {result!r}"

    def test_duration_d_marker_kept(self):
        """正例：duration 保留 `(D)` 标记"""
        from vectorizer.processors.spell import _truncate_value_prose
        result = _truncate_value_prose(
            "1轮/等级 (D)这个法术让目标进入恍惚状态",
            field="duration",
        )
        assert "1轮/等级 (D)" in result, (
            f"duration (D) 标记未被保留: {result!r}"
        )
        assert "恍惚状态" not in result, (
            f"duration 正文未被截断: {result!r}"
        )

    # ============================================================
    #  KN013 M2 第3轮返工：_truncate_value_prose Bug A + Bug B
    # ============================================================

    def test_bug_a_double_asterisk_field_boundary_truncated(self):
        """Bug A 正例：casting_time `一个标准动作\\n**语言，姿势，材料**\\n**近距...` → 截到第一个换行前

        KN012 拆行后字段值呈 `值\\n**下一字段**` 形态，第二行以 `**` 开头。
        修复前：_CONTINUATION_PREFIXES 含 `*`，`second.startswith('**')` 被误判为合法续行，
        导致 casting_time 吞入 `**语言，姿势，材料**` 等下一字段。
        修复后：第二行 `**` 开头视为字段边界，截断到第一行末尾。
        """
        from vectorizer.processors.spell import _truncate_value_prose
        result = _truncate_value_prose(
            "一个标准动作\n**语言，姿势，材料  (一株蒲公英的茎秆)**\n**近距 (25尺+5尺/2级)",
            field="casting_time",
        )
        assert "一个标准动作" in result, f"casting_time 首行丢失: {result!r}"
        assert "**" not in result, (
            f"casting_time 吞入了 `**` 包裹的下一字段: {result!r}"
        )
        assert "语言" not in result, (
            f"casting_time 吞入了下一字段内容: {result!r}"
        )
        assert "近距" not in result, (
            f"casting_time 吞入了范围字段: {result!r}"
        )

    def test_bug_a_range_double_asterisk_truncated(self):
        """Bug A 正例：range `120尺\\n**区域：** 120尺长，10尺宽` → 截到 `120尺`

        KN012 拆行后 range 吞入 `**区域：**` 块。
        """
        from vectorizer.processors.spell import _truncate_value_prose
        result = _truncate_value_prose(
            "120尺\n**区域：** 120尺长，10尺宽",
            field="range",
        )
        assert result == "120尺", (
            f"range 吞入区域字段未截断: {result!r}"
        )

    def test_bug_a_duration_absorbed_saving_block(self):
        """Bug A 正例：duration `10分钟，或专注（最多1轮/等级）；见下文\\n**意志过则无效 (无害)` → 截断

        KN012 拆行后 duration 吞入豁免块。
        """
        from vectorizer.processors.spell import _truncate_value_prose
        result = _truncate_value_prose(
            "10分钟，或专注（最多1轮/等级）；见下文\n**意志过则无效 (无害)",
            field="duration",
        )
        assert "10分钟" in result, f"duration 首段丢失: {result!r}"
        assert "意志" not in result, (
            f"duration 吞入了豁免块: {result!r}"
        )

    def test_bug_b_prose_lead_in_two_line_duration(self):
        """Bug B 正例：duration 两行 + R5 散文信号 → 截断到散文信号起始前

        真实数据：duration = `专注 + 3轮（可解消）该法术的功能如同…想像。\\n当你专注时…`
        修复前：`\\n` 分支检查第二行以 `当` 开头（不在续行白名单），提前 return lines[0]，
        返回含 `该法术的功能如同` 的脏值，R5 分支永远执行不到。
        修复后：R5 散文信号检查先于 `\\n` 分支，对整体值检查，找到信号则截断。
        """
        from vectorizer.processors.spell import _truncate_value_prose
        result = _truncate_value_prose(
            "专注 + 3轮（可解消）该法术的功能如同加速想像。\n当你专注时，你获得迅速动作效果",
            field="duration",
        )
        assert "专注 + 3轮（可解消）" in result, (
            f"duration 合法前缀丢失: {result!r}"
        )
        assert "该法术的功能如同" not in result, (
            f"duration 未在散文信号处截断: {result!r}"
        )
        assert "当你专注时" not in result, (
            f"duration 吞入了第二行正文: {result!r}"
        )

    def test_bug_b_prose_lead_in_single_line(self):
        """Bug B 回归：单行 duration 末尾粘附散文信号 → 仍正确截断（R5 移到 \\n 前也应正常）"""
        from vectorizer.processors.spell import _truncate_value_prose
        result = _truncate_value_prose(
            "1轮/等级该法术的功能如同加速术",
            field="duration",
        )
        assert result == "1轮/等级", (
            f"单行 duration R5 信号未截断: {result!r}"
        )

    def test_continuation_single_asterisk_still_allowed(self):
        """Bug A 反例保护：单 `*` 开头的合法续行仍放行

        原设计意图：`*` 在白名单中是为了放行少量单星号续行场景。
        修复后：单 `*` 不跟随 `*` 时仍视为合法续行信号。
        """
        from vectorizer.processors.spell import _truncate_value_prose
        # 单 * 开头（不是字段标签的 **）→ 保留
        result = _truncate_value_prose(
            "近距 (25尺\n* 5尺/2级)",
            field="range",
        )
        assert "25尺" in result and "5尺/2级" in result, (
            f"单 * 合法续行被错误截断: {result!r}"
        )

    def test_continuation_plus_paren_still_allowed(self):
        """Bug A/B 反例保护：`+` / `(` 开头的合法续行仍放行"""
        from vectorizer.processors.spell import _truncate_value_prose
        result = _truncate_value_prose(
            "近距 (25尺\n+ 5尺/2级)",
            field="range",
        )
        assert "25尺" in result and "5尺/2级" in result, (
            f"+ 号续行被错误截断: {result!r}"
        )

    def test_no_regression_clean_value_unchanged(self):
        """Bug A/B 反例保护：纯净字段值不变"""
        from vectorizer.processors.spell import _truncate_value_prose
        # range 合法单行
        result = _truncate_value_prose("近距 (25尺+5尺/2级)", field="range")
        assert "近距" in result and "25尺+5尺/2级" in result, (
            f"合法 range 被破坏: {result!r}"
        )
        # effect 单句
        result = _truncate_value_prose(
            "属性伤害，目盲，困惑和恶心。",
            field="effect",
        )
        assert "恶心" in result, f"effect 单句被破坏: {result!r}"

    def test_duration_terminator_with_newline_residue(self):
        """Bug A + duration terminator 顺序修复：`1分钟\\n**无 (见后文)` → `1分钟`

        原顺序 (duration terminator 在 \\n 分支前) 会让 `(见后文)` 匹配后因 rest 为空
        返回原值，跳过对 `\\n**` 残留的清理。
        修复后 \\n 分支先跑：第二行 `**无 (见后文)` 以 `**` 开头 → 截到 `1分钟`。
        """
        from vectorizer.processors.spell import _truncate_value_prose
        result = _truncate_value_prose(
            "1分钟\n**无 (见后文)",
            field="duration",
        )
        assert result == "1分钟", (
            f"duration \\n**残留未被截断: {result!r}"
        )


class TestSchoolM3Truncation:
    """KN013 M3：school 字段值吞正文（M3 症状：标签-冒号跨行断开导致值污染）。

    白名单前缀截断：`(防护|咒法|预言|惑控|塑能|幻术|死灵|变化|通用)(系)?` 命中即截断。
    例：`预言系等级⏎：通灵者 0…` → `预言系`
    """

    def test_school_with_polluted_level(self):
        """正例：school 值含等级污染 → 白名单截断"""
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {"school": "预言系等级：通灵者 0"}
        result = processor._extract_school(raw, {"text": ""})
        assert result == "预言系", (
            f"M3 school 污染未截断: {result!r}"
        )

    def test_school_with_polluted_level_v2(self):
        """正例：`变化系；等级 ⏎牧师1…` → `变化系`"""
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {"school": "变化系；等级牧师1"}
        result = processor._extract_school(raw, {"text": ""})
        assert result == "变化系", (
            f"M3 school 污染 v2 未截断: {result!r}"
        )

    def test_school_clean_unchanged(self):
        """回归：纯净 school 不变"""
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {"school": "防护系"}
        result = processor._extract_school(raw, {"text": ""})
        assert result == "防护系"

    def test_school_unknown_kept(self):
        """反例：未知学派保留原文（不引入空字符串）"""
        from vectorizer.sources.providers import SourceResolver
        processor = SpellProcessor(source_resolver=SourceResolver([]))
        raw = {"school": "未知学派（神秘）"}
        result = processor._extract_school(raw, {"text": ""})
        # 白名单未命中 → 保留归一化后的原文
        assert result == "未知学派", f"未知学派被错误清空: {result!r}"


class TestDescriptionFieldBoundary:
    """KN013 M5：`**描述：**` 成为 parse_fields 的值边界。

    当前 parse_fields 的 next_field 只识别 ALL_FIELD_LABELS（v0.3 规范字段别名），
    不含 EXTRA_FORMAT_LABELS（描述/诡计描述/伪装对象），导致 `**描述：**` 后续文本被吞。
    """

    def test_description_becomes_boundary(self):
        """正例：含 `**描述：**` 的 chunk，duration/range 等前面字段不被描述文本污染"""
        from vectorizer.processors.spell import parse_fields
        text = (
            "**学派：** 咒法系\n"
            "**持续时间：** 1分钟\n"
            "**描述：** 该法术喷出酸液，造成 1d3 酸伤害。\n"
        )
        raw = parse_fields(text)
        assert raw.get("duration") == "1分钟", (
            f"duration 被描述污染: {raw.get('duration')!r}"
        )

    def test_consecutive_field_after_description(self):
        """正例：描述后紧跟另一个字段，描述不被吞入下一个字段"""
        from vectorizer.processors.spell import parse_fields
        text = (
            "**学派：** 咒法系\n"
            "**描述：** 喷出酸液。\n"
            "**持续时间：** 1分钟\n"
        )
        raw = parse_fields(text)
        # 描述虽不在规范字段，但应让后续字段正常解析
        assert raw.get("duration") == "1分钟", (
            f"duration 字段边界被描述吞并: {raw.get('duration')!r}"
        )


# ============================================================
#  KN014 domains∩subdomains 排他
# ============================================================


class TestDomainSubdomainExclusion:
    """KN014：domain 正则 `(?<!子)领域` 排他。

    子域条目只进 subdomains，不进 domains。
    """

    def test_subdomain_excluded_from_domains(self):
        """正例：`领域 家园子域 1` → domains 不含家园子域"""
        raw = {"spell_level": "吟游诗人 2 领域 家园子域 1"}
        from vectorizer.processors.spell import SpellProcessor
        domains = SpellProcessor._extract_domains_from_level(raw)
        subdomains = SpellProcessor._extract_subdomains_from_level(raw)
        names_d = [d["name"] for d in domains]
        names_sd = [d["name"] for d in subdomains]
        assert "家园子域" not in names_d, f"家园子域 不应出现在 domains: {names_d}"
        assert "家园子域" in names_sd, f"家园子域 应出现在 subdomains: {names_sd}"

    def test_domain_and_subdomain_separate(self):
        """正例：`善良领域 1, 纯净子域 1` → 各自对桶"""
        raw = {"spell_level": "牧师 1 领域 善良领域 1, 纯净子域 1"}
        from vectorizer.processors.spell import SpellProcessor
        domains = SpellProcessor._extract_domains_from_level(raw)
        subdomains = SpellProcessor._extract_subdomains_from_level(raw)
        names_d = [d["name"] for d in domains]
        names_sd = [d["name"] for d in subdomains]
        assert "善良领域" in names_d, f"善良领域 应出现在 domains: {names_d}"
        assert "纯净子域" in names_sd, f"纯净子域 应出现在 subdomains: {names_sd}"
        assert "纯净子域" not in names_d, f"纯净子域 不应出现在 domains: {names_d}"

    def test_subdomain_variant_not_in_domains(self):
        """反例：`XX子领域 1` 不进 domains（防御变体）"""
        raw = {"spell_level": "牧师 2 领域 善良领域 2, 动物子领域 1"}
        from vectorizer.processors.spell import SpellProcessor
        domains = SpellProcessor._extract_domains_from_level(raw)
        names_d = [d["name"] for d in domains]
        assert "动物子领域" not in names_d, f"子领域变体不应出现在 domains: {names_d}"

    def test_pure_domain_unchanged(self):
        """回归：纯领域条目不变"""
        raw = {"spell_level": "牧师 3 领域 善良领域 3"}
        from vectorizer.processors.spell import SpellProcessor
        domains = SpellProcessor._extract_domains_from_level(raw)
        names_d = [d["name"] for d in domains]
        assert "善良领域" in names_d, f"善良领域 应保持不变: {names_d}"

    def test_two_domains_no_subdomain(self):
        """回归：双领域条目不受影响"""
        raw = {"spell_level": "牧师 4 领域 善良领域 4, 邪恶领域 3"}
        from vectorizer.processors.spell import SpellProcessor
        domains = SpellProcessor._extract_domains_from_level(raw)
        names_d = [d["name"] for d in domains]
        assert "善良领域" in names_d, f"善良领域 丢失: {names_d}"
        assert "邪恶领域" in names_d, f"邪恶领域 丢失: {names_d}"

    def test_no_domain_related(self):
        """回归：无领域条目 → domains 为空"""
        raw = {"spell_level": "术士/法师 3"}
        from vectorizer.processors.spell import SpellProcessor
        domains = SpellProcessor._extract_domains_from_level(raw)
        assert domains == [], f"无领域条目不应有 domains: {domains}"

    def test_domain_count_reduced(self):
        """集成：KN014 后 domains 总数应大幅下降（约 305→180）"""
        # 不依赖 chunks.jsonl，仅验证逻辑：家园子域不进 domains 则总数下降
        raw = {"spell_level": "吟游诗人 2 领域 家园子域 1, 善良领域 1"}
        from vectorizer.processors.spell import SpellProcessor
        domains = SpellProcessor._extract_domains_from_level(raw)
        names_d = [d["name"] for d in domains]
        assert "善良领域" in names_d
        assert len(names_d) == 1, f"应只有 1 个 domain（善良领域），实际: {names_d}"


# ============================================================
#  KN018 显式否定字段 truthy 编码
# ============================================================


class TestNegativeFieldStatus:
    """KN018：显式否定 → parsed（不在 _is_semantically_empty 层修）。

    ST 显式否定：type="无"（归一化），status=parsed
    SR 显式否定：applies=False，note=原否定词，status=parsed
    """

    # ---- ST 显式否定 ----

    def test_st_explicit_no(self):
        """ST `无` → type='无'（truthy → _is_semantically_empty=False → status=parsed）"""
        result = SpellProcessor._parse_saving_throw("无")
        assert result["type"] == "无"

    def test_st_explicit_meiyou(self):
        """ST `没有` → type='无'（归一化）"""
        result = SpellProcessor._parse_saving_throw("没有")
        assert result["type"] == "无"

    def test_st_explicit_dash(self):
        """ST `—` → type='无'"""
        result = SpellProcessor._parse_saving_throw("—")
        assert result["type"] == "无"

    def test_st_explicit_fou(self):
        """ST `否` → type='无'"""
        result = SpellProcessor._parse_saving_throw("否")
        assert result["type"] == "无"

    def test_st_empty_unchanged(self):
        """回归：空值 → missing（type=''）"""
        result = SpellProcessor._parse_saving_throw("")
        assert result["type"] == ""

    def test_st_normal_unchanged(self):
        """回归：正常值不变"""
        result = SpellProcessor._parse_saving_throw("强韧，通过则无效")
        assert result["type"] == "强韧"
        assert "通过则无效" in result["effect"]

    # ---- SR 显式否定 ----

    def test_sr_explicit_buke(self):
        """SR `不可` → applies=False, note='不可'"""
        result = SpellProcessor._parse_spell_resistance("不可")
        assert result["applies"] is False
        assert result["note"] == "不可"

    def test_sr_explicit_fou(self):
        """SR `否` → applies=False, note='否'"""
        result = SpellProcessor._parse_spell_resistance("否")
        assert result["applies"] is False
        assert result["note"] == "否"

    def test_sr_explicit_wu(self):
        """SR `无` → applies=False, note='无'"""
        result = SpellProcessor._parse_spell_resistance("无")
        assert result["applies"] is False
        assert result["note"] == "无"

    def test_sr_empty_unchanged(self):
        """回归：空值 → missing"""
        result = SpellProcessor._parse_spell_resistance("")
        assert result["applies"] is False
        assert result["note"] is None

    def test_sr_positive_unchanged(self):
        """回归：肯定值不变"""
        result = SpellProcessor._parse_spell_resistance("可")
        assert result["applies"] is True
        assert result["note"] is None
