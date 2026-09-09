#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 海洋之血（Blood of the Sea）BotS 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/海洋之血BotS
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/海洋之血BotS"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "BloodOfTheSea_reorganization_report.md"

SOURCE_BOOK = "海洋之血（Blood of the Sea）BotS"
SOURCE_BOOK_SHORT = "BotS"


# ========== 通用工具函数 ==========

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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 海洋之血BotS{l3_part}"


def make_hidden_marker(source_file: str, entry_name: str) -> str:
    return f"<!-- {SOURCE_BOOK_SHORT}-source:{source_file}:{entry_name} -->"


def remove_image_links(text: str) -> str:
    """移除 Markdown 图片链接标记（通常来自 AON 图标）。"""
    return re.sub(r"!\[.*?\]\(.*?\)", "", text)


def merge_crossline_bold(text: str) -> str:
    """合并因加粗标记跨行而断裂的标题行。"""
    lines = text.splitlines()
    merged = []
    i = 0
    title_end_re = re.compile(r"(?:】|\)\*+|\*{2,})$")
    body_prefix_re = re.compile(
        r"^(?:职业技能|先决条件|专长效果|要求|效果|类型|需求|来源|出处|出自|日常仪式|恩惠|"
        r"奖励|本职技能|武器和护甲熟练|吟游表演|通用魔法|职业技能|阵营|神圣判决|奖励语言|祝福|"
        r"灵光|施法者等级|位置|价格|重量|制造条件|制造成本|学派|等级|施法时间|成分|距离|目标|"
        r"持续时间|豁免|法术抗力|条件|代价|使用|动作|豁免|速度|属性调整|语言)"
    )

    def is_title_start(line: str) -> bool:
        s = line.strip()
        return bool(s.startswith("**") and not body_prefix_re.match(re.sub(r"^\*+", "", s)))

    while i < len(lines):
        line = lines[i]
        count = line.count("**")
        # 当前行本身已是完整标题（含结尾终止符）时，即使 ** 计数因重叠分组为奇数也直接保留。
        if count % 2 != 0 and is_title_start(line) and not title_end_re.search(line):
            j = i + 1
            buf = line
            while j < len(lines):
                nxt = lines[j]
                if nxt.strip() == "":
                    break
                if body_prefix_re.match(nxt.strip()):
                    break
                buf += " " + nxt.strip()
                count += nxt.count("**")
                if count % 2 == 0 or title_end_re.search(buf):
                    break
                if j - i >= 2:
                    break
                j += 1
            merged.append(buf)
            i = j + 1
        else:
            merged.append(line)
            i += 1
    return "\n".join(merged)


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


def strip_trailing_translator_url(block: str) -> str:
    """移除块末尾的译者链接、整理者标注或孤立 URL 行。"""
    lines = block.splitlines()
    while lines:
        last = lines[-1].strip()
        if last == "":
            lines.pop()
            continue
        if (
            last.startswith("[http")
            or last.startswith("**[http")
            or re.match(r"^https?://", last)
            or re.match(r"^\*\*\[https?://.*\]\(.*\)\*\*$", last)
            or "整理者" in last
            or "译者" in last
            or last in ("*", "**")
        ):
            lines.pop()
            continue
        break
    return "\n".join(lines)


def is_title_line(line: str, cn: str = "", en: str = "") -> bool:
    """判断一行是否为包含指定中文/英文名的标题行。"""
    s = line.strip()
    if not s:
        return False
    s = re.sub(r"^\*+", "", s)
    s = re.sub(r"^【[^】]+】\s*", "", s)
    if cn and re.match(r"^" + re.escape(cn), s):
        return True
    if not cn and en:
        if re.match(r"^" + re.escape(en) + r"\b", s):
            return True
        if re.match(r"^\(" + re.escape(en) + r"\)", s):
            return True
    return False


def is_source_or_artifact_line(line: str) -> bool:
    """判断是否为来源、页码、孤立标签等应跳过的行。"""
    s = line.strip()
    if not s:
        return True
    if s in ("**", "*"):
        return True
    if re.match(r"^\*+\s*$", s):
        return True
    if "出自" in s:
        return True
    if re.search(r"\b(?:pg|PG)\.", s):
        return True
    if re.search(r"第\s*\d+\s*页", s):
        return True
    if re.search(r"Blood of the Sea", s, re.IGNORECASE):
        return True
    if re.match(r"^\*?\*?\s*【PFS】\s*$", s):
        return True
    return False


