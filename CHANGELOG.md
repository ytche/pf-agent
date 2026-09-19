# CHANGELOG

本项目遵循语义化版本。公开仓（github.com/ytche/pf-agent）为快照式发布，历史不连通，版本变更以本文件为准。

## [0.2.0] - 2026-09-19

自 0.1.0（一期公开基线，2026-09-14）以来的变更。

### 新增

- **账户与持久化（SP7）**：注册/登录（JWT）+ PostgreSQL 默认持久化，会话跨重启保留；匿名配额与限频保持可配
- **检索工具增强（SP8）**：
  - `getEntryById`：按条目 ID 取完整原文（解决长条目截断漏规则）
  - `searchByMetadata` 增强：参数对象化，支持 or 组合、范围比较、排序与分页
  - `listDataGaps`：数据缺口看板，避免重复报告
  - 条目引用链 Layer 0：`resolveEntry` / `getEntryLinks`，全模块条目名索引与结构化引用链
  - `keywordSearch` v1：title/alias 子串匹配，补语义检索的精确名词盲区
- **J4 book 过滤落地**：`BookFilter` 全局来源书过滤（黑/白名单双模式，配置驱动，默认黑名单剔 `?`）
- **数据产物可复现构建链**：`build_manifest.json` + `vectorizer/build.py`（status/build/check/--force）+ `build_state.json` 指纹入库，数据产物可审计可复现

### 修复

- **数据治理（D1+KN226+trait）**：专长/规则/背景特性三模块 book 字段中文脏值清零；规则模块「怪物」843 条来源书失真修复（逐文件归书 B1/CRB/MC）；KN229 英文书名订正；三向量库全量重灌对齐
- **健壮性**：embedding 客户端增加连接/读超时（`pf.embedding.connect-timeout`/`read-timeout`），Ollama 僵死时超时降级而非悬挂拖垮连接池（AKN-010）；Ollama embedding 上下文/批大小放开至 8192（AKN-012，修复稠密中文长 chunk 400 报错）

### 质量基线

- 评测集 53/53 满分（溯源/诚实/结构三指标）；Java 单测 400 全绿；数据侧 pytest 1400+ 全绿

## [0.1.0] - 2026-09-14

一期公开基线（SP1~SP6）：规则问答 Agent 主链路（8 模块向量库检索 + 溯源引用）、会话持久化基础设施、限频与匿名配额、职业法术列表预整理、论文式上标来源标注、embedding 双通道（本地 Ollama / 云 API）、开源化工程（LICENSE/NOTICE/模板）。
