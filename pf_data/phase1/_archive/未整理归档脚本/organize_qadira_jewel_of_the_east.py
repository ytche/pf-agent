#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 卡蒂亚，东方明珠（Qadira, Jewel of the East）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/卡蒂亚，东方明珠QJotE
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/卡蒂亚，东方明珠QJotE"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "QadiraJewelOfTheEast_reorganization_report.md"

SOURCE_BOOK = "卡蒂亚，东方明珠（Qadira, Jewel of the East）"
SOURCE_BOOK_SHORT = "卡蒂亚QJotE"


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
    title_raw = re.sub(r"^\*\*|\*\*$", "", title_raw).strip()
    m = re.match(r"^(.+?)\s*[（(]([^）()]+)[）)]$", title_raw)
    if m:
        title = f"## {m.group(1).strip()}（{m.group(2).strip()}）"
    else:
        title = f"## {title_raw}"

    body = "\n".join(lines[body_start:]).strip()
    return (title, body)


def split_traits(text: str) -> list[tuple[str, str]]:
    """拆分 背景特性48.md 中的背景特性。"""
    text = clean_aggregate(text)
    text = _normalize_stars(text)
    blocks = _split_by_blank_paragraphs(text)
    items: list[tuple[str, str]] = []
    for block in blocks:
        title, body = _extract_trait_heading(block)
        if not title:
            continue
        body = re.sub(r"\*?\*?(类型|需求|要求|效果|分类)\*?\*?\s*[:：]", r"**\1**：", body)
        body = _collapse_blank_lines(body)
        items.append((title, f"{title}\n\n{body}"))
    return items


def _extract_archetype_info(block: str) -> tuple[str, str, str] | None:
    """从职业变体块提取（职业, 标题, 正文）。

    通过标题中的"（XX变体）"或"【XX变体】"判断职业；若无明确标记，则通过正文关键词推断。
    """
    lines = block.splitlines()
    # 去掉块首的 URL/译者行与空行
    while lines and (
        lines[0].strip().startswith("[http")
        or lines[0].strip().startswith("http")
        or lines[0].strip().startswith("译者")
        or lines[0].strip() == ""
    ):
        lines = lines[1:]
    if not lines:
        return None

    # 收集标题行（直到遇到能力行、来源行或斜体引述行）
    title_lines: list[str] = []
    body_start = 0
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if not stripped:
            continue
        # 能力行：加粗中文名（English）后接冒号；来源行/引述行也停止
        if (
            re.match(r"^\*\*.+?\（[^）]+\）\*\*\s*[:：]", stripped)
            or stripped.startswith("出自")
            or stripped.startswith("**出自")
            or re.match(r"^\*[^*]+\*$", stripped)
        ):
            body_start = i
            break
        title_lines.append(stripped)
        body_start = i + 1

    title_raw = " ".join(title_lines)
    title_raw = re.sub(r"^\*\*|\*\*$", "", title_raw).strip()

    # 判断职业：先判断战吟者，再吟游诗人，再女巫，避免"吟游表演"等关键词误匹配
    cls = ""
    if re.search(r"[（【]女巫变体[）】]", title_raw) or ("女巫" in title_raw and "魔宠" in block):
        cls = "女巫"
    if "战怒之歌" in block or "进行军乐" in block or "汲借秘术" in block:
        cls = "战吟者"
    elif re.search(r"[（【]吟游诗人变体[）】]", title_raw) or "吟游表演" in block:
        cls = "吟游诗人"

    if not cls:
        return None

    # 标题去掉职业变体标记
    title_clean = re.sub(r"[（【]\s*[^）】]*?变体\s*[）】]", "", title_raw).strip()
    # 尝试保留 English Name
    m = re.match(r"^(.+?)\s*[（(]([^）()]+)[）)]$", title_clean)
    if m:
        title = f"## {m.group(1).strip()}（{m.group(2).strip()}）"
    else:
        title = f"## {title_clean}"

    body = "\n".join(lines[body_start:]).strip()
    body = _collapse_blank_lines(body)
    return (cls, title, f"{title}\n\n{body}")


