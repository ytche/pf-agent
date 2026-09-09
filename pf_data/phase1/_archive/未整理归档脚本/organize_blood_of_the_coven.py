#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 巫团血脉（Blood of the Coven）BotC 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/巫团血脉BotC
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/巫团血脉BotC"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "BloodOfTheCoven_reorganization_report.md"

SOURCE_BOOK = "巫团血脉（Blood of the Coven）BotC"
SOURCE_BOOK_SHORT = "BotC"


# ========== 通用工具函数 ==========

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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 巫团血脉BotC{l3_part}"


def make_hidden_marker(source_file: str, entry_name: str) -> str:
    return f"<!-- {SOURCE_BOOK_SHORT}-source:{source_file}:{entry_name} -->"


def merge_crossline_bold(text: str) -> str:
    """合并因加粗标记跨行而断裂的标题行。"""
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
    """移除文件顶部的译者/整理者链接与空行。"""
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
    """移除文件顶部的图片引用。"""
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


def normalize_line(line: str) -> str:
    """将行首/行尾的星号、多余空白统一，便于标题匹配。"""
    return re.sub(r"\*+", "", line).strip()


def is_title_line(line: str, cn: str = "", en: str = "") -> bool:
    """判断一行是否为包含指定中文/英文名的标题行。

    只匹配行首出现的中文名或英文名（允许前置 【PFS】 等标签和加粗标记），
    避免把正文中出现的英文名当作标题。
    """
    s = line.strip()
    if not s:
        return False
    # 去掉行首的加粗标记
    s = re.sub(r"^\*+", "", s)
    # 去掉行首的 【PFS】等标签
    s = re.sub(r"^【[^】]+】\s*", "", s)
    if cn and re.match(r"^" + re.escape(cn) + r"\b", s):
        return True
    if not cn and en:
        if re.match(r"^" + re.escape(en) + r"\b", s):
            return True
        if re.match(r"^\(" + re.escape(en) + r"\)", s):
            return True
    return False


def is_source_or_artifact_line(line: str) -> bool:
    """判断是否为来源、页码、孤立标签等应跳过的行。"""
    s = line.strip()
    if not s:
        return True
    if s in ("**", "*"):
        return True
    if re.match(r"^\*+\s*$", s):
        return True
    if "出自" in s:
        return True
    if re.search(r"\b(?:pg|PG)\.", s):
        return True
    if re.search(r"第\s*\d+\s*页", s):
        return True
    if re.search(r"Blood of the Coven", s, re.IGNORECASE):
        return True
    if re.match(r"^\*?\*?\s*【PFS】\s*$", s):
        return True
    return False


def is_page_continuation(line: str) -> bool:
    """判断是否为跨行的页码/书名号结尾（如 '3》'、'13'）。"""
    s = line.strip()
    if re.match(r"^\d+\s*》\s*$", s):
        return True
    if re.match(r"^》\s*$", s):
        return True
    if re.match(r"^\d+\s*$", s):
        return True
    return False


def strip_block_header(block: str, cn: str = "", en: str = "") -> str:
    """移除条目块开头的标题行、来源行及孤立格式标记。"""
    lines = block.splitlines()
    i = 0

    # 跳过空行
    while i < len(lines) and lines[i].strip() == "":
        i += 1

    # 跳过标题行（可能跨多行或包含中文/英文名）
    if i < len(lines) and is_title_line(lines[i], cn, en):
        i += 1
        # 跳过标题残留的空行或星号行
        while i < len(lines) and (
            lines[i].strip() == "" or re.match(r"^[\s\*]+$", lines[i])
        ):
            i += 1

    # 跳过来源、页码、孤立标签及页码续行
    while i < len(lines) and (
        is_source_or_artifact_line(lines[i]) or is_page_continuation(lines[i])
    ):
        i += 1

    return "\n".join(lines[i:])


def merge_source_lines(text: str) -> str:
    """合并跨行的来源/页码标注行，便于统一剥除。"""
    lines = text.splitlines()
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*出自", line):
            buf = line.rstrip()
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if nxt == "":
                    break
                if buf.rstrip().endswith("页") or buf.rstrip().endswith("》"):
                    break
                buf += " " + nxt
                j += 1
            merged.append(buf)
            i = j
        else:
            merged.append(line)
            i += 1
    return "\n".join(merged)


