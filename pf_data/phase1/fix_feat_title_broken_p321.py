"""
fix_feat_title_broken_p321.py — page_321/page_500 标题断裂源数据修复

背景（2026-08-02 审计发现，P0 级）：
  page_321（内希斯神系专长页）85 个候选标题中仅 6 个被 pipeline 识别——
  同 page_276 怪物坐骑根因的「标题星号漂移断裂」系统性变体：
    F1  中文行 `中文**** \r` + 下行裸英文名      （13 处）
    F2  同行   `中文**** English`               （51 处纯形）
    F2b 同行   `中文**** English****（类型）****` （10 处含类型）
    F3  中文行 `中文****` + 下行 `EN****（类型）****`（6 处）
    R3  同行   `中文**** EN*****  ******正文*********`（431 行知识大师特例）
    R5  跨行   `中文****EN片段` + 下行 `EN片段`      （page_500 141 兽魂图腾）
  page_500 同型 12 处（F1 5 + F3 6 + R5 1）。
  判别器 est=86（FC-7b 64 + FC-7 21），当前产出 6 — 93% 条目丢失。

修复原则（对齐 page_276 先例 4e2bc24 / P0a 先例 7607913）：
  - 改源数据不改脚本：断裂标题归一为 pipeline 已支持的标准形态
    `**中文（English）**`（FC-1n）与 `**中文（English）（类型）**`（FC-1q）
  - 漂移正文行（`*****  ******正文*********`）保留不动（elided 机制吸收，
    page_276 先例验证过）
  - 行尾字节级保留（organized 源数据 CRLF 约定：逐行保留原行尾）

用法：python3 fix_feat_title_broken_p321.py
"""

import re
import sys

FILES = [
    "pf_rules_md_organized/专长/page_321.md",
    "pf_rules_md_organized/专长/page_500.md",
    "pf_rules_md_organized/page_321.md",   # 根目录旧副本（FeatProcessor stem 去重
    "pf_rules_md_organized/page_500.md",   # 不消费，但保持两份一致防混淆）
]

# R6 字段标签 4星漂移（**先决条件****：**）：伪条目（title='先决条'）根因。
# 仅专长消费的 5 个文件（page_500/530/529/505/509 有伪条目；page_527/1368
# 形态已工作正常不动，避免引入新回归）。职业/法术/种族页属冻结模块不碰。
R6_FILES = [
    "pf_rules_md_organized/专长/page_500.md",
    "pf_rules_md_organized/专长/page_530.md",
    "pf_rules_md_organized/专长/page_529.md",
    "pf_rules_md_organized/专长/page_505.md",
    "pf_rules_md_organized/专长/page_509.md",
    "pf_rules_md_organized/page_500.md",
    "pf_rules_md_organized/page_530.md",
    "pf_rules_md_organized/page_529.md",
    "pf_rules_md_organized/page_505.md",
    "pf_rules_md_organized/page_509.md",
]

# 中文名（不含星号行首）、英文名（含反引号——Butterfly`s Sting）、类型括号
RE_CN = r"[一-鿿]+"
RE_EN = r"[A-Za-z][A-Za-z ,\.\'\-’`]*"
RE_TYPE = r"[一-鿿A-Za-z ，、]+"

# R2  同行纯形：中文**** English
RE_R2 = re.compile(rf"^({RE_CN})\*\*\*\* ({RE_EN})$")
# R2b 同行含类型：中文**** English****（类型）****
RE_R2B = re.compile(rf"^({RE_CN})\*\*\*\* ({RE_EN}) ?\*\*\*\*（({RE_TYPE})）\*\*\*\*$")
# R3  同行+漂移正文：中文**** English*****  ******正文*********
RE_R3 = re.compile(rf"^({RE_CN})\*\*\*\* ({RE_EN})\*\*\*\*\*  \*\*\*\*\*\*(.*?)\*\*\*\*\*\*\*\*\*$")
# R4  跨行：中文行 `中文****`（行尾）；下行裸英文 或 EN****（类型）****
RE_R4_CN = re.compile(rf"^({RE_CN})\*\*\*\* *$")
RE_R4_EN = re.compile(rf"^({RE_EN})$")
RE_R4_EN_T = re.compile(rf"^({RE_EN}) ?\*\*\*\*（({RE_TYPE})）\*\*\*\*$")
# R5  跨行拆词：兽魂图腾****Totem + 下行 Beast（英文名跨行拆两段）
RE_R5_CN = re.compile(rf"^({RE_CN})\*\*\*\*({RE_EN})$")
RE_R5_EN = re.compile(rf"^({RE_EN})$")

