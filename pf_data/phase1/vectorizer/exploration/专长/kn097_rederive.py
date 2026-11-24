#!/usr/bin/env python3
"""KN097 一次性重推导：按当前源文机械重算 estimated_count / count_basis /
doc_role / field_labels_seen，并输出新旧 diff。

计数口径（可复现）：
  - 条目标题 = 行级标题（#/## 标题、行首 ** 加粗、或纯文本「中文（English）」行）
    且其后（到下一个标题前，最多 25 行）出现字段标签（先决条件/专长效果/好处/
    效果/前提/需求/描述/类型/目标/完成奖励 等）；
  - 表格条目 = 表头含 先决条件+专长效果 的表格中，首列为「中文名 + 英文名」的行；
  - 同一名称在源文重复出现按重复计（不合并）；跨行标题按 1 条计（续行不入账）；
  - 章节/书名标题（以「专长」结尾且无英文名的加粗行）不计。

人工复核覆盖（MANUAL）：机械规则无法识别内联/无字段标签的少量写法，
按下列可核对证据人工计数，逐条写进 count_basis。

用法：
  python3 vectorizer/exploration/专长/kn097_rederive.py --apply
  python3 vectorizer/exploration/专长/kn097_rederive.py --dry-run
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

PHASE1 = Path(__file__).resolve().parents[3]
BASE = PHASE1 / "pf_rules_md_organized"
OUT = Path(__file__).resolve().parent
BATCHES = range(1, 18)

CJK = re.compile(r"[\u4e00-\u9fff]")
SENT = re.compile(r"[。！？；]")
LABEL_LINE = re.compile(
    r"^\s*\*\*(先决条件|专长效果|通常状况|通常情况|特殊情况|特殊说明|特殊|注意|译者|出自|出处|来源|"
    r"好处|效果|类型|描述|要求|需求|前提|前置|正常|专长目标|即时收益|完成收益|推荐背景|专长好处|"
    r"价格|重量|灵光|施法者等级|制造条件|制造成本|目标|完成奖励|条件|资源)(?:[：:]?\*\*|[：:]|\*\*[：:]|[：:])")
FLD_ANY = re.compile(
    r"(先决条件|专长效果|通常状况|特殊情况|特殊说明|好处|效果|前提|前置|需求|专长目标|完成奖励|条件|资源)(?:\*\*)?[：:]")
NOISE = re.compile(r"^(>|<!--|\||\[|来源|译者)")
RE_IMG = re.compile(r"^!\[\[[^\]]*\]\]\([^)]*\)\s*")

LABELS = ("先决条件", "专长效果", "通常状况", "通常情况", "效果", "好处", "特殊", "特殊说明", "注意",
          "描述", "需求", "前提", "目标", "完成奖励", "正常情况", "通常效果", "特别说明")


def strip_md(s):
    return re.sub(r"\*+", "", s)


def title_part(line):
    """加粗标题的标题段（到第一个加粗闭合为止）。"""
    s = line.strip()
    s = RE_IMG.sub("", s)
    if s.startswith("## ") or re.match(r"^#\s", s):
        return s
    if not s.startswith("**"):
        return s
    runs = [(m.start(), m.end()) for m in re.finditer(r"\*{2,}", s)]
    if len(runs) < 2:
        return s
    end = runs[1][1]
    rest = s[end:]
    if rest and re.match(r"[\u4e00-\u9fff]", rest) and len(rest) > 15:
        return s[:end]
    last = runs[-1][1]
    mid = s[end:runs[-1][0]]
    if len(mid) < 40 and "。" not in mid:
        return s[:last]
    return s[:end]


def is_book_header(s):
    t = strip_md(s).strip("# ").strip()
    return t.endswith("专长") and len(t) <= 30


def english_title(t):
    return bool(re.search(r"[（(][^）)]*[A-Za-z]", t)) or "〔" in t or bool(re.search(r"[（(][^）)]*专长[）)]", t))


def find_titles(lines):
    titles, skip = [], set()
    for i, l in enumerate(lines):
        if i in skip:
            continue
        s = l.strip()
        if not s or s.startswith("|") or NOISE.match(s):
            continue
        if LABEL_LINE.match(s) or not CJK.search(s):
            continue
        if re.match(r"^[\s　]*(先决条件|专长效果|通常状况|特殊情况|特殊说明|好处|效果|前提|前置|需求|"
                    r"描述|类型|条件|目标|完成奖励|正常情况)(?:\*\*)?[：:]", s):
            continue
        if s.startswith("*") and not s.startswith("**"):
            continue
        if re.match(r"^[a-z]", s):
            continue
        if re.match(r"^[A-Z'’][^，。]*[）)]\s*$", s) and "（" not in s:
            continue
        m_img = re.match(r"^!\[\[[^\]]*\]\]\([^)]*\)\s*(.*)$", s)
        if m_img and not m_img.group(1).strip():
            continue
        if s.startswith("## ") or re.match(r"^#\s", s):
            if not is_book_header(s) and len(strip_md(s).strip()) <= 80:
                titles.append(i)
            continue
        if s.startswith("**") or s.startswith("![[图片]]"):
            tp = title_part(s)
            t = strip_md(RE_IMG.sub("", s)).strip()
            tt = strip_md(tp).strip()
            if is_book_header(tt) or len(tt) > 90:
                continue
            if not english_title(tt) and (SENT.search(tt) or len(tt) > 40
                                           or re.match(r"^(你|如果|当|若|在|为了|所有|任何|该)", tt)):
                continue
            titles.append(i)
            if t.count("（") > t.count("）") or s.count("**") % 2 == 1:
                skip.add(i + 1)
            continue
        prev = ""
        for j in range(i - 1, -1, -1):
            if lines[j].strip():
                prev = strip_md(lines[j]).strip()
                break
        if prev.count("（") > prev.count("）") or prev.count("(") > prev.count(")"):
            continue
        # 纯文本标题
        t = strip_md(s).strip()
        if len(t) <= 60 and not SENT.search(t) and english_title(t) and re.match(r"^[^\s（(〔]", t):
            titles.append(i)
            continue
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if re.match(r"^[\u4e00-\u9fff·]{2,20}$", t) and re.match(
                r"^(描述|先决条件|前提|好处|效果|类型|专长效果)[：:]", strip_md(nxt)):
            titles.append(i)
            continue
        if re.match(r"^[\u4e00-\u9fff·]{2,12}\s*[A-Za-z][A-Za-z'’\-]*\s*$", t) and len(t) <= 40:
            nn = [strip_md(x).strip() for x in lines[i + 1:i + 4] if strip_md(x).strip()]
            if any(re.match(r"^(描述|先决条件|前提|好处|效果|类型|专长效果)[：:]", x) for x in nn[1:3]) \
                    or (len(nn) > 1 and re.match(r"^[A-Za-z]", nn[0])):
                titles.append(i)
                skip.add(i + 1)
    return titles


def table_entries(lines):
    names, header, intable = [], None, False
    for l in lines:
        s = l.strip()
        if not s.startswith("|"):
            intable, header = False, None
            continue
        if re.match(r"^\|[\s:|-]+\|", s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not intable:
            if "先决条件" in cells and ("专长效果" in cells or "效果" in cells):
                header, intable = cells, True
            continue
        if header and len(cells) >= 2:
            c0 = strip_md(cells[0]).strip()
            m = re.match(r"^([^\sA-Za-z0-9（(]{2,})\s*[A-Za-z]", c0)
            if m:
                names.append(m.group(1))
    return names


def analyze(rel):
    lines = re.split(r"\r\n|\r|\n", (BASE / rel).read_text(encoding="utf-8", newline=""))
    t = find_titles(lines)
    entries, headers = [], []
    for k, i in enumerate(t):
        s = lines[i].strip()
        cap = min(len(lines), (t[k + 1] if k + 1 < len(t) else len(lines)), i + 25)
        near = [strip_md(lines[j]).strip() for j in range(i + 1, cap) if strip_md(lines[j]).strip()]
        inline = bool(FLD_ANY.search(strip_md(s)))
        near_entry = any(FLD_ANY.search(x) or (x.startswith("*") and len(x) > 4) for x in near)
        (entries if (inline or near_entry) else headers).append(i)
    tbl = table_entries(lines)
    return entries, headers, tbl, lines


def entry_name(line):
    t = strip_md(line_part := title_part(line)).strip()
    m = re.search(r"[\u4e00-\u9fff·]{2,}[^（(〔]*", t)
    return (m.group(0).strip() if m else t[:20]).strip()


def label_counts(txt):
    t = txt.replace("**", "")
    out = {}
    for lab in LABELS:
        n = len(re.findall(lab + r"[：:]", t))
        if n:
            out[lab] = n
    return out


def doc_role(rel, n_entries, n_table, lines, txt, old_role):
    """按 5 分类判据重新判定；结构证据无法区分 detail/mixed 时沿用旧值。"""
    if n_entries == 0 and n_table == 0:
        # 结构未识别出条目（单行表格/内联段落），不改判
        return old_role
    if n_entries == 0 and n_table > 0:
        return "index_table"
    if (n_table > 0 and n_entries > 0) or "一览" in rel:
        return "aggregation"
    if old_role in ("overview", "index_table", "aggregation"):
        return "detail"
    if old_role == "detail" and n_entries == 0:
        return old_role  # 结构未识别出条目（内联/段落式），不改判
    # detail/mixed 的边界依赖人工判断，结构证据不支持改写时沿用旧值
    return old_role


# 人工复核覆盖：文件 -> (计数, 依据)
MANUAL = {
    "专长/专长16.md": (7, "7 个「描述：」条目行"),
    "专长/阵营与阵营专长.md": (9, "9 个「先决条件：10 生命骰」阵营专长条目"),
    "专长/page_668.md": (6, "6 个「效果：」内联条目（标题与正文同段）"),
    "专长/魔法战术工具箱MTT_血巫术.md": (8, "8 个「（血巫术）」标记条目"),
    "专长/魔法战术工具箱MTT_调查员与盗贼天赋.md": (12, "13 个加粗标题中 1 个为章节标题，其余 12 条"),
    "专长/水下冒险AA_专长.md": (10, "10 个加粗条目标题（旧值把跨行续行重复计入）"),
    "专长/专长22.md": (10, "10 个条目标题（旧值把跨行续行重复计入）"),
    "专长/塔尔多TEoG_专长.md": (8, "8 个「## 中文（English）」条目"),
    "专长/反派法典VC_专长.md": (12, "12 个条目标题（含 3 条贰牙系列内联条目）"),
    "专长/page_556.md": (33, "33 个「**先决条件」条目行"),
    "专长/专长5.md": (4, "4 个「英文名两行标题」条目（DIVERSE OBEDIENCE / DIVINE COMMUNION / MINOR MIRACLE / REWARD OF THE FAITHFUL）"),
    "专长/page_694.md": (5, "5 个「前置条件：」内联条目（大地魔法…青翠法术）"),
    "专长/专长43.md": (1, "1 个内联条目「天堂升华 Talmandor's Lifting 伟业」"),
    "专长/安多安ASoL_专长.md": (1, "1 个内联条目「天堂升华Talmandor's Lifting 伟业」"),
}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    apply = args.apply and not args.dry_run

    paths = {b: OUT / ("per_file_B%02d.jsonl" % b) for b in BATCHES}
    batches = {}
    recs_by_file = {}
    for b, p in paths.items():
        recs = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
        batches[b] = recs
        for r in recs:
            recs_by_file[r["file"]] = (b, r)
    diff = []
    for rel, (b, r) in recs_by_file.items():
        entries, headers, tbl, lines = analyze(rel)
        txt = "\n".join(lines)
        n_tbl = len(set(tbl))
        n = len(entries) + (0 if entries else n_tbl)
        basis = ("机械重数：识别 %d 个条目标题行" % len(entries))
        if not entries and n_tbl:
            basis = "机械重数：索引表 %d 行（表头含 先决条件+专长效果）" % n_tbl
        if rel in MANUAL:
            n, why = MANUAL[rel]
            basis = "人工复核：" + why
        names = [entry_name(lines[i]) for i in entries]
        if names and rel not in MANUAL:
            basis += "；首条「%s」末条「%s」" % (names[0], names[-1])
        basis += "；同一写法重复出现按重复计，跨行续行不计"
        new_role = doc_role(rel, len(entries) or n, n_tbl, lines, txt, r['doc_role'])
        old = {"estimated_count": r["estimated_count"], "count_basis": r["count_basis"],
               "doc_role": r["doc_role"], "field_labels_seen": r.get("field_labels_seen")}
        r["estimated_count"] = n
        r["count_basis"] = "2026-11-13 重勘探：" + basis
        r["doc_role"] = new_role
        r["field_labels_seen"] = label_counts(txt)
        if n == 0 and any(tf.get("count") for tf in r["title_forms"]):
            for tf in r["title_forms"]:
                if tf.get("count"):
                    tf["count"] = 0
                    tf["note"] = (tf.get("note") or "") + "；该形态为章节/索引结构，不计专长条目（count 置 0）"
        marker = "2026-11-13 按当前源文机械重推导 estimated_count/count_basis/doc_role/field_labels_seen"
        old_notes = r.get("notes") or ""
        parts = [p for p in old_notes.split("；") if p.strip()]
        parts = [p for p in parts if not p.startswith("2026-11-13 按当前源文机械重推导")]
        parts.append(marker)
        r["notes"] = "；".join(parts)
        diff.append({"file": rel, "batch": b, "old": old,
                     "new": {"estimated_count": n, "doc_role": new_role,
                             "field_labels_seen": r["field_labels_seen"]}})
    changed = [d for d in diff if d["old"] != d["new"]]
    print("files %d, changed %d, est old %d new %d" % (
        len(diff), len(changed), sum(d["old"]["estimated_count"] for d in diff),
        sum(d["new"]["estimated_count"] for d in diff)))
    print("doc_role changes:", sum(1 for d in diff if d["old"]["doc_role"] != d["new"]["doc_role"]))
    print("est changes:", sum(1 for d in diff if d["old"]["estimated_count"] != d["new"]["estimated_count"]))
    (OUT / "kn097_rederive_diff.json").write_text(
        json.dumps(diff, ensure_ascii=False, indent=1), encoding="utf-8")
    if apply:
        for b, p in paths.items():
            p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in batches[b]),
                         encoding="utf-8")
        print("applied")


if __name__ == "__main__":
    main()
