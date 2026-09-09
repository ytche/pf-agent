#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 夜之血脉（Blood of the Night）BotN 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/夜之血脉BotN
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/夜之血脉BotN"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "BloodOfTheNight_reorganization_report.md"

SOURCE_BOOK = "夜之血脉（Blood of the Night）BotN"
SOURCE_BOOK_SHORT = "BotN"


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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 夜之血脉BotN{l3_part}"


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


# ========== 1. page_822.md 吸血裔种族特性 ==========

def process_dhampir_traits(report: dict) -> None:
    src_path = SRC_DIR / "page_822.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "种族" / "夜之血脉BotN_吸血裔种族特性.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 夜之血脉 BotN 吸血裔种族特性\n\n", "\n")

    marker = make_hidden_marker("page_822.md", "__aggregate__")
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("吸血裔种族特性聚合已存在: page_822.md")
        return

    block = strip_trailing_artifacts(text)
    safe_append_to_file(
        target_path,
        marker,
        "## 吸血裔（Dhampir）种族特性",
        make_source_annotation("page_822.md", "种族特性"),
        block,
    )
    report["merged"].append({"type": "种族特性", "name": "吸血裔种族特性", "target": str(target_path.relative_to(ORG_DIR))})


# ========== 2. page_823.md 专长 ==========

FEATS = [
    {"cn": "吸血鬼变身", "en": "Vampire Transformation"},
    {"cn": "进阶兽化变身", "en": "Improved Bestial Transformation"},
    {"cn": "进阶集群形态", "en": "Improved Swarm Form"},
    {"cn": "进阶气体形态", "en": "Improved Gaseous Form"},
    {"cn": "嫌恶耐性", "en": "Aversion Tolerance"},
    {"cn": "饥饿耐性", "en": "Famine Tolerance"},
    {"cn": "吸血同伴", "en": "Vampiric Companion"},
    {"cn": "各种护尸符", "en": "Variant Prayer Scroll"},
    {"cn": "信念加持", "en": "Conviction"},
    {"cn": "圣歌者", "en": "Hymn Singer"},
    {"cn": "", "en": "Life-Dominant Soul"},
    {"cn": "强力圣徽", "en": "Potent Holy Symbol"},
    {"cn": "科班吸血鬼猎人", "en": "Schooled Resolve"},
]


def find_feat_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for feat in FEATS:
        cn = feat["cn"]
        en = re.escape(feat["en"])
        patterns = []
        if cn:
            # 中文名（可能带跨行英文括号标题）
            patterns.append(re.compile(re.escape(cn) + r"\s*\("))
            patterns.append(re.compile(re.escape(cn)))
        # 英文-only 优先匹配带括号形式，避免把左括号留在上一个条目中
        patterns.append(re.compile(r"\(" + en + r"\)"))
        patterns.append(re.compile(r"\b" + en + r"\b"))
        m = None
        for pat in patterns:
            m = pat.search(text)
            if m:
                break
        if not m:
            if cn:
                m = re.search(re.escape(cn), text)
            if not m:
                m = re.search(re.escape(feat["en"]), text, re.IGNORECASE)
            if not m:
                raise ValueError(f"无法在 page_823.md 中定位专长：{cn or feat['en']}")
        starts.append((m.start(), feat))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_feat_title(block: str, feat: dict) -> str:
    cn = feat["cn"]
    en = re.escape(feat["en"])
    patterns = []
    if cn:
        # 匹配中文名 + 括号内跨行英文标题，直到第一个半角右括号
        patterns.append(re.compile(r"^\s*\*?\*?" + re.escape(cn) + r"\s*\([^)]*\)\s*\*?\*?\s*", re.DOTALL))
        patterns.append(re.compile(r"^\s*\*?\*?" + re.escape(cn) + r"\s*" + en + r"(?:\s*\([^)]*\))?\s*\*?\*?\s*", re.DOTALL))
        patterns.append(re.compile(r"^\s*\*?\*?" + re.escape(cn) + r"\s*\*?\*?\s*"))
    patterns.append(re.compile(r"^\s*\*?\*?\(" + en + r"\)\s*\*?\*?\s*", re.IGNORECASE | re.DOTALL))
    patterns.append(re.compile(r"^\s*\*?\*?" + en + r"(?:\s*\([^)]*\))?\s*\*?\*?\s*", re.IGNORECASE | re.DOTALL))
    for pat in patterns:
        m = pat.search(block)
        if m:
            block = block[m.end():].strip()
            break
    # 剥除可能残留的跨行英文标题（逐行或跨两行）
    lines = block.splitlines()
    cleaned: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if re.match(r"^" + en + r"(?:\s*\([^)]*\))?\s*$", line, re.IGNORECASE):
            i += 1
            continue
        if i + 1 < len(lines):
            combined = line + " " + lines[i + 1].strip()
            if re.match(r"^" + en + r"(?:\s*\([^)]*\))?\s*", combined, re.IGNORECASE):
                rest = re.sub(r"^" + en + r"(?:\s*\([^)]*\))?\s*", "", combined, flags=re.IGNORECASE).strip()
                if rest:
                    cleaned.append(rest)
                i += 2
                continue
        cleaned.append(lines[i])
        i += 1
    return "\n".join(cleaned).strip()


