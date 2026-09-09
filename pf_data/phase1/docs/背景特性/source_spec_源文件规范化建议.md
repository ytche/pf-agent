# 背景特性模块源文件规范化建议（source_spec，2026-08-05）

> k3 汇总（人工门 2）。数据基础：三批勘探 `per_file_B1~B3.jsonl` + 人工门 1 对账。
> 分类原则（与专长/法术一致）：**格式缺陷** = 解析器必须处理的源文件形态；**非条目陷阱** = 需识别过滤的内容。
> 读者：formats/trait.py 解析器 + processors/trait.py + 后处理链。

## 第一部分：去重策略（解析器与后处理固化）

1. **基础页权威 + 来源书补录双轨**：A 簇基础页（page_150~157）`【APG】/【UCa】` 条目为核心权威版；来源书文件内同英文名条目视为补录重复——**pipeline 后处理按 `title_en` 去重，保留基础页版本（book=APG/UCa），来源书版本折叠进 aliases**。
2. **同文件重复**：瓦瑞西亚等文件正文重复条目名——按 `title_en` 同文件去重。
3. **三重标题（FM/SH）**：`## 裸中文名`/`## 中文名（EN）`/`**中文名（EN）**` 三形态同条目——**标题归一后去重**（est 已按实际条目口径 3/1）。
4. **无聚合页**：背景特性无专长 page_202 式聚合页，无聚合页重复问题。
5. **不跨文件合并**：ISG 与基础页均含「大气裔」类核心条目（【书】标记区分），保留双份（不同书版本）——仅同书同英文名去重。

## 第二部分：格式缺陷分类（解析器必须处理）

### A. 断行英文名（226 行，三形态全库实例化）

| 形态 | 示例 | 处理 |
|---|---|---|
| 标题跨行 | `**基本背景（****Basic ` + `Traits****）******`（page_150~157 普遍） | ≤3 行窗口合并（专长 FC-1 族同款） |
| 字段值跨行 | `柯莱什或卡蒂亚（Kelesh or ` + `Qadira）`（卡蒂亚QJotE） | 字段值解析跨行 |
| 出自行页码跨行 | `出自《Andoran, Spirit of Liberty pg. ` + `18》` | 出自行合并（安多安同型已确认） |
| 流式三行跨行 | ISG `Affinity for ` + `the ` + `Elements` | ≤3 行窗口合并 |

### B. 字段行异体（八种标签 + 三态布局）

- 八种标签：类型/分类/类别/出处/要求/效果/背景类型/前置条件 → 归一 **类型/需求/效果/出处** 四语义字段
- 三态布局：标准冒号（`**类型**：地区`）/ 无冒号值下一行（`**分类** \n社会`）/ 无字段行（ISG/BoF/BoA → field_status=absent）
- 断行字段标签：`**分类` + `**魔法` 分裂（切利亚斯EOD/遥远世界DS/繁星子民PotS/萨迦瓦StLC）——`**标签**` 后无冒号且换行视为分裂待合并

### C. 链接残留（37 处，KN-候选 A）

- `[摘自 xxx 的翻译](http://…)`（ISG 25 处）——正文完整但链接壳混入 chunk，**后处理剥除链接壳**（保留正文），带「（未获授权）」标注的登记
- 译者行带链接（侏儒）——译者行整体剥除
- **已确认不吞正文**（区别于 KN023 链接吞正文，抽样读过）

### D. 星壳泄漏（解析器归一链）

- 正文行首/行尾 `**`（page_152 孔冉达的变形师/ page_153）
- 英文名内撇号星壳分裂 `Devil****’****s`（page_154）
- 中点星壳分裂 `凯登****·****凯连`（page_157）
- 中文名内泄漏 `**魔****染裔`（page_155）
- 尾部空壳 `**忧虑（****Anxious****）******`、括号闭合缺失 `**Tainted Spirit)`
- 四壳/双壳/单壳混合（A 簇页面普遍）——`**{2,}` 星壳归一为 `**`

### E. 特殊内容（非条目陷阱）

- 【PFS】禁用标记（page_158「PFS中不可使用缺陷系统」/ 坐骑背景【PFS】前缀）——**pfs_eligible 元数据机会**（专长同款）
- 名词解释段（page_150 旋舞修士/镣铐群岛海盗/盾勋执法官 3 段）——非条目，排除
- 脚注段落（Dalenydra 注释）、译者行 7 处——排除
- 纯英文名条目（page_151 Persuasive Insight）——保留，title_en 缺失中文
- 无描述正文条目（page_152 着魔者/page_158 揭露之影）——保留（空 text 预期）
- 章节标题（`**基本背景（****Basic Traits****）******`）——章节语义 → trait_category 或排除
- 表格：BoF 36 行 d% 表 = 非条目对照表（排除）；背景特性17 16 行 = 条目表（产条目）；page_152 8 行 = 条目内 d6 表（属正文）

### F. 英文名错配（KN-候选 B，解析器无法纠，登记不修）

- 人类「瞬击大师」=Horse Lord、TEoG「退役民兵」=Chivalrous、秽邪勇士「影视」=Shadowsight——原文错误

## 第三部分：书缩写映射表（50 来源书 + 13 基础页）

> 映射原则：①文件名后缀缩写优先（安多安ASoL→ASoL）；②缩写表冲突用中文名（繁星子民 PotS 冲突）；③「格拉里昂的 X」系列用中文书名（与专长「格拉里昂的半身人」同风格）；④无缩写文件（任务与战役/初探探索者协会）按 CHM 目录核实。

