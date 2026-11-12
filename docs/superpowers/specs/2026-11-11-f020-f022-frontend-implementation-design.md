# F-020 + F-022 前端改版与引用展示实施 Spec

- 日期：2026-11-11
- 状态：✅ 已实施并合并（2026-11-11；会话后端 `ed057ce`，前端 `43cad9f` + 复审修复 `1c47cd8`/`d2fea5a`，契约补缺 `d71b32c`；合并 `29d99ff`/`b8c3f4a`/`c85f344`）
- 实施计划：`docs/superpowers/plans/2026-11-11-phase1-five-specs-implementation.md`（Task 9/10）
- 实施证据：`docs/test-reports/测试报告_一期五项Spec收口_20261111.md`；后端/前端/契约三轮评审 final clean（`ed057ce`/`d2fea5a`/`d71b32c`）
- 实施结果：Vue 3 SPA + 统一 ConversationStore + V7 引用快照；Vitest 40、Playwright 12（桌面/手机）、全栈 E2E（真实 PG + 打桩 ChatModel）通过；匿名认领、410、重生成与来源默认 3 张/展开/上标定位均验证
- 关联：F（功能想法）020、F（功能想法）022、F（功能想法）014、F（功能想法）015、F（功能想法）026
- 交互基线：`docs/superpowers/specs/2026-11-03-f020-frontend-final-design.md`
- 主要读者：后续负责前端、会话后端、数据库迁移、CI、测试与验收的实施者

## 1. 文档关系与范围

既有 F-020 终态设计已经确认页面形态、组件边界、会话与账号规则、引用展示、目标接口和九组必过场景。本 Spec 是它的实施层补充，**不重新定义 UI，也不形成第二份交互规范**。

本 Spec 补齐：

- Vue 工程与 Spring Boot/CI 的构建关系；
- 统一 ConversationStore 与两种运行模式；
- V7 数据迁移和引用快照写入；
- 会话归属、匿名认领、删除竞态；
- 同会话并发控制的明确边界；
- 实施分段与交付验收。

F-022 的默认 3 张来源卡片、展开全部和上标定位并入本批，不单独建设另一套引用页面。

## 2. 目标与非目标

### 2.1 目标

1. 以独立 Vue 3 + TypeScript 工程替换旧单文件问答页。
2. 统一会话、模型历史、消息与引用快照的存储语义。
3. 支持匿名本机历史、登录认领和账号跨设备恢复。
4. 保证引用快照与当轮响应一致，旧数据可降级展示。
5. 保证删除后晚到结果不复活，并明确并发控制边界。
6. 建立可复现的 npm → Maven 构建与测试链。

### 2.2 非目标

既有终态设计的“不做”清单继续有效。本实施层另外明确：

- 不引入 Maven Node 插件，不提交 dist 产物；
- 不保留旧单文件页面作为第二套回退界面；
- 不新增 JVM 或数据库同会话请求锁；
- 不签发匿名专用令牌，匿名会话使用 UUID 能力访问；
- 不实现管理后台内部页面；
- 不扩展 `/api/chat/feedback` 的会话归属校验；保留现状并在交接中登记，不借本批改变反馈契约；
- 不新增聊天正文流式输出、停止生成或实时协同；
- 不把 F-026 的 V6 事件表并入本批迁移。

## 3. 已确认的实施决策

| 决策点 | 结论 |
|---|---|
| 前端工程 | `pf_agent/agent/frontend/`，Vue 3 + TypeScript + Vite + Pinia |
| 构建顺序 | npm ci → 前端测试/构建 → Maven package/test |
| 静态产物 | 输出 `src/main/resources/static/dist/`，gitignored |
| 存储 | 统一 ConversationStore，JDBC/内存各一实现 |
| 引用快照 | 保存 cited-only 过滤与编号重映射后的完整响应来源 |
| 匿名访问 | UUID 能力访问；认领后仅所属账号访问 |
| 删除竞态 | 晚到结果丢弃并返回 `410 conversation_deleted`；从未存在用 404 |
| 同会话并发 | 不加请求锁；重生成按预期消息条件替换，冲突返回 409 |
| 数据库迁移 | V7，接在 F-026 的 V6 query_gate_event 之后 |
| 重新生成 | 替换最后助手消息，不追加用户消息、不增加对话轮数 |
| 配额 | 独立 generation_attempts 统计普通问答与重生成，复用匿名配额 |
| 删号 | owner_user_id ON DELETE SET NULL；会话转匿名并接受 UUID 访问风险 |
| PG 测试 | 新增 Testcontainers PostgreSQL 测试依赖，真实验证 Flyway/JSONB/FK |
| 浏览器测试 | CI 用打桩 ChatModel；真实 Agent 保留上线前手动冒烟 |
| 文档关系 | 2026-11-03 终态设计为唯一 UI 基线，本文只补实施层 |

