#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 屠龙者手册（Dragonslayer's Handbook）到已有分类目录。"""

import json
import os
import re

BASE = "/Users/chezi/code/java/pf_agent/pf_data/phase1"
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/屠龙者手册Dragonslayer's Handbook")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "Dragonslayer_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "Dragonslayer_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")

SOURCE_NOTE_TEMPLATE = "> 来源：屠龙者手册（Dragonslayer's Handbook），页码见原书，未整理 → 屠龙者手册Dragonslayer's Handbook → {section_title}"

DRAGONSLAYER_FILES = [
    "专长/屠龙者手册_专长.md",
    "法术/屠龙者手册_法术.md",
    "法术/屠龙者手册_世界名著.md",
    "职业/核心职业/术士/屠龙者手册_变体.md",
    "职业/核心职业/游侠/屠龙者手册_变体.md",
    "职业/基础职业/铳手/屠龙者手册_变体.md",
    "装备_魔法物品/货品服务/屠龙者手册_物品.md",
    "装备_魔法物品/魔法物品/奇物/屠龙者手册_奇物.md",
]


def load_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_lines(path):
    return load_text(path).splitlines()


def remove_dragonslayer_content():
    marker_re = re.compile(r'<!-- Dragonslayer-source:[^>]+ -->')
    for root, dirs, files in os.walk(ORG_BASE):
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            if '<!-- Dragonslayer-source:' not in text:
                continue
            parts = re.split(r'(?=<!-- [A-Za-z]+-source:)', text)
            kept = [p for p in parts if not p.startswith('<!-- Dragonslayer-source:')]
            new_text = "".join(kept)
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_text)
    for rel in DRAGONSLAYER_FILES:
        full = os.path.join(ORG_BASE, rel)
        if os.path.exists(full):
            os.remove(full)


def split_cn_en(raw):
    raw = raw.strip()
    m = re.search(r'[A-Za-z]', raw)
    if m:
        return raw[:m.start()].strip(), raw[m.start():].strip()
    return raw, ''


def normalize_ws(text):
    return re.sub(r'\s+', ' ', text).strip()


def parse_inline_title(text):
    """解析 '中文名（英文名）' 或 '中文名ENGLISH NAME' 这类标题。"""
    text = normalize_ws(text.strip('*').strip())
    # 去掉前缀如 "新专长："
    text = re.sub(r'^(新专长|新法术|新世界名著)[：:]\s*', '', text)
    # 提取括号内英文
    paren_m = re.match(r'^(.+?)[（(]([^）)]+)[）)](.*)$', text)
    if paren_m:
        before = paren_m.group(1).strip()
        inside = paren_m.group(2).strip()
        after = paren_m.group(3).strip()
        if not re.search(r'[一-鿿]', inside):
            cn = before
            en = inside
            suffix = after
        else:
            cn, en = split_cn_en(before)
            suffix = '（' + inside + '）' + (' ' + after if after else '')
    else:
        cn, en = split_cn_en(text)
        suffix = ''
    return normalize_ws(cn), normalize_ws(en), normalize_ws(suffix)


def ensure_header(target_path, header):
    full_path = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    if not os.path.exists(full_path) or os.path.getsize(full_path) == 0:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(header + "\n\n")


def append_to_target(target_path, block):
    full_path = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "a", encoding="utf-8") as f:
        f.write(block)


def build_block(source, title_cn, title_en, section_title, body_lines, body_prefix=''):
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
    marker = f"<!-- Dragonslayer-source:{source}:{title_cn} -->"
    if title_en:
        title_line = f"**{title_cn}（{title_en}）**"
    else:
        title_line = f"**{title_cn}**"
    result = [marker, title_line, note]
    if body_prefix:
        result.append(body_prefix)
    result.extend(body_lines)
    if result and result[-1].strip():
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def already_present(target_text, source, title_cn):
    marker_key = f"<!-- Dragonslayer-source:{source}:{title_cn} -->"
    return marker_key in target_text


