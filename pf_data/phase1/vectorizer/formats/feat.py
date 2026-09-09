"""
formats/feat.py — 专长 Markdown 格式解析（六放行形态归一 + 条目切分）

设计依据：
  - 专长元数据设计.md §六（format_cluster 六形态：standard/whitespace/punct/
    lb_marker/img_marker/elided/annotation）
  - 开工前文档 §六 第 5 步：test_seeds.jsonl（26 条）驱动 TDD
  - 判别器执行顺序参照 format_clusters_规范与偏差对账.md §三

流程（BaseFormat 模板）：normalize（url/译者剥离 → 跨行英文合并 → 形态归一
→ 字段拆行）→ promote（恒等）→ split_into_items（标题识别 + 标记消费）。

关键机制：
  - 形态标记：normalize 检测到非标准形态时在行首插入 `[[fc:xxx]]` / `[[src:xxx]]`
    伪标记，split 时消费并写入 item（与 `[[PFS]]` 同思路，纯函数友好）。
  - 字段同行紧贴拆分：源数据常见 `值**标签：**` / `标签**：` / `。标签：` 三种
    残缺/粘连形态，统一归一为规范 `**标签：**` / `**标签**：` 并拆行为独立行，
    使 processor 层 parse_fields 可直接按行解析。
"""

import re
from typing import Optional

from vectorizer.formats.base import BaseFormat
# ---- 公共层（2026-08-04 抽取至 normalize_common.py，禁 copy 原则）----
from vectorizer.formats.normalize_common import (
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
    _mark_pfs,
    _merge_cross_line_en,
    _merge_table_continuation,
    _merge_type_seg_line,
    _normalize_whitespace_title,
    _split_closed_title_colon,
    _split_closed_title_source,
    _split_inline_fields,
    _split_title_glue_cn_en,
    _split_title_glue_paren,
    _strip_http_links,
    _wrap_bare_cn_en_allcaps,
    _wrap_bare_cn_en_lines,
    _wrap_bare_cn_type_paren,
    _wrap_bare_field_labels,
    _wrap_bare_paren_lines,
    _wrap_bare_titles,
    _wrap_hash_titles,
    _wrap_hash_titles_cn_en,
    _wrap_hash_titles_type_en,
    _wrap_index_line,
    _split_paren_content,
    _RE_ALIGN_SUFFIX,
    _RE_BARE_CN_EN_ALLCAPS,
    _RE_BARE_CN_EN_CNPAREN,
    _RE_BARE_CN_EN_LINE,
    _RE_BARE_CN_EN_PAREN,
    _RE_BARE_CN_EN_STAR,
    _RE_BARE_CN_EN_STAR_BOLD,
    _RE_BARE_LABEL_VAL,
    _RE_BOLD_GLUE_SPLIT,
    _RE_CLOSED_TRAILER_COLON,
    _RE_CLOSED_TRAILER_SRC,
    _RE_CN_EN_ADJACENT_STAR,
    _RE_COLON_TITLE_GLUE,
    _RE_CROSS_EN,
    _RE_CROSS_EN_CN,
    _RE_ELIDED_CN_EN_GLUE,
    _RE_ELIDED_INLINE_DESC,
    _RE_ELIDED_QUAD,
    _RE_FC1N_NO_CLOSING_STAR,
    _RE_FC1V_CLOSED_STAR_PAREN,
    _RE_FIELD_SPLIT_A,
    _RE_FIELD_SPLIT_B,
    _RE_FL_STAR_LEFT_BOL,
    _RE_FL_STAR_LEFT_SPLIT,
    _RE_FL_STAR_RIGHT,
    _RE_FRAGMENT_TAIL,
    _RE_FULL_STAR_LINE,
    _RE_HASH_TITLE,
    _RE_HASH_TITLE_CN_EN,
    _RE_HASH_TITLE_TYPE_EN,
    _RE_HEX_STAR,
    _RE_HTTP_LINK,
    _RE_HTTP_LINK_TAIL,
    _RE_HTTP_URL_LINK,
    _RE_INDEX_LINE,
    _RE_LABEL_TRAILING_STAR,
    _RE_NESTED_STAR,
    _RE_PAREN_NESTED_STAR,
    _RE_PFS_IMG,
    _RE_PFS_NEG,
    _RE_PROSE_LEAD,
    _RE_PROSE_LEAD_RX,
    _RE_QUAD_STAR,
    _RE_SHELL_BLANK_STAR_LINE,
    _RE_SHELL_BOL,
    _RE_SHELL_DASH,
    _RE_SHELL_EOL,
    _RE_SHELL_FIELD_QUAD,
    _RE_SHELL_ITALIC_TRAIL,
    _RE_SHELL_PFS_STAR,
    _RE_SHELL_QUAD_OPEN,
    _RE_SHELL_TRIPLE_OPEN,
    _RE_SPACED_PARENS_CN_EN,
    _RE_STAR_OUTSIDE_EN,
    _RE_STAR_OUTSIDE_EN_TYPE,
    _RE_STRIKE_SHELL,
    _RE_TABLE_CN,
    _RE_TABLE_CONT,
    _RE_TABLE_EN,
    _RE_TITLE_GLUE_CN_EN,
    _RE_TITLE_GLUE_PAREN,
    _RE_TYPE_SEG_LINE,
    _RE_WS_TITLE,
)

from vectorizer.registry_feat import (
    FEAT_ALL_FIELD_LABELS,
    FEAT_EXTRA_FORMAT_LABELS,
    FEAT_TYPE_NORMALIZE,
    split_feat_types,
)

# ---- 标题识别（split 用）----
# `**中文名（English）〔类型〕**` / `**中文名（类型，类型）**` 整行闭合形态。
# \2 括号内容可为英文名、类型标签或混合（逗号分隔）；\3 为尾部〔〕类型标签。
# \2 只排除全角闭括号——英文名可含半角括号（`(Combat)`，R1 M1b 归一产物），
# 半角 `)` 若也排除会在 `(Combat` 处截断导致标题整行不匹配。
_RE_TITLE = re.compile(
    r"^\*\*([^*\n]+?)\s*[（(]([^）〕］】]*)[)）]\s*([〔［【][^〕］】]+[〕］】])?\s*\*\*$"
)

# 分节标题（`**半鱼人专长**` 等有星无括号短行）→ 跳过不产条目、不并入条目 text
_RE_SECTION_HEADER = re.compile(r"^\*\*[^*\n]{1,30}\*\*$")

# ---- R4：AG 标题形态（判别器 FC-4/FC-3/FC-1q）----
# FC-4：`**中文（类型）English**` 类型括号后接英文名（奥多里战斗技艺）
_RE_TITLE_TYPE_EN = re.compile(
    r"^\*\*([^*\n]+?)\s*[（(]([^）)〕］】]*)[)）]\s*([A-Za-z][^*\n]*?)\s*\*\*$"
)
# FC-3：`**中文 English**` 无括号英文名（精魂信烽）
_RE_TITLE_CN_EN = re.compile(r"^\*\*([一-鿿]{2,})\s+([A-Za-z][^*\n]*?)\s*\*\*$")
# 能力标记（PF 标准缩写）：Extraordinary / Supernatural / Spell-like——
# 非专长类型，标题尾部 `（Ex）` 形态不得进 feat_type（KN084 残留）
_ABILITY_MARKS = frozenset({"Ex", "Su", "Sp"})
# 能力标记分支产物特征：text 以 `（Ex）\n` 行首开头——「子节标题排除」过滤的
# 放行信号（标记前缀 5 字符可把 text 顶过 150 阈值，WMH 庖丁解牛回归，KN084）
_RE_ABILITY_MARK_LEAD = re.compile(r"^（(?:Ex|Su|Sp)）\n")
# FC-1q 组1 尾部中文类型括号（三括号形态 `**中文（类型）（EN）〔**TYPE**〕**`
# 被组1 贪婪吞入，page_505 圣水攻袭/可能性之兵）：`圣水攻袭（战斗）` → 拆出。
# `$` 闭合守卫：真名含括号（`宿命（战斗）连锁`）不误伤。
_RE_NAME_TRAILING_CN_TYPE = re.compile(r"^(.*?)[（(]([一-鿿][^）)]*)[)）]$")