## 4. 前端工程与交付

### 4.1 工程结构

新建 `pf_agent/agent/frontend/`：

- `package.json` 与 lockfile 固定依赖版本；
- Vite + Vue 3 + TypeScript + Pinia；
- Vitest 与 Playwright；
- marked + DOMPurify；
- 自定义轻量 UI 组件，不引入整套组件库；
- npm scripts 至少包含 dev、build、test、test:e2e。

既有组件边界 AppShell、HistoryDrawer、ConversationView、MessageList/MessageItem、SourceCards、Composer、FeedbackForm、AuthDialog 按终态设计实现。

### 4.2 构建与静态服务

- Vite 输出到 `pf_agent/agent/src/main/resources/static/dist/`。
- dist 和 node_modules 均 gitignored，不提交生成物。
- Spring 将 `classpath:/static/dist/` 配置为静态资源根，并通过根路径 controller 显式 forward 到 `dist/index.html`，不能只依赖目录配置假设 `/` 自动命中。
- 前端使用 hash 路由，刷新非根页面仍回到 `/` 的 SPA，不新增 history 路由 fallback 规则。
- 新 SPA 验收替换旧 `src/main/resources/static/index.html`，不保留第二套页面。
- 不再从 CDN 加载 marked 或其他运行依赖，新页面在无 CDN 环境下可独立工作。

### 4.3 开发与 CI

本地开发：

- Vite 开发服务器代理 `/api` 到当前后端；
- 后端静态服务模式要求先执行前端构建，README/DEPLOYMENT 写明命令顺序。

CI/交付：

```text
npm ci → Vitest/前端构建 → Playwright 所需准备 → Maven package/test → 浏览器端到端
```

不通过 Maven 插件下载 Node。CI 使用 setup-node、npm lockfile 和项目已验证的 Node 版本范围。

## 5. 统一 ConversationStore

### 5.1 职责

新增 `ConversationStore` 作为会话事实源，统一负责：

- 创建和读取会话；
- 账号会话分页与匿名 lookup；
- 重命名、置顶、永久删除；
- 匿名会话认领；
- 读取模型历史；
- 追加完整问答及引用快照；
- 替换最后一条助手消息；
- 20 轮裁剪与轮数统计。

JDBC 与内存各实现一次。内存模式提供同一套接口和快照，但重启后清空；登录、认领和跨设备能力按终态设计不可用。

### 5.2 与 ChatMemory 的关系

- ChatMemory 作为模型历史读取和既有接口的兼容适配，底层复用 ConversationStore。
- ChatService 的追加问答与重新生成通过 ConversationStore 完成。
- 不允许 ChatMemory 写消息、另一个快照服务再独立写同一助手消息。
- 现有 JdbcChatMemory 行为如需保留兼容入口，必须委托统一 Store，不形成第二份写入逻辑。
- 必须删除现有 `JdbcChatMemory.doAdd` 的 `orElseGet(自动创建父会话)` 分支；所有追加/替换写入先显式检查父行，缺失时返回删除/不存在结果，禁止任何兼容入口复活会话。
- 内存 Store 同时提供 ChatMemory 兼容适配和 generation_attempts 计数，AnonymousQuotaService 两种模式都改读统一 Store，不能因替换 InMemoryChatMemory 使配额失效。

### 5.3 问答写入

1. `/api/chat` 在调用模型前确保父会话存在。
2. 模型问答失败不写不完整问答，不污染模型上下文。
3. 首轮成功后才让会话进入历史列表；账号列表和匿名 lookup 都以 `message_rounds > 0` 为可见条件，空父行保留但不可见。
4. 助手消息保存 cited-only 过滤与编号重映射后的完整响应 sources 和 gapReported。
5. 引用快照包含当轮响应中的编号、书名、目录和原文快照，不是过滤前的全部检索来源。
6. 裁剪旧轮时同时删除其引用快照。

## 6. V7 数据迁移

F-026 先使用 V6 创建 query_gate_event，本项固定使用 V7。

### 6.1 chat_conversation

新增：

- `title`：可空；
- `pinned`：非空布尔，默认 false；
- `owner_user_id`：可空，`REFERENCES user_account(id) ON DELETE SET NULL`；删号后会话转为匿名，凭 UUID 可访问，该隐私影响为用户已明确接受的决策；
- `generation_attempts`：非空整数，默认 0，累计普通问答与重新生成尝试，供匿名配额使用；它不等于对话轮数；
- 支撑账号归属、置顶和最近活跃排序的索引。

既有行的 title/owner 允许为空，pinned 使用默认值；generation_attempts 在增加默认 0 后，立即执行 `UPDATE chat_conversation SET generation_attempts = total_rounds WHERE total_rounds > 0` 回填既有累计问答数，避免旧匿名会话升级后配额被重置。历史重新生成无法追溯，不额外虚构次数。

