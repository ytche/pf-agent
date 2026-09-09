"""race.py — 种族格式解析（7 格式簇，12 枚举 component_type）。

设计（2026-08-04，元数据定稿 + 公共层抽取后实现）：
- normalize 链 = 4 条 race 特有前置规则 + 公共层安全子集（feat 链裁剪，
  已验证对 race 形态无副作用——验证脚本占位正则 `(a)` 曾误报拆词假象，
  实为 `_split_inline_fields` 的 `\1\n` 模板在占位正则命中 `a` 处插换行；
  用真实/永不匹配占位重跑后确认公共层本身安全）
- race 特有缺口（公共层不覆盖的形态）：
  1. 属性调整星壳（`**+2****敏捷，**` → `**+2敏捷，**`）
  2. 出自行数字跨行（`pg. \n5`，公共 `_RE_CROSS_EN` 只含字母）
  3. 星标拆中文（`**魅****影身姿` → `**魅影身姿`）
  4. 译者行剥除（含 URL 的 `译者：` 行）
  5. 裸文本空格形态（`霜生种 Born of Frost`，公共 `_wrap_bare_cn_en_lines`
     要求中文紧贴英文，复用其 `_is_fragment_title` 守卫）
- split = 章节状态机：章节标题关键字驱动条目 kind（alt_trait/fcb_entry/
  race_feat/race_spell/race_item/race_archetype/race_trait/race_overview），
  intro 态首个带括号标题 → race_intro、后续 → race_trait、裸中文标题 →
  race_sidebar；哨兵行绑定 replaces、出自行绑定 source、同名标题合并
  （PA 三重标题）、速查行并入不产伪条目。
"""

import re

from vectorizer.formats.base import BaseFormat
from vectorizer.formats.normalize_common import (
    _RE_FIELD_LABEL_BARE,
    _RE_STRIKE_SHELL,
    _RE_FIELD_LABEL_COLON,
    _RE_INDEX_LINE,
    _RE_REPLACE_CLAUSE,
    _fix_bare_label_colon_nextline,
    _fix_colon_title_glue,
    _fix_elided_quadruple_title,
    _fix_fc1n_no_closing_star,
    _fix_fc1v_paren_en,
    _fix_field_star_left,
    _fix_field_star_right,
    _fix_label_trailing_star,
    _fix_quad_star_halfparen,
    _fix_quadruple_star,
    _fix_spaced_parens_cn_en,
    _fix_star_outside_en,
    _fix_star_outside_en_type,
    _fix_star_shell_remnants,
    _is_fragment_title,
    _is_multiword_en,
    _is_title_case_en,
    _merge_cross_line_en,
    _merge_table_continuation,
    _merge_type_seg_line,
    _normalize_whitespace_title,
    _split_closed_title_colon,
    _split_closed_title_source,
    _split_inline_fields,
    _split_paren_content,
    _split_title_glue_cn_en,
    _split_title_glue_paren,
    _strip_hr_lines,
    _strip_http_links,
    _wrap_bare_cn_en_allcaps,
    _wrap_bare_cn_en_lines,
    _wrap_bare_field_labels,
    _wrap_bare_titles,
    _wrap_hash_titles,
    _wrap_hash_titles_cn_en,
    _wrap_hash_titles_type_en,
    _wrap_index_line,
)


# ==================== race 特有常量 ====================

# 出自行数字跨行：`pg. \n5` / `《阴影血脉 \npg. \n4》`
# 公共 `_RE_CROSS_EN`（`[a-zA-Z,]\n[a-zA-Z]`）不含数字/中文-英文边界，出自行
# 断行是种族源常态（Prepare 勘探 442 行 `pg. \nN` 断行）。
# 换行前容忍星壳残留（`《阴影血脉**\npg. 5****》`——书名尾星壳挡路，
# 2026-08-04 race 修复：剥壳后合并，出自行才能正确解析）
_RE_SOURCE_CROSS_DIGIT = re.compile(r"([A-Za-z.])\*{0,4}[ \t]*\r?\n[ \t]*(\d)")
_RE_SOURCE_CROSS_CN_PG = re.compile(r"([一-鿿])\*{0,4}[ \t]*\r?\n[ \t]*(pg\.)")

# 出自行书名内尾星剥除：`出自《阴影血脉 pg. 5****》**` → `《…pg. 5》`
#（跨行合并后残留，污染出自行可读性）
_RE_SOURCE_BOOK_TAIL_STAR = re.compile(r"《([^《\n]*?)\*{2,}》")

# 属性调整星壳行：`**+2****敏捷，****+2****魅力，****-2****感知**：…`
# 触发 = 行首 `**数值**` 闭合星后直接跟汉字（星外汉字 = 粘连形态）。每段
# 双星加粗相邻成 4 星（`**+2**` + `**敏捷，**`），数值后星数 2~4 兼容。
_RE_ABILITY_ADJ_LINE = re.compile(r"^\*\*[+−-]?\d\*{2,4}[一-鿿][^\n]*$", re.M)

# 星标拆中文：`**魅****影身姿` → `**魅影身姿`（Prepare 勘探：星标把中文名拆
# 段是常态，公共 `_fix_quadruple_star` 需前后 4 星闭合，此形态不覆盖）。
# `**魅****影` = 双星加粗相邻成 4 星（`**魅**` + `**影身姿**`）。
_RE_CN_STAR_CN_GLUE = re.compile(r"([一-鿿/])\*\*\*\*([一-鿿])")

# Obsidian 图片引用（M10 收尾，2026-08-04）：源数据 `![[图片]](URL)` 形态
# 5 处（page_1456/1016/BotN），`_strip_http_links` 剥 URL 后留 `![[图片]`
# 残壳污染条目 text——完整（含 URL）或截断（无 URL）形态整串剥除。
_RE_IMAGE_REF = re.compile(r"!\[\[图片\]\]?(?:\([^)]*\))?")


# 四星嵌套标题：`**九命天猫****（****Nine Lives****，又译９命）******` →
# `**九命天猫（Nine Lives，又译９命）**`。源数据「双星加粗段相邻」形态，
# `_RE_QUAD_STAR` 需星对星（`****X****`）不匹配（内嵌 `****（`），公共
# `_fix_quad_star_halfparen`（guard 版）只认 `）`/`)` 前 4 星截断形态，
# 此形态不拆——仍须在本函数先归一为标准标题供 `_RE_TITLE` 识别。
# 组2 = HTML 加粗段拆裂中段（M10 收尾，2026-08-04）：`**高等地精****自燃术
# （****Greater Fire Body, Ex****）**`——中文名被相邻加粗段拆两段，合并成
# 单标题。须在 glue 拆行前处理（glue 组2 以中文开头会先拆行成「高等地精」
# +「自燃术」两个伪条目）。组3 要求 4 星包围（`（****EN****`）——章节+条目
# 粘连 `**章节****条目（EN）**`（KN115）括号无星，天然豁免，仍走 glue 拆行。
# 组5 = 类型标签（`〔战斗〕`）保留供 feat_type 判定。
# KN133（2026-08-04）：组1 放宽 `{2,}`→`{1,}`（`**猎****巫人` 拆裂处无词
# 边界，段1 单字）+ 段间 4 星可重复（`**狐妖之****魅****（****` 双段拆裂，
# 狐妖之魅 P1）——HTML 拆裂中段的两种漏网形态归入同一归一
# KN133（2026-08-04 续）：EN 类型段后 `\*{0,4}`——跨行 EN 双段形态
# `**狐妖之****魅****（****Kitsune's**** \nCharm, ****Sp****）**` 经
# `_merge_cross_line_en` 合并后成 `（****Kitsune's Charm, ****Sp****）`，
# 类型段 `Sp` 后仍有一组 4 星再 `）`；原 `[)）]` 前无星容差导致整体失配，
# 狐妖之魅 P1 未闭环（单段 `****EN****）` 形态不受影响，0~4 星均可）
_RE_QUAD_NESTED_TITLE = re.compile(
    r"\*\*([一-鿿/]{1,})(?:\*\*\*\*([一-鿿A-Za-z/·\-－]{1,}))*\*{0,4}[（(]\s?\*\*\*\*([^*\n]+)\*\*\*\*([^*\n]*?)"
    r"\*{0,4}[)）]([〔［【][^〕］】]*[〕］】])?\*{2,6}"
)

# 译者行：含 URL 的译者行（PA 形态 `[**http…**](http…)  **译者：…`）或
# `**译者：…**` 行。剥除不残留。（行内 `【译者吐槽：…】` 是正文一部分，
# 测试要求保留——正则只匹配 `译者：` 冒号紧跟形态，`译者吐槽` 后是汉字
# 不匹配，天然豁免。）
_RE_TRANSLATOR_LINE = re.compile(
    r"^\s*(?:\*{0,2}\[?\*{0,2}https?://[^\n]*|(?:\*{0,2})(?:译者|翻译|校对)[：:][^\n]*)$",
    re.M,
)

# 裸文本空格形态：`霜生种 Born of Frost  你身体…`（公共 `_RE_BARE_CN_EN_LINE`
# 组 1 后无 `\s*`，中文与英文之间必须紧贴——feat 段流形态；race 源「中文 空格
# 英文」是常态，空格变体在此覆盖）。组 3 为可选类型括号（`（战斗）`，并入标题
# 尾缀 `〔战斗〕` 供 split 判别 race_feat），组 4 为汉字开头正文（en 后可直接
# 跟汉字，如 `破雾目镜 Fog-Cutting Lenses装备位置：…`）。
# M16（2026-08-04）：去 `^` 行首锚定——霜巨人聚合文件把段落并成单行，条目
# （裸「中文 空格 EN」）在行中（行首是章节引言）。守卫：组 1 前字符非汉字
# （`(?<![一-鿿])`）——正文句引用 `…使用有仇报仇 Ancestral Enmity 专长…`
# 前字符是汉字不拆；`4000GP霜血斩斧 Frostblood Axe装备位置：` 前字符是字母
# （价格单位 GP）仍拆。
_RE_RACE_BARE_CN_EN_LINE = re.compile(
    r"(?<![一-鿿])([一-鿿]{2,})\s+([A-Za-z][A-Za-z'’\.\- ]*?)"
    r"(?:[（(]\s*([^）)]+)\s*[)）]\s*([一-鿿][^\n]*)?|([一-鿿][^\n]*))",
)

# race 字段标签集（裸标签拆行/行首包裹共用，形态与 feat 同构）
_RACE_FIELD_ALT = "|".join([
    "先决条件", "专长效果", "特殊情况", "装备位置", "灵光", "施法者等级",
    "价格", "重量", "制造条件", "制造成本", "学派", "环级", "施放时间",
    "射程", "范围", "持续时间", "豁免", "法术抗力",
])

# 条目流态（race_item/race_feat/race_spell）下 `**X**：` 的字段标签集：
# X ∈ 集 → 字段行并入当前条目；否则 → 新条目（物品/专长/法术名，
# page_1456 驱兽剂/攀爬藤蔓/抓握藤蔓形态）。主集 `_RACE_FIELD_ALT`
# 已覆盖装备/法术字段，此处补统计缺口（2026-08-04 全库字段行普查）。
# KN100 追加小节（2026-08-04 全库扫描 40 候选 11 文件）：毒药/陷阱/
# 怪物 stat block 字段（类型/频率/效果/治愈/发作频率/毒素）、物品字段
# （部位/价值/制造价格/价格调整）、专长效果字段（触发/重设/需求/储存）
# 与怪物速度裸值行——词表缺口导致 race_item/feat/spell 态切出伪条目。
_ENTRY_FLOW_FIELD_LABELS = _RACE_FIELD_ALT.split("|") + [
    "特性效果", "位置", "特殊说明", "通常状况",
    "效果", "频率", "类型", "治愈", "发作频率", "价格调整", "部位",
    "价值", "制造价格", "毒素", "通常情况", "触发", "重设", "需求",
    "储存", "速度", "强韧豁免",
    # 动物伙伴 stat block 字段（2026-08-04 M10 收尾：page_1412 鼠族
    # `**骑乘用巨鼠动物伙伴****起始属性: \n体型** 中型;…` 粘连拆行后
    # `**起始属性: ` 裸冒号行在 race_item 态（鼠族装备章节）被切伪条目，
    # 主条目「骑乘用巨鼠动物伙伴」空壳——数据全在伪条目 text 中）
    "起始属性",
    # M12 词表缺口（2026-08-04 全库字段普查）：「条件」（page_440/441
    # 魔法物品制造字段链）、「推荐科研发现」（page_166 地精炼金术士）
    # ——条目流态裸标题冒号行被 L1683 词表判定切伪条目，字段值吞进
    # 伪条目 text。注意「弱点」刻意不入此表：page_163 唯一裸「弱点」
    # 行是速查残留段正文（M18 吐槽删除范畴，S4 簇锁定保持独立条目），
    # stat block 形态 `**弱点（Weakness）**：` 走 race_trait 态由
    # _ARG_FIELD_LABELS 覆盖（page_204 狗头人）
    "条件", "推荐科研发现",
    # M21 词表缺口（2026-08-04）：「备注」——半兽人 page_17 狂暴专长
    # 字段链末尾 `**备注**：如果该伤害仍会使你失去意识…` 被切
    # title=备注 的 race_feat 伪条目（语义=前条目的补充说明，并入）
    "备注",
]

# ARG 标准种族页 race_trait 态的字段行标签（勘探 field_labels_seen，
# page_164 卓尔页 7 标签）：命中 → 字段行并入当前条目；否则 →
# 独立特性条目（`**起始语言**：…` 纯中文形态，2026-08-04 审计修复
# 伴生——race_spell 子串误判修复后起始语言回到 race_trait 态，既有
# 「并入 cur」分支会吞掉独立特性）
_ARG_FIELD_LABELS = frozenset(
    {"体貌描述", "社会", "关系", "阵营和宗教", "冒险", "常用男名", "常用女名",
     # BotN 吸血裔亚种字段链（2026-08-04 M1 拆行暴露）：`**祖先**：僵尸`/
     # `**属性调整**：+2力量…` 等星壳字段行——race_trait 态并入亚种条目，
     # 不产字段伪条目（僵尸裔/诺斯弗拉图裔/维塔拉裔 4 亚种 × 5 字段 = 20）
     "祖先", "属性调整", "替换技能调整", "替换类法术能力", "替换弱点",
     "替代技能调整", "替代类法术能力", "替代弱点",
     # 巫团血脉 BotC 替换儿亚种字段（2026-08-04 BotC 幽灵 cur 修复前置，
     # 与 BotN 同构：鬼婆种族特性/鬼婆血统觉醒 并入亚种条目）
     "鬼婆种族特性", "鬼婆血统觉醒",
     # BotC 替换儿字段（2026-08-04 M10 裸行转星回归：`典型阵营：混乱中立`/
     # `替换属性调整：+2力量…` 裸字段行被转星后走 race_trait 态切条目
     # 分支——M1 前裸形态并入 cur。词表补全恢复并入）
     "典型阵营", "替换属性调整",
     # BotS 星壳来源行（2026-08-04 M10：`**塞卡利亚****来源：《海洋血脉》
     # 第6页` 粘连拆行 → `**来源**：…` 走 race_trait 态切「来源」伪条目
     # 吞掉塞卡利亚背景段 → 标题条目空 text。入词表并入 cur 恢复）
     "来源",
     # 动物伙伴 stat block 字段（2026-08-04 M10 收尾：page_1412 鼠族
     # `**骑乘用巨鼠动物伙伴****起始属性: \n体型** 中型;…` 粘连拆行后
     # `**起始属性: ` 裸冒号行被 race_trait 态切伪条目「起始属性」，
     # 主条目「骑乘用巨鼠动物伙伴」空壳——数据全在伪条目 text 中）
     "起始属性",
    }
)

# KN100 统一字段词表：裸标题/带括号标题分支（`**效果**`、`**先决条件
# （Prerequisite）**` 形态）的并入守卫共用集 = 条目流字段集 ∪ ARG 字段集。
# ARG 合法特性标题（感官/防御/法术抗力/特性/起始语言）刻意不入表——
# 它们是独立特性条目（B 类），由 race_trait 态 COLON 分支正常切出。
_ALL_FIELD_LABELS = frozenset(
    set(_ENTRY_FLOW_FIELD_LABELS) | set(_ARG_FIELD_LABELS)
)
_RE_RACE_FIELD_SPLIT_BARE = re.compile(
    rf"([。！？])(?=[^。！？\n]{{0,6}}(?:{_RACE_FIELD_ALT})[：:])"
)
_RE_RACE_BARE_FIELD_LABEL = re.compile(
    rf"^([ \t　]*)((?:{_RACE_FIELD_ALT})[：:])(?=[ \t　]*\S|$)",
    re.MULTILINE,
)
_RE_RACE_BARE_FIELD_LABEL_PERIOD = re.compile(
    rf"^[ \t　]*((?:{_RACE_FIELD_ALT}))[。．](?=[ \t　]*\S|$)",
    re.MULTILINE,
)

# ---- split 层常量 ----

# 章节标题关键字（顺序敏感：`特性替换` 必须先于 `种族特性`；`奇物/魔法物品`
# 先于 `装备`——`霜巨人魔法物品` 无括号裸标题也命中）
_SECTION_KEYWORDS: list[tuple[str, list[str]]] = [
    ("race_item", ["奇物", "魔法物品", "装备"]),
    ("race_spell", ["法术"]),
    ("race_feat", ["专长"]),
    ("fcb_entry", ["天赋职业", "职业奖励"]),
    # 三个排列形态全覆盖（2026-08-04 KN116 残留修复）：`种族特性替换` /
    # `种族替换特性`（ISR `## 内海种族 ISR 其他种族替换特性` H2）/
    # `替换种族特性`（BotC `## 替换种族特性` H2）——前二者不含「种族特性」
    # 子串不会误落 race_trait，第三者须先于 race_trait 关键字命中
    ("alt_trait", ["特性替换", "种族替换特性", "替换种族特性"]),
    ("race_archetype", ["职业变体", "变体职业", "骑士团变体"]),
    ("race_trait", ["种族特性", "背景元素"]),
    ("race_overview", ["概述"]),
]

