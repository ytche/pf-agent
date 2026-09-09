#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 冒险者的军械库2（Adventurer's Armory 2）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/冒险者的军械库2
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/冒险者的军械库2"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "AdventurersArmory2_reorganization_report.md"

SOURCE_BOOK = "冒险者的军械库2（Adventurer's Armory 2）"
SOURCE_BOOK_SHORT = "冒险者的军械库2"


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
    while lines and (
        lines[-1].strip() == ""
        or re.match(r"^\*+$", lines[-1].strip())
        or re.match(r"^\|", lines[-1].strip())
        or re.match(r"^\|?\s*---", lines[-1].strip())
    ):
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


ITEM_FIELD_LABELS = {
    "出处", "类型", "类别", "价格", "重量", "灵光", "ＣＬ", "CL", "施法者等级",
    "栏位", "位置", "效果", "描述", "制作", "制造", "制造DC", "制作条件",
    "制作成本", "制造成本", "制造要求", "灵氲",
}

_FIELD_KEYWORDS = [
    "出自", "价格", "重量", "类型", "类别", "描述", "效果", "制造", "制作",
    "出处", "灵光", "栏位", "位置", "CL", "施法者等级", "制造DC", "制造要求",
    "制作条件", "制作成本", "制造成本",
]

# 用于把无标签属性拆成字段行的关键字，避免在正文中误拆分
_SPLIT_KEYWORDS = sorted(
    [k for k in _FIELD_KEYWORDS if k not in {"效果"}],
    key=len,
    reverse=True,
)

_SOURCE_ONLY_RE = re.compile(
    r"^\s*(?:\*+)?\s*(?:"
    r"出自[：:]?|"
    r"《[^》]+》[，,]?|"
    r".*?Adventurer'?s\s+Armory.*?"
    r"|.*?pg\.\s*\d+.*?"
    r"|.*?p\.\s*\d+.*?"
    r"|.*?\d+\s*页[》）]?"
    r")\s*(?:\*+)?\s*$",
    re.IGNORECASE,
)


def is_item_field_line(line: str) -> bool:
    """判断是否为物品属性字段行（如 **类型**：xxx）。"""
    stripped = line.strip()
    m = re.match(r"^\*\*(.+?)(?:[：:])?\*\*", stripped)
    if not m:
        return False
    return m.group(1) in ITEM_FIELD_LABELS


def is_source_only_line(line: str) -> bool:
    if is_item_field_line(line):
        return False
    return bool(_SOURCE_ONLY_RE.match(line.strip()))


def strip_leading_source_prefix(line: str) -> str:
    """如果一行以'出自'开头且后面紧跟字段标签，去掉出处部分。"""
    stripped = line.strip()
    if not re.match(r"^出自[：:]?", stripped):
        return line
    field_label_re = "|".join(re.escape(k) for k in _FIELD_KEYWORDS if k != "出自")
    m = re.search(r"^出自.*?(?=\*\*(?:" + field_label_re + r")[：:]?\*\*)", stripped)
    if m:
        return stripped[m.end():].lstrip()
    return ""


