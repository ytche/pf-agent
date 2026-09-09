#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 元素血脉（Blood of the Elements）BotE 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/元素血脉BotE
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/元素血脉BotE"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "BloodOfTheElements_reorganization_report.md"

SOURCE_BOOK = "元素血脉（Blood of the Elements）BotE"
SOURCE_BOOK_SHORT = "BotE"


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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 元素血脉BotE{l3_part}"


def make_hidden_marker(source_file: str, entry_name: str) -> str:
    return f"<!-- {SOURCE_BOOK_SHORT}-source:{source_file}:{entry_name} -->"


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


def strip_trailing_artifacts(block: str) -> str:
    lines = block.splitlines()
    while lines and (lines[-1].strip() == "" or re.match(r"^\*+$", lines[-1].strip())):
        lines.pop()
    return "\n".join(lines)


# ========== 1. 元素血脉专长 ==========

FEATS = [
    {"cn": "元素融合", "en": "Elemental Commixture", "type": "（团队专长）"},
]


def find_feat_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for feat in FEATS:
        pattern = re.compile(r"(?:^|(?<=[。\n\r\s]))\s*\*?\*?" + re.escape(feat["cn"]) + r"(?:[^\n]*?)")
        m = pattern.search(text)
        if not m:
            raise ValueError(f"无法在 专长23.md 中定位专长：{feat['cn']}")
        starts.append((m.start(), feat))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_feat_title(block: str, feat: dict) -> str:
    cn = re.escape(feat["cn"])
    type_zh = re.escape(feat.get("type", "")) if feat.get("type") else ""
    en = r"\s*".join(re.escape(word) for word in feat["en"].split())
    # 主标题：加粗可选、中文名、可选中文类型、可选英文名（括号或空格）
    pattern = re.compile(
        r"^\s*\*?\*?" + cn + r"(?:" + type_zh + r")?\s*(?:（" + en + r"(?:\([^)]+\))?）|" + en + r"(?:\([^)]+\))?)?\s*",
        re.DOTALL,
    )
    m = pattern.search(block)
    if m:
        block = block[m.end():].strip()
    # 剥除可能残留的孤星号线、英文标题行、类型括号行
    lines = block.splitlines()
    cleaned: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        # 孤星号分隔线
        if re.match(r"^\*+$", stripped):
            i += 1
            continue
        # 英文标题（可能带 teamwork 等括号类型）
        if re.match(r"^" + en + r"(?:\s*\([^)]+\))?\s*$", stripped, re.IGNORECASE):
            i += 1
            continue
        # 英文标题被换行拆分：当前行首单词 + 下一行剩余
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            combined = stripped + " " + next_line
            if re.match(r"^" + en + r"(?:\s*\([^)]+\))?\s*$", combined, re.IGNORECASE):
                i += 2
                continue
        # 独立的类型括号行（如 (teamwork)）出现在最开头
        if not cleaned and re.match(r"^\([^)]+\)\s*$", stripped):
            i += 1
            continue
        cleaned.append(line)
        i += 1
    return "\n".join(cleaned).strip()


def process_feats(report: dict) -> None:
    src_path = SRC_DIR / "专长23.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "专长" / "元素血脉BotE_专长.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 元素血脉 BotE 专长\n\n", "\n")

    starts = find_feat_starts(text)
    l3 = "专长"
    for idx, (start_pos, feat) in enumerate(starts):
        marker = make_hidden_marker("专长23.md", feat["cn"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"专长已存在: {feat['cn']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        block = strip_feat_title(block, feat)
        title_full = f"{feat['cn']}{feat.get('type', '')} {feat['en']}".strip()
        heading = f"## {title_full}"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("专长23.md", l3), block)
        report["merged"].append({"type": "专长", "name": feat["cn"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 2. 元素血脉物品 ==========

ITEMS = [
    {"cn": "元素海盐水", "en": "Elemental Brine"},
]


def find_item_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for item in ITEMS:
        pattern = re.compile(
            r"(?:^|(?<=[\s\n\r]))\s*" + re.escape(item["cn"]) + r"(?:\s*[（(]" + re.escape(item["en"]) + r"[）)])?",
            re.IGNORECASE,
        )
        m = pattern.search(text)
        if not m:
            raise ValueError(f"无法在 物品24.md 中定位物品：{item['cn']}")
        starts.append((m.start(), item))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_item_title(block: str, item: dict) -> str:
    cn = re.escape(item["cn"])
    en = r"\s*".join(re.escape(word) for word in item["en"].split())
    pattern = re.compile(
        r"^\s*" + cn + r"(?:\s*[（(]" + en + r"[）)])?\s*",
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(block)
    if m:
        return block[m.end():].strip()
    return block


def process_items(report: dict) -> None:
    src_path = SRC_DIR / "物品24.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "装备_魔法物品" / "元素血脉BotE_物品.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 元素血脉 BotE 物品\n\n", "\n")

    starts = find_item_starts(text)
    l3 = "魔法物品"
    for idx, (start_pos, item) in enumerate(starts):
        marker = make_hidden_marker("物品24.md", item["cn"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"物品已存在: {item['cn']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        block = strip_item_title(block, item)
        heading = f"## {item['cn']}（{item['en']}）"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("物品24.md", l3), block)
        report["merged"].append({"type": "物品", "name": item["cn"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 3. 元素血脉背景特性 ==========

TRAITS = [
    {"cn": "阿尔曼凯利斯克学者", "en": "Armun Kelisk Scholar"},
    {"cn": "大地感应", "en": "Earthsense"},
    {"cn": "缜密许愿者", "en": "Thoughtful Wish-Maker"},
    {"cn": "绝地引导", "en": "Channel the Earth"},
]


def find_trait_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for trait in TRAITS:
        pattern = re.compile(r"(?:^|(?<=[。\n\r\s]))\s*\*?\*?" + re.escape(trait["cn"]))
        m = pattern.search(text)
        if not m:
            raise ValueError(f"无法在 背景特性39.md 中定位背景特性：{trait['cn']}（{trait['en']}）")
        starts.append((m.start(), trait))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_trait_title(block: str, trait: dict) -> str:
    en = r"\s*".join(re.escape(word) for word in trait["en"].split())
    pattern = re.compile(
        r"^\s*\*?\*?" + re.escape(trait["cn"]) + r"(?:\s*[（(]" + en + r"[）)])?\s*：?\s*",
        re.DOTALL,
    )
    m = pattern.search(block)
    if m:
        block = block[m.end():].strip()
    # 剥除可能残留的孤星号线
    lines = block.splitlines()
    if lines and re.match(r"^\*+$", lines[0].strip()):
        lines = lines[1:]
    return "\n".join(lines).strip()


def process_traits(report: dict) -> None:
    src_path = SRC_DIR / "背景特性39.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "背景特性" / "元素血脉BotE_背景特性.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 元素血脉 BotE 背景特性\n\n", "\n")

    starts = find_trait_starts(text)
    l3 = "背景特性"
    for idx, (start_pos, trait) in enumerate(starts):
        marker = make_hidden_marker("背景特性39.md", trait["cn"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"背景特性已存在: {trait['cn']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        block = strip_trait_title(block, trait)
        heading = f"## {trait['cn']}（{trait['en']}）"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("背景特性39.md", l3), block)
        report["merged"].append({"type": "背景特性", "name": trait["cn"], "target": str(target_path.relative_to(ORG_DIR))})


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
    process_feats(report)
    process_items(report)
    process_traits(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
