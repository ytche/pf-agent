"""
fix_feat_inspirational_commander.py — 激励指挥官行内「出自」拆独立出处行（P0 级，任务与战役_专长.md）

背景（2026-08-02 空 text chunk 调查，P0 级）：任务与战役_专长.md 激励指挥官
chunk 空 text（正文被吞）。SOP HTML 回溯（~/.openclaw/workspace/pf_rules/
专长45.htm）：原始 HTML 标题行 = `**激励指挥官（Inspirational Commander）**`
+ 红色小字 `出自Quests and Campaigns`（同行）。原始库 pf_rules_md/专长45.md
忠实还原行内粘连；organized 根目录专长45.md 已归一为独立 `**出处：**` 行
（正常产出 ✓）；KN053 聚合重建产物（本文件）保留了粘连形态 → normalize
M1a 拆行 → `出自Quests and Campaigns` 裸行被 M6/M9 包装为
`[[fc:elided]]**出自（Quests and Campaigns）**` 伪标题 → _RE_TITLE 匹配
（无 `$` 锚定）→ elided「出自」伪条目吞掉后续正文，激励指挥官 chunk 空 text。

修复（改源数据不改脚本，对齐 organized 根目录专长45.md 已验证形态）：
  `**激励指挥官（Inspirational Commander）** 出自Quests and Campaigns`
  → 拆 2 行：
    `**激励指挥官（Inspirational Commander）**`
    `**出处：**Quests and Campaigns`

验证：1 处转换、+1 行、LF-only 不变（CRLF 0）、继承行字节守恒、
2 新行落位、旧粘连形态残留 0、重跑 pipeline + verify + pytest。

用法：python3 fix_feat_inspirational_commander.py
"""

import sys

PATH = "pf_rules_md_organized/专长/任务与战役_专长.md"

OLD = "**激励指挥官（Inspirational Commander）** 出自Quests and Campaigns"
NEW_LINES = [
    "**激励指挥官（Inspirational Commander）**",
    "**出处：**Quests and Campaigns",
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
        if t.rstrip("\r") == OLD:
            take_raw(i)
            # LF-only 文件：输出行不带 \r（行尾类型不变）
            out.extend(NEW_LINES)
            report.append(f"L{i+1} 激励指挥官：行内「出自」拆独立出处行"
                          "（对齐 organized 根目录专长45.md 已验证形态）")
            fixed += 1
            i += 1
            continue
        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 1, f"预期修复 1 处，实际 {fixed}"
    assert len(out) == n + 1, f"预期 {n+1} 行（+1），实际 {len(out)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    full = out_bytes.decode("utf-8", errors="replace")
    for nl in NEW_LINES:
        assert nl in full, f"{nl} 未落位"
    assert OLD not in full, "旧粘连形态残留"

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
