"""formats/skill.py — 技能格式解析（M3 TDD 批次 A）

格式簇（勘探 S1~S10，M3 覆盖 S1/S2/S3/S4/S5/S6）：
  S1  CRB 任务小节型：**中文 (English) (属性[; 后缀])** + 描述 + **检定**： +
      DC 表 + 任务小节 + 【速查】块 + 技能级字段（动作/重试/特殊…）
  S2  无任务小节型（估价 page_169 等）：字段直接跟在检定描述后
  S3  子项列表型（知识/表演）：`l  ` + **子项 (English)** + (描述)，
      英文名可能断行（**地理 / (Geography)**）
  S4  UI 散文补充页（8 页，三种标题形态：文本双空格 / 星壳 / 断行）：
      源文件 CRLF 软换行（\r 即行内断点，normalize 重组成空格后标题恢复）
  S5  语言汇总（格拉利昂语言汇总）：中文 (English)(别名) + 描述行
  S6  导言页（page_161/162）：URL + 译者行 + 星壳标题 + 小节

条目 dict（processor 层按 type 映射 component_type）：
  skill → component_type=skill；task → skill_task；note → skill_note
  sub → skill_task（决策 7 子类独立 chunk）；ui → ui_supplement
  intro → skill_intro；index → skill_index
"""
import re

from vectorizer.formats.base import BaseFormat

# ---------------------------------------------------------------------------
# normalize 正则链
# ---------------------------------------------------------------------------

# 行首 URL（含整理者后缀）：[http://…](http://…) 整理者：…
_RE_URL_LINE = re.compile(r"^\[https?://[^\]]*\]\(https?://[^)]*\)[^\n]*$", re.M)
# 译者行：**译者：**lichzeta**，佐鸟カナコ**
_RE_TRANSLATOR_LINE = re.compile(r"^\*\*译者[:：][^\n]*$", re.M)
# 行内链接：[**唬骗**](http://…) → 空
_RE_INLINE_LINK = re.compile(r"\[[^\]]*\]\(https?://[^)]*\)")
# 【编注：…】/【编注:…】块（可跨行；块内无】；尾壳 **** 一并剥）
# 编注尾只吃空格/tab 不吃换行：`\s*` 会跨行贪婪吞掉下一行开壳 `**`
#（page_182「学习一门语言」标题开壳被吃 → 任务整行退化为普通文本并入前任务）
_RE_EDITOR_NOTE = re.compile(r"【编注[:：][^】]*】[ \t]*\*{0,4}")
# 斜体星壳（CHM 转换 <I> → *text*，行首/行尾单星；KN160，专长
# KN089/090 星壳家族同源）：`*Craft`/`(Int)*` 斜体标题断行、整段
# `*可以…资源。*` 斜体引言、脚注尾星 `15+生物HD*`。
# ** 加粗（标题/字段）为双星，`(?!\*)`/`(?<!\*)` 守卫不误伤。
_RE_ITALIC_LEAD = re.compile(r"^[ \t]*\*(?!\*)", re.M)
_RE_ITALIC_TAIL = re.compile(r"(?<!\*)\*[ \t]*$", re.M)

# ---------------------------------------------------------------------------
# split 正则链（CRB 页）
# ---------------------------------------------------------------------------

# 主标题：**中文 (English[, 又译中文]) (属性[; 后缀...])**
_RE_MAIN_TITLE = re.compile(r"^\*\*(.+?) \((.*?)\) \((.*?)\)\*\*")
# 英文名又译后缀：', 又译脱逃术' → 剥
_RE_EN_ALT = re.compile(r",\s*又译.*$")
# 字段级标题：**检定**：/**动作**：/**重试**：/**特殊**：/**未受训**：/**限制**：
# 标签 → 主条目 dict 键映射（决策 4：按正文实际位置归属）
_FIELD_KEYS = {"检定": "check", "动作": "action", "重试": "retry",
               "特殊": "special", "未受训": "untrained", "限制": "restriction"}
_RE_FIELD = re.compile(r"^\*\*(检定|动作|重试|特殊|未受训|限制)\*\*[:：]\s*(.*)$")
# 任务小节标题：**急救**：正文（名字非字段名）。
# (DC xx) 尾缀可选项：驯养动物技巧列表形态（**攻击 (DC 20)**: ），
# DC 必须进 dc 字段（决策 3 双写前提：任务名纯净才能与 DC 表行匹配）
_RE_TASK = re.compile(r"^\*\*([^*]+?)(?: \((DC \d+)\))?\*\*[:：]\s*(.*)$")
# 速查块：【速查】**出血 (Bleed)**: 正文
_RE_QUICK_REF = re.compile(r"^【速查】\*\*(.+?)(?: \((.*?)\))?\*\*[:：]\s*(.*)$")
# 子项列表标记行：'l  '（知识/表演子项）
_RE_LIST_MARK = re.compile(r"^l\s*$")
# 子项标题：**奥秘 (Arcana)**  （跨行英文名时无闭合星壳）
_RE_SUB_OPEN = re.compile(r"^\*\*(.+?)(?: \((.*?)\))?\*\*\s*$")
_RE_SUB_OPEN_BROKEN = re.compile(r"^\*\*(.+?)\s*$")  # **地理 （下一行补 (Geography)**）
_RE_SUB_TAIL = re.compile(r"^\(([^)]*)\)\*\*\s*$")  # (Geography)**
# 子项描述行：(古代的神秘知识；…) / (地形地貌、气候和人文的记录)
_RE_SUB_DESC = re.compile(r"^\((.*)\)[:：]?\s*(.*)$")
# DC 表数据行与表尾注（| * 跨行注 / | ※1 注）
_RE_TABLE_ROW = re.compile(r"^\|(.+)\|$")
_RE_TABLE_FOOTNOTE = re.compile(r"^\|\s*[*※]")

# ---------------------------------------------------------------------------
# split 正则链（S4 UI / S5 语言 / S6 导言）
# ---------------------------------------------------------------------------

# UI 星壳标题：**冲突情景中的技能运用 Skills in Conflict**（join 重组后无 $ 锚，
# 正文可能紧随其后；组间 1~3 空格兼容断行 join 双空格）
_RE_UI_STAR = re.compile(r"^\*\*(.+?) {1,3}([A-Za-z][A-Za-z ]*?)\*\*")
# UI 文本/断行标题：唬骗 Bluff   （中文 英文 双空格，normalize 重组后）
_RE_UI_TEXT = re.compile(r"^([一-鿿]+) {1,3}([A-Za-z][A-Za-z ]*?) {2}")
# UI 行内嵌小节：前缀双空格段落分隔 + 中文（English）：正文。
# 前缀锚 {2,} 排除 prose 括注（'技能（It Is…）：' 在段落中间无双空格）；
# 名称限长 12 字（实测最长 9 字，'唬骗检定的进行频率'）；中文与（间兼容空格
_RE_UI_SECTION = re.compile(
    r"((?:^| {2,})[一-鿿][^（）\n]{1,12}?) *（([A-Za-z][A-Za-z ,'()]*?)）[:：]")
# UI 断行英文名小节：...情况。说谎 Lying  如果你…（中文 英文 双空格；
# join 后中文与英文间可能 1~3 空格）
_RE_UI_SECTION_BROKEN = re.compile(r"([一-鿿]{1,8}) {1,3}([A-Za-z][A-Za-z ,'()]{1,30}) {2}")
# 语言条目 A：通用语 (Common)(塔尔多语，Taldane)  + 下一行 (描述)
_RE_LANG_A = re.compile(r"^([^（）()]+) \(([A-Za-z][^)]*)\)(?:\(([^)]*)\))?\s*$")
_RE_LANG_A_DESC = re.compile(r"^\(([^)]*)\)[:：]?\s*(.*)$")
# 语言条目 B：哈利特语（Hallit）：描述（全角带冒号）
_RE_LANG_B = re.compile(r"^([^（）()]+)（([A-Za-z][^）]*)）[:：](.*)$")
# 语言条目 C/F（半角无空格名称行）：火族语(Ignan) / 卡萨达(Kasatha)语
# （行尾；组3 中文尾可空；描述/使用者括号在下一行）
_RE_LANG_CF = re.compile(r"^([一-鿿]+)\(([A-Za-z][A-Za-z ]*)\)([一-鿿]*)\s*$")
# 语言条目 D（半角单行）：德鲁伊语(Druidic)(仅德鲁伊和变形者)：描述
_RE_LANG_D = re.compile(r"^([一-鿿]+)\(([A-Za-z][A-Za-z ]*)\)(?:\(([^)]*)\))?[:：]\s*(.*)$")
# 语言条目 E（全角无冒号）：暗影语（Shadowtongue）混合炼狱语…（描述直接跟名称）
_RE_LANG_E = re.compile(r"^([一-鿿]+)（([A-Za-z][A-Za-z ]*)）(?![:：])(.*)$")
# 语言条目 BB（全角名称行跨行）：古奥斯利昂语（Ancient  + 下一行 Osiriani）：描述
_RE_LANG_BB = re.compile(r"^([一-鿿]+)（([A-Za-z][A-Za-z ]*)\s*$")
_RE_LANG_BB_DESC = re.compile(r"^([A-Za-z][A-Za-z ]*)）：(.*)$")
# 英文名行：(Rougarou)语（G 形态的下一行，补 name_en）
_RE_LANG_EN_LINE = re.compile(r"^\(([A-Za-z][A-Za-z ]*)\)([一-鿿]*)$")
# 语言条目 G（仅语言名）：沼蜍人语（独立行，无括号无描述）
_RE_LANG_G = re.compile(r"^([一-鿿]{2,12})$")
# 组标题（G 形态排除）：5 分组标题（异星球/其他怪物语言带冒号变体）
_LANG_GROUP_TITLES = {"现代人类语言", "古语", "其他语言", "其他怪物语言",
                      "异星球语言", "其他怪物语言：", "异星球语言："}
