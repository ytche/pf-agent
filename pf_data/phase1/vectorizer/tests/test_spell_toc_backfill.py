import json
from pathlib import Path
from urllib.parse import unquote

import pytest

from vectorizer.postprocess.feat_chain import BackfillChmTocPath
from vectorizer.processors.spell import SpellProcessor

PHASE1 = Path(__file__).resolve().parents[2]
PF_DATA = PHASE1.parent
CHUNKS = PHASE1 / "vectorizer/output/法术/chunks.jsonl"


def test_spell_md_mapping_uses_decoded_chm_html_names():
    mapping = json.loads((PF_DATA / "md_mapping.json").read_text(encoding="utf-8"))
    toc_mapping = json.loads(
        (PF_DATA / "_archive/chm_scripts/toc_mapping.json").read_text(encoding="utf-8")
    )
    html_paths = {
        unquote(name): path
        for name, path in toc_mapping["html_to_path"].items()
    }
    spell_docs = sorted(
        name for name in mapping if name.startswith("Spell ") and name.endswith(".md")
    )

    assert len(spell_docs) == 17
    for doc in spell_docs:
        entry = mapping[doc]
        assert entry["toc_path"] == html_paths[entry["html_file"]], doc


def _write_unique_annotation_case(tmp_path, monkeypatch):
    phase1 = tmp_path / "phase1"
    organized = phase1 / "pf_rules_md_organized/法术"
    output = phase1 / "output"
    organized.mkdir(parents=True)
    output.mkdir()
    (phase1 / "../md_mapping.json").resolve().write_text(
        json.dumps({
            "page_747.md": {
                "html_file": "page_747.html",
                "toc_path": "未整理 → 初探龙国DEP → 法师学派",
                "book_source": None,
            }
        }),
        encoding="utf-8",
    )
    (organized / "初探龙国DEP_法术.md").write_text(
        "<!-- 初探龙国DEP-source:page_747.md:spells -->\n",
        encoding="utf-8",
    )
    (output / "chunks.jsonl").write_text(
        json.dumps({
            "chunk_id": "spell_初探龙国DEP_法术_0000",
            "doc_id": "初探龙国DEP_法术",
            "title": "虚空召唤",
            "chm_toc_path": "",
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(phase1)
    return output


def _read_single_chunk(output):
    return json.loads((output / "chunks.jsonl").read_text(encoding="utf-8"))


def test_spell_backfill_uses_consistent_annotation_source_as_file_toc(tmp_path, monkeypatch):
    output = _write_unique_annotation_case(tmp_path, monkeypatch)
    step_cls = next(
        (cls for cls in SpellProcessor.POSTPROCESSORS
         if cls.__name__ == "SpellBackfillChmTocPath"),
        None,
    )
    assert step_cls is not None, "SpellProcessor 未注册 SpellBackfillChmTocPath"

    stats = step_cls().run(output, tmp_path / "report")

    assert _read_single_chunk(output)["chm_toc_path"] == "未整理 → 初探龙国DEP → 法师学派"
    assert stats == {"filled": 1, "total_empty": 1, "unfilled": 0}


def test_generic_backfill_keeps_annotation_file_fallback_disabled(tmp_path, monkeypatch):
    output = _write_unique_annotation_case(tmp_path, monkeypatch)

    stats = BackfillChmTocPath().run(output, tmp_path / "report")

    assert _read_single_chunk(output)["chm_toc_path"] == ""
    assert stats == {"filled": 0, "total_empty": 1, "unfilled": 1}


def test_current_spell_chunks_have_complete_verified_toc_paths():
    if not CHUNKS.exists():
        pytest.skip("chunks.jsonl 缺失（CI 裸 checkout）——产物断言由 build check 覆盖")
    rows = [json.loads(line) for line in CHUNKS.read_text(encoding="utf-8").splitlines() if line]
    by_doc = {}
    for row in rows:
        by_doc.setdefault(row["doc_id"], []).append(row)

    assert [row["chunk_id"] for row in rows if not row.get("chm_toc_path")] == []
    assert all(
        row["chm_toc_path"] == "法术 → CRB-核心规则书"
        for row in by_doc["Spell CRB"]
    )
    assert all(
        row["chm_toc_path"] == "法术 → 玩家伴侣 → EMH-元素大师手册"
        for row in by_doc["元素大师手册EMH_法术"]
    )
    assert by_doc["初探龙国DEP_法术"][0]["chm_toc_path"] == "未整理 → 初探龙国DEP → 法师学派"


def test_spell_index_chunk_uses_md_mapping_toc_path():
    from vectorizer.sources.providers import SourceResolver, SpellIndexProvider

    processor = SpellProcessor(SourceResolver([]))
    processor.spell_index_provider = SpellIndexProvider()
    processor.spell_index_provider._index = {"acid arrow": "CRB"}

    chunk = processor._build_spell_index_chunk()

    assert chunk.chm_toc_path == "法术 → 出处速查"


def test_spell_backfill_rejects_file_toc_when_any_annotation_is_unresolved(tmp_path, monkeypatch):
    output = _write_unique_annotation_case(tmp_path, monkeypatch)
    source = tmp_path / "phase1/pf_rules_md_organized/法术/初探龙国DEP_法术.md"
    source.write_text(
        source.read_text(encoding="utf-8")
        + "<!-- 初探龙国DEP-source:missing.md:其他章节 -->\n",
        encoding="utf-8",
    )
    step_cls = next(
        cls for cls in SpellProcessor.POSTPROCESSORS
        if cls.__name__ == "SpellBackfillChmTocPath"
    )

    stats = step_cls().run(output, tmp_path / "report")

    assert _read_single_chunk(output)["chm_toc_path"] == ""
    assert stats == {"filled": 0, "total_empty": 1, "unfilled": 1}
