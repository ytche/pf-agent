"""
test_trait_format.py — 背景特性格式解析 TDD 测试（test_seeds.jsonl 驱动）

数据源：vectorizer/exploration/trait/test_seeds.jsonl（16 条：12 positive + 4 negative）
驱动方：背景特性模块 TDD 第 3 步（test_seeds.jsonl 驱动写 formats/trait.py）
断言口径：TraitFormat.normalize → promote → split_into_items 产出的 item dict：
  name / name_en / trait_type / requirement / deity / source / pfs_eligible / flaw / format_cluster / text
"""

import json
import re
from pathlib import Path

from vectorizer.formats.trait import TraitFormat

SEEDS_PATH = Path(__file__).parent.parent / "exploration" / "trait" / "test_seeds.jsonl"


def load_seeds():
    with open(SEEDS_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


SEEDS = load_seeds()


def run(raw: str, source_name: str = "seed") -> list:
    """TraitFormat 全链：normalize → promote → split"""
    fmt = TraitFormat()
    text = fmt.normalize(raw)
    text = fmt.promote(text)
    return fmt.split_into_items(text, source_name=source_name)


def item_text(it: dict) -> str:
    """条目 text 归一化（去空白差异）供断言"""
    return re.sub(r"\s+", " ", it.get("text", ""))


class TestTraitSeeds:
    """16 条 test_seeds 逐条断言"""

    # ---------- positive ----------

    def test_seed_00_page150_four_shell(self):
        """[0] A_basic_page 四壳星壳条目 + 【书缩写】来源 + 跨行英文名"""
        items = run(SEEDS[0]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "甲胄士"
        assert it["name_en"] == "Armor Expert"  # 跨行英文名合并
        assert it["source"] == "APG"             # 【书缩写】→ source
        assert "甲胄" in item_text(it)

    def test_seed_01_page150_section_title(self):
        """[1] 章节标题（星壳+英文跨行，无【书】无正文）——必须排除"""
        assert run(SEEDS[1]["raw_snippet"]) == []

    def test_seed_02_page150_glossary_para(self):
        """[2] 名词解释段（无星壳裸名+同行英文名）——不得误判为条目"""
        assert run(SEEDS[2]["raw_snippet"]) == []

    def test_seed_03_page150_append_entry(self):
        """[3] 补录段单星壳形态（**X（EN）【书】****：**）+ 尾部星壳归一"""
        items = run(SEEDS[3]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "慈悲之刃"
        assert it["name_en"] == "Merciful Scimitar"
        assert it["source"] == "WMH"
        t = item_text(it)
        assert "****" not in t, f"text 不应含星壳残留：{t[:30]!r}"
        assert "莎伦莱的修士" in t

    def test_seed_04_qjote_h2(self):
        """[4] B2_standard_h2：H2 标题 + 出自行页码跨行 + 标准冒号字段"""
        items = run(SEEDS[4]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "移情外交家"
        assert it["name_en"] == "Empathic Diplomat"
        assert it["trait_type"] == ["地区"]
        assert "卡蒂亚或奥斯里昂" in it["requirement"]
        assert "卡蒂亚，东方之珠 pg. 10" in it["source"]  # 页码跨行合并
        assert "将心比心" in item_text(it)

    def test_seed_05_isg_flow_bare(self):
        """[5] B3_flow_bare（ISG）：流式裸名 + 神名括号（非英文名）+ 英文名三行跨行"""
        items = run(SEEDS[5]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "亲近元素"
        assert it["name_en"] == "Affinity for the Elements"  # 三行合并
        assert "元素领主" in it["deity"]                      # 括号→deity 而非英文名
        assert it["trait_type"] == []                          # 无字段行，缺失

    def test_seed_06_isg_link_removed(self):
        """[6] B3_flow_bare（ISG）：流式条目 + 翻译链接残留剥除（正文完整）"""
        items = run(SEEDS[6]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "机运使徒"
        assert it["name_en"] == "Agent of Chance"
        assert "妮薇" in it["deity"]  # 神名括号跨行
        t = item_text(it)
        assert "goddessfantasy.net" not in t, "链接壳应剥除"
        assert "改变他人的命运" in t

    def test_seed_07_quest_b4_no_colon(self):
        """[7] B4_field_no_colon：加粗裸名标题 + 字段无冒号值下一行 + 效果下一行"""
        items = run(SEEDS[7]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "印象深刻"
        assert it["name_en"] == "Memorable"
        assert it["trait_type"] == ["社会"]
        assert "一大群孩子中长大" in item_text(it)
        assert "Quests and Campaigns" in it["source"]  # 出自行同行

    def test_seed_08_eod_split_field_label(self):
        """[8] B1_star_field（EOD）：星壳标题 + 断行字段标签分裂（**分类+**基础（战斗））"""
        items = run(SEEDS[8]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "速饮者"
        assert it["name_en"] == "Accelerated Drinker"
        assert it["trait_type"] == ["战斗"]  # 分裂合并 + 基础（X）剥壳（人工门 1 拍板）
        assert "Cheliax, Empire of Devils" in it["source"]
        assert "快速而熟练" in item_text(it)

    def test_seed_09_foc_dual_source(self):
        """[9] B5_dual_source：单《》双书出自行跨行 + 裸字段（类型：无星壳）"""
        items = run(SEEDS[9]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "元素亲和"
        assert it["name_en"] == "Affinity for the Elements"
        assert it["trait_type"] == ["宗教"]
        assert "元素领主" in it["requirement"]  # 需求值跨行
        assert "Inner Sea Gods pg. 218" in it["source"]
        assert "Faiths of Corruption pg. 19" in it["source"]  # 双书都保留

    def test_seed_10_fm_triple_title(self):
        """[10] B3_triple_title：三重标题（## 裸中文 + ## 中文（EN） + **中文（EN）**）归一为 1 条目"""
        items = run(SEEDS[10]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "前奴隶"
        assert it["name_en"] == "Freed Slave"  # 双空格归一

    def test_seed_11_pp_glue(self):
        """[11] B1_glue：段内粘连无标题（中文名+换行英文名（地区）：正文）"""
        items = run(SEEDS[11]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "炼金销赃者"
        assert it["name_en"] == "Alchemical Fence"
        assert "卡塔佩什" in item_text(it)
        assert "广阔集市" in item_text(it)

    def test_seed_12_page158_flaw_entry(self):
        """[12] C_flaw 缺陷条目：效果字段 + 无标题——标记 flaw"""
        items = run(SEEDS[12]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["flaw"] is True
        assert "交涉检定获得-2罚值" in item_text(it)

    def test_seed_14_cosmic_table(self):
        """[14] D_exalted_mount_cosmic：背景特性17 表格条目簇（星座表）"""
        items = run(SEEDS[14]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}（表头/分隔行不应产）"
        it = items[0]
        assert it["name"] == "画眉鸟座"
        assert it["name_en"] == "The Thrush"
        assert "表演（演唱）检定上获得+1加值" in item_text(it)

    def test_seed_15_aco_high_entropy(self):
        """[15] B9_high_entropy（ACO）：星壳标题+星壳字段无冒号+需求值跨行"""
        items = run(SEEDS[15]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "狮子的勇气"
        assert it["name_en"] == "Lion’s Audacity"  # 撇号星壳分裂归一同理
        assert it["trait_type"] == ["地区"]
        assert "塔尔多人" in it["requirement"]  # 星壳字段无冒号值跨行
        assert "雄狮般的凶猛" in item_text(it)

    # ---------- negative ----------


    def test_seed_17_type_word_suffix_no_crash(self):
        """[17] 星壳标题 +【类型词】后缀（【地区】→ trait_type 非 source）——tag_src 回归"""
        items = run(SEEDS[16]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "盾卫"
        assert it["name_en"] == "Shield Ward"
        assert it["trait_type"] == ["地区"]
        assert it["source"] == ""  # 类型词不落入 source

    def test_seed_13_page158_pfs_disabled(self):
        """[13] 【PFS】禁用标记——不得误判为条目"""
        assert run(SEEDS[13]["raw_snippet"]) == []

    def test_seed_18_page158_flaw_star_title(self):
        """[18] 缺陷条目星壳标题形态（真实 page_158 主体）——不得被章节标题判据误杀"""
        items = run(SEEDS[17]["raw_snippet"], source_name="page_158.md")
        assert len(items) == 1, f"应产出 1 个缺陷条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "忧虑"
        assert it["name_en"] == "Anxious"
        assert it["flaw"] is True
        t = item_text(it)
        assert "孩提时代" in t
        assert "交涉检定获得-2罚值" in t

    def test_seed_19_kis_star_title_body(self):
        """[19] 星壳标题+正文下一行（无字段无出自行）——真实条目不得误杀（KIS 自由）"""
        items = run(SEEDS[18]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "自由"
        assert it["name_en"] == "Freedom"
        assert "遵循自由准则" in item_text(it)

    def test_seed_20_page158_half_title_bare_book(self):
        """[20] 缺陷半星壳+同行裸英文书名（被背叛/Betrayed，Spymaster's Handbook）"""
        items = run(SEEDS[19]["raw_snippet"], source_name="page_158.md")
        assert len(items) == 1, f"应产出 1 个缺陷条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "被背叛"
        assert it["name_en"] == "Betrayed"
        assert it["flaw"] is True
        assert "Spymaster's Handbook" in it["source"]  # 同行书缩写拆行入 source
        assert "首次互动" in item_text(it)

    def test_seed_21_page158_half_title_zh_book(self):
        """[21] 缺陷半星壳+同行《书》第N页+英文名跨行（神秘交易/Occult Bargain）"""
        items = run(SEEDS[20]["raw_snippet"], source_name="page_158.md")
        assert len(items) == 1, f"应产出 1 个缺陷条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "神秘交易"
        assert it["name_en"] == "Occult Bargain"  # 英文名跨行合并
        assert it["flaw"] is True
        assert "间谍大师手册" in it["source"]
        assert "第7页" in it["source"]
        assert "专注检定中承受-1减值" in item_text(it)

    def test_seed_22_page158_unclosed_title(self):
        """[22] 缺陷跨行无闭合星壳（急躁：`**X（EN）` + 下一行 `**《书》 第N页`）"""
        items = run(SEEDS[21]["raw_snippet"], source_name="page_158.md")
        assert len(items) == 1, f"应产出 1 个缺陷条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "急躁"
        assert it["name_en"] == "Impatient"
        assert it["flaw"] is True
        assert "反英雄手册" in it["source"]  # 跨行出处合并
        assert "准备动作" in item_text(it)

    def test_seed_23_page158_quad_paren_left(self):
        """[23] 缺陷四壳残留（污染之魂：`（****Tainted Spirit)` 缺右星闭合）"""
        items = run(SEEDS[22]["raw_snippet"], source_name="page_158.md")
        assert len(items) == 1, f"应产出 1 个缺陷条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "污染之魂"
        assert it["name_en"] == "Tainted Spirit"  # 四星残留归一
        assert it["flaw"] is True

    def test_seed_24_page158_slash_dual_title(self):
        """[24] 缺陷斜杠双译名+无括号英文名跨行（奥术恶性状态/奥术畸变 Arcane Malignancies）"""
        items = run(SEEDS[23]["raw_snippet"], source_name="page_158.md")
        assert len(items) == 1, f"应产出 1 个缺陷条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "奥术恶性状态"
        assert it["name_en"] == "Arcane Malignancies"  # 无括号英文名跨行拆出
        assert it["flaw"] is True
        assert "巫团血脉" in it["source"]
        assert "第十页" in it["source"]

    def test_seed_25_isg_file_header_h2(self):
        """[25] 文件头 H2（书中文名+背景特性）+ 引用块——不产伪条目，流式条目正常"""
        items = run(SEEDS[24]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目（文件头 H2/引用块不产），实际 {len(items)}"
        it = items[0]
        assert it["name"] == "规避意外"
        assert it["name_en"] == "Accident Resistant"
        assert "泽弗斯" in it["deity"]
        assert "来源" not in it["text"]  # 引用块不并入正文

    def test_seed_26_bm_source_comment_strip(self):
        """[26] 条目级 HTML 注释行（BM-source 标记）——剥除，不并入正文"""
        items = run(SEEDS[25]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "隐秘信徒"
        assert it["name_en"] == "Covert Channeler"
        assert "<!--" not in it["text"], f"text 不应含 HTML 注释：{it['text'][:60]!r}"
        assert "快速" in item_text(it)  # 正文完整保留

    def test_seed_27_pfs_star_prefix(self):
        """[27] 【PFS】在星壳标题内（坐骑背景）——pfs_eligible 标记而非类型"""
        items = run(SEEDS[26]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "爆发之速"
        assert it["pfs_eligible"] is True
        assert "PFS" not in it["trait_type"], f"PFS 不得混入类型：{it['trait_type']}"
        assert it["trait_type"] == ["地区"]

    def test_seed_28_isp_dual_paren_long_en(self):
        """[28] 双括号星壳：中文地名括号 + 英文名括号超长（[Andoran] 21 字符）——不得吞并"""
        items = run(SEEDS[27]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目（解放奴），实际 {len(items)}"
        it = items[0]
        assert it["name"] == "解放奴"
        assert it["name_en"] == "Freed Slave  [Andoran]"  # 英文名括号（方括号原样）
        assert "安多安" not in it["trait_type"], f"地名不得混入类型：{it['trait_type']}"
        assert "解放奴" not in it["text"]  # 标题行不得被吞入正文

    def test_seed_29_field_paren_comma(self):
        """[29] 字段值括号内顿号（种族背景（半精灵、半兽人或人类））——不拆括号内"""
        items = run(SEEDS[28]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "北地人民"
        assert "种族背景（半精灵、半兽人或人类）" in it["trait_type"], (
            f"括号内顿号不得拆分：{it['trait_type']}"
        )
        assert not any("半精灵'" in t for t in it["trait_type"])

    def test_seed_30_flow_paren_top_level(self):
        """[30] 流式括号含类型词+顿号（地区，世界之冠）——顶层拆分 + 非类型词丢弃"""
        items = run(SEEDS[29]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "艾鲁塔基的读天者"
        assert it["trait_type"] == ["地区"], f"世界之冠应丢弃：{it['trait_type']}"

    # ---------- 产出即检形态缺口（2026-08-05，est↔got 对账 33 文件缺口） ----------

    def test_seed_31_page154_quad_glue_title(self):
        """[30] 四壳断裂+书缩写同行（秘文会：`**A****（****EN****）**【书】**：`）——四星粘连合并"""
        items = run(SEEDS[30]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "秘文会"
        assert it["name_en"] == "Dark Archive"
        assert it["source"] == "PFS Guide"  # 【PFS Guide】→ 条目级书缩写
        assert "秘文会" in item_text(it)

    def test_seed_32_page157_post_deity_cn(self):
        """[31] 英文名残星+阵营尾缀+后置神祇括号（圣娼姬）——deity 提取、阵营剥离"""
        items = run(SEEDS[31]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "圣娼姬"
        assert it["name_en"] == "Calistrian Divine Courtesan"  # 阵营尾缀剥离
        assert it["deity"] == "卡莉斯翠"
        assert it["source"] == "APG"
        assert "混乱中立" not in it["name_en"]

    def test_seed_33_page157_post_deity_en(self):
        """[32] 后置神祇括号+种族（背刺者）——deity=神祇英文名，source=HoG"""
        items = run(SEEDS[32]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "背刺者"
        assert it["name_en"] == "Backstabber"
        assert it["deity"] == "Thamir Gixx"
        assert it["source"] == "HoG"

    def test_seed_34_page1579_colon_in_star(self):
        """[33] 星壳标题冒号在壳内（家传武器：`**A（EN）：**`）——冒号移出"""
        items = run(SEEDS[33]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "家传武器"
        assert it["name_en"] == "Heirloom Weapon"
        assert "家传武器" in item_text(it)

    def test_seed_35_pis_bare_en_trail(self):
        """[34] 星壳中文名+裸英文名行尾（破链者：`**A**EN（地区）`）"""
        items = run(SEEDS[34]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "破链者"
        assert it["name_en"] == "Chainbreaker"
        assert "安多安" not in it["trait_type"], f"地区名不得混入类型：{it['trait_type']}"

    def test_seed_36_varisia_bare_en_src(self):
        """[35] 星壳+裸英文+残星+出处同行（桥下居民）——出处拆行"""
        items = run(SEEDS[35]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "桥下居民"
        assert it["name_en"] == "Underbridge Dweller"
        assert "瓦瑞西亚" in it["source"], f"出自行拆行失败：{it['source']!r}"

    def test_seed_37_stlc_bare_en_src(self):
        """[36] 星壳+裸英文+残星+来源同行（精魂语者）——来源拆行"""
        items = run(SEEDS[36]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "精魂语者"
        assert it["name_en"] == "Spirit Talker"
        assert "Sargava" in it["source"]

    def test_seed_38_dwarf_star_colon(self):
        """[37] 星壳中文名+裸英文名+冒号正文（头脑清醒：`**A**EN：正文`）"""
        items = run(SEEDS[37]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "头脑清醒"
        assert it["name_en"] == "Clearheaded"
        assert "炉火旁" in item_text(it)

    def test_seed_39_dwarf_bare_colon(self):
        """[38] 裸行中文名+英文名+冒号正文（深刻标记）——补星壳"""
        items = run(SEEDS[38]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "深刻标记"
        assert it["name_en"] == "Deep Marker"
        assert "纹身" in item_text(it)

    def test_seed_40_dwarf_halfwidth(self):
        """[39] 裸行中文名+英文名+半角括号半角冒号（战地诗人）"""
        items = run(SEEDS[39]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "战地诗人"
        assert it["name_en"] == "Warrior Poet"
        assert "战歌" in item_text(it)

    def test_seed_41_teog_glue(self):
        """[40] 中文名+空格+英文名+中文正文粘连（骑士精神，无冒号）"""
        items = run(SEEDS[40]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "骑士精神"
        assert it["name_en"] == "Chivalrous"
        assert "成长" in item_text(it)

    def test_seed_42_wo_bare_title_field(self):
        """[41] 裸行中文名+英文名+下一行字段行（风语者）——字段跟随才产条目"""
        items = run(SEEDS[41]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "风语者"
        assert it["name_en"] == "Windspeaker"
        assert "地区背景（沙漠）" in it["trait_type"], f"字段值原样保留：{it['trait_type']}"

    def test_seed_43_potn_bare_title_desc(self):
        """[42] 裸行中文名+英文名+下一行描述字段（传奇伤痕）——描述并入正文"""
        items = run(SEEDS[42]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "传奇伤痕"
        assert it["name_en"] == "Storied Scars"
        assert "战斗" in it["trait_type"]
        assert "伤痕" in item_text(it)

    def test_seed_44_da_link_anchor(self):
        """[43] 翻译链接锚文本作标题（次经侍祭）——链接剥除+裸英文并入"""
        items = run(SEEDS[43]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "次经侍祭"
        assert it["name_en"] == "Acolyte of Apocrypha"
        assert it["trait_type"] == ["信仰"]  # 基础（信仰）归一
        assert "次经" in item_text(it)

    def test_seed_45_stlc_trail_cn(self):
        """[44] 星壳标题+同行中文译名行尾（跨界魔法）——补冒号防吞并"""
        items = run(SEEDS[44]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "跨界魔法"
        assert it["name_en"] == "Two-World Magic"
        assert "世界魔法" not in it["name"], f"同行译名不得并入标题：{it['name']}"

    def test_seed_46_bota_pfs_trail(self):
        """[45] 星壳标题+PFS 尾缀（此翼天成：`**A(EN)PFS可**`）——转前置标记"""
        items = run(SEEDS[45]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "此翼天成"
        assert it["name_en"] == "Natural Flyer"
        assert it["pfs_eligible"] is True
        assert it["source"] == "Blood of the Ancients pg. 27"
        assert "PFS" not in it["trait_type"]

    def test_seed_47_bota_intro_glue(self):
        """[46] 引导句星壳+条目同行（自然主义者）——拆行不吞并"""
        items = run(SEEDS[46]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "自然主义者"
        assert it["name_en"] == "Naturalist"
        assert "祖先" in item_text(it)

    def test_seed_48_aco_source_book(self):
        """[47] 半星壳+同行出自《书》无页数+半角撇号（狮子的勇气）"""
        items = run(SEEDS[47]["raw_snippet"])
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "狮子的勇气"
        assert it["name_en"] == "Lion's Audacity"
        assert "进化职业起源" in it["source"]

    def test_seed_49_page154_quad_book_colon(self):
        """[48] 四壳断裂标题+【书】+冒号正文同行（page_154 图书馆员）——
        `**A****（****EN****）【书】：**正文` ——guard 不拆 elided + 冒号移出闭星"""
        raw = "**图书馆员****（****Librarian****）【PFS Guide】：**你受过管理书籍的训练，你的语言学和专业（图书馆员）技能获得+1背景加值。"
        items = run(raw, source_name="page_154.md")
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "图书馆员"
        assert it["name_en"] == "Librarian"
        assert it["source"] == "PFS Guide"
        assert "语言学" in item_text(it)

    def test_seed_50_page154_quad_apostrophe(self):
        """[49] 四壳断裂+英文撇号断裂（page_154 魔鬼印记）——
        `**A****（****EN****’****s Mark****）【书】：**正文` ——撇号段不误判 elided"""
        raw = "**魔鬼印记****（****Devil****’****s Mark****）【PFS Guide】：**某个高阶魔鬼在你身上留下印记，任何邪恶的生物看到这个印记都会三思而后行。"
        items = run(raw, source_name="page_154.md")
        assert len(items) == 1, f"应产出 1 个条目，实际 {len(items)}"
        it = items[0]
        assert it["name"] == "魔鬼印记"
        assert it["name_en"] == "Devil’s Mark"  # 源数据弯引号 U+2019
        assert it["source"] == "PFS Guide"
        assert "印记" in item_text(it)

    def test_seed_51_botm_flow_multiline(self):
        """[50] 跨行流式条目（BotM 月之血脉）：中文名+换行+EN（类型）：正文，
        条目间同行句号分隔（源文件无条目间换行）——拆行后逐条产"""
        raw = (
            "背景新背景特性：月之子裔无论是出生时的意外，还是血脉中的涌动，"
            "有些人与月亮之间的联系尤为紧密。"
            "月之子裔 \nChild of the Moon(魔法)：月光给予你的能力在满月之时尤为强力。"
            "选择攀爬、潜行或游泳之一。"
            "创痛变身Traumatic \nShift：你第一次变型是在大庭广众之下。"
            "你的唬骗检定得到+1背景加值。"
        )
        items = run(raw, source_name="月之血脉BotM_背景特性.md")
        assert len(items) == 3, f"应产出 3 个条目（intro + 2 特性），实际 {len(items)}"
        assert items[0]["name"] == ""  # intro
        assert items[1]["name"] == "月之子裔"
        assert items[1]["name_en"] == "Child of the Moon"
        assert "魔法" in items[1]["trait_type"]
        assert items[2]["name"] == "创痛变身"
        assert items[2]["name_en"] == "Traumatic Shift"
        assert "唬骗" in item_text(items[2])

    def test_seed_52_kobold_dual_paren(self):
        """[51] 狗头人双括号形态（格拉里昂的狗头人）：
        `**中文（区域）（EN \n，EN）:**正文` ——中文括号=区域子类型（保留在 title），
        全角括号=EN 名跨行含中文逗号，半角冒号在闭星内——须拆为独立条目"""
        raw = (
            "**地区背景（REGIONAL \nTRAITS）**\n"
            "以下是狗头人的地区背景(以及其他通常来自被狗头人占领地区的生物)。\n\n"
            "**荆棘强盗(森林)（Briar Bandit \n，forest）:**你在荆棘和其他茂密的灌木丛中爬行与埋伏的这段时间里，教会了你如何在不干扰周围丛林的情况下移动。当你处在茂密植物（overgrown）的区域时，你在隐匿检定上获得+2背景加值，在偷袭的伤害骰上获得+1背景加值。\n\n"
            "**砾石漫步者(阴影之地，通常在温暖山脉地带)（Gravelwalker \n，Darklands, usually under warm \nmountains）:**你在穿行崩落的岩石和摸索塌陷的隧道中长大，你能够在由碎石或其他残骸造成的困难地形中确认最稳定的路径。你可以正常通过这些不平坦（obstructed）的空间，并可以通过一个成功的特技检定来进行奔跑和冲锋。"
        )
        items = run(raw, source_name="格拉里昂的狗头人_种族背景特性.md")
        # 2 条目（标题段排除）+ 可能的 intro
        traits = [it for it in items if it.get("name")]
        assert len(traits) == 2, f"应产出 2 个特性条目，实际 {len(traits)}: {[it['name'] for it in traits]}"
        it = traits[0]
        assert it["name"] == "荆棘强盗"  # 区域子类型括号丢弃（与地名括号口径一致）
        assert it["name_en"] == "Briar Bandit, forest"  # 源数据中文逗号归一为英文规范
        assert "隐匿" in item_text(it)
        assert traits[1]["name"] == "砾石漫步者"
        assert "困难地形" in item_text(traits[1])

    def test_seed_53_bota_intro_crossline(self):
        """[52] BotA 引导句跨行 + 条目神祇括号跨行（古国血脉）：
        `**引导句（The \nFlooded Cathedral）中。****条目 EN（神名 \nEN）**：正文`
        ——引导句星壳内书名括号跨行、条目 EN 名与神祇括号均跨行——须拆出 3 条"""
        raw = (
            "**以下信仰特性仅限于信奉指定阿兹兰特神祇的角色可选。这些神祇登场于冒险之路#123： 浸没大圣堂（The \n"
            "Flooded Cathedral）中。****劳有所得 Fruits of Your Labor（贾依迪 \n"
            "Jaidi）**：你以供养社群为傲。每天一次，你可以为自己和至多六名其他生物提供一顿由你生产、购买或采集的食物所组成的餐点。提供与食用该餐点需10分钟，其间其他参与者可以进行轻微活动，如交谈、阅读或警戒。餐后每个生物恢复1d3点生命值，并在下一次使用协助他人动作帮助同样食用了该餐点的生物时，在此次d20投掷中获得+1背景加值。该加值持续24小时，每个生物每天只能通过该特性获得一次此加值。**位面旅者 Planar \n"
            "Wayfarer（奥诺斯 \n"
            "Onos）**：无数位面的自然危害无法阻止你目睹其壮丽景观。每天一次，你可以花1小时冥想位面的本质，获得能量抗力2，针对酸、寒冷、电、火焰或音波伤害（选择其一）。此抗力持续24小时，或直到你再次冥想并选择新的抗力类型。**神圣向导 Sacred \n"
            "Orienteer（埃利昂 \n"
            "Elion）**：你曾在旅途中远行，仅靠指南针与信仰作为引导。你在游戏开始时获得一个指南针（compass）。你所持有的任何指南针或寻路仪也作为埃利昂的圣徽使用。你将知识（地理）或生存视为本职技能。每天一次，你可以在整轮动作中参考你的指南针或寻路仪，使你在一次知识（地理）或生存检定中获得+2背景加值。"
        )
        items = run(raw, source_name="古国血脉BotA_背景特性.md")
        traits = [it for it in items if it.get("name")]
        assert len(traits) == 3, f"应产出 3 个条目，实际 {len(traits)}: {[it['name'] for it in traits]}"
        assert traits[0]["name"] == "劳有所得"
        assert traits[0]["name_en"] == "Fruits of Your Labor"
        assert traits[0]["deity"] == "贾依迪"
        assert traits[1]["name"] == "位面旅者"
        assert traits[1]["name_en"] == "Planar Wayfarer"
        assert traits[1]["deity"] == "奥诺斯"
        assert traits[2]["name"] == "神圣向导"
        assert traits[2]["name_en"] == "Sacred Orienteer"
        assert traits[2]["deity"] == "埃利昂"
        assert "餐点" in item_text(traits[0])

    def test_seed_54_quest_star_title_crossline_source(self):
        """[53] 任务与战役形态 B：星壳标题 + 跨行出处（纵火狂）——
        `**纵火狂（Firebug）**` 换行后跟 ` 出自《任务与战役》 Quests and \nCampaigns`
        ——「出自…」行是条目的出自行（书名跨行），不得被裸行标题分支抢走切伪条目
        （产出即检发现：纵火狂/乐观心/耐心沉着 3 条 text 被吞到「出自《任务与战役》」
        伪条目下）——须并入当前条目 source 且书名两行合并完整"""
        raw = (
            "**纵火狂（Firebug）**\n"
            " 出自《任务与战役》 Quests and \n"
            "Campaigns\n"
            "**类型：**战斗背景（Combat）\n"
            "**效果：**你是一个军械师或炼金术士的子嗣，而且特别喜欢用易燃物和炸药做实验。当你使用投炸武器或者炼金炸弹攻击时，你的攻击检定获得+1背景加值"
        )
        items = run(raw, source_name="任务与战役_背景特性.md")
        traits = [it for it in items if it.get("name")]
        assert len(traits) == 1, f"应仅产出纵火狂 1 条，实际 {len(traits)}: {[it['name'] for it in traits]}"
        it = traits[0]
        assert it["name"] == "纵火狂"
        assert "军械师" in item_text(it), "效果正文应并入纵火狂（未被伪条目吞并）"
        assert "出自" not in item_text(it), "出自行不得进正文"

    def test_seed_55_half_title_crossline_book_continuation(self):
        """[54] 跨行书名补全行不污染正文（任务与战役报复心形态）：
        `**报复心**(Vengeful)` 换行后 `出自《任务与战役Quests and \nCampaigns》`
        ——书名第二行 `Campaigns》` 是出处补全行（带闭书名号），必须并入
        source 而非落入正文分支污染 text（产出即检发现 text 以 Campaigns》 开头）"""
        raw = (
            "**报复心**(Vengeful) \n"
            "出自《任务与战役Quests and \n"
            "Campaigns》\n"
            "**分类** 战斗\n"
            "**效果** \n"
            "在你幼年时代，一些你无力抵抗的家伙时不时的会虐待你。现在当有机会反击那些曾经伤害过你的人，你便会兴奋不已。"
        )
        items = run(raw, source_name="任务与战役_背景特性.md")
        traits = [it for it in items if it.get("name")]
        assert len(traits) == 1, f"应仅产出报复心 1 条，实际 {len(traits)}: {[it['name'] for it in traits]}"
        it = traits[0]
        assert it["name"] == "报复心"
        text = item_text(it)
        assert "Campaigns" not in text, f"书名补全行不得污染正文: {text[:40]!r}"
        assert "在你幼年时代" in text

    def test_seed_56_exemplar_unclosed_title_quad_field(self):
        """[56] 典范背景未闭合星壳标题 + 四星字段行（est=5 只切出 1 条的根因）：
        `**A（EN）\n****出自**：Chronicle of Legends…`——源数据转换产物：
        标题闭星壳与下一行字段开星壳在换行两侧粘连成 quad-star，闭星壳丢失，
        `_RE_TITLE_STAR` 匹配失败整条丢失（全能战斗艺术家/口蜜腹剑/无懈可击
        的信念/神秘主义机密的保管者 4 条中 3 条全灭，RED 已验证产出 0）。
        修复：标题行补 `**` 闭合，下一行 quad-star 剥前两星还原字段行"""
        raw = (
            "**全能战斗艺术家（Artist of Battle in All \n"
            "Forms）\n"
            "****出自**：Chronicle of Legends pg. \n"
            "3\n"
            "**类别**：典范（Exemplar）\n"
            "**典范类型**：战斗典范\n"
            "你可以轻松地运用复杂的作战战术。选择一种战技（Combat \n"
            "Maneuver）。执行该战技的战技检定你获得+1背景加值。\n"
            "\n"
            "**口蜜腹剑（Charming Smile, Cunning \n"
            "Soul）\n"
            "****出自**：Chronicle of Legends pg. \n"
            "3\n"
            "**类别**：典范（Exemplar）\n"
            "**典范类型**：社会典范\n"
            "你知道如何狡诈地编织文字，动摇人心和思考能力。\n"
        )
        items = run(raw, source_name="典范背景.md")
        traits = [it for it in items if it.get("name")]
        assert len(traits) == 2, f"应产出 2 条典范背景，实际 {len(traits)}: {[it['name'] for it in traits]}"
        names = [it["name"] for it in traits]
        assert "全能战斗艺术家" in names and "口蜜腹剑" in names, f"条目名错误: {names}"
        for it in traits:
            assert it.get("name_en"), f"{it['name']} 英文名缺失"
            text = item_text(it)
            assert "****" not in text, f"{it['name']} 正文含 quad-star 残留: {text[:30]!r}"
        art = next(it for it in traits if it["name"] == "全能战斗艺术家")
        assert "复杂" in item_text(art) or "战技检定" in item_text(art), "全能战斗艺术家正文不完整"
        assert "****" not in (art.get("name_en") or ""), "英文名含星壳残留"

    # ---------- 2026-08-06 任务2：ABC 类文件补 trait_type（章节标记行段落级） ----------

    def test_seed_57_teog_section_marker_paren_glue(self):
        """[57] TEoG 无星壳裸标题 + 裸文本章节标记行（est=21 got=8 缺口根因）：
        跨行括号条目 `调和者（莎伦莱） Ambassador \n(Sarenrae)正文`（中文名
        （神）+ 空格 + 英文名 + 换行 + (英文)正文粘连）——_RE_TEOG_GLUE 组1
        排除括号匹配失败，宗教/种族段 14 条全灭。章节行 `地区背景（塔尔多）
        …`/`宗教背景…`/`种族背景…` 是裸文本分类标记行 → 段落级 trait_type。"""
        raw = (
            "地区背景（塔尔多）这些背景可以被所有塔尔多本地人选取。\n\n"
            "骑士精神 \n"
            "Chivalrous你的成长伴随着英武骑士和慈爱法师的传奇故事。你在交涉和知识（地方）检定上获得+1背景加值。\n\n"
            "宗教背景这些宗教背景可以被所有属于下列宗教的角色选取。\n\n"
            "调和者（莎伦莱） Ambassador \n"
            "(Sarenrae)你在调解和妥协方面的天赋在很小的时候就展现了出来。你在交涉检定上获得+2的背景加值。\n\n"
            "种族背景这些种族背景可以被所有拥有合适种族的角色选取。\n\n"
            "诗人梦（人类——塔尔多人） Aspiring Bard \n"
            "(Human—Taldan)你在吉萨洛丹学院和狂想曲学院的开放校园里漫步了不知道多少次。你在一种表演检定上获得+1的背景加值。\n"
        )
        items = run(raw, source_name="塔尔多TEoG_背景特性.md")
        traits = [it for it in items if it.get("name")]
        assert len(traits) == 3, f"应产出 3 条，实际 {len(traits)}: {[it['name'] for it in traits]}"
        chivalrous = next(it for it in traits if it["name"] == "骑士精神")
        assert chivalrous["_trait_type_from_marker"] == "地区背景", chivalrous
        mediator = next(it for it in traits if it["name"] == "调和者")
        assert mediator["name_en"] == "Ambassador", mediator
        assert mediator["deity"] == "莎伦莱", mediator
        assert mediator["_trait_type_from_marker"] == "宗教背景", mediator
        poet = next(it for it in traits if it["name"] == "诗人梦")
        assert poet["name_en"] == "Aspiring Bard", poet
        assert poet["_trait_type_from_marker"] == "种族背景", poet
        assert not poet.get("deity"), "人类——塔尔多人是种族细分非神祇，不得填 deity"

    def test_seed_58_elf_cn_star_en_section_marker(self):
        """[58] 精灵中文名+星壳英文+双语章节标记行（est=13 got=8 缺口根因）：
        `神奇把戏**Arcane \nDabbler**：正文`（中文名直接粘连 `**英文**`，无
        前导星壳）——_RE_TITLE_STAR 需 `**` 开头匹配失败，种族段 4 条全被
        intro 吞并。章节行 `Racial Traits`/`种族背景`（裸文本中英双语）→
        段落级 trait_type（英文映射：Racial→种族、Regional→地区）。"""
        raw = (
            "Racial Traits \n"
            "种族背景\n"
            "神奇把戏**Arcane \n"
            "Dabbler**：尽管你学习魔法已经过去了数十年之久，你依旧无法忘记你最喜欢的小戏法。\n\n"
            "遗失的信仰**Lapsed \n"
            "Faith**：你还依稀记得些许你在神殿侍奉神明时做出的祷告。你获得每天可以释放一次治疗微伤的类法术能力。\n\n"
            "Sovyrian的泛神论**Sovyrian \n"
            "Pantheist**（全部精灵神）：由于深受其他精灵的神秘王国的影响，所有格拉里昂的精灵神都对你有着一定的影响力。\n\n"
            "Regional Traits \n"
            "地区背景\n"
            "孤独者**Forlorn**（任何无精灵之地）：你在远离传统的精灵社会居住了漫长的岁月。你的强韧豁免获得+1背景加值。\n"
        )
        items = run(raw, source_name="格拉里昂的精灵_种族背景特性.md")
        traits = [it for it in items if it.get("name")]
        assert len(traits) == 4, f"应产出 4 条，实际 {len(traits)}: {[it['name'] for it in traits]}"
        trick = next(it for it in traits if it["name"] == "神奇把戏")
        assert trick["name_en"] == "Arcane Dabbler", trick
        assert trick["_trait_type_from_marker"] == "种族背景", trick
        assert not trick.get("deity"), "神奇把戏无神祇括号"
        pantheist = next(it for it in traits if it["name"] == "Sovyrian的泛神论")
        assert pantheist["name_en"] == "Sovyrian Pantheist", pantheist
        assert pantheist["_trait_type_from_marker"] == "种族背景", pantheist
        # 括号纯中文 → deity（ISG 同口径：神名/神名集合如「全部精灵神」）
        assert pantheist["deity"] == "全部精灵神", pantheist
        loner = next(it for it in traits if it["name"] == "孤独者")
        assert loner["name_en"] == "Forlorn", loner
        assert loner["_trait_type_from_marker"] == "地区背景", loner
        # 「任何无精灵之地」地名被 _RE_FLOW 括号语义误填 deity——既有行为
        #（page_156 同形态同误填，KN 登记不扩大），断言对齐现状
        assert loner["deity"] == "任何无精灵之地", loner

    def test_seed_59_dwarf_section_marker_multi_form(self):
        """[59] 矮人星壳章节标记行 + 半星壳/无星跨行条目（est=24 got=18 缺口
        根因）：`**矮人的地区背景`（星壳无闭行）、`**魔法背景：`（星壳+冒号）
        为章节标记行 → 段落级 trait_type；`**浴血者Blooded\n(Mindspin
        Mountains)：正文`（半星壳无闭星跨行）与 `霜血Frostborn\n(Lands of
        the Linnorm Kings)：正文`（无星跨行）条目切不出。"""
        raw = (
            "**矮人的地区背景\n"
            "**浴血者Blooded\n"
            "(Mindspin Mountains)：令人绝望的战斗磨练了你针对那些矮人远古宿敌的战斗技巧。\n\n"
            "霜血Frostborn\n"
            "(Lands of the Linnorm Kings)：北地寒冬的漫漫长夜让你习惯了寒冷。\n\n"
            "**魔法背景：\n"
            "紧贴大地**Earthbound**：你的德鲁伊在施放法术时可以用少量的泥土或沙子当做他们的法器。\n"
        )
        items = run(raw, source_name="格拉里昂的矮人_种族背景特性.md")
        traits = [it for it in items if it.get("name")]
        assert len(traits) == 3, f"应产出 3 条，实际 {len(traits)}: {[it['name'] for it in traits]}"
        bather = next(it for it in traits if it["name"] == "浴血者")
        assert bather["name_en"] == "Blooded", bather
        assert bather["_trait_type_from_marker"] == "地区背景", bather
        frost = next(it for it in traits if it["name"] == "霜血")
        assert frost["name_en"] == "Frostborn", frost
        assert frost["_trait_type_from_marker"] == "地区背景", frost
        earth = next(it for it in traits if it["name"] == "紧贴大地")
        assert earth["name_en"] == "Earthbound", earth
        assert earth["_trait_type_from_marker"] == "魔法背景", earth

    def test_seed_60_cosmic17_hh_segment_marker(self):
        """[60] 背景特性17 HH 段哨兵识别（方案 R3-B）：`<!-- HH-source:` 注释
        行 → 段内条目打 _hh_section 戳（processor 层 R2 整页默认跳过，防误伤）；
        哨兵同时重置 section_type（HH 段独立区域，不继承原内容段标记）；
        段内裸文本标记行（`信念背景`）继续段落级 marker 继承。"""
        raw = (
            "**篷车星系（Carvanserai）：**占星术工具。\n\n"
            "<!-- HH-source:page_703.md:血腥复仇 -->\n"
            "**血腥复仇（Bloody Revenge）：**正文1。\n\n"
            "信念背景\n"
            "<!-- HH-source:page_703.md:灵魂搜寻者之力 -->\n"
            "**灵魂搜寻者之力（Soulseeker's Power）：**正文2。\n"
        )
        items = run(raw, source_name="背景特性17.md")
        caravan, revenge, soulseeker = items[0], items[1], items[2]
        # 原内容段条目：无 HH 戳、无 marker
        assert "_hh_section" not in caravan, caravan
        assert "_trait_type_from_marker" not in caravan, caravan
        # HH 段首条目（标记行之前）：HH 戳有、marker 重置为空
        assert revenge["_hh_section"] is True, revenge
        assert "_trait_type_from_marker" not in revenge, revenge
        # HH 段标记行后条目：HH 戳有、marker=信念背景
        assert soulseeker["_hh_section"] is True, soulseeker
        assert soulseeker["_trait_type_from_marker"] == "信念背景", soulseeker

    # ---------- 2026-08-06 任务4 排查：空 text 条目家族（P1） ----------

    def test_seed_61_page151_quad_star_book_glue_text(self):
        """[61] page_151 四重星壳+【书缩写】断裂（神圣密探，空 text P1）：
        源形态 `**中文****（EN）【****书****】**：正文` 归一后残留
        `**中文**（EN）【**书****】**：正文`（闭合星壳中文 + 星壳外括号 +
        【】内残星）——标题判定失败，半星壳分支丢同行正文。应归一为
        `**中文（EN）【书】**：正文` 单星壳，_RE_TITLE_STAR 组6 接正文。"""
        raw = (
            "**神圣密探****（Divine Confidante）【****SH****】**：当他人与你谈论"
            "有关信仰，神话，道德，宗教和外位面的话题时，你在察言观色检定上"
            "得到+3背景加值。\n"
        )
        items = run(raw, source_name="page_151.md")
        traits = [it for it in items if it.get("name")]
        assert len(traits) == 1, f"应产出 1 条，实际 {len(traits)}: {traits}"
        it = traits[0]
        assert it["name"] == "神圣密探", it
        assert it["name_en"] == "Divine Confidante", it
        assert item_text(it).startswith("当他人与你谈论有关信仰"), it
        assert "察言观色检定上得到+3背景加值" in item_text(it), it

    def test_seed_62_page1579_half_star_paren_colon_text(self):
        """[62] page_1579 半星壳+星壳外括号+冒号正文（信手拈来/千杯不醉，
        空 text P1）：`**中文**(EN)：正文`——括号在星壳外，_RE_TITLE_HALF
        半星壳分支只接「出处同行」无正文捕获 → text 空。应归一为
        `**中文（EN）**：正文` 单星壳，_RE_TITLE_STAR 组6 接正文。"""
        raw = (
            "**信手拈来**(Improvisational Equipment)：你有一种不可思议的本领，"
            "能发挥出装备意想不到的新用途。当将物品用于其他用途时，例如将撬棍"
            "用作抓钩或将旧衬衫用于包扎致命伤口，减少2点使用临时工具的罚值。\n\n"
            "**千杯不醉**(Iron Liver)：由于幸运的体质或频繁接触，你的身体对"
            "包括酒精和毒品在内的毒素有抵抗力。你在对抗毒素和毒品的强韧豁免"
            "上获得+2背景加值。\n"
        )
        items = run(raw, source_name="page_1579.md")
        traits = [it for it in items if it.get("name")]
        assert len(traits) == 2, f"应产出 2 条，实际 {len(traits)}: {traits}"
        improv = next(it for it in traits if it["name"] == "信手拈来")
        assert improv["name_en"] == "Improvisational Equipment", improv
        assert "临时工具的罚值" in item_text(improv), improv
        assert improv["format_cluster"] != "B1_star_field", improv
        liver = next(it for it in traits if it["name"] == "千杯不醉")
        assert liver["name_en"] == "Iron Liver", liver
        assert "强韧豁免上获得+2背景加值" in item_text(liver), liver

    def test_seed_63_source_line_not_bare_title(self):
        """[63] 出处行误判伪条目（初探探索者协会/初探内海ISP/繁星子民 3 文件，
        空 text + 伪条目 P1）：`出自《中文书名》English Book: …` 被
        _RE_BARE_CN_EN_COLON 当「裸行中文名+英文名+冒号正文」补星壳 → 伪条目
        「初探探索者协会》」+ 真条目 source 残缺（《）。出处行应以「出自」
        前缀识别排除，不产条目；真条目字段行正常并入。"""
        raw = (
            "**协会的肌肉训练（muscle of the society）**\n"
            "出自《初探探索者协会》Pathfinder Player Companion: Pathfinder "
            "Society Primer\n"
            "**类型：**战斗背景（combat）\n"
            "**效果：**协会的力量训练使你能够进入平时无法接近的遗迹并拿出"
            "更多的战利品。你在用于破门和提起重物的力量鉴定上获得+2背景加值。\n"
        )
        items = run(raw, source_name="初探探索者协会_背景特性.md")
        traits = [it for it in items if it.get("name")]
        assert len(traits) == 1, f"应产出 1 条（无伪条目），实际 {len(traits)}: "
        f"{[it['name'] for it in traits]}"
        it = traits[0]
        assert it["name"] == "协会的肌肉训练", it
        assert it["name_en"] == "muscle of the society", it
        assert "力量鉴定上获得+2背景加值" in item_text(it), it
        # 出处行不污染 source（残缺《）也不产伪条目
        assert it["source"] != "《", it
        assert "初探探索者协会》" not in [t["name"] for t in traits]

    def test_seed_64_page156_hog_paren_star_break(self):
        """[64] page_156 切分缺口 8（est 35 got 27，KN138 家族 P1）：
        HoG 段 7 条 `**好养活（Cheap to Feed****，****奥斯里昂，瓦瑞希安）【HoG】**：`
        ——EN 星壳与中文地点星壳间 `****，****` 残壳使 _RE_TITLE_STAR 组3
        （排除 `*`）失配整条目丢失；猎魔人 1 条 `**…****【CEoD】******` 六星
        尾 normalize 后残尾单星 `**【CEoD】*` 闭星失配。剥星归一 → 全条目切出。"""
        raw = (
            "**好养活（Cheap to Feed****，****奥斯里昂，瓦瑞希安）【HoG】**："
            "Life in a big city taught the consequences of pride. 你为了获取"
            "食物，水或庇护的唬骗检定获得+3背景加值。你必须是半身人才能选择"
            "此背景\n\n"
            "**猎魔人（Hunter of Outsiders，切利亚斯）****【CEoD】******\n\n"
            "你的生活让你对于打击外位面的邪魔有所准备。\n"
            "效果：你在用于追踪邪恶异界生物的求生检定中获得+2背景加值。\n"
        )
        items = run(raw, source_name="page_156.md")
        names = [it["name"] for it in items if it.get("name")]
        assert names == ["好养活", "猎魔人"], names
        it = items[0]
        # aliases 含「EN，中文地点」为既有行为（沙之子 Desert Child，沙漠 同型），
        # 括号整体进 name_en 不剥中文
        assert it["name_en"] == "Cheap to Feed，奥斯里昂，瓦瑞希安", it
        assert "唬骗检定获得+3背景加值" in item_text(it), it
        assert "半身人才能选择" in item_text(it), it
        it2 = items[1]
        assert it2["name_en"] == "Hunter of Outsiders，切利亚斯", it2
        assert "求生检定中获得+2背景加值" in item_text(it2), it2

    def test_seed_65_page152_korada_unclosed_tail(self):
        """[65] page_152 切分缺口（est 61 got 59，KN138 家族 P1）：
        `**孔冉达的变形师（****Transmuter of Korada）【CoP】****` 标题尾
        4 星无闭星 + 正文独立行 `**` 开头（源 `**正文`）——四星归一后
        `）【CoP】**` 壳内形态缺闭星，_RE_TITLE_STAR 组5 后 `\*\*` 失配
        整条目丢失。补闭星 → 标准标题。"""
        raw = (
            "**孔冉达的变形师（****Transmuter of Korada）【CoP】****\n"
            "**你师从至高天神使孔冉达的信徒学习变形术的奥秘。当你施展变化系"
            "法术时施法等级+1。只有善良阵营才能此背景\n"
        )
        items = run(raw, source_name="page_152.md")
        names = [it["name"] for it in items if it.get("name")]
        assert names == ["孔冉达的变形师"], names
        it = items[0]
        assert it["name_en"] == "Transmuter of Korada", it
        assert "施法等级+1" in item_text(it), it
        assert "只有善良阵营才能此背景" in item_text(it), it

    def test_seed_66_page153_sh_no_open_star(self):
        """[66] page_153 切分缺口 4（est 55 got 51，KN138 家族 P1）：
        SH 段 4 条 `罪犯之子****（Criminal Roots）【SH】**：正文` ——行首
        无开星壳（源转换产物），_RE_TITLE_STAR 组1 `\*\*` 失配整条目
        丢失。补开星 → 标准标题。"""
        raw = (
            "罪犯之子****（Criminal Roots）【SH】**：你在与罪犯的交涉检定中"
            "得到+2背景加值，但在对守法公民的交涉检定中受到-2罚值。交涉或"
            "威吓（由你选择）成为你的本职技能。**\n"
            "深藏不露****（Deep Cover）【SH****】**：你总能在伪装和维持一个"
            "假身份的唬骗和易容检定上取10。唬骗或易容（由你选择）成为你的"
            "本职技能。  \n**\n"
            "上头有人****（Official Ties）【SH****】**：你与一位或多位权威"
            "人士维持着朋（P）友（Y）关系。你可以一定程度上左右他或他们的"
            "意见。**\n"
        )
        items = run(raw, source_name="page_153.md")
        names = [it["name"] for it in items if it.get("name")]
        assert names == ["罪犯之子", "深藏不露", "上头有人"], names
        it = items[0]
        assert it["name_en"] == "Criminal Roots", it
        assert "得到+2背景加值" in item_text(it), it
        it2 = items[1]
        assert it2["name_en"] == "Deep Cover", it2
        assert "取10" in item_text(it2), it2

    def test_seed_67_page155_cn_name_star_break(self):
        """[67] page_155 切分缺口 2（est 33 got 31，KN138 家族 P1）：
        `**魔****染裔（Infernal Influence）【CEoD】**` 中文名中 4 星断裂 +
        `**主宰范****（Masterful Demeanor）【CEoD】**` 双星壳连写——四星
        归一只处理 `****内容****` 完整包裹，此形态尾部 2 星闭星不匹配，
        _RE_TITLE_STAR 组3 前夹星失配整条目丢失。剥中间星 → 标准标题。"""
        raw = (
            "**魔****染裔（Infernal Influence）【CEoD】**你的家族与邪魔之间"
            "有着秘密的错综复杂的关系。\n"
            "效果：你获得+1的火焰抗力，并且在所有对毒药的强韧检定都获得"
            "+1背景加值。\n"
            "**主宰范****（Masterful Demeanor）【CEoD】**身为一个自豪的主宰"
            "者，你自觉其他的劣等种族之人都会服从于你。\n"
            "需求：切利亚斯人\n"
        )
        items = run(raw, source_name="page_155.md")
        names = [it["name"] for it in items if it.get("name")]
        assert names == ["魔染裔", "主宰范"], names
        it = items[0]
        assert it["name_en"] == "Infernal Influence", it
        assert "+1的火焰抗力" in item_text(it), it
        it2 = items[1]
        assert it2["name_en"] == "Masterful Demeanor", it2
        # 「需求：切利亚斯人」为字段行，解析入 requirement 字段而非正文
        assert it2["requirement"] == "切利亚斯人", it2

    def test_seed_68_page157_haoyinke_quad_paren(self):
        """[68] page_157 切分缺口（est 29 got 28，KN138 家族 P1）：
        `**豪饮客（****Fortified \\nDrinker****，混乱善良）【APG】**
        （**凯登****·****凯连，****Cayden \\nCailean****）**：` ——四壳
        括号 + 跨行英文 + 星壳神祇括号 + `·` 点号，多形态叠加归一后
        标题闭星失配整条目丢失。剥星归一 → 标准标题。"""
        raw = (
            "**豪饮客（****Fortified \nDrinker****，混乱善良）【APG】**"
            "（**凯登****·****凯连，****Cayden \nCailean****）**："
            "凯登·凯连在你的心神中亦灌注了佳酿，令你不易为精神攻击所动。"
            "在你饮酒之后的1小时内，你在对抗影响心智的效果的豁免中获得"
            "+2背景加值。\n"
        )
        items = run(raw, source_name="page_157.md")
        names = [it["name"] for it in items if it.get("name")]
        assert names == ["豪饮客"], names
        it = items[0]
        # 阵营尾缀剥离（与圣娼姬 seed_31 同构：`EN，混乱善良` → EN）
        assert it["name_en"] == "Fortified Drinker", it
        assert "+2背景加值" in item_text(it), it

    def test_seed_69_page150_jianhao_zhishu_strike_shell(self):
        """[69] page_150 剑豪之眼漏切（est 62 got 61，KN138 家族 P1）：
        `**~~剑豪之眼~~****~~（Aldori Caution）~~****~~【WMH】~~****~~：~~**~~`——
        删除线壳在外、星壳在内的 HTML `<B><S>` 嵌套残留，剥壳后应为标准
        标题（与护枪匠同族，护枪匠已切出）。源数据修复后 normalize 直通。"""
        raw = (
            "**剑豪之眼（Aldori Caution）【WMH】**：你在奥多里剑豪的指导下"
            "练习如何用剑刃防御敌人的打击。在进行防御式战斗或是全防御动作"
            "时，你在防御等级上获得+1额外的闪避加值。\n"
        )
        items = run(raw, source_name="page_150.md")
        names = [it["name"] for it in items if it.get("name")]
        assert names == ["剑豪之眼"], names
        it = items[0]
        assert it["name_en"] == "Aldori Caution", it
        assert "+1额外的闪避加值" in item_text(it), it

    def test_seed_70_page150_translator_riff_not_entry(self):
        """[70] page_150 译者吐槽已源数据删除（KN091 专长先例同族）：
        「艹，人家blade of mercy…」为无星壳独立行，split 裸名分支会把它
        切成伪条目（format 层兜底行为，登记 KN——不因单行改 split 全库
        裸名切分）。fix_trait_base_page_residue.py 已删除该行，本测试验证
        修复后的形态只产出和平武器，无吐槽伪条目。"""
        raw = (
            "**和平武器（Weapon of peace）【CoP】**：虽然你是训练有素的战士，"
            "擅长各类武器，你并不从杀人中感到欢欣。只有守序善良阵营才能此"
            "背景\n"
        )
        items = run(raw, source_name="page_150.md")
        names = [it["name"] for it in items if it.get("name")]
        assert names == ["和平武器"], names
        assert all("人家blade" not in item_text(it) for it in items), items

    def test_seed_71_page152_yinxiujiang_fragment_shell(self):
        """[71] page_152 隐修匠漏切（est 61 got 59，KN138 家族 P1）：
        `~~　　~~**~~隐~~****~~修~~****~~匠（~~****~~Hedge Magician~~…`
        中文名三字星壳碎片 + 删除线壳嵌套，HTML `<B><S>` 转换残留。
        源数据修复为标准标题后 normalize 直通。"""
        raw = (
            "**隐修匠（Hedge Magician）【APG】**：你在一段时期内做过某位魔法"
            "物品工匠的学徒，他教会了你许多节约工序和成本的窍门。当你制造"
            "魔法物品时，降低5%的GP成本消耗。\n"
        )
        items = run(raw, source_name="page_152.md")
        names = [it["name"] for it in items if it.get("name")]
        assert names == ["隐修匠"], names
        it = items[0]
        assert it["name_en"] == "Hedge Magician", it
        assert "5%的GP成本消耗" in item_text(it), it

    def test_seed_72_page152_korada_lead_star_leak(self):
        """[72] page_152 孔冉达的变形师漏切（est trap「正文行首星壳泄漏」）：
        `**孔冉达的变形师（****Transmuter of Korada）【CoP】****\n**你师从…`
        标题壳尾 4 星 + 正文行首 `**` 泄漏。源数据修复后 normalize 直通，
        正文行首无星壳。"""
        raw = (
            "**孔冉达的变形师（Transmuter of Korada）【CoP】**\n"
            "你师从至高天神使孔冉达的信徒学习变形术的奥秘。当你施展变化系"
            "法术时施法等级+1.只有善良阵营才能此背景\n"
        )
        items = run(raw, source_name="page_152.md")
        names = [it["name"] for it in items if it.get("name")]
        assert names == ["孔冉达的变形师"], names
        it = items[0]
        assert it["name_en"] == "Transmuter of Korada", it
        assert "师从至高天神使孔冉达" in item_text(it), it

    def test_seed_73_page152_quad_star_book_glue(self):
        """[73] page_152 四壳变体【书缩写】拆行脱节（APG 9 条 + PSP 2 条 +
        护枪匠 UCa，book '?' 12 条）：
        `**法理通（****Magical Knack****）****【APG】**：正文` —— 公共层
        _RE_BOLD_GLUE_SPLIT（KN070）把 `）****【` 4 星粘连拆行 → 【APG】
        落行首星壳，split 标题分支失配 source 空 → book 未知。链尾粘回
        行首 `**【X】**：` 形态（组5 捕获回 tag_src）。"""
        raw = (
            "**法理通（****Magical Knack****）****【APG】**：你的全部或部分"
            "童年，是由某位魔法生物陪伴成长。你施展法术时，施法者等级+1。\n"
        )
        items = run(raw, source_name="page_152.md")
        names = [it["name"] for it in items if it.get("name")]
        assert names == ["法理通"], names
        it = items[0]
        assert it["name_en"] == "Magical Knack", it
        assert it.get("source") == "APG", it
        assert "施法者等级+1" in item_text(it), it

    def test_seed_74_page151_en_only_title(self):
        """[74] page_151 纯英文名标题（无中文名）两形态——est 预测「解析器需
        兜底」（est 漏数 Kalistocratic Prophecy——误认为隐密信仰英文原文段）：
        1. 双星壳 `**（Persuasive Insight）【****SH****】**：正文`（四星归一
           后 `【**SH**】` 前后星残留）——_RE_TITLE_STAR 组1 要求非括号字符
           开头失配 → 落入正文分支被前条（隐密信仰）吞并
        2. 删除线壳剥除后无开星 `（Kalistocratic Prophecy）【~~****~~SH~~****~~】~~**~~：`
        → 均产出独立条目 name=EN（无中文名）、source=SH。"""
        raw = (
            "**（Persuasive Insight）【****SH****】**：你可以用感知调整值取代"
            "魅力调整值加在ask favors或gain influence（UI102页）.\n"
            "（Kalistocratic Prophecy）【~~****~~SH~~****~~】~~**~~：You were raised "
            "under the Prophecies of Kalistrade.\n"
        )
        items = run(raw, source_name="page_151.md")
        names = [it["name"] for it in items if it.get("name")]
        assert names == ["Persuasive Insight", "Kalistocratic Prophecy"], items
        p, k = items
        assert p["source"] == "SH" and k["source"] == "SH", (p, k)
        assert "你可以用感知调整值" in item_text(p), p
        assert "You were raised" in item_text(k), k
