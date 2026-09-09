#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 安多安，自由之魂（Andoran, Spirit of Liberty）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/安多安，自由之魂ASoL
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/安多安，自由之魂ASoL"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "AndoranSpiritOfLiberty_reorganization_report.md"

SOURCE_BOOK = "安多安，自由之魂（Andoran, Spirit of Liberty）"
SOURCE_BOOK_SHORT = "安多安ASoL"


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
    return re.sub(r"!\[.*?\]\(.*?\)", "", text)


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


def clean_aggregate(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = remove_image_links(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)
    return text


def strip_trailing_artifacts(block: str) -> str:
    lines = block.splitlines()
    while lines and (
        lines[-1].strip() == ""
        or re.match(r"^\*+$", lines[-1].strip())
        or re.match(r"^\|", lines[-1].strip())
        or re.match(r"^\|?\s*---", lines[-1].strip())
    ):
        lines.pop()
    return "\n".join(lines)


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


def _normalize_stars(text: str) -> str:
    """将标题中多余的星号对规范化为 **中文（English）**。"""
    text = re.sub(
        r"\*\*([^*]+?)\*\*\s*[（(]\s*\*\*([^*]+?)\*\*\s*[）)]",
        r"**\1（\2）**",
        text,
    )
    text = re.sub(
        r"\*\*([^*（）()]+?)\s*[（(]([^）()]+)[）)]\*\*",
        r"**\1（\2）**",
        text,
    )
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


# ---------------------------------------------------------------------------
# 条目拆分
# ---------------------------------------------------------------------------

def _split_by_blank_paragraphs(text: str) -> list[str]:
    """按两个以上空行拆分文本为多个块。"""
    text = clean_aggregate(text)
    parts = re.split(r"\n\s*\n\s*\n", text)
    blocks: list[str] = []
    for part in parts:
        part = part.strip()
        if part:
            blocks.append(part)
    return blocks


def _extract_trait_heading(block: str) -> tuple[str, str]:
    """从背景特性块提取 中文名（English Name） 标题与正文。"""
    lines = block.splitlines()
    if not lines:
        return ("", block)

    # 收集标题行，直到遇到来源/类型/需求等字段行
    title_lines: list[str] = []
    body_start = 0
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if not stripped:
            continue
        if stripped.startswith(("出自", "类型", "需求", "要求", "效果", "分类")):
            body_start = i
            break
        title_lines.append(stripped)
        body_start = i + 1

    title_raw = " ".join(title_lines)
    # 去掉首尾的 **
    title_raw = re.sub(r"^\*\*|\*\*$", "", title_raw).strip()
    # 尝试分离中文与英文
    m = re.match(r"^(.+?)\s*[（(]([^）()]+)[）)]$", title_raw)
    if m:
        title = f"## {m.group(1).strip()}（{m.group(2).strip()}）"
    else:
        title = f"## {title_raw}"

    body = "\n".join(lines[body_start:]).strip()
    return (title, body)


def split_traits(text: str) -> list[tuple[str, str]]:
    """拆分 背景特性35.md 中的背景特性。

    每个特性以 **中文名（English Name）** 开头，块间以两个以上空行分隔。
    """
    text = clean_aggregate(text)
    text = _normalize_stars(text)
    blocks = _split_by_blank_paragraphs(text)
    items: list[tuple[str, str]] = []
    for block in blocks:
        title, body = _extract_trait_heading(block)
        if not title:
            continue
        # 规范字段标签
        body = re.sub(r"\*?\*?(类型|需求|要求|效果|分类)\*?\*?\s*[:：]", r"**\1**：", body)
        body = _collapse_blank_lines(body)
        items.append((title, f"{title}\n\n{body}"))
    return items


def clean_magic_items(text: str) -> str:
    """清理 魔法物品7.md 中的魔法物品全文。"""
    text = clean_aggregate(text)
    text = _normalize_stars(text)
    text = _collapse_blank_lines(text.strip())
    return text


def clean_feat(text: str) -> str:
    """清理 专长43.md 中的伟业全文。"""
    text = clean_aggregate(text)
    text = _normalize_stars(text)
    text = _collapse_blank_lines(text.strip())
    return text


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 背景特性
    trait_items = split_traits((SRC_DIR / "背景特性35.md").read_text(encoding="utf-8"))
    if trait_items:
        process_aggregate(
            report,
            "背景特性35.md",
            "背景特性",
            "background_traits",
            ORG_DIR / "背景特性" / "安多安ASoL_背景特性.md",
            "安多安ASoL 背景特性",
            "## 安多安ASoL 背景特性",
            block="\n\n".join(block for _, block in trait_items),
        )

    # 2. 魔法物品
    magic_item_block = clean_magic_items((SRC_DIR / "魔法物品7.md").read_text(encoding="utf-8"))
    if magic_item_block:
        process_aggregate(
            report,
            "魔法物品7.md",
            "装备/物品 → 魔法物品",
            "magic_items",
            ORG_DIR / "装备_魔法物品" / "安多安ASoL_魔法物品.md",
            "安多安ASoL 魔法物品",
            "## 安多安ASoL 魔法物品",
            block=magic_item_block,
        )

    # 3. 专长（伟业）
    feat_block = clean_feat((SRC_DIR / "专长43.md").read_text(encoding="utf-8"))
    if feat_block:
        process_aggregate(
            report,
            "专长43.md",
            "专长",
            "feats",
            ORG_DIR / "专长" / "安多安ASoL_专长.md",
            "安多安ASoL 专长",
            "## 安多安ASoL 专长",
            block=feat_block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
