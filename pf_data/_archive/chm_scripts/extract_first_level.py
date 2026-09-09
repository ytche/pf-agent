import re

with open('/Users/chezi/.openclaw/workspace/pf_rules_chm/Pathfinder v2.20 SC.hhc', 'rb') as f:
    content = f.read().decode('gbk', errors='ignore')

# 按行分析，追踪UL/LI标签来确定层级
lines = content.split('\n')
indent_level = 0
in_object = False
object_name = ""
object_local = ""
results = []

for i, line in enumerate(lines):
    line = line.strip()
    
    # 检测层级变化
    if '<UL>' in line:
        indent_level += 1
    if '</UL>' in line:
        indent_level -= 1
    
    # 检测OBJECT开始
    if '<OBJECT type="text/sitemap">' in line:
        in_object = True
        object_name = ""
        object_local = ""
    
    # 检测OBJECT结束
    if '</OBJECT>' in line:
        if in_object and indent_level == 1:  # 第一层（根UL下的直接子项）
            results.append((object_name, object_local))
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

print("第一层主分类（根目录下的直接子项）：")
print("=" * 60)
for name, local in results:
    if local:
        print(f"  {name} -> {local}")
    else:
        print(f"  [{name}]")
print(f"\n共找到 {len(results)} 个第一层分类")
