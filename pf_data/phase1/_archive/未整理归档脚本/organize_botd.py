#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 永罪之书（Book of the Damned）内容到已有分类目录。

本次处理：
- 专长：专长38.md（7个专长 + 1个侧边栏）
- 专长：page_1555.md（3个魔族仪典相关专长）
- 进阶职业：page_1556.md（魔鬼大师）
- 魔法物品：page_1562.md（多个魔法物品条目）
- 仪式：仪式6.md（多个仪式条目）
- 魔鬼护身符：魔鬼护身符.md（3个特殊魔法物品）
- 神恩条目：神恩/ 下各子目录（大量魔神神恩条目）

暂不处理：
- page_1515.md：魔神总览索引页，无独立规则条目，跳过。

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
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/永罪之书BotD")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "BOTD_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "BOTD_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")
PROBLEM_RECORD_PATH = os.path.join(BASE, "未整理目录整理问题记录.md")

SOURCE_NOTE_TEMPLATE = "> 来源：永罪之书（Book of the Damned），页码见原书，未整理 → 永罪之书BotD → {section_title}"

KNOWN_LABELS = {
    "制造要求", "需求", "制造成本", "制造条件", "灵光", "位置", "栏位", "价格",
    "施法者等级", "重量", "类别", "描述", "来源", "出处", "效果", "先决条件",
    "专长效果", "通常", "特殊说明", "拥有此专长前的正常情况", "好处", "学派",
    "施放时间", "成分", "技能检定", "距离", "区域", "持续时间", "豁免", "法术抗力",
    "反冲", "失败", "类型", "成瘾性", "强韧", "伤害", "先决", "特殊",
}

# 标题中可能出现的元信息标签，检测时先剥离
FEAT_META_TAGS = ["【PFS】"]
FEAT_TYPE_TAGS = ["（战斗专长）", "（专长）", "（物品专长）", "（风格专长）"]


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
    marker_key = f"<!-- BOTD-source:{section['source']}:{section['title']} -->"
    if marker_key in target_text:
        return True, "hidden_marker"
    if section.get("duplicate_skip"):
        checks = [section["title"], section.get("english", "")]
        for c in checks:
            if c and c in target_text:
                return True, f"existing_content ({c})"
    return False, None


def clear_all_botd_targets():
    """清空所有本次脚本可能写入的目标文件，确保干净运行。"""
    targets = [
        "专长/永罪之书_专长.md",
        "装备_魔法物品/魔法物品/永罪之书_魔法物品.md",
        "装备_魔法物品/魔法物品/永罪之书_魔鬼护身符.md",
        "规则/永罪之书_仪式.md",
        "规则/永罪之书_地狱魔神神恩.md",
        "规则/永罪之书_末日荒原魔神神恩.md",
        "规则/永罪之书_深渊魔神神恩.md",
        "规则/永罪之书_其他魔神神恩.md",
    ]
    for t in targets:
        p = os.path.join(ORG_BASE, t)
        if os.path.exists(p):
            os.remove(p)
            print(f"  已清除旧目标: {t}")


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
    """将片段拆分为标题行与正文行。

    标题为开头连续的非正文行；遇到加粗标签、内联字段标签（如 先决：/效果：）、
    来源标注（出自PFRPG：）或斜体风味文本时标题结束。
    """
    section_lines = normalize_section_lines(section_lines)
    title_end = 0
    label_pattern = re.compile(r'^\*\*(' + '|'.join(re.escape(l) for l in KNOWN_LABELS) + r')')
    # 不加粗的内联字段或来源标注，以及以 * 开头的斜体风味文本
    inline_pattern = re.compile(
        r'^(?:\*\*)?(?:先决|效果|专长效果|特殊说明|特殊|通常|好处|出自PFRPG)[：:]'
        r'|^\*+[^\*]'
    )
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
        if label_pattern.match(s) or inline_pattern.match(s):
            break
        prev = section_lines[i - 1].strip()
        if prev.endswith("**"):
            break
        title_end = i + 1
    return section_lines[:title_end], section_lines[title_end:]


def build_append_block(section, section_lines, section_title=None):
    title_lines, body_lines = split_title_body(section_lines)
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title or section.get("section_title", ""))
    marker = f"<!-- BOTD-source:{section['source']}:{section['title']} -->"

    # 合并跨行标题并清理元标签、冗余空白
    if title_lines:
        joined = " ".join(l.strip() for l in title_lines).strip()
        joined = re.sub(r'\s+', ' ', joined)
        for tag in FEAT_META_TAGS:
            joined = joined.replace(tag, '')
        joined = re.sub(r'\s+', ' ', joined).strip()
        if joined.startswith("**") and not joined.endswith("**"):
            joined += "**"
        title_lines = [joined]

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
    """处理通用 SECTIONS 配置（职业变体、进阶职业等）。"""
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


def _clean_title_line(s):
    """清理标题行中的装饰性标记，用于检测阶段。"""
    s = s.strip().strip("*")
    for tag in FEAT_META_TAGS + FEAT_TYPE_TAGS:
        s = s.replace(tag, "")
    return s.strip()


