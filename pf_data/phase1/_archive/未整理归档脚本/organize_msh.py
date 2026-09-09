#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 怪物召唤者手册（Monster Summoner's Handbook）内容到已有分类目录。

本次处理：
- 魔法物品：page_666.md（奇物 + 武器附魔）
- 背景特性：背景特性47.md
- 职业变体：变体/page_665.md、page_1344.md、page_1575.md、德鲁伊变体.md、血脉狂怒者.md

跳过：
- page_667.md：格式严重混乱，专长/规则/模板/召唤列表混排，无法可靠自动拆分

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

from html_fallback import read_source_text, mark_connected, find_html_for, convert_html_to_clean_md

BASE = "/Users/chezi/code/java/pf_agent/pf_data/phase1"
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/怪物召唤者手册MSH")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "MSH_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "MSH_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")
PROBLEM_RECORD_PATH = os.path.join(BASE, "未整理目录整理问题记录.md")

SOURCE_NOTE_TEMPLATE = "> 来源：怪物召唤者手册（Monster Summoner's Handbook），页码见原书，未整理 → 怪物召唤者手册MSH → {section_title}"

# 职业变体条目配置
SECTIONS = [
    # 召唤师变体（已按 class_subcategory_mapping 迁到 page_410.md）
    {"source": "变体/page_665.md", "title": "制法召唤师", "english": "Counter-Summoner", "cls": "召唤师", "section_title": "变体", "target": "职业/基础职业/召唤师/page_410.md", "marker": "制法召唤师（Counter-Summoner)"},
    # 审判者变体
    {"source": "变体/page_1344.md", "title": "怪物战术家", "english": "Monster Tactician", "cls": "审判者", "section_title": "变体", "target": "职业/基础职业/审判者/page_78.md", "marker": "怪物战术家（Monster"},
    # 牧师变体 - 标题格式特殊，无 **
    {"source": "变体/page_1575.md", "title": "神使呼唤者", "english": "Herald Caller", "cls": "牧师", "section_title": "变体", "target": "职业/核心职业/牧师/page_41.md", "marker": "Herald Caller神使呼唤者"},
    # 德鲁伊变体
    {"source": "变体/德鲁伊变体.md", "title": "元素友伴", "english": "Elemental Ally", "cls": "德鲁伊", "section_title": "变体", "target": "职业/核心职业/德鲁伊/page_37.md", "marker": "元素友伴（Elemental Ally）【德鲁伊变体】"},
    # 血脉狂怒者变体
    {"source": "变体/血脉狂怒者.md", "title": "先祖先驱", "english": "Ancestral Harbinger", "cls": "血脉狂怒者", "section_title": "变体", "target": "职业/混合职业/血脉狂怒者/page_100.md", "marker": "先祖先驱（Ancestral"},
]

KNOWN_LABELS = {
    "制造要求", "需求", "制造成本", "制造条件", "灵光", "位置", "栏位", "价格",
    "施法者等级", "重量", "类别", "描述", "来源", "出处", "效果", "先决条件",
    "专长效果", "通常", "特殊说明", "拥有此专长前的正常情况", "好处", "学派",
    "施放时间", "成分", "技能检定", "距离", "区域", "持续时间", "豁免", "法术抗力",
    "反冲", "失败", "类型", "需求",
}

# page_666.md 的魔法物品标签（用于拆分内联格式）
MAGIC_ITEM_LABELS = ["位置", "价格", "灵光", "施法者等级", "重量", "制造成本", "制造要求", "制造条件"]


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
    marker_key = f"<!-- MSH-source:{section['source']}:{section['title']} -->"
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
    """修正标题与正文挤在同一行的情况。"""
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
    """将片段拆分为标题行与正文行。"""
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
    marker = f"<!-- MSH-source:{section['source']}:{section['title']} -->"
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
    """自动检测以中文名称开头的标题行位置。"""
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


def process_single_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """处理单文件多条目（背景特性），每个条目标题行以 ** 开头，按标题自动拆分。"""
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


