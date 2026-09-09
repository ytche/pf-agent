#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 惊骇国度（Horror Realms）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/惊骇国度HR
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/惊骇国度HR"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "HorrorRealms_reorganization_report.md"

SOURCE_BOOK = "惊骇国度（Horror Realms）"
SOURCE_BOOK_SHORT = "惊骇国度HR"


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

    mappings = [
        (
            "德鲁伊领域.md",
            "职业选项 → 德鲁伊",
            "uskbond_domain",
            ORG_DIR / "职业" / "核心职业" / "德鲁伊" / "惊骇国度HR_德鲁伊领域.md",
            "惊骇国度HR 乌斯克纽带领域",
            "## 惊骇国度HR 乌斯克纽带领域",
        ),
        (
            "幻灵亚种1.md",
            "职业选项 → 召唤师",
            "aberrant_eidolon",
            ORG_DIR / "职业" / "基础职业" / "召唤师" / "惊骇国度HR_幻灵亚种.md",
            "惊骇国度HR 异怪幻灵亚种",
            "## 惊骇国度HR 异怪幻灵亚种",
        ),
        (
            "萨满魂域1.md",
            "职业选项 → 萨满",
            "dark_tapestry_spirit",
            ORG_DIR / "职业" / "基础职业" / "萨满" / "惊骇国度HR_萨满魂域.md",
            "惊骇国度HR 暗幕精魂",
            "## 惊骇国度HR 暗幕精魂",
        ),
        (
            "诗人变体.md",
            "职业选项 → 吟游诗人",
            "mute_musician",
            ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "惊骇国度HR_吟游诗人变体.md",
            "惊骇国度HR 静默乐手变体",
            "## 惊骇国度HR 静默乐手变体",
        ),
        (
            "武僧变体.md",
            "职业选项 → 武僧",
            "scarred_monk",
            ORG_DIR / "职业" / "核心职业" / "武僧" / "惊骇国度HR_武僧变体.md",
            "惊骇国度HR 伤痕僧变体",
            "## 惊骇国度HR 伤痕僧变体",
        ),
        (
            "咒怨伙伴.md",
            "规则 → 动物伙伴",
            "accursed_companion",
            ORG_DIR / "规则" / "惊骇国度HR_咒怨伙伴.md",
            "惊骇国度HR 咒怨伙伴",
            "## 惊骇国度HR 咒怨伙伴",
        ),
    ]

    for src_name, l3, entry_name, target_path, title, heading in mappings:
        block = clean_aggregate((SRC_DIR / src_name).read_text(encoding="utf-8"))
        block = _normalize_stars(block)
        block = _collapse_blank_lines(block.strip())
        if block:
            process_aggregate(
                report,
                src_name,
                l3,
                entry_name,
                target_path,
                title,
                heading,
                block=block,
            )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
