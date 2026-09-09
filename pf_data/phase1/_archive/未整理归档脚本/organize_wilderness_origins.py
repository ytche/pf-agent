#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 荒野源始（Wilderness Origins）内容到已有分类目录。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/荒野源始WO"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "WildernessOrigins_reorganization_report.md"

SOURCE_BOOK = "荒野源始（Wilderness Origins）"
SOURCE_BOOK_SHORT = "荒野源始WO"


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

    # 1. 背景特性
    block = clean_aggregate((SRC_DIR / "背景特性49.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "背景特性49.md",
            "背景特性",
            "background_traits",
            ORG_DIR / "背景特性" / "荒野源始WO_背景特性.md",
            "荒野源始WO 背景特性",
            "## 荒野源始WO 背景特性",
            block=block,
        )

    # 2. 动物伙伴变体
    block = clean_aggregate((SRC_DIR / "动物伙伴变体1.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "动物伙伴变体1.md",
            "规则 → 动物伙伴变体",
            "animal_companion_variants",
            ORG_DIR / "规则" / "荒野源始WO_动物伙伴变体.md",
            "荒野源始WO 动物伙伴变体",
            "## 荒野源始WO 动物伙伴变体",
            block=block,
        )

    # 3. 魔宠变体
    block = clean_aggregate((SRC_DIR / "魔宠变体.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "魔宠变体.md",
            "规则 → 魔宠变体",
            "familiar_variants",
            ORG_DIR / "规则" / "荒野源始WO_魔宠变体.md",
            "荒野源始WO 魔宠变体",
            "## 荒野源始WO 魔宠变体",
            block=block,
        )

    # 4. 专长
    block = clean_aggregate((SRC_DIR / "专长13.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "专长13.md",
            "专长",
            "feats",
            ORG_DIR / "专长" / "荒野源始WO_专长.md",
            "荒野源始WO 专长",
            "## 荒野源始WO 专长",
            block=block,
        )

    variant_options = [
        (
            "变形者_拟态.md",
            "职业选项 → 变形者",
            "shifter_aspects_archetypes",
            ORG_DIR / "职业" / "极限荒野（Ultimate Wilderness）" / "变形者" / "荒野源始WO_变形者变体.md",
            "荒野源始WO 变形者拟态与变体",
            "## 荒野源始WO 变形者拟态与变体",
        ),
        (
            "操念使4.md",
            "职业选项 → 操念使",
            "kineticist_archetype",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "操念使" / "荒野源始WO_操念使变体.md",
            "荒野源始WO 灰烬之地勇士",
            "## 荒野源始WO 灰烬之地勇士",
        ),
        (
            "幻灵亚种.md",
            "职业选项 → 召唤师",
            "kami_eidolon",
            ORG_DIR / "职业" / "基础职业" / "召唤师" / "荒野源始WO_召唤师幻灵亚种.md",
            "荒野源始WO 社神幻灵",
            "## 荒野源始WO 社神幻灵",
        ),
        (
            "唤魂师1.md",
            "职业选项 → 唤魂师",
            "spiritualist_archetype",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "唤魂师" / "荒野源始WO_唤魂师变体.md",
            "荒野源始WO 御守唤魂师",
            "## 荒野源始WO 御守唤魂师",
        ),
        (
            "女巫巫术.md",
            "职业选项 → 女巫",
            "witch_hexes",
            ORG_DIR / "职业" / "基础职业" / "女巫" / "荒野源始WO_女巫巫术.md",
            "荒野源始WO 鲜花巫术",
            "## 荒野源始WO 鲜花巫术",
        ),
        (
            "骑将2.md",
            "职业选项 → 骑将",
            "cavalier_archetype",
            ORG_DIR / "职业" / "基础职业" / "骑将" / "荒野源始WO_骑将变体.md",
            "荒野源始WO 苍翠骑士",
            "## 荒野源始WO 苍翠骑士",
        ),
        (
            "忍者1.md",
            "职业选项 → 忍者",
            "ninja_archetype",
            ORG_DIR / "职业" / "基础职业" / "忍者" / "荒野源始WO_忍者变体.md",
            "荒野源始WO 散华忍",
            "## 荒野源始WO 散华忍",
        ),
        (
            "萨满魂域.md",
            "职业选项 → 萨满",
            "shaman_spirit",
            ORG_DIR / "职业" / "混合职业" / "萨满" / "荒野源始WO_萨满魂域.md",
            "荒野源始WO 部族魂域",
            "## 荒野源始WO 部族魂域",
        ),
        (
            "审判者2.md",
            "职业选项 → 审判者",
            "inquisitor_archetype",
            ORG_DIR / "职业" / "基础职业" / "审判者" / "荒野源始WO_审判者变体.md",
            "荒野源始WO 原初誓者",
            "## 荒野源始WO 原初誓者",
        ),
        (
            "圣武士1.md",
            "职业选项 → 圣骑士",
            "paladin_archetype",
            ORG_DIR / "职业" / "核心职业" / "圣骑士" / "荒野源始WO_圣骑士变体.md",
            "荒野源始WO 滥觞卫士",
            "## 荒野源始WO 滥觞卫士",
        ),
        (
            "异能者.md",
            "职业选项 → 异能者",
            "psychic_archetypes",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "异能者" / "荒野源始WO_异能者变体.md",
            "荒野源始WO 异能者变体",
            "## 荒野源始WO 异能者变体",
        ),
    ]

    for src_name, l3, entry_name, target, title, heading in variant_options:
        block = clean_aggregate((SRC_DIR / "变体_选项" / src_name).read_text(encoding="utf-8"))
        block = _normalize_stars(block)
        block = _collapse_blank_lines(block.strip())
        if block:
            process_aggregate(
                report,
                f"变体_选项/{src_name}",
                l3,
                entry_name,
                target,
                title,
                heading,
                block=block,
            )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
