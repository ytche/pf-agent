#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 格拉里昂的英雄（Heroes of Golarion）内容到已有分类目录。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/格拉里昂的英雄Heroes of Golarion"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "HeroesOfGolarion_reorganization_report.md"

SOURCE_BOOK = "格拉里昂的英雄（Heroes of Golarion）"
SOURCE_BOOK_SHORT = "格拉里昂的英雄HoG"


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


def split_by_anchors(text: str, anchors: list[dict]) -> list[tuple[dict, str]]:
    """Split text into blocks by anchor regex patterns.

    Anchors must appear in order. Each returned block starts at its anchor.
    """
    matches = []
    for anchor in anchors:
        for m in re.finditer(anchor["pattern"], text):
            matches.append((m.start(), anchor, m.end()))
    matches.sort(key=lambda x: x[0])

    # Keep only the first match for each anchor to avoid duplicates
    seen = set()
    filtered = []
    for start, anchor, end in matches:
        if anchor["name"] in seen:
            continue
        seen.add(anchor["name"])
        filtered.append((start, anchor, end))

    results = []
    prev_start = 0
    for i, (start, anchor, end) in enumerate(filtered):
        if i == 0:
            # discard leading intro before first anchor
            prev_start = start
            continue
        block = text[prev_start:start].strip()
        results.append((filtered[i - 1][1], block))
        prev_start = start
    if filtered:
        block = text[prev_start:].strip()
        results.append((filtered[-1][1], block))
    return results


