# DeepSeek 模型统一为 deepseek-flash 设计

## 目标

将 Agent 主问答与 QA 评测 Judge 的 DeepSeek 默认模型统一为 `deepseek-flash`，并同步相关文档，消除当前配置与说明不一致的问题。

## 范围

- 主 Agent：`pf_agent/agent/src/main/resources/application.yml` 已配置为 `deepseek-flash`，保持不变。
- QA Judge：将 `pf_agent/agent/qa/evaluate.py` 中 `judge_llm()` 的默认模型从 `deepseek-chat` 改为 `deepseek-flash`。
- 根 README：将架构图中的主 Agent 模型名称改为 `deepseek-flash`。
- QA README：明确 LLM-as-judge 默认使用 `deepseek-flash`。

不修改 API 地址、密钥环境变量、温度、评测判分逻辑，也不新增跨语言配置或命令行参数。

## 验证

1. 搜索当前运行配置与使用文档中的 `deepseek-chat`，确认没有残留；设计与实施记录中作为修改前事实出现的旧型号不属于残留。
2. 对 `evaluate.py` 运行 Python 语法检查。
3. 运行 QA 默认值 RED/GREEN 断言（修改前失败 `deepseek-chat`、修改后通过 `deepseek-flash`），并对 `evaluate.py` 运行 AST 语法检查，均已执行通过。
4. 运行完整 `mvn test`：622 项测试、0 失败、1 跳过。真实 DeepSeek API 未调用。
