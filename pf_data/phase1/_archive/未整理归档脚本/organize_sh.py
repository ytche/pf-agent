#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 间谍大师手册（Spymaster's Handbook）SH 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/间谍大师手册SH/
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/间谍大师手册SH"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "SH_reorganization_report.md"

SOURCE_BOOK = "间谍大师手册（Spymaster's Handbook）SH"
SOURCE_BOOK_SHORT = "SH"


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
    if existing and not existing.endswith("\n"):
        existing += line_ending
    write_text_preserve(path, existing + text, line_ending)


def make_source_annotation(source_file: str, l3: str = "") -> str:
    l3_part = f" → {l3}" if l3 else ""
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 间谍大师手册SH{l3_part}"


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


def is_title_span(span: str) -> bool:
    if not re.search(r"[一-鿿]", span):
        return False
    if re.search(r"[A-Za-z]", span):
        return True
    if re.search(r"[（(][^）)]+[）)]", span):
        return True
    return False


def find_entry_headings(section_text: str, entries: list[dict]) -> list[tuple[int, dict, str]]:
    positions = []
    for entry in entries:
        name = entry["name"]
        english = entry.get("english", "")
        eng_pat = re.escape(english).replace(r"\ ", r"\s+")
        patterns = [
            re.compile(r"\*\*[^*]*?(?<![一-鿿])" + re.escape(name) + r"(?![一-鿿])[^*]*?\*\*", re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*[（(]\s*[^）)]*?" + eng_pat + r"[^）)]*?\s*[）)]", re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*[（(][^）)]+[）)]\s*" + eng_pat, re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*" + eng_pat, re.IGNORECASE),
        ]
        found = False
        for pattern in patterns:
            m = pattern.search(section_text)
            if m:
                start = m.start()
                # 若匹配点前紧邻 **，将起点前移到加粗标记开头
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


def extract_block_by_name(text: str, name: str, english: str = "") -> str | None:
    base_pattern = re.compile(r"\*\*[^*]*?" + re.escape(name) + r"[^*]*?\*\*")
    candidates = [m for m in base_pattern.finditer(text) if is_title_span(m.group(0))]

    if candidates and english:
        eng_norm = " ".join(english.lower().split())
        pref = []
        for m in candidates:
            span = m.group(0)
            norm = re.sub(r"\s+", " ", span).lower()
            if eng_norm in norm:
                pref.append(m)
        if pref:
            candidates = pref

    if candidates:
        start_match = min(candidates, key=lambda m: len(m.group(0)))
        start = start_match.start()
        rest = text[start_match.end():]
        next_stop = re.search(r"\n\s*\n|\n\s*\*\*[^*]+\*\*", rest)
        if next_stop:
            end = start_match.end() + next_stop.start()
        else:
            end = len(text)
        return text[start:end].strip()

    if english:
        eng_pat = re.escape(english).replace(r"\ ", r"\s*")
        plain_pattern = re.compile(
            r"(?:^|\n)\s*(" + re.escape(name) + r"(?:(?:\s*[（(]\s*[^）)]*?" + eng_pat + r"[^）)]*?\s*[）)])|(?:\s*" + eng_pat + r")))",
            re.IGNORECASE,
        )
        pm = plain_pattern.search(text)
        if pm:
            start = pm.start()
            rest = text[pm.end():]
            next_stop = re.search(r"\n\s*\n|\n\s*\*\*[^*]+\*\*", rest)
            if next_stop:
                end = pm.end() + next_stop.start()
            else:
                end = len(text)
            return text[start:end].strip()

    return None


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


# ========== 1. 缺陷与背景特性 ==========

DEFECTS = [
    {"name": "空洞面具", "english": "Empty Mask", "source_file": "背景特性32.md"},
]

TRAITS = [
    {"name": "犯罪世家", "english": "Criminal Roots", "source_file": "背景特性32.md", "type": "社会"},
]


