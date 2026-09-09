# SP5 · embedding 双通道（云 API 主 + Ollama 兜底，配置化）

- 日期：2026-09-07
- 设计 / 验收：kimi-k3
- 执行：外部执行 Agent
- 关联：《微服务拆分与开源单体计划_决策记录_20260905.md》§三 SP5 行 + §关键技术约束（**模型一致性：只能托管版 bge-m3，换模型=重建 600MB 向量库，禁止**）
- 状态：**已拍板（2026-09-07）**，交接执行 Agent 开工

---

## 0. 执行指引（给执行 Agent）

- **分支**：从 `dev/pf-agent` 切 `feat/sp5-embedding-dual`；每 T 独立 commit（§6）；不自行合并，交付 k3 验收、用户拍板合并。
- **工程结构**：Java 模块根 `pf_agent/agent/`。红线见仓库根 `CLAUDE.md`：Java camelCase 无中文、**方法按访问级别排序（静态同级优先、@Test/@PostConstruct 参与排序）**、`@Autowired` 字段注入；交付文档放仓库根 `docs/handover/`。
- **常用命令**：
  - Java 单测：`cd pf_agent/agent && mvn test`——基线 **227 全绿**（2026-09-07 SP4 验收亲跑）。
  - 启动应用：`mvn spring-boot:run`（默认内存模式，需 DeepSeek key + Ollama bge-m3 + 本地向量库文件 `~/.pf_agent/vector_store_*.json` 已存在）。
  - 检索评测：`cd pf_agent/agent/qa && python3 evaluate.py --report-dir ./out_sp5`——基线口径：溯源 ≥52/53、诚实 ≥50/53（easy-2 抖动 + medium-0 gap 邻近抖动已登记）、结构 2.89~2.96（剔除基础设施 500 后 ≥2.90）。
- **交付物**：代码 + 交付文档 `docs/handover/KIMI_K3_SP5批次交付_<日期>.md`（任务矩阵 / 测试清单 / 真机证据 / 对照 §6 自查附证据 / 遗留披露）。

## 1. 背景与定位

开源单体计划第 5 子项目。当前查询向量化**单通道硬绑本地 Ollama**：`VectorStoreConfig` 8 个 store 全部 `@Qualifier("ollamaEmbeddingModel")`（bge-m3 @ localhost:11434）。问题：

- 本地 Ollama 是**单点**：进程挂掉/机器没 GPU → 检索全废（向量库文件还在，但查询无法 embedding）。
- 托管部署（微服务版远期目标）不想扛 Ollama 运维：云 embedding API 更省心。
- 决策记录已拍板约束：**模型必须仍是 bge-m3**（向量库由它构建），云通道只能选托管版 bge-m3（如硅基流动 `BAAI/bge-m3`，OpenAI 兼容 `/v1/embeddings`，1024 维与本地一致）。

现状关键事实（全部亲读核实）：

- 工程有 openai starter（DeepSeek chat）+ ollama starter 两个 `EmbeddingModel` Bean，VectorStoreConfig 靠 `@Qualifier("ollamaEmbeddingModel")` 选本地。
- 8 个 store 的 embedding 统一过 `TruncatingEmbeddingModel`（5000 字符截断防超限）。
- 向量库文件已存在时启动只做加载（DataLoader 跳过导入），**运行期 embedding 仅发生在 vectorSearch 查询侧**——双通道的日常负载就是每问几次查询向量。
- `spring.ai.retry.max-attempts=1` 已关 LLM 重试（超时不放大），fallback 语义与此兼容。

## 2. 目标 / 非目标

**目标**：
1. embedding 通道配置化：`pf.embedding.primary=ollama（默认）| cloud`，默认配置**零行为变化**（开源自部署无感）。
2. 云通道：托管 bge-m3（OpenAI 兼容 embeddings API），独立 base-url/api-key/model 配置（不复用 DeepSeek 的 `spring.ai.openai.*`）。
3. 兜底：`pf.embedding.fallback-enabled=true` 时主通道调用失败（异常/超时）→ 降级另一通道，记 WARN；双通道同挂才抛错。
4. 启动维度自检：cloud 参与（主或备）时启动探测一次 embedding 并断言维度 = 1024（与本地 bge-m3 向量库对齐），不匹配 fail-fast 防「检索全废但服务照起」。
5. 默认模式回归不回退（单测 + 评测基线口径）。

