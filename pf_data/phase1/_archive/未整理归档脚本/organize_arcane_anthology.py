#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 秘术选集（Arcane Anthology）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/秘术选集Arcane Anthology
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/秘术选集Arcane Anthology"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "ArcaneAnthology_reorganization_report.md"

SOURCE_BOOK = "秘术选集（Arcane Anthology）"
SOURCE_BOOK_SHORT = "秘术选集ArcaneAnthology"


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
    ):
        lines.pop()
    return "\n".join(lines)


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


# ---------------------------------------------------------------------------
# 条目拆分
# ---------------------------------------------------------------------------

def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


def _make_title_from_name(name: str) -> str:
    name = name.strip()
    if "（" in name and name.endswith("）"):
        return f"## {name}"
    return f"## {name}"


def split_archetypes(text: str) -> list[tuple[str, str]]:
    """拆分 page_750.md 中的职业变体。

    标题格式：**中文名 EnglishName（职业变体）**
    """
    text = clean_aggregate(text)
    pattern = re.compile(r"^\*\*([^*]+?)（([^）]+变体)）\s*\*\*", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return []

    items: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        title_body = re.sub(r"\s+", " ", m.group(1).strip())
        variant_type = m.group(2).strip()
        title = f"## {title_body}【{variant_type}】"
        # 去掉标题行本身
        body = re.sub(r"^\*\*[^*]+?（[^）]+变体）\s*\*\*\s*", "", block, count=1)
        body = _collapse_blank_lines(body.strip())
        items.append((title_body.split()[0], f"{title}\n\n{body}"))
    return items


def split_traits(text: str) -> list[tuple[str, str]]:
    """拆分 背景特性41.md 中的背景特性。

    每个特性以 **中文名** 开头，包含 **类别** 行。
    """
    text = clean_aggregate(text)
    # 按两个以上空行切分特性块
    blocks = re.split(r"\n\s*\n\s*\n", text)
    items: list[tuple[str, str]] = []
    for block in blocks:
        block = block.strip()
        if "**类别**" not in block:
            continue
        lines = block.splitlines()
        # 收集类别行之前的所有粗体片段（先合并再提取，处理跨行英文名称）
        cat_idx = 0
        for idx, ln in enumerate(lines):
            if "**类别**" in ln:
                cat_idx = idx
                break
        pre_cat_text = " ".join(lines[:cat_idx])
        bold_parts: list[str] = []
        for mm in re.finditer(r"\*\*([^*]+?)\*\*", pre_cat_text):
            part = mm.group(1).strip()
            if not part:
                continue
            # 过滤来源、页码、PFS 说明等杂质
            if re.search(r"来源|Arcane Anthology|pg\.?|PFS不可|PFS不可用", part, re.IGNORECASE):
                continue
            bold_parts.append(part)

        if not bold_parts:
            continue
        cn_name = re.sub(r"\s+", " ", bold_parts[0])
        en_name = re.sub(r"\s+", " ", bold_parts[1]) if len(bold_parts) > 1 else ""
        if en_name and re.match(r"^[A-Za-z]", en_name):
            title = f"## {cn_name}（{en_name}）"
        else:
            title = f"## {cn_name}"
        body = "\n".join(lines[cat_idx:])
        body = _collapse_blank_lines(body.strip())
        items.append((cn_name, f"{title}\n\n{body}"))
    return items


def split_discoveries(text: str) -> list[tuple[str, str]]:
    """拆分 科研发现1.md 中的科研发现。

    标题格式：**名称（English Name, Su）** 或 **名称（English Name）**
    """
    text = clean_aggregate(text)
    # 标题格式：**名称（English Name, Su）** 或 **名称（English Name） **（后带空格）
    pattern = re.compile(r"^\*\*([^*]+?（[^）]+）)\s*\*\*", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return []

    items: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        # 第一个发现前通常有关于"圣油"的总述，一起归入首个条目
        start = 0 if i == 0 else m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        title_body = re.sub(r"\s+", " ", m.group(1).strip())
        title = f"## {title_body}"
        body = re.sub(r"^\*\*[^*]+?（[^）]+）\s*\*\*\s*", "", block, count=1)
        # 去掉可能附带的"出自《奥术选集》..."来源行（含跨行）
        body_lines = body.splitlines()
        i = 0
        while i < len(body_lines):
            ln = body_lines[i].strip()
            if not ln:
                i += 1
                continue
            if re.search(r"出自|Arcane Anthology|pg\.", ln, re.IGNORECASE):
                i += 1
                # 继续移除同属一条来源说明的续行
                while i < len(body_lines):
                    next_ln = body_lines[i].strip()
                    if not next_ln:
                        i += 1
                        continue
                    if len(next_ln) < 40 and (
                        next_ln.endswith("）")
                        or next_ln.endswith(")")
                        or next_ln.endswith("**")
                    ):
                        i += 1
                        continue
                    break
                continue
            break
        body_lines = body_lines[i:]
        body = _collapse_blank_lines("\n".join(body_lines).strip())
        items.append((title_body.split("（")[0], f"{title}\n\n{body}"))
    return items


def split_feats(text: str) -> list[tuple[str, str]]:
    """拆分 专长56.md 中的专长。

    专长以 PFS 图标链接开头，后接名称（English Name）〔标签〕；图标被 clean_aggregate 移除后
    无法按空行切分，因此先按原图标链接切分，再取每个专长所在段落。
    """
    text = text.replace("\r\n", "\n")
    text = clean_translator_url(text)
    # 保留原图标链接作为分隔符，避免 clean_aggregate 将其移除
    segments = re.split(r"!?\[.*?\]\(.*?\)\s*", text)
    items: list[tuple[str, str]] = []
    for seg in segments[1:]:  # 跳过文件头说明（第一段）
        seg = seg.strip()
        if not seg:
            continue
        # 一个图标分段里可能混有《箭歌的哀伤》之类的说明段落，只取第一个自然段
        para = re.split(r"\n\s*\n", seg)[0]
        para = para.strip()
        # 把跨行的名称与正文合并到同一行
        collapsed = re.sub(r"(?<!\n)\n(?!\n)", " ", para)
        collapsed = re.sub(r"\s+", " ", collapsed)
        m = re.match(r"^(.+?（[^）]+）(?:〔[^〕]+〕)?)\s*", collapsed)
        if not m:
            continue
        title_body = re.sub(r"\s+", " ", m.group(1).strip())
        title = f"## {title_body}"
        body = collapsed[m.end():].strip()
        # 清理专长描述前的星号强调残留
        body = re.sub(r"^\*+\s*", "", body)
        # 将 '* 先决条件**' / '* **先决条件**' 类残留规范为独立字段行
        body = re.sub(r"(\S)\*\s*(先决条件|专长效果|特殊说明|好处|前提)\*\*\s*：?", r"\1\n\n**\2**：", body)
        body = re.sub(r"(\S)\s*\*\s*(\*\*(?:先决条件|专长效果|特殊说明|好处|前提)\*\*)", r"\1\n\n\2", body)
        # 去掉末尾未闭合的星号
        body = re.sub(r"\s*\*+\s*$", "", body)
        items.append((title_body.split("（")[0], f"{title}\n\n{body}"))
    return items


def split_prayer_meditation(text: str) -> str:
    """返回 祈祷书与冥想书.md 的清理后全文块。"""
    text = clean_aggregate(text)
    # 修复跨行的标题格式
    text = re.sub(
        r"\*\*法术书预置仪式（SPELLBOOK\s+PREPARATION\s+RITUALS）\s*",
        "## 法术书预置仪式（SPELLBOOK PREPARATION RITUALS）\n\n",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"\*\*祈祷书与冥想书\*\*\s*Arcane\s+Anthology\s*\n\s*祈祷书和冥想书仪式。",
        "## 祈祷书与冥想书\n\n",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = _collapse_blank_lines(text.strip())
    return text


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 职业变体
    archetype_items = split_archetypes((SRC_DIR / "page_750.md").read_text(encoding="utf-8"))
    if archetype_items:
        process_aggregate(
            report,
            "page_750.md",
            "职业变体",
            "class_archetypes",
            ORG_DIR / "职业" / "秘术选集ArcaneAnthology_变体.md",
            "秘术选集ArcaneAnthology 职业变体",
            "## 秘术选集ArcaneAnthology 职业变体",
            block="\n\n".join(block for _, block in archetype_items),
        )

    # 2. 背景特性
    trait_items = split_traits((SRC_DIR / "背景特性41.md").read_text(encoding="utf-8"))
    if trait_items:
        process_aggregate(
            report,
            "背景特性41.md",
            "背景特性",
            "background_traits",
            ORG_DIR / "背景特性" / "秘术选集ArcaneAnthology_背景特性.md",
            "秘术选集ArcaneAnthology 背景特性",
            "## 秘术选集ArcaneAnthology 背景特性",
            block="\n\n".join(block for _, block in trait_items),
        )

    # 3. 科研发现
    discovery_items = split_discoveries((SRC_DIR / "科研发现1.md").read_text(encoding="utf-8"))
    if discovery_items:
        process_aggregate(
            report,
            "科研发现1.md",
            "变体/职业选项 → 炼金术师",
            "alchemist_discoveries",
            ORG_DIR / "职业" / "基础职业" / "炼金术师" / "秘术选集ArcaneAnthology_科研发现.md",
            "秘术选集ArcaneAnthology 科研发现",
            "## 秘术选集ArcaneAnthology 科研发现",
            block="\n\n".join(block for _, block in discovery_items),
        )

    # 4. 祈祷书与冥想书规则
    prayer_block = split_prayer_meditation((SRC_DIR / "祈祷书与冥想书.md").read_text(encoding="utf-8"))
    if prayer_block:
        process_aggregate(
            report,
            "祈祷书与冥想书.md",
            "规则",
            "prayer_meditation_books",
            ORG_DIR / "规则" / "秘术选集ArcaneAnthology_祈祷书与冥想书.md",
            "秘术选集ArcaneAnthology 祈祷书与冥想书",
            "## 秘术选集ArcaneAnthology 祈祷书与冥想书",
            block=prayer_block,
        )

    # 5. 专长
    feat_items = split_feats((SRC_DIR / "专长56.md").read_text(encoding="utf-8"))
    if feat_items:
        process_aggregate(
            report,
            "专长56.md",
            "专长",
            "feats",
            ORG_DIR / "专长" / "秘术选集ArcaneAnthology_专长.md",
            "秘术选集ArcaneAnthology 专长",
            "## 秘术选集ArcaneAnthology 专长",
            block="\n\n".join(block for _, block in feat_items),
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
