"""KN234 白盒补充测试：split_into_items 子效果守卫（双信号）。

信号① `_RE_SUBEFFECT_MARK`：加粗行以 1~2 个非中文符号（CHM 丢失的项目
符号/字形，如源 md 订正前的 `**?   尘埃（气/土）**`）开头 + 空白 + 内容。
信号② `_RE_SUBEFFECT_ELEMENT_PAIR`（2026-09-22 源 md 订正方向 B 后适配）：
加粗独立行 = 短中文名 +（单字元素描述符对，如（气/土））——融合效果子项
结构特征，与条目名/文件名无关。

覆盖：
- 正例（信号①）：`**?   尘埃（气/土）**` 并入当前条目，不产新条目；
- 正例（信号②）：`**尘埃（气/土）**`（订正后形态）并入当前条目；
- 反例（信号①）：`**① xxx**` / `**※ xxx**`（同为符号开头）——守卫无
  符号白名单，这些行同样被并入，用例显式钉住该行为以供评审（D-3）；
- `cur is None`（条目外）不吞；
- 英文标题 / 【3.5R】 / 同行冒号正文 形态天然不匹配。
"""

import pytest

from vectorizer.formats.feat import (
    FeatFormat,
    _RE_SUBEFFECT_MARK,
    _RE_SUBEFFECT_ELEMENT_PAIR,
)


def _split(text: str):
    return FeatFormat().split_into_items(text, source_name="kn234_probe.md")


class TestSubeffectGuardRegex:
    @pytest.mark.parametrize("line", [
        "**?   尘埃（气/土）**",
        "**? 尘埃**",
        "**◆ 融合效果**",
        "**?? 双符号**",
    ])
    def test_matches_symbol_prefixed_bold(self, line):
        assert _RE_SUBEFFECT_MARK.match(line)

    @pytest.mark.parametrize("line", [
        "**元素融合（Elemental Commixture）**",
        "**【3.5R】旧版专长**",
        "**中文标题**",
        "**尘埃（气/土）**：描述同行",  # 无闭合加粗独立行
        "**?无空白分隔**",  # 符号后无空白 → 不命中（\s+ 必需）
    ])
    def test_not_matches_legit_titles(self, line):
        assert not _RE_SUBEFFECT_MARK.match(line)


class TestSubeffectElementPairRegex:
    """信号②：订正方向 B 后的子效果形态（短中文名+（单字/单字））。"""

    @pytest.mark.parametrize("line", [
        "**尘埃（气/土）**",
        "**熔岩（土/火）**",
        "**蒸汽（火/水）**",
        "**霜雪（气/水）**",
        "**泥淖（土/水）**",
        "**烟雾（气/火）**",
    ])
    def test_matches_element_pair_bold(self, line):
        assert _RE_SUBEFFECT_ELEMENT_PAIR.match(line)

    @pytest.mark.parametrize("line", [
        "**元素融合（Elemental Commixture）**",   # 括号内非描述符对
        "**某专长（战斗）**",                       # 单元素无斜杠
        "**某专长（气/土/火）**",                   # 三元素
        "**某专长（ 气/土）**",                     # 空白前缀
        "**长中文名称超过六字（气/土）**",           # 名长 >6
        "**尘埃（气/土）**：描述同行",              # 无闭合加粗独立行
    ])
    def test_not_matches_legit_titles(self, line):
        assert not _RE_SUBEFFECT_ELEMENT_PAIR.match(line)


class TestSubeffectGuardSplit:
    def test_subeffect_merged_into_parent(self):
        items = _split(
            "**元素融合（Elemental Commixture，团队专长）**\n"
            "你可以结合元素法术。\n"
            "**?   尘埃（气/土）**\n"
            "目标被尘埃呛住。\n"
        )
        assert len(items) == 1
        assert "尘埃（气/土）" in items[0]["text"]
        assert "目标被尘埃呛住" in items[0]["text"]

    def test_subeffect_merged_into_parent_direction_b_form(self):
        # 源 md 订正方向 B（删 `?` 前缀）后的形态：元素描述符对信号②命中
        items = _split(
            "**元素融合（Elemental Commixture，团队专长）**\n"
            "你可以结合元素法术。\n"
            "**尘埃（气/土）**\n"
            "目标被尘埃呛住。\n"
            "**蒸汽（火/水）**\n"
            "目盲 1D4 轮。\n"
        )
        assert len(items) == 1
        assert "尘埃（气/土）" in items[0]["text"]
        assert "蒸汽（火/水）" in items[0]["text"]

    def test_no_merge_before_any_item(self):
        # 守卫要求 cur is not None：条目外的符号行不得被并入后续条目。
        # 注意：单文件探针（无来源行）split 本身不产条目（formats 层既有
        # 行为，与 KN234 无关），故此处用真实来源行构造最小合法条目。
        items = _split(
            "# 探针 专长\n"
            "<!-- 探针-source:probe.md -->\n"
            "> 来源：探针（Probe），未整理 → 探针 → 专长\n"
            "**?   孤行**\n"
            "正文。\n"
        )
        texts = "\n".join(i.get("text", "") for i in items)
        assert "孤行" not in texts or all(
            "孤行" not in i.get("text", "") for i in items[1:]
        )

    def test_multiple_subeffects_single_parent(self):
        items = _split(
            "**法术融合（Spell Fusion）**\n"
            "总述。\n"
            "**?   尘埃（气/土）**\n"
            "**?   熔岩（土/火）**\n"
            "**?   蒸汽（火/水）**\n"
            "尾段。\n"
        )
        assert len(items) == 1
        for kw in ("尘埃", "熔岩", "蒸汽"):
            assert kw in items[0]["text"]

    def test_symbol_circle_number_also_merged_current_behavior(self):
        # 行为钉住：①/※ 等符号开头行当前同样被并入（守卫无符号白名单）。
        items = _split(
            "**某专长（Some Feat）**\n"
            "正文。\n"
            "**① 第一步**\n"
            "步骤内容。\n"
        )
        assert len(items) == 1
        assert "① 第一步" in items[0]["text"]