**非目标**：
- **不换模型、不重建向量库、不动数据侧 vectorizer**（Python 侧 embedding 不在本批）。
- 不做多 key 轮询/负载均衡/熔断持久化（fallback 是逐次调用降级，不做断路器状态）。
- 不动 TruncatingEmbeddingModel、不动 8 store 结构、不动检索逻辑。
- 不做运行时热切换（配置即重启生效）。
- 首次建库（向量库文件缺失时的全量 embedding）走同一通道链，但**不为建库做批量优化**（登记已知项：SimpleVectorStore 逐条 embed，云端首建慢——建议建库仍在本地 Ollama 做）。

## 3. 设计决策（D1~D7）

- **D1 通道抽象**：新 `EmbeddingConfig` 产出单一组合 Bean `queryEmbeddingModel`（`EmbeddingModel` 类型），VectorStoreConfig 的 8 处 `@Qualifier("ollamaEmbeddingModel")` 全部改 `@Qualifier("queryEmbeddingModel")`。组合逻辑对消费方完全透明。
- **D2 通道链组装**：
  - `primary=ollama`（默认）→ 直接暴露 `ollamaEmbeddingModel`；`fallback-enabled=true` 且 cloud 已配置 → 包 `FallbackEmbeddingModel(ollama, cloud)`。
  - `primary=cloud` → 主 `cloudEmbeddingModel`；`fallback-enabled=true`（默认 true 当 primary=cloud）→ 包 `FallbackEmbeddingModel(cloud, ollama)`。
  - `fallback-enabled=false` → 裸主通道。
- **D3 云通道装配**：手工构造 `OpenAiEmbeddingModel(new OpenAiApi(cloudBaseUrl, cloudApiKey), MetadataMode.EMBED, OpenAiEmbeddingOptions(model=cloudModel), retryTemplate)`——独立于 `spring.ai.openai.*`（那是 DeepSeek chat 的配置，base-url 不同）。配置段：
  ```yaml
  pf:
    embedding:
      primary: ollama            # ollama（默认，开源自部署零配置）| cloud
      fallback-enabled: false    # 主通道失败时降级另一通道；primary=cloud 时建议 true
      cloud:
        base-url: https://api.siliconflow.cn   # 托管 bge-m3 服务（OpenAI 兼容）
        api-key: ${PF_EMBEDDING_CLOUD_API_KEY:}  # 只经环境变量注入，严禁入库
        model: BAAI/bge-m3
  ```
  cloud 参与（主或备）而 api-key 为空 → 启动 fail-fast 报清晰错误（不静默回退）。
- **D4 FallbackEmbeddingModel**：实现 `EmbeddingModel` 接口（`embed(Document)`/`embed(List<String>)`/`embed(float[])` 等全部委托方法，逐方法 try primary catch → WARN + fallback；主成功零开销直传）。WARN 含通道名与异常摘要（不含 key）。**逐次调用降级**：不记状态、不做熔断——主通道恢复后自动回主（下次调用先试主）。`dimensions()` 委托主通道。
- **D5 启动维度自检**：`@PostConstruct`（或 ApplicationRunner）在 cloud 参与时执行一次 `embed("维度探测")`，断言返回维度 == 1024（本地 bge-m3 库维度，常量注明出处）；不符 → 启动失败并打印「云通道模型维度与本地向量库不一致，请确认 model=BAAI/bge-m3」。primary=ollama 且无 cloud fallback → 跳过（默认零网络行为变化）。
- **D6 配置默认值矩阵**：

  | primary | fallback-enabled | cloud api-key | 行为 |
  |---|---|---|---|
  | ollama（默认） | false（默认） | 不需要 | **现状逐字不变**（无 cloud bean、无自检、无网络新增） |
  | ollama | true | 必需 | 主 Ollama、挂时降 cloud；启动自检 cloud |
  | cloud | true（默认） | 必需 | 主 cloud、挂时降 Ollama；启动自检 cloud |
  | cloud | false | 必需 | 裸 cloud（托管极简部署）；启动自检 cloud |

