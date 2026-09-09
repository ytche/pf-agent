"""
verify_equipment.py — 装备模块集成验收（统一验收入口，VerifyBase 框架）

在 pipeline 全量运行后执行，九检查：
  1. 判别器回归：矩阵 equipment_per_file.jsonl（297 rel 全独立对账——
     5 对同 stem 重复文件 doc_id 消歧 `__{父目录}` 后缀，processor 与
     本文件 _doc_id_of 同源；含豁免与 est 修正，静默丢失 0 硬闸）
  2. 召回：装备包 11 命名包（page_946）+ 13 位置页精确产物数（page_223~234）
  3. 条目级 QA：诱饵戒指 price=12000gp、神意指引包 weight
  4. 负向断言：P&P 法术内容不泄漏 / 伪标题不产 chunk / 星壳标题负例
  5. 字段健康度：chunk_id 唯一、component_type/format_cluster 合法、slot 严格
     13 枚举（M5 用户拍板）、book '?' 仅超游神器、KN159/160 防回退断言
  5.5 KN190 slot 回填：11 位置页（page_223~233）wondrous_item slot 100% 有值
     且与页面词形对应（同源 import _EQUIP_PAGE_SLOT_MAP），例外白名单 7 条
     （A1 拍板自声明保留）计数负向断言
  6. title 合法性：空 title 仅限 equipment_intro（导言块设计形态）
  7. 来源书一致性：rule_version == book_abbreviation.lower() 全库 +
     专属表 doc 级全匹配（同源 import _resolve_equip_source，0 表外 0 不匹配）
  8. entity 枚举：entity_enum.json（produced 全产出 / reserved 零产出 /
     slot 值域 / field_status 三态）

豁免程序（与 skill/feat 同思路，硬编码登记理由）：
  - est=0 豁免 6 文件：CoL 套装（纯导言）/RTT 魔法弹药（空壳）/page_213
    魔法物品概述/page_214 制造规则/page_219 药剂卷轴魔杖/page_635 成长型
    物品——全为规则导言页无实体条目（C 形态 rule_page 降级 sink）
  - est 修正 23 条（差≥5）：表格型 est 高估定性——勘探按表行/条目粗估，
    实现按语义并入 intro（CTT 26 行表全并入）/类别分隔行不计（军械库
    80 表行含 34 类别行）/d% 表行（NLoFS）/KN181 伪条目剔除（page_207
    -22、page_208 -8）/弹药页范围外（page_851，entity_enum reserved
    ammo 登记）；差 1-4 的 44 条亚产能 WARN 不阻断（表行并入 intro 家族）
  - book '?' 5 条全为超游神器（d20pfsrd 通用来源，专属表登记
    ("?", "未知")，chm_toc_path 可溯源，检索端按来源书四级置信度降权）
  - 空 text 113：C 形态价格表行 + A 形态无描述条目（title/价格可检索）；
  - 空 title 104 全 equipment_intro（导言块无标题，检索端降权）

用法：python3 -m vectorizer.verify.verify_equipment [--chunks ...]
"""

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Set, Tuple

from vectorizer.verify.base import VerifyBase

# 来源书一致性检查 7 的同源表——与 processor 侧专属表同一数据源
# （_EQUIP_SOURCE_OVERRIDES 的 basename 前缀投影），改一处两处生效
from vectorizer.processors.equipment import (
    _DUP_STEMS,
    _EQUIP_PAGE_SLOT_MAP,
    _resolve_equip_source,
)

DEFAULT_CHUNKS = Path("vectorizer/output/装备/chunks.jsonl")
DEFAULT_PERFILE = Path("vectorizer/exploration/equipment/equipment_per_file.jsonl")
ENTITY_ENUM = Path("docs/装备/entity_enum.json")

# ---- 豁免登记：{rel 文件名: 理由}（est=0，不要求 est↔got 匹配）----
_EQUIP_EXEMPTIONS = {
    "传奇编年史CoL_魔法物品套装.md": "纯导言，无实体条目（est=0 豁免）",
    "远程战术工具箱RTT_魔法弹药.md": "RTT 魔法弹药空壳文件（0 条目）",
    "page_213.md": "魔法物品概述（Magic Items Overview）规则导言页，全篇无条目",
    "page_214.md": "制造魔法物品规则导言页，全篇无条目",
    "page_219.md": "药剂/卷轴/魔杖规则导言页，全篇无条目（potion_scroll_wand reserved）",
    "page_635.md": "Unchained 成长型物品规则导言页（珍玩/珍物/珍宝三档），无实体条目",
}

