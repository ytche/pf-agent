"""KN221 规则表格解析与导出测试

覆盖：
1. 解析器单元级（rule_tables.parse_tables）：
   - standard 两形态：`| 表：X |` + 分隔行 + 真表头（page_299 形态）；
     普通表头行 + 分隔行；合并列空单元格原样保留；
   - flattened：分隔行在表尾（page_644 形态）/ 表首，只留原文不造列结构；
   - no_separator：首行推断表头 header_inferred=True；
   - 候选口径 D1：单行碎片、无分隔且 <3 行不成为表；chunk 内多表 1-based 编号。
2. 真实产物级（规则 chunks / rule_tables.json，文件缺失时跳过）：
   - 612 表 / 472 chunk，standard=435 / flattened=173 / no_separator=4（spec §6）；
   - page_299 动物伙伴表 20 行、第 5 行 HD=5/BAB=+3；
   - page_644 全部 flattened 且不伪造表头/行；
   - chunks metadata 4 键与解析结果一致（同源事实校验）。
"""
import json
import re
import sys
from pathlib import Path

import pytest

PHASE1_ROOT = Path(__file__).resolve().parents[2]
if str(PHASE1_ROOT) not in sys.path:
    sys.path.insert(0, str(PHASE1_ROOT))

from vectorizer.rule_tables import (  # noqa: E402
    LAYOUT_FLATTENED,
    LAYOUT_NO_SEPARATOR,
    LAYOUT_STANDARD,
    parse_tables,
    split_cells,
    table_metadata,
)

CHUNKS_PATH = PHASE1_ROOT / "vectorizer" / "output" / "规则" / "chunks.jsonl"
TABLES_PATH = PHASE1_ROOT / "vectorizer" / "output" / "规则" / "rule_tables.json"
REPORT_PATH = PHASE1_ROOT / "vectorizer" / "output" / "规则" / "rule_table_export_report.json"

CAPTIONED_STANDARD = "\n".join([
    "**动物伙伴一览 (Animal Companions)**",
    "",
    "| 表：动物伙伴基本数据 |",
    "| --- |",
    "| 等级 |  | HD |  | BAB |",
    "| 1 |  | 2 |  | +1 |",
    "| 2 |  | 3 |  | +2 |",
])

PLAIN_STANDARD = "\n".join([
    "| 等级 | BAB |",
    "| --- | --- |",
    "| 1 | +1 |",
])

FLATTENED_TAIL = "\n".join([
    "| 生命骰 | 能量抗力 | 伤害减免 |",
    "| --- | --- | --- |",
])

FLATTENED_HEAD = "\n".join([
    "| --- | --- |",
    "| 甲 | 乙 |",
    "| 丙 | 丁 |",
])

NO_SEPARATOR = "\n".join([
    "| 甲 | 乙 |",
    "| 1 | 2 |",
    "| 3 | 4 |",
])


