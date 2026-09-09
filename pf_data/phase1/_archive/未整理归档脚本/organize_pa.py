#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 位面冒险（Planar Adventures）内容到已有分类目录。

本次处理：
- 新玩家种族：秩裔、熵裔、暮行者 → 种族/罕见种族
- 职业变体：暗刃（战士）、幻梦贼（盗贼）、原初使者（德鲁伊）、
  位面斥候（游侠）、契约巫师（女巫）、诸界见证人（吟游诗人）、
  灵魂守卫（唤魂师）、界门寻索人（调查员）、唯心教众（牧师）、
  世界探索者（法师）、爱塔剑客（游荡剑客）
- 专长：page_1492.md（汲引专长）、其他专长1.md（种族/通用专长）、
  位面谐律.md（位面谐律规则+各位面谐律效果）
- 新物品：
  - 护甲特殊能力：page_1570.md → 装备_魔法物品/防具附魔
  - 武器特殊能力：page_1569.md → 装备_魔法物品/武器/武器大师手册_魔法武器.md（追加）
  - 特殊武器：page_1568.md → 装备_魔法物品/武器/武器大师手册_魔法武器.md（追加）
  - 权杖：page_1566.md → 装备_魔法物品/魔法物品/戒指_权杖_法杖
  - 戒指：page_1572.md → 装备_魔法物品/魔法物品/戒指_权杖_法杖
  - 奇物：page_1567.md → 装备_魔法物品/魔法物品/奇物

暂不处理：
- 无

