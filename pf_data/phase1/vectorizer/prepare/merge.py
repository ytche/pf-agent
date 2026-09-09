"""merge.py — Prepare 分批勘探报告合并（类目无关公共骨架）

源自 vectorizer/exploration/专长/merge_batches.py（专长专属，已冻结）。
按类目 prepare_batches.json 的批数合并 per_file_B{NN}.jsonl → <类目>_per_file.jsonl，
去重检查 + 汇总统计。类目无关，纯机械合并。

用法：python3 -m vectorizer.prepare.merge --category race
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

EXPLORATION = Path(__file__).resolve().parent.parent / "exploration"


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Prepare 分批勘探报告合并")
    parser.add_argument("--category", required=True, help="类目（feat/race…）")
    args = parser.parse_args(argv)

    out_dir = EXPLORATION / args.category
    manifest_path = out_dir / "prepare_batches.json"
    if not manifest_path.exists():
        sys.exit(f"❌ 缺失批次清单 {manifest_path}（先跑 vectorizer.prepare.scan 或手工生成）")
    with open(manifest_path, encoding="utf-8") as f:
        batches = json.load(f)
    n_batches = len(batches)

    records, missing = [], []

    def batch_label(b):
        """int 批次（专长/种族 01~17）→ 'B01'；字符串批次（技能 A1/A2/B1/B2）原样"""
        return b["batch"] if isinstance(b["batch"], str) else f"B{b['batch']:02d}"

    for b in batches:
        label = batch_label(b)
        fp = out_dir / f"per_file_{label}.jsonl"
        if not fp.exists():
            missing.append(label)
            continue
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    sys.exit(f"ERROR: {fp.name} JSON 解析失败: {e}")
                records.append(rec)

    if missing:
        print(f"WARNING: 缺失批次: {', '.join(missing)}", file=sys.stderr)
    print(f"{n_batches} 批，共 {len(records)} 条记录" + ("（有缺失）" if missing else "（全部齐全）"))

    # 去重检查
    files_seen, dupes = set(), []
    for r in records:
        if r["file"] in files_seen:
            dupes.append(r["file"])
        files_seen.add(r["file"])
    if dupes:
        print(f"WARNING: {len(dupes)} 个重复文件: {dupes[:5]}", file=sys.stderr)

    # 汇总统计
    total_est = sum(r.get("estimated_count", 0) for r in records)
    roles = Counter(r.get("doc_role", "?") for r in records)
    print(f"预估条目合计: {total_est}")
    print("doc_role 分布:", dict(roles))

    out = out_dir / f"{args.category}_per_file.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
