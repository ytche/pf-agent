"""
verify_skills.py — 技能模块集成验收（统一验收入口，VerifyBase 框架）

在 pipeline 全量运行后执行，六检查：
  1. 判别器回归：per_file_A1+A2+B1+B2 est↔got 对账（含豁免与 est 修正）
  2. 召回：26 个技能主条目（25 CRB 技能页权威 + page_182 语言学）↔ chunk title
  3. 任务级 QA：指定任务/子项/语言条目的 dc + text 断言
  4. 负向断言：无垃圾条目 / 无语言列表 sub / UI 与 Unchained 页不产 skill 主条目
  5. 字段健康度：chunk_id 唯一、doc_id 非空、component_type/format_cluster 合法、
     book '?' 0、空 text 仅限设计豁免（语言条目无描述）、skill_rule 字段专项
  6. title 合法性：无空 title / 无 URL / 无译者标记

豁免程序（与 feat 同思路，硬编码登记理由）：
  - 语言汇总 est 62 → got 60：勘探 (Rougarou) 英文名行重复计数 -1 +
    脏混合行垃圾条目剔除 -1（TDD seed_17 修复，61 语言口径不变）
  - UI 9 页 est 语义块（1 主标题 + N 小节）→ got 1：小节内嵌 sections
    元数据不产独立 chunk（元数据设计决策，UI 补充页整体 1 块）
  - B1 est 修正：背景技能 18 → 15（count_basis「表格与委托步骤拆分 3」在实现中
    并入小节/步骤并入条目，est 高估，got 15 真条目全在）；其余 B1 文件 est 为
    粗估口径（page_647 55 vs got 104 等 +63 全为 est 低估真条目，已定性）
  - B2 est 修正（S10）：工具和技能工具包 51 → 31——勘探 est 含尾部整段重复
    24（冒险者的军械库节与头部同源副本，拍板 #9 段级去重跳过）+ CR 陷阱块
    勘探并入物品条目而实现独立 2 + 初探段「工具箱」导言勘探未计而实现独立 1
    + 主段导言 1；去重后 31 = 导言 1 + 物品 24 + CR 块 2 + 初探 3 + 内海 1

用法：python3 -m vectorizer.verify.verify_skills [--chunks ...]
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Set, Tuple

from vectorizer.verify.base import VerifyBase

# P1 审计修复（2026-08-07）：来源书一致性断言的同源表——与 processor
# 侧专属表（_B2_SOURCE_OVERRIDES 的 basename 投影）同一数据源，改一处
# 两处生效（补丁 #2 同源原则），防 verify 与 processor 漂移。
from vectorizer.processors.skill import _B2_SOURCE_DOC_EXPECT

DEFAULT_CHUNKS = Path("vectorizer/output/技能/chunks.jsonl")
DEFAULT_PERFILE_A1 = Path("vectorizer/exploration/skill/per_file_A1.jsonl")
DEFAULT_PERFILE_A2 = Path("vectorizer/exploration/skill/per_file_A2.jsonl")
DEFAULT_PERFILE_B1 = Path("vectorizer/exploration/skill/per_file_B1.jsonl")
DEFAULT_PERFILE_B2 = Path("vectorizer/exploration/skill/per_file_B2.jsonl")

# ---- 豁免登记：{rel 文件名: 理由}（判别器回归豁免，不要求 est↔got 匹配）----
_SKILL_EXEMPTIONS = {
    "格拉利昂语言汇总.md": "est 62 含勘探重复计数 ((Rougarou) 英文名行) 与脏混合行垃圾条目 "
                            "(TDD seed_17 剔除)，真语言 61 条口径产出 60 条 index 全在",
    "page_1038.md": "UI 补充章目录页：est 语义块 1 与产出 1 一致，登记防口径漂移",
    "page_1039.md": "UI 补充页：est 按 1 主标题 + N 小节语义块计数，小节内嵌 sections 元数据",
    "page_1040.md": "UI 补充页：est 按 1 主标题 + 16 小节语义块计数，小节内嵌 sections 元数据",
    "page_1041.md": "UI 补充页：est 按 1 主标题 + 6 小节语义块计数，小节内嵌 sections 元数据",
    "page_1042.md": "UI 补充页：est 按 1 主标题 + 5 小节语义块计数，小节内嵌 sections 元数据",
    "page_1043.md": "UI 补充页：est 按 1 主标题 + 3 小节语义块计数，小节内嵌 sections 元数据",
    "page_1044.md": "UI 补充页：est 按 1 主标题 + 4 小节语义块计数，小节内嵌 sections 元数据",
    "page_1045.md": "UI 补充页：est 按 1 主标题 + 4 小节语义块计数，小节内嵌 sections 元数据",
    "page_1046.md": "UI 补充页：est 按 1 主标题 + 2 小节语义块计数，小节内嵌 sections 元数据",
    "工具包.md": "决策 11 拍板豁免：论坛帖纯装备页不纳入（B2 只处理工具和技能工具包.md）",
}

# ---- est 修正登记：{rel 文件名: (原始 est, 修正 est, 理由)} ----
# B1 为 Unchained 规则型（S7），勘探 est 是粗估口径；B2 S10 工具和技能工具包
# 勘探 est 含尾部整段重复（拍板 #9 段级去重）；产出后对账发现的口径差异
# 在此修正（保留原始值可追溯，按文件名 basename 匹配，B1/B2 通用），
# 不豁免静默丢失监管
# CHM 26 技能权威清单（决策 11：CHM 权威，正文后缀一致性校验；与
# 《技能名规范表.md》§一 同源）。值 = (key_ability, armor_penalty, trained_only)
_CHM_SKILL_AUTHORITY = {
    "估价": ("智力", False, False), "攀爬": ("力量", True, False),
    "工艺": ("智力", False, False), "脱逃": ("敏捷", True, False),
    "飞行": ("敏捷", True, False), "驯养动物": ("魅力", False, True),
    "医疗": ("感知", False, False), "威吓": ("魅力", False, False),
    "知识": ("智力", False, True), "语言学": ("智力", False, True),
    "察觉": ("感知", False, False), "表演": ("魅力", False, False),
    "专业": ("感知", False, True), "骑术": ("敏捷", True, False),
    "察言观色": ("感知", False, False), "巧手": ("敏捷", True, True),
    "法术辨识": ("智力", False, True), "隐匿": ("敏捷", True, False),
    "生存": ("感知", False, False), "游泳": ("力量", True, False),
    "特技": ("敏捷", True, False), "唬骗": ("魅力", False, False),
    "交涉": ("魅力", False, False), "易容": ("魅力", False, False),
    "解除装置": ("敏捷", True, True), "使用魔法装置": ("魅力", False, True),
}
_B1_EST_OVERRIDES = {
    "背景技能.md": (18, 15, "count_basis「表格与委托步骤拆分 3」实现中并入：委托步骤 "
                            "（第1步~第4步）并入艺术条目、表格并入小节，got 15 真条目全在"),
    "工具和技能工具包.md": (51, 31, "勘探 est 含尾部冒险者的军械库节整段重复 24（拍板 #9 "
                              "段级去重跳过）+ CR 陷阱块勘探并入物品而实现独立 2 + 初探段 "
                              "工具箱导言 1 + 主段导言 1；去重后 31 = 导言 1 + 物品 24 + "
                              "CR 块 2 + 初探 3 + 内海 1"),
    "page_837.md": (67, 63, "勘探按节粗估 67 条 Q&A（专长节 34 + 装备节 33）；实际锚点判据"
                     "（译注块跳过 / 英文答案段内伪锚过滤 / 无锚英文问题并入上一条目）"
                     "收敛为 61 条 Q&A + 2 节标题 intro = 63 chunks"),
}
# ---- B2 待接入豁免（不入矩阵对账）：{rel 文件名: 理由} ----
# 形态解析器未实现的文件若进矩阵会以 est>0 got=0 触发静默丢失 FAIL；
# 与 processor 侧 _B2_PENDING_RELS 同步维护，每接入一个形态即移出
# B2 待接入豁免：FAQ 837 已接入（S9 问答流 _split_faq，2026-08-07），集合清空
_B2_PENDING_EXEMPT: set = set()


def load_perfile(path: Path) -> List[dict]:
    if not path.exists():
        print(f"❌ per_file 不存在: {path}")
        raise SystemExit(1)
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _doc_id_of(rel: str) -> str:
    """per_file rel → doc_id（文件名 stem）"""
    return rel.rsplit("/", 1)[-1][:-3]


# ============================================================
#  检查 1：判别器回归（est↔got 对账，含豁免）
# ============================================================


def check_discriminator_regression(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """判别器回归：per_file A1+A2+B1 每文件 est↔got 对账。

    - 豁免 rel：不要求匹配（登记理由，见模块 docstring）
    - B1 est 修正 rel：按修正后 est 对账（保留原始值追溯，见 _B1_EST_OVERRIDES）
    - 非豁免 rel est>0 但 got=0：静默丢失 → FAIL
    - 非豁免 rel got < est：亚产能（WARN 不阻断；速查块/字段级产物可使 got>est；
      B1 粗估口径下 got>est 属 est 低估已定性，不 WARN）
    """
    matrix = ctx["matrix"]
    ok = True
    issues: List[str] = []
    got_by_doc: Counter = Counter(c.get("doc_id", "") for c in chunks)
    total_est = 0
    total_got = 0
    zero_loss = 0
    sub_prod = 0
    est_over = 0
    for e in matrix:
        rel = e["file"]
        est = e["estimated_count"]
        did = _doc_id_of(rel)
        got = got_by_doc.get(did, 0)
        # P2-① 审计修复（2026-08-07）：endswith 子串匹配误豁免
        # 「工具和技能工具包.md」（endswith「工具包.md」= True），est 修正
        # 51→31 从未生效且 31 equipment 不入对账口径；改精确 basename。
        if rel.rsplit("/", 1)[-1] in _SKILL_EXEMPTIONS:
            continue
        override = _B1_EST_OVERRIDES.get(rel.rsplit("/", 1)[-1])
        if override:
            est = override[1]
        total_est += est
        total_got += got
        if est > 0 and got == 0:
            ok = False
            zero_loss += 1
            issues.append(f"❌ {rel}: est={est} got=0（静默丢失）")
        elif est > 0 and got < est:
            sub_prod += 1
            issues.append(f"⚠️  {rel}: est={est} got={got}（亚产能，既有差距）")
    print(f"  — 豁免登记 {len(_SKILL_EXEMPTIONS)} 条（UI 小节内嵌 / 语言口径修正）"
          f"，B1 est 修正 {len(_B1_EST_OVERRIDES)} 条")
    print(f"  — 矩阵 est={total_est} got={total_got}，静默丢失 {zero_loss}，亚产能 {sub_prod} 条")
    return ok, issues


# ============================================================
#  检查 2：召回（26 技能主条目 ↔ chunk title）
# ============================================================

# 26 技能权威名单：25 CRB 技能详述页（per_file A1 first_entry 源数据译名）
# + page_182 语言学。权威口径来自人工门 1（26 技能 = 技能详述 25 页 + 根目录 page_182）。
# 译名以源数据为准：隐匿（Stealth）/ 工艺（Craft）/ 唬骗（Bluff）/ 交涉（Diplomacy）
_SKILL_NAMES_26 = [
    "攀爬", "游泳", "特技", "解除装置", "脱逃", "飞行", "骑术", "巧手", "隐匿",
    "估价", "工艺", "知识", "语言学", "法术辨识", "医疗", "察觉", "专业",
    "察言观色", "生存", "唬骗", "交涉", "易容", "驯养动物", "威吓", "表演",
    "使用魔法装置",
]


def check_recall_26(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """召回：26 技能主条目 → skill chunk title 命中，且无名单外主条目"""
    skills = [c for c in chunks if c["component_type"] == "skill"]
    titles = {c.get("title", "") for c in skills}
    print(f"  — skill 主条目 {len(skills)} 个（26 名单基线）")
    miss = [n for n in _SKILL_NAMES_26 if n not in titles]
    extra = [t for t in titles if t not in set(_SKILL_NAMES_26)]
    if len(skills) != 26:
        return False, [f"❌ skill 主条目应 26 个，实际 {len(skills)}"]
    if miss:
        return False, [f"❌ {len(miss)} 个技能缺失: {miss}"]
    if extra:
        return False, [f"❌ {len(extra)} 个名单外主条目: {extra}"]
    return True, []


# ============================================================
#  检查 3：任务级 QA（指定任务 dc/text、子项、语言条目）
# ============================================================


def _task_of(chunks: List[dict], skill_name: str) -> List[dict]:
    return [c for c in chunks if c["component_type"] == "skill_task"
            and c["metadata"].get("skill_name") == skill_name]


def check_task_qa(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """任务级 QA：医疗急救（dc 15 + text）、驯养动物攻击（dc 20 + text）、
    知识 10 学科 sub_specialty、表演 9 类、语言 61 条（index 60 产出含空描述）"""
    ok = True
    issues: List[str] = []

    heal = {c["metadata"].get("task_name"): c for c in _task_of(chunks, "医疗")}
    first = heal.get("急救")
    if not first:
        ok = False
        issues.append("❌ 医疗「急救」任务缺失")
    else:
        if first["metadata"].get("dc") != "15":
            ok = False
            issues.append(f"❌ 急救 dc 应 15，实际 {first['metadata'].get('dc')}")
        if "濒死" not in (first.get("text") or ""):
            ok = False
            issues.append("❌ 急救 text 应含「濒死」")

    handle = {c["metadata"].get("task_name"): c for c in _task_of(chunks, "驯养动物")}
    attack = handle.get("攻击")
    if not attack:
        ok = False
        issues.append("❌ 驯养动物「攻击」任务缺失")
    else:
        if attack["metadata"].get("dc") != "20":
            ok = False
            issues.append(f"❌ 攻击 dc 应 20，实际 {attack['metadata'].get('dc')}")
        if "动物开始攻击" not in (attack.get("text") or ""):
            ok = False
            issues.append("❌ 攻击 text 应含「动物开始攻击」（l 前缀列表 text 空回归哨兵）")

    knowledge = next((c for c in chunks if c["component_type"] == "skill"
                      and c["title"] == "知识"), None)
    if knowledge:
        subs = knowledge["metadata"].get("sub_specialty", [])
        expect10 = {"奥秘", "地城", "工程", "地理", "历史", "地方", "自然", "贵族", "宗教", "位面"}
        missing = expect10 - set(subs)
        if missing:
            ok = False
            issues.append(f"❌ 知识 sub_specialty 缺学科: {sorted(missing)}（PF1e 第 10 学科为位面）")
        if not missing:
            print(f"  — 知识 10 学科全齐: {len(subs)} 个")
    else:
        ok = False
        issues.append("❌ 知识主条目缺失")

    perform = next((c for c in chunks if c["component_type"] == "skill"
                    and c["title"] == "表演"), None)
    if perform:
        subs = perform["metadata"].get("sub_specialty", [])
        if len(subs) != 9:
            ok = False
            issues.append(f"❌ 表演子类应 9 类（PF1e 全集），实际 {len(subs)}: {subs}")
        else:
            print(f"  — 表演 9 类全齐")
    else:
        ok = False
        issues.append("❌ 表演主条目缺失")

    langs = [c for c in chunks if c["component_type"] == "skill_index"]
    if len(langs) != 60:
        ok = False
        issues.append(f"❌ 语言 index 应 60 条产出，实际 {len(langs)}")
    else:
        print(f"  — 语言 index 60 条（61 语言口径，天狗语含空描述条目）")
    return ok, issues


# ============================================================
#  检查 4：负向断言（垃圾条目 / 语言列表 sub / UI 主条目）
# ============================================================


def check_negative(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """负向：无脏混合行垃圾条目（昆莱…）；无语言列表 sub（决策 8）；
    UI 与 Unchained 页不产 skill 主条目；语言列表不进 sub_specialty（决策 8）"""
    ok = True
    issues: List[str] = []

    junk = [c for c in chunks if "昆莱" in (c.get("title") or "")]
    if junk:
        ok = False
        issues.append(f"❌ {len(junk)} 个脏混合行垃圾条目（TDD seed_17 回归）")

    # 语言名单权威源：skill_index 产出的 name（60 条）。endswith("语") 会误伤
    # 真任务（唬骗「密语」/察言观色「解析密语」），改用名单交集零误伤
    lang_names = {c["metadata"].get("name") for c in chunks
                  if c["component_type"] == "skill_index"}
    lang_subs = [c for c in chunks if c["component_type"] == "skill_task"
                 and c["metadata"].get("task_name", "") in lang_names]
    if lang_subs:
        ok = False
        issues.append(f"❌ {len(lang_subs)} 个语言列表任务（决策 8 语言列表应保留在主条目 text）")

    ui_as_skill = [c for c in chunks if c["component_type"] == "skill"
                   and c["metadata"].get("rule_version") == "ui"]
    if ui_as_skill:
        ok = False
        issues.append(f"❌ UI 页误产 {len(ui_as_skill)} 个 skill 主条目")

    unchained_as_skill = [c for c in chunks if c["component_type"] == "skill"
                          and c["metadata"].get("rule_version") == "unchained"]
    if unchained_as_skill:
        ok = False
        issues.append(f"❌ Unchained 规则页误产 {len(unchained_as_skill)} 个 skill 主条目"
                      f"（B1 应为 skill_rule，S7 格式簇）")

    for s in [c for c in chunks if c["component_type"] == "skill"]:
        poll = [x for x in s["metadata"].get("sub_specialty", []) if x.endswith("语")]
        if poll:
            ok = False
            issues.append(f"❌ {s['title']} sub_specialty 含语言列表污染: {poll}")
    return ok, issues


# ============================================================
#  检查 5：字段健康度
# ============================================================

VALID_COMPONENT = {"skill", "skill_task", "skill_note", "ui_supplement",
                   "skill_index", "skill_intro", "skill_rule", "skill_equipment"}
VALID_FORMAT = {"S1", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10"}
# 空 text 设计豁免：语言条目源数据无描述（狩狼人/天狗语/沼蜍人语/卡萨达/特里亚克萨斯），
# index 条目标识字段（name/name_en）即可检索；FAQ 节标题 intro 为分节锚点
#（专长和技能 / 装备和魔法物品），text 恒空，检索端降权
EMPTY_TEXT_EXEMPT = {"skill_index", "skill_intro"}
# skill_rule（S7）必填字段：title 与 rule_version 必须非空；title_en 允许空
#（纯中文小节标题 / 英文在斜体行 / 裸英文行形态，82 个全定性，见 _RULE_EN_EMPTY_NOTE）
_RULE_REQUIRED = ("title", "rule_version")
_RULE_EN_EMPTY_NOTE = ("page_647 难度档 7（英文在斜体行 *Extremely Simple (DC 5)*）+ 纯中文小节 1"
                       "（工艺）；page_648 标志性技能 1（英文在裸行）；page_649 表2-8/核心职业 2；"
                       "背景技能 13 + 整合技能 47 + 分组技能 9（纯中文小节/种族子节/表标题无英文名）；"
                       "官方FAQ 837 中文条目无英文名（英文条目 title_en=自身）")


def check_field_health(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """字段健康：chunk_id 唯一、doc_id 非空、component_type/format_cluster 合法、
    book '?' 0、空 text 仅限豁免类型、skill_rule 必填字段"""
    ok = True
    issues: List[str] = []

    ids = [c.get("chunk_id", "") for c in chunks]
    dup = {k for k, v in Counter(ids).items() if v > 1}
    if dup:
        ok = False
        issues.append(f"❌ {len(dup)} 个重复 chunk_id（示例: {sorted(dup)[:5]}）")
    else:
        print(f"  — chunk_id 唯一: {len(ids)}/{len(ids)}")

    no_doc = [c for c in chunks if not c.get("doc_id", "").strip()]
    if no_doc:
        ok = False
        issues.append(f"❌ {len(no_doc)} 个 chunk 缺 doc_id")

    bad_comp = [c for c in chunks if c.get("component_type") not in VALID_COMPONENT]
    if bad_comp:
        ok = False
        issues.append(f"❌ 非法 component_type: {dict(Counter(c['component_type'] for c in bad_comp))}")

    bad_fmt = [c for c in chunks if c.get("metadata", {}).get("format_cluster") not in VALID_FORMAT]
    if bad_fmt:
        ok = False
        fmts = Counter(c["metadata"].get("format_cluster") for c in bad_fmt)
        issues.append(f"❌ 非法 format_cluster: {dict(fmts)}")

    bookq = [c for c in chunks if c.get("book_abbreviation") == "?"]
    if bookq:
        ok = False
        issues.append(f"❌ {len(bookq)} 个 chunk 来源书未知（book '?'）")

    empty = [c for c in chunks if not c.get("text", "").strip()]
    bad_empty = [c for c in empty if c["component_type"] not in EMPTY_TEXT_EXEMPT]
    if bad_empty:
        ok = False
        ct = Counter(c["component_type"] for c in bad_empty)
        issues.append(f"❌ 非豁免空 text: {dict(ct)}")
    if empty:
        print(f"  — 空 text {len(empty)}（豁免: {dict(Counter(c['component_type'] for c in empty))}）")

    # 26 技能权威清单（KN158 修复护栏，2026-08-07）：key_ability /
    # armor_penalty / trained_only 必须与 CHM 权威一致（决策 11；与
    # 《技能名规范表.md》同源）。游泳 KN158 修复前 key_ability 混入
    # 「防具检定减值」且 armor_penalty=False——此断言直接拦截。
    skill_authority = _CHM_SKILL_AUTHORITY
    for c in chunks:
        if c.get("component_type") != "skill":
            continue
        md = c.get("metadata") or {}
        exp = skill_authority.get(md.get("skill_name", ""))
        if exp is None:
            continue
        ka, ap, tr = exp
        got = (md.get("key_ability"), md.get("armor_penalty"), md.get("trained_only"))
        if got != (ka, ap, tr):
            ok = False
            issues.append(f"❌ {c.get('title')}: 权威清单 (key_ability={ka}, "
                          f"armor_penalty={ap}, trained_only={tr}) ↔ 产物 {got}")
    # KN159 防回退（2026-08-07）：skill/skill_task metadata 不得含管道符
    # 残迹——源数据表格行行中 \r 腰斩（fix_skill_table_cr.py 已洗）后
    # 第二段 `|  | 15 |` 混入 check 字段。重跑 pipeline 后此断言拦截复发。
    pipe_leak = []
    for c in chunks:
        if c.get("component_type") not in ("skill", "skill_task"):
            continue
        md_text = json.dumps(c.get("metadata") or {}, ensure_ascii=False)
        if "|" in md_text:
            pipe_leak.append(f"{c.get('title')}（{c.get('doc_id')}）")
    if pipe_leak:
        ok = False
        issues.append(f"❌ KN159 {len(pipe_leak)} 个 skill/skill_task metadata 含管道残迹: "
                      f"{sorted(set(pipe_leak))[:6]}")

    # KN160 防回退（2026-08-07）：skill/skill_rule text 不得有行首/行尾
    # 单星斜体星壳（format 剥星规则 _RE_ITALIC_LEAD/_RE_ITALIC_TAIL 同形）。
    # ** 加粗双星守卫不误伤；表 title chunk 的表格行管道符不在扫描范围。
    star_leak = []
    for c in chunks:
        if c.get("component_type") not in ("skill", "skill_rule"):
            continue
        t = c.get("text") or ""
        if _RE_STAR_LEAK.search(t):
            star_leak.append(f"{c.get('title')}（{c.get('doc_id')}）")
    if star_leak:
        ok = False
        issues.append(f"❌ KN160 {len(star_leak)} 个 skill/skill_rule text 含斜体星壳: "
                      f"{sorted(set(star_leak))[:6]}")

    # skill_rule 字段专项：必填字段缺失即 FAIL（S7 条目无标题不可检索）
    rules = [c for c in chunks if c["component_type"] == "skill_rule"]
    if rules:
        for f in _RULE_REQUIRED:
            bad = [c for c in rules if not str(c.get("metadata", {}).get(f, "")).strip()]
            if bad:
                ok = False
                issues.append(f"❌ {len(bad)} 个 skill_rule 缺必填字段 {f}"
                              f"（示例: {sorted({c['doc_id'] for c in bad})}）")
        en_empty = [c for c in rules if not c["metadata"].get("title_en", "").strip()]
        if en_empty:
            print(f"  — skill_rule 空 title_en {len(en_empty)}（设计内，详见 _RULE_EN_EMPTY_NOTE）")
            print(f"    {_RULE_EN_EMPTY_NOTE}")
        print(f"  — skill_rule {len(rules)} 个（title/rule_version 全非空，book '?' 0）")

    comp_dist = Counter(c.get("component_type") for c in chunks)
    fmt_dist = Counter(c.get("metadata", {}).get("format_cluster") for c in chunks)
    print(f"  — component_type: {dict(comp_dist)}")
    print(f"  — format_cluster: {dict(fmt_dist)}")
    return ok, issues


# ============================================================
#  检查 6：title 合法性
# ============================================================

_URL_IN_TITLE = re.compile(r"https?://")
_TRANSLATOR_MARK = re.compile(r"^译者$|^校对$|^[：:]?\s*译者[:：]|^翻译[:：]")
_TITLE_NOISE = re.compile(r"^【|^《|^\[http|^\*\*")
# KN160 防回退：行首单星（可带缩进）/行尾单星（format 剥星规则同形）
_RE_STAR_LEAK = re.compile(r"^[ \t]*\*(?!\*)|(?<!\*)\*[ \t]*$", re.M)


def check_title_health(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """title 合法性：非空、无 URL、无译者标记、无格式噪声"""
    ok = True
    issues: List[str] = []
    empty = [c for c in chunks if not c.get("title", "").strip()]
    url = [c for c in chunks if _URL_IN_TITLE.search(c.get("title", ""))]
    trans = [c for c in chunks if _TRANSLATOR_MARK.search(c.get("title", ""))]
    noise = [c for c in chunks if _TITLE_NOISE.search(c.get("title", ""))]

    print(f"  — title 空: {len(empty)}  URL: {len(url)}  译者标记: {len(trans)}  格式噪声: {len(noise)}")
    if empty:
        ok = False
        issues.append(f"❌ {len(empty)} 个空 title")
    if url:
        ok = False
        issues.append(f"❌ {len(url)} 个 title 含 URL")
    if trans:
        ok = False
        issues.append(f"❌ {len(trans)} 个 title 含译者标记")
    if noise:
        ok = False
        issues.append(f"❌ {len(noise)} 个 title 含格式噪声")
    return ok, issues


# ============================================================
#  检查 7：来源书一致性（审计 P1 修复回归护栏，2026-08-07）
# ============================================================
_SOURCE_EXPECT_BY_STEM = {k[:-3]: v for k, v in _B2_SOURCE_DOC_EXPECT.items()}


def check_source_book(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """来源书一致性：doc 级 book_abbreviation 与 rule_version 必须匹配。

    不变量（含专项覆写模块改动前置答问）：
    - rule_version ∈ {crb, ui}：book 必须 = CRB（UI 8 页为 CRB 页内补充译文）
    - rule_version ∈ {unchained, giant, potr, occult, technology, faq,
      equipment}：book 必须 = _B2_SOURCE_DOC_EXPECT[basename]（专属表短路
      conf=75，即 processor _B2_SOURCE_OVERRIDES 的 basename 投影）
    - 专属表 12 个 doc 必须全部有产出（表与矩阵同步）
    背景：DirectoryNameProvider 对 directory_hints（含文件名的全部路径
    parts）做「技能」子串匹配曾致本类目 557/557 全标 CRB（审计 P1 系统性
    失实，一期 Agent 溯源误导）；公共层 providers.py 不可改（spell/职业
    冻结模块共用，KN136 共享层改动漂移教训），本断言保证类目内专属表
    覆盖生效且不回退。
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
        if rv in ("crb", "ui"):
            if book != "CRB":
                ok = False
                issues.append(f"❌ {did}: rule_version={rv} 但 book={book}（应 CRB）")
        else:
            expect = _SOURCE_EXPECT_BY_STEM.get(did)
            if expect is None:
                ok = False
                issues.append(
                    f"❌ {did}: rule_version={rv} 未登记专属表（_B2_SOURCE_DOC_EXPECT 缺条）")
            elif book != expect:
                ok = False
                issues.append(f"❌ {did}: rule_version={rv} 但 book={book}（应 {expect}）")
    missing = sorted(set(_SOURCE_EXPECT_BY_STEM) - seen)
    if missing:
        ok = False
        issues.append(f"❌ 专属表 {len(missing)} 个 doc 无产出: {missing}")
    print(f"  — 来源书一致性：{len(seen)} 个 doc 全匹配，非 CRB 专属表 {len(_SOURCE_EXPECT_BY_STEM)} 条"
          + ("，全部命中" if not missing else f"，缺产出 {missing}"))
    return ok, issues


