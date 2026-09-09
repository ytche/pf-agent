#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理术语提取报告，移除规则书缩写条目
"""

import re

# 规则书缩写列表（来自规则书缩写对应表）
RULEBOOK_ABBREVIATIONS = {
    # 核心规则书
    'CRB', 'APG', 'UM', 'UC', 'ACG', 'ARG', 'OA', 'UI', 'HA', 'MA', 'MC', 'VC',
    # 战役设定
    'ISR', 'DEP', 'TEoG', 'CEoD', 'ASoL', 'STLC', 'LotFW', 'HoG', 'DoG', 'GoG', 
    'OoG', 'KoG', 'PotI', 'KotI', 'AArch', 'FF', 'FoP', 'FoB', 'FoC', 'CoP', 
    'CoB', 'CoC', 'MTT', 'RTT', 'DTT', 'AMH', 'DH', 'MM', 'TG', 'DR', 'BoD', 
    'CTR', 'DD', 'EMH', 'SH', 'PHH', 'HotHC', 'HotS', 'HotW', 'HotD', 'WoW', 
    'CoG', 'PotW', 'PFS', 'SEPG', 'OLoP', 'PA', 'AG', 'BotD', 'UW',
    # 其他常见缩写
    'UE', 'UCa', 'SG', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'PCS', 'ISWG', 
    'ISG', 'ISI', 'LK', 'LoC', 'QGthE', 'NLoFS', 'CotCT', 'SD', 'LoF', 
    'CoT', 'SS', 'KM', 'WotR', 'RoW', 'ShS', 'HR', 'SA', 'II', 'RoA', 
    'WftC', 'RotR', 'AA', 'BoA', 'BoF', 'BotM', 'BotN', 'BotE', 'BotB', 
    'BotC', 'FG', 'F&P', 'PotS', 'PotR', 'Q&C', 'WMH', 'AHH', 'CH', 'USH', 
    'MAH', 'AHH', 'DEG', 'WO', 'CoL', 'SF', 'PF2', 'PU'
}

def clean_terminology_report(input_file, output_file):
    """清理术语提取报告，移除规则书缩写条目"""
    
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    cleaned_lines = []
    removed_count = 0
    removed_terms = []
    
    for line in lines:
        # 检查是否是表格数据行
        if line.startswith('| ') and not line.startswith('| 英文术语'):
            # 提取英文术语（第一列）
            match = re.match(r'\|\s*([^|]+)\s*\|', line)
            if match:
                term = match.group(1).strip()
                # 检查是否是规则书缩写
                if term in RULEBOOK_ABBREVIATIONS:
                    removed_count += 1
                    removed_terms.append(term)
                    continue  # 跳过此行
        
        cleaned_lines.append(line)
    
    # 写入清理后的文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(cleaned_lines))
    
    print(f"清理完成！")
    print(f"移除条目数: {removed_count}")
    print(f"移除的术语: {', '.join(sorted(set(removed_terms)))}")
    print(f"输出文件: {output_file}")

if __name__ == '__main__':
    input_file = '/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/术语提取报告.md'
    output_file = '/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/术语提取报告_已清理.md'
    
    clean_terminology_report(input_file, output_file)
