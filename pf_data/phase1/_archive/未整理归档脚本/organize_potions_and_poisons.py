#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 药剂与毒药（Potions and Poisons）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/药剂与毒药P&amp;P
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/药剂与毒药P&amp;P"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "PotionsAndPoisons_reorganization_report.md"

SOURCE_BOOK = "药剂与毒药（Potions and Poisons）"
SOURCE_BOOK_SHORT = "药剂与毒药P&P"


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


def split_wondrous_items(text: str) -> tuple[list[str], list[str], list[str]]:
    """将装备聚合文本拆分为有位置奇物、无位置奇物与普通装备三组。

    返回 (slotted_blocks, slotless_blocks, mundane_blocks)
    """
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]

    slotted: list[str] = []
    slotless: list[str] = []
    mundane: list[str] = []
    for block in blocks:
        # 无效分隔线/表格头
        if re.match(r"^\|?\s*---", block.splitlines()[0].strip()):
            continue
        # 普通装备：没有灵光、施法者等级、位置栏位等魔法物品标记
        if not re.search(r"(?:灵光|施法者等级|价格|位置|栏位)", block):
            mundane.append(block)
            continue
        # 有位置 vs 无位置
        if re.search(r"(?:位置|栏位)[：:\*]*\s*无", block):
            slotless.append(block)
        elif re.search(r"(?:位置|栏位)[：:\*]*\s*[一-龥a-zA-Z]+", block):
            slotted.append(block)
        else:
            # 有价格/灵光但没有位置字段，视为无位置奇物
            if re.search(r"(?:灵光|施法者等级)", block):
                slotless.append(block)
            else:
                mundane.append(block)
    return slotted, slotless, mundane


