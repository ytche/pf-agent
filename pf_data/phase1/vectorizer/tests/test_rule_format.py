"""
test_rule_format.py — 规则格式切分 TDD 测试（S1~S5 形态）

数据源：B2~B4 核心规则源数据真实形态（2026-08-09 勘察）：
  S1 heading 树（战斗规则 9 rpages + page_235/236/313/408）
  S2 行首加粗标题（环境 7 页 + page_127）
  S3 BBS 星壳嵌套（page_239/240/242/243/413）
  S5 prose（page_130）

断言口径：RuleFormat.normalize → promote → split_into_items 产出的 item dict：
  title（节标题，无星壳残迹）/ text（标题行 + 节正文，含表格行）/
  type（section）/ format_cluster（S1~S5 推导）

章节型形态（M2 §一）：无字段体系，内嵌词条块字段行（`**标签**：值`）留在
text 原文不提取（KN102 字段行伪条目教训：字段行不独立成节，并入所属节）；
`l  ` 残渣行剥除且下一标题行并入所属节（page_239 移动方式子条目）。
"""

from vectorizer.formats.rule import RuleFormat


def run(raw: str, source_name: str = "seed",
        format_cluster_hint: str = None, s6_shape: str = None) -> list:
    """RuleFormat 全链：normalize → promote → split"""
    fmt = RuleFormat()
    text = fmt.normalize(raw)
    text = fmt.promote(text)
    return fmt.split_into_items(text, source_name=source_name,
                                format_cluster_hint=format_cluster_hint,
                                s6_shape=s6_shape)


def titles(items: list) -> list:
    return [it["title"] for it in items]


# ============================================================
#  S1 heading 树（B2 战斗规则形态）
# ============================================================


class TestS1HeadingTree:
    """`####`/`#####`/`######` 标题 = 节边界，标题即 chunk title"""

    def test_h4_single_section(self):
        """H4 标题 + 正文 → 1 section"""
        raw = ("#### 如何进行战斗（How Combat Works）\n\n"
               "在游戏中进行的战斗是循环回合制的。")
        items = run(raw)
        assert len(items) == 1
        assert items[0]["title"] == "如何进行战斗（How Combat Works）"
        assert items[0]["type"] == "section"
        assert "循环回合制" in items[0]["text"]

    def test_h4_h5_h6_multi_level(self):
        """H4 + H5 + H6 多级 → 每级 1 section（est 口径全层级计数）"""
        raw = (
            "#### 主节\n\n正文甲\n\n"
            "##### 子节\n\n正文乙\n\n"
            "###### 孙节\n\n正文丙"
        )
        items = run(raw)
        assert [it["title"] for it in items] == ["主节", "子节", "孙节"]
        # 每节 text 含标题行（检索上下文）
        assert "主节" in items[0]["text"] and "正文甲" in items[0]["text"]
        assert "子节" in items[1]["text"]

    def test_cross_line_en_title(self):
        """跨行英文标题 `The Combat\\nRound` → 行拼接（KN150 教训）"""
        raw = "##### 战斗轮（The Combat\nRound）\n\n正文"
        items = run(raw)
        assert items[0]["title"] == "战斗轮（The Combat Round）"

    def test_table_follows_section(self):
        """节内表格行跟随所属节（不独立成 chunk）"""
        raw = ("#### 主节\n\n正文\n\n"
               "| 表头 |\n"
               "| --- |\n"
               "| 值1 |")
        items = run(raw)
        assert len(items) == 1
        assert "| 值1 |" in items[0]["text"]

    def test_format_cluster_heading_tree(self):
        """有 H 标题（含混合加粗）→ s1_heading_tree（page_313/408 先例）"""
        raw = ("### 大节\n\n正文\n\n"
               "**加粗子节**：子节正文")
        items = run(raw)
        assert items[0]["format_cluster"] == "s1_heading_tree"


# ============================================================
#  S2 行首加粗标题（B3 环境页形态）
# ============================================================


class TestS2BoldTitle:
    """行首 `**中文（English）**` 加粗标题 = 节边界"""

    def test_halfwidth_paren_title(self):
        """半角括号 `**地下城 (Dungeons)**` → title 保留原文"""
        raw = "**地下城 (Dungeons)**\n\n在冒险者们可能探索到的各种区域中。"
        items = run(raw)
        assert len(items) == 1
        assert items[0]["title"] == "地下城 (Dungeons)"
        assert items[0]["format_cluster"] == "s2_bold_title"

    def test_colon_after_shell(self):
        """`**废弃的建筑 (Ruined Structure)**: ` 冒号在壳外 → title 剥尾冒号，
        同行正文保留在 text"""
        raw = ("**废弃的建筑 (Ruined Structure)**: \n"
               "被建造者废弃的建筑会被其他生物占据。")
        items = run(raw)
        assert len(items) == 1
        assert items[0]["title"] == "废弃的建筑 (Ruined Structure)"
        assert "被建造者废弃的建筑" in items[0]["text"]

    def test_pure_cn_label_title(self):
        """纯中文标签 + 全角冒号 + 正文（`**低可见度**：`）→ 标题
        （标签 ∉ 字段词表；苦难字段行 `**名称**：` 是词表内 → 并入节）"""
        raw = "**低可见度**：角色在最多只能看到60尺远的距离时很可能搞不清方向。"
        items = run(raw)
        assert len(items) == 1
        assert items[0]["title"] == "低可见度"

    def test_bbs_url_and_editor_note(self):
        """页首 URL 行剥除，编者说明行并入首节"""
        raw = ("[http://45.79.87.129/bbs/index.php?topic=69666]"
               "(http://45.79.87.129/bbs/index.php?topic=69666)\n\n"
               "环境章节的编者皆为Falengel。\n\n"
               "**地下城 (Dungeons)**\n\n正文")
        items = run(raw)
        assert len(items) == 1
        assert items[0]["title"] == "地下城 (Dungeons)"
        # 编者说明并入首节 text
        assert "编者皆为Falengel" in items[0]["text"]
        # URL 行已剥除
        assert "topic=69666" not in items[0]["text"]

    def test_star_wrapped_url_line(self):
        """星壳包裹 URL 行 `**[URL](URL)**` 剥除（page_413 形态）"""
        raw = ("**[http://45.79.87.129/bbs/?topic=66158.0]"
               "(http://45.79.87.129/bbs/?topic=66158.0)**\n\n"
               "**正文节**：内容")
        items = run(raw)
        assert len(items) == 1
        assert "topic=66158" not in items[0]["text"]


# ============================================================
#  S3 BBS 星壳嵌套（B4 page_239/240/413 形态）
# ============================================================


class TestS3BbsStar:
    """`**中文（****EN****）**` 嵌套星壳标题 = 节边界"""

    def test_nested_star_title(self):
        """`**战术移动（****Tactical Movement****）**：` → title 剥壳"""
        raw = ("**战术移动（****Tactical \n"
               "Movement****）**：战斗时使用，以1轮为单位时间。")
        items = run(raw)
        assert len(items) == 1
        assert items[0]["title"] == "战术移动（Tactical Movement）"
        # KN212（2026-08-09）：normalize 剥 4+ 星碎片后嵌套 4 星特征消失，
        # 兜底推导退化 s2_bold_title——S3/S2 只影响 split 层兜底元数据，
        # 产物 format_cluster 由 processor 以 manifest hint 显式注解
        #（S3 文件 hint 全量登记，不参与 component_type 分派，零产物影响）
        assert items[0]["format_cluster"] == "s2_bold_title"

    def test_l_prefix_joins_parent(self):
        """`l  ` 残渣行 + 下一行标题 → 标题并入所属节（page_239 移动方式
        子条目；l 行剥除、标题行不独立成节）"""
        raw = ("**移动（****Movement****）**\n\n"
               "移动速度因负载与防具而异。\n\n"
               "l  \n"
               "**战术移动（****Tactical Movement****）**：战斗时使用。\n\n"
               "l  \n"
               "**区域移动（****Local Movement****）**：探索区域时使用。\n\n"
               "**受阻移动（****Hampered Movement****）**\n\n"
               "受阻移动正文。")
        items = run(raw)
        # 移动（父节）+ 受阻移动（独立）= 2 节；2 个 l 组并入父节
        assert titles(items) == ["移动（Movement）", "受阻移动（Hampered Movement）"]
        parent = items[0]["text"]
        # l 残渣剥除、子条目内容（原始行含星壳）并入父节 text
        assert "l  " not in parent
        assert "战斗时使用" in parent
        assert "探索区域时使用" in parent

    def test_affliction_field_line_joins(self):
        """苦难字段行 `**名称**：值`（标签 ∈ 词表）并入所属节（KN102）"""
        raw = ("**苦难（****Afflictions****）**\n\n"
               "苦难导言。\n\n"
               "**名称**：该苦难的名称。\n\n"
               "**豁免**：这里给出了避免该苦难侵害的豁免类型。\n\n"
               "**其他节**：独立正文")
        items = run(raw)
        assert titles(items) == ["苦难（Afflictions）", "其他节"]
        aff = items[0]["text"]
        assert "该苦难的名称" in aff
        assert "豁免类型" in aff

    def test_six_star_tail_shell(self):
        """尾 6 星壳 `**苦难（****Afflictions****，又译痛苦）******` → title 剥净"""
        raw = "**苦难（****Afflictions****，又译痛苦）******\n\n正文"
        items = run(raw)
        assert items[0]["title"] == "苦难（Afflictions，又译痛苦）"

    def test_translator_multi_segment_line(self):
        """多段星壳译者行 `**译者：****Falengel****，****pandora******` 剥除"""
        raw = ("**译者：****Falengel****，****pandora******\n\n"
               "**节标题**\n\n正文")
        items = run(raw)
        assert len(items) == 1
        assert "Falengel" not in items[0]["text"]


