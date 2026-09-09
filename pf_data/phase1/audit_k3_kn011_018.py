#!/usr/bin/env python3
"""k3 独立审计脚本 v2：按 metadata 口径重算 KN011~018 指标。"""
import json, re
from collections import Counter

CHUNKS = "vectorizer/output/法术/chunks.jsonl"
chunks = [json.loads(l) for l in open(CHUNKS, encoding="utf-8") if l.strip()]
by_id = {c["chunk_id"]: c for c in chunks}
md = lambda c: c.get("metadata", {}) or {}
fs = lambda c, f: (md(c).get("field_status", {}) or {}).get(f)
print(f"总 chunk 数: {len(chunks)}")

# ---------- KN011 ----------
print("\n=== KN011 ===")
linked = [c for c in chunks if c.get("base_spell_chunk_id")]
print(f"带 base_spell_chunk_id: {len(linked)}")
self_ref = [c["chunk_id"] for c in linked if c["base_spell_chunk_id"] == c["chunk_id"]]
dangling = [c["chunk_id"] for c in linked if c["base_spell_chunk_id"] not in by_id]
print(f"自指: {len(self_ref)}; 悬空: {len(dangling)}")
ma_chunks = [c for c in chunks if "page_625" in c.get("doc_id","")]
print(f"page_625 (MA) chunks: {len(ma_chunks)}")
ma_new_full = [c for c in ma_chunks if not c.get("base_spell_chunk_id")]
print(f"MA 中无 base_id 的 chunk: {len(ma_new_full)}")
for c in ma_new_full[:12]:
    print(f"  - {c['chunk_id']} | {c.get('title','')[:30]}")
# 多匹配 CRB 优先：抽 linked 中 base 书非 CRB 但存在同名 CRB 的
def crb_priority_check():
    bad = []
    for c in linked:
        base = by_id[c["base_spell_chunk_id"]]
        if base.get("book_abbreviation") == "CRB":
            continue
        title = base.get("title","")
        crb_same = [x for x in chunks if x.get("title")==title and x.get("book_abbreviation")=="CRB"]
        if crb_same:
            bad.append((c["chunk_id"], title, base.get("book_abbreviation")))
    return bad
bad_crb = crb_priority_check()
print(f"存在 CRB 同名但 base 指向非 CRB: {len(bad_crb)} {bad_crb[:5]}")

# ---------- KN012 ----------
print("\n=== KN012 ===")
for pid in ("page_1365", "page_1363"):
    sub = [c for c in chunks if c.get("doc_id") == pid]
    sr_miss = sum(1 for c in sub if fs(c,"spell_resistance")=="missing")
    print(f"{pid}: chunks={len(sub)}, SR missing={sr_miss}")
sr_parsed = sum(1 for c in chunks if fs(c,"spell_resistance")=="parsed")
print(f"SR parsed 总数: {sr_parsed}")
m1 = 0; m1_samples=[]
STR_FIELDS = ("school","subschool","casting_time","range","target","effect","duration","area")
for c in chunks:
    for k in STR_FIELDS:
        v = md(c).get(k)
        if isinstance(v, str) and "**" in v:
            m1 += 1; m1_samples.append((c["chunk_id"], k, v[:60])); break
print(f"M1 字段值含 ** 残留: {m1}")
for s in m1_samples[:5]: print("  ", s)

# ---------- KN013 ----------
print("\n=== KN013 ===")
def stat(field, pred):
    return sum(1 for c in chunks if isinstance(md(c).get(field), str) and pred(md(c)[field]))
print(f"duration 含 。: {stat('duration', lambda v: '。' in v)}")
print(f"duration len>40: {stat('duration', lambda v: len(v) > 40)}")
print(f"target len>40: {stat('target', lambda v: len(v) > 40)}")
print(f"effect len>40: {stat('effect', lambda v: len(v) > 40)}")
print(f"school len>15: {stat('school', lambda v: len(v) > 15)}")
print(f"[补充] casting_time len>40: {stat('casting_time', lambda v: len(v) > 40)}")
ct_bad = [(c["chunk_id"], md(c)["casting_time"][:70]) for c in chunks if isinstance(md(c).get("casting_time"), str) and len(md(c)["casting_time"])>40]
for s in ct_bad[:8]: print("  ", s)

# ---------- KN014 ----------
print("\n=== KN014 ===")
inter=0; ndom=0; nsub=0; bad_dom=[]
def norm_entries(v):
    """domains/subdomains 条目可能是 str 或 dict，统一成名串。"""
    out = []
    for x in (v or []):
        if isinstance(x, dict):
            out.append(x.get("name") or x.get("domain") or json.dumps(x, ensure_ascii=False))
        else:
            out.append(str(x))
    return out
for c in chunks:
    d = norm_entries(md(c).get("domains"))
    s = norm_entries(md(c).get("subdomains"))
    if d: ndom += 1
    if s: nsub += 1
    if set(d) & set(s): inter += 1
    for x in d:
        if "子域" in x or "子领域" in x: bad_dom.append((c["chunk_id"], x))