def clean_part(text: str) -> str:
    """对一段文本进行统一的来源链接、图片、跨行加粗、跨行来源清理。"""
    text = text.replace("\r\n", "\n")
    text = clean_translator_url(text)
    text = clean_leading_image(text)
    text = merge_crossline_bold(text)
    text = merge_source_lines(text)
    return text


def read_and_clean(src_path: Path) -> str:
    text = src_path.read_text(encoding="utf-8")
    return clean_part(text)


# ========== 按条目列表拆分源文件 ==========

def find_entry_line_starts(
    lines: list[str], entries: list[dict], source_label: str = "条目"
) -> list[tuple[int, dict]]:
    """按行号定位每个条目的起始行。"""
    starts = []
    for entry in entries:
        cn = entry.get("cn", "")
        en = entry.get("en", "")
        found = None
        for i, line in enumerate(lines):
            if is_title_line(line, cn, en):
                found = i
                break
        if found is None:
            raise ValueError(f"无法在 {source_label} 中定位：{cn or en}")
        starts.append((found, entry))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_source_header(block: str) -> str:
    """移除块开头的空行、来源行、页码行及孤立格式标记（不依赖标题名）。"""
    lines = block.splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    while i < len(lines) and (
        is_source_or_artifact_line(lines[i]) or is_page_continuation(lines[i])
    ):
        i += 1
    return "\n".join(lines[i:])


def process_entry_list_file(
    report: dict,
    src_name: str,
    l3: str,
    entries: list[dict],
    target_path: Path,
    target_title: str,
    preamble_entry_name: str | None = None,
    preamble_heading: str | None = None,
) -> None:
    """将源文件中按条目拆分的多段内容写入目标聚合文件。"""
    text = read_and_clean(SRC_DIR / src_name)
    lines = text.splitlines()

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, f"# {target_title}\n\n", "\n")

    try:
        starts = find_entry_line_starts(lines, entries, src_name)
    except ValueError as e:
        report["warnings"].append(str(e))
        marker = make_hidden_marker(src_name, "__aggregate__")
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"{src_name} 聚合已存在")
            return
        block = strip_trailing_artifacts(text)
        safe_append_to_file(
            target_path,
            marker,
            f"## {target_title}",
            make_source_annotation(src_name, l3),
            block,
        )
        report["merged"].append({"type": l3, "name": f"{target_title}（聚合）", "target": str(target_path.relative_to(ORG_DIR))})
        return

    # 处理前言（第一个条目之前的介绍文字）
    if preamble_entry_name and preamble_heading:
        first_line = starts[0][0]
        preamble_lines = lines[:first_line]
        # 去掉末尾的空行或孤立标记
        while preamble_lines and preamble_lines[-1].strip() == "":
            preamble_lines.pop()
        if preamble_lines:
            preamble = "\n".join(preamble_lines)
            preamble_marker = make_hidden_marker(src_name, preamble_entry_name)
            if preamble_marker not in target_path.read_text(encoding="utf-8"):
                safe_append_to_file(
                    target_path,
                    preamble_marker,
                    preamble_heading,
                    make_source_annotation(src_name, l3),
                    strip_source_header(strip_trailing_artifacts(preamble)),
                )
                report["merged"].append({"type": l3, "name": preamble_heading.replace("## ", ""), "target": str(target_path.relative_to(ORG_DIR))})

    for idx, (line_idx, entry) in enumerate(starts):
        name = entry.get("cn") or entry.get("en")
        marker = make_hidden_marker(src_name, name)
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"{l3}已存在: {name}")
            continue
        end_line = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        block = "\n".join(lines[line_idx:end_line])
        block = strip_trailing_artifacts(block)
        block = strip_block_header(block, entry.get("cn", ""), entry.get("en", ""))
        cn = entry.get("cn", "")
        en = entry.get("en", "")
        if cn and en:
            heading = f"## {cn}（{en}）"
        elif cn:
            heading = f"## {cn}"
        else:
            heading = f"## {en}"
        safe_append_to_file(target_path, marker, heading, make_source_annotation(src_name, l3), block)
        report["merged"].append({"type": l3, "name": name, "target": str(target_path.relative_to(ORG_DIR))})


