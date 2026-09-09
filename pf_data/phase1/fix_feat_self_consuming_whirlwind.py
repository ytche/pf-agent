"""
fix_feat_self_consuming_whirlwind.py — 自残旋风标题跨行合并+补闭合星（P0 级，专长6.md）

背景（2026-08-02 KN026 复算审计，P0 级）：专长6.md 自残旋风条目丢 1 条。
标题形态：
  `**自残旋风（All-Consuming \nSwing）[战斗]`
跨行 EN 由 `_merge_cross_line_en` 合并为 `**自残旋风（All-Consuming Swing）[战斗]`，
但**缺闭合星**——FC-1q（`_RE_TITLE_EN_TYPE`）组3 `[战斗]` 后须 `\s*\*\*\s*$`
而实际行尾是 `]` → 失配 → 标题行并入相邻条目正文丢失。
对照同页熊之平衡（产出 ✓）：`**熊之平衡（Bears Balance）[战斗]**`（有闭合星）。

修复（改源数据不改脚本，对齐熊之平衡形态）：
  `**自残旋风（All-Consuming \nSwing）[战斗]` 跨行合并 + 补闭合星
  → `**自残旋风（All-Consuming Swing）[战斗]**`

验证：1 处转换、-1 行、行尾类型不变、继承行字节守恒、标题落位、残留 0、
重跑 pipeline + verify + pytest。

用法：python3 fix_feat_self_consuming_whirlwind.py
"""

import sys

PATH = "pf_rules_md_organized/专长6.md"

# 跨行标题精确锚定（首行尾 + 次行整行）
HEAD = "**自残旋风（All-Consuming "
TAIL = "Swing）[战斗]"
NEW_TITLE = "**自残旋风（All-Consuming Swing）[战斗]**"


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
            # 合并行保留首行行尾（混合 CRLF/LF 文件逐行守恒）
            out.append(NEW_TITLE + ("\r" if lines[i].endswith(b"\r") else ""))
            report.append(f"L{i+1}-L{i+2} 自残旋风：跨行合并 + 补闭合星"
                          "（FC-1q 组3 半角 [战斗] 需闭合星，对齐熊之平衡）")
            fixed += 1
            i += 2
            continue
        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 1, f"预期修复 1 处，实际 {fixed}"
    assert len(out) == n - 1, f"预期 {n-1} 行（-1），实际 {len(out)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    assert any(NEW_TITLE in l.decode("utf-8") for l in new_lines), "自残旋风未落位"
    # 残留检查：旧 2 行形态（HEAD 独立行 / HEAD\nTAIL）与旧 1 行形态
    # （HEAD+TAIL 无闭合星）均不应存在——注意新标题以 HEAD 开头，须行级精确匹配
    full = out_bytes.decode("utf-8", errors="replace")
    for l in new_lines:
        l_r = l.decode("utf-8").rstrip("\r")
        assert l_r != HEAD, "旧首行残留"
        assert l_r != f"{HEAD}{TAIL}", "旧无闭合星形态残留"
    assert f"{HEAD}\n{TAIL}" not in full, "旧跨行形态残留"

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
