---
name: Bug 报告
about: 问答行为错误、服务异常、检索未命中
title: '[Bug] '
labels: bug
assignees: ''

---

**描述 Bug**

清晰说明问题现象。

**复现步骤**

1. 提问：`在此粘贴问题`
2. 期望：...
3. 实际：...

**实际输出**

粘贴应用返回的完整回答（含来源列表与 `[#N]` 上标），或异常堆栈 / HTTP 状态码。

**运行环境**

- 部署方式：Docker Compose / 本地 `mvn spring-boot:run`
- 检索配置是否改过默认：`pf.search.*`、`pf.embedding.*`（改了的话附值）
- 数据来源：预构建数据包 / 自建 chunks
- 版本 / commit：`git log -1 --oneline`

**规则依据（可溯源）**

如属规则内容错误，请给出你查到的规则原文（书 + 章节 / 目录路径）。

**其他上下文**

日志、错误截图、相关 Issue 等。
