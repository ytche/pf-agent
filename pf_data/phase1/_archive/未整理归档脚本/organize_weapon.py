#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 武器大师手册（Weapon Master's Handbook）内容到已有分类目录。

本次处理：
- 专长：page_369.md、page_370.md、page_371.md、page_373.md、page_419.md、page_420.md、page_372.md（进阶武器训练能力也按专长处理）
- 魔法武器/特殊能力：page_421.md（仅合并标题清晰的武器条目；跳过后半段“剧透-专长速查”的勇毅专长）
- 武器设计规则：page_774.md
- 职业变体：变体/page_363.md ~ page_367.md（5 个文件）

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
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/武器大师手册")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "WEAPON_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "WEAPON_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")
PROBLEM_RECORD_PATH = os.path.join(BASE, "未整理目录整理问题记录.md")

SOURCE_NOTE_TEMPLATE = "> 来源：武器大师手册（Weapon Master's Handbook），页码见原书，未整理 → 武器大师手册 → {section_title}"

# 职业变体配置（按源文件分组）
# 注意：page_367.md 包含两个变体（瓦里西亚我流战士、魔导具大师），需分别配置
SECTIONS = [
    # 游侠变体
    {"source": "变体/page_363.md", "title": "伊舒瑞安神射手", "english": "Ilsurian Archers", "cls": "游侠", "section_title": "变体", "target": "职业/核心职业/游侠/page_58.md", "marker": "**伊舒瑞安神射手 Ilsurian"},
    # 战斗祭司变体
    {"source": "变体/page_364.md", "title": "摩尔苏恩随军神父", "english": "Molthuni Arsenal Chaplain", "cls": "战斗祭司", "section_title": "变体", "target": "职业/混合职业/战斗祭司/page_125.md", "marker": "**摩尔苏恩随军神父 Molthuni"},
    # 游荡剑客变体
    {"source": "变体/page_365.md", "title": "龙德勒洛剑客", "english": "Rondelero Swashbucklers", "cls": "游荡剑客", "section_title": "变体", "target": "职业/混合职业/游荡剑客/page_120.md", "marker": "**龙德勒洛剑客 Rondelero"},
    # 圣武士变体
    {"source": "变体/page_366.md", "title": "神炼勇士", "english": "Tempered Champions", "cls": "圣骑士", "section_title": "变体", "target": "职业/核心职业/圣骑士/page_55.md", "marker": "**神炼勇士 Tempered"},
    # 战士变体 - 瓦里西亚我流战士
    {"source": "变体/page_367.md", "title": "瓦里西亚我流战士", "english": "Varisian Free-Style Fighter", "cls": "战士", "section_title": "变体", "target": "职业/核心职业/战士/page_49.md", "marker": "**瓦里西亚我流战士 Varisian"},
    # 战士变体 - 魔导具大师（同一文件，第二个变体）
    {"source": "变体/page_367.md", "title": "魔导具大师", "english": "Relic Master", "cls": "战士", "section_title": "变体", "target": "职业/核心职业/战士/page_49.md", "marker": "**魔导具大师 Relic"},
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
    for i, line in enumerate(lines):
        if marker in line:
            return i
    raise ValueError(f"在 {source} 中未找到标记: {marker!r}")


def already_present(target_text, section):
    marker_key = f"<!-- WEAPON-source:{section['source']}:{section['title']} -->"
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
    marker = f"<!-- WEAPON-source:{section['source']}:{section['title']} -->"
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


def process_feat_files(stats, duplicates, plan_sections):
    """处理所有专长文件，合并到单一目标文件。"""
    feat_files = [
        ("专长/page_369.md", "武器掌握专长"),
        ("专长/page_370.md", "流派专长"),
        ("专长/page_371.md", "神圣武器技法"),
        ("专长/page_373.md", "魔法物品掌握专长"),
        ("专长/page_419.md", "战斗技法"),
        ("专长/page_420.md", "种族武器大师"),
        ("page_372.md", "进阶武器训练"),
    ]
    feat_target = "专长/武器大师手册_专长.md"
    header = "# 武器大师手册 专长"
    ensure_header(feat_target, header)

    for source_file, section_title in feat_files:
        src_path = os.path.join(SRC_DIR, source_file)
        if not os.path.exists(src_path):
            stats["errors"].append(f"源文件不存在: {source_file}")
            continue
        lines = load_lines(src_path)
        starts = detect_title_starts(lines)
        if not starts:
            stats["errors"].append(f"{source_file} 中未检测到标题")
            continue

        for idx, (start_idx, title_line) in enumerate(starts):
            end_idx = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
            short_title = title_line.split("（")[0].split(" ")[0].strip("*")
            sec = {
                "source": source_file,
                "title": short_title,
                "english": "",
                "target": feat_target,
                "section_title": section_title,
            }
            full_target = os.path.join(ORG_BASE, feat_target)
            target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

            present, reason = already_present(target_text, sec)
            if present:
                duplicates.append({
                    "source": source_file,
                    "title": short_title,
                    "english": "",
                    "target": feat_target,
                    "reason": reason,
                })
                stats["skipped"] += 1
                plan_sections.append({**sec, "action": "skipped", "reason": reason})
                continue

            section_lines = extract_section(lines, start_idx, end_idx)
            block = build_append_block(sec, section_lines, section_title=section_title)
            append_to_target(feat_target, block)
            stats["added"] += 1
            plan_sections.append({**sec, "action": "added"})


MAGIC_WEAPON_HEADERS = {"魔法武器", "武器特殊能力", "特殊魔法武器", "剧透"}
MAGIC_WEAPON_LABELS = ["价格", "灵光", "施法者等级", "重量", "位置", "制造要求", "制造成本"]
MAGIC_TITLE_RE = re.compile(
    r'^(\*+)?\s*([一-鿿][一-鿿\w]*)\s*[（(]\s*\*{2,}([^*()]+)\*{2,}\s*[）)]'
)
MAGIC_LABEL_SPLIT_RE = re.compile(
    r'(\*\*(?:' + '|'.join(re.escape(l) for l in MAGIC_WEAPON_LABELS) + r')\*\*)'
)


def build_magic_weapon_block(sec, section_lines, section_title):
    """将单行内联标签的魔法武器条目拆分为标准标题+多行正文格式。"""
    # 过滤掉章节标题行和空行
    filtered_lines = []
    for line in section_lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("**") and any(h in s for h in MAGIC_WEAPON_HEADERS):
            continue
        filtered_lines.append(line)

    text = '\n'.join(filtered_lines).strip()
    m = MAGIC_TITLE_RE.match(text)
    if not m:
        # 兜底：把第一行当作标题
        parts = text.splitlines()
        title_line = parts[0].strip()
        body_text = '\n'.join(parts[1:])
    else:
        cn, en = m.group(2), m.group(3).strip()
        title_line = f"**{cn}（{en}）**"
        body_text = text[m.end():]

    # 按已知标签拆分内联正文
    split_parts = MAGIC_LABEL_SPLIT_RE.split(body_text)
    body_lines = []
    for j, part in enumerate(split_parts):
        if j == 0:
            # 标题与第一个标签之间可能有残留的 * 符号
            cleaned = part.strip('* \n')
            if cleaned:
                body_lines.append(cleaned)
        elif j % 2 == 1:
            # 标签部分，如 **价格**
            body_lines.append(part)
        else:
            # 标签内容：把残留 ** 替换为空格，避免格式污染
            cleaned = re.sub(r'\*+', ' ', part).strip()
            if cleaned:
                body_lines.append(cleaned)

    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
    marker = f"<!-- WEAPON-source:{sec['source']}:{sec['title']} -->"
    result = [marker, title_line, note]
    result.extend(body_lines)
    if result[-1].strip() != "":
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def process_magic_weapons(stats, duplicates, plan_sections):
    """处理 page_421.md 魔法武器文件。

    合并武器特殊能力和特殊魔法武器条目；跳过“剧透-专长速查”中间的勇毅专长。
    """
    source_file = "page_421.md"
    target_path = "装备_魔法物品/武器/武器大师手册_魔法武器.md"
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 定位“剧透”区域，用于跳过中间穿插的勇毅专长
    spoiler_idx = None
    for i, line in enumerate(lines):
        if "剧透" in line or "专长速查" in line:
            spoiler_idx = i
            break

    # 检测标题行：中文名（****英文名****）
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        m = MAGIC_TITLE_RE.match(s)
        if not m:
            continue
        title = m.group(2)
        if title in MAGIC_WEAPON_HEADERS:
            continue
        starts.append((i, line, title, m.group(3).strip()))

    if not starts:
        stats["errors"].append(f"{source_file} 中未检测到武器条目标题")
        return

    # 剧透区域结束于剧透后的第一个武器条目，或文件末尾
    spoiler_end = len(lines)
    if spoiler_idx is not None:
        for start_idx, raw_line, title, english in starts:
            if start_idx >= spoiler_idx:
                spoiler_end = start_idx
                break

    ensure_header(target_path, "# 武器大师手册 魔法武器")

    for idx, (start_idx, raw_line, title_cn, english) in enumerate(starts):
        # 跳过剧透区域内的条目
        if spoiler_idx is not None and spoiler_idx <= start_idx < spoiler_end:
            continue
        end_idx = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        # 如果剧透区域穿插在当前条目中间，则截断到剧透之前
        if spoiler_idx is not None and start_idx < spoiler_idx < end_idx:
            end_idx = spoiler_idx
        sec = {
            "source": source_file,
            "title": title_cn,
            "english": english,
            "target": target_path,
            "section_title": "魔法武器",
        }
        full_target = os.path.join(ORG_BASE, target_path)
        target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

        present, reason = already_present(target_text, sec)
        if present:
            duplicates.append({
                "source": source_file,
                "title": title_cn,
                "english": english,
                "target": target_path,
                "reason": reason,
            })
            stats["skipped"] += 1
            plan_sections.append({**sec, "action": "skipped", "reason": reason})
            continue

        section_lines = extract_section(lines, start_idx, end_idx)
        block = build_magic_weapon_block(sec, section_lines, section_title="魔法武器")
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def process_weapon_design(stats, duplicates, plan_sections):
    """处理 page_774.md 武器设计规则文件。"""
    source_file = "page_774.md"
    target_path = "规则/武器大师手册_武器设计.md"
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)
    # 整个文件作为一个规则条目处理
    sec = {
        "source": source_file,
        "title": "武器设计",
        "english": "Weapon Design",
        "target": target_path,
        "section_title": "武器设计规则",
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

    # 构建追加块：标题 + 来源标注 + 全文内容
    marker = f"<!-- WEAPON-source:{source_file}:{sec['title']} -->"
    note = SOURCE_NOTE_TEMPLATE.format(section_title=sec["section_title"])
    result = [marker, "**武器设计（Weapon Design）**", note]
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

    # 2. 专长（多个文件合并到单一目标）
    process_feat_files(stats, duplicates, plan_sections)

    # 3. 魔法武器
    process_magic_weapons(stats, duplicates, plan_sections)

    # 4. 武器设计规则
    process_weapon_design(stats, duplicates, plan_sections)

    # 5. 写入计划文件
    plan = {
        "source_book": "武器大师手册",
        "source_book_english": "Weapon Master's Handbook",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/武器大师手册",
        "stats": stats,
        "sections": plan_sections,
        "skipped_files": [],
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 6. 写入报告
    report_lines = [
        "# 武器大师手册 整理报告",
        "",
        "## 整理策略",
        "",
        "武器大师手册（Weapon Master's Handbook）内容分散在专长、变体、魔法武器和规则文件中。",
        "本次将各类型条目按规则合并到 `pf_rules_md_organized/` 下对应分类的已有页面或来源书专属文件中。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/武器大师手册/`",
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
        "以下 7 个文件合并到 `专长/武器大师手册_专长.md`：",
        "",
        "- `page_369.md`：武器掌握专长（近战/远程武器掌握专长）",
        "- `page_370.md`：流派专长（无极流、牙突流、铁碎流、枪舞流、刺剑流、散星流、矢暴流、折翎流）",
        "- `page_371.md`：神圣武器技法（神圣武器技法专长 + 各神祇技法）",
        "- `page_373.md`：魔法物品掌握专长",
        "- `page_419.md`：战斗技法（武器技法专长 + 各类技法）",
        "- `page_420.md`：种族武器大师（种族流派专长）",
        "- `page_372.md`：进阶武器训练（按专长处理）",
        "",
        "### 职业变体",
        "",
        "- `变体/page_363.md` → 游侠/page_58.md：伊舒瑞安神射手（Ilsurian Archers）",
        "- `变体/page_364.md` → 战斗祭司/page_125.md：摩尔苏恩随军神父（Molthuni Arsenal Chaplain）",
        "- `变体/page_365.md` → 游荡剑客/page_120.md：龙德勒洛剑客（Rondelero Swashbucklers）",
        "- `变体/page_366.md` → 圣骑士/page_55.md：神炼勇士（Tempered Champions）",
        "- `变体/page_367.md` → 战士/page_49.md：瓦里西亚我流战士（Varisian Free-Style Fighter）",
        "- `变体/page_367.md` → 战士/page_49.md：魔导具大师（Relic Master）",
        "",
        "### 魔法武器",
        "",
        "- `page_421.md` → `装备_魔法物品/武器/武器大师手册_魔法武器.md`",
        "  - 合并武器特殊能力（推力、穿心、御力、释放、撼地、分裂、吸血）",
        "  - 合并特殊魔法武器（凯连斗殴杯、十字军长剑、盾勋双筒枪、光荣先祖之矛、勇气之刃、阅风者之弓）",
        "  - **跳过** 文件后半段“剧透-专长速查”的勇毅专长（这些属于铳士专长，非武器大师手册原创）",
        "",
        "### 武器设计规则",
        "",
        "- `page_774.md` → `规则/武器大师手册_武器设计.md`",
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

    # 7. 重复记录
    if duplicates:
        dup_lines = ["", "", "## 武器大师手册（Weapon Master's Handbook）", "", f"**发现时间**：2026-06-19", ""]
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
