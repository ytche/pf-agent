import os, re, json
from collections import defaultdict, Counter

BASE = '/Users/chezi/code/java/pf_agent/pf_data/phase1/pf_rules_md_organized/职业'
CHUNKS_PATH = '/Users/chezi/code/java/pf_agent/pf_data/phase1/vectorizer/output/法术/chunks.jsonl'

KNOWN_CLASSES = {
    '炼金术师','反圣武士','吟游诗人','血怒者','血脉狂怒者','战斗祭司','牧师','调查员',
    '德鲁伊','歌者','猎人','审判者','魔战士','法师','武僧','先知','圣骑士','游侠','盗贼',
    '术士','召唤师','女巫','萨满','战士','唤魂师','催眠师','异能者','秘学士','通灵者',
    '导魂者','吸血鬼猎人','大法师','斗士','圣者'
}

CLASS_ALIASES = {
    '炼金术士': '炼金术师',
    '巡林客': '游侠',
    '诗人': '吟游诗人',
    '战争祭司': '战斗祭司',
    '战斗祭祀': '战斗祭司',
    '圣骑士': '圣武士',
    '唤魂者': '唤魂师',
    '召唤师（Unchained）': '召唤师（Unchained）',
    '血怒者': '血脉狂怒者',
}

CLASS_INHERITS = {
    '猎人': ['德鲁伊', '游侠'],
}

SOURCE_BOOKS = {
    'CRB','APG','UM','UC','ACG','OA','UI','ARG','ISM','ISWG','DTT','BM','HotW','HotS','BoS','MTT','DA','MaTT','AA','ACO','GHH','AE','HHH','ISG','PSFG','LOD','MU','OO','PA','WoI','BoDV','PotR','PoP','CotR','ISMC','DEP','HR','DR','UW','HA','VC','AG','ArcA','MHH','LoD','LotFW','BotD','BotB','AquA','EMH','ISI','SpyHB','HotHC','HotD','PFS','MA','DD','ISTem'
}

NON_SPELL_LIST_PAGES = {
    '核心职业/牧师/page_42.md',
    '混合职业/猎人/page_104.md',
    '基础职业/先知/page_273.md',
    '混合职业/调查员/page_31.md',
    '混合职业/调查员/page_106.md',
    '基础职业/炼金术师/page_21.md',
    '基础职业/炼金术师/page_71.md',
    '混合职业/歌者/page_104.md',
    '混合职业/歌者/page_115.md',
    '核心职业/法师/page_68.md',
    '异能冒险（Occult Adventures）/唤魂师/page_271.md',
    '异能冒险（Occult Adventures）/唤魂师/page_269.md',
    '异能冒险（Occult Adventures）/唤魂师/page_270.md',
    '异能冒险（Occult Adventures）/唤魂师/page_272.md',
}

EXCLUDE_PATH_KEYWORDS = ['变体', '未整合', '之道', '诅咒', '秘示域', '血统', '领域', '灵器套装', '奥术学派']
LEVEL_WORDS = {'一级','二级','三级','四级','五级','六级','七级','八级','九级','1级','2级','3级','4级','5级','6级','7级','8级','9级','0级','1环','2环','3环','4环','5环','6环','7环','8环','9环','0环'}

STOP_PATTERNS = [
    re.compile(r'^##\s+'),
    re.compile(r'^<!--\s*.*source:.*变体'),
    re.compile(r'^\*\*出自《'),
    re.compile(r'^\*\*先祖先驱'),
    re.compile(r'^\*\*盾卫者'),
    re.compile(r'^\*\*野性斗士'),
]

def load_chunks():
    with open(CHUNKS_PATH) as f:
        return [json.loads(l) for l in f]

def get_classes(c):
    return [e.get('class') for e in c.get('metadata',{}).get('spell_level',[]) if isinstance(e,dict) and e.get('class')]

