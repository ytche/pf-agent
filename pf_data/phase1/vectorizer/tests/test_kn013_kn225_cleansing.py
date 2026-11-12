"""KN013 M1 清洗层 + KN225 PZO 书目行剥除 —— 独立测试（QA 补充）。

覆盖 coder 新增的 `_strip_inline_label_residue`（5 条规则）与
`_strip_pzo_bibliography_lines`，重点压 coder 未测的边界：
连续多个 `**`、值首悬挂、行尾悬挂+续行组合、纯星值、悬空连接词、
合法跨行值不动、PZO 行空行/中文锚不动性。
"""

import pytest

from vectorizer.processors.spell import _parse_field_value, _strip_inline_label_residue
from vectorizer.formats.spell import SpellFormat


class TestStripInlineLabelResidue:
    def test_rule_a_inline_known_label(self):
        assert _strip_inline_label_residue("120尺**区域：** 120尺长，10尺宽") == "120尺"

    def test_rule_a_label_with_colon_variants(self):
        assert _strip_inline_label_residue("接触**目标或目标们**：你与一名生物") == "接触"

    def test_rule_b_inline_nonlabel_prose(self):
        assert _strip_inline_label_residue("个人**法术") == "个人"
        assert _strip_inline_label_residue(
            "1分钟/等级**当你施放该法术，你可以从小型或中型的虫类中选择一种。"
        ) == "1分钟/等级"

    def test_rule_c_trailing_star_keeps_continuation(self):
        assert (
            _strip_inline_label_residue("专注，最高10分钟/等级 **\n(可解消)")
            == "专注，最高10分钟/等级 \n(可解消)"
        )

    def test_rule_c_then_rule_d_star_at_line_start(self):
        # 行尾摘星后剩余行首出现 ** → 下一轮按规则 d 截断，不得死循环
        assert _strip_inline_label_residue("10分钟/等级 **\n**意志") == "10分钟/等级"

    def test_rule_d_star_at_line_start(self):
        assert _strip_inline_label_residue("两个生物\n**意志，通过则部分生效") == "两个生物"
        assert _strip_inline_label_residue("立即\n**") == "立即"

    def test_rule_e_leading_star(self):
        assert _strip_inline_label_residue("**1轮/级") == "1轮/级"
        assert _strip_inline_label_residue("**中距 (100+10尺/级)") == "中距 (100+10尺/级)"

    def test_dangling_conjunction_removed(self):
        assert _strip_inline_label_residue("10分钟/等级或 **") == "10分钟/等级"
        assert _strip_inline_label_residue("值 或 **") == "值"

    @pytest.mark.parametrize("raw", ["", "**", "****", " ** "])
    def test_pure_double_star_values(self, raw):
        # 不得抛异常；输出不得残留 *
        out = _strip_inline_label_residue(raw)
        assert "*" not in out

    def test_single_star_passthrough(self):
        # 单个 * 不属于 KN013 M1 口径（`**` 对），原样透传（锁定现状）
        assert _strip_inline_label_residue("1轮*") == "1轮*"

    def test_consecutive_double_stars(self):
        assert _strip_inline_label_residue("值****标签：** x") == "值"
        assert _strip_inline_label_residue("值******") == "值"

    def test_legit_multiline_value_untouched(self):
        v = "近距 \n(25呎+5呎/2等级)"
        assert _strip_inline_label_residue(v) == v

    def test_no_star_value_passthrough(self):
        v = "1标准动作"
        assert _strip_inline_label_residue(v) == v

    def test_none_and_empty(self):
        assert _strip_inline_label_residue("") == ""
        assert _strip_inline_label_residue(None) is None or _strip_inline_label_residue(None) == ""

    def test_trailing_star_no_continuation(self):
        assert _strip_inline_label_residue("10分钟/等级 (可解消)**") == "10分钟/等级 (可解消)"

    def test_overtruncate_risk_bold_inside_value(self):
        # 规则 b 对值内任意行内 ** 一律截断：值内合法加粗（若有）会被截掉。
        # 当前全量产物 66738 个字段值 0 残留、备份比对 101 处全部为真残留，
        # 暂无实测误伤；此用例锁定"值内非标签加粗被截断"的既有行为以备回归参照。
        assert _strip_inline_label_residue("火焰 **塑能** 效果") == "火焰"


class TestParseFieldValue:
    def test_none_passthrough(self):
        assert _parse_field_value(None, field="duration") is None

    def test_m1_then_m2(self):
        # M1 截断先于 M2 散文截断
        assert _parse_field_value("1轮/等级**豁免 **无", field="duration") == "1轮/等级"


class TestStripPzoBibliography:
    fmt = SpellFormat.__new__(SpellFormat)

    def test_tight_url_stripped(self):
        t = "前文\n**[PZO9202 神与魔法（Gods and Magic）](http://x.y/z)**\n后文"
        assert self.fmt._strip_pzo_bibliography_lines(t) == "前文\n\n后文"

    def test_chinese_anchor_untouched(self):
        t = "**[正文锚](http://x.y)**"
        assert self.fmt._strip_pzo_bibliography_lines(t) == t

    def test_non_pzo_link_untouched(self):
        t = "**[其他书目 ABC123](http://x.y)**"
        assert self.fmt._strip_pzo_bibliography_lines(t) == t

    def test_pzo_link_inline_not_whole_line_untouched(self):
        t = "正文 **[PZO9202](http://x.y)** 正文"
        assert self.fmt._strip_pzo_bibliography_lines(t) == t

    def test_spaced_url_variant(self):
        t = "前文\n**[PZO9202 神与魔法] (http://x.y/z)**\n后文"
        assert self.fmt._strip_pzo_bibliography_lines(t) == "前文\n\n后文"
