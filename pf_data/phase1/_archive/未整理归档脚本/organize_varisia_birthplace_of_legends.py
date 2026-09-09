#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 瓦瑞西亚，传说诞生之地（Varisia, Birthplace of Legends）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/瓦瑞西亚，传说诞生之地
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/瓦瑞西亚，传说诞生之地"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "VarisiaBirthplaceOfLegends_reorganization_report.md"

SOURCE_BOOK = "瓦瑞西亚，传说诞生之地（Varisia, Birthplace of Legends）"
SOURCE_BOOK_SHORT = "瓦瑞西亚"


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
    """将标题中多余的星号对规范化为 **中文（English）**。"""
    # **中文名**（**English**）或 **中文名** ( **English** )
    text = re.sub(
        r"\*\*([^*]+?)\*\*\s*[（(]\s*\*\*([^*]+?)\*\*\s*[）)]",
        r"**\1（\2）**",
        text,
    )
    # **中文名(English)** 或 **中文名（English）**
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


# ---------------------------------------------------------------------------
# 条目拆分
# ---------------------------------------------------------------------------

def clean_traits(text: str) -> str:
    """清理 背景特性21.md 全文。

    该页特性格式混杂（部分英文名称在次行），直接整体聚合，
    仅做最小化清理：去图片/译者行、规范化括号内英文名称、合并多余空行。
    """
    text = clean_aggregate(text)
    text = _normalize_stars(text)
    # 移除整行都是星号的装饰行
    text = re.sub(r"\n\*+\s*\n", "\n\n", text)
    text = _collapse_blank_lines(text.strip())
    return text


def clean_items(text: str) -> str:
    """清理 物品27.md 全文。"""
    text = clean_aggregate(text)
    text = _normalize_stars(text)
    text = re.sub(r"\n\*+\s*\n", "\n\n", text)
    text = _collapse_blank_lines(text.strip())
    return text


def clean_armor(text: str) -> str:
    """清理 新防具.md 全文。"""
    text = clean_aggregate(text)
    text = _normalize_stars(text)
    text = re.sub(r"\n\*+\s*\n", "\n\n", text)
    text = _collapse_blank_lines(text.strip())
    return text


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 背景特性
    trait_block = clean_traits((SRC_DIR / "背景特性21.md").read_text(encoding="utf-8"))
    if trait_block:
        process_aggregate(
            report,
            "背景特性21.md",
            "背景特性",
            "background_traits",
            ORG_DIR / "背景特性" / "瓦瑞西亚，传说诞生之地_背景特性.md",
            "瓦瑞西亚，传说诞生之地 背景特性",
            "## 瓦瑞西亚，传说诞生之地 背景特性",
            block=trait_block,
        )

    # 2. 物品
    item_block = clean_items((SRC_DIR / "物品27.md").read_text(encoding="utf-8"))
    if item_block:
        process_aggregate(
            report,
            "物品27.md",
            "装备/物品",
            "items",
            ORG_DIR / "装备_魔法物品" / "瓦瑞西亚，传说诞生之地_物品.md",
            "瓦瑞西亚，传说诞生之地 物品",
            "## 瓦瑞西亚，传说诞生之地 物品",
            block=item_block,
        )

    # 3. 防具
    armor_block = clean_armor((SRC_DIR / "新防具.md").read_text(encoding="utf-8"))
    if armor_block:
        process_aggregate(
            report,
            "新防具.md",
            "装备/物品",
            "armor",
            ORG_DIR / "装备_魔法物品" / "瓦瑞西亚，传说诞生之地_物品.md",
            "瓦瑞西亚，传说诞生之地 防具",
            "## 瓦瑞西亚，传说诞生之地 防具",
            block=armor_block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