# ============================================================
#  S5 prose（page_130 形态）
# ============================================================


class TestS5Prose:
    """无结构散文：整篇 1 chunk（M3 唯一 S5 = page_130 游戏范例）"""

    def test_prose_single_section(self):
        """`### 标题` + `### [URL](URL) 译者:X`（带 ### 前缀 URL 行剥除）
        + 散文 → 1 section（format_cluster 由 processor 层 hint 覆盖为
        s5_prose，此处不断言推导值）"""
        raw = ("### 游戏范例（Example for game）\n\n"
               "### [http://45.79.87.129/bbs/index.php?topic=65615.0]"
               "(http://45.79.87.129/bbs/index.php?topic=65615.0) 译者:Falengel\n\n"
               "GM正在主持一场由4位玩家进行的冒险。")
        items = run(raw)
        assert len(items) == 1
        assert items[0]["title"] == "游戏范例（Example for game）"
        assert "GM正在主持" in items[0]["text"]
        assert "topic=65615" not in items[0]["text"]

    def test_no_heading_whole_text(self):
        """无任何标题 → 整篇 1 section（title 空串，M4 S5 补充）"""
        raw = "这是一段没有标题的散文正文，连续叙事。"
        items = run(raw)
        assert len(items) == 1
        assert items[0]["title"] == ""
        assert items[0]["format_cluster"] == "s5_prose"

    def test_s5_hint_roleplay_script(self):
        """page_130 游戏范例形态：hint=s5_prose 时角色名星壳行
        （`**哈斯克**`/`**GM**`）不切分，整篇 1 chunk（S5 语义 = 无边界
        整篇；角色名是对话说话人标注，不是节边界——M3 产出 +23 误切修复）"""
        raw = ("### 游戏范例（Example for game）\n\n"
               "**哈斯克**：\"我们进去吧。\"\n\n"
               "**GM**：你们进入地窖，闻到霉味。\n\n"
               "**席拉**：\"小心！\"")
        items = run(raw, format_cluster_hint="s5_prose")
        assert len(items) == 1
        assert items[0]["title"] == "游戏范例（Example for game）"
        assert items[0]["format_cluster"] == "s5_prose"
        assert "哈斯克" in items[0]["text"]
        assert "席拉" in items[0]["text"]
        assert items[0]["text"].count("**") >= 4  # 角色名星壳行原文保留

    def test_s5_no_h_open_star_title(self):
        """无 H 标题但首行是开星不闭标题行（`**战役说明（Campaign
        Clarifications）`——第十季战役说明/FAQ 类 S5 文件，源数据标题行
        跨行腰斩后 normalize 合并，无 `####` 结构）→ title 提取非空
        （M4 空 title 散点修复：_split_prose_whole 原只认 H 标题）"""
        raw = ("**战役说明（Campaign Clarifications）\n\n"
               "本文档对[额外资源](http://www.goddessfantasy.net)（列出了"
               "探索者协会角色扮演公会中所有可用的角色选项）进行补充。")
        items = run(raw, format_cluster_hint="s5_prose")
        assert len(items) == 1
        assert items[0]["title"] == "战役说明（Campaign Clarifications）"
        assert "战役说明" in items[0]["text"]

    def test_s5_three_star_note_not_title(self):
        """首行 3 星斜体注释（`***最后更新于…*`，战役说明正文形态）不是
        加粗标题——title 兜底只认 2 星开壳 `**X`（3 星开 = 斜体/编注行，
        不得误判为标题，防 `***最后更新…` 伪标题）"""
        raw = ("***最后更新于2018年3月14日（周四）*\n\n"
               "这是一段没有标题的散文正文，连续叙事。")
        items = run(raw, format_cluster_hint="s5_prose")
        assert len(items) == 1
        assert items[0]["title"] == ""

    def test_s5_bare_short_line_title(self):
        """首行裸标题短行（`不义（Amoral）`——HA 腐化文件形态）→ title
        提取（中英括号锚）；超长首句（`追逐(Chases)追逐在…` 正文开头，
        行 > 60 字符）不误判为标题（M4 空 title 散点修复：S5 兜底链
        H → 2 星开壳 → 裸标题短行，行短守卫防正文首句误判）"""
        raw = ("不义（Amoral）\n"
               "即使是最高贵的英雄也可能成为身体、思想或精神腐败的牺牲品。\n"
               "诱因（Catalyst）\n这种腐化往往始于你允许邪恶的力量进入你的生活。")
        items = run(raw, format_cluster_hint="s5_prose")
        assert len(items) == 1
        assert items[0]["title"] == "不义（Amoral）"

        # 超长正文首句（page_952 真实形态 ~2000 字符，此处用明确 >100 的
        # 长句模拟）：`追逐(Chases)` 行首虽匹配括号锚，但行长守卫拒绝
        raw2 = ("追逐(Chases)追逐在无数的故事里都扮演着重要的角色，不过因为移动速度系统，"
                "在pfrpg中模拟追逐却显得有些困难。每个生物都有它的移动速度，如果只按移动速度算，"
                "那么抓到（或抓不到）敌人都成为了必然。明显这并不符合逻辑，因为在逃亡的过程中需要"
                "考虑的其他因素比单纯的移动速度也许要重要得多。建立一场追逐战为了模拟现实中的追逐，"
                "你需要做一些准备工作。")
        items2 = run(raw2, format_cluster_hint="s5_prose")
        assert items2[0]["title"] == ""

        # 书名号形态（>60 但 ≤100 字符，勘误表文件首行
        # `《探索者战役设定：水下冒险》（Pathfinder Campaign Setting:
        # Aquatic Adventures）` ≈73 字符）→ 提取（守卫 100 兼容）
        raw3 = ("《探索者战役设定：水下冒险》（Pathfinder Campaign Setting: "
                "Aquatic Adventures）\n"
                "　　第51页——将海洋（Aquatic）血脉狂怒者选项中的“技能专攻（飞行）”"
                "改为“技能专攻（游泳）”。")
        items3 = run(raw3, format_cluster_hint="s5_prose")
        assert items3[0]["title"] == "《探索者战役设定：水下冒险》（Pathfinder Campaign Setting: Aquatic Adventures）"

    def test_s5_h1_wrapper_title(self):
        """首行 H1 包裹标题（`# 传奇编年史CoL 自我主义者之军势`——未整理
        整理产物形态）→ title 提取（M4 修复：_RE_H_HEADING 原只认 H3~H6，
        H1/H2 全落空）"""
        raw = ("# 传奇编年史CoL 自我主义者之军势\n\n"
               "<!-- 传奇编年史CoL-source:仪式.md:egoists_militia_ritual -->\n"
               "## 传奇编年史CoL 自我主义者之军势\n"
               "> 来源：传奇编年史（Chronicle of Legends），页码见原书\n"
               "自我主义者之军势 Egoist’s Militia\n"
               "学派 咒法系；等级8")
        items = run(raw, format_cluster_hint="s5_prose")
        assert len(items) == 1
        assert items[0]["title"] == "传奇编年史CoL 自我主义者之军势"


