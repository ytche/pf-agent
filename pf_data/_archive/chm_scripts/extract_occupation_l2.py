import re

with open('Pathfinder v2.20 SC.hhc', 'rb') as f:
    content = f.read()
    
text = content.decode('GBK')
lines = text.split('\n')

# 找到职业L1项的位置
target_line = None
for i, line in enumerate(lines):
    if '<LI><OBJECT' in line:
        for j in range(i, min(i+5, len(lines))):
            if 'Name' in lines[j] and '职业' in lines[j]:
                match = re.search(r'value="([^"]+)"', lines[j])
                if match and match.group(1) == '职业':
                    target_line = i
                    break
        if target_line:
            break

print(f'职业L1项开始: line {target_line + 1}')

# 找到职业子UL的范围
ul_start = None
ul_end = None
ul_depth = 0

for i in range(target_line, len(lines)):
    ul_opens = lines[i].count('<UL>')
    ul_closes = lines[i].count('</UL>')
    
    if ul_start is None and ul_opens > 0:
        ul_start = i
        ul_depth = 1
        continue
    
    if ul_start is not None:
        ul_depth += ul_opens - ul_closes
        if ul_depth == 0 and ul_closes > 0:
            ul_end = i
            break

print(f'职业子UL范围: lines {ul_start + 1} - {ul_end + 1}')

# 提取职业下的L2项（ul_depth == 2时的LI OBJECT）
ul_depth = 0
l2_items = []

for i in range(ul_start, ul_end + 1):
    ul_opens = lines[i].count('<UL>')
    ul_closes = lines[i].count('</UL>')
    ul_depth += ul_opens - ul_closes
    
    # L2项：ul_depth == 2 时的 LI OBJECT
    if ul_depth == 2 and '<LI><OBJECT' in lines[i]:
        # 获取名称和Local
        name = ''
        local = ''
        for j in range(i, min(i+5, len(lines))):
            if 'Name' in lines[j]:
                match = re.search(r'value="([^"]+)"', lines[j])
                if match:
                    name = match.group(1)
            if 'Local' in lines[j]:
                match = re.search(r'value="([^"]+)"', lines[j])
                if match:
                    local = match.group(1)
        l2_items.append((i+1, name, local))

print(f'\n职业下的L2项（共{len(l2_items)}个）：')
for line_num, name, local in l2_items:
    local_display = local if local else '(目录)'
    print(f'  line {line_num}: {name} -> {local_display}')
