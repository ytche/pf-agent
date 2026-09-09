#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
整理 武术手册Martial Arts Handbook（MAH）从 pf_rules_md/未整理/武术手册Martial Arts Handbook
到 pf_rules_md_organized/ 对应目录。
"""

import json
import re
from pathlib import Path
from datetime import datetime

# 基础路径
BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
SRC_DIR = BASE / "pf_rules_md/未整理/武术手册Martial Arts Handbook"
ORG_DIR = BASE / "pf_rules_md_organized"
REPORT_DIR = BASE

SOURCE_BOOK = "武术手册（Martial Arts Handbook）MAH"
SOURCE_BOOK_SHORT = "MAH"


def normalize_to_nl(text: str, target_nl: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if target_nl == "\r\n":
        text = text.replace("\n", "\r\n")
    return text


def detect_nl(path: Path) -> str:
    if not path.exists():
        return "\n"
    raw = path.read_bytes()
    return "\r\n" if b"\r\n" in raw else "\n"


def read_text_preserve(path: Path) -> tuple[str, str]:
    nl = detect_nl(path)
    if not path.exists():
        return "", nl
    return path.read_text(encoding="utf-8"), nl


def write_text_preserve(path: Path, text: str, nl: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = normalize_to_nl(text, nl)
    path.write_bytes(text.encode("utf-8"))


def append_to_file(path: Path, content: str) -> None:
    existing, nl = read_text_preserve(path)
    if existing and not existing.endswith("\n") and not existing.endswith("\r\n"):
        existing += nl
    elif existing and not (existing.endswith("\n") or existing.endswith("\r\n")):
        existing += nl
    new_content = existing + content
    write_text_preserve(path, new_content, nl)


def clean_translator_url(text: str) -> str:
    lines = text.splitlines()
    while lines and (not lines[0].strip() or lines[0].strip().startswith("http") or lines[0].strip().startswith("译者")):
        lines.pop(0)
    return "\n".join(lines)


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


def split_by_hr(text: str) -> list[str]:
    blocks = re.split(r"\n\s*---\s*\n", text)
    result = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        block = clean_translator_url(block)
        if block:
            result.append(block)
    return result


def make_source_annotation(source_file: str, l3: str = "") -> str:
    l3_part = f" → {l3}" if l3 else ""
    return f"> 来源：{SOURCE_BOOK}，页码见原书，未整理 → 武术手册MAH{l3_part}"


def make_hidden_marker(source_file: str, entry_name: str) -> str:
    return f"<!-- {SOURCE_BOOK_SHORT}-source:{source_file}:{entry_name} -->"


def merge_section_heading_lines(text: str) -> str:
    """合并跨行的大写/小写英文标题，例如 'Broken-back \nseax'、'UNARMED \nMASTERY'。"""
    lines = text.splitlines()
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            # 当前行以字母结尾，下一行以字母开头，且下一行没有前置中文或标点
            if re.search(r"[A-Za-z]$", line.rstrip()) and re.match(r"^[A-Za-z]", next_line.lstrip()):
                merged.append(line.rstrip() + " " + next_line.lstrip())
                i += 2
                continue
        merged.append(line)
        i += 1
    return "\n".join(merged)


# ========== 通用块提取 ==========

def is_title_span(span: str) -> bool:
    """判断一个加粗 span 是否像条目标题而非内联标签。"""
    if not re.search(r"[一-鿿]", span):
        return False
    # 包含英文单词，或带括号标签，视为标题
    if re.search(r"[A-Za-z]", span):
        return True
    if re.search(r"[（(][^）)]+[）)]", span):
        return True
    return False


def extract_block_by_name(text: str, name: str, english: str = "") -> str | None:
    """按中文名（及可选英文名）查找条目块。标题是包含中英名的加粗 span。"""
    # 1. 找到所有包含中文名的加粗 span 候选
    base_pattern = re.compile(r"\*\*[^*]*?" + re.escape(name) + r"[^*]*?\*\*")
    candidates = [m for m in base_pattern.finditer(text) if is_title_span(m.group(0))]

    # 2. 若提供英文名，优先选择同时包含英文名（不区分大小写）的候选
    if candidates and english:
        eng_norm = " ".join(english.lower().split())
        pref = []
        for m in candidates:
            span = m.group(0)
            norm = re.sub(r"\s+", " ", span).lower()
            if eng_norm in norm:
                pref.append(m)
        if pref:
            candidates = pref

    if candidates:
        # 3. 选择跨度最短的候选（更精确匹配具体条目而非章节标题）
        start_match = min(candidates, key=lambda m: len(m.group(0)))
        start = start_match.start()

        # 4. 从该标题 span 结束后开始，找下一个标题 span
        rest = text[start_match.end():]
        next_pattern = re.compile(r"\*\*[^*]+?\*\*")
        pos = 0
        end = len(text)
        while True:
            nm = next_pattern.search(rest, pos)
            if not nm:
                break
            span = nm.group(0)
            if is_title_span(span):
                end = start_match.end() + nm.start()
                break
            pos = nm.end()

        return text[start:end].strip()

    # Fallback：纯文本标题（如 回心转意（Change of Heart））
    if english:
        plain_pattern = re.compile(
            r"(?:^|\n)\s*(" + re.escape(name) + r"[（(][^）)]*?" + re.escape(english) + r"[^）)]*?[）)])",
            re.IGNORECASE,
        )
    else:
        plain_pattern = re.compile(r"(?:^|\n)\s*(" + re.escape(name) + r")", re.IGNORECASE)
    pm = plain_pattern.search(text)
    if pm:
        start = pm.start()
        rest = text[pm.end():]
        # 下一个空行或下一个加粗标题
        next_stop = re.search(r"\n\s*\n|\n\s*\*\*[^*]+?\*\*", rest)
        if next_stop:
            end = pm.end() + next_stop.start()
        else:
            end = len(text)
        return text[start:end].strip()

    return None


def find_entry_headings(section_text: str, entries: list[dict]) -> list[tuple[int, dict, str]]:
    """在一段文本中定位所有条目标题的位置，返回 (position, entry, heading) 列表。"""
    positions = []
    for entry in entries:
        name = entry["name"]
        english = entry.get("english", "")
        # 为英文中的空格构造可匹配任意空白的模式
        eng_pat = re.escape(english).replace(r"\ ", r"\s+")
        patterns = [
            # 中文 + (英文) 括号内可含 tag
            re.compile(re.escape(name) + r"\s*[（(]\s*[^）)]*?" + eng_pat + r"[^）)]*?\s*[）)]", re.IGNORECASE),
            # 中文 + (tag) + 英文
            re.compile(re.escape(name) + r"\s*[（(][^）)]+[）)]\s*" + eng_pat, re.IGNORECASE),
            # 中文直接接英文
            re.compile(re.escape(name) + r"\s*" + eng_pat, re.IGNORECASE),
            # 加粗标题兜底
            re.compile(r"\*\*[^*]*?" + re.escape(name) + r"[^*]*?\*\*", re.IGNORECASE),
        ]
        found = False
        for pattern in patterns:
            m = pattern.search(section_text)
            if m:
                positions.append((m.start(), entry, m.group(0)))
                found = True
                break
        if not found:
            # 最后再试一次纯中文匹配
            pattern = re.compile(re.escape(name), re.IGNORECASE)
            m = pattern.search(section_text)
            if m:
                positions.append((m.start(), entry, m.group(0)))
    positions.sort()
    return positions


def split_section_by_entries(section_text: str, entries: list[dict]) -> dict[str, str]:
    """把一段文本按条目标题拆成 {name: block}。"""
    positions = find_entry_headings(section_text, entries)
    blocks = {}
    for i, (pos, entry, heading) in enumerate(positions):
        start = pos
        end = positions[i + 1][0] if i + 1 < len(positions) else len(section_text)
        blocks[entry["name"]] = section_text[start:end].strip()
    return blocks


def extract_section(text: str, start_marker: str, end_marker: str = "") -> str | None:
    """按起始和结束标记提取文本段，结束标记为空则取到文本尾。"""
    start_pat = re.compile(re.escape(start_marker), re.IGNORECASE)
    sm = start_pat.search(text)
    if not sm:
        return None
    start = sm.start()
    if end_marker:
        end_pat = re.compile(re.escape(end_marker), re.IGNORECASE)
        em = end_pat.search(text, sm.end())
        if em:
            return text[start:em.start()].strip()
    return text[start:].strip()


def split_text_by_headings(text: str, heading_pattern: re.Pattern) -> list[tuple[str, str]]:
    """按标题正则拆分文本，返回 (标题行, 内容) 列表。"""
    matches = list(heading_pattern.finditer(text))
    blocks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        heading = m.group(0).strip()
        content = text[start:end].strip()
        blocks.append((heading, content))
    return blocks


# ========== 1. 职业变体 ==========

ARCHETYPES = [
    {"name": "即时引导者", "english": "Extemporaneous Channeler", "class": "秘学士", "source_file": "page_1343.md"},
    {"name": "战斗舞者", "english": "Battle Dancer", "class": "拳师", "source_file": "page_1341.md"},
    {"name": "铁环斗士", "english": "Iron-Ring Striker", "class": "魔战士", "source_file": "page_1341.md"},
    {"name": "宗师通灵者", "english": "Medium of the Master", "class": "通灵者", "source_file": "page_1341.md"},
    {"name": "柔拳僧", "english": "Softstrike Monk", "class": "武僧", "source_file": "page_1341.md"},
    {"name": "楚业豪强", "english": "Chu Ye Enforcer", "class": "侠客", "source_file": "page_1338.md"},
    {"name": "跳跳枪手", "english": "Black Powder Vaulter", "class": "铳士", "source_file": "page_1337.md"},
    {"name": "喧哗剑圣", "english": "Brawling Blademaster", "class": "武士", "source_file": "page_1337.md"},
    {"name": "御海寇", "english": "Okayo Corsair", "class": "游荡剑客", "source_file": "page_1337.md"},
    {"name": "矛斗士", "english": "Spear Fighter", "class": "战士", "source_file": "page_1337.md"},
    {"name": "铁线拳师", "english": "Strong-Side Boxer", "class": "拳师", "source_file": "传统流派.md"},
    {"name": "摔角手", "english": "Lifting Hand", "class": "武僧", "source_file": "战技大师.md"},
]


def process_archetypes(report: dict) -> None:
    target_path = ORG_DIR / "职业" / "武术手册MAH_变体.md"
    if not target_path.exists():
        write_text_preserve(target_path, f"# {SOURCE_BOOK} 职业变体\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    for arc in ARCHETYPES:
        src_path = SRC_DIR / arc["source_file"]
        text = src_path.read_text(encoding="utf-8")
        text = merge_section_heading_lines(text)
        text = merge_crossline_bold(text)
        block = extract_block_by_name(text, arc["name"], arc.get("english", ""))
        if block is None:
            report["warnings"].append(f"未找到变体块: {arc['name']} ({arc['source_file']})")
            continue
        marker = make_hidden_marker(arc["source_file"], arc["name"])
        if marker in existing:
            report["skipped"].append(f"变体已存在: {arc['name']}")
            continue
        entry = (
            f"\n{marker}\n"
            f"## {arc['name']}（{arc['english']}）〔{arc['class']}变体〕\n"
            f"{make_source_annotation(arc['source_file'], '变体/职业选项')}\n"
            f"{block}\n\n"
        )
        append_to_file(target_path, entry)
        report["merged"].append({"type": "变体", "name": arc["name"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 2. 专长 ==========

FEATS = [
    # page_1343
    {"name": "随心武器", "english": "Grab and Go", "source_file": "page_1343.md", "section": "临时武器专长"},
    {"name": "临时专攻", "english": "Improvised Focus", "source_file": "page_1343.md", "section": "临时武器专长"},
    {"name": "临时防御", "english": "Improvised Defenses", "source_file": "page_1343.md", "section": "临时武器专长"},
    {"name": "临时战技", "english": "Makeshift Maneuvers", "source_file": "page_1343.md", "section": "临时武器专长"},
    {"name": "式神操纵", "english": "Shikigami Manipulation", "source_file": "page_1343.md", "section": "临时武器流派"},
    {"name": "式神模仿", "english": "Shikigami Mimicry", "source_file": "page_1343.md", "section": "临时武器流派"},
    {"name": "式神流", "english": "Shikigami Style", "source_file": "page_1343.md", "section": "临时武器流派"},
    # page_1341
    {"name": "棍斗截击", "english": "Stick-Fighting Counter", "source_file": "page_1337.md", "section": "棍斗流派专长"},
    {"name": "棍斗战技", "english": "Stick-Fighting Maneuver", "source_file": "page_1337.md", "section": "棍斗流派专长"},
    {"name": "棍斗流", "english": "Stick-Fighting Style", "source_file": "page_1337.md", "section": "棍斗流派专长"},
    {"name": "武器技法", "english": "Weapon Trick", "source_file": "page_1337.md", "section": "武器技法"},
    {"name": "寸拳", "english": "One-Inch Punch", "source_file": "page_1341.md", "section": "徒手宗师"},
    {"name": "迷魂拳", "english": "Stupefying Strike", "source_file": "page_1341.md", "section": "徒手宗师"},
    {"name": "失衡击", "english": "Unbalancing Blow", "source_file": "page_1341.md", "section": "徒手宗师"},
    # page_1338
    {"name": "化形猛击", "english": "Shapeshifting Savage", "source_file": "page_1338.md", "section": "专长"},
    {"name": "化形势", "english": "Shapeshifter Style", "source_file": "page_1338.md", "section": "专长"},
    {"name": "化形扭", "english": "Shapeshifting Twist", "source_file": "page_1338.md", "section": "专长"},
    # page_1602
    {"name": "战斗韵律", "english": "Combat Rhythm", "source_file": "page_1602.md", "section": "融会专长"},
    {"name": "终结喷流", "english": "Finishing Cascade", "source_file": "page_1602.md", "section": "融会专长"},
    {"name": "滴水穿石", "english": "Cracking the Shell", "source_file": "page_1602.md", "section": "融会专长"},
    {"name": "侵蚀打击", "english": "Eroding Strikes", "source_file": "page_1602.md", "section": "融会专长"},
    {"name": "千斩", "english": "Thousand Cuts", "source_file": "page_1602.md", "section": "融会专长"},
    {"name": "雕饰激流", "english": "Sculpting the River", "source_file": "page_1602.md", "section": "融会专长"},
    {"name": "实用形", "english": "Practical Kata", "source_file": "page_1602.md", "section": "融会专长"},
    # 传统流派
    {"name": "蜻蜓飞舞", "english": "Dragonfly Flight", "source_file": "传统流派.md", "section": "新流派"},
    {"name": "蜻蜓流", "english": "Dragonfly Style", "source_file": "传统流派.md", "section": "新流派"},
    {"name": "蜻蜓之翼", "english": "Dragonfly Wings", "source_file": "传统流派.md", "section": "新流派"},
    {"name": "蛇龙猎人协作", "english": "Linnorm Hunter Coordination", "source_file": "传统流派.md", "section": "新流派"},
    {"name": "蛇龙猎人撤退", "english": "Linnorm Hunter Retreat", "source_file": "传统流派.md", "section": "新流派"},
    {"name": "蛇龙猎人流", "english": "Linnorm Hunter Style", "source_file": "传统流派.md", "section": "新流派"},
    {"name": "章鱼专注", "english": "Octopus Focus", "source_file": "传统流派.md", "section": "新流派"},
    {"name": "章鱼流", "english": "Octopus Style", "source_file": "传统流派.md", "section": "新流派"},
    {"name": "章鱼鞭打", "english": "Octopus Thrash", "source_file": "传统流派.md", "section": "新流派"},
    {"name": "盾杖突袭", "english": "Shielded Staff Ambush", "source_file": "传统流派.md", "section": "新流派"},
    {"name": "盾杖大师", "english": "Shielded Staff Master", "source_file": "传统流派.md", "section": "新流派"},
    {"name": "盾杖流", "english": "Shielded Staff Style", "source_file": "传统流派.md", "section": "新流派"},
    # 其他专长2
    {"name": "回心转意", "english": "Change of Heart", "source_file": "其他专长2.md", "section": ""},
    # 战技大师
    {"name": "擒武", "english": "Arming Grab", "source_file": "战技大师.md", "section": "卸武技巧"},
    {"name": "跟进追击", "english": "Follow-Up Strike", "source_file": "战技大师.md", "section": "卸武技巧"},
    {"name": "麻木打击", "english": "Numbing Blow", "source_file": "战技大师.md", "section": "卸武技巧"},
    {"name": "横扫卸武", "english": "Sweeping Disarm", "source_file": "战技大师.md", "section": "卸武技巧"},
    {"name": "擒腕", "english": "Wrist Grab", "source_file": "战技大师.md", "section": "卸武技巧"},
    {"name": "野蛮摔投", "english": "Savage Slam", "source_file": "战技大师.md", "section": "擒抱技巧"},
    {"name": "戏剧摔投", "english": "Dramatic Slam", "source_file": "战技大师.md", "section": "擒抱技巧"},
    {"name": "过头摔", "english": "Overhead Flip", "source_file": "战技大师.md", "section": "擒抱技巧"},
    {"name": "野蛮飞跃", "english": "Savage Leap", "source_file": "战技大师.md", "section": "擒抱技巧"},
    {"name": "旋风擒抱", "english": "Whirling Hold", "source_file": "战技大师.md", "section": "擒抱技巧"},
    {"name": "破碎冲击", "english": "Crushing Impact", "source_file": "战技大师.md", "section": "移位技巧"},
    {"name": "多米诺冲撞", "english": "Domino Crash", "source_file": "战技大师.md", "section": "移位技巧"},
    {"name": "痛苦撞击", "english": "Painful Collision", "source_file": "战技大师.md", "section": "移位技巧"},
    {"name": "反身翻腾", "english": "Reverse Somersault Throw", "source_file": "战技大师.md", "section": "移位技巧"},
    {"name": "粉碎冲击", "english": "Smashing Impact", "source_file": "战技大师.md", "section": "移位技巧"},
    {"name": "甩鞭", "english": "Whipcrack", "source_file": "战技大师.md", "section": "移位技巧"},
    {"name": "绊腿", "english": "Tangled Limbs", "source_file": "战技大师.md", "section": "摔绊技巧"},
    {"name": "泰坦纠缠", "english": "Titan's Tangle", "source_file": "战技大师.md", "section": "摔绊技巧"},
    {"name": "连环倾倒", "english": "Toppling Pileup", "source_file": "战技大师.md", "section": "摔绊技巧"},
    {"name": "翻滚摔绊", "english": "Tumbling Upset", "source_file": "战技大师.md", "section": "摔绊技巧"},
    # page_1336
    {"name": "脉轮封禁", "english": "Block Chakras", "source_file": "page_1336.md", "section": "生命力量专长"},
    {"name": "高等脉轮封禁", "english": "Block Upper Chakras", "source_file": "page_1336.md", "section": "生命力量专长"},
    {"name": "元素气池", "english": "Elemental Ki", "source_file": "page_1336.md", "section": "专长"},
    {"name": "持久力量", "english": "Enduring Might", "source_file": "page_1336.md", "section": "专长"},
    {"name": "凝聚力量", "english": "Gather Might", "source_file": "page_1336.md", "section": "专长"},
]


def process_feats(report: dict) -> None:
    from collections import defaultdict

    target_path = ORG_DIR / "专长" / "武术手册MAH_专长.md"
    if not target_path.exists():
        write_text_preserve(target_path, f"# {SOURCE_BOOK} 专长\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    def write_feat(feat: dict, block: str) -> None:
        if block is None:
            report["warnings"].append(f"未找到专长块: {feat['name']} ({feat['source_file']})")
            return
        marker = make_hidden_marker(feat["source_file"], feat["name"])
        if marker in existing:
            report["skipped"].append(f"专长已存在: {feat['name']}")
            return
        section_part = f"/{feat['section']}" if feat.get("section") else ""
        entry = (
            f"\n{marker}\n"
            f"## {feat['name']}（{feat['english']}）\n"
            f"{make_source_annotation(feat['source_file'], '专长' + section_part)}\n"
            f"{block}\n\n"
        )
        append_to_file(target_path, entry)
        report["merged"].append({"type": "专长", "name": feat["name"], "target": str(target_path.relative_to(ORG_DIR))})

    def split_file_by_entries(source_file: str, entries: list[dict], section_start: str = "", section_end: str = "") -> dict[str, str]:
        text = (SRC_DIR / source_file).read_text(encoding="utf-8")
        text = merge_section_heading_lines(text)
        text = merge_crossline_bold(text)
        if section_start:
            text = extract_section(text, section_start, section_end) or ""
        return split_section_by_entries(text, entries)

    # 1. page_1602.md 整文件为融会专长
    page_1602_entries = [f for f in FEATS if f["source_file"] == "page_1602.md"]
    blocks = split_file_by_entries("page_1602.md", page_1602_entries)
    for feat in page_1602_entries:
        write_feat(feat, blocks.get(feat["name"]))

    # 2. page_1341.md 徒手宗师段落
    unarmed_entries = [f for f in FEATS if f["source_file"] == "page_1341.md" and f.get("section") == "徒手宗师"]
    blocks = split_file_by_entries("page_1341.md", unarmed_entries, "徒手宗师UNARMED MASTERY")
    for feat in unarmed_entries:
        write_feat(feat, blocks.get(feat["name"]))

    # 3. page_1336.md 生命力量专长段落（到操念使注能之前）
    page_1336_entries = [f for f in FEATS if f["source_file"] == "page_1336.md"]
    blocks = split_file_by_entries("page_1336.md", page_1336_entries, "生命力量专长LIFE FORCE FEATS", "操念使注能")
    for feat in page_1336_entries:
        write_feat(feat, blocks.get(feat["name"]))

    # 4. 其他专长2.md 整文件为一个专长
    other2_entries = [f for f in FEATS if f["source_file"] == "其他专长2.md"]
    if other2_entries:
        text = (SRC_DIR / "其他专长2.md").read_text(encoding="utf-8")
        text = merge_crossline_bold(text)
        for feat in other2_entries:
            write_feat(feat, clean_translator_url(text))

    # 5. 其余 source files 按文件统一拆分
    handled_sources = {"page_1602.md", "page_1341.md", "page_1336.md", "其他专长2.md"}
    by_source = defaultdict(list)
    for f in FEATS:
        if f["source_file"] not in handled_sources:
            by_source[f["source_file"]].append(f)
    for source_file, entries in by_source.items():
        blocks = split_file_by_entries(source_file, entries)
        for feat in entries:
            write_feat(feat, blocks.get(feat["name"]))


# ========== 3. 杀手天赋 ==========

SLAYER_TALENTS = [
    {"name": "永世仇敌", "english": "Eternal Opposition"},
    {"name": "人生经验", "english": "Experience Across Ages"},
    {"name": "直面恐怖", "english": "Inured to Terror"},
    {"name": "山坡伏击", "english": "Mountainside Ambush"},
    {"name": "神秘之纱", "english": "Mystic Veil"},
    {"name": "重唤技艺", "english": "Recall Training"},
]


def process_slayer_talents(report: dict) -> None:
    src_path = SRC_DIR / "page_1338.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    target_path = ORG_DIR / "职业" / "混合职业" / "杀手" / "page_118.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 杀手天赋\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    section = extract_section(text, "轮回者杀手天赋（Samsaran Slayer Talents）", "专长（Feats）")
    if section:
        blocks = split_section_by_entries(section, SLAYER_TALENTS)
    else:
        blocks = {}

    for tal in SLAYER_TALENTS:
        block = blocks.get(tal["name"])
        if block is None:
            report["warnings"].append(f"未找到杀手天赋块: {tal['name']}")
            continue
        marker = make_hidden_marker("page_1338.md", tal["name"])
        if marker in existing:
            report["skipped"].append(f"杀手天赋已存在: {tal['name']}")
            continue
        entry = (
            f"\n{marker}\n"
            f"## {tal['name']}（{tal['english']}）\n"
            f"{make_source_annotation('page_1338.md', '轮回者杀手天赋')}\n"
            f"{block}\n\n"
        )
        append_to_file(target_path, entry)
        report["merged"].append({"type": "杀手天赋", "name": tal["name"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 4. 真劲击 ==========

STYLE_STRIKES = [
    {"name": "兔子拳", "english": "Rabbit Punch"},
    {"name": "切喉", "english": "Throat Crush"},
    {"name": "破缚", "english": "Break"},
]


def process_style_strikes(report: dict) -> None:
    src_path = SRC_DIR / "page_1341.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    text = merge_crossline_bold(text)
    target_path = ORG_DIR / "职业" / "核心职业" / "武僧" / "page_55.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 武僧（UC）\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    section = extract_section(text, "真劲击STYLE STRIKES", "徒手宗师UNARMED MASTERY")
    if section:
        blocks = split_section_by_entries(section, STYLE_STRIKES)
    else:
        blocks = {}

    for ss in STYLE_STRIKES:
        block = blocks.get(ss["name"])
        if block is None:
            report["warnings"].append(f"未找到真劲击块: {ss['name']}")
            continue
        marker = make_hidden_marker("page_1341.md", ss["name"])
        if marker in existing:
            report["skipped"].append(f"真劲击已存在: {ss['name']}")
            continue
        entry = (
            f"\n{marker}\n"
            f"## {ss['name']}（{ss['english']}）\n"
            f"{make_source_annotation('page_1341.md', '真劲击')}\n"
            f"{block}\n\n"
        )
        append_to_file(target_path, entry)
        report["merged"].append({"type": "真劲击", "name": ss["name"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 5. 操念使注能 ==========

INFUSIONS = [
    {"name": "拙火注能", "english": "Kundalini Infusion"},
    {"name": "武技注能", "english": "Stylish Infusion"},
    {"name": "不动之炎注能", "english": "Unblinking Flame Infusion"},
    {"name": "不断之浪注能", "english": "Unbreaking Waves Infusion"},
    {"name": "不止之风注能", "english": "Unfolding Wind Infusion"},
    {"name": "不屈之铁注能", "english": "Untwisting Iron Infusion"},
]


def process_infusions(report: dict) -> None:
    src_path = SRC_DIR / "page_1336.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_crossline_bold(text)
    target_path = ORG_DIR / "职业" / "异能冒险（Occult Adventures）" / "操念使" / "page_260.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 操念使注能\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    section = extract_section(text, "操念使注能")
    if section:
        blocks = split_section_by_entries(section, INFUSIONS)
    else:
        blocks = {}

    for inf in INFUSIONS:
        block = blocks.get(inf["name"])
        if block is None:
            report["warnings"].append(f"未找到注能块: {inf['name']}")
            continue
        marker = make_hidden_marker("page_1336.md", inf["name"])
        if marker in existing:
            report["skipped"].append(f"注能已存在: {inf['name']}")
            continue
        entry = (
            f"\n{marker}\n"
            f"## {inf['name']}（{inf['english']}）\n"
            f"{make_source_annotation('page_1336.md', '操念使注能')}\n"
            f"{block}\n\n"
        )
        append_to_file(target_path, entry)
        report["merged"].append({"type": "操念使注能", "name": inf["name"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 6. 新武器 ==========

WEAPONS = [
    {"name": "缠手布", "english": "Handwraps"},
    {"name": "旅行壶", "english": "Traveling Kettle"},
    {"name": "断背直刀", "english": "Broken-back Seax"},
    {"name": "分刃剑", "english": "Split-blade Sword"},
    {"name": "双头矛", "english": "Double Spear"},
]


def process_weapons(report: dict) -> None:
    src_path = SRC_DIR / "新武器2.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_section_heading_lines(text)
    target_path = ORG_DIR / "装备_魔法物品" / "武器" / "武术手册MAH_新武器.md"
    if not target_path.exists():
        write_text_preserve(target_path, f"# {SOURCE_BOOK} 新武器\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    # 去掉顶部的表格
    lines = text.splitlines()
    while lines and (lines[0].strip().startswith("|") or not lines[0].strip()):
        lines.pop(0)
    text = "\n".join(lines)

    blocks = split_section_by_entries(text, WEAPONS)
    for wp in WEAPONS:
        block = blocks.get(wp["name"])
        if block is None:
            report["warnings"].append(f"未找到武器块: {wp['name']}")
            continue
        marker = make_hidden_marker("新武器2.md", wp["name"])
        if marker in existing:
            report["skipped"].append(f"武器已存在: {wp['name']}")
            continue
        entry = (
            f"\n{marker}\n"
            f"## {wp['name']}（{wp['english']}）\n"
            f"{make_source_annotation('新武器2.md', '新武器')}\n"
            f"{block}\n\n"
        )
        append_to_file(target_path, entry)
        report["merged"].append({"type": "武器", "name": wp["name"], "target": str(target_path.relative_to(ORG_DIR))})


# ========== 7. 道具 / 训练物品 ==========

ITEMS = [
    {"name": "响铃紧身衣", "english": "Belled Catsuit"},
    {"name": "比利十铃", "english": "Billy Ten-Bells"},
    {"name": "助跳哑铃", "english": "Halteres"},
    {"name": "棒铃", "english": "Meels"},
    {"name": "回旋刺靶", "english": "Quintain"},
]


def process_items(report: dict) -> None:
    src_path = SRC_DIR / "道具.md"
    text = src_path.read_text(encoding="utf-8")
    text = merge_crossline_bold(text)
    target_path = ORG_DIR / "装备_魔法物品" / "货品服务" / "page_212.md"
    if not target_path.exists():
        write_text_preserve(target_path, "# 炼金物质和毒药\n\n", "\n")
    existing, _ = read_text_preserve(target_path)

    marker_section = make_hidden_marker("道具.md", "训练道具")
    if marker_section in existing:
        report["skipped"].append("MAH 训练道具小节已存在")
        return

    blocks = split_section_by_entries(text, ITEMS)

    lines = [f"\n{marker_section}\n", "\n## 武术手册MAH 特有 训练道具\n\n"]
    for it in ITEMS:
        block = blocks.get(it["name"])
        if block is None:
            report["warnings"].append(f"未找到物品块: {it['name']}")
            continue
        marker = make_hidden_marker("道具.md", it["name"])
        lines.append(f"{marker}\n")
        lines.append(f"### {it['name']}（{it['english']}）\n")
        lines.append(f"{make_source_annotation('道具.md', '道具')}\n")
        lines.append(f"{block}\n\n")
        report["merged"].append({"type": "物品", "name": it["name"], "target": str(target_path.relative_to(ORG_DIR))})

    append_to_file(target_path, "".join(lines))


# ========== 报告 ==========

def write_report(report: dict) -> None:
    report_path = REPORT_DIR / "MAH_reorganization_report.md"
    plan_path = REPORT_DIR / "MAH_reorganization_plan.json"

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
    process_feats(report)
    process_slayer_talents(report)
    process_style_strikes(report)
    process_infusions(report)
    process_weapons(report)
    process_items(report)
    write_report(report)

    print(f"整理完成。合并 {len(report['merged'])} 项，跳过 {len(report['skipped'])} 项，警告 {len(report['warnings'])} 项。")
    if report["warnings"]:
        for w in report["warnings"]:
            print(f"  警告: {w}")


if __name__ == "__main__":
    main()
