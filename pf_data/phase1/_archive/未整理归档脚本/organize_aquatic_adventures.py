#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 水下冒险（Aquatic Adventures）AA 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/水下冒险Aquatic Adventures
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/水下冒险Aquatic Adventures"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "AquaticAdventures_reorganization_report.md"

SOURCE_BOOK = "水下冒险（Aquatic Adventures）AA"
SOURCE_BOOK_SHORT = "AA"


def write_text_preserve(path: Path, text: str, line_ending: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\n", line_ending), encoding="utf-8")


def read_text_preserve(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    line_ending = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8"), line_ending


def detect_line_ending(path: Path) -> str:
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 4096))
        tail = f.read()
    if b"\r\n" in tail:
        return "\r\n"
    return "\n"


def safe_append_to_file(path: Path, marker: str, heading: str, source_annotation: str, block: str) -> None:
    """以二进制追加方式写入，保留原文件行尾不变，避免重写整个文件导致行尾混乱。"""
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
        if len(content) >= len(le.encode("utf-8")) * 2 and content.endswith((le * 2).encode("utf-8")):
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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 水下冒险AA{l3_part}"


def make_hidden_marker(source_file: str, entry_name: str) -> str:
    return f"<!-- {SOURCE_BOOK_SHORT}-source:{source_file}:{entry_name} -->"


def merge_section_heading_lines(text: str) -> str:
    lines = text.splitlines()
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*#+", line) and not line.rstrip().endswith(("）", ")", "]", "］")):
            j = i + 1
            buf = line
            while j < len(lines):
                next_line = lines[j]
                buf += " " + next_line.strip()
                if re.search(r"[）)］\]]\s*$", next_line):
                    break
                j += 1
            merged.append(buf)
            i = j + 1
        else:
            merged.append(line)
            i += 1
    return "\n".join(merged)


def merge_crossline_bold(text: str) -> str:
    lines = text.splitlines()
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        count = line.count("**")
        if count % 2 != 0:
            j = i + 1
            buf = line
            while j < len(lines):
                buf += " " + lines[j].strip()
                count += lines[j].count("**")
                if count % 2 == 0:
                    break
                j += 1
            merged.append(buf)
            i = j + 1
        else:
            merged.append(line)
            i += 1
    return "\n".join(merged)


def clean_translator_url(text: str) -> str:
    lines = text.splitlines()
    if lines and (
        lines[0].strip().startswith("[http")
        or re.match(r"^https?://", lines[0].strip())
        or "整理者" in lines[0]
        or "译者" in lines[0]
    ):
        lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return "\n".join(lines)


def clean_leading_image(text: str) -> str:
    lines = text.splitlines()
    while lines and re.match(r"^\s*!\[.*\]\(.*\)\s*$", lines[0].strip()):
        lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return "\n".join(lines)


def extract_block_whole_file(text: str) -> str:
    text = clean_translator_url(text)
    text = clean_leading_image(text)
    return text.strip()


def create_aggregation_file(path: Path, title: str, source_file: str, entries: list[tuple[str, str, str, str]], report: dict, item_type: str) -> None:
    """新建源书聚合文件；若文件已存在则跳过整本书写。"""
    if path.exists() and make_hidden_marker(source_file, "__aggregate__") in path.read_text(encoding="utf-8"):
        report["skipped"].append(f"{item_type}聚合文件已存在: {path.name}")
        return
    parts = [f"# {title}", "", make_hidden_marker(source_file, "__aggregate__"), ""]
    for marker, heading, source_annotation, block in entries:
        parts.append(marker)
        parts.append(heading)
        parts.append(source_annotation)
        parts.append("")
        parts.append(block)
        parts.append("")
        parts.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_preserve(path, "\n".join(parts), "\n")
    for _, heading, _, _ in entries:
        report["merged"].append({"type": item_type, "name": heading.lstrip("#").split("（")[0].strip(), "target": str(path.relative_to(ORG_DIR))})


def aggregate_whole_page(target_path: Path, title: str, source_file: str, heading: str, l3: str, report: dict, item_type: str) -> None:
    src_path = SRC_DIR / source_file
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    entry_marker = make_hidden_marker(source_file, heading.lstrip("# ").strip())
    entries = [(
        entry_marker,
        heading,
        make_source_annotation(source_file, l3),
        text.strip(),
    )]
    create_aggregation_file(target_path, title, source_file, entries, report, item_type)


# ========== 1. 游泳与水下冒险规则 ==========

def process_swimming_rules(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "水下冒险AA_游泳和水下冒险.md",
        "水下冒险 AA 游泳和水下冒险",
        "page_1026.md",
        "## 游泳和水下冒险",
        "游泳和水下冒险",
        report,
        "游泳和水下冒险规则",
    )


# ========== 2. 水下战斗 ==========

def process_underwater_combat(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "水下冒险AA_水下战斗.md",
        "水下冒险 AA 水下战斗",
        "page_1027.md",
        "## 水下战斗",
        "水下战斗",
        report,
        "水下战斗规则",
    )