# ============================================================
#  S6 超大型聚合（M4，10 文件 4 形态：comment_anchor / entry_line /
#  haunt / bg_table）
# ============================================================


class TestS6Common:
    """S6 通用骨架：`****` 纯星分隔行剥除不产生节（LotFW 87 / 废土 63
    空 title 碎片根因修复）"""

    def test_pure_star_no_fragment(self):
        """`****` 纯星行 = 装饰分隔线 → 剥除、不产生空 title 节"""
        raw = ("**作祟：孤寂\n"
               "正文甲\n"
               "****\n"
               "**墙后抓挠声（SCRATCHING BEIND THE WALL）**\n"
               "正文乙\n"
               "****\n"
               "**冷点（COLD SPOT）**\n"
               "正文丙")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="haunt")
        assert titles(items) == ["作祟：孤寂",
                                 "墙后抓挠声（SCRATCHING BEIND THE WALL）",
                                 "冷点（COLD SPOT）"]
        assert all(it["title"] for it in items)  # 零空 title（87 碎片回归）
        assert all("****" not in it["text"] for it in items)

    def test_anchor_comment_stripped(self):
        """`<!-- X-source -->` 注释剥除且不产生节"""
        raw = ("<!-- BOTD-source:page_1513.md:阿达德 -->\n"
               "**阿达德·莉莉（Ardad Lili）**\n"
               "正文")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="comment_anchor")
        assert len(items) == 1
        assert items[0]["title"] == "阿达德·莉莉（Ardad Lili）"
        assert "BOTD-source" not in items[0]["text"]


class TestS6CommentAnchor:
    """永罪之书×5：`<!-- X-source -->` 注释 = 唯一条目边界；条目内星壳
    小节（神恩三组/头衔/字段）全部并入"""

    def test_anchor_boundary_and_inner_sections_joined(self):
        """锚点后标题 = 边界；条目内跨行头衔/字段/神恩小节并入"""
        raw = ("<!-- BOTD-source:神恩/地狱/page_1513.md:阿达德·莉莉 -->\n"
               "**阿达德·莉莉（Ardad Lili）**\n"
               "> 来源：永罪之书\n"
               "阿达德·莉莉 Ardad Lili\n"
               "**纯真之末（End of\n"
               "Innocence）**\n"
               "**阵营** \n"
               "守序邪恶\n"
               "**飞蝇领主**\n"
               "<!-- BOTD-source:神恩/地狱/page_1524.md:巴尔泽布 -->\n"
               "**巴尔泽布（Baalzebul）**\n"
               "> 来源：永罪之书\n"
               "**资源**：*内海诸神*")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="comment_anchor")
        assert titles(items) == ["阿达德·莉莉（Ardad Lili）",
                                 "巴尔泽布（Baalzebul）"]
        first = items[0]["text"]
        # 条目内星壳小节/字段/跨行头衔并入（不独立成节）
        assert "纯真之末" in first
        assert "守序邪恶" in first
        assert "飞蝇领主" in first
        assert "> 来源：永罪之书" in first

    def test_anchor_after_blank_line(self):
        """锚点与标题间空行不破坏边界（锚点消费于首个非空行）"""
        raw = ("<!-- BOTD-source:page_79.md:阿里曼 -->\n"
               "\n"
               "**阿里曼（Ahriman）**\n"
               "正文")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="comment_anchor")
        assert titles(items) == ["阿里曼（Ahriman）"]

    def test_secondary_demon_name_line_boundary(self):
        """KN210：非锚点位置的星壳名字行（无中文括号中英混排，如次级魔鬼
        `**比弗伦斯 Bifrons**`）= 独立条目边界；条目内神恩小节（中文括号）、
        字段行（**阵营**）、头衔小节（**飞蝇领主**）、服从仪典表格行并入
        所属条目"""
        raw = ("<!-- BOTD-source:神恩/地狱/page_1513.md:阿达德·莉莉 -->\n"
               "**阿达德·莉莉（Ardad Lili）**\n"
               "> 来源：永罪之书\n"
               "**纯真之末（End of\n"
               "Innocence）**\n"
               "**阵营** \n"
               "守序邪恶\n"
               "**飞蝇领主**\n"
               "| 阵营 | 神职 | 领域 |\n"
               "| --- | --- | --- |\n"
               "| 守序邪恶 | 苍蝇 | 邪恶 |\n"
               "**比弗伦斯 Bifrons**\n"
               "**忠诚** \n"
               "服务阿达德·莉莉\n"
               "<!-- BOTD-source:神恩/地狱/page_1524.md:巴尔泽布 -->\n"
               "**巴尔泽布（Baalzebul）**\n"
               "> 来源：永罪之书\n"
               "**资源**：*内海诸神*")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="comment_anchor")
        assert titles(items) == ["阿达德·莉莉（Ardad Lili）",
                                 "比弗伦斯 Bifrons",
                                 "巴尔泽布（Baalzebul）"]
        first = items[0]["text"]
        # 条目内小节/字段/跨行头衔/表格行并入（不独立成节）
        assert "纯真之末" in first and "守序邪恶" in first
        assert "飞蝇领主" in first and "服务阿达德·莉莉" not in first
        second = items[1]["text"]
        assert "服务阿达德·莉莉" in second  # 次级魔鬼独立条目内容

    def test_secondary_demon_cross_line_name(self):
        """KN210：跨行名字行 `**洛肯 \nLorcan**`（开星不闭 + 下行英文闭壳）
        拼接为独立条目 title=`洛肯 Lorcan`，不吞入前条目"""
        raw = ("<!-- BOTD-source:神恩/地狱/page_1513.md:阿达德·莉莉 -->\n"
               "**阿达德·莉莉（Ardad Lili）**\n"
               "正文。\n"
               "**洛肯 \n"
               "Lorcan**\n"
               "**忠诚** \n"
               "服务冯易斯")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="comment_anchor")
        assert titles(items) == ["阿达德·莉莉（Ardad Lili）", "洛肯 Lorcan"]
        assert "服务冯易斯" in items[1]["text"]


class TestS6EntryLine:
    """LotFW / 废土子民：裸标题行（尾 2 空格短行中英 / 中英括号锚）=
    边界；跨行标题上行拼接；子项并入"""

    def test_lotfw_bare_title_and_subitems(self):
        """裸标题行 `矮人Dwarf  ` = 边界；子项 `漫游者：`（无尾空格）
        并入所属节；`****` 剥除"""
        raw = ("精类起源FEY ORIGINS  \n"
               "导言段落。\n"
               "****\n"
               "矮人Dwarf  \n"
               "矮人正文。\n"
               "漫游者：一些矮人获得坚忍。\n"
               "****\n"
               "精灵Elf  \n"
               "精灵正文。")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="entry_line")
        assert titles(items) == ["精类起源FEY ORIGINS", "矮人Dwarf", "精灵Elf"]
        assert "漫游者" in items[1]["text"]  # 子项并入所属节

    def test_source_block_not_title(self):
        """KN210 补：引用块 `> 来源：…（Black Markets）` 不判标题（尸体
        贸易首节伪 title）；跨行标题（`尸体贸易（The Corpse \nTrade）`）
        并入首节"""
        raw = ("## 尸体贸易\n"
               "> 来源：黑市指南（Black Markets）BM，页码见原书\n"
               "尸体贸易（The Corpse \n"
               "Trade）\n"
               "导言正文。\n"
               "亡灵雇员（Ghoulrunning）\n"
               "亡灵雇员正文。")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="entry_line")
        assert titles(items) == ["尸体贸易（The Corpse Trade）",
                                 "亡灵雇员（Ghoulrunning）"]
        # 来源行并入首节（不独立成伪 title chunk）
        assert "黑市指南" in items[0]["text"]

    def test_halfparen_mid_sentence_not_title(self):
        """KN210 补：半角括号句中（`从魔魂尸(mohrg)中提取…` 括号后紧贴
        中文）= 正文行不判标题；半角括号后非中文（`不朽奏者(Undying
        Word)【歌者】`）仍为标题"""
        raw = ("窒杀魔之舌（STRANGLER'S TONGUE）\n"
               "从魔魂尸(mohrg)中提取，这根肌肉发达的舌头被植入宿主的嘴巴或喉咙内。\n"
               "制造条件：制造奇物\n"
               "不朽奏者(Undying Word)【歌者】\n"
               "不朽奏者正文。")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="entry_line")
        assert titles(items) == ["窒杀魔之舌（STRANGLER'S TONGUE）",
                                 "不朽奏者(Undying Word)【歌者】"]
        assert "从魔魂尸" in items[0]["text"]

    def test_lotfw_english_only_title(self):
        """纯英文大写裸标题 `FEATS  ` = 边界"""
        raw = ("专长FEATS  \n"
               "导言\n"
               "****\n"
               "FEATS  \n"
               "专长列表正文")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="entry_line")
        assert titles(items) == ["专长FEATS", "FEATS"]

    def test_wasteland_bracket_anchor_and_cross_line(self):
        """废土：中英括号锚行 = 边界；标题跨 2 行（上行纯中文短行拼接）；
        章节破折号星壳 = 边界；`****` 后普通段落不误切"""
        raw = ("**————法力废土求生————**\n"
               "法力废土上危机四伏。\n"
               "相反，这些下等贱民要么是出生于此。\n"
               "****\n"
               "法力废土上的部落许多游牧部众。\n"
               "****\n"
               "无定引信 \n"
               "Volatile Fuse（战斗）：你手中的火器十分危险。\n"
               "****\n"
               "高热射击（Sizzling Shot，勇毅）你射出的子弹火焰缭绕。\n"
               "****\n"
               "六重忏悔（Sixfold Repentance）数个部落曾为大法师服务。")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="entry_line")
        assert titles(items) == [
            "————法力废土求生————",
            "无定引信 Volatile Fuse（战斗）",   # 跨行拼接（上行中文 + 括号名）
            "高热射击（Sizzling Shot，勇毅）",
            "六重忏悔（Sixfold Repentance）",
        ]
        # `****` 后的普通段落并入前节（不误切）
        assert "部落许多游牧部众" in items[0]["text"]


