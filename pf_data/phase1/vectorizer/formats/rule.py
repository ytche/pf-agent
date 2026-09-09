"""formats/rule.py — 规则格式切分器（章节型新形态，S1~S5 分派）

形态家族（B2~B4 核心规则勘察 2026-08-09 + TDD seeds 16 条）：
  S1 heading 树（战斗规则 9 rpages + page_235/236/313/408）：
    `####`/`###`/`#####`/`######` 标题 = 节边界，标题即 chunk title
    （est 口径：全层级计数，H4+H5+H6 每标题 1 节）
  S2 行首加粗标题（环境 7 页 + page_127）：
    `**中文（English）**` / `**中文 (English)**: `（半角括号/壳外冒号）=
    节边界；纯中文标签 `**低可见度**：`（标签 ∉ 字段词表）也是节边界
  S3 BBS 星壳（page_239/240/242/243/413）：
    `**中文（****EN****）**：` 嵌套 4 星壳 = 节边界；`l  ` 残渣行剥除
    且下一标题行并入所属节（移动方式子条目）；苦难字段行
    `**名称**：`（标签 ∈ RULE_FIELD_LABELS 词表）并入所属节（KN102
    字段行伪条目教训）
  S5 prose（page_130）：无边界整篇 1 chunk

章节型形态（M2 §一）：chunk 单元 = 语义节，无字段体系。内嵌词条块字段行
留在 text 原文不提取；正文中的表跟随所属节（不独立成 chunk）。

format_cluster 推导（首边界形态，processor 层以 per_file.jsonl
format_cluster_hint 显式覆盖——KN192 manifest 注解精神）。
"""

import re
from typing import Dict, List, Optional

from vectorizer.formats.base import BaseFormat
from vectorizer.formats.normalize_common import (
    _RE_STRIKE_SHELL, _merge_cross_line_en)
from vectorizer.registry_rule import RULE_FIELD_LABELS, RULE_FIELD_LABELS_S6

# ---- 行锚与剥除（须在 CR 归一后运行，行锚依赖换行结构）----

# URL+译者同行行（含 `### ` 前缀形态）：`[URL](URL) 译者:X` /
# `### [URL](URL) 译者:Falengel`——整行剥除（URL 与译者同源页头行）
_RE_URL_HEAD_LINE = re.compile(
    r"^[ \t]*#{0,6}[ \t]*\[https?://[^\]]*\]\(https?://[^)]*\)[^\n]*$", re.M)
# 多段星壳译者行：`**译者：****Falengel****，****pandora******`（闭壳
# 6 星形态，`\*{2,}` 兼容——公共层 `_strip_translator_notes` 的 `\*\*`
# 闭壳匹配不了 6 星尾壳，此处补剥）；`\*{0,2}` 兼容闭壳字段形态
# `**译者**：**四月******`（page_517/601：标签闭壳 + 冒号 + 值壳——
# 原正则要求 `译者` 后直接冒号，闭壳星在冒号前 → 全不匹配，M5 修复）
_RE_TRANSLATOR_STAR_LINE = re.compile(
    r"^\s*\*\*译者\*{0,2}[：:][^*\n]*(?:\*{1,4}[^*\n]+)*\*{2,}\s*$", re.M)
# 开星不闭译者行：`**译者：旅法师 `（page_646：跨行闭壳 `紫渊**` 在下行，
# 行尾无星 → 星壳正则不匹配）→ 整行剥除，闭壳残行并入所属节
_RE_TRANSLATOR_BARE_LINE = re.compile(r"^\s*\*\*译者[：:][^\n]*$", re.M)
# 孤立链接残渣行：`](http://...)` / `**](http://...)`（`[文本](url)` 源行
# 文本部分被剥后残留——`\*{0,4}` 兼容星壳前缀，page_322 标题残渣）→ 整行剥除
_RE_ORPHAN_URL_TAIL = re.compile(
    r"^[ \t]*\*{0,4}[ \t]*\]\([^)\n]*\)[ \t]*\n?", re.M)

# ---- 标题行形态 ----

_RE_H_HEADING = re.compile(r"^#{1,6}[ \t]+")            # H1~H6 标题
_RE_STAR_TITLE = re.compile(r"^[ \t]*\*\*")             # 行首星壳（含嵌套）
# 字段行：`**标签**：` / `**标签** `（尾空格+值换行）/ `**标签** 值` /
# `**标签：**值`（冒号在闭壳前，S6 原文地址行）/ `**标签**值`（闭壳后
# 紧贴值）且标签 ∈ 词表（苦难字段行 page_240 + S6 stat block 字段，
# KN102；M4 放宽：闭壳前可选冒号 + 闭壳后任意，词表锚定防误判）
_RE_FIELD_LINE = re.compile(r"^[ \t]*\*\*([^*：:\n]+?)(?:[：:])?\*\*")
# 行尾括号英文后缀（KN215 作祟 stat 字段注音形态）：`挑战等级（CR）` →
# 剥 `（CR）` 后词表判定；只匹配行尾（真标题 `孤寂Isolation` 无括号、
# `恶魔领主（Demon Lords）` 剥后「恶魔领主」不在词表 → 不受影响）
_RE_EN_PAREN_SUFFIX = re.compile(r"[（(][A-Za-z][^）)\n]{0,30}[）)]$")
# 开壳不闭字段行（KN215/216）：`**效果 ` / `**基础 `——行首 `**` + 标签
# + 空白到行尾（无闭壳、行内无其他星）。判定层专用：不改写文本（全局
# 补闭壳会破坏跨行名字行/表格行拼接的原文形态）
_RE_FIELD_LINE_OPEN = re.compile(r"^\*\*([^*：:\n]+?)[ \t]*$")
# l 残渣行：`l  `（page_239 列表项转换残渣，独立成行）
_RE_L_ARTIFACT = re.compile(r"^l[ \t]*$")
# 表标题行：`| 表：召唤怪物 |`（markdown 表格首行即标题行，page_400 整页
# 纯表形态——文件首行即表标题时建节，普通文件表标题行仍并入所属节）
_RE_TABLE_TITLE = re.compile(r"^\|\s*表[：:][^|\n]*\|?\s*$")
# 嵌套 4 星对：`（****X****）` → `（X）`（S3 嵌套壳）
_RE_NESTED_STAR = re.compile(r"\*{4}([^*\n]+?)\*{4}")
# 4+ 星连排碎片（KN212，normalize 第 7 步）：BBS `[b]` 嵌套转换残渣
# `\*{4,}` = 加粗壳边界粘连 + 残留，直接剥除（`**重训（****Retraining****）******`
# → `**重训（Retraining）**`）；干净 2 星加粗 / 单星斜体不在剥除范围
_RE_STAR_FRAGMENT = re.compile(r"\*{4,}")
# markdown 链接剥壳（_extract_title 内，M5）：`![[图片]](url)` → 图片
# （page_1490 图片行）；`[文本](url)` → 文本（page_314 BBS 链接标题）
_RE_IMG_LINK = re.compile(r"!\[\[([^\]\n]*?)\]\]\([^)\n]*\)")
_RE_MD_LINK = re.compile(r"\[([^\]\n]*?)\]\([^)\n]*\)")

