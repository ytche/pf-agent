#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 任务与战役（Quests and Campaigns）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/任务与战役
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/任务与战役"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "QuestsAndCampaigns_reorganization_report.md"

SOURCE_BOOK = "任务与战役（Quests and Campaigns）"
SOURCE_BOOK_SHORT = "任务与战役"


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
    """以二进制追加方式写入，保留原文件行尾不变。"""
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
    """移除 Markdown 图片链接标记（通常来自 AON 图标）。"""
    return re.sub(r"!\[.*?\]\(.*?\)", "", text)


def clean_translator_url(text: str) -> str:
    """移除文件顶部的译者/整理者链接与空行。"""
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
    """移除文件顶部的图片引用。"""
    lines = text.splitlines()
    while lines and re.match(r"^\s*!\[.*\]\(.*\)\s*$", lines[0].strip()):
        lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return "\n".join(lines)


def strip_trailing_artifacts(block: str) -> str:
    lines = block.splitlines()
    while lines and (lines[-1].strip() == "" or re.match(r"^\*+$", lines[-1].strip())):
        lines.pop()
    return "\n".join(lines)


def clean_aggregate(text: str) -> str:
    """对聚合文件进行最小清理。"""
    text = text.replace("\r\n", "\n")
    text = remove_image_links(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)
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


def split_wondrous_items(text: str) -> tuple[list[str], list[str]]:
    """将奇物聚合文本拆分为有位置与无位置两组。

    返回 (slotted_blocks, slotless_blocks)
    """
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]

    slotted: list[str] = []
    slotless: list[str] = []
    for block in blocks:
        # 过滤掉分隔线、译者链接等无效块
        if not re.search(r"(?:灵光|施法者等级|价格)", block):
            continue
        # 栏位/位置后经过可选标点、星号、空白到达“无”
        if re.search(r"(?:栏位|位置)[：:\*]*\s*无", block):
            slotless.append(block)
        else:
            slotted.append(block)
    return slotted, slotless


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

    # 背景特性
    process_aggregate(
        report,
        "page_1578.md",
        "背景特性",
        "__aggregate__",
        ORG_DIR / "背景特性" / "任务与战役_背景特性.md",
        "任务与战役 背景特性",
        "## 任务与战役 背景特性",
    )

    # 专长
    process_aggregate(
        report,
        "专长45.md",
        "专长",
        "__aggregate__",
        ORG_DIR / "专长" / "任务与战役_专长.md",
        "任务与战役 专长",
        "## 任务与战役 专长",
    )

    # 法术：典礼
    process_aggregate(
        report,
        "仪式2.md",
        "法术",
        "__aggregate__",
        ORG_DIR / "法术" / "任务与战役_法术.md",
        "任务与战役 法术",
        "## 任务与战役 法术",
    )

    # 武器附魔
    process_aggregate(
        report,
        "武器附魔8.md",
        "装备",
        "__aggregate__",
        ORG_DIR / "装备_魔法物品" / "武器附魔" / "任务与战役_武器附魔.md",
        "任务与战役 武器附魔",
        "## 任务与战役 武器附魔",
    )

    # 物品23：奇物（有位置/无位置拆分）
    items_text = clean_aggregate((SRC_DIR / "物品23.md").read_text(encoding="utf-8"))
    slotted_blocks, slotless_blocks = split_wondrous_items(items_text)

    if slotted_blocks:
        process_aggregate(
            report,
            "物品23.md",
            "装备",
            "wondrous_slotted",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "任务与战役_奇物.md",
            "任务与战役 奇物",
            "## 任务与战役 奇物",
            block="\n\n".join(slotted_blocks),
        )

    if slotless_blocks:
        process_aggregate(
            report,
            "物品23.md",
            "装备",
            "wondrous_slotless",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "无位置" / "任务与战役_奇物.md",
            "任务与战役 无位置奇物",
            "## 任务与战役 无位置奇物",
            block="\n\n".join(slotless_blocks),
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
