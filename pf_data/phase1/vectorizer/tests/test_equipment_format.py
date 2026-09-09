"""
test_equipment_format.py — 装备格式解析 TDD 测试（test_seeds.jsonl 驱动）

数据源：vectorizer/exploration/equipment/test_seeds.jsonl（9 条：7 positive + 2 negative）
驱动方：装备模块 M3 TDD 批次 1（formats/equipment.py）
断言口径：EquipmentFormat.normalize → promote → split_into_items 产出的 item dict：
  type（item/category/intro）/ title / title_en / text / fields（规范 key →
  值）/ source / format_cluster

字段断言依赖 registry_equipment.EQUIP_FIELD_LABEL_ALIASES 归一（全角ＣＬ、
灵氲、同义变体 → 规范 key），M2 §二 字段表即断言清单。
"""

import json
from pathlib import Path

from vectorizer.formats.equipment import EquipmentFormat

SEEDS_PATH = Path(__file__).parent.parent / "exploration" / "equipment" / "test_seeds.jsonl"


def load_seeds():
    with open(SEEDS_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


SEEDS = load_seeds()


def run(raw: str, source_name: str = "seed") -> list:
    """EquipmentFormat 全链：normalize → promote → split"""
    fmt = EquipmentFormat()
    text = fmt.normalize(raw)
    text = fmt.promote(text)
    return fmt.split_into_items(text, source_name=source_name)


def by_type(items: list, typ: str) -> list:
    return [it for it in items if it.get("type") == typ]


class TestEquipmentSeeds:
    """9 条 test_seeds 逐条断言"""

    # ---------- positive ----------

    def test_seed_00_h2_book_fields(self):
        """[0] A 形态：H2 条目 + 来源行 + 星壳重复去重 + 字段链"""
        items = run(SEEDS[0]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个条目，实际 {len(it)}"
        item = it[0]
        assert item["title"] == "符文守护纹身"
        # 双空格清洗（E5 英文名双空格 → 单空格）
        assert item["title_en"] == "Runeward Tattoo"
        # 字段归一：全角ＣＬ → caster_level；位置 → slot
        assert item["fields"]["aura"] == "微弱预言系"
        assert item["fields"]["caster_level"] == "1"
        assert item["fields"]["slot"] == "无"
        assert item["fields"]["price"] == "1000gp"
        assert item["fields"]["weight"] == "无"
        # 来源行挂条目（H2 → 来源行顺序）
        assert "MM" in item["source"]
        # 正文保真
        assert "侦测魔法" in item["text"]

    def test_seed_01_b_space_fields(self):
        """[1] B 形态毒药家族：**标签** 空格值 + 跨行值续行 + 行内嵌字段"""
        items = run(SEEDS[1]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 2, f"应产 2 个条目（鸡蛇唾液/提琴背毒），实际 {len(it)}"
        first = it[0]
        assert first["title"] == "鸡蛇唾液"
        assert first["title_en"] == "Cockatrice Spit"
        # 跨行值续行：**类型** 标签行 + 续行值
        assert first["fields"]["类型"] == "毒素，接触，伤口，摄入"
        # 同行值 + 续行（持续 4 \n轮 → "持续 4 轮"）
        assert first["fields"]["频率"] == "1次/每轮，持续 4 轮"
        # 值续行 2 行 + 分号链完整
        assert "敏捷伤害" in first["fields"]["效果"]
        assert "解除石化" in first["fields"]["效果"]
        assert first["fields"]["痊愈"] == "1 次豁免"
        assert first["fields"]["price"] == "1,000 gp"
        # 空格形态：类型/豁免 ∈ extra 词表（原文保真 key）
        second = it[1]
        assert second["title"] == "提琴背毒"

    def test_seed_02_star_broken_title(self):
        """[2] 跨行断行标题 join（E8 两形态之一）：**鲫鱼胶笺（Remora \\npad）**"""
        items = run(SEEDS[2]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个条目，实际 {len(it)}"
        item = it[0]
        assert item["title"] == "鲫鱼胶笺"
        assert item["title_en"] == "Remora pad"
        # 分号双字段同行；行尾句号为正文标点不属字段值（_RE_FIELD_SEG
        # lookahead 截断设计，同 price `5GP` 无标点）
        assert item["fields"]["price"] == "5GP"
        assert item["fields"]["weight"] == "1/2磅"
        # 正文保真（行内断行英文名保留）
        assert "被擒抱" in item["text"]

    def test_seed_03_category_title(self):
        """[3] 类别标题 + 闭壳借位正文（**常见物品（Mundane Items）**无尽市场…）"""
        items = run(SEEDS[3]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个条目，实际 {len(it)}"
        item = it[0]
        assert item["title"] == "常见物品"
        assert item["title_en"] == "Mundane Items"
        # 闭壳借位：正文并入 text
        assert "无尽市场" in item["text"]

    def test_seed_04_isg_quad_star(self):
        """[4] ISG 四星壳章节标题（无字段 → category）"""
        items = run(SEEDS[4]["raw_snippet"], source_name="内海诸神ISG_魔法武器.md")
        cat = by_type(items, "category")
        assert len(cat) == 1, f"应产 1 个 category（魔法武器），实际 {len(cat)}"
        assert cat[0]["title"] == "魔法武器"
        assert cat[0]["title_en"] == "Magic Weapons"
        # 章节导言并入 text
        assert "圣徒" in cat[0]["text"]

    def test_seed_05_dual_field_forms(self):
        """[5] 裸标题 + 双形态字段（E5）：H2 去重 + **中文 English** + 裸字段行"""
        items = run(SEEDS[5]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个条目（H2 去重），实际 {len(it)}"
        item = it[0]
        assert item["title"] == "蛇咬刺青"
        assert item["title_en"] == "Serpentine Tattoo"
        # 裸字段行（`灵光 昏暗咒法系 CL1`，行首词 ∈ 词表）——M5 英文
        # 标签识别后 `CL` ∈ 词表 → 拆 key（同 seed_76 拆 key 口径）：
        # aura=昏暗咒法系、caster_level=1（`CL1` 紧贴形态，CL 标签+数字值）
        assert item["fields"]["aura"] == "昏暗咒法系"
        assert item["fields"]["caster_level"] == "1"

    def test_seed_08_isg_quad_star_broken(self):
        """[8] ISG 跨行标题（**戒指**** \\nRings****）"""
        items = run(SEEDS[8]["raw_snippet"], source_name="内海诸神ISG_戒指.md")
        cat = by_type(items, "category")
        assert len(cat) == 1, f"应产 1 个 category（戒指），实际 {len(cat)}"
        assert cat[0]["title"] == "戒指"
        assert cat[0]["title_en"] == "Rings"

    def test_seed_09_bare_cn_en_title(self):
        """[9] 裸行中文(英文)标题开条目（焦油炸弹(Tar Bomb) + 出处行守卫）"""
        items = run(SEEDS[9]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个条目（焦油炸弹），实际 {len(it)}"
        assert it[0]["title"] == "焦油炸弹"
        assert it[0]["title_en"] == "Tar Bomb"
        # 冒号字段行（价格：/类型：/效果：）走 ④ 链式解析进字段
        assert "15gp" in it[0]["fields"].get("price", "")
        assert "炼金武器" in it[0]["fields"].get("类型", "")
        # 出处行保真进正文
        assert "内海海盗" in it[0]["text"]

    def test_seed_10_bare_title_doc_head_negative(self):
        """[10] 文件头导言裸行负例：后随空行+分隔线 → 不产条目（纽梅利亚液体）"""
        items = run(SEEDS[10]["raw_snippet"])
        assert not by_type(items, "item"), "文件头导言裸行不应产条目"
        assert not by_type(items, "category"), "文件头导言裸行不应产类别条目"

    def test_seed_11_isc_giant_line(self):
        """[11] ISC 四星壳巨行：章节 category + 行内条目切分（蜂刺之吻）"""
        items = run(SEEDS[11]["raw_snippet"], source_name="内海战斗ISC_魔法武器.md")
        cat = by_type(items, "category")
        assert len(cat) == 1, f"应产 1 个 category（武器），实际 {len(cat)}"
        assert cat[0]["title"] == "武器"
        assert cat[0]["title_en"] == "Weapons"
        # 章节导言并入 category text
        assert "内海地区" in cat[0]["text"]
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item（蜂刺之吻），实际 {len(it)}"
        item = it[0]
        assert item["title"] == "蜂刺之吻"
        assert item["title_en"] == "Calistrian Kiss"
        # 单侧错位星壳归位（位置**： → **位置**：）+ 字段链
        assert item["fields"]["slot"] == "无"
        assert item["fields"]["price"] == "26380gp"
        assert item["fields"]["caster_level"] == "7级"
        assert item["fields"]["weight"] == "7磅"
        assert item["fields"]["aura"] == "中等死灵系"
        assert "Craft Magic Arms and Armor" in item["fields"]["craft_requirements"]
        assert item["fields"]["craft_cost"] == "13380gp"
        # 正文保真（字段链后粘连正文段）
        assert "黄蜂" in item["text"]

    def test_seed_12_isg_bare_item(self):
        """[12] ISG 条目行无 ** 前缀：全视护甲（patron + ③裸标签字段链）"""
        items = run(SEEDS[12]["raw_snippet"], source_name="内海诸神ISG_魔法武器.md")
        cat = by_type(items, "category")
        assert len(cat) == 1, f"应产 1 个 category（魔法护甲和盾牌），实际 {len(cat)}"
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item（全视护甲），实际 {len(it)}"
        item = it[0]
        assert item["title"] == "全视护甲"
        assert item["title_en"] == "All-Seeing Armor"
        assert item["fields"].get("patron") == "内希斯"
        assert item["fields"]["slot"] == "护甲"
        assert item["fields"]["caster_level"] == "3"
        assert item["fields"]["price"] == "5570GP"
        assert item["fields"]["weight"] == "25磅"
        assert item["fields"]["aura"] == "微弱预言系"
        # 正文续行（非星壳行）并入 text
        assert "链甲衫" in item["text"]

    def test_seed_13_value_continuation_guard(self):
        """[13] 值续行终止守卫：--- 与裸标题行终止续行（氧气罐不被前件字段吞并）"""
        items = run(SEEDS[13]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 2, f"应产 2 个 item（恒星寻路仪/氧气罐），实际 {len(it)}"
        first, second = it[0], it[1]
        assert first["title"] == "恒星寻路仪"
        assert first["title_en"] == "Wayfinder of the stars"
        # 制造需求字段值 = 首行 + 续行，不含 --- 与氧气罐（值续行终止守卫）
        cr = first["fields"].get("craft_requirements", "")
        assert "35,100gp" in cr and "跨位面传送术" in cr
        assert "---" not in cr and "氧气罐" not in cr
        # 氧气罐独立开条目：裸标题 + 出处行守卫 + 正文保真
        # （`效果：` 行走 ④ 冒号字段解析进 EXTRA 保真字段，非 text）
        assert second["title"] == "氧气罐"
        assert second["title_en"] == "Compressed air"
        assert "呼吸装置" in second["fields"].get("效果", "")

    # ---------- negative ----------

    def test_seed_14_isg_crossline_item(self):
        """[14] ISG 条目行无 ** 前缀 + 跨行四星壳标题（猎手扳指）：
        _RE_ISG_TITLE_OPEN 需前缀可选才能 join 跨行条目（seed_08 仅测
        跨行章节带前缀、seed_12 仅测单行条目——跨行条目是盲区）"""
        items = run(SEEDS[14]["raw_snippet"], source_name="内海诸神ISG_魔法护甲和盾牌.md")
        cat = by_type(items, "category")
        assert len(cat) == 1, f"应产 1 个 category（戒指），实际 {len(cat)}"
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item（猎手扳指），实际 {len(it)}"
        item = it[0]
        assert item["title"] == "猎手扳指"
        assert item["title_en"] == "Deadeye`s Spotter Ring"
        assert item["fields"].get("patron") == "埃拉斯蒂尔"
        assert item["fields"]["slot"] == "戒指"
        assert item["fields"]["caster_level"] == "5"
        assert item["fields"]["price"] == "1500GP"
        assert item["fields"]["weight"] == "-"
        assert item["fields"]["aura"] == "微弱变化"
        # ③裸标签形态：制造需求 → craft_requirements / 花费 → craft_cost
        assert "锻造戒指" in item["fields"]["craft_requirements"]
        assert item["fields"]["craft_cost"] == "750GP"
        # 正文续行（非星壳行）并入 text
        assert "鹿角" in item["text"]

    def test_seed_15_isc_crossline_chapter(self):
        """[15] ISC 巨行章节标题四星嵌套跨行（**护甲（**** \\nArmor****）****）：
        _RE_ISC_TITLE_UNCLOSED 括号后是 `****`（星）非英文，需支持四星开壳
        才能 join（seed_11 仅测单行章节——跨行章节是盲区）"""
        items = run(SEEDS[15]["raw_snippet"], source_name="内海战斗ISC_魔法护甲和盾牌.md")
        cat = by_type(items, "category")
        assert len(cat) == 1, f"应产 1 个 category（护甲），实际 {len(cat)}"
        assert cat[0]["title"] == "护甲"
        assert cat[0]["title_en"] == "Armor"
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item（碎脊板甲），实际 {len(it)}"
        item = it[0]
        assert item["title"] == "碎脊板甲"
        assert item["title_en"] == "Backbreaker Mail"
        assert item["fields"]["slot"] == "护甲"
        assert item["fields"]["price"] == "17650gp"
        assert item["fields"]["caster_level"] == "10级"
        assert item["fields"]["weight"] == "45磅"
        assert item["fields"]["aura"] == "中等幻术系和变化系"
        # 制造要求值跨行续行（（Craft \\nMagic Arms）→ 空格 join）+ 制造成本
        cr = item["fields"]["craft_requirements"]
        assert "Craft Magic Arms and Armor" in cr
        assert item["fields"]["craft_cost"] == "9025gp"
        # 正文保真
        assert "鞣制皮革" in item["text"]

    def test_seed_16_isc_adjacent_items(self):
        """[16] ISC 巨行多条目：字段闭壳紧贴条目头（`9025gp**黑衫制服
        （Blackjacket）位置**：`）——lookbehind 不排除 `\\*` 才能切出
        第 2+ 条目（seed_11 仅 1 条目——紧贴形态是盲区）"""
        items = run(SEEDS[16]["raw_snippet"], source_name="内海战斗ISC_魔法护甲和盾牌.md")
        it = by_type(items, "item")
        assert len(it) == 2, f"应产 2 个 item（碎脊板甲/黑衫制服），实际 {len(it)}"
        first, second = it[0], it[1]
        assert first["title"] == "碎脊板甲"
        assert first["title_en"] == "Backbreaker Mail"
        assert first["fields"]["price"] == "17650gp"
        assert first["fields"]["craft_cost"] == "9025gp"
        assert second["title"] == "黑衫制服"
        assert second["title_en"] == "Blackjacket"
        assert second["fields"]["price"] == "28700gp"
        assert second["fields"]["slot"] == "护甲"
        assert second["fields"]["weight"] == "20磅"

    def test_seed_17_isg_bare_star_crossline(self):
        """[17] ISG 条目行 B 形态裸星标题跨行（**法视护腕Spellsight \\n
        Bracer（内希斯）**）：中文+英文无星壳粘连开壳（非四星壳）——
        _RE_ISG_TITLE_OPEN 只 join 四星壳形态，B 形态裸星开壳是盲区"""
        items = run(SEEDS[17]["raw_snippet"], source_name="内海诸神ISG_奇物.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item（法视护腕），实际 {len(it)}"
        item = it[0]
        assert item["title"] == "法视护腕"
        assert item["title_en"] == "Spellsight Bracer"
        # B 形态（patron 括号无四星壳）→ patron 提取
        assert item["fields"].get("patron") == "内希斯"
        assert item["fields"]["slot"] == "腕部"
        assert item["fields"]["caster_level"] == "5"
        assert item["fields"]["price"] == "2100GP"
        assert item["fields"]["weight"] == "1磅"
        assert item["fields"]["aura"] == "微弱防护系"
        # 正文续行并入 text
        assert "侦测魔法" in item["text"]

    def test_seed_18_isg_sep_and_double_star(self):
        """[18] ISG 神坛标题连接符 + 双星闭壳：
        凯登****．****凯利恩神坛（四星内嵌全角点）→ title 拼回「凯登．凯利恩神坛」；
        Altar of Desna**（双星闭壳，非四星）→ 闭壳 4 星可降为 2 星"""
        items = run(SEEDS[18]["raw_snippet"], source_name="内海诸神ISG_神坛.md")
        it = by_type(items, "item")
        assert len(it) == 2, f"应产 2 个 item（凯登/戴斯娜神坛），实际 {len(it)}"
        first, second = it[0], it[1]
        assert first["title"] == "凯登．凯利恩神坛"
        assert first["title_en"] == "Altar of Cayden Cailean"
        assert first["fields"]["slot"] == "无"
        assert first["fields"]["price"] == "8000GP"
        # ③裸标签字段行：制造需求/花费（seed_12/14 同形态）
        assert "制造奇物" in first["fields"].get("craft_requirements", "")
        assert first["fields"].get("craft_cost") == "4000GP"
        assert second["title"] == "戴斯娜神坛"
        assert second["title_en"] == "Altar of Desna"
        assert second["fields"]["aura"] == "中等防护系和附魔系[邪恶，守序]"

    def test_seed_19_ff_quadstar_nested(self):
        """[19] 魔宠手记 FF 四星嵌套巨行（英文被四星包裹 + & 章节标题）：
        `**装备与魔法物品（****Equipment & Magic Items****）****导言…条目1条目2…`——
        章节产 category（英文组须含 &）+ 条目头 `水族球（****Aquarium  Ball****）
        ****价格**：`（括号内英文四星包裹、字段 ①B 错位星左邻 4 星不归位、
        制造成本**：左邻句号归位）"""
        items = run(SEEDS[19]["raw_snippet"], source_name="魔宠手记FF_装备与魔法物品.md")
        cats = by_type(items, "category")
        assert len(cats) == 1, f"应产 1 个 category（装备与魔法物品），实际 {len(cats)}"
        assert cats[0]["title"] == "装备与魔法物品"
        assert cats[0]["title_en"] == "Equipment & Magic Items"
        it = by_type(items, "item")
        assert len(it) == 2, f"应产 2 个 item（水族球/羽叶甲），实际 {len(it)}"
        aqua, feather = it[0], it[1]
        assert aqua["title"] == "水族球"
        assert aqua["title_en"] == "Aquarium Ball"  # 双空格清洗
        assert aqua["fields"]["price"] == "80gp"
        assert aqua["fields"]["weight"] == "20磅"
        assert aqua["fields"]["craft_cost"] == "40gp"
        assert "制造奇物" in aqua["fields"].get("craft_requirements", "")
        assert feather["title"] == "羽叶甲"
        assert feather["title_en"] == "Featherleaf Barding"
        assert feather["fields"]["slot"] == "护甲"
        assert feather["fields"]["price"] == "7310gp"
        assert feather["fields"]["caster_level"] == "9级"
        assert feather["fields"]["weight"] == "1磅"
        assert feather["fields"]["aura"] == "微弱变化系"
        assert feather["fields"]["craft_cost"] == "3660gp"

    def test_seed_20_purity_quadstar_nested(self):
        """[20] 纯洁勇士四星嵌套（源数据修复后）：
        章节 `**魔法物品：****`（标签+四星闭壳）→ category；条目头
        `**破缚者之靴（****bondbreaker's boots****）****价格：**`（** 前缀 +
        ①A 星壳内冒号字段 + 弯撇号归一）；Rythius 英文前缀形态
        `**Rythius****，链魔之灾（****Rythius****，****the kyron scourge****）****`
        ——四星夹逗号连接符归一 → title=英文前缀，中文名"""
        items = run(SEEDS[20]["raw_snippet"], source_name="格拉里昂的纯洁勇士_魔法物品.md")
        cats = by_type(items, "category")
        assert len(cats) == 1, f"应产 1 个 category（魔法物品），实际 {len(cats)}"
        assert cats[0]["title"] == "魔法物品"
        it = by_type(items, "item")
        assert len(it) == 3, f"应产 3 个 item（破缚者之靴/魔鬼之匙/Rythius），实际 {len(it)}"
        boots, key, rythius = it[0], it[1], it[2]
        assert boots["title"] == "破缚者之靴"
        assert boots["title_en"] == "bondbreaker's boots"
        assert boots["fields"]["price"] == "1,600gp"
        assert boots["fields"]["aura"] == "微弱变化系"
        assert "制造奇物专长" in boots["fields"].get("造物", "")
        assert "割穿捆绑穿戴者" in boots["text"]
        assert key["title"] == "魔鬼之匙"
        assert key["title_en"] == "devil's key"
        assert key["fields"]["price"] == "66,750GP"
        assert rythius["title"] == "Rythius，链魔之灾"
        assert rythius["title_en"] == "Rythius，the kyron scourge"
        assert rythius["fields"]["price"] == "53,000gp"
        assert rythius["fields"]["aura"] == "强大防护系与塑能系光环"

    def test_seed_21_field_chain_not_title(self):
        """[21] 字段链负例：`**类型**：炼金药…；**工艺（炼金）**：DC 15；`
        是条目后字段行，`_RE_STAR_TITLE_FULL` 组1 惰性 `. +?` 会把
        `（炼金）**：` 当闭壳把字段行误切为条目（title 含星 `类型**：…`）——
        组1 须排除 `*`/`（` 字符类（KN160 星壳家族守卫）"""
        items = run(SEEDS[21]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 1, f"字段行不应产伪条目，应 1 个（炼金油膏），实际 {len(it)}"
        assert it[0]["title"] == "炼金油膏"
        assert "*" not in it[0]["title"], "title 不应含星壳残留"
        joined = it[0]["text"] + json.dumps(it[0]["fields"], ensure_ascii=False)
        assert "炼金药" in joined, "字段行内容应保留在字段/正文"

    def test_seed_22_quadstar_head_after_open_subtitle(self):
        """[22] 无闭壳子节标题后接四星条目头：`**武器详述`（OPEN 行）+
        `****飞钩杖（Aklys）**：`——join 不得把子节标题与条目头连吞
        （组1 含星 → title 污染 `武器详述 ****飞钩杖`）；四星条目头
        `\\*{2,4}` 前缀须可匹配（B 形态条目头变体）"""
        items = run(SEEDS[22]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item（飞钩杖），实际 {len(it)}"
        assert it[0]["title"] == "飞钩杖"
        assert it[0]["title_en"] == "Aklys"
        assert "*" not in it[0]["title"], "title 不应含星壳残留"
        assert "飞钩杖是一把钩形" in it[0]["text"]

    def test_seed_23_field_split_lines(self):
        """[23] 字段分行形态（武器大师手册/永罪之书）：`**价格**` 标签独立行
        + `：+1加值；` 值行（`：` 前缀须剥、分号剥除）；`：— 正文` 同行
        （重量值 `—` 后跟正文 → 值=`—` 正文归 text）；裸标签行
        `制造成本 ：+1加值`（行首词 ∈ 词表）不得被 weight 值续行吞并"""
        items = run(SEEDS[23]["raw_snippet"], source_name="武器大师手册_魔法武器.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item（推力），实际 {len(it)}"
        item = it[0]
        assert item["title"] == "推力"
        assert item["title_en"] == "Driving"
        f = item["fields"]
        assert f.get("price") == "+1加值", f"price={f.get('price')!r}"
        assert f.get("aura") == "中等塑能系", f"aura={f.get('aura')!r}"
        assert f.get("weight") == "—", f"weight={f.get('weight')!r}"
        assert f.get("craft_cost") == "+1加值", f"craft_cost={f.get('craft_cost')!r}"
        assert "制造魔法武器和防具" in f.get("craft_requirements", ""), \
            f"craft_requirements={f.get('craft_requirements')!r}"
        assert "这个特殊能力仅能够加持在远程武器上" in item["text"], \
            "`：—` 同行正文应归 text"

    def test_seed_24_img_prefix_value_line(self):
        """[24] AA2 图片前缀 + 跨行星壳标题 + 值行独立形态：
        `![[图片]](url) **明海茶道用茶叶（Minkaian Ceremonial ⏎Tea）**`
        （图片前缀不剥 → 标题不开条目，条目头残渣 `Tea）**` 进 text、
        字段挂错条目）；`**重量**⏎5磅⏎正文`（值行完整无 `；` 结尾 →
        吞入后 break，正文归 text）；`**重量**⏎–⏎正文`（dash 值行）"""
        items = run(SEEDS[24]["raw_snippet"], source_name="AA2来自海外的装备.md")
        it = by_type(items, "item")
        assert len(it) == 3, f"应 3 个 item，实际 {len(it)}"
        t2 = it[1]
        assert t2["title"] == "明海茶道用茶叶", f"title={t2['title']!r}"
        assert t2["title_en"] == "Minkaian Ceremonial Tea"
        assert t2["fields"].get("price") == "900 gp", \
            f"price={t2['fields'].get('price')!r}"
        assert t2["fields"].get("weight") == "5磅", \
            f"weight={t2['fields'].get('weight')!r}"
        assert "对天洲文化" in t2["text"], "值行后正文应归 text"
        t3 = it[2]
        assert t3["title"] == "白银舞衣", f"title={t3['title']!r}"
        assert t3["fields"].get("price") == "200 gp"
        assert t3["fields"].get("weight") == "–", \
            f"weight={t3['fields'].get('weight')!r}"
        assert "除了跟普通舞衣" in t3["text"], "dash 值行后正文应归 text"
        assert not any("Tea）**" in itm["text"] or "Garb）**" in itm["text"]
                       for itm in it), "跨行标题残渣不应留在 text"

    def test_seed_25_isg_quadstar_prefix_head(self):
        """[25] ISG 四星前缀条目头 + QGthE 裸头形态：
        `****司命匕首**** Fate Blade ****（法莱斯玛）****字段链`（四星前缀，
        ISG_TITLE 前缀只认双星 → 条目头 sink 进上一条目 text、字段进正文）；
        `希里没药Healy  Myrrh****灵光**：…`（无星号前缀、无 `（神名）`，
        四星在英文名后 → 整行丢弃/字段挂错；英文名双空格为转换残迹，
        _clean_en 归一双空格——H2 权威形态 `希里没药 Healy Myrrh` 单空格）"""
        items = run(SEEDS[25]["raw_snippet"], source_name="内海诸神ISG_奇物.md")
        it = by_type(items, "item")
        assert len(it) == 3, f"应 3 个 item，实际 {len(it)}（{it}）"
        names = [x["title"] for x in it]
        assert names == ["经久之花", "司命匕首", "希里没药"], f"titles={names}"
        t2 = it[1]
        assert t2["title_en"] == "Fate Blade", f"title_en={t2['title_en']!r}"
        assert t2["fields"].get("price") == "2500GP", \
            f"price={t2['fields'].get('price')!r}"
        assert "法莱斯玛" in t2["fields"].get("patron", ""), \
            f"patron={t2['fields'].get('patron')!r}"
        assert "司命匕首是一把寒铁匕首" in t2["text"]
        t3 = it[2]
        assert t3["title_en"] == "Healy Myrrh", f"title_en={t3['title_en']!r}"
        assert t3["fields"].get("price") == "50gp", \
            f"price={t3['fields'].get('price')!r}"
        assert "这种药膏" in t3["text"]
        assert not any("****司命匕首" in x["text"] or "Myrrh****" in x["text"]
                       for x in it), "条目头不应残留在 text"

    def test_seed_26_ctt_glue_title(self):
        """[26] 紧邻标题行（CTT 家族）：`震击护符AMULET OF QUAKING STRIKES`
        中文+英文无括号无星壳，后随裸字段行/裸标签行（+续行值）"""
        items = run(SEEDS[26]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 2, f"应 2 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "震击护符", f"title={t1['title']!r}"
        assert t1["title_en"] == "AMULET OF QUAKING STRIKES"
        # 裸字段行（空格形态）价格；裸标签行+续行值（位置/灵光/CL）
        assert t1["fields"].get("price") == "28,000 GP", \
            f"price={t1['fields'].get('price')!r}"
        assert "颈部" in t1["fields"].get("slot", ""), \
            f"slot={t1['fields'].get('slot')!r}"
        assert t1["fields"].get("caster_level") == "15级", \
            f"cl={t1['fields'].get('caster_level')!r}"
        assert "强烈塑能系" in t1["fields"].get("aura", ""), \
            f"aura={t1['fields'].get('aura')!r}"
        assert "青铜护符" in t1["text"]
        t2 = it[1]
        assert t2["title"] == "锚定护腕", f"title={t2['title']!r}"
        assert t2["title_en"] == "ANCHORING BRACERS"

    def test_seed_27_hftf_colon_field_chain(self):
        """[27] 冒号字段行+链式（HftF 家族）：`价格：3600 金币`、
        `位置：肩部 施法者等级：1 级 重量：1 磅`（空格分隔多字段链）"""
        items = run(SEEDS[27]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 2, f"应 2 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "遁影披风"
        assert t1["title_en"] == "Elusion Cloak"
        f1 = t1["fields"]
        assert f1.get("price") == "3600 金币", f"price={f1.get('price')!r}"
        assert f1.get("slot") == "肩部", f"slot={f1.get('slot')!r}"
        assert f1.get("caster_level") == "1 级", \
            f"cl={f1.get('caster_level')!r}"
        assert f1.get("weight") == "1 磅", f"weight={f1.get('weight')!r}"
        # 灵光值尾 `灵光` 为源数据残渣，保真（登记 KN）
        assert "微弱幻术系" in f1.get("aura", "")
        assert f1.get("craft_cost") == "1800gp", \
            f"craft_cost={f1.get('craft_cost')!r}"
        assert f1.get("craft_requirements") == "制造奇物，脚底抹油", \
            f"req={f1.get('craft_requirements')!r}"
        assert "芒吉莽原" in t1["text"]
        assert it[1]["title"] == "散射投石索"

    def test_seed_28_iswg_bracket_star_glue(self):
        """[28] ISWG 武器家族：星壳紧邻标题（`**奥多里决斗剑Aldori…**`）、
        【】字段链（`花费【12gp】`）、空格字段链（`价格 20gp 重量 3 磅.`）"""
        items = run(SEEDS[28]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 2, f"应 2 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "围巾刃/刃巾", f"title={t1['title']!r}"
        assert t1["title_en"] == "Bladed Scarf"
        # 【】字段链：花费→craft_cost、伤害（s）→damage（小写 s 归一大写）；
        # 伤害（s）/伤害（m）大小体型两段同 key 合并（保真不覆盖）
        assert t1["fields"].get("craft_cost") == "12gp", \
            f"craft_cost={t1['fields'].get('craft_cost')!r}"
        damage = t1["fields"].get("damage", "")
        assert "1d4" in damage and "1d6" in damage, f"damage={damage!r}"
        assert t1["fields"].get("subcategory") == "异种武器", \
            f"sub={t1['fields'].get('subcategory')!r}"
        t2 = it[1]
        assert t2["title"] == "奥多里决斗剑"
        assert t2["title_en"] == "Aldori Dueling Sword"
        # 空格字段链值含后续标签（粗粒度，登记 KN）
        assert "20gp" in t2["fields"].get("price", "")
        assert "1d6" in t2["fields"].get("damage", "")
        assert t2["fields"].get("subcategory") == "单手异种", \
            f"sub={t2['fields'].get('subcategory')!r}"

    def test_seed_29_giant_comment_item(self):
        """[29] GIANT 家族：注释行跳过 + 括号标题 + 冒号字段行 +
        来源块在条目**后**（挂当前条目）"""
        items = run(SEEDS[29]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 2, f"应 2 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "精金锁链"
        assert t1["title_en"] == "AdamantineChain"
        assert t1["fields"].get("price") == "3030gp", \
            f"price={t1['fields'].get('price')!r}"
        assert t1["fields"].get("weight") == "2磅"
        assert "巨人猎手手册" in t1["source"], \
            f"source={t1['source']!r}"
        assert it[1]["title"] == "秘银锁链"

    def test_seed_30_elf_star_en_title(self):
        """[30] 星壳英文标题（精灵附魔箭矢）：`领队箭**Clustershot**`——
        开壳在英文名后（中文名无星前缀）；冒号字段链 + 值尾标点剥除"""
        items = run(SEEDS[30]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 2, f"应 2 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "领队箭"
        assert t1["title_en"] == "Clustershot", \
            f"title_en={t1['title_en']!r}"
        # `位置：无，价格：+1` 链式：slot 值尾 `，` 剥除、price=+1
        assert t1["fields"].get("slot") == "无", \
            f"slot={t1['fields'].get('slot')!r}"
        assert t1["fields"].get("price") == "+1", \
            f"price={t1['fields'].get('price')!r}"
        # `灵光：微弱变化系，施法者等级5`——`施法者等级5` 无冒号，
        # 非标签 → 整段并入 aura 值（保真粗粒度）
        assert "微弱变化系" in t1["fields"].get("aura", "")
        assert "螺旋状的花纹" in t1["text"]
        t2 = it[1]
        assert t2["title"] == "医者之殇"
        # 弯撇号归一（normalize 层）：’ → '
        assert t2["title_en"] == "Healer's Sorrow"

    def test_seed_31_h2_no_paren_item(self):
        """[31] H2 无括号条目（军械库2 家族）：`## 忍者服` 后随星壳
        字段行 → 开条目（原被当章节标题跳过，条目全丢）"""
        items = run(SEEDS[31]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 2, f"应 2 个 item，实际 {len(it)}（{it}）"
        assert it[0]["title"] == "忍者服", f"title={it[0]['title']!r}"
        assert it[0]["fields"].get("price") == "50 GP"
        assert "忍者服" in it[0]["text"]
        assert it[1]["title"] == "链甲衫"
        assert it[1]["fields"].get("price") == "150 GP"

    def test_seed_32_pop_h2_source_item(self):
        """[32] PoP 家族：H2 无括号 + `> 来源：` 行 + 后随裸行括号 tail
        标题（`划空裂隙护腕（Rift-Rending Bracers）【腕部奇物】出自…`）
        → 开条目；title 剥 H1 词前缀（`PlanesOfPowerPoP ` 前缀污染）"""
        items = run(SEEDS[32]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "划空裂隙护腕", f"title={t1['title']!r}"
        assert t1["title_en"] == "Rift-Rending Bracers", \
            f"title_en={t1['title_en']!r}"
        # 裸行括号 tail 标题 + 空格字段行（粗粒度保真）
        assert "出自《位面之力》" in t1["text"]
        assert "腕部" in t1["fields"].get("slot", "")
        assert "18000GP" in t1["fields"].get("price", "")
        assert "操念使" in t1["text"]
        assert "Planes of Power" in t1["source"]

    def test_seed_06_pnp_not_leak(self):
        """[6] P&P 法术条目负例：括号内 markdown 链接 → 不产装备 item（KN163）
        （法术正文段走 intro 暂存，文件级排除在 processor/pipeline 层）"""
        items = run(SEEDS[6]["raw_snippet"])
        assert not by_type(items, "item"), "法术条目不应泄漏为装备条目"
        assert not by_type(items, "category"), "法术条目不应泄漏为类别条目"

    def test_seed_07_bare_para_no_item(self):
        """[7] 纯正文段负例：非标题非字段（句号结尾正文）→ 不产 item"""
        items = run(SEEDS[7]["raw_snippet"])
        assert not by_type(items, "item"), "正文段不应产条目"
        assert not by_type(items, "category"), "正文段不应产类别条目"

    # ---------- B1 无星流式（RTT/月之血脉/动物档案 断条家族，M3 收尾）----------

    def test_seed_33_b1_rtt_flow(self):
        """[33] B1 流式：GLUE 跨行标题拼接（Alchemist's Atlatl）+ 类别前缀
        「奇物」剥离 + 行内标题切分（暗杀瞄准镜）+ ④链字段；正文中
        长距射击longshot（UC）不误判标题"""
        items = run(SEEDS[33]["raw_snippet"], "远程战术工具箱RTT_奇物.md")
        it = by_type(items, "item")
        assert len(it) == 2, f"应 2 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "炼金掷镖器", f"title={t1['title']!r}"
        assert t1["title_en"] == "Alchemist's Atlatl", f"en={t1['title_en']!r}"
        assert t1["fields"]["slot"] == "无"
        assert t1["fields"]["caster_level"] == "1"
        assert t1["fields"]["weight"] == "2磅"
        assert t1["fields"]["aura"] == "微弱变化系"
        assert t1["fields"]["price"] == "1500gp"
        assert "制造奇物、长距射击longshot（UC）" in t1["fields"].get("craft_conditions", "")
        assert t1["fields"]["craft_cost"] == "750gp"
        assert "掷镖器看起来" in t1["text"]
        t2 = it[1]
        assert t2["title"] == "暗杀瞄准镜", f"title={t2['title']!r}"
        assert t2["title_en"] == "Assassin's Sight"
        assert t2["fields"]["price"] == "5250gp"
        assert t2["fields"]["craft_cost"] == "2625gp"

    def test_seed_34_b1_botm_bare_values(self):
        """[34] B1 裸值（月之血脉装备段）：无标签 `100gp，8磅` 解析 +
        类别前缀「装备与炼金物品」剥离 + 跨行标题拼接（Memory Incense）"""
        items = run(SEEDS[34]["raw_snippet"], "月之血脉BotM_物品.md")
        it = by_type(items, "item")
        assert len(it) == 3, f"应 3 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "动物伪装工具包", f"title={t1['title']!r}"
        assert t1["title_en"] == "Animal Disguise Kit", f"en={t1['title_en']!r}"
        assert t1["fields"]["price"] == "100gp"
        assert t1["fields"]["weight"] == "8磅"
        assert "皮革口袋" in t1["text"]
        t2 = it[1]
        assert t2["title"] == "记忆熏香"
        assert t2["title_en"] == "Memory Incense"
        assert t2["fields"]["price"] == "50gp"
        assert t2["fields"]["weight"] == "1磅"
        t3 = it[2]
        assert t3["title"] == "银滴"
        assert t3["title_en"] == "Silver Drops"
        assert t3["fields"]["price"] == "180gp"
        assert t3["fields"]["weight"] == "-磅"

    def test_seed_35_b1_botm_labeled(self):
        """[35] B1 标签链（月之血脉魔法物品段）：④ 链 + 行内标题切分 +
        正文「该物品」守卫 + 跨行续段字段归属（制造成本 6675gp 归鼻环）"""
        items = run(SEEDS[35]["raw_snippet"], "月之血脉BotM_物品.md")
        it = by_type(items, "item")
        assert len(it) == 2, f"应 2 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "神奇嗅觉鼻环", f"title={t1['title']!r}"
        assert t1["title_en"] == "Nose Ring of Unearthly Scent"
        assert t1["fields"]["aura"] == "微弱预言系"
        assert t1["fields"]["caster_level"] == "3"
        assert t1["fields"]["slot"] == "头部"
        assert t1["fields"]["price"] == "11475gp"
        assert t1["fields"]["weight"] == "- 磅"
        assert t1["fields"]["craft_cost"] == "6675gp", f"cost={t1['fields']}"
        t2 = it[1]
        assert t2["title"] == "风暴船长之三叉戟"
        assert t2["title_en"] == "Trident of the Storm Captain"
        assert t2["fields"]["aura"] == "强烈塑能和变化系"
        assert t2["fields"]["slot"] == "无"
        assert t2["fields"]["price"] == "109665gp"

    def test_seed_36_b1_guard_inline_refs(self):
        """[36] B1 正文守卫：正文中「精通先创/制造奇物」等引用不误判标题，
        价格值到守卫词截止（price=3600金币），制造成本正确切出"""
        items = run(SEEDS[36]["raw_snippet"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "护身符", f"title={t1['title']!r}"
        assert t1["title_en"] == "Amulet of Quaking Strikes"
        assert t1["fields"]["price"] == "3600金币", f"price={t1['fields']}"
        assert t1["fields"]["craft_cost"] == "1800gp"
        assert "精通先攻" in t1["text"]
        assert "制造奇物" in t1["text"]

    def test_seed_37_b1_aarch_pfs(self):
        """[37] B1 动物档案：H2=条目名（剥除为空时用 H2 作标题）+ GLUE 标题行
        + PFS可 残渣行（join 层排除，独立落 text 保真）+ 字段行并入"""
        items = run(SEEDS[37]["raw_snippet"], "动物档案AArch_装备.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "去味剂", f"title={t1['title']!r}"
        assert t1["title_en"] == "Deodorizing agent", f"en={t1['title_en']!r}"
        assert t1["fields"]["price"] == "30gp", f"fields={t1['fields']}"
        assert t1["fields"]["weight"] == "—"
        assert "PFS可" in t1["text"]
        # 「类别」入 subcategory 词表（VC/AA2 实测 11 处）→ 结构化字段
        # 而非保真文本
        assert t1["fields"]["subcategory"] == "炼金工具", \
            f"subcategory={t1['fields'].get('subcategory')!r}"
        assert "《动物档案》第13页" in t1["text"]

    def test_seed_38_b1_teog_html_entity(self):
        """[38] B1 塔尔多：HTML 实体 &eacute; 跨行英文名——EN 类含 &; 支持
        `Fortigr&eacute;`，title_en html.unescape（Fortigré）"""
        items = run(SEEDS[38]["raw_snippet"], "塔尔多TEoG_魔法物品.md")
        it = by_type(items, "item")
        assert len(it) == 2, f"应 2 个 item，实际 {len(it)}（{it}）"
        t2 = it[1]
        assert t2["title"] == "皇帝弗提格雷的摇摆沙发床", f"title={t2['title']!r}"
        assert t2["title_en"] == "The Pendulate Divan of Emperor Fortigré", \
            f"en={t2['title_en']!r}（应 unescape &eacute;）"
        assert t2["fields"]["price"] == "66000gp"

    def test_seed_39_b1_craft_lead_guard(self):
        """[39] B1 制造系守卫：制造条件尾法术引用伪标题
        `侦测魔法Detect Magic制造成本：` → 并入上一条目（craft_cost 归属），
        不产独立 chunk，伪标题文本保真进 text"""
        items = run(SEEDS[39]["raw_snippet"], "月之血脉BotM_物品.md")
        it = by_type(items, "item")
        assert len(it) == 2, f"应 2 个 item，实际 {len(it)}（{it}）"
        assert it[0]["title"] == "真形护符"
        t1 = it[1]
        assert t1["title"] == "神奇嗅觉鼻环", f"title={t1['title']!r}"
        assert t1["fields"]["craft_cost"] == "6675gp", f"fields={t1['fields']}"
        assert "侦测魔法" in t1["text"], "伪标题文本应保真进 text"
        assert all(i["title"] != "侦测魔法" for i in it), "不应产出「侦测魔法」伪标题"

    def test_seed_40_b1_ui_ring_guards(self):
        """[40] B1 UI戒指 伪标题负例：`意志 DC 16`（EN=DC 尾空格+\d lookahead）
        与制造条件值尾不产 chunk，文本保真进 text"""
        items = run(SEEDS[40]["raw_snippet"], "UI戒指.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "公报对戒", f"title={t1['title']!r}"
        assert all(i["title"] != "意志" for i in it), "不应产出「意志」伪标题"
        assert "意志 DC 16" in t1["text"], "伪标题文本应保真进 text"

    def test_seed_41_b1_silvercloud_en_full(self):
        """[41] B1 无空格英文名：`Silvercloud` 不被词表 `cl` 标签前瞻截断
        （lookahead 剔除纯英文标签）→ title_en=Silvercloud Oil"""
        items = run(SEEDS[41]["raw_snippet"], "月之血脉BotM_物品.md")
        it = by_type(items, "item")
        assert len(it) == 2, f"应 2 个 item，实际 {len(it)}（{it}）"
        t1 = it[1]
        assert t1["title"] == "银云油", f"title={t1['title']!r}"
        assert t1["title_en"] == "Silvercloud Oil", f"en={t1['title_en']!r}"
        assert t1["fields"]["price"] == "60gp"
        assert t1["fields"]["weight"] == "1/2磅"

    def test_seed_42_b1_pfs_residue(self):
        """[42] B1 怪物猎人物：行内 `PFS不可` 残渣（CHM `<BR>` 排版残渣
        家族，勘探实证 `PFS可` 同源）剥除 → 标题命中切出，title_en 无残留"""
        items = run(SEEDS[42]["raw_snippet"], "怪物猎人手册_普通物品.md")
        it = by_type(items, "item")
        assert len(it) == 2, f"应 2 个 item，实际 {len(it)}（{it}）"
        t1 = it[1]
        assert t1["title"] == "化学防护剂", f"title={t1['title']!r}"
        assert t1["title_en"] == "CHEMICAL WARD", f"en={t1['title_en']!r}"
        assert "PFS" not in t1["title_en"], "title_en 不应残留 PFS 残渣"
        assert t1["fields"]["price"] == "25gp", f"fields={t1['fields']}"
        assert t1["fields"]["weight"] == "1磅"

    def test_seed_43_b1_fullwidth_comma(self):
        """[43] B1 RTT：英文名全角逗号（`Assassin's Sight，Greater`）——
        EN 类含 `，` 吃满后组后 `位置` 字段标签命中，高等/普通两条独立切出"""
        items = run(SEEDS[43]["raw_snippet"], "远程战术工具箱RTT_奇物.md")
        it = by_type(items, "item")
        assert len(it) == 2, f"应 2 个 item，实际 {len(it)}（{it}）"
        assert it[0]["title"] == "暗杀瞄准镜", f"title={it[0]['title']!r}"
        t1 = it[1]
        assert t1["title"] == "高等暗杀瞄准镜", f"title={t1['title']!r}"
        assert t1["title_en"] == "Assassin's Sight, Greater", f"en={t1['title_en']!r}"
        assert t1["fields"]["price"] == "12250gp", f"fields={t1['fields']}"

    def test_seed_44_b1_quantity_guard(self):
        """[44] B1 RTT：正文量词守卫家族（`这根/这双/这块`）——字段值切到
        量词前，正文保真落 text（纠缠肩带 `2000gp这根` 实测；全库缺口
        这根×2/这双×1/这块×2）"""
        items = run(SEEDS[44]["raw_snippet"], "远程战术工具箱RTT_奇物.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "纠缠肩带", f"title={t1['title']!r}"
        assert t1["fields"]["price"] == "2000gp", f"price={t1['fields'].get('price')!r}"
        assert "这根细长的带刺藤蔓" in t1["text"], "正文应保真落 text"

    def test_seed_45_ab_zh_guard_shared(self):
        """[45] A/B 形态共用正文守卫（_RE_ZH_BODY 与 B1 同口径）：冒号字段
        行「这把」量词（武器大师手册 十字军长剑 `灵光：中等塑能系 这把+1
        神圣…`）→ 值切分 + 正文落 text"""
        items = run(SEEDS[45]["raw_snippet"], "武器大师手册_魔法武器.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "十字军长剑", f"title={t1['title']!r}"
        assert t1["fields"]["aura"] == "中等塑能系", f"aura={t1['fields'].get('aura')!r}"
        assert "这把+1神圣破敌恶魔寒铁长剑" in t1["text"], "正文应保真落 text"

    def test_seed_46_ap_value_star_chain(self):
        """[46] AP 值首尾星壳链 + H2/裸行 TAIL 同文合并：H2 有括号条目后
        裸行同文 TAIL（`****灵光 ` 半星标签）+ 值星壳链（`**中等咒法系；**
        施法者等级 **9；**…`）——①不重复开条目（H2 空壳消失）②链首值段
        挂灵光 ③字段完整 ④正文保真落 text"""
        items = run(SEEDS[46]["raw_snippet"], "冒险之路AP_装备.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "冒险之路AP 巨石袋", f"title={t1['title']!r}"
        assert t1["fields"].get("aura") == "中等咒法系", f"aura={t1['fields'].get('aura')!r}"
        assert t1["fields"].get("caster_level") == "9", f"cl={t1['fields'].get('caster_level')!r}"
        assert t1["fields"].get("slot") == "无", f"slot={t1['fields'].get('slot')!r}"
        assert t1["fields"].get("price") == "3,000 gp", f"price={t1['fields'].get('price')!r}"
        assert t1["fields"].get("weight") == "200磅", f"weight={t1['fields'].get('weight')!r}"
        assert "这个巨大的袋子装满了" in t1["text"], "正文应保真落 text"

    def test_seed_47_ap_star_title_merge(self):
        """[47] AP 星壳 FULL 标题同文合并：`**接物护手（…）****灵光 **微弱
        防护系；**…`（前导 `**` 星壳，非裸行）→ 归一比对不重复开、组3
        尾星壳链剥星挂字段、跨行价格续值（`**价格` 行尾 + 下行链首值段）"""
        items = run(SEEDS[47]["raw_snippet"], "冒险之路AP_装备.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "冒险之路AP 接物护手", f"title={t1['title']!r}"
        assert t1["fields"].get("aura") == "微弱防护系", f"aura={t1['fields'].get('aura')!r}"
        assert t1["fields"].get("caster_level") == "4", f"cl={t1['fields'].get('caster_level')!r}"
        assert t1["fields"].get("slot") == "手部", f"slot={t1['fields'].get('slot')!r}"
        assert t1["fields"].get("price") == "6,000 gp", f"price={t1['fields'].get('price')!r}"
        assert t1["fields"].get("weight") == "20磅", f"weight={t1['fields'].get('weight')!r}"
        assert "这种手套形似" in t1["text"], "正文应保真落 text"

    def test_seed_48_bos_tail_guard(self):
        """[48] BoS 出处行 TAIL 误判守卫：`出自阴影血脉（Blood Of Shadow）`
        裸行（组3 非空、组1 非变体词）→ 不开新条目、并入上条目 text；
        上条目冒号形态字段链完整（price/aura/caster_level）"""
        items = run(SEEDS[48]["raw_snippet"], "阴影血脉BoS_武器附魔.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "影射", f"title={t1['title']!r}"
        assert t1["fields"].get("price") == "+1等价物", f"price={t1['fields'].get('price')!r}"
        assert t1["fields"].get("aura") == "中等咒法系", f"aura={t1['fields'].get('aura')!r}"
        assert t1["fields"].get("caster_level") == "7", f"cl={t1['fields'].get('caster_level')!r}"
        assert "出自阴影血脉（Blood Of Shadow）" in t1["text"], "出处行应并入上条目 text"
        assert "这种附魔会降低武器的攻击检定" in t1["text"], "正文应保真落 text"

    def test_seed_49_isc_misaligned_star(self):
        """[49] ISC 巨行星壳错位归位（铁卫肩铠形态）：条目名闭壳
        `****）****位置**：` 四星开壳后裸标签+残星字段段（`位置` 前无星）
        → normalize 归位 `**位置**：` 解析 slot；字段链段间 `；` 分隔符
        不进 text；正文残段纯净（无 `位置**`/`**` 残渣）"""
        items = run(SEEDS[49]["raw_snippet"], "内海战斗ISC_戒指权杖奇物.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "铁卫肩铠", f"title={t1['title']!r}"
        assert t1["title_en"] == "Iron Guard Pauldrons", f"title_en={t1['title_en']!r}"
        assert t1["fields"].get("slot") == "肩部", f"slot={t1['fields'].get('slot')!r}"
        assert t1["fields"].get("price") == "5750gp", f"price={t1['fields'].get('price')!r}"
        assert t1["fields"].get("caster_level") == "3级", f"cl={t1['fields'].get('caster_level')!r}"
        assert t1["fields"].get("weight") == "6磅", f"weight={t1['fields'].get('weight')!r}"
        assert t1["fields"].get("aura") == "微弱防护系", f"aura={t1['fields'].get('aura')!r}"
        assert t1["text"].startswith("这些构造简单"), f"正文应纯净开头，实际 {t1['text'][:30]!r}"
        assert "位置**" not in t1["text"], "text 不应含标签残渣"
        assert "**" not in t1["text"], "text 不应含星壳残渣"

    # ---------- M3 收尾：11 文件 aggregation sink 家族（断行定位符/表格壳/裸字段紧贴/行内链）----------

    def test_seed_50_ui_star_title_break(self):
        """[50] UI奇物 星壳标题跨行断行定位符：`**仿声锭Accent \nPill**`
        紧贴（NOPAREN 需空格不匹配）——入口断行 join 后 GLUE 匹配开条目；
        `**价格：**` 空值跨行 `150 GP` join 补值"""
        items = run(SEEDS[50]["raw_snippet"], "极限诡道/UI奇物.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "仿声锭", f"title={t1['title']!r}"
        assert t1["title_en"] == "Accent Pill", f"title_en={t1['title_en']!r}"
        assert t1["fields"].get("slot") == "无", f"slot={t1['fields'].get('slot')!r}"
        assert t1["fields"].get("caster_level") == "1", f"cl={t1['fields'].get('caster_level')!r}"
        assert t1["fields"].get("price") == "150 GP", f"price={t1['fields'].get('price')!r}"
        assert t1["fields"].get("weight") == "—", f"weight={t1['fields'].get('weight')!r}"

    def test_seed_51_ui_table_shell(self):
        """[51] UI奇物 表格壳条目：`| 挚友吊坠Best Friend \n Pendant栏位：
        颈部…` 跨行 join 后单行——表格壳分支（剥 `| ` + B1 标题切段 +
        ④ 链挂字段）；`重量 - 灵光：` 无冒号标签段（空格+符号值首）切出
        weight"""
        items = run(SEEDS[51]["raw_snippet"], "极限诡道/UI奇物.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "挚友吊坠", f"title={t1['title']!r}"
        assert t1["title_en"] == "Best Friend Pendant", f"title_en={t1['title_en']!r}"
        assert t1["fields"].get("slot") == "颈部", f"slot={t1['fields'].get('slot')!r}"
        assert t1["fields"].get("caster_level") == "5", f"cl={t1['fields'].get('caster_level')!r}"
        assert t1["fields"].get("price") == "5000 GP", f"price={t1['fields'].get('price')!r}"
        assert t1["fields"].get("weight") == "-", f"weight={t1['fields'].get('weight')!r}"
        assert t1["fields"].get("aura") == "昏暗咒法与变化系", f"aura={t1['fields'].get('aura')!r}"
        assert "栏位" not in t1["text"], "字段标签不应落 text"

    def test_seed_52_pp_paren_break(self):
        """[52] P&P 跨行括号标题 + 行内字段链：`有效死亡之环（Band of \n
        Efficacious Death）位置：戒指；…`——join 后 TAIL 组3 行内字段链
        （以词表标签+冒号开头）→ 开条目 + ④ 链解析挂字段；正文 `这枚金
        戒指` 守卫切 text；制造要求行尾跨行括号 join 后链归属"""
        items = run(SEEDS[52]["raw_snippet"], "药剂与毒药P&P_奇物.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "有效死亡之环", f"title={t1['title']!r}"
        assert t1["title_en"] == "Band of Efficacious Death", f"title_en={t1['title_en']!r}"
        assert t1["fields"].get("slot") == "戒指", f"slot={t1['fields'].get('slot')!r}"
        assert t1["fields"].get("price") == "9250gp", f"price={t1['fields'].get('price')!r}"
        assert t1["fields"].get("caster_level") == "3级", f"cl={t1['fields'].get('caster_level')!r}"
        assert t1["fields"].get("weight") == "-磅", f"weight={t1['fields'].get('weight')!r}"
        assert t1["fields"].get("aura") == "微弱死灵系", f"aura={t1['fields'].get('aura')!r}"
        assert t1["text"].startswith("这枚金戒指"), f"正文应以这枚开头，实际 {t1['text'][:30]!r}"
        assert "致命药引" in t1["fields"].get("craft_requirements", ""), \
            f"craft_requirements={t1['fields'].get('craft_requirements')!r}"
        assert t1["fields"].get("craft_cost") == "4625gp", \
            f"craft_cost={t1['fields'].get('craft_cost')!r}"

    def test_seed_53_aoe_space_glue(self):
        """[53] AoE 空格分隔紧邻标题：`嗜血 BLOODTHIRSTY`（GLUE 组2 前导
        空格）——组2 允许前导空格变体 + 下一行裸字段链守卫开条目"""
        items = run(SEEDS[53]["raw_snippet"], "邪恶特务AoE_武器防具附魔与特殊武器.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "嗜血", f"title={t1['title']!r}"
        assert t1["title_en"] == "BLOODTHIRSTY", f"title_en={t1['title_en']!r}"
        assert t1["fields"].get("price") == "+2", f"price={t1['fields'].get('price')!r}"
        assert t1["fields"].get("aura") == "中等附魔系", f"aura={t1['fields'].get('aura')!r}"
        assert t1["fields"].get("caster_level") == "7级", f"cl={t1['fields'].get('caster_level')!r}"
        assert t1["fields"].get("weight") == "-", f"weight={t1['fields'].get('weight')!r}"
        assert t1["fields"].get("craft_cost") == "+2加值", f"craft_cost={t1['fields'].get('craft_cost')!r}"

    def test_seed_54_pis_colon_prefix(self):
        """[54] PIS `：` 前缀正文行：`星盘 Astrolabe \n：这个装置…`——join
        规则排除 `：` 前缀行（不并入标题行）；`_bare_title_follows` 加 `：`
        前缀分支开条目；正文行剥 `：` 前缀入 text；`价格：100gp，重量6磅`
        无冒号标签段（`重量6磅` 紧贴）切出 weight"""
        items = run(SEEDS[54]["raw_snippet"], "内海海盗PIS_装备.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "星盘", f"title={t1['title']!r}"
        assert t1["title_en"] == "Astrolabe", f"title_en={t1['title_en']!r}"
        assert t1["text"].startswith("这个装置"), f"正文应剥：前缀，实际 {t1['text'][:30]!r}"
        assert t1["fields"].get("price") == "100gp", f"price={t1['fields'].get('price')!r}"
        assert t1["fields"].get("weight") == "6磅", f"weight={t1['fields'].get('weight')!r}"
        assert t1["fields"].get("类型") == "工具和技能套件", f"类型={t1['fields'].get('类型')!r}"

    def test_seed_55_ctt_bare_tight(self):
        """[55] CTT 裸字段紧贴：`契者之甲ADVOCATE’S ARMOR\n价格33,160 GP`
        ——`_RE_BARE_FIELD` 紧贴变体（标签+数字值首）供守卫判定；`位置 \n
        盔甲` 裸标签跨行 join 后裸字段行分支开 slot"""
        items = run(SEEDS[55]["raw_snippet"], "近战战术工具箱CTT_魔法护甲.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "契者之甲", f"title={t1['title']!r}"
        assert t1["title_en"] == "ADVOCATE'S ARMOR", f"title_en={t1['title_en']!r}"
        assert t1["fields"].get("price") == "33,160 GP", f"price={t1['fields'].get('price')!r}"
        assert t1["fields"].get("slot") == "盔甲", f"slot={t1['fields'].get('slot')!r}"
        assert t1["fields"].get("aura") == "昏暗咒法系", f"aura={t1['fields'].get('aura')!r}"

    def test_seed_56_aa_inline_chain(self):
        """[56] 水下冒险 裸标题行内字段链：`流形（特殊盔甲附魔）Aquadynamic
        （Armor Special \n Ability）灵光：可变 施法者等级：5 价格：可变`——
        join 后 `_RE_BARE_INLINE_CHAIN`（中文名+可选尾注+英文名+可选英文
        尾注+字段链）开条目挂字段；中文尾注（特殊盔甲附魔）挂 subcategory"""
        items = run(SEEDS[56]["raw_snippet"], "水下冒险AA_水下宝藏.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "流形", f"title={t1['title']!r}"
        assert t1["title_en"] == "Aquadynamic", f"title_en={t1['title_en']!r}"
        assert t1["fields"].get("subcategory") == "特殊盔甲附魔", \
            f"subcategory={t1['fields'].get('subcategory')!r}"
        assert t1["fields"].get("aura") == "可变", f"aura={t1['fields'].get('aura')!r}"
        assert t1["fields"].get("caster_level") == "5", f"cl={t1['fields'].get('caster_level')!r}"
        assert t1["fields"].get("price") == "可变", f"price={t1['fields'].get('price')!r}"

    def test_seed_57_aa_star_chain(self):
        """[57] 水下冒险 GLUE 星壳标题组4 星壳字段链：`**机械章鱼Apparatus
        of the Octopus****灵光**：…**施法者等级**：19…`——GLUE 匹配后组4
        先字段解析挂 fields（text 不污染 `**`）"""
        items = run(SEEDS[57]["raw_snippet"], "水下冒险AA_水下宝藏.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应 1 个 item，实际 {len(it)}（{it}）"
        t1 = it[0]
        assert t1["title"] == "机械章鱼", f"title={t1['title']!r}"
        assert t1["title_en"] == "Apparatus of the Octopus", f"title_en={t1['title_en']!r}"
        assert t1["fields"].get("aura") == "强烈塑能系和变化系", f"aura={t1['fields'].get('aura')!r}"
        assert t1["fields"].get("caster_level") == "19", f"cl={t1['fields'].get('caster_level')!r}"
        assert t1["fields"].get("slot") == "无", f"slot={t1['fields'].get('slot')!r}"
        assert t1["fields"].get("price") == "20000gp", f"price={t1['fields'].get('price')!r}"
        assert t1["fields"].get("weight") == "400磅", f"weight={t1['fields'].get('weight')!r}"
        assert "**" not in t1["text"], "text 不应含星壳残渣"

    def test_seed_58_rtt_inline_multi(self):
        """[58] RTT 行内多条目链：`魔法武器箭裂者Arrow Splitter位置：无…
        制造成本：90375gp雪崩投石杖Avalanche Sling Staff位置：无…`——
        `_detect_b1_flow` 判据 4（行内 ≥2 `_RE_B1_TITLE` 段）→ 走 B1
        `_split_flow_b1` 行内 finditer 切段；H2 `魔法武器` 前缀剥除；正文
        `这只+5二重长弓` 守卫切 text"""
        items = run(SEEDS[58]["raw_snippet"], "远程战术工具箱RTT_魔法武器.md")
        it = by_type(items, "item")
        assert len(it) == 2, f"应 2 个 item，实际 {len(it)}（{it}）"
        t1, t2 = it[0], it[1]
        assert t1["title"] == "箭裂者", f"t1.title={t1['title']!r}"
        assert t1["title_en"] == "Arrow Splitter", f"t1.title_en={t1['title_en']!r}"
        assert t1["fields"].get("slot") == "无", f"t1.slot={t1['fields'].get('slot')!r}"
        assert t1["fields"].get("caster_level") == "15", f"t1.cl={t1['fields'].get('caster_level')!r}"
        assert t1["fields"].get("weight") == "3磅", f"t1.weight={t1['fields'].get('weight')!r}"
        assert t1["fields"].get("aura") == "强烈塑能系", f"t1.aura={t1['fields'].get('aura')!r}"
        assert t1["fields"].get("price") == "180375gp", f"t1.price={t1['fields'].get('price')!r}"
        assert t1["text"].startswith("这只+5二重长弓"), f"t1.text 应以这只开头，实际 {t1['text'][:30]!r}"
        assert t1["fields"].get("craft_cost") == "90375gp", f"t1.craft_cost={t1['fields'].get('craft_cost')!r}"
        assert t2["title"] == "雪崩投石杖", f"t2.title={t2['title']!r}"
        assert t2["title_en"] == "Avalanche Sling Staff", f"t2.title_en={t2['title_en']!r}"
        assert t2["fields"].get("price") == "36320gp", f"t2.price={t2['fields'].get('price')!r}"
        assert t2["text"].startswith("每天三次，这柄+3半身人投石杖"), \
            f"t2.text 应以每天三次开头，实际 {t2['text'][:30]!r}"

    def test_seed_59_pp_bare_inline_chain(self):
        """[59] P&P 裸行标题 + 行内无星壳字段链 + 行内正文连排：
        `收集者工具箱（Havester's Kit）价格：65gp重量：-磅这套外科…`
        （标题（EN）后字段同行、值后正文粘连无分隔——正文起点按
        _RE_ZH_BODY 词表 `这套`/`这跟`/`这是` 切出，字段链 ④ 链解析、
        正文残体落 text）；跨行标题（行尾空格+缩进续行）join 归一；
        表格壳残渣（`|` 独立行/` |  |` 行尾）不残留"""
        items = run(SEEDS[59]["raw_snippet"], "药剂与毒药P&P_装备.md")
        it = by_type(items, "item")
        assert len(it) == 6, f"应 6 个 item，实际 {len(it)}（{[x['title'] for x in it]}）"
        names = [x["title"] for x in it]
        assert names == ["收集者工具箱", "毒喷盒", "毒羽笔", "投毒高脚杯",
                         "匿声油", "毒云香炉"], f"titles={names}"
        t0, t1, t2 = it[0], it[1], it[2]
        # 字段链结构化：价格/重量，值不吞正文
        assert t0["fields"].get("price") == "65gp", f"t0.price={t0['fields']}"
        assert t0["fields"].get("weight") == "-磅", f"t0.weight={t0['fields'].get('weight')!r}"
        assert t0["text"].startswith("这套外科手术工具"), \
            f"t0.text 应以正文开头，实际 {t0['text'][:20]!r}"
        assert t1["fields"].get("weight") == "-磅", f"t1.weight={t1['fields'].get('weight')!r}"
        assert t2["title_en"] == "Poisoned Quill", f"t2.title_en={t2['title_en']!r}（跨行标题应 join 归一）"
        assert t2["fields"].get("price") == "30gp", f"t2.price={t2['fields'].get('price')!r}"
        assert t2["text"].startswith("这跟长笔是由一根纤细的羽毛制成"), \
            f"t2.text 应以正文开头，实际 {t2['text'][:20]!r}"
        assert it[5]["title_en"] == "Toxic Censer", f"t5.title_en={it[5]['title_en']!r}"
        assert it[5]["fields"].get("price") == "115gp", f"t5.price={it[5]['fields'].get('price')!r}"
        # 表格壳残渣不残留
        assert not any("|" in x["text"] for x in it), "表格壳 `|` 不应残留在 text"

    def test_seed_61_pp_subsection_guard(self):
        """[61] P&P 反毒药装备小节守卫：小节标题跨行
        `反毒药装备 ANTI-POISONER'S \\nGEAR每有一件…`（行尾空格 + 中文
        英文紧邻 + 英文续行后紧跟中文正文句）**不触发 B1 流误判**——
        _detect_b1_flow GLUE 判据应排除「英文段紧邻中文正文段」形态
        （B1 断条家族 GLUE 后随行为字段链 `位置：`/数值 `100gp`）；
        小节导言不产伪条目；毒液克星含片条目结构化"""
        items = run(SEEDS[60]["raw_snippet"], source_name="药剂与毒药P&P_装备.md")
        it = by_type(items, "item")
        # 小节标题+导言 + 毒液克星含片 → 只产 1 个条目（毒液克星含片）
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        loz = it[0]
        assert loz["title"] == "毒液克星含片", f"title={loz['title']!r}"
        assert loz["title_en"] == "Venombane Lozenges", f"title_en={loz['title_en']!r}"
        assert loz["fields"].get("price") == "35gp", f"price={loz['fields'].get('price')!r}"
        assert loz["fields"].get("weight") == "-磅", f"weight={loz['fields'].get('weight')!r}"
        assert loz["text"].startswith("这些微微发光的含片"), \
            f"text 应以正文开头，实际 {loz['text'][:20]!r}"
        # 表格壳不残留
        assert not any("|" in x["text"] for x in items), "表格壳 `|` 不应残留"

    def test_seed_62_pp_unslot_chain(self):
        """[62] P&P 无位置奇物 4 形态（M3 收尾 P&P_奇物无位置 6 条缺口）：
        ①GLUE 小节标记行内嵌条目（`灵药 ELIXIRS正文…敏捷灵药（…）位置：`）
        ②表格行内全角括号条目（`| 无尽之眼灵药（…）… |  |`，_RE_B1_TITLE
        只支持无括号形态 → 表格壳分支须走 TAIL 切段）
        ③行内多条目链（`…制造成本：700gp凶猛魔法灵药（…）位置：`——链头
        前段字段链挂上一条 fields，链头条目独立开）
        ④正文法术引用误判守卫（`暴怒法术（Furious Spell）制造成本：`——
        伪链头 pre 尾非字段值残尾 `gp/磅/级/数字/分号` → 不切）"""
        items = run(SEEDS[61]["raw_snippet"], source_name="药剂与毒药P&P_奇物.md")
        it = by_type(items, "item")
        by_title = {x["title"]: x for x in it}
        # 4 形态代表条目全产出
        for t in ("敏捷灵药", "无尽之眼灵药", "炼狱魔宠灵药",
                  "凶猛魔法灵药", "烈火大嘴灵药"):
            assert t in by_title, f"缺条目 {t}，实际 {list(by_title)}"
        # 正文法术引用不误判为条目（Furious Spell 是制造条件里的法术名）
        assert "暴怒法术" not in by_title, "暴怒法术不应被切为条目"
        # ①敏捷灵药：GLUE 行内嵌条目，字段+正文结构化
        agile = by_title["敏捷灵药"]
        assert agile["fields"].get("price") == "450gp", f"price={agile['fields']}"
        assert agile["text"].startswith("这个方形的瓶子"), \
            f"敏捷灵药 text 应以正文开头，实际 {agile['text'][:20]!r}"
        # ②无尽之眼灵药：表格壳条目，壳不残留
        eyes = by_title["无尽之眼灵药"]
        assert eyes["fields"].get("price") == "1200gp", f"price={eyes['fields']}"
        assert "|" not in eyes["text"], "无尽之眼 text 不应残留表格壳"
        # ③链首条（炼狱魔宠）制造系字段挂上一条目，不吞链
        infernal = by_title["炼狱魔宠灵药"]
        assert infernal["fields"].get("craft_cost") == "700gp", \
            f"炼狱魔宠 craft_cost={infernal['fields'].get('craft_cost')!r}"
        assert "凶猛魔法灵药" not in infernal["text"], \
            "链下条目标题不应吞进上一条目 text"
        # ④凶猛魔法：正文法术引用不误切为条目（守卫②），制造条件值
        # 保真挂自身 craft_requirements/craft_cost
        vicious = by_title["凶猛魔法灵药"]
        assert "暴怒法术（Furious Spell）" in vicious["fields"].get(
            "craft_requirements", ""), \
            f"暴怒法术应保真在 craft_requirements，实际 {vicious['fields']}"
        assert vicious["fields"].get("craft_cost") == "875gp", \
            f"凶猛魔法 craft_cost={vicious['fields'].get('craft_cost')!r}"

    def test_seed_63_dragon_hunter_bare_breaks(self):
        """[63] 屠龙者手册断词合体（M3 收尾 price 吞字段家族）：
        裸标签跨行 `价格 \\n50 金币重量\\n1/2 磅正文`（行尾空格断行 +
        标签值断词合体 `金币重量`）——_join_logical 拼接须在「词表标签
        + 数字前瞻」处停止（正文不并入字段链）；裸字段行值尾词表标签
        `重量` 剥除 → price 干净 `50 金币`；正文完整保真落 text"""
        items = run(SEEDS[62]["raw_snippet"], source_name="屠龙者手册_物品.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        fire = it[0]
        assert fire["title"] == "达哈克之火", f"title={fire['title']!r}"
        assert fire["fields"].get("price") == "50 金币", \
            f"price 应干净剥离重量，实际 {fire['fields'].get('price')!r}"
        assert "重量" not in fire["fields"].get("price", ""), \
            "price 不应含 重量 标签"
        assert "从一条最近去世的龙的肝脏" in fire["text"], \
            f"正文应完整保真，实际 {fire['text'][:40]!r}"
        assert "挥发性炼金试剂" in fire["text"], "正文中段保真"

    def test_seed_64_mm_price_weight_glue(self):
        """[64] MM 星壳链值内裸标签段（M3 收尾 price 吞字段家族）：
        `**价格**：150gp 重量：1/2磅`——_RE_FIELD_SEG 星壳链值吞
        `重量：` 裸段 → 值内二次切分（_RE_COLON_SEG/_RE_BARE_
        NOCOLON_SEG 双扫词表校验）→ price/weight 各自干净"""
        items = run(SEEDS[63]["raw_snippet"], source_name="商人货单MM_装备.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        mono = it[0]
        assert mono["title"] == "猴像", f"title={mono['title']!r}"
        assert mono["fields"].get("price") == "150gp", \
            f"price={mono['fields'].get('price')!r}"
        assert mono["fields"].get("weight") == "1/2磅", \
            f"weight={mono['fields'].get('weight')!r}"
        assert "重量" not in mono["fields"].get("price", ""), \
            "price 不应含 重量 标签"

    def test_seed_65_dragon_wyrmpesh_price_glue(self):
        """[65] 屠龙者手册龙精粹（M3 收尾 price 吞字段家族）：断词合体
        `500 金币重量 - 磅正文` 的**正文含 `；`**（`成瘾性: 重度; 强韧
        DC24价格：…`）→ 裸标签行并入走链式切分分支 → `_bare_weight_glue_cut`
        只挂单值 else → 整段吞进 price。链式切分前须先做断词合体截断
        （`重量` 紧贴前词判定，`；重量` 合法链不误伤）"""
        items = run(SEEDS[64]["raw_snippet"], source_name="屠龙者手册_物品.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        pesh = it[0]
        assert pesh["title"] == "龙精粹", f"title={pesh['title']!r}"
        assert pesh["fields"].get("price") == "500 金币", \
            f"price 应干净剥离重量，实际 {pesh['fields'].get('price')!r}"
        assert "重量" not in pesh["fields"].get("price", ""), \
            "price 不应含 重量 标签"
        assert "重量 -  磅这种稀有而昂贵的标准Garundi" in pesh["text"], \
            f"残段（重量+值+正文）应保真落 text，实际 {pesh['text'][:60]!r}"
        assert "强韧DC24价格" in pesh["text"], "正文尾部保真"

    def test_seed_66_balance_guard_price_chain(self):
        """[66] 格拉里昂的平衡勇士解放护手（M3 收尾 price 吞字段家族）：
        `位置 手部; 价格 \\n13,200  gp; 重量 6 \\n磅`——裸字段行拼接链，
        断词守卫「词表标签 + 数字前瞻」误把 `价格 13,200`（`价格` 前为
        空格）拦断 → price 空 + 数字行落 text。守卫须排除分隔符前缀
        （`;；、，,`/空格）标签，`；` 链整体走链式切分三字段全解析"""
        items = run(SEEDS[65]["raw_snippet"], source_name="格拉里昂的平衡勇士_奇物.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        gaunt = it[0]
        assert gaunt["title"] == "解放护手", f"title={gaunt['title']!r}"
        assert gaunt["fields"].get("slot") == "手部", \
            f"slot={gaunt['fields'].get('slot')!r}"
        assert gaunt["fields"].get("price") == "13,200 gp", \
            f"price={gaunt['fields'].get('price')!r}"
        assert gaunt["fields"].get("weight") == "6 磅", \
            f"weight={gaunt['fields'].get('weight')!r}"
        assert "13,200" not in gaunt["text"], "价格数字不应落 text"

    def test_seed_67_hotw_oak_craft_cond(self):
        """[67] HotW 橡木法杖（M3 收尾 B 制造块家族）：ANNOT 标题
        `**橡木法杖(Oaken \\nStaff)PFS可**`（闭壳星前夹注解）+ 制造块
        空值字段行 `**制造条件:** ` 行尾空格被入口 _join_logical 并入
        值行 → ①A 值前瞻 `；` 须仅当后跟字段星壳才作链分隔：craft_
        conditions 值内分号完整吞入，craft_cost 值尾 `gp` 一并归位"""
        items = run(SEEDS[66]["raw_snippet"], source_name="荒野英雄HotW_物品.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        oak = it[0]
        assert oak["title"] == "橡木法杖", f"title={oak['title']!r}"
        assert oak["fields"].get("craft_conditions") == \
            "制造魔法武器和盔甲；制造法杖；树肤术；植物滋长；植物交谈；" \
            "传送术；制造者必须是至少12级的施法者", \
            f"craft_conditions 应完整（值内分号不截断），实际 " \
            f"{oak['fields'].get('craft_conditions')!r}"
        assert oak["fields"].get("craft_cost") == "16050 gp", \
            f"craft_cost={oak['fields'].get('craft_cost')!r}"

    def test_seed_68_chr_spear_crit_mult(self):
        """[68] CHR 注射矛（M3 收尾 B 重击倍率家族）：`**重击：***3  **`
        倍率星紧贴值尾——①A 值前瞻 `\\s*\\*\\*` 放行 `*数字` 后接空格
        星壳 → critical 解析 `*3`，伤害/伤害类型链式完整"""
        items = run(SEEDS[67]["raw_snippet"], source_name="经典恐怖再临CHR_新武器.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        spear = it[0]
        assert spear["title"] == "注射矛", f"title={spear['title']!r}"
        assert spear["fields"].get("damage") == "1d6（小型）1d8（中型） 穿刺", \
            f"同 key 链段应追加保留（骰段+类型段），实际 " \
            f"{spear['fields'].get('damage')!r}"
        assert spear["fields"].get("critical") == "3", \
            f"critical={spear['fields'].get('critical')!r}（M6 A-1 剥壳：`*3`→`3`）"
        assert "*3" not in spear.get("text", ""), "倍率不应落 text"

    def test_seed_69_kis_lance_craft_cost(self):
        """[69] KIS 战争长枪（M3 收尾 B 制造块家族）：`**制造条件:** `
        后接空格行阻断入口 join → 空值字段续行收集 + 值行内嵌
        `**花费:**5310 gp` 段——①A 半角分支链式解析 craft_conditions
        完整 + craft_cost 归位（此前续行路径丢失 craft_cost）"""
        items = run(SEEDS[68]["raw_snippet"], source_name="内海骑士KIS_魔法武器.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        lance = it[0]
        assert lance["title"] == "战争长枪", f"title={lance['title']!r}"
        assert lance["fields"].get("craft_conditions") == \
            "制造魔法武器和盔甲；护盾术", \
            f"craft_conditions={lance['fields'].get('craft_conditions')!r}"
        assert lance["fields"].get("craft_cost") == "5310 gp", \
            f"craft_cost={lance['fields'].get('craft_cost')!r}"

    def test_seed_70_vc_scamper_slippers_italic(self):
        r"""[70] VC 蹦跳拖鞋（M3 收尾 B 斜体值家族）：制造要求值内嵌
        `*蛛行术*` 斜体法术名——①A 值字符类须放行完整斜体段
        （`\*[^*\n]*?\*`），否则分支失败整行 sink 丢 craft_requirements"""
        items = run(SEEDS[69]["raw_snippet"], source_name="反派法典VC_奇物.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        slip = it[0]
        assert slip["title"] == "蹦跳拖鞋", f"title={slip['title']!r}"
        assert slip["fields"].get("craft_requirements") == \
            "“制造奇物”，蛛行术", \
            f"craft_requirements 斜体壳应剥除（M6 A-1），实际 " \
            f"{slip['fields'].get('craft_requirements')!r}"
        assert slip["fields"].get("craft_cost") == "600 gp", \
            f"craft_cost={slip['fields'].get('craft_cost')!r}"
        assert "制造要求" not in slip.get("text", ""), \
            "制造要求行不应 sink 进 text"

    def test_seed_71_price_ladder_line_variant(self):
        """[71] 价格阶梯行不拆伪条目（M3 收尾 B）：`普通（Standard）
        价格：1gp 重量：无` / `精制品（Masterwork）价格：50gp`——组1 ∈
        变体词表 sink 保真挂当前条目（圣战军十字架实证；TAIL 分支
        L1882 守卫的 EN 半角括号漏网补位），不产「普通」「精制品」
        伪条目，正文完整挂真条目"""
        items = run(SEEDS[70]["raw_snippet"],
                    source_name="装备_魔法物品/货品服务/恶魔猎人手册_物品.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        cross = it[0]
        assert cross["title"] == "圣战军十字架", f"title={cross['title']!r}"
        txt = cross.get("text", "")
        assert "普通（Standard）价格：1gp" in txt, \
            f"阶梯行应保真进 text，实际 {txt[:80]!r}"
        assert "精制品（Masterwork）价格：50gp" in txt, \
            f"精制品阶梯行应保真进 text，实际 {txt[:80]!r}"
        assert "这种手掌大小的十字架" in txt, \
            f"正文应完整挂真条目，实际 {txt[:120]!r}"
        titles = [x.get("title") for x in items]
        assert "普通" not in titles and "精制品" not in titles, \
            f"不应产变体伪条目，实际 {titles}"

    def test_seed_72_bare_desc_label_line(self):
        """[72] 裸「描述」行 = 正文标记（M3 收尾 B 描述回归家族）：
        B1 无星形态 `描述` 独立行（无星壳无冒号）——sink 挂 text 保真，
        防裸标签分支开空字段 + 续行收集吞整段正文（奥多里决斗剑 text
        空实证：描述值完整进字段、正文无剩余）"""
        items = run(SEEDS[71]["raw_snippet"],
                    source_name="装备_魔法物品/内海世界指南ISWG_武器.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        sword = it[0]
        assert sword["title"] == "奥多里决斗剑", f"title={sword['title']!r}"
        assert sword["fields"].get("price") == "20gp", \
            f"price={sword['fields'].get('price')!r}"
        assert sword["fields"].get("damage") == \
            "1d6 (小体型), 1d8 (中体型)", \
            f"damage={sword['fields'].get('damage')!r}"
        assert "这把略微弯曲的剑" in sword.get("text", ""), \
            f"正文应挂 text，实际 {sword.get('text', '')[:80]!r}"
        assert "描述" not in sword.get("fields", {}), \
            f"描述不应进字段，实际 fields={list(sword.get('fields', {}).keys())}"

    def test_seed_73_chm_detailed_page223(self):
        """[73] C 形态奇物详述区（page_223 实证）：4 标题变体 + 星壳字段行
        变体 ①裸 GLUE（水性腹带AQUATIC CUMMERBUND）②删除线壳跨行无闭壳
        （~~**蟒蛇缠腰ANACONDA'S + COILS）③裸 GLUE + 英文断行（沉沦英雄
        腰带BELT OF FALLEN + HEROES）④四星开壳无闭壳（****巨力腰带BELT OF
        GIANT STRENGTH）；字段 = 星壳字段行（**灵光：…**价格：…）+ 裸字段
        行（重量/制造条件/制造成本），值跨行 join"""
        items = run(SEEDS[72]["raw_snippet"],
                    source_name="装备_魔法物品/魔法物品/奇物/page_223.md")
        it = by_type(items, "item")
        assert len(it) == 4, f"应产 4 个 item，实际 {len(it)}：{[x.get('title') for x in it]}"
        names = [x.get("title") for x in it]
        for t in ["水性腹带", "蟒蛇缠腰", "沉沦英雄腰带", "巨力腰带"]:
            assert t in names, f"缺条目 {t}，实际 {names}"
        waist = next(x for x in it if x["title"] == "水性腹带")
        assert waist["title_en"] == "AQUATIC CUMMERBUND", \
            f"title_en={waist['title_en']!r}"
        f = waist["fields"]
        assert f.get("aura") == "微弱变化系", f"aura={f.get('aura')!r}"
        assert f.get("caster_level") == "5", f"caster_level={f.get('caster_level')!r}"
        assert f.get("price") == "2600gp", f"price={f.get('price')!r}"
        assert f.get("weight") == "-", f"weight={f.get('weight')!r}"
        assert f.get("craft_conditions") == "制造奇物、海洋之触touch of the sea（APG）", \
            f"craft_conditions={f.get('craft_conditions')!r}"
        assert f.get("craft_cost") == "1300gp", f"craft_cost={f.get('craft_cost')!r}"
        assert "长久以来都认为" in waist.get("text", ""), \
            f"正文应挂 text，实际 {waist.get('text', '')[:60]!r}"
        # ② 删除线壳 + 英文断行 join（~~ 剥除 + ANACONDA'S COILS 拼回）
        snake = next(x for x in it if x["title"] == "蟒蛇缠腰")
        assert snake["title_en"] == "ANACONDA'S COILS", \
            f"跨行英文名应 join，实际 {snake['title_en']!r}"
        assert snake["fields"].get("price") == "18500gp", \
            f"price={snake['fields'].get('price')!r}"
        assert snake["fields"].get("weight") == "1磅", \
            f"值跨行 weight 应挂字段，实际 {snake['fields'].get('weight')!r}"
        assert snake["fields"].get("craft_conditions") == \
            "制造奇物、野兽形态beast shape I、牛之力量bull's strength", \
            f"制造条件值跨行应 join，实际 {snake['fields'].get('craft_conditions')!r}"
        assert snake["fields"].get("craft_cost") == "9250gp", \
            f"craft_cost={snake['fields'].get('craft_cost')!r}"
        # ③ 裸 GLUE + 英文断行（无尾空格）join
        fallen = next(x for x in it if x["title"] == "沉沦英雄腰带")
        assert fallen["title_en"] == "BELT OF FALLEN HEROES", \
            f"英文断行应 join，实际 {fallen['title_en']!r}"
        # ④ 四星开壳剥星
        giant = next(x for x in it if x["title"] == "巨力腰带")
        assert giant["title_en"] == "BELT OF GIANT STRENGTH", \
            f"title_en={giant['title_en']!r}"
        assert giant["fields"].get("price") == "+2-4000gp +4-16000gp +6-36000gp", \
            f"多档价格应保真，实际 {giant['fields'].get('price')!r}"
        assert giant["fields"].get("weight") == "1磅", \
            f"weight={giant['fields'].get('weight')!r}"

    def test_seed_74_chm_negative(self):
        """[74] C 形态负例：价格表行（| 名 | 价 |）不产条目；星壳字段行
        无标题开条目时 = 正文（sink 保真不吞）；纯正文段不产条目"""
        items = run(SEEDS[73]["raw_snippet"],
                    source_name="装备_魔法物品/魔法物品/奇物/page_223.md")
        it = by_type(items, "item")
        assert len(it) == 0, \
            f"表格行/孤儿字段行/正文不应产条目，实际 {len(it)}：{[x.get('title') for x in it]}"

    def test_seed_75_harrow_table_no_extra_items(self):
        """[75] 860 哈啰牌 22 表格行负例：4 列 `牌面|媒介|位置|注意`
        无价格/重量单位列、首列无括号英文 → 附属表不收集候选，表格行
        sink 进真条目（万象无常哈啰牌）不补切"""
        items = run(SEEDS[74]["raw_snippet"],
                    source_name="装备_魔法物品/魔法物品/神器与传说/page_860.md")
        it = by_type(items, "item")
        assert len(it) == 1, \
            f"哈啰牌表格行不应产额外条目，实际 {len(it)}：{[x.get('title') for x in it]}"
        assert it[0]["title"] == "万象无常哈啰牌"

    def test_seed_76_artifact_section_heading(self):
        """[76] 632 `**次级神器（Minor \\nArtifacts）**` 跨行星壳章节头
        → sink 保真（est 勘探口径「2 章节标题不计数」），不产条目"""
        items = run(SEEDS[75]["raw_snippet"],
                    source_name="装备_魔法物品/魔法物品/神话冒险/page_632.md")
        it = by_type(items, "item")
        assert len(it) == 0, \
            f"次级神器章节头不应产条目，实际 {len(it)}：{[x.get('title') for x in it]}"

    def test_seed_77_nagan_table_dedup(self):
        """[77] 775 纳甘表格行（多空格 `纳甘M1895         左轮手枪` +
        400GP 价格列）与详述星壳条目同文 → 补切候选名去空白归一化后
        净增 0 不重复切，双条目防回归"""
        items = run(SEEDS[76]["raw_snippet"],
                    source_name="装备_魔法物品/武器_防具/page_775.md")
        it = by_type(items, "item")
        assert len(it) == 1, \
            f"纳甘表格行不应重复切，实际 {len(it)}：{[x.get('title') for x in it]}"
        assert it[0]["title"] == "纳甘 M1895左轮手枪"

    def test_seed_78_glue_en_split(self):
        """[78] 212 毒药表 `| 黑莲汁Black lotus extract | … | 4,500 gp |`
        无括号粘连英文名 → 拆 title=黑莲汁 / title_en=Black lotus extract，
        价格列存在 = 本体行补切"""
        items = run(SEEDS[77]["raw_snippet"],
                    source_name="装备_魔法物品/货品服务/page_212.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个毒药表条目，实际 {len(it)}"
        assert it[0]["title"] == "黑莲汁", f"title={it[0]['title']!r}"
        assert it[0]["title_en"] == "Black lotus extract", \
            f"粘连英文应拆进 title_en，实际 {it[0]['title_en']!r}"

    def test_seed_79_body_sentence_negative(self):
        """[79] 860 正文句负例（伪条目家族防回退）：斜体正文段剥星 +
        `***介绍：**` 星壳（EXTRA 保真字段非规范字段）→ 不开条目、
        不触发字段链判别（860 舞动小屋实证）"""
        items = run(SEEDS[78]["raw_snippet"],
                    source_name="装备_魔法物品/魔法物品/神器与传说/page_860.md")
        it = by_type(items, "item")
        assert len(it) == 0, \
            f"正文句不应产条目，实际 {len(it)}：{[x.get('title') for x in it]}"

    def test_seed_75_chm_hh_appended_item(self):
        """[75] C 形态页底部 HH 追加条目（page_223 实证）——HTML 注释 +
        FULL 标题 + 来源块 + 无闭壳标题闭壳后同行接字段链（组3 tail
        `**银色魂索 SILVER SOUL CORD**灵光：…`）+ 字段值尾随正文切分
        （`重量：1磅这根闪闪…` 值数字单位后接中文正文 → 正文挂 text）"""
        text = "\n".join([
            "<!-- HH-source:page_715.md:银色魂索 -->",
            "**银色魂索（Silver Soul Cord）**",
            "> 来源：治疗者手册（Healer's Handbook）HH",
            "**银色魂索 \nSILVER SOUL CORD**灵光：中等防护系与死灵系 ",
            "施法者等级：9位置：腰带 ",
            "价格：25000GP 重量：1磅这根闪闪发亮的金属腰带由数捆索线组成。",
        ])
        items = run(text, source_name="装备_魔法物品/魔法物品/奇物/page_223.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 HH 追加条目，实际 {len(it)}"
        item = it[0]
        assert item["title"] == "银色魂索", f"title={item['title']!r}"
        assert item["title_en"] == "Silver Soul Cord", \
            f"FULL 标题组2 应作 title_en，实际 {item['title_en']!r}"
        # 无闭壳标题 tail 字段链（组3）→ 字段挂接
        assert item["fields"].get("aura") == "中等防护系与死灵系", \
            f"tail 灵光应挂字段，实际 {item['fields'].get('aura')!r}"
        assert item["fields"].get("caster_level") == "9", \
            f"caster_level={item['fields'].get('caster_level')!r}"
        assert item["fields"].get("slot") == "腰带", \
            f"slot={item['fields'].get('slot')!r}"
        assert item["fields"].get("price") == "25000GP", \
            f"price={item['fields'].get('price')!r}"
        # 字段值尾随正文切分：weight 干净、正文挂 text
        assert item["fields"].get("weight") == "1磅", \
            f"weight 应切分不吞正文，实际 {item['fields'].get('weight')!r}"
        assert "金属腰带由数捆索线组成" in item["text"], \
            f"正文应挂 text，实际 {item['text'][:80]!r}"

    # ---------- C 形态 1254 艾恩石详述区（M4 专项，2026-08-09）----------

    def test_seed_76_chm_ioun_a_type(self):
        """[76] 1254 A 型艾恩石标题（page_1254 实证）：`**珠光金字塔形
        艾恩石Legal Pearlescent Pyramid Ioun Stone (Normal) **`——半角
        括号型号 + 闭壳星行尾，FULL 组1 会吞中文+英文粘连错配 en=Normal，
        IOUN 分支必须先行；守卫后随 `**来源**Pathfinder #125: ...`（星壳
        标签闭壳无冒号直接值，_chm_field_follows mfs2 新识别）；en 拼装
        rstrip 防双空格"""
        text = "\n".join([
            "| 名称 | 价格 |",
            "| --- | --- |",
            "| 珠光金字塔形艾恩石 | 24,000 gp |",
            "**珠光金字塔形艾恩石Legal Pearlescent Pyramid Ioun Stone (Normal) **",
            "**来源**Pathfinder #125: 溺毙者之塔 pg. 31",
            "**灵光** 强烈咒法系;**施法者等级** 12th",
            "**位置** 无; **价格** 24,000 gp; **重量** —",
            "**效果**",
            "这种艾恩石像一个微小的珍珠白色四面体。",
        ])
        items = run(text, source_name="魔法物品/奇物/无位置/page_1254.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个艾恩石条目，实际 {len(it)}"
        item = it[0]
        assert item["title"] == "珠光金字塔形艾恩石", f"title={item['title']!r}"
        assert item["title_en"] == "Legal Pearlescent Pyramid Ioun Stone (Normal)", \
            f"en 应完整且单空格，实际 {item['title_en']!r}"
        # M5 拆 key（原整行值保真口径，注释登记拆 key 待 M6 字段健康度
        # KN 定性——现提前落地：`_parse_space_field_line` 半角分号分段后
        # aura/caster_level/slot/price/weight 各自归位，同 1127/1129
        # 全角口径；seed_85 半角分号链同步修复）
        assert item["fields"].get("aura") == "强烈咒法系", \
            f"aura={item['fields'].get('aura')!r}"
        assert item["fields"].get("caster_level") == "12th", \
            f"caster_level={item['fields'].get('caster_level')!r}"
        assert item["fields"].get("slot") == "无", \
            f"slot={item['fields'].get('slot')!r}"
        assert item["fields"].get("price") == "24,000 gp", \
            f"price={item['fields'].get('price')!r}"
        assert item["fields"].get("weight") == "—", \
            f"weight={item['fields'].get('weight')!r}"
        assert "珍珠白色四面体" in item["text"], \
            f"正文应挂 text，实际 {item['text'][:60]!r}"

    def test_seed_77_chm_ioun_c_type(self):
        """[77] 1254 C 型艾恩石标题：`**蔚蓝色梨形艾恩石Azure Briolette
        Ioun Stone(Normal)` 无闭壳 + 独立 `**` 行——_chm_field_follows
        跳过独立闭壳星行递归看来源行（mfs2 识别 `**来源**Pathfinder`）"""
        text = "\n".join([
            "| 名称 | 价格 |",
            "| --- | --- |",
            "| 蔚蓝色梨形艾恩石 | 15,000 gp |",
            "**蔚蓝色梨形艾恩石Azure Briolette Ioun Stone(Normal)",
            "**",
            "**来源**Pathfinder #125: 溺毙者之塔 pg. 36",
            "**灵光** 强烈附魔系与死灵系;**施法者等级** 12th",
            "**价格** 15,000 gp; **重量** —",
            "**效果**",
            "这颗梨形的艾恩石闪耀着明亮的蔚蓝色光辉。",
        ])
        items = run(text, source_name="魔法物品/奇物/无位置/page_1254.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个艾恩石条目，实际 {len(it)}"
        item = it[0]
        assert item["title"] == "蔚蓝色梨形艾恩石", f"title={item['title']!r}"
        assert item["title_en"] == "Azure Briolette Ioun Stone (Normal)", \
            f"en={item['title_en']!r}"
        assert "明亮的蔚蓝色光辉" in item["text"], \
            f"正文应挂 text，实际 {item['text'][:60]!r}"

    def test_seed_78_chm_ioun_b_type(self):
        """[78] 1254 B 型艾恩石标题：`**【PFS】南方星形艾恩石（Southern
        Star Ioun Stone，Normal）` 全角括号 + 【PFS】前缀——组3 全角一体
        `EN，型号` → `EN (型号)`；守卫后随 `**出自**：Heroes ...`（剥星后
        出自前缀，_chm_field_follows 新识别）"""
        text = "\n".join([
            "| 名称 | 价格 |",
            "| --- | --- |",
            "| 南方星形艾恩石 | 32,000 gp |",
            "**【PFS】南方星形艾恩石（Southern Star Ioun Stone，Normal）",
            "**出自**：Heroes from the Fringe pg. 15",
            "**灵光**：强烈变化系；**施法者等级**：12级",
            "**栏位**：无；**价格**：32,000 gp；**重量**：—",
            "**效果**",
            "此艾恩石允许使用者从南方星空获得导航。",
        ])
        items = run(text, source_name="魔法物品/奇物/无位置/page_1254.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个艾恩石条目，实际 {len(it)}"
        item = it[0]
        assert item["title"] == "南方星形艾恩石", f"title={item['title']!r}"
        assert item["title_en"] == "Southern Star Ioun Stone (Normal)", \
            f"全角 `EN，型号` 应转 `EN (型号)`，实际 {item['title_en']!r}"
        assert item["fields"].get("aura") == "强烈变化系", \
            f"aura={item['fields'].get('aura')!r}"

    def test_seed_79_chm_ioun_join_guard_negative(self):
        """[79] 值跨行 join 不吞 IOUN 标题（2026-08-09 实证 i 跳跃修复）：
        制造条件行尾 gp + 下一行 A 型标题——join 守卫须排除 IOUN 标题；
        负例：`**艾恩石（Ioun Stones）**` 页题后随正文不开条目"""
        text = "\n".join([
            "| 名称 | 价格 |",
            "| --- | --- |",
            "| 珠光金字塔形艾恩石 | 24,000 gp |",
            "**珠光金字塔形艾恩石Legal Pearlescent Pyramid Ioun Stone (Normal) **",
            "**来源**Pathfinder #125: 溺毙者之塔 pg. 31",
            "**灵光** 强烈咒法系;**施法者等级** 12th",
            "**位置** 无; **价格** 24,000 gp; **重量** —",
            "**效果**",
            "这种艾恩石像一个微小的珍珠白色四面体。",
            "**制造**",
            "**制造条件** 制造奇物，制造者必须为12级;**花费** 24,000 gp",
            "**瑕疵珠光金字塔形艾恩石Legal Pearlescent Pyramid Ioun Stone (Flawed)**",
            "**来源**Pathfinder #125: 溺毙者之塔 pg. 31",
            "**灵光** 强烈咒法系;**施法者等级** 12th",
            "**效果**",
            "这种艾恩石如同普通版本一样，但它无法赋予使用者识破隐形的好处。",
        ])
        items = run(text, source_name="魔法物品/奇物/无位置/page_1254.md")
        it = by_type(items, "item")
        assert len(it) == 2, \
            f"珠光金字塔 + 瑕疵珠光金字塔应各 1 条（join 不得吞标题），实际 {len(it)}"
        names = [x["title"] for x in it]
        assert "瑕疵珠光金字塔形艾恩石" in names, \
            f"瑕疵条目被制造条件值跨行 join 吞掉，实际 {names}"
        flawed = next(x for x in it if x["title"] == "瑕疵珠光金字塔形艾恩石")
        assert flawed["title_en"] == "Legal Pearlescent Pyramid Ioun Stone (Flawed)", \
            f"en={flawed['title_en']!r}"
        assert "识破隐形" in flawed["text"], \
            f"瑕疵条目正文应独立挂载，实际 {flawed['text'][:60]!r}"
        # 负例：页题后随正文段不开条目
        text2 = "\n".join([
            "**艾恩石（Ioun Stones）**",
            "尽管探索者协会费尽九牛二虎之力，亦只有零碎的信息是关于艾恩石的来源。",
        ])
        items2 = run(text2, source_name="魔法物品/奇物/无位置/page_1254.md")
        it2 = by_type(items2, "item")
        assert len(it2) == 0, \
            f"页题后随正文不应产条目，实际 {len(it2)}：{[x.get('title') for x in it2]}"

    # ---------- 947 表 6-3 修复回归（2026-08-09，seed_80~85） ----------

    def test_seed_80_chm_no_en_title_chain(self):
        """[80] 947 无英文标题条目（组2 可选修复）：`腐败护身符灵光：…`/
        `反噬矛`/`毒虫法袍`——CHM 原文标题即无英文名，INLINE_HEAD 组2 为
        空；preprocess ② 链头回溯（表格锚）拆出清单项，主循环组2 空 +
        表格锚守卫开条目（en=''）；正文独立挂载"""
        text = "\n".join([
            "| 15-16 | | 狂暴巨剑 | | 65-66 | | 腐败护身符 |",
            "| 27-28 | | 反噬矛 | | 81-82 | | 毒虫法袍 |",
            "正常物品：任意护肩腐败护身符灵光：中等防护系，施法者等级10装备位置：颈部，重量—",
            "这块雕刻过的宝石护身符看起来没什么特别的价值。",
            "正常物品：水晶球反噬矛灵光：强烈塑能系，施法者等级10装备位置：无（武器），重量3磅",
            "此物品等同于一把+2短矛。",
            "正常物品：融合法袍，骸骨法袍，百眼法袍，虹光法袍，星光法袍，大法师之袍，杂货法袍毒虫法袍灵光：起来防护系，施法者等级13装备位置：身体，重量1磅",
            "这件法袍十分正常。",
        ])
        items = run(text, source_name="魔法物品/page_947.md")
        it = by_type(items, "item")
        assert len(it) == 3, \
            f"应产 3 个 item，实际 {len(it)}：{[x.get('title') for x in it]}"
        names = {x["title"]: x for x in it}
        for t in ["腐败护身符", "反噬矛", "毒虫法袍"]:
            assert t in names, f"缺条目 {t}，实际 {list(names)}"
            assert names[t]["title_en"] == "", \
                f"[{t}] 无英文标题 en 应为空，实际 {names[t]['title_en']!r}"
        # 链头回溯：清单项保真不丢失（sink 目标 = intro 或前一条目正文，
        # 取决于切分时刻有无当前条目——真实 947 同为混合分布）
        all_text = " ".join(x.get("text", "") for x in items)
        for pref in ["任意护肩", "水晶球", "杂货法袍"]:
            assert pref in all_text, f"清单项 {pref} 不得丢失，实际 {all_text[:80]!r}"
        # 字段 + 正文挂载
        f = names["腐败护身符"]["fields"]
        assert f.get("aura") == "中等防护系", f"aura={f.get('aura')!r}"
        assert "宝石护身符" in names["腐败护身符"]["text"], \
            f"正文应挂 text，实际 {names['腐败护身符']['text'][:60]!r}"

    def test_seed_81_chm_split_line_clean(self):
        """[81] 947 源数据拆行后形态：`正常物品：+2短弓` 独立行落 intro，
        `毁灭袋Bag of devouring灵光：…` 独立条目（改名后 = 表格权威名）"""
        text = "\n".join([
            "| 11-12 | | 毁灭袋 |",
            "正常物品：+2短弓",
            "毁灭袋Bag of devouring灵光：强烈咒法系，施法者等级17装备位置：无，重量15磅",
            "这个口袋看上去就是个普普通通的包。",
        ])
        items = run(text, source_name="魔法物品/page_947.md")
        it = by_type(items, "item")
        assert len(it) == 1, \
            f"应产 1 个 item，实际 {len(it)}：{[x.get('title') for x in it]}"
        d = it[0]
        assert d["title"] == "毁灭袋", f"title={d['title']!r}"
        assert d["title_en"] == "Bag of devouring", f"en={d['title_en']!r}"
        assert d["fields"].get("weight") == "15磅", \
            f"weight={d['fields'].get('weight')!r}"
        assert "普普通通的包" in d["text"], f"正文应挂载，实际 {d['text'][:50]!r}"

    def test_seed_82_chm_num_prefix_title(self):
        """[82] 947 数字前缀标题：`-2诅咒长剑 –2 Cursed sword灵光：…`——
        preprocess ② 数字前缀并入标题行首 + 主循环行首数字容错（match 锚
        定行首失败剥 `-2` 重试）+ `-2`+组1 ∈ 表格权威名并入标题"""
        text = "\n".join([
            "| 01-02 | | -2诅咒长剑 |",
            "-2诅咒长剑 –2 Cursed sword灵光：强烈塑能系，施法者等级15装备位置：无（武器），重量4磅",
            "这把剑在攻击投骰上受到-2罚值。",
        ])
        items = run(text, source_name="魔法物品/page_947.md")
        it = by_type(items, "item")
        assert len(it) == 1, \
            f"应产 1 个 item，实际 {len(it)}：{[x.get('title') for x in it]}"
        c = it[0]
        assert c["title"] == "-2诅咒长剑", f"title={c['title']!r}"
        assert c["title_en"] == "–2 Cursed sword", f"en={c['title_en']!r}"
        assert c["fields"].get("caster_level") == "15", \
            f"caster_level={c['fields'].get('caster_level')!r}"
        assert "攻击投骰" in c["text"], f"正文应挂载，实际 {c['text'][:50]!r}"

    def test_seed_83_chm_field_chain_anchor_guard(self):
        """[83] 947 [17] 误开回归：字段链 `施法者等级10位置：头部…`（组1 ∈
        字段词表）预处理 ② 跳过 + 主循环 sink——不产伪条目；盲冠标题行
        字段/正文完整（tail 链解析保真）"""
        text = "\n".join([
            "| 25-26 | | 盲目王冠 |",
            "任意魔法披风盲目王冠Crown of blindness灵光：强烈幻术系，施法者等级10位置：头部，重量1磅",
            "施法者等级10位置：头部，重量1磅",
            "这顶精致的银质头环通常镶嵌着乳白色的宝石。",
        ])
        items = run(text, source_name="魔法物品/page_947.md")
        it = by_type(items, "item")
        assert len(it) == 1, \
            f"字段链不得开伪条目，实际 {len(it)}：{[x.get('title') for x in it]}"
        c = it[0]
        assert c["title"] == "盲目王冠", f"title={c['title']!r}"
        assert c["title_en"] == "Crown of blindness", f"en={c['title_en']!r}"
        f = c["fields"]
        assert f.get("aura") == "强烈幻术系", f"aura={f.get('aura')!r}"
        assert f.get("slot") == "头部", f"slot={f.get('slot')!r}"
        assert "银质头环" in c["text"], f"正文应挂载，实际 {c['text'][:60]!r}"

    def test_seed_84_chm_removed_rant_title(self):
        """[84] 947 译者吐槽删除后（KN091 同族）：`狂暴巨剑Berserking sword
        灵光：…` 独立条目——括号段曾卡 INLINE_HEAD 组2 前瞻致整行沉 intro，
        源数据删除吐槽后链头回溯 + 主循环正常开条目，正文无吐槽残留"""
        text = "\n".join([
            "| 15-16 | | 狂暴巨剑 |",
            "正常物品：强体腰带（任意加值）",
            "狂暴巨剑Berserking sword灵光：强烈塑能系，施法者等级8装备位置：无（武器）重量：8磅",
            "这把巨剑挥动时会发出咆哮声。",
        ])
        items = run(text, source_name="魔法物品/page_947.md")
        it = by_type(items, "item")
        assert len(it) == 1, \
            f"应产 1 个 item，实际 {len(it)}：{[x.get('title') for x in it]}"
        b = it[0]
        assert b["title"] == "狂暴巨剑", f"title={b['title']!r}"
        assert b["title_en"] == "Berserking sword", f"en={b['title_en']!r}"
        assert "明斯克" not in b["text"], \
            f"吐槽不得残留正文，实际 {b['text'][:60]!r}"
        assert "咆哮声" in b["text"], f"正文应挂载，实际 {b['text'][:50]!r}"

    def test_seed_85_chm_no_en_guard_negative(self):
        """[85] 已删除（2026-08-09 M6 A-1）：构造形态 `普通物品灵光：…`
        依赖「物品」subcategory 别名回退才不产条目；别名移除（噪鸣纸 KN 修复）
        后该形态与 page_234 无英文名合法条目同行为（882 个正例），测试场景
        已随修复消失。守卫意图（正文行 `灵光：` 不误开条目）由 page_947
        66 chunks 基线断言与 B 类登记覆盖，无守卫缺口。"""

    def test_seed_86_chm_star_halfwidth_paren(self):
        """[86] 220 星壳开壳 + 半角括号同行（page_220 诱饵戒指实证）：
        `**诱饵戒指 (Decoy Ring)` 行尾无星壳闭壳（FULL 组3 `\\s*\\*{2,4}`
        无星失败、CHM_TITLE 组2 括号内禁 `)` 失败）→ 改 CHM_TITLE 组2
        允许括号闭壳；守卫 = 后随星壳字段行；title_en 剥外围括号"""
        text = "\n".join([
            "**诱饵戒指 (Decoy Ring)",
            "**灵光**：中等幻术系　**施法者等级**：11**价格**：12000gp　**重量**：–**　　该戒指看起来如同一圈不透明的镜面金属。",
            "**需求**：“锻造戒指”,'假象术'**成本**：6000gp**",
        ])
        items = run(text, source_name="魔法物品/戒指_权杖_法杖/page_220.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        d = it[0]
        assert d["title"] == "诱饵戒指", f"title={d['title']!r}"
        assert d["title_en"] == "Decoy Ring", f"title_en={d['title_en']!r}"
        f = d["fields"]
        assert f.get("aura") == "中等幻术系", f"aura={f.get('aura')!r}"
        assert f.get("price") == "12000gp", f"price={f.get('price')!r}"
        assert f.get("craft_cost") == "6000gp", f"craft_cost={f.get('craft_cost')!r}"
        assert "镜面金属" in d.get("text", ""), f"正文应挂 text，实际 {d.get('text', '')[:50]!r}"

    def test_seed_87_chm_bare_halfwidth_paren(self):
        """[87] 220 裸标题 + 半角括号同行（page_220 地牢戒指实证）：`地牢
        戒指 (Dungeon Ring)` 无星无全角——BARE_EN 组1 后原要求 `\\(` 紧贴，
        半角空格隔断失败 → 允许 `\\s*`；字段链行内值跨行（`16000gp` +
        `(狱卒戒指); 250gp`）join"""
        text = "\n".join([
            "地牢戒指 (Dungeon Ring)",
            "**灵光**：中等预言系　**施法者等级**：8**价格**：16000gp",
            "(狱卒戒指); 250gp (囚犯戒指)　**重量**：–**　　狱卒戒指用金制成，镶嵌有红玛瑙。",
            "**需求**：“锻造戒指”,'探知术','关照术'**成本**：800gp",
            "(狱卒戒指); 125gp (囚犯戒指)**",
        ])
        items = run(text, source_name="魔法物品/戒指_权杖_法杖/page_220.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        d = it[0]
        assert d["title"] == "地牢戒指", f"title={d['title']!r}"
        assert d["title_en"] == "Dungeon Ring", f"title_en={d['title_en']!r}"
        f = d["fields"]
        # 价格主体保真；括号价格变体注释（`(狱卒戒指); 250gp (囚犯戒指)`）
        # 行首非字段标签 → 进 text 保真（0 丢失）
        assert f.get("price") == "16000gp", f"price={f.get('price')!r}"
        assert "(狱卒戒指); 250gp (囚犯戒指)" in d.get("text", ""), \
            f"价格变体注释应进 text 保真，实际 {d.get('text', '')[:60]!r}"
        assert "红玛瑙" in d.get("text", ""), f"正文应挂 text，实际 {d.get('text', '')[:50]!r}"

    def test_seed_88_chm_bare_halfwidth_crossline(self):
        """[88] 220 裸标题 + 半角括号跨行（page_220 动物之友戒指实证）：
        `动物之友戒指 (Ring of` + `Animal Friendship)`——BARE_EN/TAIL 括号
        未闭失败 → 下一行无中文续行 join 回完整标题再开条目"""
        text = "\n".join([
            "动物之友戒指 (Ring of",
            "Animal Friendship)",
            "**灵光**：中等心灵系　**施法者等级**：7**价格**：12000gp　**重量**：–**　　",
            "**需求**：“锻造戒指”,'动物友善术'**成本**：6000gp**",
        ])
        items = run(text, source_name="魔法物品/戒指_权杖_法杖/page_220.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        d = it[0]
        assert d["title"] == "动物之友戒指", f"title={d['title']!r}"
        assert d["title_en"] == "Ring of Animal Friendship", \
            f"跨行英文名应 join，实际 {d['title_en']!r}"

    def test_seed_89_chm_bare_fullwidth_crossline_pos(self):
        """[89] 220 全角括号跨行 + 位置式字段链（page_220 先祖血咒戒指实证）：
        `先祖血咒戒指（Ring of` + `Ancestral Blood Magic）`——TAIL 括号未闭
        失败 → 跨行 join；字段链为位置式（`**位置**：戒指；**价格**：…`）
        （AA2 格式，字段名词表含位置）"""
        text = "\n".join([
            "先祖血咒戒指（Ring of",
            "Ancestral Blood Magic）",
            "**位置**：戒指；**价格**：4000gp**施法者等级**：10级；**重量**：—**灵光**：中等变化系**当佩戴者处于血怒时能够施放法术。",
            "**制造要求**：坚忍（Endurance），锻造戒指（Forge Ring）**制造成本**：2000gp**",
        ])
        items = run(text, source_name="魔法物品/戒指_权杖_法杖/page_220.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        d = it[0]
        assert d["title"] == "先祖血咒戒指", f"title={d['title']!r}"
        assert d["title_en"] == "Ring of Ancestral Blood Magic", \
            f"跨行英文名应 join，实际 {d['title_en']!r}"
        f = d["fields"]
        assert f.get("slot") == "戒指", f"slot={f.get('slot')!r}"
        assert f.get("price") == "4000gp", f"price={f.get('price')!r}"
        assert f.get("craft_cost") == "2000gp", f"craft_cost={f.get('craft_cost')!r}"

    def test_seed_90_chm_artifact_aura_line(self):
        """[90] 949 神器详述区灵光粘着行（page_949 信仰灯塔实证）：
        `信仰灯塔BEACON`（正文末行粘着中文+英文首段）+ `OF TRUE FAITH灵光：
        强烈(所有学派)`（英文末段粘着灵光字段）——回溯切新条目，粘着行标题
        前正文回流上一条目"""
        text = "\n".join([
            "次级神器未必是独一无二的，但是它们也不是那么简单能用凡人的手段创造出来。信仰灯塔BEACON",
            "OF TRUE FAITH灵光：强烈(所有学派)",
            "施法者等级：20位置：无",
            "重量：2磅信仰灯塔通常用银金矿(electrum)制成一个华丽的火炬形态。",
        ])
        items = run(text, source_name="魔法物品/page_949.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        d = it[0]
        assert d["title"] == "信仰灯塔", f"title={d['title']!r}"
        assert d["title_en"] == "BEACON OF TRUE FAITH", \
            f"英文名应拼接，实际 {d['title_en']!r}"
        f = d["fields"]
        assert f.get("aura") == "强烈(所有学派)", f"aura={f.get('aura')!r}"
        assert f.get("slot") == "无", f"slot={f.get('slot')!r}"
        assert f.get("weight") == "2磅", f"weight={f.get('weight')!r}"
        intro = items[0]
        assert "次级神器未必是独一无二的" in intro["text"], \
            f"粘着行标题前正文应回流 intro，实际 {intro['text']!r}"
        assert "信仰灯塔BEACON" not in intro["text"], \
            f"标题不应残留 intro，实际 {intro['text']!r}"

    def test_seed_91_chm_artifact_altname_apostrophe(self):
        """[91] 949 神器异名括号 + 撇号英文（page_949 猿猴之手实证）：
        `猿猴之手(大圣遗愿/怨)MONKEY'S` + `PAW灵光：…`——异名剥壳进
        aliases，`'` 撇号英文首段必须匹配"""
        text = "\n".join([
            "猿猴之手(大圣遗愿/怨)MONKEY'S",
            "PAW灵光：强烈死灵系和共通系",
            "施法者等级：20位置：无",
            "重量：2磅这件超出想像的物品耐心地等待着被人拾起。",
        ])
        items = run(text, source_name="魔法物品/page_949.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        d = it[0]
        assert d["title"] == "猿猴之手", f"title={d['title']!r}"
        assert d["title_en"] == "MONKEY'S PAW", f"title_en={d['title_en']!r}"
        assert "大圣遗愿/怨" in d.get("aliases", []), \
            f"异名应进 aliases，实际 {d.get('aliases')!r}"

    def test_seed_92_chm_artifact_crossline_en(self):
        """[92] 949 神器英文名跨行 + 全角括号异名（page_949 天体透镜实证）：
        `天体透镜(阿基米德的太阳镜/科学家的怒火/创世纪/镇魂曲)CELESTIAL`
        + `LENS灵光：…`——英文续行拼回完整英文名"""
        text = "\n".join([
            "天体透镜(阿基米德的太阳镜/科学家的怒火/创世纪/镇魂曲)CELESTIAL",
            "LENS灵光：强烈塑能系",
            "施法者等级：20位置：无",
            "重量：2400磅天体透镜有一根12尺长的透镜安装在一个圆形框体三角架上。",
        ])
        items = run(text, source_name="魔法物品/page_949.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        d = it[0]
        assert d["title"] == "天体透镜", f"title={d['title']!r}"
        assert d["title_en"] == "CELESTIAL LENS", f"title_en={d['title_en']!r}"
        assert "阿基米德的太阳镜/科学家的怒火/创世纪/镇魂曲" in d.get("aliases", [])

    def test_seed_93_chm_artifact_section_head_negative(self):
        """[93] 949 章节标题负例：`高级神器MAJOR` + `ARTIFACTS最强大的神器…
        （英文后直接正文，无灵光粘着行）——不得误开条目，sink 保真"""
        text = "\n".join([
            "高级神器MAJOR",
            "ARTIFACTS最强大的神器，独一无二。最强大的生命都梦寐以求。",
        ])
        items = run(text, source_name="魔法物品/page_949.md")
        it = by_type(items, "item")
        assert len(it) == 0, f"章节标题不得开条目，实际 {[x.get('title') for x in it]}"

    def test_seed_94_chm_artifact_inline_joined_line(self):
        """[94] 949 join 后单行三合一形态（真实文件 page_949 行 7 实证：
        `_join_logical` 把「正文末行粘着标题」与「灵光行」拼成一行）：
        `…信仰灯塔BEACON  OF TRUE FAITH灵光：强烈(所有学派)`——行内切新
        条目：标题前正文回流上一条目、aura 挂字段"""
        text = "\n".join([
            "次级神器未必是独一无二的，但是它们也不是那么简单能用凡人的手段创造出来。信仰灯塔BEACON  OF TRUE FAITH灵光：强烈(所有学派)",
            "施法者等级：20位置：无",
            "重量：2磅信仰灯塔通常用银金矿(electrum)制成一个华丽的火炬形态。",
        ])
        items = run(text, source_name="魔法物品/page_949.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        d = it[0]
        assert d["title"] == "信仰灯塔", f"title={d['title']!r}"
        assert d["title_en"] == "BEACON OF TRUE FAITH", \
            f"英文名应归一拼接，实际 {d['title_en']!r}"
        f = d["fields"]
        assert f.get("aura") == "强烈(所有学派)", f"aura={f.get('aura')!r}"
        intro = items[0]
        assert "次级神器未必是独一无二的" in intro["text"], \
            f"标题前正文应回流 intro，实际 {intro['text']!r}"
        assert "信仰灯塔BEACON" not in intro["text"], \
            f"标题不应残留 intro，实际 {intro['text']!r}"

    def test_seed_95_chm_artifact_inline_altname_apostrophe(self):
        """[95] 949 join 单行 + 异名括号 + 撇号（真实 page_949 猿猴之手）：
        `…猿猴之手(大圣遗愿/怨)MONKEY'S  PAW灵光：强烈死灵系和共通系`——
        异名剥壳进 aliases、`'` 撇号英文段必须匹配"""
        text = "\n".join([
            "不过这只是纯粹的猜想，没有人知道它会出现在哪里。猿猴之手(大圣遗愿/怨)MONKEY'S  PAW灵光：强烈死灵系和共通系",
            "施法者等级：20位置：无",
            "重量：2磅这件超出想像的物品耐心地等待着被人拾起。",
        ])
        items = run(text, source_name="魔法物品/page_949.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        d = it[0]
        assert d["title"] == "猿猴之手", f"title={d['title']!r}"
        assert d["title_en"] == "MONKEY'S PAW", f"title_en={d['title_en']!r}"
        assert "大圣遗愿/怨" in d.get("aliases", []), \
            f"异名应进 aliases，实际 {d.get('aliases')!r}"
        assert d["fields"].get("aura") == "强烈死灵系和共通系", \
            f"aura={d['fields'].get('aura')!r}"

    def test_seed_96_chm_bare_title_starfield_chain(self):
        """[96] 29 炼金功能材料裸标题+残星字段链（page_29 强酸实证）：
        `强酸 Acid（AA）****价格：**10GP；**重量：**1磅**正文`——行首无
        星壳，GLUE 因 `$` 锚定失败、FULL 因无星失败——裸标题「中文 空格
        英文（缩写）」+ `****` 残星 + 字段链 + 同行正文"""
        text = "\n".join([
            "AA：Adventurer's Armory",
            "AM：Alchemy Manual",
            "强酸 Acid（AA）****价格：**10GP；**重量：**1磅**一瓶普通的强酸性物质适合添加进法术效果中",
            "==============================================",
            "材料成分功能****==============================================",
            "剂量：**1（价格10GP）；**可增强法术：**强酸箭（Acid Arrow）",
            "- 强酸箭（M）：**强酸箭的持续时间额外增加1轮。**",
            "炼金油膏 Alchemical Grease（AA）****价格：**5GP；**重量：**1磅**这种滑腻的物质适合增强法术",
            "==============================================",
        ])
        items = run(text, source_name="货品服务/page_29.md")
        it = by_type(items, "item")
        assert len(it) == 2, f"应产 2 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        d0, d1 = it
        assert d0["title"] == "强酸", f"title={d0['title']!r}"
        assert d0["title_en"] == "Acid", f"title_en={d0['title_en']!r}"
        f0 = d0["fields"]
        assert f0.get("price") == "10GP", f"price={f0.get('price')!r}"
        assert f0.get("weight") == "1磅", f"weight={f0.get('weight')!r}"
        assert d1["title"] == "炼金油膏", f"title={d1['title']!r}"
        assert d1["title_en"] == "Alchemical Grease", f"title_en={d1['title_en']!r}"
        # 字段行挂上一条目（剂量行冒号标签 ∈ 词表不误开条目）
        assert "剂量" in d0["text"], f"剂量行应并入强酸条目，实际 {d0['text'][:60]!r}"

    def test_seed_97_chm_star_title_crossline(self):
        """[97] 633 跨行星壳章节头：`**成为传说（Becoming` + `Legendary）**`
        ——行尾开壳无闭壳（行尾无空格 join 不生效），星壳括号跨行需主循环
        join 后按 FULL 处理；633 中「成为传说」是传说物品子章节（est 29 =
        能力条目口径），章节名词表守卫 → sink 保真进 intro"""
        text = "\n".join([
            "传说物品通常只是普通的魔法物品，但是能够凭借本身的力量逐渐成长为神器。",
            "**成为传说（Becoming",
            "Legendary）**",
            "传说物品是那些超越了纯粹的魔法，并且与神话命运产生共鸣的魔法物品。",
        ])
        items = run(text, source_name="魔法物品/神话冒险/page_633.md")
        it = by_type(items, "item")
        assert len(it) == 0, f"章节头不应开条目，实际 {len(it)}"
        intro = by_type(items, "intro")
        assert len(intro) == 1 and "成为传说" in intro[0]["text"] \
            and "超越了纯粹的魔法" in intro[0]["text"], \
            f"应保真进 intro，实际 {[x['text'][:30] for x in intro]}"

    def test_seed_98_chm_skill_star_title_list(self):
        """[98] 1067 星壳技能标题+道具清单（page_1067 特技实证）：
        `**特技**` + `用来维持平衡的平衡杆（UE）*2；…`——技能名星壳
        标题（无括号无英文，BARE_STAR 无守卫 sink）应开条目，清单行并入"""
        text = "\n".join([
            "**特技**",
            "用来维持平衡的平衡杆（UE）*2；便于立足的体育便鞋；有助跳跃的撑杆",
            "**估价**",
            "定价参考书；珠宝商用于检查微小细节的高倍目镜",
        ])
        items = run(text, source_name="货品服务/page_1067.md")
        it = by_type(items, "item")
        assert len(it) == 2, f"应产 2 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        d0, d1 = it
        assert d0["title"] == "特技", f"title={d0['title']!r}"
        assert "平衡杆" in d0["text"], f"清单应并入，实际 {d0['text'][:60]!r}"
        assert d1["title"] == "估价", f"title={d1['title']!r}"

    def test_seed_99_chm_full_inline_tail(self):
        """[99] 633 能力名闭壳+同行正文形态：`**娴熟（Adroit）**：选择…`
        ——FULL 匹配但行尾不闭壳（`）**` 闭壳后同行接正文），须开条目；
        864 嵌套星规则段头 `**武器擅长（****Proficiency****）**：攻城
        兵器属于…`（括号内 `**` = CHM 粗体嵌套残迹）→ sink 保真不开条目"""
        text = "\n".join([
            "**娴熟（Adroit）**：选择单一一项能够被物品的唤醒宝具能力加强的技能。",
            "**武器擅长（****Proficiency****）**：攻城兵器属于异种武器。",
        ])
        items = run(text, source_name="魔法物品/神话冒险/page_633.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应仅 1 条（武器擅长 sink），实际 {len(it)}"
        assert it[0]["title"] == "娴熟", f"title={it[0]['title']!r}"
        assert "选择单一" in it[0]["text"], f"正文应挂 text，实际 {it[0]['text'][:40]!r}"

    def test_seed_100_chm_legendary_section_and_slot_sink(self):
        """[100] 633 传说物品页结构：章节头（`**神话联结（Mythic
        Bond）**：传说物品通常…`）与边栏装备位列表项（`**腰部（Belt）**：
        基于力量…`）→ sink 保真（est 29 = 能力条目口径）；能力条目
        （`**娴熟（Adroit）**：选择…`）正常开条目"""
        text = "\n".join([
            "**神话联结（Mythic Bond）**：传说物品通常与一名神话生物具有联系。",
            "神话生物同一时间只能够与一个传说物品产生联结。",
            "**腰部（Belt）**：基于力量与敏捷的技能检定，以及体质检定",
            "**娴熟（Adroit）**：选择单一一项能够被物品的唤醒宝具能力加强的技能。",
        ])
        items = run(text, source_name="魔法物品/神话冒险/page_633.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应仅 1 条（章节头+位置 sink），实际 {len(it)}"
        assert it[0]["title"] == "娴熟", f"title={it[0]['title']!r}"
        intro = by_type(items, "intro")
        assert len(intro) == 1, f"应 1 个 intro（章节头+位置保真），实际 {len(intro)}"
        assert "神话联结" in intro[0]["text"], f"章节头应保真进 intro，实际 {intro[0]['text'][:60]!r}"
        assert "腰部" in intro[0]["text"], f"位置应保真进 intro，实际 {intro[0]['text'][:80]!r}"

    def test_seed_101_chm_legendary_section_joined_negative(self):
        """[101] 633 跨行星壳章节头负例：`**传说物品（Legendary ` +
        `Items）**` join 闭壳后 FULL 匹配——须 sink 保真（章节名词表
        守卫对跨行分支同样生效，防绕过超产）"""
        text = "\n".join([
            "**传说物品（Legendary",
            "Items）**",
            "传说物品最初通常只是普通的魔法物品。",
        ])
        items = run(text, source_name="魔法物品/神话冒险/page_633.md")
        it = by_type(items, "item")
        assert len(it) == 0, f"章节头不应开条目，实际 {len(it)}"
        intro = by_type(items, "intro")
        assert len(intro) == 1 and "传说物品" in intro[0]["text"], \
            f"应保真进 intro，实际 {[x['text'][:30] for x in intro]}"

    def test_seed_102_chm_inline_head_value_label(self):
        """[102] 695 草药行内链头：`地精藤 （PFS禁用，官网拼写错误了不过
        应该是禁了这个）价值：30GP采集 DC 16; 产量 1剂（1磅）…`——lookahead
        词表缺「价值」+ 组2 括号中文注释（非英文名）——开条目且英文名留空"""
        text = "\n".join([
            "| 草药 | 价格 |",
            "| --- | --- |",
            "| 地精藤 | 30GP |",
            "地精藤 （PFS禁用，官网拼写错误了不过应该是禁了这个）价值：30GP采集 DC 16; 产量 1剂（1磅）地形：任何森林",
        ])
        items = run(text, source_name="货品服务/page_695.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}"
        assert it[0]["title"] == "地精藤", f"title={it[0]['title']!r}"
        assert it[0]["title_en"] == "", f"括号中文注释不是英文名，实际 {it[0]['title_en']!r}"
        # `价值` ∈ 字段词表 → tail 字段链解析挂 fields.price（正确行为）
        assert it[0]["fields"].get("price") == "30GP", \
            f"价值：30GP 应解析进 fields.price，实际 {it[0]['fields']}"

    def test_seed_103_chm_tail_no_paren_value(self):
        """[103] 695 无括号草药链头：`夜鼠尾草价值：100GP重量 1lb专业
        （草药学）DC14地形：…`——TAIL 组2 括号可选化后 tail 以字段标签
        （价值）开头 → 开条目且英文名留空（无括号无英文）"""
        text = "\n".join([
            "| 草药 | 价格 |",
            "| --- | --- |",
            "| 夜鼠尾草 | 100GP |",
            "夜鼠尾草价值：100GP重量 1lb专业（草药学）DC14地形：任意丛林",
        ])
        items = run(text, source_name="货品服务/page_695.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}"
        assert it[0]["title"] == "夜鼠尾草", f"title={it[0]['title']!r}"
        assert it[0]["title_en"] == "", f"无括号形态英文应留空，实际 {it[0]['title_en']!r}"
        assert "价值：100GP" in it[0]["text"] or "100GP" in str(it[0]["fields"]), \
            f"价值应保真，实际 text={it[0]['text'][:40]!r} fields={it[0]['fields']}"

    def test_seed_104_chm_herb_no_table_fieldchain(self):
        """[104] 695 草药页无表格双形态：空格分隔（`蟥树皮价格 3 gp; 重量
        - 聚集 DC 16;…`）+ 冒号无括号（`夜鼠尾草价值：100GP重量 1lb…`）
        ——TAIL 组1 贪婪把字段标签（价格/价值）吃进标题 → 回拨给 tail，
        标题收窄真名 + 守卫通过开条目；`重量 -`（值形态非数字）不误判"""
        text = "\n".join([
            "地精藤 （PFS禁用）价值：30GP采集 DC 16; 产量 1剂（1磅）地形：任何森林",
            "蟥树皮价格 3 gp; 重量 - 聚集 DC 16; 产量 1d4剂地形：温暖的森林",
            "夜鼠尾草价值：100GP重量 1lb专业（草药学）DC14地形：任意丛林",
        ])
        items = run(text, source_name="货品服务/page_695.md")
        it = by_type(items, "item")
        assert len(it) == 3, f"应产 3 条，实际 {len(it)}"
        titles = [x["title"] for x in it]
        assert "蟥树皮" in titles, f"空格分隔形态未开，实际 {titles}"
        assert "夜鼠尾草" in titles, f"冒号无括号形态未开，实际 {titles}"
        ge = [x for x in it if x["title"] == "蟥树皮"][0]
        assert "3 gp" in str(ge.get("fields")) or "3 gp" in ge.get("text", ""), \
            f"蟥树皮价格应保真，实际 fields={ge.get('fields')} text={ge.get('text','')[:40]!r}"

    def test_seed_105_chm_sticky_title_inline_chain(self):
        """[105] 695 黛丝娜之星 粘着形态：介绍段行尾空格 + `黛丝娜之星
        （PFS禁用）价值：5GP重量 -…`——join 后标题嵌介绍段尾部（TAIL 组1
        被介绍段前 12 字占据）——行内链头切出条目，介绍段保真落 intro"""
        text = "\n".join([
            "草药格拉里昂生长着草药。这些折扣不与任何其他来源叠加。黛丝娜之星 ",
            "（PFS禁用）价值：5GP重量 -专业（草药学）DC13地形：森林与平原",
        ])
        items = run(text, source_name="货品服务/page_695.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}"
        assert it[0]["title"] == "黛丝娜之星", f"title={it[0]['title']!r}"
        intros = by_type(items, "intro")
        assert len(intros) == 1, f"介绍段应保真，实际 {len(intros)}"
        assert "草药格拉里昂" in intros[0]["text"], \
            f"介绍段应保真，实际 {intros[0]['text'][:40]!r}"

    def test_seed_106_chm_table_rows_as_items(self):
        """[106] 1254 艾恩石一览表（条目本体型表格）：48 行大表每行 1 颗
        艾恩石（效果/价格列即条目信息，无对应详述区）——表格行主循环
        sink 后末尾补切（候选名 − 已开条目名 = 净增量）；表头行/变体行
        （首列空，承接上行）不切；详述区已有同名条目不重复切"""
        text = "\n".join([
            "| 颜色 | 形状 | 灵光 | CL | 价格 | 效果 | 共振 | 制造需求 |",
            "| 暗灰色(Dull Gray) | 任意(Any) | 微弱通用系 | 12 | 25gp | 这些艾恩石的力量已被耗尽。 | 每天一次，阅读 | 需求文本 |",
            "| 破损的 |  |  |  | 3200gp | 摔绊战技检定+1表现加值。 |  |  |",
            "| 玛瑙色(Agate) | 椭圆(Ellipsoid) | 微弱预言系 | 9 | 1000gp | 战斗反射。 |  |  |",
            "**珠光金字塔形艾恩石Legal Pearlescent Pyramid Ioun Stone (Normal)**",
            "**灵光**：微弱防护系　**施法者等级**：5　**栏位**：无　**价格**：12000gp",
            "此艾恩石能提供保护。",
        ])
        items = run(text, source_name="魔法物品/奇物/无位置/page_1254.md")
        it = by_type(items, "item")
        titles = [x["title"] for x in it]
        # 表格行补切：暗灰色 + 玛瑙色（破损的承接暗灰色）；详述区珠光金字塔
        assert "暗灰色" in titles, f"表格行应补切条目，实际 {titles}"
        assert "玛瑙色" in titles, f"表格行应补切条目，实际 {titles}"
        assert "珠光金字塔形艾恩石" in titles, f"详述区条目应保留，实际 {titles}"
        assert len(it) == 3, f"应产 3 条（2 表格 + 1 详述），实际 {len(it)}：{titles}"
        # 变体行承接：破损的行并入暗灰色 text
        ag = [x for x in it if x["title"] == "暗灰色"][0]
        assert "破损的" in ag["text"] and "3200gp" in ag["text"], \
            f"变体行应承接上行，实际 text={ag['text'][:80]!r}"
        assert "暗灰色" in ag["text"], f"表格行原文应保真，实际 {ag['text'][:40]!r}"

    def test_seed_107_chm_effect_word_negative(self):
        """[107] 851 弹药效果表效果名负例（M4 效果词表防回退）：表头
        `| 效果名 | DC | 重量 | 制作时间 | 价格 |` 后 14 个效果行
        `| 流血（Bleeding） | 25 | - | 1小时 | 160GP |`——效果名有括号
        英文会误判「本体行独立收集」切出 `流血`/`耐用` 伪条目；效果名 =
        详述条目名去后缀（流血箭→流血），非独立条目 → _CHM_TABLE_EFFECT_WORDS
        词表排除，不产条目"""
        items = run(SEEDS[79]["raw_snippet"],
                    source_name="装备_魔法物品/武器_防具/page_851.md")
        it = by_type(items, "item")
        assert len(it) == 0, \
            f"效果行不应切出伪条目，实际 {len(it)}：{[x.get('title') for x in it]}"

    def test_seed_108_book_campaign_use_field_label_negative(self):
        """[108] 家族 3：超游神器 `**战役用途（Campaign Use）**`（×4）——
        FULL 分支无字段标签守卫误开 title=战役用途 伪条目（值在下一段
        正文）；组1 ∈ 词表 → 剥星落 text 保真并入当前条目"""
        text = "\n".join([
            "**隐匿伙伴之像（Familiar's Aid）**",
            "在其自然形态下，隐匿伙伴之像看起来不过是一块拳头大小的黏土块。",
            "**战役用途（Campaign Use）**",
            "被忽视的魔宠、体型太大而难以适应狭窄通道的动物伙伴。",
        ])
        items = run(text, source_name="装备_魔法物品/神器与传说/超游神器.md")
        it = by_type(items, "item")
        assert len(it) == 1, \
            f"应只产 1 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        d = it[0]
        assert d["title"] == "隐匿伙伴之像", f"title={d['title']!r}"
        assert "战役用途" in (d["text"] or ""), \
            f"战役用途字段行应落 text 保真，实际 text={d['text'][:60]!r}"

    def test_seed_109_book_glue_craft_dc_field_label_negative(self):
        """[109] 家族 3：SoS_炼金物品 `**制造DC**：工艺(炼金)25`——GLUE
        正则组2=`制造`+组3=`DC` 拆成「中文+英文名」误开 title=制造 伪条目；
        组1 ∈ 词表 → 走字段行解析，值挂 caster_level"""
        text = "\n".join([
            "**巨魔止血散（Troll Blood Salve）**",
            "**描述**：巨魔止血散是女巫们用巨魔血调制而成的一种药剂。",
            "**制造DC**：工艺(炼金)25",
        ])
        items = run(text, source_name="装备_魔法物品/货品服务/秘密探寻者SoS_炼金物品.md")
        it = by_type(items, "item")
        assert len(it) == 1, \
            f"应只产 1 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        d = it[0]
        assert d["title"] == "巨魔止血散", f"title={d['title']!r}"
        assert d["fields"].get("caster_level") == "工艺(炼金)25", \
            f"制造DC 值应挂 caster_level，实际 {d['fields'].get('caster_level')!r}"

    def test_seed_110_book_craft_condition_line_negative(self):
        """[110] 家族 3：亡灵杀手手册_奇物 `**工艺（炼金）**：DC 30`
        ——FULL 组1=`工艺` 误开 title=工艺 伪条目（DC 负向前瞻只拦无冒号
        形态 `DC 30`，`：DC 30` 带冒号穿透）；组1 ∈ 词表 → 剥星落 text"""
        text = "\n".join([
            "**日光瓶（Sunrod Bottle）**",
            "**制作条件**：",
            "**工艺（炼金）**：DC 30",
        ])
        items = run(text, source_name="装备_魔法物品/魔法物品/奇物/亡灵杀手手册_奇物.md")
        it = by_type(items, "item")
        assert len(it) == 1, \
            f"应只产 1 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        assert it[0]["title"] == "日光瓶", f"title={it[0]['title']!r}"
        assert "工艺" in (it[0]["text"] or ""), \
            f"制造条件行应落 text，实际 text={it[0]['text'][:60]!r}"

    def test_seed_111_book_glue_title_unaffected_positive(self):
        """[111] 家族 3 守卫正例：GLUE 正常条目 `**机械章鱼Apparatus of the
        Octopus****灵光**：…`（seed_57 真实无空格形态，组1=机械章鱼 ∉
        词表）不受标签守卫影响——组4 星壳字段链仍挂 fields"""
        text = "\n".join([
            "**机械章鱼Apparatus of the Octopus****灵光**：微弱防护系**施法者等级**：19",
            "这个八臂机械装置由精金与秘银打造。",
        ])
        items = run(text, source_name="装备_魔法物品/魔法物品/奇物/水下冒险.md")
        it = by_type(items, "item")
        assert len(it) == 1, \
            f"应只产 1 条，实际 {len(it)}：{[x.get('title') for x in it]}"
        d = it[0]
        assert d["title"] == "机械章鱼", f"title={d['title']!r}"
        assert d["fields"].get("aura") == "微弱防护系", \
            f"aura={d['fields'].get('aura')!r}"
        assert d["fields"].get("caster_level") == "19", \
            f"caster_level={d['fields'].get('caster_level')!r}"

    # ---------- M5 slot 字段污染修复（2026-08-09：CL 英文标签 / 价格裸段
    # 回退 / 全角逗号破折号 / 重复值 / 半角分号链）----------

    def test_seed_81_cl_english_label(self):
        """[81] CL 英文标签切分（AP 780/824 行实证）：词表已有 `CL`/`cl`
        但冒号链/裸段正则只匹配汉字标签 → `位置：无 CL：3rd 重量：1磅`
        的 `CL：3rd` 吞进 slot。标签字符类扩展 `[A-Za-z]`（词表校验
        兜底）后切出 caster_level"""
        text = "\n".join([
            "**测试圣徽（Test Holy Symbol）**",
            "位置：无 CL：3rd 重量：1磅",
            "正文描述",
        ])
        items = run(text, source_name="冒险之路AP_装备.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}"
        d = it[0]
        assert d["fields"].get("slot") == "无", f"slot={d['fields'].get('slot')!r}"
        assert d["fields"].get("caster_level") == "3rd", \
            f"caster_level={d['fields'].get('caster_level')!r}"
        assert d["fields"].get("weight") == "1磅", \
            f"weight={d['fields'].get('weight')!r}"

    def test_seed_82_price_bare_retro(self):
        """[82] 裸段尾缀回退（怪物召唤者手册 23 行实证）：`腕部价格 16000g`
        组1 贪婪吃 `腕部价格` 整体 ∉ 词表 → 段丢弃 → slot 吞价格。尾部
        最长前缀 ∈ 词表回退（`价格`）；守卫 = 回退目标 ∈ 字段标签词表
        （seed_34 正文 `该工具包可以使用10次` 尾部无字段词 → 不回退）"""
        text = "\n".join([
            "**测试护腕（Test Bracer）**",
            "位置：腕部价格 16000g",
            "灵光：中等防护系",
        ])
        items = run(text, source_name="怪物召唤者手册_奇物.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}"
        d = it[0]
        assert d["fields"].get("price") == "16000g", \
            f"price={d['fields'].get('price')!r}"
        assert d["fields"].get("aura") == "中等防护系", \
            f"aura={d['fields'].get('aura')!r}"
        assert d["fields"].get("slot") == "腕部", (
            f"slot 应为腕部（回退段 start=价格 真实起点，前缀 `腕部` "
            f"留作位置值），实际 {d['fields'].get('slot')!r}")

    def test_seed_83_chm_comma_dash(self):
        """[83] 全角逗号 + 破折号段切分（page_947 诅咒物品表格行实证）：
        `装备位置：眼部，重量—   它看起来像…`——`眼部` 后全角 `，`、
        `重量` 后破折号 `—`（U+2014）均不在裸段前瞻字符集 → 整段吞进
        slot。前瞻加 `，—` 后 slot=眼部、weight=`—`（未给出标记），
        描述经 _chm_value_body_cut 落 text 保真"""
        text = "\n".join([
            "**瞎人眼（Eyes of Blindness）**",
            "装备位置：眼部，重量—   它看起来像一副人畜无害的魔法目镜。",
        ])
        items = run(text, source_name="魔法物品/page_947.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}"
        d = it[0]
        assert d["fields"].get("slot") == "眼部", \
            f"slot={d['fields'].get('slot')!r}"
        assert d["fields"].get("weight") == "—", \
            f"weight 应保真 `—`，实际 {d['fields'].get('weight')!r}"
        assert "它看起来像" in (d["text"] or ""), \
            f"描述应落 text，实际 text={d['text'][:60]!r}"

    def test_seed_84_dup_value_merge(self):
        """[84] slot 值相邻重复词合并（AP 解渴高脚杯/UI 定时炸弹实证）：
        `位置：无 无 无；重量：1磅`——`无 无 无` 为解析残留，去重保序
        合并为 `无`"""
        text = "\n".join([
            "**测试水瓶（Test Flask）**",
            "位置：无 无 无；重量：1磅",
        ])
        items = run(text, source_name="冒险之路AP_装备.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}"
        d = it[0]
        assert d["fields"].get("slot") == "无", \
            f"slot={d['fields'].get('slot')!r}"
        assert d["fields"].get("weight") == "1磅", \
            f"weight={d['fields'].get('weight')!r}"

    def test_seed_85_semicolon_chain(self):
        """[85] 半角分号链（page_1254 艾恩石实证）：`**位置** 无; **价格**
        48,000 gp; **重量** —`——`_parse_space_field_line` 只按全角 `；`
        分段 → 整链吞进 slot。分段符扩展 `[；;]` 后剥星 + 半角分段
        slot/price/weight 各自归位（主循环分派无需改动）"""
        text = "\n".join([
            "**测试艾恩石（Test Ioun Stone）**",
            "**来源**Pathfinder #125: 溺毙者之塔 pg. 31",
            "**位置** 无; **价格** 48,000 gp; **重量** —",
            "**效果**",
            "正文描述。",
        ])
        items = run(text, source_name="魔法物品/奇物/无位置/page_1254.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 条，实际 {len(it)}"
        d = it[0]
        assert d["fields"].get("slot") == "无", \
            f"slot={d['fields'].get('slot')!r}"
        assert d["fields"].get("price") == "48,000 gp", \
            f"price={d['fields'].get('price')!r}"
        assert d["fields"].get("weight") == "—", \
            f"weight={d['fields'].get('weight')!r}"

    def test_seed_86_bare_chain_single_seg_retro(self):
        """[86] 链式分支单段值内裸标签二次切分（怪物召唤者手册_奇物
        裂石盔甲/束缚面容实证）：`位置 \\n盔甲价格 \\n21650g；` 三行
        join 成 `位置 盔甲价格  21650g；`——尾 `；` 使 `re.split(r"[；;]")`
        切出含空段 → 走链式分支（len(parts)>1），但链式段值不做值内
        裸段扫描 → slot 整吞 `盔甲价格 21650g`。段值统一过
        `_expand_inline_bare_segs`（与 else 分支同款：正式键集 +
        尾部最长前缀回退 `盔甲价格`→`价格`，前缀 `盔甲` 留作位置值）"""
        for name, price, slot in (
                ("测试盔甲（Test Armor）", "21650g", "盔甲"),
                ("测试面具（Test Visage）", "22900g", "头部")):
            text = "\n".join([
                f"**{name}**",
                "位置 ",
                ("盔甲价格 " if "盔甲" in name else "头部价格 "),
                f"{price}；",
                "灵光：中等咒法系",
            ])
            items = run(text, source_name="怪物召唤者手册_奇物.md")
            it = by_type(items, "item")
            assert len(it) == 1, f"应产 1 条，实际 {len(it)}"
            d = it[0]
            assert d["fields"].get("slot") == slot, (
                f"slot 应为 {slot!r}（回退段切价格，前缀留作位置值），"
                f"实际 {d['fields'].get('slot')!r}")
            assert d["fields"].get("price") == price, \
                f"price={d['fields'].get('price')!r}"
            assert d["fields"].get("aura") == "中等咒法系", \
                f"aura={d['fields'].get('aura')!r}"

    # ---------- 家族 A 相邻条目吞并修复（2026-08-09，seed_87~90） ----------

    def test_seed_87_bare_title_space_join(self):
        """[87] 跨行裸标题 join 吞并（HftF 艾恩石家族）：`北方 星形 `（行尾
        空格）+ `艾恩石（Northern Star Ioun Stone）`——_join_logical 并入
        后组1 含空格（`北方 星形 艾恩石`）裸标题正则不匹配 → 整条 sink
        吞进上一条目（散射投石索 price 三份）。join 锚点加「下一行括号
        裸标题行首」→ `艾恩石` 独立行正常开条目（方位词行 sink 保真）"""
        text = "\n".join([
            "散射投石索（Scatter Sling）",
            "价格：3300 金币",
            "位置：无 施法者等级：4 级 重量：无",
            "灵光：微弱咒法系灵光",
            "正文。",
            "制造成本：1650gp",
            "北方 星形 ",
            "艾恩石（Northern Star Ioun Stone）",
            "价格：10000 gp",
            "位置：无 施法者等级：12 级 重量：无",
            "灵光：强烈变化系灵光",
            "正文2。",
            "制造成本：5000gp",
        ])
        items = run(text, source_name="缘界英雄HftF_魔法物品.md")
        it = by_type(items, "item")
        assert len(it) == 2, (
            f"应产 2 条，实际 {len(it)}：{[x.get('title') for x in it]}")
        assert it[0]["title"] == "散射投石索"
        assert it[1]["title"] == "艾恩石", f"title={it[1]['title']!r}"
        assert it[1]["title_en"] == "Northern Star Ioun Stone", \
            f"title_en={it[1]['title_en']!r}"
        f = it[1]["fields"]
        assert f.get("price") == "10000 gp", f"price={f.get('price')!r}"
        assert f.get("slot") == "无", f"slot={f.get('slot')!r}"
        assert it[0]["fields"].get("price") == "3300 金币", \
            f"上一条 price 不应被吞：{it[0]['fields'].get('price')!r}"

    def test_seed_88_star_title_greater_comma(self):
        """[88] 星壳无括号标题英文名含 `，Greater` 变体标记（UI 高等挚友
        吊坠）：`**高等挚友吊坠Best Friend \nPendant，Greater**` join 后
        英文名 `Best Friend Pendant，Greater`——NOPAREN 字符类缺 `，` →
        标题不识别 → 详述区字段并入上一条目（slot `颈部 颈部` 双份）。
        字符类加全/半角逗号；英文名后中文正文天然截断不误伤"""
        text = "\n".join([
            "**挚友吊坠Best Friend Pendant**",
            "**栏位：**颈部  ",
            "**施法者等级：** 5",
            "**价格：**5000 GP ",
            "**重量** -",
            "**灵光：**昏暗咒法与变化系",
            "正文。",
            "**高等挚友吊坠Best Friend ",
            "Pendant，Greater**",
            "**栏位：**颈部  ",
            "**施法者等级：** 7",
            "**价格：**9000 GP ",
            "**重量** -",
            "**灵光：**中等咒法与变化系",
            "正文2。",
        ])
        items = run(text, source_name="魔法物品/极限诡道/UI奇物.md")
        it = by_type(items, "item")
        assert len(it) == 2, (
            f"应产 2 条，实际 {len(it)}：{[x.get('title') for x in it]}")
        assert it[1]["title"] == "高等挚友吊坠", f"title={it[1]['title']!r}"
        assert it[1]["title_en"] == "Best Friend Pendant，Greater", \
            f"title_en={it[1]['title_en']!r}"
        f = it[1]["fields"]
        assert f.get("price") == "9000 GP", f"price={f.get('price')!r}"
        assert f.get("caster_level") == "7", \
            f"caster_level={f.get('caster_level')!r}"
        assert it[0]["fields"].get("price") == "5000 GP", \
            f"上一条 price 不应被吞：{it[0]['fields'].get('price')!r}"

    def test_seed_89_pfs_bracket_prefix(self):
        """[89] `【PFS】` 前缀裸标题（AP 英雄酿）：`## 冒险之路AP 【PFS】
        【3.5R】英雄酿（Hero's `（H2 跨行未闭括号）+ `> 来源` + 裸行
        `【PFS】【3.5R】英雄酿（Hero's Brew）`——裸行/H2 守卫匹配前剥
        【】前缀（星壳分支 2538 同款）→ H2 同文守卫不成立（跨行残缺 ≠
        真名）不开，裸行开条目；修复前裸行 sink + 字段并入解渴高脚杯"""
        text = "\n".join([
            "## 冒险之路AP 解渴高脚杯（Goblet of ",
            "> 来源：冒险之路，页码见原书",
            "解渴高脚杯（Goblet of Quenching）",
            "灵光：微弱咒法系（创造） 施法者等级：1级 栏位：无 价格：180 gp 重量：1磅",
            "正文。",
            "## 冒险之路AP 【PFS】【3.5R】英雄酿（Hero's ",
            "> 来源：冒险之路，页码见原书",
            "【PFS】【3.5R】英雄酿（Hero's ",
            "Brew）",
            "出自：Second Darkness Player's Guide pg.",
            "25",
            "灵光：昏暗惑控系；施法者等级：5级",
            "栏位：无；价格：1,400GP；重量：-磅",
        ])
        items = run(text, source_name="冒险之路AP_装备.md")
        it = by_type(items, "item")
        assert len(it) == 2, (
            f"应产 2 条，实际 {len(it)}：{[x.get('title') for x in it]}")
        assert it[0]["title"] == "解渴高脚杯", f"title={it[0]['title']!r}"
        assert it[1]["title"] == "英雄酿", f"title={it[1]['title']!r}"
        f = it[1]["fields"]
        assert f.get("price") == "1,400GP", f"price={f.get('price')!r}"
        assert f.get("slot") == "无", f"slot={f.get('slot')!r}"
        assert it[0]["fields"].get("price") == "180 gp", \
            f"上一条 price 不应被吞：{it[0]['fields'].get('price')!r}"

    def test_seed_90_bare_pfs_mark(self):
        """[90] 裸标题组3 PFS 标记尾注（巨人猎手 轻松缎带）：`轻松缎带
        （Effortless Lace） PFS不可`——组3 非空但非字段链 → 守卫
        （_bare_title_follows/_bare_inline_chain）双不中 → sink 吞并。
        组3 PFS 标记/行内出处（`/`、`出自`、`出处`）视为条目头证据
        （C 形态 TAIL 守卫同口径）；PFS 残渣剥除（_split_flow_b1 1286 同款）"""
        text = "\n".join([
            "大地之子面罩（Earth Child Faceguard）",
            "灵光：中等变化系 施法者等级：10级 栏位：头部 价格：10,000gp 重量：无",
            "正文。",
            "轻松缎带（Effortless Lace） PFS不可",
            "正文2。",
        ])
        items = run(text, source_name="魔法物品/巨人猎手手册_新物品.md")
        it = by_type(items, "item")
        assert len(it) == 2, (
            f"应产 2 条，实际 {len(it)}：{[x.get('title') for x in it]}")
        assert it[1]["title"] == "轻松缎带", f"title={it[1]['title']!r}"
        assert "PFS不可" not in (it[1].get("text") or ""), \
            "PFS 残渣应剥除"
        assert it[0]["fields"].get("price") == "10,000gp", \
            f"上一条 price 不应被吞：{it[0]['fields'].get('price')!r}"

    def test_seed_91_semicolon_field_chain(self):
        """[91] 分号子段字段链（捕梦器/压胜人偶，异能冒险 page_1128）：
        `价格 2,800 gp；栏位 无；施法者等级`——`_RE_BARE_NOCOLON_SEG`
        前瞻 `无(?=\s|$)` 不认 `无；` → `栏位` 不成键、整链并进 price。
        修法：前瞻加 `；;` + ④链分号子段切分（有值挂字段、尾随无值剥除）"""
        text = "\n".join([
            "捕梦器 DREAMCATCHER",
            "价格 2,800 gp；栏位 无；施法者等级  ",
            "正文。",
            "压胜人偶 GANJI DOLL",
            "价格 16,000 gp；栏位 无；施法者等级6；重量 1/2磅；灵光 中等死灵系",
            "正文2。",
        ])
        items = run(text, source_name="魔法物品/异能冒险/page_1128.md")
        it = by_type(items, "item")
        assert len(it) == 2, (
            f"应产 2 条，实际 {len(it)}：{[x.get('title') for x in it]}")
        assert it[0]["title"] == "捕梦器", f"title={it[0]['title']!r}"
        assert it[1]["title"] == "压胜人偶", f"title={it[1]['title']!r}"
        assert it[0]["fields"].get("slot") == "无", \
            f"捕梦器 slot={it[0]['fields'].get('slot')!r}"
        assert it[1]["fields"].get("slot") == "无", \
            f"压胜人偶 slot={it[1]['fields'].get('slot')!r}"
        assert it[0]["fields"].get("price") == "2,800 gp", \
            f"捕梦器 price={it[0]['fields'].get('price')!r}"
        assert it[1]["fields"].get("price") == "16,000 gp", \
            f"压胜人偶 price={it[1]['fields'].get('price')!r}"
        assert it[1]["fields"].get("caster_level") == "6", \
            f"压胜人偶 caster_level={it[1]['fields'].get('caster_level')!r}"
        assert it[1]["fields"].get("weight") == "1/2磅", \
            f"压胜人偶 weight={it[1]['fields'].get('weight')!r}"

    def test_seed_92_lead_italic_pair(self):
        """[92] 段首成对斜体星壳剥壳（M5 星壳 25 家族）：`*获得降灵：*`
        段首斜体段（AP_装备 降灵条目）与独立行 `*进阶职业*`——偶数单星
        被判据视为「成对保留」而漏剥（KN160 家族缺口），段首星壳对
        须剥壳保留内文，行中斜体段（seed_70 `*蛛行术*`）不碰"""
        items = run(SEEDS[91]["raw_snippet"], source_name="冒险之路AP_装备.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        st = it[0]
        assert st["title"] in ("圣石守护者", "冒险之路AP 圣石守护者"), \
            f"title={st['title']!r}（A 形态允许书前缀，M3 清洗口径）"
        txt = st.get("text", "")
        assert "*获得降灵：*" not in txt, \
            f"段首星壳对应剥壳，实际 {txt[:80]!r}"
        assert "获得降灵：贝尔丹只会回应" in txt, \
            f"星壳内文应保留，实际 {txt[:80]!r}"
        assert "*进阶职业*" not in txt, \
            f"独立行星壳对应剥壳，实际 {txt[:80]!r}"
        assert "进阶职业" in txt, \
            f"独立行星壳内文应保留，实际 {txt[:80]!r}"

    def test_seed_93_sentence_punct_star_bbcode(self):
        """[93] 句读符后行尾裸星 + BBCode 残迹（M5 星壳 25 家族最后一例，
        page_632 塔因盔）：`*动物型态IV[/u]`（`[/u]` 顶替闭壳星，只有开壳
        星 1 个）+ 行尾 `变形。* `（1 个裸星）恰好凑偶数 → 旧判据「成对
        保留」漏剥。修法：句读符（。．！？：；）后行尾裸星无条件剥（斜体
        段内文不可能以句读符结尾再接星）；`[/u]` BBCode 残迹剥除并连带
        其前开壳星。行中成对斜体段（`*巨龙型态III*`）仍保留。"""
        text = "\n".join([
            "## 神话物品",
            "> 来源：神话冒险，页码见原书",
            "塔因盔（Tarnhelm）",
            "栏位 头部；施法者等级 20；重量 2磅",
            "每天三次，穿戴者可以化形成动物，如同他施展*动物型态IV[/u]，",
            "除了此效果将持续到被消解（dismissed）。穿戴者可以花费1次神话之",
            "力的使用次数来进行1次额外的变形。* ",
            "藉由花费2次神话之力的使用次数，穿戴者可以化身成为巨型五色龙。",
            "此能力在其他方面都视同*巨龙型态III*。",
        ])
        items = run(text, source_name="魔法物品/page_632.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        st = it[0]
        assert st["title"] == "塔因盔", f"title={st['title']!r}"
        txt = st.get("text", "")
        assert "[/u]" not in txt,             f"BBCode 残迹应剥除，实际 {txt[:120]!r}"
        assert "变形。*" not in txt,             f"句读符后行尾裸星应剥除，实际 {txt[:200]!r}"
        assert "动物型态IV" in txt and "*动物型态IV" not in txt,             f"开壳星应剥除保留内文，实际 {txt[:120]!r}"
        assert "*巨龙型态III*" in txt,             f"行中成对斜体段应保留，实际 {txt[-120:]!r}"

    def test_seed_94_bbcode_size_leak(self):
        """[94] `[/size]` BBCode 残迹泄漏（河域子民PotR_奇物 130 行，
        产物 3 chunk 污染）：`**需求**：…巧言术（tongues）[/size]`——
        无配对 `[size]`，直接剥除。与 seed_93 的 `[/u]` 同族，规则泛化
        为剥任何 `[/?[a-z]+]` 残迹（全库扫描仅此 2 家族）"""
        items = run(SEEDS[93]["raw_snippet"], source_name="河域子民PotR_奇物.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        txt = it[0].get("text", "")
        fld = it[0].get("fields", {})
        assert "[/size]" not in txt and "[/size]" not in str(fld), \
            f"[/size] 残迹应剥除，text={txt[:80]!r} fields={str(fld)[:120]!r}"
        # 需求行走 extra 保真字段（需求 ∈ EQUIP_EXTRA_FIELD_LABELS），
        # 残迹剥除后内文保留在字段值
        assert "巧言术（tongues）" in txt or "巧言术（tongues）" in str(fld), \
            f"残迹前内文应保留，text={txt[:80]!r} fields={str(fld)[:120]!r}"

    def test_seed_95_num_level_misaligned_star(self):
        """[95] 数字+汉字粗体闭壳误归位守卫（M6 审计 page_641 156 行家族）：
        `- **7级**：` 的 `级**：` 被 _RE_MISALIGNED_STAR 的星壳数量 0 星
        匹配误判为「左星壳缺失标签」→ 重排成 `- **7**级**：`。修法：
        lookbehind 排除集加 0-9——`**N级**：` 中 `级` 前是数字挡住；
        `位置**：`（ISC 左壳缺失真形态）仍归位，seed_49 回归保护"""
        items = run(SEEDS[95]["raw_snippet"], source_name="魔法物品/page_641.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        txt = it[0].get("text", "")
        assert "- **7级**：披风使得" in txt, \
            f"数字级粗体不应错位，实际 {txt[:160]!r}"
        assert "**10级**：穿戴者" in txt, \
            f"数字级粗体不应错位，实际 {txt[:160]!r}"
        assert "**7**级" not in txt and "**10**级" not in txt, \
            f"不应出现 **N**级 错位形态，实际 {txt[:160]!r}"

    # ---------- M6 A-1 字段剥壳修复回归（2026-08-09，seed_96~101） ----------

    def test_seed_96_noisy_paper_subcategory_alias_removed(self):
        """[96] 噪鸣纸 subcategory 误切回归（M6 KN）：需求值
        `制造奇物，*活化物品，魔嘴术*` 中的「物品」曾作为 subcategory 别名被
        `_expand_inline_bare_segs` 值内裸标签扫描切走 → 值断成
        `制造奇物，*活化` + `，魔嘴术*` 两段 + 伪 subcategory 键。别名移除后
        需求值完整且不产 subcategory 键（全库 66 处「物品」均为正文用法）"""
        items = run(SEEDS[96]["raw_snippet"], source_name="魔法物品/极限诡道/UI奇物.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        fld = it[0].get("fields", {})
        assert fld.get("需求") == "制造奇物，*活化物品，魔嘴术*", \
            f"需求值应完整（extra 键成对斜体壳设计保真），实际 " \
            f"{fld.get('需求')!r}"
        assert "subcategory" not in fld, \
            f"「物品」不应再产 subcategory 键，实际 {fld.get('subcategory')!r}"
        # 修复前（别名在位）：值断成 `制造奇物，*活化` + `，魔嘴术*` 两段
        # 且 text 中 `需求：` 行残缺——修复后整行值完整落在 extra「需求」键
        assert "制造奇物，*活化物品，魔嘴术*" in it[0].get("text", "") or \
            "制造奇物，*活化物品，魔嘴术*" in str(fld), \
            f"需求值不应断裂，text={it[0].get('text', '')[:80]!r}"

    def test_seed_97_folding_chair_en_open_star(self):
        """[97] 折叠椅英文名开壳星（M6 A-1）：`**折叠椅（*折凳）**` 的
        `*折凳` 开壳星（源数据 `<I>` 开标签转换残渣）应剥除 → title_en=折凳"""
        items = run(SEEDS[97]["raw_snippet"], source_name="货品服务/page_210.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        assert it[0]["title"] == "折叠椅", f"title={it[0]['title']!r}"
        assert it[0]["title_en"] == "折凳", \
            f"英文名开壳星应剥除，实际 {it[0]['title_en']!r}"
        assert "*" not in it[0]["title_en"], \
            f"title_en 不应含星，实际 {it[0]['title_en']!r}"

    def test_seed_98_caster_tattoo_quad_star_en(self):
        """[98] 施法者刺青四星嵌套英文名（M6 A-1）：源数据嵌套粗体
        `**施法者刺青（****Caster’s Tattoo****）**` → title_en 应剥壳为
        `Caster’s Tattoo`（含跨行空格归一）"""
        items = run(SEEDS[98]["raw_snippet"], source_name="魔法物品/奇物/page_275.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        assert it[0]["title"] == "施法者刺青", f"title={it[0]['title']!r}"
        assert it[0]["title_en"] == "Caster's Tattoo", \
            f"四星嵌套壳应剥除（引号归一直引号），实际 {it[0]['title_en']!r}"
        assert "*" not in it[0]["title_en"], \
            f"title_en 不应含星，实际 {it[0]['title_en']!r}"

    def test_seed_99_scarf_blade_crit_mult_star(self):
        """[99] 围巾刃重击倍率星（M6 A-1）：`重击【*2】` 的开壳星
        （源数据 `<I>*</I>2` 转换残渣）应剥除 → critical=2"""
        items = run(SEEDS[99]["raw_snippet"], source_name="内海世界指南ISWG_武器.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        fld = it[0].get("fields", {})
        assert fld.get("critical") == "2", \
            f"重击倍率开壳星应剥除，实际 {fld.get('critical')!r}"

    def test_seed_100_funeral_pyre_craft_conditions(self):
        """[100] 火葬珠制造条件斜体壳（M6 A-1）：`制造条件：…、*烙印术
        （BrandAPG）*、…` 的成对斜体法术名壳应剥除（值内星，首尾剥不覆盖
        → 白名单字段全星剥）"""
        items = run(SEEDS[100]["raw_snippet"], source_name="地狱骑士之道PotH_魔法物品.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        fld = it[0].get("fields", {})
        cc = fld.get("craft_conditions", "")
        assert cc.startswith("制造奇物（Craft Wondrous Item）、烙印术（BrandAPG）"), \
            f"制造条件斜体壳应剥除，实际 {cc!r}"
        assert "*" not in cc, f"craft_conditions 不应含星，实际 {cc!r}"

    def test_seed_101_pliant_gloves_c_form_bare_field(self):
        """[101] 柔性手套 C 形态裸字段行剥壳（M6 A-1）：page_228 裸字段行
        `制造条件：制造奇物、*流体形态(liquid form)…` 走 `_split_chm_page`
        `_RE_COLON_LEAD` 分支直挂 `cur["fields"].update(pf)`，不走
        `_assign_field_value` → 该处补白名单剥壳，值内斜体壳应剥除"""
        items = run(SEEDS[101]["raw_snippet"], source_name="魔法物品/奇物/page_228.md")
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        fld = it[0].get("fields", {})
        cc = fld.get("craft_conditions", "")
        assert cc == "制造奇物、流体形态(liquid form)(找不到该法术T,T)", \
            f"C 形态裸字段行斜体壳应剥除，实际 {cc!r}"
        assert "*" not in cc, f"craft_conditions 不应含星，实际 {cc!r}"

    # ---------- M6 A-2 text 真壳修复回归（2026-08-09，seed_102~109） ----------

    def test_seed_102_triple_star_pair(self):
        """[102] page_775 三连星对（R1a）：`***堑壕作战（Ex）：***` 是 HTML
        `<B>` 泄漏的 3 星对——剥成标准粗体保语义（`**堑壕作战（Ex）：**`）。
        黑市 `***锋锐术***` 等法术强调同族（seed_107）"""
        items = run(SEEDS[102]["raw_snippet"], source_name=SEEDS[102]["source"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        t = it[0].get("text", "")
        assert "**堑壕作战（Ex）：**" in t, \
            f"三连星对应剥成标准粗体，实际 {t[:120]!r}"
        assert "***堑壕作战" not in t, \
            f"不应残留 3 星开壳，实际 {t[:120]!r}"

    def test_seed_103_glue_quad(self):
        """[103] page_775 粗体闭开壳粘连（R2a）：`**战士变体：堑壕士兵****
        堑壕士兵（战士变体）TRENCH FIGHTER**`——4 星连续 = 前粗体闭壳+后
        粗体开壳合并，拆成 `**A** **B**` 两个独立粗体（两侧均为内容字符，
        非括号嵌套）"""
        items = run(SEEDS[103]["raw_snippet"], source_name=SEEDS[103]["source"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        t = it[0].get("text", "")
        assert "**战士变体：堑壕士兵** **堑壕士兵（战士变体）TRENCH FIGHTER**" in t, \
            f"4 星粘连应拆为两个粗体，实际 {t[:160]!r}"
        assert "****" not in t, f"text 不应含 4 星连续，实际 {t[:160]!r}"

    def test_seed_104_glue_space_open(self):
        """[104] 格拉里昂粘连+空格开壳（R2b）：`**武器特性**** ****怜悯
        （compassionate）*CL 7**`——4 星+空格+2 星 = 闭壳+开壳夹空格，剥成
        `**武器特性**`（尾部 `*CL 7` 单星残渣登记 KN189 不修）"""
        items = run(SEEDS[104]["raw_snippet"], source_name=SEEDS[104]["source"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        t = it[0].get("text", "")
        assert "**武器特性** " in t, \
            f"粘连+空格开壳应剥除，实际 {t[:120]!r}"
        assert "**** ****" not in t, \
            f"不应残留粘连星壳，实际 {t[:120]!r}"

    def test_seed_105_empty_star_line(self):
        """[105] page_234 空壳行（R3a）：`**` 独立行（`<B></B>` 转换残渣）
        剥除——text 应以正文行开头"""
        items = run(SEEDS[105]["raw_snippet"], source_name=SEEDS[105]["source"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        t = it[0].get("text", "")
        assert t.startswith("这种奇物不会局限"), \
            f"空壳行应剥除、text 以正文开头，实际 {t[:80]!r}"
        assert "\n**\n" not in t, f"text 不应含空壳行，实际 {t[:80]!r}"

    def test_seed_106_source_line_residue(self):
        """[106] ISI 来源行链接残渣（R1b）：链接壳 `[x](url)` 剥除后剩
        `** *****出自《内海诡道  Inner Sea Intrigue 50页》***`——整行
        剥成纯来源文本（行首锚定在链接剥除之后执行）"""
        items = run(SEEDS[106]["raw_snippet"], source_name=SEEDS[106]["source"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        t = it[0].get("text", "")
        assert t.startswith("出自《内海诡道  Inner Sea Intrigue 50页》"), \
            f"来源行星壳应剥除，实际 {t[:80]!r}"
        assert "*****" not in t, f"text 不应含来源行残渣，实际 {t[:80]!r}"

    def test_seed_107_triple_star_spell(self):
        """[107] 黑市三连星法术强调（R1a 保粗体语义）：`***锋锐术***` →
        `**锋锐术**`（`<B>` 泄漏剥壳不丢强调）"""
        items = run(SEEDS[107]["raw_snippet"], source_name=SEEDS[107]["source"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        t = it[0].get("text", "")
        assert "**锋锐术**" in t, f"三连星应剥成粗体，实际 {t[:120]!r}"
        assert "***锋锐术***" not in t, \
            f"不应残留 3 星对，实际 {t[:120]!r}"

    def test_seed_108_six_star_title_tail(self):
        """[108] page_567 6 星尾壳（R4b）：`**艾恩石效果******` 标题尾 6 星
        连续（`<B>` 闭壳泄漏）→ `**艾恩石效果**`。章节说明标题产 intro
        块——按 text 级断言剥壳效果"""
        items = run(SEEDS[108]["raw_snippet"], source_name=SEEDS[108]["source"])
        assert len(items) >= 1, f"应产 chunk，实际 {len(items)}"
        t = items[0].get("text", "")
        assert t.startswith("**艾恩石效果**"), \
            f"6 星尾壳应剥成标准闭壳，实际 {t[:80]!r}"
        assert "*" * 6 not in t, f"text 不应含 6 星连续，实际 {t[:80]!r}"

    def test_seed_109_glue_field_chain(self):
        """[109] page_851 字段链粘连（R2a）：`**效果详述****流血**` 两粗体
        相邻（字段链 4 星连续）→ 拆 `**效果详述** **流血**`"""
        items = run(SEEDS[109]["raw_snippet"], source_name=SEEDS[109]["source"])
        it = by_type(items, "item")
        assert len(it) == 1, f"应产 1 个 item，实际 {len(it)}"
        t = it[0].get("text", "")
        assert "**效果详述** **流血**" in t, \
            f"字段链粘连应拆开，实际 {t[:120]!r}"
        assert "****" not in t, f"text 不应含 4 星连续，实际 {t[:120]!r}"

    def test_seed_110_isc_paren_double_star_tail(self):
        """[110] ISC 艾恩石标题空壳行（A-2 暴露的既有切分器瑕疵）：
        `**刺球形艾恩石的共鸣之力（****EN****）**` 组2 后 `\s*\*{2,4}`
        贪婪吃掉 EN 后 4星，行尾闭壳 `**` 残留 tail 行首 → 剥 `）` 后
        恰 2 星闭壳须一并剥除（4 星前缀 seed_25 patron 形态不动）。
        标题行无字段链 + 下行为正文 → 判 category（intro），非 item"""
        items = run(SEEDS[110]["raw_snippet"], source_name=SEEDS[110]["source"])
        assert len(items) == 1, f"应产 1 chunk，实际 {len(items)}"
        assert items[0]["title"] == "刺球形艾恩石的共鸣之力", \
            f"标题应剥星壳，实际 {items[0]['title']!r}"
        assert items[0]["type"] == "category", \
            f"无字段链标题行应判 category，实际 {items[0]['type']!r}"
        t = items[0].get("text", "")
        assert not t.startswith("**"), f"text 不应以空壳行 `**` 开头，实际 {t[:80]!r}"
        assert t.startswith("当艾恩石"), f"text 应从正文开始，实际 {t[:80]!r}"
