"""processors/rule.py — 规则模块文件处理器（章节型新形态，M3 批次1 + M4 全量）

设计（M1/M2 人工门拍板后实现，2026-08-09）：
  - 复用 FileProcessor 模板方法（三钩子：build_chunk / resolve_source /
    infer_metadata）；chm_toc_path 由模板方法公共层按文件名查 md_mapping
    自动富化（旧式命名 CRB page_*.md 等在映射内）；
    organized 新命名规则文件（91 个）不在 md_mapping（2141 条 CHM 转换产物
    仅覆盖旧式命名）→ RuleBackfillChmTocPath 回填（M5 闸口首曝 1390 空，
    专长 1348 / 装备同源缺口，复用通用回填类，决策 A finalize 内建）
  - 扫描清单 = prepare_batches.json 全量 49 批（286 文件，M1 冻结集：
    core_rules 27 + rules 255 + retrain 1 + quick_reference 3）
  - 来源书识别 = _RULE_SOURCE_OVERRIDES 专属表短路（技能 3.1 教训：禁目录/
    文件名子串推导，KN165 同款）：M4 全量 4 组键（15 目录 + ~55 散件前缀 +
    2 特殊 '?' + 6 根级），逐文件来源行/`<!-- X-source -->` 注释定性，conf 75。
    公共层 providers.py 零改动（KN136）
  - manifest 双源注入（KN192 显式注解精神，不做运行时推导）：
      toc_group（4 枚举）← prepare_batches.json 每批 toc_group_map 显式注解
      format_cluster（S1~S6 规范名）/ doc_role ← rule_per_file.jsonl 显式
    覆盖 format 层首边界推导（hint 是权威）
  - component_type：M4 分派（doc_role=overview→rule_intro、index_table→
    rule_reference、S4→rule_table、S6→rule_entry、其余 rule_section 主）
  - 章节型形态（M2 §一）：无字段体系 → 不设 field_status；metadata 只注入
    5 规范键（toc_group/source/rule_version/format_cluster/component_type）
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from vectorizer.formats.rule import RuleFormat
from vectorizer.postprocess.feat_chain import BackfillChmTocPath
from vectorizer.processors import register
from vectorizer.processors.base import Chunk, FileProcessor
from vectorizer.registry_rule import RULE_CANONICAL_FIELDS
from vectorizer.sources.providers import SourceContext, SourceResolver

logger = logging.getLogger(__name__)


# ---- 输入范围（M4：prepare_batches.json 全量 49 批 = 286 文件）----

_ORGANIZED_ROOT = Path(__file__).resolve().parent.parent.parent / "pf_rules_md_organized"
_PREPARE_BATCHES_JSON = (
    Path(__file__).resolve().parent.parent / "exploration" / "rule" / "prepare_batches.json"
)
_RULE_PER_FILE_JSONL = (
    Path(__file__).resolve().parent.parent / "exploration" / "rule" / "rule_per_file.jsonl"
)


# ---- 来源书专属表（技能 3.1 教训：禁子串推导；M4 全量 4 组键）----
# rel 前缀 → (abbr, 中文名, 英文名)。四组：目录键（15 规则 L1 子目录）/
# 散件前缀键（规则/ 根下 ~55 书件，书名[缩写]_ 命名规范）/ 特殊 '?' 键
# （作祟汇总 KN196 / page_320 神祇扩展 KN195，装备 超游神器.md 先例）/
# 根级键（6：重训 UCa / 腐化 HA / 异能规则 OA / Unchained 导言 PU /
# UI 导言 / 第十季×2 PFS）。
# 口径约束（M4 逐文件来源行/`<!-- X-source -->` 注释定性，2026-08-09）：
#   - 跨模块同书同键同值：Unchained=PU 解放者手册（技能 3.1 同值）、
#     UI=极限诡道 / PA=位面冒险 / HA=恐怖冒险（装备先例，公共层同名
#     冲突键语义以模块专属表为准，KN165 口径）
#   - 撞键先例（装备已登记跨模块同名 KN）：AArch=动物档案（公共层
#     AArch=冒险之路：正义之怒）、RTT=远程战术工具箱（公共层 RTT=符文
#     战术工具箱）、CTT/FF/BM 同装备值、CotR=正义编年史（公共层 CotR=
#     皇冠之路）
#   - 散件键 abbr 以来源行为准（秘术选集=ArcaneAnthology 非缩写表 ArA、
#     荒野源始=WO 非缩写表「荒野起源」、异能国度=OR 非「异能领域」、
#     Belkzen=Hold of Orc Hordes 来源行原样）
#   - UCa=极限进阶（M3 拍板 KN194 已提交，M4 不回头）
_RULE_SOURCE_OVERRIDES = {
    # ---- 目录键（4 既有 + 15 规则 L1 子目录）----
    "核心规则 Core Rulebook【CRB】/": ("CRB", "核心规则书", "Core Rulebook"),
    "重训/": ("UCa", "极限进阶", "Ultimate Campaign"),
    "常用速查/": ("CRB", "核心规则书", "Core Rulebook"),
    "规则/ACG规则/": ("ACG", "进阶职业指南", "Advanced Class Guide"),
    "规则/APG规则/": ("APG", "进阶玩家指南", "Advanced Player's Guide"),
    "规则/GMG规则/": ("GMG", "游戏主持人指南", "GameMastery Guide"),
    "规则/HA规则/": ("HA", "恐怖冒险", "Horror Adventures"),
    "规则/MA规则/": ("MA", "神话冒险", "Mythic Adventures"),
    "规则/PA规则/": ("PA", "位面冒险", "Planar Adventures"),
    "规则/PFS专用/": ("PFS", "探索者协会", "Pathfinder Society"),
    "规则/UCa规则/": ("UCa", "极限进阶", "Ultimate Campaign"),
    "规则/UC规则/": ("UC", "极限战斗", "Ultimate Combat"),
    "规则/UI规则/": ("UI", "极限诡道", "Ultimate Intrigue"),
    "规则/UM规则/": ("UM", "极限魔法", "Ultimate Magic"),
    "规则/Unchained规则/": ("PU", "解放者手册", "Pathfinder Unchained"),
    "规则/UW规则/": ("UW", "极限荒野", "Ultimate Wilderness"),
    "规则/异能规则/": ("OA", "异能冒险", "Occult Adventures"),
    "规则/怪物规则/": ("怪物", "怪物规则", "Monster Rules"),
    # ---- 散件前缀键（规则/ 根下书件，来源行/注释权威定性）----
    "规则/CaC部属与伙伴_": ("CaC", "部属与伙伴", "Cohorts and Companions"),
    "规则/亡灵杀手手册_": ("UNDEAD", "亡灵杀手手册", "Undead Slayer's Handbook"),
    "规则/传奇编年史CoL_": ("CoL", "传奇编年史", "Chronicle of Legends"),
    "规则/位面行者手册PHH_": ("PHH", "位面行者手册", "Plane-Hopper's Handbook"),
    "规则/内海神殿_": ("IST", "内海神殿", "Inner Sea Temples"),
    "规则/内海诡道ISI_": ("ISI", "内海诡道", "Inner Sea Intrigue"),
    "规则/内海酒馆ISTav_": ("ISTav", "内海酒馆", "Inner Sea Taverns"),
    "规则/内海魔法ISM_": ("ISM", "内海魔法", "Inner Sea Magic"),
    "规则/再探死灵UndeadRevisited_": ("UndeadRevisited", "再探死灵", "Undead Revisited"),
    "规则/冒险之路AP_": ("AP", "冒险之路", "Adventure Path"),
    "规则/冒险者的军械库2_": ("AA2", "冒险者的军械库2", "Adventurer's Armory 2"),
    "规则/冒险者的军械库_": ("AA", "冒险者的军械库", "Adventurer's Armory"),
    "规则/初探探索者协会_": ("PSP", "探索者协会初探", "Pathfinder Society Primer"),
    "规则/动物档案AArch_": ("AArch", "动物档案", "Animal Archive"),
    "规则/卡蒂亚QJotE_": ("QJotE", "卡蒂亚，东方明珠", "Qadira, Jewel of the East"),
    "规则/商人货单MM_": ("MM", "商人货单", "Merchant's Manifest"),
    "规则/夜之血脉BotN_": ("BotN", "夜之血脉", "Blood of the Night"),
    "规则/对立协调CoR_": ("CoR", "对立协调", "Concordance of Rivals"),
    "规则/巨龙之遗LoD_": ("LoD", "巨龙之遗", "Legacy of Dragons"),
    "规则/巫团血脉BotC_": ("BotC", "巫团血脉", "Blood of the Coven"),
    "规则/废土子民PotW_": ("PotW", "废土子民", "People of the Wastes"),
    "规则/异能国度OR_": ("OR", "异能国度", "Occult Realms"),
    "规则/异能奥秘OM_": ("OM", "异能奥秘", "Occult Mysteries"),
    "规则/异能源始OO_": ("OO", "异能源始", "Occult Origins"),
    "规则/异能选集PA_": ("PsyA", "异能选集", "Psychic Anthology"),
    "规则/怪物召唤者手册MSH_": ("MSH", "怪物召唤者手册", "Monster Summoner's Handbook"),
    "规则/恶魔猎人手册_": ("DHH", "恶魔猎人手册", "Demon Hunter's Handbook"),
    "规则/惊骇国度HR_": ("HR", "惊骇国度", "Horror Realms"),
    "规则/惧怖冒险HA_": ("HA", "恐怖冒险", "Horror Adventures"),
    "规则/月之血脉BotM_": ("BotM", "月之血脉", "Blood of the Moon"),
    "规则/极限荒野UW_": ("UW", "极限荒野", "Ultimate Wilderness"),
    "规则/构装体手册CH_": ("CH", "构装体手册", "Construct Handbook"),
    "规则/格拉里昂的秽邪勇士_": ("CoC", "秽邪勇士", "Champions of Corruption"),
    "规则/正义编年史_": ("CotR", "正义编年史", "Chronicle of the Righteous"),
    "规则/武器大师手册_": ("WEAPON", "武器大师手册", "Weapon Master's Handbook"),
    "规则/水下冒险AA_": ("AqA", "水下冒险", "Aquatic Adventures"),
    "规则/永罪之书_": ("BotD", "永罪之书", "Book of the Damned"),
    "规则/法术荒疫_哈罗牌手册THH": ("THH", "哈罗牌手册", "The Harrow Handbook"),
    "规则/皇庭英豪HotHC_": ("HotHC", "皇庭英豪", "Heroes of the High Court"),
    "规则/秘术选集ArcaneAnthology_": ("ArcaneAnthology", "秘术选集", "Arcane Anthology"),
    "规则/第一世界TFWRotF_": ("TFWRotF", "第一世界，妖精之国", "The First World, Realm of the Fey"),
    "规则/第一世界的遗产LotFW_": ("LotFW", "第一世界的遗产", "Legacy of the First World"),
    "规则/荒野源始WO_": ("WO", "荒野源始", "Wilderness Origins"),
    "规则/药剂与毒药P&P_": ("P&P", "药剂与毒药", "Potions and Poisons"),
    "规则/贝尔克泽恩BHotOH_": ("BHotOH", "贝尔克泽恩，兽人部落之地", "Belkzen, Hold of Orc Hordes"),
    "规则/近战战术工具箱CTT_": ("CTT", "近战战术工具箱", "Melee Tactics Toolbox"),
    "规则/远程战术工具箱RTT_": ("RTT", "远程战术工具箱", "Ranged Tactics Toolbox"),
    "规则/遥远世界DS_": ("DS", "遥远世界", "Distant Shores"),
    "规则/邪恶特务AoE_": ("AoE", "邪恶特务", "Agents of Evil"),
    "规则/门徒教义DD_": ("DD", "门徒教义", "Disciple's Doctrine"),
    "规则/阴招战术工具箱DTT_": ("DTT", "阴招战术工具箱", "Dirty Tactics Toolbox"),
    "规则/魔宠手记FF_": ("FF", "魔宠手记", "Familiar Folio"),
    "规则/黑市指南BM_": ("BM", "黑市指南", "Black Markets"),
    # ---- 特殊 '?' 键（设计保留，装备 超游神器.md 先例）----
    "规则/作祟汇总": ("?", "未知", "Unknown"),
    "规则/page_320": ("?", "未知", "Unknown"),
    # ---- 根级键（CHM TOC 归属定性）----
    "page_159": ("UCa", "极限进阶", "Ultimate Campaign"),
    "page_1495": ("HA", "恐怖冒险", "Horror Adventures"),
    "page_314": ("OA", "异能冒险", "Occult Adventures"),
    "page_645": ("PU", "解放者手册", "Pathfinder Unchained"),
    "page_732": ("UI", "极限诡道", "Ultimate Intrigue"),
    "第十季": ("PFS", "探索者协会", "Pathfinder Society"),
}
# 长前缀优先（后续 M4 增加 `规则/` 下各书长前缀时保持序）；同长按字典序
_RULE_SOURCE_ORDER: tuple = tuple(
    sorted(_RULE_SOURCE_OVERRIDES, key=lambda p: (-len(p), p))
)


def _resolve_rule_source(rel: str) -> Optional[tuple]:
    """专属表短路（rel 前缀，长前缀优先）：rel → (abbr, cn, en)"""
    for prefix in _RULE_SOURCE_ORDER:
        if rel.startswith(prefix):
            return _RULE_SOURCE_OVERRIDES[prefix]
    return None


# ---- format_cluster_hint 短格式 → 规范簇名（rule_per_file.jsonl 权威）----

_CLUSTER_ALIAS = {
    "S1": "s1_heading_tree", "S2": "s2_bold_title", "S3": "s3_bbs_star",
    "S4": "s4_table_page", "S5": "s5_prose", "S6": "s6_large_aggregate",
}

# ---- S6 超大型聚合子策略表（M4 形态勘察定稿 10 文件 4 子策略；2026-08-09
# 批次 A KN210/211/213 修正后 13 文件 6 子策略）----
# 单一启发式不可行（各文件形态差异大，扫描脚本量化证实），按文件显式注入：
#   comment_anchor（永罪之书×5 + 极限荒野UW）：`<!-- X-source -->` 注释 =
#     唯一条目边界，锚点后首个非空行 = 标题，条目内星壳小节/字段/头衔全并入；
#     KN210 修正：无锚点位置的星壳名字行（无中文括号中英混排）也判边界
#   entry_line（LotFW/废土 + 尸体贸易BM）：裸标题行（行尾 2 空格短行中英 /
#     中英括号锚）= 边界；跨行标题上行（纯中文短行）拼接；`****` 纯星分隔剥除
#   haunt（作祟汇总/OR）：星壳标题（「作祟：」前缀 / 闭壳中英括号 / 开星不闭
#     含英文括号）= 边界；字段行三形态并入；4 星引用注并入
#   bg_table（角色背景生成器）：闭壳词表外星壳 = 边界（表标题/阶段标题）；
#     表格行（d%/数字范围）与行内加粗步骤行并入；KN214 修正：跨行表格行
#     （开星不闭 + 紧邻下行）预处理拼回
#   god_table（page_320 神祇扩展，KN211）：表格行首列含拉丁 = 独立条目
#     （title=首列神名）；表头/分隔/无拉丁首列行/说明行并入
_RULE_S6_SHAPES: Dict[str, str] = {
    "规则/永罪之书_仪式": "comment_anchor",
    "规则/永罪之书_其他魔神神恩": "comment_anchor",
    "规则/永罪之书_地狱魔神神恩": "comment_anchor",
    "规则/永罪之书_末日荒原魔神神恩": "comment_anchor",
    "规则/永罪之书_深渊魔神神恩": "comment_anchor",
    "规则/第一世界的遗产LotFW_第一世界规则": "entry_line",
    "规则/废土子民PotW_废土规则": "entry_line",
    "规则/作祟汇总": "haunt",
    "规则/异能国度OR_神秘仪式与偶像": "haunt",
    "规则/UCa规则/角色背景生成器": "bg_table",
    # KN210/213（2026-08-09 批次 A）：极限荒野 UW-source 注释锚点条目页
    # （嵌套星壳条目标题 `**魔鬼鱼(**ANGLERFISH**)**`）→ comment_anchor；
    # 尸体贸易裸中英括号标题行（`亡灵雇员（Ghoulrunning）`）→ entry_line
    "规则/极限荒野UW_新动物伙伴": "comment_anchor",
    "规则/黑市指南BM_尸体贸易": "entry_line",
    # KN211（2026-08-09 批次 A）：page_320 神祇扩展整页表格 → god_table
    # （表格行首列含拉丁 = 独立条目 title=首列神名）
    "规则/page_320": "god_table",
}


def _resolve_s6_shape(rel: str) -> Optional[str]:
    """S6 子策略查表（rel 前缀 → shape，None = 非 S6 文件）"""
    for prefix, shape in _RULE_S6_SHAPES.items():
        if rel.startswith(prefix):
            return shape
    return None


def _load_rule_manifest() -> Dict[str, Dict[str, str]]:
    """加载批次 manifest → {rel: {toc_group?, format_cluster?, doc_role?}}

    双源显式注解（KN192 精神，M1 人工门固化后不做运行时推导）：
      - toc_group ← prepare_batches.json 每批 toc_group_map（键已去前缀 rel）
      - format_cluster / doc_role ← rule_per_file.jsonl（file 键带
        `pf_rules_md_organized/` 前缀，去前缀后同键）
    doc_role（rule_chapter/rule_detail/aggregation/overview/mixed/index_table/
    bbs_page）参与 component_type 分派（M4：overview→rule_intro、
    index_table→rule_reference）。
    """
    manifest: Dict[str, Dict[str, str]] = {}
    with open(_PREPARE_BATCHES_JSON, encoding="utf-8") as f:
        batches = json.load(f)
    for batch in batches:
        for rel, group in (batch.get("toc_group_map") or {}).items():
            manifest.setdefault(rel, {})["toc_group"] = group
    with open(_RULE_PER_FILE_JSONL, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            rel = rec["file"].removeprefix("pf_rules_md_organized/")
            hint = rec.get("format_cluster_hint")
            if hint:
                cluster = _CLUSTER_ALIAS.get(hint, hint)
                manifest.setdefault(rel, {})["format_cluster"] = cluster
            role = rec.get("doc_role")
            if role:
                manifest.setdefault(rel, {})["doc_role"] = role
    return manifest


RULE_MANIFEST: Dict[str, Dict[str, str]] = _load_rule_manifest()


def _load_rule_scan_rels() -> set:
    """加载全量批次扫描清单 → {rel}（49 批 = 286 文件，M4 扩全量）"""
    with open(_PREPARE_BATCHES_JSON, encoding="utf-8") as f:
        raw = json.load(f)
    rels = set()
    for batch in raw:
        for f in batch.get("files", []):
            rels.add(f.removeprefix("pf_rules_md_organized/"))
    if len(rels) != 286:
        raise RuntimeError(
            f"规则全量批次应为 286 文件（M1 人工门 1 冻结），实际 {len(rels)}"
        )
    # 专属表完整性自证：清单内每个文件必须可短路命中（漏表 = 来源失实，
    # 技能 3.1 教训的编译期等价物）
    miss = sorted(rel for rel in rels if _resolve_rule_source(rel) is None)
    if miss:
        raise RuntimeError(
            f"规则专属来源表缺失 {len(miss)} 文件（必须逐文件定性后补表）：{miss[:5]}"
        )
    # manifest 完整性自证：清单内每文件必须有 toc_group 注解（M2 §三 3.1
    # 归属表拍板：toc_group 只认 manifest，不认路径推导）
    no_group = sorted(rel for rel in rels if not RULE_MANIFEST.get(rel, {}).get("toc_group"))
    if no_group:
        raise RuntimeError(
            f"规则 manifest 缺 toc_group 注解 {len(no_group)} 文件：{no_group[:5]}"
        )
    return rels


RULE_SCAN_RELS: set = _load_rule_scan_rels()


def _rule_file_condition(file_path: Path) -> bool:
    """规则文件判断：文件 rel 在 M3 批次扫描清单内（27 文件）"""
    try:
        rel = file_path.resolve().relative_to(_ORGANIZED_ROOT)
    except ValueError:
        return False
    return str(rel) in RULE_SCAN_RELS


class RuleBackfillChmTocPath(BackfillChmTocPath):
    """chm_toc_path 空回填（organized 规则文件不在 md_mapping，91 文件 1390 chunk）。

    M5 闸口（--max-toc-empty 0）首次暴露；模拟验证 91/91 文件有来源信号
    （注释 `<!-- XX-source:源md路径:条目标题 -->` 87 + 来源行 `未整理 → X → Y`
    4），回填机制与专长 1348 / 装备同源缺口一致——复用通用类只覆写报告目录
    （装备 EquipmentBackfillChmTocPath 同构先例）。
    """

    # 报告目录（类属性，子类覆写防跨类目覆盖）
    DEFAULT_REPORT_DIR = Path("docs/规则")


class RuleProcessor(FileProcessor):
    """规则文件处理器（章节型：一节规则 1 chunk）"""

    # 决策 A：finalize 后处理链（顺序不可变）。B2~B4 旧设计认为 md_mapping
    # 自动富化已够（CRB 旧式命名在映射内）——M5 闸口暴露 organized 新命名
    # 91 文件 1390 chunk toc 空，装配回填步骤（只填缺失，幂等）
    POSTPROCESSORS = [RuleBackfillChmTocPath]

    @property
    def category(self) -> str:
        return "rule"

    def __init__(self, source_resolver: SourceResolver):
        super().__init__(source_resolver=source_resolver, format_handler=RuleFormat())

    def build_chunk(self, template: Chunk, item: dict) -> Chunk:
        """设置节标题、正文与组件类型（M4 分派，rule_section 为主 component）。

        分派规则（M4 逐文件定性，manifest doc_role/format_cluster 显式注解）：
          - doc_role=overview（章首导言）→ rule_intro（降权）
          - doc_role=index_table（速查索引表）→ rule_reference（降权）
          - format_cluster=s4_table_page（整页纯表格）→ rule_table
          - format_cluster=s6_large_aggregate（超大型聚合条目级）→ rule_entry
          - 其余正文节 → rule_section（主 component）
        """
        template.title = " ".join(str(item.get("title", "")).split())
        template.text = item.get("text", "")
        man = RULE_MANIFEST.get(getattr(self, "_current_rel", ""), {})
        doc_role = man.get("doc_role", "")
        cluster = man.get("format_cluster", item.get("format_cluster", ""))
        if doc_role == "overview":
            ct = "rule_intro"
        elif doc_role == "index_table":
            ct = "rule_reference"
        elif cluster == "s4_table_page":
            ct = "rule_table"
        elif cluster == "s6_large_aggregate":
            ct = "rule_entry"
        else:
            ct = "rule_section"
        template.component_type = ct
        return template

    def process(self, file_path: Path) -> list:
        """记录当前 rel 供 infer_metadata 查 manifest（toc_group/format_cluster）；
        并将 manifest hint 注入 format 实例（s5_prose 时切分走无边界分支——
        游戏范例角色名星壳行不切分，M3 +23 误切教训）"""
        try:
            rel = str(file_path.resolve().relative_to(_ORGANIZED_ROOT))
        except ValueError:
            rel = ""
        self._current_rel = rel
        self.format.format_cluster_hint = RULE_MANIFEST.get(rel, {}).get(
            "format_cluster")
        self.format.s6_shape = _resolve_s6_shape(rel)
        return super().process(file_path)

    def resolve_source(self, chunk: Chunk, ctx: SourceContext, item: dict) -> Chunk:
        """解析来源书：专属表短路（M3 27 文件全命中，100% 覆盖）。

        技能 3.1 教训（KN165）：公共层 DirectoryNameProvider 对含「核心规则」
        等词的目录必子串误标，共享链在进入前短路（M1 拍板口径）。
        """
        try:
            rel = str(ctx.file_path.resolve().relative_to(_ORGANIZED_ROOT))
        except ValueError:
            rel = ""
        hit = _resolve_rule_source(rel)
        if hit:
            chunk.book_abbreviation, chunk.book_name_cn, chunk.book_name_en = hit
            chunk.source_confidence = 75
            return chunk
        # 专属表外（M4 各书展开前的漏网防御）：共享链兜底
        result = self.source_resolver.resolve(ctx)
        chunk.book_abbreviation = result.book_abbreviation
        chunk.book_name_cn = result.book_name_cn
        chunk.book_name_en = result.book_name_en
        chunk.source_confidence = result.confidence
        return chunk

    def infer_metadata(self, chunk: Chunk, item: dict) -> Chunk:
        """组装 metadata 5 规范键（章节型无字段体系，不设 field_status）。

        toc_group / format_cluster 均来自 manifest 显式注解（hint 是权威，
        覆盖 format 层首边界推导——KN192 精神）；source 原文引用块（M3 源
        数据无 `> 来源：` 块）为空串保留。
        """
        manifest = RULE_MANIFEST.get(getattr(self, "_current_rel", ""), {})
        chunk.metadata = {
            "toc_group": manifest.get("toc_group", ""),
            "source": "",
            "rule_version": chunk.book_abbreviation.lower(),
            "format_cluster": manifest.get(
                "format_cluster", item.get("format_cluster", "")),
            "component_type": chunk.component_type,
        }
        return chunk


register("rule", RuleProcessor, _rule_file_condition)
