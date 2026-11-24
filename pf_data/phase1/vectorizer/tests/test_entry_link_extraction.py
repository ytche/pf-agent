"""test_entry_link_extraction.py — F-017 条目引用离线抽取器验收（TDD）

覆盖：
  - 「见 X」「详见《Y》」「参见」「见第 N 章」形态
  - 成语境误报（意见 / 听见 / 可见 / 由此可见）不抽取
  - 同名跨模块歧义保留全部候选，不任选
  - alias 精确命中（大小写归一）
  - 技能 / 背景特性模块归属
  - 重复出现 vs 唯一边计数
  - 未决候选不计入真引用
  - occurrence_id 稳定、同输入幂等、chunks 只读

脚本：vectorizer/exploration/entry_links/extract_entry_links.py
"""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "exploration" / "entry_links" / "extract_entry_links.py"
REVIEW_NAME = "entry_links_review.jsonl"
SUMMARY_NAME = "entry_links_summary.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("entry_links_extractor", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


extractor = _load_module()


def _chunk(chunk_id, title, text, *, category, component_type=None,
           aliases=None, book="CRB"):
    return {
        "chunk_id": chunk_id,
        "doc_id": "page_1",
        "category": category,
        "component_type": component_type or category,
        "title": title,
        "text": text,
        "aliases": aliases or [],
        "book_abbreviation": book,
        "book_name_cn": "核心规则手册",
        "book_name_en": "Core Rulebook",
        "chm_toc_path": "",
        "metadata": {},
    }


def _write_chunks(tmp_path, name, rows):
    path = tmp_path / name
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path


def _run(tmp_path, *chunk_paths, out_name="out"):
    out = tmp_path / out_name
    summary = extractor.extract_entry_links([str(p) for p in chunk_paths], str(out))
    rows = [
        json.loads(line)
        for line in (out / REVIEW_NAME).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return summary, rows, out


def _by_ref(rows, ref_text):
    return [row for row in rows if row["ref_text"] == ref_text]


# ===== 形态覆盖 =====

def test_plain_see_forms_extract_exact_target(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "领导力", "有关部属的规则见领导力。", category="feat"),
        _chunk("feat_002", "猛力攻击", "详见猛力攻击。", category="feat"),
        _chunk("feat_003", "顺势斩", "（参见顺势斩）", category="feat"),
    ])

    summary, rows, _ = _run(tmp_path, chunks)

    assert len(rows) == 3
    assert {row["ref_text"] for row in rows} == {"领导力", "猛力攻击", "顺势斩"}
    for row in rows:
        assert row["match_status"] == "exact"
        assert row["target_module"] == "feat"
        assert row["target_chunk_id"].startswith("feat_")
        assert row["verdict"] is None
        assert row["candidate"]["matched_on"] == "title"
        assert row["source_chunk_id"].startswith("feat_")
        assert row["ref_form"] in {"见", "详见", "参见"}
    assert summary["reference_occurrences"] == 3
    assert summary["unique_edges"] == 3


def test_book_title_form_uses_inner_title(tmp_path):
    chunks = _write_chunks(tmp_path, "rule.jsonl", [
        _chunk("rule_001", "怪物图鉴", "怪物图鉴条目。", category="rule",
               component_type="rule_section"),
        _chunk("rule_002", "部属", "具体规则详见《怪物图鉴》第 316 页。", category="rule",
               component_type="rule_section"),
    ])

    _, rows, _ = _run(tmp_path, chunks)

    book_rows = _by_ref(rows, "怪物图鉴")
    assert len(book_rows) == 1
    row = book_rows[0]
    assert row["ref_style"] == "book"
    assert row["ref_form"] == "详见"
    assert row["match_status"] == "exact"
    assert row["target_chunk_id"] == "rule_001"


def test_chapter_form_is_unresolved_candidate(tmp_path):
    chunks = _write_chunks(tmp_path, "rule.jsonl", [
        _chunk("rule_001", "战斗规则", "战斗规则见第 3 章。", category="rule",
               component_type="rule_section"),
    ])

    summary, rows, _ = _run(tmp_path, chunks)

    chapter = [row for row in rows if row["ref_style"] == "chapter"]
    assert len(chapter) == 1
    row = chapter[0]
    assert row["match_status"] == "unresolved"
    assert row["target_module"] is None
    assert row["target_chunk_id"] is None
    assert row["candidate"] is None
    assert summary["unresolved_occurrences"] == 1
    assert summary["unique_edges"] == 0


