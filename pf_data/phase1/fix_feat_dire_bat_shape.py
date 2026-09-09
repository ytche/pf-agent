"""
fix_feat_dire_bat_shape.py — 凶暴蝙蝠化形正文粘连裸字段拆行（P0 级，月之血脉BotM_专长.md）

背景（2026-08-02 KN026 复算审计，P0 级）：月之血脉BotM_专长.md 凶暴蝙蝠化形
条目丢 1 条（verify est=16 got=15 差 1 对应）。标题形态合法（`_RE_TITLE`
匹配 ✓），但正文为**裸散文行内粘连**（无字段星包裹、标签非行首）：

  `你能转变成一只凶暴蝙蝠先决条件：魅力13，蝙蝠化形，＋3`
  `BAB，蝙蝠人后裔专长效果：当你使用蝙蝠化形时，可以变成一只凶暴蝙蝠。`

`_RE_FIELD_IN_TEXT` 三分支（星后冒号/星内冒号/行首裸标签）全失配 →
纯描述节过滤（feat.py L1110-1115：standard + len>150 + 无真字段）
→ 整条被过滤。对照同文件血印滑翔（产出 ✓）：`**先决条件：**＋5`
星内冒号闭合星形态 → 真字段命中保留。同 KN061（野兽血脉 BotB
「正文无标点直接粘连字段」）根因家族。

修复（改源数据不改脚本，对齐血印滑翔/KN061 拆行形态）：
  2 行拆 4 行（+2 行）：
    `你能转变成一只凶暴蝙蝠。` + `**先决条件：**魅力13，蝙蝠化形，＋3`
    `BAB，蝙蝠人后裔` + `**专长效果：**当你使用蝙蝠化形时，可以变成一只凶暴蝙蝠。`

验证：1 处转换、+2 行、LF-only 不变（CRLF 0）、继承行字节守恒、
4 新行落位、旧粘连形态残留 0、重跑 pipeline + verify + pytest。

用法：python3 fix_feat_dire_bat_shape.py
"""

import sys

PATH = "pf_rules_md_organized/专长/月之血脉BotM_专长.md"

# 跨 2 行正文粘连：首行尾（先决条件行）+ 次行整行（专长效果行）
HEAD = "你能转变成一只凶暴蝙蝠先决条件：魅力13，蝙蝠化形，＋3"
TAIL = "BAB，蝙蝠人后裔专长效果：当你使用蝙蝠化形时，可以变成一只凶暴蝙蝠。"

# 拆 4 行（对齐血印滑翔/KN061 字段星包裹形态）
NEW_LINES = [
    "你能转变成一只凶暴蝙蝠。",
    "**先决条件：**魅力13，蝙蝠化形，＋3",
    "BAB，蝙蝠人后裔",
    "**专长效果：**当你使用蝙蝠化形时，可以变成一只凶暴蝙蝠。",
]


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = raw.split(b"\n")
    n = len(lines)
    print(f"输入：{PATH} {n} 行，CRLF {raw.count(b'\r\n')}")

    out: list[str] = []
    fixed = 0
    report: list[str] = []
    fixed_orig: list[bytes] = []

    def take_raw(i: int) -> bytes:
        fixed_orig.append(lines[i])
        return lines[i]

    i = 0
    while i < n:
        t = lines[i].decode("utf-8")
        t_r = t.rstrip("\r")
        if t_r == HEAD:
            n1 = lines[i + 1].decode("utf-8")
            assert n1.rstrip("\r") == TAIL, f"续行异常: {n1[:40]!r}"
            take_raw(i)
            take_raw(i + 1)
            # LF-only 文件：输出行不带 \r（行尾类型不变）
            out.extend(NEW_LINES)
            report.append(f"L{i+1}-L{i+2} 凶暴蝙蝠化形：正文粘连裸字段拆 4 行"
                          "（字段星包裹，对齐血印滑翔/KN061）")
            fixed += 1
            i += 2
            continue
        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 1, f"预期修复 1 处，实际 {fixed}"
    assert len(out) == n + 2, \
        f"预期 {n+2} 行（1 处 2 行→4 行 +2），实际 {len(out)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    full = out_bytes.decode("utf-8", errors="replace")
    for nl in NEW_LINES:
        assert nl in full, f"{nl} 未落位"
    assert HEAD not in full and TAIL not in full, "旧粘连形态残留"

    if out_bytes == raw:
        print("无变更")
        return 1

    with open(PATH, "wb") as f:
        f.write(out_bytes)
    print(f"== {PATH}：修复 {fixed} 处")
    for r in report:
        print("   ", r)
    print(f"   CRLF: {raw.count(b'\r\n')} -> {out_bytes.count(b'\r\n')} "
          f"| 总行数: {n} -> {len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
