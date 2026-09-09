"""
fix_feat_41.py — 专长41.md 7 处标题形态归一（P0 级，est=50 got=43 丢 7）

背景（2026-08-02 KN026 复算审计，P0 级）：专长41.md（外星人种族团队专长页，
根级文件）50 个专长条目，7 条丢失（密集阻击/上下合围/协调轰击/效死输忠/
群体威吓/纯种/死亡翻滚）。两种根因形态：

1. 标题闭合星 + 致谢句同行粘连（6 处）：`**密集阻击（Barrage
   of Styles）〔战斗，团队〕**｜本条翻译致谢 **愚
   者**。`——`_RE_PFS_IMG` 剥离图片后，行内出现两个 `**` 对
   （标题闭合星 + 致谢人名星），split 标题解析星配对错位 → 条目丢弃。
   对照：图片+换行+标题形态（狠辣借机/共享记忆，致谢同样同行）产出成功
   ——区别在标题行以 `**` 开头时致谢进 text 正常消化。
2. 死亡翻滚：`**死亡翻滚（Death
   Roll）〔战斗〕` 无闭合星 + 无图片标记 + 续行 `***描述*`（3 星包裹）
   ——跨行 elided 变体（对齐位面冒险PA 暗影风暴形态）。

修复（改源数据不改脚本，对齐 KN052-KN055 源数据归一先例）：
  1. 6 处致谢句剥离为独立行（标题闭合星后断行）——致谢行短且含星，
     normalize 吞入条目 text（对齐狠辣借机产出 text 开头即致谢句）；
     致谢人名跨行（密集阻击 `愚 \n者`）折叠为一行
  2. 死亡翻滚：补闭合 `**` + 3 星描述剥 2 星 → `*描述*`

验证：7 处转换、377 → 366 行（合并 11 行）、CRLF 121 不变、继承行字节守恒、
7 中文名落位、`**X**｜本条翻译致谢` 粘连残留 0、重跑 pipeline + verify + pytest。

用法：python3 fix_feat_41.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长41.md"

CN_NAMES = ["密集阻击", "上下合围", "协调轰击", "效死输忠", "群体威吓", "纯种", "死亡翻滚"]

# 带致谢的 6 条：首行 `**中文（EN 断行`，续行 `EN续）〔类型〕**｜本条翻译致谢 **人名…`
# 按条名精确匹配（专长41 条目名唯一，逐条断言更稳）
_RE_TITLE_START = re.compile(
    r"^(.*?\*\*)(密集阻击|上下合围|协调轰击|效死输忠|群体威吓|纯种)（([^\n]*)$")
# 致谢行内人名跨行折叠（`**愚 \n者**。` → `**愚 者**。`）
_RE_THANKS = re.compile(r"^\s*｜本条翻译致谢 \*\*([^*\n]+)$")
_RE_THANKS_CONT = re.compile(r"^([^*\n]+)\*\*。$")


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

        def emit_orig(line: str) -> str:
            """修复行保留原行行尾（首行 CRLF 不变，续行 LF）。"""
            return line + ("\r" if t.endswith("\r") else "")

        # ---- 1) 致谢粘连标题 6 处 ----
        m = _RE_TITLE_START.match(t_r)
        if m:
            prefix, cn, en1 = m.group(1), m.group(2), m.group(3)
            n1 = lines[i + 1].decode("utf-8").rstrip("\r")
            # 续行：`EN续）〔类型〕**｜本条翻译致谢 **人名`（密集阻击人名跨行）
            m2 = re.match(r"^([^*\n]*?)〔([^〕]+)〕\*\*｜本条翻译致谢 \*\*([^*\n]*)$", n1)
            # 纯种无类型括号：`Breed）**｜本条翻译致谢 **犭良人**。`
            m3 = re.match(r"^([^*\n]*?)(?:）〔([^〕]+)〕)?\*\*｜本条翻译致谢 \*\*([^*\n]*\*\*。)$", n1)
            if m2:
                en2, typ, thanks1 = m2.group(1), m2.group(2), m2.group(3)
                take_raw(i); take_raw(i + 1)
                # 致谢人名可能跨行（密集阻击 `**愚 ` + `者**。`）
                if thanks1 and not thanks1.endswith("。"):
                    n2 = lines[i + 2].decode("utf-8")
                    m4 = re.match(r"^([^*\n]+)\*\*。$", n2)
                    assert m4, f"{cn} 致谢续行异常: {n2[:40]!r}"
                    take_raw(i + 2)
                    thanks = f"**{thanks1.strip()} {m4.group(1)}**。"
                    extra = 1
                else:
                    thanks = f"**{thanks1.strip()}" if thanks1 else ""
                    if not thanks.endswith("**。"):
                        thanks += "**。"
                    extra = 0
                out.append(emit_orig(f"{prefix}{cn}（{en1.strip()} {en2.rstrip('）')}）〔{typ}〕**"))
                thanks_crlf = lines[i + 1].endswith(b"\r")  # 合并的续行行尾（密集阻击 L45 为 CRLF）
                out.append(f"｜本条翻译致谢 {thanks}" + ("\r" if thanks_crlf else ""))
                report.append(f"L{i+1}-L{i+2+extra} {cn}：标题闭合 + 致谢剥离独立行")
                fixed += 1
                i += 2 + extra
                continue
            if m3:
                en2, typ, thanks = m3.group(1), m3.group(2), m3.group(3)
                take_raw(i); take_raw(i + 1)
                suffix = f"〔{typ}〕" if typ else ""
                out.append(emit_orig(f"{prefix}{cn}（{en1.strip()} {en2.rstrip('）')}）{suffix}**"))
                out.append(f"｜本条翻译致谢 **{thanks}")
                report.append(f"L{i+1}-L{i+2} {cn}：标题闭合 + 致谢剥离独立行"
                              + ("（无类型括号）" if not typ else ""))
                fixed += 1
                i += 2
                continue
            # EN 完整在标题行 + 致谢头（协调轰击）：`…（Coordinated Blast）〔团队〕**｜本条翻译致谢 `，
            # 续行 `**kataaaka**。`
            m7 = re.match(r"^[一-鿿]{2,}（([^*\n]*?)）〔([^〕]+)〕\*\*｜本条翻译致谢 $", t_r[len(prefix):])
            if m7:
                n2 = lines[i + 1].decode("utf-8")
                m8 = re.match(r"^\*\*([^*\n]+)\*\*。$", n2)
                assert m8, f"{cn} 致谢续行异常: {n2[:40]!r}"
                take_raw(i); take_raw(i + 1)
                out.append(emit_orig(f"{prefix}{cn}（{m7.group(1)}）〔{m7.group(2)}〕**"))
                out.append(f"｜本条翻译致谢 **{m8.group(1)}**。")
                report.append(f"L{i+1}-L{i+2} {cn}：标题闭合 + 致谢换行人名剥离（EN 同行）")
                fixed += 1
                i += 2
                continue
            # 致谢人名整行换行（协调轰击）：标题行尾 `｜本条翻译致谢 `，
            # 续行 `**kataaaka**。`
            m5 = re.match(r"^([^*\n]*?)〔([^〕]+)〕\*\*｜本条翻译致谢 $", n1)
            if m5:
                en2, typ = m5.group(1), m5.group(2)
                n2 = lines[i + 2].decode("utf-8")
                m6 = re.match(r"^\*\*([^*\n]+)\*\*。$", n2)
                assert m6, f"{cn} 致谢续行异常: {n2[:40]!r}"
                take_raw(i); take_raw(i + 1); take_raw(i + 2)
                out.append(emit_orig(f"{prefix}{cn}（{en1.strip()} {en2.rstrip('）')}）〔{typ}〕**"))
                out.append(f"｜本条翻译致谢 **{m6.group(1)}**。")
                report.append(f"L{i+1}-L{i+3} {cn}：标题闭合 + 致谢换行人名剥离")
                fixed += 1
                i += 3
                continue

        # ---- 2) 死亡翻滚：无闭合星标题 + 3 星描述剥 2 星 ----
        if t_r == "**死亡翻滚（Death ":
            n1 = lines[i + 1].decode("utf-8").rstrip("\r")
            m2 = re.match(r"^Roll）〔战斗〕$", n1)
            assert m2, f"死亡翻滚续行异常: {n1[:40]!r}"
            n2 = lines[i + 2].decode("utf-8")
            assert n2.startswith("***") and n2.endswith("*"), f"死亡翻滚描述行异常: {n2[:40]!r}"
            take_raw(i); take_raw(i + 1); take_raw(i + 2)
            out.append(emit_orig("**死亡翻滚（Death Roll）〔战斗〕**"))
            out.append(n2[2:])  # `***描述*` → `*描述*`
            report.append(f"L{i+1}-L{i+3} 死亡翻滚：补闭合星 + 3 星描述剥 2 星")
            fixed += 1
            i += 3
            continue

        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 7, f"预期修复 7 处，实际 {fixed}"
    assert len(new_lines) == n - 2, \
        f"预期 {n-2} 行（合并 2 行：密集阻击/死亡翻滚 3→2），实际 {len(new_lines)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    for cn in CN_NAMES:
        assert any(f"**{cn}（" in l.decode("utf-8") for l in new_lines), \
            f"{cn} 未落位"
    # 致谢粘连残留检查（仅本次修复的 6 条；狠辣借机/共享记忆的致谢同行
    # 是产出成功的合法形态，不在此列）
    residual = [l.decode("utf-8", errors="replace") for l in new_lines
                if re.match(r"^\*\*(密集阻击|上下合围|协调轰击|效死输忠|群体威吓|纯种)（", l.decode("utf-8", errors="replace"))
                and "｜本条翻译致谢" in l.decode("utf-8", errors="replace")]
    assert not residual, f"致谢粘连残留 {len(residual)} 处"
    # 死亡翻滚 3 星描述残留检查
    for l in new_lines:
        l = l.decode("utf-8", errors="replace")
        if l.startswith("***") and "就像短吻鳄" in l:
            raise AssertionError("死亡翻滚 3 星描述未剥")

    if out_bytes == raw:
        print("无变更")
        return 1

    with open(PATH, "wb") as f:
        f.write(out_bytes)
    print(f"== {PATH}：修复 {fixed} 处")
    for r in report:
        print("   ", r)
    print(f"CRLF: {raw.count(b'\r\n')} -> {out_bytes.count(b'\r\n')} "
          f"| 总行数: {n} -> {len(new_lines)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