def normalize_leading_fields(lines: list[str]) -> list[str]:
    """把标题行残留的无标签属性（如'价格 50 GP'）转换成标准字段行。"""
    if not lines:
        return lines
    first_field_idx = next((i for i, ln in enumerate(lines) if is_item_field_line(ln)), None)
    if first_field_idx == 0:
        return lines
    core_attr = set(_FIELD_KEYWORDS) - {"描述", "效果"}
    if first_field_idx is None:
        # 没有标准字段行时，收集开头的属性行
        prefix: list[str] = []
        i = 0
        while i < len(lines):
            ln = lines[i]
            stripped = ln.strip()
            if stripped == "":
                i += 1
                continue
            has_attr = any(kw in stripped for kw in _FIELD_KEYWORDS)
            is_short = len(stripped) <= 10
            if not has_attr and not is_short:
                break
            # 过长的行只有在包含核心属性关键字时才视为属性行
            if len(stripped) > 60 and not any(kw in stripped for kw in core_attr):
                break
            # 单独的关键字行（如“描述”）如果后面紧跟长正文，则把正文一起纳入该字段的值
            if stripped in _FIELD_KEYWORDS or re.match(r"^(?:" + "|".join(re.escape(k) for k in _FIELD_KEYWORDS) + r")[：:]?$", stripped):
                next_idx = next((j for j in range(i + 1, len(lines)) if lines[j].strip()), None)
                if next_idx is not None:
                    next_stripped = lines[next_idx].strip()
                    if len(next_stripped) > 10 and not any(kw in next_stripped for kw in core_attr):
                        prefix.append(ln)
                        prefix.append(lines[next_idx])
                        i = next_idx + 1
                        break
            prefix.append(ln)
            i += 1
        rest = lines[i:]
    else:
        prefix = lines[:first_field_idx]
        rest = lines[first_field_idx:]
    text = " ".join(ln.strip() for ln in prefix)
    if not any(kw in text for kw in _SPLIT_KEYWORDS):
        return lines
    pattern = "(" + "|".join(re.escape(k) for k in _SPLIT_KEYWORDS) + r")(?:[：:]?)"
    parts = re.split(pattern, text)
    result: list[str] = []
    i = 0
    if i < len(parts) and not any(kw in parts[i] for kw in _SPLIT_KEYWORDS):
        i += 1
    while i < len(parts):
        kw = parts[i].strip()
        i += 1
        val = parts[i].strip() if i < len(parts) else ""
        i += 1
        result.append(f"**{kw}**：{val}")
    return result + rest


def strip_item_title(block: str) -> str:
    """移除物品块首的标题与出处说明，保留属性字段。"""
    lines = block.splitlines()

    # 处理表格行：把整行表格内容合并成第一个单元格
    if lines and lines[0].strip().startswith("|"):
        row_parts: list[str] = []
        while lines and not re.match(r"^\|?\s*---", lines[0].strip()) and lines[0].strip() != "":
            row_parts.append(lines[0].strip().lstrip("|"))
            lines.pop(0)
        while lines and (lines[0].strip() == "" or re.match(r"^\|?\s*---", lines[0].strip())):
            lines.pop(0)
        joined = " ".join(row_parts)
        cell = joined.split("|")[0].strip()
        lines = [cell] + lines

    # 去掉前置空行
    while lines and lines[0].strip() == "":
        lines = lines[1:]

    # 去掉 Markdown 链接包裹的标题行
    if lines and re.match(r"^\[(\*\*.*?\*\*)\]\(.*?\)\s*$", lines[0].strip()):
        lines = lines[1:]
        while lines and lines[0].strip() == "":
            lines = lines[1:]

    # 去掉第一行的加粗标题
    if lines:
        first = lines[0].strip()
        if first.startswith("**"):
            # 去掉尾部的 Markdown 链接后缀，如 **标题**](url)
            lines[0] = re.sub(r"\]\(.*?\)\s*$", "", lines[0])
            first = lines[0].strip()
            m = re.match(r"^\*\*[^*]+?\*\*", first)
            if m:
                rest = first[m.end():].strip()
                lines[0] = rest
            else:
                # 标题跨行
                lines = lines[1:]
                while (
                    lines
                    and lines[0].strip() != ""
                    and not is_item_field_line(lines[0])
                    and not any(kw in lines[0] for kw in _FIELD_KEYWORDS)
                ):
                    lines = lines[1:]
        elif not first.startswith("|"):
            # 无加粗的标题行，若下一行是字段或出处则删除
            if len(lines) > 1 and (is_source_only_line(lines[1]) or is_item_field_line(lines[1])):
                lines = lines[1:]

    # 去掉第一行里残留的“出自...”前缀
    if lines:
        cleaned = strip_leading_source_prefix(lines[0])
        lines[0] = cleaned

    # 去掉剩余的出处-only 行与空行
    while lines and (lines[0].strip() == "" or is_source_only_line(lines[0])):
        lines = lines[1:]

    # 规范化残留的属性行
    lines = normalize_leading_fields(lines)

    # 清理表格分隔符与孤立的 '|'
    lines = [ln for ln in lines if not re.match(r"^\s*\|\s*$", ln.strip()) and not re.match(r"^\|?\s*---", ln.strip())]
    while lines and lines[0].strip() == "":
        lines = lines[1:]

    # 清理行尾残留的表格单元分隔符
    lines = [re.sub(r"(\s*\|)+\s*$", "", ln) for ln in lines]

    return "\n".join(lines).strip()