# ===== 误报 =====

def test_idiom_context_is_not_extracted(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk(
            "feat_001", "谈判专家",
            "他听见了对方的意见，可见此事并不简单，由此可见一斑。",
            category="feat",
        ),
    ])

    summary, rows, _ = _run(tmp_path, chunks)

    assert rows == []
    assert summary["reference_occurrences"] == 0


# ===== 歧义与别名 =====

def test_cross_module_ambiguity_keeps_all_candidates(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "领导力", "专长条目。", category="feat"),
        _chunk("feat_002", "引用者", "见领导力。", category="feat"),
    ])
    rule_chunks = _write_chunks(tmp_path, "rule.jsonl", [
        _chunk("rule_001", "领导力", "规则条目。", category="rule",
               component_type="rule_section"),
    ])

    summary, rows, _ = _run(tmp_path, chunks, rule_chunks)

    hits = _by_ref(rows, "领导力")
    assert len(hits) == 2
    assert {row["target_module"] for row in hits} == {"feat", "rule"}
    assert {row["match_status"] for row in hits} == {"ambiguous"}
    assert len({row["occurrence_id"] for row in hits}) == 1
    assert {row["candidate"]["chunk_id"] for row in hits} == {"feat_001", "rule_001"}
    assert all(row["candidate_count"] == 2 for row in hits)
    # 歧义边不得计入真引用
    assert summary["unique_edges"] == 0
    assert summary["ambiguous_occurrences"] == 1
    assert summary["ambiguous_candidate_rows"] == 2


def test_alias_exact_match_is_case_insensitive(tmp_path):
    chunks = _write_chunks(tmp_path, "spell.jsonl", [
        _chunk("spell_001", "酸液箭", "法术条目。", category="spell",
               aliases=["Acid Arrow"]),
        _chunk("spell_002", "法术书", "见 acid arrow。", category="spell"),
    ])

    summary, rows, _ = _run(tmp_path, chunks)

    alias_rows = _by_ref(rows, "acid arrow")
    assert len(alias_rows) == 1
    row = alias_rows[0]
    assert row["match_status"] == "exact"
    assert row["matched_on"] == "alias"
    assert row["target_chunk_id"] == "spell_001"
    assert summary["unique_edges"] == 1


# ===== 模块覆盖 =====

def test_skill_and_trait_modules(tmp_path):
    skill_chunks = _write_chunks(tmp_path, "skill.jsonl", [
        _chunk("skill_001", "特技", "技能条目。", category="skill",
               component_type="skill", aliases=["Acrobatics"]),
        _chunk("skill_002", "技能说明", "平衡检定见特技。", category="skill",
               component_type="skill_rule"),
    ])
    trait_chunks = _write_chunks(tmp_path, "trait.jsonl", [
        _chunk("trait_001", "铁胃", "背景特性条目。", category="trait",
               component_type="trait"),
        _chunk("trait_002", "拾荒者", "效果参见铁胃。", category="trait",
               component_type="trait"),
    ])

    _, rows, _ = _run(tmp_path, skill_chunks, trait_chunks)

    skill_hits = _by_ref(rows, "特技")
    trait_hits = _by_ref(rows, "铁胃")
    assert len(skill_hits) == 1 and skill_hits[0]["target_module"] == "skill"
    assert len(trait_hits) == 1 and trait_hits[0]["target_module"] == "trait"
    assert skill_hits[0]["match_status"] == "exact"
    assert trait_hits[0]["match_status"] == "exact"


# ===== 计数 =====

def test_repeated_occurrences_count_once_per_unique_edge(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "领导力", "专长条目。", category="feat"),
        _chunk("feat_002", "部属", "见领导力。另详见领导力。", category="feat"),
    ])

    summary, rows, _ = _run(tmp_path, chunks)

    hits = _by_ref(rows, "领导力")
    assert len(hits) == 2
    assert len({row["occurrence_id"] for row in hits}) == 2
    assert len({row["text_offset"] for row in hits}) == 2
    assert summary["reference_occurrences"] == 2
    assert summary["unique_edges"] == 1


