#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 阴影血脉（Blood of Shadows）BoS 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/阴影血脉
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/阴影血脉"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "BloodOfShadows_reorganization_report.md"

SOURCE_BOOK = "阴影血脉（Blood of Shadows）BoS"
SOURCE_BOOK_SHORT = "BoS"


def write_text_preserve(path: Path, text: str, line_ending: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\n", line_ending), encoding="utf-8")


def read_text_preserve(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    line_ending = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8"), line_ending


def detect_line_ending(path: Path) -> str:
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 4096))
        tail = f.read()
    if b"\r\n" in tail:
        return "\r\n"
    return "\n"


def safe_append_to_file(path: Path, marker: str, heading: str, source_annotation: str, block: str) -> None:
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
        if len(content) >= len(le.encode("utf-8")) * 2 and content.endswith((le * 2).encode("utf-8")):
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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 阴影血脉BoS{l3_part}"


def make_hidden_marker(source_file: str, entry_name: str) -> str:
    return f"<!-- {SOURCE_BOOK_SHORT}-source:{source_file}:{entry_name} -->"


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


def strip_trailing_artifacts(block: str) -> str:
    lines = block.splitlines()
    while lines and (lines[-1].strip() == "" or re.match(r"^\*+$", lines[-1].strip())):
        lines.pop()
    return "\n".join(lines)


# ========== 1. 专长 ==========

FEATS = [
    {"cn": "黄昏兜帽", "en": "Crepuscular Cowl"},
    {"cn": "强化暗影抗力", "en": "Improved Shadowy Resistance"},
    {"cn": "阴影法术防御", "en": "Shadow Magic Defense"},
    {"cn": "剪影人预言者", "en": "Wayang Soothsayer"},
    {"cn": "额外忍术", "en": "Extra Ninja Trick"},
]


def find_feat_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for feat in FEATS:
        # 标题可能紧跟在前一条描述的 ** 之后，因此前置边界放宽为行首、空白或 *
        pattern = re.compile(
            r"(?:^|(?<=[\s*]))" + re.escape(feat["cn"]) + r"(?:\s*\*)*(?:（[^）]+）)?",
        )
        m = pattern.search(text)
        if not m:
            raise ValueError(f"无法在 page_378.md 中定位专长：{feat['cn']}（{feat['en']}）")
        starts.append((m.start(), feat))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_feat_title(block: str, feat: dict) -> str:
    cn = re.escape(feat["cn"])
    en = r"\s*".join(re.escape(word) for word in feat["en"].split())
    # 标题结构多样：**中文名（English）****、中文名（English）**、中文名 English 等
    en_group = r"(?:[（(]" + en + r"(?:\([^)]+\))?[）)])?"
    pattern = re.compile(
        r"^\s*(?:\*+)?" + cn + r"(?:\s*\*+)?" + en_group + r"\s*(?:\*+)?",
        re.DOTALL,
    )
    m = pattern.search(block)
    if m:
        return block[m.end():].strip()
    return block


def truncate_at_index_list(block: str) -> str:
    """page_378.md 末尾有一个仅包含英文专长名的索引表，需截断。"""
    # 索引表以单独的 **** 行开始，随后是 **Blinded Blade Style... 等
    idx = re.search(r"\n\s*\*{4,}\s*\n\s*\n\s*\*\*Blinded", block)
    if idx:
        return block[:idx.start()].strip()
    return block


