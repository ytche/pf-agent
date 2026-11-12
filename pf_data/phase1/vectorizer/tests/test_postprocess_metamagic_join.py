"""test_postprocess_metamagic_join.py — KN228 超魔专长一览 join 回填单测

覆盖（KN228 方案实施步骤 1 单测要求）：
  - join 唯一命中回填（三书字段 + confidence 55 + metadata.source_backfill
    证据块三键齐全）
  - join 源排除 page_1367 自身（防自引用）与 book=="?" chunk
  - feat_index 行可作 join 源（ISM/DH 拍板探针口径）
  - 多书冲突默认不动；CONFLICT_OVERRIDES（水生法术→UW）生效且取库内 cn/en
  - 白名单护栏：命中但 title ∉ WHITELIST → 不回填并计入 blocked
  - 无命中保持 "?" 不动
  - 幂等：第二次 run diff 为空；非 page_1367 chunk 零触碰
"""
import json

import pytest

from vectorizer.postprocess.feat_chain import ApplyFeatMetamagicIndexJoin

from vectorizer.tests.test_postprocess import make_chunk, read_chunks, write_chunks


def _src_chunk(chunk_id, doc, title, abbr, cn, en, aliases=None, ctype="feat"):
    c = make_chunk(doc, title, book=abbr)
    c["chunk_id"] = chunk_id
    c["book_name_cn"] = cn
    c["book_name_en"] = en
    c["aliases"] = aliases or []
    c["component_type"] = ctype
    return c


def _target(chunk_id, title, aliases=None):
    c = make_chunk("page_1367", title, book="?")
    c["chunk_id"] = chunk_id
    c["aliases"] = aliases or []
    c["component_type"] = "feat_index"
    c["metadata"] = {"source": ""}
    return c


