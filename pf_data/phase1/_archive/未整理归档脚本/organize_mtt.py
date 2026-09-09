#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 魔法战术工具箱（Magic Tactics Toolbox）MTT 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/魔法战术工具箱
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/魔法战术工具箱"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "MTT_reorganization_report.md"

SOURCE_BOOK = "魔法战术工具箱（Magic Tactics Toolbox）MTT"
SOURCE_BOOK_SHORT = "MTT"


def write_text_preserve(path: Path, text: str, line_ending: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\n", line_ending), encoding="utf-8")


def read_text_preserve(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    line_ending = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8"), line_ending


def append_to_file(path: Path, text: str) -> None:
    if not path.exists():
        write_text_preserve(path, "")
    existing, line_ending = read_text_preserve(path)
    existing = existing.replace("\r", "")
    if existing and not existing.endswith("\n"):
        existing += "\n"
    write_text_preserve(path, existing + text, line_ending)


def make_source_annotation(source_file: str, l3: str = "") -> str:
    l3_part = f" → {l3}" if l3 else ""
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 魔法战术工具箱MTT{l3_part}"


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


def find_entry_headings(section_text: str, entries: list[dict]) -> list[tuple[int, dict, str]]:
    positions = []
    for entry in entries:
        name = entry["name"]
        english = entry.get("english", "")
        eng_pat = re.escape(english).replace(r"\ ", r"\s+")
        patterns = [
            re.compile(r"(?:^|\n)\s*\*\*[^*]*?(?<![一-鿿])" + re.escape(name) + r"(?![一-鿿])[^*]*?\*\*", re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*[（(]\s*[^）)]*?" + eng_pat + r"[^）)]*?\s*[）)]", re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*[（(][^）)]+[）)]\s*" + eng_pat, re.IGNORECASE),
            re.compile(r"(?:^|\n)\s*" + re.escape(name) + r"\s*" + eng_pat, re.IGNORECASE),
        ]
        found = False
        for pattern in patterns:
            m = pattern.search(section_text)
            if m:
                start = m.start()
                positions.append((start, entry, m.group(0)))
                found = True
                break
        if not found:
            pattern = re.compile(re.escape(name), re.IGNORECASE)
            m = pattern.search(section_text)
            if m:
                positions.append((m.start(), entry, m.group(0)))
    positions.sort(key=lambda x: x[0])
    return positions


def split_section_by_entries(section_text: str, entries: list[dict]) -> dict[str, str]:
    positions = find_entry_headings(section_text, entries)
    blocks = {}
    for i, (pos, entry, heading) in enumerate(positions):
        start = pos
        end = positions[i + 1][0] if i + 1 < len(positions) else len(section_text)
        blocks[entry["name"]] = section_text[start:end].strip()
    return blocks


