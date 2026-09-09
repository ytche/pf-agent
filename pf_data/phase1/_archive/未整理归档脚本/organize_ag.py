#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 冒险者指南AG（Adventurer's Guide）内容到已有分类目录。

本次处理：
- 其他专长.md 中的专长条目
- 职业变体/ 下的职业变体条目
- 进阶职业/ 下的进阶职业条目
- 其他物品.md 中的物品条目（按子类型拆分）

暂不处理：
- 14 个组织背景文件（page_*.md 及 玛伽姆比亚.md、扎布里蒂.md）：纯背景描述，无规则条目
"""

import json
import os
import re

# 与同目录下的拆分脚本共享职业变体拆分逻辑
import split_ag_archetypes

BASE = "/Users/chezi/code/java/pf_agent/pf_data/phase1"
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/冒险者指南AG")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "AG_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "AG_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")
PROBLEM_RECORD_PATH = os.path.join(BASE, "未整理目录整理问题记录.md")

SOURCE_NOTE_TEMPLATE = "> 来源：冒险者指南（Adventurer's Guide）AG，页码见原书，未整理 → 冒险者指南AG → {section_title}"

KNOWN_LABELS = {
    "制造要求", "需求", "制造成本", "制造条件", "灵光", "位置", "栏位", "价格",
    "施法者等级", "重量", "类别", "描述", "来源", "出处", "效果", "先决条件",
    "专长效果", "通常", "特殊说明", "拥有此专长前的正常情况", "好处", "学派",
    "施放时间", "成分", "技能检定", "距离", "区域", "持续时间", "豁免", "法术抗力",
    "反冲", "失败", "类型",
}

# 进阶职业源文件名 → 规范化条目标题（含英文名）
PRESTIGE_TITLES = {
    "page_1448.md": "亚萨维尔（Asavir）",
    "page_1450.md": "完美门徒（Student of Perfection）",
    "奥多里剑豪.md": "奥多里剑豪（Aldori Swordlord）",
    "钉魂密使.md": "钉魂密使（Rivethun Emissary）",
}

# 其他物品.md 条目 → 目标子类型文件
AG_ITEMS = [
    {"title": "神圣之火披风", "english": "Cloak Of Heavenly Fire", "target": "装备_魔法物品/魔法物品/奇物/冒险者指南AG_奇物.md", "section_title": "奇物"},
    {"title": "抗力马鞍", "english": "Caparison of resistance", "target": "装备_魔法物品/魔法物品/奇物/冒险者指南AG_奇物.md", "section_title": "奇物"},
    {"title": "汉化膏与娘化酊", "english": "Anderos salve and mulibrous tincture", "target": "装备_魔法物品/货品服务/page_212.md", "section_title": "炼金物品"},
    {"title": "猛犸长枪", "english": "Mammoth Lance", "target": "装备_魔法物品/武器/冒险者指南AG_武器.md", "section_title": "武器"},
    {"title": "魅影尘", "english": "Phantom Ash", "target": "装备_魔法物品/货品服务/page_212.md", "section_title": "炼金物品"},
    {"title": "风暴护符", "english": "Amulet of the Storm", "target": "装备_魔法物品/魔法物品/奇物/冒险者指南AG_奇物.md", "section_title": "奇物"},
    {"title": "哥兹面具", "english": "Goz Mask", "target": "装备_魔法物品/魔法物品/奇物/冒险者指南AG_奇物.md", "section_title": "奇物"},
    {"title": "罐装闪电", "english": "Jar of Lightning", "target": "装备_魔法物品/魔法物品/奇物/冒险者指南AG_奇物.md", "section_title": "奇物"},
    {"title": "风暴朝拜者权杖", "english": "Storm Kindler's Rod", "target": "装备_魔法物品/魔法物品/戒指_权杖_法杖/冒险者指南AG_权杖.md", "section_title": "权杖"},
]


def load_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().splitlines()


def already_present(target_text, section):
    marker_key = f"<!-- AG-source:{section['source']}:{section['title']} -->"
    if marker_key in target_text:
        return True, "hidden_marker"
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
    for i, line in enumerate(section_lines):
        s = line.strip()
        if not s:
            if title_end > 0:
                break
            continue
        if title_end == 0:
            title_end = i + 1
            continue
        prev = section_lines[i - 1].strip()
        if prev.endswith("**"):
            break
        title_end = i + 1
    return section_lines[:title_end], section_lines[title_end:]


def build_append_block(section, section_lines, section_title=None):
    title_lines, body_lines = split_title_body(section_lines)
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title or section.get("section_title", ""))
    marker = f"<!-- AG-source:{section['source']}:{section['title']} -->"
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
    if not os.path.exists(full_path) or os.path.getsize(full_path) == 0:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(header + "\n\n")


def normalize_ws(text):
    """将连续空白字符合并为单个空格。"""
    return re.sub(r'\s+', ' ', text).strip()


def normalize_file_lines(lines):
    """在整文件范围内拆分标题与正文挤在同一行的情况。

    例如 `**绽放之光(Blossoming Light)**　　有些牧师...` 会被拆成
    标题行和正文行，便于后续 detect_title_starts 定位。
    """
    result = []
    for line in lines:
        # 形如 `**标题（英文）**　　正文` 或 `**标题** ****正文` 的混行
        m = re.match(r'^(\*\*.*?\*\*)\s*(\S.*)$', line)
        if m:
            result.append(m.group(1))
            result.append(m.group(2))
        else:
            result.append(line)
    return result


def merge_multiline_titles(lines):
    """合并跨行标题。"""
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        merged = line
        # **中文** 后紧跟 （English...） 的跨行英文/变体标注
        while (
            i + 1 < len(lines)
            and s.startswith("**")
            and s.endswith("**")
            and not re.search(r"[A-Za-z]", s)
            and lines[i + 1].strip().startswith(("(", "（"))
        ):
            i += 1
            merged = merged.rstrip() + lines[i].strip()
            s = merged.strip()
        # 行内含 ** 但未以 ** 结尾，下一行以 ** 结尾（但不是独立的 `**标题**`），或为纯英文/空格续行
        # 限制当前行长度，避免把正文里的两个加粗标题合并
        while (
            i + 1 < len(lines)
            and "**" in s
            and not s.endswith("**")
            and len(s) <= 120
            and (
                (
                    lines[i + 1].strip().endswith("**")
                    and not re.match(r"^\*\*.*\*\*$", lines[i + 1].strip())
                )
                or re.fullmatch(r"[A-Za-z\s]+", lines[i + 1].strip())
            )
        ):
            i += 1
            merged = merged.rstrip() + " " + lines[i].strip()
            s = merged.strip()
        # 末尾是开括号，下一行是英文续名
        while (
            i + 1 < len(lines)
            and (s.endswith("(") or s.endswith("（"))
            and re.match(r"^[A-Za-z]", lines[i + 1].strip())
        ):
            i += 1
            merged = merged.rstrip() + lines[i].strip()
            s = merged.strip()
        # 无加粗的中文标题+英文跨行（如 中文(English ... / ...)）
        while (
            i + 1 < len(lines)
            and not s.startswith("**")
            and "(" in s
            and ")" not in s
            and re.search(r"[A-Za-z]", lines[i + 1].strip())
            and ")" in lines[i + 1]
        ):
            i += 1
            merged = merged.rstrip() + " " + lines[i].strip()
            s = merged.strip()
        result.append(merged)
        i += 1
    return result


def extract_first_title(lines):
    """从文件行中抽取第一个疑似标题作为聚合文件内的二级标题。"""
    lines = merge_multiline_titles(normalize_file_lines(lines))
    for line in lines:
        s = line.strip()
        # 清理 Markdown 加粗、图片链接、普通链接等
        s = re.sub(r'\*\*', '', s).strip()
        s = re.sub(r'!\[.*?\]\([^)]+\)', '', s).strip()
        s = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', s).strip()
        if not s or len(s) > 80:
            continue
        if s[-1] in "。！？":
            continue
        m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", s)
        if not m:
            continue
        first = m.group(1)
        if first in KNOWN_LABELS:
            continue
        return s
    return None


def _find_item_intros(lines, start_indices):
    """提取条目之间的章节引言（如 `---` 后的 `魔法物品 MAGIC ITEMS`）。

    返回 {entry_index: {"start": 分隔线行号, "lines": 引言内容列表}}，
    便于从上一个条目的正文中剔除引言，并把它 prepend 到对应条目。
    """
    intros = {}
    for i, line in enumerate(lines):
        if line.strip() != "---":
            continue
        next_starts = [s for s in start_indices if s > i]
        if not next_starts:
            continue
        intro_end = min(next_starts)
        entry_idx = start_indices.index(intro_end)
        intro_lines = lines[i + 1:intro_end]
        while intro_lines and not intro_lines[0].strip():
            intro_lines.pop(0)
        if intro_lines:
            intros[entry_idx] = {"start": i, "lines": intro_lines}
    return intros


def _strip_item_leading_lines(lines, title, english):
    """去掉物品条目顶部的标题、出处/来源行，保留正文。"""
    cn = title
    en = english.lower()
    body_labels = sorted(KNOWN_LABELS, key=len, reverse=True)

    # 对物品只合并跨行标题，不拆分 `**标签**：值 这类属性行
    lines = merge_multiline_titles(lines)
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    while idx < len(lines):
        raw = lines[idx].rstrip()
        s = raw.strip()
        if not s:
            idx += 1
            continue

        s_label = re.sub(r'^\*+', '', s)

        # 跳过原文件自带的出处/来源行
        if re.match(r'^(出处|来源|出自)[:：]', s_label):
            idx += 1
            continue

        # 正文从第一个物品属性标签开始
        if any(s_label.startswith(lbl) for lbl in body_labels):
            break

        s_clean = re.sub(r'\*\*', '', s)
        s_clean = re.sub(r'!\[.*?\]\([^)]+\)', '', s_clean)
        s_clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', s_clean)
        s_clean = re.sub(r'^\*+|\*+$', '', s_clean).strip()

        # 标题行：包含完整中文名和英文名（可处理带链接的长标题）
        if cn in s_clean and en in s_clean.lower():
            idx += 1
            continue
        # 简短标题行：只包含中文名或英文名（跨行标题的剩余部分）
        if (len(s_clean) <= len(title) + len(english) + 30 and
                (cn in s_clean or en in s_clean.lower())):
            idx += 1
            continue
        # 标题/出处后的短续行（如 `Fire)`、`168页》***`）
        if (len(s_clean) <= len(title) + len(english) + 20 and
                (s_clean.endswith(")") or s_clean.endswith("》") or
                 s_clean.endswith("***"))):
            idx += 1
            continue

        break

    return lines[idx:]


def process_ag_items(source_file, item_entries, stats, duplicates, plan_sections):
    """将 `其他物品.md` 按子类型拆分合并到对应聚合文件。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    for entry in item_entries:
        idx = None
        marker = entry["title"]
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if (stripped.startswith(marker) or
                    stripped.startswith("[**" + marker) or
                    stripped.startswith("**" + marker)):
                idx = i
                break
        entry["start"] = idx
        if idx is None:
            stats["errors"].append(f"{source_file} 中未找到 marker: {marker}")

    start_indices = [entry["start"] for entry in item_entries if entry["start"] is not None]
    intros = _find_item_intros(lines, start_indices)
    intro_lines_map = {idx: info["lines"] for idx, info in intros.items()}
    intro_start_map = {idx: info["start"] for idx, info in intros.items()}

    seen_targets = []
    for entry in item_entries:
        target = entry["target"]
        if target not in seen_targets:
            seen_targets.append(target)
            header = entry.get("header") or f"# 冒险者指南AG {entry['section_title']}"
            ensure_header(target, header)

    for idx, entry in enumerate(item_entries):
        if entry.get("start") is None:
            continue

        sec = {
            "source": source_file,
            "title": entry["title"],
            "english": entry["english"],
            "target": entry["target"],
            "section_title": entry["section_title"],
        }

        full_target = os.path.join(ORG_BASE, entry["target"])
        target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

        present, reason = already_present(target_text, sec)
        if present:
            duplicates.append({
                "source": source_file,
                "title": entry["title"],
                "english": entry["english"],
                "target": entry["target"],
                "reason": reason,
            })
            stats["skipped"] += 1
            plan_sections.append({**sec, "action": "skipped", "reason": reason})
            continue

        start_idx = entry["start"]
        next_start = item_entries[idx + 1]["start"] if idx + 1 < len(item_entries) else len(lines)
        # 如果下一个条目之前有章节引言，则当前条目正文截止到引言分隔线之前
        intro_start = intro_start_map.get(idx + 1)
        end_idx = min(next_start, intro_start) if intro_start is not None else next_start
        section_lines = lines[start_idx:end_idx]

        body_lines = _strip_item_leading_lines(section_lines, entry["title"], entry["english"])
        intro_lines = intro_lines_map.get(idx, [])
        if intro_lines:
            if body_lines and body_lines[0].strip():
                body_lines = intro_lines + [""] + body_lines
            else:
                body_lines = intro_lines + body_lines

        marker = f"<!-- AG-source:{source_file}:{entry['title']} -->"
        note = SOURCE_NOTE_TEMPLATE.format(section_title=entry["section_title"])
        block_lines = [marker, f"## {entry['title']}（{entry['english']}）", note]
        block_lines.extend(body_lines)
        if block_lines[-1].strip() != "":
            block_lines.append("")
        block_lines.append("")
        block = "\n".join(block_lines) + "\n"

        append_to_target(entry["target"], block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def process_whole_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """将整个源文件作为一个条目追加到目标聚合文件。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    ensure_header(target_path, header)

    lines = load_lines(src_path)
    title = extract_first_title(normalize_file_lines(lines)) or source_file
    sec = {
        "source": source_file,
        "title": title,
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
            "title": title,
            "english": "",
            "target": target_path,
            "reason": reason,
        })
        stats["skipped"] += 1
        plan_sections.append({**sec, "action": "skipped", "reason": reason})
        return

    marker = f"<!-- AG-source:{source_file}:{title} -->"
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
    block_lines = [marker]
    block_lines.append(f"## {title}")
    block_lines.append(note)
    block_lines.extend(lines)
    if block_lines and block_lines[-1].strip() != "":
        block_lines.append("")
    block_lines.append("")
    block = "\n".join(block_lines) + "\n"

    append_to_target(target_path, block)
    stats["added"] += 1
    plan_sections.append({**sec, "action": "added"})


def process_prestige_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """将单个进阶职业源文件追加到进阶职业聚合文件。

    与 process_whole_file 的区别：
    - 使用显式标题映射，避免源文件标题跨行/缺失导致条目标题错误；
    - 跳过源文件中已有的标题行，防止在聚合文件中出现重复标题。
    """
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    ensure_header(target_path, header)

    fname = os.path.basename(source_file)
    title = PRESTIGE_TITLES.get(fname)
    if not title:
        stats["errors"].append(f"进阶职业标题未映射: {source_file}")
        return

    sec = {
        "source": source_file,
        "title": title,
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
            "title": title,
            "english": "",
            "target": target_path,
            "reason": reason,
        })
        stats["skipped"] += 1
        plan_sections.append({**sec, "action": "skipped", "reason": reason})
        return

    lines = load_lines(src_path)
    lines = merge_multiline_titles(normalize_file_lines(lines))
    body_lines = _strip_prestige_leading_lines(lines, title)

    marker = f"<!-- AG-source:{source_file}:{title} -->"
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
    block_lines = [marker]
    block_lines.append(f"## {title}")
    block_lines.append(note)
    block_lines.extend(body_lines)
    if block_lines and block_lines[-1].strip() != "":
        block_lines.append("")
    block_lines.append("")
    block = "\n".join(block_lines) + "\n"

    append_to_target(target_path, block)
    stats["added"] += 1
    plan_sections.append({**sec, "action": "added"})


def _strip_prestige_leading_lines(lines, title):
    """去掉进阶职业源文件顶部的标题/空行，保留译者链接与正文。"""
    cn = title.split("（")[0]
    en_match = re.search(r"[（(]([^)]+)[）)]", title)
    en = en_match.group(1) if en_match else ""

    def _is_title_component(s):
        if not s:
            return False
        s_clean = re.sub(r"^#+\s*", "", s)
        s_clean = re.sub(r"\*\*", "", s_clean).strip()
        s_clean = re.sub(r"!\[.*?\]\([^)]+\)", "", s_clean)
        s_clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s_clean)
        s_clean = re.sub(r"^\*+|\*+$", "", s_clean).strip()
        if cn and cn in s_clean and len(s_clean) <= len(title) + 12:
            return True
        if en and en.lower() in s_clean.lower() and len(s_clean) <= len(title) + 12:
            return True
        return False

    result = []
    state = "start"  # start -> after_link -> body
    for line in lines:
        s = line.strip()

        if state == "start":
            if not s:
                continue
            # 译者链接行单独保留，并继续向后寻找标题
            if re.match(r"^\[.*?\]\(https?://", s) or "译者" in s:
                result.append(line)
                state = "after_link"
                continue
            if _is_title_component(s) or re.match(r"^\*\*(?:出处|出自|来源)[:：]", s):
                continue
            result.append(line)
            state = "body"
        elif state == "after_link":
            if not s:
                result.append(line)
                continue
            if _is_title_component(s) or re.match(r"^\*\*(?:出处|出自|来源)[:：]", s):
                continue
            result.append(line)
            state = "body"
        else:
            result.append(line)

    return result


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
    """对源文件按自动检测的标题行拆分并合并。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return
    lines = load_lines(src_path)
    lines = normalize_file_lines(lines)
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


def main():
    stats = {"added": 0, "skipped": 0, "errors": []}
    duplicates = []
    plan_sections = []

    # 1. 专长
    feat_target = "专长/冒险者指南AG_专长.md"
    process_auto_split_file("其他专长.md", feat_target, "其他专长", "# 冒险者指南AG 专长", stats, duplicates, plan_sections)

    # 2. 职业变体：先按整文件合并到聚合文件，再拆分到各职业目录
    archetype_target = "职业/冒险者指南AG_变体.md"
    archetype_dir = os.path.join(SRC_DIR, "职业变体")
    if os.path.isdir(archetype_dir):
        for fname in sorted(os.listdir(archetype_dir)):
            if not fname.endswith(".md"):
                continue
            process_whole_file(
                os.path.join("职业变体", fname),
                archetype_target,
                f"职业变体/{fname}",
                "# 冒险者指南AG 职业变体",
                stats,
                duplicates,
                plan_sections,
            )

    # 将聚合的职业变体拆分到职业/<分类>/<职业>/冒险者指南AG_<职业>变体.md
    aggregate_path = os.path.join(ORG_BASE, archetype_target)
    if os.path.exists(aggregate_path):
        try:
            archetype_stats, archetype_sections = split_ag_archetypes.split_aggregate_file(
                aggregate_path, org_base=ORG_BASE
            )
            stats["added"] += archetype_stats["added"]
            stats["skipped"] += archetype_stats["skipped"]
            stats["errors"].extend(archetype_stats["errors"])
            plan_sections.extend(archetype_sections)
        except Exception as e:
            stats["errors"].append(f"拆分职业变体失败: {e}")

    # 3. 进阶职业：按整文件合并到聚合文件，使用显式标题映射
    prestige_target = "职业/进阶职业/冒险者指南AG_进阶职业.md"
    prestige_dir = os.path.join(SRC_DIR, "进阶职业")
    if os.path.isdir(prestige_dir):
        for fname in sorted(os.listdir(prestige_dir)):
            if not fname.endswith(".md"):
                continue
            process_prestige_file(
                os.path.join("进阶职业", fname),
                prestige_target,
                f"进阶职业/{fname}",
                "# 冒险者指南AG 进阶职业",
                stats,
                duplicates,
                plan_sections,
            )

    # 4. 其他物品：按物品子类型拆分
    process_ag_items("其他物品.md", AG_ITEMS, stats, duplicates, plan_sections)

    # 删除已废弃的货品服务聚合文件
    old_item_aggregate = os.path.join(ORG_BASE, "装备_魔法物品/货品服务/冒险者指南AG_物品.md")
    if os.path.exists(old_item_aggregate):
        os.remove(old_item_aggregate)

    # 5. 写入计划文件
    plan = {
        "source_book": "冒险者指南AG",
        "source_book_english": "Adventurer's Guide",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/冒险者指南AG",
        "stats": stats,
        "sections": plan_sections,
        "skipped_files": [
            "page_1216.md", "page_1229.md", "page_1230.md", "page_1312.md", "page_1349.md",
            "page_1350.md", "page_1360.md", "page_1364.md", "page_1379.md", "page_1445.md",
            "page_1446.md", "page_1449.md", "玛伽姆比亚.md", "扎布里蒂.md",
        ],
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 6. 写入报告
    report_lines = [
        "# 冒险者指南AG 整理报告",
        "",
        "## 整理策略",
        "",
        "冒险者指南AG（Adventurer's Guide）内容分散在组织背景、职业变体、进阶职业、专长、物品等文件中。",
        "本次将 `其他专长.md` 按条目拆分合并，将 `进阶职业/` 按源文件整体合并到聚合文件，",
        "将 `其他物品.md` 按物品子类型拆分合并到 `装备_魔法物品/` 各子目录；",
        "将 `职业变体/` 下源文件先聚合到 `职业/冒险者指南AG_变体.md`，",
        "再通过 `split_ag_archetypes.py` 按职业拆分到各职业已有的职业变体页面（如 `page_41.md`、`page_52.md` 等），",
        "不新建 `<来源书>_<职业>变体.md`；14 个组织背景文件仍为纯背景描述，暂不处理。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/冒险者指南AG/`",
        "",
        "## 处理统计",
        "",
        f"- 新增条目：{stats['added']}",
        f"- 跳过重复：{stats['skipped']}",
        f"- 错误：{len(stats['errors'])}",
        "",
        "## 处理内容",
        "",
        f"- 专长：`其他专长.md` → `{feat_target}`",
        f"- 职业变体：`职业变体/` 下 18 个文件 → 拆分到各职业既有职业变体页面",
        f"- 进阶职业：`进阶职业/` 下 4 个文件 → `{prestige_target}`",
        "- 物品：`其他物品.md` → 按子类型拆分：",
        "  - 奇物 → `装备_魔法物品/魔法物品/奇物/冒险者指南AG_奇物.md`",
        "  - 权杖 → `装备_魔法物品/魔法物品/戒指_权杖_法杖/冒险者指南AG_权杖.md`",
        "  - 武器 → `装备_魔法物品/武器/冒险者指南AG_武器.md`",
        "  - 炼金物品 → `装备_魔法物品/货品服务/page_212.md`",
        "",
        "## 暂未处理",
        "",
        "- 14 个组织背景文件（红螳螂、盾徽财团、灰少女、地狱骑士、掌灯人、探索者协会、银渡鸦、雄鹰骑士、铃花会、盗贼议会、钉魂门、风暴朝拜者、玛伽姆比亚、扎布里蒂）：均为纯背景描述，无规则条目。",
        "详见 `pf_data/phase1/未整理目录整理问题记录.md` 中 AG-* 记录。",
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

    # 4. 重复记录（幂等：若已有 AG 块则不再追加）
    if duplicates:
        dup_anchor = "## 冒险者指南AG（Adventurer's Guide）"
        dup_existing = open(DUP_RECORD_PATH, "r", encoding="utf-8").read() if os.path.exists(DUP_RECORD_PATH) else ""
        if dup_anchor not in dup_existing:
            dup_lines = ["", "", dup_anchor, "", f"**发现时间**：2026-06-19", ""]
            dup_lines.append("| 来源文件 | 条目 | 目标文件 | 备注 |")
            dup_lines.append("|----------|------|----------|------|")
            for d in duplicates:
                en = f" / {d['english']}" if d['english'] else ""
                dup_lines.append(f"| {d['source']} | {d['title']}{en} | {d['target']} | {d['reason']} |")
            dup_lines.append("")
            with open(DUP_RECORD_PATH, "a", encoding="utf-8") as f:
                f.write("\n".join(dup_lines))

    # 5. 问题记录（避免重复追加）
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

    ensure_problem("AG-ARCHETYPES", """

## 冒险者指南AG（Adventurer's Guide）

### AG-ARCHETYPES：职业变体文件普遍存在标题/正文混行及多变体混排

- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：`需要人工校验`
- **涉及文件**：`pf_rules_md/未整理/冒险者指南AG/职业变体/` 下全部文件
- **问题描述**：
  - 多数变体条目标题与首段正文挤在同一行（如 `**绽放之光(Blossoming Light)**　　有些牧师在追求自我的纯洁与光明上走向极至...`）；
  - 标题跨行现象普遍（如 `**算命师傅（Fortune-Teller）［吟游诗人变体］` / `**`）；
  - `page_1384.md`（野蛮人）、`page_1385.md`（圣武士）、`page_1387.md`（盗贼/侠客）等文件同一文件内包含 2 个变体；
  - `page_1384.md` 末尾还出现与开头变体重复的 `附魂唤师 Geminate Invoker` 条目（不同译者版本）。
  自动拆分极易割裂条目或重复追加，准确率低于可接受水平。
- **当前处理**：本次未合并 `职业变体/` 下文件，仅合并了 `其他专长.md`。
- **备注**：建议读取对应 HTML 文件或人工按变体切分后再合并到 `职业/<分类>/<职业>/` 对应页面。

### AG-PRESTIGE：进阶职业文件含职业表且标题跨行

- **问题归类**：`markdown格式`
- **严重程度**：`需要人工校验`
- **涉及文件**：`pf_rules_md/未整理/冒险者指南AG/进阶职业/` 下全部文件
- **问题描述**：4 个进阶职业（奥多里剑豪、钉魂密使、亚萨维尔、完美门徒）均含 Markdown 职业表，且标题跨行，直接追加到现有职业目录会污染原有职业页面结构。
- **当前处理**：本次未合并 `进阶职业/` 下文件。
- **备注**：进阶职业应合并到 `职业/进阶职业/` 或单独建立 `规则/冒险者指南AG_进阶职业.md`，需先确认目录方案。

### AG-ITEMS：其他物品.md 需按子类型分类且含图片标签

- **问题归类**：`markdown格式` / `条目归属待确认`
- **严重程度**：`需要人工校验`
- **涉及文件**：`pf_rules_md/未整理/冒险者指南AG/其他物品.md`
- **问题描述**：物品条目以 `**` 粗体标题开头，边界相对清晰，但部分条目以 `![[图片]]` 图片标签开头，且物品子类型（炼金物品、魔法物品、次等神器等）需按 `装备_魔法物品/` 子目录拆分，自动分类准确率低。
- **当前处理**：本次未合并 `其他物品.md`。
- **备注**：建议人工按物品子类型分类后，再合并到 `装备_魔法物品/` 各子目录。

### AG-LORE：组织背景文件无规则条目

- **问题归类**：`其他`
- **严重程度**：`建议优化`
- **涉及文件**：`pf_rules_md/未整理/冒险者指南AG/` 下 14 个组织背景 page_*.md 及 `玛伽姆比亚.md`、`扎布里蒂.md`
- **问题描述**：这些文件均为组织背景、历史、阵营、目标等描述性内容，无职业变体、专长、物品等规则条目，不属于规则问答 Agent 一期需要索引的规则内容。
- **当前处理**：本次未合并这些背景文件。
- **备注**：若二期需要组织背景，可统一存放到 `背景/冒险者指南AG_组织背景/` 或类似目录。
""")

    print(f"整理完成：新增 {stats['added']} 条，跳过 {stats['skipped']} 条，错误 {len(stats['errors'])} 条。")
    if stats["errors"]:
        for e in stats["errors"]:
            print("  ERROR:", e)


if __name__ == "__main__":
    main()
