#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
整理 构装体手册CH (Construct Handbook) 从 pf_rules_md/未整理/构装体手册CH
到 pf_rules_md_organized/ 对应目录。
"""

import json
import re
from pathlib import Path
from datetime import datetime

# 基础路径
BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/构装体手册CH"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_DIR = BASE  # 报告文件放在 phase1 根目录

SOURCE_BOOK = "构装体手册（Construct Handbook）CH"
SOURCE_BOOK_SHORT = "CH"


def normalize_to_nl(text: str, target_nl: str) -> str:
    """将文本归一化到目标换行风格。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if target_nl == "\r\n":
        text = text.replace("\n", "\r\n")
    return text


def detect_nl(path: Path) -> str:
    """检测文件换行风格。"""
    if not path.exists():
        return "\n"
    raw = path.read_bytes()
    return "\r\n" if b"\r\n" in raw else "\n"


def read_text_preserve(path: Path) -> tuple[str, str]:
    """读取文件并保留换行风格。"""
    nl = detect_nl(path)
    if not path.exists():
        return "", nl
    return path.read_text(encoding="utf-8"), nl


def write_text_preserve(path: Path, text: str, nl: str) -> None:
    """按指定换行风格写入文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = normalize_to_nl(text, nl)
    path.write_bytes(text.encode("utf-8"))


def append_to_file(path: Path, content: str) -> None:
    """追加内容到文件，保持目标文件换行风格。"""
    existing, nl = read_text_preserve(path)
    if existing and not existing.endswith("\n") and not existing.endswith("\r\n"):
        existing += nl
    elif existing and not (existing.endswith("\n") or existing.endswith("\r\n")):
        existing += nl
    new_content = existing + content
    write_text_preserve(path, new_content, nl)


def clean_translator_url(text: str) -> str:
    """移除顶部的译者论坛链接。"""
    lines = text.splitlines()
    # 移除开头的空行和 http 链接行
    while lines and (not lines[0].strip() or lines[0].strip().startswith("http") or lines[0].strip().startswith("译者")):
        lines.pop(0)
    return "\n".join(lines)


def merge_crossline_bold(text: str) -> str:
    """合并跨行加粗标题，例如 **标题\nEnglish**。"""
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


def split_by_hr(text: str) -> list[str]:
    """按 `---` 分隔块拆分，清理每块。"""
    blocks = re.split(r"\n\s*---\s*\n", text)
    result = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # 移除顶部的译者链接行
        block = clean_translator_url(block)
        if block:
            result.append(block)
    return result


def make_source_annotation(source_file: str, l3: str = "") -> str:
    l3_part = f" → {l3}" if l3 else ""
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 构装体手册CH{l3_part}"


def make_hidden_marker(source_file: str, entry_name: str) -> str:
    return f"<!-- {SOURCE_BOOK_SHORT}-source:{source_file}:{entry_name} -->"


# ========== 1. 职业变体 ==========

ARCHETYPES = [
    {
        "name": "野性肖像",
        "english": "Wild Effigy",
        "class": "变形者",
        "marker": "**野性肖像（Wild Effigy）〔变形者变体〕",
        "source_file": "page_1619.md",
        "l3": "变体/职业选项",
    },
    {
        "name": "构装体召唤者",
        "english": "Construct Caller",
        "class": "Unchained召唤师",
        "marker": "**构装体召唤者（Construct Caller）",
        "source_file": "page_1619.md",
        "l3": "变体/职业选项",
    },
    {
        "name": "鲜血学家",
        "english": "Cruorchymist",
        "class": "炼金术士",
        "marker": "**鲜血学家（炼金术士变体） Cruorchymist",
        "source_file": "page_1619.md",
        "l3": "变体/职业选项",
    },
    {
        "name": "发条工匠",
        "english": "Clocksmith",
        "class": "法师",
        "marker": "**发条工匠（法师变体）Clocksmith",
        "source_file": "page_1619.md",
        "l3": "变体/职业选项",
    },
    {
        "name": "奥能修补匠",
        "english": "Arcane Tinkerer",
        "class": "奥能师",
        "marker": "**奥能修补匠 Arcane Tinkerer（奥能师变体）",
        "source_file": "page_1619.md",
        "l3": "变体/职业选项",
    },
    {
        "name": "构装收集者",
        "english": "Construct Collector",
        "class": "秘学士",
        "marker": "**构装收集者 Construct Collector（秘学士变体）",
        "source_file": "page_1619.md",
        "l3": "变体/职业选项",
    },
    {
        "name": "构装拆解者",
        "english": "Construct Saboteur",
        "class": "盗贼",
        "marker": "**构装拆解者（盗贼变体） Construct Saboteur",
        "source_file": "page_1619.md",
        "l3": "变体/职业选项",
    },
    {
        "name": "工程师",
        "english": "Engineer",
        "class": "调查员",
        "marker": "**工程师（调查员变体）Engineer",
        "source_file": "page_1619.md",
        "l3": "变体/职业选项",
    },
    {
        "name": "铸父寻者",
        "english": "Forgefather's Seeker",
        "class": "圣武士",
        "marker": "**铸父寻者（圣武士变体）Forgefather's Seeker",
        "source_file": "page_1619.md",
        "l3": "变体/职业选项",
    },
    {
        "name": "拾荒者",
        "english": "Scrapper",
        "class": "战士",
        "marker": "**拾荒者（战士变体）Scrapper",
        "source_file": "page_1619.md",
        "l3": "变体/职业选项",
    },
    {
        "name": "布莱之声",
        "english": "Voice of Brigh",
        "class": "吟游诗人",
        "marker": "布莱之声（Voice of Brigh）［吟游诗人变体］",
        "source_file": "page_1619.md",
        "l3": "变体/职业选项",
    },
]


def process_archetypes(report: dict) -> None:
    src_path = SRC_DIR / "page_1619.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_crossline_bold(text)
    target_path = ORG_DIR / "职业" / "构装体手册CH_变体.md"

    blocks = split_by_hr(text)
    if not target_path.exists():
        write_text_preserve(target_path, f"# {SOURCE_BOOK} 职业变体\n\n", "\n")

    existing, _ = read_text_preserve(target_path)
    for arc in ARCHETYPES:
        # 按中文名查找所属的块
        block = None
        for b in blocks:
            if arc["name"] in b:
                block = b
                break
        if block is None:
            report["warnings"].append(f"未找到变体块: {arc['name']}")
            continue
        marker = make_hidden_marker(arc["source_file"], arc["name"])
        if marker in existing:
            report["skipped"].append(f"变体已存在: {arc['name']}")
            continue
        entry = (
            f"\n{marker}\n"
            f"## {arc['name']}（{arc['english']}）〔{arc['class']}变体〕\n"
            f"{make_source_annotation(arc['source_file'], arc['l3'])}\n"
            f"{block}\n\n"
        )
        append_to_file(target_path, entry)
        report["merged"].append({
            "type": "变体",
            "name": arc["name"],
            "target": str(target_path.relative_to(ORG_DIR)),
        })


# ========== 2. 构装体模板 ==========

TEMPLATES = [
    {
        "name": "先锋构装",
        "english": "Commando Construct",
        "marker": "**创建先锋构装****COMMANDO CONSTRUCT",
    },
    {
        "name": "注能魔像",
        "english": "Energized Golem",
        "marker": "**创建注能魔像****ENERGIZED GOLEM",
    },
    {
        "name": "启迪构装",
        "english": "Enlightened Construct",
        "marker": "**创建启迪构装****ENLIGHTENED CONSTRUCT",
    },
    {
        "name": "回收构装体",
        "english": "Recycled Construct",
        "marker": "**创建回收构装体（Creating a Recycled Construct）",
    },
]


def process_templates(report: dict) -> None:
    src_path = SRC_DIR / "构装体模板.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_crossline_bold(text)
    target_path = ORG_DIR / "规则" / "构装体手册CH_模板.md"

    blocks = split_by_hr(text)
    if not target_path.exists():
        write_text_preserve(target_path, f"# {SOURCE_BOOK} 构装体模板\n\n", "\n")

    existing, _ = read_text_preserve(target_path)
    for tpl in TEMPLATES:
        block = None
        for b in blocks:
            if tpl["name"] in b:
                block = b
                break
        if block is None:
            report["warnings"].append(f"未找到模板块: {tpl['name']}")
            continue
        marker = make_hidden_marker("构装体模板.md", tpl["name"])
        if marker in existing:
            report["skipped"].append(f"模板已存在: {tpl['name']}")
            continue
        entry = (
            f"\n{marker}\n"
            f"## {tpl['name']}（{tpl['english']}）\n"
            f"{make_source_annotation('构装体模板.md', '构装体模板')}\n"
            f"{block}\n\n"
        )
        append_to_file(target_path, entry)
        report["merged"].append({
            "type": "模板",
            "name": tpl["name"],
            "target": str(target_path.relative_to(ORG_DIR)),
        })


# ========== 3. 魔法物品 ==========

ITEMS = [
    {
        "name": "灵导械核心",
        "english": "Automaton Core",
        "marker": "**灵导械核心（Automaton Core）**",
    },
    {
        "name": "奇鲁根魔方",
        "english": "Chirurgeon Cube",
        "marker": "**【PFS】奇鲁根魔方（Chirurgeon Cube）**",
    },
    {
        "name": "控制之冠",
        "english": "Diadem of Control",
        "marker": "**【PFS】控制之冠（Diadem of Control）**",
    },
    {
        "name": "活力软膏",
        "english": "Energizing Salve",
        "marker": "**【PFS】活力软膏（Energizing Salve）**",
    },
    {
        "name": "魔像手册",
        "english": "Golem Manuals",
        "marker": "**魔像手册（Golem Manuals）**",
    },
    {
        "name": "械灾之油",
        "english": "Machinebane Oil",
        "marker": "**【PFS】械灾之油（Machinebane Oil）**",
    },
    {
        "name": "构装体厌恶项链",
        "english": "Necklace of Construct Aversion",
        "marker": "**【PFS】构装体厌恶项链（Necklace of Construct Aversion）**",
    },
    {
        "name": "磁怒之眼",
        "english": "Oculus of Magnetic Fury",
        "marker": "**【PFS】磁怒之眼（Oculus of Magnetic Fury）**",
    },
    {
        "name": "抑制宝石",
        "english": "Suppression Gem",
        "marker": "**抑制宝石（Suppression Gem）**",
    },
]


def process_items(report: dict) -> None:
    src_path = SRC_DIR / "魔法物品8.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_crossline_bold(text)
    target_path = ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "无位置" / "构装体手册CH_物品.md"

    # 用正则定位每个物品标题行（按中文名即可）
    positions = []
    for it in ITEMS:
        # 匹配以 ** 开头、包含该物品中文名、且带有英文括号的行
        pattern = re.compile(
            r"^\*\*[^*]*?" + re.escape(it["name"]) + r"[^*]*?\*\*$",
            re.MULTILINE,
        )
        m = pattern.search(text)
        if m is None:
            report["warnings"].append(f"未找到物品标题: {it['name']}")
            continue
        positions.append((m.start(), it))

    positions.sort()

    if not target_path.exists():
        write_text_preserve(target_path, f"# {SOURCE_BOOK} 奇物\n\n", "\n")

    existing, _ = read_text_preserve(target_path)
    for idx, (start, it) in enumerate(positions):
        end = positions[idx + 1][0] if idx + 1 < len(positions) else len(text)
        section = text[start:end].strip()
        # 移除图片标签
        section = re.sub(r"!\[\[图片\]\]\([^)]+\)", "", section)
        marker = make_hidden_marker("魔法物品8.md", it["name"])
        if marker in existing:
            report["skipped"].append(f"物品已存在: {it['name']}")
            continue
        entry = (
            f"\n{marker}\n"
            f"## {it['name']}（{it['english']}）\n"
            f"{make_source_annotation('魔法物品8.md', '魔法物品')}\n"
            f"{section}\n\n"
        )
        append_to_file(target_path, entry)
        report["merged"].append({
            "type": "物品",
            "name": it["name"],
            "target": str(target_path.relative_to(ORG_DIR)),
        })


# ========== 4. page_1614 灵导械生态与规则 ==========

def process_page_1614(report: dict) -> None:
    """page_1614 主要是灵导械怪物条目与背景描述，规则部分已在魔法物品8中处理。
    本文件作为背景/规则参考，合并到独立的源书聚合规则文件中。"""
    src_path = SRC_DIR / "page_1614.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_crossline_bold(text)
    target_path = ORG_DIR / "规则" / "构装体手册CH_灵导械背景.md"

    # 仅保留规则相关段落：灵导械核心规则描述与构装体特征
    # 由于全文混杂怪物数据卡与背景故事，整文件作为背景归档
    if not target_path.exists():
        write_text_preserve(target_path, f"# {SOURCE_BOOK} 灵导械背景\n\n", "\n")

    existing, _ = read_text_preserve(target_path)
    marker = make_hidden_marker("page_1614.md", "灵导械背景")
    if marker in existing:
        report["skipped"].append("page_1614 背景已存在")
        return

    section = clean_translator_url(text)
    entry = (
        f"\n{marker}\n"
        f"## 灵导械背景与核心规则\n"
        f"{make_source_annotation('page_1614.md', '灵导械')}\n"
        f"{section}\n\n"
    )
    append_to_file(target_path, entry)
    report["merged"].append({
        "type": "背景规则",
        "name": "灵导械背景与核心规则",
        "target": str(target_path.relative_to(ORG_DIR)),
    })


# ========== 报告与计划 ==========

def write_report(report: dict) -> None:
    report_path = REPORT_DIR / "CH_reorganization_report.md"
    plan_path = REPORT_DIR / "CH_reorganization_plan.json"

    lines = [
        f"# {SOURCE_BOOK} 整理报告",
        "",
        f"生成时间：{datetime.now().isoformat()}",
        "",
        "## 整理内容",
        "",
    ]
    for m in report["merged"]:
        lines.append(f"- **{m['type']}**：{m['name']} → `{m['target']}`")
    lines += ["", "## 跳过项", ""]
    for s in report["skipped"]:
        lines.append(f"- {s}")
    lines += ["", "## 警告", ""]
    for w in report["warnings"]:
        lines.append(f"- {w}")
    lines += ["", "## 备注", ""]
    lines.append("- page_1614.md 中的 `灵导械核心` 与 `魔法物品8.md` 重复，规则条目以 `魔法物品8.md` 为准。")
    lines.append("- `pf_rules_md_organized/构装体模板.md` 与 `未整理/构装体手册CH/构装体模板.md` 内容重复，已记录到重复记录文档。")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    plan_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    report = {
        "source_book": SOURCE_BOOK,
        "timestamp": datetime.now().isoformat(),
        "merged": [],
        "skipped": [],
        "warnings": [],
    }
    process_archetypes(report)
    process_templates(report)
    process_items(report)
    process_page_1614(report)
    write_report(report)

    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")
    if report["warnings"]:
        for w in report["warnings"]:
            print(f"  警告: {w}")


if __name__ == "__main__":
    main()
