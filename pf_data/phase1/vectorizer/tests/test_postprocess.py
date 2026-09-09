"""test_postprocess.py — 决策 A finalize 后处理链测试（TDD，契约①幂等 + ③默认关闭）

契约：
  ① 幂等性硬契约：四步链跑第二次 diff 为空（backfill/apply 均为「只填缺失」模式）
  ② 顺序显式：POSTPROCESSORS 有序列表（声明顺序即执行顺序，此处由 feat.py 保证）
  ③ 默认关闭兼容：未声明 POSTPROCESSORS 的类目 → finalize 无操作
"""
import json
from pathlib import Path

import pytest

from vectorizer.postprocess.feat_chain import (
    ApplyChmTocMapping,
    ApplyFeatCreationSourcePromote,
    BackfillChmTocPath,
    BackfillFeatSource,
)
from vectorizer.processors.feat import FeatProcessor

# 顺序即执行顺序（契约②，与 FeatProcessor.POSTPROCESSORS 一致）
STEPS = [
    ApplyChmTocMapping,
    ApplyFeatCreationSourcePromote,
    BackfillChmTocPath,
    BackfillFeatSource,
]


def make_chunk(doc_id, title="测试专长", book="?", toc="", source=""):
    return {
        "chunk_id": f"{doc_id}-{title}-1",
        "doc_id": doc_id,
        "title": title,
        "aliases": [],
        "text": f"**先决条件：** 力量 13\n> 来源：{title}（Test Book），页码见原书，未整理 → 测试书 → TB",
        "component_type": "feat",
        "metadata": {"source": source, "format_cluster": "standard"},
        "book_abbreviation": book,
        "book_name_cn": "",
        "book_name_en": "",
        "source_confidence": 0,
        "chm_toc_path": toc,
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
    """含三类待处理状态的样本产物目录（book='?' 映射 / 造物专长一览 / toc 空 / source 空）"""
    chunks = [
        # ① 映射表命中（page_194 → CRB）
        make_chunk("page_194", "力量型专攻", toc="核心规则书 → 专长"),
        # ② 造物专长一览（promote 处理：行内来源标注 CRB）
        make_chunk("造物专长一览", "创造泥怪", book="?"),
        # ③ toc 空（backfill toc 依赖 md_map/源文件——测试环境无外部数据 → 保持空，幂等即验）
        make_chunk("page_999", "无来源专长"),
    ]
    chunks[1]["text"] = "**先决条件：** 制造\n\n【CRB】"
    chunks[1]["metadata"]["source"] = "CRB"
    # ④ source 空但 text 含来源行（backfill source 补齐）
    chunks[2]["text"] = "> 来源：极限荒野（Ultimate Wilderness），页码见原书，未整理 → 极限荒野UW → 专长"
    write_chunks(tmp_path, chunks)
    return tmp_path


def run_chain(dirpath: Path):
    for cls in STEPS:
        cls().run(dirpath, report_dir=dirpath / "reports")


def snapshot(dirpath: Path):
    """产物快照（幂等判定 = 第二次运行后产物不变）。

    报告 md 是过程记录（数字反映执行时链内状态，如步骤 1 报「设计保留」时
    promote 尚未执行），不纳入幂等判定——契约①只约束产物 chunks.jsonl。
    """
    p = dirpath / "chunks.jsonl"
    return p.read_text(encoding="utf-8")


# ---- 契约① 幂等硬契约 ----

def test_chain_idempotent(sample_dir):
    """四步链跑两次：第二次产物与第一次完全相同（重跑 diff 为空）"""
    run_chain(sample_dir)
    snap1 = snapshot(sample_dir)
    run_chain(sample_dir)
    snap2 = snapshot(sample_dir)
    assert snap1 == snap2


# ---- 终态断言（顺序执行后的确定性结果） ----

def test_chain_terminal_states(sample_dir):
    """四步链执行后：book 未知消除、source 补齐；toc 无外部数据保持空（幂等已验）"""
    run_chain(sample_dir)
    chunks = read_chunks(sample_dir)
    by_doc = {c["doc_id"]: c for c in chunks}

    # ① 映射命中 → CRB + conf 70
    assert by_doc["page_194"]["book_abbreviation"] == "CRB"
    assert by_doc["page_194"]["book_name_cn"] == "核心规则书"
    assert by_doc["page_194"]["source_confidence"] == 70
    # ② 造物专长一览行内标注 → 顶层 book（promote）
    assert by_doc["造物专长一览"]["book_abbreviation"] == "CRB"
    # ③ source 补齐（来源行 → 中文名（英文名））
    assert by_doc["page_999"]["metadata"]["source"] == "极限荒野（Ultimate Wilderness）"
    # ④ 映射/promote 覆盖的 '?' 全部消除；page_999 为虚构 doc（无映射表条目、
    # 非 SKIP_DOCS）→ 保持 '?' 属预期设计保留
    assert by_doc["page_999"]["book_abbreviation"] == "?"


# ---- 契约③ 默认关闭兼容 ----

def test_finalize_noop_without_declaration(tmp_path, monkeypatch):
    """未声明 POSTPROCESSORS 的类目 → pipeline.finalize 无操作（spell 等已验收类目零变化）"""
    from vectorizer.pipeline import Pipeline

    p = Path(tmp_path) / "out"
    p.mkdir(parents=True)
    chunks = [make_chunk("page_1")]
    write_chunks(p, chunks)
    before = (p / "chunks.jsonl").read_bytes()

    # 最小桩：伪 processor 无 POSTPROCESSORS 属性
    class Dummy:
        POSTPROCESSORS = None

    monkeypatch.setattr(Pipeline, "_finalize", Pipeline._finalize)
    pipe = Pipeline.__new__(Pipeline)
    pipe.output_dir = p
    pipe.processor = Dummy()
    pipe._finalize()

    assert (p / "chunks.jsonl").read_bytes() == before


# ---- 声明契约②：POSTPROCESSORS 与执行顺序匹配 ----

def test_postprocessors_declaration_matches_steps():
    """feat 声明的链 = 四步且顺序一致（映射 → promote → backfill toc → backfill source）"""
    declared = FeatProcessor.POSTPROCESSORS
    assert declared == STEPS


# ---- 映射表防漂移（apply_chm_toc_mapping 既有保护逻辑迁移） ----

def test_apply_mapping_keeps_skip_docs_unknown(sample_dir):
    """SKIP_DOCS（跨书索引）保持 '?'：page_1367 是设计保留"""
    chunks = read_chunks(sample_dir)
    chunks.append(make_chunk("page_1367", "超魔专长一览"))
    write_chunks(sample_dir, chunks)
    ApplyChmTocMapping().run(sample_dir, report_dir=sample_dir / "reports")
    out = read_chunks(sample_dir)
    assert out[-1]["book_abbreviation"] == "?"
