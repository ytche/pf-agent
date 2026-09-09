#!/usr/bin/env python3
"""
提取 CHM 目录结构，建立标题 -> 页面文件 的映射
"""
import re
import sys

def extract_hhc_structure(hhc_file):
    """从 .hhc 文件提取目录结构"""
    # 读取并转码
    with open(hhc_file, 'rb') as f:
        content = f.read()
    
    # 尝试 GBK 解码
    try:
        text = content.decode('gbk')
    except:
        text = content.decode('utf-8', errors='ignore')
    
    # 提取所有 <OBJECT> 块中的 Name 和 Local
    objects = re.findall(
        r'<OBJECT[^>]*>\s*'
        r'<param name="Name" value="([^"]*)">\s*'
        r'<param name="Local" value="([^"]*)">',
        text
    )
    
    return objects

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python extract_chm_toc.py <hhc_file>")
        sys.exit(1)
    
    hhc_file = sys.argv[1]
    structure = extract_hhc_structure(hhc_file)
    
    print(f"找到 {len(structure)} 个目录条目\n")
    print("=" * 60)
    
    for name, local in structure:
        if local:
            print(f"{name} -> {local}")
        else:
            print(f"\n【目录】{name}")
            print("-" * 40)
