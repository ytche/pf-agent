"""D2 清单导出补充白盒测试——边界与异常路径（QA 补充，针对 coder 18 条测试的盲区）

coder 测试（test_list_exports.py）以真实数据集成断言为主，缺单元级边界：
  - 碎片行恰好是 sink 目标 text 的最后一行
  - 碎片行出现在条目中间（同 doc 多候选 → 归属唯一性兜底）
  - sink 目标不存在 / 目标不唯一 → fragments_unsunk 非空（导出断言应失败）
  - 空 chunks（零条目）/ 字段缺失（无 title、无 metadata）
  - 软检查 version 不符 / 非法 JSON / stats.total 低于下界 → 仅 WARN 通过
  - 同名条目跨 doc 不冲突（chunk_id 级归属）
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from vectorizer.list_export import (export_list, fold_ws, fold_lower,
                                    table_fragment_reason, make_list_soft_check,
                                    VERSION)


def mk(cid, doc, title, text, ctype="gear", md=None, book="CORE"):
    return {"chunk_id": cid, "doc_id": doc, "title": title, "text": text,
            "component_type": ctype, "book_abbreviation": book,
            "book_name_cn": "核心规则书", "aliases": [],
            "metadata": md or {}}


FRAG = mk("equipment_page_1_0002", "page_1", "类型：普通",
          "| 类型：普通 | 5 gp | 1 磅 |")


def write_chunks(tmp_path, chunks):
    p = tmp_path / "chunks.jsonl"
    p.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks),
                 encoding="utf-8")
    return tmp_path


class TestFoldTools:
    def test_fold_ws_multiline_crlf(self):
        assert fold_ws("a  b\r\n\tc ") == "a b c"

    def test_fold_lower_strips_all_ws(self):
        assert fold_lower("Power Attack\n") == "powerattack"
        assert fold_lower("Power  Attack") == "powerattack"


class TestFragmentDetection:
    def test_empty_and_missing_fields_not_fragment(self):
        assert table_fragment_reason({}) is None
        assert table_fragment_reason({"title": "", "text": "| a | b |"}) is None
        assert table_fragment_reason({"title": "类型：普通"}) is None  # 无 text
        # 多行 text 不是净增补机制标记
        c = mk("x", "d", "类型：普通", "| a |\n| b |")
        assert table_fragment_reason(c) is None

    def test_section_marker_exemption(self):
        c = mk("x", "d", "表格：某表", "| 表格：某表 | gp |")
        assert table_fragment_reason(c) is None
        c2 = mk("x", "d", "边栏：价格", "| 边栏：价格 | gp |")
        assert table_fragment_reason(c2) is None


class TestSinkEdges:
    def test_fragment_last_row_of_target(self):
        """碎片行恰好是 sink 目标 text 的最后一行。"""
        host = mk("equipment_page_1_0001", "page_1", "装备甲",
                  "| 装备甲 | 10 gp |\n" + FRAG["text"])
        out = write_chunks(self._tmp(), [host, FRAG])
        r = export_list(category="equipment", out_dir=str(out),
                        main_types={"gear"}, clean_table_fragments=True)
        assert r["entries"] == 1
        data = json.loads((out / "equipment_lists.json").read_text(encoding="utf-8"))
        assert data["entries"][0]["sunk_table_fragments"][0]["chunk_id"] == FRAG["chunk_id"]
        assert data["stats"]["fragments_sunk"] == 1

    def test_ambiguous_target_unsunk_asserts(self):
        """同 doc 两个 chunk 都含碎片整行 → 无唯一 sink 目标 → 导出断言失败。"""
        a = mk("equipment_page_1_0001", "page_1", "甲", "| 甲 |\n" + FRAG["text"])
        b = mk("equipment_page_1_0003", "page_1", "乙", "| 乙 |\n" + FRAG["text"])
        out = write_chunks(self._tmp(), [a, b, FRAG])
        with pytest.raises(AssertionError, match="未找到唯一 sink"):
            export_list(category="equipment", out_dir=str(out),
                        main_types={"gear"}, clean_table_fragments=True)

    def test_no_sink_target_unsunk_asserts(self):
        """sink 目标不存在（孤儿碎片）→ 断言失败（兜底 = 显式失败，非静默丢失）。"""
        out = write_chunks(self._tmp(), [FRAG])
        with pytest.raises(AssertionError, match="未找到唯一 sink"):
            export_list(category="equipment", out_dir=str(out),
                        main_types={"gear"}, clean_table_fragments=True)

    def test_same_name_cross_doc_no_conflict(self):
        """同名条目跨 doc：归属按 chunk_id + 同 doc 匹配，互不干扰。"""
        d1 = mk("equipment_page_1_0001", "page_1", "同名", "| 同名 | 1 gp |")
        d2 = mk("equipment_page_2_0001", "page_2", "同名", "| 同名 | 2 gp |")
        out = write_chunks(self._tmp(), [d1, d2])
        r = export_list(category="equipment", out_dir=str(out),
                        main_types={"gear"})
        assert r["entries"] == 2
        data = json.loads((out / "equipment_lists.json").read_text(encoding="utf-8"))
        assert {e["doc_id"] for e in data["entries"]} == {"page_1", "page_2"}

    def test_empty_chunks_below_min_asserts(self):
        out = write_chunks(self._tmp(), [])
        with pytest.raises(AssertionError, match="下界"):
            export_list(category="equipment", out_dir=str(out),
                        main_types={"gear"}, min_entries=1)

    def test_missing_title_excluded_from_entries(self):
        """title 缺失的 chunk 不进 entries（空 name 断言会拦住——应失败而非脏数据）。"""
        c = mk("equipment_page_1_0001", "page_1", "", "| x | 1 gp |")
        out = write_chunks(self._tmp(), [c])
        with pytest.raises(AssertionError, match="空 name"):
            export_list(category="equipment", out_dir=str(out),
                        main_types={"gear"})

    def test_excluded_component_types_recorded(self):
        c = mk("equipment_page_1_0001", "page_1", "甲", "| 甲 |", ctype="equipment_intro")
        m = mk("equipment_page_1_0002", "page_1", "乙", "| 乙 |")
        out = write_chunks(self._tmp(), [c, m])
        export_list(category="equipment", out_dir=str(out), main_types={"gear"})
        data = json.loads((out / "equipment_lists.json").read_text(encoding="utf-8"))
        assert data["excluded_component_types"] == ["equipment_intro"]
        assert [e["name"] for e in data["entries"]] == ["乙"]

    @staticmethod
    def _tmp(tmp_path_factory=None):
        import tempfile
        return Path(tempfile.mkdtemp())


class TestSoftCheckEdges:
    def _make(self, tmp_path, payload):
        p = tmp_path / "x_lists.json"
        if payload is not None:
            p.write_text(payload if isinstance(payload, str)
                         else json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return make_list_soft_check("t", str(p), 10)

    def test_version_mismatch_warns_pass(self, tmp_path):
        check = self._make(tmp_path, {"version": "0.9", "stats": {"total": 99}})
        ok, issues = check[1]([], {})
        assert ok and issues == []

    def test_bad_json_warns_pass(self, tmp_path):
        check = self._make(tmp_path, "{oops")
        ok, issues = check[1]([], {})
        assert ok and issues == []

    def test_total_below_min_warns_pass(self, tmp_path):
        check = self._make(tmp_path, {"version": VERSION, "stats": {"total": 3}})
        ok, issues = check[1]([], {})
        assert ok and issues == []

    def test_ok_no_warn(self, tmp_path):
        check = self._make(tmp_path, {"version": VERSION, "stats": {"total": 50}})
        ok, issues = check[1]([], {})
        assert ok and issues == []
