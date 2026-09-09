"""
fix_feat_style_page1564.py — page_1564 流派专长 3 处标题归一（P0 级）

背景（2026-08-02 KN026 复算审计，P0 级）：page_1564.md（流派专长一览，
判别器 est=3 全丢）3 处标题形态异常：

1. 恶魔之型 L753-754（CRLF+LF 跨行）：
   `**恶魔之型（Demonic Style）**** (战斗, ` + `流派)**`
   四星 + 空格 + 半角括号类型跨行：`_fix_quadruple_star` 不处理
   （`**** ` 带空格非相邻 4 星）、`_fix_quad_star_halfparen` 失配
   （`****(` 须紧贴）、M1a 拆「出自」不适用 → `_wrap_bare_titles`
   双括号包裹 `[[fc:elided]]**恶魔之型（（Demonic Style））**` →
   双重括号 + 尾 `）**` 使 `_RE_TITLE` 组2 失配 → 整条丢弃。
2. 海豚流 L956-957：同恶魔之型形态。
3. 电鳗导管 L1242（LF 单行）：
   `**电鳗导管（战斗）（Electric Eel （Conduit）****）**`
   `（Conduit）` 后 4 星残留：`_RE_QUAD_STAR` 需 `****内容****` 成对、
   `_fix_quad_star_halfparen` 需 `****（` → 均失配 → wrap_bare_titles
   双括号包裹缺尾星 → 全分支失配丢弃。

修复（改源数据不改脚本，对齐同页成功形态）：
  恶魔之型/海豚流 → 归一为同页恶魔冲击产出形态（FC-1q）：
    `**恶魔之型（Demonic Style）（战斗）**` / `**海豚流（Dolphin Style）（战斗）**`
    （跨行合并 -1 行，保留首行行尾 CRLF）
  电鳗导管 → 去 4 星归一 FC-1r 双括号形态：
    `**电鳗导管（战斗）（Electric Eel （Conduit））**`

验证：3 处转换、-2 行、CRLF 守恒、继承行字节守恒、3 标题落位、残留 0、
重跑 pipeline + verify + pytest。

用法：python3 fix_feat_style_page1564.py
"""

import sys

PATH = "pf_rules_md_organized/专长/流派专长一览/page_1564.md"

# 跨行合并标题（首行尾 + 次行整行）→ FC-1q 双括号形态
MERGES = [
    ("**恶魔之型（Demonic Style）**** (战斗, ", "流派)**",
     "**恶魔之型（Demonic Style）（战斗）**"),
    ("**海豚流（Dolphin Style）**** (战斗, ", "流派)**",
     "**海豚流（Dolphin Style）（战斗）**"),
]
# 单行替换 → FC-1r 双括号形态。
# 注：内嵌 `（Conduit）` 的闭括号须改半角 `(Conduit)`——FC-1r 组3
# `[^）]*` 容忍半角括号对但被全角 `）` 截断（组3 吞 `（Conduit` 后
# `[)）]` 吃 `）`、行尾 `）**` 残留 → 整行失配）。
REPLACES = [
    ("**电鳗导管（战斗）（Electric Eel （Conduit）****）**",
     "**电鳗导管（战斗）（Electric Eel (Conduit)）**"),
    ("**电鳗导管（战斗）（Electric Eel （Conduit））**",
     "**电鳗导管（战斗）（Electric Eel (Conduit)）**"),
]


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = raw.split(b"\n")
    n = len(lines)
    print(f"输入：{PATH} {n} 行，CRLF {raw.count(b'\r\n')}")

    out: list[str] = []
    fixed = 0
    merges_done = 0
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
        for head, tail, new_line in MERGES:
            if t_r == head:
                n1 = lines[i + 1].decode("utf-8")
                assert n1.rstrip("\r") == tail, f"续行异常: {n1[:40]!r}"
                take_raw(i)
                take_raw(i + 1)
                # 合并行保留首行行尾（CRLF 逐行守恒）
                out.append(new_line + ("\r" if lines[i].endswith(b"\r") else ""))
                report.append(f"L{i+1}-L{i+2} {new_line}：跨行合并 + 四星去重"
                              "+ 类型括号后置（FC-1q 对齐恶魔冲击）")
                fixed += 1
                merges_done += 1
                i += 2
                matched = True
                break
        if matched:
            continue
        for old, new_line in REPLACES:
            if t_r == old:
                take_raw(i)
                out.append(new_line + ("\r" if lines[i].endswith(b"\r") else ""))
                report.append(f"L{i+1} {new_line}：去 4 星残留（FC-1r 双括号）")
                fixed += 1
                i += 1
                matched = True
                break
        if matched:
            continue
        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证（可重入：脚本非幂等，已修形态不再匹配）----
    assert fixed >= 1, f"预期至少修复 1 处，实际 {fixed}"
    assert len(out) == n - merges_done, \
        f"预期 {n - merges_done} 行（{merges_done} 处合并各 -1），实际 {len(out)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    full = out_bytes.decode("utf-8", errors="replace")
    for t in ("**恶魔之型（Demonic Style）（战斗）**",
              "**海豚流（Dolphin Style）（战斗）**",
              "**电鳗导管（战斗）（Electric Eel (Conduit)）**"):
        assert t in full, f"{t} 未落位"
    for glued in ("**** (战斗, \n流派)", "****（Conduit）****）"):
        assert glued not in full, f"旧形态残留: {glued!r}"

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
