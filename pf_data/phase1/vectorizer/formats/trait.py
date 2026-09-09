"""
formats/trait.py — 背景特性格式解析器（TDD 驱动）

设计输入：docs/背景特性/format_clusters_规范与偏差对账.md（15 簇 4 族）
参照：formats/feat.py（FeatFormat 模板）+ formats/normalize_common.py（公共链）

形态总览（split 判定链）：
- 星壳标题 `**中文（EN）【书】**：`（A 族四壳归一后）/ `**中文（EN）**`（PotR 型）
- 半星壳 `**中文**(EN) 出自《…》`（EOD/任务与战役）
- H2 `## 中文名（EN）`（B2，三重标题合并）
- 流式裸名 `中文EN（括号）：正文`（B3 ISG/ACO/P&P 归一后形态，括号=deity/类型）
- 表格行（背景特性17 星座表：d% | 星座 | 日期 | 效果）
- 缺陷条目 `**效果：**` 无标题开头（C_flaw）

normalize 链复用 normalize_common 公共函数 + 4 个 trait 专属步骤
（裸英文跨行 / 出自行页码跨行 / EOD 断行字段标签分裂 / StLC 字段标签内星壳）。
"""

import re

from .base import BaseFormat
from .normalize_common import (
    _RE_STRIKE_SHELL,
    _fix_elided_quadruple_title,
    _fix_field_star_left,
    _fix_field_star_right,
    _fix_label_trailing_star,
    _fix_quad_star_halfparen,
    _fix_quadruple_star,
    _fix_star_shell_remnants,
    _merge_cross_line_en,
    _normalize_whitespace_title,
    _split_closed_title_source,
    _strip_http_links,
)

# ---------------------------------------------------------------------------
# trait 专属 normalize 步骤
# ---------------------------------------------------------------------------

# 裸英文名跨行合并（无星壳包裹）：`Erutaki Sky \nReader（` / `炼金销赃者 \nAlchemical`
# 英文词尾含撇号星壳分裂（`Lion’s \nAudacity`）；全局 sub 一次消费两行，跑两次覆盖三行。
# 约束：行首必须是字母（续行以字母开头），避免吞中文正文。
_RE_BARE_EN_JOIN = re.compile(
    r"([A-Za-z’'][A-Za-z ’'’-]{0,40})\n([A-Za-z][A-Za-z ’'’-]{0,40})"
)

# 出自行页码跨行：`pg. \n10》`（_RE_CROSS_EN 行尾要求字母，`.` 不匹配故单独处理）
_RE_SOURCE_PAGE_JOIN = re.compile(r"(pg\.)[ \t]*\n[ \t]*(\d+)")

# 引导句星壳+条目同行拆行（BotA 六段）：`**以下…角色****自然主义者 Naturalist（亚马萨）**：正文`
# ——引导句闭合星与条目开星 4 星连续，拆行后条目走标准标题分支。
# 约束：组1 ≥6 字（防短标题误拆）；组1 无括号（防误拆「标题+种族+神名」同行形态，
# 如 `**背刺者（Backstabber）【HoG】****[半身人]（Thamir Gixx）**：`——此类由
# _RE_POST_DEITY 同行并回，拆行反而断链）；前瞻条目星壳含括号（防拆到正文）。
# 组1 容括号（BotA 引导句 `**以下…（The Flooded Cathedral）中。**`——星壳内
# 书名括号，排除 `（` 会提前截断）且容换行（`（The \nFlooded Cathedral）`
# 跨行书名括号——组1 `[^*]` 允许 `\n`，上限 120 防跨行吸收正文）；
# 前瞻容换行（`**条目名 EN \nEN2（类型）**` 跨行英文名——`[^*\n]` 在换行处
# 终止导致前瞻失败，BotA 吉斯塔克学者/劳有所得）；
# `(?<!】)` 负向后瞻：闭星前是 `】` = 后置神祇括号形态
#（`**A（EN）【书】****[半身人]（神祇）**：`，seed33 背刺者）——引导句以中文
# 结尾，`】` 结尾是【书】标签证据，不拆留给 _RE_POST_DEITY 并入。
_RE_INTRO_GLUE_STAR = re.compile(r"(\*\*[^*]{6,120}?(?<!】)\*\*)\*\*(?=[^*]{1,64}?[（(])")

# 四壳断裂+书缩写同行（page_154 秘文会）：`**A****（****EN****）**【书】**：`
# ——_fix_quadruple_star 剥 `****EN****` 后残留 `**A****（**EN**）**`，
# 4 星+括号被 _fix_quad_star_halfparen 误拆，此步先把 `**A****（B）**` 并回 `**A（B）**`
#（须在 _fix_quad_star_halfparen 之前执行；组2 容 `（**EN**）` 内星壳残留一并剥皮）
_RE_QUAD_GLUE_TITLE = re.compile(
    r"\*\*([^*\n（(]{1,24}?)\*\*\*\*[（(](?:\*\*)?([^*\n]{1,40}?)(?:\*\*)?[）)]"
)

# 括号内英文名残星+逗号（page_157 圣娼姬）：`（Calistrian Divine Courtesan**，`
# ——_fix_quadruple_star 剥 `****，混乱中立）【APG】****` 时组1 内残留闭合星，
# 清理 `**` + 全/半角逗号（限定括号内防 `**EN**，` 正常形态误伤）
_RE_EN_TRAIL_STAR_COMMA = re.compile(r"[（(]([A-Za-z][A-Za-z ’'’-]{1,40})\*\*([，,])")

# 括号内 EN 星壳+中文地点星壳断裂（page_156 HoG 段 7 条，est 35 got 27 缺口
# P1）：`**好养活（Cheap to Feed****，****奥斯里昂，瓦瑞希安）【HoG】**：`
# ——EN 星壳与中文地点星壳间 `****，****` 残壳使 _RE_TITLE_STAR 组3（排除
# `*`）失配整条目丢失（_RE_EN_TRAIL_STAR_COMMA 只剥 2 星+逗号，`\*\*` 吃 2 星
# 后组2 前仍顶 2 星回溯失败）。剥 2-4 星归一 → 标准 `（EN，中文地点）`
_RE_EN_STAR_CN_PLACE = re.compile(
    r"[（(]([A-Za-z][A-Za-z ’'’-]{1,40})\*{2,4}[，,]\*{2,4}([一-鿿][^（）()\n]{1,30})[）)]"
)

# 行尾【书】+残星（page_156 猎魔人 1 条，同缺口 P1）：`**中文（EN，地点）**
# 【书】****` ——源 `****【CEoD】******` 经公共层四星归一后残尾 4 星形态
# `）**【书】****`（括号后闭星 + 尾 4 星），_RE_OUTER_BOOK_GLUE 要求冒号不
# 处理、_RE_TITLE_STAR 组5 无法越过夹星 → 整条目丢失（尾星由 643 行
# _fix_star_shell_remnants 剥至单星，须在本正则之前）。组1 中文名+括号、
# 组2 壳外【书】、尾星 `\*{2,}$` 剥残星 → 组5 壳内形态
# `**中文（EN）【书】**`（对齐 _RE_OUTER_BOOK_GLUE 同目标形态；壳外无冒号
# 行尾 `）**【书】**` 2 星形态同转壳内幂等——`】` 后 ≥2 星行尾全库仅此
# 1 形态，`】**：`/`】**` 行尾不受影响）。须在四星归一步骤后、星壳残留前
_RE_TRAIL_SINGLE_STAR_BOOK = re.compile(
    r"\*\*([^*\n（(]{1,24}?[（(][^（）)\n*]{1,60}[）)])\*\*(【[^】\n]{1,12}】)\*{2,}$",
    re.M,
)

# 中文名内 2-4 星断裂（page_155 魔染裔 1 条，同缺口 P1）：
# `**魔****染裔（Infernal Influence）【CEoD】**` ——源转换把 `**魔染裔` 劈成
# `**魔**+**染裔` 4 星断裂，_RE_QUAD_STAR 需 `****内容****` 完整包裹（尾 2 星
# 闭星不匹配）失配，_RE_TITLE_STAR 组3 前夹星也失配 → 整条目丢失。组1 中文
# 名 + 剥中间星 + 组2 中文接续 → `**魔染裔（…）`。组2 限中文开头防误伤
# `**A****（` 双星壳连写（该形态 _RE_QUAD_STAR 已归一）。须在 _RE_POST_DEITY 前
_RE_CN_NAME_STAR_SPLIT = re.compile(
    r"\*\*([^*\n（(]{1,24}?)\*{2,4}([一-鿿][^（(\n*]{0,20}?)（"
)

# 括号开头 2-4 星残留剥除（page_152 孔冉达的变形师 1 条 + page_157 神祇括号）：
# `（****Transmuter of Korada）` 四星归一后残 `（**Transmuter of Korada）`、
# `（**凯登` —— `（` 后星残留使 _RE_TITLE_STAR 组3 排除 `*` 失配整条目丢失
#（`（****X` 全角四星形态由 _RE_QUAD_PAREN_LEFT 处理，本正则提前同语义归一）。
# 须在四星归一后、_RE_POST_DEITY 前（神祇括号组3 排除 `*` 才能匹配）
_RE_PAREN_LEAD_STAR = re.compile(r"[（(]\*{2,4}")

# 括号内中段星残留剥除（page_157 豪饮客神祇括号 1 条）：`（凯登**·**凯连，
# **Cayden Cailean）**：` ——`**·**`/`，**` 星壳断裂使 _RE_POST_DEITY 组3
#（排除 `*`）失配 → 剥括号内星恢复 `（凯登·凯连，Cayden Cailean）**：`。
# 组1/组2 排除 `*`（`（****` 四壳形态归 _RE_QUAD_PAREN_LEFT 不误伤；组2
# 吞星会残留 `**凯连，**` 段）且允许 `\n`（`Cayden \nCailean` 跨行英文
# 名，`\n` 排除则组1 卡在换行处剥不动尾星）。组1 须 `（` 锚定 + 组2 不含
# `）`：防 `）**：` 尾星误剥——正常标题闭星 `（EN）**：` 的 `**` 在 `）` 后
# 不匹配本正则。sub 单轮只剥一组（组1 锚定 `（`，括号内多处断裂星须循环
# 至稳定——魔染裔 5 轮上限内）。须在 _RE_POST_DEITY 前
_RE_PAREN_INNER_STAR = re.compile(r"([（(][^（）)*]{1,60}?)\*\*([^（）)*]{0,40})")

