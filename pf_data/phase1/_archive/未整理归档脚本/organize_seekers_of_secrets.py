#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 秘密探寻者（Seekers of Secrets）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/秘密探寻者SoS
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/秘密探寻者SoS"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "SeekersOfSecrets_reorganization_report.md"

SOURCE_BOOK = "秘密探寻者（Seekers of Secrets）"
SOURCE_BOOK_SHORT = "秘密探寻者SoS"


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


def extract_between(text: str, start: str, end: str | None = None) -> str:
    """提取 text 中从 start 标记到 end 标记（不含）之间的内容。"""
    s = text.find(start)
    if s == -1:
        return ""
    e = len(text)
    if end:
        e = text.find(end, s + len(start))
        if e == -1:
            e = len(text)
    return text[s:e].strip()


def strip_leading_heading(block: str) -> str:
    """移除块首可能存在的 Markdown 标题/星号装饰。"""
    lines = block.splitlines()
    while lines and lines[0].strip().lstrip("#").strip() == "":
        lines = lines[1:]
    return "\n".join(lines).strip()


def strip_leading_title(block: str) -> str:
    """移除块首标题（标题可能跨两行并带有 ** 加粗标记）。"""
    lines = block.splitlines()
    removed = 0
    while lines and removed < 2:
        if lines[0].strip() == "":
            lines = lines[1:]
        else:
            lines = lines[1:]
            removed += 1
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return "\n".join(lines).strip()


ITEM_FIELD_LABELS = {
    "出处", "类型", "价格", "重量", "灵光", "ＣＬ", "CL", "施法者等级", "位置",
    "效果", "描述", "制造DC", "制作条件", "制作成本", "制造要求", "制造成本",
    "灵氲",
}


def is_item_field_line(line: str) -> bool:
    """判断是否为物品属性字段行（如 **类型**：xxx、**价格**：xxx）。"""
    stripped = line.strip()
    # 字段格式：**标签**：值 或 **标签**:值（标签被 ** 包裹，后接冒号）
    m = re.match(r"^\*\*(.+?)\*\*\s*[：:]", stripped)
    if not m:
        return False
    return m.group(1) in ITEM_FIELD_LABELS


def strip_item_title(block: str) -> str:
    """移除物品块首的加粗标题，直到遇到第一个属性字段行为止。"""
    lines = block.splitlines()
    # 移除第一行标题（通常包含中文名）
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    if lines:
        first = lines[0].strip()
        lines = lines[1:]
        # 若标题跨行且第二行不是属性字段，则一并移除
        if not first.endswith("**"):
            while lines and lines[0].strip() == "":
                lines = lines[1:]
            if lines and not is_item_field_line(lines[0]):
                lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return "\n".join(lines).strip()


def split_items_11(text: str) -> tuple[list[str], list[str], list[str]]:
    """将 物品11.md 拆分为有位置奇物、无位置奇物与普通装备/炼金物品。

    返回 (slotted_blocks, slotless_blocks, mundane_blocks)
    """
    item_names = [
        "巨魔止血散", "探索者腰包", "自主绘图装置", "多功能背心",
    ]

    positions: list[tuple[int, str]] = []
    for name in item_names:
        # 优先匹配带 ** 加粗前缀的标题，避免标题前缀残留在上一物品块中
        idx = text.find(f"**{name}")
        if idx == -1:
            idx = text.find(name)
        if idx != -1:
            positions.append((idx, name))
    positions.sort()

    items: list[tuple[str, str]] = []
    for i, (start, name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        block = text[start:end].strip()
        lines = block.splitlines()
        cleaned_lines = [ln for ln in lines if not re.match(r"^\|?\s*---", ln.strip())]
        block = "\n".join(cleaned_lines).strip()
        block = strip_item_title(block)
        if block:
            block = f"## {name}\n\n{block}"
            items.append((name, block))

    slotted: list[str] = []
    slotless: list[str] = []
    mundane: list[str] = []
    for name, block in items:
        # 无位置奇物：显式标注“无位置”或“位置：无”（允许字段与“无”之间有其他描述文字）
        if re.search(r"(?:类型|位置|栏位)[：:\*]*\s*.*?无", block):
            slotless.append(block)
        # 有位置奇物：位置/栏位字段非空且非“无”
        elif re.search(r"(?:位置|栏位)[：:\*]*\s*[一-龥a-zA-Z]+", block):
            slotted.append(block)
        else:
            mundane.append(block)
    return slotted, slotless, mundane


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

    # 专长
    process_aggregate(
        report,
        "专长15.md",
        "专长",
        "feats",
        ORG_DIR / "专长" / "秘密探寻者SoS_专长.md",
        "秘密探寻者SoS 专长",
        "## 秘密探寻者SoS 专长",
    )

    # 物品拆分
    items_text = clean_aggregate((SRC_DIR / "物品11.md").read_text(encoding="utf-8"))
    slotted, slotless, mundane = split_items_11(items_text)

    if slotted:
        process_aggregate(
            report,
            "物品11.md",
            "装备",
            "slotted_wondrous",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "秘密探寻者SoS_奇物.md",
            "秘密探寻者SoS 奇物",
            "## 秘密探寻者SoS 有位置奇物",
            block="\n\n".join(slotted),
        )
    if slotless:
        process_aggregate(
            report,
            "物品11.md",
            "装备",
            "slotless_wondrous",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "无位置" / "秘密探寻者SoS_奇物.md",
            "秘密探寻者SoS 无位置奇物",
            "## 秘密探寻者SoS 无位置奇物",
            block="\n\n".join(slotless),
        )
    if mundane:
        process_aggregate(
            report,
            "物品11.md",
            "装备",
            "alchemical_gear",
            ORG_DIR / "装备_魔法物品" / "货品服务" / "秘密探寻者SoS_炼金物品.md",
            "秘密探寻者SoS 炼金物品",
            "## 秘密探寻者SoS 炼金物品",
            block="\n\n".join(mundane),
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
