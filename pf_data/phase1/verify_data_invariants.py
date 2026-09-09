#!/usr/bin/env python3
"""verify_data_invariants.py — 类目产物数据不变量闸口（CI 用，feat 与 race 共用）

与 verify_<类目> 分工：
  - verify_<类目>：判别器回归 + 召回 + 字段健康（结构性验证）
  - 本脚本：产物质量数量护栏（不变量断言，只收窄不放宽）

阈值全部参数化（默认值 = 专长类目现值，feat 调用不变）；类目装配表
（vectorizer/cicd/verify.py CATEGORIES）按类目传参。断言均为质量下限/护栏，
不是当前快照的精确值——合理变更只会更好：
  1. 空 text chunk 数 ≤ 上限（feat：51 = KN085 28 feat_index + 23 feat_intro；
     race：0，当前无空 text 条目）
  2. text > 上限字符（默认 5000）的 chunk 数 ≤ 上限（feat：0 = KN095 护栏；
     race：3 = 聚合亚种页设计保留，KN 登记）——任何形态导致的大 chunk 超限
     都属回归
  3. chunk 总数 ≥ 下限（feat：6000；race：1800）——吞并类回归会导致总数骤降
  4. 主检索目标条目数 ≥ 下限（feat：feat ≥ 4000；race：alt_trait ≥ 300）
  5. 来源书终态（v2.2 决策 A finalize 后闸口）：
     chm_toc_path 空 = 0；book_abbreviation '?' ≤ 上限
     （feat：100 = page_1367 92 + 造物专长一览 8 设计保留；
      race：1450 = 42 文件无条目级来源标记设计保留：常见种族 15 + 罕见种族 13
      + 种族概述 1 + 核心种族 3 + 年龄身高体重 1 + 怪物种族 6 + 其他种族 3，
      源数据无「出自《X pg. N」标记，单书标注不可行，检索端走 chm_toc_path 回源）
     ——⚠️ 前置条件：产物必须经过 finalize（pipeline --category X 已内建），
     裸 pipeline 产出不满足终态

用法：
  python3 verify_data_invariants.py [--chunks ...] [--max-empty N] ...
  python3 verify_data_invariants.py --chunks vectorizer/output/种族/chunks.jsonl \
      --max-empty 0 --max-oversize 3 --min-total 1800 --main-component alt_trait \
      --min-main-count 300 --max-book-unknown 1300
退出码：0 = 全部通过；1 = 有不变量违反
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", default="vectorizer/output/专长/chunks.jsonl")
    parser.add_argument("--max-empty", type=int, default=51, help="空 text 上限（feat KN085 口径 51）")
    parser.add_argument("--oversize-limit", type=int, default=5000, help="超大 chunk 判定长度")
    parser.add_argument("--max-oversize", type=int, default=0, help="超大 chunk 上限（feat KN095 = 0）")
    parser.add_argument("--min-total", type=int, default=6000, help="chunk 总数下限")
    parser.add_argument("--main-component", default="feat", help="主检索目标 component_type")
    parser.add_argument("--min-main-count", type=int, default=4000, help="主检索目标条目下限")
    parser.add_argument("--max-book-unknown", type=int, default=100, help="book '?' 上限（来源书终态）")
    # 各类目取值见 cicd/verify.py 装配表（参数变更即登记 KN，KN106 口径）
    parser.add_argument("--max-toc-empty", type=int, default=0, help="chm_toc_path 空上限")
    args = parser.parse_args()

    path = Path(args.chunks)
    if not path.exists():
        print(f"❌ chunks 文件不存在: {path}")
        return 1

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    total = len(rows)
    ct = Counter(r["component_type"] for r in rows)
    empty = [r for r in rows if not r.get("text", "").strip()]
    oversize = [r for r in rows if len(r.get("text", "")) > args.oversize_limit]
    book_unknown = [r for r in rows if r.get("book_abbreviation", "") == "?"]
    toc_empty = [r for r in rows if not r.get("chm_toc_path", "").strip()]

    print(f"chunk 总数: {total} | 构成: {dict(ct)}")
    print(f"空 text: {len(empty)}（上限 {args.max_empty}）| "
          f">{args.oversize_limit} 字符: {len(oversize)}（上限 {args.max_oversize}）")

    # book '?' 余量：上限 0 时跳过百分比，避免除零
    book_unknown_count = len(book_unknown)
    book_margin = args.max_book_unknown - book_unknown_count
    if args.max_book_unknown > 0:
        book_margin_pct = book_margin / args.max_book_unknown * 100
        book_margin_str = f"余量 {book_margin} / {book_margin_pct:.1f}%"
        if book_margin_pct < 10:
            print(f"⚠️  WARN: book '?' 余量 {book_margin_pct:.1f}% < 10%，"
                  f"下一任务开工前须登记参数审议（沉淀#10）")
    else:
        book_margin_str = "余量 N/A（上限 0）"
    print(f"book '?': {book_unknown_count}（上限 {args.max_book_unknown}，{book_margin_str}）| "
          f"toc 空: {len(toc_empty)}（上限 {args.max_toc_empty}）")

    failures = []
    if len(empty) > args.max_empty:
        failures.append(f"空 text {len(empty)} > 上限 {args.max_empty}（空 text 口径回归）")
    if len(oversize) > args.max_oversize:
        failures.append(f"{len(oversize)} 个 chunk 超过 {args.oversize_limit} 字符"
                        f"（上限 {args.max_oversize}，超大 chunk 护栏违反）: "
                        + ", ".join(f"{r['doc_id']}|{r['title']}" for r in oversize[:5]))
    if total < args.min_total:
        failures.append(f"chunk 总数 {total} < 下限 {args.min_total}（疑似吞并回归）")
    if ct.get(args.main_component, 0) < args.min_main_count:
        failures.append(f"{args.main_component} 条目 {ct.get(args.main_component, 0)}"
                        f" < 下限 {args.min_main_count}（主检索目标骤降）")
    if len(book_unknown) > args.max_book_unknown:
        failures.append(f"book '?' {len(book_unknown)} > 上限 {args.max_book_unknown}"
                        "（来源书终态回归，"
                        + f"示例: {dict(Counter(r['doc_id'] for r in book_unknown[:5]))}）")
    if len(toc_empty) > args.max_toc_empty:
        failures.append(f"chm_toc_path 空 {len(toc_empty)} 个（上限 {args.max_toc_empty}，"
                        "回填回归）: "
                        + ", ".join(f"{r['doc_id']}|{r['title']}" for r in toc_empty[:5]))

    if failures:
        print("❌ 数据不变量违反：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("✅ 数据不变量全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
