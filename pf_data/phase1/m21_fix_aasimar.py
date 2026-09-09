# -*- coding: utf-8 -*-
"""M21：神裔奇物章节标题星壳断裂修复（KN120 项，2026-08-04）

page_129 L685 `**神裔奇****物（****Aasimar**** Magic Items****）******`
（HTML 加粗拆裂产物：「神裔奇」+「物（Aasimar Magic Items」星壳断裂）：
- 标题拆错 → 「神裔奇」伪条目（race_feat len 22，正文=星壳残片）
- 章节关键字「魔法物品」被星壳拆裂 → 章节识别失败 → 天界之盾/净土之盾/
  威吓之环等奇物条目被误标 race_feat（应在 race_item 章节态）

修复：断裂星壳合并为 `**神裔奇物（****Aasimar Magic Items****）**`
（对齐同页「神裔专长（Aasimar Feats）」章节形态）。

执行教训（pf-organized-source-crlf-convention）：二进制读写，行尾原样保留。
用法：python3 m21_fix_aasimar.py（幂等：已修项自动跳过）
"""
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
PATH = BASE / "pf_rules_md_organized" / "种族" / "常见种族" / "神裔" / "page_129.md"

# (旧串, 新串, 描述)；CRLF/LF 两种行尾同串（星壳断裂在行中部，行尾无关）
FIXES: list[tuple[str, str, str]] = [
    ("**神裔奇****物（****Aasimar**** Magic Items****）******",
     "**神裔奇物（****Aasimar Magic Items****）******",
     "L685 星壳断裂合并：神裔奇+物（Aasimar+Magic Items → 神裔奇物（Aasimar Magic Items）"),
]


def main() -> None:
    if not PATH.exists():
        print(f"[缺失] {PATH}")
        return
    data = PATH.read_bytes()
    before_crlf = data.count(b"\r\n")
    applied = 0
    for old, new, desc in FIXES:
        old_b, new_b = old.encode("utf-8"), new.encode("utf-8")
        n = data.count(old_b)
        if n == 0:
            print(f"[跳过/缺失] {desc}")
            continue
        if n > 1:
            print(f"[跳过/重复] {desc}: 出现 {n} 次")
            continue
        data = data.replace(old_b, new_b)
        applied += 1
        print(f"[应用] {desc}")
    PATH.write_bytes(data)
    # 校验
    after_crlf = data.count(b"\r\n")
    new_title = data.count("**神裔奇物（****Aasimar Magic Items****）******".encode("utf-8"))
    broken = data.count("神裔奇****物".encode("utf-8"))
    print(f"应用 {applied}/{len(FIXES)} 处 | CRLF {before_crlf}→{after_crlf} "
          f"| 修复后标题 {new_title} 处 | 断裂形态残留 {broken} 处")
    if applied == 1 and after_crlf == before_crlf and new_title == 1 and broken == 0:
        print("[校验] 全部到位")
    else:
        print("[校验] 需人工复核（CRLF 计数或残留异常）")


if __name__ == "__main__":
    main()
