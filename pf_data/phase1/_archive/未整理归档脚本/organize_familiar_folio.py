#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 魔宠手记（Familiar Folio）FF 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/魔宠手记
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/魔宠手记"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "FamiliarFolio_reorganization_report.md"

SOURCE_BOOK = "魔宠手记（Familiar Folio）FF"
SOURCE_BOOK_SHORT = "FF"


def write_text_preserve(path: Path, text: str, line_ending: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\n", line_ending), encoding="utf-8")


def read_text_preserve(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    line_ending = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8"), line_ending


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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 魔宠手记FF{l3_part}"


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


# ========== 1. 魔宠选项（含普通与进阶魔宠表格）==========

def process_familiar_options(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "魔宠手记FF_魔宠选项.md",
        "魔宠手记 FF 魔宠选项",
        "page_476.md",
        "## 魔宠选项",
        "魔宠选项",
        report,
        "魔宠选项",
    )


# ========== 2. 近似魔宠 ==========

def process_approximating_familiars(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "魔宠手记FF_近似魔宠.md",
        "魔宠手记 FF 近似魔宠",
        "page_485.md",
        "## 近似魔宠",
        "近似魔宠",
        report,
        "近似魔宠",
    )


# ========== 3. 魔宠变体 ==========

def process_familiar_archetypes(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "魔宠手记FF_魔宠变体.md",
        "魔宠手记 FF 魔宠变体",
        "page_486.md",
        "## 魔宠变体",
        "魔宠变体",
        report,
        "魔宠变体",
    )


# ========== 4. 学派魔宠（含专长与变体）==========

def process_school_familiars(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "魔宠手记FF_学派魔宠.md",
        "魔宠手记 FF 学派魔宠",
        "page_487.md",
        "## 学派魔宠",
        "学派魔宠",
        report,
        "学派魔宠",
    )


# ========== 5. 魔宠专长 ==========

def process_familiar_feats(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "专长" / "魔宠手记FF_专长.md",
        "魔宠手记 FF 专长",
        "page_491.md",
        "## 魔宠专长",
        "专长",
        report,
        "专长",
    )


# ========== 6. 装备与魔法物品 ==========

def process_equipment(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "魔宠手记FF_装备与魔法物品.md",
        "魔宠手记 FF 装备与魔法物品",
        "page_492.md",
        "## 装备与魔法物品",
        "装备与魔法物品",
        report,
        "装备与魔法物品",
    )


# ========== 7. 新魔宠 ==========

def process_new_familiars(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "魔宠手记FF_新魔宠.md",
        "魔宠手记 FF 新魔宠",
        "page_518.md",
        "## 新魔宠",
        "新魔宠",
        report,
        "新魔宠",
    )


# ========== 8. 新罕见魔宠 ==========

def process_new_unusual_familiars(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "魔宠手记FF_新罕见魔宠.md",
        "魔宠手记 FF 新罕见魔宠",
        "新罕见魔宠.md",
        "## 新罕见魔宠",
        "新罕见魔宠",
        report,
        "新罕见魔宠",
    )


# ========== 9. 混血魔宠 ==========

def process_bloodline_familiars(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "魔宠手记FF_混血魔宠.md",
        "魔宠手记 FF 混血魔宠",
        "魔宠选项/page_489.md",
        "## 混血魔宠",
        "魔宠选项 → 混血魔宠",
        report,
        "混血魔宠",
    )


# ========== 10. 眷属魔宠 ==========

def process_patron_familiars(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "魔宠手记FF_眷属魔宠.md",
        "魔宠手记 FF 眷属魔宠",
        "魔宠选项/page_490.md",
        "## 眷属魔宠",
        "魔宠选项 → 眷属魔宠",
        report,
        "眷属魔宠",
    )


# ========== 11. 职业变体 ==========

ARCHETYPES = [
    {"source_file": "职业变体/page_477.md", "class": "圣武士", "target": ORG_DIR / "职业" / "核心职业" / "圣骑士" / "page_55.md", "names": ["神选之子"], "english": "Chosen One"},
    {"source_file": "职业变体/page_478.md", "class": "吟游诗人", "target": ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "page_38.md", "names": ["二重奏者"], "english": "Duettist"},
    {"source_file": "职业变体/page_479.md", "class": "战士", "target": ORG_DIR / "职业" / "核心职业" / "战士" / "page_49.md", "names": ["奥法侍卫"], "english": "Eldritch Guardian"},
    {"source_file": "职业变体/page_480.md", "class": "德鲁伊", "target": ORG_DIR / "职业" / "核心职业" / "德鲁伊" / "page_45.md", "names": ["莱西戍卫"], "english": "Leshy Warden"},
    {"source_file": "职业变体/page_481.md", "class": "魔战士", "target": ORG_DIR / "职业" / "基础职业" / "魔战士" / "page_82.md", "names": ["兽之刃"], "english": "Beastblade"},
    {"source_file": "职业变体/page_483.md", "class": "女巫", "target": ORG_DIR / "职业" / "基础职业" / "女巫" / "page_70.md", "names": ["共生使"], "english": "Synergist"},
    {"source_file": "职业变体/page_484.md", "class": "炼金术师", "target": ORG_DIR / "职业" / "基础职业" / "炼金术师" / "page_71.md", "names": ["创生师"], "english": "Homunculist"},
]


def process_single_archetypes(report: dict) -> None:
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


def strip_trailing_artifacts(block: str) -> str:
    """去除源文件切分后留在段尾的孤立 ** / **** 标记与空行。"""
    lines = block.splitlines()
    while lines and (lines[-1].strip() == "" or re.match(r"^\*+$", lines[-1].strip())):
        lines.pop()
    return "\n".join(lines)


def process_wizard_archetypes(report: dict) -> None:
    """page_482.md 包含三个法师变体：魔宠大师、契约法师、缚灵师。"""
    src_path = SRC_DIR / "职业变体" / "page_482.md"
    target_path = ORG_DIR / "职业" / "核心职业" / "法师" / "page_67.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    existing = target_path.read_text(encoding="utf-8") if target_path.exists() else ""

    wizard_archetypes = [
        ("魔宠大师", "Familiar Adept"),
        ("契约法师", "Pact Wizard"),
        ("缚灵师", "Spirit Binder"),
    ]

    # 按变体标题切分，保留标题行的前导 **
    split_pattern = "|".join(re.escape(name) + r"（法师变体）" for name, _ in wizard_archetypes)
    raw_sections = re.split(rf"(?=^\*\*(?:{split_pattern}))", text, flags=re.MULTILINE)
    raw_sections = [s.strip() for s in raw_sections if s.strip()]

    sections: list[tuple[str, str, str]] = []
    for idx, (name, english) in enumerate(wizard_archetypes):
        if idx < len(raw_sections):
            sections.append((name, english, strip_trailing_artifacts(raw_sections[idx])))

    for name, english, block in sections:
        marker = make_hidden_marker("职业变体/page_482.md", name)
        if marker in existing or name in existing:
            report["skipped"].append(f"职业变体已存在: 法师 {name}（源文件中标注为{SOURCE_BOOK_SHORT}，目标页已含同名条目）")
            continue
        heading = f"## {name}（{english}）【{SOURCE_BOOK_SHORT} 法师变体】"
        safe_append_to_file(
            target_path,
            marker,
            heading,
            make_source_annotation('职业变体/page_482.md', '变体'),
            block,
        )
        report["merged"].append({"type": "法师变体", "name": name, "target": str(target_path.relative_to(ORG_DIR))})


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
    process_familiar_options(report)
    process_approximating_familiars(report)
    process_familiar_archetypes(report)
    process_school_familiars(report)
    process_familiar_feats(report)
    process_equipment(report)
    process_new_familiars(report)
    process_new_unusual_familiars(report)
    process_bloodline_familiars(report)
    process_patron_familiars(report)
    process_single_archetypes(report)
    process_wizard_archetypes(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
