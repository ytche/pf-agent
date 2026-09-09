"""test_profession_kn222.py — KN222 修复 TDD 测试（红→绿）

KN222（pf_data/phase1/docs/已知问题记录.md:6026+）：进阶职业简写表头块整块被
纯表格过滤器丢弃（PoP 冬女巫 page_754 先决条件丢失，40 页受影响）。

根因：
- 主因：`_looks_like_class_table` 只认全称表头（基本攻击加值/强韧豁免/反射豁免/
  意志豁免），不认简写表头（`| 等级 | BAB | 强韧 | 反射 | 意志 |`）→ keep() 判定
  is_pure_table_or_nav=True + _looks_like_class_table=False → 整块（含先决条件
  与等级表）DROP。
- 次因：`promote_inline_ability_headings` 的标题截取把过渡句前缀吞进标题
  （如「后述内容为…职业能力。」+ 能力名）。

修复边界（k3 拍板）：只动 `_looks_like_class_table` 简写表头识别 +
`promote_inline_ability_headings` 过渡句边界；源数据微调本批不做。
merge_line_breaks 等其余交互污染如实测仍影响 page_754 找回，停线回报 k3。

本文件在修复前运行必失败（红），修复后全绿（绿）。
"""
from pathlib import Path

import pytest

from vectorizer.formats.profession import promote_inline_ability_headings
from vectorizer.processors.profession import (
    ProfessionProcessor,
    _looks_like_class_table,
)

# vectorizer/tests/ 的祖父目录 = pf_data/phase1
PHASE1 = Path(__file__).resolve().parents[2]
INPUT_DIR = PHASE1 / "pf_rules_md_organized" / "职业"
PAGE_754 = INPUT_DIR / "进阶职业" / "PoP进阶之路" / "page_754.md"


@pytest.fixture(scope="module")
def proc() -> ProfessionProcessor:
    """全量装配一次（load_resources 做 canonical 去重 + 变体主表预扫描）。"""
    p = ProfessionProcessor(source_resolver=None)
    p.load_resources(INPUT_DIR)
    return p


# ============================================================
#  主因：_looks_like_class_table 简写表头识别
# ============================================================


class TestLooksLikeClassTableAbbrev:
    """简写表头（BAB/强韧/反射/意志）应被识别为职业等级表"""

    def test_abbrev_standard_header(self):
        """PoP 冬女巫 page_754 标准简写表头（含职业能力/每日法术列）"""
        text = (
            "| 等级 | BAB | 强韧 | 反射 | 意志 | 职业能力 | 每日法术 |\n"
            "| 1级 | +0 | +0 | +0 | +1 | 极寒庇护主 | － |\n"
            "| 2级 | +1 | +1 | +1 | +1 | 融雪冻冰 | +1女巫等级 |\n"
        )
        assert _looks_like_class_table(text) is True

    def test_abbrev_empty_cell_header(self):
        """空列简写表头（| 等级 || BAB || 强韧 || 反射 || 意志 |）"""
        text = "| 等级 || BAB || 强韧 || 反射 || 意志 || 特殊能力 || 每日法术 |\n"
        assert _looks_like_class_table(text) is True

    def test_abbrev_no_spell_column(self):
        """简写表头但只有特殊能力列"""
        text = "| 等级 | BAB | 强韧 | 反射 | 意志 | 特殊能力 |\n"
        assert _looks_like_class_table(text) is True

    def test_full_header_still_ok(self):
        """全称表头（CRB 既有识别）行为不变"""
        text = "| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 | 特殊能力 |\n"
        assert _looks_like_class_table(text) is True

    def test_phantom_table_not_matched(self):
        """召唤师魅影表（HD/BAB/豁免/技能）不是职业等级表，不误伤"""
        text = (
            "| 等级 | HD | BAB | 豁免 | 技能 | 专长 | 护甲加值 | 魅敏加值 | 挥击伤害 | 特殊能力 |\n"
            "| 1级 | 1 | +0 | +2 | 2 | 1 | +0 | +0 | 1d4 | 无 |\n"
        )
        assert _looks_like_class_table(text) is False

    def test_prose_not_matched(self):
        """正文提到豁免/BAB（非表格）不误判"""
        text = "冬女巫的先决条件是知识（奥术）5级，法术辨识5级，强韧豁免达标。"
        assert _looks_like_class_table(text) is False


# ============================================================
#  次因：promote_inline_ability_headings 过渡句边界
# ============================================================


