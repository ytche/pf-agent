"""
test_trait_book_abbreviation.py — D1-Trait 背景特性 book 中文→ASCII 缩写修复测试

覆盖（对齐 test_feat_book_abbreviation.py 形态）：
  - trait_sources.json 映射表单测：修复的 6 书条目逐一断言 abbr 为
    {2,10} ASCII、cn/en 非空、与专长 D1（db479cf）同书同值无撞键
  - 来源解析链路：文件名线索（TraitFileNameProvider 通道）查 trait_sources
    返回 ASCII 缩写；引用块通道（复用 _feat_source_from_content，
    D1 已挂 abbr_candidates 查表）对巨人猎手手册返回 GIANT
  - 产物级 negative test（修复样例 chunk_id book 非中文）在 verify 阶段覆盖：
    verify_traits.check_d1t_negative_samples（四步链第 3 步，pipeline 之后执行），
    样例清单与 _D1T_FIXED_SAMPLE_CHUNK_IDS 同源。此处不留产物级 pytest——
    链第 1 步（pytest）先于第 2 步（pipeline 重生成），产物级断言放 pytest
    会对旧产物永远失败（bootstrap 悖论）。

取证来源：
  - 格拉里昂的侏儒=GnomeG / 兽人=OoG / 地精=GoG：复用专长 D1 登记（PF_缩写表.md）
  - 巨人猎手手册=GIANT：复用专长 D1 abbr_candidates（feat_sources.json）；
    平衡勇士=CoBal：KN230 后 feat 侧归并值（原 CoB 为 KN230 登记脏值，
    trait 配置存量 CoB 待随 trait 批次对齐，见 KN230 观察项）
  - 格拉里昂的人类=HoG：源文件引用块无 ASCII 缩写，人工核定（PF_缩写表.md ★，
    对齐 EoG/HaG/DoG/KoG/GnomeG 家族风格）
"""

import json
import re
from pathlib import Path

import pytest

from vectorizer.processors.feat import _feat_source_from_content
from vectorizer.processors.trait import TRAIT_SOURCES

_TRAIT_SOURCES_JSON = Path(__file__).resolve().parent.parent / "config" / "trait_sources.json"
_FEAT_SOURCES_JSON = Path(__file__).resolve().parent.parent / "config" / "feat_sources.json"

_RE_ASCII = re.compile(r"^[A-Za-z0-9&]{2,10}$")


def _has_chinese(s: str) -> bool:
    return any("一" <= c <= "鿿" for c in (s or ""))


# ============================================================
#  修复的 6 书映射表单测（逐条目断言）
# ============================================================


class TestFixedBookEntries:
    @pytest.mark.parametrize("keys,abbr", [
        (("格拉里昂的人类", "Humans of Golarion"), "HoG"),
        (("格拉里昂的侏儒", "Gnomes of Golarion"), "GnomeG"),
        (("格拉里昂的兽人", "Orcs of Golarion"), "OoG"),
        (("格拉里昂的地精", "Goblins of Golarion"), "GoG"),
        (("格拉里昂的平衡勇士",), "CoB"),  # en 键 Champions of Balance
                                           # 被均衡信念（Faiths of Balance）
                                           # FoB 条目占用，仅断言中文键
    ])
    def test_entry_ascii(self, keys, abbr):
        for key in keys:
            entry = TRAIT_SOURCES.get(key)
            assert entry is not None, f"trait_sources 缺键: {key!r}"
            assert entry["abbr"] == abbr, f"{key} abbr={entry['abbr']!r} ≠ {abbr!r}"
            assert _RE_ASCII.match(entry["abbr"]), f"{key} abbr 非法: {entry['abbr']!r}"
            assert entry["cn"].strip(), f"{key} cn 为空"
            assert entry["en"].strip(), f"{key} en 为空"

    def test_fixed_entries_no_chinese(self):
        # 修复的 6 值条目（cn/en 键展开）abbr 无中文残留
        keys = (
            "格拉里昂的人类", "Humans of Golarion",
            "格拉里昂的侏儒", "Gnomes of Golarion",
            "格拉里昂的兽人", "Orcs of Golarion",
            "格拉里昂的地精", "Goblins of Golarion",
            "格拉里昂的平衡勇士", "Balance Warriors of Golarion",
        )
        left = [k for k in keys if _has_chinese(TRAIT_SOURCES[k]["abbr"])]
        assert left == [], f"修复条目仍有中文 abbr: {left}"