# page_666.md 专用：魔法物品标题检测（内联格式）
# 格式示例：裂石盔甲ARMOR OF FRAGMENTING STONE位置 盔甲价格 21650g...
MAGIC_ITEM_LABELS = ["位置", "价格", "灵光", "施法者等级", "重量", "制造成本", "制造要求", "制造条件"]
MAGIC_ITEM_TITLE_RE = re.compile(
    r'([一-鿿]{2,})\s*([A-Z][A-Z\s\'-]{2,})(?=\s*(?:' + '|'.join(re.escape(l) for l in MAGIC_ITEM_LABELS) + r'))'
)
MAGIC_ITEM_CN_ONLY_RE = re.compile(r'([一-鿿]{2,})(?=\s*位置)')


def detect_magic_item_starts(text):
    """检测 page_666.md 风格的魔法物品标题位置。

    标题的中文名与英文名可能跨行，因此基于全文而非单行匹配。
    """
    candidates = []
    # 中文名 + 英文名（如 裂石盔甲ARMOR OF FRAGMENTING STONE）
    for m in MAGIC_ITEM_TITLE_RE.finditer(text):
        candidates.append((m.start(), m.group(1), m.group(2).strip()))
    # 仅中文名（如 巨化召唤权杖）
    for m in MAGIC_ITEM_CN_ONLY_RE.finditer(text):
        pos = m.start()
        if any(abs(pos - c[0]) <= len(m.group(1)) for c in candidates):
            continue
        candidates.append((pos, m.group(1), ""))

    candidates.sort()

    starts = []
    for pos, cn, en in candidates:
        if cn in KNOWN_LABELS:
            continue
        # 跳过括号内的误匹配（如 制造奇物（Craft...））
        prev_char = text[pos - 1] if pos > 0 else ""
        if prev_char in "（(":
            continue
        if len(cn) < 2:
            continue
        starts.append((pos, cn, en))
    return starts