class TestPromoteInlineAbilityHeadingBoundary:
    """过渡句前缀不进入能力标题"""

    def test_lead_in_not_in_title(self):
        """「后述内容为…职业能力。」是过渡句，应从标题剥离、留在正文"""
        line = (
            "后述内容为冬女巫进阶职业的职业能力。"
            "**武器与护甲擅长（Weapon and Armor Proficiency）：**"
            "冬女巫不获得任何额外的武器或护甲擅长。"
        )
        out = promote_inline_ability_headings([line])
        assert out, "应识别出能力标题"
        assert out[0].startswith("### ")
        assert "后述内容" not in out[0], "过渡句不应进入标题"
        assert "武器与护甲擅长（Weapon and Armor Proficiency）" in out[0]

    def test_ability_heading_unchanged(self):
        """无过渡句的正常能力标题行为不变"""
        line = "**极寒庇护主（Hyperboreal Patronage）：**冬女巫的庇护主显现出寒冷的面貌。"
        out = promote_inline_ability_headings([line])
        assert out
        assert out[0] == "### 极寒庇护主（Hyperboreal Patronage）"

    def test_nested_bold_ability_heading(self):
        """嵌套粗体形态（**能力名（****English, Ex****）**：）标题提取正确。

        术士/牧师等职业能力页常见 `**酸性射线（****Acidic Ray, Sp****）**：正文`，
        标题本体是去星号后行首到冒号（含嵌套英文），不能因尾随闭合 ** 而取空。
        """
        line = "**酸性射线（****Acidic Ray, Sp****）**：1级开始，你能用标准动作发出一道酸性射线。"
        out = promote_inline_ability_headings([line])
        assert out
        assert out[0] == "### 酸性射线（Acidic Ray, Sp）"

    def test_scattered_star_title_not_stripped(self):
        """散星号形态（*战斗大师（**Battle Master**，ＥＸ）：*正文）标题不被误剥。

        萨满 page_112 的能力行英文粗体在标题中部（非标题开头 **），「第一个 ** 之前」
        是标题前半而非过渡句——无句末标点则不得剥离，否则能力名被切剩英文。
        """
        line = (
            "*战斗大师（**Battle Master**，ＥＸ）：*"
            "每轮可以额外进行１次借机攻击。这个能力给予的借机攻击可以与战斗反射专长给予的次数叠加。"
        )
        out = promote_inline_ability_headings([line])
        assert out
        assert out[0] == "### 战斗大师（Battle Master，ＥＸ）", out[0]

    def test_field_label_title_not_stripped(self):
        """字段标签形态（念动（Telekinetic Blast）**元素**：正文）标题不被误剥。

        操念使原力整合的能力行标题不在 ** 开头，首个粗体是字段标签 **元素**；
        标题含 `（Telekinetic Blast）` 英文但无句末标点，剥离会丢掉能力名，必须保持旧行为。
        """
        line = (
            "念动（Telekinetic "
            "Blast）**元素**：以太；**类别**：简易念袭（Sp）；**等级**：－；"
            "**超载**：0你投掷出一件附近（nearby）的无主物体，用它对单个敌人做出远程攻击。"
        )
        out = promote_inline_ability_headings([line])
        assert out
        assert out[0] == "### 念动（Telekinetic Blast）元素", out[0]

    def test_archetype_inline_line_not_over_split(self):
        """变体页单行长行（**变体名【】**+intro+**中文能力名：**body...）不误拆。

        仁义剑客页整行 = 变体名（Virtuous Bravo）【圣武士】 + 斜体 intro +
        「武器和护甲擅长」等中文能力名。该能力名无英文括号/Ex/Su/Sp 信号，但其后
        正文含 `(Bravo's Finesse，EX)` 英文括号——若按 combined（cand+rest）判定
        会误把「武器和护甲擅长」提为标题、变体名整块降为 lead，最终该能力名标签
        在 merge 时被空标题吞掉丢失。cand 无信号则应保持旧行为（标题含变体名，
        能力名留在正文）。
        """
        line = (
            "**仁义剑客(Virtuous Bravo)【圣武士】***有别于其他依赖力量和坚甲的"
            "圣武士同僚，仁义剑客凭藉着自身的才智以及优雅引领着正义和希望的光辉。*"
            "**武器和护甲擅长：**仁义剑客并不擅长重甲以及除小圆盾外的所有盾牌，"
            "这项能力调整了圣武士的护甲擅长**义剑巧技(Bravo's Finesse，EX)：**"
            "仁义剑客在使用轻型或单手穿刺类近战武器时使用敏捷修正取代力量修正进行攻击检定。"
        )
        out = promote_inline_ability_headings([line])
        assert out, "应识别出标题"
        assert not out[0].startswith("### 武器和护甲擅长"), out[0]
        assert "仁义剑客" in out[0], "变体名应留在标题"
        assert any("武器和护甲擅长" in l for l in out), "能力名标签不得丢失"

    def test_table_formula_continuation_not_promoted(self):
        """表格公式续行（+ 法术等级 + …**随意施展：**舞光术（dancing lights）…）不误提。

        page_796 奥秘之灯 DC 公式被 CHM 表格切出 `+ 法术等级 + 她的智力调整值。…
        随意施展：`——cand（`要使用这些法术…随意施展`）无能力信号，pm 拒绝切分；
        但 rest 含 `（dancing lights）` 英文括号，若最终判定仍走 combined 会把整段
        提成空壳标题 `### + 法术等级 + …随意施展`，正文 `舞光术/光亮术/火花术` 随块
        缩到 < MIN_CHUNK_CHARS 被丢弃（8 字符缺失）。pm 拒绝时只认标题自身信号。
        """
        line = (
            "+ 法术等级 + 她的智力调整值。要使用这些法术，她的智力属性必须至少等于"
            "10 + 类法术能力的法术等级。**随意施展：**舞光术（dancing "
            "lights），光亮术（light），火花术APG（spark）。"
        )
        out = promote_inline_ability_headings([line])
        assert out == [line], "表格公式续行不应被提为标题，应原样保留"
        assert not out[0].startswith("### +"), out[0]

    def test_archetype_inline_with_english_ability_not_stripped(self):
        """变体页单行结构 + 首个能力名带英文信号，也不应剥离。

        骑士变体页整行 = 豪勇先锋(Gallant)【骑士】+intro+「豪勇先锋之道(Code of
        Gallantry)：」——cand 自带英文括号（is_ability_heading_text 通过），但
        lead 含【骑士】变体标记，是变体名而非过渡句。剥离会把「豪勇先锋之道
        (Code of Gallantry)」提成空标题（紧随其后的变体名被 promote_inline_
        archetype_headings 提成下级标题），英文标签在 merge 时丢失。
        """
        line = (
            "**豪勇先锋(Gallant)【骑士】***豪勇先锋乃是荣誉，慷慨，以及礼仪的化身。"
            "即使出入宫廷，豪勇先锋其依然能像身处沙场一般鼓舞着身边的人。*"
            "**豪勇先锋之道(Code of Gallantry)：**豪勇先锋所宣誓的骑士团必须是"
            "以下之一：蓝玫瑰骑士团，护卫骑士团，雄狮骑士团和利剑骑士团。"
        )
        out = promote_inline_ability_headings([line])
        assert out, "应识别出标题"
        assert not out[0].startswith("### 豪勇先锋之道"), out[0]
        assert "豪勇先锋" in out[0], "变体名应留在标题"
        assert any("豪勇先锋之道" in l for l in out), "能力名标签不得丢失"


