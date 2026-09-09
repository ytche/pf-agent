#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 邪恶特务（Agents of Evil）内容到已有分类目录。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/邪恶特务Agents of Evil"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "AgentsOfEvil_reorganization_report.md"

SOURCE_BOOK = "邪恶特务（Agents of Evil）"
SOURCE_BOOK_SHORT = "邪恶特务AoE"


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


def split_at_heading(text: str, pattern: str) -> tuple[str, str] | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return text[: match.start()].strip(), text[match.start():].strip()


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 背景特性
    block = clean_aggregate((SRC_DIR / "背景特性30.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "背景特性30.md",
            "角色选项 → 背景特性",
            "background_traits",
            ORG_DIR / "角色" / "背景" / "邪恶特务AoE_背景特性.md",
            "邪恶特务AoE 背景特性",
            "## 邪恶特务AoE 背景特性",
            block=block,
        )

    # 2. 变体.md：召唤师变体 + 牧师变体 拆分
    page_text = clean_aggregate((SRC_DIR / "变体.md").read_text(encoding="utf-8"))
    split = split_at_heading(page_text, r"\n\*\*调和者")
    if split is None:
        report["warnings"].append("变体.md 未找到调和者分隔点，整段写入召唤师变体")
        summoner_block = page_text
        cleric_block = ""
    else:
        summoner_block, cleric_block = split

    summoner_block = _normalize_stars(summoner_block)
    summoner_block = _collapse_blank_lines(summoner_block.strip())
    if summoner_block:
        process_aggregate(
            report,
            "变体.md",
            "职业选项 → 召唤师",
            "unchained_summoner_archetype",
            ORG_DIR / "职业" / "基础职业" / "召唤师" / "邪恶特务AoE_召唤师变体.md",
            "邪恶特务AoE 魔鬼冒充者",
            "## 邪恶特务AoE 魔鬼冒充者",
            block=summoner_block,
        )

    cleric_block = _normalize_stars(cleric_block)
    cleric_block = _collapse_blank_lines(cleric_block.strip())
    if cleric_block:
        process_aggregate(
            report,
            "变体.md",
            "职业选项 → 牧师",
            "cleric_archetype",
            ORG_DIR / "职业" / "核心职业" / "牧师" / "邪恶特务AoE_牧师变体.md",
            "邪恶特务AoE 调和者",
            "## 邪恶特务AoE 调和者",
            block=cleric_block,
        )

    # 3. 法术
    block = clean_aggregate((SRC_DIR / "page_394.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "page_394.md",
            "规则 → 法术",
            "spells",
            ORG_DIR / "规则" / "邪恶特务AoE_法术.md",
            "邪恶特务AoE 法术",
            "## 邪恶特务AoE 法术",
            block=block,
        )

    # 4. 专长（故事专长）
    block = clean_aggregate((SRC_DIR / "page_1276.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "page_1276.md",
            "角色选项 → 专长",
            "story_feats",
            ORG_DIR / "角色" / "专长" / "邪恶特务AoE_专长.md",
            "邪恶特务AoE 故事专长",
            "## 邪恶特务AoE 故事专长",
            block=block,
        )

    # 5. 魔法物品 page_395：盔甲/武器附魔与特殊魔法武器
    block = clean_aggregate((SRC_DIR / "魔法物品" / "page_395.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "魔法物品/page_395.md",
            "装备/魔法物品",
            "magic_weapons_armor",
            ORG_DIR / "装备_魔法物品" / "邪恶特务AoE_武器防具附魔与特殊武器.md",
            "邪恶特务AoE 武器防具附魔与特殊武器",
            "## 邪恶特务AoE 武器防具附魔与特殊武器",
            block=block,
        )

    # 6. 魔法物品 page_396：奇物与毒药
    block = clean_aggregate((SRC_DIR / "魔法物品" / "page_396.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "魔法物品/page_396.md",
            "装备/魔法物品",
            "wondrous_items_poison",
            ORG_DIR / "装备_魔法物品" / "邪恶特务AoE_奇物与毒药.md",
            "邪恶特务AoE 奇物与毒药",
            "## 邪恶特务AoE 奇物与毒药",
            block=block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
