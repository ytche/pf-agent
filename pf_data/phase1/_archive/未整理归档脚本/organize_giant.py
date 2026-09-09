#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 巨人猎手手册（Giant Slayer's Handbook）内容到已有分类目录。

本次处理：
- 专长：专长51.md（14 个专长 + 1 个故事专长）
- 职业变体：
  - 泰坦战士（Titan Fighter）→ 战士
  - 歌利亚德鲁伊（Goliath Druid）→ 德鲁伊
  - 阴险纠缠者（Vexing Dodger）→ 盗贼
- 新武器：新武器1.md（4 种武器）
- 新物品：新物品.md（10 件魔法物品 + 1 件炼金物品 + 3 个工具包）
- 装备：装备5.md（4 件普通装备 + 3 个工具包）
- 背景特性：背景特性24.md（6 个地区背景）
- 新技能选项：新技能选项.md（4 项技能新用法）
- 防具附魔：防具附魔3.md（1 个：贴身）
- 武器附魔：武器附魔3.md（2 个：贴身、放缩）

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
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/巨人猎手手册")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "GIANT_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "GIANT_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")
PROBLEM_RECORD_PATH = os.path.join(BASE, "未整理目录整理问题记录.md")
ANALYSIS_PATH = os.path.join(BASE, "GIANT_analysis.md")

SOURCE_NOTE_TEMPLATE = "> 来源：巨人猎手手册（Giant Slayer's Handbook），页码见原书，未整理 → 巨人猎手手册 → {section_title}"

# 职业变体条目配置
SECTIONS = [
    # 战士变体
    {"source": "职业选项/page_1574.md", "title": "泰坦战士", "english": "Titan Fighter", "cls": "战士", "section_title": "变体", "target": "职业/核心职业/战士/page_49.md", "marker": "泰坦战士（Titan Fighter）"},
    # 德鲁伊变体
    {"source": "职业选项/page_399.md", "title": "歌利亚德鲁伊", "english": "Goliath Druid", "cls": "德鲁伊", "section_title": "变体", "target": "职业/核心职业/德鲁伊/page_49.md", "marker": "Goliath"},
    # 盗贼变体
    {"source": "职业选项/盗贼变体.md", "title": "阴险纠缠者", "english": "Vexing Dodger", "cls": "盗贼", "section_title": "变体", "target": "职业/核心职业/盗贼/page_49.md", "marker": "阴险纠缠者（Vexing dodger）"},
]

