"""KN237 四个职业成长表解析补齐测试（spec 2026-11-12-kn237-class-table-parsing-design）。

覆盖：
1. 四个职业正例：BAB 简写表头（吸血鬼猎人）、单行压缩表（催眠师/异能者）、
   夹具（变形者）；产物级再核 20 级与关键数值；
2. 非缺口职业不补扫：只有 coverage.missing 的职业才从其他组件定向补扫；
3. 缺级仍 missing：压缩表等级不连续时整表拒收；
4. 夹具优先级与 coverage.overrides 独立登记（不写 coverage.resolved_via）。
"""
import json
import sys
from pathlib import Path

import pytest

PHASE1_ROOT = Path(__file__).resolve().parents[2]
if str(PHASE1_ROOT) not in sys.path:
    sys.path.insert(0, str(PHASE1_ROOT))

from class_table_export import (  # noqa: E402
    build, load_overrides, parse_compressed_table, parse_table,
)

OUT_JSON = PHASE1_ROOT / "vectorizer" / "output" / "职业" / "class_tables.json"
CHUNKS_JSONL = PHASE1_ROOT / "vectorizer" / "output" / "职业" / "chunks.jsonl"

# 吸血鬼猎人源表头形态：BAB 简写 + 「每日法术」被折行拆进各环列
VAMPIRE_HUNTER_TABLE = "\n".join([
    "| 等级 | BAB | 强韧 | 反射 | 意志 | 特殊 | 每1级 | 日2级 | 法3级 | 术4级 |",
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    "| 1级 | +1 | +0 | +2 | +2 | 侦测死灵，追踪 | — | — | — | — |",
    "| 2级 | +2 | +0 | +3 | +3 | 无情追猎 | — | — | — | — |",
    "| 3级 | +3 | +1 | +3 | +3 | 技巧专长 | — | — | — | — |",
    "| 4级 | +4 | +1 | +4 | +4 | 木桩 | 0 | — | — | — |",
    "| 5级 | +5 | +1 | +4 | +4 | 无情追猎团 | 1 | — | — | — |",
])

# 催眠师单行压缩表（表头一格串接列名 + 环号；行间无分隔符）
MESMERIST_COMPRESSED = "\n".join([
    "| 每日法术 | 等级基本攻击加值强韧豁免反射豁免意志豁免特殊1级2级3级4级5级6级 | "
    "1级+0+0+2+2精湛骗术，催眠注视1— — — — — | "
    "2级+1+0+3+3催眠师诡计2— — — — — | "
    "3级+2+1+3+3深邃注视3— — — — — | "
    "4级+3+1+4+4催眠师诡计31— — — — | "
    "5级+3+1+4+4多重诡计（2），心智潜能42— — — — |",
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
])

# 异能者单行压缩表：9 个法术环位，行尾折行把最后一格挤到下一物理行
PSYCHIC_COMPRESSED = "\n".join([
    "| 每日法术 | 等级基本攻击加值强韧豁免反射豁免意志豁免特殊1级2级3级4级5级6级7级8级9级 | "
    "1级+0+0+0+2境界之力，念力3— — — — — — — — | "
    "2级+1+0+0+3侦测思想4— — — — — — — — | "
    "3级+1+1+1+3精神增幅5— — — — — — — — | "
    "4级+2+1+1+4境界法术63— — — — — — — | "
    "5级+2+1+1+4境界之力64— — — — — — — | "
    "6级+3+2+2+5境界法术653— — — — — — |",
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
])


def chunk(chunk_id, component_type, doc_id, text):
    return {"chunk_id": chunk_id, "component_type": component_type,
            "doc_id": doc_id, "text": text}


def standard_table(max_level=3):
    lines = ["| 表：战士 |", "| --- |",
             "| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 | 特殊能力 |"]
    for lv in range(1, max_level + 1):
        lines.append(f"| {lv} | +{lv} | +{2 + lv // 2} | +0 | +0 | 专长{lv} |")
    return "\n".join(lines)