# 【书缩写】内星残留剥除（page_153 SH 段 4 条前置）：`【SH****】**` →
# `【SH】**`（源转换把书缩写闭星劈进【】内，_RE_QUAD_STAR 内容排除 `*`
# 部分归一失配）。组1 排除 `*`：`【**SH****】**`（星在前）不剥——该形态
# 是 _RE_STAR_CLOSE_PAREN_BOOK（page_151 神圣密探）的输入，先剥尾星会
# 留前导星使其 `【\*\*内容\*\*\*\*?】` 失配。须在行首补星前（补星后
# _RE_TITLE_STAR 组5 需壳内无星）
_RE_BOOK_INNER_STAR = re.compile(r"【([^】\n*]{1,12}?)\*{2,4}】")
# 【书缩写】全星包裹（`【****SH****】`/`【**SH**】` 前后星）→ `【SH】`，
# _RE_BOOK_INNER_STAR 只剥尾残星（page_151 纯英文名条目星壳残留）
_RE_BOOK_FULL_STAR = re.compile(r"【\*{2,4}([^】\n*]{1,12}?)\*{2,4}】")
# 行首纯英文名标题无开星（删除线壳剥除后）→ 补开星：
# `（EN）【书】**：` → `**（EN）【书】**：`（page_151 Kalistocratic Prophecy）
_RE_LINE_LEAD_EN_PAREN = re.compile(
    r"(?m)^[（(]([A-Za-z][A-Za-z ’'’-]{1,64})[）)](【[^】\n*]{1,12}】)\*\*[：:]"
)

# 行首无开星壳+星壳标题（page_153 SH 段 4 条）：`罪犯之子****（Criminal
# Roots）【SH】**：正文` ——源转换丢行首 `**`，_RE_TITLE_STAR 组1 `\*\*` 失配
# 整条目丢失。组1=行首中文名 + 剥 2-4 星 + 补开星 → `**罪犯之子（…）**：`。
# 行首「中文名+星+（」形态全库仅 SH 段此 4 条（正文行首中文后跟星罕见），
# 且须与【】内星剥除（_RE_BOOK_INNER_STAR）同处执行。须在 _RE_POST_DEITY 前
_RE_LINE_LEAD_CN_STAR = re.compile(r"(?m)^([一-鿿][^：:\n（(]{1,20}?)\*{2,4}（")

# 星壳标题+同行中文正文无冒号（page_155 魔染裔/主宰范 CEoD 段）：
# `**A（EN）【书】**正文` → `**A（EN）【书】**\n正文`。_RE_TITLE_STAR 闭星后
# 只接行尾或冒号（`\*\*(?:[：:](.*))?$`），同行正文失配整条目丢失。
# 组5 前置必选【书】——正文粗体强调 `**技能（X）**` 无【书】不拆。
# 须在链尾（全部星壳归一后），_RE_HALF_TITLE_TRAILER（出处拆行）之后
_RE_TITLE_BODY_SPLIT = re.compile(
    r"\*\*([^*\n（(]{1,24}?)[（(]([^（）()\n]{1,64})[）)]【([^】\n]{1,12})】\*\*(?=[一-鿿])"
)

# 四壳断裂+英文撇号三拆残留（page_154 魔鬼印记）：
# `**A****（****EN****’****s Mark****）【书】：**正文` —— `_RE_QUAD_STAR`
# 需 `[^*\n]{2,}`（≥2 字符），单字符 `’` 不匹配不归一；guard 不拆后残留
# `**A****（EN’**s Mark）【书】：**正文` ——括号内 EN 段残留星已由
# _RE_PAREN_INNER_STAR 循环剥除（`’**s` → `’s`），此处组名前 4 星并入
# 括号（`**A****（` → `**A（`）；不依赖括号内 `**`（剥星后形态无星）。
# 须在 _fix_quad_star_halfparen(guard) 与 _RE_STAR_PAREN_COLON 之间
# （guard 后形态稳定，冒号归一前闭星完整）。
_RE_QUAD_GLUE_APOSTROPHE = re.compile(
    r"(\*\*[^*\n（(]{1,24}?)\*{4}[（(]([^）)\n]*?[）)])"
)

# 四壳标题+【书缩写】断裂（page_151 神圣密探）：`**中文**（EN）【**书****】**：`
# → `**中文（EN）【书】**：`——_fix_quadruple_star 只归一 `（****B****）**` 完整
# 形态，括号后跟【】时断裂残留（闭合星壳中文 + 星壳外括号 + 【】内残星），
# 标题判定失败走半星壳分支丢同行正文。须在 guard 拆行后（形态稳定）。
_RE_STAR_CLOSE_PAREN_BOOK = re.compile(
    r"\*\*([^*\n（(]{1,24}?)\*\*[（(]([^（）()\n]{1,64})[）)]【\*\*([^】\n*]{1,12})\*\*\*\*?】"
)

# 半星壳+星壳外括号+冒号正文（page_1579 信手拈来/千杯不醉）：`**中文**(EN)：正文`
# → `**中文（EN）**：正文`——_RE_TITLE_HALF 半星壳分支只接「出处同行」无正文
# 捕获，text 空。组3 冒号+组4 正文首字符限定，防无正文形态
#（`**速饮者**(Accelerated Drinker) 出自《…》` 出处同行不受影响）。
_RE_HALF_PAREN_COLON = re.compile(
    r"\*\*([^*\n（(]{1,24}?)\*\*[（(]([^（）()\n]{1,64})[）)]([：:])(\S)"
)

# 星壳内「中文 空格 英文（中文）」三明治（BotA 自然主义者）：
# `**自然主义者 Naturalist（亚马萨）**：` → `**自然主义者（Naturalist）（亚马萨）**：`
# ——英文名转入括号（_RE_TITLE_STAR 组3 捕获进 name_en），地名括号保留为
# 组4（类型词/地名判定交 split 层，亚马萨非类型词丢弃）；组1 中文限连续
# 无空格（防 `**A（EN）**` 星壳形态误伤），组2 英文名后必须空格+括号
_RE_TITLE_SPACE_EN_PAREN = re.compile(
    r"\*\*([一-鿿][^：:\n（）() ]{1,24}?) ([A-Za-z][A-Za-z ’'’-]{1,40})"
    r"[（(]([^）)\n]{1,40})[）)]\*\*"
)

# 后置神祇括号并入标题（page_157 基础页两段形态）：
# `**A（EN）【书】**（神祇，**EN**）**：正文` / `**A（EN）【书】****[种族]（神祇）**：正文`
# ——组1=标题星壳（含阵营尾缀） 组2=【书】 组3=神祇中文名（可含残星前缀）
# 组4=神祇英文名（容跨行——豪饮客 `Cayden \nCailean` 源数据换行，_RE_
# CROSS_LINE_EN_PAREN 合并在其后执行，此处须先越行匹配才能并入标题）
_RE_POST_DEITY = re.compile(
    r"(\*\*[^*\n（(]{1,24}?[（(][^）)\n]{1,64}[）)](?:[（(][^）)\n]{1,60}[）)])?)"
    r"(【[^】\n]{1,12}】)\*{2,4}?\[?[^\]\n]{0,12}\]?[ \t]*"
    r"[（(]([^）)\n*]{1,24}?)(?:\*\*)?([^）)*]{1,40})[）)]\*{2,4}?[：:]"
)

# 星壳标题冒号在壳内（page_1579 家传武器）：`**A（EN）：**正文` → `**A（EN）**：正文`
# 组1 容可选【书】后缀（page_154 四壳断裂形态 `**A****（****EN****）【书】：**正文`
# 四星归一后冒号仍夹在【书】与闭星之间，须先把闭星移到冒号前 _RE_TITLE_STAR
# 组5 才接得上 `\*\*`）
_RE_STAR_PAREN_COLON = re.compile(
    r"\*\*([^*\n（(]{1,24}?[（(][^）)\n]{1,60}[）)](?:【[^】\n]{1,12}】)?)[：:]\*\*"
)

# 双括号+星壳内冒号（狗头人 `**中文（区域）（EN，EN）:**正文`——中文括号=
# 区域子类型保留 title，EN 括号含中文逗号，闭星在冒号后）：先归一为
# `**中文（区域）（EN，EN）**：正文`，再走 TITLE_STAR 组3（区域丢弃）/
# 组4（EN 名）语义分支（_RE_PAREN_SPAN 已合并括号内跨行）
_RE_DUAL_PAREN_COLON = re.compile(
    r"\*\*([^*\n（(]{1,24}?[（(][^）)\n]{1,24}[）)])\s*[（(]([^）)\n]{1,80})[）)][：:]\*\*"
)

# 星壳条目同行拆行（见 normalize 调用处注释；须在 _RE_PAREN_SPAN 跨行合并后
# 执行——EN 名/神祇括号跨行先并回单行才能匹配）——「行首不拆 + 中文空格
# 英文（X）**：」形态；组1 含空格限定（正文粗体 `**中文（EN）**：` 无空格
# 不误拆）
_RE_ENTRY_GLUE_SPLIT = re.compile(
    r"(?<!\n)(?=\*\*[^*\n（(]{1,24}? [A-Za-z][A-Za-z ’'’-]{0,60}"
    r"[（(][^）)\n]{1,40}[）)]\*\*[：:])"
)

# 星壳中文名+裸英文名行尾（PIS 破链者/伪装海盗、DA 链接锚、AON 链接剥壳后）：
# `**A**EN（地区）` / `**A**EN:（地区）` / `**A**EN ` / `**A** EN ` ——英文名
# 并入标题括号（尾括号/冒号一并吞，地区名非类型词不保留）。组2 前 `[ \t]*`
# 容「星壳后空格+英文名」（AON `[**A** EN ](url)` 剥链接壳后形态）；组2 非贪婪
# 防吞英文名尾空格（`{0,40}?` + 行尾锚定回溯，`**A** EN \n` 组2 停在 `EN`）
_RE_STAR_BARE_EN_TRAIL = re.compile(
    r"\*\*([^*\n（(]{1,24}?)\*\*[ \t]*([A-Za-z][A-Za-z ’'’-]{0,40}?)"
    r"(?:[：:]?[（(][^（)\n]{1,20}[）)]|[：:])?[ \t]*$",
    re.M,
)

# 星壳中文名+裸英文名+冒号正文（矮人 头脑清醒）：`**A**EN：正文` →
# `**A（EN）**：正文`。组1 排除字母（防 `**头脑清醒Clearheaded：` 组1 贪婪吞
# 英文名后闭合星失配整体失败——源形态闭合星可缺省，`(?:\*\*)?` 容两者）；
# 替换时组2 为 `[A-Za-z][A-Za-z ’'’-]{0,40}` 贪婪含尾空格，`\s*` 消化。
# 组1 再排除书名号《》：标题+出处同行形态（初探探索者协会 `**…**   出自
# 《初探探索者协会》Pathfinder Player Companion: …`）闭星后的「出自《中文
# 书名》」会被组1 吞为中文名 → 出处行被补星壳（伪条目+source 残留），
# 2026-08-06 任务4 排查修复（条目名不含书名号）
_RE_STAR_BARE_EN_COLON = re.compile(
    r"\*\*([^（(\n*A-Za-z《》]{1,24}?)(?:\*\*)?([A-Za-z][A-Za-z ’'’-]{0,40})[：:]\s*(\S.*)$", re.M
)

