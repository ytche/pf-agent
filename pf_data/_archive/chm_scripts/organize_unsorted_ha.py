#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
惧怖冒险 HA 未整理内容整理脚本（第二版）

把 pf_data/phase1/pf_rules_md/ 下属于"未整理 → 惧怖冒险HA"的条目，
按内容合并到已有分类目录的对应 MD 文件中。所有操作都在副本目录
pf_data/phase1/pf_rules_md_organized/ 上进行，原目录不动。

关键改进：
- 优先通过 md_mapping.json 的 toc_path 找到已有目标文件（如 page_1366.md、
  page_45.md、page_220.md 等），将 HA 内容追加到这些已有页面；
- 只有在目录/TOC 中确实找不到对应源文件时才新建文件。
"""

import json
import re
import shutil
from pathlib import Path
from collections import defaultdict


# 路径配置
BASE_DIR = Path(__file__).parent.resolve()
SOURCE_DIR = BASE_DIR / "phase1" / "pf_rules_md"
TARGET_DIR = BASE_DIR / "phase1" / "pf_rules_md_organized"
MAPPING_FILE = BASE_DIR / "md_mapping.json"
REPORT_FILE = BASE_DIR / "ha_reorganization_report.md"
PLAN_FILE = BASE_DIR / "ha_reorganization_plan.json"


# ---------------------------------------------------------------------------
# 数据加载与索引
# ---------------------------------------------------------------------------

def load_mapping():
    """加载 md_mapping.json。"""
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_ha_entries(mapping):
    """从 mapping 加载所有"未整理 → 惧怖冒险HA"条目。"""
    entries = []
    for md_name, info in mapping.items():
        toc_path = info.get("toc_path") or ""
        if toc_path.startswith("未整理 → 惧怖冒险HA"):
            entries.append({
                "md_name": md_name,
                "html_name": info.get("html_file", ""),
                "toc_path": toc_path,
            })
    return entries


def build_toc_index(mapping):
    """建立 toc_path -> [md_name] 的反向索引。"""
    index = defaultdict(list)
    for md_name, info in mapping.items():
        tp = info.get("toc_path") or ""
        if tp:
            index[tp].append(md_name)
    return index


# ---------------------------------------------------------------------------
# 目标文件解析器：优先找到已有文件，找不到再新建
# ---------------------------------------------------------------------------

def find_in_target(md_name):
    """在 TARGET_DIR 中按文件名查找已有 MD 文件，优先返回已分类目录中的副本。"""
    if not md_name:
        return None
    found = list(TARGET_DIR.rglob(md_name))
    if not found:
        return None

    # 如果同时存在根目录副本和分类目录副本，优先使用分类目录中的
    non_root = [p for p in found if p.parent != TARGET_DIR]
    if non_root:
        # 再优先已知的标准分类目录
        canonical_prefixes = (
            "/职业/",
            "/种族/",
            "/装备_魔法物品/",
            "/专长/",
            "/法术/",
            "/规则/",
        )
        for p in non_root:
            if any(prefix in str(p) for prefix in canonical_prefixes):
                return p
        return non_root[0]

    return found[0]


def toc_path_to_dir(toc_path):
    """把 TOC 路径转成目录层级（L1 的 '/' 转为 '_'，其余保留）。"""
    parts = [p.strip() for p in toc_path.split("→")]
    return Path(*[p.replace("/", "_") for p in parts])


def resolve_target(desired_toc_path, fallback_path=None):
    """
    根据期望的 TOC 路径，返回 TARGET_DIR 下应写入的 Path。
    优先使用 md_mapping 中登记的 md_name 在 TARGET_DIR 中已存在的文件；
    若不存在，则使用 fallback_path（或按 TOC 结构构造路径）。
    """
    md_names = TOC_INDEX.get(desired_toc_path, [])
    for md_name in md_names:
        found = find_in_target(md_name)
        if found:
            return found

    if fallback_path:
        return fallback_path

    # 没有登记且未提供 fallback：按 TOC 结构构造路径
    default_name = md_names[0] if md_names else "index.md"
    return TARGET_DIR / toc_path_to_dir(desired_toc_path) / default_name


# ---------------------------------------------------------------------------
# 文件读写工具
# ---------------------------------------------------------------------------

def read_source(md_name):
    """读取源 MD 文件内容。"""
    path = SOURCE_DIR / md_name
    return path.read_text(encoding="utf-8", errors="ignore")


def read_target(path):
    """读取目标文件内容（若不存在返回空字符串）。"""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def write_target(path, content):
    """写入目标文件，自动创建父目录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append_to_target(path, content, source_note_text=""):
    """追加内容到目标文件；若文件为空且目标是种族汇总则自动补标题。"""
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = read_target(path)

    # 若文件为空且目标看起来是种族汇总，先加标题
    if not existing and "种族特性替换汇总" in str(path):
        race_name = path.parent.name
        existing = f"{race_name}种族特性替换汇总\n\n"

    if existing and not existing.endswith("\n"):
        existing += "\n"
    new_content = existing + "\n" + content
    if source_note_text:
        new_content += "\n\n" + source_note_text + "\n"
    else:
        new_content += "\n"
    path.write_text(new_content, encoding="utf-8")


