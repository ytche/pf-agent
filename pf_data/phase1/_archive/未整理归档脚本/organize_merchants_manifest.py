#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 商人货单（Merchant's Manifest）内容到已有分类目录。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/商人货单MM"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "MerchantsManifest_reorganization_report.md"

SOURCE_BOOK = "商人货单（Merchant's Manifest）"
SOURCE_BOOK_SHORT = "商人货单MM"


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
    block = clean_aggregate((SRC_DIR / "背景特性8.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "背景特性8.md",
            "角色选项 → 背景特性",
            "background_traits",
            ORG_DIR / "角色" / "背景" / "商人货单MM_背景特性.md",
            "商人货单MM 贸易相关背景特性",
            "## 商人货单MM 贸易相关背景特性",
            block=block,
        )

    # 2. 吟游诗人传世名作
    block = clean_aggregate((SRC_DIR / "传世名作.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "传世名作.md",
            "职业选项 → 吟游诗人",
            "bard_masterpieces",
            ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "商人货单MM_传世名作.md",
            "商人货单MM 吟游诗人传世名作",
            "## 商人货单MM 吟游诗人传世名作",
            block=block,
        )

    # 3. 游荡者变体
    block = clean_aggregate((SRC_DIR / "盗贼变体1.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "盗贼变体1.md",
            "职业选项 → 游荡者",
            "rogue_archetype",
            ORG_DIR / "职业" / "基础职业" / "游荡者" / "商人货单MM_游荡者变体.md",
            "商人货单MM 无名之影",
            "## 商人货单MM 无名之影",
            block=block,
        )

    # 4. 服务/规则
    block = clean_aggregate((SRC_DIR / "服务.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "服务.md",
            "规则 → 服务",
            "services",
            ORG_DIR / "规则" / "商人货单MM_服务.md",
            "商人货单MM 服务",
            "## 商人货单MM 服务",
            block=block,
        )

    # 5. 骑士骑士团
    block = clean_aggregate((SRC_DIR / "骑士团.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "骑士团.md",
            "职业选项 → 骑士",
            "cavalier_order",
            ORG_DIR / "职业" / "基础职业" / "骑士" / "商人货单MM_骑士团.md",
            "商人货单MM 缰绳骑士团",
            "## 商人货单MM 缰绳骑士团",
            block=block,
        )

    # 6. 审判者变体
    block = clean_aggregate((SRC_DIR / "审判者变体.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "审判者变体.md",
            "职业选项 → 审判者",
            "inquisitor_archetype",
            ORG_DIR / "职业" / "基础职业" / "审判者" / "商人货单MM_审判者变体.md",
            "商人货单MM 契约监督者",
            "## 商人货单MM 契约监督者",
            block=block,
        )

    # 7. 物品：纪念物
    block = clean_aggregate((SRC_DIR / "物品" / "纪念物.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "物品/纪念物.md",
            "装备/物品",
            "souvenirs",
            ORG_DIR / "装备_魔法物品" / "商人货单MM_纪念物.md",
            "商人货单MM 纪念物",
            "## 商人货单MM 纪念物",
            block=block,
        )

    # 8. 物品：炼金/毒药
    block = clean_aggregate((SRC_DIR / "物品" / "炼金_毒药.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "物品/炼金_毒药.md",
            "装备/物品",
            "poison",
            ORG_DIR / "装备_魔法物品" / "商人货单MM_毒药.md",
            "商人货单MM 力之荒疫",
            "## 商人货单MM 力之荒疫",
            block=block,
        )

    # 9. 物品：食物
    block = clean_aggregate((SRC_DIR / "物品" / "食物.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "物品/食物.md",
            "装备/物品",
            "food",
            ORG_DIR / "装备_魔法物品" / "商人货单MM_食物.md",
            "商人货单MM 食物与饮料",
            "## 商人货单MM 食物与饮料",
            block=block,
        )

    # 10. 物品：特殊材料
    block = clean_aggregate((SRC_DIR / "物品" / "特殊材料1.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "物品/特殊材料1.md",
            "装备/物品",
            "special_materials",
            ORG_DIR / "装备_魔法物品" / "商人货单MM_特殊材料.md",
            "商人货单MM 特殊材料",
            "## 商人货单MM 特殊材料",
            block=block,
        )

    # 11. 物品：新增武器防具
    block = clean_aggregate((SRC_DIR / "物品" / "新增武器防具.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "物品/新增武器防具.md",
            "装备/物品",
            "weapons_armor",
            ORG_DIR / "装备_魔法物品" / "商人货单MM_武器防具.md",
            "商人货单MM 新增武器防具",
            "## 商人货单MM 新增武器防具",
            block=block,
        )

    # 12. 物品：装备
    block = clean_aggregate((SRC_DIR / "物品" / "装备1.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "物品/装备1.md",
            "装备/物品",
            "equipment",
            ORG_DIR / "装备_魔法物品" / "商人货单MM_装备.md",
            "商人货单MM 装备",
            "## 商人货单MM 装备",
            block=block,
        )

    # 13. 物品：魔法物品
    block = clean_aggregate((SRC_DIR / "物品" / "魔法物品2.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "物品/魔法物品2.md",
            "装备/魔法物品",
            "magic_items",
            ORG_DIR / "装备_魔法物品" / "商人货单MM_魔法物品.md",
            "商人货单MM 魔法物品",
            "## 商人货单MM 魔法物品",
            block=block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
