#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取术语 - 避免换行问题
"""

import os
import re
import collections

pf_rules_md = '/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/pf_rules_md'
output_file = '/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/术语提取报告_v2.md'

# 排除的规则书缩写
RULEBOOK_ABBREVIATIONS = {
    'CRB', 'APG', 'UM', 'UC', 'ACG', 'ARG', 'OA', 'UI', 'HA', 'MA', 'MC', 'VC',
    'ISR', 'DEP', 'TEoG', 'CEoD', 'ASoL', 'STLC', 'LotFW', 'HoG', 'DoG', 'GoG',
    'OoG', 'KoG', 'PotI', 'KotI', 'AArch', 'FF', 'FoP', 'FoB', 'FoC', 'CoP',
    'CoB', 'CoC', 'MTT', 'RTT', 'DTT', 'AMH', 'DH', 'MM', 'TG', 'DR', 'BoD',
    'CTR', 'DD', 'EMH', 'SH', 'PHH', 'HotHC', 'HotS', 'HotW', 'HotD', 'WoW',
    'CoG', 'PotW', 'PFS', 'SEPG', 'OLoP', 'PA', 'AG', 'BotD', 'UW', 'UE', 'UCa',
    'SG', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'PCS', 'ISWG', 'ISG', 'ISI',
    'LK', 'LoC', 'QGthE', 'NLoFS', 'CotCT', 'SD', 'LoF', 'CoT', 'SS', 'KM',
    'WotR', 'RoW', 'ShS', 'HR', 'SA', 'II', 'RoA', 'WftC', 'RotR', 'AA', 'BoA',
    'BoF', 'BotM', 'BotN', 'BotE', 'BotB', 'BotC', 'FG', 'F&P', 'PotS', 'PotR',
    'Q&C', 'WMH', 'AHH', 'CH', 'USH', 'MAH', 'DEG', 'WO', 'CoL', 'SF', 'PF2', 'PU'
}

def extract_terms():
    """提取术语"""
    term_counts = collections.Counter()
    term_translations = collections.defaultdict(list)
    
    for root, dirs, files in os.walk(pf_rules_md):
        for file in files:
            if file.endswith('.md'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        # 先把换行替换为空格，避免术语被换行分割
                        content = content.replace('\n', ' ').replace('\r', '')
                        # 合并多个空格
                        content = ' '.join(content.split())
                        
                        # 提取英文术语（至少2个单词，或包含特殊字符）
                        # 匹配：英文单词 + 可能的空格/连字符 + 更多英文单词
                        # 排除：纯数字、纯中文、规则书缩写
                        
                        # 匹配英文术语（多单词或带连字符）
                        # 例如：Craft Wondrous Item, move action, mind-affecting
                        pattern = r'\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)+|\b[a-z]+(?:-[a-z]+)+)\b'
                    
                    matches = re.findall(pattern, content)
                    for match in matches:
                        term = match.strip()
                        # 过滤
                        if len(term) < 3:
                            continue
                        if term in RULEBOOK_ABBREVIATIONS:
                            continue
                        if term.isdigit():
                            continue
                        if re.match(r'^[\u4e00-\u9fff]+$', term):
                            continue
                        
                        term_counts[term] += 1
                        
                        # 提取翻译（前后文）
                        # 简化：只统计出现次数
                        
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")
    
    return term_counts

def generate_report(term_counts):
    """生成报告"""
    # 过滤出现次数 >= 5 的术语
    filtered_terms = {term: count for term, count in term_counts.items() if count >= 5}
    
    # 按出现次数排序
    sorted_terms = sorted(filtered_terms.items(), key=lambda x: x[1], reverse=True)
    
    # 生成报告
    lines = []
    lines.append("# PathFinder 1e 中英术语对照表\n")
    lines.append("_提取自 pf_rules_md 目录下的所有 Markdown 文件_\n\n")
    
    # 能力类型标注
    lines.append("## 能力类型标注（Ability Types）\n")
    lines.append("| 英文标注 | 全称 | 中文翻译 | 说明 |")
    lines.append("|---------|------|---------|------|")
    lines.append("| Sp | Spell-like ability | 类法术能力 | 能力类型标注 |")
    lines.append("| Su | Supernatural ability | 超自然能力 | 能力类型标注 |")
    lines.append("| Ex | Extraordinary ability | 特异能力 | 能力类型标注 |")
    lines.append("\n")
    
    # 中英术语对照表
    lines.append("## 中英术语对照表\n")
    lines.append("| 英文术语 | 推荐翻译 | 其他翻译 | 出现次数 |")
    lines.append("|---------|---------|---------|---------|")
    
    for term, count in sorted_terms:
        # 确保术语不包含换行
        term_safe = term.replace('\n', ' ').replace('\r', '')
        lines.append(f"| {term_safe} | | | {count} |")
    
    lines.append(f"\n_总计：{len(sorted_terms)} 个术语_\n")
    
    return '\n'.join(lines)

if __name__ == '__main__':
    print("开始提取术语...")
    term_counts = extract_terms()
    print(f"提取到 {len(term_counts)} 个术语")
    
    print("生成报告...")
    report = generate_report(term_counts)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"报告已保存到: {output_file}")
    print(f"总术语数: {len(term_counts)}")
    print(f"收录术语数 (>=5次): {len({k:v for k,v in term_counts.items() if v >= 5})}")
