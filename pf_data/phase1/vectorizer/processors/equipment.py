"""processors/equipment.py — 装备/魔法物品文件处理器

设计（2026-08-08，装备元数据设计 §二~§四 + 人工门 1/2 拍板后实现）：
  - 复用 FileProcessor 模板方法（三钩子：build_chunk / resolve_source / infer_metadata）
  - 扫描清单 = prepare_batches.json 批次 P11~P19（223 文件，M3 批次 1 全部）
  - 来源书识别 = _EQUIP_SOURCE_OVERRIDES 专属表短路（技能 3.1 教训：禁目录/文件名
    子串推导，KN165）：88 个前缀 → (abbr, cn, en)，conf 75。公共层 providers.py
    只做纯新增键（SOURCE_BOOK_ABBREVIATIONS 只加不改成），冲突键（RTT/UI/AArch/
    FoB/PotR/HoG 等跨模块同名）不动公共层（KN136），由专属表短路自带正确值。
  - component_type：文件级默认（_EQUIP_FILE_COMPONENT，子目录语义）+ 条目级
    强信号覆盖（damage/critical → weapon；护甲加值等 → armor；slot → wondrous_item）
  - rule_version = book_abbreviation 小写（值域 = 书缩写全集，M2 决策 10）
  - 字段归一：formats 层 fields（规范键 + extra 保真键）→ metadata 规范键 +
    metadata.extra（低频散字段原文保真，§二 2.5）+ field_status 三态
  - POSTPROCESSORS = toc 回填（通用件子类覆写报告目录到 docs/装备/）
"""

import json
import logging
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from vectorizer.formats.equipment import EquipmentFormat
from vectorizer.postprocess.feat_chain import BackfillChmTocPath
from vectorizer.processors import register
from vectorizer.processors.base import Chunk, FileProcessor
from vectorizer.processors.feat import _feat_source_from_content
from vectorizer.registry_equipment import (
    ALL_EQUIP_FIELD_LABELS,
    EQUIP_COMPONENT_TYPES,
    EQUIP_LABEL_TO_KEY,
    EQUIP_SLOT_VALUES,
)
from vectorizer.sources.providers import SourceContext, SourceResolver, SourceResult

logger = logging.getLogger(__name__)


# ---- 输入范围（M3 批次 1：prepare_batches.json 的 P11~P19 = 223 文件）----
_ORGANIZED_ROOT = Path(__file__).resolve().parent.parent.parent / "pf_rules_md_organized"
_PREPARE_BATCHES_JSON = (
    Path(__file__).resolve().parent.parent / "exploration" / "equipment" / "prepare_batches.json"
)

