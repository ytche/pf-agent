#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 月之血脉（Blood of the Moon）BotM 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/月之血脉BotM
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/月之血脉BotM"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "BloodOfTheMoon_reorganization_report.md"

SOURCE_BOOK = "月之血脉（Blood of the Moon）BotM"
SOURCE_BOOK_SHORT = "BotM"


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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 月之血脉BotM{l3_part}"


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


# ========== 1. page_807.md 装备与魔法物品 ==========

def process_equipment_and_magic_items(report: dict) -> None:
    src_path = SRC_DIR / "page_807.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "装备_魔法物品" / "月之血脉BotM_物品.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 月之血脉 BotM 物品\n\n", "\n")

    marker = make_hidden_marker("page_807.md", "__aggregate__")
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("装备与魔法物品聚合已存在: page_807.md")
        return

    # Split at the magic items divider
    divider = "=======================魔法物品"
    if divider in text:
        equip_text, magic_text = text.split(divider, 1)
    else:
        equip_text = text
        magic_text = ""

    equip_text = strip_trailing_artifacts(equip_text)
    magic_text = strip_trailing_artifacts(magic_text)

    parts = []
    parts.append("## 装备与炼金物品")
    parts.append("")
    parts.append(equip_text)
    parts.append("")
    parts.append("## 魔法物品")
    parts.append("")
    parts.append(magic_text)

    block = "\n".join(parts)
    l3 = "装备与魔法物品"
    safe_append_to_file(
        target_path,
        marker,
        "## 月之血脉 BotM 装备与魔法物品",
        make_source_annotation("page_807.md", l3),
        block,
    )
    report["merged"].append({"type": "装备与魔法物品", "name": "月之血脉 BotM 装备与魔法物品", "target": str(target_path.relative_to(ORG_DIR))})


# ========== 2. page_808.md 背景特性 ==========

def process_background_traits(report: dict) -> None:
    src_path = SRC_DIR / "page_808.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "背景特性" / "月之血脉BotM_背景特性.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 月之血脉 BotM 背景特性\n\n", "\n")

    marker = make_hidden_marker("page_808.md", "__aggregate__")
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("背景特性聚合已存在: page_808.md")
        return

    block = strip_trailing_artifacts(text)
    l3 = "背景特性"
    safe_append_to_file(
        target_path,
        marker,
        "## 背景特性",
        make_source_annotation("page_808.md", l3),
        block,
    )
    report["merged"].append({"type": "背景特性", "name": "月之血脉 BotM 背景特性", "target": str(target_path.relative_to(ORG_DIR))})


# ========== 3. page_809.md 专长 ==========

FEATS = [
    {"cn": "额外特征", "en": "Extra Feature"},
    {"cn": "快速变身", "en": "Fast Change"},
    {"cn": "蝙蝠化形", "en": "Bat Shape"},
    {"cn": "凶暴蝙蝠化形", "en": "Dire Bat Shape"},
    {"cn": "血印滑翔", "en": "Bloodmarked Flight"},
    {"cn": "陷阱熊咬", "en": "Beartrap Bite"},
    {"cn": "熊抱", "en": "Bear Hug"},
    {"cn": "凶猛忠诚", "en": "Ferocious Loyalty"},
    {"cn": "集群散布", "en": "Swarm Scatter"},
    {"cn": "集群攻击", "en": "Swarm Strike"},
    {"cn": "激励技巧", "en": "Motivating Display"},
    {"cn": "暴力技巧", "en": "Violent Display"},
    {"cn": "意外战斗者", "en": "Surprising Combatant"},
    {"cn": "狼拳", "en": "Wolf Style"},
    {"cn": "狼摔", "en": "Wolf Trip"},
    {"cn": "狼抓", "en": "Wolf Savage"},
]


def find_feat_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for feat in FEATS:
        cn = re.escape(feat["cn"])
        en = re.escape(feat["en"])
        patterns = [
            re.compile(r"(?:^|(?<=[\n\r\s]))\s*\*?\*?" + cn + r"\s*\(" + en),
            re.compile(r"(?:^|(?<=[\n\r\s]))\s*\*?\*?" + cn + r"\s*" + en),
            re.compile(r"(?:^|(?<=[\n\r\s]))\s*\*?\*?" + cn + r"\s*"),
            re.compile(r"(?:^|(?<=[\n\r\s]))\s*" + cn + r"\s*"),
        ]
        m = None
        for pat in patterns:
            m = pat.search(text)
            if m:
                break
        if not m:
            # Fallback: search cn anywhere in text
            m = re.search(re.escape(feat["cn"]), text)
            if not m:
                raise ValueError(f"无法在 page_809.md 中定位专长：{feat['cn']}（{feat['en']}）")
        starts.append((m.start(), feat))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_feat_title(block: str, feat: dict) -> str:
    cn = re.escape(feat["cn"])
    en = re.escape(feat["en"])
    patterns = [
        re.compile(r"^\s*\*?\*?" + cn + r"\s*\(" + en + r"(?:\s*[^）]*)?\)\s*\*?\*?\s*", re.DOTALL),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*" + en + r"(?:\s*\([^)]*\))?\s*\*?\*?\s*", re.DOTALL),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*\*?\*?\s*"),
        re.compile(r"^\s*" + cn + r"\s*"),
    ]
    for pat in patterns:
        m = pat.search(block)
        if m:
            block = block[m.end():].strip()
            break
    # 剥除可能残留的跨行英文标题
    lines = block.splitlines()
    cleaned: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if re.match(r"^" + re.escape(feat["en"]) + r"(?:\s*\([^)]*\))?\s*$", line, re.IGNORECASE):
            i += 1
            continue
        if i + 1 < len(lines):
            combined = line + " " + lines[i + 1].strip()
            if re.match(r"^" + re.escape(feat["en"]) + r"(?:\s*\([^)]*\))?\s*", combined, re.IGNORECASE):
                rest = re.sub(r"^" + re.escape(feat["en"]) + r"(?:\s*\([^)]*\))?\s*", "", combined, flags=re.IGNORECASE).strip()
                if rest:
                    cleaned.append(rest)
                i += 2
                continue
        cleaned.append(lines[i])
        i += 1
    return "\n".join(cleaned).strip()


