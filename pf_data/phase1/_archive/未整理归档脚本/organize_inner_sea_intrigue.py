#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 内海诡道（Inner Sea Intrigue）ISI 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/内海诡道ISI
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/内海诡道ISI"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "InnerSeaIntrigue_reorganization_report.md"

SOURCE_BOOK = "内海诡道（Inner Sea Intrigue）ISI"
SOURCE_BOOK_SHORT = "ISI"


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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → {SOURCE_BOOK_SHORT}{l3_part}"


def make_hidden_marker(source_file: str, entry_name: str) -> str:
    return f"<!-- {SOURCE_BOOK_SHORT}-source:{source_file}:{entry_name} -->"


def remove_image_links(text: str) -> str:
    """移除 Markdown 图片链接标记（通常来自 AON 图标）。"""
    return re.sub(r"!\[.*?\]\(.*?\)", "", text)


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


def clean_aggregate(text: str) -> str:
    """对聚合文件进行最小清理。"""
    text = text.replace("\r\n", "\n")
    text = remove_image_links(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)
    return text


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


def split_archetypes(text: str) -> list[tuple[str, Path, str, str]]:
    """将 page_748.md 切分为各个职业变体块。

    返回 [(条目名, 目标路径, 聚合标题, 内容块), ...]
    """
    lines = text.splitlines()

    archetype_defs = [
        ("完美学者", ORG_DIR / "职业" / "核心职业" / "武僧" / "page_52.md", "完美学者（Perfect Scholar）【武僧变体】"),
        ("修补匠", ORG_DIR / "职业" / "基础职业" / "炼金术师" / "page_71.md", "修补匠（Tinkerer）【炼金术师变体】"),
        ("不朽守卫者", ORG_DIR / "职业" / "混合职业" / "调查员" / "page_72.md", "不朽守卫者（Guardian of Immortality）【调查员变体】"),
        ("灵宠干探", ORG_DIR / "职业" / "混合职业" / "调查员" / "page_72.md", "灵宠干探（Bonded Investigator）【调查员变体】"),
        ("仙城导师", ORG_DIR / "职业" / "核心职业" / "德鲁伊" / "page_37.md", "仙城导师（Nithveil Adept）【德鲁伊变体】"),
        ("冻影忍", ORG_DIR / "职业" / "基础职业" / "忍者" / "忍者职业变体.md", "冻影忍（Frozen Shadow）【忍者变体】"),
        ("虔心图书学者", ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "page_38.md", "虔心图书学者（Studious Librarian）【吟游诗人变体】"),
        ("皇家秘卫", ORG_DIR / "职业" / "基础职业" / "审判者" / "page_78.md", "皇家秘卫（Royal Accuser）【审判者变体】"),
        ("科莱什先知", ORG_DIR / "职业" / "基础职业" / "先知" / "page_88.md", "科莱什先知（Keleshite Prophet）【先知变体】"),
        ("挑衅者", ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "page_38.md", "挑衅者（Provocateur）【吟游诗人变体】"),
    ]

    # 查找每个变体标题出现的行号
    starts = []
    for i, line in enumerate(lines):
        for name, target, heading in archetype_defs:
            if name in line:
                # 确认是标题行：包含变体名且行首无缩进或为图片行
                stripped = line.strip()
                if stripped.startswith("!") or stripped.startswith("**") or re.match(rf"^\*?{re.escape(name)}", stripped):
                    starts.append((i, name, target, heading))
                    break

    # 按行号排序，去重（同一行不应匹配多个）
    starts.sort(key=lambda x: x[0])
    seen_names = set()
    unique_starts = []
    for item in starts:
        if item[1] not in seen_names:
            unique_starts.append(item)
            seen_names.add(item[1])

    blocks = []
    for idx, (start_line, name, target, heading) in enumerate(unique_starts):
        # 回溯包含前置的译者/来源链接与空行
        s = start_line
        while s > 0 and (
            lines[s - 1].strip() == ""
            or lines[s - 1].startswith("[http")
            or lines[s - 1].startswith("**[http")
            or re.match(r"^https?://", lines[s - 1].strip())
        ):
            s -= 1
        end_line = unique_starts[idx + 1][0] if idx + 1 < len(unique_starts) else len(lines)
        block = "\n".join(lines[s:end_line])
        blocks.append((name, target, heading, block))

    return blocks


