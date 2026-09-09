# PF 1e 规则问答 Agent - 设计文档

## 1. 项目目标

构建一个 PathFinder 1e（PF 1e）规则问答 Agent 产品的一期功能：

- 用户通过微信小程序用自然语言提问；
- Java 后端基于向量检索 + LLM 生成回答；
- 每条回答都附带可追溯的规则来源（规则书、目录路径、原文片段），方便用户核验信息正确性。

中英术语对照表是数据清洗的一部分工作，不是最终目标。最终目标是可核验的规则问答 Agent。

## 2. 当前基线

- 仓库路径：`/Users/chezi/code/java/pf_agent`
- 已有资产：
  - `pf_data/`：CHM→Markdown 转换脚本、目录提取脚本、分析脚本；
  - `pf_data/phase1/`：术语清洗脚本、504 条术语表（15 分类）、2156 个 Markdown 规则文件、`CHM_FULL_TOC_WITH_LEVELS.md` 目录结构；
  - `PROJECT_HANDOVER.md`：前任 Agent 的交接文档，**仅供参考**，非最终依据。
- 缺失部分：数据库、向量库、Java 后端、前端、机器可读格式的术语表。
- 根目录未初始化 Git，Git 仅存在于 `pf_data/phase1/`。

## 3. 总体路线图（数据优先）

```
阶段 0：基线建立
  └── 根目录初始化 Git，建立可回滚基线

阶段 1：数据治理
  ├── 1.1 术语表治理：修正误分类、补元数据、导出 terms.json
  ├── 1.2 规则文档治理：把 2156 个 Markdown 按 CHM 目录结构挂载来源信息
  └── 1.3 数据质量验证：自动化检查 + 人工抽查

阶段 2：文档数据库 + 向量数据库
  ├── 2.1 文档分块（chunking）
  ├── 2.2 生成 Embedding（调用 Kimi/DeepSeek / Ollama）
  └── 2.3 写入本地 ChromaDB（每条 chunk 携带来源元数据）

阶段 3：Java 问答 Agent
  └── Spring Boot 3 + WebFlux，暴露 /api/chat 接口

阶段 4：微信小程序
  └── 原生微信小程序对接后端
```

## 4. 数据来源与溯源设计（核心）

### 4.1 元数据模型

每条规则 chunk 必须携带以下元数据：

| 字段 | 说明 |
|------|------|
| `chunk_id` | 全局唯一 ID |
| `source_file` | Markdown 原文件路径 |
| `source_book` | 来源规则书：CRB / APG / UM / UC 等 |
| `toc_path` | CHM 目录路径，如 `核心规则 Core Rulebook → 第九章 魔法 → 法术 → 火焰护盾` |
| `toc_level` | 目录层级 L1-L5 |
| `page_anchor` | 页内锚点（H1-H6 标题） |
| `content` | 规则正文 |
| `term_refs` | 该 chunk 中出现的术语列表 |

### 4.2 目录结构挂载

- 解析 `CHM_FULL_TOC_WITH_LEVELS.md`，建立 `toc_id → 路径` 映射表；
- 命名规律明确的文件（如 `Spell_火焰护盾.md`、`专长_顺势斩.md`）通过文件名或标题匹配到 TOC 节点；
- `page_*.md` 这类分页原文通过标题匹配或目录项的 Local 字段反查挂载。

### 4.3 回答时的来源呈现

API 返回的每个 source 必须包含规则原文，方便用户直接核验：

```json
{
  "answer": "不能免疫，但火焰护盾会让你获得寒冷抗力 10。",
  "sources": [
    {
      "book": "CRB",
      "tocPath": "核心规则 Core Rulebook → 第九章 魔法 → 法术 → 火焰护盾",
      "anchor": "火焰护盾 Fire Shield",
      "content": "火焰护盾能阻止寒冷，它让你获得寒冷抗力10。任何用近战攻击命中你的生物会受到1d6点火焰伤害……"
    }
  ]
}
```