def normalize(s):
    s = re.sub(r'[\s|]+', '', s.strip())
    num_map = {'一':'I','二':'II','三':'III','四':'IV','五':'V','六':'VI','七':'VII','八':'VIII','九':'IX'}
    m = re.match(r'(.)级怪物召唤术', s)
    if m:
        return f'召唤怪物 {num_map[m.group(1)]}'
    m = re.match(r'召唤怪物(.)', s)
    if m and m.group(1) in num_map:
        return f'召唤怪物 {num_map[m.group(1)]}'
    m = re.match(r'(.)级自然盟友召唤术', s)
    if m:
        return f'召唤自然盟友 {num_map[m.group(1)]}'
    m = re.match(r'自然盟友召唤术(.)', s)
    if m and m.group(1) in num_map:
        return f'召唤自然盟友 {num_map[m.group(1)]}'
    m = re.match(r'召唤自然盟友(.)', s)
    if m and m.group(1) in num_map:
        return f'召唤自然盟友 {num_map[m.group(1)]}'
    s = re.sub(r'([一-鿿])([IVX]+)$', r'\1 \2', s)
    fixes = {
        '灰飞湮灭': '灰飞烟灭',
        '人类变巨术': '变巨术', '人类缩小术': '缩小术',
        '群体人类变巨术': '群体变巨术', '群体人类缩小术': '群体缩小术',
        '治疗中度伤': '治疗中伤', '治疗致命伤': '治疗重伤',
        '造成中度伤': '造成中伤', '造成致命伤': '造成重伤',
        '治疗中伤': '治疗中度伤', '治疗重伤': '治疗致命伤',
        '造成中伤': '造成中度伤', '造成重伤': '造成致命伤',
        '治疗轻微伤': '治疗轻伤', '造成轻微伤': '造成轻伤',
        '群体治疗中伤': '群体治疗中度伤', '群体造成中伤': '群体造成中度伤',
        '群体治疗重伤': '群体治疗致命伤', '群体造成重伤': '群体造成致命伤',
        '群体治疗轻微伤': '群体治疗轻伤', '群体造成轻微伤': '群体造成轻伤',
        '疲劳之触': '疲乏之触', '瞬间召唤': '即刻召唤',
        '蛇文法印': '蛇纹法印', '隐型仆役': '隐形仆役',
        '疯狂徽记': '摄魂徽记', '沉睡徽记': '睡眠徽记', '虚弱徽记': '衰弱徽记',
        '高级隐形术': '高等隐形术',
        '反各阵营法阵': '防护阵营',
        '幻像墙': '虚幻之墙', '念动法球': '念动斩',
        '构装体残废术': '构装体残废',
        '防护混乱/邪恶/善良/守序': '防护阵营',
        '防范探知': '回避侦测',
        '时间停止': '时间静止', '空间锁': '次元锁', '移土术': '地动术',
        '爆裂神符': '爆裂符文', '谜幻手稿': '迷幻手稿', '钢铁墙壁': '铁墙术',
        '法师的忠犬': '法师忠犬', '法师的私人密室': '法师密室',
        '共用抵抗能量': '共用抵抗能量伤害',
        '类人形态 IV': '类人形态IV', '虫类形态 I': '虫类形态I', '虫类形态 II': '虫类形态II',
        '亡灵形态 I': '亡灵形态I', '亡灵形态 II': '亡灵形态II', '亡灵形态 III': '亡灵形态III', '亡灵形态 IV': '亡灵形态IV',
        '反混乱/邪恶/善良/秩序法阵': '防护阵营',
        '反混乱/邪恶法阵': '防护阵营',
        '侦测混乱/邪恶/善良/守序': '侦测阵营',
        '侦测混乱/邪恶/善良/秩序': '侦测阵营',
        '防护混乱/邪恶/善良/守序': '防护阵营',
        '防护混乱/邪恶/善良/秩序': '防护阵营',
        '召唤次级盟友': '召唤次级怪物',
        '动物交谈术': '动物交谈',
        '植物交谈术': '植物交谈',
        '侦测陷阱和坑': '侦测陷阱',
        '召唤雷电风暴': '召唤雷暴',
        '操控风向': '操纵风相',
        '祝福圣水M': '祝福圣水',
        '谜幻手稿M': '迷幻手稿',
        '防范探知M': '回避侦测',
        '强迫护卫M': '强迫护卫',
    }
    return fixes.get(s, s)

def clean_source_prefix(part):
    part = part.strip()
    part = re.sub(r'^>来源：[^\s]+\s*', '', part)
    m = re.match(r'^([A-Za-z]{2,5})([-—–]+)(.*)$', part)
    if m and m.group(1) in SOURCE_BOOKS:
        part = m.group(3).strip()
    return part.strip()

