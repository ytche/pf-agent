#!/usr/bin/env python3
"""CHM 目录范围 vs 已处理输入 缺口排查（种族/职业/专长/法术）。

用法: python3 audit_chm_scope_gap.py
输出: docs/chm范围缺口排查_20260804.md（同时打印摘要）
"""
import json
import re
from pathlib import Path
from collections import defaultdict
from urllib.parse import unquote
from html import unescape

def norm_html(name):
    """CHM TOC 的 URL 编码/实体转义名 → md_mapping 存储名。"""
    return unescape(unquote(name)) if name else name

ROOT = Path(__file__).resolve().parent
PF_DATA = ROOT.parent
TOC_FILE = PF_DATA / "CHM_FULL_TOC_WITH_LEVELS.md"
MD_MAP = json.load(open(PF_DATA / "md_mapping.json"))
ORGANIZED = ROOT / "pf_rules_md_organized"

# ---------- 1. 解析 CHM TOC ----------
ENTRY_RE = re.compile(r"^(\s*)- (.*?)(?:\s*\(`([^`]+)`\))?\s*\[L(\d)\]\s*$")

toc_entries = []  # (level, title, html_file, path)
stack = []  # list of (level, title)
for line in open(TOC_FILE, encoding="utf-8"):
    m = ENTRY_RE.match(line.rstrip("\n"))
    if not m:
        continue
    indent, title, html, level = m.group(1), m.group(2).strip(), m.group(3), int(m.group(4))
    while stack and stack[-1][0] >= level:
        stack.pop()
    stack.append((level, title))
    path = " → ".join(t for _, t in stack)
    toc_entries.append({"level": level, "title": title, "html": norm_html(html), "path": path})

def l1_of(path):
    return path.split(" → ")[0]

# ---------- 1.5 类目注册表 ----------
# 模式 A（l1s）：CHM 指定 L1 子树对账（种族/职业/专长/法术，行为保持）
# 模式 B（l1s + extra_html + input_dirs + input_files）：跨 L1 页面集合
# （技能——CHM 技能内容散落 8 处：技能 L1 子树 + Unchained 技能与选项 +
# 巨人猎手新技能选项 + 河域子民新技能规则 + 冒险者军械库工具包 +
# 异能神秘技能解放 + 科技指南 + 官方FAQ，见 docs/技能/技能模块语义切分计划.md §1.2）
CATEGORY_SPEC = {
    "种族": {"l1s": ["种族"], "out": "docs/chm范围缺口排查_20260804.md"},
    "职业": {"l1s": ["职业"], "out": "docs/chm范围缺口排查_20260804.md"},
    "专长": {"l1s": ["专长"], "out": "docs/chm范围缺口排查_20260804.md"},
    "法术": {"l1s": ["法术"], "out": "docs/chm范围缺口排查_20260804.md"},
    "技能": {
        "l1s": ["技能"],
        # 跨 L1 补充页（职业·盗贼天赋 page_257 技能解放属职业类目，已覆盖，不纳入）
        "extra_html": ["page_647.html", "page_648.html", "page_649.html",
                       "背景技能.htm", "整合技能.htm", "分组技能.htm",
                       "新技能选项.htm", "新技能规则.htm", "工具和技能工具包.htm",
                       "page_315.html", "page_760.html", "page_837.html"],
        # pipeline 输入集 = 多目录 + 根目录孤儿页/散件 + 跨类目页
        "input_dirs": ["技能", "规则/Unchained规则/技能与选项"],
        "input_files": ["page_161.md", "page_162.md", "page_182.md", "page_1038.md",
                        "背景技能.md", "分组技能.md", "整合技能.md",
                        "新技能选项.md", "新技能规则.md",
                        "工具和技能工具包.md", "工具包.md",
                        "规则/河域子民PotR_新技能规则.md",
                        "规则/异能规则/page_315.md",
                        "科技指南/科技世界/page_760.md",
                        "官方FAQ/page_837.md"],
        "out": "docs/技能/chm范围缺口排查_技能_20260807.md",
    },
    # 装备/魔法物品：CHM L1 子树（行 687~782，武器/防具 + 货品服务 + 魔法物品 + 预设装备包）
    # 输入 = organized/装备_魔法物品/ 全量（含 9 子目录：武器_防具/货品服务/魔法物品/等）
    # + 根目录散件（形态 D，CHM 侧无对应节点，反向对账人工处理）
    # + 根目录内容页 2 个（2026-08-08 对账定性：page_234 奇物无位置核心页 305KB、
    #   page_635 成长型物品规则导言页；其余 4 个根目录壳文件豁免——page_626 0 字节空文件、
    #   page_859/1126/极限诡道 链接壳，内容已由子目录聚合覆盖）
    "装备/魔法物品": {
        "l1s": ["装备/魔法物品"],
        "input_dirs": ["装备_魔法物品"],
        "input_files": ["page_234.md", "page_635.md"],
        "out": "docs/装备/chm范围缺口排查_装备_20260808.md",
    },
    # 规则模块：4 个跨形态 L1 统一（核心规则 CRB / 规则 / 重训 / 常用速查，2026-08-09 拍板）
    # 输入 = 三个 organized 子目录全量（核心规则 CRB 含 战斗规则/ 环境/ 子目录；规则/ 13 书子目录 + 散件）
    # + 根级孤儿页（重训 page_159 + 4 个根级唯一副本总纲页 page_645/314/732/1495，
    #   2026-08-09 首轮对账定性：子目录无同 stem 且内容重叠 <6%，为 Unchained/异能/UI/腐化总纲）
    # + 第十季额外资源/战役说明 根级壳（CHM 节点唯一对应 md，含独有 BBS 导言——可用资源规则
    #   说明，子目录 10 个拆分文件无导言段，2026-08-09 实测；与装备纯链接壳 page_859/1126 不同）
    # 豁免（只证不删，装备链接壳先例）：根级 rpage_0001~0009 × 核心规则/战斗规则/、根级 page_9 ×
    #   常用速查/、根级作祟汇总 × 规则/、根级 新怪物模板 × 规则/HA规则/（MD5 全等 2026-08-09 实测）；
    #   7 个空/链接壳不纳入——page_4/414/417/528/1489 0 字节、page_237 战斗规则目录链接壳、
    #   page_967 译者说明
    "规则": {
        "l1s": ["核心规则 Core Rulebook【CRB】", "规则", "重训", "常用速查"],
        "input_dirs": ["核心规则 Core Rulebook【CRB】", "规则", "常用速查"],
        "input_files": ["page_159.md", "page_645.md", "page_314.md", "page_732.md", "page_1495.md",
                        "第十季额外资源（Season_10_Additional_Resource）.md",
                        "第十季战役说明（Season_10_Campaign_Clarifications）.md"],
        "out": "docs/规则/chm范围缺口排查_规则_20260809.md",
    },
}

