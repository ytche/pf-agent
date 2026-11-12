#!/usr/bin/env python3
"""D2 种族权威清单导出器（方案：数据侧产物增强 20260917 D2）

从 vectorizer/output/种族/chunks.jsonl（权威数据源，不回读 CHM 源 md）导出
全量种族条目清单 → vectorizer/output/种族/race_lists.json + 对账报告。
主条目 = component_type "race_overview"（各种族本体条目；alt_trait 等种族
特性/替换特性进 excluded_component_types）。

与 spell_list_export.py 同待遇：独立脚本、不挂 pipeline finalize、幂等、
自校验断言、verify 链软检查（WARN 不阻断）、build manifest 登记为
export_script 类 artifact（lists.race）。

条目附加字段（metadata 结构化字段，方案拍板）：race_group/ability_adj/
bio_type/size/speed/senses（race_type 等价物——metadata 无 race_type
键，bio_type=生物类型 即其口径）。用法（cwd=pf_data/phase1）：
  python3 race_list_export.py
"""
from vectorizer.list_export import export_list

OUT_DIR = "vectorizer/output/种族"

_RACE_META_KEYS = ("race_group", "ability_adj", "bio_type", "size", "speed", "senses")


def extra_fields(chunk: dict, md: dict) -> dict:
    return {k: (md.get(k) or "") for k in _RACE_META_KEYS}


def main() -> None:
    export_list(
        category="race",
        out_dir=OUT_DIR,
        main_types={"race_overview"},
        extra_fields=extra_fields,
        min_entries=100,  # 现量 111，-10% 余量
    )


if __name__ == "__main__":
    main()