# 星壳标题+PFS 尾缀（BotA 此翼天成）：`**A(EN)PFS可**` → `**【PFS】**A（EN）**`
# ——PFS 标记转星壳前置（split 层 pre=PFS → pfs_eligible），不污染类型/来源
_RE_STAR_PFS_TRAIL = re.compile(
    r"\*\*([^*\n（(]{1,24}?)[（(]([^）)\n]{1,40})[）)](PFS可|PFS可用|PFS禁用)\*\*"
)

# 星壳中文名+裸英文名+残星+出处同行（瓦瑞西亚/StLC）：
# `**A**EN** **出自《书》p21` / `**A**EN** 来源 X pg. N**` → 标题 + 独立出自行
# 残星段 `\*{0,2}`：`\*\*?` 正则语义是「1-2 星必选」（`\*` 必须 + `\*?` 可选），
# StLC 形态 `**A**EN** 来源…` 闭星后无开星——`\*\*?` 至少 1 星直接整体失败
_RE_STAR_BARE_EN_SRC = re.compile(
    r"\*\*([^*\n（(]{1,24}?)\*\*([A-Za-z][A-Za-z ’'’-]{1,40})\*\*[ \t]*\*{0,2}[ \t]*"
    r"((?:出自|来源))[ \t]*([^\n]{1,60})\*{0,2}"
)

# 裸行中文名+英文名+冒号正文（矮人 深刻标记）：`中文EN：正文` → `**中文（EN）**：正文`
# 组1 排除空格：名词解释段为 `中文 空格 英文:正文`（seed02 旋舞修士，split 层
# _RE_GLOSSARY 跳过），矮人条目为 `中文英文：正文`（无空格）——空格即分界。
# `(?!出自)` 守卫：出处行 `出自《中文书名》English: …`（初探探索者协会/初探
# 内海ISP/繁星子民 3 文件）不是条目——组1 字符类不排除《》会被补星壳产伪条目
# 「初探探索者协会》」+ source 残缺（《），2026-08-06 任务4 排查修复
_RE_BARE_CN_EN_COLON = re.compile(
    r"^(?!出自)([一-鿿][^：:\n（）() ]{1,24}?)([A-Za-z][A-Za-z ’'’-]{1,40})[：:]\s*(\S)", re.M
)

# 星壳标题+同行中文译名行尾（StLC 跨界魔法）：`**A（EN）**二（异）世界魔法` → 补冒号
#（译名并入正文防标题吞并；`[^\n]{0,30}` 限短行防正文段误伤）
_RE_STAR_TRAIL_CN = re.compile(
    r"(\*\*[^*\n（(]{1,24}?[（(][^）)\n]{1,64}[）)]\*\*)([一-鿿][^\n]{0,30})$", re.M
)

# EOD 断行字段标签分裂：`**分类 \n**基础（战斗）` → `**分类**：基础（战斗）`
# （标签未闭合行尾 + 下一行以 `**` 开头 = 值行，剥值行前导星并补闭合+冒号；
# MULTILINE 锚定行首防误伤 `**分类** 地区\n**需求**` 已闭合形态——行1 必须是裸
# `**标签` 开头）
_RE_SPLIT_FIELD_LABEL = re.compile(
    r"^\*\*(?!\*)([^：:\n ]{1,5})[ \t]*\n\*\*(?!\*)", re.MULTILINE
)

# 补录段标题尾部四星冒号：`【WMH】****：**正文` → `**：正文`
# （补录段 `**X（EN）【书】****：**` 形态，_RE_QUAD_STAR 不匹配（星后非 4 星包裹））
_RE_TITLE_TAIL_QUAD_COLON = re.compile(r"\*{4}[：:]\*{2}")

# 壳外【书】并入壳内（seed30 秘文会）：`**中文（EN）**【书】**：` →
# `**中文（EN）【书】**：`（对齐 _RE_TITLE_STAR 组5 壳内形态）。壳外形态源于
# `**中文****（**EN**）**` 4 星粘连——公共层 _RE_NESTED_STAR 需 `**A（**B**）**`
# 完整形态才能剥 `）**`，粘连断裂时闭合星残留在【书】前挡路组5。
_RE_OUTER_BOOK_GLUE = re.compile(
    r"(\*\*[^*\n（(]{1,24}?[（(][^）)\n]{1,64}[）)])\*\*(【[^】\n]{1,12}】)\*\*[：:]"
)

# 中文名 + 换行 + 英文名（P&P 段内粘连 `炼金销赃者 \nAlchemical Fence（…）：`）：
# 行2 后跟括号/冒号防正文误合并
_RE_CN_EN_LINEBREAK = re.compile(
    r"([一-鿿][^：:（(\n]{0,20})[ \t]*\n[ \t]*([A-Za-z][A-Za-z ’'’-]{1,64}[）)（(：:])"
)

# BotM/ACO 跨行流式条目拆行（见 _normalize_custom 调用处注释）：
# 条目边界 = 中文名（无空格，限 1-24 字）+ 空格 + 英文名 + `（…）：` 或 `：`。
# 负向后瞻「前面不是汉字」：中文名序列内任意字都能作「中文+字母」起点
#（`炼金销赃者` 里 `金销赃者` 也匹配），只有条目真正开头的字前面是正文
# 标点/行首——防拆行拆进中文名内部。组1 字符类排除书名号《》：
# 出处行 `出自《中文书名》English: …`（初探探索者协会等 3 文件）是「中文+
# 空格+英文+冒号」形态会被误拆（`出自` 行首点 + `《` 后点两处）——书名号
# 排除后组1 到《/》即停、后续非空格前瞻失败，出处行不再拆（2026-08-06 任务4）
_RE_BOTM_SPLIT = re.compile(
    r"(?<![一-鿿])(?=[一-鿿][^：:\n（）()《》 ]{1,24}? [A-Za-z][A-Za-z ’'’-]{1,64}"
    r"(?:[（(][^）)]{1,32}[）)][：:]|[：:]))"
)

# 括号内容跨行（神名 `（"灰色斑斓" \n妮薇）`、字段值 `（Kelesh or \nQadira）`）：
# 合并不影响语义，统一去换行
_RE_PAREN_SPAN = re.compile(r"([（(][^）)\n]*)\n([^）)\n]*[）)])")

# StLC 字段标签内星壳：`**类型：**魔法` → `**类型**：魔法`（缺陷页 `**效果：**` 同型）
_RE_LABEL_COLON_INNER_STAR = re.compile(r"\*\*([一-鿿]{2,4})[：:]\*\*")

# ---------------------------------------------------------------------------
# split 判定正则
# ---------------------------------------------------------------------------

# 星壳标题（归一后单行）：`**中文（EN）**【书】**：正文` / `**【地区】中文（EN）**【书】**` /
# `**中文（EN）（类型）**`；组1=前置【类型】 组2=中文名 组3=括号 组4=第二括号
# 组5=后缀【】 组6=标题后同行正文（`**：正文` 形态）
_RE_TITLE_STAR = re.compile(
    r"^\*\*(?:【([^】]{1,10})】)?"
    r"([^（(\n*]{1,24}?)"
    r"[（(]([^（）()\n*]{1,64})[）)]"
    r"(?:[（(]([^（）()\n*]{1,60})[）)])?"
    r"(?:【([^】]{1,12})】)?"
    r"\*\*(?:[：:](.*))?$"
)

# 纯英文名标题（无中文名，page_151 Persuasive Insight/Kalistocratic
# Prophecy，est 预测「解析器需兜底」）：`**（EN）【书】**：正文` ——
# _RE_TITLE_STAR 组1 要求非括号字符开头失配，无分支时落入正文被前条吞并
_RE_EN_ONLY_TITLE = re.compile(
    r"^\*\*[（(]([A-Za-z][A-Za-z ’'’-]{0,64})[）)]"
    r"(?:【([^】\n*]{1,12})】)?\*\*[：:](.*)$"
)


# 括号语义漂移判定：paren 是类型词（词表 / 「背景/信仰」结尾 / 基础（X））
# 才进 trait_type；地名（安多安/终焉之墙/卡塔佩什）、神名（泽弗斯）丢弃。
# （勘探确认 15 簇括号语义漂移普遍，纯中文括号全当类型会引入地名乱值）
def _is_trait_type_paren(s: str) -> bool:
    if s in _TRAIT_TYPE_WORDS:
        return True
    if s.endswith("背景"):
        return True
    return bool(re.match(r"^基[本础]?[（(][^）)]+[）)]$", s))


# 基础（X）剥壳（人工门 1 拍板：基础（X）并入对应类型，不保留「基础」限定词）——
# formats 层只剥括号壳取类型词（基础（战斗）→ 战斗）；词表映射（信仰→信念）
# 留 processor 层 _normalize_trait_types（_RE_BASIC_TRAIT 同规，两侧同源）
_RE_BASIC_PAREN = re.compile(r"^基[本础]?[（(]([^）)]+)[）)]$")


def _strip_basic_trait(s: str) -> str:
    m = _RE_BASIC_PAREN.match(s)
    return m.group(1) if m else s


# 顶层顿号拆分：忽略括号内的分隔符（`种族背景（半精灵、半兽人或人类）`
# 不拆；`地区，世界之冠` 拆 地区/世界之冠）
def _split_top_level(value: str) -> list:
    depth = 0
    parts: list = []
    cur: list = []
    for ch in value:
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth -= 1
        if ch in "，,、" and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]

# 四壳括号左残留归一（page_158 污染之魂）：`（****Tainted Spirit)` 缺右星闭合
# → `（Tainted Spirit）`，恢复 _RE_TITLE_STAR 可匹配形态。须在四星归一后
# （对称四壳先处理，剩「左四星缺右星」残留）。
_RE_QUAD_PAREN_LEFT = re.compile(r"（\*\*\*\*([^）)\n]{1,64})[）)]")

# 斜杠双译名+无括号英文名（page_158 奥术恶性状态）：
# `**奥术恶性状态/奥术畸变Arcane Malignancies **` → `**奥术恶性状态（Arcane Malignancies）**`
# 组1=主译名（排除 / 防斜杠双译名误吞） 组2=英文名（跨行已在 _merge_cross_line_en 合并）
_RE_SLASH_DUAL_EN = re.compile(
    r"\*\*([^/（(\n*]{1,24}?)/[^（(\n*]*?"
    r"([A-Za-z][A-Za-z ’'’\n]{0,60}?)\s*\*\*"
)

