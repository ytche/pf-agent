import re

with open('/Users/chezi/.openclaw/workspace/pf_rules_chm/Pathfinder v2.20 SC.hhc', 'rb') as f:
    content = f.read().decode('gbk', errors='ignore')

lines = content.split('\n')

# 重新分析：找到所有L1项（包括法术）
print("重新分析所有L1项：")
print("=" * 60)

# 找到根UL块（第一个<UL>）
root_ul_start = 0
for i, line in enumerate(lines):
    if '<UL>' in line:
        root_ul_start = i
        break

# 找到根UL块的结束
root_ul_end = 0
ul_depth = 1
for i in range(root_ul_start + 1, len(lines)):
    if '<UL>' in lines[i]:
        ul_depth += 1
    if '</UL>' in lines[i]:
        ul_depth -= 1
        if ul_depth == 0:
            root_ul_end = i
            break

print(f"根UL块: lines {root_ul_start}-{root_ul_end}")

# 在根UL块内，提取所有直接子OBJECT（L1）
print("\n根UL块下的所有L1项：")
print("-" * 60)

in_object = False
obj_name = ""
obj_local = ""
indent_level = 0

for i in range(root_ul_start, root_ul_end + 1):
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
        if in_object and indent_level == 1:  # 根UL的直接子项
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

# 现在分析法术下的子项
print("\n\n法术下的子项（L2）：")
print("=" * 60)

# 找到法术的OBJECT和对应的UL块
spell_object_start = 0
spell_object_end = 0
spell_ul_start = 0
spell_ul_end = 0

for i in range(root_ul_start, root_ul_end):
    if '<OBJECT type="text/sitemap"' in lines[i] and i+1 < len(lines) and '法术' in lines[i+1]:
        spell_object_start = i
        # 找到对应的</OBJECT>
        for j in range(i, len(lines)):
            if '</OBJECT>' in lines[j]:
                spell_object_end = j
                break
        # 找到对应的<UL>
        for j in range(spell_object_end, len(lines)):
            if '<UL>' in lines[j]:
                spell_ul_start = j
                break
        # 找到对应的</UL>
        ul_depth = 1
        for j in range(spell_ul_start + 1, len(lines)):
            if '<UL>' in lines[j]:
                ul_depth += 1
            if '</UL>' in lines[j]:
                ul_depth -= 1
                if ul_depth == 0:
                    spell_ul_end = j
                    break
        break

print(f"法术OBJECT: lines {spell_object_start}-{spell_object_end}")
print(f"法术UL块: lines {spell_ul_start}-{spell_ul_end}")

# 提取法术下的子项
in_object = False
obj_name = ""
obj_local = ""
indent_level = 0

for i in range(spell_ul_start, spell_ul_end + 1):
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
        if in_object and indent_level == 2:  # 法术UL的直接子项
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