原则：
- 仅追加到 pf_rules_md_organized/ 下已有分类目录的对应文件。
- 每个条目在标题下一行标注来源。
- 使用隐藏标记去重；已存在的条目跳过并记录为重复。
- 不修改原 pf_rules_md/ 目录。
"""

import json
import os
import re

BASE = "/Users/chezi/code/java/pf_agent/pf_data/phase1"
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/位面冒险PA")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "PA_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "PA_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")
PROBLEM_RECORD_PATH = os.path.join(BASE, "未整理目录整理问题记录.md")

SOURCE_NOTE_TEMPLATE = "> 来源：位面冒险（Planar Adventures），页码见原书，未整理 → 位面冒险PA → {section_title}"

# 职业变体条目配置
SECTIONS = [
    # 战士变体
    {"source": "职业变体/page_1433.md", "title": "暗刃", "english": "Gloomblade", "cls": "战士", "section_title": "变体", "target": "职业/核心职业/战士/page_49.md", "marker": "暗刃", "duplicate_skip": True},
    # 盗贼变体
    {"source": "职业变体/page_1475.md", "title": "幻梦贼", "english": "Dreamthief", "cls": "盗贼", "section_title": "变体", "target": "职业/核心职业/盗贼/page_47.md", "marker": "幻梦贼", "duplicate_skip": True},
    # 德鲁伊变体
    {"source": "职业变体/page_1477.md", "title": "原初使者", "english": "Progenitor", "cls": "德鲁伊", "section_title": "变体", "target": "职业/核心职业/德鲁伊/page_37.md", "marker": "**原初使者（Progenitor）**", "duplicate_skip": True},
    # 游侠变体
    {"source": "职业变体/page_1479.md", "title": "位面斥候", "english": "Planar Scout", "cls": "游侠", "section_title": "变体", "target": "职业/核心职业/游侠/page_51.md", "marker": "**位面斥候（Planar", "duplicate_skip": True},
    # 女巫变体
    {"source": "职业变体/page_1484.md", "title": "契约巫师", "english": "Pact Witch", "cls": "女巫", "section_title": "变体", "target": "职业/基础职业/女巫/page_70.md", "marker": "契约巫师（Pact Witch）", "duplicate_skip": True},
    # 吟游诗人变体
    {"source": "职业变体/page_1478.md", "title": "诸界见证人", "english": "Chronicler of Worlds", "cls": "吟游诗人", "section_title": "变体", "target": "职业/核心职业/吟游诗人/page_38.md", "marker": "**诸界见证人**", "duplicate_skip": True},
    # 唤魂师变体
    {"source": "职业变体/page_1476.md", "title": "灵魂守卫", "english": "Soul Warden", "cls": "唤魂师", "section_title": "变体", "target": "职业/异能冒险（Occult Adventures）/通灵者/page_262.md", "marker": "**灵魂守卫（Soul", "duplicate_skip": True},
    # 调查员变体
    {"source": "职业变体/page_1485.md", "title": "界门寻索人", "english": "Portal Seeker", "cls": "调查员", "section_title": "变体", "target": "职业/混合职业/调查员/page_31.md", "marker": "界门寻索人", "duplicate_skip": True},
    # 牧师变体
    {"source": "职业变体/page_1486.md", "title": "唯心教众", "english": "Idealist", "cls": "牧师", "section_title": "变体", "target": "职业/核心职业/牧师/page_41.md", "marker": "唯心教众", "duplicate_skip": True},
    # 法师变体
    {"source": "职业变体/page_1487.md", "title": "世界探索者", "english": "Worldseeker", "cls": "法师", "section_title": "变体", "target": "职业/核心职业/法师/page_45.md", "marker": "世界探索者", "duplicate_skip": True},
    # 游荡剑客变体
    {"source": "职业变体/游荡剑客.md", "title": "爱塔剑客", "english": "Azatariel", "cls": "游荡剑客", "section_title": "变体", "target": "职业/混合职业/游荡剑客/page_56.md", "marker": "爱塔剑客", "duplicate_skip": True},
]

KNOWN_LABELS = {
    "制造要求", "需求", "制造成本", "制造条件", "灵光", "位置", "栏位", "价格",
    "施法者等级", "重量", "类别", "描述", "来源", "出处", "效果", "先决条件",
    "专长效果", "通常", "特殊说明", "拥有此专长前的正常情况", "好处", "学派",
    "施放时间", "成分", "技能检定", "距离", "区域", "持续时间", "豁免", "法术抗力",
    "反冲", "失败",
}


def load_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().splitlines()


def find_index(lines, marker, source):
    """查找标记在文本中的位置，支持跨行匹配。"""
    if "\n" in marker:
        marker_parts = marker.split("\n")
        for i in range(len(lines) - len(marker_parts) + 1):
            if all(marker_part in lines[i + j] for j, marker_part in enumerate(marker_parts)):
                return i
        raise ValueError(f"在 {source} 中未找到标记: {marker!r}")
    else:
        for i, line in enumerate(lines):
            if marker in line:
                return i
        raise ValueError(f"在 {source} 中未找到标记: {marker!r}")


def already_present(target_text, section):
    marker_key = f"<!-- PA-source:{section['source']}:{section['title']} -->"
    if marker_key in target_text:
        return True, "hidden_marker"
    if section.get("duplicate_skip"):
        checks = [section["title"], section.get("english", "")]
        for c in checks:
            if c and c in target_text:
                return True, f"existing_content ({c})"
    return False, None


def extract_section(source_lines, start_idx, end_idx):
    return source_lines[start_idx:end_idx]


def normalize_section_lines(section_lines):
    """修正标题与正文挤在同一行的情况（如 **标题** *****正文）。"""
    result = []
    for line in section_lines:
        m = re.match(r'^(\*\*.*?\*\*)(\*{2,})(\*?.*)$', line)
        if m:
            result.append(m.group(1))
            body = m.group(3).lstrip('*')
            if body:
                result.append(body)
        else:
            result.append(line)
    return result


def split_title_body(section_lines):
    """将片段拆分为标题行与正文行。标题为开头连续的加粗块。"""
    section_lines = normalize_section_lines(section_lines)
    title_end = 0
    label_pattern = re.compile(r'^\*\*(' + '|'.join(re.escape(l) for l in KNOWN_LABELS) + r')')
    for i, line in enumerate(section_lines):
        s = line.strip()
        if not s:
            if title_end > 0:
                break
            continue
        if title_end == 0:
            title_end = i + 1
            continue
        # 当前行是正文标签（灵光、价格、先决条件等），标题结束
        if label_pattern.match(s):
            break
        prev = section_lines[i - 1].strip()
        if prev.endswith("**"):
            break
        title_end = i + 1
    return section_lines[:title_end], section_lines[title_end:]


def build_append_block(section, section_lines, section_title=None):
    title_lines, body_lines = split_title_body(section_lines)
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title or section.get("section_title", ""))
    marker = f"<!-- PA-source:{section['source']}:{section['title']} -->"
    result = [marker]
    result.extend(title_lines)
    result.append(note)
    result.extend(body_lines)
    if result and result[-1].strip() != "":
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def append_to_target(target_path, block):
    full_path = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    mode = "a" if os.path.exists(full_path) else "w"
    with open(full_path, mode, encoding="utf-8") as f:
        f.write(block)


def ensure_header(target_path, header):
    full_path = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    if not os.path.exists(full_path) or os.path.getsize(full_path) == 0:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(header + "\n\n")


def process_source_sections(secs, stats, duplicates, plan_sections):
    """处理通用 SECTIONS 配置。"""
    grouped = {}
    for sec in secs:
        grouped.setdefault(sec["source"], []).append(sec)

    for source, src_secs in grouped.items():
        src_path = os.path.join(SRC_DIR, source)
        if not os.path.exists(src_path):
            stats["errors"].append(f"源文件不存在: {source}")
            continue
        lines = load_lines(src_path)
        indices = []
        for sec in src_secs:
            try:
                idx = find_index(lines, sec["marker"], source)
                indices.append((idx, sec))
            except ValueError as e:
                stats["errors"].append(str(e))
        indices.sort(key=lambda x: x[0])

        for i, (start_idx, sec) in enumerate(indices):
            end_idx = indices[i + 1][0] if i + 1 < len(indices) else len(lines)
            target_path = sec["target"]
            full_target = os.path.join(ORG_BASE, target_path)
            target_text = ""
            if os.path.exists(full_target):
                target_text = open(full_target, "r", encoding="utf-8").read()

            present, reason = already_present(target_text, sec)
            if present:
                duplicates.append({
                    "source": source,
                    "title": sec["title"],
                    "english": sec.get("english", ""),
                    "target": target_path,
                    "reason": reason,
                })
                stats["skipped"] += 1
                plan_sections.append({**sec, "action": "skipped", "reason": reason})
                continue

            section_lines = extract_section(lines, start_idx, end_idx)
            block = build_append_block(sec, section_lines)
            append_to_target(target_path, block)
            stats["added"] += 1
            plan_sections.append({**sec, "action": "added"})


def detect_title_starts(lines, max_len=80):
    """自动检测以中文名称开头的标题行位置（用于专长）。"""
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        while s.startswith("*"):
            s = s[1:]
        s = s.strip()
        if not s or len(s) > max_len:
            continue
        if s[-1] in "。！？":
            continue
        m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", s)
        if not m:
            continue
        first = m.group(1)
        if first in KNOWN_LABELS:
            continue
        starts.append((i, s))
    return starts


def process_auto_split_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections, source_dir=None):
    """对专长文件按自动检测的标题行拆分并合并。"""
    src_dir = source_dir or SRC_DIR
    src_path = os.path.join(src_dir, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return
    lines = load_lines(src_path)
    starts = detect_title_starts(lines)
    if not starts:
        stats["errors"].append(f"{source_file} 中未检测到标题")
        return

    ensure_header(target_path, header)

    for idx, (start_idx, title_line) in enumerate(starts):
        end_idx = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        short_title = title_line.split("（")[0].split(" ")[0].strip("*")
        sec = {
            "source": source_file,
            "title": short_title,
            "english": "",
            "target": target_path,
            "section_title": section_title,
        }
        full_target = os.path.join(ORG_BASE, target_path)
        target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

        present, reason = already_present(target_text, sec)
        if present:
            duplicates.append({
                "source": source_file,
                "title": short_title,
                "english": "",
                "target": target_path,
                "reason": reason,
            })
            stats["skipped"] += 1
            plan_sections.append({**sec, "action": "skipped", "reason": reason})
            continue

        section_lines = extract_section(lines, start_idx, end_idx)
        block = build_append_block(sec, section_lines, section_title=section_title)
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def process_single_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections, source_dir=None):
    """处理单文件多条目（如奇物、权杖、戒指、特殊武器/防具）。

    每个条目标题行以 ** 开头，按标题自动拆分。
    """
    src_dir = source_dir or SRC_DIR
    src_path = os.path.join(src_dir, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 检测以 ** 开头的标题行
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("**"):
            # 去掉 ** 后取中文名
            rest = s[2:]
            m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", rest)
            if m:
                first = m.group(1)
                if first not in KNOWN_LABELS:
                    starts.append((i, s))

    if not starts:
        stats["errors"].append(f"{source_file} 中未找到有效标题")
        return

    ensure_header(target_path, header)

    for idx, (start_idx, title_line) in enumerate(starts):
        end_idx = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        short_title = title_line.strip("*").split("（")[0].split(" ")[0].strip()

        sec = {
            "source": source_file,
            "title": short_title,
            "english": "",
            "target": target_path,
            "section_title": section_title,
        }

        full_target = os.path.join(ORG_BASE, target_path)
        target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

        present, reason = already_present(target_text, sec)
        if present:
            duplicates.append({
                "source": source_file,
                "title": short_title,
                "english": "",
                "target": target_path,
                "reason": reason,
            })
            stats["skipped"] += 1
            plan_sections.append({**sec, "action": "skipped", "reason": reason})
            continue

        section_lines = extract_section(lines, start_idx, end_idx)
        block = build_append_block(sec, section_lines, section_title=section_title)
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def process_race_file(source_file, target_path, race_name, english_name, stats, duplicates, plan_sections):
    """处理种族文件，作为单一条目追加。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)
    sec = {
        "source": source_file,
        "title": race_name,
        "english": english_name,
        "target": target_path,
        "section_title": "新玩家种族",
    }

    full_target = os.path.join(ORG_BASE, target_path)
    target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

    present, reason = already_present(target_text, sec)
    if present:
        duplicates.append({
            "source": source_file,
            "title": race_name,
            "english": english_name,
            "target": target_path,
            "reason": reason,
        })
        stats["skipped"] += 1
        plan_sections.append({**sec, "action": "skipped", "reason": reason})
        return

    ensure_header(target_path, f"# {race_name} ({english_name})")

    marker = f"<!-- PA-source:{source_file}:{race_name} -->"
    note = SOURCE_NOTE_TEMPLATE.format(section_title="新玩家种族")
    result = [marker, f"**{race_name} ({english_name})**", note]
    result.extend(lines)
    if result and result[-1].strip() != "":
        result.append("")
    result.append("")
    block = "\n".join(result) + "\n"
    append_to_target(target_path, block)
    stats["added"] += 1
    plan_sections.append({**sec, "action": "added"})


