#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 BOTD 神恩文件拆分逻辑（改进版）。"""

import os
import re

BASE = "/Users/chezi/code/java/pf_agent/pf_data/phase1"
SRC_DIR = os.path.join(BASE, "pf_rules_md/未整理/永罪之书BotD")

# 非魔神名称的标题/字段
BOON_SECTION_HEADERS = {
    "资源", "阵营", "领域", "子域", "子领域", "偏好武器", "邪徽", "神殿", "信徒",
    "爪牙", "仪典", "教派", "族类", "崇拜中心", "标志", "神圣动物", "神圣颜色",
    "服从仪典", "恶魔遵从", "恶魔服从", "遵从仪式",
    "神恩", "神恩-永罪仪典", "神恩-崇神仪典", "神恩-魔神仪典", "神恩-魔族仪典",
    "传音者神恩", "颂教者神恩", "卫道者神恩", "第一神恩", "第二神恩", "第三神恩",
    "特殊施法规则", "特殊召唤规则", "新法术", "异界盟友", "祭司的职责", "神庙和祭坛",
    "赐福——恶魔仪典", "赐福——魔族仪典", "赐福",
    "魔族仪典", "魔神仪典", "崇神仪典", "永罪仪典",
    "领地", "教条", "教派", "外貌",
}

# 英文常见非名字词
EN_COMMON_WORDS = {
    "boon", "boons", "lord", "lords", "the", "a", "an", "of", "and", "or",
    "pg", "page", "damned", "hell", "abyss", "abaddon", "demon", "devil",
}

# 阵营/描述词，出现在这些词说明不是魔神名称
ALIGNMENT_WORDS = {"混乱", "秩序", "中立", "善良", "邪恶"}


def load_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().splitlines()


def is_header_text(text):
    t = text.strip().rstrip("：:").replace("**", "")
    t = re.sub(r"〔注：.*〕", "", t).strip()
    return t in BOON_SECTION_HEADERS or t.startswith("神恩-") or t.startswith("赐福")


def normalize_boon_lines(lines):
    """预处理：修复加粗标记异常（未闭合、粘在一起）。返回 (normalized_lines, is_list_items)。"""
    out = []
    is_list = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        list_item = bool(re.match(r'^\s*\d+\*\*', s))

        # 1. 处理 glued bold: **杰萨尔达****饥渴之月的女主人**
        m = re.match(r'^(\*\*[^*]+?\*\*)(\*+)(.+)$', s)
        if m:
            out.append(m.group(1))
            is_list.append(list_item)
            rest = m.group(3).lstrip('*')
            if rest:
                out.append(line[:len(line) - len(s)] + '**' + rest + '**')
                is_list.append(list_item)
            i += 1
            continue

        # 2. 处理未闭合加粗：
        #    **巴巴托斯 Barbatos       → 下一行 ****被须领主**
        #    **怒加，耀目天灾           → 后续 N 行英文，再 ****阵营：**
        if s.startswith('**') and not s.endswith('**') and i + 1 < n:
            next_s = lines[i + 1].strip()
            if next_s.startswith('****'):
                out.append(line.rstrip() + '**')
                is_list.append(list_item)
                i += 2
                continue
            # 探测后续最多 3 行，若出现以 **** 开头行，则合并为标题
            lookahead = []
            found_end = False
            for offset in range(1, 4):
                if i + offset >= n:
                    break
                la = lines[i + offset].strip()
                # 只合并“标题+英文+****字段”这种三行未闭合标题；
                # 普通跨行英文以 ** 结尾的留给 parse_deity_title 的 D 模式处理。
                if la.startswith('****'):
                    found_end = True
                    break
                if la == '---' or la.startswith('['):
                    break
                lookahead.append(lines[i + offset])
            if found_end and lookahead:
                merged = line.rstrip() + ' ' + ' '.join(la.strip() for la in lookahead) + '**'
                out.append(merged)
                is_list.extend([list_item] + [False] * len(lookahead))
                # 跳过合并掉的行
                i += 1 + len(lookahead)
                continue

        # 3. 列表前缀 02**阿洛斯 Alocer** → 去掉数字前缀
        if list_item:
            out.append(re.sub(r'^(\s*)\d+', r'\1', line))
            is_list.append(True)
            i += 1
            continue

        out.append(line)
        is_list.append(False)
        i += 1
    return out, is_list