def clean_source_suffix(part):
    part = part.strip()
    part = re.sub(r'\*+$', '', part).strip()
    part = re.sub(r'[（(]\s*[A-Za-z]{2,5}\s*[)）]\s*$', '', part).strip()
    m = re.match(r'^(.+?)([A-Za-z]{2,5})$', part)
    if m and m.group(2) in SOURCE_BOOKS:
        part = m.group(1).strip()
    part = re.sub(r'\s+PFS未审$', '', part)
    part = re.sub(r'\s+PFS不可用$', '', part)
    return part.strip()

def is_valid_spell_name(name):
    name = name.strip()
    if len(name) < 2:
        return False
    if name.startswith('*'):
        return False
    if re.match(r'^\d+', name):
        return False
    if re.match(r'^[A-Za-z\s,./\-\(\)]+$', name):
        return False
    if name in ('来源', '出自', '不可用', '此能力取代', '此能力类似'):
        return False
    if '此能力' in name or '取代' in name:
        return False
    if name in SOURCE_BOOKS:
        return False
    if name in LEVEL_WORDS:
        return False
    return True

def extract_spell_name(part):
    part = part.strip()
    if not part:
        return None
    part = re.sub(r'^【[^】]+】', '', part)
    part = clean_source_prefix(part)
    part = clean_source_suffix(part)
    if not part:
        return None
    part = re.sub(r'^[一二三四五六七八九十\d]+级[：:]\s*', '', part)

    m = re.match(r'^([^（）()]+?)（\s*([A-Za-z][^）]*?)\s*）$', part)
    if m:
        name = re.sub(r'[\s|]+', '', m.group(1).strip())
        if is_valid_spell_name(name):
            return normalize(name)

    m = re.match(r'^([^（）()]+?)\(\s*([A-Za-z][^)]*?)\s*\)$', part)
    if m:
        name = re.sub(r'[\s|]+', '', m.group(1).strip())
        if is_valid_spell_name(name):
            return normalize(name)

    m = re.match(r'^([一-龥][一-龥\s]*)([A-Za-z][A-Za-z\s,./\-]*)$', part)
    if m:
        name = re.sub(r'[\s|]+', '', m.group(1).strip())
        if is_valid_spell_name(name):
            return normalize(name)

    if re.match(r'^[一-龥][一-龥\s/]+$', part) and '：' not in part:
        name = re.sub(r'[\s|]+', '', part.strip())
        if is_valid_spell_name(name):
            return normalize(name)

    return None

def split_cell(cell):
    parts = re.split(r'[,，、;；]', cell)
    result = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        for sub in p.split('\n'):
            sub = sub.strip()
            if sub:
                result.append(sub)
    return result

def extract_spells_from_text(text):
    def compress(m):
        inner = re.sub(r'\s+', ' ', m.group(2)).strip()
        return m.group(1) + inner + m.group(3)
    text = re.sub(r'(（)([^）]*?)(）)', compress, text, flags=re.DOTALL)
    text = re.sub(r'(\()([^)]*?)(\))', compress, text, flags=re.DOTALL)

    spells = set()
    for line in text.split('\n'):
        line = line.strip()
        if any(p.match(line) for p in STOP_PATTERNS):
            break
        if '|' in line:
            cells = [c.strip() for c in line.split('|')]
        else:
            cells = [line]
        for cell in cells:
            for part in split_cell(cell):
                name = extract_spell_name(part)
                if name:
                    spells.add(name)
    return spells

def has_explicit_spell_list_title(text):
    for line in text.split('\n')[:60]:
        raw = line.strip()
        if not raw:
            continue
        clean = re.sub(r'\*+', '', raw).strip()
        if re.search(r'法术列表|公式列表', clean):
            return True
        m = re.search(r'(\S+?)(?:法术|公式)[（(]', clean)
        if m:
            cls = m.group(1).strip()
            if cls in KNOWN_CLASSES or cls in CLASS_ALIASES:
                return True
    return False