class TestS6Haunt:
    """作祟汇总 / OR：星壳标题（「作祟：」前缀 / 闭壳中英括号 / 开星不闭
    含英文括号）= 边界；字段行（尾空格/值同行/双空格）与名称行并入"""

    def test_haunt_title_forms(self):
        """作祟标题三形态：`**作祟：X`（开星不闭前缀）/ 闭壳中英括号 /
        名称行（名+EN 无括号+CR—）并入"""
        raw = ("**作祟：孤寂\n"
               "****（该作祟翻译引自http://x.com/topic）**\n"
               "**孤寂Isolation CR—**\n"
               "中立邪恶 作祟（半径30尺）\n"
               "**墙后抓挠声（SCRATCHING BEIND THE WALL）**\n"
               "来源 《Horror adventures》第174页\n"
               "**血手印（Bloody Handprints）**\n"
               "描述 谋杀残留的血迹。")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="haunt")
        assert titles(items) == [
            "作祟：孤寂",
            "墙后抓挠声（SCRATCHING BEIND THE WALL）",
            "血手印（Bloody Handprints）",
        ]
        # 4 星引用注 + 名称行并入条目
        assert "该作祟翻译引自" in items[0]["text"]
        assert "孤寂Isolation" in items[0]["text"]

    def test_haunt_field_lines_join(self):
        """作祟字段行三形态并入：`**施法者等级** `（尾空格值换行）/
        `**生命值** 1；触发…`（值同行）/ `**注意**  感知DC`（双空格）"""
        raw = ("**墙后抓挠声（SCRATCHING BEIND THE WALL）**\n"
               "**施法者等级** \n"
               "4级\n"
               "**注意**  感知DC 18\n"
               "**生命值** 1；触发 触碰；重置 \n"
               "1天\n"
               "**挑战等级** 1/2：**经验值** 200\n"
               "**摧毁** \n"
               "破坏该作祟需要……")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="haunt")
        assert len(items) == 1
        assert items[0]["title"] == "墙后抓挠声（SCRATCHING BEIND THE WALL）"
        assert "4级" in items[0]["text"]
        assert "感知DC 18" in items[0]["text"]
        assert "触发 触碰" in items[0]["text"]
        assert "经验值" in items[0]["text"]
        assert "破坏该作祟" in items[0]["text"]

    def test_or_open_star_title_and_dedupe(self):
        """OR：开星不闭标题（`**激活艾悠达拉（Aiudara Activation）`）=
        边界；相邻重复标题（开星版 + 闭壳完整版）合并去重"""
        raw = ("**仪式与偶像（Rituals and Idols）\n"
               "导言段。\n"
               "**激活艾悠达拉（Aiudara Activation）\n"
               "艾悠达拉网络是传送门系统。\n"
               "**激活艾悠达拉（Aiudara Activation）**\n"
               "**学派** \n"
               "咒法系\n"
               "**施放时间** \n"
               "1小时\n"
               "**解析大会（Analytical Congress）\n"
               "由巴拉丁之眼秘会。")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="haunt")
        assert titles(items) == [
            "仪式与偶像（Rituals and Idols）",
            "激活艾悠达拉（Aiudara Activation）",  # 重复标题合并为 1 节
            "解析大会（Analytical Congress）",
        ]
        # 合并节含导言 + 字段块
        assert "传送门系统" in items[1]["text"]
        assert "咒法系" in items[1]["text"]

    def test_or_effect_label_trailing_space(self):
        """`**效果 **`（闭壳前空格）标签 → 词表 strip 后并入"""
        raw = ("**解析大会（Analytical Congress）**\n"
               "**效果 **\n"
               "仪式效果描述。")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="haunt")
        assert len(items) == 1
        assert "仪式效果描述" in items[0]["text"]


class TestS6BgTable:
    """角色背景生成器：闭壳星壳标题（表标题/阶段标题）= 边界；表格行
    （`**d%`/`**01-40`）与原文地址行并入"""

    def test_table_headers_boundaries_rows_join(self):
        """`**矮人故乡**` = 边界；表格行 `**01-40——丘陵:** 值` /
        `**d%     ` 并入"""
        raw = ("**矮人故乡**\n"
               "**d%     \n"
               "**01-40——丘陵或者山脉:** \n"
               "丘陵价值。\n"
               "**41-80——地下:** \n"
               "地下价值。\n"
               "**矮人父母**\n"
               "**d%              \n"
               "**01-60——你父母都健在。\n"
               "**矮人兄弟姐妹**\n"
               "**01-90——独子。")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="bg_table")
        assert titles(items) == ["矮人故乡", "矮人父母", "矮人兄弟姐妹"]
        assert "01-40——丘陵" in items[0]["text"]
        assert "01-60——你父母都健在" in items[1]["text"]

    def test_inline_bold_heading_and_source_url(self):
        """行内加粗 `**阶段1——故乡：**确定你…` = 边界（title 剥尾冒号，
        正文同行保留）；`**原文地址：**URL` 并入不切"""
        raw = ("**角色背景生成器**\n"
               "**原文地址：**[http://legacy.aonprd.com/x](http://x)\n"
               "**阶段1——故乡、家庭、童年：**确定你的出生状况。\n"
               "**阶段1——故乡、家庭、童年**\n"
               "**步骤1：**在故乡表中找到你种族的部分。")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="bg_table")
        assert titles(items) == ["角色背景生成器", "阶段1——故乡、家庭、童年"]
        # 原文地址并入首节；相邻同名阶段标题合并
        assert "原文地址" in items[0]["text"]
        assert "legacy.aonprd.com" in items[0]["text"]
        # 阶段 2 节 = 行内加粗版 + 独立标题版合并 + 步骤并入
        assert "确定你的出生状况" in items[1]["text"]
        assert "步骤1" in items[1]["text"]

    def test_explanation_sentence_not_title(self):
        """KN214 补：表说明行（含句号）不判边界——`**投掷一次决定你的
        出生状况。`（开星不闭）与 `**当你出生时…。你可以选择**信念背景…`
        （闭壳含句号）并入所属节；表标题（`**出生状况表` 无句号）仍为边界"""
        raw = ("**出生状况表\n"
               "**投掷一次决定你的出生状况。\n"
               "**当你出生时你暴露在了强大的神圣能量之中。你可以选择**信念背景圣能渠（Sacred \n"
               "Channel）\n"
               "**d%**\n"
               "**01-10——正常出生。")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="bg_table")
        assert titles(items) == ["出生状况表"]
        assert "投掷一次决定你的出生状况" in items[0]["text"]
        assert "神圣能量" in items[0]["text"]

    def test_cross_line_table_row_continuation(self):
        """KN214：开星不闭表格行（`**01-05——学院教育（Academy Training）: `
        跨行上行）+ 下行星壳正文（`**你曾就读于…**`）→ 下行并入不判边界，
        不产生「正文首句」伪标题 chunk"""
        raw = ("**重大童年事件表**\n"
               "**01-05——学院教育（Academy Training）: \n"
               "**你曾就读于一所私立学院，在那里你学到了大量技能并且得到了**\n"
               "同班同学的照顾。\n"
               "**06-20——学徒（Apprentice）: **你曾在一个铁匠铺里当学徒**。")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="bg_table")
        assert titles(items) == ["重大童年事件表"]
        assert "你曾就读于一所私立学院" in items[0]["text"]
        assert "学院教育" in items[0]["text"]
        assert "学徒" in items[0]["text"]