print(f"交集非空: {inter}; 有 domains: {ndom}; 有 subdomains: {nsub}; domains 含子域词: {len(bad_dom)}")
if bad_dom[:5]: print("  样本:", bad_dom[:5])

# ---------- KN015 ----------
print("\n=== KN015 ===")
untitled = [c["chunk_id"] for c in chunks if not c.get("title")]
print(f"无标题 chunk: {len(untitled)}")
for nid in ("spell_page_1365_0179","spell_page_1365_0327","spell_page_1365_0337"):
    print(f"  {nid} 仍存在: {nid in by_id}")

# ---------- KN016 ----------
print("\n=== KN016 ===")
polluted = [c for c in chunks if c.get("text","").count("**学派：**") > 1]
print(f"text 含 **学派：** >1 次: {len(polluted)} (执行方口径 26)")
print(f"  来源书分布: {dict(Counter(c.get('book_abbreviation','?') for c in polluted))}")
print(f"  doc_id 分布: {dict(Counter(c.get('doc_id','?') for c in polluted))}")
for name in ("獾之凶暴","醉汉吐息","伊利森镜视术","延缓诅咒","毒液喷吐","次等指使术","梦境旅行","虫类形态"):
    hits = [c["chunk_id"] for c in chunks if c.get("title","").startswith(name)]
    print(f"  {name}: {hits if hits else '缺失!'}")
arch8 = by_id.get("spell_动物档案AArch_0008") or [c for c in chunks if "动物档案" in c.get("doc_id","") and c["chunk_id"].endswith("_0008")]
if isinstance(arch8, list): arch8 = arch8[0] if arch8 else None
if arch8: print(f"  动物档案_0008: title={arch8.get('title')!r}")
for name in ("共享形态","护卫伙伴","空中坐骑"):
    hits = [c["chunk_id"] for c in chunks if c.get("title","").startswith(name)]
    print(f"  {name}: {hits if hits else '缺失!'}")

# ---------- KN017 ----------
print("\n=== KN017 ===")
print(f"duration 含 /等级: {stat('duration', lambda v: '/等级' in v)}")
for name in ("血液解读","次级创造半位面","光荣时刻","共用召唤坐骑"):
    hits = [c for c in chunks if c.get("title","").startswith(name)]
    for c in hits[:1]:
        lv = md(c).get("spell_level")
        print(f"  {name}: {json.dumps(lv, ensure_ascii=False) if lv else None}")
fop = [c for c in chunks if c.get("book_abbreviation")=="FoP"]
resid = [c["chunk_id"] for c in fop if "/" in c.get("title","")]
print(f"FoP chunks: {len(fop)}; 标题含/: {len(resid)} {resid[:3]}")

# ---------- KN018 ----------
print("\n=== KN018 ===")
st_miss = sum(1 for c in chunks if fs(c,"saving_throw")=="missing")
sr_miss = sum(1 for c in chunks if fs(c,"spell_resistance")=="missing")
print(f"ST missing: {st_miss} (交付 2008); SR missing: {sr_miss} (交付 1906)")
st_none = [c for c in chunks if isinstance(md(c).get("saving_throw"), dict) and md(c)["saving_throw"].get("type")=="无"]
st_none_parsed = [c for c in st_none if fs(c,"saving_throw")=="parsed"]
print(f"ST type=='无': {len(st_none)}; 其中 status=parsed: {len(st_none_parsed)}")
sr_neg = [c for c in chunks if isinstance(md(c).get("spell_resistance"), dict) and md(c)["spell_resistance"].get("applies") is False]
sr_neg_note = [c for c in sr_neg if md(c)["spell_resistance"].get("note") in ("不可","否","无")]
sr_neg_parsed = [c for c in sr_neg_note if fs(c,"spell_resistance")=="parsed"]
print(f"SR applies=False: {len(sr_neg)}; note∈{{不可,否,无}}: {len(sr_neg_note)}; 其中 parsed: {len(sr_neg_parsed)}")
print(f"components status: {dict(Counter(fs(c,'components') for c in chunks))}")

# ---------- N6: MA 摘要 ST/SR ----------
print("\n=== N6 (MA 摘要 ST/SR 应保持 missing) ===")
ma_summary = [c for c in ma_chunks if c.get("base_spell_chunk_id")]
ma_st_parsed = [(c["chunk_id"], c.get("title","")) for c in ma_summary if fs(c,"saving_throw")=="parsed"]
ma_sr_parsed = [(c["chunk_id"], c.get("title","")) for c in ma_summary if fs(c,"spell_resistance")=="parsed"]
print(f"MA 摘要 ST parsed: {len(ma_st_parsed)} {ma_st_parsed[:5]}")
print(f"MA 摘要 SR parsed: {len(ma_sr_parsed)} {ma_sr_parsed[:5]}")

# ---------- 其他 ----------
print("\n=== 其他 ===")
print(f"无 field_status: {sum(1 for c in chunks if not md(c).get('field_status'))}")
print(f"component_type: {dict(Counter(c.get('component_type','?') for c in chunks))}")