class TestFourClassesPositive:
    def test_vampire_hunter_bab_header_and_split_spell_columns(self):
        rec, issues, _ = parse_table(VAMPIRE_HUNTER_TABLE.split("\n"), 0, "c", "d")
        assert rec is not None and not issues, issues
        assert rec["has_spell_table"] is True
        assert rec["spell_rings"] == [1, 2, 3, 4]
        assert rec["levels"]["1"]["bab"] == "+1"
        assert (rec["levels"]["1"]["fort"], rec["levels"]["1"]["ref"],
                rec["levels"]["1"]["will"]) == ("+0", "+2", "+2")
        assert rec["levels"]["1"]["spells"] == {"1": None, "2": None, "3": None, "4": None}
        assert rec["levels"]["4"]["spells"] == {"1": 0, "2": None, "3": None, "4": None}
        assert rec["levels"]["5"]["spells"]["1"] == 1
        assert rec["levels"]["1"]["special"] == ["侦测死灵", "追踪"]

    def test_mesmerist_single_line_compressed_table(self):
        rec, issues = parse_compressed_table(MESMERIST_COMPRESSED, "c", "d")
        assert rec is not None, issues
        assert rec["max_level"] == 5
        assert rec["spell_rings"] == [1, 2, 3, 4, 5, 6]
        lv1 = rec["levels"]["1"]
        assert (lv1["bab"], lv1["fort"], lv1["ref"], lv1["will"]) == (
            "+0", "+0", "+2", "+2")
        assert lv1["spells"]["1"] == 1
        assert lv1["spells"]["2"] is None
        assert lv1["special"] == ["精湛骗术", "催眠注视"]
        # 特殊能力里的数字（多重诡计（2））不得被当成法术位
        assert rec["levels"]["5"]["special"] == ["多重诡计（2）", "心智潜能"]
        assert rec["levels"]["5"]["spells"] == {
            "1": 4, "2": 2, "3": None, "4": None, "5": None, "6": None}

    def test_psychic_single_line_compressed_table(self):
        rec, issues = parse_compressed_table(PSYCHIC_COMPRESSED, "c", "d")
        assert rec is not None, issues
        assert rec["spell_levels"] == 9
        assert rec["levels"]["1"]["spells"] == {
            "1": 3, **{str(r): None for r in range(2, 10)}}
        assert rec["levels"]["4"]["spells"]["1"] == 6
        assert rec["levels"]["4"]["spells"]["2"] == 3
        assert rec["levels"]["6"]["spells"]["1"] == 6
        assert rec["levels"]["6"]["spells"]["3"] == 3

    def test_shifter_override_fixture_record(self):
        overrides = load_overrides()
        item = overrides["变形者"]
        assert item["source_doc_id"].endswith("变形者/page_1201.md")
        assert item["source_chunk_id"]
        assert item["source_html"].endswith("page_1201.html")
        assert item["max_level"] == 20
        assert item["has_spell_table"] is False
        assert len(item["levels"]) == 20
        assert item["levels"]["20"]["bab"] == "+20/+15/+10/+5"
        assert item["levels"]["20"]["fort"] == "+12"
        assert item["levels"]["20"]["will"] == "+6"
        assert item["levels"]["20"]["special"] == ["防御本能（+5）", "终极拟态"]


class TestTargetedSupplement:
    def test_supplement_only_for_missing_class(self):
        target_doc = "其他职业/测试猎人/page_1.md"
        chunks = [
            chunk("o1", "class_overview", target_doc, "表：测试猎人\n无成长表正文。"),
            chunk("f1", "class_feature", target_doc, "表1-1：测试猎人\n" + standard_table()),
        ]
        classes, coverage, report = build(chunks, overrides={})
        assert classes["测试猎人"]["max_level"] == 3
        assert [s["role"] for s in report["tables"]["测试猎人"]["sources"]] == ["supplement"]
        assert coverage["stats"]["supplemented"] == 1
        assert coverage["stats"]["table_chunks_hit"] == 1

    def test_non_missing_class_not_supplemented(self):
        doc = "核心职业/战士/page_1.md"
        chunks = [
            chunk("o1", "class_overview", doc, standard_table(max_level=3)),
            chunk("f1", "class_feature", doc,
                  "| 等级 | 基本攻击加值 | 强韧 | 反射 | 意志 |\n"
                  "| 1 | +1 | +2 | +0 | +0 |\n| 2 | +2 | +3 | +0 | +0 |"),
        ]
        classes, coverage, report = build(chunks, overrides={})
        assert classes["战士"]["max_level"] == 3
        assert all(s["role"] != "supplement"
                   for s in report["tables"]["战士"]["sources"]), "非缺口职业不应被补扫"


