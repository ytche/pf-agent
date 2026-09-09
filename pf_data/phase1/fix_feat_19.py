"""
fix_feat_19.py — 专长19.md 4 处形态归一（P0 级，est=10 got=6 丢 4）

背景（2026-08-02 KN026 复算审计，P0 级）：专长19.md（《街巷英雄》专长页，
根级文件）10 个专长条目，4 条丢失（狡诈施法者/污秽武器/以泥糊眼/割喉者）。
两种根因形态（对照产出成功的同族形态定位）：

1. **3 行结构 + `***描述***`（狡诈施法者）**：
   `**狡诈施法者Cunning \nCaster\n***不管…。***先决条件**：…`——
   C 分支 `_RE_BARE_CN_EN_STAR` 组2 `[A-Za-z \n]{1,}` 贪婪跨行匹配到
   `Cunning \nCaster\n` 后遇 `***` 停止，`*{4,}` 需 4 星而 `***` 仅 3 星
   → 失配；D 分支组2 `[^*\n]` 不能跨行 → 全分支失配 → 条目丢弃。
   对照：反派法典VC 协调捕获同形态（3 行 + 3 星描述）。
2. **2 行带类型 + 5 星描述（污秽武器/以泥糊眼/割喉者）**：
   `**污秽武器 Filthy \nWeapons（战斗）*****你的武器…。*`——
   C 分支组2 `[A-Za-z \n]{1,}` 贪婪匹配 `Filthy \nWeapons` 后遇全角 `（`
   停止（`（` 不在字符类内），`*{4,}` 遇 `（战斗）` → 失配。
   对照：无类型同族（边缘跑者等 5 条 `Runner*****`）C 分支跨行后直接命中
   `*{4,}` 产出成功。与反派法典VC 胆气（`Daring（战斗，派头）*****`）同族。

修复（改源数据不改脚本，对齐 KN057/KN058 归一先例）：
  1. 狡诈施法者：3 行合并归一 + `***描述***` 剥 2 星成 `*描述*` + 字段归一拆行
  2. 污秽武器/以泥糊眼/割喉者：标题闭合 `**中文（EN 折叠）〔战斗〕**` +
     5 星描述剥 4 星成 `*描述*` + 字段归一拆行
  3. 割喉者特判：字段标签 `专长先决**：`（全文件唯一）→ `先决条件**：` 再归一

归一后 4 条全部为标准闭合标题（FC-1r/1q 可识别）→ got 6→10 = est 10。

验证：4 处转换、64 → 69 行（+5：狡诈/污秽/割喉 3→4 各 +1，以泥糊眼 3→5 拆 3 字段 +2）、
CRLF 28 → 29（污秽武器字段行 L28 为 CRLF 拆 2 行 +1，其余行尾类型逐行保留）、
继承行字节守恒、4 个中文名落位、修复目标残留 0（锚定条目名，产出成功的
无类型 5 条同形态合法不检查）、重跑 pipeline + verify + pytest。

用法：python3 fix_feat_19.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长19.md"

CN_NAMES = ["狡诈施法者", "污秽武器", "以泥糊眼", "割喉者"]

# 2 行带类型续行：`EN2（类型）*****描述*`（EN 可含撇号，全角括号字面量）
_RE_5S_CONT = re.compile(r"^([A-Za-z][A-Za-z ']*?)（([^）]+)）\*{4,}(.+)$")
# 3 行结构描述行：`***描述***字段段`（对齐协调捕获）
_RE_3STAR = re.compile(r"^\*\*\*(.+?)\*\*\*(.+)$")

# 裸字段标签两种星形（对齐 fix_feat_blood_of_the_sea.py）
_RE_FLD_STAR = re.compile(r"\*\*(效果|专长效果|特殊|一般情况)\*\*：")
_RE_FLD_BARE = re.compile(r"(?<![\*一-鿿])(先决条件)\*\*：")

# 4 条目标首行精确锚定（防误伤产出成功的无类型同族 5 条）：
# 狡诈施法者 3 行结构单独处理；3 条带类型 2 行结构在此表
_BARE_TARGETS = {"**污秽武器 Filthy ": ("污秽武器", "Filthy"),
                 "**以泥糊眼 Mud in Your ": ("以泥糊眼", "Mud in Your"),
                 "**割喉者Throat ": ("割喉者", "Throat")}


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

    def emit_orig(line: str, orig: bytes) -> str:
        """修复行保留原行行尾（CRLF 行保留 \r，LF 行不加）。"""
        return line + ("\r" if orig.endswith(b"\r") else "")

    i = 0
    while i < n:
        t = lines[i].decode("utf-8")
        t_r = t.rstrip("\r")

        # ---- 1) 狡诈施法者：3 行结构（对齐协调捕获）----
        if t_r == "**狡诈施法者Cunning ":
            n1 = lines[i + 1].decode("utf-8")
            n2 = lines[i + 2].decode("utf-8")
            assert n1 == "Caster", f"狡诈施法者续行异常: {n1[:40]!r}"
            m = _RE_3STAR.match(n2)
            assert m, f"狡诈施法者描述行异常: {n2[:60]!r}"
            take_raw(i); take_raw(i + 1); take_raw(i + 2)
            out.append(emit_orig("**狡诈施法者（Cunning Caster）**", lines[i]))
            out.append(emit_orig(f"*{m.group(1)}*", lines[i + 1]))
            for p in _norm_fields(m.group(2)):
                out.append(emit_orig(p, lines[i + 2]))
            report.append(f"L{i+1}-L{i+3} 狡诈施法者：3 行合并 + 描述剥 2 星 + 字段归一")
            fixed += 1
            i += 3
            continue

        # ---- 2) 污秽武器/以泥糊眼/割喉者：2 行带类型 + 5 星描述 ----
        if t_r in _BARE_TARGETS:
            cn, en1 = _BARE_TARGETS[t_r]
            n1 = lines[i + 1].decode("utf-8")
            m2 = _RE_5S_CONT.match(n1)
            assert m2, f"{cn} 续行异常: {n1[:60]!r}"
            n2 = lines[i + 2].decode("utf-8")
            assert n2.lstrip().startswith(("先决条件", "专长先决")), \
                f"{cn} 字段行异常: {n2[:40]!r}"
            take_raw(i); take_raw(i + 1); take_raw(i + 2)
            en2, typ = m2.group(1), m2.group(2)
            desc = m2.group(3).rstrip("*")
            out.append(emit_orig(f"**{cn}（{en1} {en2}）〔{typ}〕**", lines[i]))
            out.append(emit_orig(f"*{desc}*", lines[i + 1]))
            field_line = n2.replace("专长先决**：", "先决条件**：")
            for p in _norm_fields(field_line):
                out.append(emit_orig(p, lines[i + 2]))
            report.append(f"L{i+1}-L{i+3} {cn}：标题闭合 + 5 星描述剥星 + 字段归一"
                          + ("（专长先决标签归一）" if "专长先决" in n2 else ""))
            fixed += 1
            i += 3
            continue

        out.append(t)
        i += 1

    out_bytes = "\n".join(out).encode("utf-8")
    new_lines = out_bytes.split(b"\n")

    # ---- 字节级验证 ----
    assert fixed == 4, f"预期修复 4 处，实际 {fixed}"
    assert len(out) == n + 5, \
        f"预期 {n+5} 行（狡诈/污秽/割喉 3→4 各 +1，以泥糊眼 3→5 +2），实际 {len(out)}"
    assert out_bytes.count(b"\r\n") == raw.count(b"\r\n") + 1, \
        "CRLF 计数与预期 29 不符（污秽武器 L28 字段行拆 2 行 +1，其余逐行保留）"
    fixed_orig_set = set(fixed_orig)
    for l in set(lines) - fixed_orig_set:
        assert new_lines.count(l) == lines.count(l), \
            f"继承行字节不守恒：{l[:40]!r}"
    for cn in CN_NAMES:
        assert any(f"**{cn}（" in l.decode("utf-8") for l in new_lines), \
            f"{cn} 未落位"
    # 修复目标残留检查（4 条；边缘跑者等 5 条无类型 5 星形态为合法产出，不在列）
    full = out_bytes.decode("utf-8", errors="replace")
    hits = re.findall(r"^\*\*?(狡诈施法者|污秽武器|以泥糊眼|割喉者)"
                      r"[^*\n]*\*{4,}", full, re.M)
    assert not hits, f"修复目标 5 星描述残留 {len(hits)} 处: {hits}"
    assert "专长先决" not in full, "专长先决标签残留"
    for name in ("狡诈施法者", "污秽武器", "以泥糊眼", "割喉者"):
        for l in new_lines:
            l = l.decode("utf-8", errors="replace")
            if l.startswith(name) and ("先决条件**：" in l or "专长先决" in l):
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
