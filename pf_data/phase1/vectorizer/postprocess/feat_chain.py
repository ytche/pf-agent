"""feat_chain.py — 专长后处理链四步骤（v2.2 决策 A：pipeline finalize 阶段）

迁移自 phase1 根目录四脚本（apply_chm_toc_mapping / apply_feat_creation_source_promote /
backfill_chm_toc_path / backfill_feat_source），重构为「类 + run() 函数式接口」——
每个步骤类提供 `run(output_dir, report_dir=None) -> dict`（返回统计，pipeline logger 打印）。

执行顺序（POSTPROCESSORS 声明序 = 本模块顺序，**不可变**，教训 B1；
KN228 步骤 3 为「新增不重排」插入）：
  1. ApplyChmTocMapping — chm_toc_path → 书缩写映射套用（大部分 doc 的 book）
  2. ApplyFeatCreationSourcePromote — 造物专长一览行内来源顶层提升（专处理
     apply 保持 '?' 的跨书索引 doc）
  3. ApplyFeatMetamagicIndexJoin — page_1367 超魔专长一览 × 全库同名唯一书
     join 回填（KN228，2026-10-28 插入；只改 book=="?" 的 1367 chunk，幂等）
  4. BackfillChmTocPath — chm_toc_path 空三级链路回填（只填缺失）
  5. BackfillFeatSource — metadata.source 补齐（只填缺失）

任何重排都会造成 book/toc/source 回归（B1 教训：pipeline 重跑重置后处理产物）。

契约：① 幂等硬契约（全部「只填缺失/只改空值」模式，重跑 diff 为空，
test_postprocess.py 幂等测试）；② 顺序显式；③ 默认关闭兼容（pipeline 侧）。
"""
import glob
import json
import os
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Optional

# 报告输出默认目录（相对 phase1 cwd，与迁移前一致）
# 2026-08-04：改为类属性——race 子类覆写 DEFAULT_REPORT_DIR = docs/种族，
# 防两类目 finalize 报告互相覆盖；feat 行为零变化（默认值不变）。
DEFAULT_REPORT_DIR = Path("docs/专长")


# ============================================================
#  步骤 1：chm_toc_path → 书缩写映射套用（顺序 1，不可变）
# ============================================================


