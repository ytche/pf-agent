#!/usr/bin/env python3
"""专长模块 Prepare Phase 机检脚本（k3 侧配套，与执行模型的语义勘探互补）。

产出两份：
1. machine_scan.jsonl + scan_report.md —— 190 个源文件的五合一机检
   （链接陷阱/断行英文名/〔〕类型标记/图片行/◎引用/表格块/标题候选/字段标签）
2. audit_baseline.jsonl —— page_202 全专长列表解析（专长名中英+类型+来源书），
   供召回验收对账与 feat_type 枚举权威来源。

用法：cd pf_data/phase1 && python3 vectorizer/exploration/专长/prepare_scan.py
"""
import json
import os
import re
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SRC = os.path.join(ROOT, "pf_rules_md_organized")
OUT = os.path.dirname(__file__)
MANIFEST = os.path.join(OUT, "prepare_batches.json")
PAGE_202 = os.path.join(SRC, "专长", "page_202.md")

OFFICIAL_TAGS = ["战斗", "重击", "勇毅", "造物", "演武", "超魔", "派头", "流派", "故事", "团队"]

RE_BROKEN_EN = re.compile(r"\*\*[^*]*（[A-Za-z][^）)]*$")          # 加粗标题行括号未闭合 → 断行英文名
RE_TITLE_CAND = re.compile(r"^\s*\*\*[^*]+（[^（）]*）[^*]*\*\*")   # **中文（English）** 标题候选
RE_TYPE_TAG = re.compile(r"〔([^〕]+)〕")
RE_IMG = re.compile(r"!\[")
RE_TABLE_SEP = re.compile(r"^\|[\s:|-]+\|")
RE_TABLE_ROW = re.compile(r"^\|")
RE_TRANSLATOR = re.compile(r"译者")
FIELD_LABELS = ["先决条件", "专长效果", "通常状况", "特殊", "注意"]


def read_logical_lines(path):
    """按 CR/CRLF/LF 全部切分后重组：跨行表格行（以 | 开头但不以 | 结尾）
    合并为一条逻辑行；非表格行保持碎片形态——断行英文名正是要检测的陷阱，
    不能重组掉。返回 (逻辑行列表, 裸CR数)。已验证本语料无 '|\\r' 紧邻，
    "以 | 结尾"作为表格行闭合条件是安全的。"""
    raw = open(path, encoding="utf-8", newline="").read()   # newline="" 保留原始换行符：
    bare_cr = len(re.findall(r"\r(?!\n)", raw))             # 文本模式会把 \r 静默翻译成 \n，裸CR就数不到了
    frags = re.split(r"\r\n|\r|\n", raw)
    lines, pending = [], None
    for frag in frags:
        if pending is not None:
            pending += " " + frag.strip(" \t")   # 只剥 ASCII 空白：str.strip() 会连　一起剥掉，链式深度就丢了
            if frag.rstrip(" \t").endswith("|"):
                lines.append(pending)
                pending = None
            continue
        s = frag.strip(" \t")
        if s.startswith("|") and not s.endswith("|"):
            pending = s
        else:
            lines.append(frag)
    if pending is not None:
        lines.append(pending)
    return lines, bare_cr


def collect_files():
    """manifest 17 批 + 机检除外项 page_202，全集 190 文件。"""
    with open(MANIFEST, encoding="utf-8") as f:
        batches = json.load(f)
    files = [os.path.join(ROOT, rel) for b in batches for rel in b["files"]]
    files.append(PAGE_202)
    return files


