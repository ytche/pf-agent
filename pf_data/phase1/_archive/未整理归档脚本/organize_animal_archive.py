#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 动物档案（Animal Archive）AArch 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/动物档案
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/动物档案"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "AnimalArchive_reorganization_report.md"

SOURCE_BOOK = "动物档案（Animal Archive）AArch"
SOURCE_BOOK_SHORT = "AArch"


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


def detect_line_ending(path: Path) -> str:
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 4096))
        tail = f.read()
    if b"\r\n" in tail:
        return "\r\n"
    return "\n"


def safe_append_to_file(path: Path, marker: str, heading: str, source_annotation: str, block: str) -> None:
    """以二进制追加方式写入，保留原文件行尾不变，避免重写整个文件导致行尾混乱。"""
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
        if len(content) >= len(le.encode("utf-8")) * 2 and content.endswith((le * 2).encode("utf-8")):
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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 动物档案AArch{l3_part}"


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


def split_at_heading(text: str, heading_pattern: str) -> tuple[str, str]:
    pattern = re.compile(heading_pattern, re.IGNORECASE)
    m = pattern.search(text)
    if not m:
        return text, ""
    return text[:m.start()].strip(), text[m.start():].strip()


def create_aggregation_file(path: Path, title: str, source_file: str, entries: list[tuple[str, str, str, str]], report: dict, item_type: str) -> None:
    """新建源书聚合文件；若文件已存在则跳过整本书写。"""
    if path.exists() and make_hidden_marker(source_file, "__aggregate__") in path.read_text(encoding="utf-8"):
        report["skipped"].append(f"{item_type}聚合文件已存在: {path.name}")
        return
    parts = [f"# {title}", "", make_hidden_marker(source_file, "__aggregate__"), ""]
    for marker, heading, source_annotation, block in entries:
        parts.append(marker)
        parts.append(heading)
        parts.append(source_annotation)
        parts.append("")
        parts.append(block)
        parts.append("")
        parts.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_preserve(path, "\n".join(parts), "\n")
    for _, heading, _, _ in entries:
        report["merged"].append({"type": item_type, "name": heading.lstrip("#").split("（")[0].strip(), "target": str(path.relative_to(ORG_DIR))})


def aggregate_whole_page(target_path: Path, title: str, source_file: str, heading: str, l3: str, report: dict, item_type: str) -> None:
    src_path = SRC_DIR / source_file
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    entry_marker = make_hidden_marker(source_file, heading.lstrip("# ").strip())
    entries = [(
        entry_marker,
        heading,
        make_source_annotation(source_file, l3),
        text.strip(),
    )]
    create_aggregation_file(target_path, title, source_file, entries, report, item_type)


# ========== 1. 动物专长 ==========

def process_animal_feats(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "专长" / "动物档案AArch_动物专长.md",
        "动物档案 AArch 动物专长",
        "page_437.md",
        "## 动物专长",
        "动物专长",
        report,
        "动物专长",
    )


# ========== 2. 动物变体（伙伴 + 魔宠） ==========

def process_animal_archetypes(report: dict) -> None:
    src_path = SRC_DIR / "page_438.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    # 以 "渗透魔宠" 作为魔宠变体段的起始标志（首个魔宠变体）
    companion_text, familiar_text = split_at_heading(text, r"渗透魔宠")

    if companion_text:
        aggregate_whole_page(
            ORG_DIR / "规则" / "动物档案AArch_动物伙伴变体.md",
            "动物档案 AArch 动物伙伴变体",
            "page_438.md",
            "## 动物伙伴变体",
            "动物变体 → 动物伙伴变体",
            report,
            "动物伙伴变体",
        )

    if familiar_text:
        # 为魔宠变体单独建聚合文件；由于源文件相同，需使用不同的 aggregate marker 名
        target_path = ORG_DIR / "规则" / "动物档案AArch_魔宠变体.md"
        source_file = "page_438.md"
        title = "动物档案 AArch 魔宠变体"
        heading = "## 魔宠变体"
        l3 = "动物变体 → 魔宠变体"
        item_type = "魔宠变体"

        if target_path.exists() and make_hidden_marker(source_file, "__aggregate_familiar__") in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"{item_type}聚合文件已存在: {target_path.name}")
            return

        parts = [f"# {title}", "", make_hidden_marker(source_file, "__aggregate_familiar__"), ""]
        entry_marker = make_hidden_marker(source_file, heading.lstrip("# ").strip())
        parts.append(entry_marker)
        parts.append(heading)
        parts.append(make_source_annotation(source_file, l3))
        parts.append("")
        parts.append(familiar_text.strip())
        parts.append("")
        parts.append("")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        write_text_preserve(target_path, "\n".join(parts), "\n")
        report["merged"].append({"type": item_type, "name": heading.lstrip("#").split("（")[0].strip(), "target": str(target_path.relative_to(ORG_DIR))})


# ========== 3. 法术 ==========

def process_spells(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "法术" / "动物档案AArch_法术.md",
        "动物档案 AArch 法术",
        "page_504.md",
        "## 法术",
        "法术",
        report,
        "法术",
    )


# ========== 4. 动物装备栏位 ==========

def process_equipment_slots(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "动物档案AArch_动物装备栏位.md",
        "动物档案 AArch 动物装备栏位",
        "page_519.md",
        "## 动物装备栏位",
        "动物装备栏位",
        report,
        "动物装备栏位",
    )


# ========== 5. 动物技巧 ==========

