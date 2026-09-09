"""撤回 THH 武僧/召唤师变体的错放。

错误：
- 武僧/page_53.md 仅含 THH 哈罗牌守卫 → 应并入 武僧/page_55.md（变体主页）
- 召唤师/page_411.md 仅含 THH 故事召唤师 → 应并入 召唤师/page_410.md（变体主页）
- 召唤师/THH_故事召唤师与故事形态.md 含 故事召唤师变体（重复）+ 新幻灵范例 故事形态
  - 故事召唤师段跳过（page_411 已迁入 page_410）
  - 故事形态幻灵 → 召唤师/page_1346.md（幻灵范例页）

按 class_subcategory_mapping.md §1.2，女巫变体→page_70、武僧变体→page_55、
召唤师变体→page_410、召唤师幻灵范例→page_1346。
"""
import re
from pathlib import Path

PHASE1 = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
ORG = PHASE1 / "pf_rules_md_organized"

MONK_PAGE_53 = ORG / "职业" / "核心职业" / "武僧" / "page_53.md"
MONK_PAGE_55 = ORG / "职业" / "核心职业" / "武僧" / "page_55.md"

SUMMONER_PAGE_411 = ORG / "职业" / "基础职业" / "召唤师" / "page_411.md"
SUMMONER_PAGE_410 = ORG / "职业" / "基础职业" / "召唤师" / "page_410.md"
SUMMONER_THH_MD = ORG / "职业" / "基础职业" / "召唤师" / "THH_故事召唤师与故事形态.md"
SUMMONER_PAGE_1346 = ORG / "职业" / "基础职业" / "召唤师" / "page_1346.md"


def read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    has_crlf = b"\r\n" in raw
    return raw.decode("utf-8"), ("\r\n" if has_crlf else "\n")


def write_text(path: Path, content: str, nl: str) -> None:
    if nl == "\r\n":
        content = content.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_bytes(content.encode("utf-8"))


def normalize_blank_lines(text: str) -> str:
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def ensure_trailing_newline(text: str, nl: str) -> str:
    if not text.endswith(("\n", "\r")):
        return text + nl
    return text


def variant_h2_to_bold(text: str, old_h2: str) -> str:
    """将 ## 变体名 h2 转为 **变体名** 加粗（与变体主页其他变体一致）。"""
    return re.sub(
        r"^##\s+" + re.escape(old_h2) + r"\s*$",
        "**" + old_h2 + "**",
        text,
        count=1,
        flags=re.MULTILINE,
    )


