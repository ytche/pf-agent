#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取 CHM 完整目录结构（所有层级）
修复：Name 参数在 <param> 标签中，不在 <OBJECT> 行
"""

import re
from pathlib import Path
from collections import Counter

# 配置
HHC_PATH = Path("/Users/chezi/.openclaw/workspace/pf_rules_chm/Pathfinder v2.20 SC.hhc")
OUTPUT_PATH = Path("/Users/chezi/.openclaw/workspace/touniang/CHM_FULL_TOC.md")

def extract_full_toc():
    """提取完整目录结构"""
    
    with open(HHC_PATH, 'r', encoding='gbk', errors='replace') as f:
        lines = f.readlines()
    
    # 找到根 <UL>
    root_ul_line = None
    for i, line in enumerate(lines):
        if '<UL>' in line and root_ul_line is None:
            root_ul_line = i
            break
    
    print(f"根 <UL> 在第 {root_ul_line + 1} 行")
    
    # 跟踪深度
    ul_depth = 0
    toc_entries = []
    
    i = root_ul_line
    while i < len(lines):
        line = lines[i]
        
        # 统计 UL 标签
        ul_opens = line.count('<UL>')
        ul_closes = line.count('</UL>')
        
        # 先处理开启
        if ul_opens > 0:
            ul_depth += ul_opens
        
        # 检查是否是 <OBJECT> 开始行（目录项标记）
        if '<OBJECT type="text/sitemap">' in line and ul_depth >= 1:
            # 查找下一行的 <param name="Name" ...>
            title = "未知"
            page = ""
            
            # 查看接下来的几行
            for j in range(i+1, min(i+5, len(lines))):
                next_line = lines[j]
                
                # 提取 Name
                name_match = re.search(r'<param name="Name" value="([^"]*)"', next_line)
                if name_match:
                    title = name_match.group(1)
                
                # 提取 Local（页面）
                local_match = re.search(r'<param name="Local" value="([^"]*)"', next_line)
                if local_match:
                    page = local_match.group(1)
                
                # 遇到 </OBJECT> 结束
                if '</OBJECT>' in next_line:
                    break
            
            # 目录项深度
            entry_depth = ul_depth - 1
            
            toc_entries.append((entry_depth, title, page, i + 1))
        
        # 处理关闭
        if ul_closes > 0:
            ul_depth -= ul_closes
        
        i += 1
    
    return toc_entries

def build_toc_tree(entries):
    """构建树结构"""
    
    root = {"title": "Pathfinder 规则", "page": "", "children": [], "depth": 0, "line": 0}
    stack = [root]
    
    for depth, title, page, line_num in entries:
        node = {
            "title": title,
            "page": page,
            "children": [],
            "depth": depth,
            "line": line_num
        }
        
        # 找到父节点
        while len(stack) > 1 and stack[-1]["depth"] >= depth:
            stack.pop()
        
        stack[-1]["children"].append(node)
        stack.append(node)
    
    return root

def print_tree(node, output_lines=None):
    """打印树为 Markdown 列表"""
    if output_lines is None:
        output_lines = []
    
    if node["depth"] > 0:
        indent = "  " * (node["depth"] - 1)
        page_info = f" (`{node['page']}`)" if node["page"] else ""
        line = f"{indent}- {node['title']}{page_info}"
        output_lines.append(line)
    
    for child in node["children"]:
        print_tree(child, output_lines)
    
    return output_lines

def main():
    print("=" * 60)
    print("提取 CHM 完整目录结构")
    print("=" * 60)
    
    entries = extract_full_toc()
    
    # 统计
    stats = Counter(e[0] for e in entries)
    print(f"\n各层级统计：")
    for depth in sorted(stats.keys()):
        print(f"  L{depth}: {stats[depth]} 项")
    print(f"  总计: {len(entries)} 项")
    
    # 构建树
    tree = build_toc_tree(entries)
    
    # 生成 Markdown
    output_lines = []
    output_lines.append("# Pathfinder 完整目录结构")
    output_lines.append("")
    output_lines.append("## 统计信息")
    output_lines.append("")
    output_lines.append("| 层级 | 数量 |")
    output_lines.append("|------|------|")
    for depth in sorted(stats.keys()):
        output_lines.append(f"| L{depth} | {stats[depth]} |")
    output_lines.append(f"| **总计** | **{len(entries)}** |")
    output_lines.append("")
    output_lines.append("## 完整目录")
    output_lines.append("")
    
    tree_lines = print_tree(tree)
    output_lines.extend(tree_lines)
    
    # 保存
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))
    
    print(f"\n✅ 完整目录已保存到: {OUTPUT_PATH}")
    print(f"   文件大小: {OUTPUT_PATH.stat().st_size:,} 字节")
    
    # 显示前30行预览
    print("\n" + "=" * 60)
    print("目录预览（前30行）：")
    print("=" * 60)
    for line in tree_lines[:30]:
        print(line)
    if len(tree_lines) > 30:
        print(f"\n... 还有 {len(tree_lines) - 30} 行")

if __name__ == "__main__":
    main()
