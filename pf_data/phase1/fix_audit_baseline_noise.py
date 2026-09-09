#!/usr/bin/env python3
"""专长召回基线 audit_baseline.jsonl 噪声清洗脚本（K6 召回，2026-08-02）。

背景：
  audit_baseline.jsonl 是 Prepare Phase 审计提取产物（1226 原始行，
  联合去重 1072）。部分行的 name_zh 带尾随空白+全角空格
  （`严冬之击  \\u3000`）、name_en 带尾随句号（`Faerie`s Strike。`）
  或反引号（`Winter`s Strike`）。verify 对 titles 集合做**精确成员
  匹配**——噪声版 name_zh ≠ chunk title（干净版），同一专长的「干净版」
  基线行虽已命中，噪声版行却永远匹配不上（1068/1072 时剩余 4 条缺口
  全是此类）。

修复方式（清洗基线数据，不动解析器/verify 口径）：
  - name_zh：去掉尾部空白+全角空格
  - name_en：去掉尾部句号/逗号/顿号；反引号 ` → 弯引号 ’
  清洗后与同专长的干净版行按 (name_zh, name_en) 元组联合去重合并，
  基线 1072 → 1061（11 组重复噪声行合并）。

规则：
  - 只改 name_zh/name_en 两字段，其余字段（page/audit 上下文等）原样保留
  - 幂等：重复运行无变化（clean 后不再匹配噪声正则）
  - 去重取首次出现行（与 verify 的 unique 构建一致）

用法：
  python3 fix_audit_baseline_noise.py [--dry-run]
"""
import json
import re
import sys
from pathlib import Path

BASELINE = Path(__file__).parent / "vectorizer" / "exploration" / "专长" / "audit_baseline.jsonl"

_ZH_TAIL = re.compile(r"[\s　]+$")
_EN_TAIL = re.compile(r"[。，、]+$")


def clean_name(d: dict) -> dict:
    """清洗 name_zh 尾空白 / name_en 尾标点与反引号。"""
    d = dict(d)
    zh = d.get("name_zh", "")
    en = d.get("name_en", "")
    d["name_zh"] = _ZH_TAIL.sub("", zh)
    d["name_en"] = _EN_TAIL.sub("", en).replace("`", "’")
    return d


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    rows = [json.loads(l) for l in BASELINE.open(encoding="utf-8").read().splitlines() if l.strip()]
    changed = 0
    cleaned = []
    for d in rows:
        c = clean_name(d)
        if c["name_zh"] != d.get("name_zh", "") or c["name_en"] != d.get("name_en", ""):
            changed += 1
        cleaned.append(c)
    unique = {}
    for d in cleaned:
        key = (d["name_zh"], d["name_en"])
        if key not in unique:
            unique[key] = d
    mode = "DRY-RUN" if dry_run else "FIXED"
    print(f"[{mode}] 清洗噪声行 {changed}/{len(rows)}；联合去重 {len(unique)}（原 1072）")
    if not dry_run:
        BASELINE.open("w", encoding="utf-8", newline="\n").write(
            "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in cleaned)
        )


if __name__ == "__main__":
    main()
