# chm_toc_path → 书缩写映射表（KN030 fallback 落地，2026-08-02）

> 来源判定链在页头无《书名》标注（论坛编译帖形态）时，fallback 到 `chm_toc_path` 目录名判定来源。
> 全库查证：未知来源 1780 chunks / 85 文件，chm_toc_path 100% 非空。
> 映射原则：①优先对齐既有 `book_abbreviation` 体系（同书同值）；②既有未用过的按 `规则书缩写对应表.md` 标准缩写；③无标准缩写的用中文名（与既有「武器大师手册/秽邪勇士」同风格）；④跨书索引类不映射。
> 套用脚本：`apply_chm_toc_mapping.py`（后处理，改 chunks.jsonl 顶层 book 字段，不动 metadata.source）。

## 一、organized 专长目录（23 文件）

| doc_id | chm_toc_path | 判定书 | 缩写 | 依据 |
|---|---|---|---|---|
| page_856 | 专长 → UI 极限诡道 | Ultimate Intrigue 极限诡道 | UI | 内容核实：侠客/社交身份专长（凶恶交涉人/弄假成真/义警帮手），末行「见第 9 页」指 UI 书页 |
| page_321 | 专长 → 内海诸神 | Inner Sea Gods 内海诸神 | ISG | 内容：内希斯/四驭者神祇专长 |
| page_361 | 专长 → 护甲大师 | Armor Master's Handbook 护甲大师手册 | 护甲大师手册 | 既有体系中文名（38 chunks 已用） |
| page_311 | 专长 → OA异能冒险 | Occult Adventures 异能冒险 | OA | 缩写表 |
| page_200 | 专长 → UCa 极限战役 | Ultimate Campaign 极限战役 | UCa | 页头《极限战役》标注 + 目录 |
| page_555 | 专长 → 近战战术工具箱 | Melee Tactics Toolbox 近战战术工具箱 | 近战战术工具箱 | 既有 MTT=魔法战术工具箱（Magic Tactics Toolbox）不同书，缩写冲突用中文名 |
| page_556 | 专长 → 阴招战术工具箱 | Dirty Tactics Toolbox | DTT | 缩写表 |
| page_194 | 专长 → 专长概述 | 核心规则手册专长概述章 | CRB | 内容：Feat Concept 概述（专长是什么/先决条件），CRB 专长章引言 |
| page_276 | 专长 → 内海战斗 | Inner Sea Combat 内海战斗 | ISC | 缩写表 |
| page_500 | 专长 → 进化职业起源（ACO） | Advanced Class Origins 进化职业起源 | ACO | 目录名自带 |
| page_538 | 专长 → 纯善/平衡/堕落信念 | Champions of Purity/Balance/Corruption 三合一 | CoP/CoB/CoC | 内容：酩酊侠/占决预导等三本 Champion 合集 |
| page_201 | 专长 → B1 怪物图鉴 | Bestiary 1 怪物图鉴 | B1 | 目录名 |
| page_552 | 专长 → 远程战术工具箱 | Ranged Tactics Toolbox | RTT | 缩写表 |
| page_561 | 专长 → 切里亚斯，魔鬼王朝 | Cheliax, Empire of Devils | CEoD | 缩写表（切利亚斯，魔鬼帝国） |
| page_673 | 专长 → 信仰与哲学 | Faiths & Philosophies | F&P | 既有（1 chunk） |
| page_670 | 专长 → 皇庭英豪 | Heroes of the High Court | HotHC | 缩写表 |
| page_505 | 专长 → 亡灵杀手手册 | Undead Slayer's Handbook 亡灵杀手手册 | 亡灵杀手手册 | 既有体系中文名（1 chunk） |
| page_529 | 专长 → 冒险家手册 | Dungeoneer's Handbook 冒险家手册 | DH | 页头《冒险家手册（Dungeoneer's Handbook）》 |
| page_509 | 专长 → 格拉里昂的半身人 | 格拉里昂的半身人 | 格拉里昂的半身人 | 既有体系中文名（11 chunks） |
| page_531 | 专长 → 萨加瓦，失落的殖民地 | Sargava, The Lost Colony | STLC | 缩写表 |
| page_744 | 专长 → 异能奥秘 | Occult Mysteries 异能奥秘 | 异能奥秘 | 无标准缩写，中文名 |
| page_527 | 专长 → 瓦瑞西亚，传说诞生之地 | Varisia, Birthplace of Legends | 瓦瑞西亚，传说诞生之地 | 无标准缩写，中文名 |
| page_950 | 专长 → CRB 核心规则手册 → 领导力专长和怪物部属 | 核心规则手册 | CRB | 目录名 |
| page_622 | 专长 → MA 神话冒险 | Mythic Adventures 神话冒险 | MA | 目录名 + 内容核实：神话专长/超魔专长类别介绍（KN109 纳入） |

