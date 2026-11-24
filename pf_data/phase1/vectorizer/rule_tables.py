"""rule_tables.py — 规则 chunk 内嵌表格共用解析器（KN221）

设计依据：docs/superpowers/specs/2026-11-12-kn221-rule-table-structuring-design.md
（D1~D5）。本模块是规则表格的单一解析事实源：处理器 infer_metadata 的 4 个
metadata 键与 rule_table_export.py 的 rule_tables.json 都只从这里取结果，
禁止各写一份。

候选口径（D1）：
  - 同一 chunk 内**连续** pipe 行构成一个 run（中间夹非 pipe 行即断开）；
  - run 内有分隔行且行数 ≥2，或无分隔行且行数 ≥3 → 一张表（排除单行碎片）；
  - 只含分隔行/空壳单元格的 run 也保留原文行（原文是唯一可回查的内容），
    不伪造行列结构。

分档（D2~D4，按分隔行在 run 内的位置）：
  - standard      分隔行位于 run 中部（1 ≤ k ≤ n-2）：表头在分隔行前、
                  数据行在分隔行后。分隔行前一行若是表题（`| 表：X |` 或
                  单格且在分隔行后紧跟多格表头），则表题存 caption、
                  表头取分隔行后第一行（page_299 动物伙伴表即此形态）；
  - flattened     分隔行在 run 尾（k = n-1）或 run 首（k = 0）：只保留原文
                  行，headers/rows 留空，不声明列级可靠（page_644 全部）；
  - no_separator  无分隔行：首行标为推断表头，header_inferred=True（D4）。

table_id（D5）：`{chunk_id}#t{index}`，index 为 chunk 内 1-based 顺序。
"""
import re
from dataclasses import dataclass
from typing import List, Sequence, Tuple

LAYOUT_STANDARD = "standard"
LAYOUT_FLATTENED = "flattened"
LAYOUT_NO_SEPARATOR = "no_separator"
LAYOUTS = (LAYOUT_STANDARD, LAYOUT_FLATTENED, LAYOUT_NO_SEPARATOR)

# pipe 行：行首（允许缩进）即 `|`（CHM→md 表格行可能带前导空格）
PIPE_LINE_RE = re.compile(r"^\s*\|")
# 分隔行：整行只有 | : - 与空白（`| --- | --- |`）
SEPARATOR_RE = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")
# 表题行：`| 表：动物伙伴基本数据 |` / `| 表2: X |`
CAPTION_RE = re.compile(r"^\s*\|\s*表\s*\d*\s*[：:]\s*(?P<title>[^|]+?)\s*\|\s*$")


def split_cells(line: str) -> List[str]:
    """物理 pipe 行 → 单元格列表：去首尾 `|`，格内空白 strip。

    中间的空单元格（合并列/跨列留白）原样保留，不压缩、不重排
    （spec 非目标：不修复合并列空单元格）。
    """
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _non_empty(cells: Sequence[str]) -> List[str]:
    return [c for c in cells if c]


def _normalize_title(text: str) -> str:
    return " ".join((text or "").split())


def _caption_of(line: str) -> str:
    """表题行 → 表题文本；非表题行返回空串"""
    m = CAPTION_RE.match(line)
    return _normalize_title(m.group("title")) if m else ""


@dataclass(frozen=True)
class Table:
    """一张表（chunk 内顺序 + 布局 + 原始行 + 按布局提供的结构）"""

    table_id: str
    chunk_id: str
    index: int                  # chunk 内 1-based 顺序
    layout: str
    caption: str
    headers: Tuple[str, ...]
    rows: Tuple[Tuple[str, ...], ...]
    header_inferred: bool
    raw_lines: Tuple[str, ...]
    line_start: int             # chunk text 内 1-based 起始行
    line_end: int               # chunk text 内 1-based 结束行

    @property
    def title(self) -> str:
        """表名：表题 > 表头首个非空格 > 原文首行首个非空格"""
        if self.caption:
            return self.caption
        for cell in self.headers:
            if cell:
                return _normalize_title(cell)
        if self.raw_lines:
            for cell in split_cells(self.raw_lines[0]):
                if cell:
                    return _normalize_title(cell)
        return ""

    @property
    def row_count(self) -> int:
        """数据行数：standard/no_separator 为结构行数；flattened 为原文非分隔
        行数（不承诺列结构，只表示原文规模）"""
        if self.layout == LAYOUT_FLATTENED:
            return sum(1 for ln in self.raw_lines if not SEPARATOR_RE.match(ln))
        return len(self.rows)

    def to_dict(self) -> dict:
        return {
            "table_id": self.table_id,
            "chunk_id": self.chunk_id,
            "index": self.index,
            "layout": self.layout,
            "caption": self.caption,
            "title": self.title,
            "headers": list(self.headers),
            "rows": [list(row) for row in self.rows],
            "header_inferred": self.header_inferred,
            "row_count": self.row_count,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "raw_lines": list(self.raw_lines),
        }


