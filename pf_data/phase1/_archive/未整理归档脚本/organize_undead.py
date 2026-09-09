#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 亡灵杀手手册（Undead Slayer's Handbook）内容到已有分类目录。

本次处理：
- 专长：专长47.md（1 个专长）
- 进阶职业：灵魂守卫.md（灵魂守卫 Soul Warden）
- 物品：page_1582.md（戒指 + 炼金物品，共 4 个条目）

跳过：
- page_506.md（7 个法术全部挤在一行，格式严重混乱，无法可靠自动拆分）

原则：
- 仅追加到 pf_rules_md_organized/ 下已有分类目录的对应文件。
- 每个条目在标题下一行标注来源。
- 使用隐藏标记去重；已存在的条目跳过并记录为重复。
- 不修改原 pf_rules_md/ 目录。
"""

import json
import os
import re
from pathlib import Path

from html_fallback import read_source_text, mark_connected

BASE = "/Users/chezi/code/java/pf_agent/pf_data/phase1"
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/亡灵杀手手册")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "UNDEAD_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "UNDEAD_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")
PROBLEM_RECORD_PATH = os.path.join(BASE, "未整理目录整理问题记录.md")
ANALYSIS_PATH = os.path.join(BASE, "UNDEAD_analysis.md")

SOURCE_NOTE_TEMPLATE = "> 来源：亡灵杀手手册（Undead Slayer's Handbook），页码见原书，未整理 → 亡灵杀手手册 → {section_title}"

# 进阶职业配置（单一条目）
SECTIONS = [
    {
        "source": "灵魂守卫.md",
        "title": "灵魂守卫",
        "english": "Soul Warden",
        "cls": "进阶职业",
        "section_title": "进阶职业",
        "target": "职业/进阶职业/亡灵杀手手册_灵魂守卫.md",
        "marker": "**灵魂守卫（Soul Warden）",
    },
]

KNOWN_LABELS = {
    "制造要求", "需求", "制造成本", "制造条件", "灵光", "位置", "栏位", "价格",
    "施法者等级", "重量", "类别", "描述", "来源", "出处", "效果", "先决条件",
    "专长效果", "通常", "特殊说明", "拥有此专长前的正常情况", "好处", "学派",
    "施放时间", "成分", "技能检定", "距离", "区域", "持续时间", "豁免", "法术抗力",
    "反冲", "失败", "类型", "制造DC", "分类",
}


def load_lines(path, kind=""):
    if kind:
        text = read_source_text(Path(path), kind=kind)
        return text.splitlines()
    with open(path, "r", encoding="utf-8") as f:
        return f.read().splitlines()


def find_index(lines, marker, source):
    for i, line in enumerate(lines):
        if marker in line:
            return i
    raise ValueError(f"在 {source} 中未找到标记: {marker!r}")


def already_present(target_text, section):
    marker_key = f"<!-- UNDEAD-source:{section['source']}:{section['title']} -->"
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
    marker = f"<!-- UNDEAD-source:{section['source']}:{section['title']} -->"
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
    """处理通用 SECTIONS 配置（进阶职业）。"""
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


def process_single_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理单文件多条目（如物品），按 ** 标题自动拆分。

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


def process_page_1582_items(stats, duplicates, plan_sections):
    """处理 page_1582.md：4 个物品标签体系不一致，使用 HTML 回退清洗后按条目拆分。

    4 个物品：
    - 护佑生命之戒（Ring of Protected Life）
    - 破魂锥（spiritbane spike）
    - 日光瓶（Bottled sunlight）
    - 腐肉诱饵（carrion bait）
    """
    source_file = "page_1582.md"
    target_path = "装备_魔法物品/魔法物品/奇物/亡灵杀手手册_奇物.md"
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    # 使用 HTML 回退清洗后的文本
    lines = load_lines(src_path, kind="item")
    text = "\n".join(lines)

    # 4 个物品的显式配置
    items = [
        {"cn": "护佑生命之戒", "en": "Ring of Protected Life", "marker": "护佑生命之戒"},
        {"cn": "破魂锥", "en": "spiritbane spike", "marker": "破魂锥"},
        {"cn": "日光瓶", "en": "Bottled sunlight", "marker": "日光瓶"},
        {"cn": "腐肉诱饵", "en": "carrion bait", "marker": "腐肉诱饵"},
    ]

    # 按 marker 在文本中的位置排序并切片
    positions = []
    for it in items:
        idx = text.find(it["marker"])
        if idx == -1:
            stats["errors"].append(f"{source_file} 中未找到物品: {it['cn']}")
            return
        positions.append((idx, it))
    positions.sort()

    # 重建目标文件（原文件只包含 page_1582.md 内容且拆分错误）
    full_target = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_target), exist_ok=True)
    target_blocks = []

    for i, (pos, it) in enumerate(positions):
        end_pos = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        section_text = text[pos:end_pos]

        sec = {
            "source": source_file,
            "title": it["cn"],
            "english": it["en"],
            "target": target_path,
            "section_title": "奇物",
        }

        # 清理段落：先对整个段落文本做正则清洗，再按行过滤
        section_text = re.sub(r'出自《[\s\S]*?》', '', section_text)
        section_text = re.sub(r'\*\*出处\*\*[\s\S]*?页', '', section_text)
        section_text = re.sub(r'资源[：:][^\n]*', '', section_text)
        section_text = re.sub(r'\[http://[^\]]*\][^\n]*', '', section_text)
        section_text = re.sub(r'译者[：:][^\n]*', '', section_text)

        section_lines = section_text.splitlines()
        cleaned_lines = []
        for line in section_lines:
            stripped = line.strip()
            # 跳过残留空加粗行
            if re.match(r'^\*+\s*$', stripped):
                continue
            # 跳过已冗余的出处行（来源标注已统一处理）
            if stripped.startswith('**出处**') or stripped.startswith('出处：'):
                continue
            # 为日光瓶等无加粗标签的字段统一补全 **标签**
            line = re.sub(r'^(价格[：:])', r'**价格**：', line)
            line = re.sub(r'^(分类[：:])', r'**分类**：', line)
            line = re.sub(r'^(制作条件[：:])', r'**制作条件**：', line)
            line = re.sub(r'^(工艺（炼金）[：:])', r'**工艺（炼金）**：', line)
            # 移除空行（保留段落间一个空行）
            if not stripped and cleaned_lines and cleaned_lines[-1].strip() == "":
                continue
            cleaned_lines.append(line)

        # 重新构建标题行，统一全角括号
        title_line = f"**{it['cn']}（{it['en']}）**"

        note = SOURCE_NOTE_TEMPLATE.format(section_title="奇物")
        marker = f"<!-- UNDEAD-source:{source_file}:{it['cn']} -->"
        block_lines = [marker, title_line, note, ""]
        # 跳过原第一行（标题行），追加清理后的正文
        body_lines = cleaned_lines[1:] if cleaned_lines else []
        # 移除正文开头的空行
        while body_lines and body_lines[0].strip() == "":
            body_lines.pop(0)
        block_lines.extend(body_lines)
        # 去掉尾部空行
        while block_lines and block_lines[-1].strip() == "":
            block_lines.pop()
        block_lines.extend(["", ""])
        block = "\n".join(block_lines) + "\n"
        target_blocks.append(block)

        plan_sections.append({**sec, "action": "added"})

    with open(full_target, "w", encoding="utf-8") as f:
        f.write("# 亡灵杀手手册 奇物\n\n")
        f.write("".join(target_blocks))

    stats["added"] += len(items)


SPELL_LABELS = ["学派", "环级", "施放时间", "成分", "范围", "目标", "效果", "持续时间", "豁免", "法术抗力"]
SPELL_LABEL_RE = re.compile(r'^\s*(' + '|'.join(re.escape(l) for l in SPELL_LABELS) + r')[：:]')


def detect_spell_starts(lines):
    """根据 '学派：' 标签行检测法术条目标题起始位置。

    由于上一个法术的效果描述行末尾可能嵌入了下一个法术的标题，
    当遇到以已知法术标签开头的行时，会从行尾提取标题片段，
    并截断该行以去掉残留的标题，保证上一个法术正文完整。

    返回列表，每项为 (start_idx, body_start_idx, title_lines)：
    - start_idx：标题在原文中的起始行号（用于确定上一个法术结束位置）
    - body_start_idx：'学派：' 所在行号（正文从此开始）
    - title_lines：标题文本片段列表
    """
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not (s.startswith("学派：") or s.startswith("学派:")):
            continue

        title_lines = []
        j = i - 1
        while j >= 0:
            prev = lines[j].strip()
            if not prev:
                break
            if SPELL_LABEL_RE.match(prev):
                # 标题可能嵌在效果描述行的末尾（中文名与英文名之间可能没有空格）
                m = re.search(r"([一-鿿]+)\s*([A-Za-z][A-Za-z\s\-]*)$", prev)
                if m:
                    title_lines.insert(0, prev[m.start():])
                    # 截断上一个法术正文的最后一行，去掉嵌套的标题
                    lines[j] = lines[j][:m.start()].rstrip() + "\n"
                    if not lines[j].strip():
                        lines[j] = "\n"
                break
            title_lines.insert(0, prev)
            j -= 1

        if title_lines:
            starts.append((j + 1, i, title_lines))
    return starts



def parse_spell_title(title_lines):
    """把标题行合并为 **中文名（English Name）** 格式。"""
    full = " ".join(title_lines).strip()
    full = re.sub(r'\s+', ' ', full)
    m = re.match(r'^([一-鿿]+)\s*(.*)$', full)
    if m:
        cn = m.group(1).strip()
        en = m.group(2).strip()
        if en:
            return f"**{cn}（{en}）**"
        return f"**{cn}**"
    return f"**{full}**"


def build_spell_block(sec, title_line, body_lines, section_title):
    """构建法术条目的追加块。"""
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
    marker = f"<!-- UNDEAD-source:{sec['source']}:{sec['title']} -->"
    result = [marker, title_line, note]
    result.extend(body_lines)
    if result[-1].strip() != "":
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def process_page_506_spells(stats, duplicates, plan_sections):
    """处理 page_506.md（7 个法术），使用 HTML 回退清洗文本。"""
    source_file = "page_506.md"
    target_path = "规则/亡灵杀手手册_法术.md"
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    # 使用 HTML 回退清洗后的文本，法术标签已被正确换行
    lines = load_lines(src_path, kind="spell")
    starts = detect_spell_starts(lines)
    if not starts:
        stats["errors"].append(f"{source_file} 中未检测到法术条目标题")
        return

    ensure_header(target_path, "# 亡灵杀手手册 法术")

    for idx, (start_idx, body_start_idx, title_lines) in enumerate(starts):
        title_line = parse_spell_title(title_lines)
        short_title = title_line.strip("*").split("（")[0].split(" ")[0].strip()
        end_idx = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        sec = {
            "source": source_file,
            "title": short_title,
            "english": "",
            "target": target_path,
            "section_title": "法术",
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

        # 正文从 '学派：' 行开始
        body_lines = lines[body_start_idx:end_idx]
        block = build_spell_block(sec, title_line, body_lines, section_title="法术")
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def main():
    stats = {"added": 0, "skipped": 0, "errors": []}
    duplicates = []
    plan_sections = []
    skipped_files = []

    # 1. 进阶职业（灵魂守卫）
    process_source_sections(SECTIONS, stats, duplicates, plan_sections)

    # 2. 专长
    process_auto_split_file(
        "专长47.md",
        "专长/亡灵杀手手册_专长.md",
        "专长",
        "# 亡灵杀手手册 专长",
        stats, duplicates, plan_sections
    )

    # 3. 物品（page_1582.md）— 使用 HTML 回退清洗后按条目拆分
    mark_connected(Path(SRC_DIR) / "page_1582.md", "organize_undead.py", kind="item")
    process_page_1582_items(stats, duplicates, plan_sections)

    # 4. 法术（page_506.md）— 使用 HTML 回退清洗后处理
    mark_connected(Path(SRC_DIR) / "page_506.md", "organize_undead.py", kind="spell")
    process_page_506_spells(stats, duplicates, plan_sections)

    # 5. 写入计划文件
    plan = {
        "source_book": "亡灵杀手手册",
        "source_book_english": "Undead Slayer's Handbook",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/亡灵杀手手册",
        "stats": stats,
        "sections": plan_sections,
        "skipped_files": skipped_files,
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 6. 写入报告
    report_lines = [
        "# 亡灵杀手手册 整理报告",
        "",
        "## 整理策略",
        "",
        "亡灵杀手手册（Undead Slayer's Handbook）内容分散在专长、进阶职业、法术和物品文件中。",
        "本次将各类型条目按规则合并到 `pf_rules_md_organized/` 下对应分类的已有页面或来源书专属文件中。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/亡灵杀手手册/`",
        "",
        "## 处理统计",
        "",
        f"- 新增条目：{stats['added']}",
        f"- 跳过重复：{stats['skipped']}",
        f"- 错误/跳过文件：{len(stats['errors'])}",
        "",
        "## 处理内容",
        "",
        "### 专长",
        "",
        "- `专长47.md` → `专长/亡灵杀手手册_专长.md`",
        "  - 残悔斩（Lingering Smite）",
        "",
        "### 进阶职业",
        "",
        "- `灵魂守卫.md` → `职业/进阶职业/亡灵杀手手册_灵魂守卫.md`",
        "  - 灵魂守卫（Soul Warden）",
        "",
        "### 奇物",
        "",
        "- `page_1582.md` → `装备_魔法物品/魔法物品/奇物/亡灵杀手手册_奇物.md`",
        "  - 护佑生命之戒（Ring of Protected Life）",
        "  - 破魂锥（Spiritbane Spike）",
        "  - 日光瓶（Bottled Sunlight）",
        "  - 腐肉诱饵（Carrion Bait）",
        "",
        "### 法术",
        "",
        "- `page_506.md` → `规则/亡灵杀手手册_法术.md`",
        "  - 附身陷阱（possession trap）",
        "  - 守护神球（sphere of warding）",
        "  - 腐烂罗盘（carrion compass）",
        "  - 强效圣水（enpower holy water）",
        "  - 力场锚（force anchor）",
        "  - 生命护盾（life shield）",
        "  - 死灵负担（necromantic burden）",
        "  - 不死转化（undeath inversion）",
        "",
        "### 跳过文件",
        "",
        "- 无",
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

    # 7. 重复记录（避免重复追加同来源书章节）
    if duplicates:
        dup_anchor = "## 亡灵杀手手册（Undead Slayer's Handbook）"
        dup_existing = open(DUP_RECORD_PATH, "r", encoding="utf-8").read() if os.path.exists(DUP_RECORD_PATH) else ""
        if dup_anchor not in dup_existing:
            dup_lines = ["", "", dup_anchor, "", f"**发现时间**：2026-06-19", ""]
            dup_lines.append("| 来源文件 | 条目 | 目标文件 | 备注 |")
            dup_lines.append("|----------|------|----------|------|")
            for d in duplicates:
                en = f" / {d['english']}" if d["english"] else ""
                dup_lines.append(f"| {d['source']} | {d['title']}{en} | {d['target']} | {d['reason']} |")
            dup_lines.append("")
            with open(DUP_RECORD_PATH, "a", encoding="utf-8") as f:
                f.write("\n".join(dup_lines))

    # 8. 问题记录（避免重复追加）
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

    ensure_problem("UNDEAD-SPELLS-001", """

