#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 部属与伙伴（Cohorts and Companions）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/CaC部属与伙伴
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/CaC部属与伙伴"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "CohortsAndCompanions_reorganization_report.md"

SOURCE_BOOK = "部属与伙伴（Cohorts and Companions）"
SOURCE_BOOK_SHORT = "CaC部属与伙伴"


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


def clean_aggregate(text: str) -> str:
    """对聚合文件进行最小清理。"""
    import re

    text = text.replace("\r\n", "\n")
    # 移除 Markdown 图片链接
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    # 移除顶部译者/整理者链接与空行
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


def strip_trailing_artifacts(block: str) -> str:
    import re

    lines = block.splitlines()
    while lines and (lines[-1].strip() == "" or re.match(r"^\*+$", lines[-1].strip())):
        lines.pop()
    return "\n".join(lines)


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
    lines = block.splitlines()
    while lines and lines[0].strip().lstrip("#").strip() == "":
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


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 专长
    process_aggregate(
        report,
        "专长57.md",
        "专长",
        "feats",
        ORG_DIR / "专长" / "CaC部属与伙伴_专长.md",
        "CaC部属与伙伴 专长",
        "## CaC部属与伙伴 专长",
    )

    # 种植植物生物规则
    process_aggregate(
        report,
        "种植植物生物.md",
        "规则",
        "grow_plant_creature",
        ORG_DIR / "规则" / "CaC部属与伙伴_规则.md",
        "CaC部属与伙伴 规则",
        "## 种植植物生物",
    )

    # 魔法物品15：戒指奇物
    process_aggregate(
        report,
        "魔法物品15.md",
        "装备",
        "magic_items",
        ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "CaC部属与伙伴_奇物.md",
        "CaC部属与伙伴 奇物",
        "## CaC部属与伙伴 奇物",
    )

    # 盗贼天赋
    process_aggregate(
        report,
        "变体_选项/盗贼2.md",
        "职业",
        "rogue_talents",
        ORG_DIR / "职业" / "核心职业" / "盗贼" / "CaC部属与伙伴_盗贼天赋.md",
        "CaC部属与伙伴 盗贼天赋",
        "## 盗贼天赋",
    )

    # 调查员变体（死秘探者）
    process_aggregate(
        report,
        "变体_选项/调查员.md",
        "职业",
        "dread_investigator",
        ORG_DIR / "职业" / "混合职业" / "调查员" / "page_31.md",
        "调查员",
        "## 死秘探者（Dread Investigator）",
    )

    # 炼金术师变体（构装骑士）与新科研发现
    alchemist_text = clean_aggregate((SRC_DIR / "变体_选项/炼金术师.md").read_text(encoding="utf-8"))
    construct_rider = extract_between(alchemist_text, "构装骑士/机械先驱", "新炼金术师科研发现")
    if construct_rider:
        process_aggregate(
            report,
            "变体_选项/炼金术师.md",
            "职业",
            "construct_rider",
            ORG_DIR / "职业" / "基础职业" / "炼金术师" / "page_21.md",
            "炼金术师",
            "## 构装骑士/机械先驱（Construct Rider）",
            block=strip_leading_heading(construct_rider),
        )
    new_discoveries = extract_between(alchemist_text, "新炼金术师科研发现", None)
    if new_discoveries:
        process_aggregate(
            report,
            "变体_选项/炼金术师.md",
            "职业",
            "new_discoveries",
            ORG_DIR / "职业" / "基础职业" / "炼金术师" / "page_71.md",
            "炼金术师科研发现",
            "## 新科研发现",
            block=strip_leading_heading(new_discoveries),
        )

    # 骑将变体（名流绅士）
    process_aggregate(
        report,
        "变体_选项/骑将.md",
        "职业",
        "esquire",
        ORG_DIR / "职业" / "基础职业" / "骑将" / "page_74.md",
        "骑将",
        "## 名流绅士（Esquire）",
    )

    # 圣武士变体（神卫）
    process_aggregate(
        report,
        "变体_选项/圣武士变体.md",
        "职业",
        "divine_guardian",
        ORG_DIR / "职业" / "核心职业" / "圣骑士" / "page_55.md",
        "圣武士",
        "## 神卫（Divine Guardian）",
    )

    # 战斗祭司变体（颂教圣使）
    process_aggregate(
        report,
        "变体_选项/战斗祭司变体.md",
        "职业",
        "proselytizer",
        ORG_DIR / "职业" / "混合职业" / "战斗祭司" / "page_125.md",
        "战斗祭司",
        "## 颂教圣使（Proselytizer）",
    )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