# 裸标题法术章节的正文句排除虚词（2026-08-04 审计 #103 第二版）：怪物法典
# 合法裸章节 = `种族名+法术`（地精法术/灰矮人法术/藤蔓莱西法术，无 EN 括号，
# normalize 后全库 10 个，均 ≤6 字、无句法虚词）；正文句误包
# （`当你施放该法术`/`你的命令使你创造的阴影与黑暗法术`/`这个法术` 等，
# normalize 后全库 28 行）均为整句，含句法虚词/代词（你/这/当/如/在…）。
# 逐字验证：10 合法全不含，28 正文句全含 ≥1 → 单字集合精确分隔（不依赖
# 长度——`这个法术` 4 字与 `地精法术` 同长，长度判据不可靠）
_SPELL_SECTION_BARE_BLOCKERS = frozenset(
    "这该此当如若你我他她在和或与将把被所的于从向对给更不也就而是有"
)

# 怪物数据块标准字段章节（裸 `中文（EN）` 独占一行，`---` 包裹）：公共层
# `_wrap_bare_titles` A 分支 elided 星壳化后 `_RE_TITLE` 会拆成 title='描述'
# 的伪条目（冒险之路AP_怪物 7 怪物 ×4 章节 = 28，2026-08-04 K 簇回归）→
# split 层并入当前怪物主体条目。词表 = PF 怪物数据块标准章节（格式知识，
# 同 `_RACE_FIELD_ALT` 先例）；「防御（Defense）」等特性名不得入表
# （page_204/205/323 真条目验证）
# 章节标题去重判据（2026-08-04 K 簇修复）：前一 cur 无正文且属于章节/碎片
# 形态 → 纯章节标题不入库。三路覆盖：①章节词/词尾（种族替换规则等原生
# 章节标题，不含词但词尾为 种族/亚种/天赋）②`[[fc:elided]]` 标记（normalize
# 跨行/粘连标题重写产物，剥除标记后信息丢失的碎片）③kind 为 race_intro/
# race_sidebar（文件主标题/空 intro）。破敌之锤（race_archetype 无标记）与
# 审判者（fcb_entry）是真实条目必须保留——误弹二者正是本判据引入动因
_DEDUP_SECTION_WORDS = (
    "种族替换规则", "新种族规则", "种族亚种",
    "备选种族特性", "种族特性替换", "替换种族特性",
    "可选天赋职业奖励", "天赋职业选项", "天赋职业奖励",
    "职业变体", "骑士团变体", "魔法物品", "专长", "法术",
    "概述", "怪物", "装备", "奇物", "取代",
    "背景元素",  # BotN 吸血裔章节词（2026-08-04 全量核查 M1 拆行后空壳防残留）
    "种族背景",  # 怪物种族页章节壳（2026-08-04 M10 收尾：page_940 卡萨达人
    # `**种族背景(Race Traits)**(来源：` 跨行尾注形态——章节标题壳空 text）
)

# GLUE 守卫词表：4 星粘连前段 `**X` 命中章节词时不合并（拆行处理），
# 星内单字拆裂（`**魅****影身姿`）合并（2026-08-04 全量核查 M1 守卫升级，
# 见 `_fix_cn_star_cn_glue`；前段最长 10 字 + `**` 闭合 ≤ 14 字符窗口）
_GLUE_GUARD_WORDS = tuple(
    w for _, kws in _SECTION_KEYWORDS for w in kws
) + _DEDUP_SECTION_WORDS


def _is_dedup_section_cur(cur):
    """前一 cur 是否为纯章节标题（无正文的章节/碎片形态）→ 应弹"""
    if cur is None:
        return True
    name = cur.get("name") or ""
    if not name:
        return True
    if any(w in name for w in _DEDUP_SECTION_WORDS):
        return True
    if name.endswith(("种族", "亚种", "天赋")):
        return True
    if cur.get("_elided"):
        return True
    if cur.get("kind") in ("race_intro", "race_sidebar"):
        return True
    # 无正文的变体职业壳标题（如破敌之锤 Foehammer：源数据标题后直接是特性
    # 子条目序列，无介绍散文）不入库——能力全在特性子条目 text 中（子条目
    # 正文均含「破敌之锤」字样，检索等价命中），空壳条目违反 race 空 text=0
    # 闸口（KN085 口径）。有正文的变体职业（督教/锻造大师等）不受影响——
    # 调用处 `not cur.get("text")` 前置保证（2026-08-04 K6 决策）。
    if cur.get("kind") == "race_archetype":
        return True
    # 无正文的替代特性壳标题（2026-08-04 M10 收尾：page_815 蒿兰人
    # `**替换自然魔法**` 裸标题后直接跟「甜气」子条目——替代特性组的
    # 具体能力在子条目 text 中（「这个种族特性取代了自然魔法」），检索
    # 等价命中，同 K6 破敌之锤口径；有正文的替代特性（替换墨汁云 M10 已
    # 修复并入）不受影响——调用处 `not cur.get("text")` 前置保证）
    if cur.get("kind") == "alt_trait":
        return True
    return False

_MONSTER_BLOCK_SECTIONS = (
    "描述", "防御能力", "攻击能力", "数据", "生态", "习性",
    # M15（2026-08-04）：冒险之路AP_怪物 stat block 裸行章节标题
    # （`生态背景（Ecology）` / `特殊能力（Special Abilities）` /
    # `栖息地与社会（Habitat & Society）`，`---` 分隔形态）转星后
    # 未入词表切伪条目（全库 23 个，全在 AP_怪物）——补词并入前条目
    "生态背景", "特殊能力", "栖息地与社会",
)

# 带括号标题：`**中文（EN，又译…）**` / `**中文**（EN）`（星闭合后括号，
# 九命天猫形态）/ `**中文 (EN)**`（半角+空格）/ `**中文**（EN）` 括号直接
# 行尾无闭合星（FCB 章节标题形态）/ 尾缀类型（`〔战斗〕`）/ 冒号后缀（`：值`）
# 中文与括号间 0-4 星（`**援护防御****（Defensive Aid, Ex）**` 跨行 EN 合并
# 后 4 星残留形态，2026-08-04 page_160 修复）；组1 容忍 `——` 双名标题
# （`**神裔——圣战魔法（Aasimars—Crusading Magic）：**` ISR 形态，
# 2026-08-04 修复——组1 贪婪到括号前）
_RE_TITLE = re.compile(
    # M10：行首 elided 前缀容错（`[[fc:elided]]**中文（EN）**`——公共层
    # 跨行/粘连标题重写产物，前缀剥除后恢复标准标题形态供 split 匹配；
    # whitespace 前缀在 normalize 链尾剥除，此处只容错 elided）
    r"^(?:\[\[fc:elided\]\])?\*\*[　]*"
    r"([一-鿿][一-鿿A-Za-z/·：:\-－]{1,}(?:——[一-鿿A-Za-z/·：:\-－]{1,})?)"
    r"(?:\*{0,4})[（(]\s?([^）)]+)[)）]"
    r"([〔［【][^〕］】]*[〕］】])?"
    # M10：第二括号容错（BotS 双括号形态 `**喷射（Jet）（1 RP）**`——
    # `（1 RP）` 是 RP 标注不是类型标签，组2 只取英文名；title 保持
    # 中文名，RP 值不进 title）
    # M10：第二括号后 lookahead 守卫（`(?=[：:]|\*{0,4}(?:[：:]|$)|$)`）——
    # 只吞标题尾部的 RP/类型括号（`（1 RP）：正文`/`（1 RP）**` 行尾闭合
    # 星/`（1 RP）` 独立行尾）；正文里的括号（`…水生（aquatic）子类。`，
    # 塞卡利亚人形怪物整行星壳形态）不吞——否则组尾 `([：:].*)` 找不到
    # 冒号整行失配，标题并入散文丢失（M10 实测）
    # W4（2026-08-04 KN133）：lookahead 加 `[〔［【]` + 第二括号后新增来源
    # 标注尾缀组——BoS 删线壳剥除后形态 `**X（EN）（1RP）【BoS】**：正文`
    # （page_398 面纱之后/混合视觉/幽暗居民/昏暗精准/暗影猎手等 8 条）：
    # 原 lookahead 遇 `【BoS】` 失败整行失配，标题并入前一条目
    r"(?:[（(]\s?[^）)]+[)）](?=[：:]|汇总|\*{0,4}(?:[：:]|$)|$|[〔［【]))?"
    r"(?:[〔［【][^〕］】]*[〕］】])?(?:汇总)?(?:\*{0,4})([：:].*)?$"
)
# 组1 允许混排英文/数字/全角冒号/连字符（2026-08-04 K 簇修复）：
#   边栏标题「**边栏：非人类魔裔（Blood of Fiends）**」（含「：」）
#   page_806 混排「**兽态人Skinwalker种族特性**（10RP）」
#   「**蝙蝠人后裔Werebat－kin（血印bloodmarked）**」（含全角连字符－）
# 星后全角空格（切利亚斯 `**　　嗜火者（Pyrophile）**：`）在组1 前剥除。

# 裸中文标题（无括号无冒号，整行星包裹）：`**霜巨人**` / `**非人类魔裔**` /
# `**兽态人亚种Skinwalker Heritages**`（首字符中文 + 后续混排，2026-08-04）
# 组1 容数字（2026-08-04 KN133：page_815 `**替换+2天生护甲**` 组标题——源
# 数据跨行星壳修复为单行后，原字符类不容 `+`/数字落散文分支并入前条目；
# 全库含数字裸星行仅 2 处，另 1 处 `**此特性替换奖励技能PS2**` 是哨兵行
# 被 _RE_SENTINEL 先行消费，零误伤）
_RE_BARE_CN_TITLE = re.compile(r"^\*\*([一-鿿][一-鿿A-Za-z/·\-－\s\d+]{1,})\*\*$")
# 替换特性组句（KN131 前瞻判据）：`X角色可以选择以下种族特性替换原本的种族特性。`
# ——ISR 核心替换特性页文件（page_752）开场白，聚合文件同句（7 组）。全库仅
# 两个文件出现，无歧义。聚合文件靠 `## 核心种族替换特性` 章节切 alt_trait 态，
# 页文件无章节标题 → 组句所在裸分组标题后一行为该句时切 alt_trait 态（同语义）
_RE_ALT_TRAIT_GROUP_INTRO = re.compile(
    r"^[一-鿿]{2,6}角色可以选择以下种族特性替换原本的种族特性。?$"
)
# 属性调整行（值星壳形态 `**+2敏捷，+2体质**：正文`）：`_RE_TITLE` 组1
# 不容 `+` 数字开头、`_RE_BARE_CN_COLON` 组1 汉字开头均不匹配——M4 前走
# 散文分支并入 cur（~20 族粘 intro 尾），蝮血裔（page_385 4 星章节形态）
# 因 SEC 弹 cur 后 cur=None 改走 pending 被 COLON 分支覆盖 → 完全丢失
# （2026-08-04 全量核查 M4）。组1 数字开头天然隔离普通字段行。
_RE_ABILITY_ADJ_TITLE = re.compile(r"^\*\*([+−-]?\d[^\n*]*)\*\*[：:](.*)$")

# 纯中文条目（星包裹+冒号值）：`**圣武士**：…`（FCB 态）
_RE_BARE_CN_COLON = re.compile(r"^\*\*([一-鿿/]{2,})\*\*[：:](.*)$")
# 裸职业行（无星壳）：`野蛮人：在对抗…`（BoS 剪影人 15/窃影鬼 14 条 FCB，
# 2026-08-04 全量核查 M7）——`_RE_BARE_CN_COLON` 需 `**` 星壳不命中，整节
# 并入最后一条目。仅 fcb_entry 态消费（FCB 正文均为 `职业：奖励` 形态，
# 无字段行场景）；其他态行首 2+ 汉字冒号行是散文，不切伪条目
_RE_BARE_CN_COLON_UNSTARRED = re.compile(r"^([一-鿿/]{2,})[：:](.*)$")
# 裸职业行守卫：组1 含 fcb 章节关键字（BotB `天赋职业选项吟游诗人：`
# 裸章节+条目粘连行）→ 非职业条目，不切伪条目（2026-08-04 M7 全库
# 定性发现）。职业名不含这些词，零误伤
_RE_FCB_SECTION_WORD = re.compile(r"(?:天赋职业|职业奖励)")
# 星壳闭职业行：`**吟游诗人：**从德鲁…`（闭合星在冒号后，page_814
# 伽瑟兰/page_815 蒿兰人 FCB）——`_RE_BARE_CN_COLON` 需星壳闭合后跟
# 冒号（`**X**：`）不匹配、裸版组1 需汉字开头不匹配，全库 147 处
# （page_10/401-404/BotC/BotS 等非 FCB 态由态守卫隔离，保持并入 cur）
_RE_BARE_CN_COLON_STAR_CLOSED = re.compile(r"^\*\*([一-鿿/]{2,})[：:]\*\*(.*)$")

# 哨兵行：`**此特性替换黑暗视觉**` → 绑定其后条目的 replaces
_RE_SENTINEL = re.compile(r"^\*\*此特性替换[^*\n]+\*\*$")

# 半兽人聚合 FCB 形态（page_17，2026-08-04 KN107）：`**职业（EN）《书>: `（无
# 闭合星，行尾 `: `）+ 次行 `**【…】…` 正文，或 `**职业（EN）《书》：**正文`
# （闭合星同行）。《书》为来源标记（ARG/APG/HA/ACG/OA），归一为标准 FCB 标题
# 形态（`**职业（EN）：**正文`）供 `_RE_TITLE` 识别——J 簇 UW/WO 先例：来源
# 标记不残留 text；同职业多书多条各自保留（37 职业含重复条 = 40 条目）。
# 闭合符实测为半角 `>`（码点 0x3e，CHM 转换产物），全角 `》` 兼容。
_RE_FCB_BOOK_SOURCE = re.compile(
    r"^(\*\*[一-鿿][^（\n]*?（[^）]+）)《[^》>\n]*[》>]"
    r"[:：][ \t]*\*{0,2}([^\n]*)$",
    re.MULTILINE,  # normalize 内行在文本中间，`^` 须锚定每行行首
)
# K2 次行正文剥行首星：`**【炼金炸弹】伤害+1/2。` → `【炼金炸弹】伤害+1/2。`
# （HTML <B> 转换残留；全库仅 page_17 FCB 段 1 处，误伤面为零）
_RE_FCB_BODY_LEAD_STAR = re.compile(r"^\*\*([【〔［])", re.MULTILINE)

# 出自行 → source 字段。三形态（2026-08-04 放宽）：
#   `**出自《荒野英雄 pg. 5》**`（星包裹）
#   `出自《Ultimate Wilderness pg. 23》`（normalize 剥星后裸行，page_1456）
#   `出自《位面冒险》（Planar Adventures）`（书名后英文括号，PA 熵裔/秩裔）
# 组2 = 星壳或（EN）括号；组3 = 括号内英文（组2 为星壳时无组3）
_RE_SOURCE_LINE = re.compile(
    r"^\*{0,2}出自《([^》]+)》(\*{0,2}|（([^）]+)）)$"
)

# 速查行：`【能力速查】…` / `【专长速查】…` → 并入当前条目不产伪条目
_RE_QUICK_REF = re.compile(r"^【(?:能力|专长|职业)速查】")

# ---- 血脉亚种表格行（M6/KN118） ----
# 神裔/魔裔亚种 = HTML 表格：`|  | 血脉名（中文）描述…祖先：…替换属性调整：… |`
# 一行含整条血脉全部字段链（祖先/典型阵营/替换属性调整/替换技能加值/替换类法术
# 能力），后跟缩进描述段与 `| --- | --- |` 分隔行循环——6/10 血脉整段吞进
# 1 个 mega chunk（神裔 5102 字符/魔裔 8745 字符）。拆行输出标准标题形态
# `**血脉名（中文）**` + 字段链内容行（split 建独立条目，描述段并入）。
_RE_HERITAGE_TABLE_ROW = re.compile(
    r"^\|[ \t]*\|[ \t]*([一-鿿/]{2,})[（(]([^）)]+)[)）](.*?)[ \t]*\|[ \t]*$",
    re.MULTILINE | re.DOTALL,  # DOTALL：表格单元格内跨行（L93→L102 缩进续行）
)
# 表格分隔行（`| --- | --- |`）：剥除转空行，防并入条目 text（M17 表格残留
# 家族的 KN123 `---` 残留同源）
_RE_TABLE_SEP_ROW = re.compile(
    r"^\|[ \t]*[-—]{2,}[ \t]*(\|[ \t]*[-—]{2,}[ \t]*)*\|?$", re.MULTILINE
)


# 镜像形态（兽态人 9 血统，M17）：`| 中文（EN）［血统名（EN）］　描述… |  |`
# ——第一列有内容（神裔/魔裔是空第一列 `|  | 血脉名…`），
# `_RE_HERITAGE_TABLE_ROW` 不命中 → 整表 3198 字吞进「起始语言」条目。
# 拆出 `**中文（EN）**` 标题，血统名 ［…］ 与描述+字段链入正文
# （信息零丢失，检索 title+text 双通道命中）。
_RE_HERITAGE_TABLE_ROW_MIRROR = re.compile(
    r"^\|[ \t]*([一-鿿/]{2,})[（(]([^）)]+)[)）][［\[]([^］\]]+)[\]］][ \t]*　(.*?)[ \t]*\|[ \t]*\|$",
    re.MULTILINE | re.DOTALL,  # DOTALL：单元格内字段链跨行
)


