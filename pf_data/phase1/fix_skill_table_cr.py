#!/usr/bin/env python3
"""技能源数据表格行独立 \\r 定位符清洗脚本（KN159 修复，2026-08-07）。

背景：
  与专长 fix_feat_table_cr.py 同源：CHM 转换产物中表格行的
  EN/CN 两列之间用独立 `\\r`（U+000D）定位——
  `| 有可以下手或者下脚部分的垂直平面 (天然或人工)\\r
       如非常粗糙的岩石和树木, 未打结的绳子, 或依靠双臂引体向上 |  | 15 |`。
  技能 format `_normalize_custom` 把独立 `\\r` 归一为 `\\n`，表格行
  被腰斩成两段：第二段（无行首 `|`）混入 check 字段、行内管道符
  `|  | 15 |` 残迹残留（KN159，8/26 技能受影响）。
  专长模块已修（fix_feat_table_cr.py 2026-08-02 清洗专长目录），
  技能来源文件从未清洗——本次补上（16 文件 336 处实测）。

修复方式（改源数据，不动解析器——KN158/139 先例）：
  `\\r(?!\\n)` → 空格。行尾 `\\r\\n`（CRLF 行尾）的 `\\r` 因后跟 `\\n`
  被排除，不破坏行尾约定。替换后表格行变完整单行，
  `_RE_TABLE_ROW`（`^\\|`）正常捕获进 dc_table，check 残迹消失。

范围：技能批次扫描清单精确 rel（prepare_batches.json 的 files——
判别器 `_load_skill_scan_rels` 同源，pipeline 实际消费文件）。
根目录旧副本（如 page_192 旧版含 KN158 前全角逗号）不被消费，
不动（KN077 同型：旧副本跳过无产出影响）；冻结模块文件零触碰
（KN136 禁令）。

规则：
  - 只替换行中独立 `\\r`（后跟非 `\\n`），CRLF 行尾不动
  - 幂等：替换后行中无 `\\r`，重复运行修复 0 处
  - 全库扫描，只报有修复的文件

用法：
  python3 fix_skill_table_cr.py [--dry-run]
"""
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
BATCHES = BASE / "vectorizer" / "exploration" / "skill" / "prepare_batches.json"
ORG = BASE / "pf_rules_md_organized"

# 行中独立 \r（后跟非 \n）→ 空格；CRLF 行尾的 \r\n 排除
_CR_RE = re.compile(r"\r(?!\n)")


def source_files() -> list:
    """技能批次扫描清单 rel（prepare_batches.json files，与判别器同源）。"""
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
        # newline="" 保留 CRLF 行尾（源数据为 CRLF，禁止规范化——
        # 否则 git diff 整文件污染，审计留痕不可读）
        text = p.open(encoding="utf-8", newline="").read()
        new, n = _CR_RE.subn(" ", text)
        if n:
            per_file[str(p.relative_to(BASE))] = n
            total += n
            if not dry_run:
                p.open("w", encoding="utf-8", newline="").write(new)
    mode = "DRY-RUN" if dry_run else "FIXED"
    print(f"[{mode}] 扫描 {len(files)} 个技能来源文件，\\r 定位符清洗 {total} 处，涉及 {len(per_file)} 个文件")
    for name, n in sorted(per_file.items(), key=lambda x: -x[1]):
        print(f"  {n:5d}  {name}")


if __name__ == "__main__":
    main()
