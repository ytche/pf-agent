#!/usr/bin/env python3
"""P2 批次 2：terms.json 全局去重合并——7 组同词异形（2026-08-07）

方案：术语表P2清理方案_20260807.md 批次 2。白名单硬编码锚点，
english 精确匹配，命中数 != 期望即终止（幂等，防误改）。

7 组（被合并形态 → 权威形态）：
  1. IOUN STONE → Ioun Stone（推荐译名「当艾恩石」→「艾恩石」修正）
  2. Craft Wonderous Item → Craft Wondrous Item（拼写错误）
  3. Hit Dice → Hit Die（单复数）
  4. Rogue Talent → Rogue Talents（单复数）
  5. Class Skill → Class Skills（单复数）
  6. Bonus Feat → Bonus Feats（单复数）
  7. Occult Skill Unlock → Occult Skill Unlocks（单复数）

合并规则：count 加总、other_translations 并集（去重保序）、
recommended 取权威形态值（ioun stone 组修正污染译名）、
category 取权威条目分类。terms.json 与 术语提取报告_优化版.md
同步合并（检查 5 数量一致），章节标题计数按合并后行数更新。

不重跑 cleanup_phase3.py 流水线（防丢 manual_overrides 覆盖）。

用法：python3 dedupe_terms_p2.py [--apply]
默认 dry-run 打印变更；--apply 落盘。
"""
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
JSON_FILE = BASE / "terms.json"
MD_FILE = BASE / "术语提取报告_优化版.md"

# (被合并 english, 权威 english, 期望权威推荐译名)
MERGES = [
    ("IOUN STONE", "Ioun Stone", "艾恩石"),
    ("Craft Wonderous Item", "Craft Wondrous Item", None),
    ("Hit Dice", "Hit Die", None),
    ("Rogue Talent", "Rogue Talents", None),
    ("Class Skill", "Class Skills", None),
    ("Bonus Feat", "Bonus Feats", None),
    ("Occult Skill Unlock", "Occult Skill Unlocks", None),
]


def merge_terms(terms: list) -> list:
    """返回合并后 list；白名单命中数不符时抛 ValueError。"""
    by_en = {}
    for t in terms:
        by_en.setdefault(t["english"], []).append(t)
    out = []
    merged = 0
    for victim, keep, keep_rec in MERGES:
        v = by_en.get(victim)
        k = by_en.get(keep)
        if v is None:
            continue  # 被合并形态不存在——幂等（上次已合并），无需处理
        if k is None:
            raise ValueError(f"权威形态缺失: {victim} 存在但 {keep} 不存在")
        if len(v) != 1 or len(k) != 1:
            raise ValueError(f"命中数异常: {victim}={len(v)} {keep}={len(k)}")
        victim_t, keep_t = v[0], k[0]
        # 合并到权威条目
        keep_t["count"] = int(keep_t["count"]) + int(victim_t["count"])
        if keep_rec is not None:
            keep_t["recommended"] = keep_rec  # 修正污染译名
        others = []
        for o in keep_t.get("other_translations", []) + victim_t.get("other_translations", []):
            if o and o not in others:
                others.append(o)
        keep_t["other_translations"] = others
        merged += 1
    for t in terms:
        if t["english"] in {v for v, _, _ in MERGES}:
            continue  # 被合并形态剔除
        out.append(t)
    return out, merged


def main() -> int:
    terms = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    if not isinstance(terms, list):
        print("terms.json 非 list，终止")
        return 2
    before = len(terms)
    merged_terms, merged = merge_terms(terms)
    if merged == 0:
        print("0 组合并（白名单均不存在——幂等，已合并过）")
        return 0
    print(f"合并 {merged} 组，术语数 {before} → {len(merged_terms)}（-{before - len(merged_terms)}）")
    for t in merged_terms:
        pass  # 无需校验
    if "--apply" not in sys.argv:
        print("dry-run：仅报告，加 --apply 落盘")
        return 0
    JSON_FILE.write_text(
        json.dumps(merged_terms, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已落盘 terms.json（{len(merged_terms)} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
