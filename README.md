# PF Agent — Pathfinder 1e 规则问答 Agent

基于 **Pathfinder 1e（PF1e）规则书**的本地自部署问答 Agent：回答内容锚定规则原文、
带 `[#N]` 上标来源并可追溯到对应规则条目，供玩家/主持人在跑团中快速查证规则。

> ## ⚠️ 版权与使用声明（请先阅读）
>
> 本仓库代码采用 **Anti-996 License**（见 `LICENSE` / `LICENSE_EN`）。随库发布的
> **Pathfinder 1e 规则文本数据**涉及 Paizo Inc. 商标与版权，按 **Paizo 社区使用政策
> （CUP）** 非商业使用，且包含第三方社区中文翻译的著作权层——数据仅供**个人学习与
> 社区非商业用途**，版权归原作者所有，本仓库不主张其著作权。完整声明见 **`NOTICE.md`**。
> 本项目不对用户收取任何使用/访问费用。

[![CI — Agent 构建与测试](https://github.com/ytche/pf-agent/actions/workflows/agent-ci.yml/badge.svg)](https://github.com/ytche/pf-agent/actions/workflows/agent-ci.yml)
[![Docker — GHCR](https://github.com/ytche/pf-agent/actions/workflows/docker.yml/badge.svg)](https://github.com/ytche/pf-agent/actions/workflows/docker.yml)

[English Summary](#english-summary)

---

## 目录

- [这是什么](#这是什么)
- [功能特性](#功能特性)
- [架构](#架构)
- [目录结构](#目录结构)
- [快速开始](#快速开始)（Docker 一键 / 本地开发 两种路径）
- [配置说明](#配置说明)
- [评测与质量声明](#评测与质量声明)
- [贡献指引](#贡献指引)
- [许可与数据合规](#许可与数据合规)
- [Roadmap](#roadmap)

## 这是什么

PF Agent 是把 **Pathfinder 1e 中文规则书**结构化、向量化后，架在 LLM 之上的**规则检索问答**系统。
一期目标只有一个：**让规则查询可溯源**。任何回答都能指回规则原文的书籍、目录章节与具体条目，
不靠 LLM 记忆背书，不编造规则。

数据侧覆盖 8 大规则模块：法术、职业、专长、种族、背景特性、装备、技能、通用规则；
并内置 **26 个职业的环级法术清单**（`spell_lists.json`，源自 27 个官方职业法术列表页），
使「XX 职业 N 环法术有哪些」这类枚举提问走权威清单直查，而非元数据过滤抽样。

## 功能特性

- **上标溯源**：回答正文内联 `[#1] [#2]` 上标，对应来源列表（书、章节路径、原文摘录），可点击/对照追溯。
- **8 模块独立向量库** + 元数据过滤 + 语义检索 + 重排（title/aliases 加权、低信息 chunk 降权）。
- **法术清单直查工具**：26 职业环级清单，别名归一（如 诗人 → 吟游诗人），自带来源路径。
- **诚实缺省**：检索不到/数据缺口时工具引导报告缺口，不硬凑答案。
- **双通道 embedding（SP5）**：默认本地 Ollama `bge-m3`（开源自部署零配置）；可选托管云通道做主备降级。
- **会话记忆可选持久化**：默认内存；可选 PostgreSQL（JDBC + Flyway schema 管理）。
- **按 IP 限频 + 匿名会话轮次配额**：默认关闭，部署公开服务时按需开启。
- **前端**：内置单页聊天 UI（`static/index.html`），浏览器直达。

## 架构

问答运行时（LLM + 工具检索驱动，回答可溯源）：

```
浏览器/API  ──POST /api/chat──►  ChatController
                                   │
                          ChatService（记忆/限频/配额）
                                   │  编排
                                   ▼
                 ┌────────  DeepSeek LLM（deepseek-chat）────────┐
                 │           function-calling 工具循环             │
                 │  @Tool：vectorSearch / searchByMetadata        │
                 │         getSpellList / reportDataGap           │
                 └───────────────┬───────────────────────────────┘
                                 │
                 SearchService 跨 8 模块向量库检索 + 重排（SimpleVectorStore, JSON 持久化）
                 SourceCollector 汇总来源 ──► 正文上标 [#N] + 来源列表
```

数据管线（把规则书变成可检索的向量库）：

```
CHM 规则书 ──► pf_data/ 规则文本 Markdown（未整理 → <来源书> 归类）
     │   vectorizer pipeline（8 模块：法术/职业/专长/种族/背景特性/装备/技能/规则）
     ▼
chunks.jsonl（StandardChunk：中文标题/英文别名/来源书/CHM 目录路径/正文）
     │   应用首启导入（ChunkImporter → SimpleVectorStore）
     ▼
~/.pf_agent/vector_store_*.json（向量库持久化；存在即跳过导入）
```

> 嵌入向量使用 **BGE-M3（1024 维）**。换 embedding 模型 = 语义空间变化，**必须重建向量库**。

## 目录结构

```
pf_agent/
├── pf_agent/agent/            # Java 问答服务（Spring Boot 3.4 / Java 17 / Spring AI 1.0.0-M6）
│   ├── src/main/java/…/rag/   #   检索/工具/加载器（SearchService / RetrievalTools / *DataLoader）
│   ├── src/main/java/…/chat/  #   会话编排（ChatService / ChatController）
│   ├── src/main/java/…/memory/#   会话记忆（内存 / JDBC 可选）
│   ├── src/main/resources/     #   application.yml / Flyway 迁移 / static 前端
│   └── qa/                     #   评测集（pf_qa_items.json）与评测脚本（evaluate.py）
├── pf_data/                    # 规则数据与向量化（Python）
│   └── phase1/                 #   pf_rules_md_organized 规则文本 + vectorizer pipeline + 术语表
├── docs/handover/              # 批次交付/验收/方案文档（工程过程透明）
├── LICENSE / LICENSE_EN        # 代码许可（Anti-996 中/英）
└── NOTICE.md                   # 代码 + 数据许可边界声明
```

## 快速开始

两种路径任选。无论哪种，**都需要一份可查询的数据**（规则文本随库发布，但向量库/向量化
中间产物为免检出的可再生文件，不进 git）——见下方「准备数据」。

### 准备数据（二选一）

- **A. 下载预构建数据包（推荐，开箱即用）**：从本仓库 [Releases](https://github.com/ytche/pf-agent/releases)
  下载最新的 `pf-agent-data-*.zip`，内含 8 个模块**预构建向量库**（`vector_store_*.json`，
  已用 bge-m3 生成）。解压后放到本机向量库目录 `~/.pf_agent/`（Linux/macOS 为家目录下 `.pf_agent`；
  文件与本仓库各 `*DataLoader` 的 `pf.stores.*-file-path` 默认值一致）。应用启动时检测到
  向量库文件已存在即直接加载，**无需本地跑数据管线**。可选把 `spell_lists.json` 一并放入
  向量化产物目录以启用「职业法术清单」工具。
- **B. 自建向量库（需要本地跑数据管线）**：`pf_data/` 内规则文本 Markdown 已随库发布，
  贡献者可运行各模块 vectorizer pipeline 重新生成 `chunks.jsonl`。之后首次启动应用时，
  `*DataLoader` 检测到向量库缺失会**自动从 chunks 导入构建**（数百 MB，耗时较长，仅首次）。

> 预构建向量库由 bge-m3 生成；若改用托管 embedding（`pf.embedding.primary=cloud`）做查询，
> 且向量库为同一 bge-m3 模型时可直接复用（见 `application.yml` 模型一致性约束注释）。

### 路径一：Docker Compose 一键启动（推荐）

前置：Docker。然后：

```bash
git clone https://github.com/ytche/pf-agent.git
cd pf-agent

# 1) 准备数据：下载预构建数据包 → 解压到 ./data/（compose 会挂载为 ~/.pf_agent）
#    ./data/ 内应含 vector_store_*.json（与「准备数据 A」同构）

# 2) 配置：复制 .env.example → .env，填入 DEEPSEEK_PF_API（DeepSeek Chat API key）
cp .env.example .env

# 3) 启动（首次会自动拉 bge-m3 模型，需下载 ~1.2GB，视网速等待）
docker compose up -d
```

启动后：

- 应用：<http://localhost:8080/>（内置聊天 UI）
- 健康检查：`curl http://localhost:8080/api/health`
- Ollama（embedding）：Compose 附带；默认 `http://localhost:11434`

要启用 PostgreSQL 会话持久化：`docker compose --profile pg up -d`，并在 `.env` 填 PG 连接
（见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)）。

### 路径二：本地开发

前置：**Java 17**（`mvn` 用 `java.version=17`）、**Ollama**（已 `ollama pull bge-m3`）、
数据已就绪（`~/.pf_agent/` 有向量库，或本地已生成 `chunks.jsonl`）。

```bash
cd pf_agent/agent

# 配置（env 或 export，见配置说明）
export DEEPSEEK_PF_API=sk-xxxx          # DeepSeek Chat key

# 启动（默认连 http://localhost:11434 的 Ollama bge-m3）
mvn spring-boot:run
```

> 首启无向量库时会从 `chunks.jsonl` 自动构建（需 Ollama 可用；数百 MB、耗时较长）。
> 复用 `~/.pf_agent` 预构建数据可跳过。

### 环境变量速览

| 变量 | 必填 | 说明 |
|---|---|---|
| `DEEPSEEK_PF_API` | ✅ | DeepSeek Chat API key（LLM） |
| `PF_EMBEDDING_CLOUD_API_KEY` | 仅 cloud 通道 | 托管 bge-m3 API key（`pf.embedding.primary=cloud` 或开启 fallback 时） |
| `PF_AGENT_PG_*` | 仅 jdbc 模式 | PostgreSQL 连接（启用 `pf.chat.memory=jdbc` 时） |

完整环境变量 + 三个已知配置坑见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

## 配置说明

所有配置集中在 `pf_agent/agent/src/main/resources/application.yml`（环境变量经 Spring
relaxed binding 覆盖，如 `pf.rate-limit.enabled` ↔ `PF_RATE_LIMIT_ENABLED`）。常用项：

| 配置键 | 默认 | 说明 |
|---|---|---|
| `spring.ai.openai.api-key` | `${DEEPSEEK_PF_API:…}` | LLM key（DeepSeek） |
| `spring.ai.ollama.base-url` | `http://localhost:11434` | Ollama 地址（embedding） |
| `server.port` | `8080` | HTTP 端口 |
| `pf.chat.memory` | `memory` | `memory`=内存 / `jdbc`=PostgreSQL 持久化 |
| `pf.rate-limit.enabled` | `false` | 按 IP 限频开关（`per-minute` 上限） |
| `pf.quota.enabled` | `false` | 匿名会话轮次配额开关 |
| `pf.embedding.primary` | `ollama` | 查询 embedding 通道：`ollama` / `cloud` |
| `pf.embedding.fallback-enabled` | `false` | 主通道失败降级另一通道（`primary=cloud` 时建议 `true`） |
| `pf.chunks.*-path` | `../../pf_data/…` | 各模块 chunks.jsonl 路径（首启建库用） |
| `pf.stores.*-file-path` | `~/.pf_agent/…` | 各模块向量库持久化路径 |
| `pf.search.*` | 见 yml | 检索参数：top-k / 阈值 / 重排加权 / 截断护栏等 |

> 多段虚线与含副作用的配置（如 `spring.ai.openai.chat.options`）经环境变量覆盖行为不一，
> 具体见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)「三个已知坑」。

## 评测与质量声明

一期以「可溯源、诚实、结构清晰」为质量口径，用真实规则问题做端到端评测（`qa/`）：

- **评测集**：59 题规则问答（53 题活跃计入，6 题人工排除）；维度覆盖事实点查 / 全量枚举 /
  应用计算 / 交叉判定 / 比较对比 / 数值最优解。
- **运行**：`cd pf_agent/agent/qa && python3 evaluate.py`（对运行中的应用做 HTTP 评测，
  可选 `--judge` 用 LLM 判定开放性维度）。
- **发布基线**：溯源命中 ≥52/53、诚实 ≥50/53、结构分 ≥2.89（kimi-k3 验收口径，见
  `docs/handover/`）。

质量闸口（CI）：Java 侧 `mvn test`（247 项单测全绿）；数据侧有独立的规则数据质量闸口
（见 `.github/workflows/ci.yml`）。评测题与检索/prompt 改动共版本演进——每次影响回答行为的
改动需全量重跑评测且不回退。

## 贡献指引

欢迎 Issue 与 PR。请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)：含工程红线摘要
（Java 规范 / 测试完整性 / 数据不可变基线）、提交流程、评测要求与 PR 模板。

## 许可与数据合规

- **代码**（`pf_agent/agent/` Java 工程与数据侧可执行脚本）：**Anti-996 License v1.0**——
  见 [LICENSE](LICENSE)（中文）/ [LICENSE_EN](LICENSE_EN)（英文）。
- **规则数据**（`pf_data/` 规则文本等）：受 **Paizo Community Use Policy（CUP）** 约束且含
  第三方社区中文翻译著作权层，仅供个人学习与社区非商业使用；本仓库不主张其著作权，
  详见 [NOTICE.md](NOTICE.md)。如您是相关权利人并希望移除对应内容，请发 Issue（标题前缀 `[版权]`）。

## Roadmap

- 一期（进行中/已收尾）：规则问答可溯源 —— 数据向量化 8 模块 + Agent 检索联调 + 开源化工程。
- 二期（规划）：车卡辅助 + Build 建议（术语关联关系、职业子系统组合推理）。
- 远期方向：向量库进 PostgreSQL（统一存储，替换 JSON 文件）；微服务拆分评估。

---

## English Summary

**PF Agent** is a self-hosted Pathfinder 1e rules Q&A agent. Answers are grounded in the
rulebook text and carry `[#N]` source markers that link back to the exact book / chapter / entry,
so players can verify every rule claim instead of trusting LLM recall. It covers 8 rule modules
(spells, classes, feats, races, traits, equipment, skills, generic rules) plus authoritative
per-class spell lists. Embeddings use **BGE-M3** (local Ollama by default, optional cloud channel).
Run via Docker Compose or local Java 17 + Ollama; a prebuilt vector-store package is published
under Releases for zero-pipeline setup.

**License**: code is [Anti-996](LICENSE_EN) licensed. The bundled Pathfinder 1e rules text is
distributed under Paizo's Community Use Policy for non-commercial community use (see
[NOTICE.md](NOTICE.md)); it is **not** endorsed by Paizo Inc. This project charges no fee for use.
