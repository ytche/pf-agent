#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对术语提取报告进行分类
"""

import re
from collections import defaultdict

input_file = '/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/术语提取报告_v3.md'
output_file = '/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/术语提取报告_分类版.md'

# 分类规则（基于术语名称和翻译）
CATEGORIES = {
    '法术': {
        'patterns': [
            r'术$', r'法术$', r'法球$', r'护盾$', r'结界$', r'祝福$', r'诅咒$',
            r'光辉$', r'黑暗$', r'幻象$', r'传送$', r'召唤$', r'控制$',
            r'治疗$', r'伤害$', r'防护$', r'侦测$', r'解除$', r'变形$',
            r'隐形$', r'加速$', r'减速$', r'定身$', r'魅惑$', r'恐惧$',
            r'燃烧$', r'冰冻$', r'闪电$', r'酸液$', r'音波$',
        ],
        'keywords': ['法术', '咒语', '魔法', '施法', '环级', '豁免', 'DC'],
        'examples': ['Charm Person', 'Dispel Magic', 'Fire Shield', 'True Seeing']
    },
    '专长': {
        'patterns': [
            r'专长$', r'打击$', r'攻击$', r'反射$', r'意志$', r'强韧$',
            r'闪避$', r'格挡$', r'招架$', r'冲锋$', r'射击$', r'投掷$',
            r'攀爬$', r'游泳$', r'跳跃$', r'平衡$', r'潜行$', r'侦查$',
        ],
        'keywords': ['专长', '先决条件', '效果', '战斗', '技能'],
        'examples': ['Power Attack', 'Weapon Finesse', 'Combat Reflexes', 'Improved Unarmed Strike']
    },
    '职业能力': {
        'patterns': [
            r'能力$', r'技能$', r'训练$', r'感知$', r'表演$', r'学识$',
            r'联结$', r'契约$', r'领域$', r'学派$', r'血脉$', r'诅咒$',
            r'祝福$', r'神恩$', r'祈祷$', r'冥想$', r'狂暴$', r' rage$',
        ],
        'keywords': ['职业', '等级', '每日', '轮数', '分钟', '职业能力'],
        'examples': ['Bardic Performance', 'Rage', 'Sneak Attack', 'Trap Sense']
    },
    '状态': {
        'patterns': [
            r'状态$', r'效果$', r'豁免$', r'加值$', r'减值$', r'惩罚$',
            r'恍惚$', r'战栗$', r'恶心$', r'疲乏$', r'力竭$', r'震慑$',
            r'目盲$', r'耳聋$', r'沉默$', r'定身$', r'昏迷$', r'死亡$',
            r'混乱$', r'秩序$', r'善良$', r'邪恶$', r'中立$',
        ],
        'keywords': ['状态', '豁免', '持续', '轮', '分钟', '小时'],
        'examples': ['Shaken', 'Sickened', 'Staggered', 'Fatigued']
    },
    '物品': {
        'patterns': [
            r'物品$', r'装备$', r'武器$', r'防具$', r'护甲$', r'盾牌$',
            r'药水$', r'卷轴$', r'魔杖$', r'法杖$', r'戒指$', r'项链$',
            r'斗篷$', r'靴子$', r'手套$', r'头盔$', r'腰带$', r'护腕$',
        ],
        'keywords': ['物品', '价格', '重量', '灵光', '施法者等级', '制造'],
        'examples': ['Craft Wondrous Item', 'Forge Ring', 'Craft Magic Arms']
    },
    '制造': {
        'patterns': [
            r'制造$', r'锻造$', r'抄写$', r'调配$', r'雕刻$', r'编织$',
            r'铸造$', r'打造$', r'制作$', r'合成$', r'炼金$', r'附魔$',
        ],
        'keywords': ['制造', '工艺', '材料', '成本', '时间', '技能检定'],
        'examples': ['Craft Wondrous Item', 'Craft Construct', 'Scribe Scroll']
    },
    '位面': {
        'patterns': [
            r'位面$', r'界$', r'维度$', r'空间$', r'世界$', r'领域$',
            r'天堂$', r'地狱$', r'深渊$', r'灵界$', r'阴影$', r'星界$',
        ],
        'keywords': ['位面', '异界', '传送', '旅行', '界域'],
        'examples': ['Ethereal Plane', 'Plane Shift', 'Planar Ally', 'Planar Binding']
    },
    '神祇': {
        'patterns': [
            r'神$', r'神祇$', r'神恩$', r'祝福$', r'诅咒$', r'信仰$',
            r'牧师$', r'圣武士$', r'德鲁伊$', r'先知$', r'审判者$',
        ],
        'keywords': ['神祇', '信仰', '领域', '祝福', '诅咒', '神圣'],
        'examples': ['Cayden Cailean', 'Divine Gift', 'EVANGELIST BOONS']
    },
    '种族': {
        'patterns': [
            r'种族$', r'裔$', r'人$', r'精灵$', r'矮人$', r'侏儒$',
            r'半精灵$', r'半兽人$', r'半身人$', r'龙$', r'巨人$', r'恶魔$',
        ],
        'keywords': ['种族', '特性', '替换', '亚种', '天赋'],
        'examples': ['Inner Sea Races', 'Advanced Race Guide']
    },
    '地域': {
        'patterns': [
            r'地域$', r'地区$', r'国家$', r'城市$', r'王国$', r'帝国$',
            r'荒野$', r'森林$', r'山脉$', r'海洋$', r'沙漠$', r'沼泽$',
        ],
        'keywords': ['地域', '地区', '国家', '城市', '文化'],
        'examples': ['Mwangi Expanse', 'Inner Sea', 'Ultimate Wilderness']
    },
    '规则概念': {
        'patterns': [
            r'规则$', r'概念$', r'机制$', r'系统$', r'核心$', r'基础$',
            r'动作$', r'移动$', r'攻击$', r'防御$', r'豁免$', r'检定$',
        ],
        'keywords': ['规则', '核心', '基础', '动作', '移动', '攻击'],
        'examples': ['Class Skills', 'Hit Die', 'Class Features', 'Skill Mastery']
    },
    '其他': {
        'patterns': [],
        'keywords': [],
        'examples': []
    }
}

def classify_term(term, translation, other_trans):
    """根据术语名称和翻译进行分类"""
    
    # 合并所有文本用于分析
    all_text = f"{term} {translation} {other_trans}"
    
    # 检查每个分类
    scores = defaultdict(int)
    
    for category, rules in CATEGORIES.items():
        if category == '其他':
            continue
            
        # 检查模式匹配
        for pattern in rules['patterns']:
            if re.search(pattern, translation):
                scores[category] += 3
        
        # 检查关键词
        for keyword in rules['keywords']:
            if keyword in all_text:
                scores[category] += 2
        
        # 检查示例
        for example in rules['examples']:
            if example.lower() in term.lower():
                scores[category] += 5
    
    # 特殊规则
    if 'Craft' in term and 'Item' in term:
        scores['制造'] += 10
    
    if 'Spell' in term or any(s in translation for s in ['术', '法术', '咒语']):
        scores['法术'] += 5
    
    if 'Feats' in term or 'Feat' in term or '专长' in translation:
        scores['专长'] += 5
    
    if 'Boons' in term or '神恩' in translation:
        scores['神祇'] += 5
    
    if 'Plane' in term or '位面' in translation:
        scores['位面'] += 5
    
    # 返回最高分的分类
    if scores:
        best_category = max(scores, key=scores.get)
        if scores[best_category] >= 3:
            return best_category
    
    return '其他'

def main():
    """主函数"""
    
    # 读取报告
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    
    # 分类存储
    categorized = defaultdict(list)
    
    # 解析表格
    for line in lines:
        if line.startswith('| ') and not line.startswith('| ---') and not line.startswith('| 英文术语'):
            parts = line.split('|')
            if len(parts) >= 5:
                term = parts[1].strip()
                recommended = parts[2].strip()
                other_trans = parts[3].strip()
                count = parts[4].strip()
                
                if term and term != '英文术语':
                    category = classify_term(term, recommended, other_trans)
                    categorized[category].append({
                        'term': term,
                        'recommended': recommended,
                        'other': other_trans,
                        'count': count
                    })
    
    # 生成分类报告
    output_lines = []
    output_lines.append("# PathFinder 1e 中英术语对照表（分类版）\n")
    output_lines.append("_提取自 pf_rules_md 目录下的所有 Markdown 文件_\n")
    output_lines.append("_按 PF 规则概念分类_\n\n")
    
    # 按分类顺序输出
    category_order = [
        '法术', '专长', '职业能力', '状态', '物品', '制造',
        '位面', '神祇', '种族', '地域', '规则概念', '其他'
    ]
    
    for category in category_order:
        terms = categorized.get(category, [])
        if not terms:
            continue
        
        # 按出现次数排序
        sorted_terms = sorted(terms, key=lambda x: int(x['count']) if x['count'].isdigit() else 0, reverse=True)
        
        output_lines.append(f"## {category}（{len(sorted_terms)} 个术语）\n")
        output_lines.append("| 英文术语 | 推荐翻译 | 其他翻译 | 出现次数 |")
        output_lines.append("|---------|---------|---------|---------|")
        
        for term_info in sorted_terms:
            output_lines.append(f"| {term_info['term']} | {term_info['recommended']} | {term_info['other']} | {term_info['count']} |")
        
        output_lines.append("")
    
    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))
    
    print(f"分类完成！")
    print(f"输出文件：{output_file}")
    print(f"\n分类统计：")
    for category in category_order:
        count = len(categorized.get(category, []))
        if count > 0:
            print(f"  {category}：{count} 个术语")

if __name__ == '__main__':
    main()
