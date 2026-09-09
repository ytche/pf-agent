#!/usr/bin/env python3
"""
为仅靠 Rule 2 捕获的真实变体追加 【X变体】 标记。

背景：looks_like_archetype_title 的 Rule 2（名称（English）【任意内容】）
不区分 【来源书缩写】 和 【变体标记】，导致特性条目被误判为 class_archetype。

方案：给所有真变体的源文件标题追加 【X变体】，让 Rule 1 捕获它们，
然后可以安全删除 Rule 2。

格式：**名称（English）【来源】 → **名称（English）【来源】【职业变体】
"""

import json
import re
import sys
import os
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path.cwd()
CHUNKS = BASE_DIR / 'vectorization_prep_profession' / 'chunks.jsonl'
# chunks.jsonl 中 doc_id 相对路径不开头含 职业/，而源文件在 职业/ 子目录下
SOURCE_DIR = BASE_DIR / 'pf_rules_md_organized' / '职业'

# ============================================================
# 17 条确认误判的 boundary entries（丢弃）
# ============================================================
FALSE_POSITIVES = set()

# 先知诅咒
FALSE_POSITIVES.add(('先知', '焦黑之臂（Blackened）【BOA】'))
FALSE_POSITIVES.add(('先知', '耗损（Consumed）【BOF】'))
FALSE_POSITIVES.add(('先知', '拆毁（Wrecker）【BOF】'))
FALSE_POSITIVES.add(('先知', '饥饿（Hunger）【ISMC】'))
FALSE_POSITIVES.add(('先知', '无力预言（Powerless Prophecy）【ISMC】'))
FALSE_POSITIVES.add(('先知', '夺舍（Possessed）【Horror Realms】'))
FALSE_POSITIVES.add(('先知', '歌缚（Song-Bound）【BotS】'))
FALSE_POSITIVES.add(('先知', '阴影（Shadow）【先知先知秘示域】'))

# 术士血统
FALSE_POSITIVES.add(('术士', '灵质血统 (Ectoplasm) 【OA】'))
FALSE_POSITIVES.add(('术士', '兽人血脉(Orc)【OoG】'))

# 炼金术师 — 科研发现
FALSE_POSITIVES.add(('炼金术师', '剧毒炸弹（Poisoned Explosive）【DTT 炼金术师科研发现】'))
FALSE_POSITIVES.add(('炼金术师', '沙尘炸弹（sand bomb，SU）【反英雄手册 Antihero\'s Handbook pg. 29】'))

# 法师奥术发现（page_319 整页）
FALSE_POSITIVES.add(('法师', '前提：法师等级1     效果：选择一种魔法物品的类型（药水、奇物，诸如此类的）。你制造这种类型的魔法物品的时候比正常快２５％，以及在制造这种魔法物品的法术辨识检定（或其它检定，如果适用）得到＋４加值。     特殊：你可以多次选择这个发现，效果不叠加。每次你在选择这个发现的时候，必须是用在不同魔法物品的类型。平衡召唤 (Balanced Summoning)【CoB】'))
FALSE_POSITIVES.add(('法师', '面具联结 (Bonded Mask)【AP#80】'))
FALSE_POSITIVES.add(('法师', '前提：法师等级1     效果：当你施放的一个防护系法术防止伤害（DR或者能量抗力）时，如果进行攻击的生物在被防护的生物30尺内，每有10点伤害被防止，攻击者就承受1d6伤害。艾恩联结 (Ioun Bond)【PotR】'))
FALSE_POSITIVES.add(('法师', '前提：法师等级5     效果：你施展任何同时出现在法师和炼金术士法术列表上的法术时获得+1施法者等级和+1DC。此外你能从炼金术士的公式簿将法术抄进你的法术书，就像你从其他法师的法术书里抄写法术一样。弹性幻术 (Resilient Illusions)【MM】'))
FALSE_POSITIVES.add(('法师', '前提：法师等级9     效果：你学习到制造单一类型魔像的艺术和工艺（像是石魔像或铁魔像）。当制造此种类型的魔像时，你被认为拥有制造奇物、制造魔法武器和防具、制造构装体专长。你必须符合其它全部的正常魔像建造需求。     特殊：你可以多次选择这个发现，应用在不同类型的魔像上。禁制研究 (Opposition Research)【UM】'))
FALSE_POSITIVES.add(('法师', '前提：法师等级10     效果：这个能力的作用如同一个只有1轮表面时间的[时间停止(Time Stop)]法术。你每天能使用该能力1次，在10级后每有5个法师等级次数加一次。类法杖魔杖 (Staff-Like Wand)【UM】'))

