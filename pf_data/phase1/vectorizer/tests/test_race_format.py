"""
test_race_format.py — 种族格式解析 TDD 测试（真实源数据形态驱动）

样本来源：pf_rules_md_organized/种族/ 真实文件截取（保留星壳/断行/裸文本
等原始形态，压缩连续空行——_normalize_blank_lines 天然处理）。
断言口径：RaceFormat.normalize → promote → split_into_items 产出的 item dict：
  kind / name / name_en / section / replaces / source / text / format_cluster

12 枚举（元数据定稿 2026-08-04）：race_intro / race_trait / alt_trait /
fcb_entry / race_archetype / race_variant / race_feat / race_spell /
race_item / race_sidebar / race_overview / monster_block
"""

import re

import pytest

from vectorizer.formats.race import RaceFormat, _wrap_bare_colon_titles_race as R_


def run(raw: str) -> list:
    """RaceFormat 全链：normalize → promote → split"""
    fmt = RaceFormat()
    text = fmt.normalize(raw)
    text = fmt.promote(text)
    return fmt.split_into_items(text, source_name="race")


def item_text(it: dict) -> str:
    """条目 text 归一化（去空白差异）供断言"""
    return re.sub(r"\s+", " ", it.get("text", ""))


# ============ 簇 A：ARG 完整种族页（page_160 猫族真实形态） ============

CLUSTER_A_MAIN = (
    "**猫族（****Catfolk****，又译猫人）******\n"
    "猫族是永不言退的天生探险家。\n"
    "**体貌描述**：整体而言，猫族轻盈柔软、苗条修长。\n"
    "**+2****敏捷，****+2****魅力，****-2****感知**：猫族随和而又敏捷，但是经常缺乏常识。\n"
    "**生物类型**：猫族属于类人生物，猫族子类。\n"
    "**中型体型**：猫族是中等体型生物。\n"
    "**标准速度**：猫族的基本速度为30尺。\n"
    "**昏暗视觉（****Low-Light \n"
    "Vision****）**：猫族在昏暗中可以看人类的两倍远。\n"
)


class TestClusterA:
    """簇 A：ARG 完整种族页"""

    def test_main_title_star_shell(self):
        """`**猫族（****Catfolk****，又译猫人）******`（4 星嵌套星壳 + 又译
        后缀）→ 主条目 name=猫族 name_en=Catfolk。"""
        items = run(CLUSTER_A_MAIN)
        assert items, "应产出条目"
        it = items[0]
        assert it["kind"] == "race_intro"
        assert it["name"] == "猫族"
        assert it["name_en"] == "Catfolk"
        assert "猫族（Catfolk，又译猫人）" not in item_text(it), "星壳不应残留"

    def test_ability_adj_star_shell(self):
        """属性调整字段星壳：`**+2****敏捷，****+2****魅力，****-2****感知**：`
        → 归一为 `**+2敏捷，+2魅力，-2感知**：` 并入主条目。"""
        items = run(CLUSTER_A_MAIN)
        it = items[0]
        t = item_text(it)
        assert "**+2敏捷，+2魅力，-2感知**：猫族随和而又敏捷" in t, \
            f"属性调整字段应归一为单加粗段：{t[:120]!r}"
        assert "****" not in t, "text 不应残留 4 星壳"

    def test_five_field_lines_in_intro(self):
        """五字段行（体貌描述/社会/阵营和宗教/冒险）并入主条目不产伪条目"""
        items = run(
            "**半精灵（****Half-Elf****）**\n"
            "**体貌描述**：半精灵继承了人类的适应力。\n"
            "**社会**：半精灵在人类与精灵之间徘徊。\n"
            "**阵营和宗教**：半精灵的阵营趋于中立。\n"
            "**冒险**：半精灵通常是冒险者。\n"
        )
        assert len(items) == 1, f"应只有主条目，实际 {len(items)}"
        it = items[0]
        assert it["kind"] == "race_intro"
        t = item_text(it)
        assert "**体貌描述**：半精灵继承了人类的适应力。" in t
        assert "**社会**：半精灵在人类与精灵之间徘徊。" in t
        assert "**阵营和宗教**：半精灵的阵营趋于中立。" in t
        assert "**冒险**：半精灵通常是冒险者。" in t

    def test_cross_line_en_name(self):
        """断行英文名：`**昏暗视觉（****Low-Light \\nVision****）**` →
        name_en=Low-Light Vision（跨行合并）。"""
        items = run(CLUSTER_A_MAIN)
        traits = [it for it in items if it["kind"] == "race_trait"]
        assert traits, "应产出特性条目"
        it = traits[0]
        assert it["name"] == "昏暗视觉"
        assert it["name_en"] == "Low-Light Vision"

    def test_section_header_changes_kind(self):
        """章节标题（种族特性替换）切换条目类型：替换特性 → alt_trait"""
        items = run(
            "**猫族种族特性（Catfolk Racial Traits）**\n"
            "**猫之幸运（Cat's Luck, Ex）**：每日1次，猫族骰反射豁免时可以取高。\n"
            "**种族特性替换（Alternate Racial Traits）**\n"
            "**猫爪（Cat's Claws）**：这对爪子是主要武器。这一种族特性取代狩猎本能。\n"
            "**可选天赋职业奖励（Favored Class Options）**\n"
            "**诗人**：【逸闻知识】加值+1/2。\n"
        )
        kinds = [it["kind"] for it in items]
        assert "race_trait" in kinds and "alt_trait" in kinds and "fcb_entry" in kinds, \
            f"章节应驱动条目类型：{kinds}"
        alt = next(it for it in items if it["kind"] == "alt_trait")
        assert alt["name"] == "猫爪"
        assert "取代狩猎本能" in item_text(alt)

    def test_h2_section_keyword_changes_kind(self):
        """H2 章节标题（`## 内海种族 ISR 其他种族替换特性`，整理规范形态）
        剥 `## ` 前缀后应触发章节判定：替换特性条目 → alt_trait。现状 H2 行
        带 `## ` 前缀不匹配标题正则 → 章节态不切换 → 整文件替换特性误标
        race_trait（2026-08-04 KN116 残留，ISR×2 + BotC 共 103 条）。"""
        items = run(
            "## 内海种族 ISR 其他种族替换特性\n"
            "> 来源：内海种族（Inner Sea Races）ISR，页码见原书，未整理 → ISR → 种族\n"
            "**神裔——圣战魔法（Aasimars—Crusading Magic）：**"
            "许多神裔都觉得有义务受训以对抗魔族。此种族特性替换技能奖励和类法术能力。\n"
            "**神裔——失落的约定（Aasimars—Lost Promise）：**"
            "邪恶的力量对于天界同行赐予的礼物被歪曲而感到愉悦。此种族特性替换类法术能力。\n"
        )
        alts = [it for it in items if it["kind"] == "alt_trait"]
        assert len(alts) == 2, f"两个替换特性应切 alt_trait：{[(i['kind'], i['name']) for i in items]}"
        assert alts[0]["name"] == "神裔——圣战魔法"
        assert "替换技能奖励和类法术能力" in item_text(alts[0])

    def test_h2_section_beats_race_h2_signal(self):
        """`<!-- ISR-source:… -->` 文件级注释置 pending_race_h2，但下一行
        是章节标题（含章节关键字）——章节切态优先，信号作废：后续条目
        保持 alt_trait，不被信号消费重置 intro（2026-08-04 KN116 残留：
        ISR 真实文件 `<!-- ISR-source:page_1326.md:其他种族替换特性 -->`
        注释 + H2 章节 → 「其他种族」误切 race_intro 重置 state）。"""
        items = run(
            "<!-- ISR-source:page_1326.md:其他种族替换特性 -->\n"
            "## 内海种族 ISR 其他种族替换特性\n"
            "> 来源：内海种族（Inner Sea Races）ISR，页码见原书，未整理 → ISR → 种族\n"
            "**神裔——圣战魔法（Aasimars—Crusading Magic）：**"
            "许多神裔都觉得有义务受训以对抗魔族。此种族特性替换技能奖励和类法术能力。\n"
        )
        alts = [it for it in items if it["kind"] == "alt_trait"]
        assert len(alts) == 1, f"条目应保持 alt_trait：{[(i['kind'], i['name']) for i in items]}"
        assert alts[0]["name"] == "神裔——圣战魔法"

    def test_h2_race_trait_section_keyword_regression(self):
        """H2「种族特性」→ race_trait 态（BotB/BotN 形态回归）：H2 剥前缀
        切态后条目类型与现状一致，不误伤。"""
        items = run(
            "## 影生暗生种族特性\n"
            "**影生（Fetchling）**：影生是阴影位面的后裔。\n"
            "**黑暗视觉（Darkvision）**：影生拥有黑暗视觉。\n"
        )
        traits = [it for it in items if it["kind"] == "race_trait"]
        assert len(traits) == 2, f"两个特性应切 race_trait：{[(i['kind'], i['name']) for i in items]}"

    def test_archetype_entry(self):
        """种族职业变体：`**贼猫（****Cat \\nBurglar****，盗贼变体）******` →
        race_archetype；变体能力（星标拆中文归一为完整标题 `**魅影身姿（Phantom
        Presence, Ex）**`）→ 独立 race_archetype（2026-08-04：原并入变体文本，
        检索端变体能力不可单独命中 → 独立切出）。"""
        items = run(
            "**种族职业变体（Racial Archetypes）**\n"
            "**贼猫（****Cat \n"
            "Burglar****，盗贼变体）******\n"
            "凭借过人的手腕和潜行天赋，猫族得以成为优秀的窃贼。\n"
            "**魅****影身姿（****Phantom \n"
            "Presence, Ex****）**：4级起，贼猫精通潜行之道。\n"
        )
        archs = [it for it in items if it["kind"] == "race_archetype"]
        assert len(archs) == 2, f"应产出 2 个变体条目（贼猫+魅影身姿），实际 {len(archs)}"
        it = archs[0]
        assert it["name"] == "贼猫"
        assert it["name_en"] == "Cat Burglar"
        it1 = archs[1]
        assert it1["name"] == "魅影身姿"
        assert it1["name_en"] == "Phantom Presence Ex"
        t = item_text(it1)
        assert "4级起，贼猫精通潜行之道" in t, "变体能力正文应保留"
        assert "****" not in t, "变体能力不应残留星壳"

    def test_archetype_ability_with_feat_word_in_name(self):
        """archetype 能力段名含「专长」（`**海威专长（Aquatic Prowess Feat,
        Ex）**`）不得被 race_feat 章节误判：独立切出 race_archetype、标题保留、
        后续能力段分类不被污染（2026-08-04 M21 波涛守卫，KN120）"""
        items = run(
            "**种族职业变体（Racial Archetypes）**\n"
            "**波涛守卫（****Wave \n"
            "Warden****，游侠变体）******\n"
            "波涛守卫在大海之中巡逻。\n"
            "**深水哨卫（****Deep \n"
            "Sentinel, Ex****）**：当波涛守卫在水下侦查生物时，将等级的一半加在察觉检定上。这一能力取代追踪。\n"
            "**海威专长（****Aquatic \n"
            "Prowess Feat, Ex****）**：在2级和之后的每4级，波涛守卫可以选择一个奖励专长。这一能力取代战斗流派奖励专长。\n"
            "**偏好地形（****Favored \n"
            "Terrain, Ex****）**：3级时，波涛守卫获得水体作为偏好地形。这一能力取代偏好地形。\n"
        )
        archs = [it for it in items if it["kind"] == "race_archetype"]
        assert len(archs) == 4, f"应产出 4 个变体条目（波涛守卫+3 能力段），实际 {len(archs)}"
        # 海威专长独立切出、标题保留
        hw = next(it for it in archs if it["name"] == "海威专长")
        assert "Aquatic Prowess Feat" in hw["name_en"], f"海威专长英文名应保留：{hw['name_en']}"
        assert "在2级和之后的每4级" in item_text(hw)
        # 深水哨卫不吞海威专长正文
        ds = next(it for it in archs if it["name"] == "深水哨卫")
        assert "奖励专长" not in item_text(ds), "深水哨卫不应吞并海威专长正文"
        # 无 race_feat 污染
        feats = [it for it in items if it["kind"] == "race_feat"]
        assert not feats, f"能力段不应被标 race_feat：{[(f['name'], f['text'][:20]) for f in feats]}"

    def test_note_field_line_merged_in_feat_flow(self):
        """条目流态 `**备注**：…` 是字段行并入当前条目，不切 title=备注 的
        伪条目（2026-08-04 M21：半兽人 page_17 狂暴专长备注段）"""
        items = run(
            "**半兽人专长（Half-Orc Feats）**\n"
            "**不灭狂暴（****Ferocious \n"
            "Resilience****）******\n"
            "**专长效果**：当你处于狂暴状态时，每天1次，如果你受到一次攻击所造成的伤害足以杀死你，你能够花费狂暴轮数降低伤害。\n"
            "**备注**：如果该伤害仍会使你失去意识，你的狂暴就会像通常情况那样结束。\n"
        )
        feats = [it for it in items if it["kind"] == "race_feat"]
        assert len(feats) == 1, f"备注应并入专长条目，实际 {len(feats)} 个 race_feat"
        assert feats[0]["name"] == "不灭狂暴"
        assert "如果该伤害仍会使你失去意识" in item_text(feats[0])

    def test_feat_entry_in_section(self):
        """新种族规则下专长章节：`**黑猫（****Black Cat****）******` +
        斜体壳描述 + 先决条件/专长效果字段 → race_feat，字段并入 text"""
        items = run(
            "**猫族专长（Catfolk Feats）**\n"
            "**黑猫（****Black Cat****）******\n"
            "***厄运降临在那些胆敢攻击你的人身上。*********\n"
            "**先决条件**：猫族。\n"
            "**专长效果**：每日1次，当你被近战攻击命中时……\n"
        )
        feats = [it for it in items if it["kind"] == "race_feat"]
        assert len(feats) == 1, f"应产出 1 个专长条目，实际 {len(feats)}"
        it = feats[0]
        assert it["name"] == "黑猫"
        assert it["name_en"] == "Black Cat"
        t = item_text(it)
        assert "厄运降临在那些胆敢攻击你的人身上" in t, "斜体壳描述应保留"
        assert "**先决条件**：猫族。" in t
        assert "**专长效果**：每日1次" in t
        assert "***" not in t, "斜体星壳不应残留"

    def test_item_entry(self):
        """装备/奇物条目：`**猫眼冠（****Cat's Eye Crown****）******` +
        灵光/价格字段行 → race_item"""
        items = run(
            "**猫族奇物（Catfolk Magic Items）**\n"
            "**猫眼冠（****Cat's Eye Crown****）******\n"
            "**灵光**：中等预言系；**施法者等级**：10级；\n"
            "**位置**：头部；**价格**：18000gp；**重量**：1磅。\n"
            "这顶纤细的银制冠饰的中央镶嵌着一枚猫眼石。\n"
            "**制造条件**：“制造奇物”；‘锐耳术/鹰眼术’。\n"
            "**制造成本**：9000gp。\n"
        )
        items_list = [it for it in items if it["kind"] == "race_item"]
        assert len(items_list) == 1, f"应产出 1 个奇物条目，实际 {len(items_list)}"
        it = items_list[0]
        assert it["name"] == "猫眼冠"
        assert it["name_en"] == "Cat's Eye Crown"
        t = item_text(it)
        # 同行多字段（`；**字段**：`）由公共 _split_inline_fields 星形拆分
        # 为每字段独立行（feat 同款设计），分别断言字段子串
        assert "**灵光**：中等预言系；" in t
        assert "**施法者等级**：10级；" in t
        assert "**制造条件**：" in t
        assert "****" not in t

    def test_spell_entry(self):
        """法术条目：`**九命天猫****（****Nine Lives****，又译９命）******` +
        两列空第二列表格 → race_spell，表格转字段形态"""
        items = run(
            "**猫族法术（Catfolk Spells）**\n"
            "**九命天猫****（****Nine Lives****，又译９命）******\n"
            "| 学派 |  | 防护系 |\n"
            "| 环级 |  | 牧师8，女巫9 |\n"
            "| 施放时间 |  | 标准动作 |\n"
            "和法术的名字不同，这个强大的法术并不能赋予目标更多的生命。\n"
        )
        spells = [it for it in items if it["kind"] == "race_spell"]
        assert len(spells) == 1, f"应产出 1 个法术条目，实际 {len(spells)}"
        it = spells[0]
        assert it["name"] == "九命天猫"
        assert it["name_en"] == "Nine Lives"
        t = item_text(it)
        assert "学派" in t and "防护系" in t
        assert "牧师8，女巫9" in t

    def test_quick_ref_not_fake_entry(self):
        """速查条目（`【能力速查】` / `【专长速查】`）并入当前条目，不产伪条目"""
        items = run(
            "**猫爪（Cat's Claws）**：这对爪子是主要武器。\n"
            "【能力速查】**灵敏嗅觉（Scent, Ex）**：这种特殊能力可以让生物察觉接近的敌人。\n"
        )
        assert len(items) == 1, f"速查段不应产伪条目：{len(items)}"
        t = item_text(items[0])
        assert "灵敏嗅觉" in t

    def test_translator_notes_preserved_inline(self):
        """行内译者注（【译者吐槽：…】【编注：…】）保留在 text（KN091 只删
        专长源数据级；race 行内吐槽是正文一部分，检索端不降权处理）"""
        items = run(
            "**气味信息素工具包（Trailscent Kit）**：这种装着特制猫族信息素的小盒子。"
            "【译者吐槽：卧了个大槽！尼玛这是喵星人还是汪星人啊！】\n"
        )
        assert items, "应产出条目"
        assert "译者吐槽" in item_text(items[0])


# ============ 簇 B：替换特性汇总（矮人真实形态） ============

CLUSTER_B = (
    "**矮人种族特性替换（Dwarf Alternate Racial \n"
    "Traits）**\n"
    "**此特性替换黑暗视觉**\n"
    "**昏暗视觉（Low-Light \n"
    "Vision）**\n"
    "**出自《荒野英雄 pg. \n"
    "5》**\n"
    "许多精类后裔拥有昏暗视觉。\n"
    "**此特性替换黑暗视觉，仇恨**\n"
    "**昏暗精准（Dusksight）**\n"
    "**出自《阴影血脉 \n"
    "pg. \n"
    "4》**\n"
    "一个常常在遮蔽中操作的人物学会了使用昏暗视觉推断敌人的位置。\n"
)


class TestClusterB:
    """簇 B：替换特性汇总"""

    def test_sentinel_line_becomes_replaces(self):
        """哨兵行 `**此特性替换黑暗视觉**` → 绑定到其后条目的 replaces

        KN135-3（2026-08-04）：replaces 剥「此特性替换」整句前缀——值只
        保留替换对象名（检索端按特性名匹配，前缀会污染对账）。"""
        items = run(CLUSTER_B)
        alts = [it for it in items if it["kind"] == "alt_trait"]
        assert len(alts) == 2, f"应产出 2 个替换特性，实际 {len(alts)}"
        it0, it1 = alts
        assert it0["name"] == "昏暗视觉"
        assert it0["replaces"] == "黑暗视觉"
        assert it1["name"] == "昏暗精准"
        assert it1["replaces"] == "黑暗视觉，仇恨"

    def test_sentinel_group_inherits_replaces(self):
        """组级哨兵：一个哨兵绑定一组条目（半身人汇总真实形态，15 哨兵 vs
        108 条目）——组内后续条目继承 replaces 直到下一哨兵覆盖（修复前
        绑定后清空，仅组首条目命中，半身人共享特性 replaces 错解析 5 条）"""
        raw = (
            "**半身人种族特性替换（Halfling Alternate Racial \n"
            "Trait）**\n"
            "**此特性替换无畏**\n"
            "**受福（Blessed）**\n"
            "**出自《恐怖冒险 pg. 40》**\n"
            "拥有此特性的半身人在对抗诅咒效果和巫术的豁免获得+2种族加值。此特性取代无畏。\n\n"
            "**避世的游牧民族（Evasive \n"
            "Nomad）**\n"
            "**出自《边缘英雄 pg. 28》**\n"
            "桑奥的半身人甚少在单个地方长大。此特性取代无畏。\n\n"
            "**此特性替换无畏，半身人幸运**\n"
            "**无法抑压（Irrepressible）**\n"
            "**出自《恐怖冒险 pg. 39》**\n"
            "正文。此特性替换无畏和半身人幸运。\n"
        )
        items = run(raw)
        alts = [it for it in items if it["kind"] == "alt_trait"]
        by_name = {it["name"]: it for it in alts}
        assert by_name["受福"]["replaces"] == "无畏"
        assert by_name["避世的游牧民族"]["replaces"] == "无畏", \
            f"组内第二条应继承哨兵: {by_name['避世的游牧民族']['replaces']!r}"
        assert by_name["无法抑压"]["replaces"] == "无畏，半身人幸运", \
            f"新哨兵应覆盖: {by_name['无法抑压']['replaces']!r}"

    def test_cross_line_source_line(self):
        """断行出自行 `**出自《荒野英雄 pg. \\n5》**` → source 归一单行"""
        items = run(CLUSTER_B)
        it0 = items[0]
        assert it0["source"] == "出自《荒野英雄 pg. 5》", f"出自行应合并断行：{it0['source']!r}"

    def test_source_line_not_in_text(self):
        """出自行只进 source 字段，不混入 text"""
        items = run(CLUSTER_B)
        for it in items:
            t = item_text(it)
            assert "出自《" not in t, f"出自行不应残留在 text：{t[:60]!r}"

    def test_quad_star_paren_not_elided(self):
        """`**援护防御****（****Defensive Aid, Ex****）**：…`（4 星+括号前是
        中文名——闭合标题+正文同行）→ 不拆行不包 elided（2026-08-04 回归：
        _fix_quad_star_halfparen 只认 `）****(X` 截断形态，守卫为 4 星前是
        `）`/`)`；page_160 灵动卫士能力被误拆 → 标题残片污染正文）"""
        raw = (
            "**灵动卫士（Nimble Guardian，武僧变体）**\n"
            "一些猫族武僧将他们优雅的力量奉献给他人。\n"
            "**援护防御****（****Defensive \n"
            "Aid, Ex****）**：2级起，每日“3+感知修正”次，灵动卫士可以干涉对于相邻盟友的攻击。\n"
            "**灵活反射（Nimble Reflexes, Ex）**：3级起，灵动卫士反射豁免+2。\n"
        )
        items = run(raw)
        names = [it["name"] for it in items]
        assert "援护防御" in names, f"援护防御应切出独立条目：{names}"
        it = [x for x in items if x["name"] == "援护防御"][0]
        t = item_text(it)
        assert "**" not in t, f"援护防御 text 不应含星壳：{t[:60]!r}"
        assert "Defensive Aid" in it.get("name_en", ""), f"name_en 应恢复：{it.get('name_en')!r}"

    def test_title_closing_star_not_in_text(self):
        """标题行 `**旧日之敌（Lasting Grudge）：**` 独立成行（page_752 拆行产物）
        → 组4 贪婪吞闭合星（`：**`），text 不得残留 `**`（2026-08-04 回归）；
        page_752 形态（组句前瞻）→ 条目为 alt_trait（KN131）"""
        raw = (
            "**矮人**\n"
            "矮人角色可以选择以下种族特性替换原本的种族特性。\n"
            "**旧日之敌（Lasting Grudge）：**\n"
            "有些矮人以他们可怕的记仇心而闻名。本特性替换防御训练和仇恨。\n"
            "**护城卫士（Siege Survivor）：**\n"
            "那些曾经居住在他们种族古老的天空城堡中的矮人从小就被训练。\n"
        )
        items = run(raw)
        # 组标题+组句前瞻（KN131）：组句后条目全部 alt_trait
        traits = [it for it in items if it["kind"] == "alt_trait"]
        assert len(traits) == 3, f"应产出 3 条 alt_trait（组标题+2 条目），实际 {len(traits)}"
        for it in traits[1:]:
            assert not it["text"].startswith("**"), (
                f"{it['name']} text 不应以 ** 开头：{it['text'][:40]!r}"
            )
            assert "**" not in item_text(it), f"text 不应残留星壳：{item_text(it)[:60]!r}"


# ============ 簇 C：天赋职业奖励 ============

CLUSTER_C = (
    "**矮人天赋职业奖励**（惧怖冒险HA）\n"
    "> 来源：惧怖冒险（Horror Adventures）HA，页码见原书\n"
    "下列奖励可以被矮人选取。\n"
    "**圣武士**：从游侠宿敌列表中选择一种生物类型，知识检定+1/2加值。\n"
    "**法师**：防护系法术的施法者等级+1/3。\n"
)


class TestClusterC:
    """簇 C：天赋职业奖励"""

    def test_fcb_bare_cn_entries(self):
        """纯中文加粗条目 `**圣武士**：…`（无英文名）→ fcb_entry"""
        items = run(CLUSTER_C)
        fcbs = [it for it in items if it["kind"] == "fcb_entry"]
        assert len(fcbs) == 2, f"应产出 2 个 FCB 条目，实际 {len(fcbs)}"
        assert fcbs[0]["name"] == "圣武士"
        assert "+1/2" in item_text(fcbs[0])
        assert fcbs[1]["name"] == "法师"
        assert "+1/3" in item_text(fcbs[1])

    def test_fcb_source_quote_block(self):
        """`> 来源：…` 引用块 → source 字段，不产条目"""
        items = run(CLUSTER_C)
        assert items, "应产出条目"
        # 引用块剥离进 source（首个条目携带或单独处理），text 不含 > 引用行
        all_text = "".join(item_text(it) for it in items)
        assert "> 来源" not in all_text, "引用块不应残留为正文"


# ============ 簇 D：怪物玩法扩展（霜巨人裸文本真实形态） ============

CLUSTER_D_FEAT = (
    "**霜巨人**\n"
    "> 来源：怪物志（Monster Codex）MC，页码见原书\n"
    "新规则霜巨人的能力发展于他们对极寒环境的长期适应。\n"
    "有仇报仇 Ancestral Enmity（战斗）  你熟知那些矬子对巨人的憎恨，并研究了针对这些家伙的战术\n"
    "先决条件：巨人生物亚种专长效果：你在对矮人或侏儒发动的近战攻击检定上获得+2加值。特殊情况：你可以多次选择本专长\n"
    "霜生种 Born of Frost  你身体萦绕的寒气足以冻伤其他生物\n"
    "先决条件：霜巨人专长效果：你的天生武器攻击可以造成1d6点额外的寒冷伤害。\n"
)

CLUSTER_D_ITEM = (
    "**霜巨人魔法物品**\n"
    "破雾目镜 Fog-Cutting Lenses装备位置：面部 灵光：中微弱变化系 施法者等级：5价格：8000GP 重量：1磅\n"
    "这套目镜的镜片是一对精细地手工打磨过的石英晶。\n"
    "制造条件：制造奇物，黑暗视觉，云雾术制造成本：4000GP\n"
)


class TestClusterD:
    """簇 D：怪物玩法扩展（霜巨人剥标记流式形态）"""

    def test_bare_flow_feat(self):
        """裸文本专长：`有仇报仇 Ancestral Enmity（战斗）  你熟知…`（中文+
        英文+类型+描述同段）→ race_feat，字段标签行并入 text"""
        items = run(CLUSTER_D_FEAT)
        feats = [it for it in items if it["kind"] == "race_feat"]
        assert feats, f"应产出裸文本专长条目：{items}"
        it = feats[0]
        assert it["name"] == "有仇报仇"
        assert it["name_en"] == "Ancestral Enmity"
        t = item_text(it)
        assert "你熟知那些矬子对巨人的憎恨" in t
        assert "先决条件" in t and "专长效果" in t

    def test_bare_flow_item(self):
        """裸文本奇物：`破雾目镜 Fog-Cutting Lenses装备位置：…灵光：…` →
        race_item，字段标签行并入 text"""
        items = run(CLUSTER_D_ITEM)
        items_list = [it for it in items if it["kind"] == "race_item"]
        assert len(items_list) == 1, f"应产出 1 个裸文本奇物，实际 {len(items_list)}"
        it = items_list[0]
        assert it["name"] == "破雾目镜"
        assert it["name_en"] == "Fog-Cutting Lenses"
        t = item_text(it)
        assert "装备位置" in t and "8000GP" in t


# ============ 簇 E：来源书替换特性（PA/BoS 形态） ============

CLUSTER_E_PA = (
    "# 暮行者 (Duskwalker)\n"
    "<!-- PA-source:新玩家种族/page_1488.md:暮行者 -->\n"
    "**暮行者 (Duskwalker)**\n"
    "> 来源：位面冒险（Planar Adventures），页码见原书\n"
    "[**http://45.79.87.129/bbs/index.php?topic=140162.0**](http://45.79.87.129/bbs/index.php?topic=140162.0)** **译者：unspeakable\n"
    "**暮行者（Duskwalker）**\n"
    "数据来源：[D20PFSRD](https://www.d20pfsrd.com/races/)\n"
    "暮行者是获得第二次生命荣耀的灵魂化身而成的类人生物。\n"
)

CLUSTER_E_BOS = (
    "**影生（Shadow-Born）**\n"
    "> 来源：阴影血脉（Blood of Shadows），页码见原书\n"
    "影生暗生：这些影生成员从影界获得了更多力量。\n"
    "血统之力：你的黑暗视觉提升为90尺。此特性替换黑暗视觉。\n"
)


class TestClusterE:
    """簇 E：来源书替换特性"""

    def test_pa_duplicate_titles_dedup(self):
        """PA 文件标题三重形态（# H1 / **半角** / **全角**）→ 合并为 1 个
        主条目，不产重复条目；H1/注释/译者行不残留 text"""
        items = run(CLUSTER_E_PA)
        intros = [it for it in items if it["kind"] == "race_intro"]
        assert len(intros) == 1, f"多重标题应合并为 1 个主条目，实际 {len(intros)}"
        it = intros[0]
        assert it["name"] == "暮行者"
        t = item_text(it)
        assert "# 暮行者" not in t, "H1 不应残留"
        assert "译者" not in t, "译者行不应残留"
        assert "暮行者是获得第二次生命荣耀的灵魂化身而成的类人生物。" in t

    def test_pa_english_source_dropped(self):
        """PA D20PFSRD 英文原文段（未翻译）剥离，避免检索污染"""
        items = run(CLUSTER_E_PA)
        assert items, "应产出条目"
        t = item_text(items[0])
        assert "Duskwalkers are tall" not in t, "英文原文不应进入 text"


# ============ 簇 F：概述页（page_10 表格真实形态） ============

CLUSTER_F_OVERVIEW = (
    "**种族概述（Races \n"
    "Overview）**\n"
    "| 种族 | 种族属性调整 | 生物类型 | 体型 | 速度 | 感官 |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
    "| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |\n"
    "| 核心种族 |\n"
    "| 矮人（Dwarves） |  |  | +2 |  | +2 | -2 | 类人生物 | 中型 | 20尺 | 黑暗视觉60尺 |\n"
    "| 精灵（Elves） |  | +2 | -2 | +2 |  |  | 类人生物 | 中型 | 30尺 | 昏暗视觉 |\n"
    "| 常见种族 |\n"
    "| 猫族（Catfolk） |  | +2 |  |  | -2 | +2 | 类人生物 | 中型 | 30尺 | 昏暗视觉 |\n"
)


