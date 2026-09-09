"""BackfillSlotByPage 后处理测试（KN190，TDD 先写测试）

覆盖：11 位置页 missing 条目回填页面词形 / 有值条目不动（parsed 优先，A1：
7 条页内混排自声明例外保持原值）/ 非 wondrous_item 不动 / 无映射聚合 doc
不动 / 幂等（二次运行零变更）/ field_status.slot missing→parsed（B1 拍板）。
"""
import json

from vectorizer.processors.equipment import (
    BackfillSlotByPage,
    _EQUIP_PAGE_SLOT_MAP,
)


def _write_chunks(tmp_path, chunks):
    p = tmp_path / "chunks.jsonl"
    p.write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks) + "\n",
        encoding="utf-8",
    )
    return p


def _read_rows(tmp_path):
    return [json.loads(l) for l in (tmp_path / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]


def _mk(cid, doc, ct="wondrous_item", slot=None, fs_slot=None):
    meta = {}
    if slot is not None:
        meta["slot"] = slot
    if fs_slot is not None:
        meta["field_status"] = {"slot": fs_slot}
    return {"chunk_id": cid, "doc_id": doc, "component_type": ct,
            "title": cid, "text": "x", "metadata": meta}


def test_backfill_missing_slot_by_page(tmp_path):
    """page_223 纯描述条目（无 slot）回填为「腰部」，field_status.slot → parsed"""
    chunks = [_mk("c1", "page_223", fs_slot="missing"),
              _mk("c2", "page_227", fs_slot="missing")]
    _write_chunks(tmp_path, chunks)
    stats = BackfillSlotByPage().run(tmp_path)
    rows = _read_rows(tmp_path)
    assert rows[0]["metadata"]["slot"] == "腰部"
    assert rows[0]["metadata"]["field_status"]["slot"] == "parsed"
    assert rows[1]["metadata"]["slot"] == "脚部"
    assert stats == {"backfilled": 2, "position_total": 2,
                     "missing_before": 2, "missing_after": 0}


def test_backfill_keeps_parsed_slot(tmp_path):
    """有值条目一律不动（源数据字段声明优先，A1 例外白名单语义）"""
    chunks = [_mk("c1", "page_223", slot="腰部", fs_slot="parsed"),
              _mk("c2", "page_228", slot="无", fs_slot="parsed")]
    _write_chunks(tmp_path, chunks)
    BackfillSlotByPage().run(tmp_path)
    rows = _read_rows(tmp_path)
    assert rows[0]["metadata"]["slot"] == "腰部"
    assert rows[1]["metadata"]["slot"] == "无"  # 抒情竖琴型自声明例外不被覆盖


def test_backfill_skips_non_wondrous(tmp_path):
    """weapon/gear 不动（武器无位置槽 not_applicable 语义）"""
    chunks = [_mk("c1", "page_228", ct="weapon", fs_slot="not_applicable")]
    _write_chunks(tmp_path, chunks)
    BackfillSlotByPage().run(tmp_path)
    rows = _read_rows(tmp_path)
    assert rows[0]["metadata"].get("slot") is None


def test_backfill_skips_agg_doc_no_map(tmp_path):
    """聚合书 doc_id（无页面映射）不回填"""
    chunks = [_mk("c1", "内海战斗ISC_戒指权杖奇物", fs_slot="missing")]
    _write_chunks(tmp_path, chunks)
    BackfillSlotByPage().run(tmp_path)
    rows = _read_rows(tmp_path)
    assert rows[0]["metadata"].get("slot") is None


def test_backfill_idempotent(tmp_path):
    """二次运行零变更（有值不动）"""
    chunks = [_mk("c1", "page_233", fs_slot="missing")]
    _write_chunks(tmp_path, chunks)
    b = BackfillSlotByPage()
    b.run(tmp_path)
    first = (tmp_path / "chunks.jsonl").read_text(encoding="utf-8")
    b.run(tmp_path)
    second = (tmp_path / "chunks.jsonl").read_text(encoding="utf-8")
    assert first == second


def test_page_slot_map_full_11(tmp_path):
    """映射表 11 项覆盖 page_223~233，值域 ⊆ CHM L4 位置词形"""
    assert set(_EQUIP_PAGE_SLOT_MAP) == {f"page_{n}" for n in range(223, 234)}
    assert set(_EQUIP_PAGE_SLOT_MAP.values()) <= {
        "腰部", "躯体", "胸部", "眼部", "脚部", "手部",
        "头部", "头饰", "颈部", "肩部", "腕部",
    }
