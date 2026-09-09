#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 对立协调（Concordance of Rivals）内容到已有分类目录。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/对立协调Concordance of Rivals"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "ConcordanceOfRivals_reorganization_report.md"

SOURCE_BOOK = "对立协调（Concordance of Rivals）"
SOURCE_BOOK_SHORT = "对立协调CoR"


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


def normalize_block(block: str) -> str:
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


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 督察.md：切分为进阶职业 / 专长 / 监察者半神表
    proctor_text = clean_aggregate((SRC_DIR / "督察.md").read_text(encoding="utf-8"))

    split1 = split_at_heading(proctor_text, r"\n\s*\*\*监察训诫\s*[（(]Monitor Obedience")
    if split1 is None:
        report["warnings"].append("督察.md 未找到监察训诫分隔点，整段写入进阶职业")
        prestige_block = proctor_text
        feat_block = ""
        demigod_block = ""
    else:
        prestige_block, rest = split1
        split2 = split_at_heading(rest, r"\n\s*\*\*监察者半神\s*[（(]Monitor demigod")
        if split2 is None:
            report["warnings"].append("督察.md 未找到监察者半神分隔点，后半段写入专长")
            prestige_block = proctor_text
            feat_block = rest
            demigod_block = ""
        else:
            feat_block, demigod_block = split2

    prestige_block = normalize_block(prestige_block)
    if prestige_block:
        process_aggregate(
            report,
            "督察.md",
            "职业选项 → 进阶职业",
            "proctor",
            ORG_DIR / "职业" / "进阶职业" / f"{SOURCE_BOOK_SHORT}_进阶职业.md",
            f"{SOURCE_BOOK_SHORT} 进阶职业",
            f"## {SOURCE_BOOK_SHORT} 督察",
            block=prestige_block,
        )

    feat_block = normalize_block(feat_block)
    if feat_block:
        process_aggregate(
            report,
            "督察.md",
            "角色选项 → 专长",
            "monitor_obedience",
            ORG_DIR / "角色" / "专长" / f"{SOURCE_BOOK_SHORT}_专长.md",
            f"{SOURCE_BOOK_SHORT} 专长",
            f"## {SOURCE_BOOK_SHORT} 监察训诫",
            block=feat_block,
        )

    demigod_block = normalize_block(demigod_block)
    if demigod_block:
        process_aggregate(
            report,
            "督察.md",
            "信仰",
            "monitor_demigods_table",
            ORG_DIR / "信仰" / f"{SOURCE_BOOK_SHORT}_监察者半神.md",
            f"{SOURCE_BOOK_SHORT} 监察者半神",
            f"## {SOURCE_BOOK_SHORT} 监察者半神",
            block=demigod_block,
        )

    # 2. 监察训诫.md：保留阅读说明与半神详细条目，跳过重复的专长段落
    obedience_text = clean_aggregate((SRC_DIR / "监察训诫.md").read_text(encoding="utf-8"))

    # 先切分出阅读说明与后续内容（后续含重复专长及半神条目）
    split = split_at_heading(obedience_text, r"\n\s*\*\*监察训诫(?:\s*[（(]Monitor Obedience)?")
    if split is None:
        report["warnings"].append("监察训诫.md 未找到监察训诫分隔点，整段写入信仰")
        faith_block = obedience_text
    else:
        reading_guide, rest_after_feat_heading = split
        # 后续内容中，重复专长段落之后以首个半神条目“阿特洛波斯”开始
        deity_split = split_at_heading(rest_after_feat_heading, r"\n\s*\*\*阿特洛波斯")
        if deity_split is None:
            report["warnings"].append("监察训诫.md 未找到阿特洛波斯分隔点，整段写入信仰")
            faith_block = obedience_text
        else:
            demigod_entries = deity_split[1]
            faith_block = f"{reading_guide}\n\n{demigod_entries}".strip()

    faith_block = normalize_block(faith_block)
    if faith_block:
        process_aggregate(
            report,
            "监察训诫.md",
            "信仰",
            "monitor_demigod_entries",
            ORG_DIR / "信仰" / f"{SOURCE_BOOK_SHORT}_监察者半神.md",
            f"{SOURCE_BOOK_SHORT} 监察者半神",
            f"## {SOURCE_BOOK_SHORT} 监察者半神条目",
            block=faith_block,
        )

    # 3. 仪式7.md → 神秘仪式
    ritual_block = clean_aggregate((SRC_DIR / "仪式7.md").read_text(encoding="utf-8"))
    ritual_block = normalize_block(ritual_block)
    if ritual_block:
        process_aggregate(
            report,
            "仪式7.md",
            "规则",
            "monitor_rituals",
            ORG_DIR / "规则" / f"{SOURCE_BOOK_SHORT}_神秘仪式.md",
            f"{SOURCE_BOOK_SHORT} 监察者仪式",
            f"## {SOURCE_BOOK_SHORT} 监察者仪式",
            block=ritual_block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
