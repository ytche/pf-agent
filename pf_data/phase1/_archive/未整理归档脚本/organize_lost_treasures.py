#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 失落秘宝（Lost Treasures）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/失落秘宝Lost Treasures
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/失落秘宝Lost Treasures"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "LostTreasures_reorganization_report.md"

SOURCE_BOOK = "失落秘宝（Lost Treasures）"
SOURCE_BOOK_SHORT = "失落秘宝LostTreasures"


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


ITEM_FIELD_LABELS = {
    "出处", "类型", "类别", "价格", "重量", "灵光", "ＣＬ", "CL", "施法者等级",
    "栏位", "位置", "效果", "描述", "制作", "制造", "制造DC", "制作条件",
    "制作成本", "制造成本", "制造要求", "灵氲",
}

_FIELD_KEYWORDS = [
    "出自", "价格", "重量", "类型", "类别", "描述", "效果", "制造", "制作",
    "出处", "灵光", "栏位", "位置", "CL", "ＣＬ", "施法者等级", "制造DC", "制造要求",
    "制作条件", "制作成本", "制造成本",
]

_SPLIT_KEYWORDS = sorted(
    [k for k in _FIELD_KEYWORDS if k not in {"效果"}],
    key=len,
    reverse=True,
)

_SOURCE_ONLY_RE = re.compile(
    r"^\s*(?:\*+)?\s*(?:"
    r"出自[：:]?|"
    r"《[^》]+》[，,]?|"
    r".*?Lost\s+Treasures.*?"
    r"|.*?pg\.\s*\d+.*?"
    r"|.*?p\.\s*\d+.*?"
    r")\s*(?:\*+)?\s*$",
    re.IGNORECASE,
)


def is_item_field_line(line: str) -> bool:
    stripped = line.strip()
    m = re.match(r"^\*\*(.+?)(?:[：:])?\*\*", stripped)
    if not m:
        return False
    return m.group(1) in ITEM_FIELD_LABELS


def is_source_only_line(line: str) -> bool:
    if is_item_field_line(line):
        return False
    return bool(_SOURCE_ONLY_RE.match(line.strip()))


def _attr_start_re() -> re.Pattern:
    return re.compile(
        r"^(?:\*\*)?(" + "|".join(re.escape(k) for k in _SPLIT_KEYWORDS) + r")(?:[：:])?(?:\*\*)?\s*(.*)$"
    )


_UNIT_FIELDS = {"价格", "重量", "栏位", "位置", "类型", "类别", "CL", "施法者等级"}


def normalize_fields(block: str) -> str:
    """将块中的无标签属性行统一转换成 **关键字**：值 格式。"""
    lines = block.splitlines()
    result: list[str] = []
    attr_re = _attr_start_re()
    i = 0
    while i < len(lines):
        ln = lines[i]
        stripped = ln.strip()
        if stripped == "" or is_source_only_line(ln):
            i += 1
            continue
        m = attr_re.match(stripped)
        if m:
            kw, val = m.group(1), m.group(2)
            # 对价格/重量等单位字段，如果值过长并混入了描述，按第一个句号/分号截断
            if kw in _UNIT_FIELDS and len(val) > 30:
                sm = re.search(r"[。；]", val)
                if sm and sm.start() > 0:
                    result.append(f"**{kw}**：{val[:sm.end()]}")
                    remainder = val[sm.end():].strip()
                    if remainder:
                        result.append(remainder)
                    i += 1
                    continue
            result.append(f"**{kw}**：{val}")
            i += 1
            continue
        # 丢弃残留的非属性文本碎片（如标题片段）
        if len(stripped) <= 5 and not any(kw in stripped for kw in _FIELD_KEYWORDS):
            i += 1
            continue
        result.append(ln)
        i += 1
    return "\n".join(result)


