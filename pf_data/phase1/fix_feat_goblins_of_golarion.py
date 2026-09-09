"""
fix_feat_goblins_of_golarion.py — 格拉里昂的地精_专长.md + 专长48.md 屠狗者标题归一（P0 级，est=4 got=3 丢 1）

背景（2026-08-02 KN026 复算审计，P0 级）：格拉里昂的地精_专长.md（《格拉里昂的
地精》专长页，整理产物）与根级 专长48.md（同源副本）各 4 个专长条目、各丢 1 条
（屠狗者，猎马人）。根因形态：

  `**屠狗者，猎马人** Dog Killer, Horse Hunter` —— **中文名含逗号 `，`**。
  M2 `_RE_STAR_OUTSIDE_EN` 组1 `[一-鿿/]{2,}` 不含 `，` → 组1 匹配到
  `屠狗者` 后遇 `，` 失配（星外英文名未并入星内）→ FC-3/FC-4 组1 同样
  不含 `，` → 全分支失配 → 条目丢弃。
  对照战歌手（无逗号，成功）：`**战歌手**battle singer` → M2 并入
  `**战歌手 battle singer**` → FC-3 识别产出。

修复（改源数据不改脚本，对齐 KN057-KN062 归一先例）：
  2 个文件屠狗者标题跨行合并并归一为 `_RE_TITLE` 标准闭合形态
  （组1 `[^*\n]+?` 含 `，`、组2 含逗号/空格均容忍）：
    `**屠狗者，猎马人（Dog Killer, Horse Hunter）**`
  → `_RE_TITLE` 匹配 → 独立产出（title=屠狗者，猎马人）。

验证：2 文件各 1 处转换、各 -1 行、CRLF 计数不变、继承行字节守恒、
屠狗者落位、残留 0、重跑 pipeline + verify + pytest。

用法：python3 fix_feat_goblins_of_golarion.py
"""

import sys

# （整理产物, 根级同源副本）
PATHS = ["pf_rules_md_organized/专长/格拉里昂的地精_专长.md",
         "pf_rules_md_organized/专长48.md"]

# 标题跨行处精确锚定（首行尾 + 次行整行）
HEAD = "**屠狗者，猎马人** Dog Killer, Horse "
TAIL = "Hunter"
NEW_TITLE = "**屠狗者，猎马人（Dog Killer, Horse Hunter）**"


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
        if t_r == HEAD:
            n1 = lines[i + 1].decode("utf-8")
            assert n1.rstrip("\r") == TAIL, f"续行异常: {n1[:40]!r}"
            take_raw(i)
            take_raw(i + 1)
            # 合并行保留首行行尾（专长48.md 混合 CRLF/LF：HEAD 为 CRLF → 新行 CRLF）
            out.append(NEW_TITLE + ("\r" if lines[i].endswith(b"\r") else ""))
            report.append(f"L{i+1}-L{i+2} 屠狗者：标题跨行合并 + EN 并入星内"
                          "（`_RE_TITLE` 组1 容忍中文逗号）")
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
    assert any(NEW_TITLE in l.decode("utf-8") for l in new_lines), "屠狗者未落位"
    # 残留检查：旧 2 行形态与旧 1 行形态（若有重复）均不应存在
    full = out_bytes.decode("utf-8", errors="replace")
    assert HEAD not in full and f"{HEAD}{TAIL}" not in full, "屠狗者旧形态残留"

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
    # 可选参数过滤：只处理指定路径（脚本非幂等，已修文件需跳过）
    targets = sys.argv[1:] if len(sys.argv) > 1 else PATHS
    for p in targets:
        if p not in PATHS:
            print(f"跳过未知路径：{p}")
            continue
        rc |= fix_file(p)
    return rc


if __name__ == "__main__":
    sys.exit(main())
