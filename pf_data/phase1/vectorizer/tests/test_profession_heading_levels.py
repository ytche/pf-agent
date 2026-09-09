"""test_profession_heading_levels.py — page_55 圣律沿循者 heading 层级回归

verify_heading_levels.py 的 pytest fixture 化收敛（CP3，清洗层行为回归，不读
产物）。意图：page_55.md 圣律沿循者（Oathbound Paladin）段下大量 `### / ####`
嵌套标题不应被 `_fix_paladin_page_55` 步骤 2 误降级为顶层变体——若降级，下挂
子能力会被误识别为独立 class_archetype（历史 Bug）。

老脚本直接调 PaladinProcessor.clean() 数 raw heading 层级；本单测改为对
ProfessionProcessor.process(PAGE_55) 的块化产物断言（块化即清洗链终端形态，
等价于「标题层级不被破坏」）：
- 圣律沿循者 正确为 class_archetype（唯一顶层）
- 10 个子誓约全部为 class_feature，不成为独立 class_archetype
- 关键 L3 能力标题（神祇/行为准则/圣律法术）独立成块
- L4 子能力内容（纯净灵光等）并入父块 text，不丢失
"""
from pathlib import Path

import pytest

from vectorizer.processors.profession import ProfessionProcessor

# vectorizer/tests/ 的祖父目录 = pf_data/phase1
PHASE1 = Path(__file__).resolve().parents[2]
INPUT_DIR = PHASE1 / "pf_rules_md_organized" / "职业"
PAGE_55 = INPUT_DIR / "核心职业" / "圣骑士" / "page_55.md"

# 圣律沿循者 section 下的 10 个子誓约（源数据 `###` 层级，不得成为顶层变体）
SUB_OATHS = [
    "反腐化誓约", "反邪魔誓约", "反野蛮誓约", "反亡灵誓约", "反邪龙誓约",
    "反混乱誓约", "仁慈誓约", "贞洁誓约", "忠诚誓约", "复仇誓约",
]
# 源数据 `###` 层级的 L3 能力标题（应独立成 class_feature 块）
L3_TITLES = ["神祇（Deity）", "行为准则（Code of Conduct）", "圣律法术（Oath Spells）"]
# 源数据 `####` 层级的 L4 子能力（反腐化誓约 下的子能力，内容并入父块 text）
L4_CONTENT = ["纯净灵光", "净化之焰", "归于虚空"]


@pytest.fixture(scope="module")
def chunks():
    """全量装配一次，跑 page_55 块化。"""
    proc = ProfessionProcessor(source_resolver=None)
    proc.load_resources(INPUT_DIR)
    return proc.process(PAGE_55)


class TestOathboundHeadingLevels:
    """圣律沿循者 section 标题层级不降级（子能力不误识别为顶层变体）"""

    def test_oathbound_is_single_archetype(self, chunks):
        """圣律沿循者 应为唯一 class_archetype（内容归属，不被拆成多个顶层变体）"""
        oathbound = [
            c for c in chunks
            if c.component_type == "class_archetype"
            and "圣律沿循者" in (c.title or "")
        ]
        assert len(oathbound) == 1, [
            c.title for c in chunks if c.component_type == "class_archetype"
        ][:5]
        assert oathbound[0].metadata.get("archetype_name") == "圣律沿循者"

    def test_sub_oaths_never_archetype(self, chunks):
        """10 个子誓约不得被识别为独立 class_archetype（L3 降级为 ## 的 Bug）"""
        arch_titles = [c.title for c in chunks if c.component_type == "class_archetype"]
        for oath in SUB_OATHS:
            assert not any(oath in (t or "") for t in arch_titles), (
                f"子誓约 {oath} 被误识别为 class_archetype："
                f"{[t for t in arch_titles if oath in (t or '')]}"
            )

    def test_sub_oaths_feature_chunks(self, chunks):
        """每个子誓约都应作为 class_feature 独立成块（内容可检索）"""
        feat_titles = [c.title for c in chunks if c.component_type == "class_feature"]
        for oath in SUB_OATHS:
            assert any(oath in (t or "") for t in feat_titles), (
                f"子誓约 {oath} 缺失 class_feature 块"
            )

    def test_level3_headings_independent(self, chunks):
        """L3 能力标题（神祇/行为准则/圣律法术）独立成块"""
        titles = {c.title for c in chunks}
        for t in L3_TITLES:
            assert t in titles, f"L3 标题 {t!r} 未独立成块"

    def test_level4_content_preserved(self, chunks):
        """L4 子能力内容保留：纯净灵光并入反腐化誓约块 text，净化之焰/归于虚空独立成块"""
        corrupt = next(
            (c for c in chunks if "反腐化誓约" in (c.title or "")), None
        )
        assert corrupt is not None, "反腐化誓约 块缺失"
        # 源数据 :518 纯净灵光内容特征（能力名在块化时被剥，内容并入父块）
        assert "对抗来自异怪生物" in corrupt.text, "纯净灵光 内容在反腐化誓约块丢失"
        titles = {c.title for c in chunks}
        for t in ("净化之焰（Cleansing Flame, Sp）", "归于虚空（Cast into the Void, Su）"):
            assert t in titles, f"L4 子能力 {t!r} 未独立成块"
