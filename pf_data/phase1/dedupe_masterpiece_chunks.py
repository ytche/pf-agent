#!/usr/bin/env python3
"""V004: 传世名作 chunk 去重。

按 (class_name, title_first_segment, feature_subtype) 分组：
  - 每组保留字符数最多（即内容最完整）的 chunk
  - 同组其他 chunk 标记 is_deprecated=True
  - 保留所有来源以供追溯

幂等：可重复运行（第二次无变化）。
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

CHUNKS_PATH = Path("vectorization_prep_profession/chunks.jsonl")
BACKUP_PATH = Path("vectorization_prep_chunks.jsonl.bak")


def main() -> int:
    if not CHUNKS_PATH.exists():
        print(f"ERROR: {CHUNKS_PATH} not found")
        return 1

    # 备份
    if not BACKUP_PATH.exists():
        BACKUP_PATH.write_bytes(CHUNKS_PATH.read_bytes())
        print(f"Backup: {BACKUP_PATH}")

    chunks = [json.loads(line) for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"Total chunks: {len(chunks)}")

    # 按 (class_name, title_first_seg, feature_subtype) 分组
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, c in enumerate(chunks):
        cn = c.get("class_name", "")
        title = c.get("title", "")
        fs = c.get("feature_subtype", "")
        if not cn or not title or not fs:
            continue
        # 用 title 的前 N 个中文字符作 key（避免 "万物之心" vs "万物之心（变体）" 等误合并）
        cn_first = title.split("（")[0].split("(")[0].strip()
        if not cn_first:
            continue
        groups[(cn, cn_first, fs)].append(i)

    # 同组去重
    deprecated_count = 0
    dedupe_groups = 0
    for (cn, first_seg, fs), indices in groups.items():
        if len(indices) <= 1:
            continue
        dedupe_groups += 1
        # 保留字符数最多的 chunk（跳过已 deprecated 的）
        candidates = [(i, chunks[i].get("char_count", 0)) for i in indices if not chunks[i].get("is_deprecated", False)]
        if len(candidates) <= 1:
            continue
        # 按字符数排序，取最大
        candidates.sort(key=lambda x: -x[1])
        keep_i = candidates[0][0]
        for i, _ in candidates[1:]:
            chunks[i]["is_deprecated"] = True
            deprecated_count += 1

    print(f"Dedupe groups: {dedupe_groups}")
    print(f"Deprecated chunks: {deprecated_count}")

    # 写回
    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"Written: {CHUNKS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())