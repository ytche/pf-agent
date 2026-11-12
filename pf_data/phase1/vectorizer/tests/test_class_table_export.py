"""D3 职业成长表结构化导出测试（方案_数据侧产物增强_20260917 §D3.6/§D3 验收 10~12）。

覆盖：
1. 解析器单元级：标准施法表（环号子表头）、5 列 NPC 裸表、英文序数等级（进阶职业）、
   键冲突 variants、特殊能力括号内分隔符不切分；
2. 产物级（对 vectorizer/output/职业/class_tables.json，文件缺失时跳过）：
   schema 自描述字段、覆盖率下界、levels 连续性、BAB/豁免形态、非施法职业无 spells、
   职业键与 spell_lists.json join 成功率 ≥80%（验收标准 12）。
"""
import json
import re
import sys
from pathlib import Path

import pytest

PHASE1_ROOT = Path(__file__).resolve().parents[2]
if str(PHASE1_ROOT) not in sys.path:
    sys.path.insert(0, str(PHASE1_ROOT))

from class_table_export import (  # noqa: E402
    RE_BAB, RE_HEADER, RE_SAVE, build, class_key_of, parse_table, split_special, spell_value,
)

# 源表数据行等级格：`| N |` 或 `| Nst |`（英文序数，进阶职业表）
RE_SRC_LEVEL = re.compile(r'^\s*\|\s*(\d+)(?:st|nd|rd|th)?\s*\|', re.I)

OUT_JSON = PHASE1_ROOT / "vectorizer" / "output" / "职业" / "class_tables.json"
SPELL_LISTS_JSON = PHASE1_ROOT / "vectorizer" / "output" / "法术" / "spell_lists.json"

STANDARD_TABLE = "\n".join([
    "| 表：测试师 |",
    "| --- |",
    "| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 | 特殊能力 | 每日法术 |",
    "| 0 | 1 | 2 |",
    "| 1 | +0 | +0 | +0 | +2 | 戏法，奥术联结 | 3 | 1 | - |",
    "| 2 | +1 | +0 | +0 | +3 |  | 4 | 2 | - |",
    "| 3 | +2 | +1 | +1 | +3 | 奖励专长 | 4 | 2 | 1 |",
])

NPC_TABLE = "\n".join([
    "| 表：平民 |",
    "| --- |",
    "| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 |",
    "| 1 | +0 | +0 | +0 | +0 |",
    "| 2 | +1 | +0 | +0 | +0 |",
])

PRESTIGE_TABLE = "\n".join([
    "| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 | 特殊 | 每日法术量 |",
    "| --- | --- | --- | --- | --- | --- | --- |",
    "| 1st | +0 | +1 | +0 | +1 | 隐秘施法 | - |",
    "| 2nd | +1 | +1 | +0 | +1 | 魅惑之触 | 现有等级+1 |",
])


