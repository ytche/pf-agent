#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 地城探险者手册（Dungeon Explorer's Handbook）内容到已有分类目录。

本次处理：
- 职业变体：
  - 炽热火炬手（Blazing Torchbearer）→ 炼金术师
  - 马夫（Groom）→ 游侠
  - 工兵（Sapper）→ 盗贼
- 背景特性：背景特性42.md（1 个地区背景）
- 物品：物品6.md（3 个标准格式条目 + 2 个表格格式条目）

跳过：
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
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/地城探险者手册DH")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "DH_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "DH_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")
PROBLEM_RECORD_PATH = os.path.join(BASE, "未整理目录整理问题记录.md")

SOURCE_NOTE_TEMPLATE = "> 来源：地城探险者手册（Dungeon Explorer's Handbook）DH，页码见原书，未整理 → 地城探险者手册DH → {section_title}"

# 职业变体条目配置
SECTIONS = [
    # 炼金术师变体 - 已存在，设置 duplicate_skip 用于检测
    {"source": "变体/page_535.md", "title": "炽热火炬手", "english": "Blazing Torchbearer", "cls": "炼金术师", "section_title": "变体", "target": "职业/基础职业/炼金术师/全变体未整合.md", "marker": "炽热火炬手", "duplicate_skip": True, "title_format": "inline_body"},
    # 游侠变体 - 标题无 **
    {"source": "变体/page_536.md", "title": "马夫", "english": "Groom", "cls": "游侠", "section_title": "变体", "target": "职业/核心职业/游侠/page_51.md", "marker": "马夫", "duplicate_skip": True, "title_format": "no_bold"},
    # 盗贼变体 - 标题和正文挤在一起
    {"source": "变体/page_537.md", "title": "工兵", "english": "Sapper", "cls": "盗贼", "section_title": "变体", "target": "职业/核心职业/盗贼/page_49.md", "marker": "工兵", "duplicate_skip": True, "title_format": "inline_body"},
]

