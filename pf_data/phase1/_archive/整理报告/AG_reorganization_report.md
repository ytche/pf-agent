# 冒险者指南AG 整理报告

## 整理策略

冒险者指南AG（Adventurer's Guide）内容分散在组织背景、职业变体、进阶职业、专长、物品等文件中。
本次将 `其他专长.md` 按条目拆分合并，将 `进阶职业/` 按源文件整体合并到聚合文件，
将 `其他物品.md` 按物品子类型拆分合并到 `装备_魔法物品/` 各子目录；
将 `职业变体/` 下源文件先聚合到 `职业/冒险者指南AG_变体.md`，
再通过 `split_ag_archetypes.py` 按职业拆分到各职业已有的职业变体页面（如 `page_41.md`、`page_52.md` 等），
不新建 `<来源书>_<职业>变体.md`；14 个组织背景文件仍为纯背景描述，暂不处理。

## 源目录

- `pf_data/phase1/pf_rules_md/未整理/冒险者指南AG/`

## 处理统计

- 新增条目：0
- 跳过重复：77
- 错误：0

## 处理内容

- 专长：`其他专长.md` → `专长/冒险者指南AG_专长.md`
- 职业变体：`职业变体/` 下 18 个文件 → 拆分到各职业既有职业变体页面
- 进阶职业：`进阶职业/` 下 4 个文件 → `职业/进阶职业/冒险者指南AG_进阶职业.md`
- 物品：`其他物品.md` → 按子类型拆分：
  - 奇物 → `装备_魔法物品/魔法物品/奇物/冒险者指南AG_奇物.md`
  - 权杖 → `装备_魔法物品/魔法物品/戒指_权杖_法杖/冒险者指南AG_权杖.md`
  - 武器 → `装备_魔法物品/武器/冒险者指南AG_武器.md`
  - 炼金物品 → `装备_魔法物品/货品服务/page_212.md`

## 暂未处理

- 14 个组织背景文件（红螳螂、盾徽财团、灰少女、地狱骑士、掌灯人、探索者协会、银渡鸦、雄鹰骑士、铃花会、盗贼议会、钉魂门、风暴朝拜者、玛伽姆比亚、扎布里蒂）：均为纯背景描述，无规则条目。
详见 `pf_data/phase1/未整理目录整理问题记录.md` 中 AG-* 记录。

## 重复/跳过项

