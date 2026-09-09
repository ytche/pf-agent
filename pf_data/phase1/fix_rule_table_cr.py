#!/usr/bin/env python3
"""规则源数据表格行独立 \\r 定位符清洗脚本（KN191 修复，2026-08-09）。

背景：
  与专长 fix_feat_table_cr.py / 技能 fix_skill_table_cr.py 同源：CHM 转换产物
  中表格行的 EN/CN 两列之间用独立 `\\r`（U+000D）定位，`splitlines()` 把独立
  `\\r` 当换行符，表格行被腰斩成两半——首段残留上一行行尾，条目标题/字段
  起点被吞。规则模块为全库最大灾区（scan 实测 37,613 处/195 文件，另计行级
  裸 CR 9324；超高危 page_601 1160 / page_301 1350 / 玩家手册4 1045 /
  page_598 777）。

修复方式（改源数据，不动解析器——KN158/139 先例）：
  `\\r(?!\\n)` → 空格。行尾 `\\r\\n`（CRLF 行尾）的 `\\r` 因后跟 `\\n` 被
  排除，不破坏行尾约定（源数据 CRLF，禁止规范化——否则 git diff 整文件
  污染，审计留痕不可读）。

范围：规则批次扫描清单精确 rel（prepare_batches.json 的 files——判别器
同源，pipeline 实际消费文件）。冻结模块文件零触碰（KN136 禁令）。

规则：
  - 只替换行中独立 `\\r`（后跟非 `\\n`），CRLF 行尾不动
  - 幂等：替换后行中无 `\\r`，重复运行修复 0 处
  - 全库扫描，只报有修复的文件

用法：
  python3 fix_rule_table_cr.py [--dry-run]
"""
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
BATCHES = BASE / "vectorizer" / "exploration" / "rule" / "prepare_batches.json"
ORG = BASE / "pf_rules_md_organized"

# 行中独立 \r（后跟非 \n）→ 空格；CRLF 行尾的 \r\n 排除
_CR_RE = re.compile(r"\r(?!\n)")


def source_files() -> list:
    """规则批次扫描清单 rel（prepare_batches.json files，与判别器同源）。"""
    batches = json.loads(BATCHES.read_text(encoding="utf-8"))
    rels = []
    for b in batches:
        rels.extend(b.get("files", []))
    hits = []
    for rel in rels:
        p = ORG / rel.removeprefix("pf_rules_md_organized/")
        if p.exists():
            hits.append(p)
        else:
            print(f"  !!! 清单 rel 缺失: {rel}")
    return sorted(hits)


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    total = 0
    per_file = {}
    files = source_files()
    for p in files:
        # newline="" 保留 CRLF 行尾（源数据为 CRLF，禁止规范化）
        text = p.open(encoding="utf-8", newline="").read()
        new, n = _CR_RE.subn(" ", text)
        if n:
            per_file[str(p.relative_to(BASE))] = n
            total += n
            if not dry_run:
                p.open("w", encoding="utf-8", newline="").write(new)
    mode = "DRY-RUN" if dry_run else "FIXED"
    print(f"[{mode}] 扫描 {len(files)} 个规则来源文件，\\r 定位符清洗 {total} 处，涉及 {len(per_file)} 个文件")
    for name, n in sorted(per_file.items(), key=lambda x: -x[1])[:15]:
        print(f"  {n:5d}  {name}")
    if len(per_file) > 15:
        print(f"  …其余 {len(per_file) - 15} 文件略")


if __name__ == "__main__":
    main()
