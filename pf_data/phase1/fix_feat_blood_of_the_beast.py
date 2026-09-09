"""
fix_feat_blood_of_the_beast.py — 野兽血脉BotB_专长.md 3 处正文粘连裸字段归一（P0 级，est=25 got=22 丢 3）

背景（2026-08-02 KN026 复算审计，P0 级）：野兽血脉BotB_专长.md（《野兽血脉》
专长页，未整理 → 野兽血脉BotB 整理产物）25 个井号标题条目，3 条丢失
（狡黠猛扑/剧毒注视/鼠群撕裂）。根因形态：

   `正文…猛扑先决条件：…，狐妖专长效果：…` —— 正文以动词直接粘连
   **裸字段标签**（无句号分隔）。对比同文件狐之型（成功）：`…其他形态。先决条件：…`
   正文与标签间有句号 → normalize 既有步骤拆行 + 包裹成
   `正文。\n**先决条件：**…`（text 含真字段 → 产出）。
   狡黠猛扑无标点分隔 → 不拆不包裹 → text 无真字段 → 纯描述节跳过 → 条目丢弃。

修复（改源数据不改脚本，对齐 KN057-KN060 归一先例）：
  3 处正文行拆 3 行归一（对齐狐之型产出形态）：
      `正文。`（补句号）+ `**先决条件：**值` + `**专长效果：**值`

验证：3 处转换、143 → 149 行（各 +2）、LF-only 不变（无 CRLF）、
继承行字节守恒、3 个中文名落位、正文粘连裸字段残留 0、
重跑 pipeline + verify + pytest。

用法：python3 fix_feat_blood_of_the_beast.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/野兽血脉BotB_专长.md"

CN_NAMES = ["狡黠猛扑", "剧毒注视", "鼠群撕裂"]

# 正文 + 裸字段同行粘连：`正文先决条件：值专长效果：值`
_RE_GLUED = re.compile(r"^(.+?)(先决条件：)(.+?)(专长效果：)(.+)$")


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
        m = _RE_GLUED.match(t)
        if m and m.group(1) in ("你可以在同一轮中冲锋变形并对你的对手发动猛扑",
                                "你的注视对你的敌人来说是剧毒",
                                "你和你的同伴一起撕开敌人的防御"):
            take_raw(i)
            body, pre_val, eff_val = m.group(1), m.group(3), m.group(5)
            out.append(body + "。")
            out.append(f"**先决条件：**{pre_val}")
            out.append(f"**专长效果：**{eff_val}")
            report.append(f"L{i+1} {m.group(1)[:12]}…：正文断行 + 裸字段标签包裹拆行")
            fixed += 1
            i += 1
            continue
        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 3, f"预期修复 3 处，实际 {fixed}"
    assert len(out) == n + 6, \
        f"预期 {n+6} 行（3 条各 1→3 行 +2），实际 {len(out)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    for cn in CN_NAMES:
        assert any(f"## {cn}（" in l.decode("utf-8") for l in new_lines), \
            f"{cn} 未落位"
    # 正文粘连裸字段残留检查（限 3 条修复目标；野蛮变形/幸运同形态粘连
    # 因 text 有其他真字段兜底产出成功，是合法形态不检查）
    full = out_bytes.decode("utf-8", errors="replace")
    for glued in ("猛扑先决条件：", "剧毒先决条件：", "防御先决条件："):
        assert glued not in full, f"正文粘连裸字段残留: {glued}"

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