def identify_spell_list_page(path, text):
    rel = path.replace(BASE, '').lstrip('/')
    if any(rel == p for p in NON_SPELL_LIST_PAGES):
        return None
    if not has_explicit_spell_list_title(text):
        return None
    parts = rel.split('/')
    inferred_class = parts[-2] if len(parts) >= 2 else None
    if inferred_class and inferred_class not in KNOWN_CLASSES:
        inferred_class = CLASS_ALIASES.get(inferred_class)
    lines = text.split('\n')[:60]
    for line in lines:
        raw = line.strip()
        if not raw:
            continue
        clean = re.sub(r'\*+', '', raw).strip()
        pairs = re.findall(r'([^（）\s]+?)（\s*([A-Za-z][^）]*?)\s*）', clean)
        classes = [cn.strip() for cn, en in pairs if cn.strip() in KNOWN_CLASSES]
        if classes:
            return classes
        m = re.search(r'(\S+?)(?:的)?(?:法术|公式)列表', clean)
        if m:
            cls = m.group(1).strip()
            if cls in KNOWN_CLASSES:
                return [cls]
            if cls.endswith('的'):
                cls = cls[:-1]
                if cls in KNOWN_CLASSES:
                    return [cls]
        m = re.search(r'(\S+?)(?:法术|公式)[（(]', clean)
        if m:
            cls = m.group(1).strip()
            if cls in KNOWN_CLASSES:
                return [cls]
            if cls in CLASS_ALIASES:
                return [CLASS_ALIASES[cls]]
    if inferred_class:
        return [inferred_class]
    return None

def should_exclude(path):
    rel = path.replace(BASE, '').lstrip('/')
    if rel in NON_SPELL_LIST_PAGES:
        return True
    for p in EXCLUDE_PATH_KEYWORDS:
        if p in path:
            return True
    return False

def matches_class(chunk, class_name):
    classes = get_classes(chunk)
    if class_name in classes:
        return True
    for inherited in CLASS_INHERITS.get(class_name, []):
        if inherited in classes:
            return True
    return False

