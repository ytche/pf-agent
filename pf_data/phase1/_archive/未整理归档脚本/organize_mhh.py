#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 怪物猎人手册（Monster Hunter's Handbook）内容到已有分类目录。

本次处理：
- 专长：专长1.md（约 33 个专长）
- 职业变体：
  - 秘灵猎兵（Psychodermist）→ 秘学士
  - 枪之从者（Disciple of the Pike）→ 骑士
  - 泥怪大师（Oozemaster）→ 炼金术师
  - 净化者（Abolisher）→ 审判者
  - 真实世界守卫者（Defender of the True World）→ 德鲁伊
  - 绿灾（Green Scourge）→ 德鲁伊
  - 驱魔卫士（Banishing Warden）→ 圣武士
  - 吹笛人（Luring Piper）→ 吟游诗人
- 背景特性：背景特性1.md（4 个背景 + 4 个背景特性）
- 魔法物品：page_1617.md（8 个魔法物品）
- 普通物品：普通物品.md（约 14 个普通物品/炼金物品）

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
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/怪物猎人手册MHH")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "MHH_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "MHH_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")
PROBLEM_RECORD_PATH = os.path.join(BASE, "未整理目录整理问题记录.md")

SOURCE_NOTE_TEMPLATE = "> 来源：怪物猎人手册（Monster Hunter's Handbook），页码见原书，未整理 → 怪物猎人手册MHH → {section_title}"

# 职业变体条目配置
SECTIONS = [
    # 秘学士变体
    {"source": "变体/page_1213.md", "title": "秘灵猎兵", "english": "Psychodermist", "cls": "秘学士", "section_title": "变体", "target": "职业/混合职业/秘学士/全变体未整合.md", "marker": "秘灵猎兵(Psychodermist)"},
    # 骑士变体
    {"source": "变体/page_1228.md", "title": "枪之从者", "english": "Disciple of the Pike", "cls": "骑士", "section_title": "变体", "target": "职业/基础职业/骑士/护甲大师手册_骑士变体.md", "marker": "枪之从者"},
    # 炼金术师变体
    {"source": "变体/page_1236.md", "title": "泥怪大师", "english": "Oozemaster", "cls": "炼金术师", "section_title": "变体", "target": "职业/基础职业/炼金术师/全变体未整合.md", "marker": "泥怪大师(Oozemaster)"},
    # 审判者变体
    {"source": "变体/审判者.md", "title": "净化者", "english": "Abolisher", "cls": "审判者", "section_title": "变体", "target": "职业/基础职业/审判者/page_78.md", "marker": "净化者-审判者变体 Abolisher"},
    # 德鲁伊变体 - 真实世界守卫者
    {"source": "变体/德鲁伊.md", "title": "真实世界守卫者", "english": "Defender of the True World", "cls": "德鲁伊", "section_title": "变体", "target": "职业/核心职业/德鲁伊/page_37.md", "marker": "真实世界守卫者-德鲁伊变体 Defender"},
    # 德鲁伊变体 - 绿灾
    {"source": "变体/德鲁伊.md", "title": "绿灾", "english": "Green Scourge", "cls": "德鲁伊", "section_title": "变体", "target": "职业/核心职业/德鲁伊/page_37.md", "marker": "绿灾-德鲁伊变体Green Scourge"},
    # 圣武士变体
    {"source": "变体/圣骑士.md", "title": "驱魔卫士", "english": "Banishing Warden", "cls": "圣武士", "section_title": "变体", "target": "职业/核心职业/圣骑士/page_55.md", "marker": "驱魔卫士-圣武士变体 Banishing"},
    # 吟游诗人变体
    {"source": "变体/吟游诗人.md", "title": "吹笛人", "english": "Luring Piper", "cls": "吟游诗人", "section_title": "变体", "target": "职业/核心职业/吟游诗人/page_38.md", "marker": "吹笛人-吟游诗人变体 Luring Piper"},
]