# 使用者前缀行：(火系生物)：「火焰话」…（CF 形态条目的下一行）
_RE_LANG_DESC_PRE = re.compile(r"^\(([^)]*)\)[:：]?\s*(.*)$")
# 冒号前缀行：：描述（CF 形态条目的下一行，无使用者括号）
_RE_LANG_DESC_COLON = re.compile(r"^[:：]\s*(.*)$")
# 导言星壳剥除与「中文 (English)」形态重组（_split_intro）
_RE_INTRO_STAR = re.compile(r"\*+")
_RE_INTRO_PAIR = re.compile(r"^([^()]+?)\s*\(([^)]+)\)\s*$")

# ---------------------------------------------------------------------------
# split 正则链（S7 Unchained 规则型页，批次 B1）
# ---------------------------------------------------------------------------

# 星壳标题：**中文（English）**[:：正文] / **中文**：正文（闭壳形态）
_RE_UNCH_TITLE = re.compile(r"^\*\*(.+?)\*\*\s*[:：]?\s*(.*)$")
# 开壳无闭壳（跨行标题前段）：**技能解放（Skill   /  **造物与专业替换规则（Alternate
# （HTML 转换丢闭壳；限长 ≤50 排除长正文段——page_648 导言段 75+ 字符）
_RE_UNCH_TITLE_OPEN = re.compile(r"^\*\*[^*].{0,50}$")
# 裸标题（无星壳）：中文（English）/ 中文（普通）/ 中文（智力）
_RE_UNCH_BARE = re.compile(r"^([一-鿿]{1,14})（([^（）]+)）$")
# 裸跨行标题前段：混职系统（Variant   （下一行补 Multiclassing））
_RE_UNCH_BARE_OPEN = re.compile(r"^([一-鿿]{1,14})（[^）]*$")
# 表标题（裸形态）：表2-8：混职角色晋级 / 表：工艺DC与进度价值（星壳走 _RE_UNCH_TITLE）
_RE_UNCH_TABLE_TITLE = re.compile(r"^表[\d\-－：:一-鿿A-Za-z ]+$")
# 纯中文短行（小节标题 vs 表内单值行：下一行 >15 字符佐证标题）
_RE_UNCH_SHORT_CN = re.compile(r"^[一-鿿 ]{2,10}$")
# 流程子项（并入当前条目，count_basis 不分块）：
#   四档 **5点**：…（page_648 技能解放）
#   步骤 **第1步**：…（背景技能艺术/学识条目内的制作步骤）
_RE_UNCH_POINTS = re.compile(r"^(?:\d+点|第\d+步)$")
# 标题分解：中文（English）（…）：组1=中文、组2=首括号内容（英文名或属性/DC）
_RE_UNCH_PAIR = re.compile(r"^([^（(]+)（([^）)]*)")
# 字段词表（S7 字段行并入当前条目，不新开——同 S1 字段级标题语义）：
# **检定（Check）**：/**动作**：无需。/ **重试**/**特殊**/ **未受训**
_UNCH_FIELD_WORDS = ("检定", "动作", "重试", "特殊", "未受训")
# HTML blockquote 转换残留行（「引用」单独成行，无内容）
_RE_UNCH_QUOTE = re.compile(r"^引用$")
# 译者吐槽星壳标题（（因为内容实在很多又大多与核心重复所以摸了））：
# 标题剥壳后以（ 开头（正常标题中文在前）→ 整行丢弃
_RE_UNCH_JUNK_TITLE = re.compile(r"^（")
# S8 巨人猎手标题两行形态：
#   首行 = 中文块 + 粘连英文段（佯装无害Feign / 躲在生物身后Hide behind）；
#   续行 = 英文段到全角括号前（Harmlessness（唬骗）→ 组1=Harmlessness）
_RE_GIANT_TITLE_FIRST = re.compile(r"^([一-鿿]+)([A-Za-z].*)$")
_RE_GIANT_TITLE_SECOND = re.compile(r"^([A-Za-z][A-Za-z0-9'’\- ]*?)\s*（")
# S9 异能 page_315 裸标题形态：中文块 + 空格 + 英文块（异能敏感 Psychic）；
# 续行英文（Sensitivity）纯字母空格形态（长度 ≤30 防正文行）
_RE_OCCULT_BARE = re.compile(r"^([一-鿿]+)\s+([A-Za-z].*)$")
_RE_OCCULT_EN_CONT = re.compile(r"^[A-Za-z][A-Za-z ]{1,30}$")
# S9 异能标题分解：技能：条目名（EN）双括号形态——知识（神秘）：颅相学
# （Phrenology）→ 组1=知识（神秘） 组2=颅相学 组3=Phrenology（条目名括号取
# EN，属性括号不进 title_en）；语言学：扶乩（Automatic Writing）同正则
_RE_OCCULT_CN_CN_EN = re.compile(r"^(.+?)：([^（：]+)（([^）]+)）$")
# S10 装备字段词表（工具和技能工具包 CR 块/价格行：**价格**：…；**重量**：…；
# **类型**：…；孤行 **效果**）。S7 词表不含装备字段，扩展判定不互扰
_EQUIP_FIELD_WORDS = ("价格", "重量", "类型", "察觉", "解除装置", "触发器", "复位",
                      "效果")
# S10 CR 陷阱块标题：**狗熊夹（Bear trap） CR 1** → 组1=中文 组2=EN 组3=CR 值
# （title 保留 CR 后缀区分同名物品条目；擅入者之靴陷阱 CR 1/2 断行 join 后同正则）
_RE_CR_TITLE = re.compile(r"^(.+?)（([^）]+)）(?: CR (.+))$")
# 中英粘连带空格拆离（神秘技能解放 Occult Skill Unlocks / 技能 Skills）——
# _RE_GIANT_TITLE_FIRST 仅覆盖无空格粘连（巨人猎手形态），此处补空格变体
_RE_CN_EN_SPACED = re.compile(r"^([一-鿿]+)\s+([A-Za-z].*)$")