# FC-1q：`**中文（English）（类型）**（PFS不可用）` 英文括号在前、类型在后
_RE_TITLE_EN_TYPE = re.compile(
    r"^\*\*([^*\n]+?)\s*[（(]([A-Za-z][^）)]*)[)）]\s*[（(〔【［\[]([^）)\]〕】］]*)[）)\]〕】］]\s*\*\*\s*(?:（PFS不可用）)?\s*$"
)
# FC-1r：`**中文（类型）（English）**` 中文类型括号在前、英文在后（致命之角）
# EN 停在全角 `）`（半角括号允许内嵌——魔宠手记FF（Group Deliver Touch Spells
# (Teamwork)）型，判别器 FC-4「英文内嵌别名括号」同源容忍）
_RE_TITLE_CN_TYPE_EN = re.compile(
    r"^\*\*([^*\n]+?)\s*[（(]([一-鿿][^）)]*)[)）]\s*[（(]([A-Za-z][^）]*)[)）]\s*\*\*$"
)

# ---- R2：字段标签独立行（`**先决条件：**` / `**先决条件**`）----
# 标签 ∈ FEAT_ALL_FIELD_LABELS + FEAT_EXTRA_FORMAT_LABELS → 并入当前条目 text，
# 不产新条目（_RE_SECTION_HEADER 会误跳过，R2 根因）。
_RE_FIELD_LABEL_COLON = re.compile(r"^\*\*([一-鿿]{2,8})[：:]\*\*$")
_RE_FIELD_LABEL_BARE = re.compile(r"^\*\*([一-鿿]{2,8})\*\*$")
# 字段标签行首前缀（`**先决条件：**智力13` 值同行形态）——KN082 裸中文
# 条目标题字段佐证（后续行含字段标签行 → 条目身份），防正文「先决」词误判。
_RE_FIELD_LABEL_PREFIX = re.compile(r"^\*\*[一-鿿]{2,8}[：:]\*\*")
_ALL_FIELD_LABELS: set[str] = set(FEAT_ALL_FIELD_LABELS) | set(FEAT_EXTRA_FORMAT_LABELS)

# ---- KN109：描述格式模板节词表（title 命中即弹）----
# page_622（MA 神话冒险引言）/ page_194（CRB）的「专长描述格式」模板节：字段
# 标签词（先决条件/好处/正常/专长效果/通常状况/特殊/注意）+ 格式词（专长名称/
# 专长类型/专长描述），形态同 FC-1q 专长条目被误判入库——title 为模板词污染
# 检索（既有 page_194/856 7 个同族 chunk 一并清除）。真实专长 title 不可能为
# 这些词（test 03 佐证），弹掉安全；仅 standard 簇生效（lb_marker 索引行不弹）。
_TEMPLATE_SECTION_WORDS = frozenset({
    "专长名称", "专长类型", "专长描述",
    "先决条件", "好处", "正常", "专长效果", "通常状况", "特殊", "注意",
})

# ---- 子节标题排除（判别器 FC-1n/FC-3 佐证同源）----
# 闭合标题（standard）条目 text 无任何真字段标签 → 纯描述节（永罪"灵魂的价值/
# 特色"型规则小节，判别器 10 行窗口佐证也排除）。真字段 = **标签[：:]** /
# **标签**[：:] / 行首裸"标签："；`> 来源：…` 引用块以 `>` 开头，行首裸标签
# 正则不匹配，天然豁免（来源信息走 resolve_source，不在 text 内判字段）。
_FIELD_LABEL_ALT = "|".join(
    re.escape(x) for x in sorted(_ALL_FIELD_LABELS, key=lambda s: (-len(s), s))
)
_RE_FIELD_IN_TEXT = re.compile(
    rf"\*\*(?:{_FIELD_LABEL_ALT})\*\*[：:]|\*\*(?:{_FIELD_LABEL_ALT})[：:]\*\*|^(?:{_FIELD_LABEL_ALT})[：:]"
    r"|\*\*(?:常见信徒|类法能力)\*\*",
    re.MULTILINE,
)

# ---- R3：punct 标题（`**中文：**` 独立行，中文不在字段标签集 → 条目）----
_RE_PUNCT_TITLE = re.compile(r"^\*\*([一-鿿]{2,})[：:]\*\*$")
# FC-8n：裸中文条目标题（page_744 痛苦选项型）后行单星斜体描述佐证
# （判别器 FC-8n 定义：「后行单星 *描述* 佐证」）；与 `**半鱼人专长**`
# 分节标题区分——分节标题后行为正文（非单星斜体），维持跳过。
_RE_ITALIC_DESC = re.compile(r"^\*[^*\n]{2,}\*$")
# 正文强调/元信息词：`**重要：**` 等独立行非条目标题（并入 text，不产条目）
_NON_TITLE_EMPHASIS = frozenset({
    "重要", "注意", "警告", "提示", "附注", "备注", "说明", "注记", "注解",
    "注", "原文", "译者", "译注",
})

# ---- R5：正文句首黑名单（`_RE_BARE_CN_EN_PAREN` 排除正文伪标题）----
# 以连词/动词短语开头的行是正文句（"当你通过魔族仪典（Fiendish Obedience ）…"），
# 真条目标题是名词短语。负向前瞻锚定行首。
# 扩展（R5 全库 probe 实证）：page_1367『你向法术注入了来自骨园（Boneyard）…』、
# 任务与战役『你获得该定居点（settlement）…』、page_1564『当你使用元素拳
# APG…』等——第二人称动词短语与句式引导统一登记。引导取到短语层级（如
# 『阴影攻击能够』），避免与合法专长名词（『阴影攻击』本身）误配。

# ---- R5 扩展：M6 正文句伪标题守卫（`_wrap_bare_cn_en_lines` 用）----
# M6 `_RE_BARE_CN_EN_LINE` 把"中文English[中文尾缀]"整行当标题包裹，但源数据
# 断行把正文句拆成碎片行（page_1564『当你使用元素拳APG攻击造成寒冷伤害时…』、
# AG『你在对抗所选生物的AC上同样获得…』、专长45『达成你与GM在选取…』），
# 整行被包裹成"当你使用元素拳/APG"型伪标题。真条目标题行特征：
#   - 中文名是短名词短语（≤9 字）；≥10 字是句段碎片
#   - 不以句尾虚词结尾（『该生物的』『皆属』『达成你与』是断行悬挂）
#   - 长尾缀（英文后的中文）只在英文为 Title Case 时合法——水下冒险AA
#     英文拆两行+同行描述（『深呼吸Deep \\nbreath 你屏住…』→『Deep breath 你屏住…』）
#     是真条目；全大写缩写（APG/AC/GM）或小写描述（tangible object）的长尾缀
#     是正文续接（判别器 FC8E_RX 同口径：英文名是专有名词）
# 『计』从粒子表移除（seed 56）：『灵狐计（Kitsune Tricks）』是合法专长名词后缀，
# 非断行悬挂虚词；『此为一个或一群合计』等散文句由句首引导『此为一个』兜住。







# ---- normalize：跨行英文名合并（spell 同款）----
# `\r?\n` 兼容 CRLF 源数据（organized 目录 CRLF 行尾，page_530 盲目眩光
# `Blinding \r\nFlash` 形态；LF 文件 `\r` 可选不受影响）。缺 `\r?` 时
# 跨行合并失效 → 4 星/冒号标题链全失配 → 正文条目静默丢失（KN083 补充）。
# 中文前换行 + 标题式英文（`指引 \nCelestial`）合并：仅首字母大写词
# （`DIVERSE OBEDIENCE` 全大写行是 M10 两行包裹形态，不得合并）

