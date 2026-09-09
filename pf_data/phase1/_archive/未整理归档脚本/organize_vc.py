#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""整理 反派法典VC（Villain Codex）内容到已有分类目录。

本次处理：
- 职业变体（女巫、吟游诗人、通灵者）
- 专长（专长22.md）
- 神秘仪式
- page_1036.md（蛇牙院新规则）
- 物品10.md（通过对应 GB2312 HTML 源文件 物品10.htm 解析）

原则：
- 仅追加到 pf_rules_md_organized/ 下已有分类目录的对应文件。
- 每个条目在标题下一行标注来源。
- 使用隐藏标记去重；已存在的条目跳过并记录为重复。
- 不修改原 pf_rules_md/ 目录。
"""

import json
import os
import re

BASE = "/Users/chezi/code/java/pf_agent/pf_data/phase1"
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/反派法典VC")
ORG_BASE = os.path.join(BASE, "pf_rules_md_organized")
PLAN_PATH = os.path.join(BASE, "VC_reorganization_plan.json")
REPORT_PATH = os.path.join(BASE, "VC_reorganization_report.md")
DUP_RECORD_PATH = os.path.join(BASE, "未整理目录重复记录.md")
PROBLEM_RECORD_PATH = os.path.join(BASE, "未整理目录整理问题记录.md")

# 物品10.md 对应的 GB2312 HTML 源文件（Markdown 版本格式极端混乱，无法可靠拆分）
ITEM10_HTML_PATH = "/Users/chezi/.openclaw/workspace/pf_rules/物品10.htm"

SOURCE_NOTE_TEMPLATE = "> 来源：恶棍志（Villain Codex）VC，页码见原书，未整理 → 反派法典VC → {section_title}"

# 物品10.htm 条目分类目标（按戒指/权杖/特定防具/特殊武器/奇物/普通货品服务）
VC_ITEM_TARGETS = {
    "ring": ("装备_魔法物品/魔法物品/戒指_权杖_法杖/反派法典VC_戒指.md", "# 反派法典VC 戒指"),
    "rod": ("装备_魔法物品/魔法物品/戒指_权杖_法杖/反派法典VC_权杖.md", "# 反派法典VC 权杖"),
    "armor": ("装备_魔法物品/特定魔法防具/反派法典VC_特定魔法防具.md", "# 反派法典VC 特定魔法防具"),
    "weapon": ("装备_魔法物品/武器/反派法典VC_特殊武器.md", "# 反派法典VC 特殊武器"),
    "wondrous": ("装备_魔法物品/魔法物品/奇物/反派法典VC_奇物.md", "# 反派法典VC 奇物"),
    "gear": ("装备_魔法物品/货品服务/反派法典VC_物品.md", "# 反派法典VC 物品"),
}

# 职业变体 / 职业选项条目（注意：源文件名与内容不一致，已按实际内容调整）
SECTIONS = [
    # 女巫变体（实际在 变体/page_1443.md）
    {"source": "变体/page_1443.md", "title": "魔镜女巫", "english": "Mirror Witch", "cls": "女巫", "section_title": "变体", "target": "职业/基础职业/女巫/page_70.md", "marker": "**魔镜女巫（女巫变体）"},
    # 吟游诗人变体
    {"source": "变体/page_1444.md", "title": "算命师傅", "english": "Fortune-Teller", "cls": "吟游诗人", "section_title": "变体", "target": "职业/核心职业/吟游诗人/page_38.md", "marker": "**算命师傅（Fortune-Teller）"},
    # 通灵者变体（标题跨行）
    {"source": "变体/通灵者1.md", "title": "虚空之声", "english": "Voice of the Void", "cls": "通灵者", "section_title": "变体", "target": "职业/异能冒险（Occult Adventures）/通灵者/page_262.md", "marker": "**虚空之声（Voice of the"},
]

KNOWN_LABELS = {
    "制造要求", "制造需求", "需求", "制造成本", "制造条件", "灵光", "灵氲", "位置", "栏位", "价格",
    "施法者等级", "重量", "类别", "描述", "来源", "出处", "效果", "先决条件",
    "专长效果", "通常", "特殊说明", "拥有此专长前的正常情况", "好处", "学派",
    "施放时间", "成分", "技能检定", "距离", "区域", "持续时间", "豁免", "法术抗力",
    "反冲", "失败", "CL", "成本", "制造", "运费", "运费（每英里）", "cl",
}


def load_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().splitlines()


def normalize_ws(text):
    return re.sub(r'\s+', ' ', text).strip()


# ---------------------------------------------------------------------------
# 物品10.htm 解析专用函数
# ---------------------------------------------------------------------------

_VC_ITEM_SECTION_HEADERS = {"――――描述――――", "――――制造――――"}
_VC_ITEM_WEAPON_KEYWORDS = ["鞭", "拳套", "刀", "箭", "闷棍", "灯笼", "链枷", "长鞭", "硬头锤", "水兵刀"]


def _html_to_text(html):
    """将 物品10.htm 的 GB2312 HTML 转换为近似 Markdown 的文本。"""
    text = re.sub(r'<BR\s*/?>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'</?(P|DIV|SPAN|FONT|IMG|HR|OBJECT|PARAM)[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<STRONG>', '**', text, flags=re.IGNORECASE)
    text = re.sub(r'</STRONG>', '**', text, flags=re.IGNORECASE)
    text = re.sub(r'<B>', '**', text, flags=re.IGNORECASE)
    text = re.sub(r'</B>', '**', text, flags=re.IGNORECASE)
    text = re.sub(r'<EM>', '*', text, flags=re.IGNORECASE)
    text = re.sub(r'</EM>', '*', text, flags=re.IGNORECASE)
    text = re.sub(r'<BLOCKQUOTE[^>]*>', '\n> ', text, flags=re.IGNORECASE)
    text = re.sub(r'</BLOCKQUOTE>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<A[^>]*>.*?</A>', '', text, flags=re.IGNORECASE | re.DOTALL)
    import html as ihtml
    text = ihtml.unescape(text)
    return text


def _normalize_meta_stars(line):
    """将 ****价格**： 这类嵌套星号归一化为 **价格**：。"""
    s = line.strip()
    m = re.match(r'^(\*{2,})([^*\s][^*:]*?)\s*[:：]\s*(.*)$', s)
    if m:
        label = m.group(2).strip('*').strip()
        if label in KNOWN_LABELS:
            return f"**{label}：**{m.group(3)}"
    return s


def _label_prefix(line):
    """返回行首可能的标签名（支持带 ** 或不带 **）。"""
    s = _normalize_meta_stars(line.strip())
    if s.startswith('**'):
        inner = s[2:].lstrip('*')
        return inner.split('：')[0].split('**')[0].strip()
    return s.split('：')[0].split()[0].strip()


def _is_vc_metadata_start(line):
    """判断一行是否是物品条目的元数据开头（如灵光、价格、栏位）。"""
    first = _label_prefix(line)
    return first in KNOWN_LABELS or first in _VC_ITEM_SECTION_HEADERS


def _is_vc_subitem_line(line):
    """排除胡德之饰等条目下的黑羽/黄铜叶等子项行。"""
    s = line.strip()
    if not s.startswith('**'):
        return False
    return bool(re.search(r'[）)]\s*\*+\s*：\s*[^*]*[一-鿿]', s))


def _is_vc_item_title_line(line):
    """判断一行是否是物品条目标题。"""
    s = _normalize_meta_stars(line.strip())
    if not s.startswith('**'):
        return False
    if not re.search(r'[一-鿿]', s):
        return False
    inner = s[2:].lstrip('*')
    if inner.startswith('<'):
        return False
    first = inner.split('：')[0].split('**')[0].strip()
    if first in KNOWN_LABELS or first in _VC_ITEM_SECTION_HEADERS:
        return False
    if _is_vc_subitem_line(s):
        return False
    if len(s) > 80:
        return False
    return True


def _clean_vc_item_title(title):
    """清理标题中的原始出处注记、PFS 标记，并补全 **。"""
    title = re.sub(r'\s*出自[^*]*', '', title)
    title = re.sub(r'\s*\*[^*]*Villain Codex[^*]*\*', '', title)
    title = re.sub(r'\s*PFS不可', '', title)
    title = title.strip()
    if title.startswith('**') and title.count('**') % 2 == 1:
        title = title + '**'
    title = re.sub(r'\*\*\s+', '**', title)
    title = re.sub(r'\s+\*\*', '**', title)
    return title


def _extract_vc_cn_title(title):
    """从清理后的标题中提取中文名（用于去重键）。"""
    s = title.strip('*').strip()
    m = re.match(r'^([一-鿿][一-鿿A-Za-z\s]*)', s)
    if m:
        return m.group(1).strip()
    return s.split('（')[0].split('(')[0].strip()


def _extract_vc_field(body_lines, labels):
    """从正文前几行提取指定标签的值（支持 **label：**value / **label**value / label：value）。"""
    for line in body_lines[:8]:
        s = _normalize_meta_stars(line.strip())
        for label in labels:
            # **label：**value
            if s.startswith(f'**{label}：'):
                return s[len(f'**{label}：'):].strip('*').strip()
            # **label**value
            if s.startswith(f'**{label}**'):
                return s[len(f'**{label}**'):].strip('*').strip()
            # label：value / label value
            if s.startswith(label):
                rest = s[len(label):].strip()
                if rest.startswith('：') or rest.startswith(':'):
                    rest = rest[1:].strip()
                return rest.strip('*').strip()
    return ''


def _has_vc_magic_aura(body_lines):
    """判断物品是否有魔法灵光/施法者等级等魔法物品特征。"""
    for line in body_lines[:8]:
        s = line.lower()
        if '灵光' in s or '灵氲' in s or '施法者等级' in s or s.startswith('cl'):
            return True
    return False


def _categorize_vc_item(title, body_lines):
    """根据标题与正文将物品归入 ring/rod/armor/weapon/wondrous/gear。"""
    cat = _extract_vc_field(body_lines, ['类别'])
    slot = _extract_vc_field(body_lines, ['栏位', '位置'])

    if cat in ['炼金工具', '冒险装备', '工具包', '交通工具，陆地', '交通工具', '炼金物品']:
        return 'gear'
    if '戒指' in title or 'Ring' in title or '戒指' in slot:
        return 'ring'
    if '权杖' in title or 'Rod' in title or '权杖' in slot:
        return 'rod'
    if any(k in title for k in _VC_ITEM_WEAPON_KEYWORDS):
        return 'weapon'
    if '护甲' in slot or '皮甲' in title or 'Pelt' in title:
        return 'armor'
    if not _has_vc_magic_aura(body_lines):
        return 'gear'
    return 'wondrous'


def _parse_vc_items10_html():
    """解析 物品10.htm，返回 [(清理后标题, 正文行列表, 分类)] 列表。"""
    if not os.path.exists(ITEM10_HTML_PATH):
        return []
    with open(ITEM10_HTML_PATH, 'r', encoding='gb2312', errors='ignore') as f:
        html = f.read()
    text = _html_to_text(html)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    lines = [re.sub(r'^译者：\w+\s+', '', l).strip() for l in lines]

    # 预合并：标题被换行切断时（如 **蹦跳拖鞋（Slippers of + Scampering）**）合并为一行。
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('**') and re.search(r'[一-鿿]', line) and not _is_vc_metadata_start(line):
            parts = [line]
            j = i + 1
            while j < len(lines) and not _is_vc_metadata_start(lines[j]):
                parts.append(lines[j])
                j += 1
            merged.append(' '.join(parts))
            i = j
        else:
            merged.append(line)
            i += 1
    lines = merged

    title_starts = [i for i, l in enumerate(lines) if _is_vc_item_title_line(l)]
    items = []
    for idx, start in enumerate(title_starts):
        end = title_starts[idx + 1] if idx + 1 < len(title_starts) else len(lines)
        item_lines = lines[start:end]
        raw_title = item_lines[0]
        body = item_lines[1:]
        clean_title = _clean_vc_item_title(raw_title)
        category = _categorize_vc_item(clean_title, body)
        items.append((clean_title, body, category))
    return items


def _normalize_vc_body_line(line):
    """简单归一化正文行：移除译者注、折叠嵌套星号。"""
    s = line.strip()
    if s.startswith("译者："):
        return ""
    # ****价格**：300GP → **价格：**300GP
    m = re.match(r'^\*{4,}([^*：\s]+?)\s*[:：]\s*(.*)$', s)
    if m and m.group(1) in KNOWN_LABELS:
        return f"**{m.group(1)}：**{m.group(2)}"
    # ****价格**：300GP（label 被 ** 包裹后再接 ：）
    m = re.match(r'^\*{4,}([^*：\s]+?)\*\*\s*[:：]\s*(.*)$', s)
    if m and m.group(1) in KNOWN_LABELS:
        return f"**{m.group(1)}：**{m.group(2)}"
    # **价格**300GP → **价格：**300GP（仅当值不以冒号开头）
    m = re.match(r'^\*\*([^*]+?)\*\*([^：].*)$', s)
    if m and m.group(1) in KNOWN_LABELS:
        return f"**{m.group(1)}：**{m.group(2)}"
    return s


def _build_vc_html_item_block(title, body_lines, section_title, source_file, cn_title):
    """为 HTML 解析出的物品构造带隐藏标记与来源注记的追加块。"""
    marker = f"<!-- VC-source:{source_file}:{cn_title} -->"
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title)
    normalized_body = [l for l in (_normalize_vc_body_line(l) for l in body_lines) if l]
    result = [marker, title, note]
    result.extend(normalized_body)
    if result and result[-1].strip() != "":
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"

    for i, line in enumerate(lines):
        if marker in line:
            return i
    raise ValueError(f"在 {source} 中未找到标记: {marker!r}")


def already_present(target_text, section):
    marker_key = f"<!-- VC-source:{section['source']}:{section['title']} -->"
    if marker_key in target_text:
        return True, "hidden_marker"
    if section.get("duplicate_skip"):
        checks = [section["title"], section.get("english", "")]
        for c in checks:
            if c and c in target_text:
                return True, f"existing_content ({c})"
    return False, None


def extract_section(source_lines, start_idx, end_idx):
    return source_lines[start_idx:end_idx]


def normalize_section_lines(section_lines):
    """修正标题与正文挤在同一行的情况（如 **标题** *****正文）。"""
    result = []
    for line in section_lines:
        # 匹配标题块后接 2+ 星号分隔符再接正文（常见 3-5 个星号）
        m = re.match(r'^(\*\*.*?\*\*)(\*{2,})(\*?.*)$', line)
        if m:
            result.append(m.group(1))
            body = m.group(3).lstrip('*')
            if body:
                result.append(body)
        else:
            result.append(line)
    return result


def split_title_body(section_lines):
    """将片段拆分为标题行与正文行。标题为开头连续的加粗块。"""
    section_lines = normalize_section_lines(section_lines)
    title_end = 0
    for i, line in enumerate(section_lines):
        s = line.strip()
        if not s:
            if title_end > 0:
                break
            continue
        if title_end == 0:
            title_end = i + 1
            continue
        prev = section_lines[i - 1].strip()
        if prev.endswith("**"):
            break
        title_end = i + 1
    return section_lines[:title_end], section_lines[title_end:]


def build_append_block(section, section_lines, section_title=None):
    title_lines, body_lines = split_title_body(section_lines)
    note = SOURCE_NOTE_TEMPLATE.format(section_title=section_title or section.get("section_title", ""))
    marker = f"<!-- VC-source:{section['source']}:{section['title']} -->"
    result = [marker]
    result.extend(title_lines)
    result.append(note)
    result.extend(body_lines)
    if result and result[-1].strip() != "":
        result.append("")
    result.append("")
    return "\n".join(result) + "\n"


def append_to_target(target_path, block):
    full_path = os.path.join(ORG_BASE, target_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    mode = "a" if os.path.exists(full_path) else "w"
    with open(full_path, mode, encoding="utf-8") as f:
        f.write(block)


def ensure_header(target_path, header):
    full_path = os.path.join(ORG_BASE, target_path)
    if not os.path.exists(full_path) or os.path.getsize(full_path) == 0:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(header + "\n\n")


def find_index(lines, marker, source):
    for i, line in enumerate(lines):
        if marker in line:
            return i
    raise ValueError(f"在 {source} 中未找到标记: {marker!r}")


def process_source_sections(secs, stats, duplicates, plan_sections):
    """处理通用 SECTIONS 配置。"""
    grouped = {}
    for sec in secs:
        grouped.setdefault(sec["source"], []).append(sec)

    for source, src_secs in grouped.items():
        src_path = os.path.join(SRC_DIR, source)
        if not os.path.exists(src_path):
            stats["errors"].append(f"源文件不存在: {source}")
            continue
        lines = load_lines(src_path)
        indices = []
        for sec in src_secs:
            try:
                idx = find_index(lines, sec["marker"], source)
                indices.append((idx, sec))
            except ValueError as e:
                stats["errors"].append(str(e))
        indices.sort(key=lambda x: x[0])

        for i, (start_idx, sec) in enumerate(indices):
            end_idx = indices[i + 1][0] if i + 1 < len(indices) else len(lines)
            target_path = sec["target"]
            full_target = os.path.join(ORG_BASE, target_path)
            target_text = ""
            if os.path.exists(full_target):
                target_text = open(full_target, "r", encoding="utf-8").read()

            present, reason = already_present(target_text, sec)
            if present:
                duplicates.append({
                    "source": source,
                    "title": sec["title"],
                    "english": sec.get("english", ""),
                    "target": target_path,
                    "reason": reason,
                })
                stats["skipped"] += 1
                plan_sections.append({**sec, "action": "skipped", "reason": reason})
                continue

            section_lines = extract_section(lines, start_idx, end_idx)
            block = build_append_block(sec, section_lines)
            append_to_target(target_path, block)
            stats["added"] += 1
            plan_sections.append({**sec, "action": "added"})


def detect_title_starts(lines, max_len=80):
    """自动检测以中文名称开头的标题行位置（用于专长/仪式）。"""
    starts = []
    for i, line in enumerate(lines):
        s = line.strip()
        while s.startswith("*"):
            s = s[1:]
        s = s.strip()
        if not s or len(s) > max_len:
            continue
        if s[-1] in "。！？":
            continue
        m = re.match(r"([一-鿿][一-鿿\w]*)\s*[(（A-Za-z]", s)
        if not m:
            continue
        first = m.group(1)
        if first in KNOWN_LABELS:
            continue
        starts.append((i, s))
    return starts


def remove_vc_page_1036_entries():
    """从目标文件中移除所有 page_1036.md 产生的 VC-source 块，便于重跑修正。

    只删除以 `<!-- VC-source:page_1036.md:... -->` 开头、到下一个任意来源
    hidden_marker 或文件末尾为止的块，避免误删其他来源书条目。
    """
    targets = [
        "职业/基础职业/先知/page_88.md",
        "职业/基础职业/先知/先知诅咒全扩展.md",
        "职业/基础职业/忍者/忍者职业变体.md",
        "专长/反派法典VC_专长.md",
    ]
    # 匹配 page_1036 块：从 VC-source:page_1036.md:... 开始，直到下一个 <!-- XX-source: 或文件结束
    marker_re = re.compile(
        r'<!-- VC-source:page_1036\.md:[^>]+ -->.*?(?=<!-- [A-Z][A-Za-z]*-source:|\Z)',
        re.DOTALL,
    )
    for rel in targets:
        full = os.path.join(ORG_BASE, rel)
        if not os.path.exists(full):
            continue
        with open(full, "r", encoding="utf-8") as f:
            text = f.read()
        new_text = marker_re.sub('', text)
        if new_text == text:
            continue
        with open(full, "w", encoding="utf-8") as f:
            f.write(new_text)


# 物品10.md 标题检测专用：过滤已知的非标题前缀
_ITEM10_NON_TITLES = {
    "灵光", "灵氲", "施法者等级", "位置", "栏位", "价格", "重量", "类别", "描述",
    "制造要求", "制造条件", "制造成本", "需求", "来源", "出处", "效果",
    "制造", "栏位", "出处", "PFS不可",
}


def _normalize_item10_lines(lines):
    """合并标题跨行、图片标签跨行等，返回规范化后的行列表。"""
    # 先拼成文本，统一处理跨行
    text = "\n".join(lines)
    # 移除图片标签
    text = re.sub(r'!\[\[.*?\]\]\s*', '', text)
    # 合并被换行切断的英文括号：
    #   （Word\nWord） -> （Word Word）
    text = re.sub(r'([（(][A-Za-z\s\-\'’]*)\n+([A-Za-z\s\-\'’]*[）)])', r'\1\2', text)
    # 合并 **中文\nEnglish** 类标题
    text = re.sub(r'(\*\*[^*\n]+)\n+([^*\n]*\*\*)', r'\1\2', text)
    # 合并 **中文 English\n后续（无关闭星号）类标题：若一行以 ** 开头且无关闭 **，下一行非空则合并
    lines = text.splitlines()
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # 若当前行以 ** 开头但未闭合（奇数个 ** 块），且下一行看起来是标题延续
        while line.strip().startswith('**') and line.count('**') % 2 == 1 and i + 1 < len(lines):
            nxt = lines[i + 1]
            # 若下一行仍以 ** 开头，不合并（那是新标题）
            if nxt.strip().startswith('**'):
                break
            line = line.rstrip() + ' ' + nxt.lstrip()
            i += 1
        merged.append(line)
        i += 1
    return merged


def _is_item10_title(line):
    s = line.strip()
    # 去掉首尾星号（粗略）
    while s.startswith('*'):
        s = s[1:]
    # 保留完整标题内部星号用于判断
    inner = s.strip()
    if not inner or len(inner) > 120:
        return False
    # 必须包含中文
    if not re.search(r'[一-鿿]', inner):
        return False
    # 排除已知非标题前缀
    first = inner.split('（')[0].split()[0].strip('*').strip()
    if first in _ITEM10_NON_TITLES:
        return False
    # 必须看起来像标题：中文后跟英文括号或空格+英文
    if re.search(r'[一-鿿][^*]*[（(][A-Za-z][A-Za-z\s\-\'’]*[）)]', inner):
        return True
    if re.search(r'[一-鿿]\s+[A-Za-z][A-Za-z\s\-\'’]*(?:PFS不可)?$', inner):
        return True
    if re.search(r'[一-鿿][A-Za-z][A-Za-z\s\-\'’]*(?:PFS不可)?$', inner):
        return True
    return False


def _extract_item10_title(line):
    """从标题行提取中文名与英文名。"""
    s = line.strip()
    while s.startswith('*'):
        s = s[1:]
    # 尝试匹配 **中文名（English）**
    m = re.search(r'\*\*([^*]+?\s*[（(][A-Za-z][A-Za-z\s\-\'’]*[）)])\*\*', s)
    if m:
        return normalize_ws(m.group(1))
    # 尝试匹配 **中文名**English
    m = re.search(r'\*\*([^*]+?)\*\*\s*([A-Za-z][A-Za-z\s\-\'’]*)', s)
    if m:
        cn = m.group(1).strip()
        en = m.group(2).strip()
        return f"{cn}（{en}）"
    # 尝试匹配 **中文名English ...
    m = re.search(r'\*\*([^*]+?)([A-Za-z][A-Za-z\s\-\'’]*(?:PFS不可)?)', s)
    if m:
        cn = m.group(1).strip()
        en = m.group(2).strip()
        return f"{cn}（{en}）"
    return normalize_ws(s.strip('*').strip())


def process_items10(stats, duplicates, plan_sections):
    """处理 物品10.md：按标题拆分为条目，全部归入 VC 物品文件。"""
    src_path = os.path.join(SRC_DIR, "物品10.md")
    if not os.path.exists(src_path):
        stats["errors"].append("物品10.md 不存在")
        return
    lines = load_lines(src_path)
    merged = _normalize_item10_lines(lines)

    # 找出标题行
    title_indices = []
    for idx, line in enumerate(merged):
        if _is_item10_title(line):
            title_indices.append(idx)

    if not title_indices:
        stats["errors"].append("物品10.md 中未检测到标题")
        return

    target_path = "装备_魔法物品/货品服务/反派法典VC_物品.md"
    header = "# 反派法典VC 物品"
    ensure_header(target_path, header)

    for idx, start_idx in enumerate(title_indices):
        end_idx = title_indices[idx + 1] if idx + 1 < len(title_indices) else len(merged)
        section_lines = merged[start_idx:end_idx]
        title_text = _extract_item10_title(section_lines[0])
        # 提取中文名作为去重键
        short_title = title_text.split('（')[0].strip()

        sec = {
            "source": "物品10.md",
            "title": short_title,
            "english": "",
            "target": target_path,
            "section_title": "物品",
        }
        full_target = os.path.join(ORG_BASE, target_path)
        target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

        present, reason = already_present(target_text, sec)
        if present:
            duplicates.append({
                "source": "物品10.md",
                "title": short_title,
                "english": "",
                "target": target_path,
                "reason": reason,
            })
            stats["skipped"] += 1
            plan_sections.append({**sec, "action": "skipped", "reason": reason})
            continue

        block = build_append_block(sec, section_lines, section_title="物品")
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def process_page_1036(stats, duplicates, plan_sections):
    """处理 page_1036.md：先知秘示域、先知诅咒、忍者变体、专长。"""
    src_path = os.path.join(SRC_DIR, "page_1036.md")
    if not os.path.exists(src_path):
        stats["errors"].append("page_1036.md 不存在")
        return
    text = open(src_path, "r", encoding="utf-8").read()

    # page_1036.md 中实际条目位置由显式标记确定，避免误匹配章节小标题
    entries = [
        {"title": "苦修", "english": "Ascetic", "marker": "**苦修（Ascetic）【先知秘示域】", "target": "职业/基础职业/先知/page_88.md", "section_title": "先知秘示域", "header": "# 先知（Oracle）职业变体"},
        {"title": "毒血", "english": "Toxic Blood", "marker": "**毒血（Toxic", "target": "职业/基础职业/先知/先知诅咒全扩展.md", "section_title": "先知诅咒", "header": "# 先知全诅咒资源"},
        {"title": "蝮狩忍", "english": "Hunting Serpent", "marker": "**蝮狩忍（Hunting Serpent）", "target": "职业/基础职业/忍者/忍者职业变体.md", "section_title": "忍者变体", "header": "# 忍者职业变体"},
        {"title": "贰牙突", "english": "Twin Fang Lunge", "marker": "**贰牙突（Twin Fang Lunge）【战斗】", "target": "专长/反派法典VC_专长.md", "section_title": "专长", "header": "# 反派法典VC 专长"},
        {"title": "贰牙击", "english": "Twin Fang Strike", "marker": "**贰牙击（Twin Fang Strike）【战斗】", "target": "专长/反派法典VC_专长.md", "section_title": "专长", "header": "# 反派法典VC 专长"},
        {"title": "贰牙流", "english": "Twin Fang Style", "marker": "**贰牙流（Twin Fang Style）【战斗，流派】", "target": "专长/反派法典VC_专长.md", "section_title": "专长", "header": "# 反派法典VC 专长"},
    ]

    positions = []
    for ent in entries:
        idx = text.find(ent["marker"])
        if idx == -1:
            stats["errors"].append(f"page_1036.md 中未找到标记: {ent['marker']}")
            continue
        positions.append((idx, ent))
    positions.sort(key=lambda x: x[0])

    for i, (start, ent) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        section_text = text[start:end].strip()
        section_lines = section_text.splitlines()

        sec = {
            "source": "page_1036.md",
            "title": ent["title"],
            "english": ent["english"],
            "target": ent["target"],
            "section_title": ent["section_title"],
        }

        ensure_header(ent["target"], ent["header"])
        full_target = os.path.join(ORG_BASE, ent["target"])
        target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

        present, reason = already_present(target_text, sec)
        if present:
            duplicates.append({
                "source": "page_1036.md",
                "title": ent["title"],
                "english": ent["english"],
                "target": ent["target"],
                "reason": reason,
            })
            stats["skipped"] += 1
            plan_sections.append({**sec, "action": "skipped", "reason": reason})
            continue

        block = build_append_block(sec, section_lines)
        append_to_target(ent["target"], block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def process_auto_split_file(source_file, target_path, section_title, header, stats, duplicates, plan_sections):
    """对 专长22.md / 神秘仪式.md / 物品10.md 按自动检测的标题行拆分并合并。"""
    src_path = os.path.join(SRC_DIR, source_file)
    if not os.path.exists(src_path):
        stats["errors"].append(f"源文件不存在: {source_file}")
        return
    lines = load_lines(src_path)
    starts = detect_title_starts(lines)
    if not starts:
        stats["errors"].append(f"{source_file} 中未检测到标题")
        return

    ensure_header(target_path, header)

    for idx, (start_idx, title_line) in enumerate(starts):
        end_idx = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        short_title = title_line.split("（")[0].split(" ")[0].strip("*")
        sec = {
            "source": source_file,
            "title": short_title,
            "english": "",
            "target": target_path,
            "section_title": section_title,
        }
        full_target = os.path.join(ORG_BASE, target_path)
        target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

        present, reason = already_present(target_text, sec)
        if present:
            duplicates.append({
                "source": source_file,
                "title": short_title,
                "english": "",
                "target": target_path,
                "reason": reason,
            })
            stats["skipped"] += 1
            plan_sections.append({**sec, "action": "skipped", "reason": reason})
            continue

        section_lines = extract_section(lines, start_idx, end_idx)
        block = build_append_block(sec, section_lines, section_title=section_title)
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def process_items10_html(stats, duplicates, plan_sections):
    """处理 物品10.htm：解析 HTML 源文件，按条目分类写入装备目录。"""
    items = _parse_vc_items10_html()
    if not items:
        stats["errors"].append("物品10.htm 未解析到任何条目或文件不存在")
        return

    source_file = "物品10.md"
    for title, body_lines, category in items:
        cn_title = _extract_vc_cn_title(title)
        target_path, header = VC_ITEM_TARGETS[category]
        section_title = "物品"
        sec = {
            "source": source_file,
            "title": cn_title,
            "english": "",
            "target": target_path,
            "section_title": section_title,
        }

        ensure_header(target_path, header)
        full_target = os.path.join(ORG_BASE, target_path)
        target_text = open(full_target, "r", encoding="utf-8").read() if os.path.exists(full_target) else ""

        present, reason = already_present(target_text, sec)
        if present:
            duplicates.append({
                "source": source_file,
                "title": cn_title,
                "english": "",
                "target": target_path,
                "reason": reason,
            })
            stats["skipped"] += 1
            plan_sections.append({**sec, "action": "skipped", "reason": reason})
            continue

        block = _build_vc_html_item_block(title, body_lines, section_title, source_file, cn_title)
        append_to_target(target_path, block)
        stats["added"] += 1
        plan_sections.append({**sec, "action": "added"})


def main():
    stats = {"added": 0, "skipped": 0, "errors": []}
    duplicates = []
    plan_sections = []

    # 1. 职业变体 / 职业选项
    process_source_sections(SECTIONS, stats, duplicates, plan_sections)

    # 2. 专长
    feat_target = "专长/反派法典VC_专长.md"
    process_auto_split_file("专长22.md", feat_target, "专长", "# 反派法典VC 专长", stats, duplicates, plan_sections)

    # 3. 神秘仪式
    process_auto_split_file("神秘仪式.md", "法术/反派法典VC_神秘仪式.md", "神秘仪式", "# 反派法典VC 神秘仪式", stats, duplicates, plan_sections)

    # 4. page_1036.md（蛇牙院新规则）
    remove_vc_page_1036_entries()
    process_page_1036(stats, duplicates, plan_sections)

    # 5. 物品10.md（通过对应 HTML 源文件处理）
    process_items10_html(stats, duplicates, plan_sections)

    # 6. 写入计划文件
    plan = {
        "source_book": "反派法典VC",
        "source_book_english": "Villain Codex",
        "source_dir": "pf_data/phase1/pf_rules_md/未整理/反派法典VC",
        "stats": stats,
        "sections": plan_sections,
        "skipped_files": [],
    }
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    # 6. 写入报告
    report_lines = [
        "# 反派法典VC 整理报告",
        "",
        "## 整理策略",
        "",
        "反派法典VC（Villain Codex）内容分散在 `变体/`、`专长22.md`、`神秘仪式.md`、`page_1036.md`、`物品10.md` 等文件中。",
        "本次将职业变体、专长、神秘仪式、page_1036.md 新规则、物品10.md（通过对应 GB2312 HTML 源文件解析）按条目合并到 `pf_rules_md_organized/` 下对应职业的已有页面或来源书专属文件中。",
        "",
        "## 源目录",
        "",
        "- `pf_data/phase1/pf_rules_md/未整理/反派法典VC/`",
        "- `~/.openclaw/workspace/pf_rules/物品10.htm`（用于解析物品条目）",
        "",
        "## 处理统计",
        "",
        f"- 新增条目：{stats['added']}",
        f"- 跳过重复：{stats['skipped']}",
        f"- 错误：{len(stats['errors'])}",
        "",
        "## 物品10 分类汇总",
        "",
    ]
    # 统计各分类新增数量
    cat_counts = {}
    for sec in plan_sections:
        if sec.get("action") == "added" and sec.get("source") == "物品10.md":
            cat = None
            for k, (tp, _) in VC_ITEM_TARGETS.items():
                if tp == sec.get("target"):
                    cat = k
                    break
            if cat:
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
    cat_names = {"ring": "戒指", "rod": "权杖", "armor": "特定魔法防具", "weapon": "特殊武器", "wondrous": "奇物", "gear": "货品服务"}
    for cat, name in cat_names.items():
        report_lines.append(f"- {name}：{cat_counts.get(cat, 0)} 条")
    report_lines.append("")
    if stats["errors"]:
        report_lines.extend(["", "## 错误", ""])
        for e in stats["errors"]:
            report_lines.append(f"- {e}")
    if duplicates:
        report_lines.extend(["", "## 重复/跳过项", ""])
        for d in duplicates:
            en = f" / {d['english']}" if d["english"] else ""
            report_lines.append(f"- `{d['source']}` `{d['title']}{en}` → `{d['target']}`（原因：{d['reason']}）")
    report_lines.extend(["", "## 验证清单", "", "- [ ] 原目录未被修改", "- [ ] 新增条目均出现 `> 来源：` 标注", "- [ ] 标注位于条目标题下一行", "- [ ] 未重复追加", "- [ ] 进度文档已更新", "- [ ] 已提交 Git", ""])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    # 6. 重复记录
    if duplicates:
        dup_lines = ["", "", "## 反派法典VC（Villain Codex）", "", f"**发现时间**：2026-06-19", ""]
        dup_lines.append("| 来源文件 | 条目 | 目标文件 | 备注 |")
        dup_lines.append("|----------|------|----------|------|")
        for d in duplicates:
            en = f" / {d['english']}" if d["english"] else ""
            dup_lines.append(f"| {d['source']} | {d['title']}{en} | {d['target']} | {d['reason']} |")
        dup_lines.append("")
        with open(DUP_RECORD_PATH, "a", encoding="utf-8") as f:
            f.write("\n".join(dup_lines))

    # 7. 问题记录（避免重复追加）
    if os.path.exists(PROBLEM_RECORD_PATH):
        problem_text = open(PROBLEM_RECORD_PATH, "r", encoding="utf-8").read()
    else:
        problem_text = ""

    def ensure_problem(anchor, block):
        nonlocal problem_text
        if anchor not in problem_text:
            problem_text += block
            with open(PROBLEM_RECORD_PATH, "a", encoding="utf-8") as f:
                f.write(block)

    ensure_problem("VC-PAGE1036", """