class ApplyChmTocMapping:
    """chm_toc_path → 书缩写映射套用（KN030 fallback 落地，2026-08-02）。

    来源判定链在页头无《书名》标注时，按 chm_toc_path 目录名判定来源。
    映射表权威文档：docs/专长/chm_toc_path_映射表.md（doc_id 粒度）。

    处理：
    1. 对 book_abbreviation == '?' 的 chunk，按 doc_id 查映射表改四字段
       （book_abbreviation / book_name_cn / book_name_en / source_confidence=70）。
    2. 一 doc 多书合集（SECTION_MAPPING，KN230）：按源文件章节边界把 chunk 归到
       具体书（page_538 = 纯善/平衡/堕落信念三本 Champions 合集）。
    3. 既有残缺/历史脏缩写统一修正（FIX_LEGACY）：'Handbook'（屠龙者手册）→ DSH；
       KN230 脏值 CAMPAIGN → PCS、ArcaneAnthology → ArAn、Dragonslayer → DSH
       （任意通道产出即改）。
    4. 跨书索引类不映射：page_1367 超魔专长一览、造物专长一览（保持 '?'，
      由步骤 2 promote 专处理）。

    只改顶层 book 字段，不动 text / title / metadata / chunk_id——chunk 结构与
    verify_feats.py 判别器不变量不变。幂等：'?' 处理一次后不再命中。
    """

    DEFAULT_REPORT_DIR = Path("docs/专长")

    # doc_id → (book_abbreviation, book_name_cn, book_name_en)
    # 值与既有体系对齐（同书同值直接复用 FEAT_SOURCES/共享缩写表/规则模块
    # 专属表先例；无先例的按 docs/规则书缩写对应表.md 或 toc 目录名核定）。
    # D1（2026-09-18）：abbr 全部 ASCII 化（原中文名占位值按上列先例归一，
    # GnomeG/DRR/CTT/OM 为本表首登记，见 docs/PF_缩写表.md）。
    # 依据见 docs/专长/chm_toc_path_映射表.md。
    MAPPING = {
        # --- organized 专长目录 ---
        "page_856": ("UI", "极限诡道", "Ultimate Intrigue"),
        "page_321": ("ISG", "内海诸神", "Inner Sea Gods"),
        "page_361": ("ARMOR", "护甲大师手册", "Armor Master's Handbook"),
        "page_311": ("OA", "异能冒险", "Occult Adventures"),
        "page_200": ("UCa", "极限战役", "Ultimate Campaign"),
        "page_555": ("CTT", "近战战术工具箱", "Melee Tactics Toolbox"),
        "page_556": ("DTT", "阴招战术工具箱", "Dirty Tactics Toolbox"),
        "page_194": ("CRB", "核心规则书", "Core Rulebook"),
        "page_276": ("ISC", "内海战斗", "Inner Sea Combat"),
        "page_500": ("ACO", "进化职业起源", "Advanced Class Origins"),
        "page_201": ("B1", "怪物图鉴", "Bestiary 1"),
        "page_552": ("RTT", "远程战术工具箱", "Ranged Tactics Toolbox"),
        "page_561": ("CEoD", "切利亚斯，魔鬼帝国", "Cheliax, Empire of Devils"),
        "page_673": ("F&P", "信仰与哲学", "Faiths and Philosophies"),
        "page_670": ("HotHC", "皇庭英豪", "Heroes of the High Court"),
        "page_505": ("UNDEAD", "亡灵杀手手册", "Undead Slayer's Handbook"),
        "page_529": ("DH", "冒险家手册", "Dungeoneer's Handbook"),
        "page_509": ("HaG", "格拉里昂的半身人", "Halflings of Golarion"),
        "page_531": ("STLC", "萨加瓦，失落的殖民地", "Sargava, The Lost Colony"),
        "page_744": ("OM", "异能奥秘", "Occult Mysteries"),
        "page_527": ("VBoL", "瓦瑞西亚，传说诞生之地", "Varisia, Birthplace of Legends"),
        "page_950": ("CRB", "核心规则书", "Core Rulebook"),
        # KN109 纳入（2026-08-04）：MA 神话冒险引言页（神话专长/超魔专长类别介绍）
        "page_622": ("MA", "神话冒险", "Mythic Adventures"),
        # --- 未整理目录 ---
        "专长11": ("UW", "极限荒野", "Ultimate Wilderness"),
        "专长": ("CoCorr", "秽邪勇士", "Champions of Corruption"),
        "专长41": ("ISR", "内海种族", "Inner Sea Races"),
        "专长33": ("CoBal", "平衡勇士", "Champions of Balance"),
        "专长1": ("MHH", "怪物猎人手册", "Monster Hunter's Handbook"),
        "专长24": ("HftF", "缘界英雄", "Heroes from the Fringe"),
        "专长45": ("QaC", "任务与战役", "Quests and Campaigns"),
        "page_820": ("DSH", "屠龙者手册", "Dragonslayer's Handbook"),
        "专长51": ("GIANT", "巨人猎手手册", "Giant Slayer's Handbook"),
        "专长7": ("AM", "炼金术手册", "Alchemy Manual"),
        "闹鬼专长": ("HHH", "闹鬼英雄手册", "Haunted Heroes Handbook"),
        "专长28": ("OO", "异能源始", "Occult Origins"),
        "专长36": ("SH", "间谍大师手册", "Spymaster's Handbook"),
        "专长52": ("GnomeG", "格拉里昂的侏儒", "Gnomes of Golarion"),
        "动物伙伴专长": ("UW", "极限荒野", "Ultimate Wilderness"),
        "专长49": ("PotH", "地狱骑士之道", "Path of the Hellknight"),
        "专长9": ("DR", "遥远国度", "Distant Realms"),
        "专长19": ("HotS", "街巷英雄", "Heroes of the Streets"),
        "其他专长": ("AG", "冒险者指南", "Adventurer's Guide"),
        "阵营与阵营专长": ("PU", "解放者", "Pathfinder Unchained"),
        "专长2": ("ISTav", "内海酒馆", "Inner Sea Taverns"),
        "专长13": ("WO", "荒野源始", "Wilderness Origins"),
        "专长38": ("BotD", "永罪之书", "Book of the Damned"),
        "专长10": ("CoG", "格拉里昂的城市", "Cities of Golarion"),
        "专长16": ("DHH", "恶魔猎人手册", "Demon Hunter's Handbook"),
        "专长3": ("PotR", "河域子民", "People of the River"),
        "专长53": ("RM", "敌手指南", "Rival Guide"),
        "专长58": ("BotS", "海洋之血", "Blood of the Sea"),
        "专长21": ("DS", "遥远世界", "Distant Shores"),
        "专长4": ("BM", "黑市指南", "Black Markets"),
        "专长39": ("QJotE", "卡蒂亚，东方明珠", "Qadira, Jewel of the East"),
        "专长56": ("ArAn", "秘术选集", "Arcane Anthology"),
        "专长57": ("CaC", "部属与伙伴", "Cohorts and Companions"),
        "专长6": ("THH", "哈罗牌手册", "The Harrow Handbook"),
        "专长12": ("PHH", "位面行者手册", "Plane-Hopper's Handbook"),
        "专长37": ("BotC", "巫团血脉", "Blood of the Coven"),
        "专长44": ("PotS", "沙之子民", "People of the Sands"),
        "专长48": ("GoG", "格拉里昂的地精", "Goblins of Golarion"),
        "专长5": ("DA", "神术选集", "Divine Anthology"),
        "专长55": ("ISI", "内海诡道", "Inner Sea Intrigue"),
        "专长18": ("PotN", "北地居民", "People of the North"),
        "专长25": ("MM", "魔法市集指南", "Magical Marketplace"),
        "专长27": ("AA2", "冒险者的军械库2", "Adventurer's Armory 2"),
        "专长35": ("BoG", "格拉里昂的混种", "Bastards of Golarion"),
        "专长50": ("DoG", "格拉里昂的矮人", "Dwarves of Golarion"),
        "专长31": ("HaG", "格拉里昂的半身人", "Halflings of Golarion"),
        "专长54": ("GR", "巨人再临", "Giants Revisited"),
        "专长15": ("SoS", "秘密探寻者", "Seekers of Secrets"),
        "专长8": ("PoS", "繁星子民", "People of the Stars"),
        "专长17": ("F&P", "信仰与哲学", "Faiths and Philosophies"),
        "专长20": ("CTR", "再探经典宝藏", "Classic Treasures Revisited"),
        "专长23": ("BotE", "元素血脉", "Blood of the Elements"),
        "专长26": ("AA", "冒险者的军械库", "Adventurer's Armory"),
        "专长29": ("OoG", "格拉里昂的兽人", "Orcs of Golarion"),
        "专长32": ("AH", "反英雄手册", "Antihero's Handbook"),
        "专长34": ("DRR", "巨龙再临", "Dragons Revisited"),
        "专长43": ("ASoL", "安多安，自由之魂", "Andoran, Spirit of Liberty"),
        "专长46": ("KoG", "格拉里昂的狗头人", "Kobolds of Golarion"),
        "专长47": ("UNDEAD", "亡灵杀手手册", "Undead Slayer's Handbook"),
        "其他专长2": ("MAH", "武术手册", "Martial Arts Handbook"),
    }

    # KN230（2026-09-21）一 doc 多书的分节映射：page_538（纯善/平衡/堕落信念三本
    # Champions 合集）按源 md 章节标记把每个 chunk 归到具体书。key = doc_id，
    # value = [(分节起始 chunk title, (abbr, cn, en)), ...]——chunk 按产物序（=
    # 源文件序）迭代，title 命中分节边界即切换到该节的书；首节前 chunk 属首节。
    # 依据：源文件 page_538.md 的「纯善信念」（line 5）/「平衡信念」（line 88）/
    # 「堕落信念」（line 140）章节标记与 CHM toc 路径
    # 「专长 → 纯善/平衡/堕落信念」。缩写取值同 MAPPING 口径（KN230 归并值）。
    SECTION_MAPPING = {
        "page_538": [
            ("酩酊侠",  ("CoPur", "纯洁勇士", "Champion of Purity")),
            ("洞观奥秘", ("CoBal", "平衡勇士", "Champions of Balance")),
            ("火罚之烙", ("CoCorr", "秽邪勇士", "Champions of Corruption")),
        ],
    }

    # 既有残缺/历史脏缩写统一修正（任意来源通道产出即改，幂等）：
    # 'Handbook'（屠龙者手册）→ DSH（D1 前既有残留）；
    # KN230（2026-09-21）历史脏值归并：CAMPAIGN（CHM toc 子串匹配产物，
    # 书=Pathfinder Campaign Setting，缩写对应表口径 PCS）→ PCS；
    # ArcaneAnthology（通道 1 引用块箭头段 ASCII 尾部直信产物）→ ArAn
    # （AA 已被冒险者的军械库登记，取 trait 侧 KN231 同书同值 ArAn）；
    # Dragonslayer（共享缩写表键直出，conf 50 正文线索通道）→ DSH；
    # CoP/CoB/CoC（共享缩写表键经 conf 50 正文线索通道直出，早于专长
    # 引用块兜底）→ CoPur/CoBal/CoCorr——共享表保留旧键不动（KN136 共享层
    # 改动漂移教训），feat 侧在本步骤统一归并。
    FIX_LEGACY = {
        "Handbook": ("DSH", "屠龙者手册", "Dragonslayer's Handbook"),
        "CAMPAIGN": ("PCS", "战役设定", "Campaign Setting"),
        "ArcaneAnthology": ("ArAn", "秘术选集", "Arcane Anthology"),
        "Dragonslayer": ("DSH", "屠龙者手册", "Dragonslayer's Handbook"),
        "CoP": ("CoPur", "纯洁勇士", "Champion of Purity"),
        "CoB": ("CoBal", "平衡勇士", "Champions of Balance"),
        "CoC": ("CoCorr", "秽邪勇士", "Champions of Corruption"),
    }

    # KN230 tester D-1（2026-09-21）：(abbr, toc 目录名) 复合键归并——同一
    # 缩写对不同书都合法、且 conf 50 子串通道连中文书名都落成了一版书的值
    # （SOURCE_BOOK_ABBREVIATIONS[abbr] 直出）时，须按 toc 目录段判定真实出处。
    # ("AA", "冒险者的军械库2") → AA2：CHMTocPathProvider 子串匹配把 toc
    # 「未整理 → 冒险者的军械库2 → 专长」先命中 "AA"（conf 50，早于 toc '?' 映射
    # 与引用块兜底），军械库2 各 doc 落值成一书缩写。
    # 判定证据两路：chunk.chm_toc_path（md_mapping 直查已落值时）；或源 organized
    # 文件的「> 来源：…未整理 → X → Y」行（BackfillChmTocPath 步骤 3 同源的
    # RE_SRC_PATH 口径——步骤 1 时部分 doc 的 toc 尚未回填，如
    # 冒险者的军械库2_专长，空 toc 不能当无证据放过）。doc 级缓存只读一次。
    # 与 FIX_LEGACY 同口径（任意通道产出即改、幂等），toc 目录段级判定非
    # 文件名特判。
    FIX_LEGACY_BY_BOOK = {
        "AA": ("AA2", "冒险者的军械库2", "Adventurer's Armory 2", "冒险者的军械库2"),
    }

    ORGANIZED = "pf_rules_md_organized"
    RE_SRC_PATH = re.compile(r"未整理\s*→[^\n，。]*")

    def _toc_evidence(self, doc_files: dict, doc: str, toc: str) -> str:
        """toc 判定证据：chunk 自身 toc + 源 organized 文件来源行路径（doc 级缓存并集）。"""
        if not hasattr(self, "_srcpath_cache"):
            self._srcpath_cache = {}
        if doc not in self._srcpath_cache:
            path = doc_files.get(doc)
            self._srcpath_cache[doc] = " ⑊ ".join(
                p.strip() for p in self.RE_SRC_PATH.findall(
                    open(path, encoding="utf-8").read())) if path else ""
        return (toc or "") + " ⑊ " + self._srcpath_cache[doc]

    # 跨书索引类：不映射，保持 '?'（metadata.source 已就位的造物专长一览除外，
    # 由步骤 2 promote 专处理；page_1367 设计保留）
    SKIP_DOCS = {"page_1367", "造物专长一览"}

    def run(self, output_dir: Path, report_dir: Optional[Path] = None) -> Dict[str, Any]:
        chunks_path = output_dir / "chunks.jsonl"
        report_dir = report_dir or type(self).DEFAULT_REPORT_DIR
        lines = open(chunks_path, encoding="utf-8").readlines()
        shutil.copy(chunks_path, str(chunks_path) + ".bak_chm_toc")

        applied = Counter()
        legacy_fixed = 0
        unknown_after = Counter()
        changed = []
        section_idx = -1   # SECTION_MAPPING 当前分节（按 doc 内 chunk 顺序推进）
        last_doc = None
        # organized doc_id → 源文件路径（FIX_LEGACY_BY_BOOK 的 toc 证据回查用，
        # 口径同 BackfillChmTocPath：stem 索引、先到者为主）
        doc_files = {}
        for p in glob.glob(os.path.join(self.ORGANIZED, "**", "*.md"), recursive=True):
            doc_files.setdefault(os.path.splitext(os.path.basename(p))[0], p)

        for i, line in enumerate(lines):
            o = json.loads(line)
            doc = o["doc_id"]
            if doc != last_doc:
                last_doc = doc
                section_idx = 0 if doc in self.SECTION_MAPPING else -1
            # KN230 分节映射（先于 '?' 的 doc 粒度映射）：一 doc 多书合集按
            # 源文件章节边界把 chunk 归到具体书（page_538 三 Champions 合集）
            if section_idx >= 0 and o["book_abbreviation"] in ("?", "CoP/CoB/CoC"):
                bounds = self.SECTION_MAPPING[doc]
                while section_idx + 1 < len(bounds) and o.get("title") == bounds[section_idx + 1][0]:
                    section_idx += 1
                abbr, cn, en = bounds[section_idx][1]
                o["book_abbreviation"] = abbr
                o["book_name_cn"] = cn
                o["book_name_en"] = en
                o["source_confidence"] = 70
                applied[abbr] += 1
                changed.append((i, doc, "分节", abbr))
            elif o["book_abbreviation"] == "?":
                if doc in self.MAPPING:
                    abbr, cn, en = self.MAPPING[doc]
                    o["book_abbreviation"] = abbr
                    o["book_name_cn"] = cn
                    o["book_name_en"] = en
                    o["source_confidence"] = 70
                    applied[abbr] += 1
                    changed.append((i, doc, "?", abbr))
                elif doc in self.SKIP_DOCS:
                    unknown_after[doc] += 1
                else:
                    print(f"⚠️ 未知文件未在映射表也未在跳过清单: doc_id={doc} toc={o['chm_toc_path']}")
            elif o["book_abbreviation"] in self.FIX_LEGACY:
                old_abbr = o["book_abbreviation"]
                abbr, cn, en = self.FIX_LEGACY[old_abbr]
                o["book_abbreviation"] = abbr
                o["book_name_cn"] = cn
                o["book_name_en"] = en
                legacy_fixed += 1
                changed.append((i, doc, old_abbr, abbr))
            elif o["book_abbreviation"] in self.FIX_LEGACY_BY_BOOK:
                # KN230 D-1：(缩写, toc 目录段/源文件来源行) 复合键归并（AA+军械库2 → AA2）
                old_abbr = o["book_abbreviation"]
                abbr, cn, en, toc_mark = self.FIX_LEGACY_BY_BOOK[old_abbr]
                if toc_mark in self._toc_evidence(doc_files, doc, o.get("chm_toc_path", "")):
                    o["book_abbreviation"] = abbr
                    o["book_name_cn"] = cn
                    o["book_name_en"] = en
                    legacy_fixed += 1
                    changed.append((i, doc, old_abbr, abbr))
            else:
                # 映射表里已有的 doc 若值不一致则警告（防映射表与既有值漂移）
                if doc in self.MAPPING and self.MAPPING[doc][0] != o["book_abbreviation"]:
                    print(f"⚠️ 已判来源 doc 与映射表不一致: doc_id={doc} 既有={o['book_abbreviation']} 映射表={self.MAPPING[doc][0]}")

            lines[i] = json.dumps(o, ensure_ascii=False) + "\n"

        with open(chunks_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        n_applied = sum(applied.values())
        unknown_left = sum(unknown_after.values())
        report_dir.mkdir(parents=True, exist_ok=True)
        report = [
            "# chm_toc_path 映射套用报告（finalize 步骤 1，2026-08-03 迁移）",
            "",
            f"- 总 chunks：{len(lines)}",
            f"- 映射套用：**{n_applied}**，涉及 {len(applied)} 本书",
            f"- 既有残缺/脏值修正：**{legacy_fixed}**（FIX_LEGACY：'Handbook'/'Dragonslayer' → DSH、CAMPAIGN → PCS、ArcaneAnthology → ArAn、CoP/CoB/CoC → CoPur/CoBal/CoCorr；FIX_LEGACY_BY_BOOK：AA+冒险者的军械库2 → AA2）",
            f"- 未知剩余：**{unknown_left}**（设计保留 {dict(unknown_after) or '无'}）",
            "",
        ]
        with open(report_dir / "chm_toc_mapping_report.md", "w", encoding="utf-8") as f:
            f.write("\n".join(report) + "\n")
        return {"applied": n_applied, "legacy_fixed": legacy_fixed, "unknown_left": unknown_left}


# ============================================================
#  步骤 2：造物专长一览行内来源顶层提升（顺序 2，不可变）
# ============================================================


class ApplyFeatCreationSourcePromote:
    """造物专长一览行内来源顶层提升（任务 #70，2026-08-02）。

    背景：造物专长一览.md 是跨书索引（28 列表行 + 26 正文/子条目），来源判定链按
    doc_id 无法判定（步骤 1 的 SKIP_DOCS 保持 '?'），但行内【缩写】标注与正文
    出处行已解析到 metadata.source。本步骤把 source → 顶层 book 三字段，
    conf=65（与判定链「行内来源标注」档一致）。

    source 三形态：列表行标注 / 正文出处行 / 空 source 条目归属补源。
    只改顶层 book 字段与 source_confidence，不动 text / title / metadata / chunk_id。
    幂等：book != '?' 后不再命中。
    """

    DOC_ID = "造物专长一览"
    # 报告目录（类属性，子类覆写防跨类目覆盖）
    DEFAULT_REPORT_DIR = Path("docs/专长")

    SOURCE_CONFIDENCE = 65  # 行内来源标注档（与判定链 65 一致）

    # 列表行【标注】→ 顶层书字段（值与既有体系对齐）
    SRC_KEY_TO_BOOK = {
        "CRB":  ("CRB", "核心规则书", "Core Rulebook"),
        "B1":   ("B1", "怪物图鉴", "Bestiary 1"),
        "AM":   ("AM", "炼金术手册", "Alchemy Manual"),
        "AA2":  ("AA2", "冒险者的军械库2", "Adventurer's Armory 2"),
        "CoC":  ("CoCorr", "秽邪勇士", "Champions of Corruption"),
        "UW":   ("UW", "极限荒野", "Ultimate Wilderness"),
        "HA":   ("HA", "恐怖冒险", "Horror Adventures"),
        "CaC":  ("CaC", "部属与伙伴", "Cohorts and Companions"),
        "HHH":  ("HHH", "闹鬼英雄手册", "Haunted Heroes Handbook"),
        "BM":   ("BM", "黑市指南", "Black Markets"),
        "ISM":  ("ISM", "内海魔法", "Inner Sea Magic"),
        "MHH":  ("MHH", "怪物猎人手册", "Monster Hunter's Handbook"),
        "HoG":  ("HoG", "格拉里昂英雄", "Heroes of Golarion"),
        "PotW": ("PotW", "废土子民", "People of the Wastes"),
        # Pathfinder Adventure Path 期刊（新缩写，PF_缩写表.md 同步登记）
        "#16": ("PF16", "Endless Night", "Pathfinder #16: Endless Night"),
        "#74": ("PF74", "Sword of Valor", "Pathfinder #74: Sword of Valor"),
        "#5":  ("PF5", "Sins of the Saviors", "Pathfinder #5: Sins of the Saviors"),
    }

    # 正文出处行书名 → 标注（无【】标注的正文条目出处）
    TITLE_TO_KEY = {
        "Adventurer's Armory 2": "AA2",
        "Horror Adventures": "HA",
        "Cohorts and Companions": "CaC",
        "Haunted Heroes Handbook": "HHH",
    }

    # 期刊出处行：'Pathfinder #N: Name pg. X'
    _JOURNAL_RE = re.compile(r"^Pathfinder #(\d+):")

    # 空 source 条目归属补源：列表行标注回溯（正文条目与列表行同名）+ 子物品归属。
    # D1（2026-09-18）：补 7 个 CRB 造物专长（列表行【CRB】标注回溯，源文件
    # 顶部列表可证：调制药剂/制造魔法武器和防具/制造法杖/制造魔杖/制造奇物/
    # 锻造戒指/抄写卷轴均【CRB】）——修复后专长 '?' 清零至 page_1367 92 条。
    FALLBACK_TITLE = {
        "抵异作成": "PotW",
        "制造构装体": "B1",
        "创造泥怪": "AM",
        "胶质怪": "AM", "灰泥怪": "AM", "滑行猎手": "AM", "赭冻怪": "AM",
        "黑布丁怪": "AM", "岩浆怪": "AM", "死亡陷阱怪": "AM", "肉食晶簇": "AM",
        "制造影钉": "CoC",
        "制造强化火器": "PotW",
        "奇植培育": "UW",
        "灌法毒药": "BM",
        "施法者刺青": "ISM", "贮法刺青": "ISM", "法术刺青": "ISM",  # 绘制魔法刺青【ISM】子物品
        "强固作成": "PotW",
        "调制药剂": "CRB", "制造魔法武器和防具": "CRB", "制造法杖": "CRB",
        "制造魔杖": "CRB", "制造奇物": "CRB", "锻造戒指": "CRB", "抄写卷轴": "CRB",
    }

    def resolve_key(self, source: str, title: str) -> Optional[str]:
        """source → 标注 key；空 source 或出处行无法识别时走条目归属补源。

        D1（2026-09-18）：原实现对「source 非空但无法识别」直接返回 None
        （如锻造戒指 chunk 因相邻子条目粘连混入 '**Source Monster Hunter's
        Handbook pg. 24' 行，按条目归属应归 CRB）——现改为先尝试出处行识别，
        未识别再回退 FALLBACK_TITLE（title 归属），仍无命中才返回 None。"""
        src = (source or "").strip()
        if src:
            if src in self.SRC_KEY_TO_BOOK:
                return src
            m = self._JOURNAL_RE.match(src)
            if m:
                return "#" + m.group(1)
            for name, key in self.TITLE_TO_KEY.items():
                if src.startswith(name):
                    return key
            # 出处行无法识别 → 条目归属补源兜底（D1）
            return self.FALLBACK_TITLE.get(title)
        return self.FALLBACK_TITLE.get(title)

    def run(self, output_dir: Path, report_dir: Optional[Path] = None) -> Dict[str, Any]:
        chunks_path = output_dir / "chunks.jsonl"
        lines = open(chunks_path, encoding="utf-8").readlines()
        shutil.copy(chunks_path, str(chunks_path) + ".bak_src_promote")

        applied = Counter()
        by_route = Counter()  # src_标注 / src_出处 / src_期刊 / fallback
        unresolved = []

        for i, line in enumerate(lines):
            o = json.loads(line)
            if o.get("doc_id") != self.DOC_ID or o.get("book_abbreviation") != "?":
                continue
            md = o.get("metadata", {}) or {}
            src = md.get("source")
            title = o.get("title", "")
            key = self.resolve_key(src, title)
            if key is None:
                unresolved.append((i, title, src))
                continue
            book = self.SRC_KEY_TO_BOOK[key]
            o["book_abbreviation"], o["book_name_cn"], o["book_name_en"] = book
            o["source_confidence"] = self.SOURCE_CONFIDENCE
            applied[key] += 1
            by_route["src_标注" if (src or "").strip() in self.SRC_KEY_TO_BOOK
                     else "src_期刊" if self._JOURNAL_RE.match((src or "").strip())
                     else "src_出处" if (src or "").strip()
                     else "fallback"] += 1
            lines[i] = json.dumps(o, ensure_ascii=False) + "\n"

        with open(chunks_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        n = sum(applied.values())
        return {"promoted": n, "routes": dict(by_route), "unresolved": len(unresolved)}


# ============================================================
#  步骤 3：page_1367 超魔专长一览 × 全库同名唯一书 join 回填
#  （KN228 方案，2026-10-28 拍板；顺序 3，插在 promote 之后、
#   BackfillChmTocPath 之前——「新增不重排」，顺序约束不变）
# ============================================================


class ApplyFeatMetamagicIndexJoin:
    """page_1367（超魔专长一览）来源归书：全库同名唯一书 join 回填（KN228）。

    背景：page_1367 是跨书混排索引（速查表行 + 详细段），步骤 1 SKIP_DOCS 保持
    '?'（92 条）。本步骤在 chunks.jsonl 落盘后全库快照上 join：page_1367 条目
    × 库内同名条目（中文 title 或英文别名命中）唯一书推断来源。

    join 源：book != "?" 且非 page_1367 自身、component_type ∈ {feat, feat_index}
    （拍板探针口径——ISM/DH 等书仅有 feat_index 行承载超魔专长，唯一直达
    feat 行会漏配；1367 自身整页排除防自引用）。键归一：中文 title 去空白；
    英文别名 strip+lower+剥【…】后缀+压单空格。sorted(chunk_id) 遍历 + 集合
    语义，与遍历序无关，产物可复现。

    回填规则（仅 page_1367 且 book=="?" 的 chunk，幂等硬契约）：
    - 键命中唯一书 且 title ∈ WHITELIST（64 条拍板探针证据常量）→ 回填三书
      字段（cn/en 取被命中 chunk 的库内权威值），source_confidence=55
      （引用块显式标记 65 与纯正文提及 50 之间），metadata["source_backfill"]
      证据块（method/matched_key/matched_chunk_id）。
    - 命中唯一书 但 title ∉ WHITELIST → 跳过 + 报告（红线结构性护栏：探针
      之外新发现能配上停下报告，不回填）。
    - 多书冲突 → 默认不动；唯一例外 CONFLICT_OVERRIDES（拍板决策 2）：
      「水生法术」→ UW（极限荒野：水生/自然环境主题原书 + 专长11→UW 既有
      映射先例 feat_chain.py MAPPING）。
    - 无命中 → 不动，保持 "?"（27 条遗留，不做外部考据）。
    只改 book 三字段 / source_confidence / metadata.source_backfill，不动
    text/title/aliases/chunk_id。
    """

    DOC_ID = "page_1367"
    DEFAULT_REPORT_DIR = Path("docs/专长")

    SOURCE_CONFIDENCE = 55  # 库内同名推断档（拍板 Q2）

    # 冲突裁决（拍板决策 2，唯一允许的条目级特判）：title → abbr
    CONFLICT_OVERRIDES = {"水生法术": "UW"}

    # 白名单（拍板 Q1 方案 a）：2026-10-28 探针重跑导出的 64 条唯一命中 title
    # 常量。join 命中但 title 不在清单内 → 跳过并报告（探针之外新发现停下报告）。
    WHITELIST = frozenset([
        "侦查召唤", "元素法术", "创痕法术", "剧毒法术", "卓越法术", "及远法术",
        "咸水法术", "哄骗法术", "回音法术", "威胁幻影", "实体幽影", "广域法术",
        "延续法术", "弹性法术", "强化法术", "强固法术", "影握法术", "感染法术",
        "慈悯法术", "扰咒法术", "拟鬼之术", "时髦法术", "晦暗法术", "暴怒法术",
        "暴雷法术", "本能法术", "死圣法术", "法术击倒", "法术升阶", "法术增远",
        "法术定法", "法术延时", "法术强效", "法术扩展", "法术极效", "法术瞬发",
        "法术穿刺", "法术默发", "浑浊法术", "深海法术", "激励法术", "燃烧法术",
        "甄选法术", "眩晕法术", "短暂法术", "纯净法术", "苍翠法术", "蒸汽法术",
        "触发医疗法术", "诡诈法术", "跨界法术", "轻快法术", "辐影法术", "通灵法术",
        "逻辑法术", "闪耀法术", "限制法术", "集中法术", "震荡法术", "霉咒法术",
        "霜冻法术", "顽强法术", "骇人法术", "魔宠法术",
    ])

    @staticmethod
    def _norm_cn(s: str) -> str:
        return "".join((s or "").split())

    @staticmethod
    def _norm_en(s: str) -> str:
        s = (s or "").strip().lower()
        s = re.sub(r"【[^】]*】\s*$", "", s).strip()
        return " ".join(s.split())

    def _keys(self, chunk: dict) -> tuple:
        """匹配键元组（sorted 保确定性——set 迭代序随进程哈希随机化，
        两次 build matched_key/源 chunk 会漂移，产物可复现性硬要求）。"""
        keys = {self._norm_cn(chunk.get("title", ""))}
        keys |= {self._norm_en(a) for a in chunk.get("aliases", []) or []}
        return tuple(sorted(k for k in keys if k))

    def run(self, output_dir: Path, report_dir: Optional[Path] = None) -> Dict[str, Any]:
        chunks_path = output_dir / "chunks.jsonl"
        report_dir = report_dir or type(self).DEFAULT_REPORT_DIR
        with open(chunks_path, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]

        # join 源：book 已定稿且非 1367 自身的条目/索引行；key → abbr → 源 chunk
        key_to_books: Dict[str, Dict[str, dict]] = {}
        for c in sorted(rows, key=lambda x: x["chunk_id"]):
            if c.get("doc_id") == self.DOC_ID or c.get("book_abbreviation", "?") == "?":
                continue
            if c.get("component_type") not in ("feat", "feat_index"):
                continue
            for k in self._keys(c):
                key_to_books.setdefault(k, {}).setdefault(
                    c["book_abbreviation"], c)

        applied = Counter()
        blocked = []      # 白名单外命中（红线：停下报告）
        conflicts = []    # 多书冲突（override 之外）
        unresolved = 0
        for r in rows:
            if r.get("doc_id") != self.DOC_ID or r.get("book_abbreviation") != "?":
                continue
            hit: Dict[str, tuple] = {}   # abbr -> (matched_key, src_chunk)
            for k in self._keys(r):
                for abbr, src in key_to_books.get(k, {}).items():
                    hit.setdefault(abbr, (k, src))
            title = r.get("title", "")
            if not hit:
                unresolved += 1
                continue
            if len(hit) > 1:
                override = self.CONFLICT_OVERRIDES.get(title)
                if override is None or override not in hit:
                    conflicts.append((title, sorted(hit)))
                    continue
                abbr = override
                k, src = hit[abbr]
            else:
                abbr = next(iter(hit))
                k, src = hit[abbr]
                if title not in self.WHITELIST:
                    blocked.append((title, abbr, k))
                    continue
            r["book_abbreviation"] = abbr
            r["book_name_cn"] = src["book_name_cn"]
            r["book_name_en"] = src["book_name_en"]
            r["source_confidence"] = self.SOURCE_CONFIDENCE
            md = r.setdefault("metadata", {})
            md["source_backfill"] = {
                "method": "feat_metamagic_index_join",
                "matched_key": k,
                "matched_chunk_id": src["chunk_id"],
            }
            applied[abbr] += 1

        shutil.copyfile(chunks_path, str(chunks_path) + ".bak_mmjoin")
        with open(chunks_path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        report_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# 超魔专长一览（page_1367）来源归书报告（KN228，finalize 步骤 3）",
            "",
            f"> join 回填 **{sum(applied.values())}** 条，涉及 {len(applied)} 本书",
            f"> 保持 '?'：{unresolved} 条（库内无命中，不做外部考据）",
            f"> 多书冲突未裁决：{len(conflicts)} 条",
            f"> 白名单外命中（未回填，须停下报告）：{len(blocked)} 条",
            "",
            "| 书 | 条数 |",
            "|---|---|",
        ]
        for abbr, n in applied.most_common():
            lines.append(f"| {abbr} | {n} |")
        if blocked:
            lines += ["", "## 白名单外命中（红线护栏触发，未回填）", ""]
            for t, ab, k in blocked:
                lines.append(f"- {t} → {ab}（key={k}）")
        if conflicts:
            lines += ["", "## 多书冲突未裁决（保持 '?'）", ""]
            for t, abs_ in conflicts:
                lines.append(f"- {t} → {', '.join(abs_)}")
        with open(report_dir / "metamagic_index_join_report.md", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return {
            "applied": sum(applied.values()),
            "by_book": dict(applied),
            "unresolved": unresolved,
            "conflicts": len(conflicts),
            "blocked": len(blocked),
        }

class BackfillChmTocPath:
    """chm_toc_path 空回填（来源书链路修复方案 §三 断点 B）。

    背景：83 个 organized doc（1348 chunks）chm_toc_path 为空——MdMappingTocProvider
    按 md_mapping.json（2141 条，CHM 转换产物）文件名查，organized 整理文件不在映射。

    organized 文件内两类来源信号（均验证 100% 覆盖）：
      注释：<!-- XX-source:源md路径:条目标题 --> → 源 md basename → md_map toc_path
      来源行：> 来源：…未整理 → X → Y → 直接提取路径
    三级回填：
      ① chunk title 命中条目级注释标题 → 注释对应 toc（章节级粒度，80/83 文件可查）
      ② 未命中 → 文件级 toc（来源行路径：46 文件唯一；37 条目级文件取公共前缀）
      ③ 清洗：路径段含 .md 丢弃；源名含 + 的怪格式（DR 魔法技艺.md+专长9.md）跳过注释走 ②

    只改顶层 chm_toc_path，不动 text/title/metadata/chunk_id。幂等：空值填一次。
    """

    # 报告目录（类属性，子类覆写防跨类目覆盖）
    DEFAULT_REPORT_DIR = Path("docs/专长")

    MD_MAP = "../md_mapping.json"          # 相对 phase1 cwd（pipeline 运行目录）
    ORGANIZED = "pf_rules_md_organized"

    # 注释：<!-- XX-source:源md路径:条目标题 -->（前缀可为中文，如 秽邪勇士-source）
    RE_ANNO = re.compile(r"<!--\s*(.+?)-source:([^:]+?):(.+?)\s*-->")
    # 来源行路径：> 来源：…，未整理 → X → Y（路径以「未整理 →」起始，段以 → 分隔）
    RE_SRC_PATH = re.compile(r"未整理\s*→[^\n，。]*")

    @staticmethod
    def norm_title(t: str) -> str:
        """title 归一化（去全部空白）供注释标题匹配"""
        return re.sub(r"\s+", "", t or "")

    @staticmethod
    def longest_common_prefix_paths(paths: list) -> str:
        """多路径取段级最长公共前缀（37 条目级文件的文件级兜底）"""
        parts_list = [p.split("→") for p in paths]
        common = []
        for segs in zip(*parts_list):
            if len(set(s.strip() for s in segs)) == 1:
                common.append(segs[0].strip())
            else:
                break
        return " → ".join(common)

    @staticmethod
    def clean_toc(toc: str) -> str:
        """清洗：路径段含 .md / page_ 的丢弃（MSH 一条混入 page_667.md）"""
        segs = [s.strip() for s in toc.split("→")]
        keep = [s for s in segs if ".md" not in s and not s.startswith("page_")]
        return " → ".join(keep)

    def _resolve_doc_file(self, doc_files: dict, doc_id: str) -> Optional[str]:
        """doc_id → organized 源文件路径（扩展点，子类可覆写）。

        默认按 doc_id 精确查（源文件 stem 索引）。equipment 子类覆写：
        消歧 doc_id（`__{父目录}` 后缀，同 stem 重复 5 对文件）剥后缀回源
        stem，否则消歧 doc 的回填全落空（unfilled 40，2026-08-09）。
        """
        return doc_files.get(doc_id)

    def run(self, output_dir: Path, report_dir: Optional[Path] = None) -> Dict[str, Any]:
        chunks_path = output_dir / "chunks.jsonl"
        report_dir = report_dir or type(self).DEFAULT_REPORT_DIR
        with open(self.MD_MAP, encoding="utf-8") as f:
            md_map = json.load(f)

        # doc_id → organized 文件路径（stem 匹配）
        doc_files = {}
        for p in glob.glob(os.path.join(self.ORGANIZED, "**", "*.md"), recursive=True):
            stem = os.path.splitext(os.path.basename(p))[0]
            doc_files.setdefault(stem, p)

        with open(chunks_path, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]

        empty = [r for r in rows if not r.get("chm_toc_path", "").strip()]

        # 按 doc 预解析：注释映射 + 文件级 toc
        doc_meta = {}
        for doc_id in sorted({r["doc_id"] for r in empty}):
            path = self._resolve_doc_file(doc_files, doc_id)
            if not path:
                doc_meta[doc_id] = {"title_toc": {}, "file_toc": ""}
                continue
            text = open(path, encoding="utf-8").read()
            title_toc = {}
            for prefix, src_raw, anno_title in self.RE_ANNO.findall(text):
                src = os.path.basename(src_raw)  # 去子目录前缀（专长/page_369.md → page_369.md）
                if "+" in src or ".md" not in src:
                    continue  # DR 怪格式（魔法技艺.md+专长9.md）跳过注释，走文件级兜底
                entry = md_map.get(src)
                if not entry or not entry.get("toc_path"):
                    continue
                toc = self.clean_toc(entry["toc_path"])
                title_toc.setdefault(self.norm_title(anno_title), toc)
            # 来源行路径（文件级 toc）
            src_paths = self.RE_SRC_PATH.findall(text)
            if src_paths:
                paths = [self.clean_toc(p.strip()) for p in src_paths if p.strip()]
                paths = [p for p in paths if p]
                if len(set(paths)) == 1:
                    file_toc = paths[0]
                else:
                    file_toc = self.longest_common_prefix_paths(paths)
            else:
                file_toc = ""
            doc_meta[doc_id] = {"title_toc": title_toc, "file_toc": file_toc}

        # 回填
        stats = Counter()
        unfilled_docs = Counter()
        for r in empty:
            meta = doc_meta.get(r["doc_id"], {"title_toc": {}, "file_toc": ""})
            toc = meta["title_toc"].get(self.norm_title(r["title"]))
            if toc:
                r["chm_toc_path"] = toc
                stats["chunk 级（注释）"] += 1
            elif meta["file_toc"]:
                r["chm_toc_path"] = meta["file_toc"]
                stats["文件级（来源行）"] += 1
            else:
                unfilled_docs[r["doc_id"]] += 1

        # 备份 + 写回
        shutil.copyfile(chunks_path, str(chunks_path) + ".bak_tocfix")
        with open(chunks_path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        report_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# chm_toc_path 回填报告（finalize 步骤 4，2026-08-03 迁移）",
            "",
            f"> 回填 {sum(stats.values())} / {len(empty)}（doc {len(doc_meta)} 个）",
            f"> 依据：来源书链路修复方案 §三 断点 B（三级链路）",
            "",
            f"| 级别 | 数量 |",
            f"|---|---|",
            f"| ① chunk 级（注释源 md → md_map toc） | {stats['chunk 级（注释）']} |",
            f"| ② 文件级（`> 来源：` 行路径） | {stats['文件级（来源行）']} |",
            f"| 未回填 | {sum(unfilled_docs.values())} |",
            "",
        ]
        with open(report_dir / "chm_toc_backfill_report.md", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return {"filled": sum(stats.values()), "total_empty": len(empty), "unfilled": sum(unfilled_docs.values())}


# ============================================================
#  步骤 4：metadata.source 补齐（顺序 4，不可变）
# ============================================================


class BackfillFeatSource:
    """metadata.source 补齐（可解析未解析的 656 个）。

    背景：text 含 `> 来源：` 引用块（如 `> 来源：武器大师手册（Weapon Master's
    Handbook），页码见原书，未整理 → …`），book 四字段已由 resolve_source 解析
    （conf=65），但 metadata.source 未填——引用块不是 `**来源：**` 标签形态，
    _SRC_LABELS_RE 匹配不到。

    复用 resolve_source 的 _RE_SOURCE_LINE（cn/en 提取，验证 656/656 = 100%），
    填 metadata.source = 中文名（English Name）——与来源行字面一致。
    只填缺失，不动已有；只改 metadata.source。幂等：非空不再处理。
    """

    # 报告目录（类属性，子类覆写防跨类目覆盖）
    DEFAULT_REPORT_DIR = Path("docs/专长")

    RE_LINE = re.compile(r"^\s*> 来源：", re.M)

    def run(self, output_dir: Path, report_dir: Optional[Path] = None) -> Dict[str, Any]:
        # 懒导入：feat_chain ↔ feat 互相引用（feat.POSTPROCESSORS ←→ 本模块
        # _RE_SOURCE_LINE），模块加载期 import 会循环导入；run 调用期两模块必已就绪
        from vectorizer.processors.feat import _RE_SOURCE_LINE

        chunks_path = output_dir / "chunks.jsonl"
        report_dir = report_dir or type(self).DEFAULT_REPORT_DIR
        with open(chunks_path, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]

        empty = [r for r in rows if not r.get("metadata", {}).get("source")]

        filled = 0
        by_type = Counter()
        for r in empty:
            if not self.RE_LINE.search(r.get("text", "")):
                continue  # 无来源行 → 不可解析（feat 正文 3057 / 速查表行 1843 等）
            m = _RE_SOURCE_LINE.search(r["text"])
            if not m or not m.group(1):
                continue
            cn = m.group(1).strip()
            en = (m.group(2) or "").strip()
            r["metadata"]["source"] = f"{cn}（{en}）" if en else cn
            filled += 1
            by_type[r["component_type"]] += 1

        shutil.copyfile(chunks_path, str(chunks_path) + ".bak_srcfix")
        with open(chunks_path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        total_src = sum(1 for r in rows if r.get("metadata", {}).get("source"))
        report_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# metadata.source 补齐报告（finalize 步骤 5，2026-08-03 迁移）",
            "",
            f"> 补齐 {filled} 个 → metadata.source 非空 {total_src} / {len(rows)}",
            "",
            "| component_type | 补齐数 |",
            "|---|---|",
        ]
        for k, v in by_type.most_common():
            lines.append(f"| {k} | {v} |")
        with open(report_dir / "source_补齐报告.md", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return {"filled": filled, "total_source": total_src}
