"""page_194 冒号独立加粗段残留修复（KN089 附项）。

HTML 三连加粗段（`<B>擒拿手流</B><B> Grabbing Style</B><B>：</B>`）转换产物：
`**擒拿手流（Grabbing Style）****：**这种…`——冒号段被 4 星包裹且 1 字符
（`****：**`）不被 _RE_QUAD_STAR（需 ≥2 非星字符）消费，残留在标题闭合星后，
M13a 前瞻 `(?![\n：:])` 又因冒号不拆行 → `**：**` 空标签漏进 text 开头
（3 处：擒拿手流 / 百裂拳流 / 刚烈掌流）。

修法：删 `****：**`（`）****：**` → `）**`），标题变 `**中文（EN）**正文`
走 M13a 拆行，正文并入标准路径。全库仅此 3 处，一次性源数据修复。

行尾约定：page_194 为混合行尾（185 CRLF + 338 LF），逐行处理保留原行尾。
"""
from pathlib import Path

TARGET = Path("pf_rules_md_organized/专长/page_194.md")
OLD = "）****：**"
NEW = "）**"


def main() -> None:
    raw = TARGET.read_bytes()
    text = raw.decode("utf-8")
    cnt = text.count(OLD)
    if cnt != 3:
        raise SystemExit(f"期望 3 处 `{OLD}`，实际 {cnt} 处——中止（防误改）")
    # 逐行替换，保留原行尾（splitlines(keepends=True) 区分 \r\n / \n）
    lines = text.splitlines(keepends=True)
    new_lines = []
    hit = 0
    for ln in lines:
        if OLD in ln:
            new_lines.append(ln.replace(OLD, NEW))
            hit += 1
        else:
            new_lines.append(ln)
    assert hit == 3, f"逐行命中 {hit} != 3"
    TARGET.write_bytes("".join(new_lines).encode("utf-8"))
    print(f"已修复 {hit} 处：{TARGET.name}")


if __name__ == "__main__":
    main()