class TestS6GodTable:
    """page_320 神祇扩展整页表格（KN211）：含拉丁首列表格行 = 独立条目
    （title=首列神名）；表头/分隔/说明行/表标题并入首节"""

    def test_table_row_title_first_col(self):
        """`| 埃拉斯蒂尔（Erastil） | …` = 边界 title=首列；表头行/分隔行/
        说明行/嵌套星标题行并入首节"""
        raw = ("**内海****&****龙国部分神祇扩展列表**\n"
               "**注：**神职中带有**下划线加粗**的可在引导能量变体中找到。\n"
               "| 神祇 | 阵营 | 神职 | 领域 | 偏好武器 | 分类 | 出处 |\n"
               "| --- | --- | --- | --- | --- | --- | --- |\n"
               "| 埃拉斯蒂尔（Erastil） | 秩序善良（LG） | 家庭, 农业 | 动物 | 长弓 | 核心神祇 | CRB/ISWG |\n"
               "| 莎伦莱（Sarenrae） | 中立善良（NG） | 医疗, 诚实 | 太阳 | 弯刀 | 核心神祇 | CRB |")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="god_table")
        assert titles(items) == ["埃拉斯蒂尔（Erastil）", "莎伦莱（Sarenrae）"]
        # 首节 = 表标题 + 说明 + 表头 + 分隔行并入（不独立成 chunk）
        assert "神祇扩展列表" in items[0]["text"]
        assert "注：" in items[0]["text"]
        assert "| 神祇 |" in items[0]["text"]
        # 条目 text 保留整行内容（可检索阵营/神职）
        assert "秩序善良（LG）" in items[0]["text"]

    def test_no_latin_row_joined(self):
        """无拉丁首列行（`| 表：变体引导 |` / `| 神职/主题 |`）= 表头/分组行
        并入所属节，不产生泛词 title chunk"""
        raw = ("| 表：变体引导 |\n"
               "| 神职/主题 | 引导能量 | 来源 |\n"
               "| --- | --- | --- |\n"
               "| 医疗/太阳 | 神圣 | CRB |\n"
               "| 医疗（Healing） | 神圣 | CRB |")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="god_table")
        assert titles(items) == ["医疗（Healing）"]
        assert "变体引导" in items[0]["text"]


class TestS6Negative:
    """S6 防回退：title 无星壳 / 无空 title / 词表断言"""

    def test_no_star_in_s6_titles(self):
        """所有 S6 title 无 `*` 残迹（KN160 防回退）"""
        raw = ("**作祟：孤寂\n"
               "正文\n"
               "****\n"
               "**冷点（COLD SPOT）**\n"
               "正文")
        for it in run(raw, format_cluster_hint="s6_large_aggregate",
                      s6_shape="haunt"):
            assert "*" not in it["title"]

    def test_s6_field_words_extended(self):
        """S6 词表扩展已注册（施法者等级/察觉/摧毁/注意/触发 ∈ 字段词表）"""
        from vectorizer.registry_rule import RULE_FIELD_LABELS_S6
        for w in ("施法者等级", "察觉", "摧毁", "注意", "生命值", "触发",
                  "再起", "重置", "挑战等级", "经验值"):
            assert w in RULE_FIELD_LABELS_S6, w

    def test_bg_table_row_never_title(self):
        """表格行永不产生节（d% 行 / 数字范围行）"""
        raw = ("**矮人故乡**\n"
               "**d%     \n"
               "**01-40——丘陵:** 值\n"
               "**96-100——不寻常的故乡:** 值")
        items = run(raw, format_cluster_hint="s6_large_aggregate",
                    s6_shape="bg_table")
        assert len(items) == 1
        assert items[0]["title"] == "矮人故乡"


# ============================================================
#  负向防回退（KN159/160 + 字段行）
# ============================================================


class TestNegative:
    """星壳残迹 / CR 残迹 / 字段行伪条目 防回退断言"""

    def test_no_star_shell_in_titles(self):
        """所有 title 无 `*` 残迹（KN160 星壳剥离防回退）"""
        raw = ("#### 节一（****EN****）\n\n"
               "**纯中文节**：正文\n\n"
               "**嵌套节（****Nested****）******：正文")
        for it in run(raw):
            assert "*" not in it["title"], f"title 含星壳残迹: {it['title']!r}"

    def test_no_cr_left_after_normalize(self):
        """normalize 后无 `\\r`（KN159/191 表格 CR 腰斩防回退）"""
        fmt = RuleFormat()
        text = fmt.normalize("正文\r\n行尾\n行中\r残迹\n")
        assert "\r" not in text
        assert "行尾" in text and "行中" in text

    def test_field_line_never_empty_section(self):
        """字段行永不产生空 text 独立 section"""
        raw = ("**节标题**\n\n"
               "**效果**：该能力的效果描述。\n\n"
               "**先决条件**：力量13。")
        items = run(raw)
        assert len(items) == 1
        assert items[0]["text"].strip()


class TestStarFragmentStripped:
    """KN212（2026-08-09）：text 4+ 星连排碎片剥壳防回退。

    BBS `[b]` 嵌套转换残渣（`**重训（****Retraining****）******` /
    `**野蛮****人****（Unchained）**` / `**【****PFS****】**`）散布全模块
    1239 片/109 文件（audit 登记 1241，9377→9366 后微差）。剥壳规则：
    4+ 星连排 = 「加粗壳边界粘连 + 残留」，直接剥除；干净 2 星加粗
    （`**X**` 正文强调）与单星斜体（人名/书名，docstring 305 处全定性
    保留）不在剥除范围。
    """

    def test_nested_star_pairs_flattened(self):
        """嵌套加粗壳 `**重训（****Retraining****）******` → 无 4+ 星"""
        fmt = RuleFormat()
        text = fmt.normalize("**重训（****Retraining****）******")
        assert "****" not in text
        assert "重训（Retraining）" in text

    def test_adjacent_star_pairs_glued(self):
        """相邻加粗壳粘连 `**野蛮****人****（Unchained）**` → 干净 2 星"""
        fmt = RuleFormat()
        text = fmt.normalize("**野蛮****人****（Unchained）**")
        assert "****" not in text
        assert text == "**野蛮人（Unchained）**"

    def test_pfs_quad_star_block(self):
        """行内 `**【****PFS****】**` → `**【PFS】**`"""
        fmt = RuleFormat()
        text = fmt.normalize("原本的原力有相同或更低的等级。**【****PFS****】**")
        assert "****" not in text
        assert "【PFS】" in text

    def test_clean_double_star_untouched(self):
        """干净 2 星加粗（正文强调/小节标记）不受影响"""
        fmt = RuleFormat()
        text = fmt.normalize("**阶段1——故乡、家庭、童年：**确定你的人生。")
        assert "**阶段1——故乡、家庭、童年：**" in text

    def test_italic_single_star_untouched(self):
        """单星斜体（人名/书名语义，docstring 全定性保留）不受影响"""
        fmt = RuleFormat()
        text = fmt.normalize("这是 *Pathfinder* 的一条规则。")
        assert "*Pathfinder*" in text

    def test_run_output_no_quad_star(self):
        """split 产物 text 全无 4+ 星连排（碎片形态端到端回归）"""
        raw = ("**重训（****Retraining****）******\n\n"
               "你可以通过重训改变职业特性。**【****PFS****】**\n\n"
               "野蛮****人****（Unchained）**：重训一项【狂暴之力】。")
        for it in run(raw):
            assert "****" not in it["text"], f"text 含 4+ 星: {it['text'][:60]!r}"


# ============================================================
#  主循环 H1/H2 与表标题行（M4 空 title 散点修复，2026-08-09）
# ============================================================