# ========== 1. 专长 ==========

FEATS = [
    {"cn": "魔宠连接", "en": "Familiar Link"},
    {"cn": "协同超魔", "en": "Metamagical Synergy"},
    {"cn": "战团之触", "en": "Coven-Touched"},
]


def process_feats(report: dict) -> None:
    process_entry_list_file(
        report,
        "专长37.md",
        "专长",
        FEATS,
        ORG_DIR / "专长" / "巫团血脉BotC_专长.md",
        "巫团血脉 BotC 专长",
        preamble_entry_name="__preamble__",
        preamble_heading="## 巫团血脉 BotC 战团专长",
    )


# ========== 2. 物品 ==========

def process_equipment(report: dict) -> None:
    src_path = SRC_DIR / "物品31.md"
    text = read_and_clean(src_path)

    target_path = ORG_DIR / "装备_魔法物品" / "巫团血脉BotC_物品.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 巫团血脉 BotC 物品\n\n", "\n")

    marker = make_hidden_marker("物品31.md", "__aggregate__")
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("装备聚合已存在: 物品31.md")
        return

    block = strip_trailing_artifacts(text)
    block = strip_block_header(block, "牺牲项圈", "Collar of Sacrifice")
    safe_append_to_file(
        target_path,
        marker,
        "## 牺牲项圈（Collar of Sacrifice）",
        make_source_annotation("物品31.md", "物品"),
        block,
    )
    report["merged"].append({"type": "装备/物品", "name": "牺牲项圈", "target": str(target_path.relative_to(ORG_DIR))})


# ========== 3. 背景特性 ==========

TRAITS = [
    {"cn": "织命女的赐福", "en": "Blessed of the Norns"},
    {"cn": "巫团咏", "en": "Coven Casting"},
    {"cn": "压制咒", "en": "Rebuke the Curse"},
]


def process_background_traits(report: dict) -> None:
    process_entry_list_file(
        report,
        "背景特性38.md",
        "背景特性",
        TRAITS,
        ORG_DIR / "背景特性" / "巫团血脉BotC_背景特性.md",
        "巫团血脉 BotC 背景特性",
    )


# ========== 4. 种族选项聚合 ==========

def process_aggregate(
    report: dict,
    src_name: str,
    l3: str,
    entry_name: str,
    target_path: Path,
    target_title: str,
    heading: str,
) -> None:
    text = read_and_clean(SRC_DIR / src_name)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, f"# {target_title}\n\n", "\n")

    marker = make_hidden_marker(src_name, entry_name)
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append(f"{l3}已存在: {src_name}")
        return

    block = strip_trailing_artifacts(text)
    safe_append_to_file(target_path, marker, heading, make_source_annotation(src_name, l3), block)
    report["merged"].append({"type": l3, "name": target_title, "target": str(target_path.relative_to(ORG_DIR))})


def process_changeling_options(report: dict) -> None:
    process_aggregate(
        report,
        "替换儿种族选项.md",
        "种族特性",
        "__aggregate__",
        ORG_DIR / "种族" / "巫团血脉BotC_替换儿种族选项.md",
        "巫团血脉 BotC 替换儿种族选项",
        "## 替换儿亚种（Changeling Subraces）",
    )


def process_replacement_traits(report: dict) -> None:
    process_aggregate(
        report,
        "替换种族特性3.md",
        "种族特性",
        "__aggregate__",
        ORG_DIR / "种族" / "巫团血脉BotC_替换种族特性.md",
        "巫团血脉 BotC 替换种族特性",
        "## 替换种族特性",
    )
    # 根目录已存在同名副本，是重复文件
    root_duplicate = ORG_DIR / "替换种族特性3.md"
    if root_duplicate.exists():
        report["warnings"].append(
            f"注意：{root_duplicate} 已存在为根目录副本，是重复文件，建议后续手动清理。"
        )


# ========== 5. 神秘仪式 ==========

def process_rituals(report: dict) -> None:
    process_aggregate(
        report,
        "神秘仪式2.md",
        "神秘仪式",
        "__aggregate__",
        ORG_DIR / "规则" / "巫团血脉BotC_神秘仪式.md",
        "巫团血脉 BotC 神秘仪式",
        "## 仪式魔法与女巫仪式",
    )


