#!/usr/bin/env python3
# ⚠️ SUPERSEDED（2026-09-01 · CP3）
# 本脚本逻辑已收敛进 vectorizer/verify/verify_profession.py（VerifyBase 八检查，
# cicd/verify.py profession 类目唯一验收入口）。保留仅作历史参考，不再在 cicd
# 调用；如需复跑请用 `python3 -m vectorizer.verify.verify_profession`。
"""V006: 验证新增 feature_subtype 的数量下限。

断言每个 V006 新增/已有的 subtype 至少有期望数的 chunk。
"""
import json
import sys
from pathlib import Path
from collections import Counter

CHUNKS_FILE = Path("vectorization_prep_profession/chunks.jsonl")

# (subtype, 期望最小数量, 说明)
EXPECTED_SUBTYPES = [
    # V006 新增（低风险 subtype_mapping）
    ("arcane_discovery", 0, "法师奥术发现（多在变体下，0 合理）"),
    ("exploit", 1, "奥能师奥能技艺"),
    ("arcana", 1, "魔战士奥能"),
    ("deed", 3, "铳手/游荡剑客炫技"),
    ("gun_training", 1, "铳手枪械训练"),
    ("vigilante_talent", 10, "侠客天赋"),
    ("social_talent", 10, "侠客社交天赋"),
    ("slayer_talent", 5, "杀手天赋"),
    ("investigator_talent", 5, "调查员天赋"),
    ("eidolon_subtype", 5, "召唤师幻灵亚种"),
    ("phrenic_amplification", 3, "异能者精神增幅"),
    ("emotional_focus", 0, "唤魂师情感羁绊（需 source 修复，breadcrumb 无关键词）"),
    ("subdomain", 3, "牧师子域"),
    # V006 Unchained 修复
    ("rage_power", 200, "野蛮人/歌者/血脉狂怒者狂暴之力（含 Unchained）"),
    # 已有 subtype（回归保护）
    ("hex", 30, "女巫巫术"),
    ("major_hex", 15, "女巫强力巫术"),
    ("grand_hex", 8, "女巫高等巫术"),
    ("patron", 25, "女巫庇护主"),
    ("discovery", 50, "炼金术师科研发现"),
    ("domain", 200, "牧师/德鲁伊领域"),
    ("bloodline", 30, "术士血承"),
    ("rogue_talent", 200, "盗贼天赋"),
    ("ninja_trick", 30, "忍者忍术"),
    ("arcane_school", 3, "法师奥术学派（误标已清理，实际仅 5 条）"),
    ("bardic_masterpiece", 60, "吟游诗人传世名作"),
]


def main():
    if not CHUNKS_FILE.exists():
        print(f"FAIL: {CHUNKS_FILE} 不存在")
        sys.exit(1)

    chunks = [json.loads(line) for line in CHUNKS_FILE.read_text(encoding="utf-8").splitlines()]
    subtype_counts = Counter(
        c.get("feature_subtype") for c in chunks
        if c.get("feature_subtype")
    )

    all_pass = True
    for subtype, min_count, desc in EXPECTED_SUBTYPES:
        actual = subtype_counts.get(subtype, 0)
        if actual < min_count:
            print(f"  FAIL: {subtype} ({desc}) → 实际 {actual} < {min_count}")
            all_pass = False
        else:
            print(f"  PASS: {subtype} ({desc}) → {actual} ≥ {min_count}")

    # 额外检查：列出所有发现的 subtype 做汇总
    all_found = sorted(subtype_counts.keys())
    print(f"\n  共 {len(all_found)} 个 subtype: {', '.join(all_found)}")

    if all_pass:
        print("\nALL PASSED")
        return 0
    else:
        print("\nSOME FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
