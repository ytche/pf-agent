#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 巨龙之遗（Legacy of Dragons）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/巨龙之遗LoD
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/巨龙之遗LoD"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "LegacyOfDragons_reorganization_report.md"

SOURCE_BOOK = "巨龙之遗（Legacy of Dragons）"
SOURCE_BOOK_SHORT = "巨龙之遗LoD"


def write_text_preserve(path: Path, text: str, line_ending: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\n", line_ending), encoding="utf-8")


def detect_line_ending(path: Path) -> str:
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 4096))
        tail = f.read()
    if b"\r\n" in tail:
        return "\r\n"
    return "\n"


def safe_append_to_file(
    path: Path,
    marker: str,
    heading: str,
    source_annotation: str,
    block: str,
) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    with open(path, "rb") as f:
        content = f.read()
    if marker.encode("utf-8") in content:
        raise FileExistsError(f"{path} already contains {marker}")
    le = detect_line_ending(path)
    if not content.endswith(b"\n"):
        suffix = le * 2
    elif content.endswith(le.encode("utf-8")):
        if len(content) >= len(le.encode("utf-8")) * 2 and content.endswith(
            (le * 2).encode("utf-8")
        ):
            suffix = ""
        else:
            suffix = le
    else:
        suffix = le * 2
    entry = f"{marker}\n{heading}\n{source_annotation}\n{block}\n\n"
    entry = entry.replace("\n", le)
    with open(path, "ab") as f:
        f.write(suffix.encode("utf-8"))
        f.write(entry.encode("utf-8"))


def make_source_annotation(source_file: str, l3: str = "") -> str:
    l3_part = f" → {l3}" if l3 else ""
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → {SOURCE_BOOK_SHORT}{l3_part}"


def make_hidden_marker(source_file: str, entry_name: str) -> str:
    return f"<!-- {SOURCE_BOOK_SHORT}-source:{source_file}:{entry_name} -->"


def remove_image_links(text: str) -> str:
    return re.sub(r"!\[.*?\]\(.*?\)", "", text)


def clean_translator_url(text: str) -> str:
    lines = text.splitlines()
    while lines:
        first = lines[0].strip()
        if (
            first.startswith("[http")
            or first.startswith("**[http")
            or re.match(r"^https?://", first)
            or re.match(r"^\*\*\[https?://.*\]\(.*\)\*\*$", first)
            or "整理者" in first
            or "译者" in first
            or first == ""
        ):
            lines = lines[1:]
        else:
            break
    return "\n".join(lines)


def clean_leading_image(text: str) -> str:
    lines = text.splitlines()
    while lines and re.match(r"^\s*!\[.*\]\(.*\)\s*$", lines[0].strip()):
        lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return "\n".join(lines)


