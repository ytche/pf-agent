#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
整理 反英雄手册Antihero's Handbook（AH）从 pf_rules_md/未整理/反英雄手册Antihero's Handbook
到 pf_rules_md_organized/ 对应目录。
"""

import re
from pathlib import Path
from datetime import datetime

# 基础路径
BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/反英雄手册Antihero's Handbook"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_DIR = BASE

SOURCE_BOOK = "反英雄手册（Antihero's Handbook）AH"
SOURCE_BOOK_SHORT = "AH"


def normalize_to_nl(text: str, target_nl: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if target_nl == "\r\n":
        text = text.replace("\n", "\r\n")
    return text


def detect_nl(path: Path) -> str:
    if not path.exists():
        return "\n"
    raw = path.read_bytes()
    return "\r\n" if b"\r\n" in raw else "\n"


def read_text_preserve(path: Path) -> tuple[str, str]:
    nl = detect_nl(path)
    if not path.exists():
        return "", nl
    return path.read_text(encoding="utf-8"), nl


def write_text_preserve(path: Path, text: str, nl: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = normalize_to_nl(text, nl)
    path.write_bytes(text.encode("utf-8"))


def append_to_file(path: Path, content: str) -> None:
    existing, nl = read_text_preserve(path)
    if existing and not existing.endswith("\n") and not existing.endswith("\r\n"):
        existing += nl
    elif existing and not (existing.endswith("\n") or existing.endswith("\r\n")):
        existing += nl
    new_content = existing + content
    write_text_preserve(path, new_content, nl)


def clean_translator_url(text: str) -> str:
    lines = text.splitlines()
    while lines and (
        not lines[0].strip()
        or lines[0].strip().startswith("http")
        or lines[0].strip().startswith("[http")
        or lines[0].strip().startswith("译者")
    ):
        lines.pop(0)
    return "\n".join(lines)


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


def merge_section_heading_lines(text: str) -> str:
    """合并跨行的大写/小写英文标题，例如 'Broken-back \nseax'、'UNARMED \nMASTERY'。"""
    lines = text.splitlines()
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            if re.search(r"[A-Za-z]$", line.rstrip()) and re.match(r"^[A-Za-z]", next_line.lstrip()):
                merged.append(line.rstrip() + " " + next_line.lstrip())
                i += 2
                continue
        merged.append(line)
        i += 1
    return "\n".join(merged)


def make_source_annotation(source_file: str, l3: str = "") -> str:
    l3_part = f" → {l3}" if l3 else ""
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 反英雄手册AH{l3_part}"


def make_hidden_marker(source_file: str, entry_name: str) -> str:
    return f"<!-- {SOURCE_BOOK_SHORT}-source:{source_file}:{entry_name} -->"


def is_title_span(span: str) -> bool:
    if not re.search(r"[一-鿿]", span):
        return False
    if re.search(r"[A-Za-z]", span):
        return True
    if re.search(r"[（(][^）)]+[）)]", span):
        return True
    return False


def extract_block_by_name(text: str, name: str, english: str = "") -> str | None:
    base_pattern = re.compile(r"\*\*[^*]*?" + re.escape(name) + r"[^*]*?\*\*")
    candidates = [m for m in base_pattern.finditer(text) if is_title_span(m.group(0))]

    if candidates and english:
        eng_norm = " ".join(english.lower().split())
        pref = []
        for m in candidates:
            span = m.group(0)
            norm = re.sub(r"\s+", " ", span).lower()
            if eng_norm in norm:
                pref.append(m)
        if pref:
            candidates = pref

    if candidates:
        start_match = min(candidates, key=lambda m: len(m.group(0)))
        start = start_match.start()
        rest = text[start_match.end():]
        next_pattern = re.compile(r"\*\*[^*]+?\*\*")
        pos = 0
        end = len(text)
        while True:
            nm = next_pattern.search(rest, pos)
            if not nm:
                break
            span = nm.group(0)
            if is_title_span(span):
                end = start_match.end() + nm.start()
                break
            pos = nm.end()
        return text[start:end].strip()

    if english:
        eng_pat = re.escape(english).replace(r"\ ", r"\s*")
        plain_pattern = re.compile(
            r"(?:^|\n)\s*(" + re.escape(name) + r"(?:(?:\s*[（(]\s*[^）)]*?" + eng_pat + r"[^）)]*?\s*[）)])|(?:\s*" + eng_pat + r")))",
            re.IGNORECASE,
        )
    else:
        plain_pattern = re.compile(r"(?:^|\n)\s*(" + re.escape(name) + r")", re.IGNORECASE)
    pm = plain_pattern.search(text)
    if pm:
        start = pm.start()
        rest = text[pm.end():]
        next_stop = re.search(r"\n\s*\n|\n\s*\*\*[^*]+\*\*", rest)
        if next_stop:
            end = pm.end() + next_stop.start()
        else:
            end = len(text)
        return text[start:end].strip()

    return None


def find_entry_headings(section_text: str, entries: list[dict]) -> list[tuple[int, dict, str]]:
    positions = []
    for entry in entries:
        name = entry["name"]
        english = entry.get("english", "")
        eng_pat = re.escape(english).replace(r"\ ", r"\s+")
        patterns = [
            re.compile(re.escape(name) + r"\s*[（(]\s*[^）)]*?" + eng_pat + r"[^）)]*?\s*[）)]", re.IGNORECASE),
            re.compile(re.escape(name) + r"\s*[（(][^）)]+[）)]\s*" + eng_pat, re.IGNORECASE),
            re.compile(re.escape(name) + r"\s*" + eng_pat, re.IGNORECASE),
            re.compile(r"\*\*[^*]*?" + re.escape(name) + r"[^*]*?\*\*", re.IGNORECASE),
        ]
        found = False
        for pattern in patterns:
            m = pattern.search(section_text)
            if m:
                positions.append((m.start(), entry, m.group(0)))
                found = True
                break
        if not found:
            pattern = re.compile(re.escape(name), re.IGNORECASE)
            m = pattern.search(section_text)
            if m:
                positions.append((m.start(), entry, m.group(0)))
    positions.sort()
    return positions


def split_section_by_entries(section_text: str, entries: list[dict]) -> dict[str, str]:
    positions = find_entry_headings(section_text, entries)
    blocks = {}
    for i, (pos, entry, heading) in enumerate(positions):
        start = pos
        end = positions[i + 1][0] if i + 1 < len(positions) else len(section_text)
        blocks[entry["name"]] = section_text[start:end].strip()
    return blocks


def extract_section(text: str, start_marker: str, end_marker: str = "") -> str | None:
    start_pat = re.compile(re.escape(start_marker), re.IGNORECASE)
    sm = start_pat.search(text)
    if not sm:
        return None
    start = sm.start()
    if end_marker:
        end_pat = re.compile(re.escape(end_marker), re.IGNORECASE)
        em = end_pat.search(text, sm.end())
        if em:
            return text[start:em.start()].strip()
    return text[start:].strip()


# ========== 1. 职业变体 ==========
ARCHETYPES = [
    {"name": "风骚客", "english": "Blatherskite", "class": "铳士", "source_file": "铳士变体.md"},
    {"name": "恶党同谋", "english": "Colluding Scoundrel", "class": "猎人", "source_file": "猎人变体.md"},
    {"name": "碎裂之魂", "english": "Splintersoul", "class": "侠客", "source_file": "page_1189.md"},
    {"name": "无名引路人", "english": "Channeler of the Unknown", "class": "前牧师", "source_file": "page_1091.md"},
    {"name": "位面异端", "english": "Planar Extremist", "class": "前德鲁伊", "source_file": "page_1091.md"},
    {"name": "原罪僧", "english": "Sin Monk", "class": "前武僧", "source_file": "page_1091.md"},
    {"name": "复仇暴徒", "english": "Vindictive Bastard", "class": "前圣武士", "source_file": "page_1091.md"},
]


def _prepare_text(source_file: str) -> str:
    text = (SRC_DIR / source_file).read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    return clean_translator_url(text)


def process_archetypes(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "反英雄手册AH_变体.md"
    if not target_path.exists():
        write_text_preserve(target_path, f"# {SOURCE_BOOK} 职业变体\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    # page_1091.md 包含多个前职业变体，需要按条目拆分
    multi_source = "page_1091.md"
    multi_entries = [arc for arc in ARCHETYPES if arc["source_file"] == multi_source]
    if multi_entries:
        text = _prepare_text(multi_source)
        multi_blocks = split_section_by_entries(text, multi_entries)
    else:
        multi_blocks = {}

    for arc in ARCHETYPES:
        if arc["source_file"] == multi_source:
            block = multi_blocks.get(arc["name"])
        else:
            block = _prepare_text(arc["source_file"])

        if block is None:
            report["warnings"].append(f"未找到变体块: {arc['name']} ({arc['source_file']})")
            continue

        marker = make_hidden_marker(arc["source_file"], arc["name"])
        if marker in existing:
            report["skipped"].append(f"变体已存在: {arc['name']}")
            continue
        entry = (
            f"\n{marker}\n"
            f"## {arc['name']}（{arc['english']}）〔{arc['class']}变体〕\n"
            f"{make_source_annotation(arc['source_file'], '变体/职业选项')}\n"
            f"{block}\n\n"
        )
        append_to_file(target_path, entry)
        report["merged"].append({"type": "变体", "name": arc["name"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 2. 专长 ==========
FEATS = [
    {"name": "矢志不移", "english": "Sheltering Stubborness", "source_file": "专长32.md"},
]


def process_feats(report: dict) -> None:
    target_path = ORG_DIR / "专长" / "反英雄手册AH_专长.md"
    if not target_path.exists():
        write_text_preserve(target_path, f"# {SOURCE_BOOK} 专长\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    for feat in FEATS:
        block = _prepare_text(feat["source_file"])
        if not block.strip():
            report["warnings"].append(f"未找到专长块: {feat['name']} ({feat['source_file']})")
            continue
        marker = make_hidden_marker(feat["source_file"], feat["name"])
        if marker in existing:
            report["skipped"].append(f"专长已存在: {feat['name']}")
            continue
        entry = (
            f"\n{marker}\n"
            f"## {feat['name']}（{feat['english']}）\n"
            f"{make_source_annotation(feat['source_file'], '专长')}\n"
            f"{block}\n\n"
        )
        append_to_file(target_path, entry)
        report["merged"].append({"type": "专长", "name": feat["name"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 3. 魅影情感羁绊：受难 ==========
PHANTOM_FOCUS = [
    {"name": "受难灵", "english": "Suffering"},
]


def process_phantom_focus(report: dict) -> None:
    src_path = SRC_DIR / "职业选项.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    target_path = ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "唤魂师" / "page_271.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 魅影\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    section = extract_section(text, "魅影情感羁绊：受难", "沙尘炸弹")
    if section:
        blocks = split_section_by_entries(section, [{"name": "受难灵", "english": "Suffering"}])
        block = blocks.get("受难灵")
    else:
        block = None

    if block is None:
        report["warnings"].append("未找到受难灵块")
        return

    marker = make_hidden_marker("职业选项.md", "受难灵")
    if marker in existing:
        report["skipped"].append("受难灵已存在")
        return

    entry = (
        f"\n{marker}\n"
        f"## 受难灵（Suffering）\n"
        f"{make_source_annotation('职业选项.md', '魅影情感羁绊')}\n"
        f"{block}\n\n"
    )
    append_to_file(target_path, entry)
    report["merged"].append({"type": "魅影情感羁绊", "name": "受难灵", "target": str(target_path.relative_to(ORG_DIR))})


# ========== 4. 炼金术士科研发现：沙尘炸弹 ==========
DISCOVERIES = [
    {"name": "沙尘炸弹", "english": "Sand Bomb"},
]


def process_discoveries(report: dict) -> None:
    src_path = SRC_DIR / "职业选项.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)

    target_path = ORG_DIR / "职业" / "基础职业" / "炼金术师" / "page_71.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 炼金术师科研发现\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    section = extract_section(text, "沙尘炸弹")
    if section:
        blocks = split_section_by_entries(section, [{"name": "沙尘炸弹", "english": "Sand Bomb"}])
        block = blocks.get("沙尘炸弹")
    else:
        block = None

    if block is None:
        report["warnings"].append("未找到沙尘炸弹块")
        return

    marker = make_hidden_marker("职业选项.md", "沙尘炸弹")
    if marker in existing:
        report["skipped"].append("沙尘炸弹已存在")
        return

    entry = (
        f"\n{marker}\n"
        f"## 沙尘炸弹（Sand Bomb）\n"
        f"{make_source_annotation('职业选项.md', '炼金术士科研发现')}\n"
        f"{block}\n\n"
    )
    append_to_file(target_path, entry)
    report["merged"].append({"type": "炼金术士科研发现", "name": "沙尘炸弹", "target": str(target_path.relative_to(ORG_DIR))})


# ========== 5. 物品 ==========
ITEMS = [
    {"name": "粪球榴弹", "english": "Dung grenade", "source_file": "物品25.md"},
]


def process_items(report: dict) -> None:
    target_path = ORG_DIR / "装备_魔法物品" / "货品服务" / "page_212.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 货品与服务\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    for item in ITEMS:
        block = _prepare_text(item["source_file"])
        if not block.strip():
            report["warnings"].append(f"未找到物品块: {item['name']} ({item['source_file']})")
            continue
        marker = make_hidden_marker(item["source_file"], item["name"])
        if marker in existing:
            report["skipped"].append(f"物品已存在: {item['name']}")
            continue
        entry = (
            f"\n{marker}\n"
            f"## {item['name']}（{item['english']}）\n"
            f"{make_source_annotation(item['source_file'], '物品')}\n"
            f"{block}\n\n"
        )
        append_to_file(target_path, entry)
        report["merged"].append({"type": "物品", "name": item["name"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 6. 缺陷（合并到根目录缺陷.md） ==========
FLAWS = [
    {"name": "轻蔑", "english": "Contemptuous", "source_file": "缺陷.md"},
    {"name": "贪财好利", "english": "For the Money", "source_file": "缺陷.md"},
]


def process_flaws(report: dict) -> None:
    target_path = ORG_DIR / "缺陷.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 缺陷\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    src_path = SRC_DIR / "缺陷.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)

    for flaw in FLAWS:
        block = extract_block_by_name(text, flaw["name"], flaw.get("english", ""))
        if block is None:
            report["warnings"].append(f"未找到缺陷块: {flaw['name']}")
            continue
        marker = make_hidden_marker(flaw["source_file"], flaw["name"])
        if marker in existing:
            report["skipped"].append(f"缺陷已存在: {flaw['name']}")
            continue
        # 若目标文件已有同名标题但无 marker，视为早期已手动合并，仅记录跳过
        existing_has_name = re.search(
            r"(?:^|\n)\s*#{0,2}\s*\*?\*" + re.escape(flaw['name']) + r"(?:\*\*|\（|\()",
            existing,
        )
        if existing_has_name:
            report["skipped"].append(f"缺陷已在目标文件存在（无 marker）: {flaw['name']}")
            continue
        entry = (
            f"\n{marker}\n"
            f"## {flaw['name']}（{flaw['english']}）\n"
            f"{make_source_annotation(flaw['source_file'], '缺陷')}\n"
            f"{block}\n\n"
        )
        append_to_file(target_path, entry)
        report["merged"].append({"type": "缺陷", "name": flaw["name"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 主流程 ==========

def main() -> None:
    report = {
        "merged": [],
        "skipped": [],
        "warnings": [],
    }

    process_archetypes(report)
    process_feats(report)
    process_phantom_focus(report)
    process_discoveries(report)
    process_items(report)
    process_flaws(report)

    # 生成报告
    report_path = REPORT_DIR / "AH_reorganization_report.md"
    lines = [f"# 反英雄手册（Antihero's Handbook）AH 整理报告\n", f"\n生成时间：{datetime.now().isoformat()}\n"]
    lines.append("\n## 整理内容\n")
    for item in report["merged"]:
        lines.append(f"- **{item['type']}**：{item['name']} → `{item['target']}`")
    lines.append("\n## 跳过项\n")
    for item in report["skipped"]:
        lines.append(f"- {item}")
    lines.append("\n## 警告\n")
    for item in report["warnings"]:
        lines.append(f"- {item}")
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")
    if report["warnings"]:
        for w in report["warnings"]:
            print(f"  警告: {w}")


if __name__ == "__main__":
    main()