def main():
    chunks = load_chunks()
    all_titles = {c.get('title','').strip(): c for c in chunks if c.get('title')}

    results = []
    scanned = 0
    for root, dirs, fnames in os.walk(BASE):
        for fn in fnames:
            if not fn.endswith('.md'):
                continue
            path = os.path.join(root, fn)
            if should_exclude(path):
                continue
            try:
                with open(path, encoding='utf-8', errors='ignore') as f:
                    text = f.read()
            except Exception:
                continue
            classes = identify_spell_list_page(path, text)
            if not classes:
                continue
            scanned += 1
            spells = extract_spells_from_text(text)
            if not spells:
                continue
            for cls in classes:
                chunk_cls = CLASS_ALIASES.get(cls, cls)
                matched = set()
                exists_other = set()
                missing = set()
                other_classes_counter = Counter()
                for s in spells:
                    c = all_titles.get(s)
                    if c and matches_class(c, chunk_cls):
                        matched.add(s)
                    elif c:
                        exists_other.add(s)
                        for cc in get_classes(c):
                            other_classes_counter[cc] += 1
                    else:
                        missing.add(s)
                results.append({
                    'path': path,
                    'class': cls,
                    'chunk_class': chunk_cls,
                    'classes': classes,
                    'spells': len(spells),
                    'matched': len(matched),
                    'exists_other': len(exists_other),
                    'missing': len(missing),
                    'match_rate': len(matched)/len(spells)*100 if spells else 0,
                    'matched_spells': sorted(matched),
                    'exists_other_spells': sorted(exists_other),
                    'missing_spells': sorted(missing),
                    'other_classes_counter': dict(other_classes_counter),
                })

    by_class = defaultdict(list)
    for r in results:
        by_class[r['class']].append(r)

    best_results = []
    for cls, rs in by_class.items():
        def path_match_score(r):
            parts = r['path'].replace(BASE, '').split('/')
            return 1 if parts[-2] == r['class'] else 0
        best = max(rs, key=lambda x: (x['spells'], path_match_score(x)))
        best_results.append(best)

    # 保存结构化结果
    with open('/tmp/spell_list_scan_results.json', 'w', encoding='utf-8') as f:
        json.dump({
            'scanned_pages': scanned,
            'classes_covered': len(by_class),
            'total_list_spells': sum(r['spells'] for r in best_results),
            'total_matched': sum(r['matched'] for r in best_results),
            'classes': best_results,
        }, f, ensure_ascii=False, indent=2)

    # 生成 Markdown 报告
    lines = []
    lines.append('# 职业法术列表与法术 chunk 匹配率扫描报告')
    lines.append('')
    lines.append('> 扫描对象：`pf_data/phase1/pf_rules_md_organized/职业/` 下所有法术/公式列表页面')
    lines.append('> 匹配对象：`vectorizer/output/法术/chunks.jsonl`')
    lines.append('> 统计口径：按标题精确匹配；职业匹配指 `spell_level.class` 包含列表职业或其继承职业')
    lines.append('')
    lines.append('## 一、总体摘要')
    lines.append('')
    total_spells = sum(r['spells'] for r in best_results)
    total_matched = sum(r['matched'] for r in best_results)
    total_exists_other = sum(r['exists_other'] for r in best_results)
    total_missing = sum(r['missing'] for r in best_results)
    lines.append(f'- 识别到 **{scanned}** 个法术列表页面，覆盖 **{len(by_class)}** 个职业')
    lines.append(f'- 列表法术总计 **{total_spells}** 条')
    lines.append(f'- 匹配成功 **{total_matched}** 条（**{total_matched/total_spells*100:.1f}%**）')
    lines.append(f'- 法术存在但 `spell_level.class` 未标该职业：**{total_exists_other}** 条（**{total_exists_other/total_spells*100:.1f}%**）')
    lines.append(f'- 法术在 chunks 中未找到：**{total_missing}** 条（**{total_missing/total_spells*100:.1f}%**）')
    lines.append('')

    # 总表
    lines.append('## 二、按职业匹配率总表')
    lines.append('')
    lines.append('| 职业 | chunk职业名 | 文件路径 | 列表法术数 | 匹配数 | 匹配率 | 存在但class未标 | 缺失 |')
    lines.append('|------|-------------|----------|------------|--------|--------|-----------------|------|')
    for r in sorted(best_results, key=lambda x: x['match_rate'], reverse=True):
        rel_path = r['path'].replace(BASE, '')
        lines.append(f"| {r['class']} | {r['chunk_class']} | `{rel_path}` | {r['spells']} | {r['matched']} | {r['match_rate']:.1f}% | {r['exists_other']} | {r['missing']} |")
    lines.append('')

    # 分组
    high = [r for r in best_results if r['match_rate'] >= 70]
    mid = [r for r in best_results if 50 <= r['match_rate'] < 70]
    low = [r for r in best_results if r['match_rate'] < 50]

    lines.append('## 三、分组概览')
    lines.append('')
    lines.append(f'- 高匹配（≥70%）：{len(high)} 个职业')
    lines.append(f'- 中匹配（50%-70%）：{len(mid)} 个职业')
    lines.append(f'- 低匹配（<50%）：{len(low)} 个职业')
    lines.append('')

    lines.append('### 3.1 高匹配职业（≥70%）')
    lines.append('')
    if high:
        lines.append('| 职业 | 匹配率 | 主要问题 |')
        lines.append('|------|--------|----------|')
        for r in sorted(high, key=lambda x: x['match_rate'], reverse=True):
            issue = 'class 标签部分缺失' if r['exists_other'] > r['missing'] else '少量法术缺失/翻译不一致'
            lines.append(f"| {r['class']} | {r['match_rate']:.1f}% | {issue} |")
    else:
        lines.append('无')
    lines.append('')

    lines.append('### 3.2 中匹配职业（50%-70%）')
    lines.append('')
    if mid:
        lines.append('| 职业 | 匹配率 | 主要问题 |')
        lines.append('|------|--------|----------|')
        for r in sorted(mid, key=lambda x: x['match_rate'], reverse=True):
            lines.append(f"| {r['class']} | {r['match_rate']:.1f}% | class 标签缺失较多 |")
    else:
        lines.append('无')
    lines.append('')

    lines.append('### 3.3 低匹配职业（<50%，需重点处理）')
    lines.append('')
    if low:
        lines.append('| 职业 | 匹配率 | 列表法术数 | 已匹配 | 存在但class未标 | 缺失 | 根因 |')
        lines.append('|------|--------|------------|--------|-----------------|------|------|')
        for r in sorted(low, key=lambda x: x['match_rate'], reverse=True):
            root = 'spell_level.class 元数据覆盖率低' if r['exists_other'] > r['missing'] else '法术缺失/翻译不一致'
            lines.append(f"| {r['class']} | {r['match_rate']:.1f}% | {r['spells']} | {r['matched']} | {r['exists_other']} | {r['missing']} | {root} |")
    else:
        lines.append('无')
    lines.append('')

    # 问题根因分析
    lines.append('## 四、问题根因分析')
    lines.append('')

    # Class 标签缺失统计
    lines.append('### 4.1 `spell_level.class` 标签缺失分布')
    lines.append('')
    lines.append('以下职业存在大量"法术已在 chunks 中，但 `spell_level.class` 未标注该职业"的情况。')
    lines.append('')
    all_other_classes = Counter()
    for r in best_results:
        all_other_classes.update(r['other_classes_counter'])
    if all_other_classes:
        lines.append('| 法术实际归属职业（按 chunks） | 被其他列表引用次数 | 说明 |')
        lines.append('|----------------------------|-------------------|------|')
        for cls, cnt in all_other_classes.most_common(20):
            lines.append(f'| {cls} | {cnt} | 这些 chunk 只标了 {cls}，但其他职业的列表也包含它们 |')
    lines.append('')

    # 缺失分析
    lines.append('### 4.2 法术在 chunks 中缺失/翻译不一致样例')
    lines.append('')
    for r in sorted(best_results, key=lambda x: x['missing'], reverse=True)[:5]:
        if r['missing'] == 0:
            continue
        lines.append(f"- **{r['class']}**（{r['missing']} 个缺失）: {', '.join(r['missing_spells'][:15])}")
    lines.append('')

    # 详细问题样例
    lines.append('## 五、各职业问题样例（匹配率 < 95%）')
    lines.append('')
    for r in sorted(best_results, key=lambda x: x['match_rate']):
        if r['match_rate'] >= 95:
            continue
        lines.append(f"### {r['class']} — {r['match_rate']:.1f}%（{r['matched']}/{r['spells']}）")
        lines.append(f"- 文件：`{r['path'].replace(BASE, '')}`")
        lines.append(f"- 存在但 class={r['chunk_class']} 未标：{r['exists_other']} 个")
        lines.append(f"- 缺失：{r['missing']} 个")
        if r['exists_other_spells']:
            lines.append(f"- 未标样例：{', '.join(r['exists_other_spells'][:10])}")
        if r['missing_spells']:
            lines.append(f"- 缺失样例：{', '.join(r['missing_spells'][:10])}")
        lines.append('')

    # 建议
    lines.append('## 六、建议行动项')
    lines.append('')
    lines.append('1. **补全 occult 类职业的 `spell_level.class` 元数据**：通灵者/唤魂师/秘学士/异能者/催眠师/萨满/血脉狂怒者匹配率均低于 20%，大量法术已在 chunks 中但 class 未标。建议在解析阶段为这些职业补充来源书法术列表映射，或在后处理中追加 class 标签。')
    lines.append('2. **处理核心/基础职业中的 class 未标问题**：术士、法师、女巫、德鲁伊、牧师、审判者、魔战士等匹配率 66%-82%，主要问题是跨职业共享法术未全部标注。例如术士/法师共享列表中大量法术只标了其中一个职业。')
    lines.append('3. **补录缺失法术或对齐翻译**：部分列表法术（如`侦测阵营`、`防护阵营`、`造成中伤`、`荆棘之墙`等）在 chunks 中完全不存在，需检查源数据是否已整理到 `pf_rules_md_organized/法术/` 或是否存在翻译变体。')
    lines.append('4. **建立 KN 记录**：建议将 occult 职业 spell_level.class 覆盖率低登记为新的已知问题（如 KN018），并纳入下一轮解析器迭代。')
    lines.append('5. **修复重复文件路径**：炼金术师公式列表同时出现在 `基础职业/炼金术师/page_72.md` 和 `混合职业/调查员/page_72.md`，后者还附加了调查员变体。建议整理源数据时去重，或在报告中明确标注真实归属。')
    lines.append('')

    report = '\n'.join(lines)
    with open('/tmp/spell_list_report.md', 'w', encoding='utf-8') as f:
        f.write(report)

    print(f'已保存结构化结果：/tmp/spell_list_scan_results.json')
    print(f'已生成 Markdown 报告：/tmp/spell_list_report.md')
    print(f'\n总体：{total_spells} 个列表法术，{total_matched} 个匹配（{total_matched/total_spells*100:.1f}%）')

if __name__ == '__main__':
    main()
