# -*- coding: utf-8 -*-
"""KN108 Task 1/2：职业根目录七页显式清单、逻辑路径接入与 rule_version 标注。"""
import dataclasses
from pathlib import Path

import pytest

from vectorizer.formats.profession import INPUT_DIR
from vectorizer.processors.profession import (
    ROOT_PAGE_MANIFEST,
    Chunk,
    ProfessionProcessor,
    RootPageSpec,
    _profession_file_condition,
    _profession_rel_path,
    _resolve_rule_version,
    _root_page_spec_for_doc,
    _root_page_spec_for_path,
)

ORGANIZED_ROOT = INPUT_DIR.parent

EXPECTED_ROOT_RELS = {
    "page_30.md": "职业概述/page_30.md",
    "page_53.md": "核心职业/武僧/武僧清规/page_53.md",
    "page_128.md": "进阶职业/page_128.md",
    "page_134.md": "进阶职业/CRB进阶职业/龙脉术士/page_134.md",
    "page_244.md": "掉链子（Unchained）/page_244.md",
    "page_411.md": "基础职业/召唤师/幻灵/page_411.md",
    "page_609.md": "神话冒险/page_609.md",
}


def test_root_page_manifest_covers_seven_pages():
    assert set(ROOT_PAGE_MANIFEST) == set(EXPECTED_ROOT_RELS)
    for name, spec in ROOT_PAGE_MANIFEST.items():
        assert isinstance(spec, RootPageSpec)
        assert spec.logical_rel == EXPECTED_ROOT_RELS[name]


@pytest.mark.parametrize("name,logical", sorted(EXPECTED_ROOT_RELS.items()))
def test_profession_rel_path_maps_root_pages(name, logical):
    abs_path = ORGANIZED_ROOT / name
    assert abs_path.exists()
    assert _profession_rel_path(abs_path).as_posix() == logical


@pytest.mark.parametrize("name", sorted(EXPECTED_ROOT_RELS))
def test_profession_file_condition_accepts_root_pages(name):
    assert _profession_file_condition(ORGANIZED_ROOT / name) is True


def test_existing_subdir_file_rel_path_unchanged():
    abs_path = INPUT_DIR / "核心职业" / "圣骑士" / "page_55.md"
    assert _profession_rel_path(abs_path).as_posix() == "核心职业/圣骑士/page_55.md"
    assert _profession_file_condition(abs_path) is True


def test_non_manifest_root_page_not_matched():
    # 根目录下其他 page 不属于职业清单
    assert _root_page_spec_for_path(ORGANIZED_ROOT / "page_31.md") is None
    assert _profession_file_condition(ORGANIZED_ROOT / "page_31.md") is False
    # 其他模块文件不匹配职业条件
    other = ORGANIZED_ROOT / "技能"
    if other.is_dir():
        sample = next(other.rglob("*.md"), None)
        if sample is not None:
            assert _profession_file_condition(sample) is False


def test_deeper_same_name_path_does_not_match_root_spec():
    # 更深路径下同名文件不应命中根层清单
    assert _root_page_spec_for_path(INPUT_DIR / "核心职业" / "page_30.md") is None


def test_real_root_pages_pass_verify(proc):
    # RED 固化：7 页真实 StandardChunk 必须整体通过既有锚点闸口（不得放宽断言）
    from vectorizer.verify import verify_profession as vp
    chunks = []
    for name in sorted(EXPECTED_ROOT_RELS):
        chunks.extend(dataclasses.asdict(c) for c in proc.process(ORGANIZED_ROOT / name))
    ok, issues = vp.check_kn108_root_pages(chunks, {})
    assert ok, issues


# ---- 集成：真实页面 process() ----

@pytest.fixture(scope="module")
def proc():
    p = ProfessionProcessor(None)
    p.load_resources(INPUT_DIR)
    return p


@pytest.mark.parametrize("name", sorted(EXPECTED_ROOT_RELS))
def test_root_pages_process(proc, name):
    chunks = proc.process(ORGANIZED_ROOT / name)
    assert chunks, f"{name} 无产物"
    logical = EXPECTED_ROOT_RELS[name]
    for c in chunks:
        assert c.doc_id == logical
        assert c.metadata["source_paths"] == [logical]


