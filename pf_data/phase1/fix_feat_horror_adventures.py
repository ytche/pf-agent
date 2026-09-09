"""
fix_feat_horror_adventures.py — 惧怖冒险HA_专长.md 4 处标题补闭合星（P0 级，est=8 got=4 丢 4）

背景（2026-08-02 KN026 复算审计，P0 级）：惧怖冒险HA_专长.md（《惧怖冒险》专长页，
未整理 → 惧怖冒险HA 整理产物）8 个专长条目，4 条丢失（敌对教团/幽灵向导/
平民守护者/扭曲之爱），全部为**故事专长**统一形态：

   `**中文（EN 跨行）（故事）` —— FC-1n 无闭合星**双括号**变体：
   标题行首 `**` + 行 2 `EN续）（类型）` 无尾闭合星。`_merge_cross_line_en`
   合并跨行 EN 后仍无闭合星 → M4 补星正则 `_RE_FC1N_NO_CLOSING_STAR`
   （`**中文（English）` 单括号形态）失配 → split `_RE_TITLE` 系列
   全部失配 → 条目丢弃。
   对照：以血蒙眼 `**以血蒙眼(Blood Spurt，战斗)**` 单括号 + 闭合星 → 产出成功。

   已验证：补闭合星后跨行 EN 合并得 `**中文（EN）（故事）**` 单行，
   FC-1q `_RE_TITLE_EN_TYPE` 匹配成功（组3 类型括号）；字段行经
   `_wrap_bare_field_labels` 已正确包裹（`　　先决条件**：` → `**先决条件**：`）。

修复（改源数据不改脚本，对齐 KN057-KN059 归一先例）：
  4 处标题续行补闭合 `**`：`Cult）（故事）` → `Cult）（故事）**` 等，
  行内替换不增删行。归一后 4 条全部为标准闭合标题（FC-1q 可识别）
  → got 4→8 = est 8。

验证：4 处转换、行数 101 不变、LF-only 不变（无 CRLF）、继承行字节守恒、
4 个中文名落位、无闭合星标题残留 0、重跑 pipeline + verify + pytest。

用法：python3 fix_feat_horror_adventures.py
"""

import sys

PATH = "pf_rules_md_organized/专长/惧怖冒险HA_专长.md"

# 4 条目标续行精确锚定（防误伤其他行）
TARGETS = {"Cult）（故事）": "敌对教团",
           "Guide）（故事）": "幽灵向导",
           "People）（故事）": "平民守护者",
           "Love）（故事）": "扭曲之爱"}
CN_NAMES = list(TARGETS.values())


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = raw.split(b"\n")
    n = len(lines)
    print(f"输入：{n} 行，CRLF {raw.count(b'\r\n')}")

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
        if t in TARGETS:
            cn = TARGETS[t]
            prev = lines[i - 1].decode("utf-8")
            assert prev.startswith("**") and "（" in prev and " " in prev, \
                f"{cn} 标题首行异常: {prev[:40]!r}"
            take_raw(i)
            out.append(t + "**")
            report.append(f"L{i+1} {cn}：标题补闭合星（FC-1n 双括号变体）")
            fixed += 1
            i += 1
            continue
        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 4, f"预期修复 4 处，实际 {fixed}"
    assert len(out) == n, f"预期行数不变（行内替换），实际 {len(out)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    full = out_bytes.decode("utf-8", errors="replace")
    for cn in CN_NAMES:
        assert any(f"**{cn}（" in l.decode("utf-8") for l in new_lines), \
            f"{cn} 未落位"
    # 无闭合星标题残留检查（`**中文（EN）（类型）` 形态，行尾非 **）
    import re
    hits = re.findall(r"^\*\*[一-鿿]{2,}（[A-Za-z][^*\n]*）（[^（）]+）$", full, re.M)
    assert not hits, f"无闭合星标题残留 {len(hits)} 处: {hits}"

    if out_bytes == raw:
        print("无变更")
        return 1

    with open(PATH, "wb") as f:
        f.write(out_bytes)
    print(f"== {PATH}：修复 {fixed} 处")
    for r in report:
        print("   ", r)
    print(f"CRLF: {raw.count(b'\r\n')} -> {out_bytes.count(b'\r\n')} "
          f"| 总行数: {n} -> {len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