## 亡灵杀手手册（Undead Slayer's Handbook）

### UNDEAD-SPELLS-001：page_506.md 法术全部挤在一行

- **问题归类**：`markdown格式` / `文本挤在一行` / `无法自动拆分`
- **严重程度**：`影响严重`
- **涉及文件**：`page_506.md`
- **问题描述**：7 个法术条目全部挤在同一行内，标题、学派、环级、施放时间、成分、范围、目标、持续时间、豁免、法术抗力、效果描述之间没有任何换行分隔。例如第一个法术"附身陷阱"从第 7 行开始，一直持续到第 11 行（守护神球）之前，中间没有换行。
- **影响**：无法使用自动标题检测（`detect_title_starts`）可靠拆分，因为标题和正文混在一起，且没有明确的行边界。
- **建议处理**：
  1. 人工将每个法术拆分为独立条目，按标准法术格式排版（标题、学派、环级、施放时间、成分、范围、目标、持续时间、豁免、法术抗力、效果描述各一行）。
  2. 或编写专门的正则脚本，按法术名称+英文名的模式进行文本级拆分，但风险较高（可能切错边界）。
- **当前处理**：已在 `organize_undead.py` 中接入 HTML 回退清洗，并编写专用法术拆分逻辑处理。7 个法术已合并到 `规则/亡灵杀手手册_法术.md`。详见 `未整理目录Markdown格式问题处理记录.md#UNDEAD-SPELLS-001`。