# ========== 3. 水下的危险与特征 ==========

def process_underwater_hazards(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "规则" / "水下冒险AA_水下危险与特征.md",
        "水下冒险 AA 水下的危险与特征",
        "page_1028.md",
        "## 水下的危险与特征",
        "水下的危险与特征",
        report,
        "水下危险与特征",
    )


# ========== 4. 水下装备 ==========

def process_underwater_gear(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "水下冒险AA_水下装备.md",
        "水下冒险 AA 水下装备",
        "page_1029.md",
        "## 水下装备",
        "水下装备",
        report,
        "水下装备",
    )


# ========== 5. 水下专长 ==========

def process_underwater_feats(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "专长" / "水下冒险AA_专长.md",
        "水下冒险 AA 专长",
        "page_1030.md",
        "## 水下专长",
        "专长",
        report,
        "专长",
    )


# ========== 6. 水下法术 ==========

def process_underwater_spells(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "法术" / "水下冒险AA_法术.md",
        "水下冒险 AA 法术",
        "page_1031.md",
        "## 水下法术",
        "法术",
        report,
        "法术",
    )


# ========== 7. 水下宝藏 ==========

def process_underwater_treasure(report: dict) -> None:
    aggregate_whole_page(
        ORG_DIR / "装备_魔法物品" / "水下冒险AA_水下宝藏.md",
        "水下冒险 AA 水下宝藏",
        "page_1032.md",
        "## 水下宝藏",
        "水下宝藏",
        report,
        "水下宝藏",
    )


# ========== 8. 职业变体、血脉、骑士团、战斗流派 ==========

ARCHETYPES = [
    {"cn": "海洋化学家", "en": "Aquachymist", "class": "炼金术师", "target": ORG_DIR / "职业" / "基础职业" / "炼金术师" / "page_71.md", "kind": "炼金术师变体"},
    {"cn": "海之操念使", "en": "Aquakineticist", "class": "操念使", "target": ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "操念使" / "page_297.md", "kind": "操念使变体"},
    {"cn": "深潜战士", "en": "Aquanaut", "class": "战士", "target": ORG_DIR / "职业" / "核心职业" / "战士" / "page_49.md", "kind": "战士变体"},
    {"cn": "海洋", "en": "Aquatic", "class": "血脉狂怒者", "target": ORG_DIR / "职业" / "混合职业" / "血脉狂怒者" / "page_99.md", "kind": "血脉狂怒者血脉"},
    {"cn": "深海萨满", "en": "Deep Shaman", "class": "萨满", "target": ORG_DIR / "职业" / "混合职业" / "萨满" / "page_111.md", "kind": "萨满变体"},
    {"cn": "溺亡者引渡人", "en": "Drowned Channeler", "class": "唤魂师", "target": ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "唤魂师" / "page_270.md", "kind": "唤魂师变体"},
    {"cn": "大洋骑士", "en": "Oceanrider", "class": "骑士", "target": ORG_DIR / "职业" / "基础职业" / "骑士" / "护甲大师手册_骑士变体.md", "kind": "骑士变体"},
    {"cn": "波涛骑士团", "en": "Order of The Waves", "class": "骑将", "target": ORG_DIR / "职业" / "基础职业" / "骑将" / "page_23.md", "kind": "骑将骑士团"},
    {"cn": "珍珠寻者", "en": "Pearl seeker", "class": "圣武士", "target": ORG_DIR / "职业" / "核心职业" / "圣骑士" / "page_55.md", "kind": "圣武士变体"},
    {"cn": "远洋猎人", "en": "Pelagic Hunter", "class": "猎人", "target": ORG_DIR / "职业" / "混合职业" / "猎人" / "page_104.md", "kind": "猎人变体"},
    {"cn": "弄潮儿", "en": "Tidal Trickster", "class": "游荡者", "target": ORG_DIR / "职业" / "核心职业" / "盗贼" / "page_22.md", "kind": "游荡者变体"},
    {"cn": "水下", "en": "Underwater", "class": "游侠", "target": ORG_DIR / "职业" / "核心职业" / "游侠" / "page_59.md", "kind": "游侠战斗流派"},
]


def find_entry_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for entry in ARCHETYPES:
        # 标题可能以纯文本或加粗形式出现，英文可能跨行；这里只匹配 Chinese+English 的起始
        pattern = re.compile(
            rf"^\s*(?:\*\*)?{re.escape(entry['cn'])}\s*{re.escape(entry['en'])}",
            re.MULTILINE | re.IGNORECASE,
        )
        m = pattern.search(text)
        if not m:
            # 兜底：只用中文名
            pattern = re.compile(rf"^\s*(?:\*\*)?{re.escape(entry['cn'])}", re.MULTILINE)
            m = pattern.search(text)
        if m:
            starts.append((m.start(), entry))
        else:
            raise ValueError(f"无法在 page_1033.md 中定位条目：{entry['cn']}（{entry['en']}）")
    starts.sort(key=lambda x: x[0])
    return starts