class TestParser:
    def test_standard_caster_table(self):
        lines = STANDARD_TABLE.split("\n")
        rec, issues, _ = parse_table(lines, 2, "cid", "doc")
        assert rec is not None and not issues, issues
        assert rec["has_spell_table"] is True
        assert rec["spell_levels"] == 3
        assert rec["spell_rings"] == [0, 1, 2]
        assert rec["max_level"] == 3
        lv1 = rec["levels"]["1"]
        assert lv1["bab"] == "+0"
        assert lv1["fort"] == "+0" and lv1["ref"] == "+0" and lv1["will"] == "+2"
        assert lv1["special"] == ["戏法", "奥术联结"]
        assert lv1["spells"] == {"0": 3, "1": 1, "2": None}
        assert rec["levels"]["3"]["spells"] == {"0": 4, "1": 2, "2": 1}

    def test_npc_bare_table_no_special_no_spells(self):
        lines = NPC_TABLE.split("\n")
        rec, issues, _ = parse_table(lines, 2, "cid", "doc")
        assert rec is not None and not issues
        assert rec["has_spell_table"] is False
        assert rec["spell_levels"] == 0
        assert rec["max_level"] == 2
        assert "special" not in rec["levels"]["1"]
        assert "spells" not in rec["levels"]["1"]

    def test_prestige_english_ordinal_levels_and_spell_note(self):
        lines = PRESTIGE_TABLE.split("\n")
        rec, issues, _ = parse_table(lines, 0, "cid", "doc")
        assert rec is not None, issues
        assert sorted(rec["levels"]) == ["1", "2"]
        assert rec["levels"]["2"]["special"] == ["魅惑之触"]
        assert rec["levels"]["2"]["spells_note"] == "现有等级+1"
        assert "spells" not in rec["levels"]["1"]  # 无环号子表头 → 无结构化法术位

    def test_bab_multi_attack_and_fold(self):
        lines = ["| 等级 | 基本攻击加值 | 强韧豁免 | 反射豁免 | 意志豁免 |",
                 "| 1 | +0 | +2 | +0 | +0 |",
                 "| 2 | +11/+6 /+1 | +7 | +3 | +3 |"]
        rec, issues, _ = parse_table(lines, 0, "cid", "doc")
        assert rec["levels"]["2"]["bab"] == "+11/+6/+1"
        assert rec["levels"]["2"]["bab_attacks"] == [11, 6, 1]

    def test_class_key_caption_and_fallback(self):
        assert class_key_of("吟游诗人", "核心职业/吟游诗人/page_39.md") == "吟游诗人"
        assert class_key_of(None, "核心职业/战士/page_48.md") == "战士"
        assert class_key_of("圣武士", "x/y/z.md") == "圣骑士"  # CLASS_ALIASES 归一
        assert class_key_of("铳士", "基础职业/铳手/page_75.md") == "铳手"  # 源表 typo 归一
        assert class_key_of("骑士", "基础职业/骑将/page_73.md") == "骑将"
        assert class_key_of(None, "page_862.md") is None

    def test_split_special_paren_aware(self):
        assert split_special("疾风连击（奖励攻击）、震慑拳") == ["疾风连击（奖励攻击）", "震慑拳"]
        assert split_special("") == []
        assert split_special("武器训练1") == ["武器训练1"]

    def test_split_special_folds_newline(self):
        """D1：格内折行合并后的特殊能力格（含 \n）先折叠空白再切分。"""
        assert split_special("毒性抗力+2，藏刃,\n毁灭刺杀") == ["毒性抗力+2", "藏刃", "毁灭刺杀"]

    def test_spell_value_forms(self):
        assert spell_value("-") is None
        assert spell_value("") is None
        assert spell_value("3") == 3
        assert spell_value("1+1") == "1+1"  # 领域法术加成保留原文

    def test_bab_save_regex(self):
        assert RE_BAB.match("+20/+15/+10/+5")
        assert RE_BAB.match("+6/+1")
        assert not RE_BAB.match("6")
        assert RE_SAVE.match("+12")
        assert not RE_SAVE.match("+6/+1")