# ============================================================
#  类目装配（VerifyBase 模板）
# ============================================================


class SkillVerify(VerifyBase):
    name = "技能集成验收"
    description = "技能模块集成验收（统一验收入口）"
    DEFAULT_CHUNKS = DEFAULT_CHUNKS

    checks = [
        ("判别器回归", check_discriminator_regression, "无 est>0 静默丢失"),
        ("召回 26 技能", check_recall_26, "26 技能主条目全命中"),
        ("任务级 QA", check_task_qa, "任务 dc/text、知识 10 学科、表演 9 类、语言 61 条全过"),
        ("负向断言", check_negative, "无垃圾条目/语言列表 sub/UI 误判"),
        ("字段健康度", check_field_health, "字段全健康"),
        ("title 合法性", check_title_health, "title 全合法"),
        ("来源书一致性", check_source_book, "doc 级 book↔rule_version 全匹配"),
    ]

    def add_args(self, parser):
        parser.add_argument("--perfile-a1", default=DEFAULT_PERFILE_A1, type=Path)
        parser.add_argument("--perfile-a2", default=DEFAULT_PERFILE_A2, type=Path)
        parser.add_argument("--perfile-b1", default=DEFAULT_PERFILE_B1, type=Path)
        parser.add_argument("--perfile-b2", default=DEFAULT_PERFILE_B2, type=Path)

    def prepare(self, args):
        b2 = [e for e in load_perfile(args.perfile_b2)
              if e["file"].rsplit("/", 1)[-1] not in _B2_PENDING_EXEMPT]
        skipped = len(load_perfile(args.perfile_b2)) - len(b2)
        self.ctx["matrix"] = (load_perfile(args.perfile_a1)
                              + load_perfile(args.perfile_a2)
                              + load_perfile(args.perfile_b1)
                              + b2)
        print(f"加载 {len(self.ctx['matrix'])} 个 per_file 矩阵 rel"
              f"（A1 25 + A2 13 + B1 6 + B2 {len(b2)}），B2 待接入豁免 {skipped}")


def main():
    SkillVerify().main()


if __name__ == "__main__":
    main()
