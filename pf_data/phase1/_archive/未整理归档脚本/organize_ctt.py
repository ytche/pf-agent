#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 近战战术工具箱（Melee Tactics Toolbox）CTT 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/近战战术工具箱
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/近战战术工具箱"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "CTT_reorganization_report.md"

SOURCE_BOOK = "近战战术工具箱（Melee Tactics Toolbox）CTT"
SOURCE_BOOK_SHORT = "CTT"


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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 近战战术工具箱CTT{l3_part}"


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
    lines = text.splitlines()
    while lines and re.match(r"^\s*!\[.*\]\(.*\)\s*$", lines[0].strip()):
        lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return "\n".join(lines)


def extract_block_whole_file(text: str) -> str:
    text = clean_translator_url(text)
    text = clean_leading_image(text)
    return text.strip()


def find_entry_headings(section_text: str, entries: list[dict]) -> list[tuple[int, dict, str]]:
    positions = []
    for entry in entries:
        name = entry["name"]
        english = entry.get("english", "")
        eng_pat = re.escape(english).replace(r"\ ", r"\s+")
        patterns = [
            re.compile(r"(?:^|\n)\s*\*\*[^*]*?(?<![一-鿿])" + re.escape(name) + r"(?![一-鿿])[^*]*?\*\*", re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*[（(]\s*[^）)]*?" + eng_pat + r"[^）)]*?\s*[）)]", re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*[（(][^）)]+[）)]\s*" + eng_pat, re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*" + eng_pat, re.IGNORECASE),
        ]
        found = False
        for pattern in patterns:
            m = pattern.search(section_text)
            if m:
                start = m.start()
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
        write_text_preserve(path, "")
    existing, _ = read_text_preserve(path)
    if marker in existing:
        report["skipped"].append(f"{item_type}已存在: {item_name}")
        return
    entry = f"\n{marker}\n{heading}\n{source_annotation}\n{block}\n\n"
    append_to_file(path, entry)
    report["merged"].append({"type": item_type, "name": item_name, "target": target_rel})


def create_aggregation_file(path: Path, title: str, source_file: str, entries: list[tuple[str, str, str, str]], report: dict, item_type: str) -> None:
    """新建源书聚合文件；若文件已存在则跳过整本书写。"""
    if path.exists() and make_hidden_marker(source_file, "__aggregate__") in path.read_text(encoding="utf-8"):
        report["skipped"].append(f"{item_type}聚合文件已存在: {path.name}")
        return
    parts = [f"# {title}", "", make_hidden_marker(source_file, "__aggregate__"), ""]
    for marker, heading, source_annotation, block in entries:
        parts.append(marker)
        parts.append(heading)
        parts.append(source_annotation)
        parts.append("")
        parts.append(block)
        parts.append("")
        parts.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_preserve(path, "\n".join(parts), "\n")
    for _, heading, _, _ in entries:
        report["merged"].append({"type": item_type, "name": heading.lstrip("#").split("（")[0].strip(), "target": str(path.relative_to(ORG_DIR))})


def aggregate_whole_page(target_path: Path, title: str, source_file: str, heading: str, l3: str, report: dict, item_type: str) -> None:
    """将整页内容作为一个条目的源书聚合文件。"""
    src_path = SRC_DIR / source_file
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    aggregate_marker = make_hidden_marker(source_file, "__aggregate__")
    entry_marker = make_hidden_marker(source_file, heading.lstrip("# ").strip())
    entries = [(
        entry_marker,
        heading,
        make_source_annotation(source_file, l3),
        text.strip(),
    )]
    create_aggregation_file(target_path, title, source_file, entries, report, item_type)


# ========== 1. 吟游诗人传世名作 ==========

def process_masterpiece(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "传世名作汇总.md"
    src_path = SRC_DIR / "page_425.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    # 去掉开头的 "吟游诗人传世名作" 标题行，因为目标文件已有该章节
    lines = text.splitlines()
    if lines and "传世名作" in lines[0]:
        lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    block = "\n".join(lines).strip()

    marker = make_hidden_marker("page_425.md", "义勇军进行曲")
    existing = target_path.read_text(encoding="utf-8") if target_path.exists() else ""

    # 已有内容（无论 MTT 还是 CTT 标记）均视为存在；传世名作汇总中该名作已存在
    if marker in existing or "义勇军进行曲" in existing:
        report["skipped"].append("传世名作已存在: 义勇军进行曲")
        return

    heading = "## 义勇军进行曲（Battle Song of the People's Revolt）"
    entry = f"\n{marker}\n{heading}\n{make_source_annotation('page_425.md', '吟游诗人传世名作')}\n{block}\n\n"
    append_to_file(target_path, entry)
    report["merged"].append({"type": "传世名作", "name": "义勇军进行曲", "target": str(target_path.relative_to(ORG_DIR))})


# ========== 2. 新武器 ==========

def process_weapons(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "近战战术工具箱CTT_武器.md",
        "近战战术工具箱 CTT 武器",
        "page_426.md",
        "## 武器",
        "武器",
        report,
        "武器",
    )


# ========== 3. 规则详解 ==========

def process_rules(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "近战战术工具箱CTT_规则详解.md",
        "近战战术工具箱 CTT 规则详解",
        "page_431.md",
        "## 规则详解",
        "规则详解",
        report,
        "规则",
    )


# ========== 4. 魔法物品 ==========

def process_magic_items(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "近战战术工具箱CTT_魔法护甲.md",
        "近战战术工具箱 CTT 魔法护甲",
        "魔法物品/page_427.md",
        "## 魔法护甲",
        "魔法物品 → 魔法护甲",
        report,
        "魔法护甲",
    )
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "近战战术工具箱CTT_魔法武器.md",
        "近战战术工具箱 CTT 魔法武器",
        "魔法物品/page_428.md",
        "## 魔法武器",
        "魔法物品 → 魔法武器",
        report,
        "魔法武器",
    )
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "近战战术工具箱CTT_特殊附魔.md",
        "近战战术工具箱 CTT 特殊附魔",
        "魔法物品/page_429.md",
        "## 特殊附魔",
        "魔法物品 → 特殊附魔",
        report,
        "特殊附魔",
    )
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "近战战术工具箱CTT_奇物.md",
        "近战战术工具箱 CTT 奇物",
        "魔法物品/page_430.md",
        "## 奇物",
        "魔法物品 → 奇物",
        report,
        "奇物",
    )


