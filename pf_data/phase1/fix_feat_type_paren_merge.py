#!/usr/bin/env python3
"""专长源数据 4+2 星类型括号归一脚本（K5 步骤 C 补充，2026-08-02）。

背景：
  fix_feat_title_parens.py 把 `**中文**** English****（类型）**` 规范化为
  `**中文（English）****（类型）**`（类型括号前 4 星、后 2 星）。该形态
  处于解析器归一链的夹缝：`_RE_QUAD_STAR` 需（类型）前后各 4 星（尾 6 星
  形态 page_361 等已正常），4+2 星不匹配 → M13a 粘连拆行把 `**（类型）**`
  当正文拆到标题后，类型残留正文首行、feat_type 丢失（page_203 憎恶集中
  实证：elided + 正文首行 `（战斗专长）**`）。

修复方式（改源数据，不动解析器——攻坚决议）：
  `**中文（English）****（类型）**` → `**中文（English）（类型）**`
  （标准 FC-1q 标题形态，类型并入标题括号）。

规则：
  - 标题部分：中文开头、括号内含英文（≥1 字母）
  - 中间恰好 4 星；类型括号 1~12 字、禁嵌套括号
  - `(?!\\*)` 排除尾 6 星形态（`****（类型）******`，QUAD_STAR 已有
    成功路径，page_361 实证），幂等不误伤
  - 幂等：替换后（类型）前无 4 星，重复运行修复 0 处

用法：
  python3 fix_feat_type_paren_merge.py [--dry-run]
"""
import re
import sys
from pathlib import Path

TARGET_DIR = Path(__file__).parent / "pf_rules_md_organized" / "专长"

# **中文（EN）****（类型）** —— 中间 4 星、尾 2 星且后无星
TYPE_MERGE_RE = re.compile(
    r"\*\*([一-鿿][^*\n]*?[（(][^）)]*[A-Za-z][^）)]*[)）])\*\*\*\*([（(][^（()）]{1,12}[)）])\*\*(?!\*)",
)


def fix_text(text: str) -> tuple[str, int]:
    def repl(m: re.Match) -> str:
        return f"**{m.group(1)}{m.group(2)}**"

    new, n = TYPE_MERGE_RE.subn(repl, text)
    return new, n


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    total = 0
    per_file = {}
    files = sorted(TARGET_DIR.rglob("*.md"))
    for p in files:
        # newline="" 保留 CRLF 行尾（同 fix_feat_glue / fix_feat_title_parens）
        text = p.open(encoding="utf-8", newline="").read()
        new, n = fix_text(text)
        if n:
            per_file[str(p.relative_to(TARGET_DIR))] = n
            total += n
            if not dry_run:
                p.open("w", encoding="utf-8", newline="").write(new)
    mode = "DRY-RUN" if dry_run else "FIXED"
    print(f"[{mode}] 扫描 {len(files)} 个文件，类型括号归一 {total} 处，涉及 {len(per_file)} 个文件")
    for name, n in sorted(per_file.items(), key=lambda x: -x[1]):
        print(f"  {n:4d}  {name}")


if __name__ == "__main__":
    main()
