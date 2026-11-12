"""D3 成长表导出 QA 补充测试（独立测试层，针对 coder 14 条测试的覆盖盲区）。

盲区清单（审计发现）：
B1. 多攻 BAB 边界 +6/+1（coder 只测 +11/+6/+1 折行形态）；
B2. extras 附加列（徒手伤害/AC加值）与环号子表头标签格（战斗祭司「伤害骰」）；
B3. 表格跨行断裂：数据行折行（BAB 跨行 / 法术位列数不足）→ 是否静默丢数据；
B4. 等级缺失/非连续 → parse_table 应判失败而非产出畸形产物；
B5. 表头正则误命中：非成长表（专长前置表等）不应进入 iter_hit_chunks；
B6. 等级 0 行 / 20 级之外行（如 21 级）处理；
B7. 环号子表头存在但数据行法术格不足 → 缺位补 None。
"""
import json
import sys
from pathlib import Path

import pytest

PHASE1_ROOT = Path(__file__).resolve().parents[2]
if str(PHASE1_ROOT) not in sys.path:
    sys.path.insert(0, str(PHASE1_ROOT))

from class_table_export import (  # noqa: E402
    RE_HEADER, RE_BAB, build, parse_table, iter_hit_chunks,
)

MONK_TABLE = "\n".join([
    "| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 | 特殊能力 | 徒手伤害 | AC加值 |",
    "| --- |",
    "| 1 | +0 | +2 | +2 | +2 | 震慑拳 | 1d6 | +0 |",
    "| 2 | +1 | +3 | +3 | +3 | 疾风连击（奖励攻击）、轻身坠 | 1d6 | +0 |",
])

PRIEST_TABLE = "\n".join([  # 战斗祭司形态：子表头含非数字标签格「伤害骰」
    "| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 | 特殊能力 | 神圣武器 | 每日法术 |",
    "| --- |",
    "| 1 | 2 | 3 | 4 | 5 | 6 | 伤害骰 |",
    "| 1 | +0 | +2 | +0 | +2 | 祝福圣物 | 1d6 | 3 | 1 | - |",
])

GAP_TABLE = "\n".join([  # 缺第 3 级
    "| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 |",
    "| 1 | +0 | +0 | +0 | +0 |",
    "| 2 | +1 | +0 | +0 | +0 |",
    "| 4 | +3 | +1 | +1 | +1 |",
])

LV0_TABLE = "\n".join([  # 0 级行 + 21 级行
    "| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 |",
    "| 0 | +0 | +0 | +0 | +0 |",
    "| 1 | +1 | +2 | +0 | +0 |",
    "| 21 | +21/+16/+11/+6 | +12 | +12 | +12 |",
])


class TestBABBoundary:
    def test_multi_attack_exactly_plus6_plus1(self):
        lines = ["| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 |"] + [
            f"| {i} | +{i} | +{i} | +0 | +0 |" for i in range(1, 6)]
        lines[-1] = "| 5 | +5 | +4 | +1 | +1 |"
        lines.append("| 6 | +6/+1 | +5 | +2 | +2 |")
        rec, issues, _ = parse_table(lines, 0, "c", "d")
        assert rec is not None, issues
        assert rec["levels"]["6"]["bab"] == "+6/+1"
        assert rec["levels"]["6"]["bab_attacks"] == [6, 1]

    def test_bab_regex_rejects_garbage(self):
        assert not RE_BAB.match("+6 +1")
        assert not RE_BAB.match("++6")
        assert not RE_BAB.match("")


class TestExtras:
    def test_monk_extra_columns(self):
        rec, issues, _ = parse_table(MONK_TABLE.split("\n"), 0, "c", "d")
        assert rec is not None and not issues, issues
        e = rec["levels"]["2"]
        assert e["extras"] == {"徒手伤害": "1d6", "AC加值": "+0"}
        assert "疾风连击（奖励攻击）" in e["special"]
        assert "轻身坠" in e["special"]

    def test_subheader_label_cell_not_ring(self):
        rec, issues, _ = parse_table(PRIEST_TABLE.split("\n"), 0, "c", "d")
        assert rec is not None, issues
        assert rec["spell_rings"] == [1, 2, 3, 4, 5, 6]
        assert rec["levels"]["1"]["spells"] == {"1": 3, "2": 1, "3": None,
                                                "4": None, "5": None, "6": None}
        assert rec["levels"]["1"]["extras"].get("神圣武器") == "1d6"


