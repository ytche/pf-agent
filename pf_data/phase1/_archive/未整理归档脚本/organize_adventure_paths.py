#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 冒险之路 (Adventure Paths) 内容到已有分类目录。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/冒险之路"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "AdventurePaths_reorganization_report.md"

SOURCE_BOOK = "冒险之路"
SOURCE_BOOK_SHORT = "冒险之路AP"


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
            or "编注" in first
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


def merge_broken_bold(text: str) -> str:
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("**") and not re.search(r"\*\*.*\*\*", line.strip()):
            merged = line
            i += 1
            while i < len(lines) and not re.search(r"\*\*.*\*\*", merged):
                merged = f"{merged} {lines[i]}".rstrip()
                i += 1
            out.append(merged)
        else:
            out.append(line)
            i += 1
    return "\n".join(out)


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
    block = merge_broken_bold(block)
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
    report["merged"].append({"type": l3, "name": target_title, "entry": entry_name, "target": str(target_path.relative_to(ORG_DIR))})


def write_report(report: dict) -> None:
    lines = [f"# {SOURCE_BOOK} 整理报告\n", f"\n生成时间：{datetime.now().isoformat()}\n"]
    lines.append("\n## 整理内容\n")
    for item in report["merged"]:
        entry_name = item.get("entry", item["name"])
        lines.append(f"- **{item['type']}**：{entry_name} → `{item['target']}`")
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
# Adventure Path specific helpers
# ---------------------------------------------------------------------------

TARGETS = {
    "background": ORG_DIR / "角色" / "背景特性" / f"{SOURCE_BOOK_SHORT}_背景特性.md",
    "feat": ORG_DIR / "角色" / "专长" / f"{SOURCE_BOOK_SHORT}_专长.md",
    "equipment": ORG_DIR / "装备_魔法物品" / f"{SOURCE_BOOK_SHORT}_装备.md",
    "rogue_talent": ORG_DIR / "职业" / "核心职业" / "游荡者" / f"{SOURCE_BOOK_SHORT}_盗贼天赋.md",
    "prestige": ORG_DIR / "职业" / "进阶职业" / f"{SOURCE_BOOK_SHORT}_进阶职业.md",
    "faith": ORG_DIR / "信仰" / f"{SOURCE_BOOK_SHORT}_神祇.md",
    "monster": ORG_DIR / "种族" / "怪物种族" / f"{SOURCE_BOOK_SHORT}" / f"{SOURCE_BOOK_SHORT}_怪物.md",
    "ritual": ORG_DIR / "规则" / f"{SOURCE_BOOK_SHORT}_神秘仪式.md",
    "bloodline": ORG_DIR / "职业" / "核心职业" / "术士" / f"{SOURCE_BOOK_SHORT}_术士血统.md",
    "oracle_mystery": ORG_DIR / "职业" / "核心职业" / "先知" / f"{SOURCE_BOOK_SHORT}_先知秘示域.md",
    "class_archetype": ORG_DIR / "职业" / f"{SOURCE_BOOK_SHORT}_变体.md",
}


def route(report: dict, src_name: str, l3: str, entry_name: str, block: str) -> None:
    target_path = TARGETS[l3]
    target_title = f"{SOURCE_BOOK_SHORT} {_TARGET_TITLES[l3]}"
    heading = f"## {SOURCE_BOOK_SHORT} {entry_name}"
    process_aggregate(report, src_name, _L3_LABELS[l3], entry_name, target_path, target_title, heading, block=block)


_L3_LABELS = {
    "background": "角色选项 → 背景特性",
    "feat": "角色选项 → 专长",
    "equipment": "装备/魔法物品",
    "rogue_talent": "职业选项 → 游荡者天赋",
    "prestige": "职业选项 → 进阶职业",
    "faith": "信仰",
    "monster": "怪物",
    "ritual": "规则 → 神秘仪式",
    "bloodline": "职业选项 → 术士血统",
    "oracle_mystery": "职业选项 → 先知秘示域",
    "class_archetype": "职业选项 → 职业变体",
}