def is_page_continuation(line: str) -> bool:
    """判断是否为跨行的页码/书名号结尾。"""
    s = line.strip()
    if re.match(r"^\d+\s*》\s*$", s):
        return True
    if re.match(r"^》\s*$", s):
        return True
    if re.match(r"^\d+\s*$", s):
        return True
    return False


def strip_block_header(block: str, cn: str = "", en: str = "") -> str:
    """移除条目块开头的标题行、来源行及孤立格式标记。"""
    lines = block.splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i < len(lines) and is_title_line(lines[i], cn, en):
        i += 1
        while i < len(lines) and (
            lines[i].strip() == "" or re.match(r"^[\s\*]+$", lines[i])
        ):
            i += 1
    while i < len(lines) and (
        is_source_or_artifact_line(lines[i]) or is_page_continuation(lines[i])
    ):
        i += 1
    return "\n".join(lines[i:])


def merge_source_lines(text: str) -> str:
    """合并跨行的来源/页码标注行，便于统一剥除。"""
    lines = text.splitlines()
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*出自", line):
            buf = line.rstrip()
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if nxt == "":
                    break
                if buf.rstrip().endswith("页") or buf.rstrip().endswith("》"):
                    break
                buf += " " + nxt
                j += 1
            merged.append(buf)
            i = j
        else:
            merged.append(line)
            i += 1
    return "\n".join(merged)


def clean_aggregate(text: str) -> str:
    """对聚合文件进行最小清理。"""
    text = text.replace("\r\n", "\n")
    text = remove_image_links(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)
    text = merge_crossline_bold(text)
    text = merge_source_lines(text)
    return text


def clean_split(text: str) -> str:
    """对需要按标题拆分的文件进行清理。"""
    text = text.replace("\r\n", "\n")
    text = remove_image_links(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)
    text = merge_crossline_bold(text)
    text = merge_source_lines(text)
    return text


# ========== 按条目列表拆分源文件 ==========

def find_entry_line_starts(
    lines: list[str], entries: list[dict], source_label: str = "条目"
) -> list[tuple[int, dict]]:
    """按行号定位每个条目的起始行。"""
    starts = []
    for entry in entries:
        cn = entry.get("cn", "")
        en = entry.get("en", "")
        found = None
        for i, line in enumerate(lines):
            if is_title_line(line, cn, en):
                found = i
                break
        if found is None:
            raise ValueError(f"无法在 {source_label} 中定位：{cn or en}")
        starts.append((found, entry))
    starts.sort(key=lambda x: x[0])
    return starts


def process_aggregate(
    report: dict,
    src_name: str,
    l3: str,
    entry_name: str,
    target_path: Path,
    target_title: str,
    heading: str,
    strip_title: tuple[str, str] = ("", ""),
) -> None:
    text = clean_aggregate((SRC_DIR / src_name).read_text(encoding="utf-8"))

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, f"# {target_title}\n\n", "\n")

    marker = make_hidden_marker(src_name, entry_name)
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append(f"{l3}已存在: {src_name}")
        return

    block = strip_trailing_artifacts(text)
    block = strip_trailing_translator_url(block)
    if strip_title[0] or strip_title[1]:
        block = strip_block_header(block, strip_title[0], strip_title[1])
    safe_append_to_file(target_path, marker, heading, make_source_annotation(src_name, l3), block)
    report["merged"].append({"type": l3, "name": target_title, "target": str(target_path.relative_to(ORG_DIR))})


def append_multi_section(
    report: dict,
    source_file: str,
    sections: list[dict],
    l3_prefix: str = "职业变体",
    tag: str = "BotS",
    preprocessed_text: str = "",
) -> None:
    src_path = SRC_DIR / source_file
    text = preprocessed_text or clean_split(src_path.read_text(encoding="utf-8"))
    lines = text.splitlines()

    starts = find_entry_line_starts(lines, sections, source_file)
    for idx, (line_idx, sec) in enumerate(starts):
        cn = sec.get("cn", "")
        en = sec.get("en", "")
        target_rel = sec.get("target")
        if not target_rel:
            report["warnings"].append(f"{source_file} 中 {cn or en} 缺少目标路径")
            continue
        target_path = ORG_DIR / target_rel
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not target_path.exists():
            write_text_preserve(target_path, f"# {target_path.stem}\n\n", "\n")

        marker = make_hidden_marker(source_file, cn or en)
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"职业选项已存在: {cn or en}")
            continue

        end_line = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        block = "\n".join(lines[line_idx:end_line])
        block = strip_trailing_artifacts(block)
        block = strip_trailing_translator_url(block)
        block = strip_block_header(block, cn, en)

        if cn and en:
            heading = f"## {cn}（{en}）【{tag}】"
        elif cn:
            heading = f"## {cn}【{tag}】"
        else:
            heading = f"## {en}【{tag}】"
        l3 = sec.get("l3", l3_prefix)
        safe_append_to_file(
            target_path,
            marker,
            heading,
            make_source_annotation(source_file, l3),
            block,
        )
        report["merged"].append({"type": l3, "name": cn or en, "target": str(target_path.relative_to(ORG_DIR))})