class TestRowBreaks:
    def test_bab_folded_across_lines_merged(self):
        """D1 修复后行为：行首非 '|' 的续行并入上一逻辑行再解析——
        BAB 格内折行（「+3 |\\n/+4 |」形态）合并为 +3/+4，折行点后的等级不再丢失，
        表按完整 4 级接受。"""
        lines = ["| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 |",
                 "| 1 | +1 | +2 | +0 | +0 |",
                 "| 2 | +2 | +3 | +0 | +0 |",
                 "| 3 | +3 |",
                 "/+4 | +3 | +1 | +1 |",
                 "| 4 | +4 | +4 | +1 | +1 |"]
        rec, issues, _ = parse_table(lines, 0, "c", "d")
        assert rec is not None, issues
        assert rec["max_level"] == 4
        assert set(rec["levels"]) == {"1", "2", "3", "4"}
        assert rec["levels"]["3"]["bab"] == "+3/+4"
        assert rec["levels"]["3"]["fort"] == "+3"
        assert not any("截断" in i or "列数不足" in i for i in issues)

    def test_special_cell_fold_merged(self):
        """D1 真实命中形态（刺客 L4）：特殊能力格内折行「藏刃,\n毁灭刺杀」
        并入末格并按分隔符切分，后续等级（L5-L10）不再静默丢失。"""
        lines = ["| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 | 特殊能力 |",
                 "| 1 | +0 | +0 | +1 | +0 | 偷袭+1d6，夺命攻击 |",
                 "| 2 | +1 | +1 | +1 | +1 | 毒性抗力+1，直觉闪避 |",
                 "| 3 | +2 | +1 | +2 | +1 | 偷袭+2d6， |",
                 "| 4 | +3 | +1 | +2 | +1 | 毒性抗力+2，藏刃,",
                 "毁灭刺杀 |",
                 "| 5 | +3 | +2 | +3 | +2 | 偷袭+3d6，精通直觉闪避 |"]
        rec, issues, _ = parse_table(lines, 0, "c", "d")
        assert rec is not None, issues
        assert rec["max_level"] == 5
        assert rec["levels"]["4"]["special"] == ["毒性抗力+2", "藏刃", "毁灭刺杀"]

    def test_unmergeable_break_rejected_not_silent(self):
        """诚实兜底：疑截断（表后紧跟无法归一的短行）整表拒收并写明位置，
        严禁当完整表接受（返回 None + 截断 reason）。"""
        lines = ["| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 |",
                 "| 1 | +1 | +2 | +0 | +0 |",
                 "某不可归一的极长散文行某不可归一的极长散文行某不可归一的极长散文行"]
        rec, issues, _ = parse_table(lines, 0, "c", "d")
        # 散文行（>40 字）正常结束表：L1 完整表可接受（表在 1 级完结属合法小表）
        assert rec is not None
        assert rec["max_level"] == 1
        # 末行残缺（<5 格）→ 拒收
        lines2 = ["| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 |",
                  "| 1 | +1 | +2 | +0 | +0 |",
                  "| 2 | +2 |"]
        rec2, issues2, _ = parse_table(lines2, 0, "c", "d")
        assert rec2 is None
        assert any("截断" in i for i in issues2)

    def test_spell_cells_shorter_than_rings_padded_none(self):
        lines = ["| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 | 每日法术 |",
                 "| 0 | 1 | 2 |",
                 "| 1 | +0 | +0 | +0 | +2 | 3 |"]
        rec, issues, _ = parse_table(lines, 0, "c", "d")
        assert rec is not None
        assert rec["levels"]["1"]["spells"] == {"0": 3, "1": None, "2": None}


class TestLevelGaps:
    def test_gap_level_rejected(self):
        rec, issues, _ = parse_table(GAP_TABLE.split("\n"), 0, "c", "d")
        assert rec is None
        assert any("等级不连续" in i for i in issues)

    def test_level0_and_level21(self):
        """现状（如实记录）：0 级行使 seq 非 1 起点 → 整表判失败。
        21 级（20 级之外行）本身可解析，但若与低等级组合成非连续同样失败。"""
        rec, issues, _ = parse_table(LV0_TABLE.split("\n"), 0, "c", "d")
        assert rec is None  # 0 级行导致 [0,1,21] 不连续
        assert any("等级不连续" in i for i in issues)