_TARGET_TITLES = {
    "background": "背景特性",
    "feat": "专长",
    "equipment": "装备",
    "rogue_talent": "盗贼天赋",
    "prestige": "进阶职业",
    "faith": "神祇",
    "monster": "怪物",
    "ritual": "神秘仪式",
    "bloodline": "术士血统",
    "oracle_mystery": "先知秘示域",
    "class_archetype": "职业变体",
}


def classify_block(text: str) -> str | None:
    """Return a target key for the whole block, or None if unclear."""
    t = text
    first_line = t.splitlines()[0] if t.splitlines() else ""

    # Monster: clear stat block (allow **AC**： style formatting)
    if re.search(r"CR\s+\d", t) and re.search(r"AC[\s\*]*[:：]", t) and re.search(r"HP[\s\*]*[:：]", t):
        return "monster"
    # Deity: domains + favored weapon
    if ("领域" in t or "domain" in t.lower()) and "偏好武器" in t:
        return "faith"
    # Prestige class: requirements + class table
    if (re.search(r"前置条件\s*[（(]Requirements", t) or re.search(r"进阶条件\s*[（(]Requirements", t)) and re.search(r"\|\s*BAB\s*\|", t):
        return "prestige"
    # Class archetype
    if "变体" in t and ("此能力取代" in t or "此能力调整了" in t or "职业变体" in t):
        return "class_archetype"
    # Oracle mystery
    if "秘示域" in t and "启示" in t:
        return "oracle_mystery"
    # Sorcerer bloodline
    if "术士血统" in t or ("血统力量" in t and "血统奥秘" in t):
        return "bloodline"
    # Occult ritual
    if "神秘仪式" in t and "技能检定" in t and "反冲" in t:
        return "ritual"
    # Rogue talent
    if "盗贼技艺" in t:
        return "rogue_talent"
    # Equipment: strong item indicators (avoid matching "施法者等级" alone in feat text)
    strong_eq = re.search(r"位置\s*[:：]|栏位|灵光|制造要求|制造需求|制造DC|制造花费", t)
    price_and_detail = "价格" in t and (
        "重量" in t
        or re.search(r"类型[*]*[：:]\s*[*]*炼金", t)
        or "栏位" in t
        or "灵光" in t
        or re.search(r"施法者等级", t)
    )
    if strong_eq or price_and_detail:
        return "equipment"
    # Alchemical item (allow bold markers around the label)
    if re.search(r"类型[*]*[：:]\s*[*]*炼金", t) and "价格" in t:
        return "equipment"
    # Special material
    if "特殊材料" in t or re.search(r"额外支付\s*\d+\s*金币", t):
        return "equipment"
    # Weapons table
    if re.search(r"异种武器\s*\|\s*价格\s*\|\s*小型伤害\s*\|\s*中型伤害", t):
        return "equipment"
    # Feat: prerequisites + effect, or multiple feat entries
    if ("先决条件" in t or "前置条件" in t) and ("效果" in t or "专长效果" in t):
        return "feat"
    # Feat collection heading
    if re.search(r"专长\s*$", first_line) and ("先决条件" in t or "效果" in t):
        return "feat"
    # Background trait
    if "背景特性" in t or re.search(r"分类\s*[:：]\s*(战斗|种族|宗教|战役|社会|信念)", t):
        return "background"
    return None


def split_by_bold_headings(text: str) -> list[tuple[str, str]]:
    """Split a block into entries starting with **Name**.

    Excludes inline label lines like **分类**：... or **需求**：...
    """
    lines = text.splitlines()
    entries: list[tuple[str, str]] = []
    current_name: str | None = None
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        # Entry heading: **Name** followed by whitespace/end, not by colon.
        bold_match = re.match(r"^\*\*([^*]+?)\*\*(?![：:])", stripped)
        # Avoid matching single-word labels such as **分类** or **需求**.
        if bold_match and not re.match(r"^\*\*[^*]{1,4}\*\*$", stripped):
            if current_name is not None:
                entries.append((current_name, "\n".join(current_lines).strip()))
            current_name = bold_match.group(1).strip()
            current_lines = [line]
        else:
            if current_name is not None:
                current_lines.append(line)

    if current_name is not None:
        entries.append((current_name, "\n".join(current_lines).strip()))

    return entries


