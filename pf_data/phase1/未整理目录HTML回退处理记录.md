# 未整理目录 HTML 回退处理记录

> 本文件记录因 Markdown 源文件格式混乱而回退到原始 HTML 重新提取/清洗的处理。
> 由 `未整理目录HTML回退处理记录.json` 自动生成，请勿直接手工编辑本表格。

| 来源 Markdown | 对应 HTML | 问题记录 | 严重程度 | 处理方式 | 接入脚本 | 状态 | 处理时间 |
|---|---|---|---|---|---|---|---|
| `亡灵杀手手册/page_1582.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1582.html` | UNDEAD-ITEMS-001：page_1582.md 物品标签不统一 | 影响轻微 | html_to_markdown + clean_postprocess | organize_undead.py | 已接入 | 2026-07-18T02:28:27 |
| `亡灵杀手手册/page_506.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_506.html` | UNDEAD-SPELLS-001：page_506.md 法术全部挤在一行 | 影响严重 | html_to_markdown + clean_postprocess | organize_undead.py | 已接入 | 2026-07-18T02:28:27 |
| `亡灵杀手手册/专长47.md` | `/Users/chezi/.openclaw/workspace/pf_rules/专长47.htm` | UNDEAD-FEAT-001：专长47.md 标题跨行 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `元素血脉BotE/专长23.md` | `/Users/chezi/.openclaw/workspace/pf_rules/专长23.htm` | BotE-2：专长英文标题跨行且类型括号独立成行 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `元素血脉BotE/背景特性39.md` | `/Users/chezi/.openclaw/workspace/pf_rules/背景特性39.htm` | BotE-3：背景特性来源字段格式不统一 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `冒险者指南AG/其他物品.md` | `/Users/chezi/.openclaw/workspace/pf_rules/其他物品.htm` | AG-ITEMS：其他物品.md 已使用显式 marker 拆分合并 | 需要人工校验 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `冒险者指南AG/职业变体` | `/Users/chezi/.openclaw/workspace/pf_rules/职业变体.htm` | AG-ARCHETYPES：职业变体文件已按源文件整体合并到聚合文件 | 需要人工校验 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `反派法典VC/page_1036.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1036.html` | ~~VC-PAGE1036：page_1036.md 内容严重混行，暂未处理~~（已解决） | 需要人工校验 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `反派法典VC/专长22.md` | `/Users/chezi/.openclaw/workspace/pf_rules/专长22.htm` | VC-FEATS：专长22.md 大量条目标题与首句正文挤在同一行 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `反派法典VC/物品10.md` | `/Users/chezi/.openclaw/workspace/pf_rules/物品10.htm` | ~~VC-ITEMS：物品10.md 格式混乱，暂未处理~~（已解决） | 需要人工校验 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `反派法典VC/神秘仪式.md` | `/Users/chezi/.openclaw/workspace/pf_rules/神秘仪式.htm` | VC-RITUALS：神秘仪式.md 条目标题跨行且部分加粗标记缺失 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `夜之血脉BotN/page_823.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_823.html` | BotN-1：page_823.md 专长之间无分隔且英文标题跨行 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `夜之血脉BotN/page_825.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_825.html` | BotN-2：page_825.md 部分魔法物品无中文名且嵌入前一物品造物需求 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `天界血脉/page_829.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_829.html` | BoA-4：专长/背景特性标题跨行导致定位依赖中文锚点 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `天界血脉/page_830.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_830.html` | BoA-4：专长/背景特性标题跨行导致定位依赖中文锚点 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `怪物召唤者手册MSH/page_666.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_666.html` | MSH-PAGE666：魔法物品内联格式 | 影响中等 | html_to_markdown + clean_postprocess | organize_msh.py | 已接入 | 2026-07-18T16:18:51 |
| `怪物召唤者手册MSH/page_667.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_667.html` | MSH-PAGE667：page_667.md 格式严重混乱 | 影响严重 | html_to_markdown + clean_postprocess | organize_msh.py | 已接入 | 2026-07-18T16:18:51 |
| `怪物召唤者手册MSH/变体/page_1575.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1575.html` | MSH-VARIANTS：变体文件格式差异 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `怪物召唤者手册MSH/变体/血脉狂怒者.md` | `/Users/chezi/.openclaw/workspace/pf_rules/血脉狂怒者.htm` | MSH-VARIANTS：变体文件格式差异 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `护甲大师手册/page_1089.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1089.html` | ARMOR-FEATS：专长文件标题跨行 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `护甲大师手册/page_1184.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1184.html` | ARMOR-FEATS：专长文件标题跨行 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `护甲大师手册/page_375.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_375.html` | ARMOR-FEATS：专长文件标题跨行 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `月之血脉BotM/page_807.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_807.html` | BotM-4：page_807.md 物品标题与价格重量粘连 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `月之血脉BotM/page_809.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_809.html` | BotM-2：page_809.md 专长之间无明确分隔且标题粘连 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `极限荒野UW/专长11.md` | `/Users/chezi/.openclaw/workspace/pf_rules/专长11.htm` | UW-FEATS：专长文件标题跨行且存在重复条目 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `极限荒野UW/物品3.md` | `/Users/chezi/.openclaw/workspace/pf_rules/物品3.htm` | UW-ITEMS：物品文件格式复杂 | 需要人工校验 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `极限诡道UI/变体_职业选项/page_353.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_353.html` | UI-1：变体标题跨行且 Markdown 嵌套不统一 | 建议优化 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `极限诡道UI/变体_职业选项/page_358.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_358.html` | UI-1：变体标题跨行且 Markdown 嵌套不统一 | 建议优化 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `水下冒险Aquatic Adventures/page_1026.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1026.html` | AA-1：源文件页码与内容错配 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `水下冒险Aquatic Adventures/page_1033.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1033.html` | AA-1：源文件页码与内容错配 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `永罪之书BotD/page_1555.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1555.html` | BOTD-OBEDIENCE：魔族仪典专长标题跨行 | 阻塞性 | organize_botd.py preprocess_page_1555_obedience | organize_botd.py | 脚本已修复 | 2026-06-25T15:23:03 |
| `永罪之书BotD/专长38.md` | `/Users/chezi/.openclaw/workspace/pf_rules/专长38.htm` | BOTD-FEATS：专长文件格式不统一 | 影响轻微 | organize_botd.py 增强标题检测 | organize_botd.py | 脚本已修复 | 2026-06-25T12:36:05 |
| `炼狱血脉/page_833.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_833.html` | BoF-3：专长英文名称跨行且部分带中文类型，标题剥离后仍残留括号英文 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `炼狱血脉/page_834.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_834.html` | BoF-4：背景特性标题为纯文本，英文可能被换行拆分 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `秽邪勇士/物品.md` | `/Users/chezi/.openclaw/workspace/pf_rules/物品.htm` | AM-1：跨行加粗标题（来自 `AM_物品.md`、`AM_毒药.md`） | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `野兽血脉BotB/page_697.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_697.html` | BotB-2：page_697.md 职业变体标题格式多样且部分缺失规范标记 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `野兽血脉BotB/page_699.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_699.html` | BotB-3：page_699.md 专长标题格式不统一 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `阴影血脉/page_384.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_384.html` | BoS-2：标题英文名称跨行或被特殊前缀/格式干扰 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `阴影血脉/变体_职业选项/page_1618.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1618.html` | BoS-2：标题英文名称跨行或被特殊前缀/格式干扰 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `阴影血脉/武器附魔6.md` | `/Users/chezi/.openclaw/workspace/pf_rules/武器附魔6.htm` | BoS-2：标题英文名称跨行或被特殊前缀/格式干扰 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `阴招战术工具箱/变体_职业选项/page_457.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_457.html` | DTT-1：page_457.md 与 page_458.md 文件名与内容错配 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `阴招战术工具箱/变体_职业选项/page_458.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_458.html` | DTT-1：page_457.md 与 page_458.md 文件名与内容错配 | 影响轻微 | html_to_markdown + clean_postprocess |  | 待接入 |  |
| `元素大师手册EMH/page_1111.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1111.html` |  |  | html_to_markdown + clean_postprocess | organize_emh.py | 已接入 | 2026-07-18T17:34:44 |
| `元素大师手册EMH/page_1112.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1112.html` |  |  | html_to_markdown + clean_postprocess | organize_emh.py | 已接入 | 2026-07-18T17:34:44 |
| `元素大师手册EMH/page_1113.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1113.html` |  |  | html_to_markdown + clean_postprocess | organize_emh.py | 已接入 | 2026-07-18T17:34:44 |
| `元素大师手册EMH/page_1114.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1114.html` |  |  | html_to_markdown + clean_postprocess | organize_emh.py | 已接入 | 2026-07-18T17:34:44 |
| `元素大师手册EMH/page_1116.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1116.html` |  |  | html_to_markdown + clean_postprocess | organize_emh.py | 已接入 | 2026-07-18T17:34:44 |
| `元素大师手册EMH/page_1119.md` | `/Users/chezi/.openclaw/workspace/pf_rules/page_1119.html` |  |  | html_to_markdown + clean_postprocess | organize_emh.py | 已接入 | 2026-07-18T17:34:44 |

## 统计

- 总记录数：48
- 已解决（已接入/脚本修复/无需接入）：12
- 待接入：36
