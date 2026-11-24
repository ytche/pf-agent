"""test_spell_list_union_export.py — F-025 法术 union 1.1 去重导出白盒测试

覆盖（F-025 spec 2026-11-10 §10.1 数据侧验收口径）：
  - schema/scope：26 官方职业 + 2 union-only 职业（导师/红螳螂杀手）全在；
    OA 五职业零 derived；召唤师(掉链子) 不派生
  - KN243：union-only 职业 0~9 环、source_page=null/aliases=[]/official_list=false；
    巡林客派生经别名并入游侠（元数据不改）
  - 女巫 1 环 205 → 165（68 官方 + 97 新增派生，40 重复派生来源折叠）
  - union 1.1 条目契约：sources 完整、主来源首位、(chunk_id, source) 去重、
    顶层镜像、每来源 matched_by 枚举准确
  - 官方内部折叠（召唤师(掉链子) 6 环冰晶传送族）与官方/派生交叉合并
  - per_class_level 数量守恒；diff_counts「条目合并」== derived_duplicates_merged
  - KN246 `_dup` 原始候选报告不丢失；dedup_name_conflicts 结构
  - diff_unclassified == 0；重跑字节一致

测试内运行导出脚本（subprocess，cwd=phase1，与 spell_list_export 测试同先例）。
"""
import hashlib
import json
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pytest

PHASE1 = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PHASE1))
import spell_list_union_export as ex  # noqa: E402
import spell_list_export as sle  # noqa: E402
UNION = PHASE1 / "vectorizer/output/法术/spell_lists_union.json"
REPORT = PHASE1 / "vectorizer/output/法术/spell_list_union_report.json"
SPELL_LISTS = PHASE1 / "vectorizer/output/法术/spell_lists.json"
SPELL_REPORT = PHASE1 / "vectorizer/output/法术/spell_list_export_report.json"
CHUNKS = PHASE1 / "vectorizer/output/法术/chunks.jsonl"
MANIFEST = PHASE1 / "vectorizer/build_manifest.json"

OA = {"唤魂师", "秘学士", "通灵者", "异能者", "催眠师"}
LEGAL_TAGS = {"书范围外", "译名变体", "标题污染", "条目合并", "环级证据缺失",
              "清单页缺录"}
MATCHED_BY = {"official_primary", "derived_new", "official_cn", "official_en",
              "official_cn_and_en", "derived_cn", "derived_en",
              "derived_cn_and_en"}