class TestParser:
    def test_captioned_standard_header_after_separator(self):
        """page_299 形态：表题占分隔行前一行，真表头在分隔行之后。"""
        (table,) = parse_tables(CAPTIONED_STANDARD, "rule_page_299_0000")
        assert table.table_id == "rule_page_299_0000#t1"
        assert table.layout == LAYOUT_STANDARD
        assert table.caption == "动物伙伴基本数据"
        assert table.title == "动物伙伴基本数据"
        assert table.headers == ("等级", "", "HD", "", "BAB")  # 合并列空单元格不压缩
        assert table.row_count == 2
        assert table.rows[0] == ("1", "", "2", "", "+1")
        assert table.line_start == 3 and table.line_end == 7
        assert table.raw_lines[0] == "| 表：动物伙伴基本数据 |"

    def test_plain_standard_header_before_separator(self):
        (table,) = parse_tables(PLAIN_STANDARD, "cid")
        assert table.layout == LAYOUT_STANDARD
        assert table.caption == ""
        assert table.headers == ("等级", "BAB")
        assert table.rows == (("1", "+1"),)
        assert table.header_inferred is False

    def test_standard_single_cell_caption_then_multi_cell_header(self):
        """`| 0环药水与油 |` + 分隔行 + 多格表头 → 前置单格行作表题，不冒充表头。"""
        text = "| 0环药水与油 |\n| --- | --- |\n| 药水或油 | 价格 |\n| 神导术 | 25gp |"
        (table,) = parse_tables(text, "cid")
        assert table.layout == LAYOUT_STANDARD
        assert table.caption == "0环药水与油"
        assert table.headers == ("药水或油", "价格")
        assert table.rows == (("神导术", "25gp"),)

    def test_flattened_tail_keeps_raw_only(self):
        """page_644 形态：分隔行在表尾 → 只保留原文，headers/rows 为空。"""
        (table,) = parse_tables(FLATTENED_TAIL, "cid")
        assert table.layout == LAYOUT_FLATTENED
        assert table.headers == () and table.rows == ()
        assert table.title == "生命骰"
        assert table.row_count == 1  # 原文非分隔行数
        assert table.raw_lines == ("| 生命骰 | 能量抗力 | 伤害减免 |",
                                   "| --- | --- | --- |")

    def test_flattened_head(self):
        (table,) = parse_tables(FLATTENED_HEAD, "cid")
        assert table.layout == LAYOUT_FLATTENED
        assert table.headers == () and table.rows == ()
        assert table.row_count == 2

    def test_no_separator_infers_first_row(self):
        (table,) = parse_tables(NO_SEPARATOR, "cid")
        assert table.layout == LAYOUT_NO_SEPARATOR
        assert table.header_inferred is True
        assert table.headers == ("甲", "乙")
        assert table.rows == (("1", "2"), ("3", "4"))

    def test_single_line_fragment_not_table(self):
        assert parse_tables("| 孤行 |", "cid") == []

    def test_two_pipe_lines_without_separator_not_table(self):
        """D1：无分隔行须 ≥3 行，2 行 pipe 碎片排除。"""
        assert parse_tables("| 甲 |\n| 乙 |", "cid") == []

    def test_three_pipe_lines_without_separator_is_table(self):
        tables = parse_tables("| 甲 |\n| 1 |\n| 2 |", "cid")
        assert len(tables) == 1 and tables[0].layout == LAYOUT_NO_SEPARATOR

    def test_multiple_tables_one_based_ids(self):
        text = "\n".join([CAPTIONED_STANDARD, "", "中间散文", "",
                          "| 等级 | BAB |", "| --- | --- |", "| 1 | +1 |"])
        tables = parse_tables(text, "rule_x_0000")
        assert [t.table_id for t in tables] == ["rule_x_0000#t1", "rule_x_0000#t2"]
        assert [t.index for t in tables] == [1, 2]
        assert tables[1].line_start == 11

    def test_pipe_run_breaks_on_non_pipe_line(self):
        """非 pipe 行断开 run（环境表断行形态），不得跨段拼表。"""
        text = "| 表：X |\n| --- |\n| a | b |\n散文\n| 1 | 2 |\n| 3 | 4 |"
        tables = parse_tables(text, "cid")
        assert len(tables) == 1
        assert tables[0].table_id == "cid#t1"

    def test_split_cells_preserves_empty_cells(self):
        assert split_cells("| a |  | c |") == ["a", "", "c"]
        assert split_cells("        |") == [""]

    def test_empty_shell_run_keeps_raw_lines(self):
        """仅空壳/分隔行：保留原文行（可回查），不伪造结构；空壳不计行数。"""
        (table,) = parse_tables("|  |  |\n| --- | --- |", "cid")
        assert table.layout == LAYOUT_FLATTENED
        assert table.headers == () and table.rows == ()
        assert table.row_count == 0

    def test_table_metadata_keys_and_shapes(self):
        meta = table_metadata(CAPTIONED_STANDARD, "cid")
        assert set(meta) == {"has_table", "table_ids", "table_titles", "table_row_counts"}
        assert meta["has_table"] is True
        assert meta["table_ids"] == ["cid#t1"]
        assert meta["table_titles"] == ["动物伙伴基本数据"]
        assert meta["table_row_counts"] == [2]
        empty = table_metadata("纯散文，无表格。", "cid")
        assert empty == {"has_table": False, "table_ids": [],
                         "table_titles": [], "table_row_counts": []}


@pytest.fixture(scope="module")
def chunks():
    if not CHUNKS_PATH.exists():
        pytest.skip("规则 chunks 未生成（跑 python3 -m vectorizer.cicd verify --category rule）")
    return [json.loads(line) for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()]


@pytest.fixture(scope="module")
def artifact():
    if not TABLES_PATH.exists():
        pytest.skip("rule_tables.json 未生成（跑 python3 rule_table_export.py）")
    return json.loads(TABLES_PATH.read_text(encoding="utf-8"))