# ---- S6 超大型聚合专用（M4，2026-08-09 形态勘察定稿）----

# `****` 纯星分隔线（LotFW 87 / 废土 63 / 神恩 4 处装饰线——被 `^\*\*`
# 误判为节边界 → 空 title 碎片根因，剥除不产生节）
# re.M：整文本 sub 时 `$` 需匹配每行行尾（S6 骨架逐行 match 不受影响）
_RE_PURE_STARS = re.compile(r"^\*{2,}[ \t]*$", re.M)
# BBS 跨行加粗壳：`**  `（行首 2 星 + 纯空白 + 换行，壳行本身无内容）与
# 下一行拼接为 `**下一行内容`——BBS 帖「标签加粗换行」形态（page_159/
# page_591 空 title 根因）。⚠️ 只匹配 2 星：`****\n正文` 形态（创造世界/
# page_739）由 _RE_PURE_STARS 剥除（4 星纯行 = 分隔线，正文行自然并入
# 所属节；拼接会破坏 S6 骨架的 `****` 分隔剥除/at_separator 逻辑）
_RE_BBS_BOLD_SHELL = re.compile(r"^\*\*[ \t]*\n+", re.M)
# 来源注释锚点 `<!-- X-source -->`（永罪之书×5 条目边界，BOTD-source）
_RE_ANCHOR_COMMENT = re.compile(r"^\s*<!--\s*[^>]*?-->")
# 4 星引用注行 `****（该作祟翻译引自…）**`（作祟跨行引用注，并入所属节）
_RE_QUAD_STAR_REF = re.compile(r"^\*{4}")
# 表格行 `**d%     ` / `**01-40——丘陵:** 值`（角色背景生成器，并入）
_RE_S6_TABLE_ROW = re.compile(r"^\*\*(?:d\d*|d%|\d+\s*[-–—]\s*\d+)")
# 中英括号锚裸行：`高热射击（Sizzling Shot，勇毅）…` / `不朽奏者(Undying
# Word)【歌者】…`（废土条目/专长形态；半角括号兼容）
_RE_CN_EN_BRACKET = re.compile(r"^[^（(\n]{1,40}[（(][A-Za-z]")
# 跨行标题英文行：`Volatile Fuse（战斗）：你手中的火器…`——英文名 +
# （中文类型）+ 冒号 + 正文（废土跨行条目第二行）；兼容 normalize
# `_merge_cross_line_en` 合并后的单行形态 `无定引信 Volatile Fuse（战斗）：…`
# （可选纯中文前缀 + 空格，KN150 跨行合并先拼后判）
_RE_EN_CN_PAREN = re.compile(
    r"^(?:[一-鿿/·]{1,8}[ \t]+)?[A-Za-z][A-Za-z \-]{0,30}（[^）\n]{1,8}）[：:]")
# 行尾 2 空格（LotFW 裸标题行 `矮人Dwarf  ` 标记）
_RE_TRAIL_2SP = re.compile(r"  $")
_RE_LATIN = re.compile(r"[A-Za-z]")
# 纯中文短行（≤30 字符、无标点；废土跨行标题上行拼接候选）
_RE_CN_SHORT = re.compile(r"^[一-鿿/·]{1,30}[ \t]*$")

_FIELD_LABELS: frozenset = frozenset(RULE_FIELD_LABELS + RULE_FIELD_LABELS_S6)


def _extract_title(line: str) -> str:
    """标题行 → 干净标题（无星壳残迹，KN160 防回退）。

    顺序约束：嵌套星归一（`****X****` → X）→ 首个闭壳截取（`**X**：正文`
    同行形态停于闭壳，正文不入 title）→ 残余星/尾冒号兜底 → 空白归一。
    闭壳截取兼容：6 星尾壳 `**苦难（…）******` 停在 6 星前 2 星、无正文
    形态 `**地下城 (Dungeons)**`、H 标题（无开壳时 else 分支原样）。
    """
    line = line.strip()
    line = _RE_NESTED_STAR.sub(r"\1", line)
    # 行首任意星数开壳归一为 `**`（`****X**` 4 开 2 闭转写残留——S2/S3
    # 文件如神赐/创造世界/page_597，`^\*{2}(.*?)\*{2}` 惰性匹配空组 → 空
    # title 根因，M4 2026-08-09）
    line = re.sub(r"^\*{2,}", "**", line)
    m = re.match(r"^\*{2}(.*?)\*{2}", line)
    if m:
        line = m.group(1)
    else:
        line = re.sub(r"^\*{2,}", "", line)
    # markdown 链接剥壳：`[文本](url)` → 文本（BBS 链接标题 page_314）/
    # `![[图片]](url)` → 图片（page_1490）——先图后链，图片内层 `[X]]` 不
    # 被普通链接正则误吃
    line = _RE_IMG_LINK.sub(r"\1", line)
    line = _RE_MD_LINK.sub(r"\1", line)
    # 兜底：残余星壳/尾冒号（`**X**：` 等截取残余形态）
    line = re.sub(r"\*{2,}[ \t]*(?:[：:][ \t]*)?$", "", line)
    line = line.replace("*", "")
    return " ".join(line.split())


