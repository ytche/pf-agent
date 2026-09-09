#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 炼狱血脉（Blood of Fiends）BoF 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/炼狱血脉
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/炼狱血脉"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "BloodOfFiends_reorganization_report.md"

SOURCE_BOOK = "炼狱血脉（Blood of Fiends）BoF"
SOURCE_BOOK_SHORT = "BoF"


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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 炼狱血脉BoF{l3_part}"


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


def find_title_starts(text: str, titles: list[str]) -> list[tuple[int, str]]:
    starts = []
    for title in titles:
        pattern = re.compile(r"\*\*" + re.escape(title) + r"\*\*")
        m = pattern.search(text)
        if not m:
            pattern = re.compile(re.escape(title))
            m = pattern.search(text)
        if not m:
            raise ValueError(f"无法在源文件中定位条目：{title}")
        starts.append((m.start(), title))
    starts.sort(key=lambda x: x[0])
    return starts


# ========== 1. 吟游诗人世界名著 ==========

MASTERPIECE_TITLES = [
    "燃欲之舞（舞蹈）",
    "骇亡音律（弦乐）",
    "痰之歌（歌唱）",
]


def process_bard_masterpieces(report: dict) -> None:
    src_path = SRC_DIR / "page_523.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "传世名作汇总.md"
    section_marker = make_hidden_marker("page_523.md", "__aggregate__")

    if target_path.exists() and section_marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("传世名作聚合已存在: 炼狱血脉 BoF 传世名作")
        return

    starts = find_title_starts(text, MASTERPIECE_TITLES)

    entry_parts = []
    l3 = "变体/选项 → 吟游诗人传世名作"
    for idx, (start_pos, title) in enumerate(starts):
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        block = re.sub(r"^\s*\*\*" + re.escape(title) + r"\*\*\s*", "", block).strip()
        entry_marker = make_hidden_marker("page_523.md", title)
        entry_parts.append(entry_marker)
        entry_parts.append(f"### {title}")
        entry_parts.append(make_source_annotation("page_523.md", l3))
        entry_parts.append("")
        entry_parts.append(block)
        entry_parts.append("")

    section_block = "\n".join(entry_parts)
    safe_append_to_file(
        target_path,
        section_marker,
        "## 炼狱血脉 BoF 传世名作",
        make_source_annotation("page_523.md", l3),
        section_block,
    )
    for _, title in starts:
        report["merged"].append({"type": "吟游诗人传世名作", "name": title, "target": str(target_path.relative_to(ORG_DIR))})


# ========== 2. 魔裔能力变体 ==========

