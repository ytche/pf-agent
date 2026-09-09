"""scan.py — Prepare 五合一机检（v2.2 决策 G 参数化公共骨架）

源自 vectorizer/exploration/专长/prepare_scan.py（专长专属，已冻结）。
骨架通用：链接陷阱/断行英文名/〔〕类型标记/图片行/◎引用/表格块/
标题候选/字段标签/译者行 + 基线表解析；类目专属配置注册于 categories.py
（scan 键），新类目注册即复用，禁止在脚本里硬编码类目词。

基线表解析两模式：
  feat_table    —— 专长 page_202 全专长列表（表头含「先决条件+专长效果」）
  race_overview —— 种族 page_10 概述总表（双表头：6 列调整子列名 + 名称行；
                  数据行种族名格后 1~6 格为属性调整，尾 4 列固定为
                  生物类型/体型/速度/感官，合并调整格（任一属性+2）自然兼容）

用法：python3 -m vectorizer.prepare.scan --category <类目>
产出（写 exploration/<类目>/）：
  machine_scan.jsonl + scan_report.md —— 源文件五合一机检
  audit_baseline.jsonl —— 基线表解析（供召回验收对账与枚举权威来源）
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

from vectorizer.prepare.categories import get

ROOT = Path(__file__).resolve().parent.parent.parent      # phase1 根
SRC = ROOT / "pf_rules_md_organized"
EXPLORATION = Path(__file__).resolve().parent.parent / "exploration"

RE_BROKEN_EN = re.compile(r"\*\*[^*]*（[A-Za-z][^）)]*$")          # 加粗标题行括号未闭合 → 断行英文名
RE_TITLE_CAND = re.compile(r"^\s*\*\*[^*]+（[^（）]*）[^*]*\*\*")   # **中文（English）** 标题候选
RE_TYPE_TAG = re.compile(r"〔([^〕]+)〕")
RE_IMG = re.compile(r"!\[")
RE_TABLE_SEP = re.compile(r"^\|[\s:|-]+\|")
RE_TABLE_ROW = re.compile(r"^\|")
RE_TRANSLATOR = re.compile(r"译者")

# 种族名格：中文名（English）形态（分组列可能为空，按格位置识别）
RE_RACE_NAME = re.compile(r"[一-鿿]+（[A-Za-z][^）]*）")
RE_SECTION = re.compile(r"\*\*([^*（）]{1,20}专长)（")
RE_CJK = re.compile(r"[一-鿿]")


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


def collect_files(scan_cfg):
    """按类目收集策略展开源文件清单：
    manifest —— 专长 17 批 prepare_batches.json + extra_files（page_202）
    glob     —— source_dir 递归，排除 exclude_dirs（如种族构建）"""
    strategy = scan_cfg.get("collect", "glob")
    if strategy == "manifest":
        with open(ROOT / scan_cfg["manifest"], encoding="utf-8") as f:
            batches = json.load(f)
        files = [ROOT / rel for b in batches for rel in b["files"]]
        for rel in scan_cfg.get("extra_files", []):
            files.append(ROOT / rel)
        return files
    files = []
    src = ROOT / scan_cfg["source_dir"]
    exclude = tuple(scan_cfg.get("exclude_dirs", []))
    for root, dirs, names in os.walk(src):
        dirs[:] = [d for d in dirs if d not in exclude]
        for n in sorted(names):
            if n.endswith(".md"):
                files.append(Path(root) / n)
    return sorted(files)


def scan_file(path, scan_cfg):
    lines, bare_cr = read_logical_lines(path)
    field_labels = scan_cfg.get("field_labels", [])
    rec = {
        "file": str(path.relative_to(SRC)),
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
        for label in field_labels:
            if f"**{label}**" in ln:
                rec["field_labels"][label] += 1
    rec["type_tags"] = dict(rec["type_tags"])
    rec["field_labels"] = dict(rec["field_labels"])
    return rec


def write_scan_report(recs, scan_cfg, out_dir):
    total = Counter()
    for r in recs:
        for k in ("link_count", "broken_en_count", "image_lines", "circle_quote_count",
                  "table_blocks", "table_rows", "title_candidates", "translator_lines", "bare_cr"):
            total[k] += r[k]

    tag_dist = Counter()
    for r in recs:
        tag_dist.update(r["type_tags"])
    official_tags = set(scan_cfg.get("official_tags", []))

    def top(key, n=10, nonzero=True):
        rows = sorted(recs, key=lambda r: r[key], reverse=True)
        return [(r["file"], r[key]) for r in rows[:n] if r[key] > 0 or not nonzero]

    category = scan_cfg.get("category", "?")
    out = []
    out.append(f"# {category} 模块 Prepare Phase 机检报告\n")
    out.append(f"- 文件数：{len(recs)}")
    out.append(f"- 链接 `](http` 总数：{total['link_count']}（KN023 同型风险）")
    out.append(f"- 断行英文名行：{total['broken_en_count']}")
    out.append(f"- 图片行：{total['image_lines']}（PFS 图标候选）")
    out.append(f"- ◎ 引用：{total['circle_quote_count']}（KN022 同型格式）")
    out.append(f"- 表格块：{total['table_blocks']}，表格行：{total['table_rows']}")
    out.append(f"- 标题候选（`**中文（EN）**` 完整单行）：{total['title_candidates']}")
    out.append(f"- 译者行：{total['translator_lines']}")
    out.append(f"- 裸 CR 换行符：{total['bare_cr']}（CHM 转换残留；逻辑行已重组，执行方直接用 splitlines() 会读出行内断裂）\n")

    if official_tags:
        out.append("## 〔〕类型标记分布（对照官方标记体系）\n")
    else:
        out.append("## 〔〕类型标记分布（本类目无官方标记体系，仅供参考）\n")
    out.append("| 标记 | 次数 | 官方 |")
    out.append("| --- | --- | --- |")
    for tag, c in tag_dist.most_common():
        out.append(f"| {tag} | {c} | {'✓' if tag in official_tags else '✗ 非官方'} |")

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

    with open(out_dir / "scan_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


# ---------- 基线表解析（audit_baseline） ----------

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


def parse_feat_table(path):
    """page_202 全专长列表：表头以「先决条件+专长效果」识别（首列标签各小节不同）。"""
    lines, _ = read_logical_lines(path)
    section = None
    header = None
    rows = []
    occurrence = Counter()

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
    return rows


def parse_race_overview(path):
    """page_10 种族概述总表：双表头（6 列调整子列名 + 名称行）。
    数据行 = [分组?, 种族名（EN）, 调整 1~6 格, 生物类型, 体型, 速度, 感官]。
    种族名格按「中文（EN）」形态定位且**名后至少 4 格**（合并调整格
    「任一属性+2」自然兼容；后半页职业变体表行名后仅 2~3 格，自动排除）。
    分组从行首（核心种族/常见种族/…）或上行继承。"""
    lines, _ = read_logical_lines(path)
    rows = []
    group = ""
    for i, ln in enumerate(lines, 1):
        if not RE_TABLE_ROW.match(ln) or RE_TABLE_SEP.match(ln):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        # 表头2：6 列属性调整子列名（力量/敏捷/体质/智力/感知/魅力）→ 跳过
        if len(cells) == 6 and all(c in ("力量", "敏捷", "体质", "智力", "感知", "魅力") for c in cells):
            continue
        # 表头1：列名行（种族/种族属性调整/生物类型/…）→ 跳过
        if "种族" in cells and "生物类型" in cells:
            continue
        # 种族名格定位：中文（EN）形态，且名后至少 4 格（调整1~6 + 尾4列）
        name_idx = None
        for j, c in enumerate(cells):
            if RE_RACE_NAME.search(c) and len(cells) - j - 1 >= 4:
                name_idx = j
                break
        if name_idx is None:
            continue                          # 职业变体表/统计表/杂行
        if cells[0] and not RE_RACE_NAME.search(cells[0]):
            group = cells[0]                  # 行首分组列（核心种族/常见种族/…）
        # 名格切分：种族名为配对括号「中文（EN）」形态（split_name 面向专长名格，
        # 会把括号误切进英文段，如 矮人（ / Dwarves））
        m = re.match(r"([一-鿿]+)（([^）]*)）", cells[name_idx])
        if m:
            name_zh, name_en = m.group(1), m.group(2).strip(" \t")
        else:
            name_en, name_zh, _ = split_name(cells[name_idx])
        tail = cells[name_idx + 1:]
        rows.append({
            "line_no": i,
            "group": group,
            "name_zh": name_zh,
            "name_en": name_en,
            "ability_adj": tail[:-4],         # 1~6 格（合并格自然兼容）
            "bio_type": tail[-4],
            "size": tail[-3],
            "speed": tail[-2],
            "senses": tail[-1],
            "anomaly": False,
        })
    return rows


def parse_baseline(scan_cfg, out_dir):
    """基线表解析 → audit_baseline.jsonl；无基线配置则跳过。"""
    baseline = scan_cfg.get("baseline")
    if not baseline:
        return []
    path = ROOT / baseline["file"]
    mode = baseline.get("mode", "feat_table")
    rows = parse_feat_table(path) if mode == "feat_table" else parse_race_overview(path)
    with open(out_dir / "audit_baseline.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Prepare 五合一机检（类目注册于 categories.py）")
    parser.add_argument("--category", required=True, help="类目（feat/race…）")
    args = parser.parse_args(argv)

    cfg = get(args.category)
    scan_cfg = cfg.get("scan")
    if not scan_cfg:
        sys.exit(f"❌ 类目 {args.category!r} 未注册 scan 配置（categories.py）")
    scan_cfg = dict(scan_cfg, category=args.category)

    out_dir = EXPLORATION / args.category
    out_dir.mkdir(parents=True, exist_ok=True)

    files = collect_files(scan_cfg)
    recs = [scan_file(p, scan_cfg) for p in files]
    with open(out_dir / "machine_scan.jsonl", "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    write_scan_report(recs, scan_cfg, out_dir)

    rows = parse_baseline(scan_cfg, out_dir)
    n_anomaly = sum(1 for r in rows if r.get("anomaly"))
    uniq = len({r.get("name_zh") or r.get("name_en") for r in rows if not r.get("anomaly")})
    print(f"机检完成：{len(recs)} 文件 → {out_dir}/machine_scan.jsonl + scan_report.md")
    if rows:
        print(f"基线表解析：{len(rows)} 行（去重后 {uniq} 个，异常行 {n_anomaly}）→ audit_baseline.jsonl")


if __name__ == "__main__":
    main()