# ============================================================
#  KN222 实样集成：PoP 冬女巫 page_754
# ============================================================


class TestPage754KN222Regression:
    """修复前 page_754 产出 3 个污染 chunk 且主块 DROP；修复后找回"""

    def test_prestige_requirements_restored(self, proc):
        """冬女巫主块（先决条件+简写等级表）应被保留。

        主块 title 为「冬女巫（Winter Witch）」，component_type 归 class_feature
        是进阶职业页的既有归类（含英文括号 → looks_like_ability_title，classify_
        component 基础页特判仅对基础页生效），KN222 目标是内容找回，不限归类。
        """
        chunks = proc.process(PAGE_754)
        main = [c for c in chunks if c.title == "冬女巫（Winter Witch）"]
        assert main, "KN222：冬女巫主块被纯表格过滤器整块丢弃"
        assert any(
            "先决条件（Requirements）" in c.text for c in main
        ), "先决条件应随主块找回"
        assert any(
            "| 等级 | BAB | 强韧 | 反射 | 意志 |" in c.text for c in main
        ), "简写等级表应随主块保留"

    def test_feature_title_not_polluted(self, proc):
        """武器与护甲擅长标题不应含过渡句前缀"""
        chunks = proc.process(PAGE_754)
        titles = [c.title for c in chunks]
        assert any(
            t.startswith("武器与护甲擅长（Weapon and Armor Proficiency）") for t in titles
        ), "应产出武器与护甲擅长能力块"
        assert not any("后述内容为" in t for t in titles), "过渡句不应进入任何标题"