class TestClusterF:
    """簇 F：概述页"""

    def test_overview_table_rows(self):
        """概述表数据行 → race_overview 条目：name/name_en + 属性调整六列
        组装为 ability_adj + 生物类型/体型/速度/感官 组装"""
        items = run(CLUSTER_F_OVERVIEW)
        rows = [it for it in items if it["kind"] == "race_overview"]
        assert len(rows) == 3, f"应产出 3 行概述条目（矮人/精灵/猫族），实际 {len(rows)}"
        dwarf = rows[0]
        assert dwarf["name"] == "矮人"
        assert dwarf["name_en"] == "Dwarves"
        assert dwarf["ability_adj"] == "+2体质，+2感知，-2魅力", \
            f"六列属性应组装：{dwarf['ability_adj']!r}"
        assert dwarf["bio_type"] == "类人生物"
        assert dwarf["size"] == "中型"
        assert dwarf["speed"] == "20尺"
        assert dwarf["senses"] == "黑暗视觉60尺"
        elf = rows[1]
        assert elf["ability_adj"] == "+2敏捷，-2体质，+2智力"
        cat = rows[2]
        assert cat["name"] == "猫族"
        assert cat["ability_adj"] == "+2敏捷，-2感知，+2魅力"

    def test_group_header_rows_skipped(self):
        """分组行（`| 核心种族 |`）不产条目"""
        items = run(CLUSTER_F_OVERVIEW)
        names = [it["name"] for it in items]
        assert "核心种族" not in names and "常见种族" not in names


# ============ 簇 F3：组标题/概念段（page_10 真实形态，KN134） ============

CLUSTER_F3_GROUP_TITLES = (
    "**种族概述（Races Overview）**\n"
    "| 种族 | 种族属性调整 | 生物类型 | 体型 | 速度 | 感官 |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
    "| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |\n"
    "| 矮人（Dwarves） |  |  | +2 |  | +2 | -2 | 类人生物 | 中型 | 20尺 | 黑暗视觉60尺 |\n"
    "**核心种族（Core Races）**\n"
    "种族是决定角色身份的重要部分。\n"
    "**矮人（Dwarves）**：这些粗矮而坚韧的山岭要塞防卫者们。\n"
    "**常见种族（Featured Races）**\n"
    "尽管七大核心种族是《寻路者》游戏的重中之重。\n"
    "**猫族（Catfolk）**：从机敏的猫族。\n"
)


class TestClusterF3GroupTitles:
    """簇 F3：page_10 组标题/概念段归位（KN134，2026-08-04）

    「种族概述」章节标题把 state 切 race_overview 后，带括号标题经
    _kind_for_title 直接映射 state → 组标题（核心种族/常见种族/罕见种族/
    整体描述）与各族介绍段全误标 race_overview。overview 条目语义 = 表
    数据行（_parse_overview_row 产出），带括号标题是介绍性文字 → intro。
    """

    def test_group_title_kind_is_intro(self):
        """组标题「核心种族/常见种族」→ race_intro（不再 race_overview）"""
        items = run(CLUSTER_F3_GROUP_TITLES)
        by_name = {it["name"]: it for it in items}
        assert by_name["核心种族"]["kind"] == "race_intro", \
            f"组标题应 race_intro: {by_name['核心种族']['kind']!r}"
        assert by_name["常见种族"]["kind"] == "race_intro", \
            f"组标题应 race_intro: {by_name['常见种族']['kind']!r}"

    def test_race_intro_paragraph_kind_is_intro(self):
        """各族介绍段标题（`**矮人（Dwarves）**：介绍`）→ race_intro
        （同详情页 intro 语义，不再是 overview 表条目）"""
        items = run(CLUSTER_F3_GROUP_TITLES)
        by_name = {it["name"]: it for it in items}
        intro = [it for it in by_name.values() if it["kind"] == "race_intro"]
        assert {it["name"] for it in intro} >= {"矮人", "猫族"}, \
            f"族介绍段应 race_intro: {[it['name'] for it in intro]}"

    def test_overview_rows_stay_overview(self):
        """表格数据行不受影响：仍 race_overview（属性调整组装不回归）"""
        items = run(CLUSTER_F3_GROUP_TITLES)
        rows = [it for it in items if it["kind"] == "race_overview"]
        assert len(rows) == 1, f"表格行应仍 1 条 overview: {[it['name'] for it in rows]}"
        assert rows[0]["name"] == "矮人"
        assert rows[0]["ability_adj"] == "+2体质，+2感知，-2魅力"

    def test_group_title_text_no_header_rows(self):
        """组标题 chunk text 不含概述表表头残留（`| 种族 |…`/`| 力量 |…`
        两表头行丢弃，不再 flush 进「核心种族」intro chunk）"""
        items = run(CLUSTER_F3_GROUP_TITLES)
        by_name = {it["name"]: it for it in items}
        text = by_name["核心种族"]["text"]
        assert text == "种族是决定角色身份的重要部分。", f"text 应纯介绍段: {text!r}"
        assert "|" not in text, f"表头行不得残留: {text[:60]!r}"


# ============ 簇 G：边栏（单段无标题） ============

CLUSTER_G = (
    "**非人类魔裔**\n"
    "> 来源：核心规则书，页码见原书\n"
    "魔裔是那些据说拥有凡人无法企及力量的存在。\n"
    "边栏：以下内容描述非人类魔裔的独特之处。\n"
)


CLUSTER_F2_REAL = (
    "**种族概述（Races Overview）**\n"
    "| 种族 | 种族属性调整 | 生物类型 | 体型 | 速度 | 感官 |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
    "| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |\n"
    "| 核心种族 | 矮人（Dwarves） |  |  | +2 |  | +2 | -2 | 类人生物 | 中型 | 20尺 | 黑暗视觉60尺 |\n"
    "| 精灵（Elves） |  | +2 | -2 | +2 |  |  | 类人生物 | 中型 | 30尺 | 昏暗视觉 |\n"
    "| 常见种族 | 神裔（Aasimar） |  |  | +2 |  | +2 | +2 | 类人生物 | 中型 | 30尺 | 黑暗视觉60尺 |\n"
    "| 半精灵（Half-Elves） | 任一属性+2 | 类人生物 | 中型 | 30尺 | 昏暗视觉 |\n"
    "| 人类（Humans） | 任一属性+2 | 类人生物 | 中型 | 30尺 | 无 |\n"
)


class TestClusterF2:
    """簇 F2：概述表真实形态（page_10 实测：分组词在数据行首格 + 6 格压缩行）"""

    def test_group_column_in_data_row(self):
        """真实 12 格行：`| 核心种族 | 矮人（Dwarves） | …` 分组词在首格 → 跳过分组格解析"""
        items = run(CLUSTER_F2_REAL)
        rows = {it["name"]: it for it in items if it["kind"] == "race_overview"}
        assert "矮人" in rows, f"带分组列行应产出矮人，实际 {list(rows)}"
        assert rows["矮人"]["ability_adj"] == "+2体质，+2感知，-2魅力"
        assert rows["矮人"]["bio_type"] == "类人生物"
        assert rows["矮人"]["size"] == "中型"
        assert rows["矮人"]["speed"] == "20尺"
        assert rows["矮人"]["senses"] == "黑暗视觉60尺"
        assert "神裔" in rows, f"常见种族分组行应产出神裔：{list(rows)}"
        assert rows["神裔"]["ability_adj"] == "+2体质，+2感知，+2魅力"

    def test_compact_six_cell_row(self):
        """真实 6 格压缩行：`| 半精灵（Half-Elves） | 任一属性+2 | 类人生物 | 中型 | 30尺 | 昏暗视觉 |`
        → 属性调整合并格 + 类型/体型/速度/感官"""
        items = run(CLUSTER_F2_REAL)
        rows = {it["name"]: it for it in items if it["kind"] == "race_overview"}
        half = rows["半精灵"]
        assert half["ability_adj"] == "任一属性+2"
        assert half["bio_type"] == "类人生物"
        assert half["size"] == "中型"
        assert half["speed"] == "30尺"
        assert half["senses"] == "昏暗视觉"
        human = rows["人类"]
        assert human["ability_adj"] == "任一属性+2"
        assert human["senses"] == "无"


CLUSTER_B2_TAIL_REPLACES = (
    "**矮人种族特性替换汇总**\n"
    "矮人角色可以选择以下种族特性替换原本的种族特性。\n"
    "  **旧日之敌（Lasting Grudge）：**有些矮人以他们可怕的记仇心而闻名。本特性替换防御训练和仇恨。\n"
    "  **护城卫士（Siege Survivor）：**那些曾经居住在天空城堡中的矮人从小就被训练。本特性替换贪婪，坚韧和仇恨。\n"
    "  **渣滓（Slag Child）：**那些失格家族出身的矮人常常被人唤作渣滓。本特性替换防御训练和仇恨。\n"
    "  **战豪（Unstoppable）：**有的矮人为了和他们的老对手交战而拼命训练。本特性替换坚韧。\n"
    "  **葡萄藤（Grapevine）：**一名由葡萄藤创造的藤蔓莱西可以长出灌注魔法的果实。该特性取代行踪无迹。\n"
    "  **残酷压迫（Cruel Tyranny）：**半兽人以恫吓震慑弱者。此种族特性替换夜行生物和自负。\n"
    "  **猫爪（Cat's Claws）：**猫族猎手生有利爪。这一种族特性取代狩猎本能。\n"
    "  **铁心（Iron Heart）：**矮人能以此特性替换防御训练。\n"
    "  **沼泽亲和（Marsh Affinity）：**沼泽莱西游刃有余。该特性取代了攀爬者并改变了朴素枝叶。\n"
    "  **猫落（Cat Fall）：**猫族落地总是双脚着地。这一族特性取代短跑健将。\n"
    "  **阴毒恶作剧（Vicious Prankster）：**侏儒专精战斗即兴创作。此族特性替换防御训练、仇恨和敏锐感官。\n"
)


class TestClusterB2:
    """簇 B2：描述尾部替换说明（无哨兵行形态）→ replaces 提取"""

    def test_tail_replaces_extracted(self):
        """「本特性替换XX。」/「该特性取代XX。」描述尾部 → replaces 字段"""
        items = run(CLUSTER_B2_TAIL_REPLACES)
        by_name = {it["name"]: it for it in items if it["kind"] == "alt_trait"}
        assert "旧日之敌" in by_name
        assert by_name["旧日之敌"]["replaces"] == "防御训练和仇恨"
        assert by_name["战豪"]["replaces"] == "坚韧"
        assert by_name["护城卫士"]["replaces"] == "贪婪，坚韧和仇恨"
        # 该特性取代（page_1456 莱西形态）
        assert by_name["葡萄藤"]["replaces"] == "行踪无迹"
        # 此种族特性替换 / 这一种族特性取代 / 能以…特性替换（真实源数据形态）
        assert by_name["残酷压迫"]["replaces"] == "夜行生物和自负"
        assert by_name["猫爪"]["replaces"] == "狩猎本能"
        assert by_name["铁心"]["replaces"] == "防御训练"
        # 「并」尾巴停靠：replaces 只取替换目标，不吞后续说明
        assert by_name["沼泽亲和"]["replaces"] == "攀爬者"
        # 「族特性」形态（无「种」字）
        assert by_name["猫落"]["replaces"] == "短跑健将"
        assert by_name["阴毒恶作剧"]["replaces"] == "防御训练、仇恨和敏锐感官"

    def test_tail_replaces_does_not_swallow_text(self):
        """replaces 提取只读描述尾部，text 完整保留（不被裁剪）"""
        items = run(CLUSTER_B2_TAIL_REPLACES)
        by_name = {it["name"]: it for it in items}
        assert "本特性替换防御训练和仇恨。" in by_name["旧日之敌"]["text"], \
            "text 应完整保留替换说明（replaces 是派生字段，不裁剪正文）"


class TestClusterG:
    """簇 G：边栏/单条目整理页"""

    def test_sidebar_entry(self):
        """边栏单段 → race_sidebar（降权）"""
        items = run(CLUSTER_G)
        assert items, "应产出条目"
        it = items[0]
        assert it["kind"] == "race_sidebar"
        assert "非人类魔裔" in it["name"]
        assert "边栏" in item_text(it)


# ============ 簇 H：ISR 替换特性页（~~删除线壳/4星粘连/无星条目/——双名） ============

CLUSTER_H_ISR_CORE = (
    "**~~矮人****矮人角色可以选择以下种族特性替换原本的种族特性。\n"
    "\n"
    "  旧日之敌（****Lasting \n"
    "Grudge****）：**有些矮人以他们可怕的记仇心而闻名。本特性替换防御训练和仇恨。**\n"
    "\n"
    "**~~精灵****精灵角色可以选择以下种族特性替换原本的种族特性。\n"
    "\n"
    "  元素亲和（****Elemental \n"
    "Acolyte****）：**精灵自幼便会与元素的力量相伴。本特性替换精灵魔法。**\n"
)

CLUSTER_H_ISR_OTHER = (
    "**神裔——圣战魔法（Aasimars—Crusading \n"
    "Magic）：**许多神裔都觉得有义务受训以对抗魔族。这些神裔在克服法术抗力的\n"
    "施法者等级和知识〔位面〕检定获得+2种族加值。此种族特性替换技能奖励和类法术能力。**\n"
)


class TestClusterH_ISR:
    """簇 H：ISR 替换特性页（内海种族 ISR 形态）

    类名带 _ISR 后缀——本文件 834 行另有 `TestClusterH`（簇 H2 系列补充），
    重名会被后定义覆盖导致本簇测试静默不跑（2026-08-04 发现）。
    """

    def test_strike_shell_and_quad_glue_titles(self):
        """`**~~矮人****矮人…` 删除线壳 + 4 星粘连 → 节标题独立切出；
        组句前瞻（KN131）→ 组标题 alt_trait"""
        items = run(CLUSTER_H_ISR_CORE)
        sides = [it for it in items if it["kind"] == "alt_trait"]
        # 2 组标题 + 2 条目（矮人 1 + 精灵 1）全部 alt_trait
        assert len(sides) == 4, f"应产出 4 条 alt_trait（2 组标题+2 条目），实际 {len(sides)}"
        assert sides[0]["name"] == "矮人"
        assert "~~" not in sides[0]["name"]
        assert "~~" not in item_text(sides[0])

    def test_indented_starless_entries(self):
        """`  旧日之敌（EN）：**` 无开头星缩进条目 → 补星切出独立条目（alt_trait）"""
        items = run(CLUSTER_H_ISR_CORE)
        traits = [it for it in items if it["kind"] == "alt_trait"]
        assert len(traits) == 4, f"应产出 4 条 alt_trait，实际 {len(traits)}"
        it = traits[1]
        assert it["name"] == "旧日之敌"
        assert it["name_en"] == "Lasting Grudge"
        assert "**" not in it["text"], f"text 不应残留星壳：{it['text']!r}"
        assert "本特性替换防御训练和仇恨" in item_text(it)

    def test_dash_double_name_title(self):
        """`**中文——特性名（EN）：**` 双名标题 → `——` 保留为条目名

        intro 态首个带括号标题 → race_intro（既定行为），`——` 不拆分。
        """
        items = run(CLUSTER_H_ISR_OTHER)
        traits = [it for it in items if it["kind"] == "race_intro"]
        assert len(traits) == 1, f"应切出 1 条，实际 {len(traits)}"
        it = traits[0]
        assert it["name"] == "神裔——圣战魔法"
        assert it["name_en"] == "Aasimars—Crusading Magic"
        assert "**" not in it["text"]


# ============ 簇 I：page_11 年龄/身高体重表（无括号表行 + 岁/寸判定） ============

CLUSTER_I_AGE_TABLE = (
    "**年龄（****Age****）******\n"
    "你可以自行选择或者随机生成角色的年龄。\n"
    "| 核心种族 | 矮人 | 40岁 | +3d6 | +5d6 | +7d6 | 125岁 | 188岁 | 250岁 | 250+2d100岁 |\n"
    "| 精灵 | 110岁 | +4d6 | +6d6 | +10d6 | 175岁 | 263岁 | 350岁 | 350+4d100岁 |\n"
    "| 侏儒 | 40岁 | +4d6 | +6d6 | +9d6 | 100岁 | 150岁 | 200岁 | 200+3d100岁 |\n"
)

CLUSTER_I_HEIGHT_TABLE = (
    "**身高和体重（****Height \n"
    "and Weight****）******\n"
    "要想确立一名角色的身高，需要按照表格选择适当的修正值投掷对应的骰数。\n"
    "| 常见种族 | 火元素裔 | 5尺2寸 | 110磅 | 2d8 | ×5磅 | 5尺0寸 | 90磅 | 2d8 | ×5磅 |\n"
    "| 狗头人 | 2尺6寸 | 25磅 | 2d4 | ×1磅 | 2尺4寸 | 20磅 | 2d4 | ×1磅 |\n"
)


class TestClusterI:
    """簇 I：page_11 年龄/身高体重表行（race_overview）"""

    def test_age_table_rows(self):
        """年龄表数据行（9 格含「岁」）→ race_overview，带组别前缀行（裸中文次格）同解析"""
        items = run(CLUSTER_I_AGE_TABLE)
        rows = [it for it in items if it["kind"] == "race_overview"]
        assert len(rows) == 3, f"应产出 3 行（矮人/精灵/侏儒），实际 {len(rows)}"
        dwarf = rows[0]
        assert dwarf["name"] == "矮人"
        assert "随机起始年龄：40岁" in dwarf["text"], f"起始年龄应可检索：{dwarf['text']!r}"
        assert "中年：125岁" in dwarf["text"]
        assert "最大年龄：250+2d100岁" in dwarf["text"]
        names = [it["name"] for it in rows]
        assert "核心种族" not in names, "分组词不得产出"

    def test_height_table_rows(self):
        """身高体重表数据行（9 格含「寸」）→ race_overview"""
        items = run(CLUSTER_I_HEIGHT_TABLE)
        rows = [it for it in items if it["kind"] == "race_overview"]
        assert len(rows) == 2, f"应产出 2 行，实际 {len(rows)}"
        fire = rows[0]
        assert fire["name"] == "火元素裔"
        assert "男性基础身高：5尺2寸" in fire["text"], f"身高应可检索：{fire['text']!r}"
        assert "女性体重乘数：×5磅" in fire["text"]


class TestClusterKN131:
    """簇 KN131：page_752 替换特性组标题前瞻（裸分组标题 + 组句 → alt_trait 态）"""

    def test_group_title_lookahead_alt_trait(self):
        """`**矮人**` 组标题 + 下一行组句「X角色可以选择以下种族特性替换原本的种族
        特性。」→ 组标题与条目全部 alt_trait——聚合文件（内海种族ISR_核心种族
        替换特性）靠 `## 核心种族替换特性` 章节切 alt_trait，页文件 page_752
        无章节标题致 52 条误标 race_trait（KN131）"""
        items = run(
            "**矮人**\n"
            "矮人角色可以选择以下种族特性替换原本的种族特性。\n"
            "**旧日之敌（Lasting Grudge）：**有些矮人以他们可怕的记仇心而闻名。"
            "本特性替换防御训练和仇恨。\n"
            "**护城卫士（Siege Survivor）：**那些曾经居住在他们种族古老的天空城堡"
            "中的矮人。本特性替换贪婪，坚韧和仇恨。\n"
        )
        alt = [it for it in items if it["kind"] == "alt_trait"]
        assert len(alt) == 3, f"应产出 3 条 alt_trait（组标题+2 条目），实际 {len(alt)}"
        group = alt[0]
        assert group["name"] == "矮人"
        assert "矮人角色可以选择以下种族特性替换原本的种族特性" in group["text"]
        assert alt[1]["name"] == "旧日之敌"
        assert "防御训练和仇恨" in alt[1].get("replaces", "")
        assert alt[2]["name"] == "护城卫士"
        kinds = [it["kind"] for it in items]
        assert "race_trait" not in kinds and "race_sidebar" not in kinds


class TestClusterKN131_P398:
    """簇 KN131-页文件：page_398 半精灵替换特性汇总页（链接形态章节标题）

    页文件形态与聚合文件同构但标题为加粗链接行
    `**[半精灵种族特性替换（Alternate Racial Traits）汇总](http://…)**`
    （锚=中文正文）。base._strip_url_lines 第三正则把加粗链接行整行剥空
    → 标题消失 → 整章落默认态（1 intro + 19 race_trait，KN131 页文件漏网）。
    """

    def test_link_anchor_section_title_alt_trait(self):
        """链接章节标题（锚=中文）+ 条目 → 全部 alt_trait，URL 不残留"""
        items = run(
            "**[半精灵种族特性替换（Alternate \r\n"
            "Racial Traits）汇总](http://www.golarian.com/races/half-elf.php)**\n"
            "**海之子（Child of the Sea）：**半精灵游荡在风浪之中。本特性替换\n"
            "多才多艺。\n"
        )
        assert items, "应产出条目"
        alts = [it for it in items if it["kind"] == "alt_trait"]
        assert alts, f"链接章节标题应切 alt_trait 态：{[it['kind'] for it in items]}"
        assert alts[0]["name"] == "海之子", alts[0]["name"]
        assert "http" not in item_text(alts[0])
        assert all(it["kind"] != "race_trait" for it in items)


class TestClusterH2:
    """簇 H2：章节关键字只查标题串（描述含关键字不误判）"""

    def test_description_keyword_not_section(self):
        """`**吸血裔——吸血鬼猎手（EN）：**…类法术能力…` 描述含「法术」——
        关键字只查标题串 → race_trait 而非 race_spell（2026-08-04 修复）"""
        items = run(
            "**吸血裔——吸血鬼猎手（Vampire Hunters—Bloodline）：**许多吸血裔\n"
            "都会训练自身以猎杀同类。这些吸血裔获得+2加值。此种族特性替换\n"
            "吸血者的弱点，如同类法术能力一般释放。**\n"
        )
        kinds = [it["kind"] for it in items]
        assert "race_spell" not in kinds, f"描述含法术字样不得判 race_spell：{kinds}"
        assert kinds == ["race_intro"]


class TestClusterH3:
    """簇 H3：`~~~~` 删除线包整条标题（ISR 尖耳朵形态）"""

    def test_tilde_wrapped_entry_title(self):
        """`~~~~尖耳朵（~~****~~Eleven Arrogance~~****~~）~~****~~：**…`——
        剥 `~~` 后 `）****：` 4 星粘连：`_fix_quadruple_star` 不得拆行、
        `_RE_TITLE` 括号后容 4 星 → 独立条目且 text 无星壳无波浪线；
        组句前瞻（KN131）→ 尖耳朵为 alt_trait"""
        items = run(
            "**~~精灵****精灵角色可以选择以下种族特性替换原本的种族特性。\n"
            "\n"
            "  ~~~~尖耳朵（~~****~~Eleven \n"
            "Arrogance~~****~~）~~****~~：**有些精灵如此相信他们种族的不凡之处。\n"
            "本特性替换精灵魔法和敏锐感官。**\n"
        )
        traits = [it for it in items if it["kind"] == "alt_trait"]
        assert len(traits) == 2, f"应产出 2 条 alt_trait（组标题+尖耳朵），实际 {len(traits)}"
        it = traits[1]
        assert it["name"] == "尖耳朵"
        assert it["name_en"] == "Eleven Arrogance"
        t = it["text"]
        assert "**" not in t and "~" not in t, f"text 不应残留星壳/波浪线：{t!r}"
        assert "有些精灵如此相信他们种族的不凡之处" in t


class TestClusterH4:
    """簇 H4：`出自《X》` 出自行裸行/英文括号形态（source 提取）"""

    def test_bare_source_line(self):
        """裸行 `出自《Ultimate Wilderness pg. 23》`（normalize 剥星后无星壳）
        → 仍进 source 字段、不落正文（page_1456 形态）"""
        items = run(
            "**莱西操念使（Leshy Kineticist）**\n"
            "出自《Ultimate Wilderness pg. 23》\n"
            "植语者的具有影响心灵效果的诗人法术。\n"
        )
        assert items, "应产出条目"
        assert items[0]["source"] == "出自《Ultimate Wilderness pg. 23》", (
            f"裸行出自行应提取：{items[0]['source']!r}"
        )
        assert "出自《" not in item_text(items[0]), "出自行不应残留在 text"

    def test_source_line_with_en_paren(self):
        """`出自《位面冒险》（Planar Adventures）`（书名后英文括号）→ source
        保留完整书名字面（PA 熵裔/秩裔形态，全库 3 行）"""
        items = run(
            "**熵裔（Aphorite）**\n"
            "出自《位面冒险》（Planar Adventures）\n"
            "熵裔是一群生活在轴心城的生物。\n"
        )
        assert items, "应产出条目"
        assert items[0]["source"] == "出自《位面冒险》（Planar Adventures）", (
            f"英文括号应保留：{items[0]['source']!r}"
        )


# ============ 簇 H：整理页 H2/裸标题/行内标题形态（verify 判别器回归揪出的 14 文件） ============

CLUSTER_H_H2_BARE = (
    "## 剪影人\n"
    "> 来源：阴影血脉（Blood of Shadows），页码见原书，未整理 → 阴影血脉BoS → 替换种族特性\n"
    "光明转化\n"
    "在黑暗纪元的末尾，剪影人的历史被孤独的悲哀所感染。\n"
    "**此特性替换短跑健将**\n"
    "**暗影亲和（Shadow Affinity）：**剪影人可以暗中潜行。此特性替换短跑健将。\n"
)

CLUSTER_H_H2_PAREN = (
    "## 格拉里昂的侏儒 脱色症（The Bleaching）\n"
    "**类型**：诅咒；**豁免**：意志检定可中止或逆转（见下文）\n"
    "**效果**：步入中年后，任何被GM判定其没有充分寻求新奇体验的侏儒都面临脱色风险。\n"
)

CLUSTER_H_H2_PAREN_TAG = (
    "## 半身人霉咒（Halfling Jinx）【种族特性】\n"
    "你失去半身人幸运这个特性（即失去豁免上的+1种族加值）。\n"
)

CLUSTER_H_FULLWIDTH_SPACE = (
    "由灰烬鬼婆的邪恶行径诞生的替换儿往往有灰色眼睛。灰烬鬼婆的女儿可以使用以下特质作为她的种族特质。\n"
    "**　　嗜火者（Pyrophile）**：当使用具有火焰描述符的法术时，替换儿在伤害掷骰上获得＋1种族加值。\n"
)

CLUSTER_H_BARE_PAREN_COLON = (
    "可选天赋职业奖励（Favored Class Options）\n"
    "以下职业在狗头人章节中没有涉及。\n"
    "野蛮人（Barbarian）：狂暴时，你的种族天生武器造成的伤害增加1/4。\n"
    "法师（Wizard）：你的魔宠对抗魅惑效果的意志检定上增加1/2。\n"
)

CLUSTER_H_INLINE_TITLES = (
    "翼龙人(Wyvaran)角色翼龙人的HD基于他们的职业等级。\n"
    "**中型龙类：**翼龙人是中型体型的龙类生物。**飞行（Flight）**：翼龙人有着龙一般的翅膀。\n"
    "故事背景待补充**种族特性替换**以下种族特性可以被选择用来替换翼龙人的种族特性。**贪婪（Greed）**：大部分翼龙人渴求财宝。**此特性取代扫尾（slapping tail）。**\n"
    "**天赋职业奖励**下列选择可用于所有拥有列表中天赋职业的翼龙人。**血脉狂怒者**：每天增加1轮血怒。\n"
)

CLUSTER_H_STAR_CN_EN = (
    "翼龙人专长翼龙人由于他们独特的生理机能和龙族文化的影响，可以使用下列的专长。\n"
    "**巢穴守卫者 Brood Defender**当某人在你的保护之下被袭击时，你立刻反抗攻击者。\n"
    "**先决条件**：保镖APG，战斗反射，翼龙人\n"
    "**专长效果**：如果一个盟友躲过了敌人的攻击，你可以尝试威吓检定。\n"
)


class TestClusterH:
    """簇 H：整理页标题形态（H2/裸标题/星后全角空格/行内标题/星内中文+EN）"""

    def test_h2_bare_cn_title(self):
        """`## 剪影人`（H2 裸中文）→ 条目 + 哨兵行 replaces + 出自行"""
        items = run(CLUSTER_H_H2_BARE)
        by_name = {it["name"]: it for it in items}
        assert "剪影人" in by_name, f"H2 裸中文应成条目，实际: {[it['name'] for it in items]}"
        assert "阴影血脉" in by_name["剪影人"]["source"]  # `> 来源：` 行原串绑定（split 既有口径）
        assert by_name["暗影亲和"]["replaces"] == "短跑健将"  # 哨兵行剥前缀口径（KN135-3）

    def test_h2_paren_title(self):
        """`## 中文（EN）`（H2 带括号）→ 条目，name_en 提取"""
        items = run(CLUSTER_H_H2_PAREN)
        by_name = {it["name"]: it for it in items}
        assert "格拉里昂的侏儒 脱色症" in by_name or "脱色症" in by_name
        it = next(v for k, v in by_name.items() if "脱色症" in k)
        assert it["name_en"] == "The Bleaching"
        # 字段行并入 text、星壳保留（A 簇既有口径：`**体貌描述**：…` 同形态
        # 断言在 text——字段标记是正文一部分，检索保留）
        assert "**效果**：步入中年后" in it["text"]

    def test_h2_paren_with_tag(self):
        """`## 中文（EN）【种族特性】`（H2 带括号+类型标签）→ 条目"""
        items = run(CLUSTER_H_H2_PAREN_TAG)
        assert items, "H2 带括号+标签应产出条目"
        assert items[0]["name"].endswith("霉咒")

    def test_fullwidth_space_after_star(self):
        """`**　　嗜火者（Pyrophile）**`（星后全角空格）→ 条目"""
        items = run(CLUSTER_H_FULLWIDTH_SPACE)
        by_name = {it["name"]: it for it in items}
        assert "嗜火者" in by_name, f"星后全角空格应成条目: {[it['name'] for it in items]}"
        assert by_name["嗜火者"]["name_en"] == "Pyrophile"

    def test_bare_paren_colon_title(self):
        """`野蛮人（Barbarian）：正文`（裸中文（EN）：无星）→ FCB 条目"""
        items = run(CLUSTER_H_BARE_PAREN_COLON)
        by_name = {it["name"]: it for it in items}
        assert "野蛮人" in by_name, f"裸中文（EN）：应成条目: {[it['name'] for it in items]}"
        assert by_name["野蛮人"]["kind"] == "fcb_entry"
        assert by_name["法师"]["kind"] == "fcb_entry"

    def test_inline_star_titles_split(self):
        """行内星包裹标题（`…**贪婪（Greed）**：…`）→ 拆行成独立条目"""
        items = run(CLUSTER_H_INLINE_TITLES)
        by_name = {it["name"]: it for it in items}
        assert "贪婪" in by_name, f"行内标题应拆出条目: {[it['name'] for it in items]}"
        assert by_name["贪婪"]["replaces"] == "扫尾（slapping tail）" or by_name["贪婪"]["replaces"].startswith("扫尾")
        assert "飞行" in by_name, "行内 **飞行（Flight）** 应成条目"
        assert "血脉狂怒者" in by_name, "行内 **血脉狂怒者** 应成条目（fcb）"

    def test_star_cn_en_title(self):
        """`**巢穴守卫者 Brood Defender**正文`（星内中文+EN 无括号）→ 条目"""
        items = run(CLUSTER_H_STAR_CN_EN)
        by_name = {it["name"]: it for it in items}
        assert "巢穴守卫者" in by_name, f"星内中文+EN 应成条目: {[it['name'] for it in items]}"
        assert by_name["巢穴守卫者"]["name_en"] == "Brood Defender"
        assert by_name["巢穴守卫者"]["kind"] == "race_feat"


# ============ 簇 J：page_1456 聚合页形态（UW/WO 来源标记 + 字段行 + 裸小节标题） ============
# 2026-08-04 产出巡检发现。「其他种族」聚合页 page_1456 的 4 类形态：
#   J1 UW/WO 来源标记：`**葡萄藤（Grapevine）**UW：…` / `**炼金术士**UW：…`
#      ——UW=《Ultimate Wilderness》、WO=《Wilderness Origins》逐条标记，
#      应转为标准冒号 `：`（判定保留，标记不残留 text）
#   J2 毒药块字段行：`…；**豁免** 强韧DC…；**效果** 恶心1轮；…`
#      ——`**标签** 值`（星后空格）是字段行不是标题，不得拆行（并入当前条目）
#   J3 裸小节标题：`藤蔓莱西装备` / `藤蔓莱西专长` / `藤蔓莱西法术` 独立行
#      ——tail 空形态，应转星标题并驱动 state 切换（race_item/race_feat/race_spell）
#   J4 小节标题关键字：「种族变体职业与职业能力」→ race_archetype（含「变体职业」）