# 跨行无闭合星壳+星壳出处行合并（page_158 急躁）：
# `**急躁（Impatient） \n**《反英雄手册…》 第6页` → `**急躁（Impatient）**《…》 第6页`，
# 供 _RE_HALF_TITLE_TRAILER 拆行（出处行特征 `**《` 防误并正文）。
_RE_UNCLOSED_TITLE_TRAILER = re.compile(
    r"(\*\*[^*\n（(]{1,24}?[（(][^）)\n]{1,64}[）)])\s*?\r?\n(\*\*《[^》\n]{1,64}》[^）)\n]*)"
)

# 未闭合星壳标题+下一行四星字段（典范背景形态，seed_56）：
# `**A（EN）\n****标签**：值` → 组1=未闭合标题 组2=quad-star 前两星（弃）
# 组3=字段行余部（`**标签**：`）。替换补标题闭星、剥弃星还原字段行。
_RE_QUAD_NEXT_FIELD = re.compile(
    r"^(\*\*[^*\n]{1,40}[（(][^）)\n]{1,64}[）)])\r?\n\*\*(\*\*[^\n]{1,20}?\*\*：)",
    re.M,
)

# ---- 2026-08-06 任务2：ABC 类扩展书文件章节标记行 + 无星壳条目形态 ----

# TEoG 跨行括号条目（中文（神/种族） EN + 换行 + (EN)正文粘连）：
# `调和者（莎伦莱） Ambassador \n(Sarenrae)你在…` → 单行供 _RE_TEOG_PAREN。
# 组1=中文名（括号）+英文名 组2=下一行 (英文)正文（括号开头防误并正文）。
_RE_TEOG_PAREN_CROSS_LINE = re.compile(
    r"^([一-鿿][^：:\n]{1,20}?[（(][^）)]{1,16}[）)][ \t]*[A-Za-z][A-Za-z ’'’-]{1,50})[ \t]*\r?\n"
    r"([（(][^）)\n]{1,24}[）)][一-鿿])",
    re.M,
)

# 矮人无星/半星壳跨行（中文EN + 换行 + （地区）：正文）：`霜血Frostborn\n
# (Lands of the Linnorm Kings)：…` → 单行。组1=中文名 组2=英文名
# 组3=（地区）：正文。组1 排除括号防吞 TEOG 形态（TEOG 组1 带括号）。
_RE_CROSS_LINE_EN_PAREN = re.compile(
    r"^([一-鿿][^：:\n（）()]{1,20}?)([A-Za-z][A-Za-z ’'’-]{1,50})[ \t]*\r?\n"
    r"([（(][^）)\n]{1,30}[）)][：:])",
    re.M,
)

# 矮人半星壳（`**浴血者Blooded` 无闭星）→ 剥前导星。星后必须是字母（英文名），
# `**头脑清醒（Clearheaded）`（星后中文+括号）不剥。
_RE_STAR_HALF_CN_EN = re.compile(
    r"^\*\*([一-鿿][^：:\n*（）()A-Za-z]{1,20}?)([A-Za-z][A-Za-z ’'’-]{1,50})", re.M
)

# 矮人星壳中文+星壳英文（`**大地的加护**Deep Guardian**：正文`，魔法段形态）
# → `**大地的加护（Deep Guardian）**：正文`，复用 _RE_TITLE_STAR。
_RE_STAR_CN_STAR_EN = re.compile(
    r"^\*\*([一-鿿][^：:\n*]{1,20}?)\*\*([A-Za-z][A-Za-z ’'’-]{1,50})\*\*[：:]\s*(.*)$",
    re.M,
)

# 矮人括号错位（`（波络卡**Bolka）`——神名中文星壳+英文无闭星）→
# `（波络卡）Bolka`，恢复 _RE_FLOW 可匹配形态（deity 提取）。
_RE_PAREN_STAR_EN = re.compile(r"[（(]([一-鿿]{1,12})\*\*([A-Za-z][A-Za-z ’'’-]{1,30})[）)]")

# 中文名+星壳英文（精灵/矮人魔法段）：`神奇把戏**Arcane Dabbler**：正文`。
# 星壳保留型（公共层剥星型走 _RE_FLOW）。组3=括号（纯中文非类型词丢弃
# 防地名误填 deity，对齐 _RE_FLOW 英文括号丢弃策略）。
_RE_CN_STAR_EN = re.compile(
    r"^((?:[A-Za-z]{1,20}?的)?[一-鿿][^：:\n*]{1,24}?)\*\*([A-Za-z][A-Za-z ’'’\-]{1,64})\*\*"
    r"(?:[（(]([^）)]{1,24})[）)])?[：:]\s*(.*)$"
)

# TEoG 行内/合并后括号条目（`调和者（莎伦莱） Ambassador (Sarenrae)你…`）：
# 组1=中文名 组2=中文括号（神名→deity；种族细分/区域→丢弃） 组3=英文名
# 组4=英文括号（丢弃） 组5=正文（中文开头限定防英文行误匹配）。
_RE_TEOG_PAREN = re.compile(
    r"^([一-鿿][^：:\n]{1,20}?)[（(]([^）)]{1,16})[）)][ \t]*"
    r"([A-Za-z][A-Za-z ’'’-]{1,50})"
    r"(?:[（(]([^）)]{1,24})[）)])?([一-鿿].*)$"
)

# 中文括号非神判定：种族细分（人类——塔尔多人/半兽人/精灵）与区域词
# （安多安/奇奥尼）开头特征——含「——」/「、」/「·」分隔或种族词前缀。
_RE_NON_DEITY_CN = re.compile(
    r"^(?:人类|精灵|矮人|半兽人|半精灵|半身人|侏儒|神裔|魔裔|地精|豺狼人)"
    r"|——|、|·"
)

# 章节分类标记行（裸文本/星壳中文 / 裸文本英文 Traits 三形态）→ 段落级
# trait_type 来源（TEoG `地区背景（塔尔多）…`、矮人 `**矮人的地区背景`/
# `**魔法背景：**`、精灵 `Racial Traits`/`Religious Traits 信仰背景…`）。
# 中文：`^\**` 前缀 + 可选「X的」前缀 + X背景；英文：`X Traits` 词表映射。
_SECTION_MARKER_CN = re.compile(
    r"^\*{0,2}\s*(?:[一-鿿]{1,6}的)?"
    r"((?:地区|宗教|种族|魔法|战斗|社会|信念|信仰|派系|宇宙|装备|坐骑|典范|缺陷)背景)"
    r"[ \t]*[：:（(]?\*{0,2}"
)
_SECTION_MARKER_EN = re.compile(r"^([A-Za-z]{2,12})[ \t]+Traits?\b")
_EN_TO_CN_SECTION = {
    "Racial": "种族背景", "Religious": "信仰背景", "Regional": "地区背景",
    "Magic": "魔法背景", "Combat": "战斗背景", "Social": "社会背景",
    "Faith": "信念背景", "Faction": "派系背景", "Cosmic": "宇宙背景",
    "Equipment": "装备背景", "Mount": "坐骑背景", "Exemplar": "典范背景",
    "Defect": "缺陷背景",
}

# 半星壳+同行出处拆行（page_158 缺陷补录形态，无「出自」前缀；
# 2026-08-05 扩展 `出自《…》` 变体——ACO 狮的勇气/DA 名门望族无页数形态）：
# `**中文（EN）**《书》 第N页` / `**中文（EN）**Spymaster's Handbook` /
# `**中文（EN）** 出自《书》` → 标题独立 + 出处行。
# 组1=星壳标题（闭合星前容空格） 组2=出处（《书》+页数 | 出自《书》 | 裸英文书名）。
# 拆行后标题走 _RE_TITLE_STAR，出处行走 _RE_SOURCE_LINE 扩展形态。
_RE_HALF_TITLE_TRAILER = re.compile(
    r"(\*\*[^*\n（(]{1,24}?[（(][^）)\n]{1,64}[）)])\s*\*\*\s*"
    r"(《[^》\n]{1,64}》\s*第[0-9零一二三四五六七八九十百]{1,6}页"
    r"|出自《[^》\n]{1,64}》[^：:\n]{0,40}"
    r"|[A-Za-z][^《\n]{1,64})"
)

# 半星壳标题：`**速饮者**(Accelerated Drinker) 出自《…》`（组3 出处同行）
_RE_TITLE_HALF = re.compile(
    r"^\*\*([^（(\n*]{1,24}?)\*\*[（(]([^）)\n]{1,64})[）)]\*{0,2} ?(?:出自《(.+?)》)?"
)

# H2 标题：`## 中文名（EN）` 或 `## 裸中文名`（三重标题合并）
_RE_H2 = re.compile(r"^## (.+)$")

# 流式裸名（归一后）：`亲近元素Affinity for the Elements（任何一位元素领主）：正文`
# 组1=中文名 组2=英文名 组3=括号（deity/类型，语义簇感知） 组4=同行正文
# 2026-08-05：`[）)]` 后容半角冒号（矮人 `(Lands of the Linnorm Kings):正文`）
# 2026-08-06：组1 容英文前缀（精灵 `Sovyrian的泛神论Sovyrian Pantheist（全部
# 精灵神）：`——公共层 _RE_CN_EN_ADJACENT_STAR 剥星后形态，英文开头中文名）
_RE_FLOW = re.compile(
    r"^((?:[A-Za-z]{1,20}?的)?[一-鿿][^：:\n（）()]{1,24}?)([A-Za-z][A-Za-z ’'’-]{1,64})"
    r"[（(]([^）)]{1,32})[）)][：:]\s*(.*)$"
)

# 表格条目（背景特性17 星座表）：`| 1-7 | 画眉鸟座（The Thrush） | … | 效果 |`
_RE_TABLE_ENTRY = re.compile(
    r"^\|[^|]*\| ([^|（(]+)[（(]([^）)]+)[）)] \|[^|]*\| ([^|]+) \|$"
)

# 字段行（九种异体标签）：`**类型**：地区` / `**类型：**魔法` / `类型：宗教` /
# `**分类** 地区`（无冒号值同行）/ `**效果：**正文` / `**分类**`（无冒号值下一行）/
# `描述：…`（PotN 行走正文分支，2026-08-05 补录）
_RE_FIELD = re.compile(
    r"^\*{0,2}(类型|分类|类别|背景类型|需求|要求|前置条件|效果|出处|描述)\*{0,2}[：:]?\*{0,2}([^\n]*)$"
)