def test_unresolved_candidates_are_not_edges(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "已知条目", "见未知条目。", category="feat"),
    ])

    summary, rows, _ = _run(tmp_path, chunks)

    assert len(rows) == 1
    row = rows[0]
    assert row["match_status"] == "unresolved"
    assert row["edge_key"] is None
    assert row["verdict"] is None
    assert summary["unresolved_occurrences"] == 1
    assert summary["unique_edges"] == 0


# ===== 稳定与幂等 =====

def test_occurrence_id_is_stable_sha256(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "领导力", "专长条目。", category="feat"),
        _chunk("feat_002", "部属", "见领导力。", category="feat"),
    ])

    _, rows, _ = _run(tmp_path, chunks)
    row = _by_ref(rows, "领导力")[0]
    payload = f"feat_002\x1f{row['text_offset']}\x1f领导力".encode("utf-8")
    assert row["occurrence_id"] == hashlib.sha256(payload).hexdigest()


def test_same_input_is_byte_idempotent(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "领导力", "专长条目。", category="feat"),
        _chunk("feat_002", "部属", "见领导力，详见领导力。", category="feat"),
    ])
    out = tmp_path / "out"

    extractor.extract_entry_links([str(chunks)], str(out))
    first_review = (out / REVIEW_NAME).read_bytes()
    first_summary = (out / SUMMARY_NAME).read_bytes()
    extractor.extract_entry_links([str(chunks)], str(out))
    second_review = (out / REVIEW_NAME).read_bytes()
    second_summary = (out / SUMMARY_NAME).read_bytes()

    assert first_review == second_review
    assert first_summary == second_summary


def test_chunks_are_read_only_and_duplicate_inputs_deduped(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "领导力", "专长条目。", category="feat"),
        _chunk("feat_002", "部属", "见领导力。", category="feat"),
    ])
    copy_path = tmp_path / "feat_copy.jsonl"
    copy_path.write_bytes(chunks.read_bytes())
    before = chunks.read_bytes()

    summary, rows, _ = _run(tmp_path, chunks, copy_path)

    assert chunks.read_bytes() == before
    assert len(rows) == 1
    assert summary["chunks_loaded"] == 2
    assert summary["duplicate_chunk_rows"] == 2