class TestHtmlCommentStripped:
    """KN206（2026-08-09 M6 审计 P1-1）：S1~S5 路径 HTML 来源注释行剥除。

    S6 锚点已在 TestS6Common.test_anchor_comment_stripped 覆盖（消费不产生
    节）；S1~S5 无锚点语义，注释行走正文并入所属节造成 126 chunk 泄漏
    （s2 90 + s5 29 + s3 5 + s4 2）。剥离只影响 chunk 文本——chm_toc_path
    回填读**源文件**注释（feat_chain RE_ANNO），不受影响。
    """

    def test_s2_head_comment_stripped(self):
        """S2 加粗标题路径：注释行在标题前 → 不进首节 text、不产生节"""
        raw = ("<!-- CaC部属与伙伴-source:种植植物生物.md:grow_plant_creature -->\n"
               "**种植植物生物（Grow Plant Creature）**\n"
               "正文内容")
        items = run(raw)
        assert len(items) == 1
        assert items[0]["title"] == "种植植物生物（Grow Plant Creature）"
        assert "<!--" not in items[0]["text"]
        assert "CaC部属与伙伴-source" not in items[0]["text"]

    def test_s1_heading_comment_stripped(self):
        """S1 heading 路径：注释行 + H 标题 → 剥除"""
        raw = ("<!-- AA-source:page_438.md:__aggregate__ -->\n"
               "#### 突袭轮（The Surprise Round）\n"
               "正文")
        items = run(raw)
        assert len(items) == 1
        assert items[0]["title"] == "突袭轮（The Surprise Round）"
        assert "<!--" not in items[0]["text"]

    def test_mid_text_comment_stripped(self):
        """chunk 中部注释行 → 剥除（审计：126 泄漏含 chunk 中部形态）"""
        raw = ("**陷阱（Traps）**\n"
               "正文段落一\n"
               "<!-- 机关陷阱-source:page_279.md:trap_rules -->\n"
               "正文段落二")
        items = run(raw)
        assert len(items) == 1
        assert items[0]["title"] == "陷阱（Traps）"
        assert "<!--" not in items[0]["text"]
        assert "正文段落一" in items[0]["text"]
        assert "正文段落二" in items[0]["text"]

    def test_s5_prose_comment_stripped(self):
        """S5 prose 整篇：注释行剥除（不进正文；注释剥除后首行星壳兜底生效）"""
        raw = ("<!-- ISI-source:假面伪装.md:masked_persona_rules -->\n"
               "**面具（Masks）**\n"
               "伪装规则正文")
        items = run(raw, format_cluster_hint="s5_prose")
        assert len(items) == 1
        assert items[0]["title"] == "面具（Masks）"
        assert "<!--" not in items[0]["text"]
        assert "ISI-source" not in items[0]["text"]

    def test_pending_comment_stripped(self):
        """文件首导言注释（首个边界前）→ 剥除不污染首节"""
        raw = ("<!-- 药剂与毒药P&P-source:page_1263.md:potion_oil_reference -->\n"
               "导言段落\n"
               "**药剂（Potions）**\n"
               "正文")
        items = run(raw)
        assert len(items) == 1
        assert "<!--" not in items[0]["text"]
        assert "导言段落" in items[0]["text"]


class TestS4TablePage:
    """s4 整页纯表与主循环 H 扩展形态"""

    def test_h1_h2_wrapper_merged(self):
        """`# X` + 注释 + `## X` 同题包裹复述（未整理整理产物形态，
        传奇编年史CoL_神秘仪式）→ 单节 title=X，不复述双节碎片——
        同题相邻且 cur 仅标题+注释行时覆盖不新建"""
        raw = ("# 传奇编年史CoL 自我主义者之军势\n\n"
               "<!-- 传奇编年史CoL-source:仪式.md:egoists_militia_ritual -->\n"
               "## 传奇编年史CoL 自我主义者之军势\n"
               "> 来源：传奇编年史（Chronicle of Legends），页码见原书\n"
               "自我主义者之军势 Egoist’s Militia\n"
               "学派 咒法系；等级8\n"
               "施放时间 80分钟\n\n"
               "## 下一个仪式\n"
               "正文内容。")
        items = run(raw)
        assert len(items) == 2
        assert items[0]["title"] == "传奇编年史CoL 自我主义者之军势"
        assert "Egoist’s Militia" in items[0]["text"]
        assert "> 来源：传奇编年史" in items[0]["text"]
        assert items[1]["title"] == "下一个仪式"

    def test_h1_leading_title(self):
        """H1 标题行建节（第一世界TFWRotF 形态：H1 + 注释 + H2 复述 +
        正文 → title=H1 内容，非空）"""
        raw = ("# 第一世界TFWRotF 第一世界施法规则\n\n"
               "<!-- 第一世界TFWRotF-source:施法规则.md:first_world_spellcasting -->\n"
               "## 第一世界TFWRotF 第一世界施法规则\n"
               "> 来源：第一世界（The First World），页码见原书\n"
               "第一世界的施法者遵循不同的规则。")
        items = run(raw)
        assert len(items) == 1
        assert items[0]["title"] == "第一世界TFWRotF 第一世界施法规则"
        assert "第一世界的施法者" in items[0]["text"]

    def test_first_line_bare_title_in_main_loop(self):
        """主循环文件首行裸标题短行（page_653 s2 形态：空行 + `天生物品
        加值（Innate Item Bonuses）` + 正文）→ 建节提取 title；正文中
        裸短行（`诱因（Catalyst）` 类小标）不建节（仅首行触发）"""
        raw = ("\n\n天生物品加值（Innate Item Bonuses）\n"
               "一些GM会发现，面对玩家们想获得魔法物品特定加值的需求时显得很为难。\n"
               "诱因（Catalyst）\n这种腐化往往始于邪恶的力量进入你的生活。")
        items = run(raw)
        assert len(items) == 1
        assert items[0]["title"] == "天生物品加值（Innate Item Bonuses）"

    def test_first_line_table_title(self):
        """文件首行即表标题行（`| 表：召唤怪物 |`，page_400 整页纯表）
        → title=表标题；普通文件表格标题行（前有节标题）仍并入所属节"""
        raw = ("| 表：召唤怪物 |\n"
               "| --- |\n"
               "| 召唤生物 | 亚种 |\n"
               "| 1环 |  |")
        items = run(raw)
        assert len(items) == 1
        assert items[0]["title"] == "表：召唤怪物"

        raw2 = ("**节标题**\n\n"
                "正文内容。\n\n"
                "| 表：属性购点 |\n"
                "| --- |\n"
                "| 原始属性 | 消耗购点 |")
        items2 = run(raw2)
        assert len(items2) == 1
        assert items2[0]["title"] == "节标题"
        assert "表：属性购点" in items2[0]["text"]


# ============================================================
#  Oversize 超限预拆（M4 R9，2026-08-09：>5000 段落级/行级再拆，
#  表格 chunk 不拆——结构完整性，登记 max-oversize）
# ============================================================


