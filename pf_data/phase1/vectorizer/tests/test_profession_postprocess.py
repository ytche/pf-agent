"""test_profession_postprocess.py — 职业 finalize 索引写出测试

覆盖 ProfessionIndexWriter（POSTPROCESSORS 唯一步骤，CP3 补产物）：
class_archetype_index.json 从最终 chunks.jsonl 按 §3 映射重建——class_name /
archetype_name 读 metadata，source_book ← book_name_cn、source_book_english
← book_name_en（顶层），其余顶层 1:1；component_type 归类（overview /
feature / archetype）。

幂等：同一产物重复执行输出字节一致（不修改 chunk 数据，重跑 diff 为空）。
"""
import json

import pytest

from vectorizer.postprocess.profession_index import ProfessionIndexWriter


def _chunk(cid, ct, title, cn, an=None, abbr="CRB", bcn="核心规则", ben="Core Rulebook", toc="职业 → 核心职业"):
    d = {
        "chunk_id": cid,
        "doc_id": "核心职业/圣骑士/page_55.md",
        "category": "profession",
        "component_type": ct,
        "title": title,
        "text": f"{title}：正文。",
        "book_abbreviation": abbr,
        "book_name_cn": bcn,
        "book_name_en": ben,
        "source_confidence": 80,
        "chm_toc_path": toc,
        "aliases": [],
        "metadata": {"class_name": cn},
    }
    if an:
        d["metadata"]["archetype_name"] = an
    return d


def _write_chunks(dirpath, chunks):
    p = dirpath / "chunks.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


@pytest.fixture
def sample_dir(tmp_path):
    """圣骑士 overview + 2 变体 + 1 feature + 女巫 overview 的最小产物目录"""
    chunks = [
        _chunk("ov-pal", "class_overview", "圣骑士", "圣骑士"),
        _chunk("feat-oath", "class_feature", "反腐化誓约（Oath against Corruption）", "圣骑士", an="圣律沿循者", abbr="UM", bcn="极限魔法", ben="Ultimate Magic", toc="职业 → 核心职业 → 圣骑士"),
        _chunk("arch-oath", "class_archetype", "圣律沿循者（Oathbound Paladin）", "圣骑士", an="圣律沿循者", abbr="UM", bcn="极限魔法", ben="Ultimate Magic", toc="职业 → 核心职业 → 圣骑士"),
        _chunk("arch-gray", "class_archetype", "灰骑士（Gray Paladin）", "圣骑士", an="灰骑士", abbr="HA", bcn="地狱复仇者", ben="Hell's Vengeance", toc="职业 → 核心职业 → 圣骑士"),
        _chunk("ov-witch", "class_overview", "女巫", "女巫"),
    ]
    _write_chunks(tmp_path, chunks)
    return tmp_path


class TestProfessionIndexWriter:
    def test_writes_index_file(self, sample_dir):
        """运行后 class_archetype_index.json 落盘"""
        stats = ProfessionIndexWriter().run(sample_dir)
        assert (sample_dir / "class_archetype_index.json").exists()
        assert stats == {"classes": 2, "archetypes": 2}

    def test_index_structure_and_metadata_mapping(self, sample_dir):
        """按 §3 映射归类：metadata.class_name 归职业，book 字段走顶层"""
        ProfessionIndexWriter().run(sample_dir)
        idx = json.loads((sample_dir / "class_archetype_index.json").read_text(encoding="utf-8"))
        # 圣骑士 overview + feature 归类
        pal = idx["圣骑士"]
        assert pal["overview_chunk_ids"] == ["ov-pal"]
        assert "feat-oath" in pal["feature_chunk_ids"]
        # 变体按 metadata.archetype_name 归组，book 字段取自顶层
        oath = pal["archetypes"]["圣律沿循者"]
        assert oath["base_class"] == "圣骑士"
        assert oath["source_book"] == "极限魔法"          # ← book_name_cn
        assert oath["source_book_english"] == "Ultimate Magic"  # ← book_name_en
        assert oath["book_abbreviation"] == "UM"
        assert oath["chm_toc_path"] == "职业 → 核心职业 → 圣骑士"
        assert oath["chunk_ids"] == ["arch-oath"]
        assert pal["archetypes"]["灰骑士"]["book_abbreviation"] == "HA"
        # 女巫独立
        assert "ov-witch" in idx["女巫"]["overview_chunk_ids"]

    def test_idempotent(self, sample_dir):
        """幂等：重复执行输出字节一致（纯读 chunks.jsonl 重建）"""
        ProfessionIndexWriter().run(sample_dir)
        first = (sample_dir / "class_archetype_index.json").read_bytes()
        ProfessionIndexWriter().run(sample_dir)
        second = (sample_dir / "class_archetype_index.json").read_bytes()
        assert first == second

    def test_missing_metadata_falls_back(self, tmp_path):
        """无 metadata 职业字段 → 未知职业/未知变体兜底（对齐老产物口径）"""
        bare = {
            "chunk_id": "x1",
            "doc_id": "x.md",
            "category": "profession",
            "component_type": "class_archetype",
            "title": "无名变体",
            "text": "正文",
            "book_abbreviation": "",
            "book_name_cn": "",
            "book_name_en": "",
            "source_confidence": 0,
            "chm_toc_path": "",
            "aliases": [],
            "metadata": {},
        }
        _write_chunks(tmp_path, [bare])
        ProfessionIndexWriter().run(tmp_path)
        idx = json.loads((tmp_path / "class_archetype_index.json").read_text(encoding="utf-8"))
        assert "未知职业" in idx
        assert "未知变体" in idx["未知职业"]["archetypes"]