class TestBuildIntegration:
    """对真实产物 class_tables.json 的验收（验收标准 10~12）。文件缺失跳过。"""

    @pytest.fixture()
    def artifact(self):
        if not OUT_JSON.exists():
            pytest.skip("class_tables.json 未生成（跑 python3 class_table_export.py）")
        return json.loads(OUT_JSON.read_text(encoding="utf-8"))

    @pytest.fixture()
    def chunks_by_id(self):
        chunks_path = PHASE1_ROOT / "vectorizer" / "output" / "职业" / "chunks.jsonl"
        if not chunks_path.exists():
            pytest.skip("职业 chunks 未生成")
        return {json.loads(l)["chunk_id"]: json.loads(l)
                for l in chunks_path.read_text(encoding="utf-8").splitlines() if l.strip()}

    def test_schema_self_describing(self, artifact):
        assert artifact["version"] == "1.0"
        assert artifact["category"] == "profession"
        assert re.fullmatch(r"[0-9a-f]{64}", artifact["source_fingerprint"])
        assert artifact["generated_from"].endswith("职业/chunks.jsonl")
        cov = artifact["coverage"]
        assert set(cov["parsed"]) == set(artifact["classes"])
        for m in cov["missing"]:
            assert m["class"] and m["reason"]

    def test_parsed_count_lower_bound(self, artifact):
        assert len(artifact["classes"]) >= 15

    def test_levels_continuous_and_forms(self, artifact):
        for key, rec in artifact["classes"].items():
            seq = sorted(int(lv) for lv in rec["levels"])
            assert seq == list(range(1, rec["max_level"] + 1)), f'{key}: levels 不连续'
            for lv, e in rec["levels"].items():
                assert RE_BAB.match(e["bab"]), f'{key} L{lv} BAB {e["bab"]!r}'
                for sk in ("fort", "ref", "will"):
                    assert RE_SAVE.match(e[sk]), f'{key} L{lv} {sk} {e[sk]!r}'
                if not rec["has_spell_table"]:
                    assert "spells" not in e, f'{key} L{lv} 非施法职业有 spells'

    def test_join_with_spell_lists(self, artifact):
        """验收标准 12：职业键与 spell_lists.json classes 键 join 成功率 ≥80%。"""
        if not SPELL_LISTS_JSON.exists():
            pytest.skip("spell_lists.json 未生成")
        spell_classes = set(json.loads(
            SPELL_LISTS_JSON.read_text(encoding="utf-8"))["classes"])
        overlap = spell_classes & set(artifact["classes"])
        assert len(overlap) / len(spell_classes) >= 0.8, (
            f'join {len(overlap)}/{len(spell_classes)}')

    def test_assassin_folded_special_full_table(self, artifact):
        """D1 回归（2026-09-22）：刺客 L4 特殊能力格折行「藏刃,\\n毁灭刺杀」
        曾致解析循环静默终止、L5-L10 全丢（max_level=4）。修复后须为完整 10 级。"""
        rec = artifact["classes"]["刺客"]
        assert rec["max_level"] == 10
        assert rec["levels"]["4"]["special"] == ["毒性抗力+2", "藏刃", "毁灭刺杀"]
        assert rec["levels"]["10"]["special"] == ["毒性抗力+5", "死亡使徒"]
        assert rec["levels"]["5"]["special"] == ["偷袭+3d6", "精通直觉闪避"]

    def test_coverage_missing_is_genuine(self, artifact):
        """D2 修复后：missing 只含真正未解析职业；别名/variant 归一的进 resolved_via。"""
        cov = artifact["coverage"]
        missing_names = {m["class"] for m in cov["missing"]}
        assert not ({"召唤师(掉链子)", "骑士"} & missing_names)
        assert cov["resolved_via"]["召唤师(掉链子)"] == "召唤师"
        assert cov["resolved_via"]["骑士"] == "骑将"
        for m in cov["missing"]:
            assert "成长表解析失败" in m["reason"] or "无成长表" in m["reason"]

    def test_no_truncated_table_accepted(self, artifact, chunks_by_id):
        """棘轮（2026-09-22 QA R1 固化）：任何已解析职业（含 variants）的
        max_level 不得小于其 source chunk 成长表内的实际最大等级——断行静默
        截断（缺陷 D1）回退即失败。missing 职业不在 classes 中，天然跳过。"""
        for key, rec in artifact["classes"].items():
            for tag, r in [('primary', rec)] + [('variant', v) for v in rec.get('variants', [])]:
                text = chunks_by_id[r['source_chunk_id']]['text']
                m = RE_HEADER.search(text)
                assert m, f'{key}({tag}): source chunk 无成长表表头行？'
                src_max = 0
                for ln in text[m.end():].split('\n'):
                    lm = RE_SRC_LEVEL.match(ln)
                    if lm:
                        src_max = max(src_max, int(lm.group(1)))
                    elif ln.strip() and not ln.lstrip().startswith('|') and src_max:
                        break  # 表结束（散文/空行后的非表行）
                assert src_max == 0 or r['max_level'] >= src_max, (
                    f'{key}({tag}): 产物 max_level={r["max_level"]} < 源表 '
                    f'{src_max} 级——疑折行截断回退（D1）')

    def test_spot_values_fighter_mage_cleric(self, artifact):
        """抽查（验收 11 附加）：战士/法师/牧师核心等级数值与 chunks 原文一致。"""
        f = artifact["classes"]["战士"]
        assert f["levels"]["1"] == {"bab": "+1", "bab_attacks": [1], "fort": "+2",
                                    "ref": "+0", "will": "+0", "special": ["奖励专长"]}
        assert f["levels"]["20"]["bab"] == "+20/+15/+10/+5"
        m = artifact["classes"]["法师"]
        assert m["levels"]["1"]["spells"]["0"] == 3
        assert m["levels"]["20"]["spells"]["9"] == 4
        c = artifact["classes"]["牧师"]
        assert c["levels"]["1"]["spells"]["1"] == "1+1"
        assert c["levels"]["8"]["fort"] == "+6"


def test_build_function_smoke():
    """build() 对真实职业 chunks 全量解析冒烟：产物语义与 main() 一致。"""
    chunks_path = PHASE1_ROOT / "vectorizer" / "output" / "职业" / "chunks.jsonl"
    if not chunks_path.exists():
        pytest.skip("职业 chunks 未生成")
    chunks = [json.loads(l) for l in chunks_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    classes, coverage, report = build(chunks)
    assert len(classes) >= 15
    assert not [i for i in report["issues"] if "等级不连续" in i]
    for key, rec in classes.items():
        seq = sorted(int(lv) for lv in rec["levels"])
        assert seq == list(range(1, rec["max_level"] + 1)), key
