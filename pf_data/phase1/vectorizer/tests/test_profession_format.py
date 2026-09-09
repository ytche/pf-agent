"""test_profession_format.py — ProfessionFormat 块拆分语义 seed 单测

参照 skill 的 test_skill_format.py seed 形态（真实源数据形态切片驱动），覆盖
ProfessionFormat 公开 API split_into_items（行 → 块）的拆分语义：
- 按 `## ` 标题拆块（level 保真）
- HTML 来源注释（<!-- X-source:... -->）剥离进 markers，不混入 text
- 表格行保留在块 text（职业等级表是合法块内容）
- 来源行（> 来源：...）暂留 text（后续块层处理）

与 test_profession_kn222.py（单函数：_looks_like_class_table /
promote_inline_ability_headings）互补。
"""
from vectorizer.formats.profession import ProfessionFormat


def _fmt() -> ProfessionFormat:
    f = ProfessionFormat()
    f.doc_id = "核心职业/圣骑士/page_55.md"
    return f


class TestSplitIntoBlocks:
    """split_into_items 行 → 块拆分语义"""

    def test_split_by_heading_level(self):
        """按 ## 标题拆块，level 保真"""
        seed = (
            "## 圣律沿循者（Oathbound Paladin）【圣骑士变体】\n"
            "\n"
            "介绍文字。\n"
            "\n"
            "## 反腐化誓约（Oath against Corruption）\n"
            "\n"
            "子能力正文。\n"
        )
        items = _fmt().split_into_items(seed, source_name="page_55.md")
        assert len(items) == 2
        assert [it["level"] for it in items] == [2, 2]
        assert items[0]["title"] == "圣律沿循者（Oathbound Paladin）【圣骑士变体】"
        assert "反腐化誓约" in items[1]["title"]

    def test_source_marker_extracted(self):
        """HTML 来源注释 → markers，text 中剥离"""
        seed = (
            "## 灰骑士（Gray Paladin）【UI 圣骑士变体】\n"
            "\n"
            "<!-- UI-source:page_352.md:灰骑士 -->\n"
            "\n"
            "正文。\n"
        )
        items = _fmt().split_into_items(seed, source_name="page_55.md")
        assert len(items) == 1
        block = items[0]
        assert "<!--" not in block["text"], "来源注释不应混入 text"
        assert len(block["markers"]) == 1
        m = block["markers"][0]
        assert m.source_book_abbr == "UI"
        assert m.anchor == "灰骑士"

    def test_table_preserved_in_text(self):
        """职业等级表行保留在块 text（KN222 简写表头形态）"""
        seed = (
            "## 冬女巫（Winter Witch）【UM 女巫变体】\n"
            "\n"
            "| 等级 | BAB | 强韧 | 反射 | 意志 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 1级 | +0 | +0 | +0 | +1 |\n"
            "\n"
            "正文。\n"
        )
        items = _fmt().split_into_items(seed, source_name="page_70.md")
        assert len(items) == 1
        assert "| 1级 | +0 | +0 | +0 | +1 |" in items[0]["text"], "等级表行不得被丢弃"

    def test_source_line_kept_for_block_layer(self):
        """> 来源：行暂留 text（块层/后处理负责剥离）"""
        seed = (
            "## 神卫（Divine Guardian）【CaC 圣骑士变体】\n"
            "\n"
            "正文。\n"
            "\n"
            "> 来源：部属与伙伴（Cohorts and Companions）CaC\n"
        )
        items = _fmt().split_into_items(seed, source_name="page_55.md")
        assert len(items) == 1
        assert "部属与伙伴" in items[0]["text"], "来源行由块层处理，本层不剥离"

    def test_breadcrumbs_prefix_doc(self):
        """breadcrumbs 以文件名为根，逐级累积标题"""
        seed = (
            "## 反腐化誓约（Oath against Corruption）\n"
            "\n"
            "正文。\n"
        )
        items = _fmt().split_into_items(seed, source_name="page_55.md")
        assert items[0]["breadcrumbs"][0] == "page_55"
        assert "反腐化誓约" in items[0]["breadcrumbs"][-1]
