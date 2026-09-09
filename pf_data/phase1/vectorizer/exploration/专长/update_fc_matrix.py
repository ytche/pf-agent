#!/usr/bin/env python3
"""判别器矩阵演进重生成（v2.2 决策 F 通用化，替代 update_fc_matrix_20260802.py 一次性工具）。

背景：
  fc_deviation_matrix.json 三重身份：verify 回归基线（est↔got）、pipeline 扫描
  集合（feat.py _FEAT_MATRIX_JSON）、勘探留痕。K5 先例证明源数据修复后 est
  必须随判别器重计数演进（否则回归对账失真）——本脚本把该流程制度化：

  - 全量重计数：对矩阵每个 rel 用判别器重新计数 → est=got=判别器计数
    （替代手写 AFFECTED 列表；未变化 rel 自然保持原值，diff 为空）
  - 对账：悬空 rel（源文件缺失）报出；--scan 额外目录下判别器计数 >0 但不在
    矩阵的文件报出为候选新增（人工确认后决定是否加入矩阵）
  - 留痕：默认 dry-run 不写盘；--write 落盘后 git diff 即审计痕迹

语义：
  est = 判别器对源数据的期望专长数（K5 起统一，非勘探估计）
  got = 判别器自身口径计数（与产出对账）
  per = 各格式簇计数（短名）

用法：
  cd vectorizer/exploration/专长
  python3 update_fc_matrix.py              # dry-run 预览（只报将发生的变更）
  python3 update_fc_matrix.py --write      # 落盘
  python3 update_fc_matrix.py --write --scan <目录>...  # 候选新增对账
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fc_match  # noqa: E402

MATRIX = Path(__file__).parent / "fc_deviation_matrix.json"


def recount(matrix: list) -> list:
    """全量重计数：判别器计数 → est/got/per；返回变更描述列表"""
    changes = []
    for entry in matrix:
        rel = entry["rel"]
        p = os.path.join(fc_match.SRC_ROOT, rel)
        if not os.path.exists(p):
            changes.append(f"!! 悬空（源文件缺失，建议从矩阵删除）: {rel}")
            continue
        text = open(p, newline="", encoding="utf-8").read()
        counts, _misses = fc_match.match_file(text)
        got = sum(counts.values())
        per = {k.split()[0]: v for k, v in counts.items()}
        if entry["est"] != got or entry["got"] != got:
            changes.append(
                f"更新 {rel}: est {entry['est']}→{got}, got {entry['got']}→{got}"
            )
            entry["est"] = got
            entry["got"] = got
            entry["per"] = per
    return changes


def scan_new(scan_dirs: list, by_rel: dict) -> list:
    """候选新增对账：扫描目录下判别器计数 >0 且不在矩阵的 .md 文件"""
    found = []
    for d in scan_dirs:
        for root, _, files in os.walk(d):
            for fn in sorted(files):
                if not fn.endswith(".md"):
                    continue
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, fc_match.SRC_ROOT)
                if rel in by_rel:
                    continue
                text = open(p, newline="", encoding="utf-8").read()
                counts, _ = fc_match.match_file(text)
                got = sum(counts.values())
                if got > 0:
                    found.append((rel, got))
    return found


def main() -> None:
    ap = argparse.ArgumentParser(description="判别器矩阵演进重生成（决策 F 通用化）")
    ap.add_argument("--write", action="store_true", help="落盘（默认 dry-run 预览）")
    ap.add_argument("--scan", nargs="*", default=[], help="额外扫描目录（候选新增对账）")
    args = ap.parse_args()

    matrix = json.load(open(MATRIX, encoding="utf-8"))
    by_rel = {r["rel"]: r for r in matrix}
    print(f"矩阵现状：{len(matrix)} rel")

    changes = recount(matrix)

    if args.scan:
        for rel, got in scan_new(args.scan, by_rel):
            changes.append(f"!! 候选新增（判别器计 {got}，人工确认后加入矩阵）: {rel}")

    if not changes:
        print("无变化：判别器重计数与矩阵一致（est 已全量同步，无需改动）")
    else:
        for c in changes:
            print(f"  {c}")

    if args.write:
        with open(MATRIX, "w", encoding="utf-8") as f:
            json.dump(matrix, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"✅ 已落盘：{len(matrix)} rel（git diff 即审计痕迹）")
    elif changes:
        print("（dry-run：未写盘；--write 落盘）")


if __name__ == "__main__":
    main()