# ---- normalize：表格跨行续行合并（seed 05）----
# `| Brewmaster\n酿造大师 | ...` → `| Brewmaster 酿造大师 | ...`。
# 仅合并"未闭合"表格行（行首 `|` 且行内无 `|` 结尾）+ 后续 `|` 结尾行——
# 完整表格行（`| A | B |`）行尾闭合 `|` 天然免疫，不会误并两行。
# 行首锚定 (?m:^)：\| 若匹配上一行行尾闭合 `|`，完整行会被逐行粘成
# 一行、仅首行产条目（page_195 专长索引表 150 行 → 0 产出的根因）。

# ---- normalize：PFS 图标 / 否定标记 ----

# ---- normalize：四星归一 ----
# 1) ****X**** → **X**（elided 常见包裹形态）
# 2) ****** → **（6 星收尾）
# 3) **中文（****English****）****** → **中文（English）**（嵌套剥皮，seed 06）
# 4) `中文（****English****，类型）****正文` 行首无星变体（KN070 纯洁勇士
#    page_515.html 三连加粗段转换产物）：_RE_NESTED_STAR 要求行首 `**`，
#    行首无星时嵌套星残留 → A 分支组2 吞 `*` 包裹 → split 不识别。不限行首
#    剥括号内嵌套星（组2 容括号内尾缀 `，团队专长`），让后续
#    _wrap_bare_titles 各分支正常匹配。`（**X**）` 嵌套星本身即转换残留，
#    剥星仅去加粗标记、语义不变（全库 222 行剥后均正确）。
# 5) `中文**English**（专长）****正文`（美德信条）：EN 星包裹在括号外、
#    中文名后无空格粘连（`<B>美德信条</B><B>Virtuous creed</B><B>（专长）</B>`）。
#    剥星后走 B 分支（星外中文类型括号）。组2 限定英文开头 + 后跟中文括号：
#    防字段序列 `先决条件**：值。**专长效果**：` 形态（组2 吞值再闭星）误剥
#    （全库 `中文**X**` 10574 行，绝大多数为行内字段序列，不可泛化剥星）。
# 6) `）****正文` 4 星粘连（标题闭星 + 正文开星并成 4 星）→ 拆行
#    `）**\n**正文`。`(?!\*)` 防 6 星（`_RE_HEX_STAR` 归一）与 5 星残留；
#    `(\S)` 防全角空格（E 分支 `**中文（EN）****　　*描述*` 形态）误拆。

# ---- normalize：elided 四星标题（seed 04）----
# `****酩酊侠**** \nDurnken Brawler****（战斗专长）*****正文` →
# `**酩酊侠（Durnken Brawler）〔战斗专长〕**\n正文`。
# 星号数量宽容（2-4 开/闭）：须先于通用 4→2 归一执行，否则
# `English****（类型）*****` 的星会被 _RE_QUAD_STAR 误配对改写。

# ---- normalize：半角括号 4 星包裹系列名标题（KN081，page_566 物品掌握专长族）----
# `**能力掌握**** ability Mastery(****物品掌握专长****)**`：HTML 表格
# 「中文名 | 英文名 | 系列名」三格加粗段粘连成一行，`_RE_ELIDED_QUAD` 只吃
# 全角括号（`（类型）`）漏此半角括号形态，`_RE_QUAD_STAR` 又把 `**** EN(****`
# 配对剥星 → 残留 `(**系列名****)**` 使全部标题正则失配 → 条目并入前条目吞并。
# 先于 _fix_quadruple_star 消费完整 4 星形态，归一为 elided 标准标题
# （镜像 _fix_elided_quadruple_title 产物：split 走 FC-1n，系列名进 feat_type）。
# `$` 行尾锚定防 MTT 文件正文形态（`…(****物品掌握专长) **你能用…`）误伤。
_RE_MASTERY_SERIES_PAREN = re.compile(
    r"^\*\*([^*\n]+?)\*\*\*\*\s*([A-Za-z][^*\n]*?)\s*\(\*\*\*\*([一-鿿][^*\n]*?)\*\*\*\*\)\s*\*\*$",
    re.M,
)

# ---- normalize：四星+半角括号截断（seed 11，elided 变体）----
# `**上下合围（战斗，团队）****(Combat,` → 闭合 + 残留括号落新行

# ---- normalize：索引行（seed 07，lb_marker）----
# `【PotW】抵异作成（造物）（Aligned Crafting）` → 标准标题 + fc/src 标记
# 组4 `[^）\n]` 排除全角 ）与换行（KN050 回归）：源数据 EN 括号是全角，
# 原 `[^)]` 只排除半角 ) → 组4 贪婪跨行吞掉后续全部列表行，仅首行标记。
# 组2 允许 `/`（制造波普宠/制造人偶）；尾 `【…】` 容错行尾多余来源标记
# （【3.5R】，3.5 规则来源由详情区 `**【3.5R】…**` 完整覆盖，索引行丢弃）。

# ---- normalize：无星标题包裹（elided）----
# B: `困于城中City-Locked(故事) 正文` → `**中文（English）〔类型〕**\n正文`
#    `锁链熟稔 Chain Mastery（战斗专长）`（永罪之书 FC-6）：中文与英文间允许
#    \s*（`\1` 后空格），英文名内部可含空格/连字符。
# C: `高等时髦法术 Greater Stylized Spell*****正文` → `**中文（English）**\n正文`
#    （中文名可含斜杠：`时髦/风格化魔法 Stylized Magic*****`）
# D: `**中文 English*****正文`（行首已有星，判别器 FC-8c，ISI 风格化法术）
#      → `[[fc:elided]]**中文（English）**\n正文`
# 组2 排除 `（(`（KN070）：`**中文（EN）****正文` 的组2 吞括号会产出
# `（（EN））` 双括号 → split 不识别（黄金军团 0 产出的直接根因）。
# 该形态由 _RE_BOLD_GLUE_SPLIT 先行拆行，D 分支只处理 EN 无括号形态。
# 组1 后 `\s+`（KN090 收口）：`**中文****EN`（无空格紧邻，page_311 详细条目
# 块）组1 贪婪吃全中文后组2 非贪婪吞尾字配 `\*{4,}` → name 截断
# （情感导体→情感导）；要求空格后紧邻形态整体失配，转交
# _RE_ELIDED_CN_EN_GLUE（无空格 elided 规则，见 _wrap_bare_titles）。
# 无空格紧邻 elided：`**中文****EN`（HTML 相邻加粗段粘连，page_311 详细条目
# 块 3 处）→ `[[fc:elided]]**中文（EN）**`。EN 以字母开头、限英文名常见
# 字符、行尾锚定——防 `**中文****EN，中文续句`/`**中文****EN正文` 误吞。
# E: `**中文（EN）****　　*描述*` 同行 elided（KN053，任务与战役_专长）：
#    闭合星内标题 + 4 星 + 同行单星描述 → 拆行 elided 标题 + 描述。
#    组1 以 `）` 结尾锚定 EN 带括号（D 分支输入 EN 无括号，天然不匹配；
#    6 星包裹形态 `****X****` 由 _RE_QUAD_STAR 先行归一）。
# A: `雕像伙伴(Companion Figurine) 正文` → `**中文（English）**\n正文`
# R5：行首负向前瞻排除正文句（"当你通过魔族仪典（Fiendish Obedience ）专长获得…"），
# 真条目标题不以连词/动词短语开头（seed 29 negative）。