def process_animal_tricks(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "动物档案AArch_动物技巧.md",
        "动物档案 AArch 动物技巧",
        "page_674.md",
        "## 动物技巧",
        "动物技巧",
        report,
        "动物技巧",
    )


# ========== 6. 新动物伙伴 ==========

def process_new_companions(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "动物档案AArch_新动物伙伴.md",
        "动物档案 AArch 新动物伙伴",
        "page_696.md",
        "## 新动物伙伴",
        "新动物伙伴",
        report,
        "新动物伙伴",
    )


# ========== 7. 玩家变体（大多已存在）==========

ARCHETYPES = [
    {"source_file": "玩家变体/page_501.md", "class": "盗贼", "target": ORG_DIR / "职业" / "核心职业" / "盗贼" / "page_22.md", "names": ["游艺人"], "english": "Carnivalist"},
    {"source_file": "玩家变体/page_502.md", "class": "骑将", "target": ORG_DIR / "职业" / "基础职业" / "骑将" / "page_74.md", "names": ["围猎大师"], "english": "Huntmaster"},
]


def process_player_archetypes(report: dict) -> None:
    for arc in ARCHETYPES:
        src_path = SRC_DIR / arc["source_file"]
        target_path = arc["target"]
        text = src_path.read_text(encoding="utf-8")
        text = merge_section_heading_lines(text)
        text = merge_crossline_bold(text)
        text = clean_translator_url(text)
        text = clean_leading_image(text)

        marker = make_hidden_marker(arc["source_file"], "/".join(arc["names"]))
        existing = target_path.read_text(encoding="utf-8") if target_path.exists() else ""

        title_pattern = re.compile(re.escape(arc["names"][0]), re.IGNORECASE)
        if marker in existing or title_pattern.search(existing):
            report["skipped"].append(f"职业变体已存在: {arc['class']} {'/'.join(arc['names'])}（源文件中标注为{SOURCE_BOOK_SHORT}，目标页已含同名条目）")
            continue

        heading = f"## {'/'.join(arc['names'])}（{arc['english']}）【{SOURCE_BOOK_SHORT} {arc['class']}变体】"
        safe_append_to_file(
            target_path,
            marker,
            heading,
            make_source_annotation(arc['source_file'], '变体'),
            text.strip(),
        )
        report["merged"].append({
            "type": f"{arc['class']}变体",
            "name": "、".join(arc["names"]),
            "target": str(target_path.relative_to(ORG_DIR)),
        })


# ========== 8. 狂犬变体（已存在）+ 新狂暴之力 ==========

def process_mad_dog(report: dict) -> None:
    src_path = SRC_DIR / "玩家变体" / "page_503.md"
    archetype_target = ORG_DIR / "职业" / "核心职业" / "野蛮人" / "page_35.md"
    rage_target = ORG_DIR / "职业" / "核心职业" / "野蛮人" / "page_36.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    # 切分变体与狂暴之力
    archetype_text, rage_text = split_at_heading(text, r"引用")

    # 8.1 狂犬变体
    arc_marker = make_hidden_marker("玩家变体/page_503.md", "狂犬")
    existing = archetype_target.read_text(encoding="utf-8") if archetype_target.exists() else ""
    if arc_marker in existing or "狂犬" in existing:
        report["skipped"].append("职业变体已存在: 野蛮人 狂犬（源文件中标注为AArch，目标页已含同名条目）")
    else:
        heading = "## 狂犬（Mad Dog）【AArch 野蛮人变体】"
        safe_append_to_file(
            archetype_target,
            arc_marker,
            heading,
            make_source_annotation('玩家变体/page_503.md', '变体'),
            archetype_text.strip(),
        )
        report["merged"].append({"type": "野蛮人变体", "name": "狂犬", "target": str(archetype_target.relative_to(ORG_DIR))})

    # 8.2 新狂暴之力（凶兽 / 高等凶兽）
    if not rage_text:
        report["warnings"].append("未能在 page_503.md 中找到 引用 分段")
        return
    rage_marker = make_hidden_marker("玩家变体/page_503.md", "AArch新狂暴之力")
    existing_rage = rage_target.read_text(encoding="utf-8") if rage_target.exists() else ""
    if rage_marker in existing_rage or "凶兽" in existing_rage:
        report["skipped"].append("狂暴之力已存在: AArch 动物档案新狂暴之力")
    else:
        heading = "## 动物档案 AArch 新狂暴之力"
        safe_append_to_file(
            rage_target,
            rage_marker,
            heading,
            make_source_annotation('玩家变体/page_503.md', '狂暴之力'),
            rage_text.strip(),
        )
        report["merged"].append({"type": "狂暴之力", "name": "动物档案 AArch 新狂暴之力", "target": str(rage_target.relative_to(ORG_DIR))})


# ========== 9. 动物装备（仅去味剂；磨牙骨已在根目录动物装备.md） ==========

def process_equipment(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "动物档案AArch_装备.md",
        "动物档案 AArch 装备",
        "装备6.md",
        "## 去味剂",
        "装备",
        report,
        "装备",
    )


# ========== 报告 ==========

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
    if report["warnings"]:
        lines.append("\n## 警告\n")
        for item in report["warnings"]:
            lines.append(f"- {item}")
    else:
        lines.append("\n## 警告\n\n无\n")
    write_text_preserve(REPORT_PATH, "\n".join(lines))


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}
    process_animal_feats(report)
    process_animal_archetypes(report)
    process_spells(report)
    process_equipment_slots(report)
    process_animal_tricks(report)
    process_new_companions(report)
    process_player_archetypes(report)
    process_mad_dog(report)
    process_equipment(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