# ========== 1. 专长 ==========

def process_feats(report: dict) -> None:
    process_aggregate(
        report,
        "专长58.md",
        "专长",
        "__aggregate__",
        ORG_DIR / "专长" / "海洋之血BotS_专长.md",
        "海洋之血 BotS 专长",
        "## 海洋之血 BotS 专长",
    )


# ========== 2. 法术 ==========

def process_spells(report: dict) -> None:
    process_aggregate(
        report,
        "page_1060.md",
        "法术",
        "__aggregate__",
        ORG_DIR / "法术" / "海洋之血BotS_法术.md",
        "海洋之血 BotS 法术",
        "## 海洋之血 BotS 法术",
    )


# ========== 3. 魔法物品 ==========

def process_items(report: dict) -> None:
    process_aggregate(
        report,
        "page_1059.md",
        "魔法物品",
        "__aggregate__",
        ORG_DIR / "装备_魔法物品" / "海洋之血BotS_魔法物品.md",
        "海洋之血 BotS 魔法物品",
        "## 海洋之血 BotS 魔法物品",
    )


# ========== 4. 种族 ==========

def process_races(report: dict) -> None:
    process_aggregate(
        report,
        "新种族.md",
        "种族",
        "__aggregate__",
        ORG_DIR / "种族" / "海洋之血BotS_种族.md",
        "海洋之血 BotS 种族",
        "## 海洋之血 BotS 种族",
    )
    process_aggregate(
        report,
        "种族：水栖精灵.md",
        "种族",
        "水栖精灵",
        ORG_DIR / "种族" / "海洋之血BotS_种族.md",
        "海洋之血 BotS 种族",
        "## 水栖精灵（Aquatic Elves）",
        strip_title=("水栖精灵", "Aquatic Elves"),
    )


# ========== 5. 职业变体追加到既有页面 ==========

ARCHETYPE_SECTIONS = [
    {"cn": "遗迹探索者", "en": "SEEKER OF THE LOST", "source": "变体/盗贼3.md", "target": Path("职业/核心职业/盗贼/page_47.md"), "l3": "盗贼变体"},
    {"cn": "风暴驯服者", "en": "Tempest Tamer", "source": "变体/德鲁伊3.md", "target": Path("职业/核心职业/德鲁伊/page_45.md"), "l3": "德鲁伊变体"},
    {"cn": "水兽之主", "en": "Aquatic Beastmaster", "source": "变体/猎人.md", "target": Path("职业/混合职业/猎人/page_104.md"), "l3": "猎人变体"},
    {"cn": "狂澜", "en": "Crashing Wave", "source": "变体/牧师1.md", "target": Path("职业/核心职业/牧师/page_41.md"), "l3": "牧师变体"},
    {"cn": "珊瑚女巫", "en": "Coral Witch", "source": "变体/女巫2.md", "target": Path("职业/基础职业/女巫/page_70.md"), "l3": "女巫变体"},
    {"cn": "潮汐守卫", "en": "Keeper of the Current", "source": "变体/审判者3.md", "target": Path("职业/基础职业/审判者/page_78.md"), "l3": "审判者变体"},
    {"cn": "克拉肯杀手", "en": "Kraken Slayer", "source": "变体/圣武士.md", "target": Path("职业/核心职业/圣骑士/page_55.md"), "l3": "圣武士变体"},
]


def process_archetypes(report: dict) -> None:
    for sec in ARCHETYPE_SECTIONS:
        append_multi_section(report, sec["source"], [sec], sec["l3"])
    # 先知+诅咒.md 包含两个条目，需要一次拆分
    append_multi_section(
        report,
        "变体/先知+诅咒.md",
        [
            {"cn": "海洋之声", "en": "Ocean's Echo", "target": Path("职业/基础职业/先知/page_20.md"), "l3": "先知变体"},
            {"cn": "歌缚", "en": "Song-Bound", "target": Path("职业/基础职业/先知/先知诅咒全扩展.md"), "l3": "先知诅咒"},
        ],
        "职业变体",
    )


# ========== 报告与主流程 ==========

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
    process_feats(report)
    process_spells(report)
    process_items(report)
    process_races(report)
    process_archetypes(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
