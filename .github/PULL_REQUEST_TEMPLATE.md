---
name: Pull Request
about: 提交代码 / 数据 / 文档变更
title: ''
labels: ''
assignees: ''

---

## 变更摘要

一句话说明改了什么、为什么。

## 关联 Issue

Fixes #（如无关联 Issue 填「无」）

## 改动面（勾选）

- [ ] Java 代码（`pf_agent/agent/src/main/`）——**不改业务逻辑之外的共享层**（如需改动，列清单）
- [ ] 数据（`pf_data/`）
- [ ] 评测集（`pf_agent/agent/qa/`）
- [ ] 文档 / CI / 工程化

## 自测清单

- [ ] `cd pf_agent/agent && mvn test` 全绿（附末尾输出）
- [ ] 若改动影响回答行为：`cd pf_agent/agent/qa && python3 evaluate.py` 全量重跑，三维不回退（附结果）
- [ ] 若数据改动：已列出结构不变量并确认 `verify_*.py` 断言通过（附命令/输出）
- [ ] Java 规范自查：camelCase 无中文、方法按访问级别排序、`@Autowired`/`@Value` 字段注入、注释讲 why
- [ ] 注释/日志无 key/token；未引入不必要依赖

## 评审重点

希望 reviewer 特别关注的点 / 已知取舍。