# 来源书专属表（KN165 落地，2026-08-08 逐文件核验；2026-08-09 M4 批次 2
# 增 74 页键）：
# rel 前缀 → (abbr, 中文名, 英文名)。覆盖 P1+P2 全部 297 文件（88 前缀 + 74 页键）。
# 缩写来源优先级：源数据 HTML 注释（`<!-- XXX-source:`）> `> 来源：` 行括号缩写
# > 官方缩写；模块内同名冲突已拍板区分（登记 KN）：
#   - MM=商人货单（Merchant's Manifest）/ MMG=魔法市集指南（Magical Marketplace）
#   - AA=冒险者的军械库（技能先例）/ AqA=水下冒险（Aquatic Adventures）
#   - PA=位面冒险（公共层权威）/ PsyA=异能选集（Psychic Anthology）
#   - PotS=沙之子民 / PoS=繁星子民（People of the Stars）
#   - HoG=格拉里昂的英雄 / HaG=格拉里昂的半身人
# 跨模块同名（chunk 级无冲突，检索端按类目过滤，登记 KN）：AArch=动物档案
# （公共层 AArch=冒险之路：正义之怒）、RTT=远程战术工具箱（公共层误标符文）、
# UI=极限诡道（公共层=极限异能）、FoB=均衡信念（公共层=信仰之书）、
# PotR=河域子民（技能同款：河域之民）。
# 注释/来源行自带长缩写（WEAPON/ARMOR/UNDEAD/Dragonslayer）保持同源一致。
_EQUIP_SOURCE_OVERRIDES = {
    "PlanesOfPowerPoP": ("PoP", "万界之力", "Planes of Power"),
    "QGthE": ("QGthE", "卡蒂亚，通向东方的大门", "Qadira, Gateway to the East"),
    "Worldscape": ("WS", "PF官方漫画Worldscape", "Worldscape"),
    "位面行者手册PHH": ("PHH", "位面行者手册", "Plane-Hopper's Handbook"),
    "元素血脉BotE": ("BotE", "元素血脉", "Blood of the Elements"),
    "内海世界指南ISWG": ("ISWG", "内海世界指南", "Inner Sea World Guide"),
    "内海战斗ISC": ("ISC", "内海战斗", "Inner Sea Combat"),
    "内海海盗PIS": ("PIS", "内海海盗", "Pirates of the Inner Sea"),
    "内海神殿": ("IST", "内海神殿", "Inner Sea Temples"),
    "内海种族ISR": ("ISR", "内海种族", "Inner Sea Races"),
    "内海舰船": ("ISS", "内海舰船", "Ships of the Inner Sea"),
    "内海诡道ISI": ("ISI", "内海诡道", "Inner Sea Intrigue"),
    "内海诸神ISG": ("ISG", "内海诸神", "Inner Sea Gods"),
    "内海骑士KIS": ("KIS", "内海骑士", "Knights of the Inner Sea"),
    "内海魔法ISM": ("ISM", "内海魔法", "Inner Sea Magic"),
    "再探经典宝藏CTR": ("CTR", "再探经典宝藏", "Classic Treasures Revisited"),
    "传奇编年史CoL": ("CoL", "传奇编年史", "Chronicle of Legends"),
    "冒险之路AP": ("AP", "冒险之路", "Adventure Path"),
    "动物档案AArch": ("AArch", "动物档案", "Animal Archive"),
    "商人货单MM": ("MM", "商人货单", "Merchant's Manifest"),
    "地狱骑士之道PotH": ("PotH", "地狱骑士之道", "Path of the Hellknight"),
    "塔尔多TEoG": ("TEoG", "塔尔多，荣光荡漾之地", "Taldor, Echoes of Glory"),
    "夜之血脉BotN": ("BotN", "夜之血脉", "Blood of the Night"),
    "奈多": ("NLS", "奈多，阴影之地", "Nidal, Land of Shadows"),
    "安多安ASoL": ("ASoL", "安多安，自由之魂", "Andoran, Spirit of Liberty"),
    "巨人再临GR": ("GR", "巨人再临", "Giants Revisited"),
    "巫团血脉BotC": ("BotC", "巫团血脉", "Blood of the Coven"),
    "幽暗地域英雄HotD": ("HotD", "幽暗地域英雄", "Heroes of the Darklands"),
    "异能选集PA": ("PsyA", "异能选集", "Psychic Anthology"),
    "敌手指南RM": ("RM", "敌手指南", "Rival Guide"),
    "月之血脉BotM": ("BotM", "月之血脉", "Blood of the Moon"),
    "格拉里昂的混种": ("BoG", "格拉里昂的混种", "Bastards of Golarion"),
    "格拉里昂的精灵": ("EoG", "格拉里昂的精灵", "Elves of Golarion"),
    "格拉里昂的纯洁勇士": ("CoP", "纯洁勇士", "Champions of Purity"),
    "格拉里昂的英雄HoG": ("HoG", "格拉里昂的英雄", "Heroes of Golarion"),
    "位面冒险PA": ("PA", "位面冒险", "Planar Adventures"),
    "元素大师手册EMH": ("EMH", "元素大师手册", "Elemental Master's Handbook"),
    "冒险者指南AG": ("AG", "冒险者指南", "Adventurer's Guide"),
    "冒险者的军械库": ("AA", "冒险者的军械库", "Adventurer's Armory"),
    "反派法典VC": ("VC", "恶棍志", "Villain Codex"),
    "巨人猎手手册": ("GIANT", "巨人猎手手册", "Giant Slayer's Handbook"),
    "怪物召唤者手册": ("MSH", "怪物召唤者手册", "Monster Summoner's Handbook"),
    "格拉里昂的半身人": ("HaG", "格拉里昂的半身人", "Halflings of Golarion"),
    "武器大师手册": ("WEAPON", "武器大师手册", "Weapon Master's Handbook"),
    "武术手册MAH": ("MAH", "武术手册", "Martial Arts Handbook"),
    "遥远世界DS": ("DS", "遥远世界", "Distant Shores"),
    "任务与战役": ("QaC", "任务与战役", "Quests and Campaigns"),
    "初探探索者协会": ("PSP", "初探探索者协会", "Pathfinder Society Primer"),
    "探索者协会战地指南PSFG": ("PSFG", "探索者协会战地指南",
                                         "Pathfinder Society Field Guide"),
    "极限荒野UW": ("UW", "极限荒野", "Ultimate Wilderness"),
    "间谍大师手册SH": ("SH", "间谍大师手册", "Spymaster's Handbook"),
    "阴影血脉BoS": ("BoS", "阴影血脉", "Blood of Shadows"),
    "魔法市集指南MM": ("MMG", "魔法市集指南", "Magical Marketplace"),
    "水下冒险AA": ("AqA", "水下冒险", "Aquatic Adventures"),
    "永罪之书第二卷BotD2": ("BotD2", "永罪之书第二卷：混沌诸王",
                                     "Book of the Damned - Volume 2: Lords of Chaos"),
    "海洋之血BotS": ("BotS", "海洋之血", "Blood of the Sea"),
    "纽梅利亚NLoFS": ("NLoFS", "纽梅利亚，星落之地",
                              "Numeria, Land of Fallen Stars"),
    "萨迦瓦StLC": ("StLC", "萨迦瓦，失落的殖民地", "Sargava, the Lost Colony"),
    "护甲大师手册": ("ARMOR", "护甲大师手册", "Armor Master's Handbook"),
    "卡蒂亚QJotE": ("QJotE", "卡蒂亚，东方明珠", "Qadira, Jewel of the East"),
    "遥远国度DR": ("DR", "遥远国度", "Distant Realms"),
    "瓦瑞西亚，传说诞生之地": ("VBoL", "瓦瑞西亚，传说诞生之地",
                                "Varisia, Birthplace of Legends"),
    "皇庭英豪HotHC": ("HotHC", "皇庭英豪", "Heroes of the High Court"),
    "神话源始MO": ("MO", "神话源始", "Mythic Origins"),
    "经典恐怖再临CHR": ("CHR", "经典恐怖再临", "Classic Horrors Revisited"),
    "缘界英雄HftF": ("HftF", "缘界英雄", "Heroes from the Fringe"),
    "荒野英雄HotW": ("HotW", "荒野英雄", "Heroes of the Wild"),
    "街巷英雄HotS": ("HotS", "街巷英雄", "Heroes of the Streets"),
    "冒险者的军械库2": ("AA2", "冒险者的军械库2", "Adventurer's Armory 2"),
    "地城探险者手册DH": ("DH", "地城探险者手册", "Dungeon Explorer's Handbook"),
    "屠龙者手册": ("Dragonslayer", "屠龙者手册", "Dragonslayer's Handbook"),
    "怪物猎人手册": ("MHH", "怪物猎人手册", "Monster Hunter's Handbook"),
    "恶魔猎人手册": ("DHH", "恶魔猎人手册", "Demon Hunter's Handbook"),
    "格拉里昂的狗头人": ("KoG", "格拉里昂的狗头人", "Kobolds of Golarion"),
    "格拉里昂的矮人": ("DoG", "格拉里昂的矮人", "Dwarves of Golarion"),
    "秘密探寻者SoS": ("SoS", "秘密探寻者", "Seekers of Secrets"),
    "药剂与毒药P&P": ("P&P", "药剂与毒药", "Potions and Poisons"),
    "近战战术工具箱CTT": ("CTT", "近战战术工具箱", "Melee Tactics Toolbox"),
    "进化职业起源ACO": ("ACO", "进化职业起源", "Advanced Class Origins"),
    "远程战术工具箱RTT": ("RTT", "远程战术工具箱", "Ranged Tactics Toolbox"),
    "邪恶特务AoE": ("AoE", "邪恶特务", "Agents of Evil"),
    "门徒教义DD": ("DD", "门徒教义", "Disciple's Doctrine"),
    "阴招战术工具箱DTT": ("DTT", "阴招战术工具箱", "Dirty Tactics Toolbox"),
    "魔宠手记FF": ("FF", "魔宠手记", "Familiar Folio"),
    "魔法战术工具箱MTT": ("MTT", "魔法战术工具箱", "Magic Tactics Toolbox"),
    "哈罗牌手册THH": ("THH", "哈罗牌手册", "The Harrow Handbook"),
    "CaC部属与伙伴": ("CaC", "部属与伙伴", "Cohorts and Companions"),
    "亡灵杀手手册": ("UNDEAD", "亡灵杀手手册", "Undead Slayer's Handbook"),
    "信仰与哲学F&P": ("F&P", "信仰与哲学", "Faiths and Philosophies"),
    "废土子民PotW": ("PotW", "废土子民", "People of the Wastes"),
    "均衡信念FoB": ("FoB", "均衡信念", "Faiths of Balance"),
    "失落秘宝LostTreasures": ("LT", "失落秘宝", "Lost Treasures"),
    "构装体手册CH": ("CH", "构装体手册", "Construct Handbook"),
    "林诺姆诸王之国LotLK": ("LotLK", "林诺姆诸王之国",
                                    "Lands of the Linnorm Kings"),
    "格拉里昂的平衡勇士": ("CoB", "平衡勇士", "Champions of Balance"),
    "格拉里昂的秽邪勇士": ("CoC", "秽邪勇士", "Champions of Corruption"),
    "沙之子民PotS": ("PotS", "沙之子民", "People of the Sands"),
    "河域子民PotR": ("PotR", "河域子民", "People of the River"),
    "河域诸国指南GttRK": ("GttRK", "河域诸国指南",
                                  "Guide to the River Kingdoms"),
    "繁星子民PotS": ("PoS", "繁星子民", "People of the Stars"),
    "永罪之书": ("BotD", "永罪之书", "Book of the Damned"),
    "炼金术手册AM": ("AM", "炼金术手册", "Alchemy Manual"),
    "黑市指南BM": ("BM", "黑市指南", "Black Markets"),
    # 无来源行的 8 文件（2026-08-08 逐文件定性）：
    # 武器_防具/武器.md = CRB 表6-1 新武器；炼金物品3/装备3/武器附魔5/特殊武器防具
    # = 极限诡道 UI 章节（内容引用《极限诡道》）；HA炼金物品 = 恐怖冒险 HA 炼金章；
    # AA2来自海外的装备 = 冒险者的军械库2 海外装备节；超游神器.md = d20pfsrd 通用
    # 神器导言无书归属 → 显式 '?' 键（KN 登记，闸口 max-book-unknown 内；
    # 建键是为了专属表完整性自证 223 全命中，区别于「漏表」）
    "武器.md": ("CRB", "核心规则书", "Core Rulebook"),
    "炼金物品3.md": ("UI", "极限诡道", "Ultimate Intrigue"),
    "装备3.md": ("UI", "极限诡道", "Ultimate Intrigue"),
    "武器附魔5.md": ("UI", "极限诡道", "Ultimate Intrigue"),
    "特殊武器防具.md": ("UI", "极限诡道", "Ultimate Intrigue"),
    "UI奇物.md": ("UI", "极限诡道", "Ultimate Intrigue"),
    "UI戒指.md": ("UI", "极限诡道", "Ultimate Intrigue"),
    "HA炼金物品.md": ("HA", "恐怖冒险", "Horror Adventures"),
    "AA2来自海外的装备.md": ("AA2", "冒险者的军械库2", "Adventurer's Armory 2"),
    "超游神器.md": ("?", "未知", "Unknown"),
    # ---- C 形态 CHM 大页（M4 批次 2，74 页，2026-08-09 逐页定性）----
    # 定性依据 = CHM TOC（CHM_FULL_TOC_WITH_LEVELS.md 行 687~782 装备 L1 子树）
    # L2/L3 归属 + 页内容核验；页键精确到页码（长前缀优先排序保证
    # page_1006 先于 page_1 命中，与书件前缀同表同序）。
    #   CRB 装备章（无书前缀 L3，40 页）：206~234（表 6-1~6-8 武器防具/
    #   货品服务/魔法物品/奇物 13 位置）、275（刺青魔法）、567~569（艾恩石/
    #   寻路仪）、775（现代火器，正文「现代火器规则」参照极限战斗）、851
    #   （PF 官方弹药汇总——d20pfsrd 汇总页书目列表首标 CRB，TOC 归 CRB
    #   武器章，KN 登记跨书）、864（攻城兵器，CRB 表 6-1）、946~949（预设
    #   装备包/被诅咒物品/智能物品/次级与高等神器）、1254（艾恩石合集——
    #   TOC L5 归 CRB 无位置奇物下，但正文含 AG/HftF/AP#138 跨书条目，
    #   KN 登记）
    "page_206.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_207.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_208.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_209.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_210.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_211.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_212.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_213.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_214.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_215.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_216.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_217.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_218.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_219.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_220.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_221.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_222.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_223.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_224.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_225.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_226.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_227.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_228.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_229.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_230.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_231.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_232.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_233.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_234.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_275.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_567.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_568.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_569.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_775.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_851.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_864.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_946.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_947.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_948.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_949.md": ("CRB", "核心规则书", "Core Rulebook"),
    "page_1254.md": ("CRB", "核心规则书", "Core Rulebook"),
    #   AA（1 页）：1590（TOC「AA新增武器」）
    "page_1590.md": ("AA", "冒险者的军械库", "Adventurer's Armory"),
    #   AA2（6 页）：1006（AA2新增武器）、1014（武器改造）、1020（盔甲
    #   改造）、1021（AA2新增防具）、1022（AA2新增服饰）、1067（AA2的
    #   范例精制品工具）
    "page_1006.md": ("AA2", "冒险者的军械库2", "Adventurer's Armory 2"),
    "page_1014.md": ("AA2", "冒险者的军械库2", "Adventurer's Armory 2"),
    "page_1020.md": ("AA2", "冒险者的军械库2", "Adventurer's Armory 2"),
    "page_1021.md": ("AA2", "冒险者的军械库2", "Adventurer's Armory 2"),
    "page_1022.md": ("AA2", "冒险者的军械库2", "Adventurer's Armory 2"),
    "page_1067.md": ("AA2", "冒险者的军械库2", "Adventurer's Armory 2"),
    #   OA 异能冒险（5 页）：729（TOC「OA的冒险装备与炼金道具」）、
    #   1127~1130（TOC「异能冒险」L3：魔法物品/奇物/诅咒物品/神器）
    "page_729.md": ("OA", "异能冒险", "Occult Adventures"),
    "page_1127.md": ("OA", "异能冒险", "Occult Adventures"),
    "page_1128.md": ("OA", "异能冒险", "Occult Adventures"),
    "page_1129.md": ("OA", "异能冒险", "Occult Adventures"),
    "page_1130.md": ("OA", "异能冒险", "Occult Adventures"),
    #   HA 恐怖冒险（1 页）：736（TOC「HA折磨刑具」）
    "page_736.md": ("HA", "恐怖冒险", "Horror Adventures"),
    #   UW 极限荒野（2 页）：695（草药学子系统——PFS 特殊规则+草药学
    #   系统为 UW 独有）、1469（TOC「UW的炼金工具」）
    "page_695.md": ("UW", "极限荒野", "Ultimate Wilderness"),
    "page_1469.md": ("UW", "极限荒野", "Ultimate Wilderness"),
    #   P&P 药剂与毒药（1 页）：884（炼金合剂——「合剂效果持续时间
    #   1 小时」为 P&P 合剂标志性规则，正文无书标注，按规则特征定性）
    "page_884.md": ("P&P", "药剂与毒药", "Potions and Poisons"),
    #   AA+AM 混合（1 页）：29（炼金功能材料——正文逐条标（AA）/（AM），
    #   AA 13 条 + AM 21 条，页级取书目列表首位 AA，AM 21 条书归属未细分
    #   登记 KN）
    "page_29.md": ("AA", "冒险者的军械库", "Adventurer's Armory"),
    #   MA 神话冒险（7 页）：627~633（TOC「神话冒险」L3：防具附魔/特殊
    #   魔法防具/武器附魔/特殊魔法武器/其他魔法物品/神器/传说物品）
    "page_627.md": ("MA", "神话冒险", "Mythic Adventures"),
    "page_628.md": ("MA", "神话冒险", "Mythic Adventures"),
    "page_629.md": ("MA", "神话冒险", "Mythic Adventures"),
    "page_630.md": ("MA", "神话冒险", "Mythic Adventures"),
    "page_631.md": ("MA", "神话冒险", "Mythic Adventures"),
    "page_632.md": ("MA", "神话冒险", "Mythic Adventures"),
    "page_633.md": ("MA", "神话冒险", "Mythic Adventures"),
    #   PU 极限解放（7 页）：635~641（TOC「Pathfinder:Unchained」L3：
    #   成长型奇物 + 特殊防具/特殊武器/戒指/权杖/法杖/奇物 L5）
    "page_635.md": ("PU", "极限解放", "Pathfinder Unchained"),
    "page_636.md": ("PU", "极限解放", "Pathfinder Unchained"),
    "page_637.md": ("PU", "极限解放", "Pathfinder Unchained"),
    "page_638.md": ("PU", "极限解放", "Pathfinder Unchained"),
    "page_639.md": ("PU", "极限解放", "Pathfinder Unchained"),
    "page_640.md": ("PU", "极限解放", "Pathfinder Unchained"),
    "page_641.md": ("PU", "极限解放", "Pathfinder Unchained"),
    #   ISG 内海诸神（2 页）：860/865（TOC「神器与传说」L3 高等/次级神器
    #   ——内容核验：860 含 Apollyon 之戒/Chellan，865 含骨头屋/十人团之盔/
    #   西牟鸟之冠等 ISG 神器章标志性条目，正文提及「内海指南」）
    "page_860.md": ("ISG", "内海诸神", "Inner Sea Gods"),
    "page_865.md": ("ISG", "内海诸神", "Inner Sea Gods"),
}
# 长前缀优先（冒险者的军械库2 在 冒险者的军械库 之前、永罪之书第二卷 在
# 永罪之书 之前等）；同长按 rel 字典序保证确定性
_EQUIP_SOURCE_ORDER: tuple = tuple(
    sorted(_EQUIP_SOURCE_OVERRIDES, key=lambda p: (-len(p), p))
)

