#!/usr/bin/env python3
"""D3 职业成长表结构化导出器（方案：数据侧产物增强 20260917 §D3）

扫描职业库 chunks.jsonl 中 class_overview 的成长表 chunk（严格口径：表头行
`等级 | 基本攻击加值 | 强韧` + 数据行），解析为结构化 class_tables.json，
供 Java 侧 J5 查表工具消费。

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

自描述 header：version / generated_at / source_fingerprint（职业 chunks sha256）/
coverage（parsed/missing）。产物只由本脚本生成，禁止手改；源 md 一律不改。
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

# 严格表头行：等级|基本攻击加值|强韧（豁免可缺省），其后列不定
RE_HEADER = re.compile(
    r'^\s*\|\s*等级\s*\|\s*基本攻击加值\s*\|\s*强韧(?:豁免)?\s*'
    r'\|\s*反射(?:豁免)?\s*\|\s*意志(?:豁免)?\s*\|(.*)$', re.M)
RE_SEPARATOR = re.compile(r'^\s*\|[\s:\-|]+\|\s*$')
RE_CAPTION = re.compile(r'\|\s*表\d*\s*[：:]\s*([^|（(]+?)\s*(?:[（(][^|)]*[）)])?\s*\|')
RE_BAB = re.compile(r'^[+-]\d+(?:\s*/\s*[+-]\d+)*$')
RE_SAVE = re.compile(r'^[+-]\d+$')
RE_LEVEL_EN = re.compile(r'^(\d+)(?:st|nd|rd|th)$', re.I)
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
    """等级格 → int：纯数字或英文序数（1st/2nd/3rd/4th…，进阶职业表常见）。"""
    s = (cell or '').strip()
    if re.fullmatch(r'\d+', s):
        return int(s)
    m = RE_LEVEL_EN.match(s)
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
    extra_cols = [i for i, c in enumerate(tail)
                  if i not in (special_col, spell_col)]
    total_cols = 5 + len(tail)

    # 折行归一后的逻辑行
    raw_rows, i, truncation = collect_rows(lines, start_idx, total_cols, doc_id)

    # 环号子表头：首个「各格为数字或已知标签」的逻辑行
    rings = None       # 环号 int 列表（顺序 = 数据行法术列自前向后）
    sub_labels = {}    # 附加列下标 → 子表头标签（如 神圣武器→伤害骰）
    rows = []
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
        # 每日法术
        if rings is not None and spell_col is not None:
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
    """严格口径命中：class_overview 且含成长表表头行。"""
    for ch in chunks:
        if ch.get('component_type') != 'class_overview':
            continue
        m = RE_HEADER.search(ch.get('text') or '')
        if m:
            yield ch, m


def build(chunks):
    """主解析：返回 (classes, coverage, report)。"""
    classes = {}
    report = {'tables': {}, 'issues': []}
    hit_docs = set()
    parse_failures = {}  # key|doc_id → reason（截断/不连续等拒收原因，进 coverage.missing）

    for ch, _m in iter_hit_chunks(chunks):
        doc_id = (ch.get('doc_id') or '').strip()
        chunk_id = ch.get('chunk_id') or ''
        hit_docs.add(doc_id)
        text = (ch.get('text') or '').replace('\r', '\n')
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
            if key in classes:
                # 键冲突（同职业多来源：核心 vs 掉链子/APG vs Unchained）——保留多个并记溯源
                entry = classes[key]
                entry.setdefault('variants', []).append(record)
                report['tables'].setdefault(key, {'sources': []})['sources'].append(
                    {'doc_id': doc_id, 'chunk_id': chunk_id, 'role': 'variant'})
            else:
                record['class'] = key
                classes[key] = record
                report['tables'][key] = {'sources': [{'doc_id': doc_id, 'chunk_id': chunk_id,
                                                      'role': 'primary'}]}

    # ---- coverage ----
    candidates = {CANONICAL_CLASS.get(k, k) for k in CLASS_LISTS}
    doc_first = {}
    for ch in chunks:
        if ch.get('component_type') != 'class_overview':
            continue
        d = (ch.get('doc_id') or '').strip()
        parts = d.split('/')
        if len(parts) >= 2 and parts[0] in MAIN_DIRS and not parts[1].endswith('.md'):
            sub = parts[1].strip()
            candidates.add(CLASS_ALIASES.get(sub, sub))
            doc_first.setdefault(sub, d)
    parsed = sorted(classes)
    missing = []
    resolved_via = {}
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
        missing.append({'class': c, 'reason': 'class_overview 无成长表（未命中 等级|基本攻击加值|强韧 表头行）',
                        'doc_id': doc_first.get(c)})
    # 命中表但职业键不在候选集内的拒收（如进阶职业散页）也如实登记
    for key, f in sorted(parse_failures.items()):
        if key not in candidates:
            missing.append({'class': key, 'reason': f'成长表解析失败（拒收）: {f["reason"]}',
                            'doc_id': f['doc_id']})
    coverage = {'parsed': parsed, 'missing': missing, 'resolved_via': resolved_via,
                'stats': {'parsed': len(parsed), 'missing': len(missing),
                          'resolved_via': len(resolved_via),
                          'table_chunks_hit': len(hit_docs)}}
    return classes, coverage, report


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(CHUNKS_PATH, encoding='utf-8') as f:
        chunks = [json.loads(l) for l in f if l.strip()]
    fingerprint = hashlib.sha256(
        open(CHUNKS_PATH, 'rb').read()).hexdigest()

    classes, coverage, report = build(chunks)

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