def process_page378_feats(report: dict) -> None:
    src_path = SRC_DIR / "page_378.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "专长" / "阴影血脉BoS_专长.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 阴影血脉 BoS 专长\n\n", "\n")

    starts = find_feat_starts(text)
    l3 = "专长"
    for idx, (start_pos, feat) in enumerate(starts):
        marker = make_hidden_marker("page_378.md", feat["cn"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"专长已存在: {feat['cn']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = truncate_at_index_list(block)
        block = strip_trailing_artifacts(block)
        block = strip_feat_title(block, feat)
        heading = f"## {feat['cn']}（{feat['en']}）"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("page_378.md", l3), block)
        report["merged"].append({"type": "专长", "name": feat["cn"], "target": str(target_path.relative_to(ORG_DIR))})


FETCHLING_FEATS = [
    {"cn": "额外光与暗", "en": "Extra Light and Dark"},
]


def find_fetchling_feat_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for feat in FETCHLING_FEATS:
        pattern = re.compile(r"(?:^|(?<=[。\n\r]))\s*" + re.escape(feat["cn"]))
        m = pattern.search(text)
        if not m:
            raise ValueError(f"无法在 page_388.md 中定位专长：{feat['cn']}（{feat['en']}）")
        starts.append((m.start(), feat))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_fetchling_feat_title(block: str, feat: dict) -> str:
    cn = re.escape(feat["cn"])
    en = r"\s*".join(re.escape(word) for word in feat["en"].split())
    pattern = re.compile(
        r"^\s*" + cn + r"\s*[（(]" + en + r"[）)]\s*",
        re.DOTALL,
    )
    m = pattern.search(block)
    if m:
        return block[m.end():].strip()
    return block


def truncate_fetchling_feat_block(block: str) -> str:
    """额外光与暗之后是重复的剪影人预言家，截断。"""
    idx = re.search(r"\n\s*剪影人预言家\s*[（(]Wayang", block)
    if idx:
        return block[:idx.start()].strip()
    return block


def process_page388_fetchling_feats(report: dict) -> None:
    """page_388.md 末尾的剪影人专长；剪影人预言者与 page_378 重复，跳过。"""
    src_path = SRC_DIR / "种族特性" / "page_388.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    # 只取「剪影人专长」段落之后的内容
    section_start = text.find("剪影人专长")
    if section_start == -1:
        report["warnings"].append("page_388.md 未找到『剪影人专长』段落")
        return
    section_text = text[section_start:]

    target_path = ORG_DIR / "专长" / "阴影血脉BoS_专长.md"
    starts = find_fetchling_feat_starts(section_text)
    l3 = "专长"
    for idx, (start_pos, feat) in enumerate(starts):
        marker = make_hidden_marker("page_388.md", feat["cn"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"专长已存在: {feat['cn']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(section_text)
        block = section_text[start_pos:end_pos]
        block = truncate_fetchling_feat_block(block)
        block = strip_trailing_artifacts(block)
        block = strip_fetchling_feat_title(block, feat)
        heading = f"## {feat['cn']}（{feat['en']}）"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("种族特性/page_388.md", l3), block)
        report["merged"].append({"type": "专长", "name": feat["cn"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 2. 法术 ==========


def process_spells(report: dict) -> None:
    src_path = SRC_DIR / "page_383.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "法术" / "阴影血脉BoS_法术.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 阴影血脉 BoS 法术\n\n", "\n")

    marker = make_hidden_marker("page_383.md", "返初溯源")
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("法术已存在: 返初溯源")
        return

    # 去除开头的「剪影人法术：」说明句，避免重复标题
    block = re.sub(r"^\s*剪影人法术：\s*\n?\s*", "", text).strip()
    heading = "## 返初溯源（First World Revisions）"
    safe_append_to_file(target_path, marker, heading, make_source_annotation("page_383.md", "法术"), block)
    report["merged"].append({"type": "法术", "name": "返初溯源", "target": str(target_path.relative_to(ORG_DIR))})


# ========== 3. 魔法物品与纹身 ==========


def process_magic_items(report: dict) -> None:
    src_path = SRC_DIR / "page_384.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "装备_魔法物品" / "阴影血脉BoS_物品.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 阴影血脉 BoS 物品\n\n", "\n")

    items = [
        ("迷幻刺青", "Mesmerizing Tattoo"),
        ("影缘刺青", "Penumbra Tattoo"),
        ("旋烟刺青", "Swirling Smoke Tattoo"),
        ("忠诚提灯", "Faithful Lantern"),
    ]

    # 按中文标题切分条目
    starts = []
    for cn, en in items:
        en_pattern = r"\s*".join(re.escape(word) for word in en.split())
        pattern = re.compile(r"(?:^|(?<=[\n\r]))\s*" + re.escape(cn) + r"\s*" + en_pattern, re.IGNORECASE)
        m = pattern.search(text)
        if not m:
            raise ValueError(f"无法在 page_384.md 中定位物品：{cn}（{en}）")
        starts.append((m.start(), cn, en))
    starts.sort(key=lambda x: x[0])

    for idx, (start_pos, cn, en) in enumerate(starts):
        marker = make_hidden_marker("page_384.md", cn)
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"物品已存在: {cn}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        # 去掉标题行
        en_pattern = r"\s*".join(re.escape(word) for word in en.split())
        block = re.sub(r"^\s*" + re.escape(cn) + r"\s*" + en_pattern + r"\s*", "", block, flags=re.IGNORECASE).strip()
        heading = f"## {cn}（{en}）"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("page_384.md", "魔法物品"), block)
        report["merged"].append({"type": "魔法物品", "name": cn, "target": str(target_path.relative_to(ORG_DIR))})


# ========== 4. 武器附魔 ==========


def process_weapon_enchants(report: dict) -> None:
    src_path = SRC_DIR / "武器附魔6.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "装备_魔法物品" / "武器附魔" / "阴影血脉BoS_武器附魔.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 阴影血脉 BoS 武器附魔\n\n", "\n")

    enchants = [
        ("影射", "Shadowshooting"),
        ("耀光", "Beaming"),
    ]

    starts = []
    for cn, en in enchants:
        en_pattern = r"\s*".join(re.escape(word) for word in en.split())
        pattern = re.compile(
            r"(?:^|[\s*（(])" + re.escape(cn) + r"\s*[（(]?" + en_pattern + r"[）)]?",
            re.IGNORECASE,
        )
        m = pattern.search(text)
        if not m:
            raise ValueError(f"无法在 武器附魔6.md 中定位武器附魔：{cn}（{en}）")
        starts.append((m.start(), cn, en))
    starts.sort(key=lambda x: x[0])

    for idx, (start_pos, cn, en) in enumerate(starts):
        marker = make_hidden_marker("武器附魔6.md", cn)
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"武器附魔已存在: {cn}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        en_pattern = r"\s*".join(re.escape(word) for word in en.split())
        block = re.sub(r"^\s*" + re.escape(cn) + r"\s*[（(]?" + en_pattern + r"[）)]?\s*", "", block, flags=re.IGNORECASE).strip()
        heading = f"## {cn}（{en}）"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("武器附魔6.md", "武器附魔"), block)
        report["merged"].append({"type": "武器附魔", "name": cn, "target": str(target_path.relative_to(ORG_DIR))})


# ========== 5. 职业变体与职业选项 ==========

CLASS_OPTIONS = [
    {
        "file": "page_1234.md",
        "cn": "幽影化学家",
        "en": "Gloom Chymist",
        "class": "炼金术师",
        "target": ORG_DIR / "职业" / "基础职业" / "炼金术师" / "page_71.md",
        "kind": "变体与科研发现",
    },
    {
        "file": "page_1618.md",
        "cn": "阴影子域",
        "en": "Shadow Subdomain",
        "class": "牧师",
        "target": ORG_DIR / "职业" / "核心职业" / "牧师" / "page_42.md",
        "kind": "牧师子域",
    },
    {
        "file": "page_381.md",
        "cn": "阴影行者",
        "en": "Shadow Walker",
        "class": "盗贼",
        "target": ORG_DIR / "职业" / "核心职业" / "盗贼" / "page_47.md",
        "kind": "盗贼变体",
    },
    {
        "file": "page_382.md",
        "cn": "阴影幻灵",
        "en": "Shadow Eidolon",
        "class": "召唤师",
        "target": ORG_DIR / "职业" / "基础职业" / "召唤师" / "page_1346.md",
        "kind": "幻灵亚种",
    },
    {
        "file": "page_496.md",
        "cn": "阴影",
        "en": "Shadow",
        "class": "先知",
        "target": ORG_DIR / "职业" / "基础职业" / "先知" / "page_88.md",
        "kind": "先知秘示域",
    },
    {
        "file": "圣骑士1.md",
        "cn": "薄暮骑士",
        "en": "Dusk Knight",
        "class": "圣武士",
        "target": ORG_DIR / "职业" / "核心职业" / "圣骑士" / "page_55.md",
        "kind": "圣武士变体",
    },
    {
        "file": "术士.md",
        "cn": "暗影后裔",
        "en": "Umbral Scions",
        "class": "术士",
        "target": ORG_DIR / "职业" / "核心职业" / "术士" / "page_24.md",
        "kind": "术士变体",
    },
    {
        "file": "血脉狂怒者血脉.md",
        "cn": "阴影",
        "en": "Shadow",
        "class": "血脉狂怒者",
        "target": ORG_DIR / "职业" / "混合职业" / "血脉狂怒者" / "page_104.md",
        "kind": "血脉狂怒者血脉",
    },
]


def find_class_option_start(text: str, entry: dict) -> re.Match | None:
    """允许标题无加粗、英文名跨行，且同一行开头可能有 PFS 等前缀标注。"""
    cn = re.escape(entry["cn"])
    en = r"\s*".join(re.escape(word) for word in entry["en"].split())
    patterns = [
        re.compile(re.escape(entry["cn"]) + r"\s*[（(]" + en + r"[）)]", re.DOTALL),
        re.compile(re.escape(entry["cn"]) + r"\s*" + en, re.DOTALL),
        re.compile(re.escape(entry["cn"]) + r"\s*[【\[]", re.DOTALL),
        re.compile(re.escape(entry["cn"])),
    ]
    for pattern in patterns:
        m = pattern.search(text)
        if m:
            return m
    return None


def strip_class_option_title(block: str, entry: dict) -> str:
    cn = re.escape(entry["cn"])
    en = r"\s+".join(re.escape(word) for word in entry["en"].split())
    patterns = [
        re.compile(r"^\s*\*?\*?" + cn + r"\s*[（(]" + en + r"[）)]\s*[【\[][^\]】]+[】\]]?\s*", re.DOTALL),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*[（(]" + en + r"[）)]\s*", re.DOTALL),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*" + en + r"\s*", re.DOTALL),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*[【\[][^\]】]+[】\]]?\s*", re.DOTALL),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*", re.DOTALL),
    ]
    for pattern in patterns:
        m = pattern.search(block)
        if m:
            return block[m.end():].strip()
    return block


