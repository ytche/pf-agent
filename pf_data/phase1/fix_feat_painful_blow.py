"""
fix_feat_painful_blow.py — 苦痛一击井号标题括号归一（P0 级，秘术选集ArcaneAnthology_专长.md）

背景（2026-08-02 KN026 复算审计，P0 级）：秘术选集ArcaneAnthology_专长.md
苦痛一击条目丢 1 条。标题形态：
  `## 苦痛一击（Painful Blow）〔战斗〕`
M5（`_RE_HASH_TITLE`）组2 `[A-Za-z][^）)]*` 匹配 `Painful Blow` 后须
`[)）]\s*$`，但 `）` 后还有 `〔战斗〕` 尾缀 → 失配 → 标题行丢弃。
对照同文件法术抗拒（产出 ✓）：`## 法术抗拒（Spell Denial）` 无尾缀。
判别器 FC-H 同源形态，M5 注释明确「文件标题行尾非括号天然不匹配」，
`〔〕` 尾缀同样不在 M5 覆盖（M5 组3 无 `〔〕` 处理）。

修复（改源数据不改脚本，对齐法术抗拒井号形态，最小改动）：
  `## 苦痛一击（Painful Blow）〔战斗〕` → `## 苦痛一击（Painful Blow，战斗）`
M5 组2 `[A-Za-z][^）)]*` 容忍中文逗号（`Painful Blow，战斗`）→ 匹配产出
`**苦痛一击（Painful Blow，战斗）**` → `_split_paren_content` 按逗号拆：
EN=`Painful Blow`、类型=[战斗]。

验证：1 处转换、行数与行尾不变、继承行字节守恒、落位、残留 0、
重跑 pipeline + verify + pytest。

用法：python3 fix_feat_painful_blow.py
"""

import sys

PATH = "pf_rules_md_organized/专长/秘术选集ArcaneAnthology_专长.md"

OLD = "## 苦痛一击（Painful Blow）〔战斗〕"
NEW = "## 苦痛一击（Painful Blow，战斗）"


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
        if t_r == OLD:
            take_raw(i)
            out.append(NEW + ("\r" if lines[i].endswith(b"\r") else ""))
            report.append(f"L{i+1} `{OLD}` → `{NEW}`"
                          "（M5 组2 容忍逗号，`〔〕` 尾缀并入括号）")
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