# 宽松字符集合
CN_CHARS = r'[一-鿿][一-鿿\w\s·\/\-，、——…]*?'
EN_CHARS = r'[A-Za-z][A-Za-z0-9\s\-,\.\'’]*'


def looks_like_name(cn, en):
    cn = cn.strip()
    en = en.strip()
    if is_header_text(cn):
        return False
    if len(cn) < 2:
        return False
    if en and len(en) <= 1:
        return False
    # 中文含阵营词
    if any(w in cn for w in ALIGNMENT_WORDS):
        return False
    # 英文是常见非名字词
    if en and en.lower() in EN_COMMON_WORDS:
        return False
    # 中文以虚词结尾
    if re.search(r'[到在是的了而为]$', cn):
        return False
    return True


def parse_deity_title(line, next_line=None):
    s = line.strip()
    if not s:
        return None, None

    # A. **中文名（English）** / 中文名（English）
    m = re.match(r'^\*\*\s*(' + CN_CHARS + r')\s*[（(](' + EN_CHARS + r')[）)]\s*\*\*$', s)
    if not m:
        m = re.match(r'^(' + CN_CHARS + r')\s*[（(](' + EN_CHARS + r')[）)]\s*$', s)
    if m:
        cn, en = m.group(1).strip(), m.group(2).strip()
        if looks_like_name(cn, en):
            return cn, en

    # B. **中文名 English** / 中文名 English
    m = re.match(r'^\*\*\s*(' + CN_CHARS + r')\s+(' + EN_CHARS + r')\s*\*\*$', s)
    if not m:
        m = re.match(r'^(' + CN_CHARS + r')\s+(' + EN_CHARS + r')\s*$', s)
    if m:
        cn, en = m.group(1).strip(), m.group(2).strip()
        # 英文以逗号结尾且下一行是纯英文：合并为完整英文名
        if en.endswith((',', '，')) and next_line:
            next_en = next_line.strip()
            if re.match(r'^[A-Za-z][A-Za-z0-9\s\-\'’]+$', next_en):
                en = en.rstrip(',，').strip() + ' ' + next_en
        if looks_like_name(cn, en):
            return cn, en

    # B2. 中文名/别名English（无空格）如 煞克斯/沙克斯Shax
    m = re.match(r'^(' + CN_CHARS + r')/(' + CN_CHARS + r')?([A-Za-z][A-Za-z0-9\-\']*)\s*$', s)
    if m:
        cn = m.group(1).strip()
        en = m.group(3).strip()
        if looks_like_name(cn, en):
            return cn, en

    # C. 中文名English 无空格，可接（...）后缀
    m = re.match(r'^(' + CN_CHARS + r')([A-Z][A-Z0-9\-]+)\s*[（(].*?[）)]\s*$', s)
    if m:
        cn, en = m.group(1).strip(), m.group(2).strip()
        if looks_like_name(cn, en):
            return cn, en
    m = re.match(r'^(' + CN_CHARS + r')([A-Z][A-Z0-9\-]+)$', s)
    if m:
        cn, en = m.group(1).strip(), m.group(2).strip()
        if looks_like_name(cn, en):
            return cn, en

    # C2. 纯英文魔神名（无中文），后跟括号注释
    m = re.match(r'^([A-Z][A-Z0-9\-]+)\s*[（(].*?[）)]\s*$', s)
    if m:
        en = m.group(1).strip()
        if looks_like_name(en, en):
            return en, en

    # D. 跨两行：第一行 中文名，第二行 English
    m = re.match(r'^\*\*\s*(' + CN_CHARS + r')\s*\*\*$', s)
    if not m:
        m = re.match(r'^(' + CN_CHARS + r')\s*$', s)
    if m and next_line:
        cn = m.group(1).strip()
        en_line = next_line.strip()
        if re.match(r'^' + EN_CHARS + r'$', en_line):
            if looks_like_name(cn, en_line):
                return cn, en_line
        m2 = re.match(r'^[^（(]*[（(](' + EN_CHARS + r')[）)]', en_line)
        if m2:
            if looks_like_name(cn, m2.group(1).strip()):
                return cn, m2.group(1).strip()

    # E. 仅中文名：文件开头或紧跟分隔线，且不是已知标题/阵营
    m = re.match(r'^\*\*\s*(' + CN_CHARS + r')\s*\*\*$', s)
    if not m:
        m = re.match(r'^(' + CN_CHARS + r')\s*$', s)
    if m:
        cn = m.group(1).strip()
        if looks_like_name(cn, ""):
            return cn, ""

    return None, None


