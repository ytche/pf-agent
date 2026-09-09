#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 野兽血脉（Blood of the Beast）BotB 内容到已有分类目录。

源目录：pf_data/phase1/pf_rules_md/未整理/野兽血脉BotB
目标目录：pf_data/phase1/pf_rules_md_organized/
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/野兽血脉BotB"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_PATH = BASE / "BloodOfTheBeast_reorganization_report.md"

SOURCE_BOOK = "野兽血脉（Blood of the Beast）BotB"
SOURCE_BOOK_SHORT = "BotB"


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
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 野兽血脉BotB{l3_part}"


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


# ========== 1. 职业变体 from page_697.md ==========

CLASS_VARIANTS = [
    {"cn": "九尾裔", "en": "Nine-tailed heir", "class": "术士", "target": ORG_DIR / "职业" / "核心职业" / "术士" / "page_24.md", "kind": "变体"},
    {"cn": "主母之牙", "en": "First mother's fang", "class": "骑士", "target": ORG_DIR / "职业" / "核心职业" / "骑士" / "page_51.md", "kind": "变体"},
    {"cn": "寻运行者", "en": "Fortune-finder", "class": "游侠", "target": ORG_DIR / "职业" / "核心职业" / "游侠" / "page_49.md", "kind": "变体"},
    {"cn": "疾行快剑", "en": "Courser", "class": "游荡剑客", "target": ORG_DIR / "职业" / "基础职业" / "游荡剑客" / "page_72.md", "kind": "变体"},
    {"cn": "噬厄巫觋", "en": "Jinx witch", "class": "女巫", "target": ORG_DIR / "职业" / "基础职业" / "女巫" / "page_78.md", "kind": "变体"},
    {"cn": "红舌", "en": "Red tongue", "class": "歌者", "target": ORG_DIR / "职业" / "混合职业" / "歌者" / "page_106.md", "kind": "变体"},
    {"cn": "狩魔猎手", "en": "Ravener hunter", "class": "审判者", "target": ORG_DIR / "职业" / "基础职业" / "审判者" / "page_82.md", "kind": "变体"},
    {"cn": "绝境巡行者", "en": "Prowler at world's end", "class": "血脉狂怒者", "target": ORG_DIR / "职业" / "混合职业" / "血脉狂怒者" / "page_104.md", "kind": "变体"},
    {"cn": "机缘萨满", "en": "Serendipity shaman", "class": "萨满", "target": ORG_DIR / "职业" / "基础职业" / "萨满" / "page_90.md", "kind": "变体"},
    {"cn": "孽生腐主", "en": "Swarm mongers", "class": "德鲁伊", "target": ORG_DIR / "职业" / "核心职业" / "德鲁伊" / "page_40.md", "kind": "变体"},
    {"cn": "巧技斗士", "en": "Opportunist", "class": "战士", "target": ORG_DIR / "职业" / "核心职业" / "战士" / "page_44.md", "kind": "变体"},
    {"cn": "拾荒技师", "en": "Scavenger", "class": "调查员", "target": ORG_DIR / "职业" / "混合职业" / "调查员" / "page_100.md", "kind": "变体"},
    {"cn": "人柱力", "en": "Fiend keeper", "class": "通灵者", "target": ORG_DIR / "职业" / "基础职业" / "通灵者" / "page_92.md", "kind": "变体"},
    {"cn": "剧毒射手", "en": "Poison darter", "class": "游侠", "target": ORG_DIR / "职业" / "核心职业" / "游侠" / "page_49.md", "kind": "变体"},
    {"cn": "战绘师", "en": "War painter", "class": "歌者", "target": ORG_DIR / "职业" / "混合职业" / "歌者" / "page_106.md", "kind": "变体"},
]


