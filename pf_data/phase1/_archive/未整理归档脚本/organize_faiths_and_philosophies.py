#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 信仰与哲学（Faiths and Philosophies）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/信仰与哲学F&amp;P
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/信仰与哲学F&amp;P"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "FaithsAndPhilosophies_reorganization_report.md"

SOURCE_BOOK = "信仰与哲学（Faiths and Philosophies）"
SOURCE_BOOK_SHORT = "信仰与哲学F&P"


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


def strip_first_line(block: str) -> str:
    """移除块首第一行非空内容（用于去掉原文标题，因标题由调用方单独提供）。"""
    lines = block.splitlines()
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    if lines:
        lines = lines[1:]
    while lines and lines[0].strip() == "":
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


def process_druid_domains(report: dict, text: str) -> None:
    """将四个德鲁伊领域分别追加到德鲁伊领域汇总.md。"""
    domains = [
        ("荒原领域（Badlands", "badlands_domain", "## 荒原领域（Badlands Domain）"),
        ("鳄鱼领域（Crocodile", "crocodile_domain", "## 鳄鱼领域（Crocodile Domain）"),
        ("黑豹领域（Panther", "panther_domain", "## 黑豹领域（Panther Domain）"),
        ("秃鹫领域（Vulture", "vulture_domain", "## 秃鹫领域（Vulture Domain）"),
    ]

    for i, (title, key, heading) in enumerate(domains):
        start = title
        end = domains[i + 1][0] if i + 1 < len(domains) else None
        block = extract_between(text, start, end)
        if not block:
            report["warnings"].append(f"变体_选项.md: 未找到 {title}")
            continue
        process_aggregate(
            report,
            "变体_选项.md",
            "职业",
            key,
            ORG_DIR / "职业" / "核心职业" / "德鲁伊" / "德鲁伊领域汇总.md",
            "德鲁伊领域汇总",
            heading,
            block=strip_leading_title(strip_leading_heading(block)),
        )


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 背景特性
    process_aggregate(
        report,
        "背景特性26.md",
        "背景特性",
        "faith_traits",
        ORG_DIR / "背景特性" / "信仰与哲学F&P_背景特性.md",
        "信仰与哲学F&P 背景特性",
        "## 信仰与哲学F&P 背景特性",
    )

    # 专长
    process_aggregate(
        report,
        "专长17.md",
        "专长",
        "druidic_decoder",
        ORG_DIR / "专长" / "信仰与哲学F&P_专长.md",
        "信仰与哲学F&P 专长",
        "## 德鲁伊语破译者（Druidic Decoder）",
    )

    # 德鲁伊领域
    domains_text = clean_aggregate((SRC_DIR / "变体_选项.md").read_text(encoding="utf-8"))
    process_druid_domains(report, domains_text)

    # 魔法物品（有位置奇物）
    process_aggregate(
        report,
        "物品4.md",
        "装备",
        "wondrous_items",
        ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "信仰与哲学F&P_奇物.md",
        "信仰与哲学F&P 奇物",
        "## 信仰与哲学F&P 奇物",
    )

    # 吟游诗人变体
    bard_text = clean_aggregate((SRC_DIR / "吟游诗人变体1.md").read_text(encoding="utf-8"))
    process_aggregate(
        report,
        "吟游诗人变体1.md",
        "职业",
        "arcane_healer",
        ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "page_38.md",
        "吟游诗人",
        "## 玄秘愈师（Arcane Healer）",
        block=strip_leading_title(bard_text),
    )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
