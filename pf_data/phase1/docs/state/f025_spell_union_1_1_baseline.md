# F-025 spell union 1.1 去重重建基线（2026-11-11，M17）

数据侧唯一事实源：`pf_data/phase1/spell_list_union_export.py`（F-025 spec：
`docs/superpowers/specs/2026-11-10-f025-spell-list-deduplication-design.md`）。
数值基线机器可读版见同目录 `f025_spell_union_1_1_baseline.json`（逐职业逐环
新旧 per_class_level 全量）。

## 重建命令

```bash
cd pf_data/phase1
python3 spell_list_union_export.py   # 写出 union 1.1 + report 1.1（幂等，字节一致）
python3 -m vectorizer.build lists.spell_union --force
python3 -m vectorizer.build check
python3 -m pytest vectorizer/tests/test_spell_list_union_export.py -q
```

## 来源对账命令（可复跑，双向比较，非仅 union 自证）

从 spell_lists.json + chunks.jsonl **独立重建**官方与派生原始候选（复用导出器
同一过滤/归一逻辑），与 union 1.1 的 sources 双向比较：
① 每个非污染派生候选 (class, level, chunk_id) 必须出现在 union derived
   sources；② union 的每个 derived 来源必须能回指到重建候选（无凭空来源）；
③ 官方来源按 (class, level, chunk_id) 双向覆盖（chunk_id=null 的清单页条目
   由逐环数量恒等式 `官方主条目 + official_duplicates_merged == official` 兜底）；
④ KN246 `_dup` 候选单独与 chunks 原始 spell_level 核对（不参与折叠覆盖，
   只验留痕完整）；⑤ 标题污染候选明确排除出折叠对账、只验报告计数与不泄漏。

```bash
cd pf_data/phase1
python3 - <<'EOF'
import json, sys
from collections import Counter
sys.path.insert(0, ".")
import spell_list_union_export as ex

u = json.load(open("vectorizer/output/法术/spell_lists_union.json"))
r = json.load(open("vectorizer/output/法术/spell_list_union_report.json"))
lists = json.load(open("vectorizer/output/法术/spell_lists.json"))
chunks = [json.loads(l) for l in open("vectorizer/output/法术/chunks.jsonl") if l.strip()]

scope = set(r["scope_classes"])
# ①② 派生候选重建（与导出器同一过滤：scope + 职业词表 + 0..9 环）
rebuilt_derived, rebuilt_polluted, dup_rebuilt = set(), set(), 0
for c in chunks:
    sl = (c.get("metadata") or {}).get("spell_level") or []
    dup = ex._has_dup_level(sl)
    for it in sl:
        cls, lv = it.get("class"), it.get("level")
        if cls not in scope or cls not in ex._CLASS_TOKENS or not 0 <= lv <= 9:
            continue
        if dup:
            dup_rebuilt += 1
        if ex._is_polluted_title(c.get("title", "")):
            rebuilt_polluted.add((cls, lv, c["chunk_id"]))
        else:
            rebuilt_derived.add((cls, lv, c["chunk_id"]))
union_derived, union_official = set(), set()
official_primary = Counter()
for cname, c in u["classes"].items():
    for lv, entries in c["levels"].items():
        for e in entries:
            if e["source"] == "official_list":
                official_primary[(cname, int(lv))] += 1
            for s in e["sources"]:
                if s["source"] == "derived":
                    union_derived.add((cname, int(lv), s["chunk_id"]))
                else:
                    union_official.add((cname, int(lv), s["chunk_id"]))
assert not (rebuilt_derived - union_derived), \
    f"派生候选丢失: {sorted(rebuilt_derived - union_derived)[:5]}"
assert not (union_derived - rebuilt_derived), \
    f"union 凭空派生来源: {sorted(union_derived - rebuilt_derived)[:5]}"
# ③ 官方来源双向覆盖 + 逐环数量恒等式（null chunk_id 由后者兜底）
rebuilt_official, official_count = set(), Counter()
for cname in u["classes"]:
    for lv in range(10):
        for e in lists["classes"][cname].get("levels", {}).get(str(lv), []):
            rebuilt_official.add((cname, lv, e.get("chunk_id")))
            official_count[(cname, lv)] += 1
assert not (union_official - rebuilt_official), \
    f"union 凭空官方来源: {sorted(union_official - rebuilt_official)[:5]}"
assert not (rebuilt_official - union_official), \
    f"官方来源丢失: {sorted(rebuilt_official - union_official)[:5]}"
for key, pl in r["per_class_level"].items():
    cname, lv = key.rsplit("|", 1)
    cname, lv = cname, int(lv)
    assert official_count[(cname, lv)] == pl["official"], key
    assert (official_primary[(cname, lv)] + pl["official_duplicates_merged"]
            == pl["official"]), key
    assert pl["derived_candidates"] == (pl["derived_added"] + pl["official_merged"]
                                        + pl["derived_duplicates_merged"]), key
    assert pl["union"] == (pl["official"] - pl["official_duplicates_merged"]
                           + pl["derived_added"]), key
# ④ KN246 _dup 单独核对：报告登记数 == 原始 _dup 候选数，且逐条可回源
kn = r["kn246_duplicate_level_candidates"]
assert len(kn) == dup_rebuilt, (len(kn), dup_rebuilt)
chunk_ids = {c["chunk_id"] for c in chunks}
assert all(it["_dup"] is True and it["chunk_id"] in chunk_ids for it in kn)
# ⑤ 标题污染明确排除出折叠对账：不泄漏进 union，报告计数一致
assert not (rebuilt_polluted & union_derived), "标题污染候选泄漏进 union"
assert r["diff_counts"].get("标题污染", 0) == len(rebuilt_polluted), \
    (r["diff_counts"].get("标题污染", 0), len(rebuilt_polluted))
assert r["diff_unclassified"] == 0
print(f"来源对账 OK：派生 {len(union_derived)} 来源、官方 {len(union_official)} 来源对、"
      f"KN246 {dup_rebuilt}、标题污染排除 {len(rebuilt_polluted)}")
EOF
```

