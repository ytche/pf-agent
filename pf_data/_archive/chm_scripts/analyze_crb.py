import re

with open('/Users/chezi/.openclaw/workspace/pf_rules_chm/Pathfinder v2.20 SC.hhc', 'rb') as f:
    content = f.read().decode('gbk', errors='ignore')

lines = content.split('\n')

# 分析截图中显示的结构
# 截图显示：
# - 说明（展开）
# - 版本更新纪录
# - 核心规则 Core Rulebook【CRB】（展开）
#   - 开始游戏
#   - 常用术语
#   - ...
#   - 战斗规则（展开）
#   - 环境（展开）
#   - ...

# 让我提取核心规则下的所有直接子项（L2）
print("核心规则下的直接子项（L2）：")
print("=" * 60)

in_crb = False
indent_level = 0
in_object = False
object_name = ""
object_local = ""

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
    
    if '</OBJECT>' in line:
        if in_object:
            # 检查是否是核心规则下的直接子项
            if in_crb and indent_level == 2:
                if object_local:
                    print(f"  {object_name} -> {object_local}")
                else:
                    print(f"  [{object_name}]")
            
            # 检测核心规则开始
            if "核心规则 Core Rulebook" in object_name:
                in_crb = True
            
            # 检测核心规则结束（当回到L1时）
            if in_crb and indent_level == 1 and "核心规则" not in object_name:
                pass  # 仍在核心规则下
            
            if in_crb and indent_level == 0:
                in_crb = False
        
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
