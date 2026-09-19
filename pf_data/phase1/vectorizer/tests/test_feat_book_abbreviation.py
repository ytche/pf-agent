"""
test_feat_book_abbreviation.py — D1 专长 book 中文→ASCII 缩写修复测试

覆盖（方案验收标准 2/3/5）：
  - abbr_candidates 映射表单测：18 条逐一断言可加载、abbr 为 {2,10} ASCII、
    cn/en 非空、key 无 ASCII 尾部（= 通道 1 无 ASCII 尾部的形态才会查表）
  - 通道 1 归一：箭头段无 ASCII → 查表返回规范值；有 ASCII 尾部不动；
    查表未命中保留原文
  - ApplyChmTocMapping.MAPPING 全条目 abbr ASCII 化（D1 无中文回退）
  - ApplyFeatCreationSourcePromote：CRB 造物 7 标题补源 + 出处行未识别回退
  - 产物级 negative test（修复样例 chunk_id book 非中文）在 verify 阶段覆盖：
    verify_feats.check_d1_negative_samples（四步链第 3 步，pipeline 之后执行），
    样例清单与 _D1_FIXED_SAMPLE_CHUNK_IDS 同源。此处不留产物级 pytest——
    链第 1 步（pytest）先于第 2 步（pipeline 重生成），产物级断言放 pytest
    会对旧产物永远失败（bootstrap 悖论）。
"""

import re

import pytest

from vectorizer.postprocess.feat_chain import (
    ApplyChmTocMapping,
    ApplyFeatCreationSourcePromote,
)
from vectorizer.processors.feat import (
    _feat_source_from_content,
    FEAT_ABBR_CANDIDATES,
)

_RE_ASCII = re.compile(r"^[A-Za-z0-9&/]{2,10}$")
_RE_ASCII_TAIL = re.compile(r"[A-Za-z0-9&]+$")


def _has_chinese(s: str) -> bool:
    return any("一" <= c <= "鿿" for c in (s or ""))


# ============================================================
#  abbr_candidates 映射表单测（18 条逐一）
# ============================================================


class TestAbbrCandidates:
    def test_count(self):
        # D1 实测：扫描集内通道 1 可产出的中文箭头段共 18 个（2026-09-18 枚举）
        assert len(FEAT_ABBR_CANDIDATES) == 18

    def test_each_entry_valid(self):
        for key, entry in FEAT_ABBR_CANDIDATES.items():
            assert _has_chinese(key), f"key 应为中文原样值: {key!r}"
            assert not _RE_ASCII_TAIL.search(key), f"key 含 ASCII 尾部（不会走查表）: {key!r}"
            abbr = entry["abbr"]
            assert _RE_ASCII.match(abbr), f"{key} abbr 非法: {abbr!r}"
            assert entry["cn"].strip(), f"{key} cn 为空"
            assert entry["en"].strip(), f"{key} en 为空"

    @pytest.mark.parametrize("key,abbr", [
        ("秽邪勇士", "CoC"), ("平衡勇士", "CoB"), ("纯洁勇士", "CoP"),
        ("武器大师手册", "WEAPON"), ("护甲大师手册", "ARMOR"),
        ("亡灵杀手手册", "UNDEAD"), ("巨人猎手手册", "GIANT"),
        ("任务与战役", "QaC"), ("冒险者的军械库", "AA"),
        ("初探探索者协会", "PSP"), ("CaC部属与伙伴", "CaC"),
        ("格拉里昂的半身人", "HaG"), ("格拉里昂的矮人", "DoG"),
        ("格拉里昂的混种", "BoG"), ("格拉里昂的狗头人", "KoG"),
        ("格拉里昂的兽人", "OoG"), ("格拉里昂的地精", "GoG"),
        ("格拉里昂的侏儒", "GnomeG"),
    ])
    def test_expected_abbr(self, key, abbr):
        assert FEAT_ABBR_CANDIDATES[key]["abbr"] == abbr


# ============================================================
#  通道 1 归一逻辑
# ============================================================


class TestChannel1Resolution:
    def test_no_ascii_tail_looked_up(self):
        content = "> 来源：秽邪勇士（Champions of Corruption），页码见原书，未整理 → 秽邪勇士 → 专长"
        abbr, cn, en = _feat_source_from_content(content)
        assert abbr == "CoC"
        assert cn == "秽邪勇士"
        assert en == "Champions of Corruption"

    def test_arrow_key_lookup(self):
        # 箭头段 'CaC部属与伙伴' ≠ 规范中文名，key 按箭头段原样文本
        content = "> 来源：部属与伙伴（Cohorts and Companions），未整理 → CaC部属与伙伴 → 专长"
        abbr, _, _ = _feat_source_from_content(content)
        assert abbr == "CaC"

    def test_ascii_tail_untouched(self):
        # 有 ASCII 尾部时不查表（原行为保持）
        content = "> 来源：极限荒野（Ultimate Wilderness），页码见原书，未整理 → 极限荒野UW → 专长"
        abbr, _, _ = _feat_source_from_content(content)
        assert abbr == "UW"

    def test_miss_keeps_raw(self):
        content = "> 来源：某不知名书（Unknown Book），未整理 → 某不知名书 → 专长"
        abbr, cn, _ = _feat_source_from_content(content)
        assert abbr == "某不知名书"  # 查表未命中保留原文（不编造）


# ============================================================
#  MAPPING / promote 表值 ASCII 化
# ============================================================


class TestMappingAscii:
    def test_mapping_all_ascii(self):
        for doc, (abbr, cn, en) in ApplyChmTocMapping.MAPPING.items():
            assert not _has_chinese(abbr), f"MAPPING {doc} abbr 仍为中文: {abbr!r}"
            assert cn.strip() and en.strip(), f"MAPPING {doc} cn/en 为空"

    def test_promote_values_ascii(self):
        for key, (abbr, cn, en) in ApplyFeatCreationSourcePromote.SRC_KEY_TO_BOOK.items():
            assert not _has_chinese(abbr), f"promote {key} abbr 仍为中文: {abbr!r}"
            assert cn.strip() and en.strip(), f"promote {key} cn/en 为空"


class TestCreationPromoteFallback:
    PROMOTE = ApplyFeatCreationSourcePromote()

    @pytest.mark.parametrize("title", [
        "调制药剂", "制造魔法武器和防具", "制造法杖", "制造魔杖",
        "制造奇物", "锻造戒指", "抄写卷轴",
    ])
    def test_crb_craft_titles(self, title):
        # D1：列表行【CRB】标注回溯补源（空 source）
        assert self.PROMOTE.resolve_key("", title) == "CRB"

    def test_unrecognized_src_falls_back_to_title(self):
        # 锻造戒指 chunk 粘连相邻 MHH 子条目出处行 → 按条目归属归 CRB
        assert self.PROMOTE.resolve_key("Monster Hunter's Handbook pg. 24", "锻造戒指") == "CRB"

    def test_unresolved_still_none(self):
        assert self.PROMOTE.resolve_key("", "不存在的条目") is None
        assert self.PROMOTE.resolve_key("Unknown Book pg. 1", "不存在的条目") is None