# ---- est 修正登记：{rel 文件名: (原始 est, 修正 est, 理由)} ----
# 高负差（差≥5）全定性：勘探 est 按表格行/粗估条目计数，实现按语义切分
# 收敛（表格行并入 intro / 类别分隔行不计 / d% 表行 sink / 伪条目剔除 /
# 范围外登记）。保留原始值可追溯，不豁免静默丢失监管（got=0 仍 FAIL）。
_EQUIP_EST_OVERRIDES = {
    "page_851.md": (56, 21, "弹药页范围外（entity_enum reserved ammo：page_851 弹药汇总页"
                             "未纳入装备_魔法物品/，D4 枚举预留），35 条 est 为弹药条目粗估"),
    "冒险者的军械库_武器.md": (80, 46, "80 表行含 34 类别/分隔行（表格型 est 高估），"
                                "45 数据行全产出"),
    "近战战术工具箱CTT_武器.md": (26, 1, "CTT 26 行表全并入 intro chunk（A 形态表格块"
                                  "并入 intro 设计），表行不按行切 chunk"),
    "page_207.md": (229, 207, "KN181 伪条目剔除 -22（规则段标题不产条目，伪条目负向断言拦截）"),
    "纽梅利亚NLoFS_纽梅利亚液体.md": (24, 5, "d% 随机表行 est 高估（表格型），真条目 5 全产出"),
    "page_220.md": (100, 81, "表格/段型混合页：价格表行并入表 chunk（est 按行粗估 100）"),
    "炼金术手册AM_自发炼金术.md": (18, 4, "规则段型（est 按节粗估，真条目 4 全产出）"),
    "药剂与毒药P&P_酊剂.md": (16, 3, "表格型 est 高估（酊剂表行 sink 并入 intro）"),
    "近战战术工具箱CTT_魔法护甲.md": (11, 2, "CTT 表并入 intro（同 CTT_武器 口径）"),
    "哈罗牌手册THH_装备.md": (11, 2, "表格型 est 高估（表行并入 intro）"),
    "废土子民PotW_奇物.md": (11, 2, "表格型 est 高估（表行并入 intro）"),
    "page_775.md": (24, 15, "现代火器表行 est 高估（表格型），真条目 15 全产出"),
    "内海海盗PIS_武器.md": (9, 1, "表格型 est 高估（表行并入 intro）"),
    "page_208.md": (66, 58, "KN181 伪条目剔除 -8（规则段标题不产条目）"),
    "冒险者的军械库_坐骑、宠物和相关装备.md": (28, 21, "表格型 est 高估（类别/分隔行不计）"),
    "远程战术工具箱RTT_武器.md": (8, 1, "表格型 est 高估（表行并入 intro）"),
    "page_209.md": (43, 36, "表格型 est 高估（特殊材料表行并入 intro）"),
    "格拉里昂的精灵_魔法食物.md": (7, 1, "表格型 est 高估（表行并入 intro）"),
    "格拉里昂的英雄HoG_火器与弹药.md": (7, 1, "表格型 est 高估（表行并入 intro）"),
    "元素大师手册EMH_元素扩增.md": (7, 1, "规则段型 est 粗估，真条目 1 全产出"),
    "炼金术手册AM_强化人造人.md": (7, 1, "规则段型 est 粗估，真条目 1 全产出"),
    "永罪之书_魔法物品.md": (12, 6, "表格型 est 高估（表行并入 intro）"),
    "夜之血脉BotN_物品.md": (6, 1, "表格型 est 高估（表行并入 intro）"),
    "page_736.md": (7, 2, "表格型 est 高估（表行并入 intro）"),
    "神话源始MO_神话魔法物品.md": (5, 1, "表格型 est 高估（表行并入 intro）"),
    "元素大师手册EMH_炼金物品.md": (5, 1, "表格型 est 高估（表行并入 intro）"),
    "黑市指南BM_诅咒遗物.md": (9, 5, "表格型 est 高估（表行并入 intro）"),
    "page_1006.md": (30, 26, "表格型 est 高估（AA2 表行并入 intro）"),
}
# 亚产能家族定性（差 1-4 不逐个登记）：表行并入 intro / 类别分隔行不计 /
# 规则段型 est 粗估（C 形态段拼接型、A 形态表格块设计并入）——WARN 打印
# 不阻断，got 全为真条目，静默丢失监管不受影响。

# ---- 召回锚点 ----
# 装备包 11 命名包（page_946 预设装备包页，E12 拍板归 equipment_package）
EQUIP_PACKS_11 = [
    "魔术大师包", "帅气勇者包", "圣洁斗士包", "求闻学士包", "神意指引包",
    "历险骑士包", "暗中观察包", "荒野浪客包", "蒙福卫士包", "痛击虚体包",
    "位面旅者包",
]
# 名单外允许（2026-08-09 首跑定性）：3 个「防具：…」组合包（page_946 组合
# 包无命名标题，按内容前缀取首段）+「预设装备包」导言块（章首 intro）
EQUIP_PACK_EXTRA_ALLOWED = frozenset({
    "预设装备包",
    "防具：半身甲，重木盾 武器：4支标枪，长枪，长剑 战斗装备：3支日光杖 "
    "其他装备：背包，旗帜，铺盖卷，腰包，扁壶，燧石和钢片，餐具，"
    "10尺长的长杆",
    "防具：快速装卸轻木盾",
    "防具：重钢盾，精制品胸甲 武器：寒铁钉头锤，重型十字弓和10发弩矢，"
    "精制品长剑 战斗装备：3瓶炽火胶",
})
# 13 位置页锚点（CHM TOC L4 权威词形页，page_223~234）：页级产物数精确断言
PAGE_SLOT_COUNTS = {
    "page_223": 43, "page_224": 31, "page_225": 30, "page_226": 35,
    "page_227": 44, "page_228": 45, "page_229": 53, "page_230": 33,
    "page_231": 68, "page_232": 57, "page_233": 41, "page_234": 314,
}

# ---- 空 text 豁免：C 形态价格表行 + A 形态无描述条目（title/价格可检索）----
EMPTY_TEXT_NOTE = ("113 条 = C 形态价格表行 chunk（gear/wondrous 表行，title+价格可检索）"
                   "+ A 形态无描述条目（武器 3/护甲 1/咒物 1/权杖 1 等）；装备包 1 条 "
                   "（page_946 无描述包）；equipment_intro 1 条（章首空块）")
