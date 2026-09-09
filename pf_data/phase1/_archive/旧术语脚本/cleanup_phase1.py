#!/usr/bin/env python3
"""
PF 术语提取报告 Phase 1 清洗脚本 v2
- 修复"推荐翻译"字段污染
- 拆分"其他"分类
- 修正错位分类
- "制造"分类并入"专长"
"""

import argparse
import re
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="PF 术语提取报告 Phase 1 清洗脚本")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path(__file__).parent,
        help="phase1 工作目录，默认脚本所在目录",
    )
    return parser.parse_args()


ARGS = parse_args()
BASE_DIR = ARGS.base_dir.resolve()
INPUT_FILE = BASE_DIR / "术语提取报告_分类版.md"
OUTPUT_CLEAN = BASE_DIR / "术语提取报告_清洗版.md"
OUTPUT_RECAT = BASE_DIR / "术语提取报告_重分类版.md"
OUTPUT_BORDERLINE = BASE_DIR / "边界案例待复核.md"
OUTPUT_LOG = BASE_DIR / "优化日志.md"

# 描述性前缀列表（用于清洗推荐翻译）
DESCRIPTION_PREFIXES = [
    "该能力改变了", "该能力取代了", "该能力调整了", "该能力在其他方面都",
    "该法术的功能如同", "这个法术工作方式如同", "此能力如同",
    "该效果在其他方面的功能都", "该效果在判断包含", "此奖励",
    "该武器价格与重量和同书的", "这个物品基本等同于",
    "使得圣物猎手可以使用存有这些法术的", "若佩戴者能够施放",
    "每当魔宠的主人施放", "任何被", "天赋与", "和次等",
    "级获得", "级起使用", "你必须选择", "可以施展", "必须信奉",
    "职业能力", "智力调整值", "对所选近战武器拥有战士",
    "对所选远程武器拥有战士", "且你对它拥有战士的", "战士",
    "你能够", "由该法术造出的水在其他方面与", "生效的",
    "就好像受到了", "或解除", "个骰子来获得", "分钟的法术",
    "施放一次法术", "他们能够以类法术能力施放",
    "所有你的听众都会受到一个法术", "一个受到法术",
    "等级该法术的功能如同", "你无法通过共鸣通道来使用",
    "此类持续时间的延长不会与", "法术就如同被狂怒变形者使用",
    "就如同使用", "你可以用", "此武器同样获得", "匕首可以像",
    "你可以对目标施加法术", "之类的法术仍旧会如常侦测到",
    "身体", "神话", "版本的", "专长或者",
    "若一个身体成为了", "她将", "类似", "次",
    "那么他会立即受到", "并且这个法术可以被",
    "他们可以以类法术能力施放", "你可以施放", "你可以如同",
    "穿戴者被视为受到常驻的", "这个动物会获得",
    "这类似于", "这被视为", "这如同", "就如同", "类似",
    "和", "或", "不过", "即使", "一旦", "由于", "那么",
    "此能力调整了", "此能力替代", "这取代了", "这改变了",
    "能力并替代了", "不过它还能够额外提供",
    "该能力在其他方面都", "该能力取代了", "该能力改变了",
    "此能力替代", "这取代了", "这改变了", "能力并替代了",
    "就如同", "类似", "和", "或", "次",
]