- `其他专长.md` `奥多里战斗技艺` → `专长/冒险者指南AG_专长.md`（原因：hidden_marker）
- `其他专长.md` `奥多里决斗学徒` → `专长/冒险者指南AG_专长.md`（原因：hidden_marker）
- `其他专长.md` `加仑之戒` → `专长/冒险者指南AG_专长.md`（原因：hidden_marker）
- `其他专长.md` `涤净引导` → `专长/冒险者指南AG_专长.md`（原因：hidden_marker）
- `其他专长.md` `出自` → `专长/冒险者指南AG_专长.md`（原因：hidden_marker）
- `其他专长.md` `触力旁通` → `专长/冒险者指南AG_专长.md`（原因：hidden_marker）
- `其他专长.md` `西瑞安之证` → `专长/冒险者指南AG_专长.md`（原因：hidden_marker）
- `其他专长.md` `精魂信烽` → `专长/冒险者指南AG_专长.md`（原因：hidden_marker）
- `其他专长.md` `精魂斥责` → `专长/冒险者指南AG_专长.md`（原因：hidden_marker）
- `其他专长.md` `精魂视野` → `专长/冒险者指南AG_专长.md`（原因：hidden_marker）
- `其他专长.md` `风暴洗礼` → `专长/冒险者指南AG_专长.md`（原因：hidden_marker）
- `职业变体/page_1382.md` `绽放之光(Blossoming Light)` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/page_1383.md` `卑铜门徒(Brazen Disciple)` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/page_1384.md` `灵辅修士 Geminate Invoker（野蛮人变体）` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/page_1385.md` `泰尔曼多圣从者  Scion of Talmandor（圣武士变体）` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/page_1386.md` `卡蒂亚马王（QADIRAN HORSELORD，骑士变体）QADIRAN` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/page_1387.md` `旭骑兵（Sunrider，德鲁伊变体）SUNRIDER` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/page_1388.md` `带头大哥（RINGLEADER ，吟游诗人变体）` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/page_1389.md` `奥多里卫士（Aldori Defender，战士变体）ALDORI` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/page_1390.md` `雷斯兰暴徒（Rostland Bravo，游荡剑客变体）ROSTLAND` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/page_1391.md` `展览馆长（Curator，秘学士变体）CURATOR` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/page_1392.md` `铃花浚洫客（Bellflower Irrigator，盗贼变体）BELLFLOWER` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/page_1393.md` `铃花秋穑客（Bellflower Harvester，侠客变体）BELLFLOWER` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/page_1394.md` `符文法师（RUNESAGE，法师变体）RUNESAGE` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/page_1395.md` `魔符战士（SIGILUS，魔战士变体）SIGILUS` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/唤魂师2.md` `内衍学者 Involutionist 【唤魂师变体】` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/猎人1.md` `图腾猎人Totem-Bonded（猎人变体）` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/血脉狂怒者2.md` `贤者之血（Enlightened Bloodrager）【血脉狂怒者变体】` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `职业变体/通灵者2.md` `澜梦者 Storm Dreamer 【通灵者变体】` → `职业/冒险者指南AG_变体.md`（原因：hidden_marker）
- `进阶职业/page_1448.md` `亚萨维尔（Asavir）` → `职业/进阶职业/冒险者指南AG_进阶职业.md`（原因：hidden_marker）
- `进阶职业/page_1450.md` `完美门徒（Student of Perfection）` → `职业/进阶职业/冒险者指南AG_进阶职业.md`（原因：hidden_marker）
- `进阶职业/奥多里剑豪.md` `奥多里剑豪（Aldori Swordlord）` → `职业/进阶职业/冒险者指南AG_进阶职业.md`（原因：hidden_marker）
- `进阶职业/钉魂密使.md` `钉魂密使（Rivethun Emissary）` → `职业/进阶职业/冒险者指南AG_进阶职业.md`（原因：hidden_marker）
- `其他物品.md` `神圣之火披风 / Cloak Of Heavenly Fire` → `装备_魔法物品/魔法物品/奇物/冒险者指南AG_奇物.md`（原因：hidden_marker）
- `其他物品.md` `抗力马鞍 / Caparison of resistance` → `装备_魔法物品/魔法物品/奇物/冒险者指南AG_奇物.md`（原因：hidden_marker）
- `其他物品.md` `汉化膏与娘化酊 / Anderos salve and mulibrous tincture` → `装备_魔法物品/货品服务/page_212.md`（原因：hidden_marker）
- `其他物品.md` `猛犸长枪 / Mammoth Lance` → `装备_魔法物品/武器/冒险者指南AG_武器.md`（原因：hidden_marker）
- `其他物品.md` `魅影尘 / Phantom Ash` → `装备_魔法物品/货品服务/page_212.md`（原因：hidden_marker）
- `其他物品.md` `风暴护符 / Amulet of the Storm` → `装备_魔法物品/魔法物品/奇物/冒险者指南AG_奇物.md`（原因：hidden_marker）
- `其他物品.md` `哥兹面具 / Goz Mask` → `装备_魔法物品/魔法物品/奇物/冒险者指南AG_奇物.md`（原因：hidden_marker）
- `其他物品.md` `罐装闪电 / Jar of Lightning` → `装备_魔法物品/魔法物品/奇物/冒险者指南AG_奇物.md`（原因：hidden_marker）
- `其他物品.md` `风暴朝拜者权杖 / Storm Kindler's Rod` → `装备_魔法物品/魔法物品/戒指_权杖_法杖/冒险者指南AG_权杖.md`（原因：hidden_marker）

## 验证清单

- [x] 原目录未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 未重复追加
- [x] 进度文档已更新
- [x] 已提交 Git