def already_contains(path, marker):
    """检查目标文件中是否已包含指定标记（用于去重）。"""
    if not path.exists():
        return False
    return marker in read_target(path)


def source_note(l3_title, page=None):
    """生成统一的来源标注。"""
    page_str = f"{page}页" if page else "页码见原书"
    return f"> 来源：惧怖冒险（Horror Adventures）HA，{page_str}，未整理 → 惧怖冒险HA → {l3_title}"


def insert_note_after_headings(text, note_text, heading_pattern):
    """在匹配 heading_pattern 的每一行标题后插入来源标注。"""
    def repl(match):
        return match.group(0) + "\n\n" + note_text + "\n"
    return re.sub(heading_pattern, repl, text, flags=re.MULTILINE)


def insert_class_source_notes(text, note_text):
    """
    为职业变体源文本插入来源标注。
    优先匹配二级标题；其次匹配包含"变体/Archetype"的加粗标题；
    若仍未插入，则在首个看起来像标题的加粗行后插入。
    """
    # 1. 二级标题（跳过仅包含网址的标题行）
    text = insert_note_after_headings(text, note_text, r"^(##\s+(?!http).+)")

    # 2. 包含"变体"或"Archetype"的加粗标题（允许跨行，但不跨段落）
    text = insert_note_after_headings(
        text, note_text,
        r"(\*\*(?=[^*\s：:])[^*]{0,200}?(?:变体|Archetype)[^*]{0,200}?\*\*)"
    )

    # 3. 兜底：如果还没有标注，找到首个非能力标签的加粗标题
    if note_text not in text:
        for m in re.finditer(r"(\*\*[^*\n]+\*\*)", text):
            inner = m.group(1).strip("*")
            if inner.endswith((":", "：")):
                continue
            if any(x in inner for x in ["（Su）", "（Ex）", "（Sp）", "(Su)", "(Ex)", "(Sp)"]):
                continue
            text = text[:m.end()] + "\n\n" + note_text + "\n" + text[m.end():]
            break
    return text


def insert_item_source_notes(section_content, note_text):
    """
    在物品章节内容中，尝试在每个条目标题后插入来源标注。
    支持的标题形式：
      - **条目名（English）** ...
      - 条目名（English）**** ...
      - **条目名**HA：...
    避免匹配常见的统计标签（位置、灵光、价格等）。
    """
    stat_labels = (
        "位置", "栏位", "灵光", "价格", "成本", "重量", "施法者等级", "灵氲",
        "制造需求", "制造要求", "制造条件", "先决条件", "效果", "描述",
        "需求", "出处", "来源", "起源描述", "Description Source",
    )

    def is_stat_label(text):
        t = text.strip("* ：:.\n")
        if t in stat_labels:
            return True
        # 避免把以统计标签开头的条目标题误判，例如"灵光爆发"
        for label in stat_labels:
            if t.startswith(label):
                nxt = t[len(label)] if len(t) > len(label) else ""
                if nxt in " ：:（(":
                    return True
        return False

    # 模式1: **条目名（English）** 或 **条目名**HA： 或 **条目名**出自...
    def repl_bold(match):
        inner = match.group(1)
        if is_stat_label(inner):
            return match.group(0)
        return match.group(0) + "\n\n" + note_text + "\n"

    pattern_bold = re.compile(r"(\*\*[^*]+?\*\*)(?=[\s　]*(?:HA|出自|来源)[：:]?)", flags=re.MULTILINE)
    section_content = pattern_bold.sub(repl_bold, section_content)

    # 模式2: 中文名（English）**** 统计块
    def repl_inline(match):
        return match.group(1) + "\n\n" + note_text + "\n"

    pattern_inline = re.compile(r"(^[^*\n\r].*?[）)])(?=\*\*\*\*)", flags=re.MULTILINE)
    section_content = pattern_inline.sub(repl_inline, section_content)

    return section_content


