"""firstlast.py — Prepare 三闸口 ② T6.3 first/last_entry 自包含检查（v2.2 决策 G 参数化迁移）

源自 docs/专长/t63_firstlast_check.py（k3 审计用，只读）。判定每份报告的
first_entry / last_entry 中文名是否真实存在于**自身**源文件——错位勘探
（报告描述他文件内容）在此检查下必然现形。复用 census 的加载与归一化。

用法：python3 -m vectorizer.prepare.firstlast [--merged ...] [--source ...]
退出码：0 = 全部自包含；1 = 有查无。
"""
import argparse
import json
import re
import sys
from pathlib import Path

from vectorizer.prepare import census as C

CJK = re.compile(r"[一-鿿][一-鿿·/]*")


def cn_name(s):
    m = CJK.match(s.strip().lstrip("*#"))
    return m.group(0) if m else ""


def main(argv=None):
    ap = argparse.ArgumentParser(description="T6.3 first/last_entry 自包含检查（只读）")
    ap.add_argument("--merged", type=Path, default=C.DEFAULT_MERGED, help="per_file.jsonl 路径")
    ap.add_argument("--source", type=Path, default=C.DEFAULT_SOURCE, help="源数据根目录")
    args = ap.parse_args(argv)

    reports = [json.loads(l) for l in open(args.merged, encoding="utf-8") if l.strip()]
    bad = []
    checked = 0
    for r in reports:
        rel = r["file"].removeprefix("pf_rules_md_organized/")
        t = C.load_source(rel, args.source)
        if t is None:
            continue
        np = C.norm_p(t)
        for key in ("first_entry", "last_entry"):
            v = r.get(key, "") or ""
            n = cn_name(v)
            if not n:
                continue
            checked += 1
            if C.norm_p(n) not in np:
                bad.append((r["file"], key, v))
    print(f"检查 first/last_entry {checked} 处，查无 {len(bad)} 处")
    for f, k, v in bad:
        print(f"  {f} [{k}] {v!r}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