# ========== 6. 职业变体追加到既有页面 ==========

def append_single_archetype(
    report: dict,
    source_file: str,
    target_rel: Path,
    cn: str,
    en: str,
    l3: str,
    tag: str = "BotC",
) -> None:
    src_path = SRC_DIR / "变体_选项" / source_file
    text = read_and_clean(src_path)

    target_path = ORG_DIR / target_rel
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, f"# {target_path.stem}\n\n", "\n")

    marker = make_hidden_marker(f"变体_选项/{source_file}", cn)
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append(f"职业变体已存在: {cn}")
        return

    block = strip_trailing_artifacts(text)
    block = strip_block_header(block, cn, en)
    heading = f"## {cn}（{en}）【{tag}】"
    safe_append_to_file(
        target_path,
        marker,
        heading,
        make_source_annotation(f"变体_选项/{source_file}", l3),
        block,
    )
    report["merged"].append({"type": "职业变体", "name": cn, "target": str(target_path.relative_to(ORG_DIR))})


def append_multi_section(
    report: dict,
    source_file: str,
    target_rel: Path,
    sections: list[dict],
    l3_prefix: str,
    tag: str = "BotC",
) -> None:
    src_path = SRC_DIR / "变体_选项" / source_file
    text = read_and_clean(src_path)
    lines = text.splitlines()

    target_path = ORG_DIR / target_rel
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, f"# {target_path.stem}\n\n", "\n")

    starts = find_entry_line_starts(lines, sections, source_file)
    for idx, (line_idx, sec) in enumerate(starts):
        cn = sec.get("cn", "")
        en = sec.get("en", "")
        marker = make_hidden_marker(f"变体_选项/{source_file}", cn or en)
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"职业选项已存在: {cn or en}")
            continue
        end_line = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        block = "\n".join(lines[line_idx:end_line])
        block = strip_trailing_artifacts(block)
        block = strip_block_header(block, cn, en)
        if cn and en:
            heading = f"## {cn}（{en}）【{tag}】"
        elif cn:
            heading = f"## {cn}【{tag}】"
        else:
            heading = f"## {en}【{tag}】"
        l3 = sec.get("l3", l3_prefix)
        safe_append_to_file(
            target_path,
            marker,
            heading,
            make_source_annotation(f"变体_选项/{source_file}", l3),
            block,
        )
        report["merged"].append({"type": "职业变体" if "变体" in l3 else l3, "name": cn or en, "target": str(target_path.relative_to(ORG_DIR))})


def process_witch_variants(report: dict) -> None:
    sections = [
        {"cn": "鬼婆之缚", "en": "HagBound", "l3": "女巫变体"},
        {"cn": "腐朽者", "en": "Putrefactor", "l3": "女巫变体"},
        {"cn": "赐福者", "en": "VelleMancer", "l3": "女巫变体"},
        {"cn": "女巫庇护主主题", "en": "Witch Patron Themes", "l3": "女巫庇护主"},
    ]
    append_multi_section(
        report,
        "女巫.md",
        Path("职业/基础职业/女巫/page_70.md"),
        sections,
        "女巫变体",
    )


def process_cleric_variant(report: dict) -> None:
    append_single_archetype(
        report,
        "牧师.md",
        Path("职业/核心职业/牧师/page_41.md"),
        "三元教士",
        "Triadic Priest",
        "牧师变体",
    )


def process_kineticist_variant(report: dict) -> None:
    append_single_archetype(
        report,
        "操念使.md",
        Path("职业/异能冒险（Occult Adventures）/操念使/page_297.md"),
        "暗蚀操念使",
        "Arakineticist",
        "操念使变体",
    )


def process_investigator_variant(report: dict) -> None:
    append_single_archetype(
        report,
        "调查员1.md",
        Path("职业/混合职业/调查员/page_107.md"),
        "恶念收割者",
        "Malice Binder",
        "调查员变体",
    )


def process_slayer_variant(report: dict) -> None:
    append_single_archetype(
        report,
        "杀手.md",
        Path("职业/混合职业/杀手/page_117.md"),
        "战团克星",
        "Covenbane",
        "杀手变体",
    )