def find_deity_starts(raw_lines):
    lines, is_list = normalize_boon_lines(raw_lines)
    n = len(lines)
    first_sep = next((i for i, line in enumerate(lines) if line.strip() == "---"), n)
    starts = []
    first_title_found = False

    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s == "---" or s.startswith("["):
            continue

        is_at_boundary = False
        if not first_title_found and i < first_sep:
            is_at_boundary = True
        else:
            j = i - 1
            while j >= 0 and lines[j].strip() == "":
                j -= 1
            if j >= 0 and lines[j].strip() == "---":
                is_at_boundary = True
            # 列表项允许跨行出现
            if is_list[i]:
                is_at_boundary = True

        if not is_at_boundary:
            continue

        next_line = lines[i + 1] if i + 1 < n else ""
        cn, en = parse_deity_title(line, next_line)
        if cn:
            starts.append((i, cn, en))
            first_title_found = True

    return lines, starts


def split_file(path):
    lines, starts = find_deity_starts(load_lines(path))
    if not starts:
        fn = os.path.basename(path)
        return [(fn.replace(".md", ""), "", lines)]

    # 对以类别命名的文件（如 古魔领主.md、恐亡魔摧残者.md），若首候选中文与文件名相同，
    # 则视为文件总标题而非单个魔神，跳过。
    fn_base = os.path.splitext(os.path.basename(path))[0]
    # 取文件名中的中文部分（去掉英文/符号）
    fn_cn = re.sub(r'[^一-鿿]', '', fn_base)
    filtered = []
    for k, (idx, cn, en) in enumerate(starts):
        # 仅当存在后续候选且当前候选中文完全匹配文件名中文时跳过
        if k == 0 and len(starts) > 1 and re.sub(r'[^一-鿿]', '', cn) == fn_cn:
            continue
        filtered.append((idx, cn, en))

    sections = []
    for k, (idx, cn, en) in enumerate(filtered):
        end = filtered[k + 1][0] if k + 1 < len(filtered) else len(lines)
        sections.append((cn, en, lines[idx:end]))
    return sections


if __name__ == "__main__":
    boon_dir = os.path.join(SRC_DIR, "神恩")
    total = 0
    for subdir in ["地狱", "末日荒原", "深渊", "其他"]:
        d = os.path.join(boon_dir, subdir)
        if not os.path.exists(d):
            continue
        print(f"\n=== {subdir} ===")
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md"):
                continue
            p = os.path.join(d, fn)
            secs = split_file(p)
            total += len(secs)
            print(f"  {fn}: {len(secs)} sections")
            for cn, en, _ in secs:
                en_part = f" ({en})" if en else ""
                print(f"    - {cn}{en_part}")
    print(f"\nTotal deity sections: {total}")