# 唤魂师情感羁绊
FALSE_POSITIVES.add(('唤魂师', '色欲（Lust）【魅影情感羁绊】'))

# 游侠战斗流派
FALSE_POSITIVES.add(('游侠', '水下（Underwater）【AA 游侠战斗流派】'))

# 牧师子域
FALSE_POSITIVES.add(('牧师', '阴影子域（Shadow Subdomain）【牧师牧师子域】'))

# 血脉狂怒者血脉
FALSE_POSITIVES.add(('血脉狂怒者', '阴影（Shadow）【血脉狂怒者血脉狂怒者血脉】'))
FALSE_POSITIVES.add(('血脉狂怒者', '海洋（Aquatic）【AA 血脉狂怒者血脉】'))
FALSE_POSITIVES.add(('血脉狂怒者', '鬼婆血脉（Hag）【BotC】'))
FALSE_POSITIVES.add(('血脉狂怒者', '血脉狂怒者 血脉（Vestige Bloodline）【BotA】'))

# 边界审计确认的真变体（从 19 条中挑出）
BOUNDARY_REAL = {
    ('炼金术师', '幽影化学家（Gloom Chymist）【炼金术师变体与科研发现】'): '炼金术师',
    ('血脉狂怒者', '绝境巡行者（Prowler at world\'s end）【血脉狂怒者】'): '血脉狂怒者',
}

# ============================================================
# 辅助函数
# ============================================================

rule1_re = re.compile(r'【[^】]*?变体】')
rule2_re = re.compile(r'[（(][A-Za-z][^）)]*[）)]\s*【[^】]+】')


def is_rule2_only(title: str) -> bool:
    """检查标题是否被 Rule 1 跳过但被 Rule 2 捕获。"""
    if rule1_re.search(title):
        return False
    if rule2_re.search(title):
        return True
    return False


def normalize_en(name: str) -> str:
    """标准化英文名以便匹配。"""
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def make_replacement_title(old_bold_content: str, base_class: str) -> str:
    """
    old_bold_content: **与** 之间的内容，如 "书卷学者（Archivist）【APG】"
    返回新的 bold content，如 "书卷学者（Archivist）【APG】【吟游诗人变体】"
    """
    # 如果已含 【X变体】 则不重复加
    if rule1_re.search(old_bold_content):
        return old_bold_content
    return old_bold_content + f'【{base_class}变体】'


def _title_matches(search_text: str, en_name: str | None, src_tag: str | None) -> bool:
    """检查文本中是否有 en_name 和 src_tag（处理 **/~~/换行）。"""
    # 去掉 ** / ~~ / 换行，折叠空白
    text = search_text.replace('*', '').replace('~', '')
    text = re.sub(r'\s+', ' ', text)

    if en_name:
        if en_name not in text:
            # 从括号提取标准化比较
            m = re.search(r'[（(]([^）)]+)[）)]', text)
            if m:
                line_en = normalize_en(m.group(1))
                if normalize_en(en_name) != line_en:
                    return False
            else:
                return False

    if src_tag:
        # 匹配 【src_tag】 或 【**src_tag**】 等
        pat = rf'【[^】]*?{re.escape(src_tag)}[^】]*】'
        if not re.search(pat, text):
            return False

    return True


# ============================================================
# 主逻辑
# ============================================================