CLUSTER_J_UW_MARKERS = (
    "**种族特性替换**（已整合，来源已注明）\n"
    "**葡萄藤（Grapevine）**UW：一名由葡萄藤创造的藤蔓莱西可以长出灌注魔法的果实用以治愈盟友。该特性取代行踪无迹。\n"
    "**藤鞭（Vine Whip）**WO：一些藤蔓莱西能长出鞭状的附属物。该特性取代攀爬者。\n"
)

CLUSTER_J_FCB_UW = (
    "**天赋职业奖励**（已整合，来源已注明）\n"
    "**炼金术士**UW：在突变药剂生效时，在天生防御上1/4点加值。\n"
    "**吟游诗人**UW：在表演（演讲）中获得+1/3加值。\n"
    "**变形者**WO：在有关植物的知识（自然）检定中+1加值。\n"
)

CLUSTER_J_POISON_FIELDS = (
    "**毒性（Poisonous）**UW：由有毒的常春藤藤蔓创造的藤蔓莱西体内含有天然毒素。该莱西下一次用徒手攻击一个生物时，该生物会受到以下毒药的影响。\n"
    "*莱西毒素*：徒手打击-伤口；**豁免** 强韧DC 10+该藤蔓莱西HD的一半+该莱西体质调整值；**发作频率** 1/每轮 持续6轮；**效果** 恶心1轮；**治愈** 1次豁免。\n"
    "一名藤蔓莱西每天可以使用这个能力的次数等于它的体质调整值（最少1次）。该特性取代树语者与变身。\n"
)

CLUSTER_J_BARE_SECTIONS = (
    "**种族变体职业与职业能力**\n"
    "以下变体和职业能力被藤蔓莱西及具有莱西亚种的其他角色选用。\n"
    "**草药学（Herbalism）**：植者的研究让他以独特方式制作炼金术发现。\n"
    "**自然魔法（Natural Magic）**：植者对的莱西精魄研究给予他接触其他炼金术师无法企及的自然魔法。\n"
    "藤蔓莱西装备\n"
    "藤蔓莱西拥有获取以下装备的渠道。\n"
    "**驱兽剂**：这种炼金术肥料能保护植物。\n"
    "藤蔓莱西专长\n"
    "藤蔓莱西可以获得以下专长。\n"
    "**攀爬藤蔓**：你像藤蔓一般在所有生物周围环绕。\n"
    "藤蔓莱西法术\n"
    "藤蔓莱西可以获得以下法术。\n"
    "**抓握藤蔓**：你能够控制藤蔓抓握。\n"
)


class TestClusterJ:
    """簇 J：page_1456 聚合页形态（UW/WO 标记 / 字段行 / 裸小节标题）"""

    def test_uw_wo_marker_stripped_from_alt_trait(self):
        """`**X（EN）**UW：正文` 来源标记 → 转标准冒号，不残留 text"""
        items = run(CLUSTER_J_UW_MARKERS)
        by_name = {it["name"]: it for it in items if it["kind"] == "alt_trait"}
        assert "葡萄藤" in by_name, f"UW 替换特性应成条目: {[it['name'] for it in items]}"
        assert "UW" not in (by_name["葡萄藤"].get("text") or ""), \
            f"UW 标记不应残留 text: {by_name['葡萄藤'].get('text')!r}"
        assert by_name["葡萄藤"]["replaces"] == "行踪无迹"
        assert "藤鞭" in by_name, f"WO 替换特性应成条目: {[it['name'] for it in items]}"
        assert "WO" not in (by_name["藤鞭"].get("text") or ""), \
            f"WO 标记不应残留 text: {by_name['藤鞭'].get('text')!r}"

    def test_uw_wo_marker_in_fcb_entry(self):
        """`**职业**UW：奖励` FCB 形态 → fcb_entry，标记不残留"""
        items = run(CLUSTER_J_FCB_UW)
        by_name = {it["name"]: it for it in items if it["kind"] == "fcb_entry"}
        assert "炼金术士" in by_name, f"FCB 条目应成条目: {[it['name'] for it in items]}"
        assert "吟游诗人" in by_name
        assert "变形者" in by_name
        for name in ("炼金术士", "吟游诗人", "变形者"):
            assert "UW" not in (by_name[name].get("text") or "") and \
                "WO" not in (by_name[name].get("text") or ""), \
                f"{name} 来源标记不应残留: {by_name[name].get('text')!r}"
        assert by_name["炼金术士"]["text"].startswith("在突变药剂生效时")

    def test_poison_block_fields_stay_in_entry(self):
        """毒药块 `**豁免** 强韧DC…`（星后空格字段行）→ 并入条目，不拆行"""
        items = run(CLUSTER_J_POISON_FIELDS)
        by_name = {it["name"]: it for it in items}
        assert "毒性" in by_name, f"毒性条目应存在: {[it['name'] for it in items]}"
        text = by_name["毒性"].get("text") or ""
        assert "**豁免** 强韧DC" in text, f"豁免字段行应并入毒性 text: {text!r}"
        assert "**效果** 恶心1轮" in text, f"效果字段行应并入毒性 text: {text!r}"
        # 字段行不得拆成独立条目
        for label in ("豁免", "发作频率", "效果", "治愈"):
            assert label not in by_name, f"{label} 是字段行，不得成独立条目: {[it['name'] for it in items]}"
        assert "UW" not in text, f"UW 标记不应残留: {text!r}"

    def test_bare_section_titles_drive_state(self):
        """裸小节标题（装备/专长/法术）+ 变体职业标题 → 驱动 state 切换"""
        items = run(CLUSTER_J_BARE_SECTIONS)
        by_name = {it["name"]: it for it in items}
        # 种族变体职业标题 → race_archetype 态，后续条目 race_archetype
        assert "草药学" in by_name, f"变体职业条目应成条目: {[it['name'] for it in items]}"
        assert by_name["草药学"]["kind"] == "race_archetype", \
            f"变体职业条目应是 race_archetype，实际 {by_name['草药学']['kind']}"
        assert by_name["自然魔法"]["kind"] == "race_archetype"
        # 裸行「藤蔓莱西装备」→ 转标题 + 切 race_item 态（章节标题只切态不产条目）
        assert "藤蔓莱西装备" not in by_name, \
            f"章节标题不产条目: {[it['name'] for it in items]}"
        assert by_name["驱兽剂"]["kind"] == "race_item", \
            f"装备小节条目应是 race_item，实际 {by_name['驱兽剂']['kind']}"
        # 裸行「藤蔓莱西专长」→ race_feat 态
        assert "藤蔓莱西专长" not in by_name
        assert by_name["攀爬藤蔓"]["kind"] == "race_feat", \
            f"专长小节条目应是 race_feat，实际 {by_name['攀爬藤蔓']['kind']}"
        # 裸行「藤蔓莱西法术」→ race_spell 态
        assert "藤蔓莱西法术" not in by_name
        assert by_name["抓握藤蔓"]["kind"] == "race_spell", \
            f"法术小节条目应是 race_spell，实际 {by_name['抓握藤蔓']['kind']}"

# ============ 簇 K：分配表内 0 产出文件形态修复（2026-08-04） ============
# 背景：判别器回归（race_per_file.jsonl est ↔ got）发现 6 个分配表内文件整文件
# 0 产出——format 层只认「纯中文（EN）」窄标题形态，以下形态全漏：
#   K1 边栏标题含全角冒号「：」（边栏：非人类魔裔/神裔，est=1+1）
#   K2 组1 前全角空格（切利亚斯CtIE `**　　嗜火者（Pyrophile）**：`，est=1）
#   K3 混排中文+英文标题 + 超长单行 8 亚种（page_806 兽态人，est=9）
# 修复点：_RE_TITLE/_RE_BARE_CN_TITLE/_RE_INLINE_STAR_TITLE 组1 字符集扩展
# （允许英文/数字/全角冒号/全角空格）。
# 豁免登记（裸文本形态切条不可靠，KN 另记）：page_812 阿斯托莫伊人（est=1）、
# 阴影血脉BoS 影生暗生特性（est=10）。

CLUSTER_K1_SIDEBAR = (
    "**边栏：非人类魔裔（Blood of Fiends）**\n"
    "外层位面最深处的造物并未将他们的污秽混血局限于人类。\n"
    "需要注意的是，虽然任何与魔族孕育后代的动物或怪物均可诞下半炼狱子嗣。\n"
    "就游戏而言，非人类魔裔和人类魔裔仅在体型上有所区别。\n"
)


class TestClusterK1:
    """边栏标题（组1 含「：」）→ 产 1 条目"""

    def test_sidebar_title_with_colon(self):
        items = run(CLUSTER_K1_SIDEBAR)
        assert len(items) == 1, f"边栏文件应产 1 条目: {[it['name'] for it in items]}"
        it = items[0]
        assert it["name"] == "边栏：非人类魔裔", f"name 应为边栏标题: {it['name']!r}"
        assert it["kind"] in ("race_intro", "race_sidebar"), \
            f"边栏条目 kind 应为 race_intro/race_sidebar: {it['kind']}"
        assert "污秽混血" in (it.get("text") or ""), \
            f"正文应并入边栏条目: {it.get('text')!r}"


CLUSTER_K2_CTIE = (
    "由灰烬鬼婆的的邪恶行径诞生的替换儿往往有一个明显的灰色眼睛。\n"
    "灰烬鬼婆的女儿可以使用以下特质作为她的种族特质。"
    "**　　嗜火者（Pyrophile）**：当使用具有火焰描述符的法术时，"
    "替换儿在伤害掷骰上获得＋1种族加值。\n"
)


class TestClusterK2:
    """行中星标题（组1 前全角空格）→ 产 1 条目"""

    def test_inline_title_with_fullwidth_space(self):
        items = run(CLUSTER_K2_CTIE)
        assert len(items) >= 1, f"应产出条目: {[it['name'] for it in items]}"
        names = [it["name"] for it in items]
        assert "嗜火者" in names, f"嗜火者应成条目: {names}"
        it = next(x for x in items if x["name"] == "嗜火者")
        assert "火焰描述符" in (it.get("text") or ""), \
            f"正文应并入嗜火者: {it.get('text')!r}"


CLUSTER_K3_SKINWALKER = (
    "**兽态人Skinwalker种族特性**（10RP）\n"
    "兽态人是类人生物，兽态人和变形生物。\n"
    "**蝙蝠人后裔Werebat－kin（血印bloodmarked）**先祖：蝙蝠人"
    "典型阵营：中立邪恶替换属性调整值：＋2智力，－2感知（变形时＋2敏捷）"
    "替换技能加值：飞行，夜晚时的察觉。\n"
    "**熊人后裔Werebear－kin（冷嗣Coldborn）**先祖：熊人"
    "典型阵营：秩序善良替换属性调整值：＋2体质，－2魅力（变形时＋2感知）"
    "替换技能加值：攀爬，野性认同。\n"
    "**野猪人后裔Wereboar－kin（怒孽Ragebred）**先祖：野猪人"
    "典型阵营：混乱中立替换属性调整值：＋2感知，－2魅力（变形时＋2体质）\n"
)


class TestClusterK3:
    """混排英文标题 + 超长单行 → 主条目 + 亚种各自成条目"""

    def test_mixed_en_titles_split(self):
        items = run(CLUSTER_K3_SKINWALKER)
        by_name = {it["name"]: it for it in items}
        assert "兽态人Skinwalker种族特性" in by_name, \
            f"主条目应成条目（源数据标题为全串）: {[it['name'] for it in items]}"
        # RP 标注不得泄漏进 name_en
        assert by_name["兽态人Skinwalker种族特性"]["name_en"] == "", \
            f"主条目 name_en 不得为 RP 标注: {by_name['兽态人Skinwalker种族特性']['name_en']!r}"
        for sub in ("蝙蝠人后裔Werebat－kin", "熊人后裔Werebear－kin", "野猪人后裔Wereboar－kin"):
            assert sub in by_name, f"{sub} 亚种应成条目: {[it['name'] for it in items]}"
            assert "先祖" in (by_name[sub].get("text") or ""), \
                f"{sub} 正文应含字段内容: {by_name[sub].get('text')!r}"
        # 混排标题（含英文）不得残留星壳
        for it in items:
            assert "**" not in it["name"], f"title 不得残留星壳: {it['name']!r}"


CLUSTER_K4_MONSTER_SECTIONS = (
    "**铜蛇（Copper Dragon）**CR 1\n"
    "XP：400\n"
    "先攻：+2；感官：黑暗视觉60尺；察觉：+6\n"
    "\n"
    "---\n"
    "\n"
    "描述（Description）\n"
    "\n"
    "---\n"
    "\n"
    "蛇类象征着智慧、医学、和康复艺术。这种印象可能起源于铜蛇，"
    "一种罕见的神奇治疗能力生物。\n"
)


class TestClusterK4:
    """怪物数据块字段章节（裸 `描述（Description）` 等）→ 并入怪物主体条目，
    不产 title='描述' 的独立伪条目（2026-08-04 K 簇星壳化回归修复）"""

    def test_monster_sections_merge_into_creature(self):
        items = run(CLUSTER_K4_MONSTER_SECTIONS)
        names = [it["name"] for it in items]
        assert "描述" not in names, f"字段章节不得成独立条目: {names}"
        assert "铜蛇" in names, f"怪物主体应成条目: {names}"
        it = next(x for x in items if x["name"] == "铜蛇")
        assert "智慧" in (it.get("text") or ""), \
            f"描述正文应并入铜蛇条目: {it.get('text')!r}"
        assert "XP" in (it.get("text") or ""), \
            f"怪物主体字段应保留: {it.get('text')!r}"


# ============ 簇 I：法术块字段链（page_814 柳絮随风真实形态） ============

CLUSTER_I_SPELL_FIELD_CHAIN = (
    "**伽瑟兰法术（GATHLAIN \n"
    "SPELLS）**\n"
    "伽瑟兰可以使用以下法术。\n"
    "**柳絮随风 \n"
    "WAFT****学派：**变化系**等级：**牧师 5，德鲁伊 5，魔战士 5，秘学士 5，萨满 5，术士/法师 \n"
    "5，唤魂师 \n"
    "5**施法时间：**1标准动作**成分：**语言，姿势，材料（一颗蒲公英的种子）"
    "**距离：**近距（25尺+5尺/2等级）**目标：**至多一名生物/2个等级，彼此相距不超过30英尺"
    "**持续时间：**1小时/等级**豁免检定：**意志通过则无效**法术抗力：**可\n"
    "你使目标变得轻到足够可以被风携带走。受此法术影响的生物会受到可累积的攻击减值。\n"
)


class TestClusterI_SpellFieldChain:
    """法术块字段链（`**标签：**值**标签：**值` 同行嵌套）→ 完整法术条目。
    字段星壳边界把「值」夹成 `**值**` 形态，`_split_inline_star_titles` 行中分支
    不得把字段值当行内标题拆出伪条目（page_814 变化系/近距/意志通过则无效
    伪条目根因，2026-08-04 #101 产出即检）"""

    def test_spell_field_chain_single_item(self):
        items = run(CLUSTER_I_SPELL_FIELD_CHAIN)
        spells = [it for it in items if it["kind"] == "race_spell"]
        assert len(spells) == 1, f"应产出 1 个法术条目（字段链不得拆成多个），实际 {len(items)}"
        it = spells[0]
        assert it["name"] == "柳絮随风", f"法术名: {it.get('name')!r}"
        assert it["name_en"] == "WAFT", f"法术英文名: {it.get('name_en')!r}"

    def test_field_values_not_fake_entries(self):
        """字段值（变化系/近距/意志通过则无效等）不得成独立条目"""
        items = run(CLUSTER_I_SPELL_FIELD_CHAIN)
        names = [it["name"] for it in items]
        for fake in ("变化系", "近距", "意志通过则无效", "个人", "自己", "姿势", "目标"):
            assert fake not in names, f"字段值不得成伪条目: {names}"

    def test_field_chain_preserved_in_text(self):
        """字段链完整保留在法术条目 text（spell 解析可提取字段）"""
        items = run(CLUSTER_I_SPELL_FIELD_CHAIN)
        it = next(x for x in items if x["kind"] == "race_spell")
        t = item_text(it)
        assert "**学派：**变化系" in t, f"学派字段缺失: {t[:150]}"
        assert "**距离：**近距（25尺+5尺/2等级）" in t, f"距离字段缺失: {t[:150]}"
        assert "**法术抗力：**可" in t, f"法术抗力字段缺失: {t[:150]}"
        assert "你使目标变得轻到" in t, f"法术正文缺失: {t[:150]}"


class TestClusterI2_FieldParse:
    """法术块字段链 → parse_fields 字段取值（簇 I 的 processor 层延续）。

    page_814 法术块用「等级/施法时间/成分/距离/豁免检定」变体词，而
    capture 标签集原本只有「环级/施放时间」——变体词不构成字段边界 →
    school 吞掉后续字段（2026-08-04 #101 产出即检发现）"""

    def test_field_chain_values_not_swallowed(self):
        from vectorizer.processors.parse_fields_common import parse_fields
        from vectorizer.processors.race import (
            _RACE_ALL_FIELD_LABELS, _RACE_EXTRA_LABELS, _RACE_LABEL_TO_KEY,
        )
        text = (
            "**学派：**变化系\n"
            "**等级：**牧师 5，德鲁伊 5\n"
            "**施法时间：**1标准动作\n"
            "**成分：**语言，姿势\n"
            "**距离：**近距（25尺+5尺/2等级）\n"
            "**目标：**至多一名生物\n"
            "**持续时间：**1小时/等级\n"
            "**豁免检定：**意志通过则无效\n"
            "**法术抗力：**可\n"
        )
        r = parse_fields(
            text,
            all_labels=_RACE_ALL_FIELD_LABELS,
            extra_labels=_RACE_EXTRA_LABELS,
            label_to_key=_RACE_LABEL_TO_KEY,
        )
        assert r.get("school") == "变化系", f"school: {r.get('school')!r}"
        assert r.get("spell_level") == "牧师 5，德鲁伊 5", f"spell_level: {r.get('spell_level')!r}"
        assert r.get("casting_time") == "1标准动作", f"casting_time: {r.get('casting_time')!r}"
        assert r.get("spell_targets") == "至多一名生物", f"spell_targets: {r.get('spell_targets')!r}"


# ============ 簇 I3：物品字段链首尾星壳（豺狼人鬣狗围脖真实形态） ============

CLUSTER_I3_ITEM_FIELD_CHAIN = (
    "**豺狼人魔法物品**\n"
    "豺狼人和弗林得豺狼人开发了以下魔法物品。\n"
    "**鬣狗围脖（Hyena Shawl）**\n"
    "**装备位置：**头部 **灵光：**中等防护和死灵系\n"
    "**施法者等级：**8**价格：**11000gp **重量：-**\n"
    "将它围在穿戴者的脖子和下巴上，这条黑围脖可以让穿戴者看穿沙尘暴。\n"
)


class TestClusterI3_ItemFieldChain:
    """物品字段链（`**标签：**值` 同行嵌套 + 行尾闭星）→ 字段行星壳完整。

    豺狼人形态：`**价格：**11000gp **重量：-**`——`_split_field_chain_star_shells`
    拆行后「整行首尾都是 `**`」（`**重量：-**` 值在星内 → 行尾闭星），split 层
    「散文行星壳剥除」分支 1（`startswith ** and endswith **`）误当整行星壳残留
    剥成 `价格：**11000gp **重量：-`（2026-08-04 #101 产出即检 D 簇定性）"""

    def test_item_field_chain_single_item(self):
        items = run(CLUSTER_I3_ITEM_FIELD_CHAIN)
        items = [it for it in items if it["kind"] == "race_item"]
        assert len(items) == 1, f"应产出 1 个物品条目，实际 {len(items)}"
        assert items[0]["name"] == "鬣狗围脖"

    def test_item_field_chain_stars_preserved(self):
        """字段行星壳不得被散文行星壳剥除误剥（首尾星壳是字段链不是残留）"""
        items = run(CLUSTER_I3_ITEM_FIELD_CHAIN)
        it = next(x for x in items if x["kind"] == "race_item")
        t = item_text(it)
        assert "**价格：**11000gp **重量：-**" in t, f"价格/重量字段星壳缺失: {t[:150]}"
        assert "**施法者等级：**8" in t, f"施法者等级字段缺失: {t[:150]}"
        assert "**装备位置：**头部" in t, f"装备位置字段缺失: {t[:150]}"


# ============ 簇 I4：标题含「法术」子串的条目不误判章节（KN098 同家族规模化） ============

CLUSTER_I4_SPELL_SUBSTRING_ENTRIES = (
    "**卓尔（Drow）**\n"
    "**种族特性**\n"
    "**法术抗力（Spell Resistance）**：卓尔拥有等同于“6+角色等级”的法术抗力。\n"
    "**强光致盲（Light Blindness）**：突然暴露在强光下会使卓尔目盲1轮。\n"
    "**起始语言**：精灵语以及地底通用语。\n"
    "**卓尔法术（Drow Spells）**\n"
    "**返祖术（Return to Nature）**：你能回归本源形态。\n"
)


class TestClusterI4_SpellSubstringEntries:
    """标题含「法术」子串的条目标题（法术抗力/类法术能力/卓越法术抗力）不得
    误判为法术章节——`_match_section` 的 race_spell 关键字「法术」是子串匹配，
    条目标题 `**法术抗力（Spell Resistance）**` 命中后整页后续条目被切进
    race_spell 态（2026-08-04 审计发现：page_164 特性 5 + 专长 4 被污染，
    全库 44 doc / 174 race_spell 中大量为特性/专长，KN098 同家族规模化）。
    合法法术章节：组1 以「法术」结尾（`卓尔法术`）或 EN 以 Spells 结尾。"""

    def test_ability_entry_not_treated_as_spell_section(self):
        """「法术抗力」是特性条目：其后条目保持 race_trait，不落入 race_spell"""
        items = run(CLUSTER_I4_SPELL_SUBSTRING_ENTRIES)
        traits = [it for it in items if it["kind"] == "race_trait"]
        spells = [it for it in items if it["kind"] == "race_spell"]
        names = [t["name"] for t in traits]
        assert "强光致盲" in names, f"强光致盲应保持 race_trait，实际 {names}"
        assert "起始语言" in names, f"起始语言应保持 race_trait，实际 {names}"
        assert all(s["name"] != "强光致盲" for s in spells), "强光致盲不得落入 race_spell"

    def test_real_spell_section_still_works(self):
        """「卓尔法术（Drow Spells）」是合法章节：其下条目正常判 race_spell"""
        items = run(CLUSTER_I4_SPELL_SUBSTRING_ENTRIES)
        spells = [it for it in items if it["kind"] == "race_spell"]
        names = [s["name"] for s in spells]
        assert "返祖术" in names, f"返祖术应在 race_spell 章节内，实际 {names}"
        assert "法术抗力" not in names, f"法术抗力是特性不是法术，实际 {names}"


# ============ 簇 I5：法术章节形态校验第二版（裸章节 + EN 大小写/单复数） ============

CLUSTER_I5_SPELL_SECTION_FORMS = (
    # 怪物法典裸章节（无 EN）——合法
    "**地精（Goblin）**\n"
    "**种族特性**\n"
    # 带括号：EN 不以 Spell 结尾——条目非章节（race_trait 态）
    "**体质法术（Constitution Dependent）**：你的法术依赖体质。\n"
    "**巫术疤痕（Scarred）**：你将巫术疤痕纹在身上。\n"
    "**地精法术**\n"
    "**油脂术（Grease）**：你将滑腻的油脂撒在地面上。\n"
    "**专长**\n"
    # 正文句误包（裸标题，page_164 引言行形态）——非法，不得切章节
    "**你的命令使你创造的阴影与黑暗法术**\n"
    "**蛛行步（Spider Climber）**：你获得攀爬速度。\n"
    # 带括号：EN 大写（GATHLAIN SPELLS）——合法
    "**伽瑟兰法术（GATHLAIN SPELLS）**\n"
    "**种子密探（SEED SPIES）**：你可以种下种子。\n"
    # 带括号：EN 单数（Ghoran Spell）——合法
    "**蒿兰人法术（Ghoran Spell）**\n"
    "**花之唇（BLOOM LIPS）**：你的嘴唇散发花香。\n"
)


class TestClusterI5_SpellSectionForms:
    """法术章节形态校验第二版（2026-08-04 审计 #103 升级）：
    第一版 `or` 条件放行了 `体质法术（Constitution Dependent）`（组1 以法术
    结尾但 EN=Dependent）与裸标题正文句 `你的命令使你创造的阴影与黑暗法术`；
    且 `endswith("Spells")` 大小写/单复数敏感会漏掉合法章节
    `伽瑟兰法术（GATHLAIN SPELLS）` / `蒿兰人法术（Ghoran Spell）`。
    第二版判据：带括号 = 组1 以「法术」结尾 且 EN 匹配 `Spells?$`（忽略大小写）；
    裸标题 = 组1 以「法术」结尾 且 不含句法虚词（`地精法术` 是怪物法典
    合法裸章节，`你的命令…` 是正文句误包）。"""

    def test_bare_monster_spell_section_kept(self):
        """`**地精法术**` 裸章节：其下条目正常判 race_spell"""
        items = run(CLUSTER_I5_SPELL_SECTION_FORMS)
        spells = [it for it in items if it["kind"] == "race_spell"]
        names = [s["name"] for s in spells]
        assert "油脂术" in names, f"地精法术章节下条目应 race_spell，实际 {names}"

    def test_bare_sentence_not_section(self):
        """裸标题正文句 `你的命令使你创造的阴影与黑暗法术` 不得切 race_spell
        章节：其后条目（蛛行步）不得落入 race_spell"""
        items = run(CLUSTER_I5_SPELL_SECTION_FORMS)
        spells = [it for it in items if it["kind"] == "race_spell"]
        names = [s["name"] for s in spells]
        assert "蛛行步" not in names, f"蛛行步是专长不是法术，实际 {names}"

    def test_uppercase_en_section_kept(self):
        """`伽瑟兰法术（GATHLAIN SPELLS）`：EN 大写仍需判合法章节"""
        items = run(CLUSTER_I5_SPELL_SECTION_FORMS)
        spells = [it for it in items if it["kind"] == "race_spell"]
        names = [s["name"] for s in spells]
        assert "种子密探" in names, f"伽瑟兰法术章节（大写 EN）下条目应 race_spell，实际 {names}"

    def test_singular_en_section_kept(self):
        """`蒿兰人法术（Ghoran Spell）`：EN 单数 Spell 仍需判合法章节"""
        items = run(CLUSTER_I5_SPELL_SECTION_FORMS)
        spells = [it for it in items if it["kind"] == "race_spell"]
        names = [s["name"] for s in spells]
        assert "花之唇" in names, f"蒿兰人法术章节（单数 EN）下条目应 race_spell，实际 {names}"

    def test_entry_with_magic_en_not_section(self):
        """`深穿法术（Deep Magic）` / `体质法术（Constitution Dependent）`：
        特性条目（EN 非 Spell/Spells 结尾）不得切 race_spell 章节"""
        items = run(CLUSTER_I5_SPELL_SECTION_FORMS)
        spells = [it for it in items if it["kind"] == "race_spell"]
        names = [s["name"] for s in spells]
        assert "深穿法术" not in names, f"深穿法术是灰矮人特性，实际 {names}"
        assert "体质法术" not in names, f"体质法术是巫术疤痕特性，实际 {names}"

    def test_entry_after_fake_section_not_polluted(self):
        """体质法术/巫术疤痕（race_trait 态条目，EN 非 Spell 结尾）不得被
        切进 race_spell；正文句误包（你的命令…）不得把蛛行步（race_feat 态）
        带进 race_spell"""
        items = run(CLUSTER_I5_SPELL_SECTION_FORMS)
        spells = [it for it in items if it["kind"] == "race_spell"]
        traits = [it for it in items if it["kind"] == "race_trait"]
        feats = [it for it in items if it["kind"] == "race_feat"]
        tnames = [t["name"] for t in traits]
        fnames = [f["name"] for f in feats]
        snames = [s["name"] for s in spells]
        assert "体质法术" in tnames, f"体质法术应保持 race_trait，实际 {tnames}"
        assert "巫术疤痕" in tnames, f"巫术疤痕应保持 race_trait，实际 {tnames}"
        assert "蛛行步" in fnames, f"蛛行步应保持 race_feat，实际 {fnames}"
        assert "体质法术" not in snames and "巫术疤痕" not in snames, f"不得落入 race_spell: {snames}"
        assert "蛛行步" not in snames, f"蛛行步不得落入 race_spell: {snames}"


# ============ 簇 I6：正文句段落截断回归（第二版修复） ============

CLUSTER_I6_SENTENCE_PARAGRAPH_SPLIT = (
    # 怪物法典真实结构：裸章节 + 法术条目 + 正文句段落行。
    # 源 40 行「在你施法以及之后法术持续的每轮开始时，…」——
    # `_split_bare_section_titles` 曾在「法术」（idx=7）处截断包星成伪裸标题
    # `**在你施法以及之后法术**`；第二版虚词排除后伪裸标题不切章节，
    # 反落裸标题条目分支 → race_spell 伪条目（2026-08-04 审计 #103 回归）
    "**食尸鬼（Ghoul）**\n"
    "**种族特性**\n"
    "**食尸鬼法术**\n"
    "**饥饿大地（Hungry Earth）**：你接触过的地面开始腐化。\n"
    "在你施法以及之后法术持续的每轮开始时，任何接触该污秽血池的生物都会受到腐蚀。\n"
    "**墓穴瘟疫（Grave Plague）**：你的攻击传播瘟疫。\n"
    # 巨魔：正文句段落行（你将自己的再生能力转移到法术持续期间的任何伤口）
    "**巨魔（Troll）**\n"
    "**巨魔法术**\n"
    "**再生术（Regeneration）**：你获得再生。\n"
    "你将自己的再生能力转移到法术持续期间的任何伤口。\n"
    # 蛇人：正文句段落行（如果你施放你偷取到的法术，你失去对应形态）
    "**蛇人（Serpentfolk）**\n"
    "**蛇人法术**\n"
    "**蛇之相（Serpent's Aspect）**：你化身为蛇。\n"
    "如果你施放你偷取到的法术，你失去对应形态。\n"
)


class TestClusterI6_SentenceParagraphNoSplit:
    """正文句段落行不得被 `_split_bare_section_titles` 截断包星（第二版回归：
    伪裸标题经 `_RE_BARE_CN_TITLE` 成 race_spell 伪条目）。修复在 normalize 层：
    `_BARE_HEAD_NOISE` 虚词表扩展（你/在/当/这/若/的 等），正文句 head 含虚词
    即不拆行——宁保持散文（并入 cur 条目 text），不产伪标题。"""

    def test_normalize_keeps_sentence_paragraph(self):
        """正文句段落行保持整行，不得在「法术」处截断包星"""
        norm = RaceFormat().normalize(CLUSTER_I6_SENTENCE_PARAGRAPH_SPLIT)
        for fake in ("**在你施法以及之后法术**", "**你将自己的再生能力转移到法术**",
                     "**如果你施放你偷取到的法术**"):
            assert fake not in norm, f"正文句不得截断包星: {fake}"

    def test_no_fake_entry_from_sentence(self):
        """正文句段落不得产生 race_spell 伪条目"""
        items = run(CLUSTER_I6_SENTENCE_PARAGRAPH_SPLIT)
        names = [it["name"] for it in items]
        for fake in ("在你施法以及之后法术", "你将自己的再生能力转移到法术",
                     "如果你施放你偷取到的法术"):
            assert fake not in names, f"正文句不得成伪条目: {fake}"

    def test_entries_after_sentence_preserved(self):
        """正文句段落行吞并前不得丢失后续法术条目（章节切换不清 cur 的既有
        机制：段落行并入 cur 的 text，后续条目不受影响）"""
        items = run(CLUSTER_I6_SENTENCE_PARAGRAPH_SPLIT)
        spells = [it for it in items if it["kind"] == "race_spell"]
        snames = [s["name"] for s in spells]
        assert "墓穴瘟疫" in snames, f"段落行后条目应保持 race_spell，实际 {snames}"
        assert "再生术" in snames, f"巨魔段落后条目应保持 race_spell，实际 {snames}"
        assert "蛇之相" in snames, f"蛇人段落后条目应保持 race_spell，实际 {snames}"