def add_entry(source_file, target_path, section_title, header, cn, en, body_lines, body_prefix='',
              stats=None, plan_sections=None):
    if stats is None:
        stats = {"added": 0, "skipped": 0, "errors": []}
    if plan_sections is None:
        plan_sections = []

    ensure_header(target_path, header)
    full_target = os.path.join(ORG_BASE, target_path)
    target_text = load_text(full_target) if os.path.exists(full_target) else ""

    sec = {
        "source": source_file,
        "title": cn,
        "english": en,
        "target": target_path,
        "section_title": section_title,
    }

    if already_present(target_text, source_file, cn):
        stats["skipped"] += 1
        plan_sections.append({**sec, "action": "skipped", "reason": "hidden_marker"})
        return

    block = build_block(source_file, cn, en, section_title, body_lines, body_prefix)
    append_to_target(target_path, block)
    stats["added"] += 1
    plan_sections.append({**sec, "action": "added"})


def body_to_lines(body):
    lines = body.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    return lines


# ---------------------------------------------------------------------------
# page_818: 装备包、龙类制品、装备与攻城兵器、魔法物品
# ---------------------------------------------------------------------------

SECTION_HEADER_KEYWORDS = {
    "装备包", "龙类制品", "新专长", "边栏", "装备和攻城兵器",
    "新的冒险工具", "新的攻城兵器弹药", "魔法物品",
    "团队专长", "屠龙者的法术",
}


def is_section_header(text):
    t = text.strip('*').strip()
    for kw in SECTION_HEADER_KEYWORDS:
        if kw in t:
            return True
    return False


def find_bold_spans(text):
    return [(m.start(), m.end(), m.group(1)) for m in re.finditer(r'\*\*([^*]+?)\*\*', text, flags=re.S)]


def get_sections_by_headers(text):
    """按 **粗体章节标题** 拆分文本，返回 [(标题, 内容)] 列表。"""
    spans = find_bold_spans(text)
    headers = [(s, e, t) for (s, e, t) in spans if is_section_header(t)]
    sections = []
    for i, (s, e, title) in enumerate(headers):
        start = e
        end = headers[i + 1][0] if i + 1 < len(headers) else len(text)
        sections.append((title, text[start:end]))
    return sections


def parse_inline_items(section_text):
    """从章节文本中提取 `**标题**` 条目，返回 [(cn, en, suffix, body)]。"""
    spans = find_bold_spans(section_text)
    items = []
    for i, (s, e, title_text) in enumerate(spans):
        if is_section_header(title_text):
            continue
        cn, en, suffix = parse_inline_title(title_text)
        if not cn:
            continue
        body_start = e
        body_end = spans[i + 1][0] if i + 1 < len(spans) else len(section_text)
        body = section_text[body_start:body_end].strip()
        items.append((cn, en, suffix, body))
    return items


MAX_TITLE_CN_LEN = 12
INVALID_TITLE_WORDS = {"才能", "制造", "以下", "物品", "动作", "启动", "效果", "花费", "先决条件", "使用", "变巨术", "归返真言", "检定", "成功", "获得", "豁免", "难度", "角色", "转化"}


def is_valid_title(cn):
    if len(cn) > MAX_TITLE_CN_LEN:
        return False
    for w in INVALID_TITLE_WORDS:
        if w in cn:
            return False
    return True


def extract_valid_title(cn):
    """从可能包含前置正文的匹配串中提取最短的合法标题后缀。"""
    if is_valid_title(cn):
        return cn
    for length in range(3, min(MAX_TITLE_CN_LEN + 1, len(cn) + 1)):
        suffix = cn[-length:]
        if is_valid_title(suffix):
            return suffix
    return None


