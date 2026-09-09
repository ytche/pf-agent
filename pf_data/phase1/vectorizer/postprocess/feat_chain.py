"""feat_chain.py — 专长后处理链四步骤（v2.2 决策 A：pipeline finalize 阶段）

迁移自 phase1 根目录四脚本（apply_chm_toc_mapping / apply_feat_creation_source_promote /
backfill_chm_toc_path / backfill_feat_source），重构为「类 + run() 函数式接口」——
每个步骤类提供 `run(output_dir, report_dir=None) -> dict`（返回统计，pipeline logger 打印）。

执行顺序（POSTPROCESSORS 声明序 = 本模块顺序，**不可变**，教训 B1）：
  1. ApplyChmTocMapping — chm_toc_path → 书缩写映射套用（大部分 doc 的 book）
  2. ApplyFeatCreationSourcePromote — 造物专长一览行内来源顶层提升（专处理
     apply 保持 '?' 的跨书索引 doc）
  3. BackfillChmTocPath — chm_toc_path 空三级链路回填（只填缺失）
  4. BackfillFeatSource — metadata.source 补齐（只填缺失）

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
    2. 顺带修正既有残缺缩写：'Handbook'（屠龙者手册）→ DSH。
    3. 跨书索引类不映射：page_1367 超魔专长一览、造物专长一览（保持 '?'，
      由步骤 2 promote 专处理）。

    只改顶层 book 字段，不动 text / title / metadata / chunk_id——chunk 结构与
    verify_feats.py 判别器不变量不变。幂等：'?' 处理一次后不再命中。
    """

    DEFAULT_REPORT_DIR = Path("docs/专长")

    # doc_id → (book_abbreviation, book_name_cn, book_name_en)
    # 值与既有体系对齐（既有同书值直接复用；无则用缩写表标准缩写；无缩写用中文名）。
    # 依据见 docs/专长/chm_toc_path_映射表.md。
    MAPPING = {
        # --- organized 专长目录 ---
        "page_856": ("UI", "极限诡道", "Ultimate Intrigue"),
        "page_321": ("ISG", "内海诸神", "Inner Sea Gods"),
        "page_361": ("护甲大师手册", "护甲大师手册", "Armor Master's Handbook"),
        "page_311": ("OA", "异能冒险", "Occult Adventures"),
        "page_200": ("UCa", "极限战役", "Ultimate Campaign"),
        "page_555": ("近战战术工具箱", "近战战术工具箱", "Melee Tactics Toolbox"),
        "page_556": ("DTT", "阴招战术工具箱", "Dirty Tactics Toolbox"),
        "page_194": ("CRB", "核心规则书", "Core Rulebook"),
        "page_276": ("ISC", "内海战斗", "Inner Sea Combat"),
        "page_500": ("ACO", "进化职业起源", "Advanced Class Origins"),
        "page_538": ("CoP/CoB/CoC", "纯洁/平衡/秽邪勇士", "Champions of Purity/Balance/Corruption"),
        "page_201": ("B1", "怪物图鉴", "Bestiary 1"),
        "page_552": ("RTT", "远程战术工具箱", "Ranged Tactics Toolbox"),
        "page_561": ("CEoD", "切利亚斯，魔鬼帝国", "Cheliax, Empire of Devils"),
        "page_673": ("F&P", "信仰与哲学", "Faiths and Philosophies"),
        "page_670": ("HotHC", "皇庭英豪", "Heroes of the High Court"),
        "page_505": ("亡灵杀手手册", "亡灵杀手手册", "Undead Slayer's Handbook"),
        "page_529": ("DH", "冒险家手册", "Dungeoneer's Handbook"),
        "page_509": ("格拉里昂的半身人", "格拉里昂的半身人", "Halflings of Golarion"),
        "page_531": ("STLC", "萨加瓦，失落的殖民地", "Sargava, The Lost Colony"),
        "page_744": ("异能奥秘", "异能奥秘", "Occult Mysteries"),
        "page_527": ("瓦瑞西亚，传说诞生之地", "瓦瑞西亚，传说诞生之地", "Varisia, Birthplace of Legends"),
        "page_950": ("CRB", "核心规则书", "Core Rulebook"),
        # KN109 纳入（2026-08-04）：MA 神话冒险引言页（神话专长/超魔专长类别介绍）
        "page_622": ("MA", "神话冒险", "Mythic Adventures"),
        # --- 未整理目录 ---
        "专长11": ("UW", "极限荒野", "Ultimate Wilderness"),
        "专长": ("秽邪勇士", "秽邪勇士", "Champions of Corruption"),
        "专长41": ("ISR", "内海种族", "Inner Sea Races"),
        "专长33": ("平衡勇士", "平衡勇士", "Champions of Balance"),
        "专长1": ("MHH", "怪物猎人手册", "Monster Hunter's Handbook"),
        "专长24": ("HftF", "缘界英雄", "Heroes from the Fringe"),
        "专长45": ("任务与战役", "任务与战役", "Quests and Campaigns"),
        "page_820": ("DSH", "屠龙者手册", "Dragonslayer's Handbook"),
        "专长51": ("巨人猎手手册", "巨人猎手手册", "Giant Slayer's Handbook"),
        "专长7": ("AM", "炼金术手册", "Alchemy Manual"),
        "闹鬼专长": ("HHH", "闹鬼英雄手册", "Haunted Heroes Handbook"),
        "专长28": ("OO", "异能源始", "Occult Origins"),
        "专长36": ("SH", "间谍大师手册", "Spymaster's Handbook"),
        "专长52": ("格拉里昂的侏儒", "格拉里昂的侏儒", "Gnomes of Golarion"),
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
        "专长56": ("ArcaneAnthology", "秘术选集", "Arcane Anthology"),
        "专长57": ("CaC部属与伙伴", "部属与伙伴", "Cohorts and Companions"),
        "专长6": ("THH", "哈罗牌手册", "Tarot Heroes Handbook"),
        "专长12": ("PHH", "位面行者手册", "Plane-Hopper's Handbook"),
        "专长37": ("BotC", "巫团血脉", "Blood of the Coven"),
        "专长44": ("PotS", "沙之子民", "People of the Sands"),
        "专长48": ("格拉里昂的地精", "格拉里昂的地精", "Goblins of Golarion"),
        "专长5": ("DA", "神术选集", "Divine Anthology"),
        "专长55": ("ISI", "内海诡道", "Inner Sea Intrigue"),
        "专长18": ("PotN", "北地居民", "People of the North"),
        "专长25": ("MM", "魔法市集指南", "Magical Marketplace"),
        "专长27": ("2", "冒险者的军械库2", "Adventurer's Armory 2"),
        "专长35": ("格拉里昂的混种", "格拉里昂的混种", "Bastards of Golarion"),
        "专长50": ("格拉里昂的矮人", "格拉里昂的矮人", "Dwarves of Golarion"),
        "专长31": ("格拉里昂的半身人", "格拉里昂的半身人", "Halflings of Golarion"),
        "专长54": ("巨人再临", "巨人再临", "Giants Revisited"),
        "专长15": ("SoS", "秘密探寻者", "Seekers of Secrets"),
        "专长8": ("繁星子民", "繁星子民", "People of the Stars"),
        "专长17": ("F&P", "信仰与哲学", "Faiths and Philosophies"),
        "专长20": ("再探经典宝藏", "再探经典宝藏", "Classic Treasures Revisited"),
        "专长23": ("BotE", "元素血脉", "Blood of the Elements"),
        "专长26": ("冒险者的军械库", "冒险者的军械库", "Adventurer's Armory"),
        "专长29": ("格拉里昂的兽人", "格拉里昂的兽人", "Orcs of Golarion"),
        "专长32": ("AH", "反英雄手册", "Antihero's Handbook"),
        "专长34": ("巨龙再临", "巨龙再临", "Dragons Revisited"),
        "专长43": ("ASoL", "安多安，自由之魂", "Andoran, Spirit of Liberty"),
        "专长46": ("格拉里昂的狗头人", "格拉里昂的狗头人", "Kobolds of Golarion"),
        "专长47": ("亡灵杀手手册", "亡灵杀手手册", "Undead Slayer's Handbook"),
        "其他专长2": ("MAH", "武术手册", "Martial Arts Handbook"),
    }

    # 既有残缺缩写统一修正：'Handbook'（屠龙者手册）→ DSH
    FIX_LEGACY = {
        "Handbook": ("DSH", "屠龙者手册", "Dragonslayer's Handbook"),
    }

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

        for i, line in enumerate(lines):
            o = json.loads(line)
            doc = o["doc_id"]
            if o["book_abbreviation"] == "?":
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
                abbr, cn, en = self.FIX_LEGACY[o["book_abbreviation"]]
                o["book_abbreviation"] = abbr
                o["book_name_cn"] = cn
                o["book_name_en"] = en
                legacy_fixed += 1
                changed.append((i, doc, "Handbook", abbr))
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
            f"- 既有残缺修正：**{legacy_fixed}**（'Handbook' → DSH，屠龙者手册）",
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
        "AA2":  ("2", "冒险者的军械库2", "Adventurer's Armory 2"),
        "CoC":  ("秽邪勇士", "秽邪勇士", "Champions of Corruption"),
        "UW":   ("UW", "极限荒野", "Ultimate Wilderness"),
        "HA":   ("HA", "恐怖冒险", "Horror Adventures"),
        "CaC":  ("CaC部属与伙伴", "部属与伙伴", "Cohorts and Companions"),
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

    # 空 source 条目归属补源：列表行标注回溯（正文条目与列表行同名）+ 子物品归属
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
    }

    def resolve_key(self, source: str, title: str) -> Optional[str]:
        """source → 标注 key；空 source 走条目归属补源。返回 None 表示未识别。"""
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
            return None  # 未识别的出处（调用方告警）
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
#  步骤 3：chm_toc_path 空三级链路回填（顺序 3，不可变）
# ============================================================


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
            "# chm_toc_path 回填报告（finalize 步骤 3，2026-08-03 迁移）",
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
            "# metadata.source 补齐报告（finalize 步骤 4，2026-08-03 迁移）",
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