# ============ 簇 K2：半兽人聚合 FCB 形态（page_17 真实形态，2026-08-04 KN107） ============
# 与 ARG 版 FCB（`**中文**：` 纯中文 / `**职业（EN）**：` 闭合星）不同，半兽人页
# FCB 段为「聚合目录版」：
#   K2a 无闭合星：`**炼金术师（Alchemist）《ARG，APG>: `（行尾 `: `）+ 次行 `**【…】…` 正文
#   K2b 闭合星同行：`**炼金术师（Alchemist）《HA》：**+1/2破坏物品…`
# 《书》为来源标记（ARG/APG/HA/ACG/OA），归一为标准 FCB 标题形态（J 簇 UW/WO 先例：
# 标记不残留 text），同一职业多书多条应各自产出（37 职业含重复条 = 40 条目）。

CLUSTER_K2_FCB = (
    "**可选天赋职业奖励（****Favored \n"
    "Class Options****）******\n"
    "\n"
    "**炼金术师（Alchemist）《ARG，APG>: \n"
    "**【炼金炸弹】伤害+1/2。\n"
    "**炼金术师（Alchemist）《HA》：**+1/2破坏物品的力量检定和处于增加力量或体质的【突变药剂】影响下的破武检定。\n"
    "**奥能师（Arcanist）《ACG》：**在施放奥能师法术时，由于受到伤害而进行的专注检定获得+1加值。\n"
)


class TestClusterK2AggregateFCB:
    """簇 K2：半兽人聚合目录版 FCB（无闭合星 + 次行正文 / 闭合星同行 + 《书》标记）"""

    def test_k2a_bare_star_no_close_colon(self):
        """`**职业（EN）《书>: `（无闭合星）+ 次行 `**【…】…` → fcb_entry，正文并入"""
        items = run(CLUSTER_K2_FCB)
        fcbs = [it for it in items if it["kind"] == "fcb_entry"]
        assert len(fcbs) == 3, f"应产出 3 个 FCB 条目（3 职业行），实际 {len(fcbs)}"
        assert fcbs[0]["name"] == "炼金术师", fcbs[0]["name"]
        assert "炼金炸弹" in item_text(fcbs[0]), "次行正文应并入条目"

    def test_k2b_closed_star_book_mark(self):
        """`**职业（EN）《书》：**正文`（闭合星同行）→ fcb_entry，正文同行并入"""
        items = run(CLUSTER_K2_FCB)
        fcbs = [it for it in items if it["kind"] == "fcb_entry"]
        assert fcbs[1]["name"] == "炼金术师", fcbs[1]["name"]
        assert "破武检定" in item_text(fcbs[1]), "同行正文应并入条目"

    def test_k2_duplicate_class_kept(self):
        """同一职业多书多条（炼金术师 ARG+HA）各自产出，不合并去重"""
        items = run(CLUSTER_K2_FCB)
        fcbs = [it for it in items if it["kind"] == "fcb_entry"]
        names = [f["name"] for f in fcbs]
        assert names.count("炼金术师") == 2, f"重复职业应各产出，实际 {names}"

    def test_k2_book_mark_not_in_text(self):
        """《书》来源标记不残留 text（J 簇 UW/WO 先例）"""
        items = run(CLUSTER_K2_FCB)
        all_text = "".join(item_text(it) for it in items)
        assert "《ARG" not in all_text and "《HA" not in all_text and "《ACG" not in all_text

    def test_k2_arcanist_entry(self):
        """奥能师条目（闭合星形态）正常产出"""
        items = run(CLUSTER_K2_FCB)
        fcbs = [it for it in items if it["kind"] == "fcb_entry"]
        assert fcbs[2]["name"] == "奥能师", fcbs[2]["name"]
        assert "专注检定" in item_text(fcbs[2])

# ============ 簇 K3：能力块法术表标题（page_12 钢铁法术，2026-08-04 KN107 对账） ============
# 变体能力块内法术列表表标题 `**钢铁法术（Steel Spells）**` 形态完全符合合法
# race_spell 章节校验（组1「法术」结尾 + EN 复数 Spells），被误切 race_spell 态
# → 后续能力条目（带 Ex/Su/Sp 标记）与无标记能力全被污染。修复：race_spell 态
# 内遇带能力标记条目 → 永久退态 race_archetype（巨魔法术等合法章节后是无标记
# 法术条目 → 不触发，零误伤）。传古威仪（无标记能力）在首个带标记条目之后
# → 随退态归位。

CLUSTER_K3_SPELL_TABLE = (
    "**种族职业变体（****Racial \n"
    "Archetypes****）******\n"
    "\n"
    "**锻造大师（****Forgemaster****，牧师变体）******\n"
    "锻造大师擅长制造魔法物品。\n"
    "\n"
    "**手艺人（Artificer）**\n"
    "一名锻造大师只获得一个领域，且必须是手艺领域。\n"
    "\n"
    "**钢铁法术（Steel Spells）**\n"
    "锻造大师将以下法术加入她的法术列表中。\n"
    "\n"
    "**| 1环法术**\n"
    " | 匠人诅咒（crafter’s curse） | 匠人祝福（crafter’s fortune） |\n"
    "| --- | --- |\n"
    "\n"
    "**神圣铁匠（Divine Smith, Su）**\n"
    "当锻造大师施放一个目标为武器、盾牌或盔甲的法术时，法术的效果以施法者等级+1计算。\n"
    "\n"
    "**传古威仪（Ancient Splendor）**\n"
    "被刻印的武器，护甲或盾牌在交涉和威吓上提供+2环境加值。\n"
)


class TestClusterK3SpellTableTitle:
    """簇 K3：能力块法术表标题（钢铁法术）+ 能力条目退态"""

    def test_k3a_ability_after_spell_table_is_archetype(self):
        """表标题后的带标记能力（Divine Smith, Su）→ race_archetype 非 race_spell"""
        items = run(CLUSTER_K3_SPELL_TABLE)
        ab = [it for it in items if it["kind"] == "race_archetype"]
        sp = [it for it in items if it["kind"] == "race_spell"]
        names = [a["name"] for a in ab]
        assert "神圣铁匠" in names, f"带标记能力应归 race_archetype，实际 {names}"
        snames = [s["name"] for s in sp]
        assert "神圣铁匠" not in snames, f"能力不得误判 race_spell，实际 {snames}"

    def test_k3b_unmarked_ability_after_exit(self):
        """首个带标记条目退态后，无标记能力（传古威仪）随退态归位 race_archetype"""
        items = run(CLUSTER_K3_SPELL_TABLE)
        ab = [it for it in items if it["kind"] == "race_archetype"]
        sp = [it for it in items if it["kind"] == "race_spell"]
        names = [a["name"] for a in ab]
        assert "传古威仪" in names, f"无标记能力应随退态归位，实际 {names}"
        assert "传古威仪" not in [s["name"] for s in sp]

    def test_k3c_steel_spells_chapter_not_section(self):
        """钢铁法术表标题不吞并后续条目为 race_spell 章节态（标题行本身可成条目）"""
        items = run(CLUSTER_K3_SPELL_TABLE)
        # 变体主条目 + 手艺人 + 神圣铁匠 + 传古威仪 = 4 race_archetype
        assert len([it for it in items if it["kind"] == "race_archetype"]) == 4


# 簇 K5：page_16 骑士团变体章节（KN107 对账）——章节标题「种族职业和
# 骑士团变体（Racial Archetypes & Orders）」不含 race_archetype 既有
# 关键字「职业变体/变体职业」（「职业」后接「和」不连续），若 `_match_section`
# 不识别则状态停留上一章节态（fcb_entry）→ 后续骑士团能力条目全污染。
CLUSTER_K5_ORDER_ARCHETYPE = (
    "**种族职业和骑士团变体（****Racial \n"
    "Archetypes & Orders****）******\n"
    "\n"
    "**社群守卫（****Community \n"
    "Guardian****，先知变体）******\n"
    "社群守卫命中注定将会保护并援助她社群中的弱者与无辜者。她的呼唤让还能"
    "她凝聚并提炼出集体的意志，来达成这些目标。\n"
)


class TestClusterK5OrderArchetype:
    """簇 K5：骑士团变体章节（page_16，半身人）"""

    def test_k5a_order_archetype_section_matches(self):
        """「种族职业和骑士团变体」章节 → 后续能力归 race_archetype 非 fcb_entry"""
        items = run(CLUSTER_K5_ORDER_ARCHETYPE)
        ab = [it for it in items if it["kind"] == "race_archetype"]
        fc = [it for it in items if it["kind"] == "fcb_entry"]
        names = [a["name"] for a in ab]
        assert "社群守卫" in names, f"骑士团变体能力应归 race_archetype，实际 {names}"
        assert "社群守卫" not in [f["name"] for f in fc], \
            f"不得误归 fcb_entry，实际 {[f['name'] for f in fc]}"


# 簇 K6：章节标题去重误弹修复（KN107 对账 2 误弹：破敌之锤 page_12 +
# 审判者 page_17）——pop 判据加「章节标题/跨行碎片」守卫：
# 无正文变体主条目（破敌之锤）保留；章节标题/elided 跨行残片仍弹。
CLUSTER_K6_FOEHAMMER = (
    "**种族职业和骑士团变体（****Racial \n"
    "Archetypes & Orders****）******\n"
    "\n"
    "**破敌之锤（****Foehammer****，战士变体）******\n"
    "\n"
    "**大锤（****Sledgehammer, \n"
    "Ex****）**：3级时，破敌之锤在持用锤类武器时在冲撞、闯越、卸武和绊摔的战技检定上获得+2环境加值。这一能力取代盔甲训练1。\n"
)

CLUSTER_K6_FCB_INQUISITOR = (
    "**半兽人（Half-Orc）**\n"
    "半兽人的起始年龄、身高和体重修改表。\n"
    "\n"
    "**天赋职业奖励（****Favored Class \n"
    "Bonuses****）******\n"
    "\n"
    "**审判者（Inquisitor）《ARG，APG》：**威吓检定以及识别怪物的知识检定+1/2。\n"
)

CLUSTER_K6_SECTION_TITLES = (
    "**种族替换规则（Alternate Racial Rules）**\n"
    "\n"
    "**水栖精灵种族替换规则（Aquatic Elf Alternate Racial Rules）**\n"
    "\n"
    "**新种族规则（New Racial Rules）**\n"
    "\n"
    "**娜迦裔（Nagaji）**\n"
    "娜迦裔是一种蛇形有鳞的类人生物。\n"
    "\n"
    "**娜迦**\n"
    "[[fc:elided]]\n"
    "\n"
    "**种族特性（Nagaji Racial Traits）**\n"
    "**+2力量，+2魅力，-2智力**：娜迦裔强壮。\n"
)


class TestClusterK6DedupGuard:
    """簇 K6：章节标题去重守卫（误弹修复）"""

    def test_k6a_foehammer_shell_title_popped(self):
        """无正文变体壳标题（破敌之锤）与章节标题同策略弹掉，特性子条目完整保留

        破敌之锤（Foehammer，战士变体）源数据无介绍散文，标题后直接是特性
        子条目序列——能力全在子条目 text（子条目正文均含「破敌之锤」字样，
        检索等价命中），空壳条目违反 race 空 text=0 闸口（KN085 口径）。
        核心验证：弹壳标题后其下特性正文不随弹丢失（K6 误弹修复的机制保障）。
        """
        items = run(CLUSTER_K6_FOEHAMMER)
        names = [it["name"] for it in items]
        assert "破敌之锤" not in names, f"无正文变体壳标题不入库，实际 {names}"
        assert "大锤" in names, f"子条目大锤应完整保留，实际 {names}"
        sledge = [it for it in items if it["name"] == "大锤"][0]
        assert "3级时，破敌之锤在持用锤类武器时在冲撞、闯越、卸武和绊摔的战技检定上获得+2环境加值" in sledge["text"], \
            "破敌之锤能力正文须完整保留在子条目中"

    def test_k6b_section_titles_still_popped(self):
        """章节标题（种族替换规则/水栖精灵种族替换规则/新种族规则）仍弹"""
        items = run(CLUSTER_K6_SECTION_TITLES)
        names = [it["name"] for it in items]
        assert "种族替换规则" not in names, "种族替换规则章节标题不得入库"
        assert "水栖精灵种族替换规则" not in names, "带括号章节标题不得入库"
        assert "新种族规则" not in names, "新种族规则章节标题不得入库"

    def test_k6c_elided_fragment_still_popped(self):
        """elided 跨行残片（**娜迦** + elided 标记）仍弹，真实条目不受影响"""
        items = run(CLUSTER_K6_SECTION_TITLES)
        names = [it["name"] for it in items]
        # 碎片娜迦不入库（真实娜迦裔条目在）
        assert "娜迦裔" in names, f"真实条目应保留，实际 {names}"
        frag = [n for n in names if n == "娜迦"]
        assert not frag, f"elided 跨行残片不得入库，实际 {frag}"
        # 碎片后的种族特性字段行并入条目，不产生空壳
        assert all(it["text"] for it in items if it["name"] == "娜迦裔"), "娜迦裔正文应完整"

    def test_k6d_inquisitor_fcb_text_restored(self):
        """审判者 FCB 行正文不再被「怪物」关键字拆行误吞（tail「的」守卫）"""
        items = run(CLUSTER_K6_FCB_INQUISITOR)
        fc = [it for it in items if it["kind"] == "fcb_entry"]
        names = [f["name"] for f in fc]
        assert "审判者" in names, f"审判者 FCB 应产出，实际 {names}"
        inj = [f for f in fc if f["name"] == "审判者"][0]
        assert "威吓检定以及识别怪物的知识检定+1/2。" in inj["text"], \
            f"FCB 正文应完整保留（不被拆行），实际 {inj['text']!r}"
        # 伪标题「威吓检定以及识别怪物」不得出现
        assert not any("识别怪物" in f["name"] for f in fc), \
            f"拆行伪标题不得入库，实际 {[f['name'] for f in fc]}"

# ============ 簇 KN100：数据块字段行伪条目（字段词表守卫） ============
# KN100 登记（已知问题记录 §追加小节）：`**字段名**：值`/`**字段名**－值` 等
# stat block 字段行被当条目切出（title=字段名）。区隔判据（全库普查
# 2026-08-04，40 候选 11 文件）：title 为 stat block 字段名（效果/频率/
# 类型/治愈/发作频率/价格调整/部位/价值/制造价格/毒素/通常情况/先决条件
# 等）→ 伪条目并入当前条目；ARG 标准特性标题（感官/防御/法术抗力/特性/
# 起始语言）→ 保持独立条目（B 类不回归）。


class TestClusterKN100FieldRows:
    """KN100：数据块字段行伪条目——字段词表守卫，并入当前条目"""

    def test_kn100a_poison_stat_block_merged(self):
        """毒药 stat block（树蛙毒形态）：频率/效果/治愈裸标题并入毒药条目"""
        raw = (
            "**树蛙毒（Grippli Poison）**\n"
            "**类型**－毒素，接触或伤口；**强韧豁免（DC）**\n"
            "“10+1/2树蛙人HD+体质修正”；\n"
            "**频率**\n"
            "－每轮1次，持续6轮；\n"
            "**效果**\n"
            "－1d2敏捷伤害；\n"
            "**治愈**\n"
            "－1次豁免。\n"
        )
        items = run(raw)
        names = [it["name"] for it in items]
        assert names == ["树蛙毒"], f"字段行不得切伪条目: {names}"
        text = item_text(items[0])
        assert "频率" in text and "效果" in text and "治愈" in text, \
            f"字段值应并入毒药条目: {text!r}"

    def test_kn100b_feat_effect_field_merged(self):
        """专长章节态（鸮形人形态）：`**鸮形人专长**` 章节后效果字段并入"""
        raw = (
            "**鸮形人（Strix）**\n"
            "鸮形人善于空中战斗。\n"
            "**鸮形人专长**\n"
            "摄风之翼（战斗）\n"
            "**先决条件**：盘旋，强力之翼\n"
            "**效果**：以一个整轮动作，你可以挥舞你的翅膀。\n"
        )
        items = run(raw)
        names = [it["name"] for it in items]
        assert names == ["鸮形人"], f"效果字段不得切伪条目: {names}"
        text = item_text(items[0])
        assert "先决条件" in text and "效果" in text, \
            f"字段值应并入专长条目: {text!r}"

    def test_kn100c_trap_banner_effect_merged(self):
        """陷阱横幅（狗头人 `====**效果**====` 拆行残留）：效果裸标题并入陷阱条目"""
        raw = (
            "**狗头人陷阱**\n"
            "====**效果**====\n"
            "**触发：**进入位置；\n"
            "**重设：**无。\n"
        )
        items = run(raw)
        names = [it["name"] for it in items]
        assert names == ["狗头人陷阱"], f"横幅效果不得切伪条目: {names}"
        text = item_text(items[0])
        assert "效果" in text and "触发" in text, f"横幅应并入陷阱条目: {text!r}"

    def test_kn100d_creature_speed_bare_value_merged(self):
        """怪物数据块（鼠族形态）：`**速度**40尺；` 裸值行并入怪物条目"""
        raw = (
            "**鼠族**\n"
            "**速度**40尺；**防御等级：** +1天生护甲\n"
        )
        items = run(raw)
        names = [it["name"] for it in items]
        assert names == ["鼠族"], f"速度字段行不得切伪条目: {names}"
        assert "速度" in item_text(items[0])

    def test_kn100e_item_stat_block_chain_merged(self):
        """物品 stat block（page_18 权杖形态）：部位/价值/制造价格并入物品条目"""
        raw = (
            "**魔法物品**\n"
            "**命令权杖**：一根强大的权杖。\n"
            "**部位**：无；**价值**：38305gp；**重量**：5磅。\n"
            "**制造价格**：19305gp。\n"
        )
        items = run(raw)
        names = [it["name"] for it in items]
        assert names == ["命令权杖"], f"物品字段行不得切伪条目: {names}"
        text = item_text(items[0])
        assert "部位" in text and "价值" in text and "制造价格" in text, \
            f"字段值应并入物品条目: {text!r}"

    def test_kn100f_field_label_en_paren_merged(self):
        """带 EN 字段标题（半人马形态）：`**先决条件（Prerequisite）**` 并入变体条目"""
        raw = (
            "**陷阵士（Charger）【骑将变体】**\n"
            "陷阵士完全能够体现出半人马那毁灭性的战斗力。\n"
            "**先决条件（Prerequisite）：**半人马（或者任何四足半人身。\n"
        )
        items = run(raw)
        names = [it["name"] for it in items]
        assert names == ["陷阵士"], f"先决条件字段标题不得切伪条目: {names}"
        assert "先决条件" in item_text(items[0])

    def test_kn100g_poison_ex_field_bare_merged(self):
        """怪物特殊攻击（AP_怪物形态）：`毒素（Poison，Ex）：` 并入怪物条目"""
        raw = (
            "**铜蛇**\n"
            "毒素（Poison，Ex）：伤口感染（injury）——啮咬（bite）；豁免 DC 12。\n"
        )
        items = run(raw)
        names = [it["name"] for it in items]
        assert names == ["铜蛇"], f"毒素字段标题不得切伪条目: {names}"
        assert "毒素" in item_text(items[0])

    def test_kn100h_arg_legit_trait_unchanged(self):
        """B 类不回归：ARG 合法特性（感官/起始语言）保持独立条目"""
        raw = (
            "**吸血裔（Dhampir）**\n"
            "吸血裔是人类与吸血鬼结合的产物。\n"
            "**黑暗视觉（Darkvision）**\n"
            "**感官（Senses）**：吸血裔拥有昏暗视觉和60尺黑暗视觉。\n"
            "**起始语言（Languages）**：通用语。\n"
        )
        items = run(raw)
        names = [it["name"] for it in items]
        assert "感官" in names, f"ARG 合法特性感官应独立: {names}"
        assert "起始语言" in names, f"ARG 合法特性起始语言应独立: {names}"

    def test_kn100i_legit_item_entry_unchanged(self):
        """B 类不回归：条目流态非字段名（驱兽剂）仍独立切条目"""
        raw = (
            "**魔法物品**\n"
            "**驱兽剂**：售价25gp。\n"
            "**攀爬藤蔓**：售价50gp。\n"
        )
        items = run(raw)
        names = [it["name"] for it in items]
        assert "驱兽剂" in names and "攀爬藤蔓" in names, \
            f"合法物品条目应独立: {names}"


# ============ 簇 L：4 星粘连「章节+条目」家族（BotB/BotN/ISR 核心，2026-08-04 全量核查 M1） ============

CLUSTER_L_BOTB_SECTION = (
    "**种族特性替换****敏锐狐妖（Keen Kitsune）**：尽管狐妖很友善，"
    "但是众所周知他们比看上去的更加聪明和狡猾。"
)

CLUSTER_L_BOTB_FCB = (
    "**天赋职业选项****炼金术师**：获得1/6个科研发现。"
)

CLUSTER_L_BOTB_FCB_NOEN = (
    "**天赋职业选项****所有职业**：获得1/6个新的魔性之尾。"
)

CLUSTER_L_BOTN_BG = (
    "**背景元素****生于光明(Born in the Light)**"
)

CLUSTER_L_ISR_BARE = (
    "精灵****精灵角色可以选择以下种族特性替换原本的种族特性。"
)

CLUSTER_L_GLUE_REGRESSION = (
    "**魅****影身姿（Phantom Presence, Ex）**\n"
    "魅影身姿的变体能力描述正文。"
)

# BotN 源 L13 真实形态（2026-08-04 行中 4 星章节粘连）：前文散文 + 行中
# `**背景元素****语言天才(Linguistic  Genius)**：`（4 星前是 `那里。**` 非星
# 闭合——行首锚定拆行不命中、GLUE 守卫拦住合并 → 整行吞并。Linguistic 后
# 双空格为源数据原文，标题清洗层剥除）。
CLUSTER_L_BOTN_INLINE = (
    "Xia，那儿僵尸很常见。但一些僵尸裔游民也被吸引到了Numeria的技术奇迹那里。"
    "**背景元素****语言天才(Linguistic  Genius)**："
    "你可以从字里行间读出比作者想要表达的还多的信。"
)

CLUSTER_L_BOTN_INLINE_TWO = (
    "**背景元素****语言天才(Linguistic  Genius)**：你可以从字里行间读出信。\n"
    "**背景元素****大忽悠(Mind Trapper)**：你的话术滴水不漏。"
)

# BotN 亚种字段链（2026-08-04 行中 `**X**：` 星壳字段，僵尸裔真实形态）：
# `**祖先**：僵尸***属性调整**：+2力量…` ——3 星粘连 + 同行字段链
# （`_RE_FIELD_CHAIN_STAR` 拆行成 `**祖先：**` 等星内冒号形态）——字段词表
# 缺口（祖先/属性调整/替换技能调整/替换类法术能力/替换弱点 等）导致
# race_trait 态切出 20 个字段伪条目（M1 拆行暴露的中间态）。
CLUSTER_L_BOTN_HERITAGE_FIELDS = (
    "**种族特性**\n"
    "**僵尸裔(Jiang-Shi Born, Ru-Shi)**![[图片]](http://x.jpg)\n"
    "**祖先**：僵尸***属性调整**：+2力量，+2智力，-2敏捷"
    "**替换技能调整**：特技，知识(工程)\n"
    "**替换类法术能力**：僵尸裔获得抹消术(erase)作为类法术能力。"
    "**替换弱点**：僵尸裔对抗声音效果和法术的豁免遭受-1减值。"
)


class TestClusterL_QuadGlueSectionTitles:
    """簇 L：4 星粘连「章节+条目」家族（BotB/BotN/ISR 核心）

    全量核查 M1（KN115 根因）：`_RE_CN_STAR_CN_GLUE` 把 `**种族特性替换
    ****敏锐狐妖**` 误并为 `**种族特性替换敏锐狐妖**` → 章节行消费标题、
    替换特性 0 hits、FCB 0 个切出、title 前缀污染。修复：拆行扩展 + GLUE
    守卫（组1 前字符须为 `*` 才合并）。
    """

    def test_botb_section_title_glue(self):
        """`**种族特性替换****敏锐狐妖（Keen Kitsune）**：` → 章节消费 + alt_trait 切出"""
        items = run(CLUSTER_L_BOTB_SECTION)
        assert len(items) == 1, f"应切出 1 条，实际 {len(items)}"
        it = items[0]
        assert it["kind"] == "alt_trait"
        assert it["name"] == "敏锐狐妖"
        assert it["name_en"] == "Keen Kitsune"
        assert "种族特性替换" not in it["name"]

    def test_botb_fcb_glue(self):
        """`**天赋职业选项****炼金术师**：` → fcb_entry 切出（KN115 ② 0 fcb_entry）"""
        items = run(CLUSTER_L_BOTB_FCB)
        assert len(items) == 1, f"应切出 1 条，实际 {len(items)}"
        it = items[0]
        assert it["kind"] == "fcb_entry"
        assert it["name"] == "炼金术师"
        assert "天赋职业选项" not in it["name"]

    def test_botb_fcb_noen_glue(self):
        """`**天赋职业选项****所有职业**：` 无 EN 条目形态 → fcb_entry 切出"""
        items = run(CLUSTER_L_BOTB_FCB_NOEN)
        assert len(items) == 1, f"应切出 1 条，实际 {len(items)}"
        it = items[0]
        assert it["kind"] == "fcb_entry"
        assert it["name"] == "所有职业"

    def test_botn_background_element_glue(self):
        """`**背景元素****生于光明(Born in the Light)**` → title 无「背景元素」前缀污染"""
        items = run(CLUSTER_L_BOTN_BG)
        assert len(items) == 1, f"应切出 1 条，实际 {len(items)}"
        it = items[0]
        assert "背景元素" not in it["name"], f"title 不得含章节前缀: {it['name']!r}"
        assert it["name"] == "生于光明"
        assert it["name_en"] == "Born in the Light"

    def test_isr_bare_quad_glue_leading(self):
        """`精灵****精灵角色可以…` 行首裸 4 星 → 「精灵」节标题切出（非「精灵精灵」
        合并）；组句前瞻（KN131）→ 组标题 alt_trait"""
        items = run(CLUSTER_L_ISR_BARE)
        assert len(items) == 1, f"应切出 1 条，实际 {len(items)}"
        it = items[0]
        assert it["kind"] == "alt_trait"
        assert it["name"] == "精灵"
        assert "精灵" in item_text(it)

    def test_glue_star_inner_regression(self):
        """`**魅****影身姿` 星内拆裂仍合并（GLUE 原职责回归：组1 前字符为 `*`）"""
        items = run(CLUSTER_L_GLUE_REGRESSION)
        assert items, "应产出条目"
        it = items[0]
        assert it["name"] == "魅影身姿"
        assert "Phantom Presence" in it["name_en"]

    def test_botn_inline_glue(self):
        """行中 4 星章节粘连（BotN 源 L13 真实形态）：`…那里。**背景元素****语言天才(Linguistic  Genius)**：…`

        行首锚定版拆行正则不命中 → GLUE 守卫（前字符非 `*`）也不合并 →
        整行变散文吞并后续（BotN 回归 18→8 chunks 根因，2026-08-04）。
        修复：`_RE_QUAD_GLUE_SECTION_TITLE` 去行首锚定 + 替换加 `\n` 前缀，
        前文散文保留、章节行消费、条目独立切出。
        """
        items = run(CLUSTER_L_BOTN_INLINE)
        assert len(items) == 1, f"应切出 1 条，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "语言天才"
        assert "Linguistic" in it["name_en"] and "Genius" in it["name_en"]
        assert it["kind"] == "race_trait", f"背景元素章节 → race_trait: {it['kind']}"
        assert "背景元素" not in it["name"]
        assert "你可以从字里行间" in item_text(it), "正文不得丢失"
        # 前文散文（Xia…）在章节切换时按既有行为清空（pending_text.clear）——
        # 真实文件中该行前有僵尸裔 cur，散文并入前一条目；此处无前 cur

    def test_botn_inline_glue_multi(self):
        """行中粘连连续两条（BotN L13/L17 形态）：两条均切出、章节行不产空壳"""
        items = run(CLUSTER_L_BOTN_INLINE_TWO)
        assert len(items) == 2, f"应切出 2 条，实际 {len(items)}"
        assert [it["name"] for it in items] == ["语言天才", "大忽悠"]
        assert all(it["kind"] == "race_trait" for it in items)
        assert all("背景元素" not in it["name"] for it in items)

    def test_botn_heritage_fields(self):
        """BotN 亚种字段链并入亚种条目（不产 20 个字段伪条目）

        `**祖先**：僵尸***属性调整**：+2力量…` —— `_RE_FIELD_CHAIN_STAR`
        拆行后 `**祖先**：` 等星内冒号形态 → race_trait 态 BARE_CN_COLON
        分支：X ∈ `_ARG_FIELD_LABELS`（补词后）→ 并入当前条目。
        """
        items = run(CLUSTER_L_BOTN_HERITAGE_FIELDS)
        assert len(items) == 1, f"应切出 1 条（僵尸裔），实际 {len(items)}: {[it['name'] for it in items]}"
        it = items[0]
        assert it["name"] == "僵尸裔"
        assert "Jiang-Shi" in it["name_en"]
        text = item_text(it)
        assert "+2力量" in text, "属性调整值并入"
        assert "抹消术" in text, "替换类法术能力并入"
        assert "替换弱点" in text, "替换弱点字段保留"
        assert "声音效果" in text, "替换弱点正文并入"


# BotC 替换儿亚种双段标题（2026-08-04 全量核查 M3，巫团血脉BotC_替换儿
# 种族选项.md L15 真实形态）：`**妖鬼婆裔 替换儿（Annis-Born
# Changelings） 矿砾之女（Slag May）**` —— `_RE_TITLE` 组1 字符集不容
# 空格 → 整行不匹配任何标题正则 → 散文行并入 intro cur（10 亚种 0 产出，
# E 组幽灵 cur 实证）。修复：normalize 拆行成 `**妖鬼婆裔替换儿（EN）**`
# + `（矿砾之女 Slag May）` 正文行——条目名取亚种名（官方名 Annis-Born
# Changeling），变体名（Slag May 俗称）进 text 保检索。
CLUSTER_M_BOTC_DUAL_TITLE = (
    "**种族特性**\n"
    "**妖鬼婆裔 替换儿（Annis-Born Changelings） 矿砾之女（Slag May）**\n"
    "拥有着宽阔的肩膀和健壮的体格，矿渣之女在所有的体力活动中展现出不可思议的天赋。\n"
    "祖先：妖鬼婆（Annis hag）\n"
    "典型阵营：混乱中立\n"
    "替换属性调整：+2力量，+2魅力，-2体质\n"
    "鬼婆种族特性：妖鬼婆裔替换儿在近战伤害检定上获得+1种族加值。\n"
    "鬼婆血统觉醒：你那锯齿般的爪子会造成撕裂状的伤口，在重击确认成功时可额外造成1点流血伤害。"
)