### 6.2 chat_message

新增：

- `sources`：可空 JSONB，保存助手消息的完整响应来源快照；
- `gap_reported`：非空布尔，默认 false。

旧消息 sources 为 null 时，API 和前端显示“历史来源未保存”，不伪造来源。

### 6.3 迁移验收

- 新增 Testcontainers PostgreSQL 测试依赖，使用 PostgreSQL 16 在 JUnit 本地/CI 自动启动真实数据库；
- 从既有 V5 数据升级后，再应用 F-026 V6 和本项 V7；
- 既有消息和轮数不丢失；
- 新字段默认值、JSONB 读写、外键与删号 SET NULL 行为生效；
- 实体通过 `ddl-auto=validate`；
- 内存模式不触发数据库迁移。

## 7. 问答、重新生成与删除竞态

### 7.1 重新生成

- 只允许最后一轮。
- 读取最后一轮用户问题，模型历史不包含即将被替换的旧助手回答。
- 成功后替换最后一条助手消息的正文、sources、gapReported 和完成时间，保持原消息 ID 和位置。
- 不追加用户消息，不增加 messageRounds/totalRounds。
- 普通问答与重新生成在实际调用模型前都增加 `generation_attempts`，并先通过同一匿名配额检查；模型调用已发生后即使失败也保留本次尝试计数，避免失败重试绕过成本护栏。
- 替换必须带读到的 `expectedLastSeq + role=assistant` 条件：父会话已删除返回 410；期间出现新消息或最后消息已变化返回 `409 conversation_changed`，不得覆盖他人新提交的内容。
- 失败保留旧回答与旧来源，不写入新内容。
- 消息 DTO 暴露稳定的 `id` 与完成时间；重新生成响应返回同一消息 ID。

### 7.2 同会话并发边界

本批只在 Pinia/Composer 层禁止同会话并发，不增加 JVM 或数据库请求锁。

因此：

- 直接 API 或多设备并发可能产生后提交覆盖先提交的结果；
- 本批不承诺跨实例互斥、请求租约或崩溃恢复；
- 重新生成通过 expectedLastSeq 条件更新防止覆盖期间新增的消息，这属于终态校验，不是请求锁；
- 数据库仍需保证消息结构合法和删除后不复活；
- 该限制必须在验收和交接文档中明确，不能宣称服务端已禁止所有并发。

### 7.3 删除与晚到结果

- 删除是硬删除，立即以删除为终态。
- 追加或替换时发现父会话不存在，不得自动重建。
- 请求开始时存在、完成后发现已删除的晚到结果被丢弃并记录告警，返回 `410 conversation_deleted`。
- 从未存在或 UUID 错误的普通读取返回 `404 conversation_not_found`，不把所有 404 都写成已删除。
- 前端收到 410 后清理请求状态，不展示为新回答，不重新加入历史列表。
- 删除不需要等待模型停止，本批仍不提供停止生成。

## 8. 认证、归属与匿名认领

### 8.1 共享身份解析与拦截范围

抽取共享认证身份解析组件，供会话接口和 `/api/chat` 使用：

- 有效 Bearer JWT 得到当前用户；
- 非法、过期或结构错误的 token 返回 401；
- 不得把非法 token 静默降级为匿名；
- 既有 AuthController 行为保持兼容，可复用同一解析组件。

`pf.auth.enabled=true` 时也允许完全没有 Authorization 的匿名问答，这是用户明确确认的安全语义调整，不再代表“开启认证即强制登录”。AuthInterceptor 对无 token 请求标记匿名并放行，对非法 token 仍返回 401；IP 限频和匿名配额继续生效。

`WebConfig` 将 `/api/conversations/**` 纳入 AuthInterceptor；`/api/chat` 与 `/api/conversations/**` 均纳入既有限频范围。重新生成在调用模型前复用匿名配额检查，不得绕过。

### 8.2 访问规则

- 匿名请求凭不可猜测 UUID 读取和操作 owner 为空的会话。
- 已登录用户访问 owner 为空的会话返回 403，必须通过本机显式认领流程绑定，不在读取时自动转移归属。
- 匿名 lookup 只返回 owner 仍为空的会话。
- 有 owner 的会话仅所属账号可读取、修改、问答、重新生成或删除；匿名用户或其他账号访问时统一返回 404，避免泄露该 UUID 已存在且被认领。
- 账号会话列表必须登录；匿名历史使用 lookup。
- 登录用户新建问答自动写入 owner。
- 现有匿名 `/api/chat` 与反馈接口保持兼容。

### 8.3 认领

- 认领必须登录。
- 只把 owner 为空的会话写给当前账号。
- 同一账号重复认领幂等。
- 其他账号已认领的会话不得覆盖，结果中明确报告未认领项。
- 认领失败保留本机 ID，允许重试。
- 退出登录隐藏账号历史并清除本机账号缓存，云端数据保留。

