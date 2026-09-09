#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 冒险者的军械库（Adventurer's Armory）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/冒险者的军械库
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/冒险者的军械库"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "AdventurersArmory_reorganization_report.md"

SOURCE_BOOK = "冒险者的军械库（Adventurer's Armory）"
SOURCE_BOOK_SHORT = "冒险者的军械库"


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


def clean_aggregate(text: str) -> str:
    """对聚合文件进行最小清理。"""
    import re

    text = text.replace("\r\n", "\n")
    # 移除 Markdown 图片链接
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    # 移除顶部译者/整理者链接与空行
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


def strip_trailing_artifacts(block: str) -> str:
    import re

    lines = block.splitlines()
    while lines and (lines[-1].strip() == "" or re.match(r"^\*+$", lines[-1].strip())):
        lines.pop()
    return "\n".join(lines)


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


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 专长
    process_aggregate(
        report,
        "专长26.md",
        "专长",
        "splash_weapon_mastery",
        ORG_DIR / "专长" / "冒险者的军械库_专长.md",
        "冒险者的军械库 专长",
        "## 溅射武器大师（Splash Weapon Mastery）",
    )

    # 装备技法规则与示例（page_512）
    process_aggregate(
        report,
        "page_512.md",
        "规则",
        "equipment_tricks",
        ORG_DIR / "规则" / "冒险者的军械库_装备技法.md",
        "冒险者的军械库 装备技法",
        "## 装备技法",
    )

    # 装备技法汇总（page_1090）
    process_aggregate(
        report,
        "page_1090.md",
        "规则",
        "equipment_tricks_compilation",
        ORG_DIR / "规则" / "冒险者的军械库_装备技法汇总.md",
        "冒险者的军械库 装备技法汇总",
        "## 装备技法汇总",
    )

    # 新武器
    process_aggregate(
        report,
        "新武器4.md",
        "装备",
        "new_weapons",
        ORG_DIR / "装备_魔法物品" / "武器" / "冒险者的军械库_武器.md",
        "冒险者的军械库 武器",
        "## 冒险者的军械库 新武器",
    )

    # 装备目录下的普通货品/服务
    equipment_files = [
        ("装备/page_1589.md", "adventuring_gear", "冒险装备"),
        ("装备/服饰.md", "clothing", "服饰"),
        ("装备/黑市道具.md", "black_market_goods", "黑市道具"),
        ("装备/食物、饮料和住宿.md", "food_drink_lodging", "食物、饮料和住宿"),
        ("装备/特殊物品和道具.md", "special_items", "特殊物品和道具"),
        ("装备/休闲道具.md", "leisure_items", "休闲道具"),
        ("装备/坐骑，宠物和相关装备.md", "mounts_pets_gear", "坐骑、宠物和相关装备"),
    ]
    for src, key, title in equipment_files:
        process_aggregate(
            report,
            src,
            "装备",
            key,
            ORG_DIR / "装备_魔法物品" / "货品服务" / f"冒险者的军械库_{title}.md",
            f"冒险者的军械库 {title}",
            f"## {title}",
        )

    # 工具和技能工具包追加到已有文件
    process_aggregate(
        report,
        "装备/工具和技能工具包.md",
        "装备",
        "tools_skill_kits",
        ORG_DIR / "工具和技能工具包.md",
        "工具和技能工具包",
        "## 冒险者的军械库 工具和技能工具包",
    )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