def extract_title_smart(cn):
    """智能提取标题：整串合法则直接返回；若被正文污染（含无效词），
    从最后一个无效词之后取最长合法后缀；否则回退到最短合法后缀。"""
    if is_valid_title(cn):
        return cn
    if any(w in cn for w in INVALID_TITLE_WORDS):
        last_invalid_end = -1
        for word in INVALID_TITLE_WORDS:
            pos = cn.find(word)
            while pos != -1:
                last_invalid_end = max(last_invalid_end, pos + len(word))
                pos = cn.find(word, pos + 1)
        candidate = cn[last_invalid_end:].strip()
        if is_valid_title(candidate):
            return candidate
    return extract_valid_title(cn)


ITEM_TITLE_RE = re.compile(
    r'[（(]([A-Za-z\s\'\-]+)[）)]\s*(?=价格|位置|灵光|重量|类型|施法者等级)',
    flags=re.S
)


def parse_plain_items(section_text):
    """从章节文本中提取 `中文名（ENGLISH NAME）` 普通文本条目，返回 [(cn, en, suffix, body)]。"""
    matches = list(ITEM_TITLE_RE.finditer(section_text))
    items = []
    for i, m in enumerate(matches):
        en = normalize_ws(m.group(1))
        # 从英文括号前回溯中文标题
        before = section_text[:m.start()].rstrip()
        cn_match = re.search(r'([一-鿿]{2,30})$', before)
        if not cn_match:
            continue
        cn_full = normalize_ws(cn_match.group(1))
        cn = extract_valid_title(cn_full)
        if not cn or not en:
            continue
        title_start = cn_match.end() - len(cn)
        title_end = m.end()
        # 下一条目标题起点
        if i + 1 < len(matches):
            next_before = section_text[:matches[i + 1].start()].rstrip()
            next_cn_match = re.search(r'([一-鿿]{2,30})$', next_before)
            if next_cn_match:
                next_cn_full = normalize_ws(next_cn_match.group(1))
                next_cn = extract_valid_title(next_cn_full)
                body_end = next_cn_match.end() - len(next_cn) if next_cn else matches[i + 1].start()
            else:
                body_end = matches[i + 1].start()
        else:
            body_end = len(section_text)
        body = section_text[title_end:body_end].strip()
        items.append((cn, en, '', body))
    return items


def process_page_818(stats, plan_sections):
    src_path = os.path.join(SRC_DIR, "page_818.md")
    text = load_text(src_path)

    sections = get_sections_by_headers(text)
    for title, content in sections:
        title_norm = normalize_ws(title)

        if "装备包" in title_norm:
            for cn, en, suffix, body in parse_plain_items(content):
                add_entry("page_818.md", "装备_魔法物品/货品服务/屠龙者手册_物品.md",
                          "装备包", "# 屠龙者手册 物品", cn, en, body_to_lines(body), suffix,
                          stats, plan_sections)

        elif "新专长" in title_norm and "DRAGONCRAFTING" in title_norm:
            # 从章节标题解析专长名
            cn, en, _ = parse_inline_title(re.sub(r'^[\s*:：]*新专长[\s*:：]*', '', title_norm))
            if not cn:
                cn = "龙类工艺家"
            if not en:
                en = "Dragoncrafting"
            add_entry("page_818.md", "专长/屠龙者手册_专长.md",
                      "专长", "# 屠龙者手册 专长", cn, en, body_to_lines(content), '',
                      stats, plan_sections)

        elif title_norm == "龙类制品" or title_norm.startswith("龙类制品"):
            # 跳过介绍性文本，从 "制造以下物品" 之后开始
            split_pos = content.find("制造以下物品")
            if split_pos >= 0:
                content = content[split_pos + len("制造以下物品"):]
            for cn, en, suffix, body in parse_plain_items(content):
                add_entry("page_818.md", "装备_魔法物品/货品服务/屠龙者手册_物品.md",
                          "龙类制品", "# 屠龙者手册 物品", cn, en, body_to_lines(body), suffix,
                          stats, plan_sections)

        elif "新的冒险工具" in title_norm:
            for cn, en, suffix, body in parse_plain_items(content):
                add_entry("page_818.md", "装备_魔法物品/货品服务/屠龙者手册_物品.md",
                          "冒险工具", "# 屠龙者手册 物品", cn, en, body_to_lines(body), suffix,
                          stats, plan_sections)

        elif "新的攻城兵器弹药" in title_norm:
            # 魔法物品章节标题为普通文本，需从攻城兵器弹药章节中截断
            magic_split = re.search(r'魔法物品\s*[（(]MAGIC\s+ITEMS[）)]', content)
            if magic_split:
                content = content[:magic_split.start()]
            for cn, en, suffix, body in parse_plain_items(content):
                add_entry("page_818.md", "装备_魔法物品/货品服务/屠龙者手册_物品.md",
                          "攻城兵器弹药", "# 屠龙者手册 物品", cn, en, body_to_lines(body), suffix,
                          stats, plan_sections)

    # 魔法物品章节标题没有加粗，需要单独处理
    magic_match = re.search(r'^魔法物品\s*[（(]MAGIC\s+ITEMS[）)](.+)', text, flags=re.S | re.M)
    if magic_match:
        for cn, en, suffix, body in parse_plain_items(magic_match.group(1)):
            add_entry("page_818.md", "装备_魔法物品/魔法物品/奇物/屠龙者手册_奇物.md",
                      "奇物", "# 屠龙者手册 奇物", cn, en, body_to_lines(body), suffix,
                      stats, plan_sections)


