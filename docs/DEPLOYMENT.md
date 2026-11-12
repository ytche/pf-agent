# 部署文档（DEPLOYMENT）

本文档面向**部署/运维**读者，说明环境变量、三种部署形态与**四个已知配置坑**。
新用户上手请看 [README](../README.md)「快速开始」。

- [一、环境变量总表](#一环境变量总表)
- [二、部署形态](#二部署形态)
- [三、已知配置坑（四个，务必读）](#三已知配置坑四个务必读)
- [四、检索与 embedding 参数调优](#四检索与-embedding-参数调优)
- [五、数据目录速查](#五数据目录速查)
- [六、向量库全量重灌手册（chunks 变更唯一路径）](#六向量库全量重灌手册chunks-变更唯一路径)

---

## 一、环境变量总表

配置统一在 `pf_agent/agent/src/main/resources/application.yml`（键 `pf.*` 为项目自定义，
`spring.*` / `server.*` 为 Spring/Spring AI 标准键）。环境变量模板见仓库根 `.env.example`。

| 环境变量 | 对应配置键 | 必填 | 说明 |
|---|---|---|---|
| `DEEPSEEK_PF_API` | `spring.ai.openai.api-key` | ✅ | DeepSeek Chat API key（LLM） |
| `PF_EMBEDDING_PRIMARY` | `pf.embedding.primary` | 否 | `ollama`（默认）/ `cloud` |
| `PF_EMBEDDING_FALLBACK_ENABLED` | `pf.embedding.fallback-enabled` | 否 | 主通道失败降级（`primary=cloud` 建议 `true`） |
| `PF_EMBEDDING_CLOUD_API_KEY` | `pf.embedding.cloud.api-key` | 仅 cloud/降级 | 托管 bge-m3 key（**只经 env 注入，严禁入库**） |
| `PF_EMBEDDING_CLOUD_BASE_URL` | `pf.embedding.cloud.base-url` | 否 | 托管 API 地址（默认 siliconflow） |
| `PF_EMBEDDING_CLOUD_MODEL` | `pf.embedding.cloud.model` | 否 | 托管模型（默认 `BAAI/bge-m3`） |
| `PF_CHAT_MEMORY` | `pf.chat.memory` | 否 | `jdbc`（默认，PostgreSQL）/ `memory`（纯内存回退） |
| `SPRING_DATASOURCE_URL` | `spring.datasource.url` | 否 | PG 连接串（默认 `jdbc:postgresql://localhost:5432/pf_agent`） |
| `SPRING_DATASOURCE_USERNAME` | `spring.datasource.username` | 否 | PG 用户（默认 `pf_agent`） |
| `SPRING_DATASOURCE_PASSWORD` | `spring.datasource.password` | 否 | PG 密码（默认 `pf_agent`） |
| `PF_AUTH_ENABLED` | `pf.auth.enabled` | 否 | 鉴权开关（默认 `false`；`true` 时 `/api/chat`、`/api/chat/feedback` 需 JWT） |
| `PF_AUTH_JWT_SECRET` | `pf.auth.jwt-secret` | 开鉴权时 ✅ | JWT HS256 密钥（**生产必须覆盖**，见下方坑 ④） |
| `PF_AUTH_TOKEN_TTL_HOURS` | `pf.auth.token-ttl-hours` | 否 | JWT 有效期小时数（默认 72；多虚线属性，env 覆盖不可靠，见坑 ①） |
| `SPRING_AI_OLLAMA_BASE_URL` | `spring.ai.ollama.base-url` | 否 | Ollama 地址（默认 `http://localhost:11434`） |
| `SERVER_PORT` | `server.port` | 否 | HTTP 端口（默认 `8080`） |

> 环境变量经 Spring「松散绑定」覆盖 yml 同名键（`PF_CHAT_MEMORY` → `pf.chat.memory`）。
> **例外**：多虚线属性见下方「坑 ①」，不要依赖 env 覆盖。

### 限频 / 配额

| 配置键 | 默认 | 说明 |
|---|---|---|
| `pf.rate-limit.enabled` | `false` | 按 IP 限频开关（F-010）。`false` = 不装配拦截器 |
| `pf.rate-limit.per-minute` | `20` | 每 IP 每分钟 `/api/chat` 上限（超限 429 `rate_limited`） |
| `pf.rate-limit.trust-forwarded-for` | `false` | 反向代理取 `X-Forwarded-For` 首跳；默认关防伪造 |
| `pf.quota.enabled` | `false` | 匿名会话轮次配额（F-011）。`false` = 不装配服务 |
| `pf.quota.anonymous-rounds` | `20` | 每会话累计轮数上限（达限 429 `quota_exceeded`） |

默认全关（开源自部署零摩擦优先）。**托管公网部署建议开启**，防 DeepSeek token 成本失控。

---

## 二、部署形态

### 形态 1：Docker Compose 一键（公开库默认路径）

```bash
git clone <repo>.git && cd <repo>
cp .env.example .env          # 填 DEEPSEEK_PF_API
docker compose up -d          # app + Ollama + PostgreSQL（首次自动拉 bge-m3）
```

- 应用 <http://localhost:8080/>；健康检查 `GET /api/health`。
- 数据：见 [README「准备数据」](../README.md#快速开始)（预构建数据包放 `~/.pf_agent/`，
  或用卷映射）。
- PostgreSQL（SP7 起默认服务）：会话历史与用户表自动落库，Flyway 执行 V1~V7 迁移
  （SP7 建会话/用户表，F-026 V6 建 `query_gate_event`，F-020 V7 增加会话标题/置顶/
  归属/生成计数与消息引用快照），app `depends_on: pg (service_healthy)` 等 PG 就绪后启动。
  回退纯内存：`PF_CHAT_MEMORY=memory`（并去掉 app 的 `depends_on: pg`）。
- **升级即切库**：SP7 起默认 jdbc，老部署（内存模式）升级后历史会话「消失」的观感属
  预期——内存会话本就不持久，无数据回归；切回 `PF_CHAT_MEMORY=memory` 行为同旧版。
- 可选鉴权：`PF_AUTH_ENABLED=true` + 覆盖 `PF_AUTH_JWT_SECRET`（坑 ④），注册入口在
  前端右上角出现。**F-020 起鉴权开启时仍允许无 token 匿名使用**（本机 UUID 能力会话）；
  非法 token 返回 401；登录后可显式认领会话，认领后仅所属账号可访问（匿名/他账号 404）。
  删号后 `owner_user_id` 置空、会话转匿名并继续凭 UUID 访问，这是用户已确认的隐私取舍。

### 形态 2：本地开发（mvn）

前置 Java 17 + Ollama（`ollama pull bge-m3`）+ **Node ≥20.19**（前端构建）+
**本机 PostgreSQL**（SP7 起默认 `pf.chat.memory=jdbc`；无 PG 时启动即报 Flyway 连接错误，
属明确失败）。无 PG 的临时开发可显式 `--pf.chat.memory=memory` 回退（用户表/鉴权接口随之不可用）。

```bash
cd pf_agent/agent

# 1) 前端先构建：Vite 输出到 src/main/resources/static/dist（gitignored，不提交）
cd frontend && npm ci && npm run build && cd ..

# 2) 启动后端（根路径由 SpaForwardController forward 到 dist/index.html）
export DEEPSEEK_PF_API=sk-xxx
mvn spring-boot:run
```

程序参数覆盖（推荐用于虚线属性）：`mvn spring-boot:run -Dspring-boot.run.arguments="--pf.rate-limit.enabled=true"`。

前端开发可单独 `npm run dev`（Vite 代理 `/api` 到当前后端）；只调后端时 `static/dist/`
缺失不影响 `/api/**`。

### 形态 3：反向代理托管（Nginx / Caddy）

- 开限频请同时开 `pf.rate-limit.trust-forwarded-for: true`（否则所有请求被看作同一
  `remoteAddr` = 代理 IP，共享一个限频桶）。⚠️ 仅在你信任代理会**覆盖/剥离**客户端伪造的
  `X-Forwarded-For` 时开启，否则攻击者可伪造 IP 绕过限频。
- 该开关因含虚线，建议 yml 或程序参数设置，勿用 env。

---

## 三、已知配置坑（四个，务必读）

> 来源：SP2 验收（2026-09-06）与 SP5 交付实测。**前两个直接影响「配置了却不生效/不按
> 预期降级」，部署前请对照。**

### 坑 ①：多虚线属性的 env 覆盖绑定不一致（Spring 6.2.6 实测）

`pf.rate-limit.per-minute` 这类**多虚线**属性，环境变量覆盖行为不一致：

| 写法 | 实测结果 |
|---|---|
| `PF_RATELIMIT_PER_MINUTE` | ❌ **不生效**（静默回落默认 20） |
| `PF_RATELIMIT_PERMINUTE` | ✅ 生效（去下划线粘合） |
| `PF_QUOTA_ANONYMOUS_ROUNDS`（单段虚线） | ✅ 按松散绑定生效 |

**结论**：含虚线的配置项**以 yml 或程序参数（`--pf.rate-limit.per-minute=N`）为准**，
不要依赖 env 覆盖；`.env.example` 中对这类项已标注注释。

### 坑 ②：`pf.embedding.fallback-enabled` 的 yml 显式值覆盖默认逻辑

SP5 设计默认：`primary=cloud` 时 fallback 默认开、`primary=ollama` 时默认关（仅本地单通道）。
但 `application.yml` **显式写了 `fallback-enabled: false`**（带注释的缺省值）——这会**覆盖
设计默认**：

- 若你想用 **cloud 主 + ollama 兜底**（托管断线自动降级本地），必须**删除该行**（让 D6
  默认逻辑生效）或**显式写 `true`**；仅设 `primary=cloud` 而保留 `false`，则主通道失败时
  **不会**降级。
- 只想本地单通道（默认零配置）：保持 `false` 即可，无需改动。

### 坑 ③：cloud 主通道的成本特征——每次检索每 store 一次 embed 调用

用 cloud 做**查询 embedding 主通道**时，单次问答会触发多次云端 embed 调用：

- Spring AI 观测链在每次 `similaritySearch` 前都会调用 `dimensions()`；多模块检索 + 重排
  候选扩容下，**实测单问约 60 次**云端 embed 请求（V5② 实测口径）。
- 成本估算按「每次问答 ≈ 60 次 embed」预留给付制 API，而非「每问 1~2 次」。
- 若在意成本：默认走本地 Ollama 主通道（零成本）；cloud 仅作 fallback（主通道罕见失败
  时才触发），可大幅压低调用量。

### 坑 ④（SP7 新增）：JWT 默认密钥是公开的开发值，开鉴权必须覆盖

`pf.auth.jwt-secret` 在 yml 里给了开发默认值（`pf-agent-dev-jwt-secret-change-me`，
仓库内公开），仅供本地零配置跑通：

- `pf.auth.enabled=true` 且密钥仍为默认值时，启动会打 **WARN** 提醒（不阻断，自部署
  友好）——**看到 WARN 即应处理**，生产环境必须经 `PF_AUTH_JWT_SECRET` 覆盖为足够长
  的随机字符串；密钥泄露 = 任何人可伪造任意用户的登录 JWT。
- 该属性是单段（`jwt-secret`），`PF_AUTH_JWT_SECRET` 按松散绑定生效；但
  `token-ttl-hours` 是多虚线，env 覆盖不可靠（同坑 ①），调有效期请改 yml 或程序参数。
- 限频建议：`/api/auth/**` 已纳入 `pf.rate-limit` 拦截范围（开关同源，默认关），托管
  公网部署开鉴权时建议同时开限频，防注册接口被刷库。

---

## 四、检索与 embedding 参数调优

完整键见 `application.yml` 的 `pf.search.*`。常用：

| 键 | 默认 | 说明 |
|---|---|---|
| `pf.search.top-k` | `15` | 语义检索默认命中数 |
| `pf.search.similarity-threshold` | `0.5` | 相似度阈值 |
| `pf.search.max-tool-rounds` | `10` | LLM 工具循环轮次上限（超限强制收敛作答） |
| `pf.search.chat-timeout` | `60s` | 单次 LLM 读超时 |
| `pf.search.filter-blank-text` | `true` | 空 text chunk 剔除 |
| `pf.embedding.primary` | `ollama` | 查询 embedding 通道 |

> ⚠️ **模型一致性约束**：查询 embedding 与向量库构建必须同为 **bge-m3**（1024 维），
> 换模型 = 语义空间变化，**必须重建向量库**（删除 `~/.pf_agent/vector_store_*.json` 重启自动重建）。

---

## 五、数据目录速查

| 内容 | 位置 | 说明 |
|---|---|---|
| 向量库持久化 | `~/.pf_agent/vector_store_*.json` | 8 模块独立文件；存在即跳过导入 |
| 数据缺口/反馈/工具记录 | `~/.pf_agent/*.jsonl` | 运行时追加，脚本分析用 |
| chunks 源 | `pf_data/phase1/vectorizer/output/<模块>/chunks.jsonl` | gitignored，管线产物 |
| 法术清单 | `.../法术/spell_lists.json` | gitignored，SP3 直查数据源 |
| 法术 union 清单 | `.../法术/spell_lists_union.json` + `spell_list_union_report.json` | gitignored，F-025 去重后 union 1.1（Java 直读；独立 JSON 变更只重启消费者，不重灌向量库） |
| 规则文本 | `pf_data/phase1/pf_rules_md_organized/` | 随库发布，管线输入 |

日志默认 `logging.level.com.pfagent.agent: DEBUG`（见 yml 尾部）。

---

## 六、向量库全量重灌手册（chunks 变更唯一路径）

> DVG-001（2026-11-11）清偿后，向量库**唯一写路径**为：数据侧 chunks.jsonl → Java
> DataLoader 全量重灌。旧 metadata 重放工具 `SpellMetadataReplayTool` 已彻底删除；
> 若历史部署命令/环境变量误带 `pf.stores.metadata-replay=true`，启动会被
> `DeprecatedMetadataReplayGuard` 明确拒绝（fail-fast），按本节流程处理。
> **禁止直接修改 `vector_store_*.json`。**

### 6.1 适用范围

仅用于 **chunks 内容、边界、元数据或 Mapper 消费字段变化**导致的向量库更新（如数据侧
KN 修复后重新产出的 chunks.jsonl）。独立清单 JSON 变化（spell_lists / class_tables /
list_exports）走对应消费者重启即可，**不使用本流程、不重算 embedding**。更换 embedding
模型（必须同为 bge-m3）也走本流程。

### 6.2 前置确认

1. **确认消费面**：目标模块、chunks 路径、store 路径、当前运行实例。
   以法术模块为例（其余模块替换路径即可）：

   | 项 | 值 |
   |---|---|
   | chunks 产物 | `pf_data/phase1/vectorizer/output/法术/chunks.jsonl` |
   | store 路径 | `~/.pf_agent/vector_store_spells.json`（8 模块对应 `vector_store_<模块>.json`） |
   | 正式实例 | 常驻 8080（`server.port=8080`） |

2. 数据侧产物已重新生成且本仓库已更新到对应版本。

### 6.3 备份旧库（禁止无备份删除）

```bash
TS=$(date +%Y%m%d_%H%M%S)
mv ~/.pf_agent/vector_store_spells.json ~/.pf_agent/vector_store_spells.json.bak_${TS}
ls -la ~/.pf_agent/ | grep vector_store_spells   # 确认备份存在且未覆盖任何既有 .bak*
```

### 6.4 同路径临时实例全量重灌

临时实例与正式实例使用**同一 `user.home` 和同一 store 路径**（store 配置是
`pf.stores.*-file-path: ${user.home}/.pf_agent/...`，不能经 env 改到别处——改了就不是
同一个库）。用 `PF_CHAT_MEMORY=memory` 隔离会话数据库（只隔离 PG，不改 store 路径），
随机端口避免与正式实例冲突：

```bash
cd pf_agent/agent
export DEEPSEEK_PF_API=sk-xxx
PF_CHAT_MEMORY=memory mvn spring-boot:run -Dspring-boot.run.arguments="--server.port=0"
```

启动日志确认法术 DataLoader 全量导入并持久化（store 文件不存在 → 全量 embedding 导入，
法术库约 4200 条，耗时取决于 Ollama，分钟级~30 分钟）。**常驻正式实例全程不重启、不受
影响**（同一 store 文件此时不存在于原路径，但正式实例已加载在内存中）。

### 6.5 产物对账

临时实例保持运行，另开终端核对新 store 与数据侧产物：

```bash
# 条数：产物行数 vs store 条目数
wc -l < ../../pf_data/phase1/vectorizer/output/法术/chunks.jsonl
python3 -c "import json;print(len(json.load(open('$HOME/.pf_agent/vector_store_spells.json'))))"

# chunk_id 集合一致（空输出 = 一致）
python3 - <<'EOF'
import json
store = json.load(open(__import__('os').path.expanduser('~/.pf_agent/vector_store_spells.json')))
store_ids = {str(d['metadata']['chunk_id']) for d in store.values()}
jsonl_ids = {json.loads(l)['chunk_id'] for l in open('../../pf_data/phase1/vectorizer/output/法术/chunks.jsonl') if l.strip()}
print('store 有而产物无:', sorted(store_ids - jsonl_ids))
print('产物有而 store 无:', sorted(jsonl_ids - store_ids))
EOF
```

另抽验 text 与 Mapper 应支持字段（title / school / spell_level_* / book_* 等）与目标
锚点条目正确。

### 6.6 失败回滚

若导入或对账失败：**不重启、不切换正式实例**。

```bash
# 停止临时实例（Ctrl+C 或 kill），移除仅本次新生成且未通过验收的 store
rm ~/.pf_agent/vector_store_spells.json
# 备份恢复到原路径
mv ~/.pf_agent/vector_store_spells.json.bak_${TS} ~/.pf_agent/vector_store_spells.json
```

保留失败日志供排查；回滚后正式实例内存中仍是旧库，行为不变。

### 6.7 切换正式实例与真实验证

对账通过后：停止临时实例 → 重启正式实例（`cd pf_agent/agent && mvn spring-boot:run`），
它自动加载新库（store 存在即跳过导入）。然后在新库实例上做一次**真实检索/问答**冒烟并
记录结果：

```bash
curl -s -X POST http://localhost:8080/api/chat -H 'Content-Type: application/json' \
  -d '{"question":"火球术的豁免和伤害是多少？"}' | head -c 500
```

记录端口/实例与回答要点，作为验收证据。

### 6.8 保留备份

旧库备份 `.bak_<时间戳>` **不自动删除**；后续清理由部署方另行决定。