class SkillFormat(BaseFormat):
    def category(self) -> str:
        return "skill"

    # ------------------------------------------------------------------
    # normalize：去噪 + 软换行重组
    # ------------------------------------------------------------------

    def _normalize_custom(self, text: str) -> str:
        # 1. 剥行首 URL 与译者行（须在 \r 重组前，行锚依赖换行结构）
        text = _RE_URL_LINE.sub("", text)
        text = _RE_TRANSLATOR_LINE.sub("", text)
        # 2. CR 归一：\r\n → \n（CRB 页 \r\n 是空行标记，UI 页是行内断点；
        #    统一换行结构，UI 断点重组在 split 层 UI 分支做整页 join）
        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")
        # 2b. 剥斜体星壳（须在 CR 归一后，行锚依赖换行结构；KN160）
        text = _RE_ITALIC_LEAD.sub("", text)
        text = _RE_ITALIC_TAIL.sub("", text)
        # 3. 剥【编注】块（含跨行）与行内链接
        text = _RE_EDITOR_NOTE.sub("", text)
        text = _RE_INLINE_LINK.sub("", text)
        return text

    def promote(self, text: str) -> str:
        # 技能无抽象提升（标题提升已在 split 内完成）
        return text

    # ------------------------------------------------------------------
    # split：判定链（S1~S6）
    # ------------------------------------------------------------------

    @staticmethod
    def _new_item(typ: str, **kw) -> dict:
        item = {
            "type": typ,
            "format_cluster": "",
            "text": "",
        }
        item.update(kw)
        return item

    @staticmethod
    def _parse_title_suffix(suffix: str) -> tuple:
        """'敏捷; 防具检定减值; 须受训' → (key_ability, armor_penalty, trained_only)"""
        parts = [p.strip() for p in suffix.split(";") if p.strip()]
        ability = parts[0] if parts else ""
        return (ability, "防具检定减值" in parts, "须受训" in parts)

    def _parse_main_title(self, line: str) -> dict | None:
        """**中文 (English) (属性[; 后缀])** → 主条目头信息；不匹配返回 None"""
        m = _RE_MAIN_TITLE.match(line)
        if not m:
            return None
        name, name_en, suffix = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        name_en = _RE_EN_ALT.sub("", name_en).strip()
        ability, armor, trained = self._parse_title_suffix(suffix)
        return {
            "skill_name": name, "english_name": name_en,
            "key_ability": ability, "armor_penalty": armor, "trained_only": trained,
        }

    def _split_crb_page(self, text: str, head: dict) -> list:
        """S1/S2/S3 主循环：字段 / DC 表 / 任务小节 / 速查块 / 子项"""
        items = []
        cur = self._new_item(
            "skill", format_cluster="S1", skill_name=head["skill_name"],
            english_name=head["english_name"], key_ability=head["key_ability"],
            trained_only=head["trained_only"], armor_penalty=head["armor_penalty"],
            sub_specialty=[], description="", check="", dc_table=[],
            action="", retry="", special="", untrained="", restriction="",
        )
        items.append(cur)
        dc_table: list[dict] = []
        cur_field: str | None = None      # 当前字段值收集（跨行）
        cur_task: dict | None = None      # 当前任务小节正文收集
        cur_note: dict | None = None      # 当前速查块正文收集
        pending_sub = False               # 刚遇 'l  ' 标记行
        cur_sub: dict | None = None       # 当前子项描述收集
        table_state = None                # None / "header" / "rows" + 表头列
        lines = text.splitlines()

        def close_contexts():
            """离开正文区时清空收集状态（避免跨结构粘连）"""
            nonlocal cur_field, cur_task, cur_note, cur_sub
            cur_field = cur_task = cur_note = cur_sub = None

        def append_text(target: dict, key: str, value: str):
            """正文值跨行追加（去首尾空白，行间保留单空格）"""
            value = value.strip()
            if not value:
                return
            prev = target.get(key, "")
            target[key] = (prev + " " + value).strip() if prev else value

        for line in lines:
            line = line.rstrip()
            if not line.strip():
                # DC 表尾注行跨空行（page_174 '| * ' 后空行再接注文）：保留表状态
                if table_state:
                    table_state = {"header": table_state["header"],
                                   "cols": table_state["cols"],
                                   "tail_note": table_state.get("tail_note", "")}
                continue

            # 1. 字段级标题（新字段 → 状态切换；值按标签映射进规范键）
            m = _RE_FIELD.match(line)
            if m:
                fname, lead = m.group(1), m.group(2)
                cur_field = _FIELD_KEYS[fname]
                table_state = None
                cur_task = cur_note = cur_sub = None
                if lead:
                    append_text(cur, cur_field, lead)
                continue

            # 2. DC 表（表头含 DC 字样才采集；表尾注行跳过）
            if line.startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if _RE_TABLE_FOOTNOTE.match(line):
                    continue  # | * / | ※1 尾注行
                if all(re.fullmatch(r":?-{2,}", c or "-") for c in cells):
                    continue  # 分隔行 | --- |
                if table_state is None:
                    # 表头判定：任一列头含 DC 才采集成 dc_table
                    if any("DC" in c for c in cells):
                        table_state = {"header": cells, "cols": len(cells)}
                else:
                    if len(cells) != table_state["cols"]:
                        continue  # 表尾注/畸形行
                    dc_idx = next((i for i, c in enumerate(table_state["header"]) if "DC" in c), 1)
                    row = {"task": cells[0], "dc": cells[dc_idx] if dc_idx < len(cells) else ""}
                    dc_table.append(row)
                    cur["dc_table"] = dc_table
                continue

            # 3. 速查块（独立 skill_note，不产任务）
            m = _RE_QUICK_REF.match(line)
            if m:
                name, name_en, lead = m.group(1).strip(), (m.group(2) or "").strip(), m.group(3)
                cur_note = self._new_item(
                    "note", format_cluster="S1", skill_name=cur["skill_name"],
                    name=name, name_en=name_en,
                )
                items.append(cur_note)
                cur_field = cur_task = cur_sub = None
                table_state = None
                if lead:
                    append_text(cur_note, "text", lead)
                continue

            # 4. 任务小节标题（名字非字段名）
            m = _RE_TASK.match(line)
            if m:
                tname, dc_tail, lead = m.group(1).strip(), m.group(2), m.group(3)
                cur_task = self._new_item(
                    "task", format_cluster="S1", skill_name=cur["skill_name"],
                    name=tname, name_en="", dc="",
                )
                if dc_tail:
                    # 技巧列表任务（驯养动物「攻击 (DC 20)」类）：DC 尾缀进
                    # dc 字段，任务名保持纯净（决策 3 双写前提）
                    cur_task["dc"] = dc_tail.split()[-1]
                items.append(cur_task)
                cur_field = cur_note = cur_sub = None
                # l 前缀是技巧列表标记非 S3 子项：任务标题必须重置列表待定，
                # 否则首行正文被 S3 子项分支吞掉（驯养动物技巧 text 空根因）
                pending_sub = False
                table_state = None
                if lead:
                    append_text(cur_task, "text", lead)
                continue

            # 5. 子项列表（S3）：'l  ' 标记 + **子项 (English)** + (描述)
            if _RE_LIST_MARK.match(line):
                pending_sub = True
                continue
            if pending_sub or cur_sub is not None:
                # 子项标题识别（闭合星壳 / 断行英文名；cur_sub 活跃时也识别新子项）。
                # 断行形态（**地理  ）组1 不含 *；闭合标题 **工程 (Engineering)** 组1 含 *
                m = _RE_SUB_OPEN.match(line)
                broken = False
                if not m:
                    bm = _RE_SUB_OPEN_BROKEN.match(line)
                    if bm and "*" not in bm.group(1):
                        m, broken = bm, True
                if m:
                    sname = m.group(1).strip()
                    if sname.endswith("语"):
                        # 语言列表子项（深渊语/邪灵语…，page_182 语言学正文尾部）：
                        # 语言条目由语言汇总页 skill_index 权威产出（设计决策 8），
                        # 名字行保留在主条目 description（决策 8 全文保留），
                        # 同时切出任务上下文——否则后续使用者行与列表尾文本
                        # 会粘入前一任务 text（page_182 制作任务污染根因）
                        sname_en = "" if broken else (m.group(2) or "").strip()
                        append_text(cur, "description",
                                    sname + ((" " + sname_en) if sname_en else ""))
                        pending_sub = False
                        cur_sub = None
                        cur_task = None
                        continue
                    sname_en = "" if broken else (m.group(2) or "").strip()
                    cur_sub = self._new_item(
                        "sub", format_cluster="S3", skill_name=cur["skill_name"],
                        name=sname, name_en=sname_en)
                    items.append(cur_sub)
                    if sname not in cur["sub_specialty"]:
                        cur["sub_specialty"].append(sname)
                    pending_sub = False
                    continue
                # 'l  ' 后非子项标题 → 取消待定
                pending_sub = False
                m = _RE_SUB_TAIL.match(line)  # (Geography)** 补英文名
                if m and cur_sub is not None:
                    if not cur_sub.get("name_en"):
                        cur_sub["name_en"] = m.group(1).strip()
                    continue
                m = _RE_SUB_DESC.match(line)  # (描述)
                if m and cur_sub is not None:
                    append_text(cur_sub, "text", m.group(1) + " " + m.group(2))
                    continue
                # 子项区后的普通行：结束子项收集
                if cur_sub is not None and not line.startswith("**"):
                    cur_sub = None
                continue

            # 6. 普通行：按当前上下文归属
            if cur_task is not None:
                append_text(cur_task, "text", line)
            elif cur_note is not None:
                append_text(cur_note, "text", line)
            elif cur_field is not None:
                append_text(cur, cur_field, line)
            else:
                append_text(cur, "description", line)

        # 任务 DC 双写（决策 3）：任务名匹配 DC 表行
        for t in items:
            if t["type"] != "task":
                continue
            row = next((r for r in dc_table if r["task"] == t["name"]), None)
            if row:
                t["dc"] = row["dc"]
        # 主条目 tasks 列表（决策 1 双级结构：主条目保留任务摘要，任务自包含）
        cur["tasks"] = [
            {"name": t["name"], "name_en": t["name_en"], "dc": t["dc"],
             "action": t.get("action", ""), "retry": t.get("retry", ""),
             "special": t.get("special", ""), "text": t["text"]}
            for t in items if t["type"] == "task"
        ]
        return items

    # ------------------------------------------------------------------
    # S4 UI 页
    # ------------------------------------------------------------------

    def _split_ui_page(self, text: str) -> list:
        # lstrip 保留行尾双空格（标题/小节锚点），join 分隔加一个空格
        lines = [l.lstrip() for l in text.splitlines() if l.strip()]
        if not lines:
            return []
        head, body_lines = self._ui_head_lines(lines)
        if head is None:
            return []
        ui = self._new_item(
            "ui", format_cluster="S4", skill_name=head.get("skill_name", ""),
            english_name=head.get("english_name", ""), title=head.get("title", ""),
            title_en=head.get("title_en", ""), sections=[],
        )
        body = " ".join(body_lines)
        # 行内嵌小节（中文（English）：正文）
        secs: list[dict] = []
        last_end = 0
        for m in _RE_UI_SECTION.finditer(body):
            # 组1 前缀含段落分隔空格（{2,}），strip 还原纯名称
            name = re.sub(r" {2,}", " ", m.group(1)).strip()
            name_en = m.group(2).strip()
            lead = body[last_end:m.start()].strip()
            if secs:
                secs[-1]["text"] = (secs[-1].get("text", "") + " " + lead).strip()
            elif lead:
                ui["text"] = (ui["text"] + " " + lead).strip()
            secs.append({"name": name, "name_en": name_en, "text": ""})
            last_end = m.end()
        if secs:
            secs[-1]["text"] = (secs[-1].get("text", "") + " " + body[last_end:]).strip()
        else:
            ui["text"] = (ui["text"] + " " + body).strip()
        # 断行英文名小节（说谎 Lying  双空格）：并入已有 sections（去重）
        if secs:
            names = {s["name"] for s in secs}
            for m in _RE_UI_SECTION_BROKEN.finditer(body):
                name, name_en = m.group(1).strip(), m.group(2).strip()
                if name not in names:
                    secs.append({"name": name, "name_en": name_en, "text": ""})
                    names.add(name)
        ui["sections"] = secs
        return [ui]

    @staticmethod
    def _ui_head_lines(lines: list) -> tuple:
        """UI 标题识别：前 1~3 行重组候选（文本单行 / 断行中文+英文 / 星壳跨行），
        命中即返回 (头信息, 正文行)。"""
        for k in (1, 2, 3):
            if len(lines) < k:
                break
            cand = " ".join(lines[:k])
            m = _RE_UI_STAR.match(cand)
            if m:
                # 英文名 join 断行会残留双空格伪影（'Skills in  Conflict'），压缩还原
                return {"title": m.group(1).strip(),
                        "title_en": re.sub(r" {2,}", " ", m.group(2)).strip()}, lines[k:]
            m = _RE_UI_TEXT.match(cand)
            if m:
                return {"skill_name": m.group(1).strip(),
                        "english_name": re.sub(r" {2,}", " ", m.group(2)).strip()}, lines[k:]
        return None, lines

    # ------------------------------------------------------------------
    # S5 语言汇总 / S6 导言
    # ------------------------------------------------------------------

    @staticmethod
    def _is_lang_entry_head(s: str) -> bool:
        """入口判定：除 G 外各形态（纯中文名太宽泛，防其他页前几行误入）"""
        return any(r.match(s) for r in (
            _RE_LANG_A, _RE_LANG_B, _RE_LANG_BB, _RE_LANG_D,
            _RE_LANG_E, _RE_LANG_CF))

    @staticmethod
    def _is_lang_entry_line(s: str) -> bool:
        """该行是否为条目起始行（各形态正则之一，含 G 纯名）"""
        return any(r.match(s) for r in (
            _RE_LANG_A, _RE_LANG_B, _RE_LANG_BB, _RE_LANG_D,
            _RE_LANG_E, _RE_LANG_CF, _RE_LANG_G))

    @staticmethod
    def _take_lang_desc(lines: list, i: int) -> str:
        """取下一行作为条目描述（仅吞括号/冒号前缀形态，防吞组标题）

        支持三种描述行：'(使用者)：描述' → '使用者 描述'（同 A 形态惯例）、
        '：描述' → '描述'；普通行/空行不吞（可能是组标题或下一个条目）。
        """
        if i + 1 >= len(lines):
            return ""
        nxt = lines[i + 1].strip()
        if not nxt:
            return ""
        dm = _RE_LANG_DESC_PRE.match(nxt)
        if dm:
            return (dm.group(1) + " " + dm.group(2)).strip()
        cm = _RE_LANG_DESC_COLON.match(nxt)
        if cm:
            return cm.group(1).strip()
        return ""

    @staticmethod
    def _fallback_lang_desc(lines: list, i: int) -> str:
        """B 形态冒号后无描述的兜底：下一行普通描述行（排除组标题/条目行）"""
        if i + 1 >= len(lines):
            return ""
        nxt = lines[i + 1].strip()
        if not nxt or nxt in _LANG_GROUP_TITLES:
            return ""
        if SkillFormat._is_lang_entry_line(nxt):
            return ""
        return nxt

    def _split_language(self, text: str) -> list:
        """S5 语言汇总条目（62 条口径，7 形态）：

        A 通用语 (Common)(塔尔多语，Taldane) + 下一行(描述)（半角空格+别名）
        B 哈利特语（Hallit）：描述（全角带冒号）
        CF 火族语(Ignan) / 卡萨达(Kasatha)语 + 下一行(使用者)：描述（半角无空格）
        D 德鲁伊语(Druidic)(仅德鲁伊和变形者)：描述（半角单行）
        E 暗影语（Shadowtongue）描述…（全角无冒号）
        G 沼蜍人语（仅语言名，无描述）
        组标题（现代人类语言/古语/…）与引导段不产条目。
        """
        items = []
        lines = text.splitlines()
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            m = _RE_LANG_A.match(line)
            if m:
                name, name_en, alias = m.group(1), m.group(2), (m.group(3) or "")
                desc = self._take_lang_desc(lines, i)
                text_body = (alias + " " + desc).strip() if alias else desc
                items.append(self._new_item(
                    "index", format_cluster="S5", name=name, name_en=name_en,
                    text=text_body))
                continue
            m = _RE_LANG_B.match(line)
            if m:
                name = m.group(1).strip()
                if re.search(r"[。，,、]", name):
                    # 脏混合行（语言汇总 L153 后：描述+条目重复合并进一行，
                    # 组1 吞入前导描述句）→ 跳过不产条目，防垃圾条目名
                    continue
                text_body = m.group(3).strip()
                if not text_body:
                    # 轮回者语（Samsaran）： 冒号后空 → 描述在下一行普通行
                    text_body = self._fallback_lang_desc(lines, i)
                items.append(self._new_item(
                    "index", format_cluster="S5",
                    name=name, name_en=m.group(2).strip(),
                    text=text_body))
                continue
            m = _RE_LANG_BB.match(line)
            if m:
                # 古奥斯利昂语（Ancient  + 下一行 Osiriani）：描述（全角跨行）
                name_en, text_body = m.group(2).strip(), ""
                if i + 1 < len(lines):
                    dm = _RE_LANG_BB_DESC.match(lines[i + 1].strip())
                    if dm:
                        name_en = (m.group(2).strip() + " " + dm.group(1)).strip()
                        text_body = dm.group(2).strip()
                items.append(self._new_item(
                    "index", format_cluster="S5",
                    name=m.group(1), name_en=name_en, text=text_body))
                continue
            m = _RE_LANG_D.match(line)
            if m:
                items.append(self._new_item(
                    "index", format_cluster="S5",
                    name=m.group(1), name_en=m.group(2),
                    text=(m.group(4) or "").strip()))
                continue
            m = _RE_LANG_E.match(line)
            if m:
                items.append(self._new_item(
                    "index", format_cluster="S5",
                    name=m.group(1), name_en=m.group(2),
                    text=m.group(3).strip()))
                continue
            m = _RE_LANG_CF.match(line)
            if m:
                items.append(self._new_item(
                    "index", format_cluster="S5",
                    name=m.group(1), name_en=m.group(2),
                    text=self._take_lang_desc(lines, i)))
                continue
            m = _RE_LANG_G.match(line)
            if m and m.group(1) not in _LANG_GROUP_TITLES:
                name_en, desc = "", ""
                # 狩狼人 + 下一行 (Rougarou)语：英文名行并入 name_en
                if i + 1 < len(lines):
                    em = _RE_LANG_EN_LINE.match(lines[i + 1].strip())
                    if em:
                        name_en = em.group(1)
                        desc = self._take_lang_desc(lines, i + 1)
                items.append(self._new_item(
                    "index", format_cluster="S5", name=m.group(1),
                    name_en=name_en, text=desc))
        return items

    @staticmethod
    def _clean_intro_title(raw: str) -> tuple:
        """剥逐字加粗残留（**技能****详****述****）→ 纯文本 → (中文, 英文)。

        HTML 转换会把「技能详述」逐字加粗（**技能****详****述****），
        星壳正则 `[^*]+?` 在首个 `**` 处锚死无法跨过——统一剥 `*+` 后
        按「中文 (English)」形态重组；无星壳痕迹（非标题行）返回 ('', '')。
        """
        if "*" not in raw:
            return "", ""
        clean = _RE_INTRO_STAR.sub("", raw).strip()
        if not clean:
            return "", ""
        m = _RE_INTRO_PAIR.match(clean)
        if m:
            # join 空格 + 行内尾空格会叠出双空格（Skills  Descriptions），归一化
            return m.group(1).strip(), " ".join(m.group(2).split())
        if "(" in clean or ")" in clean:
            return "", ""  # 括号不成对 = 跨行中间态（英文名未完），等更长 join
        return clean, ""

    def _split_intro(self, text: str) -> list:
        lines = [l for l in text.splitlines() if l.strip()]
        title, title_en, rest = "", "", []
        # 跨行星壳标题（page_162：**技能****详****述**** \n(Skill****s \n
        # Descriptions****)** 拆 3 行）：前 3 行 join 剥星壳试重组。
        # en 缺失（纯中文标题）时继续长 join 补英文名；中文部分变化
        #（join 吃进正文）则拒绝该步
        best_cn = best_en = ""
        used = 0
        for k in (1, 2, 3):
            cn, en = self._clean_intro_title(" ".join(lines[:k]))
            if not cn:
                continue
            if not best_cn:
                best_cn, best_en, used = cn, en, k
            elif en and cn == best_cn:
                best_en, used = en, k
            if best_en:
                break
        title, title_en = best_cn, best_en
        rest = lines[used:]
        if not title:
            # 单行标题（**学习技能 (Acquiring Skills)**）：逐行扫描
            for i, line in enumerate(lines):
                cn, en = self._clean_intro_title(line)
                if cn:
                    title, title_en = cn, en
                    rest = lines[i + 1:]
                    break
            else:
                rest = lines
        return [self._new_item(
            "intro", format_cluster="S6", title=title, title_en=title_en,
            text="\n".join(rest).strip())]

    # ------------------------------------------------------------------
    # S7 Unchained 规则型页（批次 B1：page_647/648/649 + 背景/整合/分组技能）
    # ------------------------------------------------------------------

    # 并入规则按 count_basis 口径（人工门 1 拍板）：
    #   page_647 造物与专业：导言 + 15 大节 + 4 表 + 7 难度档 + 30 范例 全独立
    #   page_648 技能解放：导言 + 标志性技能 + 26 技能；四档 **N点**：并入技能
    #   page_649 混职：导言 + 表 + 2 小节 + 19 职业；星壳特性并入职业（absorb）
    #   背景/整合/分组技能：星壳子节 + 标准 | 表格 + 新技能条目

    @staticmethod
    def _unch_en_of(inner: str) -> str:
        """括号内容 → title_en：含字母且非 DC 难度/纯中文属性才算英文名"""
        inner = inner.strip()
        if inner.upper().startswith("DC"):
            return ""
        if re.search(r"[A-Za-z]", inner):
            return " ".join(inner.split())
        return ""

    @staticmethod
    def _unch_title_parts(raw: str) -> tuple:
        """标题分解 → (中文, 英文名)：中文（English）（属性）→ 首括号内容取 en"""
        raw = raw.strip()
        m = _RE_UNCH_PAIR.match(raw)
        if m:
            return m.group(1).strip(), SkillFormat._unch_en_of(m.group(2))
        return raw, ""

    @staticmethod
    def _occult_title_parts(raw: str) -> tuple:
        """S9 异能标题拆（中文, 英文）：
        技能：条目名（EN）双括号 → 中文含技能前缀、EN 取条目名括号；
        中文+英文粘连（主标题）→ 空格拆离；其余回落 _unch_title_parts"""
        m = _RE_OCCULT_CN_CN_EN.match(raw)
        if m:
            return f"{m.group(1)}：{m.group(2)}", SkillFormat._unch_en_of(m.group(3))
        cn, en = SkillFormat._unch_title_parts(raw)
        if not en:
            gm = _RE_CN_EN_SPACED.match(cn)
            if gm:
                cn, en = gm.group(1), gm.group(2)
        return cn, en

    @staticmethod
    def _unch_join(lines: list, i: int, max_rows: int = 4) -> tuple:
        """跨行标题 join：从 i 行起拼后续行直到出现 ） 或 ** 或行数超限"""
        parts = [lines[i]]
        j = i
        while j + 1 < len(lines) and len(parts) < max_rows:
            nxt = lines[j + 1].strip()
            if not nxt:
                break
            parts.append(nxt)
            j += 1
            if "）" in nxt or "**" in nxt:
                break
        return " ".join(parts), j - i + 1

    @staticmethod
    def _unch_next_nonempty(lines: list, i: int):
        """下一非空行（纯中文短行的标题佐证）"""
        while i < len(lines):
            if lines[i].strip():
                return lines[i].strip()
            i += 1
        return None

    def _unch_append(self, items: list, cur: dict, line: str,
                     cluster: str = "S7") -> dict:
        """并入当前条目 text（保留原文行格式）；无当前条目时开导言 item"""
        if cur is None:
            cur = self._new_item("rule", format_cluster=cluster, title="", title_en="",
                                 text="")
            items.append(cur)
        cur["text"] = (cur["text"] + "\n" + line).strip()
        return cur

    def _split_unchained(self, text: str, source_name: str = "",
                         cluster: str = "S7") -> list:
        """S7 统一解析器：行级扫描，标题开条目、正文/表格/字段并入。

        cluster 参数：S9 河域子民复用本解析器（形态同族：星壳 规则名：正文
        + 纯中文短行小节标题），标 S9 与 B1 页区分。
        """
        lines = [l.strip() for l in text.splitlines()]
        items: list = []
        cur = None
        pending_source = None  # 条目前来源行 → 挂第一个新开条目（S9 河域形态）
        from_bare = False  # 当前条目是否由裸标题开启（page_649 吸收判定）
        absorb = "page_649" in (source_name or "")
        i, n = 0, len(lines)

        def open_item(**kw) -> dict:
            """开条目并挂载 pending_source（文件级来源行在条目前时——
            对整文件条目有效，不清空；B1 无来源行时 pending 恒 None）"""
            item = self._new_item("rule", format_cluster=cluster, **kw)
            if pending_source:
                item["source"] = pending_source
            items.append(item)
            return item

        while i < n:
            l = lines[i]
            if not l or _RE_UNCH_QUOTE.match(l):
                i += 1
                continue
            # 整理注释行（<!-- 河域子民PotR-source… -->）：B1 6 文件无此形态，零回归
            if l.startswith("<!--") and "-->" in l:
                i += 1
                continue
            # markdown 标题行（# / ## 文档头）：B1 6 文件无此形态，零回归
            if l.startswith("#"):
                i += 1
                continue
            if _RE_URL_LINE.match(l) or l.startswith("**译者"):
                i += 1
                continue
            # 来源行 → source 字段（不进 text，同 S8 口径）；条目未开时缓存，
            # 首个条目由 open_item 创建时挂载（河域来源行在标题之前）
            if l.startswith(">") and "来源：" in l:
                if cur is not None:
                    cur["source"] = l
                else:
                    pending_source = l
                i += 1
                continue
            # 星壳标题（闭壳；开壳无闭壳 → 跨行 join 补闭壳，限长防正文段）
            if l.startswith("**"):
                m = _RE_UNCH_TITLE.match(l)
                used = 1
                if not m and len(l) <= 50:
                    joined, used = self._unch_join(lines, i)
                    m = _RE_UNCH_TITLE.match(joined)
                    if not m and joined.startswith("**") and "**" not in joined[2:]:
                        # 跨行标题闭壳丢失形态（page_648 主标题 **技能解放（Skill
                        # Unlocks） 无 ** 闭壳）：剥开壳星后整行须是「中文（…）」
                        # 闭括号形态才作标题（正文长行如「**随着角色…（Skill
                        # Unlocks）会赋予她…」带尾随文字，不得误判）
                        if _RE_UNCH_BARE.match(joined[2:].strip()):
                            m = re.match(r"^\*\*(.*)$", joined)
                else:
                    joined = None
                if m:
                    title_raw = m.group(1).strip()
                    body = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else ""
                    if not _RE_UNCH_JUNK_TITLE.match(title_raw):
                        if _RE_UNCH_POINTS.match(title_raw):
                            cur = self._unch_append(items, cur, l, cluster=cluster)
                        elif (absorb and from_bare and cur is not None
                                or SkillFormat._unch_title_parts(title_raw)[0]
                                in _UNCH_FIELD_WORDS):
                            cur = self._unch_append(items, cur, l, cluster=cluster)
                        else:
                            cn, en = SkillFormat._unch_title_parts(title_raw)
                            item = open_item(title=cn, title_en=en, text=body)
                            cur, from_bare = item, False
                    # 译者吐槽形态（（摸了））→ 整行丢弃
                elif joined is not None:
                    # 跨行 join 未成标题（正文开壳行断点）：重组文本并入，
                    # 防后续行在 used 推进中丢失
                    cur = self._unch_append(items, cur, joined, cluster=cluster)
                else:
                    cur = self._unch_append(items, cur, l, cluster=cluster)
                i += used
                continue
            # 裸跨行标题（中文（ 开壳无闭壳，限长 ≤30 防正文括注）
            if _RE_UNCH_BARE_OPEN.match(l) and len(l) <= 30:
                joined, used = self._unch_join(lines, i, max_rows=3)
                bm = _RE_UNCH_BARE.match(joined)
                if bm:
                    item = open_item(title=bm.group(1).strip(),
                                     title_en=SkillFormat._unch_en_of(bm.group(2)),
                                     text="")
                    cur, from_bare = item, True
                    i += used
                    continue
            # 裸标题：中文（English）/ 中文（属性）
            bm = _RE_UNCH_BARE.match(l)
            if bm:
                item = open_item(title=bm.group(1).strip(),
                                 title_en=SkillFormat._unch_en_of(bm.group(2)),
                                 text="")
                cur, from_bare = item, True
                i += 1
                continue
            # 裸表标题：表2-8：混职角色晋级
            if _RE_UNCH_TABLE_TITLE.match(l):
                item = open_item(title=l, title_en="", text="")
                cur, from_bare = item, False
                i += 1
                continue
            # 纯中文短行：下一行长行佐证 = 小节标题；否则表内单值行并入
            if _RE_UNCH_SHORT_CN.match(l):
                nxt = self._unch_next_nonempty(lines, i + 1)
                if nxt is not None and len(nxt) > 15:
                    item = open_item(title=l, title_en="", text="")
                    cur, from_bare = item, False
                else:
                    cur = self._unch_append(items, cur, l, cluster=cluster)
                i += 1
                continue
            # 其余：正文段 / 表格行 | / 斜体英文行 → 并入当前条目
            cur = self._unch_append(items, cur, l, cluster=cluster)
            i += 1
        return items

    # ------------------------------------------------------------------
    # S8 巨人猎手新技能选项（GIANT-source 注释锚点 + 裸标题两行重组）
    # ------------------------------------------------------------------

    def _split_giant(self, text: str, source_name: str = "") -> list:
        """S8 巨人猎手新技能选项条目流。

        形态（勘探 B2）：`<!-- GIANT-source:…:锚点 -->` 注释行开新条目；
        标题 = 裸文本行「中文名+英文名粘连」（佯装无害Feign）+ 英文续行
        「Harmlessness（唬骗）」（英文段重组、括号技能归属剥离）；字段流
        （检定：/特殊规则：/动作：/重试：）与正文并入 text；`> 来源：` 行
        提取到 source 字段；`****` 纯星号行 / URL / 译者行剔除（count_basis
        est 5 = 导言 1 + 4 条目）。
        """
        lines = [l.strip() for l in text.splitlines()]
        items: list = []
        cur: dict = None
        i, n = 0, len(lines)
        while i < n:
            l = lines[i]
            if not l or set(l) <= {"*", " "}:
                i += 1
                continue
            if _RE_URL_LINE.match(l) or l.startswith("**译者"):
                i += 1
                continue
            # GIANT-source 注释锚点：开新条目（锚点是整理标记，不作标题）
            if l.startswith("<!-- GIANT-source"):
                cur = self._new_item("rule", format_cluster="S8",
                                     title="", title_en="", text="")
                items.append(cur)
                i += 1
                continue
            # 来源行 → source 字段（挂当前条目，不进 text）
            if l.startswith(">") and "来源：" in l:
                if cur is not None:
                    cur["source"] = l
                i += 1
                continue
            if cur is None:
                # 首个注释前的 # 文档标题等非条目内容：不入条目
                i += 1
                continue
            if cur.get("title"):
                cur = self._unch_append(items, cur, l)
                i += 1
                continue
            # 标题未定：裸标题行重组（中文块 + 粘连英文段）
            m = _RE_GIANT_TITLE_FIRST.match(l)
            if m:
                cur["title"] = m.group(1)
                en = m.group(2).strip()
                nxt = lines[i + 1] if i + 1 < n else ""
                m2 = _RE_GIANT_TITLE_SECOND.match(nxt)
                if m2:
                    # 英文续行：英文段重组，括号技能归属剥离
                    cur["title_en"] = f"{en} {m2.group(1).strip()}"
                    i += 2
                else:
                    cur["title_en"] = en
                    i += 1
                continue
            # 纯中文标题行（导言「巨人猎手们的技能（Skill）新选项」整行保留）
            cur["title"] = l
            i += 1
        return items

    # ------------------------------------------------------------------
    # S9 异能神秘技能解放 page_315（断行星壳标题 + 裸标题 + 字段并入）
    # ------------------------------------------------------------------

    def _split_occult(self, text: str, source_name: str = "") -> list:
        """S9 异能规则 page_315 神秘技能解放页。

        形态（勘探 B2）：跨行星壳主标题「**神秘技能解放 Occult Skill
        Unlocks**」（导言 item，中英粘连拆离）；开壳悬空形态（`**` 单独行 +
        续行「语言学：扶乩（Automatic」+「Writing）**」跨行闭壳，join 重组）；
        裸标题「异能敏感 Psychic」+ 英文续行「Sensitivity」；8 个技能解放
        标题「**技能：名称（EN）**」（技能名前缀保留在 title）；字段行
        （技能检定（Check）：/动作：/重试：/特殊：）与斜体引言、纯文本
        对齐 DC 表、`x` 乘号续行并入 text（count_basis est 10 = 导言 1 +
        异能敏感 1 + 8 解放）。
        """
        lines = [l.strip() for l in text.splitlines()]
        items: list = []
        cur: dict = None
        i, n = 0, len(lines)
        while i < n:
            l = lines[i]
            if not l or _RE_UNCH_QUOTE.match(l):
                i += 1
                continue
            if _RE_URL_LINE.match(l) or l.startswith("**译者"):
                i += 1
                continue
            # 开壳悬空形态：整行 `**` 单独 → 后续行 join 到 ）** 闭壳
            if l == "**":
                parts, j = [], i + 1
                while j < n and (not parts or "）**" not in parts[-1]):
                    parts.append(lines[j])
                    j += 1
                joined = "**" + " ".join(parts)
                m = _RE_UNCH_TITLE.match(joined)
                if m and not m.group(1).strip().endswith("："):
                    cn, en = SkillFormat._occult_title_parts(m.group(1).strip())
                    item = self._new_item("rule", format_cluster="S9", title=cn,
                                          title_en=en, text="")
                    items.append(item)
                    cur = item
                else:
                    cur = self._unch_append(items, cur, joined, cluster="S9")
                i = j
                continue
            # 星壳标题（单行闭壳 / 跨行 join 补闭壳）
            if l.startswith("**"):
                m = _RE_UNCH_TITLE.match(l)
                used = 1
                joined = None
                if not m and len(l) <= 50:
                    joined, used = self._unch_join(lines, i)
                    m = _RE_UNCH_TITLE.match(joined)
                if m:
                    title_raw = m.group(1).strip()
                    body = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else ""
                    if title_raw.endswith(("：", ":")):
                        # 字段行（技能检定（Check）：）→ 并入
                        cur = self._unch_append(items, cur, l, cluster="S9")
                    else:
                        cn, en = SkillFormat._occult_title_parts(title_raw)
                        item = self._new_item("rule", format_cluster="S9", title=cn,
                                              title_en=en, text=body)
                        items.append(item)
                        cur = item
                    i += used
                    continue
                cur = self._unch_append(items, cur, joined if joined is not None else l,
                                        cluster="S9")
                i += used
                continue
            # 裸标题：中文块 + 空格 + 英文块（异能敏感 Psychic / 续行 Sensitivity）。
            # 要求下一行为英文续行——页内唯一裸标题形态；表头行「技能等级要求
            # DC」（normalize 压缩空格后同形态）后跟空行/表值，天然排除
            m = _RE_OCCULT_BARE.match(l)
            nxt = lines[i + 1] if i + 1 < n else ""
            if m and len(l) <= 40 and nxt and _RE_OCCULT_EN_CONT.match(nxt):
                item = self._new_item("rule", format_cluster="S9", title=m.group(1),
                                      title_en=f"{m.group(2).strip()} {nxt.strip()}",
                                      text="")
                items.append(item)
                cur = item
                i += 2
                continue
            # 其余：斜体引言 / DC 表 / x 乘号续行 / 正文 → 并入
            cur = self._unch_append(items, cur, l, cluster="S9")
            i += 1
        return items

    # ------------------------------------------------------------------
    # S9 科技世界 page_760（行内连排：标题嵌行尾/行中）
    # ------------------------------------------------------------------

    def _split_tech(self, text: str, source_name: str = "") -> list:
        """S9 科技指南 page_760 技能页。

        形态（勘探 B2）：导言标题「**技能 Skills**」行首 + 正文紧随；
        条目标题（**手艺（智力）** / **解除装置（敏捷；护甲减值；需受训）**
        / **语言学（智力）** / **研究科技产品**）嵌在前一条目正文行尾/
        行中（属性括号剥除不进 title_en）；斜体子项（*设置爆炸物 Arm
        Explosive：* 断行开壳闭壳）与混合壳子项（**瘫痪电子锁或触发器 +
        续行 EN：*）与行内字段（**特殊：**/时间：/机械语：/医疗：/知识
        （奥术）：）并入 text（count_basis est 5 = 导言 1 + 4 条目）。
        """
        lines = [l.strip() for l in text.splitlines()]
        items: list = []
        cur: dict = None
        for l in lines:
            if not l:
                continue
            # 行内扫描 ** 闭合对（开壳无闭壳的跨行子项整体并入 text）
            pos = 0
            for m in re.finditer(r"\*\*([^*]+)\*\*", l):
                seg = l[pos:m.start()]
                if seg.strip():
                    cur = self._unch_append(items, cur, seg, cluster="S9")
                x = m.group(1)
                if x.endswith(("：", ":")):
                    # 行内字段（特殊：/时间：/机械语：/医疗：）→ 并入
                    cur = self._unch_append(items, cur, m.group(0), cluster="S9")
                elif "（" in x and "）" in x:
                    # 条目标题：中文（属性/EN）→ 括号不进 title_en
                    cn, en = SkillFormat._unch_title_parts(x)
                    item = self._new_item("rule", format_cluster="S9", title=cn,
                                          title_en=en, text="")
                    items.append(item)
                    cur = item
                elif re.fullmatch(r"[一-鿿]{1,8}", x):
                    # 纯中文条目标题（研究科技产品）
                    item = self._new_item("rule", format_cluster="S9", title=x,
                                          title_en="", text="")
                    items.append(item)
                    cur = item
                elif _RE_CN_EN_SPACED.match(x):
                    # 导言标题中英粘连（技能 Skills）→ 拆离（允许空格）
                    gm = _RE_CN_EN_SPACED.match(x)
                    item = self._new_item("rule", format_cluster="S9",
                                          title=gm.group(1), title_en=gm.group(2),
                                          text="")
                    items.append(item)
                    cur = item
                else:
                    cur = self._unch_append(items, cur, m.group(0), cluster="S9")
                pos = m.end()
            tail = l[pos:]
            if tail.strip():
                cur = self._unch_append(items, cur, tail, cluster="S9")
        return items

    # ------------------------------------------------------------------
    # S10 工具和技能工具包（装备物品卡：四段来源拼接 + 尾部整段重复去重）
    # ------------------------------------------------------------------

    def _split_equipment(self, text: str, source_name: str = "") -> list:
        """S10 工具和技能工具包装备物品卡（count_basis est 51 = 24 物品
        + 初探 2 + 内海 1 + 尾部重复 24；去重后 31 = 导言 1 + 物品 24 +
        CR 块 2 + 初探 3 + 内海 1）。

        形态（勘探 B2 + 拍板 #9）：
        ① 主段（冒险者的军械库）：裸标题导言（价格表/表注并入）+ 开壳星壳
           导言（闭壳借位下一行 `**` 句子，剥壳并入）+ 逐物品条目（断行标题
           `**中文（EN` 跨行 join + `**价格**：…；**重量**：…。` 字段并入 +
           `![[图片]]` 行剔除）+ CR 陷阱块（**中文（EN） CR N** 独立条目，
           title 保留 CR 后缀区分同名物品）
        ② 初探探索者协会工具箱：`<!-- …-source -->` 注释 + `## 段标题`（剔除）
           + `> 来源：` pending_source + 行内连排 `**标题****正文`（_RE_UNCH_
           TITLE 组2 余文剥前导 `**`）
        ③ 内海炼金工具箱：中英粘连导言（_RE_CN_EN_SPACED 拆离）+ `|` 地区
           表格并入
        ④ 冒险者的军械库段：source 路径 basename == 本文件 → 整段跳过
           （拍板 #9 段级去重，跳至下一 `<!--` 注释）
        """
        lines = [l.strip() for l in text.splitlines()]
        items: list = []
        cur: dict = None
        pending_source = None  # 段首来源行 → 挂该段全部新开条目（同 S7 语义）
        i, n = 0, len(lines)

        def open_item(**kw) -> dict:
            item = self._new_item("equipment", format_cluster="S10", **kw)
            if pending_source:
                item["source"] = pending_source
            items.append(item)
            return item

        while i < n:
            l = lines[i]
            # 空行 / 引用 / 水平线 / 图片行 / markdown 标题 → 剔除
            if (not l or _RE_UNCH_QUOTE.match(l) or set(l) <= {"-", " "}
                    or l.startswith("![[") or l.startswith("#")):
                i += 1
                continue
            # 表格分隔行（| --- | --- |）→ 剔除（数据行并入正文）
            if re.fullmatch(r"\|[\s\-|]+\|", l):
                i += 1
                continue
            # 段级去重（拍板 #9）：<!-- 书-source:路径:锚点 --> 注释的 source
            # 路径是本文件自身 → 尾部整段重复副本，跳至下一注释/EOF
            if l.startswith("<!--") and "-->" in l:
                m = re.search(r"-source:([^:>]+):", l)
                if m and m.group(1).rsplit("/", 1)[-1] == source_name:
                    i += 1
                    while i < n and not (lines[i].startswith("<!--")
                                         and "-->" in lines[i]):
                        i += 1
                    continue
                i += 1
                continue
            if _RE_URL_LINE.match(l) or l.startswith("**译者"):
                i += 1
                continue
            # 来源行 → source 字段（不进 text）。S10 为多段拼接文件，来源行
            # 恒在段首（前段 cur 非 None）——统一走 pending 覆盖式挂载，
            # 挂该段全部新开条目（段间无条目级来源行，与 S7 语义不冲突）
            if l.startswith(">") and "来源：" in l:
                pending_source = l
                i += 1
                continue
            # 星壳行：闭壳标题 / 开壳跨行 join / 字段与句子并入
            if l.startswith("**"):
                # 星壳句子（导言闭壳借位正文：**这些道具涉及到了…。 无闭壳，
                # 非 **X**：… 字段行——剥壳后无 `**` 残留才属句子）→ 剥壳并入
                inner = l[2:].strip()
                if (not l.endswith("**") and "**" not in inner
                        and inner.endswith(("。", "！", "？"))):
                    cur = self._unch_append(items, cur, inner, cluster="S10")
                    i += 1
                    continue
                m = _RE_UNCH_TITLE.match(l)
                used = 1
                joined = None
                if not m and len(l) <= 50:
                    joined, used = self._unch_join(lines, i)
                    m = _RE_UNCH_TITLE.match(joined)
                    if not m and joined.startswith("**") and "**" not in joined[2:]:
                        # 闭壳丢失形态（**工具和技能工具包（Tools and Skill
                        # Kits） 无 ** 闭壳）：剥壳后须是中文（EN）才作标题
                        if _RE_UNCH_BARE.match(joined[2:].strip()):
                            m = re.match(r"^\*\*(.*)$", joined)
                else:
                    joined = None
                if m:
                    title_raw = m.group(1).strip()
                    body = (m.group(2).strip()
                            if m.lastindex and m.lastindex >= 2 else "")
                    if body.startswith("**"):
                        body = body[2:].strip()  # 行内连排余文剥前导星壳
                    parts = SkillFormat._unch_title_parts(title_raw)
                    if not _RE_UNCH_JUNK_TITLE.match(title_raw):
                        if title_raw.endswith(("。", "！", "？")):
                            # 星壳句子（导言闭壳借位正文）→ 剥壳并入
                            cur = self._unch_append(items, cur, l[2:],
                                                    cluster="S10")
                        elif parts[0] in (_UNCH_FIELD_WORDS + _EQUIP_FIELD_WORDS):
                            # 字段行（**价格**：…；**效果** 孤行）→ 原行并入
                            cur = self._unch_append(items, cur, l, cluster="S10")
                        elif _RE_CR_TITLE.match(title_raw):
                            # CR 陷阱块：title 保留 CR 后缀区分同名物品
                            cm = _RE_CR_TITLE.match(title_raw)
                            item = open_item(title=f"{cm.group(1)} CR {cm.group(3)}",
                                             title_en=SkillFormat._unch_en_of(
                                                 cm.group(2)), text=body)
                            cur = item
                        elif cur is not None and parts[0] == cur["title"]:
                            # 导言标题重复（裸标题 + 星壳标题同内容）→ 丢弃
                            # 标题行（正文由后续行自行并入）
                            pass
                        else:
                            item = open_item(title=parts[0], title_en=parts[1],
                                             text=body)
                            cur = item
                    i += used
                    continue
                cur = self._unch_append(items, cur,
                                        joined if joined is not None else l,
                                        cluster="S10")
                i += used
                continue
            # 裸跨行标题：中文（ 开壳 + 续行补闭括号（主段导言断行形态）
            if _RE_UNCH_BARE_OPEN.match(l) and len(l) <= 30:
                joined, used = self._unch_join(lines, i, max_rows=3)
                bm = _RE_UNCH_BARE.match(joined)
                if bm:
                    item = open_item(title=bm.group(1).strip(),
                                     title_en=SkillFormat._unch_en_of(
                                         bm.group(2)), text="")
                    cur = item
                    i += used
                    continue
            # 裸标题：中文（English）
            bm = _RE_UNCH_BARE.match(l)
            if bm:
                item = open_item(title=bm.group(1).strip(),
                                 title_en=SkillFormat._unch_en_of(bm.group(2)),
                                 text="")
                cur = item
                i += 1
                continue
            # 行内连排（无前导星壳）：渗透工具箱****价格：140gp 重量：15磅
            # ——源数据加粗不一致：导言标题有 ** 前缀、条目标题裸形态，
            # **** 分隔符后为字段/正文 → 开条目（title 取分隔符前）
            if "****" in l:
                head, _, tail = l.partition("****")
                head = head.strip()
                if head and not head.endswith(("。", "！", "？")):
                    item = open_item(title=head, title_en="",
                                     text=tail.strip())
                    cur = item
                    i += 1
                    continue
            # 中英粘连导言（内海炼金工具箱 INNER SEA ALCHEMY）：空格拆离，
            # 英文块截到中文/行尾（KITS炼金术士… 粘连正文不进 title_en）
            gm = _RE_CN_EN_SPACED.match(l)
            if gm and len(l) <= 60:
                en = re.match(r"^([A-Za-z][A-Za-z0-9'’\- ]*?)(?=[一-鿿]|$)",
                              gm.group(2).strip())
                item = open_item(title=gm.group(1),
                                 title_en=en.group(1).strip() if en else "",
                                 text="")
                cur = item
                i += 1
                continue
            # 其余：价格表行 / 地区表格行 / 表注 / 正文段 → 并入
            cur = self._unch_append(items, cur, l, cluster="S10")
            i += 1
        return items

    # S9 官方FAQ page_837（问答流：星壳节标题 + 主题名：问题　　答案）
    _RE_FAQ_SECTION = re.compile(r"^\*\*(.+?)\s*\(([^)]*)\)\*\*$")
    _RE_FAQ_ANCHOR = re.compile(r"([^　。！？!?～~*:：]{1,40})[：:]")

    @staticmethod
    def _faq_clean_name(name: str) -> tuple:
        """FAQ 主题名清理：先拆尾部括号对（中文（EN）），再剥离粘连前缀。
        '法术掌握 (Spell Mastery)' → ('法术掌握', 'Spell Mastery')
        '”）增强召唤' → ('增强召唤', '')；'xterity…attacks.高等摔绊'
        → ('高等摔绊', '')——英文答案段尾句点 + 中文主题名同段连排。"""
        m = re.match(r"^(.*?)[（(]([^）)]*?)[）)]\s*$", name)
        if m:
            cn, en = m.group(1), m.group(2)
        else:
            cn, en = name, ""
        # 剥离答案段尾粘连前缀（到最后一个句号/括号/右引号等分隔符；
        # 右弯引号 ” 常见于英文答案段尾引文 + 中文主题名同段连排）
        cn = re.sub(r"^.*[。！？!?～~」』】》）).”]", "", cn)
        return cn.strip(), en.strip()

    def _split_faq(self, text: str, source_name: str = "") -> list:
        """S9 官方FAQ page_837 问答流。

        形态：约 80 字符硬断行 → 先 flat 拼接为单行流再切（断行在词/字中
        任意位置）；2 个星壳节标题 → intro（空 text，检索端降权）；节体内
        按「主题名：」锚点扫描切条目——中文条目判据 = 冒号后 500 字符窗口
        内先遇「？」且问号前无句号（半角含答案段尾句点，如 '…attacks.高等
        摔绊：'），英文条目判据 = 先遇「?」且主题名首字母大写（排除答案内
        小写冒号伪锚，如 'transform: you always count…'）；【译注】块整体
        跳过；无锚英文问题（When I use a magic item…）自然并入上一条目
        text。text = 锚末尾到下一锚的原文切片（全角空格连排保留）。
        """
        items = []
        flat = re.sub(r"[\r\n]+", "", text)
        # 星壳节标题拆分：**中文 (EN)**
        parts = re.split(r"(\*\*[^*\r\n]+\*\*)", flat)
        for i in range(1, len(parts), 2):
            head = parts[i]
            m = self._RE_FAQ_SECTION.match(head)
            if m:
                cn, en = m.group(1).strip(), m.group(2).strip()
            else:
                cn, en = head.strip("*").strip(), ""
            items.append(self._new_item(
                "intro", format_cluster="S9", title=cn, title_en=en, text=""))
            body = parts[i + 1] if i + 1 < len(parts) else ""
            if not body:
                continue
            # 锚点扫描（500 字符窗口判据）
            hits = []
            for mm in self._RE_FAQ_ANCHOR.finditer(body):
                pos, name = mm.start(1), mm.group(1)
                if "译注" in name:  # 【译注：…】块内部问句整体跳过
                    continue
                seg = body[pos + len(name) + 1: pos + len(name) + 501]
                qi, enq = seg.find("？"), seg.find("?")
                if qi < 0 and enq < 0:
                    continue
                if qi >= 0 and (enq < 0 or qi < enq):
                    # 中文条目：问号前不得有句号（英文答案段尾句点粘连伪锚）
                    if "。" in seg[:qi] or "." in seg[:qi]:
                        continue
                else:
                    # 英文条目：主题名首字母须大写（答案内小写冒号伪锚）
                    s = name.lstrip(" .:：·)")
                    if not s or not s[0].isupper():
                        continue
                hits.append((pos, name))
            for j, (pos, name) in enumerate(hits):
                end = hits[j + 1][0] if j + 1 < len(hits) else len(body)
                text_slice = body[pos + len(name) + 1: end].strip()
                cn, en = self._faq_clean_name(name)
                if en == "" and cn and cn[0].isupper() and \
                        not re.search(r"[一-鿿]", cn):
                    en = cn  # 英文条目 title_en = 自身（供英文检索匹配）
                items.append(self._new_item(
                    "rule", format_cluster="S9", title=cn, title_en=en,
                    text=text_slice))
        return items

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------

    def split_into_items(self, text: str, *, source_name: str | None = None) -> list[dict]:
        if not text.strip():
            return []
        first = text.lstrip().splitlines()[0].strip()
        # S6 导言（page_161/162：URL 行剥除后首行为星壳章节标题，无主标题结构）
        if source_name and ("page_161" in source_name or "page_162" in source_name):
            return self._split_intro(text)
        # S8 巨人猎手新技能选项（GIANT-source 注释锚点形态，与 S7 分派互斥）
        if source_name and "巨人猎手手册" in source_name:
            return self._split_giant(text, source_name)
        # S9 变体规则（批次 B2）：河域子民复用 S7 解析器（cluster=S9 区分）；
        # 异能 page_315 断行星壳标题；科技 page_760 行内连排
        if source_name and "河域子民" in source_name:
            return self._split_unchained(text, source_name, cluster="S9")
        if source_name and "page_315" in source_name:
            return self._split_occult(text, source_name)
        if source_name and "page_760" in source_name:
            return self._split_tech(text, source_name)
        if source_name and "page_837" in source_name:
            return self._split_faq(text, source_name)
        # S10 装备物品卡（工具和技能工具包：多来源拼接 + 尾部整段重复去重）
        if source_name and "工具和技能工具包" in source_name:
            return self._split_equipment(text, source_name)
        # S7 Unchained 规则型（B1 6 文件：造物与专业替换/技能解放/混职/
        # 背景技能/整合技能/分组技能；全角括号标题形态，与 S1 半角括号区分）
        if source_name and any(
                k in source_name for k in
                ("page_647", "page_648", "page_649", "背景技能",
                 "整合技能", "分组技能")):
            return self._split_unchained(text, source_name)
        # S1/S2/S3 CRB 页：主标题 **中文 (English) (属性)**
        head = self._parse_main_title(first)
        if head:
            return self._split_crb_page(text, head)
        # S4 UI 页（星壳 / 文本双空格 / 断行标题，前 1~3 行重组判定）
        ui_lines = [l.lstrip() for l in text.splitlines() if l.strip()]
        if ui_lines and self._ui_head_lines(ui_lines)[0] is not None:
            return self._split_ui_page(text)
        # S5 语言汇总（小节标题行/描述行不匹配条目正则，内容判定：
        # 前几行出现任一语言条目形态（除 G 纯名，防其他页误入））
        head_lines = [l.strip() for l in text.splitlines()[:10] if l.strip()]
        if any(self._is_lang_entry_head(l) for l in head_lines):
            return self._split_language(text)
        return []