def _fix_heritage_table_rows(text: str) -> str:
    def repl_row(m: re.Match) -> str:
        return f"**{m.group(1)}（{m.group(2)}）**\n" + (m.group(3) or "").strip()

    text = _RE_HERITAGE_TABLE_ROW.sub(repl_row, text)

    def repl_mirror(m: re.Match) -> str:
        return f"**{m.group(1)}（{m.group(2)}）**\n［{m.group(3)}］　{m.group(4)}"

    text = _RE_HERITAGE_TABLE_ROW_MIRROR.sub(repl_mirror, text)
    return _RE_TABLE_SEP_ROW.sub("", text)

# ---- PFS 禁用/修订尾注拆行（M8/KN114） ----
# 形态 A/C：`**精类思维（Fey Thoughts）** PFS禁用` / 同行粘连
# `**修理者（Wright）** PFS禁用**出自《内海种族 pg. 211》**`
# （星壳闭合后尾注 → `_RE_TITLE` 失配并入前条目；组3 出自行拆出独立行，
#   走 `_RE_SOURCE_LINE` 提升）
_RE_PFS_TAIL_NOTE = re.compile(
    r"^(\*\*[^*\n]+\*\*)[ \t]*(PFS禁用|PFS 禁用|PFS不可用|PFS 不可用)"
    r"(\*\*出自[^*\n]*\*\*)?[ \t]*\r?$",
    re.MULTILINE,  # normalize 内行在文本中间，`^`/`$` 须锚定每行行首/行尾
)
# 形态 B：`**钢铁公民（Iron Citizen）**（PFS修订：选择钢铁公民…` 跨行长尾注。
# 链路：`_split_title_glue_paren` 先拆成两行 → `_RE_WS_TITLE` 的 `\s+` 跨行又粘回
# 并打 `[[fc:whitespace]]` 标记（矮人 L192 打坏形态）。去行首 `（` → `PFS修订：`
# 前缀不再被 `_RE_WS_TITLE` 匹配（其要求 `（` 开头）；同行兜底拆行同理。
_RE_PFS_REVISION_TITLE = re.compile(
    r"^(\*\*[^*\n]+\*\*)[ \t]*（PFS修订：", re.MULTILINE
)
_RE_PFS_REVISION_LINE = re.compile(r"^（PFS修订：", re.MULTILINE)


def _fix_pfs_tail_notes(text: str) -> str:
    def repl_tail(m: re.Match) -> str:
        # 星内尾空格（HTML 转换残留 `（EN） **`，page_934 萨满加持/精类思维）：
        # 清掉使 `_RE_TITLE` 可匹配（`）` 后须紧跟星壳闭合）
        head = re.sub(r"[ \t]+\*\*$", "**", m.group(1))
        return head + "\n" + m.group(2) + "\n" + (m.group(3) or "")

    def repl_revision(m: re.Match) -> str:
        head = re.sub(r"[ \t]+\*\*$", "**", m.group(1))
        return head + "\nPFS修订："

    text = _RE_PFS_TAIL_NOTE.sub(repl_tail, text)
    text = _RE_PFS_REVISION_TITLE.sub(repl_revision, text)
    return _RE_PFS_REVISION_LINE.sub("PFS修订：", text)


# 概述表数据行：`| 中文（EN） | 六列属性 | 类型 | 体型 | 速度 | 感官 |`
_RE_OVERVIEW_ROW = re.compile(r"^([一-鿿/]{2,})[（(]([^）)]+)[)）]$")
# 无括号种族名表行（page_11 年龄/身高体重表）：`| 矮人 | 40岁 |…`
_RE_OVERVIEW_BARE = re.compile(r"^[一-鿿/]{2,}$")

_OVERVIEW_ADJ_LABELS = ["力量", "敏捷", "体质", "智力", "感知", "魅力"]
_OVERVIEW_SIZES = ("微型", "超小型", "小型", "中型", "大型", "超大型", "巨型", "超巨型")

# 描述尾部替换说明：「本特性替换XX。」/「该特性取代XX。」（无哨兵行形态兜底）
_RE_REPLACES_TAIL = re.compile(
    r"(?:能)?(?:以|用)?(?:该|本|此|这(?:一|个)?)(?:种族|族)?特性"
    r"(?:取代|替换)(?:了)?([^。；]+?)(?:[。；]|并(?:且)?|同时|也|$)"
)


# ==================== race 特有 normalize 规则 ====================

# 超长行拆行（2026-08-04）：page_752 无换行连续文本——3 行/最长 8178 字符，
# 条目分隔符 `。  **中文（EN）：**`、分组裸标题 `。**矮人**矮人…` 全在同一行内，
# split 状态机按行无法切分 → items 0。拆出条目边界与分组标题行（仅超长行触发，
# 其余 111 文件行 <3000 同形态不触发，零副作用）。
_RE_LONG_ITEM_BOUNDARY = re.compile(r"[。！？][ ]*\*\*([一-鿿]{2,10}[（(])")
_RE_LONG_MID_TITLE = re.compile(r"[。！？][ ]*\*\*([一-鿿]{2,4})\*\*([一-鿿])")
_RE_LONG_LEADING_TITLE = re.compile(r"^\*\*([一-鿿]{2,4})\*\*([一-鿿])", re.MULTILINE)


def _split_long_lines(text: str) -> str:
    """超长行（>3000 字符）拆行：条目边界/分组标题独立成行。

    顺序：条目边界（带括号标题）→ 行中分组裸标题 → 行首分组裸标题，
    拆后各段走现有状态机（条目标题 → race_trait、裸标题 → race_sidebar）。
    """
    if not any(len(line) > 3000 for line in text.splitlines()):
        return text
    text = _RE_LONG_ITEM_BOUNDARY.sub(r"\n**\1", text)
    text = _RE_LONG_MID_TITLE.sub(r"\n**\1**\2", text)
    text = _RE_LONG_LEADING_TITLE.sub(r"**\1**\n\2", text)
    return text


# 行首 4 星粘连拆行（2026-08-04 ISR 修复）：`**~~矮人****矮人角色…` 剥删除
# 线壳后剩 `**中文****中文` 4 星粘连——`_RE_CN_STAR_CN_GLUE` 会把中段剥成
# 无分隔（`**矮人矮人…`），须先拆出节标题行。前段 2~10 字（`**种族特性
# 替换****敏锐狐妖**` 6 字章节行，2026-08-04 全量核查 M1 放宽）。
_RE_QUAD_GLUE_LEADING = re.compile(r"^\*\*([一-鿿]{2,10})\*\*\*\*([一-鿿])", re.MULTILINE)

# 行首 4 星粘连的「章节+条目标题」形态（2026-08-04 全量核查 M1，KN115 根因）：
# `**种族特性替换****敏锐狐妖（Keen Kitsune）**：正文`——`_RE_QUAD_GLUE_LEADING`
# 第二段只捕获单字，残留 `敏锐狐妖（…）**：` 星壳行仍不匹配标题正则；此形态
# 整行拆成章节行 + 标准条目标题行（`**X**\n**Y（EN）**：正文`）。第二段括号
# 可选（`**天赋职业选项****所有职业**：` 无 EN 的 FCB 形态），括号组须含字母
# （防中文尾注 `（又译…）` 误拆——走 `_RE_QUAD_NESTED_TITLE`）。
_RE_QUAD_GLUE_SECTION_TITLE = re.compile(
    r"\*\*([一-鿿]{2,10})\*\*\*\*((?:[一-鿿A-Za-z/·\-－]{1,})"
    r"(?:[（(][^）)]*[A-Za-z][^）)]*[)）])?[^*\n]*?)(?:\*\*)?([：:][^\n]*)",
    re.MULTILINE,
)

# 行首裸（无 `**`）4 星粘连（2026-08-04 全量核查 M1）：`精灵****精灵角色…`
# 行首无星 → 上述两正则不命中、GLUE 合并成 `精灵精灵角色…` → 节标题消失。
# 拆成标准节标题行 + 散文行（形态全库仅 ISR 核心 6 处）。
_RE_QUAD_GLUE_BARE_LEADING = re.compile(
    r"^([一-鿿]{2,6})\*\*\*\*([一-鿿][^\n]*)", re.MULTILINE
)


def _split_quad_glue_titles(text: str) -> str:
    """4 星粘连标题拆行（须在星标拆中文前）。

    - `**中文****中文` → `**中文**\n中文`（节标题 + 散文，原逻辑）
    - `**章节词****条目名（EN）**：正文` → `**章节词**\n**条目名（EN）**：正文`
      （章节 + 标准条目标题——GLUE 守卫只认星内形态，此形态若被合并会把章节
      标题吞进条目名，KN115）
    - `中文****中文…`（行首无星）→ `**中文**\n中文…`（ISR 核心节标题）
    """
    text = _RE_QUAD_GLUE_SECTION_TITLE.sub(r"\n**\1**\n**\2**\3", text)
    text = _RE_QUAD_GLUE_LEADING.sub(r"**\1**\n\2", text)
    return _RE_QUAD_GLUE_BARE_LEADING.sub(r"**\1**\n\2", text)


# BotC 双段标题拆行（2026-08-04 全量核查 M3）：`**妖鬼婆裔 替换儿（Annis-Born
# Changelings） 矿砾之女（Slag May）**` —— `_RE_TITLE` 组1 字符集不容空格 →
# 整行不匹配任何标题正则 → 散文行并入 intro cur（BotC 10 亚种 0 产出，
# E 组幽灵 cur 实证）。拆成亚种标题 + 变体名正文行——条目名取亚种名
# （官方名 Annis-Born Changeling），变体名（Slag May 俗称）进 text 保检索。
_RE_DUAL_CN_TITLE = re.compile(
    r"^\*\*([一-鿿]{2,8}) ([一-鿿]{2,4})（([^）]+)）"
    r" ([一-鿿]{2,6})（([^）]+)）\*\*$",
    re.MULTILINE,  # 锚定每行行首（文件中部标题）
)


def _split_dual_cn_titles(text: str) -> str:
    """双段标题拆成标准标题 + 变体名正文行（`**X1X2（EN1）**` + `**（X3 EN2）**`）。

    变体行必须星壳包裹：公共层 `_RE_WS_TITLE`（星闭后空白+开括号模式）的
    跨行匹配会把裸 `（矿砾之女 Slag May）` 行拼回标题并打
    `[[fc:whitespace]]` 标记（M3 首版实证）；星壳阻断该模式（星后须紧接
    开括号），split prose 分支剥壳后正文干净。
    """
    return _RE_DUAL_CN_TITLE.sub(r"**\1\2（\3）**\n**（\4 \5）**", text)


# 无星缩进条目补星（2026-08-04 ISR 修复）：`  旧日之敌（EN）：**…`（行首
# 2 空格 + 无开头星，HTML 列表排版残留）→ `**旧日之敌（EN）：**…` 标准标题
# 形态供 `_RE_TITLE` 识别。形态全库仅 ISR 核心一个文件。
# 括号后容 0-4 星：尖耳朵剥删除线壳后 `）****：**`（4 星粘连）同样命中
# （2026-08-04 尖耳朵形态：`~~~~尖耳朵（~~****~~EN~~****~~）~~****~~：**`）。
_RE_INDENT_STARLESS_TITLE = re.compile(
    r"^[ \t]{2,}([一-鿿/]{2,}[（(][^）)]+[)）]\*{0,4}[：:]\*{2})", re.MULTILINE
)


def _fix_indent_starless_titles(text: str) -> str:
    """缩进无星条目补开头星（`  中文（EN）：**` → `**中文（EN）：**`）。"""
    return _RE_INDENT_STARLESS_TITLE.sub(r"**\1", text)


def _fix_ability_adj_line(text: str) -> str:
    """属性调整字段星壳归一：`**+2****敏捷，…**：值` → `**+2敏捷，…**：值`。

    公共 `_fix_quadruple_star` 对 `**+2**敏捷，`（闭合星后直接汉字）剥不动，
    属性调整行残留碎片星（验证输出 `**+2**敏捷，**+2**魅力，**-2****感知**`）。
    整行剥星重组为单加粗段，冒号前为标题、后为值（split 并入主条目 text）。
    """
    def _repl(m):
        line = m.group(0)
        body = re.sub(r"\*+", "", line)
        mm = re.match(r"^([^：:]+)[：:](.*)$", body)
        if not mm:
            return line
        return f"**{mm.group(1).strip()}**：{mm.group(2)}"
    return _RE_ABILITY_ADJ_LINE.sub(_repl, text)


def _merge_source_cross_lines(text: str) -> str:
    """出自行跨行合并（数字/中文-英文边界）：`pg. \\n5` → `pg. 5`。

    公共 `_merge_cross_line_en` 只合并字母-字母（`Low-Light \\nVision`），
    `pg. \\nN` 数字断行与 `《阴影血脉 \\npg. \\n4》` 中文-英文边界不覆盖。
    """
    text = _RE_SOURCE_CROSS_CN_PG.sub(r"\1 \2", text)
    text = _RE_SOURCE_CROSS_DIGIT.sub(r"\1 \2", text)
    text = _RE_SOURCE_BOOK_TAIL_STAR.sub(r"《\1》", text)
    return text


def _fix_cn_star_cn_glue(text: str) -> str:
    """星标拆中文：`**魅****影身姿` → `**魅影身姿`（4 星粘连中文段）。

    守卫：组1 前段为 `**X` 且 X 命中章节词（`**背景元素****语言天才…`、
    `**种族特性替换****敏锐狐妖…`）时不合并——章节标题+条目标题粘连由
    `_split_quad_glue_titles` 拆行处理（2026-08-04 全量核查 M1，KN115 根因）；
    星内单字拆裂（`**魅****影身姿`，X=「魅」非章节词）仍合并。裸文本 4 星
    （`精灵****精灵角色…`）前字符非 `*` 也不合并（拆行处理）。
    """
    def _repl(m):
        if m.start() == 0:
            return m.group(0)
        pre = m.string[: m.start()]
        if pre[-1] == "*" and not any(w in pre[-14:] for w in _GLUE_GUARD_WORDS):
            return m.group(1) + m.group(2)
        return m.group(0)
    return _RE_CN_STAR_CN_GLUE.sub(_repl, text)


def _fix_quad_nested_title(text: str) -> str:
    """四星嵌套标题归一：`**中文****（****EN****，后缀）******` →
    `**中文（EN，后缀）**`；HTML 拆裂中段 `**高等地精****自燃术（****Greater
    Fire Body, Ex****）**` → `**高等地精自燃术（Greater Fire Body, Ex）**`
    合并，类型标签（`〔战斗〕`）保留。

    源数据「双星加粗段相邻」产物（`**中文**`+`**（**`+`**EN**`+…），公共
    `_RE_QUAD_STAR`（星对星）不匹配（内嵌 `****（`）、`_fix_quad_star_
    halfparen` guard 版不拆（4 星前非 `）`/`)`）——先归一为标准形态供
    `_RE_TITLE` 识别。

    ⚠️ 须在 `_split_quad_glue_titles` 前调用：中段形态 glue 组2 以中文
    开头会先拆行成伪条目；EN 跨行形态（`（****Fire \\nBody, Ex****）`）
    先借公共 `_merge_cross_line_en` 合并（幂等，链后重复调用无副作用）。
    """
    text = _merge_cross_line_en(text)

    def _repl(m):
        # 组1 = 首段，中间组 = 段间拆裂段（0+），最后 3 组 = EN/尾缀/类型。
        # 类型标签保留在星壳内（`〔战斗〕` 供 _RE_TITLE 组3 feat_type 判定）
        g = m.groups()
        mid = "".join(x for x in g[1:-3] if x)
        en, tail, typ = g[-3], g[-2], g[-1]
        return f"**{g[0]}{mid}（{en}{tail}）{typ or ''}**"

    return _RE_QUAD_NESTED_TITLE.sub(_repl, text)


# 专长简述表剥离（KN133 物品粘专长简述表家族）：`| 表：X专长简述 |` 表标题
# + `| 专长名称 |…|` 表头 + 数据行（首格「EN 中文」）剥除——简述表信息与
# 后文专长详述条目重复，并入前一条目（熏香/不稳定促进剂等物品）会污染
# text。守卫：
#   - 数据行首格须同时含 EN≥3 与中文（stat block 表首格纯 EN 标签
#     `| AC | +2天生护甲 |`、纯中文表 `| 精灵（Elves） |` 均豁免）
#   - 须在 `_merge_table_continuation` 之后（数据行 EN/中文跨行，合并后
#     才能识别首格）
_RE_FEAT_TABLE_HEAD = re.compile(r"(?m)^\s*\| 表：[^\n]*\|[ \t]*$")
_RE_FEAT_TABLE_HEADER_ROW = re.compile(r"(?m)^\s*\| 专长名称[^\n]*\|[ \t]*$")
_RE_FEAT_TABLE_ROW = re.compile(
    r"(?m)^\| ([A-Za-z][A-Za-z .'’\-*]{2,}[^|\n]*[一-鿿][^|\n]*?) \|[^\n]*\|[ \t]*$"
)
# 表格尾注行——随表剥除。两形态：`| * 标注星号专长为战斗专长。 |`
# （page_19/160 等）与 `| * \r       标注星号… |`（page_165~167/204/205/238，
# 星号后 CR+空格，2026-08-04 全库 13 残留复扫发现）；`[ \t\r]+` 不含换行防跨行
_RE_FEAT_TABLE_NOTE = re.compile(r"(?m)^\s*\| [**]+[ \t\r]+标注星号专长为战斗专长。\s*\|?[ \t]*$")