def process_single_class_option(report: dict, entry: dict) -> None:
    src_path = SRC_DIR / "变体_职业选项" / entry["file"]
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = entry["target"]
    marker = make_hidden_marker(f"变体_职业选项/{entry['file']}", entry["cn"])
    existing = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    if marker in existing:
        report["skipped"].append(f"{entry['kind']}已存在: {entry['class']} {entry['cn']}")
        return

    m = find_class_option_start(text, entry)
    if not m:
        raise ValueError(f"无法在 {entry['file']} 中定位条目：{entry['cn']}（{entry['en']}）")

    block = text[m.start():]
    block = strip_trailing_artifacts(block)
    block = strip_class_option_title(block, entry)
    heading = f"## {entry['cn']}（{entry['en']}）【{entry['class']}{entry['kind']}】"
    l3 = f"变体/职业选项 → {entry['class']}"
    safe_append_to_file(target_path, marker, heading, make_source_annotation(f"变体_职业选项/{entry['file']}", l3), block)
    report["merged"].append({"type": entry["kind"], "name": entry["cn"], "target": str(target_path.relative_to(ORG_DIR))})


def process_class_options(report: dict) -> None:
    for entry in CLASS_OPTIONS:
        process_single_class_option(report, entry)


def process_rogue_talents(report: dict) -> None:
    """盗贼天赋与高等盗贼天赋整体追加到盗贼天赋主列表。"""
    src_path = SRC_DIR / "变体_职业选项" / "page_380.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "职业" / "核心职业" / "盗贼" / "page_62.md"
    marker = make_hidden_marker("变体_职业选项/page_380.md", "盗贼天赋")
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("盗贼天赋已存在: page_380.md 阴影血脉盗贼天赋")
        return

    block = strip_trailing_artifacts(text)
    heading = "## 阴影血脉 BoS 盗贼天赋与高等盗贼天赋"
    l3 = "变体/职业选项 → 盗贼"
    safe_append_to_file(target_path, marker, heading, make_source_annotation("变体_职业选项/page_380.md", l3), block)
    report["merged"].append({"type": "盗贼天赋", "name": "阴影血脉 BoS 盗贼天赋", "target": str(target_path.relative_to(ORG_DIR))})


