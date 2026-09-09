"""
fix_feat_halflings_of_golarion.py — 格拉里昂的半身人_专长.md 2 条无中文名标题补名（P0 级，est=11 got=9 丢 2）

背景（2026-08-02 KN026 复算审计，P0 级）：格拉里昂的半身人_专长.md
（《格拉里昂的半身人》专长页，未整理 → 格拉里昂的半身人 整理产物）
11 个裸中文标题条目（`霉咒奥术师（Arcane Jinxer）` 型，无星包裹），
2 条丢失，均为**纯英文括号标题（无中文名）**：

  `（Bolster Jinx）` / `（Worst Case Jinx）`（2 行结构：`（Bolster \nJinx）`）

中文名缺失在源数据即存在（未整理 page_572.md 同缺，CHM 提取即无）。
所有标题正则组1 均要求中文（`[一-鿿]` 等）→ 纯英文括号全分支失配 →
条目并入相邻条目正文。对照 9 条成功（裸中文行 + 括号英文）：
`_wrap_bare_titles` 包裹成 `[[fc:elided]]**中文（English）**` → 产出。

修复（改源数据不改脚本，对齐 KN057-KN063 归一先例）：
  2 条跨行合并 + 补中文名（暂译，源数据缺失，KN064 登记标注）：
    `强化霉咒（Bolster Jinx）`      —— bolster 意为「支撑、加强」，
                                      效果：持加强强韧/钢铁意志/闪电反射时霉咒减值+2
    `最坏情形霉咒（Worst Case Jinx）` —— 效果：被霉咒者有益可变效果总是最小
  与 9 条成功条目同形态（裸中文行 + 括号英文）→ 同路径 elided 包裹 → 产出。

验证：2 处转换、各 -1 行、行尾类型不变、继承行字节守恒、2 中文名落位、
残留 0、重跑 pipeline + verify + pytest。

用法：python3 fix_feat_halflings_of_golarion.py
"""

import sys

PATH = "pf_rules_md_organized/专长/格拉里昂的半身人_专长.md"

# 2 条目标跨行处精确锚定（首行尾 + 次行整行）→ 归一裸中文行（对齐 9 条成功形态）
TARGETS = [
    ("（Bolster ", "Jinx）", "强化霉咒（Bolster Jinx）"),
    ("（Worst ", "Case Jinx）", "最坏情形霉咒（Worst Case Jinx）"),
]


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
        for head, tail, new_line in TARGETS:
            if t_r == head:
                n1 = lines[i + 1].decode("utf-8")
                assert n1.rstrip("\r") == tail, f"续行异常: {n1[:40]!r}"
                take_raw(i)
                take_raw(i + 1)
                # 合并行保留首行行尾（CRLF 逐行守恒）
                out.append(new_line + ("\r" if lines[i].endswith(b"\r") else ""))
                report.append(f"L{i+1}-L{i+2} {new_line}：跨行合并 + 补中文名"
                              "（源数据缺失，暂译）")
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
    assert len(out) == n - 2, f"预期 {n-2} 行（2 处各 -1），实际 {len(out)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    for cn in ("强化霉咒（Bolster Jinx）", "最坏情形霉咒（Worst Case Jinx）"):
        assert any(l.decode("utf-8") == cn for l in new_lines), f"{cn} 未落位"
    full = out_bytes.decode("utf-8", errors="replace")
    for glued in ("（Bolster \nJinx）", "（Worst \nCase Jinx）"):
        assert glued not in full, f"纯英文括号标题残留: {glued!r}"

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