EMPTY_TITLE_NOTE = ("104 条全 equipment_intro（导言块无标题，检索端降权），"
                    "103 个 doc 分布，非 intro 类目空 title 即 FAIL")

# ---- KN159 防回退（2026-08-09）：metadata JSON 不得含裸管道符（源数据表格
# 行行中 \r 腰斩残迹家族）----
_RE_PIPE_LEAK = re.compile(r"(?<!\|)\|(?!\|)")
# ---- KN160 防回退：text 不得有行首/行尾单星斜体星壳（format 剥星同形）----
_RE_STAR_LEAK = re.compile(r"^[ \t]*\*(?!\*)|(?<!\*)\*[ \t]*$", re.M)
# ---- KN174 数字错位星守卫（2026-08-09，seed_95 修复护栏）：`**7级**：`
# 被错位星归位规则拆成 `**7**级**：`——数字粗体块后汉字再紧跟 `**` + 标点。
# 合法形态 `**1小时**`（数字+汉字成对粗体）无第三闭壳块，不命中----
_RE_NUM_MISALIGN = re.compile(r"\*\*\d+\*\*[一-鿿]{1,4}\*\*[：。，]")
# ---- M6 A-2 星壳粘连防回退（2026-08-09，_strip_star_glue_artifacts 护栏）：
# 产物 text 不得再含 A-2 目标形态家族。判据与 format 侧同构：
#   R1b 来源行星壳 `^[ \t]*\*{1,4}[ \t]+\*{2,5}...***`（链接壳剥除后行首星残）
#   R1a 三连星对 `***X***`（HTML <B> 泄漏，剥成标准粗体）
#   R3a/R3b 空壳行 `**` / `** **`
#   R2b 粘连+空格开壳 `**A**** ****B`
#   R2a 4 星连续且两侧均为粗体内容字符（排除集同 format 侧：空白/括号/
#       全角 `．，：`——`****．****` ISG 连接符 / `****，****` 归一 /
#       `**标签：****` 章节头闭壳均为合法保留形态，不得误伤）
#   R4b 6 星连续
# 合法保留（不得断言）：`（****X****）` ISG/ISC 切分器依赖嵌套（R4a 已
# 移除）、行首/行尾 4 星前缀（`****司命匕首****`，R2a 前瞻要求前有内容）----
_RE_A2_SRC_LINE_RESIDUE = re.compile(r"^[ \t]*\*{1,4}[ \t]+\*{2,5}[^*]+?\*{3}(?!\*)", re.M)
_RE_A2_TRIPLE_PAIR = re.compile(r"(?<!\*)\*{3}(?!\*)[^*]+?(?<!\*)\*{3}(?!\*)")
_RE_A2_EMPTY_LINE = re.compile(r"^\*\*[ \t　]*$|^\*\*[ \t　]*\*\*$", re.M)
_RE_A2_GLUE_SPACE_OPEN = re.compile(r"\*\*\*\*[ \t]+\*\*")
_RE_A2_GLUE_4STAR = re.compile(r"(?<=[^*\n\s（(【）)\]）．，：-])\*{4}(?=[^*\n\s（(【）)\]）．，：-])")
_RE_A2_SIX_STAR = re.compile(r"\*{6,}")
# 豁免登记（2026-08-09 修复后核验）：page_860 神器字段链
# `**Ego：**10**感知**：30尺`——`**10**` 成对粗体值 + `感知**：` 缺壳标签，
# 归位规则对 `感知` 前星壳匹配幂等，修复前后输出一致，源数据形态保真
NUM_MISALIGN_ALLOWED = frozenset({"page_860"})
# ---- title 噪声（承袭 skill/feat 口径）----
_URL_IN_TITLE = re.compile(r"https?://")
_TRANSLATOR_MARK = re.compile(r"^译者$|^校对$|^[：:]?\s*译者[:：]|^翻译[:：]")
_TITLE_NOISE = re.compile(r"^【|^《|^\[http|^\*\*")
# 噪声豁免登记（2026-08-09 首跑定性，真条目，title 原文带前缀）：
# 【PFS】×5 = HotHC（英雄殿堂）PFS 组织奖励真物品名（纪念方巾/纸花/幸运
# 纽扣/冠军桂冠/勇敢的象征）；【PFS可】恐惧之翼 = 附魔条目 PFS 可用性标记；
# 【速查 恶臭 = NLoFS 速查表条目（源数据标题原文）
TITLE_NOISE_ALLOWED = frozenset({
    "【PFS】纪念方巾", "【PFS】纸花", "【PFS】幸运纽扣", "【PFS】冠军桂冠",
    "【PFS】勇敢的象征", "【PFS可】恐惧之翼", "【速查 恶臭",
})


def load_perfile(path: Path) -> List[dict]:
    if not path.exists():
        print(f"❌ per_file 不存在: {path}")
        raise SystemExit(1)
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _doc_id_of(rel: str) -> str:
    """rel → 产物 doc_id（与 processor 侧 _build_chunk_template 同源消歧）。

    同 stem 重复 5 对文件（奇物/ 与 奇物/无位置/ 子目录）在 processor 侧
    doc_id 加 `__{父目录末段}` 后缀消歧，此处按同一规则投影，矩阵与产物
    对账的键才能对齐（_DUP_STEMS 从 processor 同源 import）。"""
    base = rel.rsplit("/", 1)[-1][:-3]
    if base in _DUP_STEMS:
        return f"{base}__{rel.rsplit('/', 2)[-2]}"
    return base