# 同 stem 重复文件（奇物/ 与 奇物/无位置/ 同名 5 对，矩阵 297 含全部）：
# doc_id/chunk_id 按 stem 生成必撞车（chunk_id 唯一性不变量），消歧后缀 =
# 父目录末段（奇物 / 无位置）。verify 侧 _doc_id_of 同源 import 本集合
#（check_discriminator_regression 按消歧后 doc_id 独立对账）；模块级常量
# 沿袭技能 _B2_SOURCE_OVERRIDES 同源惯例（KN136：公共层 base.py 零改动）
_DUP_STEMS: frozenset = frozenset({
    "任务与战役_奇物", "初探探索者协会_奇物", "探索者协会战地指南PSFG_奇物",
    "秘密探寻者SoS_奇物", "药剂与毒药P&P_奇物",
})


def _resolve_equip_source(rel: str) -> Optional[tuple]:
    """专属表短路（basename 前缀，长前缀优先）：rel → (abbr, cn, en)

    表键 = 文件名前缀（含子目录文件的 basename，如 武器/位面冒险PA_特殊
    武器.md → 「位面冒险PA」），与 rel 的目录结构解耦——子目录聚合文件
    （武器/ 货品服务/ 炼金物品/ 魔法物品/ 等）同书同键命中。
    """
    base = rel.rsplit("/", 1)[-1]
    for prefix in _EQUIP_SOURCE_ORDER:
        if base.startswith(prefix):
            return _EQUIP_SOURCE_OVERRIDES[prefix]
    return None