def clean_aggregate(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = remove_image_links(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)
    return text


def strip_trailing_artifacts(block: str) -> str:
    lines = block.splitlines()
    while lines and (
        lines[-1].strip() == ""
        or re.match(r"^\*+$", lines[-1].strip())
        or re.match(r"^\|", lines[-1].strip())
        or re.match(r"^\|?\s*---", lines[-1].strip())
    ):
        lines.pop()
    return "\n".join(lines)


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


def _normalize_stars(text: str) -> str:
    text = re.sub(
        r"\*\*([^*]+?)\*\*\s*[（(]\s*\*([^*]+?)\*\s*[）)]",
        r"**\1（\2）**",
        text,
    )
    text = re.sub(
        r"\*\*([^*（）()]+?)\s*[（(]([^）()]+)[）)]\*\*",
        r"**\1（\2）**",
        text,
    )
    return text


def process_aggregate(
    report: dict,
    src_name: str,
    l3: str,
    entry_name: str,
    target_path: Path,
    target_title: str,
    heading: str,
    block: str | None = None,
) -> None:
    if block is None:
        block = clean_aggregate((SRC_DIR / src_name).read_text(encoding="utf-8"))

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, f"# {target_title}\n\n", "\n")

    marker = make_hidden_marker(src_name, entry_name)
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append(f"{l3}已存在: {src_name}:{entry_name}")
        return

    block = strip_trailing_artifacts(block)
    safe_append_to_file(target_path, marker, heading, make_source_annotation(src_name, l3), block)
    report["merged"].append({"type": l3, "name": target_title, "target": str(target_path.relative_to(ORG_DIR))})


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
    lines.append("\n## 警告\n")
    if report["warnings"]:
        for item in report["warnings"]:
            lines.append(f"- {item}")
    else:
        lines.append("\n无\n")
    write_text_preserve(REPORT_PATH, "\n".join(lines))


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 龙兽伙伴规则
    drake_block = clean_aggregate((SRC_DIR / "page_1378.md").read_text(encoding="utf-8"))
    drake_block = _collapse_blank_lines(drake_block.strip())
    if drake_block:
        process_aggregate(
            report,
            "page_1378.md",
            "规则 → 动物伙伴",
            "drake_companion",
            ORG_DIR / "规则" / "巨龙之遗LoD_龙兽伙伴.md",
            "巨龙之遗LoD 龙兽伙伴",
            "## 巨龙之遗LoD 龙兽伙伴",
            block=drake_block,
        )

    # 2. 战士变体：龙血后裔
    archetype_block = clean_aggregate((SRC_DIR / "page_941.md").read_text(encoding="utf-8"))
    archetype_block = _normalize_stars(archetype_block)
    archetype_block = _collapse_blank_lines(archetype_block.strip())
    if archetype_block:
        process_aggregate(
            report,
            "page_941.md",
            "职业选项 → 战士",
            "fighter_archetype_dragonheir",
            ORG_DIR / "职业" / "核心职业" / "战士" / "巨龙之遗LoD_战士变体.md",
            "巨龙之遗LoD 战士变体",
            "## 巨龙之遗LoD 战士变体",
            block=archetype_block,
        )

    # 3. 种族特性替换：巨龙魔法
    racial_block = clean_aggregate((SRC_DIR / "page_942.md").read_text(encoding="utf-8"))
    racial_block = _normalize_stars(racial_block)
    racial_block = _collapse_blank_lines(racial_block.strip())
    if racial_block:
        process_aggregate(
            report,
            "page_942.md",
            "规则 → 种族特性",
            "dragon_magic_racial",
            ORG_DIR / "规则" / "巨龙之遗LoD_种族特性替换.md",
            "巨龙之遗LoD 种族特性替换",
            "## 巨龙之遗LoD 种族特性替换",
            block=racial_block,
        )

    # 4. 先知秘示域
    mystery_block = clean_aggregate((SRC_DIR / "先知秘示域4.md").read_text(encoding="utf-8"))
    mystery_block = _collapse_blank_lines(mystery_block.strip())
    if mystery_block:
        process_aggregate(
            report,
            "先知秘示域4.md",
            "职业选项 → 先知",
            "oracle_mystery_dragon",
            ORG_DIR / "职业" / "基础职业" / "先知" / "巨龙之遗LoD_先知秘示域.md",
            "巨龙之遗LoD 先知秘示域",
            "## 巨龙之遗LoD 先知秘示域",
            block=mystery_block,
        )

    # 5. 先知诅咒
    curse_block = clean_aggregate((SRC_DIR / "先知诅咒.md").read_text(encoding="utf-8"))
    curse_block = _collapse_blank_lines(curse_block.strip())
    if curse_block:
        process_aggregate(
            report,
            "先知诅咒.md",
            "职业选项 → 先知",
            "oracle_curse_covetous",
            ORG_DIR / "职业" / "基础职业" / "先知" / "巨龙之遗LoD_先知诅咒.md",
            "巨龙之遗LoD 先知诅咒",
            "## 巨龙之遗LoD 先知诅咒",
            block=curse_block,
        )

    # 6. 新魔宠：书卷龙
    familiar_block = clean_aggregate((SRC_DIR / "新魔宠.md").read_text(encoding="utf-8"))
    familiar_block = _collapse_blank_lines(familiar_block.strip())
    if familiar_block:
        process_aggregate(
            report,
            "新魔宠.md",
            "规则 → 动物伙伴",
            "caligraphy_wyrm",
            ORG_DIR / "规则" / "巨龙之遗LoD_新魔宠.md",
            "巨龙之遗LoD 新魔宠",
            "## 巨龙之遗LoD 新魔宠",
            block=familiar_block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
