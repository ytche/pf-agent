#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 异能选集（Psychic Anthology）内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/异能选集PA
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/异能选集PA"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "PsychicAnthology_reorganization_report.md"

SOURCE_BOOK = "异能选集（Psychic Anthology）"
SOURCE_BOOK_SHORT = "异能选集PA"


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
    return re.sub(r"!?\[.*?\]\(.*?\)", "", text)


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


def split_by_heading(text: str, markers: list[tuple[str, str]]) -> dict[str, str]:
    """按连续标记切分文本。

    markers: [(entry_name, marker_text), ...]，按出现顺序。
    返回 {entry_name: block, ...}，未匹配到 marker 的 entry 值为空字符串。
    """
    text = clean_aggregate(text)
    # 构建 positions
    positions: list[tuple[int, str, str]] = []
    for entry_name, marker_text in markers:
        for m in re.finditer(re.escape(marker_text), text):
            positions.append((m.start(), entry_name, marker_text))
    # 按位置排序，同名只取第一次出现
    positions.sort(key=lambda x: x[0])
    seen: set[str] = set()
    unique_positions: list[tuple[int, str, str]] = []
    for pos, entry_name, marker_text in positions:
        if entry_name in seen:
            continue
        seen.add(entry_name)
        unique_positions.append((pos, entry_name, marker_text))

    # 从文本开头作为第一个隐式起点
    starts = [(0, "__start__", "")] + unique_positions
    result: dict[str, str] = {name: "" for name, _ in markers}
    for i, (pos, entry_name, _) in enumerate(starts):
        if entry_name == "__start__":
            continue
        start = starts[i - 1][0]
        block = text[start:pos].strip()
        # 将前一段归属给前一个 marker（除了第一个块归给第一个 marker）
        prev_name = starts[i - 1][1]
        if prev_name == "__start__":
            result[entry_name] = block
        else:
            # 前一段追加到前一个 marker
            result[prev_name] = result.get(prev_name, "") + "\n\n" + block if result.get(prev_name, "") else block
    # 最后一段追加到最后一个 marker
    if unique_positions:
        last_pos, last_name, _ = unique_positions[-1]
        tail = text[last_pos:].strip()
        result[last_name] = result.get(last_name, "") + "\n\n" + tail if result.get(last_name, "") else tail
    return result


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

    # 1. 心能代谢腐化（独立规则）
    process_aggregate(
        report,
        "page_1023.md",
        "规则",
        "psychometabolic_corruption",
        ORG_DIR / "规则" / "异能选集PA_心能代谢腐化.md",
        "异能选集PA 心能代谢腐化",
        "## 异能选集PA 心能代谢腐化",
    )

    # 2. 灵态百科（唤魂师：情感羁绊 + 变体）
    page_722_text = (SRC_DIR / "page_722.md").read_text(encoding="utf-8")
    parts_722 = split_by_heading(page_722_text, [
        ("emotional_focus", "仁慈（Kindness，魅影情感羁绊）"),
        ("archetypes", "唤魂师变体"),
    ])
    if parts_722.get("emotional_focus"):
        process_aggregate(
            report,
            "page_722.md",
            "职业选项 → 唤魂师 → 魅影情感羁绊",
            "emotional_focus",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "唤魂师" / "异能选集PA_魅影情感羁绊.md",
            "异能选集PA 魅影情感羁绊",
            "## 异能选集PA 魅影情感羁绊",
            block=parts_722["emotional_focus"],
        )
    if parts_722.get("archetypes"):
        process_aggregate(
            report,
            "page_722.md",
            "职业选项 → 唤魂师 → 变体",
            "archetypes",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "唤魂师" / "异能选集PA_变体.md",
            "异能选集PA 唤魂师变体",
            "## 异能选集PA 唤魂师变体",
            block=parts_722["archetypes"],
        )

    # 3. 失落奥秘骸骨（秘学士：灵器套装 + 变体）
    page_727_text = (SRC_DIR / "page_727.md").read_text(encoding="utf-8")
    parts_727 = split_by_heading(page_727_text, [
        ("panoplies", "灵器套装（Panoplies）"),
        ("archetype", "灵装专家（Panoply savant）（秘学士变体）"),
    ])
    if parts_727.get("panoplies"):
        process_aggregate(
            report,
            "page_727.md",
            "职业选项 → 秘学士 → 灵器套装",
            "panoplies",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "秘学士" / "异能选集PA_灵器套装.md",
            "异能选集PA 灵器套装",
            "## 异能选集PA 灵器套装",
            block=parts_727["panoplies"],
        )
    if parts_727.get("archetype"):
        process_aggregate(
            report,
            "page_727.md",
            "职业选项 → 秘学士 → 变体",
            "archetype",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "秘学士" / "异能选集PA_变体.md",
            "异能选集PA 秘学士变体",
            "## 异能选集PA 秘学士变体",
            block=parts_727["archetype"],
        )

    # 4. 万象众界全典（通灵者变体）
    process_aggregate(
        report,
        "page_724.md",
        "职业选项 → 通灵者 → 变体",
        "outer_channeler",
        ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "通灵者" / "异能选集PA_变体.md",
        "异能选集PA 通灵者变体",
        "## 异能选集PA 通灵者变体",
    )

    # 5. 奥利瓦罗小品曲集（催眠师专长 + 变体）
    page_725_text = (SRC_DIR / "page_725.md").read_text(encoding="utf-8")
    parts_725 = split_by_heading(page_725_text, [
        ("feats", "专长"),
        ("archetypes", "催眠师变体"),
    ])
    if parts_725.get("feats"):
        process_aggregate(
            report,
            "page_725.md",
            "专长",
            "mesmerist_feats",
            ORG_DIR / "专长" / "异能选集PA_专长.md",
            "异能选集PA 专长",
            "## 异能选集PA 催眠师专长",
            block=parts_725["feats"],
        )
    if parts_725.get("archetypes"):
        process_aggregate(
            report,
            "page_725.md",
            "职业选项 → 催眠师 → 变体",
            "archetypes",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "催眠师" / "异能选集PA_变体.md",
            "异能选集PA 催眠师变体",
            "## 异能选集PA 催眠师变体",
            block=parts_725["archetypes"],
        )

    # 6. 无限卷轴（魔法物品 + 法术）
    page_723_text = (SRC_DIR / "page_723.md").read_text(encoding="utf-8")
    parts_723 = split_by_heading(page_723_text, [
        ("magic_items", "魔法物品"),
        ("spells", "法术"),
    ])
    if parts_723.get("magic_items"):
        process_aggregate(
            report,
            "page_723.md",
            "装备/物品 → 魔法物品",
            "magic_items",
            ORG_DIR / "装备_魔法物品" / "异能选集PA_魔法物品.md",
            "异能选集PA 魔法物品",
            "## 异能选集PA 魔法物品",
            block=parts_723["magic_items"],
        )
    if parts_723.get("spells"):
        process_aggregate(
            report,
            "page_723.md",
            "法术",
            "spells",
            ORG_DIR / "法术" / "异能选集PA_法术.md",
            "异能选集PA 法术",
            "## 异能选集PA 法术",
            block=parts_723["spells"],
        )

    # 7. 回溯万花筒（操念使注能 + 通用原力 + 专长 + 变体）
    page_726_text = (SRC_DIR / "page_726.md").read_text(encoding="utf-8")
    parts_726 = split_by_heading(page_726_text, [
        ("infusions", "念袭和注能"),
        ("wild_talents", "通用原力"),
        ("feats", "专长"),
        ("archetype", "念力骑士（Kinetic"),
    ])
    if parts_726.get("infusions"):
        process_aggregate(
            report,
            "page_726.md",
            "职业选项 → 操念使 → 注能",
            "infusions",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "操念使" / "异能选集PA_注能.md",
            "异能选集PA 操念使注能",
            "## 异能选集PA 操念使注能",
            block=parts_726["infusions"],
        )
    if parts_726.get("wild_talents"):
        process_aggregate(
            report,
            "page_726.md",
            "职业选项 → 操念使 → 通用原力",
            "wild_talents",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "操念使" / "异能选集PA_通用原力.md",
            "异能选集PA 操念使通用原力",
            "## 异能选集PA 操念使通用原力",
            block=parts_726["wild_talents"],
        )
    if parts_726.get("feats"):
        process_aggregate(
            report,
            "page_726.md",
            "专长",
            "kineticist_feats",
            ORG_DIR / "专长" / "异能选集PA_专长.md",
            "异能选集PA 专长",
            "## 异能选集PA 操念使专长",
            block=parts_726["feats"],
        )
    if parts_726.get("archetype"):
        process_aggregate(
            report,
            "page_726.md",
            "职业选项 → 操念使 → 变体",
            "kinetic_knight",
            ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "操念使" / "异能选集PA_变体.md",
            "异能选集PA 操念使变体",
            "## 异能选集PA 操念使变体",
            block=parts_726["archetype"],
        )

    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
