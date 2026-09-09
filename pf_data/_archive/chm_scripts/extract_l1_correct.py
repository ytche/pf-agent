import re

with open('/Users/chezi/.openclaw/workspace/pf_rules_chm/Pathfinder v2.20 SC.hhc', 'rb') as f:
    content = f.read().decode('gbk', errors='ignore')

lines = content.split('\n')

# 找到根 <UL> 的位置
root_ul_line = 0
for i, line in enumerate(lines):
    if '<UL>' in line:
        root_ul_line = i
        break

print(f"根 <UL> 在 line {root_ul_line}")

# 找到根 </UL> 的位置
root_end_line = 0
ul_depth = 0
for i in range(root_ul_line, len(lines)):
    ul_depth += lines[i].count('<UL>')
    ul_depth -= lines[i].count('</UL>')
    if ul_depth == 0:
        root_end_line = i
        break

print(f"根 </UL> 在 line {root_end_line}")

# 在根 UL 内，提取所有 L1 项
# L1 项的特征：紧跟在 <LI> 后的 <OBJECT>
results = []
for i in range(root_ul_line, root_end_line):
    line = lines[i].strip()
    
    # 检测 <LI><OBJECT> 模式
    if '<LI><OBJECT type="text/sitemap"' in line or ('<LI>' in line and i+1 < len(lines) and '<OBJECT type="text/sitemap"' in lines[i+1]):
        # 提取接下来的 Name 和 Local
        name = ""
        local = ""
        for j in range(i, min(i+5, len(lines))):
            if 'param name="Name"' in lines[j]:
                match = re.search(r'value="([^"]*)"', lines[j])
                if match:
                    name = match.group(1)
            if 'param name="Local"' in lines[j]:
                match = re.search(r'value="([^"]*)"', lines[j])
                if match:
                    local = match.group(1)
        
        results.append((name, local, i))

print(f"\n所有 L1 项：")
print("=" * 60)
for name, local, line_num in results:
    if local:
        print(f"  {name} -> {local} (line {line_num})")
    else:
        print(f"  [{name}] (line {line_num})")

print(f"\n总共 {len(results)} 个 L1 项")