def split_page_1268_items(text: str) -> tuple[list[str], list[str], list[str]]:
    """按已知物品名将 page_1268 拆分为有位置奇物、无位置奇物与普通装备。

    返回 (slotted_items, slotless_items, mundane_items)
    """
    # page_1268 中所有物品的中文名称（按出现顺序）
    item_names = [
        "有效死亡之环", "凋败踢踏", "死亡之愿", "收集者工具箱", "瘴气面具",
        "毒喷盒", "毒羽笔", "投毒高脚杯", "收割者之智", "凝毒骸布",
        "匿声油", "毒云香炉", "高等复原徽章", "炼金术士的花洒",
        "谨慎化学家的围裙", "化毒指环", "毒晶之眼", "忍耐的恩泽",
        "拒亡手套", "收割者的束臂", "腐化衔尾蛇头带", "反麻痹护身符",
        "毒液克星含片", "强韧回荡背心",
    ]
    # 去重并保持顺序
    seen = set()
    unique_names = []
    for name in item_names:
        if name not in seen:
            seen.add(name)
            unique_names.append(name)

    # 找到每个物品的起始位置
    positions: list[tuple[int, str]] = []
    for name in unique_names:
        idx = text.find(name)
        if idx != -1:
            positions.append((idx, name))
    positions.sort()

    # 提取每个物品块
    items: list[tuple[str, str]] = []
    for i, (start, name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        block = text[start:end].strip()
        # 去掉表格残留的分隔符行
        lines = block.splitlines()
        cleaned_lines = [ln for ln in lines if not re.match(r"^\|?\s*---", ln.strip())]
        block = "\n".join(cleaned_lines).strip()
        if block:
            items.append((name, block))

    slotted: list[str] = []
    slotless: list[str] = []
    mundane: list[str] = []
    for name, block in items:
        # 判断分类：位置字段
        if re.search(r"(?:位置|栏位)[：:\*]*\s*无", block):
            slotless.append(block)
        elif re.search(r"(?:位置|栏位)[：:\*]*\s*[一-龥a-zA-Z]+", block):
            slotted.append(block)
        else:
            mundane.append(block)
    return slotted, slotless, mundane


def extract_between(text: str, start: str, end: str | None = None) -> str:
    """提取 text 中从 start 标记到 end 标记（不含）之间的内容。"""
    s = text.find(start)
    if s == -1:
        return ""
    e = len(text)
    if end:
        e = text.find(end, s + len(start))
        if e == -1:
            e = len(text)
    return text[s:e].strip()


def strip_leading_heading(block: str) -> str:
    """移除块首可能存在的 Markdown 标题/星号装饰。"""
    lines = block.splitlines()
    while lines and lines[0].strip().lstrip("#").strip() == "":
        lines = lines[1:]
    return "\n".join(lines).strip()


def process_page_1258(report: dict, text: str) -> None:
    """处理种族专长、职业变体、术士血脉。"""
    # 树蛙人专长
    grippli_feats = extract_between(text, "树蛙人专长", "曼特蛙")
    if grippli_feats:
        process_aggregate(
            report,
            "page_1258.md",
            "专长",
            "grippli_feats",
            ORG_DIR / "专长" / "药剂与毒药P&P_专长.md",
            "药剂与毒药P&P 专长",
            "## 树蛙人专长",
            block=strip_leading_heading(grippli_feats),
        )

    # 曼特蛙（德鲁伊变体）
    mantella = extract_between(text, "曼特蛙", "沼泽毒杀者")
    if mantella:
        process_aggregate(
            report,
            "page_1258.md",
            "职业",
            "mantella",
            ORG_DIR / "职业" / "核心职业" / "德鲁伊" / "page_37.md",
            "德鲁伊",
            "## 曼特蛙（Mantella）",
            block=strip_leading_heading(mantella),
        )

    # 沼泽毒杀者（盗贼变体）
    swamp_poisoner = extract_between(text, "沼泽毒杀者", "娜迦裔")
    if swamp_poisoner:
        process_aggregate(
            report,
            "page_1258.md",
            "职业",
            "swamp_poisoner",
            ORG_DIR / "职业" / "核心职业" / "盗贼" / "page_22.md",
            "盗贼",
            "## 沼泽毒杀者（Swamp Poisoner）",
            block=strip_leading_heading(swamp_poisoner),
        )

    # 娜迦裔专长
    nagaji_feats = extract_between(text, "娜迦裔专长", "毒刃")
    if nagaji_feats:
        process_aggregate(
            report,
            "page_1258.md",
            "专长",
            "nagaji_feats",
            ORG_DIR / "专长" / "药剂与毒药P&P_专长.md",
            "药剂与毒药P&P 专长",
            "## 娜迦裔专长",
            block=strip_leading_heading(nagaji_feats),
        )

    # 毒刃（战士变体）
    venomblade = extract_between(text, "毒刃", "蝮血裔")
    if venomblade:
        process_aggregate(
            report,
            "page_1258.md",
            "职业",
            "venomblade",
            ORG_DIR / "职业" / "核心职业" / "战士" / "page_44.md",
            "战士",
            "## 毒刃（Venomblade）",
            block=strip_leading_heading(venomblade),
        )

    # 蝮血裔专长
    vishkanya_feats = extract_between(text, "蝮血裔专长", "叉舌门徒")
    if vishkanya_feats:
        process_aggregate(
            report,
            "page_1258.md",
            "专长",
            "vishkanya_feats",
            ORG_DIR / "专长" / "药剂与毒药P&P_专长.md",
            "药剂与毒药P&P 专长",
            "## 蝮血裔专长",
            block=strip_leading_heading(vishkanya_feats),
        )

    # 叉舌门徒（吟游诗人变体）
    disciple = extract_between(text, "叉舌门徒", "剧毒遗产")
    if disciple:
        process_aggregate(
            report,
            "page_1258.md",
            "职业",
            "disciple_forked_tongue",
            ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "page_38.md",
            "吟游诗人",
            "## 叉舌门徒（Disciple of the Forked Tongue）",
            block=strip_leading_heading(disciple),
        )

    # 蝎子血脉
    scorpion_bloodline = extract_between(text, "蝎子血脉", None)
    if scorpion_bloodline:
        process_aggregate(
            report,
            "page_1258.md",
            "职业",
            "scorpion_bloodline",
            ORG_DIR / "职业" / "核心职业" / "术士" / "page_64.md",
            "术士",
            "## 蝎子血脉（Scorpion Bloodline）",
            block=strip_leading_heading(scorpion_bloodline),
        )


def process_page_1259(report: dict, text: str) -> None:
    """炼金术师变体与科研发现。"""
    concocter = extract_between(text, "调制师", "身酿酵师")
    if concocter:
        process_aggregate(
            report,
            "page_1259.md",
            "职业",
            "concocter",
            ORG_DIR / "职业" / "基础职业" / "炼金术师" / "page_21.md",
            "炼金术师",
            "## 调制师（Concocter）",
            block=strip_leading_heading(concocter),
        )

    fermenter = extract_between(text, "身酿酵师", "科研发现")
    if fermenter:
        process_aggregate(
            report,
            "page_1259.md",
            "职业",
            "fermenter",
            ORG_DIR / "职业" / "基础职业" / "炼金术师" / "page_21.md",
            "炼金术师",
            "## 身酿酵师（Fermenter）",
            block=strip_leading_heading(fermenter),
        )

    discoveries = extract_between(text, "科研发现", None)
    if discoveries:
        process_aggregate(
            report,
            "page_1259.md",
            "职业",
            "discoveries",
            ORG_DIR / "职业" / "基础职业" / "炼金术师" / "page_71.md",
            "炼金术师科研发现",
            "## 科研发现（Discoveries）",
            block=strip_leading_heading(discoveries),
        )


def process_page_1260(report: dict, text: str) -> None:
    """女巫变体、巫术、强力巫术、女巫法术。"""
    venom_siphoner = extract_between(text, "汲毒巫", "巫术")
    if venom_siphoner:
        process_aggregate(
            report,
            "page_1260.md",
            "职业",
            "venom_siphoner",
            ORG_DIR / "职业" / "基础职业" / "女巫" / "page_70.md",
            "女巫",
            "## 汲毒巫（Venom Siphoner）",
            block=strip_leading_heading(venom_siphoner),
        )

    hexes = extract_between(text, "巫术", "强力巫术")
    if hexes:
        process_aggregate(
            report,
            "page_1260.md",
            "职业",
            "hexes",
            ORG_DIR / "职业" / "基础职业" / "女巫" / "药剂与毒药P&P_女巫巫术.md",
            "药剂与毒药P&P 女巫巫术",
            "## 巫术（Hexes）",
            block=strip_leading_heading(hexes),
        )

    major_hexes = extract_between(text, "强力巫术", "女巫法术")
    if major_hexes:
        process_aggregate(
            report,
            "page_1260.md",
            "职业",
            "major_hexes",
            ORG_DIR / "职业" / "基础职业" / "女巫" / "药剂与毒药P&P_女巫巫术.md",
            "药剂与毒药P&P 女巫巫术",
            "## 强力巫术（Major Hexes）",
            block=strip_leading_heading(major_hexes),
        )

    witch_spells = extract_between(text, "女巫法术", None)
    if witch_spells:
        process_aggregate(
            report,
            "page_1260.md",
            "法术",
            "witch_spells",
            ORG_DIR / "法术" / "药剂与毒药P&P_法术.md",
            "药剂与毒药P&P 法术",
            "## 女巫法术",
            block=strip_leading_heading(witch_spells),
        )


def process_page_1261(report: dict, text: str) -> None:
    """盗贼变体、盗贼天赋、杀手天赋。"""
    needler = extract_between(text, "针杀者", "饮毒鬼")
    if needler:
        process_aggregate(
            report,
            "page_1261.md",
            "职业",
            "needler",
            ORG_DIR / "职业" / "核心职业" / "盗贼" / "page_22.md",
            "盗贼",
            "## 针杀者（Needler）",
            block=strip_leading_heading(needler),
        )

    rotdrinker = extract_between(text, "饮毒鬼", "盗贼天赋")
    if rotdrinker:
        process_aggregate(
            report,
            "page_1261.md",
            "职业",
            "rotdrinker",
            ORG_DIR / "职业" / "核心职业" / "盗贼" / "page_22.md",
            "盗贼",
            "## 饮毒鬼（Rotdrinker）",
            block=strip_leading_heading(rotdrinker),
        )

    rogue_talents = extract_between(text, "盗贼天赋", "杀手天赋")
    if rogue_talents:
        process_aggregate(
            report,
            "page_1261.md",
            "职业",
            "rogue_talents",
            ORG_DIR / "职业" / "核心职业" / "盗贼" / "药剂与毒药P&P_盗贼天赋.md",
            "药剂与毒药P&P 盗贼天赋",
            "## 盗贼天赋（Rogue Talents）",
            block=strip_leading_heading(rogue_talents),
        )

    slayer_talents = extract_between(text, "杀手天赋", None)
    if slayer_talents:
        process_aggregate(
            report,
            "page_1261.md",
            "职业",
            "slayer_talents",
            ORG_DIR / "职业" / "混合职业" / "杀手" / "药剂与毒药P&P_杀手天赋.md",
            "药剂与毒药P&P 杀手天赋",
            "## 杀手天赋（Slayer Talents）",
            block=strip_leading_heading(slayer_talents),
        )


def process_page_1262(report: dict, text: str) -> None:
    """调查员变体与调查员天赋。"""
    reckless = extract_between(text, "无忌饮者", "编毒师")
    if reckless:
        process_aggregate(
            report,
            "page_1262.md",
            "职业",
            "reckless_epicurean",
            ORG_DIR / "职业" / "混合职业" / "调查员" / "page_31.md",
            "调查员",
            "## 无忌饮者（Reckless Epicurean）",
            block=strip_leading_heading(reckless),
        )

    toxin_codexer = extract_between(text, "编毒师", "调查员天赋")
    if toxin_codexer:
        process_aggregate(
            report,
            "page_1262.md",
            "职业",
            "toxin_codexer",
            ORG_DIR / "职业" / "混合职业" / "调查员" / "page_31.md",
            "调查员",
            "## 编毒师（Toxin Codexer）",
            block=strip_leading_heading(toxin_codexer),
        )

    investigator_talents = extract_between(text, "调查员天赋", None)
    if investigator_talents:
        process_aggregate(
            report,
            "page_1262.md",
            "职业",
            "investigator_talents",
            ORG_DIR / "职业" / "混合职业" / "调查员" / "药剂与毒药P&P_调查员天赋.md",
            "药剂与毒药P&P 调查员天赋",
            "## 调查员天赋（Investigator Talents）",
            block=strip_leading_heading(investigator_talents),
        )


def process_page_1263(report: dict, text: str) -> None:
    """专长、适饮法术、药水与油参考指南。"""
    # 专长：从"多样化制药"到"适饮法术"
    feats = extract_between(text, "多样化制药", "适饮法术")
    if feats:
        process_aggregate(
            report,
            "page_1263.md",
            "专长",
            "versatile_brewing_feats",
            ORG_DIR / "专长" / "药剂与毒药P&P_专长.md",
            "药剂与毒药P&P 专长",
            "## 多样化制药专长",
            block=strip_leading_heading(feats),
        )

    # 适饮法术：从"适饮法术"到"药水与油参考指南"
    potable_spells = extract_between(text, "适饮法术", "药水与油参考指南")
    if potable_spells:
        process_aggregate(
            report,
            "page_1263.md",
            "法术",
            "potable_spells",
            ORG_DIR / "法术" / "药剂与毒药P&P_法术.md",
            "药剂与毒药P&P 法术",
            "## 适饮法术",
            block=strip_leading_heading(potable_spells),
        )

    # 药水与油参考指南
    reference = extract_between(text, "药水与油参考指南", None)
    if reference:
        process_aggregate(
            report,
            "page_1263.md",
            "规则",
            "potion_oil_reference",
            ORG_DIR / "规则" / "药剂与毒药P&P_规则.md",
            "药剂与毒药P&P 规则",
            "## 药水与油参考指南",
            block=strip_leading_heading(reference),
        )


def process_page_1268(report: dict, text: str) -> None:
    """施毒者/反毒药装备：拆分有位置奇物、无位置奇物与普通装备。"""
    # 跳过介绍性段落，从第一个装备开始
    first_item_idx = text.find("有效死亡之环")
    if first_item_idx == -1:
        report["warnings"].append("page_1268.md: 未找到物品起始标记")
        return
    items_text = text[first_item_idx:]

    slotted, slotless, mundane = split_page_1268_items(items_text)

    if slotted:
        process_aggregate(
            report,
            "page_1268.md",
            "装备",
            "poisoner_gear_slotted",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "药剂与毒药P&P_奇物.md",
            "药剂与毒药P&P 奇物",
            "## 药剂与毒药P&P 有位置奇物",
            block="\n\n".join(slotted),
        )
    if slotless:
        process_aggregate(
            report,
            "page_1268.md",
            "装备",
            "poisoner_gear_slotless",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "无位置" / "药剂与毒药P&P_奇物.md",
            "药剂与毒药P&P 无位置奇物",
            "## 药剂与毒药P&P 无位置奇物",
            block="\n\n".join(slotless),
        )
    if mundane:
        process_aggregate(
            report,
            "page_1268.md",
            "装备",
            "poisoner_gear_mundane",
            ORG_DIR / "装备_魔法物品" / "货品服务" / "药剂与毒药P&P_装备.md",
            "药剂与毒药P&P 装备",
            "## 药剂与毒药P&P 普通装备",
            block="\n\n".join(mundane),
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
    write_text_preserve(REPORT_PATH, "\n".join(lines))


def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 内海炼金工具箱 → 工具包
    process_aggregate(
        report,
        "page_1256.md",
        "装备",
        "inner_sea_alchemy_kits",
        ORG_DIR / "工具和技能工具包.md",
        "工具和技能工具包",
        "## 内海炼金工具箱",
    )

    # 背景特性
    process_aggregate(
        report,
        "page_1257.md",
        "背景特性",
        "brewing_poisoning_traits",
        ORG_DIR / "背景特性" / "药剂与毒药P&P_背景特性.md",
        "药剂与毒药P&P 背景特性",
        "## 制药与用毒背景",
    )

    # page_1258: 种族专长、变体、血脉
    process_page_1258(report, clean_aggregate((SRC_DIR / "page_1258.md").read_text(encoding="utf-8")))

    # page_1259: 炼金术师变体与发现
    process_page_1259(report, clean_aggregate((SRC_DIR / "page_1259.md").read_text(encoding="utf-8")))

    # page_1260: 女巫变体、巫术、法术
    process_page_1260(report, clean_aggregate((SRC_DIR / "page_1260.md").read_text(encoding="utf-8")))

    # page_1261: 盗贼变体、天赋、杀手天赋
    process_page_1261(report, clean_aggregate((SRC_DIR / "page_1261.md").read_text(encoding="utf-8")))

    # page_1262: 调查员变体、天赋
    process_page_1262(report, clean_aggregate((SRC_DIR / "page_1262.md").read_text(encoding="utf-8")))

    # page_1263: 专长、法术、参考指南
    process_page_1263(report, clean_aggregate((SRC_DIR / "page_1263.md").read_text(encoding="utf-8")))

    # page_1264: 灵药（无位置奇物）
    process_aggregate(
        report,
        "page_1264.md",
        "装备",
        "elixirs",
        ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "无位置" / "药剂与毒药P&P_奇物.md",
        "药剂与毒药P&P 无位置奇物",
        "## 灵药（Elixirs）",
    )

    # page_1265: 酊剂
    process_aggregate(
        report,
        "page_1265.md",
        "装备",
        "tinctures",
        ORG_DIR / "装备_魔法物品" / "货品服务" / "药剂与毒药P&P_酊剂.md",
        "药剂与毒药P&P 酊剂",
        "## 酊剂（Tinctures）",
    )

    # page_1266: 毒药
    process_aggregate(
        report,
        "page_1266.md",
        "装备",
        "poisons",
        ORG_DIR / "装备_魔法物品" / "货品服务" / "药剂与毒药P&P_毒药.md",
        "药剂与毒药P&P 毒药",
        "## 毒药（Poisons）",
    )

    # page_1267: 毒品
    process_aggregate(
        report,
        "page_1267.md",
        "装备",
        "drugs",
        ORG_DIR / "装备_魔法物品" / "货品服务" / "药剂与毒药P&P_毒品.md",
        "药剂与毒药P&P 毒品",
        "## 毒品（Drugs）",
    )

    # page_1268: 施毒者/反毒药装备拆分
    process_page_1268(report, clean_aggregate((SRC_DIR / "page_1268.md").read_text(encoding="utf-8")))

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
