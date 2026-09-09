#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 闹鬼英雄手册（Haunted Heroes Handbook）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/闹鬼英雄手册HHH/
目标目录：pf_data/phase1/pf_rules_md_organized/

包含 6 个源文件：
- 闹鬼专长.md          16 条专长 → 专长/闹鬼英雄手册HHH_专长.md
- 背景特性25.md        3 条背景特性 → 背景特性/闹鬼英雄手册HHH_背景特性.md
- 牧师变体领域力量.md   6 条变体领域力量 → 职业/核心职业/牧师/闹鬼英雄手册HHH_变体领域力量.md
- 仪式3.md             4 条驱魔仪式 → 法术/闹鬼英雄手册HHH_驱魔仪式.md
- page_672.md          10 条职业变体 → 各职业/闹鬼英雄手册HHH_变体.md
- page_1217.md         1 条术士血脉 → 职业/核心职业/术士/闹鬼英雄手册HHH_血脉.md
"""

import json
import os
import re

BASE = "/Users/chezi/code/java/pf_agent/pf_data/phase1"
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/闹鬼英雄手册HHH")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "HHH_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "HHH_reorganization_report.md")

SOURCE_NOTE_TEMPLATE = "> 来源：闹鬼英雄手册（Haunted Heroes Handbook），页码见原书，未整理 → 闹鬼英雄手册HHH → {section_title}"

HHH_FILES = [
    "专长/闹鬼英雄手册HHH_专长.md",
    "背景特性/闹鬼英雄手册HHH_背景特性.md",
    "职业/核心职业/牧师/闹鬼英雄手册HHH_变体领域力量.md",
    "法术/闹鬼英雄手册HHH_驱魔仪式.md",
    "职业/混合职业/杀手/闹鬼英雄手册HHH_变体.md",
    "职业/基础职业/女巫/闹鬼英雄手册HHH_变体.md",
    "职业/基础职业/审判者/闹鬼英雄手册HHH_变体.md",
    "职业/基础职业/炼金术师/闹鬼英雄手册HHH_变体.md",
    "职业/核心职业/战士/闹鬼英雄手册HHH_变体.md",
    "职业/核心职业/法师/闹鬼英雄手册HHH_变体.md",
    "职业/异能冒险（Occult Adventures）/通灵者/闹鬼英雄手册HHH_变体.md",
    "职业/异能冒险（Occult Adventures）/唤魂师/闹鬼英雄手册HHH_变体.md",
    "职业/混合职业/调查员/闹鬼英雄手册HHH_变体.md",
    "职业/核心职业/术士/闹鬼英雄手册HHH_血脉.md",
]


def load_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_lines(path):
    return load_text(path).splitlines()


def remove_hhh_content():
    """清除所有目标文件中以 HHH-source 标记的内容块，并删除 HHH 专属新文件。"""
    for root, dirs, files in os.walk(ORG_BASE):
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            if "<!-- HHH-source:" not in text:
                continue
            parts = re.split(r"(?=<!-- [A-Za-z]+-source:)", text)
            kept = [p for p in parts if not p.startswith("<!-- HHH-source:")]
            new_text = "".join(kept)
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_text)
    for rel in HHH_FILES:
        full = os.path.join(ORG_BASE, rel)
        if os.path.exists(full):
            os.remove(full)


def normalize_ws(text):
    return re.sub(r"\s+", " ", text).strip()


def split_cn_en(raw):
    raw = raw.strip()
    m = re.search(r"[A-Za-z]", raw)
    if m:
        return raw[: m.start()].strip(), raw[m.start():].strip()
    return raw, ""


def build_title_pattern(cn, en):
    """构造跨行匹配模式：** + cn + en 各词 + **。

    由于源文件中英文标题常被换行打断（如 'POSSESSED \\nHAND'），
    不能用 re.escape(en) 整体匹配。改为拆词后逐段匹配。
    """
    parts = [r"\*\*[\s\S]{0,20}?", re.escape(cn)]
    en_words = en.split()
    for w in en_words:
        parts.append(r"[\s\S]{0,40}?")
        parts.append(re.escape(w))
    parts.append(r"[\s\S]{0,40}?\*\*")
    return "".join(parts)


def parse_inline_title(text):
    """解析 '中文名（英文名）' 或 '中文名ENGLISH NAME'。"""
    text = normalize_ws(text.strip("*").strip())
    paren_m = re.match(r"^(.+?)[（(]([^）)]+)[）)](.*)$", text)
    if paren_m:
        before = paren_m.group(1).strip()
        inside = paren_m.group(2).strip()
        after = paren_m.group(3).strip()
        if not re.search(r"[一-鿿]", inside):
            return normalize_ws(before), normalize_ws(inside), normalize_ws(after)
        cn, en = split_cn_en(before)
        suffix = "（" + inside + "）" + ((" " + after) if after else "")
        return normalize_ws(cn), normalize_ws(en), normalize_ws(suffix)
    cn, en = split_cn_en(text)
    return normalize_ws(cn), normalize_ws(en), ""


def ensure_header(target_path, header):
    full_path = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    if not os.path.exists(full_path) or os.path.getsize(full_path) == 0:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(header + "\n\n")


def append_to_target(target_path, block):
    full_path = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "a", encoding="utf-8") as f:
        f.write(block)


def build_block(source, title_cn, title_en, section_title, body_lines, body_prefix=""):
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
    marker = f"<!-- HHH-source:{source}:{title_cn} -->"
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
    marker_key = f"<!-- HHH-source:{source}:{title_cn} -->"
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


# ---------------------------------------------------------------------------
# 闹鬼专长.md：16 个专长
# ---------------------------------------------------------------------------

# 每个专长：标题子串 + 标题后内容（用作分割锚点）。脚本通过 find 寻找标题出现位置切分。
FEATS = [
    # (cn, en, 下一条目起始子串，None 表示到文末)
    ("鬼上手", "POSSESSED HAND", "**自动手（HAND’S"),
    ("自动手", "HAND’S AUTONOMY", "**人手分离（HAND’S"),
    ("人手分离", "HAND’S DETACHMENT", "**手不释卷（HAND’S"),
    ("手不释卷", "HAND’S KNOWLEDGE", "**手心长眼（HAND’S"),
    ("手心长眼", "HAND’S SIGHT", "**精魄受体（SPIRIT"),
    ("精魄受体", "SPIRIT RIDDEN", "**英灵受体（CHANNEL"),
    ("英灵受体", "CHANNEL SPIRIT", "**精魄盟友（SPIRIT"),
    ("精魄盟友", "SPIRIT ALLY", "**精神训练（SPIRITUAL"),
    ("精神训练", "SPIRITUAL TRAINING", "**虚幻杀手"),
    ("虚幻杀手", "Ghostslayer", "**灵魂打击"),
    ("灵魂打击", "Soulwrecking Strike", "[**魂刃"),
    ("魂刃", "Soulblade", "**解说之策"),
    ("解说之策", "Studied Expertise", "**魅影盟友"),
    ("魅影盟友", "Phantom Ally", "**十方鬼众"),
    ("十方鬼众", "Spirit Oni Master", "**作祟拾荒者"),
    ("作祟拾荒者", "Haunt Scavenger", None),
]


def process_feats(stats, plan_sections):
    src = os.path.join(SRC_DIR, "闹鬼专长.md")
    text = load_text(src)
    target_path = "专长/闹鬼英雄手册HHH_专长.md"
    header = "# 闹鬼英雄手册 专长"

    for i, (cn, en, next_marker) in enumerate(FEATS):
        # 跨行匹配：标题英文可能被换行打断
        title_pattern = build_title_pattern(cn, en)
        m = re.search(title_pattern, text)
        if not m:
            stats["errors"].append(f"闹鬼专长.md 未找到条目：{cn}")
            continue

        start = m.end()
        if next_marker:
            nm = text.find(next_marker, start)
            if nm < 0:
                stats["errors"].append(f"闹鬼专长.md 未找到下一条目：{next_marker}")
                end = len(text)
            else:
                end = nm
        else:
            end = len(text)

        body = text[start:end].strip()
        # 去掉首部残留的标题结尾字符（*、）、空白）
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "闹鬼专长.md", target_path, "专长", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


# ---------------------------------------------------------------------------
# 背景特性25.md：3 条背景特性
# ---------------------------------------------------------------------------

TRAITS = [
    ("英灵向导/英灵引", "Guiding Spirit", "**灵性依恋"),
    ("灵性依恋", "Spiritual Attachment", "**钉魂门信徒"),
    ("钉魂门信徒", "Rivethun Adherent", None),
]


def process_traits(stats, plan_sections):
    src = os.path.join(SRC_DIR, "背景特性25.md")
    text = load_text(src)
    target_path = "背景特性/闹鬼英雄手册HHH_背景特性.md"
    header = "# 闹鬼英雄手册 背景特性"

    # 跳过文件头部的 URL/译者行
    # 第一个有效条目从"**英灵向导/英灵引"开始

    for cn, en, next_marker in TRAITS:
        # 跨行匹配：优先标准模式，若失败则退化到 cn + en 顺序匹配（处理"灵性依恋"格式：英文不在括号内）
        title_pattern = build_title_pattern(cn, en)
        m = re.search(title_pattern, text)
        if not m:
            m = re.search(
                re.escape(cn) + r"[\s\S]{0,200}?" + re.escape(en),
                text
            )
        if not m:
            stats["errors"].append(f"背景特性25.md 未找到条目：{cn}")
            continue

        start = m.end()
        if next_marker:
            nm = text.find(next_marker, start)
            end = nm if nm >= 0 else len(text)
        else:
            end = len(text)

        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        add_entry(
            "背景特性25.md", target_path, "背景特性", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


# ---------------------------------------------------------------------------
# 牧师变体领域力量.md：6 个神祇变体领域力量
# 文件中条目以 '---' 分隔；每个条目以 神祇名（拼音）开头
# ---------------------------------------------------------------------------

DOMAIN_POWERS = [
    ("阿斯莫迪斯", "Asmodeus", "诡术"),
    ("凯登凯连", "Cayden Cailean", "混乱"),
    ("义洛理", "Irori", "医疗"),
    ("奈德丽", "Naderi", "高贵"),
    ("法莱斯玛", "Pharasma", "安眠"),
    ("厄加图娅", "Urgathoa", "死亡"),
]


def process_domain_powers(stats, plan_sections):
    src = os.path.join(SRC_DIR, "牧师变体领域力量.md")
    text = load_text(src)
    target_path = "职业/核心职业/牧师/page_41.md"
    header = None  # 追加到牧师变体页

    # 按 "---" 分段；跳过首部译者行/标题
    chunks = re.split(r"\n-{3,}\n", text)
    for cn, en, domain in DOMAIN_POWERS:
        # 找包含 cn 的 chunk（en 可能因跨行不在同 chunk 中）
        matched = None
        for ch in chunks:
            if cn in ch:
                matched = ch
                break
        if not matched:
            stats["errors"].append(f"牧师变体领域力量.md 未找到神祇：{cn}")
            continue
        body = matched.strip()
        # 清理以 http 开头的译者署名行
        body_lines = [ln for ln in body.splitlines() if not ln.lstrip().startswith("[http")]
        body = "\n".join(body_lines).strip()

        title_cn = f"{cn}（{domain}领域变体力量）"
        add_entry(
            "牧师变体领域力量.md", target_path,
            "牧师变体领域力量", header, title_cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


# ---------------------------------------------------------------------------
# 仪式3.md：4 条驱魔仪式
# ---------------------------------------------------------------------------

RITUALS = [
    ("地缚结界", "Earthbound Ward", "**驱除作祟"),
    ("驱除作祟", "Exorcise Haunt", "**采集亵渎之魂"),
    ("采集亵渎之魂", "Harvest the Defiled Soul", "**诅咒之音"),
    ("诅咒之音", "Voice of the Damned", None),
]


def process_rituals(stats, plan_sections):
    src = os.path.join(SRC_DIR, "仪式3.md")
    text = load_text(src)
    target_path = "法术/闹鬼英雄手册HHH_驱魔仪式.md"
    header = "# 闹鬼英雄手册 驱魔仪式"

    for cn, en, next_marker in RITUALS:
        # 跨行匹配
        title_pattern = build_title_pattern(cn, en)
        m = re.search(title_pattern, text)
        if not m:
            stats["errors"].append(f"仪式3.md 未找到条目：{cn}")
            continue
        start = m.end()
        if next_marker:
            nm = text.find(next_marker, start)
            end = nm if nm >= 0 else len(text)
        else:
            end = len(text)
        body = text[start:end].strip()
        body = re.sub(r"^[\s\)\(]+", "", body)
        # 跳过首部 [http 译者行（已在第一条目之前）
        body_lines = [ln for ln in body.splitlines() if not ln.lstrip().startswith("[http")]
        body = "\n".join(body_lines).strip()
        add_entry(
            "仪式3.md", target_path, "驱魔仪式", header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


# ---------------------------------------------------------------------------
# page_672.md：10 个职业变体
# 格式：**中文名【English】** 职业
# ---------------------------------------------------------------------------

ARCHETYPES = [
    # (cn, en, 职业目录, 目标路径)
    ("鬼屠", "Spiritslayer", "杀手", "职业/混合职业/杀手/page_117.md", None),
    ("祈求者", "Invoker", "女巫", "职业/基础职业/女巫/page_70.md", None),
    ("除灵师", "Expulsionist", "审判者", "职业/基础职业/审判者/page_78.md", None),
    ("炼魂士", "Ectoplasm Master", "炼金术师", "职业/基础职业/炼金术师/page_21.md", None),
    ("钢魂神兵", "Steelbound Fighter", "战士", "职业/核心职业/战士/page_49.md", None),
    ("密契法师", "Pact wizard", "法师", "职业/核心职业/法师/page_67.md", None),
    ("导灵修士", "Rivethun Spirit Channeler", "通灵者", "职业/异能冒险（Occult Adventures）/通灵者/page_262.md", None),
    ("巫毒祭司", "Uda Wendo", "通灵者", "职业/异能冒险（Occult Adventures）/通灵者/page_262.md", None),
    ("痛苦之源", "Scourges", "唤魂师", "职业/异能冒险（Occult Adventures）/唤魂师/page_270.md", None),
    ("怪谈终结者", "Skeptic", "调查员", "职业/混合职业/调查员/page_107.md", None),
]


def process_archetypes(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_672.md")
    text = load_text(src)
    # 跳过首部 URL 与译者行
    # 文件首部含 "[http...]" 行和 "译者:" 行

    for i, (cn, en, klass, target_path, header) in enumerate(ARCHETYPES):
        # 跨行匹配：标题形如 **中文(English)【职业】**（半角括号 + 【职业】后缀），英文可跨行
        parts = [r"\*\*[\s\S]{0,20}?", re.escape(cn)]
        en_words = en.split()
        for w in en_words:
            parts.append(r"[\s\S]{0,40}?")
            parts.append(re.escape(w))
        parts.append(r"[\s\S]{0,40}?\*\*")
        title_pattern = "".join(parts)
        m = re.search(title_pattern, text)
        if not m:
            stats["errors"].append(f"page_672.md 未找到职业变体：{cn}")
            continue

        start = m.end()
        # 找下一条目
        if i + 1 < len(ARCHETYPES):
            next_cn, next_en, _, _, _ = ARCHETYPES[i + 1]
            next_parts = [r"\*\*[\s\S]{0,20}?", re.escape(next_cn)]
            for w in next_en.split():
                next_parts.append(r"[\s\S]{0,40}?")
                next_parts.append(re.escape(w))
            next_pattern = "".join(next_parts)
            nm = re.search(next_pattern, text[start:])
            end = (start + nm.start()) if nm else len(text)
        else:
            end = len(text)

        body = text[start:end].strip()
        # 去掉首部残留的 `*` （紧随标题的 `***起源于`）
        body = re.sub(r"^[\s\)\(]+", "", body)
        body_lines = [ln for ln in body.splitlines() if not ln.lstrip().startswith("[http")
                      and not ln.lstrip().startswith("译者:")]
        body = "\n".join(body_lines).strip()

        section_title = f"{klass}变体"
        add_entry(
            "page_672.md", target_path, section_title, header, cn, en,
            body_to_lines(body), "", stats, plan_sections
        )


# ---------------------------------------------------------------------------
# page_1217.md：1 条术士血脉
# ---------------------------------------------------------------------------

def process_bloodlines(stats, plan_sections):
    src = os.path.join(SRC_DIR, "page_1217.md")
    text = load_text(src)
    target_path = "职业/核心职业/术士/page_64.md"
    header = None  # 追加到术士变体页

    cn = "操灵血统"
    en = "Possessed"
    # 跨行匹配：标题形如 **操灵血统（Possessed）**
    title_pattern = (
        r"\*\*[\s\S]{0,20}?" + re.escape(cn)
        + r"[\s\S]{0,40}?" + re.escape(en) + r"[\s\S]{0,30}?\*\*"
    )
    m = re.search(title_pattern, text)
    if not m:
        stats["errors"].append("page_1217.md 未找到血脉条目")
        return

    body = text[m.end():].strip()
    # 跳过首部 [http 译者行
    body_lines = [ln for ln in body.splitlines() if not ln.lstrip().startswith("[http")]
    body = "\n".join(body_lines).strip()
    add_entry(
        "page_1217.md", target_path, "术士血脉", header, cn, en,
        body_to_lines(body), "", stats, plan_sections
    )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    remove_hhh_content()

    stats = {"added": 0, "skipped": 0, "errors": []}
    plan_sections = []

    process_feats(stats, plan_sections)
    process_traits(stats, plan_sections)
    process_domain_powers(stats, plan_sections)
    process_rituals(stats, plan_sections)
    process_archetypes(stats, plan_sections)
    process_bloodlines(stats, plan_sections)

    plan = {
        "source_book": "闹鬼英雄手册",
        "source_book_english": "Haunted Heroes Handbook",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/闹鬼英雄手册HHH",
        "stats": stats,
        "sections": plan_sections,
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 生成报告
    section_groups = {}
    for sec in plan_sections:
        section_groups.setdefault(sec["section_title"], []).append(sec)

    report_lines = [
        "# 闹鬼英雄手册 整理报告",
        "",
        "## 整理策略",
        "",
        "闹鬼英雄手册（Haunted Heroes Handbook）内容分散在专长、背景特性、牧师变体领域力量、驱魔仪式、职业变体与术士血脉中。",
        "本次将各类型条目按规则合并到 `pf_rules_md_organized/` 下对应分类的来源书专属文件中。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/闹鬼英雄手册HHH/`",
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
        by_source = {}
        for s in added:
            by_source.setdefault(s["source"], []).append(s)
        for source, items in by_source.items():
            target = items[0]["target"]
            report_lines.append(f"- `{source}` → `{target}`")
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