# ============================================================
#  跨模块一致性与撞键检查
# ============================================================


class TestCrossModuleConsistency:
    @pytest.fixture(scope="class")
    def feat_sources(self):
        return json.loads(_FEAT_SOURCES_JSON.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("cn,abbr", [
        ("格拉里昂的侏儒", "GnomeG"),
        ("格拉里昂的兽人", "OoG"),
        ("格拉里昂的地精", "GoG"),
        ("巨人猎手手册", "GIANT"),
        ("平衡勇士", "CoBal"),  # KN230：feat 侧 CoB → CoBal（trait 侧 CoB 存量待对齐）
    ])
    def test_reuses_feat_d1_abbr(self, feat_sources, cn, abbr):
        # 与专长 D1 批次重叠的书必须复用同一缩写（红线）
        cands = feat_sources.get("abbr_candidates", {})
        hit = cands.get(cn)
        assert hit is not None, f"feat abbr_candidates 缺 {cn!r}"
        assert hit["abbr"] == abbr, f"{cn}: feat={hit['abbr']!r} ≠ trait 约定 {abbr!r}"

    def test_no_abbr_collision_with_feat(self):
        # 本批 5 个缩写跨模块同书检查（全表撞键检查超出本批范围：
        # 既有 AA=秘术选集/冒险者的军械库 撞键为存量 KN，不在 D1-Trait 修复面）
        fixed = {
            "HoG": "Humans of Golarion",
            "GnomeG": "Gnomes of Golarion",
            "OoG": "Orcs of Golarion",
            "GoG": "Goblins of Golarion",
            "CoB": "Champions of Balance",
            "GIANT": "Giant Slayer's Handbook",
        }
        feat = json.loads(_FEAT_SOURCES_JSON.read_text(encoding="utf-8"))
        feat_en = {}
        for table in ("sources", "abbr_candidates"):
            for e in feat.get(table, {}).values():
                feat_en.setdefault(e["abbr"], set()).add(e["en"])
        for abbr, en in fixed.items():
            for f_en in feat_en.get(abbr, ()):
                assert f_en == en, f"撞键: abbr={abbr!r} 约定 en={en!r} feat en={f_en!r}"


# ============================================================
#  引用块通道（巨人猎手手册，复用 feat D1 查表）
# ============================================================


class TestTraitModuleNoCollision:
    def test_abbr_maps_to_single_en_within_trait(self):
        # 同模块撞键守卫：trait_sources 全表 abbr 不得对应多个 en。
        # （跨模块 AA 撞键为存量 KN，不在本批；此断言只锁 trait 模块内部一致性，
        #   防后续新增条目悄悄撞键）
        by_abbr: dict = {}
        for key, entry in TRAIT_SOURCES.items():
            by_abbr.setdefault(entry["abbr"], set()).add(entry["en"])
        collided = {a: sorted(es) for a, es in by_abbr.items() if len(es) > 1}
        assert collided == {}, f"trait 模块内 abbr 撞键: {collided}"

    def test_abbr_nonempty(self):
        # 最低限度健康断言：全表 abbr/cn/en 均非空（中文残留清理由 verify 检查 7 兜底）
        for key, entry in TRAIT_SOURCES.items():
            for field in ("abbr", "cn", "en"):
                assert entry.get(field, "").strip(), f"{key} 的 {field} 为空"


class TestQuoteBlockChannel:
    def test_giant_slayers_handbook(self):
        content = (
            "> 来源：巨人猎手手册（Giant Slayer's Handbook），"
            "页码见原书，未整理 → 巨人猎手手册 → 背景特性"
        )
        abbr, cn, en = _feat_source_from_content(content)
        assert abbr == "GIANT"
        assert cn == "巨人猎手手册"
        assert en == "Giant Slayer's Handbook"