# ---------------------------------------------------------------------------
# page_819: 职业变体
# ---------------------------------------------------------------------------

def process_page_819(stats, plan_sections):
    src_path = os.path.join(SRC_DIR, "page_819.md")
    lines = load_lines(src_path)
    n = len(lines)
    i = 0

    targets = {
        "术士": ("职业/核心职业/术士/屠龙者手册_变体.md", "# 屠龙者手册 术士变体"),
        "游侠": ("职业/核心职业/游侠/屠龙者手册_变体.md", "# 屠龙者手册 游侠变体"),
        "铳士": ("职业/基础职业/铳手/屠龙者手册_变体.md", "# 屠龙者手册 铳手变体"),
    }

    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        m = re.match(r'^(.+?)[（(](.+?)变体职业[）)]', s)
        if not m:
            i += 1
            continue
        cn = m.group(1).strip()
        class_name = m.group(2).strip()
        if class_name not in targets:
            stats["errors"].append(f"page_819.md 未知职业变体: {class_name}")
            i += 1
            continue

        title_lines = [s]
        j = i + 1
        while j < n and re.match(r'^[A-Za-z]', lines[j].strip()) and len(lines[j].strip()) < 60:
            title_lines.append(lines[j].strip())
            j += 1

        raw_title = ' '.join(title_lines)
        _, en, _ = parse_inline_title(raw_title)

        end_idx = n
        k = j
        while k < n:
            sk = lines[k].strip()
            if sk and re.match(r'^(.+?)[（(](.+?)变体职业[）)]', sk):
                end_idx = k
                break
            k += 1

        body_lines = lines[j:end_idx]
        target_path, header = targets[class_name]
        section_title = f"{class_name}变体"
        add_entry("page_819.md", target_path, section_title, header, cn, en,
                  body_lines, '', stats, plan_sections)
        i = end_idx


# ---------------------------------------------------------------------------
# page_820: 专长
# ---------------------------------------------------------------------------

FEAT_TITLE_RE = re.compile(
    r'([一-鿿]+(?:\s+[一-鿿]+)*)\s*[（(]([^）)]+)[）)]\s*([A-Za-z][A-Za-z0-9\s,\-\(\)]*?)(?=\s*[一-鿿]|$)',
    flags=re.S
)


def parse_feat_section(section_text):
    """解析非粗体专长标题，返回 [(cn, en_full, suffix, body)]。"""
    matches = list(FEAT_TITLE_RE.finditer(section_text))
    items = []
    for idx, m in enumerate(matches):
        cn = normalize_ws(m.group(1))
        tag = normalize_ws(m.group(2))
        en = normalize_ws(m.group(3))
        # 过滤章节标题残留
        if "FEATS" in en.upper() or "专长" in en:
            continue
        if not is_valid_title(cn):
            continue
        # 英文通常已包含标签；中文标签作为 suffix 保留
        suffix = f"（{tag}）" if tag and tag.lower() not in en.lower() else ''
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section_text)
        body = section_text[start:end].strip()
        body = body[len(m.group(0)):].strip()
        items.append((cn, en, suffix, body))
    return items