def test_page411_summoner_anchors(proc):
    chunks = proc.process(ORGANIZED_ROOT / "page_411.md")
    text = "\n".join(c.text for c in chunks)
    for anchor in ("幻灵", "生命骰", "基本攻击加值", "技能", "专长"):
        assert anchor in text, f"page_411 产物缺失锚点：{anchor}"


# ---- Task 2：rule_version 优先级与空值 ----

def test_resolve_rule_version_priority():
    # 清单覆盖优先（page_244 即使 book=PFS 也标 unchained）
    assert _resolve_rule_version("掉链子（Unchained）/page_244.md", "PFS") == "unchained"
    # Unchained 逻辑 doc_id 前缀
    assert _resolve_rule_version("掉链子（Unchained）/盗贼/page_x.md", "PU") == "unchained"
    # book 小写兜底
    assert _resolve_rule_version("核心职业/武僧/page_53.md", "CRB") == "crb"
    # 空 / ? 来源不写 rule_version
    assert _resolve_rule_version("核心职业/武僧/page_53.md", "") is None
    assert _resolve_rule_version("核心职业/武僧/page_53.md", "?") is None


def test_root_page_spec_for_doc_full_path_lookup():
    # 按完整逻辑 doc_id 查清单；同名但更深/其他目录不得误命中
    assert _root_page_spec_for_doc("掉链子（Unchained）/page_244.md") is ROOT_PAGE_MANIFEST["page_244.md"]
    assert _root_page_spec_for_doc("核心职业/武僧/page_244.md") is None
    assert _root_page_spec_for_doc("进阶职业/page_128.md") is ROOT_PAGE_MANIFEST["page_128.md"]


# ---- Task 2：page_244 真实产物 ----

def test_page_244_pfs_unchained_overview(proc):
    chunks = proc.process(ORGANIZED_ROOT / "page_244.md")
    assert chunks, "page_244 无产物"
    for c in chunks:
        assert c.doc_id == "掉链子（Unchained）/page_244.md"
        assert c.component_type == "class_overview"
        assert c.metadata["class_name"] == ""
        assert c.book_abbreviation == "PFS"
        assert c.book_name_cn == "探索者协会"
        assert c.book_name_en == "Pathfinder Society"
        assert c.metadata["rule_version"] == "unchained"
        assert "pfs_eligible" not in c.metadata


def test_real_unchained_dir_page_rule_version(proc):
    chunks = proc.process(INPUT_DIR / "掉链子（Unchained）" / "武僧" / "page_250.md")
    assert chunks, "Unchained 武僧 page_250 无产物"
    for c in chunks:
        assert c.metadata["rule_version"] == "unchained"


def test_real_crb_page_rule_version(proc):
    chunks = proc.process(INPUT_DIR / "核心职业" / "武僧" / "page_55.md")
    assert chunks, "CRB 武僧 page_55 无产物"
    # 普通页按各自解析出的来源书小写标注（页内含 APG 来源能力则标 apg）
    for c in chunks:
        assert c.metadata["rule_version"] == c.book_abbreviation.lower()


def test_unknown_source_chunk_has_no_rule_version(proc):
    chunks = proc.process(INPUT_DIR / "核心职业" / "武僧" / "page_55.md")
    assert chunks
    std = chunks[0]
    raw = Chunk(
        chunk_id=std.chunk_id,
        doc_id=std.doc_id,
        source_paths=list(std.metadata["source_paths"]),
        category=std.category,
        component_type=std.component_type,
        class_name=std.metadata["class_name"],
        archetype_name=std.metadata["archetype_name"],
        book_source=std.book_name_cn,
        book_source_english=std.book_name_en,
        book_abbreviation=std.book_abbreviation,
        chm_toc_path=std.chm_toc_path,
        title=std.title,
        heading_breadcrumbs=list(std.metadata["heading_breadcrumbs"]),
        source_markers=list(std.metadata["source_markers"]),
        terms=list(std.metadata["terms"]),
        aliases=list(std.aliases),
        feature_subtype=std.metadata["feature_subtype"],
        is_deprecated=std.metadata["is_deprecated"],
        char_count=std.metadata["char_count"],
        text=std.text,
        source_confidence=std.source_confidence,
    )
    unknown = dataclasses.replace(raw, book_abbreviation="?")
    result = proc._to_standard(unknown)
    assert "rule_version" not in result.metadata