def process_planar_infusion_file(stats, duplicates, plan_sections):
    """处理位面谐律.md——这是一个特殊文件，包含规则说明+大量位面谐律效果。
    作为单一条目追加到专长目录下。"""
    source_file = "专长/位面谐律.md"
    target_path = "专长/位面冒险PA_位面谐律.md"
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)
    sec = {
        "source": source_file,
        "title": "位面谐律",
        "english": "Planar Infusions",
        "target": target_path,
        "section_title": "位面谐律",
    }

    full_target = os.path.join(ORG_BASE, target_path)
    target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

    present, reason = already_present(target_text, sec)
    if present:
        duplicates.append({
            "source": source_file,
            "title": "位面谐律",
            "english": "Planar Infusions",
            "target": target_path,
            "reason": reason,
        })
        stats["skipped"] += 1
        plan_sections.append({**sec, "action": "skipped", "reason": reason})
        return

    ensure_header(target_path, "# 位面冒险 位面谐律")

    marker = f"<!-- PA-source:{source_file}:位面谐律 -->"
    note = SOURCE_NOTE_TEMPLATE.format(section_title="位面谐律")
    result = [marker, "**位面谐律（Planar Infusions）**", note]
    result.extend(lines)
    if result and result[-1].strip() != "":
        result.append("")
    result.append("")
    block = "\n".join(result) + "\n"
    append_to_target(target_path, block)
    stats["added"] += 1
    plan_sections.append({**sec, "action": "added"})


