#!/usr/bin/env python3
"""D3 职业成长表结构化导出器（方案：数据侧产物增强 20260917 §D3）

扫描职业库 chunks.jsonl 中 class_overview 的成长表 chunk（主通道严格口径：表头行
`等级 | 基本攻击加值 | 强韧` + 数据行；BAB 简写与单行压缩表另见 KN237 段），
解析为结构化 class_tables.json，供 Java 侧 J5 查表工具消费。

数据源 = 职业库 chunks（权威产物），不回读 CHM 源 md（与 D2 同口径）。
职业键归一复用 spell_list_export 的 CLASS_ALIASES/CANONICAL_CLASS（单一事实源）。

表形态（D3 现状实测）：
- 表头行固定前 5 列：等级|基本攻击加值|强韧豁免|反射豁免|意志豁免；其后为
  特殊能力（或「职业能力」「特殊」）/每日法术（或「每日法术量」，可缺省）及
  职业特有附加列（徒手伤害/AC加值/神圣武器…）。
- 表头行后紧跟纯数字行 = 法术位环号子表头（环数 = 数字列数，环号 = 数字值；
  战斗祭司形态含非数字标签格「伤害骰」按位归附加列）。
- 数据行：等级（纯数字或 1st/2nd 英文序数）、BAB（+6/+1 多攻形态保留原文）、
  豁免 +x、特殊能力（逗号/顿号分隔）、法术位 `-`→null、数字→int、`1+1`→字符串。

覆盖率如实处理：解析不出的职业进 coverage.missing（含 doc_id 依据），不硬凑。

KN237 补齐（spec docs/superpowers/specs/2026-11-12-kn237-class-table-parsing-design.md）：
- 表头放宽：`BAB` 与 `基本攻击加值` 等价（吸血鬼猎人简写表头）；表头内嵌环号的
  法术列（`每1级|日2级|法3级|术4级`，CHM 折行把「每日法术」拆进各环列）按环号取列。
- 单行压缩表（催眠师/异能者）：表头一格串接全部列名 + 每行以 `N级` 起行、数值无
  分隔符。由表头确定列序与环位数，行尾逆向取固定数量法术位，剩余部分为特殊能力。
- 定向补扫：class_overview 主通道优先；只对当前 coverage.missing 的职业，从同一
  doc 的其他组件补扫，且只取第一张通过完整校验的表（不放开全量扫描）。
- 夹具 `vectorizer/config/class_table_overrides.json`：仅对登记的对应职业生效
  （变形者源页转置压平不可逐级恢复），报告写独立 coverage.overrides，不复用
  coverage.resolved_via（后者是 Java 的别名→规范职业映射）。

自描述 header：version / generated_at / source_fingerprint（职业 chunks sha256）/
coverage（parsed/missing/resolved_via/overrides）。产物只由本脚本生成，禁止手改；
源 md 一律不改。
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

# 与 pf_data/phase1/vectorizer/output/职业/ 同目录，相对 pf_data/phase1 运行
OUT_DIR = 'vectorizer/output/职业'
CHUNKS_PATH = os.path.join(OUT_DIR, 'chunks.jsonl')
JSON_PATH = os.path.join(OUT_DIR, 'class_tables.json')
REPORT_PATH = os.path.join(OUT_DIR, 'class_table_export_report.json')

# 夹具配置（相对脚本所在目录，裸 checkout/CI 不依赖 source_chm）
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'vectorizer', 'config', 'class_table_overrides.json')

# 职业键归一常量复用 spell_list_export（单一事实源，D3 方案拍板）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spell_list_export import CLASS_ALIASES, CANONICAL_CLASS, CLASS_LISTS  # noqa: E402

# coverage 误导性条目的显式消解（2026-09-22 QA D2）：候选名对应的成长表
# 已以目录归属解析到别的键（核心职业/骑士 page_51 无成长表；page_73 表题「骑士」
# 归属目录「骑将」解析）。召唤师(掉链子) 由去括号基名规则自动消解。
RESOLVED_VIA_TABLE = {
    '骑士': '骑将',
}

def class_key_of(caption, doc_id):
    """职业键：doc_id 目录第二段（主职业目录内，权威归属）优先；进阶职业合并页/
    无目录前缀回退表标题 `表：XX`（去英文括注）；再过别名归一。"""
    key = None
    parts = (doc_id or '').split('/')
    if len(parts) >= 2 and parts[0] in MAIN_DIRS and not parts[1].endswith('.md'):
        key = parts[1].strip()
    if not key and caption:
        key = re.sub(r'\s+', '', caption)
    if not key:
        return None
    key = CLASS_ALIASES.get(key, key)
    return CANONICAL_CLASS.get(key, key)


RE_TEXT_TITLE = re.compile(r'^\s*([一-鿿·]{2,12}?)\s*[（(][A-Za-z]')


def class_key_from_text(text):
    """无表标题且无目录前缀（进阶职业散页如 ISI page_742/743）→ 文本首行
    「中文名（English）」标题回退（妩媚交际花（Enchantingcourtesan）/狮子剑(Lionblade)）。"""
    for ln in (text or '').split('\n')[:6]:
        m = RE_TEXT_TITLE.match(ln)
        if m:
            key = m.group(1).strip()
            return CLASS_ALIASES.get(key, key)
    return None

VERSION = '1.0'
MIN_PARSED_CLASSES = 15  # 实测约 20 个标准职业有标准表（方案 §D3.6 下界留余量）

# 主职业目录前缀（coverage 对照范围：CLASS_LISTS 规范键 + 这些目录下出现的主职业）
MAIN_DIRS = {
    '核心职业', '基础职业', '混合职业', '掉链子（Unchained）',
    '异能冒险（Occult Adventures）', '极限荒野（Ultimate Wilderness）',
    '极限诡道', '其他职业',
}

# 表头行：等级 | 基本攻击加值（主通道严格口径）| 强韧（豁免可缺省），其后列不定
RE_HEADER = re.compile(
    r'^\s*\|\s*等级\s*\|\s*基本攻击加值\s*\|\s*强韧(?:豁免)?\s*'
    r'\|\s*反射(?:豁免)?\s*\|\s*意志(?:豁免)?\s*\|(.*)$', re.M)
# 放宽表头（KN237-D1）：BAB 与「基本攻击加值」等价。只用于对 missing 职业的定向补扫，
# 不进入 class_overview 主通道——全量放宽会额外识别一批进阶职业表，破坏 64→68 验收口径。
RE_HEADER_RELAXED = re.compile(
    r'^\s*\|\s*等级\s*\|\s*(?:基本攻击加值|BAB)\s*\|\s*强韧(?:豁免)?\s*'
    r'\|\s*反射(?:豁免)?\s*\|\s*意志(?:豁免)?\s*\|(.*)$', re.M)
# 单行压缩表表头：一格串接「等级基本攻击加值强韧豁免反射豁免意志豁免特殊」+ 环号序列
RE_COMPRESSED_HEADER = re.compile(
    r'(?:^|\|)\s*等级\s*基本攻击加值\s*强韧(?:豁免)?\s*反射(?:豁免)?\s*意志(?:豁免)?'
    r'\s*特殊\s*((?:\d+级)+)')
# 单行压缩表数据行：以 `N级` 起行（物理折行由调用方先拼接）
RE_COMPRESSED_ROW = re.compile(r'^\s*(\d+)级')
# 表头内嵌环号的法术列（CHM 折行把「每日法术」拆进各环列：每1级/日2级/法3级/术4级）
RE_SPELL_RING_CELL = re.compile(r'^[每日法术]+(\d+)级$')
RE_SEPARATOR = re.compile(r'^\s*\|[\s:\-|]+\|\s*$')
# 多行文本中的表格分隔行（压缩表 region 截断用；单行版 RE_SEPARATOR 无 re.M，
# 对多行 chunk 的 `^...$` 只能匹配全文首尾，截断会静默失效）
RE_SEPARATOR_LINE = re.compile(r'^\s*\|[\s:\-|]+\|\s*$', re.M)
RE_CAPTION = re.compile(r'\|\s*表\d*\s*[：:]\s*([^|（(]+?)\s*(?:[（(][^|)]*[）)])?\s*\|')
RE_BAB = re.compile(r'^[+-]\d+(?:\s*/\s*[+-]\d+)*$')
RE_SAVE = re.compile(r'^[+-]\d+$')
RE_LEVEL_EN = re.compile(r'^(\d+)(?:st|nd|rd|th)$', re.I)
RE_LEVEL_CN = re.compile(r'^(\d+)\s*级$')
RE_TABLE_LINE = re.compile(r'^\s*\|')

SPECIAL_NAMES = ('特殊能力', '特殊', '职业能力')
SPELL_NAMES = ('每日法术', '每日法术量')
# 环号子表头中的非环级标签格（按位对齐附加列，如战斗祭司「伤害骰」→神圣武器列）
SUBHEADER_LABELS = {'伤害骰', '武器加值'}


def fold_bab(s):
    """BAB 原文归一：`+6 /+1`（空格折行）→ `+6/+1`；多攻形态展开为数组留 Java 侧或 bab_attacks。"""
    s = re.sub(r'\s*/\s*', '/', (s or '').strip())
    return s


def bab_attacks(bab):
    """`+6/+1` → [6, 1]（无多攻 → [n]）；非规范形态返回 None。"""
    m = re.fullmatch(r'([+-]\d+(?:/[+-]\d+)*)', bab or '')
    if not m:
        return None
    return [int(x) for x in m.group(1).split('/')]


def split_special(s):
    """特殊能力格 → 列表：折叠空白（含折行 \n）后按顿号/逗号/分号分隔（括号内分隔符不切分）。"""
    s = re.sub(r'\s+', ' ', (s or '').strip())
    if not s:
        return []
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch in '（(':
            depth += 1
        elif ch in '）)':
            depth = max(0, depth - 1)
        if depth == 0 and ch in '，,、；;':
            parts.append(''.join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append(''.join(cur))
    return [p.strip() for p in parts if p.strip()]


def spell_value(cell):
    """法术位格：`-`/空 → None；纯数字 → int；其余（`1+1`/`现有等级+1`）→ 原文字符串。"""
    s = (cell or '').strip()
    if s in ('-', '—', ''):
        return None
    if re.fullmatch(r'\d+', s):
        return int(s)
    return s


def parse_level(cell):
    """等级格 → int：纯数字、`N级`（简写表头数据行）或英文序数（进阶职业表常见）。"""
    s = (cell or '').strip()
    if re.fullmatch(r'\d+', s):
        return int(s)
    m = RE_LEVEL_EN.match(s) or RE_LEVEL_CN.match(s)
    if m:
        return int(m.group(1))
    return None


def split_row(ln):
    """物理表行 → 单元格列表（strip 首尾 '|'，中间空格格保留为空串）。"""
    return [c.strip() for c in ln.strip().strip('|').split('|')]


RE_PROSE_LIKE = re.compile(r'(。|^#|^\*\*)')


def looks_like_prose(s):
    """行首非 | 的物理行是否更像表外散文（而非 CHM 折行续段）。
    折行续段特征：短（≤40 字符）、无句读、非标题/加粗行。"""
    s = s.strip()
    return len(s) > 40 or bool(RE_PROSE_LIKE.search(s))


def collect_rows(lines, start_idx, total_cols, doc_id):
    """表头行之后的数据行收集 + 折行归一（2026-09-22 D1 修复）。

    CHM→md 的表行硬折行普遍：行首非 `|` 的续行并入上一逻辑行——
    上一物理行以 `|` 收尾且逻辑行已满列 → 单元边界折行，续段作为新格追加；
    否则为格内折行（如「藏刃,\n毁灭刺杀」「+3 |\n/+4 |」），首段并入末格。
    返回 (rows, next_idx, truncation)；truncation 非 None = 表疑被截断（位置写明），
    调用方须整表拒收进 coverage.missing，严禁当完整表接受（拍板口径）。
    """
    rows, cur, i = [], None, start_idx + 1
    while i < len(lines):
        ln = lines[i]
        if RE_TABLE_LINE.match(ln):
            if cur is not None:
                rows.append(cur)
            cur = split_row(ln)
            i += 1
            continue
        s = ln.strip()
        if not s:
            break
        if cur is None or looks_like_prose(s):
            break
        frag = split_row(ln)
        prev_pipe = lines[i - 1].rstrip().endswith('|')
        if prev_pipe and len(cur) >= total_cols:
            cur.extend(frag)            # 单元边界折行：续段是新格
        elif frag:
            head, rest = frag[0], frag[1:]
            cur[-1] = head if not cur[-1] else cur[-1] + '\n' + head  # 格内折行：并入末格
            cur.extend(rest)
        i += 1
    if cur is not None:
        rows.append(cur)

    truncation = None
    if rows and len(rows[-1]) < 5:
        lv = parse_level(rows[-1][0]) if rows[-1] else None
        truncation = (f'{doc_id}: 末行残缺（等级 {lv if lv is not None else "?"} 行仅 '
                      f'{len(rows[-1])} 格 <5），表被 chunk 截断')
    elif i < len(lines) and not RE_TABLE_LINE.match(lines[i]) and lines[i].strip() \
            and not looks_like_prose(lines[i]) and rows:
        # 表后紧跟短无句读非 | 行：疑折行被拒绝合并（解析不完整）
        truncation = (f'{doc_id}: 表在第 {i + 1} 行处中断，紧跟短行 {lines[i].strip()[:30]!r} '
                      f'疑为未归一折行（等级 {parse_level(rows[-1][0]) if rows[-1] else "?"} 后截断）')
    return rows, i, truncation


def parse_table(lines, start_idx, chunk_id, doc_id):
    """从表头行（lines[start_idx]）解析一张成长表。

    返回 (record, issues, next_idx)；record 结构见 build_record。解析失败返回 (None, issues, …)。
    列模型：前 5 列固定（等级/BAB/强韧/反射/意志），其后列按表头名分类——
    特殊能力列 / 每日法术列（可缺省）/ 附加列（徒手伤害等，进 extras）。
    """
    issues = []
    header_cells = [c.strip() for c in lines[start_idx].strip().strip('|').split('|')]
    tail = header_cells[5:]
    if not tail:  # NPC 职业（望族/平民/专家/武者）5 列裸表：无特殊能力/法术列
        special_col = None
    else:
        special_col = next((i for i, c in enumerate(tail)
                            if c in SPECIAL_NAMES or c.startswith('特殊')), None)
        if special_col is None:  # 兜底：无名称命中则第 6 列视为特殊能力
            special_col = 0
            issues.append(f'{doc_id}: 特殊能力列表头未识别，按位置取第 6 列: {tail!r}')
    spell_col = next((i for i, c in enumerate(tail) if c in SPELL_NAMES), None)
    # 表头内嵌环号的法术列（KN237-D1：BAB 简写表的「每日法术」被折行拆进各环列）
    header_rings = [(i, int(m.group(1))) for i, c in enumerate(tail)
                    if (m := RE_SPELL_RING_CELL.match(c))]
    ring_cols = {i for i, _ in header_rings}
    extra_cols = [i for i, c in enumerate(tail)
                  if i not in (special_col, spell_col) and i not in ring_cols]
    total_cols = 5 + len(tail)

    # 折行归一后的逻辑行
    raw_rows, i, truncation = collect_rows(lines, start_idx, total_cols, doc_id)

    # 环号子表头：首个「各格为数字或已知标签」的逻辑行（表头无内嵌环号时）
    rings = None       # 环号 int 列表（顺序 = 数据行法术列自前向后）
    sub_labels = {}    # 附加列下标 → 子表头标签（如 神圣武器→伤害骰）
    rows = []
    if header_rings:
        rings = [r for _, r in header_rings]
    for cells in raw_rows:
        if RE_SEPARATOR.match('|' + '|'.join(cells) + '|'):
            continue
        if rings is None and not rows:
            numeric = [c for c in cells if re.fullmatch(r'\d+', c)]
            labeled = [c for c in cells if c in SUBHEADER_LABELS]
            if cells and len(numeric) + len(labeled) == len(cells) and numeric:
                rings = [int(c) for c in cells if re.fullmatch(r'\d+', c)]
                # 非数字标签格按位对齐附加列（cells 与 tail 列一一对应时）
                if len(cells) == len(tail):
                    for ci, c in enumerate(cells):
                        if c in SUBHEADER_LABELS:
                            sub_labels[ci] = c
                continue
        rows.append(cells)

    if not rows:
        return None, [f'{doc_id}: 表头行后无数据行（chunk {chunk_id[:8]}）'], i

    levels = {}
    max_cols_seen = 0
    for cells in rows:
        max_cols_seen = max(max_cols_seen, len(cells))
        lv = parse_level(cells[0] if cells else '')
        if lv is None:
            issues.append(f'{doc_id}: 数据行等级格无法解析，跳过: {cells[:3]!r}')
            continue
        if lv in levels:
            issues.append(f'{doc_id}: 等级 {lv} 重复行，后行覆盖')
        if len(cells) < 5:
            issues.append(f'{doc_id}: 等级 {lv} 行列数不足 5，跳过: {cells!r}')
            continue
        bab = fold_bab(cells[1])
        saves = cells[2], cells[3], cells[4]
        for name, val in zip(('BAB', '强韧', '反射', '意志'), (bab, *saves)):
            pat = RE_BAB if name == 'BAB' else RE_SAVE
            if not pat.match(val):
                issues.append(f'{doc_id}: 等级 {lv} {name} 格形态异常: {val!r}')
        entry = {
            'bab': bab,
            'bab_attacks': bab_attacks(bab),
            'fort': saves[0],
            'ref': saves[1],
            'will': saves[2],
        }
        special = split_special(tail_cells(cells, special_col)) if special_col is not None else []
        if special:
            entry['special'] = special
        # 附加列（徒手伤害/AC加值/神圣武器…）
        extras = {}
        for ci in extra_cols:
            v = tail_cells(cells, ci)
            if v:
                extras[tail[ci]] = v
        if extras:
            entry['extras'] = extras
        # 每日法术：表头内嵌环号（每1级/日2级/…）按列直取；否则按环号子表头顺序取尾部列
        if header_rings:
            entry['spells'] = {str(ring): spell_value(tail_cells(cells, ci))
                               for ci, ring in header_rings}
        elif rings is not None and spell_col is not None:
            spell_cells = cells[5 + spell_col:]
            spells = {}
            for k, ring in enumerate(rings):
                v = spell_cells[k] if k < len(spell_cells) else ''
                spells[str(ring)] = spell_value(v)
            entry['spells'] = spells
        elif spell_col is not None:
            note = tail_cells(cells, spell_col)
            if note:
                entry['spells_note'] = note
        levels[lv] = entry

    if not levels:
        return None, issues + [f'{doc_id}: 全部数据行解析失败'], i
    seq = sorted(levels)
    if seq != list(range(1, len(seq) + 1)):
        return None, issues + [f'{doc_id}: 等级不连续 {seq}（表被截断或解析错位）'], i
    if truncation:
        # 拍板口径：疑被截断的表严禁当完整表接受 → 整表拒收，进 coverage.missing
        return None, issues + [truncation], i

    record = {
        'source_chunk_id': chunk_id,
        'source_doc_id': doc_id,
        'max_level': seq[-1],
        'has_spell_table': rings is not None,
        'spell_levels': len(rings) if rings else 0,
        'levels': {str(lv): levels[lv] for lv in seq},
    }
    if rings:
        record['spell_rings'] = rings
    return record, issues, i


def tail_cells(cells, tail_idx):
    """取 tail 区（第 6 列起）第 tail_idx 列；列错位（折行丢列）返回空串。"""
    pos = 5 + tail_idx
    return cells[pos].strip() if pos < len(cells) else ''


def iter_hit_chunks(chunks):
    """命中口径（供测试/诊断）：class_overview 且含严格成长表表头行。"""
    for ch in chunks:
        if ch.get('component_type') != 'class_overview':
            continue
        m = RE_HEADER.search(ch.get('text') or '')
        if m:
            yield ch, m


def take_tail_spells(text, count):
    """单行压缩表行尾逆向取固定数量法术位（KN237-D4）。

    返回 (tokens, rest)：tokens 与表头环号同序（None=空位），rest = 特殊能力原文。
    只按 count 取值，防止「多重诡计（2）」「催眠注视（-3）」等特殊能力文本里的
    数字被误当法术位；取不满 count 格返回 (None, 原文)。
    """
    s = (text or '').rstrip()
    tokens = []
    for _ in range(count):
        s = s.rstrip()
        if not s:
            return None, text
        if s[-1] in '—-－':
            tokens.append(None)
            s = s[:-1]
            continue
        m = re.search(r'(\d+\+\d+|\d)$', s)
        if not m:
            return None, text
        tokens.append(spell_value(m.group(1)))
        s = s[:m.start()]
    tokens.reverse()
    return tokens, s.strip()


def parse_compressed_table(text, chunk_id, doc_id):
    """解析单行压缩成长表（催眠师/异能者），返回 (record|None, issues)。

    CHM→md 把整张表压成一行 pipe 单元：表头一格串接全部列名 + 环号序列，数据行以
    `N级` 起行且 BAB/三豁免/特殊能力/法术位之间无分隔符；物理折行还会把行尾数字
    挤到下一行（`…55543\\n1 | 17级…`），故先把表区折行拼平再按 `|` 切分。
    列序与环位数由表头确定，行尾逆序取固定数量法术位，剩余部分为特殊能力。
    """
    m = RE_COMPRESSED_HEADER.search(text or '')
    if not m:
        return None, []
    rings = [int(x) for x in re.findall(r'(\d+)级', m.group(1))]
    region = (text or '')[m.start():]
    sep = RE_SEPARATOR_LINE.search(region)
    if sep:
        region = region[:sep.start()]
    cells = [re.sub(r'\s+', ' ', c).strip() for c in region.replace('\n', ' ').split('|')]
    issues, levels = [], {}
    for cell in cells:
        lm = RE_COMPRESSED_ROW.match(cell)
        if not lm:
            continue
        lv = int(lm.group(1))
        rest = cell[lm.end():].strip()
        bm = re.match(r'([+-]\d+(?:\s*/\s*[+-]\d+)*)', rest)
        if not bm:
            issues.append(f'{doc_id}: 等级 {lv} BAB 格无法解析: {rest[:30]!r}')
            continue
        bab = fold_bab(bm.group(1))
        rest = rest[bm.end():]
        saves = []
        for _ in range(3):
            sm = re.match(r'\s*([+-]\d+)', rest)
            if not sm:
                break
            saves.append(sm.group(1))
            rest = rest[sm.end():]
        if len(saves) != 3 or not RE_BAB.match(bab) \
                or not all(RE_SAVE.match(s) for s in saves):
            issues.append(f'{doc_id}: 等级 {lv} BAB/豁免形态异常: {bab!r} {saves!r}')
            continue
        slots, special_text = take_tail_spells(rest, len(rings))
        if slots is None:
            issues.append(f'{doc_id}: 等级 {lv} 行尾法术位不足 {len(rings)} 位: {rest[-40:]!r}')
            continue
        entry = {
            'bab': bab,
            'bab_attacks': bab_attacks(bab),
            'fort': saves[0],
            'ref': saves[1],
            'will': saves[2],
            'spells': {str(r): v for r, v in zip(rings, slots)},
        }
        special = split_special(special_text)
        if special:
            entry['special'] = special
        if lv in levels:
            issues.append(f'{doc_id}: 等级 {lv} 重复行，后行覆盖')
        levels[lv] = entry
    if not levels:
        return None, issues + [f'{doc_id}: 单行压缩表无可用数据行（chunk {chunk_id[:8]}）']
    seq = sorted(levels)
    if seq != list(range(1, len(seq) + 1)):
        return None, issues + [f'{doc_id}: 单行压缩表等级不连续 {seq}（表被截断或解析错位）']
    record = {
        'source_chunk_id': chunk_id,
        'source_doc_id': doc_id,
        'max_level': seq[-1],
        'has_spell_table': True,
        'spell_levels': len(rings),
        'levels': {str(lv): levels[lv] for lv in seq},
        'spell_rings': rings,
    }
    return record, issues


def validate_record(rec):
    """成长表 record 完整性校验（解析通道与夹具共用）。通过返回 None，否则返回原因。"""
    levels = rec.get('levels') or {}
    if not levels:
        return 'levels 为空'
    try:
        seq = sorted(int(lv) for lv in levels)
    except (TypeError, ValueError):
        return 'levels 键非等级数字'
    max_level = int(rec.get('max_level') or 0)
    if seq != list(range(1, max_level + 1)):
        return f'等级不连续或与 max_level 不符 {seq} / {max_level}'
    for lv in seq:
        e = levels.get(str(lv))
        if not isinstance(e, dict):
            return f'等级 {lv} 条目缺失或非对象'
        if not RE_BAB.match(e.get('bab') or ''):
            return f'等级 {lv} BAB 形态异常: {e.get("bab")!r}'
        for sk in ('fort', 'ref', 'will'):
            if not RE_SAVE.match(e.get(sk) or ''):
                return f'等级 {lv} {sk} 形态异常: {e.get(sk)!r}'
        if not rec.get('has_spell_table') and 'spells' in e:
            return f'等级 {lv} 非施法职业不应有 spells'
    return None


def load_overrides(path=None):
    """加载夹具配置 → {规范职业名: 夹具条目}；文件缺失返回 {}（裸 checkout/CI 可跑）。"""
    path = path or CONFIG_PATH
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    out = {}
    for item in data.get('overrides') or []:
        raw = (item.get('class') or '').strip()
        if not raw:
            continue
        key = CLASS_ALIASES.get(raw, raw)
        out[CANONICAL_CLASS.get(key, key)] = item
    return out


def apply_overrides(classes, overrides, report):
    """应用夹具（夹具对其登记的职业优先级最高），返回 (溯源记录, 失败原因)。

    失败（等级不连续/BAB 或豁免形态非法）不改 classes，交回调用方进 coverage.missing。
    """
    provenance, failures = {}, {}
    for key, item in overrides.items():
        rec = {
            'source_chunk_id': item.get('source_chunk_id'),
            'source_doc_id': item.get('source_doc_id'),
            'max_level': item.get('max_level'),
            'has_spell_table': bool(item.get('has_spell_table')),
            'spell_levels': int(item.get('spell_levels') or 0),
            'levels': item.get('levels') or {},
        }
        reason = validate_record(rec)
        if reason:
            failures[key] = reason
            report['issues'].append(f'夹具 {key}: {reason}')
            continue
        rec['class'] = key
        if rec['has_spell_table']:
            first = rec['levels'][str(min(int(lv) for lv in rec['levels']))]
            rec['spell_rings'] = sorted(int(k) for k in (first.get('spells') or {}))
        replaced = key in classes
        if replaced:
            # 夹具优先：原解析结果降级为 variant，保留溯源不丢数据
            old = classes[key]
            rec.setdefault('variants', []).extend(old.get('variants') or [])
            rec['variants'].insert(0, {k: v for k, v in old.items() if k != 'variants'})
        classes[key] = rec
        report.setdefault('tables', {}).setdefault(key, {'sources': []})['sources'].append(
            {'doc_id': rec['source_doc_id'], 'chunk_id': rec['source_chunk_id'],
             'role': 'override'})
        provenance[key] = {
            'source_chunk_id': rec['source_chunk_id'],
            'source_doc_id': rec['source_doc_id'],
            'source_html': item.get('source_html'),
            'extracted_at': item.get('extracted_at'),
            'replaced_parsed': replaced,
        }
    return provenance, failures


def scan_supplement(chunks, doc_id, report):
    """定向补扫：同一 doc 的组件里取第一张通过完整校验的成长表。

    只对 coverage.missing 的职业调用，且表头放宽为「基本攻击加值 | BAB」等价——
    不放开全量扫描（KN237-D2）。`class_overview` 主通道已先跑过严格口径，这里
    再扫一次同 doc 不会扩大范围（键已解析的职业不会进入补扫）。
    """
    for ch in chunks:
        if (ch.get('doc_id') or '').strip() != doc_id:
            continue
        text = (ch.get('text') or '').replace('\r', '\n')
        if not RE_HEADER_RELAXED.search(text):
            continue
        chunk_id = ch.get('chunk_id') or ''
        lines = text.split('\n')
        idx = 0
        while idx < len(lines):
            if not RE_HEADER_RELAXED.match(lines[idx]):
                idx += 1
                continue
            record, issues, next_idx = parse_table(lines, idx, chunk_id, doc_id)
            report['issues'].extend(issues)
            if record is not None:
                return record
            idx = next_idx
    return None


def _insert_class(classes, report, key, record, doc_id, chunk_id, role):
    """登记解析结果：首见为 primary，同键再次出现保留为 variants（多来源）。"""
    if key in classes:
        classes[key].setdefault('variants', []).append(record)
        report.setdefault('tables', {}).setdefault(key, {'sources': []})['sources'].append(
            {'doc_id': doc_id, 'chunk_id': chunk_id, 'role': 'variant'})
        return False
    record['class'] = key
    classes[key] = record
    report['tables'][key] = {'sources': [{'doc_id': doc_id, 'chunk_id': chunk_id, 'role': role}]}
    return True


def _coverage(classes, parse_failures, doc_first):
    """计算 coverage：parsed / missing / resolved_via（overrides 由调用方并入）。"""
    candidates = {CANONICAL_CLASS.get(k, k) for k in CLASS_LISTS}
    candidates.update(CLASS_ALIASES.get(k, k) for k in doc_first)
    missing, resolved_via = [], {}
    for c in sorted(candidates):
        canon = CLASS_ALIASES.get(c, c)
        canon = CANONICAL_CLASS.get(canon, canon)
        if canon in classes:
            continue
        # D2 口径：别名/去括号基名/目录归属已解析到别的键 → 记 resolved_via 不算 missing
        base = re.sub(r'[（(].*?[）)]', '', c).strip()
        base = CLASS_ALIASES.get(base, base)
        base = CANONICAL_CLASS.get(base, base)
        if base != c and base in classes:
            resolved_via[c] = base
            continue
        # D2：表题归属目录后于别的键解析（page_73 表题「骑士」→ 目录归属「骑将」）
        rv = RESOLVED_VIA_TABLE.get(c)
        if rv and rv in classes:
            resolved_via[c] = rv
            continue
        if c in parse_failures:
            f = parse_failures[c]
            missing.append({'class': c, 'reason': f'成长表解析失败（拒收）: {f["reason"]}',
                            'doc_id': f['doc_id']})
            continue
        missing.append({'class': c, 'reason': 'class_overview 无成长表（未命中 等级|基本攻击加值|BAB|强韧 表头行）',
                        'doc_id': doc_first.get(c)})
    # 命中表但职业键不在候选集内的拒收（如进阶职业散页）也如实登记
    for key, f in sorted(parse_failures.items()):
        if key not in candidates:
            missing.append({'class': key, 'reason': f'成长表解析失败（拒收）: {f["reason"]}',
                            'doc_id': f['doc_id']})
    return missing, resolved_via


def build(chunks, overrides=None):
    """主解析：返回 (classes, coverage, report)。

    通道顺序：class_overview（标准表头 + 单行压缩表）→ 仅对 missing 职业的同 doc
    其他组件定向补扫（BAB 表头放宽）→ 夹具覆盖。overrides 传 None 时从 config
    加载（缺文件视为无夹具）。
    """
    if overrides is None:
        overrides = load_overrides()
    classes = {}
    report = {'tables': {}, 'issues': [], 'supplements': []}
    hit_docs = set()
    parse_failures = {}  # key|doc_id → reason（截断/不连续等拒收原因，进 coverage.missing）
    doc_first = {}

    # ---- 通道 1：class_overview（主通道）----
    for ch in chunks:
        if ch.get('component_type') != 'class_overview':
            continue
        doc_id = (ch.get('doc_id') or '').strip()
        chunk_id = ch.get('chunk_id') or ''
        text = (ch.get('text') or '').replace('\r', '\n')
        parts = doc_id.split('/')
        if len(parts) >= 2 and parts[0] in MAIN_DIRS and not parts[1].endswith('.md'):
            doc_first.setdefault(parts[1].strip(), doc_id)

        # 单行压缩表（催眠师/异能者）：整块 chunk 一张表
        if RE_COMPRESSED_HEADER.search(text):
            record, issues = parse_compressed_table(text, chunk_id, doc_id)
            report['issues'].extend(issues)
            key = class_key_of(None, doc_id) or class_key_from_text(text)
            if record is not None and key is not None:
                _insert_class(classes, report, key, record, doc_id, chunk_id, 'primary')
                hit_docs.add(doc_id)
            elif record is None and key is not None:
                reason = '；'.join(i for i in issues if doc_id in i) or '单行压缩表解析失败'
                parse_failures.setdefault(key, {'class': key, 'reason': reason,
                                                'doc_id': doc_id})
            elif record is not None:
                report['issues'].append(f'{doc_id}: 单行压缩表职业键无法归属')

        lines = text.split('\n')
        # 逐张表解析（一个 chunk 内可能有表标题 + 表头行；进阶职业合并页一张表一个 chunk）
        idx = 0
        while idx < len(lines):
            if not RE_HEADER.match(lines[idx]):
                idx += 1
                continue
            # 表标题：向上找最近的 | 表：XX | 行（同窗内）
            caption = None
            for back in range(idx - 1, max(-1, idx - 6), -1):
                cm = RE_CAPTION.search(lines[back])
                if cm:
                    caption = cm.group(1)
                    break
            record, issues, next_idx = parse_table(lines, idx, chunk_id, doc_id)
            report['issues'].extend(issues)
            idx = next_idx
            key = class_key_of(caption, doc_id) or class_key_from_text(text)
            if record is None:
                # 命中成长表但解析失败（截断/等级不连续）：如实记 missing，不静默丢弃
                reason = '；'.join(i for i in issues if doc_id in i) or '表解析失败'
                if key is not None:
                    parse_failures.setdefault(key, {'class': key, 'reason': reason,
                                                    'doc_id': doc_id})
                else:
                    report['issues'].append(f'{doc_id}: 表解析失败且职业键无法归属')
                continue
            if key is None:
                report['issues'].append(f'{doc_id}: 职业键无法归属（无表标题且 doc_id 无目录前缀）')
                continue
            _insert_class(classes, report, key, record, doc_id, chunk_id, 'primary')
            hit_docs.add(doc_id)

    # ---- 通道 2：仅对当前 missing 职业的定向补扫 ----
    missing, resolved_via = _coverage(classes, parse_failures, doc_first)
    supplemented = set()
    for item in list(missing):
        key = item['class']
        doc = doc_first.get(key)
        if not doc or key in classes:
            continue
        record = scan_supplement(chunks, doc, report)
        if record is None:
            continue
        _insert_class(classes, report, key, record, doc, record['source_chunk_id'], 'supplement')
        hit_docs.add(doc)
        supplemented.add(key)
        report['supplements'].append({'class': key, 'doc_id': doc,
                                      'chunk_id': record['source_chunk_id']})
        parse_failures.pop(key, None)

    # ---- 通道 3：夹具（优先级最高，仅对登记职业生效）----
    override_provenance, override_failures = apply_overrides(classes, overrides, report)
    for key, reason in override_failures.items():
        parse_failures.setdefault(key, {'class': key, 'reason': f'夹具拒收: {reason}',
                                        'doc_id': (overrides[key].get('source_doc_id'))})

    # ---- coverage（补扫/夹具生效后重算）----
    missing, resolved_via = _coverage(classes, parse_failures, doc_first)
    parsed = sorted(classes)
    # stats.table_chunks_hit = 真正产出成长表 record 的 doc 数（主通道 + 定向补扫；
    # 夹具来源页不是可解析成长表，不计入）。注意它不是 class_overview 文档总数。
    coverage = {
        'parsed': parsed,
        'missing': missing,
        'resolved_via': resolved_via,
        'overrides': override_provenance,
        'stats': {'parsed': len(parsed), 'missing': len(missing),
                  'resolved_via': len(resolved_via),
                  'overrides': len(override_provenance),
                  'supplemented': len(supplemented),
                  'table_chunks_hit': len(hit_docs)},
    }
    return classes, coverage, report


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(CHUNKS_PATH, encoding='utf-8') as f:
        chunks = [json.loads(l) for l in f if l.strip()]
    fingerprint = hashlib.sha256(
        open(CHUNKS_PATH, 'rb').read()).hexdigest()

    overrides = load_overrides()
    classes, coverage, report = build(chunks, overrides=overrides)

    payload = {
        'version': VERSION,
        'category': 'profession',
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'generated_from': CHUNKS_PATH,
        'source_fingerprint': fingerprint,
        'classes': classes,
        'coverage': coverage,
    }
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    report['summary'] = coverage['stats']
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    # ---- 自校验断言（方案 §D3.6）----
    assert len(classes) >= MIN_PARSED_CLASSES, \
        f'解析职业数 {len(classes)} < 下界 {MIN_PARSED_CLASSES}'
    for key, rec in classes.items():
        seq = sorted(int(lv) for lv in rec['levels'])
        assert seq == list(range(1, rec['max_level'] + 1)), f'{key}: levels 不连续'
        for lv, e in rec['levels'].items():
            assert RE_BAB.match(e['bab']), f'{key} L{lv}: BAB 形态 {e["bab"]!r}'
            for sk in ('fort', 'ref', 'will'):
                assert RE_SAVE.match(e[sk]), f'{key} L{lv}: {sk} 形态 {e[sk]!r}'
            if not rec['has_spell_table']:
                assert 'spells' not in e, f'{key} L{lv}: 非施法职业不应有 spells'
    join_keys = set(CLASS_LISTS) & set(classes)
    print(f'\n===== 汇总：解析职业 {len(classes)}（含 variants 键冲突 '
          f'{sum(1 for r in classes.values() if "variants" in r)}）/ 未覆盖 {len(coverage["missing"])} / '
          f'与法术列表职业键 join {len(join_keys)}/{len(set(CLASS_LISTS))} =====')
    print('missing:', ', '.join(m['class'] for m in coverage['missing']))
    if report['issues']:
        print(f'issues（{len(report["issues"])} 条，抽样）:')
        for it in report['issues'][:15]:
            print('  -', it)
    print('自校验通过。产物 →', JSON_PATH)


if __name__ == '__main__':
    main()
