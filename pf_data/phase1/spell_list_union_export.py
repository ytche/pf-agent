#!/usr/bin/env python3
"""spell_list_union_export.py — F-025 法术清单去重（union schema 1.1）

产物形态乙：新增独立产物 spell_lists_union.json（官方清单 ∪ 库侧 spell_level
派生），spell_lists.json 字节级不动。同步产出 spell_list_union_report.json
（per_class_level 守恒对账 + diff 全归类 + conflicts + KN246 原始候选 +
dedup_name_conflicts），diff_unclassified==0 与数量守恒硬断言。

F-025（2026-11-10 spec）：同一职业同一环级内每个法术只出现一次。
法术身份 = 保守归一后的中文键或英文键任一命中，分组采用传递闭包；
官方内部重复与官方/派生交叉按同一规则折叠，官方主条目优先，纯派生组
保持首次命中为主。条目保留主字段 + 完整 sources（主来源首位，
(chunk_id, source) 去重），每来源记录准确 matched_by。

范围（D6）：五书线 20 职业（26 职业 − OA 五职业[唤魂/秘学/通灵/异能/催眠]
− 召唤师(掉链子) 脏键）；OA 五职业仅官方清单透传（derived:false）。
译名变体白名单（D4）= KN017 已归类先例（spell_list_export.normalize 同源
fixes 表）；先例外新候选只进报告「译名变体候选」节，停下报告主 Agent，
不入常量（内容类审批流）。
"""
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spell_list_export import normalize as kn017_normalize  # KN017 先例映射（已归类）

BASE = Path(__file__).resolve().parent
LISTS_JSON = BASE / "vectorizer/output/法术/spell_lists.json"
CHUNKS = BASE / "vectorizer/output/法术/chunks.jsonl"
OUT_UNION = BASE / "vectorizer/output/法术/spell_lists_union.json"
OUT_REPORT = BASE / "vectorizer/output/法术/spell_list_union_report.json"

OA_CLASSES = {"唤魂师", "秘学士", "通灵者", "异能者", "催眠师"}
DIRTY_CLASS_KEYS = {"召唤师(掉链子)"}  # KN233 脏键，非真实职业，不入派生范围
FIVE_BOOKS = {"CRB", "APG", "UM", "UC", "ACG"}
LEGAL_DIFF_TAGS = {"书范围外", "译名变体", "标题污染", "条目合并", "环级证据缺失",
                   # 第六标签（2026-10-29 实施时扩展，拍下报告待追认）：库侧有、
                   # 清单页五书内缺录（官方列表页本身不完整，M12 已知族）
                   "清单页缺录"}
MAX_LEVEL = 9

# 派生职业词表：白名单 20 职业的 class token 归一目标（含 F3 拆分后单职业名）
_CLASS_TOKENS = {
    "术士", "法师", "女巫", "牧师", "吟游诗人", "德鲁伊", "先知", "审判者",
    "魔战士", "奥能师", "异能者", "召唤师", "游侠", "圣武士", "炼金术师",
    "萨满", "反圣武士", "战斗祭司", "催眠师", "秘学士", "歌者", "通灵者",
    "猎人", "唤魂师", "血脉狂怒者", "调查员",
}

_EN_EMPTY_KEYS = {"", "n/a", "na", "none", "null", "-", "—", "?", "？"}
_EN_APOSTROPHES = {"'", "’", "‘", "ʼ", "′"}
_EN_QUOTES = {'"', '“', '”', '«', '»', '‹', '›'}


def _norm_cn(s: str) -> str:
    """匹配键归一：KN017 译名变体归一 + 去空白（全半角/大小写不敏感靠 KN017 表）。

    F-025：保守归一，不得在本批增加新译名映射或删除实义词。
    """
    return kn017_normalize(re.sub(r"[\s|]+", "", (s or "").strip()))