def split_archetypes(text: str, report: dict) -> dict[str, list[tuple[str, str]]]:
    """拆分 职业变体1.md 为各职业变体块。

    返回 {职业: [(标题, 正文), ...]}。
    """
    text = clean_aggregate(text)
    text = _normalize_stars(text)
    # 按 --- 分隔符或两个以上空行切分
    parts = re.split(r"\n\s*---\s*\n", text)
    result: dict[str, list[tuple[str, str]]] = {}
    for part in parts:
        part = part.strip()
        if not part:
            continue
        info = _extract_archetype_info(part)
        if not info:
            report["warnings"].append(f"无法识别职业变体块: {part[:60]}...")
            continue
        cls, title, body = info
        result.setdefault(cls, []).append((title, body))
    return result


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 背景特性
    trait_items = split_traits((SRC_DIR / "背景特性48.md").read_text(encoding="utf-8"))
    if trait_items:
        process_aggregate(
            report,
            "背景特性48.md",
            "背景特性",
            "background_traits",
            ORG_DIR / "背景特性" / "卡蒂亚QJotE_背景特性.md",
            "卡蒂亚QJotE 背景特性",
            "## 卡蒂亚QJotE 背景特性",
            block="\n\n".join(block for _, block in trait_items),
        )

    # 2. 动物伙伴（沙漠骏马）
    companion_block = clean_aggregate((SRC_DIR / "动物伙伴_坐骑1.md").read_text(encoding="utf-8"))
    companion_block = _collapse_blank_lines(companion_block.strip())
    if companion_block:
        process_aggregate(
            report,
            "动物伙伴_坐骑1.md",
            "规则 → 动物伙伴",
            "shissah",
            ORG_DIR / "规则" / "卡蒂亚QJotE_新动物伙伴.md",
            "卡蒂亚QJotE 新动物伙伴",
            "## 卡蒂亚QJotE 新动物伙伴",
            block=companion_block,
        )

    # 3. 马匹技巧
    trick_block = clean_aggregate((SRC_DIR / "马匹技巧1.md").read_text(encoding="utf-8"))
    trick_block = _collapse_blank_lines(trick_block.strip())
    if trick_block:
        process_aggregate(
            report,
            "马匹技巧1.md",
            "规则 → 动物技巧",
            "horse_tricks",
            ORG_DIR / "规则" / "卡蒂亚QJotE_马匹技巧.md",
            "卡蒂亚QJotE 马匹技巧",
            "## 卡蒂亚QJotE 马匹技巧",
            block=trick_block,
        )

    # 4. 术士血统
    bloodline_block = clean_aggregate((SRC_DIR / "术士血统4.md").read_text(encoding="utf-8"))
    bloodline_block = _normalize_stars(bloodline_block)
    bloodline_block = _collapse_blank_lines(bloodline_block.strip())
    if bloodline_block:
        process_aggregate(
            report,
            "术士血统4.md",
            "职业选项 → 术士",
            "solar_bloodline",
            ORG_DIR / "职业" / "核心职业" / "术士" / "卡蒂亚QJotE_术士血统.md",
            "卡蒂亚QJotE 术士血统",
            "## 卡蒂亚QJotE 术士血统",
            block=bloodline_block,
        )

    # 5. 特殊材料
    material_block = clean_aggregate((SRC_DIR / "特殊材料4.md").read_text(encoding="utf-8"))
    material_block = _collapse_blank_lines(material_block.strip())
    if material_block:
        process_aggregate(
            report,
            "特殊材料4.md",
            "装备/物品 → 特殊材料",
            "sunsilk",
            ORG_DIR / "装备_魔法物品" / "特殊材料" / "卡蒂亚QJotE_特殊材料.md",
            "卡蒂亚QJotE 特殊材料",
            "## 卡蒂亚QJotE 特殊材料",
            block=material_block,
        )

    # 6. 职业变体
    archetype_map = {
        "女巫": (ORG_DIR / "职业" / "基础职业" / "女巫" / "卡蒂亚QJotE_女巫变体.md", "卡蒂亚QJotE 女巫变体"),
        "吟游诗人": (ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "卡蒂亚QJotE_吟游诗人变体.md", "卡蒂亚QJotE 吟游诗人变体"),
        "战吟者": (ORG_DIR / "职业" / "基础职业" / "战吟者" / "卡蒂亚QJotE_战吟者变体.md", "卡蒂亚QJotE 战吟者变体"),
    }
    archetypes = split_archetypes((SRC_DIR / "职业变体1.md").read_text(encoding="utf-8"), report)
    for cls, items in archetypes.items():
        if cls not in archetype_map:
            report["warnings"].append(f"未配置目标路径: {cls}")
            continue
        target_path, target_title = archetype_map[cls]
        entry_name = f"archetype_{cls}"
        process_aggregate(
            report,
            "职业变体1.md",
            f"职业选项 → {cls}",
            entry_name,
            target_path,
            target_title,
            f"## {target_title}",
            block="\n\n".join(block for _, block in items),
        )

    # 7. 专长
    feat_block = clean_aggregate((SRC_DIR / "专长39.md").read_text(encoding="utf-8"))
    feat_block = _normalize_stars(feat_block)
    feat_block = re.sub(r"\*?\*(先决条件|专长效果)\*?\*\s*[:：]", r"**\1**：", feat_block)
    feat_block = _collapse_blank_lines(feat_block.strip())
    if feat_block:
        process_aggregate(
            report,
            "专长39.md",
            "专长",
            "genie_touched_companion",
            ORG_DIR / "专长" / "卡蒂亚QJotE_专长.md",
            "卡蒂亚QJotE 专长",
            "## 卡蒂亚QJotE 专长",
            block=feat_block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
