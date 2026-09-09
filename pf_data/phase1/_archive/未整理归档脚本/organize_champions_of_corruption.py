#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 秽邪勇士（Champions of Corruption）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/秽邪勇士
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/秽邪勇士"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "ChampionsOfCorruption_reorganization_report.md"

SOURCE_BOOK = "秽邪勇士（Champions of Corruption）"
SOURCE_BOOK_SHORT = "秽邪勇士"


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


def split_page_1226(text: str) -> dict[str, str]:
    """将 page_1226.md 切分为多个内容块。

    返回 {entry_name: block, ...}
    """
    # 按显式分隔线切出大块
    parts = [p.strip() for p in re.split(r"\n\s*-{3,}\s*\n", text) if p.strip()]
    sections: dict[str, str] = {}

    for part in parts:
        first_lines = "\n".join(part.splitlines()[:5])
        first_line = part.splitlines()[0].strip()
        if "怒噬者" in first_lines and "野蛮人变体" in first_lines:
            sections["raging_cannibal"] = part
        elif "震怖先锋" in first_lines and "反圣武士变体" in first_lines:
            sections["dread_vanguard"] = part
        elif first_line == "**子域**":
            sections["subdomains"] = part
        elif "鲜血召唤师" in first_lines and "召唤师变体" in first_lines:
            sections["blood_summoner"] = part
        elif "炼金术师科研发现" in first_lines:
            sections["alchemist_discoveries"] = part

    # 从怒噬者块中拆出通用狂暴之力
    if "raging_cannibal" in sections:
        rage_match = re.search(r"\n\s*\*\*狂暴之力\*\*\s*\n", sections["raging_cannibal"])
        if rage_match:
            variant_part = sections["raging_cannibal"][:rage_match.start()].strip()
            rage_part = sections["raging_cannibal"][rage_match.end():].strip()
            sections["raging_cannibal"] = variant_part
            sections["rage_powers"] = rage_part

    return sections


def split_items_file(text: str) -> tuple[str, str, str]:
    """将 物品.md 切分为毒药、影钉、其他魔法物品三块。"""
    shadow_idx = text.find("**奈多影钉**")
    magic_idx = text.find("**魔法物品**")
    if shadow_idx == -1 or magic_idx == -1:
        raise ValueError("物品.md 中未找到预期的'奈多影钉'或'魔法物品'分隔")
    poison_block = text[:shadow_idx].strip()
    shadow_block = text[shadow_idx:magic_idx].strip()
    item_block = text[magic_idx:].strip()
    return poison_block, shadow_block, item_block