# ---- A 分支正文句守卫（2026-08-02 空 text chunk 调查）----
# 召唤列表行 `中文(English,阵营)` 的英文名以逗号+阵营缩写结尾（生物,NG/CG/LG…
# 集合仅 9 种阵营）。专长英文名不含此形态（物品变体 `Ioun Stone, Thorny` 逗号
# 后是 Title Case 完整词、招式类型 `,Ex` 不在集合）→ 零误伤（全库 27 处命中
# 全部为纯洁勇士召唤善良怪物列表）。

# ---- normalize：whitespace 括号前空格（seed 10）----
# `**密集阻击** (Barrage of Styles，战斗，团队 ) 出处` → 标准标题 + fc 标记。
# 要求 `**` 后至少一个空格，避免误伤标准 `**X（Y）**`。
# KN084：能力标记（`（Su）/（Ex）/（Sp）`）跨行并入后由 FC-1q 分支的
# _ABILITY_MARKS 过滤（不进 feat_type、前置正文）——不在此排除，保持
# whitespace 簇形态流（MTT 天赋条目「标题 + 空行 + （Su）正文」若变
# standard 会撞「子节标题排除」过滤被整条误删）。

# ---- normalize：字段残缺形态修复（先归一后拆行）----
# 1) 右星残缺：`**坚忍**效果：**` → `**坚忍**\n**效果：**`（值闭合后裸标签+右星）
#    负向保证：`**先决条件：**` 等已包裹形态不二次包裹（需紧邻 `**值**` 前缀）。
# 2) 左星残缺拆行：`。先决条件**：` → `。\n**先决条件**：`。
#    前非星/换行/中文——中文排除防子串起点（`先决条件**：` 从"决"开始误配）；
#    `　`（U+3000）同样排除——`**　专长效果**：`（page_553 全角空格前缀
#    字段）已包裹形态，拆行会残留 `**　` 垃圾行（KN090 风暴洗礼）。
# 3) 左星残缺行首归一：`\n先决条件**：` → `\n**先决条件**：`（不拆行）
# 4) 已包裹字段非行首 → 拆行：`**标签：**` 形态（seed 04 拆行产物防御）
# 5) 已包裹字段非行首 → 拆行：`**标签**：` 形态（seed 12 专长效果）

# 6) 句末标点后裸标签 → 拆行（seed 08 先决条件/即时收益/专长目标同行紧贴）。
#    仅限句末标点之后（标签在散文句中段时保持原样，防误拆）。
_LABELS_ALT = "|".join(re.escape(l) for l in FEAT_ALL_FIELD_LABELS)
_RE_FIELD_SPLIT_BARE = re.compile(rf"([。！？])(?=[^。！？\n]{{0,6}}(?:{_LABELS_ALT})[：:])")

# ---- split：表格行（FC-T 索引，lb_marker）----
# 首格须含英文名（≥3 字母），防非专长表（追随者修正表等）与分隔行误识别。








# KN075：正文参考链接（`[锚文本](httpURL)` 等，URL 为论坛帖/官网参考指向）。
# 防误伤：PFS 图片 `![[图片]](path)` 的 path 非 http 开头，天然不匹配。
# 锚=URL 的链接带星壳形态：`**[URL](URL) [URL](URL)**`（page_553 章首）与
# `[URL](URL)　****[URL](URL)`（page_195 链接行，`　****` 是链接2 的前缀星壳）
# ——星壳只吃「紧邻链接」的星（无空格），跨空格/全角空格不吃，防链接间
# 空隙星被贪婪消费而残留打开星污染后续标题行（page_195 回归根因）。




# 整行星号散文（seed 55）：`******当你使用一件穿刺…窘境*********`（6+9 星包裹
# 散文句）须整行剥离——若只剥 4 星，残留星（`**…*****`）会重组成 `**…**` 标题。






def _fix_mastery_series_paren(text: str) -> str:
    """半角括号 4 星包裹系列名标题 → elided 标准标题（KN081）。

    `**能力掌握**** ability Mastery(****物品掌握专长****)**`
      → `[[fc:elided]]**能力掌握（ability Mastery）〔物品掌握专长〕**`
    （镜像 _fix_elided_quadruple_title 产物，全库仅 page_566 3 处命中。）
    """
    return _RE_MASTERY_SERIES_PAREN.sub(r"[[fc:elided]]**\1（\2）〔\3〕**", text)




# KN083：`**中文[：:]\*{0,2}英文\*{2,}**` 冒号标题粘连（page_529/530 索引表格
# 后正文区，`<B>中文</B>：<B>English</B>` 相邻加粗段转换残留 + 4 星粘连）。
# `_fix_quadruple_star` 剥 `****X****` 后残留形态：
#   `**奥法陷阱压制者：**ARCANE TRAP SUPPRESSOR****`（全角冒号+尾 4 星）
#   `**淡化身形:**Dampen Presence**：****`（半角冒号+英文闭合星+字段开星残留）
# `\*{0,4}` 容残留星（2 星 `**中文：**X****` 与 4 星开头 `**中文：****X**`——
# page_530 跨行英文合并后是 4 星开头+2 星尾形态，`_RE_QUAD_STAR` 4 星尾不
# 匹配剥不动，须 A 直接吃 4 星）；`\*{2,}` 贪婪吃英文后全部星、
# `(?:[：:]\*{0,2})?` 吃字段开星残留——替换后标准 FC-1n 标题。字段标签形态
# （值同行无英文）不匹配，由 `_RE_LABEL_TRAILING_STAR` 剥星保留字段行。
# 字段标签闭合星后残留星剥除：`**特殊情况：**** **值` → `**特殊情况：**值`。
# 仅剥「标签闭合后紧跟 2+ 星」（`**标签：**` + 值以星开头/粘连残留），
# 正常字段行（`**先决条件：**可以…`）标签后无星天然不匹配。




# page_197 红色多段加粗标题（HTML 相邻 `<B>` 段逐段星壳转换产物）：
# `**中文（****EN****）****〔****类型〕******` → _RE_NESTED_STAR 吃「（）」段、
# _RE_BOLD_GLUE_SPLIT 把 `）****〔` 拆行 → 残留独立行 `**〔**类型〕****` 在
# 标题行后（KN 巡检：41 chunks text 以 `**〔**` 开头且 feat_type 丢失）。
# 合并回标题行 → `**中文（EN）〔类型〕**` 走标准标题解析。
# 守卫：组2 后必须有星壳闭合（`〔注〕正文` 等非星尾不匹配）；组1 为整行闭合标题。












# ---- P0a：裸/星外中文类型括号标题（专长57 秘语、专长13 违和感）----
# `秘语（团队专长）` / `**违和感**（动物伙伴专长)` ——无星或星外中文类型
# 括号（非英文名）→ 包裹为 **中文（类型）** 走 FC-1n（_split_paren_content
# 纯中文段 → 类型标签）。守卫 = normalize 表 key + 动物伙伴专长：正文碎片
# 行（`震慑1轮（强韧）`）括号不在守卫集，天然豁免（全库 1567 裸括号短行
# 仅 8 处命中守卫，全部真实标题）。
_FEAT_TYPE_GUARD = "|".join(
    re.escape(x)
    for x in sorted(set(FEAT_TYPE_NORMALIZE) | {"动物伙伴专长"}, key=lambda s: (-len(s), s))
)
_RE_BARE_CN_TYPE_PAREN = re.compile(
    rf"^(\*{{0,2}})([一-鿿][^*\n]{{0,14}}?)(\*{{0,2}})[（(]({_FEAT_TYPE_GUARD})[)）]$",
    re.MULTILINE,
)






