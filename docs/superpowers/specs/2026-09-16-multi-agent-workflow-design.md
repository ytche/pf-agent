# 多 Agent 协作开发流程 — 设计 Spec

日期：2026-09-16
状态：设计已逐节确认，待实施

## 背景与目标

在 pf_agent 仓库引入分角色的多 Agent 开发流程：架构（architect）、编码（coder）、测试（tester）、验收（主 Agent）。目标是：

- 把项目既有规矩（"讨论阶段不动手"、扩展点优先、KN 登记惯例）固化到角色与流程中，而非每次口头叮嘱；
- 编码与验收之间加一层独立测试，防止 coding agent 自证自验；
- 分级触发，轻量任务不背完整流程的开销。

## 角色与分工

| 角色 | 形态 | 职责 |
|------|------|------|
| 主 Agent | 内置默认 | 流程编排 + 最终验收：派单、中转打回、对照验收标准逐条核对、向用户汇报结论 |
| architect | 自定义 `.kimi-code/agents/architect.md` | 设计阶段：读代码与文档，产出方案（改动范围、模块划分、扩展点、风险、验收标准草案），落盘 `docs/design/`。只读代码，只写方案文档，用户拍板后才进入编码 |
| coder | 内置，不定制 | 按方案实现 + 自测；交付代码与结构化提交说明（改动文件、方案覆盖情况、自测内容、**已知未覆盖点**声明）。主 Agent 派单时附项目红线摘要 |
| tester | 已建 `.kimi-code/agents/tester.md` | ① 读方案制定用例/测试代码；② 对交付物黑盒测试（真实调用）；③ 审计 coder 测试代码（查假测试、覆盖盲区）+ 白盒补测，重点边界条件；④ 出具结构化测试报告。缺陷三级：Blocker / Major / Minor |

验收由主 Agent 承担，不设独立 acceptor：验收标准源于用户对话，只有主 Agent 看得到完整上下文；tester 报告作为验收的强制输入保证证据性。

## 分级触发

- **轻量任务**（配置修改、脚本小 bug、文档更新）：主 Agent 直接做 → tester 针对性验证 → 主 Agent 验收；方案与报告不留档。
- **标准任务**（新功能、新模块、跨文件改动）：architect → coder → tester → 主 Agent 验收；方案与测试报告留档。
- **大工程**（新 pipeline、架构调整）：标准链路前加一轮方案评审，用户拍板后才动工（落实"讨论阶段不动手"）。

## 交接物与目录

| 阶段 | 交接物 | 形式 |
|------|--------|------|
| architect | 方案文档 | `docs/design/方案_<主题>_<日期>.md`，含验收标准草案 |
| coder | 代码 + 提交说明 | 结构化说明含"已知未覆盖点" |
| tester | 测试报告 | 标准/大任务落盘 `docs/test-reports/测试报告_<主题>_<日期>.md`；轻量任务只回消息 |
| 主 Agent | 验收结论 | 对照验收标准逐条核对 + tester 报告摘要 + 明确结论；验收反馈维持进 `docs/handover/` |

新增目录各带 `README.md` 写明收录规则（对齐 `docs/handover/README.md` 惯例）。`docs/design/` 与 `docs/superpowers/specs/` 分工：前者是日常开发轻量方案，后者是 brainstorming 正式 spec。

## 迭代回路

- **tester 不通过**（Blocker/Major）→ 主 Agent 中转打回 coder（附缺陷清单与复现步骤），修完 tester 回归；coder 与 tester 不直接对话，主 Agent 负责过滤无效缺陷与仲裁。**上限 3 轮**，超限升级用户拍板（放宽标准 / 改方案 / 重来）。
- **主 Agent 验收打回**按原因定路线：实现不达标 → coder；方案缺陷 → architect（方案改动需用户重新拍板）；需求不清 → 找用户澄清。
- **Minor 缺陷**由用户拍板：放行（登记 KN，接入 `docs/已知问题记录.md` 惯例）或打回。

## 固化方式

- 完整流程：`docs/WORKFLOW.md`（按需读取）。
- CLAUDE.md"约束与规范"新增压缩版红线（5-8 行，遵守 CLAUDE.md 防膨胀规范），含分级触发、角色顺序、回路上限与 `docs/WORKFLOW.md` 指针。

## 实施清单

1. `docs/superpowers/specs/2026-09-16-multi-agent-workflow-design.md`（本文档）
2. `docs/WORKFLOW.md`
3. `.kimi-code/agents/architect.md`
4. `docs/design/README.md`、`docs/test-reports/README.md`
5. CLAUDE.md 压缩版红线条目
6. git commit（含此前已建未提交的 `.kimi-code/agents/tester.md`）