def split_masked_persona(text: str) -> tuple[str, str]:
    """将 假面伪装.md 切分为规则部分与专长部分。"""
    lines = text.splitlines()
    split_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^\*\*可信伪装：", line.strip()):
            split_idx = i
            break
    if split_idx is None:
        return text, ""
    rules = "\n".join(lines[:split_idx])
    feats = "\n".join(lines[split_idx:])
    return rules, feats


def split_items(text: str) -> tuple[str, str, str]:
    """将 物品12.md 切分为炼金物品块与奇物块。

    炼金物品：醉蜂赐、胡蜂腑、解毒剂；奇物：显隐之雾烟斗。
    """
    lines = text.splitlines()
    item_patterns = [
        ("醉蜂赐", "alchemical"),
        ("显隐之雾烟斗", "wondrous"),
        ("胡蜂腑", "alchemical"),
        ("解毒剂", "alchemical"),
    ]

    starts = []
    for i, line in enumerate(lines):
        for name, kind in item_patterns:
            if name in line and (line.strip().startswith("[") or line.strip().startswith("!") or line.strip().startswith("**") or line.strip().startswith(name)):
                starts.append((i, name, kind))
                break
    starts.sort(key=lambda x: x[0])

    alchemical_blocks = []
    wondrous_blocks = []
    for idx, (start_line, name, kind) in enumerate(starts):
        end_line = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start_line:end_line])
        if kind == "alchemical":
            alchemical_blocks.append(block)
        else:
            wondrous_blocks.append(block)

    return "\n\n".join(alchemical_blocks), "\n\n".join(wondrous_blocks)


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

    # 1. 职业变体：page_748.md 切分后追加到对应职业页面
    page_748_text = clean_aggregate((SRC_DIR / "page_748.md").read_text(encoding="utf-8"))
    for name, target, heading, block in split_archetypes(page_748_text):
        if name == "冻影忍":
            # 忍者职业变体.md 中已存在冻影忍，跳过避免重复
            report["skipped"].append(f"职业变体：冻影忍已存在于 {target.relative_to(ORG_DIR)}，跳过")
            continue
        process_aggregate(
            report,
            "page_748.md",
            "职业变体",
            name,
            target,
            heading,
            f"## {heading}",
            block=block,
        )

    # 2. 假面伪装规则 + 专长
    masked_text = clean_aggregate((SRC_DIR / "假面伪装.md").read_text(encoding="utf-8"))
    rules_part, feats_part = split_masked_persona(masked_text)

    process_aggregate(
        report,
        "假面伪装.md",
        "规则",
        "masked_persona_rules",
        ORG_DIR / "规则" / "内海诡道ISI_假面伪装.md",
        "内海诡道 ISI 假面伪装",
        "## 内海诡道 ISI 假面伪装规则",
        block=rules_part,
    )
    process_aggregate(
        report,
        "假面伪装.md",
        "专长",
        "masked_persona_feats",
        ORG_DIR / "专长" / "内海诡道ISI_专长.md",
        "内海诡道 ISI 专长",
        "## 内海诡道 ISI 专长",
        block=feats_part,
    )

    # 3. 武器附魔
    process_aggregate(
        report,
        "武器附魔.md",
        "装备",
        "__aggregate__",
        ORG_DIR / "装备_魔法物品" / "武器附魔" / "内海诡道ISI_武器附魔.md",
        "内海诡道 ISI 武器附魔",
        "## 内海诡道 ISI 武器附魔",
    )

    # 4. 物品12.md 拆分
    item_text = clean_aggregate((SRC_DIR / "物品12.md").read_text(encoding="utf-8"))
    alchemical_block, wondrous_block = split_items(item_text)
    process_aggregate(
        report,
        "物品12.md",
        "装备",
        "alchemical_items",
        ORG_DIR / "装备_魔法物品" / "内海诡道ISI_炼金物品.md",
        "内海诡道 ISI 炼金物品",
        "## 内海诡道 ISI 炼金物品",
        block=alchemical_block,
    )
    process_aggregate(
        report,
        "物品12.md",
        "装备",
        "wondrous_item",
        ORG_DIR / "装备_魔法物品" / "内海诡道ISI_奇物.md",
        "内海诡道 ISI 奇物",
        "## 内海诡道 ISI 奇物",
        block=wondrous_block,
    )

    # 5. 专长55.md
    process_aggregate(
        report,
        "专长55.md",
        "专长",
        "__aggregate__",
        ORG_DIR / "专长" / "内海诡道ISI_专长.md",
        "内海诡道 ISI 专长",
        "## 内海诡道 ISI 专长",
    )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