def _strip_feat_table_rows(text: str) -> str:
    """专长简述表行剥除（表标题/表头/数据行/尾注行），防物品条目 text 污染。"""
    text = _RE_FEAT_TABLE_HEAD.sub("\n", text)
    text = _RE_FEAT_TABLE_HEADER_ROW.sub("\n", text)
    text = _RE_FEAT_TABLE_NOTE.sub("\n", text)
    return _RE_FEAT_TABLE_ROW.sub("\n", text)


def _strip_translator_lines(text: str) -> str:
    """译者行剥除：含 URL 的译者行 / `**译者：…**` 行（PA 形态）。"""
    return _RE_TRANSLATOR_LINE.sub("", text)


# 行中星包裹标题拆行（2026-08-04，page_716 翼龙人整页压缩文本形态）：
# `…。**贪婪（Greed）**：…` / `…。**天赋职业奖励**下列…` / `…。**血脉狂怒者**：…`
# ——标题嵌在散文行中，split 状态机按行无法切分 → 拆为独立行；拆出后
# 标题后的粘连正文（`**种族特性替换**以下…`）也换行落回散文（`_RE_TITLE`
# 需整行闭合星，粘连正文留在标题行会使其无法识别）。
# 守卫（不拆的正常形态，2026-08-04 回归修复）：
#   - 星内以句号/分号结尾（哨兵句 `**此特性取代扫尾（slapping tail）。**`
#     是正文，replaces 兜底捕获——拆行会把它误当标题）
#   - 行首星 + 星后冒号：字段行 `**体貌描述**：…` / FCB 条目 `**圣武士**：…`
#     ——split 按行直接识别，拆行破坏形态（A 簇/C 簇回归）
#   - 星前 `【…】` 标签（速查行 `【能力速查】**X**：…`）——并入正文（A 簇回归）
#   - 星后 `**`（4 星粘连 `**援护防御****（****…`）——`_RE_TITLE` 容 4 星
#     形态已处理，拆行断 name_en（B 簇回归）
_RE_INLINE_STAR_TITLE = re.compile(
    r"\*\*[　]*([一-鿿][一-鿿A-Za-z/·\-－]+(?:[（(][^）)]+[)）])?(?![。；]))\*\*"
)


# 字段标签行首（2026-08-04，法术块字段链守卫）：`等级：**…` / `目标：**…`
# ——行中星壳后紧跟「标签：」说明被拆候选是字段值（`**学派：**值**等级：**`
# 的星是相邻字段星壳边界），不是嵌在散文中的行中标题
_RE_FIELD_LABEL_LEAD = re.compile(r"^[一-鿿A-Za-z0-9（）()/·\-－ ]{1,12}[：:]")


# 字段链星壳拆行（2026-08-04，法术块字段链 `**标签：**值**标签：**值` 同行
# 嵌套，page_814 柳絮随风形态）：每个 `**标签：**` 前插换行——星壳后的值不再
# 被相邻字段星壳边界夹成 `**值**`，且跨行标题尾部（`WAFT****学派：`）与字段链
# 的粘连在 `_wrap_bare_titles` elided 合并前断开（否则闭星+开星 4 星粘连被
# 当标题尾部吞掉，字段链开星被剥）。行首已是独立字段行不拆（`(?<!^)` MULTILINE）。
# 守卫：星内以冒号结尾——`**X**：`（星外冒号字段行）/`**X（EN）**` 标题均不含。
_RE_FIELD_CHAIN_STAR = re.compile(
    r"(?<!^)\*\*([一-鿿A-Za-z0-9（）()/·\-－ ]{1,12})[：:]\*\*", re.MULTILINE
)


def _split_field_chain_star_shells(text: str) -> str:
    """字段链星壳拆行：`…**学派：**变化系**等级：**…` → 每星壳独立成行。

    须在 `_wrap_bare_titles` 前（elided 合并会吞粘连的 4 星）、
    `_RE_SOURCE_MARKER` 前不冲突（`**UW：**` 形态全库不存在）。
    """
    return _RE_FIELD_CHAIN_STAR.sub(r"\n**\1：**", text)


def _split_inline_star_titles(text: str) -> str:
    """行中/行首星包裹标题拆为独立行（守卫见 `_RE_INLINE_STAR_TITLE` 注释）。"""
    def _split_line(line: str) -> str:
        # 行首星：星后冒号（字段行/FCB 行）/星后 `**`（4 星）/星后括号
        # （`**X**（Y）` 标题+括号尾注，`_RE_TITLE` `\*{0,4}` 容错）/星后空格
        # （`**豁免** 强韧DC` 字段标签，page_1456 毒药块）/无粘连 → 不拆
        m = _RE_INLINE_STAR_TITLE.match(line)
        if m:
            after = line[m.end():]
            if not after or after.startswith(("：", ":", "**", "（", "(", " ")):
                # 星后冒号（M14）：FCB/字段行守卫——行首标题本身保持原行
                # （`**圣武士**：…` split 按行识别），但行中可能还有第二个
                # 标题（`**特技专家（Acrobatic）**：正文…（nimble）**变换
                # 体型（Change Size，Su）**：…`，BotB 同行多条目 HTML 段落
                # 合并）——递归扫描 after；无行中标题时 rest==after 行为
                # 不变（A/C 簇回归保护）。其余守卫（4 星/括号/空格）不递归
                if after.startswith(("：", ":")):
                    rest = _split_line(after)
                    if rest != after:
                        return line[: m.end()] + rest
                return line
            return m.group(0) + "\n" + _split_line(after)
        # 行中星：星前标签 `】`（速查行）/星后 `**`（4 星）/星后括号/星后空格
        # （字段标签）→ 不拆
        m = _RE_INLINE_STAR_TITLE.search(line)
        while m:
            before, after = line[:m.start()], line[m.end():]
            # 字段标签词表（M14 回归守卫，2026-08-04）：星壳头部中文 ∈
            # `_ALL_FIELD_LABELS`（类型/频率/效果/治愈/强韧豁免/先决条件/
            # 发作频率/…毒药块 + 条目流态字段）→ 跳过该星壳继续扫行内
            # 后续星壳——不整行返回（行内真标题连带不拆，page_716 翼龙人
            # 专长 L2：`…**先决条件**：…士气。**龙人秩序（Draconian
            # Law）**` 行尾标题被字段标签卡住）；毒液块字段链（page_26
            # 毒刺）行内全是字段标签 → 全部跳过 → 整行保持原样不拆
            inner = m.group(1) or ""
            inner_cn = re.match(r"[一-鿿]+", inner)
            if inner_cn and inner_cn.group(0) in _ALL_FIELD_LABELS:
                m = _RE_INLINE_STAR_TITLE.search(line, m.end())
                continue
            # 字段链形态 `**标签：**值**标签：**值`（page_814 法术块）：值被
            # 相邻字段星壳边界夹成 `**值**`，after 以「标签：」开头 → 候选是
            # 字段值不是行中标题，不拆（否则「变化系/近距/意志通过则无效」等
            # 字段值成伪条目，2026-08-04 #101 产出即检簇 I）
            if after and _RE_FIELD_LABEL_LEAD.match(after):
                return line
            # 星后换行/连字符（`**强韧豁免（DC）**\n“10+…”`、`**初始效果**
            # －恍惚1d4轮；`）→ 字段值形态不拆（专长效果行内子字段
            # 初始效果/后续效果防伪条目）
            if before.endswith("】") or after.startswith(("**", "（", "(", " ", "\n", "－", "-")):
                return line
            # 只递归 after（文本严格缩短，收敛）；before 是首个匹配前文本，
            # 不可能再含匹配（否则 search 会先命中）
            return before + "\n" + m.group(0) + "\n" + _split_line(after)
        return line

    return "\n".join(_split_line(line) for line in text.split("\n"))


# page_1456 聚合页来源标记（2026-08-04）：`**葡萄藤（Grapevine）**UW：正文`
# / `**炼金术士**UW：…`——UW=《Ultimate Wilderness》、WO=《Wilderness Origins》
# 逐条标记（小节标题「种族特性替换（已整合，来源已注明）」等注明来源已整合）。
# 转标准冒号——`_RE_TITLE`/`_RE_BARE_CN_COLON` 判定保留，标记不残留 text；
# 须在 `_split_inline_star_titles` 前（否则 `UW：正文` 被拆成独立正文行）。
_RE_SOURCE_MARKER = re.compile(r"\*\*(?:UW|WO)[：:]")


# 星内中文+英文无括号标题（2026-08-04，page_716 巢穴守卫者形态）：
# `**巢穴守卫者 Brood Defender**当某人…` → `**巢穴守卫者（Brood Defender）**` 独立行。
# `_RE_TITLE_GLUE_CN_EN` 已拆行（无括号形态 `_RE_TITLE` 不识别）→ 补括号供识别；
# 换行前缀标为正文与标题拆开。`**通常速度**`/`**中型龙类：**`/带括号标题均不匹配。
_RE_STAR_CN_EN_TITLE = re.compile(
    r"\*\*([一-鿿/]{2,})\s+([A-Za-z][A-Za-z'’\.\- ]*?)\*\*"
)


# H2 裸中文标题（2026-08-04，page_163 剪影人形态）：`## 剪影人` → `**剪影人**`。
# 守卫：`## 格拉里昂的狗头人 可选天赋职业奖励`（含空格 14 字）与
# `## 切利亚斯CtIE 替换儿种族选项`（含 Latin）天然不匹配。
# 2026-08-04 M9：扩展「前缀 空格 种族名」形态（`## 水晶 土元素裔`、
# `# 内海怪物志 德洛人`，全库 10 处）——含空格原失配 → 拆行碎片化
# （`**内海怪物**` + `志 德洛人`），注释信号/裸中文标题抢占碎片；
# 转星时取末段（`**德洛人**`），前缀为页眉冗余剥除。⚠️ 仅 H2/H3
# （`#{2,3}`）——H1 页眉（`# 内海怪物志 德洛人`）留给 split `# ` 跳过，
# 转星会与带括号主条目同名重复（2026-08-04 德洛人回归实证）。
_RE_H2_BARE_CN = re.compile(
    r"^#{2,3}\s*([一-鿿/]{2,6}(?:\s+[一-鿿/]{2,6})*)\s*$", re.MULTILINE
)

# 星包哈希章节（2026-08-04 M9，BotB 形态）：`**## 种族特性**`——`## X` 先被
# `_wrap_bare_cn_en_allcaps` 类裸标题规则包星，H2 规则失配 → 章节关键字失效
# state 无法切换。剥壳恢复标准章节形态（`_wrap_h2_titles_race` 内处理，链序
# 在裸标题包裹规则之后）。
_RE_H2_STAR_HASH = re.compile(r"^\*\*#{1,3}\s*([一-鿿/]{2,8})\s*\*\*$", re.MULTILINE)

# H2 带括号标题（2026-08-04，整理页子标题形态）：
# `## 格拉里昂的侏儒 脱色症（The Bleaching）`（前缀段+空格）→ `**脱色症（The Bleaching）**`；
# `## 半身人霉咒（Halfling Jinx）【种族特性】`（带类型标签，无空格）→ 整标题保留。
# 前缀段（`格拉里昂的侏儒`）为页眉冗余，剥除——`_RE_TITLE` 组1 不容空格。
_RE_H2_PAREN_TITLE = re.compile(
    r"^#{1,3}\s*([一-鿿/]{2,}(?:\s+[一-鿿/]{2,})*)[（(]([A-Za-z][^）)]*)[)）]"
    r"([〔［【][^〕］】]*[〕］】])?\s*$",
    re.MULTILINE,
)

# 星后全角空格（2026-08-04，page_103 替换儿形态）：`**　　嗜火者（Pyrophile）**`
# ——`_RE_TITLE` 组1 不含 U+3000，剥除后恢复标准标题形态。
_RE_STAR_FULLWIDTH_LEAD = re.compile(r"^(\*\*)[ \t　]+(?=[一-鿿])", re.MULTILINE)

# whitespace 断行合并标记剥除（M10，标题行前缀）：`[[fc:whitespace]]**…**`
# 行首标记使 split `_RE_TITLE`/`_RE_BARE_CN_COLON` 失配 → 并入散文。
# 仅剥标记（含换行合并的空格），星壳保留。
_RE_WS_PREFIX_TITLE = re.compile(r"^\[\[fc:whitespace\]\]+(?=\*\*)", re.MULTILINE)


# 整理注释（2026-08-04 M9）：`<!-- ISR-source:新种族/page_1599.md:勒珊塔灵族 -->`
# / `<!-- 切利亚斯CtIE-source:切利亚斯，炼狱帝国CtIE.md:pyrophile -->`——组2 为
# 种族名（或 `__aggregate__` 聚合标记）。多种族聚合文件（ISR 新种族 3 族/BotS
# 3 族/CtIE）逐种族注释 → 下一标题行即种族 H2（state 重置信号，KN127）。
_RE_SOURCE_COMMENT = re.compile(r"<!--[^>]*?-source:[^:>]+:([^>]+?)-->")


def _wrap_h2_titles_race(text: str) -> str:
    """H2 标题转星（裸中文 / 带括号±标签），`_wrap_hash_titles` 系列补缺。"""
    def _repl(m):
        cn = m.group(1)
        en = m.group(2)
        tag = m.group(3) or ""
        # 前缀段（「格拉里昂的侏儒 脱色症」）剥除，取括号前最后一段
        base = re.split(r"\s+", cn)[-1] if re.search(r"\s", cn) else cn
        return f"**{base}（{en}）{tag}**"
    text = _RE_H2_PAREN_TITLE.sub(_repl, text)
    # 裸中文 H2 → 星壳（`## 剪影人` → `**剪影人**`；`# 内海怪物志 德洛人`
    # → `**德洛人**`，前缀段剥除），split 裸中文标题分支按 intro 态 →
    # race_sidebar 处理（D 簇怪物主条目由 processor 映射 monster_block，
    # M9 回归验证：h2_line 升级曾把怪物文件 12 个 monster_block 误抢成
    # race_intro，已移除——裸中文 H2 保持既有行为）
    text = _RE_H2_BARE_CN.sub(
        lambda m: f"**{re.split(r'\s+', m.group(1))[-1]}**", text
    )
    # 星包哈希剥壳（M9/BotB）：`**## 种族特性**` → `**种族特性**`
    return _RE_H2_STAR_HASH.sub(r"**\1**", text)


def _strip_star_fullwidth_lead(text: str) -> str:
    """剥星后全角空格（`**　　中文` → `**中文`），须在星标处理族最前。"""
    return _RE_STAR_FULLWIDTH_LEAD.sub(r"\1", text)


# 行首裸「中文（EN）：正文」标题（2026-08-04，page_253 狗头人 FCB 形态）：
# `野蛮人（Barbarian）：狂暴时…` → `**野蛮人（Barbarian）：**狂暴时…`；
# 章节行 `可选天赋职业奖励（Favored Class Options）`（无冒号行尾）同规则转星。
# 守卫 `_is_fragment_title`：正文句首碎片（长句/虚词开头）不包裹。
# M10：组2 数字开头（BotS 裸特性 `触手感知（1 RP）：正文`——RP 标注是特性
# 形态特征）+ 第二括号容错（`喷射（Jet）（1 RP）：正文` 双括号）——转星后
# `_RE_TITLE` 单括号/双括号均匹配，特性独立成条目
_RE_BARE_PAREN_COLON_TITLE = re.compile(
    r"^([一-鿿/]{2,})[（(]([A-Za-z0-9][^）)]*)[)）]"
    r"([（(][^）)]*[)）])?([：:][^\n]*)?$",
    re.MULTILINE,
)


def _wrap_star_cn_en_titles(text: str) -> str:
    """星内中文+EN 无括号 → `**中文（EN）**` 独立行（page_716 专长标题）。"""
    return _RE_STAR_CN_EN_TITLE.sub(r"**\1（\2）**\n", text)


# 裸章节标题拆行（2026-08-04，page_716/page_806 整页压缩文本形态）：
# `翼龙人专长翼龙人由于…` / `剪影人天赋职业选项` / `剪影人备选种族特性`
# ——无星无括号裸行，行首中文段以章节关键字结尾且后接粘连正文 → 拆出
# 章节标题行（`**翼龙人专长**`）供 split `_match_section` 识别。
# 守卫：行首 2~14 字窗口内命中（过长是正文句）；tail 首字为虚词
# （`以下种族特性可以被选择…` 说明散文行）不拆。
# 关键字表与 split `_SECTION_KEYWORDS` 同源（长关键字优先防子串误判）。
_BARE_SECTION_KEYWORDS = (
    "备选种族特性", "种族特性替换", "替换种族特性", "可选天赋职业奖励",
    "天赋职业选项", "天赋职业奖励", "种族特性", "职业变体", "魔法物品",
    "专长", "法术", "概述", "怪物", "装备",
)
_BARE_TAIL_LEADERS = ("的", "可以", "能够", "能", "会", "被", "将", "要", "需",
                      "是", "时", "为", "在", "与", "和", "或", "也", "都")