# KN090：星壳残留链尾收口（page_203 红色多段加粗标题 + 斜体正文段转换产物）。
# 残留形态（归一目标 `*正文*` 斜体标准形态，对齐 page_1564 详述区）：
# 1) 行首星壳（HTML `<I>` 空段+正文段拼接、`<I>` 段内嵌 `<B>` 加粗转换产物）：
#    `*  **正文** *` / `*   **正文*` / `*  ****正文*****` / `***  ****正文*****`
#    → BOL/EOL 剥两端壳为 `*正文*`（EOL 需两段星——`*正文*` 单段闭星不匹配）。
# 2) 半对称开星（`<B><I>` 粗斜体段 normalize 削星残留）：`****正文***`（4开3闭）
#    → `*正文*`；`***正文*`（3开1闭）同族。
# 3) 独立纯星行（1~6 星，可含水平空白/缩进）：normalize 拆出（`（战斗，流派
#    专长）****` 行尾 4 星经 whitespace 簇重组残留）或源数据自带（水下冒险旧
#    格式断行残留、`    ****` 缩进行 page_536、`**　` 全角空格残留、`*** ***`
#    page_529 炫富字段前）→ 删除（无信息量，非标题/正文/字段）。
# 4) PFS 图片行尾壳：`![[图片]](httpURL)**` → `[[PFS]]**` 残留行（`[[PFS]]`
#    前缀使纯星行正则行首锚定失配，split 消费标记后 `**` 漏进 text）→ 删除。
# 守卫：
# - `**正文**`（999 合法加粗）与 `***正文***`（78 合法粗斜体）星对称无空白，
#   BOL 需星后水平空白、EOL 需两段星，均不匹配，天然免疫；
# - QUAD_OPEN 要求 4+ 开星——3开3闭合法粗斜体不匹配；内容组全非星
#   （`[^*\n]+?`），且 `\*{0,9}` 后必须行尾——`****正文****——**长剑…`
#   破折号族（DASH 规则先行消费）、`****正文。**尾` 均不匹配，安全保留。
# - 行首规则均带 `[ \t　]*` 缩进容忍：源数据术语条目残留（page_556 剧毒法术
#   `  * **正文*` 缩进 2 空格）会逃逸无缩进锚定，split 剥缩进后壳残留进 text。
# 行尾壳两形态：A) 星+空白+星（`** *` / `*** ***`）；B) ≥4 连星（`*****`）。
# 守卫：`**`（合法标题闭星）`\*{1,4}` 贪婪吃 2 星后无可回溯成两段 1 星
# ——A 需强制空白、B 需 4 连星，`**`/`***`（合法粗斜体闭星）均不匹配。
# 半对称开星：`****正文***`（4开3闭）/ `*****正文*`（5开1闭）/ `****正文。`（4开0闭）。
# 闭星放宽 0-9：HTML `<B><I>` 粗斜体段 normalize 削星后闭星残缺到 0（page_54
# 冒烟巨石 4开0闭行尾截断）；守卫——`\*{0,9}` 后必须行尾，纯星行（组1 为空）
# 不匹配（BLANK_STAR 负责），`**`/`***` 行尾闭星不构成多星壳。
# 破折号族（page_321 拔群剑术/梦魇伤疤）：3 段 `<B><I>` 粗斜体拼接
# （段1 + `——` 段 + 段2）→ normalize 链前部 `****A****` 已还原 2 星，
# 链尾收到 `**A**——**B`（段2 闭星残 0，段1 闭星在 `——` 前）。
# 语义为整句斜体 → `*A——B*` 一段归一（`——` 内嵌，对齐 HTML 全文斜体原意）。
# 守卫：组2 `[^*\n]+?` 后必须直接行尾——`**A**——**B**`（B 有闭星，
# 合法并列加粗）不匹配；`*A*——*B*`（1星斜体并列）开星不匹配。
# 1开N闭斜体尾壳（`*正文***` / `*正文**`，page_203 击昏拳/奥多里剑术详述段）：
# `<I>` 斜体段 normalize 闭星未削净 → `*正文*`。
# 守卫：`***正文***`（3开3闭合法粗斜体）`^\*` 吃第 1 星后 `[^*\n]+?` 需
# 立即非星内容，第 2 星挡住不匹配；`*正文*`（1开1闭）`\*{2,}` 不匹配。
# 字段后 4 星壳（`**效果：****正文`，page_1367 超魔系 50 行）：相邻
# `<B>` 段（`效果：` 加粗段 + 正文段）拼接 → `**标签：**` 闭星与正文开星
# 粘连 `****` → `**标签：**正文`。守卫：正常字段 `**标签：**` 后无 4 星。
# 速查表删除线壳（KN090 收口）：HTML `<B><S>` 加粗删除线段转出
# `**~~中文（~~****~~EN~~****~~）〔类型〕~~****~~~~**`，`~~` 干扰 split 标题
# 判定 → 详细条目并入前条、该专长只剩 feat_index。`~{2,}` 剥壳恢复标准
# 标题形态（与 L455 致盲重击一致）；单 `~`（译者吐槽语气词等）不匹配。










# ---- P0b：行首裸标签包裹（`先决条件：值` → `**先决条件：**值`）----
# 源数据大量条目字段标签无加粗（专长44 缩进半角冒号、专长9 值内嵌加粗跨行），
# parse_fields 只认 **标签[：:]** 形态 → prerequisites=null 高发（抽查 22 文件
# fields_ok=false 中 14 例为此根因）。行首（允许前导空白）标签 ∈ 字段标签集 +
# 冒号（值非空或行尾空标签行）→ 包裹。引用块（>）、表格行（|）、列表（-）、
# 已带星（*）行首字符不在标签集，天然豁免；锚定行首，句中"先决条件："字样不
# 误包（拆行职责在 _split_inline_fields）。置于链尾：拆行完成后逐行包裹。
_RE_BARE_FIELD_LABEL = re.compile(
    rf"^([ \t　]*)((?:{_FIELD_LABEL_ALT})[：:])(?=[ \t　]*\S|$)",
    re.MULTILINE,
)
# 句号分隔变体（专长12 等 3 处全库实测）：`先决条件。位面训导*，…`——句号
# 非 parse_fields 分隔符，包裹时同步转为冒号（值保留）。
_RE_BARE_FIELD_LABEL_PERIOD = re.compile(
    rf"^[ \t　]*((?:{_FIELD_LABEL_ALT}))[。．](?=[ \t　]*\S|$)",
    re.MULTILINE,
)






# `**标签**\n[引用块行\n]?：值` → `**标签**：值`（值行冒号前缀提回标签后）


# ---- R1：根目录 66 文件形态缺口（判别器 FC-4 变体/FC-1v/FC-1n 无闭合/FC-H/FC-8e/FC-1c）----
# 源数据整理把来源/正文/英文名同行拼在闭合星后，formats 标题正则要求行尾闭合星，
# 需先归一为可识别形态。判别器（fc_match.py）注释明确支持这些变体（FC-1n
# "闭合星后必须行尾或'出自'"、FC-1v "闭合星后括号英文"），formats 漏覆盖是
# R1 验收"根目录 est>0 文件 0 产出"的根因（M1~M7 逐项）。