def test_cli_end_to_end(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "领导力", "专长条目。", category="feat"),
        _chunk("feat_002", "部属", "见领导力。", category="feat"),
    ])
    out = tmp_path / "cli_out"

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--chunks", str(chunks), "--output-dir", str(out)],
        capture_output=True,
        text=True,
        cwd=str(SCRIPT.parent.parent.parent),
    )

    assert result.returncode == 0, result.stderr
    assert (out / REVIEW_NAME).exists()
    assert (out / SUMMARY_NAME).exists()
    summary = json.loads((out / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["reference_occurrences"] == 1


# ===== P0 复核新增 =====

def test_race_target_uses_intro_not_overview(tmp_path):
    chunks = _write_chunks(tmp_path, "race.jsonl", [
        _chunk("race_intro_001", "矮人", "种族介绍。", category="race",
               component_type="race_intro"),
        _chunk("race_overview_001", "矮人", "种族总览。", category="race",
               component_type="race_overview"),
        _chunk("race_trait_001", "坚韧", "该特性见矮人。", category="race",
               component_type="race_trait", aliases=["Sturdy"]),
    ])

    summary, rows, _ = _run(tmp_path, chunks)

    hits = _by_ref(rows, "矮人")
    assert len(hits) == 1
    row = hits[0]
    assert row["match_status"] == "exact"
    assert row["candidate_count"] == 1
    assert row["target_chunk_id"] == "race_intro_001"
    assert summary["catalog_targets_by_component_type"]["race"]["race_intro"] == 1
    assert "race_overview" not in summary["catalog_targets_by_component_type"]["race"]
    assert summary["excluded_targets_by_component_type"]["race"]["race_overview"] == 1


def test_catalog_whitelist_excludes_intro_components(tmp_path):
    chunks = _write_chunks(tmp_path, "all.jsonl", [
        _chunk("class_001", "战士", "职业。", category="职业",
               component_type="class_feature"),
        _chunk("class_002", "职业特性", "总览。", category="职业",
               component_type="class_overview"),
        _chunk("equip_001", "长剑", "装备。", category="equipment",
               component_type="weapon"),
        _chunk("equip_002", "装备介绍", "介绍。", category="equipment",
               component_type="equipment_intro"),
        _chunk("rule_001", "战斗", "规则。", category="rule",
               component_type="rule_section"),
        _chunk("rule_002", "规则介绍", "介绍。", category="rule",
               component_type="rule_intro"),
        _chunk("skill_001", "特技", "技能。", category="skill",
               component_type="skill_rule"),
        _chunk("trait_001", "铁胃", "背景特性。", category="trait",
               component_type="trait"),
        _chunk("feat_001", "领导力", "专长。", category="feat"),
        _chunk("spell_001", "火球术", "法术。", category="spell"),
    ])

    summary, _, _ = _run(tmp_path, chunks)

    included = summary["catalog_targets_by_component_type"]
    excluded = summary["excluded_targets_by_component_type"]
    assert included["class"]["class_overview"] == 1
    assert included["equipment"]["weapon"] == 1
    assert included["rule"]["rule_section"] == 1
    assert "equipment_intro" not in included["equipment"]
    assert excluded["equipment"]["equipment_intro"] == 1
    assert "rule_intro" not in included["rule"]
    assert excluded["rule"]["rule_intro"] == 1
    assert summary["catalog_targets"] >= 8


def test_bracket_and_quote_forms(tmp_path):
    chunks = _write_chunks(tmp_path, "catalog.jsonl", [
        _chunk("spell_001", "火球术", "法术。", category="spell"),
        _chunk("feat_001", "领导力", "专长。", category="feat"),
        _chunk("feat_002", "猛力攻击", "专长。", category="feat"),
        _chunk("spell_002", "解除魔法", "法术。", category="spell"),
        _chunk("spell_003", "治疗术", "法术。", category="spell"),
        _chunk("rule_001", "战斗规则", "规则。", category="rule",
               component_type="rule_section"),
        _chunk("rule_002", "怪物图鉴", "规则。", category="rule",
               component_type="rule_section"),
        _chunk("src_001", "引用来源", (
            "见【火球术】，见「领导力」，见（猛力攻击），见\"解除魔法\"，"
            "见'治疗术'，见效果“火球术”，见条目《领导力》，"
            "详见《怪物图鉴》，见本书第 3 章。"
        ), category="rule", component_type="rule_section"),
    ])

    _, rows, _ = _run(tmp_path, chunks)

    hits = [row for row in rows if row["source_chunk_id"] == "src_001"]
    assert {row["ref_text"] for row in hits} >= {
        "火球术", "领导力", "猛力攻击", "解除魔法", "治疗术", "怪物图鉴",
    }
    styles = {row["ref_style"] for row in hits}
    assert {"corner", "quoted", "paren", "ascii_quoted", "book", "chapter"} <= styles
    effect_row = [row for row in hits if row["ref_label"] == "效果"][0]
    assert effect_row["ref_text"] == "火球术"
    assert effect_row["match_status"] == "exact"
    assert effect_row["target_chunk_id"] == "spell_001"
    chapter_row = [row for row in hits if row["ref_style"] == "chapter"][0]
    assert chapter_row["match_status"] == "unresolved"


def test_uncovered_anchor_is_recorded(tmp_path):
    chunks = _write_chunks(tmp_path, "rule.jsonl", [
        _chunk("rule_001", "规则", "规则详见。另见：", category="rule",
               component_type="rule_section"),
    ])

    summary, rows, _ = _run(tmp_path, chunks)

    uncovered = [row for row in rows if row["ref_style"] == "uncovered"]
    assert len(uncovered) == 2
    for row in uncovered:
        assert row["match_status"] == "unresolved"
        assert row["candidate_count"] == 0
        assert row["candidate"] is None
    assert summary["uncovered_occurrences"] == 2


def test_idiom_suppression_and_exact_hit_precedence(tmp_path):
    chunks = _write_chunks(tmp_path, "mixed.jsonl", [
        _chunk("spell_001", "解除魔法", "法术。", category="spell"),
        _chunk("spell_002", "火球术", "法术。", category="spell"),
        _chunk("feat_001", "闲谈", (
            "他听见了声音，意见很大，由此可见一斑。"
            "见解除魔法。见效果‘火球术’。"
        ), category="feat"),
    ])

    summary, rows, _ = _run(tmp_path, chunks)

    hits = _by_ref(rows, "解除魔法") + _by_ref(rows, "火球术")
    assert len(hits) == 2
    assert all(row["match_status"] == "exact" for row in hits)
    assert _by_ref(rows, "火球术")[0]["ref_label"] == "效果"
    assert summary["suppressed_count"] == 3
    assert {sample["suppressed_word"] for sample in summary["suppressed_samples"]} == {
        "听见", "意见", "可见一斑",
    }


def test_rerun_restores_human_verdict(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "领导力", "专长条目。", category="feat"),
        _chunk("feat_002", "部属", "见领导力。", category="feat"),
    ])
    out = tmp_path / "out"
    extractor.extract_entry_links([str(chunks)], str(out))
    review_path = out / REVIEW_NAME
    rows = [json.loads(line) for line in review_path.read_text(encoding="utf-8").splitlines()]
    rows[0].update({
        "verdict": "正确",
        "reviewer": "alice",
        "note": "确认",
        "reviewed_at": "2026-11-13T10:00:00+08:00",
        "chosen_target_chunk_id": "feat_001",
    })
    review_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    extractor.extract_entry_links([str(chunks)], str(out))

    merged = [json.loads(line) for line in review_path.read_text(encoding="utf-8").splitlines()]
    assert merged[0]["verdict"] == "正确"
    assert merged[0]["reviewer"] == "alice"
    assert merged[0]["note"] == "确认"
    assert merged[0]["reviewed_at"] == "2026-11-13T10:00:00+08:00"
    assert merged[0]["chosen_target_chunk_id"] == "feat_001"
    diff = json.loads((out / "entry_links_review_diff.json").read_text(encoding="utf-8"))
    assert diff["restored_rows"] == 1
    assert diff["added_rows"] == []
    assert diff["missing_rows"] == []