# 需要修正错位的术语
MISPLACEMENT_FIXES = {
    'Shield Other': '法术',
    'Detect Evil': '法术',
    'Smite Evil': '法术',
    'Dispel Evil': '法术',
    'Detect Law': '法术',
    'Detect Chaos': '法术',
    'Detect Good': '法术',
    'Dimension Door': '法术',
    'Spring Attack': '专长',
    'Whirlwind Attack': '专长',
    'Fast Movement': '职业能力',
    'Craft Wondrous Item': '专长',
    'Craft Construct': '专长',
    'Scribe Scroll': '专长',
    'Craft Wonderous Item': '专长',
    'Craft Staff': '专长',
    'Enchantment Foil': '专长',
    # 高优先级误分类修正
    'Combat Expertise': '专长',
    'Weapon Focus': '专长',
    'Weapon Specialization': '专长',
    'Neutralize Poison': '法术',
    'Remove Disease': '法术',
    'Detect Poison': '法术',
    'Improved Trip': '专长',
    'Improved Disarm': '专长',
    'Improved Bull Rush': '专长',
    'Improved Grapple': '专长',
    'Improved Feint': '专长',
    'Improved Initiative': '专长',
    'Power Attack': '专长',
    'Cleave': '专长',
    'Dodge': '专长',
    'Mobility': '专长',
    'Skill Focus': '专长',
    'Spell Penetration': '专长',
    'Greater Spell Penetration': '专长',
    'Toughness': '专长',
    'Alertness': '专长',
    'Acrobatic': '专长',
    'Stealthy': '专长',
    'Self-Sufficient': '专长',
    'Persuasive': '专长',
    'Deceitful': '专长',
    'Negotiator': '专长',
    'Magical Aptitude': '专长',
    'Athletic': '专长',
    'Endurance': '专长',
}

# 法术相关关键词（用于保留在法术分类）
SPELL_KEYWORDS = [
    'spell', 'magic', 'cast', 'casting', 'arcane', 'divine',
    'summon', 'conjuration', 'evocation', 'abjuration', 'transmutation',
    'enchantment', 'illusion', 'divination', 'necromancy', 'universal',
    'metamagic', 'counterspell', 'dispel', 'resist', 'ward',
    'charm', 'curse', 'bless', 'prayer', 'miracle', 'wish',
    'fireball', 'lightning', 'frost', 'acid', 'sonic',
    'heal', 'harm', 'cure', 'inflict', 'restoration',
    'invisibility', 'fly', 'haste', 'slow', 'polymorph',
    'teleport', 'dimension', 'plane', 'ethereal', 'astral',
    'scrying', 'detect', 'identify', 'analyze',
    'shield', 'armor', 'protection', 'mage', 'sorcerer', 'wizard',
    'cleric', 'druid', 'bard', 'witch', 'oracle', 'summoner',
    'bloodline', 'patron', 'familiar', 'bond', 'school',
]

# 专长相关关键词
FEAT_KEYWORDS = [
    'feat', 'improved', 'greater', 'weapon focus', 'weapon specialization',
    'dodge', 'mobility', 'spring attack', 'whirlwind', 'cleave',
    'power attack', 'combat', 'expertise', 'toughness', 'endurance',
    'alertness', 'athletic', 'acrobatic', 'stealthy', 'negotiator',
    'persuasive', 'deceitful', 'magical aptitude', 'self-sufficient',
    'skill focus', 'spell penetration', 'greater spell penetration',
]

# 技能关键词
SKILL_KEYWORDS = [
    'acrobatics', 'appraise', 'bluff', 'climb', 'craft', 'diplomacy',
    'disable device', 'disguise', 'escape artist', 'fly', 'handle animal',
    'heal', 'intimidate', 'knowledge', 'linguistics', 'perception',
    'perform', 'profession', 'ride', 'sense motive', 'sleight of hand',
    'spellcraft', 'stealth', 'survival', 'swim', 'use magic device',
    'concentration', 'decipher script', 'forgery', 'gather information',
    'hide', 'move silently', 'open lock', 'search', 'spot', 'listen',
    'tumble', 'balance', 'jump', 'use rope', 'speak language',
]

# 装备/物品关键词
EQUIPMENT_KEYWORDS = [
    'armor', 'shield', 'weapon', 'sword', 'bow', 'arrow', 'dagger',
    'staff', 'wand', 'rod', 'ring', 'amulet', 'cloak', 'boots',
    'belt', 'bracers', 'gauntlet', 'helm', 'potion', 'scroll',
    'elixir', 'oil', 'poison', 'antitoxin', 'tanglefoot',
    'backpack', 'bedroll', 'rope', 'lantern', 'torch',
    'mace', 'spear', 'crossbow', 'knife', 'club', 'quarterstaff',
]

