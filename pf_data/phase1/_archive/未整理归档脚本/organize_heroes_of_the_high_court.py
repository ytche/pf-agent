#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 皇庭英豪（Heroes of the High Court）内容到已有分类目录。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/皇庭英豪HotHC"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "HeroesOfTheHighCourt_reorganization_report.md"

SOURCE_BOOK = "皇庭英豪（Heroes of the High Court）"
SOURCE_BOOK_SHORT = "皇庭英豪HotHC"


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
        or lines[-1].strip() == "---"
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


CLASS_PATHS = {
    "圣武士": ("职业/核心职业/圣武士", "圣武士"),
    "骑士": ("职业/基础职业/骑士", "骑士"),
    "炼金术师": ("职业/基础职业/炼金术师", "炼金术师"),
    "武僧": ("职业/核心职业/武僧", "武僧"),
    "秘学士": ("职业/基础职业/秘学士", "秘学士"),
    "战士": ("职业/核心职业/战士", "战士"),
    "侠客": ("职业/混合职业/侠客", "侠客"),
    "杀手": ("职业/混合职业/杀手", "杀手"),
    "铳士": ("职业/基础职业/铳士", "铳士"),
    "先知": ("职业/基础职业/先知", "先知"),
    "歌者": ("职业/混合职业/歌者", "歌者"),
    "吟游诗人": ("职业/核心职业/吟游诗人", "吟游诗人"),
    "女巫": ("职业/基础职业/女巫", "女巫"),
}


def split_archetypes(text: str) -> list[tuple[str, str, str, str]]:
    """Split page_671.md into (class_name, archetype_cn, archetype_en, block)."""
    pattern = re.compile(r"\*\*([^*（）()]+?)\s*[（(]([^）()]+)[）)]\s*【([^】]+)】")
    matches = list(pattern.finditer(text))
    results = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        results.append((m.group(3).strip(), m.group(1).strip(), m.group(2).strip(), block))
    return results


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 背景特性
    block = clean_aggregate((SRC_DIR / "背景特性7.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "背景特性7.md",
            "角色选项 → 背景特性",
            "background_traits",
            ORG_DIR / "角色" / "背景" / "皇庭英豪HotHC_背景特性.md",
            "皇庭英豪HotHC 背景特性",
            "## 皇庭英豪HotHC 背景特性",
            block=block,
        )

    # 2. 茶道仪式
    block = clean_aggregate((SRC_DIR / "茶道仪式.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "茶道仪式.md",
            "规则 → 神秘仪式",
            "occult_ritual",
            ORG_DIR / "规则" / "皇庭英豪HotHC_茶道仪式.md",
            "皇庭英豪HotHC 茶道赐福",
            "## 皇庭英豪HotHC 茶道赐福",
            block=block,
        )

    # 3. 科研发现
    block = clean_aggregate((SRC_DIR / "科研发现.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "科研发现.md",
            "职业选项 → 炼金术师",
            "alchemist_discoveries",
            ORG_DIR / "职业" / "基础职业" / "炼金术师" / "皇庭英豪HotHC_科研发现.md",
            "皇庭英豪HotHC 炼金术师科研发现",
            "## 皇庭英豪HotHC 炼金术师科研发现",
            block=block,
        )

    # 4. 牧师子域
    block = clean_aggregate((SRC_DIR / "牧师子域1.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "牧师子域1.md",
            "职业选项 → 牧师",
            "cleric_subdomains",
            ORG_DIR / "职业" / "核心职业" / "牧师" / "皇庭英豪HotHC_子域.md",
            "皇庭英豪HotHC 牧师子域",
            "## 皇庭英豪HotHC 牧师子域",
            block=block,
        )

    # 5. 替换种族特性
    block = clean_aggregate((SRC_DIR / "替换种族特性.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "替换种族特性.md",
            "角色选项 → 种族特性",
            "racial_traits",
            ORG_DIR / "角色" / "种族" / "皇庭英豪HotHC_替换种族特性.md",
            "皇庭英豪HotHC 替换种族特性",
            "## 皇庭英豪HotHC 替换种族特性",
            block=block,
        )

    # 6. 女巫巫术与庇护主
    page_text = clean_aggregate((SRC_DIR / "巫术+庇护主.md").read_text(encoding="utf-8"))
    split = re.split(r"\n\-\-\-", page_text, maxsplit=1)
    if len(split) < 2:
        report["warnings"].append("巫术+庇护主.md 未找到分隔线，整段写入女巫巫术")
        witch_block = page_text
        patron_block = ""
    else:
        witch_block, patron_block = split

    witch_block = _normalize_stars(witch_block.strip())
    witch_block = _collapse_blank_lines(witch_block)
    if witch_block:
        process_aggregate(
            report,
            "巫术+庇护主.md",
            "职业选项 → 女巫",
            "witch_hexes",
            ORG_DIR / "职业" / "基础职业" / "女巫" / "皇庭英豪HotHC_巫术.md",
            "皇庭英豪HotHC 女巫巫术",
            "## 皇庭英豪HotHC 女巫巫术",
            block=witch_block,
        )

    patron_block = _normalize_stars(patron_block.strip())
    patron_block = _collapse_blank_lines(patron_block)
    if patron_block:
        process_aggregate(
            report,
            "巫术+庇护主.md",
            "职业选项 → 女巫",
            "witch_patron",
            ORG_DIR / "职业" / "基础职业" / "女巫" / "皇庭英豪HotHC_庇护主.md",
            "皇庭英豪HotHC 女巫庇护主",
            "## 皇庭英豪HotHC 女巫庇护主",
            block=patron_block,
        )

    # 7. page_671.md：多个职业变体拆分
    page_text = clean_aggregate((SRC_DIR / "page_671.md").read_text(encoding="utf-8"))
    archetypes = split_archetypes(page_text)
    if not archetypes:
        report["warnings"].append("page_671.md 未解析到任何变体")

    for class_name, archetype_cn, archetype_en, block in archetypes:
        if class_name not in CLASS_PATHS:
            report["warnings"].append(f"page_671.md 中未识别的职业：{class_name}（{archetype_cn}）")
            continue

        rel_dir, class_key = CLASS_PATHS[class_name]
        block = _normalize_stars(block)
        block = _collapse_blank_lines(block.strip())
        if not block:
            continue

        target_dir = ORG_DIR / rel_dir
        target_filename = f"{SOURCE_BOOK_SHORT}_{class_key}变体.md"
        target_path = target_dir / target_filename
        target_title = f"{SOURCE_BOOK_SHORT} {class_name}变体"
        heading = f"## {SOURCE_BOOK_SHORT} {class_name}变体"
        entry_name = f"{class_key}_archetypes"

        process_aggregate(
            report,
            "page_671.md",
            f"职业选项 → {class_name}",
            entry_name,
            target_path,
            target_title,
            heading,
            block=block,
        )

    # 8. page_1612.md：魔法物品
    block = clean_aggregate((SRC_DIR / "page_1612.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "page_1612.md",
            "装备/魔法物品",
            "magic_items",
            ORG_DIR / "装备_魔法物品" / "皇庭英豪HotHC_魔法物品.md",
            "皇庭英豪HotHC 魔法物品",
            "## 皇庭英豪HotHC 魔法物品",
            block=block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