def _extract_anchor_title(s: str) -> str:
    """锚点后标题行提取（comment_anchor 专属，KN213）：整体剥嵌套星壳
    （`**魔鬼鱼(**ANGLERFISH**)**` → `魔鬼鱼(ANGLERFISH)…`——_extract_title
    惰性匹配只取到 `魔鬼鱼(` 残缺）后取首个中英括号闭处（正文同行不入
    title）；括号前含句号（正文括号）回落 _extract_title"""
    inner = re.sub(r"\*\*([^*\n]+?)\*\*", r"\1", s).strip()
    for closer in ("）", ")"):
        idx = inner.find(closer)
        if 0 < idx <= 80 and "。" not in inner[:idx]:
            return inner[:idx + 1].strip()
    return _extract_title(s)


def _is_field_line(line: str) -> bool:
    """字段行判定：`**标签**：` / `**标签** `（尾空格+值换行）/ `**标签** 值`
    且标签 ∈ 词表 → 并入所属节（KN102；S6 放宽无冒号形态——作祟/OR stat
    block 字段 `**施法者等级** ` 标签带尾空格、值换行在下行）。
    标签带英文括号后缀（KN215 作祟 stat `**挑战等级（CR）** 2` /
    `**类型（CA）**` / `**感知（Perception）**`）先剥后缀再查词表——作祟
    字段名 = 词表词 + `（英文）` 注音形态，不剥则词表永不命中。
    开壳不闭形态（KN215/216）：`**效果 ` / `**基础 `——BBS「标签加粗换行」
    行尾无闭壳，_RE_FIELD_LINE 匹配不了（词表有词仍漏判 → 独立成泛词
    chunk）。判定层兼容只查词表不改写文本——全局补闭壳会破坏跨行名字行
    拼接（`**洛肯 \nLorcan**`）与跨行表格行（`**d%  `）的原文行形态
    （KN210/KN214 既有修复依赖）"""
    m = _RE_FIELD_LINE.match(line)
    if not m:
        # 开壳不闭变体：行首 `**` + 标签 + 空白到行尾（行内无闭壳/其他星）
        m = _RE_FIELD_LINE_OPEN.match(line)
    if not m:
        return False
    label = m.group(1).strip().rstrip("：:")
    if label in _FIELD_LABELS:
        return True
    # 行尾括号英文后缀（`（CR）`/`（CA）`/`（Benefit）`）剥除后词表判定；
    # 真标题「孤寂Isolation」无括号不受影响、「1环法术 (1st Level)」剥后
    # 仍不在词表
    m2 = _RE_EN_PAREN_SUFFIX.search(label)
    return bool(m2) and label[:m2.start()] in _FIELD_LABELS


def _bare_title_text(s: str) -> Optional[str]:
    """裸标题行 → title：
    - markdown 链接行（`![[图片]](url)` / `[文本](url)`）：剥壳取文本
      （page_1490 图片行——`_RE_CN_EN_BRACKET` 的 `[^（(\n]` 字符类不排除
      `[`/`]`/`!`，会把图片行误判为中英括号锚取整行，M5 修复）
    - 尾 2 空格短行（LotFW `矮人Dwarf  `）：strip 原样
    - 中英括号锚（废土 `高热射击（Sizzling Shot，勇毅）…`）：取括号闭处
      （全角 `）` 优先，半角 `)` 兼容——`不朽奏者(Undying Word)`）
    """
    m = _RE_IMG_LINK.match(s)
    if m:
        return m.group(1).strip()
    m = _RE_MD_LINK.match(s)
    if m:
        return m.group(1).strip()
    if _RE_TRAIL_2SP.search(s):
        return s.strip()
    if _RE_CN_EN_BRACKET.match(s):
        for closer in ("）", ")"):
            idx = s.find(closer)
            if idx > 0:
                # 括号闭处后跟类别标记 `【歌者】` → 并入 title（废土
                # `不朽奏者(Undying Word)【歌者】`，KN210 尸体贸易批次
                # 实测暴露）
                tail = re.match(r"^【[^】\n]{1,12}】", s[idx + 1:])
                end = idx + 1 + (tail.end() if tail else 0)
                # 过 _extract_title 剥壳：`_RE_CN_EN_BRACKET` 的 `[^（(\n]`
                # 字符类不排除星——星壳行 `**高等爆裂哑火（…）` 截取含前导
                # `**`（PotW，M5 修复）
                return _extract_title(s[:end])
    return None