def _load_equip_scan_rels() -> set:
    """加载批次扫描清单 → {rel}（P1x 223 文件 M3 批次 1 + P2x 74 页件 M4 批次 2 = 297）"""
    try:
        with open(_PREPARE_BATCHES_JSON, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        raise RuntimeError(
            f"无法加载批次清单 {_PREPARE_BATCHES_JSON}（装备扫描清单同口径来源）：{e}"
        ) from e
    rels = set()
    for batch in raw:
        if batch.get("batch", "").startswith(("P1", "P2")):
            for f in batch.get("files", []):
                rels.add(f.removeprefix("pf_rules_md_organized/"))
    if len(rels) != 297:
        raise RuntimeError(f"装备批次扫描清单应为 297 文件（P1 223 + P2 74），实际 {len(rels)}")
    # 专属表完整性自证：清单内每个文件必须可短路命中（漏表 = 来源失实，
    # 技能 3.1 教训的编译期等价物）
    miss = sorted(rel for rel in rels if _resolve_equip_source(rel) is None)
    if miss:
        raise RuntimeError(
            f"装备专属来源表缺失 {len(miss)} 文件（必须逐文件定性后补表）：{miss[:5]}"
        )
    return rels


EQUIP_SCAN_RELS: set = _load_equip_scan_rels()


def _equip_file_condition(file_path: Path) -> bool:
    """装备文件判断：文件 rel 在批次 1 扫描清单内（223 文件）"""
    try:
        rel = file_path.resolve().relative_to(_ORGANIZED_ROOT)
    except ValueError:
        return False
    return str(rel) in EQUIP_SCAN_RELS


# ---- 文件级默认 component_type（子目录语义，M2 §四 16 主类）----
# 条目级强信号（_signal_component_type）在 infer_metadata 覆盖；混合目录给
# 保守默认 gear，由信号纠正。前缀全路径锚定（2026-08-08 修复：`魔法物品/`
# 子串会误配根级 `装备_魔法物品/xxx.md`，全库 wondrous_item 虚高——
# 根级文件走默认 gear 由信号纠正）；防具附魔/武器附魔 → enchantment
# （M2 §三 3.2，enchantment_target 按文件语义注入）。
_EQUIP_FILE_COMPONENT = (
    ("装备_魔法物品/魔法物品/奇物/", "wondrous_item"),
    ("装备_魔法物品/魔法物品/极限荒野UW_魔法植物", "magic_plant"),
    ("装备_魔法物品/魔法物品/神器与传说/", "artifact"),
    ("装备_魔法物品/魔法物品/极限诡道/", "gear"),
    ("装备_魔法物品/魔法物品/魔法武器防具/", "gear"),
    ("装备_魔法物品/防具附魔/", "enchantment"),
    ("装备_魔法物品/武器附魔/", "enchantment"),
    ("装备_魔法物品/特定魔法防具/", "armor"),
    ("装备_魔法物品/炼金物品/", "alchemical_item"),
    ("装备_魔法物品/武器/", "weapon"),
    ("装备_魔法物品/武器_防具/", "gear"),
    ("装备_魔法物品/货品服务/", "gear"),
    ("装备_魔法物品/魔法物品/", "wondrous_item"),
)
# 戒指/权杖/法杖文件名语义（M2 §四：ring/rod/staff 独立类；子目录
# 戒指_权杖_法杖/ 内文件名自带类名 → 精确 endswith 判定，禁子串推导）
_RING_ROD_STAFF_SUFFIX = (
    ("_戒指.md", "ring"),
    ("_权杖.md", "rod"),
    ("_法杖.md", "staff"),
)


# CHM 大页 → 类目（M5 用户拍板「CHM 大页对齐 D4」，2026-08-09）：
# page_220~222 戒指/权杖/法杖、947~949 诅咒/智能/神器、946 装备包、
# 234 无位置奇物（根级文件，无栏位行条目曾漏信号归 gear）。书聚合混合
# 文件维持 wondrous_item 吸收 + slot 区分。精确 basename 匹配（禁子串
# 推导，KN182 同款教训）。
_EQUIP_PAGE_COMPONENT = {
    "page_220": "ring",
    "page_221": "rod",
    "page_222": "staff",
    "page_234": "wondrous_item",
    "page_946": "equipment_package",
    "page_947": "cursed_item",
    "page_948": "intelligent_item",
    "page_949": "artifact",
}


def _file_component_type(rel: str) -> str:
    # CHM 大页映射（精确 stem，优先于文件名/目录语义）
    stem = rel.rsplit("/", 1)[-1][:-3]
    if stem in _EQUIP_PAGE_COMPONENT:
        return _EQUIP_PAGE_COMPONENT[stem]
    # 文件名语义优先（`魔法物品/` 兜底前缀会抢先命中戒指权杖文件）
    for suffix, ct in _RING_ROD_STAFF_SUFFIX:
        if rel.endswith(suffix):
            return ct
    for prefix, ct in _EQUIP_FILE_COMPONENT:
        if prefix in rel:
            return ct
    return "gear"


# component_type 条目级强信号（fields 键 → 类目）：
# damage/critical → weapon；护甲加值/最大敏捷加值/防具检定减值/奥术失败机率
# → armor；slot 归一后 ∈ 13 枚举 → wondrous_item（仅 gear/wondrous 默认类，
# 专属类不被覆盖）；slot ∈ 护甲类（护甲/盾牌/盔甲/铠甲）→ armor。无信号 →
# 文件级默认。
_ARMOR_SIGNAL_KEYS = ("护甲加值", "最大敏捷加值", "防具检定减值", "奥术失败机率")

# slot 严格 13 枚举归一（M5 用户拍板，2026-08-09）：别名/译注/多位置 → 规范值
# （CHM TOC L4 词形）；护甲类穿戴值 → None（条目归 armor 类，slot 不设）；
# 其他非奇物值（—/符文/武器等）→ None（slot 只对奇物条目有意义）。
_EQUIP_SLOT_ALIASES = {
    "身体": "躯体", "躯干": "躯体",
    "腰带": "腰部", "手腕": "腕部", "手": "手部", "手指": "戒指",
    "头带": "头饰", "肩膀": "肩部", "颈": "颈部", "眼睛": "眼部",
    "双脚": "脚部", "脸部": "头部",
}
# 护甲类穿戴值（非奇物位置，条目归 armor 类）
_SLOT_ARMOR_VALUES = ("护甲", "盾牌", "盔甲", "铠甲")
# slot 只对奇物语义类目有意义（M5 拍板）：附魔/武器/护甲/gear 等非奇物
# 类目即使源数据写了位置值（附魔条目「位置 无」——「无」是 13 枚举合法值
# 但语义是奇物位置的「无」），也不设 slot 键，field_status 置 not_applicable
_SLOT_RELEVANT_CT = frozenset({
    "wondrous_item", "ring", "rod", "staff", "cursed_item",
    "intelligent_item", "artifact", "magic_plant",
})
# 前缀主词：剥「（」「［」「，」「或」「和」取开头槽位词（`头部（head）`/
# `颈部或肩部`/`无，重力1磅`/`躯干和头部（见下文）`/`手［注…］`），
# 再取汉字前缀剥尾部英文（`头部head`）——通用译注/多位置/粘连兜底
_RE_SLOT_LEAD = re.compile(r"([一-鿿]+)")
_SLOT_SEG_SPLIT = re.compile(r"[（(［，,、或和]")


def _normalize_slot(raw: str) -> Optional[str]:
    """slot 严格 13 枚举归一：直通/别名/前缀主词；非奇物值 → None。

    返回 None 的调用方（infer_metadata）：不设 md["slot"] 键，field_status
    对 slot 置 not_applicable（slot 只对奇物条目有意义，M5 用户拍板）。
    """
    s = str(raw or "").strip()
    if not s:
        return None
    if s in EQUIP_SLOT_VALUES:
        return s
    if s in _EQUIP_SLOT_ALIASES:
        return _EQUIP_SLOT_ALIASES[s]
    if s in _SLOT_ARMOR_VALUES:
        return None
    lead = _SLOT_SEG_SPLIT.split(s, 1)[0]
    m = _RE_SLOT_LEAD.match(lead)
    if not m:
        return None
    word = m.group(1)
    if word in EQUIP_SLOT_VALUES:
        return word
    return _EQUIP_SLOT_ALIASES.get(word)


def _signal_component_type(fields: dict, file_ct: str) -> str:
    if fields.get("damage") or fields.get("critical"):
        return "weapon"
    if any(fields.get(k) for k in _ARMOR_SIGNAL_KEYS):
        return "armor"
    slot = fields.get("slot")
    if slot:
        if _normalize_slot(slot) is not None:
            # 13 枚举值（含别名归一）→ 奇物；专属类（ring/rod/staff/…）不被覆盖
            if file_ct in ("gear", "wondrous_item"):
                return "wondrous_item"
        elif slot.strip() in _SLOT_ARMOR_VALUES:
            # 护甲类穿戴值 → armor（书聚合护甲条目纠正，修复曾覆盖成 wondrous）
            return "armor"
    return file_ct


# formats 层 item type → component_type（category/intro → equipment_intro 导言；
# index → equipment_index；rule → equipment_rule；item 由信号+文件级判定）
_TYPE_TO_CT = {
    "item": None,  # infer_metadata 信号判定
    "category": "equipment_intro",
    "intro": "equipment_intro",
    "index": "equipment_index",
    "rule": "equipment_rule",
}


class EquipmentBackfillChmTocPath(BackfillChmTocPath):
    """toc 空回填（同专长三级链路：注释源 md → md_map / 来源行路径），
    报告写 docs/装备/（子类覆写类属性目录，feat_chain 逻辑零改动）"""
    DEFAULT_REPORT_DIR = Path("docs/装备")

    def _resolve_doc_file(self, doc_files: dict, doc_id: str) -> Optional[str]:
        """消歧 doc_id 剥 `__{父目录}` 后缀回源 stem——5 对同 stem 重复文件
        （奇物/ 与 奇物/无位置/）的 doc 由 _build_chunk_template 加后缀消歧，
        源文件注释/来源行只在源 stem 名下（父类默认精确查会 40 条全落空，
        2026-08-09 unfilled 40 实测）"""
        hit = doc_files.get(doc_id)
        if hit is not None:
            return hit
        return doc_files.get(doc_id.rsplit("__", 1)[0])


# 奇物 11 位置页 doc_id → 位置词形映射（CHM TOC L4 权威词形，KN190 方案 §2.1）
_EQUIP_PAGE_SLOT_MAP = {
    "page_223": "腰部", "page_224": "躯体", "page_225": "胸部", "page_226": "眼部",
    "page_227": "脚部", "page_228": "手部", "page_229": "头部", "page_230": "头饰",
    "page_231": "颈部", "page_232": "肩部", "page_233": "腕部",
}


class BackfillSlotByPage:
    """奇物位置页 slot 回填（KN190，方案 docs/装备/奇物slot回填方案_20260809.md）。

    背景：11 个位置页（page_223~233）纯描述形态条目无「位置：」字段链 →
    slot=missing（326/479 ≈ 68%，KN190），位置仅隐含于 doc_id 页面归属（CHM TOC
    L4 目录词形）。回填按 doc_id 精确映射补 slot（精确匹配非前缀，防聚合书
    子串误命中）；有值条目一律不动（源数据字段声明 > 页面归属推导——A1 拍板：
    7 条页内混排自声明例外如抒情竖琴=无、游击头巾=头饰保持原值）。

    field_status.slot：missing → parsed（B1 拍板，三态内扩展语义「源数据字段
    解析 ∪ 页面归属映射」，doc_id 为源数据固有属性、映射表为 CHM 目录权威，
    schema 零变更）。

    只改 metadata.slot + field_status.slot；不动 text/title/chunk 边界/来源书。
    幂等：有值不动，二次运行零变更。公共层零改动（KN136 安全）。
    """

    # 报告目录（类属性，子类覆写防跨类目覆盖）
    DEFAULT_REPORT_DIR = Path("docs/装备")

    PAGE_SLOT = _EQUIP_PAGE_SLOT_MAP

    def run(self, output_dir, report_dir: Optional[Path] = None) -> Dict[str, Any]:
        chunks_path = Path(output_dir) / "chunks.jsonl"
        report_dir = report_dir or type(self).DEFAULT_REPORT_DIR
        lines = open(chunks_path, encoding="utf-8").readlines()
        shutil.copy(chunks_path, str(chunks_path) + ".bak_slot")

        applied = Counter()
        total_pos = 0   # 位置页 wondrous_item 条目数（终态统计）
        missing_before = 0  # 回填前缺失数
        for i, line in enumerate(lines):
            o = json.loads(line)
            meta = o.get("metadata") or {}
            if o.get("component_type") == "wondrous_item" and o.get("doc_id") in self.PAGE_SLOT:
                total_pos += 1
                if meta.get("slot") is None:
                    missing_before += 1
                    slot = self.PAGE_SLOT[o["doc_id"]]
                    meta["slot"] = slot
                    fs = meta.get("field_status") or {}
                    if fs.get("slot") == "missing":
                        fs["slot"] = "parsed"
                        meta["field_status"] = fs
                    applied[o["doc_id"]] += 1
            lines[i] = json.dumps(o, ensure_ascii=False) + "\n"

        with open(chunks_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        report_dir.mkdir(parents=True, exist_ok=True)
        total = sum(applied.values())
        missing_after = missing_before - total  # 回填后剩余缺失（终态应为 0）
        lines_md = [
            "# slot 回填报告（KN190，finalize 后处理）",
            "",
            f"> 位置页条目 {total_pos} / 回填前缺失 {missing_before}（本次回填 {total}，"
            f"回填后缺失 {missing_after}）",
            "> 依据：`docs/装备/奇物slot回填方案_20260809.md`（A1/B1 拍板，doc_id 页面归属映射）",
            "",
            "| doc_id | 本次回填 |",
            "|---|---|",
        ]
        lines_md += [f"| {doc} | {n} |" for doc, n in sorted(applied.items())]
        lines_md += ["", "> 幂等：有值条目一律不动（源数据字段声明优先），缺失为 0 后二次运行零变更。"]
        with open(report_dir / "slot_backfill_report.md", "w", encoding="utf-8") as f:
            f.write("\n".join(lines_md))
        return {"backfilled": total, "position_total": total_pos,
                "missing_before": missing_before, "missing_after": missing_after}


class EquipmentProcessor(FileProcessor):
    """装备/魔法物品文件处理器"""

    POSTPROCESSORS = [EquipmentBackfillChmTocPath, BackfillSlotByPage]

    @property
    def category(self) -> str:
        return "equipment"

    def __init__(self, source_resolver: SourceResolver):
        super().__init__(source_resolver=source_resolver, format_handler=EquipmentFormat())

    def build_chunk(self, template: Chunk, item: dict) -> Chunk:
        """设置条目标题、正文、别名与组件类型

        component_type：item 由 infer_metadata 信号+文件级判定；category/intro
        → equipment_intro；index → equipment_index；rule → equipment_rule。
        """
        typ = item.get("type", "item")
        template.title = " ".join(str(item.get("title", "")).split())
        template.text = item.get("text", "")
        name_en = item.get("title_en", "")
        template.aliases = [" ".join(str(name_en).split())] if name_en else []
        # 神器异名括号（949 族 `猿猴之手(大圣遗愿/怨)MONKEY'S`）剥壳后的
        # 中文别名（format 层 item["aliases"]）——查询别名，检索端可用
        template.aliases += [a for a in item.get("aliases", []) if a]
        if typ in _TYPE_TO_CT and _TYPE_TO_CT[typ] is not None:
            template.component_type = _TYPE_TO_CT[typ]
        else:
            try:
                rel = str(self._current_rel)
            except AttributeError:
                rel = ""
            template.component_type = _file_component_type(rel)
        return template

    def process(self, file_path: Path) -> List[Chunk]:
        """记录当前 rel 供 build_chunk 文件级 component_type 判定"""
        try:
            self._current_rel = str(file_path.resolve().relative_to(_ORGANIZED_ROOT))
        except ValueError:
            self._current_rel = ""
        return super().process(file_path)

    def _build_chunk_template(self, file_path: Path, idx: int, ctx) -> "Chunk":
        """覆写模板方法：仅对同 stem 重复 5 对文件消歧 doc_id/chunk_id，
        其余文件行为与公共层完全一致（KN136 公共层零改动）"""
        chunk = super()._build_chunk_template(file_path, idx, ctx)
        if file_path.stem in _DUP_STEMS:
            suffix = f"__{file_path.parent.name}"
            chunk.doc_id = file_path.stem + suffix
            chunk.chunk_id = f"{self.category}_{file_path.stem}{suffix}_{idx:04d}"
        return chunk

    def resolve_source(self, chunk: Chunk, ctx: SourceContext, item: dict) -> Chunk:
        """解析来源书：专属表短路（100% 覆盖 P1 223 文件）→ 共享链 → 引用块兜底。

        技能 3.1 教训（KN165）：本类目 40+ 来源书、文件名/目录含「装备」「魔法
        物品」等词，公共层 DirectoryNameProvider 子串匹配必误标（557/557 系统性
        失实复现风险）；且公共层冲突键（RTT/UI/AArch/FoB/PotR/HoG 等）语义与
        装备不同，共享链会返回错误值。故 P1 全部文件在进入共享链前短路。
        """
        try:
            rel = str(ctx.file_path.resolve().relative_to(_ORGANIZED_ROOT))
        except ValueError:
            rel = ""
        hit = _resolve_equip_source(rel)
        if hit:
            chunk.book_abbreviation, chunk.book_name_cn, chunk.book_name_en = hit
            chunk.source_confidence = 75
            return chunk
        # 专属表外（超游神器.md 等无书归属文件）：共享链 → 引用块兜底
        result = self.source_resolver.resolve(ctx)
        if result.book_abbreviation == "?":
            hint = _feat_source_from_content(ctx.file_content)
            if hint:
                result = SourceResult(hint[0], hint[1], hint[2], 65,
                                      "EquipmentSourceLineProvider")
        chunk.book_abbreviation = result.book_abbreviation
        chunk.book_name_cn = result.book_name_cn
        chunk.book_name_en = result.book_name_en
        chunk.source_confidence = result.confidence
        return chunk

    def infer_metadata(self, chunk: Chunk, item: dict) -> Chunk:
        """按条目类型组装 metadata + field_status 三态 + component_type 信号覆盖

        - item 主条目：item_name/english_name（标题）+ 规范字段（slot/subcategory/
          price/weight/aura/caster_level/craft_cost/craft_conditions/
          craft_requirements/damage/critical）+ extra 保真（低频散字段原文）+
          source 原文 + rule_version（= book 小写）+ format_cluster
        - category/intro/index/rule：title/title_en + source + rule_version
        - field_status：规范键值非空 = parsed / 空 = missing；非主条目类目 = 全集
          not_applicable
        - component_type：信号覆盖文件级默认（_signal_component_type）
        """
        typ = item.get("type", "item")
        md: Dict[str, Any] = {}
        if typ == "item":
            md["item_name"] = " ".join(str(item.get("title", "")).split())
            md["english_name"] = " ".join(str(item.get("title_en", "")).split())
            fields = item.get("fields", {}) or {}
            # 规范键 → metadata；其余 → extra 原文保真（§二 2.5）
            canonical = {"slot", "subcategory", "price", "weight", "aura",
                         "caster_level", "craft_cost", "craft_conditions",
                         "craft_requirements", "damage", "critical"}
            extra: Dict[str, str] = {}
            slot_na = False
            for key, val in fields.items():
                if key in canonical:
                    if key == "slot":
                        # slot 严格 13 枚举（M5 用户拍板）：归一失败（护甲类/
                        # 非奇物值）→ 不设 slot 键，field_status 置
                        # not_applicable（slot 只对奇物条目有意义）
                        canon = _normalize_slot(val)
                        if canon:
                            md[key] = canon
                        else:
                            slot_na = True
                    else:
                        md[key] = val
                else:
                    extra[key] = val
            if extra:
                md["extra"] = extra
            md["source"] = item.get("source", "")
            md["rule_version"] = chunk.book_abbreviation.lower()
            md["format_cluster"] = item.get("format_cluster", "")
            if chunk.component_type != "enchantment":
                # 混合目录：信号覆盖文件级默认
                md["component_type"] = _signal_component_type(fields, chunk.component_type)
            else:
                # 附魔专属目录：enchantment 固定 + enchantment_target 按文件
                # 语义注入（M2 §三 3.2：防具附魔 → armor，武器附魔 → weapon）
                md["component_type"] = "enchantment"
                rel = self._current_rel or ""
                if "防具附魔" in rel:
                    md["enchantment_target"] = "armor"
                elif "武器附魔" in rel:
                    md["enchantment_target"] = "weapon"
                else:
                    md["enchantment_target"] = "special"
            chunk.component_type = md["component_type"]
            # slot 只对奇物语义类目有意义（M5 拍板）：附魔/武器/护甲/gear 等
            # 非奇物类目即使源数据写了位置值（附魔条目「位置 无」——「无」是
            # 13 枚举合法值但语义是奇物位置的「无」），也不设 slot 键，
            # field_status 置 not_applicable（2026-08-09 verify 检查 4 新增
            # 断言「enchantment 不得带 slot」暴露 6 条，PSFG 决斗等）
            if md["component_type"] not in _SLOT_RELEVANT_CT:
                md.pop("slot", None)
                slot_na = True
            fields_list = ("item_name", "english_name", "slot", "subcategory",
                           "price", "weight", "aura", "caster_level",
                           "craft_cost", "craft_conditions", "craft_requirements",
                           "damage", "critical", "source", "rule_version")
            md["field_status"] = self._compute_field_status(md, fields_list, typ)
            if slot_na:
                # slot 归一失败（护甲类/非奇物值）：字段对本条目不适用
                md["field_status"]["slot"] = "not_applicable"
        else:
            md["title"] = " ".join(str(item.get("title", "")).split())
            md["title_en"] = " ".join(str(item.get("title_en", "")).split())
            md["source"] = item.get("source", "")
            md["rule_version"] = chunk.book_abbreviation.lower()
            md["format_cluster"] = item.get("format_cluster", "")
            fields_list = ("title", "title_en", "source", "rule_version")
            md["field_status"] = self._compute_field_status(md, fields_list, typ)
        chunk.metadata = md
        return chunk

    # ---- field_status 三态（设计 §二 2.4：parsed / missing / not_applicable）----

    @staticmethod
    def _compute_field_status(metadata: dict, fields: tuple, typ: str) -> dict:
        """计算条目字段解析状态。

        - 主条目 item：全规范字段检查（非空 = parsed / 空 = missing）；
          extra 保真键单独 parsed
        - 辅助条目（category/intro/index/rule）：非标题字段 not_applicable
        """
        status = {}
        for f in fields:
            val = metadata.get(f)
            if f == "source":
                status[f] = "parsed" if val else "not_applicable"
            else:
                status[f] = "parsed" if val else "missing"
        if typ == "item":
            extra = metadata.get("extra", {})
            for k in extra:
                status[k] = "parsed"
        return status


# 模块加载时自动注册
register("equipment", EquipmentProcessor, _equip_file_condition)
