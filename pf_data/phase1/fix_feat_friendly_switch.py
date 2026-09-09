"""
fix_feat_friendly_switch.py — 友军换位字段星后补冒号（P0 级，专长15 + 秘密探寻者SoS 双副本）

背景（2026-08-02 KN026 复算审计，P0 级）：专长15.md 与 秘密探寻者SoS_专长.md
（同源双副本）的友军换位条目各丢 1 条。标题形态本身合法：
  `**友军换位(Friendly Switch)**`（M1a 拆出独立行，`_RE_TITLE` 匹配 ✓），
但条目被「纯描述节」过滤（feat.py L1110-1115）：产出条件要求 text 含真字段
（`_RE_FIELD_IN_TEXT`：`**标签**：` 星后冒号 / `**标签：**` 星内冒号 /
行首裸 `标签：`），而友军换位字段形态为星后空格：
  `**需求** 基本攻击加值+1` / `**效果** ` → 三分支全失配 → 整条被过滤。
对照同文件通才（产出 ✓）：`**先决条件**：在5个不同的知识技能…` 星后冒号。

修复（改源数据不改脚本，对齐通才星后冒号形态）：
  `**需求** 基本攻击加值+1` → `**需求**：基本攻击加值+1`
  `**效果** `             → `**效果**：`
（2 文件 × 2 字段行，行数/行尾不变）

验证：2 文件各 2 处转换、行数与 CRLF 不变、继承行字节守恒、冒号落位、
残留 0、重跑 pipeline + verify + pytest。

用法：python3 fix_feat_friendly_switch.py
"""

import sys

# （整理产物, 同源副本）
PATHS = ["pf_rules_md_organized/专长15.md",
         "pf_rules_md_organized/专长/秘密探寻者SoS_专长.md"]

# 目标字段行：星后空格 → 星后冒号（行尾保留原样）
FIELDS = [
    ("**需求** 基本攻击加值+1", "**需求**：基本攻击加值+1"),
    ("**效果** ", "**效果**："),
]


def fix_file(path: str) -> int:
    raw = open(path, "rb").read()
    lines = raw.split(b"\n")
    n = len(lines)
    print(f"输入：{path} {n} 行，CRLF {raw.count(b'\r\n')}")

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
        for old, new in FIELDS:
            if t_r == old:
                take_raw(i)
                out.append(new + ("\r" if lines[i].endswith(b"\r") else ""))
                report.append(f"L{i+1} `{old}` → `{new}`")
                fixed += 1
                matched = True
                break
        if matched:
            i += 1
            continue
        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 2, f"预期修复 2 处，实际 {fixed}"
    assert len(out) == n, f"行数不应变化，实际 {n} -> {len(out)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    full = out_bytes.decode("utf-8", errors="replace")
    for new in ("**需求**：基本攻击加值+1", "**效果**："):
        assert new in full, f"{new} 未落位"
    for old in ("**需求** 基本攻击加值+1", "**效果** "):
        assert old not in full, f"旧形态残留: {old!r}"

    if out_bytes == raw:
        print("  无变更")
        return 1

    with open(path, "wb") as f:
        f.write(out_bytes)
    print(f"== {path}：修复 {fixed} 处")
    for r in report:
        print("   ", r)
    print(f"   CRLF: {raw.count(b'\r\n')} -> {out_bytes.count(b'\r\n')} "
          f"| 总行数: {n} -> {len(out)}")
    return 0


def main() -> int:
    rc = 0
    targets = sys.argv[1:] if len(sys.argv) > 1 else PATHS
    for p in targets:
        if p not in PATHS:
            print(f"跳过未知路径：{p}")
            continue
        rc |= fix_file(p)
    return rc


if __name__ == "__main__":
    sys.exit(main())