# ========== 6. 种族特性 ==========


def process_race_traits(report: dict) -> None:
    """影生/暗生、窃影鬼、剪影人种族特性分别聚合到源书文件。"""
    race_files = [
        ("种族特性/page_386.md", "影生暗生种族特性", "种族/阴影血脉BoS_影生暗生种族特性.md", "影生/暗生种族特性"),
        ("种族特性/page_387.md", "窃影鬼", "种族/罕见种族/阴影血脉BoS_窃影鬼.md", "窃影鬼种族特性"),
        ("种族特性/page_388.md", "剪影人", "种族/罕见种族/阴影血脉BoS_剪影人.md", "剪影人种族特性"),
    ]

    for source_file, name, target_rel, l3 in race_files:
        src_path = SRC_DIR / source_file
        text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        text = merge_crossline_bold(text)
        text = clean_translator_url(text)
        text = clean_leading_image(text).strip()

        # page_388.md 末尾的「剪影人专长」段落已拆分到专长文件，
        # 聚合种族特性时应截断，避免与专长文件重复。
        if source_file == "种族特性/page_388.md":
            cutoff = text.find("剪影人专长")
            if cutoff != -1:
                text = text[:cutoff].strip()

        target_path = ORG_DIR / target_rel
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not target_path.exists():
            write_text_preserve(target_path, f"# 阴影血脉 BoS {name}\n\n", "\n")

        marker = make_hidden_marker(source_file, "__aggregate__")
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"种族特性聚合已存在: {name}")
            continue

        heading = f"## {name}"
        safe_append_to_file(target_path, marker, heading, make_source_annotation(source_file, l3), text)
        report["merged"].append({"type": "种族特性", "name": name, "target": str(target_path.relative_to(ORG_DIR))})


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
    process_page378_feats(report)
    process_page388_fetchling_feats(report)
    process_spells(report)
    process_magic_items(report)
    process_weapon_enchants(report)
    process_class_options(report)
    process_rogue_talents(report)
    process_race_traits(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
