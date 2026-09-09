"""profession_index.py — 职业 finalize 步骤：class_archetype_index.json 等价索引写出

背景（CP3）：老脚本 vectorization_prep_profession.py 产出四件套
（chunks.jsonl / manifest.json / class_archetype_index.json / quality_report.md），
CP1 迁入框架后 pipeline 只写 chunks.jsonl + index.json，class_archetype_index.json
（审计用等价索引）缺失。write_outputs 遗留函数（processors/profession.py）依赖
老脚本内部 Chunk 的 class_name/book_source 顶层属性，迁移后 §3 映射已把业务字段
收进 metadata，且该函数从不被 pipeline 调用——本步骤按 §3 映射从最终 chunks.jsonl
重建等价索引，走框架 finalize 扩展点（类 + run(output_dir) 函数式接口，
见 pipeline.py _finalize）。

设计约束：
  - 只写出索引，不修改任何 chunk 数据（chunks.jsonl 零改动）→ 满足
    「CP3 不引入行为变化」，重跑产物与 CP2 after（13922）保持一致。
  - 幂等：同一产物重复执行输出相同（纯读 chunks.jsonl 重建）。
  - 结构对齐老产物（class_name / overview_chunk_ids / feature_chunk_ids /
    archetypes{archetype_name: {source_book, source_book_english,
    book_abbreviation, chm_toc_path, chunk_ids}}），字段来源按 §3 映射：
    class_name/archetype_name ← metadata，source_book ← book_name_cn，
    source_book_english ← book_name_en，其余顶层 1:1。
"""
import json
from pathlib import Path


class ProfessionIndexWriter:
    """写 class_archetype_index.json（审计用等价索引）。

    从 output_dir/chunks.jsonl（finalize 后最终态）按 component_type 归类：
      class_overview  → 职业级 overview_chunk_ids
      class_feature   → 职业级 feature_chunk_ids
      class_archetype → 按 metadata.archetype_name 归入 archetypes
    """

    def run(self, output_dir, report_dir=None) -> dict:
        output_dir = Path(output_dir)
        chunks_path = output_dir / "chunks.jsonl"
        index: dict = {}

        with chunks_path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                meta = d.get("metadata") or {}
                cn = meta.get("class_name") or "未知职业"
                cls = index.setdefault(cn, {
                    "class_name": cn,
                    "overview_chunk_ids": [],
                    "feature_chunk_ids": [],
                    "archetypes": {},
                })

                ct = d.get("component_type")
                if ct == "class_overview":
                    cls["overview_chunk_ids"].append(d.get("chunk_id", ""))
                elif ct == "class_feature":
                    cls["feature_chunk_ids"].append(d.get("chunk_id", ""))
                elif ct == "class_archetype":
                    an = meta.get("archetype_name") or "未知变体"
                    arc = cls["archetypes"].setdefault(an, {
                        "archetype_name": an,
                        "base_class": cn,
                        "source_book": d.get("book_name_cn", ""),
                        "source_book_english": d.get("book_name_en", ""),
                        "book_abbreviation": d.get("book_abbreviation", ""),
                        "chm_toc_path": d.get("chm_toc_path", ""),
                        "chunk_ids": [],
                    })
                    arc["chunk_ids"].append(d.get("chunk_id", ""))

        (output_dir / "class_archetype_index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "classes": len(index),
            "archetypes": sum(len(c["archetypes"]) for c in index.values()),
        }