def _s6_judge_title(line: str, shape: str, anchor: bool) -> Optional[str]:
    """S6 行级标题判定 → title（None = 并入所属节）。

    4 子策略（M4 形态勘察定稿，processor 层 `_RULE_S6_SHAPES` 注入）：
      comment_anchor（永罪之书×5）：`<!-- X-source -->` 锚点后的首个非空行
        = 唯一条目边界；条目内星壳小节/字段/头衔全部并入
      entry_line（LotFW/废土）：裸标题行（尾 2 空格短行中英 / 中英括号锚）
        = 边界；星壳破折号章节壳 = 边界；跨行标题上行拼接在骨架层处理
      haunt（作祟/OR）：星壳标题（「作祟：」前缀 / 闭壳中英括号 / 开星不闭
        含英文括号）= 边界；字段/名称行/4 星引用注并入
      bg_table（角色背景生成器）：闭壳词表外星壳 = 边界（表标题/阶段标题
        独立行）；表格行（d%/数字范围）/ 行内加粗步骤行并入
    """
    s = line.rstrip("\n")
    if s.startswith(">") and shape in ("entry_line", "bg_table"):
        # 引用块（`> 来源：…（Black Markets）` 来源行）不判标题
        # （KN210 尸体贸易首节伪 title——中英括号形态误匹配）
        return None
    if shape == "comment_anchor":
        # 锚点后的首个非空行 = 条目标题（KN213：极限荒野嵌套星壳形态
        # `**魔鬼鱼(**ANGLERFISH**)**` 走专属提取，_extract_title 惰性
        # 匹配只取到 `魔鬼鱼(` 残缺）
        if anchor:
            return _extract_anchor_title(s)
        # KN210：非锚点位置的星壳名字行（无中文括号中英混排，次级魔鬼
        # `**比弗伦斯 Bifrons**`）= 独立条目边界——无注释锚点时不再吞入
        # 前条目触发 oversize 续拆；字段行/表格行/条目内小节（中文括号/
        # 纯中文头衔如 `**飞蝇领主**`）并入
        if s.startswith("**") and not _RE_S6_TABLE_ROW.match(s) \
                and not _is_field_line(s):
            inner = _extract_title(s).strip()
            if inner and "（" not in inner and _RE_LATIN.search(inner) \
                    and len(inner) <= 80:
                return inner
        return None
    if shape == "entry_line":
        # 裸标题：尾 2 空格短行（≤60）且含拉丁（中英混排/纯英文大写 FEATS）；
        # 过 _extract_title 剥壳（PotW `**高等爆裂哑火（…）**  ` 尾 2 空格
        # + 加粗壳形态，原 return s.strip() 带星壳入 title，M5 修复）
        if _RE_TRAIL_2SP.search(s) and len(s.strip()) <= 60 \
                and _RE_LATIN.search(s):
            return _extract_title(s)
        # 跨行标题英文行：`Volatile Fuse（战斗）：你手中的火器…`——英文名 +
        # （中文类型）+ 冒号 + 正文（废土跨行条目第二行，上行中文名拼接）
        if _RE_EN_CN_PAREN.match(s) and len(s) <= 130:
            for idx in (s.find("："), s.find(":")):
                if idx > 0:
                    return s[:idx].strip()
        # 中英括号锚（废土条目/专长，含「标题+正文同行」长行粘连形态）
        if _RE_CN_EN_BRACKET.match(s) and len(s) <= 130:
            # KN210：半角括号句中（`从魔魂尸(mohrg)中提取…` 括号后紧贴
            # 中文）= 正文行不判标题；中文括号形态不受限（废土标题）
            m = re.search(r"\([^)\n]{1,20}\)", s)
            if m and m.end() < len(s) and \
                    "一" <= s[m.end()] <= "鿿":
                return None
            t = _bare_title_text(s)
            if t:
                return t
        # 星壳标题：词表外 + 非表格行（章节破折号壳 `**————法力废土求生————**`）
        if s.startswith("**") and not _RE_S6_TABLE_ROW.match(s) \
                and not _is_field_line(s):
            inner = _extract_title(s).strip()
            if inner:
                return inner
        return None
    if shape == "haunt":
        if s.startswith("****") or _RE_PURE_STARS.match(s):
            return None  # 4 星引用注行并入
        if _RE_S6_TABLE_ROW.match(s) or _is_field_line(s):
            return None
        if s.startswith("**"):
            inner_raw = s[2:]
            if "**" in inner_raw:  # 闭壳形态
                inner = _extract_title(s).strip()
                if not inner or inner in _FIELD_LABELS:
                    return None  # 纯空格壳 / 字段行
                if inner.startswith("（译注") or "译注" in inner[:6]:
                    return None  # 译注行 `**（译注：…）**` 并入所属节
                    # （作祟汇总 ×4：含 `（`+拉丁 .jpg/dm 被括号标题规则
                    # 误判为标题，M5 修复）
                if "（" not in inner and _RE_LATIN.search(inner):
                    return None  # 名称行 `孤寂Isolation CR—`（并入条目）
                if "（" in inner and _RE_LATIN.search(inner) and len(inner) <= 80:
                    return inner  # 闭壳中英括号标题
                return None  # 其余纯中文闭壳保守并入
            # 开星不闭形态
            if inner_raw.startswith("作祟："):
                # `**作祟：孤寂` = 作祟条目开星不闭名称行（孤寂作祟，真条
                # 目标题——stat block 完整随行；KN215 复核：非引用注，注释
                # 口径修正 2026-08-09）
                return inner_raw.rstrip()
            if _RE_CN_EN_BRACKET.match(inner_raw) and len(inner_raw) <= 80:
                return inner_raw.rstrip()  # OR 仪式标题 `**激活艾悠达拉（…）`
            return None
        return None
    if shape == "bg_table":
        if not s.startswith("**") or _RE_PURE_STARS.match(s) \
                or _RE_S6_TABLE_ROW.match(s) or _is_field_line(s):
            return None
        inner = _extract_title(s).strip().rstrip("：:")
        if not inner or inner.startswith("步骤"):
            return None  # 行内加粗步骤行并入（非表标题）
        if "。" in inner:
            # KN214：含句号 = 表说明行/正文行（`**投掷一次决定你的出生
            # 状况。` / `**当你出生时…。你可以选择**信念背景…`）并入；
            # 表标题（`**出生状况表`）无句号仍为边界
            return None
        return inner
    if shape == "god_table":
        # page_320 神祇扩展整页表格（KN211）：表格行首列含拉丁 = 独立条目
        # （title=首列神名，可检索）；表头行/分隔行/无拉丁首列行（`表：变体
        # 引导`/`神职/主题`）/说明行并入所属节
        if s.startswith("|"):
            m = re.match(r"^\|\s*([^|]+)\|", s)
            if m:
                name = m.group(1).strip()
                if name and _RE_LATIN.search(name) and "---" not in name:
                    return name
        return None
    return None


# 跨行表格行上行：`**01-05——学院教育（Academy Training）: ` / `**d%     `
# ——开星不闭表格行（行内除开星外无星，KN214）
_RE_TABLE_ROW_OPEN = re.compile(
    r"^\*\*(?:d\d*|d%|\d+\s*[-–—]\s*\d+)[^*]*$")
# 跨行名字行上行：`**洛肯 `——开星不闭纯中文短行（KN210 次级魔鬼）
_RE_STAR_CN_SHORT = re.compile(r"^\*\*[一-鿿/·]{1,30}[ \t]*$")