def main():
    stats = {"added": 0, "skipped": 0, "errors": []}
    duplicates = []
    plan_sections = []

    # 1. 新玩家种族
    process_race_file("新玩家种族/page_1482.md", "种族/罕见种族/位面冒险PA_秩裔.md", "秩裔", "Aphorite", stats, duplicates, plan_sections)
    process_race_file("新玩家种族/page_1483.md", "种族/罕见种族/位面冒险PA_熵裔.md", "熵裔", "Ganzi", stats, duplicates, plan_sections)
    process_race_file("新玩家种族/page_1488.md", "种族/罕见种族/位面冒险PA_暮行者.md", "暮行者", "Duskwalker", stats, duplicates, plan_sections)

    # 2. 职业变体
    process_source_sections(SECTIONS, stats, duplicates, plan_sections)

    # 3. 专长
    feat_target = "专长/位面冒险PA_专长.md"
    feat_header = "# 位面冒险 专长"
    # page_1492.md 是汲引专长，按标题自动拆分
    process_auto_split_file("专长/page_1492.md", feat_target, "专长", feat_header, stats, duplicates, plan_sections, source_dir=SRC_DIR)
    # 其他专长1.md 是种族/通用专长，按标题自动拆分
    process_auto_split_file("专长/其他专长1.md", feat_target, "专长", feat_header, stats, duplicates, plan_sections, source_dir=SRC_DIR)

    # 4. 位面谐律（作为单独文件处理）
    process_planar_infusion_file(stats, duplicates, plan_sections)

    # 5. 新物品——护甲特殊能力
    process_single_file(
        "新物品/page_1570.md",
        "装备_魔法物品/防具附魔/位面冒险PA_防具附魔.md",
        "防具附魔",
        "# 位面冒险 防具附魔",
        stats, duplicates, plan_sections, source_dir=SRC_DIR
    )

    # 6. 新物品——武器特殊能力
    process_single_file(
        "新物品/page_1569.md",
        "装备_魔法物品/武器/位面冒险PA_武器附魔.md",
        "武器附魔",
        "# 位面冒险 武器附魔",
        stats, duplicates, plan_sections, source_dir=SRC_DIR
    )

    # 7. 新物品——特殊武器
    process_single_file(
        "新物品/page_1568.md",
        "装备_魔法物品/武器/位面冒险PA_特殊武器.md",
        "特殊武器",
        "# 位面冒险 特殊武器",
        stats, duplicates, plan_sections, source_dir=SRC_DIR
    )

    # 8. 新物品——权杖
    process_single_file(
        "新物品/page_1566.md",
        "装备_魔法物品/魔法物品/戒指_权杖_法杖/位面冒险PA_权杖.md",
        "权杖",
        "# 位面冒险 权杖",
        stats, duplicates, plan_sections, source_dir=SRC_DIR
    )

    # 9. 新物品——戒指
    process_single_file(
        "新物品/page_1572.md",
        "装备_魔法物品/魔法物品/戒指_权杖_法杖/位面冒险PA_戒指.md",
        "戒指",
        "# 位面冒险 戒指",
        stats, duplicates, plan_sections, source_dir=SRC_DIR
    )

    # 10. 新物品——奇物
    process_single_file(
        "新物品/page_1567.md",
        "装备_魔法物品/魔法物品/奇物/位面冒险PA_奇物.md",
        "奇物",
        "# 位面冒险 奇物",
        stats, duplicates, plan_sections, source_dir=SRC_DIR
    )

    # 11. 写入计划文件
    plan = {
        "source_book": "位面冒险",
        "source_book_english": "Planar Adventures",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/位面冒险PA",
        "stats": stats,
        "sections": plan_sections,
        "skipped_files": [],
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 12. 写入报告
    report_lines = [
        "# 位面冒险（Planar Adventures）整理报告",
        "",
        "## 整理策略",
        "",
        "位面冒险（Planar Adventures）内容分散在新玩家种族、职业变体、专长、新物品等文件中。",
        "本次将所有规则条目按类型合并到 `pf_rules_md_organized/` 下对应分类目录。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/位面冒险PA/`",
        "",
        "## 处理统计",
        "",
        f"- 新增条目：{stats['added']}",
        f"- 跳过重复：{stats['skipped']}",
        f"- 错误：{len(stats['errors'])}",
        "",
        "## 处理内容",
        "",
        "### 新玩家种族",
        "- 秩裔（Aphorite）→ `种族/罕见种族/位面冒险PA_秩裔.md`",
        "- 熵裔（Ganzi）→ `种族/罕见种族/位面冒险PA_熵裔.md`",
        "- 暮行者（Duskwalker）→ `种族/罕见种族/位面冒险PA_暮行者.md`",
        "",
        "### 职业变体",
        "- 暗刃（Gloomblade，战士）→ `职业/核心职业/战士/page_49.md`",
        "- 幻梦贼（Dreamthief，盗贼）→ `职业/核心职业/盗贼/page_47.md`",
        "- 原初使者（Progenitor，德鲁伊）→ `职业/核心职业/德鲁伊/page_37.md`",
        "- 位面斥候（Planar Scout，游侠）→ `职业/核心职业/游侠/page_51.md`",
        "- 契约巫师（Pact Witch，女巫）→ `职业/基础职业/女巫/page_70.md`",
        "- 诸界见证人（Chronicler of Worlds，吟游诗人）→ `职业/核心职业/吟游诗人/page_38.md`",
        "- 灵魂守卫（Soul Warden，唤魂师）→ `职业/异能冒险（Occult Adventures）/通灵者/page_262.md`",
        "- 界门寻索人（Portal Seeker，调查员）→ `职业/混合职业/调查员/page_31.md`",
        "- 唯心教众（Idealist，牧师）→ `职业/核心职业/牧师/page_41.md`",
        "- 世界探索者（Worldseeker，法师）→ `职业/核心职业/法师/page_45.md`",
        "- 爱塔剑客（Azatariel，游荡剑客）→ `职业/混合职业/游荡剑客/page_56.md`",
        "",
        "### 专长",
        "- 汲引专长（page_1492.md）→ `专长/位面冒险PA_专长.md`",
        "- 其他专长（其他专长1.md：抓取用尾巴、鞭击用尾巴、调皮用尾巴、位面血脉、精通异界传送、引导圣临）→ `专长/位面冒险PA_专长.md`",
        "- 位面谐律规则与效果 → `专长/位面冒险PA_位面谐律.md`",
        "",
        "### 新物品",
        "- 护甲特殊能力（page_1570.md：气缓、结茧、共旅、混影）→ `装备_魔法物品/防具附魔/位面冒险PA_防具附魔.md`",
        "- 武器特殊能力（page_1569.md：无阵营、位面打击）→ `装备_魔法物品/武器/位面冒险PA_武器附魔.md`",
        "- 特殊武器（page_1568.md：不确定之刃、魔蝠首级之箭、库凯图斯的碎片）→ `装备_魔法物品/武器/位面冒险PA_特殊武器.md`",
        "- 权杖（page_1566.md：末日/喝令/福佑/墓园/喧嚣/冥河超魔权杖、叉形权杖、厉鬼权杖）→ `装备_魔法物品/魔法物品/戒指_权杖_法杖/位面冒险PA_权杖.md`",
        "- 戒指（page_1572.md：熵与秩之戒、位面聚焦之戒、灵魂联结戒指）→ `装备_魔法物品/魔法物品/戒指_权杖_法杖/位面冒险PA_戒指.md`",
        "- 奇物（page_1567.md：受膏者圣徽、星仪、位面锚定之靴等16件）→ `装备_魔法物品/魔法物品/奇物/位面冒险PA_奇物.md`",
    ]
    if stats["errors"]:
        report_lines.extend(["", "## 错误", ""])
        for e in stats["errors"]:
            report_lines.append(f"- {e}")
    if duplicates:
        report_lines.extend(["", "## 重复/跳过项", ""])
        for d in duplicates:
            en = f" / {d['english']}" if d["english"] else ""
            report_lines.append(f"- `{d['source']}` `{d['title']}{en}` → `{d['target']}`（原因：{d['reason']}）")
    report_lines.extend(["", "## 验证清单", "", "- [ ] 原目录未被修改", "- [ ] 新增条目均出现 `> 来源：` 标注", "- [ ] 标注位于条目标题下一行", "- [ ] 未重复追加", "- [ ] 进度文档已更新", "- [ ] 已提交 Git", ""])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    # 13. 重复记录
    if duplicates:
        dup_lines = ["", "", "## 位面冒险（Planar Adventures）", "", f"**发现时间**：2026-06-19", ""]
        dup_lines.append("| 来源文件 | 条目 | 目标文件 | 备注 |")
        dup_lines.append("|----------|------|----------|------|")
        for d in duplicates:
            en = f" / {d['english']}" if d["english"] else ""
            dup_lines.append(f"| {d['source']} | {d['title']}{en} | {d['target']} | {d['reason']} |")
        dup_lines.append("")
        with open(DUP_RECORD_PATH, "a", encoding="utf-8") as f:
            f.write("\n".join(dup_lines))

    print(f"整理完成：新增 {stats['added']} 条，跳过 {stats['skipped']} 条，错误 {len(stats['errors'])} 条。")
    if stats["errors"]:
        for e in stats["errors"]:
            print("  ERROR:", e)


if __name__ == "__main__":
    main()