def test_rerun_reports_missing_and_added_rows(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "领导力", "专长条目。", category="feat"),
        _chunk("feat_002", "部属", "见领导力。", category="feat"),
    ])
    out = tmp_path / "out"
    extractor.extract_entry_links([str(chunks)], str(out))

    chunks.write_text(
        "\n".join([
            json.dumps(_chunk("feat_001", "领导力", "专长条目。", category="feat"),
                       ensure_ascii=False),
            json.dumps(_chunk("feat_002", "部属", "暂无引用。", category="feat"),
                       ensure_ascii=False),
        ]) + "\n",
        encoding="utf-8",
    )
    extractor.extract_entry_links([str(chunks)], str(out))
    diff = json.loads((out / "entry_links_review_diff.json").read_text(encoding="utf-8"))
    assert len(diff["missing_rows"]) == 1
    assert len(diff["added_rows"]) == 0

    chunks.write_text(
        "\n".join([
            json.dumps(_chunk("feat_001", "领导力", "专长条目。", category="feat"),
                       ensure_ascii=False),
            json.dumps(_chunk("feat_002", "部属", "详见领导力。", category="feat"),
                       ensure_ascii=False),
        ]) + "\n",
        encoding="utf-8",
    )
    extractor.extract_entry_links([str(chunks)], str(out))
    diff = json.loads((out / "entry_links_review_diff.json").read_text(encoding="utf-8"))
    assert len(diff["added_rows"]) == 1