# BotC「鬼婆血统觉醒」真条目标题（L193 真实形态）：M1 词表补丁把「鬼婆
# 血统觉醒」加入 `_ARG_FIELD_LABELS`（BotN 字段链 `**鬼婆血统觉醒：**` 星壳
# 冒号形态并入亚种条目），但 `_ALL_FIELD_LABELS` 同词在 split L1127 带括号
# 标题拦截处误吞 BotC 真条目（`**鬼婆血统觉醒（Awakened Hag  Heritage）**`
# 含 EN 括号 → 被并入前一条目）。修复：L1127 拦截收窄为 `_ENTRY_FLOW_FIELD_
# LABELS`（ARG 字段词带括号形态全库无字段行场景，BotN 字段走 COLON 分支）。
CLUSTER_M_BOTC_HERITAGE_TITLE = (
    "**种族特性**\n"
    "**妖鬼婆裔替换儿（Annis-Born Changelings）**\n"
    "拥有着宽阔的肩膀和健壮的体格。\n"
    "**鬼婆血统觉醒（Awakened Hag  Heritage）**\n"
    "你的鬼婆血统变得更为强大，在对抗奥术法术（Arcane Spells）的豁免检定中获得+2种族加值。"
)

# TITLE 分支 dedup pop 后 cur 未置 None（2026-08-04 全量核查 M2）：
# 空壳章节标题（`**种族替换规则（EN）**`，ISR 拼接文件同名双标题真实形态）
# 被 TITLE 分支弹掉后 cur 仍指向已弹死 dict → 后续同名标题同名合并 continue、
# 散文并入死 dict 整段丢失（章节分支 L1098-1102 与裸标题分支 L1228-1232
# 均有 cur=None，TITLE 分支独缺——代码审查不对称）。修复：pop 后补
# `cur = None`，散文改走 pending_text 由下一条目 flush 承接。
CLUSTER_M_TITLE_DEDUP_POP_CUR = (
    "**种族替换规则（Race Replacement Rules）**\n"
    "**种族替换规则（Race Replacement Rules）**\n"
    "以下规则适用于所有种族。\n"
    "**妖鬼婆裔替换儿（Annis-Born Changelings）**\n"
    "拥有着宽阔的肩膀和健壮的体格。"
)


class TestClusterM_BotCDualTitles:
    """簇 M：BotC 替换儿亚种双段标题 + 词表回归 + TITLE pop 幽灵 cur（M2/M3）"""

    def test_botc_dual_title_split(self):
        """双段标题拆行：亚种名作条目、变体名与字段链进 text（10 亚种 0 产出根因）"""
        items = run(CLUSTER_M_BOTC_DUAL_TITLE)
        assert len(items) == 1, f"应切出 1 条（妖鬼婆裔替换儿），实际 {len(items)}: {[it['name'] for it in items]}"
        it = items[0]
        assert it["name"] == "妖鬼婆裔替换儿"
        assert "Annis-Born" in it["name_en"]
        assert it["kind"] == "race_trait"
        text = item_text(it)
        assert "矿砾之女" in text, "变体名进 text（检索可达）"
        assert "Slag May" in text
        assert "祖先：妖鬼婆" in text, "字段链并入"
        assert "+2力量" in text, "替换属性调整并入"
        assert "鬼婆种族特性" in text
        assert "鬼婆血统觉醒" in text

    def test_botc_heritage_title_not_swallowed(self):
        """`**鬼婆血统觉醒（Awakened Hag  Heritage）**` 是带 EN 括号的真条目标题
        → 独立切出，不并入前一条目（M1 词表补丁在 L1127 的误伤）"""
        items = run(CLUSTER_M_BOTC_HERITAGE_TITLE)
        assert len(items) == 2, f"应切出 2 条，实际 {len(items)}: {[it['name'] for it in items]}"
        assert [it["name"] for it in items] == ["妖鬼婆裔替换儿", "鬼婆血统觉醒"]
        it = items[1]
        assert it["kind"] == "race_trait"
        assert "Awakened Hag" in it["name_en"]
        assert "奥术法术" in item_text(it), "血统觉醒正文不得丢失"

    def test_title_dedup_pop_sets_cur_none(self):
        """TITLE 分支 pop 空壳章节标题后 cur=None：同名标题不再合并进死 dict，
        散文归新章节条目不丢失（与章节/裸标题分支对称）。

        修复前：pop 后 cur 未置 None → 同名标题 continue、散文并入死 dict
        整段丢失（「种族替换规则」章节散文消失、产出 1 条）。
        """
        items = run(CLUSTER_M_TITLE_DEDUP_POP_CUR)
        assert len(items) == 2, f"应 2 条（章节 + 亚种），实际 {len(items)}: {[it['name'] for it in items]}"
        assert items[0]["name"] == "种族替换规则"
        text0 = item_text(items[0])
        assert "以下规则适用于所有种族" in text0, "pop 后章节散文不得丢失"
        it = items[1]
        assert it["name"] == "妖鬼婆裔替换儿"
        assert "拥有着宽阔的肩膀" in item_text(it)


# ============ 簇 N：属性调整行独立切出（2026-08-04 全量核查 M4） ============

# 值星壳形态属性行（`**+2敏捷，+2体质**：正文`）在 race_trait 态（章节标题
# 「种族特性」之后）须独立切出——修复前无匹配分支：`_RE_TITLE` 组1 以汉字
# 开头不容 `+` → 走散文分支并入 intro cur（~20 族粘 intro 尾）；蝮血裔
# （page_385 4 星章节形态）则因 SEC 弹 cur 后 cur=None → 属性行改走
# pending_text 被 COLON 分支 `cur["text"]=m.group(2)` 覆盖 → 完全丢失。
# intro 态（无章节标题，ISR 新种族块）保持并入现状（属性行即该族 intro）。
CLUSTER_N_ABILITY_ADJ_TRAIT = (
    "**大地精（Hobgoblins）**\n"
    "性情激烈并奉行军国主义，大地精以征服为生。\n"
    "**大地精种族特性（Hobgoblin Racial Traits）**\n"
    "**+2敏捷，+2体质**：大地精迅捷又强健。\n"
    "**生物类型**：大地精属于类人生物，地精子类。\n"
)

CLUSTER_N_ABILITY_ADJ_VISHKANYA = (
    "**蝮血裔（Vishkanyas）**\n"
    "蝮血裔是一种有毒血的异种类人生物。\n"
    "**蝮血裔****种族特性（****Vishkanya Racial Traits****）******\n"
    "**+2****敏捷，****+2****魅力，****-2****感知**：蝮血裔优美而又典雅，但是她们往往不够理性。\n"
    "**生物类型**：蝮血裔属于类人生物，蝮血裔子类。\n"
)

CLUSTER_N_ABILITY_ADJ_INTRO_KEEP = (
    "**绪任克斯枭族（Syrinx）**\n"
    "**+2感知，-2敏捷**：绪任克斯枭族善于沉思具有耐心，这些特点也让她们的行动有些迟缓。\n"
    "**标准速度（Normal Speed）**：绪任克斯枭族的基本速度为30尺。\n"
)


class TestClusterN_AbilityAdj:
    """簇 N：属性调整行（值星壳形态）在 race_trait 态独立切出（M4）"""

    def test_trait_state_cuts_independent_item(self):
        """标准 ARG 页（大地精形态）：章节标题后属性行 → 独立「属性调整」条目，
        不粘 intro 尾（修复前并入 intro cur）。"""
        items = run(CLUSTER_N_ABILITY_ADJ_TRAIT)
        names = [it["name"] for it in items]
        assert "属性调整" in names, f"应切出属性调整条目：{names}"
        it = next(i for i in items if i["name"] == "属性调整")
        assert it["kind"] == "race_trait"
        text = item_text(it)
        assert "+2敏捷，+2体质" in text, "属性值进 text（检索可达）"
        assert "大地精迅捷又强健" in text, "属性调整正文不得丢失"
        intro = next(i for i in items if i["kind"] == "race_intro")
        assert "迅捷又强健" not in item_text(intro), "属性行不得粘 intro 尾"

    def test_vishkanya_not_lost(self):
        """蝮血裔 4 星章节形态（page_385）：属性行独立切出（修复前经 pending
        被 COLON 分支覆盖 → 完全丢失）。"""
        items = run(CLUSTER_N_ABILITY_ADJ_VISHKANYA)
        names = [it["name"] for it in items]
        assert "属性调整" in names, f"属性行不得丢失：{names}"
        it = next(i for i in items if i["name"] == "属性调整")
        assert "+2敏捷，+2魅力，-2感知" in item_text(it)
        assert "优美而又典雅" in item_text(it)
        # 字段行照常独立
        assert "生物类型" in names

    def test_intro_state_keeps_merge(self):
        """ISR 新种族形态（无章节标题，intro 态）：属性行并入主条目保持现状
        （属性行即该族 intro 正文，切出会产空 intro）。"""
        items = run(CLUSTER_N_ABILITY_ADJ_INTRO_KEEP)
        assert len(items) == 2, f"应 2 条（intro + 标准速度），实际 {len(items)}"
        intro = items[0]
        assert intro["kind"] == "race_intro"
        assert intro["name"] == "绪任克斯枭族"
        assert "善于沉思" in item_text(intro), "属性行并入 intro"


# ============ 簇 O：BoS FCB 裸职业行（M7） ============

CLUSTER_O_FCB_BARE = (
    "**剪影人（Wayang）**\n"
    "剪影人描述。\n"
    "**剪影人天赋职业选项**\n"
    "以下选项对所有有着列出的天赋职业的剪影人可用。除非另有说明，否则每当你选择该天赋职业时都会得到这些奖励。\n"
    "野蛮人：在对抗处于昏暗或黑暗的对手时在武器伤害检定上获得+1/4加值\n"
    "牧师：当使用引导能量和施展造成负能量或正能量伤害的法术，包括造成伤害和治疗伤害法术时在伤害检定上获得+1/2加值。这个加值在通过正能量或负能量效果治疗时不生效\n"
    "操念使：操念使的虚空注能和原力的DC+1/4\n"
    "女巫：将一个不在女巫法术列表上的术士/法师法术作为加入女巫的法术列表。这个法术必须至少比女巫可以施展的最高等级法术低1级并且必须属于幻术（幽影幻觉）子学派或有着黑暗描述符。\n"
)


CLUSTER_O_FCB_TITLE_BODY = (
    "**精灵可选天赋职业奖励（Favored Class Options）**\n"
    "**猎人（Hunter）**\n"
    "从后述列表中选择一种武器：长弓（longbow）、长剑（longsword）、细剑（rapier）、短剑（short sword）、短弓（shortbow）或其他冠以“精灵（elven）”之名的武器。持用该种武器进行的重击确认检定获得+1/2加值（最高+4）。\n"
)

CLUSTER_O_FCB_SECTION_PREFIX = (
    "**伽瑟兰天赋职业选项**\n"
    "下述选项可以被所有选择了所列出天赋职业的伽瑟兰角色选取。\n"
    "天赋职业选项吟游诗人：在破咒曲和清心的表演检定中获得+1/3加值\n"
    "拳师：当使用啄击（啮咬）并作为次要天生武器进行攻击时，获得+1/2洞察加值（最大+3）\n"
)


class TestClusterO_FcbBare:
    """簇 O：FCB 裸职业行（无星壳 `职业：奖励`，BoS 剪影人 15/窃影鬼 14 条）
    必须独立切出 fcb_entry（M7）——修复前整节并入最后一条目"""

    def test_bare_occupation_rows_cut_fcb_entries(self):
        """剪影人形态：fcb_entry 态裸职业行 → 独立 fcb_entry 条目"""
        items = run(CLUSTER_O_FCB_BARE)
        fcbs = [it for it in items if it["kind"] == "fcb_entry"]
        assert [it["name"] for it in fcbs] == ["野蛮人", "牧师", "操念使", "女巫"], \
            f"4 条 FCB 全切出：{[(it['name'], it['kind']) for it in items]}"

    def test_fcb_text_full(self):
        """FCB 正文完整进 text（检索可达）"""
        items = run(CLUSTER_O_FCB_BARE)
        it = next(i for i in items if i["name"] == "野蛮人")
        assert "武器伤害检定上获得+1/4加值" in item_text(it)
        it = next(i for i in items if i["name"] == "操念使")
        assert "虚空注能和原力的DC+1/4" in item_text(it)

    def test_no_tail_contamination(self):
        """最后一条 FCB 不粘其他职业行（修复前整节并入最后条目）"""
        items = run(CLUSTER_O_FCB_BARE)
        it = next(i for i in items if i["name"] == "女巫")
        assert "野蛮人" not in item_text(it), "不得粘前序职业行"

    def test_title_body_line_not_cut(self):
        """标题独立成行后的正文行（page_13 `**猎人（Hunter）**` + 武器列表行）
        并入刚建的标题 cur——fcb_entry 态裸冒号行若 cur 空 text 是正文不是条目"""
        items = run(CLUSTER_O_FCB_TITLE_BODY)
        fcbs = [it for it in items if it["kind"] == "fcb_entry"]
        names = [it["name"] for it in fcbs]
        assert "猎人" in names, f"猎人条目应在：{names}"
        assert "从后述列表中选择一种武器" not in names, \
            f"武器列表行不得切伪条目：{names}"
        hunter = next(it for it in fcbs if it["name"] == "猎人")
        assert "长弓（longbow）" in item_text(hunter), "武器列表并入猎人正文"

    def test_section_keyword_prefix_not_cut(self):
        """行首含 fcb 章节关键字（BotB `天赋职业选项吟游诗人：`）不切伪条目——
        这是裸章节+条目粘连行（章节词在行首非行尾，裸章节拆行不覆盖）"""
        items = run(CLUSTER_O_FCB_SECTION_PREFIX)
        names = [it["name"] for it in items if it["kind"] == "fcb_entry"]
        assert not any(n.startswith("天赋职业选项") for n in names), \
            f"不得切 title 污染的伪条目：{names}"

CLUSTER_O_FCB_SIDEBAR_LINE = (
    "**藤蔓莱西可选天赋职业奖励（Favored Class Options）**\n"
    "**变形者（Shifter）**：在有关植物的知识（自然）检定中+1加值。\n"
    "引述: 边栏：种植藤蔓莱西\n"
    "藤蔓莱西生长最旺盛的地方是可以使她们接受充足的阳光的地方。\n"
)


class TestClusterO_FcbBare:
    """簇 O：FCB 裸职业行（无星壳 `职业：奖励`，BoS 剪影人 15/窃影鬼 14 条）
    必须独立切出 fcb_entry（M7）——修复前整节并入最后一条目"""

    def test_bare_occupation_rows_cut_fcb_entries(self):
        """剪影人形态：fcb_entry 态裸职业行 → 独立 fcb_entry 条目"""
        items = run(CLUSTER_O_FCB_BARE)
        fcbs = [it for it in items if it["kind"] == "fcb_entry"]
        assert [it["name"] for it in fcbs] == ["野蛮人", "牧师", "操念使", "女巫"], \
            f"4 条 FCB 全切出：{[(it['name'], it['kind']) for it in items]}"

    def test_fcb_text_full(self):
        """FCB 正文完整进 text（检索可达）"""
        items = run(CLUSTER_O_FCB_BARE)
        it = next(i for i in items if i["name"] == "野蛮人")
        assert "武器伤害检定上获得+1/4加值" in item_text(it)
        it = next(i for i in items if i["name"] == "操念使")
        assert "虚空注能和原力的DC+1/4" in item_text(it)

    def test_no_tail_contamination(self):
        """最后一条 FCB 不粘其他职业行（修复前整节并入最后条目）"""
        items = run(CLUSTER_O_FCB_BARE)
        it = next(i for i in items if i["name"] == "女巫")
        assert "野蛮人" not in item_text(it), "不得粘前序职业行"

    def test_title_body_line_not_cut(self):
        """标题独立成行后的正文行（page_13 `**猎人（Hunter）**` + 武器列表行）
        并入刚建的标题 cur——fcb_entry 态裸冒号行若 cur 空 text 是正文不是条目"""
        items = run(CLUSTER_O_FCB_TITLE_BODY)
        fcbs = [it for it in items if it["kind"] == "fcb_entry"]
        names = [it["name"] for it in fcbs]
        assert "猎人" in names, f"猎人条目应在：{names}"
        assert "从后述列表中选择一种武器" not in names, \
            f"武器列表行不得切伪条目：{names}"
        hunter = next(it for it in fcbs if it["name"] == "猎人")
        assert "长弓（longbow）" in item_text(hunter), "武器列表并入猎人正文"
        assert "细剑（rapier）" in item_text(hunter), "武器列表正文完整（不留伪条目残尾）"

    def test_section_keyword_prefix_not_cut(self):
        """行首含 fcb 章节关键字（BotB `天赋职业选项吟游诗人：`）不切伪条目——
        这是裸章节+条目粘连行（章节词在行首非行尾，裸章节拆行不覆盖）"""
        items = run(CLUSTER_O_FCB_SECTION_PREFIX)
        names = [it["name"] for it in items if it["kind"] == "fcb_entry"]
        assert not any(n.startswith("天赋职业选项") for n in names), \
            f"不得切 title 污染的伪条目：{names}"

    def test_sidebar_mark_line_not_cut(self):
        """边栏标记行（page_1456 `引述: 边栏：种植藤蔓莱西`）不切伪条目——
        组2 以「边栏」开头是边栏标题标记，非职业条目"""
        items = run(CLUSTER_O_FCB_SIDEBAR_LINE)
        names = [it["name"] for it in items if it["kind"] == "fcb_entry"]
        assert "引述" not in names, f"边栏标记行不得切伪条目：{names}"
        assert "变形者" in names, "FCB 变形者条目照常切出"

CLUSTER_O_FCB_STAR_CLOSED = (
    "**伽瑟兰天赋职业选项**\n"
    "下述选项可以被所有选择了所列出天赋职业的伽瑟兰角色选取。\n"
    "野蛮人：**野蛮人的伤害减免能力增加1/3（最高5/-）**\n"
    "**吟游诗人：**从德鲁伊法术列表中选择一个0环法术加入到吟游诗人已知法术列表中\n"
    "**拳师：**在使用紧身拳套攻击时获得+1/2洞察加值\n"
)


class TestClusterO_FcbStarClosed:
    """簇 O2：FCB 星壳闭职业行（`**职业：**正文`，page_814/815 伽瑟兰/蒿兰人 FCB）
    闭合星在冒号后，星壳开正则/裸版均不匹配——fcb_entry 态独立切出（M7）"""

    def test_star_closed_rows_cut_fcb_entries(self):
        """混合形态：裸职业行（正文带星壳）+ 星壳闭行全部独立切出"""
        items = run(CLUSTER_O_FCB_STAR_CLOSED)
        fcbs = [it for it in items if it["kind"] == "fcb_entry"]
        assert [it["name"] for it in fcbs] == ["野蛮人", "吟游诗人", "拳师"], \
            f"3 条 FCB 全切出：{[(it['name'], it['kind']) for it in items]}"

    def test_star_closed_text_full(self):
        """星壳闭正文剥壳完整进 text（检索可达）"""
        items = run(CLUSTER_O_FCB_STAR_CLOSED)
        it = next(i for i in items if i["name"] == "吟游诗人")
        assert "德鲁伊法术列表" in item_text(it), "正文完整进 text"
        assert "0环法术" in item_text(it)
        assert not item_text(it).startswith("**"), "星壳已剥"

    def test_mixed_no_contamination(self):
        """裸行与星壳闭行互不粘连（修复前 `**吟游诗人：**` 粘进「野蛮人」text）"""
        items = run(CLUSTER_O_FCB_STAR_CLOSED)
        it = next(i for i in items if i["name"] == "野蛮人")
        assert "吟游诗人" not in item_text(it), "裸行条目不得粘后续星壳闭行"
        assert "伤害减免能力增加1/3" in item_text(it), "裸行正文（带星壳）剥壳进 text"

# ============ 簇 P：PFS 禁用/修订尾注标题行（M8/KN114） ============

CLUSTER_P_PFS_TAIL = (
    "**矮人种族特性替换**\n"
    "**远古敌意（Ancestral Enmity）**\n"
    "矮人与精灵的冲突由来已久。此特性取代仇恨。\n"
    "**精类思维（Fey Thoughts）** PFS禁用\n"
    "此角色看待事物的方式与精类近似。此特性取代精灵抗性。\n"
    "**幽暗居民（Dimdweller）** PFS禁用\n"
    "矮人习惯了地底。此特性取代敏锐感知。\n"
)

CLUSTER_P_PFS_REVISION = (
    "**矮人种族特性替换**\n"
    "**勤劳城市人（Industrious Urbanite）**\n"
    "适应了居住城市需求的矮人能在制造非魔法物品的工艺检定中有双倍的进展。此特性取代仇恨。\n"
    "**钢铁公民（Iron Citizen）**（PFS修订：选择钢铁公民（Iron Citizen）的矮人必须同时以工匠（Craftsman）可选种族特性替换坚韧种族特性。［注：工匠（Craftsman）PFS不开］\n"
    "拥有此特性的矮人在交涉和察言观色检定获得+2加值。此特性取代稳固。\n"
)

CLUSTER_P_PFS_SOURCE_SAME_LINE = (
    "**侏儒种族特性替换**\n"
    "**修理者（Wright）** PFS禁用**出自《内海种族 pg. 211》**\n"
    "拥有此特性的侏儒可以在制造检定时…\n"
)


class TestClusterP_PfsTailNotes:
    """簇 P：PFS 禁用/修订尾注标题行——星壳闭合后尾注致 `_RE_TITLE` 失配，
    整行并入前一条目（矮人 6 处/半身人 5 处，全库 62 处）"""

    def test_pfs_tail_cut_entries(self):
        """`**X（EN）** PFS禁用` 独立切出条目（修复前粘进前一条目）"""
        items = run(CLUSTER_P_PFS_TAIL)
        traits = [it["name"] for it in items if it["kind"] == "alt_trait"]
        assert "精类思维" in traits and "幽暗居民" in traits, \
            f"PFS 禁用条目应切出：{traits}"

    def test_pfs_tail_no_contamination(self):
        """前一条目不粘 PFS 行（修复前 `**精类思维…** PFS禁用` 并入远古敌意）"""
        items = run(CLUSTER_P_PFS_TAIL)
        it = next(i for i in items if i["name"] == "远古敌意")
        assert "精类思维" not in item_text(it), "前条目不得粘后续 PFS 标题行"

    def test_pfs_tail_note_in_text(self):
        """PFS禁用 标记保留在该条目 text（检索端可查 PFS 状态）"""
        items = run(CLUSTER_P_PFS_TAIL)
        it = next(i for i in items if i["name"] == "精类思维")
        t = item_text(it)
        assert "PFS禁用" in t, "PFS 标记进 text"
        assert "此角色看待事物的方式与精类近似" in t, "正文完整进 text"

    def test_pfs_revision_note(self):
        """`**X（EN）**（PFS修订：…）` 长尾注拆行——条目独立 + 尾注入 text"""
        items = run(CLUSTER_P_PFS_REVISION)
        traits = [it["name"] for it in items if it["kind"] == "alt_trait"]
        assert "钢铁公民" in traits, f"钢铁公民应切出：{traits}"
        it = next(i for i in items if i["name"] == "钢铁公民")
        t = item_text(it)
        assert "PFS修订" in t and "工匠（Craftsman）" in t, "PFS修订说明进 text"
        assert "此特性取代稳固" in t, "正文完整进 text"
        prev = next(i for i in items if i["name"] == "勤劳城市人")
        assert "钢铁公民" not in item_text(prev), "前条目不得粘钢铁公民"

    def test_pfs_source_same_line(self):
        """同行粘连 `PFS禁用**出自《…》**` 拆行——条目独立、出自行不残留"""
        items = run(CLUSTER_P_PFS_SOURCE_SAME_LINE)
        traits = [it["name"] for it in items if it["kind"] == "alt_trait"]
        assert "修理者" in traits, f"修理者应切出：{traits}"
        it = next(i for i in items if i["name"] == "修理者")
        t = item_text(it)
        assert "PFS禁用" in t, "PFS 标记进 text"
        assert "出自" not in t, "出自行不残留进 text"

CLUSTER_P_PFS_SPACED_STAR = (
    "**半兽人种族特性替换**\n"
    "**此种族特性替换武器熟悉、威慑力**\n"
    "**萨满加持（Shaman Enhancement） ** PFS禁用\n"
    "**出自《第一世界遗产 pg. 5》**\n"
    "某些半兽人懂得能够增强盟友的力量与残暴的仪式。此种族特性替换武器熟悉和威慑力。\n"
    "**精类思维（Fey Thoughts） ** PFS禁用\n"
    "此角色看待世界时更像是第一世界的原居民。此特性取代仇恨。\n"
)


class TestClusterP_PfsSpacedStar:
    """簇 P 补：星内尾空格形态 `**X（EN） ** PFS禁用`（page_934 萨满加持/
    精类思维，HTML 转换残留 `） **`）——拆行时清星内空格使 `_RE_TITLE` 可匹配"""

    def test_spaced_star_cut(self):
        items = run(CLUSTER_P_PFS_SPACED_STAR)
        traits = [it["name"] for it in items if it["kind"] == "alt_trait"]
        assert "萨满加持" in traits and "精类思维" in traits, \
            f"空格形态应切出：{traits}"
        it = next(i for i in items if i["name"] == "萨满加持")
        assert "PFS禁用" in item_text(it), "PFS 标记进 text"

    def test_spaced_star_no_contamination(self):
        items = run(CLUSTER_P_PFS_SPACED_STAR)
        prev = next(i for i in items if i["name"] == "此种族特性替换武器熟悉、威慑力"
                    or "萨满加持" not in i["name"])
        for it in items:
            if it["name"] == "萨满加持":
                break
        # 哨兵行（此种族特性替换…）应作为前条目的替换说明，不得吞萨满加持标题
        sentinel = [i for i in items if "武器熟悉、威慑力" in str(i.get("replaces", ""))]
        for i in sentinel:
            assert "萨满加持" not in item_text(i), "前条目不得粘萨满加持"

# ============ 簇 Q：血脉亚种表格行 mega chunk 拆分（M6/KN118） ============

CLUSTER_Q_HERITAGE_TABLE = (
    "**神裔亚种（Aasimar Heritages）**\n"
    "大部分神裔都不知晓自己血脉的确切来源。角色可以在以下六种神裔种族特性中选择一种来替换原本的神裔种族特性。\n"
    "|  | 盖丁血脉（伊迪尔人）伊迪尔人同时具有兽性和冷静的性格。祖先：盖丁天族（Agathion）典型阵营：中立善良替换属性调整：+2体质，+2魅力替换技能加值：驯养动物，生存替换类法术能力：伊迪尔人获得二级召唤自然盟友。 |\n"
    "      和盖丁天族祖先一样，伊迪尔人用最纯粹的方式行善。\n"
    "| --- | --- |\n"
    "|  | 天使血脉（天使裔）天使是凡人心目中美丽和善良的代名词。祖先：天使（Angel）典型阵营：任意善良替换属性调整：+2力量，+2魅力替换技能加值：医疗，知识（位面）替换类法术能力：天使裔获得变身术。 |\n"
    "      天使血脉的神裔通常被称为天使裔。\n"
    "| --- | --- |\n"
    "|  | 神使血脉（秩序使者）秩序使者是正义的化身。祖先：神使天族（Archon）典型阵营：守序善良替换属性调整：+2体质，+2感知替换技能加值：威吓，察言观色替换类法术能力：秩序使者获得不灭明焰。 |\n"
    "      秩序使者和他们的神使天族祖先一样在日常生活中充满谨慎。\n"
    "| --- | --- |\n"
)

CLUSTER_Q_HERITAGE_TABLE_TIEFLING = (
    "**魔裔亚种（Tiefling Heritages）**\n"
    "大多数魔裔都表现出了类似的特征与能力。\n"
    "|  | 阿修罗后裔（咎恶族裔）咎恶族裔没有任何同情心或怜悯之情。祖先：阿修罗（Asura）典型阵营：守序邪恶替换属性调整：+2敏捷，+2感知，-2智力替换技能加值：估价，知识（地方）替换类法术能力：咎恶族裔获得狂笑术。 |\n"
    "      与他们的阿修罗祖先一样，咎恶族裔醉心于神祇与其信众的失败。\n"
    "| --- | --- |\n"
    "|  | 邪魔后裔（残忍族裔）残忍族裔对死亡、疾病与破败着迷。祖先：邪魔（Daemon）典型阵营：中立邪恶替换属性调整：+2敏捷，+2智力，-2感知替换技能加值：解除装置，巧手替换类法术能力：残忍族裔获得死亡丧钟。 |\n"
    "      残忍族裔与他们的邪魔祖先一样着魔于疾病与腐朽。\n"
    "| --- | --- |\n"
)


class TestClusterQ_HeritageTable:
    """簇 Q：血脉亚种表格行（`|  | 血脉名（中文）描述… |`）——神裔 6 血脉
    5102 字符/魔裔 10 血脉 8745 字符整段吞进 1 个 mega chunk（KN118/M6）"""

    def test_heritage_rows_cut(self):
        """表格行拆出独立血脉条目（修复前 6 血脉全在 1 个 mega chunk）"""
        items = run(CLUSTER_Q_HERITAGE_TABLE)
        names = [it["name"] for it in items if it["kind"] in ("race_trait", "race_intro")]
        for n in ("盖丁血脉", "天使血脉", "神使血脉"):
            assert n in names, f"血脉应切出：{names}"

    def test_heritage_desc_merged(self):
        """缩进描述段并入对应血脉条目（祖先字段链 + 描述同条目）"""
        items = run(CLUSTER_Q_HERITAGE_TABLE)
        it = next(i for i in items if i["name"] == "盖丁血脉")
        t = item_text(it)
        assert "祖先：盖丁天族（Agathion）" in t, "祖先字段链进 text"
        assert "和盖丁天族祖先一样" in t, "描述段并入血脉条目"
        assert "典型阵营" in t and "替换属性调整" in t, "字段链完整"

    def test_heritage_no_table_marks(self):
        """`|  | ` 表格前缀与 `| --- |` 分隔行不残留"""
        items = run(CLUSTER_Q_HERITAGE_TABLE)
        for it in items:
            assert "| ---" not in item_text(it), f"分隔行残留：{it['name']}"
            assert "|  |" not in item_text(it), f"表格前缀残留：{it['name']}"

    def test_heritage_tiefling_rows(self):
        """魔裔亚种 10 血脉同构——切出且字段链完整"""
        items = run(CLUSTER_Q_HERITAGE_TABLE_TIEFLING)
        names = [it["name"] for it in items if it["kind"] in ("race_trait", "race_intro")]
        assert "阿修罗后裔" in names and "邪魔后裔" in names, f"魔裔血脉应切出：{names}"
        it = next(i for i in items if i["name"] == "阿修罗后裔")
        t = item_text(it)
        assert "祖先：阿修罗（Asura）" in t and "替换属性调整：+2敏捷" in t
        assert "与他们的阿修罗祖先一样" in t


# ============ 簇 R：种族 H2 state 重置（M9/KN127） ============
# 多种族聚合文件（ISR 新种族 3 族 / BotB 6 族 / BotS 3 族）：第 2 个种族起
# H2 标题不重置 state——被按残留章节态（alt_trait/fcb_entry）切 kind，
# race_name 全继承第一个种族（KN127）。两类信号：
#   ① `<!-- xxx-source:…:种族名 -->` 整理注释（ISR/CtIE/BotS 逐种族注释）
#   ② 裸中文行 + 散文段（BotB `**猫族**　　散文` 同行拆行形态 / 剪影人
#      `## 剪影人` H2 形态）——标题行建 cur 后首行并入散文 → 升级 race_intro
CLUSTER_R_ISR_MULTI_RACE = (
    "## 绪任克斯枭族（Syrinx）\n"
    "> 来源：内海种族（Inner Sea Races）ISR，页码见原书，未整理 → ISR → 种族\n"
    "**+2感知，-2敏捷**：绪任克斯枭族善于沉思具有耐心。\n"
    "**标准速度（Normal Speed）**：绪任克斯枭族的基本速度为30尺。\n"
    "**绪任克斯枭族种族特性替换（Syrinx Alternate Racial Traits）**\n"
    "**残酷压迫（Oppressive）**：此种族特性替换夜行生物和自负。\n"
    "<!-- ISR-source:新种族/page_1599.md:勒珊塔灵族 -->\n"
    "## 勒珊塔灵族（Lashunta）\n"
    "> 来源：内海种族（Inner Sea Races）ISR，页码见原书，未整理 → ISR → 种族\n"
    "**勒珊塔灵族角色（Lashunta Characters，11 RP）**：拉申塔人是由他们的职业等级来定级的。\n"
    "**两性异形（Sexual Dimorphism）**：男性和女性勒珊塔灵族的身心具备差异性。\n"
    "**语言（Languages）**：勒珊塔灵族语以及精灵语。\n"
    "**勒珊塔灵族种族特性替换（Lashunta Alternate Racial Traits）**\n"
    "**狡诈心灵感应（Insidious Telepathy）**：所有基于魅力的技能检定+1。\n"
)