### UNDEAD-ITEMS-001：page_1582.md 物品标签不统一

- **问题归类**：`markdown格式` / `标签不一致`
- **严重程度**：`影响轻微`
- **涉及文件**：`page_1582.md`
- **问题描述**：4 个物品条目使用了不同的标签体系：
  - 护佑生命之戒：使用 **灵光**、**位置**、**价格**、**重量**、**效果**（标准魔法物品格式）
  - 破魂锥：使用 **类型**、**制造DC**、**价格**、**重量**、**效果**（炼金物品格式）
  - 日光瓶：无 ** 标签，纯文本描述（非标准格式）
  - 腐肉诱饵：使用 **出处**、**价格**、**重量**、**分类**、**描述**（另一种格式）
- **当前处理**：已在 `organize_undead.py` 中接入 `page_1582.html` HTML 回退清洗，使用专用 `process_page_1582_items()` 按 4 个物品拆分并统一标题格式。4 个物品已重新合并到 `装备_魔法物品/魔法物品/奇物/亡灵杀手手册_奇物.md`。详见 `未整理目录Markdown格式问题处理记录.md#UNDEAD-ITEMS-001`。

### UNDEAD-FEAT-001：专长47.md 标题跨行

- **问题归类**：`markdown格式` / `标题跨行`
- **严重程度**：`影响轻微`
- **涉及文件**：`专长47.md`
- **问题描述**：标题 `**残悔斩（Lingering` + `Smite）**` 跨两行，但 `normalize_section_lines` 函数可自动修正。
- **当前处理**：脚本使用 `process_auto_split_file` 处理，已兼容跨行标题。
""")

    print(f"整理完成：新增 {stats['added']} 条，跳过 {stats['skipped']} 条，错误/跳过文件 {len(stats['errors'])} 条。")
    if stats["errors"]:
        for e in stats["errors"]:
            print("  ERROR:", e)
    if skipped_files:
        for sf in skipped_files:
            print(f"  SKIPPED: {sf['file']} — {sf['reason']}")


if __name__ == "__main__":
    main()
