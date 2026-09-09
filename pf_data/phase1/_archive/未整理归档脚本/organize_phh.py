#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 位面行者手册（Plane-Hopper's Handbook）PHH 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/位面行者手册PHH/
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/位面行者手册PHH"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "PHH_reorganization_report.md"

SOURCE_BOOK = "位面行者手册（Plane-Hopper's Handbook）PHH"
SOURCE_BOOK_SHORT = "PHH"


def write_text_preserve(path: Path, text: str, line_ending: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\n", line_ending), encoding="utf-8")


def read_text_preserve(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    line_ending = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8"), line_ending


def append_to_file(path: Path, text: str) -> None:
    if not path.exists():
        write_text_preserve(path, "")
    existing, line_ending = read_text_preserve(path)
    existing = existing.replace("\r", "")
    if existing and not existing.endswith("\n"):
        existing += "\n"
    write_text_preserve(path, existing + text, line_ending)


def make_source_annotation(source_file: str, l3: str = "") -> str:
    l3_part = f" → {l3}" if l3 else ""
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 位面行者手册PHH{l3_part}"


def make_hidden_marker(source_file: str, entry_name: str) -> str:
    return f"<!-- {SOURCE_BOOK_SHORT}-source:{source_file}:{entry_name} -->"


def merge_section_heading_lines(text: str) -> str:
    lines = text.splitlines()
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*#+", line) and not line.rstrip().endswith(("）", ")", "]", "］")):
            j = i + 1
            buf = line
            while j < len(lines):
                next_line = lines[j]
                buf += " " + next_line.strip()
                if re.search(r"[）)］\]]\s*$", next_line):
                    break
                j += 1
            merged.append(buf)
            i = j + 1
        else:
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


def clean_translator_url(text: str) -> str:
    lines = text.splitlines()
    if lines and (
        lines[0].strip().startswith("[http")
        or re.match(r"^https?://", lines[0].strip())
        or "整理者" in lines[0]
        or "译者" in lines[0]
    ):
        lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return "\n".join(lines)


def clean_leading_image(text: str) -> str:
    """移除 Markdown 图片语法行，例如 ![[图片]](url)"""
    lines = text.splitlines()
    while lines and re.match(r"^\s*!\[.*\]\(.*\)\s*$", lines[0].strip()):
        lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return "\n".join(lines)


def find_entry_headings(section_text: str, entries: list[dict]) -> list[tuple[int, dict, str]]:
    positions = []
    for entry in entries:
        name = entry["name"]
        english = entry.get("english", "")
        eng_pat = re.escape(english).replace(r"\ ", r"\s+")
        patterns = [
            re.compile(r"\*\*[^*]*?(?<![一-鿿])" + re.escape(name) + r"(?![一-鿿])[^*]*?\*\*", re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*[（(]\s*[^）)]*?" + eng_pat + r"[^）)]*?\s*[）)]", re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*[（(][^）)]+[）)]\s*" + eng_pat, re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*" + eng_pat, re.IGNORECASE),
        ]
        found = False
        for pattern in patterns:
            m = pattern.search(section_text)
            if m:
                start = m.start()
                if start >= 2 and section_text[start - 2:start] == "**":
                    start -= 2
                positions.append((start, entry, m.group(0)))
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


def append_entry(path: Path, marker: str, heading: str, source_annotation: str, block: str, report: dict, item_type: str, item_name: str, target_rel: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_preserve(path, heading.split("\n")[0].split("（")[0].strip() + "\n\n", "\n")
    existing, _ = read_text_preserve(path)
    if marker in existing:
        report["skipped"].append(f"{item_type}已存在: {item_name}")
        return
    entry = f"\n{marker}\n{heading}\n{source_annotation}\n{block}\n\n"
    append_to_file(path, entry)
    report["merged"].append({"type": item_type, "name": item_name, "target": target_rel})


# ========== 1. 动物伙伴变体 ==========

ANIMAL_COMPANION_VARIANTS = [
    {"name": "元素伙伴", "english": "Elemental Companion", "source_file": "动物伙伴变体.md"},
]


def process_animal_companion_variants(report: dict) -> None:
    target_path = ORG_DIR / "规则" / "位面行者手册PHH_动物伙伴变体.md"

    text = (SRC_DIR / "动物伙伴变体.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    blocks = split_section_by_entries(text, ANIMAL_COMPANION_VARIANTS)

    for item in ANIMAL_COMPANION_VARIANTS:
        block = blocks.get(item["name"])
        if block is None:
            report["warnings"].append(f"未找到动物伙伴变体块: {item['name']}")
            continue
        marker = make_hidden_marker(item["source_file"], item["name"])
        append_entry(
            target_path,
            marker,
            f"## {item['name']}（{item['english']}）",
            make_source_annotation(item["source_file"], "动物伙伴变体"),
            block,
            report,
            "动物伙伴变体",
            item["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 2. 幻灵基础形态/亚种 ==========

EIDOLON_SUBTYPES = [
    {"name": "叙中人", "english": "Storykin", "source_file": "幻灵基础形态.md"},
    {"name": "虚空", "english": "Void", "source_file": "幻灵基础形态.md"},
    {"name": "星界", "english": "Astral", "source_file": "幻灵基础形态.md"},
    {"name": "御衡者", "english": "Aeon", "source_file": "幻灵基础形态.md"},
    {"name": "辐光", "english": "Radiant", "source_file": "幻灵基础形态.md"},
]


def process_eidolon_subtypes(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "掉链子（Unchained）" / "召唤师" / "page_247.md"
    if not target_path.exists():
        report["warnings"].append(f"目标文件不存在，跳过幻灵亚种: {target_path}")
        return

    existing, _ = read_text_preserve(target_path)

    text = (SRC_DIR / "幻灵基础形态.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    blocks = split_section_by_entries(text, EIDOLON_SUBTYPES)

    for item in EIDOLON_SUBTYPES:
        names_to_check = [item["name"], item["english"]]
        if any(n in existing for n in names_to_check):
            report["skipped"].append(f"幻灵亚种已存在: {item['name']}")
            continue

        block = blocks.get(item["name"])
        if block is None:
            report["warnings"].append(f"未找到幻灵亚种块: {item['name']}")
            continue
        marker = make_hidden_marker(item["source_file"], item["name"])
        append_entry(
            target_path,
            marker,
            f"## {item['name']}（{item['english']}）〔幻灵亚种〕",
            make_source_annotation(item["source_file"], "幻灵基础形态"),
            block,
            report,
            "幻灵亚种",
            item["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 3. 魔宠变体 ==========

FAMILIAR_VARIANTS = [
    {"name": "元素魔宠", "english": "Elemental Familiar", "source_file": "魔宠变体1.md"},
]


def process_familiar_variants(report: dict) -> None:
    target_path = ORG_DIR / "规则" / "位面行者手册PHH_魔宠变体.md"

    text = (SRC_DIR / "魔宠变体1.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    blocks = split_section_by_entries(text, FAMILIAR_VARIANTS)

    for item in FAMILIAR_VARIANTS:
        block = blocks.get(item["name"])
        if block is None:
            report["warnings"].append(f"未找到魔宠变体块: {item['name']}")
            continue
        marker = make_hidden_marker(item["source_file"], item["name"])
        append_entry(
            target_path,
            marker,
            f"## {item['name']}（{item['english']}）",
            make_source_annotation(item["source_file"], "魔宠变体"),
            block,
            report,
            "魔宠变体",
            item["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 4. 物品（位面之力施法组件） ==========

ITEMS = [
    {"name": "协同水晶", "english": "Cooperation Crystal", "source_file": "物品32.md"},
    {"name": "炎之碎片", "english": "Fire Fragment", "source_file": "物品32.md"},
    {"name": "天堂石英", "english": "Heavenly Quartz", "source_file": "物品32.md"},
    {"name": "虚空碎晶", "english": "Void Shard", "source_file": "物品32.md"},
    {"name": "妙想之星", "english": "Whimsy Star", "source_file": "物品32.md"},
]


def process_items(report: dict) -> None:
    target_path = ORG_DIR / "装备_魔法物品" / "位面行者手册PHH_物品.md"

    text = (SRC_DIR / "物品32.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    blocks = split_section_by_entries(text, ITEMS)

    for item in ITEMS:
        block = blocks.get(item["name"])
        if block is None:
            report["warnings"].append(f"未找到物品块: {item['name']}")
            continue
        marker = make_hidden_marker(item["source_file"], item["name"])
        append_entry(
            target_path,
            marker,
            f"## {item['name']}（{item['english']}）",
            make_source_annotation(item["source_file"], "物品"),
            block,
            report,
            "物品",
            item["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 5. 元素裔亚种 ==========

ELEMENTAL_HERITAGES = [
    {"name": "水晶 土元素裔", "english": "Crystal Oread", "source_file": "元素裔亚种.md"},
    {"name": "金属 土元素裔", "english": "Metal Oread", "source_file": "元素裔亚种.md"},
    {"name": "蒸汽 水元素裔", "english": "Vapor Undine", "source_file": "元素裔亚种.md"},
    {"name": "冰晶 水元素裔", "english": "Frost Undine", "source_file": "元素裔亚种.md"},
    {"name": "烟云 风元素裔", "english": "Fume Sylph", "source_file": "元素裔亚种.md"},
    {"name": "闪电 风元素裔", "english": "Lightning Sylph", "source_file": "元素裔亚种.md"},
    {"name": "岩浆 火元素裔", "english": "Magma Ifrit", "source_file": "元素裔亚种.md"},
    {"name": "光能 火元素裔", "english": "Solar Ifrit", "source_file": "元素裔亚种.md"},
]


def process_elemental_heritages(report: dict) -> None:
    target_path = ORG_DIR / "种族" / "常见种族" / "元素裔" / "位面行者手册PHH_元素裔亚种.md"

    text = (SRC_DIR / "元素裔亚种.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    blocks = split_section_by_entries(text, ELEMENTAL_HERITAGES)

    for item in ELEMENTAL_HERITAGES:
        block = blocks.get(item["name"])
        if block is None:
            report["warnings"].append(f"未找到元素裔亚种块: {item['name']}")
            continue
        marker = make_hidden_marker(item["source_file"], item["name"])
        append_entry(
            target_path,
            marker,
            f"## {item['name']}（{item['english']}）",
            make_source_annotation(item["source_file"], "元素裔亚种"),
            block,
            report,
            "元素裔亚种",
            item["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 6. 职业变体 ==========

ARCHETYPES = [
    {"name": "混沌骑士", "english": "Chaos Knight", "class": "圣武士", "source_file": "职业变体/page_1605.md"},
    {"name": "裂空枪手", "english": "Planar Rifter", "class": "铳士", "source_file": "职业变体/铳士.md"},
    {"name": "位面谐律人", "english": "Planar Harmonizer", "class": "秘学士", "source_file": "职业变体/秘学士.md"},
]


def process_archetypes(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "位面行者手册PHH_变体.md"

    for arc in ARCHETYPES:
        text = (SRC_DIR / arc["source_file"]).read_text(encoding="utf-8")
        text = merge_section_heading_lines(text)
        text = merge_crossline_bold(text)
        text = clean_translator_url(text)
        text = clean_leading_image(text)

        blocks = split_section_by_entries(text, [arc])
        block = blocks.get(arc["name"])
        if block is None:
            report["warnings"].append(f"未找到变体块: {arc['name']}")
            continue
        marker = make_hidden_marker(arc["source_file"], arc["name"])
        append_entry(
            target_path,
            marker,
            f"## {arc['name']}（{arc['english']}）〔{arc['class']}变体〕",
            make_source_annotation(arc["source_file"], "职业变体"),
            block,
            report,
            "变体",
            arc["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 7. 专长 ==========

FEATS = [
    {"name": "位面训导", "english": "Planar Mentor", "source_file": "专长12.md"},
    {"name": "进阶位面训导", "english": "Improved Planar Mentor", "source_file": "专长12.md"},
    {"name": "高等位面训导", "english": "Greater Planar Mentor", "source_file": "专长12.md"},
    {"name": "惩戒召唤", "english": "Retributive Summoning", "source_file": "专长12.md"},
]


def process_feats(report: dict) -> None:
    target_path = ORG_DIR / "专长" / "位面行者手册PHH_专长.md"

    text = (SRC_DIR / "专长12.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    blocks = split_section_by_entries(text, FEATS)

    for feat in FEATS:
        block = blocks.get(feat["name"])
        if block is None:
            report["warnings"].append(f"未找到专长块: {feat['name']}")
            continue
        marker = make_hidden_marker(feat["source_file"], feat["name"])
        append_entry(
            target_path,
            marker,
            f"## {feat['name']}（{feat['english']}）",
            make_source_annotation(feat["source_file"], "专长"),
            block,
            report,
            "专长",
            feat["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 报告 ==========

def write_report(report: dict) -> None:
    lines = [f"# {SOURCE_BOOK} 整理报告\n", f"\n生成时间：{datetime.now().isoformat()}\n"]
    lines.append("\n## 整理内容\n")
    for item in report["merged"]:
        lines.append(f"- **{item['type']}**：{item['name']} → `{item['target']}`")
    lines.append("\n## 跳过项\n")
    for item in report["skipped"]:
        lines.append(f"- {item}")
    if report["warnings"]:
        lines.append("\n## 警告\n")
        for item in report["warnings"]:
            lines.append(f"- {item}")
    else:
        lines.append("\n## 警告\n\n无\n")
    write_text_preserve(REPORT_PATH, "\n".join(lines))


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}
    process_animal_companion_variants(report)
    process_eidolon_subtypes(report)
    process_familiar_variants(report)
    process_items(report)
    process_elemental_heritages(report)
    process_archetypes(report)
    process_feats(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