def split_by_headers(text, header_pattern):
    """按标题模式拆分文本，返回 [(标题, 内容)] 列表。"""
    parts = re.split(header_pattern, text)
    if len(parts) < 2:
        return [("", text)]
    result = []
    if parts[0].strip():
        result.append(("", parts[0]))
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        result.append((header, body))
    return result


# ---------------------------------------------------------------------------
# 种族替换特性与天赋职业奖励
# ---------------------------------------------------------------------------

RACES = ["矮人", "精灵", "侏儒", "半精灵", "半身人", "半兽人", "人类"]


def resolve_race_summary(race_name):
    """找到某种族已有的种族替换特性汇总页面。"""
    race_dir = TARGET_DIR / "种族" / "核心种族" / race_name

    # 先搜索 TOC 索引：该种族下任何像"汇总/替换/一览"的页面
    summary_keywords = ["替换汇总", "替换一览", "种族替换", "种族特性替换", "【整理】"]
    matched_tps = []
    for tp, md_names in TOC_INDEX.items():
        if tp.startswith(f"种族 → 核心种族 → {race_name} →"):
            if any(kw in tp for kw in summary_keywords):
                matched_tps.append((tp, md_names))
    # 优先使用更"标准"的路径，然后回退到任何匹配
    for tp, md_names in matched_tps:
        path = resolve_target(tp, race_dir / (md_names[0] if md_names else f"{race_name}种族特性替换汇总.md"))
        if path.exists():
            return path
    for tp, md_names in matched_tps:
        path = resolve_target(tp, race_dir / (md_names[0] if md_names else f"{race_name}种族特性替换汇总.md"))
        return path

    # 按目录 + 文件名模式再搜一次
    if race_dir.exists():
        for f in race_dir.glob("*.md"):
            if any(kw in f.name for kw in summary_keywords):
                return f

    return race_dir / f"{race_name}种族特性替换汇总.md"


def resolve_fcb_file(race_name):
    """找到/创建某种族的天赋职业奖励文件。"""
    race_dir = TARGET_DIR / "种族" / "核心种族" / race_name
    if race_dir.exists():
        for f in race_dir.glob("*天赋职业奖励*.md"):
            return f
    return race_dir / f"{race_name}天赋职业奖励.md"


def process_racial_traits(entry, changes):
    """处理 page_524.md：拆出种族替换特性与天赋职业奖励，分别合并。"""
    text = read_source(entry["md_name"])
    pattern = r"\*\*(" + "|".join(RACES) + r")\*\*"
    sections = split_by_headers(text, pattern)

    trait_changes = []
    fcb_changes = []

    for header, body in sections:
        if not header or header not in RACES:
            continue
        race_name = header

        # ---- 种族替换特性 ----
        trait_text = re.split(r"\*\*天赋职业奖励\*\*", body)[0]
        trait_target = resolve_race_summary(race_name)

        trait_pattern = r"\*\*([^*\n]+?)\*\*(?:[（(].*?[）)])?"
        traits = split_by_headers(trait_text, trait_pattern)
        merged_traits = []
        for trait_header, trait_body in traits:
            if not trait_header:
                continue
            trait_name = trait_header.strip()
            if trait_name in ("种族替换特性",):
                continue
            if already_contains(trait_target, trait_name):
                continue
            trait_content = f"**{trait_name}**\n\n{source_note('替换种族特性')}\n\n{trait_body.strip()}"
            append_to_target(trait_target, trait_content, "")
            merged_traits.append(trait_name)

        if merged_traits:
            trait_changes.append({
                "race": race_name,
                "target": str(trait_target.relative_to(TARGET_DIR)),
                "traits": merged_traits,
            })

        # ---- 天赋职业奖励 ----
        fcb_match = re.search(r"\*\*天赋职业奖励\*\*(.*?)(?=\*\*" + "|".join(RACES) + r"\*\*|\Z)", body, re.DOTALL)
        if not fcb_match:
            continue
        fcb_section = fcb_match.group(1).strip()
        if not fcb_section:
            continue

        fcb_target = resolve_fcb_file(race_name)
        marker = f"HA-{race_name}-FCB"
        if already_contains(fcb_target, marker):
            continue

        header_text = f"**{race_name}天赋职业奖励**（惧怖冒险HA）\n\n{source_note('天赋职业奖励')}\n\n"
        append_to_target(
            fcb_target,
            header_text + fcb_section,
            "",
        )
        # 写入去重标记（不显示）
        append_to_target(fcb_target, f"<!-- {marker} -->", "")
        fcb_changes.append({
            "race": race_name,
            "target": str(fcb_target.relative_to(TARGET_DIR)),
        })

    if trait_changes or fcb_changes:
        changes.append({
            "file": entry["md_name"],
            "trait_changes": trait_changes,
            "fcb_changes": fcb_changes,
        })


