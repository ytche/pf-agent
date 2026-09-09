#!/bin/bash
# ==============================================================================
# 装备 chunk 重生成 + 完整验证链单入口（v2.2 决策 B：收敛为 cicd verify）
#
# 用法：
#   cd pf_data/phase1
#   bash regen_equipment_chunks.sh
#
# 设计（决策 B，2026-08-03）：
#   - 验证链单一事实源 = python3 -m vectorizer.cicd verify --category equipment
#     （pytest 全量 → pipeline 含 finalize → verify_equipment 八检查 → 数据
#     不变量），本地跑 = CI 跑同一命令同一结果（消除双份编排漂移）。
#   - 本脚本仅做 cwd 收敛 + 命令转发，不再维护独立步骤清单——教训 B1
#     （后处理漏跑即回归）由 pipeline finalize 结构保证，教训 B 双份编排
#     漂移由单命令保证。
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHONPATH=. python3 -m vectorizer.cicd verify --category equipment