# head 虚词守卫：行首~关键字之间含虚词 → 章节描述散文句（`精灵角色可以
# 选择以下种族特性替换原本的种族特性。`），不是标题（真实标题 head 是
# 种族名，如 `翼龙人`/`剪影人`，2~3 字且无虚词）。
# head 虚词守卫：行首~关键字之间含虚词 → 章节描述散文句（`精灵角色可以
# 选择以下种族特性替换原本的种族特性。`/`在你施法以及之后法术持续的每轮
# 开始时…`），不是标题（真实标题 head 是种族名，如 `翼龙人`/`剪影人`/
# `地精`，2~3 字且无虚词）。2026-08-04 扩展单字代词/介词/连词/副词：
# 怪物法典正文句段落行（`在你施法以及之后法术持续的每轮开始时…`，源
# page_96 食尸鬼）曾被在「法术」（idx=7）处截断包星成伪裸标题
# `**在你施法以及之后法术**`——第二版虚词排除后不切章节，反落裸标题条目
# 分支 → race_spell 伪条目（审计 #103 回归）。逐字验证：10 个合法裸章节
# head（地精/灰矮人/巨魔/沙华鱼人/蛇人/食尸鬼/蜥蜴人/熊地精/沼蜍人/藤蔓
# 莱西）均不含下列虚词；28 个正文句 head 全含 ≥1（你/在/当/这/该/若/的…）。
_BARE_HEAD_NOISE = ("以下", "可以", "能够", "所有", "每个", "选择", "具有", "拥有",
                    "你", "我", "他", "她", "在", "当", "如", "若", "这", "该",
                    "此", "和", "或", "与", "将", "把", "被", "所", "的", "于",
                    "从", "向", "对", "给", "更", "不", "也", "就", "而", "是",
                    "有", "它", "其", "则", "并", "但", "且")


def _split_bare_section_titles(text: str) -> str:
    """裸章节标题行拆行：行首中文段以章节关键字结尾 + 粘连正文 → 标题独立行。

    守卫：
      - 星壳行不拆（`**精灵角色可以选择以下种族特性替换…` 是章节描述，
        4 星粘连拆行后行首残留 `**`——星包裹形态走其他规则）
      - head 含虚词（`精灵角色可以选择以下…`）不拆
      - `> ` 引用行（`> 来源：怪物志…` 含「怪物」关键字）不拆
      - 行首 14 字含冒号（字段行 `先决条件：…专长效果：…` 含「专长」
        关键字）不拆——真实标题 head 是纯种族名，无冒号
    """
    out = []
    for line in text.split("\n"):
        # 井号/注释行不拆（M9/德洛人回归）：`# 内海怪物志 德洛人` 的
        # 「怪物」命中章节关键字 → 拆成 `**内海怪物**` + `志 德洛人`
        # 碎片；`<!-- 内海怪物志-source:… -->` 的「怪物」同样拆碎——
        # 注释信号机制依赖 `<!--` 开头，拆碎后信号失效、注释被并入
        # 条目。H1/H2 统一留给 `_wrap_h2_titles_race` 转星
        if line.startswith("#") or line.startswith("<!--") or line.startswith("**"):
            out.append(line)
            continue
        if line.startswith(">") or "：" in line[:14] or ":" in line[:14]:
            out.append(line)
            continue
        for kw in _BARE_SECTION_KEYWORDS:
            idx = line.find(kw)
            if 2 <= idx <= 14 and idx + len(kw) <= len(line):
                head = line[:idx]
                if any(v in head for v in _BARE_HEAD_NOISE):
                    break
                tail = line[idx + len(kw):]
                if not tail:
                    # 独立裸行小节标题（`藤蔓莱西装备`/`藤蔓莱西专长`/`藤蔓莱西
                    # 法术`，page_1456 聚合页）——关键字到行尾 → 整行转星标题
                    # 供 split 章节判定（head 虚词守卫已在前，无虚词才到此处）
                    line = f"**{line}**"
                    break
                if not tail.startswith(_BARE_TAIL_LEADERS) \
                        and not tail.startswith(("取代", "替换")) \
                        and not tail.startswith(("（", "(")):
                    if tail.strip() and all(
                        c in "。！？；…、，,.!?;:" for c in tail.strip()
                    ):
                        # tail 纯标点 = 散文句尾（`锻造大师擅长制造魔法
                        # 物品。`，page_12 KN107）：「标题+正文」形态的 tail
                        # 是实质正文（`翼龙人专长翼龙人由于…`，全库清单
                        # 内 0 误伤验证），不会只有标点。不拆 → 整行保留
                        # 句号 → 后续包星规则产物 `**…魔法物品。**` 的组1
                        # 含句号，_RE_BARE_CN_TITLE 不匹配 → 不会误判
                        # race_item 章节吞掉手艺人/钢铁法术
                        break
                    # 「取代/替换」开头 = 替换说明句（`…这一种族特性取代
                    # 狩猎本能。` 正文描述，B2 簇形态），不是章节标题；
                    # 括号开头 = 裸括号标题行（`人形怪物（Monstrous
                    # Humanoid）：…`，M10 塞卡利亚——关键字「怪物」命中但
                    # tail 是 EN 括号段，拆出会断标题+正文错位）——两者
                    # 都不拆，留给 `_wrap_bare_paren_colon_titles` 转星
                    line = f"**{line[: idx + len(kw)]}**\n{tail}"
                    break
        out.append(line)
    return "\n".join(out)


def _wrap_bare_paren_colon_titles(text: str) -> str:
    """行首裸 `中文（EN）：正文` / `中文（EN）` → 星包裹标题（FCB 条目/章节）。"""
    def _repl(m):
        name, en, tail = m.group(1), m.group(2), m.group(4) or ""
        paren2 = m.group(3) or ""
        # M13：取代条款行（`此能力取代偏好地形（favored terrain）` 跨行
        # EN 合并后无句点形态）——无冒号分支会把独立行 replaces 说明转星
        # 切伪条目（怪物种族 page_940）。保持裸行 → 后续并入前条目
        if _is_fragment_title(name) or _RE_REPLACE_CLAUSE.match(name):
            return m.group(0)
        return f"**{name}（{en}）{paren2}{tail}**"
    return _RE_BARE_PAREN_COLON_TITLE.sub(_repl, text)


# M10：数字断行合并（BotS 属性调整/特性行形态）：
#   `+2 敏捷，+2 感知，-2 \n智力：正文` → `+2 敏捷，+2 感知，-2 智力：正文`
#   `属性调整：+2 \n力量、+2 魅力、…` → `属性调整：+2 力量、+2 魅力、…`
#   `触手感知（1 \nRP）：正文` → `触手感知（1 RP）：正文`
# 公共 `_merge_cross_line_en` 只合字母边界、`_RE_SOURCE_CROSS_DIGIT` 只合
# 字母→数字——中文值行/数字括号断行全不覆盖 → 裸值行与标签行分离、
# 数字括号 RP 断行，裸行规则无法识别。守卫：组1 不含句末标点（`。！？`）
# ——正文句 `游泳速度为40英尺。\n` 的断行是句子完结，不合并；
# 起点必须带符号（`[+\-−]\d`）——无符号数字（`《怪物图鉴2》` 的 `2`、
# `1d6 伤害` 等正文行）不触发，防 intro 句内数字跨行误合并
# （梭螺鱼人 `…近似版本，可能不完全一致：\n属性调整：…` 实测：`2》中
# 梭螺鱼人的近似版本` 组1 无能力词本应拒绝，但组1 不含 `。` 时贪婪到
# 行尾 `：` 前仍合并——符号守卫从根上隔离正文数字）
_RE_ABILITY_ADJ_CROSS_CN = re.compile(
    r"([+\-−]\d[^。！？\n]*?)[ \t]*\r?\n[ \t]*(?=力量|敏捷|体质|智力|感知|魅力)"
)
_RE_ABILITY_ADJ_CROSS_PAREN_DIGIT = re.compile(
    r"([（(]\d)[ \t]*\r?\n[ \t]*(?=[A-Za-z])"
)
# M11：能力值/引文数字断行（ISR 新种族 2 处）：`Telepathy，3 \nRP` /
# `Characters，11 \nRP）`——行尾「字母，数字」公共 `_RE_CROSS_EN` 组1
# （`[a-zA-Z,]`）失配，标题不成形整条并入相邻条目（「有限心灵感应」粘
# 知识渊博、「勒珊塔灵族角色」粘 intro）。守卫：组1 字母紧贴逗号（千分位
# `1,500\nGP` 逗号前是数字不触发）；组2 短缩写词 ≤3 字母 + 星壳吸收
# （`RP**：`）——正文「，数字 \n长词」形态不误并。
_RE_CROSS_CN_DIGIT_EN = re.compile(
    r"([A-Za-z][，,]\d+)[ \t]*\*{0,4}[ \t]*\r?\n[ \t]*([A-Za-z]{1,3}\*{0,4})"
)


def _merge_ability_adj_lines(text: str) -> str:
    """属性调整/数字括号断行合并（M10 BotS）——须在裸行转星规则之前。"""
    text = _RE_ABILITY_ADJ_CROSS_CN.sub(r"\1", text)
    text = _RE_ABILITY_ADJ_CROSS_PAREN_DIGIT.sub(r"\1", text)
    text = _RE_CROSS_CN_DIGIT_EN.sub(r"\1 \2", text)
    return text


# M10：裸中文冒号行转星（BotS 特性行 `中型体型：正文` / `异怪：正文`）：
# `_RE_BARE_CN_COLON_UNSTARRED` 仅 fcb_entry 态消费，race_trait 态裸行
# 全部并入散文（塞卡利亚 14 特性/梭螺鱼人 10 特性整节丢失）。转星后走
# `_RE_BARE_CN_COLON` race_trait 态分支独立成条目。守卫：
#   - 组1 ≤8 字（特性标签短；散文长句行首不匹配）
#   - 组1 ∈ `_ALL_FIELD_LABELS` 不转（裸字段行并入当前条目，防伪条目）
#   - 空正文仅属性调整转（`属性调整： \n+4 敏捷…` 标签+值行分离形态）——
#     其他空正文行（散文「注意：」类）不转防伪条目
_RE_BARE_COLON_TITLE_RACE = re.compile(
    r"^([一-鿿/]{2,8})[：:]\s*(.*)$", re.MULTILINE
)


# M10：属性调整裸行 → `**值**：正文`（BotS/ISR 裸形态，四类）：
#   ① 空标签跨行（海地精 `属性调整： \n+4 敏捷，…`）→ 值行并入标签行
#   ② 标签+值（`属性调整：+2 力量、…：正文`）→ 剥标签、值转星
#   ③ 裸数字行（塞卡利亚 `+2 敏捷，…-2 智力：正文`，无标签）→ 值转星
#   ④ 星壳内冒号（水栖精灵 `**+2敏捷，…-2体质：**正文`）→ 冒号移出
# 统一产出 `**+2 敏捷，…**：正文`，split `_RE_ABILITY_ADJ_TITLE`
# race_trait 态切独立「属性调整」条目（值+正文进 text 保检索）。
# 守卫：值段以能力六维结尾——stat block 正文行（`1 次/天：…`/
# `+1 攻击：…`）不误转；吸血裔亚种字段链（M1）星壳 `**属性调整**：
# +2力量…` 行首 `*` 不匹配裸行规则，不受影响
_RE_ABILITY_ADJ_EMPTY_LABEL = re.compile(
    r"^属性调整[：:][ \t　]*\r?\n([+−-]?\d[^\n]*)", re.MULTILINE
)
_RE_ABILITY_ADJ_STAR_INNER_COLON = re.compile(
    r"\*\*([+−-]?\d[^\n*]*?)[：:]\*\*"
)
# 首段强制正负号（KN133 狐妖之魅 P1 收尾）：正文行「3级起，…该能力取代
# 陷阱感知。」以数字开头 + 以「感知」能力词结尾，`[+−-]?` 容差误转星壳；
# 真实属性调整裸行（BotS/塞卡利亚）必带正负号，收窄后正文行天然豁免
_RE_ABILITY_ADJ_VALUE = re.compile(
    r"^([+−-]\d[^\n]*?(?:力量|敏捷|体质|智力|感知|魅力)"
    r"(?:[，、][+−-]?\d[^\n]*?(?:力量|敏捷|体质|智力|感知|魅力)){0,5})"
)


def _wrap_ability_adj_bare(text: str) -> str:
    """属性调整裸行转星（M10 四类形态 → `**值**：正文`，见上注释）。"""
    text = _RE_ABILITY_ADJ_EMPTY_LABEL.sub(
        lambda m: f"属性调整：{m.group(1)}", text)
    text = _RE_ABILITY_ADJ_STAR_INNER_COLON.sub(
        lambda m: f"**{m.group(1)}**：", text)

    def _to_star(value_body: str) -> str:
        m = _RE_ABILITY_ADJ_VALUE.match(value_body)
        if not m:
            return value_body
        value = m.group(1)
        rest = value_body[len(value):]
        if not rest.startswith(("：", ":", "。")):
            return value_body
        return f"**{value.strip()}**：{rest[1:].strip()}"

    # ② 标签形态：`属性调整：值+正文` → 剥标签、值转星
    text = re.sub(
        r"^属性调整[：:]\s*([^\n]*)$",
        lambda m: _to_star(m.group(1)), text, flags=re.MULTILINE)
    # ③ 裸数字行（塞卡利亚无标签形态）：值转星，非能力词守卫失配原样保留
    text = re.sub(
        r"^([+−-]?\d[^\n]*)$",
        lambda m: _to_star(m.group(1)), text, flags=re.MULTILINE)
    return text


def _wrap_bare_colon_titles_race(text: str) -> str:
    """行首裸中文冒号行 → 星包裹（BotS 裸特性行，race_trait 态独立条目）。"""
    text = _wrap_ability_adj_bare(text)
    def _repl(m):
        name, body = m.group(1), m.group(2)
        if name in _ALL_FIELD_LABELS:
            return m.group(0)
        if not body.strip() and name not in ("属性调整",):
            return m.group(0)
        # 边栏标记行（page_1456 `引述: 边栏：种植藤蔓莱西`）：转星后走
        # `_RE_BARE_CN_COLON` fcb 分支切伪条目（M7 守卫③在裸形态分支，
        # 转星绕过）——保持裸由 UNSTARRED 守卫③并入 cur
        if body.lstrip().startswith(("边栏",)):
            return m.group(0)
        return f"**{name}**：{body}"
    return _RE_BARE_COLON_TITLE_RACE.sub(_repl, text)


def _wrap_bare_cn_en_lines_race(text: str) -> str:
    """空格形态裸中英行包裹：`霜生种 Born of Frost  你身体…` → elided 标题。

    公共 `_wrap_bare_cn_en_lines` 要求中文紧贴英文；race 源「中文 空格 英文」
    （霜巨人裸文本流式）是常态。守卫复用公共 `_is_fragment_title` /
    `_is_title_case_en` / `_is_multiword_en`（正文断行碎片不包裹）。
    """
    def _repl(m):
        name, en, typ = m.group(1), m.group(2), m.group(3)
        # M16：tail 取括号分支组4 或裸正文分支组5——无括号形态
        # （`冰滑术 Ice Slick学派：…`）的正文在组5，之前只取组4 导致
        # 替换时整段正文被吞（条目拆出但 text 为空，提取层丢弃）
        tail = m.group(4) or m.group(5) or ""
        # 取代条款行不在此函数处理：本函数正则要求「中文 空格 英文」，
        # 取代条款行是括号形态（`此特性取代腐化抗性（ward against
        # corruption）.`）不匹配；真实误包点在公共 `_wrap_bare_paren_lines`
        # （R10 守卫，见 normalize_common.py）
        if (
            len(name) >= 10
            or _is_fragment_title(name)
            or (
                len(tail) > 8
                and (not _is_title_case_en(en) or not _is_multiword_en(en))
            )
        ):
            return m.group(0)
        # 尾随「闭合括号+冒号」（`喷射（Jet）（1 RP）： `）：拆 tail 到下一行
        # 会被 `_normalize_whitespace_title` 跨行合并成 `**…**` + 独立 `：`
        # 行 → text 以 `：` 开头（M10 BotS 海地精实测）。留整行给
        # `_wrap_bare_paren_colon_titles` 转星 `**…（1 RP）： **`，split
        # `_RE_TITLE` 组4 剥冒号，正文并入无污染
        if tail and re.search(r"[)）][：:]", tail):
            return m.group(0)
        # M16：纯大写缩写（DC/AC/HD/RP…）不是条目名——`此豁免 DC 基于
        # 魅力` 的 en=`DC` 是豁免缩写，拆出产生伪条目「此豁免」（透肌魔人
        # 实测）。1-3 字符全大写为缩写形态；真实条目 EN 为完整词/短语
        # （`Ancestral Enmity` 等，含小写或 >3 字符）。组2 非贪婪回溯
        # 会吞尾随空格（`DC `），strip 后判断
        if re.fullmatch(r"[A-Z]{1,3}", en.strip()):
            return m.group(0)
        title = f"**{name}（{en}）"
        if typ:
            title += f"〔{typ}〕"
        title += "**"
        base = f"[[fc:elided]]{title}"
        # M16：前置 `\n` 使行中匹配的标题独立成行（`_RE_TITLE` 行首锚定；
        # 前缀 `…获得。` 留在散文行并入前条目）——行首匹配时前缀为空，
        # `\n` 只产生无害空行
        return f"\n{base}\n{tail}" if tail else f"\n{base}"
    return _RE_RACE_BARE_CN_EN_LINE.sub(_repl, text)


def _race_split_types(cn: str) -> str:
    """类型归一透传：race 无专长类型白名单，括号内纯中文段原样返回。"""
    return cn


# ==================== RaceFormat ====================

