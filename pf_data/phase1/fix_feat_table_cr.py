#!/usr/bin/env python3
"""专长源数据表格行独立 \\r 定位符清洗脚本（K6 召回，2026-08-02）。

背景：
  CHM 转换产物中，表格行的 EN/CN 两列之间用独立 `\\r`（U+000D）定位：
  `| Armor Proficiency, Light\\r       擅长轻型盔甲 |`。解析器
  `splitlines()` 把独立 `\\r` 当换行符，表格行被腰斩成两半、各自无法
  组成条目（先决条件/效果列被吞），专长索引表条目全部丢失——41 条
  召回缺口的根因之一（page_195 专长表 ~150 行 → 0 产出）。

修复方式（改源数据，不动解析器——攻坚决议）：
  `\\r(?!\\n)` → 空格。行尾 `\\r\\n`（CRLF 行尾）的 `\\r` 因后跟 `\\n`
  被排除，不破坏行尾约定。替换后表格行变 `| EN        中文 |`，
  `splitlines` 不再腰斩，`_RE_TABLE_EN`/`_RE_TABLE_CN` 正常提取。

规则：
  - 只替换行中独立 `\\r`（后跟非 `\\n`），CRLF 行尾不动
  - 幂等：替换后行中无 `\\r`，重复运行修复 0 处
  - 全库扫描，只报有修复的文件

用法：
  python3 fix_feat_table_cr.py [--dry-run]
"""
import re
import sys
from pathlib import Path

TARGET_DIR = Path(__file__).parent / "pf_rules_md_organized" / "专长"

# 行中独立 \r（后跟非 \n）→ 空格；CRLF 行尾的 \r\n 排除
_CR_RE = re.compile(r"\r(?!\n)")


def fix_text(text: str) -> tuple[str, int]:
    new, n = _CR_RE.subn(" ", text)
    return new, n


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    total = 0
    per_file = {}
    files = sorted(TARGET_DIR.rglob("*.md"))
    for p in files:
        # newline="" 保留 CRLF 行尾（源数据为 CRLF，禁止规范化——否则
        # git diff 整文件污染，审计留痕不可读）
        text = p.open(encoding="utf-8", newline="").read()
        new, n = fix_text(text)
        if n:
            per_file[str(p.relative_to(TARGET_DIR))] = n
            total += n
            if not dry_run:
                p.open("w", encoding="utf-8", newline="").write(new)
    mode = "DRY-RUN" if dry_run else "FIXED"
    print(f"[{mode}] 扫描 {len(files)} 个文件，\\r 定位符清洗 {total} 处，涉及 {len(per_file)} 个文件")
    for name, n in sorted(per_file.items(), key=lambda x: -x[1]):
        print(f"  {n:5d}  {name}")


if __name__ == "__main__":
    main()
