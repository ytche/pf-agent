#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 PF官方漫画Worldscape 内容到已有分类目录。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "Worldscape_reorganization_report.md"

SOURCE_BOOK = "PF官方漫画Worldscape"
SOURCE_BOOK_SHORT = "Worldscape"


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


def merge_broken_bold(text: str) -> str:
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("**") and not re.search(r"\*\*.*\*\*", line.strip()):
            merged = line
            i += 1
            while i < len(lines) and not re.search(r"\*\*.*\*\*", merged):
                merged = f"{merged} {lines[i]}".rstrip()
                i += 1
            out.append(merged)
        else:
            out.append(line)
            i += 1
    return "\n".join(out)


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


def normalize_block(block: str) -> str:
    block = merge_broken_bold(block)
    block = _normalize_stars(block)
    return _collapse_blank_lines(block.strip())


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


def slice_by_headings(text: str, patterns: list[tuple[str, str | None]]) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    remaining = text
    for i, (name, pattern) in enumerate(patterns):
        if pattern is None:
            blocks.append((name, remaining.strip()))
            remaining = ""
            break
        split = split_at_heading(remaining, pattern)
        if split is None:
            report["warnings"].append(f"未找到 {name} 分隔点，剩余内容归入该块")
            blocks.append((name, remaining.strip()))
            remaining = ""
            break
        current, remaining = split
        blocks.append((name, current))
    if remaining.strip():
        blocks.append(("remainder", remaining.strip()))
    return blocks


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    text = clean_aggregate((SRC_DIR / "PF官方漫画Worldscape.md").read_text(encoding="utf-8"))
    text = normalize_block(text)

    # 按顺序切分文件中的主要条目
    patterns = [
        ("sword_devil", r"\n\s*\*\*新专长："),
        ("extra_vow_feats", r"\n\s*\*\*丛林之王"),
        ("jungle_lord", r"\n\s*\*\*战将"),
        ("warlord", r"\n\s*\*\*镭武器"),
        ("radium_weapons", r"\n\s*\*\*绿色火星人"),
        ("green_martian", r"\n\s*\*\*失落者变体"),
        ("elegist", r"\n\s*\*\*哀刃"),
        ("sorrow_blade", r"\n\s*\*\*受膜生怪"),
        ("psychovore_feats", None),
    ]

    blocks = []
    remaining = text
    for name, pattern in patterns:
        if pattern is None:
            blocks.append((name, remaining.strip()))
            remaining = ""
            break
        split = split_at_heading(remaining, pattern)
        if split is None:
            report["warnings"].append(f"未找到 {name} 分隔点，剩余内容归入该块")
            blocks.append((name, remaining.strip()))
            remaining = ""
            break
        current, remaining = split
        blocks.append((name, current))
    if remaining.strip():
        blocks.append(("remainder", remaining.strip()))

    # 路由到对应目标文件
    for name, block in blocks:
        if not block:
            continue
        if name == "sword_devil":
            process_aggregate(
                report, "PF官方漫画Worldscape.md", "职业选项 → 游侠变体", "sword_devil",
                ORG_DIR / "职业" / "核心职业" / "游侠" / f"{SOURCE_BOOK_SHORT}_游侠变体.md",
                f"{SOURCE_BOOK_SHORT} 游侠变体", f"## {SOURCE_BOOK_SHORT} 剑魔", block=block,
            )
        elif name == "extra_vow_feats":
            process_aggregate(
                report, "PF官方漫画Worldscape.md", "角色选项 → 专长", "extra_vow_feats",
                ORG_DIR / "角色" / "专长" / f"{SOURCE_BOOK_SHORT}_专长.md",
                f"{SOURCE_BOOK_SHORT} 专长", f"## {SOURCE_BOOK_SHORT} 额外誓仇与复仇死誓", block=block,
            )
        elif name == "jungle_lord":
            process_aggregate(
                report, "PF官方漫画Worldscape.md", "职业选项 → 游侠变体", "jungle_lord",
                ORG_DIR / "职业" / "核心职业" / "游侠" / f"{SOURCE_BOOK_SHORT}_游侠变体.md",
                f"{SOURCE_BOOK_SHORT} 游侠变体", f"## {SOURCE_BOOK_SHORT} 丛林之王", block=block,
            )
        elif name == "warlord":
            process_aggregate(
                report, "PF官方漫画Worldscape.md", "职业选项 → 战士变体", "warlord",
                ORG_DIR / "职业" / "核心职业" / "战士" / f"{SOURCE_BOOK_SHORT}_战士变体.md",
                f"{SOURCE_BOOK_SHORT} 战士变体", f"## {SOURCE_BOOK_SHORT} 战将", block=block,
            )
        elif name == "radium_weapons":
            process_aggregate(
                report, "PF官方漫画Worldscape.md", "装备/魔法物品", "radium_weapons",
                ORG_DIR / "装备_魔法物品" / f"{SOURCE_BOOK_SHORT}_新武器.md",
                f"{SOURCE_BOOK_SHORT} 新武器", f"## {SOURCE_BOOK_SHORT} 镭武器", block=block,
            )
        elif name == "green_martian":
            process_aggregate(
                report, "PF官方漫画Worldscape.md", "种族", "green_martian",
                ORG_DIR / "种族" / "其他种族" / f"{SOURCE_BOOK_SHORT}_绿色火星人.md",
                f"{SOURCE_BOOK_SHORT} 绿色火星人", f"## {SOURCE_BOOK_SHORT} 绿色火星人", block=block,
            )
        elif name == "elegist":
            process_aggregate(
                report, "PF官方漫画Worldscape.md", "职业选项 → 吟游诗人变体", "elegist",
                ORG_DIR / "职业" / "核心职业" / "吟游诗人" / f"{SOURCE_BOOK_SHORT}_吟游诗人变体.md",
                f"{SOURCE_BOOK_SHORT} 吟游诗人变体", f"## {SOURCE_BOOK_SHORT} 挽歌奏者", block=block,
            )
        elif name == "sorrow_blade":
            process_aggregate(
                report, "PF官方漫画Worldscape.md", "职业选项 → 魔战士变体", "sorrow_blade",
                ORG_DIR / "职业" / "基础职业" / "魔战士" / f"{SOURCE_BOOK_SHORT}_魔战士变体.md",
                f"{SOURCE_BOOK_SHORT} 魔战士变体", f"## {SOURCE_BOOK_SHORT} 哀刃", block=block,
            )
        elif name == "psychovore_feats":
            process_aggregate(
                report, "PF官方漫画Worldscape.md", "角色选项 → 专长", "psychovore_feats",
                ORG_DIR / "角色" / "专长" / f"{SOURCE_BOOK_SHORT}_专长.md",
                f"{SOURCE_BOOK_SHORT} 专长", f"## {SOURCE_BOOK_SHORT} 噬心流专长", block=block,
            )
        elif name == "remainder":
            report["warnings"].append(f"未路由的剩余内容：{block[:80]}...")

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