## 反派法典VC（Villain Codex）

### VC-PAGE1036：page_1036.md 内容严重混行，暂未处理

- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：`需要人工校验`
- **涉及文件**：`pf_rules_md/未整理/反派法典VC/page_1036.md`
- **问题描述**：该文件包含蛇牙院的先知秘示域（苦修）、先知诅咒（毒血）、忍者变体（蝮狩忍）及蛇牙院专长（贰牙流系列）。由于 Markdown 转换问题，多个条目标题与正文被挤在同一行或相邻行中（例如 `**绝杀（Certain` 的标题续行与 `**专长（Feats）**` 乃至 `**贰牙突` 位于同一行），导致按行拆分极易割裂条目，无法可靠地将内容分别合并到先知、忍者与专长目录。
- **当前处理**：本次未合并 `page_1036.md`，其余内容（女巫/吟游诗人/通灵者变体、专长22.md、神秘仪式）已正常处理。
- **备注**：建议读取对应 HTML 文件（`page_1036.html`）或人工按条目切分后再处理。
""")

    ensure_problem("VC-ITEMS", """

### VC-ITEMS：物品10.md 格式混乱，暂未处理

- **问题归类**：`markdown格式` / `标题定位`
- **严重程度**：`需要人工校验`
- **涉及文件**：`pf_rules_md/未整理/反派法典VC/物品10.md`
- **问题描述**：物品文件存在大量格式问题：
  - 标题跨行（如 `**动物面具（Animal` + `Mask）**`）；
  - 部分条目以 `![[图片]]` 图片标签开头，导致标题行不以 `**` 开头；
  - 元数据标签写法不统一（`栏位：无`、`灵光 微弱变化系`、`**类别**：炼金工具**描述**：...` 等）；
  - 中英名称混排且无统一分隔。
  自动拆分极易出错，可能把描述段落误当作标题，或将同一物品拆成多段。
- **当前处理**：本次未合并 `物品10.md`。
- **备注**：建议后续读取对应 HTML 文件（`物品10.htm`）或人工逐条切分后再合并到 `装备_魔法物品/` 各子目录。
""")

    print(f"整理完成：新增 {stats['added']} 条，跳过 {stats['skipped']} 条，错误 {len(stats['errors'])} 条。")
    if stats["errors"]:
        for e in stats["errors"]:
            print("  ERROR:", e)


if __name__ == "__main__":
    main()
