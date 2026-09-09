#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 进化职业起源（Advanced Class Origins）内容到已有分类目录。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/进化职业起源"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "AdvancedClassOrigins_reorganization_report.md"

SOURCE_BOOK = "进化职业起源（Advanced Class Origins）"
SOURCE_BOOK_SHORT = "进化职业起源ACO"


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

    top_level = [
        (
            "背景特性19.md",
            "背景特性",
            "background_traits",
            ORG_DIR / "背景特性" / "进化职业起源ACO_背景特性.md",
            "进化职业起源ACO 背景特性",
            "## 进化职业起源ACO 背景特性",
        ),
        (
            "防具附魔2.md",
            "装备/魔法物品 → 防具附魔",
            "armor_enchantments",
            ORG_DIR / "装备_魔法物品" / "进化职业起源ACO_防具附魔.md",
            "进化职业起源ACO 防具附魔",
            "## 进化职业起源ACO 防具附魔",
        ),
        (
            "物品16.md",
            "装备/魔法物品",
            "magic_items",
            ORG_DIR / "装备_魔法物品" / "进化职业起源ACO_魔法物品.md",
            "进化职业起源ACO 魔法物品",
            "## 进化职业起源ACO 魔法物品",
        ),
    ]

    for src_name, l3, entry_name, target, title, heading in top_level:
        block = clean_aggregate((SRC_DIR / src_name).read_text(encoding="utf-8"))
        block = _normalize_stars(block)
        block = _collapse_blank_lines(block.strip())
        if block:
            process_aggregate(
                report,
                src_name,
                l3,
                entry_name,
                target,
                title,
                heading,
                block=block,
            )

    variant_pages = [
        (
            "变体/page_574.md",
            "职业选项 → 奥能师",
            "arcanist_archetype",
            ORG_DIR / "职业" / "混合职业" / "奥能师" / "进化职业起源ACO_奥能师变体.md",
            "进化职业起源ACO 暮光贤者",
            "## 进化职业起源ACO 暮光贤者",
        ),
        (
            "变体/page_575.md",
            "职业选项 → 血脉狂怒者",
            "bloodrager_bloodlines",
            ORG_DIR / "职业" / "混合职业" / "血脉狂怒者" / "进化职业起源ACO_血脉狂怒者变体.md",
            "进化职业起源ACO 血脉狂怒者血脉与法术",
            "## 进化职业起源ACO 血脉狂怒者血脉与法术",
        ),
        (
            "变体/page_576.md",
            "职业选项 → 拳师",
            "brawler_archetypes",
            ORG_DIR / "职业" / "混合职业" / "拳师" / "进化职业起源ACO_拳师变体.md",
            "进化职业起源ACO 拳师变体",
            "## 进化职业起源ACO 拳师变体",
        ),
        (
            "变体/page_577.md",
            "职业选项 → 猎人",
            "hunter_archetypes",
            ORG_DIR / "职业" / "混合职业" / "猎人" / "进化职业起源ACO_猎人变体.md",
            "进化职业起源ACO 猎人变体",
            "## 进化职业起源ACO 猎人变体",
        ),
        (
            "变体/page_578.md",
            "职业选项 → 调查员",
            "investigator_archetype",
            ORG_DIR / "职业" / "混合职业" / "调查员" / "进化职业起源ACO_调查员变体.md",
            "进化职业起源ACO 勒彼斯塔德检察官",
            "## 进化职业起源ACO 勒彼斯塔德检察官",
        ),
        (
            "变体/page_579.md",
            "职业选项 → 萨满",
            "shaman_spirit",
            ORG_DIR / "职业" / "混合职业" / "萨满" / "进化职业起源ACO_萨满魂域.md",
            "进化职业起源ACO 古兽魂域",
            "## 进化职业起源ACO 古兽魂域",
        ),
        (
            "变体/page_580.md",
            "职业选项 → 歌者",
            "skald_archetypes",
            ORG_DIR / "职业" / "混合职业" / "歌者" / "进化职业起源ACO_歌者变体.md",
            "进化职业起源ACO 歌者变体",
            "## 进化职业起源ACO 歌者变体",
        ),
        (
            "变体/page_581.md",
            "职业选项 → 杀手",
            "slayer_archetypes",
            ORG_DIR / "职业" / "混合职业" / "杀手" / "进化职业起源ACO_杀手变体.md",
            "进化职业起源ACO 杀手变体",
            "## 进化职业起源ACO 杀手变体",
        ),
        (
            "变体/page_582.md",
            "职业选项 → 游荡剑客",
            "swashbuckler_archetypes",
            ORG_DIR / "职业" / "混合职业" / "游荡剑客" / "进化职业起源ACO_游荡剑客变体.md",
            "进化职业起源ACO 游荡剑客变体",
            "## 进化职业起源ACO 游荡剑客变体",
        ),
        (
            "变体/page_583.md",
            "职业选项 → 战斗祭司",
            "warpriest_archetypes",
            ORG_DIR / "职业" / "混合职业" / "战斗祭司" / "进化职业起源ACO_战斗祭司变体.md",
            "进化职业起源ACO 战斗祭司变体",
            "## 进化职业起源ACO 战斗祭司变体",
        ),
    ]

    for src_name, l3, entry_name, target, title, heading in variant_pages:
        block = clean_aggregate((SRC_DIR / src_name).read_text(encoding="utf-8"))
        block = _normalize_stars(block)
        block = _collapse_blank_lines(block.strip())
        if block:
            process_aggregate(
                report,
                src_name,
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
