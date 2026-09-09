#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 初探探索者协会（Pathfinder Society Primer）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/初探探索者协会
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/初探探索者协会"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "PathfinderSocietyPrimer_reorganization_report.md"

SOURCE_BOOK = "初探探索者协会（Pathfinder Society Primer）"
SOURCE_BOOK_SHORT = "初探探索者协会"


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


def split_page_550(text: str) -> dict[str, str]:
    """将 page_550.md 切分为工具箱、武器附魔、奇物三块。"""
    # 源文件标题格式不统一：工具箱有前导 **，武器附魔没有
    toolkits_idx = text.find("**工具箱**")
    weapon_idx = text.find("武器附魔****")
    wondrous_idx = text.find("**奇物")
    if toolkits_idx == -1 or weapon_idx == -1 or wondrous_idx == -1:
        raise ValueError("page_550.md 中未找到预期的工具箱/武器附魔/奇物分隔")
    return {
        "toolkits": text[toolkits_idx:weapon_idx].strip(),
        "weapon_enchant": text[weapon_idx:wondrous_idx].strip(),
        "wondrous": text[wondrous_idx:].strip(),
    }


def split_wondrous_items(text: str) -> tuple[list[str], list[str]]:
    """将奇物块按位置切分为有位置与无位置两组。

    返回 (slotted_blocks, slotless_blocks)
    """
    # 去掉总标题行
    lines = text.splitlines()
    if lines and "奇物" in lines[0]:
        body = "\n".join(lines[1:]).strip()
    else:
        body = text

    # 按空行分割，筛选出至少包含“价格”的独立条目
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip() and "价格" in b]

    slotted: list[str] = []
    slotless: list[str] = []
    for block in blocks:
        if re.search(r"位置[:：]\s*无", block):
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
        "page_1587.md",
        "背景特性",
        "__aggregate__",
        ORG_DIR / "背景特性" / "初探探索者协会_背景特性.md",
        "初探探索者协会 背景特性",
        "## 初探探索者协会 背景特性",
    )

    # 进阶职业：外勤探员
    process_aggregate(
        report,
        "page_546.md",
        "进阶职业",
        "__aggregate__",
        ORG_DIR / "职业" / "进阶职业" / "初探探索者协会_外勤探员.md",
        "初探探索者协会 外勤探员",
        "## 初探探索者协会 外勤探员（Pathfinder Field Agent）",
    )

    # 专长
    process_aggregate(
        report,
        "page_547.md",
        "专长",
        "__aggregate__",
        ORG_DIR / "专长" / "初探探索者协会_专长.md",
        "初探探索者协会 专长",
        "## 初探探索者协会 专长",
    )

    # 法术
    process_aggregate(
        report,
        "page_549.md",
        "法术",
        "__aggregate__",
        ORG_DIR / "法术" / "初探探索者协会_法术.md",
        "初探探索者协会 法术",
        "## 初探探索者协会 法术",
    )

    # page_550：工具箱、武器附魔、奇物
    page_550_text = clean_aggregate((SRC_DIR / "page_550.md").read_text(encoding="utf-8"))
    parts = split_page_550(page_550_text)

    process_aggregate(
        report,
        "page_550.md",
        "装备",
        "toolkits",
        ORG_DIR / "工具和技能工具包.md",
        "工具和技能工具包",
        "## 初探探索者协会 工具箱",
        block=parts["toolkits"],
    )

    process_aggregate(
        report,
        "page_550.md",
        "装备",
        "weapon_enchant",
        ORG_DIR / "装备_魔法物品" / "武器附魔" / "初探探索者协会_武器附魔.md",
        "初探探索者协会 武器附魔",
        "## 初探探索者协会 武器附魔",
        block=parts["weapon_enchant"],
    )

    slotted_blocks, slotless_blocks = split_wondrous_items(parts["wondrous"])

    if slotted_blocks:
        process_aggregate(
            report,
            "page_550.md",
            "装备",
            "wondrous_slotted",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "初探探索者协会_奇物.md",
            "初探探索者协会 奇物",
            "## 初探探索者协会 奇物",
            block="\n\n".join(slotted_blocks),
        )

    if slotless_blocks:
        process_aggregate(
            report,
            "page_550.md",
            "装备",
            "wondrous_slotless",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "无位置" / "初探探索者协会_奇物.md",
            "初探探索者协会 无位置奇物",
            "## 初探探索者协会 无位置奇物",
            block="\n\n".join(slotless_blocks),
        )

    # 探索者编年史规则
    process_aggregate(
        report,
        "page_551.md",
        "独立规则",
        "__aggregate__",
        ORG_DIR / "规则" / "初探探索者协会_探索者编年史.md",
        "初探探索者协会 探索者编年史",
        "## 初探探索者协会 探索者编年史",
    )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
