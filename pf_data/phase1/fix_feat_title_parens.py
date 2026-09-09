#!/usr/bin/env python3
"""专长源数据无括号双星标题规范化脚本（K5 步骤 C 辅助）。

背景：
  部分专长正文标题是无括号双星形态——`**中文**** 英文**`（中文英文
  间无 `（`），解析器只认 `**中文（英文）**`，此类标题被降级为 elided
  且中文名截断（如「异变疖体」→「异变疖」），导致召回基线匹配失败
  （page_203 的 ACG 缺口 33 条主因）。

修复方式（改源数据，不动解析器——攻坚决议）：
  `**中文**** 英文**` → `**中文（英文）**`，英文内多空白压平为单空格。
  尾部 `**（标签）**`（如（战斗专长））保持原样。

规则：
  - 中文 2~12 字 + 4 星 + 英文（≥2 字母，含空格/撇号/连字符）+ 2 星
  - 幂等：替换后不再匹配
  - 全库扫描，只报有修复的文件

用法：
  python3 fix_feat_title_parens.py [--dry-run]
"""
import re
import sys
from pathlib import Path

TARGET_DIR = Path(__file__).parent / "pf_rules_md_organized" / "专长"

# **中文**** 英文**
TITLE_RE = re.compile(
    r"\*\*([一-鿿]{2,12})\*\*\*\*\s*([A-Za-z][A-Za-z0-9 .'’\-]{1,40}?)\*\*",
)


def _norm_en(en: str) -> str:
    """英文名内多空白压平为单空格。"""
    return re.sub(r"\s+", " ", en).strip()


def fix_text(text: str) -> tuple[str, int]:
    def repl(m: re.Match) -> str:
        return f"**{m.group(1)}（{_norm_en(m.group(2))}）**"

    new, n = TITLE_RE.subn(repl, text)
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
    print(f"[{mode}] 扫描 {len(files)} 个文件，规范化 {total} 处，涉及 {len(per_file)} 个文件")
    for name, n in sorted(per_file.items(), key=lambda x: -x[1]):
        print(f"  {n:4d}  {name}")


if __name__ == "__main__":
    main()
