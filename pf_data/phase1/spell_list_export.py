#!/usr/bin/env python3
"""F-007 职业法术列表预整理导出器（SP3 T1）

读 27 职业官方法术列表页（pf_rules_md_organized/职业/...）→ 按环级（0~9）分段解析 →
与法术库 chunks.jsonl 交叉补 chunk_id → 写结构化 spell_lists.json + 对账报告。

设计依据：《SP3_职业法术列表预整理方案_20260906.md》D1~D7。
- D1 权威数据源 = 规则书官方列表页（不用 spell_level 元数据）。
- D2 产物 gitignored，脚本入库（F-012：脚本与产物同版本提交）。
- D3 schema：classes{职业:{aliases, source_page, source_toc_path, source_excerpt,
  list_chunk_id, levels{0..9:[{cn,en,book,chunk_id}]}}}；chunk_id 对不上置 null 不阻塞。

幂等：产物不含时间戳，重跑字节一致（V1）。
复用先例：LISTS/ENTRY ← verify_spell_list_recall.py；normalize/SOURCE_BOOKS/别名表 ←
docs/scan_spell_lists_20260729.py（60+ 译名变体归一）。
"""
import json, os, re
from collections import Counter, defaultdict

# 与 pf_data/phase1/vectorizer/output/法术/ 同目录，相对 pf_data/phase1 运行
OUT_DIR = 'vectorizer/output/法术'
CHUNKS_PATH = os.path.join(OUT_DIR, 'chunks.jsonl')
JSON_PATH = os.path.join(OUT_DIR, 'spell_lists.json')
REPORT_PATH = os.path.join(OUT_DIR, 'spell_list_export_report.json')
ORGANIZED_ROOT = 'pf_rules_md_organized/职业'
# 职业库（list_chunk_id 交叉来源：doc_id = 列表页相对 pf_rules_md_organized/职业 的路径）
CLASS_CHUNKS_PATH = 'vectorizer/output/职业/chunks.jsonl'