def _merge_cross_line_star(lines: List[str]) -> List[str]:
    """跨行名字行拼接（comment_anchor 专属，KN210）：`**洛肯 \nLorcan**`
    （开星不闭纯中文短行 + 紧邻英文闭壳行）→ `**洛肯 Lorcan**` 单行，使
    名字行规则能判边界（骨架逐行判定无法跨行）；条目内跨行小节标题
    （`**纯真之末（End of\nInnocence）**` 上行含括号/拉丁）不匹配不拼接"""
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _RE_STAR_CN_SHORT.match(line) and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            m = re.match(r"^([A-Za-z][A-Za-z \-]{0,30})\*{2}$", nxt)
            if m:
                out.append(line.rstrip() + " " + m.group(1) + "**")
                i += 2
                continue
        out.append(line)
        i += 1
    return out


def _merge_cross_line_table(lines: List[str]) -> List[str]:
    """跨行表格行拼接（bg_table 专属，KN214）：`**01-05——…: `（开星不闭
    表格行）+ 紧邻下行（`**你曾就读于…**`）→ 拼回单行；拼回后
    _RE_S6_TABLE_ROW 匹配 → 整行并入所属节，下行星壳正文不再被误判为
    边界（背景生成器「正文首句」伪标题 chunk 根因）"""
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _RE_TABLE_ROW_OPEN.match(line) and i + 1 < len(lines) \
                and lines[i + 1].strip():
            out.append(line.rstrip() + " " + lines[i + 1].strip())
            i += 2
            continue
        out.append(line)
        i += 1
    return out


def _split_aggregate(text: str, shape: str) -> List[dict]:
    """S6 超大型聚合切分器：条目级专用（M2 拍板「超大型条目级预拆」）。

    通用骨架：`****` 纯星行剥除（空 title 碎片根因修复）；`<!-- -->` 注释
    锚点消费于下一非空行；字段/表格/引用注并入所属节；相邻重复标题合并
    （OR「开星版 + 闭壳完整版」两条标题并一节）。跨行标题上行拼接
    （entry_line：上行纯中文短行 + 本行括号名——废土 `无定引信 ` +
    `Volatile Fuse（战斗）：…`）。
    """
    lines = text.split("\n")
    if shape == "comment_anchor":
        lines = _merge_cross_line_star(lines)
    elif shape == "bg_table":
        lines = _merge_cross_line_table(lines)
    items: List[Dict] = []
    cur: Dict = None
    pending: List[str] = []   # 首个边界前的导言行（并入首节）
    anchor = False            # 注释锚点：下个非空行是条目边界
    at_separator = True       # 文件首/剥除行后：下个非空行可作跨行拼接上行
    prev_cn_short: Optional[str] = None  # 跨行标题上行（entry_line 拼接）

    for line in lines:
        if _RE_PURE_STARS.match(line):
            at_separator = True
            continue  # 纯星分隔线剥除（不产生节）
        if _RE_ANCHOR_COMMENT.match(line):
            anchor = True
            at_separator = True
            continue
        if not line.strip():
            continue
        title = _s6_judge_title(line, shape, anchor)
        if title is not None:
            # 跨行标题拼接：上行纯中文短行（`无定引信 ` + `Volatile Fuse…`，
            # 仅限剥除行后首个非空行——正文短行不误拼，LotFW 导言教训）
            if shape == "entry_line" and prev_cn_short is not None \
                    and title != prev_cn_short:
                title = prev_cn_short + " " + title
            if cur is not None and cur["title"] == title:
                # 相邻重复标题 → 并入当前打开项（OR 开星+闭壳双标题；
                # 对 cur 判重而非 items[-1]——cur 未 flush 时（重复标题间
                # 有正文行）旧写法会双重 append 产生重复项）
                cur["text"] += line + "\n"
            else:
                if cur is not None:
                    items.append(cur)
                cur = {"title": title, "text": line + "\n",
                       "type": "section", "format_cluster": "s6_large_aggregate"}
                if pending:
                    cur["text"] = "\n".join(pending) + "\n" + cur["text"]
                    pending = []
        else:
            if cur is not None:
                cur["text"] += line + "\n"
            else:
                pending.append(line)
        anchor = False
        # 记录跨行拼接上行（entry_line：剥除行后首个非空行且为纯中文短行；
        # `无定引信 ` 形态——废土跨行标题第一行）
        s = line.rstrip("\n")
        if shape == "entry_line" and at_separator and _RE_CN_SHORT.match(s):
            prev_cn_short = s.strip()
        else:
            prev_cn_short = None
        at_separator = False

    if cur is not None:
        items.append(cur)
    if not items and pending:
        # 无任何边界：整篇 1 chunk（含 title 提取退化）
        items.append({"title": "", "text": "\n".join(pending) + "\n",
                      "type": "section", "format_cluster": "s6_large_aggregate"})
    return items


# ---- 超限预拆（M4 R9，2026-08-09：>5000 按下一级结构再拆）----
# 计划文档 79 行「oversize-limit 5000 超限按下一级结构再拆」落地：
#   非表格超限 chunk → 段落级（\n\n）累积切分；无段落边界（S5 整篇
#   连写/单段长文）→ 行级（\n）累积；续块 title = `原title（续N）`。
#   表格 chunk（text 首行即表行 `|`）不拆——表格行拆分会断结构完整性，
#   登记 max-oversize（装备 KN186 先例），检索端降权。
#   碎尾块不并入前块：段落级累积的切点判据（cur+2+p > limit）与「并入
#   不超限」（cur+2+尾 ≤ limit）数学上互补——尾段并入不超限时累积阶段
#   就并进 cur 了，并入逻辑恒不触发；碎尾独立成 chunk（续标可检索）。
#   含表格行的行（`|` 开头）独立成段不参与行级拼接（表格行拆分会断
#   结构，登记保留）。

_OVERSIZE_LIMIT = 5000      # 与闸口 oversize-limit 5000 同口径
# 纯表格分隔行：`| --- |` / `| --- | --- |`（markdown 表格分隔符，无语义；
# 行级续拆中独立成段会产出 8 字符噪声 chunk——KN210 阿达德·莉莉续5）
_RE_TABLE_SEP = re.compile(r"^\|\s*[-—:]+\s*(\|\s*[-—:]+\s*)*\|?$")
# 纯空表格行 `|  |`（page_279 范例陷阱续N 家族，KN218）：无语义，并入
# 当前段不独立成段（同 _RE_TABLE_SEP 机制）
_RE_TABLE_EMPTY = re.compile(r"^\|\s*\|$")