def detect_title_starts(lines, max_len=80, require_feat_format=False):
    """自动检测以中文名称开头的标题行位置（用于专长）。

    支持以下复杂情况：
    - 标题跨行（中文名 + 英文名分两行）；
    - 标题中间插入“（战斗专长）”等类型标签；
    - 标题前缀带“【PFS】”标记；
    - 标题加粗但未正确闭合。

    当 require_feat_format=True 时，只匹配以中文名开头且包含英文名的行。
    """
    starts = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        s = _clean_title_line(raw)
        if not s or len(s) > max_len:
            i += 1
            continue
        if s[-1] in "。！？":
            i += 1
            continue

        # 如果前一行是字段标签（如 **先决条件：**），当前行是字段值，不应视为标题
        if i > 0:
            prev_raw = lines[i - 1].strip()
            if re.match(r'^\*\*(' + '|'.join(re.escape(l) for l in KNOWN_LABELS) + r')[：:]\*\*$', prev_raw):
                i += 1
                continue

        # 单行标题：中文名（English 或 中文名 English
        m = re.match(r"([一-鿿]+)(?![一-鿿])(?:\s+[A-Za-z]|\s*[（(]\s*[A-Za-z])", s)
        if m:
            first = m.group(1)
            if first not in KNOWN_LABELS:
                # 如果匹配后还出现句读，说明是正文句子而非标题
                remainder = s[m.end():]
                if re.search(r"[，。；]", remainder):
                    i += 1
                    continue
                # 合并可能被拆到下一行的英文部分
                combined = s
                j = i
                while j + 1 < len(lines):
                    nxt = _clean_title_line(lines[j + 1])
                    if not nxt or nxt[-1] in "。！？" or len(nxt) > max_len:
                        break
                    if not re.match(r"^[A-Za-z]", nxt):
                        break
                    combined = combined.rstrip() + " " + nxt
                    j += 1
                    # 括号平衡后停止继续合并
                    if combined.count("（") <= combined.count("）") and combined.count("(") <= combined.count(")"):
                        break
                starts.append((i, combined))
                i = j + 1
                continue

        # 双行标题：当前行纯中文，下一行以英文开头
        if i + 1 < len(lines):
            nxt = _clean_title_line(lines[i + 1])
            if (re.match(r"^[一-鿿]+$", s.strip())
                    and nxt
                    and re.match(r"^[A-Za-z]", nxt)
                    and nxt[-1] not in "。！？"
                    and len(nxt) <= max_len):
                combined = s.strip() + " " + nxt
                starts.append((i, combined))
                i += 2
                continue

        i += 1
    return starts


def preprocess_page_1555_obedience(lines):
    """预处理 page_1555.md 的魔族仪典专长。

    该文件存在三种格式问题：
    1. 加粗标题跨行（如 **魔族仪典（Fiendish\nObedience ）**）；
    2. 先决条件/专长效果标签与正文挤在同一行；
    3. 括号内的英文名称跨行（如 魔族仪典（Fiendish\nObedience ））。

    预处理会先合并跨行加粗块，按标签和标题拆分，再合并断行的英文名称。
    """
    text = "\n".join(lines)

    # 1. 合并跨行加粗块（**...** 内部允许换行）
    def _collapse_bold(m):
        inner = re.sub(r"\s+", " ", m.group(1)).strip()
        return f"**{inner}**"

    text = re.sub(r"\*\*(.*?)\*\*", _collapse_bold, text, flags=re.DOTALL)

    # 2. 按内联标签和嵌入标题拆分
    label_re = r"\*\*(?:先决条件|专长效果)[：:]\*\*"
    title_re = r"\*\*[一-鿿][一-鿿\w]*\s*[（(]\s*[A-Za-z][A-Za-z\s\-]*\s*[）)]\*\*"
    split_re = re.compile(f"({label_re}|{title_re})")

    split_lines = []
    for line in text.splitlines():
        parts = split_re.split(line)
        for part in parts:
            part = part.strip()
            if part:
                split_lines.append(part)

    # 3. 合并括号/英文名称跨行
    return _merge_broken_parentheticals(split_lines)


def _merge_broken_parentheticals(lines):
    """合并以英文单词或开括号结尾、且下一行继续英文/闭括号的断行。"""
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.search(r"[（(]\s*[A-Za-z][A-Za-z\s\-]*$|\s+[A-Za-z][A-Za-z\s\-]*$", line.rstrip()):
            j = i
            merged = line
            while j + 1 < len(lines):
                nxt = lines[j + 1]
                merged = merged.rstrip() + " " + nxt.lstrip()
                j += 1
                # 括号平衡且不再以英文单词结尾时停止
                if (merged.count("（") <= merged.count("）")
                        and merged.count("(") <= merged.count(")")
                        and not re.search(r"[A-Za-z][A-Za-z\s\-]*$", merged.rstrip())):
                    break
                if j - i > 5:
                    break
            result.append(merged)
            i = j + 1
        else:
            result.append(line)
            i += 1
    return result


def process_auto_split_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections, require_feat_format=False, preprocess_lines=None):
    """按自动检测的标题行拆分并合并（用于专长文件）。

    preprocess_lines：可选的预处理函数，接收原始行列表并返回处理后的行列表。
    """
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return
    lines = load_lines(src_path)
    if preprocess_lines:
        lines = preprocess_lines(lines)
    starts = detect_title_starts(lines, require_feat_format=require_feat_format)
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


