"""
test_skill_format.py — 技能格式解析 TDD 测试（test_seeds.jsonl 驱动）

数据源：vectorizer/exploration/skill/test_seeds.jsonl（14 条：10 positive + 4 negative）
驱动方：技能模块 M3 TDD 批次 A（formats/skill.py）
断言口径：SkillFormat.normalize → promote → split_into_items 产出的 item dict：
  type（skill/task/note/sub/ui/intro/index）/ skill_name / english_name /
  key_ability / trained_only / armor_penalty / sub_specialty / check / dc_table /
  action / retry / special / text / format_cluster
"""

import json
import re
from pathlib import Path

from vectorizer.formats.skill import SkillFormat

SEEDS_PATH = Path(__file__).parent.parent / "exploration" / "skill" / "test_seeds.jsonl"


def load_seeds():
    with open(SEEDS_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


SEEDS = load_seeds()


def run(raw: str, source_name: str = "seed") -> list:
    """SkillFormat 全链：normalize → promote → split"""
    fmt = SkillFormat()
    text = fmt.normalize(raw)
    text = fmt.promote(text)
    return fmt.split_into_items(text, source_name=source_name)


def by_type(items: list, typ: str) -> list:
    return [it for it in items if it.get("type") == typ]


class TestSkillSeeds:
    """14 条 test_seeds 逐条断言"""

    # ---------- positive ----------

    def test_seed_00_s1_full_page(self):
        """[0] S1 CRB 技能页全结构：主条目 + 任务 + 速查"""
        items = run(SEEDS[0]["raw_snippet"])
        skills = by_type(items, "skill")
        assert len(skills) == 1, f"应产 1 个主条目，实际 {len(skills)}"
        s = skills[0]
        assert s["skill_name"] == "医疗"
        assert s["english_name"] == "Heal"
        assert s["key_ability"] == "感知"
        assert s["trained_only"] is False
        assert s["armor_penalty"] is False
        # 检定字段（含行内 DC 值）
        assert "医疗技能检定的DC" in s["check"]
        # DC 表双写：主条目 dc_table 保真
        tasks = [(r["task"], r["dc"]) for r in s["dc_table"]]
        assert ("急救", "15") in tasks and ("长期护理", "15") in tasks
        # 任务 chunk
        t = by_type(items, "task")
        assert len(t) == 1 and t[0]["name"] == "急救"
        assert t[0]["dc"] == "15"  # DC 双写：任务自包含
        assert "濒死的生物" in t[0]["text"]
        # 主条目 tasks 摘要列表（决策 1 双级结构，与任务 chunk 同源）
        assert len(s["tasks"]) == 1 and s["tasks"][0]["name"] == "急救"
        assert s["tasks"][0]["dc"] == "15"
        # 速查块 → note（不产 task）
        notes = by_type(items, "note")
        assert len(notes) == 1 and notes[0]["name"] == "出血"
        assert notes[0]["name_en"] == "Bleed"
        assert "受到出血伤害的生物" in notes[0]["text"]

    def test_seed_01_title_armor_penalty(self):
        """[1] S1 标题后缀：防具检定减值"""
        items = run(SEEDS[1]["raw_snippet"])
        s = by_type(items, "skill")[0]
        assert s["skill_name"] == "特技"
        assert s["english_name"] == "Acrobatics"
        assert s["key_ability"] == "敏捷"
        assert s["armor_penalty"] is True
        assert s["trained_only"] is False

    def test_seed_02_title_dual_suffix(self):
        """[2] S1 标题双后缀 + 检定正文跨行重组"""
        items = run(SEEDS[2]["raw_snippet"])
        s = by_type(items, "skill")[0]
        assert s["skill_name"] == "解除装置"
        assert s["english_name"] == "Disable Device"
        assert s["armor_penalty"] is True
        assert s["trained_only"] is True
        # 跨行重组：'低于DC 5点以上' 原断在 'DC ' 后，重组为带空格连续串
        assert "低于DC 5点以上" in s["check"]

    def test_seed_03_title_editor_note(self):
        """[3] S1 标题尾缀【编注】剥除，不进名称"""
        items = run(SEEDS[3]["raw_snippet"])
        s = by_type(items, "skill")[0]
        assert s["skill_name"] == "骑术"
        assert s["english_name"] == "Ride"
        assert "编注" not in s["skill_name"]
        assert "编注" not in s["text"]

    def test_seed_04_s2_no_task(self):
        """[4] S2 无任务小节页：仅主条目，字段技能级"""
        items = run(SEEDS[4]["raw_snippet"])
        assert len(by_type(items, "task")) == 0, "估价页无任务小节，不得产 task"
        s = by_type(items, "skill")[0]
        assert s["skill_name"] == "估价"
        assert s["english_name"] == "Appraise"
        assert s["key_ability"] == "智力"
        # 检定跨行重组：'DC 20的估价检定' 原断在 'DC ' 后，重组为带空格连续串
        assert "DC 20的估价检定" in s["check"]
        assert "标准动作" in s["action"]
        assert "多次估价检定只能获得同样的结果" in s["retry"]

    def test_seed_05_s3_sub_specialty(self):
        """[5] S3 子项列表：sub_specialty + 每子类 sub item（含断行英文名）"""
        items = run(SEEDS[5]["raw_snippet"])
        s = by_type(items, "skill")[0]
        assert s["skill_name"] == "知识"
        assert s["english_name"] == "Knowledge"
        assert s["trained_only"] is True
        assert s["sub_specialty"] == ["奥秘", "地城", "工程", "地理"]
        subs = by_type(items, "sub")
        assert len(subs) == 4
        geo = next(x for x in subs if x["name"] == "地理")
        assert geo["name_en"] == "Geography"  # 断行英文名重组
        assert "地形地貌" in geo["text"]

    def test_seed_06_s4_text_crlf(self):
        """[6] S4 UI 文本模式：CRLF 断行重组 + 小节识别"""
        items = run(SEEDS[6]["raw_snippet"])
        uis = by_type(items, "ui")
        assert len(uis) == 1, "UI 页产 1 个 ui item"
        u = uis[0]
        assert u["skill_name"] == "唬骗"
        assert u["english_name"] == "Bluff"
        # 小节：说谎（断行英文名 Lying 独立行重组）
        names = [x["name"] for x in u["sections"]]
        assert "说谎" in names
        assert "唬骗并不是万应锭" in names

    def test_seed_07_s4_star(self):
        """[7] S4 UI 星壳模式：**标题跨行 + 【编注】剥除"""
        items = run(SEEDS[7]["raw_snippet"])
        uis = by_type(items, "ui")
        assert len(uis) == 1
        u = uis[0]
        assert u["title"] == "冲突情景中的技能运用"
        assert u["title_en"] == "Skills in Conflict"
        assert "编注" not in u["text"]

    def test_seed_08_s4_broken_title(self):
        """[8] S4 UI 断行标题：中文行+英文行分离重组"""
        items = run(SEEDS[8]["raw_snippet"])
        uis = by_type(items, "ui")
        assert len(uis) == 1
        u = uis[0]
        assert u["skill_name"] == "威吓"
        assert u["english_name"] == "Intimidate"

    def test_seed_09_s5_language_index(self):
        """[9] S5 语言汇总：中文 (English) 行首模式 → index item"""
        items = run(SEEDS[9]["raw_snippet"])
        idx = by_type(items, "index")
        assert len(idx) == 1
        it = idx[0]
        assert it["name"] == "通用语"
        assert it["name_en"] == "Common"
        assert "塔尔多语" in it["text"]

    def test_seed_14_s5_language_broken_variants(self):
        """[14] S5 语言汇总跨行变体：全角名称跨行 / 英文名独立行 / 冒号后空描述"""
        items = run(SEEDS[14]["raw_snippet"])
        idx = by_type(items, "index")
        by_name = {it["name"]: it for it in idx}
        assert "古奥斯利昂语" in by_name, "全角名称跨行条目不得丢失"
        assert by_name["古奥斯利昂语"]["name_en"] == "Ancient Osiriani"  # 跨行重组
        assert "现代奥斯利昂语的前身" in by_name["古奥斯利昂语"]["text"]
        assert by_name["兽人语"]["name_en"] == "Orc"  # CF 形态 + 使用者行
        assert "兽人和半兽人" in by_name["兽人语"]["text"]
        assert by_name["狩狼人"]["name_en"] == "Rougarou"  # 英文名独立行并入
        assert by_name["轮回者语"]["name_en"] == "Samsaran"
        assert by_name["轮回者语"]["text"], "冒号后空描述应下行兜底"

    def test_seed_16_animal_trick_list(self):
        """[16] S1 驯养动物技巧列表：l 前缀 + **任务 (DC xx)**: 半角冒号空 + 下行正文

        技巧列表（攻击/过来…）与 S3 知识学科形态同前缀（l 行）但属任务：
        标题行必须重置 pending_sub，否则首行正文被子项分支吞掉（text 空）；
        任务名须剥除 (DC xx) 尾缀（dc 进 dc 字段，决策 3 双写前提）。
        """
        items = run(SEEDS[16]["raw_snippet"])
        assert by_type(items, "sub") == [], "技巧列表不得产 sub（l 前缀是列表标记非 S3 子项）"
        t = {x["name"]: x for x in by_type(items, "task")}
        assert "攻击" in t and "教授动物一个技巧" in t
        assert t["攻击"]["dc"] == "20", "DC 应从标题尾缀 (DC 20) 提取"
        assert "动物开始攻击" in t["攻击"]["text"], "冒号后空任务应吞下行正文"

    def test_seed_17_dirty_mixed_lang_line(self):
        """[17] 负向：描述+条目重复合并的脏行不得产垃圾条目

        格拉利昂语言汇总 L151（HTML 转换重复产物）：「描述。天狗语（Tengu）:
        描述」整行——B 形态组1 会吞入前导描述句 → 组1 含句内标点即跳过，
        防垃圾条目名（昆莱的官方语言…天狗语）。
        """
        items = run(SEEDS[17]["raw_snippet"])
        names = [it["name"] for it in by_type(items, "index")]
        assert not any("昆莱" in n for n in names), "前导描述不得混入条目名"
        assert "天狗语" in names, "真条目保留"

    # ---------- negative ----------

    def test_seed_10_field_titles_no_task(self):
        """[10] 负向：字段级标题（**检定**：）与 DC 表行不产任务"""
        items = run(SEEDS[10]["raw_snippet"])
        assert by_type(items, "task") == [], "字段级标题不得产 task"
        # 主条目 dc_table 由 DC 表解析产出（切片 L9~L19 含全部 6 行）
        s = by_type(items, "skill")
        assert len(s) == 1 and len(s[0]["dc_table"]) == 6

    def test_seed_11_note_not_task(self):
        """[11] 负向：任务小节产 task，速查块产 note 不产 task"""
        items = run(SEEDS[11]["raw_snippet"])
        t = by_type(items, "task")
        n = by_type(items, "note")
        assert len(t) == 1 and t[0]["name"] == "急救"
        assert len(n) == 1 and n[0]["name"] == "出血"
        assert len(t) == 1, "速查块不得产 task"

    def test_seed_12_ui_not_crb(self):
        """[12] 负向：UI 页不误判为 CRB 技能页（无 ** 星壳主标题）"""
        items = run(SEEDS[12]["raw_snippet"])
        assert by_type(items, "skill") == [], "UI 页不得产 type=skill"
        assert len(by_type(items, "ui")) == 1

    def test_seed_13_bare_para_no_item(self):
        """[13] 负向：描述段（无标题裸段）不产条目"""
        assert run(SEEDS[13]["raw_snippet"]) == []

    def test_seed_20_intro_star_broken_title(self):
        """[20] S6 导言逐字加粗残留标题（page_162）：剥星壳重组 title/title_en

        **技能****详****述**** (Skill****s Descriptions****)**（HTML 逐字加粗
        残留跨 3 行）——旧 _RE_INTRO_TITLE 的 `[^*]+?` 在首个 `**` 处锚死，
        标题空 → 空 title chunk。修复：标题行剥 `*+` 后按「中文 (English)」
        形态重组。
        """
        # S6 分支按 source_name 判定（split_into_items 对 page_161/162 硬编码），
        # seed 传入 page_162 名触发
        items = run(SEEDS[19]["raw_snippet"], source_name="page_162.md")
        intros = by_type(items, "intro")
        assert len(intros) == 1, f"应产 1 个 intro，实际 {len(intros)}"
        it = intros[0]
        assert it["title"] == "技能详述", f"title 应重组为技能详述，实际 {it['title']!r}"
        assert it["title_en"] == "Skills Descriptions", \
            f"title_en 应重组为 Skills Descriptions，实际 {it['title_en']!r}"
        assert "这部份描述了" in it["text"], "导言正文应保留"

    def test_seed_19_editor_note_lang_list(self):
        """[19] 编注块后任务标题 + 语言列表：跨行星壳不吞、任务切出、列表入主条目

        page_182 语言学尾部：编注块 2 后紧跟「学习一门语言」任务标题 + 语言列表
        （深渊语…）。编注正则尾 `\s*\*{0,4}` 曾跨行贪婪吃掉下一行开壳星 → 学习行
        粘入制作任务 text（任务整体丢失）；语言列表使用者行粘入 cur_task（污染）。
        修复：编注尾 `[ \t]*` 不跨行；语言列表段切出任务上下文并保留在主条目
        description（决策 8）。
        """
        items = run(SEEDS[18]["raw_snippet"])
        assert by_type(items, "sub") == [], "语言列表不得产 sub"
        t = {x["name"]: x for x in by_type(items, "task")}
        assert "制作或识破伪造文书" in t and "学习一门语言" in t, \
            f"两个任务都应产出，实际 {list(t)}"
        assert "每当你在语言学技能上获得等级" in t["学习一门语言"]["text"], \
            "学习任务 text 应含正文（编注正则不得跨行吃开壳星）"
        assert "学习一门语言" not in t["制作或识破伪造文书"]["text"], \
            "制作任务 text 不得粘连学习任务标题"
        assert "深渊语" not in t["制作或识破伪造文书"]["text"], \
            "制作任务 text 不得被语言列表污染"
        s = by_type(items, "skill")[0]
        assert "深渊语" in s["description"], "语言列表应保留在主条目 description（决策 8）"

    def test_seed_15_language_list_no_sub(self):
        """[15] 负向：语言学正文尾部语言列表（深渊语…）不产 sub 子项"""
        items = run(SEEDS[15]["raw_snippet"])
        assert by_type(items, "sub") == [], "语言列表子项不得产 sub（语言汇总页 index 权威）"
        s = by_type(items, "skill")
        assert len(s) == 1
        # 语言列表保留在主条目 description（formats 层主条目正文字段；
        # processor 组装 text 时回退 description）
        assert "深渊语" in s[0]["description"], "语言列表应保留在主条目正文"
        assert s[0]["sub_specialty"] == [], "语言列表不得进 sub_specialty"
        t = by_type(items, "task")
        assert len(t) == 1 and t[0]["name"] == "制作或识破伪造文书", "真任务小节不受影响"

    # ---------- S7 Unchained 批次 B（page_647/648/649）----------

    def test_seed_21_s7_skill_unlocks(self):
        """[21] S7 技能解放页（page_648）：跨行星壳主标题 + 裸标题 + 四档并入

        形态：页首跨行星壳主标题 **技能解放（Skill \\nUnlocks）（闭壳缺失）、
        裸标题「标志性技能（普通）」+ 先决条件/好处正文、星壳技能条目
        **特技动作（Acrobatics）** + 四档 **N点**：并入（count_basis 口径
        page_648 = 28：导言 + 标志性技能 + 26 技能，四档不分块）。
        """
        items = run(SEEDS[20]["raw_snippet"], source_name="page_648.md")
        rules = by_type(items, "rule")
        assert len(rules) >= 4, f"应产 导言/标志性技能/特技动作/估价 至少 4 个 rule，实际 {len(rules)}"
        by_title = {r["title"].strip(): r for r in rules}
        intro = by_title.get("技能解放")
        assert intro, f"跨行主标题应重组为导言 rule，实际标题 {list(by_title)}"
        assert intro["title_en"] == "Skill Unlocks"
        assert "随着角色在某项技能上投入5点" in intro["text"], "导言正文应并入"
        assert by_title["标志性技能"], "裸标题标志性技能（普通）应产 rule"
        assert "先决条件" in by_title["标志性技能"]["text"], "先决条件正文应并入"
        acro = by_title["特技动作"]
        assert acro["title_en"] == "Acrobatics"
        for n in ("5点", "10点", "15点", "20点"):
            assert n in acro["text"], f"四档 {n} 应并入技能 text"
        assert by_title["估价"], "估价条目应产出"
        assert not any("点" == t.strip()[-1] and t.strip()[:-1].isdigit() for t in by_title), \
            "四档 **N点** 不得新开 item"

    def test_seed_22_s7_crafting(self):
        """[22] S7 造物与专业替换页（page_647）：大节 + 字段并入 + 表 + 难度档 + 范例

        形态：跨行主标题、大节 **造物（Crafting）**、嵌套 **造物替换规则
        （Alternate Crafting Rules）**、技能标题 **工艺（智力）**（括号为属性
        非英文名）+ 斜体 *Craft (Int)* 行、字段 **检定（Check）**：并入、
        **表：工艺DC与进度价值** + 表格行、难度档 **极其简单（DC 5）** +
        范例条目 **炼金物品（Alchemical Items）**：。
        """
        items = run(SEEDS[21]["raw_snippet"], source_name="page_647.md")
        rules = by_type(items, "rule")
        by_title = {r["title"].strip(): r for r in rules}
        assert by_title["造物"]["title_en"] == "Crafting"
        assert by_title["造物替换规则"]["title_en"] == "Alternate Crafting Rules"
        craft = by_title.get("工艺")
        assert craft, f"工艺（智力）应产 rule，实际标题 {list(by_title)}"
        assert craft["title_en"] == "", "（智力）是属性非英文名，title_en 应为空"
        # 斜体英文行 *Craft (Int)* 断行并入（seed 不经 processor pre_normalize
        # 的 \r→空格 join，断言按断行两段；pipeline 全链后为连续串）
        assert "Craft" in craft["text"] and "(Int)" in craft["text"], \
            "斜体英文行应并入 text"
        # KN160：斜体星壳剥离（*Craft (Int)* → Craft (Int)），** 加粗不受影响
        assert "*Craft" not in craft["text"] and "(Int)*" not in craft["text"], \
            "KN160 斜体星壳 *Craft/(Int)* 应剥离"
        assert "检定" not in by_title, "字段 **检定（Check）**：应并入当前条目，不得新开"
        tbl = by_title.get("表：工艺DC与进度价值")
        assert tbl and tbl["title_en"] == "Crafting DCs and Progress Values"
        assert "| 制作难度" in tbl["text"], "表格行应并入表标题 item"
        assert by_title["极其简单"], "难度档（DC 5）应产 rule"
        alch = by_title.get("炼金物品")
        assert alch and alch["title_en"] == "Alchemical Items"
        assert "石膏" in alch["text"], "范例正文应并入"

    def test_seed_23_s7_gestalt(self):
        """[23] S7 混职系统页（page_649）：裸跨行主标题 + 单值行表 + 职业吸收

        形态：页首裸跨行主标题「混职系统（Variant \\nMulticlassing）」、
        裸表标题「表2-8：混职角色晋级」+ 单值行表格（无 | 竖线，每单元格
        一行）、裸小节「核心职业」、裸职业「野蛮人（Barbarian）」+ 星壳特性
        **狂暴（Rage）：**…**直觉闪避（Uncanny \\nDodge）：**（count_basis
        口径 page_649 = 23：导言 + 表 + 2 小节 + 19 职业，特性并入职业）。
        """
        items = run(SEEDS[22]["raw_snippet"], source_name="page_649.md")
        rules = by_type(items, "rule")
        by_title = {r["title"].strip(): r for r in rules}
        intro = by_title.get("混职系统")
        assert intro and intro["title_en"] == "Variant Multiclassing", \
            f"裸跨行主标题应重组为导言 rule，实际标题 {list(by_title)}"
        assert "在核心规则之下" in intro["text"], "导言正文应并入"
        tbl = by_title.get("表2-8：混职角色晋级")
        assert tbl, "表2-8 裸表标题应产 rule"
        assert "角色等级" in tbl["text"] and "专长" in tbl["text"], "单值行表格应并入表 item"
        assert "核心职业" in by_title, "裸小节标题应产 rule"
        barb = by_title.get("野蛮人")
        assert barb and barb["title_en"] == "Barbarian"
        assert "狂暴" in barb["text"] and "直觉闪避" in barb["text"], \
            "星壳特性应并入职业 item（吸收）"
        assert "狂暴" not in by_title, "特性标题不得新开 item"

    def test_seed_24_s8_giant_options(self):
        """[24] S8 巨人猎手新技能选项：GIANT-source 注释锚点 + 裸标题两行重组

        形态：GIANT-source 注释行开条目；标题 = 裸文本行「中文名+英文名粘连
        」（佯装无害Feign）+ 英文续行「Harmlessness（唬骗）」重组；字段流
        （检定：/特殊规则：/动作：/重试：）并入 text；`> 来源：` 行提取到
        source 字段（不产 item）；`****` 结尾孤行不产 item（count_basis
        口径 est 5 = 导言 1 + 4 条目）。
        """
        items = run(SEEDS[23]["raw_snippet"], source_name="巨人猎手手册_新技能选项.md")
        rules = by_type(items, "rule")
        by_title = {r["title"].strip(): r for r in rules}
        # 导言 + 4 条目
        assert len(rules) == 5, f"应 5 个 rule（导言+4 条目），实际 {len(rules)}: {list(by_title)}"
        intro = by_title.get("巨人猎手们的技能（Skill）新选项")
        assert intro, f"导言标题应保留整行（含（Skill）新选项），实际 {list(by_title)}"
        assert "巨人打交道的角色" in intro["text"], "导言正文应并入"
        # 佯装无害：粘连中文/英文分离 + 英文续行重组
        feign = by_title.get("佯装无害")
        assert feign and feign["title_en"] == "Feign Harmlessness", \
            f"两行标题应重组，实际 title_en={feign and feign.get('title_en')}"
        assert "检定：" in feign["text"] and "动作：" in feign["text"] and "重试：" in feign["text"], \
            "字段流应并入 text（不新开条目）"
        assert "巨人猎手手册" in (feign.get("source") or ""), "来源行应提取到 source"
        # 躲在生物身后：英文续行（隐匿）剥离，特殊规则并入
        hide = by_title.get("躲在生物身后")
        assert hide and hide["title_en"] == "Hide behind Creatures", \
            f"英文名两行重组，实际 {hide and hide.get('title_en')}"
        assert "特殊规则：" in hide["text"] and "Aware" in hide["text"], "特殊规则正文应并入"
        assert "威吓体型更大的生物" in by_title, "威吓条目应产"
        plant = by_title.get("植入想法")
        assert plant and plant["title_en"] == "Plant Notion", \
            f"植入想法英文重组，实际 {plant and plant.get('title_en')}"
        assert "（唬骗和交涉）" not in plant["title_en"], "技能归属括号不得进 title_en"
        assert not any(r["title"].strip() == "****" for r in rules), "结尾星号孤行不得产条目"
        assert not any("来源：" in r["title"] for r in rules), "来源行不得产条目"

    def test_seed_25_s9_potr(self):
        """[25] S9 河域子民新技能规则：复用 S7 形态（星壳 规则名：正文）
        + 纯中文短行小节标题；注释行剔除；来源行提取（不产 item）
        （count_basis 口径 est 3 = 生存策略小节 1 + 2 条规则）。
        """
        items = run(SEEDS[24]["raw_snippet"], source_name="河域子民PotR_新技能规则.md")
        rules = by_type(items, "rule")
        by_title = {r["title"].strip(): r for r in rules}
        assert len(rules) == 3, \
            f"应 3 个 rule（生存策略+2 规则），实际 {len(rules)}: {list(by_title)}"
        strat = by_title.get("生存策略")
        assert strat, f"纯中文短行小节应产标题，实际 {list(by_title)}"
        assert "河流周边冒险" in strat["text"], "导言正文应并入生存策略小节"
        catch = by_title.get("捕捉溪流中顺流而下的生物")
        assert catch, "星壳规则标题应产条目"
        assert "力量检定" in catch["text"] and "反射检定" in catch["text"], \
            "规则正文（含跨行重组）应并入"
        assert "河域子民" in (catch.get("source") or ""), "来源行应提取到 source"
        swing = by_title.get("摆荡飞跃")
        assert swing and "借机攻击" in swing["text"], "第二条规则应产条目"
        assert not any(r["text"].lstrip().startswith("<!--") for r in rules), \
            "注释行不得进入 text"
        assert not any("来源：" in r["title"] for r in rules), "来源行不得产条目"

    def test_seed_26_s9_occult_unlocks(self):
        """[26] S9 异能神秘技能解放页：跨行星壳主标题（导言）+ 开壳悬空
        `**` 行 + 断行标题重组 + 8 技能解放 + 字段/斜体引言/DC 表并入
        （count_basis 口径 est 10 = 导言 1 + 异能敏感 1 + 8 解放）。
        """
        items = run(SEEDS[25]["raw_snippet"], source_name="page_315.md")
        rules = by_type(items, "rule")
        by_title = {r["title"].strip(): r for r in rules}
        assert len(rules) == 10, \
            f"应 10 个 rule（导言+异能敏感+8 解放），实际 {len(rules)}: {list(by_title)}"
        intro = by_title.get("神秘技能解放")
        assert intro and intro["title_en"] == "Occult Skill Unlocks", \
            f"导言标题应中英拆离，实际 title_en={intro and intro.get('title_en')}"
        assert "可以施放异能法术的角色" in intro["text"], "导言正文（L10-15 裸文本）应并入导言"
        assert "意识交给精魂" not in intro["text"], \
            "扶乩条目的斜体引言（标题之后）不得并入页导言"
        sense = by_title.get("异能敏感")
        assert sense and sense["title_en"] == "Psychic Sensitivity", \
            f"裸标题两行英文应重组，实际 {sense and sense.get('title_en')}"
        assert "专长效果" in sense["text"], "专长效果字段应并入异能敏感"
        auto = by_title.get("语言学：扶乩")
        assert auto and auto["title_en"] == "Automatic Writing", \
            f"开壳悬空标题应重组，实际 {auto and auto.get('title_en')}"
        assert "技能检定" in auto["text"] and "动作：" in auto["text"] and "重试：" in auto["text"], \
            "技能检定/动作/重试字段应并入"
        for t in ("生存：探宝", "医疗：信念治疗", "交涉：催眠术",
                  "知识（神秘）：颅相学", "察言观色：算命", "估价：感灵",
                  "察觉：望气"):
            assert t in by_title, f"缺少解放条目 {t}，实际 {list(by_title)}"
        dowsing = by_title["生存：探宝"]
        assert dowsing["title_en"] == "Dowsing", \
            f"单行闭壳标题英文，实际 {dowsing['title_en']}"
        # KN160：整段斜体剥星（*可以…资源。* → 可以…资源。），** 加粗字段不受影响
        assert "*可以" not in dowsing["text"] and not dowsing["text"].rstrip().endswith("。*"), \
            "KN160 整段斜体行首/行尾星应剥离"
        phren = by_title["知识（神秘）：颅相学"]
        assert "15+生物HD*" not in phren["text"] and "15+生物HD" in phren["text"], \
            "KN160 脚注尾星 15+生物HD* 应剥离"
        aura = by_title["察觉：望气"]
        assert aura["title_en"] == "Read Aura", \
            f"跨行标题英文重组，实际 {aura['title_en']}"
        assert not any(r["title"].strip() in ("**", "x", "引用") for r in rules), \
            "星壳/乘号/引用行不得产条目"

    def test_seed_27_s9_technology(self):
        """[27] S9 科技世界技能页：行内连排形态——导言标题（技能 Skills）+
        4 条目标题嵌行尾/行中（属性括号不进 title_en）+ 斜体子项/行内字段并入
        （count_basis 口径 est 5 = 导言 1 + 手艺/解除装置/语言学/研究科技产品 4）。
        """
        items = run(SEEDS[26]["raw_snippet"], source_name="page_760.md")
        rules = by_type(items, "rule")
        by_title = {r["title"].strip(): r for r in rules}
        assert len(rules) == 5, \
            f"应 5 个 rule（导言+4 条目），实际 {len(rules)}: {list(by_title)}"
        intro = by_title.get("技能")
        assert intro and intro["title_en"] == "Skills", \
            f"导言标题应拆中英，实际 title_en={intro and intro.get('title_en')}"
        assert "不会因为需要接触高科技" in intro["text"], "导言正文应并入"
        craft = by_title.get("手艺")
        assert craft and craft["title_en"] == "", \
            f"属性括号不得进 title_en，实际 {craft and craft.get('title_en')}"
        assert "构装机械" in craft["text"], "手艺正文应并入"
        disable = by_title.get("解除装置")
        assert disable and disable["title_en"] == "", "解除装置属性括号不得进 title_en"
        assert "起爆器" in disable["text"] and "Arm Explosive" in disable["text"], \
            "斜体子项应保留在 text"
        assert "瘫痪电子锁或触发器" in disable["text"] and "E-pick" in disable["text"], \
            "混合壳子项应保留在 text"
        assert "特殊：" in disable["text"] and "时间：" in disable["text"], \
            "行内字段应并入（不产条目）"
        ling = by_title.get("语言学")
        assert ling and ling["title_en"] == "", "语言学属性括号不得进 title_en"
        assert "机械语：" in ling["text"] and "Androffan" in ling["text"], \
            "语言学正文与机械语字段应并入"
        research = by_title.get("研究科技产品")
        assert research and research["title_en"] == "", "研究科技产品为纯中文标题"
        assert "医疗：" in research["text"] and "知识（工程学）" in research["text"], \
            "研究科技产品字段应并入"
        assert not any(r["title"].strip().startswith("**") for r in rules), \
            "标题不得残留星壳"

    def test_seed_28_s10_equipment(self):
        """[28] S10 工具和技能工具包装备页：主段（裸标题导言 + 价格表/表注并入
        + 开壳星壳导言闭壳借位 + 断行物品标题 + CR 陷阱块独立条目）+ 初探段
        （行内连排 **标题****正文）+ 内海段（中英粘连导言 + 地区表格）+ 尾部
        重复段整段跳过（拍板 #9 段级去重：source 路径 = 本文件）。
        """
        items = run(SEEDS[27]["raw_snippet"], source_name="工具和技能工具包.md")
        eqs = by_type(items, "equipment")
        by_title = {it["title"].strip(): it for it in eqs}
        assert len(eqs) == 9, \
            f"应 9 个 equipment（导言+算盘+炼金台+狗熊夹+CR块+初探3+内海1），" \
            f"实际 {len(eqs)}: {list(by_title)}"
        # 主段导言：裸标题 + 价格表 + 表注 + 星壳导言（剥壳）合并为 1 条目
        intro = by_title["工具和技能工具包"]
        assert intro["title_en"] == "Tools and Skill Kits", \
            f"导言英文名，实际 {intro['title_en']}"
        assert "| 算盘（Abacus） | 2 gp | 2磅 |" in intro["text"], "价格表应并入导言"
        assert "为小型角色制造的这些物品重量" in intro["text"], "表注应并入导言"
        assert "这些道具涉及到了技能、工艺、和专业" in intro["text"], \
            "星壳导言正文（闭壳借位）应剥壳并入"
        assert "**这些道具" not in intro["text"], "星壳句子不得残留前导 **"
        # 断行物品标题重组 + 字段并入
        lab = by_title["便携式炼金术工作台"]
        assert lab["title_en"] == "Portable alchemist's lab", \
            f"断行英文全名重组，实际 {lab['title_en']}"
        assert "**价格**：75 GP；**重量**：20磅。" in lab["text"], "价格/重量字段应并入"
        # 图片行剔除
        assert not any("PathfinderSocietySymbol" in (it.get("text") or "") for it in eqs), \
            "![[图片]] 行不得并入正文"
        # CR 陷阱块独立条目（title 保留 CR 后缀区分同名物品）
        trap = by_title["狗熊夹 CR 1"]
        assert trap["title_en"] == "Bear trap", f"CR 块英文名，实际 {trap['title_en']}"
        assert "机械型陷阱" in trap["text"] and "触发器" in trap["text"], \
            "类型/触发器字段应并入"
        assert "近战攻击+10" in trap["text"], "效果正文应并入"
        assert "效果" in trap["text"], "孤行 **效果** 字段应并入"
        bear = by_title["狗熊夹"]
        assert bear["title_en"] == "Bear trap", "物品条目英文名"
        assert "20的力量检定" in bear["text"], "物品正文应并入"
        # 初探段：行内连排 + pending_source
        kit = by_title["渗透工具箱"]
        assert "价格：140gp" in kit["text"] and "这个工具箱对需要以渗透和窃听" in kit["text"], \
            "行内连排余文应剥壳并入正文"
        assert "初探探索者协会" in kit.get("source", ""), "来源行应挂渗透工具箱"
        assert by_title["工具箱"] and "尽管寻路仪是一名探索者" in by_title["工具箱"]["text"], \
            "初探导言（工具箱）应为独立条目"
        explorer = by_title["探索者工具箱"]
        assert "价格：12gp" in explorer["text"], "探索者工具箱条目"
        # 内海段：中英粘连导言拆离 + 地区表格并入
        sea = by_title["内海炼金工具箱"]
        assert sea["title_en"] == "INNER SEA ALCHEMY", f"内海导言英文名，实际 {sea['title_en']}"
        assert "贝尔克泽恩" in sea["text"] and "纽美利亚" in sea["text"], "地区表格应并入"
        assert "炼金术士" in sea["text"], "内海导言正文应并入"
        # 尾部重复段整段跳过：算盘在导言价格表（主段）→ 不得新增重复条目；
        # 鼓风机仅出现在尾部重复段 → 全库不得出现
        assert "鼓风机" not in by_title, f"尾部重复段不得产出条目: {list(by_title)}"
        assert not any("鼓风机" in (it.get("text") or "") for it in eqs), \
            "尾部重复段正文不得并入任何条目"

    def test_seed_29_s9_faq(self):
        """[29] S9 官方FAQ 问答流：星壳节标题（第 2 节跨行断行需 flat 拼接）
        + 主题名：问题　　答案（全角空格连排 + 80 字符硬断行）+ 中英条目混排
        + 同主题多问句（特技/顺势斩/重拳护符/盾击 ×2）+ 答案内冒号/译注不误开
        + 无锚英文问题并入上一条目（When I use a magic item → 单手持用双手武器）。
        """
        items = run(SEEDS[28]["raw_snippet"], source_name="page_837.md")
        rules = by_type(items, "rule")
        intros = by_type(items, "intro")
        assert len(intros) == 2, f"应 2 个节标题 intro，实际 {len(intros)}: {intros}"
        assert len(rules) == 39, \
            f"应 39 个 rule（段1 10 + 段2 29），实际 {len(rules)}"
        # 节标题：title 中文 + title_en 英文（跨行断行拼接完整），text 空
        head1 = [i for i in intros if "专长和技能" in i.get("title", "")][0]
        assert head1["title_en"] == "Feats and Skills", \
            f"节1 英文名，实际 {head1['title_en']}"
        head2 = [i for i in intros if "装备和魔法物品" in i.get("title", "")][0]
        assert head2["title_en"] == "Gear and Magic Items", \
            f"节2 跨行断行应拼接完整，实际 {head2['title_en']}"
        assert not intros[0].get("text", "").strip() and \
            not intros[1].get("text", "").strip(), "节标题 text 应为空"
        # 同主题多问句：同名条目各 2
        for dup in ("特技", "顺势斩", "重拳护符", "盾击"):
            n = sum(1 for r in rules if r.get("title", "").strip() == dup)
            assert n == 2, f"{dup} 应 2 个条目，实际 {n}"
        # 主题名清理：粘连前缀（右引号/答案段尾英文句点）剥除
        titles = {r.get("title", "").strip() for r in rules}
        assert "增强召唤" in titles and "顺势斩" in titles, \
            f"右引号前缀应剥除: {sorted(titles)[:8]}"
        assert "超魔法术" in titles, \
            "答案段尾英文句点粘连应剥除（damage reduction.超魔法术）"
        assert not any("damage reduction" in t for t in titles), \
            f"英文答案段尾残留不得进 title: {sorted(titles)[:10]}"
        # 英文条目：title=英文名（含多词形态），title_en=自身
        fl = [r for r in rules if r.get("title") == "Flight and Magical Flight"]
        assert fl and fl[0]["title_en"] == "Flight and Magical Flight", \
            f"英文条目 title_en 应同 title: {fl[:1]}"
        # 无锚英文问题并入上一条目（单手持用双手武器 text 含 ring of invisibility）
        one_hand = [r for r in rules if r.get("title") == "单手持用双手武器"]
        assert one_hand and "ring of invisibility" in one_hand[0].get("text", ""), \
            "无锚英文问题应并入单手持用双手武器"
        assert "reset the duration" in one_hand[0].get("text", ""), \
            "无锚英文问题答案应并入"
        # 问题/答案保真：中文条目含全角空格连排的问答原文
        pot = [r for r in rules if r.get("title") == "调制药剂"]
        assert pot and "提高5点DC" in pot[0].get("text", ""), \
            "调制药剂问题应保真（含全角空格连排的问答原文）"
        # 答案内冒号不误开（更正：/注意：/更新：/译注均在 text 内）
        all_text = " ".join(r.get("text", "") for r in rules)
        assert "更正：" in all_text and "注意：" in all_text, "答案内冒号应并入正文"
        assert "译注" not in "".join(t for t in titles), "译注块不得产条目"

    def test_seed_30_swim_semicolon_suffix(self):
        """[30] KN158 回归：游泳标题关键属性分号形态（源数据已 `，`→`; `）
        ——`**游泳 (Swim) (力量; 防具检定减值)**` 须拆出
        key_ability=力量 / armor_penalty=True / trained_only=False
        （其余 8 个【减】技能同形态，防全角逗号混入回归）。
        """
        items = run(SEEDS[29]["raw_snippet"])
        s = by_type(items, "skill")[0]
        assert s["skill_name"] == "游泳"
        assert s["english_name"] == "Swim"
        assert s["key_ability"] == "力量"
        assert s["armor_penalty"] is True
        assert s["trained_only"] is False
