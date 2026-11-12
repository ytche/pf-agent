"""
test_trait_kn137_qa.py — KN137 背景特性来源归书 独立 QA 白盒补充测试

审计目的（对照 coder 7 条自报单测的盲区）：
  - formats 层 _RE_OUTER_BOOK_LEAD_STAR（R6）完全无单测：补幂等性 / 误伤面 /
    字符集边界（【】含 *、超长、无括号壳、无标题壳）
  - processor 页级默认 _PAGE_SOURCE_DEFAULT 的 doc_id 精确匹配（前缀相似
    文件名不得命中）
  - 基础页前缀键的页范围 guard（startswith("page_") 过宽的实测行为记录）

注意：本文件为 QA 审计产物，不改实现；如发现实现行为与方案不符，以断言
失败暴露，由实现方处理。
"""

from pathlib import Path

import pytest

from vectorizer.formats.trait import _RE_OUTER_BOOK_LEAD_STAR
from vectorizer.processors.trait import TraitProcessor, _PAGE_SOURCE_DEFAULT


def _strip(text: str) -> str:
    return _RE_OUTER_BOOK_LEAD_STAR.sub(r"\1\2**", text)


def make_processor():
    from vectorizer.sources.providers import SourceResolver

    return TraitProcessor(source_resolver=SourceResolver([]))


def _resolve(file_path: Path, item: dict = None):
    proc = make_processor()
    ctx = proc._build_source_context(file_path, "")
    chunk = proc._build_chunk_template(file_path, 0, ctx)
    return proc.resolve_source(chunk, ctx, item or {})


# ============================================================
# R6：_RE_OUTER_BOOK_LEAD_STAR（残星剥除）
# ============================================================


class TestOuterBookLeadStar:
    def test_strip_four_star_lead(self):
        """`）****【书】**` 4 星残壳 → 目标形态 `）【书】**`（KN137 R6 主形态）"""
        src = "**背刺者（Backstabber）****【CEoD】**\n正文"
        assert _strip(src) == "**背刺者（Backstabber）【CEoD】**\n正文"

    def test_strip_two_star_minimal(self):
        r"""`\**{2,}` 下界 2 星也剥（壳外闭星+【书】粘连同目标形态）"""
        src = "**背刺者（Backstabber）**【CEoD】**"
        assert _strip(src) == "**背刺者（Backstabber）【CEoD】**"

    def test_idempotent(self):
        """幂等：二次执行输出不变（fix_* 纪律，方案验收标准 6）"""
        src = "**背刺者（Backstabber）****【CEoD】**"
        once = _strip(src)
        assert _strip(once) == once

    def test_book_content_with_star_not_matched(self):
        """【】内容含 `*`（如切利亚斯支持者 `【SH****】` 内残星形态）不匹配、
        不吞字符——该形态为 KN241 登记范围，正则须保持不动作而非半剥"""
        src = "**切利亚斯支持者（Chelish Sympathizer）****【SH****】**"
        assert _strip(src) == src

    def test_no_title_shell_not_matched(self):
        """无 `**中文（EN）` 标题壳（正文普通 `）****【注】**`）不误剥"""
        src = "这是正文（见上文）****【注】**后续文字"
        assert _strip(src) == src

    def test_no_paren_shell_not_matched(self):
        """无括号壳的 `**条目名****【书】**` 不匹配（无（EN）段）——
        记录为 R6 形态盲区：此类噪声当前不存在于库内"""
        src = "**某条目****【CEoD】**"
        assert _strip(src) == src

    def test_book_content_over_12_chars_not_matched(self):
        """【】内容 >12 字符不匹配（防御超长误吃）"""
        src = "**背刺者（Backstabber）****【这是一段超长的来源描述文字】**"
        assert _strip(src) == src

    def test_en_part_with_paren_not_matched(self):
        """EN 段内嵌括号（charset 排除（））不匹配——不拆合法嵌套标题"""
        src = "**背刺者（Backstabber（Dex））****【CEoD】**"
        assert _strip(src) == src

    def test_name_over_24_chars_not_matched(self):
        """中文名 >24 字符不匹配"""
        src = "**" + "超" * 30 + "（EN）****【CEoD】**"
        assert _strip(src) == src