def process_variant_abilities(report: dict) -> None:
    src_path = SRC_DIR / "page_831.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text).strip()

    target_path = ORG_DIR / "种族" / "常见种族" / "魔裔" / "魔裔种族特性替换汇总.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 魔裔种族特性替换汇总\n\n", "\n")

    marker = make_hidden_marker("page_831.md", "魔裔能力变体")
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("魔裔能力变体已存在")
        return

    heading = "## 魔裔能力变体（Variant Tiefling Abilities）"
    l3 = "种族替换特性"
    safe_append_to_file(target_path, marker, heading, make_source_annotation("page_831.md", l3), text)
    report["merged"].append({"type": "魔裔能力变体", "name": heading.lstrip("# ").split("（")[0], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 3. 魔裔亚种 ==========

def process_heritages(report: dict) -> None:
    src_path = SRC_DIR / "page_832.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text).strip()

    target_path = ORG_DIR / "种族" / "常见种族" / "魔裔" / "魔裔种族特性替换汇总.md"
    if not target_path.exists():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        write_text_preserve(target_path, "# 魔裔种族特性替换汇总\n\n", "\n")

    marker = make_hidden_marker("page_832.md", "魔裔亚种")
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("魔裔亚种已存在")
        return

    heading = "## 魔裔亚种（Tiefling Heritages）"
    l3 = "种族替换特性"
    safe_append_to_file(target_path, marker, heading, make_source_annotation("page_832.md", l3), text)
    report["merged"].append({"type": "魔裔亚种", "name": heading.lstrip("# ").split("（")[0], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 4. 炼狱专长 ==========

FEATS = [
    {"cn": "先祖的蔑视", "en": "Ancestral Scorn", "type": ""},
    {"cn": "毁灭之旗", "en": "Banner of Doom", "type": "（战斗专长）"},
    {"cn": "致盲偷袭", "en": "Blinding Sneak Attack", "type": "（战斗专长）"},
    {"cn": "炼狱黑暗", "en": "Fiendish Darkness", "type": ""},
    {"cn": "炼狱假象", "en": "Fiendish Facade", "type": ""},
    {"cn": "炼狱抗性", "en": "Fiendish Resilience", "type": ""},
    {"cn": "污秽之怒", "en": "Fury of the Tainted", "type": "（战斗专长）"},
    {"cn": "精通炼狱黑暗", "en": "Improved Fiendish Darkness", "type": ""},
    {"cn": "精通炼狱魔力", "en": "Improved Fiendish Sorcery", "type": ""},
    {"cn": "精通污秽之怒", "en": "Improved Fury of the Tainted", "type": "（战斗专长）"},
    {"cn": "恐怖面容", "en": "Monstrous Mask", "type": ""},
    {"cn": "鲁莽瞄准", "en": "Reckless Aim", "type": "（战斗专长）"},
    {"cn": "骇人面容", "en": "Terrifying Mask", "type": ""},
    {"cn": "顽恶之勇", "en": "Wicked Valor", "type": ""},
]


def find_feat_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for feat in FEATS:
        pattern = re.compile(r"(?:^|(?<=[。\n\r]))\s*" + re.escape(feat["cn"]) + r"(?:（[^）]+）)?")
        m = pattern.search(text)
        if not m:
            raise ValueError(f"无法在 page_833.md 中定位专长：{feat['cn']}")
        starts.append((m.start(), feat))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_feat_title(block: str, feat: dict) -> str:
    cn = re.escape(feat["cn"])
    en = r"\s+".join(re.escape(word) for word in feat["en"].split())
    type_zh = re.escape(feat.get("type", "")) if feat.get("type") else ""
    # 英文名可能被全角括号包裹，也可能直接接在中文名后（无空格），允许跨行
    en_group = r"(?:（" + en + r"(?:\([^)]+\))?）|" + en + r"(?:\([^)]+\))?)?"
    pattern = re.compile(
        r"^\s*" + cn + r"(?:" + type_zh + r")?\s*" + en_group + r"\s*",
        re.DOTALL,
    )
    m = pattern.search(block)
    if m:
        return block[m.end():].strip()
    return block


def process_feats(report: dict) -> None:
    src_path = SRC_DIR / "page_833.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "专长" / "炼狱血脉BoF_专长.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 炼狱血脉 BoF 专长\n\n", "\n")

    starts = find_feat_starts(text)
    l3 = "专长"
    for idx, (start_pos, feat) in enumerate(starts):
        marker = make_hidden_marker("page_833.md", feat["cn"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"专长已存在: {feat['cn']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        block = strip_feat_title(block, feat)
        title_full = f"{feat['cn']}{feat.get('type', '')} {feat['en']}"
        heading = f"## {title_full}".strip()
        safe_append_to_file(target_path, marker, heading, make_source_annotation("page_833.md", l3), block)
        report["merged"].append({"type": "专长", "name": feat["cn"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 5. 魔裔种族背景特性 ==========

TRAITS = [
    {"cn": "预知邪恶", "en": "Anticipate Evil"},
    {"cn": "威吓野兽", "en": "Beast Bully"},
    {"cn": "暗之祝福", "en": "Blessing of Darkness"},
    {"cn": "生于诅咒", "en": "Born Damned"},
    {"cn": "黑暗魔法亲和", "en": "Dark Magic Affinity"},
    {"cn": "保持警惕", "en": "Ever Wary"},
    {"cn": "家族联系", "en": "Family Connections"},
    {"cn": "无依无靠", "en": "Friendless"},
    {"cn": "煽动者", "en": "Inciter"},
    {"cn": "没有母亲", "en": "Motherless"},
    {"cn": "延时法术", "en": "Prolong Magic"},
    {"cn": "高傲的怒火", "en": "Prideful Temper"},
    {"cn": "阴影暗杀者", "en": "Shadow Stabber"},
    {"cn": "自我毁灭", "en": "Suicidal"},
    {"cn": "暮光之热诚", "en": "Twilight Zeal"},
    {"cn": "走卒", "en": "Underling"},
]


def find_trait_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for trait in TRAITS:
        pattern = re.compile(r"(?:^|(?<=[。\n\r]))\s*" + re.escape(trait["cn"]))
        m = pattern.search(text)
        if not m:
            raise ValueError(f"无法在 page_834.md 中定位背景特性：{trait['cn']}（{trait['en']}）")
        starts.append((m.start(), trait))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_trait_title(block: str, trait: dict) -> str:
    en = r"\s+".join(re.escape(word) for word in trait["en"].split())
    pattern = re.compile(
        r"^\s*" + re.escape(trait["cn"]) + r"(?:（" + en + r"）)?\s*：?\s*",
        re.DOTALL,
    )
    m = pattern.search(block)
    if m:
        return block[m.end():].strip()
    return block


def process_race_traits(report: dict) -> None:
    src_path = SRC_DIR / "page_834.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "背景特性" / "炼狱血脉BoF_背景特性.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 炼狱血脉 BoF 背景特性\n\n", "\n")

    starts = find_trait_starts(text)
    l3 = "背景特性"
    for idx, (start_pos, trait) in enumerate(starts):
        marker = make_hidden_marker("page_834.md", trait["cn"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"背景特性已存在: {trait['cn']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        if "**随机魔裔特征" in block:
            block = block[: block.index("**随机魔裔特征")]
        block = strip_trailing_artifacts(block)
        block = strip_trait_title(block, trait)
        heading = f"## {trait['cn']}（{trait['en']}）"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("page_834.md", l3), block)
        report["merged"].append({"type": "背景特性", "name": trait["cn"], "target": str(target_path.relative_to(ORG_DIR))})

    report["skipped"].append("page_834.md 随机魔裔特征表为纯风味随机表，未合并")


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
    process_bard_masterpieces(report)
    process_variant_abilities(report)
    process_heritages(report)
    process_feats(report)
    process_race_traits(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