# 状态/条件关键词
CONDITION_KEYWORDS = [
    'blinded', 'confused', 'cowered', 'dazed', 'dazzled', 'deafened',
    'disabled', 'dying', 'energy drained', 'entangled', 'exhausted',
    'fascinated', 'fatigued', 'frightened', 'grappled', 'helpless',
    'incorporeal', 'invisible', 'nauseated', 'panicked', 'paralyzed',
    'petrified', 'pinned', 'prone', 'shaken', 'sickened', 'staggered',
    'stunned', 'unconscious', 'bleed', 'burning', 'flat-footed',
    'blindness', 'deafness', 'disease', 'poison', 'curse',
]

# 动作/战技关键词
COMBAT_KEYWORDS = [
    'attack', 'defense', 'dodge', 'parry', 'riposte', 'feint',
    'charge', 'run', 'withdraw', 'move', 'grapple', 'trip',
    'disarm', 'sunder', 'bull rush', 'overrun', 'trample',
    'drag', 'reposition', 'steal', 'dirty trick', 'aid another',
    'total defense', 'fight defensively', 'cast defensively',
    'full attack', 'attack of opportunity', 'combat maneuver',
    'initiative', 'surprise round', 'flanking', 'cover', 'concealment',
    'reach', 'threatened', 'critical', 'confirm', 'fumble',
]

# 怪物/生物关键词
CREATURE_KEYWORDS = [
    'dragon', 'goblin', 'orc', 'elf', 'dwarf', 'halfling', 'gnome',
    'human', 'half-elf', 'half-orc', 'tiefling', 'aasimar',
    'undead', 'skeleton', 'zombie', 'ghost', 'vampire', 'lich',
    'demon', 'devil', 'angel', 'celestial', 'fiend', 'elemental',
    'fey', 'giant', 'troll', 'ogre', 'wolf', 'bear', 'lion',
    'snake', 'spider', 'rat', 'bat', 'raven', 'eagle', 'hawk',
    'familiar', 'animal companion', 'mount', 'pet', 'vermin',
    'ooze', 'plant', 'construct', 'outsider', 'aberration',
]

# 组织/势力关键词
FACTION_KEYWORDS = [
    'society', 'guild', 'order', 'church', 'temple', 'cult', 'sect',
    'faction', 'organization', 'brotherhood', 'sisterhood', 'league',
    'alliance', 'coalition', 'council', 'court', 'syndicate',
    'pathfinder society', 'hellknight', 'red mantis', 'aspis consortium',
    'sczarni', 'prophets of kalistrade',
]


def clean_translation(text, english_term):
    """清洗推荐翻译：去掉描述前缀和括号数字，提取纯译名"""
    if not text or text.strip() == "":
        return ""
    
    text = text.strip()
    
    # 去掉末尾的括号数字引用，如 "奥术联结(3)" -> "奥术联结"
    text = re.sub(r'\(\d+\)$', '', text).strip()
    
    # 如果文本很短（<=8字）且不以描述词开头，直接返回
    bad_starts = ["该", "就", "和", "或", "不", "此", "这", "如", "类", "每", "任", "即", "一", "级", "你", "他", "她", "它", "能", "可", "会", "将", "使", "让", "被", "受", "遭", "经", "由", "从", "向", "往", "到", "在", "于", "对", "为", "与", "及", "同", "跟", "比", "较", "更", "最", "很", "非", "无", "没", "未", "别", "勿", "莫", "毋"]
    if len(text) <= 8 and not any(text.startswith(p) for p in bad_starts):
        return text
    
    # 去掉描述前缀（循环处理，因为可能有多个前缀嵌套）
    cleaned = text
    max_iterations = 5
    for _ in range(max_iterations):
        original = cleaned
        for prefix in DESCRIPTION_PREFIXES:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        if cleaned == original:
            break
    
    # 再去掉一次括号数字
    cleaned = re.sub(r'\(\d+\)$', '', cleaned).strip()
    
    # 再去掉一次可能残留的描述前缀
    for prefix in DESCRIPTION_PREFIXES:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    
    # 如果清洗后为空或还是太长（>15字），标记为需复核
    if not cleaned or len(cleaned) > 15:
        return f"[需复核] {text[:50]}"
    
    # 如果清洗后仍包含明显的句子结构，标记为需复核
    if any(cleaned.startswith(p) for p in bad_starts):
        return f"[需复核] {text[:50]}"
    
    return cleaned


