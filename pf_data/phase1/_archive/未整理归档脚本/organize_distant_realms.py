#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 遥远国度（Distant Realms）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/遥远国度DR
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/遥远国度DR"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "DistantRealms_reorganization_report.md"

SOURCE_BOOK = "遥远国度（Distant Realms）"
SOURCE_BOOK_SHORT = "遥远国度DR"


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


ARCHETYPE_PATTERNS: list[tuple[re.Pattern, dict]] = [
    (
        re.compile(r"自我典范主义者\(Quintessentialist\)〔唤魂师变体〕"),
        {
            "entry": "quintessentialist",
            "title": "遥远国度DR 自我典范主义者",
            "heading": "## 遥远国度DR 自我典范主义者",
            "l3": "职业选项 → 唤魂师",
            "target": ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "唤魂师" / "遥远国度DR_唤魂师变体.md",
        },
    ),
    (
        re.compile(r"自适应变形者\(Adaptive"),
        {
            "entry": "adaptive_shifter",
            "title": "遥远国度DR 自适应变形者",
            "heading": "## 遥远国度DR 自适应变形者",
            "l3": "职业选项 → 变形者",
            "target": ORG_DIR / "职业" / "极限荒野（Ultimate Wilderness）" / "变形者" / "遥远国度DR_变形者变体.md",
        },
    ),
    (
        re.compile(r"密识入信者\(Esoteric"),
        {
            "entry": "esoteric_initiate",
            "title": "遥远国度DR 密识入信者",
            "heading": "## 遥远国度DR 密识入信者",
            "l3": "职业选项 → 秘学士",
            "target": ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "秘学士" / "遥远国度DR_秘学士变体.md",
        },
    ),
    (
        re.compile(r"记忆炼成师（Mnemostiller）"),
        {
            "entry": "mnemostiller",
            "title": "遥远国度DR 记忆炼成师",
            "heading": "## 遥远国度DR 记忆炼成师",
            "l3": "职业选项 → 炼金术师",
            "target": ORG_DIR / "职业" / "基础职业" / "炼金术师" / "遥远国度DR_炼金术师.md",
        },
    ),
    (
        re.compile(r"第六翼盾卫\(战斗祭祀变体\)"),
        {
            "entry": "sixth_wing_bulwark",
            "title": "遥远国度DR 第六翼盾卫",
            "heading": "## 遥远国度DR 第六翼盾卫",
            "l3": "职业选项 → 战斗祭司",
            "target": ORG_DIR / "职业" / "混合职业" / "战斗祭司" / "遥远国度DR_战斗祭司变体.md",
        },
    ),
    (
        re.compile(r"界域旅者 Realm Wanderer \[游侠变体\]"),
        {
            "entry": "realm_wanderer",
            "title": "遥远国度DR 界域旅者",
            "heading": "## 遥远国度DR 界域旅者",
            "l3": "职业选项 → 游侠",
            "target": ORG_DIR / "职业" / "核心职业" / "游侠" / "遥远国度DR_游侠变体.md",
        },
    ),
]


def split_page_1319(text: str) -> list[dict]:
    lines = text.splitlines()
    blocks: list[dict] = []
    current: dict | None = None
    start = 0
    for i, line in enumerate(lines):
        for pat, info in ARCHETYPE_PATTERNS:
            if pat.search(line):
                if current is not None:
                    current["block"] = "\n".join(lines[start:i])
                    blocks.append(current)
                current = dict(info)
                start = i
                break
    if current is not None:
        current["block"] = "\n".join(lines[start:])
        blocks.append(current)
    return blocks


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. page_1319 多职业变体拆分
    page_text = clean_aggregate((SRC_DIR / "page_1319.md").read_text(encoding="utf-8"))
    for info in split_page_1319(page_text):
        block = _normalize_stars(info["block"])
        block = _collapse_blank_lines(block.strip())
        if block:
            process_aggregate(
                report,
                "page_1319.md",
                info["l3"],
                info["entry"],
                info["target"],
                info["title"],
                info["heading"],
                block=block,
            )

    # 2. 炼金术师科研发现（与 page_1319 记忆炼成师合并到同一目标）
    discovery_block = clean_aggregate((SRC_DIR / "科研发现3.md").read_text(encoding="utf-8"))
    discovery_block = _normalize_stars(discovery_block)
    discovery_block = _collapse_blank_lines(discovery_block.strip())
    if discovery_block:
        process_aggregate(
            report,
            "科研发现3.md",
            "职业选项 → 炼金术师",
            "distant_discoveries",
            ORG_DIR / "职业" / "基础职业" / "炼金术师" / "遥远国度DR_炼金术师.md",
            "遥远国度DR 炼金术师",
            "## 遥远国度DR 炼金术师科研发现",
            block=discovery_block,
        )

    # 3. 杀手天赋
    slayer_block = clean_aggregate((SRC_DIR / "杀手天赋.md").read_text(encoding="utf-8"))
    slayer_block = _normalize_stars(slayer_block)
    slayer_block = _collapse_blank_lines(slayer_block.strip())
    if slayer_block:
        process_aggregate(
            report,
            "杀手天赋.md",
            "职业选项 → 杀手",
            "slayer_talents",
            ORG_DIR / "职业" / "混合职业" / "杀手" / "遥远国度DR_杀手天赋.md",
            "遥远国度DR 杀手天赋",
            "## 遥远国度DR 杀手天赋",
            block=slayer_block,
        )

    # 4. 术士血统
    bloodline_block = clean_aggregate((SRC_DIR / "术士血统3.md").read_text(encoding="utf-8"))
    bloodline_block = _normalize_stars(bloodline_block)
    bloodline_block = _collapse_blank_lines(bloodline_block.strip())
    if bloodline_block:
        process_aggregate(
            report,
            "术士血统3.md",
            "职业选项 → 术士",
            "sorcerer_bloodline",
            ORG_DIR / "职业" / "核心职业" / "术士" / "遥远国度DR_术士血统.md",
            "遥远国度DR 术士血统",
            "## 遥远国度DR 术士血统",
            block=bloodline_block,
        )

    # 5. 特殊材料
    material_block = clean_aggregate((SRC_DIR / "特殊材料2.md").read_text(encoding="utf-8"))
    material_block = _normalize_stars(material_block)
    material_block = _collapse_blank_lines(material_block.strip())
    if material_block:
        process_aggregate(
            report,
            "特殊材料2.md",
            "装备/物品 → 特殊材料",
            "shadow_materials",
            ORG_DIR / "装备_魔法物品" / "特殊材料" / "遥远国度DR_特殊材料.md",
            "遥远国度DR 特殊材料",
            "## 遥远国度DR 特殊材料",
            block=material_block,
        )

    # 6. 专长：魔法技艺 + 专长9 合并
    feat_blocks: list[str] = []
    for src_file in ["魔法技艺.md", "专长9.md"]:
        block = clean_aggregate((SRC_DIR / src_file).read_text(encoding="utf-8"))
        block = _normalize_stars(block)
        block = strip_trailing_artifacts(block.strip())
        if block:
            feat_blocks.append(block)
    if feat_blocks:
        feat_block = _collapse_blank_lines("\n\n".join(feat_blocks))
        process_aggregate(
            report,
            "魔法技艺.md+专长9.md",
            "专长",
            "feats",
            ORG_DIR / "专长" / "遥远国度DR_专长.md",
            "遥远国度DR 专长",
            "## 遥远国度DR 专长",
            block=feat_block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