KNOWN_LABELS = {
    "制造要求", "需求", "制造成本", "制造条件", "灵光", "位置", "栏位", "价格",
    "施法者等级", "重量", "类别", "描述", "来源", "出处", "效果", "先决条件",
    "专长效果", "通常", "特殊说明", "拥有此专长前的正常情况", "好处", "学派",
    "施放时间", "成分", "技能检定", "距离", "区域", "持续时间", "豁免", "法术抗力",
    "反冲", "失败", "类型", "动作", "重试", "特殊规则", "检定",
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
    marker_key = f"<!-- GIANT-source:{section['source']}:{section['title']} -->"
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
    marker = f"<!-- GIANT-source:{section['source']}:{section['title']} -->"
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
    """按自动检测的标题行拆分并合并（用于专长文件）。"""
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


def process_single_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理单文件多条目（如背景特性、新物品）。

    每个条目标题行以 ** 开头，按标题自动拆分。
    """
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


def process_weapons(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理新武器文件。格式：标题行无 **，以中文名开头，后有类型说明。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 检测武器标题：中文名开头，后面有英文或类型说明
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or len(s) > 80:
            continue
        # 跳过章节标题和说明文字
        if s in {"新型武器（本书第24页）", "新工具包"} or s.startswith("![") or s.startswith("("):
            continue
        m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", s)
        if not m:
            continue
        first = m.group(1)
        if first in KNOWN_LABELS:
            continue
        starts.append((i, s))

    if not starts:
        stats["errors"].append(f"{source_file} 中未检测到武器标题")
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


def process_equipment(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理普通装备文件。格式：标题行无 **，以中文名开头，后接英文。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 检测装备标题：中文名开头，后接英文（无括号）
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or len(s) > 80:
            continue
        # 跳过章节标题和说明文字
        if s == "新工具包" or s.startswith("(") or s.startswith("此部分") or s.startswith("你可以"):
            continue
        m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", s)
        if not m:
            continue
        first = m.group(1)
        if first in KNOWN_LABELS:
            continue
        starts.append((i, s))

    if not starts:
        stats["errors"].append(f"{source_file} 中未检测到装备标题")
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


def process_magic_items(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理魔法物品文件。格式：标题行无 **，以中文名开头，后接英文和价格等。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 检测魔法物品标题：中文名开头，后接英文（无括号）
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or len(s) > 80:
            continue
        m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", s)
        if not m:
            continue
        first = m.group(1)
        if first in KNOWN_LABELS:
            continue
        starts.append((i, s))

    if not starts:
        stats["errors"].append(f"{source_file} 中未检测到魔法物品标题")
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


def process_skill_options(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理新技能选项文件。格式：标题行无 **，以中文名开头，后接英文和技能名。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 检测技能选项标题：中文名开头，后接英文和技能名
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or len(s) > 80:
            continue
        m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", s)
        if not m:
            continue
        first = m.group(1)
        if first in KNOWN_LABELS:
            continue
        starts.append((i, s))

    if not starts:
        stats["errors"].append(f"{source_file} 中未检测到技能选项标题")
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


def process_enchantment_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections, enchant_type="防具"):
    """处理附魔文件（防具附魔/武器附魔）。格式：标题行可能有 **，以中文名开头。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 检测附魔标题：中文名开头，先去掉前导 *
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        while s.startswith("*"):
            s = s[1:].strip()
        if not s or len(s) > 80:
            continue
        m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", s)
        if not m:
            continue
        first = m.group(1)
        if first in KNOWN_LABELS:
            continue
        starts.append((i, s))

    if not starts:
        stats["errors"].append(f"{source_file} 中未检测到附魔标题")
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


def main():
    stats = {"added": 0, "skipped": 0, "errors": []}
    duplicates = []
    plan_sections = []
    skipped_files = []

    # 1. 职业变体
    process_source_sections(SECTIONS, stats, duplicates, plan_sections)

    # 2. 专长
    feat_target = "专长/巨人猎手手册_专长.md"
    feat_header = "# 巨人猎手手册 专长"
    process_auto_split_file("专长51.md", feat_target, "专长", feat_header, stats, duplicates, plan_sections)

    # 3. 新武器
    process_weapons(
        "新武器1.md",
        "装备_魔法物品/武器/巨人猎手手册_新武器.md",
        "新武器",
        "# 巨人猎手手册 新武器",
        stats, duplicates, plan_sections
    )

    # 4. 新物品（魔法物品）
    process_magic_items(
        "新物品.md",
        "装备_魔法物品/魔法物品/巨人猎手手册_新物品.md",
        "新物品",
        "# 巨人猎手手册 新物品",
        stats, duplicates, plan_sections
    )

    # 5. 装备（普通装备）
    process_equipment(
        "装备5.md",
        "装备_魔法物品/货品服务/巨人猎手手册_装备.md",
        "装备",
        "# 巨人猎手手册 装备",
        stats, duplicates, plan_sections
    )

    # 6. 背景特性（标题无 **，使用自动标题检测）
    process_auto_split_file(
        "背景特性24.md",
        "背景/巨人猎手手册_背景特性.md",
        "背景特性",
        "# 巨人猎手手册 背景特性",
        stats, duplicates, plan_sections
    )

    # 7. 新技能选项
    process_skill_options(
        "新技能选项.md",
        "技能/巨人猎手手册_新技能选项.md",
        "新技能选项",
        "# 巨人猎手手册 新技能选项",
        stats, duplicates, plan_sections
    )

    # 8. 防具附魔
    process_enchantment_file(
        "防具附魔3.md",
        "装备_魔法物品/防具附魔/巨人猎手手册_防具附魔.md",
        "防具附魔",
        "# 巨人猎手手册 防具附魔",
        stats, duplicates, plan_sections,
        enchant_type="防具"
    )

    # 9. 武器附魔
    process_enchantment_file(
        "武器附魔3.md",
        "装备_魔法物品/武器附魔/巨人猎手手册_武器附魔.md",
        "武器附魔",
        "# 巨人猎手手册 武器附魔",
        stats, duplicates, plan_sections,
        enchant_type="武器"
    )

    # 10. 写入计划文件
    plan = {
        "source_book": "巨人猎手手册",
        "source_book_english": "Giant Slayer's Handbook",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/巨人猎手手册",
        "stats": stats,
        "sections": plan_sections,
        "skipped_files": skipped_files,
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 11. 写入报告
    report_lines = [
        "# 巨人猎手手册 整理报告",
        "",
        "## 整理策略",
        "",
        "巨人猎手手册（Giant Slayer's Handbook）内容分散在专长、职业变体、新武器、新物品、装备、背景特性、新技能选项、防具附魔和武器附魔等文件中。",
        "本次将各类型条目按规则合并到 `pf_rules_md_organized/` 下对应分类的已有页面或来源书专属文件中。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/巨人猎手手册/`",
        "",
        "## 处理统计",
        "",
        f"- 新增条目：{stats['added']}",
        f"- 跳过重复：{stats['skipped']}",
        f"- 错误：{len(stats['errors'])}",
        "",
        "## 处理内容",
        "",
        "### 专长",
        "",
        "- `专长51.md` → `专长/巨人猎手手册_专长.md`",
        "  - 巧夺缴械物（Darting Retrieval）",
        "  - 摔得更狠（Harder They Fall）",
        "  - 躲避投石（Stone Dodger）",
        "  - 抑制再生（Suppress Regeneration）",
        "  - 辗转腾挪（Swing About）",
        "  - 弧线抛投（Arcing Lob）",
        "  - 高呼挑衅（Cry Challenge）",
        "  - 巨人克星施法者（Giant-Bane Caster）",
        "  - 巨人杀手姿态（Giant-Killer Stance）",
        "  - 抓地者（Ground-Grabber）",
        "  - 开山掌（Mountain-Splitting Strike）",
        "  - 致命毒刺（Pernicious Stab）",
        "  - 急爬（Scuttle）",
        "  - 仿巨鬼法术（Yai-Mimic Spell）",
        "  - 巨人之敌（Giant Vendetta，故事专长）",
        "",
        "### 职业变体",
        "",
        "- `职业选项/page_1574.md` → `职业/核心职业/战士/page_49.md`：泰坦战士（Titan Fighter）",
        "- `职业选项/page_399.md` → `职业/核心职业/德鲁伊/page_49.md`：歌利亚德鲁伊（Goliath Druid）",
        "- `职业选项/盗贼变体.md` → `职业/核心职业/盗贼/page_49.md`：阴险纠缠者（Vexing Dodger）",
        "",
        "### 新武器",
        "",
        "- `新武器1.md` → `装备_魔法物品/武器/巨人猎手手册_新武器.md`",
        "  - 萨里沙长矛（Sarissa）",
        "  - 巨型套牛绳（Dire Bolas）",
        "  - 刺矛（Barbed Spear）",
        "  - 爆瓶矛（Flask Pike）",
        "",
        "### 新物品（魔法物品）",
        "",
        "- `新物品.md` → `装备_魔法物品/魔法物品/巨人猎手手册_新物品.md`",
        "  - 伐敌斧（Axe of Felling）",
        "  - 大地之子面罩（Earth Child Faceguard）",
        "  - 轻松缎带（Effortless Lace）",
        "  - 紧抓套牛索（Grasping Bolas）",
        "  - 催眠竖琴（Harp Of Slumber）",
        "  - 冲击手套（Impact Gauntlets）",
        "  - 小鼠罩衣（Manteau Of The Mouse）",
        "  - 萎缩之刃（Shrivel Blade）",
        "  - 走私者投石索（Smuggler's Sling）",
        "  - 巨魔克星涂层（Troll Bane Blanch）",
        "  - 巨魔之血灵药（Trollblood Elixir）",
        "",
        "### 装备（普通装备）",
        "",
        "- `装备5.md` → `装备_魔法物品/货品服务/巨人猎手手册_装备.md`",
        "  - 精金锁链（AdamantineChain）",
        "  - 秘银锁链（MithralChain）",
        "  - 磁石靴（Lodestone Boots）",
        "  - 壁虎手套（Gecko Gloves）",
        "  - 口香糖绳（Gum Rope）",
        "  - 火巨人猎手工具包（Fire Giant Hunter's kit）",
        "  - 霜巨人猎手工具包（Frost Giant Hunter's kit）",
        "  - 巨人巢穴渗透者工具包（Giant Lair Infiltrator's Kit）",
        "",
        "### 背景特性",
        "",
        "- `背景特性24.md` → `背景/巨人猎手手册_背景特性.md`",
        "  - 巨人调查员（Giant Investigator）",
        "  - 巨人闪避者（Giant Dodger）",
        "  - 倾心巨人（Enchanted by Giants）",
        "  - 巨人歧感（Giant Ambivalence）",
        "  - 残虐铸冷心（Chilled by Brutality）",
        "  - 惊惶仆役（Scrambling Servant）",
        "  - 巨人受害者（Giant-Harried）",
        "",
        "### 新技能选项",
        "",
        "- `新技能选项.md` → `技能/巨人猎手手册_新技能选项.md`",
        "  - 佯装无害（Feign Harmlessness，唬骗）",
        "  - 躲在生物身后（Hide behind Creatures，隐匿）",
        "  - 威吓体型更大的生物（Intimidate Larger Creatures，威吓）",
        "  - 植入想法（Plant Notion，唬骗和交涉）",
        "",
        "### 防具附魔",
        "",
        "- `防具附魔3.md` → `装备_魔法物品/防具附魔/巨人猎手手册_防具附魔.md`",
        "  - 贴身（Fitting）",
        "",
        "### 武器附魔",
        "",
        "- `武器附魔3.md` → `装备_魔法物品/武器附魔/巨人猎手手册_武器附魔.md`",
        "  - 贴身（Fitting）",
        "  - 放缩（Resizing）",
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

    # 12. 重复记录
    if duplicates:
        dup_lines = ["", "", "## 巨人猎手手册（Giant Slayer's Handbook）", "", f"**发现时间**：2026-06-19", ""]
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