def build_magic_item_block(sec, section_text, section_title):
    """构建魔法物品追加块（处理内联格式）。"""
    section_text = section_text.strip()

    # 提取标题
    m = MAGIC_ITEM_TITLE_RE.search(section_text)
    if m:
        cn = m.group(1)
        en = m.group(2).strip().replace("\n", " ")
        title_line = f"**{cn}（{en}）**"
    else:
        m2 = MAGIC_ITEM_CN_ONLY_RE.match(section_text)
        if m2:
            cn = m2.group(1)
            en = ""
            title_line = f"**{cn}**"
        else:
            parts = section_text.splitlines()
            title_line = parts[0].strip()
            cn = title_line
            en = ""

    # 移除标题部分，正文保留原行
    if m:
        en_pattern = r'\s+'.join(re.escape(part) for part in en.split())
        title_re = re.compile(re.escape(cn) + r'\s*' + en_pattern, re.DOTALL)
        body = title_re.sub('', section_text, count=1).strip()
    else:
        body = section_text[len(cn):].strip()

    body_lines = [l.strip() for l in body.splitlines() if l.strip()]

    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
    marker = f"<!-- MSH-source:{sec['source']}:{sec['title']} -->"
    result = [marker, title_line, note]
    result.extend(body_lines)
    if result[-1].strip() != "":
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def _split_item_labels(text: str) -> str:
    """在物品属性标签前插入换行，将内联属性拆分为多行。"""
    labels = ["位置", "价格", "灵光", "施法者等级", "重量", "类型", "制造DC",
              "制造成本", "制造要求", "制造条件"]
    # 在标签前插入换行（如果不在行首且前面不是换行）
    for label in labels:
        text = re.sub(rf'(?<!\n)(?={re.escape(label)}[：:])', '\n', text)
    # 合并连续空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def process_magic_items(stats, duplicates, plan_sections):
    """处理 page_666.md 魔法物品文件（内联格式）。

    使用 HTML 回退清洗后，按已知物品 marker 切片，统一标题格式并拆分属性标签。
    将奇物和武器附魔分开处理：
    - 破召（Summon Bane）是武器附魔，其余为奇物。
    """
    source_file = "page_666.md"
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    # 使用 HTML 回退清洗后的文本
    text = read_source_text(Path(src_path), kind="item")

    # 9 个已知物品（含 1 个武器附魔）
    items = [
        {"cn": "裂石盔甲", "en": "Armor of Fragmenting Stone", "marker": "裂石盔甲"},
        {"cn": "天界干涉护腕", "en": "Bracers of Celestial Intervention", "marker": "天界干涉护腕"},
        {"cn": "召唤者羽毛", "en": "Caller's Feather", "marker": "召唤者羽毛"},
        {"cn": "临时魔宠护符", "en": "Periapt of Temporary Familiar", "marker": "临时魔宠护符"},
        {"cn": "巨化召唤权杖", "en": "Rod of Giant Summoning", "marker": "巨化召唤权杖"},
        {"cn": "召唤者长袍", "en": "Summoner's Robe", "marker": "召唤者长袍"},
        {"cn": "暴风雨之剑", "en": "Sword of Tempests", "marker": "暴风雨之剑"},
        {"cn": "束缚面容", "en": "Visage of the Bound", "marker": "束缚面容"},
        {"cn": "破召", "en": "Summon Bane", "marker": "破召", "weapon": True},
    ]

    positions = []
    for it in items:
        idx = text.find(it["marker"])
        if idx == -1:
            stats["errors"].append(f"{source_file} 中未找到物品: {it['cn']}")
            return
        positions.append((idx, it))
    positions.sort()

    wondrous_target = "装备_魔法物品/魔法物品/奇物/怪物召唤者手册_奇物.md"
    weapon_target = "装备_魔法物品/武器/怪物召唤者手册_武器附魔.md"

    wondrous_blocks = []
    weapon_blocks = []

    for i, (pos, it) in enumerate(positions):
        end_pos = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        section_text = text[pos:end_pos]

        target_path = weapon_target if it.get("weapon") else wondrous_target
        section_title = "武器附魔" if it.get("weapon") else "奇物"

        sec = {
            "source": source_file,
            "title": it["cn"],
            "english": it["en"],
            "target": target_path,
            "section_title": section_title,
        }

        # 清理段落
        section_text = re.sub(r'\[http://[^\]]*\][^\n]*', '', section_text)
        section_text = re.sub(r'译者[：:][^\n]*', '', section_text)

        # 彻底移除标题部分（中文名 + 英文名，可能跨行）
        en_parts = [re.escape(part) for part in it['en'].upper().split()]
        en_pattern = r'\s*'.join(en_parts)
        title_re = re.compile(
            rf"{re.escape(it['cn'])}\s*{en_pattern}",
            re.IGNORECASE | re.DOTALL
        )
        section_text = title_re.sub('', section_text, count=1).strip()

        section_text = _split_item_labels(section_text)

        section_lines = section_text.splitlines()
        # 段首可能残留英文名单词或空行，跳过直到遇到有效正文
        body_lines = []
        started = False
        for line in section_lines:
            stripped = line.strip()
            if not started:
                # 跳过空行和仅大写英文/空格的残留行
                if stripped == "":
                    continue
                if re.match(r'^[A-Z\s\'-]+$', stripped):
                    continue
                started = True
            body_lines.append(line)
        # 去掉正文末尾的空行
        while body_lines and body_lines[-1].strip() == "":
            body_lines.pop()

        title_line = f"**{it['cn']}（{it['en']}）**"
        note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
        marker = f"<!-- MSH-source:{source_file}:{it['cn']} -->"
        block_lines = [marker, title_line, note, ""]
        block_lines.extend(body_lines)
        block_lines.extend(["", ""])
        block = "\n".join(block_lines) + "\n"

        if it.get("weapon"):
            weapon_blocks.append(block)
        else:
            wondrous_blocks.append(block)

        plan_sections.append({**sec, "action": "added"})

    # 重建目标文件（原文件只包含 page_666.md 内容）
    os.makedirs(os.path.join(ORG_BASE, os.path.dirname(wondrous_target)), exist_ok=True)
    os.makedirs(os.path.join(ORG_BASE, os.path.dirname(weapon_target)), exist_ok=True)

    with open(os.path.join(ORG_BASE, wondrous_target), "w", encoding="utf-8") as f:
        f.write("# 怪物召唤者手册 奇物\n\n")
        f.write("".join(wondrous_blocks))

    with open(os.path.join(ORG_BASE, weapon_target), "w", encoding="utf-8") as f:
        f.write("# 怪物召唤者手册 武器附魔\n\n")
        f.write("".join(weapon_blocks))

    stats["added"] += len(items)


