#!/usr/bin/env python3
"""合并 17 个 per_file_BNN.jsonl → 专长_per_file.jsonl + 汇总统计"""
import json, os, sys
from collections import Counter
from pathlib import Path

DIR = Path(__file__).resolve().parent
PATTERN = "per_file_B{:02d}.jsonl"

def main():
    records = []
    missing = []
    for i in range(1, 18):
        fp = DIR / PATTERN.format(i)
        if not fp.exists():
            missing.append(f"B{i:02d}")
            continue
        with open(fp, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"ERROR: {fp.name} JSON 解析失败: {e}", file=sys.stderr)
                    sys.exit(1)
                records.append(rec)

    if missing:
        print(f"WARNING: 缺失批次: {', '.join(missing)}", file=sys.stderr)
        print(f"已合并 {len(records)} 条记录", file=sys.stderr)
    else:
        print(f"17 批全部齐全，共 {len(records)} 条记录")

    # 去重检查
    files_seen = set()
    dupes = []
    for r in records:
        if r['file'] in files_seen:
            dupes.append(r['file'])
        files_seen.add(r['file'])
    if dupes:
        print(f"WARNING: 重复文件: {dupes}", file=sys.stderr)

    # 排序：按 batch 再按 file
    records.sort(key=lambda r: (r.get('batch', 'Z99'), r['file']))

    # 写入合并文件
    merged_path = DIR / "专长_per_file.jsonl"
    with open(merged_path, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f"合并输出: {merged_path} ({len(records)} 行)")

    # 统计
    doc_roles = Counter(r.get('doc_role', 'UNKNOWN') for r in records)
    total_entries = sum(r.get('estimated_count', 0) for r in records)
    trap_all = Counter()
    for r in records:
        for t in r.get('traps', []):
            trap_all[t.get('kind', 'UNKNOWN')] += 1

    print(f"\n=== 汇总统计 ===")
    print(f"文件数: {len(records)}")
    print(f"条目合计 (estimated_count): {total_entries}")
    print(f"\ndoc_role 分布:")
    for role, cnt in doc_roles.most_common():
        print(f"  {role}: {cnt}")
    print(f"\n陷阱类型频次:")
    for kind, cnt in trap_all.most_common():
        print(f"  {kind}: {cnt}")

    # 与 audit_baseline 对照
    audit_path = DIR / "audit_baseline.jsonl"
    if audit_path.exists():
        with open(audit_path, encoding='utf-8') as f:
            audit_count = sum(1 for _ in f)
        print(f"\naudit_baseline.jsonl 专长数: {audit_count}")
        print(f"勘探条目合计 vs audit: {total_entries} vs {audit_count} (差值 {total_entries - audit_count})")

if __name__ == '__main__':
    main()
