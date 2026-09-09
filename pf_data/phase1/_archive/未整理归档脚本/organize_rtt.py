#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 远程战术工具箱（Ranged Tactics Toolbox）RTT 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/远程战术工具箱
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/远程战术工具箱"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "RTT_reorganization_report.md"

SOURCE_BOOK = "远程战术工具箱（Ranged Tactics Toolbox）RTT"
SOURCE_BOOK_SHORT = "RTT"


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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 远程战术工具箱RTT{l3_part}"


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


def append_whole_page(target_path: Path, source_file: str, heading: str, l3: str, report: dict, item_type: str, item_name: str) -> None:
    """将整页内容作为一个条目追加到已有文件。"""
    src_path = SRC_DIR / source_file
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    marker = make_hidden_marker(source_file, item_name)
    entry = f"\n{marker}\n{heading}\n{make_source_annotation(source_file, l3)}\n{text.strip()}\n\n"
    append_to_file(
        target_path,
        entry,
        report,
        item_type,
        item_name,
        str(target_path.relative_to(ORG_DIR)),
    )


# ========== 1. 新远程武器 ==========

def process_weapons(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "远程战术工具箱RTT_武器.md",
        "远程战术工具箱 RTT 武器",
        "page_468.md",
        "## 新远程武器",
        "武器",
        report,
        "武器",
    )


# ========== 2. 游荡者天赋 ==========

def process_rogue_talents(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "核心职业" / "盗贼" / "page_62.md"
    src_path = SRC_DIR / "变体_职业选项" / "page_465.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    marker = make_hidden_marker("变体_职业选项/page_465.md", "RTT游荡者天赋")
    existing = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    if marker in existing or "投弹手" in existing:
        report["skipped"].append("盗贼天赋已存在: RTT 远程战术工具箱游荡者天赋")
        return

    heading = "## 远程战术工具箱 RTT 游荡者天赋"
    entry = f"\n{marker}\n{heading}\n{make_source_annotation('变体_职业选项/page_465.md', '游荡者天赋')}\n{text.strip()}\n\n"
    append_to_file(target_path, entry)
    report["merged"].append({"type": "盗贼天赋", "name": "远程战术工具箱 RTT 游荡者天赋", "target": str(target_path.relative_to(ORG_DIR))})


# ========== 3. 新游侠陷阱 ==========

def process_ranger_traps(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "远程战术工具箱RTT_游侠陷阱.md",
        "远程战术工具箱 RTT 游侠陷阱",
        "变体_职业选项/page_466.md",
        "## 新游侠陷阱",
        "职业选项 → 游侠陷阱",
        report,
        "游侠陷阱",
    )


# ========== 4. 炼金物品 ==========

def process_alchemical_items(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "远程战术工具箱RTT_炼金物品.md",
        "远程战术工具箱 RTT 炼金物品",
        "炼金物品.md",
        "## 炼金物品",
        "炼金物品",
        report,
        "炼金物品",
    )


# ========== 5. 魔法物品 ==========

def process_magic_items(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "远程战术工具箱RTT_魔法武器.md",
        "远程战术工具箱 RTT 魔法武器",
        "魔法物品/page_469.md",
        "## 魔法武器",
        "魔法物品 → 魔法武器",
        report,
        "魔法武器",
    )
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "远程战术工具箱RTT_魔法弹药.md",
        "远程战术工具箱 RTT 魔法弹药",
        "魔法物品/page_470.md",
        "## 魔法弹药",
        "魔法物品 → 魔法弹药",
        report,
        "魔法弹药",
    )
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "远程战术工具箱RTT_武器特殊附魔.md",
        "远程战术工具箱 RTT 武器特殊附魔",
        "魔法物品/page_471.md",
        "## 武器特殊附魔",
        "魔法物品 → 武器特殊附魔",
        report,
        "武器特殊附魔",
    )
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "远程战术工具箱RTT_奇物.md",
        "远程战术工具箱 RTT 奇物",
        "魔法物品/page_472.md",
        "## 奇物",
        "魔法物品 → 奇物",
        report,
        "奇物",
    )


# ========== 6. 职业变体（大多已存在） ==========

ARCHETYPES = [
    {"source_file": "变体_职业选项/page_461.md", "class": "吟游诗人", "target": ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "page_38.md", "names": ["杂耍者"], "english": "Juggler"},
    {"source_file": "变体_职业选项/page_462.md", "class": "武僧", "target": ORG_DIR / "职业" / "核心职业" / "武僧" / "page_52.md", "names": ["远战武僧"], "english": "Far Strike Monk"},
    {"source_file": "变体_职业选项/page_463.md", "class": "野蛮人", "target": ORG_DIR / "职业" / "核心职业" / "野蛮人" / "page_35.md", "names": ["原始猎手"], "english": "Primal Hunter"},
    {"source_file": "变体_职业选项/page_464.md", "class": "游侠", "target": ORG_DIR / "职业" / "核心职业" / "游侠" / "page_58.md", "names": ["箭艺师"], "english": "Toxophilite"},
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

        title_pattern = re.compile(re.escape(arc["names"][0]), re.IGNORECASE)
        if marker in existing or title_pattern.search(existing):
            report["skipped"].append(f"职业变体已存在: {arc['class']} {'/'.join(arc['names'])}（源文件中标注为{SOURCE_BOOK_SHORT}，目标页已含同名条目）")
            continue

        heading = f"## {'/'.join(arc['names'])}（{arc['english']}）【{SOURCE_BOOK_SHORT} {arc['class']}变体】"
        entry = f"\n{marker}\n{heading}\n{make_source_annotation(arc['source_file'], '变体')}\n{text.strip()}\n\n"
        append_to_file(target_path, entry)
        report["merged"].append({
            "type": f"{arc['class']}变体",
            "name": "、".join(arc["names"]),
            "target": str(target_path.relative_to(ORG_DIR)),
        })


# ========== 7. 魔战士奥能（大多已存在） ==========

def process_magus_arcana(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "基础职业" / "魔战士" / "page_83.md"
    src_path = SRC_DIR / "变体_职业选项" / "page_467.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    marker = make_hidden_marker("变体_职业选项/page_467.md", "RTT魔战士奥能")
    existing = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    if marker in existing or "力池射线" in existing:
        report["skipped"].append("魔战士奥能已存在: RTT 远程战术工具箱魔战士奥能")
        return

    heading = "## 远程战术工具箱 RTT 魔战士奥能"
    entry = f"\n{marker}\n{heading}\n{make_source_annotation('变体_职业选项/page_467.md', '魔战士奥能')}\n{text.strip()}\n\n"
    append_to_file(target_path, entry)
    report["merged"].append({"type": "魔战士奥能", "name": "远程战术工具箱 RTT 魔战士奥能", "target": str(target_path.relative_to(ORG_DIR))})


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
    process_weapons(report)
    process_rogue_talents(report)
    process_ranger_traps(report)
    process_alchemical_items(report)
    process_magic_items(report)
    process_archetypes(report)
    process_magus_arcana(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
