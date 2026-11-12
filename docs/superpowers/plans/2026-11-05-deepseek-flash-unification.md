# DeepSeek 型号统一实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 QA 评测 Judge 与相关文档中的 DeepSeek 默认模型统一为 `deepseek-flash`。

**Architecture:** 保留主 Agent 现有 Spring AI 配置不变，仅修改 QA 脚本的默认参数和两处文档说明。不引入新配置层、命令行参数或依赖。

**Tech Stack:** Python 3 标准库、Markdown、Spring AI 现有配置

---

### Task 1: 统一 QA Judge 默认模型

**Files:**
- Modify: `pf_agent/agent/qa/evaluate.py:177`

- [x] **Step 1: 运行默认模型断言，确认修改前失败**

Run:

```bash
cd /Users/chezi/code/java/pf_agent/pf_agent/agent/qa
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import inspect; from evaluate import judge_llm; actual = inspect.signature(judge_llm).parameters["model"].default; assert actual == "deepseek-flash", f"unexpected default model: {actual}"'
```

Expected: FAIL，错误信息包含 `unexpected default model: deepseek-chat`。

- [x] **Step 2: 修改默认模型**

将：

```python
def judge_llm(question: str, golden_points: list, answer: str, model: str = "deepseek-chat") -> dict:
```

改为：

```python
def judge_llm(question: str, golden_points: list, answer: str, model: str = "deepseek-flash") -> dict:
```

- [x] **Step 3: 重跑默认模型断言，确认通过**

Run:

```bash
cd /Users/chezi/code/java/pf_agent/pf_agent/agent/qa
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import inspect; from evaluate import judge_llm; actual = inspect.signature(judge_llm).parameters["model"].default; assert actual == "deepseek-flash", f"unexpected default model: {actual}"'
```

Expected: PASS，命令无输出且退出码为 0。

### Task 2: 同步模型文档

**Files:**
- Modify: `README.md:68`
- Modify: `pf_agent/agent/qa/README.md:99-107`

- [x] **Step 1: 更新根 README 架构图**

将：

```text
┌────────  DeepSeek LLM（deepseek-chat）────────┐
```

改为：

```text
┌────────  DeepSeek LLM（deepseek-flash）────────┐
```

- [x] **Step 2: 更新 QA README 的 Judge 说明**

将：

```text
B 批接口已留好：`judge_llm()` 调 DeepSeek chat API（`temperature=0` + `response_format=json_object`），
```

改为：

```text
B 批接口已留好：`judge_llm()` 默认调用 DeepSeek `deepseek-flash` 模型（`temperature=0` + `response_format=json_object`），
```

### Task 3: 完整验证

**Files:**
- Verify: `pf_agent/agent/qa/evaluate.py`
- Verify: `README.md`
- Verify: `pf_agent/agent/qa/README.md`
- Verify: `pf_agent/agent/src/main/resources/application.yml`

- [x] **Step 1: 检查旧型号无残留**

Run:

```bash
cd /Users/chezi/code/java/pf_agent
git grep -n -i 'deepseek-chat' -- README.md pf_agent/agent
```

Expected: 无输出，退出码为 1（表示当前运行配置与使用文档没有匹配项）；设计与实施记录中的旧型号仅作为修改前事实保留。

- [x] **Step 2: 检查主 Agent 与 QA Judge 均为 deepseek-flash**

Run:

```bash
cd /Users/chezi/code/java/pf_agent
git grep -n 'deepseek-flash' -- README.md pf_agent/agent
```

Expected: 输出包含主 Agent `application.yml`、QA `evaluate.py`、根 README 和 QA README 四处配置或说明。

- [x] **Step 3: 检查 Python 文件语法**

Run:

```bash
cd /Users/chezi/code/java/pf_agent/pf_agent/agent/qa
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import ast, pathlib; ast.parse(pathlib.Path("evaluate.py").read_text(encoding="utf-8"))'
```

Expected: 命令无输出且退出码为 0。

- [x] **Step 4: 检查最终改动**

Run:

```bash
cd /Users/chezi/code/java/pf_agent
git diff --check
git status --short
git log --oneline -4
```

Expected: `git diff --check` 无输出；`git status --short` 无输出（所有改动与过程文档均已提交，工作区干净）；最近提交包含四个任务提交（`df490d2`、`681de41`、`b3d1bed`、过程文档提交）。三处型号修改已包含在 `681de41` / `b3d1bed` 中，不再以未提交 diff 形式出现。
