#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 异能源始（Occult Origins）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/异能源始OO
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/异能源始OO"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "OccultOrigins_reorganization_report.md"

SOURCE_BOOK = "异能源始（Occult Origins）"
SOURCE_BOOK_SHORT = "异能源始OO"


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


PAGE_1227_PATTERNS: list[tuple[re.Pattern, dict]] = [
    (
        re.compile(r"^\s*\*\*心能狂怒者"),
        {
            "entry": "id_rager",
            "title": "异能源始OO 心能狂怒者",
            "heading": "## 异能源始OO 心能狂怒者",
            "l3": "职业选项 → 血脉狂怒者",
            "target": ORG_DIR / "职业" / "混合职业" / "血脉狂怒者" / "异能源始OO_血脉狂怒者变体.md",
        },
    ),
    (
        re.compile(r"^\s*\*\*超自然学家"),
        {
            "entry": "supernaturalist",
            "title": "异能源始OO 超自然学家",
            "heading": "## 异能源始OO 超自然学家",
            "l3": "职业选项 → 德鲁伊",
            "target": ORG_DIR / "职业" / "核心职业" / "德鲁伊" / "异能源始OO_德鲁伊变体.md",
        },
    ),
    (
        re.compile(r"^\s*\*\*灵刃骑士"),
        {
            "entry": "mind_sword",
            "title": "异能源始OO 灵刃骑士",
            "heading": "## 异能源始OO 灵刃骑士",
            "l3": "职业选项 → 圣骑士",
            "target": ORG_DIR / "职业" / "核心职业" / "圣骑士" / "异能源始OO_圣骑士变体.md",
        },
    ),
    (
        re.compile(r"^\s*银王座先知"),
        {
            "entry": "true_silvered_throne",
            "title": "异能源始OO 银王座先知",
            "heading": "## 异能源始OO 银王座先知",
            "l3": "职业选项 → 萨满",
            "target": ORG_DIR / "职业" / "基础职业" / "萨满" / "异能源始OO_萨满变体.md",
        },
    ),
]


def split_page_1227(text: str) -> list[dict]:
    lines = text.splitlines()
    blocks: list[dict] = []
    current: dict | None = None
    start = 0
    for i, line in enumerate(lines):
        for pat, info in PAGE_1227_PATTERNS:
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

    # 1. page_1214 秘学士神圣遗物
    block = clean_aggregate((SRC_DIR / "page_1214.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "page_1214.md",
            "职业选项 → 秘学士",
            "sacred_relics",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "秘学士" / "异能源始OO_秘学士变体.md",
            "异能源始OO 神圣遗物",
            "## 异能源始OO 神圣遗物",
            block=block,
        )

    # 2. page_1227 多职业变体拆分
    page_text = clean_aggregate((SRC_DIR / "page_1227.md").read_text(encoding="utf-8"))
    # 修复标题被换行拆断的情况
    page_text = re.sub(
        r"银王座先知\s+True\s+Silvered\s*\n\s*Throne\s*（萨满变体）",
        "银王座先知 True Silvered Throne（萨满变体）",
        page_text,
        flags=re.MULTILINE,
    )
    for info in split_page_1227(page_text):
        block = _normalize_stars(info["block"])
        block = _collapse_blank_lines(block.strip())
        if block:
            process_aggregate(
                report,
                "page_1227.md",
                info["l3"],
                info["entry"],
                info["target"],
                info["title"],
                info["heading"],
                block=block,
            )

    # 3. page_1600 奥能师变体
    block = clean_aggregate((SRC_DIR / "page_1600.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "page_1600.md",
            "职业选项 → 奥能师",
            "harrowed_society_student",
            ORG_DIR / "职业" / "混合职业" / "奥能师" / "异能源始OO_奥能师变体.md",
            "异能源始OO 哈罗牌研究者",
            "## 异能源始OO 哈罗牌研究者",
            block=block,
        )

    # 4. page_1616 通灵者变体
    block = clean_aggregate((SRC_DIR / "page_1616.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "page_1616.md",
            "职业选项 → 通灵者",
            "nexian_channeler",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "通灵者" / "异能源始OO_通灵者变体.md",
            "异能源始OO 奈克斯唤灵师",
            "## 异能源始OO 奈克斯唤灵师",
            block=block,
        )

    # 5. 唤魂师+情感羁绊
    block = clean_aggregate((SRC_DIR / "唤魂师+情感羁绊.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "唤魂师+情感羁绊.md",
            "职业选项 → 唤魂师",
            "fated_guide",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "唤魂师" / "异能源始OO_唤魂师变体.md",
            "异能源始OO 命运向导",
            "## 异能源始OO 命运向导",
            block=block,
        )

    # 6. 武僧变体
    block = clean_aggregate((SRC_DIR / "武僧2.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "武僧2.md",
            "职业选项 → 武僧",
            "serpent_fire_adept",
            ORG_DIR / "职业" / "核心职业" / "武僧" / "异能源始OO_武僧变体.md",
            "异能源始OO 蛇焰宗师",
            "## 异能源始OO 蛇焰宗师",
            block=block,
        )

    # 7. 专长
    block = clean_aggregate((SRC_DIR / "专长28.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "专长28.md",
            "专长",
            "feats",
            ORG_DIR / "专长" / "异能源始OO_专长.md",
            "异能源始OO 专长",
            "## 异能源始OO 专长",
            block=block,
        )

    # 8. 神秘仪式
    block = clean_aggregate((SRC_DIR / "神秘仪式4.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "神秘仪式4.md",
            "规则 → 神秘仪式",
            "occult_rituals",
            ORG_DIR / "规则" / "异能源始OO_神秘仪式.md",
            "异能源始OO 神秘仪式",
            "## 异能源始OO 神秘仪式",
            block=block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