KNOWN_LABELS = {
    "制造要求", "需求", "制造成本", "制造条件", "灵光", "位置", "栏位", "价格",
    "施法者等级", "重量", "类别", "描述", "来源", "出处", "效果", "先决条件",
    "专长效果", "通常", "特殊说明", "拥有此专长前的正常情况", "好处", "学派",
    "施放时间", "成分", "技能检定", "距离", "区域", "持续时间", "豁免", "法术抗力",
    "反冲", "失败", "类型", "动作", "重试", "特殊规则", "检定", "需求",
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
    marker_key = f"<!-- MHH-source:{section['source']}:{section['title']} -->"
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
        # 当前行是正文标签，标题结束
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
    marker = f"<!-- MHH-source:{section['source']}:{section['title']} -->"
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
    """处理通用 SECTIONS 配置（职业变体）。"""
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
        if s and s[-1] in "。！？":
            continue
        m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", s)
        if not m:
            continue
        first = m.group(1)
        if first in KNOWN_LABELS:
            continue
        starts.append((i, s))
    return starts


def process_auto_split_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """按自动检测的标题行拆分并合并（用于专长文件）。

    修正：处理标题跨行的情况（如 **异怪专精(战斗)**Focused Aberration\nExpertise）。
    """
    src_path = os.path.join(SRC_DIR, source_file)
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
        # 修正标题提取：取中文名部分
        short_title = title_line.split("（")[0].split(" ")[0].strip("*")
        # 如果标题中有英文括号，进一步清理
        short_title = re.sub(r'[\(（].*$', '', short_title).strip()
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


def process_single_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理单文件多条目（如背景特性、普通物品），每个条目标题行以 ** 开头，按标题自动拆分。"""
    src_path = os.path.join(SRC_DIR, source_file)
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


def process_magic_items(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理魔法物品文件（page_1617.md）。格式：标题行以 ** 开头，有标准魔法物品格式。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 检测以 ** 开头的标题行（魔法物品标题）
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("**"):
            # 去掉 ** 后取中文名
            rest = s[2:]
            m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", rest)
            if m:
                first = m.group(1)
                if first not in KNOWN_LABELS and first not in {"PFS", "魔法物品"}:
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


def process_equipment_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理普通物品文件（普通物品.md）。格式：标题行无 **，以中文名开头，后接英文和价格等。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 检测物品标题：中文名开头，后接英文（无括号）
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or len(s) > 80:
            continue
        # 跳过章节标题和说明文字
        if s in {"新物品", "PFS和谐需要"} or s.startswith("![") or s.startswith("["):
            continue
        m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", s)
        if not m:
            continue
        first = m.group(1)
        if first in KNOWN_LABELS:
            continue
        starts.append((i, s))

    if not starts:
        stats["errors"].append(f"{source_file} 中未检测到物品标题")
        return

    ensure_header(target_path, header)

    for idx, (start_idx, title_line) in enumerate(starts):
        end_idx = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        short_title = title_line.split("（")[0].split(" ")[0].strip("*")
        # 修正：如果标题包含英文跨行（如 猎兽哨BEAST-HUNTER），只保留中文部分
        m = re.match(r"([一-鿿][一-鿿\w]*)", short_title)
        if m:
            short_title = m.group(1)
        # 修正：如果标题以 BEAST 结尾（因为英文跨行），去掉 BEAST 及后续
        if short_title.endswith("BEAST"):
            short_title = short_title[:-5].strip()
        if short_title.endswith("BOTTLED"):
            short_title = short_title[:-7].strip()
        if short_title.endswith("CHEMICAL"):
            short_title = short_title[:-8].strip()
        if short_title.endswith("DISPLAY"):
            short_title = short_title[:-7].strip()
        if short_title.endswith("HUNTER"):
            short_title = short_title[:-6].strip()
        if short_title.endswith("MONSTER"):
            short_title = short_title[:-7].strip()
        if short_title.endswith("ODOR"):
            short_title = short_title[:-4].strip()
        if short_title.endswith("POISON"):
            short_title = short_title[:-6].strip()
        if short_title.endswith("STATIC"):
            short_title = short_title[:-6].strip()
        if short_title.endswith("TAXIDERMY"):
            short_title = short_title[:-9].strip()
        if short_title.endswith("VENOMBLOCK"):
            short_title = short_title[:-10].strip()
        if short_title.endswith("WRANGLER"):
            short_title = short_title[:-8].strip()

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


def process_background_traits(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理背景特性文件（背景特性1.md）。格式特殊：先介绍背景，再给出具体特性。

    每个背景有：背景名（如 挑战者）+ 具体特性名（如 怪物挑战者）。
    我们按具体特性名拆分。
    """
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 检测具体特性标题行：以中文名开头，后面有英文
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        # 匹配 "怪物挑战者Monster Challenger" 这种格式
        m = re.match(r"([一-鿿][一-鿿\w]*)\s*([A-Z][A-Za-z\s]*)", s)
        if m:
            first = m.group(1)
            if first in KNOWN_LABELS or first in {"新背景特性", "捕食者与猎物", "挑战者", "学者", "追踪者", "幸存者"}:
                continue
            # 确认这是具体特性名（不是背景名）
            if first.startswith("怪物"):
                starts.append((i, s))

    if not starts:
        stats["errors"].append(f"{source_file} 中未找到有效特性标题")
        return

    ensure_header(target_path, header)

    for idx, (start_idx, title_line) in enumerate(starts):
        end_idx = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        short_title = title_line.split(" ")[0].strip()
        short_title = re.sub(r'[\(（].*$', '', short_title).strip()
        # 修正：如果标题包含英文跨行（如 怪物挑战者Monster），只保留中文部分
        m = re.match(r'([一-鿿][一-鿿\w]*)', short_title)
        if m:
            short_title = m.group(1)
        # 修正：如果标题以 Monster 结尾（因为英文跨行），去掉 Monster
        if short_title.endswith("Monster"):
            short_title = short_title[:-7].strip()

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


def main():
    stats = {"added": 0, "skipped": 0, "errors": []}
    duplicates = []
    plan_sections = []
    skipped_files = []

    # 1. 职业变体
    process_source_sections(SECTIONS, stats, duplicates, plan_sections)

    # 2. 专长
    process_auto_split_file(
        "专长1.md",
        "专长/怪物猎人手册_专长.md",
        "专长",
        "# 怪物猎人手册 专长",
        stats, duplicates, plan_sections
    )

    # 3. 背景特性
    process_background_traits(
        "背景特性1.md",
        "背景/怪物猎人手册_背景特性.md",
        "背景特性",
        "# 怪物猎人手册 背景特性",
        stats, duplicates, plan_sections
    )

    # 4. 魔法物品（page_1617.md）
    process_magic_items(
        "page_1617.md",
        "装备_魔法物品/魔法物品/怪物猎人手册_奇物.md",
        "奇物",
        "# 怪物猎人手册 奇物",
        stats, duplicates, plan_sections
    )

    # 5. 普通物品（普通物品.md）
    process_equipment_file(
        "普通物品.md",
        "装备_魔法物品/货品服务/怪物猎人手册_普通物品.md",
        "普通物品",
        "# 怪物猎人手册 普通物品",
        stats, duplicates, plan_sections
    )

    # 6. 写入计划文件
    plan = {
        "source_book": "怪物猎人手册",
        "source_book_english": "Monster Hunter's Handbook",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/怪物猎人手册MHH",
        "stats": stats,
        "sections": plan_sections,
        "skipped_files": skipped_files,
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 7. 写入报告
    report_lines = [
        "# 怪物猎人手册 整理报告",
        "",
        "## 整理策略",
        "",
        "怪物猎人手册（Monster Hunter's Handbook）内容分散在专长、职业变体、背景特性、魔法物品和普通物品等文件中。",
        "本次将各类型条目按规则合并到 `pf_rules_md_organized/` 下对应分类的已有页面或来源书专属文件中。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/怪物猎人手册MHH/`",
        "",
        "## 处理统计",
        "",
        f"- 新增条目：{stats['added']}",
        f"- 跳过重复：{stats['skipped']}",
        f"- 错误：{len(stats['errors'])}",
        "",
        "## 处理内容",
        "",
        "### 职业变体",
        "",
        "- `变体/page_1213.md` → `职业/混合职业/秘学士/全变体未整合.md`：秘灵猎兵（Psychodermist）",
        "- `变体/page_1228.md` → `职业/基础职业/骑士/护甲大师手册_骑士变体.md`：枪之从者（Disciple of the Pike）",
        "- `变体/page_1236.md` → `职业/基础职业/炼金术师/全变体未整合.md`：泥怪大师（Oozemaster）",
        "- `变体/审判者.md` → `职业/基础职业/审判者/page_78.md`：净化者（Abolisher）",
        "- `变体/德鲁伊.md` → `职业/核心职业/德鲁伊/page_37.md`：真实世界守卫者（Defender of the True World）、绿灾（Green Scourge）",
        "- `变体/圣骑士.md` → `职业/核心职业/圣骑士/page_55.md`：驱魔卫士（Banishing Warden）",
        "- `变体/吟游诗人.md` → `职业/核心职业/吟游诗人/page_38.md`：吹笛人（Luring Piper）",
        "",
        "### 专长",
        "",
        "- `专长1.md` → `专长/怪物猎人手册_专长.md`",
        "  - 生物专攻（Creature Focus）",
        "  - 异怪专精（Focused Aberration Expertise）",
        "  - 动物专精（Focused Animal Expertise）",
        "  - 构装体专精（Focused Construct Expertise）",
        "  - 精类专精（Focused Fey Expertise）",
        "  - 魔法兽专精（Focused Magical Beast Expertise）",
        "  - 泥怪专精（Focused Ooze Expertise）",
        "  - 异界生物专精（Focused Outsider Expertise）",
        "  - 植物专精（Focused Plant Expertise）",
        "  - 不死生物专精（Focused Undead Expertise）",
        "  - 虫类专精（Focused Vermin Expertise）",
        "  - 解剖专家（Anatomical Savant）",
        "  - 破敌审判（Baneful Judgment）",
        "  - 斗牛式（Bull-Catcher Style）",
        "  - 投牛手（Bull-Catcher Toss）",
        "  - 牧牛人（Bull-Catcher Wrangler）",
        "  - 老虎钳（Claw Wrench）",
        "  - 专注目标（Focused Target）",
        "  - 次元跟进（Dimensional Step Up）",
        "  - 扩展猎人战术（Expanded Hunter Tactics）",
        "  - 采集残骸（Harvest Parts）",
        "  - 骇人饰物（Grisly Ornament）",
        "  - 怪物工匠（Monstrous Crafter）",
        "  - 梅花步（Punishing Step）",
        "  - 精通梅花步（Improved Punishing Step）",
        "  - 博学施法者（Knowledgeable Spellcaster）",
        "  - 迷宫专家（Maze Expert）",
        "  - 怪物雷达（Monster Spotter）",
        "  - 怪物伪装（Monstrous Disguise）",
        "  - 怪物假面（Monstrous Masquerade）",
        "  - 大海捞针（Needle in a Haystack）",
        "  - 安抚动物（Pacify Animal）",
        "  - 不羁者（Resisting Grappler）",
        "  - 共享狩猎目标（Shared Quarry）",
        "  - 解除石化专家（Stone to Flesh Savant）",
        "  - 龙类专精（Focused Dragon Expertise）",
        "",
        "### 背景特性",
        "",
        "- `背景特性1.md` → `背景/怪物猎人手册_背景特性.md`",
        "  - 挑战者（Challenger）/ 怪物挑战者（Monster Challenger）",
        "  - 学者（Scholar）/ 怪物学者（Monster Scholar）",
        "  - 追踪者（Stalker）/ 怪物追踪者（Monster Stalker）",
        "  - 幸存者（Survivor）/ 怪物幸存者（Monster Survivor）",
        "",
        "### 魔法物品",
        "",
        "- `page_1617.md` → `装备_魔法物品/魔法物品/怪物猎人手册_奇物.md`",
        "  - 骨持者的刀具（Bone Bearer's Cutter）",
        "  - 侦测飞镖（Detecting Dart）",
        "  - 融合披风（Melding Cloak）",
        "  - 怪物染料（Monstrous Dye）",
        "  - 兽之力项链（Necklace of Beast's Might）",
        "  - 巢穴探测器（Nest Revealer）",
        "  - 穿透型磨刀石（Penetrating Whetstone）",
        "  - 口袋猎物（Pocket Prey）",
        "",
        "### 普通物品",
        "",
        "- `普通物品.md` → `装备_魔法物品/货品服务/怪物猎人手册_普通物品.md`",
        "  - 猎兽哨（Beast-Hunter Whistle）",
        "  - 瓶装麝香（Bottled Musk）",
        "  - 化学防护剂（Chemical Ward）",
        "  - 展示架（Display Stand）",
        "  - 狩猎指南（Hunter's Manual）",
        "  - 怪物诱饵（Monster Bait）",
        "  - 怪物假人（Monster Dummy）",
        "  - 怪物猎人工具包（Monster Hunter's Kit）",
        "  - 臭气棒（Odor Stalk）",
        "  - 毒液海绵（Poison Sponge）",
        "  - 静电羊毛（Static Wool）",
        "  - 标本制作工具（Taxidermy Tools）",
        "  - 毒液阻断剂（Venomblock）",
        "  - 牧者手套（Wrangler's Gloves）",
        "",
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

    # 8. 重复记录
    if duplicates:
        dup_lines = ["", "", "## 怪物猎人手册（Monster Hunter's Handbook）", "", f"**发现时间**：2026-06-19", ""]
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
    if skipped_files:
        for sf in skipped_files:
            print(f"  SKIPPED: {sf['file']} — {sf['reason']}")


if __name__ == "__main__":
    main()
