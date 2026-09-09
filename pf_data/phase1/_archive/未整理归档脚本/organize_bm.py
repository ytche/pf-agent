#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 黑市指南（Black Markets）BM 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/黑市指南BM/
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/黑市指南BM"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "BM_reorganization_report.md"

SOURCE_BOOK = "黑市指南（Black Markets）BM"
SOURCE_BOOK_SHORT = "BM"


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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 黑市指南BM{l3_part}"


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


def extract_block_from_heading(text: str, name: str) -> str:
    """从文本中第一条匹配 name 的标题行开始截取，并清理顶部的译者/URL行。"""
    lines = text.splitlines()
    pat = re.compile(re.escape(name), re.IGNORECASE)
    for i, line in enumerate(lines):
        if pat.search(line):
            return clean_translator_url("\n".join(lines[i:]))
    return clean_translator_url(text)


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
    {"name": "黑市交易高手", "english": "Black Market Dealings", "source_file": "专长4.md"},
    {"name": "黑市侦探", "english": "Black Market Sleuth", "source_file": "专长4.md"},
    {"name": "犯罪同伙", "english": "Connected Criminal", "source_file": "专长4.md"},
    {"name": "谨慎走私者", "english": "Wary Smuggler", "source_file": "专长4.md"},
]

FEAT_ITEM_CREATION = {
    "name": "灌法毒药（物品制造）",
    "english": "Infuse Poison",
    "source_file": "专长4.md",
}