def process_page_667_full(stats, duplicates, plan_sections):
    """完整处理 page_667.md：从 HTML 回退清洗后拆分专长、简易模板、守护灵规则与扩展召唤列表。"""
    source_file = "page_667.md"
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return

    src_md_path = Path(src_path)
    mark_connected(src_md_path, "organize_msh.py", kind="feat")

    html_path = find_html_for(src_md_path)
    if not html_path:
        stats["errors"].append(f"找不到 {source_file} 对应的 HTML 源文件")
        return

    text = convert_html_to_clean_md(html_path, kind="")

    FEATS = {
        '增强呼唤': 'Augment Calling',
        '驱逐重击': 'Banishing Critical',
        '维度察觉': 'Dimensional Awareness',
        '次元断裂': 'Dimensional Disruption',
        '位面之力': 'Planar Focus',
        '侦查召唤': 'Scouting Summons',
        '实体幽影': 'Solid Shadows',
        '刺青协调': 'Tattoo Attunement',
        '刺青转变': 'Tattoo Conversion',
        '刺青转换': 'Tattoo Transformation',
        '思乡游子诗篇': 'Ballad of the Homesick Wanderer',
        '多功能召唤生物': 'Versatile Summon Monster',
        '多功能召唤自然盟友': "Versatile Summon Nature's Ally",
        '呼神守卫': 'Summon Guardian Spirit',
        '扩展召唤怪物': 'Expanded Summon Monster',
        '解法专攻': 'Dispel Focus',
        '高等解法专攻': 'Greater Dispel Focus',
    }
    TEMPLATES = {
        '气流生物': 'Aerial Creature',
        '水流生物': 'Aqueous Creature',
        '地层生物': 'Chthonic Creature',
        '黑暗生物': 'Dark Creature',
        '烈火生物': 'Fiery Creature',
        '原初生物': 'Primordial Creature',
    }
    GUARDIAN = {
        '守护灵': 'Guardian Spirits',
        '创造守护灵': '',
    }
    INTRO = {
        '誓缚和呼唤': 'Binding and Calling',
        '跨位面亚种的力量': 'Extraplanar Power',
    }
    SUMMON_INTRO = {
        '扩展召唤列表': '',
    }
    CN_NUMS = ['一', '二', '三', '四', '五', '六', '七', '八', '九']

    TITLE_MAP = {}
    for cn, en in FEATS.items():
        TITLE_MAP[cn] = ("feat", en)
    for cn, en in TEMPLATES.items():
        TITLE_MAP[cn] = ("template", en)
    for cn, en in GUARDIAN.items():
        TITLE_MAP[cn] = ("guardian", en)
    for cn, en in INTRO.items():
        TITLE_MAP[cn] = ("intro", en)
    for cn, en in SUMMON_INTRO.items():
        TITLE_MAP[cn] = ("summon_intro", en)
    for lvl, cn_num in enumerate(CN_NUMS, 1):
        TITLE_MAP[f"{cn_num}级召唤怪物"] = ("summon_list", "")

    def find_boundaries(text, title_map):
        candidates = []
        for cn, (cat, en) in title_map.items():
            if en:
                en_parts = en.split()
                en_pattern = r'\s*'.join(re.escape(p) for p in en_parts)
                # 支持两种标题格式：中文名（English Name）和 中文名 English Name
                paren_pat = re.escape(cn) + r'\s*[（(]' + en_pattern + r'[）)]'
                space_pat = re.escape(cn) + r'\s+' + en_pattern
                pat = re.compile(f'(?:{paren_pat}|{space_pat})')
            else:
                pat = re.compile(re.escape(cn))
            for m in pat.finditer(text):
                if cat == "summon_list":
                    snippet = text[m.end():m.end() + 200]
                    if "来源" not in snippet or "挑战等级" not in snippet:
                        continue
                candidates.append((m.start(), m.end(), cn, cat, en))
        candidates.sort()
        filtered = []
        for c in candidates:
            dup_idx = None
            for i, ex in enumerate(filtered):
                if abs(c[0] - ex[0]) < 5:
                    dup_idx = i
                    break
            if dup_idx is None:
                filtered.append(c)
            else:
                if len(c[2]) > len(filtered[dup_idx][2]):
                    filtered[dup_idx] = c
        return filtered

    boundaries = find_boundaries(text, TITLE_MAP)
    if not boundaries:
        stats["errors"].append(f"{source_file} 未找到任何已知标题边界")
        return

    targets = {
        "feat": "专长/怪物召唤者手册MSH_专长.md",
        "template": "规则/怪物召唤者手册MSH_简易模板.md",
        "guardian": "规则/怪物召唤者手册MSH_守护灵.md",
        "summon_list": "规则/怪物召唤者手册MSH_扩展召唤列表.md",
        "intro": "规则/怪物召唤者手册MSH_page_667.md",
    }
    section_titles = {
        "feat": "专长",
        "template": "简易模板",
        "guardian": "守护灵",
        "summon_list": "扩展召唤列表",
        "summon_intro": "扩展召唤列表",
        "intro": "章节引言",
    }
    headers = {
        "template": "# 怪物召唤者手册 简易模板\n\n",
        "guardian": "# 怪物召唤者手册 守护灵\n\n",
        "summon_list": "# 怪物召唤者手册 扩展召唤列表\n\n",
        "intro": "# 怪物召唤者手册 page_667 章节引言\n\n",
    }

    # 专长目标文件已存在，使用追加；其余文件本次整体生成
    feats_target_full = os.path.join(ORG_BASE, targets["feat"])
    ensure_header(targets["feat"], "# 怪物召唤者手册 专长")
    feats_existing_text = open(feats_target_full, "r", encoding="utf-8").read() if os.path.exists(feats_target_full) else ""

    generated = {cat: [] for cat in targets if cat != "feat"}
    for cat in generated:
        full = os.path.join(ORG_BASE, targets[cat])
        os.makedirs(os.path.dirname(full), exist_ok=True)

    def format_section_title(cn, en):
        if en:
            en_clean = re.sub(r'\s+', ' ', en).strip()
            return f"**{cn}（{en_clean}）**"
        return f"**{cn}**"

    def build_entry_block(cn, en, body_text, section_title):
        title_line = format_section_title(cn, en)
        note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
        marker = f"<!-- MSH-source:{source_file}:{cn} -->"
        body_lines = [l.rstrip() for l in body_text.splitlines()]
        while body_lines and body_lines[0].strip() == "":
            body_lines.pop(0)
        # 去除末尾残留的空行或孤立的加粗标记（通常是下一条目标题的 ** 前缀残留）
        while body_lines and body_lines[-1].strip() in ("", "**"):
            body_lines.pop()
        block_lines = [marker, title_line, note, ""]
        block_lines.extend(body_lines)
        if block_lines[-1].strip() != "":
            block_lines.append("")
        block_lines.append("")
        return "\n".join(block_lines) + "\n"

    for i, (start, end, cn, cat, en) in enumerate(boundaries):
        next_start = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        body_text = text[end:next_start]

        sec = {
            "source": source_file,
            "title": cn,
            "english": en,
            "target": targets.get(cat, targets["summon_list"]),
            "section_title": section_titles.get(cat, section_titles["summon_list"]),
        }

        if cat == "feat":
            present, reason = already_present(feats_existing_text, sec)
            if present:
                duplicates.append({
                    "source": source_file,
                    "title": cn,
                    "english": en,
                    "target": targets[cat],
                    "reason": reason,
                })
                stats["skipped"] += 1
                plan_sections.append({**sec, "action": "skipped", "reason": reason})
                continue
            block = build_entry_block(cn, en, body_text, section_titles[cat])
            append_to_target(targets[cat], block)
            feats_existing_text += block
            stats["added"] += 1
            plan_sections.append({**sec, "action": "added"})
        else:
            block = build_entry_block(cn, en, body_text, section_titles[cat])
            if cat == "summon_intro":
                generated["summon_list"].insert(0, block)
            else:
                generated[cat].append(block)
            stats["added"] += 1
            plan_sections.append({**sec, "action": "added"})

    # 写回非专长目标文件
    for cat, blocks in generated.items():
        full = os.path.join(ORG_BASE, targets[cat])
        with open(full, "w", encoding="utf-8") as f:
            f.write(headers.get(cat, ""))
            f.write("".join(blocks))