def parse_markdown_table(content):
    """解析 markdown 表格，返回 (分类名, [术语列表]) 的列表"""
    sections = []
    current_section = None
    current_terms = []
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        
        # 检测分类标题
        if line.startswith('## '):
            if current_section and current_terms:
                sections.append((current_section, current_terms))
            current_section = line[3:].strip()
            current_terms = []
        
        # 检测表格数据行
        elif line.startswith('|') and current_section:
            parts = [p.strip() for p in line.split('|')]
            parts = [p for p in parts if p]
            
            # 跳过表头行和分隔行
            if len(parts) >= 4 and parts[0] != '英文术语' and '---' not in parts[0]:
                current_terms.append({
                    'english': parts[0],
                    'recommended': parts[1] if len(parts) > 1 else "",
                    'others': parts[2] if len(parts) > 2 else "",
                    'count': parts[3] if len(parts) > 3 else "0"
                })
    
    if current_section and current_terms:
        sections.append((current_section, current_terms))
    
    return sections


def classify_term(term):
    """基于英文术语名判断分类"""
    en = term['english'].lower()
    
    # 检查各个分类关键词
    if any(kw in en for kw in SKILL_KEYWORDS):
        return '技能'
    if any(kw in en for kw in EQUIPMENT_KEYWORDS):
        return '装备/物品'
    if any(kw in en for kw in CREATURE_KEYWORDS):
        return '怪物/生物'
    if any(kw in en for kw in COMBAT_KEYWORDS):
        return '动作/战技'
    if any(kw in en for kw in CONDITION_KEYWORDS):
        return '状态/条件'
    if any(kw in en for kw in FACTION_KEYWORDS):
        return '组织/势力'
    if any(kw in en for kw in FEAT_KEYWORDS):
        return '专长'
    
    # 法术相关（但已经在法术分类中的不应该到这里）
    if any(kw in en for kw in SPELL_KEYWORDS):
        return '法术'
    
    return None