def scan_file(path):
    lines, bare_cr = read_logical_lines(path)
    rec = {
        "file": os.path.relpath(path, SRC),
        "size_kb": round(os.path.getsize(path) / 1024, 1),
        "lines": len(lines),
        "bare_cr": bare_cr,
        "link_count": 0,
        "broken_en_count": 0,
        "broken_en_lines": [],
        "type_tags": Counter(),
        "image_lines": 0,
        "circle_quote_count": 0,
        "table_blocks": 0,
        "table_rows": 0,
        "title_candidates": 0,
        "field_labels": Counter(),
        "translator_lines": 0,
    }
    for i, ln in enumerate(lines, 1):
        rec["link_count"] += ln.count("](http")
        rec["circle_quote_count"] += ln.count("◎")
        if RE_IMG.search(ln):
            rec["image_lines"] += 1
        if RE_TABLE_SEP.match(ln):
            rec["table_blocks"] += 1
        if RE_TABLE_ROW.match(ln):
            rec["table_rows"] += 1
        if RE_TRANSLATOR.search(ln):
            rec["translator_lines"] += 1
        if RE_BROKEN_EN.search(ln):
            rec["broken_en_count"] += 1
            if len(rec["broken_en_lines"]) < 3:
                rec["broken_en_lines"].append(i)
        if RE_TITLE_CAND.match(ln):
            rec["title_candidates"] += 1
        for t in RE_TYPE_TAG.findall(ln):
            rec["type_tags"][t] += 1
        for label in FIELD_LABELS:
            if f"**{label}**" in ln:
                rec["field_labels"][label] += 1
    rec["type_tags"] = dict(rec["type_tags"])
    rec["field_labels"] = dict(rec["field_labels"])
    return rec