def main():
    stats = {"added": 0, "skipped": 0, "errors": []}
    duplicates = []
    plan_sections = []

    # 1. 职业变体
    process_source_sections(SECTIONS, stats, duplicates, plan_sections)

    # 2. 背景特性
    process_single_file(
        "背景特性47.md",
        "背景/怪物召唤者手册_背景特性.md",
        "背景特性",
        "# 怪物召唤者手册 背景特性",
        stats, duplicates, plan_sections
    )

    # 3. 魔法物品（page_666.md）— 使用 HTML 回退清洗后处理
    mark_connected(Path(SRC_DIR) / "page_666.md", "organize_msh.py", kind="item")
    process_magic_items(stats, duplicates, plan_sections)

    # 4. page_667.md 完整处理：使用 HTML 回退清洗后拆分专长/模板/守护灵/召唤列表
    process_page_667_full(stats, duplicates, plan_sections)

    # 5. 写入计划文件
    plan = {
        "source_book": "怪物召唤者手册",
        "source_book_english": "Monster Summoner's Handbook",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/怪物召唤者手册MSH",
        "stats": stats,
        "sections": plan_sections,
        "skipped_files": [],
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 5. 写入报告
    report_lines = [
        "# 怪物召唤者手册 整理报告",
        "",
        "## 整理策略",
        "",
        "怪物召唤者手册（Monster Summoner's Handbook）内容分散在魔法物品、背景特性、职业变体等文件中。",
        "本次将各类型条目按规则合并到 `pf_rules_md_organized/` 下对应分类的已有页面或来源书专属文件中。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/怪物召唤者手册MSH/`",
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
        "- `变体/page_665.md` → 召唤师/page_410.md：制法召唤师（Counter-Summoner）",
        "- `变体/page_1344.md` → 审判者/page_78.md：怪物战术家（Monster Tactician）",
        "- `变体/page_1575.md` → 牧师/page_41.md：神使呼唤者（Herald Caller）",
        "- `变体/德鲁伊变体.md` → 德鲁伊/page_37.md：元素友伴（Elemental Ally）",
        "- `变体/血脉狂怒者.md` → 血脉狂怒者/page_100.md：先祖先驱（Ancestral Harbinger）",
        "",
        "### 背景特性",
        "",
        "- `背景特性47.md` → `背景/怪物召唤者手册_背景特性.md`",
        "  - 屠魔召唤师（Demonbane Summoner）",
        "  - 异物纽带（Outsider Ties）",
        "  - 邪恶领域（Vile Domain）",
        "",
        "### 魔法物品",
        "",
        "- `page_666.md` → `装备_魔法物品/魔法物品/奇物/怪物召唤者手册_奇物.md`",
        "  - 裂石盔甲（Armor of Fragmenting Stone）",
        "  - 天界干涉护腕（Bracers of Celestial Intervention）",
        "  - 召唤者羽毛（Caller's Feather）",
        "  - 临时魔宠护符（Periapt of Temporary Familiar）",
        "  - 巨化召唤权杖（Rod of Giant Summoning）",
        "  - 召唤者长袍（Summoner's Robe）",
        "  - 暴风雨之剑（Sword of Tempests）",
        "  - 束缚面容（Visage of the Bound）",
        "",
        "- `page_666.md` → `装备_魔法物品/武器/怪物召唤者手册_武器附魔.md`",
        "  - 破召（Summon Bane）",
        "",
        "### 专长（page_667.md）",
        "",
        "- `page_667.md` → `专长/怪物召唤者手册MSH_专长.md`",
        "  - 增强呼唤（Augment Calling）",
        "  - 驱逐重击（Banishing Critical）",
        "  - 维度察觉（Dimensional Awareness）",
        "  - 次元断裂（Dimensional Disruption）",
        "  - 位面之力（Planar Focus）",
        "  - 侦查召唤（Scouting Summons）",
        "  - 实体幽影（Solid Shadows）",
        "  - 刺青协调（Tattoo Attunement）",
        "  - 刺青转变（Tattoo Conversion）",
        "  - 刺青转换（Tattoo Transformation）",
        "  - 思乡游子诗篇（Ballad of the Homesick Wanderer）",
        "  - 多功能召唤生物（Versatile Summon Monster）",
        "  - 多功能召唤自然盟友（Versatile Summon Nature's Ally）",
        "  - 呼神守卫（Summon Guardian Spirit）",
        "  - 扩展召唤怪物（Expanded Summon Monster）",
        "  - 解法专攻（Dispel Focus）",
        "  - 高等解法专攻（Greater Dispel Focus）",
        "",
        "### 简易模板（page_667.md）",
        "",
        "- `page_667.md` → `规则/怪物召唤者手册MSH_简易模板.md`",
        "  - 气流生物（Aerial Creature）",
        "  - 水流生物（Aqueous Creature）",
        "  - 地层生物（Chthonic Creature）",
        "  - 黑暗生物（Dark Creature）",
        "  - 烈火生物（Fiery Creature）",
        "  - 原初生物（Primordial Creature）",
        "",
        "### 守护灵（page_667.md）",
        "",
        "- `page_667.md` → `规则/怪物召唤者手册MSH_守护灵.md`",
        "  - 守护灵（Guardian Spirits）",
        "  - 创造守护灵（后天模板）",
        "",
        "### 扩展召唤列表（page_667.md）",
        "",
        "- `page_667.md` → `规则/怪物召唤者手册MSH_扩展召唤列表.md`",
        "  - 一级到九级召唤怪物扩展列表",
        "",
        "### page_667.md 章节引言",
        "",
        "- `page_667.md` 中的章节引言已归档到 `规则/怪物召唤者手册MSH_page_667.md`",
        "  - 誓缚和呼唤（Binding and Calling）",
        "  - 跨位面亚种的力量（Extraplanar Power）",
        "",
        "### 已完全处理的文件",
        "",
        "- `page_666.md`（魔法物品）",
        "- `page_667.md`（专长、简易模板、守护灵、扩展召唤列表、章节引言）",
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

    # 6. 重复记录（避免重复追加同来源书章节）
    if duplicates:
        dup_anchor = "## 怪物召唤者手册（Monster Summoner's Handbook）"
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

    # 7. 问题记录
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

    ensure_problem("MSH-PAGE667", """

## 怪物召唤者手册（Monster Summoner's Handbook）

### ~~MSH-PAGE667：page_667.md 格式严重混乱~~（已解决）

- **问题归类**：`markdown格式` / `文件结构混乱`
- **严重程度**：`影响严重`
- **涉及文件**：`page_667.md`
- **问题描述**：该文件内容极其混杂，包含专长、规则说明、简易模板、守护灵规则、扩展召唤列表等多种类型。标题格式不统一，专长与规则说明混排无清晰边界。
- **处理方式**：使用 HTML 回退（`page_667.html`）清洗后，通过预定义标题边界自动拆分为：
  - 17 个专长 → `专长/怪物召唤者手册MSH_专长.md`
  - 6 个简易模板 → `规则/怪物召唤者手册MSH_简易模板.md`
  - 守护灵规则与创造守护灵模板 → `规则/怪物召唤者手册MSH_守护灵.md`
  - 扩展召唤列表（含 1-9 级）→ `规则/怪物召唤者手册MSH_扩展召唤列表.md`
  - 章节引言 → `规则/怪物召唤者手册MSH_page_667.md`
- **状态**：`已解决`
- **处理时间**：2026-07-18

### MSH-PAGE666：魔法物品内联格式

- **问题归类**：`markdown格式` / `标题与属性内联`
- **严重程度**：`影响中等`
- **涉及文件**：`page_666.md`
- **问题描述**：魔法物品标题和属性全部挤在一行，无 `**` 加粗分隔。例如：`裂石盔甲ARMOR OF FRAGMENTING STONE位置 盔甲价格 21650g；灵光：中等咒法系...`
- **当前处理**：脚本使用正则匹配中文名+英文名来拆分标题，然后按属性标签（位置、价格、灵光等）拆分正文。
- **备注**：需人工复核拆分边界和属性提取是否正确。

### MSH-VARIANTS：变体文件格式差异

- **问题归类**：`markdown格式` / `标题格式不统一`
- **严重程度**：`影响轻微`
- **涉及文件**：`变体/page_1575.md`、`变体/血脉狂怒者.md`
- **问题描述**：
  - `page_1575.md` 标题无 `**` 加粗，格式为 `Herald Caller神使呼唤者`。
  - `血脉狂怒者.md` 标题后有额外文字 `崇皇时王`。
- **当前处理**：脚本使用特殊 marker 定位变体起始位置。
- **备注**：需人工复核变体内容是否完整提取。
""")

    print(f"整理完成：新增 {stats['added']} 条，跳过 {stats['skipped']} 条，错误 {len(stats['errors'])} 条。")
    if stats["errors"]:
        for e in stats["errors"]:
            print("  ERROR:", e)


if __name__ == "__main__":
    main()