def _split_oversize_body(body_lines: List[str], limit: int = _OVERSIZE_LIMIT,
                         allowance: int = 0) -> List[str]:
    """正文行序列 → 超限分段（段落级优先，无段落边界行级）。

    累积判据 = 字符数（与闸口一致）；段间 `\n\n`（2 字符）、行间
    `\n`（1 字符）计入。allowance = 首块标题行 + 分隔开销（head+2）：
    阈值对**链首**（首段/首行）前移 limit-allowance，保证 piece0 =
    标题行 + 段 ≤ limit；递归下传只作用于子链首块。超限段（>阈值）
    且含换行 → 行级递归再拆（计划文档 79 行「超限按下一级结构再拆」
    本义：段落 → 行两级下探）；单行 >阈值（词表行/超长整段无内部分
    界）递归终止保留登记（max-oversize）。
    """
    text = "\n".join(body_lines)
    # 阈值统一 = limit - allowance：allowance 是链首块的标题行 + 分隔
    # 开销（head+2），累积/递归判据必须同源——否则区间 [limit-allowance,
    # limit] 的块会「递归体又全收」形成无限递归（Spell UI 4 行 4723 案例，
    # M4 2026-08-09 死循环调试）
    thr = limit - allowance
    if len(text) <= thr:
        return [text]
    paras = [p for p in text.split("\n\n") if p.strip()]
    if len(paras) > 1:
        # 段落级累积：cur + `\n\n` + p 超阈值即切；首段自身超阈值独立
        segs: List[str] = []
        cur = ""
        for p in paras:
            if cur and len(cur) + 2 + len(p) > thr:
                segs.append(cur)
                cur = p
            elif not cur and len(p) > thr:
                segs.append(p)  # 首段独立（递归层统一再拆）
                cur = ""
            else:
                cur = f"{cur}\n\n{p}" if cur else p
        if cur:
            segs.append(cur)
    else:
        # 无段落边界（单段长文/S5 整篇连写）：行级累积，逐行并入；
        # 含表行的行（`|` 开头）独立成段（表格行结构保护）
        segs = []
        cur = ""
        for l in body_lines:
            if l.lstrip().startswith("|"):
                if _RE_TABLE_SEP.match(l.strip()):
                    # 纯分隔行 `| --- |`：无语义，并入当前段不独立成段
                    # （防 8 字符噪声 chunk，KN210 阿达德·莉莉续5）
                    if cur:
                        cur = f"{cur}\n{l}"
                    continue
                if _RE_TABLE_EMPTY.match(l.strip()):
                    # 纯空表格行 `|  |`（page_279 范例陷阱续N 家族，
                    # KN218）：无语义，并入当前段（同上机制）
                    if cur:
                        cur = f"{cur}\n{l}"
                    continue
                # 表格行：不参与行级拼接，独立成段（结构保护）
                if cur:
                    segs.append(cur)
                    cur = ""
                segs.append(l)
                continue
            if cur and len(cur) + 1 + len(l) > thr:
                segs.append(cur)
                cur = l
            elif not cur and len(l) > thr:
                segs.append(l)  # 首行超阈值独立（单行无界，登记保留）
                cur = ""
            else:
                cur = f"{cur}\n{l}" if cur else l
        if cur:
            segs.append(cur)
    # 超限段行级递归再拆（下一级结构；链首带 allowance 下传）
    final: List[str] = []
    for i, seg in enumerate(segs):
        thr = limit - allowance if i == 0 else limit
        if len(seg) > thr and "\n" in seg:
            final.extend(_split_oversize_body(
                seg.split("\n"), limit, allowance if i == 0 else 0))
        else:
            final.append(seg)
    return final


def _oversize_split(items: List[dict],
                    limit: int = _OVERSIZE_LIMIT) -> List[dict]:
    """split_into_items 全出口统一包裹：>limit 超限 chunk 预拆。

    表格 chunk（text 首行即表行）不拆；首行是标题行时标题行保留在
    首块 text（检索上下文），续块 title = `原title（续N）`。空 title
    （S5 整篇连写无标题）时全部行按正文拆。
    """
    out: List[dict] = []
    for it in items:
        text = it["text"]
        if len(text) <= limit:
            out.append(it)
            continue
        lines = text.split("\n")
        if lines and lines[0].lstrip().startswith("|"):
            # 整表 chunk（S4 整页纯表）不拆：登记 max-oversize
            out.append(it)
            continue
        title = it["title"]
        # 标题行判定跳过前导空行（page_299 动物伙伴一览 chunk text 前导
        # 空行——S6/主循环 pending 空行并入形态）：head_is_title 时标题行
        # 保留在首块 text（检索上下文），前导空行丢弃（清洗语义）
        head_i = next((i for i, l in enumerate(lines) if l.strip()), 0)
        head_line = lines[head_i] if head_i < len(lines) else ""
        head_is_title = bool(title) and bool(head_line) and \
            _extract_title(_RE_H_HEADING.sub("", head_line)).strip() == title
        body_lines = lines[head_i + 1:] if head_is_title else lines
        segs = _split_oversize_body(body_lines, limit,
                                    allowance=len(head_line) + 2 if head_is_title else 0)
        for i, seg in enumerate(segs):
            piece = dict(it)
            if i == 0 and head_is_title:
                piece["text"] = head_line + "\n\n" + seg + "\n"
            else:
                piece["text"] = seg + "\n"
            if i > 0:
                # KN217：续块 title 取首行表格行首列条目名（`| 弯刀 | 价
                # 格 |…` → 「弯刀（续2）」）——1262 表格行续块（大节含表
                # 超限后行级续拆）从无差别「原title（续N）」语义化为条目
                # 名。守卫：行内 `|` ≥3（真多列表格行）才提取——单格行
                # `| 陷阱 stat 整行 |`（page_279 范例陷阱，首列=整行内容
                # 退化）+ 首列空（表头 `| 名称 |`）+ 非表格行续块 → 原 title
                first = seg.split("\n", 1)[0].lstrip()
                head = ""
                if first.startswith("|") and first.count("|") >= 3:
                    m = re.match(r"^\|\s*([^|]*?)\s*\|", first)
                    if m:
                        head = m.group(1).strip()
                piece["title"] = f"{head}（续{i + 1}）" if head \
                    else f"{title}（续{i + 1}）"
            out.append(piece)
    return out