# 漂移正文行（保留不动）——仅用于排除误判
RE_DRIFT = re.compile(r"^\*\*{4,}")

# R6：字段标签 4星漂移 `**先决条件****：**` → `**先决条件：**`
RE_R6 = re.compile(r"\*\*([一-鿿]{2,8})\*\*\*\*([：:])")


def fix_file(path: str) -> tuple[int, list[str]]:
    raw = open(path, "rb").read()
    lines = raw.split(b"\n")
    fixed = 0
    report: list[str] = []
    n = len(lines)
    for i in range(n):
        line = lines[i]
        # 行尾字节：\r 结尾则保留
        has_cr = line.endswith(b"\r")
        body = line[:-1] if has_cr else line
        s = body.decode("utf-8", "ignore")
        st = s.strip()
        new_body: str | None = None
        drop_next = False
        if st:
            m = RE_R2B.match(st)
            if m:
                # F2b → **中文（EN）（类型）**（FC-1q）
                new_body = f"**{m.group(1)}（{m.group(2).strip()}）（{m.group(3)}）**"
            else:
                m = RE_R3.match(st)
                if m:
                    # 431 知识大师特例：标题 + 漂移正文拆两行
                    title = f"**{m.group(1)}（{m.group(2)}）**"
                    drift = f"*****  ******{m.group(3)}*********"
                    new_body = title + "\n" + drift
                else:
                    m = RE_R2.match(st)
                    if m:
                        # F2 → **中文（EN）**（FC-1n）
                        new_body = f"**{m.group(1)}（{m.group(2)}）**"
                    else:
                        # R4/R5 跨行：本行是中文行，看下行
                        m4 = RE_R4_CN.match(st)
                        m5 = RE_R5_CN.match(st)
                        if m4 and i + 1 < n:
                            nxt = lines[i + 1].decode("utf-8", "ignore").strip()
                            m_t = RE_R4_EN_T.match(nxt)
                            m_e = RE_R4_EN.match(nxt)
                            if m_t:
                                new_body = f"**{m4.group(1)}（{m_t.group(1).strip()}）（{m_t.group(2)}）**"
                                drop_next = True
                            elif m_e:
                                new_body = f"**{m4.group(1)}（{m_e.group(1).strip()}）**"
                                drop_next = True
                        elif m5 and i + 1 < n:
                            nxt = lines[i + 1].decode("utf-8", "ignore").strip()
                            m_e = RE_R5_EN.match(nxt)
                            if m_e:
                                # 英文名跨行拆段合并：中文（EN段1 EN段2）
                                new_body = f"**{m5.group(1)}（{m5.group(2)} {m_e.group(1).strip()}）**"
                                drop_next = True
        if new_body is None and path in R6_FILES:
            # R6 字段标签 4星漂移（`**先决条件****：**` → `**先决条件：**`）：
            # 标题正则全未命中才执行（漂移正文行 `*****  ******` 形态天然不匹配）
            s_r6, n_r6 = RE_R6.subn(lambda m: f"**{m.group(1)}{m.group(2)}", s)
            if n_r6:
                new_body = s_r6
        if new_body is not None:
            report.append(f"L{i+1}: {st[:40]} -> {new_body[:50]}")
            if "\n" in new_body:
                # R3 拆两行：标题行保留原行尾，正文漂移行用裸 LF（文件主流行尾）
                t_title, t_drift = new_body.split("\n", 1)
                enc = (t_title.encode("utf-8") + (b"\r" if has_cr else b"")) + b"\n" + t_drift.encode("utf-8")
            else:
                enc = new_body.encode("utf-8")
            lines[i] = (enc + b"\r" if has_cr and "\n" not in new_body else enc)
            fixed += 1
            if drop_next and i + 1 < n:
                nxt_orig = lines[i + 1].decode("utf-8", "ignore").strip()
                nxt_cr = lines[i + 1].endswith(b"\r")
                lines[i + 1] = b"\r" if nxt_cr else b""
                report.append(f"L{i+2}: 置空（原 {nxt_orig[:30]!r}）")
                # 置空行再入循环时 st 为空自动跳过，无需额外控制
    out = b"\n".join(lines)
    if out != raw:
        with open(path, "wb") as f:
            f.write(out)
    return fixed, report


def main():
    total = 0
    seen = set()
    for path in [*FILES, *R6_FILES]:
        if path in seen:
            continue
        seen.add(path)
        try:
            fixed, report = fix_file(path)
        except FileNotFoundError:
            print(f"跳过（不存在）: {path}")
            continue
        total += fixed
        print(f"== {path}：修复 {fixed} 处")
        for r in report:
            print("   ", r)
    print(f"\n合计修复 {total} 处")
    return 0 if total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