def process_bloodrager_variants(report: dict) -> None:
    text = read_and_clean(SRC_DIR / "变体_选项" / "血脉狂怒者血脉1.md")

    # 按 --- 分隔符拆分：前半为鬼婆撕裂者，后半为鬼婆血脉
    parts = re.split(r"\n\s*---+\s*\n", text)
    if len(parts) < 2:
        report["warnings"].append("血脉狂怒者血脉1.md 中未找到 --- 分隔符，尝试整个文件追加到 page_98.md")
        block = strip_trailing_artifacts(clean_part(text))
        target_path = ORG_DIR / "职业/混合职业/血脉狂怒者/page_98.md"
        marker = make_hidden_marker("变体_选项/血脉狂怒者血脉1.md", "鬼婆撕裂者")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not target_path.exists():
            write_text_preserve(target_path, f"# {target_path.stem}\n\n", "\n")
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append("职业变体已存在: 鬼婆撕裂者")
        else:
            safe_append_to_file(
                target_path,
                marker,
                "## 鬼婆撕裂者（Hag-Riven）【BotC】",
                make_source_annotation("变体_选项/血脉狂怒者血脉1.md", "血脉狂怒者变体"),
                block,
            )
            report["merged"].append({"type": "职业变体", "name": "鬼婆撕裂者", "target": str(target_path.relative_to(ORG_DIR))})
        return

    # 鬼婆撕裂者 -> page_98.md
    block_98 = strip_trailing_artifacts(clean_part(parts[0]))
    block_98 = strip_block_header(block_98, "鬼婆撕裂者", "Hag-Riven")
    target_path_98 = ORG_DIR / "职业/混合职业/血脉狂怒者/page_98.md"
    target_path_98.parent.mkdir(parents=True, exist_ok=True)
    if not target_path_98.exists():
        write_text_preserve(target_path_98, f"# {target_path_98.stem}\n\n", "\n")
    marker_98 = make_hidden_marker("变体_选项/血脉狂怒者血脉1.md", "鬼婆撕裂者")
    if marker_98 in target_path_98.read_text(encoding="utf-8"):
        report["skipped"].append("职业变体已存在: 鬼婆撕裂者")
    else:
        safe_append_to_file(
            target_path_98,
            marker_98,
            "## 鬼婆撕裂者（Hag-Riven）【血脉狂怒者变体】【BotC】",
            make_source_annotation("变体_选项/血脉狂怒者血脉1.md", "血脉狂怒者变体"),
            block_98,
        )
        report["merged"].append({"type": "职业变体", "name": "鬼婆撕裂者", "target": str(target_path_98.relative_to(ORG_DIR))})

    # 鬼婆血脉 -> page_99.md
    block_99 = strip_trailing_artifacts(clean_part(parts[1]))
    block_99 = strip_block_header(block_99, "鬼婆血脉", "Hag")
    target_path_99 = ORG_DIR / "职业/混合职业/血脉狂怒者/page_99.md"
    target_path_99.parent.mkdir(parents=True, exist_ok=True)
    if not target_path_99.exists():
        write_text_preserve(target_path_99, f"# {target_path_99.stem}\n\n", "\n")
    marker_99 = make_hidden_marker("变体_选项/血脉狂怒者血脉1.md", "鬼婆血脉")
    if marker_99 in target_path_99.read_text(encoding="utf-8"):
        report["skipped"].append("血脉已存在: 鬼婆血脉")
    else:
        safe_append_to_file(
            target_path_99,
            marker_99,
            "## 鬼婆血脉（Hag）【BotC】",
            make_source_annotation("变体_选项/血脉狂怒者血脉1.md", "血脉狂怒者血脉"),
            block_99,
        )
        report["merged"].append({"type": "血脉", "name": "鬼婆血脉", "target": str(target_path_99.relative_to(ORG_DIR))})


# ========== 报告与主流程 ==========

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
    process_feats(report)
    process_equipment(report)
    process_background_traits(report)
    process_changeling_options(report)
    process_replacement_traits(report)
    process_rituals(report)
    process_witch_variants(report)
    process_cleric_variant(report)
    process_kineticist_variant(report)
    process_investigator_variant(report)
    process_slayer_variant(report)
    process_bloodrager_variants(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