class TestRealChunks:
    def test_known_chunk_fixtures(self, chunks):
        c299 = next(c for c in chunks if c["chunk_id"] == "rule_page_299_0000")
        assert c299["metadata"]["has_table"] is True
        assert c299["metadata"]["table_ids"] == ["rule_page_299_0000#t1"]
        assert "page_644" in {c["doc_id"] for c in chunks}

    def test_page_299_standard_table_row5(self, chunks):
        """spec §6 代表表：20 行，第 5 行 HD=5、BAB=+3。"""
        text = next(c for c in chunks if c["chunk_id"] == "rule_page_299_0000")["text"]
        (table,) = parse_tables(text, "rule_page_299_0000")
        assert table.layout == LAYOUT_STANDARD
        assert table.caption == "动物伙伴基本数据"
        assert table.row_count == 20
        hd_col = table.headers.index("HD")
        bab_col = table.headers.index("BAB")
        assert table.rows[4][hd_col] == "5"
        assert table.rows[4][bab_col] == "+3"

    def test_page_644_flattened_degradation(self, chunks):
        """spec §6：flattened 只返回原文并标降级，不伪造表头/列级值。"""
        texts = [c for c in chunks if c["doc_id"] == "page_644"]
        tables = [t for c in texts for t in parse_tables(c["text"], c["chunk_id"])]
        assert tables and all(t.layout == LAYOUT_FLATTENED for t in tables)
        for t in tables:
            assert t.headers == () and t.rows == ()
            assert t.raw_lines

    def test_counts_match_spec(self, chunks):
        """spec §6：612 表 / 472 chunk；standard=435、flattened=173、no_separator=4。"""
        counts = {}
        chunk_ids = set()
        for c in chunks:
            for t in parse_tables(c["text"], c["chunk_id"]):
                counts[t.layout] = counts.get(t.layout, 0) + 1
                chunk_ids.add(c["chunk_id"])
        assert sum(counts.values()) == 612
        assert len(chunk_ids) == 472
        assert counts == {LAYOUT_STANDARD: 435, LAYOUT_FLATTENED: 173,
                          LAYOUT_NO_SEPARATOR: 4}

    def test_chunk_metadata_consistent_with_parser(self, chunks):
        for c in chunks:
            meta = c["metadata"]
            for key in ("has_table", "table_ids", "table_titles", "table_row_counts"):
                assert key in meta, c["chunk_id"]
            tables = parse_tables(c["text"], c["chunk_id"])
            assert meta["has_table"] is bool(tables)
            assert meta["table_ids"] == [t.table_id for t in tables]
            assert meta["table_titles"] == [t.title for t in tables]
            assert meta["table_row_counts"] == [t.row_count for t in tables]
            if tables:
                assert meta["table_ids"][0] == f"{c['chunk_id']}#t1"


class TestArtifact:
    def test_schema_self_describing(self, artifact):
        assert artifact["version"] == "1.0"
        assert artifact["category"] == "rule"
        assert artifact["table_id_index_base"] == 1
        assert re.fullmatch(r"[0-9a-f]{64}", artifact["source_fingerprint"])
        assert artifact["generated_from"].endswith("规则/chunks.jsonl")

    def test_counts_and_report_agree(self, artifact):
        counts = artifact["counts"]
        assert counts["tables"] == len(artifact["tables"]) == 612
        assert counts["chunks"] == 472
        assert counts["by_layout"] == {LAYOUT_STANDARD: 435, LAYOUT_FLATTENED: 173,
                                       LAYOUT_NO_SEPARATOR: 4}
        if REPORT_PATH.exists():
            report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            assert report["summary"] == counts

    def test_table_records_shape(self, artifact):
        for table_id, rec in artifact["tables"].items():
            assert rec["table_id"] == table_id
            assert table_id.startswith(rec["chunk_id"] + "#t")
            assert rec["layout"] in (LAYOUT_STANDARD, LAYOUT_FLATTENED, LAYOUT_NO_SEPARATOR)
            assert rec["doc_id"]
            assert rec["raw_lines"]
            assert rec["line_start"] <= rec["line_end"]
            assert isinstance(rec["header_inferred"], bool)
            if rec["layout"] == LAYOUT_FLATTENED:
                assert rec["headers"] == [] and rec["rows"] == []
            elif rec["layout"] == LAYOUT_STANDARD:
                assert rec["row_count"] == len(rec["rows"])
            else:
                assert rec["header_inferred"] is True
                assert rec["row_count"] == len(rec["rows"])

    def test_raw_line_range_points_into_chunk_text(self, artifact, chunks):
        by_id = {c["chunk_id"]: c for c in chunks}
        for rec in list(artifact["tables"].values())[:50]:
            lines = by_id[rec["chunk_id"]]["text"].replace("\r\n", "\n").split("\n")
            assert lines[rec["line_start"] - 1] == rec["raw_lines"][0]
            assert lines[rec["line_end"] - 1] == rec["raw_lines"][-1]