| 文件名（组织） | 中文书/章节 | 英文书名 | 缩写 |
|---|---|---|---|
| 安多安ASoL_背景特性 | 安多安，自由之魂 | Andoran, Spirit of Liberty | ASoL |
| 北地居民PotN_背景特性 | 北地居民 | People of the North | PotN |
| 卡蒂亚QJotE_背景特性 | 卡蒂亚，东方明珠 | Qadira, Jewel of the East | QJotE |
| 初探内海ISP_背景特性 | 初探内海 | Inner Sea Primer | ISP |
| 初探龙国DEP_背景特性 | 初探龙国 | Dragon Empires Primer | DEP |
| 初探探索者协会_背景特性 | 探索者协会入门 | Pathfinder Society Primer | PSP |
| 内海诸神ISG_背景特性 | 内海诸神 | Inner Sea Gods | ISG |
| 内海骑士KIS_背景特性 | 内海骑士 | Knights of the Inner Sea | KIS |
| 内海海盗PIS_背景特性 | 内海海盗 | Pirates of the Inner Sea | PIS |
| 内海种族ISR_背景特性 | 内海种族 | Inner Sea Races | ISR |
| 塔尔多TEoG_背景特性 | 塔尔多 | Taldor, Echoes of Glory | TEoG |
| 瓦瑞西亚，传说诞生之地_背景特性 | 瓦瑞西亚 | Varisia, Birthplace of Legends | VBoL |
| 沙之子民PotS_背景特性 | 沙漠之民 | People of the Sands | PotS |
| 繁星子民PotS_背景特性 | 星辰之民 | People of the Stars | **繁星子民**（PotS 冲突，用中文名） |
| 河域子民PotR_背景特性 | 河域之民 | People of the River | PotR |
| 废土子民PotW_背景特性 | 废土之民 | People of the Wastes | PotW |
| 神术选集DA_背景特性 | 神术选集 | Divine Anthology | DA |
| 秘术选集ArcaneAnthology_背景特性 | 秘术选集 | Arcane Anthology | AA |
| 组织指南FM_背景特性 | 组织指南 | Faction Guide | FM |
| 间谍大师手册SH_背景特性 | 间谍大师手册 | Spies Handbook | SH |
| 闹鬼英雄手册HHH_背景特性 | 闹鬼英雄手册 | Haunted Heroes Handbook | HHH |
| 黑市指南BM_背景特性 | 黑市指南 | Black Markets | BM |
| 进化职业起源ACO_背景特性 | 进化职业起源 | Advanced Class Origins | ACO |
| 信仰与哲学F&P_背景特性 | 信仰与哲学 | Faiths & Philosophies | F&P |
| 荒野源始WO_背景特性 | 荒野源始 | Wilderness Origins | WO |
| 遥远世界DS_背景特性 | 遥远世界 | Distant Shores | DS |
| 萨迦瓦StLC_背景特性 | 萨迦瓦 | Sarusan, Land of… | StLC |
| 第一世界的遗产LotFW_地区背景特性 | 第一世界的遗产 | Legacy of the First World | LotFW |
| 任务与战役_背景特性 | 任务与战役 | Quests and Campaigns | Q&C |
| 切利亚斯EOD_背景特性 | 切利亚斯，魔鬼帝国 | Cheliax, Empire of Devils | EOD |
| 药剂与毒药P&P_背景特性 | 药剂与毒药 | Potions & Poisons | P&P |
| 元素血脉BotE / 天界血脉BoA / 古国血脉BotA / 月之血脉BotM / 炼狱血脉BoF / 野兽血脉BotB / 巫团血脉BotC | 血脉合集系列 | Blood of the Elements / Angels / Ancients / Moon / Fiends / Beasts / Coven | BotE/BoA/BotA/BotM/BoF/BotB/BotC |
| 堕落信念FoC / 均衡信念FoB | 堕落/均衡信念 | Champions of Corruption / Balance | FoC/FoB |
| 格拉里昂的人类/侏儒/兽人/地精/平衡勇士/混种/狗头人/矮人/精灵_种族背景特性 | 格拉里昂的 X | Humans/Gnomes/Orcs/Goblins/… of Golarion | **格拉里昂的 X**（中文名） |
| 格拉里昂的秽邪勇士_背景特性 | 秽邪勇士 | Champions of Corruption 等 | **秽邪勇士**（中文名） |
| 基础页 page_150~158 / 典范 / 坐骑 / 背景特性17 | — | — | 解析自【书缩写】标记（APG/UCa/AA 等） |

> ⚠️ **待核实**：繁星子民/沙之子民 PotS 冲突、任务与战役（Q&C 或 Quests and Campaigns）、初探探索者协会（PSP）三个缩写需 pipeline 阶段 chm_toc_path 回填时核实；格拉里昂系列 10 书缩写统一用中文名。

## 第四部分：无类型字段文件来源推断

| 文件 | 类型推断 |
|---|---|
| ISG（108 条流式） | 标题括号 = 神名（非类型）；类型按文件上下文 = 信仰（ISG 书主题）或 absent |
| BoF（16 条 H2） | 书主题 = 血脉/血统相关，absent 或按条目内容推断 |
| BoA（9 条 H2） | 同上 |

## 第五部分：交付物清单（人工门 2 收尾）

- [x] `format_cluster_assign.json`（15 簇 63 文件）
- [x] `format_clusters_规范与偏差对账.md`（15 簇定义 + 括号语义漂移 + 偏差对账）
- [x] 本文档（去重 + 格式缺陷 + 书缩写映射）
- [ ] `test_seeds.jsonl`（15 簇代表条目，TDD 种子）
- [ ] `背景特性元数据设计.md`（字段 × component_type 矩阵 + field_status 三态）