class TestHeaderFalsePositive:
    def test_non_growth_table_not_matched(self):
        feat_like = "| 等级 | 专长名 | 前置 | 效果 |\n| 1 | 猛力攻击 | 力量13 | xxx |"
        assert not RE_HEADER.search(feat_like)
        ch = {"component_type": "class_overview", "text": feat_like,
              "doc_id": "x/y.md", "chunk_id": "c1"}
        assert list(iter_hit_chunks([ch])) == []

    def test_component_type_must_be_overview(self):
        growth = "| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 |\n| 1 | +1 | +2 | +0 | +0 |"
        ch = {"component_type": "class_feature", "text": growth,
              "doc_id": "x/y.md", "chunk_id": "c1"}
        assert list(iter_hit_chunks([ch])) == []


class TestArtifactExtendedQA:
    """对真实产物的扩展抽查（QA 独立样本，与 coder 抽查不重叠）。"""
    OUT = PHASE1_ROOT / "vectorizer" / "output" / "职业" / "class_tables.json"
    CHUNKS = PHASE1_ROOT / "vectorizer" / "output" / "职业" / "chunks.jsonl"

    @pytest.fixture()
    def artifact(self):
        if not self.OUT.exists():
            pytest.skip("class_tables.json 未生成")
        return json.loads(self.OUT.read_text(encoding="utf-8"))

    @pytest.fixture()
    def chunks(self):
        return {json.loads(l)["chunk_id"]: json.loads(l)
                for l in self.CHUNKS.read_text(encoding="utf-8").splitlines() if l.strip()}

    @pytest.mark.parametrize("key,lv,field,expect", [
        ("召唤师", "8", "bab", "+6/+1"),          # 多攻边界 +6/+1
        ("女巫", "18", "bab", "+9/+4"),
        ("女巫", "20", "spells", {"0": 4, "1": 4, "2": 4, "3": 4, "4": 4,
                                  "5": 4, "6": 4, "7": 4, "8": 4, "9": 4}),
        ("审判者", "15", "bab", "+11/+6/+1"),
        ("野蛮人", "18", "bab_attacks", [18, 13, 8, 3]),  # 跨行折行形态
        ("战士", "18", "bab_attacks", [18, 13, 8, 3]),
    ])
    def test_spot_values_vs_source(self, artifact, chunks, key, lv, field, expect):
        """QA 独立抽查：JSON 值须与 source_chunk 原文行一致。"""
        rec = artifact["classes"][key]
        assert rec["levels"][lv][field] == expect
        # 溯源：原文中应能找到该 BAB 串（允许折行空格形态）
        text = chunks[rec["source_chunk_id"]]["text"].replace(" ", "")
        if field != "spells":
            src_form = ("/".join(f"+{n}" for n in expect)
                        if isinstance(expect, list) else str(expect))
            assert src_form.replace(" ", "") in text

    def test_variants_have_traceable_source(self, artifact):
        for key, rec in artifact["classes"].items():
            if "variants" not in rec:
                continue
            for v in rec["variants"]:
                assert v["levels"], f"{key} variant 空 levels"
                assert v["source_doc_id"] != rec["source_doc_id"] or \
                    v["source_chunk_id"] != rec["source_chunk_id"]

    def test_missing_alias_redundancy(self):
        """D2 修复后行为：missing 只含真正未解析职业——别名归一/variant/目录归属
        已解析的（召唤师(掉链子)→召唤师 variant、骑士→骑将）须出现在
        coverage.resolved_via 而非 missing。"""
        art = json.loads(self.OUT.read_text(encoding="utf-8"))
        missing_names = {m["class"] for m in art["coverage"]["missing"]}
        resolved = art["coverage"].get("resolved_via", {})
        assert not ({"召唤师(掉链子)", "骑士"} & missing_names)
        assert resolved.get("召唤师(掉链子)") == "召唤师"
        assert resolved.get("骑士") == "骑将"


def test_build_no_level_gap_issues():
    chunks_path = PHASE1_ROOT / "vectorizer" / "output" / "职业" / "chunks.jsonl"
    if not chunks_path.exists():
        pytest.skip("职业 chunks 未生成")
    chunks = [json.loads(l) for l in chunks_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    classes, coverage, report = build(chunks)
    assert not [i for i in report["issues"] if "无法解析" in i and "等级" in i]
