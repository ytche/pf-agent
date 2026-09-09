"""test_race_postprocess.py — 种族模块后处理链测试

覆盖 RaceBackfillBookFromSource（POSTPROCESSORS 预留决策点落地）：book '?'
且 metadata.source 为「出自《X pg. N》」形态时，按源数据书名体系映射表回填。
"""

import json
from pathlib import Path

import pytest

from vectorizer.processors.race import RaceBackfillBookFromSource


def make_chunk(doc_id, title="测试种族", book="?", source=""):
    return {
        "chunk_id": f"{doc_id}-{title}-1",
        "doc_id": doc_id,
        "title": title,
        "aliases": [],
        "text": f"**属性调整：** +2敏捷\n> 来源：{title}（Test Book），页码见原书，未整理 → 测试书",
        "component_type": "race_trait",
        "metadata": {"source": source, "format_cluster": "standard"},
        "book_abbreviation": book,
        "book_name_cn": "",
        "book_name_en": "",
        "source_confidence": 0,
        "chm_toc_path": "种族 → 罕见种族",
    }


def write_chunks(dirpath: Path, chunks):
    p = dirpath / "chunks.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return p


def read_chunks(dirpath: Path):
    p = dirpath / "chunks.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


@pytest.fixture
def sample_dir(tmp_path):
    """含六类 book 状态的样本产物目录（映射命中×2 / 未映射 / 已解析 / 无 source / 英文书名）"""
    chunks = [
        # ① 映射命中（带页码形态）
        make_chunk("page_934", "半兽人亚种", source="出自《进阶种族手册 pg. 1》"),
        # ② 映射命中（无页码形态）
        make_chunk("page_934", "荒野亚种", source="出自《荒野英雄》"),
        # ③ 未映射书名 → 保持 '?'
        make_chunk("page_999", "未知来源", source="出自《未收录之书 pg. 5》"),
        # ④ book 已解析 → 不动
        make_chunk("page_10", "精灵", book="ISR", source="出自《内海种族 pg. 212》"),
        # ⑤ 无 source → 不动
        make_chunk("page_11", "无来源"),
        # ⑥ 英文书名形态
        make_chunk("page_934", "莱西", source="出自《Ultimate Wilderness pg. 23》"),
    ]
    write_chunks(tmp_path, chunks)
    return tmp_path


def test_book_backfill_from_source(sample_dir):
    """映射命中填三字段 + 置信度 65；未映射/已解析/无 source 不动"""
    RaceBackfillBookFromSource().run(sample_dir, report_dir=sample_dir / "reports")
    rows = {c["title"]: c for c in read_chunks(sample_dir)}

    # ① 带页码 → 剥页码命中
    assert rows["半兽人亚种"]["book_abbreviation"] == "ARG"
    assert rows["半兽人亚种"]["book_name_cn"] == "种族指南"
    assert rows["半兽人亚种"]["book_name_en"] == "Advanced Race Guide"
    assert rows["半兽人亚种"]["source_confidence"] == 65
    # ② 无页码形态
    assert rows["荒野亚种"]["book_abbreviation"] == "HotW"
    assert rows["荒野亚种"]["book_name_cn"] == "荒野英雄"
    assert rows["荒野亚种"]["source_confidence"] == 65
    # ⑥ 英文书名
    assert rows["莱西"]["book_abbreviation"] == "UW"
    assert rows["莱西"]["book_name_en"] == "Ultimate Wilderness"
    # ③ 未映射保持 '?'
    assert rows["未知来源"]["book_abbreviation"] == "?"
    # ④ 已解析不动（幂等）
    assert rows["精灵"]["book_abbreviation"] == "ISR"
    assert rows["精灵"]["source_confidence"] == 0
    # ⑤ 无 source 不动
    assert rows["无来源"]["book_abbreviation"] == "?"


def test_book_backfill_idempotent(sample_dir):
    """跑两次产物不变（第二次全跳过）"""
    RaceBackfillBookFromSource().run(sample_dir, report_dir=sample_dir / "reports")
    snap1 = [(c["title"], c["book_abbreviation"], c["source_confidence"]) for c in read_chunks(sample_dir)]
    RaceBackfillBookFromSource().run(sample_dir, report_dir=sample_dir / "reports")
    snap2 = [(c["title"], c["book_abbreviation"], c["source_confidence"]) for c in read_chunks(sample_dir)]
    assert snap1 == snap2
