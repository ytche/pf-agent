import re

with open('/Users/chezi/.openclaw/workspace/pf_rules_chm/Pathfinder v2.20 SC.hhc', 'rb') as f:
    content = f.read().decode('gbk', errors='ignore')

lines = content.split('\n')

# 重新分析：找到核心规则OBJECT的范围
print("重新分析核心规则结构：")
print("=" * 60)

# 找到核心规则OBJECT的开始和结束
crb_object_start = 0
crb_object_end = 0
in_crb_object = False

for i, line in enumerate(lines):
    if '<OBJECT type="text/sitemap"' in line and '核心规则' in lines[i+1]:
        crb_object_start = i
        in_crb_object = True
    
    if in_crb_object and '</OBJECT>' in line:
        crb_object_end = i
        break

print(f"核心规则OBJECT: lines {crb_object_start}-{crb_object_end}")

# 在核心规则OBJECT之后，找到对应的<UL>块
ul_start = 0
ul_end = 0
for i in range(crb_object_end, len(lines)):
    if '<UL>' in lines[i]:
        ul_start = i
        break

# 找到对应的</UL>
ul_depth = 1
for i in range(ul_start + 1, len(lines)):
    if '<UL>' in lines[i]:
        ul_depth += 1
    if '</UL>' in lines[i]:
        ul_depth -= 1
        if ul_depth == 0:
            ul_end = i
            break

print(f"核心规则子项UL块: lines {ul_start}-{ul_end}")

# 在这个UL块内，提取所有直接子OBJECT（L2）
print("\n核心规则下的L2项：")
print("-" * 60)

in_object = False
obj_name = ""
obj_local = ""
indent_level = 0

for i in range(ul_start, ul_end + 1):
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
        if in_object and indent_level == 1:  # 直接子项（在核心规则的UL内，且没有被嵌套）
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