# ========== 5. 冒险装备 ==========

def process_equipment(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "近战战术工具箱CTT_装备.md",
        "近战战术工具箱 CTT 装备",
        "装备2.md",
        "## 冒险装备",
        "冒险装备",
        report,
        "装备",
    )


# ========== 6. 职业变体 ==========

ARCHETYPES = [
    {"source_file": "变体/page_432.md", "class": "骑将", "target": ORG_DIR / "职业" / "基础职业" / "骑将" / "page_74.md", "names": ["守备官"], "english": "Castellan"},
    {"source_file": "变体/page_433.md", "class": "战士", "target": ORG_DIR / "职业" / "核心职业" / "战士" / "page_49.md", "names": ["教官"], "english": "Drill Sergeant"},
    {"source_file": "变体/page_434.md", "class": "血脉狂怒者", "target": ORG_DIR / "职业" / "混合职业" / "血脉狂怒者" / "page_98.md", "names": ["血暴铁拳"], "english": "Bloody-Knuckled Rowdy"},
    {"source_file": "变体/page_435.md", "class": "盗贼", "target": ORG_DIR / "职业" / "核心职业" / "盗贼" / "page_22.md", "names": ["浪荡凶徒"], "english": "Makeshift Scrapper"},
]


def process_archetypes(report: dict) -> None:
    for arc in ARCHETYPES:
        src_path = SRC_DIR / arc["source_file"]
        target_path = arc["target"]
        text = src_path.read_text(encoding="utf-8")
        text = merge_section_heading_lines(text)
        text = merge_crossline_bold(text)
        text = clean_translator_url(text)
        text = clean_leading_image(text)

        marker = make_hidden_marker(arc["source_file"], "/".join(arc["names"]))
        existing = target_path.read_text(encoding="utf-8") if target_path.exists() else ""

        # 已有内容（无论 MTT 还是 CTT 标记）均视为存在
        title_pattern = re.compile(re.escape(arc["names"][0]), re.IGNORECASE)
        if marker in existing or title_pattern.search(existing):
            report["skipped"].append(f"职业变体已存在: {arc['class']} {'/'.join(arc['names'])}（源文件中标注为{SOURCE_BOOK_SHORT}，但目标页已含同名条目）")
            continue

        heading = f"## {'/'.join(arc['names'])}（{arc['english']}）【{SOURCE_BOOK_SHORT} {arc['class']}变体】"
        entry = f"\n{marker}\n{heading}\n{make_source_annotation(arc['source_file'], '变体')}\n{text.strip()}\n\n"
        append_to_file(target_path, entry)
        report["merged"].append({
            "type": f"{arc['class']}变体",
            "name": "、".join(arc["names"]),
            "target": str(target_path.relative_to(ORG_DIR)),
        })


# ========== 报告 ==========

def write_report(report: dict) -> None:
    lines = [f"# {SOURCE_BOOK} 整理报告\n", f"\n生成时间：{datetime.now().isoformat()}\n"]
    lines.append("\n## 整理内容\n")
    for item in report["merged"]:
        lines.append(f"- **{item['type']}**：{item['name']} → `{item['target']}`")
    lines.append("\n## 跳过项\n")
    if report["skipped"]:
        for item in report["skipped"]:
            lines.append(f"- {item}")
    else:
        lines.append("\n无\n")
    if report["warnings"]:
        lines.append("\n## 警告\n")
        for item in report["warnings"]:
            lines.append(f"- {item}")
    else:
        lines.append("\n## 警告\n\n无\n")
    write_text_preserve(REPORT_PATH, "\n".join(lines))


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}
    process_masterpiece(report)
    process_weapons(report)
    process_rules(report)
    process_magic_items(report)
    process_equipment(report)
    process_archetypes(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