KNOWN_LABELS = {
    "制造要求", "需求", "制造成本", "制造条件", "灵光", "位置", "栏位", "价格",
    "施法者等级", "重量", "类别", "描述", "来源", "出处", "效果", "先决条件",
    "专长效果", "通常", "特殊说明", "拥有此专长前的正常情况", "好处", "学派",
    "施放时间", "成分", "技能检定", "距离", "区域", "持续时间", "豁免", "法术抗力",
    "反冲", "失败", "类型", "动作", "重试", "特殊规则", "检定", "制造DC", "分类",
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
    marker_key = f"<!-- DH-source:{section['source']}:{section['title']} -->"
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
    marker = f"<!-- DH-source:{section['source']}:{section['title']} -->"
    result = [marker]
    result.extend(title_lines)
    result.append(note)
    result.extend(body_lines)
    if result and result[-1].strip() != "":
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def build_append_block_variant(section, section_lines, section_title=None, title_format=None):
    """为格式混乱的变体文件构建追加块。

    title_format: 特殊标题格式处理
      - 'no_bold': 标题没有 **，需要手动加粗
      - 'inline_body': 标题和正文在同一行，需要拆分
    """
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title or section.get("section_title", ""))
    marker = f"<!-- DH-source:{section['source']}:{section['title']} -->"

    # 清理内联格式
    section_lines = normalize_section_lines(section_lines)

    if title_format == 'no_bold':
        # 第一行是标题，没有 **，格式如：马夫(游侠变体)GROOM新郎同义词
        first_line = section_lines[0].strip()
        # 提取中文名
        m = re.match(r'([一-鿿][一-鿿\w]*)', first_line)
        if m:
            cn = m.group(1)
            # 尝试提取英文名（在括号内）
            en_m = re.search(r'[（(]([A-Za-z][A-Za-z\s\-\']*)[）)]', first_line)
            en = en_m.group(1) if en_m else ""
            if en:
                title_line = f"**{cn}（{en}）**"
            else:
                title_line = f"**{cn}**"
            # 剩余部分作为正文
            remaining = first_line[len(cn):].strip()
            # 去掉括号内的英文名和额外文字
            remaining = re.sub(r'[（(][A-Za-z][A-Za-z\s\-\']*[）)]', '', remaining).strip()
            remaining = re.sub(r'新郎同义词', '', remaining).strip()
            remaining = re.sub(r'[（(]\w+变体[）)]', '', remaining).strip()
            # 去掉可能残留的英文单词（如 GROOM）
            remaining = re.sub(r'\b[A-Z]{2,}\b', '', remaining).strip()
            body_start = [remaining] if remaining else []
            body_lines = body_start + section_lines[1:]
        else:
            title_line = f"**{section['title']}**"
            body_lines = section_lines
        result = [marker, title_line, note]
        result.extend(body_lines)

    elif title_format == 'inline_body':
        # 第一行标题和正文挤在一起，如：**工兵**盗贼变体SAPPER**工兵是...
        first_line = section_lines[0].strip()
        # 提取 **工兵** 部分
        m = re.match(r'(\*\*[一-鿿][一-鿿\w]*\*\*)(.*)', first_line)
        if m:
            title_line = m.group(1)
            remaining = m.group(2).strip()
            # 去掉 "盗贼变体SAPPER" 等前缀文字
            remaining = re.sub(r'盗贼变体\w+', '', remaining).strip()
            remaining = re.sub(r'炼金师变体\w+', '', remaining).strip()
            # 如果剩余部分以 ** 开头，说明正文开始
            if remaining.startswith('**'):
                body_start = [remaining]
            else:
                body_start = [remaining] if remaining else []
            body_lines = body_start + section_lines[1:]
        else:
            title_line = f"**{section['title']}**"
            body_lines = section_lines
        result = [marker, title_line, note]
        result.extend(body_lines)

    else:
        # 默认处理
        title_lines, body_lines = split_title_body(section_lines)
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
            # 使用特殊格式处理
            title_format = sec.get("title_format")
            block = build_append_block_variant(sec, section_lines, title_format=title_format)
            append_to_target(target_path, block)
            stats["added"] += 1
            plan_sections.append({**sec, "action": "added"})


