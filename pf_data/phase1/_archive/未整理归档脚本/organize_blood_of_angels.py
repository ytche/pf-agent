#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 天界血脉（Blood of Angels）BoA 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/天界血脉
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/天界血脉"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "BloodOfAngels_reorganization_report.md"

SOURCE_BOOK = "天界血脉（Blood of Angels）BoA"
SOURCE_BOOK_SHORT = "BoA"


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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 天界血脉BoA{l3_part}"


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


def extract_block_whole_file(text: str) -> str:
    text = clean_translator_url(text)
    text = clean_leading_image(text)
    return text.strip()


def strip_trailing_artifacts(block: str) -> str:
    lines = block.splitlines()
    while lines and (lines[-1].strip() == "" or re.match(r"^\*+$", lines[-1].strip())):
        lines.pop()
    return "\n".join(lines)


# ========== 1. 吟游诗人世界名著 ==========

MASTERPIECE_TITLES = [
    "天堂花开派拉维（舞蹈）",
    "天国秩序回旋曲（歌唱）",
    "乐土之心交响曲（键盘乐器，吹奏乐器）",
]


def find_title_starts(text: str, titles: list[str]) -> list[tuple[int, str]]:
    starts = []
    for title in titles:
        # 优先匹配加粗标题，否则退回到纯文本标题
        pattern = re.compile(r"\*\*" + re.escape(title) + r"\*\*")
        m = pattern.search(text)
        if not m:
            pattern = re.compile(re.escape(title))
            m = pattern.search(text)
        if not m:
            raise ValueError(f"无法在 page_522.md 中定位条目：{title}")
        starts.append((m.start(), title))
    starts.sort(key=lambda x: x[0])
    return starts


def process_bard_masterpieces(report: dict) -> None:
    src_path = SRC_DIR / "page_522.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "传世名作汇总.md"
    section_marker = make_hidden_marker("page_522.md", "__aggregate__")

    if target_path.exists() and section_marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("传世名作聚合已存在: 天界血脉 BoA 传世名作")
        return

    starts = find_title_starts(text, MASTERPIECE_TITLES)

    entry_parts = []
    l3 = "变体/选项 → 吟游诗人传世名作"
    for idx, (start_pos, title) in enumerate(starts):
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        # 去掉标题行本身，避免重复
        block = re.sub(r"^\s*\*\*" + re.escape(title) + r"\*\*\s*", "", block).strip()
        entry_marker = make_hidden_marker("page_522.md", title)
        entry_parts.append(entry_marker)
        entry_parts.append(f"### {title}")
        entry_parts.append(make_source_annotation("page_522.md", l3))
        entry_parts.append("")
        entry_parts.append(block)
        entry_parts.append("")

    section_block = "\n".join(entry_parts)
    safe_append_to_file(
        target_path,
        section_marker,
        "## 天界血脉 BoA 传世名作",
        make_source_annotation("page_522.md", l3),
        section_block,
    )
    for _, title in starts:
        report["merged"].append({"type": "吟游诗人传世名作", "name": title, "target": str(target_path.relative_to(ORG_DIR))})


# ========== 2. 神裔能力变体 ==========