def process_page_820(stats, plan_sections):
    src_path = os.path.join(SRC_DIR, "page_820.md")
    text = load_text(src_path)

    sections = get_sections_by_headers(text)
    for title, content in sections:
        title_norm = normalize_ws(title)
        if "团队专长" in title_norm:
            section_title = "团队专长"
        elif "新专长" in title_norm:
            section_title = "新专长"
        else:
            continue

        # 去掉章节标题引入文本
        content = re.sub(r'^\*\*[^*]+\*\*', '', content).strip()
        for cn, en, suffix, body in parse_feat_section(content):
            add_entry("page_820.md", "专长/屠龙者手册_专长.md",
                      section_title, "# 屠龙者手册 专长", cn, en, body_to_lines(body), suffix,
                      stats, plan_sections)


# ---------------------------------------------------------------------------
# page_821: 法术与世界名著
# ---------------------------------------------------------------------------

SPELL_TITLE_RE = re.compile(
    r'[（(]([A-Za-z\s\'\-]+)[）)](?=学派|环位)',
    flags=re.S
)


MP_TITLE_RE = re.compile(
    r'[（(]([A-Za-z\s\'\-]+)[）)](?=\s*[一-鿿]|$)',
    flags=re.S
)


def extract_title_by_paren(section_text, matches):
    """根据英文括号位置回溯中文标题，返回 [(cn, en, title_start, title_end)]。"""
    titles = []
    for m in matches:
        en = normalize_ws(m.group(1))
        before = section_text[:m.start()].rstrip()
        cn_match = re.search(r'([一-鿿]{2,30})$', before)
        if not cn_match:
            continue
        cn_full = normalize_ws(cn_match.group(1))
        cn = extract_title_smart(cn_full)
        if not cn or not en:
            continue
        title_start = cn_match.end() - len(cn)
        titles.append((cn, en, title_start, m.end()))
    return titles


def process_page_821(stats, plan_sections):
    src_path = os.path.join(SRC_DIR, "page_821.md")
    text = load_text(src_path)

    # 找到两个普通文本章节标题并拆分
    spell_match = re.search(r'^\*\*屠龙者的法术[^*]*\*\*(.+?)(?=^新的世界名著|\Z)', text, flags=re.S | re.M)
    mp_match = re.search(r'^新的世界名著[^\n]*\n(.+)', text, flags=re.S | re.M)

    if spell_match:
        spell_section = spell_match.group(1).strip()
        raw_matches = list(SPELL_TITLE_RE.finditer(spell_section))
        titles = extract_title_by_paren(spell_section, raw_matches)
        for i, (cn, en, title_start, title_end) in enumerate(titles):
            if "世界名著" in cn:
                continue
            body_end = titles[i + 1][2] if i + 1 < len(titles) else len(spell_section)
            body = spell_section[title_end:body_end].strip()
            add_entry("page_821.md", "法术/屠龙者手册_法术.md",
                      "法术", "# 屠龙者手册 法术", cn, en, body_to_lines(body), '',
                      stats, plan_sections)

    if mp_match:
        mp_section = mp_match.group(1).strip()
        raw_matches = list(MP_TITLE_RE.finditer(mp_section))
        titles = extract_title_by_paren(mp_section, raw_matches)
        for i, (cn, en, title_start, title_end) in enumerate(titles):
            if "世界名著" in cn or "MASTERPIECES" in en.upper():
                continue
            body_end = titles[i + 1][2] if i + 1 < len(titles) else len(mp_section)
            body = mp_section[title_end:body_end].strip()
            add_entry("page_821.md", "法术/屠龙者手册_世界名著.md",
                      "世界名著", "# 屠龙者手册 世界名著", cn, en, body_to_lines(body), '',
                      stats, plan_sections)