# ---------- 2. html -> md 反查 ----------
html2md = {}
for md_name, info in MD_MAP.items():
    h = info.get("html_file")
    if h:
        html2md[norm_html(h)] = md_name

def stem(name):
    return Path(name).stem if name else None

# ---------- 3. 各类目已处理输入集 ----------
def load_jsonl_files(p):
    files = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            files.append(json.loads(line)["file"])
    return files

inputs = {}
# 统一口径：pipeline 实际输入 = organized 该类目输入集合全量 md
# （per_file 勘探清单仅是 Prepare 快照，不代表真实输入——page_195 不在专长
# 勘探清单却产出 412 chunks 已实证）
# 模式 A（4 类目）：organized/<类目>/ 子树全量；模式 B（技能）：
# 多目录 + 根目录孤儿页/散件 + 跨类目页（跨 L1 页面集合）
for cat, spec in CATEGORY_SPEC.items():
    fs = []
    # 缺省 [cat] = 模式 A 行为（organized/<类目>/ 子树全量，4 类目保持原状）
    for d in spec.get("input_dirs", [cat]):
        fs += [str(p.relative_to(ORGANIZED)) for p in ORGANIZED.glob(f"{d}/**/*.md")]
    for f in spec.get("input_files", []):
        p = ORGANIZED / f
        if p.exists():
            fs.append(f)
    inputs[cat] = sorted(set(fs))

input_stems = {cat: {stem(Path(f).name) for f in fs} for cat, fs in inputs.items()}

# ---------- 4. organized 全量文件定位（判断缺口文件在哪）----------
org_files = defaultdict(list)  # stem -> [relative paths]
for p in ORGANIZED.rglob("*.md"):
    org_files[p.stem].append(str(p.relative_to(ORGANIZED)))