def _run_export():
    return subprocess.run(
        [sys.executable, "spell_list_union_export.py"],
        cwd=PHASE1, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def products():
    if not CHUNKS.exists():
        pytest.skip("chunks.jsonl 缺失（CI 裸 checkout）——产物断言由 build check 覆盖")
    r = _run_export()
    assert r.returncode == 0, r.stdout + r.stderr
    return {
        "union": json.loads(UNION.read_text(encoding="utf-8")),
        "report": json.loads(REPORT.read_text(encoding="utf-8")),
    }


def _entries(union, cls, lv):
    return union["classes"][cls]["levels"][str(lv)]


UNION_ONLY = {"导师", "红螳螂杀手"}


class TestScope:
    def test_classes_26_official_plus_2_union_only(self, products):
        assert len(products["union"]["classes"]) == 28
        assert UNION_ONLY <= set(products["union"]["classes"])

    def test_official_classes_flagged(self, products):
        """官方清单职业 official_list=true；union-only 职业 false（显式派生空态）"""
        for cls, c in products["union"]["classes"].items():
            assert c["official_list"] is (cls not in UNION_ONLY), cls
            if cls in UNION_ONLY:
                assert c["source_page"] is None and c["aliases"] == [], cls
            else:
                assert c["source_page"], cls

    def test_union_only_classes_levels_0_to_9(self, products):
        """union-only 职业 0~9 环键齐全，条目全为 derived 主条目"""
        for cls in UNION_ONLY:
            levels = products["union"]["classes"][cls]["levels"]
            assert sorted(levels, key=int) == [str(i) for i in range(10)], cls
            entries = [e for lv in levels.values() for e in lv]
            assert entries, f"{cls} 派生条目不应为空"
            assert all(e["source"] == "derived" for e in entries), cls
            assert all(s["source"] == "derived"
                       for e in entries for s in e["sources"]), cls
            assert cls in products["report"]["union_only_classes"]

    def test_ranger_old_translation_merged_into_ranger(self, products):
        """KN243 D7：巡林客派生并入游侠（元数据不改，只并派生候选）"""
        lv1 = _entries(products["union"], "游侠", 1)
        lv4 = _entries(products["union"], "游侠", 4)
        assert any("spell_Spell ISWG_0011" in [s["chunk_id"] for s in e["sources"]]
                   for e in lv1)
        assert any("spell_Spell ISWG_0009" in [s["chunk_id"] for s in e["sources"]]
                   for e in lv4)
        # 巡林客不单独成键（并入游侠而非新建职业）
        assert "巡林客" not in products["union"]["classes"]

    def test_oa_five_zero_derived(self, products):
        """OA 五职业派生条目数 = 0（仅 official_list 透传）"""
        for c in OA:
            entries = [e for lv in products["union"]["classes"][c]["levels"].values()
                       for e in lv]
            assert entries, f"{c} 官方清单不应为空"
            assert all(e["source"] == "official_list" for e in entries), c
            assert all(s["source"] == "official_list"
                       for e in entries for s in e["sources"]), c

    def test_dirty_class_key_not_derived(self, products):
        cls_ = products["union"]["classes"]["召唤师(掉链子)"]
        entries = [e for lv in cls_["levels"].values() for e in lv]
        assert all(e["source"] == "official_list" for e in entries)

    def test_scope_classes_20(self, products):
        rep = products["report"]
        assert len(rep["scope_classes"]) == 20
        assert not (set(rep["scope_classes"]) & OA)
        assert not (set(rep["scope_classes"]) & UNION_ONLY)


class TestVersion:
    def test_union_version_1_1(self, products):
        assert products["union"]["version"] == "1.1"
        assert products["report"]["version"] == "1.1"

    def test_manifest_expected_1_1(self, products):
        man = json.loads(MANIFEST.read_text(encoding="utf-8"))
        art = next(a for a in man["artifacts"] if a["name"] == "lists.spell_union")
        assert art["schema"]["expected"] == "1.1"


class TestUnionContract:
    def test_every_entry_has_sources(self, products):
        for c in products["union"]["classes"].values():
            for entries in c["levels"].values():
                for e in entries:
                    assert isinstance(e["sources"], list) and e["sources"], e
                    assert e["sources"][0]["book"] == e["book"]
                    assert e["sources"][0]["chunk_id"] == e.get("chunk_id")
                    assert e["sources"][0]["source"] == e["source"]

    def test_source_keys_and_matched_by(self, products):
        for c in products["union"]["classes"].values():
            for entries in c["levels"].values():
                for e in entries:
                    for s in e["sources"]:
                        for k in ("book", "chunk_id", "source", "matched_by"):
                            assert k in s, (e, s, k)
                        assert s["matched_by"] in MATCHED_BY, s
                        if s["source"] == "derived":
                            assert s["chunk_id"], s
                            assert s.get("level_evidence", "").startswith(
                                "spell_level: "), s
                        else:
                            assert "chunk_id" in s  # 官方来源允许 null

    def test_chunk_source_pair_dedup(self, products):
        for c in products["union"]["classes"].values():
            for entries in c["levels"].values():
                for e in entries:
                    pairs = [(s["chunk_id"], s["source"]) for s in e["sources"]]
                    assert len(pairs) == len(set(pairs)), e

    def test_top_level_matched_by_mirror(self, products):
        for c in products["union"]["classes"].values():
            for entries in c["levels"].values():
                for e in entries:
                    if e["source"] == "derived":
                        assert e["matched_by"] == "derived_new", e
                        assert e["level_evidence"].startswith("spell_level: ")
                    else:
                        assert "matched_by" not in e, e
                        assert e["sources"][0]["matched_by"] == "official_primary"

    def test_primary_source_first_and_order(self, products):
        for c in products["union"]["classes"].values():
            for entries in c["levels"].values():
                for e in entries:
                    rest = e["sources"][1:]
                    seen = set()
                    for s in rest:
                        pair = (s["chunk_id"], s["source"])
                        assert pair not in seen, e
                        seen.add(pair)


class TestWitchLevel1:
    def test_205_to_165(self, products):
        """F-025 验收：女巫 1 环 205 原始 → 165 不同法术"""
        lv1 = _entries(products["union"], "女巫", 1)
        assert len(lv1) == 165, len(lv1)
        pl = products["report"]["per_class_level"]["女巫|1"]
        assert pl["official"] == 68
        assert pl["union"] == 165
        assert pl["derived_added"] == 97

    def test_duplicate_groups_folded_once(self, products):
        lv1 = _entries(products["union"], "女巫", 1)
        for name in ("雪球术", "精确施法", "护卫伙伴", "速凝术"):
            hits = [e for e in lv1 if e["cn"] == name]
            assert len(hits) == 1, (name, len(hits))
            assert len(hits[0]["sources"]) >= 2, (name, hits[0])

    def test_multi_source_books_visible(self, products):
        lv1 = _entries(products["union"], "女巫", 1)
        e = next(e for e in lv1 if e["cn"] == "精确施法")
        books = {s["book"] for s in e["sources"] if s["book"]}
        assert len(books) >= 2, e["sources"]

    def test_40_duplicate_derived_sources_merged(self, products):
        pl = products["report"]["per_class_level"]["女巫|1"]
        assert pl["derived_duplicates_merged"] == 40
        assert pl["official_merged"] + pl["derived_duplicates_merged"] == 108


class TestOfficialInternalFold:
    def test_dirty_summoner_level6_ice_teleport(self, products):
        """召唤师(掉链子) 6 环 冰晶传送UM / 冰晶传送 官方内部重复折叠"""
        lv6 = _entries(products["union"], "召唤师(掉链子)", 6)
        hits = [e for e in lv6 if "冰晶传送" in e["cn"]]
        assert len(hits) == 1, [(e["cn"], len(e["sources"])) for e in lv6]
        assert hits[0]["source"] == "official_list"
        assert hits[0]["sources"][0]["matched_by"] == "official_primary"
        pl = products["report"]["per_class_level"]["召唤师(掉链子)|6"]
        assert pl["official_duplicates_merged"] >= 1
        assert pl["union"] == pl["official"] - pl["official_duplicates_merged"]


class TestConservation:
    def test_all_class_level_equations(self, products):
        for key, pl in products["report"]["per_class_level"].items():
            official_retained = pl["official"] - pl["official_duplicates_merged"]
            assert pl["derived_candidates"] == (
                pl["derived_added"] + pl["official_merged"]
                + pl["derived_duplicates_merged"]), key
            assert pl["union"] == official_retained + pl["derived_added"], key

    def test_diff_entry_merge_equals_derived_duplicates(self, products):
        rep = products["report"]
        total_ddm = sum(pl["derived_duplicates_merged"]
                        for pl in rep["per_class_level"].values())
        assert rep["diff_counts"].get("条目合并", 0) == total_ddm

    def test_union_entry_counts_match_report(self, products):
        for cls, c in products["union"]["classes"].items():
            for lv, entries in c["levels"].items():
                assert (products["report"]["per_class_level"][f"{cls}|{lv}"]
                        ["union"] == len(entries)), (cls, lv)


class TestKn246AndConflicts:
    def test_kn246_dup_candidates_preserved(self, products):
        """KN246 _dup 原始候选报告：结构合法；当前数据无 _dup 时允许为空列表，
        但字段必须存在且任何条目都带完整明细（审计不静默丢失）。"""
        kn = products["report"]["kn246_duplicate_level_candidates"]
        assert isinstance(kn, list)
        for it in kn:
            for k in ("class", "level", "chunk_id", "cn", "book", "_dup"):
                assert k in it, (it, k)
            assert it["_dup"] is True

    def test_name_conflicts_structure(self, products):
        for it in products["report"]["dedup_name_conflicts"]:
            for k in ("class", "level", "primary_cn", "names", "norm_keys",
                      "sources", "matched"):
                assert k in it, (it, k)
            assert isinstance(it["matched"], list)
            for m in it["matched"]:
                for k in ("cn", "en", "chunk_id", "source", "matched_by",
                          "hit_keys"):
                    assert k in m, (m, k)


class TestReport:
    def test_diff_unclassified_zero(self, products):
        assert products["report"]["diff_unclassified"] == 0

    def test_all_diffs_tagged_legal(self, products):
        rep = products["report"]
        tagged = {k: v for k, v in rep["diff_counts"].items()}
        assert set(tagged) <= LEGAL_TAGS, set(tagged) - LEGAL_TAGS
        assert tagged.get("书范围外", 0) > 0

    def test_variant_candidates_all_kn017(self, products):
        for c in products["report"]["variant_candidates_pending"]:
            assert c["kn017_precedent"] is True, c

    def test_multi_source_entries_counted(self, products):
        total = sum(pl["multi_source_entries"]
                    for pl in products["report"]["per_class_level"].values())
        assert total > 0


class TestUnitFold:
    """r1 修复纯函数级测试：直接驱动 _fold_level（不走真实产物）。"""

    @staticmethod
    def _report():
        return {"per_class_level": {}, "diff_tagged": defaultdict(list),
                "variant_candidates": [], "conflicts": [], "kn246": [],
                "name_conflicts": []}

    def test_p1_2_kn246_registered_before_any_branch(self):
        """_dup 候选在标题污染/键命中/排除任何分支前登记 kn246：
        普通并入官方、键命中折叠、标题污染排除三种场景全部留痕。"""
        rep = self._report()
        derived = [
            {"cn": "甲术", "en": "Foo", "book": "CRB", "chunk_id": "c1",
             "_dup": True},   # 键命中并入官方组
            {"cn": "乙术", "en": "Baz", "book": "CRB", "chunk_id": "c2",
             "_dup": True},   # 普通新建派生组
            {"cn": "III", "en": "Bar", "book": "CRB", "chunk_id": "c3",
             "_dup": True},   # 标题污染：排除出折叠但仍须登记
            {"cn": "丙术", "en": "Qux", "book": "CRB", "chunk_id": "c4",
             "_dup": False},  # 非 _dup 不登记
        ]
        official = [{"cn": "甲术", "en": "Foo", "book": "CRB",
                     "chunk_id": None}]
        ex._fold_level("女巫", 1, official, derived, rep)
        ids = {it["chunk_id"] for it in rep["kn246"]}
        assert ids == {"c1", "c2", "c3"}, ids
        assert all(it["_dup"] is True for it in rep["kn246"])
        # 污染候选不进折叠对账（c1/c2/c4 三个参与）
        pl = rep["per_class_level"]["女巫|1"]
        assert pl["derived_candidates"] == 3, pl

    def test_p1_1_primary_without_any_key_fails_validation(self):
        """主条目既无有效中文键又无有效英文键（空串/占位值）必须被检出。"""
        rep = self._report()
        entries = ex._fold_level(
            "女巫", 1, [],
            [{"cn": "", "en": "n/a", "book": "CRB", "chunk_id": "c9",
              "_dup": False}], rep)
        errors = ex.find_primary_key_errors({"女巫": {"levels": {"1": entries}}})
        assert errors, "空键主条目必须产生校验错误"

    def test_p1_1_real_products_all_primary_have_keys(self, products):
        """r1-P1-1：真实产物写盘前每个主条目至少一个有效规范键。"""
        errors = ex.find_primary_key_errors(products["union"]["classes"])
        assert errors == []

    def test_p2_3_name_conflict_per_source_no_overwrite(self):
        """dedup_name_conflicts.matched 按来源列表记录，不以中文名做键：
        同表面名的多个来源不覆盖；A/B/C 传递链保留逐来源命中键与命中来源。"""
        rep = self._report()
        official = [{"cn": "甲术", "en": None, "book": "CRB",
                     "chunk_id": None}]
        derived = [
            {"cn": "甲术", "en": "E1", "book": "APG", "chunk_id": "cB",
             "_dup": False},  # 经 cn 命中 A
            {"cn": "丙术", "en": "E1", "book": "APG", "chunk_id": "cC",
             "_dup": False},  # 经 en 命中 B（传递入组）
            {"cn": "甲术", "en": "E9", "book": "UM", "chunk_id": "cD",
             "_dup": False},  # 与 A/B 同中文名，第三个来源不得覆盖前两个
        ]
        entries = ex._fold_level("女巫", 1, official, derived, rep)
        assert len(entries) == 1 and len(entries[0]["sources"]) == 4
        (conf,) = rep["name_conflicts"]
        matched = conf["matched"]
        assert isinstance(matched, list) and len(matched) == 4, matched
        by_chunk = {m["chunk_id"]: m for m in matched}
        assert set(by_chunk) == {None, "cB", "cC", "cD"}, by_chunk
        # 同表面名 甲术 三来源全部保留（不以中文名做键覆盖）
        assert [m["chunk_id"] for m in matched if m["cn"] == "甲术"] == \
            [None, "cB", "cD"]
        assert by_chunk[None]["role"] == "primary"
        assert by_chunk[None]["matched_by"] == "official_primary"
        assert by_chunk[None]["hit_keys"] == ["cn"]
        # cB 经 cn 连 A、经 en 连 cC（组内全部命中键如实记录）；
        # cC 仅经 en 传递入组；cD 仅经 cn 连 A——传递链逐来源保留
        assert set(by_chunk["cB"]["hit_keys"]) == {"cn", "en"}, by_chunk["cB"]
        assert by_chunk["cC"]["hit_keys"] == ["en"], by_chunk["cC"]
        assert by_chunk["cD"]["hit_keys"] == ["cn"], by_chunk["cD"]
        # 逐条命中关系：cC 只连到共享英文键的 cB（不冒充直连 A）
        c_refs = {(h["chunk_id"], tuple(h["keys"]))
                  for h in by_chunk["cC"]["hits"]}
        assert c_refs == {("cB", ("en",))}, c_refs
        b_refs = {(h["chunk_id"], tuple(h["keys"]))
                  for h in by_chunk["cB"]["hits"]}
        assert b_refs == {(None, ("cn",)), ("cC", ("en",)),
                          ("cD", ("cn",))}, b_refs
        for m in matched:
            for k in ("cn", "en", "chunk_id", "source", "role", "matched_by",
                      "norm_keys", "hit_keys", "hits"):
                assert k in m, (m, k)
            assert set(m["norm_keys"]) == {"cn", "en"}
            assert m["norm_keys"]["cn"] == (ex._norm_cn(m["cn"]) or None)
            for h in m["hits"]:
                assert set(h) == {"cn", "chunk_id", "source", "keys"}, h
                assert h["keys"] and set(h["keys"]) <= {"cn", "en"}, h

    @pytest.mark.parametrize("en", sorted(ex._EN_EMPTY_KEYS))
    def test_p1_1_all_en_placeholders_with_empty_cn_fail(self, en):
        """英文占位值全谱（含空串）与空中文键同时出现 → 主条目无有效键。"""
        rep = self._report()
        entries = ex._fold_level(
            "女巫", 1, [],
            [{"cn": "  ", "en": en, "book": "CRB", "chunk_id": "c9",
              "_dup": False}], rep)
        assert ex.find_primary_key_errors({"女巫": {"levels": {"1": entries}}})

    def test_p1_1_one_valid_key_suppresses_error(self):
        """任一键有效即合法：中文占位但英文有效、英文占位但中文有效。"""
        rep = self._report()
        entries = ex._fold_level(
            "女巫", 1, [],
            [{"cn": "", "en": "Fireball", "book": "CRB", "chunk_id": "c1",
              "_dup": False}], rep)
        assert ex.find_primary_key_errors({"女巫": {"levels": {"1": entries}}}) == []
        rep = self._report()
        entries = ex._fold_level(
            "女巫", 1, [],
            [{"cn": "火球术", "en": "n/a", "book": "CRB", "chunk_id": "c2",
              "_dup": False}], rep)
        assert ex.find_primary_key_errors({"女巫": {"levels": {"1": entries}}}) == []

    def test_p1_1_build_blocks_before_writing_products(self, tmp_path,
                                                      monkeypatch):
        """§10.1 构建失败边界：空主键条目使 main() 非零退出且不写产物。"""
        lists = {"classes": {"女巫": {
            "source_page": "p", "aliases": [],
            "levels": {"1": [{"cn": "", "en": "n/a", "book": "CRB",
                              "chunk_id": None}]}}}}
        (tmp_path / "lists.json").write_text(
            json.dumps(lists, ensure_ascii=False), encoding="utf-8")
        (tmp_path / "chunks.jsonl").write_text("", encoding="utf-8")
        monkeypatch.setattr(ex, "LISTS_JSON", tmp_path / "lists.json")
        monkeypatch.setattr(ex, "CHUNKS", tmp_path / "chunks.jsonl")
        monkeypatch.setattr(ex, "OUT_UNION", tmp_path / "union.json")
        monkeypatch.setattr(ex, "OUT_REPORT", tmp_path / "report.json")
        assert ex.main() == 1
        assert not (tmp_path / "union.json").exists()
        assert not (tmp_path / "report.json").exists()

    def test_p2_4_null_chunk_source_pair_deduped(self):
        """(chunk_id, source) 去重不得对 null 官方例外：同组两个
        chunk_id=null 的官方条目只写入一个来源。"""
        rep = self._report()
        official = [
            {"cn": "甲术", "en": "Ice", "book": "CRB", "chunk_id": None},
            {"cn": "乙术", "en": "Ice", "book": "UM", "chunk_id": None},
        ]
        entries = ex._fold_level("女巫", 1, official, [], rep)
        assert len(entries) == 1, entries
        assert len(entries[0]["sources"]) == 1, entries[0]["sources"]
        pairs = [(s["chunk_id"], s["source"]) for s in entries[0]["sources"]]
        assert len(pairs) == len(set(pairs))


class TestDerivedTraceback:
    def test_spot_check_20(self, products):
        """抽 20 条派生来源回源，chunk spell_level 确含职业+环级"""
        chunks = {json.loads(l)["chunk_id"]: json.loads(l)
                  for l in CHUNKS.read_text(encoding="utf-8").splitlines() if l.strip()}
        derived = []
        for cname, c in products["union"]["classes"].items():
            for lv, entries in c["levels"].items():
                for e in entries:
                    derived += [(cname, lv, s) for s in e["sources"]
                                if s["source"] == "derived"]
        random.seed(42)
        sample = random.sample(derived, 20)
        for cname, lv, s in sample:
            ch = chunks[s["chunk_id"]]
            sl = (ch.get("metadata") or {}).get("spell_level") or []
            assert any(it["class"] == cname and it["level"] == int(lv) for it in sl), \
                (cname, lv, s["chunk_id"])


class TestIdempotent:
    def test_rerun_byte_identical(self, products):
        b1 = UNION.read_bytes(), REPORT.read_bytes()
        r = _run_export()
        assert r.returncode == 0
        assert (UNION.read_bytes(), REPORT.read_bytes()) == b1


class TestSpellTocPath:
    """F-008：spell 条目 toc_path 按 chunk_id join 法术/chunks.jsonl 的 chm_toc_path。

    列表页 source_toc_path（职业 → … → 法术列表）保留原义，不冒充条目路径。
    """

    @pytest.fixture(scope="module")
    def spell_products(self):
        if not CHUNKS.exists():
            pytest.skip("chunks.jsonl 缺失（CI 裸 checkout）——产物断言由 build check 覆盖")
        r = subprocess.run([sys.executable, "spell_list_export.py"],
                           cwd=PHASE1, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        return {
            "lists": json.loads(SPELL_LISTS.read_text(encoding="utf-8")),
            "report": json.loads(SPELL_REPORT.read_text(encoding="utf-8")),
            "chunks": {json.loads(l)["chunk_id"]: json.loads(l)
                       for l in CHUNKS.read_text(encoding="utf-8").splitlines() if l.strip()},
        }

    @staticmethod
    def _entries(lists):
        for cls, body in lists["classes"].items():
            for lv, entries in body["levels"].items():
                for e in entries:
                    yield cls, lv, e

    def test_header_version_and_fingerprint(self, spell_products):
        lists = spell_products["lists"]
        assert lists["version"] == "1.1"
        digest = hashlib.sha256(CHUNKS.read_bytes()).hexdigest()
        assert lists["source_fingerprint"] == f"sha256:{digest}"

    def test_nonempty_count_ratchet(self, spell_products):
        """棘轮：KN250 后 10007/10068；剩余 61 条为既有 join_failed。"""
        assert spell_products["report"]["toc_path"]["nonempty"] == 10007

    def test_every_entry_joined_from_own_chunk(self, spell_products):
        chunks = spell_products["chunks"]
        for cls, lv, e in self._entries(spell_products["lists"]):
            assert "toc_path" in e, (cls, lv, e.get("chunk_id"))
            cid = e.get("chunk_id")
            want = (chunks[cid].get("chm_toc_path") or "") if cid in chunks else ""
            assert e["toc_path"] == want, (cls, lv, cid)

    def test_entry_paths_not_list_page_path(self, spell_products):
        """条目不把列表页 source_toc_path 当自身目录路径。"""
        lists = spell_products["lists"]
        for cls, body in lists["classes"].items():
            page_path = body["source_toc_path"]
            assert page_path.endswith("法术列表"), (cls, page_path)
            for lv, e in ((lv, e) for lv, es in body["levels"].items() for e in es):
                assert e["toc_path"] != page_path, (cls, lv, e.get("chunk_id"))
                assert "法术列表" not in e["toc_path"], (cls, lv, e["toc_path"])
        nonempty = [e for _, _, e in self._entries(lists) if e["toc_path"]]
        assert nonempty, "至少应有部分法术命中 chunk 目录路径（join 正例）"

    def test_report_counts_and_join_failed(self, spell_products):
        lists, report = spell_products["lists"], spell_products["report"]
        chunks = spell_products["chunks"]
        t = report["toc_path"]
        entries = [e for _, _, e in self._entries(lists)]
        # join 失败 = chunk_id 为空或不在法术 chunks 中（条目保留，路径空串）
        join_failed = sum(1 for e in entries
                          if not e.get("chunk_id") or e["chunk_id"] not in chunks)
        assert t["total"] == len(entries)
        assert t["nonempty"] == sum(1 for e in entries if e["toc_path"])
        assert t["empty"] == sum(1 for e in entries if not e["toc_path"])
        assert t["total"] == t["nonempty"] + t["empty"]
        assert t["join_failed"] == join_failed
        assert any(e["toc_path"] == "" for e in entries), "join 失败条目须保留空串"

    def test_apply_toc_paths_unit_contract(self):
        classes = {"甲": {"levels": {"1": [
            {"chunk_id": "c1"}, {"chunk_id": "c2"},
            {"chunk_id": None}, {"chunk_id": "missing"},
        ]}}}
        stats = sle.apply_toc_paths(classes, {"c1": "法术 → CRB", "c2": ""})
        paths = [e["toc_path"] for e in classes["甲"]["levels"]["1"]]
        assert paths == ["法术 → CRB", "", "", ""]
        assert stats == {"total": 4, "nonempty": 1, "empty": 3, "join_failed": 2}

    def test_rerun_byte_identical(self, spell_products):
        b1 = SPELL_LISTS.read_bytes(), SPELL_REPORT.read_bytes()
        r = subprocess.run([sys.executable, "spell_list_export.py"],
                           cwd=PHASE1, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        assert (SPELL_LISTS.read_bytes(), SPELL_REPORT.read_bytes()) == b1

