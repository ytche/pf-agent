# -*- coding: utf-8 -*-
"""从 4 个 HTML 重建 3 个专长聚合文件为规范条目（整理规则 §10/§12）。
条目名清单为人工阅读确认；按 zh 定位块、按 zh/en 组装标题、规范化后提取描述与字段。

输出到 _rebuild_draft/（相对本脚本），人工核对后复制到
pf_rules_md_organized/专长/ 下对应文件。2026-08-01 R1 返工交付。
"""
import re, html as html_mod
from pathlib import Path

HTML_DIR = Path('/Users/chezi/.openclaw/workspace/pf_rules')
OUT = Path(__file__).resolve().parent / '_rebuild_draft'
OUT.mkdir(parents=True, exist_ok=True)

def load(path):
    raw = path.read_bytes()
    for enc in ('gb18030', 'utf-8'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('gb18030', errors='ignore')

def coarse(html):
    t = html[html.lower().find('<body'):] if '<body' in html.lower() else html
    t = re.sub(r'<BR[^>]*>', '\n', t, flags=re.I)
    t = re.sub(r'<STRONG[^>]*>', '**', t, flags=re.I)
    t = re.sub(r'</STRONG>', '**', t, flags=re.I)
    t = re.sub(r'<EM[^>]*>', '*', t, flags=re.I)
    t = re.sub(r'</EM>', '*', t, flags=re.I)
    t = re.sub(r'<[^>]+>', '', t)
    t = html_mod.unescape(t)
    t = t.replace('\r', '')
    t = re.sub(r'\n{3,}', '\n\n', t)
    lines = [ln.strip() for ln in t.split('\n')]
    return '\n'.join(ln for ln in lines if ln)

# 条目清单： (中文名, 英文名)
ENTRIES = {
    'page_547': [
        ('改善日常工作', 'Impro Day Jos'),
        ('蓄势待发（战斗）', 'PATIENT STRIKE (COMBAT)'),
        ('魔法回收', 'STEADFAST MIND'),
        ('快速准备', 'QUICK PREPARATION'),
        ('声誉', 'RENOWN'),
        ('自发准备', 'VERSATILE SPONTANEITY'),
        ('集思广益（团队）', 'COLLECTIVE RECOLLECTION (TEAMWORK)'),
        ('洞悉弱点', 'ESOTERIC ADVANTAGE'),
        ('奇妙激活', 'Uncanny Activation'),
        ('紧急调整', 'EMERGENCY ATTUNEMENT'),
        ('有备无患', 'PLANNED SPONTANEITY'),
        ('魔毯行者', 'TAPESTRY TRAVELER'),
        ('快速转进', 'CUT YOUR LOSSES'),
        ('卑鄙协作（战斗，团队）', 'UNDERHANDED TEAMWORK (COMBAT, TEAMWORK)'),
        ('特卑鄙协作（战斗，团队）', 'IMPROVED UNDERHANDED TEAMWORK(COMBAT, TEAMWORK)'),
    ],
    'page_437': [
        ('好伙伴', 'Boon Companion'),
        ('重击导魔', 'Critical Conduit'),
        ('额外装备位', 'Extra Item Slot'),
        ('魔宠专攻', 'Familiar Focus'),
        ('魔宠法术（超魔专长）', 'Familiar Spell (Metamagic)'),
        ('跳跃者', 'Jumper'),
        ('轻柔攻击者', 'Lithe Attacker'),
        ('同族之主', 'Master of Your Kind'),
        ('纤细身躯', 'Narrow Frame'),
        ('法术海绵', 'Spell Sponge'),
        ('稳健奔驰', 'Stable Gallop'),
        ('脚踏实地', 'Sure-Footed'),
        ('勇猛坐骑', 'Valiant Steed'),
    ],
    'page_1258': [
        ('毒性分泌物', 'Toxic Secretions'),
        ('毒性硬脂', 'Poison Resin'),
        ('剧毒接触', 'Noxious Touch'),
        ('溢血之毒', 'Hemorrhaging Venom'),
        ('剧毒喷雾', 'Toxic Spray'),
        ('致命毒液', 'Virulent Venom'),
        ('粘稠毒液', 'Viscous Venom'),
        ('解法之血', 'Dispelling Blood'),
        ('鬼咒脓液', 'Ghostbane Ichor'),
        ('拆解之血', 'Unraveling Blood'),
        ('守护之血', 'Warding Blood'),
    ],
    'page_1263': [
        ('延迟药水', 'Delayed Potion'),
        ('治疗药水', 'Healing Potion'),
        ('蒸汽药水', 'Vaporous Potion'),
    ],
}

FIELD_PAT = re.compile(r'\*\*([一-鿿]{2,10})[：:]\*\*|\*\*([一-鿿]{2,10})\*\*[：:]')

# 非条目内容起始：变体/血脉/章节标题、变体/血脉能力（字段值在此截止）
SECTION = re.compile(
    r'\*\*[^*\n]{1,8}[\s\S]{0,40}?【[^】]*变体】'          # 变体标题（**中文名…【…变体】**，如 **曼特蛙\n（Mantella）【树蛙人德鲁伊变体】**）
    r'|【[^】]*变体】'                                     # 独立【变体】标题兜底
    r'|（术士血脉）'                                       # 血脉标题（蝎子血脉）
    r'|\*\*剧毒遗产'                                       # 剧毒遗产章节
    r'|\*\*娜迦裔专长|\*\*蝮血裔专长'                      # 种族专长章节标题
    r'|\*\*娜迦裔 |\*\*蝮血裔'                             # 种族章节标题
    r'|\*\*适饮法术'                                       # 法术章节（page_1263）
    r'|\*\*[^*]{0,24}?[A-Za-z’’][^*]{0,40}?[（(](?:Su|Ex|Sp)[）)][：:]\*{1,3}'  # 变体/血脉能力
)

def find_zh(text, zh):
    """zh 定位，兼容全角/半角括号变体。"""
    variants = [zh, zh.replace('（', '(').replace('）', ')'), zh.replace('(', '（').replace(')', '）')]
    for v in variants:
        i = text.find(v)
        if i >= 0:
            return i
    return -1

def split_entries(text, entries):
    """按标题行（去星号后行首匹配 zh 变体）定位条目起始行号。
    行首匹配避免命中正文引用（如"纤细身躯"出现在轻柔攻击者的先决条件里）。
    块结束 = 下一标题行。"""
    stripped = text.replace('*', '')
    slines = stripped.split('\n')
    poss = []
    for (zh, en) in entries:
        variants = [zh, zh.replace('（', '(').replace('）', ')'), zh.replace('(', '（').replace(')', '）')]
        found = None
        for i, line in enumerate(slines):
            ls = line.strip()
            for v in variants:
                if ls.startswith(v):
                    found = (i, v)
                    break
            if found:
                break
        if not found:
            raise RuntimeError(f"标题行未找到: {zh}")
        poss.append((found[0], zh, en))
    poss.sort(key=lambda p: p[0])
    for i in range(len(poss) - 1):
        if poss[i][0] >= poss[i+1][0]:
            raise RuntimeError(f"条目顺序异常: {poss[i][1]} >= {poss[i+1][1]}")
    return poss

def parse_entry(block, zh, en):
    """规范化加粗标点 → 字段/章节边界切分 → 描述（EM 优先，否则去标题）。"""
    norm = re.sub(r'\*{1,2}([：:。，、；♂,:])\*{1,2}', r'\1', block)
    # 内容边界：字段标签（值起点=标签后）与章节/变体起始（值终点）
    boundaries = []
    for m in FIELD_PAT.finditer(norm):
        boundaries.append((m.start(), 'field', m.end(), m.group(1) or m.group(2)))
    for m in SECTION.finditer(norm):
        boundaries.append((m.start(), 'section', None, None))
    boundaries.sort(key=lambda b: b[0])
    pre = norm[:boundaries[0][0]] if boundaries else norm
    # 第一个 section 边界之后的字段（变体/血脉/法术区）不属于本条，截止
    section_cut = len(norm)
    for pos, kind, _, _ in boundaries:
        if kind == 'section':
            section_cut = pos
            break
    fields = []
    for k, (pos, kind, vend, label) in enumerate(boundaries):
        if kind != 'field' or pos >= section_cut:
            continue
        s = vend
        e = boundaries[k+1][0] if k+1 < len(boundaries) else len(norm)
        if e > section_cut:
            e = section_cut
        val = norm[s:e].strip()
        # 剔除字段值尾部混入的小节导语段（**...** 包裹、以句号结尾的独立段落）
        lead = re.search(r'\n\*\*[^*\n]+。\*\*\s*$', val)
        if lead:
            val = val[:lead.start()].strip()
        # 折叠为单行：源 HTML 的 <BR> 在英文术语/句子中部断行，若保留换行，
        # 续行（中文开头+英文括号）会被 formats 的 M6/M9 裸中英行逻辑误判成
        # 幽灵条目标题（实测动物档案魔宠法术 好处 多行值拆出第 14 条）。
        val = re.sub(r'\s+', ' ', val).strip()
        fields.append((label, val))
    # EM 描述要求换行前导，避免把 **标题** 的第二个 * 误当描述
    em = re.search(r'\n\*([^*\n].*?)\*', pre, re.S)
    if em:
        desc = em.group(1).strip()
    else:
        i = find_zh(pre, zh)
        if i >= 0:
            # 标题行整体吃掉（英文名/类型括号跨行残留留在标题行及下一行首）
            line_end = pre.find('\n', i)
            if line_end >= 0:
                pre = pre[line_end+1:]
            else:
                pre = pre[i+len(zh):]
        pre = re.sub(r'^[^一-鿿]+', '', pre)
        desc = pre.strip().strip('*').strip()
    return desc, fields

def build_md(zh, en, desc, fields, src_line, src_note):
    lines = [f"<!-- {src_line} -->", "", f"**{zh}（{en}）**  ", "", src_note, ""]
    if desc:
        lines += [f"*{desc}*", ""]
    for label, val in fields:
        lines += [f"**{label}：**{val}", ""]
    return '\n'.join(lines)

META = {
    '初探探索者协会_专长.md': {
        'pages': ['page_547'], 'header': '# 初探探索者协会 专长',
        'src_prefix': '初探探索者协会',
        'src_note': '> 来源：初探探索者协会（Pathfinder Society Primer），页码见原书，未整理 → 初探探索者协会 → 专长',
    },
    '药剂与毒药P&P_专长.md': {
        'pages': ['page_1258', 'page_1263'], 'header': '# 药剂与毒药P&P 专长',
        'src_prefix': '药剂与毒药P&P',
        'src_note': '> 来源：药剂与毒药（Potions and Poisons），页码见原书，未整理 → 药剂与毒药P&P → 专长',
    },
    '动物档案AArch_动物专长.md': {
        'pages': ['page_437'], 'header': '# 动物档案 AArch 动物专长',
        'src_prefix': 'AArch',
        'src_note': '> 来源：动物档案（Animal Archive）AArch，页码见原书，未整理 → 动物档案AArch → 动物专长',
    },
}

results = {}
for fname, meta in META.items():
    parts = [meta['header'], ""]
    total = 0
    for page in meta['pages']:
        text = coarse(load(HTML_DIR / f"{page}.html"))
        poss = split_entries(text, ENTRIES[page])
        lines = text.split('\n')
        for i, (ln, zh, en) in enumerate(poss):
            end = poss[i+1][0] if i+1 < len(poss) else None
            block = '\n'.join(lines[ln:end])
            desc, fields = parse_entry(block, zh, en)
            src_line = f"{meta['src_prefix']}-source:{page}.md:{zh}({en})"
            parts += [build_md(zh, en, desc, fields, src_line, meta['src_note']), ""]
            total += 1
    results[fname] = {'total': total, 'content': '\n'.join(parts)}
    print(f"{fname}: {total} entries")

for fname, r in results.items():
    (OUT / fname).write_text(r['content'], encoding='utf-8')
print("draft written to", OUT)