def strip_trailing_artifacts(block: str) -> str:
    """去除源文件切分后留在段尾的孤立 ** / **** 标记与空行。"""
    lines = block.splitlines()
    while lines and (lines[-1].strip() == "" or re.match(r"^\*+$", lines[-1].strip())):
        lines.pop()
    return "\n".join(lines)


def check_existing_anywhere(entry: dict, report: dict) -> bool:
    """检查已经在其他位置存在同名条目，避免重复追加。"""
    cn = entry["cn"]
    en = entry["en"]

    # 炼金术师变体在《全变体未整合.md》中以“深潜化学家/Aquachymist”存在，与 AA 的“海洋化学家”是同一变体
    if en == "Aquachymist":
        alt_paths = [
            ORG_DIR / "职业" / "基础职业" / "炼金术师" / "全变体未整合.md",
            ORG_DIR / "全变体未整合.md",
        ]
        for p in alt_paths:
            if p.exists() and re.search(rf"深潜化学家|{re.escape(en)}", p.read_text(encoding="utf-8"), re.IGNORECASE):
                report["skipped"].append(
                    f"职业变体已存在: 炼金术师 海洋化学家（{en}）在 `{p.relative_to(ORG_DIR)}`，源文件标注为{SOURCE_BOOK_SHORT}，跳过以避免重复"
                )
                report.setdefault("cross_duplicates", []).append({
                    "entry": f"海洋化学家（{en}）",
                    "new_target": str(entry["target"].relative_to(ORG_DIR)),
                    "existing": str(p.relative_to(ORG_DIR)),
                    "note": "中文译名不同（海洋化学家 vs 深潜化学家），实为同一 Aquachymist 变体",
                })
                return True

    # 波涛骑士团已经出现在 page_1212.md 的骑士团汇编中
    if cn == "波涛骑士团":
        alt = ORG_DIR / "职业" / "基础职业" / "骑将" / "page_1212.md"
        if alt.exists() and cn in alt.read_text(encoding="utf-8"):
            report["skipped"].append(
                f"骑将骑士团已存在: {cn}（{en}）在 `{alt.relative_to(ORG_DIR)}`，源文件标注为{SOURCE_BOOK_SHORT}，跳过以避免重复"
            )
            report.setdefault("cross_duplicates", []).append({
                "entry": f"{cn}（{en}）",
                "new_target": str(entry["target"].relative_to(ORG_DIR)),
                "existing": str(alt.relative_to(ORG_DIR)),
                "note": "page_1212.md 已收录多个骑将骑士团，波涛骑士团已存在",
            })
            return True

    return False


def process_class_options(report: dict) -> None:
    src_path = SRC_DIR / "page_1033.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    starts = find_entry_starts(text)

    for idx, (start_pos, entry) in enumerate(starts):
        if check_existing_anywhere(entry, report):
            continue

        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)

        target_path = entry["target"]
        marker = make_hidden_marker("page_1033.md", entry["cn"])
        existing = target_path.read_text(encoding="utf-8") if target_path.exists() else ""

        title_pattern = re.compile(re.escape(entry["cn"]), re.IGNORECASE)
        if marker in existing or title_pattern.search(existing):
            report["skipped"].append(
                f"{entry['kind']}已存在: {entry['class']} {entry['cn']}（源文件标注为{SOURCE_BOOK_SHORT}，目标页已含同名条目）"
            )
            continue

        heading = f"## {entry['cn']}（{entry['en']}）【{SOURCE_BOOK_SHORT} {entry['kind']}】"
        l3 = f"变体/职业选项 → {entry['class']}"
        safe_append_to_file(
            target_path,
            marker,
            heading,
            make_source_annotation("page_1033.md", l3),
            block,
        )
        report["merged"].append({
            "type": entry["kind"],
            "name": entry["cn"],
            "target": str(target_path.relative_to(ORG_DIR)),
        })


# ========== 报告 ==========

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
    if report["warnings"]:
        lines.append("\n## 警告\n")
        for item in report["warnings"]:
            lines.append(f"- {item}")
    else:
        lines.append("\n## 警告\n\n无\n")
    if report.get("cross_duplicates"):
        lines.append("\n## 跨文件重复记录\n")
        for item in report["cross_duplicates"]:
            lines.append(
                f"- **{item['entry']}**：本次目标 `{item['new_target']}`；"
                f"已存在 `{item['existing']}` —— {item['note']}"
            )
    write_text_preserve(REPORT_PATH, "\n".join(lines))


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": [], "cross_duplicates": []}
    process_swimming_rules(report)
    process_underwater_combat(report)
    process_underwater_hazards(report)
    process_underwater_gear(report)
    process_underwater_feats(report)
    process_underwater_spells(report)
    process_underwater_treasure(report)
    process_class_options(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
