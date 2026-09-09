"""
fix_feat_improvisational_healer.py — 即兴治疗者字段星后补冒号（P0 级，冒险者的军械库2_专长.md）

背景（2026-08-02 KN026 复算审计，P0 级）：冒险者的军械库2_专长.md
即兴治疗者条目丢 1 条。标题行首有空格但 M13a `^[ \t]*` 消费后独立
（`**即兴治疗者(Improvisational Healer)**`，`_RE_TITLE` 匹配 ✓），
条目被「纯描述节」过滤（feat.py L1110-1115，同 KN065 根因）：
字段形态为星后空格（`**出处** `、`**要求** `）→ `_RE_FIELD_IN_TEXT`
三分支全失配 → 整条被过滤。对照同文件铁蟒出洞（产出 ✓）：
`**先决条件：**` / `**专长效果：**` 星内冒号形态。

修复（改源数据不改脚本，对齐铁蟒出洞字段形态）：
  `**出处** 《冒险者的武具库2》…` → `**出处**：《冒险者的武具库2》…`
  `**要求** `                        → `**要求**：`
（2 行改动，行数/行尾不变）

验证：2 处转换、行数与 CRLF 不变、继承行字节守恒、冒号落位、残留 0、
重跑 pipeline + verify + pytest。

用法：python3 fix_feat_improvisational_healer.py
"""

import sys

PATH = "pf_rules_md_organized/专长/冒险者的军械库2_专长.md"

# 目标字段行前缀：星后空格 → 星后冒号（行内其余内容与行尾保留原样）
PREFIXES = [
    ("**出处** ", "**出处**："),
    ("**要求** ", "**要求**："),
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
        matched = False
        for old, new in PREFIXES:
            if t_r.startswith(old):
                take_raw(i)
                out.append(new + t_r[len(old):] + ("\r" if lines[i].endswith(b"\r") else ""))
                report.append(f"L{i+1} `{t_r[:40]}…` → `{new}{t_r[len(old):40]}…`")
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
    assert "**出处**：《冒险者的武具库2》" in full, "出处冒号未落位"
    assert "**要求**：" in full, "要求冒号未落位"
    assert "**出处** 《" not in full and "**要求** \n" not in full, "旧形态残留"

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