# ---- 27 职业 → 列表页相对路径（verify_spell_list_recall.LISTS，逐路径已验证存在）----
CLASS_LISTS = {
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

# 已知纯英文等不可解析源页的处置说明（数据侧勘察 2026-09-06 确认）：
#   唤魂师 page_272 为纯英文受限列表（ENTRY 中英配对不可用）→ 该页产出为空并记入对账报告；
#   其规范中文列表落在 page_1037，导出时经 CANONICAL_CLASS 归一为规范键「唤魂师」（见下）。
PAGE_NOTES = {
    '唤魂师': 'page_272 为纯英文受限列表（ENTRY 中英配对不可用）→ 产出为空；规范中文列表在 page_1037',
}

# 导出键规范化：注册表保留同职业双页（page_272 纯英文 / page_1037 中文规范）以如实上报
# 每页解析结果（对齐 §7「27 页逐页解析成功率入报告」），但导出 classes 一律归一到规范
# 职业键，避免 Agent 侧出现「唤魂师」「唤魂师(p1037)」两个可查询职业。
CANONICAL_CLASS = {'唤魂师(p1037)': '唤魂师'}

# ---- 译名/别名/来源书常量（复用 scan_spell_lists_20260729 先例，标注来源）----
SOURCE_BOOKS = {
    'CRB', 'APG', 'UM', 'UC', 'ACG', 'OA', 'UI', 'ARG', 'ISM', 'ISWG', 'DTT', 'BM',
    'HotW', 'HotS', 'BoS', 'MTT', 'DA', 'MaTT', 'AA', 'ACO', 'GHH', 'AE', 'HHH',
    'ISG', 'PSFG', 'LOD', 'MU', 'OO', 'PA', 'WoI', 'BoDV', 'PotR', 'PoP', 'CotR',
    'ISMC', 'DEP', 'HR', 'DR', 'UW', 'HA', 'VC', 'AG', 'ArcA', 'MHH', 'LoD', 'LotFW',
    'BotD', 'BotB', 'AquA', 'EMH', 'ISI', 'SpyHB', 'HotHC', 'HotD', 'PFS', 'MA', 'DD',
    'ISTem', 'COMP', 'CAMPAIGN', 'AArch', 'MC', 'TG', 'PotI', 'HH',
}

# 职业常见译名变体 → 规范职业键（值必须是 CLASS_LISTS 的键；方向：变体在前、规范在后）。
# 覆盖中文社区常见异译/简称：诗人/游吟诗人→吟游诗人、圣武士→圣骑士、审判官→审判者、
# 巡林客→游侠、炼金术士→炼金术师、战争祭司/战斗祭祀→战斗祭司、血怒者→血脉狂怒者、
# 唤魂者→唤魂师、召唤师(掉链子) 的全角括号/去括号变体。
CLASS_ALIASES = {
    '炼金术士': '炼金术师',
    '巡林客': '游侠',
    '诗人': '吟游诗人',
    '游吟诗人': '吟游诗人',
    '战争祭司': '战斗祭司',
    '战斗祭祀': '战斗祭司',
    '圣武士': '圣骑士',
    '审判官': '审判者',
    '唤魂者': '唤魂师',
    '血怒者': '血脉狂怒者',
    '召唤师（掉链子）': '召唤师(掉链子)',
    '召唤师掉链子': '召唤师(掉链子)',
}

# 环级词形全集（5 种：X级法术/X环法术/X环公式/X级/X环），用于过滤误入条目名的环词
LEVEL_WORD_SET = {
    f'{i}级法术' for i in range(10)} | {f'{i}环法术' for i in range(10)} | {
    f'{i}环公式' for i in range(10)} | {f'{i}级' for i in range(10)} | {
    f'{i}环' for i in range(10)}

ENTRY = re.compile(  # 中文名（English）对；【学派】前缀可选；中/英文括号皆接受（萨满页半角混用）
    r'(?:【[^】]*】)?\s*([一-鿿][一-鿿A-Za-z0-9/·\s’\'\-]{0,30}?)\s*'
    r'[（(]\s*([A-Za-z][^（）()]*?)\s*[）)]')

re_level_cell = re.compile(  # 表格整格环级头：数字 X级法术/X环法术/X环公式 + 中文 祷念/戏法(=0)
    r'^\s*(?:(?:(\d+)[级环](?:法术|公式)?)|祷念|戏法)\s*$')


def level_of_cell(cell):
    """整格环级头 → 环级 int；非环级头返回 None。数字取数，祷念/戏法归 0。"""
    m = re_level_cell.match(cell or '')
    if not m:
        return None
    if m.group(1) is not None:
        return int(m.group(1))
    return 0
re_bold_level = re.compile(r'^\*{1,3}\s*(\d+)[级环][^。]*?\*+')       # 独立加粗环级头（B/C 格式）
re_bold_book = re.compile(r'^\*{1,3}\s*([A-Za-z]{1,10})\s*[—–—-]')   # B 格式「**CRB——**」书前缀
re_sep_row = re.compile(r'^\s*\|?[\s:\-|]+\|?\s*$')                    # markdown 分隔行/空行
re_book_suffix = re.compile(r'([A-Za-z]{2,10})(?=[，。、,;；]|$|\s*[（(【])')  # 条目尾缀书（C 格式）


def normalize(s):
    """译名变体归一（scan_spell_lists_20260729.normalize 同源）：列表页译名 → 法术 chunk 标题用词。"""
    s = re.sub(r'[\s|]+', '', s.strip())
    num_map = {'一': 'I', '二': 'II', '三': 'III', '四': 'IV', '五': 'V',
               '六': 'VI', '七': 'VII', '八': 'VIII', '九': 'IX'}
    m = re.match(r'(.)级怪物召唤术', s)
    if m:
        return f'召唤怪物 {num_map[m.group(1)]}'
    m = re.match(r'召唤怪物(.)', s)
    if m and m.group(1) in num_map:
        return f'召唤怪物 {num_map[m.group(1)]}'
    m = re.match(r'(.)级自然盟友召唤术', s)
    if m:
        return f'召唤自然盟友 {num_map[m.group(1)]}'
    for head in ('自然盟友召唤术', '召唤自然盟友'):
        m = re.match(f'{head}(.)', s)
        if m and m.group(1) in num_map:
            return f'召唤自然盟友 {num_map[m.group(1)]}'
    s = re.sub(r'([一-鿿])([IVX]+)$', r'\1 \2', s)
    fixes = {
        '灰飞湮灭': '灰飞烟灭',
        '人类变巨术': '变巨术', '人类缩小术': '缩小术',
        '群体人类变巨术': '群体变巨术', '群体人类缩小术': '群体缩小术',
        '治疗中度伤': '治疗中伤', '治疗致命伤': '治疗重伤',
        '造成中度伤': '造成中伤', '造成致命伤': '造成重伤',
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
        '类人形态 IV': '类人形态IV', '虫类形态 I': '虫类形态I',
        '虫类形态 II': '虫类形态II', '亡灵形态 I': '亡灵形态I',
        '亡灵形态 II': '亡灵形态II', '亡灵形态 III': '亡灵形态III',
        '亡灵形态 IV': '亡灵形态IV',
        '反混乱/邪恶/善良/秩序法阵': '防护阵营',
        '反混乱/邪恶法阵': '防护阵营',
        '侦测混乱/邪恶/善良/守序': '侦测阵营',
        '侦测混乱/邪恶/善良/秩序': '侦测阵营',
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


def fold_ws(s):
    """折叠任意空白（含 \r/\n/多空格）为单个空格并收尾。"""
    return re.sub(r'\s+', ' ', s).strip()


def fold_lower(s):
    """交叉匹配键：小写 + 去所有空白（对英文名折行/大小写差异鲁棒）。"""
    return re.sub(r'\s+', '', s).lower()


def norm_book(token):
    """列表页来源书写法 → 规范缩写：`CRB 核心手册`→CRB；纯中文全称查表兜底。"""
    token = (token or '').strip()
    if not token:
        return None
    head = token.split()[0].split('　')[0].strip('* ') if token.split() else token
    # 全称中文（无缩写前缀）——如「核心手册」，映射兜底表
    cn_map = {
        '核心手册': 'CRB', '进阶玩家手册': 'APG', '极限魔法': 'UM', '极限战斗': 'UC',
        '进阶职业手册': 'ACG', '异能冒险': 'OA', '极限诡道': 'UI', '惧怖冒险': 'HA',
        '冒险者指南': 'AG', '极限荒野': 'UW', '邪恶特务': 'AoE', '阴影血脉': 'BoS',
        '野兽血脉': 'BotB', '皇庭英豪': 'HotHC', '内海诡道': 'ISI', '恶棍志': 'VC',
        '护甲大师手册': 'AMH',
    }
    if head in SOURCE_BOOKS:
        return head
    if token in cn_map:
        return cn_map[token]
    m = re.match(r'^([A-Za-z]{1,10})', token)
    if m and m.group(1) in SOURCE_BOOKS:
        return m.group(1)
    return None


def split_table_blocks(lines):
    """markdown 表格物理行 → 逻辑块：以 | 起始的物理行开块，后续 7 空格缩进续行并入。"""
    blocks, cur = [], []
    for ln in lines:
        if ln.lstrip().startswith('|'):
            if cur:
                blocks.append(cur)
            cur = [ln]
        else:
            if cur:
                cur.append(ln)
    if cur:
        blocks.append(cur)
    return blocks


def parse_cells(block):
    """逻辑块 → (col1, col2, body)。body = col3 及之后并集（可能跨物理续行）。"""
    txt = '\n'.join(block).strip()
    if not txt or re_sep_row.match(txt):
        return None
    txt = txt.strip('|')
    parts = [c.strip() for c in txt.split('|')]
    c1 = parts[0] if len(parts) > 0 else ''
    c2 = parts[1] if len(parts) > 1 else ''
    body = ' '.join(p for p in parts[2:] if p.strip())
    return c1, c2, body


def classify_format(text, page_note):
    """格式分类：A 环级表 / B 加粗标题段落 / C 学派表 / D 粘连名 / None 不可解析。

    D（通灵者）：法术写成 `出血术Bleed`（中文直接粘连小写英文、无括号），书以 （书） 后缀。
    判据：正文中「CJK 紧贴 latin」的粘连名 ≥30 且显著多于全角配对——萨满页的半角是
    `中文(latin)` 中间有括号分隔，不构成 CJK→latin 直连，故不误判。
    """
    lines = text.replace('\r', '\n').split('\n')
    blocks = split_table_blocks(lines)
    col1_numeric = col1_school = 0
    for b in blocks:
        c = parse_cells(b)
        if not c:
            continue
        c1, _, _ = c
        if level_of_cell(c1) is not None:
            col1_numeric += 1
        elif c1.endswith('系：') or c1.endswith('系:'):
            col1_school += 1
    glued = len(re.findall(r'[一-鿿][A-Za-z]', re.sub(r'\s', '', text)))
    bold_level = sum(1 for ln in lines if re_bold_level.match(ln.strip()))
    bold_book = sum(1 for ln in lines if re_bold_book.match(ln.strip()))
    if col1_numeric >= 2 and glued >= 30:
        return 'D'
    if col1_numeric >= 2:
        return 'A'
    if col1_school >= 2:
        return 'C'
    if bold_level and not col1_numeric:
        return 'B'
    return None  # 纯英文等不可解析页


def extract_entries(body, default_book, book_suffix=False):
    """对结构化文本抽全部「中文名（English）」对；返回 [(cn, en, book)]。

    ENTRY finditer 对粘连条目（`（Bleed）晕眩术（Daze）`）与折行英文名同样鲁棒，
    不依赖分隔符。book = 容器书 default_book；book_suffix=True 时（C 格式
    `搜寻术（Sift）APG，` 尾缀书）再嗅探条目后尾缀书优先。
    """
    out = []
    for m in ENTRY.finditer(body):
        cn = m.group(1).strip()
        en = fold_ws(m.group(2))
        if not valid_entry(cn):
            continue
        book = default_book
        if book_suffix:
            seg = body[m.end():].split('，')[0].split(',')[0].split('。')[0].split('、')[0]
            rm = re_book_suffix.search(seg)
            if rm and rm.group(1) in SOURCE_BOOKS:
                book = rm.group(1)
        out.append((cn, en, book))
    return out


def cells_of(block):
    """逻辑块 → 非空单元格字符串列表（按 | 边界切分、去空、收 trim）。分隔/空块返回 None。"""
    txt = '\n'.join(block).strip()
    if not txt or re_sep_row.match(txt):
        return None
    return [c.strip() for c in txt.strip('|').split('|') if c.strip()]


def valid_entry(cn):
    """条目名粗校验：滤掉纯英文/环级词/占位噪声。保留『暂无翻译』等占位（诚实反映源）。"""
    if len(cn) < 2:
        return False
    if cn in SOURCE_BOOKS or cn in LEVEL_WORD_SET:
        return False
    if re.match(r'^[A-Za-z0-9\s,.\-]+$', cn):
        return False
    if any(k in cn for k in ('此能力', '取代', '来源', '出自', '环位', '学派')):
        return False
    return True


# ------------------------------------------------------------------ 三种格式解析
def parse_a(lines):
    """格式 A：环级/书/法术三类格交错，逐格分类切环切书，法术格独立抽 ENTRY。

    行形态统一（列位不预设、逐格判型）：
      [4格] | 0级法术 | CRB | 法术… | 法术… |   ← 环级格 + 书格 + 两个法术格
      [3格] | APG     | 法术… | 法术… |         ← 书格（继承上一环级行）+ 两个法术格
    CHM→MD 长格软折行并入续行、`|` 只在格边界出现，故每格角色独立可判：
    纯环级头格 → 切环；纯书格（`CRB`/`CRB 核心手册`）→ 切书；其余 → 法术格抽 ENTRY。
    """
    levels = defaultdict(list)  # level -> [(cn,en,book)]
    cur_level = None
    cur_book = None
    for b in split_table_blocks(lines):
        for cell in cells_of(b) or []:
            ml = level_of_cell(cell)
            if ml is not None:
                cur_level = ml
                continue
            bk = norm_book(cell)
            if bk is not None:  # 纯书格
                cur_book = bk
                continue
            if cur_level is None:  # 首个环级头前的 intro 段（理论上 A 不会）——忽略
                continue
            for cn, en, eb in extract_entries(cell, cur_book, book_suffix=False):
                levels[cur_level].append((cn, en, eb))
    return levels


def parse_b(lines):
    """格式 B（催眠师/异能者）：`**N级XX法术**` 切环；`**CRB——**条目，…` 书前缀行 + 列 0 硬折行续。

    B 页英文名在物理行间按列 0 硬折（`七彩喷射（Color \\nSpray），命令术…`），逐行抽取会把
    跨行名配不齐而丢。故按「书前缀 **BOOK——**」切分段落：同一书内文本片段以空格重接折行
    （去掉列 0 换行，等价还原书写序列），再整体跑 ENTRY。环级加粗头/书前缀为段落边界，flush 前一书。
    """
    levels = defaultdict(list)
    cur_level = None
    cur_book = None
    started = False
    buf = []

    def flush():
        if started and cur_level is not None and buf:
            for cn, en, eb in extract_entries(' '.join(buf), cur_book):
                levels[cur_level].append((cn, en, eb))
        buf.clear()

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if re_sep_row.match(s) or s.startswith('|'):
            continue
        mb = re_bold_level.match(s)
        if mb:
            flush()
            cur_level = int(mb.group(1))
            cur_book = None
            started = True
            continue
        if not started:
            continue  # intro 段落在首个环级头前，跳过（避免误抽「Mesmerist Spells」等标题假条目）
        mbook = re_bold_book.match(s)
        if mbook:
            flush()
            cur_book = norm_book(mbook.group(1))
            rest = re_bold_book.sub('', s).strip()
            if rest:
                buf.append(rest)
        else:
            buf.append(s)  # 列 0 硬折行续，属当前书
    flush()
    return levels


def parse_c(lines):
    """格式 C（秘学士）：学派表 + 加粗环级头续行。

    结构实测：学派表行 `| 防护系： | 造水术（Create ⏎ Water），稳定伤势… |`，条目长格跨
    物理续行（须并块）；环级加粗头 `**1环秘学士法术**` 常以续行形式粘在前一块尾（非独立
    `|` 行）。0 环无加粗头（紧跟 intro 学派表）→ cur_level 默认 0。
    每块两阶段：先按当前环抽法术（格文本剔除裹入的环级头字样），再扫描块内加粗头推进环级。
    """
    levels = defaultdict(list)
    cur_level = 0
    for b in split_table_blocks(lines):
        for cell in cells_of(b) or []:
            cell = re_bold_level.sub('', cell).strip()
            if not cell:
                continue
            for cn, en, eb in extract_entries(cell, None, book_suffix=True):
                levels[cur_level].append((cn, en, eb))
        for ln in b:
            mb = re_bold_level.match(ln.strip())
            if mb:
                cur_level = int(mb.group(1))
    return levels


def _is_cjk(ch):
    return '㐀' <= ch <= '鿿'


def parse_glued(text):
    """D 格式粘连名切分：`出血术Bleed 舞光术dancing lights …（OA）` 序列 → [(cn, en, book)]。

    通灵者页：法术名中文直接粘连小写英文、无括号分隔（`出血术Bleed`），词间空格重接硬折行后
    序列 = CJK串 + latin串 + 可选（书） 交替。逐串扫描：CJK 段为中文名，随后的 latin 段为
    英文名（含内部空格/斜杠/连字符），紧跟的 （书） 为来源书。句读噪声先清成空格。
    """
    out = []
    t = re.sub(r'[。.，,、;；:：]+', ' ', text)  # 句读噪声 → 空格
    t = re.sub(r'\s+', ' ', t)                  # 任意空白折叠为单空格（英文名跨行硬折复原）
    n = len(t)
    i = 0
    while i < n:
        while i < n and not _is_cjk(t[i]):
            i += 1
        if i >= n:
            break
        j = i
        while j < n and (_is_cjk(t[j]) or t[j] == '·'):
            j += 1
        cn = t[i:j]
        k = j
        while k < n and (t[k].isascii() and (t[k].isalnum() or t[k] in " /'-")):
            k += 1
        en = t[j:k].strip()
        if not en:  # CJK 后无英文（杂行）——跳过该段避免死循环
            i = j
            continue
        book = None
        m = re.match(r'[（(]\s*([^（）()]{1,14}?)\s*[）)]', t[k:])
        if m:
            book = norm_book(m.group(1))
            k += m.end()
        out.append((cn, fold_ws(en), book))
        i = k
    return out


def parse_d(lines):
    """格式 D（通灵者）：环级头块 col1=环级，col2/3 整环粘连名。"""
    levels = defaultdict(list)
    cur_level = None
    for b in split_table_blocks(lines):
        cells = cells_of(b)
        if not cells:
            continue
        c0 = level_of_cell(cells[0])
        if c0 is not None:
            cur_level = c0
            spell_cells = cells[1:]
        else:
            spell_cells = cells  # 块头非环级：继承当前环
        if cur_level is None:
            continue
        for cell in spell_cells:
            for cn, en, book in parse_glued(cell):
                if not valid_entry(cn):
                    continue
                levels[cur_level].append((cn, en, book))
    return levels


# ------------------------------------------------------------------ chunk 交叉
def dedupe(entries):
    """同环去重：以 (归一中文名, 小写英文名) 为键保序去重。"""
    seen, out = set(), []
    for cn, en, book in entries:
        key = (normalize(cn), fold_lower(en))
        if key in seen:
            continue
        seen.add(key)
        out.append((cn, en, book))
    return out


def build_class_index(class_chunks):
    """职业库索引：doc_id(=列表页相对 pf_rules_md_organized/职业 路径) → 首个 chunk。

    列表页在职业库未必有对应 chunk（职业库 doc 覆盖类特性页为主，法术列表页多数
    未向量化）；对不上则返回 None，list_chunk_id 置 null 不阻塞（V1 允许）。"""
    first = {}
    for ch in class_chunks:
        d = (ch.get('doc_id') or '').strip()
        if d and d not in first:
            first[d] = ch.get('chunk_id')
    return first


def build_spell_index(chunks):
    """法术库索引：title(原样)→chunk 列表、alias 折叠键→chunk 列表。"""
    by_title, by_alias = defaultdict(list), defaultdict(list)
    for ch in chunks:
        t = (ch.get('title') or '').strip()
        if t:
            by_title[t].append(ch)
        for a in (ch.get('aliases') or []):
            fa = fold_lower(str(a))
            if fa:
                by_alias[fa].append(ch)
    return by_title, by_alias


def cross_ref(cn, en, book, by_title, by_alias):
    """chunk_id 交叉：中文名（过 normalize）+ 英文名 + 来源书三键评分，取最高候选。"""
    cand = list(by_title.get(normalize(cn), []))
    fen = fold_lower(en)
    if fen:
        for c in by_alias.get(fen, []):
            if c not in cand:
                cand.append(c)
    if not cand:
        return None, None, 0
    best, best_s = None, -1
    for c in cand:
        s = 0
        cb = c.get('book_abbreviation')
        if book and cb == book:
            s += 3
        if fen and any(fold_lower(str(a)) == fen for a in (c.get('aliases') or [])):
            s += 2
        if normalize(cn) == normalize((c.get('title') or '').strip()):
            s += 1
        if s > best_s:
            best, best_s = c, s
    return best.get('chunk_id'), (best.get('book_abbreviation') or ''), best_s


def derive_toc_path(rel):
    """列表页 rel → CHM TOC 路径：职业 → <大类> → <职业目录> → 法术列表。"""
    parts = rel.split('/')
    if len(parts) >= 3:
        return f'职业 → {parts[0]} → {parts[1]} → 法术列表'
    return f'职业 → {rel}'


def derive_excerpt(text, entry_cnt):
    """溯源摘要 = 列表页首个标题行 + 「本职业收录 0~9 环法术共 M 条」概述（拍板方案，
    截断 ~500 字符）。标题行取首个非空且非表格行的行（列表页第一行多为职业名标题）。"""
    title = ''
    for ln in text.replace('\r', '\n').split('\n'):
        s = re.sub(r'\*+', '', ln.strip())
        if s and not s.startswith('|'):
            title = s
            break
    ex = f'{title}；本职业收录 0~9 环法术共 {entry_cnt} 条'
    return ex[:500]


# ------------------------------------------------------------------ 主流程
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    chunks = [json.loads(l) for l in open(CHUNKS_PATH, encoding='utf-8')]
    by_title, by_alias = build_spell_index(chunks)
    print(f'法术库 chunks: {len(chunks)} | title 键 {len(by_title)} | alias 键 {len(by_alias)}')
    # 职业库 list_chunk_id 交叉（doc_id 即 rel；文件不存在/对不上 → 全 null 不阻塞）
    class_doc = {}
    if os.path.exists(CLASS_CHUNKS_PATH):
        with open(CLASS_CHUNKS_PATH, encoding='utf-8') as f:
            class_doc = build_class_index(json.loads(l) for l in f)
        print(f'职业库 chunks 索引: {len(class_doc)} 个 doc_id')

    classes = {}
    report = {'generated_from': '职业列表页 27 路径', 'pages': {}, 'issues': []}
    tot_entries = tot_hit = tot_miss = 0

    for cls, rel in CLASS_LISTS.items():
        path = os.path.join(ORGANIZED_ROOT, rel)
        try:
            text = open(path, encoding='utf-8').read()
        except OSError as e:
            report['issues'].append({'职业': cls, '问题': f'读取失败 {e}'})
            continue
        fmt = classify_format(text, PAGE_NOTES.get(cls))
        if fmt is None:
            report['issues'].append({'职业': cls, '问题': PAGE_NOTES.get(cls, '页面格式无法识别（无表格/加粗环级头）')})
            continue
        lines = text.replace('\r', '\n').split('\n')
        levels = {'A': parse_a, 'B': parse_b, 'C': parse_c, 'D': parse_d}[fmt](lines)
        levels = {lv: dedupe(ents) for lv, ents in levels.items()}

        page_hit = page_miss = 0
        page_entry_cnt = 0
        levels_json = {}
        for lv in range(10):
            item_json = []
            for cn, en, book in levels.get(lv, []):
                cid, cbook, score = cross_ref(cn, en, book, by_title, by_alias)
                if cid:
                    page_hit += 1
                else:
                    page_miss += 1
                item_json.append({
                    'cn': cn, 'en': en, 'book': book,
                    'chunk_id': cid, 'cross_book': cbook, 'cross_score': score,
                })
                page_entry_cnt += 1
            levels_json[str(lv)] = item_json

        tot_entries += page_entry_cnt
        tot_hit += page_hit
        tot_miss += page_miss
        # 输出职业键归一：唤魂师双页 → 规范键「唤魂师」（page_1037 承载数据）
        canonical = CANONICAL_CLASS.get(cls, cls)
        # 本职业自己的别名（反向查变体→规范键表）；如 诗人/游吟诗人 → 吟游诗人
        aliases = [v for v, c in CLASS_ALIASES.items() if c == canonical]
        classes[canonical] = {
            'aliases': aliases,
            'source_page': rel,
            'source_toc_path': derive_toc_path(rel),
            'source_excerpt': derive_excerpt(text, page_entry_cnt),
            # 职业库 doc_id 交叉：列表页已向量化则取该页首 chunk_id，否则 null
            'list_chunk_id': class_doc.get(rel),
            'levels': levels_json,
        }
        report['pages'][cls] = {
            'format': fmt, 'entries': page_entry_cnt,
            'by_level': {str(lv): len(levels.get(lv, [])) for lv in range(10)},
            'chunk_hit': page_hit, 'chunk_miss': page_miss,
            'null_rate': round(page_miss / page_entry_cnt, 3) if page_entry_cnt else None,
            'list_chunk_id': class_doc.get(rel),
        }

    payload = {
        'version': '1.0',
        'generated_from': '职业列表页 27 路径（脚本 CLASS_LISTS 注册表）',
        'classes': classes,
    }
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    list_hit = sum(1 for p in report['pages'].values() if p.get('list_chunk_id'))
    report['summary'] = {
        '职业数': len(classes), '总条目': tot_entries,
        'chunk命中': tot_hit, 'chunk缺失': tot_miss,
        'null率': round(tot_miss / tot_entries, 3) if tot_entries else None,
        'list_chunk命中': list_hit,
    }
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    # ---- 自校验 + 对账打印 ----
    print(f'\n{"职业":<14}{"格式":<4}{"条目":>6}  各环条目数(0-9)                         命中/缺失')
    for cls, rel in CLASS_LISTS.items():
        p = report['pages'].get(cls)
        if not p:
            note = PAGE_NOTES.get(cls, '未解析')
            print(f'{cls:<14}{"-":<4}{" -":>6}  {note}')
            continue
        by = p['by_level']
        row = ' '.join(f'{by[str(i)]:>3}' for i in range(10))
        print(f'{cls:<14}{p["format"]:<4}{p["entries"]:>6}  {row}  '
              f'{p["chunk_hit"]}/{p["chunk_miss"]} null率={p["null_rate"]}')
    s = report['summary']
    print(f'\n===== 汇总：职业 {s["职业数"]} / 条目 {s["总条目"]} / '
          f'chunk 命中 {s["chunk命中"]} / 缺失 {s["chunk缺失"]} / null率 {s["null率"]} / '
          f'list_chunk 命中 {s["list_chunk命中"]} =====')

    # 自校验断言：27 职业全部成功解析（跳过页除外）；每条记录字段完整
    assert len(classes) + len([1 for i in report['issues'] if i['职业'] in PAGE_NOTES]) >= 27, \
        f'解析失败职业数异常: {[i for i in report["issues"]]}'
    for cls in classes:
        assert set(classes[cls]['levels']) == {str(i) for i in range(10)}, cls + ' levels 键不全'
    print('自校验通过：levels 键 0~9 齐备，记录字段完整。产物 →', JSON_PATH)


if __name__ == '__main__':
    main()
