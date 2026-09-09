#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
去重术语提取报告中的重复术语
合并相同术语的翻译和出现次数
"""

import re
from collections import defaultdict, Counter

input_file = '/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/术语提取报告_v3.md'
output_file = '/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/术语提取报告_v3_dedup.md'

def deduplicate_terms():
    """去重术语，合并翻译和出现次数"""
    
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    
    # 存储术语：{英文术语: {中文翻译: 出现次数}}
    terms = defaultdict(lambda: defaultdict(int))
    
    header_lines = []
    in_table = False
    
    for line in lines:
        # 检查是否是表格数据行
        if line.startswith('| ') and not line.startswith('| ---') and not line.startswith('| 英文术语'):
            in_table = True
            # 解析表格行
            parts = line.split('|')
            if len(parts) >= 5:
                eng_term = parts[1].strip()
                recommended = parts[2].strip()
                other_trans = parts[3].strip()
                count_str = parts[4].strip()
                
                # 提取出现次数
                try:
                    count = int(count_str)
                except:
                    count = 0
                
                # 合并推荐翻译
                if recommended:
                    terms[eng_term][recommended] += count
                
                # 解析其他翻译
                if other_trans:
                    # 格式：翻译(次数), 翻译(次数)
                    trans_items = re.findall(r'([^,(]+)\((\d+)\)', other_trans)
                    for trans, trans_count in trans_items:
                        trans = trans.strip()
                        try:
                            tc = int(trans_count)
                        except:
                            tc = 0
                        if trans:
                            terms[eng_term][trans] += tc
        else:
            if not in_table:
                header_lines.append(line)
    
    # 生成去重后的报告
    output_lines = header_lines.copy()
    
    # 添加表头
    output_lines.append("| 英文术语 | 推荐翻译 | 其他翻译 | 出现次数 |")
    output_lines.append("|---------|---------|---------|---------|")
    
    # 按总出现次数排序
    sorted_terms = sorted(terms.items(), 
                         key=lambda x: sum(x[1].values()), 
                         reverse=True)
    
    for term, translations in sorted_terms:
        # 按出现次数排序翻译
        sorted_trans = sorted(translations.items(), key=lambda x: x[1], reverse=True)
        
        # 推荐翻译（出现次数最多的）
        recommended = sorted_trans[0][0] if sorted_trans else ""
        
        # 其他翻译
        other_trans = [f"{t}({c})" for t, c in sorted_trans[1:6]]  # 最多5个其他翻译
        other_str = ", ".join(other_trans) if other_trans else ""
        
        # 总出现次数
        total_count = sum(translations.values())
        
        output_lines.append(f"| {term} | {recommended} | {other_str} | {total_count} |")
    
    # 添加统计信息
    output_lines.append(f"\n_总计：{len(sorted_terms)} 个术语（去重后）_\n")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))
    
    print(f"去重完成！")
    print(f"原始术语数：{len(terms)}（去重前）")
    print(f"去重后术语数：{len(sorted_terms)}")
    print(f"输出文件：{output_file}")
    
    # 显示前10个术语
    print("\n前10个术语：")
    for term, trans in sorted_terms[:10]:
        total = sum(trans.values())
        top_trans = max(trans.items(), key=lambda x: x[1])
        print(f"  {term}: {top_trans[0]} ({top_trans[1]}/{total})")

if __name__ == '__main__':
    deduplicate_terms()
