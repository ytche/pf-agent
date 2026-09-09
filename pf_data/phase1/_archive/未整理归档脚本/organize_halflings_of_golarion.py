#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 格拉里昂的半身人（Halflings of Golarion）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/格拉里昂的半身人
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/格拉里昂的半身人"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "HalflingsOfGolarion_reorganization_report.md"

SOURCE_BOOK = "格拉里昂的半身人（Halflings of Golarion）"
SOURCE_BOOK_SHORT = "格拉里昂的半身人"


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


def split_jinx_file(text: str) -> tuple[str, str]:
    """将 page_572.md 切分为种族特性块和专长块。"""
    lines = text.splitlines()
    split_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*新专长\s*$", line.strip()):
            split_idx = i
            break
    if split_idx is None:
        raise ValueError("page_572.md 中未找到'新专长'分隔行")
    trait_block = "\n".join(lines[:split_idx])
    feat_block = "\n".join(lines[split_idx:])
    return trait_block, feat_block


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

    # 1. 武器（投石索技艺）
    process_aggregate(
        report,
        "page_571.md",
        "装备",
        "__aggregate__",
        ORG_DIR / "装备_魔法物品" / "武器" / "格拉里昂的半身人_投石索.md",
        "格拉里昂的半身人 投石索",
        "## 格拉里昂的半身人 投石索",
    )

    # 2. page_572.md 切分为种族特性与专长
    jinx_text = clean_aggregate((SRC_DIR / "page_572.md").read_text(encoding="utf-8"))
    trait_block, feat_block = split_jinx_file(jinx_text)

    process_aggregate(
        report,
        "page_572.md",
        "种族特性",
        "半身人霉咒",
        ORG_DIR / "种族" / "核心种族" / "半身人" / "格拉里昂的半身人_半身人霉咒.md",
        "格拉里昂的半身人 半身人霉咒",
        "## 格拉里昂的半身人 半身人霉咒（Halfling Jinx）【种族特性】",
        block=trait_block,
    )

    process_aggregate(
        report,
        "page_572.md",
        "专长",
        "__jinx_feats__",
        ORG_DIR / "专长" / "格拉里昂的半身人_专长.md",
        "格拉里昂的半身人 专长",
        "## 格拉里昂的半身人 专长",
        block=feat_block,
    )

    # 3. 进阶职业
    process_aggregate(
        report,
        "半身人投机客.md",
        "进阶职业",
        "__aggregate__",
        ORG_DIR / "职业" / "进阶职业" / "格拉里昂的半身人_半身人投机客.md",
        "格拉里昂的半身人 半身人投机客",
        "## 格拉里昂的半身人 半身人投机客（Halfling Opportunist）",
    )

    # 4. 酒品
    process_aggregate(
        report,
        "物品36.md",
        "装备",
        "__aggregate__",
        ORG_DIR / "装备_魔法物品" / "货品服务" / "格拉里昂的半身人_半身人酒品.md",
        "格拉里昂的半身人 半身人酒品",
        "## 格拉里昂的半身人 半身人酒品",
    )

    # 5. 专长31.md 与 格拉里昂的矮人/专长50.md 内容重复，疑为源文件错放，跳过并记录
    report["warnings"].append(
        "专长31.md 内容与 格拉里昂的矮人/专长50.md 高度重复（弹跳锤/滑行斧投掷/索恩站姿），"
        "疑为源文件错放；本次跳过，不合并到半身人专长。"
    )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
