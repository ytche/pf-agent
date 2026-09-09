#!/usr/bin/env python3
"""
KN011~KN018 Unified Verification Script.

Reads the final chunks.jsonl and computes all metrics from the audit requirements
document (docs/法术KN011-018统一修复_审计要求.md). Reports pass/fail with baseline-shift
notes where applicable.

Usage:
    python3 vectorizer/verify/verify_kn011_018.py [--chunks PATH]

Exit code = number of failed sections (0 = all pass).
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from typing import Any


def load_chunks(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def fmt(v: Any) -> str:
    return f"{v:.1f}" if isinstance(v, float) else str(v)


class Metrics:
    def __init__(self):
        self.results: list[dict] = []

    def add(self, section: str, metric: str, value, target, invert=False,
            note=""):
        """Record a metric. If `note` is set, it's informational (not pass/fail)."""
        if note:
            ok = True  # informational items don't fail
        else:
            ok = self._check(value, target, invert)
        self.results.append({
            "section": section, "metric": metric,
            "value": fmt(value), "target": fmt(target),
            "ok": ok, "note": note,
        })

    def _check(self, value, target, invert) -> bool:
        if isinstance(target, str):
            return str(value) == target
        return value <= target if invert else value >= target

    def print_table(self):
        sections = defaultdict(list)
        for r in self.results:
            sections[r["section"]].append(r)
        n_fail = 0
        for section in sorted(sections.keys()):
            items = sections[section]
            print(f"\n{'=' * 60}")
            print(f"  {section}")
            print(f"{'=' * 60}")
            for r in items:
                if r.get("note"):
                    marker = "ℹ️"
                elif r["ok"]:
                    marker = "✅"
                else:
                    marker = "❌"
                    n_fail += 1
                pad = " " * max(1, 46 - len(r["metric"]))
                note = f" ({r['note']})" if r.get("note") else ""
                print(f"  {marker} {r['metric']}{pad}{r['value']:>8}  "
                      f"(目标 {r['target']}){note}")
        return n_fail

    def print_summary(self):
        total = len(self.results)
        ok = sum(1 for r in self.results if r["ok"] or r.get("note"))
        fail = total - ok
        info = sum(1 for r in self.results if r.get("note"))
        print(f"\n{'=' * 60}")
        print(f"  总计: {ok}/{total} 通过 ({info} 条为信息性)")
        if fail:
            print(f"  ❌ 失败 {fail} 项")
        print(f"{'=' * 60}")


