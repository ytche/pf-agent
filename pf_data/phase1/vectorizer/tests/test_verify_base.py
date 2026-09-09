"""
test_verify_base.py — verify 公共框架测试（v2.2 决策 E）

覆盖（不依赖产物，unit 级）：
  - load_chunks：正常加载 / 文件缺失退出
  - VerifyBase 模板方法：checks 顺序执行、ctx 传递、exit code 汇总、通过文案打印
  - GENERIC_CHECKS 六条（原 audit.py Tier 1）：对构造数据的判定
"""

import json

import pytest

from vectorizer.verify.base import GENERIC_CHECKS, VerifyBase, load_chunks, make_row_recall_check


def _write_chunks(tmp_path, chunks):
    p = tmp_path / "chunks.jsonl"
    p.write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks) + "\n",
        encoding="utf-8",
    )
    return p


# ---- load_chunks ----


def test_load_chunks_ok(tmp_path):
    p = _write_chunks(tmp_path, [{"chunk_id": "c1"}, {"chunk_id": "c2"}])
    chunks = load_chunks(p)
    assert [c["chunk_id"] for c in chunks] == ["c1", "c2"]


def test_load_chunks_missing(tmp_path, capsys):
    with pytest.raises(SystemExit):
        load_chunks(tmp_path / "nope.jsonl")
    assert "chunks 文件不存在" in capsys.readouterr().out


# ---- VerifyBase 模板方法 ----


def _ok_check(chunks, ctx):
    assert ctx["marker"] == "m1"  # ctx 必须经 prepare 注入
    print("  — ok check ran")
    return True, []


def _warn_check(chunks, ctx):
    return True, ["⚠️  WARN 不算失败"]


def _fail_check(chunks, ctx):
    return False, ["❌ 故意失败"]


class _DemoVerify(VerifyBase):
    name = "demo"
    description = "demo"
    DEFAULT_CHUNKS = None

    checks = [
        ("OK 检查", _ok_check, "OK 通过"),
        ("WARN 检查", _warn_check, "WARN 通过（不该打印）"),
        ("FAIL 检查", _fail_check, "FAIL 通过（不该打印）"),
    ]

    def add_args(self, parser):
        parser.add_argument("--marker", default="m1")

    def prepare(self, args):
        self.ctx["marker"] = args.marker


def test_verify_base_fail_exit(tmp_path, capsys):
    p = _write_chunks(tmp_path, [{"chunk_id": "c1"}])
    with pytest.raises(SystemExit) as e:
        _DemoVerify().main(["--chunks", str(p)])
    assert e.value.code == 1
    out = capsys.readouterr().out
    # 检查顺序与序号
    assert "加载 1 chunks" in out
    assert "【1/3】OK 检查" in out and "【2/3】WARN 检查" in out and "【3/3】FAIL 检查" in out
    # 通过文案仅在 issues 为空时打印
    assert "✅ OK 通过" in out
    assert "WARN 通过" not in out and "FAIL 通过" not in out
    # WARN 打印但计入失败集合
    assert "⚠️  WARN 不算失败" in out and "❌ 故意失败" in out
    assert "❌ 验收未完全通过" in out


def test_verify_base_pass_exit(tmp_path, capsys):
    p = _write_chunks(tmp_path, [{"chunk_id": "c1"}])

    class _PassOnly(VerifyBase):
        DEFAULT_CHUNKS = None
        checks = [("OK 检查", _ok_check, "OK 通过")]

        def prepare(self, args):
            self.ctx["marker"] = "m1"

    with pytest.raises(SystemExit) as e:
        _PassOnly().main(["--chunks", str(p)])
    assert e.value.code == 0
    assert "✅ 全部验收通过" in capsys.readouterr().out


def test_verify_base_default_chunks(tmp_path):
    """DEFAULT_CHUNKS 作为 --chunks 默认值"""
    p = _write_chunks(tmp_path, [{"chunk_id": "c1"}])

    class _DefaultChunks(VerifyBase):
        DEFAULT_CHUNKS = p
        checks = []

    with pytest.raises(SystemExit) as e:
        _DefaultChunks().main([])
    assert e.value.code == 0


# ---- GENERIC_CHECKS（原 audit.py Tier 1 六条）----


def _check_by_name(name):
    for n, fn, pass_msg in GENERIC_CHECKS:
        if n == name:
            return fn
    raise AssertionError(f"GENERIC_CHECKS 缺 {name}")


def test_generic_url_in_title():
    fn = _check_by_name("url_in_title")
    ok, issues = fn([{"chunk_id": "c1", "title": "https://x"}], {})
    assert not ok and len(issues) == 1
    ok, issues = fn([{"chunk_id": "c1", "title": "正常"}], {})
    assert ok and not issues


def test_generic_unknown_placeholder():
    fn = _check_by_name("unknown_placeholder")
    ok, _ = fn([{"chunk_id": "c1", "title": "x【?】"}], {})
    assert not ok
    ok, _ = fn([{"chunk_id": "c1", "text": "正文【?】"}], {})
    assert not ok
    ok, _ = fn([{"chunk_id": "c1", "title": "正常", "text": "正常"}], {})
    assert ok


