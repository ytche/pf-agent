# docs/test-reports — 测试报告留档

收录 tester 产出的测试报告。

## 收录规则

- 仅收录**标准任务与大工程**的测试报告；轻量任务的测试结论只回消息，不留档。
- 命名：`测试报告_<主题>_<日期>.md`（日期 YYYYMMDD），与同主题方案文档（`docs/design/`）主题名对齐。
- 报告模板见 `.kimi-code/agents/tester.md`（测试对象与范围 / 测试设计 / 黑盒结果 / 白盒审计 / 缺陷清单 / 结论与建议 / 需求澄清项）。
- 同一主题多轮打回回归时，在原文档追加回归记录（轮次、修复内容、回归结论），不新建文件。
- 报告中的 Minor 缺陷由用户拍板放行后，登记到 `docs/已知问题记录.md`（KN 编号）。

流程详见 `docs/WORKFLOW.md`。

## 文档索引

| 文档 | 日期 | 主题 |
|---|---|---|
| `测试报告_SP7单体鉴权与默认持久化_20260917.md` | 2026-09-17 | SP7 单体鉴权与默认持久化（PG 默认化/用户域/JWT/前端/compose） |
| `测试报告_SP8a检索工具增强_20260918.md` | 2026-09-18 | SP8a 检索工具 J1 getEntryById / J2 searchByMetadata 参数对象化 / J3 listDataGaps |
| `测试报告_数据产物可复现构建链批1_20260918.md` | 2026-09-18 | 数据产物可复现构建链批 1（build_manifest + build.py + build_state） |
| `测试报告_SP8c条目引用链_20260918.md` | 2026-09-18 | SP8c J6 Layer 0 条目引用链（EntryResolver / resolveEntry / getEntryLinks） |
| `测试报告_SP8d_keywordSearch_20260918.md` | 2026-09-18 | SP8d keywordSearch v1（title/alias 子串匹配） |
| `测试报告_D1与KN226_book修复_20260919.md` | 2026-09-19 | D1 专长 book 中文归一 + KN226 怪物规则 book 失真修复（黑盒复测 + 白盒审计 + 边界补测） |
| `测试报告_trait_book归一_20260919.md` | 2026-09-19 | trait（背景特性）book 中文名归一（D1 同型，6 值 59 条，含 CoB en 订正）黑盒复测 + 白盒审计 + 同模块撞键补测 |
| `测试报告_发布前收口SP8b与AKN010与KN229_20260919.md` | 2026-09-19 | 发布前收口三项：SP8b J4 BookFilter / AKN-010 embedding 读超时 / KN229 THH 英文书名订正（独立复测 + 白盒审计 + 边界补测 + 两项观察核实） |
