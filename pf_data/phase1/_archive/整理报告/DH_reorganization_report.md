# 地城探险者手册 整理报告

## 整理策略

地城探险者手册（Dungeon Explorer's Handbook）内容分散在职业变体、背景特性和物品文件中。
本次将各类型条目按规则合并到 `pf_rules_md_organized/` 下对应分类的已有页面或来源书专属文件中。

## 源目录

- `pf_data/phase1/pf_rules_md/未整理/地城探险者手册DH/`

## 处理统计

- 新增条目：5
- 跳过重复：4
- 错误/跳过文件：0

## 处理内容

### 职业变体

- `变体/page_535.md` → `职业/基础职业/炼金术师/全变体未整合.md`：炽热火炬手（Blazing Torchbearer）
- `变体/page_536.md` → `职业/核心职业/游侠/page_51.md`：马夫（Groom）
- `变体/page_537.md` → `职业/核心职业/盗贼/page_49.md`：工兵（Sapper）

### 背景特性

- `背景特性42.md` → `背景/地城探险者手册DH_背景特性.md`
  - 光明前途（Destined for Greatness）

### 物品

- `物品6.md` → `装备_魔法物品/货品服务/地城探险者手册DH_物品.md`
  - 干冰油（Cardice Oil）
  - 发条响尾蛇（Key-wound rattler）
  - 特种烟玉（Specialty Smoke Pellet）
  - 盗贼戒指（Thieves' ring）
  - 盗贼工具延长器（Thieves' tool extenders）


## 重复/跳过项

- `变体/page_535.md` `炽热火炬手 / Blazing Torchbearer` → `职业/基础职业/炼金术师/全变体未整合.md`（原因：existing_content (Blazing Torchbearer)）
- `变体/page_536.md` `马夫 / Groom` → `职业/核心职业/游侠/page_51.md`（原因：hidden_marker）
- `变体/page_537.md` `工兵 / Sapper` → `职业/核心职业/盗贼/page_49.md`（原因：hidden_marker）
- `背景特性42.md` `光明前途` → `背景/地城探险者手册DH_背景特性.md`（原因：hidden_marker）
- `物品6.md` `干冰油` → `装备_魔法物品/货品服务/地城探险者手册DH_物品.md`（原因：hidden_marker）
- `物品6.md` `发条响尾蛇` → `装备_魔法物品/货品服务/地城探险者手册DH_物品.md`（原因：hidden_marker）
- `物品6.md` `特种烟玉` → `装备_魔法物品/货品服务/地城探险者手册DH_物品.md`（原因：hidden_marker）

## 验证清单

- [x] 原目录未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 未重复追加
- [x] 进度文档已更新
- [x] 已提交 Git
