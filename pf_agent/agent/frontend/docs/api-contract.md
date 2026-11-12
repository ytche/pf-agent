# PF Agent 前端 API 契约（F-020 / F-022）

- 冻结日期：2026-11-11（M25，经塔批准）
- 依据：`docs/superpowers/specs/2026-11-03-f020-frontend-final-design.md` §7、
  `docs/superpowers/specs/2026-11-11-f020-f022-frontend-implementation-design.md` §5–§9
- 消费方：`pf_agent/agent/frontend`；实现方：M24（`pf_agent/agent/src/main/java/.../conversation`）
- 本文件只固定 JSON 字段，不新增交互规则。日期时间一律 ISO-8601 字符串。

## 1. 公共类型

```ts
interface ConversationSummary {
  id: string            // UUID
  title: string | null  // 首轮成功后由首条问题生成，可重命名
  pinned: boolean
  createdAt: string
  updatedAt: string     // 最近活跃时间
  messageRounds: number // 可见轮数（0 = 空会话，不在历史列表）
}

interface Source {
  book: string                     // 兼容展示名：中文书名与缩写合并（如“核心规则书 (CRB)”）
  bookNameCn?: string | null       // 结构化中文书名；官方/未知来源可为空
  bookAbbreviation?: string | null // 结构化书名缩写；官方/未知来源可为空
  tocPath: string
  content: string
  chunkId?: string | null
}

interface Message {
  id: number | string
  seq: number                  // 会话内单调递增
  role: 'user' | 'assistant'
  content: string
  sources: Source[] | null     // 旧消息为 null → 前端显示“历史来源未保存”
  gapReported: boolean
  createdAt: string
  completedAt?: string | null
}

interface ConversationDetail extends ConversationSummary {
  messages: Message[]          // 仅最近 20 轮，按 seq 升序
}
```

## 2. 会话接口

| 方法 | 路径 | 请求体 | 成功响应 |
|---|---|---|---|
| POST | `/api/conversations` | 空 | 200 `ConversationSummary`（messageRounds=0） |
| GET | `/api/conversations?limit=30&cursor=` | — | 200 `{ items: ConversationSummary[], nextCursor: string \| null }`，置顶优先、其余 updatedAt 倒序 |
| POST | `/api/conversations/lookup` | `{ ids: string[] }` | 200 `{ items: ConversationSummary[] }`，只返回 owner 为空的会话 |
| GET | `/api/conversations/{id}` | — | 200 `ConversationDetail` |
| PATCH | `/api/conversations/{id}` | `{ title?: string, pinned?: boolean }` | 200 `ConversationSummary` |
| DELETE | `/api/conversations/{id}` | — | 204（无响应体） |
| POST | `/api/conversations/claim` | `{ conversationIds: string[] }` | 200 `{ claimed: string[], alreadyOwned: string[], rejected: string[] }` |
| POST | `/api/conversations/{id}/regenerate` | `{ expectedLastSeq: number }` | 200 `ChatAnswer` |

`ChatAnswer`：

```ts
interface ChatAnswer {
  answer: string
  sources: Source[]        // cited-only 过滤与编号重映射后的快照
  gapReported: boolean
  conversationId: string
  messageId?: number | string  // 助手消息 ID（重新生成后保持不变）
  messageSeq?: number
  completedAt?: string
}
```

## 3. 问答与反馈

| 方法 | 路径 | 请求体 | 响应 |
|---|---|---|---|
| POST | `/api/chat` | `{ question: string, conversationId: string }` | 200 `ChatAnswer` |
| POST | `/api/chat/feedback` | `{ conversationId, question, answer, sources, errorType, correction?, comment? }` | 200 `{ ok: true, id }`；400 `invalid_input`；503 `unavailable` |

`/api/chat` 与 `/api/chat/feedback` 保持既有兼容字段；本批只在响应上追加可选
`messageId` / `messageSeq` / `completedAt`，旧客户端不受影响。

## 4. 认证与管理员探测

| 方法 | 路径 | 请求体 | 响应 |
|---|---|---|---|
| GET | `/api/auth/status` | — | `{ enabled: boolean, registrationEnabled: boolean, memoryMode?: boolean }` |
| POST | `/api/auth/login` | `{ username, password }` | `{ token, uid, username, nickname }` |
| POST | `/api/auth/register` | `{ username, password }` | 同上；403 `registration_closed` |
| GET | `/api/auth/me` | — | `{ uid, username, nickname }` |

管理员入口不扩展 `/api/auth/me`：前端在登录态下请求 `GET /api/admin/settings`，
200 = 管理员，401/403 = 非管理员。失败按非管理员处理，不影响问答。

`memoryMode` 反映后端 `pf.chat.memory`：`jdbc` → `false`，`memory` → `true`。
前端在 `memoryMode=true` 时提示“临时模式，重启后历史清空”；字段始终返回，
旧前端忽略该字段不受影响。

## 5. 错误码

统一错误体 `{ error: string, message?: string }`。

| HTTP | error | 前端行为 |
|---|---|---|
| 400 | `invalid_request` / `invalid_input` | 表单内联提示 |
| 401 | `unauthorized` / `invalid_credentials` | 保留当前会话与问题，打开登录弹层，用户手动重试 |
| 403 | `forbidden` / `registration_closed` | 提示无权限 / 注册关闭 |
| 404 | `conversation_not_found` | 历史读取失败可重试；写入时表示会话从未存在 |
| 409 | `conversation_changed` | 重新生成冲突：保留旧回答，提示重新打开会话 |
| 410 | `conversation_deleted` | 晚到结果丢弃，清请求状态，不重新加入历史列表 |
| 429 | `quota_exceeded` | 提示配额用完并提供“新建会话” |
| 429 | `rate_limited` | 提示稍后重试 |
| 5xx | — | 当前轮内联错误 + 重试 |

## 6. 前端承担与不承担

- 同会话并发只在 Pinia/Composer 层禁止；服务端不提供请求锁，直接 API 或多设备
  并发仍可能后写覆盖先写（实施 spec §7.2）。
- 前端不实现正文流式输出、停止生成、实时同步、草稿持久化。
- 匿名会话 ID 仅存本机；登录后通过 claim 显式认领，退出登录隐藏账号历史并清缓存。

## 7. Spring 静态服务约定（M24 负责，Java 侧不在前端 scope）

- `classpath:/static/dist/` 作为静态资源根；
- 根路径 `/` 显式 forward 到 `dist/index.html`；
- 前端使用 hash 路由，刷新 `/#/c/{id}` 仍由同一 `dist/index.html` 承载；
- 不保留旧 `src/main/resources/static/index.html` 回退页面。

## 8. 后端契约缺口补记（M27 已补齐）

M25 登记的两个缺口已由 M27 补齐，本节保留变更记录：

1. `GET /api/auth/status` 现返回 `memoryMode`（`pf.chat.memory=jdbc` → false，
   `memory` → true），前端可展示“临时模式，重启后历史清空”提示。
2. `ChatResponse.SourceRef` 现新增 `bookNameCn` / `bookAbbreviation`，并保留
   `book` 兼容字段。前端来源卡片优先展示结构化书名与缩写，缺失时回退 `book`；
   旧 JSONB 快照缺少新字段时仍可正常读取并在前端降级展示。

