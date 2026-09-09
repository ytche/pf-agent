# 位面冒险（Planar Adventures）整理报告

## 整理策略

位面冒险（Planar Adventures）内容分散在新玩家种族、职业变体、专长、新物品等文件中。
本次将所有规则条目按类型合并到 `pf_rules_md_organized/` 下对应分类目录。

## 源目录

- `pf_data/phase1/pf_rules_md/未整理/位面冒险PA/`

## 处理统计

- 新增条目：33
- 跳过重复：9
- 错误：0

## 处理内容

### 新玩家种族
- 秩裔（Aphorite）→ `种族/罕见种族/位面冒险PA_秩裔.md`
- 熵裔（Ganzi）→ `种族/罕见种族/位面冒险PA_熵裔.md`
- 暮行者（Duskwalker）→ `种族/罕见种族/位面冒险PA_暮行者.md`

### 职业变体
- 暗刃（Gloomblade，战士）→ `职业/核心职业/战士/page_49.md`
- 幻梦贼（Dreamthief，盗贼）→ `职业/核心职业/盗贼/page_47.md`
- 原初使者（Progenitor，德鲁伊）→ `职业/核心职业/德鲁伊/page_37.md`
- 位面斥候（Planar Scout，游侠）→ `职业/核心职业/游侠/page_51.md`
- 契约巫师（Pact Witch，女巫）→ `职业/基础职业/女巫/page_70.md`
- 诸界见证人（Chronicler of Worlds，吟游诗人）→ `职业/核心职业/吟游诗人/page_38.md`
- 灵魂守卫（Soul Warden，唤魂师）→ `职业/异能冒险（Occult Adventures）/通灵者/page_262.md`
- 界门寻索人（Portal Seeker，调查员）→ `职业/混合职业/调查员/page_31.md`
- 唯心教众（Idealist，牧师）→ `职业/核心职业/牧师/page_41.md`
- 世界探索者（Worldseeker，法师）→ `职业/核心职业/法师/page_45.md`
- 爱塔剑客（Azatariel，游荡剑客）→ `职业/混合职业/游荡剑客/page_56.md`

### 专长
- 汲引专长（page_1492.md）→ `专长/位面冒险PA_专长.md`
- 其他专长（其他专长1.md：抓取用尾巴、鞭击用尾巴、调皮用尾巴、位面血脉、精通异界传送、引导圣临）→ `专长/位面冒险PA_专长.md`
- 位面谐律规则与效果 → `专长/位面冒险PA_位面谐律.md`

### 新物品
- 护甲特殊能力（page_1570.md：气缓、结茧、共旅、混影）→ `装备_魔法物品/防具附魔/位面冒险PA_防具附魔.md`
- 武器特殊能力（page_1569.md：无阵营、位面打击）→ `装备_魔法物品/武器/位面冒险PA_武器附魔.md`
- 特殊武器（page_1568.md：不确定之刃、魔蝠首级之箭、库凯图斯的碎片）→ `装备_魔法物品/武器/位面冒险PA_特殊武器.md`
- 权杖（page_1566.md：末日/喝令/福佑/墓园/喧嚣/冥河超魔权杖、叉形权杖、厉鬼权杖）→ `装备_魔法物品/魔法物品/戒指_权杖_法杖/位面冒险PA_权杖.md`
- 戒指（page_1572.md：熵与秩之戒、位面聚焦之戒、灵魂联结戒指）→ `装备_魔法物品/魔法物品/戒指_权杖_法杖/位面冒险PA_戒指.md`
- 奇物（page_1567.md：受膏者圣徽、星仪、位面锚定之靴等16件）→ `装备_魔法物品/魔法物品/奇物/位面冒险PA_奇物.md`

## 重复/跳过项

- `职业变体/page_1433.md` `暗刃 / Gloomblade` → `职业/核心职业/战士/page_49.md`（原因：hidden_marker）
- `职业变体/page_1475.md` `幻梦贼 / Dreamthief` → `职业/核心职业/盗贼/page_47.md`（原因：hidden_marker）
- `职业变体/page_1484.md` `契约巫师 / Pact Witch` → `职业/基础职业/女巫/page_70.md`（原因：existing_content (契约巫师)）
- `职业变体/page_1478.md` `诸界见证人 / Chronicler of Worlds` → `职业/核心职业/吟游诗人/page_38.md`（原因：existing_content (诸界见证人)）
- `职业变体/page_1476.md` `灵魂守卫 / Soul Warden` → `职业/异能冒险（Occult Adventures）/通灵者/page_262.md`（原因：existing_content (灵魂守卫)）
- `职业变体/page_1485.md` `界门寻索人 / Portal Seeker` → `职业/混合职业/调查员/page_31.md`（原因：hidden_marker）
- `职业变体/page_1486.md` `唯心教众 / Idealist` → `职业/核心职业/牧师/page_41.md`（原因：hidden_marker）
- `职业变体/page_1487.md` `世界探索者 / Worldseeker` → `职业/核心职业/法师/page_45.md`（原因：hidden_marker）
- `职业变体/游荡剑客.md` `爱塔剑客 / Azatariel` → `职业/混合职业/游荡剑客/page_56.md`（原因：hidden_marker）

## 验证清单

- [x] 原目录未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 未重复追加
- [x] 进度文档已更新
- [x] 已提交 Git
