#!/bin/bash
# ==============================================================================
# 法术 chunk 重生成 + 后处理链 + 验证入口
#
# 用法：
#   cd pf_data/phase1
#   bash regen_spell_chunks.sh
#
# 红线：
#   - chunk 总数必须为 4200（含 link 后不变）
#   - pytest 264 全绿
#   - MA 增强链接 253/253
#
# 重生成后交付前，必须走完本脚本的三件套验证：
#   ① pytest（单元测试）
#   ② verify_spells.py（来源书检查）
#   ③ verify_kn011_018.py（KN011~018 专项指标）
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Step 1: 向量化重生成 ────────────────────────────────────────────────
echo "=== Step 1/4: 向量化重生成 ==="
PYTHONPATH=. python3 vectorizer/pipeline.py \
    --category spell \
    --input pf_rules_md_organized/法术 \
    --output vectorizer/output/法术

# ── Step 2: KN011 MA 增强链接 ────────────────────────────────────────────
echo "=== Step 2/4: KN011 MA 增强链接 ==="
python3 link_mythic_base_spells.py \
    --input vectorizer/output/法术/chunks.jsonl \
    --output vectorizer/output/法术/chunks.jsonl

# ── Step 3: 单元测试 ─────────────────────────────────────────────────────
echo "=== Step 3/4: pytest ==="
python3 -m pytest vectorizer/tests/ -q

# ── Step 4: 验收验证 ─────────────────────────────────────────────────────
echo "=== Step 4/4: 验收 ==="
echo "--- verify_spells ---"
PYTHONPATH=. python3 vectorizer/verify/verify_spells.py
echo "--- verify_kn011_018 ---"
PYTHONPATH=. python3 vectorizer/verify/verify_kn011_018.py

echo ""
echo "=== 全量完成 ==="
