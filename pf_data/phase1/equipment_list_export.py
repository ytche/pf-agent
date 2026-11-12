#!/usr/bin/env python3
"""D2 装备权威清单导出器（方案：数据侧产物增强 20260917 D2；AKN-025 补全）

从 vectorizer/output/装备/chunks.jsonl（权威数据源，不回读 CHM 源 md）导出
全量装备条目清单 → vectorizer/output/装备/equipment_lists.json + 对账报告。
主条目 = gear 三族 component_type {gear, weapon, armor}（同 KN235 "gear/
weapon/armor 主条目族"口径）。

AKN-025（2026-11-11 设计 Spec）：在主线条目之外，从价格表行补全法杖/权杖/
戒指/奇物等只以价目表出现的类别（vectorizer/list_export.parse_price_table_
entries）——条目 chunk_id 指向来源价格表 chunk（溯源口径依赖），price 保留
原文、price_gp 为可空整数（解析失败条目保留并计入导出报告）。无标价条目
（神器/诅咒物品）同样保留在 entries（price_gp=null，Java 清单查询侧排序时
排最后，不进入“最高价”结论）；仅非条目族（enchantment/equipment_intro/
equipment_package 及智能物品/魔法植物等非价格表族）进 excluded_component_types。

KN235-① 清洗（拍板：清单导出层做，chunks.jsonl 不动）：table_candidates
净增补机制的 33 条表格碎片标题（page_210 分组行/单位行 24 条 + page_211
交通工具分组行/表头行 9 条）不独立出现在清单 entries，sink 回所属价目表
章节/条目（entries 或 sections 的 sunk_table_fragments 字段，价格数据
仍可在清单内追到）。检测为通用规则（标题形态 + 单表格行机制标记，
vectorizer/list_export.table_fragment_reason），无 chunk_id 特判。

与 spell_list_export.py 同待遇：独立脚本、不挂 pipeline finalize、幂等、
自校验断言、verify 链软检查（WARN 不阻断）、build manifest 登记为
export_script 类 artifact（lists.equipment）。

条目附加字段（metadata 结构化字段，方案拍板）：price/weight/slot
（slot 仅 not_applicable/missing 外的有义值）+ price_gp（AKN-025）。
用法（cwd=pf_data/phase1）：
  python3 equipment_list_export.py
"""
from vectorizer.list_export import export_list, parse_price_gp

OUT_DIR = "vectorizer/output/装备"
# 主条目族：gear/weapon/armor + 无标价神器/诅咒物品（AKN-025：Spec 要求
# 无标价条目（神器等）保留在清单，price_gp=null，排序时排最后）
MAIN_TYPES = {"gear", "weapon", "armor", "artifact", "cursed_item"}
_SLOTS_DROP = {"not_applicable", "missing", ""}


def extra_fields(chunk: dict, md: dict) -> dict:
    slot = str(md.get("slot") or "")
    price = str(md.get("price") or "")
    return {
        "price": price,
        # 主目录 metadata price 亦可能为裸数字/千分位（如 `120,830`、`1,000`），
        # 与价格表同口径按 gp 解析（PK1-3）；无法解析才为 null
        "price_gp": parse_price_gp(price, allow_bare=True),
        "weight": str(md.get("weight") or ""),
        "slot": "" if slot in _SLOTS_DROP else slot,
    }


def main() -> None:
    export_list(
        category="equipment",
        out_dir=OUT_DIR,
        main_types=MAIN_TYPES,
        extra_fields=extra_fields,
        min_entries=4100,  # 现量 2802 主条目 + 价格表类别，余量充足
        clean_table_fragments=True,
        expected_fragments=33,  # KN235-① 登记数（棘轮：漂移即断言失败）
        include_price_tables=True,
    )


if __name__ == "__main__":
    main()
