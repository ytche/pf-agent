#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
怪物法典 MC 未整理内容整理脚本（第二版）

把 pf_data/phase1/pf_rules_md/ 下属于"未整理 → 怪物法典MC"的条目，
按章节类型拆分到已有分类目录的对应 MD 文件中。

处理策略：
- 其他物品1.md：按物品类型拆分到装备_魔法物品各子目录或货品服务
- 各怪物章节：按"替换种族特性/天赋职业奖励/专长/法术/装备/魔法物品/变体职业"拆分
  - 种族特性、FCB → 种族/怪物种族/<种族>/
  - 专长 → 专长/怪物法典MC_专长.md
  - 法术 → 法术/怪物法典MC_法术.md
  - 变体职业 → 尝试识别职业，合并到对应职业的变体页面；无法识别时保留统一文件
  - 装备 → 装备_魔法物品/货品服务/怪物法典MC_货品.md
  - 魔法物品 → 按类型拆分到 奇物/魔法武器防具/戒指_权杖_法杖
"""

import json
import re
import shutil
from pathlib import Path
from collections import defaultdict


BASE_DIR = Path(__file__).parent.resolve()
SOURCE_DIR = BASE_DIR / "phase1" / "pf_rules_md"
TARGET_DIR = BASE_DIR / "phase1" / "pf_rules_md_organized"
MAPPING_FILE = BASE_DIR / "md_mapping.json"
REPORT_FILE = BASE_DIR / "mc_reorganization_report.md"
PLAN_FILE = BASE_DIR / "mc_reorganization_plan.json"

BOOK_L2 = "怪物法典MC"
BOOK_NAME = "怪物法典（Monster Codex）MC"


# ---------------------------------------------------------------------------
# 数据加载与索引
# ---------------------------------------------------------------------------

def load_mapping():
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_mc_entries(mapping):
    entries = []
    for md_name, info in mapping.items():
        tp = info.get("toc_path") or ""
        if tp.startswith(f"未整理 → {BOOK_L2}"):
            entries.append({
                "md_name": md_name,
                "html_name": info.get("html_file", ""),
                "toc_path": tp,
            })
    return entries


def build_toc_index(mapping):
    index = defaultdict(list)
    for md_name, info in mapping.items():
        tp = info.get("toc_path") or ""
        if tp:
            index[tp].append(md_name)
    return index


def find_in_target(md_name):
    if not md_name:
        return None
    found = list(TARGET_DIR.rglob(md_name))
    if not found:
        return None
    non_root = [p for p in found if p.parent != TARGET_DIR]
    if non_root:
        canonical_prefixes = (
            "/职业/", "/种族/", "/装备_魔法物品/", "/专长/", "/法术/", "/规则/"
        )
        for p in non_root:
            if any(prefix in str(p) for prefix in canonical_prefixes):
                return p
        return non_root[0]
    return found[0]


def resolve_target(desired_toc_path, fallback_path=None):
    md_names = TOC_INDEX.get(desired_toc_path, [])
    for md_name in md_names:
        found = find_in_target(md_name)
        if found:
            return found
    if fallback_path:
        return fallback_path
    return None


def read_source(md_name):
    return (SOURCE_DIR / md_name).read_text(encoding="utf-8", errors="ignore")


def read_target(path):
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def write_target(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append_to_target(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_target(path)
    if existing and not existing.endswith("\n"):
        existing += "\n"
    path.write_text(existing + "\n" + content + "\n", encoding="utf-8")


def already_contains(path, marker):
    if not path or not path.exists():
        return False
    return marker in read_target(path)


def source_note(l3_title, page=None):
    page_str = f"{page}页" if page else "页码见原书"
    return f"> 来源：{BOOK_NAME}，{page_str}，未整理 → {BOOK_L2} → {l3_title}"


def insert_note_after_headings(text, note_text, heading_pattern):
    def repl(match):
        return match.group(0) + "\n\n" + note_text + "\n"
    return re.sub(heading_pattern, repl, text, flags=re.MULTILINE)


# ---------------------------------------------------------------------------
# 章节拆分
# ---------------------------------------------------------------------------

SECTION_KEYWORDS = [
    ("新规则", "引言"),
    ("变体职业", "变体职业"),
    ("替换种族特性", "替换种族特性"),
    ("天赋职业奖励", "天赋职业奖励"),
    ("专长", "专长"),
    ("法术", "法术"),
    ("装备", "装备"),
    ("魔法物品", "魔法物品"),
    ("术士血脉", "术士血脉"),
    ("模板", "模板"),
    ("变异", "替换种族特性"),
    ("引用", "引用"),
]


def build_section_header_re(race_name=None):
    """构建章节标题正则。前缀限定为短文本且不含冒号，后续用 is_section_header 过滤。"""
    keywords = [
        "变体职业", "替换种族特性", "天赋职业奖励", "专长", "法术",
        "装备", "魔法物品", "术士血脉", "模板", "变异",
    ]
    patterns = ["新规则", "引用"]
    for kw in keywords:
        # 允许 0-8 个非星号、非冒号字符作为前缀（兼容“卓尔专长”这类简称）
        patterns.append("(?:[^*：:]{0,8}?)" + re.escape(kw))
    return re.compile(r"(\*\*(?:{})\*\*)".format("|".join(patterns)))


def is_section_header(text):
    inner = text.strip("*")
    inner_norm = re.sub(r"\s+", "", inner)
    inner_no_eng = re.sub(r"[A-Za-z]+", "", inner_norm)
    for kw, _ in SECTION_KEYWORDS:
        if inner_no_eng.endswith(kw) or inner_no_eng == kw:
            prefix = inner_no_eng[:-len(kw)] if inner_no_eng.endswith(kw) else ""
            # 合法前缀：空、种族名（少量中文，不含数字/冒号/量词等标签字符）
            if prefix == "" or (len(prefix) <= 8 and not re.search(r"[：:0-9件个名条；;]", prefix)):
                return True
    return False


def classify_section(header):
    for kw, stype in SECTION_KEYWORDS:
        if kw in header:
            return stype
    return "其他"


def split_sections(text, race_name=None):
    section_re = build_section_header_re(race_name)
    matches = [m for m in section_re.finditer(text) if is_section_header(m.group(1))]
    if not matches:
        return [("全文", text)]
    sections = []
    if matches[0].start() > 0:
        intro = text[:matches[0].start()].strip()
        if intro:
            sections.append(("引言", intro))
    for i, m in enumerate(matches):
        header = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        section_type = classify_section(header)
        sections.append((section_type, header + "\n" + content))
    return sections


# ---------------------------------------------------------------------------
# 通用块拆分（专长/法术/物品/变体职业都基于加粗标题块）
# ---------------------------------------------------------------------------

# 这些加粗文本属于标签/属性，不应作为独立条目标题
BLOCK_LABEL_DENYLIST = {
    # 法术/能力标签
    "持续时间", "豁免", "豁免检定", "法术抗力", "学派", "等级", "施法时间",
    "成分", "距离", "法术目标", "目标", "法术范围", "法术效果", "范围",
    "立即", "永久", "标准动作", "移动动作", "迅捷动作", "整轮动作",
    "自由动作", "直觉动作", "专注", "无害",
    # 物品/装备标签
    "价格", "重量", "类型", "制造DC", "效果", "制造", "手艺（炼金术）",
    "工艺(炼金)", "制造条件", "制造要求", "制造需求", "制造成本", "装备位置",
    "栏位", "灵光", "灵氲", "施法者等级", "出处", "来源", "起源描述",
    "DescriptionSource", "描述", "需求", "制造等级",
    # 专长/职业标签
    "先决条件", "专长效果", "特殊情况", "奖励专长", "举例", "本职技能", "阵营",
    "最终启示", "启示",
    # 生物/动物伙伴属性
    "起始属性", "体型", "速度", "防御等级", "攻击", "属性", "特性",
    "4级进化", "特殊攻击", "特殊能力", "天生武器", "徒手击打",
    # 陷阱标签
    "察觉检定", "解除装置检定", "触发", "重设",
}


def normalize_block_title(block_text):
    """把跨行的加粗标题压缩成单行。"""
    m = re.match(r"^(\*\*.*?\*\*)", block_text, re.DOTALL)
    if not m:
        return block_text
    title = m.group(1)
    normalized_title = re.sub(r"\s+", " ", title).strip()
    return normalized_title + block_text[m.end():]


def _looks_like_label(inner):
    """判断加粗文本是否是‘标签：值’形式的属性行。"""
    if "：" not in inner and ":" not in inner:
        return False
    label_part = re.split(r"[：:]", inner, maxsplit=1)[0]
    label_norm = re.sub(r"\s+", "", label_part)
    return label_norm in BLOCK_LABEL_DENYLIST


def _is_kept_title(text, m):
    title = m.group(1)
    inner = title.strip("*")
    inner_norm = re.sub(r"\s+", "", inner)

    if inner_norm.endswith((":", "：", "；", ";")):
        return False
    if inner_norm in BLOCK_LABEL_DENYLIST:
        return False
    if _looks_like_label(inner):
        return False
    if is_section_header(title):
        return False

    # 跳过行内引用式加粗，如“的**凶猛**特性”。
    start, end = m.start(), m.end()
    prev_char = text[start - 1] if start > 0 else ""
    next_char = text[end] if end < len(text) else ""
    if next_char in (":", "："):
        return False
    if (prev_char
            and not re.match(r"[\s\n\r\t\(\)\[\]\{\}，。：；！？、\"\'\*\|\-—\…]", prev_char)
            and next_char
            and re.match(r"[一-鿿0-9A-Za-z]", next_char)):
        return False
    return True


def split_into_blocks(text):
    """
    把文本按加粗标题拆分成独立块。
    跳过统计/章节标签，跳过章节标题，跳过行内引用式加粗。
    使用下一个被保留的标题作为块结束位置，避免标签截断条目内容。
    """
    title_re = re.compile(r"(\*\*.*?\*\*)", re.DOTALL)
    matches = list(title_re.finditer(text))
    kept_indices = [i for i, m in enumerate(matches) if _is_kept_title(text, m)]

    blocks = []
    for j, idx in enumerate(kept_indices):
        start = matches[idx].start()
        next_idx = kept_indices[j + 1] if j + 1 < len(kept_indices) else None
        block_end = matches[next_idx].start() if next_idx is not None else len(text)
        block_text = text[start:block_end].rstrip()
        if block_text:
            blocks.append(normalize_block_title(block_text))
    return blocks


def add_source_note_to_block(block_text, note_text):
    """在块的第一行加粗标题后插入来源标注。"""
    m = re.match(r"^(\*\*.*?\*\*)", block_text, re.DOTALL)
    if not m:
        return block_text
    return block_text[:m.end()] + "\n\n" + note_text + "\n" + block_text[m.end():]


# ---------------------------------------------------------------------------
# 变体职业：职业识别与目标文件解析
# ---------------------------------------------------------------------------

CLASS_KEYWORDS = [
    ("炼金术士发现", "炼金术师"),
    ("炼金术士", "炼金术师"),
    ("炼金术师", "炼金术师"),
    ("反圣武士", "反圣武士"),
    ("女巫", "女巫"),
    ("巫术", "女巫"),
    ("野蛮人", "野蛮人"),
    ("德鲁伊", "德鲁伊"),
    ("吟游诗人", "吟游诗人"),
    ("先知诅咒", "先知"),
    ("先知", "先知"),
]

# 优先使用的已有职业页面（基于 TOC/目录结构）
CLASS_TARGET_OVERRIDES = {
    "炼金术师": TARGET_DIR / "职业" / "基础职业" / "炼金术师" / "page_21.md",
    "反圣武士": TARGET_DIR / "职业" / "基础职业" / "反圣武士" / "page_406.md",
    "女巫": TARGET_DIR / "职业" / "基础职业" / "女巫" / "page_70.md",
    "野蛮人": TARGET_DIR / "职业" / "核心职业" / "野蛮人" / "page_35.md",
    "德鲁伊": TARGET_DIR / "职业" / "核心职业" / "德鲁伊" / "page_45.md",
    "吟游诗人": TARGET_DIR / "职业" / "核心职业" / "吟游诗人" / "page_38.md",
    "先知": TARGET_DIR / "职业" / "基础职业" / "先知" / "page_20.md",
}

UNIFIED_ARCHETYPES_TARGET = TARGET_DIR / "职业" / f"{BOOK_L2}_职业变体.md"


def detect_class_name(block_text):
    title_line = block_text.split("\n", 1)[0]
    search_text = title_line + "\n" + block_text[:400]
    for kw, cls in CLASS_KEYWORDS:
        if kw in search_text:
            return cls
    return None


# 职业变体章节中，属于职业能力描述而非独立变体/选项的加粗小标题
CLASS_FEATURE_LABELS = {
    "军用武器擅长", "炼金武器", "精确炸弹", "定向爆破", "震撼爆破",
    "爆破陷阱", "寻找陷阱", "吟游表演", "多才多艺", "奖励专长",
    "狂怒战术", "远古武装", "部族纽带", "自然的宽容", "远古行者",
    "消除敌意", "无懈可击", "消解炼化", "激发狂怒", "猎物必杀",
    "天怒印记", "咒符", "魔巫之眼", "豺狼形态", "飞行坐骑",
    "本职技能", "阵营", "摄食恐惧", "恐怖暴行",
    # 狗头人陷阱的统计标签（DC 会被 normalize 去掉）
    "类型", "察觉检定", "解除装置检定", "效果", "触发", "重设",
}


def _normalize_title(inner):
    """去掉英文、空白和常见标点，用于判断标题是否是职业能力标签。"""
    s = re.sub(r"[A-Za-z]+", "", inner)
    s = re.sub(r"\s+", "", s)
    s = s.strip(":：")
    return s


def is_main_class_option(title, inner):
    """判断加粗标题是否为职业变体/选项的顶层标题。"""
    inner_clean = inner.rstrip(":：")
    # 显式职业变体
    if "（" in inner and "变体）" in inner:
        return True
    # 选项组标题
    if inner_clean in {"新先知诅咒", "新女巫巫术", "蜥蜴人先知诅咒", "狗头人陷阱"}:
        return True
    # 职业能力标签（如 军用武器擅长、炼金武器 等）不是顶层标题
    norm = _normalize_title(inner)
    if any(label in norm for label in CLASS_FEATURE_LABELS):
        return False
    # 带 (Ex)/(Su)/(Sp) 或中文括号（Ex）/（Su）/（Sp）的都是职业能力标签
    if re.search(r"[\(（][Ee][Xx][\)）]|[\(（][Ss][Uu][\)）]|[\(（][Ss][Pp][\)）]", inner):
        return False
    # 包含英文的顶层标题：炼金术士发现、变体英文名等
    if re.search(r"[A-Za-z]", inner):
        return True
    return False


def split_class_option_blocks(section_content):
    """把变体职业章节拆成独立选项块，并把职业能力描述合并到对应选项块中。"""
    title_re = re.compile(r"(\*\*.*?\*\*)", re.DOTALL)
    matches = list(title_re.finditer(section_content))
    main_indices = []
    for i, m in enumerate(matches):
        title = m.group(1)
        inner = title.strip("*")
        if is_section_header(title):
            continue
        if is_main_class_option(title, inner):
            main_indices.append(i)

    blocks = []
    for j, idx in enumerate(main_indices):
        start = matches[idx].start()
        end = matches[main_indices[j + 1]].start() if j + 1 < len(main_indices) else len(section_content)
        block_text = section_content[start:end].rstrip()
        if block_text:
            blocks.append(block_text)
    return blocks


def resolve_class_file(class_name):
    if not class_name:
        return None
    override = CLASS_TARGET_OVERRIDES.get(class_name)
    if override and override.exists():
        return override

    # 通过 TOC 路径查找职业变体页面
    for tp in TOC_INDEX:
        if f"→ {class_name}" not in tp:
            continue
        if "职业变体" in tp:
            path = resolve_target(tp)
            if path and path.exists():
                return path

    # 回退到该职业的根页面
    for tp in TOC_INDEX:
        if tp.endswith(f"→ {class_name}") and "职业" in tp:
            path = resolve_target(tp)
            if path and path.exists():
                return path

    return None


# ---------------------------------------------------------------------------
# 魔法物品：类型识别与目标文件
# ---------------------------------------------------------------------------

MAGIC_ITEM_TARGETS = {
    "奇物": TARGET_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / f"{BOOK_L2}_奇物.md",
    "魔法武器防具": TARGET_DIR / "装备_魔法物品" / "魔法物品" / "魔法武器防具" / f"{BOOK_L2}_魔法武器防具.md",
    "戒指_权杖_法杖": TARGET_DIR / "装备_魔法物品" / "魔法物品" / "戒指_权杖_法杖" / f"{BOOK_L2}_戒指_权杖_法杖.md",
}

EQUIPMENT_TARGET = TARGET_DIR / "装备_魔法物品" / "货品服务" / f"{BOOK_L2}_货品.md"


def classify_magic_item(block_text):
    """根据装备位置/制造条件等判断魔法物品子类型。"""
    if "锻造戒指" in block_text:
        return "戒指_权杖_法杖"

    slot_match = re.search(r"装备位置[：:]\s*\*?\*?([^\s\n\*]+)", block_text)
    slot = slot_match.group(1) if slot_match else ""
    if "戒指" in slot:
        return "戒指_权杖_法杖"

    # 制造条件行在原 MD 中常被加粗包裹，如 **制造条件：**制造魔法武器和护甲
    if any(x in block_text for x in ("制造魔法武器和防具", "制造魔法武器和护甲")):
        return "魔法武器防具"

    if any(x in slot for x in ("武器", "盾牌", "护甲")):
        return "魔法武器防具"

    return "奇物"


def is_alchemy_item(block_text):
    """判断是否为炼金/普通物品（非魔法物品）。"""
    if re.search(r"类型[：:]\s*炼金", block_text):
        return True
    if "手艺（炼金术）" in block_text or "工艺(炼金)" in block_text:
        return True
    if "制造DC" in block_text:
        return True
    return False


# ---------------------------------------------------------------------------
# 种族名提取
# ---------------------------------------------------------------------------

def extract_race_name(toc_path, text):
    parts = [p.strip() for p in toc_path.split("→")]
    if len(parts) >= 3 and parts[2] != BOOK_L2:
        return parts[2]
    lines = text.split("\n")
    for line in lines[:5]:
        line = line.strip()
        m = re.match(r"\*\*([^*]+)\*\*", line)
        if m:
            return m.group(1).strip()
    return "未知种族"


# ---------------------------------------------------------------------------
# 各类型处理函数
# ---------------------------------------------------------------------------

RACE_DIR = TARGET_DIR / "种族" / "怪物种族"


def resolve_race_file(race_name, suffix):
    d = RACE_DIR / race_name
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob(f"*{suffix}.md"):
        return f
    return d / f"{race_name}{suffix}.md"


def process_traits(race_name, section_content, l3_title, changes):
    target = resolve_race_file(race_name, "种族特性替换汇总")
    note = source_note(l3_title)
    marker = f"MC-{race_name}-traits"
    if already_contains(target, marker):
        return
    content_with_notes = insert_note_after_headings(
        section_content, note,
        r"(\*\*[^*\n]{2,20}[：:]\*\*)"
    )
    append_to_target(target, f"\n{content_with_notes}\n\n<!-- {marker} -->\n")
    changes.setdefault(str(target.relative_to(TARGET_DIR)), []).append("替换种族特性")


def process_fcb(race_name, section_content, l3_title, changes):
    target = resolve_race_file(race_name, "天赋职业奖励")
    note = source_note(l3_title)
    marker = f"MC-{race_name}-fcb"
    if already_contains(target, marker):
        return
    header = f"**{race_name}天赋职业奖励**（{BOOK_NAME}）\n\n{note}\n\n"
    append_to_target(target, header + section_content + f"\n\n<!-- {marker} -->\n")
    changes.setdefault(str(target.relative_to(TARGET_DIR)), []).append("天赋职业奖励")


def process_feats(section_content, l3_title, changes):
    target = TARGET_DIR / "专长" / f"{BOOK_L2}_专长.md"
    note = source_note(l3_title)
    marker = f"MC-feats-{l3_title}"
    if already_contains(target, marker):
        return
    for block in split_into_blocks(section_content):
        block_with_note = add_source_note_to_block(block, note)
        append_to_target(target, block_with_note)
    append_to_target(target, f"\n<!-- {marker} -->\n")
    changes.setdefault(str(target.relative_to(TARGET_DIR)), []).append("专长")


def process_spells(section_content, l3_title, changes):
    target = TARGET_DIR / "法术" / f"{BOOK_L2}_法术.md"
    note = source_note(l3_title)
    marker = f"MC-spells-{l3_title}"
    if already_contains(target, marker):
        return
    for block in split_into_blocks(section_content):
        block_with_note = add_source_note_to_block(block, note)
        append_to_target(target, block_with_note)
    append_to_target(target, f"\n<!-- {marker} -->\n")
    changes.setdefault(str(target.relative_to(TARGET_DIR)), []).append("法术")


def process_class_archetype(section_content, l3_title, changes):
    """处理变体职业章节。识别每个块的职业并追加到对应职业页面。"""
    note = source_note(l3_title)
    blocks_by_target = defaultdict(list)
    for block in split_class_option_blocks(section_content):
        class_name = detect_class_name(block)
        target = resolve_class_file(class_name) or UNIFIED_ARCHETYPES_TARGET
        blocks_by_target[(target, class_name)].append(block)
    for (target, class_name), blocks in blocks_by_target.items():
        marker = f"MC-archetypes-{l3_title}-{class_name or 'unified'}"
        if already_contains(target, marker):
            continue
        for block in blocks:
            block_with_note = add_source_note_to_block(block, note)
            append_to_target(target, block_with_note)
        append_to_target(target, f"\n<!-- {marker} -->\n")
        changes.setdefault(str(target.relative_to(TARGET_DIR)), []).append(
            class_name or "变体职业（未识别职业）"
        )


def process_equipment(section_content, l3_title, changes):
    target = EQUIPMENT_TARGET
    note = source_note(l3_title)
    marker = f"MC-equipment-{l3_title}"
    if already_contains(target, marker):
        return
    for block in split_into_blocks(section_content):
        block_with_note = add_source_note_to_block(block, note)
        append_to_target(target, block_with_note)
    append_to_target(target, f"\n<!-- {marker} -->\n")
    changes.setdefault(str(target.relative_to(TARGET_DIR)), []).append("装备")


def process_magic_items(section_content, l3_title, changes):
    note = source_note(l3_title)
    blocks_by_type = defaultdict(list)
    for block in split_into_blocks(section_content):
        item_type = classify_magic_item(block)
        blocks_by_type[item_type].append(block)
    for item_type, blocks in blocks_by_type.items():
        target = MAGIC_ITEM_TARGETS[item_type]
        marker = f"MC-magic-items-{l3_title}-{item_type}"
        if already_contains(target, marker):
            continue
        for block in blocks:
            block_with_note = add_source_note_to_block(block, note)
            append_to_target(target, block_with_note)
        append_to_target(target, f"\n<!-- {marker} -->\n")
        changes.setdefault(str(target.relative_to(TARGET_DIR)), []).append(item_type)


def process_unparsed_fallback(entry, changes):
    target = TARGET_DIR / "规则" / f"{BOOK_L2}_未识别内容.md"
    marker = f"MC-unparsed:{entry['md_name']}"
    if already_contains(target, marker):
        return
    text = read_source(entry["md_name"])
    l3_title = entry["toc_path"].split(" → ")[-1] if " → " in entry["toc_path"] else "其他"
    note = source_note(l3_title)
    append_to_target(target, f"\n{note}\n\n{text}\n\n<!-- {marker} -->\n")
    changes.append({
        "file": entry["md_name"],
        "target": str(target.relative_to(TARGET_DIR)),
    })


def preprocess_text(text):
    """把纯文本章节标记（如“引用”）转换为加粗章节标题，便于 split_sections 识别。"""
    # 将独立成行的“引用”转换为加粗标题
    text = re.sub(r"^引用\s*$", "**引用**", text, flags=re.MULTILINE)
    return text


def process_monster_chapter(entry, changes):
    text = preprocess_text(read_source(entry["md_name"]))
    race_name = extract_race_name(entry["toc_path"], text)
    l3_title = entry["toc_path"].split(" → ")[-1] if " → " in entry["toc_path"] else race_name
    sections = split_sections(text, race_name)
    file_changes = {}
    note = source_note(l3_title)
    for section_type, section_content in sections:
        if section_type == "引用":
            # 旁白/引用栏跳过，避免污染规则条目
            continue
        if section_type == "引言":
            # 若引言明确提到职业选项（如秘示域），尝试提取并路由
            if any(kw in section_content for kw in ["秘示域", "新先知诅咒", "新女巫巫术"]):
                blocks_by_target = defaultdict(list)
                for block in split_class_option_blocks(section_content):
                    class_name = detect_class_name(block)
                    if not class_name:
                        continue
                    target = resolve_class_file(class_name) or UNIFIED_ARCHETYPES_TARGET
                    blocks_by_target[(target, class_name)].append(block)
                for (target, class_name), blocks in blocks_by_target.items():
                    marker = f"MC-archetypes-{l3_title}-{class_name}"
                    if already_contains(target, marker):
                        continue
                    for block in blocks:
                        block_with_note = add_source_note_to_block(block, note)
                        append_to_target(target, block_with_note)
                    append_to_target(target, f"\n<!-- {marker} -->\n")
                    file_changes.setdefault(str(target.relative_to(TARGET_DIR)), []).append(class_name)
            continue
        elif section_type == "替换种族特性":
            process_traits(race_name, section_content, l3_title, file_changes)
        elif section_type == "天赋职业奖励":
            process_fcb(race_name, section_content, l3_title, file_changes)
        elif section_type == "专长":
            process_feats(section_content, l3_title, file_changes)
        elif section_type == "法术":
            process_spells(section_content, l3_title, file_changes)
        elif section_type == "变体职业":
            process_class_archetype(section_content, l3_title, file_changes)
        elif section_type == "装备":
            process_equipment(section_content, l3_title, file_changes)
        elif section_type == "魔法物品":
            process_magic_items(section_content, l3_title, file_changes)
        elif section_type in ("术士血脉", "模板"):
            target = resolve_race_file(race_name, "其他规则")
            marker = f"MC-{race_name}-{section_type}"
            if not already_contains(target, marker):
                for block in split_into_blocks(section_content):
                    block_with_note = add_source_note_to_block(block, note)
                    append_to_target(target, block_with_note)
                append_to_target(target, f"\n<!-- {marker} -->\n")
                file_changes.setdefault(str(target.relative_to(TARGET_DIR)), []).append(section_type)
    if file_changes:
        changes.append({
            "file": entry["md_name"],
            "race": race_name,
            "targets": file_changes,
        })


def process_other_items(entry, changes):
    text = read_source(entry["md_name"])
    routed = defaultdict(list)
    blocks_by_type = defaultdict(list)
    for block in split_into_blocks(text):
        if is_alchemy_item(block):
            item_type = "炼金/普通物品"
        else:
            item_type = classify_magic_item(block)
        blocks_by_type[item_type].append(block)
    for item_type, blocks in blocks_by_type.items():
        if item_type == "炼金/普通物品":
            target = EQUIPMENT_TARGET
        else:
            target = MAGIC_ITEM_TARGETS[item_type]
        marker = f"MC-other-items-{item_type}"
        if already_contains(target, marker):
            continue
        note = source_note("其他物品")
        for block in blocks:
            block_with_note = add_source_note_to_block(block, note)
            append_to_target(target, block_with_note)
        append_to_target(target, f"\n<!-- {marker} -->\n")
        routed[str(target.relative_to(TARGET_DIR))].append(item_type)
    changes.append({
        "file": entry["md_name"],
        "targets": dict(routed) if routed else {"其他物品": ["待分类"]},
    })


def process_intro(entry, changes):
    target = TARGET_DIR / "规则" / f"{BOOK_L2}_开篇.md"
    marker = f"MC-source:{entry['md_name']}"
    if already_contains(target, marker):
        return
    text = read_source(entry["md_name"])
    l3_title = entry["toc_path"].split(" → ")[-1] if " → " in entry["toc_path"] else "开篇"
    note = source_note(l3_title)
    append_to_target(target, f"\n{note}\n\n{text}\n\n<!-- {marker} -->\n")
    changes.append({
        "file": entry["md_name"],
        "target": str(target.relative_to(TARGET_DIR)),
    })


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    global TOC_INDEX
    mapping = load_mapping()
    TOC_INDEX = build_toc_index(mapping)
    entries = load_mc_entries(mapping)
    print(f"加载到 {len(entries)} 个 MC 条目")

    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)
    print(f"创建副本目录: {TARGET_DIR}")
    shutil.copytree(SOURCE_DIR, TARGET_DIR)

    changes = []
    skipped = []

    for entry in entries:
        tp = entry["toc_path"]
        if tp == f"未整理 → {BOOK_L2}" or "开篇" in tp:
            process_intro(entry, changes)
        elif "其他物品" in tp:
            process_other_items(entry, changes)
        elif " → " in tp and len(tp.split(" → ")) >= 3:
            before = len(changes)
            process_monster_chapter(entry, changes)
            if len(changes) == before:
                process_unparsed_fallback(entry, changes)
        else:
            skipped.append(entry["md_name"])

    report_lines = [
        f"# {BOOK_NAME} 整理报告",
        "",
        f"共处理 {len(entries)} 个文件，跳过 {len(skipped)} 个。",
        "",
        "## 变更明细",
        "",
    ]
    for change in changes:
        report_lines.append(f"- **{change.get('file', '?')}**")
        if "race" in change:
            report_lines.append(f"  - 种族: {change['race']}")
        if "target" in change:
            report_lines.append(f"  - 目标: {change['target']}")
        if "targets" in change:
            for target, items in change["targets"].items():
                report_lines.append(f"  - {target}: {', '.join(items)}")

    if skipped:
        report_lines.extend(["", "## 跳过文件", ""])
        for name in skipped:
            report_lines.append(f"- {name}")

    REPORT_FILE.write_text("\n".join(report_lines), encoding="utf-8")
    PLAN_FILE.write_text(json.dumps({
        "entries": entries,
        "changes": changes,
        "skipped": skipped,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"整理完成。跳过: {skipped}")
    print(f"报告: {REPORT_FILE}")
    print(f"清单: {PLAN_FILE}")


if __name__ == "__main__":
    main()
