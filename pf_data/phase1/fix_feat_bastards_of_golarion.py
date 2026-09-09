"""
fix_feat_bastards_of_golarion.py — 格拉里昂的混种_专长.md 2 处标题跨行括号合并（P0 级，est=3 got=1 丢 2）

背景（2026-08-02 KN026 复算审计，P0 级）：格拉里昂的混种_专长.md（《格拉里昂的
混种》专长页，未整理 → 格拉里昂的混种 整理产物）3 个条目，实时 got=1 丢 2。
溯源真相是「3 条全吞进 1 chunk」：孤狼独舞/叛逆打击/阴招大师内容全在
孤狼独舞 chunk（title=孤狼独舞）内。根因形态：

  `**叛逆打击(战斗)PFS可(Betraying Blow ` + `(Combat))**` —— 标题 EN 跨行处
  **换行后是半角括号 `(`**。`_merge_cross_line_en`（`([a-zA-Z,])[ \t]*\n[ \t]*([a-zA-Z])`）
  要求换行后首字符为字母，遇 `(Combat)` 不合并 → 标题保持 2 行：行 1 无闭合星
  `**`、行 2 不以 `**` 开头 → split 全分支失配 → 条目内容并入前一条目。
  对照孤狼独舞（成功）：`Solo \nManeuvers (Combat))` 换行后是字母 `M` →
  跨行合并成功 → 单行 `**孤狼独舞(战斗)PFS可(Solo Maneuvers (Combat))**`
  → FC-4 `_RE_TITLE_TYPE_EN`（组 1 中文、组 2 半角括号类型、组 3
  `[A-Za-z][^*\n]*?` 容忍 PFS可 噪声与内嵌半角括号）匹配 → 独立产出。

修复（改源数据不改脚本，对齐 KN057-KN061 归一先例）：
  2 处标题跨行合并成单行（行内合并，各 -1 行）：
    `**叛逆打击(战斗)PFS可(Betraying Blow (Combat))**`
    `**阴招大师（战斗）Dirty Trick Master (Combat)**`
  合并后与孤狼独舞同路径 FC-4 识别 → 3 条各自独立产出 → got 1→3 = est 3。

验证：2 处转换、36 → 34 行（各 -1）、LF-only 不变（CRLF 0）、继承行字节守恒、
3 个中文名落位、标题跨行形态残留 0、重跑 pipeline + verify + pytest。

用法：python3 fix_feat_bastards_of_golarion.py
"""

import sys

PATH = "pf_rules_md_organized/专长/格拉里昂的混种_专长.md"

# 2 条目标标题跨行处精确锚定（首行尾 + 次行整行）
TARGETS = [
    ("**叛逆打击(战斗)PFS可(Betraying Blow ", "(Combat))**", "叛逆打击"),
    ("**阴招大师（战斗）Dirty Trick Master ", "(Combat)**", "阴招大师"),
]
CN_NAMES = ["孤狼独舞", "叛逆打击", "阴招大师"]


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
        t_r = t.rstrip("\r")
        matched = False
        for head, tail, cn in TARGETS:
            if t_r == head:
                n1 = lines[i + 1].decode("utf-8")
                assert n1.rstrip("\r") == tail, f"{cn} 续行异常: {n1[:40]!r}"
                take_raw(i)
                take_raw(i + 1)
                out.append(head + tail)
                report.append(f"L{i+1}-L{i+2} {cn}：标题跨行括号合并"
                              f"（{tail} 换行后为括号，跨行 EN 合并失配）")
                fixed += 1
                i += 2
                matched = True
                break
        if matched:
            continue
        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 2, f"预期修复 2 处，实际 {fixed}"
    assert len(out) == n - 2, \
        f"预期 {n-2} 行（2 处各 -1），实际 {len(out)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    for cn in CN_NAMES:
        assert any(l.decode("utf-8").startswith(f"**{cn}") for l in new_lines), \
            f"{cn} 未落位"
    # 标题跨行形态残留检查（`EN 尾空格\n(Combat))**` 2 行结构）
    full = out_bytes.decode("utf-8", errors="replace")
    for glued in ("Betraying Blow \n(Combat))", "Dirty Trick Master \n(Combat))"):
        assert glued not in full, f"标题跨行残留: {glued!r}"

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
