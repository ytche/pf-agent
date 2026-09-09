import re

with open('/Users/chezi/.openclaw/workspace/pf_rules_chm/Pathfinder v2.20 SC.hhc', 'rb') as f:
    content = f.read().decode('gbk', errors='ignore')

# 打印所有带层级的OBJECT项，看看实际结构
lines = content.split('\n')
indent_level = 0
in_object = False
object_name = ""
object_local = ""
object_count = 0

print("所有OBJECT项（带层级）：")
print("=" * 80)

for i, line in enumerate(lines):
    line = line.strip()
    
    # 检测层级变化
    if '<UL>' in line:
        indent_level += 1
    if '</UL>' in line:
        indent_level -= 1
    
    # 检测OBJECT开始
    if '<OBJECT type="text/sitemap"' in line:
        in_object = True
        object_name = ""
        object_local = ""
    
    # 检测OBJECT结束
    if '</OBJECT>' in line:
        if in_object:
            object_count += 1
            # 打印所有项，看看层级分布
            prefix = "  " * (indent_level - 1) if indent_level > 0 else ""
            if object_local:
                print(f"{prefix}[L{indent_level}] {object_name} -> {object_local}")
            else:
                print(f"{prefix}[L{indent_level}] [{object_name}]")
        in_object = False
    
    # 在OBJECT中提取Name和Local
    if in_object:
        if 'param name="Name"' in line:
            name_match = re.search(r'value="([^"]*)"', line)
            if name_match:
                object_name = name_match.group(1)
        if 'param name="Local"' in line:
            local_match = re.search(r'value="([^"]*)"', line)
            if local_match:
                object_local = local_match.group(1)

print(f"\n总共找到 {object_count} 个OBJECT项")