def _pipe_runs(lines: Sequence[str]) -> List[List[int]]:
    """连续 pipe 行的行号 run 列表（非 pipe 行断开）"""
    runs: List[List[int]] = []
    current: List[int] = []
    for idx, line in enumerate(lines):
        if PIPE_LINE_RE.match(line):
            current.append(idx)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def _is_candidate(run_lines: Sequence[str], sep_positions: Sequence[int]) -> bool:
    """D1：有分隔行且 ≥2 行，或无分隔行且 ≥3 行"""
    if sep_positions:
        return len(run_lines) >= 2
    return len(run_lines) >= 3


def _build_table(chunk_id: str, index: int, lines: Sequence[str],
                 run: Sequence[int]) -> Table:
    raw = [lines[i] for i in run]
    n = len(raw)
    sep_positions = [i for i, ln in enumerate(raw) if SEPARATOR_RE.match(ln)]
    first_sep = sep_positions[0] if sep_positions else None
    table_id = f"{chunk_id}#t{index}"

    def make(layout: str, caption: str = "", headers: Sequence[str] = (),
             rows: Sequence[Sequence[str]] = (), inferred: bool = False) -> Table:
        return Table(
            table_id=table_id, chunk_id=chunk_id, index=index, layout=layout,
            caption=caption, headers=tuple(headers),
            rows=tuple(tuple(r) for r in rows), header_inferred=inferred,
            raw_lines=tuple(raw), line_start=run[0] + 1, line_end=run[-1] + 1,
        )

    # ---- no_separator：首行推断表头（D4）----
    if first_sep is None:
        headers = split_cells(raw[0])
        rows = [split_cells(ln) for ln in raw[1:]]
        return make(LAYOUT_NO_SEPARATOR, headers=headers, rows=rows, inferred=True)

    # ---- flattened：分隔行在 run 尾或 run 首（D3）----
    if first_sep in (0, n - 1):
        caption = ""
        for ln in raw:
            caption = _caption_of(ln)
            if caption:
                break
        return make(LAYOUT_FLATTENED, caption=caption)

    # ---- standard：分隔行在 run 中部（D2）----
    k = first_sep
    header_idx = k - 1
    data_start = k + 1
    caption = _caption_of(raw[header_idx])
    if caption:
        # 表题占分隔行前一行（`| 表：X |` + 分隔行 + 真表头）：表头取分隔行后首行
        header_idx = k + 1
        data_start = k + 2
    else:
        pre_cells = _non_empty(split_cells(raw[k - 1]))
        next_cells = (_non_empty(split_cells(raw[k + 1]))
                      if k + 1 < n and not SEPARATOR_RE.match(raw[k + 1]) else [])
        # 单格前置行 + 分隔行后紧跟多格表头 → 视作表题（如「| 0环药水与油 |」
        # + 分隔行 + 「| 药水或油 | ... |」），而不是把章节名当表头
        if len(pre_cells) == 1 and len(next_cells) >= 2:
            caption = _normalize_title(pre_cells[0])
            header_idx = k + 1
            data_start = k + 2

    headers: List[str] = []
    if header_idx < n and not SEPARATOR_RE.match(raw[header_idx]):
        headers = split_cells(raw[header_idx])
    rows = [split_cells(ln) for ln in raw[data_start:]
            if not SEPARATOR_RE.match(ln)]
    return make(LAYOUT_STANDARD, caption=caption, headers=headers, rows=rows)


def parse_tables(text: str, chunk_id: str) -> List[Table]:
    """解析 chunk 正文中的全部表格，按出现顺序返回（table_id 1-based 编号）"""
    if not text:
        return []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    tables: List[Table] = []
    for run in _pipe_runs(lines):
        run_lines = [lines[i] for i in run]
        sep_positions = [i for i, ln in enumerate(run_lines)
                         if SEPARATOR_RE.match(ln)]
        if not _is_candidate(run_lines, sep_positions):
            continue
        tables.append(_build_table(chunk_id, len(tables) + 1, lines, run))
    return tables


def table_metadata(text: str, chunk_id: str) -> dict:
    """chunk metadata 的 4 个表格键（spec D6：键名与值形态固定）

    - has_table：是否含候选表
    - table_ids：table_id 列表（1-based 顺序）
    - table_titles：表名列表（与 table_ids 同序同长）
    - table_row_counts：行数列表（与 table_ids 同序同长）
    """
    tables = parse_tables(text, chunk_id)
    return {
        "has_table": bool(tables),
        "table_ids": [t.table_id for t in tables],
        "table_titles": [t.title for t in tables],
        "table_row_counts": [t.row_count for t in tables],
    }