# M2：`**中文**English Source…` 星外英文名 → `**中文 English**`（FC-3 形态）。
# 星内排除 'XX专长' 结尾的分类标题（判别器 FC7B lookbehind 同源，位面导师系列
# 专长等章节标题不转）；星外英文前瞻到 Source/出自/第N页 来源词或行尾防吞。
# 注意不可含 '书名 pg.' 分支——merge 把 `Focus\nSource` 并成一行后，pg. 分支
# 会让 group2 在 'Creature' 处误判来源成立（'Focus Source…pg.' 也是 pg. 结尾）。
# M1：闭合星后同行来源 → 拆行（'出自…第N页' / 'Source …pg' / '书名 …pg' 型）
# M3（FC-1v）：`**中文**（English）` 闭合星后括号英文 → `**中文（English）**`
# M4（FC-1n 无闭合星）：`**中文（English）` 行尾无闭合星（跨行英文已合并，
# 判别器"闭合星可缺"型）→ 补闭合星
# M5（FC-H）：`# 中文（English）` 井号条目标题 → 星包裹；文件标题
#（'（…）EMH 专长' 结尾）行尾非括号天然不匹配
# M6（FC-8e 裸中英行）：`中文English` 行首中文+星外英文短语到行尾（无星无括号）
# → elided 包裹；裸字段行（含中文冒号）、URL 行、** 开头天然不匹配
# M8（FC-4 变体）：`**中文（类型）** English` 星内类型闭合、星外英文名同行
# → `**中文（类型, English）**` 归一。类型括号须中文内容、星外英文到行尾。
# M10（FC-7c）：`中文行\n全大写英文行` → elided 标题（merge 已把跨行英文合并，
# 此处处理中文行+下一行英文名）
# M1b：`**中文(类型) English(English)**` 星内中文+半角类型括号+空格+英文名
# → FC-1n 单括号形态 `**中文（类型, English）**`。类型括号须为中文内容、
# 与英文名间至少一空格，防误伤已规范的双括号标题（FC-1r/FC-1q 括号紧邻）。
# 归一到单括号形态后 `_split_paren_content` 按逗号拆出 name_en 与类型。
# M7：闭合星+同行冒号（星内含括号的标题特征）→ 拆行
# M11a（FC-Hb 井号带类型+英文）：`## 中文（类型） English` → `**中文（English，类型）**`
# 天界/炼狱血脉（BoA/BoF）聚合文件的专长标题。限定 H2/H3（`#{2,3}`）——
# H1（`# 天界血脉 BoA 专长`）是文件标题非专长，防误包。类型括号须中文内容。
# M11b（FC-Hb 井号中文+英文）：`## 中文 English` → `**中文（English）**`
# M13a（FC-G/FC-1x 行首闭合星+粘连正文）：`**中文（English）**正文` / `**领导力（Leadership）***正文*`
# 标题星闭合后正文无换行粘连（page_950 斜体正文、贰牙击【战斗】型）→ 拆行让
# split 识别。行首锚定防正文内联加粗误拆；lookahead 排除：
#   换行（已是独立标题行）、冒号（字段标签 `**先决条件**：`）、
#   空格+英文（`**中文（类型）** English` 归 M8 处理，防重复拆行）。
# M13b（FC-3 星内中文+大写英文+闭合星后正文粘连）：`**中文 EN**正文` → 拆行
# 英文名须首字母大写（防 `**中文**：` 字段、防 `**专长效果**` 无英文形态）。






























def _is_magic_item(item: dict) -> bool:
    """价格+重量双字段 → 非专长（魔法物品），排除（seed 24）。

    造物专长只有"价格"（制造成本）没有"重量"，双字段同时出现可判定物品。
    """
    text = item.get("text", "")
    return "**价格：**" in text and "**重量：**" in text