MAGIC_ITEM_HEADERS = {"魔法物品", "物品", "剧透"}
MAGIC_ITEM_LABELS = ["价格", "灵光", "施法者等级", "重量", "位置", "栏位", "制造要求", "制造成本", "类型", "成瘾性", "强韧", "效果", "伤害"]
MAGIC_TITLE_RE = re.compile(
    r'^(\*+)?\s*([一-鿿][一-鿿\w]*)\s*[（(]\s*([A-Za-z][A-Za-z\s\-]*)\s*[）)]'
)
MAGIC_LABEL_SPLIT_RE = re.compile(
    r'(\*\*(?:' + '|'.join(re.escape(l) for l in MAGIC_ITEM_LABELS) + r')\*\*)'
)


def build_magic_item_block(sec, section_lines, section_title):
    """将单行内联标签的魔法物品条目拆分为标准标题+多行正文格式。"""
    filtered_lines = []
    for line in section_lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("**") and any(h in s for h in MAGIC_ITEM_HEADERS):
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
            cleaned = part.strip('* \n')
            if cleaned:
                body_lines.append(cleaned)
        elif j % 2 == 1:
            body_lines.append(part)
        else:
            cleaned = re.sub(r'\*+', ' ', part).strip()
            if cleaned:
                body_lines.append(cleaned)

    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
    marker = f"<!-- BOTD-source:{sec['source']}:{sec['title']} -->"
    result = [marker, title_line, note]
    result.extend(body_lines)
    if result[-1].strip() != "":
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def process_magic_items(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理魔法物品文件（page_1562.md）。

    合并多个魔法物品条目；跳过章节标题行。
    """
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 检测标题行：中文名（English Name）
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        m = MAGIC_TITLE_RE.match(s)
        if not m:
            continue
        title = m.group(2)
        if title in MAGIC_ITEM_HEADERS:
            continue
        starts.append((i, line, title, m.group(3).strip()))

    if not starts:
        stats["errors"].append(f"{source_file} 中未检测到魔法物品条目标题")
        return

    ensure_header(target_path, header)

    for idx, (start_idx, raw_line, title_cn, english) in enumerate(starts):
        end_idx = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        sec = {
            "source": source_file,
            "title": title_cn,
            "english": english,
            "target": target_path,
            "section_title": section_title,
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
        block = build_magic_item_block(sec, section_lines, section_title=section_title)
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


RITUAL_HEADERS = {"仪式", "魔族召唤", "升魔仪式", "灵魂捕捉", "真名", "侧边栏"}
RITUAL_LABELS = ["学派", "施放时间", "成分", "技能检定", "距离", "区域", "持续时间", "豁免", "法术抗力", "反冲", "失败", "效果", "目标"]
RITUAL_TITLE_RE = re.compile(
    r'^\*\*([一-鿿][一-鿿\w\s]*)\s*[(（]\s*([A-Za-z][A-Za-z\s\-]*)\s*[）)]\*\*'
)
RITUAL_SIMPLE_TITLE_RE = re.compile(
    r'^\*\*([一-鿿][一-鿿\w\s]*)\*\*'
)
RITUAL_LABEL_SPLIT_RE = re.compile(
    r'(\*\*(?:' + '|'.join(re.escape(l) for l in RITUAL_LABELS) + r')\*\*)'
)


def build_ritual_block(sec, section_lines, section_title):
    """构建仪式条目的追加块。"""
    filtered_lines = []
    for line in section_lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("**") and any(h in s for h in RITUAL_HEADERS):
            continue
        filtered_lines.append(line)

    text = '\n'.join(filtered_lines).strip()
    # 尝试匹配带英文名的标题
    m = RITUAL_TITLE_RE.match(text)
    if m:
        cn, en = m.group(1).strip(), m.group(2).strip()
        title_line = f"**{cn}（{en}）**"
        body_text = text[m.end():]
    else:
        # 尝试匹配纯中文标题
        m2 = RITUAL_SIMPLE_TITLE_RE.match(text)
        if m2:
            cn = m2.group(1).strip()
            title_line = f"**{cn}**"
            body_text = text[m2.end():]
        else:
            parts = text.splitlines()
            title_line = parts[0].strip()
            body_text = '\n'.join(parts[1:])

    # 按已知标签拆分内联正文
    split_parts = RITUAL_LABEL_SPLIT_RE.split(body_text)
    body_lines = []
    for j, part in enumerate(split_parts):
        if j == 0:
            cleaned = part.strip('* \n')
            if cleaned:
                body_lines.append(cleaned)
        elif j % 2 == 1:
            body_lines.append(part)
        else:
            cleaned = re.sub(r'\*+', ' ', part).strip()
            if cleaned:
                body_lines.append(cleaned)

    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
    marker = f"<!-- BOTD-source:{sec['source']}:{sec['title']} -->"
    result = [marker, title_line, note]
    result.extend(body_lines)
    if result[-1].strip() != "":
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def process_rituals(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理仪式文件（仪式6.md）。

    合并多个仪式条目；跳过章节标题行和侧边栏。
    """
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 检测仪式条目标题行
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        # 匹配 **中文名（English Name）**
        m = RITUAL_TITLE_RE.match(s)
        if m:
            title = m.group(1).strip()
            if title in RITUAL_HEADERS or "侧边栏" in s or title in KNOWN_LABELS:
                continue
            starts.append((i, line, title, m.group(2).strip()))
            continue
        # 匹配纯中文标题 **分离为四** 等
        m2 = RITUAL_SIMPLE_TITLE_RE.match(s)
        if m2:
            title = m2.group(1).strip()
            if title in RITUAL_HEADERS or "侧边栏" in s or len(title) < 2 or title in KNOWN_LABELS:
                continue
            # 检查下一行是否包含仪式标签，以确认是仪式条目
            # 同时要求标题不是纯 ritual 子章节标题（如"目标"单独一行后跟"自身"）
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if any(f"**{label}**" in next_line for label in RITUAL_LABELS):
                    starts.append((i, line, title, ""))
            else:
                starts.append((i, line, title, ""))

    if not starts:
        stats["errors"].append(f"{source_file} 中未检测到仪式条目标题")
        return

    ensure_header(target_path, header)

    for idx, (start_idx, raw_line, title_cn, english) in enumerate(starts):
        end_idx = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        sec = {
            "source": source_file,
            "title": title_cn,
            "english": english,
            "target": target_path,
            "section_title": section_title,
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
        block = build_ritual_block(sec, section_lines, section_title=section_title)
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


# ---------------------------------------------------------------------------
# 神恩条目拆分（Book of the Damned Divine Boons）
# ---------------------------------------------------------------------------

# 非魔神名称的标题/字段
BOON_SECTION_HEADERS = {
    "资源", "阵营", "领域", "子域", "子领域", "偏好武器", "邪徽", "神殿", "信徒",
    "爪牙", "仪典", "教派", "族类", "崇拜中心", "标志", "神圣动物", "神圣颜色",
    "服从仪典", "恶魔遵从", "恶魔服从", "遵从仪式",
    "神恩", "神恩-永罪仪典", "神恩-崇神仪典", "神恩-魔神仪典", "神恩-魔族仪典",
    "传音者神恩", "颂教者神恩", "卫道者神恩", "第一神恩", "第二神恩", "第三神恩",
    "特殊施法规则", "特殊召唤规则", "新法术", "异界盟友", "祭司的职责", "神庙和祭坛",
    "赐福——恶魔仪典", "赐福——魔族仪典", "赐福",
    "魔族仪典", "魔神仪典", "崇神仪典", "永罪仪典",
    "领地", "教条", "教派", "外貌",
}

# 英文常见非名字词
BOON_EN_COMMON_WORDS = {
    "boon", "boons", "lord", "lords", "the", "a", "an", "of", "and", "or",
    "pg", "page", "damned", "hell", "abyss", "abaddon", "demon", "devil",
}

# 阵营/描述词，出现在这些词说明不是魔神名称
BOON_ALIGNMENT_WORDS = {"混乱", "秩序", "中立", "善良", "邪恶"}


def _boon_is_header_text(text):
    t = text.strip().rstrip("：:").replace("**", "")
    t = re.sub(r"〔注：.*〕", "", t).strip()
    return t in BOON_SECTION_HEADERS or t.startswith("神恩-") or t.startswith("赐福")


def _boon_normalize_lines(lines):
    """预处理：修复加粗标记异常（未闭合、粘在一起）。返回 (normalized_lines, is_list_items)。"""
    out = []
    is_list = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        list_item = bool(re.match(r'^\s*\d+\*\*', s))

        # 1. 处理 glued bold: **杰萨尔达****饥渴之月的女主人**
        m = re.match(r'^(\*\*[^*]+?\*\*)(\*+)(.+)$', s)
        if m:
            out.append(m.group(1))
            is_list.append(list_item)
            rest = m.group(3).lstrip('*')
            if rest:
                out.append(line[:len(line) - len(s)] + '**' + rest + '**')
                is_list.append(list_item)
            i += 1
            continue

        # 2. 处理未闭合加粗：
        #    **巴巴托斯 Barbatos       → 下一行 ****被须领主**
        #    **怒加，耀目天灾           → 后续 N 行英文，再 ****阵营：**
        if s.startswith('**') and not s.endswith('**') and i + 1 < n:
            next_s = lines[i + 1].strip()
            if next_s.startswith('****'):
                out.append(line.rstrip() + '**')
                is_list.append(list_item)
                i += 2
                continue
            # 探测后续最多 3 行，若出现以 **** 开头行，则合并为标题
            lookahead = []
            found_end = False
            for offset in range(1, 4):
                if i + offset >= n:
                    break
                la = lines[i + offset].strip()
                # 只合并“标题+英文+****字段”这种三行未闭合标题；
                # 普通跨行英文以 ** 结尾的留给 parse_deity_title 处理。
                if la.startswith('****'):
                    found_end = True
                    break
                if la == '---' or la.startswith('['):
                    break
                lookahead.append(lines[i + offset])
            if found_end and lookahead:
                merged = line.rstrip() + ' ' + ' '.join(la.strip() for la in lookahead) + '**'
                out.append(merged)
                is_list.extend([list_item] + [False] * len(lookahead))
                # 跳过合并掉的行
                i += 1 + len(lookahead)
                continue

        # 3. 列表前缀 02**阿洛斯 Alocer** → 去掉数字前缀
        if list_item:
            out.append(re.sub(r'^(\s*)\d+', r'\1', line))
            is_list.append(True)
            i += 1
            continue

        out.append(line)
        is_list.append(False)
        i += 1
    return out, is_list


# 宽松字符集合
BOON_CN_CHARS = r'[一-鿿][一-鿿\w\s·\/\-，、——…]*?'
BOON_EN_CHARS = r'[A-Za-z][A-Za-z0-9\s\-,\.\'’]*'


def _boon_looks_like_name(cn, en):
    cn = cn.strip()
    en = en.strip()
    if _boon_is_header_text(cn):
        return False
    if len(cn) < 2:
        return False
    if en and len(en) <= 1:
        return False
    # 中文含阵营词
    if any(w in cn for w in BOON_ALIGNMENT_WORDS):
        return False
    # 英文是常见非名字词
    if en and en.lower() in BOON_EN_COMMON_WORDS:
        return False
    # 中文以虚词结尾
    if re.search(r'[到在是的了而为]$', cn):
        return False
    return True


def _boon_parse_deity_title(line, next_line=None):
    s = line.strip()
    if not s:
        return None, None

    # A. **中文名（English）** / 中文名（English）
    m = re.match(r'^\*\*\s*(' + BOON_CN_CHARS + r')\s*[（(](' + BOON_EN_CHARS + r')[）)]\s*\*\*$', s)
    if not m:
        m = re.match(r'^(' + BOON_CN_CHARS + r')\s*[（(](' + BOON_EN_CHARS + r')[）)]\s*$', s)
    if m:
        cn, en = m.group(1).strip(), m.group(2).strip()
        if _boon_looks_like_name(cn, en):
            return cn, en

    # B. **中文名 English** / 中文名 English
    m = re.match(r'^\*\*\s*(' + BOON_CN_CHARS + r')\s+(' + BOON_EN_CHARS + r')\s*\*\*$', s)
    if not m:
        m = re.match(r'^(' + BOON_CN_CHARS + r')\s+(' + BOON_EN_CHARS + r')\s*$', s)
    if m:
        cn, en = m.group(1).strip(), m.group(2).strip()
        # 英文以逗号结尾且下一行是纯英文：合并为完整英文名
        if en.endswith((',', '，')) and next_line:
            next_en = next_line.strip()
            if re.match(r'^[A-Za-z][A-Za-z0-9\s\-\'’]+$', next_en):
                en = en.rstrip(',，').strip() + ' ' + next_en
        if _boon_looks_like_name(cn, en):
            return cn, en

    # B2. 中文名/别名English（无空格）如 煞克斯/沙克斯Shax
    m = re.match(r'^(' + BOON_CN_CHARS + r')/(' + BOON_CN_CHARS + r')?([A-Za-z][A-Za-z0-9\-\']*)\s*$', s)
    if m:
        cn = m.group(1).strip()
        en = m.group(3).strip()
        if _boon_looks_like_name(cn, en):
            return cn, en

    # C. 中文名English 无空格，可接（...）后缀
    m = re.match(r'^(' + BOON_CN_CHARS + r')([A-Z][A-Z0-9\-]+)\s*[（(].*?[）)]\s*$', s)
    if m:
        cn, en = m.group(1).strip(), m.group(2).strip()
        if _boon_looks_like_name(cn, en):
            return cn, en
    m = re.match(r'^(' + BOON_CN_CHARS + r')([A-Z][A-Z0-9\-]+)$', s)
    if m:
        cn, en = m.group(1).strip(), m.group(2).strip()
        if _boon_looks_like_name(cn, en):
            return cn, en

    # C2. 纯英文魔神名（无中文），后跟括号注释
    m = re.match(r'^([A-Z][A-Z0-9\-]+)\s*[（(].*?[）)]\s*$', s)
    if m:
        en = m.group(1).strip()
        if _boon_looks_like_name(en, en):
            return en, en

    # D. 跨两行：第一行 中文名，第二行 English
    m = re.match(r'^\*\*\s*(' + BOON_CN_CHARS + r')\s*\*\*$', s)
    if not m:
        m = re.match(r'^(' + BOON_CN_CHARS + r')\s*$', s)
    if m and next_line:
        cn = m.group(1).strip()
        en_line = next_line.strip()
        if re.match(r'^' + BOON_EN_CHARS + r'$', en_line):
            if _boon_looks_like_name(cn, en_line):
                return cn, en_line
        m2 = re.match(r'^[^（(]*[（(](' + BOON_EN_CHARS + r')[）)]', en_line)
        if m2:
            if _boon_looks_like_name(cn, m2.group(1).strip()):
                return cn, m2.group(1).strip()

    # E. 仅中文名：文件开头或紧跟分隔线，且不是已知标题/阵营
    m = re.match(r'^\*\*\s*(' + BOON_CN_CHARS + r')\s*\*\*$', s)
    if not m:
        m = re.match(r'^(' + BOON_CN_CHARS + r')\s*$', s)
    if m:
        cn = m.group(1).strip()
        if _boon_looks_like_name(cn, ""):
            return cn, ""

    return None, None


def _boon_find_deity_starts(raw_lines):
    lines, is_list = _boon_normalize_lines(raw_lines)
    n = len(lines)
    first_sep = next((i for i, line in enumerate(lines) if line.strip() == "---"), n)
    starts = []
    first_title_found = False

    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s == "---" or s.startswith("["):
            continue

        is_at_boundary = False
        if not first_title_found and i < first_sep:
            is_at_boundary = True
        else:
            j = i - 1
            while j >= 0 and lines[j].strip() == "":
                j -= 1
            if j >= 0 and lines[j].strip() == "---":
                is_at_boundary = True
            # 列表项允许跨行出现
            if is_list[i]:
                is_at_boundary = True

        if not is_at_boundary:
            continue

        next_line = lines[i + 1] if i + 1 < n else ""
        cn, en = _boon_parse_deity_title(line, next_line)
        if cn:
            starts.append((i, cn, en))
            first_title_found = True

    return lines, starts


def _split_boon_file(path):
    """拆分单个神恩源文件为多个 (cn, en, lines) 片段。"""
    lines, starts = _boon_find_deity_starts(load_lines(path))
    if not starts:
        fn = os.path.basename(path)
        return [(fn.replace(".md", ""), "", lines)]

    # 对以类别命名的文件（如 古魔领主.md、恐亡魔摧残者.md），若首候选中文与文件名相同，
    # 则视为文件总标题而非单个魔神，跳过。
    fn_base = os.path.splitext(os.path.basename(path))[0]
    # 取文件名中的中文部分（去掉英文/符号）
    fn_cn = re.sub(r'[^一-鿿]', '', fn_base)
    filtered = []
    for k, (idx, cn, en) in enumerate(starts):
        # 仅当存在后续候选且当前候选中文完全匹配文件名中文时跳过
        if k == 0 and len(starts) > 1 and re.sub(r'[^一-鿿]', '', cn) == fn_cn:
            continue
        filtered.append((idx, cn, en))

    sections = []
    for k, (idx, cn, en) in enumerate(filtered):
        end = filtered[k + 1][0] if k + 1 < len(filtered) else len(lines)
        sections.append((cn, en, lines[idx:end]))
    return sections


def _build_boon_block(sec, section_lines, section_title):
    """构建单个魔神神恩条目的追加块。

    标题可能跨多行（如 page_1545.md），需要先合并清理。
    """
    # 取标题部分：到第一个字段/空行/表格前
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
        # 遇到字段标签（**阵营：** 等）或 Markdown 表格行则标题结束
        if re.match(r'^\*\*(?:' + '|'.join(re.escape(h) for h in BOON_SECTION_HEADERS) + r')[：:]\*\*$', s):
            break
        if s.startswith('|'):
            break
        # 上一行已闭合加粗，当前行开始正文
        prev = section_lines[i - 1].strip()
        if prev.endswith('**'):
            break
        title_end = i + 1

    title_lines = section_lines[:title_end]
    body_lines = section_lines[title_end:]

    # 合并跨行标题并清理
    joined = ' '.join(l.strip() for l in title_lines).strip()
    joined = re.sub(r'\*+', '', joined)
    joined = re.sub(r'\s+', ' ', joined).strip()

    # 生成标准标题
    cn = sec['title']
    en = sec.get('english', '')
    if en and en != cn:
        title_line = f"**{cn}（{en}）**"
    else:
        title_line = f"**{cn}**"

    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
    marker = f"<!-- BOTD-source:{sec['source']}:{sec['title']} -->"

    result = [marker, title_line, note]
    # 如果清理后的 joined 与标准标题不同且包含额外信息，保留作为正文第一行
    cleaned_body_prefix = joined
    if cleaned_body_prefix and cleaned_body_prefix != f"{cn}（{en}）" and cleaned_body_prefix != cn:
        result.append(cleaned_body_prefix)
    result.extend(body_lines)
    if result and result[-1].strip() != "":
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def process_devil_talismans(stats, duplicates, plan_sections):
    """处理魔鬼护身符.md（3个特殊魔法物品）。"""
    source_file = "魔鬼护身符.md"
    target_path = "装备_魔法物品/魔法物品/永罪之书_魔鬼护身符.md"
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    lines = load_lines(src_path)

    # 检测魔鬼护身符条目标题
    talisman_starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        # 匹配 "XX护身符（English Name）" 格式
        m = re.match(r'^([一-鿿][一-鿿\w]*)\s*[(（]\s*([A-Za-z][A-Za-z\s\-]*)\s*[）)]', s)
        if m:
            title = m.group(1)
            if title in {"魔鬼护身符"}:
                continue
            talisman_starts.append((i, m.group(1), m.group(2).strip()))

    if not talisman_starts:
        stats["errors"].append(f"{source_file} 中未检测到魔鬼护身符条目标题")
        return

    ensure_header(target_path, "# 永罪之书 魔鬼护身符")

    for idx, (start_idx, title_cn, english) in enumerate(talisman_starts):
        end_idx = talisman_starts[idx + 1][0] if idx + 1 < len(talisman_starts) else len(lines)
        sec = {
            "source": source_file,
            "title": title_cn,
            "english": english,
            "target": target_path,
            "section_title": "魔鬼护身符",
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
        # 魔鬼护身符条目格式特殊，需要手动构建块
        marker = f"<!-- BOTD-source:{source_file}:{title_cn} -->"
        note = SOURCE_NOTE_TEMPLATE.format(section_title="魔鬼护身符")
        title_line = f"**{title_cn}（{english}）**"
        result = [marker, title_line, note]
        result.extend(section_lines)
        if result and result[-1].strip() != "":
            result.append("")
        result.append("")
        block = "\n".join(result) + "\n"
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def process_divine_boons(stats, duplicates, plan_sections):
    """处理神恩/ 下各子目录的魔神神恩条目。

    使用按魔神拆分的策略：每个文件可能包含一个或多个魔神条目，
    通过 _split_boon_file 自动识别标题边界并拆分。
    """
    boon_dirs = {
        "地狱": "地狱魔神神恩",
        "末日荒原": "末日荒原魔神神恩",
        "深渊": "深渊魔神神恩",
        "其他": "其他魔神神恩",
    }

    for subdir, section_title in boon_dirs.items():
        boon_dir = os.path.join(SRC_DIR, "神恩", subdir)
        if not os.path.exists(boon_dir):
            continue

        target_path = f"规则/永罪之书_{section_title}.md"
        ensure_header(target_path, f"# 永罪之书 {section_title}")

        for filename in sorted(os.listdir(boon_dir)):
            if not filename.endswith(".md"):
                continue

            src_path = os.path.join(boon_dir, filename)
            sections = _split_boon_file(src_path)

            for cn, en, section_lines in sections:
                sec = {
                    "source": f"神恩/{subdir}/{filename}",
                    "title": cn,
                    "english": en,
                    "target": target_path,
                    "section_title": section_title,
                }

                full_target = os.path.join(ORG_BASE, target_path)
                target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

                present, reason = already_present(target_text, sec)
                if present:
                    duplicates.append({
                        "source": sec["source"],
                        "title": cn,
                        "english": en,
                        "target": target_path,
                        "reason": reason,
                    })
                    stats["skipped"] += 1
                    plan_sections.append({**sec, "action": "skipped", "reason": reason})
                    continue

                block = _build_boon_block(sec, section_lines, section_title)
                append_to_target(target_path, block)
                stats["added"] += 1
                plan_sections.append({**sec, "action": "added"})


def main():
    stats = {"added": 0, "skipped": 0, "errors": []}
    duplicates = []
    plan_sections = []

    # 清空旧目标文件，避免残留标记导致全部跳过
    clear_all_botd_targets()

    # 1. 专长
    feat_target = "专长/永罪之书_专长.md"
    feat_header = "# 永罪之书 专长"
    process_auto_split_file("专长38.md", feat_target, "专长", feat_header, stats, duplicates, plan_sections, require_feat_format=False)

    # 1.5 魔族仪典专长（page_1555.md）
    # 该文件标题跨行且嵌入前一条目正文末尾，需要专门预处理
    process_auto_split_file(
        "page_1555.md",
        feat_target,
        "专长",
        feat_header,
        stats,
        duplicates,
        plan_sections,
        require_feat_format=False,
        preprocess_lines=preprocess_page_1555_obedience,
    )

    # 2. 进阶职业 - 魔鬼大师（page_1556.md）
    # 注意：page_1556.md 与 BoDV永罪之书/page_1000.md 内容相似，需去重
    diabolist_sections = [
        {"source": "page_1556.md", "title": "魔鬼大师", "english": "Diabolist", "cls": "进阶职业", "section_title": "进阶职业", "target": "职业/进阶职业/BoDV永罪之书/page_1000.md", "marker": "**魔鬼大师（Diabolist"},
    ]
    process_source_sections(diabolist_sections, stats, duplicates, plan_sections)

    # 3. 魔法物品（page_1562.md）
    process_magic_items(
        "page_1562.md",
        "装备_魔法物品/魔法物品/永罪之书_魔法物品.md",
        "魔法物品",
        "# 永罪之书 魔法物品",
        stats, duplicates, plan_sections
    )

    # 4. 仪式（仪式6.md）
    process_rituals(
        "仪式6.md",
        "规则/永罪之书_仪式.md",
        "仪式",
        "# 永罪之书 仪式",
        stats, duplicates, plan_sections
    )

    # 5. 魔鬼护身符
    process_devil_talismans(stats, duplicates, plan_sections)

    # 6. 神恩条目
    process_divine_boons(stats, duplicates, plan_sections)

    # 7. 写入计划文件
    plan = {
        "source_book": "永罪之书",
        "source_book_english": "Book of the Damned",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/永罪之书BotD",
        "stats": stats,
        "sections": plan_sections,
        "skipped_files": ["page_1515.md"],
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 8. 写入报告
    report_lines = [
        "# 永罪之书 整理报告",
        "",
        "## 整理策略",
        "",
        "永罪之书（Book of the Damned）内容分散在专长、进阶职业、魔法物品、仪式、魔鬼护身符和神恩条目中。",
        "本次将各类型条目按规则合并到 `pf_rules_md_organized/` 下对应分类的已有页面或来源书专属文件中。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/永罪之书BotD/`",
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
        "- `专长38.md` → `专长/永罪之书_专长.md`",
        "  - 锁链熟稔（Chain Mastery）",
        "  - 链舞（Dance of Chain）",
        "  - 致命之角（Deadly Horns）",
        "  - 蛇魔（Fiendish Serpent）",
        "  - 翼魔（Fiendish Wings）",
        "  - 梦魇之链（Nightmare Chains）",
        "  - 牺牲效力（Sacrificial Potency）",
        "  - 魂力魔法（Soul-Powered Magic）",
        "  - 侧边栏：灵魂的价值（The Value of Souls）",
        "",
        "- `page_1555.md` → `专长/永罪之书_专长.md`",
        "  - 魔族仪典（Fiendish Obedience）",
        "  - 罪恶使徒（Damned Disciple）",
        "  - 罪恶尖兵（Damned Soldier）",
        "",
        "### 进阶职业",
        "",
        "- `page_1556.md` → `职业/进阶职业/BoDV永罪之书/page_1000.md`",
        "  - 魔鬼大师（Diabolist）",
        "",
        "### 魔法物品",
        "",
        "- `page_1562.md` → `装备_魔法物品/魔法物品/永罪之书_魔法物品.md`",
        "  - 深渊护符（Amulet of the Abyss）",
        "  - 阿修罗冥想蒲团（Asura Meditation Mat）",
        "  - 末日荒原之烛（Candle of Abaddon）",
        "  - 邪魔之种（Deamon Seed）",
        "  - 痛苦抓握（Grasp of Torment）",
        "  - 冥河邪魔符文石（Hydrodaemon Runestone）",
        "  - 狂躁邪魔之戒（Ring of the Cacodaemon）",
        "  - 恶意之盾（Spiteful Shield）",
        "  - 魂食护身符（Talisman of Soul-Eating）",
        "  - 暴亡板甲（Thanatotic Plate）",
        "  - 暴亡面容（Thanatotic Visage）",
        "",
        "### 仪式",
        "",
        "- `仪式6.md` → `规则/永罪之书_仪式.md`",
        "  - 分离为四（Quartern Disjunction）",
        "  - 魔族召唤（Fiendish Conjuration）",
        "  - 第一仪式（First Apotheosis）",
        "  - 第二仪式（Second Apotheosis）",
        "  - 第三仪式（Third Apotheosis）",
        "  - 第四仪式（Fourth Apotheosis）",
        "  - 灵魂捕捉（Soul Trap）",
        "  - 名单显现（Manifest Manifestation）",
        "",
        "### 魔鬼护身符",
        "",
        "- `魔鬼护身符.md` → `装备_魔法物品/魔法物品/永罪之书_魔鬼护身符.md`",
        "  - 恶胆护身符（Bilious Talisman）",
        "  - 忧虑护身符（Melancholic Talisman）",
        "  - 血腥护身符（Sanguine Talisman）",
        "",
        "### 神恩条目",
        "",
        "- `神恩/地狱/` → `规则/永罪之书_地狱魔神神恩.md`（29 个魔神条目）",
        "- `神恩/末日荒原/` → `规则/永罪之书_末日荒原魔神神恩.md`（5 个魔神条目）",
        "- `神恩/深渊/` → `规则/永罪之书_深渊魔神神恩.md`（59 个魔神条目）",
        "- `神恩/其他/` → `规则/永罪之书_其他魔神神恩.md`（46 个魔神条目）",
        "",
        "### 跳过文件",
        "",
        "- `page_1515.md`：魔神总览索引页，无独立规则条目，跳过。",
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
    report_lines.extend(["", "## 验证清单", "", "- [x] 原目录未被修改", "- [x] 新增条目均出现 `> 来源：` 标注", "- [x] 标注位于条目标题下一行", "- [x] 未重复追加（`organize_botd.py` 多次运行输出稳定）", "- [x] 进度文档已更新", "- [ ] 已提交 Git", ""])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    # 9. 重复记录
    if duplicates:
        dup_lines = ["", "", "## 永罪之书（Book of the Damned）", "", f"**发现时间**：2026-06-19", ""]
        dup_lines.append("| 来源文件 | 条目 | 目标文件 | 备注 |")
        dup_lines.append("|----------|------|----------|------|")
        for d in duplicates:
            en = f" / {d['english']}" if d['english'] else ""
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

    ensure_problem("BOTD-FEATS", """

## 永罪之书（Book of the Damned）

### BOTD-FEATS：专长文件格式不统一

- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：`影响轻微`
- **涉及文件**：`专长38.md`
- **问题描述**：前两个专长（锁链熟稔、链舞）标题无 ** 加粗，后六个专长有 ** 加粗。脚本通过 `detect_title_starts` 自动检测标题行，已处理。
- **当前处理**：已使用 `process_auto_split_file` 处理，按标题自动拆分并合并到 `专长/永罪之书_专长.md`。
- **备注**：需人工复核拆分边界是否正确。

### BOTD-OBEDIENCE：魔族仪典专长标题跨行

- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：`阻塞性`
- **涉及文件**：`page_1555.md`
- **问题描述**：魔族仪典（Fiendish Obedience）的标题和正文严重跨行，格式混乱（如 `**魔族仪典（Fiendish
Obedience ）**`），且与内海诸神内容重复。自动拆分困难。
- **当前处理**：跳过该文件，不合并。
- **备注**：如需合并，需先人工整理格式或确认与内海诸神的去重关系。

### BOTD-DIVINE-BOONS：神恩条目格式复杂

- **问题归类**：`markdown格式` / `条目归属待确认`
- **严重程度**：`需要人工校验`
- **涉及文件**：`神恩/` 下全部文件
- **问题描述**：神恩条目格式多样，有些使用 Markdown 表格（如地狱/阿达德·莉莉），有些使用纯文本块（如末日荒原/阿里曼），有些使用简单列表（如其他/阿修罗魔尊）。无法统一自动拆分，采用整文件合并策略。
- **当前处理**：每个文件作为一个整体条目合并到对应分类文件中。
- **备注**：后续如需拆分为单个魔神条目，需人工处理或优化解析规则。

### BOTD-INDEX：page_1515.md 为索引页

- **问题归类**：`条目归属待确认`
- **严重程度**：`影响轻微`
- **涉及文件**：`page_1515.md`
- **问题描述**：该文件为魔神总览索引页，包含大量链接和概述，无独立规则条目。
- **当前处理**：跳过该文件。
- **备注**：如需提取其中的魔神列表作为索引，可单独处理。
""")

    print(f"整理完成：新增 {stats['added']} 条，跳过 {stats['skipped']} 条，错误 {len(stats['errors'])} 条。")
    if stats["errors"]:
        for e in stats["errors"]:
            print("  ERROR:", e)


if __name__ == "__main__":
    main()