class TestOversizeSplit:
    """超限 chunk 预拆：段落级（\n\n）优先，无段落边界行级（\n）；
    表格 chunk（text 首行即表行）不拆；尾块过小并入前块"""

    def test_table_sep_row_not_isolated(self):
        """KN210 补：行级续拆中纯分隔行 `| --- |` 并入前段，不独立成
        8 字符噪声 chunk（阿达德·莉莉续5 len=8 根因）"""
        rows = "\n".join(f"第{i}行。" + "乙" * 120 for i in range(40))
        raw = f"**大节标题**\n{rows}\n| --- |\n| 制造成本：18000gp |"
        items = run(raw)
        assert len(items) >= 2
        assert not any(it["text"].strip() == "| --- |" for it in items)
        assert any("| --- |" in it["text"] for it in items)

    def test_multi_para_split(self):
        """多段落超限（8 段 × 700 ≈ 5600）→ 段落累积 2 块；首块 title
        原样，续块 `原title（续2）`；总字符守恒"""
        paras = "\n\n".join(f"第{i}段。" + "甲" * 690 for i in range(8))
        raw = f"**大节标题**\n\n{paras}"
        items = run(raw)
        assert len(items) == 2
        assert items[0]["title"] == "大节标题"
        assert items[1]["title"] == "大节标题（续2）"
        # 内容不丢：首块含标题行 + 段1，续块含段8；字符守恒 ± 分隔符
        # 重构（首块保留标题行、续块重建 `\n\n`，总长 = 原文 ± 换行）
        assert "**大节标题**" in items[0]["text"]
        assert "第0段。" in items[0]["text"]
        assert "第7段。" in items[1]["text"]
        total = sum(len(it["text"]) for it in items)
        assert abs(total - len(raw)) < 100

    def test_table_chunk_untouched(self):
        """整表超限（text 首行即 `|` 表行）→ 不拆（表格结构完整性，
        登记 max-oversize，检索端降权）"""
        rows = "\n".join(f"| 行{i} | {'甲' * 60} |" for i in range(120))
        raw = f"| 表：大表 |\n| --- |\n{rows}"
        items = run(raw)
        assert len(items) == 1

    def test_single_block_line_split(self):
        """无段落边界（\n\n 不存在）超限（120 行 × 60 ≈ 7200）→ 行级
        累积 2 块；续块 title 续标"""
        lines = "\n".join(f"第{i}行内容。" + "乙" * 40 for i in range(120))
        raw = f"**大节标题**\n\n{lines}"
        items = run(raw)
        assert len(items) == 2
        assert items[0]["title"] == "大节标题"
        assert items[1]["title"] == "大节标题（续2）"
        assert len(items[0]["text"]) <= 5000 + 200
        # 内容不丢：行首行在首块、尾行在续块（行级拆无段落重构）
        assert "第0行内容。" in items[0]["text"]
        assert "第119行内容。" in items[1]["text"]

    def test_small_chunk_untouched(self):
        """3000 字符不超限 → 1 块不动"""
        raw = "**小标题**\n\n" + "正" * 2990
        items = run(raw)
        assert len(items) == 1

    def test_s5_oversize_split(self):
        """S5 整篇超限（prose 无边界）→ 预拆仍生效（s5 hint 出口同样
        走 oversize 拆分包）；行级拆 2 满块 + 碎尾块（并入会超限不并，
        碎尾独立 chunk 可检索）；空 title 续块 = `（续N）`"""
        lines = "\n".join(f"第{i}行。" + "丙" * 45 for i in range(200))
        items = run(lines, format_cluster_hint="s5_prose")
        assert len(items) >= 2
        assert all(it["format_cluster"] == "s5_prose" for it in items)
        # 空 title → 续块 title = `（续2）`；内容不丢（行首/行尾保留）
        assert items[1]["title"] == "（续2）"
        assert "第0行。" in items[0]["text"]
        assert "第199行。" in items[-1]["text"]

    def test_oversize_para_recurse(self):
        """段级切出的超限段（>5000 多行）→ 行级递归再拆（计划文档
        「超限按下一级结构再拆」本义：段落 → 行两级下探）"""
        seg1 = "\n".join(f"第{i}行。" + "丁" * 50 for i in range(120))
        raw = f"**大节标题**\n\n{seg1}\n\n结尾段。"
        items = run(raw)
        assert len(items) >= 3
        assert all(len(it["text"]) <= 5000 for it in items)
        # 内容不丢：行首/行尾保留（整体拼接断言，不依赖块序）
        joined = "".join(it["text"] for it in items)
        assert "第0行。" in joined and "第119行。" in joined

    def test_oversize_head_allowance(self):
        """首块标题行 + 分隔开销（head+2）→ 阈值前移，piece0 ≤ 5000"""
        seg1 = "\n".join(f"第{i}行。" + "戊" * 50 for i in range(100))
        raw = f"**大节标题**\n\n{seg1}"
        items = run(raw)
        assert len(items) >= 2
        assert all(len(it["text"]) <= 5000 for it in items)

    def test_oversize_table_row_segments(self):
        """行级拆中表格行（`|` 开头）独立成段（结构保护，不拼入正文块）"""
        rows = "\n".join(f"| 行{i} | {'己' * 40} |" for i in range(150))
        raw = f"**大节标题**\n\n{rows}"
        items = run(raw)
        assert len(items) >= 2
        for it in items:
            assert len(it["text"]) <= 5000 or it["text"].strip().startswith("|")


# ============================================================
#  M5 title 清洗缺陷修复（2026-08-09：verify title 合法性检查前置）
#  三类：markdown 链接 title（page_314/1490）/ S6 entry_line 加粗壳
#  （PotW）/ 译者星壳行（page_517/601/646，闭壳+开星不闭双形态）
# ============================================================

class TestTitleCleanup:
    """M5 探针发现的 title 清洗缺陷（verify title 合法性检查会红）"""

    def test_title_md_link_stripped(self):
        """`**[神秘技能解放（Occult Skill Unlocks）](http://...)` → 剥链接
        取文本（page_314 BBS 链接标题形态，`_extract_title` 缺 markdown
        链接剥壳）"""
        raw = "**[神秘技能解放（Occult Skill Unlocks）](http://paizo.com/occult-skills)**\n\n正文。\n"
        items = run(raw)
        assert items[0]["title"] == "神秘技能解放（Occult Skill Unlocks）"
        assert "http" not in items[0]["title"]

    def test_title_img_link_stripped(self):
        """`![[图片]](url)` → 图片（page_1490 图片行形态）"""
        raw = "![[法术效果图]](https://example.com/img.png)\n\n正文。\n"
        items = run(raw)
        assert items[0]["title"] == "法术效果图"

    def test_title_orphan_url_tail_stripped(self):
        """孤立 `](http://...)` 残渣行 → normalize 剥除（page_322，
        `[文本](url)` 源行被剥文本部分后残留）"""
        raw = "**正常节**\n\n正文内容。\n\n](http://paizo.com/rule)\n\n下一节。\n"
        items = run(raw)
        assert all("](http" not in it["title"] for it in items)
        assert "](http" not in "".join(it["text"] for it in items)

    def test_s6_entry_line_star_shell(self):
        """entry_line 裸标题行带加粗壳 `**高等爆裂哑火（Violent Misfire,
        Greater）**  `（尾 2 空格 + 星壳）→ 剥壳（PotW 形态，
        `_s6_judge_title` 167 行 `return s.strip()` 未过 _extract_title）"""
        raw = ("废土武器Wasteland Weapons  \n"
               "导言。\n"
               "****\n"
               "**高等爆裂哑火（Violent Misfire, Greater）**  \n"
               "正文内容。\n")
        items = run(raw, s6_shape="entry_line",
                    format_cluster_hint="s6_large_aggregate")
        assert items[0]["title"] == "废土武器Wasteland Weapons"
        assert items[1]["title"] == "高等爆裂哑火（Violent Misfire, Greater）"
        assert "**" not in items[1]["title"]

    def test_translator_closed_field_line(self):
        """`**译者**：**四月******` 闭壳字段形态 → normalize 剥除
        （page_517/601 BBS 帖头译者行，原正则要求 `译者` 后直接冒号，
        闭壳星在冒号前 → 全不匹配）"""
        raw = "**译者**：**四月******\n\n**正文节**\n\n内容。\n"
        items = run(raw)
        assert items[0]["title"] == "正文节"
        assert "译者" not in items[0]["text"]

    def test_translator_bare_open_line(self):
        """`**译者：旅法师 ` 开星不闭形态 → 整行剥除（page_646，
        跨行闭壳 `紫渊**` 在下行——剥行首译者字段行即可）"""
        raw = "**译者：旅法师 \n紫渊**\n\n**正文节**\n\n内容。\n"
        items = run(raw)
        assert all("译者" not in it["title"] for it in items)
        assert all("译者" not in it["text"] for it in items)

    def test_orphan_url_tail_star_prefix(self):
        """`**](http://...)` 星壳前缀孤立链接残渣行 → normalize 剥除
        （page_322 形态：`**[原文链接](url)` 被剥文本部分后残留）"""
        raw = "**正常节**\n\n正文内容。\n\n**](http://45.79.87.129/bbs/?topic=81394.0)  \n\n下一节。\n"
        items = run(raw)
        assert all("](http" not in it["title"] for it in items)
        assert "](http" not in "".join(it["text"] for it in items)

    def test_haunt_translator_note_line(self):
        """作祟形态 `**（译注：…）**` 行 → 并入所属节不独立成节（作祟汇总
        ×4：haunt 分支「闭壳中英括号标题」规则把含 `（`+拉丁（.jpg/dm）的
        译注行误判为标题）"""
        raw = ("**作祟：孤寂\n"
               "**（译注：译者不确定圣化之地指的是否是【祝圣术】（consecrate），姑且先这么翻了.)**\n"
               "**摧毁**\n唯有神迹术可永久闭合裂隙。\n")
        items = run(raw, s6_shape="haunt",
                    format_cluster_hint="s6_large_aggregate")
        assert titles(items) == ["作祟：孤寂"]
        assert "译注" in items[0]["text"]

    def test_entry_line_cn_en_bracket_star_shell(self):
        """entry_line 星壳标题无尾 2 空格形态 `**高等爆裂哑火（Violent
        Misfire, Greater）**` → 剥壳（PotW：`_RE_CN_EN_BRACKET` 字符类不
        排除星 → `_bare_title_text` 括号截取含前导星壳）"""
        raw = ("废土武器Wasteland Weapons  \n"
               "导言。\n"
               "****\n"
               "**高等爆裂哑火（Violent Misfire, Greater）**\n"
               "正文内容。\n")
        items = run(raw, s6_shape="entry_line",
                    format_cluster_hint="s6_large_aggregate")
        assert items[1]["title"] == "高等爆裂哑火（Violent Misfire, Greater）"