# ---------------------------------------------------------------------------
# 职业变体
# ---------------------------------------------------------------------------

CLASS_CATEGORIES = [
    "核心职业",
    "基础职业",
    "混合职业",
    "极限诡道",
    "异能冒险（Occult Adventures）",
]


def extract_class_name(toc_path):
    """从未整理目录的 toc_path 中提取职业名。"""
    # 例如：未整理 → 惧怖冒险HA → 变体/职业选项 → 德鲁伊
    parts = [p.strip() for p in toc_path.split("→")]
    if len(parts) >= 4:
        return parts[3]
    return ""


def resolve_class_variant(class_name):
    """找到某职业已有的职业变体页面。"""
    # 先尝试各标准分类下的精确 TOC 路径
    for category in CLASS_CATEGORIES:
        tp = f"职业 → {category} → {class_name} → 职业变体"
        md_names = TOC_INDEX.get(tp, [])
        fallback = TARGET_DIR / "职业" / category / class_name / (md_names[0] if md_names else f"{class_name}职业变体.md")
        path = resolve_target(tp, fallback)
        if path.exists():
            return path

    # 模糊搜索：任何包含该职业名且以"职业变体"结尾的 TOC 路径
    matched = []
    for tp, md_names in TOC_INDEX.items():
        if class_name in tp and tp.endswith("职业变体"):
            matched.append((tp, md_names))
    # 优先标准分类
    for category in CLASS_CATEGORIES:
        for tp, md_names in matched:
            if f"职业 → {category}" in tp:
                fallback = TARGET_DIR / "职业" / category / class_name / (md_names[0] if md_names else f"{class_name}职业变体.md")
                path = resolve_target(tp, fallback)
                if path.exists():
                    return path
    for tp, md_names in matched:
        category = tp.split(" → ")[1] if " → " in tp else "核心职业"
        fallback = TARGET_DIR / "职业" / category / class_name / (md_names[0] if md_names else f"{class_name}职业变体.md")
        path = resolve_target(tp, fallback)
        if path.exists():
            return path

    # 在目标目录中按职业名和文件名模式搜索
    for d in TARGET_DIR.rglob(class_name):
        if d.is_dir():
            for f in d.glob("*职业变体*.md"):
                return f
            page_files = sorted(d.glob("page_*.md"))
            if page_files:
                return page_files[0]

    # 实在找不到则新建
    return TARGET_DIR / "职业" / "核心职业" / class_name / f"{class_name}职业变体.md"


def process_class_archetype(entry, changes):
    """处理职业变体文件：追加到对应职业的已有职业变体页面。"""
    class_name = extract_class_name(entry["toc_path"])
    if not class_name:
        return

    target = resolve_class_variant(class_name)
    dedup_marker = f"<!-- HA-source:{entry['md_name']} -->"
    if already_contains(target, dedup_marker):
        return

    text = read_source(entry["md_name"])
    note = source_note(f"变体/职业选项 → {class_name}")
    # 在职业变体标题后插入来源标注
    text_with_notes = insert_class_source_notes(text, note)
    content = f"\n\n{text_with_notes}\n\n{dedup_marker}\n"
    append_to_target(target, content, "")
    changes.append({
        "file": entry["md_name"],
        "class": class_name,
        "target": str(target.relative_to(TARGET_DIR)),
    })


