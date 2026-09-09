#!/usr/bin/env python3
"""V006 C2: 通用去重脚本。

按 (class_name, component_type, title_prefix, text_hash) 分组，
每组保留 char_count 最大的 chunk，其余标记 is_deprecated=True。

输出直接覆盖 chunks.jsonl（备份到 .bak）。
"""
import json
import shutil
from collections import defaultdict
from pathlib import Path

CHUNKS_FILE = Path("vectorization_prep_profession/chunks.jsonl")


def title_prefix(title: str, max_chars: int = 30) -> str:
    """取标题前 max_chars 个字符作为去重键（去除首尾空格）。"""
    return title.strip()[:max_chars]


def main():
    if not CHUNKS_FILE.exists():
        print(f"FAIL: {CHUNKS_FILE} 不存在")
        return 1

    lines = CHUNKS_FILE.read_text(encoding="utf-8").splitlines()
    chunks = [json.loads(line) for line in lines]

    # 备份
    backup = CHUNKS_FILE.with_suffix(".jsonl.bak2")
    if not backup.exists():
        shutil.copy2(CHUNKS_FILE, backup)
        print(f"备份: {backup}")

    # 分组：按 (class_name, component_type, title_prefix, text_hash)
    groups = defaultdict(list)
    for idx, c in enumerate(chunks):
        if c.get("is_deprecated", False):
            continue
        key = (
            c.get("class_name", ""),
            c.get("component_type", ""),
            title_prefix(c.get("title", "")),
            c.get("feature_subtype"),  # None and str differentiate
        )
        groups[key].append(idx)

    deprecated = 0
    for key, indices in groups.items():
        if len(indices) <= 1:
            continue
        # 只保留 char_count 最大的
        best = max(indices, key=lambda i: chunks[i].get("char_count", 0))
        for idx in indices:
            if idx != best:
                # 验证 text 是否相同（至少开头 500 字符）
                t_best = chunks[best].get("text", "")[:500]
                t_idx = chunks[idx].get("text", "")[:500]
                if t_best == t_idx:
                    chunks[idx]["is_deprecated"] = True
                    deprecated += 1

    # 写出
    new_lines = [json.dumps(c, ensure_ascii=False) for c in chunks]
    CHUNKS_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"标记 deprecated: {deprecated} chunk")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