def normalize_block(block: str) -> str:
    block = _normalize_stars(block)
    return _collapse_blank_lines(block.strip())


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. page_1374.md：变形者变体 + 调查员变体
    text = clean_aggregate((SRC_DIR / "page_1374.md").read_text(encoding="utf-8"))
    anchors = [
        {"name": "shifter_archetype", "pattern": r"(?:^|\n)\*{0,}圣兽", "l3": "职业选项 → 变形者", "entry": "shifter_holy_beast", "path": ORG_DIR / "职业" / "极限荒野（Ultimate Wilderness）" / "变形者" / f"{SOURCE_BOOK_SHORT}_变形者变体.md", "title": f"{SOURCE_BOOK_SHORT} 圣兽", "heading": f"## {SOURCE_BOOK_SHORT} 圣兽"},
        {"name": "investigator_archetype", "pattern": r"\n\*{0,}霍洛蒙格爆破专家", "l3": "职业选项 → 调查员", "entry": "investigator_holomog", "path": ORG_DIR / "职业" / "混合职业" / "调查员" / f"{SOURCE_BOOK_SHORT}_调查员变体.md", "title": f"{SOURCE_BOOK_SHORT} 霍洛蒙格爆破专家", "heading": f"## {SOURCE_BOOK_SHORT} 霍洛蒙格爆破专家"},
    ]
    for anchor, block in split_by_anchors(text, anchors):
        block = normalize_block(block)
        if block:
            process_aggregate(report, "page_1374.md", anchor["l3"], anchor["entry"], anchor["path"], anchor["title"], anchor["heading"], block=block)

    # 2. page_1375.md：术士血统 + 血脉狂怒者血统
    text = clean_aggregate((SRC_DIR / "page_1375.md").read_text(encoding="utf-8"))
    anchors = [
        {"name": "sorcerer_bloodline", "pattern": r"\n\*{0,}不死鸟血统", "l3": "职业选项 → 术士", "entry": "sorcerer_bloodlines", "path": ORG_DIR / "职业" / "核心职业" / "术士" / f"{SOURCE_BOOK_SHORT}_术士血统.md", "title": f"{SOURCE_BOOK_SHORT} 术士血统", "heading": f"## {SOURCE_BOOK_SHORT} 术士血统"},
        {"name": "bloodrager_bloodline", "pattern": r"\n\*{0,}斯芬克斯血统", "l3": "职业选项 → 血脉狂怒者", "entry": "bloodrager_sphinx", "path": ORG_DIR / "职业" / "混合职业" / "血脉狂怒者" / f"{SOURCE_BOOK_SHORT}_血脉狂怒者血脉.md", "title": f"{SOURCE_BOOK_SHORT} 血脉狂怒者血脉", "heading": f"## {SOURCE_BOOK_SHORT} 血脉狂怒者血脉"},
    ]
    for anchor, block in split_by_anchors(text, anchors):
        block = normalize_block(block)
        if block:
            process_aggregate(report, "page_1375.md", anchor["l3"], anchor["entry"], anchor["path"], anchor["title"], anchor["heading"], block=block)

    # 3. 阿卡迪亚英雄.md：专长 + 杀手天赋 + 传奇英灵
    text = clean_aggregate((SRC_DIR / "阿卡迪亚英雄.md").read_text(encoding="utf-8"))
    anchors = [
        {"name": "feats", "pattern": r"阿卡迪亚枪械专长", "l3": "角色选项 → 专长", "entry": "arcadian_gun_feats", "path": ORG_DIR / "角色" / "专长" / f"{SOURCE_BOOK_SHORT}_专长.md", "title": f"{SOURCE_BOOK_SHORT} 专长", "heading": f"## {SOURCE_BOOK_SHORT} 阿卡迪亚枪械专长"},
        {"name": "slayer_talents", "pattern": r"猎豹杀手天赋", "l3": "职业选项 → 杀手", "entry": "slayer_jaguar_talents", "path": ORG_DIR / "职业" / "混合职业" / "杀手" / f"{SOURCE_BOOK_SHORT}_杀手天赋.md", "title": f"{SOURCE_BOOK_SHORT} 猎豹杀手天赋", "heading": f"## {SOURCE_BOOK_SHORT} 猎豹杀手天赋"},
        {"name": "medium_spirits", "pattern": r"瓦伦哈拉传奇英灵", "l3": "职业选项 → 通灵者", "entry": "medium_valenhall_spirits", "path": ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "通灵者" / f"{SOURCE_BOOK_SHORT}_传奇英灵.md", "title": f"{SOURCE_BOOK_SHORT} 瓦伦哈拉传奇英灵", "heading": f"## {SOURCE_BOOK_SHORT} 瓦伦哈拉传奇英灵"},
    ]
    for anchor, block in split_by_anchors(text, anchors):
        block = normalize_block(block)
        if block:
            process_aggregate(report, "阿卡迪亚英雄.md", anchor["l3"], anchor["entry"], anchor["path"], anchor["title"], anchor["heading"], block=block)

    # 4. 阿维斯坦与世界之冠.md：吟游诗人变体、催眠师选项、专长、术士血统、萨满魂域
    text = clean_aggregate((SRC_DIR / "阿维斯坦与世界之冠.md").read_text(encoding="utf-8"))
    anchors = [
        {"name": "bard_archetype", "pattern": r"\n\*{0,}廷臣之眼语者", "l3": "职业选项 → 吟游诗人", "entry": "bard_speaker", "path": ORG_DIR / "职业" / "核心职业" / "吟游诗人" / f"{SOURCE_BOOK_SHORT}_吟游诗人变体.md", "title": f"{SOURCE_BOOK_SHORT} 廷臣之眼语者", "heading": f"## {SOURCE_BOOK_SHORT} 廷臣之眼语者"},
        {"name": "mesmerist_options", "pattern": r"\n\*{0,}盲眼催眠师", "l3": "职业选项 → 催眠师", "entry": "mesmerist_blind", "path": ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "催眠师" / f"{SOURCE_BOOK_SHORT}_催眠师选项.md", "title": f"{SOURCE_BOOK_SHORT} 盲眼催眠师选项", "heading": f"## {SOURCE_BOOK_SHORT} 盲眼催眠师选项"},
        {"name": "feats", "pattern": r"\n\*{0,}英雄地精专长", "l3": "角色选项 → 专长", "entry": "goblin_hero_feats", "path": ORG_DIR / "角色" / "专长" / f"{SOURCE_BOOK_SHORT}_专长.md", "title": f"{SOURCE_BOOK_SHORT} 专长", "heading": f"## {SOURCE_BOOK_SHORT} 英雄地精专长"},
        {"name": "sorcerer_bloodline", "pattern": r"\n\*{0,}独角兽血统", "l3": "职业选项 → 术士", "entry": "sorcerer_unicorn_avistan", "path": ORG_DIR / "职业" / "核心职业" / "术士" / f"{SOURCE_BOOK_SHORT}_术士血统.md", "title": f"{SOURCE_BOOK_SHORT} 术士血统", "heading": f"## {SOURCE_BOOK_SHORT} 独角兽血统"},
        {"name": "shaman_spirit", "pattern": r"\n\*{0,}寒霜萨满魂域", "l3": "职业选项 → 萨满", "entry": "shaman_frost_spirit", "path": ORG_DIR / "职业" / "混合职业" / "萨满" / f"{SOURCE_BOOK_SHORT}_萨满魂域.md", "title": f"{SOURCE_BOOK_SHORT} 寒霜萨满魂域", "heading": f"## {SOURCE_BOOK_SHORT} 寒霜萨满魂域"},
    ]
    for anchor, block in split_by_anchors(text, anchors):
        block = normalize_block(block)
        if block:
            process_aggregate(report, "阿维斯坦与世界之冠.md", anchor["l3"], anchor["entry"], anchor["path"], anchor["title"], anchor["heading"], block=block)

    # 5. 艾布利多斯.md：先知诅咒、传奇英灵、女巫巫术、血脉狂怒者血统、唤魂师变体
    text = clean_aggregate((SRC_DIR / "艾布利多斯.md").read_text(encoding="utf-8"))
    anchors = [
        {"name": "oracle_curse", "pattern": r"\n\*{0,}先知\s*\n", "l3": "职业选项 → 先知", "entry": "oracle_god_meddled", "path": ORG_DIR / "职业" / "基础职业" / "先知" / f"{SOURCE_BOOK_SHORT}_先知诅咒.md", "title": f"{SOURCE_BOOK_SHORT} 神扰诅咒", "heading": f"## {SOURCE_BOOK_SHORT} 神扰诅咒"},
        {"name": "medium_spirits", "pattern": r"\n\*{0,}通灵者传奇英灵", "l3": "职业选项 → 通灵者", "entry": "medium_iblydos_spirits", "path": ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "通灵者" / f"{SOURCE_BOOK_SHORT}_传奇英灵.md", "title": f"{SOURCE_BOOK_SHORT} 艾布利多斯传奇英灵", "heading": f"## {SOURCE_BOOK_SHORT} 艾布利多斯传奇英灵"},
        {"name": "witch_hexes", "pattern": r"\n\*{0,}巫术（Hex）", "l3": "职业选项 → 女巫", "entry": "witch_iblydos_hexes", "path": ORG_DIR / "职业" / "基础职业" / "女巫" / f"{SOURCE_BOOK_SHORT}_女巫巫术.md", "title": f"{SOURCE_BOOK_SHORT} 艾布利多斯女巫巫术", "heading": f"## {SOURCE_BOOK_SHORT} 艾布利多斯女巫巫术"},
        {"name": "bloodrager_bloodline", "pattern": r"\n\*{0,}蛇发女妖血统", "l3": "职业选项 → 血脉狂怒者", "entry": "bloodrager_medusa", "path": ORG_DIR / "职业" / "混合职业" / "血脉狂怒者" / f"{SOURCE_BOOK_SHORT}_血脉狂怒者血脉.md", "title": f"{SOURCE_BOOK_SHORT} 血脉狂怒者血脉", "heading": f"## {SOURCE_BOOK_SHORT} 蛇发女妖血统"},
        {"name": "spiritualist_archetype", "pattern": r"\n\*{0,}陨落者司祭", "l3": "职业选项 → 唤魂师", "entry": "spiritualist_priest_of_the_fallen", "path": ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "唤魂师" / f"{SOURCE_BOOK_SHORT}_唤魂师变体.md", "title": f"{SOURCE_BOOK_SHORT} 陨落者司祭", "heading": f"## {SOURCE_BOOK_SHORT} 陨落者司祭"},
    ]
    for anchor, block in split_by_anchors(text, anchors):
        block = normalize_block(block)
        if block:
            process_aggregate(report, "艾布利多斯.md", anchor["l3"], anchor["entry"], anchor["path"], anchor["title"], anchor["heading"], block=block)

    # 6. 加伦德荒野.md：变形者拟态
    text = clean_aggregate((SRC_DIR / "加伦德荒野.md").read_text(encoding="utf-8"))
    anchors = [
        {"name": "shifter_aspects", "pattern": r"加伦德动物拟态", "l3": "职业选项 → 变形者", "entry": "shifter_garundi_aspects", "path": ORG_DIR / "职业" / "极限荒野（Ultimate Wilderness）" / "变形者" / f"{SOURCE_BOOK_SHORT}_变形者拟态.md", "title": f"{SOURCE_BOOK_SHORT} 加伦德动物拟态", "heading": f"## {SOURCE_BOOK_SHORT} 加伦德动物拟态"},
    ]
    for anchor, block in split_by_anchors(text, anchors):
        block = normalize_block(block)
        if block:
            process_aggregate(report, "加伦德荒野.md", anchor["l3"], anchor["entry"], anchor["path"], anchor["title"], anchor["heading"], block=block)

    # 7. 加伦德英雄.md：火器弹药、侠客天赋、奥能技艺、野兽语者专长
    text = clean_aggregate((SRC_DIR / "加伦德英雄.md").read_text(encoding="utf-8"))
    anchors = [
        {"name": "firearms", "pattern": r"阿肯斯塔枪支弹药", "l3": "装备/火器", "entry": "alkenstar_firearms", "path": ORG_DIR / "装备_魔法物品" / f"{SOURCE_BOOK_SHORT}_火器与弹药.md", "title": f"{SOURCE_BOOK_SHORT} 阿肯斯塔火器与弹药", "heading": f"## {SOURCE_BOOK_SHORT} 阿肯斯塔火器与弹药"},
        {"name": "vigilante_talents", "pattern": r"侠客天赋", "l3": "职业选项 → 侠客", "entry": "vigilante_mwangi_talents", "path": ORG_DIR / "职业" / "混合职业" / "侠客" / f"{SOURCE_BOOK_SHORT}_侠客天赋.md", "title": f"{SOURCE_BOOK_SHORT} 侠客天赋", "heading": f"## {SOURCE_BOOK_SHORT} 侠客天赋"},
        {"name": "arcanist_exploits", "pattern": r"原能魔法奥能技艺", "l3": "职业选项 → 奥能师", "entry": "arcanist_primal_magic", "path": ORG_DIR / "职业" / "混合职业" / "奥能师" / f"{SOURCE_BOOK_SHORT}_奥能技艺.md", "title": f"{SOURCE_BOOK_SHORT} 原能魔法奥能技艺", "heading": f"## {SOURCE_BOOK_SHORT} 原能魔法奥能技艺"},
        {"name": "feats", "pattern": r"泰克立坦野兽语者", "l3": "角色选项 → 专长", "entry": "beast_speaker_feats", "path": ORG_DIR / "角色" / "专长" / f"{SOURCE_BOOK_SHORT}_专长.md", "title": f"{SOURCE_BOOK_SHORT} 专长", "heading": f"## {SOURCE_BOOK_SHORT} 泰克立坦野兽语者专长"},
    ]
    for anchor, block in split_by_anchors(text, anchors):
        block = normalize_block(block)
        if block:
            process_aggregate(report, "加伦德英雄.md", anchor["l3"], anchor["entry"], anchor["path"], anchor["title"], anchor["heading"], block=block)

    # 8. 卡斯马隆英雄.md：唤魂师变体、变形者拟态、异能者精神增幅
    text = clean_aggregate((SRC_DIR / "卡斯马隆英雄.md").read_text(encoding="utf-8"))
    anchors = [
        {"name": "spiritualist_archetype", "pattern": r"\n\*{0,}噬瘟者", "l3": "职业选项 → 唤魂师", "entry": "spiritualist_plague_eater", "path": ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "唤魂师" / f"{SOURCE_BOOK_SHORT}_唤魂师变体.md", "title": f"{SOURCE_BOOK_SHORT} 唤魂师变体", "heading": f"## {SOURCE_BOOK_SHORT} 噬瘟者"},
        {"name": "shifter_aspects", "pattern": r"新变形者拟态", "l3": "职业选项 → 变形者", "entry": "shifter_peacock", "path": ORG_DIR / "职业" / "极限荒野（Ultimate Wilderness）" / "变形者" / f"{SOURCE_BOOK_SHORT}_变形者拟态.md", "title": f"{SOURCE_BOOK_SHORT} 变形者拟态", "heading": f"## {SOURCE_BOOK_SHORT} 孔雀拟态"},
        {"name": "psychic_amplifications", "pattern": r"乌笃剌精神增幅", "l3": "职业选项 → 异能者", "entry": "psychic_vudrani_amps", "path": ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "异能者" / f"{SOURCE_BOOK_SHORT}_精神增幅.md", "title": f"{SOURCE_BOOK_SHORT} 乌笃剌精神增幅", "heading": f"## {SOURCE_BOOK_SHORT} 乌笃剌精神增幅"},
    ]
    for anchor, block in split_by_anchors(text, anchors):
        block = normalize_block(block)
        if block:
            process_aggregate(report, "卡斯马隆英雄.md", anchor["l3"], anchor["entry"], anchor["path"], anchor["title"], anchor["heading"], block=block)

    # 9. 龙国操念使.md：操念使原力
    text = clean_aggregate((SRC_DIR / "龙国操念使.md").read_text(encoding="utf-8"))
    anchors = [
        {"name": "kineticist_talents", "pattern": r"先祖原力", "l3": "职业选项 → 操念使", "entry": "kineticist_dragon_empires", "path": ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "操念使" / f"{SOURCE_BOOK_SHORT}_操念使原力.md", "title": f"{SOURCE_BOOK_SHORT} 龙国操念使原力", "heading": f"## {SOURCE_BOOK_SHORT} 龙国操念使原力"},
    ]
    for anchor, block in split_by_anchors(text, anchors):
        block = normalize_block(block)
        if block:
            process_aggregate(report, "龙国操念使.md", anchor["l3"], anchor["entry"], anchor["path"], anchor["title"], anchor["heading"], block=block)

    # 10. 神话异能.md：神话道途能力
    text = clean_aggregate((SRC_DIR / "神话异能.md").read_text(encoding="utf-8"))
    block = normalize_block(text)
    if block:
        process_aggregate(
            report,
            "神话异能.md",
            "职业选项 → 神话冒险",
            "mythic_occultism",
            ORG_DIR / "职业" / "神话冒险" / f"{SOURCE_BOOK_SHORT}_神话异能.md",
            f"{SOURCE_BOOK_SHORT} 神话异能",
            f"## {SOURCE_BOOK_SHORT} 神话异能",
            block=block,
        )

    # 11. 天夏英雄.md：术士血统、通灵者变体、炼金术师科研发现
    text = clean_aggregate((SRC_DIR / "天夏英雄.md").read_text(encoding="utf-8"))
    anchors = [
        {"name": "sorcerer_bloodline", "pattern": r"\n\*{0,}凤凰血统", "l3": "职业选项 → 术士", "entry": "sorcerer_phoenix_tian", "path": ORG_DIR / "职业" / "核心职业" / "术士" / f"{SOURCE_BOOK_SHORT}_术士血统.md", "title": f"{SOURCE_BOOK_SHORT} 术士血统", "heading": f"## {SOURCE_BOOK_SHORT} 凤凰血统"},
        {"name": "medium_archetype", "pattern": r"\n\*{0,}噬魂人", "l3": "职业选项 → 通灵者", "entry": "medium_spirit_eater", "path": ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "通灵者" / f"{SOURCE_BOOK_SHORT}_通灵者变体.md", "title": f"{SOURCE_BOOK_SHORT} 噬魂人", "heading": f"## {SOURCE_BOOK_SHORT} 噬魂人"},
        {"name": "alchemist_discoveries", "pattern": r"天洲炼金术", "l3": "职业选项 → 炼金术师", "entry": "alchemist_tian_inks", "path": ORG_DIR / "职业" / "基础职业" / "炼金术师" / f"{SOURCE_BOOK_SHORT}_科研发现.md", "title": f"{SOURCE_BOOK_SHORT} 天洲炼金术科研发现", "heading": f"## {SOURCE_BOOK_SHORT} 天洲炼金术科研发现"},
    ]
    for anchor, block in split_by_anchors(text, anchors):
        block = normalize_block(block)
        if block:
            process_aggregate(report, "天夏英雄.md", anchor["l3"], anchor["entry"], anchor["path"], anchor["title"], anchor["heading"], block=block)

    # 12. 种族替换特性：汲魂木.md：种族特性 + 专长
    text = clean_aggregate((SRC_DIR / "种族替换特性：汲魂木.md").read_text(encoding="utf-8"))
    anchors = [
        {"name": "race", "pattern": r"\n\*{0,}汲魂木(?:\*\*)?", "l3": "角色选项 → 种族特性", "entry": "wyrwood_race", "path": ORG_DIR / "角色" / "种族" / f"{SOURCE_BOOK_SHORT}_汲魂木.md", "title": f"{SOURCE_BOOK_SHORT} 汲魂木", "heading": f"## {SOURCE_BOOK_SHORT} 汲魂木"},
        {"name": "feats", "pattern": r"\n专长\s*\n", "l3": "角色选项 → 专长", "entry": "wyrwood_feats", "path": ORG_DIR / "角色" / "专长" / f"{SOURCE_BOOK_SHORT}_专长.md", "title": f"{SOURCE_BOOK_SHORT} 专长", "heading": f"## {SOURCE_BOOK_SHORT} 汲魂木专长"},
    ]
    for anchor, block in split_by_anchors(text, anchors):
        block = normalize_block(block)
        if block:
            process_aggregate(report, "种族替换特性：汲魂木.md", anchor["l3"], anchor["entry"], anchor["path"], anchor["title"], anchor["heading"], block=block)

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