# ============================================================
# R4/R5：_PAGE_SOURCE_DEFAULT doc_id 精确匹配
# ============================================================


class TestPageSourceDefaultDocIdExactness:
    def test_default_table_keys(self):
        """默认表仅含两页（方案 R4/R5 拍板最小集，防配置漂移扩大误归书）"""
        assert set(_PAGE_SOURCE_DEFAULT) == {"page_154", "典范背景"}

    def test_similar_filename_not_matched(self):
        """前缀相似文件名 `典范背景X.md` 不得命中页面级默认 CoL"""
        chunk = _resolve(Path("pf_rules_md_organized/背景特性/典范背景X.md"))
        assert chunk.book_abbreviation == "?"

    def test_page_154_suffixed_not_matched(self):
        """`page_1540`（数字后缀文件，若存在）不得命中 page_154 默认"""
        chunk = _resolve(Path("pf_rules_md_organized/背景特性/page_1540.md"))
        assert chunk.book_abbreviation == "?"

    def test_non_default_page_unchanged(self):
        """page_155（不在默认表）无来源线索仍为 '?'"""
        chunk = _resolve(Path("pf_rules_md_organized/背景特性/page_155.md"))
        assert chunk.book_abbreviation == "?"


# ============================================================
# R1：基础页前缀键页范围 guard
# ============================================================


class TestBasicPagePrefixKeyGuard:
    def test_prefix_key_only_page_docs(self):
        """非 page_ 前缀 doc（如 背景特性17）裸 HoG 不落前缀键 → '?'"""
        chunk = _resolve(
            Path("pf_rules_md_organized/背景特性/背景特性17.md"),
            {"source": "HoG"},
        )
        assert chunk.book_abbreviation == "?"

    def test_prefix_key_narrowed_to_155_157(self):
        """QA-1 收窄（2026-10-28 拍板）：guard 从 startswith('page_') 收窄到
        仅 page_155~157——page_150 裸 HoG 不再落前缀键 → '?'"""
        chunk = _resolve(
            Path("pf_rules_md_organized/背景特性/page_150.md"),
            {"source": "HoG"},
        )
        assert chunk.book_abbreviation == "?"

    def test_prefix_key_still_applies_in_155_157(self):
        """收窄后拍板语境内前缀键照常命中（page_155 裸 HoG → HaG）"""
        chunk = _resolve(
            Path("pf_rules_md_organized/背景特性/page_155.md"),
            {"source": "HoG"},
        )
        assert chunk.book_abbreviation == "HaG"
        assert chunk.source_confidence == 60

    def test_direct_key_wins_over_prefix(self):
        """已有直达键（USH）不被前缀逻辑干扰（同页共存多键）"""
        chunk = _resolve(
            Path("pf_rules_md_organized/背景特性/page_156.md"),
            {"source": "USH"},
        )
        assert chunk.book_abbreviation == "USH"
        assert chunk.source_confidence == 60


# ============================================================
# KN241：R6 未覆盖三种条目级【书】噪声形态（2026-10-28 修复）
# ============================================================

from vectorizer.formats.trait import (
    _RE_BOOK_IN_EN_PAREN,
    _RE_BOOK_LINE_COLON_INLINE,
    _RE_HALF_SHELL_BOOK_GLUE,
)


def _norm(text: str) -> str:
    from vectorizer.formats.trait import TraitFormat

    return TraitFormat().normalize(text)


def _split(text: str) -> dict:
    from vectorizer.formats.trait import TraitFormat

    items = TraitFormat().split_into_items(TraitFormat().normalize(text))
    return {it["name"]: it for it in items}