class TestGapStillMissing:
    def test_compressed_table_missing_level_rejected(self):
        doc = "异能冒险（Occult Adventures）/催眠师/page_9.md"
        text = ("| 每日法术 | 等级基本攻击加值强韧豁免反射豁免意志豁免特殊1级2级 | "
                "1级+0+0+2+2诡计1— | 2级+1+0+3+3诡计2— | 4级+3+1+4+4诡计31 |\n"
                "| --- | --- | --- |")
        rec, issues = parse_compressed_table(text, "c", doc)
        assert rec is None
        assert any("等级不连续" in i for i in issues), issues
        classes, coverage, _ = build(
            [chunk("o1", "class_overview", doc, text)], overrides={})
        assert "催眠师" not in classes
        missing = {m["class"]: m["reason"] for m in coverage["missing"]}
        assert "催眠师" in missing
        assert "解析失败" in missing["催眠师"]

    def test_override_with_level_gap_stays_missing(self):
        doc = "极限荒野（Ultimate Wilderness）/变形者/page_9.md"
        bad = {"变形者": {
            "class": "变形者", "source_chunk_id": "c", "source_doc_id": doc,
            "source_html": "x.html", "extracted_at": "2026-11-12",
            "max_level": 3, "has_spell_table": False, "spell_levels": 0,
            "levels": {"1": {"bab": "+1", "fort": "+2", "ref": "+2", "will": "+0"},
                       "3": {"bab": "+3", "fort": "+3", "ref": "+3", "will": "+1"}},
        }}
        _, coverage, report = build([], overrides=bad)
        assert "变形者" in {m["class"] for m in coverage["missing"]}
        assert coverage["overrides"] == {}
        assert any("夹具 变形者" in i for i in report["issues"])


class TestCompressedBoundaries:
    """评审 r1 p2-1：region 截断必须真生效；重复等级不得静默覆盖。"""

    TRAILING = "\n".join([
        "| 每日法术 | 等级基本攻击加值强韧豁免反射豁免意志豁免特殊1级2级 | "
        "1级+0+0+2+2诡计1— | 2级+1+0+3+3诡计2— |",
        "| --- | --- |",
        "职业能力后述内容为测试职业的职业能力。",
        "| 每日法术 | 等级基本攻击加值强韧豁免反射豁免意志豁免特殊1级2级 | "
        "1级+9+9+9+9第二张表9— | 2级+8+8+8+8第二张表8— |",
        "| --- | --- |",
    ])

    def test_region_truncated_before_trailing_text_and_second_table(self):
        rec, issues = parse_compressed_table(self.TRAILING, "c", "d")
        assert rec is not None, issues
        assert rec["max_level"] == 2
        assert rec["levels"]["1"]["bab"] == "+0"
        assert rec["levels"]["1"]["special"] == ["诡计"]
        assert rec["levels"]["2"]["bab"] == "+1"
        # 表后正文与第二张表不得被吸收成数据行，也不得触发重复等级
        assert not any("重复行" in i for i in issues), issues
        assert rec["levels"]["2"]["special"] == ["诡计"]

    def test_duplicate_levels_reported_not_silent(self):
        text = ("| 每日法术 | 等级基本攻击加值强韧豁免反射豁免意志豁免特殊1级2级 | "
                "1级+0+0+2+2诡计1— | 2级+1+0+3+3诡计2— | "
                "1级+5+5+5+5重复5— | 2级+6+6+6+6重复6— |")
        rec, issues = parse_compressed_table(text, "c", "d")
        assert rec is not None
        assert any("等级 1 重复行" in i for i in issues), issues
        assert any("等级 2 重复行" in i for i in issues), issues
        assert rec["levels"]["1"]["bab"] == "+5"  # 与标准通道同口径：后行覆盖且留痕

    def test_table_chunks_hit_counts_record_docs_only(self):
        chunks = [
            chunk("o1", "class_overview", "核心职业/战士/page_1.md", standard_table(3)),
            chunk("o2", "class_overview", "核心职业/法师/page_1.md", "只有正文，没有成长表。"),
        ]
        classes, coverage, _ = build(chunks, overrides={})
        assert classes["战士"]["max_level"] == 3
        assert coverage["stats"]["table_chunks_hit"] == 1


