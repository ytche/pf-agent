#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 门徒教义（Disciple's Doctrine）内容到已有分类目录。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/门徒教义DD"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "DisciplesDoctrine_reorganization_report.md"

SOURCE_BOOK = "门徒教义（Disciple's Doctrine）"
SOURCE_BOOK_SHORT = "门徒教义DD"


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


def split_at_heading(text: str, pattern: str) -> tuple[str, str] | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return text[: match.start()].strip(), text[match.start():].strip()


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 唤魂师变体
    block = clean_aggregate((SRC_DIR / "唤魂师.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "唤魂师.md",
            "职业选项 → 唤魂师",
            "spiritualist_archetype",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "唤魂师" / "门徒教义DD_唤魂师变体.md",
            "门徒教义DD 领悟探求者",
            "## 门徒教义DD 领悟探求者",
            block=block,
        )

    # 2. 忍者变体
    block = clean_aggregate((SRC_DIR / "忍者.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "忍者.md",
            "职业选项 → 忍者",
            "ninja_archetype",
            ORG_DIR / "职业" / "基础职业" / "忍者" / "门徒教义DD_忍者变体.md",
            "门徒教义DD 活神假面",
            "## 门徒教义DD 活神假面",
            block=block,
        )

    # 3. 通灵者变体
    block = clean_aggregate((SRC_DIR / "通灵者.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "通灵者.md",
            "职业选项 → 通灵者",
            "medium_archetype",
            ORG_DIR / "职业" / "基础职业" / "通灵者" / "门徒教义DD_通灵者变体.md",
            "门徒教义DD 未达者之皿",
            "## 门徒教义DD 未达者之皿",
            block=block,
        )

    # 4. 武僧变体
    block = clean_aggregate((SRC_DIR / "武僧.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "武僧.md",
            "职业选项 → 武僧",
            "monk_archetype",
            ORG_DIR / "职业" / "核心职业" / "武僧" / "门徒教义DD_武僧变体.md",
            "门徒教义DD 四象僧",
            "## 门徒教义DD 四象僧",
            block=block,
        )

    # 5. 战斗祭司变体
    block = clean_aggregate((SRC_DIR / "战斗祭司1.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "战斗祭司1.md",
            "职业选项 → 战斗祭司",
            "warpriest_archetype",
            ORG_DIR / "职业" / "混合职业" / "战斗祭司" / "门徒教义DD_战斗祭司变体.md",
            "门徒教义DD 神爪之拳",
            "## 门徒教义DD 神爪之拳",
            block=block,
        )

    # 6. 魔法物品
    block = clean_aggregate((SRC_DIR / "物品33.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "物品33.md",
            "装备/魔法物品",
            "magic_items",
            ORG_DIR / "装备_魔法物品" / "门徒教义DD_魔法物品.md",
            "门徒教义DD 魔法物品",
            "## 门徒教义DD 魔法物品",
            block=block,
        )

    # 7. 神秘仪式
    block = clean_aggregate((SRC_DIR / "仪式4.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "仪式4.md",
            "规则 → 神秘仪式",
            "occult_rituals",
            ORG_DIR / "规则" / "门徒教义DD_神秘仪式.md",
            "门徒教义DD 神秘仪式",
            "## 门徒教义DD 神秘仪式",
            block=block,
        )

    # 8. page_1275：先知变体 + 调查员天赋 拆分
    page_text = clean_aggregate((SRC_DIR / "page_1275.md").read_text(encoding="utf-8"))
    split = split_at_heading(page_text, r"\n\*\*调查员天赋")
    if split is None:
        report["warnings"].append("page_1275.md 未找到调查员天赋分隔点，整段写入先知变体")
        oracle_block = page_text
        investigator_block = ""
    else:
        oracle_block, investigator_block = split

    oracle_block = _normalize_stars(oracle_block)
    oracle_block = _collapse_blank_lines(oracle_block.strip())
    if oracle_block:
        process_aggregate(
            report,
            "page_1275.md",
            "职业选项 → 先知",
            "oracle_archetype",
            ORG_DIR / "职业" / "基础职业" / "先知" / "门徒教义DD_先知变体.md",
            "门徒教义DD 钦天算师",
            "## 门徒教义DD 钦天算师",
            block=oracle_block,
        )

    investigator_block = _normalize_stars(investigator_block)
    investigator_block = _collapse_blank_lines(investigator_block.strip())
    if investigator_block:
        process_aggregate(
            report,
            "page_1275.md",
            "职业选项 → 调查员",
            "investigator_talents",
            ORG_DIR / "职业" / "混合职业" / "调查员" / "门徒教义DD_调查员天赋.md",
            "门徒教义DD 天机庭调查员天赋",
            "## 门徒教义DD 天机庭调查员天赋",
            block=investigator_block,
        )

    # 9. page_1329：武士变体 + 秘学士变体 拆分
    page_text = clean_aggregate((SRC_DIR / "page_1329.md").read_text(encoding="utf-8"))
    split = split_at_heading(page_text, r"\n\*\*秘会入信者")
    if split is None:
        report["warnings"].append("page_1329.md 未找到秘会入信者分隔点，整段写入武士变体")
        samurai_block = page_text
        occultist_block = ""
    else:
        samurai_block, occultist_block = split

    samurai_block = _normalize_stars(samurai_block)
    samurai_block = _collapse_blank_lines(samurai_block.strip())
    if samurai_block:
        process_aggregate(
            report,
            "page_1329.md",
            "职业选项 → 武士",
            "samurai_archetype",
            ORG_DIR / "职业" / "基础职业" / "武士" / "门徒教义DD_武士变体.md",
            "门徒教义DD 御灵卫",
            "## 门徒教义DD 御灵卫",
            block=samurai_block,
        )

    occultist_block = _normalize_stars(occultist_block)
    occultist_block = _collapse_blank_lines(occultist_block.strip())
    if occultist_block:
        process_aggregate(
            report,
            "page_1329.md",
            "职业选项 → 秘学士",
            "occultist_archetype",
            ORG_DIR / "职业" / "基础职业" / "秘学士" / "门徒教义DD_秘学士变体.md",
            "门徒教义DD 秘会入信者",
            "## 门徒教义DD 秘会入信者",
            block=occultist_block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