# ============================================================
#  批次 C（KN215~218，2026-08-09）：泛词 title / 续N 命名 / 低语义碎片
# ============================================================


class TestBatchCFieldLabels:
    """词表扩展（C2，KN216）：泛词字段行并入所属节，不产出泛词 title
    chunk——「．」怪物特性列表 / 战策 / 格式 / 咒字环位 / stat 缩写 /
    王国建设地形 / 魔宠环境 等 1172 个低语义碎片根因"""

    def test_dot_feature_line_merged(self):
        """「．」怪物特性列表行（page_300 `**．** d8 生命骰。`）并入所属
        节——列表项标记无语义，不产出 title=「．」chunk"""
        raw = ("**怪物类别**\n\n"
               "**．** d8 生命骰。\n\n"
               "**．** BAB 等于总 HD 的 3/4。")
        items = run(raw)
        assert titles(items) == ["怪物类别"]
        assert "**．** d8 生命骰。" in items[0]["text"]

    def test_tactics_field_merged(self):
        """战策（page_651 职业变体）字段行并入所属节"""
        raw = "**职业变体**\n\n**战策** 你的战策让你更灵活。\n\n正文。"
        items = run(raw)
        assert titles(items) == ["职业变体"]

    def test_ring_fields_merged(self):
        """环位 / 1环~6环（page_597/602 咒字法术列表）字段行并入所属节；
        `1环法术 (1st Level)` 真标题（标签含「法术」）不受影响"""
        raw = ("**咒字列表**\n\n"
               "**环位** 1环\n\n"
               "**1环** 治疗轻伤（Cure Light Wounds）\n\n"
               "**1环法术 (1st Level)**\n\n正文。")
        items = run(raw)
        assert titles(items) == ["咒字列表", "1环法术 (1st Level)"]

    def test_stat_abbrev_fields_merged(self):
        """AC/HP/XP/BAB 缩写 stat 字段并入所属节"""
        raw = "**物品**\n\n**AC** 10\n\n**HP** 15\n\n**BAB** +5"
        items = run(raw)
        assert titles(items) == ["物品"]

    def test_terrain_field_merged(self):
        """地形字段行（page_517 王国建设 `**地形**：…`）并入所属节"""
        raw = ("**建筑**\n\n"
               "**地形**：一端必须为丘陵或山脉地块；可以穿过任意类型的地块。")
        items = run(raw)
        assert titles(items) == ["建筑"]

    def test_env_org_field_merged(self):
        """环境/组织（魔宠 stat `**环境**：任意城市。`）并入所属节"""
        raw = "**新魔宠**\n\n**环境**：任意城市。\n\n**组织**：单独。"
        items = run(raw)
        assert titles(items) == ["新魔宠"]

    def test_open_star_field_closed_and_merged(self):
        """开壳不闭字段行（`**效果 \n`）判定层兼容（_RE_FIELD_LINE_OPEN）
        并入所属节——作祟/神祇 stat 字段（`**效果 ` / `**基础 ` 形态，词表
        有词但闭壳正则匹配不了的根因）。文本原样保留（判定层不改写——全
        局补闭壳会破坏跨行名字行/表格行拼接的原文形态）"""
        raw = "**作祟条目**\n\n**效果 \n触发：位置型\n\n正文。"
        items = run(raw)
        assert titles(items) == ["作祟条目"]
        assert "**效果 " in items[0]["text"]

    def test_real_attr_title_untouched(self):
        """真标题不受词表扩展误伤：「力量」（page_240 属性条目名行）仍是
        独立节标题——词表锚定只并入字段行，属性条目/疾病名/领域节标题
        （力量/步骤/健康/时间/魔法/奖励）均不在词表"""
        raw = ("**力量**：力量的临时增加给予你基于力量的技能以加值。\n\n"
               "**敏捷**：敏捷的临时增加给予你基于敏捷的技能以加值。")
        items = run(raw)
        assert titles(items) == ["力量", "敏捷"]

    def test_step_title_untouched(self):
        """「步骤」（page_1125 构建怪物）真标题不受影响——连续星壳标题行
        `**步骤** **1：设定怪物**` 仍为独立节（title 截断为「步骤」是
        既有行为，KN 登记 P3）"""
        raw = ("**步骤** **1：设定怪物** **(Plan** **the** **Monster)**\n\n"
               "正文。")
        items = run(raw)
        assert items[0]["title"] == "步骤"

    def test_closed_star_line_untouched(self):
        """补闭壳不误伤闭壳行：`**注能**`（已闭壳）保持原形态（行内第二
        个星使正则不匹配）"""
        raw = "**注能**\n\n正文。"
        items = run(raw)
        assert items[0]["title"] == "注能"

    def test_haunt_paren_field_merged(self):
        """作祟 stat 字段带英文括号（C4a，`**挑战等级（CR）** 2`）剥括号
        后缀后词表判定并入——作祟汇总不再拆出 37 片「挑战等级（CR）」"""
        raw = ("**血手印（Bloody Handprints）**\n\n"
               "**挑战等级（CR）** 2：**经验值** 600（XP 600）\n\n"
               "**施法者等级** 3级（3rd）")
        items = run(raw, s6_shape="haunt",
                    format_cluster_hint="s6_large_aggregate")
        assert titles(items) == ["血手印（Bloody Handprints）"]
        assert "挑战等级（CR）" in items[0]["text"]

    def test_benefit_track_field_merged(self):
        """作祟「增益效果（Benefit）」（C4b 词表补词）并入所属节"""
        raw = ("**变换的季节（Shifting Seasons）**\n\n"
               "**增益效果（Benefit）** 1点声望\n\n"
               "**病程（Track）** 1天")
        items = run(raw, s6_shape="haunt",
                    format_cluster_hint="s6_large_aggregate")
        assert titles(items) == ["变换的季节（Shifting Seasons）"]

    def test_empty_table_row_merged(self):
        """空表格行（C1，`|  |` page_279 范例陷阱续N 家族）并入前段，不
        独立成段"""
        rows = "\n".join(f"| 行{i} | " + "甲" * 80 + " |" for i in range(60))
        raw = f"**大节标题**\n\n{rows}\n|  |\n| 尾行 |"
        items = run(raw)
        assert len(items) >= 2
        assert not any(it["text"].strip() == "|  |" for it in items)


class TestBatchCContName:
    """续N title 语义化（C3，KN217）：表格行续块 title 取表格行首列条目
    名——1359 个「原title（续N）」中 1262 表格行续块（大节含表超限后
    行级续拆）从无差别续标语义化为条目名"""

    def test_oversize_table_cont_name_first_col(self):
        """超限表格节 → 续块 title = 续块首行表格行首列（`| 第N行 | …`）"""
        rows = "\n".join(f"| 第{i}行 | " + "甲" * 40 + " |" for i in range(150))
        raw = f"**武器表**\n\n| 名称 | 价格 |\n| --- |\n{rows}"
        items = run(raw)
        assert items[0]["title"] == "武器表"
        cont = [it for it in items[1:] if "续" in it["title"]]
        assert cont, "应有续块"
        for it in cont:
            first = it["text"].split("\n", 1)[0].lstrip()
            parts = first.strip().strip("|").split("|") \
                if first.startswith("|") else [""]
            head = parts[0].strip() if parts else ""
            assert it["title"].startswith(head), (it["title"], head)
