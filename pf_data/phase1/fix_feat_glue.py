#!/usr/bin/env python3
"""专长源数据行内粘连拆行修复脚本（K5 步骤 B）。

背景：
  专长正文存在「上一专长正文结尾 + 下一专长标题同行」的粘连，
  标题不在行首导致 formats/feat.py 的标题识别逻辑不认，专长正文
  被吞成 lb_marker 碎片（page_199 的 248 处 → UC 缺口 101 条）。

修复方式（改源数据，不动解析器——攻坚决议）：
  在「正文结尾标点（。；）」后紧跟的 `**中文（英文）**` 标题前插入
  换行，使标题回到行首。英文名跨行（`（Adept \\nChampion）`）由
  formats/feat.py 的 `_merge_cross_line_en` 在 normalize 阶段自动合并。

规则：
  - 只处理「标题不在行首」的粘连：`**` 前同一行内有非空白内容
    （行首标题——`。\\n\\n**标题`——天然跳过，幂等）
  - 标题特征：`**中文（English）**`，括号内禁全角逗号（神祇赐福
    能力列表 `1：**能力（X，Sp）**：` 形态不匹配）、后置排除 `**：`
  - 字段标签（`**先决条件**：`）无括号天然不匹配，不误拆
  - 幂等：重复运行修复 0 处，可复算（git diff 兜底回退）

用法：
  python3 fix_feat_glue.py [--dry-run] [--file 相对路径]
"""
import re
import sys
from pathlib import Path

TARGET_DIR = Path(__file__).parent / "pf_rules_md_organized" / "专长"

# 粘连模式：行中「。**中文（English）〔类型〕**」。整文件匹配，是否粘连
# 由「** 前同行是否非空白」判定。
# 英文名可跨行（`（Haunted \nGnome）`——源数据换行截断），拆行时压平换行；
# 可选〔类型〕随标题带走（否则 〔战斗〕**正文 残留次行、feat_type 丢失）。
GLUE_RE = re.compile(
    r"([。；])\s*\*\*([一-鿿]{2,12})（"
    r"([A-Za-z][^，（）]*?(?:\s*\n\s*[A-Za-z][^，（）]*?)*)）"
    r"([〔［【][^〕］】]{1,8}[〕］】])?\*\*(?![:：])",
)


def fix_text(text: str) -> tuple[str, int]:
    """对全文做粘连拆行，返回 (新文本, 修复数)。"""
    fixed = 0
    out = []
    pos = 0
    for m in GLUE_RE.finditer(text):
        # 定位「**」位置（跳过标点与 \s* 空白）
        punct_end = m.start(1) + len(m.group(1))
        j = m.end(1)
        while j < len(text) and text[j].isspace():
            j += 1
        # 行首判定：** 前同一行内是否有非空白（同行粘连才拆）
        line_start = text.rfind("\n", 0, j) + 1
        if not text[line_start:j].strip():
            continue  # 行首标题（标点在上一行行尾或独立成行），跳过
        # 标点后插换行，新行从「**」开始（去前导空白）
        out.append(text[pos:punct_end])
        out.append("\n")
        pos = j
        fixed += 1
    out.append(text[pos:])
    return "".join(out), fixed


def fix_file(path: Path, dry_run: bool) -> int:
    # newline="" 保留 CRLF 行尾（源数据为 CRLF，禁止规范化——否则
    # git diff 整文件污染，审计留痕不可读）
    text = path.open(encoding="utf-8", newline="").read()
    new_text, fixed = fix_text(text)
    if fixed and not dry_run:
        path.open("w", encoding="utf-8", newline="").write(new_text)
    return fixed


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    total = 0
    per_file = {}
    files = sorted(TARGET_DIR.rglob("*.md"))
    for p in files:
        n = fix_file(p, dry_run)
        if n:
            per_file[str(p.relative_to(TARGET_DIR))] = n
            total += n
    mode = "DRY-RUN" if dry_run else "FIXED"
    print(f"[{mode}] 扫描 {len(files)} 个文件，粘连修复 {total} 处，涉及 {len(per_file)} 个文件")
    for name, n in sorted(per_file.items(), key=lambda x: -x[1]):
        print(f"  {n:4d}  {name}")


if __name__ == "__main__":
    main()