# ---------- 5. 对比 ----------
report = {}
for cat, spec in CATEGORY_SPEC.items():
    extra = set(spec.get("extra_html", []))
    # CHM 该类目所有带 html 的叶子/节点：L1 子树 + 跨类目补充页（技能）
    pages = [e for e in toc_entries
             if e["html"] and (l1_of(e["path"]) in spec["l1s"] or e["html"] in extra)]
    rows = []
    n_ok = 0
    for e in pages:
        md_name = html2md.get(e["html"])
        md_stem = stem(md_name) if md_name else stem(e["html"])
        if md_stem and md_stem in input_stems[cat]:
            n_ok += 1
            continue
        locs = org_files.get(md_stem, []) if md_stem else []
        rows.append({
            "toc_path": e["path"],
            "html": e["html"],
            "md": md_name,
            "in_md_mapping": md_name is not None,
            "locations": locs,
        })
    report[cat] = {"chm_total": len(pages), "covered": n_ok, "gaps": rows,
                   "input_count": len(inputs[cat])}

# ---------- 6. 输出（每类目独立文件） ----------
def render_report(cat, r, out_path):
    out = ["# CHM 目录范围 vs 已处理输入 缺口排查报告", "",
           f"> 生成：{__import__('datetime').date.today().isoformat()} audit_chm_scope_gap.py（类目：{cat}）",
           "> 口径：CHM_FULL_TOC_WITH_LEVELS.md 该类目全部带 html 节点",
           "> （L1 子树 + 跨类目补充页）；",
           "> 已处理输入 = organized 该类目输入集合全量 md（pipeline 真实输入，",
           "> 非 per_file 勘探快照——page_195 不在专长勘探清单却产出 412 chunks 已实证）",
           ""]
    out.append(f"## {cat}：CHM {r['chm_total']} 页，已覆盖 {r['covered']}，缺口 {len(r['gaps'])}（输入文件 {r['input_count']}）")
    out.append("")
    if not r["gaps"]:
        out.append("无缺口。")
        out.append("")
        return "\n".join(out)
    in_cat_dir, in_root, elsewhere, no_md = [], [], [], []
    for g in r["gaps"]:
        if not g["in_md_mapping"] and not g["locations"]:
            no_md.append(g)
        elif any(x.startswith(cat + "/") for x in g["locations"]):
            in_cat_dir.append(g)  # 在类目录下却没被处理（异常）
        elif any("/" not in x for x in g["locations"]):
            in_root.append(g)
        elif g["locations"]:
            elsewhere.append(g)
        else:
            no_md.append(g)
    if in_cat_dir:
        out.append(f"### ⚠️ 在 {cat}/ 目录下但未处理（{len(in_cat_dir)}）")
        for g in in_cat_dir:
            out.append(f"- `{g['md'] or g['html']}` | {g['toc_path']} | 位置: {', '.join(g['locations'])}")
        out.append("")
    if in_root:
        out.append(f"### 文件在 organized 根目录（未纳入类目录，{len(in_root)}）")
        for g in in_root:
            out.append(f"- `{g['md'] or g['html']}` | {g['toc_path']}")
        out.append("")
    if elsewhere:
        out.append(f"### 文件在其他目录（{len(elsewhere)}）")
        for g in elsewhere:
            out.append(f"- `{g['md'] or g['html']}` | {g['toc_path']} | 位置: {', '.join(g['locations'])}")
        out.append("")
    if no_md:
        out.append(f"### md_mapping / organized 中均无对应 md（{len(no_md)}）")
        for g in no_md:
            out.append(f"- `{g['html']}` | {g['toc_path']}")
        out.append("")
    return "\n".join(out)

# 同 out 路径的类目（4 旧类目共享 20260804 合并报告）聚合到一个文件，
# 后续类目段剥掉重复的 # 主标题行，保持既有合并报告形态
from collections import OrderedDict

out_bundles = OrderedDict()
for cat, spec in CATEGORY_SPEC.items():
    r = report[cat]
    out_bundles.setdefault(ROOT / spec["out"], []).append((cat, r, spec))
for out_path, items in out_bundles.items():
    parts = []
    for i, (cat, r, spec) in enumerate(items):
        text = render_report(cat, r, out_path)
        if i > 0:
            text = text.split("\n", 1)[1]
        parts.append(text)
        print(f"{cat}: CHM {r['chm_total']} 页 / 覆盖 {r['covered']} / 缺口 {len(r['gaps'])}（输入文件 {r['input_count']}）→ {spec['out']}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n\n".join(parts), encoding="utf-8")
