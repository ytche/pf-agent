#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 平衡勇士（Champions of Balance）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/平衡勇士
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/平衡勇士"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "ChampionsOfBalance_reorganization_report.md"

SOURCE_BOOK = "平衡勇士（Champions of Balance）"
SOURCE_BOOK_SHORT = "平衡勇士"


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


def split_page_565(text: str) -> tuple[str, str]:
    """将 page_565.md 切分为狂暴之力块与忍术块。"""
    parts = text.split("**忍术******")
    if len(parts) != 2:
        raise ValueError("page_565.md 中未找到'忍术'分隔")
    rage_block = parts[0].replace("**狂暴之力******", "").strip()
    ninja_block = parts[1].strip()
    return rage_block, ninja_block


def split_variants_file(text: str) -> list[tuple[str, str]]:
    """将 变体3.md 按 '吟游诗人变体：' / '德鲁伊变体：' 切分。

    返回 [(清理后的标题, 内容块), ...]
    """
    sections = []
    # 标题后的 ** 可能换行，使用 DOTALL 匹配到下一个 **
    bard_match = re.search(r"\*\*吟游诗人变体[:：](.+?)\*\*", text, re.DOTALL)
    druid_match = re.search(r"\*\*德鲁伊变体[:：](.+?)\*\*", text, re.DOTALL)
    if not bard_match or not druid_match:
        raise ValueError("变体3.md 中未找到预期的职业变体标题")

    bard_start = bard_match.start()
    druid_start = druid_match.start()
    bard_block = text[bard_start:druid_start].strip()
    druid_block = text[druid_start:].strip()

    bard_title = re.sub(r"\s+", " ", bard_match.group(1).strip())
    druid_title = re.sub(r"\s+", " ", druid_match.group(1).strip())
    sections.append((bard_title, bard_block))
    sections.append((druid_title, druid_block))
    return sections


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

    # page_565.md 狂暴之力 + 忍术
    page_565_text = clean_aggregate((SRC_DIR / "page_565.md").read_text(encoding="utf-8"))
    rage_block, ninja_block = split_page_565(page_565_text)

    process_aggregate(
        report,
        "page_565.md",
        "职业选项",
        "rage_powers",
        ORG_DIR / "职业" / "核心职业" / "野蛮人" / "格拉里昂的平衡勇士_狂暴之力.md",
        "格拉里昂的平衡勇士 狂暴之力",
        "## 格拉里昂的平衡勇士 狂暴之力",
        block=rage_block,
    )

    process_aggregate(
        report,
        "page_565.md",
        "职业选项",
        "ninja_tricks",
        ORG_DIR / "职业" / "基础职业" / "忍者" / "格拉里昂的平衡勇士_忍术.md",
        "格拉里昂的平衡勇士 忍术",
        "## 格拉里昂的平衡勇士 忍术",
        block=ninja_block,
    )

    # 背景特性
    process_aggregate(
        report,
        "背景特性40.md",
        "背景特性",
        "__aggregate__",
        ORG_DIR / "背景特性" / "格拉里昂的平衡勇士_种族背景特性.md",
        "格拉里昂的平衡勇士 种族背景特性",
        "## 格拉里昂的平衡勇士 种族背景特性",
    )

    # 变体3.md
    variants_text = clean_aggregate((SRC_DIR / "变体3.md").read_text(encoding="utf-8"))
    variant_targets = {
        "谈判者 Negotiator": (
            ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "page_38.md",
            "吟游诗人 谈判者",
            "## 格拉里昂的平衡勇士 吟游诗人谈判者（Negotiator）",
        ),
        "幸存者 Survivor": (
            ORG_DIR / "职业" / "核心职业" / "德鲁伊" / "page_45.md",
            "德鲁伊 幸存者",
            "## 格拉里昂的平衡勇士 德鲁伊幸存者（Survivor）",
        ),
    }
    for title, block in split_variants_file(variants_text):
        target_info = variant_targets.get(title)
        if not target_info:
            report["warnings"].append(f"变体3.md 中未识别的职业变体节：{title}")
            continue
        target_path, target_title, heading = target_info
        safe_title = title.replace(" ", "_").replace("/", "_")
        process_aggregate(
            report,
            "变体3.md",
            "职业变体",
            safe_title,
            target_path,
            target_title,
            heading,
            block=block,
        )

    # 均衡密使 进阶职业
    process_aggregate(
        report,
        "均衡密使.md",
        "进阶职业",
        "__aggregate__",
        ORG_DIR / "职业" / "进阶职业" / "格拉里昂的平衡勇士_均衡密使.md",
        "格拉里昂的平衡勇士 均衡密使",
        "## 格拉里昂的平衡勇士 均衡密使",
    )

    # 炼金术师科研发现
    process_aggregate(
        report,
        "炼金术师科研发现.md",
        "职业选项",
        "__aggregate__",
        ORG_DIR / "职业" / "基础职业" / "炼金术师" / "格拉里昂的平衡勇士_科研发现.md",
        "格拉里昂的平衡勇士 炼金科研发现",
        "## 格拉里昂的平衡勇士 炼金科研发现",
    )

    # 牧师子域
    process_aggregate(
        report,
        "牧师子域3.md",
        "职业选项",
        "__aggregate__",
        ORG_DIR / "职业" / "核心职业" / "牧师" / "格拉里昂的平衡勇士_牧师子域.md",
        "格拉里昂的平衡勇士 牧师子域",
        "## 格拉里昂的平衡勇士 牧师子域",
    )

    # 奇物
    process_aggregate(
        report,
        "奇物1.md",
        "装备",
        "__aggregate__",
        ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "格拉里昂的平衡勇士_奇物.md",
        "格拉里昂的平衡勇士 奇物",
        "## 格拉里昂的平衡勇士 奇物",
    )

    # 术士血统
    process_aggregate(
        report,
        "术士血统2.md",
        "职业选项",
        "__aggregate__",
        ORG_DIR / "职业" / "核心职业" / "术士" / "格拉里昂的平衡勇士_术士血统.md",
        "格拉里昂的平衡勇士 术士血统",
        "## 格拉里昂的平衡勇士 术士血统",
    )

    # 特殊魔法武器
    process_aggregate(
        report,
        "特殊魔法武器.md",
        "装备",
        "__aggregate__",
        ORG_DIR / "装备_魔法物品" / "魔法物品" / "魔法武器防具" / "格拉里昂的平衡勇士_特殊魔法武器.md",
        "格拉里昂的平衡勇士 特殊魔法武器",
        "## 格拉里昂的平衡勇士 特殊魔法武器",
    )

    # 专长
    process_aggregate(
        report,
        "专长33.md",
        "专长",
        "__aggregate__",
        ORG_DIR / "专长" / "格拉里昂的平衡勇士_专长.md",
        "格拉里昂的平衡勇士 专长",
        "## 格拉里昂的平衡勇士 专长",
    )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
