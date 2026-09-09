#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 阴招战术工具箱（Dirty Tactics Toolbox）DTT 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/阴招战术工具箱
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/阴招战术工具箱"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "DTT_reorganization_report.md"

SOURCE_BOOK = "阴招战术工具箱（Dirty Tactics Toolbox）DTT"
SOURCE_BOOK_SHORT = "DTT"


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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 阴招战术工具箱DTT{l3_part}"


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


def split_at_heading(text: str, heading_pattern: str) -> tuple[str, str]:
    """将文本在第一个匹配 heading_pattern 的标题处切分为 (前, 后)。"""
    pattern = re.compile(heading_pattern, re.IGNORECASE)
    m = pattern.search(text)
    if not m:
        return text, ""
    return text[:m.start()].strip(), text[m.start():].strip()


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

    entry_marker = make_hidden_marker(source_file, heading.lstrip("# ").strip())
    entries = [(
        entry_marker,
        heading,
        make_source_annotation(source_file, l3),
        text.strip(),
    )]
    create_aggregation_file(target_path, title, source_file, entries, report, item_type)


# ========== 1. 诡术种族特性（整页聚合） ==========

def process_racial_options(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "阴招战术工具箱DTT_诡术种族特性.md",
        "阴招战术工具箱 DTT 诡术种族特性",
        "page_451.md",
        "## 诡术种族特性",
        "诡术种族特性",
        report,
        "种族特性",
    )


# ========== 2. 职业变体 ==========

ARCHETYPES = [
    {"source_file": "变体_职业选项/page_454.md", "class": "盗贼", "target": ORG_DIR / "职业" / "核心职业" / "盗贼" / "page_22.md", "names": ["剪径贼"], "english": "Waylayer"},
    {"source_file": "变体_职业选项/page_456.md", "class": "牧师", "target": ORG_DIR / "职业" / "核心职业" / "牧师" / "page_41.md", "names": ["阿斯莫迪斯律师"], "english": "Asmodean Advocate"},
    {"source_file": "变体_职业选项/page_458.md", "class": "审判者", "target": ORG_DIR / "职业" / "基础职业" / "审判者" / "page_78.md", "names": ["秘密抹杀者"], "english": "Secret Sanctifier"},
    {"source_file": "变体_职业选项/page_457.md", "class": "武僧", "target": ORG_DIR / "职业" / "核心职业" / "武僧" / "page_52.md", "names": ["镰切僧"], "english": "Monk of the Mantis"},
    {"source_file": "变体_职业选项/page_459.md", "class": "德鲁伊", "target": ORG_DIR / "职业" / "核心职业" / "德鲁伊" / "page_45.md", "names": ["海怪之主"], "english": "Kraken Caller"},
]


def process_simple_archetypes(report: dict) -> None:
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


# ========== 3. 炼金术师变体 + 剧毒炸弹发现 ==========

def process_alchemist(report: dict) -> None:
    src_path = SRC_DIR / "变体_职业选项" / "page_453.md"
    target_path = ORG_DIR / "职业" / "基础职业" / "炼金术师" / "page_71.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    # 切分变体与发现
    archetype_text, discovery_text = split_at_heading(text, r"新炼金术士发现")

    # 3.1 制毒师变体
    arc_marker = make_hidden_marker("变体_职业选项/page_453.md", "制毒师")
    existing = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    if arc_marker in existing or "制毒师" in existing:
        report["skipped"].append("职业变体已存在: 炼金术师 制毒师（源文件中标注为DTT，目标页已含同名条目）")
    else:
        heading = "## 制毒师（Toxicant）【DTT 炼金术师变体】"
        entry = f"\n{arc_marker}\n{heading}\n{make_source_annotation('变体_职业选项/page_453.md', '变体')}\n{archetype_text.strip()}\n\n"
        append_to_file(target_path, entry)
        report["merged"].append({"type": "炼金术师变体", "name": "制毒师", "target": str(target_path.relative_to(ORG_DIR))})

    # 3.2 剧毒炸弹发现
    if not discovery_text:
        report["warnings"].append("未能在 page_453.md 中找到 新炼金术士发现 分段")
        return
    disc_marker = make_hidden_marker("变体_职业选项/page_453.md", "剧毒炸弹")
    if disc_marker in existing or "剧毒炸弹" in existing:
        report["skipped"].append("炼金术师科研发现已存在: 剧毒炸弹")
    else:
        heading = "## 剧毒炸弹（Poisoned Explosive）【DTT 炼金术师科研发现】"
        entry = f"\n{disc_marker}\n{heading}\n{make_source_annotation('变体_职业选项/page_453.md', '炼金术师科研发现')}\n{discovery_text.strip()}\n\n"
        append_to_file(target_path, entry)
        report["merged"].append({"type": "炼金术师科研发现", "name": "剧毒炸弹", "target": str(target_path.relative_to(ORG_DIR))})