class TestMetamagicIndexJoin:
    def test_unique_hit_backfills_with_evidence(self, tmp_path):
        d = tmp_path / "out"
        d.mkdir()
        src = _src_chunk("feat_page_196_0001", "page_196", "强化法术", "APG",
                         "进阶玩家指南", "Advanced Player's Guide",
                         aliases=["Intensified Spell"])
        tgt = _target("feat_page_1367_0001", "强化法术",
                      aliases=["intensified spell"])
        write_chunks(d, [src, tgt])
        stats = ApplyFeatMetamagicIndexJoin().run(d, tmp_path / "rep")
        assert stats["applied"] == 1
        rows = read_chunks(d)
        t = rows[1]
        assert t["book_abbreviation"] == "APG"
        assert t["book_name_cn"] == "进阶玩家指南"
        assert t["book_name_en"] == "Advanced Player's Guide"
        assert t["source_confidence"] == 55
        sb = t["metadata"]["source_backfill"]
        assert sb["method"] == "feat_metamagic_index_join"
        assert sb["matched_key"] in ("强化法术", "intensified spell")
        assert sb["matched_chunk_id"] == "feat_page_196_0001"

    def test_en_alias_hit_case_insensitive_strip_book_suffix(self, tmp_path):
        """英文别名键：小写不敏感 + 剥【书】后缀（join 源别名带后缀形态）"""
        d = tmp_path / "out"
        d.mkdir()
        src = _src_chunk("feat_page_195_0001", "page_195", "法术瞬发", "CRB",
                         "核心规则书", "Core Rulebook",
                         aliases=["Quicken Spell【CRB】"])
        tgt = _target("feat_page_1367_0001", "法术瞬发",
                      aliases=["QUICKEN SPELL"])
        write_chunks(d, [src, tgt])
        ApplyFeatMetamagicIndexJoin().run(d, tmp_path / "rep")
        assert read_chunks(d)[1]["book_abbreviation"] == "CRB"

    def test_self_doc_excluded_as_join_source(self, tmp_path):
        """page_1367 自身已定稿条目不作 join 源（防自引用扩散）"""
        d = tmp_path / "out"
        d.mkdir()
        src = _src_chunk("feat_page_1367_0099", "page_1367", "强化法术", "APG",
                         "进阶玩家指南", "Advanced Player's Guide")
        tgt = _target("feat_page_1367_0001", "强化法术")
        write_chunks(d, [src, tgt])
        stats = ApplyFeatMetamagicIndexJoin().run(d, tmp_path / "rep")
        assert stats["applied"] == 0 and stats["unresolved"] == 1

    def test_unknown_book_source_excluded(self, tmp_path):
        """book=="?" chunk 不作 join 源"""
        d = tmp_path / "out"
        d.mkdir()
        src = _src_chunk("feat_x_0001", "其他专长", "强化法术", "?",
                         "", "")
        tgt = _target("feat_page_1367_0001", "强化法术")
        write_chunks(d, [src, tgt])
        stats = ApplyFeatMetamagicIndexJoin().run(d, tmp_path / "rep")
        assert stats["unresolved"] == 1

    def test_feat_index_row_can_be_join_source(self, tmp_path):
        """ISM/DH 拍板探针口径：feat_index 行可作 join 源"""
        d = tmp_path / "out"
        d.mkdir()
        src = _src_chunk("feat_page_277_0004", "page_277", "Tenebrous Spell",
                         "ISM", "内海魔法", "Inner Sea Magic",
                         aliases=["Tenebrous Spell"], ctype="feat_index")
        tgt = _target("feat_page_1367_0001", "晦暗法术",
                      aliases=["Tenebrous Spell"])
        write_chunks(d, [src, tgt])
        stats = ApplyFeatMetamagicIndexJoin().run(d, tmp_path / "rep")
        assert stats["applied"] == 1
        assert read_chunks(d)[1]["book_abbreviation"] == "ISM"

    def test_multi_book_conflict_untouched(self, tmp_path):
        d = tmp_path / "out"
        d.mkdir()
        a = _src_chunk("feat_a_0001", "page_a", "雷鸣法术", "CRB",
                       "核心规则书", "Core Rulebook")
        b = _src_chunk("feat_b_0001", "page_b", "Thundering Spell", "UM",
                       "极限魔法", "Ultimate Magic", aliases=["Thundering Spell"])
        tgt = _target("feat_page_1367_0001", "雷鸣法术",
                      aliases=["Thundering Spell"])
        write_chunks(d, [a, b, tgt])
        stats = ApplyFeatMetamagicIndexJoin().run(d, tmp_path / "rep")
        assert stats["applied"] == 0 and stats["conflicts"] == 1
        assert read_chunks(d)[2]["book_abbreviation"] == "?"

    def test_conflict_override_aquatic_to_uw(self, tmp_path):
        """水生法术（CTT vs UW）拍板裁决 → UW，cn/en 取库内 UW 值"""
        d = tmp_path / "out"
        d.mkdir()
        a = _src_chunk("feat_page_566_0001", "page_566", "水生法术", "CTT",
                       "近战战术工具箱", "Melee Tactics Toolbox")
        b = _src_chunk("feat_专长11_0098", "专长11", "Aquatic Spell", "UW",
                       "极限荒野", "Ultimate Wilderness",
                       aliases=["Aquatic Spell"])
        tgt = _target("feat_page_1367_0001", "水生法术",
                      aliases=["Aquatic Spell"])
        write_chunks(d, [a, b, tgt])
        stats = ApplyFeatMetamagicIndexJoin().run(d, tmp_path / "rep")
        assert stats["applied"] == 1
        t = read_chunks(d)[2]
        assert t["book_abbreviation"] == "UW"
        assert t["book_name_cn"] == "极限荒野"
        assert t["metadata"]["source_backfill"]["method"] == \
            "feat_metamagic_index_join"

    def test_whitelist_blocks_unapproved_hit(self, tmp_path):
        """白名单护栏：命中唯一书但 title ∉ WHITELIST → 不回填 + blocked"""
        d = tmp_path / "out"
        d.mkdir()
        src = _src_chunk("feat_z_0001", "page_z", "未批法术", "CRB",
                         "核心规则书", "Core Rulebook")
        tgt = _target("feat_page_1367_0001", "未批法术")
        write_chunks(d, [src, tgt])
        stats = ApplyFeatMetamagicIndexJoin().run(d, tmp_path / "rep")
        assert stats["applied"] == 0 and stats["blocked"] == 1
        assert read_chunks(d)[1]["book_abbreviation"] == "?"

    def test_no_hit_stays_unknown(self, tmp_path):
        d = tmp_path / "out"
        d.mkdir()
        tgt = _target("feat_page_1367_0001", "库外法术")
        write_chunks(d, [tgt])
        stats = ApplyFeatMetamagicIndexJoin().run(d, tmp_path / "rep")
        assert stats["unresolved"] == 1
        assert read_chunks(d)[0]["book_abbreviation"] == "?"

    def test_non_target_chunk_untouched_and_idempotent(self, tmp_path):
        d = tmp_path / "out"
        d.mkdir()
        src = _src_chunk("feat_page_196_0001", "page_196", "强化法术", "APG",
                         "进阶玩家指南", "Advanced Player's Guide")
        other = make_chunk("page_194", "别的专长", book="CRB")
        other["chunk_id"] = "feat_page_194_0001"
        other["book_name_cn"] = "核心规则书"
        other["book_name_en"] = "Core Rulebook"
        tgt = _target("feat_page_1367_0001", "强化法术")
        write_chunks(d, [src, other, tgt])
        step = ApplyFeatMetamagicIndexJoin()
        step.run(d, tmp_path / "rep")
        snapshot = (d / "chunks.jsonl").read_text(encoding="utf-8")
        stats2 = step.run(d, tmp_path / "rep")
        assert (d / "chunks.jsonl").read_text(encoding="utf-8") == snapshot
        assert stats2["applied"] == 0 and stats2["unresolved"] == 0
        rows = read_chunks(d)
        assert rows[1]["book_abbreviation"] == "CRB"  # 非 1367 chunk 未动
        assert "source_backfill" not in rows[1]["metadata"]