## 9. 前端状态与引用展示

- Pinia 集中管理会话、消息、分页、请求、未读、账号、匿名 ID 和认领。
- 本机只持久化必要的匿名会话 ID、认证状态和终态设计允许的客户端状态；退出时清除账号消息缓存。
- 后台请求状态不依赖当前停留组件。
- 来源默认 3 张，展开显示全部；上标定位自动展开并高亮目标。
- 历史消息直接使用该消息自己的编号和来源快照，不按当前回答重映射。
- 模型回答先 marked 再 DOMPurify 白名单消毒；来源原文始终纯文本。
- 表格、代码块、链接按终态设计白名单处理，外链使用 `rel="noopener"`。

## 10. 实施分段

1. **后端基础批**：V7、ConversationStore 两实现、会话 API、归属、配额、快照和竞态测试。
2. **前端核心批**：工程骨架、AppShell、消息流、基础问答、来源卡片和 Markdown 安全。
3. **完整交互批**：后台请求、未读、认领、重新生成、标错、401/409/410/429 和失败重试。
4. **端到端验收批**：Vitest、Testcontainers PG、Java 全量测试、CI 打桩模型 Playwright，以及上线前真实 Agent 手动冒烟。

每批保持代码、测试、构建配置和文档同版本；跨批依赖未就绪时不以 mock 结果冒充最终端到端闭环。

## 11. 测试与验收

### 11.1 前端自动化

Vitest 除覆盖终态设计既有项外，还必须覆盖：

- 每条历史消息使用自己的 ID、完成时间和来源快照；
- 认领后匿名 lookup 移除已归属记录；
- 404、409、410 的提示和请求状态清理正确；
- 重新生成失败保留旧回答，成功才替换且消息 ID 不变；
- 非法 JWT 的 401 不降级匿名；
- 同会话前端禁用并发，不同会话可后台并行。

### 11.2 后端自动化

除终态设计既有项外，覆盖：

- ConversationStore 两种实现的同一契约和 generation_attempts 计数；
- 普通问答与重生成都消耗匿名配额，429 在模型调用前返回；
- 认证开启时无 token 可匿名、非法 token 仍 401，新增接口进入鉴权与限频范围；
- 他账号或匿名访问已认领会话返回 404，登录访问未认领匿名会话返回 403；
- 同账号重复认领幂等，他账号认领不覆盖；
- 快照与当轮响应 sources 完全一致；
- 删除后追加/替换不重建父行；晚到请求 410，从未存在 404；
- 重新生成不改变对话轮数，expectedLastSeq 冲突返回 409 且不覆盖新消息；
- Testcontainers PostgreSQL 16 验证 V5→V6→V7、JSONB、外键及删号 SET NULL，不能用 H2 代替这些断言。

### 11.3 浏览器与真实模型分层

CI Playwright 使用真实 Spring 后端、Testcontainers PG 和打桩 ChatModel，稳定验证会话、鉴权、引用快照、竞态和浏览器交互，不在 PR 门禁中调用 DeepSeek/Ollama。

既有终态设计九组场景在打桩链路全部执行，另外验证：

1. 新构建在无 CDN、无旧 index.html 回退时独立工作，hash 路由刷新不 404；
2. 匿名 → 登录认领 → 另一设备读取 → 退出清缓存；
3. 删除进行中的会话后返回 410，刷新不复活；
4. 重新生成失败保留旧回答，成功替换且对话轮数不变；
5. 来源默认 3 张、展开与上标定位在历史恢复后仍正确；
6. CI/交付按 Node 构建 → Java 打包顺序执行，仓库无 dist 生成物。

上线前另做 1～2 条真实 Agent 手动冒烟，验证真实模型、检索和完整回答链路；不得用打桩 CI 结果冒充真实模型验收，也不让外部模型波动阻塞每次 PR。

### 11.4 完成与文档

- 前端全量测试、Java 全量测试、Testcontainers PG、CI 打桩浏览器验收和上线前真实 Agent 冒烟全部通过。
- 不以构建成功、纯 mock 测试或单页截图代替功能验收。
- 闭环时同步 F-020、F-022、一期临时汇总、项目总索引、README、DEPLOYMENT 和测试报告索引。
- F-026 未先实施时不应通过复用 V6 绕过依赖；应停止并处理迁移顺序，而不是撞号。

## 12. 后续实施计划边界

本 Spec 只固定实施层设计，不代替详细计划。后续计划应明确：

- 每批文件归属、测试命令和真实环境准备；
- V7 对 F-026 V6 的依赖；
- Testcontainers PG 的 Docker 前提、CI 打桩模型配置与手动真实模型冒烟配置；
- 新发现问题只登记，不在本批扩张到管理后台、服务端并发锁或实时同步。
