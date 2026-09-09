"""test_rule_postprocess.py — 规则模块 finalize 后处理测试（TDD，KN 家族 toc 回填）

背景（M5 闸口首次暴露）：organized 规则文件（91 个）不在 md_mapping.json
（CHM 转换产物，2141 条仅覆盖旧式命名 page_*.md 等），公共层 MdMappingTocProvider
富化落空 → 1390 chunk chm_toc_path 空。与专长（1348）/装备先例同源缺口，复用
feat_chain.BackfillChmTocPath 通用回填（装备同构子类先例）：源文件两类信号
（`<!-- XX-source:源md路径:条目标题 -->` 注释 + `> 来源：…未整理 → X → Y` 行）
100% 覆盖 91 文件（模拟验证注释级 87 + 来源行级 4）。

契约：
  ① 真实回填：toc 空 chunk → 从源文件信号解析出 CHM TOC 路径
  ② 幂等：二次运行 toc 不变（只填缺失）
  ③ 非空不动：已有 toc 的 chunk 不被覆盖
  ④ 装配：RuleProcessor.POSTPROCESSORS 含回填步骤（决策 A finalize 内建）
"""
import json
from pathlib import Path

import pytest

from vectorizer.processors.rule import RuleBackfillChmTocPath, RuleProcessor

# 真实规则 doc（源文件含 `<!-- BM-source:黑市规则.md:黑市规则 -->` 注释 +
# `> 来源：…未整理 → 黑市指南BM → 黑市规则` 行，文件级 toc 必可回填）
_REAL_DOC = "黑市指南BM_黑市规则"
# 源文件相对 phase1 cwd（run() 的 ORGANIZED 解析基准）
_REAL_SRC = "pf_rules_md_organized/规则/黑市指南BM_黑市规则.md"


def _write_chunks(tmp_path, chunks):
    p = tmp_path / "chunks.jsonl"
    p.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in chunks) + "\n",
                 encoding="utf-8")
    return p


def _read_rows(tmp_path):
    return [json.loads(l) for l in
            (tmp_path / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def _mk(cid, doc, toc=""):
    return {"chunk_id": cid, "doc_id": doc, "component_type": "rule_section",
            "title": "黑市规则", "text": "x", "book_abbreviation": "BM",
            "chm_toc_path": toc}


def _run(tmp_path):
    return RuleBackfillChmTocPath().run(tmp_path, report_dir=tmp_path / "reports")


# ---- 契约① 真实回填 ----

def test_backfill_real_doc_toc(tmp_path):
    """真实规则 doc 的 toc 空 chunk → 从源文件来源行回填（未整理 → 黑市指南BM → …）"""
    _write_chunks(tmp_path, [_mk("c1", _REAL_DOC)])
    stats = _run(tmp_path)
    rows = _read_rows(tmp_path)
    toc = rows[0]["chm_toc_path"]
    assert toc, "toc 必须被回填"
    assert toc.startswith("未整理 → 黑市指南BM")
    assert stats["filled"] == 1 and stats["unfilled"] == 0


# ---- 契约② 幂等 ----

def test_backfill_idempotent(tmp_path):
    """二次运行：已回填 toc 保持不变，回填计数归零"""
    _write_chunks(tmp_path, [_mk("c1", _REAL_DOC)])
    _run(tmp_path)
    toc1 = _read_rows(tmp_path)[0]["chm_toc_path"]
    stats2 = _run(tmp_path)
    toc2 = _read_rows(tmp_path)[0]["chm_toc_path"]
    assert toc1 == toc2
    assert stats2["filled"] == 0


# ---- 契约③ 非空不动 ----

def test_backfill_keeps_existing_toc(tmp_path):
    """已有 toc 的 chunk 不被覆盖"""
    _write_chunks(tmp_path, [_mk("c1", _REAL_DOC, toc="核心规则书 → 战斗规则")])
    _run(tmp_path)
    assert _read_rows(tmp_path)[0]["chm_toc_path"] == "核心规则书 → 战斗规则"


# ---- 契约④ 装配 ----

def test_processor_postprocessors_assembly():
    """finalize 链含 toc 回填步骤（决策 A：pipeline 重跑即自动执行，无独立脚本）"""
    assert RuleProcessor.POSTPROCESSORS == [RuleBackfillChmTocPath]


@pytest.fixture(autouse=True)
def _require_phase1_cwd():
    """run() 的 MD_MAP/ORGANIZED 为相对 phase1 cwd 的路径——确保测试在 phase1 跑"""
    assert Path("pf_rules_md_organized").is_dir(), "测试须以 phase1 为 cwd"
    assert Path("../md_mapping.json").is_file(), "测试须以 phase1 为 cwd"
    yield
