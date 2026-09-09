#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复术语提取报告中的换行问题
"""

input_file = '/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/术语提取报告_v3.md'
output_file = '/Users/chezi/.openclaw/workspace/touniang/pf_data/phase1/术语提取报告_v3_fixed.md'

with open(input_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 替换术语中的换行
content = content.replace('Craft Wondrous \nItem', 'Craft Wondrous Item')
content = content.replace('Craft \nWondrous Item', 'Craft Wondrous Item')
content = content.replace('Class \nSkills', 'Class Skills')
content = content.replace('Hit \nDie', 'Hit Die')
content = content.replace('Craft \nConstruct', 'Craft Construct')
content = content.replace('Class \nFeatures', 'Class Features')
content = content.replace('Cayden \nCailean', 'Cayden Cailean')
content = content.replace('Ethereal \nPlane', 'Ethereal Plane')
content = content.replace('Extend \nSpell', 'Extend Spell')
content = content.replace('Mwangi \nExpanse', 'Mwangi Expanse')
content = content.replace('Charm \nPerson', 'Charm Person')
content = content.replace('EVANGELIST \n  BOONS', 'EVANGELIST BOONS')

with open(output_file, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"修复完成！输出文件: {output_file}")
