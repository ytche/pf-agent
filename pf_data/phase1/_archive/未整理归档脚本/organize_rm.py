#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 敌手指南（Rival Guide）RM 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/敌手指南RM/
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/敌手指南RM"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "RM_reorganization_report.md"

SOURCE_BOOK = "敌手指南（Rival Guide）RM"
SOURCE_BOOK_SHORT = "RM"


def write_text_preserve(path: Path, text: str, line_ending: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\n", line_ending), encoding="utf-8")


def read_text_preserve(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    line_ending = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8"), line_ending


def append_to_file(path: Path, text: str) -> None:
    if not path.exists():
        write_text_preserve(path, "")
    existing, line_ending = read_text_preserve(path)
    existing = existing.replace("\r", "")
    if existing and not existing.endswith("\n"):
        existing += "\n"
    write_text_preserve(path, existing + text, line_ending)


def make_source_annotation(source_file: str, l3: str = "") -> str:
    l3_part = f" → {l3}" if l3 else ""
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 敌手指南RM{l3_part}"


def make_hidden_marker(source_file: str, entry_name: str) -> str:
    return f"<!-- {SOURCE_BOOK_SHORT}-source:{source_file}:{entry_name} -->"


def merge_section_heading_lines(text: str) -> str:
    lines = text.splitlines()
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*#+", line) and not line.rstrip().endswith(("）", ")", "]", "］")):
            j = i + 1
            buf = line
            while j < len(lines):
                next_line = lines[j]
                buf += " " + next_line.strip()
                if re.search(r"[）)］\]]\s*$", next_line):
                    break
                j += 1
            merged.append(buf)
            i = j + 1
        else:
            merged.append(line)
            i += 1
    return "\n".join(merged)


def merge_crossline_bold(text: str) -> str:
    lines = text.splitlines()
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        count = line.count("**")
        if count % 2 != 0:
            j = i + 1
            buf = line
            while j < len(lines):
                buf += " " + lines[j].strip()
                count += lines[j].count("**")
                if count % 2 == 0:
                    break
                j += 1
            merged.append(buf)
            i = j + 1
        else:
            merged.append(line)
            i += 1
    return "\n".join(merged)


def clean_translator_url(text: str) -> str:
    lines = text.splitlines()
    if lines and (
        lines[0].strip().startswith("[http")
        or re.match(r"^https?://", lines[0].strip())
        or "整理者" in lines[0]
        or "译者" in lines[0]
    ):
        lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return "\n".join(lines)


def clean_leading_image(text: str) -> str:
    """移除 Markdown 图片语法行，例如 ![[图片]](url)"""
    lines = text.splitlines()
    while lines and re.match(r"^\s*!\[.*\]\(.*\)\s*$", lines[0].strip()):
        lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return "\n".join(lines)


def extract_block_whole_file(text: str) -> str:
    text = clean_translator_url(text)
    text = clean_leading_image(text)
    return text.strip()


def find_entry_headings(section_text: str, entries: list[dict]) -> list[tuple[int, dict, str]]:
    positions = []
    for entry in entries:
        name = entry["name"]
        english = entry.get("english", "")
        eng_pat = re.escape(english).replace(r"\ ", r"\s+")
        patterns = [
            re.compile(r"(?:^|\n)\s*\*\*[^*]*?(?<![一-鿿])" + re.escape(name) + r"(?![一-鿿])[^*]*?\*\*", re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*[（(]\s*[^）)]*?" + eng_pat + r"[^）)]*?\s*[）)]", re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*[（(][^）)]+[）)]\s*" + eng_pat, re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*" + eng_pat, re.IGNORECASE),
        ]
        found = False
        for pattern in patterns:
            m = pattern.search(section_text)
            if m:
                start = m.start()
                if start >= 2 and section_text[start - 2:start] == "**":
                    start -= 2
                positions.append((start, entry, m.group(0)))
                found = True
                break
        if not found:
            pattern = re.compile(re.escape(name), re.IGNORECASE)
            m = pattern.search(section_text)
            if m:
                positions.append((m.start(), entry, m.group(0)))
    positions.sort(key=lambda x: x[0])
    return positions


def split_section_by_entries(section_text: str, entries: list[dict]) -> dict[str, str]:
    positions = find_entry_headings(section_text, entries)
    blocks = {}
    for i, (pos, entry, heading) in enumerate(positions):
        start = pos
        end = positions[i + 1][0] if i + 1 < len(positions) else len(section_text)
        blocks[entry["name"]] = section_text[start:end].strip()
    return blocks


def append_entry(path: Path, marker: str, heading: str, source_annotation: str, block: str, report: dict, item_type: str, item_name: str, target_rel: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_preserve(path, heading.split("\n")[0].split("（")[0].strip() + "\n\n", "\n")
    existing, _ = read_text_preserve(path)
    if marker in existing:
        report["skipped"].append(f"{item_type}已存在: {item_name}")
        return
    entry = f"\n{marker}\n{heading}\n{source_annotation}\n{block}\n\n"
    append_to_file(path, entry)
    report["merged"].append({"type": item_type, "name": item_name, "target": target_rel})


# ========== 1. 专长 ==========

FEATS = [
    {"name": "循环进攻", "english": "Circling Offense", "source_file": "专长53.md"},
    {"name": "足锯师", "english": "Footslasher", "source_file": "专长53.md"},
    {"name": "翻敌覆寇", "english": "Topple Foe", "source_file": "专长53.md"},
    {"name": "鞭如灵蛇", "english": "Serpent Lash", "source_file": "专长53.md"},
    {"name": "高等鞭如灵蛇", "english": "Greater Serpent Lash", "source_file": "专长53.md"},
    {"name": "杀戮袭行", "english": "Slaying Sprint", "source_file": "专长53.md"},
    {"name": "豺产", "english": "Jackal Heritage", "source_file": "专长53.md"},
    {"name": "吸血鬼化动物伙伴", "english": "Jackal Heritage", "source_file": "专长53.md"},
]


def process_feats(report: dict) -> None:
    target_path = ORG_DIR / "专长" / "敌手指南RM_专长.md"

    text = (SRC_DIR / "专长53.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    blocks = split_section_by_entries(text, FEATS)

    for feat in FEATS:
        block = blocks.get(feat["name"])
        if block is None:
            report["warnings"].append(f"未找到专长块: {feat['name']}")
            continue
        marker = make_hidden_marker(feat["source_file"], feat["name"])
        append_entry(
            target_path,
            marker,
            f"## {feat['name']}（{feat['english']}）",
            make_source_annotation(feat["source_file"], "专长"),
            block,
            report,
            "专长",
            feat["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 2. 物品（源书聚合） ==========

def process_items(report: dict) -> None:
    target_path = ORG_DIR / "装备_魔法物品" / "敌手指南RM_物品.md"

    text = (SRC_DIR / "物品13.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    marker = make_hidden_marker("物品13.md", "物品")
    append_entry(
        target_path,
        marker,
        "## 物品",
        make_source_annotation("物品13.md", "物品"),
        text.strip(),
        report,
        "物品",
        "物品",
        str(target_path.relative_to(ORG_DIR)),
    )


# ========== 3. 魔法物品（源书聚合） ==========

def process_magic_items(report: dict) -> None:
    target_path = ORG_DIR / "装备_魔法物品" / "敌手指南RM_魔法物品.md"

    text = (SRC_DIR / "魔法物品13.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    marker = make_hidden_marker("魔法物品13.md", "魔法物品")
    append_entry(
        target_path,
        marker,
        "## 魔法物品",
        make_source_annotation("魔法物品13.md", "魔法物品"),
        text.strip(),
        report,
        "魔法物品",
        "魔法物品",
        str(target_path.relative_to(ORG_DIR)),
    )


# ========== 报告 ==========

def write_report(report: dict) -> None:
    lines = [f"# {SOURCE_BOOK} 整理报告\n", f"\n生成时间：{datetime.now().isoformat()}\n"]
    lines.append("\n## 整理内容\n")
    for item in report["merged"]:
        lines.append(f"- **{item['type']}**：{item['name']} → `{item['target']}`")
    lines.append("\n## 跳过项\n")
    for item in report["skipped"]:
        lines.append(f"- {item}")
    if report["warnings"]:
        lines.append("\n## 警告\n")
        for item in report["warnings"]:
            lines.append(f"- {item}")
    else:
        lines.append("\n## 警告\n\n无\n")
    write_text_preserve(REPORT_PATH, "\n".join(lines))


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}
    process_feats(report)
    process_items(report)
    process_magic_items(report)
    report["warnings"].append(
        "备注：专长“吸血鬼化动物伙伴”源文标题英文为 Jackal Heritage，与条目内容（吸血鬼化动物伙伴）明显不符，疑似译者错放；已按源文保留，建议人工复核。"
    )
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
