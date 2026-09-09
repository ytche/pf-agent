#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 护甲大师手册（Armor Master's Handbook）内容到已有分类目录。

本次处理：
- 专长：page_375.md、page_1089.md、page_1184.md
- 防具附魔：防具附魔1.md
- 特定魔法防具：特殊魔法防具.md
- 特殊材料：特殊材料3.md
- 背景特性：背景特性50.md
- 职业变体：魔战士、战士、圣武士、战斗祭司、骑士

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
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/护甲大师手册")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "ARMOR_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "ARMOR_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")
PROBLEM_RECORD_PATH = os.path.join(BASE, "未整理目录整理问题记录.md")

SOURCE_NOTE_TEMPLATE = "> 来源：护甲大师手册（Armor Master's Handbook），页码见原书，未整理 → 护甲大师手册 → {section_title}"

# 职业变体条目配置
# 注意：源文件名与内容可能不一致，已按实际内容调整
SECTIONS = [
    # 魔战士变体（变体/魔战士.md）
    {"source": "变体/魔战士.md", "title": "战甲智库", "english": "Armored Battlemage", "cls": "魔战士", "section_title": "变体", "target": "职业/基础职业/魔战士/page_82.md", "marker": "战甲智库"},
    # 战士变体（变体/page_376.md）
    {"source": "变体/page_376.md", "title": "用心棒", "english": "Yojimbo", "cls": "战士", "section_title": "变体", "target": "职业/核心职业/战士/page_49.md", "marker": "用心棒"},
    # 战士变体（变体/page_397.md）
    {"source": "变体/page_397.md", "title": "摩尔苏恩防御者", "english": "Molthuni Defender", "cls": "战士", "section_title": "变体", "target": "职业/核心职业/战士/page_49.md", "marker": "摩尔苏恩防御者"},
    # 战斗祭司变体（变体/page_422.md）
    {"source": "变体/page_422.md", "title": "盾卫者", "english": "Shieldbearer", "cls": "战斗祭司", "section_title": "变体", "target": "职业/混合职业/战斗祭司/page_43.md", "marker": "盾卫者"},
    # 圣武士变体（变体/page_423.md）
    {"source": "变体/page_423.md", "title": "圣使", "english": "Legate", "cls": "圣武士", "section_title": "变体", "target": "职业/核心职业/圣骑士/page_55.md", "marker": "圣使"},
    # 骑士变体（变体/page_1233.md）
    {"source": "变体/page_1233.md", "title": "阿尼萨恩特骑士", "english": "Knight of Arnisant", "cls": "骑士", "section_title": "变体", "target": "职业/基础职业/骑士/护甲大师手册_骑士变体.md", "marker": "阿尼萨恩特骑士"},
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
    # 如果标记包含换行符，进行跨行匹配
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
    marker_key = f"<!-- ARMOR-source:{section['source']}:{section['title']} -->"
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
    marker = f"<!-- ARMOR-source:{section['source']}:{section['title']} -->"
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


def process_auto_split_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """对专长文件按自动检测的标题行拆分并合并。"""
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
    """处理单文件多条目（如防具附魔、特定魔法防具、特殊材料、背景特性）。

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


def process_single_material(stats, duplicates, plan_sections):
    """处理特殊材料3.md（虚空玻璃）。该文件标题无 **，直接作为单一条目处理。"""
    source_file = "特殊材料3.md"
    target_path = "装备_魔法物品/特殊材料/护甲大师手册_特殊材料.md"
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)
    sec = {
        "source": source_file,
        "title": "虚空玻璃",
        "english": "Voidglass",
        "target": target_path,
        "section_title": "特殊材料",
    }

    full_target = os.path.join(ORG_BASE, target_path)
    target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

    present, reason = already_present(target_text, sec)
    if present:
        duplicates.append({
            "source": source_file,
            "title": sec["title"],
            "english": sec["english"],
            "target": target_path,
            "reason": reason,
        })
        stats["skipped"] += 1
        plan_sections.append({**sec, "action": "skipped", "reason": reason})
        return

    ensure_header(target_path, "# 护甲大师手册 特殊材料")

    # 手动构建追加块
    marker = f"<!-- ARMOR-source:{source_file}:{sec['title']} -->"
    note = SOURCE_NOTE_TEMPLATE.format(section_title=sec["section_title"])
    result = [marker, "**虚空玻璃 (Voidglass)**", note]
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

    # 1. 职业变体
    process_source_sections(SECTIONS, stats, duplicates, plan_sections)

    # 2. 专长（合并到同一个文件）
    feat_target = "专长/护甲大师手册_专长.md"
    feat_header = "# 护甲大师手册 专长"
    for feat_file in ["page_375.md", "page_1089.md", "page_1184.md"]:
        process_auto_split_file(feat_file, feat_target, "专长", feat_header, stats, duplicates, plan_sections)

    # 3. 防具附魔
    process_single_file(
        "防具附魔1.md",
        "装备_魔法物品/防具附魔/护甲大师手册_防具附魔.md",
        "防具附魔",
        "# 护甲大师手册 防具附魔",
        stats, duplicates, plan_sections
    )

    # 4. 特定魔法防具
    process_single_file(
        "特殊魔法防具.md",
        "装备_魔法物品/特定魔法防具/护甲大师手册_特定魔法防具.md",
        "特定魔法防具",
        "# 护甲大师手册 特定魔法防具",
        stats, duplicates, plan_sections
    )

    # 5. 特殊材料（单一条目，标题无 **）
    process_single_material(stats, duplicates, plan_sections)

    # 6. 背景特性
    process_single_file(
        "背景特性50.md",
        "背景/护甲大师手册_背景特性.md",
        "背景特性",
        "# 护甲大师手册 背景特性",
        stats, duplicates, plan_sections
    )

    # 7. 写入计划文件
    plan = {
        "source_book": "护甲大师手册",
        "source_book_english": "Armor Master's Handbook",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/护甲大师手册",
        "stats": stats,
        "sections": plan_sections,
        "skipped_files": [],
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 8. 写入报告
    report_lines = [
        "# 护甲大师手册 整理报告",
        "",
        "## 整理策略",
        "",
        "护甲大师手册（Armor Master's Handbook）内容分散在专长、防具附魔、特定魔法防具、特殊材料、背景特性、职业变体等文件中。",
        "本次将所有规则条目按类型合并到 `pf_rules_md_organized/` 下对应分类目录。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/护甲大师手册/`",
        "",
        "## 处理统计",
        "",
        f"- 新增条目：{stats['added']}",
        f"- 跳过重复：{stats['skipped']}",
        f"- 错误：{len(stats['errors'])}",
        "",
        "## 处理内容",
        "",
        "- 专长：page_375.md、page_1089.md、page_1184.md → `专长/护甲大师手册_专长.md`",
        "- 防具附魔：防具附魔1.md → `装备_魔法物品/防具附魔/护甲大师手册_防具附魔.md`",
        "- 特定魔法防具：特殊魔法防具.md → `装备_魔法物品/特定魔法防具/护甲大师手册_特定魔法防具.md`",
        "- 特殊材料：特殊材料3.md → `装备_魔法物品/特殊材料/护甲大师手册_特殊材料.md`",
        "- 背景特性：背景特性50.md → `背景/护甲大师手册_背景特性.md`",
        "- 职业变体：",
        "  - 战甲智库（魔战士）→ `职业/基础职业/魔战士/page_82.md`",
        "  - 用心棒（战士）→ `职业/核心职业/战士/page_49.md`",
        "  - 摩尔苏恩防御者（战士）→ `职业/核心职业/战士/page_49.md`",
        "  - 圣使（圣武士）→ `职业/核心职业/圣骑士/page_55.md`",
        "  - 盾卫者（战斗祭司）→ `职业/混合职业/战斗祭司/page_43.md`",
        "  - 阿尼萨恩特骑士（骑士）→ `职业/基础职业/骑士/护甲大师手册_骑士变体.md`",
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

    # 9. 重复记录
    if duplicates:
        dup_lines = ["", "", "## 护甲大师手册（Armor Master's Handbook）", "", f"**发现时间**：2026-06-19", ""]
        dup_lines.append("| 来源文件 | 条目 | 目标文件 | 备注 |")
        dup_lines.append("|----------|------|----------|------|")
        for d in duplicates:
            en = f" / {d['english']}" if d["english"] else ""
            dup_lines.append(f"| {d['source']} | {d['title']}{en} | {d['target']} | {d['reason']} |")
        dup_lines.append("")
        with open(DUP_RECORD_PATH, "a", encoding="utf-8") as f:
            f.write("\n".join(dup_lines))

    # 10. 问题记录（避免重复追加）
    if os.path.exists(PROBLEM_RECORD_PATH):
        problem_text = open(PROBLEM_RECORD_PATH, "r", encoding="utf-8").read()
    else:
        problem_text = ""

    def ensure_problem(anchor, block):
        nonlocal problem_text
        if anchor not in problem_text:
            problem_text += block
            with open(PROBLEM_RECORD_PATH, "a", encoding="utf-8") as f:
                f.write(block)

    ensure_problem("ARMOR-FEATS", """

## 护甲大师手册（Armor Master's Handbook）

### ARMOR-FEATS：专长文件标题跨行

- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：`影响轻微`
- **涉及文件**：`page_375.md`、`page_1089.md`、`page_1184.md`
- **问题描述**：部分专长的中文名称和英文名称跨行（如 `**龙之战甲(Dragon` + `Armor)PFS可**`）。脚本通过 `detect_title_starts` 自动检测标题行，并合并跨行标题。
- **当前处理**：已使用 `process_auto_split_file` 处理，按标题自动拆分并合并到 `专长/护甲大师手册_专长.md`。
- **备注**：需人工复核拆分边界是否正确。
""")

    print(f"整理完成：新增 {stats['added']} 条，跳过 {stats['skipped']} 条，错误 {len(stats['errors'])} 条。")
    if stats["errors"]:
        for e in stats["errors"]:
            print("  ERROR:", e)


if __name__ == "__main__":
    main()
