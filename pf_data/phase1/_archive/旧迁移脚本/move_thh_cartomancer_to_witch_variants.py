"""把 THH 牌灵师变体从女巫/page_92.md 迁移到女巫/page_70.md（女巫职业变体页）。

按 class_subcategory_mapping.md §1，女巫变体 → 女巫/page_70.md；
page_92.md 仅保留女巫巫术+庇护主主列表，不应含变体。
"""
import re
from pathlib import Path

PHASE1 = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
ORG = PHASE1 / "pf_rules_md_organized"

WITCH_PAGE_92 = ORG / "职业" / "基础职业" / "女巫" / "page_92.md"
WITCH_PAGE_70 = ORG / "职业" / "基础职业" / "女巫" / "page_70.md"


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


def main() -> None:
    # ---------- 1. 从女巫 page_92.md 切下 "THH 特有变体" 段 ----------
    page92, nl92 = read_text(WITCH_PAGE_92)
    page92 = ensure_trailing_newline(page92, nl92)

    # 切点：从 "## 哈罗牌手册 THH 特有变体" 起到文件结尾都丢弃
    cut_marker = "## 哈罗牌手册 THH 特有变体"
    cut_idx = page92.find(cut_marker)
    if cut_idx < 0:
        raise SystemExit(f"[FATAL] 未在 page_92 找到 {cut_marker}")

    # 主体：保留 cut_idx 之前的内容，并把 cut_idx 之前的尾部空白清干净
    page92_body = page92[:cut_idx].rstrip() + nl92
    page92_body = normalize_blank_lines(page92_body)
    write_text(WITCH_PAGE_92, page92_body, nl92)
    print(f"[OK] page_92 切短完成: {WITCH_PAGE_92} ({len(page92_body)} 字符)")

    # 牌灵师正文：cut_idx 之后，去掉 `## 哈罗牌手册 THH 特有变体` 这行本身 + 紧随的空行
    # 然后把 `### 牌灵师（CARTOMANCER）【女巫变体】` 转为 `**牌灵师（CARTOMANCER）【女巫变体】**`（与其他变体追加的 `**变体名**` 风格一致）
    cartomancer_raw = page92[cut_idx + len(cut_marker):]
    cartomancer_raw = cartomancer_raw.lstrip("\r\n")
    # 替换 `### 牌灵师...` 为 `**牌灵师...**`
    cartomancer_text = re.sub(
        r"^### 牌灵师（CARTOMANCER）【女巫变体】\s*$",
        "**牌灵师（CARTOMANCER）【女巫变体】**",
        cartomancer_raw,
        count=1,
        flags=re.MULTILINE,
    )
    cartomancer_text = cartomancer_text.rstrip()
    cartomancer_text = normalize_blank_lines(cartomancer_text)

    # ---------- 2. 追加到女巫 page_70.md（女巫变体页） ----------
    page70, nl70 = read_text(WITCH_PAGE_70)
    page70 = ensure_trailing_newline(page70, nl70)

    appended = (
        page70
        + nl70
        + "<!-- THH-source:变体_选项/女巫+巫术.md:牌灵师 -->"
        + nl70
        + cartomancer_text
        + nl70
    )
    appended = normalize_blank_lines(appended)
    write_text(WITCH_PAGE_70, appended, nl70)
    print(f"[OK] page_70 追加完成: {WITCH_PAGE_70} ({len(appended)} 字符)")


if __name__ == "__main__":
    main()