def test_conflicting_prior_review_exits_nonzero(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "领导力", "专长条目。", category="feat"),
        _chunk("feat_002", "部属", "见领导力。", category="feat"),
    ])
    out = tmp_path / "out"
    extractor.extract_entry_links([str(chunks)], str(out))
    review_path = out / REVIEW_NAME
    row = json.loads(review_path.read_text(encoding="utf-8").splitlines()[0])
    conflicting_a = dict(row, verdict="正确")
    conflicting_b = dict(row, verdict="非引用误报")
    review_path.write_text(
        json.dumps(conflicting_a, ensure_ascii=False) + "\n" +
        json.dumps(conflicting_b, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    before = review_path.read_bytes()

    with pytest.raises(extractor.ReviewConflictError):
        extractor.extract_entry_links([str(chunks)], str(out))
    assert review_path.read_bytes() == before

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--chunks", str(chunks), "--out", str(out)],
        capture_output=True,
        text=True,
        cwd=str(SCRIPT.parent.parent.parent),
    )
    assert result.returncode == 2
    assert "冲突" in result.stderr


def test_review_row_fields_and_unresolved_candidate_count(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "领导力", "专长条目。", category="feat"),
        _chunk("feat_002", "部属", "见领导力。见未知条目。", category="feat"),
    ])

    _, rows, _ = _run(tmp_path, chunks)

    exact = _by_ref(rows, "领导力")[0]
    assert len(exact["candidate_id"]) == 64
    assert exact["target_book_abbreviation"] == "CRB"
    assert exact["target_component_type"] == "feat"
    assert exact["chosen_target_chunk_id"] is None
    assert exact["correct_target_chunk_id"] is None
    assert exact["reviewed_at"] is None
    unresolved = _by_ref(rows, "未知条目")[0]
    assert unresolved["candidate_count"] == 0
    assert unresolved["candidate_id"] and unresolved["candidate_id"] != exact["candidate_id"]


def test_from_review_summary_matches_detail(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "领导力", "专长条目。", category="feat"),
        _chunk("feat_002", "部属", "见领导力。见未知条目。", category="feat"),
    ])
    out = tmp_path / "out"
    extractor.extract_entry_links([str(chunks)], str(out))
    review_path = out / REVIEW_NAME
    rows = [json.loads(line) for line in review_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["verdict"] = "正确"
    rows[1]["verdict"] = "非引用误报"
    review_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    summary = extractor.summarize_review(str(review_path), str(tmp_path / "from_review"))

    assert summary["mode"] == "from-review"
    assert summary["reference_occurrences"] == 2
    assert summary["unique_edges"] == 1
    assert summary["affected_source_chunks"] == 1
    assert summary["verdict_counts"] == {"正确": 1, "非引用误报": 1}
    assert summary["verdict_counts_by_module"]["feat"] == {"正确": 1, "非引用误报": 1}
    assert summary["occurrences_by_book"] == {"CRB": 2}
    assert "plain" in summary["form_samples"]
    assert summary["pending_verdict_rows"] == 0


def test_cli_task15_glob_and_out_alias(tmp_path):
    (tmp_path / "种族").mkdir()
    (tmp_path / "专长").mkdir()
    _write_chunks(tmp_path / "种族", "chunks.jsonl", [
        _chunk("race_intro_001", "矮人", "种族介绍。", category="race",
               component_type="race_intro"),
        _chunk("race_trait_001", "坚韧", "见矮人。", category="race",
               component_type="race_trait"),
    ])
    _write_chunks(tmp_path / "专长", "chunks.jsonl", [
        _chunk("feat_001", "领导力", "专长。", category="feat"),
        _chunk("feat_002", "部属", "详见领导力。", category="feat"),
    ])
    out = tmp_path / "f017"
    markdown = tmp_path / "F017_汇总.md"

    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--chunks", str(tmp_path / "*" / "chunks.jsonl"),
            "--out", str(out),
            "--markdown", str(markdown),
        ],
        capture_output=True,
        text=True,
        cwd=str(SCRIPT.parent.parent.parent),
    )

    assert result.returncode == 0, result.stderr
    assert (out / REVIEW_NAME).exists()
    assert (out / SUMMARY_NAME).exists()
    summary = json.loads((out / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["reference_occurrences"] == 2
    assert summary["unique_edges"] == 2
    assert markdown.exists()
    assert "F-017" in markdown.read_text(encoding="utf-8")


def test_input_guardrails(tmp_path):
    single = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "领导力", "专长。", category="feat"),
    ])
    with pytest.raises(extractor.InputValidationError):
        extractor.extract_entry_links([str(single)], str(tmp_path / "strict"), strict=True)
    summary = extractor.extract_entry_links([str(single)], str(tmp_path / "lenient"))
    assert set(summary["missing_modules"]) == {
        "race", "class", "spell", "equipment", "rule", "skill", "trait",
    }
    strict_cli = subprocess.run(
        [sys.executable, str(SCRIPT), "--chunks", str(single),
         "--out", str(tmp_path / "strict_cli"), "--strict"],
        capture_output=True, text=True, cwd=str(SCRIPT.parent.parent.parent),
    )
    assert strict_cli.returncode == 2

    unknown = _write_chunks(tmp_path, "unknown.jsonl", [
        _chunk("x_001", "未知", "见未知。", category="mystery",
               component_type="feat"),
    ])
    summary = extractor.extract_entry_links([str(unknown)], str(tmp_path / "unknown_out"))
    assert summary["unknown_category_chunks"] == 1
    with pytest.raises(extractor.InputValidationError):
        extractor.extract_entry_links([str(unknown)], str(tmp_path / "unknown_strict"),
                                      strict=True)

    conflict_a = _write_chunks(tmp_path, "a.jsonl", [
        _chunk("dup_001", "甲", "文本一", category="feat"),
    ])
    conflict_b = _write_chunks(tmp_path, "b.jsonl", [
        _chunk("dup_001", "甲", "文本二", category="feat"),
    ])
    with pytest.raises(extractor.InputValidationError):
        extractor.extract_entry_links([str(conflict_a), str(conflict_b)],
                                      str(tmp_path / "dup_out"))


