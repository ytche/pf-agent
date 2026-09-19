#!/usr/bin/env python3
"""J7 keywordSearch 实测探针（方案_Agent检索工具增强_20260917.md 第一步）。

对 200 条确切中文术语（法术/专长/装备）分别跑：
  A. vectorSearch 近似复现：读 ~/.pf_agent/vector_store_<module>.json，
     术语经 Ollama bge-m3 embed 后余弦 topK=8，判定失败 = 目标 chunk_id/title 未进 topK。
  B. 子串原型对照：在 store metadata 的 title/aliases 中做子串匹配。

注意（近似口径）：此处为裸余弦 topK，不复刻 SearchService 的阈值/加权/RRF 等逻辑，
用于探测"确切术语能否被语义检索召回"的缺口，不代表生产检索精确行为。
"""
import json
import math
import os
import sys
import time
import urllib.request

HOME = os.path.expanduser("~")
STORE_DIR = os.path.join(HOME, ".pf_agent")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
TOP_K = 8
EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "bge-m3"

MODULES = {
    "spells": {
        "store": "vector_store_spells.json",
        "chunks": "pf_data/phase1/vectorizer/output/法术/chunks.jsonl",
        "terms_source": "spells",
    },
    "feats": {
        "store": "vector_store_feats.json",
        "chunks": "pf_data/phase1/vectorizer/output/专长/chunks.jsonl",
        "terms_source": "feats",
    },
    "equipment": {
        "store": "vector_store_equipment.json",
        "chunks": "pf_data/phase1/vectorizer/output/装备/chunks.jsonl",
        "terms_source": "equipment",
    },
}


def repo_root():
    # 本文件在 <root>/pf_agent/agent/qa/
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))


def load_store(module):
    path = os.path.join(STORE_DIR, MODULES[module]["store"])
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return path, data


def build_terms():
    """从 spell_lists.json 与 feat/equipment chunks 生成 200 条确切术语（确定性抽样）。"""
    root = repo_root()
    terms = []  # (module, term, target_chunk_id)

    # 法术：spell_lists.json 中各职业法术列表的 cn 名（带 chunk_id），去重后等距抽 100
    sp = os.path.join(root, "pf_data/phase1/vectorizer/output/法术/spell_lists.json")
    with open(sp, encoding="utf-8") as f:
        spell_lists = json.load(f)["classes"]
    spells = {}
    for cls, body in spell_lists.items():
        for lvl, items in body.get("levels", {}).items():
            for it in items:
                if it.get("cn") and it.get("chunk_id") and it["cn"] not in spells:
                    spells[it["cn"]] = it["chunk_id"]
    uniq = sorted(spells.items())
    step = max(1, len(uniq) // 100)
    picked = [uniq[i] for i in range(0, len(uniq), step)][:100]
    for cn, cid in picked:
        terms.append({"module": "spells", "term": cn, "chunk_id": cid})

    # 专长：chunks.jsonl component_type == 'feat' 的 title，等距抽 50
    def pick_from_chunks(rel, want_types, n):
        rows = []
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r.get("component_type") in want_types and r.get("title"):
                    rows.append((r["title"], r["chunk_id"]))
        seen, uniq = set(), []
        for t, cid in sorted(rows):
            if t not in seen:
                seen.add(t)
                uniq.append((t, cid))
        step = max(1, len(uniq) // n)
        return [uniq[i] for i in range(0, len(uniq), step)][:n]

    for t, cid in pick_from_chunks(MODULES["feats"]["chunks"], {"feat"}, 50):
        terms.append({"module": "feats", "term": t, "chunk_id": cid})
    for t, cid in pick_from_chunks(MODULES["equipment"]["chunks"], {"gear", "weapon", "armor"}, 50):
        terms.append({"module": "equipment", "term": t, "chunk_id": cid})
    return terms


def embed(text, retries=2):
    body = json.dumps({"model": EMBED_MODEL, "input": text}).encode()
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(EMBED_URL, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                out = json.load(resp)
            return out["embeddings"][0]
        except Exception as e:
            if attempt == retries:
                raise
            time.sleep(2 * (attempt + 1))


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def vector_search(store, query_vec, top_k=TOP_K):
    scored = []
    for _id, rec in store.items():
        scored.append((cosine(query_vec, rec["embedding"]), _id, rec))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_k]


def substring_match(store, term):
    t = term.lower()
    hits = []
    for _id, rec in store.items():
        md = rec.get("metadata", {})
        title = (md.get("title") or "").lower()
        aliases = md.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        hay = [title] + [a.lower() for a in aliases]
        if any(t in h or h in t for h in hay if h):
            hits.append(_id)
    return hits


def main():
    terms = build_terms()
    print(f"[probe] terms built: {len(terms)}")
    for m in ("spells", "feats", "equipment"):
        sub = [t for t in terms if t["module"] == m]
        print(f"[probe]   {m}: {len(sub)}  e.g. {[t['term'] for t in sub[:5]]}")

    stores = {}
    for m in MODULES:
        path, data = load_store(m)
        stores[m] = data
        print(f"[probe] store {path}: {len(data)} records")

    results = []
    for i, t in enumerate(terms):
        m, term = t["module"], t["term"]
        store = stores[m]
        rec = vector_search(store, embed(term))
        rank = next((k + 1 for k, (_s, _id, r) in enumerate(rec)
                     if _id == t["chunk_id"] or r.get("metadata", {}).get("chunk_id") == t["chunk_id"]
                     or r.get("metadata", {}).get("title") == term), None)
        sub_hits = substring_match(store, term)
        results.append({
            "module": m, "term": term, "chunk_id": t["chunk_id"],
            "vector_rank": rank,
            "vector_top": [{"rank": k + 1, "title": r.get("metadata", {}).get("title"),
                            "score": round(s, 4), "chunk_id": r.get("metadata", {}).get("chunk_id")}
                           for k, (s, _id, r) in enumerate(rec)],
            "substring_hit": bool(sub_hits),
        })
        if (i + 1) % 20 == 0:
            print(f"[probe] {i + 1}/{len(terms)} done")

    with open(os.path.join(OUT_DIR, "keyword_gap_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    summary = {}
    for m in MODULES:
        sub = [r for r in results if r["module"] == m]
        vf = [r for r in sub if r["vector_rank"] is None]
        sf = [r for r in sub if not r["substring_hit"]]
        summary[m] = {
            "n": len(sub),
            "vector_fail": len(vf), "vector_fail_rate": round(len(vf) / len(sub) * 100, 1),
            "substr_fail": len(sf), "substr_fail_rate": round(len(sf) / len(sub) * 100, 1),
        }
    vf_all = sum(s["vector_fail"] for s in summary.values())
    sf_all = sum(s["substr_fail"] for s in summary.values())
    n_all = len(results)
    print(json.dumps({"per_module": summary,
                      "overall": {"n": n_all,
                                  "vector_fail_rate": round(vf_all / n_all * 100, 1),
                                  "substr_fail_rate": round(sf_all / n_all * 100, 1)}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
