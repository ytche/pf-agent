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

# 从根UL开始计算ul_depth，提取职业下的所有项并记录层级
root_ul_start = 14  # line 15

ul_depth = 0
current_items = []  # 记录所有项及其层级

for i in range(root_ul_start, len(lines)):
    ul_opens = lines[i].count('<UL>')
    ul_closes = lines[i].count('</UL>')
    ul_depth += ul_opens - ul_closes
    
    # 只处理职业范围内的项
    if i < target_line:
        continue
    
    # 检查是否超出职业范围（遇到下一个L1项）
    if i > target_line and ul_depth == 1 and '<LI><OBJECT' in lines[i]:
        name = ''
        for j in range(i, min(i+5, len(lines))):
            if 'Name' in lines[j]:
                match = re.search(r'value="([^"]+)"', lines[j])
                if match:
                    name = match.group(1)
                    break
        print(f'\n遇到下一个L1项: line {i+1}: {name} (depth={ul_depth})')
        break
    
    # 记录所有LI OBJECT项
    if '<LI><OBJECT' in lines[i]:
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
        current_items.append((i+1, name, local, ul_depth))

# 按层级分组
l2_items = [item for item in current_items if item[3] == 2]
l3_items = [item for item in current_items if item[3] == 3]
l4_items = [item for item in current_items if item[3] == 4]

print(f'\n职业下的L2项（共{len(l2_items)}个）：')
for line_num, name, local, depth in l2_items:
    local_display = local if local else '(目录)'
    print(f'  line {line_num}: {name} -> {local_display}')

# 按L2父项分组L3项 - 修正版
print('\n\n=== 按L2父项分组的L3项 ===')

for idx, (l2_line, l2_name, l2_local, l2_depth) in enumerate(l2_items):
    l2_start = l2_line - 1
    
    # 找到这个L2项的结束位置
    # L2项的结束 = 下一个L2项的开始，或者L1范围的结束
    if idx + 1 < len(l2_items):
        l2_end = l2_items[idx + 1][0] - 1
    else:
        # 最后一个L2项，找到职业范围的结束
        l2_end = None
        for i in range(l2_start, len(lines)):
            if '</UL></UL><LI><OBJECT' in lines[i] or (i > l2_start and '</UL><LI><OBJECT' in lines[i] and '背景特性' in lines[i]):
                l2_end = i
                break
    
    # 收集这个L2下的L3项
    l3_under_l2 = []
    for l3_line, l3_name, l3_local, l3_depth in l3_items:
        if l2_start <= l3_line - 1 < l2_end:
            l3_under_l2.append((l3_line, l3_name, l3_local))
    
    if l3_under_l2:
        print(f'\n【{l2_name}】下的L3项（{len(l3_under_l2)}个）：')
        for l3_line, l3_name, l3_local in l3_under_l2:
            l3_local_display = l3_local if l3_local else '(目录)'
            print(f'  line {l3_line}: {l3_name} -> {l3_local_display}')
    else:
        print(f'\n【{l2_name}】下没有L3项')