## 关键验收数字（真实重建）

- 女巫 1 环：205 → **165**（68 官方 + 97 新增派生；official_merged=68，
  derived_duplicates_merged=40，multi_source_entries=103）。雪球术、精确施法、
  护卫伙伴、速凝术各只出现一次且 sources ≥ 2。
- 召唤师(掉链子) 6 环：冰晶传送UM / 冰晶传送（同 chunk 同英文键）按官方
  内部重复折叠，official 29 → union 28。
- 全量 union 条目总数 23031 → 18431；diff_unclassified=0；
  diff_counts：条目合并 4598（= 全量 derived_duplicates_merged）、书范围外
  8217、译名变体 76、清单页缺录 72、环级证据缺失 1（旧口径 12815/76/144/1，
  书范围外/清单页缺录下降是官方精确命中改为静默折叠所致）。
- OA 五职业零派生、脏职业键零派生；`spell_lists.json` 字节不变；
  union/report version=1.1，manifest expected=1.1，build check 通过。
- 当前 chunks.jsonl 无 KN246 `_dup` 重复 (class, level) 候选，
  `kn246_duplicate_level_candidates` 为空列表属真实数据状态；字段契约与
  明细结构由测试锁定，回潮时自动留痕。

## 已知边界

- 数量守恒、`diff_unclassified != 0`、主条目空规范键（空串/`n/a` 等占位值）
  均为构建硬断言，非零退出且不写产物（spec §8.2/§10.1）。
- 传递链（A 中、B 英、C 传递入组）在 `dedup_name_conflicts.matched` 逐来源
  留痕：每条记录表面名、chunk/source、规范键、`matched_by`、命中键
  `hit_keys` 与逐条命中关系 `hits`（连到哪个来源、经哪个键）；
  条目级 `matched_by` 仍只表示主来源或直接命中类型（spec §6.3）。
- `kn246_duplicate_level_candidates` 在任何标题污染/折叠分支之前登记，
  与是否命中、是否折叠无关（spec §8.2）。
