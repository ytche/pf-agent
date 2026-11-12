#!/usr/bin/env python3
"""D2 专长权威清单导出器（方案：数据侧产物增强 20260917 D2）

从 vectorizer/output/专长/chunks.jsonl（权威数据源，不回读 CHM 源 md）导出
全量专长条目清单 → vectorizer/output/专长/feat_lists.json + 对账报告。
主条目 = component_type "feat"（feat_index/feat_intro 进 excluded_component_types）。

与 spell_list_export.py 同待遇：独立脚本、不挂 pipeline finalize、幂等
（无时间戳，重跑字节一致）、自校验断言、verify 链软检查（WARN 不阻断）、
build manifest 登记为 export_script 类 artifact（lists.feat）。

条目附加字段：prerequisites_raw（metadata.prerequisites.raw 结构化字段，
方案拍板"白送"）、feat_type。用法（cwd=pf_data/phase1）：
  python3 feat_list_export.py
"""
from vectorizer.list_export import export_list

OUT_DIR = "vectorizer/output/专长"


def extra_fields(chunk: dict, md: dict) -> dict:
    prereq = md.get("prerequisites") or {}
    return {
        "prerequisites_raw": prereq.get("raw") or "",
        "feat_type": [str(t) for t in (md.get("feat_type") or [])],
    }


def main() -> None:
    export_list(
        category="feat",
        out_dir=OUT_DIR,
        main_types={"feat"},
        extra_fields=extra_fields,
        min_entries=3600,  # 现量 4080，-10% 余量（方案阈值口径）
    )


if __name__ == "__main__":
    main()
