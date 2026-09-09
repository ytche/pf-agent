"""
fix_feat_villain_codex.py — 反派法典VC_专长.md 5 处杂糅标题归一（P0 级，est=25 got=20 丢 5）

背景（2026-08-02 KN026 复算审计，P0 级）：反派法典VC_专长.md（《恶棍志》专长页，
已整理文件）25 个专长条目，5 条丢失（协调捕获/火枪手的胆气/火枪手的滑步/自然之怒/
优雅双武）。三种根因形态（对照产出成功的同族形态定位）：

1. **EN 含撇号 `'`（3 处：胆气/滑步/自然之怒）**：
   `火枪手的胆气Musketeer's \nDaring（战斗，派头）*****你越大胆…*`——B 分支
   `_RE_BARE_CN_EN_CNPAREN` EN 字符类 `[A-Za-z- ]` 与 C 分支 `[A-Za-z \n]`
   均不含撇号 → `Musketeer's`/`Nature's` 匹配中断 → wrap 全分支失配 → 条目丢弃。
   对照：掩护射击（`Covering Fire` 无撇号）同形态产出成功。
2. **3 行结构 + `***描述***`（协调捕获）**：`**协调捕获Coordinated \nCapture（战斗，团队）\n***你与…***先决条件**：…`——
   D 分支组2 `[^*\n]{1,}?` 不能跨行（类型括号独立行），4 星锚定在换行处失败。
3. **`**` 开头无闭合星 + 出处断行（优雅双武）**：`**优雅双武Two-Weapon Grace（战斗专长）（PFS不可用）\n**出处：恶棍志Villain \nCodex pg. 224\n先决条件：DEX \n15；…`——
   D 分支 `[^*\n]{1,}?` 组2 后无 4 星 → 失配。

修复（改源数据不改脚本，对齐 KN052-KN057 归一先例）：
  1. 胆气/滑步/自然之怒：`**中文（EN 折叠）〔类型〕**`（无类型不带括号）+
     5 星描述剥 4 星成 `*描述*`（对齐狡黠产出形态）+ 裸字段标签归一拆行
  2. 协调捕获：3 行合并归一 + `***描述***` 剥 2 星成 `*描述*` + 字段归一拆行
  3. 优雅双武：标题闭合 `**优雅双武（Two-Weapon Grace）（战斗专长）**【PFS不可用】`，
     出处 2 行剥离（已有 `> 来源` 注释行补位），先决条件 2 行折叠归一

归一后 5 条全部为标准闭合标题（FC-1r/1q 可识别）→ got 20→25 = est 25。

验证：5 处转换、207 → 208 行（拆行 +4 / 合并 -3）、LF-only 不变（无 CRLF）、
继承行字节守恒、5 个中文名落位、修复目标 5 星描述/裸字段残留 0、
重跑 pipeline + verify + pytest。

用法：python3 fix_feat_villain_codex.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/反派法典VC_专长.md"

CN_NAMES = ["优雅双武", "协调捕获", "火枪手的胆气", "火枪手的滑步", "自然之怒"]

# 胆气/滑步/自然之怒首行：`中文[空格]EN1 `（EN 可含撇号，行尾尾随空格）
_RE_BARE_5S = re.compile(r"^([一-鿿]{2,})\s*([A-Za-z][A-Za-z ']*?)\s*$")
# 续行带类型：`EN2（类型）*****描述*`
_RE_5S_CONT = re.compile(r"^([A-Za-z][A-Za-z ']*?)（([^）]+)）\*{4,}(.+)$")
# 续行无类型：`EN2*****描述*`
_RE_5S_CONT_NO_TYP = re.compile(r"^([A-Za-z][A-Za-z ']*?)\*{4,}(.+)$")
# 协调捕获第 3 行：`***描述***字段段`
_RE_3STAR = re.compile(r"^\*\*\*(.+?)\*\*\*(.+)$")

# 裸字段标签两种星形（对齐 fix_feat_blood_of_the_sea.py）
_RE_FLD_STAR = re.compile(r"\*\*(效果|专长效果|特殊|一般情况)\*\*：")
_RE_FLD_BARE = re.compile(r"(?<![\*一-鿿])(先决条件)\*\*：")
_RE_TRAIL_STAR = re.compile(r"\*\*$")


def _norm_fields(line: str) -> list[str]:
    """裸字段标签行归一：标签包裹 + 按标签拆行 + 行尾剥星。"""
    line = _RE_FLD_STAR.sub(r"**\1：**", line)
    line = _RE_FLD_BARE.sub(r"**\1：**", line)
    parts = re.split(r"(?=\*\*(?:效果|专长效果|特殊|一般情况)：)", line)
    return [p[:-2] if p.endswith("**") else p for p in parts]


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

        # ---- 1) 优雅双武：`**` 开头无闭合星 + 出处断行 + 先决条件跨行 ----
        if t == "**优雅双武Two-Weapon Grace（战斗专长）（PFS不可用）":
            n1 = lines[i + 1].decode("utf-8")
            n2 = lines[i + 2].decode("utf-8")
            n3 = lines[i + 3].decode("utf-8")
            n4 = lines[i + 4].decode("utf-8")
            assert n1 == "**出处：恶棍志Villain ", f"优雅双武出此行异常: {n1[:40]!r}"
            assert n2 == "Codex pg. 224", f"优雅双武出处页异常: {n2[:40]!r}"
            assert n3 == "先决条件：DEX ", f"优雅双武先决行异常: {n3[:40]!r}"
            assert n4.startswith("15；优雅挑刺"), f"优雅双武先决续行异常: {n4[:40]!r}"
            take_raw(i); take_raw(i + 1); take_raw(i + 2); take_raw(i + 3); take_raw(i + 4)
            out.append("**优雅双武（Two-Weapon Grace）（战斗专长）**【PFS不可用】")
            out.append("**先决条件：**DEX 15；优雅挑刺/优雅挥砍/优雅繁星三者之一；"
                       "双武器格斗；武器娴熟")
            report.append(f"L{i+1}-L{i+5} 优雅双武：标题闭合 + 出处剥离 + 先决条件归一")
            fixed += 1
            i += 5
            continue

        # ---- 2) 协调捕获：3 行 + `***描述***` ----
        if t == "**协调捕获Coordinated ":
            n1 = lines[i + 1].decode("utf-8")
            n2 = lines[i + 2].decode("utf-8")
            assert n1 == "Capture（战斗，团队）", f"协调捕获续行异常: {n1[:40]!r}"
            m = _RE_3STAR.match(n2)
            assert m, f"协调捕获描述行异常: {n2[:60]!r}"
            take_raw(i); take_raw(i + 1); take_raw(i + 2)
            out.append("**协调捕获（Coordinated Capture）〔战斗，团队〕**")
            out.append(f"*{m.group(1)}*")
            out.extend(_norm_fields(m.group(2)))
            report.append(f"L{i+1}-L{i+3} 协调捕获：3 行合并 + 描述剥 2 星 + 字段归一")
            fixed += 1
            i += 3
            continue

        # ---- 3) 胆气/滑步/自然之怒：EN 撇号 + 5 星描述 ----
        # 精确锚定 3 条目标首行（掩护射击等 12 条无撇号同形态为合法产出，不误伤）
        _BARE_TARGETS = {"火枪手的胆气Musketeer's ": ("火枪手的胆气", "Musketeer's"),
                         "火枪手的滑步 Musketeer's ": ("火枪手的滑步", "Musketeer's"),
                         "自然之怒 Nature's ": ("自然之怒", "Nature's")}
        if t in _BARE_TARGETS:
            cn, en1 = _BARE_TARGETS[t]
            n1 = lines[i + 1].decode("utf-8")
            m2 = _RE_5S_CONT.match(n1)
            has_typ = bool(m2)
            if not m2:
                m2 = _RE_5S_CONT_NO_TYP.match(n1)
            if m2:
                en2 = m2.group(1)
                typ = m2.group(2) if has_typ else None
                desc = m2.group(3).rstrip("*") if has_typ else m2.group(2).rstrip("*")
                n2 = lines[i + 2].decode("utf-8")
                assert n2.startswith("先决条件"), f"{cn} 字段行异常: {n2[:40]!r}"
                take_raw(i); take_raw(i + 1); take_raw(i + 2)
                typ_suffix = f"〔{typ}〕" if typ else ""
                out.append(f"**{cn}（{en1} {en2}）{typ_suffix}**")
                out.append(f"*{desc}*")
                out.extend(_norm_fields(n2))
                report.append(f"L{i+1}-L{i+3} {cn}：标题闭合 + 5 星描述剥星 + 字段归一"
                              + ("（无类型）" if not typ else ""))
                fixed += 1
                i += 3
                continue

        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 5, f"预期修复 5 处，实际 {fixed}"
    assert len(out) == n + 1, \
        f"预期 {n+1} 行（拆行 +4 / 合并 -3），实际 {len(out)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n"), \
        "CRLF 计数变化，行尾被污染"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    for cn in CN_NAMES:
        assert any(f"**{cn}（" in l.decode("utf-8") for l in new_lines), \
            f"{cn} 未落位"
    # 修复目标残留检查（5 条；掩护射击等 12 条 5 星形态为合法产出，不在列）
    full = out_bytes.decode("utf-8", errors="replace")
    hits = re.findall(r"^\*\*?(优雅双武|协调捕获|火枪手的胆气|火枪手的滑步|自然之怒)"
                      r"[^*\n]*\*{4,}", full, re.M)
    assert not hits, f"修复目标 5 星描述残留 {len(hits)} 处: {hits}"
    for name in ("优雅双武", "协调捕获", "火枪手的胆气", "火枪手的滑步", "自然之怒"):
        for l in new_lines:
            l = l.decode("utf-8", errors="replace")
            if l.startswith(name) and "先决条件**：" in l:
                raise AssertionError(f"{name} 裸字段残留")

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
