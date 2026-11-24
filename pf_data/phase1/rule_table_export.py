#!/usr/bin/env python3
"""KN221 规则内嵌表格结构化导出器

数据源 = 规则库 chunks.jsonl（权威产物，不回读 CHM 源 md，与 D3 职业成长表
同口径）；解析统一走 vectorizer/rule_tables.py（与处理器 metadata 同一事实源）。

产物：
  - vectorizer/output/规则/rule_tables.json         全量表格（612 张 / 472 chunk 实测）
  - vectorizer/output/规则/rule_table_export_report.json  分 layout 统计 + 异常清单

分档口径（spec D2~D4）：standard / flattened / no_separator，见 rule_tables
模块头注释。flattened 只保留原文行与 layout，不伪造表头/列级结构。

自校验（构建期硬闸口）：
  - table_id 全局唯一、各 layout 计数之和 = 总表数
  - chunks.jsonl 的 4 个表格 metadata 键与本脚本重算结果一致（不一致说明
    chunks 未按当前解析器重生成，须先跑 chunks.rule）
"""
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone

from vectorizer.rule_tables import LAYOUTS, parse_tables

# 与 pf_data/phase1/vectorizer/output/规则/ 同目录，相对 pf_data/phase1 运行
OUT_DIR = "vectorizer/output/规则"
CHUNKS_PATH = os.path.join(OUT_DIR, "chunks.jsonl")
JSON_PATH = os.path.join(OUT_DIR, "rule_tables.json")
REPORT_PATH = os.path.join(OUT_DIR, "rule_table_export_report.json")

VERSION = "1.0"
TABLE_ID_INDEX_BASE = 1


def build(chunks):
    """解析全量规则 chunks → (tables, stats, issues)。

    tables: 有序 dict {table_id: record}；record 结构见 Table.to_dict + doc_id。
    """
    tables = {}
    issues = []
    layout_tables = Counter()
    layout_chunks = {layout: set() for layout in LAYOUTS}
    chunks_with_table = set()
    metadata_mismatch = 0

    for ch in chunks:
        chunk_id = ch.get("chunk_id") or ""
        doc_id = ch.get("doc_id") or ""
        parsed = parse_tables(ch.get("text") or "", chunk_id)

        meta = ch.get("metadata") or {}
        expected = {
            "has_table": bool(parsed),
            "table_ids": [t.table_id for t in parsed],
            "table_titles": [t.title for t in parsed],
            "table_row_counts": [t.row_count for t in parsed],
        }
        for key, value in expected.items():
            if meta.get(key) != value:
                metadata_mismatch += 1
                if metadata_mismatch <= 10:
                    issues.append(
                        f"{chunk_id}: metadata.{key} 与重算不一致"
                        f"（chunks 未按当前解析器重生成？）")

        for t in parsed:
            if t.table_id in tables:
                raise AssertionError(f"table_id 重复: {t.table_id}")
            record = t.to_dict()
            record["doc_id"] = doc_id
            tables[t.table_id] = record
            layout_tables[t.layout] += 1
            layout_chunks[t.layout].add(chunk_id)
            chunks_with_table.add(chunk_id)
            if not t.title:
                issues.append(f"{t.table_id}: 无法取得表名（无表题且表头为空）")
            if t.layout == "standard" and not any(t.headers):
                issues.append(f"{t.table_id}: standard 表头为空")
            if t.layout == "standard" and not t.rows:
                issues.append(f"{t.table_id}: standard 无数据行（原始行保留可回查）")

    if metadata_mismatch:
        raise AssertionError(
            f"{metadata_mismatch} 处 metadata 表格键与重算不一致——"
            f"请先重跑 chunks.rule（python3 -m vectorizer.cicd verify --category rule）")

    stats = {
        "tables": len(tables),
        "chunks": len(chunks_with_table),
        "by_layout": {layout: layout_tables.get(layout, 0) for layout in LAYOUTS},
        "chunks_by_layout": {layout: len(ids) for layout, ids in layout_chunks.items()},
    }
    assert sum(stats["by_layout"].values()) == stats["tables"]
    return tables, stats, issues


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]
    fingerprint = hashlib.sha256(open(CHUNKS_PATH, "rb").read()).hexdigest()

    tables, stats, issues = build(chunks)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "version": VERSION,
        "category": "rule",
        "generated_at": generated_at,
        "generated_from": CHUNKS_PATH,
        "source_fingerprint": fingerprint,
        "table_id_index_base": TABLE_ID_INDEX_BASE,
        "counts": stats,
        "tables": tables,
    }
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    report = {
        "version": VERSION,
        "generated_at": generated_at,
        "source_fingerprint": fingerprint,
        "summary": stats,
        "tables_with_caption": sum(1 for r in tables.values() if r["caption"]),
        "issues": issues,
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    print("\n===== KN221 规则表格导出 =====")
    print(f"表 {stats['tables']} / chunk {stats['chunks']}")
    for layout in LAYOUTS:
        print(f"  {layout}: 表 {stats['by_layout'][layout]} / "
              f"chunk {stats['chunks_by_layout'][layout]}")
    if issues:
        print(f"issues（{len(issues)} 条，抽样）:")
        for item in issues[:15]:
            print("  -", item)
    print("产物 →", JSON_PATH, "|", REPORT_PATH)


if __name__ == "__main__":
    main()
