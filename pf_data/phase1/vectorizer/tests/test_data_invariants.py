"""test_data_invariants.py — 数据不变量闸口行为测试（A3 TDD）

聚焦 book '?' 余量 WARN：
  - 余量充足不打印 WARN
  - 余量 <10% 打印 WARN 但不改变闸口结果
  - 超限仍 fail（旧行为回归）
  - 上限 0 时跳过百分比计算
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

PHASE1 = Path(__file__).resolve().parent.parent.parent
SCRIPT = PHASE1 / "verify_data_invariants.py"


def _make_chunk(component_type="feat", book_abbreviation="CRB", chm_toc_path="toc"):
    return {
        "doc_id": "page_1",
        "title": "样例",
        "component_type": component_type,
        "text": "样例文本",
        "book_abbreviation": book_abbreviation,
        "chm_toc_path": chm_toc_path,
    }


def _run(tmp_path: Path, *, max_book_unknown: int, book_unknown: int,
         total: int = 10, main_count: int = 10) -> subprocess.CompletedProcess:
    chunks_path = tmp_path / "chunks.jsonl"
    rows = []
    # 主检索目标条目，保证 min-main-count 通过
    for _ in range(main_count):
        rows.append(_make_chunk(component_type="feat", book_abbreviation="CRB"))
    # 填充剩余行到 total
    for _ in range(total - main_count - book_unknown):
        rows.append(_make_chunk(component_type="other", book_abbreviation="CRB"))
    # book '?' 行
    for _ in range(book_unknown):
        rows.append(_make_chunk(component_type="other", book_abbreviation="?"))
    chunks_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")

    cmd = [
        sys.executable, str(SCRIPT),
        "--chunks", str(chunks_path),
        "--max-empty", "100",
        "--max-oversize", "100",
        "--min-total", "1",
        "--main-component", "feat",
        "--min-main-count", "1",
        "--max-book-unknown", str(max_book_unknown),
        "--max-toc-empty", "100",
    ]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=PHASE1)


def test_book_unknown_margin_healthy_no_warn(tmp_path):
    """余量充足（>10%）时不打印 WARN，闸口通过"""
    r = _run(tmp_path, max_book_unknown=10, book_unknown=1)
    assert r.returncode == 0
    assert "WARN" not in r.stdout
    assert "余量 9 / 90.0%" in r.stdout


def test_book_unknown_margin_low_warn_but_still_pass(tmp_path):
    """余量 <10% 时打印 WARN，但 N<=M 仍通过（闸口失败语义不变）"""
    r = _run(tmp_path, max_book_unknown=10, book_unknown=10)
    assert r.returncode == 0
    assert "WARN" in r.stdout
    assert "余量 0 / 0.0%" in r.stdout
    assert "< 10%" in r.stdout


def test_book_unknown_exceeds_limit_still_fails(tmp_path):
    """book '?' 超限仍 fail（旧行为回归）"""
    r = _run(tmp_path, max_book_unknown=10, book_unknown=11)
    assert r.returncode == 1
    assert "book '?' 11 > 上限 10" in r.stdout


def test_book_unknown_zero_limit_no_division_by_zero(tmp_path):
    """上限 0 时跳过百分比，无 WARN，零条通过"""
    r = _run(tmp_path, max_book_unknown=0, book_unknown=0, total=10, main_count=10)
    assert r.returncode == 0
    assert "WARN" not in r.stdout
    assert "余量 N/A（上限 0）" in r.stdout
