"""执行 THH 子类别迁移：合并女巫 page_92、追加盗贼/魔战士、删除冗余/源文件。

详细对应关系与设计理由见 class_subcategory_mapping.md §1 与 §3。
"""
import re
from pathlib import Path

PHASE1 = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
ORG = PHASE1 / "pf_rules_md_organized"

ROOT_PAGE_92 = ORG / "page_92.md"
ROOT_PAGE_62 = ORG / "page_62.md"
ROOT_PAGE_83 = ORG / "page_83.md"

WITCH_PAGE_92 = ORG / "职业" / "基础职业" / "女巫" / "page_92.md"
ROGUE_PAGE_62 = ORG / "职业" / "核心职业" / "盗贼" / "page_62.md"
MAGUS_PAGE_83 = ORG / "职业" / "基础职业" / "魔战士" / "page_83.md"

THH_TALENTS = ORG / "专长" / "哈罗牌手册THH_盗贼天赋.md"
THH_HEX = ORG / "专长" / "哈罗牌手册THH_女巫巫术.md"
THH_ARCANA = ORG / "专长" / "哈罗牌手册THH_魔战士奥能.md"


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


def demote_headings(text: str) -> str:
    """将 h1→h2、h2→h3、h3→h4、h4→h5、h5→h6、h6→h6（封顶）；用于把聚合文件嵌入主页面时避免 §16.4 跳级。"""
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        m = re.match(r"^(#{1,6})(\s)", line)
        if not m:
            out.append(line)
            continue
        hashes, rest = m.group(1), line[m.end():]
        if len(hashes) >= 6:
            out.append("######" + rest)
        else:
            out.append("#" + hashes + rest)
    return "\n".join(out)


def strip_top_h1_and_marker(text: str) -> str:
    """移除文件顶部首个 # h1 标题行 + 紧随的隐藏标记 + 空行；聚合文件的"自身标题"嵌入主页面后不需要。"""
    lines = text.split("\n")
    idx = 0
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx < len(lines) and lines[idx].startswith("# "):
        idx += 1
    while idx < len(lines) and (lines[idx].strip() == "" or lines[idx].lstrip().startswith("<!-- ")):
        idx += 1
    return "\n".join(lines[idx:])


def main() -> None:
    # ---------- 1. 女巫 page_92 合并 ----------
    root92, nl92 = read_text(ROOT_PAGE_92)
    root92 = ensure_trailing_newline(root92, nl92)

    # 占卜者 + 哈罗诅咒：剥 h1 标题和文件级隐藏标记，剩余 h2→h3、h3→h4
    thh_hex_body = THH_HEX.read_text(encoding="utf-8")
    thh_hex_body = strip_top_h1_and_marker(thh_hex_body)
    thh_hex_body = demote_headings(thh_hex_body)
    thh_hex_body = normalize_blank_lines(thh_hex_body.strip())

    # 牌灵师变体：从旧女巫/page_92.md 提取；旧文件末尾的 `**新巫术（New Witch Hexes）**` 是占位空标题
    witch92_old, _ = read_text(WITCH_PAGE_92)
    cartomancer_body = witch92_old.strip()
    if cartomancer_body.endswith("**新巫术（New Witch Hexes）**"):
        cartomancer_body = cartomancer_body[: -len("**新巫术（New Witch Hexes）**")].rstrip()
    cartomancer_body = normalize_blank_lines(cartomancer_body)
    cartomancer_body = demote_headings(cartomancer_body)

    merged = (
        root92
        + nl92
        + "## 哈罗牌手册 THH 特有巫术"
        + nl92
        + nl92
        + thh_hex_body
        + nl92
        + nl92
        + "## 哈罗牌手册 THH 特有变体"
        + nl92
        + nl92
        + cartomancer_body
        + nl92
    )
    merged = normalize_blank_lines(merged)
    write_text(WITCH_PAGE_92, merged, nl92)
    print(f"[OK] 女巫 page_92 合并完成: {WITCH_PAGE_92} ({len(merged)} 字符)")

    # ---------- 2. 盗贼 page_62 追加 THH 盗贼天赋 ----------
    rogue62, nl62 = read_text(ROGUE_PAGE_62)
    rogue62 = ensure_trailing_newline(rogue62, nl62)
    thh_talents_body = THH_TALENTS.read_text(encoding="utf-8")
    thh_talents_body = strip_top_h1_and_marker(thh_talents_body)
    thh_talents_body = demote_headings(thh_talents_body)
    thh_talents_body = normalize_blank_lines(thh_talents_body.strip())

    rogue62_new = (
        rogue62
        + nl62
        + "## 哈罗牌手册 THH 特有盗贼天赋"
        + nl62
        + nl62
        + thh_talents_body
        + nl62
    )
    rogue62_new = normalize_blank_lines(rogue62_new)
    write_text(ROGUE_PAGE_62, rogue62_new, nl62)
    print(f"[OK] 盗贼 page_62 追加完成: {ROGUE_PAGE_62} ({len(rogue62_new)} 字符)")

    # ---------- 3. 魔战士 page_83 追加 THH 魔战士奥能 ----------
    magus83, nl83 = read_text(MAGUS_PAGE_83)
    magus83 = ensure_trailing_newline(magus83, nl83)
    thh_arcana_body = THH_ARCANA.read_text(encoding="utf-8")
    thh_arcana_body = strip_top_h1_and_marker(thh_arcana_body)
    thh_arcana_body = demote_headings(thh_arcana_body)
    thh_arcana_body = normalize_blank_lines(thh_arcana_body.strip())

    magus83_new = (
        magus83
        + nl83
        + "## 哈罗牌手册 THH 特有魔战士奥能"
        + nl83
        + nl83
        + thh_arcana_body
        + nl83
    )
    magus83_new = normalize_blank_lines(magus83_new)
    write_text(MAGUS_PAGE_83, magus83_new, nl83)
    print(f"[OK] 魔战士 page_83 追加完成: {MAGUS_PAGE_83} ({len(magus83_new)} 字符)")

    # ---------- 4. 删除冗余/源文件 ----------
    for f in [ROOT_PAGE_92, ROOT_PAGE_62, ROOT_PAGE_83, THH_TALENTS, THH_HEX, THH_ARCANA]:
        if f.exists():
            f.unlink()
            print(f"[OK] 删除: {f}")
        else:
            print(f"[WARN] 不存在: {f}")


if __name__ == "__main__":
    main()