def find_variant_starts(text: str) -> list[tuple[int, dict]]:
    """Locate each variant by matching Chinese name and English name.
    Title format: **中文名(English Name)【职业】***
    Handle line-wrapped English names by using merge_crossline_bold first.
    """
    starts = []
    for variant in CLASS_VARIANTS:
        cn = re.escape(variant["cn"])
        en = re.escape(variant["en"])
        # Try bolded title with class tag and trailing asterisks
        patterns = [
            re.compile(r"\*\*" + cn + r"\s*\(" + en + r"\)\s*【" + re.escape(variant["class"]) + r"】\*\*\*"),
            re.compile(r"\*\*" + cn + r"\s*\(" + en + r"\)\s*【" + re.escape(variant["class"]) + r"】\*\*"),
            re.compile(r"\*\*" + cn + r"\s*\(" + en + r"\)\s*【" + re.escape(variant["class"]) + r"】"),
            re.compile(r"\*\*" + cn + r"\s*\(" + en + r"\)"),
            re.compile(r"\*\*" + cn + r"\(" + en + r"\)"),
            re.compile(r"\*\*" + cn + r"\(" + en),
            re.compile(r"\*\*" + cn + r"\s*\(" + en),
            re.compile(r"\*\*" + cn + r"\s*" + en),
            re.compile(r"\*\*" + cn),
            re.compile(re.escape(variant["cn"])),
        ]
        m = None
        for pat in patterns:
            m = pat.search(text)
            if m:
                break
        if not m:
            raise ValueError(f"无法在 page_697.md 中定位职业变体：{variant['cn']}（{variant['en']}）")
        starts.append((m.start(), variant))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_variant_title(block: str, variant: dict) -> str:
    """Strip the title line from the variant block."""
    cn = re.escape(variant["cn"])
    en = re.escape(variant["en"])
    cls = re.escape(variant["class"])
    patterns = [
        re.compile(r"^\s*\*\*" + cn + r"\s*\(" + en + r"\)\s*【" + cls + r"】\*\*\*\s*"),
        re.compile(r"^\s*\*\*" + cn + r"\s*\(" + en + r"\)\s*【" + cls + r"】\*\*\s*"),
        re.compile(r"^\s*\*\*" + cn + r"\s*\(" + en + r"\)\s*【" + cls + r"】\s*"),
        re.compile(r"^\s*\*\*" + cn + r"\s*\(" + en + r"\)\s*\*\*\*\s*"),
        re.compile(r"^\s*\*\*" + cn + r"\s*\(" + en + r"\)\s*\*\*\s*"),
        re.compile(r"^\s*\*\*" + cn + r"\s*\(" + en + r"\)\s*"),
        re.compile(r"^\s*\*\*" + cn + r"\(" + en + r"\)\s*"),
        re.compile(r"^\s*\*\*" + cn + r"\s*\(" + en + r"\)\s*"),
    ]
    for pat in patterns:
        m = pat.search(block)
        if m:
            return block[m.end():].strip()
    return block


def process_class_variants(report: dict) -> None:
    src_path = SRC_DIR / "page_697.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    starts = find_variant_starts(text)

    for idx, (start_pos, variant) in enumerate(starts):
        target_path = variant["target"]
        marker = make_hidden_marker("page_697.md", variant["cn"])

        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            write_text_preserve(target_path, f"# {variant['class']}\n\n", "\n")

        existing = target_path.read_text(encoding="utf-8")
        if marker in existing:
            report["skipped"].append(f"职业变体已存在: {variant['class']} {variant['cn']}")
            continue

        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        block = strip_variant_title(block, variant)

        heading = f"## {variant['cn']}（{variant['en']}）【{variant['class']}】"
        l3 = f"变体/职业选项 → {variant['class']}"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("page_697.md", l3), block)
        report["merged"].append({
            "type": f"{variant['class']}变体",
            "name": variant["cn"],
            "target": str(target_path.relative_to(ORG_DIR)),
        })


# ========== 2. Race info from page_698.md ==========

def process_race_info(report: dict) -> None:
    src_path = SRC_DIR / "page_698.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text).strip()

    target_path = ORG_DIR / "种族" / "野兽血脉BotB_种族特性.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 野兽血脉 BotB 种族特性\n\n", "\n")

    marker = make_hidden_marker("page_698.md", "__aggregate__")
    if marker in target_path.read_text(encoding="utf-8"):
        report["skipped"].append("种族特性聚合已存在: page_698.md")
        return

    heading = "## 种族特性"
    l3 = "种族特性"
    safe_append_to_file(target_path, marker, heading, make_source_annotation("page_698.md", l3), text)
    report["merged"].append({"type": "种族特性", "name": "野兽血脉 BotB 种族特性", "target": str(target_path.relative_to(ORG_DIR))})


# ========== 3. Feats from page_699.md ==========

