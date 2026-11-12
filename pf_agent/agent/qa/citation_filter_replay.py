#!/usr/bin/env python3
"""离线重放：把基线快照 (qa_report.json) 的 answer+sources 过一遍「只保留被引用来源」过滤，
噪声无关地量化对 A 批三维度分数的纯代价（供 M16 引用治理试点报告复现）。

过滤逻辑与 ChatService.filterCitedSources 一致：
  有效引用 = 正文 [#N] 中纯数字且 1<=N<=len(sources)；保留来源按原顺序；
  正文标记按新下标重映射；无有效引用时 sources=[]。

用法：
    python3 citation_filter_replay.py            # 读同目录 qa_report.json
    python3 citation_filter_replay.py --json out.json
"""
import argparse
import json
import re
from pathlib import Path

from evaluate import score_citation, score_honesty, score_structure

HERE = Path(__file__).resolve().parent
MARK = re.compile(r"\[#([^\]]*)]")


def parse(body: str, maxn: int):
    if re.fullmatch(r"\d+", body) and len(body) <= 9:
        n = int(body)
        if 1 <= n <= maxn:
            return n
    return None


def filter_cited(answer: str, sources: list):
    """返回 (新answer, 新sources, 被引用编号集合, 原引用数)"""
    maxn = len(sources)
    cited_set = set()
    for m in MARK.finditer(answer or ""):
        n = parse(m.group(1), maxn)
        if n is not None:
            cited_set.add(n)
    if not cited_set:
        return MARK.sub("", answer or ""), [], cited_set, 0
    kept = [sources[i - 1] for i in sorted(cited_set)]
    remap = {old: idx + 1 for idx, old in enumerate(sorted(cited_set))}
    out, last = [], 0
    for m in MARK.finditer(answer):
        out.append(answer[last:m.start()])
        n = parse(m.group(1), maxn)
        if n is not None:
            out.append(f"[#{remap[n]}]")
        last = m.end()
    out.append(answer[last:])
    return "".join(out), kept, cited_set, len(cited_set)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default=str(HERE / "qa_report.json"))
    ap.add_argument("--items", default=str(HERE / "pf_qa_items.json"))
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    snap = json.load(open(args.snapshot, encoding="utf-8"))
    items_meta = {it["id"]: it for it in json.load(open(args.items, encoding="utf-8"))["items"]}

    rows = []
    for it in snap["items"]:
        iid = it["id"]
        meta = items_meta.get(iid, {})
        answer = it.get("answer") or ""
        sources = it.get("sources") or []
        gap = bool(it.get("gapReported"))
        is_gap = (not meta.get("expected_chunks")) or (meta.get("notes", "") or "").startswith("gap")
        loose = meta.get("citation_mode") == "loose"
        expected = meta.get("expected_chunks") or []

        new_answer, new_sources, cited_set, n_cited = filter_cited(answer, sources)
        before = {
            "溯源正确性": score_citation(sources, expected, loose=loose),
            "拒绝诚实性": score_honesty({"answer": answer, "sources": sources, "gapReported": gap}, is_gap),
            "回答结构": score_structure(answer, meta.get("dimension", ""), sources),
        }
        after = {
            "溯源正确性": score_citation(new_sources, expected, loose=loose),
            "拒绝诚实性": score_honesty(
                {"answer": new_answer, "sources": new_sources, "gapReported": gap}, is_gap),
            "回答结构": score_structure(new_answer, meta.get("dimension", ""), new_sources),
        }
        rows.append({
            "id": iid, "question": it.get("question", ""), "module": it.get("module", ""),
            "n_sources_before": len(sources), "n_sources_after": len(new_sources),
            "n_cited": n_cited, "cited_set": sorted(cited_set),
            "before": before, "after": after,
            "delta": {k: after[k] - before[k] for k in before},
        })

    dims = ["溯源正确性", "拒绝诚实性", "回答结构"]
    tot_b = {d: sum(r["before"][d] for r in rows) for d in dims}
    tot_a = {d: sum(r["after"][d] for r in rows) for d in dims}
    result = {"n": len(rows), "totals_before": tot_b, "totals_after": tot_a, "rows": rows}
    if args.json:
        json.dump(result, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print("=== 汇总（离线重放基线快照，噪声无关）===")
    for d in dims:
        print(f"  {d}: {tot_b[d]}/{len(rows)} -> {tot_a[d]}/{len(rows)}  (Δ {tot_a[d]-tot_b[d]:+d})")

    zero = [r for r in rows if r["n_cited"] == 0]
    print(f"\n正文引用数为 0 的题: {len(zero)} 题")
    for r in zero:
        print(f"  {r['id']}: sources {r['n_sources_before']}->0, 溯源 "
              f"{r['before']['溯源正确性']}->{r['after']['溯源正确性']}")

    print("\n=== 溯源掉分的题 ===")
    for r in rows:
        if r["delta"]["溯源正确性"] < 0:
            print(f"  {r['id']}: 溯源 1->0 (sources {r['n_sources_before']} 引 {r['n_cited']} 条 "
                  f"cited={r['cited_set']})")

    print("\n=== 结构/诚实掉分的题 ===")
    for r in rows:
        if r["delta"]["回答结构"] < 0 or r["delta"]["拒绝诚实性"] < 0:
            print(f"  {r['id']}: 诚实 {r['before']['拒绝诚实性']}->{r['after']['拒绝诚实性']}, "
                  f"结构 {r['before']['回答结构']}->{r['after']['回答结构']} "
                  f"(sources {r['n_sources_before']}->{r['n_sources_after']})")

    print("\n=== 重点题 ===")
    for iid in ("easy-22", "medium-17"):
        r = next((x for x in rows if x["id"] == iid), None)
        if r:
            print(f"  {iid}: sources {r['n_sources_before']}->{r['n_sources_after']}, "
                  f"cited={r['n_cited']}, 溯源 {r['before']['溯源正确性']}->{r['after']['溯源正确性']}")

    print("\n体积：sources 总条数 %d -> %d" % (
        sum(r["n_sources_before"] for r in rows), sum(r["n_sources_after"] for r in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