def test_all_eight_modules_are_targetable(tmp_path):
    specs = [
        ("race", "race_intro"),
        ("职业", "class_feature"),
        ("feat", "feat"),
        ("spell", "spell"),
        ("equipment", "gear"),
        ("rule", "rule_section"),
        ("skill", "skill_rule"),
        ("trait", "trait"),
    ]
    rows = []
    for index, (category, component_type) in enumerate(specs):
        rows.append(_chunk(
            f"target_{index}", f"目标{index}", "目标条目。",
            category=category, component_type=component_type,
        ))
        rows.append(_chunk(
            f"source_{index}", f"来源{index}", f"见目标{index}。",
            category=category, component_type=component_type,
        ))
    chunks = _write_chunks(tmp_path, "all.jsonl", rows)

    summary, out_rows, _ = _run(tmp_path, chunks)

    targets = {
        row["target_module"] for row in out_rows
        if row["ref_text"].startswith("目标") and row["match_status"] == "exact"
    }
    assert targets == {
        "race", "class", "feat", "spell", "equipment", "rule", "skill", "trait",
    }
    assert summary["unique_edges"] == 8


def test_cli_from_review_recomputes_summary(tmp_path):
    chunks = _write_chunks(tmp_path, "feat.jsonl", [
        _chunk("feat_001", "领导力", "专长条目。", category="feat"),
        _chunk("feat_002", "部属", "见领导力。", category="feat"),
    ])
    out = tmp_path / "out"
    extractor.extract_entry_links([str(chunks)], str(out))
    review_path = out / REVIEW_NAME
    rows = [json.loads(line) for line in review_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["verdict"] = "正确"
    review_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    recomputed = tmp_path / "recomputed"
    markdown = tmp_path / "F017_review.md"

    result = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--from-review", str(review_path),
            "--out", str(recomputed),
            "--markdown", str(markdown),
        ],
        capture_output=True,
        text=True,
        cwd=str(SCRIPT.parent.parent.parent),
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads((recomputed / SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["mode"] == "from-review"
    assert summary["verdict_counts"] == {"正确": 1}
    assert summary["unique_edges"] == 1
    assert markdown.exists()


def test_uncovered_form_field(tmp_path):
    chunks = _write_chunks(tmp_path, "rule.jsonl", [
        _chunk("rule_001", "规则", "规则详见。", category="rule",
               component_type="rule_section"),
    ])

    _, rows, _ = _run(tmp_path, chunks)

    assert rows[0]["uncovered_form"] is True
    assert rows[0]["candidate_count"] == 0