FEATS = [
    {"cn": "狐之型", "en": "Fox Shape"},
    {"cn": "迅捷狐妖变身者", "en": "Swift Kitsune Shapechanger"},
    {"cn": "狡黠猛扑", "en": "Vulpine Pounce"},
    {"cn": "人类伪装", "en": "Human Guise"},
    {"cn": "野蛮变形", "en": "Shapechanging Savage"},
    {"cn": "惊人变形", "en": "Startling Shapechange"},
    {"cn": "狡猾猎人", "en": "Cunning Killer"},
    {"cn": "牢固捕网", "en": "Knotted Nets"},
    {"cn": "优雅健将", "en": "Graceful Athlete"},
    {"cn": "幸运", "en": "Lucky"},
    {"cn": "机动特技", "en": "Mobile Acrobat"},
    {"cn": "虚张声势", "en": "Empty Threats"},
    {"cn": "迷人恶棍", "en": "Lovable Scoundrel"},
    {"cn": "纠缠注视", "en": "Entwining Stare"},
    {"cn": "剧毒注视", "en": "Venomous Stare"},
    {"cn": "合作鼠群", "en": "Cooperative Swarmer"},
    {"cn": "鼠群堆叠", "en": "Rat Stack"},
    {"cn": "鼠群撕裂", "en": "Rending Swarm"},
    {"cn": "蠕动鼠堆", "en": "Squirming Pile"},
    {"cn": "足下缠斗", "en": "Underfoot"},
    {"cn": "扩展战斗冥想", "en": "Extended Combat Meditation"},
    {"cn": "高阶冥想大师", "en": "Greater Meditation Master"},
    {"cn": "正念冥想", "en": "Mindful Meditation"},
    {"cn": "正念掌握", "en": "Mindfulness Mastery"},
    {"cn": "感觉制御", "en": "Sensory Control"},
]


def find_feat_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for feat in FEATS:
        # Feat titles may be bolded or plain; allow various prefixes
        cn = re.escape(feat["cn"])
        en = re.escape(feat["en"])
        patterns = [
            re.compile(r"(?:^|(?<=[\n\r\s]))\s*\*?\*?" + cn + r"\s*\(" + en),
            re.compile(r"(?:^|(?<=[\n\r\s]))\s*\*?\*?" + cn + r"\s*" + en),
            re.compile(r"(?:^|(?<=[\n\r\s]))\s*\*?\*?" + cn + r"\s*"),
            re.compile(r"(?:^|(?<=[\n\r\s]))\s*" + cn + r"\s*"),
        ]
        m = None
        for pat in patterns:
            m = pat.search(text)
            if m:
                break
        if not m:
            # Fallback: search cn anywhere in text
            m = re.search(re.escape(feat["cn"]), text)
            if not m:
                raise ValueError(f"无法在 page_699.md 中定位专长：{feat['cn']}（{feat['en']}）")
        starts.append((m.start(), feat))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_feat_title(block: str, feat: dict) -> str:
    cn = re.escape(feat["cn"])
    en = re.escape(feat["en"])
    patterns = [
        re.compile(r"^\s*\*?\*?" + cn + r"\s*\(" + en + r"(?:\s*[^）]*)?\)\s*\*?\*?\s*", re.DOTALL),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*" + en + r"(?:\s*\([^)]*\))?\s*\*?\*?\s*", re.DOTALL),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*\*?\*?\s*"),
        re.compile(r"^\s*" + cn + r"\s*"),
    ]
    for pat in patterns:
        m = pat.search(block)
        if m:
            block = block[m.end():].strip()
            break
    # 剥除可能残留的跨行英文标题（无括号、源文件未加粗）
    lines = block.splitlines()
    cleaned: list[str] = []
    i = 0
    en_words = feat["en"].split()
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        # 单行英文标题
        if re.match(r"^" + re.escape(feat["en"]) + r"(?:\s*\([^)]*\))?\s*$", line, re.IGNORECASE):
            i += 1
            continue
        # 英文标题跨行：当前行 + 下一行
        if i + 1 < len(lines):
            combined = line + " " + lines[i + 1].strip()
            if re.match(r"^" + re.escape(feat["en"]) + r"(?:\s*\([^)]*\))?\s*", combined, re.IGNORECASE):
                # 若下一行在英文后还有正文，需要保留
                rest = re.sub(r"^" + re.escape(feat["en"]) + r"(?:\s*\([^)]*\))?\s*", "", combined, flags=re.IGNORECASE).strip()
                if rest:
                    cleaned.append(rest)
                i += 2
                continue
        cleaned.append(lines[i])
        i += 1
    return "\n".join(cleaned).strip()