# 出自行独立行，三分支：
# 1. `出自《…》` / `**出自《…》**`（StLC 星壳）/ `来源 X pg. N`（StLC 双译名尾）——前缀必现
# 2. `《书》 第N页`（page_158 缺陷补录拆行，中文数字页）
# 3. `Spymaster's Handbook`（裸英文书名拆行）——字母开头整行
# ⚠️ 分支 1 前缀不可省（省则全放开吞正文）；全角空格行尾在解析处剥除。
_RE_SOURCE_LINE = re.compile(
    r"^\*{0,2}(?:出自|来源)\*{0,2}《?[：:]?(.+?)》?\*{0,2}$"
    r"|^《([^》\n]{1,40}》[　 ]*第[0-9零一二三四五六七八九十百]{1,6}页)[　 ]*$"
    r"|^([A-Za-z][A-Za-z ’'’\-]{1,50})[　 ]*$"
)

# PFS 禁用说明行：`【PFS】PFS中不可使用缺陷系统。`
_RE_PFS_DISABLED = re.compile(r"^【PFS】.*不可使用")

# 名词解释段（条目正文后的散文段）：`旋舞修士 Whirling Dervishes:在阿维斯坦…`
# 无星壳无括号裸名 + 冒号开头 → 跳过（区别于 _RE_FLOW 需括号）
_RE_GLOSSARY = re.compile(
    r"^[一-鿿][^：:\n（）()]{1,24}? [A-Za-z][A-Za-z ’'’-]{1,64}[：:]"
)

# 中文名+空格+英文名+中文正文粘连（TEoG 骑士精神：`骑士精神 Chivalrous你的成长…`
# 无冒号无括号，_merge_cross_line_en 跨行合并后形态）——组3 以中文开头限定
_RE_TEOG_GLUE = re.compile(
    r"^([一-鿿][^：:\n（）()]{1,20}?) ([A-Za-z][A-Za-z ’'’-]{1,50})([一-鿿].*)$"
)

# 裸行标题（无星壳），两变体：
# 1. `中文EN` 行尾（WO 风语者 / PotN 传奇伤痕）——下一行是字段行才产条目
# 2. `中文（EN）` 裸行（DA 地名/名词解释同形）——下一行是字段行才产条目
#（无字段跟随 → 走正文分支，DA 扎摩诔地名不误判）
_RE_BARE_TITLE = re.compile(
    r"^([一-鿿][^：:\n（）()]{1,24}?)([A-Za-z][A-Za-z ’'’-]{1,40})[ \t]*$"
    r"|^([一-鿿][^：:\n（）()]{1,24}?)[（(]([^）)\n]{1,40})[）)][ \t]*$"
)

# 星壳无括号纯行（BotA 引导句/正文强调）：`**以下…角色**` ——星壳但无括号
# 无冒号——归一后条目必有括号（_RE_TITLE_STAR），纯星壳行是引导句/强调
# 文本非条目，skip（防 split 正文分支将其当章节介绍产 intro 空条目）
_RE_BARE_STAR_SHELL = re.compile(r"^\*\*[^*\n（()：:]{2,80}?\*\*$")

# 【】后缀 = 类型词（非书缩写）→ trait_type
_TRAIT_TYPE_WORDS = {
    "地区", "种族", "战斗", "信念", "魔法", "社会", "装备", "宗教", "派系",
    "宇宙", "典范", "坐骑", "缺陷", "基础", "信仰",
}

# 字段标签九种异体 → 四语义字段（描述 → effect 并入正文，PotN）
_FIELD_SEMANTIC = {
    "类型": "trait_type",
    "分类": "trait_type",
    "类别": "trait_type",
    "背景类型": "trait_type",
    "需求": "requirement",
    "要求": "requirement",
    "前置条件": "requirement",
    "效果": "effect",
    "出处": "source",
    "描述": "effect",
}