def main():
    print("开始读取原始文件...")
    content = INPUT_FILE.read_text(encoding='utf-8')
    
    print("解析表格数据...")
    sections = parse_markdown_table(content)
    print(f"解析到 {len(sections)} 个分类")
    
    # 记录日志
    log_entries = []
    log_entries.append("# 优化日志\n")
    log_entries.append(f"原始文件: {INPUT_FILE}\n")
    log_entries.append(f"处理时间: 2024-06-17\n")
    log_entries.append(f"原始分类数: {len(sections)}\n\n")
    
    total_terms = sum(len(terms) for _, terms in sections)
    log_entries.append(f"原始总术语数: {total_terms}\n")
    for section_name, terms in sections:
        log_entries.append(f"  - {section_name}: {len(terms)} 个术语\n")
    log_entries.append("\n")
    
    # 阶段 1.1: 清洗推荐翻译
    print("阶段 1.1: 清洗推荐翻译...")
    cleaned_sections = []
    borderline_cases = []
    
    for section_name, terms in sections:
        cleaned_terms = []
        for term in terms:
            original_rec = term['recommended']
            cleaned_rec = clean_translation(original_rec, term['english'])
            
            if cleaned_rec.startswith('[需复核]'):
                # 尝试从"其他翻译"中提取候选
                if term['others']:
                    # 先去掉所有括号数字
                    others_clean = re.sub(r'\(\d+\)', '', term['others'])
                    # 按逗号、顿号分割
                    candidates = [c.strip() for c in re.split(r'[,，、]', others_clean)]
                    
                    # 进一步清洗每个候选：去掉描述前缀
                    bad_starts = ["该", "就", "和", "或", "此", "这", "如", "类", "每", "任", "即", "一", "级", "你", "他", "她", "它", "能", "可", "会", "将", "使", "让", "被", "受", "遭", "经", "由", "从", "向", "往", "到", "在", "于", "对", "为", "与", "及", "同", "跟", "比", "较", "更", "最", "很", "非", "无", "没", "未", "别", "勿", "莫", "毋"]
                    
                    valid_candidates = []
                    for c in candidates:
                        c = c.strip()
                        # 去掉描述前缀
                        for prefix in DESCRIPTION_PREFIXES:
                            if c.startswith(prefix):
                                c = c[len(prefix):].strip()
                        # 再去掉括号数字
                        c = re.sub(r'\(\d+\)$', '', c).strip()
                        # 检查是否有效
                        if len(c) <= 10 and len(c) >= 2 and not any(c.startswith(p) for p in bad_starts):
                            valid_candidates.append(c)
                    
                    if valid_candidates:
                        # 优先找和英文术语直接对应的（最短且包含关键字的）
                        # 例如 Dimension Door -> 找包含"门"或"传送"的
                        cleaned_rec = min(valid_candidates, key=len)
                        log_entries.append(f"[自动修复] {term['english']}: '{original_rec}' -> '{cleaned_rec}' (从其他翻译提取)\n")
                    else:
                        borderline_cases.append({
                            'english': term['english'],
                            'original': original_rec,
                            'section': section_name,
                            'others': term['others']
                        })
                        cleaned_rec = "[需人工复核]"
                        log_entries.append(f"[需复核] {term['english']}: 推荐翻译='{original_rec}', 其他翻译='{term['others']}'\n")
                else:
                    borderline_cases.append({
                        'english': term['english'],
                        'original': original_rec,
                        'section': section_name,
                        'others': term['others']
                    })
                    cleaned_rec = "[需人工复核]"
                    log_entries.append(f"[需复核] {term['english']}: 推荐翻译='{original_rec}', 无其他翻译\n")
            elif original_rec != cleaned_rec:
                log_entries.append(f"[清洗] {term['english']}: '{original_rec}' -> '{cleaned_rec}'\n")
            
            term['recommended'] = cleaned_rec
            cleaned_terms.append(term)
        
        cleaned_sections.append((section_name, cleaned_terms))
    
    print(f"清洗完成，发现 {len(borderline_cases)} 个边界案例")
    
    # 阶段 1.2 & 1.3: 重新分类
    print("阶段 1.2 & 1.3: 重新分类...")
    
    category_mapping = {
        '法术': '法术',
        '专长': '专长',
        '职业能力': '职业能力',
        '状态': '状态/条件',
        '物品': '装备/物品',
        '制造': '专长',
        '位面': '位面',
        '神祇': '神祇',
        '种族': '种族',
        '地域': '地域',
        '规则概念': '规则概念',
    }
    
    new_categories = {
        '法术': [], '专长': [], '职业能力': [],
        '状态/条件': [], '装备/物品': [], '技能': [],
        '怪物/生物': [], '动作/战技': [], '位面': [],
        '神祇': [], '种族': [], '地域': [],
        '组织/势力': [], '规则概念': [], '其他': [],
    }
    
    for section_name, terms in cleaned_sections:
        for term in terms:
            en = term['english']
            
            # 先检查错位修正
            if en in MISPLACEMENT_FIXES:
                target = MISPLACEMENT_FIXES[en]
                log_entries.append(f"[错位修正] {en}: '{section_name}' -> '{target}'\n")
                new_categories[target].append(term)
                continue
            
            # 尝试自动分类（针对"其他"分类中的术语）
            if section_name == '其他（780 个术语）' or section_name == '其他':
                auto_category = classify_term(term)
                if auto_category and auto_category in new_categories:
                    log_entries.append(f"[自动分类] {en}: '其他' -> '{auto_category}'\n")
                    new_categories[auto_category].append(term)
                    continue
            
            # 标准映射
            base_name = section_name.split('（')[0].strip()
            if base_name in category_mapping:
                target = category_mapping[base_name]
                new_categories[target].append(term)
            else:
                auto_category = classify_term(term)
                if auto_category and auto_category in new_categories:
                    new_categories[auto_category].append(term)
                else:
                    new_categories['其他'].append(term)
    
    # 生成输出
    print("生成输出文件...")
    
    # 生成清洗版
    clean_output = ["# PathFinder 1e 中英术语对照表（清洗版）\n\n"]
    clean_output.append("_推荐翻译字段已清洗，去掉了描述性前缀_\n\n")
    
    for section_name, terms in cleaned_sections:
        if terms:
            base_name = section_name.split('（')[0].strip()
            clean_output.append(f"## {base_name}（{len(terms)} 个术语）\n\n")
            clean_output.append("| 英文术语 | 推荐翻译 | 其他翻译 | 出现次数 |\n")
            clean_output.append("|---------|---------|---------|---------|\n")
            for term in terms:
                clean_output.append(f"| {term['english']} | {term['recommended']} | {term['others']} | {term['count']} |\n")
            clean_output.append("\n")
    
    OUTPUT_CLEAN.write_text(''.join(clean_output), encoding='utf-8')
    print(f"已生成: {OUTPUT_CLEAN}")
    
    # 生成重分类版
    recat_output = ["# PathFinder 1e 中英术语对照表（重分类版）\n\n"]
    recat_output.append("_按 PF 规则概念重新分类，新增技能/装备/怪物/动作/状态/组织等分类_\n\n")
    
    for category, terms in new_categories.items():
        if terms:
            recat_output.append(f"## {category}（{len(terms)} 个术语）\n\n")
            recat_output.append("| 英文术语 | 推荐翻译 | 其他翻译 | 出现次数 |\n")
            recat_output.append("|---------|---------|---------|---------|\n")
            sorted_terms = sorted(terms, key=lambda x: int(x['count']) if x['count'].isdigit() else 0, reverse=True)
            for term in sorted_terms:
                recat_output.append(f"| {term['english']} | {term['recommended']} | {term['others']} | {term['count']} |\n")
            recat_output.append("\n")
    
    OUTPUT_RECAT.write_text(''.join(recat_output), encoding='utf-8')
    print(f"已生成: {OUTPUT_RECAT}")
    
    # 生成边界案例文件
    borderline_output = ["# 边界案例待复核\n\n"]
    borderline_output.append("以下术语的推荐翻译无法自动确定，需要人工复核：\n\n")
    borderline_output.append("| 英文术语 | 当前推荐翻译 | 其他翻译 | 原分类 | 建议操作 |\n")
    borderline_output.append("|---------|------------|---------|--------|---------|\n")
    
    for case in borderline_cases:
        others_short = case['others'][:50] + '...' if len(case['others']) > 50 else case['others']
        borderline_output.append(f"| {case['english']} | {case['original']} | {others_short} | {case['section']} | 人工确认译名 |\n")
    
    OUTPUT_BORDERLINE.write_text(''.join(borderline_output), encoding='utf-8')
    print(f"已生成: {OUTPUT_BORDERLINE}")
    
    # 生成日志
    log_entries.append("\n## 重新分类统计\n\n")
    for category, terms in new_categories.items():
        if terms:
            log_entries.append(f"- {category}: {len(terms)} 个术语\n")
    
    other_count = len(new_categories['其他'])
    total_recat = sum(len(terms) for terms in new_categories.values())
    log_entries.append(f"\n其他分类占比: {other_count}/{total_recat} = {other_count/total_recat*100:.1f}%\n")
    
    OUTPUT_LOG.write_text(''.join(log_entries), encoding='utf-8')
    print(f"已生成: {OUTPUT_LOG}")
    
    print("\nPhase 1 完成！")
    print(f"  - 清洗版: {OUTPUT_CLEAN}")
    print(f"  - 重分类版: {OUTPUT_RECAT}")
    print(f"  - 边界案例: {OUTPUT_BORDERLINE} ({len(borderline_cases)} 个)")
    print(f"  - 日志: {OUTPUT_LOG}")


if __name__ == '__main__':
    main()
