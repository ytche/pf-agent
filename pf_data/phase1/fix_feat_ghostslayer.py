"""
fix_feat_ghostslayer.py — 虚幻杀手标题「专长」尾缀删除（P0 级，闹鬼专长.md）

背景（2026-08-02 KN026 复算审计，P0 级）：闹鬼专长.md 虚幻杀手条目丢 1 条
（verify est=16 got=15 差 1 对应）。标题形态：
  `**虚幻杀手（Ghostslayer）专长** `（含尾随空格）
`）` 后跟「专长」二字——`_RE_TITLE` 组1 非贪婪无法跨 `（`、
FC-1q/FC-1r 组尾须 `\s*\*\*\s*$` 而实际为「专长**」→ 全分支失配
→ 标题行并入相邻条目正文丢弃。

修复（改源数据不改脚本，对齐同文件成功条目形态）：
  `**虚幻杀手（Ghostslayer）专长** ` → `**虚幻杀手（Ghostslayer）**`
（1 行改动，行数/CRLF 不变，保留 \r 行尾）

验证：1 处转换、行数与 CRLF 不变、继承行字节守恒、标题落位、残留 0、
重跑 pipeline + verify + pytest。

用法：python3 fix_feat_ghostslayer.py
"""

import sys

PATH = "pf_rules_md_organized/闹鬼专长.md"

# 旧行（含行尾空格——rstrip(\r) 不去空格，须精确匹配）与目标
OLD = "**虚幻杀手（Ghostslayer）专长** "
NEW = "**虚幻杀手（Ghostslayer）**"


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
        if t.rstrip("\r") == OLD:
            take_raw(i)
            # 保留原行行尾（CRLF 逐行守恒）
            out.append(NEW + ("\r" if lines[i].endswith(b"\r") else ""))
            report.append(f"L{i+1} `{OLD}` → `{NEW}`"
                          "（`）` 后「专长」尾缀使标题正则全分支失配）")
            fixed += 1
            i += 1
            continue
        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 1, f"预期修复 1 处，实际 {fixed}"
    assert len(out) == n, f"行数不应变化，实际 {n} -> {len(out)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    full = out_bytes.decode("utf-8", errors="replace")
    assert NEW in full, f"{NEW} 未落位"
    assert OLD not in full, "旧形态残留"

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