class TraitFormat(BaseFormat):
    def category(self) -> str:
        return "trait"

    # ------------------------------------------------------------------
    # normalize：公共链 + trait 专属 4 步
    # ------------------------------------------------------------------

    def _normalize_custom(self, text: str) -> str:
        # 整行 HTML 注释剥除（`<!-- BM-source:背景特性3.md:条目名 -->` 条目级
        # 来源标记，51 文件；非正文，并入 text 会污染检索）。HH 段注释
        #（`<!-- HH-source:page_703.md:条目名 -->`，背景特性17 补录段）保留
        # 哨兵行 `<!-- HH-segment -->`：split 层识别 HH 段起点（方案 R3-B——
        # 处理器层 R2 页面级默认需排除 HH 段条目防误伤）
        def _strip_comments(m):
            return "<!-- HH-segment -->\n" if "HH-source" in m.group(0) else ""

        text = re.sub(r"^[ \t]*<!--.*-->[ \t]*\r?\n?", _strip_comments, text, flags=re.M)
        # 引导句星壳+条目同行拆行（BotA 六段）——须在跨行合并前（拆后各行独立处理）。
        # 替换 `\1\n**`：4 星连续时组1 闭星吃前 2 星、正则 `\*\*` 吃条目开星
        #（星 3-4）——不加回 `**` 会丢条目开星前缀（seed46 自然主义者）
        text = _RE_INTRO_GLUE_STAR.sub(r"\1\n**", text)
        # 删除线壳剥除（C_flaw `**~~缺陷~~**`），恢复标准标题形态
        text = _RE_STRIKE_SHELL.sub("", text)
        # 星壳内跨行英文合并（A 族四壳 `（****Armor \nExpert****）`）
        text = _merge_cross_line_en(text)
        # 裸英文跨行合并（ACO/P&P/StLC 无星壳形态），两次覆盖三行
        text = _RE_BARE_EN_JOIN.sub(r"\1 \2", text)
        text = _RE_BARE_EN_JOIN.sub(r"\1 \2", text)
        # 中文名+换行+英文名（P&P 段内粘连）与括号内容跨行（神名/字段值）
        text = _RE_CN_EN_LINEBREAK.sub(r"\1 \2", text)
        # BotM/ACO 跨行流式条目：源文件条目间同行句号分隔（`月之子裔 \nChild of
        # the Moon(魔法)：正文。创痛变身Traumatic \nShift：正文。…`），跨行合并
        # 后整段压成一行，FLOW 行首锚定只产首条目——按条目边界（中文名+英文名
        # 后跟括号/冒号）插换行拆开。正文「中文+字母+（/：」序列罕见（中文正文
        # 为主，数字/标点不触发），前瞻拆行误伤面小。
        text = _RE_BOTM_SPLIT.sub("\n", text)
        text = _RE_PAREN_SPAN.sub(r"\1\2", text)
        # 星壳条目同行相连（BotA 劳有所得段）：`**A（EN）**：正文…**B（EN）**：正文…`
        # ——引导句拆行后条目仍同行（源文件条目间无换行），按「中文 空格 英文
        # （X）**：」完整条目星壳边界拆行；行首不拆（防拆第一条自身）、组1 后
        # 必须有「空格+字母」（`**法术辨识（Spellcraft）**：` 正文粗体强调无
        # 空格 EN 段不拆）
        text = _RE_ENTRY_GLUE_SPLIT.sub("\n", text)
        # 出自行页码跨行 `pg. \n10`
        text = _RE_SOURCE_PAGE_JOIN.sub(r"\1 \2", text)
        # 翻译链接壳剥除（ISG 25 处，正文完整不吞）
        text = _strip_http_links(text)
        # 四壳/嵌套星壳归一（`**A（****B****）**` → `**A（B）**`；ISG 星壳 EN 剥星）
        text = _fix_quadruple_star(text)
        text = _fix_elided_quadruple_title(text)
        # 四壳断裂标题并回（`**A****（**EN**）**` → `**A（EN）**`，防 _fix_quad_star_halfparen 误拆）
        text = _RE_QUAD_GLUE_TITLE.sub(r"**\1（\2）", text)
        # 星壳内「中文 空格 英文（中文）」三明治（BotA）——英文名转入括号
        #（跨行英文合并后执行，`**A EN（X）**` 形态方完整）
        text = _RE_TITLE_SPACE_EN_PAREN.sub(r"**\1（\2）（\3）**", text)
        # 括号内 EN 星壳+中文地点星壳断裂（`（EN****，****中文）` → `（EN，中文）`，
        # page_156 HoG 段；须在 _RE_EN_TRAIL_STAR_COMMA 前——其 `\*\*` 吃 2 星后
        # 组2 前顶 2 星回溯失败，4 星形态归本正则）
        text = _RE_EN_STAR_CN_PLACE.sub(r"（\1，\2）", text)
        # 括号内英文名残星+逗号清理（`（EN**，` → `（EN，`，后置神祇括号并入的前置）
        text = _RE_EN_TRAIL_STAR_COMMA.sub(r"（\1\2", text)
        # 中文名内星断裂剥除（page_155 魔染裔 `**魔****染裔（` → `**魔染裔（`，
        # 四星归一后形态；须在 _RE_POST_DEITY 前）
        text = _RE_CN_NAME_STAR_SPLIT.sub(r"**\1\2（", text)
        # 括号内中段星残留剥除（page_157 豪饮客 `（凯登**·**凯连，**Cayden…`）
        # → 剥星后 _RE_POST_DEITY 组3/4 可匹配；须在 _RE_POST_DEITY 前。
        # 组1 锚定 `（` 每轮只剥一组，括号内多处断裂（`**凯连，**` + 尾 4 星）
        # 循环至稳定（豪饮客 5 轮、魔鬼印记 3 轮）
        while True:
            _prev = _RE_PAREN_INNER_STAR.sub(r"\1\2", text)
            if _prev == text:
                break
            text = _prev
        # 【书缩写】内星残留剥除（page_153 SH 段 `【SH****】**` → `【SH】**`）
        # ——行首补星前置步骤
        text = _RE_BOOK_INNER_STAR.sub(r"【\1】", text)
        # 行首无开星壳+星壳标题（page_153 SH 段 `中文名****（EN）【SH】**`）
        # → 补开星恢复 _RE_TITLE_STAR 可匹配形态（行首中文名+星全库仅此形态）
        text = _RE_LINE_LEAD_CN_STAR.sub(r"**\1（", text)
        # 后置神祇括号并入标题（`**A（EN）【书】**（神祇，EN）**：` → 单标题星壳）
        text = _RE_POST_DEITY.sub(r"\1（\3\4）\2**：", text)
        # guard=True：`）****（` 截断形态才拆行（seed11 残留括号）。四壳断裂标题
        # `**中文****（****EN****）【书】：**正文`（4 星前是中文名）是完整标题+
        # 同行正文，拆行会丢条目（page_154 38 条特性全灭，KN112 同款守卫）
        text = _fix_quad_star_halfparen(text, guard=True)
        # 四壳断裂+撇号三拆残留（`**A****（EN’s Mark）` → `**A（EN’s Mark）`）
        # ——括号内星已由 _RE_PAREN_INNER_STAR 循环剥除，此处只并入组名前 4 星
        text = _RE_QUAD_GLUE_APOSTROPHE.sub(r"\1（\2", text)
        # 四壳标题+【书缩写】断裂（page_151 神圣密探）→ 单星壳，标题判定接正文
        #（替换串不补尾星——源 `】**：` 的闭星不在匹配范围，自然闭合）
        text = _RE_STAR_CLOSE_PAREN_BOOK.sub(r"**\1（\2）【\3】", text)
        # 【书缩写】全星包裹剥除（`【**SH**】`/`【****SH****】` → `【SH】`，
        # _RE_BOOK_INNER_STAR 只剥尾残星；page_151 Persuasive Insight/隐密
        # 信仰 src 星壳残留同根因）。须在 _RE_STAR_CLOSE_PAREN_BOOK 后——
        # 其输入 `**中文**（EN）【**SH****】**` 依赖【】内残星形态
        text = _RE_BOOK_FULL_STAR.sub(r"【\1】", text)
        # 行首纯英文名标题补开星（page_151 Kalistocratic Prophecy：删除线
        # 壳剥除后无开星 `（EN）【书】**：` → `**（EN）【书】**：`，供 split
        # 纯英文名标题分支）。后接闭星+冒号限定（正文行内 `（EN）【X】**：`
        # 罕见，防正文行误补）
        text = _RE_LINE_LEAD_EN_PAREN.sub(r"**（\1）\2**：", text)
        # 半星壳+星壳外括号+冒号正文（page_1579 信手拈来）→ 单星壳，组6 接正文
        text = _RE_HALF_PAREN_COLON.sub(r"**\1（\2）**\3\4", text)
        # 星壳标题冒号在壳内（`**A（EN）：**` → `**A（EN）**：`；
        # 双括号形态 `**A（区域）（EN，EN）:**` 先并回单星壳再走同上归一）
        text = _RE_DUAL_PAREN_COLON.sub(r"**\1（\2）**：", text)
        text = _RE_STAR_PAREN_COLON.sub(r"**\1**：", text)
        # 星壳中文名+裸英文名归一（行尾/冒号正文两变体，PIS/矮人/DA 链接锚）
        text = _RE_STAR_BARE_EN_TRAIL.sub(r"**\1（\2）**", text)
        text = _RE_STAR_BARE_EN_COLON.sub(r"**\1（\2）**：\3", text)
        # 星壳+PFS 尾缀（`**A(EN)PFS可**` → `**【PFS】A（EN）**`）——前置【】后
        # 不加中间星：_RE_TITLE_STAR 组1 前置形态是 `**【地区】中文（EN）**`
        #（组2 字符类 `[^（(\n*]` 排除 `*`，中间星会使组2 无法越过【】后星）
        text = _RE_STAR_PFS_TRAIL.sub(r"**【PFS】\1（\2）**", text)
        # 星壳+裸英文+残星+出处同行（瓦瑞西亚/StLC）→ 标题 + 独立出自行
        text = _RE_STAR_BARE_EN_SRC.sub(r"**\1（\2）**\n\3\4", text)
        # 裸行中文名+英文名+冒号正文（矮人）→ 补星壳
        text = _RE_BARE_CN_EN_COLON.sub(r"**\1（\2）**：\3", text)
        # EOD 断行字段标签分裂（须在四星归一后，防 `**分类\n**值` 干扰嵌套剥皮）
        text = _RE_SPLIT_FIELD_LABEL.sub(r"**\1**：", text)
        # 补录段标题尾部四星冒号：`【WMH】****：**正文` → `**：正文`
        text = _RE_TITLE_TAIL_QUAD_COLON.sub("**：", text)
        # 壳外【书】并入壳内（须在四星冒号归一后，处理 `**：` 已定型形态）
        text = _RE_OUTER_BOOK_GLUE.sub(r"\1\2**：", text)
        # 行尾【书】+单残星补闭星（`**中文（EN，地点）**【书】*` → `**【书】**`，
        # page_156 猎魔人；四星归一后残尾形态，放链尾最终定型处）
        text = _RE_TRAIL_SINGLE_STAR_BOOK.sub(r"**\1\2**", text)
        # StLC 字段标签内星壳 `**类型：**值` → `**类型**：值`
        text = _RE_LABEL_COLON_INNER_STAR.sub(r"**\1**：", text)
        # 标签闭合星后残留星剥除（KN083 同型 `**效果：**** 正文`）
        text = _fix_label_trailing_star(text)
        # 字段星残缺补全（`**值**标签：**` → 拆行；`标签**：` → `**标签**：`）
        text = _fix_field_star_right(text)
        text = _fix_field_star_left(text)
        # 星壳残留收口（`Devil****’****s`、`凯登****·****凯连`、尾部空壳）
        text = _fix_star_shell_remnants(text)
        # 闭合星 + 同行出处拆行（`**…** 出自…` → 独立出处行）
        text = _split_closed_title_source(text)
        # 四壳括号左残留归一（page_158 污染之魂 `（****X)`，须在四星归一后）
        text = _RE_QUAD_PAREN_LEFT.sub(r"（\1）", text)
        # 括号开头 2 星残留剥除（page_152 孔冉达 `（**X）【书】**`——四星归一
        # 后 `（****X` 已归 `（X`，`（**X` 双星残留在 _RE_QUAD_PAREN_LEFT 后
        # 才剥；须在四壳归一全部完成后（`（****` 形态防误剥）
        text = _RE_PAREN_LEAD_STAR.sub("（", text)
        # 斜杠双译名+无括号英文名（page_158 奥术恶性状态）→ 标准星壳
        text = _RE_SLASH_DUAL_EN.sub(r"**\1（\2）**", text)
        # 跨行无闭合星壳+星壳出处行合并（page_158 急躁），再统一拆行
        text = _RE_UNCLOSED_TITLE_TRAILER.sub(r"\1\2", text)
        # 未闭合星壳标题+下一行四星字段（典范背景 3 条全灭根因）：源数据转换
        # 产物——标题闭星壳与字段开星壳在换行两侧粘连成 `）\n****字段**：`，
        # `_RE_TITLE_STAR` 匹配失败整条丢失。补标题闭星、剥弃星还原字段行
        #（组1 标题 + `**` 闭合 + 组2 字段行）。标题行要求 `（…）` 结尾且
        # 壳内无星（防字段行 `**类型**：` 与正文加粗误配）。
        text = _RE_QUAD_NEXT_FIELD.sub(r"\1**\n\2", text)
        # TEoG 跨行括号条目（中文（神/种族） EN + 换行 + (EN)正文）→ 单行
        text = _RE_TEOG_PAREN_CROSS_LINE.sub(r"\1 \2", text)
        # 矮人半星壳（`**浴血者Blooded` 无闭星）→ 剥前导星（须在跨行合并前）
        text = _RE_STAR_HALF_CN_EN.sub(r"\1\2", text)
        # 矮人无星/半星壳跨行（中文EN + 换行 + （地区）：正文）→ 单行
        text = _RE_CROSS_LINE_EN_PAREN.sub(r"\1\2\3", text)
        # 矮人星壳中文+星壳英文（`**大地的加护**Deep Guardian**：`）→
        # 标准星壳标题（_RE_TITLE_STAR 复用）
        text = _RE_STAR_CN_STAR_EN.sub(r"**\1（\2）**：\3", text)
        # 矮人括号错位（`（波络卡**Bolka）` → `（波络卡）Bolka`）恢复
        # _RE_FLOW 可匹配形态（deity 提取）；顺带冒号去重（`：：` 源数据残留）
        text = _RE_PAREN_STAR_EN.sub(r"（\1）\2", text)
        text = re.sub(r"([：:])\1+", r"\1", text)
        # 星壳标题+同行中文译名行尾（StLC 跨界魔法）——补冒号防标题吞并
        text = _RE_STAR_TRAIL_CN.sub(r"\1：\2", text)
        # 半星壳+同行出处拆行（page_158 缺陷补录，无「出自」前缀；
        # 组2 含 `出自《…》` 变体——ACO 狮子的勇气无页数形态）：
        # `**X（EN）**《书》 第N页` / `**X（EN）**Spymaster's Handbook` / `**X（EN）** 出自《…》`
        # → 标题独立 + 出处行
        # ⚠️ 闭合星在组外（空格容差），sub 必须补回 `**`
        text = _RE_HALF_TITLE_TRAILER.sub(r"\1**\n\2", text)
        # 星壳标题+同行中文正文无冒号（page_155 魔染裔/主宰范 CEoD 段 2 条，
        # KN138 家族）：`**A（EN）【书】**正文` → 拆行。_RE_TITLE_STAR 闭星后
        # 只接行尾或冒号（`\*\*(?:[：:](.*))?$`），同行正文失配整条目丢失。
        # 组5 前置必选【书】——正文粗体强调 `**技能（X）**` 无【书】不拆
        #（全库扫描「星壳+括号+【书】+闭星+同行中文」仅此 2 形态）
        text = _RE_TITLE_BODY_SPLIT.sub(r"**\1（\2）【\3】**\n", text)
        # 行首星壳书缩写粘回（page_152 四壳变体 12 条：`**法理通（****
        # Magical Knack****）****【APG】**：` 公共层 _RE_BOLD_GLUE_SPLIT（KN070）
        # 把 `）****【` 4 星粘连拆行 → 【APG】落行首星壳，split 标题分支组5
        # 失配 source 空 → book 未知）。匹配 `**\n**` 段（前一标题闭星+行
        # 首开星）一并消掉 → `（EN）【X】**` 标准形态。后接冒号限定（正文
        # 行内【】/B1_marker 前置类型不受影响）。链尾执行——拆行后形态稳定
        _RE_LINE_LEAD_BOOK_GLUE = re.compile(r"\*\*\n\*\*【([^】\n]{1,12}?)】\*\*(?=[：:])")
        text = _RE_LINE_LEAD_BOOK_GLUE.sub(r"【\1】**", text)
        # 标题空白归一（`Freed  Slave` 双空格 / `( Lion’s` 前导空格）
        text = _normalize_whitespace_title(text)
        return text

    def normalize(self, text: str) -> str:
        return self._normalize_custom(text)

    def promote(self, text: str) -> str:
        return text

    # ------------------------------------------------------------------
    # split：判定链
    # ------------------------------------------------------------------

    @staticmethod
    def _new_item(
        name: str = "", name_en: str = "", trait_types: list[str] | None = None
    ) -> dict:
        return {
            "name": name,
            "name_en": name_en,
            "trait_type": list(dict.fromkeys(trait_types or [])),
            "requirement": "",
            "deity": "",
            "source": "",
            "pfs_eligible": False,
            "flaw": False,
            "format_cluster": "standard",
            "text": "",
        }

    def _stamp_item(self, section_type: str, *args, **kwargs) -> dict:
        """创建条目并打章节标记行段落级类型戳（_trait_type_from_marker）。

        章节分类标记行（TEoG 地区背景/精灵 Racial Traits/矮人 **魔法背景：）
        之后的条目继承该段类型，processor 层归一后为空时兜底（R3-B 同机制）。
        section_type 为空（文件头 intro 段）不戳。
        背景特性17 HH 补录段（split 遇 HH-segment 哨兵行置位）条目另打
        _hh_section 戳：processor 层 R2 页面级默认跳过 HH 段条目（方案 R3）。
        """
        item = TraitFormat._new_item(*args, **kwargs)
        if getattr(self, "_hh_section", False):
            item["_hh_section"] = True
        if section_type:
            item["_trait_type_from_marker"] = section_type
        return item

    def _is_chapter_title(self, name: str, name_en: str) -> bool:
        """章节标题判据：分类名 `**X背景（X Traits）**`（无冒号无【书】形态）。"""
        return (name.endswith("背景") or name_en.rstrip("*").endswith("Traits"))

    def split_into_items(
        self, text: str, *, source_name: str | None = None
    ) -> list[dict]:
        items: list[dict] = []
        cur: dict | None = None
        pending_field: str | None = None  # 字段无冒号标签，值在下一行
        lines = text.splitlines()
        # C_flaw 缺陷文件（page_158）：星壳标题条目均为缺陷条目（勘探确认
        # 缺陷页条目无【书】无类型字段，形态与普通 trait 同构，靠文件判定）
        is_flaw_file = bool(source_name and "page_158" in source_name)
        # 段落级 trait_type 标记（章节分类标记行 → 后续条目继承，processor
        # 层归一后为空时兜底；None = 文件头 intro 段不戳）
        section_type: str | None = None
        # 背景特性17 HH 补录段标记（遇 `<!-- HH-segment -->` 哨兵行置位，
        # _stamp_item 打 _hh_section 戳）。实例属性（split 跨文件复用），
        # 每文件 split 开头重置防残留。
        self._hh_section = False

        def merge_title(name: str, name_en: str) -> bool:
            """三重标题合并：连续标题行同 name 且当前无正文 → 复用条目补 name_en。"""
            nonlocal cur
            if cur is not None and cur.get("name") == name and not cur.get("text"):
                if name_en and not cur.get("name_en"):
                    cur["name_en"] = name_en
                return True
            return False

        for idx, line in enumerate(lines):
            line = line.strip()
            if not line:
                # 字段无冒号标签的值与下一字段间有空行 → 丢弃待定
                pending_field = None
                continue

            # 0. HH 段哨兵行（_normalize_custom 由 HH-source 注释保留）：标记
            # 背景特性17 补录段起点。仅原内容段 → HH 段首次进入时重置
            # section_type（HH 段独立区域，不继承原内容段标记状态）；段内
            # 哨兵（每条 HH 条目前各有一行）保留标记行状态——「信念背景」等
            # 标记行作用域覆盖其后所有 HH 条目直到下一标记行（方案 R3-B）。
            if line.startswith("<!-- HH-segment"):
                if not self._hh_section:
                    section_type = None
                self._hh_section = True
                continue

            # 1. PFS 禁用说明行（page_158）：不产条目
            if _RE_PFS_DISABLED.match(line):
                continue
            # 坐骑背景：`【PFS】**…**` 前缀 → pfs_eligible=True，剥前缀继续判定
            pfs_prefix = False
            if line.startswith("【PFS】"):
                pfs_prefix = True
                line = line[len("【PFS】") :].strip()

            # 2. 表格（背景特性17 星座表）：表头/分隔行跳过，条目行产条目
            if line.startswith("|"):
                if line.startswith("| d%") or line.startswith("| ---") or re.match(r"^\| *:?-+", line):
                    continue
                m = _RE_TABLE_ENTRY.match(line)
                if m:
                    item = self._stamp_item(section_type, m.group(1).strip(), m.group(2).strip())
                    item["format_cluster"] = "D_exalted_mount_cosmic"
                    item["text"] = m.group(3).strip() + "\n"
                    items.append(item)
                    cur = item
                continue

            # 2b. 章节分类标记行（段落级 trait_type 戳）：裸文本（TEoG
            # `地区背景（塔尔多）…`/`宗教背景…`/精灵 `种族背景`）、英文行
            # （精灵 `Racial Traits`/`Religious Traits 信仰背景（…）`，跨行
            # 英文已由 _RE_BARE_EN_JOIN 合并）、星壳（矮人 `**矮人的地区背景`/
            # `**魔法背景：`）——不产条目仅更新 section_type，后续条目继承。
            # 须在 _RE_TITLE_STAR 之前（星壳带冒号形态 `**魔法背景：` 会被
            # 星壳标题分支误判）；标记行同行引导句（`这些背景可以…`）吞弃。
            mc = _SECTION_MARKER_CN.match(line)
            if mc:
                section_type = mc.group(1)
                continue
            ms = _SECTION_MARKER_EN.match(line)
            if ms:
                section_type = _EN_TO_CN_SECTION.get(ms.group(1))
                continue

            # 3. 星壳标题（A 族四壳归一后 / PotR 型 / 补录段 / B1_marker【类型】前置）
            m = _RE_TITLE_STAR.match(line)
            if m:
                name = m.group(2).strip()
                # 括号语义漂移：组3 含英文字母 = 英文名；纯中文 = 类型词
                # （词表判定，地名/神名丢弃——安多安/终焉之墙）；组4 为第
                # 二括号：含英文 = 英文名（ISP 解放奴 [Andoran] 超长形态），
                # 纯中文类型词 → 类型；组4 神祇括号（page_157 `中文，EN` /
                # 纯英文神名）→ deity（双英文段时组3 是英文名，组4 不覆盖）
                paren = m.group(3).strip()
                extra = (m.group(4) or "").strip()
                deity = ""
                if re.search(r"[A-Za-z]", paren):
                    name_en = paren
                    trait_types = []
                    if extra and re.search(r"[A-Za-z]", extra):
                        # 神祇括号：`卡莉斯翠，Calistria`（中文，EN）或纯英文神名
                        m_d = re.match(
                            r"^([一-鿿]{1,8})(?:[，,]\s*|\s+)([A-Za-z][A-Za-z ’'’-]{0,40})$", extra
                        )
                        deity = m_d.group(1) if m_d else extra
                    elif extra and (v := _strip_basic_trait(extra)) and _is_trait_type_paren(v):
                        trait_types.append(v)
                else:
                    name_en = ""
                    trait_types = (
                        [v] if (v := _strip_basic_trait(paren)) and _is_trait_type_paren(v) else []
                    )
                    if extra:
                        if re.search(r"[A-Za-z]", extra):
                            # 中文逗号归一（狗头人 `（Briar Bandit ，forest）`——源
                            # 数据 EN 内用中文逗号），不影响神祇括号（走 deity 分支）
                            name_en = re.sub(r"\s*[，,]\s*", ", ", extra)
                        elif (v := _strip_basic_trait(extra)) and _is_trait_type_paren(v):
                            trait_types.append(v)
                # 阵营尾缀剥离（page_157 神祇括号并存：`英文名，混乱中立`）
                name_en = re.sub(
                    r"[，,]\s*(混乱中立|绝对中立|守序中立|中立善良|守序善良|"
                    r"混乱善良|中立邪恶|守序邪恶|混乱邪恶|绝对善良|绝对邪恶)\s*$",
                    "", name_en,
                )
                # 【】后缀：类型词 → trait_type；书缩写 → source
                tag = (m.group(5) or "").strip()
                tag_src = ""
                if tag and tag in _TRAIT_TYPE_WORDS:
                    trait_types.append(tag)
                elif tag:
                    tag_src = tag
                # 【】前置（B1_marker 秽邪勇士）；PFS 前缀（坐骑背景）→
                # pfs_eligible 标记而非类型
                pre = (m.group(1) or "").strip()
                if pre:
                    if pre == "PFS":
                        pfs_prefix = True
                    elif (v := _strip_basic_trait(pre)) and _is_trait_type_paren(v):
                        trait_types.append(v)
                # 章节标题排除：无冒号无【书】无正文，仅当分类名特征才排除
                # （`**X背景（X Traits）**` 星壳标题；正文 m.group(6)/【书】tag_src
                # 是条目标题证据放行）。⚠️ 2026-08-05 产出即检：原「下一行非
                # 字段非出自行」分句误杀 139 处真实条目（KIS 自由/秽邪勇士
                # 切利亚斯/侏儒急性子/page_158 缺陷条目——星壳标题+空行/正文
                # 形态），移除后仅分类名特征排除（全库扫描确认章节标题均以
                # 背景/Traits 结尾可捕获）
                if not (m.group(6) or line.endswith("**：") or tag_src):
                    if self._is_chapter_title(name, paren):
                        continue
                if merge_title(name, name_en):
                    continue
                item = self._stamp_item(section_type, name, name_en, trait_types)
                if deity:
                    item["deity"] = deity
                if tag_src:
                    item["source"] = tag_src
                if is_flaw_file:
                    item["flaw"] = True
                    item["format_cluster"] = "C_flaw"
                else:
                    item["format_cluster"] = (
                        "A_basic_page" if not tag_src and not pre else "B1_marker"
                    )
                if pfs_prefix:
                    item["pfs_eligible"] = True
                if m.group(6):
                    item["text"] = m.group(6).strip() + "\n"
                items.append(item)
                cur = item
                continue

            # 3a. 纯英文名标题（无中文名，page_151 Persuasive Insight /
            # Kalistocratic Prophecy，est 预测「解析器需兜底」）：`**（EN）
            # 【书】**：正文` —— _RE_TITLE_STAR 组1 非括号字符开头失配。
            # name=EN（无中文名条目 title 即英文）、name_en 留空、【书】→
            # source（归一后【】内已无星）
            m = _RE_EN_ONLY_TITLE.match(line)
            if m:
                name = m.group(1).strip()
                tag_src = (m.group(2) or "").strip()
                if merge_title(name, ""):
                    continue
                item = self._stamp_item(section_type, name, "")
                if tag_src:
                    item["source"] = tag_src
                if is_flaw_file:
                    item["flaw"] = True
                    item["format_cluster"] = "C_flaw"
                else:
                    item["format_cluster"] = "B1_marker" if tag_src else "A_basic_page"
                if pfs_prefix:
                    item["pfs_eligible"] = True
                if m.group(3):
                    item["text"] = m.group(3).strip() + "\n"
                items.append(item)
                cur = item
                continue

            # 3b. 中文裸开头+星壳英文（精灵 `神奇把戏**Arcane Dabbler**：正文`
            # / 矮人 `紧贴大地**Earthbound**：正文`；组1 容英文前缀——
            # `Sovyrian的泛神论**Sovyrian Pantheist**`）。括号语义同
            # _RE_TITLE_STAR（类型词→trait_type，其余丢弃不臆造——防
            # 「任何无精灵之地」类地名误填 deity，KN 口径不扩大）
            m = _RE_CN_STAR_EN.match(line)
            if m:
                name = m.group(1).strip()
                name_en = m.group(2).strip()
                trait_types = []
                paren = (m.group(3) or "").strip()
                if paren and (v := _strip_basic_trait(paren)) and _is_trait_type_paren(v):
                    trait_types.append(v)
                if merge_title(name, name_en):
                    continue
                item = self._stamp_item(section_type, name, name_en, trait_types)
                item["format_cluster"] = "B3_flow_bare"
                if pfs_prefix:
                    item["pfs_eligible"] = True
                if m.group(4):
                    item["text"] = m.group(4).strip() + "\n"
                items.append(item)
                cur = item
                continue

            # 4. 半星壳标题（EOD `**速饮者**(Accelerated Drinker) 出自《…》`）
            m = _RE_TITLE_HALF.match(line)
            if m:
                name = m.group(1).strip()
                name_en = m.group(2).strip()
                if merge_title(name, name_en):
                    continue
                item = self._stamp_item(section_type, name, name_en)
                src = m.group(3)
                if src:
                    item["source"] = src.strip()
                item["format_cluster"] = "B1_star_field"
                if pfs_prefix:
                    item["pfs_eligible"] = True
                items.append(item)
                cur = item
                continue

            # 5. H2 标题（B2_standard_h2 / FM 三重标题）
            m = _RE_H2.match(line)
            if m:
                h = m.group(1).strip()
                hm = re.match(r"^([^（(]+?)(?:[（(]([^）)]+)[）)])?$", h)
                name = hm.group(1).strip() if hm else h
                name_en = hm.group(2).strip() if hm and hm.group(2) else ""
                # 文件头/章节标题排除：无括号 H2 且（含「背景」字样——文件
                # 头 `## 内海诸神 ISG 背景特性`/`## 制药与用毒背景`——或
                # 下一行为引用块——章节标题 `## 巫术的证明`）→ 非条目
                # （真条目 H2 均有括号；三重标题「前奴隶」无括号但下一行
                # 为 H2 合并标题而非引用块，不受影响）
                if not name_en and (
                    "背景" in name
                    or (idx + 1 < len(lines) and lines[idx + 1].lstrip().startswith(">"))
                ):
                    continue
                if merge_title(name, name_en):
                    continue
                item = self._stamp_item(section_type, name, name_en)
                item["format_cluster"] = "B2_standard_h2"
                items.append(item)
                cur = item
                continue

            # 6. 流式裸名（B3_flow_bare / ACO 裸文本 / P&P 段内粘连）
            m = _RE_FLOW.match(line)
            if m:
                name = m.group(1).strip()
                name_en = m.group(2).strip()
                if merge_title(name, name_en):
                    continue
                item = self._stamp_item(section_type, name, name_en)
                # 括号语义：顶层顿号拆分后逐段判定——类型词 → trait_type；
                # 否则 → deity（ISG 神名为主场景；「地区，世界之冠」拆后
                # 世界之冠非类型词丢弃）
                paren = m.group(3).strip()
                parts = _split_top_level(paren)
                types = [
                    v for p in parts if (v := _strip_basic_trait(p)) and _is_trait_type_paren(v)
                ]
                if types:
                    item["trait_type"].extend(types)
                elif re.search(r"[A-Za-z]", paren):
                    # 英文括号=地名（矮人 `(Mindspin Mountains)`/`(Lands of the
                    # Linnorm Kings)`），非神祇——丢弃不进 deity（2026-08-06）
                    pass
                else:
                    item["deity"] = paren
                item["format_cluster"] = "B3_flow_bare"
                if pfs_prefix:
                    item["pfs_eligible"] = True
                if m.group(4):
                    item["text"] = m.group(4).strip() + "\n"
                items.append(item)
                cur = item
                continue

            # 6b. 中文名+空格+英文名+中文正文粘连（TEoG 骑士精神，无冒号无括号）
            m = _RE_TEOG_GLUE.match(line)
            if m:
                item = self._stamp_item(section_type, m.group(1).strip(), m.group(2).strip())
                item["format_cluster"] = "B3_flow_bare"
                if pfs_prefix:
                    item["pfs_eligible"] = True
                item["text"] = m.group(3).strip() + "\n"
                items.append(item)
                cur = item
                continue

            # 6c. 中文+中文括号+英文名+可选英文括号（TEoG `调和者（莎伦莱）
            # Ambassador (Sarenrae)正文`，跨行已由 _RE_TEOG_PAREN_CROSS_LINE
            # 合并）——组2 中文括号：类型词→trait_type、种族词（人类——塔尔
            # 多人/半兽人/矮人）→ 丢弃、其余→deity（双括号结构对称，中文括号
            # 必为神名——莎伦莱/奥罗登/艾奥梅黛）；组4 英文括号丢弃
            m = _RE_TEOG_PAREN.match(line)
            if m:
                name = m.group(1).strip()
                name_en = m.group(3).strip()
                trait_types = []
                deity = ""
                paren = m.group(2).strip()
                if (v := _strip_basic_trait(paren)) and _is_trait_type_paren(v):
                    trait_types.append(v)
                elif not _RE_NON_DEITY_CN.match(paren):
                    deity = paren
                if merge_title(name, name_en):
                    continue
                item = self._stamp_item(section_type, name, name_en, trait_types)
                if deity:
                    item["deity"] = deity
                item["format_cluster"] = "B3_flow_bare"
                if pfs_prefix:
                    item["pfs_eligible"] = True
                if m.group(5):
                    item["text"] = m.group(5).strip() + "\n"
                items.append(item)
                cur = item
                continue

            # 6d. 裸行标题（WO/PotN 中文EN / DA 中文（EN））——下一行是字段行才产条目
            m = _RE_BARE_TITLE.match(line)
            if m:
                # 「出自/来源」开头的裸行是条目出自行（任务与战役跨行出处
                # `出自《任务与战役》 Quests and\nCampaigns` 归一后单行），
                # 非条目名——不产条目，落入第 8 分支 SOURCE_LINE 并入当前条目
                # （产出即检：曾把该行切伪条目「出自《任务与战役》」，吞并
                # 纵火狂/乐观心/耐心沉着 3 条效果正文，真条目 text 空）
                name_bare = (m.group(1) if m.group(2) else m.group(3)) or ""
                is_source_line = name_bare.startswith(("出自", "来源"))
                nxt = lines[idx + 1].strip() if idx + 1 < len(lines) else ""
                nxt_field = (
                    _RE_FIELD.match(nxt)
                    or _RE_SOURCE_LINE.match(nxt)
                    or _RE_PFS_DISABLED.match(nxt)
                )
                if nxt_field and not is_source_line:
                    if m.group(2):
                        name, name_en = m.group(1).strip(), m.group(2).strip()
                    else:
                        name, name_en = m.group(3).strip(), m.group(4).strip()
                    item = self._stamp_item(section_type, name, name_en)
                    item["format_cluster"] = "B1_star_field"
                    if pfs_prefix:
                        item["pfs_eligible"] = True
                    items.append(item)
                    cur = item
                    continue
                # 无字段跟随 → 非条目（DA 地名/名词解释），落入正文分支

            # 7. 字段行（标准冒号 / 标签内星壳 / 裸文本 / 无冒号值同行）
            m = _RE_FIELD.match(line)
            if m:
                label, value = m.group(1), m.group(2).strip()
                semantic = _FIELD_SEMANTIC[label]
                if cur is None:
                    # 无标题字段行：仅「效果」开新缺陷条目（page_158 C_flaw）
                    if semantic != "effect":
                        continue
                    cur = self._stamp_item(section_type, )
                    cur["flaw"] = True
                    cur["format_cluster"] = "C_flaw"
                    items.append(cur)
                if semantic == "trait_type":
                    # 顶层顿号拆分：括号内分隔符不拆（`种族背景（半精灵、半兽人或人类）`）；
                    # 基础（X）剥壳并入对应类型（人工门 1 拍板）
                    for v in _split_top_level(value):
                        if v:
                            cur["trait_type"].append(_strip_basic_trait(v))
                elif semantic == "requirement":
                    cur["requirement"] = value
                elif semantic == "effect":
                    cur["text"] += value + "\n"
                elif semantic == "source":
                    cur["source"] = value
                # 值空且行内无冒号 → 待定字段（值在下一行，B4_field_no_colon）
                if not value and "：" not in line and ":" not in line:
                    pending_field = semantic
                else:
                    pending_field = None
                continue

            # 7b. 星壳无括号纯行 skip（BotA 引导句）——须在字段行分支后：
            # `**分类**`/`**需求**`（字段标签无冒号值下一行）已由 _RE_FIELD
            # 处理进 pending_field，此处只拦星壳引导句/强调行（`**以下…角色**`），
            # 归一后条目必有括号（_RE_TITLE_STAR），纯星壳行非条目——不产
            # 条目不并入正文（防 split 正文分支当章节介绍产 intro 空条目）
            m = _RE_BARE_STAR_SHELL.match(line)
            if m:
                continue

            # 8. 出自行独立行（`出自《…》` / StLC 星壳 / `来源 …` / page_158 拆行形态）
            m = _RE_SOURCE_LINE.match(line)
            if m:
                src = next((g for g in m.groups() if g), "")
                if src and cur is not None:
                    # 剥全角空格（page_158 拆行残留 `　　`）+ ASCII 空白
                    cur["source"] = re.sub(r"[　\s]+$", "", src.strip())
                continue

            # 9. 正文行：并入当前条目；无当前条目 → 章节介绍段（intro）
            # 引用块（`> 来源：…`）：文件级来源标记（全库抽查确认无条目
            # 级引用），不并入正文、不产条目
            if line.startswith(">"):
                continue
            # 名词解释段（`旋舞修士 Whirling Dervishes:…` 无括号裸名）整段跳过
            if _RE_GLOSSARY.match(line):
                continue
            if pending_field is not None and cur is not None:
                # 字段无冒号的值在下一行（B4_field_no_colon 值行）
                if pending_field == "trait_type":
                    cur["trait_type"].append(line)
                elif pending_field == "requirement":
                    cur["requirement"] = line
                elif pending_field == "effect":
                    cur["text"] += line + "\n"
                pending_field = None
                continue
            if cur is None:
                cur = self._stamp_item(section_type, )
                cur["format_cluster"] = "intro"
                items.append(cur)
            cur["text"] += line + "\n"

        return items