def process_player_handbook_legacy_of_fire(report: dict) -> None:
    src = "烈焰传承/玩家手册1.md"
    text = clean_aggregate((SRC_DIR / src).read_text(encoding="utf-8"))
    text = normalize_block(text)
    parts = re.split(r"\n\s*-{3,}\s*\n", text, maxsplit=1)
    background_part = parts[0]
    item_part = parts[1] if len(parts) > 1 else ""

    entries = split_by_bold_headings(background_part)
    for name, block in entries:
        if not block.strip():
            continue
        route(report, src, "background", name, block)

    if item_part.strip():
        # First non-empty line is the item name
        item_name = item_part.strip().splitlines()[0].strip().strip("* ")
        route(report, src, "equipment", item_name, item_part.strip())


def process_player_handbook_shattered_star(report: dict) -> None:
    src = "破碎魔星/玩家手册.md"
    text = clean_aggregate((SRC_DIR / src).read_text(encoding="utf-8"))
    text = normalize_block(text)
    entries = split_by_bold_headings(text)
    for name, block in entries:
        if not block.strip():
            continue
        route(report, src, "background", name, block)


def process_player_handbook_crimson_throne(report: dict) -> None:
    src = "猩红王座的诅咒/玩家手册2.md"
    text = clean_aggregate((SRC_DIR / src).read_text(encoding="utf-8"))
    text = normalize_block(text)
    name = text.strip().splitlines()[0].strip().strip("* ")
    route(report, src, "feat", name, text)


def process_player_handbook_second_darkness(report: dict) -> None:
    src = "二度黑暗_黑暗再临/玩家手册3.md"
    text = clean_aggregate((SRC_DIR / src).read_text(encoding="utf-8"))
    text = normalize_block(text)
    name = text.strip().splitlines()[0].strip().strip("* ")
    route(report, src, "equipment", name, text)


def process_player_handbook_war_for_the_crown(report: dict) -> None:
    src = "皇冠战争/玩家手册6.md"
    text = clean_aggregate((SRC_DIR / src).read_text(encoding="utf-8"))
    text = normalize_block(text)
    name = text.strip().splitlines()[0].strip().strip("* ")
    route(report, src, "feat", name, text)


def process_deity_articles(report: dict) -> None:
    for src in ["钢铁巨神/泽弗斯.md", "破碎魔星/璃殇.md"]:
        path = SRC_DIR / src
        if not path.exists():
            report["warnings"].append(f"源文件不存在: {src}")
            continue
        text = clean_aggregate(path.read_text(encoding="utf-8"))
        text = normalize_block(text)
        name = text.strip().splitlines()[0].strip().strip("*# ")
        route(report, src, "faith", name, text)


def _is_url_only(block: str) -> bool:
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    return bool(lines) and all(ln.startswith("[") or ln.startswith("!") or ln.startswith("http") for ln in lines)


def process_split_file(report: dict, src: str) -> None:
    """Process a file known to contain multiple independent sections separated by ---."""
    path = SRC_DIR / src
    if not path.exists():
        report["warnings"].append(f"源文件不存在: {src}")
        return
    text = clean_aggregate(path.read_text(encoding="utf-8"))
    text = normalize_block(text)
    sections = re.split(r"\n\s*-{3,}\s*\n", text)
    for section in sections:
        if not section.strip() or _is_url_only(section):
            continue
        kind = classify_block(section)
        if kind is None:
            report["warnings"].append(f"无法分类: {src} → {_section_heading(section)[:40]}")
            continue
        name = _section_heading(section)
        route(report, src, kind, name, section)


