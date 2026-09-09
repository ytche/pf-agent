# 贡献指引（CONTRIBUTING）

感谢你愿意参与 PF Agent。请先读 [README](README.md) 了解项目定位，再按本文档
的红线提交。工程全量红线见仓库根 `CLAUDE.md`（本项目开发用），本文档摘录**对贡献者
生效**的部分并给出来源指针。

> ⚠️ **版权提示**：本仓库 `pf_data/` 的规则文本受 Paizo CUP 与第三方翻译著作权约束，
> 仅接受**社区非商业用途**相关的修正（错译、漏条、结构化改进）；不接受据为己有的再分发。
> 你提交的代码按本仓库 `LICENSE`（Anti-996）授权；你提交的数据修正视为对既有数据层的
> 善意校正，不转移原著作权。

## 目录

1. [如何报告问题（Issue）](#1-如何报告问题issue)
2. [如何提交代码（PR）](#2-如何提交代码pr)
3. [代码规范红线（Java）](#3-代码规范红线java)
4. [数据与评测红线](#4-数据与评测红线)
5. [提交信息规范](#5-提交信息规范)

## 1. 如何报告问题（Issue）

先搜已有 Issue 是否已报。新问题请选模板（`.github/ISSUE_TEMPLATE/`）：

| 模板 | 用途 |
|---|---|
| [Bug 报告](.github/ISSUE_TEMPLATE/bug_report.md) | 问答行为错误、服务异常、检索未命中 |
| [功能建议](.github/ISSUE_TEMPLATE/feature_request.md) | 新能力 / 交互改进 |
| [数据纠错](.github/ISSUE_TEMPLATE/data_correction.md) | 规则文本错译、漏条、条目归属错误 |

**规则类问题（某条规则是什么 / 对不对）请走「数据纠错」或 Bug 报告**，附上你查到的
规则原文依据（书 + 章节），不要只贴 LLM 输出——本项目强调可溯源，Issue 也一样。

## 2. 如何提交代码（PR）

```bash
# 从最新开发分支切功能分支（本仓库开放协作分支见 README/仓库主页）
git checkout -b feat/<your-feature> dev/pf-agent
# ……改动、跑通测试（见 §4）……
git push origin feat/<your-feature>
```

PR 请使用 [PR 模板](.github/PULL_REQUEST_TEMPLATE.md)：
- **说明改动面**：仅 Java 代码 / 数据（pf_data）/ 评测集 / 文档。
- **附自测证据**：`mvn test` 输出、必要时评测重跑结果。
- **数据改动必须**附「不变量核对」（哪些结构不变量不受影响 / 已断言），见 §4。

小提示：纯文档或单一改动请保持 PR 小步；检索/prompt/评测集改动对回答行为影响大，
评审会更严格。

## 3. 代码规范红线（Java）

改动 `pf_agent/agent/` 下的 Java 代码时必须遵守（全文见根 `CLAUDE.md` 对应小节）：

1. **方法名 / 标识符用标准英文驼峰**（camelCase），禁止中文；中文说明写进 Javadoc。
2. **方法按访问级别排序**：静态 public > public > 静态 protected > protected >
   静态 package > package > 静态 private > private；Javadoc/注解随方法移动，
   字段/构造器/内部类保持原位。
3. **Spring 注入用 `@Autowired` 字段注入**，配置值用 `@Value` 字段注入；
   **禁止构造器注入**；构造器中的组装逻辑移到 `@PostConstruct`。多实例 bean 字段上加
   `@Qualifier`。（`@Configuration` 的 `@Bean` 工厂方法与手动 `new` 的非 bean 不受限）
4. **注释用中文、讲「为什么」**，不重复代码能自明的内容。
5. **显式错误处理**：try-catch + 有意义的错误信息，日志含上下文与时间戳（框架默认），
   不在注释/日志输出任何 key/token。
6. 优先原生 API，不引入不必要的依赖；新文件不加版权注释头。

**测试**：偏好 TDD。修改 bug 前先确认对应单测断言是否正确（业务逻辑错误先修测试，
**禁止因 bug 难修而改/删测试**）。提交前 `mvn test` 必须全绿。

## 4. 数据与评测红线

### 评测

- 评测集：`pf_agent/agent/qa/pf_qa_items.json`（59 题，53 活跃）。入口 `qa/evaluate.py`。
- **改动会改变回答行为**（检索策略 / prompt / 工具 / 评测集本身）时，必须全量重跑评测：
  ```bash
  cd pf_agent/agent/qa && python3 evaluate.py
  ```
  且对照当前基线（README「评测与质量声明」）**不允许三维回退**。
- 评测集题目的 `status` 字段语义：`D`/`R` 活跃计入、`X` 人工排除。新增题先核对口径再改状态。

### 数据（`pf_data/`）

- **基线文件不可手工改动**：如 `pf_data/phase1/术语提取报告_分类版.md` 等标注「基线」的
  文件只读；所有对数据的修改走脚本/文档化流程，禁手工编辑结构化表格。
- **产物与脚本同版本**：数据脚本改动提交时，同步可再生的 gitignored 产物说明；产物本身
  不入库（如 `chunks.jsonl`、`spell_lists.json`、向量库）。
- **先理解后修改**：动任何主题数据前，先读其来源与既有清洗规则（`pf_data/phase1/规则书向量化规则.md`、
  对应模块脚本），禁止只靠正则硬修。
- **结构不变量**：改动含专项覆写的核心处理模块前，先列出本次涉及的结构不变量
  （heading 层级 / chunk 边界 / 归属 / 来源书），并在对应 `verify_*.py` 中有断言，
  跑通才算完成。只报「OK 数合理」不算验证。

## 5. 提交信息规范

- 语义化前缀：`feat` / `fix` / `refactor` / `docs` / `test` / `chore` + 范围（模块），
  如 `feat(agent): 增加 xxx 工具`、`fix(data): 修正 xxx 错译`。
- 一次提交一个逻辑变更，不夹带无关改动。
- 中文说明提交主题，可附正文说明动机与影响面。

---

有问题先问：在 Issue 里讨论方案再动手，避免返工。感谢贡献！
