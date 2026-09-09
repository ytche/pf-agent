#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 河域子民（People of the River）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/河域子民PotR
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/河域子民PotR"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "PeopleOfTheRiver_reorganization_report.md"

SOURCE_BOOK = "河域子民（People of the River）"
SOURCE_BOOK_SHORT = "河域子民PotR"


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


# 变体文件映射：文件名模式 → (职业, 职业目录, 条目名)
ARCHETYPE_MAP: dict[str, tuple[str, Path, str]] = {
    "盗贼.md": ("盗贼", ORG_DIR / "职业" / "基础职业" / "盗贼" / "河域子民PotR_盗贼变体.md", "river_rat"),
    "德鲁伊1.md": ("德鲁伊", ORG_DIR / "职业" / "基础职业" / "德鲁伊" / "河域子民PotR_德鲁伊变体.md", "river_druid"),
    "女巫1.md": ("女巫", ORG_DIR / "职业" / "基础职业" / "女巫" / "河域子民PotR_女巫变体.md", "veneficus_witch"),
    "诗人传世名作.md": ("吟游诗人", ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "河域子民PotR_吟游诗人传世名作.md", "masterpieces"),
    "术士血统.md": ("术士", ORG_DIR / "职业" / "核心职业" / "术士" / "河域子民PotR_术士血统.md", "mutated_bloodline"),
    "野蛮人.md": ("野蛮人", ORG_DIR / "职业" / "核心职业" / "野蛮人" / "河域子民PotR_野蛮人变体.md", "numerian_liberator"),
    "游侠.md": ("游侠", ORG_DIR / "职业" / "核心职业" / "游侠" / "河域子民PotR_游侠变体.md", "galvanic_saboteur"),
}


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 背景特性
    trait_block = clean_aggregate((SRC_DIR / "背景特性2.md").read_text(encoding="utf-8"))
    trait_block = _normalize_stars(trait_block)
    trait_block = _collapse_blank_lines(trait_block.strip())
    if trait_block:
        process_aggregate(
            report,
            "背景特性2.md",
            "背景特性",
            "background_traits",
            ORG_DIR / "背景特性" / "河域子民PotR_背景特性.md",
            "河域子民PotR 背景特性",
            "## 河域子民PotR 背景特性",
            block=trait_block,
        )

    # 2. 专长
    feat_block = clean_aggregate((SRC_DIR / "专长3.md").read_text(encoding="utf-8"))
    feat_block = _normalize_stars(feat_block)
    feat_block = _collapse_blank_lines(feat_block.strip())
    if feat_block:
        process_aggregate(
            report,
            "专长3.md",
            "专长",
            "feats",
            ORG_DIR / "专长" / "河域子民PotR_专长.md",
            "河域子民PotR 专长",
            "## 河域子民PotR 专长",
            block=feat_block,
        )

    # 3. 新技能规则
    skill_block = clean_aggregate((SRC_DIR / "新技能规则.md").read_text(encoding="utf-8"))
    skill_block = _collapse_blank_lines(skill_block.strip())
    if skill_block:
        process_aggregate(
            report,
            "新技能规则.md",
            "规则",
            "new_skill_rules",
            ORG_DIR / "规则" / "河域子民PotR_新技能规则.md",
            "河域子民PotR 新技能规则",
            "## 河域子民PotR 新技能规则",
            block=skill_block,
        )

    # 4. 魔法物品
    item_block = clean_aggregate((SRC_DIR / "魔法物品.md").read_text(encoding="utf-8"))
    item_block = _normalize_stars(item_block)
    item_block = _collapse_blank_lines(item_block.strip())
    if item_block:
        process_aggregate(
            report,
            "魔法物品.md",
            "装备/物品 → 奇物",
            "magic_items",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "河域子民PotR_奇物.md",
            "河域子民PotR 奇物",
            "## 河域子民PotR 奇物",
            block=item_block,
        )

    # 5. 变体与选项
    variant_dir = SRC_DIR / "变体_选项"
    for src_file, (cls, target_path, entry_name) in ARCHETYPE_MAP.items():
        src_path = variant_dir / src_file
        if not src_path.exists():
            report["warnings"].append(f"变体文件缺失: {src_file}")
            continue
        block = clean_aggregate(src_path.read_text(encoding="utf-8"))
        block = _normalize_stars(block)
        block = _collapse_blank_lines(block.strip())
        if block:
            target_title = target_path.stem.replace("_", " ")
            process_aggregate(
                report,
                f"变体_选项/{src_file}",
                f"职业选项 → {cls}",
                entry_name,
                target_path,
                target_title,
                f"## {target_title}",
                block=block,
            )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
