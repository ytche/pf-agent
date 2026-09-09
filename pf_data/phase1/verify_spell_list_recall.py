#!/usr/bin/env python3
"""法术列表→chunk 召回验收：每个职业法术列表随机抽 10 个法术，验证 chunk 存在性与质量"""
import json, re, os, random
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
LISTS = {
    '牧师': '核心职业/牧师/page_43.md',
    '德鲁伊': '核心职业/德鲁伊/page_47.md',
    '吟游诗人': '核心职业/吟游诗人/page_39.md',
    '圣骑士': '核心职业/圣骑士/page_56.md',
    '游侠': '核心职业/游侠/page_60.md',
    '术士': '核心职业/术士/page_65.md',
    '法师': '核心职业/法师/page_65.md',
    '先知': '基础职业/先知/page_43.md',
    '女巫': '基础职业/女巫/page_93.md',
    '魔战士': '基础职业/魔战士/page_84.md',
    '审判者': '基础职业/审判者/page_80.md',
    '召唤师': '基础职业/召唤师/page_412.md',
    '反圣武士': '基础职业/反圣武士/page_407.md',
    '炼金术师': '基础职业/炼金术师/page_72.md',
    '召唤师(掉链子)': '掉链子（Unchained）/召唤师/page_248.md',
    '奥能师': '混合职业/奥能师/page_65.md',
    '战斗祭司': '混合职业/战斗祭司/page_43.md',
    '歌者': '混合职业/歌者/page_39.md',
    '猎人': '混合职业/猎人/page_105.md',
    '萨满': '混合职业/萨满/page_114.md',
    '血脉狂怒者': '混合职业/血脉狂怒者/page_100.md',
    '唤魂师': '异能冒险（Occult Adventures）/唤魂师/page_272.md',
    '唤魂师(p1037)': '异能冒险（Occult Adventures）/唤魂师/page_1037.md',
    '秘学士': '异能冒险（Occult Adventures）/秘学士/page_1232.md',
    '通灵者': '异能冒险（Occult Adventures）/通灵者/page_264.md',
    '异能者': '异能冒险（Occult Adventures）/异能者/page_309.md',
    '催眠师': '异能冒险（Occult Adventures）/催眠师/page_304.md',
}

# ---- 1. 解析法术列表 ----
ENTRY = re.compile(r'(?:【[^】]*】)?\s*([一-鿿][一-鿿A-Za-z0-9/·\s’\'\-]{0,30}?)\s*（\s*([A-Za-z][^（）]*?)\s*）', re.S)
def parse_list(path):
    text = open(path, encoding='utf-8').read()
    out = {}
    for m in ENTRY.finditer(text):
        cn = re.sub(r'\s+', '', m.group(1))
        en = re.sub(r'\s+', ' ', m.group(2)).strip()
        if len(cn) < 2 or len(en) < 3: continue
        if cn.startswith(('法术', '列表')): continue
        out[en.lower()] = (cn, en)
    return out

# ---- 2. 建立 chunk 索引 ----
chunks = [json.loads(l) for l in open(f'{ROOT}/vectorizer/output/法术/chunks.jsonl', encoding='utf-8')]
def norm_en(s): return re.sub(r'\s+', ' ', s).strip().lower()
by_alias = defaultdict(list)
by_title = defaultdict(list)
for c in chunks:
    for a in (c.get('aliases') or []):
        by_alias[norm_en(a)].append(c)
        by_alias[norm_en(a).replace(',', '')].append(c)
    t = (c.get('title') or '').strip()
    if t: by_title[t].append(c)

FIELDS = ('school', 'spell_level', 'casting_time', 'components', 'range', 'duration', 'saving_throw', 'spell_resistance')
KN019_TITLE = re.compile(r'^(I{1,3}V?|IV|V|VI{0,3}|IX|X)$|^[，(。]')
def quality(c):
    m = c.get('metadata') or {}
    fs = m.get('field_status') or {}
    parsed = sum(1 for f in FIELDS if fs.get(f) == 'parsed')
    dirty = any(isinstance(m.get(f), str) and '**' in m[f] for f in FIELDS)
    tail = bool(re.search(r'\n\s*([A-Z][A-Za-z\'\-]+(?: [A-Za-z\'\-]+){0,4})\s*$', c.get('text') or ''))
    bad_title = bool(KN019_TITLE.match((c.get('title') or '').strip())) or len((c.get('title') or '')) > 25
    return parsed, dirty, tail, bad_title, len(c.get('text') or '')

def best(cands):
    # 优先字段解析多、文本长的 chunk
    return max(cands, key=lambda c: (quality(c)[0], quality(c)[4]))

random.seed(20260730)
report = []
for cls, rel in LISTS.items():
    path = os.path.join(ROOT, 'pf_rules_md_organized/职业', rel)
    if not os.path.exists(path):
        report.append((cls, 0, 0, 0, [], ['列表页不存在']))
        continue
    spells = parse_list(path)
    keys = sorted(spells)
    sample = random.sample(keys, min(10, len(keys)))
    hits, misses, qrows = [], [], []
    for k in sample:
        cn, en = spells[k]
        cands = by_alias.get(k) or by_alias.get(k.replace(',', '')) or by_title.get(cn) or []
        if not cands:
            misses.append(f'{cn}（{en}）')
            continue
        c = best(cands)
        p, dirty, tail, badt, tl = quality(c)
        qrows.append((cn, en, c['chunk_id'], p, dirty, tail, badt, tl))
        hits.append(k)
    report.append((cls, len(keys), len(hits), len(misses), qrows, misses))

# ---- 3. 输出 ----
print(f"{'职业':<10} {'列表法术数':>6} {'命中':>4} {'丢失':>4}  命中chunk质量(字段数/8, 标记)")
tot_s = tot_h = 0
all_issues = []
for cls, total, h, ms, qrows, misses in report:
    tot_s += min(10, total) if total else 0
    tot_h += h
    print(f'\n■ {cls}  列表={total} 抽样={len(qrows)+len(misses)} 命中={h} 丢失={ms}')
    for cn, en, cid, p, dirty, tail, badt, tl in qrows:
        flags = []
        if badt: flags.append('KN019伪标题')
        if dirty: flags.append('KN020脏字段')
        if tail: flags.append('KN021尾英文')
        if p < 4: flags.append(f'字段少({p}/8)')
        if tl < 200: flags.append('文本极短')
        flag = '⚠' + ','.join(flags) if flags else '✓'
        print(f'    {cn:<14} {cid:<34} {p}/8字段 {tl:>5}字符 {flag}')
        if flags: all_issues.append((cls, cn, cid, flags))
    for msn in misses:
        print(f'    ✗ 未找到: {msn}')
        all_issues.append((cls, msn, '-', ['未找到']))
print(f'\n===== 总召回: {tot_h}/{tot_s} = {tot_h/tot_s*100:.1f}% =====')
print(f'问题条目: {len(all_issues)}')