def split_backgrounds_file(text: str) -> tuple[str, str]:
    """将 背景特性.md 切分为背景特性块与缺陷块。"""
    idx = text.find("**缺陷**")
    if idx == -1:
        raise ValueError("背景特性.md 中未找到'缺陷'分隔")
    trait_block = text[:idx].strip()
    flaw_block = text[idx:].strip()
    return trait_block, flaw_block


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

    # page_1226.md 多职业选项
    page_1226_text = clean_aggregate((SRC_DIR / "page_1226.md").read_text(encoding="utf-8"))
    sections = split_page_1226(page_1226_text)

    # 怒噬者野蛮人变体
    if "raging_cannibal" in sections:
        process_aggregate(
            report,
            "page_1226.md",
            "职业变体",
            "raging_cannibal",
            ORG_DIR / "职业" / "核心职业" / "野蛮人" / "page_35.md",
            "野蛮人 怒噬者",
            "## 格拉里昂的秽邪勇士 怒噬者（Raging Cannibal）",
            block=sections["raging_cannibal"],
        )

    # 新增狂暴之力
    if "rage_powers" in sections:
        process_aggregate(
            report,
            "page_1226.md",
            "职业选项",
            "rage_powers",
            ORG_DIR / "职业" / "核心职业" / "野蛮人" / "格拉里昂的秽邪勇士_狂暴之力.md",
            "格拉里昂的秽邪勇士 狂暴之力",
            "## 格拉里昂的秽邪勇士 狂暴之力",
            block=sections["rage_powers"],
        )

    # 震怖先锋反圣武士变体
    if "dread_vanguard" in sections:
        process_aggregate(
            report,
            "page_1226.md",
            "职业变体",
            "dread_vanguard",
            ORG_DIR / "职业" / "基础职业" / "反圣武士" / "page_406.md",
            "反圣武士 震怖先锋",
            "## 格拉里昂的秽邪勇士 震怖先锋（Dread Vanguard）",
            block=sections["dread_vanguard"],
        )

    # 子域
    if "subdomains" in sections:
        process_aggregate(
            report,
            "page_1226.md",
            "职业选项",
            "subdomains",
            ORG_DIR / "职业" / "核心职业" / "牧师" / "格拉里昂的秽邪勇士_牧师子域.md",
            "格拉里昂的秽邪勇士 牧师子域",
            "## 格拉里昂的秽邪勇士 牧师子域",
            block=sections["subdomains"],
        )

    # 鲜血召唤师变体 + 新进化
    if "blood_summoner" in sections:
        # 拆分为变体部分和进化部分
        evo_match = re.search(r"\n\s*\*\*新召唤师进化型态\*\*\s*\n", sections["blood_summoner"])
        if evo_match:
            variant_block = sections["blood_summoner"][:evo_match.start()].strip()
            evo_block = sections["blood_summoner"][evo_match.end():].strip()
        else:
            variant_block = sections["blood_summoner"]
            evo_block = ""
            report["warnings"].append("鲜血召唤师块中未找到'新召唤师进化型态'分隔")

        process_aggregate(
            report,
            "page_1226.md",
            "职业变体",
            "blood_summoner",
            ORG_DIR / "职业" / "基础职业" / "召唤师" / "page_410.md",
            "召唤师 鲜血召唤师",
            "## 格拉里昂的秽邪勇士 鲜血召唤师（Blood Summoner）",
            block=variant_block,
        )

        if evo_block:
            process_aggregate(
                report,
                "page_1226.md",
                "职业选项",
                "eidolon_evolutions",
                ORG_DIR / "职业" / "基础职业" / "召唤师" / "格拉里昂的秽邪勇士_召唤师进化.md",
                "格拉里昂的秽邪勇士 召唤师进化",
                "## 格拉里昂的秽邪勇士 召唤师进化",
                block=evo_block,
            )

    # 炼金术师科研发现
    if "alchemist_discoveries" in sections:
        process_aggregate(
            report,
            "page_1226.md",
            "职业选项",
            "alchemist_discoveries",
            ORG_DIR / "职业" / "基础职业" / "炼金术师" / "格拉里昂的秽邪勇士_科研发现.md",
            "格拉里昂的秽邪勇士 炼金科研发现",
            "## 格拉里昂的秽邪勇士 炼金科研发现",
            block=sections["alchemist_discoveries"],
        )

    # 物品.md：毒药 + 影钉 + 魔法物品
    items_text = clean_aggregate((SRC_DIR / "物品.md").read_text(encoding="utf-8"))
    poison_block, shadow_block, item_block = split_items_file(items_text)

    process_aggregate(
        report,
        "物品.md",
        "装备",
        "poisons",
        ORG_DIR / "装备_魔法物品" / "货品服务" / "page_212.md",
        "炼金物质和毒药",
        "## 格拉里昂的秽邪勇士 毒药",
        block=poison_block,
    )

    process_aggregate(
        report,
        "物品.md",
        "装备",
        "shadow_piercings",
        ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "格拉里昂的秽邪勇士_奇物.md",
        "格拉里昂的秽邪勇士 奇物",
        "## 格拉里昂的秽邪勇士 奈多影钉",
        block=shadow_block,
    )

    process_aggregate(
        report,
        "物品.md",
        "装备",
        "magic_items",
        ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "格拉里昂的秽邪勇士_奇物.md",
        "格拉里昂的秽邪勇士 奇物",
        "## 格拉里昂的秽邪勇士 魔法物品",
        block=item_block,
    )

    # 背景特性.md：背景特性 + 缺陷
    bg_text = clean_aggregate((SRC_DIR / "背景特性.md").read_text(encoding="utf-8"))
    trait_block, flaw_block = split_backgrounds_file(bg_text)

    process_aggregate(
        report,
        "背景特性.md",
        "背景特性",
        "traits",
        ORG_DIR / "背景特性" / "格拉里昂的秽邪勇士_背景特性.md",
        "格拉里昂的秽邪勇士 背景特性",
        "## 格拉里昂的秽邪勇士 背景特性",
        block=trait_block,
    )

    process_aggregate(
        report,
        "背景特性.md",
        "独立规则",
        "flaws",
        ORG_DIR / "规则" / "格拉里昂的秽邪勇士_缺陷.md",
        "格拉里昂的秽邪勇士 缺陷",
        "## 格拉里昂的秽邪勇士 缺陷",
        block=flaw_block,
    )

    # 专长.md
    process_aggregate(
        report,
        "专长.md",
        "专长",
        "__aggregate__",
        ORG_DIR / "专长" / "格拉里昂的秽邪勇士_专长.md",
        "格拉里昂的秽邪勇士 专长",
        "## 格拉里昂的秽邪勇士 专长",
    )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
