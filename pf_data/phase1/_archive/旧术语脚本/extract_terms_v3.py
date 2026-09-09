#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取 PF 规则文档中的中英术语对照表
简化版本：从表格和文本中提取翻译
"""

import os
import re
from collections import defaultdict, Counter

base_dir = '/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/pf_rules_md'
output_file = '/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/术语提取报告_v3.md'

def extract_translations():
    """提取术语翻译"""
    # 结构：{英文术语: [中文翻译列表]}
    term_translations = defaultdict(list)
    
    file_count = 0
    
    for root, dirs, files in os.walk(base_dir):
        for filename in files:
            if not filename.endswith('.md'):
                continue
            
            file_count += 1
            if file_count % 100 == 0:
                print(f"处理第 {file_count} 个文件...")
            
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 模式1：中文（English）- 括号模式
                # 例如：制造奇物（Craft Wondrous Item）
                pattern1 = r'([\u4e00-\u9fff][\u4e00-\u9fff]*)\s*[\uff08(]\s*([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)+)\s*[\uff09)]'
                matches1 = re.findall(pattern1, content)
                for chn, eng in matches1:
                    chn = chn.strip()
                    eng = eng.strip()
                    if len(eng) < 3 or len(chn) < 2:
                        continue
                    term_translations[eng].append(chn)
                
                # 模式2：表格中的中文 ENGLISH
                # 例如：| 万溶剂UNIVERSAL SOLVENT |
                pattern2 = r'([\u4e00-\u9fff][\u4e00-\u9fff]*)\s*([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)+)'
                matches2 = re.findall(pattern2, content)
                for chn, eng in matches2:
                    chn = chn.strip()
                    eng = eng.strip()
                    if len(eng) < 3 or len(chn) < 2:
                        continue
                    # 排除纯数字和缩写
                    if eng.isupper() and len(eng) < 5:
                        continue
                    term_translations[eng].append(chn)
                
            except Exception as e:
                print(f"Error reading {filepath}: {e}")
    
    return term_translations

def generate_report(term_translations):
    """生成报告"""
    # 统计每个翻译的出现次数
    term_stats = {}
    for term, translations in term_translations.items():
        trans_counts = Counter(translations)
        term_stats[term] = trans_counts
    
    # 过滤出现次数 >= 5 的术语
    filtered_terms = {term: trans for term, trans in term_stats.items() 
                      if sum(trans.values()) >= 5}
    
    # 按总出现次数排序
    sorted_terms = sorted(filtered_terms.items(), 
                         key=lambda x: sum(x[1].values()), 
                         reverse=True)
    
    # 生成报告
    lines = []
    lines.append("# PathFinder 1e 中英术语对照表\n")
    lines.append("_提取自 pf_rules_md 目录下的所有 Markdown 文件_\n")
    lines.append("_提取方法：中文（English）模式和表格提取_\n\n")
    
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
        sorted_trans = sorted(translations.items(), key=lambda x: x[1], reverse=True)
        
        recommended = sorted_trans[0][0] if sorted_trans else ""
        
        other_trans = [f"{t}({c})" for t, c in sorted_trans[1:5]]
        other_str = ", ".join(other_trans) if other_trans else ""
        
        total_count = sum(translations.values())
        
        lines.append(f"| {term} | {recommended} | {other_str} | {total_count} |")
    
    lines.append(f"\n_总计：{len(sorted_terms)} 个术语_\n")
    
    return '\n'.join(lines)

if __name__ == '__main__':
    print("开始提取术语翻译...")
    term_translations = extract_translations()
    print(f"提取到 {len(term_translations)} 个术语")
    
    print("生成报告...")
    report = generate_report(term_translations)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"报告已保存到: {output_file}")
    
    total_terms = len(term_translations)
    filtered_terms = len({k:v for k,v in term_translations.items() if len(v) >= 5})
    print(f"总术语数: {total_terms}")
    print(f"收录术语数 (>=5次): {filtered_terms}")
    
    sorted_terms = sorted(term_translations.items(), 
                         key=lambda x: len(x[1]), 
                         reverse=True)
    print("\n前10个术语：")
    for term, trans in sorted_terms[:10]:
        top_trans = Counter(trans).most_common(1)[0]
        print(f"  {term}: {top_trans[0]} ({top_trans[1]}/{len(trans)})")