def process_background_traits(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理背景特性文件。

    背景特性42.md 格式：标题无 **，中文名开头，后接英文（可能跨行）。
    需要特殊处理：标题没有加粗，需要手动构造标题行。
    """
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 检测背景特性标题：中文名开头，后接英文（可能在同一行或下一行）
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or len(s) > 80:
            continue
        # 跳过说明文字
        if s.startswith("出自《") or s.startswith("类型：") or s.startswith("需求："):
            continue
        m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", s)
        if not m:
            continue
        first = m.group(1)
        if first in KNOWN_LABELS:
            continue
        starts.append((i, s))

    if not starts:
        stats["errors"].append(f"{source_file} 中未找到有效标题")
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
        # 背景特性使用特殊格式处理（标题无 **）
        block = build_append_block_variant(sec, section_lines, section_title=section_title, title_format="no_bold")
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def process_items_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理物品文件。

    物品6.md 包含：
    - 3 个标准格式条目（干冰油、发条响尾蛇、特种烟玉），以 ** 开头
    - 2 个表格格式条目（盗贼戒指、盗贼工具延长器），以 | 开头
    """
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    raw_lines = load_lines(src_path)

    # 表格行可能在单元格内部被硬换行拆成多行，先合并成完整行
    lines = []
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        if line.strip().startswith("|") and not line.rstrip().endswith("|"):
            combined = line
            while i + 1 < len(raw_lines):
                i += 1
                combined += "\n" + raw_lines[i]
                if raw_lines[i].rstrip().endswith("|"):
                    break
            lines.append(combined)
        else:
            lines.append(line)
        i += 1

    # 检测标准格式条目（以 ** 开头）
    standard_starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("**"):
            rest = s[2:]
            m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", rest)
            if m:
                first = m.group(1)
                if first not in KNOWN_LABELS:
                    standard_starts.append((i, s, first))

    # 检测表格格式条目（以 | 开头，包含中文名+英文名）
    table_starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("|"):
            # 跨行单元格先展平为空格便于匹配
            flat = re.sub(r"\s+", " ", s)
            # 提取表格中的中文名和英文名
            m = re.search(r"([一-鿿]{2,})\s*[(（]([A-Za-z][A-Za-z\s'\-]*)[)）]", flat)
            if m:
                cn = m.group(1)
                en = m.group(2).strip()
                if cn not in KNOWN_LABELS:
                    table_starts.append((i, s, cn, en))

    all_starts = []
    # 标准格式条目
    for idx, line, title in standard_starts:
        all_starts.append((idx, line, title, "standard"))
    # 表格格式条目
    for idx, line, title, en in table_starts:
        all_starts.append((idx, line, title, "table"))

    # 按行号排序
    all_starts.sort(key=lambda x: x[0])

    if not all_starts:
        stats["errors"].append(f"{source_file} 中未找到有效条目")
        return

    ensure_header(target_path, header)

    for idx, (start_idx, title_line, short_title, fmt) in enumerate(all_starts):
        end_idx = all_starts[idx + 1][0] if idx + 1 < len(all_starts) else len(lines)

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

        # 表格格式需要特殊处理：去掉 Markdown 表格语法，转为纯文本
        if fmt == "table":
            block = build_table_item_block(sec, section_lines, section_title=section_title)
        else:
            block = build_append_block(sec, section_lines, section_title=section_title)
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def build_table_item_block(section, section_lines, section_title=None):
    """为表格格式的物品条目构建追加块，把跨行单元格展平为单行。"""
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title or section.get("section_title", ""))
    marker = f"<!-- DH-source:{section['source']}:{section['title']} -->"

    # 合并同一单元格内的硬换行，并按 '|' 取第一个单元格
    raw_cell_parts = []
    for line in section_lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("|"):
            content = s[1:]
            if content.endswith("|"):
                content = content[:-1]
            content = content.strip()
            if re.match(r'^\s*[-\s|]+\s*$', content):
                continue
            parts = content.split("|")
            if parts:
                cell = parts[0].strip()
                if cell:
                    raw_cell_parts.append(cell)
        else:
            raw_cell_parts.append(s)

    # 把整个单元格内容展平成一行，清理多余空白
    full_cell = " ".join(raw_cell_parts)
    full_cell = re.sub(r"\s+", " ", full_cell).strip()

    title_cn = section["title"]
    title_en = section.get("english", "")
    if not title_en:
        m = re.search(r'[（(]([A-Za-z][A-Za-z\s\'\-]*)[）)]', full_cell)
        if m:
            title_en = m.group(1).strip()

    if title_en:
        title_line = f"**{title_cn}（{title_en}）**"
    else:
        title_line = f"**{title_cn}**"

    # 去掉单元格开头的标题，避免重复
    body = full_cell
    if body.startswith(title_cn):
        body = body[len(title_cn):].strip()
    body = re.sub(r'^[（(][A-Za-z][A-Za-z\s\'\-]*[）)]\s*', '', body).strip()

    result = [marker, title_line, note]
    if body:
        result.append(body)
    if result and result[-1].strip() != "":
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def main():
    stats = {"added": 0, "skipped": 0, "errors": []}
    duplicates = []
    plan_sections = []
    skipped_files = []

    # 1. 职业变体
    process_source_sections(SECTIONS, stats, duplicates, plan_sections)

    # 2. 背景特性
    process_background_traits(
        "背景特性42.md",
        "背景/地城探险者手册DH_背景特性.md",
        "背景特性",
        "# 地城探险者手册 背景特性",
        stats, duplicates, plan_sections
    )

    # 3. 物品
    process_items_file(
        "物品6.md",
        "装备_魔法物品/货品服务/地城探险者手册DH_物品.md",
        "物品",
        "# 地城探险者手册 物品",
        stats, duplicates, plan_sections
    )

    # 4. 写入计划文件
    plan = {
        "source_book": "地城探险者手册",
        "source_book_english": "Dungeon Explorer's Handbook",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/地城探险者手册DH",
        "stats": stats,
        "sections": plan_sections,
        "skipped_files": skipped_files,
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 5. 写入报告
    report_lines = [
        "# 地城探险者手册 整理报告",
        "",
        "## 整理策略",
        "",
        "地城探险者手册（Dungeon Explorer's Handbook）内容分散在职业变体、背景特性和物品文件中。",
        "本次将各类型条目按规则合并到 `pf_rules_md_organized/` 下对应分类的已有页面或来源书专属文件中。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/地城探险者手册DH/`",
        "",
        "## 处理统计",
        "",
        f"- 新增条目：{stats['added']}",
        f"- 跳过重复：{stats['skipped']}",
        f"- 错误/跳过文件：{len(stats['errors'])}",
        "",
        "## 处理内容",
        "",
        "### 职业变体",
        "",
        "- `变体/page_535.md` → `职业/基础职业/炼金术师/全变体未整合.md`：炽热火炬手（Blazing Torchbearer）",
        "- `变体/page_536.md` → `职业/核心职业/游侠/page_51.md`：马夫（Groom）",
        "- `变体/page_537.md` → `职业/核心职业/盗贼/page_49.md`：工兵（Sapper）",
        "",
        "### 背景特性",
        "",
        "- `背景特性42.md` → `背景/地城探险者手册DH_背景特性.md`",
        "  - 光明前途（Destined for Greatness）",
        "",
        "### 物品",
        "",
        "- `物品6.md` → `装备_魔法物品/货品服务/地城探险者手册DH_物品.md`",
        "  - 干冰油（Cardice Oil）",
        "  - 发条响尾蛇（Key-wound rattler）",
        "  - 特种烟玉（Specialty Smoke Pellet）",
        "  - 盗贼戒指（Thieves' ring）",
        "  - 盗贼工具延长器（Thieves' tool extenders）",
        "",
    ]
    if stats["errors"]:
        report_lines.extend(["", "## 错误", ""])
        for e in stats["errors"]:
            report_lines.append(f"- {e}")
    if duplicates:
        report_lines.extend(["", "## 重复/跳过项", ""])
        for d in duplicates:
            en = f" / {d['english']}" if d['english'] else ""
            report_lines.append(f"- `{d['source']}` `{d['title']}{en}` → `{d['target']}`（原因：{d['reason']}）")
    report_lines.extend(["", "## 验证清单", "", "- [ ] 原目录未被修改", "- [ ] 新增条目均出现 `> 来源：` 标注", "- [ ] 标注位于条目标题下一行", "- [ ] 未重复追加", "- [ ] 进度文档已更新", "- [ ] 已提交 Git", ""])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    # 6. 重复记录
    if duplicates:
        dup_lines = ["", "", "## 地城探险者手册（Dungeon Explorer's Handbook）", "", f"**发现时间**：2026-06-19", ""]
        dup_lines.append("| 来源文件 | 条目 | 目标文件 | 备注 |")
        dup_lines.append("|----------|------|----------|------|")
        for d in duplicates:
            en = f" / {d['english']}" if d['english'] else ""
            dup_lines.append(f"| {d['source']} | {d['title']}{en} | {d['target']} | {d['reason']} |")
        dup_lines.append("")
        with open(DUP_RECORD_PATH, "a", encoding="utf-8") as f:
            f.write("\n".join(dup_lines))

    print(f"整理完成：新增 {stats['added']} 条，跳过 {stats['skipped']} 条，错误/跳过文件 {len(stats['errors'])} 条。")
    if stats["errors"]:
        for e in stats["errors"]:
            print("  ERROR:", e)
    if skipped_files:
        for sf in skipped_files:
            print(f"  SKIPPED: {sf['file']} — {sf['reason']}")


if __name__ == "__main__":
    main()