def process_feats(report: dict) -> None:
    src_path = SRC_DIR / "page_823.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "专长" / "夜之血脉BotN_专长.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 夜之血脉 BotN 专长\n\n", "\n")

    try:
        starts = find_feat_starts(text)
    except ValueError as e:
        report["warnings"].append(str(e))
        marker = make_hidden_marker("page_823.md", "__aggregate__")
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append("专长聚合已存在: page_823.md")
            return
        block = strip_trailing_artifacts(text)
        safe_append_to_file(
            target_path,
            marker,
            "## 夜之血脉 BotN 专长",
            make_source_annotation("page_823.md", "专长"),
            block,
        )
        report["merged"].append({"type": "专长", "name": "夜之血脉 BotN 专长（聚合）", "target": str(target_path.relative_to(ORG_DIR))})
        return

    l3 = "专长"
    for idx, (start_pos, feat) in enumerate(starts):
        marker = make_hidden_marker("page_823.md", feat["cn"] or feat["en"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"专长已存在: {feat['cn'] or feat['en']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        block = strip_feat_title(block, feat)
        if feat["cn"]:
            heading = f"## {feat['cn']}（{feat['en']}）"
        else:
            heading = f"## {feat['en']}"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("page_823.md", l3), block)
        report["merged"].append({"type": "专长", "name": feat["cn"] or feat["en"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 3. page_824.md 法术 ==========

SPELLS = [
    {"cn": "显现嫌恶", "en": "Display Aversion"},
    {"cn": "支配连接", "en": "Domination Link"},
    {"cn": "弱点投射", "en": "Project Weakness"},
    {"cn": "盗取青春", "en": "Steal Years"},
    {"cn": "高等盗取青春", "en": "Steal Years, Greater"},
    {"cn": "化酒为血", "en": "Transmute wine to blood"},
]


def find_spell_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for spell in SPELLS:
        cn = re.escape(spell["cn"])
        en = re.escape(spell["en"])
        patterns = [
            re.compile(r"(?:^|(?<=[\n\r\s]))\s*\*?\*?" + cn + r"\s*\("),
            re.compile(r"(?:^|(?<=[\n\r\s]))\s*\*?\*?" + cn + r"\s*"),
        ]
        m = None
        for pat in patterns:
            m = pat.search(text)
            if m:
                break
        if not m:
            m = re.search(re.escape(spell["cn"]), text)
            if not m:
                raise ValueError(f"无法在 page_824.md 中定位法术：{spell['cn']}（{spell['en']}）")
        starts.append((m.start(), spell))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_spell_title(block: str, spell: dict) -> str:
    cn = re.escape(spell["cn"])
    en = re.escape(spell["en"])
    patterns = [
        re.compile(r"^\s*\*?\*?" + cn + r"\s*\([^)]*\)\s*\*?\*?\s*", re.DOTALL),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*" + en + r"(?:\s*\([^)]*\))?\s*\*?\*?\s*", re.DOTALL),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*\*?\*?\s*"),
    ]
    for pat in patterns:
        m = pat.search(block)
        if m:
            block = block[m.end():].strip()
            break
    return block


def process_spells(report: dict) -> None:
    src_path = SRC_DIR / "page_824.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "法术" / "夜之血脉BotN_法术.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 夜之血脉 BotN 法术\n\n", "\n")

    try:
        starts = find_spell_starts(text)
    except ValueError as e:
        report["warnings"].append(str(e))
        marker = make_hidden_marker("page_824.md", "__aggregate__")
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append("法术聚合已存在: page_824.md")
            return
        block = strip_trailing_artifacts(text)
        safe_append_to_file(
            target_path,
            marker,
            "## 夜之血脉 BotN 法术",
            make_source_annotation("page_824.md", "法术"),
            block,
        )
        report["merged"].append({"type": "法术", "name": "夜之血脉 BotN 法术（聚合）", "target": str(target_path.relative_to(ORG_DIR))})
        return

    l3 = "法术"
    for idx, (start_pos, spell) in enumerate(starts):
        marker = make_hidden_marker("page_824.md", spell["cn"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"法术已存在: {spell['cn']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        block = strip_spell_title(block, spell)
        heading = f"## {spell['cn']}（{spell['en']}）"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("page_824.md", l3), block)
        report["merged"].append({"type": "法术", "name": spell["cn"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 4. page_825.md 魔法物品 ==========

ITEMS = [
    {"cn": "放血扳指", "en": "Bloodletting Thimble"},
    {"cn": "", "en": "Deadly Draught"},
    {"cn": "", "en": "Dread Heart of Life"},
    {"cn": "力场网", "en": "Force Net"},
    {"cn": "吸血鬼牙项链", "en": "Necklace of Fangs"},
    {"cn": "正义之桩", "en": "Stake of the Righteous"},
]


def find_item_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for item in ITEMS:
        cn = item["cn"]
        en = re.escape(item["en"])
        patterns = []
        if cn:
            patterns.append(re.compile(r"(?:^|(?<= [\n\r\s]))\s*\*?\*?" + re.escape(cn) + r"\s*\(" + en + r"\)"))
            patterns.append(re.compile(r"(?:^|(?<= [\n\r\s]))\s*\*?\*?" + re.escape(cn) + r"\s*" + en))
            patterns.append(re.compile(r"(?:^|(?<= [\n\r\s]))\s*\*?\*?" + re.escape(cn) + r"\s*"))
        patterns.append(re.compile(r"(?:^|(?<=[\n\r\s]))\s*\(" + en + r"\)"))
        patterns.append(re.compile(r"(?:^|(?<=[\n\r\s]))\s*" + en + r"\s*"))
        m = None
        for pat in patterns:
            m = pat.search(text)
            if m:
                break
        if not m:
            if cn:
                m = re.search(re.escape(cn), text)
            if not m:
                m = re.search(re.escape(item["en"]), text, re.IGNORECASE)
            if not m:
                raise ValueError(f"无法在 page_825.md 中定位物品：{cn or item['en']}")
        starts.append((m.start(), item))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_item_title(block: str, item: dict) -> str:
    cn = item["cn"]
    en = re.escape(item["en"])
    patterns = []
    if cn:
        patterns.append(re.compile(r"^\s*\*?\*?" + re.escape(cn) + r"\s*\(" + en + r"(?:\s*[^）]*)?\)\s*\*?\*?\s*", re.DOTALL))
        patterns.append(re.compile(r"^\s*\*?\*?" + re.escape(cn) + r"\s*" + en + r"(?:\s*\([^)]*\))?\s*\*?\*?\s*", re.DOTALL))
        patterns.append(re.compile(r"^\s*\*?\*?" + re.escape(cn) + r"\s*\*?\*?\s*"))
    patterns.append(re.compile(r"^\s*\*?\*?\(" + en + r"\)\s*\*?\*?\s*", re.IGNORECASE | re.DOTALL))
    patterns.append(re.compile(r"^\s*\*?\*?" + en + r"(?:\s*\([^)]*\))?\s*\*?\*?\s*", re.IGNORECASE | re.DOTALL))
    for pat in patterns:
        m = pat.search(block)
        if m:
            block = block[m.end():].strip()
            break
    return block


def process_magic_items(report: dict) -> None:
    src_path = SRC_DIR / "page_825.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "装备_魔法物品" / "夜之血脉BotN_物品.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 夜之血脉 BotN 物品\n\n", "\n")

    # page_825.md 中 Deadly Draught 与 Dread Heart of Life 没有中文名，且紧接在前一物品造物需求后出现，
    # 无法可靠拆分，按源书整页聚合。
    marker = make_hidden_marker("page_825.md", "__aggregate__")
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("物品聚合已存在: page_825.md")
        return
    block = strip_trailing_artifacts(text)
    safe_append_to_file(
        target_path,
        marker,
        "## 夜之血脉 BotN 物品",
        make_source_annotation("page_825.md", "物品"),
        block,
    )
    report["merged"].append({"type": "物品", "name": "夜之血脉 BotN 物品（聚合）", "target": str(target_path.relative_to(ORG_DIR))})


# ========== 5. page_826.md 不死生物饥渴可选规则 ==========

def process_undead_hunger_rules(report: dict) -> None:
    src_path = SRC_DIR / "page_826.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "规则" / "夜之血脉BotN_不死生物饥渴可选规则.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 夜之血脉 BotN 不死生物饥渴可选规则\n\n", "\n")

    marker = make_hidden_marker("page_826.md", "__aggregate__")
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("不死生物饥渴可选规则已存在: page_826.md")
        return

    block = strip_trailing_artifacts(text)
    safe_append_to_file(
        target_path,
        marker,
        "## 不死生物饥渴（Undead Hunger）可选规则",
        make_source_annotation("page_826.md", "可选规则"),
        block,
    )
    report["merged"].append({"type": "可选规则", "name": "不死生物饥渴可选规则", "target": str(target_path.relative_to(ORG_DIR))})


# ========== main ==========

def run() -> None:
    report = {"merged": [], "skipped": [], "warnings": []}

    process_dhampir_traits(report)
    process_feats(report)
    process_spells(report)
    process_magic_items(report)
    process_undead_hunger_rules(report)

    lines = [
        "# 夜之血脉（Blood of the Night）BotN 整理报告",
        "",
        f"生成时间：{datetime.now().isoformat()}",
        "",
        "## 整理内容",
        "",
    ]
    for item in report["merged"]:
        lines.append(f"- {item['type']}：{item['name']} → {item['target']}")
    lines.append("")
    lines.append("## 跳过项")
    lines.append("")
    if report["skipped"]:
        for s in report["skipped"]:
            lines.append(f"- {s}")
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("## 警告")
    lines.append("")
    if report["warnings"]:
        for w in report["warnings"]:
            lines.append(f"- {w}")
    else:
        lines.append("- 无")
    lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"整理完成，报告见 {REPORT_PATH}")


if __name__ == "__main__":
    run()