# ---------------------------------------------------------------------------
# 专长
# ---------------------------------------------------------------------------

def process_feats(entry, changes):
    """处理专长42.md，创建/追加 专长/惧怖冒险HA_专长.md。"""
    target = TARGET_DIR / "专长" / "惧怖冒险HA_专长.md"
    dedup_marker = f"<!-- HA-source:{entry['md_name']} -->"
    if already_contains(target, dedup_marker):
        return
    text = read_source(entry["md_name"])
    note = source_note('专长')
    text_with_notes = insert_item_source_notes(text, note)
    content = f"\n\n{text_with_notes}\n\n{dedup_marker}\n"
    append_to_target(target, content, "")
    changes.append({
        "file": entry["md_name"],
        "target": str(target.relative_to(TARGET_DIR)),
        "merged": ["专长列表"],
    })


# ---------------------------------------------------------------------------
# 物品
# ---------------------------------------------------------------------------

# 物品文件中的主要分节标记 -> 对应已有分类目录的 TOC 路径
ITEM_SECTION_TARGETS = {
    "护身符": "装备/魔法物品 → 魔法物品 → 奇物 → 颈部",
    "处刑人之索": "装备/魔法物品 → 魔法物品 → 魔法武器防具 → 特殊魔法武器",
    "鍊魔戒": "装备/魔法物品 → 魔法物品 → 戒指/权杖/法杖 → 戒指",
    "腥红祭坛": "装备/魔法物品 → 魔法物品 → 奇物 → 无位置",
    "特殊魔法防具": "装备/魔法物品 → 魔法物品 → 魔法武器防具 → 特殊魔法防具",
    "武器附魔": "装备/魔法物品 → 魔法物品 → 魔法武器防具 → 武器附魔",
    "特殊魔法武器": "装备/魔法物品 → 魔法物品 → 魔法武器防具 → 特殊魔法武器",
    "戒指": "装备/魔法物品 → 魔法物品 → 戒指/权杖/法杖 → 戒指",
    "法杖": "装备/魔法物品 → 魔法物品 → 戒指/权杖/法杖 → 法杖",
    "奇物": "装备/魔法物品 → 魔法物品 → 奇物 → 无位置",
}


def process_items(entry, changes):
    """处理物品9.md，按主要分节拆分到对应已有物品分类页面。"""
    text = read_source(entry["md_name"])

    marker_patterns = []
    for marker, toc_path in ITEM_SECTION_TARGETS.items():
        escaped = re.escape(marker)
        pat = re.compile(
            "(?:^\\s*(?:!?\\[.*?\\]\\(.*?\\)\\s+)?(?:(?:\\*\\*)\\s*)?" + escaped + "[^*。；：\\n]*?(?:\\*\\*)+"
            "|^\\s*(?:\\*\\*)?\\s*" + escaped + "[^*。；：\\n]*?\\n[^*。；：\\n]*?(?:\\*\\*)+)"
            "|^\\s*(?:\\*\\*)?\\s*" + escaped + "[^*。；：\\n]*?\\n\\s*\\*\\*",
            flags=re.MULTILINE,
        )
        marker_patterns.append((marker, toc_path, pat))

    matches = []
    for marker, toc_path, pat in marker_patterns:
        for m in pat.finditer(text):
            matches.append((m.start(), m.end(), marker, toc_path))
    matches.sort()

    # 去重：同一标记只保留第一次出现；后续同名匹配通常是子分类或重复标题
    seen_markers = set()
    unique_matches = []
    for start, end, marker, toc_path in matches:
        if marker in seen_markers:
            continue
        seen_markers.add(marker)
        unique_matches.append((start, end, marker, toc_path))
    matches = unique_matches

    routed = {}
    for idx, (start, end, marker, toc_path) in enumerate(matches):
        content_start = end
        content_end = matches[idx + 1][0] if idx + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip()
        if not content:
            continue

        target = resolve_target(toc_path)
        section_marker = f"## {marker}"
        if already_contains(target, section_marker):
            continue

        note = source_note('物品')
        content_with_notes = insert_item_source_notes(content, note)
        section = f"\n\n{section_marker}\n\n{content_with_notes}\n"
        append_to_target(target, section, "")
        routed.setdefault(str(target.relative_to(TARGET_DIR)), []).append(marker)

    if routed:
        changes.append({
            "file": entry["md_name"],
            "targets": routed,
        })


