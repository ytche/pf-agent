#!/usr/bin/env python3
"""fix_feat_title_glue_split.py — 标点后接条目标题同行拆行修复（专长/page_199.md）

根因（KN078）：源数据整理时把「标点后接条目标题」同行形态统一拆为独立行
（KN076 豭突千裂等），但狂暴撞飞标题因跨行英文名（`（Raging \nThrow…）`）
使标题特征匹配失败漏拆 → 完整条目（描述+先决+效果）同行留在狂暴投掷条目
效果值后，split 只认行首标题 → 狂暴撞飞条目被狂暴投掷吞并（仅 lb_marker
索引行残留），且狂暴投掷 benefit 吞入狂暴撞飞标题+描述。

拆行后 normalize 链自动完成剩余工作：
- `_merge_cross_line_en` 合并 `（Raging \nThrow` → `（Raging Throw`
- `_split_title_glue_paren`（M13a）拆「标题** 同行描述」
- `_split_paren_content` 剥离「，又译地狱极乐投」注记（不产类型）

字节级替换保留行尾（LF/CRLF 混合文件逐字节不动），diff 仅 1 行。
"""

from pathlib import Path

TARGET = Path("pf_rules_md_organized/专长/page_199.md")

# 1 处拆行：狂暴投掷效果文本末尾「。**狂暴撞飞（」→ 拆行
# 精确匹配上一条目效果句尾，防误伤。
SPLITS = [
    ("用于投掷。**狂暴撞飞（Raging ", "用于投掷。\n**狂暴撞飞（Raging "),
]


def main() -> int:
    data = TARGET.read_bytes()
    total = 0
    for old, new in SPLITS:
        ob, nb = old.encode("utf-8"), new.encode("utf-8")
        n = data.count(ob)
        if n == 0:
            raise SystemExit(f"未命中: {old[:30]}…（文件内容与预期不符，中止）")
        data = data.replace(ob, nb)
        total += n
    TARGET.write_bytes(data)
    print(f"完成：{TARGET} 拆行 {total} 处")
    return total


if __name__ == "__main__":
    main()