def append_entry(path: Path, marker: str, heading: str, source_annotation: str, block: str, report: dict, item_type: str, item_name: str, target_rel: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_preserve(path, "")
    existing, _ = read_text_preserve(path)
    if marker in existing:
        report["skipped"].append(f"{item_type}已存在: {item_name}")
        return
    entry = f"\n{marker}\n{heading}\n{source_annotation}\n{block}\n\n"
    append_to_file(path, entry)
    report["merged"].append({"type": item_type, "name": item_name, "target": target_rel})


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


# ========== 1. 专长 ==========

FEATS = [
    {"name": "敏锐射击", "english": "Acute Shot", "source_file": "page_325.md"},
    {"name": "轻快超魔", "english": "Brisk Spell", "source_file": "page_325.md"},
    {"name": "奥法强袭", "english": "Eldritch Assault", "source_file": "page_325.md"},
    {"name": "激励法术", "english": "Encouraging Spell", "source_file": "page_325.md"},
    {"name": "熟练祭祀", "english": "Practiced Ritualist", "source_file": "page_325.md"},
    {"name": "鳞片与毛皮", "english": "Scale and Skin", "source_file": "page_325.md"},
    {"name": "广域法术", "english": "Vast Spell", "source_file": "page_325.md"},
    {"name": "燃烧扩增", "english": "Burning Amplification", "source_file": "page_325.md"},
    {"name": "引导变化", "english": "Channeling Variance", "source_file": "page_325.md"},
    {"name": "寒冷扩增", "english": "Chilling Amplification", "source_file": "page_325.md"},
    {"name": "扩展超念", "english": "Expanded Metakinesis", "source_file": "page_325.md"},
    {"name": "额外变化", "english": "Extra Variance", "source_file": "page_325.md"},
    {"name": "多样凝视", "english": "Manifold Stare", "source_file": "page_325.md"},
    {"name": "冲击扩增", "english": "Shocking Amplification", "source_file": "page_325.md"},
    {"name": "炼金打击", "english": "Alchemical Strike", "source_file": "page_325.md"},
    {"name": "脱节凝视", "english": "Disconnected Stare", "source_file": "page_325.md"},
    {"name": "消解障碍", "english": "Hindrance Dismissal", "source_file": "page_325.md"},
    {"name": "能力掌握", "english": "Ability Mastery", "source_file": "page_325.md"},
    {"name": "隐藏掌握", "english": "Concealment Mastery", "source_file": "page_325.md"},
    {"name": "力场盾掌握", "english": "Force Shield Mastery", "source_file": "page_325.md"},
    {"name": "灵器掌握", "english": "Implement Mastery", "source_file": "page_325.md"},
    {"name": "种族物品掌握", "english": "Racial Item Mastery", "source_file": "page_325.md"},
    {"name": "抗力掌握", "english": "Resistance Mastery", "source_file": "page_325.md"},
    {"name": "复原掌握", "english": "Restoration Mastery", "source_file": "page_325.md"},
    {"name": "圣徽掌握", "english": "Symbolic Mastery", "source_file": "page_325.md"},
    {"name": "武器觉醒掌握", "english": "Weapon Evoker Mastery", "source_file": "page_325.md"},
]


def process_feats(report: dict) -> None:
    target_path = ORG_DIR / "专长" / "魔法战术工具箱MTT_专长.md"

    text = (SRC_DIR / "page_325.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    blocks = split_section_by_entries(text, FEATS)
    entries = []
    for feat in FEATS:
        block = blocks.get(feat["name"])
        if block is None:
            report["warnings"].append(f"未找到专长块: {feat['name']}")
            continue
        marker = make_hidden_marker(feat["source_file"], feat["name"])
        heading = f"## {feat['name']}（{feat['english']}）"
        source_annotation = make_source_annotation(feat["source_file"], "专长")
        entries.append((marker, heading, source_annotation, block))

    create_aggregation_file(
        target_path,
        "魔法战术工具箱 MTT 专长",
        "page_325.md",
        entries,
        report,
        "专长",
    )


# ========== 2. 法术 ==========

SPELLS = [
    {"name": "骸骨之拳", "english": "Bone Fists", "source_file": "page_326.md"},
    {"name": "时光闪回", "english": "Flash Forward", "source_file": "page_326.md"},
    {"name": "粒子形态", "english": "Particulate Form", "source_file": "page_326.md"},
    {"name": "相位挑战", "english": "Phasic Challenge", "source_file": "page_326.md"},
    {"name": "法咒", "english": "Spellcurse", "source_file": "page_326.md"},
    {"name": "扭曲金属", "english": "Warp Metal", "source_file": "page_326.md"},
    {"name": "咬人之语", "english": "Biting Words", "source_file": "page_326.md"},
    {"name": "弹性炸弹添加剂", "english": "Bouncing Bomb Admixture", "source_file": "page_326.md"},
    {"name": "关门放狗", "english": "Release the Hounds", "source_file": "page_326.md"},
    {"name": "追踪坑", "english": "Roaming Pit", "source_file": "page_326.md"},
    {"name": "沉眠之触", "english": "Touch of Slumber", "source_file": "page_326.md"},
    {"name": "分心徽记", "english": "Symbol of Distraction", "source_file": "page_326.md"},
    {"name": "魅影重温", "english": "Phantasmal Reminder", "source_file": "page_326.md"},
    {"name": "隐匿魔法书", "english": "Secluded Grimoire", "source_file": "page_326.md"},
    {"name": "先知誓缚", "english": "Bind Sage", "source_file": "page_326.md"},
    {"name": "阿卡西交流", "english": "Akashic Communion", "source_file": "page_326.md"},
    {"name": "骸骨之墙", "english": "Wall of Bone", "source_file": "page_326.md"},
    {"name": "顺风耳", "english": "Earsend", "source_file": "page_326.md"},
    {"name": "隐藏之刃", "english": "Hidden Blades", "source_file": "page_326.md"},
    {"name": "无解面纱", "english": "Impenetrable Veil", "source_file": "page_326.md"},
    {"name": "人畜无害", "english": "Innocuous Shape", "source_file": "page_326.md"},
    {"name": "次等回避侦测", "english": "Lesser Nondetection", "source_file": "page_326.md"},
    {"name": "阿拉兹尼斯特的厄运", "english": "Alaznist's Jinx", "source_file": "page_326.md"},
    {"name": "软化诅咒", "english": "Flexile Curse", "source_file": "page_326.md"},
    {"name": "不正体型", "english": "Irregular Size", "source_file": "page_326.md"},
    {"name": "痕痒诅咒", "english": "Itching Curse", "source_file": "page_326.md"},
    {"name": "卡利斯拉德的梦魇", "english": "Kalistocrat's Nightmare", "source_file": "page_326.md"},
    {"name": "失落馈赠", "english": "Lost Legacy", "source_file": "page_326.md"},
]


def process_spells(report: dict) -> None:
    target_path = ORG_DIR / "法术" / "魔法战术工具箱MTT_法术.md"

    text = (SRC_DIR / "page_326.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    blocks = split_section_by_entries(text, SPELLS)
    entries = []
    for spell in SPELLS:
        block = blocks.get(spell["name"])
        if block is None:
            report["warnings"].append(f"未找到法术块: {spell['name']}")
            continue
        marker = make_hidden_marker(spell["source_file"], spell["name"])
        heading = f"## {spell['name']}（{spell['english']}）"
        source_annotation = make_source_annotation(spell["source_file"], "法术")
        entries.append((marker, heading, source_annotation, block))

    create_aggregation_file(
        target_path,
        "魔法战术工具箱 MTT 法术",
        "page_326.md",
        entries,
        report,
        "法术",
    )


# ========== 3. 物品 ==========

ITEMS = [
    {"name": "学识银针", "english": "Lore Needle", "source_file": "物品28.md"},
    {"name": "印记粉笔", "english": "Sigil Chalk", "source_file": "物品28.md"},
]


def process_items(report: dict) -> None:
    target_path = ORG_DIR / "装备_魔法物品" / "魔法战术工具箱MTT_物品.md"

    text = (SRC_DIR / "物品28.md").read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    blocks = split_section_by_entries(text, ITEMS)
    entries = []
    for item in ITEMS:
        block = blocks.get(item["name"])
        if block is None:
            report["warnings"].append(f"未找到物品块: {item['name']}")
            continue
        marker = make_hidden_marker(item["source_file"], item["name"])
        heading = f"## {item['name']}（{item['english']}）"
        source_annotation = make_source_annotation(item["source_file"], "物品")
        entries.append((marker, heading, source_annotation, block))

    create_aggregation_file(
        target_path,
        "魔法战术工具箱 MTT 物品",
        "物品28.md",
        entries,
        report,
        "物品",
    )


# ========== 4. 职业变体 ==========

ARCHETYPES = [
    {"source_file": "变体/page_328.md", "class": "德鲁伊", "target": ORG_DIR / "职业" / "核心职业" / "德鲁伊" / "page_45.md", "names": ["牧兽者", "毒物学家"]},
    {"source_file": "变体/page_333.md", "class": "女巫", "target": ORG_DIR / "职业" / "基础职业" / "女巫" / "page_70.md", "names": ["浩劫使"]},
    {"source_file": "变体/page_334.md", "class": "炼金术师", "target": ORG_DIR / "职业" / "基础职业" / "炼金术师" / "page_21.md", "names": ["次元挖掘者"]},
    {"source_file": "变体/page_335.md", "class": "猎人", "target": ORG_DIR / "职业" / "混合职业" / "猎人" / "page_104.md", "names": ["耐心伏击者"]},
    {"source_file": "变体/page_337.md", "class": "审判者", "target": ORG_DIR / "职业" / "基础职业" / "审判者" / "page_78.md", "names": ["城市渗透者"]},
    {"source_file": "变体/page_336.md", "class": "魔战士", "target": ORG_DIR / "职业" / "基础职业" / "魔战士" / "page_82.md", "names": ["法术捕猎者"]},
    {"source_file": "变体/page_340.md", "class": "牧师", "target": ORG_DIR / "职业" / "核心职业" / "牧师" / "page_41.md", "names": ["神圣鞭笞者"]},
    {"source_file": "变体/page_341.md", "class": "萨满", "target": ORG_DIR / "职业" / "混合职业" / "萨满" / "page_111.md", "names": ["监督者"]},
    {"source_file": "变体/page_342.md", "class": "调查员", "target": ORG_DIR / "职业" / "混合职业" / "调查员" / "page_31.md", "names": ["秘兽学者", "发问者"]},
]


def process_archetypes(report: dict) -> None:
    for arc in ARCHETYPES:
        src_path = SRC_DIR / arc["source_file"]
        target_path = arc["target"]
        text = src_path.read_text(encoding="utf-8")
        text = merge_section_heading_lines(text)
        text = merge_crossline_bold(text)
        text = clean_translator_url(text)
        text = clean_leading_image(text)

        marker = make_hidden_marker(arc["source_file"], "/".join(arc["names"]))
        if marker in (target_path.read_text(encoding="utf-8") if target_path.exists() else ""):
            report["skipped"].append(f"职业变体已存在: {arc['class']} {'/'.join(arc['names'])}")
            continue

        heading = f"## {'/'.join(arc['names'])}（{SOURCE_BOOK_SHORT} 职业变体）"
        entry = f"\n{marker}\n{heading}\n{make_source_annotation(arc['source_file'], '变体')}\n{text.strip()}\n\n"
        append_to_file(target_path, entry)
        report["merged"].append({
            "type": f"{arc['class']}变体",
            "name": "、".join(arc["names"]),
            "target": str(target_path.relative_to(ORG_DIR)),
        })


# ========== 5. 职业选项 ==========

CLASS_OPTIONS = [
    {"source_file": "职业选项/page_329.md", "name": "调查员与盗贼天赋", "target": ORG_DIR / "专长" / "魔法战术工具箱MTT_调查员与盗贼天赋.md", "heading": "## 调查员与盗贼天赋"},
    {"source_file": "职业选项/page_330.md", "name": "进阶武器训练", "target": ORG_DIR / "职业" / "核心职业" / "战士" / "page_1094.md", "heading": "## 进阶武器训练（MTT）", "append_whole": True},
    {"source_file": "职业选项/page_331.md", "name": "血统突变", "target": ORG_DIR / "职业" / "核心职业" / "术士" / "page_64.md", "heading": "## 血统突变（MTT）", "append_whole": True},
    {"source_file": "职业选项/page_331.md", "name": "血统突变（血脉狂怒者）", "target": ORG_DIR / "职业" / "混合职业" / "血脉狂怒者" / "page_98.md", "heading": "## 血统突变（MTT）", "append_whole": True, "extra_note": "血统突变同时适用于术士与血脉狂怒者，此处追加至血脉狂怒者页面。"},
    {"source_file": "职业选项/page_332.md", "name": "新奥术发现", "target": ORG_DIR / "职业" / "核心职业" / "法师" / "page_67.md", "heading": "## 新奥术发现（MTT）", "append_whole": True},
    {"source_file": "职业选项/page_338.md", "name": "萨迦", "target": ORG_DIR / "职业" / "混合职业" / "歌者" / "page_115.md", "heading": "## 萨迦（MTT）", "append_whole": True},
    {"source_file": "职业选项/page_339.md", "name": "诅咒祝福", "target": ORG_DIR / "职业" / "混合职业" / "战斗祭司" / "【整理】战斗祭司祝福汇总.md", "heading": "## 诅咒祝福 Curse（MTT）", "append_whole": True},
    {"source_file": "职业选项/page_343.md", "name": "血巫术", "target": ORG_DIR / "专长" / "魔法战术工具箱MTT_血巫术.md", "heading": "## 血巫术"},
]


def process_class_options(report: dict) -> None:
    for opt in CLASS_OPTIONS:
        src_path = SRC_DIR / opt["source_file"]
        target_path = opt["target"]
        text = src_path.read_text(encoding="utf-8")
        text = merge_section_heading_lines(text)
        text = merge_crossline_bold(text)
        text = clean_translator_url(text)
        text = clean_leading_image(text)

        marker = make_hidden_marker(opt["source_file"], opt["name"])

        if opt.get("append_whole"):
            existing = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
            if marker in existing:
                report["skipped"].append(f"职业选项已存在: {opt['name']}")
                continue
            entry = f"\n{marker}\n{opt['heading']}\n{make_source_annotation(opt['source_file'], '职业选项')}\n{text.strip()}\n\n"
            append_to_file(target_path, entry)
            report["merged"].append({
                "type": "职业选项",
                "name": opt["name"],
                "target": str(target_path.relative_to(ORG_DIR)),
            })
        else:
            entries = [(
                marker,
                opt["heading"],
                make_source_annotation(opt["source_file"], "职业选项"),
                text.strip(),
            )]
            create_aggregation_file(
                target_path,
                opt["heading"].lstrip("# "),
                opt["source_file"],
                entries,
                report,
                "职业选项",
            )

        if "extra_note" in opt:
            report["warnings"].append(opt["extra_note"])


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
    write_text_preserve(REPORT_PATH, "\n".join(lines))


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}
    process_feats(report)
    process_spells(report)
    process_items(report)
    process_archetypes(report)
    process_class_options(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