def collect_entries():
    """从 chunks.jsonl 收集所有仅 Rule 2 命中的条目。"""
    entries = []
    with open(CHUNKS, encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            if c.get('component_type') != 'class_archetype':
                continue
            title = c.get('title', '') or ''
            if not is_rule2_only(title):
                continue

            cls = c.get('class_name', '') or ''
            doc = c.get('doc_id', '') or ''
            key = (cls, title)

            # 跳过确认的误判
            if key in FALSE_POSITIVES:
                continue

            # 边界条目：确认在 BOUNDARY_REAL 中
            if key in BOUNDARY_REAL:
                base_class = BOUNDARY_REAL[key]
            else:
                # 默认：class_name = base_class
                base_class = cls

            entries.append({
                'class_name': cls,
                'base_class': base_class,
                'title': title,
                'doc': doc,
                'key': key,
            })
    return entries


def build_edit_plan(entries):
    """
    构建编辑计划：对每个条目，在源文件中找到对应的标题行。
    支持：
    - 单行标题（Pass 1）
    - 多行标题（Pass 2）：cn_name 在行 N，】在行 N+1（常见于 ACG/ARG 换行）
    - ~~ 删除线干扰（_title_matches 自动处理）
    """
    plan = []

    # 按文件分组
    by_file = defaultdict(list)
    for e in entries:
        by_file[e['doc']].append(e)

    for doc_rel, file_entries in sorted(by_file.items()):
        filepath = SOURCE_DIR / doc_rel
        if not filepath.exists():
            print(f'  ⚠️  文件不存在: {filepath}', file=sys.stderr)
            continue

        with open(filepath, encoding='utf-8') as f:
            content = f.read()
        lines = content.splitlines(keepends=True)

        for e in file_entries:
            title = e['title']
            base_class = e['base_class']
            cls = e['class_name']

            # 从 title 提取关键匹配信息
            # 中文名 = title 中第一个 （或 ( 之前的部分
            m = re.match(r'^([^（(]+)', title)
            if not m:
                print(f'  ⚠️  无法提取中文名: [{cls}] {title}', file=sys.stderr)
                continue
            cn_name = m.group(1).strip()

            # 英文名（用于更精确的匹配）
            en_name = None
            m = re.search(r'[（(]([^）)]+)[）)]', title)
            if m:
                en_name = normalize_en(m.group(1))

            # 来源标记
            src_tag = None
            m = re.search(r'【([^】]+)】', title)
            if m:
                src_tag = m.group(1)

            # 构造新 bold content（仅用于跳过已含 【X变体】 的条目）
            old_bold_content = title
            new_bold_content = make_replacement_title(old_bold_content, base_class)

            if old_bold_content == new_bold_content:
                continue  # 无需修改

            found = False

            # --- Pass 1: 单行匹配 ---
            for i, line in enumerate(lines):
                if cn_name not in line:
                    continue
                if not _title_matches(line, en_name, src_tag):
                    continue
                last_close = line.rfind('】')
                if last_close == -1:
                    continue
                new_line = line[:last_close + 1] + f'【{base_class}变体】' + line[last_close + 1:]
                if new_line == line:
                    continue
                plan.append({
                    'filepath': filepath,
                    'lineno': i + 1,
                    'class_name': cls,
                    'base_class': base_class,
                    'title': title,
                    'old_line': line.rstrip('\n\r'),
                    'new_line': new_line.rstrip('\n\r'),
                })
                found = True
                break

            # --- Pass 2: 多行回退 ---
            if not found:
                for i, line in enumerate(lines):
                    if cn_name not in line:
                        continue
                    if i + 1 >= len(lines):
                        continue
                    combined = line + lines[i + 1]
                    if not _title_matches(combined, en_name, src_tag):
                        continue
                    next_line = lines[i + 1]
                    if '】' not in next_line:
                        continue
                    last_close = next_line.rfind('】')
                    new_next = next_line[:last_close + 1] + f'【{base_class}变体】' + next_line[last_close + 1:]
                    if new_next == next_line:
                        continue
                    plan.append({
                        'filepath': filepath,
                        'lineno': i + 2,
                        'class_name': cls,
                        'base_class': base_class,
                        'title': title,
                        'old_line': next_line.rstrip('\n\r'),
                        'new_line': new_next.rstrip('\n\r'),
                    })
                    found = True
                    break

            if not found:
                print(f'  ❌ 未匹配: [{cls}] {title}', file=sys.stderr)
                for i, line in enumerate(lines):
                    if cn_name in line and src_tag and f'【{src_tag}】' in line:
                        print(f'     疑似行 {i+1}: {line.strip()[:80]}...', file=sys.stderr)
                        break

    return plan


def dry_run(plan):
    """预览编辑计划。"""
    print(f'\n{"=" * 60}')
    print(f'编辑计划：{len(plan)} 处修改')
    print(f'{"=" * 60}\n')

    by_file = defaultdict(list)
    for p in plan:
        by_file[p['filepath']].append(p)

    for fp in sorted(by_file, key=str):
        entries = by_file[fp]
        rel = fp.relative_to(BASE_DIR)
        print(f'📄 {rel} ({len(entries)} 处):')
        for p in entries:
            print(f'  L{p["lineno"]:>4} [{p["class_name"]}→{p["base_class"]}变体]')
            print(f'    -: {p["old_line"][:90]}')
            print(f'    +: {p["new_line"][:90]}')
        print()

    print(f'总计：{len(plan)} 处修改，{len(by_file)} 个文件')


def apply_plan(plan):
    """执行编辑计划。"""
    by_file = defaultdict(list)
    for p in plan:
        by_file[p['filepath']].append(p)

    total_modified = 0
    for fp in sorted(by_file, key=str):
        entries = by_file[fp]
        with open(fp, encoding='utf-8') as f:
            lines = f.readlines()

        modified = 0
        for p in entries:
            lineno = p['lineno'] - 1  # 0-indexed
            old = lines[lineno]
            new = p['new_line'] + '\n'
            if old == new:
                print(f'  跳过（已修改）: L{p["lineno"]}', file=sys.stderr)
                continue
            lines[lineno] = new
            modified += 1

        if modified:
            with open(fp, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            total_modified += modified
            print(f'  ✅ {fp.relative_to(BASE_DIR)}: {modified} 处修改')

    print(f'\n总计：{total_modified} 处修改，{len(by_file)} 个文件')
    return total_modified


# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description='为仅靠 Rule 2 捕获的真实变体追加 【X变体】 标记')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不修改')
    parser.add_argument('--apply', action='store_true', help='执行修改')
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.print_help()
        print('\n请指定 --dry-run（预览）或 --apply（执行）')
        sys.exit(1)

    print('📡 收集仅 Rule 2 命中的条目...')
    entries = collect_entries()
    print(f'   → {len(entries)} 个真变体需要加标记\n')

    if not entries:
        print('没有需要修改的条目。')
        return

    print('🔍 构建编辑计划（单行匹配 → 多行回退）...')
    plan = build_edit_plan(entries)
    print(f'   → {len(plan)} 处匹配成功\n')

    unmatched = len(entries) - len(plan)
    if unmatched:
        print(f'  ⚠️  {unmatched} 条未匹配到源文件（见上方警告）\n')

    if args.dry_run:
        dry_run(plan)
    elif args.apply:
        print('✏️  执行修改...')
        total = apply_plan(plan)
        if total:
            print('\n✅ 完成！请运行向量化脚本验证结果。')

    # 输出统计
    by_class = defaultdict(int)
    for e in entries:
        by_class[e['base_class']] += 1
    print(f'\n📊 按职业统计：')
    for cls, cnt in sorted(by_class.items(), key=lambda x: -x[1]):
        print(f'   {cls}: {cnt}')


if __name__ == '__main__':
    main()