def process_feats(report: dict) -> None:
    src_path = SRC_DIR / "page_809.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "专长" / "月之血脉BotM_专长.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 月之血脉 BotM 专长\n\n", "\n")

    try:
        starts = find_feat_starts(text)
    except ValueError as e:
        report["warnings"].append(str(e))
        # Fallback: append whole text as aggregate
        marker = make_hidden_marker("page_809.md", "__aggregate__")
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append("专长聚合已存在: page_809.md")
            return
        block = strip_trailing_artifacts(text)
        safe_append_to_file(
            target_path,
            marker,
            "## 月之血脉 BotM 专长",
            make_source_annotation("page_809.md", "专长"),
            block,
        )
        report["merged"].append({"type": "专长", "name": "月之血脉 BotM 专长（聚合）", "target": str(target_path.relative_to(ORG_DIR))})
        return

    l3 = "专长"
    for idx, (start_pos, feat) in enumerate(starts):
        marker = make_hidden_marker("page_809.md", feat["cn"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"专长已存在: {feat['cn']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        block = strip_feat_title(block, feat)
        heading = f"## {feat['cn']}（{feat['en']}）"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("page_809.md", l3), block)
        report["merged"].append({"type": "专长", "name": feat["cn"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 4. page_810.md 混合内容 ==========

PAGE810_SECTIONS = [
    {
        "keyword": "狂暴之力",
        "marker_name": "狂暴之力",
        "target": ORG_DIR / "规则" / "月之血脉BotM_狂暴之力.md",
        "heading": "## 狂暴之力",
        "l3": "狂暴之力",
        "aggregate": True,
    },
    {
        "keyword": "新游荡者天赋",
        "marker_name": "新游荡者天赋",
        "target": ORG_DIR / "职业" / "核心职业" / "盗贼" / "月之血脉BotM_盗贼天赋.md",
        "heading": "## 新游荡者天赋",
        "l3": "变体/职业选项 → 盗贼",
        "aggregate": True,
    },
    {
        "keyword": "秘示域",
        "marker_name": "月亮秘示域",
        "target": ORG_DIR / "职业" / "基础职业" / "先知" / "page_88.md",
        "heading": "## 月亮秘示域（Lunar Mystery）",
        "l3": "变体/职业选项 → 先知",
        "aggregate": False,
    },
    {
        "keyword": "巫术",
        "marker_name": "巫术",
        "target": ORG_DIR / "职业" / "基础职业" / "女巫" / "月之血脉BotM_女巫巫术.md",
        "heading": "## 巫术",
        "l3": "变体/职业选项 → 女巫",
        "aggregate": True,
    },
    {
        "keyword": "新奥术发现",
        "marker_name": "新奥术发现",
        "target": ORG_DIR / "职业" / "核心职业" / "法师" / "月之血脉BotM_奥术发现.md",
        "heading": "## 新奥术发现",
        "l3": "变体/职业选项 → 法师",
        "aggregate": True,
    },
    {
        "keyword": "新科研发现",
        "marker_name": "新科研发现",
        "target": ORG_DIR / "职业" / "基础职业" / "炼金术师" / "月之血脉BotM_科研发现.md",
        "heading": "## 新科研发现",
        "l3": "变体/职业选项 → 炼金术师",
        "aggregate": True,
    },
    {
        "keyword": "魔战士奥能",
        "marker_name": "魔战士奥能",
        "target": ORG_DIR / "职业" / "基础职业" / "魔战士" / "月之血脉BotM_魔战士奥能.md",
        "heading": "## 魔战士奥能",
        "l3": "变体/职业选项 → 魔战士",
        "aggregate": True,
    },
]


def split_page810_by_sections(text: str) -> dict[str, str]:
    """Split page_810.md text into sections by Chinese keywords."""
    sections: dict[str, str] = {}

    # Define section boundaries with keywords in order of appearance
    section_keywords = [
        ("法术", "狂暴之力"),
        ("狂暴之力", "新游荡者天赋"),
        ("新游荡者天赋", "秘示域"),
        ("秘示域", "巫术"),
        ("巫术", "新奥术发现"),
        ("新奥术发现", "新科研发现"),
        ("新科研发现", "魔战士奥能"),
        ("魔战士奥能", None),
    ]

    for start_kw, end_kw in section_keywords:
        start_idx = text.find(start_kw)
        if start_idx == -1:
            continue
        if end_kw:
            end_idx = text.find(end_kw, start_idx + len(start_kw))
            if end_idx == -1:
                end_idx = len(text)
        else:
            end_idx = len(text)
        section_text = text[start_idx:end_idx]
        sections[start_kw] = strip_trailing_artifacts(section_text)

    return sections


def process_page810(report: dict) -> None:
    src_path = SRC_DIR / "page_810.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    sections = split_page810_by_sections(text)

    for sec in PAGE810_SECTIONS:
        keyword = sec["keyword"]
        if keyword not in sections:
            report["warnings"].append(f"page_810.md 中未找到段落：{keyword}")
            continue

        target_path = sec["target"]
        marker = make_hidden_marker("page_810.md", sec["marker_name"])

        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if sec["aggregate"]:
                # For aggregate files, create with a generic title
                title = sec["heading"].lstrip("# ").split("（")[0]
                write_text_preserve(target_path, f"# {title}\n\n", "\n")
            else:
                # For appending to existing class page
                title = sec["heading"].lstrip("# ").split("（")[0]
                write_text_preserve(target_path, f"# {title}\n\n", "\n")

        existing = target_path.read_text(encoding="utf-8")
        if marker in existing:
            report["skipped"].append(f"page_810 段落已存在: {sec['marker_name']}")
            continue

        block = sections[keyword]

        # Strip the section title from the block
        # Try to strip the keyword heading
        stripped_block = re.sub(r"^\s*" + re.escape(keyword) + r"\s*[\-–—]?\s*", "", block).strip()

        safe_append_to_file(
            target_path,
            marker,
            sec["heading"],
            make_source_annotation("page_810.md", sec["l3"]),
            stripped_block,
        )
        report["merged"].append({
            "type": sec["l3"].split(" → ")[-1] if " → " in sec["l3"] else sec["l3"],
            "name": sec["marker_name"],
            "target": str(target_path.relative_to(ORG_DIR)),
        })

    # Handle spells separately (they are in the "法术" section)
    if "法术" in sections:
        process_spells_from_page810(sections["法术"], report)


def process_spells_from_page810(spell_section_text: str, report: dict) -> None:
    """Extract spells from the 法术 section and write to spell aggregate."""
    spells = [
        {"cn": "诅咒瞪视", "en": "Accused Glare"},
        {"cn": "分享皮肤", "en": "Share Skin"},
        {"cn": "高等分享皮肤", "en": "Share Skin, Greater"},
    ]

    target_path = ORG_DIR / "法术" / "月之血脉BotM_法术.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 月之血脉 BotM 法术\n\n", "\n")

    # Try to locate each spell individually
    text = spell_section_text
    starts = []
    for spell in spells:
        cn = re.escape(spell["cn"])
        en = re.escape(spell["en"])
        patterns = [
            # Match Chinese name immediately followed by English (no space, no parens)
            re.compile(re.escape(cn) + r"\s*" + en),
            # Match with parentheses
            re.compile(re.escape(cn) + r"\s*\(" + en + r"\)"),
            # Match Chinese name only
            re.compile(re.escape(cn) + r"\s*"),
        ]
        m = None
        for pat in patterns:
            m = pat.search(text)
            if m:
                break
        if not m:
            report["warnings"].append(f"无法在 page_810.md 法术段落中定位法术：{spell['cn']}（{spell['en']}）")
            continue
        starts.append((m.start(), spell))

    starts.sort(key=lambda x: x[0])

    l3 = "法术"
    for idx, (start_pos, spell) in enumerate(starts):
        marker = make_hidden_marker("page_810.md", spell["cn"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"法术已存在: {spell['cn']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)

        # Strip title - handle both "诅咒瞪视Accused Glare" and "诅咒瞪视（Accused Glare）" formats
        cn = re.escape(spell["cn"])
        en = re.escape(spell["en"])
        patterns = [
            re.compile(r"^\s*" + cn + r"\s*\(" + en + r"\)\s*"),
            re.compile(r"^\s*" + cn + r"\s*" + en + r"\s*"),
            re.compile(r"^\s*" + cn + r"\s*"),
        ]
        for pat in patterns:
            m = pat.search(block)
            if m:
                block = block[m.end():].strip()
                break

        heading = f"## {spell['cn']}（{spell['en']}）"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("page_810.md", l3), block)
        report["merged"].append({"type": "法术", "name": spell["cn"], "target": str(target_path.relative_to(ORG_DIR))})


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
    process_equipment_and_magic_items(report)
    process_background_traits(report)
    process_feats(report)
    process_page810(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