class RuleFormat(BaseFormat):
    """规则格式切分器（S1~S5 统一行扫描，差异只在标题形态与并入词表）"""

    @property
    def category(self) -> str:
        return "rule"

    def __init__(self) -> None:
        # processor 层按文件注入的 manifest hint（KN192；split 时参数优先）
        self.format_cluster_hint: Optional[str] = None
        # S6 子策略（comment_anchor/entry_line/haunt/bg_table，processor 层
        # `_RULE_S6_SHAPES` 表注入——10 文件形态差异太大，单一启发式不可行）
        self.s6_shape: Optional[str] = None

    # ---- Phase 1：纯去噪 ----

    def _normalize_custom(self, text: str) -> str:
        # 1. CR 归一：\r\n → \n（CRLF 行尾），\r → \n（KN159/191 表格行
        #    行中 CR 腰斩）——前置清洗后仍须防御（KN159 防回退断言），
        #    行锚剥除依赖换行结构
        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")
        # 2. 页头 URL+译者同行行剥除（含 `### ` 前缀形态 page_130）
        text = _RE_URL_HEAD_LINE.sub("", text)
        # 3. 多段星壳译者行（`**译者：****X****，****Y******`，page_413；
        #    `\*{0,2}` 兼容闭壳字段 `**译者**：**四月******` page_517/601）
        text = _RE_TRANSLATOR_STAR_LINE.sub("", text)
        # 3b. 开星不闭译者行（`**译者：旅法师 `，page_646 跨行闭壳）+
        #     孤立链接残渣行（`](http://...)`，page_322）
        text = _RE_TRANSLATOR_BARE_LINE.sub("", text)
        text = _RE_ORPHAN_URL_TAIL.sub("", text)
        # 4. 跨行英文名合并（KN150 教训：断行英文名 2485 处；含星壳内
        #    跨行 `Tactical \nMovement`——_RE_CROSS_EN 的 `\*{0,4}` 兼容）
        text = _merge_cross_line_en(text)
        # 5. BBS 跨行加粗壳：`**  `（星壳+纯空白行）与下一行拼接——BBS 帖
        #    「标签加粗换行」形态前半（page_159 重训 30 / page_591 咒字 34
        #    空 title 根因：壳行被 _RE_STAR_TITLE 判标题但 _extract_title 空）
        text = _RE_BBS_BOLD_SHELL.sub("**", text)
        # 6. 纯星分隔行剥除（S1~S5 扫描路径无 S6 骨架的纯星防御，`****` 行
        #    判标题 → 空 title chunk，page_159 30 中 4 个）
        text = _RE_PURE_STARS.sub("", text)
        # 7. 4+ 星连排碎片剥除（KN212）：BBS `[b]` 嵌套转换残渣
        #    （`**重训（****Retraining****）******` / `**野蛮****人****（Unchained）**`
        #    / `**【****PFS****】**`）——`\*{4,}` = 「加粗壳边界粘连 + 残留」，
        #    直接剥除；干净 2 星加粗（正文强调）与单星斜体（人名/书名，
        #    verify docstring 305 处全定性保留）不在剥除范围
        text = _RE_STAR_FRAGMENT.sub("", text)
        # 8. 删除线壳剥除（HTML `<S>` 转换标记，KN160 家族）
        text = _RE_STRIKE_SHELL.sub("", text)
        return text

    def promote(self, text: str) -> str:
        # 规则无字段体系（M2 §一），无抽象提升
        return text

    # ---- Phase 2：拆分为语义节 ----

    def split_into_items(self, text: str, *, source_name: Optional[str] = None,
                         format_cluster_hint: Optional[str] = None,
                         s6_shape: Optional[str] = None) -> List[dict]:
        """行扫描切分：节边界 = H3~H6 标题 + 行首星壳标题（- 字段行 / - l
        组并入所属节）。首节导言段（首边界前内容）并入首节 text。

        format_cluster_hint：processor 层 manifest 显式注解（KN192），
        s5_prose 时走专用分支整篇 1 chunk——S5 语义 = 无边界（游戏范例
        角色名星壳行是对话说话人标注，不是节边界，M3 +23 误切教训）；
        s6_large_aggregate 时走条目级切分（s6_shape 子策略分派）。
        参数优先级 > 实例属性（pipeline 复用实例时以每次注入为准）。
        """
        hint = format_cluster_hint if format_cluster_hint is not None \
            else self.format_cluster_hint
        if hint == "s5_prose":
            return _oversize_split(self._split_prose_whole(text))
        if hint == "s6_large_aggregate":
            shape = s6_shape if s6_shape is not None else self.s6_shape
            return _oversize_split(_split_aggregate(text, shape or "entry_line"))
        lines = text.split("\n")
        items: List[Dict] = []
        cur: Dict = None  # 当前节
        pending: List[str] = []  # 首个边界前的导言行（并入首节）
        join_next = False        # l 残渣后下一标题行并入所属节
        has_h = False
        has_nested_star = False

        def flush():
            nonlocal cur
            if cur is not None:
                items.append(cur)

        for line in lines:
            # l 残渣行：剥除 + 标记下一标题行并入
            if _RE_L_ARTIFACT.match(line):
                join_next = True
                continue
            # HTML 来源注释行（`<!-- X-source:... -->`）消费不并入正文（KN206）：
            # S6 锚点语义只在 _split_aggregate（此处无锚点信号）；chm_toc_path
            # 回填读源文件注释（feat_chain RE_ANNO），剥除 chunk 文本不受影响
            if _RE_ANCHOR_COMMENT.match(line):
                continue
            if _RE_H_HEADING.match(line):
                has_h = True
                t = _extract_title(_RE_H_HEADING.sub("", line))
                if (cur is not None and cur["title"] == t
                        and len([l for l in cur["text"].split("\n")
                                 if l.strip()]) <= 2):
                    # 同题相邻包裹合并：`# X` + 注释 + `## X` 复述（未整理
                    # 整理产物 H1/H2 同题复述形态）——cur 仅标题+可选注释行
                    # 时覆盖标题行不新建节，防同题双节碎片（M4 2026-08-09）
                    cur["title"] = t
                    cur["text"] = line + "\n"
                else:
                    flush()
                    cur = {"title": t, "text": line + "\n", "type": "section",
                           "format_cluster": "s1_heading_tree"}
                    if pending:
                        cur["text"] = "\n".join(pending) + "\n" + cur["text"]
                        pending = []
                join_next = False
            elif _RE_TABLE_TITLE.match(line) and cur is None and not pending:
                # 整页纯表：文件首个非空行即表标题行（page_400 `| 表：召唤
                # 怪物 |`）→ 建节；普通文件表格标题行（前有节标题）仍并入
                # 所属节（M3「表格跟随所属节」不破坏）
                flush()
                cur = {"title": _extract_title(line.strip("|").strip()),
                       "text": line + "\n", "type": "section",
                       "format_cluster": "s4_table_page"}
                join_next = False
            elif (cur is None
                    and all(not l.strip() for l in pending)
                    and not line.startswith("*")
                    and len(line) <= 100 and _bare_title_text(line)):
                # 文件首行裸标题短行（page_653 s2 形态：空行 + `天生物品加值
                # （Innate Item Bonuses）` + 正文）→ 建节。仅首行触发（pending
                # 无实义内容），正文中裸短行（`诱因（Catalyst）` 小标）不建节
                flush()
                t = _bare_title_text(line)
                cur = {"title": t, "text": line + "\n", "type": "section",
                       "format_cluster": "s2_bold_title"}
                if pending:
                    cur["text"] = "\n".join(pending) + "\n" + cur["text"]
                    pending = []
                join_next = False
            elif _RE_STAR_TITLE.match(line) and not _is_field_line(line):
                if "*{4}" in line or "****" in line:
                    has_nested_star = True
                if join_next:
                    # l 组：标题并入所属节（子条目，page_239 移动方式）
                    if cur is not None:
                        cur["text"] += line + "\n"
                    else:
                        pending.append(line)
                    join_next = False
                    continue
                if not _extract_title(line).strip():
                    # 星壳空标题（`** **` / `***** **说明**` 空组形态，
                    # page_532/page_302）——不判标题，并入所属节
                    if cur is not None:
                        cur["text"] += line + "\n"
                    else:
                        pending.append(line)
                    continue
                flush()
                cur = {"title": _extract_title(line),
                       "text": line + "\n", "type": "section",
                       "format_cluster": "s2_bold_title"}
                if pending:
                    cur["text"] = "\n".join(pending) + "\n" + cur["text"]
                    pending = []
            else:
                # 正文行（含字段行——并入所属节，KN102）
                if cur is not None:
                    cur["text"] += line + "\n"
                else:
                    pending.append(line)
            # 已开启节后 join_next 不再生效于后续行（l 标记只对下一标题行）
            if join_next and cur is not None:
                join_next = False

        if cur is None and pending:
            # 无任何边界：整篇 1 chunk（S5 prose，page_130 外的无标题文件）
            return _oversize_split([{
                "title": "", "text": "\n".join(pending) + "\n",
                "type": "section", "format_cluster": "s5_prose"}])

        flush()

        # format_cluster 推导（processor 层以 manifest hint 显式覆盖）：
        # H 标题存在 → s1_heading_tree（page_313/408 混合先例）；否则按
        # 星壳形态（嵌套 4 星 = s3_bbs_star / 单层 = s2_bold_title）
        cluster = "s1_heading_tree" if has_h else (
            "s3_bbs_star" if has_nested_star else "s2_bold_title")
        for it in items:
            it["format_cluster"] = cluster
        return _oversize_split(items)

    def _split_prose_whole(self, text: str) -> List[dict]:
        """S5 prose 专用分支：整篇 1 chunk（无边界语义）。

        角色名星壳行（`**哈斯克**` 等游戏范例对话说话人标注）不是节边界
        （M3 产出 page_130 +23 误切教训）；URL/译者行已在 normalize 剥除。
        title = 首个 H 标题（无 H 则空串）；正文原文保留（含星壳行）。
        """
        lines = [l for l in text.split("\n")
                 if l.strip() and not _RE_ANCHOR_COMMENT.match(l)]
        title = ""
        body: List[str] = []
        for line in lines:
            m = _RE_H_HEADING.match(line)
            if m and not title:
                title = _extract_title(_RE_H_HEADING.sub("", line))
            elif not title and not body:
                # 首行星壳标题兜底：无 H 结构但首行是 2 星开壳标题
                # （`**战役说明（Campaign Clarifications）` 开星不闭形态，
                # 第十季战役说明类 S5 文件——源数据标题行跨行腰斩，normalize
                # 合并后无 `####` 结构，M4 空 title 散点修复）。
                # 守卫 `^\*\*(?!\*)`：3 星开 = 斜体/编注行（`***最后更新…*`），
                # 不得误判为标题；字段行（`**标签**：`）同理并入正文。
                if (re.match(r"^\*\*(?!\*)", line) and not _is_field_line(line)
                        and _extract_title(line).strip()):
                    title = _extract_title(line)
                elif (not line.startswith("*") and len(line) <= 100
                        and _bare_title_text(line)):
                    # 裸标题短行兜底（`不义（Amoral）` / `《…》（EN）` 书名号
                    # 形态，HA 腐化/勘误表类 S5 文件）：中英括号锚或尾 2 空格
                    # 短行 = 标题。无星守卫（星壳行已由上一分支处理）+ 行短
                    # 守卫防正文首句误判（`追逐(Chases)追逐在…` 超长正文行
                    # 数百+ 字符不提取；书名号形态 ~73 字符实测，守卫取 100）
                    title = _bare_title_text(line)
            body.append(line)
        return [{"title": title, "text": "\n".join(body) + "\n",
                 "type": "section", "format_cluster": "s5_prose"}]