class TestHalfShellBookGlue:
    """形态①：星壳提前闭合 `**CN**（EN）【书】**` → `**CN（EN）【书】**`"""

    def test_merges_half_shell(self):
        src = "**切利亚斯支持者**（Chelish Sympathizer）【SH】**：每月一次"
        assert _RE_HALF_SHELL_BOOK_GLUE.sub(r"\1\2\3**", src) == (
            "**切利亚斯支持者（Chelish Sympathizer）【SH】**：每月一次"
        )

    def test_idempotent(self):
        src = "**切利亚斯支持者**（Chelish Sympathizer）【SH】**"
        once = _RE_HALF_SHELL_BOOK_GLUE.sub(r"\1\2\3**", src)
        assert _RE_HALF_SHELL_BOOK_GLUE.sub(r"\1\2\3**", once) == once

    def test_standard_form_untouched(self):
        """标准壳内【书】形态不误伤"""
        src = "**切利亚斯支持者（Chelish Sympathizer）【SH】**：每月一次"
        assert _RE_HALF_SHELL_BOOK_GLUE.sub(r"\1\2\3**", src) == src

    def test_end_to_end_sh(self):
        """page_153 切利亚斯支持者端到端：item 产出 + source=SH"""
        items = _split("**切利亚斯支持者**（Chelish Sympathizer）【SH】**：正文")
        assert items["切利亚斯支持者"]["source"] == "SH"
        assert items["切利亚斯支持者"]["name_en"] == "Chelish Sympathizer"


class TestBookInEnParen:
    """形态②：【书】在 EN 括号内 `（EN【书】）` → `（EN）【书】`"""

    def test_moves_book_out(self):
        src = "**诡器使（Surprise Weapon【UCa】）**：正文"
        assert _RE_BOOK_IN_EN_PAREN.sub(r"\1\3\2", src) == (
            "**诡器使（Surprise Weapon）【UCa】**：正文"
        )

    def test_idempotent(self):
        src = "**诡器使（Surprise Weapon【UCa】）**"
        once = _RE_BOOK_IN_EN_PAREN.sub(r"\1\3\2", src)
        assert _RE_BOOK_IN_EN_PAREN.sub(r"\1\3\2", once) == once

    def test_standard_form_untouched(self):
        src = "**诡器使（Surprise Weapon）【UCa】**：正文"
        assert _RE_BOOK_IN_EN_PAREN.sub(r"\1\3\2", src) == src

    def test_end_to_end_uca(self):
        """page_150 诡器使端到端：source=UCa 且 name_en 不含【书】残片"""
        items = _split("**诡器使（Surprise Weapon【UCa】）**：正文")
        assert items["诡器使"]["source"] == "UCa"
        assert items["诡器使"]["name_en"] == "Surprise Weapon"


class TestBookLineColonInline:
    """形态③：裸标题行+下行星壳包【书】冒号正文（冒号在壳内）"""

    def test_merges_lines(self):
        src = "**护枪匠（Unblemished Barrel）**\n**【UCa】：**正文"
        assert _RE_BOOK_LINE_COLON_INLINE.sub(r"\1【\2】**：", src) == (
            "**护枪匠（Unblemished Barrel）【UCa】**：正文"
        )

    def test_idempotent(self):
        src = "**护枪匠（Unblemished Barrel）**\n**【UCa】：**正文"
        once = _RE_BOOK_LINE_COLON_INLINE.sub(r"\1【\2】**：", src)
        assert _RE_BOOK_LINE_COLON_INLINE.sub(r"\1【\2】**：", once) == once

    def test_glue_disjoint_form_untouched(self):
        """_RE_LINE_LEAD_BOOK_GLUE 形态（星在冒号外 `】**：`）不误伤"""
        src = "**护枪匠（Unblemished Barrel）**\n**【UCa】**：正文"
        assert _RE_BOOK_LINE_COLON_INLINE.sub(r"\1【\2】**：", src) == src

    def test_end_to_end_strike_shell(self):
        """page_150 护枪匠端到端：删除线壳源形态 → item 产出 + source=UCa"""
        src = (
            "~~　　**护枪匠（~~****~~Unblemished \nBarrel~~****~~）~~"
            "****~~【UCa】：~~**~~你对火器的精熟~~\n\n"
        )
        items = _split(src)
        assert items["护枪匠"]["source"] == "UCa"
        assert items["护枪匠"]["name_en"] == "Unblemished Barrel"
        assert "你对火器的精熟" in items["护枪匠"]["text"]