## 5. 文档数据库与向量数据库设计

### 5.1 文档数据库

使用 **SQLite**：

- `documents` 表：chunk 全文 + 元数据；
- `terms` 表：术语表；
- `toc` 表：CHM 目录结构。

选型理由：本地开发零运维，后续可平滑迁移到 PostgreSQL。

### 5.2 向量数据库

使用 **ChromaDB 本地持久化模式**：

- 集合 `pf_rules` 存储 chunk 的 embedding；
- 每个 vector 的 metadata 携带 `chunk_id`、`source_book`、`toc_path`、`term_refs`；
- Java 后端通过 ChromaDB HTTP API 查询，用 `chunk_id` 回 SQLite 查完整内容。

### 5.3 Embedding 生成

- 用 Python 脚本批量调用 Kimi/DeepSeek Embedding API（或本地 Ollama）生成向量；
- Java 后端只做查询，不生成 Embedding。

## 6. Java 问答 Agent 设计

### 6.1 技术栈

- Spring Boot 3 + WebFlux（支持流式 SSE 输出）
- REST API 暴露 `/api/chat`

### 6.2 模块结构

```
pf-agent-server/
├── chat/
│   ├── ChatController.java
│   ├── ChatService.java
│   └── ChatRequest.java / ChatResponse.java
├── rag/
│   ├── EmbeddingClient.java
│   ├── VectorStoreClient.java
│   ├── DocumentRetriever.java
│   └── PromptBuilder.java
├── llm/
│   └── LlmClient.java
├── source/
│   └── TocService.java
└── config/
    └── AgentConfig.java
```

### 6.3 问答流程

```text
用户提问
  → EmbeddingClient 获取问题向量
  → VectorStoreClient 查 ChromaDB 返回 top-k chunk
  → DocumentRetriever 用 chunk_id 回 SQLite 查完整内容和来源
  → PromptBuilder 组装 system prompt + context + question
  → LlmClient 调 Kimi/DeepSeek 生成回答
  → 返回 { answer, sources[] }
```

### 6.4 Prompt 设计原则

- System：你是 PF 1e 规则助手，只基于提供的规则内容回答，不确定就直说；
- Context：每条检索到的规则片段都附带来源路径和原文；
- 要求 LLM 回答时区分"明确规则"和"推断内容"。

## 7. 微信小程序设计

### 7.1 页面结构

| 页面 | 功能 |
|------|------|
| `pages/index/index` | 问答主界面：输入框 + 对话列表 |
| `pages/source/source` | 来源详情页：展示完整目录路径和规则原文 |

### 7.2 数据流

```text
用户输入 → wx.request POST /api/chat
        → 渲染 answer + sources[]
        → 点击来源 → source 页展示 tocPath + content
```

### 7.3 体验要点

- 回答下方显示"回答基于以下规则来源"；
- 来源卡片可展开查看规则原文；
- 不确定时提示"未找到明确规则，请人工确认"。

## 8. 测试与验证策略

| 阶段 | 验证方式 |
|------|---------|
| 数据清洗 | 自动化检查：分类数量、术语重复、空推荐翻译、source 元数据完整性；人工抽查高频术语 |
| 向量检索 | 用已知问题测试 top-k 召回率，例如"火焰护盾免疫寒冷吗"应召回火焰护盾 chunk |
| Java 后端 | 单元测试 PromptBuilder、集成测试 /api/chat |
| 小程序 | 微信开发者工具走通问答闭环 |

## 9. 约束与风险

- 开发阶段不使用云托管；
- 术语表分类准确率当前较低，需优先修正；
- 部分 Markdown 源文件存在 OCR 乱码，清洗阶段需要处理或标记；
- 原 openclaw Agent 上下文丢失严重，本次设计以独立可核验的来源追踪为核心。

## 10. 下一步

进入实现计划阶段，按路线图逐步落地。
