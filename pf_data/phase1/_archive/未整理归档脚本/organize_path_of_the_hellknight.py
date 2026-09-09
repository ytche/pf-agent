#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 地狱骑士之道（Path of the Hellknight）内容到已有分类目录。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/地狱骑士之道PotH"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "PathOfTheHellknight_reorganization_report.md"

SOURCE_BOOK = "地狱骑士之道（Path of the Hellknight）"
SOURCE_BOOK_SHORT = "地狱骑士之道PotH"


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


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 背景特性
    block = clean_aggregate((SRC_DIR / "背景特性9.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "背景特性9.md",
            "角色选项 → 背景特性",
            "background_traits",
            ORG_DIR / "角色" / "背景" / "地狱骑士之道PotH_背景特性.md",
            "地狱骑士之道PotH 背景特性",
            "## 地狱骑士之道PotH 背景特性",
            block=block,
        )

    # 2. 专长
    block = clean_aggregate((SRC_DIR / "专长49.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "专长49.md",
            "角色选项 → 专长",
            "feats",
            ORG_DIR / "角色" / "专长" / "地狱骑士之道PotH_专长.md",
            "地狱骑士之道PotH 专长",
            "## 地狱骑士之道PotH 专长",
            block=block,
        )

    # 3. 物品
    block = clean_aggregate((SRC_DIR / "物品35.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "物品35.md",
            "装备/物品",
            "equipment",
            ORG_DIR / "装备_魔法物品" / "地狱骑士之道PotH_装备.md",
            "地狱骑士之道PotH 装备",
            "## 地狱骑士之道PotH 装备",
            block=block,
        )

    # 4. 魔法物品
    block = clean_aggregate((SRC_DIR / "魔法物品9.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "魔法物品9.md",
            "装备/魔法物品",
            "magic_items",
            ORG_DIR / "装备_魔法物品" / "地狱骑士之道PotH_魔法物品.md",
            "地狱骑士之道PotH 魔法物品",
            "## 地狱骑士之道PotH 魔法物品",
            block=block,
        )

    # 5. 神器
    block = clean_aggregate((SRC_DIR / "神器1.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "神器1.md",
            "装备/神器",
            "artifact",
            ORG_DIR / "装备_魔法物品" / "地狱骑士之道PotH_神器.md",
            "地狱骑士之道PotH 恶毒链接",
            "## 地狱骑士之道PotH 恶毒链接",
            block=block,
        )

    # 6. 地狱骑士戒律（进阶职业选项）
    block = clean_aggregate((SRC_DIR / "职业变体_选项" / "地狱骑士戒律.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "职业变体_选项/地狱骑士戒律.md",
            "职业选项 → 进阶职业 → 地狱骑士",
            "hellknight_disciplines",
            ORG_DIR / "职业" / "进阶职业" / "地狱骑士之道PotH_戒律.md",
            "地狱骑士之道PotH 地狱骑士戒律",
            "## 地狱骑士之道PotH 地狱骑士戒律",
            block=block,
        )

    # 7. 骑将变体与九刃星骑士团
    block = clean_aggregate((SRC_DIR / "职业变体_选项" / "骑将3.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "职业变体_选项/骑将3.md",
            "职业选项 → 骑士",
            "cavalier_archetype_order",
            ORG_DIR / "职业" / "基础职业" / "骑士" / "地狱骑士之道PotH_骑士变体与骑士团.md",
            "地狱骑士之道PotH 巡回法官与九刃星骑士团",
            "## 地狱骑士之道PotH 巡回法官与九刃星骑士团",
            block=block,
        )

    # 8. 侠客变体
    block = clean_aggregate((SRC_DIR / "职业变体_选项" / "侠客1.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "职业变体_选项/侠客1.md",
            "职业选项 → 侠客",
            "vigilante_archetype",
            ORG_DIR / "职业" / "混合职业" / "侠客" / "地狱骑士之道PotH_侠客变体.md",
            "地狱骑士之道PotH 无面执法者",
            "## 地狱骑士之道PotH 无面执法者",
            block=block,
        )

    # 9. 先知秘示域
    block = clean_aggregate((SRC_DIR / "职业变体_选项" / "先知秘示域.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "职业变体_选项/先知秘示域.md",
            "职业选项 → 先知",
            "oracle_mystery",
            ORG_DIR / "职业" / "基础职业" / "先知" / "地狱骑士之道PotH_秘示域.md",
            "地狱骑士之道PotH 神爪秘示域",
            "## 地狱骑士之道PotH 神爪秘示域",
            block=block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
