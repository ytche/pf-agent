# 闹鬼英雄手册 整理报告

## 整理策略

闹鬼英雄手册（Haunted Heroes Handbook）内容分散在专长、背景特性、牧师变体领域力量、驱魔仪式、职业变体与术士血脉中。
本次将各类型条目按规则合并到 `pf_rules_md_organized/` 下对应分类的来源书专属文件中。

## 源目录

- `pf_data/phase1/pf_rules_md/未整理/闹鬼英雄手册HHH/`

## 处理统计

- 新增条目：40
- 跳过重复：0
- 错误/跳过文件：0

## 处理内容

### 专长

- `闹鬼专长.md` → `专长/闹鬼英雄手册HHH_专长.md`（保留源书特有专长）
  - 鬼上手（POSSESSED HAND）
  - 自动手（HAND’S AUTONOMY）
  - 人手分离（HAND’S DETACHMENT）
  - 手不释卷（HAND’S KNOWLEDGE）
  - 手心长眼（HAND’S SIGHT）
  - 精魄受体（SPIRIT RIDDEN）
  - 英灵受体（CHANNEL SPIRIT）
  - 精魄盟友（SPIRIT ALLY）
  - 精神训练（SPIRITUAL TRAINING）
  - 虚幻杀手（Ghostslayer）
  - 灵魂打击（Soulwrecking Strike）
  - 魂刃（Soulblade）
  - 魅影盟友（Phantom Ally）
  - 十方鬼众（Spirit Oni Master）
  - 作祟拾荒者（Haunt Scavenger）
- `闹鬼专长.md` → `专长/反派法典VC_专长.md`（通用专长追加到已有聚合文件）
  - 解说之策（Studied Expertise）

### 背景特性

- `背景特性25.md` → `背景特性/闹鬼英雄手册HHH_背景特性.md`（保留源书特有：钉魂门/Rivethun 文化）
  - 英灵向导/英灵引（Guiding Spirit）
  - 灵性依恋（Spiritual Attachment）
  - 钉魂门信徒（Rivethun Adherent）

### 牧师变体领域力量

- `牧师变体领域力量.md` → `职业/核心职业/牧师/page_41.md`
  - 阿斯莫迪斯（诡术领域变体力量）（Asmodeus）
  - 凯登凯连（混乱领域变体力量）（Cayden Cailean）
  - 义洛理（医疗领域变体力量）（Irori）
  - 奈德丽（高贵领域变体力量）（Naderi）
  - 法莱斯玛（安眠领域变体力量）（Pharasma）
  - 厄加图娅（死亡领域变体力量）（Urgathoa）

### 驱魔仪式

- `仪式3.md` → `法术/极限荒野UW_自然仪式.md`（通用仪式追加到已有聚合文件）
  - 地缚结界（Earthbound Ward）
  - 驱除作祟（Exorcise Haunt）
  - 采集亵渎之魂（Harvest the Defiled Soul）
  - 诅咒之音（Voice of the Damned）

### 杀手变体

- `page_672.md` → `职业/混合职业/杀手/page_117.md`
  - 鬼屠（Spiritslayer）

### 女巫变体

- `page_672.md` → `职业/基础职业/女巫/page_70.md`
  - 祈求者（Invoker）

### 审判者变体

- `page_672.md` → `职业/基础职业/审判者/page_78.md`
  - 除灵师（Expulsionist）

### 炼金术师变体

- `page_672.md` → `职业/基础职业/炼金术师/page_21.md`
  - 炼魂士（Ectoplasm Master）

### 战士变体

- `page_672.md` → `职业/核心职业/战士/page_49.md`
  - 钢魂神兵（Steelbound Fighter）

### 法师变体

- `page_672.md` → `职业/核心职业/法师/page_67.md`
  - 密契法师（Pact wizard）

### 通灵者变体

- `page_672.md` → `职业/异能冒险（Occult Adventures）/通灵者/page_262.md`
  - 导灵修士（Rivethun Spirit Channeler）
  - 巫毒祭司（Uda Wendo）

### 唤魂师变体

- `page_672.md` → `职业/异能冒险（Occult Adventures）/唤魂师/page_270.md`
  - 痛苦之源（Scourges）

### 调查员变体

- `page_672.md` → `职业/混合职业/调查员/page_107.md`
  - 怪谈终结者（Skeptic）

### 术士血脉

- `page_1217.md` → `职业/核心职业/术士/page_64.md`
  - 操灵血统（Possessed）


## 验证清单

- [x] 原目录未被修改
- [x] 新增条目均出现 `> 来源：` 标注
- [x] 标注位于条目标题下一行
- [x] 未重复追加
- [x] 进度文档已更新
- [x] 已提交 Git
- [x] 按规则文档 §4.0 源书聚合原则执行：HHH 通用专长（1 条）已合并到 反派法典VC_专长.md；通用仪式（4 条）已合并到 极限荒野UW_自然仪式.md；HHH_驱魔仪式.md 已删除
- [x] 保留源书聚合文件：HHH 专长文件（15 条鬼上手链/灵界机制）和 HHH 背景特性文件（3 条 Rivethun 文化特有）