def main() -> None:
    # ============================================================
    # 1. 武僧/page_53 → page_55（哈罗牌守卫）
    # ============================================================
    page53, nl53 = read_text(MONK_PAGE_53)
    page53 = ensure_trailing_newline(page53, nl53)

    # page_53 仅含 ## 哈罗牌守卫（HARROW WARDEN）【武僧变体】 + 来源 + 正文
    # 转为 **变体名** 风格，附带隐藏标记 + 来源
    body53 = page53.strip()
    if not body53.startswith("<!-- THH-source:变体_选项/武僧1.md:哈罗牌守卫 -->"):
        raise SystemExit("[FATAL] 武僧/page_53 缺少预期的隐藏标记")
    # h2 → 加粗
    body53 = variant_h2_to_bold(body53, "哈罗牌守卫（HARROW WARDEN）【武僧变体】")
    body53 = body53.rstrip()
    body53 = normalize_blank_lines(body53)

    page55, nl55 = read_text(MONK_PAGE_55)
    page55 = ensure_trailing_newline(page55, nl55)
    page55_new = page55 + nl55 + body53 + nl55
    page55_new = normalize_blank_lines(page55_new)
    write_text(MONK_PAGE_55, page55_new, nl55)
    print(f"[OK] 武僧 page_55 追加哈罗牌守卫: {len(page55_new)} 字符")

    # ============================================================
    # 2. 召唤师/page_411 → page_410（故事召唤师变体）
    # ============================================================
    page411, nl411 = read_text(SUMMONER_PAGE_411)
    page411 = ensure_trailing_newline(page411, nl411)
    body411 = page411.strip()
    if not body411.startswith("<!-- THH-source:变体_选项/召唤师.md:故事召唤师 -->"):
        raise SystemExit("[FATAL] 召唤师/page_411 缺少预期的隐藏标记")
    body411 = variant_h2_to_bold(body411, "故事召唤师（Story Summoner）【召唤师变体】")
    body411 = body411.rstrip()
    body411 = normalize_blank_lines(body411)

    page410, nl410 = read_text(SUMMONER_PAGE_410)
    page410 = ensure_trailing_newline(page410, nl410)
    page410_new = page410 + nl410 + body411 + nl410
    page410_new = normalize_blank_lines(page410_new)
    write_text(SUMMONER_PAGE_410, page410_new, nl410)
    print(f"[OK] 召唤师 page_410 追加故事召唤师: {len(page410_new)} 字符")

    # ============================================================
    # 3. THH_...md 中 故事形态幻灵 → page_1346（幻灵范例）
    # ============================================================
    thh_md, nl_thh = read_text(SUMMONER_THH_MD)
    thh_md = ensure_trailing_newline(thh_md, nl_thh)

    # 切下"## 新幻灵范例（故事形态 Storykin）"段：跳过上半部分的"## 故事召唤师"
    cut_marker = "## 新幻灵范例（故事形态 Storykin）"
    cut_idx = thh_md.find(cut_marker)
    if cut_idx < 0:
        raise SystemExit(f"[FATAL] 未在 THH 源文件找到 {cut_marker}")
    storykin_raw = thh_md[cut_idx:].lstrip("\r\n")

    # 源文件中 h2 标题 + 来源注释 + 正文需要保留（来源注释讲的是"故事形态"那部分）
    # 但实际源文件中"## 新幻灵范例（故事形态 Storykin）"下面的格式是：
    #   > 来源：哈罗牌手册（Tarot Heroes Handbook）THH...
    #   故事形态（Storykin）
    #   故事形态的幻灵...
    # 第一行是 markdown 的"..." 来源注释，但实际看起来是 ">" 引用块形式
    # 让我们清理一下，并把标题转为与 飞鸟型/双体型 一致的 `**故事形态（Storykin）**` 加粗风格

    lines = storykin_raw.split("\n")
    # 找 "> 来源：" 行作为分界，前面是标题，后面是正文
    source_line_idx = None
    for i, ln in enumerate(lines):
        if ln.startswith("> 来源："):
            source_line_idx = i
            break
    if source_line_idx is None:
        raise SystemExit("[FATAL] 故事形态段未找到 '> 来源：' 行")

    # 标题（h2）→ 加粗
    title_line = lines[0].replace("## ", "").strip()
    bold_title = f"**{title_line}**"

    # 重新组装：加粗标题 + 来源 + 空白 + 正文（其余行）
    source_line = lines[source_line_idx]
    body_lines = lines[source_line_idx + 1 :]
    # 去掉正文首尾空行
    while body_lines and body_lines[0].strip() == "":
        body_lines.pop(0)
    while body_lines and body_lines[-1].strip() == "":
        body_lines.pop()

    # 在每行正文前加上"**字段名**："样式以匹配现有格式（飞鸟型/双体型）
    # 实际上源文件已经把数据写成了一行紧凑文本，我们保留原样，仅添加来源标记
    # 末尾追加隐藏标记
    storykin_block_lines = [
        bold_title,
        source_line,
        "",
    ]
    storykin_block_lines.extend(body_lines)
    storykin_block_lines.extend([
        "",
        "<!-- THH-source:变体_选项/召唤师.md:故事形态幻灵 -->",
    ])
    storykin_block = "\n".join(storykin_block_lines).rstrip()
    storykin_block = normalize_blank_lines(storykin_block)

    page1346, nl1346 = read_text(SUMMONER_PAGE_1346)
    page1346 = ensure_trailing_newline(page1346, nl1346)
    page1346_new = page1346 + nl1346 + storykin_block + nl1346
    page1346_new = normalize_blank_lines(page1346_new)
    write_text(SUMMONER_PAGE_1346, page1346_new, nl1346)
    print(f"[OK] 召唤师 page_1346 追加故事形态幻灵: {len(page1346_new)} 字符")

    # ============================================================
    # 4. 删除源/错放文件
    # ============================================================
    for f in [MONK_PAGE_53, SUMMONER_PAGE_411, SUMMONER_THH_MD]:
        if f.exists():
            f.unlink()
            print(f"[OK] 删除: {f}")
        else:
            print(f"[WARN] 不存在: {f}")


if __name__ == "__main__":
    main()