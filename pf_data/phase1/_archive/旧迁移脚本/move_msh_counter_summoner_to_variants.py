"""撤回 MSH 制法召唤师变体的错放：page_1346 → page_410。

按 class_subcategory_mapping.md §1.2，召唤师变体应入 page_410（变体主页），
page_1346 是幻灵范例主页（飞鸟型/双体型等），不应包含变体。

精确切点（page_1346）：
  行 10 末尾 `<!-- MSH-source:变体/page_665.md:制法召唤师 -->`
  行 11-15 制法召唤师正文（4 个能力串联为长段）
  行 16 `> 来源：怪物召唤者手册（Monster Summoner's Handbook），...MSH → 变体`
整段从 `<!-- MSH-source...` 起切到 `> 来源：...变体` 止（含尾部换行）。
不要混进行 9-10 的 骑手纽带（幻灵进化，留 page_1346）和行 19+ 的 故事形态。
"""
import re
from pathlib import Path

PHASE1 = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
ORG = PHASE1 / "pf_rules_md_organized"

SUMMONER_PAGE_1346 = ORG / "职业" / "基础职业" / "召唤师" / "page_1346.md"
SUMMONER_PAGE_410 = ORG / "职业" / "基础职业" / "召唤师" / "page_410.md"

MARKER = "<!-- MSH-source:变体/page_665.md:制法召唤师 -->"
SOURCE_LINE_PREFIX = "> 来源：怪物召唤者手册（Monster Summoner's Handbook）"

TITLE_PREFIX = "制法召唤师（Counter-Summoner)——召唤师变体（兼容Unchained）"
TITLE_AFTER = "当大多数召唤师擅长召唤怪物时"


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


def compile_patterns() -> tuple[re.Pattern, re.Pattern, re.Pattern]:
    # title_pat: ^(<变体抬头>)(?=当大多数召唤师擅长召唤怪物时)
    title_pat = re.compile(
        r"^(" + re.escape(TITLE_PREFIX) + r")(?=" + re.escape(TITLE_AFTER) + r")"
    )
    # ability_pat: 在能力名前加换行（lookbehind 中文标点 + lookahead 能力名 + 全角开括号）
    ability_pat = re.compile(
        r"(?<=[。；])"           # lookbehind: 。 or ；
        + r"(?="                 # lookahead open
        + r"(?:"                  # non-capture open
        + r"反制召唤|侦测召唤|弱化召唤|高等弱化召唤"
        + r")"                    # non-capture close
        + r"（"                   # literal full-width open
        + r")"                    # lookahead close
    )
    # ab_header_pat: 段头加粗 ^(能力名)（(English Name)）（Su）
    ab_header_pat = re.compile(
        r"^("                     # capture open
        + r"反制召唤|侦测召唤|弱化召唤|高等弱化召唤"
        + r")"                    # capture close
        + r"（("                  # literal open + capture open
        + r"[^）]+"                # negated char class (anything but ）)
        + r")"                    # capture close
        + r"）（Su）"              # literal close + （Su）
    )
    return title_pat, ability_pat, ab_header_pat


def format_counter_summoner_block(marker: str, raw_body: str, source_line: str) -> str:
    """把页 1346 里挤在一段中的 4 个能力拆成 4 个段落（每能力独立一段），加上变体标题。"""
    title_pat, ability_pat, ab_header_pat = compile_patterns()

    # 1. 剥变体抬头
    m = title_pat.search(raw_body)
    if not m:
        raise SystemExit("[FATAL] 未在制法召唤师正文开头匹配到变体抬头")
    title_text = m.group(1)
    intro = raw_body[m.end():].lstrip()

    # 2. 在能力名前加换行（让 4 个能力各成一段）
    parts = ability_pat.split(intro)
    if not parts:
        raise SystemExit("[FATAL] 制法召唤师正文未拆分出任何段落")

    # 3. 给每段能力加粗段头
    formatted_paragraphs: list[str] = []
    for i, chunk in enumerate(parts):
        chunk_stripped = chunk.strip()
        if not chunk_stripped:
            continue
        mh = ab_header_pat.match(chunk_stripped)
        if mh:
            cn, en = mh.group(1), mh.group(2)
            rest = chunk_stripped[mh.end():].lstrip("：:")
            # 段头格式：**反制召唤（Counter-summon，Su）**：...
            formatted_paragraphs.append(f"**{cn}（{en}，Su）**：{rest}")
        else:
            # 第一段是开头简介，按原文保留
            formatted_paragraphs.append(chunk_stripped)

    if not formatted_paragraphs:
        raise SystemExit("[FATAL] 制法召唤师正文格式化后无段落")

    block = (
        marker
        + "\n\n"
        + f"**{title_text}**"
        + "\n"
        + source_line
        + "\n\n"
        + "\n\n".join(formatted_paragraphs)
        + "\n"
    )
    return normalize_blank_lines(block)


def main() -> None:
    # ============================================================
    # 1. 从 page_1346 切出 制法召唤师 段（含 marker + 正文 + 来源行）
    # ============================================================
    page1346, nl1346 = read_text(SUMMONER_PAGE_1346)
    page1346 = ensure_trailing_newline(page1346, nl1346)

    marker_idx = page1346.find(MARKER)
    if marker_idx < 0:
        raise SystemExit(f"[FATAL] 未在 page_1346 找到 {MARKER}")

    pre_block = page1346[:marker_idx].rstrip() + nl1346
    after_marker = page1346[marker_idx + len(MARKER):]
    after_marker = after_marker.lstrip("\r\n")

    src_idx = after_marker.find(SOURCE_LINE_PREFIX)
    if src_idx < 0:
        raise SystemExit(f"[FATAL] 未在 page_1346 制法召唤师段找到 {SOURCE_LINE_PREFIX}")
    nl_after_src = after_marker.find("\n", src_idx)
    if nl_after_src < 0:
        nl_after_src = len(after_marker)
    source_line = after_marker[src_idx:nl_after_src].rstrip("\r\n")
    raw_body = after_marker[:src_idx].rstrip("\r\n")
    after_source = after_marker[nl_after_src:]

    page1346_new = pre_block + after_source
    page1346_new = normalize_blank_lines(page1346_new)
    write_text(SUMMONER_PAGE_1346, page1346_new, nl1346)
    print(f"[OK] page_1346 已切走 制法召唤师 段: {len(page1346_new)} 字符")

    # ============================================================
    # 2. 把 制法召唤师 段格式化后追加到 page_410
    # ============================================================
    block = format_counter_summoner_block(MARKER, raw_body, source_line)

    page410, nl410 = read_text(SUMMONER_PAGE_410)
    page410 = ensure_trailing_newline(page410, nl410)
    page410_new = page410 + nl410 + block + nl410
    page410_new = normalize_blank_lines(page410_new)
    write_text(SUMMONER_PAGE_410, page410_new, nl410)
    print(f"[OK] page_410 已追加 制法召唤师: {len(page410_new)} 字符")


if __name__ == "__main__":
    main()