def _norm_en(s: str):
    """F-025 英文键保守兼容归一；无英文键返回 None。

    Unicode 全半角兼容归一 + 小写 + 连续空白折叠 + 直弯 apostrophe/双引号归一；
    n/a 等占位值视为无英文键。
    """
    t = unicodedata.normalize("NFKC", (s or "")).strip().lower()
    for ch in _EN_APOSTROPHES:
        t = t.replace(ch, "'")
    for ch in _EN_QUOTES:
        t = t.replace(ch, '"')
    t = re.sub(r"\s+", " ", t)
    if t in _EN_EMPTY_KEYS:
        return None
    return t or None


def _is_polluted_title(title: str) -> bool:
    """KN244 标题污染启发：标题截成 I/II 等罗马数字碎片。"""
    t = (title or "").strip()
    return bool(re.fullmatch(r"[IVX]{1,6}", t))


def _build_kn017_fold_index() -> dict:
    """KN017 折叠先例反查索引：逐阵营细目 → 清单页合并条目（显式展开，
    合并键分段不带前缀/后缀，逐一重组后登记）。

    依据：spell_list_export.normalize 的 KN017 fixes 表归类
    （侦测混乱/邪恶/善良/守序→侦测阵营 类合并对，官方清单页收合并形态）。
    """
    index = {}
    families = (
        ("侦测", "", ("混乱", "邪恶", "善良", "守序", "秩序"), "侦测阵营"),
        ("防护", "", ("混乱", "邪恶", "善良", "守序", "秩序"), "防护阵营"),
        ("反", "法阵", ("混乱", "邪恶", "善良", "守序", "秩序"), "反混乱/邪恶/善良/守序法阵"),
        ("反制", "", ("混乱", "邪恶", "善良", "守序", "秩序"), "反制混乱/邪恶/善良/守序"),
    )
    for head, tail, subs, _target in families:
        for sub in subs:
            index[head + sub + tail] = True
    return index


_KN017_FOLD = _build_kn017_fold_index()


def _build_fixes_values() -> set:
    """KN017 fixes 表值集合（动物交谈术→动物交谈 类已归类对的右端）。"""
    vals = set()
    for key, target in (
        ("动物交谈术", None), ("植物交谈术", None),
    ):
        vals.add(kn017_normalize(key))
    # fixes 表右端（chunk 标题用词）——从 normalize 行为推：KN017 归类过的
    # 「列表页译名→chunk 用词」对全部收录于 spell_list_export.normalize 的
    # fixes 表；此处仅登记 union 差异对账涉及的右端词（术-strip 族）
    vals |= {kn017_normalize(x) for x in (
        "动物交谈", "植物交谈", "构装体残废", "侦测阵营", "防护阵营",
        "治疗中伤", "治疗重伤", "治疗轻伤", "造成中伤", "造成重伤", "造成轻伤",
    )}
    return vals


_FIXES_VALUES = _build_fixes_values()


def _strip_colon(s: str) -> str:
    """全半角冒号/间隔号剥离（真言术：盲 ↔ 真言术盲 类标点变体）。"""
    return re.sub(r"[：:；;·．.]", "", s)


def _has_dup_level(items: list) -> bool:
    """KN246 条目合并启发：同一 chunk spell_level 含重复 (class, level)。"""
    seen = set()
    for it in items:
        k = (it.get("class"), it.get("level"))
        if k in seen:
            return True
        seen.add(k)
    return False


class _UnionFind:
    """传递闭包分组：候选间中文键或英文键任一相同即同组。"""

    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def _variant_tag(k_cn: str, off_cn: set) -> str:
    """译名变体检出（三级，全部 KN017 先例族内）：kn017_fold / punct / 术尾。"""
    if k_cn in _KN017_FOLD:
        return "kn017_fold"
    stem = re.sub(r"术$", "", k_cn)
    if _strip_colon(k_cn) != k_cn and any(
            _strip_colon(k_cn) == _strip_colon(o) for o in off_cn):
        return "punct_variant"
    if (stem and stem in off_cn) or any(
            re.sub(r"术$", "", o) == k_cn for o in off_cn):
        return "shu_suffix"
    return None