- **D7 观测**：启动日志打印生效通道链（如 `embedding 通道链: primary=cloud, fallback=ollama`）；fallback 每次触发一条 WARN。不进 metrics（本批无观测设施先例可沿）。

## 4. 任务分解（T1~T4）

| # | 任务 | 产出 | 依赖 |
|---|---|---|---|
| T1 | FallbackEmbeddingModel + EmbeddingConfig 通道链组装（D1/D2/D4/D6/D7）+ yml 配置段 | config/EmbeddingConfig、config/FallbackEmbeddingModel、application.yml + 单测（主成功/主失败降级/双失败抛错/降级 WARN/默认 ollama 零装配变化） | — |
| T2 | 云通道装配 + api-key 校验 + 启动维度自检（D3/D5） | EmbeddingConfig 扩展 + 单测（stub OpenAiApi 或 mock EmbeddingModel 验证维度断言通过/失败路径、key 缺失 fail-fast） | T1 |
| T3 | VectorStoreConfig 8 处 Qualifier 切换 + 全量回归 | VectorStoreConfig + 既有单测全绿 | T1 |
| T4 | 真机验证（§6 V4/V5）+ 交付文档 | 交付文档 | T1~T3 |

## 5. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 云 bge-m3 与本地向量数值差异导致检索质量漂移 | 同模型权重，余弦兼容（差异在浮点精度级）；D5 维度自检 + V5 真机检索比对（同问题两通道结果一致性抽查） |
| cloud api-key 误入库 | D3 强制 env 占位符；验收红线 grep |
| 默认配置行为变化 | D6 矩阵锁定「ollama + fallback=false = 现状」；V2 专项验证（启动日志比对 + 无 cloud bean） |
| 三个 EmbeddingModel Bean 注入歧义 | D1 单一 `queryEmbeddingModel` 组合 Bean，VectorStoreConfig 只认它；openai starter 自带 Bean 不动 |
| fallback 掩盖主通道长期故障 | D7 每次降级 WARN 留痕；qa 可 grep 日志；本批不做告警（无设施） |
| 云通道超时拖慢问答 | Spring AI retry 已关（max-attempts=1）；fallback 仅在异常后触发；超时阈值用 Spring 默认（登记：如需自定义 timeout 后续批次加配置） |

## 6. 验收清单（V1~V6，k3 亲验口径）

| # | 验证项 | 通过标准 |
|---|---|---|
| V1 | 单测 | `mvn test` 全绿；基线 227 + 新增（fallback 三分支/维度断言/key 校验/默认装配不变） |
| V2 | 默认零变化 | 默认 yml 启动：日志无 cloud 装配、无维度自检、通道链日志为 primary=ollama；向量库加载与检索行为同前 |
| V3 | 改动面 | diff 仅：EmbeddingConfig/FallbackEmbeddingModel（新）+ VectorStoreConfig（Qualifier 切换）+ application.yml + 测试 + 交付文档；检索/工具/Chat 零 diff |
| V4 | 默认模式评测 | 53 题复跑：溯源 ≥52/53、诚实 ≥50/53、结构 ≥2.89；波动题逐题归因（easy-2/medium-0 已登记抖动口径） |
| V5 | 双通道真机 | 本地 stub HTTP server（OpenAI 兼容 /v1/embeddings，返回固定 1024 维向量）配 `primary=cloud` 启动：① 维度自检通过；② vectorSearch 请求落到 stub（stub 侧有请求记录）；③ kill stub 后下一问走 Ollama 兜底（WARN 日志 + 正常作答）；④ api-key 缺失启动 fail-fast 报清晰错误。**用户若有真实硅基流动 key，加跑一次真实 cloud 主通道问答+同问题双通道结果一致性抽查** |
| V6 | 红线 | camelCase 无中文（注释除外）、方法排序、字段注入、每 T 独立 commit、api-key 仅 env 注入（grep 全库无 key）、交付文档如实披露未跑项 |

## 7. 与既有批次的接口

- SP1（PG）：零交集。
- SP6（开源化）：本批配置段将进入 SP6 的部署文档（自部署默认 ollama、托管开 cloud）；SP5 先行定稿是决策记录要求。
- 远期向量库进 DB（决策记录后话）：embedding 通道链在 VectorStore 之下，与存储层演进正交，不冲突。
