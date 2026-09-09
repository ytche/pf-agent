# -*- coding: utf-8 -*-
"""基础页 HTML 残留修复（任务 #142，KN138 家族 P1）

背景：page_150/152 基础页 4 处 HTML `<B><S>` 转换残留导致条目漏切，
est 已预测（per_file_B1.jsonl traps）：
1. page_150 剑豪之眼（L303）：`**~~X~~****~~（EN）~~****~~【WMH】~~****~~：~~**~~` 删除线壳嵌套
   ——est「含删除线 2 条：护枪匠（已切出）、剑豪之眼（漏切）」
2. page_150 吐槽行（L461）：译者吐槽「艹，人家blade of mercy…」独立行混入正文
   ——同 KN091 专长译者吐槽先例，源数据字节级删除
3. page_152 隐修匠（L180）：`~~　　~~**~~隐~~****~~修~~****~~匠（~~…` 中文名星壳碎片
   ——est「含删除线 1 条：隐修匠」
4. page_152 孔冉达的变形师（L432-433）：标题壳尾 4 星 + 正文行首 `**` 泄漏
   ——est trap「正文行首星壳泄漏 L432-433」

修复原则：只动目标行字节，保留行尾（混合 CRLF/LF 不动），其余行零接触。
幂等：目标行不存在时跳过（不重复替换）。
"""
from pathlib import Path

BASE = Path("pf_rules_md_organized/背景特性")

# (文件, 0-based 行号, 目标行字节精确匹配前缀, 新行字节)
# 新行 = 剥离删除线壳与星壳碎片后的标准条目形态（正文剥 ~ 保留标点）
FIXES = []

FIXES.append((
    "page_150.md", 302,
    "**~~剑豪之眼~~****~~（Aldori Caution）~~****~~【WMH】~~****~~：~~**~~",
    "**剑豪之眼（Aldori Caution）【WMH】**：",
))
FIXES.append((
    "page_152.md", 179,
    "~~　　~~**~~隐~~****~~修~~****~~匠（~~****~~Hedge Magician~~****~~）~~****~~【APG】~~**~~：",
    "**隐修匠（Hedge Magician）【APG】**：",
))
FIXES.append((
    "page_152.md", 431,
    "**孔冉达的变形师（****Transmuter of Korada）【CoP】****",
    "**孔冉达的变形师（Transmuter of Korada）【CoP】**",
))
# 孔冉达正文行首 `**` 泄漏（est trap「正文行首星壳泄漏 L432-433」）
FIXES.append((
    "page_152.md", 432,
    "**你师从至高天神使孔冉达的信徒学习变形术的奥秘",
    "你师从至高天神使孔冉达的信徒学习变形术的奥秘",
))
# 吐槽行：整体删除（含行尾换行）
FIXES.append((
    "page_150.md", 460,
    "艹，人家blade of mercy",  # 前缀匹配
    None,  # None = 删除整行（含行尾 \r?\n）
))


def strip_tilde(text: str) -> str:
    """剥离正文残留的 ~~ 删除线壳（正文内部 ~~~~5%~~~~ 等）。"""
    return text.replace("~~", "")


def main() -> None:
    # 先收集按文件分组
    by_file = {}
    for fname, ln, prefix, new in FIXES:
        by_file.setdefault(fname, []).append((ln, prefix, new))

    for fname, fixes in by_file.items():
        path = BASE / fname
        data = path.read_bytes()
        lines = data.split(b"\n")
        for ln, prefix, new in fixes:
            raw = lines[ln].decode("utf-8")
            if not raw.startswith(prefix):
                print(f"[SKIP] {fname} L{ln+1} 前缀不匹配：{raw[:40]!r}")
                continue
            if new is None:
                # 删除整行：吞掉本行与其行尾换行
                lines[ln] = b"\x00DEL\x00"
            else:
                # 保留行尾（\r 或空），前缀替换 + 正文剥删除线壳
                eol = "\r" if raw.endswith("\r") else ""
                new_text = strip_tilde(new) + strip_tilde(raw[len(prefix):])
                lines[ln] = (new_text + eol).encode("utf-8")
                print(f"[OK] {fname} L{ln+1} -> {new_text[:50]}…")
        out = b"\n".join(x for x in lines if x != b"\x00DEL\x00")
        path.write_bytes(out)
        print(f"[DONE] {fname} 写回（{len(data)} -> {len(out)} 字节）")


if __name__ == "__main__":
    main()