def process_feats(report: dict) -> None:
    target_path = ORG_DIR / "专长" / "黑市指南BM_专长.md"

    text = (SRC_DIR / "专长4.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    # “灌法毒药”一节包含一段通用规则引言，这段引言已在“黑市毒药.md”中聚合，
    # 这里只取最后的“物品制造”专长块，并把引言从切分范围中剔除，
    # 避免它被错误地并入“谨慎走私者”条目。
    item_creation_match = re.search(r"(?:^|\n)\s*\*\*灌法毒药（物品制造）.*", text)
    intro_match = re.search(r"(?:^|\n)\s*灌法毒药[（(]Infused\s+Poisons[）)]", text, re.IGNORECASE)
    if item_creation_match:
        item_creation_block = text[item_creation_match.start():].strip()
        split_end = intro_match.start() if intro_match else item_creation_match.start()
        text_for_split = text[:split_end]
    else:
        item_creation_block = None
        text_for_split = text
        report["warnings"].append("未找到灌法毒药（物品制造）专长块")

    blocks = split_section_by_entries(text_for_split, FEATS)

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

    if item_creation_block:
        marker = make_hidden_marker(FEAT_ITEM_CREATION["source_file"], FEAT_ITEM_CREATION["name"])
        append_entry(
            target_path,
            marker,
            f"## {FEAT_ITEM_CREATION['name']}（{FEAT_ITEM_CREATION['english']}）",
            make_source_annotation(FEAT_ITEM_CREATION["source_file"], "专长"),
            item_creation_block,
            report,
            "专长",
            FEAT_ITEM_CREATION["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 2. 背景特性 ==========

BACKGROUND_TRAITS = [
    {"name": "黄昏市场的艺术", "english": "Dusk Market Bribery", "source_file": "背景特性3.md"},
    {"name": "夜色集市的精明", "english": "Nightstalls Navigator", "source_file": "背景特性3.md"},
    {"name": "红丝路的诚意", "english": "Red Silk Frankness", "source_file": "背景特性3.md"},
    {"name": "玷污大厅的速度", "english": "Tarnished Halls Runner", "source_file": "背景特性3.md"},
    {"name": "隐秘信徒", "english": "Covert Channeler", "source_file": "背景特性3.md"},
    {"name": "巫术的证明", "english": "", "source_file": "背景特性3.md"},
]


def process_background_traits(report: dict) -> None:
    target_path = ORG_DIR / "背景特性" / "黑市指南BM_背景特性.md"

    text = (SRC_DIR / "背景特性3.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    blocks = split_section_by_entries(text, BACKGROUND_TRAITS)

    for trait in BACKGROUND_TRAITS:
        block = blocks.get(trait["name"])
        if block is None:
            report["warnings"].append(f"未找到背景特性块: {trait['name']}")
            continue
        marker = make_hidden_marker(trait["source_file"], trait["name"])
        english_part = f"（{trait['english']}）" if trait["english"] else ""
        append_entry(
            target_path,
            marker,
            f"## {trait['name']}{english_part}",
            make_source_annotation(trait["source_file"], "背景特性"),
            block,
            report,
            "背景特性",
            trait["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 3. 黑市毒药（源书聚合） ==========

POISON_AGGREGATION = [
    {"name": "黑市毒药", "source_file": "黑市毒药.md"},
]


def process_poisons(report: dict) -> None:
    target_path = ORG_DIR / "装备_魔法物品" / "黑市指南BM_黑市毒药.md"

    text = (SRC_DIR / "黑市毒药.md").read_text(encoding="utf-8")
    text = extract_block_from_heading(text, "黑市毒药")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_leading_image(text)

    blocks = split_section_by_entries(text, POISON_AGGREGATION)
    block = blocks.get("黑市毒药")
    if block is None:
        report["warnings"].append("未找到黑市毒药块")
        return

    marker = make_hidden_marker("黑市毒药.md", "黑市毒药")
    append_entry(
        target_path,
        marker,
        "## 黑市毒药",
        make_source_annotation("黑市毒药.md", "黑市毒药"),
        block,
        report,
        "黑市毒药",
        "黑市毒药",
        str(target_path.relative_to(ORG_DIR)),
    )


# ========== 4. 黑市规则（源书聚合） ==========

RULES_AGGREGATION = [
    {"name": "黑市规则", "source_file": "黑市规则.md"},
]


def process_black_market_rules(report: dict) -> None:
    target_path = ORG_DIR / "规则" / "黑市指南BM_黑市规则.md"

    text = (SRC_DIR / "黑市规则.md").read_text(encoding="utf-8")
    text = extract_block_from_heading(text, "黑市规则")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_leading_image(text)

    blocks = split_section_by_entries(text, RULES_AGGREGATION)
    block = blocks.get("黑市规则")
    if block is None:
        report["warnings"].append("未找到黑市规则块")
        return

    marker = make_hidden_marker("黑市规则.md", "黑市规则")
    append_entry(
        target_path,
        marker,
        "## 黑市规则",
        make_source_annotation("黑市规则.md", "黑市规则"),
        block,
        report,
        "黑市规则",
        "黑市规则",
        str(target_path.relative_to(ORG_DIR)),
    )


# ========== 5. 炼金术师变体 ==========

ALCHEMIST_ARCHETYPES = [
    {"name": "邪术毒师", "english": "Eldritch Poisoner", "source_file": "炼金术师变体.md"},
]


def process_alchemist_archetypes(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "基础职业" / "炼金术师" / "page_71.md"
    if not target_path.exists():
        report["warnings"].append(f"目标文件不存在，跳过炼金术师变体: {target_path}")
        return

    existing, _ = read_text_preserve(target_path)

    for arc in ALCHEMIST_ARCHETYPES:
        names_to_check = [arc["name"], arc["english"]]
        if any(n in existing for n in names_to_check):
            report["skipped"].append(f"炼金术师变体已存在: {arc['name']}")
            continue

        text = (SRC_DIR / arc["source_file"]).read_text(encoding="utf-8")
        text = merge_section_heading_lines(text)
        text = merge_crossline_bold(text)
        text = clean_translator_url(text)
        text = clean_leading_image(text)

        blocks = split_section_by_entries(text, [arc])
        block = blocks.get(arc["name"])
        if block is None:
            report["warnings"].append(f"未找到炼金术师变体块: {arc['name']}")
            continue
        marker = make_hidden_marker(arc["source_file"], arc["name"])
        append_entry(
            target_path,
            marker,
            f"## {arc['name']}（{arc['english']}）〔炼金术师变体〕",
            make_source_annotation(arc["source_file"], "炼金术师变体"),
            block,
            report,
            "炼金术师变体",
            arc["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 6. 吟游诗人变体 ==========

BARD_ARCHETYPES = [
    {"name": "诈骗犯", "english": "Hoaxer", "source_file": "吟游诗人变体.md"},
]


def process_bard_archetypes(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "page_38.md"
    if not target_path.exists():
        report["warnings"].append(f"目标文件不存在，跳过吟游诗人变体: {target_path}")
        return

    existing, _ = read_text_preserve(target_path)

    for arc in BARD_ARCHETYPES:
        names_to_check = [arc["name"], arc["english"]]
        if any(n in existing for n in names_to_check):
            report["skipped"].append(f"吟游诗人变体已存在: {arc['name']}")
            continue

        text = (SRC_DIR / arc["source_file"]).read_text(encoding="utf-8")
        text = merge_section_heading_lines(text)
        text = merge_crossline_bold(text)
        text = clean_translator_url(text)
        text = clean_leading_image(text)

        blocks = split_section_by_entries(text, [arc])
        block = blocks.get(arc["name"])
        if block is None:
            report["warnings"].append(f"未找到吟游诗人变体块: {arc['name']}")
            continue
        marker = make_hidden_marker(arc["source_file"], arc["name"])
        append_entry(
            target_path,
            marker,
            f"## {arc['name']}（{arc['english']}）〔吟游诗人变体〕",
            make_source_annotation(arc["source_file"], "吟游诗人变体"),
            block,
            report,
            "吟游诗人变体",
            arc["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 7. 尸体贸易（源书聚合） ==========

CORPSE_TRADE_AGGREGATION = [
    {"name": "尸体贸易", "source_file": "尸体贸易.md"},
]


def process_corpse_trade(report: dict) -> None:
    target_path = ORG_DIR / "规则" / "黑市指南BM_尸体贸易.md"

    text = (SRC_DIR / "尸体贸易.md").read_text(encoding="utf-8")
    text = extract_block_from_heading(text, "尸体贸易")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_leading_image(text)

    blocks = split_section_by_entries(text, CORPSE_TRADE_AGGREGATION)
    block = blocks.get("尸体贸易")
    if block is None:
        report["warnings"].append("未找到尸体贸易块")
        return

    marker = make_hidden_marker("尸体贸易.md", "尸体贸易")
    append_entry(
        target_path,
        marker,
        "## 尸体贸易",
        make_source_annotation("尸体贸易.md", "尸体贸易"),
        block,
        report,
        "尸体贸易",
        "尸体贸易",
        str(target_path.relative_to(ORG_DIR)),
    )


# ========== 8. 诅咒遗物（源书聚合） ==========

CURSED_RELICS_AGGREGATION = [
    {"name": "诅咒遗物", "source_file": "诅咒遗物.md"},
]


def process_cursed_relics(report: dict) -> None:
    target_path = ORG_DIR / "装备_魔法物品" / "黑市指南BM_诅咒遗物.md"

    text = (SRC_DIR / "诅咒遗物.md").read_text(encoding="utf-8")
    text = extract_block_from_heading(text, "诅咒遗物")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_leading_image(text)

    blocks = split_section_by_entries(text, CURSED_RELICS_AGGREGATION)
    block = blocks.get("诅咒遗物")
    if block is None:
        report["warnings"].append("未找到诅咒遗物块")
        return

    marker = make_hidden_marker("诅咒遗物.md", "诅咒遗物")
    append_entry(
        target_path,
        marker,
        "## 诅咒遗物",
        make_source_annotation("诅咒遗物.md", "诅咒遗物"),
        block,
        report,
        "诅咒遗物",
        "诅咒遗物",
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
    process_background_traits(report)
    process_poisons(report)
    process_black_market_rules(report)
    process_alchemist_archetypes(report)
    process_bard_archetypes(report)
    process_corpse_trade(report)
    process_cursed_relics(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