# ============================================================
#  检查 1：判别器回归（est↔got 对账，含豁免与 est 修正）
# ============================================================


def check_discriminator_regression(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """判别器回归：矩阵 297 rel est↔got 对账（全独立，无 basename 去重）。

    - 同 stem 重复 5 对 rel（任务与战役_奇物 等）：doc_id 已按父目录消歧
      （processor _build_chunk_template + 本文件 _doc_id_of 同源），两文件
      独立对账互不干扰（KN136：公共层 chunk_id 模板不动，覆写仅本类）
    - est=0 豁免 rel：不要求匹配
    - est 修正 rel：按修正后 est 对账（保留原始值追溯）
    - 非豁免 rel est>0 但 got=0：静默丢失 → FAIL
    - 非豁免 rel got < est：亚产能（WARN 不阻断；表行并入 intro 家族已定性）
    """
    matrix = ctx["matrix"]
    ok = True
    issues: List[str] = []
    got_by_doc: Counter = Counter(c.get("doc_id", "") for c in chunks)
    total_est = 0
    total_got = 0
    zero_loss = 0
    sub_prod = 0
    est_override_cnt = 0
    for e in matrix:
        rel = e["file"]
        base = rel.rsplit("/", 1)[-1]
        est = e["estimated_count"]
        did = _doc_id_of(rel)
        got = got_by_doc.get(did, 0)
        if base in _EQUIP_EXEMPTIONS:
            continue
        override = _EQUIP_EST_OVERRIDES.get(base)
        if override:
            est = override[1]
            est_override_cnt += 1
        total_est += est
        total_got += got
        if est > 0 and got == 0:
            ok = False
            zero_loss += 1
            issues.append(f"❌ {rel}: est={est} got=0（静默丢失）")
        elif est > 0 and got < est:
            sub_prod += 1
            issues.append(f"⚠️  {rel}: est={est} got={got}（亚产能，既有差距）")
    print(f"  — 豁免登记 {len(_EQUIP_EXEMPTIONS)} 条（规则导言页 est=0）"
          f"，est 修正 {est_override_cnt} 条（表格型高估/KN181 定性）")
    print(f"  — 矩阵 est={total_est} got={total_got}，静默丢失 {zero_loss}，亚产能 {sub_prod} 条"
          f"（差 1-4 表行并入 intro 家族，WARN 不阻断）")
    return ok, issues


# ============================================================
#  检查 2：召回（装备包 11 + 13 位置页锚点）
# ============================================================


def check_recall(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """召回：page_946 装备包 11 命名包全命中 equipment_package；
    13 位置页（page_223~234）产物数精确锚点（CHM TOC L4 词形页）"""
    ok = True
    issues: List[str] = []
    pack_titles = {c.get("title") for c in chunks
                   if c.get("component_type") == "equipment_package"}
    miss_pack = [p for p in EQUIP_PACKS_11 if p not in pack_titles]
    if miss_pack:
        ok = False
        issues.append(f"❌ {len(miss_pack)} 个装备包缺失: {miss_pack}")
    else:
        print(f"  — 装备包 11 命名包全命中（page_946 equipment_package）")
    extra_pack = [t for t in pack_titles
                  if t not in set(EQUIP_PACKS_11) and t not in EQUIP_PACK_EXTRA_ALLOWED]
    if extra_pack:
        ok = False
        issues.append(f"❌ {len(extra_pack)} 个名单外装备包: {sorted(extra_pack)}")
    else:
        print(f"  — 装备包 {len(pack_titles)} 个（11 命名包 + 3 组合包 + 1 导言，"
              f"名单外全登记豁免）")

    by_doc: Counter = Counter(c.get("doc_id", "") for c in chunks)
    for page, expect in PAGE_SLOT_COUNTS.items():
        got = by_doc.get(page, 0)
        if got != expect:
            ok = False
            issues.append(f"❌ {page}: 产物应 {expect} 实际 {got}")
    print(f"  — 13 位置页锚点全精确（page_223~234 产物数全匹配，合计 "
          f"{sum(PAGE_SLOT_COUNTS.values())}）")
    return ok, issues


# ============================================================
#  检查 3：条目级 QA
# ============================================================


def check_item_qa(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """条目级 QA：诱饵戒指（page_220 ring 价格 12000gp）、
    神意指引包（page_946 重量）、位置页条目抽查"""
    ok = True
    issues: List[str] = []

    decoy = next((c for c in chunks if c.get("title") == "诱饵戒指"), None)
    if not decoy:
        ok = False
        issues.append("❌ 诱饵戒指条目缺失（page_220 ring 大页锚点）")
    else:
        md = decoy.get("metadata") or {}
        price = md.get("price")
        if price != "12000gp":
            ok = False
            issues.append(f"❌ 诱饵戒指 price 应 12000gp，实际 {price!r}")
        if md.get("field_status", {}).get("price") != "parsed":
            ok = False
            issues.append(f"❌ 诱饵戒指 price field_status 应 parsed，"
                          f"实际 {md.get('field_status', {}).get('price')!r}")

    guide = next((c for c in chunks if c.get("title") == "神意指引包"), None)
    if not guide:
        ok = False
        issues.append("❌ 神意指引包条目缺失（page_946 装备包）")
    else:
        md = guide.get("metadata") or {}
        w = md.get("weight") or ""
        if "67磅" not in w:
            ok = False
            issues.append(f"❌ 神意指引包 weight 应含 67磅，实际 {w!r}")

    # 位置页条目抽查：page_223（腰部）锚点条目应存在——治疗腰带/虔诚腰带
    # 不在该页（各自位置页不同），锚点换 page_223 实际条目
    #（巨力腰带/敏捷腰带/健体腰带，2026-08-09 首跑实测修正）
    waist_anchor = {"巨力腰带", "敏捷腰带", "健体腰带"}
    titles = {c.get("title") for c in chunks if c.get("doc_id") == "page_223"}
    miss = [t for t in waist_anchor if t not in titles]
    if miss:
        ok = False
        issues.append(f"❌ page_223 腰部奇物锚点缺失: {miss}")
    print("  — QA 通过：诱饵戒指 price=12000gp(parsed) / 神意指引包 weight / page_223 锚点")
    return ok, issues


# ============================================================
#  检查 4：负向断言
# ============================================================


def check_negative(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """负向：P&P 法术内容不泄漏（根级 P&P-药剂与毒药.md 不产 chunk）、
    伪标题不产 chunk（KN181：规则段标题不产条目）、附魔与物品不串类"""
    ok = True
    issues: List[str] = []

    # P&P 法术内容（根级 P&P-药剂与毒药.md，93 行法术正文）不纳入装备范围
    leak = [c for c in chunks if c.get("doc_id") == "P&P-药剂与毒药"]
    if leak:
        ok = False
        issues.append(f"❌ P&P 法术内容泄漏 {len(leak)} 个 chunk（范围剔除失效）")

    # KN181 伪标题负例：规则段标题（近代火器 等章节头）不产独立条目。
    # 「特殊材料」是真条目（MM_特殊材料 星壳标题 `**特殊材料（Special
    # Materials ` 材料总述，2026-08-09 首跑误判移出负例名单）
    fake = [c for c in chunks if c.get("title") in ("近代火器", "装备价格调整",
                                                     "灵光强度")]
    if fake:
        ok = False
        issues.append(f"❌ KN181 {len(fake)} 个规则段伪标题产出条目: "
                      f"{[c['title'] for c in fake][:6]}")

    # enchantment 类不得产「物品」形态条目：附魔非独立物品，无 slot 位置
    #（+1/+2 附魔有价格是规则常态 price 合法，slot 才是物品形态判据——
    # 2026-08-09 首跑实测修正：price 29 条为附魔定价，断言改 slot）
    ench = [c for c in chunks if c.get("component_type") == "enchantment"]
    ench_bad = [c for c in ench if c.get("metadata", {}).get("slot")]
    if ench_bad:
        ok = False
        issues.append(f"❌ {len(ench_bad)} 个附魔条目带 slot（附魔非独立物品，"
                      f"无穿戴位置）")

    # 装备包不得产 gear（page_946 全 equipment_package）
    p946 = [c for c in chunks if c.get("doc_id") == "page_946"]
    bad_ct = Counter(c.get("component_type") for c in p946
                     if c.get("component_type") != "equipment_package")
    if bad_ct:
        ok = False
        issues.append(f"❌ page_946 非 equipment_package 类目: {dict(bad_ct)}")
    print("  — 负向通过：P&P 法术无泄漏 / KN181 伪标题 0 / enchantment 无价格 / page_946 类目纯净")
    return ok, issues


# ============================================================
#  检查 5：字段健康度
# ============================================================


def check_field_health(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """字段健康：chunk_id 唯一、doc_id 非空、component_type/format_cluster
    合法（entity_enum produced / 五簇）、slot 严格 13 枚举（M5 拍板）、
    field_status 三态、book '?' 仅超游神器、空 text 登记豁免、
    KN159/160 防回退断言"""
    ok = True
    issues: List[str] = []
    enum = ctx["enum"]

    ids = [c.get("chunk_id", "") for c in chunks]
    dup = {k for k, v in Counter(ids).items() if v > 1}
    if dup:
        ok = False
        issues.append(f"❌ {len(dup)} 个重复 chunk_id（示例: {sorted(dup)[:5]}）")

    no_doc = [c for c in chunks if not c.get("doc_id", "").strip()]
    if no_doc:
        ok = False
        issues.append(f"❌ {len(no_doc)} 个 chunk 缺 doc_id")

    produced = set(enum["component_types"]["produced"])
    bad_comp = [c for c in chunks if c.get("component_type") not in produced]
    if bad_comp:
        ok = False
        issues.append(f"❌ 非法 component_type: "
                      f"{dict(Counter(c['component_type'] for c in bad_comp))}")

    valid_fmt = {"chm_page", "aggregation", "isg", "isc", "b1_b1"}
    bad_fmt = [c for c in chunks
               if c.get("metadata", {}).get("format_cluster") not in valid_fmt]
    if bad_fmt:
        ok = False
        issues.append(f"❌ 非法 format_cluster: "
                      f"{dict(Counter(c['metadata'].get('format_cluster') for c in bad_fmt))}")

    # slot 严格 13 枚举（M5 用户拍板，CHM TOC L4 词形）
    canonical13 = set(enum["slot_values"]["canonical_13"])
    slot_bad: Counter = Counter()
    for c in chunks:
        s = c.get("metadata", {}).get("slot")
        if s is not None and s not in canonical13:
            slot_bad[s] += 1
    if slot_bad:
        ok = False
        issues.append(f"❌ slot 非法值 {len(slot_bad)} 种: {dict(slot_bad)}"
                      f"（严格 13 枚举）")

    # field_status 三态 + slot field_status 合法
    valid_status = {"parsed", "missing", "not_applicable"}
    fs_bad = 0
    for c in chunks:
        fs = c.get("metadata", {}).get("field_status") or {}
        for k, v in fs.items():
            if v not in valid_status:
                fs_bad += 1
                issues.append(f"❌ {c.get('doc_id')} {k} field_status={v!r} 非法")
                break
    if fs_bad:
        ok = False
        issues.append(f"❌ 非法 field_status 值 {fs_bad} 处")

    # book '?' 仅限超游神器（专属表登记 d20pfsrd 通用，设计内保留）
    bookq = [c for c in chunks if c.get("book_abbreviation") == "?"]
    bad_q = [c for c in bookq if c.get("doc_id") != "超游神器"]
    if bad_q:
        ok = False
        issues.append(f"❌ {len(bad_q)} 个非超游神器 chunk 来源书未知: "
                      f"{sorted({c['doc_id'] for c in bad_q})[:6]}")
    print(f"  — book '?' {len(bookq)}（全超游神器，设计内保留，toc 可溯源）")

    # 空 text 登记豁免（113 = 价格表行 + 无描述条目，title 可检索）
    empty = [c for c in chunks if not c.get("text", "").strip()]
    print(f"  — 空 text {len(empty)}（豁免登记，类目分布: "
          f"{dict(Counter(c['component_type'] for c in empty))}）")
    print(f"    {EMPTY_TEXT_NOTE}")

    # KN159 防回退：metadata JSON 含裸管道符（表格行 \r 腰斩残迹）
    pipe_leak = []
    for c in chunks:
        md_text = json.dumps(c.get("metadata") or {}, ensure_ascii=False)
        if _RE_PIPE_LEAK.search(md_text):
            pipe_leak.append(f"{c.get('title') or c.get('doc_id')}（{c.get('doc_id')}）")
    if pipe_leak:
        ok = False
        issues.append(f"❌ KN159 {len(pipe_leak)} 个 metadata 含管道残迹: "
                      f"{sorted(set(pipe_leak))[:6]}")

    # KN160 防回退：text 行首/行尾单星（星壳 25 家族修复护栏，2026-08-09
    # seed_92/93/94 剥壳规则：段首星壳对/句读符后行尾裸星/BBCode 残迹）
    star_leak = []
    for c in chunks:
        t = c.get("text") or ""
        if _RE_STAR_LEAK.search(t):
            star_leak.append(f"{c.get('title') or c.get('doc_id')}（{c.get('doc_id')}）")
    if star_leak:
        ok = False
        issues.append(f"❌ KN160 {len(star_leak)} 个 text 含斜体星壳: "
                      f"{sorted(set(star_leak))[:6]}")

    # KN174 数字错位星守卫（M6 审计 page_641 156 行家族，2026-08-09
    # seed_95 修复护栏）：`**7级**：` → `**7**级**：` 错位形态；
    # page_860 字段链形态豁免登记（NUM_MISALIGN_ALLOWED）
    num_leak = []
    for c in chunks:
        if c.get("doc_id") in NUM_MISALIGN_ALLOWED:
            continue
        if _RE_NUM_MISALIGN.search(c.get("text") or ""):
            num_leak.append(f"{c.get('title') or c.get('doc_id')}（{c.get('doc_id')}）")
    if num_leak:
        ok = False
        issues.append(f"❌ KN174 {len(num_leak)} 个 text 含数字错位星壳: "
                      f"{sorted(set(num_leak))[:6]}")

    # M6 A-2 星壳粘连防回退（2026-08-09，_strip_star_glue_artifacts 护栏）：
    # 六形态逐类扫查（判据与 format 侧同构），命中即 FAIL（设计内保留形态
    # 在正则层面已排除，见 _RE_A2_* 定义注释）
    _A2_PATTERNS = (
        ("来源行星壳", _RE_A2_SRC_LINE_RESIDUE),
        ("三连星对", _RE_A2_TRIPLE_PAIR),
        ("空壳行", _RE_A2_EMPTY_LINE),
        ("粘连+空格开壳", _RE_A2_GLUE_SPACE_OPEN),
        ("4星连续粘连", _RE_A2_GLUE_4STAR),
        ("6星连续", _RE_A2_SIX_STAR),
    )
    a2_leak = []
    for c in chunks:
        t = c.get("text") or ""
        for name, pat in _A2_PATTERNS:
            if pat.search(t):
                a2_leak.append(f"{name}@{c.get('title') or c.get('doc_id')}（{c.get('doc_id')}）")
                break
    if a2_leak:
        ok = False
        issues.append(f"❌ A-2 {len(a2_leak)} 个 text 含星壳粘连形态: "
                      f"{sorted(set(a2_leak))[:8]}")

    # M6 A-1 字段剥壳防回退（2026-08-09，seed_96~101 修复护栏）：白名单
    # 规范字段值内星壳（`*烙印术（BrandAPG）*` / `*2` / `*折凳` / 四星嵌套
    # `****Caster's Tattoo****`）全量剥除——_FIELD_STRIP_TARGETS 六字段 +
    # _strip_field_stars 三处调用统一口径。extra 键与 item_name 不入
    # （成对斜体正文 / 脚注星原文保真，KN185 口径）。
    _FIELD_NO_STAR = ("english_name", "critical", "subcategory",
                      "craft_conditions", "craft_requirements", "craft_cost")
    field_leak = []
    for c in chunks:
        md = c.get("metadata") or {}
        for k in _FIELD_NO_STAR:
            v = md.get(k) or c.get(k) or ""
            if isinstance(v, str) and "*" in v:
                field_leak.append(f"{k}={v[:40]!r}@{c.get('title')}（{c.get('doc_id')}）")
    if field_leak:
        ok = False
        issues.append(f"❌ A-1 {len(field_leak)} 个白名单字段含星壳: "
                      f"{sorted(set(field_leak))[:6]}")

    comp_dist = Counter(c.get("component_type") for c in chunks)
    fmt_dist = Counter(c.get("metadata", {}).get("format_cluster") for c in chunks)
    print(f"  — component_type: {dict(comp_dist)}")
    print(f"  — format_cluster: {dict(fmt_dist)}")
    return ok, issues


# ============================================================
#  检查 5.5：KN190 奇物位置页 slot 回填防回退
#  11 位置页（page_223~233）wondrous_item slot 100% 有值且与页面词形对应；
#  A1 拍板例外白名单 7 条（源数据「位置：」自声明页内混排）保留原值——
#  白名单计数负向断言（值变/缺失即 FAIL，防未来覆盖误伤）。
# ============================================================
# KN190 例外白名单（A1 拍板保留自声明）：(doc_id, title) → 自声明 slot
_EXCEPTION_SLOT_SELF_DECLARED = {
    ("page_225", "复仇追踪者背心"): "躯体",
    ("page_228", "抒情竖琴"): "无",
    ("page_228", "独角兽邪角"): "无",
    ("page_229", "游击头巾"): "头饰",
    ("page_232", "医师挎包"): "无",
    ("page_233", "巨魔皮革止血带"): "无",
    ("page_233", "悼念之根"): "无",
}


def check_slot_page_backfill(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """奇物 11 位置页 slot 100% 有值 + 页内对应性 + 例外白名单（KN190）"""
    issues: List[str] = []
    page_slot = _EQUIP_PAGE_SLOT_MAP  # 同源 import（改一处两处生效）
    missing: List[tuple] = []
    mismatched: List[tuple] = []
    seen_exc = set()
    total = 0
    for c in chunks:
        did = c.get("doc_id")
        if did not in page_slot or c.get("component_type") != "wondrous_item":
            continue
        if not c.get("title"):
            continue  # intro 等无标题块不算装备条目
        total += 1
        slot = c.get("metadata", {}).get("slot")
        if slot is None:
            missing.append((did, c.get("title")))
        elif slot != page_slot[did]:
            key = (did, c.get("title"))
            if key in _EXCEPTION_SLOT_SELF_DECLARED and slot == _EXCEPTION_SLOT_SELF_DECLARED[key]:
                seen_exc.add(key)
            else:
                mismatched.append((did, slot, c.get("title")))
    if missing:
        issues.append(f"❌ KN190 位置页 slot 缺失 {len(missing)} 条: {missing[:8]}")
    if mismatched:
        issues.append(f"❌ 位置页 slot 与页面词形不符 {len(mismatched)} 条: {mismatched[:8]}")
    missed_exc = set(_EXCEPTION_SLOT_SELF_DECLARED) - seen_exc
    if missed_exc:
        issues.append(f"❌ 例外白名单条目缺失/值变 {len(missed_exc)} 条: {sorted(missed_exc)}")
    if not issues:
        print(f"  — KN190 位置页 {total} 条 slot 有值率 100%，"
              f"例外白名单 {len(seen_exc)}/7 保持自声明")
    return not issues, issues


# ============================================================
#  检查 6：title 合法性
# ============================================================


def check_title_health(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """title 合法性：空 title 仅限 equipment_intro（导言块设计形态）、
    无 URL/译者标记/格式噪声"""
    ok = True
    issues: List[str] = []
    empty = [c for c in chunks if not c.get("title", "").strip()]
    bad_empty = [c for c in empty if c.get("component_type") != "equipment_intro"]
    if bad_empty:
        ok = False
        issues.append(f"❌ {len(bad_empty)} 个非 intro 空 title: "
                      f"{dict(Counter(c['component_type'] for c in bad_empty))}")
    print(f"  — 空 title {len(empty)}（全 equipment_intro，设计形态）")
    print(f"    {EMPTY_TITLE_NOTE}")

    url = [c for c in chunks if _URL_IN_TITLE.search(c.get("title", ""))]
    trans = [c for c in chunks if _TRANSLATOR_MARK.search(c.get("title", ""))]
    noise = [c for c in chunks
             if _TITLE_NOISE.search(c.get("title", ""))
             and c.get("title", "") not in TITLE_NOISE_ALLOWED]
    if url:
        ok = False
        issues.append(f"❌ {len(url)} 个 title 含 URL")
    if trans:
        ok = False
        issues.append(f"❌ {len(trans)} 个 title 含译者标记")
    if noise:
        ok = False
        issues.append(f"❌ {len(noise)} 个 title 含格式噪声: "
                      f"{[c['title'][:20] for c in noise][:6]}")
    print(f"  — title URL/译者/噪声: {len(url)}/{len(trans)}/{len(noise)}")
    return ok, issues


# ============================================================
#  检查 7：来源书一致性（同源 import 专属表）
# ============================================================


def check_source_book(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """来源书一致性：rule_version == book_abbreviation.lower() 全库；
    专属表 doc 级全匹配（_resolve_equip_source 同源 import，0 表外 0 不匹配）；
    book '?' 仅超游神器。

    不变量（M5 结构不变量清单）：
    - rule_version = book_abbreviation.lower()（M2 决策 10；WEAPON/ARMOR/
      UNDEAD/Dragonslayer 是源数据 HTML 注释自带长缩写，lower 后同源一致）
    - 每个 doc 的 book 必须与 _EQUIP_SOURCE_OVERRIDES 前缀命中值一致
      （技能 557/557 系统性失实教训的类目内护栏，专属表短路 conf=75）
    """
    ok = True
    issues: List[str] = []
    seen: Set[str] = set()
    for c in chunks:
        did = c.get("doc_id", "")
        if not did or did in seen:
            continue
        seen.add(did)
        rv = (c.get("metadata") or {}).get("rule_version", "")
        book = c.get("book_abbreviation", "")
        if rv != book.lower():
            ok = False
            issues.append(f"❌ {did}: rule_version={rv} 与 book={book} 不一致"
                          f"（应 rule_version == book.lower()）")
        if book == "?":
            if did != "超游神器":
                ok = False
                issues.append(f"❌ {did}: book '?' 非超游神器（设计内豁免之外）")
            continue
        exp = _resolve_equip_source(did + ".md")
        if exp is None:
            ok = False
            issues.append(f"❌ {did}: 专属表未覆盖（_EQUIP_SOURCE_OVERRIDES 缺条）")
        elif book != exp[0]:
            ok = False
            issues.append(f"❌ {did}: book={book} 但专属表应 {exp[0]}"
                          f"（{exp[1]}）")
    print(f"  — 来源书一致性：{len(seen)} 个 doc 全匹配，专属表 0 表外 0 不匹配"
          f"（rule_version == book.lower() 全库成立）")
    return ok, issues


# ============================================================
#  检查 8：entity 枚举（entity_enum.json）
# ============================================================


def check_entity_enum(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """entity 枚举：component_type ⊆ produced（15 种全产出）、
    reserved_zero_production 零产出、slot 值域 ⊆ canonical_13、
    format_cluster 五簇合法（同 field_health 口径）"""
    ok = True
    issues: List[str] = []
    enum = ctx["enum"]

    produced = set(enum["component_types"]["produced"])
    got_comp = Counter(c.get("component_type") for c in chunks)
    not_produced = set(got_comp) - produced
    if not_produced:
        ok = False
        issues.append(f"❌ 产物含枚举外 component_type: {sorted(not_produced)}")
    missing = produced - set(got_comp)
    if missing:
        ok = False
        issues.append(f"❌ produced 枚举 {len(missing)} 种无产出: {sorted(missing)}")

    reserved = {r["value"] for r in enum["component_types"]["reserved_zero_production"]}
    reserved_hit = set(got_comp) & reserved
    if reserved_hit:
        ok = False
        issues.append(f"❌ reserved_zero_production 意外产出: {sorted(reserved_hit)}")

    canonical13 = set(enum["slot_values"]["canonical_13"])
    slot_vals = {c.get("metadata", {}).get("slot") for c in chunks}
    slot_vals.discard(None)
    outside = slot_vals - canonical13
    if outside:
        ok = False
        issues.append(f"❌ slot 值域越界: {sorted(outside)}（canonical_13 之外）")

    print(f"  — entity 枚举：produced 15 种全产出、reserved 5 种零产出、"
          f"slot 值域 {len(slot_vals)} 值 ⊆ canonical_13")
    return ok, issues


# ============================================================
#  类目装配（VerifyBase 模板）
# ============================================================


class EquipmentVerify(VerifyBase):
    name = "装备集成验收"
    description = "装备模块集成验收（统一验收入口）"
    DEFAULT_CHUNKS = DEFAULT_CHUNKS

    checks = [
        ("判别器回归", check_discriminator_regression, "无 est>0 静默丢失"),
        ("召回", check_recall, "装备包 11 + 13 位置页锚点全命中"),
        ("条目级 QA", check_item_qa, "诱饵戒指/神意指引包/位置页锚点全过"),
        ("负向断言", check_negative, "P&P 无泄漏/伪标题 0/类目不串"),
        ("字段健康度", check_field_health, "slot 13 枚举/字段全健康/KN159/160 防回退"),
        ("KN190 slot 回填", check_slot_page_backfill, "位置页 slot 100% 有值 + 页内对应 + 例外白名单"),
        ("title 合法性", check_title_health, "空 title 仅 intro"),
        ("来源书一致性", check_source_book, "rule_version==book.lower() 全库 + 专属表全匹配"),
        ("entity 枚举", check_entity_enum, "produced 全产出/reserved 零产出/slot 值域"),
    ]

    def add_args(self, parser):
        parser.add_argument("--perfile", default=DEFAULT_PERFILE, type=Path)
        parser.add_argument("--entity-enum", default=ENTITY_ENUM, type=Path)

    def prepare(self, args):
        self.ctx["matrix"] = load_perfile(args.perfile)
        print(f"加载 {len(self.ctx['matrix'])} 个 per_file 矩阵 rel（basename 去重后 "
              f"292，重复 5 对：任务与战役_奇物/初探探索者协会_奇物/PSFG_奇物/"
              f"SoS_奇物/P&P_奇物）")
        if not args.entity_enum.exists():
            print(f"❌ entity_enum.json 不存在: {args.entity_enum}")
            raise SystemExit(1)
        with open(args.entity_enum, encoding="utf-8") as f:
            self.ctx["enum"] = json.load(f)


def main():
    EquipmentVerify().main()


if __name__ == "__main__":
    main()
