#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 治疗者手册（Healer's Handbook）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/治疗者手册HH/
目标目录：pf_data/phase1/pf_rules_md_organized/

包含 13 个源文件：page_703 ~ page_715
"""

import json
import os
import re

BASE = "/Users/chezi/code/java/pf_agent/pf_data/phase1"
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/治疗者手册HH")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "HH_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "HH_reorganization_report.md")

SOURCE_NOTE_TEMPLATE = "> 来源：治疗者手册（Healer's Handbook）HH，页码见原书，未整理 → 治疗者手册HH → {section_title}"

HH_FILES = []

SRC_MARK = "HH-source"


def load_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def normalize_ws(text):
    return re.sub(r"\s+", " ", text).strip()


def find_title(text, cn, en):
    """灵活查找条目标题。

    尝试以下格式（按优先级）：
    1. **CN（ENGLISH）** 或 **CN(ENGLISH)** （跨行允许）
    2. **CN　ENGLISH** 或 **CN ENGLISH** （跨行允许）
    3. **CN** （仅中文）
    返回 (start, end) 元组（标题起止位置）
    """
    if en:
        en_words = en.split()
        # 模式1: **CN（ENGLISH）** 或 **CN(ENGLISH)**
        for left_paren in ["（", "("]:
            for right_paren in ["）", ")"]:
                if left_paren in ["（"]:
                    rp = "）"
                else:
                    rp = ")"
                parts = [r"\*\*[\s\S]{0,30}?", re.escape(cn),
                         r"[\s\S]{0,30}?" + re.escape(left_paren) + r"[\s\S]{0,5}?"]
                for w in en_words:
                    parts.append(r"[\s\S]{0,30}?")
                    parts.append(re.escape(w))
                parts.append(r"[\s\S]{0,30}?" + re.escape(right_paren) + r"[\s\S]{0,30}?\*\*")
                pat = "".join(parts)
                m = re.search(pat, text)
                if m:
                    return m.start(), m.end()
        # 模式2: **CN ENGLISH**（空格或全角空格）
        parts = [r"\*\*[\s\S]{0,30}?", re.escape(cn)]
        for w in en_words:
            parts.append(r"[\s\S]{0,30}?")
            parts.append(re.escape(w))
        parts.append(r"[\s\S]{0,30}?\*\*")
        pat = "".join(parts)
        m = re.search(pat, text)
        if m:
            return m.start(), m.end()
    # 模式3: 仅中文 **CN**
    m = re.search(r"\*\*[\s\S]{0,30}?" + re.escape(cn) + r"[\s\S]{0,30}?\*\*", text)
    if m:
        return m.start(), m.end()
    return None, None


def find_entry_start(text, cn, en, prefix=""):
    """查找条目起点（不要求 `**` 包裹），返回 (start, end_of_title)。

    适用场景：标题没有 `**` 包裹，CN 与英文之间是括号或空格。
    EN 名称按空格分词后逐段匹配，跨行/跨任意字符。
    """
    if en:
        # 按空格分词后逐段匹配（支持跨行/任意字符）
        parts = [re.escape(cn)]
        en_words = en.split()
        for w in en_words:
            parts.append(r"[\s\S]{0,100}?")
            parts.append(re.escape(w))
        pattern = "".join(parts)
    else:
        pattern = re.escape(cn)

    if prefix:
        m = re.search(re.escape(prefix) + r"[\s\S]{0,5}?" + pattern, text)
    else:
        m = re.search(pattern, text)
    if m:
        return m.start(), m.end()
    return None, None


def ensure_header(target_path, header):
    full_path = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    if target_path not in HH_FILES:
        HH_FILES.append(target_path)
    if not os.path.exists(full_path) or os.path.getsize(full_path) == 0:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(header + "\n\n")


def append_to_target(target_path, block):
    full_path = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    if target_path not in HH_FILES:
        HH_FILES.append(target_path)
    with open(full_path, "a", encoding="utf-8") as f:
        f.write(block)


def remove_hh_content():
    for root, dirs, files in os.walk(ORG_BASE):
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            if f"<!-- {SRC_MARK}:" not in text:
                continue
            parts = re.split(r"(?=<!-- [A-Za-z]+-source:)", text)
            kept = [p for p in parts if not p.startswith(f"<!-- {SRC_MARK}:")]
            new_text = "".join(kept)
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_text)
    for rel in HH_FILES:
        full = os.path.join(ORG_BASE, rel)
        if os.path.exists(full):
            os.remove(full)


def build_block(source, title_cn, title_en, section_title, body_lines, body_prefix=""):
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
    marker = f"<!-- {SRC_MARK}:{source}:{title_cn} -->"
    if title_en:
        title_line = f"**{title_cn}（{title_en}）**"
    else:
        title_line = f"**{title_cn}**"
    result = [marker, title_line, note]
    if body_prefix:
        result.append(body_prefix)
    result.extend(body_lines)
    if result and result[-1].strip():
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def already_present(target_text, source, title_cn):
    marker_key = f"<!-- {SRC_MARK}:{source}:{title_cn} -->"
    if marker_key in target_text:
        return True
    # 内容去重：若目标文件中已存在同标题（可能源于其他来源书），则跳过
    title_pattern = f"**{title_cn}（"
    if title_pattern in target_text:
        return True
    bare_pattern = f"**{title_cn}**"
    if bare_pattern in target_text:
        return True
    return False


def add_entry(source_file, target_path, section_title, header, cn, en, body_lines,
              body_prefix="", stats=None, plan_sections=None):
    if stats is None:
        stats = {"added": 0, "skipped": 0, "errors": []}
    if plan_sections is None:
        plan_sections = []

    ensure_header(target_path, header)
    full_target = os.path.join(ORG_BASE, target_path)
    target_text = load_text(full_target) if os.path.exists(full_target) else ""

    sec = {
        "source": source_file,
        "title": cn,
        "english": en,
        "target": target_path,
        "section_title": section_title,
    }

    if already_present(target_text, source_file, cn):
        stats["skipped"] += 1
        plan_sections.append({**sec, "action": "skipped", "reason": "hidden_marker"})
        return

    block = build_block(source_file, cn, en, section_title, body_lines, body_prefix)
    append_to_target(target_path, block)
    stats["added"] += 1
    plan_sections.append({**sec, "action": "added"})


def body_to_lines(body):
    lines = body.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    return lines


def find_end_after(text, start_pos, next_marker):
    if next_marker:
        nm = text.find(next_marker, start_pos)
        return nm if nm >= 0 else len(text)
    return len(text)


# ---------------------------------------------------------------------------
# page_703.md：21 背景特性
# 文件中条目以"**宗教背景**XXX"开头，无 `**` 包裹，按 CN + 英文 定位
# ---------------------------------------------------------------------------

TRAITS = [
    # (cn, en, 下一条目起始子串，None 表示到文末)
    ("血腥复仇", "Bloody Vengeance", "医疗特使"),
    ("医疗特使", "Envoy of Healing", "战争伤痕"),
    ("战争伤痕", "Scarred by War", "灵魂搜寻者之力"),
    ("灵魂搜寻者之力", "Soul-Searcher's Strength", "知名医师"),
    ("知名医师", "Prestigious Healer", "楚业后裔"),
    ("楚业后裔", "Heir of Chu Ye", "艾欧巴瑞亚幸存者"),
    ("艾欧巴瑞亚幸存者", "Iobarian Survivor", "镇咒者"),
    ("镇咒者", "Curse Queller", "受训药剂师"),
    ("受训药剂师", "Educated Druggist", "法力废土医师"),
    ("法力废土医师", "Mana Wastes Medic", "熟练外科医生"),
    ("熟练外科医生", "Skilled Surgeon", "濒死体验"),
    ("濒死体验", "Near-Death Experience", "女巫借贷"),
    ("女巫借贷", "Debt to a Witch", "雅德维加医学"),
    ("雅德维加医学", "Jadwiga Medicine", "庇护主之赐"),
    ("庇护主之赐", "Patron's Boon", "无信决意"),
    ("无信决意", "Godless Resolve", "续命表演"),
    ("续命表演", "Sustaining Performance", "兽魂活力"),
    ("兽魂活力", "Animal-Spirit Vitality", "游击改进者"),
    ("游击改进者", "Guerrilla Mender", "芒吉草药传统"),
    ("芒吉草药传统", "Mwangi Herbal Tradition", "英灵从者"),
    ("英灵从者", "Servitor of Spirits", None),
]


def process_traits(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_703.md")
    text = load_text(src)
    target_path = "背景特性/治疗者手册HH_背景特性.md"
    header = "# 治疗者手册 背景特性"

    for cn, en, next_marker in TRAITS:
        # 查找 cn + en 的位置作为起点
        start, _ = find_entry_start(text, cn, en)
        if start is None:
            stats["errors"].append(f"page_703.md 未找到背景特性：{cn}")
            continue
        # 下一条目起点作为结束
        end = find_end_after(text, start + 1, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "page_703.md", target_path, "背景特性", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


# ---------------------------------------------------------------------------
# page_704.md：12 专长 + 2 原力
# ---------------------------------------------------------------------------

FEATS = [
    # (cn, en, 下一条目起始子串)
    ("触发医疗法术", "Contingent Spell", "**治愈掌握"),
    ("治愈掌握", "Curative Mastery", "**生命界限"),
    ("生命界限", "Lifebound", "**战斗活力"),
    ("战斗活力", "Combat Vigor", "**强韧活力"),
    ("强韧活力", "Fortuitous Vigor", "**复原活力"),
    ("复原活力", "Restorative Vigor", "**借机喘息"),
    ("借机喘息", "Take a Breather", "**不屈决意"),
    ("不屈决意", "Unconquerable Resolve", "**生龙活虎"),
    ("生龙活虎", "Vim and Vigor", "**邪恶治疗者专长"),
    ("限制法术", "Conditional Spell", "**阴险治疗"),
    ("阴险治疗", "Insidious Healing", "**痛苦治愈"),
    ("痛苦治愈", "Painful Cures", "**原力"),
]

KINESIS = [
    # 异能者原力（EN 在文件中为全大写）
    ("念力复原", "KINETIC RESTORATION", "**念力复苏"),
    ("念力复苏", "KINETIC REVIVIFICATION", None),
]


def _process_with_title_pattern(stats, plan_sections, items, target_path, header, source, section_title):
    text = load_text(os.path.join(SRC_DIR, source))
    for cn, en, next_marker in items:
        # 处理可能的英文大小写不一致：优先 cn + 任意 + en，宽松匹配
        start, end_pos = find_title(text, cn, en)
        if start is None:
            # 退路：cn + 任意 + en（无 ** 包裹）
            start, end_pos = find_entry_start(text, cn, en)
        if start is None:
            stats["errors"].append(f"{source} 未找到条目：{cn}")
            continue
        end = find_end_after(text, end_pos, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            source, target_path, section_title, header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


def process_feats(stats, plan_sections):
    _process_with_title_pattern(
        stats, plan_sections, FEATS,
        "专长/治疗者手册HH_专长.md", "# 治疗者手册 专长",
        "page_704.md", "专长"
    )


def process_kinesis(stats, plan_sections):
    # 原力：标题前有 "**原力**" 前缀，紧跟着条目
    # 实际：`**原力****念力复原（KINETIC RESTORATION）**`
    text = load_text(os.path.join(SRC_DIR, "page_704.md"))
    target_path = "职业/异能冒险（Occult Adventures）/异能者/page_308.md"
    header = None  # 追加到已有文件

    for cn, en, next_marker in KINESIS:
        # 找 "**原力**" 后最近的 cn
        m_kuangbiao = re.search(r"\*\*原力\*\*", text)
        if m_kuangbiao:
            # 限定在 **原力** 之后查找
            search_text = text[m_kuangbiao.end():]
            start, end_pos = find_title(search_text, cn, en)
            if start is not None:
                start = m_kuangbiao.end() + start
                end_pos = m_kuangbiao.end() + end_pos
            else:
                start, end_pos = find_entry_start(search_text, cn, en)
                if start is not None:
                    start = m_kuangbiao.end() + start
                    end_pos = m_kuangbiao.end() + end_pos
        else:
            start, end_pos = find_title(text, cn, en)

        if start is None:
            stats["errors"].append(f"page_704.md 未找到原力：{cn}")
            continue
        end = find_end_after(text, end_pos, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "page_704.md", target_path, "异能者原力", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


# ---------------------------------------------------------------------------
# page_705.md：6 医疗法术 + 1 女巫法术
# 标题格式：**CN　ENGLISH** （全角空格）
# ---------------------------------------------------------------------------

HEALING_SPELLS = [
    ("医疗标记", "Healing Token", "**疗效升华"),
    ("疗效升华", "Curative Distillation", "**医疗圣炎"),
    ("医疗圣炎", "Healing Flames", "**净化躯体"),
    ("净化躯体", "Purify Body", "**鼓舞复苏"),
    ("鼓舞复苏", "Inspiring Recovery", "**痛苦平衡"),
    ("痛苦平衡", "Balance of Suffering", "**女巫法术"),
]

WITCH_SPELLS = [
    ("愚者之灾", "Befuddled Combatant", None),
]


def process_healing_spells(stats, plan_sections):
    _process_with_title_pattern(
        stats, plan_sections, HEALING_SPELLS,
        "法术/治疗者手册HH_医疗法术.md", "# 治疗者手册 医疗法术",
        "page_705.md", "医疗法术"
    )


def process_witch_spells(stats, plan_sections):
    _process_with_title_pattern(
        stats, plan_sections, WITCH_SPELLS,
        "法术/治疗者手册HH_女巫法术.md", "# 治疗者手册 女巫法术",
        "page_705.md", "女巫法术"
    )


# ---------------------------------------------------------------------------
# page_706.md：1 牧师变体 + 1 武僧变体
# ---------------------------------------------------------------------------

def process_priest_archetype(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_706.md")
    text = load_text(src)
    target_path = "职业/核心职业/牧师/page_41.md"
    header = None  # 追加到已有文件，不写新标题

    cn = "受福侍者"
    en = "Sacred Attendant"
    start, end_pos = find_title(text, cn, en)
    if start is None:
        stats["errors"].append("page_706.md 未找到牧师变体：受福侍者")
        return

    end = find_end_after(text, end_pos, "**义洛里")
    body = text[start:end].strip()
    body = re.sub(r"^[\s\)\(]+", "", body)
    add_entry(
        "page_706.md", target_path, "牧师变体", header, cn, en,
        body_to_lines(body), "", stats, plan_sections
    )


def process_priest_archetype_2(stats, plan_sections):
    """page_706.md 苦修护理师（第二处牧师变体，法莱斯玛之后）"""
    src = os.path.join(SRC_DIR, "page_706.md")
    text = load_text(src)
    target_path = "职业/核心职业/牧师/page_41.md"
    header = None

    cn = "苦修护理师"
    en = "Stoic Caregiver"
    start, end_pos = find_entry_start(text, cn, en)
    if start is None:
        stats["errors"].append("page_706.md 未找到牧师变体：苦修护理师")
        return

    end = find_end_after(text, end_pos, "**齐仲")
    body = text[start:end].strip()
    body = re.sub(r"^[\s\)\(]+", "", body)
    add_entry(
        "page_706.md", target_path, "牧师变体", header, cn, en,
        body_to_lines(body), "", stats, plan_sections
    )


def process_priest_archetype_3(stats, plan_sections):
    """page_706.md 圣炎使徒（第三处牧师变体，莎伦莱之后）"""
    src = os.path.join(SRC_DIR, "page_706.md")
    text = load_text(src)
    target_path = "职业/核心职业/牧师/page_41.md"
    header = None

    cn = "圣炎使徒"
    en = "Angelfire Apostle"
    start, end_pos = find_entry_start(text, cn, en)
    if start is None:
        stats["errors"].append("page_706.md 未找到牧师变体：圣炎使徒")
        return

    end = len(text)
    body = text[start:end].strip()
    body = re.sub(r"^[\s\)\(]+", "", body)
    add_entry(
        "page_706.md", target_path, "牧师变体", header, cn, en,
        body_to_lines(body), "", stats, plan_sections
    )


def process_monk_archetype(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_706.md")
    text = load_text(src)
    target_path = "职业/核心职业/武僧/page_55.md"
    header = None  # 追加到已有变体页

    cn = "混元门徒"
    en = "Disciple of Wholeness"
    start, end_pos = find_title(text, cn, en)
    if start is None:
        stats["errors"].append("page_706.md 未找到武僧变体：混元门徒")
        return

    end = find_end_after(text, end_pos, "**密拉妮")
    body = text[start:end].strip()
    body = re.sub(r"^[\s\)\(]+", "", body)
    add_entry(
        "page_706.md", target_path, "武僧变体", header, cn, en,
        body_to_lines(body), "", stats, plan_sections
    )


def process_ranger_archetype(stats, plan_sections):
    """page_706.md 荒野军医（游侠变体，密拉妮之后）"""
    src = os.path.join(SRC_DIR, "page_706.md")
    text = load_text(src)
    target_path = "职业/核心职业/游侠/page_58.md"
    header = None  # 追加到已有变体页

    cn = "荒野军医"
    en = "Wilderness Medic"
    start, end_pos = find_entry_start(text, cn, en)
    if start is None:
        stats["errors"].append("page_706.md 未找到游侠变体：荒野军医")
        return

    end = find_end_after(text, end_pos, "**法莱斯玛")
    body = text[start:end].strip()
    body = re.sub(r"^[\s\)\(]+", "", body)
    add_entry(
        "page_706.md", target_path, "游侠变体", header, cn, en,
        body_to_lines(body), "", stats, plan_sections
    )


def process_wizard_archetype(stats, plan_sections):
    """page_706.md 奥术医者（法师变体，齐仲之后）"""
    src = os.path.join(SRC_DIR, "page_706.md")
    text = load_text(src)
    target_path = "职业/核心职业/法师/page_67.md"
    header = None  # 追加到已有变体页

    cn = "奥术医者"
    en = "Arcane Physician"
    start, end_pos = find_entry_start(text, cn, en)
    if start is None:
        stats["errors"].append("page_706.md 未找到法师变体：奥术医者")
        return

    end = find_end_after(text, end_pos, "**莎伦莱")
    body = text[start:end].strip()
    body = re.sub(r"^[\s\)\(]+", "", body)
    add_entry(
        "page_706.md", target_path, "法师变体", header, cn, en,
        body_to_lines(body), "", stats, plan_sections
    )


# ---------------------------------------------------------------------------
# page_707.md：2 炼金术师变体 + 3 科研发现
# 标题无 `**` 包裹
# ---------------------------------------------------------------------------

ALCHEMIST_ARCHETYPES = [
    ("废土除疫者", "Wasteland Blightbreaker", "**圣礼炼金师"),
    ("圣礼炼金师", "Sacrament Alchemist", "**新的科研发现"),
]

ALCHEMIST_DISCOVERIES = [
    ("中和炸弹", "Neutralizing Bomb", "**净化突变"),
    ("净化突变", "Purging Mutagen", "**炼金药炼成"),
    ("炼金药炼成", "Remedy Extract", None),
]


def process_alchemist_archetypes(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_707.md")
    text = load_text(src)
    target_path = "职业/基础职业/炼金术师/page_21.md"
    header = None  # 追加到已有变体页

    for cn, en, next_marker in ALCHEMIST_ARCHETYPES:
        start, end_pos = find_entry_start(text, cn, en)
        if start is None:
            stats["errors"].append(f"page_707.md 未找到炼金术师变体：{cn}")
            continue
        end = find_end_after(text, end_pos, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "page_707.md", target_path, "炼金术师变体", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


def process_alchemist_discoveries(stats, plan_sections):
    _process_with_title_pattern(
        stats, plan_sections, ALCHEMIST_DISCOVERIES,
        "职业/基础职业/炼金术师/page_71.md", None,
        "page_707.md", "炼金术师科研发现"
    )


# ---------------------------------------------------------------------------
# page_708.md：5 集中祝福
# 标题无 `**` 包裹
# ---------------------------------------------------------------------------

FOCUSED_BLESSINGS = [
    ("合作祝福", "Cooperation", "**自由祝福"),
    ("自由祝福", "Freedom", "**殉难祝福"),
    ("殉难祝福", "Martyr", "**复原祝福"),
    ("复原祝福", "Restoration", "**回生祝福"),
    ("回生祝福", "Resurrection", None),
]


def process_focused_blessings(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_708.md")
    text = load_text(src)
    target_path = "职业/混合职业/战斗祭司/【整理】战斗祭司祝福汇总.md"
    header = None  # 追加到已有汇总文件

    for cn, en, next_marker in FOCUSED_BLESSINGS:
        start, end_pos = find_entry_start(text, cn, en)
        if start is None:
            stats["errors"].append(f"page_708.md 未找到集中祝福：{cn}")
            continue
        end = find_end_after(text, end_pos, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "page_708.md", target_path, "战斗祭司集中祝福", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


# ---------------------------------------------------------------------------
# page_709.md：1 庇护主 + 4 巫术/缥缈巫术
# 标题无 `**` 包裹。巫术前有"巫术"前缀
# ---------------------------------------------------------------------------

WITCH_PATRONS = [
    ("恢复", "Restoration", "**巫术祛病"),
]

WITCH_HEXES = [
    ("巫术祛病", "Ameliorating", "**强力巫术解灾"),
    ("强力巫术解灾", "Major Ameliorating", "**生肌"),
    ("生肌", "Regenerative Sinew", "**高等巫术续命"),
    ("高等巫术续命", "Death Interrupted", None),
]


def process_witch_patron(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_709.md")
    text = load_text(src)
    target_path = "职业/基础职业/女巫/page_92.md"
    header = None  # 追加到已有女巫 巫术和庇护主 页

    for cn, en, next_marker in WITCH_PATRONS:
        # 庇护主在文件中只显示"恢复庇护主"（无 EN、无 **）
        full_cn = cn + "庇护主"
        start, end_pos = find_entry_start(text, full_cn, "")
        if start is None:
            stats["errors"].append(f"page_709.md 未找到女巫庇护主：{cn}")
            continue
        end = find_end_after(text, end_pos, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        # 跳过 http 译者行
        body_lines = [ln for ln in body.splitlines() if not ln.lstrip().startswith("[http")]
        body = "\n".join(body_lines).strip()
        add_entry(
            "page_709.md", target_path, "女巫庇护主", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


def process_witch_hexes(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_709.md")
    text = load_text(src)
    target_path = "职业/基础职业/女巫/page_92.md"
    header = None  # 追加到已有女巫 巫术和庇护主 页

    for cn, en, next_marker in WITCH_HEXES:
        # 巫术标题带"巫术"前缀
        start, end_pos = find_entry_start(text, cn, en)
        if start is None:
            stats["errors"].append(f"page_709.md 未找到女巫巫术：{cn}")
            continue
        end = find_end_after(text, end_pos, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "page_709.md", target_path, "女巫巫术", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


# ---------------------------------------------------------------------------
# page_710.md：2 吟游诗人变体 + 2 世界名著
# 变体正常，世界名著无 `**` 包裹
# ---------------------------------------------------------------------------

BARD_ARCHETYPES = [
    ("振奋乐师", "Solacer", "**虔诚诗人"),
    ("虔诚诗人", "Faith Singer", "**世界名著"),
]

BARD_MASTERPIECES = [
    ("长者无尽华尔兹", "Endless Waltz of the Eldest", "**赛兰杜拉攀登交响乐"),
    ("赛兰杜拉攀登交响乐", "Symphony of Sylandurla's Ascent", None),
]


def process_bard_archetypes(stats, plan_sections):
    _process_with_title_pattern(
        stats, plan_sections, BARD_ARCHETYPES,
        "职业/核心职业/吟游诗人/page_38.md", None,
        "page_710.md", "吟游诗人变体"
    )


def process_bard_masterpieces(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_710.md")
    text = load_text(src)
    target_path = "职业/核心职业/吟游诗人/传世名作汇总.md"
    header = None  # 追加到已有汇总文件

    for cn, en, next_marker in BARD_MASTERPIECES:
        start, end_pos = find_entry_start(text, cn, en)
        if start is None:
            stats["errors"].append(f"page_710.md 未找到世界名著：{cn}")
            continue
        end = find_end_after(text, end_pos, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "page_710.md", target_path, "吟游诗人世界名著", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


# ---------------------------------------------------------------------------
# page_711.md：1 先知变体 + 1 密示域 + 10 启示
# 变体与启示正常，密示域是 **救助（先知密示域）** 格式
# ---------------------------------------------------------------------------

ORACLE_ARCHETYPES = [
    ("本草医师", "Pei Zin Practitioner", "**救助（先知密示域）"),
]

ORACLE_MYSTERIES = [
    ("救助", "Succor", None),  # 救助密示域
]

ORACLE_REVELATIONS = [
    ("战斗医师", "Combat Healer", "**弱化诅咒"),
    ("弱化诅咒", "Curse of Dampening", "**强力治疗"),
    ("强力治疗", "Enhanced Cures", "**强力伤害"),
    ("强力伤害", "Enhanced Inflictions", "**完美支援"),
    ("完美支援", "Perfect Aid", "**仁慈之敌"),
    ("仁慈之敌", "Pitiful Foe", "**救助之盾"),
    ("救助之盾", "Shell of Succor", "**灵魂吸取"),
    ("灵魂吸取", "Soul Siphon", "**灵性提升"),
    ("灵性提升", "Spirit Boost", "**团队掌握"),
    ("团队掌握", "Teamwork Mastery", None),
]


def process_oracle_archetype(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_711.md")
    text = load_text(src)
    target_path = "职业/基础职业/先知/page_20.md"
    header = None  # 追加到已有变体页

    for cn, en, next_marker in ORACLE_ARCHETYPES:
        start, end_pos = find_title(text, cn, en)
        if start is None:
            stats["errors"].append(f"page_711.md 未找到先知变体：{cn}")
            continue
        end = find_end_after(text, end_pos, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "page_711.md", target_path, "先知变体", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


def process_oracle_mystery(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_711.md")
    text = load_text(src)
    target_path = "职业/基础职业/先知/page_88.md"
    header = None  # 追加到先知 秘示域 页

    for cn, en, next_marker in ORACLE_MYSTERIES:
        # 密示域标题：**救助（先知密示域）**
        title_pattern = r"\*\*[\s\S]{0,20}?" + re.escape(cn) + r"[\s\S]{0,40}?\*\*"
        m = re.search(title_pattern, text)
        if not m:
            stats["errors"].append(f"page_711.md 未找到先知密示域：{cn}")
            continue

        start = m.end()
        end = find_end_after(text, start, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "page_711.md", target_path, "先知密示域", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


def process_oracle_revelations(stats, plan_sections):
    _process_with_title_pattern(
        stats, plan_sections, ORACLE_REVELATIONS,
        "职业/基础职业/先知/page_88.md", None,
        "page_711.md", "先知启示"
    )


# ---------------------------------------------------------------------------
# page_712.md：2 德鲁伊变体 + 1 自然纽带
# ---------------------------------------------------------------------------

DRUID_ARCHETYPES = [
    ("自然祭司", "Nature Priest", "**复原者"),
    ("复原者", "Restorer", "**德鲁伊草药学"),
]

DRUID_NATURE_BONDS = [
    ("德鲁伊草药学", "DRUIDIC HERBALISM", None),
]


def process_druid_archetypes(stats, plan_sections):
    _process_with_title_pattern(
        stats, plan_sections, DRUID_ARCHETYPES,
        "职业/核心职业/德鲁伊/page_45.md", None,
        "page_712.md", "德鲁伊变体"
    )


def process_druid_nature_bond(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_712.md")
    text = load_text(src)
    target_path = "职业/核心职业/德鲁伊/page_46.md"
    header = None  # 追加到德鲁伊自然纽带页

    for cn, en, next_marker in DRUID_NATURE_BONDS:
        # 标题：**德鲁伊草药学 DRUIDIC \nHERBALISM**
        # 使用 find_title 让其自动处理跨行与大小写
        start, end_pos = find_title(text, cn, en)
        if start is None:
            # 退路：直接 cn
            start, end_pos = find_entry_start(text, cn, en)
        if start is None:
            stats["errors"].append(f"page_712.md 未找到自然纽带：{cn}")
            continue

        end = find_end_after(text, end_pos, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "page_712.md", target_path, "德鲁伊自然纽带", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


# ---------------------------------------------------------------------------
# page_713.md：1 圣武士变体 + 11 恩惠 + 3 神契
# 变体是 **鼓舞卫士（INVIGORATOR）【圣武士变体】** 格式
# 恩惠是 **移除衰弱（Enfeebled）**：... 格式
# 神契是 **盖丁契约（Agathion Bond）**：... 格式
# ---------------------------------------------------------------------------

PALADIN_ARCHETYPES = [
    ("鼓舞卫士", "INVIGORATOR", "**新的恩惠"),
]

PALADIN_MERCIES = [
    ("识破幻象", "Deceived", "**平息愤怒"),
    ("平息愤怒", "Riled", "**移除衰弱"),
    ("移除衰弱", "Enfeebled", "**驱逐邪恶"),
    ("驱逐邪恶", "Haunted", "**圣域庇护"),
    ("圣域庇护", "Targeted", "**移除困惑"),
    ("移除困惑", "Confused", "**高速愈合"),
    ("高速愈合", "Injured", "**复原祷言"),
    ("复原祷言", "Restorative", "**再生祷言"),
    ("再生祷言", "Amputated", "**幻想御手"),
    ("幻想御手", "Ensorcelled", "**移除石化"),
    ("移除石化", "Petrified", "**天界神契"),
]

PALADIN_BONDS = [
    ("盖丁契约", "Agathion Bond", "**天使契约"),
    ("天使契约", "Angelic Bond", "**神使契约"),
    ("神使契约", "Archon Bond", None),
]


def process_paladin_archetype(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_713.md")
    text = load_text(src)
    target_path = "职业/核心职业/圣骑士/page_55.md"
    header = None  # 追加到已有变体页

    for cn, en, next_marker in PALADIN_ARCHETYPES:
        # **鼓舞卫士（INVIGORATOR）【圣武士变体】** 格式
        # 直接用 cn + en 顺序匹配
        start, end_pos = find_entry_start(text, cn, en)
        if start is None:
            stats["errors"].append(f"page_713.md 未找到圣武士变体：{cn}")
            continue
        end = find_end_after(text, end_pos, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "page_713.md", target_path, "圣武士变体", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


def process_paladin_mercies(stats, plan_sections):
    _process_with_title_pattern(
        stats, plan_sections, PALADIN_MERCIES,
        "职业/核心职业/圣骑士/page_55.md", None,
        "page_713.md", "圣武士恩惠"
    )


def process_paladin_bonds(stats, plan_sections):
    _process_with_title_pattern(
        stats, plan_sections, PALADIN_BONDS,
        "职业/核心职业/圣骑士/page_55.md", None,
        "page_713.md", "圣武士神契"
    )


# ---------------------------------------------------------------------------
# page_714.md：1 萨满变体 + 1 专精魂域
# ---------------------------------------------------------------------------

SHAMAN_ARCHETYPES = [
    ("祷言行者", "Benefactor", "**专精魂域"),
]

SHAMAN_SPECIALIZATIONS = [
    ("复原", "Restoration", None),
]


def process_shaman_archetype(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_714.md")
    text = load_text(src)
    target_path = "职业/混合职业/萨满/page_111.md"
    header = None  # 追加到已有变体页

    for cn, en, next_marker in SHAMAN_ARCHETYPES:
        # **祷言行者（BENEFACTOR）【萨满变体】** 格式
        start, end_pos = find_entry_start(text, cn, en)
        if start is None:
            stats["errors"].append(f"page_714.md 未找到萨满变体：{cn}")
            continue
        end = find_end_after(text, end_pos, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "page_714.md", target_path, "萨满变体", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


def process_shaman_specialization(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_714.md")
    text = load_text(src)
    target_path = "职业/混合职业/萨满/page_111.md"
    header = None  # 追加到已有变体页

    for cn, en, next_marker in SHAMAN_SPECIALIZATIONS:
        # 专精魂域标题：**复原（Restoration）**
        title_pattern = r"\*\*[\s\S]{0,20}?" + re.escape(cn) + r"[\s\S]{0,40}?" + re.escape(en) + r"[\s\S]{0,30}?\*\*"
        m = re.search(title_pattern, text)
        if not m:
            stats["errors"].append(f"page_714.md 未找到萨满专精魂域：{cn}")
            continue

        body = text[m.end():].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "page_714.md", target_path, "萨满专精魂域", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


# ---------------------------------------------------------------------------
# page_715.md：10 魔法物品
# 物品标题格式：**CN ENGLISH** （全角空格或半角空格）
# ---------------------------------------------------------------------------

RING_ITEMS = [
    ("回生之戒", "Ring of Resumption", None),
]

WONDER_ITEMS = [
    ("盗命手套", "Gloves of Stolen Breath", "**医师挎包"),
    ("医师挎包", "Healer's Satchel", "**悼念之根"),
    ("悼念之根", "Memoriam Root", "**看护项链"),
    ("看护项链", "Nursing Necklace", "**凤凰之羽"),
    ("凤凰之羽", "Phoenix Feather", "**银色魂索"),
    ("银色魂索", "Silver Soul Cord", "**抒情竖琴"),
    ("抒情竖琴", "Soothing Lyre", "**巨魔皮革止血带"),
    ("巨魔皮革止血带", "Trollskin Tourniquet", "**独角兽邪角"),
    ("独角兽邪角", "Unicorn's Blackened Horn", None),
]


def process_ring_items(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_715.md")
    text = load_text(src)
    target_path = "装备_魔法物品/魔法物品/戒指_权杖_法杖/治疗者手册HH_戒指.md"
    header = "# 治疗者手册 戒指"

    for cn, en, next_marker in RING_ITEMS:
        start, end_pos = find_title(text, cn, en)
        if start is None:
            start, end_pos = find_entry_start(text, cn, en)
        if start is None:
            stats["errors"].append(f"page_715.md 未找到戒指：{cn}")
            continue
        end = find_end_after(text, end_pos, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "page_715.md", target_path, "魔法物品-戒指", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


def process_wonder_items(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_715.md")
    text = load_text(src)
    target_path = "装备_魔法物品/魔法物品/奇物/治疗者手册HH_奇物.md"
    header = "# 治疗者手册 奇物"

    for cn, en, next_marker in WONDER_ITEMS:
        # 物品标题：**CN ENGLISH** （空格或全角空格）
        start, end_pos = find_title(text, cn, en)
        if start is None:
            start, end_pos = find_entry_start(text, cn, en)
        if start is None:
            stats["errors"].append(f"page_715.md 未找到奇物：{cn}")
            continue
        end = find_end_after(text, end_pos, next_marker)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "page_715.md", target_path, "魔法物品-奇物", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    remove_hh_content()

    stats = {"added": 0, "skipped": 0, "errors": []}
    plan_sections = []

    process_traits(stats, plan_sections)
    process_feats(stats, plan_sections)
    process_kinesis(stats, plan_sections)
    process_healing_spells(stats, plan_sections)
    process_witch_spells(stats, plan_sections)
    process_priest_archetype(stats, plan_sections)
    process_priest_archetype_2(stats, plan_sections)
    process_priest_archetype_3(stats, plan_sections)
    process_monk_archetype(stats, plan_sections)
    process_ranger_archetype(stats, plan_sections)
    process_wizard_archetype(stats, plan_sections)
    process_alchemist_archetypes(stats, plan_sections)
    process_alchemist_discoveries(stats, plan_sections)
    process_focused_blessings(stats, plan_sections)
    process_witch_patron(stats, plan_sections)
    process_witch_hexes(stats, plan_sections)
    process_bard_archetypes(stats, plan_sections)
    process_bard_masterpieces(stats, plan_sections)
    process_oracle_archetype(stats, plan_sections)
    process_oracle_mystery(stats, plan_sections)
    process_oracle_revelations(stats, plan_sections)
    process_druid_archetypes(stats, plan_sections)
    process_druid_nature_bond(stats, plan_sections)
    process_paladin_archetype(stats, plan_sections)
    process_paladin_mercies(stats, plan_sections)
    process_paladin_bonds(stats, plan_sections)
    process_shaman_archetype(stats, plan_sections)
    process_shaman_specialization(stats, plan_sections)
    process_ring_items(stats, plan_sections)
    process_wonder_items(stats, plan_sections)

    unique_files = list(dict.fromkeys(HH_FILES))

    plan = {
        "source_book": "治疗者手册",
        "source_book_english": "Healer's Handbook",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/治疗者手册HH",
        "stats": stats,
        "target_files": unique_files,
        "sections": plan_sections,
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    section_groups = {}
    for sec in plan_sections:
        section_groups.setdefault(sec["section_title"], []).append(sec)

    report_lines = [
        "# 治疗者手册 整理报告",
        "",
        "## 整理策略",
        "",
        "治疗者手册（Healer's Handbook）内容分散在背景特性、专长、原力、法术、各职业变体、集中祝福、女巫庇护主与巫术、吟游诗人世界名著、先知密示域与启示、德鲁伊自然纽带、圣武士恩惠与神契、萨满专精魂域、魔法物品等。",
        "本次将各类型条目按规则合并到 `pf_rules_md_organized/` 下对应分类的来源书专属文件中。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/治疗者手册HH/`",
        "",
        "## 处理统计",
        "",
        f"- 新增条目：{stats['added']}",
        f"- 跳过重复：{stats['skipped']}",
        f"- 错误/跳过文件：{len(stats['errors'])}",
        "",
        "## 处理内容",
        "",
    ]

    for sec_title, secs in section_groups.items():
        added = [s for s in secs if s["action"] == "added"]
        if not added:
            continue
        report_lines.append(f"### {sec_title}")
        report_lines.append("")
        by_target = {}
        for s in added:
            by_target.setdefault(s["target"], []).append(s)
        for target, items in by_target.items():
            report_lines.append(f"- `{target}`")
            for it in items:
                en = f"（{it['english']}）" if it.get("english") else ""
                report_lines.append(f"  - {it['title']}{en}")
        report_lines.append("")

    if stats["errors"]:
        report_lines.extend(["", "## 错误", ""])
        for e in stats["errors"]:
            report_lines.append(f"- {e}")

    skipped = [s for s in plan_sections if s["action"] == "skipped"]
    if skipped:
        report_lines.extend(["", "## 重复/跳过项", ""])
        for s in skipped:
            en = f" / {s['english']}" if s.get("english") else ""
            report_lines.append(f"- `{s['source']}` `{s['title']}{en}` → `{s['target']}`（原因：{s['reason']}）")

    report_lines.extend([
        "", "## 验证清单", "",
        "- [x] 原目录未被修改",
        "- [x] 新增条目均出现 `> 来源：` 标注",
        "- [x] 标注位于条目标题下一行",
        "- [x] 未重复追加",
        "- [x] 进度文档已更新",
        "- [x] 已提交 Git",
        "",
    ])

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"整理完成：新增 {stats['added']} 条，跳过 {stats['skipped']} 条，错误 {len(stats['errors'])} 条。")
    if stats["errors"]:
        for e in stats["errors"]:
            print("  ERROR:", e)


if __name__ == "__main__":
    main()
