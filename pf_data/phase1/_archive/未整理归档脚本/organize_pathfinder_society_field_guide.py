#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 探索者协会战地指南 PSFG 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/探索者协会战地指南PSFG
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/探索者协会战地指南PSFG"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "PathfinderSocietyFieldGuide_reorganization_report.md"

SOURCE_BOOK = "探索者协会战地指南（Pathfinder Society Field Guide）"
SOURCE_BOOK_SHORT = "探索者协会战地指南PSFG"


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


def split_items8(text: str) -> dict[str, list[str]]:
    """将 物品8.md 拆分为普通物品、有位置奇物、无位置奇物三类块列表。"""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]

    mundane: list[str] = []
    slotted: list[str] = []
    slotless: list[str] = []

    for block in blocks:
        # 以“灵光”或“施法者等级”作为奇物判定依据
        if "灵光" in block or "施法者等级" in block:
            if re.search(r"位置\s*无", block):
                slotless.append(block)
            else:
                slotted.append(block)
        else:
            mundane.append(block)

    return {"mundane": mundane, "slotted": slotted, "slotless": slotless}


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

    # 防具附魔
    process_aggregate(
        report,
        "防具附魔.md",
        "装备",
        "__aggregate__",
        ORG_DIR / "装备_魔法物品" / "防具附魔" / "探索者协会战地指南PSFG_防具附魔.md",
        "探索者协会战地指南PSFG 防具附魔",
        "## 探索者协会战地指南PSFG 防具附魔",
    )

    # 武器附魔
    process_aggregate(
        report,
        "武器附魔1.md",
        "装备",
        "__aggregate__",
        ORG_DIR / "装备_魔法物品" / "武器附魔" / "探索者协会战地指南PSFG_武器附魔.md",
        "探索者协会战地指南PSFG 武器附魔",
        "## 探索者协会战地指南PSFG 武器附魔",
    )

    # 物品8：普通物品 + 奇物
    items_text = clean_aggregate((SRC_DIR / "物品8.md").read_text(encoding="utf-8"))
    parts = split_items8(items_text)

    if parts["mundane"]:
        process_aggregate(
            report,
            "物品8.md",
            "装备",
            "mundane",
            ORG_DIR / "装备_魔法物品" / "货品服务" / "探索者协会战地指南PSFG_物品.md",
            "探索者协会战地指南PSFG 物品",
            "## 探索者协会战地指南PSFG 普通物品",
            block="\n\n".join(parts["mundane"]),
        )

    if parts["slotted"]:
        process_aggregate(
            report,
            "物品8.md",
            "装备",
            "wondrous_slotted",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "探索者协会战地指南PSFG_奇物.md",
            "探索者协会战地指南PSFG 奇物",
            "## 探索者协会战地指南PSFG 奇物",
            block="\n\n".join(parts["slotted"]),
        )

    if parts["slotless"]:
        process_aggregate(
            report,
            "物品8.md",
            "装备",
            "wondrous_slotless",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "无位置" / "探索者协会战地指南PSFG_奇物.md",
            "探索者协会战地指南PSFG 无位置奇物",
            "## 探索者协会战地指南PSFG 无位置奇物",
            block="\n\n".join(parts["slotless"]),
        )

    # 古卷学者变体：追加到牧师与法师职业变体页面
    variant_text = clean_aggregate((SRC_DIR / "职业变体.md").read_text(encoding="utf-8"))
    for cls, target in (
        ("牧师", ORG_DIR / "职业" / "核心职业" / "牧师" / "page_41.md"),
        ("法师", ORG_DIR / "职业" / "核心职业" / "法师" / "page_67.md"),
    ):
        process_aggregate(
            report,
            "职业变体.md",
            "职业变体",
            "scroll_scholar",
            target,
            f"{cls} 古卷学者",
            f"## 探索者协会战地指南PSFG 古卷学者（Scroll Scholar）【{cls}变体】",
            block=variant_text,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