def strip_item_title(block: str) -> str:
    lines = block.splitlines()

    if lines and lines[0].strip().startswith("|"):
        row_parts: list[str] = []
        while lines and not re.match(r"^\|?\s*---", lines[0].strip()) and lines[0].strip() != "":
            row_parts.append(lines[0].strip().lstrip("|"))
            lines.pop(0)
        while lines and (lines[0].strip() == "" or re.match(r"^\|?\s*---", lines[0].strip())):
            lines.pop(0)
        joined = " ".join(row_parts)
        cell = joined.split("|")[0].strip()
        lines = [cell] + lines

    while lines and lines[0].strip() == "":
        lines = lines[1:]

    if lines and re.match(r"^\[(\*\*.*?\*\*)\]\(.*?\)\s*$", lines[0].strip()):
        lines = lines[1:]
        while lines and lines[0].strip() == "":
            lines = lines[1:]

    if lines:
        first = lines[0].strip()
        if first.startswith("**"):
            lines[0] = re.sub(r"\]\(.*?\)\s*$", "", lines[0])
            first = lines[0].strip()
            if not is_item_field_line(first):
                m = re.match(r"^\*\*[^*]+?\*\*", first)
                if m:
                    rest = first[m.end():].strip()
                    lines[0] = rest
                else:
                    lines = lines[1:]
                    while (
                        lines
                        and lines[0].strip() != ""
                        and not is_item_field_line(lines[0])
                        and not any(kw in lines[0] for kw in _FIELD_KEYWORDS)
                    ):
                        lines = lines[1:]
        elif not first.startswith("|"):
            if len(lines) > 1 and (is_source_only_line(lines[1]) or is_item_field_line(lines[1])):
                lines = lines[1:]

    # 去掉跨行的出处说明（如 **出自《Lost Treasures pg. /n 13》**）
    while lines and (lines[0].strip().startswith("**出自") or lines[0].strip().startswith("出自")):
        while lines and not (lines[0].strip().endswith("**") or lines[0].strip().endswith("》")):
            lines = lines[1:]
        if lines:
            lines = lines[1:]
        while lines and lines[0].strip() == "":
            lines = lines[1:]

    while lines and (lines[0].strip() == "" or is_source_only_line(lines[0])):
        lines = lines[1:]

    block = "\n".join(lines)
    block = normalize_fields(block)
    lines = block.splitlines()

    lines = [ln for ln in lines if not re.match(r"^\s*\|\s*$", ln.strip()) and not re.match(r"^\|?\s*---", ln.strip())]
    while lines and lines[0].strip() == "":
        lines = lines[1:]

    lines = [re.sub(r"(\s*\|)+\s*$", "", ln) for ln in lines]

    return "\n".join(lines).strip()
def split_items(text: str) -> list[tuple[str, str]]:
    item_names = ["飞天宝箱", "女巫市集硬币"]
    positions: list[tuple[int, str]] = []
    for name in item_names:
        idx = text.find(f"**{name}")
        if idx == -1:
            idx = text.find(name)
        if idx != -1:
            positions.append((idx, name))
    positions.sort()

    items: list[tuple[str, str]] = []
    for i, (start, name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        block = text[start:end].strip()
        lines = block.splitlines()
        cleaned_lines = [ln for ln in lines if not re.match(r"^\|?\s*---", ln.strip())]
        block = "\n".join(cleaned_lines).strip()
        block = strip_item_title(block)
        if block:
            block = f"## {name}\n\n{block}"
            items.append((name, block))
    return items


def classify_item(block: str) -> str:
    if re.search(r"(?:栏位|位置)[：:\*]*\s*[一-龥a-zA-Z]+", block):
        if not re.search(r"(?:栏位|位置)[：:\*]*\s*.*?无", block):
            return "slotted"
    return "slotless"


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


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    text = clean_aggregate((SRC_DIR / "魔法物品6.md").read_text(encoding="utf-8"))
    items = split_items(text)

    slotted = [block for _, block in items if classify_item(block) == "slotted"]
    slotless = [block for _, block in items if classify_item(block) == "slotless"]

    if slotted:
        process_aggregate(
            report,
            "魔法物品6.md",
            "装备",
            "slotted_wondrous",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "失落秘宝LostTreasures_奇物.md",
            "失落秘宝 奇物",
            "## 失落秘宝 有位置奇物",
            block="\n\n".join(slotted),
        )
    if slotless:
        process_aggregate(
            report,
            "魔法物品6.md",
            "装备",
            "slotless_wondrous",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "无位置" / "失落秘宝LostTreasures_奇物.md",
            "失落秘宝 无位置奇物",
            "## 失落秘宝 无位置奇物",
            block="\n\n".join(slotless),
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()