CLUSTER_R_BOTB_MULTI_RACE = (
    "## 种族特性\n"
    "**猫族**　　因为有着过分的求知欲，猫族在格拉里昂是一群卓越的流浪家。\n"
    "出身于奥斯里昂的猫族可以选择以下背景：\n"
    "**古代奥斯里昂信徒（地区）**：你将手甲钩视作军用武器而不是异种武器。\n"
    "**种族特性替换**\n"
    "**敏锐狐妖（Keen Kitsune）**：这样的狐妖在敏捷和智力上+2。\n"
    "**天赋职业选项**\n"
    "**炼金术师**：获得1/6个科研发现。\n"
    "**狐妖**　　尽管居住在天夏的狐妖有着最多的人口。\n"
    "出身于瓦里西安的狐妖可以选择下列背景：\n"
    "**篷车牧民（地区）**：你的家族在瓦里西安的广阔大道上生活了无数世代。\n"
)

CLUSTER_R_BARE_H2 = (
    "## 剪影人\n"
    "> 来源：阴影血脉（Blood of Shadows）BoS，页码见原书，未整理 → 阴影血脉BoS → 剪影人种族特性\n"
    "光明转化\n"
    "在黑暗纪元的末尾，剪影人的历史被孤独的悲哀所感染。\n"
    "**阴影护甲（Shadowy Armor）**：剪影人依靠与阴影位面的联系获得+2护甲加值。\n"
)


class TestClusterR_RaceH2Reset:
    """簇 R：种族 H2 state 重置（M9）——多种族文件第 2 个种族起不被残留
    章节态误标 kind、race_name 归属正确（KN127）"""

    def test_comment_h2_reset_state(self):
        """注释信号 + H2 带括号：勒珊塔灵族切 race_intro，后续特性恢复
        race_trait（修复前 alt_trait 态残留，整段误标 alt_trait）"""
        items = run(CLUSTER_R_ISR_MULTI_RACE)
        by_name = {it["name"]: it["kind"] for it in items}
        assert by_name.get("勒珊塔灵族") == "race_intro", \
            f"种族 H2 应切 race_intro：{by_name}"
        assert by_name.get("两性异形") == "race_trait", \
            f"state 重置后特性应 race_trait：{by_name}"
        assert by_name.get("语言") == "race_trait"
        assert by_name.get("狡诈心灵感应") == "alt_trait", \
            f"后续特性替换章节仍生效：{by_name}"

    def test_comment_h2_first_race_unchanged(self):
        """文件首个种族 H2（intro 态）行为不变——绪任克斯枭族 race_intro"""
        items = run(CLUSTER_R_ISR_MULTI_RACE)
        by_name = {it["name"]: it["kind"] for it in items}
        assert by_name.get("绪任克斯枭族") == "race_intro"
        assert by_name.get("标准速度") == "race_trait"
        assert by_name.get("残酷压迫") == "alt_trait"

    def test_botb_bare_title_upgrade(self):
        """BotB 裸中文+散文同行：狐妖切 race_intro 且 state 重置——背景
        （篷车牧民）race_trait、替换特性（敏锐狐妖）alt_trait、FCB（炼金
        术师）fcb_entry（修复前狐妖被残留 fcb_entry 态误标）"""
        items = run(CLUSTER_R_BOTB_MULTI_RACE)
        by_name = {it["name"]: it["kind"] for it in items}
        assert by_name.get("狐妖") == "race_intro", \
            f"狐妖种族名应升级 race_intro：{by_name}"
        assert by_name.get("篷车牧民") == "race_trait", \
            f"state 重置后背景特性应 race_trait：{by_name}"
        assert by_name.get("敏锐狐妖") == "alt_trait"
        assert by_name.get("炼金术师") == "fcb_entry"
        assert by_name.get("猫族") == "race_intro", \
            f"intro 态裸中文种族名应 race_intro（非 race_sidebar）：{by_name}"
        assert by_name.get("古代奥斯里昂信徒") == "race_trait"

    def test_bare_h2_upgrade(self):
        """剪影人裸中文 H2 + 散文：保持 race_sidebar（既有行为——D 簇怪物
        主条目依赖 sidebar 形态映射 monster_block；M9 曾加 h2_line 升级致
        12 个 monster_block 误抢成 race_intro，回归验证后移除升级）"""
        items = run(CLUSTER_R_BARE_H2)
        by_name = {it["name"]: it["kind"] for it in items}
        assert by_name.get("剪影人") == "race_sidebar", f"剪影人应 race_sidebar：{by_name}"
        assert by_name.get("阴影护甲") == "race_trait"

    def test_star_hash_section(self):
        """星包哈希章节（`**## 种族特性**`，BotB normalize 产物）剥壳——
        `_wrap_bare_cn_en_allcaps` 先包星致 H2 规则失配的补修"""
        fmt = RaceFormat()
        text = fmt.normalize("## 种族特性\n")
        assert "**## 种族特性**" not in text, f"星包哈希应剥壳：{text!r}"
        assert "**种族特性**" in text


# ============ 簇 S：elided 空行不触发散文升级（M9 回归） ============

CLUSTER_S_ELIDED_BLANK_UPGRADE = (
    "**种族职业变体（Racial Archetypes）**\n"
    "**娜迦**\n"
    "[[fc:elided]]\n"
    "**候选者（Naga Aspirant，德鲁伊变体）**\n"
    "娜迦候选者遵从着古老的信仰并从事着德鲁伊教传统仪式。\n"
    "**候选者之纽带（Aspirant’**s Bond, Ex）**\n"
    "娜迦候选者与娜迦所崇拜的蛇神之间形成了一种精神联系。\n"
)


class TestClusterS_ElidedBlankUpgrade:
    """簇 S：`[[fc:elided]]` 剥后空行不落散文升级分支（M9/KN127 回归）。

    page_26「娜迦候选者」进阶职业：`**娜迦****候选者（…）**` 粘连经
    normalize 拆出 `**娜迦**`（裸中文壳）+ `[[fc:elided]]` + 完整标题。
    elided 行剥后为空、原实现无 continue → 空行落进散文升级分支，判据
    对空行全过（`any(w in "" for w in …)` 恒 False）→ 无辜壳被升级
    race_intro 且 state 被重置 intro → 后续候选者/变身/亮鳞膏全部误标
    race_intro（修复前 page_26 4 个误标）。
    """

    def test_elided_blank_line_keeps_state(self):
        """候选者（种族职业变体章节后）应保持残留态 race_archetype——
        修复前 elided 空行升级触发 state=intro，候选者被误标 race_intro"""
        items = run(CLUSTER_S_ELIDED_BLANK_UPGRADE)
        by_name = {it["name"]: it["kind"] for it in items}
        assert by_name.get("候选者") == "race_archetype", \
            f"候选者应保持 race_archetype（残留态），不得被升级 race_intro：{by_name}"
        assert by_name.get("候选者之纽带") == "race_archetype", \
            f"变体职业能力条目随残留态 race_archetype（非 race_trait）：{by_name}"

    def test_elided_bare_shell_not_upgraded(self):
        """粘连拆出的「娜迦」裸中文壳（race_archetype 残留态）不得被空行
        升级——壳被 dedup 弹掉（_elided 标记），不产出 race_intro"""
        items = run(CLUSTER_S_ELIDED_BLANK_UPGRADE)
        intro = [it["name"] for it in items if it["kind"] == "race_intro"]
        assert "娜迦" not in intro, \
            f"裸中文壳不得升级 race_intro：{intro}"
        assert all(it["name"] != "娜迦" for it in items), \
            f"空 text 壳应被 dedup 弹掉：{[(it['name'], it['kind']) for it in items]}"


CLUSTER_S_TITLE_LINE_UPGRADE = (
    "**种族职业变体（Racial Archetypes）**\n"
    "**毒性**\n"
    "啮咬（Venomous Bite, Ex）\n"
    "娜迦形态的啮咬攻击会造成毒素伤害。\n"
    "**真娜迦（True Naga, Su）**\n"
    "20级时，娜迦候选者变为一名独特的娜迦。\n"
    "**娜迦裔奇物（Nagaji Magic Items）**\n"
    "**亮鳞膏（Nagaji Scale Polish）**\n"
    "这个小泥罐中容纳着闪亮的软膏。\n"
)


class TestClusterS_TitleLineNoUpgrade:
    """簇 S2：散文升级的标题形态守卫——裸中文条目后跟标题形态行
    （`啮咬（Venomous Bite, Ex）`/`物（Nagaji Magic Items）`）不是
    散文，不得升级 race_intro；升级行是 BotB 型整句散文才升级"""

    def test_title_line_not_upgraded(self):
        items = run(CLUSTER_S_TITLE_LINE_UPGRADE)
        intro = [it["name"] for it in items if it["kind"] == "race_intro"]
        assert not intro, \
            f"标题形态行不触发升级，不得产出 race_intro：{intro}"
        by_name = {it["name"]: it["kind"] for it in items}
        assert by_name.get("啮咬") == "race_archetype", \
            f"能力条目保持残留态：{by_name}"
        assert by_name.get("真娜迦") == "race_archetype", \
            f"state 未被误重置，真娜迦保持残留态：{by_name}"
        assert by_name.get("亮鳞膏") == "race_item", \
            f"亮鳞膏不被 intro 态误标：{by_name}"

    def test_botb_sentence_still_upgrades(self):
        """BotB 型整句散文升级不受影响"""
        items = run(CLUSTER_R_BOTB_MULTI_RACE)
        by_name = {it["name"]: it["kind"] for it in items}
        assert by_name.get("狐妖") == "race_intro", \
            f"BotB 整句散文仍应升级：{by_name}"


# ============ 簇 S3：stat block 属性行不触发散文升级（M9 回归） ============
# page_16 半身人真实形态：normalize 把属性调整行拆成裸标题 `**敏捷**`
# + 值行（`+2**，魅力**+2**，力量****-2**：半身人灵巧…` 数字开头）。
# 散文升级分支误把 stat block 字段当 BotB 散文升级 race_intro +
# state=intro → 后续 stat block 字段（小型体型/缓慢速度/武器熟悉/
# 起始语言）全部被并入「敏捷」条目（M9 回归实证，HEAD 版正常独立）。

CLUSTER_S3_ABILITY_ROW = (
    "**半身人（Halflings）**\n"
    "天性乐观、永远微笑，被漫游癖所驱策的半身人小小的身体里蕴藏着勇气。\n"
    "**半身人种族特性（Halfling Racial Traits）**\n"
    "**敏捷**\n"
    "+2**，魅力**+2**，力量****-2**：半身人灵巧而坚强，只是小巧的体型限制了他们的力量。\n"
    "**小型体型**：半身人是小型体型生物，AC获得+1体型加值。\n"
    "**缓慢速度**：半身人的基本陆地速度为20尺。\n"
    "**武器熟悉**：半身人擅长投石索，并将任何冠以“半身人”之名的武器视为军用武器。\n"
    "**起始语言**：通用语和半身人语。\n"
)


class TestClusterS3_AbilityRowNoUpgrade:
    """簇 S3：stat block 属性调整行（裸标题 + 数字值行）不得被散文升级
    误抢 race_intro——值行剥星后数字开头，既有标题形态守卫
    （`^[一-鿿]{1,8}[（(]`）不拦截，需补数字行判据（M9 回归：page_16
    「敏捷」被升级 race_intro 且 4 个 stat block 字段被并入丢失）"""

    def test_ability_row_not_upgraded(self):
        items = run(CLUSTER_S3_ABILITY_ROW)
        intro = [it["name"] for it in items if it["kind"] == "race_intro"]
        assert intro == ["半身人"], \
            f"仅种族主条目是 race_intro，stat block 字段不得升级：{intro}"
        by_name = {it["name"]: it["kind"] for it in items}
        assert by_name.get("敏捷") == "race_trait", \
            f"属性调整字段保持 stat block 字段语义（race_trait）：{by_name}"
        for field in ("小型体型", "缓慢速度", "武器熟悉", "起始语言"):
            assert by_name.get(field) == "race_trait", \
                f"stat block 字段不得被并入上一字段条目：{field} → {by_name.get(field)}"

    def test_ability_text_kept_in_own_item(self):
        """值行文本留在「敏捷」条目内，不并入后续字段"""
        items = run(CLUSTER_S3_ABILITY_ROW)
        by_name = {it["name"]: it["text"] for it in items}
        assert "半身人灵巧而坚强" in by_name.get("敏捷", ""), \
            f"值行应并入「敏捷」条目 text：{by_name.get('敏捷', '')[:60]!r}"
        assert "小型体型生物" in by_name.get("小型体型", ""), \
            f"字段正文留在各自条目：{by_name.get('小型体型', '')[:60]!r}"


# ============ 簇 S4：无汉字符号行不触发散文升级（M9 回归） ============
# page_163 血族武器区：速查行拆行残留 `**沙包**】` → normalize 后
# `**沙包**`（裸标题）+ `】`（符号独立行）。散文升级判据对符号行全过
# （标题/数字守卫都不拦截）→ 「沙包」误升级 race_intro 并重置 state
# → 后续「**弱点**：…」字段被吞并入「沙包」（M9 回归实证，HEAD 版
# 「弱点」独立条目）。升级行须含中文字符（散文必有汉字，符号/纯
# 英文/标点行零误伤）。

CLUSTER_S4_SYMBOL_LINE = (
    "**吸血裔装备（Dhampir Equipment）**\n"
    "**穿心弩箭（Bolts）**\n"
    "穿心弩箭由实心黑木特制而成，专门用于猎杀吸血鬼。\n"
    "**沙包**\n"
    "】\n"
    "**弱点**：吸血鬼无法忍受强烈的大蒜气味，所以不会接近有那种玩意儿的地方。\n"
    "**护颈**\n"
    "护颈用于保护颈部的皮革圈。\n"
)


class TestClusterS4_SymbolLineNoUpgrade:
    """簇 S4：无汉字符号行（`】` 速查残留）不得触发散文升级——升级行
    须是中文散文形态（BotB 型），符号/标点/纯英文行拦截"""

    def test_symbol_line_not_upgraded(self):
        items = run(CLUSTER_S4_SYMBOL_LINE)
        by_name = {it["name"]: it["kind"] for it in items}
        assert by_name.get("沙包") == "race_item", \
            f"武器条目保持条目流态，不得升级 race_intro：{by_name}"
        assert by_name.get("弱点") == "race_item", \
            f"「弱点」行不得被吞并入「沙包」，保持独立条目：{by_name}"
        assert by_name.get("护颈") == "race_item", \
            f"后续标题不被 intro 态误标：{by_name}"

    def test_symbol_line_kept_in_text(self):
        """符号残留并入原条目 text，不丢失"""
        items = run(CLUSTER_S4_SYMBOL_LINE)
        by_name = {it["name"]: it["text"] for it in items}
        assert "】" in by_name.get("沙包", ""), \
            f"符号行并入「沙包」text：{by_name.get('沙包', '')[:40]!r}"


# ============ 簇 T：M10 BotS 裸特性行家族（海洋之血 2026-08-04） ============

CLUSTER_T_SEGARAN = (
    "**塞卡利亚种族特性**\n"
    "由于塞卡利亚是罕见且强大的魔物，只有在获得GM的许可后，才可以扮演此种族的角色。PC 塞卡利亚具有以下种族特性：\n"
    "+2 敏捷，+2 感知，-2 \n"
    "智力：塞卡利亚灵巧并富有洞察力，但容易分心。\n"
    "人形怪物（Monstrous \n"
    "Humanoid）：塞卡利亚属于人形怪物，水生（aquatic）子类。\n"
    "中型体型：塞卡利亚是中型生物，不因体型而获得任何加值或惩罚。\n"
    "黑暗视觉：塞卡利亚拥有60尺范围的黑暗视觉。\n"
    "触手感知（1 \n"
    "RP）：当游泳且未被擒抱或擒抱他人时，塞卡利亚可以用一个迅捷动作展开触须，形成感知网。这赋予其10尺范围的盲感，持续时间为专注，或直到其用触须攻击或移动为止。\n"
    "天生护甲：塞卡利亚拥有+2天生护甲加值。\n"
    "喷射推进（1 \n"
    "RP）：塞卡利亚可以在一个整轮动作中向后游动200英尺。喷射时必须直线移动，且不会引发借机攻击。\n"
    "语言：塞卡利亚初始掌握水族语与通用语。智力高的塞卡利亚可以从以下语言中选择：邪灵语、天界语、龙语、精灵语、巨人语、侏儒语和半身人语。\n"
)

CLUSTER_T_SOLEIL = (
    "**梭螺鱼人种族特性**\n"
    "梭螺鱼人是特殊角色，仅在GM允许的情况下才能作为玩家角色。下列能力为《怪物图鉴2》中梭螺鱼人的近似版本，可能不完全一致：\n"
    "属性调整：+2 \n"
    "力量、+2 魅力、-2 敏捷：梭螺鱼人强壮、富有感染力，但动作不够灵活。\n"
    "异界生物：梭螺鱼人为本地异界生物，具有水元素子类型。\n"
    "中体型：梭螺鱼人为中型生物。\n"
    "黑暗视觉：梭螺鱼人拥有60英尺黑暗视觉。\n"
    "微光视觉：梭螺鱼人在昏暗光照下视野是人类的两倍。\n"
    "语言：梭螺鱼人初始会说水族语与通用语。\n"
)

CLUSTER_T_GRINDA = (
    "**海地精种族特性**\n"
    "玩家角色的海地精拥有以下种族特性：\n"
    "属性调整： \n"
    "+4 敏捷，-2 智力，-2 感知，-2 \n"
    "魅力。海地精残忍、无知且冲动，但天生极为灵活。\n"
    "异怪：海地精属于异怪，具有水栖子类型。\n"
    "小型体型（Small）： \n"
    "海地精为小型生物，获得以下体型调整：+1 AC加值。\n"
    "游泳速度（Swim Speed）： 游泳速度为30英尺。\n"
    "喷射（Jet）（1 RP）： \n"
    "海地精可以在一个整轮动作中向后以直线方向喷射游动200英尺。使用此能力不会引发借机攻击。\n"
    "啮咬攻击（Bite）： \n"
    "拥有1d3伤害的天生啮咬攻击。\n"
)


CLUSTER_T_SEGARAN_ALT = (
    "**塞卡利亚种族特性**\n"
    "由于塞卡利亚是罕见且强大的魔物，只有在获得GM的许可后，才可以扮演此种族的角色。\n"
    "替代墨汁云：\n"
    "灵巧触须（Dexterous \n"
    "Tentacles）\n"
    "来源：《海洋血脉》第7页  \n"
    "\n"
    "有些塞卡利亚天生拥有两条触须。拥有此特性的塞卡利亚不再具有墨汁云能力。\n"
)


class TestClusterT_BotsBareTrait:
    """簇 T：BotS 裸特性行家族（M10）——无星壳中文特性行/属性调整断行/
    数字括号 RP 标注，全并入前条目的回归修复"""

    def test_segaran_alt_trait_no_elided(self):
        """塞卡利亚替代特性段 `替代墨汁云：\\n灵巧触须（Dexterous \\nTentacles）
        \\n来源：…\\n正文`——跨行英文断行合并 + 英文名并入「替代墨汁云」
        条目（洛卡鱼人 [0057] 同构），任何条目 text 不得含
        `[[fc:elided]]` 残留（M10 星壳粘连链）"""
        items = run(CLUSTER_T_SEGARAN_ALT)
        for it in items:
            assert "[[fc:elided]]" not in item_text(it), \
                f"{it['name']} text 不得含 elided 残留：{item_text(it)[:50]!r}"

    def test_segaran_alt_replacement_title_filled(self):
        """`替代墨汁云：` 裸冒号行 → 独立条目，text 含英文名（断行合并）、
        来源与正文（不得空 text，不产「灵巧触须」伪独立条目）"""
        items = run(CLUSTER_T_SEGARAN_ALT)
        by_name = {i["name"]: i for i in items}
        it = by_name.get("替代墨汁云")
        assert it is not None, f"替代墨汁云应独立条目：{[i['name'] for i in items]}"
        t = item_text(it)
        assert "灵巧触须（Dexterous Tentacles）" in t, f"英文名并入：{t[:60]!r}"
        assert "有些塞卡利亚" in t, f"正文并入：{t[:60]!r}"
        assert "来源" in t, f"来源行并入：{t[:60]!r}"
        assert "灵巧触须" not in by_name, \
            f"灵巧触须是替代墨汁云的英文名非独立条目：{[i['name'] for i in items]}"

    def test_segaran_ability_adj_merged(self):
        """塞卡利亚 `+2 敏捷，+2 感知，-2 \\n智力：正文` 断行合并 → 属性调整
        独立条目，text 含值与正文"""
        items = run(CLUSTER_T_SEGARAN)
        by_name = {it["name"]: it for it in items}
        it = by_name.get("属性调整")
        assert it is not None, f"属性调整应独立条目：{[i['name'] for i in items]}"
        assert it["kind"] == "race_trait"
        t = item_text(it)
        assert "智力：塞卡利亚灵巧" in t, f"值+正文完整：{t[:60]!r}"

    def test_segaran_paren_digit_trait(self):
        """`触手感知（1 \\nRP）：正文` / `喷射推进（1 \\nRP）：` 断行合并 +
        数字括号转星 → 独立条目"""
        items = run(CLUSTER_T_SEGARAN)
        names = [i["name"] for i in items]
        assert "触手感知" in names, f"触手感知应独立：{names}"
        assert "喷射推进" in names, f"喷射推进应独立：{names}"

    def test_segaran_bare_cn_trait(self):
        """`中型体型：正文` / `黑暗视觉：` / `天生护甲：` 裸中文冒号行 → 独立条目"""
        items = run(CLUSTER_T_SEGARAN)
        names = [i["name"] for i in items]
        for want in ("中型体型", "黑暗视觉", "天生护甲", "语言"):
            assert want in names, f"{want} 应独立条目：{names}"

    def test_segaran_bare_paren_en_trait(self):
        """`人形怪物（Monstrous \\nHumanoid）：正文` 断行+裸括号 → 独立条目，
        text 不以 `：` 开头"""
        items = run(CLUSTER_T_SEGARAN)
        by_name = {i["name"]: i for i in items}
        it = by_name.get("人形怪物")
        assert it is not None, f"人形怪物应独立条目：{[i['name'] for i in items]}"
        assert not item_text(it).lstrip().startswith("："), \
            f"text 不得以冒号开头：{item_text(it)[:40]!r}"

    def test_segaran_no_pseudo_trait(self):
        """断行合并不得产出伪条目（`智力`/`敏捷` 值行碎片）"""
        items = run(CLUSTER_T_SEGARAN)
        names = [i["name"] for i in items]
        assert "智力" not in names, f"「智力」是值行碎片非条目：{names}"
        assert "RP" not in names, f"「RP」断行碎片非条目：{names}"

    def test_soleil_ability_adj_label(self):
        """梭螺鱼人 `属性调整：+2 \\n力量、…` 标签形态断行合并 → 属性调整
        独立条目，text 含值"""
        items = run(CLUSTER_T_SOLEIL)
        by_name = {it["name"]: it for it in items}
        it = by_name.get("属性调整")
        assert it is not None, f"属性调整应独立条目：{[i['name'] for i in items]}"
        assert "力量" in item_text(it), f"值进 text：{item_text(it)[:50]!r}"

    def test_soleil_bare_cn_traits(self):
        """梭螺鱼人全裸特性行（异界生物/中体型/黑暗视觉/微光视觉/语言）独立"""
        items = run(CLUSTER_T_SOLEIL)
        names = [i["name"] for i in items]
        for want in ("异界生物", "中体型", "黑暗视觉", "微光视觉", "语言"):
            assert want in names, f"{want} 应独立条目：{names}"

    def test_grinda_jet_dual_paren(self):
        """海地精 `喷射（Jet）（1 RP）：正文` 双括号 → 独立条目（不得并入
        游泳速度）"""
        items = run(CLUSTER_T_GRINDA)
        by_name = {i["name"]: i for i in items}
        it = by_name.get("喷射")
        assert it is not None, f"喷射应独立条目：{[i['name'] for i in items]}"
        assert it["kind"] == "race_trait"
        swim = by_name.get("游泳速度", {})
        assert "喷射" not in item_text(swim), \
            f"喷射不得并入游泳速度：{item_text(swim)[:50]!r}"

    def test_grinda_bare_cn_trait(self):
        """海地精 `异怪：正文` 裸无括号行 → 独立条目"""
        items = run(CLUSTER_T_GRINDA)
        names = [i["name"] for i in items]
        assert "异怪" in names, f"异怪应独立条目：{names}"

    def test_grinda_ability_adj_label_blank(self):
        """海地精 `属性调整： \\n+4 敏捷…` 空正文标签 → 属性调整条目，
        值行并入 text（不产空 text 条目）"""
        items = run(CLUSTER_T_GRINDA)
        by_name = {i["name"]: i for i in items}
        it = by_name.get("属性调整")
        assert it is not None, f"属性调整应独立条目：{[i['name'] for i in items]}"
        assert "敏捷" in item_text(it), f"值行并入：{item_text(it)[:50]!r}"
        assert it.get("text", "").strip(), f"text 非空：{it!r}"

    def test_grinda_jet_text_no_colon_lead(self):
        """`喷射（Jet）（1 RP）： ` 双括号+冒号行——text 不得以 `：` 开头

        `_wrap_bare_paren_lines`（公共 A 分支）把 `（1 RP）： ` 当 tail 拆行
        → `_normalize_whitespace_title` 跨行合并 `（1 RP）` 回标题、`： `
        剩独立行 → text 以冒号开头污染。守卫：rest 含 `）:` 形态不拆，
        留给 `_wrap_bare_paren_colon_titles` 整行转星（split `_RE_TITLE`
        组4 剥冒号）。
        """
        items = run(CLUSTER_T_GRINDA)
        by_name = {i["name"]: i for i in items}
        it = by_name.get("喷射")
        assert it is not None, f"喷射应独立条目：{[i['name'] for i in items]}"
        t = item_text(it)
        assert not t.lstrip().startswith("："), f"text 不得以冒号开头：{t[:40]!r}"
        assert "海地精可以" in t, f"正文完整：{t[:60]!r}"

CLUSTER_U_SPLIT_CN_NAME = (
    "**地精（Goblin）**\n"
    "**地精种族****特性（****Goblin Racial Traits）**\n"
    "**地精自燃****术（****Fire Body, Ex****）**：8级时，地精可以释放出一团火焰。\n"
    "**精通地精自燃****术（****Improved Fire Body, Ex****）**：10级时，火焰更加炽烈。\n"
    "**高等地精****自燃术（****Greater Fire Body, Ex****）**：14级时，火焰波及范围更广。\n"
    "**地精铳****士（****Goblin Gunslinger****）〔战斗〕**：你学会使用火枪进行战斗。\n"
    "**灌魔恶臭****墨水（****Stink Ink, Arcane****）**：你可以制造恶臭墨水。\n"
)


class TestClusterU_SplitCnNameMerge:
    """簇 U：HTML 加粗段拆裂中段分裂（M10 收尾）——`**高等地精****自燃术（****
    Greater Fire Body, Ex****）**` 中文名被相邻加粗段拆成两段，正确语义是
    **合并**成单标题「高等地精自燃术（Greater Fire Body, Ex）」，而非
    `_split_quad_glue_titles` 拆行成的「高等地精」空壳 +「自燃术」伪条目"""

    def test_split_name_h2_shell_popped(self):
        """`**地精（Goblin）**` H2 壳 + 章节行 → 壳被弹（不产空 text 的
        race_intro「地精」），章节行被合并并识别为章节态"""
        items = run(CLUSTER_U_SPLIT_CN_NAME)
        names = [i["name"] for i in items]
        assert "地精" not in names, f"H2 壳应被弹：{names}"
        assert "地精自燃术" in names, f"章节后特性条目正常切出：{names}"

    def test_split_name_merged_single_entry(self):
        """`**地精自燃****术（****EN****）**` → 「地精自燃术」单条目，text 含
        正文；不产「地精自燃」/「术」伪条目；全部条目 text 非空"""
        items = run(CLUSTER_U_SPLIT_CN_NAME)
        by_name = {i["name"]: i for i in items}
        it = by_name.get("地精自燃术")
        assert it is not None, f"地精自燃术应合并为单条目：{[i['name'] for i in items]}"
        assert "8级时" in item_text(it), f"正文并入：{item_text(it)[:60]!r}"
        assert "地精自燃" not in by_name, \
            f"「地精自燃」是拆裂碎片非条目：{[i['name'] for i in items]}"
        assert "术" not in by_name, f"「术」是拆裂碎片非条目：{[i['name'] for i in items]}"
        for i in items:
            assert i.get("text", "").strip(), f"{i['name']} text 非空"

    def test_split_name_single_char_first_segment(self):
        """`**猎****巫人（****Magehunter****）**` 段1 单字（HTML 拆裂处无
        词语边界）→ 合并「猎巫人」单条目，不得拆成「猎」+「巫人」伪条目
        （KN133 大地精 page_167 标题劈半 2 处之一）"""
        items = run("**猎****巫人（****Magehunter****）**：大地精对施法者又惧又恨。\n")
        by_name = {i["name"]: i for i in items}
        it = by_name.get("猎巫人")
        assert it is not None, f"猎巫人应合并：{[i['name'] for i in items]}"
        assert "又惧又恨" in item_text(it), f"正文并入：{item_text(it)[:50]!r}"
        assert "猎" not in by_name and "巫人" not in by_name, \
            f"不得拆出伪条目：{[i['name'] for i in items]}"

    def test_split_name_double_quad_star_segments(self):
        """`**狐妖之****魅****（****Kitsune's Charm, Sp****）**` 段间双 4 星 +
        （ 前 4 星 → 合并「狐妖之魅」单条目（KN133 狐妖之魅破损，P1）"""
        items = run("**狐妖之****魅****（****Kitsune’s Charm, Sp****）**：3级起，狐妖欺诈者能够以类法术能力每日使用1次‘魅惑人类’。\n")
        by_name = {i["name"]: i for i in items}
        it = by_name.get("狐妖之魅")
        assert it is not None, f"狐妖之魅应合并：{[i['name'] for i in items]}"
        assert "魅惑人类" in item_text(it), f"正文并入：{item_text(it)[:50]!r}"
        assert "狐妖之" not in by_name and "魅" not in by_name, \
            f"不得拆出伪条目：{[i['name'] for i in items]}"

    def test_split_name_cross_line_en_double_quad_star(self):
        """`**狐妖之****魅****（****Kitsune's**** \nCharm, ****Sp****）**` 跨行
        EN 双段形态（page_25 真实形态）：`_merge_cross_line_en` 合并 EN 后
        类型段 `Sp` 后仍有一组 4 星再接 `）`——类型段后须有星容差才能归一
        （KN133 狐妖之魅 P1 真实文件的最后残留形态）"""
        items = run("**狐妖之****魅****（****Kitsune’s**** \nCharm, ****Sp****）**：3级起，狐妖欺诈者能够以类法术能力每日使用1次‘魅惑人类’。\n")
        by_name = {i["name"]: i for i in items}
        it = by_name.get("狐妖之魅")
        assert it is not None, f"狐妖之魅应合并：{[i['name'] for i in items]}"
        assert "魅惑人类" in item_text(it), f"正文并入：{item_text(it)[:50]!r}"
        assert "狐妖之" not in by_name and "魅" not in by_name, \
            f"不得拆出伪条目：{[i['name'] for i in items]}"

    def test_body_line_digit_lead_ability_tail_not_wrapped(self):
        """正文行「3级起，…该能力取代陷阱感知。」（数字开头 + 以能力词
        结尾）不得被 `_wrap_bare_colon_titles_race` 的裸数字行规则转星壳
        （KN133 狐妖之魅 P1 收尾：正文被误包成 `**3级起…**：` 残留）"""
        body = "3级起，狐妖欺诈者能够以类法术能力每日使用1次‘魅惑人类’。该能力取代陷阱感知。"
        out = R_(body)
        assert not out.startswith("**"), f"正文行不得被包星: {out[:50]!r}"

    def test_ability_adj_bare_still_wrapped(self):
        """真属性调整裸行（带正负号）仍转星（BotS 塞卡利亚形态回归保护）"""
        out = R_("+2力量，+2敏捷，-2智力：鲛人肉体强悍。")
        assert out.startswith("**+2力量"), f"属性调整行应转星: {out[:40]!r}"

    def test_split_name_merged_quad_and_higher(self):
        """「精通地精自燃术」（前段长）与「高等地精自燃术」（后段长）同样合并
        成单条目"""
        items = run(CLUSTER_U_SPLIT_CN_NAME)
        by_name = {i["name"]: i for i in items}
        it = by_name.get("精通地精自燃术")
        assert it is not None, f"精通地精自燃术应合并：{[i['name'] for i in items]}"
        assert "10级时" in item_text(it)
        it = by_name.get("高等地精自燃术")
        assert it is not None, f"高等地精自燃术应合并：{[i['name'] for i in items]}"
        assert "14级时" in item_text(it)
        assert "高等地精" not in by_name and "自燃术" not in by_name, \
            f"拆裂碎片不得独立成条目：{[i['name'] for i in items]}"

    def test_split_name_type_tag_no_residue(self):
        """`**地精铳****士（****Goblin Gunslinger****）〔战斗〕**：` 合并成
        「地精铳士」单条目，类型标签〔战斗〕不残留 title/text（race 无类型
        字段，仅防污染）"""
        items = run(CLUSTER_U_SPLIT_CN_NAME)
        by_name = {i["name"]: i for i in items}
        it = by_name.get("地精铳士")
        assert it is not None, f"地精铳士应合并：{[i['name'] for i in items]}"
        assert "〔战斗〕" not in it["name"], f"title 不得残留类型标签：{it['name']!r}"
        t = item_text(it)
        assert "火枪" in t, f"正文并入：{t[:60]!r}"
        assert "〔战斗〕" not in t, f"text 不得残留类型标签：{t[:60]!r}"
        assert "地精铳" not in by_name, f"「地精铳」是碎片非条目"

    def test_split_name_arcane_ink(self):
        """`**灌魔恶臭****墨水（****Stink Ink, Arcane****）**` 同样合并成
        「灌魔恶臭墨水」单条目"""
        items = run(CLUSTER_U_SPLIT_CN_NAME)
        by_name = {i["name"]: i for i in items}
        it = by_name.get("灌魔恶臭墨水")
        assert it is not None, f"灌魔恶臭墨水应合并：{[i['name'] for i in items]}"
        assert "恶臭墨水" in item_text(it)

