"""
fix_feat_aquatic.py — 水下冒险AA_专长.md 带类型标题断裂源数据修复（P0 级，est=16 got=7）

背景（2026-08-02 审计发现，P0 级）：水下冒险AA 是 K3 聚合文件（AA-source 注释），
判别器 est=16（FC-4b:10 + FC-8e:7）。当前仅 7 个 chunk（6 无类型专长 + 1 节标题
「水下专长」），10 个带类型括号条目（`中文（类型）EN 正文`）100% 丢失——M6
裸中英正则（FC-8e）EN 捕获后跟全角 `（` 失配，M13 系列要求 `**` 前缀不匹配。

形态族（标题 = `中文（类型）EN`，EN 跨行拆词或同行粘连正文）：

  S1 跨行（8 条）`中文（类型）EN \nEN续 正文`：
     水下战斗专攻（战斗）Aquadynamic \n focus 你在…
     水下射击（战斗）Aquadynamic \n shot 你使用…
     两个世界的孩子（故事）Child of two \n worlds 你是…
     海豚环杀（战斗）Dolphin \n circle 你像…
     浑浊法术（超魔）Murky \n spell 你可以在…
     猛鲨流（战斗，流派）Shark \n style 你像…
     蒸汽法术（超魔）Steam \n spell 你成功…
  S2 同行（3 条）`中文（类型）EN正文`：
     海豚流（战斗，流派）Dolphin style你像…
     鲨跃（战斗）Shark leap像一只…
     鲨裂（战斗）Shark tear你撕裂…

无类型条目（深呼吸/海豚突进/压力适应等 6 条）已被 M6 识别，保持原样；
L9 节标题 `水下专长Aquatic feats地上…`（FC-8e 计 1）保持原样。

修复（改源数据不改脚本，对齐 KN037~KN041 先例）：
  - S1/S2 → FC-1q 独立标题行 `**中文（EN）（类型）**`，正文行原样保留
  - 行尾字节级保留（CRLF/LF 沿用原行行尾）；断言 n==73 + L12 水下战斗专攻防漂移

修复后：16 = est=16 精确匹配（10 带类型恢复 + 6 无类型 + 节标题 FC-8e 计 1）。

用法：python3 fix_feat_aquatic.py
"""

import re
import sys

PATH = "pf_rules_md_organized/专长/水下冒险AA_专长.md"

# S1 前缀行：`中文（类型）EN `（EN 跨行拆词，行尾空格）
RE_SPLIT_PREFIX = re.compile(
    r"^([一-鿿]{2,15})（([一-鿿A-Za-z ，、]{1,12})）([A-Za-z][A-Za-z'’\.\- ]*?) $"
)
# S1 续行：`EN续 正文`（EN 词首 + 正文同行）
RE_SPLIT_CONT = re.compile(r"^([A-Za-z][A-Za-z'’\.\- ]*?)(.*)$")
# S2 同行：`中文（类型）EN正文`
RE_SAME = re.compile(
    r"^([一-鿿]{2,15})（([一-鿿A-Za-z ，、]{1,12})）([A-Za-z][A-Za-z'’\.\- ]*?)([一-鿿].*)$"
)


def split_lines(raw: bytes) -> list[tuple[str, bool]]:
    """读文件 → [(内容, 是否 CR 行尾)]，保留原始行尾字节信息"""
    return [(l[:-1].decode("utf-8", "ignore"), True) if l.endswith(b"\r")
            else (l.decode("utf-8", "ignore"), False)
            for l in raw.split(b"\n")]


def join_lines(lines: list[tuple[str, bool]]) -> bytes:
    out = []
    for text, cr in lines:
        out.append(text.encode("utf-8") + (b"\r" if cr else b""))
    return b"\n".join(out)


def make_title(cn: str, en: str, type_: str) -> str:
    return f"**{cn}（{en.strip()}）（{type_}）**"


def main() -> int:
    raw = open(PATH, "rb").read()
    lines = split_lines(raw)
    n = len(lines)
    assert n == 74, f"预期 74 行，实际 {n} 行——行号假设失效，中止"
    assert lines[11][0].startswith("水下战斗专攻（战斗）"), \
        f"L12 非水下战斗专攻：{lines[11][0][:30]!r}"

    out: list[tuple[str, bool]] = []
    fixed = 0
    report: list[str] = []
    i = 0
    while i < n:
        text, cr = lines[i]
        st = text.strip()
        if not st or st == "****":
            out.append((text, cr))
            i += 1
            continue

        # ---- S1：跨行（前缀行 + EN续行）----
        m1 = RE_SPLIT_PREFIX.match(text)
        if m1 and i + 1 < n:
            nxt, nxt_cr = lines[i + 1]
            mc = RE_SPLIT_CONT.match(nxt)
            if mc:
                out.append((make_title(m1.group(1), m1.group(3) + " " + mc.group(1),
                                       m1.group(2)), cr))
                if mc.group(2).strip():
                    out.append((mc.group(2).strip(), nxt_cr))
                fixed += 1
                report.append(f"L{i+1}-L{i+2}: {m1.group(1)} 跨行归一")
                i += 2
                continue

        # ---- S2：同行（中文（类型）EN正文）----
        m2 = RE_SAME.match(text)
        if m2:
            out.append((make_title(m2.group(1), m2.group(3), m2.group(2)), cr))
            out.append((m2.group(4), cr))
            fixed += 1
            report.append(f"L{i+1}: {m2.group(1)} 同行归一")
            i += 1
            continue

        out.append((text, cr))
        i += 1

    out_bytes = join_lines(out)
    if out_bytes == raw:
        print("无变更")
        return 1

    with open(PATH, "wb") as f:
        f.write(out_bytes)
    print(f"== {PATH}：修复 {fixed} 处")
    for r in report:
        print("   ", r)
    print(f"CRLF: {raw.count(b'\r\n')} -> {out_bytes.count(b'\r\n')} "
          f"| 裸LF: {raw.count(b'\n')-raw.count(b'\r\n')} "
          f"-> {out_bytes.count(b'\n')-out_bytes.count(b'\r\n')} "
          f"| 总行数: {n} -> {len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
