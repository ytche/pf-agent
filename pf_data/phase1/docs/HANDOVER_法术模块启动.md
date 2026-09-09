# 交接：vectorizer/ 框架搭建 + 法术模块 TDD 实践

> 2026-07-24 · 本阶段产出：架构设计确认 → 探索法术数据 → 编写实施计划

---

## 一、做了什么

1. **确认终局架构设计**：`docs/VECTORIZER_ARCHITECTURE_DESIGN.md` v1.4 — 16 条设计决策，7 模块包结构
2. **深度探索法术源数据**：
   - 149 个 .md 文件，4 个子目录（核心/冒险之路/玩家伴侣/战役设定）
   - 7 种格式变体（管道表格/Bold标签/冒号标签/AONPRD/紧凑内联/换行无冒号/文章体）
   - 特殊资源：`Spell index.md`（1786 行，~1700+ 法术→来源书映射表）
3. **编写了完整实施计划**：`/Users/chezi/.claude/plans/users-chezi-code-java-pf-agent-pf-data-wise-shore.md`

---

## 二、关键决策回顾（已确认）

| # | 决策 | 说明 |
|---|------|------|
| 1 | 框架先行，法术试点 | 搭建 vectorizer/ 包，法术模块作为第一个使用者 |
| 2 | TDD 先行 | 先写 6 类测试，再写实现 |
| 3 | CategoryPipeline 推迟 | 等法术接入后再抽象（两个样本） |
| 4 | 职业重构等法术完成 | 与 CategoryPipeline 抽象一次做完 |
| 5 | 格式两阶段 | Phase 1 normalize（纯去噪）+ Phase 2 promote（结构提升） |
| 6 | 不变量契约 | fixup 必须声明执行前后不变量 |
| 7 | Chunk.extra 存法术字段 | 不污染通用字段 |
| 8 | Spell index.md 双用途 | SourceProvider 数据源 + 索引 chunk |

---

## 三、实施计划速查

详细计划见：`/Users/chezi/.claude/plans/users-chezi-code-java-pf-agent-pf-data-wise-shore.md`

### 步骤概览

| Step | 内容 | 产出 | 依赖 |
|------|------|------|------|
| 0 | 搭建 vectorizer/ 包骨架 | 22 个文件（目录 + `__init__.py`） | 无 |
| 1 | sources/providers.py | SourceProvider 链（9 Provider） | Step 0 |
| 2 | formats/ (base + spell) | 7 种格式归一化 + 字段提取 | Step 0 |
| 3 | processors/ (base + spell) | FileProcessor 模板 + SpellProcessor | Step 1, 2 |
| 4 | pipeline.py | 流水线编排 + CLI | Step 1, 2, 3 |
| 5 | diagnostics.py | 源文件质量门（ERROR/WARN） | 无（可并行） |
| 6 | audit.py | Tier 1 审计引擎 | Step 4 |
| 7 | fixups/base.py | @fixup 装饰器 + 不变量引擎 | 无（可并行） |
| 8 | tests/ (6 类 TDD) | 先写测试，后驱动实现 | Step 2 |
| 9 | 全量跑 + 验收 | 149 文件处理 + verify_spells.py | Step 1~8 |

### 并行优化

- Step 1 + 2 可并行
- Step 5 + 7 可与 Step 1~4 并行
- Step 8 在 Step 2 完成后立即开始

---

## 四、法术数据关键文件

| 文件 | 路径 | 作用 |
|------|------|------|
| 法术索引表 | `pf_rules_md_organized/法术/Spell index.md` | ~1700+ 法术→来源书映射，1786 行管道表格 |
| CRB 法术（管道表格） | `pf_rules_md_organized/法术/Spell CRB.md` | 格式变体 A，最大文件 |
| UM 法术（Bold标签） | `pf_rules_md_organized/法术/Spell UM.md` | 格式变体 B |
| ACG 法术（冒号标签） | `pf_rules_md_organized/法术/Spell ACG.md` | 格式变体 C |
| 冒险之路法术（AONPRD） | `pf_rules_md_organized/法术/冒险之路/正义之怒.md` | 格式变体 D |
| 玩家伴侣法术 | `pf_rules_md_organized/法术/玩家伴侣/BotA-古国血脉.md` | 格式变体 E |
| MTT 法术（换行无冒号） | `pf_rules_md_organized/法术/魔法战术工具箱MTT_法术.md` | 格式变体 F |
| 神话法术（文章体） | `pf_rules_md_organized/法术/page_625.md` | 格式变体 G |

---

## 五、Spell index.md 特别说明

```
格式：| 来源书缩写 | 中文名(English Name) |
覆盖：AArch, ACG, APG, ARG, CotR, CRB, FoB, FoC, FoP, ISG, ISM, ISWG, MTT, RTT, TG, UC, UM, OA
```

这个文件的作用：
1. **作为 SourceProvider**：SpellIndexProvider 加载此表，按英文名查来源书缩写（置信度 65）
2. **作为索引 chunk**：整个表清洗后作为 `component_type: "spell_index"` 的独立 chunk，RAG 可检索"法术 X 出自哪本书"
3. **作为中英对照表**：1,700+ 法术的中英名对照，可用于术语对齐

数据质量问题：
- 英文名含换行断裂（需 `re.sub(r'\s+', ' ', name)` 修复）
- 部分行含译者注（`※...`），需清理
- 表头注明"此部分暂不更新"，可能缺少数法术

---

## 六、参考文档索引

| 文档 | 路径 | 说明 |
|------|------|------|
| 终局架构设计 | `docs/VECTORIZER_ARCHITECTURE_DESIGN.md` | v1.4，16 决策 + 7 模块设计 |
| 质量迭代工作流 | `docs/WORKFLOW.md` | v2.0，Step 0~5 标准化流程 |
| 实施计划 | `.claude/plans/users-chezi-code-java-pf-agent-pf-data-wise-shore.md` | 本文档附带的详细计划 |
| 项目整体状态 | `PROJECT_HANDOVER.md` | 完整项目状态 + 待办 |
| 职业主脚本（参考） | `vectorization_prep_profession.py` | 4236 行，SourceProvider 提取源 |
| 职业格式簇报告 | `职业目录格式簇报告.json` | 格式变体分析参考 |

---

## 七、下一步（按优先级）

1. **Step 0**：创建 vectorizer/ 包骨架（22 个文件）
2. **Step 1**：从 `vectorization_prep_profession.py` 提取 SourceProvider 链 → `sources/providers.py`
3. **Step 8 + 2**：先写 TDD 测试（conftest.py + 6 类测试），再实现 `formats/spell.py`
4. **Step 3~7**：按依赖顺序实现剩余模块
5. **Step 9**：全量跑 149 文件 → 按 WORKFLOW.md Step 0~5 迭代修复

---

*本交接文档供下一模型继续实施。所有设计决策已确认，计划已编写完毕，无需重新探索或讨论。*

*直接按 Step 顺序开始实施即可。*
