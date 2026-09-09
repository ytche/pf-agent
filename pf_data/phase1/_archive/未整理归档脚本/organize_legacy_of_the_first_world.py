#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 第一世界的遗产（Legacy of the First World）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/第一世界的遗产LotFW
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/第一世界的遗产LotFW"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "LegacyOfTheFirstWorld_reorganization_report.md"

SOURCE_BOOK = "第一世界的遗产（Legacy of the First World）"
SOURCE_BOOK_SHORT = "第一世界的遗产LotFW"


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


def split_page_1070(text: str, report: dict) -> tuple[str, str]:
    """拆分 page_1070 为古老者介绍与地区背景特性两部分。"""
    text = clean_aggregate(text)
    text = _normalize_stars(text)
    parts = re.split(r"\n\s*\*\*\*\*?\s*\n", text)
    intro_parts: list[str] = []
    trait_parts: list[str] = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        # 前两个部分为介绍与古老者概述，其余均为地区背景特性
        if i < 2:
            intro_parts.append(part)
        else:
            trait_parts.append(part)
    return "\n\n".join(intro_parts), "\n\n".join(trait_parts)


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 古老者详细属性
    eldest_block = clean_aggregate((SRC_DIR / "page_1069.md").read_text(encoding="utf-8"))
    eldest_block = _collapse_blank_lines(eldest_block.strip())
    if eldest_block:
        process_aggregate(
            report,
            "page_1069.md",
            "信仰 → 神祇",
            "the_eldest_stats",
            ORG_DIR / "信仰" / "第一世界的遗产LotFW_古老者.md",
            "第一世界的遗产LotFW 古老者",
            "## 第一世界的遗产LotFW 古老者",
            block=eldest_block,
        )

    # 2. page_1070 拆分
    page_1070_text = (SRC_DIR / "page_1070.md").read_text(encoding="utf-8")
    intro_block, trait_block = split_page_1070(page_1070_text, report)

    if intro_block:
        intro_block = _collapse_blank_lines(intro_block.strip())
        process_aggregate(
            report,
            "page_1070.md",
            "信仰 → 神祇",
            "the_eldest_intro",
            ORG_DIR / "信仰" / "第一世界的遗产LotFW_古老者.md",
            "第一世界的遗产LotFW 古老者",
            "## 第一世界的遗产LotFW 古老者",
            block=intro_block,
        )

    if trait_block:
        trait_block = _collapse_blank_lines(trait_block.strip())
        process_aggregate(
            report,
            "page_1070.md",
            "背景特性",
            "regional_traits",
            ORG_DIR / "背景特性" / "第一世界的遗产LotFW_地区背景特性.md",
            "第一世界的遗产LotFW 地区背景特性",
            "## 第一世界的遗产LotFW 地区背景特性",
            block=trait_block,
        )

    # 3. 其余规则页聚合到第一世界规则
    rule_pages = [f"page_{p}.md" for p in range(1071, 1085)]
    rule_blocks: list[str] = []
    for page in rule_pages:
        block = clean_aggregate((SRC_DIR / page).read_text(encoding="utf-8"))
        block = _normalize_stars(block)
        block = strip_trailing_artifacts(block.strip())
        if block:
            rule_blocks.append(block)

    if rule_blocks:
        rule_block = "\n\n".join(rule_blocks)
        rule_block = _collapse_blank_lines(rule_block)
        process_aggregate(
            report,
            "page_1071-1084.md",
            "规则",
            "first_world_rules",
            ORG_DIR / "规则" / "第一世界的遗产LotFW_第一世界规则.md",
            "第一世界的遗产LotFW 第一世界规则",
            "## 第一世界的遗产LotFW 第一世界规则",
            block=rule_block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
