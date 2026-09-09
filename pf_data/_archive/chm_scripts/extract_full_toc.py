#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取 CHM 完整目录结构（所有层级）
按照 CHM_STRUCTURE_ANALYSIS.md 的规则：
- 从根 <UL> 开始计算深度
- <UL> depth+1, </UL> depth-1
- depth == 1 为 L1, depth == 2 为 L2, ...
"""

import re
from pathlib import Path

# 配置
HHC_PATH = Path("/Users/chezi/.openclaw/workspace/pf_rules_chm/Pathfinder v2.20 SC.hhc")
OUTPUT_PATH = Path("/Users/chezi/.openclaw/workspace/touniang/CHM_FULL_TOC.md")

def extract_full_toc():
    """提取完整目录结构，保留层级关系"""
    
    # 读取 .hhc 文件（GBK 编码）
    with open(HHC_PATH, 'r', encoding='gbk', errors='ignore') as f:
        lines = f.readlines()
    
    # 找到根 <UL>（从第15行开始）
    root_ul_line = None
    for i, line in enumerate(lines):
        if '<UL>' in line and root_ul_line is None:
            root_ul_line = i
            break
    
    print(f"根 <UL> 在第 {root_ul_line + 1} 行")
    
    # 从根 UL 开始跟踪深度
    ul_depth = 0  # 根 UL 之前 depth=0
    toc_entries = []  # [(depth, title, page, line_num)]
    
    i = root_ul_line
    while i < len(lines):
        line = lines[i]
        
        # 更新深度
        ul_opens = line.count('<UL>')
        ul_closes = line.count('</UL>')
        
        # 处理当前行的 UL 标签
        if ul_opens > 0:
            ul_depth += ul_opens
        
        # 检查是否是目录项（<LI><OBJECT> 且 depth >= 1）
        if '<LI><OBJECT' in line and ul_depth >= 1:
            # 提取标题和页面
            title_match = re.search(r'Name="([^"]*)"', line)
            page_match = re.search(r'Local="([^"]*)"', line)
            
            title = title_match.group(1) if title_match else "未知"
            page = page_match.group(1) if page_match else ""
            
            # 使用当前 depth（在计算 UL 开启之后）
            # 但注意：目录项的 depth 应该是它所在的 UL 层级
            # 即：如果当前 depth=2，说明它在 L2 的 UL 中，是 L2 项
            entry_depth = ul_depth - 1  # 因为 <UL> 开启了 depth，但 <LI> 在其中
            
            toc_entries.append((entry_depth, title, page, i + 1))
        
        # 处理关闭标签（在检查 <LI> 之后）
        if ul_closes > 0:
            ul_depth -= ul_closes
        
        i += 1
    
    return toc_entries

def build_toc_tree(entries):
    """将扁平列表构建为树结构"""
    
    # 按行号排序（保持原始顺序）
    entries_sorted = sorted(entries, key=lambda x: x[3])
    
    # 构建树
    root = {"title": "Pathfinder 规则", "page": "", "children": [], "depth": 0, "line": 0}
    stack = [root]  # 当前路径上的节点
    
    for depth, title, page, line_num in entries_sorted:
        node = {
            "title": title,
            "page": page,
            "children": [],
            "depth": depth,
            "line": line_num
        }
        
        # 找到正确的父节点
        while len(stack) > 1 and stack[-1]["depth"] >= depth:
            stack.pop()
        
        # 添加到父节点的 children
        stack[-1]["children"].append(node)
        stack.append(node)
    
    return root

def print_tree(node, indent=0, output_lines=None):
    """打印树结构"""
    if output_lines is None:
        output_lines = []
    
    if node["depth"] > 0:  # 跳过根节点
        prefix = "  " * (node["depth"] - 1) + "- "
        page_info = f" [{node['page']}]" if node["page"] else ""
        line = f"{prefix}{node['title']}{page_info}"
        output_lines.append(line)
    
    for child in node["children"]:
        print_tree(child, indent + 1, output_lines)
    
    return output_lines

def count_stats(entries):
    """统计各层级数量"""
    from collections import Counter
    depths = [e[0] for e in entries]
    return Counter(depths)

def main():
    print("=" * 60)
    print("提取 CHM 完整目录结构")
    print("=" * 60)
    
    # 提取目录
    entries = extract_full_toc()
    
    # 统计
    stats = count_stats(entries)
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
    
    # 打印树
    tree_lines = print_tree(tree)
    output_lines.extend(tree_lines)
    
    # 保存
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))
    
    print(f"\n✅ 完整目录已保存到: {OUTPUT_PATH}")
    print(f"   文件大小: {OUTPUT_PATH.stat().st_size} 字节")
    
    # 显示前50行预览
    print("\n" + "=" * 60)
    print("目录预览（前50行）：")
    print("=" * 60)
    for line in tree_lines[:50]:
        print(line)
    if len(tree_lines) > 50:
        print(f"\n... 还有 {len(tree_lines) - 50} 行")

if __name__ == "__main__":
    main()