def write_scan_report(recs):
    total = Counter()
    for r in recs:
        for k in ("link_count", "broken_en_count", "image_lines", "circle_quote_count",
                  "table_blocks", "table_rows", "title_candidates", "translator_lines", "bare_cr"):
            total[k] += r[k]

    tag_dist = Counter()
    for r in recs:
        tag_dist.update(r["type_tags"])

    def top(key, n=10, nonzero=True):
        rows = sorted(recs, key=lambda r: r[key], reverse=True)
        return [(r["file"], r[key]) for r in rows[:n] if r[key] > 0 or not nonzero]

    out = []
    out.append("# 专长模块 Prepare Phase 机检报告\n")
    out.append(f"- 文件数：{len(recs)}（含机检项 page_202.md）")
    out.append(f"- 链接 `](http` 总数：{total['link_count']}（KN023 同型风险）")
    out.append(f"- 断行英文名行：{total['broken_en_count']}")
    out.append(f"- 图片行：{total['image_lines']}（PFS 图标候选）")
    out.append(f"- ◎ 引用：{total['circle_quote_count']}（KN022 同型格式）")
    out.append(f"- 表格块：{total['table_blocks']}，表格行：{total['table_rows']}")
    out.append(f"- 标题候选（`**中文（EN）**` 完整单行）：{total['title_candidates']}")
    out.append(f"- 译者行：{total['translator_lines']}")
    out.append(f"- 裸 CR 换行符：{total['bare_cr']}（CHM 转换残留，28 个文件；逻辑行已重组，执行方直接用 splitlines() 会读出行内断裂）\n")

    out.append("## 〔〕类型标记分布（对照官方 10 类）\n")
    out.append("| 标记 | 次数 | 官方 |")
    out.append("| --- | --- | --- |")
    for tag, c in tag_dist.most_common():
        out.append(f"| {tag} | {c} | {'✓' if tag in OFFICIAL_TAGS else '✗ 非官方'} |")

    for title, key in [("链接 TOP10（KN023 风险）", "link_count"),
                       ("断行英文名 TOP10", "broken_en_count"),
                       ("裸 CR TOP10（行内断裂）", "bare_cr"),
                       ("标题候选 TOP10（对账基准）", "title_candidates"),
                       ("表格行 TOP10", "table_rows")]:
        out.append(f"\n## {title}\n")
        out.append("| 文件 | 数量 |")
        out.append("| --- | --- |")
        for f, c in top(key):
            out.append(f"| {f} | {c} |")

    suspicious = [r for r in recs
                  if r["title_candidates"] == 0 and sum(r["field_labels"].values()) > 0]
    out.append("\n## 可疑文件：0 标题候选但有字段标签（标题形态可能全部断行）\n")
    out.append("| 文件 | 字段标签数 | 断行英文名行 |")
    out.append("| --- | --- | --- |")
    for r in suspicious:
        out.append(f"| {r['file']} | {sum(r['field_labels'].values())} | {r['broken_en_count']} |")

    with open(os.path.join(OUT, "scan_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


# ---------- Part B: page_202 全专长列表解析 → audit_baseline.jsonl ----------

RE_SECTION = re.compile(r"\*\*([^*（）]{1,20}专长)（")
RE_CJK = re.compile(r"[一-鿿]")


def split_name(cell):
    """名单元格 → (英文名, 中文名, 链式深度)。

    三种形态：英文在前（`Dented Helm 　裂盔护体`，　数=链式深度）、
    中文在前（`引导力刃  Channeling Force`）、纯英文/纯中文。
    不用字符类正则切分——英文名含 ! & , ( ) 等符号，位置法更稳。"""
    cell = cell.strip(" \t")
    if not cell:
        return "", "", 0
    m = RE_CJK.search(cell)
    if not m:
        return cell, "", 0                      # 纯英文（漏译或双语分行）
    if m.start() == 0:
        me = re.search(r"[A-Za-z]", cell)       # 中文在前：英文段在中文段后
        if me:
            return cell[me.start():].strip(" \t"), cell[:me.start()].strip(" \t"), 0
        return "", cell, 0                      # 纯中文
    depth = 0                                   # 英文在前：紧贴中文名前的　数=链式深度
    k = m.start() - 1
    while k >= 0 and cell[k] == "　":
        depth += 1
        k -= 1
    en = cell[:k + 1].strip(" \t")
    zh = cell[m.start():].strip(" \t")
    return en, zh, depth


def parse_page_202():
    lines, _ = read_logical_lines(PAGE_202)

    section = None
    header = None          # 当前表列名
    rows = []
    occurrence = Counter() # name_zh 出现次数（类表允许多处列出）

    def emit(line_no, cells, anomaly=False):
        nonlocal header
        if header is None:
            return
        name_idx = header.index("专长名称") if "专长名称" in header else 0
        if len(cells) == len(header) - 1 and name_idx > 0:
            cells = [""] + cells          # 缺首列（种族/职业等分组列）
        while len(cells) < len(header):
            cells.append("")              # 尾部 类型/出处 列缺失
        if len(cells) != len(header):
            rows.append({"line_no": line_no, "section": section, "anomaly": True,
                         "raw_cells": cells})
            return
        rec = dict(zip(header, cells))
        name_en, name_zh, depth = split_name(cells[name_idx])
        key = name_zh or name_en
        occurrence[key] += 1
        rows.append({
            "line_no": line_no,
            "section": section,
            "group": cells[0] if name_idx > 0 else "",
            "name_zh": name_zh,
            "name_en": name_en,
            "chain_depth": depth,
            "feat_type": rec.get("类型", "").strip(" \t"),
            "source_book": rec.get("出处", "").strip(" \t"),
            "occurrence": occurrence[key],
            "anomaly": anomaly,
        })

    in_table = False
    for i, ln in enumerate(lines, 1):
        sm = RE_SECTION.search(ln)
        if sm:
            section = sm.group(1)
        if RE_TABLE_ROW.match(ln):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if RE_TABLE_SEP.match(ln):
                in_table = True
                continue
            if "先决条件" in cells and "专长效果" in cells:
                header = cells            # 表头行：首列标签各小节不同（专长名称/重击专长/施法专长…），
                in_table = True           # 以不变列 先决条件+专长效果 识别；分隔行可选（勇毅专长表就
                continue                  # 没有 |---| 分隔行），表头即视为表开始
            if not in_table:
                continue                  # 游离表格行，无表头上下文
            emit(i, cells)
        else:
            in_table = False
            header = None

    with open(os.path.join(OUT, "audit_baseline.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows


def main():
    files = collect_files()
    recs = [scan_file(p) for p in files]
    with open(os.path.join(OUT, "machine_scan.jsonl"), "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    write_scan_report(recs)

    rows = parse_page_202()
    n_anomaly = sum(1 for r in rows if r.get("anomaly"))
    uniq = len({r.get("name_zh") or r.get("name_en") for r in rows if not r.get("anomaly")})
    print(f"机检完成：{len(recs)} 文件 → machine_scan.jsonl + scan_report.md")
    print(f"类表解析：{len(rows)} 行（去重后专长 {uniq} 个，异常行 {n_anomaly}）→ audit_baseline.jsonl")


if __name__ == "__main__":
    main()