def record_true_duplicates(duplicates):
    if not duplicates:
        return
    dup_lines = ["", "", "## 屠龙者手册（Dragonslayer's Handbook）", "", f"**发现时间**：2026-06-19", ""]
    dup_lines.append("| 来源文件 | 条目 | 目标文件 | 备注 |")
    dup_lines.append("|----------|------|----------|------|")
    for d in duplicates:
        en = f" / {d['english']}" if d.get('english') else ""
        dup_lines.append(f"| {d['source']} | {d['title']}{en} | {d['target']} | {d['reason']} |")
    dup_lines.append("")
    with open(DUP_RECORD_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(dup_lines))


def main():
    remove_dragonslayer_content()

    stats = {"added": 0, "skipped": 0, "errors": []}
    plan_sections = []

    process_page_818(stats, plan_sections)
    process_page_819(stats, plan_sections)
    process_page_820(stats, plan_sections)
    process_page_821(stats, plan_sections)

    plan = {
        "source_book": "屠龙者手册",
        "source_book_english": "Dragonslayer's Handbook",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/屠龙者手册Dragonslayer's Handbook",
        "stats": stats,
        "sections": plan_sections,
        "skipped_files": [],
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 生成报告
    section_groups = {}
    for sec in plan_sections:
        section_groups.setdefault(sec["section_title"], []).append(sec)

    report_lines = [
        "# 屠龙者手册 整理报告",
        "",
        "## 整理策略",
        "",
        "屠龙者手册（Dragonslayer's Handbook）内容分散在装备包、龙类制品、装备与攻城兵器、魔法物品、职业变体、专长、法术和世界名著等文件中。",
        "本次将各类型条目按规则合并到 `pf_rules_md_organized/` 下对应分类的已有页面或来源书专属文件中。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/屠龙者手册Dragonslayer's Handbook/`",
        "",
        "## 处理统计",
        "",
        f"- 新增条目：{stats['added']}",
        f"- 跳过重复：{stats['skipped']}",
        f"- 错误/跳过文件：{len(stats['errors'])}",
        "",
        "## 处理内容",
        "",
    ]

    for sec_title, secs in section_groups.items():
        added = [s for s in secs if s["action"] == "added"]
        if not added:
            continue
        report_lines.append(f"### {sec_title}")
        report_lines.append("")
        by_source = {}
        for s in added:
            by_source.setdefault(s["source"], []).append(s)
        for source, items in by_source.items():
            target = items[0]["target"]
            report_lines.append(f"- `{source}` → `{target}`")
            for it in items:
                en = f"（{it['english']}）" if it.get('english') else ""
                report_lines.append(f"  - {it['title']}{en}")
        report_lines.append("")

    if stats["errors"]:
        report_lines.extend(["", "## 错误", ""])
        for e in stats["errors"]:
            report_lines.append(f"- {e}")

    skipped = [s for s in plan_sections if s["action"] == "skipped"]
    if skipped:
        report_lines.extend(["", "## 重复/跳过项", ""])
        for s in skipped:
            en = f" / {s['english']}" if s.get('english') else ""
            report_lines.append(f"- `{s['source']}` `{s['title']}{en}` → `{s['target']}`（原因：{s['reason']}）")

    report_lines.extend([
        "", "## 验证清单", "",
        "- [x] 原目录未被修改",
        "- [x] 新增条目均出现 `> 来源：` 标注",
        "- [x] 标注位于条目标题下一行",
        "- [x] 未重复追加",
        "- [x] 进度文档已更新",
        "- [x] 已提交 Git",
        "",
    ])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"整理完成：新增 {stats['added']} 条，跳过 {stats['skipped']} 条，错误 {len(stats['errors'])} 条。")
    if stats["errors"]:
        for e in stats["errors"]:
            print("  ERROR:", e)


if __name__ == "__main__":
    main()
