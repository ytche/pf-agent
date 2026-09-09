#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 塔尔多，荣光荡漾之地（Taldor, Echoes of Glory）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/塔尔多，荣光荡漾之地TEoG
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/塔尔多，荣光荡漾之地TEoG"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "TaldorEchoesOfGlory_reorganization_report.md"

SOURCE_BOOK = "塔尔多，荣光荡漾之地（Taldor, Echoes of Glory）"
SOURCE_BOOK_SHORT = "塔尔多TEoG"


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

def _split_by_stars(text: str) -> list[str]:
    """按 `****` 分隔符拆分文本为多个块。"""
    text = clean_aggregate(text)
    # 将独立的 `****` 行作为分隔符
    parts = re.split(r"\n\*\*\*+\s*\n", text)
    blocks: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 去掉块内残留的 `****` 行
        lines = [ln for ln in part.splitlines() if not re.match(r"^\s*\*\*\*+\s*$", ln)]
        block = "\n".join(lines).strip()
        if block:
            blocks.append(block)
    return blocks


def _extract_feat_heading(block: str) -> tuple[str, str]:
    """从专长块首行提取标题与正文。

    源文件常见格式：中文名 英文名中文描述（英文名与描述间无空格），
    例如：资深流民 Experienced Vagabond你作为一个流浪汉...
    少数英文名称跨行，如：城市觅食者 Urban\nforager你精于...
    """
    lines = block.splitlines()
    if not lines:
        return ("", block)
    first = lines[0].strip()
    # 若首行以英文单词结尾且次行以英文开头，则合并为同一标题行
    if (
        len(lines) > 1
        and re.search(r"[A-Za-z]$", first)
        and re.match(r"^[A-Za-z]", lines[1].strip())
    ):
        first = (first + " " + lines[1].strip()).strip()
        lines = [first] + lines[2:]
    # 中文名 + 空格 + 英文名 + 中文描述
    m = re.match(r"^([一-龥]+)\s+([A-Za-z][A-Za-z\s'’]*?)\s*([一-龥].*)$", first)
    if m:
        cn = m.group(1).strip()
        en = m.group(2).strip()
        title = f"## {cn}（{en}）"
        body = m.group(3).strip()
        return (title, body)
    # 回退：整行作为标题
    return (f"## {first}", "\n".join(lines[1:]).strip())


def split_feats(text: str) -> list[tuple[str, str]]:
    """拆分 page_936.md 中的专长。

    每个专长以中文名（可能包含或跟随英文名）开头，以 **** 分隔。
    """
    blocks = _split_by_stars(text)
    items: list[tuple[str, str]] = []
    for block in blocks:
        # 去掉末尾的注（不属于某个专长）
        if block.startswith("注："):
            continue
        title, body = _extract_feat_heading(block)
        if not title:
            continue
        # 规范字段标签
        body = re.sub(r"\*?\*?(先决条件|专长效果|效果)\*?\*?\s*[:：]", r"**\1**：", body)
        body = _collapse_blank_lines(body)
        items.append((title, f"{title}\n\n{body}"))
    return items


def clean_magic_items(text: str) -> str:
    """清理 page_937.md 中的魔法物品全文。

    该页物品种类繁杂、英文名称偶有跨行，直接整体聚合，保留内部条目结构。
    """
    text = clean_aggregate(text)
    text = _normalize_stars(text)
    text = re.sub(r"\n\*\*\*+\s*\n", "\n\n", text)
    text = _collapse_blank_lines(text.strip())
    return text


def clean_traits(text: str) -> str:
    """清理 page_938.md 中的背景特性全文。

    该页按地区/宗教/种族分节，直接整体聚合，保留内部小节结构。
    """
    text = clean_aggregate(text)
    text = _normalize_stars(text)
    text = re.sub(r"\n\*\*\*+\s*\n", "\n\n", text)
    text = _collapse_blank_lines(text.strip())
    return text


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 专长
    feat_items = split_feats((SRC_DIR / "page_936.md").read_text(encoding="utf-8"))
    if feat_items:
        process_aggregate(
            report,
            "page_936.md",
            "专长",
            "feats",
            ORG_DIR / "专长" / "塔尔多TEoG_专长.md",
            "塔尔多TEoG 专长",
            "## 塔尔多TEoG 专长",
            block="\n\n".join(block for _, block in feat_items),
        )

    # 2. 魔法物品
    magic_item_block = clean_magic_items((SRC_DIR / "page_937.md").read_text(encoding="utf-8"))
    if magic_item_block:
        process_aggregate(
            report,
            "page_937.md",
            "装备/物品 → 魔法物品",
            "magic_items",
            ORG_DIR / "装备_魔法物品" / "塔尔多TEoG_魔法物品.md",
            "塔尔多TEoG 魔法物品",
            "## 塔尔多TEoG 魔法物品",
            block=magic_item_block,
        )

    # 3. 背景特性
    trait_block = clean_traits((SRC_DIR / "page_938.md").read_text(encoding="utf-8"))
    if trait_block:
        process_aggregate(
            report,
            "page_938.md",
            "背景特性",
            "background_traits",
            ORG_DIR / "背景特性" / "塔尔多TEoG_背景特性.md",
            "塔尔多TEoG 背景特性",
            "## 塔尔多TEoG 背景特性",
            block=trait_block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