# ========== 4. 野蛮人变体 + 新狂暴之力 ==========

def process_barbarian(report: dict) -> None:
    src_path = SRC_DIR / "变体_职业选项" / "page_455.md"
    archetype_target = ORG_DIR / "职业" / "核心职业" / "野蛮人" / "page_35.md"
    rage_target = ORG_DIR / "职业" / "核心职业" / "野蛮人" / "page_36.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    # 切分变体与狂暴之力
    archetype_text, rage_text = split_at_heading(text, r"新狂暴之力")

    # 4.1 恶党变体
    arc_marker = make_hidden_marker("变体_职业选项/page_455.md", "恶党")
    existing = archetype_target.read_text(encoding="utf-8") if archetype_target.exists() else ""
    if arc_marker in existing or "恶党" in existing:
        report["skipped"].append("职业变体已存在: 野蛮人 恶党（源文件中标注为DTT，目标页已含同名条目）")
    else:
        heading = "## 恶党（Untamed Rager）【DTT 野蛮人变体】"
        entry = f"\n{arc_marker}\n{heading}\n{make_source_annotation('变体_职业选项/page_455.md', '变体')}\n{archetype_text.strip()}\n\n"
        append_to_file(archetype_target, entry)
        report["merged"].append({"type": "野蛮人变体", "name": "恶党", "target": str(archetype_target.relative_to(ORG_DIR))})

    # 4.2 新狂暴之力
    if not rage_text:
        report["warnings"].append("未能在 page_455.md 中找到 新狂暴之力 分段")
        return
    rage_marker = make_hidden_marker("变体_职业选项/page_455.md", "DTT新狂暴之力")
    existing_rage = rage_target.read_text(encoding="utf-8") if rage_target.exists() else ""
    if rage_marker in existing_rage or "奇毒" in existing_rage:
        report["skipped"].append("狂暴之力已存在: DTT 阴招战术工具箱新狂暴之力")
    else:
        heading = "## 阴招战术工具箱 DTT 新狂暴之力"
        entry = f"\n{rage_marker}\n{heading}\n{make_source_annotation('变体_职业选项/page_455.md', '狂暴之力')}\n{rage_text.strip()}\n\n"
        append_to_file(rage_target, entry)
        report["merged"].append({"type": "狂暴之力", "name": "阴招战术工具箱 DTT 新狂暴之力", "target": str(rage_target.relative_to(ORG_DIR))})


# ========== 5. 毒药、附魔、刺青 ==========

def process_poison(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "阴招战术工具箱DTT_毒药.md",
        "阴招战术工具箱 DTT 毒药",
        "毒药1.md",
        "## 红泪",
        "毒药",
        report,
        "毒药",
    )


def process_armor_enchantment(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "阴招战术工具箱DTT_防具附魔.md",
        "阴招战术工具箱 DTT 防具附魔",
        "防具附魔5.md",
        "## 防具附魔",
        "防具附魔",
        report,
        "防具附魔",
    )


def process_tattoos(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "阴招战术工具箱DTT_魔法刺青.md",
        "阴招战术工具箱 DTT 魔法刺青",
        "魔法刺青.md",
        "## 魔法刺青",
        "魔法刺青",
        report,
        "魔法刺青",
    )


def process_weapon_enchantments(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "阴招战术工具箱DTT_武器附魔.md",
        "阴招战术工具箱 DTT 武器附魔",
        "武器附魔2.md",
        "## 武器附魔",
        "武器附魔",
        report,
        "武器附魔",
    )


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
    process_racial_options(report)
    process_simple_archetypes(report)
    process_alchemist(report)
    process_barbarian(report)
    process_poison(report)
    process_armor_enchantment(report)
    process_tattoos(report)
    process_weapon_enchantments(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
