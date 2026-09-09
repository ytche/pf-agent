"""
test_feat_format.py — 专长格式解析 TDD 测试（test_seeds.jsonl 驱动）

数据源：vectorizer/exploration/专长/专长_test_seeds.jsonl（58 条：38 positive + 20 negative）
驱动方：开工前文档 §六 第 5 步（test_seeds.jsonl 驱动 TDD 写 formats/feat.py）
断言口径：FeatFormat.normalize → promote → split_into_items 产出的 item dict：
  name / name_en / feat_type / format_cluster / pfs_eligible / text / source
"""

import json
import re
from pathlib import Path

import pytest

from vectorizer.formats.feat import FeatFormat, _split_paren_content as F_split_paren
from vectorizer.registry_feat import split_feat_types

SEEDS_PATH = Path(__file__).parent.parent / "exploration" / "专长" / "专长_test_seeds.jsonl"


def load_seeds():
    with open(SEEDS_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


SEEDS = load_seeds()


def run(raw: str) -> list:
    """FeatFormat 全链：normalize → promote → split"""
    fmt = FeatFormat()
    text = fmt.normalize(raw)
    text = fmt.promote(text)
    return fmt.split_into_items(text, source_name="seed")


def item_text(it: dict) -> str:
    """条目 text 归一化（去空白差异）供断言"""
    return re.sub(r"\s+", " ", it.get("text", ""))


class TestFeatSeeds:
    """26 条 test_seeds 逐条断言"""

    # ---------- positive ----------

    def test_seed_00_standard_entry_with_pfs(self):
        """[0] PFS 图标 + 跨行英文名 + 先决条件字段"""
        items = run(SEEDS[0]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "突袭警惕"
        assert it["name_en"] == "Ambush Awareness"  # 跨行英文名合并
        assert it["pfs_eligible"] is True            # PFS 图标提取
        assert "警觉" in item_text(it)               # 先决条件值保留
        assert "![[图片]]" not in item_text(it)

    def test_seed_page197_red_multi_bold_title(self):
        """page_197 红色多段加粗标题（相邻 `<B>` 段逐段星壳转换产物）：
        `**快步顺势斩（****Cleave Through****）****〔****战斗〕******` →
        标准解析。`_RE_NESTED_STAR` 只能吃「（）」段，`）****〔` 粘连残留
        「〔**战斗〕****」会漏进 text 且 feat_type 丢失（41 chunks）。"""
        items = run(
            "**快步顺势斩（****Cleave Through****）****〔****战斗〕******\n"
            "你那猛烈的挥砍能够伤到更多敌人。"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "快步顺势斩"
        assert it["name_en"] == "Cleave Through"
        assert it["feat_type"] == ["战斗"]
        assert "〔" not in item_text(it), "类型标记不应残留在 text"

    def test_seed_page203_type_paren_star_shell(self):
        """page_203 红色多段加粗标题 + 斜体正文段星壳残留：
        `**擒拿手（Grabbing Style）****（战斗，流派专长）******`（类型括号
        4 星包裹）→ normalize 拆出独立 `****` 行；正文 `<I>` 段转换残留
        `*   **正文*` 行首星壳（72 + 117 chunks）。链尾收口：
        独立纯星行删除 + 行首脏星壳正文归一为 `*正文*`（斜体标准形态，
        对齐 page_1564 详述区）。"""
        items = run(
            "**擒拿手（Grabbing Style）****（战斗，流派专长）******\n"
            "*   **你磨练自己挟制敌人的技巧，单手即可将对方抓牢。*\n"
            "**先决条件：**精通擒抱\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "擒拿手"
        assert it["name_en"] == "Grabbing Style"
        assert it["feat_type"] == ["战斗", "流派"]
        t = item_text(it)
        assert not t.startswith("****"), f"text 不应以 **** 开头：{t[:30]!r}"
        assert "****" not in t, "text 不应含独立 **** 行"
        assert "*   **" not in t, "text 不应含 `*   **` 星壳"
        assert "你磨练自己挟制敌人的技巧，单手即可将对方抓牢。" in t

    def test_seed_page529_slot_field_merge(self):
        """page_529 炫耀财富（OSTENTATIOUS DISPLAY）详述区星壳：
        金色粗斜体 `<B><I>` 字段段 `***装备位置：*********` → 链前部剥壳
        成独立 `*` 行 + `**装备位置：**` 独立行；前邻 `*** ***` 纯星壳行。
        收口后：纯星壳行删、`*` 残留行删、「装备位置」登记为字段标签并入
        当前条目（不产伪条目），字段保持加粗形态不被降级为 `*装备位置：*`。"""
        items = run(
            "**炫耀财富（OSTENTATIOUS DISPLAY）**\n"
            "**专长效果：**只要你在正常穿戴魔法物品的栏位装备有价的非魔法物品，"
            "让你在对应的技能上得到+1的加值。\n"
            "*** ***\n"
            "***装备位置：*********\n"
            "腰带、胸口、肩膀：+1威吓\n"
            "身体、脖子、脚部：+1交涉\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}（伪条目装备位置）"
        it = items[0]
        assert it["name"] == "炫耀财富"
        assert it["name_en"] == "OSTENTATIOUS DISPLAY"
        t = item_text(it)
        assert "**装备位置：**" in t, "字段标签应保持加粗：\n" + t
        assert "腰带、胸口、肩膀：+1威吓" in t
        lines = t.split("\n")
        assert not any(ln.strip() == "*装备位置：*" for ln in lines), \
            "字段标签不应被降级为斜体独立行"
        assert "***" not in t, f"text 不应含纯星壳行：{t!r}"
        assert not any(ln.strip() == "*" for ln in lines), "text 不应含独立 * 行"

    def test_seed_page321_god_feat_italic_shell(self):
        """page_321 神祇专长详述区（红色加粗标题 + `<B><I>` 粗斜体描述段）：
        `<B><I>&nbsp;</I></B>` 空段 + `<B><I>正文</I></B>` 拼接 → normalize
        后 `****正文***`（4开3闭）→ 链尾收口 `*正文*`（斜体标准形态）。"""
        items = run(
            "**祝福之锤（Blessed Hammer）**\n"
            "****你信仰的神明之力在你所持的战锤上熠熠生辉***\n"
            "**先决条件：**能够施放3环神术，擅长战锤，信仰托拉格\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "祝福之锤"
        assert it["name_en"] == "Blessed Hammer"
        t = item_text(it)
        assert "**你信仰的神明之力在你所持的战锤上熠熠生辉*" not in t, \
            "4 开 3 闭星壳应归一：\n" + t
        assert "你信仰的神明之力在你所持的战锤上熠熠生辉" in t
        assert not any(ln.startswith("*") and ln.endswith("*") and ln.startswith("**")
                       for ln in t.split("\n") if ln.startswith("*")), \
            "不应残留多星开头描述段"

    def test_seed_feat22_cover_fire_five_star_shell(self):
        """专长22 掩护射击详述段：`*****正文*`（5开1闭，`<B><I>` 粗斜体段
        normalize 削星残留）→ 链尾收口 `*正文*`（斜体标准形态）。"""
        items = run(
            "**掩护射击（Covering Fire）**\n"
            "*****你的射击能让敌人失去戒备，从而给你的队友创造行动机会。*\n"
            "**先决条件**：擅长异种武器（火器）UC，武器专攻（至少一种火器）。\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "掩护射击"
        t = item_text(it)
        assert "你的射击能让敌人失去戒备" in t
        assert not t.startswith("**"), f"text 不应以多星开头：{t[:40]!r}"
        assert not any(ln.strip().startswith("*****") for ln in t.split("\n")), \
            "5 开 1 闭星壳应归一：\n" + t

    def test_seed_feat54_smoking_boulder_quad_open(self):
        """专长54 冒烟巨石详述段：`****正文。`（4开0闭，`<B><I>` 段闭星
        normalize 削没 + 行尾截断）→ 链尾收口 `*正文。*`。"""
        items = run(
            "**冒烟巨石（Smoking Boulder）**\n"
            "****你掷出的巨石炽热燃烧，击中后腾起滚滚浓烟。\n"
            "**先决条件**：BAB\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "冒烟巨石"
        t = item_text(it)
        assert "你掷出的巨石炽热燃烧" in t
        assert not t.startswith("****"), f"text 不应以 **** 开头：{t[:40]!r}"

    def test_seed_page321_disciple_sword_dash_shell(self):
        """page_321 拔群剑术/梦魇伤疤详述段：3 段 `<B><I>` 粗斜体拼接
        （段1 + `——` 段 + 段2）→ normalize `****A****——**B`（段2 闭星残 0）。
        语义整句斜体 → `*A——B*` 一段归一（`——` 内嵌）。
        守卫：`**A**——**B**`（2开2闭合法并列加粗）不剥。"""
        items = run(
            "**拔群剑术（Disciplined Striker）**\n"
            "****你掌握艾奥梅黛的偏好武器****——**长剑的能力使同侪自叹不如。\n"
            "**先决条件：**武器专攻（长剑），4级审判者或牧师，信仰艾奥梅黛\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "拔群剑术"
        t = item_text(it)
        assert "你掌握艾奥梅黛的偏好武器——长剑的能力使同侪自叹不如" in t, \
            "破折号族应归一为一段斜体：\n" + t
        assert not t.startswith("****"), f"text 不应以 **** 开头：{t[:40]!r}"
        # 守卫：合法并列加粗不动
        items2 = run("**守卫测试（Guard Test）**\n**A**——**B**\n**先决条件：**X\n")
        assert len(items2) == 1
        assert "**A**——**B**" in item_text(items2[0]), "2开2闭并列加粗应保留"

    def test_seed_page556_indented_star_shell(self):
        """page_556 剧毒法术详述段：`  * **正文*`（术语条目格式缩进残留，
        normalize 时无缩进锚定的 BOL 逃逸，split 剥缩进后壳残留）→
        缩进容忍后收口 `*正文*`。"""
        items = run(
            "**无色无味（Unseen Poison）**\n"
            "   * **你可以隐蔽随身毒物的魔法灵光。*\n"
            "**先决条件：**唬骗技能5级，手艺（制毒）技能5级\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "无色无味"
        t = item_text(it)
        # 行级断言：item_text 压缩换行后「`*正文*` 闭星 + 空格 + 下行
        # `**先决条件**` 开星」会跨行粘连出 `* **` 子串，须按行判断。
        assert not any(ln.lstrip().startswith("* **") for ln in it["text"].split("\n")), \
            f"`* **` 缩进行首壳应剥除：{it['text']!r}"
        assert "你可以隐蔽随身毒物的魔法灵光" in t

    def test_seed_wmh_material_line(self):
        """武器大师手册_专长.md 材质行（page_369 `<I>标签：</I>正文` 转换残留，
        源数据已修复为 `*精金（Adamantine）：*正文`）：目标形态保持不回归。
        含带 UE 来源缩写族（净土青铜/毒琉璃 `）UE：` 在斜体内）与寒铁同族。"""
        items = run(
            "**神圣武器技巧（Sacred Weapon Mastery）**\n"
            "**先决条件：**基础攻击加值+7\n"
            "**专长效果：**当持用一把所选的近战武器时，你获得如下特殊能力。\n"
            "*精金（Adamantine）：*你的重击忽略目标的DR。\n"
            "*炼银（Alchemical Silver）/秘银（Mithral）或银纺（Silversheen）：*当你成功\n"
            "*寒铁（Cold Iron）：*每当你成功对一个受到法术效果影响的生物确认重击时\n"
            "*净土青铜（Elysium Bronze）UE：*每当你对一个魔法兽造成伤害时\n"
            "*毒琉璃（Viridum）UE：*你可以将你的力量调整值加入强韧豁免DC中\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "神圣武器技巧"
        t = item_text(it)
        assert "*精金（Adamantine）：*你的重击忽略目标的DR。" in t, \
            "材质行目标形态应保持：\n" + t
        assert "*炼银（Alchemical Silver）/秘银（Mithral）或银纺（Silversheen）：*" in t
        assert "*寒铁（Cold Iron）：*" in t, "寒铁行目标形态：\n" + t
        assert "*净土青铜（Elysium Bronze）UE：*" in t, "净土青铜行（UE 斜体内）：\n" + t
        assert "*毒琉璃（Viridum）UE：*" in t, "毒琉璃行（UE 斜体内）：\n" + t
        assert "* **" not in t, f"不应残留 `* **` 壳：{t[:80]!r}"

    def test_seed_page276_italic_trail_shell(self):
        """page_276 奥多里剑术详述段：`*正文***`（1开3闭，`<I>` 斜体段闭星
        未削净）→ 收口 `*正文*`。守卫：`***粗斜体***`/`**加粗**`/`*斜体*`
        对称星形不剥。"""
        items = run(
            "**奥多里剑术（Aldori Swordlord）**\n"
            "*你对自己的奥多里剑术手法充满自豪，这赋予了你勇气和冒险精神。***\n"
            "**先决条件：**擅长异种武器（奥多里决斗剑）\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "奥多里剑术"
        t = item_text(it)
        assert "*你对自己的奥多里剑术手法充满自豪，这赋予了你勇气和冒险精神。*" in t, \
            "1开3闭应收口 1开1闭：\n" + t
        assert not re.search(r"\*[^*\n]+\*{2,}$", t), f"不应残留斜体尾多星：\n{t}"

    def test_seed_page1367_field_quad_shell(self):
        """page_1367 超魔系专长：`**效果：****正文`（`**标签：**` 闭星与
        正文段开星粘连 4 星）→ `**效果：**正文`。守卫：正常字段不动。"""
        items = run(
            "**喝令法术（Commanding Spell）**\n"
            "**效果：****你能够调整一个影响效果为区域，持续时间为立刻的法术\n"
            "**先决条件：**法术专攻\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "喝令法术"
        t = item_text(it)
        assert "**效果：**你能够调整一个影响效果为区域" in t, \
            "字段后 4 星壳应收口 2 星：\n" + t
        assert "：****" not in t, f"不应残留 `：****` 壳：\n{t}"

    def test_seed_page202_italic_bold_mix_shell(self):
        """page_202 `<I>` 空段+正文段拼接：`*  **正文** *`（两端壳夹加粗中段）
        → BOL/EOL 剥壳 `*正文*`；`***  ****正文*****`（3开 空格 4星开）同族。
        守卫：`**正文**`（加粗）与 `***正文***`（粗斜体）行尾闭星不被剥。"""
        items = run(
            "**眩晕拳（Dazing Fist）**\n"
            "*  **你知道如何一拳将目标打懵的方法。** *\n"
            "**先决条件：**敏捷13，感知13，精通徒手击打，BAB+4\n"
            "**专长效果：**在正常造成伤害的同时，豁免检定失败的防御者将眩晕1轮\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        t = item_text(it)
        assert "*  **" not in t, f"行首星壳应剥除：{t!r}"
        assert "你知道如何一拳将目标打懵的方法。" in t
        # 合法粗斜体不受影响
        items2 = run("**测试（Test）**\n***合法粗斜体正文***\n**先决条件：**X\n")
        assert "***合法粗斜体正文***" in item_text(items2[0]), \
            "合法粗斜体应保留"
        # 合法加粗标题闭星不受影响
        items3 = run("**正常标题（Normal）**\n**先决条件：**X\n")
        assert items3[0]["name"] == "正常标题"

    def test_seed_pfs_star_residue_and_indent_star(self):
        """PFS 图片行尾壳 `[[PFS]]** ` 行（图片转标记后残留星）与缩进纯星行
        `    ****`（page_536 源数据）→ 删除，不落 text。"""
        items = run(
            "**天然毒素采集员（Toxin Harvester）**\n"
            "*你非常擅长从那些有毒的怪物身上采集或提炼毒素。*\n"
            "**先决条件：**工艺（炼金）6级，生存6级。\n"
            "**专长效果：**当你制造那些需要从有毒的怪物身上采集的毒素时，"
            "你在工艺（炼金）检定上获得+2加值。\n"
            "\n![[图片]](http://www.aonprd.com/images/PathfinderSocietySymbol.gif)** \n"
            "    ****\n"
            "**特殊情况：**PFS可用\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        t = item_text(items[0])
        assert "[[PFS]]" not in t, f"PFS 残留壳不应在 text：{t!r}"
        for ln in t.split("\n"):
            assert ln.strip() not in ("**", "****"), f"不应含纯星行：{t!r}"
        assert "特殊情况" in t

    def test_seed_01_duplicate_with_type_tag(self):
        """[1] 〔战斗〕类型标签版（与无标签版同条目重复）"""
        items = run(SEEDS[1]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "突袭警惕"              # 类型标签剥离
        assert "〔战斗〕" not in it["name"]
        assert it["feat_type"] == ["战斗"]
        assert it["pfs_eligible"] is True

    def test_seed_02_crossline_en_halfwidth_brackets(self):
        """[2] 跨行英文名 + 半角［］标签 + 多标签拆分"""
        items = run(SEEDS[2]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "友身作盾"
        assert it["name_en"] == "Ally Shield"
        assert it["feat_type"] == ["背叛", "团队"]

    def test_seed_03_standard_single_line(self):
        """[3] 标准单行闭合 + 〔战斗〕"""
        items = run(SEEDS[3]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "碎物者"
        assert it["name_en"] == "Chairbreaker"
        assert it["feat_type"] == ["战斗"]
        assert it["format_cluster"] == "standard"

    def test_seed_04_elided_quadruple_asterisk(self):
        """[4] elided：四星包裹 + 英文裸排 + （战斗专长）标签 + 字段同行紧贴"""
        items = run(SEEDS[4]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "酩酊侠"
        assert it["name_en"] == "Durnken Brawler"
        assert it["feat_type"] == ["战斗"]           # （战斗专长）归一化
        assert it["format_cluster"] == "elided"
        text = item_text(it)
        assert "先决条件" in text and "坚忍" in text
        # 字段同行紧贴拆分为独立字段
        assert re.search(r"先决条件[：:].*?(?=效果|$)", text), "先决条件/效果 需拆行"

    def test_seed_05_fc_t_table_row(self):
        """[5] FC-T 表格行：| EN名 中文名 | 先决条件 | 效果 |"""
        items = run(SEEDS[5]["raw_snippet"])
        assert len(items) == 1, f"表格行应产 1 个索引条目，实际 {len(items)}"
        it = items[0]
        assert it["name_en"] == "Brewmaster"
        assert it["name"] == "酿造大师"              # EN/CN 同行配对
        assert it["format_cluster"] == "lb_marker"
        assert "工艺" in item_text(it)

    def test_seed_05b_full_table_rows_not_merged(self):
        """完整表格行（行尾闭合 |）不得被续行合并：多行各自产条目。

        回归：_RE_TABLE_CONT 原实现无行首锚定，\\| 匹配到上一行行尾闭合
        |，把整张表格粘成一行、仅首行产条目（page_195 专长索引表 ~150
        行 → 0 产出，41 条召回缺口的根因之一）。
        """
        raw = (
            "| Acrobatic        特技专家 |  | 特技和飞行检定+2 |\n"
            "| Armor Proficiency, Light        擅长轻型盔甲 |  | 穿轻甲时攻击无防具减值 |\n"
            "| Alertness        警觉 |  | 察觉和察言观色检定+2 |\n"
        )
        items = run(raw)
        assert len(items) == 3, f"3 行完整表格行应各自产 1 条目，实际 {len(items)}"
        names = [it["name"] for it in items]
        assert "擅长轻型盔甲" in names
        assert "特技专家" in names
        assert "警觉" in names
        assert all(it["format_cluster"] == "lb_marker" for it in items)

    def test_seed_06_table_outer_entry(self):
        """[6] 表格外正文条目（与表格行合法双份）：四星包裹变体"""
        items = run(SEEDS[6]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "酿造大师"
        assert it["name_en"] == "Brewmaster"

    def test_seed_07_index_line_with_source_abbr(self):
        """[7] 索引列表行：【来源缩写】中文名（类型）（English）"""
        items = run(SEEDS[7]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "抵异作成"
        assert it["name_en"] == "Aligned Crafting"
        assert it["feat_type"] == ["造物"]
        assert it["source"] == "PotW"                # 【来源缩写】
        assert it["format_cluster"] == "lb_marker"

    def test_seed_07b_index_lines_cross_line_en_not_swallowed(self):
        """[7b] 多列表行连续 + 跨行 EN 不得互吞（KN050 回归）

        回归：_RE_INDEX_LINE 组4 `[^)]*` 只排除半角 )，源数据 EN 括号是
        全角 ）——组4 贪婪跨行吞掉后续全部列表行（\4 原样放回掩盖破坏），
        仅首行标记且 〔类型〕** 尾被推走，split 全部落空。
        造物专长一览（est=28 got=19）根因：28 列表行只有首行产出。

        同时覆盖两个伴生形态：
          - 中文名含斜杠（制造波普宠/制造人偶）——组2 须允许 `/`
          - 行尾多余来源标记（【3.5R】）——EN 括号后尾部容错，索引行
            丢弃该标记（3.5 规则来源由详情区 `**【3.5R】…**` 完整覆盖）
        """
        raw = (
            "【PotW】抵异作成（造物）（Aligned Crafting）\n"
            "【#16】调制塑肉毒素（造物）（Brew Fleshcrafting \n"
            "Poison）【3.5R】\n"
            "【CRB】调制药剂（造物）（Brew Potion）\n"
            "【AA2】制造波普宠/制造人偶（造物）（Craft \n"
            "Poppet）\n"
            "【#5】铭刻符文（造物）（Inscribe \n"
            "Rune）【3.5R】\n"
        )
        items = run(raw)
        assert len(items) == 5, f"5 列表行应各产 1 条目，实际 {len(items)}"
        assert [it["name"] for it in items] == [
            "抵异作成", "调制塑肉毒素", "调制药剂",
            "制造波普宠/制造人偶", "铭刻符文",
        ]
        assert all(it["format_cluster"] == "lb_marker" for it in items)
        assert items[1]["source"] == "#16" and items[3]["source"] == "AA2"

    def test_seed_08_quest_line_feat(self):
        """[8] 任务链专长：无加粗标题 + 字段同行紧贴"""
        items = run(SEEDS[8]["raw_snippet"])
        assert len(items) == 1, f"任务链专长应产 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "困于城中"
        assert it["feat_type"] == ["故事"]
        text = item_text(it)
        assert "先决条件" in text
        assert "即时收益" in text                     # 同行字段拆分
        assert "专长目标" in text
        assert "City-Locked" in text or it["name_en"] == "City-Locked"

    def test_seed_09_bare_title_with_crossline_en(self):
        """[9] 标题无加粗：纯文本 中文名(English)"""
        items = run(SEEDS[9]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "雕像伙伴"
        assert it["name_en"] == "Companion Figurine"
        assert it["format_cluster"] == "elided"      # 星号缺失形态

    def test_seed_10_whitespace_paren_spacing(self):
        """[10] whitespace：括号前空格 + 类型在括号内 + 无闭合星"""
        items = run(SEEDS[10]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "密集阻击"
        assert it["name_en"] == "Barrage of Styles"
        assert it["feat_type"] == ["战斗", "团队"]
        assert it["format_cluster"] == "whitespace"

    def test_seed_11_punct_halfwidth_parens(self):
        """[11] punct：半角圆括号类型 + 四星英文名包裹"""
        items = run(SEEDS[11]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "上下合围"
        assert it["feat_type"] == ["战斗", "团队"]
        # KN070 后：_RE_BOLD_GLUE_SPLIT 把 `）****(Combat,` 拆为标题闭合 +
        # 截断残留落正文行 → standard（信息保留完整）；旧路径 _fix_quad_star_
        # halfparen elided 降级仅用于 `****(` 未拆场景（全角括号变体）
        assert it["format_cluster"] == "standard"
        assert "(Combat," in item_text(it)          # 截断残留保留在正文

    def test_seed_12_field_label_colon_right(self):
        """[12] 标签在冒号右（先决条件**：）+ 同行多字段 + 跨行英文名"""
        items = run(SEEDS[12]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "高等时髦法术"
        assert it["name_en"] == "Greater Stylized Spell"
        text = item_text(it)
        assert "先决条件" in text and "时髦法术（Stylized Spell）" in text
        assert "专长效果" in text                     # 同行多字段拆分

    def test_seed_13_bare_title_with_source_line(self):
        """[13] 无加粗标题 + 出处混排（出自《书名》页）"""
        items = run(SEEDS[13]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "溅射武器大师"
        assert it["name_en"] == "Splash Weapon Mastery"
        assert it["format_cluster"] == "elided"
        assert "冒险家军械库" in item_text(it)        # 出处保留可提取

    def test_seed_14_crossline_en_closing_star_own_line(self):
        """[14] 跨行英文名 + ** 闭合符独占一行 + 无类型标签"""
        items = run(SEEDS[14]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "邪恶领导力"
        assert it["name_en"] == "Vile leadership"
        assert it["feat_type"] == []

    # ---------- negative ----------

    def test_seed_15_translator_line(self):
        """[15] 译者行：不产条目"""
        assert run(SEEDS[15]["raw_snippet"]) == []

    def test_seed_16_url_line_with_translator(self):
        """[16] 链接行（KN023 高危）：剥离不产条目、不截断"""
        assert run(SEEDS[16]["raw_snippet"]) == []

    def test_seed_17_intro_prose(self):
        """[17] 前言散文：不产条目"""
        assert run(SEEDS[17]["raw_snippet"]) == []

    def test_seed_18_deity_block(self):
        """[18] 神祇分块叙述：不产条目"""
        assert run(SEEDS[18]["raw_snippet"]) == []

    def test_seed_19_non_feat_table(self):
        """[19] 非条目表格（追随者修正表）：不产条目"""
        assert run(SEEDS[19]["raw_snippet"]) == []

    def test_seed_20_table_separator_row(self):
        """[20] 表格分隔行 | --- |：不产条目"""
        assert run(SEEDS[20]["raw_snippet"]) == []

    def test_seed_21_table_bilingual_split_rows(self):
        """[21] 表格双语分行：EN 行与 CN 行配对为一条目，不拆两条"""
        items = run(SEEDS[21]["raw_snippet"])
        assert len(items) == 1, f"EN/CN 分行应配对为 1 条，实际 {len(items)}"
        assert items[0]["name_en"] == "False Casting"

    def test_seed_22_section_header(self):
        """[22] 小节标题（半鱼人专长）：不产条目"""
        assert run(SEEDS[22]["raw_snippet"]) == []

    def test_seed_23_source_annotation_line(self):
        """[23] 出处标注行（annotation）：不单独计条目"""
        assert run(SEEDS[23]["raw_snippet"]) == []

    def test_seed_24_magic_item_entry(self):
        """[24] 非专长物品（价格/重量字段）：不产条目"""
        assert run(SEEDS[24]["raw_snippet"]) == []

    def test_seed_25_inline_feat_reference(self):
        """[25] 正文引用句：不产条目"""
        assert run(SEEDS[25]["raw_snippet"]) == []

    def test_seed_26_field_label_standalone_line(self):
        """[26] R2 字段标签独立行：**先决条件：**/**专长效果：** 不产新条目、标签并入 text"""
        items = run(SEEDS[26]["raw_snippet"])
        assert len(items) == 1, f"字段标签行不产新条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "魔族仪典"
        text = item_text(it)
        assert "先决条件" in text and "专长效果" in text   # 标签行保留（供 parse_fields）
        assert "在知识〔宗教〕技能上拥有3个等级" in text
        assert "你获得神恩" in text

    def test_seed_27_punct_title(self):
        """[27] R3 punct 标题：**可信伪装：** 独立冒号加粗行作条目标题"""
        items = run(SEEDS[27]["raw_snippet"])
        assert len(items) == 1, f"punct 标题应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "可信伪装"
        assert it["format_cluster"] == "punct"
        text = item_text(it)
        assert "假面伪装" in text          # 描述并入
        assert "前置" in text              # 裸字段并入

    def test_seed_28_ag_title_with_en_after_type(self):
        """[28] R4 AG 标题形态：**中文（类型）English** 类型括号后接英文名"""
        items = run(SEEDS[28]["raw_snippet"])
        assert len(items) == 1, f"AG 标题应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "奥多里战斗技艺"
        assert it["name_en"] == "Aldori Artistry"
        assert it["feat_type"] == ["战斗"]
        assert it["format_cluster"] == "standard"
        text = item_text(it)
        assert "异种武器擅长" in text

    def test_seed_29_prose_fake_title_negative(self):
        """[29] R5 正文句伪标题：当你通过魔族仪典（Fiendish Obedience ）专长获得神恩时… 不产条目"""
        assert run(SEEDS[29]["raw_snippet"]) == []

    def test_seed_30_bare_title_with_space_en_type(self):
        """[30] 无加粗标题 中文空格English（类型）：中英之间有空格（B 分支 \\s*），永罪 FC-6"""
        items = run(SEEDS[30]["raw_snippet"])
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "锁链熟稔"
        assert it["name_en"] == "Chain Mastery"
        assert it["feat_type"] == ["战斗"]
        assert it["format_cluster"] == "elided"

    def test_seed_31_dual_paren_cn_type_en(self):
        """[31] FC-1r 双括号：**中文（类型）（English）** name 不得吞第一个括号对"""
        items = run(SEEDS[31]["raw_snippet"])
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "致命之角"                 # 无（战斗专长）残留
        assert "战斗" in it["feat_type"]
        assert it["format_cluster"] == "standard"

    def test_seed_32_star_bold_with_slash_cn_name(self):
        """[32] 行首星+斜杠中文名：**时髦/风格化魔法 English***** name 含斜杠不截断"""
        items = run(SEEDS[32]["raw_snippet"])
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "时髦/风格化魔法"
        assert it["name_en"] == "Stylized Magic"
        assert it["format_cluster"] == "elided"

    def test_seed_33_long_prose_section_negative(self):
        """[33] 子节标题过滤：闭合标题 + 长 text 无字段标签（灵魂贸易规则小节）→ 不产条目"""
        assert run(SEEDS[33]["raw_snippet"]) == []

    def test_seed_34_pantheon_entry_field_text_kept(self):
        """[34] 万神殿条目豁免子节标题过滤：神祇/常见信徒/类法能力列表正文
        （`**常见信徒**` 星包裹无冒号形态，page_673 万神殿段）→ 条目保留。
        KN052 回归：乌笃喇神殿正文无 `**标签：**` 冒号字段，曾被子节标题
        过滤器（text>150 无字段标签）误删；万神录专属字段放行。"""
        raw = (
            "**乌笃喇神殿（文化）**\n"
            "　**神祇**　Chamidu (N), Dhalavei (LE), Gruhastha (LG), "
            "lrori*(LN), Lahkgya (CE), Likha (N), Ragdya (N), Raumya (NE), "
            "Suyuddha (LN), Vineshvakhi (LN), Vritra (LE), thousands of other deities\n"
            "**常见信徒** 乌笃喇人\n"
            "**类法能力** 克敌机先（true strike）"
        )
        items = run(raw)
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "乌笃喇神殿"
        assert "常见信徒" in item_text(it)
        assert "类法能力" in item_text(it)
        assert "神祇" in item_text(it)

    def test_seed_35_elided_inline_desc_same_line(self):
        """[35] 同行 elided 描述：`**中文（EN）****　　*描述*`（4 星 + 同行
        单星描述，任务与战役_专长 17 处）→ elided 标题 + 描述拆行。
        KN053 回归：原被 _RE_BARE_CN_EN_STAR_BOLD（D 分支）误吞，组2 含
        括号再包层 → `（（EN））` 双括号 → split 不识别全丢。"""
        raw = (
            "**权力中心（CENTER OF POWER）****　　*你已将忠诚的追随者"
            "安插至最关键的位置。*\n"
            "　　先决条件**：领导力值13"
        )
        items = run(raw)
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "权力中心"
        assert it["name_en"] == "CENTER OF POWER"
        assert "你已将忠诚的追随者" in item_text(it)
        assert "先决条件" in item_text(it)

    def test_seed_36_elided_inline_desc_cross_line_en(self):
        """[36] 跨行 EN + 同行 elided 描述：`**中文（EN 前半\nEN 后半）****
        `　　*描述*`（任务与战役_专长 8 处）→ 跨行合并后同 [35]。"""
        raw = (
            "**专业教练（EXPERT \n"
            "TRAINER）****　　*你拥有特定领域的特殊天赋，并能轻松掌握其精髓。*\n"
            "　　专长效果**：选择三个职业。"
        )
        items = run(raw)
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "专业教练"
        assert it["name_en"] == "EXPERT TRAINER"
        assert "你拥有特定领域" in item_text(it)

    def test_seed_37_elided_inline_desc_type_suffix(self):
        """[37] 同行 elided + 类型括号尾：`**中文（EN）（类型）****　　*描述*`
        （任务与战役_专长故事专长 6 处）→ 标题含类型。"""
        raw = (
            "**登神之路（APOTHEOSIS）（故事）****　　*你被命运标选为未来的"
            "神明——即使你还没有意识到此等宿命，命运将屈从于你的意志。*"
        )
        items = run(raw)
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "登神之路"
        assert it["name_en"] == "APOTHEOSIS"
        assert it["feat_type"] == ["故事"]


class TestBareCnTitle:
    """FC-8n 裸中文条目标题（page_744 痛苦选项型）：`**截肢**` + 后行单星 `*描述*` 佐证 → 条目"""

    BARE_CN_RAW = (
        "**截肢**\n"
        "*你已经截断了你的一根手指并治疗了伤口从而让它再也不能完全愈合。*\n"
        "**服从仪典**：操控你截断的手指的血痂、疤痕和开放的伤口，阻止它闭合，"
        "并把一些金属或玻璃强行弄进伤口。你会在解除装置、易容、逃脱、巧手检定"
        "以及你对抗卸武的CMD上承受-2减值。当尝试施放带\n"
        "你在对抗变化系法术的豁免投骰上获得+2加值；如果这个法术是变形子学派的则加值提高到+4。\n"
        "**第一恩惠**：除了痛苦打击的正常效果外，目标还可能在你用痛苦打击击中它后"
        "立即掉落手中的一个物体。成功的反射豁免（DC为10+1/2HD+你的敏捷调整值）可以避免此效果。"
    )

    def test_bare_cn_title_with_italic_desc_produces_item(self):
        """FC-8n：**截肢** + 后行单星描述 → 产 1 条（痛苦选项条目）"""
        items = run(self.BARE_CN_RAW)
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "截肢"
        text = item_text(it)
        assert "服从仪典" in text and "第一恩惠" in text

    def test_bare_cn_without_italic_desc_is_section_header(self):
        """负例：裸中文闭合行 + 后行非单星（正文）→ 维持分节标题跳过（不破坏 seed_22）"""
        raw = (
            "**半鱼人专长**\n"
            "半鱼人拥有下列专长。\n"
            "**鱼人专长（Fish Feat）**\n"
            "正文描述。"
        )
        items = run(raw)
        assert all(it["name"] != "半鱼人专长" for it in items)
        assert any(it["name"] == "鱼人专长" for it in items)

    # ---------- R1：根目录 66 文件形态缺口（M1~M7 共性机制） ----------

    def test_seed_34_closed_title_with_same_line_source(self):
        """[34] M1 闭合星+同行出自：**中文（类型） English（Combat）** 闭合后同行跟『出自…第N页』"""
        items = run(SEEDS[34]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "不屈坐骑"
        assert it["name_en"] == "Indomitable Mount (Combat)"
        assert "战斗" in it["feat_type"]
        text = item_text(it)
        assert "出自" in text or "格拉利昂的城市" in text   # 来源并入 text 不吞 name_en

    def test_seed_35_closed_title_star_outside_en(self):
        """[35] M2 闭合星+星外英文：**中文**English 星内中文闭合、英文在星外、同行跟 Source"""
        items = run(SEEDS[35]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "生物专攻"
        assert it["name_en"] == "Creature Focus"
        text = item_text(it)
        assert "Source" in text                          # 来源并入 text
        assert "先决条件" in text and "宿敌" in text       # 裸字段行保留

    def test_seed_36_fc1v_closed_star_paren_en(self):
        """[36] M3 FC-1v：**中文**（English） 闭合星后括号英文名"""
        items = run(SEEDS[36]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "位面训导"
        assert it["name_en"] == "Planar Mentor"
        text = item_text(it)
        assert "好处" in text                            # 裸字段保留

    def test_seed_37_fc1n_no_closing_star(self):
        """[37] M4 FC-1n 无闭合星：**中文（English） 行尾无闭合星 + *** 正文行"""
        items = run(SEEDS[37]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "哈罗召唤术"
        assert it["name_en"] == "Harrowed Summoning"
        assert it["format_cluster"] == "standard"
        text = item_text(it)
        assert "前提" in text and "好处" in text          # 字段并入

    def test_seed_38_hash_title(self):
        """[38] M5 井号标题：# 中文（English） 井号条目标题（判别器 FC-H）"""
        items = run(SEEDS[38]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "剧毒咬撃"
        assert it["name_en"] == "Noxious Bite"
        assert it["format_cluster"] == "standard"
        text = item_text(it)
        assert "前置需求" in text

    def test_seed_39_bare_cn_en_line(self):
        """[39] M6 裸中英行：『中文English』无星行首条目标题（判别器 FC-8e）"""
        items = run(SEEDS[39]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "恶魔克星"
        assert it["name_en"] == "Demonic Nemesis"
        assert it["format_cluster"] == "elided"
        text = item_text(it)
        assert "描述" in text and "类型" in text and "先决条件" in text   # 裸字段并入

    def test_seed_40_closed_title_same_line_colon(self):
        """[40] M7 闭合星+同行冒号：**中文（English, 类型）**： 冒号在闭合星后"""
        items = run(SEEDS[40]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "羊首狮身之角"
        assert "战斗" in it["feat_type"]
        text = item_text(it)
        assert "狮子般" in text                          # 冒号后正文并入

    def test_seed_41_closed_title_type_star_outside_en(self):
        """[41] M8 星内类型闭合+星外英文名：**中文（类型）** English（FC-4 变体）"""
        items = run(SEEDS[41]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "弹跳锤"
        assert it["name_en"] == "Bounding Hammer"
        assert "战斗" in it["feat_type"]
        text = item_text(it)
        assert "先决条件" in text and "专长效果" in text      # 字段并入

    def test_seed_42_bare_cn_en_line_cn_tail(self):
        """[42] M9 裸中英行+中文尾缀：『中文English 中文后缀』（FC-8e）"""
        items = run(SEEDS[42]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "天堂升华"
        assert it["name_en"] == "Talmandor's Lifting"
        assert it["format_cluster"] == "elided"
        text = item_text(it)
        assert "条件" in text and "效果" in text              # 裸字段并入

    def test_seed_43_cn_line_uppercase_en(self):
        """[43] M10 中文行+全大写英文行：『中文\\nALLCAPS』（FC-7c）"""
        items = run(SEEDS[43]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "多样尊崇"
        assert it["name_en"] == "DIVERSE OBEDIENCE"
        assert it["format_cluster"] == "elided"
        text = item_text(it)
        assert "先决条件" in text and "好处" in text           # 裸字段并入

    def test_seed_44_hash_title_cn_type_en(self):
        """[44] M11a 井号标题带类型+英文：『## 中文（类型） English』（FC-Hb）"""
        items = run(SEEDS[44]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "神使援护"
        assert it["name_en"] == "Archon Diversion"
        assert it["feat_type"] == ["战斗"]
        text = item_text(it)
        assert "先决条件" in text and "好处" in text

    def test_seed_45_hash_title_cn_en(self):
        """[45] M11b 井号标题中文+英文：『## 中文 English』（FC-Hb）"""
        items = run(SEEDS[45]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "先祖的蔑视"
        assert it["name_en"] == "Ancestral Scorn"
        assert it["feat_type"] == []

    def test_seed_46_paren_title_italic_glue(self):
        """[46] M13a 星内括号闭合星后斜体正文粘连：『**中文（English）***正文*』（FC-G）"""
        items = run(SEEDS[46]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "领导力"
        assert it["name_en"] == "Leadership"
        assert "你是他人追随的对象" in item_text(it)

    def test_seed_47_cn_en_bold_glue_body(self):
        """[47] M13b 星内中文+大写英文闭合星后正文粘连：『**中文 EN**正文』（FC-3）"""
        items = run(SEEDS[47]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "身体制御"
        assert it["name_en"] == "BODY CONTROL"
        assert "先决条件" in item_text(it)

    def test_seed_48_body_emphasis_no_split_negative(self):
        """[48] M13 反例：正文内强调加粗（**必须**）不拆行、不丢字"""
        items = run(SEEDS[48]["raw_snippet"])
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        text = item_text(items[0])
        assert "必须" in text and "达到7级" in text

    def test_seed_49_m6_prose_fragment_negative(self):
        """[49] R5 扩展 M6 正文句伪标题：『中文English长尾缀』整行正文（page_1564
        『当你使用元素拳APG攻击造成寒冷伤害时…』）不产条目；真条目标题行尾缀
        仅短词（seed 42 伟业 2 字），尾缀>8字是正文描述续接"""
        assert run(SEEDS[49]["raw_snippet"]) == []

    def test_seed_50_path_a_paren_prose_negative(self):
        """[50] R5 路径A 括号形态正文句（page_1367『你向法术注入了来自骨园
        （Boneyard）…』）：句首引导『你向』+尾虚词判定，`中文（English）正文`
        散文句不包裹为 elided 伪条目"""
        assert run(SEEDS[50]["raw_snippet"]) == []

    def test_seed_51_star_prose_negative(self):
        """[51] R5 星形散文句（page_553『****标注星号专长为战斗专长。******』）：
        句号收尾的星内散文去星留正文，不冒充标题"""
        assert run(SEEDS[51]["raw_snippet"]) == []

    def test_seed_52_underwater_crossline_multiword_positive(self):
        """[52] R5 恢复回归点：水下冒险AA 跨行英文+同行描述（『深呼吸Deep \\nbreath
        你屏住…』）是真条目，多词 Title Case 英文长尾缀必须包裹（seed 49 反例的
        对立面：尾缀>8 但英文为多词专有名词 = 合法条目同行描述）"""
        items = run(SEEDS[52]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "深呼吸"
        assert it["name_en"] == "Deep breath"
        assert it["format_cluster"] == "elided"

    def test_seed_53_single_word_region_prose_negative(self):
        """[53] R5 M6 单字专名散文引言（EMH『卡塔佩什Katapesh卡塔佩什的峡谷…』）：
        英文单字（无空格）非条目名，长尾缀触发碎片守卫不包裹；多词限制保住
        真条目（seed 52）而拒地区引言"""
        assert run(SEEDS[53]["raw_snippet"]) == []

    def test_seed_54_path_b_cnparen_prose_negative(self):
        """[54] R5 路径B（中文English+中文类型括号，`_RE_BARE_CN_EN_CNPAREN`）正文句
        （page_856『该生物的CR（该CR要基于这个生物的种族…）』）：中文名『该生物的』
        以尾虚词『的』结尾是断行悬挂，B 分支不包裹为 elided 伪条目（seed 50 是路径A，
        本种子覆盖路径B 守卫缺口）"""
        assert run(SEEDS[54]["raw_snippet"]) == []

    def test_seed_55_full_star_line_prose_negative(self):
        """[55] R5 整行星号散文（page_321『******当你使用一件穿刺或挥砍武器攻击时，
        你得意于对手血如泉涌的窘境*********』）：6+9 星包裹散文句，句首引导『当你』。
        四星归一若只剥 4 星会残留星号重组为 `**...**` 标题，须整行剥离星号留正文"""
        assert run(SEEDS[55]["raw_snippet"]) == []

    def test_seed_56_particle_ji_legit_positive(self):
        """[56] R5 粒子表移除『计』：『灵狐计（Kitsune Tricks）』是合法专长（专长名词
        后缀，非断行悬挂虚词），计结尾的 M6 行必须包裹；『此为一个或一群合计』等散文
        由句首引导『此为一个』兜住，不依赖计粒子"""
        items = run(SEEDS[56]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "灵狐计"
        assert it["name_en"] == "Kitsune Tricks"
        assert it["format_cluster"] == "elided"

    def test_seed_57_img_marker_inline_pfs_positive(self):
        """[57] R9 img_marker 图片标记放行（format_clusters 规范 §一 #4）：PFS 图标
        URL 与条目名同行内联（专长28 酒后真言『...SymbolN.gif**酒后真言（Truth in
        Wine）**』），图片标记剥离后仍是条目 → format_cluster=img_marker +
        pfs_eligible=true。判别键是同行内联前缀：seed_00 图片独立行 → standard，
        本种子同行前缀 → img_marker（同行图片前缀在 split 消费 [[PFS]] 时携带）"""
        items = run(SEEDS[57]["raw_snippet"])
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "酒后真言"
        assert it["name_en"] == "Truth in Wine"
        assert it["format_cluster"] == "img_marker"
        assert it["pfs_eligible"] is True


# ---- P0b：行首裸标签包裹（`先决条件：值` → `**先决条件：**值`）----
# 根因：parse_fields 只认 **标签[：:]** 形态；源数据大量条目字段标签无加粗
# （专长44 缩进半角冒号、专长9 值内嵌加粗跨行）→ prerequisites=null 高发
# （抽查 22 文件 fields_ok=false 中 14 例为此根因）。

from vectorizer.processors.feat import parse_fields  # noqa: E402


def _norm(raw: str) -> str:
    fmt = FeatFormat()
    return fmt.promote(fmt.normalize(raw))


class TestBareFieldLabelWrapping:
    """行首裸标签包裹为 **标签：** 后 parse_fields 可抽取"""

    def test_bare_labels_with_indent_and_halfwidth_colon(self):
        """专长44 形态：2 空格缩进 + 半角冒号 + 完全裸标签"""
        raw = (
            "  **羊首狮身之角（Horn of the Criosphinx, 战斗）**：\n"
            "  先决条件：BAB+6或武僧等级6\n"
            "  效果：你在攻击检定上获得+2加值。\n"
            "  正常：无。\n"
            "  特殊：无法与其他专长叠加。\n"
        )
        f = parse_fields(_norm(raw))
        assert f.get("prerequisites") == "BAB+6或武僧等级6"
        assert f.get("benefit") == "你在攻击检定上获得+2加值"
        assert f.get("normal") == "无"
        assert f.get("special") == "无法与其他专长叠加"

    def test_bare_label_value_with_inline_bold_crossline(self):
        """专长9 形态：值内嵌加粗 + 跨行（rstrip 后值完整）"""
        raw = (
            "**受控图纹（Controlled Patterns）**\n"
            "先决条件：**图纹讯息，法术专攻（幻术），施法者等级\n"
            "7**\n"
            "效果：你可以调整图纹。\n"
        )
        f = parse_fields(_norm(raw))
        assert "图纹讯息" in f.get("prerequisites", "")
        assert "施法者等级\n7" in f.get("prerequisites", "")
        assert f.get("benefit") == "你可以调整图纹"

    def test_bare_label_only_line_then_value_nextline(self):
        """空标签行 + 值在下一行（`先决条件：\n敏捷 13`）"""
        t = _norm("先决条件：\n敏捷 13\n")
        assert "**先决条件：**" in t

    def test_already_bold_label_idempotent(self):
        """已带星标签不二次包裹"""
        t = _norm("**先决条件：**力量 13\n")
        assert t.count("**先决条件：**") == 1

    def test_quote_block_line_not_wrapped(self):
        """引用块行（`> 来源：…`）不包裹"""
        t = _norm("> 来源：格拉里昂的诸神（Deities of Golarion）DoG\n")
        assert "> 来源：" in t

    def test_table_row_not_wrapped(self):
        """表格行（`| 先决条件：… |`）不包裹"""
        t = _norm("| 先决条件：BAB+6 | 效果：+2 |\n")
        assert "**先决条件：**" not in t

    def test_no_colon_not_wrapped(self):
        """无冒号的标签词行不包裹"""
        t = _norm("先决条件 BAB+6\n")
        assert t == "先决条件 BAB+6\n"

    def test_inline_label_not_wrapped(self):
        """句中（非行首）标签词不包裹"""
        t = _norm("此专长需要先决条件：敏捷 15，否则无效。\n")
        assert "**先决条件：**" not in t

    def test_condition_alias_added(self):
        """专长43 方言「条件：」→ prerequisites（非标准标签扩展）"""
        raw = (
            "**天堂升华（Talmandor's Lifting）**\n"
            "条件：信仰天堂之主\n"
            "效果：你获得天堂祝福。\n"
        )
        f = parse_fields(_norm(raw))
        assert f.get("prerequisites") == "信仰天堂之主"

    def test_condition_alias_added(self):
        """专长43 方言「条件：」→ prerequisites（非标准标签扩展）"""
        raw = (
            "**天堂升华（Talmandor's Lifting）**\n"
            "条件：信仰天堂之主\n"
            "效果：你获得天堂祝福。\n"
        )
        f = parse_fields(_norm(raw))
        assert f.get("prerequisites") == "信仰天堂之主"

    def test_period_separated_label(self):
        """专长12 形态：句号分隔（`先决条件。位面训导*，…`）→ 转冒号包裹"""
        raw = (
            "**位面训导（Planar Mentor）**\n"
            "先决条件。位面训导*，角色等级7级。\n"
            "效果：获得位面联系。\n"
        )
        f = parse_fields(_norm(raw))
        assert f.get("prerequisites") == "位面训导*，角色等级7级"
        assert f.get("benefit") == "获得位面联系"

    def test_colon_with_space_after(self):
        """专长17 形态：冒号后带空格（全库 107 处）"""
        raw = (
            "**德鲁伊语破译者（Druidic Decoder）**\n"
            "先决条件： 1级语言学，不是德鲁伊\n"
            "效果：你破解德鲁伊语。\n"
        )
        f = parse_fields(_norm(raw))
        assert f.get("prerequisites") == "1级语言学，不是德鲁伊"
        assert f.get("benefit") == "你破解德鲁伊语"

    def test_compound_label_fullwidth_indent(self):
        """专长34 形态：「前置需求」复合词 + 全角空格缩进"""
        raw = (
            "**剧毒咬撃（Noxious Bite）**\n"
            "　　前置需求：强酸吐息武器，啃咬攻击。\n"
            "效果：你的咬击附带剧毒。\n"
        )
        f = parse_fields(_norm(raw))
        assert f.get("prerequisites") == "强酸吐息武器，啃咬攻击"
        assert f.get("benefit") == "你的咬击附带剧毒"

    def test_special_status_halfwidth_colon_inline(self):
        """page_1564 形态：`**特殊状况：** 值`（半角冒号星内 + 同行值）→ special"""
        raw = (
            "**魔鬼之型（Diabolic Style）（战斗，流派）**\n"
            "**先决条件：**战斗反射。\n"
            "**专长效果：**在使用该风格时你可以进行徒手打击。\n"
            "**特殊状况：**一个6级以上的武僧可以选择*要害打击*作为武僧奖励专长。\n"
        )
        f = parse_fields(_norm(raw))
        assert f.get("special") == "一个6级以上的武僧可以选择*要害打击*作为武僧奖励专长"

    def test_special_status_colon_outside(self):
        """page_1014 形态：`**特殊状况**：值`（冒号在闭合星外）→ special"""
        raw = (
            "**改造武器专攻（Weapon Adept）**\n"
            "**专长效果**：选择一种武器改造。\n"
            "**通常状况**：改造后的武器使用难度往上提一阶。\n"
            "**特殊状况**：你可以多次选择本专长。\n"
        )
        f = parse_fields(_norm(raw))
        assert f.get("special") == "你可以多次选择本专长"


# ---- P0a：跨行英文名合并缺口（中文/引号前换行）----
# _RE_CROSS_EN 原只合并「字母紧邻换行」：`指引 \nCelestial`（中文前换行）
# 与 `Caster’s \nChampion`（右单引号）漏掉 → 标题跨行不识别。

class TestCrossLineEnMergeExtensions:
    def test_cn_char_before_newline_en(self):
        """繁星子民形态：`**天体指引 \nCelestial Guidance**` → FC-3 可识别"""
        raw = (
            "**占星时机 AstrologicaL timing**\n正文1\n\n"
            "**天体指引 \nCelestial Guidance**\n正文2\n"
        )
        items = run(raw)
        titles = [it["name"] for it in items]
        assert "天体指引" in titles, f"天体指引未识别为标题，实际: {titles}"
        it = next(i for i in items if i["name"] == "天体指引")
        assert it["name_en"] == "Celestial Guidance"
        assert "正文2" in item_text(it)

    def test_quotes_apostrophe_before_newline_en(self):
        """专长49 形态：`Caster’s \nChampion`（右单引号 + 换行）"""
        raw = "**术师先锋（Caster’s \nChampion）[战斗]**\n正文\n"
        items = run(raw)
        assert len(items) == 1, f"实际 {len(items)}"
        assert items[0]["name"] == "术师先锋"
        assert "Champion" in items[0]["name_en"]
        assert items[0]["feat_type"] == ["战斗"]


# ---- P0a：裸/星外中文类型括号标题（专长57 秘语、专长13 违和感）----
# `秘语（团队专长）` / `**违和感**（动物伙伴专长)` ——无星或星外中文类型
# 括号（非英文名）→ 包裹为 **中文（类型）** 走 FC-1n（_split_paren_content
# 纯中文段 → 类型标签）。守卫 = 括号内容命中 normalize 类型词集，正文碎片
# 行（`震慑1轮（强韧）`）不误包（全库 1567 裸括号行中仅 8 处命中，全真实标题）。

class TestBareCnTypeParenTitle:
    def test_bare_cn_type_paren_title(self):
        """专长57 形态：完全裸标题 + 中文类型括号（团队专长）"""
        raw = (
            "秘语（团队专长）\n\n"
            "你与同伴早已约定一套复杂的暗号。\n"
            "先决条件：唬骗1级\n"
            "效果：传递暗号时获得加值。\n\n"
            "培育植物生物（物品制造）\n\n"
            "通过细心研究，你学会了栽培植物。\n"
        )
        items = run(raw)
        titles = [it["name"] for it in items]
        assert "秘语" in titles, f"实际: {titles}"
        assert "培育植物生物" in titles
        it = next(i for i in items if i["name"] == "秘语")
        assert "团队" in it["feat_type"]
        assert "暗号" in item_text(it)

    def test_star_outside_cn_type_paren_title(self):
        """专长13 形态：闭合星 + 星外中文类型括号"""
        raw = (
            "**违和感**（动物伙伴专长)\n"
            "所有魔宠都不只是它们看起来的那样。\n"
            "前提：魔宠职业能力\n"
            "效果：你的魔宠可以说一种语言。\n\n"
            "**无定型魔宠**（动物伙伴专长)\n"
            "魔宠拥有多种物理形态。\n"
        )
        items = run(raw)
        titles = [it["name"] for it in items]
        assert "违和感" in titles, f"实际: {titles}"
        assert "无定型魔宠" in titles
        it = next(i for i in items if i["name"] == "违和感")
        assert "魔宠" in item_text(it)

    def test_body_fragment_not_wrapped(self):
        """正文碎片行（`震慑1轮（强韧）`）不误包"""
        raw = "震慑1轮（强韧）\n纠缠1d4+1轮（反射）\n"
        assert run(raw) == []


class TestTitleTypeEnWithParens:
    """FC-4 提前修复（P0a：page_820 英文名带括号形态）。

    `**中文（类型）EN (EN_TYPE)**`（人多胆壮（团队专长）COURAGE IN
    NUMBERS (TEAMWORK)）曾被 _RE_TITLE（FC-1n）嵌套括号回溯吞进 name，
    类型不进 feat_type。FC-4 提前后：name 拆净 / feat_type 正确 /
    name_en 完整保留尾括号。
    """

    def test_cn_type_en_with_paren_split_clean(self):
        """page_820 形态：类型括号 + 英文名带括号"""
        items = run("**人多胆壮（团队专长）COURAGE IN NUMBERS (TEAMWORK)**\n\n正文")
        assert len(items) == 1
        assert items[0]["name"] == "人多胆壮"
        assert items[0]["feat_type"] == ["团队"]
        assert items[0]["name_en"] == "COURAGE IN NUMBERS (TEAMWORK)"

    def test_cn_type_en_double_types(self):
        """双类型顿号 + 英文名双括号（压制 OVERWHELM）"""
        items = run("**压制（战斗专长，团队专长）OVERWHELM (COMBAT, TEAMWORK)**\n\n正文")
        assert items[0]["name"] == "压制"
        assert items[0]["feat_type"] == ["战斗", "团队"]
        assert items[0]["name_en"] == "OVERWHELM (COMBAT, TEAMWORK)"

    def test_pure_cn_type_paren_not_preempted(self):
        """FC-4 提前不抢占 FC-1n 纯中文类型括号（专长57 秘语形态）"""
        items = run("**秘语（团队专长）**\n\n正文")
        assert items[0]["name"] == "秘语"
        assert items[0]["feat_type"] == ["团队"]

    def test_pure_en_paren_not_preempted(self):
        """FC-4 提前不抢占 FC-1n 纯英文括号（**中文（English）** 经典形态）"""
        items = run("**铁拳（Iron Fist）**\n\n正文")
        assert items[0]["name"] == "铁拳"
        assert items[0]["name_en"] == "Iron Fist"

    def test_cn_type_paren_en_paren_nested_en(self):
        """FC-1r 双括号 + 英文名内嵌别名括号（魔宠手记FF 团队传递接触法术型）

        `**中文（类型）（EN (EN_TYPE)）**`：EN 部分含半角括号
        （Group Deliver Touch Spells (Teamwork)），原 EN `[^）)]*` 在半角
        `)` 处截断导致 FC-1r 失败、FC-1n 回溯把类型括号吞进 name。
        """
        items = run("**团队传递接触法术（团队专长）（Group Deliver Touch Spells (Teamwork)）**\n\n正文")
        assert items[0]["name"] == "团队传递接触法术"
        assert items[0]["feat_type"] == ["团队"]
        assert items[0]["name_en"] == "Group Deliver Touch Spells (Teamwork)"


class TestP1bPseudotitleFixes:
    """P1b 伪标题碎片治理（2026-08-02）

    源数据 RE2 残留两种断裂形态：
      1. 译者行双段加粗拼接 `**译者：X，****Y**`（page_198/200/201/203）——
         形态归一产出 `**译者（：X，）**` 被 _RE_TITLE 当条目标题；
      2. 条目标题断裂 `中文****` + `**English`（page_276 怪物坐骑/精通
         怪物坐骑/枪械亲熟）——标题识别失败，正文并入前一个引导 chunk。
    修复：base.py 译者剥离正则放宽（段间 `****` 形态）+ 源数据 3 处标题
    归一。本类为回归防护测试。
    """

    def _names(self, raw: str) -> list:
        return [i["name"] for i in run(raw)]

    def test_translator_bold_broken_joined(self):
        """`**译者：X，****Y**` 双段拼接断裂 → 不产「译者」条目（page_200 形态）"""
        assert "译者" not in self._names(
            "**译者：傻豆，****Falengel**\n\n**《极限魔法》专长（Ultimate Magic Feats）**\n正文"
        )

    def test_translator_bold_broken_cn_only(self):
        """`**译者：****X**` 双段拼接断裂（无逗号）→ 不产「译者」条目（page_203 形态）"""
        assert "译者" not in self._names(
            "**译者：****傻豆**\n\n**《极限魔法》专长（Ultimate Magic Feats）**\n正文"
        )

    def test_translator_bold_joined_keeps_broken_tail(self):
        """译者行尾 `**` 漂移（`**译者：X，****Y` 无闭合）→ 不产「译者」条目（page_198 形态）"""
        assert "译者" not in self._names(
            "**译者：他化自在天，****PATIBAUL**\n\n**《极限魔法》专长（Ultimate Magic Feats）**\n正文"
        )

    def test_mount_feat_standard_title(self):
        """`**怪物坐骑（Monstrous Mount）**` 标准形态 → 独立条目（page_276 修复目标）"""
        items = run("**怪物坐骑（Monstrous Mount）**\n*你学会了如何驯服并骑乘那些奇特猛兽的技巧。*\n\n**先决条件**：驯养动物4级\n")
        assert items[0]["name"] == "怪物坐骑"
        assert items[0]["name_en"] == "Monstrous Mount"


class TestPage321TitleForms:
    """page_321/page_500 标题断裂与字段标签 4星漂移归一形态回归防护（2026-08-02）

    源数据 RE2 星号漂移家族（与 page_276 怪物坐骑同根因）：
      F1 跨行：`中文**** \r` + 下行裸英文名 → 归一 `**中文（English）**`（FC-1n）
      F2 同行：`中文**** English` → 归一 `**中文（English）**`
      F2b    ：`中文**** English****（类型）****` → 归一 `**中文（EN）（类型）**`（FC-1q）
      R6 字段标签：`**先决条件****：**` → 归一 `**先决条件：**`
    归一形态均须被解析器识别为标准条目（防伪条目「先决条」与标题丢失回归）。
    """

    def _names(self, raw: str) -> list:
        return [i["name"] for i in run(raw)]

    def test_f1_merged_title(self):
        """F1 归一 `**崩坏灵光（Aura of Succumbing）**` → 独立条目（page_321）"""
        items = run("**崩坏灵光（Aura of Succumbing）**\n*****  ******你的邪恶主宰赋予你为万物带来死亡的大能*********\n\n**先决条件：**引导能量职业能力\n")
        assert items[0]["name"] == "崩坏灵光"
        assert items[0]["name_en"] == "Aura of Succumbing"
        assert items[0]["format_cluster"] in ("elided", "standard")

    def test_f2_inline_title(self):
        """F2 归一 `**残酷（Cruelty）**` 同行形态 → 独立条目（page_321）"""
        items = run("**残酷（Cruelty）**\n*****  ******目睹他人的苦痛使你变得更为残暴*********\n\n**先决条件：**邪恶阵营\n")
        assert items[0]["name"] == "残酷"
        assert items[0]["name_en"] == "Cruelty"

    def test_f2b_title_with_type(self):
        """F2b 归一 `**酩酊侠（Durnken Brawler）（战斗专长）**` → 类型解析（FC-1q）"""
        items = run("**酩酊侠（Durnken Brawler）（战斗专长）**\n**先决条件：**坚忍\n**专长效果：**当你在饮用麦酒后\n")
        assert items[0]["name"] == "酩酊侠"
        assert items[0]["name_en"] == "Durnken Brawler"
        assert items[0]["feat_type"] == ["战斗"]

    def test_r6_field_label_quad_star(self):
        """R6 归一 `**先决条件****：**` → `**先决条件：**` 并入条目，不产「先决条」伪条目"""
        items = run(
            "**强能巫术（Amplified Hex）**\n"
            "**先决条件：**巫术职业能力**专长效果：**你可以将法术位消耗掉从而强化巫术\n"
        )
        names = [i["name"] for i in items]
        assert "先决条" not in names and "专长效" not in names
        assert "强能巫术" in names
        feat = next(i for i in items if i["name"] == "强能巫术")
        assert "先决条件" in feat["text"] and "专长效果" in feat["text"]

    def test_r6_field_label_bare_star(self):
        """`**先决条件****：擅长投石索。**`（标签后直接内容）→ 并入条目不产伪条目（page_509 形态）"""
        items = run("**杖式投石索（Slings）**\n**先决条件：擅长投石索。**\n**专长效果：**你使用投石索攻击\n")
        names = [i["name"] for i in items]
        assert "先决条" not in names
        assert any(i["name"] == "杖式投石索" for i in items)

    def test_r5_merged_en_segments(self):
        """R5 归一 `**兽魂图腾（Totem Beast）**`（跨行英文拆段合并）→ 独立条目（page_500）"""
        items = run("**兽魂图腾（Totem Beast）**\n***你的动物伙伴和你所供奉的动物图腾产生了联系***\n")
        assert items[0]["name"] == "兽魂图腾"
        assert items[0]["name_en"] == "Totem Beast"


class TestBareParenProseGuards:
    """A 分支正文句/列表行守卫（2026-08-02 空 text chunk 调查）

    `_wrap_bare_paren_lines` 逐行包裹 `中文(English) 正文` 为 elided 标题，
    但三类合法非标题行穿透守卫被误包（产 elided 伪条目 + 原条目空 text）：
      1. 召唤列表行 `天界海豚(Celestial dolphin,NG)`——组2 英文以「,阵营缩写」
         结尾（纯洁勇士召唤善良怪物列表 27 行）
      2. 长散文正文行 `拉兹米尔（Razmir）谙熟将…骗术。`——组3 >30 字且句号
         结尾（page_277 章节引言、武术手册MAH 化形扭/化形势、武器大师 在塔尔多）
      3. 量词开头正文行 `一只豺化人（Jackalwere）蹲在你的家谱上。`——组1
         以「一只」开头（豺产正文，9 字短句句号结尾，阈值不覆盖）
    回归：短尾缀真标题（海滨后裔 11 字）维持包裹。
    """

    def _names(self, raw: str) -> list:
        return [i["name"] for i in run(raw)]

    def test_summon_list_row_not_wrapped(self):
        """守卫1：召唤列表行 `天界海豚(Celestial dolphin,NG)` 不包裹，留在正文"""
        items = run(
            "**新专长：召唤善良怪物（Summon good monster）**\n"
            "**条件：**善良阵营\n"
            "**效果：**当你施展召唤怪物，你能从善良怪物列表中选取要召唤的生物。\n"
            "善良怪物列表\n"
            "1级天界狗(Celestial dog,NG)\n"
            "天界海豚(Celestial dolphin,NG)\n"
            "天界鹰(Celestial eagle,NG)\n"
        )
        assert len(items) == 1, f"召唤列表行不产 elided 伪条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "新专长：召唤善良怪物"
        text = item_text(it)
        assert "天界海豚" in text and "天界鹰" in text, "列表行留在条目正文"

    def test_quantity_lead_prose_not_wrapped(self):
        """守卫3：量词开头正文行 `一只豺化人（Jackalwere）蹲在你的家谱上。` 不包裹"""
        items = run(
            "**豺产（Jackal Heritage）**\n"
            "一只豺化人（Jackalwere）蹲在你的家谱上。\n"
            "**先决条件：**人类，只能在1级获取\n"
        )
        assert len(items) == 1, f"豺产正文行不产 elided 伪条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "豺产"
        text = item_text(it)
        assert "一只豺化人" in text and "先决条件" in text, "正文行留在条目正文"

    def test_long_prose_trailer_not_wrapped(self):
        """守卫2：长散文正文行 `拉兹米尔（Razmir）谙熟将…`（>30字句号结尾）不包裹"""
        items = run(
            "**虚假神术（False Divine Magic）**\n"
            "拉兹米尔（Razmir）谙熟将强大的奥术与圆滑的谎言结合使用的技巧，"
            "并以此登上信仰的尖塔顶端。多年以来，拉兹米尔发展并完善了"
            "一种新形式的奥术——虚假神术。\n"
        )
        assert len(items) == 1, f"长散文行不产 elided 伪条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "虚假神术"
        assert "拉兹米尔" in item_text(it), "散文行留在条目正文"

    def test_short_trailer_title_still_wrapped(self):
        """回归：短尾缀章节标题 `海滨后裔（Shoreborn）半精灵可获得以下专长。`
        （11 字句号结尾）维持包裹（现状不回归）"""
        items = run(
            "海洋馈赠（Gifts from the Sea）\n"
            "海滨后裔（Shoreborn）半精灵可获得以下专长。\n"
        )
        names = [i["name"] for i in items]
        assert "海洋馈赠" in names and "海滨后裔" in names, "短尾缀标题仍产条目"
        assert all(i["format_cluster"] == "elided" for i in items)

    def test_summon_good_monster_normalized_title(self):
        """召唤善良怪物标题归一后产出完整条目（源数据补星后的形态）"""
        items = run(
            "**新专长：召唤善良怪物（Summon good monster）**\n"
            "**条件：**善良阵营\n"
            "**效果：**当你施展召唤怪物，你能从善良怪物列表中选取要召唤的生物。\n"
        )
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "新专长：召唤善良怪物"
        assert it["name_en"] == "Summon good monster"
        assert "条件" in item_text(it) and "效果" in item_text(it)


class TestQuadStarGlueFamily:
    """4 星粘连家族（KN070）：`中文（****EN****，类型）****正文` 源数据形态 → 标准条目。

    源数据（page_515.html 转换产物）：`<B>中文（</B><B>EN</B><B>，类型）</B><SPAN>正文`
    三连加粗段 → markdown `（****EN****）****正文` 嵌套星 + 4 星粘连。
    脚本 _RE_QUAD_STAR/_RE_NESTED_STAR（seed 06）只覆盖「行首星 + `）**` 闭合」
    变体；「`）****正文` 4 星粘连」「行首无星嵌套」「星外类型括号」变体漏网 →
    D 分支双括号 / A 分支组2 吞星 → split 不识别 → 条目丢失（纯洁勇士 5 条）。
    """

    def test_golden_legion_quad_star_glue(self):
        """A 型行首 2 星：`**中文（****EN****）****正文` → 标准条目"""
        items = run(
            "**黄金军团的不杀之刃（****Golden Legion’s Stayed Blade****）****"
            "当你面对庞大而神秘的组织时，死掉的敌人不过是具尸体，而活捉的敌人则是可用的工具\n"
            "条件：**BAB +3**效果：**如果你造成了能杀死目标的伤害，你能选择只造成"
            "刚好使其HP到达-1并且稳定伤势的伤害。**\n"
        )
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "黄金军团的不杀之刃"
        assert it["name_en"] == "Golden Legion’s Stayed Blade"
        assert "当你面对" in item_text(it) and "条件" in item_text(it)

    def test_lastwall_phalanx_no_lead_star(self):
        """B 型行首无星 + 星外中文类型：`中文（****EN****，团队专长）****正文`"""
        items = run(
            "终焉之墙方阵（****Lastwall Phalanx****，团队专长）****"
            "当对抗Belkzen恐怖的大军时，你从并肩的兄弟姐妹身上获得力量\n"
            "条件：**BAB +3，善良阵营**效果：**在对抗邪恶生物攻击的AC和对抗邪恶生物"
            "法术和效果的豁免上，获得等同拥有此专长的相邻战友数量的神圣加值。**\n"
        )
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "终焉之墙方阵"
        assert "Lastwall" in it["name_en"]
        assert "对抗邪恶生物" in item_text(it)

    def test_siphon_poison_no_lead_star(self):
        """B 型行首无星：`中文（****EN****）****正文` → 标准条目"""
        items = run(
            "吮毒（****Siphon Poison****）****你可以从其他生物身上吸走毒素。\n"
            "效果：**以一个全轮动作，如果成功通过医疗技能鉴定，你可以将伤口型毒素"
            "一个无助或自愿生物的血中去除。**\n"
        )
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "吮毒"
        assert "医疗技能鉴定" in item_text(it)

    def test_summon_good_monster_raw_glue(self):
        """源数据原始形态（4 星嵌套 + 字段粘连）→ 归一后走标准标题"""
        items = run(
            "**新专长：召唤善良怪物（****Summon good monster****）****条件**：善良阵营"
            "**效果**：当你施展召唤怪物，你能从善良怪物列表中选取要召唤的生物。"
            "你的正义信念给予这些召唤生物顽强专长。**\n"
        )
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "新专长：召唤善良怪物"
        assert it["name_en"] == "Summon good monster"
        assert "善良怪物列表" in item_text(it) and "顽强专长" in item_text(it)

    def test_virtuous_creed_outer_type_paren(self):
        """星外类型括号：`中文**EN**（专长）****正文`（EN 无星内括号、星外类型）"""
        items = run(
            "美德信条****Virtuous creed****（专长）****该信条在你向善的命运中指引着你。\n"
            "前提条件：你必须是善良阵营。\n"
            "效果：在下列美德中选择一个。你必须遵守该美德的信条，并得到相应奖励。\n"
        )
        assert len(items) == 1, f"应产 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "美德信条"
        assert "Virtuous" in it["name_en"]
        assert "前提条件" in item_text(it)

    # ---------- 回归：既有形态不受影响 ----------

    def test_regression_seed06_brewmaster_six_star(self):
        """seed 06：`**酿造大师（****Brewmaster****）******` 6 星收尾形态不变"""
        items = run(
            "**酿造大师（****Brewmaster****）******\n"
            "**先决条件：**酿造师等级1级\n"
            "**效果：**你酿造的饮品效果更佳。\n"
        )
        assert len(items) == 1
        assert items[0]["name"] == "酿造大师"

    def test_regression_elided_inline_desc_fullwidth_space(self):
        """E 分支：`**中文（EN）****　　*描述*` 全角空格形态不被新规则拆行"""
        items = run(
            "**激励指挥官（Inspirational Commander）****　　*出自Quests and Campaigns*\n"
            "**先决条件：**领导力\n"
            "**效果：**你的指挥艺术鼓舞人心。\n"
        )
        assert len(items) >= 1
        names = [i["name"] for i in items]
        assert "激励指挥官" in names

    def test_regression_branch_d_no_paren(self):
        """D 分支：`**中文 English*****正文`（EN 无括号）仍走 elided"""
        items = run(
            "**魔法鱼叉 Magic Harpoon*****你投掷的鱼叉附带魔法之力。\n"
        )
        assert len(items) == 1
        assert items[0]["format_cluster"] == "elided"

    def test_regression_halfparen_no_break(self):
        """seed 11：`）****(Combat,` 半角括号截断形态不被新规则误拆行破坏"""
        items = run(
            "**上下合围（战斗，团队）****(Combat, Teamwork)\n"
        )
        assert len(items) == 1

    def test_weapon_trick_fullwidth_paren_glue(self):
        """武器技法段：`**EN****（类型）**` 4 星粘连子条目不破坏类别标题切分。

        武器大师手册技法形态：跨行英文名 + `**Mindful Dodge****（闪避）**：
        正文`（4 星前是英文名，非 `）`/`)` 截断；无成对四星，`_fix_quadruple_star`
        不消费）。e80ec0e 的 halfparen 守卫（race page_160 援护防御修复）
        误伤此形态——守卫只认 `）****(` 截断，子条目 4 星不拆行 → 半残星壳
        行 `**Mindful Dodge****（闪避）**` 不匹配任何标题/跳过正则、吞进当前
        条目 text → 前置 `[[fc:elided]]` 拆行泄漏链断裂 → 类别标题「长武器
        技法」失去 elided 标记 → standard + text>150 无字段被「子节标题排除」
        弹掉（6 技法 P1 回归：长武器技法/远程武器技法/双手武器技法/双武器
        技法/盾武双持技法/种族武器大师，武器大师手册_专长 116→110）。
        """
        raw = (
            # 前置子条目：跨行英文名 + 无成对四星粘连——guard=False 拆行产
            # `[[fc:elided]]**Mindful Dodge**` 前缀行 → 子条目行被跳过时标记
            # 泄漏到下一类别标题（真实文件同机制，武器大师手册_专长 698 行）
            "**Mindful \n"
            "Dodge****（闪避）**：以直觉动作（immediate action），你在对抗自身意识到的"
            "单次攻击时，AC会获得+4闪避加值。你必须在攻击检定结果被揭示之前作出是否"
            "使用该技法的决定。你的下个回合会陷入恍惚（staggered）。\n"
            "·         \n"
            "**长武器技法**\n"
            "*Polearm Tricks*\n"
            "迦伦德（Garund）南部以及阿卡迪亚（Arcadia）大陆艾欧巴瑞亚（Iobaria）"
            "地区的武者通常会使用这些武器技法。你只有在持用一把属于长兵器武器组"
            "（polearm weapon group）的武器时才能使用这些技法。\n"
        )
        items = run(raw)
        names = [it["name"] for it in items]
        assert "长武器技法" in names, f"类别标题应切出独立条目：{names}"
        # 类别标题保留依赖前置 elided 标记泄漏——cluster=elided 是拆行生效的
        # 直接证据（guard=True 时无拆行无泄漏 → standard → 被子节排除弹掉）
        it = next(x for x in items if x["name"] == "长武器技法")
        assert it.get("format_cluster") == "elided", (
            f"类别标题应带 elided 标记（前置子条目拆行泄漏），"
            f"实际 {it.get('format_cluster')}"
        )


class TestBareParenListContinuationGuard:
    """A 分支守卫扩展（KN070 补）：组3 以逗号开头的行 = 列表续行，不包裹为标题。

    纯洁勇士 L14 `爱与和平（Euphoric Tranquility），和谐术（Serenity）**` 是
    和平缔造者效果文本的跨行法术列表续行（L13 效果列举法术以 `，` 结尾），
    A 分支误包为独立 elided 伪条目（17 字）；任务与战役 L210
    `静思者（Scholar of the Great Beyond）, 漫游者（Wanderlust）` 同族
    （专长名列表续行）。真实条目标题正文不从逗号开始。
    """

    def test_list_continuation_not_wrapped(self):
        """`中文（EN），后续列表项` 行不产独立条目"""
        items = run(
            "**和平缔造者（Peacemaker）**\n"
            "**效果：**造成和平效果和使攻击性生物变得平和的法术DC+2。"
            "包括并不限于：圣域术（sanctuary），平静动物（calm animals），"
            "战友情深（Compassionate Ally），注目术（Enthrall），\n"
            "爱与和平（Euphoric Tranquility），和谐术（Serenity）**\n"
        )
        names = [i["name"] for i in items]
        assert "和平缔造者" in names, "主条目应产出"
        assert "爱与和平" not in names, "列表续行不得误包为独立条目"
        assert "和谐术" in item_text(items[0]), "列表续行内容并入主条目 text"

    def test_halfwidth_comma_list_not_wrapped(self):
        """半角逗号列表续行：`中文（EN）, 后续` 不产独立条目"""
        items = run(
            "**战斗风格（Combat Style）**\n"
            "**效果：**你可以选择下列风格流派。\n"
            "静思者（Scholar of the Great Beyond）, 漫游者（Wanderlust）\n"
        )
        names = [i["name"] for i in items]
        assert "战斗风格" in names
        assert "静思者" not in names, "半角逗号列表续行不得误包"


class TestYiYouAnnotation:
    """「又译」注记标题（`**中文（EN，又译别译）**`）——又译段是翻译注记非类型"""

    def test_38_yiyou_annotation_title_split(self):
        """狂暴撞飞型：`**狂暴撞飞（Raging Throw，又译地狱极乐投）**` + 同行描述 + 字段
        → 独立条目，name_en 取英文段，feat_type 不含「又译…」注记"""
        items = run(
            "**狂暴撞飞（Raging Throw，又译地狱极乐投）**　　"
            "*你将部分狂怒用于把对手狠狠摔向其他敌人。*\n"
            "**先决条件**：力量13，体质13，【狂暴】职业特性，精通冲撞，猛力攻击，"
            "基本攻击加值+6。\n"
            "**专长效果**：当你在狂暴中尝试使用冲撞战技时，你能以迅捷动作消耗1轮"
            "每日狂暴轮数，来将体质修正添加到冲撞战技检定上。\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "狂暴撞飞"
        assert it["name_en"] == "Raging Throw"
        assert it["feat_type"] == [], f"又译注记不得进 feat_type：{it['feat_type']}"
        assert "你将部分狂怒" in item_text(it), "同行描述应保留在条目 text"
        assert "先决条件" in item_text(it), "字段应并入条目"

    def test_39_four_star_yiyou_annotation_split(self):
        """诈欺师型（4 星包裹英文）：`**诈欺师（****Deceitful****，又译欺诈）**`
        → 独立条目，feat_type 不含「又译欺诈」"""
        items = run(
            "**诈欺师（****Deceitful****，又译欺诈）**\n"
            "你能通过模仿别人的行为举止来欺骗或误导别人，以改善人际关系…\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "诈欺师"
        assert it["name_en"] == "Deceitful"
        assert it["feat_type"] == [], f"又译注记不得进 feat_type：{it['feat_type']}"

    def test_40_split_paren_content_strips_yiyou(self):
        """_split_paren_content 对「，又译…」段剥离（翻译注记非类型）"""
        assert F_split_paren("Raging Throw，又译地狱极乐投", split_feat_types) == (
            "Raging Throw",
            [],
        )
        assert F_split_paren("Deceitful，又译欺诈", split_feat_types) == ("Deceitful", [])
        # 真实类型与又译共存：类型保留、又译剥离
        assert F_split_paren("Barrage of Styles，战斗，团队", split_feat_types) == (
            "Barrage of Styles",
            ["战斗", "团队"],
        )


class TestMasterySeriesParen:
    """4 星粘连系列名括号标题（page_566 物品掌握专长族）——KN081 根因：
    `**中文**** EN(****系列名****)**` 半角括号内 4 星包裹形态未被
    _RE_ELIDED_QUAD 消费（其只吃全角括号 `（类型）`），_RE_QUAD_STAR 又把
    `**** EN(****` 配对剥星 → 残留 `(**系列名****)**` 使全部标题正则失配 →
    条目被并入前条目吞并（page_566 能力掌握/力场盾掌握/武器觉醒掌握 3 条目丢失）"""

    def test_41_mastery_series_title_split(self):
        """能力掌握型（无空格）：`**能力掌握**** ability Mastery(****物品掌握专长****)**`
        → 独立条目，name/name_en/feat_type 对齐复原掌握（feat_type=物品掌握）"""
        items = run(
            "**能力掌握**** ability Mastery(****物品掌握专长****)**\n"
            "*你能用变化系魔法物品增强你天生的能力。*\n"
            "**先决条件**：使用魔法装置技能3级，基础强韧豁免加值+4\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "能力掌握"
        assert it["name_en"] == "ability Mastery"
        assert it["feat_type"] == ["物品掌握"], f"系列名应进 feat_type：{it['feat_type']}"
        assert "你能用变化系魔法物品" in item_text(it), "描述应并入条目"
        assert "先决条件" in item_text(it), "字段应并入条目"

    def test_42_mastery_series_space_variant(self):
        """武器觉醒掌握型（英文后带空格）：`**武器觉醒掌握**** weapen evoker mastery (****…`
        → 独立条目（原书拼写 weapen 保留不纠错）"""
        items = run(
            "**武器觉醒掌握**** weapen evoker mastery (****物品掌握专长****)**\n"
            "*你用你魔法武器上的秘法能量折磨你的对手。*\n"
            "**先决条件**：使用魔法装置技能2级，基础强韧豁免加值+3\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "武器觉醒掌握"
        assert it["name_en"] == "weapen evoker mastery"

    def test_43_mastery_series_fourth_variant(self):
        """力场盾掌握型：`**力场盾掌握**** force shield mastery(****物品掌握专长****)**`"""
        items = run(
            "**力场盾掌握**** force shield mastery(****物品掌握专长****)**\n"
            "*你可以用防护系魔法物品创造力场屏障*\n"
            "**先决条件**：使用魔法装置技能3级，基础强韧豁免加值+3\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "力场盾掌握"
        assert it["name_en"] == "force shield mastery"

    def test_44_no_lead_star_prose_not_wrapped(self):
        """负测试：无星开头同行正文形态（MTT 文件正文脏内容）不得被误归一为标题/产条目"""
        raw = (
            "**Pfs：在决定物品掌握专长的先决条件与效果时，你只能选择你单一个职业的"
            "强韧豁免加值。 魔法物品掌握专长初出武器大师工具箱（果园已有翻译）  "
            "能力掌握 ability Mastery(****物品掌握专长) **你能用变化系魔法物品增强"
            "你天生的能力。\n"
        )
        text = FeatFormat().normalize(raw)
        assert "能力掌握（ability Mastery）〔物品掌握专长〕" not in text, \
            "正文形态不得被误归一为标题"
        items = FeatFormat().split_into_items(text, source_name="seed")
        assert all(i["name"] != "能力掌握" for i in items), "无行首星不得产条目"

    def test_45_fullwidth_restoration_kept(self):
        """负测试：复原掌握跨行全角形态保持原归一路径（新正则不得抢占 _RE_ELIDED_QUAD）"""
        text = FeatFormat().normalize(
            "**复原掌握**** restoration \nmastery****（物品掌握专长）******\n"
            "*你不仅仅能治疗肉体上的伤势。*\n"
        )
        assert "[[fc:elided]]**复原掌握（restoration mastery）〔物品掌握专长〕**" in text, \
            "跨行全角形态应保持 _RE_ELIDED_QUAD 归一产物"
        items = FeatFormat().split_into_items(text, source_name="seed")
        assert len(items) == 1 and items[0]["name"] == "复原掌握"


class TestBareTitleFieldCorroboration:
    """裸中文标题 + 字段标签佐证（page_744 数学魔法节）——KN082 根因：
    转换脚本把 `<BR>` 段落边界转成同行 → `**算术占卜**通过将文字…**先决条件：**…`
    整节挤一行，split 无标题可认 → 段落并入 cur=None 被丢弃（内容彻底丢失）。
    源数据按 HTML 段落边界拆行后，`**算术占卜**` 独立行 + 后续行含
    `**先决条件：**` 等字段标签 → FC-8n 佐证扩展（判别器 FC-8q「需字段标签
    佐证」同思路）识别为条目；章节标题（后跟纯段落无字段）保持跳过。"""

    def test_46_bare_title_field_corroboration(self):
        """算术占卜型（拆行后）：`**算术占卜**` 独立行 + 描述行 + `**先决条件：**` 字段行
        → 独立条目，描述与字段并入 text"""
        items = run(
            "**算术占卜**\n"
            "通过将文字转化为数学等式，你可以解开文字内隐藏的秘密，以此强化你的"
            "法术效应。\n"
            "**先决条件：**智力13，法术专攻（预言系），法术辨识3级\n"
            "**收益：**　　在施法前以一个迅捷动作，你可以尝试用算术占卜强化你的法术。\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "算术占卜"
        assert it["name_en"] == ""
        assert "通过将文字转化为数学等式" in item_text(it), "描述应并入条目"
        assert "先决条件" in item_text(it) and "收益" in item_text(it), "字段应并入条目"

    def test_47_section_header_no_field_kept_skipped(self):
        """负测试：裸中文短行标题后跟纯段落（无字段标签）→ 章节标题保持跳过（半鱼人专长型）"""
        items = run(
            "**半鱼人专长**\n"
            "本章节介绍了半鱼人相关的专长，通常与海洋环境和水下作战有关。\n"
            "半鱼人（Gillmen）是失落国度阿兹兰特（Azlant）的后裔。\n"
        )
        assert all(i["name"] != "半鱼人专长" for i in items), "章节标题不得产条目"

    def test_47b_section_header_before_subfeat_titles_skipped(self):
        """负测试：小节标题后跟子条目标题（子条目的字段在窗口内）→ 章节标题保持跳过
        （专长58 半鱼人专长型：`**半鱼人专长**` + `**异怪克星施法者（…）**` + 其字段——
        字段佐证必须先遇子条目标题终止，不得跨子条目误佐证）"""
        items = run(
            "**半鱼人专长**\n"
            "\n"
            "**异怪克星施法者（Aberration-Bane Caster）**\n"
            "\n"
            "**先决条件：** 施法者等级4级，半鱼人，宿敌（异怪）职业特性\n"
            "\n"
            "**底栖魔鱼欺诈者（Aboleth Deceiver）**\n"
        )
        assert all(i["name"] != "半鱼人专长" for i in items), "小节标题不得产条目"
        assert any(i["name"] == "异怪克星施法者" for i in items), "子条目应正常产出"

    def test_48_italic_desc_corroboration_kept(self):
        """负测试/回归：FC-8n 原佐证（后行单星 *描述*）保持工作（截肢型）"""
        items = run(
            "**截肢**\n"
            "*你已经截断了你的一根手指并治疗了伤口从而让它再也不能完全愈合。*\n"
            "**服从仪典**：操控你截断的手指的血痂、疤痕和开放的伤口\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "截肢"

    def test_49_prose_without_fields_kept_merged(self):
        """负测试：裸中文短行标题 + 后续普通段落（含「先决」词但非字段标签形态）
        → 不产条目（防正文误判）"""
        items = run(
            "**永罪契约**\n"
            "签订契约需要先决条件成立，但这是正文描述而非字段标签。\n"
            "契约的条款与灵魂的价值相关。\n"
        )
        assert all(i["name"] != "永罪契约" for i in items), "正文含「先决」词不得产条目"


class TestColonTitleGlue:
    """KN083：`**中文[：:]**英文**` 冒号标题粘连归一（page_529/530
    `<B>中文</B>：<B>English</B>` 相邻加粗段转换残留 + 4 星粘连）→ 标准 FC-1n
    标题。`_fix_quadruple_star` 剥 `****X****` 后残留 `**中文：**X****` 形态，
    `_wrap_bare_titles`/split 全失配 → 正文条目并入前条目或静默丢失（判别器
    FC-3b 带冒号变体也不匹配 → est=got 假一致，page_529 6 条正文丢失）。"""

    def test_50_quad_star_residue_title(self):
        """`**奥法陷阱压制者：**ARCANE TRAP SUPPRESSOR****`（剥星后残留）
        → 标准标题条目"""
        items = run(
            "**奥法陷阱压制者：**ARCANE TRAP SUPPRESSOR****\n"
            "**先决条件：**可以施展或以类法术能力施放解除魔法或高等解除魔法。\n"
            "**专长效果：**你可以用解除魔法或高等解除魔法压制魔法陷阱。\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "奥法陷阱压制者"
        assert it["name_en"] == "ARCANE TRAP SUPPRESSOR"

    def test_51_original_crossline_form(self):
        """原始形态：`**千钧一发：****CLOSE \\nCALL******`（跨行英文）→ 条目"""
        items = run(
            "**千钧一发：****CLOSE \n"
            "CALL******\n"
            "**先决条件：**巧手专长\n"
            "**专长效果：**每日一次，你可重骰巧手。\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "千钧一发"
        assert it["name_en"] == "CLOSE CALL"

    def test_52_halfwidth_colon_plus_field_tail(self):
        """`**淡化身形:**Dampen Presence**：****`（半角冒号+英文闭合星+
        字段开星残留）→ 标题干净转换"""
        items = run(
            "**淡化身形:**Dampen Presence**：****\n"
            "**先决条件**：技能专供（潜行），潜行技能5级\n"
            "**专长效果**：你可以用潜行技能避开任何想用盲视或盲感察觉你的生物。\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        assert items[0]["name"] == "淡化身形"
        assert items[0]["name_en"] == "Dampen Presence"

    def test_53_field_label_quad_star_kept_as_field(self):
        """负测试：`**特殊情况：**** **你可以…`（字段标签+4星残留+值同行，
        无英文）→ 不产伪条目；并入当前条目 text"""
        items = run(
            "**业余调查员（Amateur Investigator）**\n"
            "**先决条件：**智力13\n"
            "**专长效果：**你获得一个灵感池。\n"
            "**特殊情况：**** **你可以选择本专长最多4次。\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "业余调查员"
        assert "特殊情况" in it["text"], "特殊情况字段应保留在条目 text 中"
        assert "最多4次" in it["text"], "字段值应保留"

    def test_54_field_label_hex_star(self):
        """`**专长效果：******`（字段标签+6星残留）→ 剥星保留字段标签"""
        text = FeatFormat().normalize("**专长效果：******\n值在下一行\n")
        assert "**专长效果：**" in text
        assert "******" not in text

    def test_55_field_label_value_guard(self):
        """负测试：字段标签（标签集内）后的英文值不转换（先决条件：Prereq）"""
        items = run(
            "**先决条件：**Prerequisites，又译前置要求\n"
            "**专长效果：**你可以选择本专长。\n"
        )
        assert all(i["name"] != "先决条件" for i in items), "字段标签不得产条目"

    def test_56_translator_guard(self):
        """负测试：`**译者：**yhx_178****`（英文无大写→翻译署名）不转换"""
        text = FeatFormat().normalize(
            "**译者：****yhx_178****，****Falengel******\n"
        )
        assert "译者（yhx_178）" not in text, "译者署名不得转成标题"
        assert "**译者：**" in text, "译者标签保留"

class TestCrossLineEnCRLF:
    """KN083 补充：CRLF 行尾下的跨行英文名合并（page_530 形态）

    源数据 organized 目录为 CRLF 行尾（`Blinding \r\nFlash`），
    `_RE_CROSS_EN` 的 `[ \t]*\n` 跨不过 `\r` → 跨行合并失效 → 4 星/冒号
    标题链全失配 → 正文条目静默丢失（page_530 盲目眩光等 10 条）。
    LF 文件不受影响（`\r?` 可选）。
    """

    def test_57_crlf_cross_line_en_quad_star_title(self):
        """page_530 形态：`**盲目眩光：****Blinding \r\nFlash(Combat)**` → 条目"""
        raw = "**盲目眩光：****Blinding \r\nFlash(Combat)**\n" \
              "**先决条件：**敏捷13，寓守于攻\r\n" \
              "**专长效果：**你可以用剑刃折射强光。\r\n"
        items = run(raw)
        titles = [it["name"] for it in items]
        assert "盲目眩光" in titles, f"CRLF 跨行标题未识别，实际: {titles}"
        it = next(i for i in items if i["name"] == "盲目眩光")
        assert "Blinding" in it["name_en"] and "Flash" in it["name_en"]
        assert "折射强光" in item_text(it)

    def test_58_crlf_cross_line_en_bare_cn_en(self):
        """page_530 表格行后续正文：`**迷失打击：****Disorienting \r\nBlow**`"""
        raw = "**迷失打击：****Disorienting \r\nBlow**\n" \
              "**专长效果：**正文内容。\r\n"
        items = run(raw)
        titles = [it["name"] for it in items]
        assert "迷失打击" in titles, f"实际: {titles}"


class TestHttpLinkStrip:
    """KN075：正文参考链接 `](http…` 剥离（25 chunks 残留清洗）

    形态（HTML 追溯确认 `<A href="论坛帖">锚文本</A>`，锚文本即有效内容）：
    - `[锚文本](httpURL)` → 留锚文本（URL 为论坛帖/官网参考指向噪声）
    - `[URL](URL)` 页头论坛链接行 → 整链剥空（含 `**[URL](URL) **` 加粗壳）
    - `](httpURL)` 残缺（锚文本缺失，如 archivesofnethys）→ 剥空
    - 星内锚（`[*唤起神力PA*]`）整体消费后再交星号归一
    防误伤：PFS 图片 `![[图片]](path)` path 非 http 不动；`**A** **B**` 双加粗不动。
    断言层级：FeatFormat.normalize 输出文本（_strip_http_links 所在层）。
    """

    def _norm(self, raw: str) -> str:
        return FeatFormat().normalize(raw)

    def test_59_body_link_keeps_anchor_text(self):
        """正文参考链接：剥 URL 留锚文本"""
        text = self._norm(
            "**骤雨连击（Flurry of Strikes）**\n"
            "**好处**：你能够将巨化生物模板（快速套用规则版，请见"
            "[怪物图鉴的295页](http://www.goddessfantasy.net/bbs/index.php?topic=63055)"
            "）套用到任何自然变身变化的形态上。\n"
        )
        assert "请见怪物图鉴的295页" in text, f"锚文本应保留，实际: {text}"
        assert "http" not in text and "](http" not in text, f"URL 应剥除，实际: {text}"

    def test_60_header_url_link_line_stripped(self):
        """页头论坛链接行：`[URL](URL) 译者：X` → 只留译者"""
        text = self._norm(
            "[https://www.goddessfantasy.net/bbs/index.php?topic=161097.0]"
            "(https://www.goddessfantasy.net/bbs/index.php?topic=161097.0) 译者：Kochchchch\n"
            "**皇庭巧言（Court Trickster）**\n**好处**：正文。\n"
        )
        assert "译者：Kochchchch" in text, f"译者应保留，实际: {text}"
        assert "http" not in text and "goddessfantasy" not in text

    def test_61_header_url_link_bold_shell_stripped(self):
        """加粗壳页头：`**[URL](URL) **译者` → 无 http、无 **** 残渣"""
        text = self._norm(
            "**[https://goddessfantasy.net/bbs/index.php?topic=83830]"
            "(https://goddessfantasy.net/bbs/index.php?topic=83830) **译者：思维熵化\n"
            "**数学天才（Mathematical Prodigy）**\n**好处**：正文。\n"
        )
        assert "译者：思维熵化" in text
        assert "http" not in text and "****" not in text, f"加粗壳应收敛，实际: {text}"

    def test_62_broken_link_tail_stripped(self):
        """残缺形态：`](httpURL)`（无锚文本）→ 剥空"""
        text = self._norm(
            "**灵魂刃（Soulblade）**\n**好处**：你召唤的武器具有幽冥特性，参见"
            "](http://www.archivesofnethys.com/FeatDisplay.aspx?ItemName=Soulblade)\n"
        )
        assert "参见" in text
        assert "http" not in text and "archivesofnethys" not in text

    def test_63_anchor_with_inner_asterisks_kept(self):
        """星内锚：`[*唤起神力PA*](URL)` → 留 `*唤起神力PA*` 交星号归一"""
        text = self._norm(
            "**领域转授（Domain Channel）**\n**好处**：你获得"
            "[*唤起神力PA*](http://45.79.87.129/bbs/index.php?topic=117833)"
            "中对应领域带来的特殊能力。\n"
        )
        assert "唤起神力PA" in text, f"锚文本应保留，实际: {text}"
        assert "http" not in text and "[*" not in text, f"链接语法应剥除，实际: {text}"

    def test_64_pfs_image_untouched(self):
        """防误伤：PFS 图片 `![[图片]](path)` 非 http 不动（走 _mark_pfs）"""
        text = self._norm(
            "![[图片]](images/feat_pfs.png)\n**突袭警惕（Ambush Awareness）**\n**好处**：正文。\n"
        )
        assert "[[PFS]]" in text, f"PFS 标记应保留，实际: {text}"

    def test_65_double_bold_untouched(self):
        """防误伤：`**A** **B**` 双加粗不被空壳收敛误伤"""
        text = self._norm("**骤雨连击（Flurry of Strikes）**\n**好处**：**敏捷** **感知** 双加值。\n")
        assert "**敏捷** **感知**" in text, f"双加粗应保留，实际: {text}"


class TestStrikeShellRemoval:
    """速查表删除线壳剥除（KN090 收口）——HTML `<B><S>` 加粗删除线段转出
    `**~~中文（~~****~~EN~~****~~）〔类型〕~~****~~~~**`，split 标题判定
    FC 规则不识别（`~~` 干扰）→ 详细条目并入前条、该专长只剩 feat_index
    索引 chunk。normalize 链最前剥 `~{2,}` → 恢复标准标题形态
    （与 L455 致盲重击 `**致盲重击（****Blinding Critical****）〔战斗，重击〕******` 一致）。"""

    def test_01_craft_title_shell_restored(self):
        """调制药剂型（page_195 L473 原样）：剥壳后独立 split 出条目"""
        items = run(
            "**~~调制药剂（~~****~~Brew Potion~~****~~）〔造物〕~~****~~~~**\n"
            "你能制造魔法药水。\n"
            "**先决条件**：施法者等级3级。\n"
            "**专长效果**：你可以制造魔法药水，如同法术制造工艺。\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "调制药剂", f"name 应完整，实际: {it['name']}"
        assert it["name_en"] == "Brew Potion", f"name_en 应完整，实际: {it['name_en']}"
        assert it["feat_type"] == ["造物"], f"feat_type 应归一，实际: {it['feat_type']}"
        assert "~~" not in it["text"], f"删除线壳应剥净，实际: {it['text']}"
        assert "你能制造魔法药水" in it["text"], "正文应并入条目"

    def test_02_leadership_no_type_shell_restored(self):
        """领导力型（无〔类型〕，page_195 L1885 原样）：剥壳后独立 split"""
        items = run(
            "**~~领导力（~~****~~Leadership~~****~~）~~****~~~~**\n"
            "你能让同伴效忠追随你。\n"
            "**先决条件**：魅力13。\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "领导力", f"name 应完整，实际: {it['name']}"
        assert it["name_en"] == "Leadership", f"name_en 应完整，实际: {it['name_en']}"
        assert it["feat_type"] == [], f"无类型不应产出 feat_type，实际: {it['feat_type']}"

    def test_03_plain_text_strike_line_kept_content(self):
        """防误伤：正文 `<S>` 删除线段（`~~旧文字~~`）剥标记留内容，不破坏周围文本"""
        text = FeatFormat().normalize(
            "**抄写卷轴（****Scribe Scroll****）〔造物〕******\n"
            "~~已删除的旧描述~~你能把法术抄成卷轴。\n"
        )
        assert "~~" not in text, f"删除线标记应剥净，实际: {text}"
        assert "已删除的旧描述" in text, f"删除线内容应保留，实际: {text}"
        assert "你能把法术抄成卷轴" in text, f"正文不应被误伤，实际: {text}"


class TestElidedCnEnGlue:
    """无空格紧邻 elided 形态（KN090 收口）——page_311 详细条目块：
    `**情感导体****Emotional Conduit`（HTML 相邻加粗段粘连，中文与英文间
    无空格）。D 分支 `_RE_BARE_CN_EN_STAR_BOLD` 组2 非贪婪吞中文尾字配
    `\*{4,}` → name 截断（情感导体→情感导）；组1 后 `\s+` 收窄后紧邻形态
    整体失配，转交 `_RE_ELIDED_CN_EN_GLUE` 归一。"""

    def test_01_cn_en_glue_no_space_kept_full_name(self):
        """情感导体型（page_311 L156 原样）：name/name_en 完整"""
        items = run(
            "**情感导体****Emotional Conduit\n"
            "*你与魅影之间深刻的情感共鸣使你能够掌握他人的情绪。*\n"
            "**先决条件**：共享意识（Shared Consciousness）职业能力\n"
            "**好处**：根据你的魅影（Phantom）的情感羁绊（Emotional Focus），"
            "你能够精通数个\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "情感导体", f"name 应完整，实际: {it['name']}"
        assert it["name_en"] == "Emotional Conduit", f"name_en 应完整，实际: {it['name_en']}"
        assert "情感导体" not in it["text"], "正文不应残留未归一标题"
        assert it["format_cluster"] == "elided"

    def test_02_glue_en_with_leading_space(self):
        """横冲直撞型（page_321，`**** EN` 前导空格）：EN 前导空格自动剥离"""
        items = run(
            "**横冲直撞**** Merciless Rush\n"
            "你可以用肩膀撞击敌人的盾牌。\n"
            "**先决条件**：力量13。\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "横冲直撞", f"name 应完整，实际: {it['name']}"
        assert it["name_en"] == "Merciless Rush", f"name_en 应剥前导空格，实际: {it['name_en']}"

    def test_03_d_branch_spaced_kept(self):
        """守卫：D 分支空格形态（`**中文 English*****正文`，FC-8c ISI 风格化
        法术）收窄后仍正确归一（组1 完整不截断）"""
        items = run(
            "**高等时髦法术 Greater Stylized Spell*****你的移动类魔法让盟友"
            "比平时更迅捷。\n**先决条件**：法术辨识5级。\n"
        )
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "高等时髦法术", f"name 应完整，实际: {it['name']}"
        assert it["name_en"] == "Greater Stylized Spell"


class TestKn084TypeParenEnLeak:
    """KN084：FC-1r 类型括号混入英文名泄漏 feat_type（MA 页 M8 跨行并入形态）。

    源形态（page_624）：`**中文（类型）**` + 跨行裸英文名 + 跨行裸英文类型括号，
    M8（`_RE_STAR_OUTSIDE_EN_TYPE`）把裸英文名并进类型括号 →
    `**中文（类型, English ）（EN_TYPE）**`，FC-1r 分支原用 split_feat_types
    把英文段当类型泄漏进 feat_type。修复：FC-1r 分支类型括号改用
    `_split_paren_content` 拆分（英文段进 name_en，纯中文段进 feat_type）。
    """

    def test_01_ma_type_paren_en_leak_fixed(self):
        """MA 形态：`**诅咒巫术（神话, Accursed Hex ）（Mythic）**` →
        name_en=Accursed Hex、feat_type=['神话']（无英文泄漏）；Mythic（英文
        类型）不进 name_en/feat_type"""
        items = run(
            "**诅咒巫术（神话）**\n"
            "Accursed Hex \n"
            "(Mythic)\n"
            "*你能够施展一个神话版本的诅咒。*\n"
            "**好处**：你可以使用一次神话之力来施展一个诅咒。\n"
        )
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "诅咒巫术", f"name 应完整，实际: {it['name']}"
        assert it["name_en"] == "Accursed Hex", f"name_en 应为真英文名，实际: {it['name_en']!r}"
        assert it["feat_type"] == ["神话"], f"feat_type 不应泄漏英文，实际: {it['feat_type']}"

    def test_02_pure_cn_type_fc1r_guard(self):
        """守卫：正常 FC-1r（类型括号纯中文）行为不变——英文括号仍是 name_en"""
        items = run(
            "**致命之角（战斗专长）（Deadly Horns）**\n"
            "**好处**：你的角可以造成致命伤害。\n"
        )
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "致命之角"
        assert it["name_en"] == "Deadly Horns", f"纯中文类型括号英文名不变，实际: {it['name_en']!r}"
        assert it["feat_type"] == ["战斗"], f"战斗专长应归一为战斗，实际: {it['feat_type']}"

    def test_03_multi_cn_type_plus_en(self):
        """多中文类型 + 英文名：`（战斗专长，演武专长, Spectacular Exit）` →
        中文段全进 feat_type（战斗专长归一为战斗）、英文段进 name_en"""
        items = run(
            "**华丽转进（战斗专长，演武专长）**\n"
            "Spectacular Exit \n"
            "(Combat, Performance)\n"
            "**好处**：你可以华丽的转进。\n"
        )
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "华丽转进"
        assert it["name_en"] == "Spectacular Exit", f"name_en 应为真英文名，实际: {it['name_en']!r}"
        assert it["feat_type"] == ["战斗", "演武专长"], f"实际: {it['feat_type']}"


class TestKn084AbilityMarkNotType:
    """KN084 残留：能力标记（Su/Sp/Ex）不得进 feat_type。

    源形态两类：
    - MTT（whitespace 跨空行误并入）：`**奥法导管（Eldritch Conduit）**` +
      空行 + `（Su）正文段首`——_RE_WS_TITLE 的 `\s+` 跨空行把正文段首
      （Su）并入标题 → FC-1q 当类型。修法：whitespace 并入限同行空白。
    - WMH（标题行（Ex））：`**武艺无尽（Abundant Tactics）（Ex）**`——
      FC-1q 把能力标记当类型。修法：FC-1q 分支能力标记不进 feat_type、
      保正文。
    """

    def test_01_mtt_blank_line_ability_mark_not_merged(self):
        """`**标题（EN）**` + 空行 + `（Su）正文` → （Su）前置正文（FC-1q 能力
        标记过滤），feat_type 空，whitespace 簇保持（防子节标题过滤误删）"""
        items = run(
            "**奥法导管（Eldritch Conduit）**\n"
            "\n"
            "（Su）以一个整轮动作，拥有该天赋的盗贼可以使用两瓶药水。\n"
        )
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "奥法导管", f"实际: {it['name']}"
        assert it["name_en"] == "Eldritch Conduit", f"实际: {it['name_en']!r}"
        assert it["feat_type"] == [], f"能力标记（Su）不得进 feat_type，实际: {it['feat_type']}"
        assert it["text"].startswith("（Su）"), f"（Su）应前置正文，实际 text: {it['text'][:60]!r}"
        assert it["format_cluster"] == "whitespace", f"应为 whitespace 簇，实际: {it['format_cluster']}"

    def test_02_wmh_ex_mark_in_title_not_type(self):
        """`**武艺无尽（Abundant Tactics）（Ex）**` → feat_type 空、（Ex）保正文"""
        items = run(
            "**武艺无尽（Abundant Tactics）（Ex）**\n"
            "战士可以将自己的武器训练加值加到每日使用次数上。\n"
        )
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "武艺无尽", f"实际: {it['name']}"
        assert it["name_en"] == "Abundant Tactics", f"实际: {it['name_en']!r}"
        assert it["feat_type"] == [], f"能力标记（Ex）不得进 feat_type，实际: {it['feat_type']}"
        assert "（Ex）" in it["text"], f"（Ex）应保正文，实际 text: {it['text'][:60]!r}"

    def test_03_seed10_whitespace_same_line_kept(self):
        """守卫：seed 10 同行 whitespace 形态不变（密集阻击）"""
        items = run(
            "**密集阻击** (Barrage of Styles，战斗，团队 ) 出处\n"
        )
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "密集阻击"
        assert it["name_en"] == "Barrage of Styles"
        assert it["feat_type"] == ["战斗", "团队"]
        assert it["format_cluster"] == "whitespace"

class TestKn084StarShellTypeParen:
    """KN084 残留：page_505 elided 星壳类型括号（`〔**Combat**〕` 形态）——
    BBS 帖 HTML 转换产物 `**中文（类型）****EN****（****类型****）******`
    归一后为 `**中文（类型）（EN）〔**TYPE**〕**`：FC-1q 组1 贪婪吞 `（战斗）`
    （中文类型进 name）、组3 带星壳（英文类型进 feat_type）——双修复：
    组1 尾部中文括号拆出为类型、组3 星壳剥除且中英同义去重（中文优先）。"""

    def test_01_page505_holy_water_assault(self):
        """`**圣水攻袭（战斗）****Holy \r\nWater Assault****（****Combat****）******`
        → name 纯中文、feat_type=['战斗']（中文，与速查表一致）、name_en 英文"""
        raw = (
            "**圣水攻袭（战斗）****Holy \r\n"
            "Water Assault****（****Combat****）******\n"
            "**先决条件：**BAB+1、知识（宗教）3级\n"
        )
        items = run(raw)
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "圣水攻袭", f"（战斗）不得进 name，实际: {it['name']!r}"
        assert it["name_en"] == "Holy Water Assault", f"实际: {it['name_en']!r}"
        assert it["feat_type"] == ["战斗"], f"实际: {it['feat_type']}"
        assert "**Combat**" not in str(it["feat_type"]), f"星壳不得进 feat_type"

    def test_02_page505_weapon_versatility(self):
        """同构第二条：可能性之兵"""
        raw = (
            "**可能性之兵（战斗）****Weapon \r\n"
            "Versatility****（****Combat****）******\n"
            "**先决条件：**武器专攻、BAB+1\n"
        )
        items = run(raw)
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "可能性之兵", f"实际: {it['name']!r}"
        assert it["name_en"] == "Weapon Versatility", f"实际: {it['name_en']!r}"
        assert it["feat_type"] == ["战斗"], f"实际: {it['feat_type']}"

    def test_03_plain_fc1q_untouched(self):
        """守卫：常规 FC-1q（组1 无中文括号）不受影响——宿命（Fate）（战斗）"""
        items = run(
            "**宿命（Fate）（战斗）**\n"
            "正文描述。\n"
        )
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "宿命", f"实际: {it['name']!r}"
        assert it["name_en"] == "Fate", f"实际: {it['name_en']!r}"
        assert it["feat_type"] == ["战斗"], f"实际: {it['feat_type']}"

    def test_04_cn_paren_no_en_type(self):
        """守卫：组1 尾部纯中文括号但无星壳类型——`**致盲水光（法术）**`
        （FC-1n 形态）不误入：仍是单括号形态，name_en 应为空"""
        items = run(
            "**致盲水光（法术）**\n"
            "正文描述。\n"
        )
        assert len(items) == 1
        it = items[0]
        assert it["name"] == "致盲水光", f"实际: {it['name']!r}"


class TestIntroMarker:
    """KN094：feat_intro 判别（57 高置信）——空 text 章首标题 / title 以「专长」结尾
    且无字段标签的类别介绍段，format 层打 intro 标记（processor 层映射 feat_intro）"""

    def test_01_chapter_header_empty_text(self):
        """章首标题《核心规则手册》专长（空 text）→ intro"""
        items = run("**《核心规则手册》专长（****Core \nRulebook Feats****）******\n")
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        assert not items[0].get("text", "").strip()
        assert items[0].get("intro") is True

    def test_02_category_intro_no_field(self):
        """类别介绍段（团队专长 + 散文，无字段标签）→ intro"""
        items = run(
            "**团队专长（****Teamwork Feats****）******\n"
            "团队专长会带来很高加值，但只能在特定环境下生效。\n"
        )
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        assert items[0].get("intro") is True

    def test_03_feat_entry_with_field_not_intro(self):
        """具体专长条目（有字段标签）→ 不打标"""
        items = run(
            "**突袭警惕（Ambush Awareness）**\n"
            "**先决条件：** 警觉\n"
            "**好处：** 你不受突袭的措手不及。\n"
        )
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        assert "intro" not in items[0]

    def test_04_intro_title_with_field_not_intro(self):
        """title 以「专长」结尾但有字段标签（多条目拼组）→ 不打标"""
        items = run(
            "**新流派专长**\n"
            "**先决条件：** 内家拳\n"
            "**好处：** 你获得该流派。\n"
        )
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        assert "intro" not in items[0]

    def test_05_table_row_not_intro(self):
        """速查表行（lb_marker）→ 不打标（feat_index 优先，KN085 28 个空 text）"""
        items = run("| Acrobatic 特技专家 |  | 特技和飞行检定+2 |\n")
        assert items and items[0]["format_cluster"] == "lb_marker"
        assert "intro" not in items[0]

    def test_06_plain_named_entry_not_intro(self):
        """普通条目名不以「专长」结尾 → 不打标"""
        items = run(
            "**钢铁之躯**\n"
            "**好处：** 你的躯体如铁般坚硬。\n"
        )
        assert len(items) == 1, f"应产 1 个条目，实际 {len(items)}"
        assert "intro" not in items[0]


class TestKn109TemplateSectionDrop:
    """KN109（page_622 MA 神话冒险引言）：专长描述格式模板节弹掉 + intro 前置。

    page_622 是纯引言页：神话专长规则说明 + 专长类型 + 描述格式模板。格式模板节
    （title 命中字段标签词/格式词）形态同 FC-1q 专长条目，被误判为伪条目入库
    （先决条件/好处/正常 等 title 污染检索）；类别规则节（神话专长 text>150
    无字段）被「子节标题排除」误杀丢失正文。修复：模板词弹掉 + intro 判定前置
    （intro 豁免子节排除）。"""

    TEMPLATE_WORDS = ("专长名称", "专长类型", "专长描述", "先决条件", "好处", "正常")

    def test_01_field_word_titles_dropped(self):
        """格式模板节 title=先决条件/好处/正常 → 弹掉（不入库）"""
        raw = (
            "**先决条件（Prerequisite）**：此处会列出为了选取该专长而需要的最低属性。\n"
            "**好处（Benefit）**：此处会列出专长能给角色带来什么。\n"
            "**正常（Normal）**：此处会列出当角色不具有该专长时受到的限制。\n"
        )
        items = run(raw)
        names = [it["name"] for it in items]
        assert all(w not in names for w in self.TEMPLATE_WORDS), f"模板节应弹掉，实际 {names}"

    def test_02_format_word_titles_dropped(self):
        """格式模板节 title=专长名称/专长类型/专长描述 → 弹掉"""
        raw = (
            "**专长名称（Feat Name）**：专长的名称后也标注了它所属的类别。\n"
            "**专长类型（Types of Feats）**：许多专长所属的类型都具有特殊规则。\n"
            "**专长描述（Feat Descriptions）**：神话专长按照后述的简表中进行了总结。\n"
        )
        items = run(raw)
        names = [it["name"] for it in items]
        assert all(w not in names for w in ("专长名称", "专长类型", "专长描述")), f"实际 {names}"

    def test_03_regular_feat_with_field_kept(self):
        """真实专长条目（有字段标签、title 非模板词）→ 不受影响"""
        items = run(
            "**突袭警惕（Ambush Awareness）**\n"
            "**先决条件：** 警觉\n"
            "**好处：** 你不受突袭的措手不及。\n"
        )
        assert len(items) == 1, f"实际 {len(items)}"
        assert items[0]["name"] == "突袭警惕"

    def test_04_mythic_feats_intro_long_text_kept(self):
        """类别规则节（title 以专长结尾 + 长散文无字段）→ intro 保留（intro 前置）"""
        raw = (
            "**神话专长（Mythic Feats）**\n"
            "神话角色与怪物会在他们获取神话阶层或神话等级时得到神话专长。"
            "这些专长只能在神话力量得到提升时选取，神话专长不能在角色正常等级提高"
            "或者任何其他奖励专长中获得。大多数神话专长都需要非神话专长做为前置。"
            "这些神话专长会增强作为先决条件的非神话专长所带来的优势，使它们的效果"
            "变得令人惊异。当角色在获取神话专长时，若她并不具有任何作为先决条件的"
            "必要专长的话，她可以等到下一次获得阶层或等级时再选取神话专长。\n"
        )
        items = run(raw)
        assert len(items) == 1, f"应保留为 intro，实际 {len(items)}"
        assert items[0]["name"] == "神话专长", f"实际 {items[0]['name']}"
        assert items[0].get("intro") is True

    def test_05_mythic_metamagic_intro_kept(self):
        """神话和超魔专长（title 以专长结尾 + 长散文）→ intro 保留"""
        raw = (
            "**神话和超魔专长（Mythic and Metamagic Feats）**\n"
            "你会注意到这里并不存在神话超魔专长。这是因为神话版本的法术已经存在了，"
            "在某种程度上它们自身已经受到超魔了，而且还有许多神话能力能够进一步增强"
            "这些法术，所以不再需要神话超魔专长进一步进行提升。若你渴望得到更多强大"
            "的施法能力，那么可以多次选取神话法术学识专长。本节中还提供一个非神话"
            "超魔专长，用于施放神话版的法术：卓越法术（Ascendant Spell）。\n"
        )
        items = run(raw)
        assert len(items) == 1, f"应保留为 intro，实际 {len(items)}"
        assert items[0]["name"] == "神话和超魔专长", f"实际 {items[0]['name']}"
        assert items[0].get("intro") is True

    def test_06_page_622_end_to_end(self):
        """page_622 整页近似输入：产出 = 3 个类别 intro，无伪条目"""
        raw = (
            "**神话专长（Mythic Feats）**\n"
            "神话角色与怪物会在他们获取神话阶层或神话等级时得到神话专长。"
            "这些专长只能在神话力量得到提升时选取，神话专长不能在角色正常等级提高"
            "或者任何其他奖励专长中获得。大多数神话专长都需要非神话专长做为前置。"
            "这些神话专长会增强作为先决条件的非神话专长所带来的优势。若神话专长的"
            "效果是基于你的神话阶层的话，那么最低值总是1点。本节会包含一些非神话"
            "专长。\n"
            "**专长类型（Types of Feats）**\n"
            "许多专长所属的类型都具有一些与其相关的特殊规则。\n"
            "**超魔专长（Metamagic Feats）**\n"
            "超魔专长使得施法者能够调整并改变他们的法术。\n"
            "**神话专长（Mythic Feats）**\n"
            "只有具有神话阶层的角色和具有神话等级的生物能够选取这些专长。"
            "若生物变为非神话的状态，它就不会再获得这些专长的好处。许多神话专长"
            "会增强具有相同名称的非神话专长的效果。\n"
            "**神话和超魔专长（Mythic and Metamagic Feats）**\n"
            "你会注意到这里并不存在神话超魔专长。这是因为神话版本的法术已经存在了，"
            "所以不再需要神话超魔专长进一步进行提升。\n"
            "**专长描述（Feat Descriptions）**\n"
            "神话专长按照后述的简表中进行了总结。\n"
            "**专长名称（Feat Name）**：专长的名称后也标注了它所属的类别。\n"
            "**先决条件（Prerequisite）**：此处会列出为了选取该专长而需要的最低属性。\n"
            "**好处（Benefit）**：此处会列出专长能给角色带来什么。\n"
            "**正常（Normal）**：此处会列出当角色不具有该专长时受到的限制。\n"
            "**特殊（Special）**：此处会额外补充一些关于专长的不寻常情况。\n"
        )
        items = run(raw)
        names = [it["name"] for it in items]
        assert "神话专长" in names, f"神话专长应保留，实际 {names}"
        assert "神话和超魔专长" in names, f"神话和超魔专长应保留，实际 {names}"
        assert "超魔专长" in names, f"超魔专长应保留，实际 {names}"
        assert all(w not in names for w in ("专长名称", "专长类型", "专长描述", "先决条件", "好处", "正常", "特殊")), \
            f"模板节应弹掉，实际 {names}"
        for it in items:
            assert it.get("intro") is True, f"全部应为 intro，实际 {[ (i['name'], i.get('intro')) for i in items ]}"