# Item name pattern: optional **, optional spaces, Chinese name without whitespace, (English name).
# Full-width parentheses are used in the source Markdown.
_ITEM_NAME_RE = re.compile(r"(?:\*\*)?\s*[^\s*（\n]*?（[A-Za-z][A-Za-z0-9\s'’]+）")

def process_giant_slayer_91(report: dict) -> None:
    """巨人杀手第91章：专长 / 炼金武器 / 魔法物品 三大块，魔法物品内部用 --- 分描述/制造条件。"""
    src = "巨人杀手/91_Battle_of_Bloodmarch_Hills.md"
    path = SRC_DIR / src
    if not path.exists():
        report["warnings"].append(f"源文件不存在: {src}")
        return
    text = clean_aggregate(path.read_text(encoding="utf-8"))
    text = normalize_block(text)

    # 按顶层分类标题拆分，保留标题块
    parts = re.split(r"(?=\n\s*\*\*(?:巨人专长|巨人炼金武器|巨人魔法物品)\b)", text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^\*\*(.+?)\*\*", part)
        if not m:
            continue
        category = m.group(1).strip()

        if category == "巨人专长":
            route(report, src, "feat", "巨人专长", part)
        elif category == "巨人炼金武器":
            route(report, src, "equipment", "巨人炼金武器", part)
        elif category == "巨人魔法物品":
            # 按中英名标题切片（MD 中部分条目标题丢失加粗，不能仅靠 split_by_bold_headings）
            matches = list(_ITEM_NAME_RE.finditer(part))
            for i, match in enumerate(matches):
                name = match.group(0).strip().lstrip("*").strip()
                if name == "巨人魔法物品" or not name:
                    continue
                start = match.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(part)
                block = part[start:end].strip()
                if not block:
                    continue
                route(report, src, "equipment", name, block)


def process_mixed_files(report: dict) -> None:
    """Files containing clearly distinct mechanical sections of different types."""
    process_giant_slayer_91(report)
    for src in [
        "符文领主的崛起/5_Sins_of_the_Saviors.md",
        "蛇神颅骨/39_The_City_of_Seven_Spears.md",
        "暴君魔爪/139_The_Dead_Road_.md",
    ]:
        process_split_file(report, src)


def _section_heading(block: str) -> str:
    first = block.strip().splitlines()[0].strip().strip("*# ")
    # Collapse extra whitespace from broken bold merges.
    return re.sub(r"\s+", " ", first)


def process_remaining_file(report: dict, src: Path) -> None:
    rel = str(src.relative_to(SRC_DIR))
    text = clean_aggregate(src.read_text(encoding="utf-8"))
    text = normalize_block(text)
    if not text.strip():
        report["warnings"].append(f"空文件: {rel}")
        return

    kind = classify_block(text)
    if kind is None:
        report["warnings"].append(f"无法分类: {rel}")
        return

    name = _section_heading(text)
    route(report, rel, kind, name, text)


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # Explicit handlers
    process_player_handbook_legacy_of_fire(report)
    process_player_handbook_shattered_star(report)
    process_player_handbook_crimson_throne(report)
    process_player_handbook_second_darkness(report)
    process_player_handbook_war_for_the_crown(report)
    process_deity_articles(report)
    process_mixed_files(report)

    # All remaining .md files
    handled = {
        "烈焰传承/玩家手册1.md",
        "破碎魔星/玩家手册.md",
        "猩红王座的诅咒/玩家手册2.md",
        "二度黑暗_黑暗再临/玩家手册3.md",
        "皇冠战争/玩家手册6.md",
        "钢铁巨神/泽弗斯.md",
        "破碎魔星/璃殇.md",
        "符文领主的崛起/5_Sins_of_the_Saviors.md",
        "巨人杀手/91_Battle_of_Bloodmarch_Hills.md",
        "蛇神颅骨/39_The_City_of_Seven_Spears.md",
        "暴君魔爪/139_The_Dead_Road_.md",
    }
    for src in sorted(SRC_DIR.rglob("*.md")):
        rel = str(src.relative_to(SRC_DIR))
        if rel in handled:
            continue
        process_remaining_file(report, src)

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