## 二、未整理目录（61 文件，目录名即书全名）

| doc_id | chm_toc_path | 判定书 | 缩写 |
|---|---|---|---|
| 专长11 | 未整理 → 极限荒野UW → 专长 | Ultimate Wilderness 极限荒野 | UW |
| 专长 | 未整理 → 秽邪勇士 → 专长 | Champions of Corruption 秽邪勇士 | 秽邪勇士 |
| 专长41 | 未整理 → 内海种族 → 专长 | Inner Sea Races | ISR |
| 专长33 | 未整理 → 平衡勇士 → 专长 | Champions of Balance | 平衡勇士 |
| 专长1 | 未整理 → 怪物猎人手册MHH → 专长 | Monster Hunter's Handbook | MHH |
| 专长24 | 未整理 → 缘界英雄Heroes from the Fringe → 专长 | Heroes from the Fringe | HftF |
| 专长45 | 未整理 → 任务与战役 → 专长 | 任务与战役 | 任务与战役 |
| page_820 | 未整理 → 屠龙者手册Dragonslayer's Handbook → 专长 | Dragonslayer's Handbook 屠龙者手册 | DSH（顺带修正既有 'Handbook' 14 chunks） |
| 专长51 | 未整理 → 巨人猎手手册 → 专长 | 巨人猎手手册 | 巨人猎手手册 |
| 专长7 | 未整理 → 炼金术手册AM → 专长 | Alchemy Manual | AM |
| 闹鬼专长 | 未整理 → 闹鬼英雄手册HHH → 专长 | Haunted Heroes Handbook | HHH |
| 专长28 | 未整理 → 异能源始OO → 专长 | Occult Origins | OO |
| 专长36 | 未整理 → 间谍大师手册SH → 专长 | Spymaster's Handbook | SH |
| 专长52 | 未整理 → 格拉里昂的侏儒 → 专长 | 格拉里昂的侏儒 | 格拉里昂的侏儒 |
| 动物伙伴专长 | 未整理 → 极限荒野UW → 伙伴 → 动物伙伴专长 | Ultimate Wilderness | UW |
| 专长49 | 未整理 → 地狱骑士之道PotH → 专长 | Path of the Hellknight | PotH |
| 专长9 | 未整理 → 遥远国度DR → 专长 | Distant Realms | DR |
| 专长19 | 未整理 → 街巷英雄HotS → 专长 | Heroes of the Streets | HotS |
| 其他专长 | 未整理 → 冒险者指南AG → 其他专长 | Adventurer's Guide | AG |
| 阵营与阵营专长 | 规则 → Unchained规则 → 游戏进行 → 阵营与阵营专长 | Pathfinder Unchained 解放者 | PU |
| 专长2 | 未整理 → 内海酒馆ISTav → 专长 | Inner Sea Taverns | ISTav |
| 专长13 | 未整理 → 荒野源始WO → 专长 | Wild Origins | WO |
| 专长38 | 未整理 → 永罪之书BotD → 专长 | Book of the Damned | BotD |
| 专长10 | 未整理 → 格拉里昂的城市CoG → 专长 | Cities of Golarion | CoG |
| 专长16 | 未整理 → 恶魔猎人手册DHH → 专长 | Demon Hunter's Handbook | DHH |
| 专长3 | 未整理 → 河域子民PotR → 专长 | People of the River | PotR |
| 专长53 | 未整理 → 敌手指南RM → 专长 | Rival Guide | RM |
| 专长58 | 未整理 → 海洋之血BotS → 专长 | Blood of the Sea | BotS |
| 专长21 | 未整理 → 遥远世界Distant Shores → 专长 | Distant Shores | DS |
| 专长4 | 未整理 → 黑市指南BM → 专长 | Black Markets | BM |
| 专长39 | 未整理 → 卡蒂亚，东方明珠QJotE → 专长 | Qadira, Jewel of the East | QJotE |
| 专长56 | 未整理 → 秘术选集Arcane Anthology → 专长 | Arcane Anthology | ArcaneAnthology |
| 专长57 | 未整理 → CaC部属与伙伴 → 专长 | Cohorts & Companions | CaC部属与伙伴 |
| 专长6 | 未整理 → 哈罗牌手册THH → 专长 | The Harrow Handbook | THH |
| 专长12 | 未整理 → 位面行者手册PHH → 专长 | Planar Handbook | PHH |
| 专长37 | 未整理 → 巫团血脉BotC → 专长 | Blood of the Coven | BotC |
| 专长44 | 未整理 → 沙之子民 → 专长 | People of the Sands | PotS |
| 专长48 | 未整理 → 格拉里昂的地精 → 专长 | 格拉里昂的地精 | 格拉里昂的地精 |
| 专长5 | 未整理 → 神术选集DA → 专长 | Divine Anthology | DA |
| 专长55 | 未整理 → 内海诡道ISI → 专长 | Inner Sea Intrigue | ISI |
| 专长18 | 未整理 → 北地居民 → 专长 | People of the North | PotN |
| 专长25 | 未整理 → 魔法市集指南MM → 专长 | Magic Markets | MM |
| 专长27 | 未整理 → 冒险者的军械库2 → 专长 | Adventurer's Armory 2 冒险者的军械库2 | 2（跟既有） |
| 专长35 | 未整理 → 格拉里昂的混种 → 专长 | 格拉里昂的混种 | 格拉里昂的混种 |
| 专长50 | 未整理 → 格拉里昂的矮人 → 专长 | 格拉里昂的矮人 | 格拉里昂的矮人 |
| 专长31 | 未整理 → 格拉里昂的半身人 → 专长 | 格拉里昂的半身人 | 格拉里昂的半身人 |
| 专长54 | 未整理 → 巨人再临Giants Revisited → 专长 | Giants Revisited | 巨人再临 |
| 专长15 | 未整理 → 秘密探寻者SoS → 专长 | Seekers of Secrets | SoS |
| 专长8 | 未整理 → 繁星子民PotS → 专长 | People of the Stars | 繁星子民 |
| 专长17 | 未整理 → 信仰与哲学F&P → 专长 | Faiths & Philosophies | F&P |
| 专长20 | 未整理 → 再探经典宝藏CTR → 专长 | Classic Treasures Revisited | 再探经典宝藏 |
| 专长23 | 未整理 → 元素血脉BotE → 专长 | Blood of the Elements | BotE |
| 专长26 | 未整理 → 冒险者的军械库 → 专长 | 冒险者的军械库 | 冒险者的军械库 |
| 专长29 | 未整理 → 格拉里昂的兽人 → 专长 | 格拉里昂的兽人 | 格拉里昂的兽人 |
| 专长32 | 未整理 → 反英雄手册Antihero's Handbook → 专长 | Antihero's Handbook | AH（跟既有） |
| 专长34 | 未整理 → 巨龙再临DR → 专长 | Dragons Revisited | 巨龙再临 |
| 专长43 | 未整理 → 安多安，自由之魂ASoL → 专长 | Andoran, Spirit of Liberty | ASoL |
| 专长46 | 未整理 → 格拉里昂的狗头人 → 专长 | 格拉里昂的狗头人 | 格拉里昂的狗头人 |
| 专长47 | 未整理 → 亡灵杀手手册 → 专长 | Undead Slayer's Handbook | 亡灵杀手手册 |
| 其他专长2 | 未整理 → 武术手册Martial Arts Handbook → 其他专长 | Martial Arts Handbook | MAH |

## 三、跨书索引类（不映射，保持 ?，共 136 chunks）

| doc_id | chm_toc_path | chunks | 说明 |
|---|---|---|---|
| page_1367 | 专长 → 超魔专长一览 | 91 | 跨书超魔专长汇总表（末日法术=APG/水生法术=ISM 等），表格无行内来源标注 |
| 造物专长一览 | 专长 → 造物专长一览 | 45 | 跨书造物索引，**行内【】标注已解析到 metadata.source**（如 CRB），仅顶层 book 字段未提升 |

> 造物专长一览的 metadata.source 已就位——顶层提升可后续随 pipeline source_spec 富化做（`MdMappingTocProvider` 纯富化模式，架构决策 29）。

## 四、覆盖统计

- 映射文件：83/85（97.6%）；消解 chunks：1780 - 136 = **1644（92.4%）**
- 剩余未知：136（page_1367 91 + 造物专长一览 45，均为跨书索引形态，非单书可判）
- 映射值复用既有体系比例：既有已用值 39/83、新增值 44（其中缩写表标准缩写为主，中文名 11 个无缩写书）
