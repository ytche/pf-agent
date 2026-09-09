#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 内海神殿（Inner Sea Temples）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/内海神殿
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/内海神殿"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "InnerSeaTemples_reorganization_report.md"

SOURCE_BOOK = "内海神殿（Inner Sea Temples）"
SOURCE_BOOK_SHORT = "内海神殿"


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
    """以二进制追加方式写入，保留原文件行尾不变。"""
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
    """移除 Markdown 图片链接标记（通常来自 AON 图标）。"""
    return re.sub(r"!\[.*?\]\(.*?\)", "", text)


def clean_translator_url(text: str) -> str:
    """移除文件顶部的译者/整理者链接与空行。"""
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
    """移除文件顶部的图片引用。"""
    lines = text.splitlines()
    while lines and re.match(r"^\s*!\[.*\]\(.*\)\s*$", lines[0].strip()):
        lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return "\n".join(lines)


def strip_trailing_artifacts(block: str) -> str:
    lines = block.splitlines()
    while lines and (lines[-1].strip() == "" or re.match(r"^\*+$", lines[-1].strip())):
        lines.pop()
    return "\n".join(lines)


def clean_aggregate(text: str) -> str:
    """对聚合文件进行最小清理。"""
    text = text.replace("\r\n", "\n")
    text = remove_image_links(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)
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


# 各文件拆分配置：按章节标题识别物品、法术、仪式三类
SPLIT_CONFIG = {
    "page_1601.md": [
        ("items", re.compile(r"^\*\*赛伦尼特魔法物品")),
        ("rituals", re.compile(r"^\*\*赛伦尼特神秘仪式")),
    ],
    "page_1606.md": [
        ("items", re.compile(r"^\*\*卡莉斯翠安魔法物品")),
        ("spells", re.compile(r"^\*\*卡莉斯翠安法术")),
    ],
    "page_1607.md": [
        ("items", re.compile(r"^\*\*法莱斯门装备")),
        ("items", re.compile(r"^\*\*法莱斯门魔法物品")),
        ("spells", re.compile(r"^\*\*法莱斯门法术")),
    ],
    "page_1608.md": [
        ("items", re.compile(r"^\*\*库松特魔法物品")),
        ("rituals", re.compile(r"^\*\*库松特神秘仪式")),
        ("spells", re.compile(r"^\*\*库松特法术")),
    ],
    "page_1609.md": [
        ("items", re.compile(r"^\*\*阿巴达兰魔法物品")),
        ("items", re.compile(r"^\*\*阿巴达兰魔法武器")),
        ("spells", re.compile(r"^\*\*阿巴达兰法术")),
    ],
    "page_1610.md": [
        ("items", re.compile(r"^\*\*凯登．凯连魔法物品")),
        ("spells", re.compile(r"^\*\*凯登．凯连法术")),
    ],
}


def split_file(text: str, config: list[tuple[str, re.Pattern]]) -> dict[str, list[str]]:
    """按配置切分文件，返回 {kind: [block, ...]}。"""
    lines = text.splitlines()
    sections = []
    for kind, pattern in config:
        for i, line in enumerate(lines):
            if pattern.match(line):
                sections.append((i, kind))
                break
    sections.sort(key=lambda x: x[0])

    result: dict[str, list[str]] = {"items": [], "spells": [], "rituals": []}
    for idx, (start_line, kind) in enumerate(sections):
        end_line = sections[idx + 1][0] if idx + 1 < len(sections) else len(lines)
        block = "\n".join(lines[start_line:end_line])
        result.setdefault(kind, []).append(block)
    return result


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

    items_target = ORG_DIR / "装备_魔法物品" / "内海神殿_魔法物品.md"
    spells_target = ORG_DIR / "法术" / "内海神殿_法术.md"
    rituals_target = ORG_DIR / "规则" / "内海神殿_神秘仪式.md"

    for src_name in sorted(SPLIT_CONFIG.keys()):
        text = clean_aggregate((SRC_DIR / src_name).read_text(encoding="utf-8"))
        parts = split_file(text, SPLIT_CONFIG[src_name])

        if parts.get("items"):
            process_aggregate(
                report,
                src_name,
                "装备",
                "items",
                items_target,
                "内海神殿 魔法物品",
                "## 内海神殿 魔法物品",
                block="\n\n".join(parts["items"]),
            )
        if parts.get("spells"):
            process_aggregate(
                report,
                src_name,
                "法术",
                "spells",
                spells_target,
                "内海神殿 法术",
                "## 内海神殿 法术",
                block="\n\n".join(parts["spells"]),
            )
        if parts.get("rituals"):
            process_aggregate(
                report,
                src_name,
                "规则",
                "rituals",
                rituals_target,
                "内海神殿 神秘仪式",
                "## 内海神殿 神秘仪式",
                block="\n\n".join(parts["rituals"]),
            )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