CLUSTER_V_M10_TRIO = (
    # 1. 动物伙伴 stat block 字段吞并（page_1412 鼠族：「鼠族装备」章节 →
    # race_item 态）
    "**鼠族（Ratfolk）**\n"
    "**鼠族装备（Ratfolk Equipment）**\n"
    "**骑乘用巨鼠动物伙伴****起始属性: \n"
    "体型** 中型;\n"
    "**速度**\n"
    "40尺；\n"
    "**攻击：**啮咬（1d6）；\n"
    # 2. 替代特性标题壳（page_815 蒿兰人：`**替换自然魔法**` 无正文，内容
    # 在「甜气」条目 text——弹壳检索等价命中；`**种族特性替换**` 章节行
    # 触发 alt_trait 态）
    "**种族特性替换**\n"
    "**替换自然魔法**\n"
    "\n"
    "**甜气** \n"
    "(吐槽)：有些蒿兰人带有一种令人迷醉的芳香。\n"
    "这个种族特性取代了自然魔法。\n"
    # 3. 章节标题壳（page_940 卡萨达人：`**种族背景(Race Traits)**(来源
    # \nPathfinder…)**四手灵巧…`——来源括号跨行 + 背景条目独立）
    "**种族背景(Race Traits)**(来源 \n"
    "Pathfinder Player Companion: People of the Stars)**四手灵巧(Adroit)**: \n"
    "如果你有一只手是自由的，你可以在移动动作中拔出一把武器。\n"
)


class TestClusterV_M10Trio:
    """簇 V：M10 收尾空 text 三件套——动物伙伴字段吞并（词表）+ 替代特性
    标题壳/章节标题壳弹壳（dedup 判据）"""

    def test_animal_companion_field_merged(self):
        """`**骑乘用巨鼠动物伙伴****起始属性: \\n体型** 中型;…` 字段行
        「起始属性」并入主条目（不切伪条目），text 含 stat block 数据"""
        items = run(CLUSTER_V_M10_TRIO)
        by_name = {i["name"]: i for i in items}
        it = by_name.get("骑乘用巨鼠动物伙伴")
        assert it is not None, f"动物伙伴应独立条目：{[i['name'] for i in items]}"
        t = item_text(it)
        assert "中型" in t, f"体型数据并入：{t[:60]!r}"
        assert "40尺" in t, f"速度数据并入：{t[:60]!r}"
        assert it.get("text", "").strip(), f"text 非空"
        assert "起始属性" not in by_name, \
            f"「起始属性」是字段标签非独立条目：{[i['name'] for i in items]}"

    def test_replacement_trait_shell_popped(self):
        """`**替换自然魔法**` 替代特性空壳（正文在「甜气」条目）→ 弹壳不
        产空 text；甜气条目保留且 text 含取代描述"""
        items = run(CLUSTER_V_M10_TRIO)
        by_name = {i["name"]: i for i in items}
        assert "替换自然魔法" not in by_name, \
            f"替代特性空壳应弹：{[i['name'] for i in items]}"
        it = by_name.get("甜气")
        assert it is not None, f"甜气应保留：{[i['name'] for i in items]}"
        assert "取代了自然魔法" in item_text(it), \
            f"取代描述保留：{item_text(it)[:60]!r}"

    def test_section_shell_popped(self):
        """`**种族背景(Race Traits)**(来源：` 章节标题壳 → 弹壳不产空 text"""
        items = run(CLUSTER_V_M10_TRIO)
        by_name = {i["name"]: i for i in items}
        assert "种族背景" not in by_name, \
            f"章节标题壳应弹：{[i['name'] for i in items]}"

    def test_image_ref_stripped(self):
        """`![[图片]](URL)` 完整与截断形态剥除（须在 _strip_http_links 前），
        不污染条目 text"""
        items = run(
            "**藤蔓莱西（Vine Lass）**\n"
            "![[图片]](https://i.bmp.ovh/imgs/2021/03/d30c67200da23287.png)\n"
            "正文。\n"
        )
        by_name = {i["name"]: i for i in items}
        it = by_name.get("藤蔓莱西")
        assert it is not None, f"藤蔓莱西应独立条目：{[i['name'] for i in items]}"
        t = item_text(it)
        assert "图片" not in t, f"图片引用残留：{t!r}"
        assert "正文" in t, f"正文保留：{t[:60]!r}"


CLUSTER_X_M12_FIELD_WORDS = (
    # 1. race_item 态「条件」（page_440 土元素裔奇物章节字段链：
    # `**条件**：` 后 `**价格**：` 同行）
    "**土元素裔奇物（Oread Wondrous Items）**\n"
    "**护卫（Guarding）**：护卫盾牌允许佩戴者将部分或全部盾牌的增强加值"
    "转移到一名临近生物的AC上。\n"
    "**条件**：“制造魔法武器和防具”；‘护卫他人’；**价格**：+1加值。\n"
    # 2. race_item 态「弱点」（page_163 吸血裔 stat block：弑亲者能力
    # 条目流后 `**弱点**：`）
    "**察觉亡灵（Undead Sense, Sp）**：2级起，弑亲者获得如同使用类法术"
    "能力一般使用‘侦测亡灵’的能力。\n"
    "**弱点**：吸血鬼无法忍受强烈的大蒜气味，所以不会接近有那种玩意儿"
    "的地方。\n"
    # 3. race_trait 态「弱点（Weakness）」（page_204 狗头人种族特性章节：
    # `**狗头人种族特性（Kobold Racial Traits）**` 后特性条目流）
    "**狗头人种族特性（Kobold Racial Traits）**\n"
    "**狡诈（Crafty）**：狗头人在工艺（陷阱）检定上获得+2种族加值。\n"
    "**弱点（Weakness）**：强光敏感。\n"
    # 4. race_feat 态「推荐科研发现」（page_166 地精专长章节形态近似）
    "**地精专长（Goblin Feats）**\n"
    "**推荐科研发现**：瓶装泥怪（Bottled Ooze），炸裂喷吐。\n"
)


class TestClusterX_M12FieldWords:
    """簇 X：M12 词表补全——「条件」「弱点」「推荐科研发现」字段行并入
    当前条目，不切伪条目"""

    def test_condition_field_merged(self):
        """`**条件**：` 在 race_item 态并入（page_440 奇物字段链）"""
        items = run(CLUSTER_X_M12_FIELD_WORDS)
        by_name = {i["name"]: i for i in items}
        assert "条件" not in by_name, f"条件是字段非独立条目：{[i['name'] for i in items]}"
        it = by_name.get("护卫")
        assert it is not None, f"护卫应保留：{[i['name'] for i in items]}"
        t = item_text(it)
        assert "制造魔法武器和防具" in t, f"条件值并入护卫：{t[:80]!r}"

    def test_weakness_item_kept(self):
        """`**弱点**：` 裸标题冒号在 race_item 态保持独立条目（page_163
        唯一裸「弱点」是速查残留段正文——S4 簇锁定行为；词表补「弱点」
        曾误吞该行，2026-08-04 M12 收窄：带 EN 括号形态才并入）"""
        items = run(CLUSTER_X_M12_FIELD_WORDS)
        by_name = {i["name"]: i for i in items}
        assert "弱点" in by_name, \
            f"裸弱点保持独立条目：{[i['name'] for i in items]}"
        assert any("大蒜" in item_text(i) for i in items), \
            f"弱点正文保留：{[(i['name'], item_text(i)[:40]) for i in items]}"

    def test_weakness_trait_merged(self):
        """`**弱点（Weakness）**：` 带 EN 括号在 race_trait 态并入
        （page_204 狗头人 stat block）"""
        items = run(CLUSTER_X_M12_FIELD_WORDS)
        by_name = {i["name"]: i for i in items}
        # ⚠️ 不断言 "弱点" not in by_name：场景 2 裸「弱点」是合法独立
        # 条目（test_weakness_item_kept 锁定），共享输入互斥
        it = by_name.get("狡诈")
        assert it is not None, f"狡诈应保留：{[i['name'] for i in items]}"
        assert "强光敏感" in item_text(it), f"弱点值并入狡诈：{item_text(it)[:80]!r}"

    def test_research_merged(self):
        """`**推荐科研发现**：` 在 race_feat 态并入（page_166 地精
        炼金术士）"""
        items = run(CLUSTER_X_M12_FIELD_WORDS)
        by_name = {i["name"]: i for i in items}
        assert "推荐科研发现" not in by_name, \
            f"推荐科研发现是字段：{[i['name'] for i in items]}"
        assert any("瓶装泥怪" in item_text(i) for i in items), \
            f"科研发现值并入：{[(i['name'], item_text(i)[:40]) for i in items]}"


CLUSTER_W_M11_CROSS_DIGIT = (
    # 1. 能力值断行（page_1599 勒珊塔灵族「有限心灵感应」原始形态：
    # `Telepathy，3 \nRP）`——数字结尾行公共 _RE_CROSS_EN 失配（组1 只收
    # 字母/逗号），标题不成形整条并入相邻条目）
    "**有限心灵感应（Limited \n"
    "Telepathy，3 \n"
    "RP）**：一名勒珊塔灵族可与其30尺内任何由她共享了一种语言的生物进行"
    "精神上的交流。除此之外，这种能力与心灵感应（telepathy）能力相同。\n"
    # 2. 小节标题断行（`Characters，11 \nRP）`，ISR 书第 11 页引文形态）
    "**勒珊塔灵族角色（Lashunta \n"
    "Characters，11 \n"
    "RP）\n"
    "**拉申塔人是由他们的职业等级来定级的——他们没有种族生命骰。\n"
)


class TestClusterW_M11CrossDigit:
    """簇 W：M11 数字结尾断行合并——`X，N \\nRP` 能力值/引文行拆断行"""

    def test_limited_telepathy_title_restored(self):
        """`Telepathy，3 \\nRP）` 合并 → 完整标题独立切出，text 无断行残留"""
        items = run(CLUSTER_W_M11_CROSS_DIGIT)
        by_name = {i["name"]: i for i in items}
        it = by_name.get("有限心灵感应")
        assert it is not None, f"有限心灵感应应独立条目：{[i['name'] for i in items]}"
        assert it.get("name_en", "") == "Limited Telepathy 3 RP", \
            f"断行合并进标题：{it.get('name_en')!r}"
        t = item_text(it)
        assert "30尺" in t, f"正文完整：{t[:80]!r}"
        assert not any(x in t for x in ("\nRP", "，3\n")), f"断行残留：{t!r}"

    def test_characters_section_title_restored(self):
        """`Characters，11 \\nRP）` 合并 → 「勒珊塔灵族角色」小节标题切出，
        正文并入不粘连前条目"""
        items = run(CLUSTER_W_M11_CROSS_DIGIT)
        by_name = {i["name"]: i for i in items}
        it = by_name.get("勒珊塔灵族角色")
        assert it is not None, f"小节标题应独立：{[i['name'] for i in items]}"
        assert "职业等级" in item_text(it), \
            f"正文并入：{item_text(it)[:80]!r}"


# ============ 簇 Y：M13 取代条款行（PA 暮行者 + 格拉里昂狗头人 2026-08-04） ============

CLUSTER_Y_M13_REPLACE_CLAUSE = (
    # 1. PA 暮行者（位面冒险PA_暮行者.md L148-160）：替换特性条目 + 独立行
    #    取代条款（跨行 EN 括号形态——`此特性取代腐化抗性（ward against
    #    \ncorruption）.` 被公共 `_wrap_bare_paren_lines` 误转星 →
    #    `[[fc:elided]]**此特性取代腐化抗性（ward against corruption）**`
    #    切伪条目，句点拆出成 text='.'——根因：A 分支守卫 5 只拦「中文句号
    #    + >30 字长散文」，英文句点短行穿透；R10 守卫补取代条款形态）
    "**种族特性替换（Alternate Racial Traits）\n"
    "**劫运代理者（Olethros’s \n"
    "Agent）**：有些暮行者身上比起同类体现出更多来自其守护者的力量，一位被劫运观魂使祝福的暮行者是万中无一的命运代行者。每天一次，以一个自由动作，拥有此种族特性的暮行者可以在一次攻击命中后无视相当于10+魅力调整值的DR。\n"
    "此特性取代腐化抗性（ward against \n"
    "corruption）.\n"
    "**阎摩执行官（Yamaraj’s \n"
    "Bailiff）**：与强大的阎摩判魂使们紧密联系的暮行者可以洞见那些终末判官的哲思，并将其中皮毛化为己用。拥有此种族特性的暮行者可以在进行交涉和唬骗时使用感知调整替代魅力调整。\n"
    "此特性取代腐化抗性（ward against \n"
    "corruption）.\n"
    # 2. 格拉里昂狗头人（格拉里昂的狗头人_种族替换特性.md L13-17）：条目 +
    #    独立行取代条款（EN 同行，中文句号结尾）
    "**龙之喉（Dragonmaw）:**你的龙族血脉给你带来笑容——不仅因为它让你快乐，还因为你强壮的下颚和牙齿证明你与彩色龙的血亲关系。你获得一个造成1d4点伤害的啮咬攻击。每天一次，你可以用你的啮咬攻击造成1d6点额外能量伤害。\n"
    "该特性取代防御（Armor）。\n"
    # 3. 怪物种族（怪物种族/page_940.md L60-61）：`此能力取代偏好地形
    #    （favored terrain）`——跨行 EN 合并后无句点形态（组3 为空），
    #    R10 守卫同样拦截（`此能力取代` 前缀）
    "**碎甲箭（Exploit the \n"
    "Gap）**：在18级时，游牧猎手能够利用对手天然的弱点。\n"
    "此能力取代偏好地形（favored \n"
    "terrain）\n"
    # 4. 纯中文形态回归（无 EN 括号——既有行为并入，防回归）
    "**弃子（Abandoned）**：有些暮行者孩子被所在的社区回避与忌惮，只得以盗窃和拾荒为生。拥有此种族特性的暮行者在隐匿和生存检定中获得+2种族加值。\n"
    "此特性取代技能奖励。\n"
)


class TestClusterY_M13ReplaceClause:
    """簇 Y：M13——独立行取代条款（`X特性取代Y（EN）。`）并入前条目，
    不切伪条目（PA 暮行者 2 处 + 格拉里昂狗头人 1 处 + 纯中文回归）"""

    def test_replace_clause_not_item(self):
        """取代条款行不得被切独立条目（含 elided 转星形态）"""
        items = run(CLUSTER_Y_M13_REPLACE_CLAUSE)
        names = [i["name"] for i in items]
        for bad in (
            "此特性取代腐化抗性",
            "该特性取代防御",
            "此能力取代偏好地形",
        ):
            assert bad not in names, f"取代条款切伪条目：{names}"
        # 无孤立标点条目（转星后句点拆出成 text='.'/'。'）
        for it in items:
            t = item_text(it)
            assert t not in (".", "。"), f"孤立标点条目：{it['name']!r} → {t!r}"

    def test_replace_clause_merged(self):
        """取代条款并入前一条目 text（作为 replaces 说明）"""
        items = run(CLUSTER_Y_M13_REPLACE_CLAUSE)
        by_name = {i["name"]: i for i in items}
        assert by_name.get("劫运代理者") is not None
        assert "取代腐化抗性" in item_text(by_name["劫运代理者"]), \
            f"取代条款并入劫运代理者：{item_text(by_name['劫运代理者'])[:60]!r}"
        assert by_name.get("阎摩执行官") is not None
        assert "取代腐化抗性" in item_text(by_name["阎摩执行官"]), \
            f"取代条款并入阎摩执行官：{item_text(by_name['阎摩执行官'])[:60]!r}"
        assert by_name.get("龙之喉") is not None
        assert "取代防御" in item_text(by_name["龙之喉"]), \
            f"取代条款并入龙之喉：{item_text(by_name['龙之喉'])[:60]!r}"
        assert by_name.get("碎甲箭") is not None
        assert "取代偏好地形" in item_text(by_name["碎甲箭"]), \
            f"取代条款并入碎甲箭：{item_text(by_name['碎甲箭'])[:60]!r}"
        assert by_name.get("弃子") is not None
        assert "取代技能奖励" in item_text(by_name["弃子"]), \
            f"纯中文取代条款并入弃子：{item_text(by_name['弃子'])[:60]!r}"


# ============ 簇 Z：M14 同行多条目拆行（BotB 变换体型粘 0005，2026-08-04） ============

CLUSTER_Z_M14_INLINE_TWO_TITLES = (
    # 野兽血脉BotB_种族特性.md L71-73：`**种族特性替换****特技专家（Acrobatic）**
    # ：正文…（nimble）**变换体型（Change Size，Su）**：正文`——HTML 段落合并
    # 两条目同行粘连。`_split_inline_star_titles` 行首星+星后冒号守卫跳过整行
    # （FCB/字段行设计），行中第二个标题（变换体型）被连带跳过 → 并入前条目
    # text。修复：行首星+星后冒号分支递归扫描 after（无行中标题时行为不变）
    "**种族特性替换****特技专家（Acrobatic）**：灵猴族通常异常灵巧，可以如同玩耍一般在移动缓慢的人类周围起舞。他们在特技和逃脱检定中获得+2种族加值。此种族特性取代了灵巧（nimble）**变换体型（Change Size，Su）**：每500只灵猴族中间就有一只拥有有限的变形能力。她可以随意调整她的体型。她获得了变身（change \n"
    "shape subtype）。她可以使用变身来将体型变为小型而不是改变外表。\n"
)


class TestClusterZ_M14InlineTwoTitles:
    """簇 Z：M14——同行多条目（行首标题+行中标题）拆行"""

    def test_inline_two_titles_split(self):
        """变换体型拆为独立条目（不并入特技专家）"""
        items = run(CLUSTER_Z_M14_INLINE_TWO_TITLES)
        names = [i["name"] for i in items]
        assert "变换体型" in names, f"变换体型未拆出：{names}"
        assert "特技专家" in names, f"特技专家丢失：{names}"
        by_name = {i["name"]: i for i in items}
        # 特技专家 text 不含变换体型正文
        assert "每500只" not in item_text(by_name["特技专家"]), \
            f"变换体型正文粘进特技专家：{item_text(by_name['特技专家'])[:80]!r}"
        # 变换体型 text 含自身正文
        assert "每500只" in item_text(by_name["变换体型"]), \
            f"变换体型正文缺失：{item_text(by_name['变换体型'])[:80]!r}"


class TestClusterZ2_M14FieldChainGuard:
    """簇 Z2：M14 回归守卫——行中星壳仅拆「真标题」（after 为纯正文），
    字段标签（星后换行/连字符/字段链）不拆（page_26 毒刺、page_312 树蛙毒）"""

    FIELD_CHAIN_STING = (
        # 娜迦裔毒刺（page_26 真实形态）：`**类型**：毒素，伤口；**强韧豁免**
        # **DC**…` 星外冒号字段链——`**类型**`/`**强韧豁免（DC）**` 是字段
        # 标签不是标题，不得拆行丢壳
        "**毒刺（****Poisonous \n"
        "Sting, Ex****）**：德鲁伊的蜇刺变得具有毒性。德鲁伊的娜迦形态必须拥有【尾刺】才能选择该能力。**类型**：毒素，伤口；**强韧豁免****DC**“10+1/2德鲁伊等级+体质修正”；**发作频率**：每轮1次；**效果**：睡眠2d4分钟；**治愈**：1次豁免。\n"
    )

    DROWSY_TOXIN = (
        # 树蛙人昏睡毒素（page_312 形态）：`**初始效果**－…`/`**后续效果**－…`
        # 是专长效果内的行内子字段，不是独立条目
        "**昏睡毒素（****Slumber \n"
        "Toxin, Ex****）**：你能够改变天生毒素的性质，并用其让你的敌人呼呼大睡。**先决条件**：蝮血裔。**专长效果**：以一个迅捷动作，你能够改变自身毒素的效果，使其能够让目标失去意识。以下为你的毒素的初始以及后续效果的改变：**初始效果**－恍惚1d4轮；**后续效果**－失去意识1分钟。你必须在将毒素涂抹在武器上之前决定它的效果。\n"
    )

    def test_field_chain_not_split(self):
        """字段链（星后冒号 + after 含 `**`）不拆：毒刺保留完整字段行"""
        items = run(self.FIELD_CHAIN_STING)
        names = [i["name"] for i in items]
        assert names == ["毒刺"], f"字段标签被拆成条目：{names}"
        t = item_text(items[0])
        assert "**强韧豁免（DC）**" in t, \
            f"强韧豁免星壳丢失：{t[:160]!r}"

    def test_hyphen_field_not_split(self):
        """星后连字符字段（初始效果/后续效果）不拆为独立条目"""
        items = run(self.DROWSY_TOXIN)
        names = [i["name"] for i in items]
        assert "初始效果" not in names and "后续效果" not in names, \
            f"行内子字段被拆成条目：{names}"
        t = item_text(next(i for i in items if i["name"] == "昏睡毒素"))
        assert "初始效果" in t and "后续效果" in t, \
            f"子字段说明丢失：{t[:160]!r}"


class TestClusterZ3_M14FieldLabelSkipTitle:
    """簇 Z3：M14 字段标签跳过不卡标题——`…**先决条件**：…**龙人秩序（Draconian
    Law）**`（page_716 翼龙人专长 L2）行内字段标签后的行尾标题仍拆出"""

    CLUSTER = (
        # page_716 L29-32 真实形态：`**巢穴守卫者 Brood \nDefender**当某人…`
        # 同行多条目——行内 `**先决条件**`（字段标签）之后的行尾标题
        # （龙人秩序/遗物精通/诚挚恭维/尾部技巧/翼龙人施法专精）必须拆出，
        # 不能被字段标签的「整行跳过」卡住
        "翼龙人专长翼龙人由于他们独特的生理机能和龙族文化的影响，可以使用下列的专长。**巢穴守卫者 Brood \n"
        "Defender**当某人在你的保护之下被袭击时，你立刻反抗攻击者。**先决条件**：保镖APG，战斗反射，翼龙人**专长效果**：如果一个盟友在这轮通过你成功地使用援助他人提高AC之后，躲过了敌人的攻击，你可以尝试以直觉动作进行一次威吓检定来挫败这个敌人的士气。**龙人秩序（Draconian Law）**你的荣誉准则延伸至你生活中的方方面面，包括你对敌人的审判。**先决条件**：守序阵营，翼龙人**专长效果**：当与你目击到破坏秩序（law）的敌人战斗时，你在对抗该目标的第一次攻击骰和全部伤害骰上获得+1环境加值，直到他忏悔自己的罪行。**遗物精通 Relic \n"
        "Familiarity**你的部落有一个惊人的古代神器收藏品，你在旅途中常常看到一些东西让你回想起你部落宝库中的宝物。**先决条件**：翼龙人**专长效果**：你在确定一件物品价值的估价检定和一件物品魔法特性的法术辨识检定上获得+2加值。\n"
    )

    def test_field_label_not_blocking_tail_title(self):
        """字段标签后的行尾标题仍拆出（翼龙人专长）"""
        items = run(self.CLUSTER)
        names = [i["name"] for i in items]
        assert "巢穴守卫者" in names, f"巢穴守卫者丢失：{names}"
        assert "龙人秩序" in names, f"龙人秩序未拆出：{names}"
        assert "遗物精通" in names, f"遗物精通未拆出：{names}"
        # 龙人秩序 text 不含巢穴守卫者正文
        by_name = {i["name"]: i for i in items}
        assert "威吓检定" not in item_text(by_name["龙人秩序"]), \
            f"巢穴守卫者正文粘进龙人秩序：{item_text(by_name['龙人秩序'])[:80]!r}"


class TestClusterZ4_M15StatBlockSectionTitles:
    """簇 Z4：M15 stat block 章节标题伪条目——`生态背景（Ecology）` /
    `特殊能力（Special Abilities）` / `栖息地与社会（Habitat & Society）`
    （冒险之路AP_怪物 裸行 + `---` 分隔形态）不得切独立条目，并入前条目"""

    CLUSTER = (
        # 73_The_Worldwound_Incursion L70-98 铜蛇 stat block 真实形态：
        # `---` 分隔行 + 裸行章节标题（无 `**`）
        "**铜蛇（Nehushtan）**\n"
        "**XP 3200**\n"
        "铜蛇 守序善良 超大型龙类\n"
        "先攻 +3；感官：黑暗视觉60尺；察觉+9\n"
        "灵光：毒之瘴气（DC 19）\n"
        "防御能力：AC 23，接触 7，措手不及 20（+13 天生，-2 体型）\n"
        "攻击能力：啃咬+19（2d8+7）\n"
        "技能：飞行+10，察觉+9，察言观色+10，生存+5\n"
        "语言：通用语（Common）；心灵感应30尺。\n"
        "\n"
        "---\n"
        "生态背景（Ecology）\n"
        "\n"
        "---\n"
        "环境：任何城镇。\n"
        "组织：单独。\n"
        "宝藏：无。\n"
        "\n"
        "---\n"
        "特殊能力（Special \n"
        "Abilities）\n"
        "\n"
        "毒之瘴气（Aura of Venom，Su）：…\n"
        "啃咬（Bite，Ex）：…\n"
        "\n"
        "---\n"
        "栖息地与社会（Habitat \n"
        "& Society）\n"
        "铜蛇的性情各不相同。有些聚集在大型扩编族群中，而另一些与其他铜蛇交流的时间只够繁衍和养育后代。\n"
    )

    def test_stat_block_sections_not_items(self):
        """stat block 章节标题不切独立条目，并入铜蛇条目"""
        items = run(self.CLUSTER)
        names = [i["name"] for i in items]
        assert "铜蛇" in names, f"铜蛇丢失：{names}"
        for bad in ("生态背景", "特殊能力", "栖息地与社会"):
            assert bad not in names, f"{bad} 切了伪条目：{names}"
        # 铜蛇条目 text 含章节标题行（并入，可追溯 stat block 结构）
        by_name = {i["name"]: i for i in items}
        text = item_text(by_name["铜蛇"])
        assert "生态背景（Ecology）" in text, f"生态背景未并入铜蛇 text：{text[:120]!r}"
        # 能力列表条目（带 Su/Ex 标记）独立切出——stat block 能力条目正确行为
        assert "毒之瘴气" in names, f"毒之瘴气（能力条目）丢失：{names}"
        assert "啃咬" in names, f"啃咬（能力条目）丢失：{names}"
        # 栖息地与社会（stat block 末节）并入前条目（啃咬），不切伪条目
        bite = item_text(by_name["啃咬"])
        assert "栖息地与社会" in bite, f"栖息地与社会未并入前条目：{bite[:150]!r}"
        # 无孤立 `---` 分隔线 chunk
        for it in items:
            assert item_text(it).strip(" -—") != "", f"孤立分隔线 chunk：{it['name']!r}"


