# PF Agent 前端

Vue 3 + TypeScript + Vite + Pinia 的问答 SPA，替换旧单文件 `static/index.html`。

- UI 基线：`docs/superpowers/specs/2026-11-03-f020-frontend-final-design.md`（唯一）
- 实施 spec：`docs/superpowers/specs/2026-11-11-f020-f022-frontend-implementation-design.md`
- 固定 API 契约：`docs/api-contract.md`

## 命令

```bash
npm ci            # 安装锁定依赖
npm run dev       # Vite 开发服务器（/api 代理到 http://localhost:8080）
npm run build     # 类型检查 + 构建到 ../src/main/resources/static/dist
npm run test:unit # Vitest
npm run test:e2e  # 构建后 Playwright（打桩 API，不调用真实模型）
```

后端静态服务模式必须先 `npm run build`，再启动 Spring Boot；产物目录
`pf_agent/agent/src/main/resources/static/dist` 已被 `.gitignore` 排除。

## 结构

```
src/api/         固定契约类型与 fetch 客户端
src/stores/      Pinia：auth、conversations
src/components/  AppShell / HistoryDrawer / ConversationView / MessageList /
                 MessageItem / SourceCards / Composer / FeedbackForm / AuthDialog
src/utils/       markdown（marked + DOMPurify）、时间、本地存储
e2e/             Playwright 桌面与手机场景，support/stub-api.ts 为打桩后端
tests/           Vitest 单元测试
```

## 测试分层

- Vitest：store 会话切换/后台完成/未读/分页/认领/401/409/410/429、来源默认 3 张与
  展开定位、Markdown XSS 与来源纯文本。
- Playwright：真实浏览器 + 打桩 API（打桩 ChatModel 语义），覆盖空态、多会话、
  置顶/重命名/删除、后台完成未读、手机全屏历史与多行输入、宽表格局部滚动、
  长来源完整展示、XSS、hash 刷新恢复。
- 全栈 Playwright（`npm run test:e2e:fullstack`）：真实 Spring Boot 后端 + Docker
  启动的一次性 PostgreSQL 16 + OpenAI 兼容打桩 ChatModel，覆盖匿名提问真实来源快照、
  登录认领、401 清 token 后匿名/登录重试、删除进行中会话的 410 晚到结果。需要 Docker
  与 Java 17；`pretest:e2e:fullstack` 会先构建前端并 `mvn package` 出含 dist 的 jar。
- 真实 Agent（DeepSeek/Ollama）保留上线前手动冒烟，不在 PR 门禁调用。
