"""
F 类：来源书判定正确

测试目标：
  - FileNameAbbrProvider：CRB → CRB, APG → APG, UM → UM
  - 未知文件名 → 不崩溃，继续下一个 Provider
  - 未知缩写 → 告警（DefaultProvider）
  - 子目录来源推断（冒险之路 → AArch）

溯源于 Bug 002/003
"""

import pytest
from pathlib import Path

from vectorizer.sources.providers import (
    FileNameAbbrProvider, SourceContext, SourceResolver,
    ALL_PROVIDERS, UNKNOWN_SOURCE, ContentBookMentionProvider,
)


class TestSourceResolution:
    """来源书判定"""

    def test_filename_crb(self):
        """Spell CRB.md → CRB"""
        provider = FileNameAbbrProvider()
        ctx = SourceContext(file_path=Path("Spell CRB.md"))
        result = provider.resolve(ctx)
        assert result is not None
        assert result.book_abbreviation == "CRB"

    def test_filename_um(self):
        """Spell UM.md → UM"""
        provider = FileNameAbbrProvider()
        ctx = SourceContext(file_path=Path("Spell UM.md"))
        result = provider.resolve(ctx)
        assert result is not None
        assert result.book_abbreviation == "UM"

    def test_filename_apg(self):
        """Spell APG.md → APG"""
        provider = FileNameAbbrProvider()
        ctx = SourceContext(file_path=Path("Spell APG.md"))
        result = provider.resolve(ctx)
        assert result is not None
        assert result.book_abbreviation == "APG"

    def test_unknown_file(self):
        """未知文件 → DefaultProvider 兜底"""
        resolver = SourceResolver(ALL_PROVIDERS)
        ctx = SourceContext(file_path=Path("unknown_file.md"))
        result = resolver.resolve(ctx)
        assert result.book_abbreviation == "?"

    def test_source_resolver_chain_completes(self):
        """链式聚合对所有输入都能返回结果（不崩溃）"""
        resolver = SourceResolver(ALL_PROVIDERS)
        test_cases = [
            Path("Spell CRB.md"),
            Path("Spell UM.md"),
            Path("unknown_book.md"),
            Path("冒险之路/wrath.md"),
        ]
        for path in test_cases:
            ctx = SourceContext(file_path=path, directory_hints=list(path.parts))
            result = resolver.resolve(ctx)
            assert result is not None, f"{path}: resolver 返回 None"
            assert result.book_abbreviation != "", f"{path}: 来源书为空"


