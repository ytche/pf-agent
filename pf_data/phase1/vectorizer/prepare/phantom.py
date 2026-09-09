"""phantom.py — Prepare 三闸口 ③ T6.3 phantom 逐条取证（v2.2 决策 G 参数化迁移）

源自 docs/专长/t63_phantom_forensics.py（k3 审计用，只读）。对 census 判出的
phantom 元素，提取中/英文名 token，判定：
  in_own_file（格式差异，可换真实例）/ cross_file（串扰，他文件存在）/
  invented（源文件全无）。
STOP 词表按类目注册（categories.py），--category 切换；--out 指定取证 JSON 输出。

用法：python3 -m vectorizer.prepare.phantom [--merged ...] [--source ...]
      [--category feat] [--out <verdicts.json>]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from vectorizer.prepare import categories, census as C

L_PREFIX = re.compile(r"^L\d+(?:[-~～/]L?\d+)*[:：]?\s*")
CJK = re.compile(r"[一-鿿][一-鿿·]{1,}")
EN = re.compile(r"[A-Za-z][A-Za-z'’\-]+(?: [A-Za-z'’\-]+){0,4}")

DEFAULT_OUT = Path(__file__).parent.parent.parent / "docs" / "专长" / "t63_phantom_verdicts.json"


def tokens_of(text, stop_cjk, stop_en):
    text = re.sub(r"!\[\[[^\]]*\]\](?:\([^)]*\))?", " ", text)
    cjk = {t for t in CJK.findall(text) if t not in stop_cjk and len(t) >= 2}
    en = set()
    for m in EN.findall(text):
        m = m.strip()
        if m in stop_en or len(m) < 4:
            continue
        en.add(m)
    return sorted(cjk), sorted(en)


def main(argv=None):
    ap = argparse.ArgumentParser(description="T6.3 phantom 逐条取证（只读）")
    ap.add_argument("--merged", type=Path, default=C.DEFAULT_MERGED, help="per_file.jsonl 路径")
    ap.add_argument("--source", type=Path, default=C.DEFAULT_SOURCE, help="源数据根目录")
    ap.add_argument("--category", default="feat", help="类目语义表（categories.py 注册）")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="取证 JSON 输出路径")
    args = ap.parse_args(argv)

    stop = categories.get(args.category)
    reports = [json.loads(l) for l in open(args.merged, encoding="utf-8") if l.strip()]
    # 预载全部源文（报告对应文件去重）
    lib = {}
    for r in reports:
        rel = r["file"].removeprefix("pf_rules_md_organized/")
        if rel not in lib:
            t = C.load_source(rel, args.source)
            if t is not None:
                lib[rel] = (t, C.norm_p(t), C.norm_img(t))
    results = []
    for r in reports:
        rel = r["file"].removeprefix("pf_rules_md_organized/")
        if rel not in lib:
            continue
        src, snp, sni = lib[rel]
        ctx = (src, C.norm(src), snp, sni)
        for i, tf in enumerate(r.get("title_forms", [])):
            raw = tf.get("raw_example", "")
            if not raw:
                continue
            v, details = C.classify_element(raw, ctx)
            if v != "phantom":
                continue
            bad = [s for c, s in details if c == "phantom"]
            joined = " ".join(bad)
            cjks, ens = tokens_of(joined, stop["stop_cjk"], stop["stop_en"])
            own, other = [], defaultdict(list)
            for tok in cjks + ens:
                tn = C.norm_p(tok)
                if tn and tn in snp:
                    own.append(tok)
                else:
                    for rel2, (_, snp2, _) in lib.items():
                        if rel2 != rel and tn and tn in snp2:
                            other[tok].append(rel2)
            if own:
                verdict = "in_own_file"      # 名字在本文件，是格式/错行问题
            elif other:
                verdict = "cross_file"       # 串扰：他文件存在
            else:
                verdict = "invented"         # 全无：虚构
            results.append({
                "file": r["file"], "tf_index": i, "verdict": verdict,
                "tokens_own": own,
                "tokens_elsewhere": {k: v[:3] for k, v in other.items()},
                "bad_segments": bad,
            })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    vc = Counter(x["verdict"] for x in results)
    print(f"phantom 元素 {len(results)} 条 -> {dict(vc)}")
    print(f"明细已写 {args.out}\n")
    for x in results:
        tok = ",".join(x["tokens_own"][:3]) or ",".join(list(x["tokens_elsewhere"])[:3]) or "(无token)"
        print(f"[{x['verdict']:11s}] {x['file']} tf[{x['tf_index']}] :: {tok} :: {x['bad_segments'][0][:60]!r}")
    sys.exit(1 if results else 0)


if __name__ == "__main__":
    main()