def process_backgrounds(report: dict) -> None:
    source_file = "背景特性32.md"
    text = (SRC_DIR / source_file).read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    blocks = split_section_by_entries(text, DEFECTS + TRAITS)

    # 缺陷 -> 缺陷.md
    for d in DEFECTS:
        block = blocks.get(d["name"])
        if block is None:
            report["warnings"].append(f"未找到缺陷块: {d['name']}")
            continue
        target_path = ORG_DIR / "缺陷.md"
        marker = make_hidden_marker(d["source_file"], d["name"])
        append_entry(
            target_path,
            marker,
            f"## {d['name']}（{d['english']}）",
            make_source_annotation(d["source_file"], "缺陷"),
            block,
            report,
            "缺陷",
            d["name"],
            "缺陷.md",
        )

    # 背景特性 -> 背景特性/间谍大师手册SH_背景特性.md
    target_path = ORG_DIR / "背景特性" / "间谍大师手册SH_背景特性.md"
    for t in TRAITS:
        block = blocks.get(t["name"])
        if block is None:
            report["warnings"].append(f"未找到背景特性块: {t['name']}")
            continue
        marker = make_hidden_marker(t["source_file"], t["name"])
        append_entry(
            target_path,
            marker,
            f"## {t['name']}（{t['english']}）",
            make_source_annotation(t["source_file"], "背景特性"),
            block,
            report,
            "背景特性",
            t["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 2. 职业变体 ==========

ARCHETYPES = [
    {"name": "盖丁侠士", "english": "Agathiel", "class": "侠客", "source_file": "变体/侠客.md"},
    {"name": "侦查使", "english": "Teisatsu", "class": "侠客", "source_file": "变体/侠客.md"},
]


def process_archetypes(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "极限诡道" / "侠客" / "职业变体汇总.md"
    if not target_path.exists():
        report["warnings"].append(f"目标文件不存在，跳过职业变体: {target_path}")
        return

    existing, _ = read_text_preserve(target_path)

    text = (SRC_DIR / "变体" / "侠客.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    blocks = split_section_by_entries(text, ARCHETYPES)

    for arc in ARCHETYPES:
        # 这两个变体已在 极限诡道/侠客/职业变体汇总.md 中存在（不同译名），跳过合并
        names_to_check = [arc["name"], arc["english"]]
        if arc["name"] == "盖丁侠士":
            names_to_check.append("盖丁圣者")
        if any(n in existing for n in names_to_check):
            report["skipped"].append(f"变体已存在: {arc['name']}")
            continue

        block = blocks.get(arc["name"])
        if block is None:
            report["warnings"].append(f"未找到变体块: {arc['name']}")
            continue
        marker = make_hidden_marker(arc["source_file"], arc["name"])
        append_entry(
            target_path,
            marker,
            f"## {arc['name']}（{arc['english']}）〔{arc['class']}变体〕",
            make_source_annotation(arc["source_file"], "变体/职业选项"),
            block,
            report,
            "变体",
            arc["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 3. 武器附魔 ==========

WEAPON_ENCHANTS = [
    {"name": "次级隐匿", "english": "Lesser Concealed", "source_file": "武器附魔7.md"},
    {"name": "隐匿", "english": "Concealed", "source_file": "武器附魔7.md"},
]


def process_weapon_enchants(report: dict) -> None:
    target_path = ORG_DIR / "装备_魔法物品" / "武器附魔" / "间谍大师手册SH_武器附魔.md"

    text = (SRC_DIR / "武器附魔7.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    blocks = split_section_by_entries(text, WEAPON_ENCHANTS)

    for we in WEAPON_ENCHANTS:
        block = blocks.get(we["name"])
        if block is None:
            report["warnings"].append(f"未找到武器附魔块: {we['name']}")
            continue
        marker = make_hidden_marker(we["source_file"], we["name"])
        append_entry(
            target_path,
            marker,
            f"## {we['name']}（{we['english']}）",
            make_source_annotation(we["source_file"], "武器附魔"),
            block,
            report,
            "武器附魔",
            we["name"],
            str(target_path.relative_to(ORG_DIR)),
        )


# ========== 4. 专长 ==========

FEATS = [
    {"name": "遗忘注视", "english": "Oblivating Stare", "source_file": "专长36.md"},
    {"name": "攀向高层", "english": "Ascendant", "source_file": "专长36.md"},
    {"name": "调解者", "english": "Concilator", "source_file": "专长36.md"},
    {"name": "无误正义", "english": "Inerrant Justice", "source_file": "专长36.md"},
    {"name": "渗透者", "english": "Infiltrator", "source_file": "专长36.md"},
    {"name": "神秘魔源", "english": "Magical Enigma", "source_file": "专长36.md"},
    {"name": "傀儡大师", "english": "Puppet Master", "source_file": "专长36.md"},
    {"name": "宿敌", "english": "Rival", "source_file": "专长36.md"},
    {"name": "超自然间谍", "english": "Supernatural Spy", "source_file": "专长36.md"},
    {"name": "狡诈战士", "english": "Wily Warrior", "source_file": "专长36.md"},
    {"name": "黄金联盟刺青", "english": "Golden League Tattoos", "source_file": "专长36.md"},
    {"name": "洞察忠诚", "english": "Sense Loyalties", "source_file": "专长36.md"},
    {"name": "精纯卫队猛攻", "english": "Pure Legion Assault", "source_file": "专长36.md"},
]


def process_feats(report: dict) -> None:
    target_path = ORG_DIR / "专长" / "间谍大师手册SH_专长.md"

    text = (SRC_DIR / "专长36.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    blocks = split_section_by_entries(text, FEATS)

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
    process_backgrounds(report)
    process_archetypes(report)
    process_weapon_enchants(report)
    process_feats(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