class FeatFormat(BaseFormat):
    """专长格式解析：normalize 六形态归一 → promote 恒等 → split 条目切分。"""

    @property
    def category(self) -> str:
        return "feat"

    def promote(self, text: str) -> str:
        return text

    def _normalize_custom(self, text: str) -> str:
        # 删除线壳剥除放链最前：`~~` 是 HTML `<S>` 转换标记、PF 文本无语义，
        # 先剥恢复标准标题形态，后续标题归一规则（elided/quadruple/FC-1r 等）
        # 才能正确识别速查表条目（否则 `**~~` 开头干扰匹配，条目整条丢失）
        text = _RE_STRIKE_SHELL.sub("", text)
        text = _merge_cross_line_en(text)
        text = _merge_table_continuation(text)
        # 顺序要点：_mark_pfs 先行消费 `![[图片]](http…)` 整体（PFS 图片 URL
        # 是 aonprd http 链接），_strip_http_links 后置即天然不会误剥 PFS 标记
        text = _mark_pfs(text)
        text = _strip_http_links(text)  # KN075：正文参考链接剥离（URL 剥除留锚文本）
        # elided 四星标题先于通用 4→2：`English****（类型）*****` 的星需整体消费
        text = _fix_elided_quadruple_title(text)
        # KN081：半角括号 4 星包裹系列名（`EN(****系列名****)**`）同先于 4→2
        text = _fix_mastery_series_paren(text)
        text = _fix_quadruple_star(text)
        # page_197 红色多段加粗标题：`）****〔` 拆行后的独立〔〕类型段残留
        # （`**〔**战斗〕****`）合并回标题行，紧接拆行规则（_RE_BOLD_GLUE_SPLIT
        # 在 _fix_quadruple_star 内 L410），避免其被 _wrap_bare_titles 误包装
        text = _merge_type_seg_line(text)
        text = _fix_quad_star_halfparen(text)
        # KN083：`**中文：**English****` 冒号标题粘连（剥星后残留）→ FC-1n；
        # 字段标签剥星（`**特殊情况：****`）须在其后（英文形态已整体消费）
        text = _fix_colon_title_glue(text, _ALL_FIELD_LABELS)
        text = _fix_label_trailing_star(text)
        text = _wrap_index_line(text)
        text = _wrap_bare_titles(text, _ALL_FIELD_LABELS)
        text = _wrap_bare_cn_type_paren(text, _RE_BARE_CN_TYPE_PAREN)  # P0a：裸/星外中文类型括号标题（专长57/13）
        # R1 根目录形态缺口 M1~M13：源数据把来源/英文名/正文/井号标题拼在
        # 标题星内或星外同行，先归一为 split 可识别的标题形态（判别器
        # FC-1n 注释'闭合星后必须行尾或出自'同源佐证）。顺序要点：
        # M2 先于 M1a（`**中文**English Source` 需先并入英文名，M1a 才
        # 能识别闭合星后跟来源）；M13a/b 先于 M8（行首粘连正文先拆行，
        # M8 只吃 `**中文（类型）** English` 空格形态，防整行吞进英文名）；
        # M1b 后于 M1a（拆来源行后才独立成标题）；M11 随 M5 后（井号标题
        # 带类型+英文 / 中文+英文两种变体）。
        text = _fix_star_outside_en(text)          # M2：星外英文名并入星内
        text = _split_title_glue_paren(text)       # M13a：行首**中文（English）**粘连正文拆行
        text = _split_title_glue_cn_en(text)       # M13b：行首**中文 EN**粘连正文拆行
        text = _fix_star_outside_en_type(text)     # M8：**中文（类型）** English → 单括号
        text = _split_closed_title_source(text)    # M1a：闭合星+同行来源拆行
        text = _fix_spaced_parens_cn_en(text)      # M1b：中文(类型) English(English) → FC-1n
        text = _split_closed_title_colon(text)     # M7：闭合星+同行冒号拆行
        text = _fix_fc1v_paren_en(text)            # M3：**中文**（English）→ FC-1n
        text = _fix_fc1n_no_closing_star(text)     # M4：补闭合星
        text = _wrap_hash_titles(text)             # M5：井号标题转星
        text = _wrap_hash_titles_type_en(text)     # M11a：## 中文（类型） English → 单括号
        text = _wrap_hash_titles_cn_en(text)       # M11b：## 中文 English → **中文（English）**
        text = _wrap_bare_cn_en_lines(text)        # M6/M9：裸中英行 elided 包裹
        text = _wrap_bare_cn_en_allcaps(text)      # M10：中文行+全大写英文行
        text = _normalize_whitespace_title(text)
        text = _fix_field_star_right(text)
        text = _fix_field_star_left(text)
        text = _fix_bare_label_colon_nextline(text)  # R2：`**标签**\n：值` → `**标签**：值`
        text = _split_inline_fields(text, _RE_FIELD_SPLIT_BARE)
        text = _wrap_bare_field_labels(text, _RE_BARE_FIELD_LABEL, _RE_BARE_FIELD_LABEL_PERIOD)  # P0b：行首裸标签 → **标签：**（拆行后逐行包裹）
        # KN090：星壳残留收口须在全部标题/字段归一之后（独立纯星行删除 +
        # 行首脏星壳正文归一 `*正文*`），此前任何规则都不再产生新星壳
        text = _fix_star_shell_remnants(text)
        return text

    def _make_item(self, m: re.Match) -> dict:
        name = m.group(1).strip()
        name_en, types = _split_paren_content(m.group(2), split_feat_types)
        tail = m.group(3)
        if tail:
            types.extend(split_feat_types(tail.strip("〔［【〕］】")))
        return self._make_item_from_parts(name, name_en, types)

    def _make_item_from_parts(self, name: str, name_en: str, feat_types: list[str]) -> dict:
        """由 (中文名, 英文名, 类型列表) 构造条目（R4 AG 形态共用构造）。"""
        seen: set[str] = set()
        dedup: list[str] = []
        for t in feat_types:
            if t not in seen:
                seen.add(t)
                dedup.append(t)
        return {
            "name": name,
            "name_en": name_en,
            "feat_type": dedup,
            "format_cluster": "standard",
            "pfs_eligible": False,
            "source": "",
            "text": "",
        }

    def _open_item(self, items: list[dict], item: dict,
                   pending_fc, pending_src, pending_pfs,
                   inline_img: bool = False) -> tuple:
        """消费待定标记（fc/src/PFS）→ 提交条目 → 返回更新后的待定标记。

        R9 img_marker：行首 PFS 图片前缀与条目名同行内联（`[[PFS]]**酒后真言
        （Truth in Wine）**`，format_clusters 规范 §一 #4）时，条目形态标记为
        img_marker 而非 standard；图片独立行（seed_00）不触发（inline_img=False）。
        pending_fc 优先（显式形态标记 > 图片前缀推断）。"""
        if pending_fc is not None:
            item["format_cluster"] = pending_fc
            pending_fc = None
        elif inline_img and item.get("format_cluster") == "standard":
            item["format_cluster"] = "img_marker"
        if pending_src is not None:
            item["source"] = pending_src
            pending_src = None
        if pending_pfs is not None:
            item["pfs_eligible"] = pending_pfs
            pending_pfs = None
        items.append(item)
        return pending_fc, pending_src, pending_pfs

    def _parse_table_row(self, line: str) -> dict | None:
        """FC-T 表格行 → 索引条目；非专长表/分隔行 → None。

        条目判定：首格含英文名（≥3 字母）。EN/CN 同行配对提取（Brewmaster 酿造大师
        → name=酿造大师, name_en=Brewmaster）；纯 EN 行（False Casting）以 EN 为名。
        """
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            return None
        first = cells[0]
        if not re.search(r"[A-Za-z]{3,}", first):
            return None
        if re.fullmatch(r"[\s:\-—–~]+", first):
            return None
        m_en = _RE_TABLE_EN.search(first)
        m_cn = _RE_TABLE_CN.search(first)
        en = m_en.group(1).strip() if m_en else ""
        cn = m_cn.group(1) if m_cn else ""
        name = cn or en
        text = "；".join(c for c in cells[1:] if c)
        return {
            "name": name,
            "name_en": en,
            "feat_type": [],
            "format_cluster": "lb_marker",
            "pfs_eligible": False,
            "source": "",
            "text": text + "\n",
        }

    def split_into_items(
        self, text: str, *, source_name: Optional[str] = None
    ) -> list[dict]:
        """按标题/标记切分条目。

        - `[[fc:xxx]]`/`[[src:xxx]]`/`[[PFS]]` 行内标记：消费并写入当前/下一条目
        - 标题行（`**中文（English）〔类型〕**`）开新条目
        - 表格行（lb_marker）开索引条目
        - 有星无括号短行（分节标题）跳过；其余行并入当前条目 text
        - 价格+重量双字段条目（魔法物品）过滤
        """
        items: list[dict] = []
        cur: dict | None = None
        pending_fc: str | None = None
        pending_src: str | None = None
        pending_pfs: bool | None = None
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            line = line.strip()
            inline_img = False
            while True:
                if line.startswith("[[fc:"):
                    pending_fc = line[5:line.index("]]")]
                    line = line[line.index("]]") + 2 :].strip()
                elif line.startswith("[[src:"):
                    pending_src = line[6:line.index("]]")]
                    line = line[line.index("]]") + 2 :].strip()
                elif line.startswith("[[PFS]]"):
                    pending_pfs = True
                    line = line[len("[[PFS]]") :].strip()
                    if line:
                        # R9：图片前缀与条目名同行内联 → img_marker 候选
                        # （`[[PFS]]**酒后真言（Truth in Wine）**`）；图片独立行
                        # 时 remainder 为空，不置位（seed_00 保持 standard）
                        inline_img = True
                elif line.startswith("[[PFSN]]"):
                    pending_pfs = False
                    line = line[len("[[PFSN]]") :].strip()
                else:
                    break
            if not line:
                continue
            # 标题识别：双括号形态先于单括号——FC-1n（**中文（English）**）的
            # `\1` 非贪婪回溯会把第一个括号对吞进 name，必须让更特定的
            # FC-1r（**中文（类型）（English）**）/ FC-1q（**中文（EN）（类型）**）
            # 先判定（致命之角：`（战斗专长）（Deadly Horns）` 曾产 name 带括号）。
            # 顺序：FC-1r → FC-1q → FC-1n → FC-4（中文（类型）English）→ FC-3（中文 English）
            m = _RE_TITLE_CN_TYPE_EN.match(line)
            if m:
                # KN084：MA 页 M8（_fix_star_outside_en_type）把跨行裸英文名并进
                # 类型括号（`**诅咒巫术（神话, Accursed Hex ）（Mythic）**`），
                # 英文段才是真名，group(3) 只是英文类型（Mythic）——英文段优先；
                # 纯中文类型括号（致命之角）行为不变
                en_in_type, types = _split_paren_content(m.group(2), split_feat_types)
                en = en_in_type or m.group(3).strip()
                item = self._make_item_from_parts(m.group(1).strip(), en, types)
                pending_fc, pending_src, pending_pfs = self._open_item(
                    items, item, pending_fc, pending_src, pending_pfs, inline_img
                )
                cur = item
                continue
            m = _RE_TITLE_EN_TYPE.match(line)
            if m:
                en, en_type = m.group(2).strip(), m.group(3).strip()
                # KN084：能力标记（Ex/Su/Sp，Extraordinary/Supernatural/
                # Spell-like）不是专长类型——进阶武器训练/盗贼天赋条目
                # `**武艺无尽（Abundant Tactics）（Ex）**` 的（Ex）是能力
                # 类型，丢之失检索信息，保留在正文首行
                if en_type in _ABILITY_MARKS:
                    item = self._make_item_from_parts(m.group(1).strip(), en, [])
                    item["text"] = f"（{en_type}）\n"
                else:
                    name = m.group(1).strip()
                    # KN084：三括号形态 `**中文（类型）（EN）〔**TYPE**〕**`
                    # （page_505 BBS 帖 HTML 转换产物，组3 带星壳）——组1 非贪婪
                    # 会吞下 `（战斗）` 中文类型括号（`圣水攻袭（战斗）`），星壳
                    # 英文类型与中文类型同义（速查表列「战斗」）——中文括号拆出为
                    # 类型、星壳英文类型丢弃，避免英文再入 feat_type
                    m_cn = _RE_NAME_TRAILING_CN_TYPE.match(name)
                    if m_cn:
                        name = m_cn.group(1).strip()
                        types = [m_cn.group(2).strip()]
                    else:
                        types = split_feat_types(en_type.strip("*"))
                    item = self._make_item_from_parts(name, en, types)
                pending_fc, pending_src, pending_pfs = self._open_item(
                    items, item, pending_fc, pending_src, pending_pfs, inline_img
                )
                cur = item
                continue
            # FC-4 先于 FC-1n（P0a page_820）：`**中文（类型）EN (EN_TYPE)**`
            # 英文名带括号时 _RE_TITLE 的非贪婪回溯会把整串吞进 name 且类型
            # 不进 feat_type；FC-4 只吃「类型括号后跟英文」，纯括号形态天然
            # 不匹配，提前不抢占既有 FC-1n 命中。
            m = _RE_TITLE_TYPE_EN.match(line)
            if m:
                item = self._make_item_from_parts(
                    m.group(1).strip(), m.group(3).strip(), split_feat_types(m.group(2))
                )
                pending_fc, pending_src, pending_pfs = self._open_item(
                    items, item, pending_fc, pending_src, pending_pfs, inline_img
                )
                cur = item
                continue
            m = _RE_TITLE.match(line)
            if m:
                item = self._make_item(m)
                pending_fc, pending_src, pending_pfs = self._open_item(
                    items, item, pending_fc, pending_src, pending_pfs, inline_img
                )
                cur = item
                continue
            m = _RE_TITLE_CN_EN.match(line)
            if m:
                item = self._make_item_from_parts(m.group(1).strip(), m.group(2).strip(), [])
                pending_fc, pending_src, pending_pfs = self._open_item(
                    items, item, pending_fc, pending_src, pending_pfs, inline_img
                )
                cur = item
                continue
            # R2：字段标签独立行（先决条件：/专长效果：等）→ 并入当前条目 text，
            # 不产新条目（先于 section header 判定，避免被当分节标题跳过）
            m = _RE_FIELD_LABEL_COLON.match(line)
            if m and m.group(1) in _ALL_FIELD_LABELS:
                if cur is not None:
                    cur["text"] += line + "\n"
                continue
            m = _RE_FIELD_LABEL_BARE.match(line)
            if m and m.group(1) in _ALL_FIELD_LABELS:
                if cur is not None:
                    cur["text"] += line + "\n"
                continue
            # R3：punct 标题（**中文：** 独立行，中文不在字段标签/强调词集）→ 条目
            m = _RE_PUNCT_TITLE.match(line)
            if m and m.group(1) not in _ALL_FIELD_LABELS and m.group(1) not in _NON_TITLE_EMPHASIS:
                item = self._make_item_from_parts(m.group(1), "", [])
                item["format_cluster"] = "punct"
                pending_fc, pending_src, pending_pfs = self._open_item(
                    items, item, pending_fc, pending_src, pending_pfs, inline_img
                )
                cur = item
                continue
            # FC-8n：裸中文条目标题（page_744 痛苦选项型）。`**截肢**` 独立
            # 闭合行 + 后行单星 `*描述*` 佐证 → 条目；无佐证（分节标题如
            # `**半鱼人专长**`）维持跳过（seed_22）。先于 _RE_SECTION_HEADER。
            # KN082：佐证扩展——同行条目源数据拆行后（`**算术占卜**` 独立行 +
            # 描述段落 + `**先决条件：**` 字段行，page_744 数学魔法节），后续
            # 8 行内出现字段标签行（`**标签[：:]**` 前缀）同样佐证条目身份
            # （判别器 FC-8q「需字段标签佐证」同思路）；章节标题后跟纯段落
            # 无字段标签 → 保持跳过。扫描中先遇子条目标题行（`**异怪克星
            # 施法者（…）**` 等，专长58 半鱼人专长型）→ 当前为小节标题，
            # 立即终止不得跨子条目误佐证。
            m = _RE_FIELD_LABEL_BARE.match(line)
            if m and m.group(1) not in _ALL_FIELD_LABELS:
                nxt = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
                field_corroborated = False
                for j in range(idx + 1, min(idx + 9, len(lines))):
                    ln2 = lines[j].strip()
                    if not ln2:
                        continue
                    if _RE_FIELD_LABEL_PREFIX.match(ln2):
                        field_corroborated = True
                        break
                    if (
                        _RE_TITLE_CN_TYPE_EN.match(ln2)
                        or _RE_TITLE_EN_TYPE.match(ln2)
                        or _RE_TITLE_TYPE_EN.match(ln2)
                        or _RE_TITLE.match(ln2)
                        or _RE_TITLE_CN_EN.match(ln2)
                    ):
                        break  # 先遇子条目标题 → 当前是小节标题
                if _RE_ITALIC_DESC.match(nxt) or field_corroborated:
                    item = self._make_item_from_parts(m.group(1), "", [])
                    pending_fc, pending_src, pending_pfs = self._open_item(
                        items, item, pending_fc, pending_src, pending_pfs, inline_img
                    )
                    cur = item
                    continue
            if _RE_SECTION_HEADER.match(line):
                continue
            if line.startswith("|"):
                row = self._parse_table_row(line)
                if row:
                    if pending_pfs is not None:
                        row["pfs_eligible"] = pending_pfs
                        pending_pfs = None
                    items.append(row)
                    cur = row
                continue
            if cur is not None:
                cur["text"] += line + "\n"
        items = [it for it in items if not _is_magic_item(it)]
        for it in items:
            it.setdefault("format_cluster", "standard")
            # KN094（feat_intro）：介绍性 chunk 打 intro 标记——空 text 章首标题
            # （23 个，如《核心规则手册》专长）或 title 以「专长」结尾且无字段标签
            # 的类别介绍段（34 个，如团队专长/超魔专长）。lb_marker 表格行跳过
            # （feat_index 优先，KN085 28 个空 text 不误伤）；带字段标签的「X专长」
            # 多条目拼组（4 个，如新流派专长后跟先决条件）是具体条目形态，不打标。
            # KN109：intro 判定前置到子节排除之前——intro 豁免过滤，否则类别规则
            # 节（page_622 神话专长/神话和超魔专长，text>150 无字段标签）被误杀，
            # 真实规则正文丢失。
            if it.get("format_cluster") != "lb_marker":
                text = it.get("text", "")
                if not text.strip() or (
                    it.get("name", "").rstrip().endswith("专长")
                    and not _RE_FIELD_IN_TEXT.search(text)
                ):
                    it["intro"] = True
        # 子节标题排除（判别器 FC-1n/FC-3 佐证同源）：闭合标题（standard）条目
        # text 较长却无任何真字段标签 → 纯描述节（永罪"灵魂的价值/特色"型规则
        # 小节，判别器 10 行窗口佐证也排除）。len>150 语义 ≈ 判别器"字段标签若
        # 存在应紧跟标题"（窗口约 10 行）；短 text（seed 片段等测试输入）信息
        # 不足，保守保留。punct/elided/lb_marker 等形态不受影响。
        # KN084：能力标记分支的 standard 条目（text 以 `（Ex）/（Su）/（Sp）`
        # 行首开头）直接保留——标记前缀 5 字符可把 text 147→152 顶过 150 阈值
        # （WMH 庖丁解牛回归）；纯描述子节（seed 33"特色（Flavor）"）是 FC-1n
        # 形态，text 无标记前缀，不受守卫影响。
        # KN109：intro 豁免（类别规则节）+ 模板词弹掉（描述格式模板节，见
        # _TEMPLATE_SECTION_WORDS）。intro 前置已验证矩阵内既有产出零影响
        # （全库命中仅武器大师手册 1 条且本已保留）。模板词弹掉独立过滤——
        # 模板节 text 通常 <150（先决条件 110 字符等），放保留链会被 len 分支
        # 覆盖；独立过滤保证弹掉优先。
        items = [
            it for it in items
            if it.get("intro")
            or it.get("format_cluster") != "standard"
            or len(it.get("text", "")) <= 150
            or _RE_FIELD_IN_TEXT.search(it.get("text", ""))
            or _RE_ABILITY_MARK_LEAD.search(it.get("text", ""))
        ]
        items = [
            it for it in items
            if not (
                it.get("format_cluster") == "standard"
                and it.get("name", "").rstrip() in _TEMPLATE_SECTION_WORDS
            )
        ]
        return items