class TestClusterZ5_M16FrostGiantChapter:
    """簇 Z5：M16 霜巨人整章粘连——聚合文件段落同行连排（行中裸
    「中文 EN（类型） 正文」形态），条目须拆出（专长/法术/物品）"""

    CLUSTER = (
        # 霜巨人.md L5/L7/L9/L20/L24 真实形态：行首章节引言 + 行中
        # 裸「中文 空格 EN」条目（无 `**`、无换行）
        "新规则霜巨人的能力发展于他们对极寒环境的长期适应，而他们的法术和战术则多用于配合自己巨大的体型与突袭策略。\n霜巨人专长\n以下专长只有霜巨人战士才能获得。有仇报仇 Ancestral Enmity（战斗）  你熟知那些矬子对巨人的憎恨，并研究了针对这些家伙的战术\n"
        "\n"
        "先决条件：巨人生物亚种专长效果：你在对矮人或侏儒发动的近战攻击检定上获得+2加值。特殊情况：你可以多次选择本专长，它们的效果叠加。可怖冲撞 Awesome Charge（战斗）  你可以借冲锋之势打飞你的敌人\n"
        "\n"
        "先决条件：力量25，可怖殴击，精通冲撞，猛力攻击专长效果：当你在一次冲锋攻击中命中目标时，你可以以一个自由动作对其发动可怖殴击战技攻击。霜生种 Born of Frost  你身体萦绕的寒气足以冻伤其他生物\n"
        "\n"
        "先决条件：霜生种，霜巨人专长效果：你的天生武器攻击和徒手击打可以造成1d6点额外的寒冷伤害，以天生武器或是徒手击打命中你的生物会承受1点寒冷伤害。冰寒石块 Chilled Rock  你可以将自己天生的低温传递给你投掷的岩石\n"
        "\n"
        "先决条件：霜生种，霜巨人专长效果：你通过投石能力投掷的物体将在命中目标时造成1d6点额外的寒冷伤害。顺势扫荡 Cleaving Sweep（战斗）  你旋舞大斧，将周围的敌人纷纷扫倒在地\n"
        "\n"
        "先决条件：力量15，顺势劈，精通摔绊，武器专攻（巨斧），基本攻击加值+11专长效果：当你使用双手武器发动一次整轮攻击时，你可以放弃正常的攻击，而是对你触及范围内的每一个生物都发动一次摔绊战技攻击尝试，使用你的最高基础攻击加值。你必须分别对每一个目标发动一次战技攻击检定冷酷逼视 Icy Stare  你的双眼闪烁着严寒，只需一瞪便可让敌人在冰冻中颤抖\n"
        "\n"
        "先决条件：霜生种，霜巨人专长效果：以一个标准动作，你可以用酷寒的视线扫向一个10尺内的生物或物体，这些生物或物体必须通过一个DC=（10+你的HD的一半+你的魅力调整值）的强韧检定（无主物体不能进行豁免检定），否则承受1d6点寒冷伤害。在豁免检定中失败的生物还会额外承受1点力量伤害。踏冰者 Sure on Ice  你在湿滑的冰面或雪地上如履平地\n"
        "\n"
        "先决条件：霜巨人专长效果：你在结冰或积雪的地面上移动时不会承受任何减值，也不必因为在冰面上奔跑或冲锋而进行特技动作检定，除此之外，你在攀爬冰面的攀爬技能检定获得+4加值。\n霜巨人法术\n霜巨人研究出了这些法术帮助他们在严寒的环境中狩猎和劫掠。冰滑术 Ice Slick学派：塑能系[冷]；等级：德鲁伊2，魔战士2，游侠2，术士/法师2，女巫2施法时间：1个标准动作成分：语言，姿势距离：近距（25尺+5尺/两个等级）法术范围：5尺爆发范围持续时间：立即（见下文）豁免检定：反射通过则部分无效（见下文）；法术抗力：见下文\n"
        "\n"
        "魔岩术 Magic Boulder学派：变化系；等级：牧师2，德鲁伊2法术目标：最多三块接触到的岩石\n"
        "\n"
        "本法术的效果类似于法术魔石术，但你可以将最多三块岩块（体积至少比你小一级）转化为魔法武器或是攻城武器的弹药。这些变化后的岩石会造成体型大一级的伤害，并在攻击和伤害检定上拥有+1增强加值。\n霜巨人魔法物品\n很多传说都指出，霜巨人是世界上第一件魔法物品的制造者，而这些上古就流传下来的手艺至今仍然在霜巨人铁匠和符文师的实验室中保存着它们的魔力。很多冒着横死在峭壁和冰川上的风险袭击霜巨人要塞的英雄都渴望能从他们的财宝库捞上一把，而确实有些辛运儿儿能够（基本上）全须全尾地带着霜巨人的宝物返回家乡，成为歌手传颂的奇闻异事。破雾目镜 Fog-Cutting Lenses装备位置：面部（注：大概是眼部） 灵光：中微弱变化系 施法者等级：5价格：8000GP 重量：1磅\n"
    )

    def test_frost_giant_entries_split(self):
        """霜巨人专长/法术/物品条目拆出，不整章粘连"""
        items = run(self.CLUSTER)
        names = [i["name"] for i in items]
        # 冷酷逼视不在此列：前字符是汉字（`…战技攻击检定冷酷逼视 Icy
        # Stare`——句尾词「检定」后无标点直连条目名，HTML 合并丢句号），
        # 与正文引用形态不可区分，登记不修（并入前条目无损，M16 备忘）
        for feat in ("有仇报仇", "可怖冲撞", "霜生种", "冰寒石块", "顺势扫荡",
                     "踏冰者", "冰滑术", "魔岩术", "破雾目镜"):
            assert feat in names, f"{feat} 未拆出：{names}"
        # 字段行并入前条目（先决条件/专长效果并入有仇报仇）
        by_name = {i["name"]: i for i in items}
        text = item_text(by_name["有仇报仇"])
        assert "先决条件" in text, f"字段行未并入有仇报仇：{text[:100]!r}"
        assert "巨人生物亚种" in text, f"先决条件值丢失：{text[:100]!r}"
        # M16 章节拆行：霜巨人法术/霜巨人魔法物品 独立成行 → 条目归正确类型
        # （源数据拆行，章节标题识别后法术/物品不再落入 race_trait）
        ctype = {i["name"]: i["kind"] for i in items}
        assert ctype["冰滑术"] == "race_spell", f"冰滑术类型错误：{ctype.get('冰滑术')}"
        assert ctype["魔岩术"] == "race_spell", f"魔岩术类型错误：{ctype.get('魔岩术')}"
        assert ctype["破雾目镜"] == "race_item", f"破雾目镜类型错误：{ctype.get('破雾目镜')}"
        assert ctype["有仇报仇"] == "race_feat", f"有仇报仇类型错误：{ctype.get('有仇报仇')}"
        # 霜生种/冰寒石块/踏冰者同为「霜巨人专长」章节条目（怪物法典专长），
        # 章节识别后归 race_feat 是正确行为（拆行前章节未识别落入 race_trait）
        assert ctype["霜生种"] == "race_feat", f"霜生种类型错误：{ctype.get('霜生种')}"
        assert ctype["踏冰者"] == "race_feat", f"踏冰者类型错误：{ctype.get('踏冰者')}"

    def test_bare_cn_en_inline_not_body_quote(self):
        """正文句中的「中文 空格 EN」引用不误拆（前字符汉字守卫）"""
        items = run("……霜巨人战士往往会使用有仇报仇 Ancestral Enmity 专长来对付矮人。")
        names = [i["name"] for i in items]
        assert "有仇报仇" not in names, f"正文引用误拆：{names}"

    def test_bare_cn_en_inline_uppercase_abbr_not_split(self):
        """纯大写缩写（DC/AC/HD）不是条目名——`此豁免 DC 基于魅力` 不误拆
        （M16 去 `^` 行首锚定后行中形态扩大，DC 缩写守卫防伪条目）"""
        items = run("……魔宝蝙蝠和透肌魔人对该效果免疫。此豁免 DC 基于魅力。")
        names = [i["name"] for i in items]
        assert "此豁免" not in names, f"DC 缩写误拆：{names}"


# ---- 簇 M17：内海怪物志星壳错位修复（2026-08-04） ----
# 源数据 `X（类型）**（EN\n(Ex)）：正文` / `X****` / `X**：**` 错位星壳
# （CHM→MD 转换器嵌套 STRONG 闭合错位产物）→ 修复为标准形态
# `**X（EN, 类型）**：正文`（类型并入 EN 括号逗号连接，_split_paren_content
# 字母段合并进 name_en）。样例为修复后源数据形态，锁定拆分行为。
CLUSTER_M17_ISMC_STARSHELL = (
    "**透肌魔人（Urdefhan）**\n"
    "透肌魔人生活在内海大陆地下的幽暗地域之中，他们擅长用双叉剑战斗。\n"
    "**透肌魔人专长**\n"
    "**必然毁灭（Assured Destruction）**：你对死亡的热情——包括你自己——给所有你周围的人造成更严重的伤害。\n"
    "**汲取之剑（Siphoning Blade, Combat）**：你用双叉剑汲取敌人的鲜血，用于增强自己。\n"
    "**尸鬼蝙蝠伙伴（Skaveling Companion）**：这只来自于亵渎邪魔仪式的骇人不死坐骑与你形成紧密羁绊。\n"
    " 体型：大型\n"
    "  ；速度：20尺，飞行40尺（良好） ；AC：+6天生防御\n"
    "**德洛人（Derro）**\n"
    "**德洛人炼金术士科研发现**\n"
    "**碧幻菌炸弹（Cytillesh Bomb）**：当炼金术士制作炼金炸弹时，他可以给其注入碧幻菌提取物。\n"
    "**疯狂研究（Method to the Madness, Ex）**：炼金术士学会了将自己的疯狂融入自己的炼金术士职业能力中。\n"
    "**休眠傀儡（Sleeper Agent, Su）**：炼金术士学会了将他人变为休眠傀儡的方法。\n"
    "**半蝎人（Girtablilu）**\n"
    "**半蝎人德鲁伊领域**\n"
    "**虫类领域（Vermin Domain）**：神授力量：你与这些未开智的无脊椎动物建立了深切联系。\n"
    "**虫类朋友（Vermin Friend, Ex）**：如果你还不具备该能力，你可以使用野性认同影响虫类动物。\n"
    "**半蝎人专长**\n"
    "**护卫传统（Guardian of Tradition）**：你对族群职责的奉献让神明降下奖励\n"
    "**鸮形人（Strix）**\n"
    "**鸮形人专长**\n"
    "**摄风之翼（Buffeting Wings, Combat）**：以一个整轮动作，你可以挥舞你的翅膀，制造一阵强风。\n"
)


class TestClusterM17_IsmcStarShell:
    """簇 M17：内海怪物志星壳错位修复形态——条目独立切出、name_en 完整、
    stat block 不拆伪条目、text 无星壳残留"""

    def test_ismc_entries_split(self):
        """修复后标准形态条目全部独立切出（专长/科研发现/领域/章节）"""
        items = run(CLUSTER_M17_ISMC_STARSHELL)
        names = [i["name"] for i in items]
        for want in ("必然毁灭", "汲取之剑", "尸鬼蝙蝠伙伴", "碧幻菌炸弹",
                     "疯狂研究", "休眠傀儡", "虫类领域", "虫类朋友",
                     "护卫传统", "摄风之翼"):
            assert want in names, f"{want} 未独立切出：{names}"

    def test_ismc_name_en_complete(self):
        """name_en 含完整 EN（类型逗号并入字母段，`_split_paren_content`
        空格连接）——修复前 EN 全名留在 text 或丢失"""
        items = run(CLUSTER_M17_ISMC_STARSHELL)
        by_name = {i["name"]: i for i in items}
        want = {
            "必然毁灭": "Assured Destruction",
            "汲取之剑": "Siphoning Blade Combat",
            "疯狂研究": "Method to the Madness Ex",
            "休眠傀儡": "Sleeper Agent Su",
            "虫类朋友": "Vermin Friend Ex",
            "摄风之翼": "Buffeting Wings Combat",
        }
        for name, en in want.items():
            assert by_name[name]["name_en"] == en, \
                f"{name} name_en={by_name[name]['name_en']!r} 期望 {en!r}"

    def test_ismc_stat_block_no_pseudo(self):
        """stat block（` 体型：大型` 行首空格形态）不拆伪条目，并入
        尸鬼蝙蝠伙伴（修复前 `体型：大型` 裸行拆出 title=体型 伪 feat）"""
        items = run(CLUSTER_M17_ISMC_STARSHELL)
        names = [i["name"] for i in items]
        assert "体型" not in names, f"stat block 误拆伪条目：{names}"
        by_name = {i["name"]: i for i in items}
        text = item_text(by_name["尸鬼蝙蝠伙伴"])
        assert "大型" in text, f"stat block 值未并入尸鬼蝙蝠伙伴：{text[:80]!r}"

    def test_ismc_no_star_residue(self):
        """条目 text 不得含星壳残留（`**`/`****`）——修复前 text 以
        `**（Method to the Madness` 开头（星壳残渣）污染检索"""
        items = run(CLUSTER_M17_ISMC_STARSHELL)
        for it in items:
            t = item_text(it)
            assert "****" not in t, f"{it['name']} text 含 4 星残留：{t[:60]!r}"
            assert not t.startswith("**"), \
                f"{it['name']} text 以星壳开头：{t[:60]!r}"


# ============ 簇 M17b：兽态人血统表镜像拆分 + 裸 --- 剥除（M17/KN123） ============
# 兽态人 9 血统 = 镜像表格（`| 中文（EN）［血统名（EN）］　描述… |  |`）——
# 第一列有内容，与神裔/魔裔空第一列形态（M6 `_RE_HERITAGE_TABLE_ROW`）互为镜像，
# 未被匹配 → 整表 3198 字吞进「起始语言」条目。裸 `---` 行 = CHM 转换 HTML
# `<hr>` 的 Markdown 形态（stat block 章节分隔/段落分隔），110 行残留（KN123）。
CLUSTER_M17B_WEREBAT_TABLE = (
    "**起始语言（Languages）：**兽态人使用通用语。拥有高智力属性的兽态人能选择任何额外语言（除了秘密语言，例如德鲁伊语）。\n"
    "\n"
    "---\n"
    "\n"
    "| 蝙蝠人后裔（Werebat-kin）［血印（bloodmarked）］　　这些兽态人通常组成自治团体。替换属性调整（Alternate \n"
    "       Ability Modifiers）：+2智力，-2感知（变形时+2敏捷）替换技能调整（Alternate Skill \n"
    "       Modifiers）：飞行，夜晚的察觉替换类法术能力（Alternate Spell-Like \n"
    "       Ability）：每天1次隐雾术（Obscuring Mist） |  |\n"
    "| --- | --- |\n"
    "\n"
    "| 熊人后裔（Werebear-kin）［冷嗣（Coldborn）］　　在林诺姆诸王国作为旷野的守卫者而闻名。替换属性调整（Alternate \n"
    "       Ability Modifiers）：+2体质，-2魅力（变形时+2感知）替换技能调整（Alternate Skill \n"
    "       Modifiers）：攀爬，野性认同 |  |\n"
    "| --- | --- |\n"
    "\n"
    "| 野猪人后裔（Wereboar-kin）［怒种（Ragebred）］　　这些兽态人以脾气暴躁而闻名。替换属性调整（Alternate Ability \n"
    "       Modifiers）：+2力量，-2魅力（变形时+2体质） |  |\n"
    "| --- | --- |\n"
)

CLUSTER_M17B_STATBLOCK = (
    "**中立善良**\n"
    "超小型魔法兽\n"
    "**先攻**：+3；感官： 60尺黑暗视觉（darkvision），昏暗视觉（low-light vision）；察觉：+8\n"
    "\n"
    "---\n"
    "\n"
    "防御能力（Defense）\n"
    "\n"
    "---\n"
    "\n"
    "AC：18；接触：16；措手不及：14（+3敏捷，+1闪避，+2天生，+2体型）\n"
    "HP：19（3d10+3）\n"
)

CLUSTER_M17B_PROSE_SEP = (
    "**妖鬼婆裔 替换儿（Annis-Born Changelings） 矿砾之女（Slag May）**\n"
    "拥有着宽阔的肩膀和健壮的体格。\n"
    "\n"
    "祖先：妖鬼婆（Annis hag）\n"
    "\n"
    "---\n"
    "\n"
    "**灰烬鬼婆裔 替换儿（Ash-Born Changelings） 壁炉之女（Hearth May）**\n"
    "拥有着火焰般炽热的内心。\n"
)


class TestClusterM17b_WerebatTable:
    """簇 M17b：兽态人血统表（镜像表格）+ 裸 `---` 剥除"""

    def test_start_language_standalone(self):
        """起始语言独立条目，不再吞并血统表（修复前 9 血统整表并入）"""
        items = run(CLUSTER_M17B_WEREBAT_TABLE)
        names = [it["name"] for it in items]
        assert "起始语言" in names, f"起始语言应独立：{names}"
        it = next(i for i in items if i["name"] == "起始语言")
        t = item_text(it)
        assert "兽态人使用通用语" in t, "起始语言正文完整"
        assert "蝙蝠人后裔" not in t, "血统表不应并入起始语言"

    def test_werebat_rows_split(self):
        """镜像表格行拆出独立血统条目（蝙蝠/熊/野猪后裔）"""
        items = run(CLUSTER_M17B_WEREBAT_TABLE)
        names = [it["name"] for it in items]
        for n in ("蝙蝠人后裔", "熊人后裔", "野猪人后裔"):
            assert n in names, f"血统应切出：{names}"

    def test_werebat_name_en_fields_heritage(self):
        """name_en 完整 + 字段链 + 血统名入 text（信息零丢失）"""
        items = run(CLUSTER_M17B_WEREBAT_TABLE)
        it = next(i for i in items if i["name"] == "蝙蝠人后裔")
        assert it["name_en"] == "Werebat-kin", f"name_en={it['name_en']!r}"
        t = item_text(it)
        assert "替换属性调整（Alternate Ability Modifiers）：+2智力" in t, "字段链完整"
        assert "替换技能调整（Alternate Skill Modifiers）：飞行" in t
        assert "替换类法术能力（Alternate Spell-Like Ability）：每天1次隐雾术" in t
        assert "血印（bloodmarked）" in t, "血统名入 text"
        assert "这些兽态人通常组成自治团体" in t, "描述段并入"

    def test_werebat_no_table_marks(self):
        """`| ---` 分隔行、表格前缀、裸 `---` 行均不残留"""
        items = run(CLUSTER_M17B_WEREBAT_TABLE)
        for it in items:
            t = it.get("text", "")
            assert "| ---" not in t and "| 蝙蝠" not in t, f"表格残留：{it['name']}"
            assert not re.search(r"^[ \t]*---[ \t]*$", t, re.M), f"--- 残留：{it['name']}"

    def test_statblock_hr_stripped(self):
        """stat block 章节 `---` 剥除、防御能力章节标题保留"""
        items = run(CLUSTER_M17B_STATBLOCK)
        assert items, "应产出条目"
        for it in items:
            t = it.get("text", "")
            assert not re.search(r"^[ \t]*---[ \t]*$", t, re.M), f"--- 残留：{it['name']}"
        joined = " ".join(it.get("text", "") for it in items)
        assert "防御能力（Defense）" in joined or "AC：18" in joined, "章节内容保留"

    def test_prose_hr_stripped(self):
        """prose 段落分隔 `---` 剥除、两侧条目正文完整"""
        items = run(CLUSTER_M17B_PROSE_SEP)
        for it in items:
            t = it.get("text", "")
            assert not re.search(r"^[ \t]*---[ \t]*$", t, re.M), f"--- 残留：{it['name']}"
        names = [it["name"] for it in items]
        assert "妖鬼婆裔替换儿" in names, f"条目缺失：{names}"

CLUSTER_M17B_BOTC_FULL = (
    "**替换儿亚种（Changeling  Subraces）**\n"
    "\n"
    "---\n"
    "\n"
    "**妖鬼婆裔 替换儿（Annis-Born Changelings） 矿砾之女（Slag May）**\n"
    "拥有着宽阔的肩膀和健壮的体格。\n"
    "\n"
    "祖先：妖鬼婆（Annis hag）\n"
    "\n"
    "---\n"
    "\n"
    "**灰烬鬼婆裔 替换儿（Ash-Born Changelings） 壁炉之女（Hearth May）**\n"
    "拥有着火焰般炽热的内心。\n"
)


class TestClusterM17c_H2NoSwallowPureTitle:
    """簇 M17c：`---` 剥除暴露的 M9 H2 吞并缺陷——H2 主标题（空 text）
    后的纯标题行不得并入作正文（旧库 `---` 行侥幸填充 H2 text 阻止吞并，
    KN123 剥 `---` 后 BotC 首个替换儿被并入「替换儿亚种」intro）"""

    def test_botc_first_subrace_not_swallowed(self):
        """妖鬼婆裔替换儿（H2 后首个纯标题行）独立切出，不并入替换儿亚种"""
        items = run(CLUSTER_M17B_BOTC_FULL)
        names = [it["name"] for it in items]
        assert "妖鬼婆裔替换儿" in names, f"首个子条目应独立：{names}"
        it = next(i for i in items if i["name"] == "妖鬼婆裔替换儿")
        assert "矿砾之女" in it.get("text", ""), "正文并入子条目"
        assert "拥有着宽阔的肩膀" in it.get("text", "")

    def test_h2_star_colon_still_merged(self):
        """M9 场景不回归：H2 后 `**X（EN）**：正文` 同行形态仍并入 H2
        （ISR 勒珊塔灵族 `**勒珊塔灵族角色（…）**：拉申塔人是…`）"""
        raw = (
            "**勒珊塔灵族（Lashunta）**\n"
            "\n"
            "**勒珊塔灵族角色（Lashunta Characters，11 RP）**：拉申塔人是…\n"
            "**两性异形**：勒珊塔灵族男女差异…\n"
        )
        items = run(raw)
        by_name = {it["name"]: it for it in items}
        assert "勒珊塔灵族" in by_name, f"H2 条目应存在：{list(by_name)}"
        it = by_name["勒珊塔灵族"]
        assert "拉申塔人是" in it.get("text", ""), f"标题+正文同行应并入：{it['text'][:60]!r}"


CLUSTER_W_FEAT_TABLE = (
    # 真实 page_129 神裔形态：物品条目 → 专长章节标题（星壳错位）→
    # 表标题/表头/数据行（EN+中文 跨行）
    "**熏香（****Incense****）**：这种由圣油和芳香树脂制成的熏香通常为棒状、锥形或球形，用于在举行仪式或进行冥想期间焚烧。一枚熏香可以燃烧1个小时。熏香（10枚装）价格10gp，重1磅。\n"
    "**神裔专长****（****Aasimar**** Feats****）******\n"
    "\n"
    "| 表：神裔专长简述 |\n"
    "| --- |\n"
    "| 专长名称 | 先决条件 | 专长效果 |\n"
    "| Angelic Blood\n"
    "       天使之血 | 体质13，神裔 | 对邪恶效果豁免和稳定伤势检定+2，并在出血时伤害邪恶生物 |\n"
    "| Angelic Flesh\n"
    "       天使之躯 | 天使之血 | 易容和隐匿技能-2，但根据金属血脉获得各种强化 |\n"
)


class TestClusterW_StripFeatTableRows:
    """簇 W：专长简述表行剥离（KN133 物品粘专长简述表家族）——表格数据行
    （首格 EN+中文）、表标题（| 表：…简述 |）、表头行剥除，物品条目 text
    不被表格污染；stat block 表（首格纯 EN 标签，如 | AC |）保留"""

    def test_item_not_contaminated_by_table(self):
        """熏香条目 text 不含任何表格残留（表标题/表头/数据行全剥离）"""
        items = run(CLUSTER_W_FEAT_TABLE)
        by_name = {i["name"]: i for i in items}
        it = by_name.get("熏香")
        assert it is not None, f"熏香条目应存在：{list(by_name)}"
        t = item_text(it)
        assert "重1磅" in t, f"物品正文保留：{t[:60]!r}"
        assert "表：" not in t, f"表标题不得残留：{t[:60]!r}"
        assert "专长名称" not in t, f"表头不得残留：{t[:60]!r}"
        assert "Angelic" not in t, f"表格数据行不得残留：{t[:60]!r}"

    def test_feat_section_title_not_in_item(self):
        """专长章节标题（星壳错位归一后）是状态切换器不产条目，且不得被
        表格剥除规则误伤或并入物品条目 text"""
        items = run(CLUSTER_W_FEAT_TABLE)
        t = item_text(next(i for i in items if i["name"] == "熏香"))
        assert "神裔专长" not in t, f"章节标题不得并入物品：{t[:60]!r}"

    def test_table_rows_stripped_no_items(self):
        """表格数据行不产生条目也不残留——天使之血/天使之躯是表格行中文
        名（此样本无详述段），不得被识别为条目"""
        items = run(CLUSTER_W_FEAT_TABLE)
        names = [i["name"] for i in items]
        assert "天使之血" not in names, f"表格行不得成条目：{names}"

    def test_table_note_row_stripped(self):
        """表格尾注行（`| * 标注星号专长为战斗专长。 |`）随表剥除——不得
        残留进物品条目（page_167 不稳定促进剂真实形态）"""
        raw = (
            "**不稳定促进剂（Unstable Accelerant）**：正文。价格50gp。\n"
            "| * 标注星号专长为战斗专长。 |\n"
        )
        items = run(raw)
        t = item_text(items[0])
        assert "标注星号" not in t, f"尾注行应剥除：{t!r}"

    def test_table_note_row_cr_spaces_stripped(self):
        """尾注行 CR+空格变体（`| * \r       标注星号… |`，page_165~167/
        204/205/238 真实形态）随表剥除——2026-08-04 全库 13 残留复扫发现
        星号后为 CR+8 空格，固定单空格正则失配"""
        raw = (
            "**影脂（Shadow Blight）**：正文。重1磅。\n"
            "| * \r       标注星号专长为战斗专长。 |\n"
        )
        items = run(raw)
        t = item_text(items[0])
        assert "标注星号" not in t, f"CR 变体尾注行应剥除：{t!r}"

    def test_statblock_table_row_kept(self):
        """stat block 表（首格纯 EN 字段标签无中文）保留——`| AC | +2天生
        护甲 |`（page_13 真实形态）不得被剥除"""
        raw = (
            "**盔甲（Armor）**：正文。\n"
            "| AC |  | +2天生护甲 |  |  |\n"
            "| AC |  | +1天生护甲 |  | +2天生护甲 |\n"
        )
        items = run(raw)
        texts = " ".join(item_text(i) for i in items)
        assert "+2天生护甲" in texts, f"stat block 行应保留：{texts[:80]!r}"
        assert "+1天生护甲" in texts, f"stat block 行应保留：{texts[:80]!r}"


class TestClusterW3_BareCNDigits:
    """簇 W3：裸中文标题含数字/加号（page_815 `**替换+2天生护甲**` 组标题，
    2026-08-04 跨行星壳源数据修复后形态）——识别为标题独立成组，不并入
    前一条目；组内首个特性并入组标题 text（与「替换美味可口和世代传承」
    组同构，chunk 0003 既有行为）"""

    def test_group_title_with_digits_not_merged(self):
        """含 + 数字的裸中文组标题识别：修复前落散文分支并入前条目（天然
        伪装+组标题残留进「替换美味可口和世代传承」）；修复后独立成组"""
        raw = (
            "**替换美味可口和世代传承**\n"
            "**难以下咽**：一些蒿兰人因为过去生活逐渐腐烂。\n"
            "这个种族特性取代美味可口和世代传承。\n\n"
            "**替换+2天生护甲**\n"
            "**天然伪装**：一些蒿兰人通过在不同的位置重新播种而进化。\n"
            "这个种族特性取代+2天生护甲。\n"
        )
        items = run(raw)
        by_name = {it["name"]: it for it in items}
        # 组标题独立切出，text 承载组内首个特性（同难以下咽并入机制）
        assert "替换+2天生护甲" in by_name, f"组标题应独立切出: {list(by_name)}"
        assert "天然伪装" in by_name["替换+2天生护甲"]["text"], \
            "天然伪装应并入本组标题 text"
        # 前一条目不残留组标题/子条目
        prev = by_name.get("替换美味可口和世代传承")
        assert prev is not None
        t = item_text(prev)
        assert "替换+2天生护甲" not in t, f"组标题残留: {t!r}"
        assert "天然伪装" not in t, f"子条目残留: {t!r}"


class TestClusterW4_BoS_SourceTagInTitle:
    """簇 W4：BoS 删线壳剥除后标题形态 `**X（EN）（N RP）【BoS】**：正文`
    （page_398 面纱之后/混合视觉/幽暗居民/昏暗精准/暗影猎手等 8 条，
    2026-08-04 KN133）——`_RE_TITLE` 第二括号（N RP）后跟 `【BoS】` 来源
    标注，原 lookahead 只容 `：`/汇总/闭合星/行尾，`【BoS】` 整行失配 →
    标题并入前一条目。修复：第二括号 lookahead 加 `[〔［【]` + 吞尾缀组"""

    def test_bos_tag_after_rp_paren(self):
        """面纱之后形态：`（1RP）` 后跟 `【BoS】` → 切出且尾缀不残留"""
        raw = (
            "**面纱之后（Behind the Veil）（1RP）【BoS】**：有着该特性的"
            "人物擅长隐藏他们的肢体语言。\n"
        )
        items = run(raw)
        by_name = {it["name"]: it for it in items}
        assert "面纱之后" in by_name, f"BoS 尾缀标题应切出: {list(by_name)}"
        it = by_name["面纱之后"]
        assert "【BoS】" not in it["text"], f"来源标注残留 text: {it['text']!r}"
        assert "【BoS】" not in it["name"], f"来源标注残留 title: {it['name']!r}"

    def test_bos_tag_then_body_own_line(self):
        """暗影猎手形态：标题行独立、正文另起行（`**X（EN）（2RP）【BoS】**\n正文`）"""
        raw = (
            "**暗影猎手（Shadowhunter）（2RP）【BoS】**\n"
            "那些懂得阴影和负能量位面之间的链接的生物懂得如何和黑暗的精神存在战斗。\n"
        )
        items = run(raw)
        by_name = {it["name"]: it for it in items}
        assert "暗影猎手" in by_name, f"标题行独立形态应切出: {list(by_name)}"
        t = item_text(by_name["暗影猎手"])
        assert t.startswith("那些懂得阴影"), t

    def test_star_closed_colon_then_body(self):
        """混合视觉形态：`**X（EN）（2RP）【BoS】**：正文`（闭合星+冒号同行）"""
        raw = (
            "**混合视觉（Blended View）（2RP）【BoS】**：先决条件：昏暗视觉。"
            "有着非卓尔长辈的半卓尔可能有着来自遗传赠与的昏暗视觉。\n"
        )
        items = run(raw)
        by_name = {it["name"]: it for it in items}
        assert "混合视觉" in by_name, f"闭合星+冒号形态应切出: {list(by_name)}"
        t = item_text(by_name["混合视觉"])
        # 正文首行「先决条件：」被 _wrap_bare_field_labels 包星并入 text
        # （字段行既有行为，黑暗之声等产物同形态），断言正文内容在
        assert "昏暗视觉" in t, t
        assert "【BoS】" not in t, f"来源标注残留 text: {t!r}"

# ============ 簇 T：裸职业行 UNSTARRED fcb_entry 并入路径升级（KN133） ============


CLUSTER_T_BOTS_SAHUAGIN = (
    "**天赋职业选项**\n"
    "**沙华鱼人**\n"
    "来源：《海洋血脉》第17页\n"
    "沙华鱼人拥有人类与鲨鱼的混合特质。\n"
    "**沙华鱼人种族特性**\n"
    "**盲感（Blindsense）**：沙华鱼人具有30英尺盲感。\n"
)

CLUSTER_T_FCB_PLAIN = (
    "**天赋职业选项**\n"
    "野蛮人：从你的基本速度中选择+5尺。\n"
)


class TestClusterT_BareColonUpgradeInFcbEntry:
    """簇 T：`_RE_BARE_CN_COLON_UNSTARRED` fcb_entry 态并入路径缺失升级
    逻辑（KN133）——BotS 沙华鱼人 `**沙华鱼人**`（fcb_entry 残留态裸
    标题）+ `来源：《海洋血脉》第17页`（裸冒号行）被并入 text 且残留
    fcb_entry（狐妖/剪影人走散文分支有升级，UNSTARRED 并入路径无）；
    修复后并入路径复用同一升级判定"""

    def test_sahuagin_bare_title_upgrade(self):
        """沙华鱼人形态：裸标题（fcb_entry 残留态）+ 裸冒号来源行 →
        升级 race_intro、来源行并入 text、state 重置（后续特性 race_trait
        而非残留 fcb_entry）"""
        items = run(CLUSTER_T_BOTS_SAHUAGIN)
        by_kind = {it["name"]: it["kind"] for it in items}
        by_item = {it["name"]: it for it in items}
        assert by_kind.get("沙华鱼人") == "race_intro", \
            f"裸标题+来源行应升级 race_intro（修复前残留 fcb_entry）：{by_kind}"
        t = item_text(by_item["沙华鱼人"])
        assert "来源：《海洋血脉》第17页" in t, f"来源行应并入 text：{t!r}"
        assert by_kind.get("盲感") == "race_trait", \
            f"state 重置后盲感应 race_trait（修复前残留 fcb_entry）：{by_kind}"

    def test_plain_fcb_entry_unchanged(self):
        """回归保护：正常裸职业行（cur 空）仍切 fcb_entry 不升级——
        升级判定要求 _bare_cn_title 标记，切出的条目无标记不误伤"""
        items = run(CLUSTER_T_FCB_PLAIN)
        by_kind = {it["name"]: it["kind"] for it in items}
        assert by_kind.get("野蛮人") == "fcb_entry", \
            f"裸职业行应保持 fcb_entry：{by_kind}"
