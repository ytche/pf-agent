#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 卡蒂亚，通向东方的大门 (Qadira, Gateway to the East) 内容到已有分类目录。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from organize_adventure_paths import (
    clean_aggregate,
    detect_line_ending,
    normalize_block,
    safe_append_to_file,
    write_text_preserve,
)

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_PATH = BASE / "pf_rules_md/未整理/page_1005.md"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "Qadira_reorganization_report.md"

SOURCE_BOOK = "卡蒂亚，通向东方的大门"
SOURCE_BOOK_SHORT = "QGthE"
SOURCE_FILE = "page_1005.md"

TARGETS = {
    "background": ORG_DIR / "角色" / "背景特性" / f"{SOURCE_BOOK_SHORT}_背景特性.md",
    "feat": ORG_DIR / "角色" / "专长" / f"{SOURCE_BOOK_SHORT}_专长.md",
    "equipment": ORG_DIR / "装备_魔法物品" / f"{SOURCE_BOOK_SHORT}_装备.md",
}

_L3_LABELS = {
    "background": "角色选项 → 背景特性",
    "feat": "角色选项 → 专长",
    "equipment": "装备/魔法物品",
}

_TARGET_TITLES = {
    "background": "背景特性",
    "feat": "专长",
    "equipment": "装备",
}

# (marker_in_text, kind, display_entry_name)
ENTRIES: list[tuple[str, str, str]] = [
    ("军队背景和专长", "skip", "军队背景和专长"),
    ("治愈的甜美味道", "skip", "治愈的甜美味道"),
    ("信者工具", "skip", "信者工具"),
    ("新的地区背景**这座大城市", "skip", "新的地区背景"),
    ("新的地区背景下列背景", "skip", "新的地区背景"),
    ("新的特殊材料", "skip", "新的特殊材料"),
    ("骑乘砍杀", "feat", "骑乘砍杀 Mounted Blade [General]"),
    ("壮臂柔腕", "background", "壮臂柔腕 Strong Arm, Supple Wrist"),
    ("巴勒斯骑士", "background", "巴勒斯骑士（卡蒂亚）Rider of Paresh (Qadira)"),
    ("监视塔尔多", "background", "监视塔尔多（卡蒂亚）Watching Taldor (Qadira)"),
    ("科莱什公主", "background", "科莱什公主（卡蒂亚科莱什女性）Keleshite Princess (Qadiran Keleshite female)"),
    ("卡希尔商人", "background", "卡希尔商人（卡蒂亚）Merchant of Katheer (Qadira)"),
    ("维尼坎医师", "background", "维尼坎医师（卡蒂亚）Venicaan Medic (Qadira)"),
    ("希里没药Healy", "equipment", "希里没药 Healy Myrrh"),
    ("晨花烈焰", "background", "晨花烈焰（莎伦莱）Flame of the Dawnflower (Sarenrae)"),
    ("莎伦莱的战裙", "equipment", "莎伦莱的战裙 War-Kilt of Sarenrae"),
    ("狂舞 [", "feat", "狂舞 [战斗专长] Dervish Dance [Combat]"),
    ("炼金奇才", "background", "炼金奇才 Alchemical Prodigy（苏比亚）"),
    ("元素门徒", "background", "元素门徒 Elemental Pupil"),
    ("巨灵呼唤者", "background", "巨灵呼唤者 Genie-Caller"),
    ("面纱隐者", "background", "面纱隐者 Keeper of the Veil"),
    ("自走结界", "background", "自走结界 Walking Ward"),
    ("亮银Silversheen", "equipment", "亮银 Silversheen"),
]


def make_source_annotation(l3: str = "") -> str:
    return f"> 来源：{SOURCE_BOOK}（{SOURCE_BOOK_SHORT}），页码见原书，未整理 → {SOURCE_FILE} → {l3}"


def make_hidden_marker(entry_name: str) -> str:
    return f"<!-- {SOURCE_BOOK_SHORT}-source:{SOURCE_FILE}:{entry_name} -->"


def process_entry(report: dict, kind: str, entry_name: str, block: str) -> None:
    target_path = TARGETS[kind]
    target_title = f"{SOURCE_BOOK_SHORT} {_TARGET_TITLES[kind]}"
    heading = f"## {SOURCE_BOOK_SHORT} {entry_name}"

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, f"# {target_title}\n\n", "\n")

    marker = make_hidden_marker(entry_name)
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append(f"{_L3_LABELS[kind]}已存在: {SOURCE_FILE}:{entry_name}")
        return

    # strip trailing table/horizontal-rule artifacts copied from adventure script
    lines = block.splitlines()
    while lines and (
        lines[-1].strip() == ""
        or re.match(r"^\*+$", lines[-1].strip())
        or re.match(r"^\|", lines[-1].strip())
        or re.match(r"^\|?\s*---", lines[-1].strip())
        or lines[-1].strip() == "---"
    ):
        lines.pop()
    block = "\n".join(lines)

    safe_append_to_file(
        target_path,
        marker,
        heading,
        make_source_annotation(_L3_LABELS[kind]),
        block,
    )
    report["merged"].append(
        {"type": _L3_LABELS[kind], "name": entry_name, "target": str(target_path.relative_to(ORG_DIR))}
    )


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
    write_text_preserve(REPORT_PATH, "\n".join(lines), "\n")


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    text = clean_aggregate(SRC_PATH.read_text(encoding="utf-8"))
    text = normalize_block(text)

    # Locate each entry by its Chinese marker and slice between markers.
    matches: list[tuple[int, str, str, str]] = []
    for marker, kind, name in ENTRIES:
        pat = re.compile(re.escape(marker))
        found = list(pat.finditer(text))
        if not found:
            report["warnings"].append(f"未找到条目定位子串: {marker}")
            continue
        if len(found) > 1:
            report["warnings"].append(f"条目定位子串出现多次，取首次: {marker}")
        matches.append((found[0].start(), marker, kind, name))

    matches.sort()

    for i, (start, _marker, kind, name) in enumerate(matches):
        end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if not block or kind == "skip":
            continue
        process_entry(report, kind, name, block)

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
