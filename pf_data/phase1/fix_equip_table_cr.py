#!/usr/bin/env python3
"""装备源数据表格行独立 \\r 定位符清洗 + 断行单位合并脚本（M4，2026-08-09）。

背景：
  CHM 转换产物中，表格行单元格内用独立 `\\r`（U+000D）+ 空格定位：
  `| Battle \\r       aspergillum\\r       圣水花洒 | 5 \\r       gp |`。
  解析器 `splitlines()` 把独立 `\\r` 当换行符，表格行被腰斩；同时字段值
  内单位被断行（`价格：10\\ngp`、`重量：44\\n磅`，KN170 68 处实测）——
  `gp`/`磅` 独立成行（CHM `<BR>` 排版残渣家族，与专长 K6 表格行 CR 同族）。

修复方式（改源数据，不动解析器——攻坚决议）：
  规则 1（同专长 fix_feat_table_cr.py）：`\\r(?!\\n)` → 空格。
    行尾 `\\r\\n`（CRLF 行尾）的 `\\r` 因后跟 `\\n` 被排除，不破坏行尾约定。
  规则 2（KN170 断行单位合并）：行内容为纯单位词（gp/GP/G/SP/CP/金币/银币/
    铜币/磅 ± 句号变体）且上一行以数字结尾 → 单位并入上一行尾（前置空格），
    本行清空。内容锚定：只看行自身形态 + 上一行数字结尾，不依赖字段上下文，
    幂等——修复后上一行以「数字 单位」结尾、单位行已空，重复运行 0 处。

规则：
  - 只替换行中独立 `\\r`（后跟非 `\\n`），CRLF 行尾不动
  - 只合并「纯单位行 + 上一行数字结尾」，正文完整行不误伤
  - 幂等：重复运行修复 0 处
  - 全库扫描，只报有修复的文件
  - newline="" 保留 CRLF 行尾（源数据为 CRLF，禁止规范化——否则
    git diff 整文件污染，审计留痕不可读）

用法：
  python3 fix_equip_table_cr.py [--dry-run]
"""
import re
import sys
from pathlib import Path

TARGET_DIR = Path(__file__).parent / "pf_rules_md_organized" / "装备_魔法物品"

# 行中独立 \r（后跟非 \n）→ 空格；CRLF 行尾的 \r\n 排除
_CR_RE = re.compile(r"\r(?!\n)")
# 纯单位行：单位词 ± 句号变体
_UNIT_RE = re.compile(r"(?:gp|GP|G|SP|CP|金币|银币|铜币|磅)[。．]?$")


def fix_text(text: str) -> tuple[str, int, int]:
    lines = text.split("\n")
    n_cr = 0
    n_unit = 0
    out = []
    for i, ln in enumerate(lines):
        # ⚠️ 行尾 \r 是 CRLF 行尾标志，必须剥离保护——split('\n') 后
        # `\r(?!\n)` 会把它当行中 \r 误替换（首次实现整文件 CRLF→LF 污染教训）
        has_cr = ln.endswith("\r")
        body = ln[:-1] if has_cr else ln
        # 规则 1：行体内 \r（行中定位符）→ 空格
        s, n = _CR_RE.subn(" ", body)
        n_cr += n
        # 规则 2：纯单位行且上一行数字结尾 → 并入上一行，本行清空（保留行尾 \r）
        if _UNIT_RE.match(s.strip()):
            if out and re.search(r"\d\s*$", out[-1].rstrip("\r")):
                out[-1] = out[-1].rstrip("\r") + " " + s.strip() + (
                    "\r" if out[-1].rstrip("\r") != out[-1] else ""
                )
                n_unit += 1
                out.append("\r" if has_cr else "")
                continue
        out.append(s + ("\r" if has_cr else ""))
    return "\n".join(out), n_cr, n_unit


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    total_cr = total_unit = 0
    per_file = {}
    files = sorted(TARGET_DIR.rglob("*.md"))
    for p in files:
        text = p.open(encoding="utf-8", newline="").read()
        new, n_cr, n_unit = fix_text(text)
        if n_cr or n_unit:
            per_file[str(p.relative_to(TARGET_DIR))] = (n_cr, n_unit)
            total_cr += n_cr
            total_unit += n_unit
            if not dry_run:
                p.open("w", encoding="utf-8", newline="").write(new)
    mode = "DRY-RUN" if dry_run else "FIXED"
    print(f"[{mode}] 扫描 {len(files)} 个文件：\\r 定位符 {total_cr} 处 + 断行单位合并 {total_unit} 处，涉及 {len(per_file)} 个文件")
    for name, (n1, n2) in sorted(per_file.items(), key=lambda x: -(x[1][0] + x[1][1])):
        print(f"  \\r {n1:4d} + 单位 {n2:3d}  {name}")


if __name__ == "__main__":
    main()