def process_variant_abilities(report: dict) -> None:
    src_path = SRC_DIR / "page_827.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text).strip()

    target_path = ORG_DIR / "种族" / "常见种族" / "神裔" / "神裔种族特性替换汇总.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 神裔种族特性替换汇总\n\n", "\n")

    marker = make_hidden_marker("page_827.md", "神裔能力变体")
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("神裔能力变体已存在")
        return

    heading = "## 神裔能力变体（Variant Aasimar Abilities）"
    l3 = "种族替换特性"
    safe_append_to_file(target_path, marker, heading, make_source_annotation("page_827.md", l3), text)
    report["merged"].append({"type": "神裔能力变体", "name": heading.lstrip("# ").split("（")[0], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 3. 神裔亚种 ==========

def process_heritages(report: dict) -> None:
    src_path = SRC_DIR / "page_828.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text).strip()

    target_path = ORG_DIR / "种族" / "常见种族" / "神裔" / "神裔种族特性替换汇总.md"
    if not target_path.exists():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        write_text_preserve(target_path, "# 神裔种族特性替换汇总\n\n", "\n")

    marker = make_hidden_marker("page_828.md", "神裔亚种")
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("神裔亚种已存在")
        return

    heading = "## 神裔亚种（Aasimar Heritages）"
    l3 = "种族替换特性"
    safe_append_to_file(target_path, marker, heading, make_source_annotation("page_828.md", l3), text)
    report["merged"].append({"type": "神裔亚种", "name": heading.lstrip("# ").split("（")[0], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 4. 天界专长 ==========

FEATS = [
    {"cn": "神使援护", "en": "Archon Diversion", "type": "（战斗专长）"},
    {"cn": "神使正义", "en": "Archon Justice", "type": "（战斗专长）"},
    {"cn": "神使之型", "en": "Archon Style", "type": "（战斗专长，流派专长）"},
    {"cn": "放逐重击", "en": "Banishing Critical", "type": "（战斗专长，重击专长）"},
    {"cn": "炫目光辉", "en": "Blinding Light", "type": ""},
    {"cn": "法术祝圣", "en": "Consecrate Spell", "type": "（超魔专长）"},
    {"cn": "内在之光", "en": "Inner Light", "type": ""},
    {"cn": "尊贵向导", "en": "Revered Guidance", "type": ""},
    {"cn": "阳光打击", "en": "Sunlit Strike", "type": ""},
    {"cn": "圣餐", "en": "Supernal Feast", "type": ""},
]


def find_feat_starts(text: str) -> list[tuple[int, dict]]:
    """以中文专长名为锚点定位条目起点；排除先决条件等内文引用。"""
    starts = []
    for feat in FEATS:
        # 标题起点：位于行首或句末标点（。）之后，后接可选中文类型括号
        pattern = re.compile(
            r"(?:^|(?<=[。\n\r]))\s*" + re.escape(feat["cn"]) + r"(?:（[^）]+）)?",
        )
        m = pattern.search(text)
        if not m:
            raise ValueError(f"无法在 page_829.md 中定位专长：{feat['cn']}")
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
    src_path = SRC_DIR / "page_829.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "专长" / "天界血脉BoA_专长.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 天界血脉 BoA 专长\n\n", "\n")

    starts = find_feat_starts(text)
    l3 = "专长"
    for idx, (start_pos, feat) in enumerate(starts):
        marker = make_hidden_marker("page_829.md", feat["cn"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"专长已存在: {feat['cn']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        block = strip_feat_title(block, feat)
        title_full = f"{feat['cn']}{feat.get('type', '')} {feat['en']}"
        heading = f"## {title_full}".strip()
        safe_append_to_file(target_path, marker, heading, make_source_annotation("page_829.md", l3), block)
        report["merged"].append({"type": "专长", "name": feat["cn"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 5. 神裔种族背景特性 ==========

TRAITS = [
    {"cn": "漂泊", "en": "Adrift"},
    {"cn": "神职人员", "en": "Clergy Member"},
    {"cn": "道德领袖", "en": "Ethical Leader"},
    {"cn": "行医人", "en": "Faith Healer"},
    {"cn": "无辜之人", "en": "Innocent"},
    {"cn": "异界交涉人", "en": "Planar Negotiator"},
    {"cn": "选择性体质", "en": "Selective Health"},
    {"cn": "我恨蛇", "en": "Snake Hater"},
    {"cn": "谨慎", "en": "Wary"},
]


def find_trait_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for trait in TRAITS:
        pattern = re.compile(r"(?:^|(?<=[。\n\r]))\s*\*\*" + re.escape(trait["cn"]))
        m = pattern.search(text)
        if not m:
            raise ValueError(f"无法在 page_830.md 中定位背景特性：{trait['cn']}（{trait['en']}）")
        starts.append((m.start(), trait))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_trait_title(block: str, trait: dict) -> str:
    # 背景特性标题被 ** 包裹，可能附带种族限定说明，最后以 **： 结束
    pattern = re.compile(r"^\s*\*\*[^*]+?\*\*\s*：?\s*", re.DOTALL)
    m = pattern.search(block)
    if m:
        return block[m.end():].strip()
    return block


def process_race_traits(report: dict) -> None:
    src_path = SRC_DIR / "page_830.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "背景特性" / "天界血脉BoA_背景特性.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 天界血脉 BoA 背景特性\n\n", "\n")

    starts = find_trait_starts(text)
    l3 = "背景特性"
    for idx, (start_pos, trait) in enumerate(starts):
        marker = make_hidden_marker("page_830.md", trait["cn"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"背景特性已存在: {trait['cn']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        # 最后一条背景特性后紧跟随机神裔特征表，需截断
        if "**随机神裔特征" in block:
            block = block[: block.index("**随机神裔特征")]
        block = strip_trailing_artifacts(block)
        block = strip_trait_title(block, trait)
        heading = f"## {trait['cn']}（{trait['en']}）"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("page_830.md", l3), block)
        report["merged"].append({"type": "背景特性", "name": trait["cn"], "target": str(target_path.relative_to(ORG_DIR))})

    report["skipped"].append("page_830.md 随机神裔特征表为纯风味随机表，未合并")


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
