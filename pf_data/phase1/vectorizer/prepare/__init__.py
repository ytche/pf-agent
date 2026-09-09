"""vectorizer.prepare — Prepare Phase 审计工具包（v2.2 决策 G 参数化迁移）

Prepare Phase 三闸口（k3 勘探审计）从 `docs/专长/t63_*.py` 站点脚本迁入本包，
路径与类目语义参数化，跨模块复用走「骨架通用 + 类目语义表注册」（categories.py）：
  - census.py     T6.3 raw_example 逐字普查（底座，firstlast/phantom 复用）
  - firstlast.py  T6.3 first/last_entry 自包含检查
  - phantom.py    T6.3 phantom 逐条取证（STOP 语义表按类目注册）

用法（python3 -m 模块式，默认参数兼容专长历史行为）：
  python3 -m vectorizer.prepare.census [--merged <per_file.jsonl>] [--source <源根>]
  python3 -m vectorizer.prepare.firstlast
  python3 -m vectorizer.prepare.phantom [--category feat] [--out <verdicts.json>]
"""
