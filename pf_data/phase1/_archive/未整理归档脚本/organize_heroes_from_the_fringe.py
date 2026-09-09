#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 缘界英雄（Heroes from the Fringe）内容到已有分类目录。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/缘界英雄Heroes from the Fringe"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "HeroesFromTheFringe_reorganization_report.md"

SOURCE_BOOK = "缘界英雄（Heroes from the Fringe）"
SOURCE_BOOK_SHORT = "缘界英雄HftF"


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
        or lines[-1].strip() == "---"
    ):
        lines.pop()
    return "\n".join(lines)


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


def _normalize_stars(text: str) -> str:
    text = re.sub(
        r"\*\*([^*]+?)\*\*\s*[（(]\s*\*([^*]+?)\*\s*[）)]",
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


def split_at_heading(text: str, pattern: str) -> tuple[str, str] | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return text[: match.start()].strip(), text[match.start():].strip()


CLASS_PATHS = {
    "page_1611.md": ("职业/混合职业/血脉狂怒者", "血脉狂怒者", "血脉狂怒者"),
    "操念使1.md": ("职业/异能冒险（Occult Adventures）/操念使", "操念使", "操念使"),
    "法师1.md": ("职业/核心职业/法师", "法师", "法师"),
    "唤魂师魅影.md": ("职业/异能冒险（Occult Adventures）/唤魂师", "唤魂师", "唤魂师"),
    "忍者2.md": ("职业/基础职业/忍者", "忍者", "忍者"),
    "萨满巫术.md": ("职业/混合职业/萨满", "萨满", "萨满"),
    "异能者1.md": ("职业/异能冒险（Occult Adventures）/异能者", "异能者", "异能者"),
    "吟游诗人2.md": ("职业/混合职业/歌者", "歌者", "歌者"),
    "战斗祭司.md": ("职业/混合职业/战斗祭司", "战斗祭司", "战斗祭司"),
}


def process_class_option(
    report: dict,
    filename: str,
    class_name: str,
    rel_dir: str,
    class_key: str,
    entry_name: str,
    target_title: str,
    heading: str,
    block: str | None = None,
) -> None:
    if block is None:
        block = clean_aggregate((SRC_DIR / "职业选项" / filename).read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if not block:
        return
    process_aggregate(
        report,
        f"职业选项/{filename}",
        f"职业选项 → {class_name}",
        entry_name,
        ORG_DIR / rel_dir / f"{SOURCE_BOOK_SHORT}_{class_key}变体.md",
        target_title,
        heading,
        block=block,
    )


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 背景特性
    block = clean_aggregate((SRC_DIR / "背景特性46.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "背景特性46.md",
            "角色选项 → 背景特性",
            "background_traits",
            ORG_DIR / "角色" / "背景" / "缘界英雄HftF_背景特性.md",
            "缘界英雄HftF 背景特性",
            "## 缘界英雄HftF 背景特性",
            block=block,
        )

    # 2. 替换种族特性
    block = clean_aggregate((SRC_DIR / "替换种族特性2.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "替换种族特性2.md",
            "角色选项 → 种族特性",
            "racial_traits",
            ORG_DIR / "角色" / "种族" / "缘界英雄HftF_替换种族特性.md",
            "缘界英雄HftF 替换种族特性",
            "## 缘界英雄HftF 替换种族特性",
            block=block,
        )

    # 3. 专长
    block = clean_aggregate((SRC_DIR / "专长24.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "专长24.md",
            "角色选项 → 专长",
            "feats",
            ORG_DIR / "角色" / "专长" / "缘界英雄HftF_专长.md",
            "缘界英雄HftF 专长",
            "## 缘界英雄HftF 专长",
            block=block,
        )

    # 4. 矮人武器
    block = clean_aggregate((SRC_DIR / "矮人武器.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "矮人武器.md",
            "装备/武器",
            "weapons",
            ORG_DIR / "装备_魔法物品" / "缘界英雄HftF_武器.md",
            "缘界英雄HftF 矮人武器",
            "## 缘界英雄HftF 矮人武器",
            block=block,
        )

    # 5. 新防具
    block = clean_aggregate((SRC_DIR / "新防具1.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "新防具1.md",
            "装备/防具",
            "armor",
            ORG_DIR / "装备_魔法物品" / "缘界英雄HftF_防具.md",
            "缘界英雄HftF 投毒者小圆盾",
            "## 缘界英雄HftF 投毒者小圆盾",
            block=block,
        )

    # 6. 装备技法
    block = clean_aggregate((SRC_DIR / "装备技法.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "装备技法.md",
            "装备/物品",
            "equipment_technique",
            ORG_DIR / "装备_魔法物品" / "缘界英雄HftF_装备技法.md",
            "缘界英雄HftF 投石索技法",
            "## 缘界英雄HftF 投石索技法",
            block=block,
        )

    # 7. 魔法物品
    block = clean_aggregate((SRC_DIR / "魔法物品10.md").read_text(encoding="utf-8"))
    block = _normalize_stars(block)
    block = _collapse_blank_lines(block.strip())
    if block:
        process_aggregate(
            report,
            "魔法物品10.md",
            "装备/魔法物品",
            "magic_items",
            ORG_DIR / "装备_魔法物品" / "缘界英雄HftF_魔法物品.md",
            "缘界英雄HftF 魔法物品",
            "## 缘界英雄HftF 魔法物品",
            block=block,
        )

    # 8. page_1372：武士变体 + 鸣禽之道（武士道/骑士团）
    page_text = clean_aggregate((SRC_DIR / "职业选项" / "page_1372.md").read_text(encoding="utf-8"))
    split = split_at_heading(page_text, r"\n\*\*鸣禽之道")
    if split is None:
        report["warnings"].append("page_1372.md 未找到鸣禽之道分隔点，整段写入武士变体")
        warrior_block = page_text
        order_block = ""
    else:
        warrior_block, order_block = split

    warrior_block = _normalize_stars(warrior_block)
    warrior_block = _collapse_blank_lines(warrior_block.strip())
    if warrior_block:
        process_aggregate(
            report,
            "职业选项/page_1372.md",
            "职业选项 → 武士",
            "samurai_archetype",
            ORG_DIR / "职业" / "基础职业" / "武士" / "缘界英雄HftF_武士变体.md",
            "缘界英雄HftF 花间诗剑",
            "## 缘界英雄HftF 花间诗剑",
            block=warrior_block,
        )

    order_block = _normalize_stars(order_block)
    order_block = _collapse_blank_lines(order_block.strip())
    if order_block:
        process_aggregate(
            report,
            "职业选项/page_1372.md",
            "职业选项 → 武士",
            "samurai_order",
            ORG_DIR / "职业" / "基础职业" / "武士" / "缘界英雄HftF_武士道.md",
            "缘界英雄HftF 鸣禽之道",
            "## 缘界英雄HftF 鸣禽之道",
            block=order_block,
        )

    # 9. 其他职业选项
    for filename, (rel_dir, class_key, class_name) in CLASS_PATHS.items():
        process_class_option(
            report,
            filename,
            class_name,
            rel_dir,
            class_key,
            f"{class_key}_option",
            f"{SOURCE_BOOK_SHORT} {class_name}变体",
            f"## {SOURCE_BOOK_SHORT} {class_name}变体",
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