def split_items_14(text: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """将 物品14.md 拆分为有位置奇物、无位置奇物、炼金物品与普通装备。

    返回 (slotted_blocks, slotless_blocks, alchemical_blocks, mundane_blocks)
    """
    item_names = [
        "吉荼木之怒", "临时力量手套", "忍者服", "铠装磁铁", "长发酊",
        "弹簧卷轴匣", "盗贼训练工具", "手术果冻", "姬图姆之忿",
    ]

    positions: list[tuple[int, str]] = []
    for name in item_names:
        idx = text.find(f"**{name}")
        if idx == -1:
            idx = text.find(name)
        if idx != -1:
            positions.append((idx, name))
    positions.sort()

    items: list[tuple[str, str]] = []
    for i, (start, name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        block = text[start:end].strip()
        lines = block.splitlines()
        cleaned_lines = [ln for ln in lines if not re.match(r"^\|?\s*---", ln.strip())]
        block = "\n".join(cleaned_lines).strip()
        block = strip_item_title(block)
        if block:
            block = f"## {name}\n\n{block}"
            items.append((name, block))

    slotted: list[str] = []
    slotless: list[str] = []
    alchemical: list[str] = []
    mundane: list[str] = []
    for name, block in items:
        # 有位置奇物
        if re.search(r"(?:栏位|位置)[：:\*]*\s*[一-龥a-zA-Z]+", block):
            slotted.append(block)
        # 无位置奇物
        elif re.search(r"(?:栏位|位置|类型|类别)[：:\*]*\s*.*?无", block):
            slotless.append(block)
        # 炼金物品
        elif re.search(r"(?:类型|类别)[：:\*]*\s*.*?炼金", block):
            alchemical.append(block)
        else:
            mundane.append(block)
    return slotted, slotless, alchemical, mundane


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
        "专长27.md",
        "专长",
        "feats",
        ORG_DIR / "专长" / "冒险者的军械库2_专长.md",
        "冒险者的军械库2 专长",
        "## 冒险者的军械库2 专长",
    )

    # 拓展临时武器属性规则
    process_aggregate(
        report,
        "拓展临时武器属性.md",
        "规则",
        "expanded_improvised_weapons",
        ORG_DIR / "规则" / "冒险者的军械库2_规则.md",
        "冒险者的军械库2 规则",
        "## 拓展临时武器属性",
    )

    # 制造人偶规则
    process_aggregate(
        report,
        "制造人偶.md",
        "规则",
        "poppet_construction",
        ORG_DIR / "规则" / "冒险者的军械库2_规则.md",
        "冒险者的军械库2 规则",
        "## 制造人偶",
    )

    # 物品拆分
    items_text = clean_aggregate((SRC_DIR / "物品14.md").read_text(encoding="utf-8"))
    slotted, slotless, alchemical, mundane = split_items_14(items_text)

    if slotted:
        process_aggregate(
            report,
            "物品14.md",
            "装备",
            "slotted_wondrous",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "冒险者的军械库2_奇物.md",
            "冒险者的军械库2 奇物",
            "## 冒险者的军械库2 有位置奇物",
            block="\n\n".join(slotted),
        )
    if slotless:
        process_aggregate(
            report,
            "物品14.md",
            "装备",
            "slotless_wondrous",
            ORG_DIR / "装备_魔法物品" / "魔法物品" / "奇物" / "无位置" / "冒险者的军械库2_奇物.md",
            "冒险者的军械库2 无位置奇物",
            "## 冒险者的军械库2 无位置奇物",
            block="\n\n".join(slotless),
        )
    if alchemical:
        process_aggregate(
            report,
            "物品14.md",
            "装备",
            "alchemical_items",
            ORG_DIR / "装备_魔法物品" / "货品服务" / "冒险者的军械库2_炼金物品.md",
            "冒险者的军械库2 炼金物品",
            "## 冒险者的军械库2 炼金物品",
            block="\n\n".join(alchemical),
        )
    if mundane:
        process_aggregate(
            report,
            "物品14.md",
            "装备",
            "mundane_gear",
            ORG_DIR / "装备_魔法物品" / "货品服务" / "冒险者的军械库2_装备.md",
            "冒险者的军械库2 装备",
            "## 冒险者的军械库2 普通装备",
            block="\n\n".join(mundane),
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()