# ---------------------------------------------------------------------------
# 肉体改制与神秘仪式
# ---------------------------------------------------------------------------

def process_fleshcrafting(entry, changes):
    """处理肉体改制.md，新建规则文件。"""
    target = TARGET_DIR / "规则" / "惧怖冒险HA_肉体改制.md"
    dedup_marker = f"<!-- HA-source:{entry['md_name']} -->"
    if already_contains(target, dedup_marker):
        return
    text = read_source(entry["md_name"])
    write_target(target, source_note("肉体改制") + "\n\n" + text + "\n\n" + dedup_marker + "\n")
    changes.append({
        "file": entry["md_name"],
        "target": str(target.relative_to(TARGET_DIR)),
        "merged": ["肉体改制规则"],
    })


def process_rituals(entry, changes):
    """处理神秘仪式3.md，新建法术文件。"""
    target = TARGET_DIR / "法术" / "惧怖冒险HA_神秘仪式.md"
    dedup_marker = f"<!-- HA-source:{entry['md_name']} -->"
    if already_contains(target, dedup_marker):
        return
    text = read_source(entry["md_name"])
    write_target(target, source_note("神秘仪式") + "\n\n" + text + "\n\n" + dedup_marker + "\n")
    changes.append({
        "file": entry["md_name"],
        "target": str(target.relative_to(TARGET_DIR)),
        "merged": ["神秘仪式列表"],
    })


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    global TOC_INDEX
    mapping = load_mapping()
    TOC_INDEX = build_toc_index(mapping)
    entries = load_ha_entries(mapping)
    print(f"加载到 {len(entries)} 个 HA 条目")

    if not TARGET_DIR.exists():
        print(f"创建副本目录: {TARGET_DIR}")
        shutil.copytree(SOURCE_DIR, TARGET_DIR)

    changes = []
    skipped = []

    for entry in entries:
        toc_path = entry["toc_path"]
        if "替换种族特性" in toc_path:
            process_racial_traits(entry, changes)
        elif "变体/职业选项" in toc_path:
            process_class_archetype(entry, changes)
        elif toc_path.endswith(" → 专长"):
            process_feats(entry, changes)
        elif toc_path.endswith(" → 物品"):
            process_items(entry, changes)
        elif toc_path.endswith(" → 肉体改制"):
            process_fleshcrafting(entry, changes)
        elif toc_path.endswith(" → 神秘仪式"):
            process_rituals(entry, changes)
        elif toc_path == "未整理 → 惧怖冒险HA":
            skipped.append(entry["md_name"])
        else:
            skipped.append(entry["md_name"])

    # 生成报告
    report_lines = [
        "# 惧怖冒险 HA 整理报告",
        "",
        f"共处理 {len(entries)} 个文件，跳过 {len(skipped)} 个。",
        "",
        "## 变更明细",
        "",
    ]
    for change in changes:
        if "file" in change and "target" in change:
            report_lines.append(f"- **{change['file']}** → {change['target']}")
        elif "file" in change and "targets" in change:
            report_lines.append(f"- **{change['file']}** → {change['targets']}")
        else:
            report_lines.append(f"- **{change.get('file', '?')}** → {change}")

        if "merged" in change:
            for item in change["merged"]:
                report_lines.append(f"  - {item}")
        if "trait_changes" in change:
            for tc in change["trait_changes"]:
                report_lines.append(f"  - 种族替换特性 [{tc['race']}] → {tc['target']}: {', '.join(tc['traits'])}")
        if "fcb_changes" in change:
            for fc in change["fcb_changes"]:
                report_lines.append(f"  - 天赋职业奖励 [{fc['race']}] → {fc['target']}")
        if "class" in change:
            report_lines.append(f"  - 职业变体 [{change['class']}]")

    if skipped:
        report_lines.extend(["", "## 跳过文件", ""])
        for name in skipped:
            report_lines.append(f"- {name}")

    REPORT_FILE.write_text("\n".join(report_lines), encoding="utf-8")
    PLAN_FILE.write_text(json.dumps({
        "entries": entries,
        "changes": changes,
        "skipped": skipped,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"整理完成。跳过: {skipped}")
    print(f"报告: {REPORT_FILE}")
    print(f"清单: {PLAN_FILE}")


if __name__ == "__main__":
    main()