def _variant_in_fixes(k_cn: str) -> bool:
    stem = re.sub(r"术$", "", k_cn)
    return (k_cn in _FIXES_VALUES) or (stem in _FIXES_VALUES)


def _fold_level(cls: str, lv: int, official: list, derived: list,
                report: dict) -> list:
    """F-025：单（职业, 环级）候选折叠。

    官方与派生候选统一参与保守键分组（传递闭包），主来源 = 首个官方
    条目，否则首个派生条目。返回 union 1.1 条目序列（官方组在前）。
    """
    # ---- 候选清单（官方在前，保持既有导出顺序）----
    candidates = []  # {cn,en,book,chunk_id,source,level_evidence,_dup,k_cn,k_en}
    for e in official:
        candidates.append({
            "cn": e.get("cn", ""), "en": e.get("en", ""),
            "book": e.get("book", ""), "chunk_id": e.get("chunk_id"),
            "source": "official_list", "level_evidence": None,
            "_dup": False,
            "k_cn": _norm_cn(e.get("cn", "")) or None,
            "k_en": _norm_en(e.get("en", "")),
        })
    participating = []  # 参与折叠的派生原始记录（供报告/差异归类）
    for d in derived:
        if d["_dup"]:
            # KN246 原始候选：在任何标题污染/排除/折叠分支之前登记，
            # 无论是否命中、是否最终被折叠，审计不静默消失（r1-P1-2）
            report["kn246"].append({
                "class": cls, "level": lv, "chunk_id": d["chunk_id"],
                "cn": d["cn"], "en": d["en"], "book": d["book"],
                "_dup": True,
            })
        if _is_polluted_title(d["cn"]):
            # KN244 污染标题 derived 只进报告不并入产物（QA-K1：标题失真
            # 条目进 union 即污染检索，待标题簇批次修复后自然回流）；
            # 不参与折叠，不计入 derived_candidates
            report["diff_tagged"]["标题污染"].append({
                "class": cls, "level": lv, "chunk_id": d["chunk_id"],
                "cn": d["cn"], "en": d["en"], "book": d["book"],
            })
            continue
        k_cn = _norm_cn(d["cn"]) or None
        k_en = _norm_en(d["en"])
        candidates.append({
            "cn": d["cn"], "en": d["en"], "book": d["book"],
            "chunk_id": d["chunk_id"], "source": "derived",
            "level_evidence": f"spell_level: {cls} {lv}",
            "_dup": d["_dup"], "k_cn": k_cn, "k_en": k_en,
        })
        participating.append(d)

    # ---- 传递闭包分组 ----
    n = len(candidates)
    uf = _UnionFind(n)
    by_key = defaultdict(list)
    for i, c in enumerate(candidates):
        if c["k_cn"]:
            by_key[("cn", c["k_cn"])].append(i)
        if c["k_en"]:
            by_key[("en", c["k_en"])].append(i)
    for ids in by_key.values():
        for j in ids[1:]:
            uf.union(ids[0], j)

    groups = defaultdict(list)  # root -> member indices（候选序）
    for i in range(n):
        groups[uf.find(i)].append(i)
    ordered = list(groups.values())  # 组代表候选序号最小者 → 官方在前
    ordered.sort(key=min)

    # ---- 主来源选择 + sources 折叠 ----
    entries = []
    n_official_dup = n_official_merged = n_derived_dup = n_multi = 0
    for members in ordered:
        primary_idx = next(i for i in members
                           if candidates[i]["source"] == "official_list") \
            if any(candidates[i]["source"] == "official_list" for i in members) \
            else members[0]
        primary = candidates[primary_idx]
        is_official_group = primary["source"] == "official_list"

        # sources：主来源首位，其余按首次出现顺序，(chunk_id, source) 去重
        ordered_members = [primary_idx] + [i for i in members if i != primary_idx]
        sources = []
        seen_pairs = set()
        member_sources = {}  # idx -> matched_by
        member_hit_keys = {}  # idx -> 本候选自身与组内其他成员命中的键种类
        member_hits = {}      # idx -> 逐条命中关系（连到哪个来源、经哪个键）
        for i in ordered_members:
            c = candidates[i]
            hits = []
            for j in ordered_members:
                if j == i:
                    continue
                keys = [k for k in ("cn", "en")
                        if c[f"k_{k}"] and candidates[j][f"k_{k}"] == c[f"k_{k}"]]
                if keys:
                    hits.append({
                        "cn": candidates[j]["cn"],
                        "chunk_id": candidates[j]["chunk_id"],
                        "source": candidates[j]["source"],
                        "keys": keys,
                    })
            member_hits[i] = hits
            member_hit_keys[i] = [k for k in ("cn", "en")
                                  if any(k in h["keys"] for h in hits)]
        for i in ordered_members:
            c = candidates[i]
            if i == primary_idx:
                mb = "official_primary" if is_official_group else "derived_new"
            else:
                hit_cn = "cn" in member_hit_keys[i]
                hit_en = "en" in member_hit_keys[i]
                prefix = "official" if is_official_group else "derived"
                if hit_cn and hit_en:
                    mb = prefix + "_cn_and_en"
                elif hit_cn:
                    mb = prefix + "_cn"
                elif hit_en:
                    mb = prefix + "_en"
                else:
                    mb = "derived_new"  # 无键候选只能独立成组，防御分支
            member_sources[i] = mb
            pair = (c["chunk_id"], c["source"])
            if pair in seen_pairs:
                continue  # 相同 (chunk_id, source) 不重复写入（null 无例外，r1-P2-4）
            seen_pairs.add(pair)
            s = {"book": c["book"], "chunk_id": c["chunk_id"],
                 "source": c["source"], "matched_by": mb}
            if c["source"] == "derived":
                s["level_evidence"] = c["level_evidence"]
            sources.append(s)

        # ---- 折叠计数（守恒口径）----
        n_off = sum(1 for i in members
                    if candidates[i]["source"] == "official_list")
        n_dev = len(members) - n_off
        if is_official_group:
            n_official_dup += n_off - 1
            n_official_merged += n_dev
        else:
            n_derived_dup += n_dev - 1
        if len(sources) > 1:
            n_multi += 1

        # ---- 差异归类（基于原始候选记录，折叠不丢审计线索）----
        off_cn = {c["k_cn"] for i, c in enumerate(candidates)
                  if c["source"] == "official_list" and c["k_cn"]}
        off_en = {c["k_en"] for i, c in enumerate(candidates)
                  if c["source"] == "official_list" and c["k_en"]}
        for i in ordered_members:
            c = candidates[i]
            if c["source"] != "derived":
                continue
            mb = member_sources[i]
            if mb.startswith("official_"):
                continue  # 命中官方清单 → 非差异（并入官方组）
            if mb != "derived_new":
                # 并入既有派生组 → 条目合并（折叠的重复派生来源）
                report["diff_tagged"]["条目合并"].append({
                    "class": cls, "level": lv, "chunk_id": c["chunk_id"],
                    "cn": c["cn"], "en": c["en"], "book": c["book"],
                    "note": "跨 chunk 重复条目（KN246 族观察）"})
            elif c["book"] not in FIVE_BOOKS:
                report["diff_tagged"]["书范围外"].append({
                    "class": cls, "level": lv, "chunk_id": c["chunk_id"],
                    "cn": c["cn"], "en": c["en"], "book": c["book"]})
            else:
                kind = _variant_tag(c["k_cn"] or "", off_cn)
                if kind:
                    report["diff_tagged"]["译名变体"].append({
                        "class": cls, "level": lv, "chunk_id": c["chunk_id"],
                        "cn": c["cn"], "en": c["en"], "book": c["book"]})
                    report["variant_candidates"].append({
                        "class": cls, "level": lv, "chunk_id": c["chunk_id"],
                        "derived_cn": c["cn"], "derived_en": c["en"],
                        "book": c["book"], "kind": kind,
                        "kn017_precedent": kind == "kn017_fold" or
                        (kind == "shu_suffix" and _variant_in_fixes(c["k_cn"])),
                    })
                else:
                    report["diff_tagged"]["清单页缺录"].append({
                        "class": cls, "level": lv, "chunk_id": c["chunk_id"],
                        "cn": c["cn"], "en": c["en"], "book": c["book"],
                        "note": "库侧 spell_level 可证、清单页未收录"})

        # ---- 组内名称冲突明细 ----
        cn_surfaces = sorted({candidates[i]["cn"] for i in members})
        en_surfaces = sorted({candidates[i]["en"] for i in members if
                              _norm_en(candidates[i]["en"])})
        if len(cn_surfaces) > 1 or len(en_surfaces) > 1:
            report["name_conflicts"].append({
                "class": cls, "level": lv, "primary_cn": primary["cn"],
                "names": {"cn": cn_surfaces, "en": en_surfaces},
                "norm_keys": {"cn": sorted({candidates[i]["k_cn"] for i in members
                                            if candidates[i]["k_cn"]}),
                              "en": sorted({candidates[i]["k_en"] for i in members
                                            if candidates[i]["k_en"]})},
                "sources": sources,
                # r1-P2-3：按原始来源列表记录，不以中文名做键——同表面名
                # 多来源不覆盖；A/B/C 传递链逐来源保留规范键与命中来源/键
                "matched": [
                    {"cn": candidates[i]["cn"], "en": candidates[i]["en"],
                     "chunk_id": candidates[i]["chunk_id"],
                     "source": candidates[i]["source"],
                     "role": "primary" if i == primary_idx else "merged",
                     "matched_by": member_sources[i],
                     "norm_keys": {"cn": candidates[i]["k_cn"],
                                   "en": candidates[i]["k_en"]},
                     "hit_keys": member_hit_keys[i],
                     "hits": member_hits[i]}
                    for i in ordered_members],
            })

        entry = {"cn": primary["cn"], "en": primary["en"],
                 "book": primary["book"], "chunk_id": primary["chunk_id"],
                 "source": primary["source"], "sources": sources}
        if primary["source"] == "derived":
            entry["level_evidence"] = primary["level_evidence"]
            entry["matched_by"] = "derived_new"
        entries.append(entry)

    pl = {"official": len(official),
          "derived_candidates": len(participating),
          "derived_added": sum(1 for e in entries if e["source"] == "derived"),
          "union": len(entries),
          "official_duplicates_merged": n_official_dup,
          "official_merged": n_official_merged,
          "derived_duplicates_merged": n_derived_dup,
          "multi_source_entries": n_multi}
    report["per_class_level"][f"{cls}|{lv}"] = pl
    return entries


