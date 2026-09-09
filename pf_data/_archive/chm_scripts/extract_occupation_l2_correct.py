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

# 从根UL开始计算ul_depth，提取职业下的L2项（ul_depth == 2）
root_ul_start = 14  # line 15

ul_depth = 0
l2_items = []

for i in range(root_ul_start, len(lines)):
    ul_opens = lines[i].count('<UL>')
    ul_closes = lines[i].count('</UL>')
    ul_depth += ul_opens - ul_closes
    
    # 只处理职业范围内的项
    if i < target_line:
        continue
    
    # 检查是否超出职业范围（遇到下一个L1项）
    if i > target_line and ul_depth == 1 and '<LI><OBJECT' in lines[i]:
        break
    
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