def test_generic_bold_mismatch():
    fn = _check_by_name("bold_mismatch")
    ok, _ = fn([{"chunk_id": "c1", "text": "**未闭合"}], {})
    assert not ok
    ok, _ = fn([{"chunk_id": "c1", "text": "**成对**"}], {})
    assert ok


def test_generic_unknown_source_book():
    fn = _check_by_name("unknown_source_book")
    for bad in ("?", "", None):
        ok, _ = fn([{"chunk_id": "c1", "book_abbreviation": bad}], {})
        assert not ok
    ok, _ = fn([{"chunk_id": "c1", "book_abbreviation": "CRB"}], {})
    assert ok


def test_generic_missing_category_id():
    fn = _check_by_name("missing_category_id")
    # 无 class_name 且无 metadata.school → 违规
    ok, _ = fn([{"chunk_id": "c1", "title": "t"}], {})
    assert not ok
    # 有 class_name 或 school → 通过
    ok, _ = fn([{"chunk_id": "c1", "class_name": "法师"}], {})
    assert ok
    ok, _ = fn([{"chunk_id": "c1", "metadata": {"school": "防护"}}], {})
    assert ok


def test_generic_empty_text():
    fn = _check_by_name("empty_text")
    ok, _ = fn([{"chunk_id": "c1", "text": ""}], {})
    assert not ok
    ok, _ = fn([{"chunk_id": "c1", "text": "短"}], {})
    assert not ok
    ok, _ = fn([{"chunk_id": "c1", "text": "有实质内容的一整段正文文字"}], {})
    assert ok


# ---- make_row_recall_check（源表数据行 ↔ chunk title 对账）----


def _make_src(text: str, tmp_path):
    p = tmp_path / "src.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_row_recall_all_hit(tmp_path):
    name, fn, pass_msg = make_row_recall_check(
        name="装备行级召回",
        src_path=_make_src("| 长剑 | 1d8 |\n| 短剑 | 1d6 |", tmp_path),
        row_extractor=lambda text: {line.split("|")[1].strip() for line in text.splitlines() if line.startswith("|")},
        component_type="item",
        pass_msg="装备全命中",
    )
    ok, issues = fn([{"title": "长剑", "component_type": "item"}, {"title": "短剑", "component_type": "item"}], {})
    assert ok and not issues
    assert name == "装备行级召回"
    assert pass_msg == "装备全命中"


def test_row_recall_missing_fails(tmp_path):
    _, fn, _ = make_row_recall_check(
        name="装备行级召回",
        src_path=_make_src("| 长剑 | 1d8 |\n| 短剑 | 1d6 |", tmp_path),
        row_extractor=lambda text: {line.split("|")[1].strip() for line in text.splitlines() if line.startswith("|")},
        component_type="item",
    )
    ok, issues = fn([{"title": "短剑", "component_type": "item"}], {})
    assert not ok
    assert any("长剑" in i for i in issues)


def test_row_recall_empty_source_table_passes(tmp_path):
    """源表无数据行时不产生未命中，检查通过"""
    _, fn, _ = make_row_recall_check(
        name="怪物行级召回",
        src_path=_make_src("# 标题\n无表格正文。", tmp_path),
        row_extractor=lambda text: set(),
        component_type="monster",
    )
    ok, issues = fn([], {})
    assert ok and not issues


def test_row_recall_only_matching_component_type(tmp_path):
    """非目标 component_type 的 title 不参与对账"""
    _, fn, _ = make_row_recall_check(
        name="装备行级召回",
        src_path=_make_src("| 长剑 | 1d8 |", tmp_path),
        row_extractor=lambda text: {line.split("|")[1].strip() for line in text.splitlines() if line.startswith("|")},
        component_type="item",
    )
    ok, issues = fn([{"title": "长剑", "component_type": "other"}], {})
    assert not ok
    ok, issues = fn([{"title": "长剑", "component_type": "item"}], {})
    assert ok and not issues


def test_row_recall_missing_source_skips(tmp_path):
    """源文件不存在时跳过，返回通过（与现有 race 口径一致）"""
    _, fn, _ = make_row_recall_check(
        name="装备行级召回",
        src_path=tmp_path / "not_exist.md",
        row_extractor=lambda text: {"长剑"},
        component_type="item",
    )
    ok, issues = fn([], {})
    assert ok and not issues


def test_row_recall_override_src_path(tmp_path):
    """检查函数接受可选 src_path 覆盖，便于单测"""
    _, fn, _ = make_row_recall_check(
        name="装备行级召回",
        src_path=tmp_path / "default.md",
        row_extractor=lambda text: {line.split("|")[1].strip() for line in text.splitlines() if line.startswith("|")},
        component_type="item",
    )
    override = _make_src("| 长剑 | 1d8 |", tmp_path)
    ok, issues = fn([{"title": "长剑", "component_type": "item"}], {}, override)
    assert ok and not issues
