"""cicd — 验证链统一编排（v2.2 决策 B）

regen 脚本与 CI yml 各写一份验证链 → 漂移（实证：regen Step 2 占位 2 天回归
窗口；本地验收面 ≠ CI 验收面）。收敛为单一命令承载完整验证链，本地与 CI
同一事实源：

  python3 -m vectorizer.cicd verify --category <类目>

执行链（顺序固定）：pytest 全量 → pipeline（含 finalize）→ verify 公共框架
→ 数据不变量闸口。新增类目 = 装配表（cicd/verify.py CATEGORIES）加一行。
"""
