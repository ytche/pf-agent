#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取 PF 规则文档中的中英术语对照表
优化版本：减少处理时间
"""

import os
import re
from collections import defaultdict

# 规则书缩写列表（排除）
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
    'Q&C', 'WMH', 'AHH', 'CH', 'USH', 'MAH', 'AHH', 'DEG', 'WO', 'CoL', 'SF',
    'PF2', 'PU', 'PFS'
}

base_dir = '/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/pf_rules_md'
output_file = '/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/术语提取报告_v3.md'

def extract_terms_with_translations():
    """提取术语及其中文翻译"""
    # 结构：{英文术语: {中文翻译: 出现次数}}
    term_translations = defaultdict(lambda: defaultdict(int))
    
    # 只处理前100个文件（测试用）
    file_count = 0
    max_files = 100
    
    for root, dirs, files in os.walk(base_dir):
        for filename in files:
            if not filename.endswith('.md'):
                continue
            
            file_count += 1
            if file_count > max_files:
                break
            
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 先把换行替换为空格
                content = content.replace('\n', ' ').replace('\r', '')
                content = ' '.join(content.split())
                
                # 模式1：英文术语（中文翻译）
                pattern1 = r'([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)+)\s*[\uff08(]([^\uff09)]+)[\uff09)]'
                matches1 = re.findall(pattern1, content)
                for eng, chn in matches1:
                    eng = eng.strip()
                    chn = chn.strip()
                    if len(eng) < 3 or len(chn) < 2:
                        continue
                    if eng in RULEBOOK_ABBREVIATIONS:
                        continue
                    if re.match(r'^[\u4e00-\u9fff]+$', eng):
                        continue
                    term_translations[eng][chn] += 1
                
                # 模式2：中文翻译（英文术语）
                pattern2 = r'([\u4e00-\u9fff]+(?:\s*[\u4e00-\u9fff]+)*)\s*[\uff08(]([A-Za-z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)+)[\uff09)]'
                matches2 = re.findall(pattern2, content)
                for chn, eng in matches2:
                    eng = eng.strip()
                    chn = chn.strip()
                    if len(eng) < 3 or len(chn) < 2:
                        continue
                    if eng in RULEBOOK_ABBREVIATIONS:
                        continue
                    term_translations[eng][chn] += 1
                
            except Exception as e:
                print(f"Error reading {filepath}: {e}")
        
        if file_count > max_files:
            break
    
    return term_translations

def generate_report(term_translations):
    """生成报告"""
    # 过滤出现次数 >= 2 的术语（测试用，降低阈值）
    filtered_terms = {term: trans for term, trans in term_translations.items() 
                      if sum(trans.values()) >= 2}
    
    # 按总出现次数排序
    sorted_terms = sorted(filtered_terms.items(), 
                         key=lambda x: sum(x[1].values()), 
                         reverse=True)
    
    # 生成报告
    lines = []
    lines.append("# PathFinder 1e 中英术语对照表\n")
    lines.append("_提取自 pf_rules_md 目录下的所有 Markdown 文件_\n")
    lines.append("_提取方法：英文术语（中文翻译）模式_\n\n")
    
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
    
    for term, translations in sorted_terms:
        term_safe = term.replace('\n', ' ').replace('\r', '')
        
        sorted_trans = sorted(translations.items(), key=lambda x: x[1], reverse=True)
        
        recommended = sorted_trans[0][0] if sorted_trans else ""
        
        other_trans = [f"{t}({c})" for t, c in sorted_trans[1:5]]
        other_str = ", ".join(other_trans) if other_trans else ""
        
        total_count = sum(translations.values())
        
        lines.append(f"| {term_safe} | {recommended} | {other_str} | {total_count} |")
    
    lines.append(f"\n_总计：{len(sorted_terms)} 个术语_\n")
    
    return '\n'.join(lines)

if __name__ == '__main__':
    print("开始提取术语及翻译...")
    term_translations = extract_terms_with_translations()
    print(f"提取到 {len(term_translations)} 个术语")
    
    print("生成报告...")
    report = generate_report(term_translations)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"报告已保存到: {output_file}")
    
    total_terms = len(term_translations)
    filtered_terms = len({k:v for k,v in term_translations.items() if sum(v.values()) >= 2})
    print(f"总术语数: {total_terms}")
    print(f"收录术语数 (>=2次): {filtered_terms}")
    
    sorted_terms = sorted(term_translations.items(), 
                         key=lambda x: sum(x[1].values()), 
                         reverse=True)
    print("\n前10个术语：")
    for term, trans in sorted_terms[:10]:
        total = sum(trans.values())
        top_trans = max(trans.items(), key=lambda x: x[1])
        print(f"  {term}: {top_trans[0]} ({top_trans[1]}/{total})")
