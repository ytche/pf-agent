#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 神术选集（Divine Anthology）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/神术选集DA
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/神术选集DA"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "DivineAnthology_reorganization_report.md"

SOURCE_BOOK = "神术选集（Divine Anthology）"
SOURCE_BOOK_SHORT = "神术选集DA"


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


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


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


def mark_existing_file(
    report: dict,
    src_name: str,
    l3: str,
    entry_name: str,
    target_path: Path,
) -> None:
    """对已经存在且内容完整的目标文件仅补充隐藏来源标记，避免重复追加内容。"""
    marker = make_hidden_marker(src_name, entry_name)
    if not target_path.exists():
        report["warnings"].append(f"目标文件不存在，无法补标记: {target_path}")
        return
    content = target_path.read_text(encoding="utf-8")
    if marker in content:
        report["skipped"].append(f"{l3}已存在标记: {src_name}:{entry_name}")
        return
    le = detect_line_ending(target_path)
    # 在文件第一行之后插入标记和来源说明
    lines = content.splitlines()
    insert_idx = 1 if lines and lines[0].startswith("#") else 0
    annotation = make_source_annotation(src_name, l3)
    new_lines = (
        lines[:insert_idx]
        + ([""] if insert_idx > 0 else [])
        + [marker, annotation, ""]
        + lines[insert_idx:]
    )
    target_path.write_text(le.join(new_lines), encoding="utf-8")
    report["merged"].append({"type": l3, "name": str(target_path), "target": str(target_path.relative_to(ORG_DIR))})


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

def split_subdomains(text: str) -> list[tuple[str, str]]:
    """拆分 page_1215.md 中的牧师子域。

    每个子域以 `[**中文名** English Name](url)` 开头。
    """
    text = clean_aggregate(text)
    # 按两个以上空行切分
    blocks = re.split(r"\n\s*\n\s*\n", text)
    items: list[tuple[str, str]] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # 提取标题：[**中文名** English Name](url) 或 **中文名** English Name
        m = re.match(r"^\[\*\*([^*]+?)\*\*\s+([^\]]+?)\]\([^)]+\)", block)
        if not m:
            m = re.match(r"^\*\*([^*]+?)\*\*\s+([^\n]+)", block)
        if not m:
            continue
        cn_name = re.sub(r"\s+", " ", m.group(1).strip())
        en_name = re.sub(r"\s+", " ", m.group(2).strip())
        title = f"## {cn_name}（{en_name}）"
        # 去掉标题行与 **Source** *Divine Anthology pg. N* 来源行（可能跨行）
        body = re.sub(
            r"^\[\*\*[^*]+?\*\*\s+[^\]]+?\]\([^)]+?\)(?:\*\*Source\*\*\s*\*[^*]+?\*\s*)?",
            "",
            block,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        body = _collapse_blank_lines(body.strip())
        items.append((cn_name, f"{title}\n\n{body}"))
    return items


def split_traits(text: str) -> tuple[str, str] | None:
    """返回 背景特性5.md 的清理后全文块。

    该文件来源/译者段落穿插、特性格式多样，整体作为一块聚合，保留内部子结构。
    """
    text = clean_aggregate(text)
    # 移除残留的译者/URL 说明段落（以 http 或"译者"开头的孤立行）
    lines = text.splitlines()
    cleaned: list[str] = []
    for ln in lines:
        stripped = ln.strip()
        if re.match(r"^\[?https?://", stripped) and "(" in stripped:
            continue
        if stripped.startswith("译者") or stripped.startswith("译者："):
            continue
        cleaned.append(ln)
    text = "\n".join(cleaned)
    # 将 --- 分隔符统一换成空行
    text = re.sub(r"\n\s*---\s*\n", "\n\n", text)
    text = _collapse_blank_lines(text.strip())
    if not text:
        return None
    return ("background_traits", text)


def split_feats(text: str) -> list[tuple[str, str]]:
    """拆分 专长5.md 中的专长。

    每个专长以 中文名\nENGLISH NAME（可能跨行）开头，字段以"先决条件："、"好处："标注。
    """
    text = clean_aggregate(text)
    # 去掉"专长"文件头说明
    text = re.sub(r"^专长\s*\n", "", text)
    text = re.sub(r"^《[^》]+》包含了.*?\n\n", "", text, flags=re.DOTALL)
    # 按空行切分
    blocks = re.split(r"\n\s*\n", text.strip())
    items: list[tuple[str, str]] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        cn_name = lines[0].strip()
        # 英文名称可能跨多行（全大写）
        en_lines: list[str] = []
        desc_start = 1
        for i in range(1, len(lines)):
            if re.match(r"^[A-Z][A-Z\s'’]*$", lines[i].strip()):
                en_lines.append(lines[i].strip())
                desc_start = i + 1
            else:
                break
        if not en_lines:
            continue
        en_name = " ".join(en_lines)
        title = f"## {cn_name}（{en_name}）"
        body_lines = lines[desc_start:]
        # 规范化字段标签
        body = "\n".join(body_lines)
        body = re.sub(r"^(先决条件|好处)：", r"**\1**：", body, flags=re.MULTILINE)
        body = _collapse_blank_lines(body.strip())
        items.append((cn_name, f"{title}\n\n{body}"))
    return items


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    report: dict = {"merged": [], "skipped": [], "warnings": []}

    # 1. 牧师子域
    subdomain_items = split_subdomains((SRC_DIR / "page_1215.md").read_text(encoding="utf-8"))
    if subdomain_items:
        process_aggregate(
            report,
            "page_1215.md",
            "职业选项 → 牧师",
            "cleric_subdomains",
            ORG_DIR / "职业" / "核心职业" / "牧师" / "神术选集DA_牧师子域.md",
            "神术选集DA 牧师子域",
            "## 神术选集DA 牧师子域",
            block="\n\n".join(block for _, block in subdomain_items),
        )

    # 2. 背景特性
    trait_result = split_traits((SRC_DIR / "背景特性5.md").read_text(encoding="utf-8"))
    if trait_result:
        _, trait_block = trait_result
        process_aggregate(
            report,
            "背景特性5.md",
            "背景特性",
            "background_traits",
            ORG_DIR / "背景特性" / "神术选集DA_背景特性.md",
            "神术选集DA 背景特性",
            "## 神术选集DA 背景特性",
            block=trait_block,
        )

    # 3. 专长
    feat_items = split_feats((SRC_DIR / "专长5.md").read_text(encoding="utf-8"))
    if feat_items:
        process_aggregate(
            report,
            "专长5.md",
            "专长",
            "feats",
            ORG_DIR / "专长" / "神术选集DA_专长.md",
            "神术选集DA 专长",
            "## 神术选集DA 专长",
            block="\n\n".join(block for _, block in feat_items),
        )

    # 4. 圣武士守则补充（目标文件已存在，仅补标记）
    paladin_target = ORG_DIR / "圣武士守则补充.md"
    if paladin_target.exists():
        mark_existing_file(
            report,
            "圣武士守则补充.md",
            "职业选项 → 圣武士",
            "paladin_codes",
            paladin_target,
        )
    else:
        # 若不存在则按普通聚合处理
        process_aggregate(
            report,
            "圣武士守则补充.md",
            "职业选项 → 圣武士",
            "paladin_codes",
            paladin_target,
            "神术选集DA 圣武士守则补充",
            "## 神术选集DA 圣武士守则补充",
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
