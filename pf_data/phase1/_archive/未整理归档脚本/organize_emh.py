#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
整理 元素大师手册Elemental Master's Handbook（EMH）从 pf_rules_md/未整理/元素大师手册EMH
到 pf_rules_md_organized/ 对应目录。

策略：
- 变体、进阶职业、幻灵亚种 → 源书聚合或对应职业页面
- 血脉 → 对应职业血脉页面
- 世界名著 → 传世名作汇总
- 盗贼天赋 → 盗贼 page_62.md
- 魅影情感羁绊 → 唤魂师 page_271.md
- 法师学派/专攻学派 → 法师 page_68.md
- 先知秘示域/诅咒/启示 → 先知 page_88.md / 先知诅咒全扩展.md
- 炼金科研发现 → 炼金术师 page_71.md
- 操念使注能/原力 → 操念使 page_260.md
- 专长/法术/物品：本次先跳过，记录到报告
"""

import re
from pathlib import Path
from datetime import datetime

from html_fallback import read_source_text, mark_connected

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/元素大师手册EMH"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_DIR = BASE

SOURCE_BOOK = "元素大师手册（Elemental Master's Handbook）EMH"
SOURCE_BOOK_SHORT = "EMH"


def normalize_to_nl(text: str, target_nl: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if target_nl == "\r\n":
        text = text.replace("\n", "\r\n")
    return text


def detect_nl(path: Path) -> str:
    if not path.exists():
        return "\n"
    raw = path.read_bytes()
    return "\r\n" if b"\r\n" in raw else "\n"


def read_text_preserve(path: Path) -> tuple[str, str]:
    nl = detect_nl(path)
    if not path.exists():
        return "", nl
    return path.read_text(encoding="utf-8"), nl


def write_text_preserve(path: Path, text: str, nl: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = normalize_to_nl(text, nl)
    path.write_bytes(text.encode("utf-8"))


def append_to_file(path: Path, content: str) -> None:
    existing, nl = read_text_preserve(path)
    if existing and not existing.endswith("\n") and not existing.endswith("\r\n"):
        existing += nl
    elif existing and not (existing.endswith("\n") or existing.endswith("\r\n")):
        existing += nl
    new_content = existing + content
    write_text_preserve(path, new_content, nl)


def clean_translator_url(text: str) -> str:
    lines = text.splitlines()
    while lines and (
        not lines[0].strip()
        or lines[0].strip().startswith("http")
        or lines[0].strip().startswith("[http")
        or lines[0].strip().startswith("译者")
    ):
        lines.pop(0)
    return "\n".join(lines)


def merge_section_heading_lines(text: str) -> str:
    lines = text.splitlines()
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            if re.search(r"[A-Za-z]$", line.rstrip()) and re.match(r"^[A-Za-z]", next_line.lstrip()):
                merged.append(line.rstrip() + " " + next_line.lstrip())
                i += 2
                continue
        merged.append(line)
        i += 1
    return "\n".join(merged)


def merge_crossline_bold(text: str) -> str:
    lines = text.splitlines()
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        count = line.count("**")
        if count % 2 != 0:
            j = i + 1
            buf = line
            while j < len(lines):
                buf += " " + lines[j].strip()
                count += lines[j].count("**")
                if count % 2 == 0:
                    break
                j += 1
            merged.append(buf)
            i = j + 1
        else:
            merged.append(line)
            i += 1
    return "\n".join(merged)


def make_source_annotation(source_file: str, l3: str = "") -> str:
    l3_part = f" → {l3}" if l3 else ""
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 元素大师手册EMH{l3_part}"


def make_hidden_marker(source_file: str, entry_name: str) -> str:
    return f"<!-- {SOURCE_BOOK_SHORT}-source:{source_file}:{entry_name} -->"


def is_title_span(span: str) -> bool:
    if not re.search(r"[一-鿿]", span):
        return False
    if re.search(r"[A-Za-z]", span):
        return True
    if re.search(r"[（(][^）)]+[）)]", span):
        return True
    return False


def extract_block_by_name(text: str, name: str, english: str = "") -> str | None:
    base_pattern = re.compile(r"\*\*[^*]*?" + re.escape(name) + r"[^*]*?\*\*")
    candidates = [m for m in base_pattern.finditer(text) if is_title_span(m.group(0))]

    if candidates and english:
        eng_norm = " ".join(english.lower().split())
        pref = []
        for m in candidates:
            span = m.group(0)
            norm = re.sub(r"\s+", " ", span).lower()
            if eng_norm in norm:
                pref.append(m)
        if pref:
            candidates = pref

    if candidates:
        start_match = min(candidates, key=lambda m: len(m.group(0)))
        start = start_match.start()
        rest = text[start_match.end():]
        next_pattern = re.compile(r"\*\*[^*]+?\*\*")
        pos = 0
        end = len(text)
        while True:
            nm = next_pattern.search(rest, pos)
            if not nm:
                break
            span = nm.group(0)
            if is_title_span(span):
                end = start_match.end() + nm.start()
                break
            pos = nm.end()
        return text[start:end].strip()

    if english:
        eng_pat = re.escape(english).replace(r"\ ", r"\s*")
        plain_pattern = re.compile(
            r"(?:^|\n)\s*(" + re.escape(name) + r"(?:(?:\s*[（(]\s*[^）)]*?" + eng_pat + r"[^）)]*?\s*[）)])|(?:\s*" + eng_pat + r")))",
            re.IGNORECASE,
        )
    else:
        plain_pattern = re.compile(r"(?:^|\n)\s*(" + re.escape(name) + r")", re.IGNORECASE)
    pm = plain_pattern.search(text)
    if pm:
        start = pm.start()
        rest = text[pm.end():]
        next_stop = re.search(r"\n\s*\n|\n\s*\*\*[^*]+\*\*", rest)
        if next_stop:
            end = pm.end() + next_stop.start()
        else:
            end = len(text)
        return text[start:end].strip()

    return None


def find_entry_headings(section_text: str, entries: list[dict]) -> list[tuple[int, dict, str]]:
    positions = []
    for entry in entries:
        name = entry["name"]
        english = entry.get("english", "")
        eng_pat = re.escape(english).replace(r"\ ", r"\s+")
        patterns = [
            re.compile(re.escape(name) + r"\s*[（(]\s*[^）)]*?" + eng_pat + r"[^）)]*?\s*[）)]", re.IGNORECASE),
            re.compile(re.escape(name) + r"\s*[（(][^）)]+[）)]\s*" + eng_pat, re.IGNORECASE),
            re.compile(re.escape(name) + r"\s*" + eng_pat, re.IGNORECASE),
            re.compile(r"\*\*[^*]*?" + re.escape(name) + r"[^*]*?\*\*", re.IGNORECASE),
        ]
        found = False
        for pattern in patterns:
            m = pattern.search(section_text)
            if m:
                positions.append((m.start(), entry, m.group(0)))
                found = True
                break
        if not found:
            pattern = re.compile(re.escape(name), re.IGNORECASE)
            m = pattern.search(section_text)
            if m:
                positions.append((m.start(), entry, m.group(0)))
    positions.sort(key=lambda x: x[0])
    return positions


def split_section_by_entries(section_text: str, entries: list[dict]) -> dict[str, str]:
    positions = find_entry_headings(section_text, entries)
    blocks = {}
    for i, (pos, entry, heading) in enumerate(positions):
        start = pos
        end = positions[i + 1][0] if i + 1 < len(positions) else len(section_text)
        blocks[entry["name"]] = section_text[start:end].strip()
    return blocks


def extract_section(text: str, start_marker: str, end_marker: str = "") -> str | None:
    start_pat = re.compile(re.escape(start_marker), re.IGNORECASE)
    sm = start_pat.search(text)
    if not sm:
        return None
    start = sm.start()
    if end_marker:
        end_pat = re.compile(re.escape(end_marker), re.IGNORECASE)
        em = end_pat.search(text, sm.end())
        if em:
            return text[start:em.start()].strip()
    return text[start:].strip()


def split_by_hr(text: str) -> list[str]:
    blocks = re.split(r"\n\s*[-*]{3,}\s*\n", text)
    result = []
    for block in blocks:
        block = block.strip()
        if block:
            result.append(clean_translator_url(block))
    return result


# ========== 配置 ==========

ARCHETYPES = [
    {"name": "纵火狂徒", "english": "Firebrand", "class": "铳士", "source_file": "page_1111.md"},
    {"name": "歌火者", "english": "Flamesinger", "class": "吟游诗人", "source_file": "page_1111.md"},
    {"name": "坚信者", "english": "Foundation of Faith", "class": "牧师", "source_file": "page_1112.md"},
    {"name": "大地之影", "english": "Earthshadow", "class": "盗贼", "source_file": "page_1112.md"},
    {"name": "阿本迭戈泳者", "english": "Abendgeo Diver", "class": "游侠", "source_file": "page_1113.md"},
    {"name": "风暴召唤者", "english": "Storm Caller", "class": "召唤师", "source_file": "page_1114.md"},
    {"name": "风行大师", "english": "Windstep Master", "class": "武僧", "source_file": "page_1114.md"},
    {"name": "能量科研员", "english": "Energy Scientist", "class": "炼金术师", "source_file": "page_1119.md"},
]

ARCHETYPE_SECTION_MARKERS = {
    "page_1111.md": ("**变体ARCHETYPES**", "**世界名著MASTERPIECES**"),
    "page_1112.md": ("**变体ARCHETYPES**", "**天赋**"),
    "page_1113.md": ("", "情感羁绊-"),
    "page_1114.md": ("", "**气之法术SPELLS OF AIR**"),
    "page_1119.md": ("", "**新科研发现NEW DISCOVERY**"),
}

BLOODLINES = [
    {"name": "火蜥", "english": "Salamander", "type": "血脉狂怒者", "source_file": "page_1111.md", "target": "职业/混合职业/血脉狂怒者/page_99.md"},
    {"name": "火蜥", "english": "Salamander", "type": "术士", "source_file": "page_1111.md", "target": "职业/核心职业/术士/page_24.md"},
]

MASTERPIECES = [
    {"name": "爆燃回旋曲", "english": "Blazing Rondo", "source_file": "page_1111.md"},
    {"name": "迷欲之舞", "english": "dance of captivating desire", "source_file": "page_1111.md"},
]

ROGUE_TALENTS = [
    {"name": "壁垒", "english": "Castling", "source_file": "page_1112.md"},
    {"name": "额外残岩", "english": "Extra Earthcraft", "source_file": "page_1112.md"},
    {"name": "坚固阵地", "english": "Fortified Position", "source_file": "page_1112.md"},
    {"name": "失衡技巧", "english": "Unbalancing Trick", "source_file": "page_1112.md"},
    {"name": "墙角杀法", "english": "Against the Wall", "source_file": "page_1112.md"},
    {"name": "石化打击", "english": "Petrifying Strike", "source_file": "page_1112.md"},
    {"name": "回音击", "english": "Resonating Rumbles", "source_file": "page_1112.md"},
    {"name": "石化肌肤", "english": "Stony Skin", "source_file": "page_1112.md"},
]

PHANTOM_FOCUS = [
    {"name": "绝望灵", "english": "Despair", "source_file": "page_1113.md"},
]

PRESTIGE_CLASSES = [
    {"name": "巨灵束缚者", "english": "Genie Binder", "source_file": "page_1117.md"},
]

EIDOLON_SUBTYPES = [
    {"name": "巨灵幻灵", "english": "Genie Eidolon", "source_file": "page_1117.md"},
]

WIZARD_SCHOOLS = [
    {"name": "以太元素学派", "english": "Aether Elemental School", "source_file": "page_1115.md"},
    {"name": "冰学派", "english": "Ice", "source_file": "page_1115.md"},
    {"name": "熔岩学派", "english": "Magma", "source_file": "page_1115.md"},
    {"name": "泥学派", "english": "Mud", "source_file": "page_1115.md"},
    {"name": "烟学派", "english": "Smoke", "source_file": "page_1115.md"},
]

ORACLE_MYSTERIES = [
    {
        "name": "元素",
        "english": "Elemental",
        "source_file": "page_1118.md",
        "revelations": [
            {"name": "流转水舞", "english": "Flowing Dance"},
            {"name": "沙漠幻影", "english": "Desert Mirage"},
            {"name": "元素庇护", "english": "Elemental Shelter"},
            {"name": "元素盟友", "english": "Elemental Ally"},
            {"name": "元素导能", "english": "Elemental Channel"},
            {"name": "元素抗力", "english": "Elemental Resistance"},
            {"name": "流动步伐", "english": "Fluid Steps"},
            {"name": "重铸武器", "english": "Reforged Weapon"},
            {"name": "混浊之土", "english": "Turbid Earth"},
            {"name": "横扫冲击", "english": "Sweeping Impact"},
        ],
    },
]

ORACLE_CURSES = [
    {"name": "元素失衡", "english": "Elemental Imbalance", "source_file": "page_1118.md"},
]

ALCHEMICAL_DISCOVERIES = [
    {"name": "元素紊乱", "english": "Elemental Discorporation", "source_file": "page_1119.md"},
]

KINETICIST_INFUSIONS = [
    {"name": "抑光注能", "english": "Dampening Infusion", "source_file": "元素之力的操纵者.md"},
    {"name": "炫目注能", "english": "Dazzling Infusion", "source_file": "元素之力的操纵者.md"},
    {"name": "注能武器", "english": "Energize Weapon", "source_file": "元素之力的操纵者.md"},
    {"name": "渗透注能", "english": "Penetrating Infusion", "source_file": "元素之力的操纵者.md"},
    {"name": "纺锤", "english": "Spindle", "source_file": "元素之力的操纵者.md"},
    {"name": "丧胆注能", "english": "Unnerving Infusion", "source_file": "元素之力的操纵者.md"},
    {"name": "吸血注能", "english": "Vampiric Infusion", "source_file": "元素之力的操纵者.md"},
]

KINETICIST_UTILITY = [
    {"name": "磁力", "english": "Magnetism", "source_file": "元素之力的操纵者.md"},
    {"name": "高等磁力", "english": "Greater Magnetism", "source_file": "元素之力的操纵者.md"},
    {"name": "升柱", "english": "Pillar", "source_file": "元素之力的操纵者.md"},
]


# ========== 通用追加函数 ==========

def append_entry(path: Path, marker: str, heading: str, source_annotation: str, block: str, existing: str, report: dict, item_type: str, item_name: str, target_rel: str) -> None:
    if marker in existing:
        report["skipped"].append(f"{item_type}已存在: {item_name}")
        return
    entry = (
        f"\n{marker}\n"
        f"{heading}\n"
        f"{source_annotation}\n"
        f"{block}\n\n"
    )
    append_to_file(path, entry)
    report["merged"].append({"type": item_type, "name": item_name, "target": target_rel})


# ========== 1. 职业变体 ==========

def process_archetypes(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "元素大师手册EMH_变体.md"
    if not target_path.exists():
        write_text_preserve(target_path, f"# {SOURCE_BOOK} 职业变体\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    by_source: dict[str, list[dict]] = {}
    for arc in ARCHETYPES:
        by_source.setdefault(arc["source_file"], []).append(arc)

    blocks_cache: dict[str, dict[str, str]] = {}
    for source_file, entries in by_source.items():
        text = (SRC_DIR / source_file).read_text(encoding="utf-8")
        text = merge_section_heading_lines(text)
        text = merge_crossline_bold(text)
        text = clean_translator_url(text)
        start_marker, end_marker = ARCHETYPE_SECTION_MARKERS.get(source_file, ("", ""))
        if start_marker:
            section = extract_section(text, start_marker, end_marker) or ""
        elif end_marker:
            end_pat = re.compile(re.escape(end_marker), re.IGNORECASE)
            em = end_pat.search(text)
            section = text[:em.start()] if em else text
        else:
            section = text
        blocks_cache[source_file] = split_section_by_entries(section, entries)

    for arc in ARCHETYPES:
        block = blocks_cache[arc["source_file"]].get(arc["name"])
        if block is None:
            report["warnings"].append(f"未找到变体块: {arc['name']} ({arc['source_file']})")
            continue
        marker = make_hidden_marker(arc["source_file"], arc["name"])
        append_entry(
            target_path,
            marker,
            f"## {arc['name']}（{arc['english']}）〔{arc['class']}变体〕",
            make_source_annotation(arc["source_file"], "变体/职业选项"),
            block,
            existing,
            report,
            "变体",
            arc["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 2. 血脉 ==========

def process_bloodlines(report: dict) -> None:
    # 按 source_file 分组，避免重复读取
    by_source: dict[str, list[dict]] = {}
    for bl in BLOODLINES:
        by_source.setdefault(bl["source_file"], []).append(bl)

    blocks_cache: dict[str, dict[str, str]] = {}
    for source_file, entries in by_source.items():
        text = (SRC_DIR / source_file).read_text(encoding="utf-8")
        text = merge_section_heading_lines(text)
        text = merge_crossline_bold(text)
        text = clean_translator_url(text)
        blocks_cache[source_file] = split_section_by_entries(text, entries)

    for bl in BLOODLINES:
        block = blocks_cache[bl["source_file"]].get(bl["name"])
        if block is None:
            report["warnings"].append(f"未找到血脉块: {bl['name']} ({bl['type']}) ({bl['source_file']})")
            continue
        target_path = ORG_DIR / bl["target"]
        if not target_path.exists():
            write_text_preserve(target_path, f"# {bl['type']}血脉\n\n", "\n")
        existing, _ = read_text_preserve(target_path)
        marker = make_hidden_marker(bl["source_file"], f"{bl['name']}({bl['type']})")
        append_entry(
            target_path,
            marker,
            f"## {bl['name']}（{bl['english']}）〔{bl['type']}血脉〕",
            make_source_annotation(bl["source_file"], "血脉"),
            block,
            existing,
            report,
            "血脉",
            f"{bl['name']}（{bl['type']}）",
            bl["target"],
        )


# ========== 3. 世界名著 ==========

def process_masterpieces(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "传世名作汇总.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 吟游诗人传世名作汇总\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    text = (SRC_DIR / "page_1111.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    section = extract_section(text, "世界名著MASTERPIECES", "血脉BLOODLINES") or ""
    blocks = split_section_by_entries(section, MASTERPIECES)

    for mp in MASTERPIECES:
        block = blocks.get(mp["name"])
        if block is None:
            report["warnings"].append(f"未找到世界名著块: {mp['name']} ({mp['source_file']})")
            continue
        marker = make_hidden_marker(mp["source_file"], mp["name"])
        append_entry(
            target_path,
            marker,
            f"## {mp['name']}（{mp['english']}）",
            make_source_annotation(mp["source_file"], "世界名著"),
            block,
            existing,
            report,
            "世界名著",
            mp["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 4. 盗贼天赋 ==========

def process_rogue_talents(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "核心职业" / "盗贼" / "page_62.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 盗贼天赋\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    text = (SRC_DIR / "page_1112.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    section = extract_section(text, "天赋", "石之平面") or ""
    blocks = split_section_by_entries(section, ROGUE_TALENTS)

    for rt in ROGUE_TALENTS:
        block = blocks.get(rt["name"])
        if block is None:
            report["warnings"].append(f"未找到盗贼天赋块: {rt['name']} ({rt['source_file']})")
            continue
        marker = make_hidden_marker(rt["source_file"], rt["name"])
        append_entry(
            target_path,
            marker,
            f"## {rt['name']}（{rt['english']}）",
            make_source_annotation(rt["source_file"], "盗贼天赋"),
            block,
            existing,
            report,
            "盗贼天赋",
            rt["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 5. 魅影情感羁绊 ==========

def process_phantom_focus(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "唤魂师" / "page_271.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 魅影\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    text = (SRC_DIR / "page_1113.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    section = extract_section(text, "情感羁绊-", "水之法术") or ""
    blocks = split_section_by_entries(section, [{"name": "绝望灵", "english": "Despair"}])
    block = blocks.get("绝望灵")
    if block is None:
        report["warnings"].append("未找到绝望灵块")
        return
    marker = make_hidden_marker("page_1113.md", "绝望灵")
    append_entry(
        target_path,
        marker,
        "## 绝望灵（Despair）",
        make_source_annotation("page_1113.md", "魅影情感羁绊"),
        block,
        existing,
        report,
        "魅影情感羁绊",
        "绝望灵",
        str(target_path.relative_to(ORG_DIR)),
    )


# ========== 6. 进阶职业 ==========

def process_prestige_classes(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "进阶职业" / "元素大师手册EMH_进阶职业.md"
    if not target_path.exists():
        write_text_preserve(target_path, f"# {SOURCE_BOOK} 进阶职业\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    by_source: dict[str, list[dict]] = {}
    for pc in PRESTIGE_CLASSES:
        by_source.setdefault(pc["source_file"], []).append(pc)

    blocks_cache: dict[str, dict[str, str]] = {}
    for source_file, entries in by_source.items():
        text = (SRC_DIR / source_file).read_text(encoding="utf-8")
        text = merge_section_heading_lines(text)
        text = merge_crossline_bold(text)
        text = clean_translator_url(text)
        blocks_cache[source_file] = split_section_by_entries(text, entries)

    for pc in PRESTIGE_CLASSES:
        block = blocks_cache[pc["source_file"]].get(pc["name"])
        if block is None:
            report["warnings"].append(f"未找到进阶职业块: {pc['name']} ({pc['source_file']})")
            continue
        marker = make_hidden_marker(pc["source_file"], pc["name"])
        append_entry(
            target_path,
            marker,
            f"## {pc['name']}（{pc['english']}）",
            make_source_annotation(pc["source_file"], "进阶职业"),
            block,
            existing,
            report,
            "进阶职业",
            pc["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 7. 幻灵亚种 ==========

def process_eidolon_subtypes(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "掉链子（Unchained）" / "召唤师" / "page_247.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 幻灵\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    text = (SRC_DIR / "page_1117.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_text = clean_translator_url(text)
    section = extract_section(text, "巨灵幻灵（幻灵亚种）") or ""
    blocks = split_section_by_entries(section, EIDOLON_SUBTYPES)

    for es in EIDOLON_SUBTYPES:
        block = blocks.get(es["name"])
        if block is None:
            report["warnings"].append(f"未找到幻灵亚种块: {es['name']} ({es['source_file']})")
            continue
        marker = make_hidden_marker(es["source_file"], es["name"])
        append_entry(
            target_path,
            marker,
            f"## {es['name']}（{es['english']}）",
            make_source_annotation(es["source_file"], "幻灵亚种"),
            block,
            existing,
            report,
            "幻灵亚种",
            es["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 8. 法师学派 ==========

def process_wizard_schools(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "核心职业" / "法师" / "page_68.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 法师奥术学派\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    text = (SRC_DIR / "page_1115.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    blocks = split_section_by_entries(text, WIZARD_SCHOOLS)

    for ws in WIZARD_SCHOOLS:
        block = blocks.get(ws["name"])
        if block is None:
            report["warnings"].append(f"未找到法师学派块: {ws['name']} ({ws['source_file']})")
            continue
        marker = make_hidden_marker(ws["source_file"], ws["name"])
        heading = f"## {ws['name']}（{ws['english']}）"
        if "专攻" in ws["name"] or ws["name"] in ("冰学派", "熔岩学派", "泥学派", "烟学派"):
            heading = f"## {ws['name']}（{ws['english']}）〔专攻学派〕"
        append_entry(
            target_path,
            marker,
            heading,
            make_source_annotation(ws["source_file"], "法师学派/专攻学派"),
            block,
            existing,
            report,
            "法师学派",
            ws["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 9. 先知秘示域、启示、诅咒 ==========

def process_oracle(report: dict) -> None:
    mystery_target = ORG_DIR / "职业" / "基础职业" / "先知" / "page_88.md"
    if not mystery_target.exists():
        write_text_preserve(mystery_target, "# 先知秘示域\n\n", "\n")
    mystery_existing, _ = read_text_preserve(mystery_target)

    curse_target = ORG_DIR / "职业" / "基础职业" / "先知" / "先知诅咒全扩展.md"
    if not curse_target.exists():
        write_text_preserve(curse_target, "# 先知诅咒\n\n", "\n")
    curse_existing, _ = read_text_preserve(curse_target)

    text = (SRC_DIR / "page_1118.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    # 秘示域
    for mys in ORACLE_MYSTERIES:
        section = extract_section(text, "元素（先知秘示域）", "元素失衡")
        if section is None:
            report["warnings"].append(f"未找到先知秘示域块: {mys['name']}")
            continue
        marker = make_hidden_marker(mys["source_file"], mys["name"])
        append_entry(
            mystery_target,
            marker,
            f"## {mys['name']}（{mys['english']}）〔先知秘示域〕",
            make_source_annotation(mys["source_file"], "先知秘示域"),
            section,
            mystery_existing,
            report,
            "先知秘示域",
            mys["name"],
            str(mystery_target.relative_to(ORG_DIR)),
        )

        # 启示追加到同一文件
        rev_section = extract_section(text, "启示：", "最终启示")
        if rev_section:
            rev_blocks = split_section_by_entries(rev_section, mys["revelations"])
            for rev in mys["revelations"]:
                block = rev_blocks.get(rev["name"])
                if block is None:
                    report["warnings"].append(f"未找到启示块: {rev['name']} ({mys['name']})")
                    continue
                rev_marker = make_hidden_marker(mys["source_file"], f"{mys['name']}-{rev['name']}")
                append_entry(
                    mystery_target,
                    rev_marker,
                    f"### {rev['name']}（{rev['english']}）",
                    make_source_annotation(mys["source_file"], f"先知秘示域/{mys['name']}/启示"),
                    block,
                    mystery_existing,
                    report,
                    "先知启示",
                    f"{mys['name']}-{rev['name']}",
                    str(mystery_target.relative_to(ORG_DIR)),
                )

    # 诅咒
    for cur in ORACLE_CURSES:
        section = extract_section(text, "元素失衡", "")
        if section is None:
            report["warnings"].append(f"未找到先知诅咒块: {cur['name']}")
            continue
        marker = make_hidden_marker(cur["source_file"], cur["name"])
        append_entry(
            curse_target,
            marker,
            f"## {cur['name']}（{cur['english']}）〔先知诅咒〕",
            make_source_annotation(cur["source_file"], "先知诅咒"),
            section,
            curse_existing,
            report,
            "先知诅咒",
            cur["name"],
            str(curse_target.relative_to(ORG_DIR)),
        )


# ========== 10. 炼金科研发现 ==========

def process_alchemical_discoveries(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "基础职业" / "炼金术师" / "page_71.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 炼金术师科研发现\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    text = (SRC_DIR / "page_1119.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    section = extract_section(text, "新科研发现NEW DISCOVERY", "炼金物品ALCHEMICAL ITEMS") or ""
    blocks = split_section_by_entries(section, ALCHEMICAL_DISCOVERIES)

    for ad in ALCHEMICAL_DISCOVERIES:
        block = blocks.get(ad["name"])
        if block is None:
            report["warnings"].append(f"未找到炼金科研发现块: {ad['name']} ({ad['source_file']})")
            continue
        marker = make_hidden_marker(ad["source_file"], ad["name"])
        append_entry(
            target_path,
            marker,
            f"## {ad['name']}（{ad['english']}）",
            make_source_annotation(ad["source_file"], "炼金术师科研发现"),
            block,
            existing,
            report,
            "炼金科研发现",
            ad["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 11. 操念使注能 ==========

def process_kineticist_infusions(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "操念使" / "page_260.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 操念使注能\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    text = (SRC_DIR / "元素之力的操纵者.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    section = extract_section(text, "注能INFUSIONS", "通用原力UTILITY WILD TALENTS") or ""
    blocks = split_section_by_entries(section, KINETICIST_INFUSIONS)

    for inf in KINETICIST_INFUSIONS:
        block = blocks.get(inf["name"])
        if block is None:
            report["warnings"].append(f"未找到操念使注能块: {inf['name']} ({inf['source_file']})")
            continue
        marker = make_hidden_marker(inf["source_file"], inf["name"])
        append_entry(
            target_path,
            marker,
            f"## {inf['name']}（{inf['english']}）",
            make_source_annotation(inf["source_file"], "操念使注能"),
            block,
            existing,
            report,
            "操念使注能",
            inf["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 12. 操念使通用原力 ==========

def process_kineticist_utility(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "操念使" / "操念使原力整合.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 操念使原力\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    text = (SRC_DIR / "元素之力的操纵者.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    section = extract_section(text, "通用原力UTILITY WILD TALENTS", "") or ""
    blocks = split_section_by_entries(section, KINETICIST_UTILITY)

    for ut in KINETICIST_UTILITY:
        block = blocks.get(ut["name"])
        if block is None:
            report["warnings"].append(f"未找到操念使通用原力块: {ut['name']} ({ut['source_file']})")
            continue
        marker = make_hidden_marker(ut["source_file"], ut["name"])
        append_entry(
            target_path,
            marker,
            f"## {ut['name']}（{ut['english']}）",
            make_source_annotation(ut["source_file"], "操念使通用原力"),
            block,
            existing,
            report,
            "操念使通用原力",
            ut["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 12b. 专长/法术/物品（HTML 回退清洗后处理） ==========

def get_cleaned_text(source_file: str, kind: str = "") -> str:
    """从 HTML 回退读取清洗后的文本；如未注册则回退到原 Markdown。"""
    src_path = SRC_DIR / source_file
    return read_source_text(src_path, kind)


def clean_block(block: str) -> str:
    """清理条目块：移除译者/URL 行，合并多余空行。"""
    lines = block.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("http") or stripped.startswith("译者"):
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_feat_title(line: str) -> tuple[str, str, str]:
    """从专长标题行提取 (中文名, 英文名, 类型)。"""
    # 尝试匹配：中文 英文（类型）描述
    # 英文允许空格、连字符、撇号（含中文文档中常见的 “ ’ ” 变体）
    m = re.match(
        r"^([一-龥]+(?:\s*[·•]\s*[一-龥]+)*)\s*"
        r"([A-Za-z][A-Za-z0-9\s'’\-]*?)?"
        r"(?:（([^）]+)）)?"
        r"(?:PFS不可用)?"
        r"(.*)$",
        line.strip(),
    )
    if not m:
        # 退化为仅中文
        m2 = re.match(r"^([一-龥]+(?:（[^）]+）)?)(.*)$", line.strip())
        if m2:
            return m2.group(1).strip(), "", m2.group(2).strip()
        return line.strip(), "", ""
    name = m.group(1).strip()
    english = (m.group(2) or "").strip()
    feat_type = (m.group(3) or "").strip()
    # 清理英文末尾可能残留的 PFS/中文混杂物
    english = re.sub(r"[^A-Za-z0-9\s'’\-]+$", "", english).strip()
    return name, english, feat_type


REGIONAL_FEATS = [
    # 火之域
    {"name": "重生于烬", "english": "Growth in Ash", "source_file": "page_1111.md"},
    {"name": "护砧之锤", "english": "Hammer Guards the Anvil", "source_file": "page_1111.md"},
    {"name": "熔火狂暴", "english": "Flumefire Rage", "source_file": "page_1111.md"},
    {"name": "日耀斩", "english": "Sunblade", "source_file": "page_1111.md"},
    # 土之域
    {"name": "碎石拳", "english": "Stone-handed", "source_file": "page_1112.md"},
    {"name": "无趣劳作", "english": "Joyless Toil", "source_file": "page_1112.md"},
    {"name": "库拉贡敦姿态", "english": "Kraggodan's Stance", "source_file": "page_1112.md"},
    # 水之域
    {"name": "深海法术", "english": "Benthic Spell", "source_file": "page_1113.md"},
    {"name": "咸水法术", "english": "Brackish Spell", "source_file": "page_1113.md"},
    {"name": "舱底之鼠", "english": "Bilge Rat", "source_file": "page_1113.md"},
    {"name": "风暴粉碎者", "english": "Storm Breaker", "source_file": "page_1113.md"},
    # 气之域
    {"name": "苔原疾行", "english": "Tundra Stride", "source_file": "page_1114.md"},
    {"name": "风之歌", "english": "Wind Song", "source_file": "page_1114.md"},
    {"name": "群山之眼", "english": "Mountain Eyes", "source_file": "page_1114.md"},
    {"name": "暴风拳", "english": "", "source_file": "page_1114.md"},
]


def process_emh_regional_feats(report: dict) -> None:
    """处理四元素之域的区域专长。"""
    target_path = ORG_DIR / "专长" / "元素大师手册EMH_专长.md"
    if not target_path.exists():
        write_text_preserve(target_path, f"# {SOURCE_BOOK} 专长\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    by_source: dict[str, list[dict]] = {}
    for feat in REGIONAL_FEATS:
        by_source.setdefault(feat["source_file"], []).append(feat)

    blocks_cache: dict[str, dict[str, str]] = {}
    for source_file, entries in by_source.items():
        text = get_cleaned_text(source_file, "feat")
        text = merge_section_heading_lines(text)
        text = merge_crossline_bold(text)
        text = clean_translator_url(text)

        # 找到该文件对应的 "X之域" 专长区域（允许英文后缀如 **火之域LANDS OF FIRE**）
        domain_match = re.search(r"\*\*[火水土气]之域[^*]*\*\*", text)
        if not domain_match:
            report["warnings"].append(f"未找到 {source_file} 的区域专长节")
            continue
        section = text[domain_match.start():]

        # 按 **** 分隔，找出包含 "专长效果" 的块
        blocks = re.split(r"\n\s*[-*]{3,}\s*\n", section)
        found_blocks: dict[str, str] = {}
        for block in blocks:
            block = block.strip()
            if "专长效果" not in block:
                continue
            lines = [ln for ln in block.splitlines() if ln.strip()]
            if not lines:
                continue
            # 尝试用条目名定位块边界（允许区域描述在前）
            for entry in entries:
                name = entry["name"]
                for i, line in enumerate(lines):
                    if line.startswith(name):
                        # 从该条目名所在行开始截取到块尾
                        found_blocks[name] = "\n".join(lines[i:])
                        break
        blocks_cache[source_file] = found_blocks

    for feat in REGIONAL_FEATS:
        block = blocks_cache.get(feat["source_file"], {}).get(feat["name"])
        if block is None:
            report["warnings"].append(f"未找到区域专长块: {feat['name']}")
            continue
        marker = make_hidden_marker(feat["source_file"], feat["name"])
        name, english, feat_type = parse_feat_title(block.splitlines()[0])
        title_parts = [name]
        if english:
            title_parts.append(f"（{english}）")
        if feat_type:
            title_parts.append(f"〔{feat_type}〕")
        heading = f"## {''.join(title_parts)}"
        body = clean_block("\n".join(block.splitlines()[1:]))
        append_entry(
            target_path,
            marker,
            heading,
            make_source_annotation(feat["source_file"], "区域专长"),
            body,
            existing,
            report,
            "专长",
            feat["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


SPELL_FILES = [
    {"source_file": "page_1113.md", "section_start": "**水之法术**", "section_end": "**水之域**"},
    {"source_file": "page_1114.md", "section_start": "**气之法术**", "section_end": "**气之域**"},
]


def process_emh_spells(report: dict) -> None:
    """处理水之法术和气之法术。"""
    target_path = ORG_DIR / "法术" / "元素大师手册EMH_法术.md"
    if not target_path.exists():
        write_text_preserve(target_path, f"# {SOURCE_BOOK} 法术\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    for cfg in SPELL_FILES:
        source_file = cfg["source_file"]
        text = get_cleaned_text(source_file, "spell")
        text = merge_section_heading_lines(text)
        text = merge_crossline_bold(text)
        text = clean_translator_url(text)

        # extract_section 要求精确匹配，但 EMH 的标题后紧跟英文（如 **气之法术SPELLS OF AIR**），改用正则
        start_pat = re.compile(re.escape(cfg["section_start"].rstrip("*")) + r"[^*]*\*\*", re.IGNORECASE)
        sm = start_pat.search(text)
        if not sm:
            report["warnings"].append(f"未找到法术章节起点: {cfg['section_start']} ({source_file})")
            continue
        start = sm.start()
        end_pat = re.compile(re.escape(cfg["section_end"].rstrip("*")) + r"[^*]*\*\*", re.IGNORECASE)
        em = end_pat.search(text, sm.end())
        end = em.start() if em else len(text)
        section = text[start:end].strip()

        blocks = re.split(r"\n\s*[-*]{3,}\s*\n", section)
        for block in blocks:
            block = block.strip()
            if not block or "环位" not in block:
                continue
            lines = [ln for ln in block.splitlines() if ln.strip()]
            if not lines:
                continue
            title_line = lines[0]
            # 法术标题：【学派】(子学派)名称[描述符]
            m = re.match(r"(【[^】]+】)(?:（[^）]+）)?\s*([^[\n]+?)(?:\[([^\]]+)\])?$", title_line.strip())
            if not m:
                report["warnings"].append(f"无法解析法术标题: {title_line[:40]}")
                continue
            school = m.group(1).strip()
            spell_name = m.group(2).strip()
            descriptors = (m.group(3) or "").strip()
            marker = make_hidden_marker(source_file, spell_name)
            heading = f"## {spell_name}"
            if descriptors:
                heading += f"〔{school}｜{descriptors}〕"
            else:
                heading += f"〔{school}〕"
            body = clean_block("\n".join(lines[1:]))
            append_entry(
                target_path,
                marker,
                heading,
                make_source_annotation(source_file, "法术"),
                body,
                existing,
                report,
                "法术",
                spell_name,
                str(target_path.relative_to(ORG_DIR)),
            )


# 物品配置：按文件分组，每个物品给出中文名与对应目标子类型
EMH_ITEMS = [
    # page_1112 石之平面
    {"name": "致密之锤", "english": "Hammer of Density", "source_file": "page_1112.md", "target": "装备_魔法物品/武器/元素大师手册EMH_物品.md", "category": "武器"},
    {"name": "神秘皇冠", "english": "Crown of Enlightenment", "source_file": "page_1112.md", "target": "装备_魔法物品/魔法物品/奇物/无位置/元素大师手册EMH_奇物.md", "category": "奇物"},
    {"name": "奇妙雕像（赤铁山狮）", "english": "Figurine of Wondrous Power", "source_file": "page_1112.md", "target": "装备_魔法物品/魔法物品/奇物/无位置/元素大师手册EMH_奇物.md", "category": "奇物"},
    {"name": "石化权杖", "english": "Petrification Rod", "source_file": "page_1112.md", "target": "装备_魔法物品/魔法物品/戒指_权杖_法杖/元素大师手册EMH_权杖.md", "category": "权杖"},
    {"name": "宝石雕刻者工具", "english": "Gemcutter's Tools", "source_file": "page_1112.md", "target": "装备_魔法物品/魔法物品/奇物/无位置/元素大师手册EMH_奇物.md", "category": "奇物"},
    # page_1116 元素扩增
    {"name": "火眼金睛", "english": "Blazing Eyes", "source_file": "page_1116.md", "target": "装备_魔法物品/魔法物品/奇物/无位置/元素大师手册EMH_元素扩增.md", "category": "元素扩增"},
    {"name": "灼手热臂", "english": "Blazing Hand", "source_file": "page_1116.md", "target": "装备_魔法物品/魔法物品/奇物/无位置/元素大师手册EMH_元素扩增.md", "category": "元素扩增"},
    {"name": "霜骨冰骸", "english": "Hoarfrost Bones", "source_file": "page_1116.md", "target": "装备_魔法物品/魔法物品/奇物/无位置/元素大师手册EMH_元素扩增.md", "category": "元素扩增"},
    {"name": "快银之血", "english": "Quicksilver Blood", "source_file": "page_1116.md", "target": "装备_魔法物品/魔法物品/奇物/无位置/元素大师手册EMH_元素扩增.md", "category": "元素扩增"},
    {"name": "燃烧之血", "english": "Smoldering Blood", "source_file": "page_1116.md", "target": "装备_魔法物品/魔法物品/奇物/无位置/元素大师手册EMH_元素扩增.md", "category": "元素扩增"},
    {"name": "蒸汽肺部", "english": "Vaporous Lungs", "source_file": "page_1116.md", "target": "装备_魔法物品/魔法物品/奇物/无位置/元素大师手册EMH_元素扩增.md", "category": "元素扩增"},
    {"name": "涡流之胃", "english": "Whirlpool Maw", "source_file": "page_1116.md", "target": "装备_魔法物品/魔法物品/奇物/无位置/元素大师手册EMH_元素扩增.md", "category": "元素扩增"},
    # page_1119 炼金物品
    {"name": "水延剂", "english": "Aqueous Elixir", "source_file": "page_1119.md", "target": "装备_魔法物品/货品服务/元素大师手册EMH_炼金物品.md", "category": "炼金物品"},
    {"name": "阿塔拉之光", "english": "Atlatl Light", "source_file": "page_1119.md", "target": "装备_魔法物品/货品服务/元素大师手册EMH_炼金物品.md", "category": "炼金物品"},
    {"name": "腐朽沙砾", "english": "Gravel of Ruin", "source_file": "page_1119.md", "target": "装备_魔法物品/货品服务/元素大师手册EMH_炼金物品.md", "category": "炼金物品"},
    {"name": "死地尘", "english": "Dust of the Dead", "source_file": "page_1119.md", "target": "装备_魔法物品/货品服务/元素大师手册EMH_炼金物品.md", "category": "炼金物品"},
    {"name": "土缚团块", "english": "Clod of Earth", "source_file": "page_1119.md", "target": "装备_魔法物品/货品服务/元素大师手册EMH_炼金物品.md", "category": "炼金物品"},
]


def _extract_item_block(text: str, item_name: str) -> str | None:
    """从清洗后的物品文本中提取单个物品块。"""
    # 先按 **** 分隔，再在每个块中查找物品名
    blocks = re.split(r"\n\s*[-*]{3,}\s*\n", text)
    for block in blocks:
        block = block.strip()
        idx = block.find(item_name)
        if idx == -1:
            continue
        # 找到物品名所在行/段落的起点
        prefix = block[:idx]
        # 如果前缀在同一行还有文字，截断到该物品名
        last_nl = prefix.rfind("\n")
        if last_nl == -1:
            # 物品名在块的第一行，去掉前面非物品名的文字
            block = block[idx:]
        else:
            block = block[last_nl + 1:]
        # 找到下一个物品起点或块结束
        # 启发：下一个以中文名开头且后面紧跟价格/灵光/CL/槽位/位置的行
        lines = block.splitlines()
        end = len(lines)
        for i in range(1, len(lines)):
            line = lines[i].strip()
            if re.match(r"^[一-龥]+", line) and re.search(r"价格|灵光|CL|槽位|位置|重量", line):
                end = i
                break
            if re.match(r"^\s*[-*]{3,}", line):
                end = i
                break
        return "\n".join(lines[:end]).strip()
    return None


def process_emh_items(report: dict) -> None:
    """处理 EMH 的魔法物品、元素扩增和炼金物品。"""
    by_target: dict[Path, list[dict]] = {}
    for item in EMH_ITEMS:
        target = ORG_DIR / item["target"]
        by_target.setdefault(target, []).append(item)

    # 缓存每个源文件的清洗后文本
    source_cache: dict[str, str] = {}
    for target_path, items in by_target.items():
        if not target_path.exists():
            # 根据路径推断标题
            if "炼金物品" in str(target_path):
                header = f"# {SOURCE_BOOK} 炼金物品\n\n"
            elif "元素扩增" in str(target_path):
                header = f"# {SOURCE_BOOK} 元素扩增\n\n"
            elif "奇物" in str(target_path):
                header = f"# {SOURCE_BOOK} 奇物\n\n"
            elif "权杖" in str(target_path):
                header = f"# {SOURCE_BOOK} 权杖\n\n"
            elif "武器" in str(target_path):
                header = f"# {SOURCE_BOOK} 武器\n\n"
            else:
                header = f"# {SOURCE_BOOK} 物品\n\n"
            write_text_preserve(target_path, header, "\n")
        existing, _ = read_text_preserve(target_path)

        for item in items:
            source_file = item["source_file"]
            if source_file not in source_cache:
                text = get_cleaned_text(source_file, "item")
                text = merge_section_heading_lines(text)
                text = merge_crossline_bold(text)
                text = clean_translator_url(text)
                source_cache[source_file] = text
            text = source_cache[source_file]

            block = _extract_item_block(text, item["name"])
            if block is None:
                report["warnings"].append(f"未找到物品块: {item['name']} ({source_file})")
                continue

            marker = make_hidden_marker(source_file, item["name"])
            heading = f"## {item['name']}"
            if item.get("english"):
                heading += f"（{item['english']}）"
            if item.get("category"):
                heading += f"〔{item['category']}〕"
            body = clean_block(block)
            append_entry(
                target_path,
                marker,
                heading,
                make_source_annotation(source_file, "物品"),
                body,
                existing,
                report,
                "物品",
                item["name"],
                str(target_path.relative_to(ORG_DIR)),
            )


# ========== 主流程 ==========

def main() -> None:
    report = {
        "merged": [],
        "skipped": [],
        "warnings": [],
    }

    process_archetypes(report)
    process_bloodlines(report)
    process_masterpieces(report)
    process_rogue_talents(report)
    process_phantom_focus(report)
    process_prestige_classes(report)
    process_eidolon_subtypes(report)
    process_wizard_schools(report)
    process_oracle(report)
    process_alchemical_discoveries(report)
    process_kineticist_infusions(report)
    process_kineticist_utility(report)

    # 处理专长/法术/物品（已接入 HTML 回退清洗）
    process_emh_regional_feats(report)
    process_emh_spells(report)
    process_emh_items(report)

    report_path = REPORT_DIR / "EMH_reorganization_report.md"
    lines = [f"# 元素大师手册（Elemental Master's Handbook）EMH 整理报告\n", f"\n生成时间：{datetime.now().isoformat()}\n"]
    lines.append("\n## 整理内容\n")
    for item in report["merged"]:
        lines.append(f"- **{item['type']}**：{item['name']} → `{item['target']}`")
    lines.append("\n## 跳过项\n")
    for item in report["skipped"]:
        lines.append(f"- {item}")
    lines.append("\n## 警告\n")
    for item in report["warnings"]:
        lines.append(f"- {item}")
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")
    if report["warnings"]:
        for w in report["warnings"]:
            print(f"  警告: {w}")


if __name__ == "__main__":
    main()