class TestOverridePriority:
    def test_override_wins_and_is_recorded_separately(self):
        doc = "极限荒野（Ultimate Wilderness）/变形者/page_1.md"
        good = {"变形者": {
            "class": "变形者", "source_chunk_id": "fix", "source_doc_id": doc,
            "source_html": "page_1201.html", "extracted_at": "2026-11-12",
            "max_level": 2, "has_spell_table": False, "spell_levels": 0,
            "levels": {"1": {"bab": "+1", "fort": "+2", "ref": "+2", "will": "+0"},
                       "2": {"bab": "+2", "fort": "+3", "ref": "+3", "will": "+0"}},
        }}
        classes, coverage, _ = build(
            [chunk("o1", "class_overview", doc, standard_table(max_level=2))],
            overrides=good)
        assert classes["变形者"]["source_chunk_id"] == "fix"
        assert classes["变形者"]["variants"][0]["source_chunk_id"] == "o1"
        assert coverage["overrides"]["变形者"]["source_html"] == "page_1201.html"
        assert "变形者" not in coverage["resolved_via"]
        assert "变形者" not in {m["class"] for m in coverage["missing"]}




class TestArtifactKN237:
    @pytest.fixture()
    def artifact(self):
        if not OUT_JSON.exists():
            pytest.skip("class_tables.json 未生成（跑 python3 class_table_export.py）")
        return json.loads(OUT_JSON.read_text(encoding="utf-8"))

    def test_coverage_64_to_68_and_missing_cleared(self, artifact):
        cov = artifact["coverage"]
        assert len(cov["parsed"]) == len(artifact["classes"]) == 68
        assert cov["missing"] == []
        assert set(cov["overrides"]) == {"变形者"}
        assert "变形者" not in cov["resolved_via"]

    @pytest.mark.parametrize("name", ["催眠师", "吸血鬼猎人", "异能者", "变形者"])
    def test_four_classes_twenty_levels(self, artifact, name):
        rec = artifact["classes"][name]
        assert rec["max_level"] == 20
        assert sorted(int(lv) for lv in rec["levels"]) == list(range(1, 21))
        for lv in rec["levels"].values():
            assert lv["bab"].startswith("+")
            assert all(lv[k].startswith("+") for k in ("fort", "ref", "will"))

    def test_spot_values(self, artifact):
        c = artifact["classes"]
        assert c["催眠师"]["levels"]["1"]["spells"]["1"] == 1
        assert c["催眠师"]["levels"]["16"]["spells"]["6"] == 1
        assert c["吸血鬼猎人"]["levels"]["4"]["spells"]["1"] == 0
        assert c["吸血鬼猎人"]["levels"]["20"]["spells"] == {
            "1": 4, "2": 4, "3": 3, "4": 3}
        assert c["异能者"]["levels"]["1"]["spells"]["1"] == 3
        assert c["异能者"]["levels"]["20"]["bab"] == "+10/+5"
        assert c["变形者"]["levels"]["20"]["special"] == ["防御本能（+5）", "终极拟态"]
        assert c["变形者"]["levels"]["20"]["bab"] == "+20/+15/+10/+5"

    def test_build_matches_artifact(self):
        if not CHUNKS_JSONL.exists():
            pytest.skip("职业 chunks 未生成")
        chunks = [json.loads(l) for l in
                  CHUNKS_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
        classes, coverage, report = build(chunks)
        assert len(classes) == 68
        assert coverage["missing"] == []
        assert coverage["overrides"]["变形者"]["source_doc_id"].endswith("page_1201.md")
        assert "吸血鬼猎人" in {s["class"] for s in report["supplements"]}
