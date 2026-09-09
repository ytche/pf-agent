#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 传奇编年史（Chronicle of Legends）内容到已有分类目录。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/传奇编年史CoL"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "ChronicleOfLegends_reorganization_report.md"

SOURCE_BOOK = "传奇编年史（Chronicle of Legends）"
SOURCE_BOOK_SHORT = "传奇编年史CoL"


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


def normalize_block(block: str) -> str:
    block = _normalize_stars(block)
    return _collapse_blank_lines(block.strip())


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


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. page_1498.md：珍品编年史 → 魔法物品套装 + 收藏者之恩惠专长
    page_text = clean_aggregate((SRC_DIR / "page_1498.md").read_text(encoding="utf-8"))
    split = split_at_heading(page_text, r"\n\s*收藏者之恩惠")
    if split is None:
        report["warnings"].append("page_1498.md 未找到收藏者之恩惠分隔点，整段写入魔法物品套装")
        item_block = page_text
        feat_block = ""
    else:
        item_block, feat_block = split

    item_block = normalize_block(item_block)
    if item_block:
        process_aggregate(
            report,
            "page_1498.md",
            "装备/魔法物品",
            "collector_item_sets",
            ORG_DIR / "装备_魔法物品" / f"{SOURCE_BOOK_SHORT}_魔法物品套装.md",
            f"{SOURCE_BOOK_SHORT} 魔法物品套装",
            f"## {SOURCE_BOOK_SHORT} 魔法物品套装",
            block=item_block,
        )

    feat_block = normalize_block(feat_block)
    # 移除 feats 之后重复出现的套装描述段落
    if feat_block:
        feat_split = split_at_heading(feat_block, r"\n\s*格拉里昂的装备套装")
        if feat_split is not None:
            feat_block = normalize_block(feat_split[0])
    if feat_block:
        process_aggregate(
            report,
            "page_1498.md",
            "角色选项 → 专长",
            "collector_bo_feats",
            ORG_DIR / "角色" / "专长" / f"{SOURCE_BOOK_SHORT}_专长.md",
            f"{SOURCE_BOOK_SHORT} 专长",
            f"## {SOURCE_BOOK_SHORT} 收藏者之恩惠专长",
            block=feat_block,
        )

    # 2. page_1499.md：专究编年史 → 魔法技艺专长
    block = clean_aggregate((SRC_DIR / "page_1499.md").read_text(encoding="utf-8"))
    block = normalize_block(block)
    if block:
        process_aggregate(
            report,
            "page_1499.md",
            "角色选项 → 专长",
            "magic_trick_feats",
            ORG_DIR / "角色" / "专长" / f"{SOURCE_BOOK_SHORT}_专长.md",
            f"{SOURCE_BOOK_SHORT} 专长",
            f"## {SOURCE_BOOK_SHORT} 魔法技艺",
            block=block,
        )

    # 3. page_1500.md：英雄编年史 → 职业选项（战旗/炫技/忍术/天赋）
    block = clean_aggregate((SRC_DIR / "page_1500.md").read_text(encoding="utf-8"))
    block = normalize_block(block)
    if block:
        process_aggregate(
            report,
            "page_1500.md",
            "职业选项",
            "hero_chronicle_class_options",
            ORG_DIR / "职业" / f"{SOURCE_BOOK_SHORT}_职业选项.md",
            f"{SOURCE_BOOK_SHORT} 英雄编年史职业选项",
            f"## {SOURCE_BOOK_SHORT} 英雄编年史职业选项",
            block=block,
        )

    # 4. page_1501.md：典范编年史 → 替代巅峰
    block = clean_aggregate((SRC_DIR / "page_1501.md").read_text(encoding="utf-8"))
    block = normalize_block(block)
    if block:
        process_aggregate(
            report,
            "page_1501.md",
            "规则",
            "alternative_capstones",
            ORG_DIR / "规则" / f"{SOURCE_BOOK_SHORT}_替代巅峰.md",
            f"{SOURCE_BOOK_SHORT} 替代巅峰",
            f"## {SOURCE_BOOK_SHORT} 替代巅峰",
            block=block,
        )

    # 5. page_1502.md：进阶编年史 → 进阶职业专长
    block = clean_aggregate((SRC_DIR / "page_1502.md").read_text(encoding="utf-8"))
    block = normalize_block(block)
    if block:
        process_aggregate(
            report,
            "page_1502.md",
            "角色选项 → 专长",
            "prestige_feats",
            ORG_DIR / "角色" / "专长" / f"{SOURCE_BOOK_SHORT}_专长.md",
            f"{SOURCE_BOOK_SHORT} 专长",
            f"## {SOURCE_BOOK_SHORT} 进阶职业专长",
            block=block,
        )

    # 6. 密传骑士.md → 进阶职业
    block = clean_aggregate((SRC_DIR / "密传骑士.md").read_text(encoding="utf-8"))
    block = normalize_block(block)
    if block:
        process_aggregate(
            report,
            "密传骑士.md",
            "职业选项 → 进阶职业",
            "esoteric_knight",
            ORG_DIR / "职业" / "进阶职业" / f"{SOURCE_BOOK_SHORT}_进阶职业.md",
            f"{SOURCE_BOOK_SHORT} 密传骑士",
            f"## {SOURCE_BOOK_SHORT} 密传骑士",
            block=block,
        )

    # 7. 仪式师.md → 进阶职业
    block = clean_aggregate((SRC_DIR / "仪式师.md").read_text(encoding="utf-8"))
    block = normalize_block(block)
    if block:
        process_aggregate(
            report,
            "仪式师.md",
            "职业选项 → 进阶职业",
            "ritualist",
            ORG_DIR / "职业" / "进阶职业" / f"{SOURCE_BOOK_SHORT}_进阶职业.md",
            f"{SOURCE_BOOK_SHORT} 仪式师",
            f"## {SOURCE_BOOK_SHORT} 仪式师",
            block=block,
        )

    # 8. 仪式.md → 神秘仪式
    block = clean_aggregate((SRC_DIR / "仪式.md").read_text(encoding="utf-8"))
    block = normalize_block(block)
    if block:
        process_aggregate(
            report,
            "仪式.md",
            "规则",
            "egoists_militia_ritual",
            ORG_DIR / "规则" / f"{SOURCE_BOOK_SHORT}_神秘仪式.md",
            f"{SOURCE_BOOK_SHORT} 自我主义者之军势",
            f"## {SOURCE_BOOK_SHORT} 自我主义者之军势",
            block=block,
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