def process_feats(report: dict) -> None:
    src_path = SRC_DIR / "page_699.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "专长" / "野兽血脉BotB_专长.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 野兽血脉 BotB 专长\n\n", "\n")

    starts = find_feat_starts(text)
    l3 = "专长"
    for idx, (start_pos, feat) in enumerate(starts):
        marker = make_hidden_marker("page_699.md", feat["cn"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"专长已存在: {feat['cn']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        block = strip_feat_title(block, feat)
        heading = f"## {feat['cn']}（{feat['en']}）"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("page_699.md", l3), block)
        report["merged"].append({"type": "专长", "name": feat["cn"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 4. page_700.md sections ==========

PAGE700_SECTIONS = [
    {
        "cn": "进阶多才多艺",
        "en": "Advanced Versatile Performance",
        "marker_name": "进阶多才多艺",
        "target": ORG_DIR / "职业" / "核心职业" / "吟游诗人" / "page_38.md",
        "heading": "## 进阶多才多艺（Advanced Versatile Performance）",
        "l3": "变体/职业选项 → 吟游诗人",
    },
    {
        "cn": "先祖",
        "en": "Ancestor Eidolon Subtype",
        "marker_name": "先祖",
        "target": ORG_DIR / "职业" / "基础职业" / "召唤师" / "page_1346.md",
        "heading": "## 先祖幻灵亚种（Ancestor Eidolon Subtype）",
        "l3": "变体/职业选项 → 召唤师",
    },
    {
        "cn": "猫科",
        "en": "Feline Wildsoul Natural Course",
        "marker_name": "猫科",
        "target": ORG_DIR / "职业" / "基础职业" / "侠客" / "page_70.md",
        "heading": "## 猫科（Feline Wildsoul Natural Course）",
        "l3": "变体/职业选项 → 侠客",
    },
    {
        "cn": "战士进阶武器训练",
        "en": "Fighter Advanced Weapon Training",
        "marker_name": "战士进阶武器训练",
        "target": ORG_DIR / "职业" / "核心职业" / "战士" / "page_44.md",
        "heading": "## 进阶武器训练（野兽血脉 BotB）",
        "l3": "变体/职业选项 → 战士",
    },
    {
        "cn": "催眠师诡计",
        "en": "Mesmerist Tricks",
        "marker_name": "催眠师诡计",
        "target": ORG_DIR / "职业" / "基础职业" / "催眠师" / "page_94.md",
        "heading": "## 催眠师诡计（野兽血脉 BotB）",
        "l3": "变体/职业选项 → 催眠师",
    },
    {
        "cn": "娜迦血脉",
        "en": "Naga Bloodline",
        "marker_name": "娜迦血脉",
        "target": ORG_DIR / "职业" / "混合职业" / "血脉狂怒者" / "page_104.md",
        "heading": "## 娜迦血脉（Naga Bloodline）",
        "l3": "变体/职业选项 → 血脉狂怒者",
    },
]


def find_page700_section_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for sec in PAGE700_SECTIONS:
        cn = re.escape(sec["cn"])
        patterns = [
            re.compile(r"(?:^|(?<=[\n\r]))\s*\*?\*?" + cn + r"\s*\(" + re.escape(sec["en"]) + r"\)"),
            re.compile(r"(?:^|(?<=[\n\r]))\s*\*?\*?" + cn + r"\s*" + re.escape(sec["en"])),
            re.compile(r"(?:^|(?<=[\n\r]))\s*\*?\*?" + cn + r"\s*"),
            re.compile(r"(?:^|(?<=[\n\r]))\s*" + cn + r"\s*"),
        ]
        m = None
        for pat in patterns:
            m = pat.search(text)
            if m:
                break
        if not m:
            raise ValueError(f"无法在 page_700.md 中定位段落：{sec['cn']}（{sec['en']}）")
        starts.append((m.start(), sec))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_page700_section_title(block: str, sec: dict) -> str:
    cn = re.escape(sec["cn"])
    en = re.escape(sec["en"])
    patterns = [
        re.compile(r"^\s*\*?\*?" + cn + r"\s*\(" + en + r"\)\s*\*?\*?\s*"),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*" + en + r"\s*\*?\*?\s*"),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*\*?\*?\s*"),
        re.compile(r"^\s*" + cn + r"\s*"),
    ]
    for pat in patterns:
        m = pat.search(block)
        if m:
            return block[m.end():].strip()
    return block


def process_page700_sections(report: dict) -> None:
    src_path = SRC_DIR / "page_700.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    starts = find_page700_section_starts(text)

    for idx, (start_pos, sec) in enumerate(starts):
        target_path = sec["target"]
        marker = make_hidden_marker("page_700.md", sec["marker_name"])

        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            write_text_preserve(target_path, f"# {sec['heading'].lstrip('# ').split('（')[0]}\n\n", "\n")

        existing = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        if marker in existing:
            report["skipped"].append(f"page_700 段落已存在: {sec['cn']}")
            continue

        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        block = strip_page700_section_title(block, sec)

        safe_append_to_file(target_path, marker, sec["heading"], make_source_annotation("page_700.md", sec["l3"]), block)
        report["merged"].append({"type": sec["l3"].split(" → ")[-1] + "选项", "name": sec["cn"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 5. Background traits from 背景特性37.md ==========

TRAITS = [
    {"cn": "篷车牧民", "en": "Caravan Nomad"},
    {"cn": "寻找财富", "en": "Fortune Found"},
    {"cn": "丛林土著", "en": "Jungle Native"},
]


def find_trait_starts(text: str) -> list[tuple[int, dict]]:
    starts = []
    for trait in TRAITS:
        cn = re.escape(trait["cn"])
        en = re.escape(trait["en"])
        patterns = [
            re.compile(r"(?:^|(?<=[\n\r]))\s*\*?\*?" + cn + r"\s*\(" + en + r"\)"),
            re.compile(r"(?:^|(?<=[\n\r]))\s*\*?\*?" + cn + r"\s*" + en),
            re.compile(r"(?:^|(?<=[\n\r]))\s*\*?\*?" + cn + r"\s*"),
            re.compile(r"(?:^|(?<=[\n\r]))\s*" + cn + r"\s*"),
        ]
        m = None
        for pat in patterns:
            m = pat.search(text)
            if m:
                break
        if not m:
            raise ValueError(f"无法在 背景特性37.md 中定位背景特性：{trait['cn']}（{trait['en']}）")
        starts.append((m.start(), trait))
    starts.sort(key=lambda x: x[0])
    return starts


def strip_trait_title(block: str, trait: dict) -> str:
    cn = re.escape(trait["cn"])
    en = re.escape(trait["en"])
    patterns = [
        re.compile(r"^\s*\*?\*?" + cn + r"\s*\(" + en + r"\)\s*\*?\*?\s*"),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*\(" + en + r"\)\s*"),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*" + en + r"\s*\*?\*?\s*"),
        re.compile(r"^\s*\*?\*?" + cn + r"\s*\*?\*?\s*"),
        re.compile(r"^\s*" + cn + r"\s*"),
    ]
    for pat in patterns:
        m = pat.search(block)
        if m:
            return block[m.end():].strip()
    return block


def process_background_traits(report: dict) -> None:
    src_path = SRC_DIR / "背景特性37.md"
    text = src_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = merge_crossline_bold(text)
    text = clean_translator_url(text)
    text = clean_leading_image(text)

    target_path = ORG_DIR / "背景特性" / "野兽血脉BotB_背景特性.md"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not target_path.exists():
        write_text_preserve(target_path, "# 野兽血脉 BotB 背景特性\n\n", "\n")

    starts = find_trait_starts(text)
    l3 = "背景特性"
    for idx, (start_pos, trait) in enumerate(starts):
        marker = make_hidden_marker("背景特性37.md", trait["cn"])
        if marker in target_path.read_text(encoding="utf-8"):
            report["skipped"].append(f"背景特性已存在: {trait['cn']}")
            continue
        end_pos = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
        block = text[start_pos:end_pos]
        block = strip_trailing_artifacts(block)
        block = strip_trait_title(block, trait)
        heading = f"## {trait['cn']}（{trait['en']}）"
        safe_append_to_file(target_path, marker, heading, make_source_annotation("背景特性37.md", l3), block)
        report["merged"].append({"type": "背景特性", "name": trait["cn"], "target": str(target_path.relative_to(ORG_DIR))})


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
    process_class_variants(report)
    process_race_info(report)
    process_feats(report)
    process_page700_sections(report)
    process_background_traits(report)
    write_report(report)
    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")


if __name__ == "__main__":
    main()