class RaceFormat(BaseFormat):
    """种族格式解析：normalize 特有规则 + 公共层 → split 章节状态机。"""

    @property
    def category(self) -> str:
        return "race"

    def promote(self, text: str) -> str:
        return text

    def _normalize_custom(self, text: str) -> str:
        # race 特有前置（属性调整/出自行/星标拆中文/四星嵌套/译者行——
        # 公共层不覆盖的形态，先归一为标准标题形态供公共规则与 split 识别）
        text = _RE_STRIKE_SHELL.sub("", text)  # 删除线壳剥除（HTML <S> 产物，feat 同构）
        text = _strip_star_fullwidth_lead(text)  # 星后全角空格剥除（page_103 替换儿）
        # 血脉亚种表格行拆行（M6/KN118 + 兽态人镜像 M17）+ 表格分隔行剥除
        # （须在链首——拆出的 `**血脉名（中文）**` 标准标题形态后续规则不再
        # 触碰；分隔行转空行防并入条目 text）
        text = _fix_heritage_table_rows(text)
        # 裸 `---` 水平线剥除（KN123：stat block 章节分隔/段落分隔，110 行
        # 残留）——须在表格拆行后（`| --- | --- |` 已转空行，互不干扰）
        text = _strip_hr_lines(text)
        text = _split_long_lines(text)  # 超长行拆行最优先（page_752 无换行连续文本）
        # 四星嵌套/拆裂标题合并（M10 收尾）——须在 glue 拆行前：中段分裂
        # （`**高等地精****自燃术（****EN****）**`）glue 组2 以中文开头会先
        # 拆行成伪条目，先合并成标准标题后 glue 不再触碰
        text = _fix_quad_nested_title(text)
        text = _split_quad_glue_titles(text)  # 4 星粘连标题拆行（须在星标拆中文前）
        text = _split_dual_cn_titles(text)  # BotC 双段标题拆行（M3，须在星标拆中文前）
        text = _fix_ability_adj_line(text)
        text = _merge_source_cross_lines(text)
        text = _merge_ability_adj_lines(text)  # 数字断行合并（M10 BotS）
        text = _fix_cn_star_cn_glue(text)
        text = _strip_translator_lines(text)
        text = _fix_indent_starless_titles(text)  # 缩进无星条目补星（须在 4 星剥净后）
        # 公共层安全子集（feat 链裁剪，验证确认对 race 形态无副作用）
        text = _merge_cross_line_en(text)
        text = _merge_table_continuation(text)
        # 专长简述表行剥除（KN133 物品粘专长简述表家族）——须在合并后
        # （数据行 EN/中文跨行）；表行并入前一条目（熏香/不稳定促进剂）会
        # 污染物品 text，剥除后信息由专长详述条目承载
        text = _strip_feat_table_rows(text)
        # Obsidian 图片引用剥除（M10 收尾，2026-08-04）：`![[图片]](URL)`
        # 完整或 `![[图片]` 截断形态整串剥除——须在 _strip_http_links 前
        #（URL 先剥会留 `![[图片]` 残壳）；race 无 pfs_eligible 字段，
        # 不需公共 `_mark_pfs` 的 [[PFS]] 标记语义
        text = _RE_IMAGE_REF.sub("", text)
        text = _strip_http_links(text)
        text = _fix_elided_quadruple_title(text)
        text = _fix_quadruple_star(text)
        text = _merge_type_seg_line(text)
        # guard=True：只拆 `）****(`/`）****（` 截断形态——feat 侧默认
        # 无条件拆 `****（` 会误伤 race 全角嵌套标题（援护防御 page_160），
        # 守卫参数使两类目各取所需（2026-08-04 e80ec0e 误伤 feat 后收敛）
        text = _fix_quad_star_halfparen(text, guard=True)
        # race 无「**中文：**English****」粘连形态（KN083 专长特有），
        # 传空标签集——守卫"组1 ∈ 标签集不转换"对 race 恒不触发
        text = _fix_colon_title_glue(text, set())
        text = _fix_label_trailing_star(text)
        text = _wrap_index_line(text)
        text = _split_field_chain_star_shells(text)  # 字段链星壳拆行（page_814 法术块）
        text = _wrap_bare_titles(text, set())
        # page_1456 聚合页来源标记（UW/WO）须在一切拆行规则前转标准冒号——
        # `_split_title_glue_paren` 等会把 `**X**UW：正文` 拆成无星行，
        # 转后星后冒号形态天然不拆（判定保留、标记不残留）
        text = _RE_SOURCE_MARKER.sub("**：", text)
        # 半兽人聚合 FCB 形态归一（须在拆行族前——`_split_inline_star_titles`
        # 会把 `**职业（EN）《书》：**正文` 的正文拆走，先归一成标准标题形态
        # `**职业（EN）：**正文` 后星后冒号守卫天然不拆）
        text = _RE_FCB_BOOK_SOURCE.sub(r"\1：**\2", text)
        # R1 根目录粘连形态（M1~M13 同 feat 顺序）
        text = _fix_star_outside_en(text)
        text = _split_title_glue_paren(text)
        text = _split_title_glue_cn_en(text)
        text = _wrap_star_cn_en_titles(text)  # 星内中文+EN 补括号（page_716 专长）
        text = _split_inline_star_titles(text)  # 行中星标题拆行（page_716 压缩文本）
        text = _split_bare_section_titles(text)  # 裸章节标题拆行（page_716 章节）
        text = _fix_star_outside_en_type(text)
        text = _split_closed_title_source(text)
        text = _fix_spaced_parens_cn_en(text)
        text = _split_closed_title_colon(text)
        text = _fix_fc1v_paren_en(text)
        text = _fix_fc1n_no_closing_star(text)
        text = _wrap_hash_titles(text)
        text = _wrap_hash_titles_type_en(text)
        text = _wrap_hash_titles_cn_en(text)
        text = _wrap_h2_titles_race(text)  # H2 裸中文/带括号（race 特有补缺）
        text = _wrap_bare_cn_en_lines(text)
        text = _wrap_bare_cn_en_lines_race(text)  # 空格形态（race 特有）
        text = _wrap_bare_paren_colon_titles(text)  # 裸中文（EN）：标题（FCB 形态）
        text = _wrap_bare_colon_titles_race(text)  # 裸中文冒号行（M10 BotS）
        text = _wrap_bare_cn_en_allcaps(text)
        # PFS 禁用/修订尾注拆行（M8/KN114）：`**X（EN）** PFS禁用` 星壳闭合后有
        # 尾注 → `_RE_TITLE`（行尾 $ 锚定）不匹配 → 整行并入前一条目（矮人 6 处/
        # 半身人 5 处，全库 62 处）。拆出后 PFS 标记独立行走散文并入刚建的标题
        # cur，标记信息保留在 text（检索端可查 PFS 状态）。须在
        # `_normalize_whitespace_title` 之前——钢铁公民 `（PFS修订：` 跨行长尾注
        # 会被 `_RE_WS_TITLE` 重写吞掉星壳闭合（`[[fc:whitespace]]**钢铁公民（Iron
        # Citizen）（PFS修订：…**`），先拆行则首行变纯标题形态不受影响。
        text = _fix_pfs_tail_notes(text)
        text = _normalize_whitespace_title(text)
        # M10：whitespace 断行合并标记剥除（标题行前缀）——`[[fc:whitespace]]
        # **人形怪物（Monstrous Humanoid）**` 行首标记使 `_RE_TITLE` 失配 →
        # 整行并入散文。whitespace 标记仅表示「断行合并产物」，内容完整无
        # 信息损失，剥除恢复标准标题形态；elided 标记（截断标题）保留——
        # 检索端降权信号
        text = _RE_WS_PREFIX_TITLE.sub("", text)
        text = _fix_field_star_right(text)
        text = _fix_field_star_left(text)
        text = _fix_bare_label_colon_nextline(text)
        text = _split_inline_fields(text, _RE_RACE_FIELD_SPLIT_BARE)
        text = _wrap_bare_field_labels(
            text, _RE_RACE_BARE_FIELD_LABEL, _RE_RACE_BARE_FIELD_LABEL_PERIOD
        )
        text = _fix_star_shell_remnants(text)
        # 次行正文剥行首星（`**【炼金炸弹】…` → `【炼金炸弹】…`，须在链尾——
        # 剥星后无星行若提前出现会被裸行规则重新包星）
        text = _RE_FCB_BODY_LEAD_STAR.sub(r"\1", text)
        return text

    # ---- split：章节状态机 ----

    def _match_section(self, line: str) -> str | None:
        """章节标题判定：`**中文（EN）**` / `**裸中文**` 含章节关键字 → kind。

        关键字在括号内/外均命中（`种族特性替换（Alternate Racial Traits）`
        与 `霜巨人魔法物品` 同口径）；无关键字 → None（非章节标题）。

        关键字只查标题串（组1+组2，不含组3 类型标签）——标题与描述同行的
        条目（ISR `**中文——特性名（EN）：**描述…`）不得因描述含「法术」等
        字样误判章节（2026-08-04 ISR 其他文件 38 条误判 race_spell 修复）；
        组3 尾缀（`〔战斗〕`/`【种族特性】`）是条目标签不是章节标题——
        `**半身人霉咒（Halfling Jinx）【种族特性】**` 不得误判 race_trait
        章节（2026-08-04 剪影人/霉咒 H2 形态修复）。
        """
        m = _RE_TITLE.match(line) or _RE_BARE_CN_TITLE.match(line)
        if not m:
            return None
        # 组2 为 RP 标注（`（10RP）`）→ 种族条目非章节标题：`**兽态人
        # Skinwalker种族特性**（10RP）` 组1 虽含「种族特性」，但 RP 标注
        # 是种族条目特征（页首主条目），不得切 race_trait 章节吞掉
        # （2026-08-04 K 簇 page_806 修复）；`**种族特性替换
        # （Alternate Racial Traits）**` 组2 非 RP → 正常切章节
        if m.lastindex and m.lastindex >= 2 and re.fullmatch(r"\d+\s*RP", m.group(2) or ""):
            return None
        # 能力段形态排除（2026-08-04 M21）：带括号标题组2 以 `, Ex|Su|Sp`
        # 结尾（`**海威专长（Aquatic Prowess Feat, Ex）**`）是 archetype
        # 能力段非章节标题——中文名含「专长」/「法术」等章节关键字子串时
        # 被 _match_section 误判章节：章节行不产条目（能力标题丢失、正文
        # 并入前一 chunk）+ state 整块切错（波涛守卫 5 能力段 race_feat
        # 污染、海威专长标题被吞）。与 L1655 退态逻辑同款正则（`, Ex/Su/Sp
        # 结尾 = 能力段，既有口径）；真实章节标题（种族特性替换/装备/法术
        # Spells）括号内无能力标记 → 零误伤
        if m.lastindex and m.lastindex >= 2 and re.search(
            r",\s*(?:Ex|Su|Sp)\s*$", m.group(2).strip(), re.IGNORECASE
        ):
            return None
        title_scope = m.group(1)
        if m.lastindex and m.lastindex >= 2:
            title_scope += m.group(2) or ""
        for kind, kws in _SECTION_KEYWORDS:
            for kw in kws:
                if kw in title_scope:
                    if kind == "race_spell":
                        # 法术章节形态校验（2026-08-04 审计发现，KN098 同家族
                        # 规模化）：race_spell 关键字「法术」是子串匹配，条目标题
                        # `**法术抗力（Spell Resistance）**` / `**类法术能力
                        # （Spell-Like Abilities）**` / `**卓越法术抗力
                        # （Noble Spell Resistance）**` / `**体质法术
                        # （Constitution Dependent）**` / `**深穿法术
                        # （Deep Magic）**` 命中后整页后续条目被切进 race_spell
                        # 态（page_164 特性 5 + 专长 4 污染，全库 44 doc/174
                        # race_spell 大量为特性/专长）。合法章节形态：
                        # 带括号 = 组1 以「法术」结尾 且 EN 匹配 `Spells?$`
                        # （忽略大小写——`伽瑟兰法术（GATHLAIN SPELLS）`/
                        # `蒿兰人法术（Ghoran Spell）` 单复数均合法）；
                        # 裸标题 = 组1 以「法术」结尾 且 不含句法虚词
                        # （怪物法典 `**地精法术**` 等 10 个合法裸章节 vs
                        # 正文句误包 `**当你施放该法术**` 等 28 行，见
                        # _SPELL_SECTION_BARE_BLOCKERS）。条目形态（「法术」
                        # 在标题中部、EN 非 Spell 结尾、裸标题含虚词）→ 非章节。
                        group1 = m.group(1) or ""
                        group2 = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
                        if m.lastindex and m.lastindex >= 2:
                            if not (group1.endswith("法术")
                                    and re.search(r"Spells?$", group2.strip(), re.IGNORECASE)):
                                continue
                        else:
                            if not group1.endswith("法术") \
                                    or any(c in _SPELL_SECTION_BARE_BLOCKERS for c in group1):
                                continue
                    return kind
        return None

    def _new_item(self, kind: str, name: str, name_en: str = "") -> dict:
        return {
            "kind": kind,
            "name": name,
            "name_en": name_en,
            "section": "",
            "replaces": "",
            "source": "",
            "text": "",
            "format_cluster": "standard",
        }

    def _kind_for_title(self, state: str, cur: dict | None, m: re.Match | None = None) -> str:
        """带括号标题在状态机下的 kind：intro 态首个 → race_intro、后续 →
        race_trait；带 `〔〕` 类型尾缀（`〔战斗〕`，裸文本流式专长的 elided
        标记形态）→ race_feat（不依赖章节标题，霜巨人页无「专长」章节）；
        其余章节态直接映射。

        KN134（2026-08-04）：overview 态（「种族概述」章节标题触发，全库
        仅 page_10）带括号标题 → race_intro——overview 条目只由表格行产出
        （_parse_overview_row 与 state 无关），overview 态出现的带括号标题
        是组标题/概念段（核心种族/常见种族/罕见种族/整体描述）与各族介绍
        段（`**矮人（Dwarves）**：…`），均为介绍性文字；直接映射 state 把
        41 个 chunk 全误标 race_overview。"""
        if state == "intro":
            if m is not None and m.group(3):
                return "race_feat"
            if cur is None:
                return "race_intro"
            return "race_trait"
        if state == "race_overview":
            return "race_intro"
        return state

    def _maybe_upgrade_bare_cn_title(self, cur: dict, line: str) -> bool:
        """裸中文标题条目 + 散文首行 → 升级 race_intro（狐妖规则）。

        散文分支与裸职业行（_RE_BARE_CN_COLON_UNSTARRED）fcb_entry 态
        并入路径共用——后者曾无升级逻辑，BotS 沙华鱼人 `**沙华鱼人**`
        + `来源：《海洋血脉》第17页` 被吞入 text 残留 fcb_entry（KN133，
        2026-08-04）。state 判据（仅残留章节态升级）由调用方检查——
        本方法只判 cur/line 形态，满足则改写 kind/删除标记并返回 True。
        """
        if not cur.get("_bare_cn_title"):
            return False
        if cur.get("text"):
            return False
        if not line.strip():
            # 空行不升级（M9 回归双保险：elided 剥后空行曾落此分支
            # 升级无辜壳并重置 state）
            return False
        if re.match(r"^[一-鿿]{1,8}[（(]", line.replace("**", "")):
            # 升级行是标题形态（`啮咬（Venomous Bite, Ex）`/`物（Nagaji
            # Magic Items）`，剥星后中文段紧跟括号）不是散文——能力条目/
            # 章节标题残段不得升级（2026-08-04 M9 回归：page_26 毒性/
            # 娜迦裔奇被标题行误升级 race_intro 并重置 state）
            return False
        if re.match(r"^[+−-]?\d", line.replace("**", "")):
            # 升级行是数值开头（属性调整值行 `+2**，魅力**…`，剥星后
            # 数字开头）也不是散文——stat block 字段行不得升级
            # （2026-08-04 M9 回归：page_16 半身人「敏捷」裸标题被值行
            # 升级 race_intro 并重置 state → 4 字段被并入上一字段条目
            # 丢失）
            return False
        if not re.search(r"[一-鿿]", line):
            # 升级行须含中文字符——散文必有汉字，无汉字符号行（`】`
            # 速查尾残留、纯英文行）不是散文（2026-08-04 M9 回归：
            # page_163 血族武器「沙包」裸标题被 `】` 行升级 race_intro）
            return False
        if cur.get("source"):
            return False
        if any(w in line for w in _GLUE_GUARD_WORDS):
            # 散文行含章节关键词（ISR 精灵/矮人 `**精灵****精灵角色…`
            # 分组节标题 + 说明行）——升级会吞并说明、污染 kind
            return False
        cur["kind"] = "race_intro"
        del cur["_bare_cn_title"]
        return True

    # 概述表分组行（`| 核心种族 |`）与表头行——首格无括号中文且无数字/无岁寸
    # 特征的行不产条目；分组词显式排除（源数据表结构语义，非业务特判）
    _OVERVIEW_GROUP_WORDS = ("核心种族", "常见种族", "罕见种族")

    # 概述表表头行列名全集（page_10 两行：`| 种族 | 种族属性调整 | 生物类型 |
    # 体型 | 速度 | 感官 |` + `| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |`）。
    # KN134（2026-08-04）：表头行经 _parse_overview_row 拒绝后曾随 pending
    # flush 污染「核心种族」组标题 chunk text；cells 全 ∈ 集合才剥除——数据行
    # 必含非列名格，page_11 表头（起始年龄/天赋骰/男高 等）与武器表/法术块
    # 表头（价格/学派 等）不在集合不误伤
    _OVERVIEW_HEADER_CELLS = frozenset((
        "种族", "种族属性调整", "生物类型", "体型", "速度", "感官",
        "力量", "敏捷", "体质", "智力", "感知", "魅力",
    ))

    def _parse_overview_row(self, line: str) -> dict | None:
        """表数据行 → race_overview 条目。

        两类表（均以种族名为行首，2026-08-04 扩展支持 page_11）：
        - 概述表 11 格：`| 种族（EN） | 六列属性 | 生物类型 | 体型 | 速度 | 感官 |`
          （page_10，六列属性组装 + 类型/体型/速度/感官）
        - 年龄表 9 格（含「岁」）：`| 种族 | 起始 | 天赋骰 | 自学骰 | 训练骰 |
          中年 | 老年 | 暮年 | 最大年龄 |`（page_11，列错位源数据按表头语义映射）
        - 身高体重表 9 格（含「寸」）：`| 种族 | 男高 | 男重 | 男骰 | 男乘 |
          女高 | 女重 | 女骰 | 女乘 |`（page_11）

        拒：表头行（无数字）、分组行（首格分组词）、武器表行（含 gp/d 磅/尺
        但无岁/寸——`重型捕俘十字弓 80尺` 射程表）、格数不足行。
        """
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6:
            return None
        # 分组词在数据行首格（真实 12 格行：`| 核心种族 | 矮人（Dwarves） |…`
        # 概述表形态 + page_11 表形态 `| 常见种族 | 神裔 | 20岁 |…`，次格为
        # 裸中文，2026-08-04 KN130 修复：此前仅接受「中文（EN）」次格，page_11
        # 三个分组行（矮人/神裔/替换儿）整行静默丢失）：次格为「中文（EN）」
        # 或裸中文（`_RE_OVERVIEW_BARE`）时跳过分组格；独立分组行
        # （`| 核心种族 |`）与非族名次格仍拒
        if cells[0] in self._OVERVIEW_GROUP_WORDS:
            if len(cells) < 7:
                return None
            if not (_RE_OVERVIEW_ROW.match(cells[1])
                    or _RE_OVERVIEW_BARE.match(cells[1])):
                return None
            cells = cells[1:]
        m = _RE_OVERVIEW_ROW.match(cells[0])
        if m:
            name, name_en = m.group(1), m.group(2)
            bare = False
        else:
            if not _RE_OVERVIEW_BARE.match(cells[0]):
                return None
            name, name_en = cells[0], ""
            bare = True
        body = cells[1:]
        # 数据行特征：后续格含数字（表头行 `| 成年 | 天赋之力 |…` 无数字 → 拒）
        if not any(re.search(r"\d", c) for c in body):
            return None
        item = self._new_item("race_overview", name, name_en)
        if len(cells) == 6 and body[2] in _OVERVIEW_SIZES:
            # 6 格压缩行（半精灵/半兽人/人类，page_10 实测）：属性调整合并格
            # + 生物类型/体型/速度/感官——与 9 格表（含岁/寸）互斥
            item["ability_adj"] = body[0]
            item["bio_type"] = body[1]
            item["size"] = body[2]
            item["speed"] = body[3]
            item["senses"] = body[4]
            parts = []
            if item["ability_adj"]:
                parts.append("属性调整：" + item["ability_adj"])
            for label, v in (("生物类型", body[1]), ("体型", body[2]),
                             ("速度", body[3]), ("感官", body[4])):
                if v:
                    parts.append(f"{label}：{v}")
            item["text"] = "；".join(parts)
            return item
        if len(cells) >= 11:
            # 概述表：六列属性 + 类型/体型/速度/感官（page_10 现状）
            adj_parts = []
            for i, label in enumerate(_OVERVIEW_ADJ_LABELS):
                v = body[i]
                if v:
                    adj_parts.append(f"{v}{label}")
            item["ability_adj"] = "，".join(adj_parts)
            item["bio_type"] = body[6]
            item["size"] = body[7]
            item["speed"] = body[8]
            item["senses"] = body[9]
            parts = []
            if item["ability_adj"]:
                parts.append("属性调整：" + item["ability_adj"])
            for label, v in (("生物类型", body[6]), ("体型", body[7]),
                             ("速度", body[8]), ("感官", body[9])):
                if v:
                    parts.append(f"{label}：{v}")
            item["text"] = "；".join(parts)
            return item
        # 9 格表（page_11）：非概述态表行须含「岁/寸」特征（武器表行拒）
        joined = "|".join(body)
        if "岁" in joined:
            labels = ("随机起始年龄", "天赋之力", "自学成才", "训练有素",
                      "中年", "老年", "暮年", "最大年龄")
        elif "寸" in joined:
            labels = ("男性基础身高", "男性基础体重", "男性身高修正", "男性体重乘数",
                      "女性基础身高", "女性基础体重", "女性身高修正", "女性体重乘数")
        else:
            return None
        parts = [f"{lab}：{v}" for lab, v in zip(labels, body) if v]
        item["text"] = "；".join(parts)
        return item

    def split_into_items(
        self, text: str, *, source_name: str | None = None
    ) -> list[dict]:
        """章节状态机切分条目。

        - `<!-- -->` / `# H1` / `数据来源：` 行剥除（整理元信息）
        - `> 来源：` 引用块 → 绑定其后条目 source
        - 章节标题（含关键字）→ 切换状态；哨兵行 → pending replaces
        - 带括号标题 → 新条目（intro 首个 race_intro）；同名标题（PA 三重
          形态）→ 并入不重复；裸中文标题 → race_sidebar
        - `【速查】` 行 / 字段行 / 散文行 → 并入当前条目
        - overview 态表格行 → race_overview
        """
        items: list[dict] = []
        cur: dict | None = None
        state = "intro"
        pending_replaces: str | None = None
        pending_source: str | None = None
        pending_text: list[str] = []
        pending_race_h2 = False  # 整理注释信号：下一标题行是种族 H2（M9/KN127）

        def flush_pending(item: dict) -> None:
            nonlocal pending_source, pending_text
            if pending_source is not None:
                item["source"] = pending_source
                pending_source = None
            if pending_text:
                item["text"] = "\n".join(pending_text)
                pending_text.clear()

        elided_next = False  # 同行 elided 前缀：下一标题为碎片形态（2026-08-04 K 簇）
        # 索引式遍历：裸中文标题分支需前瞻下一行（KN131 替换组句判定）
        _lines = text.splitlines()
        for _i, raw_line in enumerate(_lines):
            line = raw_line.strip()
            if not line:
                continue
            # 整理元信息行剥除；`-source:` 注释携带种族 H2 信号（M9/KN127：
            # ISR 新种族/CtIE/BotS 逐种族注释 → 下一标题行重置 state 为 intro
            # 并切 race_intro，`__aggregate__` 聚合注释无信号）
            if line.startswith("<!--"):
                m_comment = _RE_SOURCE_COMMENT.match(line)
                if m_comment and m_comment.group(1).strip() != "__aggregate__":
                    pending_race_h2 = True
                continue
            if line.startswith("# "):
                continue
            if line.startswith("数据来源"):
                continue
            if line.startswith("> "):
                # 来源行在条目标题行之后（`**剪影人**` H2 转星 → `> 来源`）：
                # 绑定当前 source 空的条目（页面主条目），否则等下一条目承接
                if cur is not None and not cur.get("source"):
                    cur["source"] = line.lstrip("> ").strip()
                else:
                    pending_source = line.lstrip("> ").strip()
                continue
            # elided 标记：同行前缀形态 → 剥除并置 elided_next（下一标题为
            # normalize 跨行/粘连重写产物，建 cur 时打标记）；独立行形态 →
            # 标记当前 cur（`**中文**` 换行 `[[fc:elided]]` 的碎片化形态）
            if line.startswith("[[fc:elided]]"):
                line = line[len("[[fc:elided]]"):].strip()
                if line:
                    elided_next = True
                elif cur is not None and not cur.get("text"):
                    cur["_elided"] = True
                if not line:
                    # 剥后空行（碎片标记独立行）不再落后续分支——原实现漏
                    # continue，空行落进散文升级分支且判据对空行全过
                    # （`any(w in "" …)` 恒 False）→ 无辜裸中文壳被升级
                    # race_intro 并重置 state（2026-08-04 M9 回归：page_26
                    # 娜迦候选者粘连壳 → 候选者/变身/亮鳞膏 4 个误标）
                    continue
            # 哨兵行（replaces 绑定其后条目）——须先于章节判定：哨兵含
            # 「特性替换」关键字，后置会被 _match_section 吞成章节标题
            if _RE_SENTINEL.match(line):
                # KN135-3（2026-08-04）：replaces 剥「此特性替换」整句前缀
                # （`**此特性替换无畏**` → 无畏）——值只保留替换对象名，
                # 检索端按特性名对账，整句前缀污染（全库 192 处）
                pending_replaces = line.strip("*").replace("此特性替换", "")
                continue
            # H2 章节标题包星壳（2026-08-04 KN116 残留修复）：整理规范 H2
            # （`## 内海种族 ISR 其他种族替换特性` / `## 替换种族特性` /
            # `## 种族特性`）带 `## ` 前缀不匹配标题正则 → 章节判定不触发
            # → 替换特性文件（ISR×2 + BotC）条目全落默认态误标 race_trait
            # 103 条。仅含章节关键字的 H2 包星壳走章节判定（全库 6 处：
            # 种族特性×4/替换特性×1/天赋职业×1，命中即切态不产条目）；
            # 不含关键字的 H2（`## 矮人` 等种族/组标题）保持原行落散文
            # 吸收，行为不变
            if line.startswith("## ") and any(
                kw in line[3:] for _, kws in _SECTION_KEYWORDS for kw in kws
            ):
                line = f"**{line[3:]}**"
            # 章节标题
            sec = self._match_section(line)
            if sec:
                # 章节标题优先于种族 H2 信号（2026-08-04 KN116 残留：ISR
                # 替换特性文件 `<!-- ISR-source:… -->` 文件级注释被
                # _RE_SOURCE_COMMENT 匹配置 pending_race_h2，H2 章节切态
                # 后信号未被消费 → 下一条目「其他种族」切 race_intro 并
                # state 重置 intro → 98 条替换特性仍误标 race_trait）
                pending_race_h2 = False
                # 章节切换前弹掉前一 elided 碎片/章节形态空 cur（K 簇：娜迦
                # elided 残片在 `**种族特性**` 章节行漏网——章节分支原不弹
                # cur，字段行正文被碎片承接）
                if (
                    cur is not None
                    and not cur.get("text")
                    and _is_dedup_section_cur(cur)
                    and items
                    and items[-1] is cur
                ):
                    items.pop()
                    # 弹后 cur 置空：后续表格/字段行改走 pending_text，由
                    # 下一条目 flush 承接（page_166 地精武器表/蝮血裔字段行
                    # 曾随被弹 cur 丢失——2026-08-04 K 簇全库 diff 实证）
                    cur = None
                state = sec
                pending_text.clear()  # 章节切换后散文行从零暂存
                # 哨兵继承在章节边界重置（KN133：新章节是新替换组边界，防跨
                # 章残留 binds 到无关条目）
                pending_replaces = None
                continue
            # 出自行 → source（存全串「出自《…》」，引用块口径一致）；
            # 组3（（EN）括号内英文）非 None 时保留英文学名（PA 熵裔/秩裔
            # 形态；不用 lastindex 判——交替分支内子组 lastindex=2 失真）
            m = _RE_SOURCE_LINE.match(line)
            if m:
                en = m.group(3) or ""
                source = f"出自《{m.group(1)}》" + (f"（{en}）" if en else "")
                if cur is not None:
                    cur["source"] = source
                elif pending_source is None:
                    pending_source = source
                continue
            # 带括号标题 → 新条目
            m = _RE_TITLE.match(line)
            if m:
                # 种族 H2 空 text：首个标题行并入 H2 作正文（M9/KN127，ISR
                # 勒珊塔灵族 H2 后 `**勒珊塔灵族角色（Lashunta Characters，
                # 11 RP）**：拉申塔人是…` 形态）——H2 无正文则 dedup 弹掉
                # 种族条目；并入后 text 非空正常切出（只并入一次）。
                # M17c 守卫：仅并入「H2 名是标题行前缀」的标题行（ISR
                # 勒珊塔灵族 H2 → `**勒珊塔灵族角色（…）**` 简介标题）——
                # 独立子条目标题（BotC `**妖鬼婆裔替换儿（…）**`、PHH
                # `**宝石之魂（…）**`）并入会把首个子条目吞进 H2 壳
                # （`---` 剥除前旧库靠 `---` 行侥幸填充 H2 text 未暴露；
                # 组4 `：正文` 不可用——normalize 已把 `**X**：正文` 拆成
                # 标题行+正文行，组4 恒空）
                if (
                    cur is not None
                    and cur.get("_race_h2")
                    and not cur.get("text")
                    and m.group(1).startswith(cur.get("name", ""))
                ):
                    cur["text"] = line
                    del cur["_race_h2"]
                    continue
                name = m.group(1).strip()
                # 怪物数据块字段章节（`**描述（Description）**` 等，elided
                # 星壳化产物）与 KN100 字段标题（`**先决条件（Prerequisite）**
                # **` 半人马变体 stat block 形态）→ 并入当前主体条目，不产
                # title='描述'/'先决条件' 的伪条目（2026-08-04 K 簇回归 +
                # KN100 追加小节）；无当前条目时照旧建条目
                # ⚠️ 只查 `_ENTRY_FLOW_FIELD_LABELS` 不查 `_ALL_FIELD_LABELS`：
                # ARG 字段词（祖先/属性调整/鬼婆血统觉醒等）带括号形态全库无
                # 字段行场景——BotC「**鬼婆血统觉醒（Awakened Hag  Heritage）**」
                # 是带 EN 括号的真亚种血统条目标题，M1 词表补丁后曾被误吞
                # （2026-08-04 M2/M3 修复）；BotN 字段链 `**祖先**：` 星壳冒号
                # 形态走 COLON 分支（词表在 L1265 判定），不经此分支
                # M12 特例「弱点」：page_204 狗头人 stat block `**弱点
                # （Weakness）**`（星壳嵌套剥除后带 EN 括号形态）是字段行
                # 应并入（全库仅此一处）；裸形态 `**弱点**：`（page_163
                # 速查残留段正文）不入词表——由 L1662 `_ALL_FIELD_LABELS`
                # 判定切独立条目（S4 簇锁定，M18 吐槽删除范畴）
                if (
                    cur is not None
                    and (name in _MONSTER_BLOCK_SECTIONS
                         or name in _ENTRY_FLOW_FIELD_LABELS
                         or name == "弱点")
                ):
                    text_line = line
                    if text_line.startswith("**") and text_line.endswith("**"):
                        text_line = text_line[2:-2]
                    cur["text"] = (cur["text"] + "\n" + text_line).strip()
                    continue
                # 能力块法术表标题误切退态（2026-08-04 KN107 对账）：变体能力
                # 块内法术列表表标题（`**钢铁法术（Steel Spells）**`，page_12
                # 锻造大师）形态完全符合合法 race_spell 章节校验（组1「法术」
                # 结尾 + EN 复数），被切 race_spell 态 → 后续能力条目全污染。
                # 能力条目带 Ex/Su/Sp 标记（`**神圣铁匠（Divine Smith, Su）**`）
                # → 遇首个即永久退态 race_archetype（后续无标记能力/专长随退态
                # 归位）。巨魔法术等合法章节后是无标记法术条目 → 不触发零误伤。
                if (
                    state == "race_spell"
                    and m.lastindex
                    and m.lastindex >= 2
                    and re.search(r",\s*(?:Ex|Su|Sp)\s*$", m.group(2).strip(), re.IGNORECASE)
                ):
                    state = "race_archetype"
                name_en, _types = _split_paren_content(m.group(2), _race_split_types)
                # RP 标注（`（10RP）`）是种族点数非英文名，剥出防检索污染
                # （2026-08-04 K 簇 page_806 主条目修复）
                if re.fullmatch(r"\d+\s*RP", name_en.strip()):
                    name_en = ""
                # 章节标题去重：前一 cur 为纯章节标题（无正文 + 章节/碎片
                # 形态，`**种族替换规则（EN）**` 后直接跟下一标题）→ 不入库。
                # `_is_dedup_section_cur` 三路判据（章节词/elided 标记/kind），
                # 防误弹真实条目（破敌之锤 race_archetype 无标记、审判者
                # fcb_entry——2026-08-04 K 簇误弹修复）
                if (
                    cur is not None
                    and not cur.get("text")
                    and _is_dedup_section_cur(cur)
                    and items
                    and items[-1] is cur
                ):
                    items.pop()
                    # 弹后 cur 置空：同名合并判据（下方）需 cur 非空才命中——
                    # 不置空时后续同名标题 continue、散文并入已弹死 dict 整段
                    # 丢失（2026-08-04 M2 修复，与章节分支/裸标题分支对称）
                    cur = None
                # 同名合并（PA 三重标题/ISR 拼接：半角/全角括号标题重复 →
                # 并入当前条目不重复建；兽态人等 ISR 形态同名标题）
                # fcb_entry 态例外：半兽人聚合 FCB 同职业多书多条
                # （炼金术师 ARG+HA = 40 条目）是合法数据形态，必须各自产出
                # （2026-08-04 KN107 K2）
                if (
                    cur is not None
                    and name == cur["name"]
                    and state != "fcb_entry"
                ):
                    # 同名补英文名（M9/德洛人回归）：H2 页眉转星
                    # `**德洛人**`（无 en）后跟带括号主条目
                    # `**德洛人（Derro）**` 同名 → 合并时补 name_en，
                    # 防英文名随页眉条目丢失（普通 PA 三重/ISR 拼接
                    # 同名合并语义不受影响）
                    if not cur.get("name_en") and m.group(2):
                        cur["name_en"] = m.group(2)
                    continue
                # 变体能力（星标拆中文等）已由 normalize 修复为完整标题 → 独立切出
                #（2026-08-04 删除并入分支：`**魅影身姿（Phantom Presence, Ex）**`
                # 等 archetype 态能力被并入变体主条目 → page_160 变体能力丢失）
                # 种族 H2 信号（M9/KN127）：注释标记的下一标题重置 state 为 intro
                # 并切 race_intro——多种族文件第 2 个种族起不被残留章节态误标
                if pending_race_h2:
                    kind = "race_intro"
                    state = "intro"
                    pending_race_h2 = False
                    race_h2_mark = True
                else:
                    kind = self._kind_for_title(state, cur, m)
                    # 真主条目标记：intro 态首个带括号标题（透肌魔人
                    # `**透肌魔人（Trox）**` 等怪物/血脉文件主条目）空 text
                    # 时靠 `_race_h2` 并入首个标题行防 dedup 弹掉。章节壳
                    # 守卫：名含章节词（`**种族替换规则（EN）**` 等 K6B
                    # 样本）不标记、保持被弹——2026-08-04 M9 回归：标记
                    # 收窄到注释信号后 7 个文件主条目 race_intro 被弹
                    race_h2_mark = kind == "race_intro" and not any(
                        w in name for w in _DEDUP_SECTION_WORDS
                    )
                item = self._new_item(kind, name, name_en)
                if race_h2_mark:
                    # 种族 H2 标记：空 text 时首个标题行并入作正文（ISR
                    # 勒珊塔灵族 H2 后 `**勒珊塔灵族角色（…）**：` 形态），
                    # 防 dedup 弹掉种族条目（M9/KN127）
                    item["_race_h2"] = True
                if elided_next:  # 同行 elided 前缀 → 碎片形态标记（K 簇去重判据）
                    item["_elided"] = True
                    elided_next = False
                # 哨兵组级绑定（KN133 2026-08-04）：`**此特性替换无畏**` 声明
                # 一组替换对象（半身人汇总 15 哨兵 vs 108 条目），原实现绑定
                # 后清空 → 仅组首条目命中，共享特性（精类思维/昏暗精准等 5 条
                # text 尾部无「取代」句）replaces 错解析为 None；保持继承直到
                # 下一哨兵覆盖（单条目语义的 CLUSTER_B 逐条哨兵覆盖式同样正确）
                if pending_replaces is not None:
                    item["replaces"] = pending_replaces
                flush_pending(item)
                items.append(item)
                cur = item
                if m.group(4):
                    # 标题行闭合星残留：组4 `([：:].*)?` 贪婪吞闭合星
                    # （`**标题（EN）：**` → 组4=`：**`），剥星壳后才是正文
                    # （2026-08-04 page_752 拆行后标题独立成行暴露）
                    text = m.group(4).lstrip("：:").strip()
                    if text.startswith("**"):
                        text = text[2:]
                    if text.endswith("**"):
                        text = text[:-2]
                    cur["text"] = text.strip()
                continue
            # 裸中文标题 → 条目（章节关键字裸标题已在上方章节分支命中）
            m = _RE_BARE_CN_TITLE.match(line)
            if m:
                # KN100 字段行（`**效果**`/`**频率**` 等裸标题，normalize
                # `====**效果**====` 横幅/`_wrap_star_cn_en_titles` 拆行
                # 产物）→ 并入当前条目，不产 title=字段名的伪条目；正文
                # 零丢失（cur 空时走 pending，由下一条目 flush 承接）。
                # ⚠️ 必须先于下方碎片弹掉判据：字段行是主体条目（鼠族等
                # 空 text intro 标题）的正文，弹掉判据会把主体误弹后并入
                # 死 dict → 整条目丢失（2026-08-04 KN100 d 实测）
                if m.group(1) in _ALL_FIELD_LABELS:
                    if cur is not None:
                        cur["text"] = (cur["text"] + "\n" + line).strip()
                    else:
                        pending_text.append(line)
                    continue
                # 章节标题去重（同上：`**战蜥人**` 后无正文直接跟 `**新规则**`；
                # 审判者 fcb_entry 误弹修复——裸标题分支 pop 判据同带括号分支）
                if (
                    cur is not None
                    and not cur.get("text")
                    and _is_dedup_section_cur(cur)
                    and items
                    and items[-1] is cur
                ):
                    items.pop()
                    # 弹后 cur 置空：后续字段行改走 pending（守卫行若并入
                    # 死 dict 会整段丢失——2026-08-04 KN100 守卫引入后
                    # 补齐，与章节分支先例一致）
                    cur = None
                if pending_race_h2:
                    # 注释信号（M9/KN127）：下一裸中文标题是种族 H2
                    kind = "race_intro"
                    state = "intro"
                    pending_race_h2 = False
                    item = self._new_item(kind, m.group(1))
                    item["_race_h2"] = True
                else:
                    # KN131（2026-08-04）：替换特性组标题前瞻——下一行是
                    # 替换组句（page_752 形态，聚合文件靠 `## 核心种族替换
                    # 特性` 章节切 alt_trait，页文件无章节标题）→ 切 alt_trait
                    # 态：组标题 alt_trait（text=组句）+ 组内条目全 alt_trait
                    if (_i + 1 < len(_lines)
                            and _RE_ALT_TRAIT_GROUP_INTRO.match(
                                _lines[_i + 1].strip())):
                        kind = "alt_trait"
                        state = "alt_trait"
                    elif state == "intro":
                        kind = "race_sidebar"
                    else:
                        # 裸中文行 + 无注释信号（BotB 型）：打标记待散文行升级——
                        # `**狐妖**` 在 fcb_entry 章节后按残留态切错 kind，首行
                        # 并入散文时升级 race_intro 并重置 state（见散文分支）
                        kind = state
                    item = self._new_item(kind, m.group(1))
                    item["_bare_cn_title"] = True
                if elided_next:  # 同行 elided 前缀 → 碎片形态标记（K 簇去重判据）
                    item["_elided"] = True
                    elided_next = False
                # 哨兵组级绑定（KN133 2026-08-04）：`**此特性替换无畏**` 声明
                # 一组替换对象（半身人汇总 15 哨兵 vs 108 条目），原实现绑定
                # 后清空 → 仅组首条目命中，共享特性（精类思维/昏暗精准等 5 条
                # text 尾部无「取代」句）replaces 错解析为 None；保持继承直到
                # 下一哨兵覆盖（单条目语义的 CLUSTER_B 逐条哨兵覆盖式同样正确）
                if pending_replaces is not None:
                    item["replaces"] = pending_replaces
                flush_pending(item)
                items.append(item)
                cur = item
                continue
            # 纯中文条目（`**圣武士**：…`）——FCB 态与条目流态（物品/专长/
            # 法术，X 非字段标签）产条目；其他态是字段行（`**体貌描述**：…`）
            # 并入当前条目，不产伪条目
            m = _RE_BARE_CN_COLON.match(line)
            if m:
                if state == "fcb_entry":
                    item = self._new_item("fcb_entry", m.group(1))
                    flush_pending(item)
                    items.append(item)
                    cur = item
                    cur["text"] = m.group(2).strip()
                elif state in ("race_item", "race_feat", "race_spell") \
                        and m.group(1) not in _ENTRY_FLOW_FIELD_LABELS:
                    # 条目流态（page_1456 驱兽剂/攀爬藤蔓/抓握藤蔓形态）：
                    # `**X**：` 且 X 非字段标签（价格/先决条件等）→ 新条目
                    item = self._new_item(state, m.group(1))
                    flush_pending(item)
                    items.append(item)
                    cur = item
                    cur["text"] = m.group(2).strip()
                elif state == "race_trait" and m.group(1) not in _ARG_FIELD_LABELS:
                    # ARG 纯中文特性（`**起始语言**：…`）→ 独立条目，非
                    # 字段行（2026-08-04 审计修复伴生：race_spell 误判修复
                    # 后起始语言回到 race_trait 态，既有「并入 cur」分支会
                    # 吞掉独立特性——全库 ARG 种族页均有此特性）
                    item = self._new_item(state, m.group(1))
                    flush_pending(item)
                    items.append(item)
                    cur = item
                    cur["text"] = m.group(2).strip()
                elif cur is not None:
                    # 字段行（`**体貌描述**：…`）并入当前条目，星壳保留
                    # （A 簇既有口径：字段行是正文一部分，检索保留字段标记）
                    cur["text"] = (cur["text"] + "\n" + line).strip()
                continue
            # 裸职业行（无星壳 `野蛮人：…`，BoS 剪影人/窃影鬼 FCB）：仅
            # fcb_entry 态切条目（M7）——FCB 章节内裸冒号行全为职业条目；
            # 其他态是散文行（含冒号的普通句子），保持并入 cur 既有行为。
            # 三守卫：①组1 含 fcb 章节关键字（BotB `天赋职业选项吟游诗人：`
            # 裸章节+条目粘连行，章节词在行首非行尾裸章节拆行不覆盖）→ 不切
            # title 污染伪条目；②cur 空 text（`**猎人（Hunter）**` 标题独立
            # 成行后的正文行，page_13 武器列表形态）→ 并入标题 cur 非切条目；
            # ③组2 以「边栏」开头（page_1456 `引述: 边栏：种植藤蔓莱西`
            # 边栏标记行）→ 非职业条目，并入 cur 保持既有行为
            m = _RE_BARE_CN_COLON_UNSTARRED.match(line)
            if m and state == "fcb_entry":
                if not _RE_FCB_SECTION_WORD.search(m.group(1)) \
                        and not m.group(2).lstrip().startswith("边栏") \
                        and (cur is None or cur.get("text")):
                    item = self._new_item("fcb_entry", m.group(1))
                    flush_pending(item)
                    items.append(item)
                    cur = item
                    # 剥正文行首星壳残留（page_814 `野蛮人：**野蛮人的伤害
                    # 减免…`，源数据加粗从正文中开始）——与其他 FCB 条目
                    # text 形态一致
                    text = m.group(2).strip()
                    if text.startswith("**"):
                        text = text[2:]
                    cur["text"] = text
                elif cur is not None:
                    # 并入路径复用散文分支升级判定：裸标题（_bare_cn_title
                    # 无 text）的 fcb_entry 残留条目首行是裸冒号行（BotS
                    # 沙华鱼人 `来源：《海洋血脉》第17页`）→ 升级 race_intro
                    # 而非吞入 text 残留 fcb_entry（KN133，2026-08-04；
                    # 狐妖走散文分支有升级，此处曾缺失）
                    if self._maybe_upgrade_bare_cn_title(cur, line):
                        state = "intro"
                    cur["text"] = (cur["text"] + "\n" + line).strip()
                continue
            # 星壳闭职业行（`**吟游诗人：**从德鲁…`，page_814/815 FCB）：
            # 仅 fcb_entry 态切条目，守卫同裸职业行（章节词/边栏不切）
            m = _RE_BARE_CN_COLON_STAR_CLOSED.match(line)
            if m and state == "fcb_entry":
                if not _RE_FCB_SECTION_WORD.search(m.group(1)) \
                        and (cur is None or cur.get("text")):
                    item = self._new_item("fcb_entry", m.group(1))
                    flush_pending(item)
                    items.append(item)
                    cur = item
                    cur["text"] = m.group(2).strip()
                elif cur is not None:
                    cur["text"] = (cur["text"] + "\n" + line).strip()
                continue
            # 属性调整行（值星壳形态）：race_trait 态产独立条目——name=
            # 属性调整（与「生物类型/标准速度」字段 trait 平行），值+正文
            # 进 text 保检索（`+2敏捷，+2体质：正文`，星壳剥除）。其他态
            # 并入 cur（ISR intro 态属性行即该族 intro 正文，切出产空 intro）
            m = _RE_ABILITY_ADJ_TITLE.match(line)
            if m:
                if state == "race_trait":
                    item = self._new_item(state, "属性调整")
                    flush_pending(item)
                    items.append(item)
                    cur = item
                    cur["text"] = f"{m.group(1).strip()}：{m.group(2).strip()}"
                elif cur is not None:
                    cur["text"] = (cur["text"] + "\n" + line).strip()
                else:
                    pending_text.append(line)
                continue
            # 速查行 → 并入当前条目（不产伪条目）
            if _RE_QUICK_REF.match(line):
                if cur is not None:
                    cur["text"] = (cur["text"] + "\n" + line).strip()
                continue
            # 概述表格行：race_overview 态与 page_11 表行（9 格含岁/寸，非态
            # 由 `_parse_overview_row` 特征判定）→ race_overview 条目；其余
            # 表格行（武器表等）并入当前条目不产伪条目（2026-08-04 扩展）
            if line.startswith("|"):
                row = self._parse_overview_row(line)
                if row is not None:
                    items.append(row)
                    continue
                # KN134（2026-08-04）：overview 表头行剥除——cells 全 ∈ 列名
                # 集合即表头（_parse_overview_row 已按无数字拒掉，但行走
                # pending flush 污染组标题 chunk text），直接丢弃不承接
                if all(c.strip() in self._OVERVIEW_HEADER_CELLS
                       for c in line.strip("|").split("|")):
                    continue
                if cur is not None:
                    cur["text"] = (cur["text"] + "\n" + line).strip()
                else:
                    # cur 空（章节行弹 cur 后）→ 表格行改走 pending，由下一
                    # 条目 flush 承接（page_166 地精武器表曾随被弹 cur 丢失
                    # ——2026-08-04 K 簇全库 diff 实证）
                    pending_text.append(line)
                continue
            # 其余行（字段行/散文行）并入当前条目。散文行星壳剥除（2026-08-04
            # ISR 修复）：`**标题（EN）：**` 被 `_split_closed_title_colon` 拆行后，
            # 描述行尾残留 HTML <B> 闭合星（`…仇恨。**`）——行首加粗词
            # （`**新规则**以下…` 无尾星）不剥，行内星保留
            if cur is not None:
                # 裸中文标题行升级（M9/KN127，BotB 型）：`**狐妖**` 建条目后
                # 首行并入为散文 → 种族主条目——升级 race_intro 并重置 state
                # （后续背景 race_trait/替换特性 alt_trait/FCB fcb_entry 归位）。
                # 守卫：该分支仅承接散文/碎片行（标题/字段/表格/速查已先行
                # 分支），首行即散文段即 BotB `**种族名**　　散文` 拆行形态。
                # ⚠️ 不升级判据（2026-08-04 簇 G/L/H/K6B 回归守卫）：
                # ① 残留章节态才升级——intro 态裸中文标题（怪物文件
                #    `**卓尔精灵**` 主条目、D 簇映射 monster_block；魔裔
                #    `**非人类魔裔**` 边栏条目）本来就是 race_sidebar
                #    正确语义，升级会把 18 个 monster_block 误抢成
                #    race_intro（2026-08-04 M9 回归实证）；
                # ② 已绑定 `> 来源` 的裸中文标题不升级；
                # ③ 散文行含章节关键词（ISR 精灵/矮人 `**精灵****精灵角色
                #    可以选择以下种族特性替换原本的…` 分组节标题 + 说明行；
                #    K6B `**娜迦**` 后跟章节说明）——升级会吞并说明、污染
                #    kind
                if (
                    state in ("race_trait", "alt_trait", "race_archetype", "fcb_entry")
                    # 仅残留章节态升级——条目流态（race_item/race_feat/
                    # race_spell）裸标题 + 散文是正常条目流（`**护颈**\n
                    # 护颈用于保护…` 物品条目形态），升级会把物品/专长/
                    # 法术条目误抢成 race_intro（2026-08-04 M9 回归：
                    # page_163 护颈裸标题被散文升级 race_intro）
                    and self._maybe_upgrade_bare_cn_title(cur, line)
                ):
                    state = "intro"
                pending_race_h2 = False
                if line.startswith("**") and line.endswith("**"):
                    # 守卫：剥壳后仍含 `**` → 字段链/粘连形态（豺狼人
                    # `**价格：**11000gp **重量：-**` 拆行后首尾星壳但中间
                    # 是字段链，`**重量：-**` 值在星内致行尾闭星），非 ISR
                    # 整行星壳残留（`**…仇恨。**` 剥壳后无星）→ 不剥
                    # （2026-08-04 #101 D 簇定性）
                    if "**" not in line[2:-2]:
                        line = line[2:-2]
                elif line.startswith("**") and line[2:].lstrip("：:；;。").startswith("**"):
                    # 行首空壳星对（`**：**有些精灵…` 4 星粘连拆行残留——
                    # 剥 `**` 后是标点+`**`）→ 剥行首闭合对；守卫限定星内
                    # 无中文，`**体貌描述**：…` 字段行不受影响（A 簇口径）
                    line = line[2:]
                    line = line.replace("**", "", 1)
                elif line.endswith("**"):
                    line = line[:-2]
                cur["text"] = (cur["text"] + "\n" + line).strip()
            else:
                pending_text.append(line)

        # 尾部待定文本（无条目承接）丢弃；尾部空 cur（纯章节标题）同丢弃
        # （判据同前两处 pop：真实条目如破敌之锤保留，K 簇修复）
        if cur is not None and not cur.get("text") and items and items[-1] is cur \
                and _is_dedup_section_cur(cur):
            items.pop()
        # 描述尾部替换说明兜底（无哨兵行形态，page_1456 莱西页/B 簇）：「本特性
        # 替换防御训练和仇恨。」/「该特性取代行踪无迹。」——文本在散文行 append
        # 后才组装完成，条目创建时（flush_pending）查不到 → 结尾统一补齐。
        # 只填充 replaces 派生字段，不裁剪 text（正文完整保留）
        for it in items:
            if not it["replaces"]:
                m = _RE_REPLACES_TAIL.search(it["text"])
                if m:
                    it["replaces"] = re.sub(r"\s+", "", m.group(1))
        return items
