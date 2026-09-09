# 永罪之书 整理报告

## 整理策略

永罪之书（Book of the Damned）内容分散在专长、进阶职业、魔法物品、仪式、魔鬼护身符和神恩条目中。
本次将各类型条目按规则合并到 `pf_rules_md_organized/` 下对应分类的已有页面或来源书专属文件中。

## 源目录

- `pf_data/phase1/pf_rules_md/未整理/永罪之书BotD/`

## 处理统计

- 新增条目：164
- 跳过重复：3
- 错误：0

## 处理内容

### 专长

- `专长38.md` → `专长/永罪之书_专长.md`
  - 锁链熟稔（Chain Mastery）
  - 链舞（Dance of Chain）
  - 致命之角（Deadly Horns）
  - 蛇魔（Fiendish Serpent）
  - 翼魔（Fiendish Wings）
  - 梦魇之链（Nightmare Chains）
  - 牺牲效力（Sacrificial Potency）
  - 魂力魔法（Soul-Powered Magic）
  - 侧边栏：灵魂的价值（The Value of Souls）

- `page_1555.md` → `专长/永罪之书_专长.md`
  - 魔族仪典（Fiendish Obedience）
  - 罪恶使徒（Damned Disciple）
  - 罪恶尖兵（Damned Soldier）

### 进阶职业

- `page_1556.md` → `职业/进阶职业/BoDV永罪之书/page_1000.md`
  - 魔鬼大师（Diabolist）

### 魔法物品

- `page_1562.md` → `装备_魔法物品/魔法物品/永罪之书_魔法物品.md`
  - 深渊护符（Amulet of the Abyss）
  - 阿修罗冥想蒲团（Asura Meditation Mat）
  - 末日荒原之烛（Candle of Abaddon）
  - 邪魔之种（Deamon Seed）
  - 痛苦抓握（Grasp of Torment）
  - 冥河邪魔符文石（Hydrodaemon Runestone）
  - 狂躁邪魔之戒（Ring of the Cacodaemon）
  - 恶意之盾（Spiteful Shield）
  - 魂食护身符（Talisman of Soul-Eating）
  - 暴亡板甲（Thanatotic Plate）
  - 暴亡面容（Thanatotic Visage）

### 仪式

- `仪式6.md` → `规则/永罪之书_仪式.md`
  - 分离为四（Quartern Disjunction）
  - 魔族召唤（Fiendish Conjuration）
  - 第一仪式（First Apotheosis）
  - 第二仪式（Second Apotheosis）
  - 第三仪式（Third Apotheosis）
  - 第四仪式（Fourth Apotheosis）
  - 灵魂捕捉（Soul Trap）
  - 名单显现（Manifest Manifestation）

### 魔鬼护身符

- `魔鬼护身符.md` → `装备_魔法物品/魔法物品/永罪之书_魔鬼护身符.md`
  - 恶胆护身符（Bilious Talisman）
  - 忧虑护身符（Melancholic Talisman）
  - 血腥护身符（Sanguine Talisman）

### 神恩条目

- `神恩/地狱/` → `规则/永罪之书_地狱魔神神恩.md`（29 个魔神条目）
- `神恩/末日荒原/` → `规则/永罪之书_末日荒原魔神神恩.md`（5 个魔神条目）
- `神恩/深渊/` → `规则/永罪之书_深渊魔神神恩.md`（59 个魔神条目）
- `神恩/其他/` → `规则/永罪之书_其他魔神神恩.md`（46 个魔神条目）

### 跳过文件

- `page_1515.md`：魔神总览索引页，无独立规则条目，跳过。


## 重复/跳过项

- `page_1556.md` `魔鬼大师 / Diabolist` → `职业/进阶职业/BoDV永罪之书/page_1000.md`（原因：hidden_marker）
- `仪式6.md` `目标` → `规则/永罪之书_仪式.md`（原因：hidden_marker）
- `仪式6.md` `目标` → `规则/永罪之书_仪式.md`（原因：hidden_marker）

## 验证清单

- [x] 原目录未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 未重复追加（`organize_botd.py` 多次运行输出稳定）
- [x] 进度文档已更新
- [ ] 已提交 Git