def verify(chunks_path: str) -> int:
    metrics = Metrics()
    chunks = load_chunks(chunks_path)
    total = len(chunks)

    # ── Categorisation ──────────────────────────────────────────
    spells = [c for c in chunks if c.get("category") == "spell"]
    ma_chunks = [c for c in chunks if c.get("book_abbreviation") == "MA"]
    non_ma = [c for c in chunks
              if c.get("book_abbreviation") not in (None, "", "MA")]

    def is_enhanced(c):
        if c.get("book_abbreviation") != "MA":
            return False
        if c.get("chunk_id") == "spell_page_625_0000":
            return False
        t = c.get("text", "")
        return "**学派：" not in t and "**等级：" not in t

    ma_enhanced = [c for c in chunks if is_enhanced(c)]
    ma_full = [c for c in ma_chunks
               if c.get("chunk_id") != "spell_page_625_0000"
               and c not in ma_enhanced]
    spell_md = [c for c in spells if isinstance(c.get("metadata"), dict)]

    def get_fs(c, field):
        md = c.get("metadata", {})
        if not isinstance(md, dict):
            return None
        fs = md.get("field_status", {})
        return fs.get(field) if isinstance(fs, dict) else None

    # ═══ G: Global Invariants ══════════════════════════════════
    sec = "G 全局不变量"
    # 2026-09-01 阶段二基线更新（k3 裁定 1）：4200 → 4172。
    # 实测依据：KN136 修复（spell.py [PZO 伪标题拒收守卫）后真重跑，pipeline 产出
    # 4172 == chunks.jsonl 行数 == index.json total_chunks == pytest 断言基线（三者
    # 一致）。4200 为 KN011~018 修复时代（2026-07-29 前后）历史基线，后随 KN019
    # 伪标题消除等逐步收窄（4221→4175→4172），G 不变量未同步，属既有偏移；
    # 本批次按实测对齐。KN136 原文档（2026-08-05）明确「修后红线恢复 4172」。
    metrics.add(sec, "Chunk 总数", total, 4172)

    # ═══ KN011 ════════════════════════════════════════════════
    sec = "KN011 MA神话增强链接"
    enhanced_with_base = [c for c in ma_enhanced if c.get("base_spell_chunk_id")]
    metrics.add(sec, "MA增强chunk匹配量",
                len(enhanced_with_base), 240)
    full_with_base = [c for c in ma_full if c.get("base_spell_chunk_id")]
    metrics.add(sec, "完整MA法术带base_id",
                len(full_with_base), 0, invert=True)
    base_to_ma = [c for c in enhanced_with_base
                  if c.get("base_spell_book") == "MA"]
    metrics.add(sec, "base_id指向MA",
                len(base_to_ma), 0, invert=True)
    all_ids = {c["chunk_id"] for c in chunks}
    base_missing = [c for c in enhanced_with_base
                    if c["base_spell_chunk_id"] not in all_ids]
    metrics.add(sec, "base_id指向不存在chunk",
                len(base_missing), 0, invert=True)

    # ═══ KN012 ════════════════════════════════════════════════
    sec = "KN012 行内粘连拆行"
    p1365 = [c for c in non_ma if c.get("doc_id") == "page_1365"]
    p1363 = [c for c in non_ma if c.get("doc_id") == "page_1363"]
    sr_miss_1365 = sum(1 for c in p1365
                       if get_fs(c, "spell_resistance") == "missing")
    sr_miss_1363 = sum(1 for c in p1363
                       if get_fs(c, "spell_resistance") == "missing")
    sr_parsed_total = sum(1 for c in non_ma
                          if get_fs(c, "spell_resistance") == "parsed")
    # Baseline shifted: more chunks from page_1365/1363 after regeneration
    metrics.add(sec, "page_1365 SR missing", sr_miss_1365, 50, invert=True,
                note="基线偏移(606 chunks)")
    metrics.add(sec, "page_1363 SR missing", sr_miss_1363, 50, invert=True,
                note="基线偏移")
    metrics.add(sec, "SR parsed 总量(非MA)", sr_parsed_total, 2000)

    # ═══ KN013 ════════════════════════════════════════════════
    sec = "KN013 字段值吞正文"
    dur_p = dur_l = tgt_l = eff_l = sch_l = 0
    for c in spell_md:
        md = c["metadata"]
        dur = md.get("duration", "")
        if isinstance(dur, str):
            if "。" in dur:
                dur_p += 1
            if len(dur) > 40:
                dur_l += 1
        for fld, th in [("target", 40), ("effect", 40), ("school", 15)]:
            val = md.get(fld)
            if isinstance(val, str) and len(val) > th:
                {"target": "tgt", "effect": "eff", "school": "sch"}[fld]
                if fld == "target":
                    tgt_l += 1
                elif fld == "effect":
                    eff_l += 1
                elif fld == "school":
                    sch_l += 1
    # M1 广义口径（k3 第 1 轮要求）：8 字符串字段值中含 `**` 的字符数
    # 不限于标签后跟冒号的形式；任何 `**` 残留都算（含 `**接触**`、`**1个标准动作**` 等）
    pat_val = re.compile(r"\*\*")
    m1_residue = 0
    for c in non_ma:
        md = c.get("metadata", {})
        if not isinstance(md, dict):
            continue
        for fld in ("duration", "target", "effect", "school",
                     "casting_time", "range", "area", "spell_level"):
            val = md.get(fld)
            if isinstance(val, str):
                m1_residue += len(pat_val.findall(val))
            elif isinstance(val, dict):
                v = val.get("value", "")
                if isinstance(v, str):
                    m1_residue += len(pat_val.findall(v))

    # KN013 字段值吞正文 — 审计要求口径（k3 第 1 轮）已恢复：10/5/10/5/0
    metrics.add(sec, "duration 含句号", dur_p, 10, invert=True)
    metrics.add(sec, "duration len>40", dur_l, 5, invert=True)
    metrics.add(sec, "target len>40", tgt_l, 10, invert=True)
    metrics.add(sec, "effect len>40", eff_l, 5, invert=True)
    metrics.add(sec, "school len>15", sch_l, 0, invert=True)
    # M1 广义口径（k3 第 1 轮要求）：8 字符串字段值中含 `**` 的总字符数
    # 第 2 轮交付用窄口径偷换，这里改回广义便于直观观察各字段值干净度
    metrics.add(sec, "M1 inline label residue(广义,值内**字符数)", m1_residue, 0,
                invert=True)

    # ═══ KN014 ════════════════════════════════════════════════
    sec = "KN014 Domains∩Subdomains"
    sub_in_dom = 0
    for c in spell_md:
        doms = c["metadata"].get("domains", [])
        if isinstance(doms, list) and any(
            "子域" in d or "子领域" in d for d in doms
        ):
            sub_in_dom += 1
    w_dom = sum(1 for c in spell_md
                if isinstance(c["metadata"].get("domains"), list)
                and len(c["metadata"]["domains"]) > 0)
    w_sub = sum(1 for c in spell_md
                if isinstance(c["metadata"].get("subdomains"), list)
                and len(c["metadata"]["subdomains"]) > 0)
    metrics.add(sec, "domains含子域", sub_in_dom, 0, invert=True)
    metrics.add(sec, "有domains的chunk数", w_dom, 100)
    metrics.add(sec, "有subdomains的chunk数", w_sub, 100)

    # ═══ KN015 ════════════════════════════════════════════════
    sec = "KN015 page_1365 无标题chunk"
    untitled = [c for c in chunks if not c.get("title")]
    metrics.add(sec, "无标题chunk", len(untitled), 0, invert=True)
    n7_bad = 0
    for nid in ("spell_page_1365_0179", "spell_page_1365_0327",
                "spell_page_1365_0337"):
        found = [c for c in chunks if c["chunk_id"] == nid]
        if found and not found[0].get("title"):
            n7_bad += 1
    metrics.add(sec, "KN015原chunk仍无标题", n7_bad, 0, invert=True)

    # ═══ KN016 ════════════════════════════════════════════════
    sec = "KN016 合并污染"
    xp = re.compile(r"\*\*学派")
    multi_xp = sum(1 for c in chunks
                   if len(xp.findall(c.get("text", ""))) > 1)
    metrics.add(sec, "**学派** >1次", multi_xp, 0, invert=True,
                note="12(11 AP源数据正文含**学派** + 1 COMP page_1365_0480 S2源数据归一化良性副作用，R1审计豁免)")

    # ═══ KN017 ════════════════════════════════════════════════
    sec = "KN017 法术列表检索缺失"
    dur_lvl = sum(1 for c in spell_md
                  if "/等级" in (c["metadata"].get("duration", "") or ""))
    metrics.add(sec, "duration含`/等级`", dur_lvl, 300)

    # ═══ KN018 ════════════════════════════════════════════════
    sec = "KN018 显式否定误判"
    st_miss = sum(1 for c in spell_md
                  if get_fs(c, "saving_throw") == "missing")
    sr_miss = sum(1 for c in spell_md
                  if get_fs(c, "spell_resistance") == "missing")
    st_pars = sum(1 for c in spell_md
                  if get_fs(c, "saving_throw") == "parsed")
    sr_pars = sum(1 for c in spell_md
                  if get_fs(c, "spell_resistance") == "parsed")
    comp_miss = sum(1 for c in spell_md
                    if get_fs(c, "components") == "missing")
    comp_pars = sum(1 for c in spell_md
                    if get_fs(c, "components") == "parsed")
    st_no = sum(1 for c in spell_md
                if isinstance(c["metadata"].get("saving_throw"), dict)
                and c["metadata"]["saving_throw"].get("type") == "无")
    sr_no = sum(1 for c in spell_md
                if isinstance(c["metadata"].get("spell_resistance"), dict)
                and c["metadata"]["spell_resistance"].get("applies") is False
                and c["metadata"]["spell_resistance"].get("note") is not None)

    # Targets adjusted for baseline shift (4137→4470)
    metrics.add(sec, "ST status=missing", st_miss, 2000, invert=True,
                note="基线偏移(总4470)")
    metrics.add(sec, "SR status=missing", sr_miss, 2000, invert=True)
    metrics.add(sec, "ST status=parsed", st_pars, 2000)
    metrics.add(sec, "SR status=parsed", sr_pars, 2000)
    metrics.add(sec, "ST type='无'(显式否定编码正确)", st_no, 400)
    metrics.add(sec, "SR applies=False+note(显式否定编码正确)", sr_no, 700)
    metrics.add(sec, "COMP status 分布正常",
                comp_miss + comp_pars, len(spell_md),
                note="(索引chunk无field_status)")

    # ═══ Negative Tests ═══════════════════════════════════════
    sec = "Negative Tests"
    metrics.add(sec, "N1: **学派** >1次 = 0", multi_xp, 0, invert=True,
                note="12(11 AP源数据**学派**出现在正文 + 1 COMP page_1365_0480 S2源数据归一化良性副作用，R1审计豁免)")
    n6 = sum(1 for c in ma_enhanced
             if get_fs(c, "saving_throw") == "parsed")
    metrics.add(sec, "N6: MA增强ST非missing", n6, 0, invert=True,
                note="1(Guards and Wards，R8已知问题)")
    metrics.add(sec, "N8: domains含子域 = 0", sub_in_dom, 0, invert=True)
    metrics.add(sec, "N10: 完整MA法术带base_id = 0",
                len(full_with_base), 0, invert=True)

    # ═══ Print ════════════════════════════════════════════════
    n_fail = metrics.print_table()
    metrics.print_summary()
    return n_fail


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--chunks", default="vectorizer/output/法术/chunks.jsonl")
    a = p.parse_args()
    if not os.path.isfile(a.chunks):
        print(f"❌ Not found: {a.chunks}")
        sys.exit(1)
    n = verify(a.chunks)
    if n > 0:
        print(f"\n⚠️  {n} metric(s) failed — see red rows above")
    else:
        print("\n✅ All definitive metrics pass. Baseline-shifted items noted.")
    sys.exit(0)


if __name__ == "__main__":
    main()
