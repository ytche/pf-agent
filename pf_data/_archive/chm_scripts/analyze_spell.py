import re

with open('/Users/chezi/.openclaw/workspace/pf_rules_chm/Pathfinder v2.20 SC.hhc', 'rb') as f:
    content = f.read().decode('gbk', errors='ignore')

lines = content.split('\n')

# 重新分析：找到"法术"的位置，然后提取其下的子项
print("分析法术目录结构：")
print("=" * 60)

# 先找到所有L1项的位置
l1_items = []
indent_level = 0
in_object = False
object_name = ""
object_local = ""
object_start_line = 0

for i, line in enumerate(lines):
    line = line.strip()
    
    if '<UL>' in line:
        indent_level += 1
    if '</UL>' in line:
        indent_level -= 1
    
    if '<OBJECT type="text/sitemap"' in line:
        in_object = True
        object_name = ""
        object_local = ""
        object_start_line = i
    
    if '</OBJECT>' in line:
        if in_object and indent_level == 1:  # L1项
            l1_items.append((object_name, object_local, object_start_line, i))
        in_object = False
    
    if in_object:
        if 'param name="Name"' in line:
            name_match = re.search(r'value="([^"]*)"', line)
            if name_match:
                object_name = name_match.group(1)
        if 'param name="Local"' in line:
            local_match = re.search(r'value="([^"]*)"', line)
            if local_match:
                object_local = local_match.group(1)

print("所有L1项：")
for name, local, start, end in l1_items:
    print(f"  {name} -> {local} (lines {start}-{end})")

# 找到"法术"的位置
spell_item = None
for item in l1_items:
    if item[0] == "法术":
        spell_item = item
        break

if spell_item:
    print(f"\n法术项位置：lines {spell_item[2]}-{spell_item[3]}")
    
    # 提取法术下的子项（在法术的OBJECT结束之前，且层级为2）
    print("\n法术下的直接子项（L2）：")
    print("-" * 60)
    
    in_spell = False
    indent_level = 0
    in_object = False
    obj_name = ""
    obj_local = ""
    
    for i in range(spell_item[2], spell_item[3]):
        line = lines[i].strip()
        
        if '<UL>' in line:
            indent_level += 1
        if '</UL>' in line:
            indent_level -= 1
        
        if '<OBJECT type="text/sitemap"' in line:
            in_object = True
            obj_name = ""
            obj_local = ""
        
        if '</OBJECT>' in line:
            if in_object and indent_level == 2:  # 法术下的直接子项
                if obj_local:
                    print(f"  {obj_name} -> {obj_local}")
                else:
                    print(f"  [{obj_name}]")
            in_object = False
        
        if in_object:
            if 'param name="Name"' in line:
                name_match = re.search(r'value="([^"]*)"', line)
                if name_match:
                    obj_name = name_match.group(1)
            if 'param name="Local"' in line:
                local_match = re.search(r'value="([^"]*)"', line)
                if local_match:
                    obj_local = local_match.group(1)