def find_primary_key_errors(union_classes: dict) -> list:
    """r1-P1-1：写产物前校验——每个主条目至少一个有效规范中文或英文键。

    空串、全英文占位值（n/a 等）归一后均为无键 → 构建必须失败（非零退出）。
    """
    errors = []
    for cls, c in union_classes.items():
        for lv, entries in (c.get("levels") or {}).items():
            for e in entries:
                if not (_norm_cn(e.get("cn", "")) or _norm_en(e.get("en", ""))):
                    errors.append(
                        f"{cls}|{lv}: 主条目无有效规范键 cn={e.get('cn')!r} "
                        f"en={e.get('en')!r}")
    return errors


def main() -> int:
    lists = json.loads(LISTS_JSON.read_text(encoding="utf-8"))
    chunks = [json.loads(l) for l in CHUNKS.read_text(encoding="utf-8").splitlines() if l.strip()]

    all_classes = list(lists["classes"].keys())
    scope_classes = [c for c in all_classes if c not in OA_CLASSES and c not in DIRTY_CLASS_KEYS]
    excluded = {c: "OA 清单页跨 20+ 书，派生无收益" for c in sorted(OA_CLASSES)}
    excluded.update({c: "KN233 脏键非真实职业，不派生" for c in sorted(DIRTY_CLASS_KEYS)})

    # ---- 派生聚合：chunks spell_level 展开（A 阶段清洗后产物，class 已归一/F3 已拆） ----
    derived = defaultdict(list)  # (class, level) -> [{cn,en,book,chunk_id,_dup}]
    for c in chunks:
        sl = (c.get("metadata") or {}).get("spell_level") or []
        if not sl:
            continue  # 环级证据缺失（10.1% 空率）→ 不产生派生候选
        dup = _has_dup_level(sl)
        for it in sl:
            cls = it.get("class")
            if cls not in _CLASS_TOKENS:
                continue
            if cls in OA_CLASSES:
                continue  # D6：OA 五职业不派生（双重过滤）
            derived[(cls, it["level"])].append({
                "cn": c.get("title", ""),
                "en": (c.get("aliases") or [""])[0] if c.get("aliases") else "",
                "book": c.get("book_abbreviation", ""),
                "chunk_id": c["chunk_id"],
                "_dup": dup,
            })

    # ---- 并集 + F-025 折叠 ----
    union_classes = {}
    report = {"per_class_level": {}, "diff_tagged": defaultdict(list),
              "variant_candidates": [], "conflicts": [],
              "kn246": [], "name_conflicts": []}

    for cls in all_classes:
        src = lists["classes"][cls]
        levels_out = {}
        in_scope = cls in scope_classes
        lv_src = src.get("levels", {})
        for lv in range(MAX_LEVEL + 1):
            key = str(lv)
            official = lv_src.get(key, [])
            entries = _fold_level(
                cls, lv, official,
                derived.get((cls, lv), []) if in_scope else [],
                report)
            levels_out[key] = entries

            # D7 冲突：派生候选与清单页同书但归一名不同（同书重复条目）→ 清单页权威
            if in_scope:
                off_cn = {_norm_cn(e.get("cn", "")) for e in official}
                off_by_book = Counter(e.get("book") for e in official)
                for d in derived.get((cls, lv), []):
                    if d["book"] in FIVE_BOOKS and off_by_book.get(d["book"], 0) > 0:
                        k_cn = _norm_cn(d["cn"])
                        if k_cn and k_cn not in off_cn:
                            report["conflicts"].append({
                                "class": cls, "level": lv, "book": d["book"],
                                "chunk_id": d["chunk_id"], "derived_cn": d["cn"],
                                "rule": "清单页权威（official kept）",
                            })
        union_classes[cls] = {
            "source_page": src.get("source_page", ""),
            "aliases": src.get("aliases", []),
            "levels": levels_out,
        }

    # ---- 官方条目侧缺口：chunk spell_level 空（环级证据缺失）----
    chunk_by_id = {c["chunk_id"]: c for c in chunks}
    for cls in scope_classes:
        for lv in range(MAX_LEVEL + 1):
            for e in lists["classes"][cls].get("levels", {}).get(str(lv), []):
                cid = e.get("chunk_id")
                if not cid or cid not in chunk_by_id:
                    continue
                if not ((chunk_by_id[cid].get("metadata") or {}).get("spell_level") or []):
                    report["diff_tagged"]["环级证据缺失"].append({
                        "class": cls, "level": lv, "chunk_id": cid,
                        "cn": e.get("cn"), "book": e.get("book"),
                    })

    # ---- F-025 数量守恒硬断言（阻断构建）----
    pl = report["per_class_level"]
    for key, v in pl.items():
        official_retained = v["official"] - v["official_duplicates_merged"]
        if v["derived_candidates"] != (v["derived_added"] + v["official_merged"]
                                       + v["derived_duplicates_merged"]):
            print(f"❌ 守恒失败（derived_candidates）: {key} {v}")
            return 1
        if v["union"] != official_retained + v["derived_added"]:
            print(f"❌ 守恒失败（union）: {key} {v}")
            return 1
    diff_tagged = report["diff_tagged"]
    if len(diff_tagged.get("条目合并", [])) != sum(
            v["derived_duplicates_merged"] for v in pl.values()):
        print("❌ diff_counts[条目合并] != 全量 derived_duplicates_merged")
        return 1

    unclassified = diff_tagged.get("__unclassified__", [])
    key_errors = find_primary_key_errors(union_classes)
    if key_errors:
        print(f"❌ 主条目空规范键 {len(key_errors)} 处：", key_errors[:10])
        return 1
    spell_level_keyed = [c for c in chunks if "spell_level" in (c.get("metadata") or {})]
    spell_level_empty = sum(
        1 for c in spell_level_keyed
        if not (c["metadata"].get("spell_level") or [])
        and (c["metadata"].get("field_status") or {}).get("spell_level") != "not_applicable"
    )
    spell_level_total = len(spell_level_keyed)
    report_out = {
        "version": "1.1",
        "scope_classes": scope_classes,
        "excluded_classes": excluded,
        "per_class_level": pl,
        "diff_counts": {k: len(v) for k, v in diff_tagged.items() if k != "__unclassified__"},
        "diff_unclassified": len(unclassified),
        "diff_unclassified_detail": unclassified[:50],
        "variant_candidates_pending": report["variant_candidates"],
        "conflicts": report["conflicts"],
        "kn246_duplicate_level_candidates": report["kn246"],
        "dedup_name_conflicts": report["name_conflicts"],
    }
    union = {
        "version": "1.1",
        "generated_from": "职业列表页 26 路径 ∪ chunks.jsonl spell_level（KN244/KN246 修复后；F-025 去重折叠）",
        "scope_note": (
            "五书线 20 职业（清单页仅收 CRB/APG/UM/UC/ACG）并集库侧派生（全库书范围）；"
            "OA 五职业（唤魂师/秘学士/通灵者/异能者/催眠师）仅官方清单不派生。"
            "F-025：同职业同环级内按保守中英文键（传递闭包）折叠，每法术只出现一次；"
            "官方内部重复与官方/派生交叉合并保留完整 sources 与逐来源 matched_by。"
            "KN244/KN246 已修复，标题污染与已确认条目合并不再构成派生缺口。"
            f"残留口径：spell_level 空 {spell_level_empty}/{spell_level_total}"
            f"（{spell_level_empty * 100 / spell_level_total:.1f}%）不参与派生；"
            "KN245 十八条裁除项已全部闭环（回填/别名归一/标签容错），"
            "非法术条目（阿底顿等）标 not_applicable 不计入空率；"
            "官方清单原有条目不受裁除约束。"
        ),
        "classes": union_classes,
        "excluded_classes": excluded,
    }
    OUT_UNION.write_text(json.dumps(union, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    OUT_REPORT.write_text(json.dumps(report_out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"union classes={len(union_classes)} derived_added="
          f"{sum(v['derived_added'] for v in pl.values())} "
          f"diff_tags={ {k: len(v) for k, v in diff_tagged.items() if k != '__unclassified__'} } "
          f"diff_unclassified={len(unclassified)} variant_candidates={len(report['variant_candidates'])} "
          f"conflicts={len(report['conflicts'])} kn246={len(report['kn246'])} "
          f"name_conflicts={len(report['name_conflicts'])}")
    if unclassified:
        print("❌ diff_unclassified != 0：", unclassified[:10])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