class TestContentBookMentionProvider:
    """ContentBookMentionProvider — 正文来源书线索判定

    P1a 修复（2026-08-02）：误抓正文引用（先决条件交叉引用 / 页码引用 /
    参见 等）为来源书。修复后仅信任「来源声明形态」行：
      标题《X》专长、# 标题、**来源**/**出处**/**Source** 行、
      > 来源：引用块、出自《X》句。
    正文引用形态（先决条件 / 第 N 页 / pg.N / 参见）一律拒绝。

    形态样例取自 40 个 conf=50 实证 doc（专长11/page_1564/恶魔猎人手册 等）。
    """

    def _resolve(self, content: str):
        """构造最小 SourceContext 并走该 Provider（跳过链上其他 Provider）"""
        provider = ContentBookMentionProvider()
        ctx = SourceContext(file_path=Path("unknown_file.md"), file_content=content)
        return provider.resolve(ctx)

    # ---- 信任形态：应命中 ----

    def test_title_book_bracket(self):
        """标题行《X》专长 → 判 X（page_198 形态）"""
        content = "**《极限魔法》专长（****Ultimate\nMagic）******\n正文..."
        result = self._resolve(content)
        assert result is not None
        assert result.book_abbreviation == "UM"

    def test_source_blockquote(self):
        """> 来源：引用块 → 判（惧怖冒险HA 形态）"""
        content = "> 来源：惧怖冒险（Horror Adventures）HA，页码见原书，未整理 → 惧怖冒险HA → 专长\n正文"
        result = self._resolve(content)
        assert result is not None
        assert result.book_abbreviation == "HA"

    def test_source_label_line(self):
        """**来源** 行（含页码）→ 判（page_1564 形态）"""
        content = "**来源** 位面冒险*Planar Adventures* pg. 25\n正文"
        result = self._resolve(content)
        assert result is not None
        assert result.book_abbreviation == "PA"

    def test_origin_statement(self):
        """出自《X》句 → 判（专长42 形态，含 pg 也应判）"""
        content = "**突袭（Spurt，战斗）** 出自《惧怖冒险》(Horror Adventures)，pg8\n正文"
        result = self._resolve(content)
        assert result is not None
        assert result.book_abbreviation == "HA"

    def test_hash_title(self):
        """# X 专长 标题 → 判（古国血脉 形态）"""
        content = "# 古国血脉 BotA 专长\n正文"
        result = self._resolve(content)
        assert result is not None
        assert result.book_abbreviation == "BotA"

    def test_origin_source_label(self):
        """**出处：** 行被信任处理，未收录书 → None 不误判（专长35 形态）

        2026-08-08 装备模块扩展词表：BoG 格拉里昂的混种 已收录（公共层
        SOURCE_BOOK_ABBREVIATIONS 纯新增键），原负例 Bastards of Golarion
        现在应判 BoG；负例改用虚构书名保持「出处行 + 未收录 → None」语义。
        """
        content = "**出处：**Fictional Book of Testing pg. 23\n正文"
        assert self._resolve(content) is None

    # ---- 拒绝形态：应返回 None（不误抓）----

    def test_prerequisite_cross_reference(self):
        """先决条件交叉引用 → 拒绝（恶魔猎人手册 形态）"""
        content = "**先决条件**：恶魔猎手专长ISWG内海世界指南，知识（位面）6\n正文"
        assert self._resolve(content) is None

    def test_body_page_reference(self):
        """正文页码引用「Core Rulebook第442页」→ 拒绝（专长11 形态）"""
        content = "**极地适应**：你将寒冷环境影响视为低一级（Core Rulebook第442页）\n正文"
        assert self._resolve(content) is None

    def test_body_mention(self):
        """正文提及「Pathfinder RPG Ultimate Combat」→ 拒绝（专长3 形态）"""
        content = "决斗是米翁文化的中心。下列专长可以被运用于决斗（Pathfinder RPG Ultimate Combat）\n正文"
        assert self._resolve(content) is None

    def test_cross_line_english(self):
        """跨行英文书名「Core \\r\\nRulebook」→ 拒绝（专长11 跨行形态）"""
        content = "你将寒冷环境影响视为低一级（Core \r\nRulebook第442页）\n正文"
        assert self._resolve(content) is None

    def test_see_reference(self):
        """参见《X》→ 拒绝（专长49 形态）"""
        content = "**专长效果**：你对抗使用火器或科技武器（参见《Pathfinder战役设定》中关于科技的规则）\n正文"
        assert self._resolve(content) is None

    def test_effect_body_reference(self):
        """专长效果行正文引用「RPG Ultimate Magic 138」→ 拒绝（专长7 形态）"""
        content = "**专长效果**：任何由你（Pathfinder RPG Ultimate Magic 138）施放的任何法术的豁免DC都会增加1\n正文"
        assert self._resolve(content) is None

    def test_effect_body_book_page(self):
        """专长效果行正文引用「《异能冒险》208页」→ 拒绝（异能源始OO 形态）"""
        content = "**专长效果**：你学会了执行一种特殊的神秘仪式（《异能冒险》208页）\n正文"
        assert self._resolve(content) is None

    def test_out_of_reference_statement(self):
        """"使用出自《X》的 Y"（引用书中内容）→ 拒绝（第一世界TFWRotF 形态）"""
        content = ("进行恰当的服从仪典可以换来偌大的赐福。妖精誓缚者进阶职业（参见第8页）则能加速"
                   "赐福的获取。除此之外，使用出自《探索者战役设定：内海诸神》的传音者、颂教者和"
                   "卫道者进阶职业的角色也能通过这些赐福和服从仪典来从一位古老者主君处获得力量\n正文")
        assert self._resolve(content) is None

    def test_two_books_same_line_first_wins(self):
        """同一出处行双书 → 取行内最先出现的书（其他专长1 形态：
        ARG 在缩写表顺序上先于 PA，但 PA 在行内先出现 → 判 PA）"""
        content = "**出自《Planar Adventures pg. 28, Advanced Race Guide pg. 174》**\n正文"
        result = self._resolve(content)
        assert result is not None
        assert result.book_abbreviation == "PA"
