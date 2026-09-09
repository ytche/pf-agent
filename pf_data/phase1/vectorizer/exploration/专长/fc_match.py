#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
format_clusters 簇判别器（k3 汇总阶段工具，只读源数据）
对 189 个源文件按优先级套用簇判别正则，统计每文件各簇标题命中数，
与勘探报告 estimated_count 对账。判别在"逻辑行"上进行（\r\n|\r|\n 切分），
跨行英文名允许最多 3 行窗口。
用法：python3 fc_match.py [--file 专长42.md] [--miss]
"""
import json, re, os, sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_ROOT = os.path.normpath(os.path.join(ROOT, "../../../pf_rules_md_organized"))
MERGED = os.path.join(ROOT, "专长_per_file.jsonl")

# ---- 原子 ----
CN  = r"[一-鿿][一-鿿·/\-]*"                       # 中文名（允许 · / -）
ENW = r"[A-Za-z][A-Za-z'’\.\-]*"                   # 英文单词
EN  = ENW + r"(?:[ ]+" + ENW + r")*"               # 单行英文短语（允许多空格）
ENX = EN + r"[ ]*(?:\s*\n\s*" + EN + r"[ ]*){0,2}" # 允许跨行（≤3行）英文（尾部容忍空格：闹鬼 'Soulwrecking Strike )' 型）
ENWE = r"[A-Za-z][A-Za-z&;'’\.\-]*"                # FC-6h 专用：HTML 实体容忍（Fa&ccedil;ade）
FTW = r"(?:战斗|团队|超魔|故事|流派|造物|勇毅|重击|演武|派头|注视|凝视|诅咒|背叛|神话|物品制造|物品掌握|汲引|地方|伟业|血巫术|动物伙伴|魔宠|伙伴|专长|掌握|武器掌握|瞄准|诡计|盔甲掌握)"
FT  = FTW + r"(?:[，、, ]?" + FTW + r")*"          # 复合标签（分隔符可选：流派专长/战斗专长）
STAR = r"\*{2,}[ ]*"                                # 2+ 星号（4/6 星噪声归并；尾部容忍空格——page_1368 '** 狠辣借机' 星后 18 空格型）
OSTAR = r"(?:\*{2,})?"                              # 可选星号包裹
BR_OPEN  = r"[（(]"
BR_CLOSE = r"[）)]"
FT_SUFFIX = (r"(?:\s*[〔【［\[]" + FT + r"(?:专长)?[〕】］\]]"
             r"|\s*" + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE + r")?")

def C(re_str, name, note):
    return (name, re.compile(re_str, re.M), note)

# 优先级有序：先特殊后一般。模式作用于"从行首开始的 ≤4 行窗口"文本。
TABLE_SEP = re.compile(r"^\|[\s\-|]+\|$")
TABLE_HDR = re.compile(r"专长名称|名称\s*\|\s*先决条件|^\|\s*先决条件")
# 表头特征词（叠加"下一行是分隔行"判据用）：条目表表头必有字段标签
# （'| 种族专长 | 先决条件 |'）；怪物召唤表头（'| 召唤生物 |'）无 → 数据表
HDR_FIELD = re.compile(r"先决条件|前置|专长效果|好处|专长名称")
# 区段表头：'| 团队专长 | 先决条件 | 专长效果 | 类型 |'——后续区段表头
# 无分隔行跟随（仅首区段表头后跟 ---），首单元格纯中文含"专长"且无星号
# （'| 水下战斗法* |' 数据闭合行有星号、'| Got Your Back* |' 英文行首 → 均排除）
SEG_HDR = re.compile(r"^\|\s*[^|*A-Za-z]*专长[^|*]*\s*\|")

CLUSTERS = [
 C(r"^\|", "FC-T 表格行",
   "行首 | 即表格行起点（裸 CR 断行使行可只含 1 个 |）；需滤表头/分隔行"),
 C(r"^\*{0,2}【(?!速查)[^】]+】" + r"[ ]?\*{0,2}" + CN + r"[（(][^）)]{1,40}[）)]", "FC-I 索引/聚合行",
   "【来源缩写】中文名（类型）（English）索引行；【速查】速查表行除外；容忍行首 **（【PFS】魔宠连接型）与【】后 ** 粘连（【PFS不可】 **治疗者之手型）、英文跨行（Healer's\\nHands 型）"),
 C(r"^#{1,3}\s*" + OSTAR + CN + r"[（(]" + ENX + r"[）)]\s*\*{0,2}(?=\n|$)",
   "FC-H 井号标题", "# / ## / ### 标题，可带 ** 包裹；行尾锚排除文件标题（'# 武术手册（Martial Arts Handbook）MAH 专长' 型）"),
 C(r"^#{1,3}\s*" + OSTAR + CN + r"(?:[（(]" + FT + r"(?:专长)?[）)]\s*|[ ])?" + ENX + r"(?=\s*$)",
   "FC-Hb 井号裸英文", "## 中文名 Ancestral Scorn / ## 中文名（类型） Banner of Doom（炼狱血脉/天界血脉型）；行尾锚排除文件标题（'# 异能源始OO 专长'）"),
 C(r"^" + STAR + CN + BR_OPEN + r"(?:神话|超魔)" + BR_CLOSE + OSTAR + r"\s*$",
   "FC-5 神话族", "**中文名（神话）** 标题行，英文名在次行"),
 C(r"^" + STAR + CN + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE + STAR + r"\s*$",
   "FC-5b 中文类型族", "**中文名（战斗）** 无英文名；位面谐律（汲引）/武器技法（战斗）/元素融合（团队专长）型"),
 C(r"^" + STAR + r"~~?" + CN + r"~~?" + STAR + r"~~?" + ENX,
   "FC-9 删除线标题", "**~~中文~~**~~**English 删除线族"),
 C(r"^" + STAR + CN + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE
   + r"(?:" + OSTAR + BR_OPEN + ENX
   + r"(?:[ ]?(?:\n[ ]*)?[（(][A-Za-z][^）)]{0,24}[）)])?"  # 英文内嵌别名括号（闪现步（汲引）（Flickering Step (Conduit)）型；ENX 停后残留空格/换行需容忍，内嵌括号可跨行（相位打击 (Phase Strike (Combat,\nConduit)) 型）
   + BR_CLOSE + OSTAR + r"|" + OSTAR + r"[ ]*" + ENX + r")",
   "FC-4 feat_type前置", "**中文名（类型）（English）** / **中文名（类型）**English（英文前容忍多空格：不屈坐骑(战斗) Indomitable / 浪徒之幸(汲引)  (Wanderer's 型；英文内嵌别名括号容忍：闪现步（汲引）（Flickering Step (Conduit)）型）"),
 C(r"^" + CN + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE + r"[ ]?" + ENX,
   "FC-4b 裸类型前置", "水下冒险型：中文名（类型）English 行首无 **"),
 C(r"^" + CN + STAR + CN + r"[ ]" + ENX + STAR + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE + OSTAR,
   "FC-6d 星号断名", "鲨蜥·****扑 Bulette Leap****（战斗专长）**** 星号插入中文名中段"),
 C(r"^" + STAR + CN + ENX + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE
   + r"(?:" + BR_OPEN + r"[^）)\n]{1,25}" + BR_CLOSE + r")?\s*$",
   "FC-6e 加粗未闭合", "**优雅双武Two-Weapon Grace（战斗专长）（PFS不可用） 行尾无闭合 **"),
 C(r"^" + STAR + CN + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE + STAR + r"[ ]?" + BR_OPEN + ENX + BR_CLOSE,
   "FC-1p2 类型前置+英文括号", "**上下合围（战斗，团队）****(Combat, \\nTeamwork)** 中文类型括号在前、英文括号在后（page_1368 L1 型）；须在 FC-3 前——FC-3 的 [ ]?STAR 会吞 4 星闭合导致误抢"),
 C(r"^" + STAR + CN + r"\s*" + ENX + r"(?:[ ]?" + BR_OPEN + EN + r"[）)])?" + FT_SUFFIX + r"[ ]?" + STAR,
   "FC-3 无括号英文", "**中文名 English** / **中文名**\\nEnglish ***（英文在括号外，多空格/换行分隔兼容；类型括号后尾星前容忍空格（护甲大师 (盔甲掌握) *** 型）；英文全大写类型括号容忍（page_673 '**完美集中 PERFECT CENTER (COMBAT)**' 型）"),
 C(r"^" + STAR + CN + STAR + r"\s*" + ENX + r"(?:" + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE + r")?" + STAR,
   "FC-3b 双段加粗", "**中文名** **English**（类型）/ **中文名**** \nEnglish***** 双段加粗族"),
 C(r"^" + CN + r"[ ]+" + ENX + STAR + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE + OSTAR,
   "FC-6c 裸标题四星", "武器专家 Martial Focus****（战斗专长）**** 无行首 ** 但中段四星"),
 C(r"^" + STAR + CN + BR_OPEN + ENX + BR_CLOSE + OSTAR
   + r"(?=\n|\s*$|出自|专长(?:\*\*|\s*$))",
   "FC-1n 单行闭合无标签", "**中文名（English）** 无 feat_type（含跨行英文名；闭合星可缺（专长52 跨行括号'**惊奇大师（Master of \\nWonders）'型、位面冒险PA 灵体打击'（Ethereal Strike）出自《'型）；闭合星后必须行尾或'出自'，同行粘连归 FC-1x/FC-2；'专长**' 尾词变体（闹鬼 '**虚幻杀手（Ghostslayer）专长**' 型）"),
 C(r"^" + STAR + CN + BR_OPEN + r"[A-Za-z][A-Za-z0-9'’\.\-:]*(?:[ ]+[A-Za-z][A-Za-z0-9'’\.\-:]*)*"
   + r"(?:[ ]?:|[ ]?[（(][A-Za-z][A-Za-z0-9, ]*[）)])"       # 必须含冒号（NEW FEAT:）或括号注释
   #（(COMBAT, TEAMWORK)，容忍 OCR I→l 小写混排）——无注释的普通英文名归 FC-1n
   + BR_CLOSE + STAR, "FC-1u 单行闭合全大写", "**中文名（全大写英文 + 冒号/括号注释）** 屠龙者手册型；注释/冒号必选与 FC-1n 区分"),
 C(r"^\[?" + STAR + CN + BR_OPEN + ENX + BR_CLOSE + STAR + r"\]?" + r"[ ]?\(http[^)]*\)",
   "FC-1m 链接包裹", "[**魂刃（Soulblade）**](http://…) markdown 链接包裹条目标题（闹鬼型）"),
 C(r"^" + STAR + CN + BR_OPEN + ENX + BR_CLOSE + r"[〔【［\[]" + FT + r"(?:专长)?[〕】］\]]" + OSTAR,
   "FC-1t 单行闭合+〔类型〕", "**中文名（English）**〔战斗〕 及 【】［］[] 变体"),
 C(r"^" + STAR + CN + BR_OPEN + ENX + r"[，,][ ]*" + FT + BR_CLOSE + r"[：:]?",
   "FC-1c 单行闭合+括号内类型", "**中文名（English，类型）**："),
 C(r"^" + STAR + CN + STAR + r"[ ]?" + BR_OPEN + ENX + r"[，,][ ]*" + FT + r"[ ]*" + BR_CLOSE,
   "FC-1c2 闭合星先型", "**密集阻击** (Barrage of Styles，战斗，团队 ) 中文名闭合加粗后括号内 EN+类型（page_1368 L8 型；容忍括号闭合前空格）"),
 C(r"^" + STAR + CN + BR_OPEN + ENX + BR_CLOSE + STAR + r"[ ]?" + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE + OSTAR,
   "FC-1p 单行闭合+（类型）", "**中文名（English）**（战斗专长）"),
 C(r"^" + STAR + CN + BR_OPEN + ENX + BR_CLOSE + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE
   + r"\s*" + r"(?:STAR)?",
   "FC-1q 单行闭合+（EN）（类型）", "**中文名（English）（故事）**** 类型括号在英文后、闭合星在最后（page_670 型；闭合星可次行（暗影风暴（Gloomstorm）（汲引，战斗）\\n*** 型）或缺失（HA 敌对教团（Enemy \\nCult）（故事）型）；无闭合星需字段标签佐证"),
 C(r"^" + STAR + CN + BR_OPEN + r"[一-鿿][^）)\n]{0,14}" + BR_CLOSE + BR_OPEN
   + r"[A-Za-z][^）]{0,44}" + BR_CLOSE + r"(?:STAR)?",
   "FC-1r 中文括号前置+英文", "**中文名（专名）（English）**** 英文括号前有中文括号（忍受痛苦（宗-库松之吻）（Endure Pain (Zon-Kuthon's）型）；首括号中文锚定防吞英文，英文区容忍内嵌半角括号与跨行；闭合星可缺（闹鬼 作祟拾荒者（造物专长）（Haunt Scavenger，Item Creation）型）；无闭合星需字段标签佐证"),
 C(r"^" + STAR + CN + STAR + r"[ ]?" + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE,
   "FC-8o 双段无英文", "**中文名**（动物伙伴专长) 双段加粗后类型括号、无英文名（专长13 型）；半角闭合括号容忍"),
 C(r"^(?!\*\*(?:先决条件|专长效果|效果|好处|特殊|前提|前置条件|前置|来源|出处|描述|收益|完成收益|制造收益|价格|代价|目标|要求|需求|原文|译者|注)\*\*[ ：:]?)"
   + r"^\*\*" + CN + r"\*\*(?!\*\*)" + r"[^：:（()）\n]",
   "FC-8q 加粗名描述粘连", "**算术占卜**通过将文字…（page_744 型）中文名闭合加粗后同行描述粘连；rest 冒号/括号开头（字段标签 **先决条件**：、**xx**（EN）型）与多段加粗粘连（**A****B** 型，FC-3b 专责）由正则排除；需字段标签佐证"),
 C(r"^" + STAR + CN + STAR + BR_OPEN + ENX + BR_CLOSE,
   "FC-1v 闭合星后括号英文", "**位面训导**（Planar Infusions） 中文名闭合加粗后英文括号（专长12 型）；需字段标签佐证"),
 C(r"^" + STAR + CN + BR_OPEN + ENX + BR_CLOSE + STAR,
   "FC-1x 单行闭合其他", "闭合后还有行尾内容（出自/描述等）；需字段标签跟随佐证"),
 C(r"^" + CN + BR_OPEN + ENX + r"[，,][ ]*" + FT + r"(?:专长)?" + BR_CLOSE,
   "FC-1s 无星括号内类型", "中文名（English，类型）行首无 **（怒嚎挑战（Call Out，战斗专长）型，专长3/河域子民PotR）"),
 C(r"^" + CN + BR_OPEN + ENX + BR_CLOSE + r"[：:]?\s*$",
   "FC-6 无加粗纯文本", "中文名（English）行首无 **（含缩进变体）"),
 C(r"^" + CN + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE + r"\s*$",
   "FC-6i 无加粗中文类型", "秘语（团队专长）裸中文名+类型、无英文名（专长57 型）；需字段标签佐证"),
 C(r"^" + CN + r"[ ]?" + ENX + r"(?:" + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE + r")?" + STAR,
   "FC-8c 无星粘连四星", "掩护射击Covering\nFire（战斗，团队）*****描述 无行首**、英文跨行、星号+描述粘连（专长22 型）"),
 C(r"^" + CN + BR_OPEN + ENX + BR_CLOSE,
   "FC-6g 无加粗括号粘连", "长气潜水（Long\nbreath 你屏住… 跨行括号+描述粘连（水下冒险型）；需字段标签佐证"),
 C(r"^" + CN + STAR + BR_OPEN + ENX + BR_CLOSE + STAR + r"(?=[一-鿿]|\s*$)",
   "FC-8k 星夹括号跨行", "中文名**（English\nEnglish）**描述 行首无星、2 星夹括号（专长58 型）；与 FC-6g（CN 后直接括号）不重叠"),
 C(r"^" + STAR + CN + STAR + r"\s*$",
   "FC-8n 裸中文加粗", "**截肢** 独立行裸中文加粗无英文无类型（page_744 型）；需后行单星 *描述* 佐证（与 FC-7 次行英文佐证互补）"),
 C(r"^\*\*(" + CN + r")[：:]\s*\*\*$",
   "FC-8p 冒号加粗行", "**可信伪装：** 独立加粗标签行（ISI 型条目名后置冒号）；字段标签行（**先决条件：** 等）由佐证排除表排除，正文 **重要：** 型由字段标签佐证排除"),
 C(r"^" + OSTAR + CN + r"(?:[（(]" + FT + r"[）)])?" + BR_OPEN + STAR + ENX + STAR + BR_CLOSE
   + r"(?:【" + FT + r"】)?" + r"\*{4}(?!\*)\s*$",
   "FC-8l 星括四星行尾", "中文名（类型）（****English****）**** 括号内 4 星包裹英文、闭合星恰 4 星且必须行尾（page_552/527 型）；6 星噪声闭合（****** = 4+2）与同行描述（魔宠手记FF 章节标题）均被排除"),
 C(r"^" + CN + r"[！!]?" + r"[ ]?" + ENWE
   + r"(?:[ ]+" + ENWE + r")*"
   + r"(?:\s*\n\s*" + ENWE + r"){0,2}"
   + r"\s*[（(](?i:su|sp|ex)[）)](?:[：:]|[ ]*pfs[ ]*x[ ]*|[ ]*)",
   "FC-6h 无加粗能力类型", "奥法导管eldritch conduit（su）：描述（职业天赋型）；容忍！断名（我刚一直在这儿！）、HTML实体（Fa&ccedil;ade）、PFS标注吞冒号（Unlock Ki (Ex) pfs x）"),
 C(r"^" + CN + ENW + r"(?:[ ]+" + ENW + r"|\s*\n\s*" + ENW + r")*" + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE + r"\s*$",
   "FC-6b 无加粗粘连", "中文名English（类型）无空格粘连（容忍英文跨行：狂暴增幅Amplified\nRage（团队）型）"),
]

# 粘连行内标题（KN012 同型）：全角双空格后的 **中文名（English）**，标题不在行首
GLUE_RX = re.compile(r"(?<=　　)" + STAR + CN + BR_OPEN + ENX + BR_CLOSE + STAR)

# FC-2 冠位粘连族（page_670 型）：**中文名**English*描述 同行/跨行粘连，
# 闭合是单星号故与 FC-3/3b（需 2+ 星）不重叠
CROWN_RX = re.compile(r"\*\*(?!\*)" + CN + r"\*\*(?!\*)" + ENX + r"\*(?!\*)")

# FC-8 段流族（异能选集PA 型）：中文名（English）（类型）描述… 整段粘连无换行无加粗，
# 标题前有句号或粗体结尾。仅统计行中位置（非行首），行首情形由行级簇负责。
# 尾部二选一：(类型) 括号（游荡诡计（Bouncing Trick）（诡计））或 星号（**元素学识（Elemental Knowledge）***），
# 二者都不满足即视为正文（如 注视专长（Stare Feats）注视专长允许…）不计数
STREAM_RX = re.compile(r"(?:(?<=。)|(?<=\*\*))" + CN + BR_OPEN + EN + BR_CLOSE
                       + r"(?:" + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE
                       + r"|(?:\*(?!\*)|\*{3}(?!\*)))")
# 星号分支排除恰 2 星（markdown 加粗闭合，如章节标题 **冠位专长(Vested Feats)**）
# —— 真条目是 1 星脏星（**元素学识（Elemental Knowledge）*）或 3 星闭合

# FC-8b 段流跨行英文族（初探探索者型）：**中文名 English\nEnglish*描述 粗体后粘连
STREAM_X_RX = re.compile(r"(?<=\*\*)" + CN + r"[ ]?" + ENX + r"\*(?!\*)")

# FC-8c 段流类型前置跨行（初探探索者型）：。中文名（战斗）PATIENT \nSTRIKE (COMBAT)*描述
# 与 STREAM_RX（英文在括号内）互补：类型括号在前、英文裸奔跨行、星号闭合描述。
# 英文尾缀（(COMBAT) 别名）与空格在星号前需容忍；
# `(COMBAT)*` 形态空格在括号前（STRIKE (COMBAT)*），括号容忍组自带 [ ]? 前缀
STREAM_C_RX = re.compile(r"(?<=。)" + CN + r"(?:[ ]?" + BR_OPEN + FT + r"(?:专长)?" + BR_CLOSE + r")?[ ]?" + ENX
                         + r"(?:[ ]?[（(][^）)\n]{1,25}[）)])?[ ]?\*{1,3}(?!\*)")

# FC-8d 段流双段加粗（初探探索者型）：。**声誉**** RENOWN*** / 。****快速转进**** CUT YOUR\nLOSSES***
# \*{0,4} 容忍 4 星行首前缀（`。****快速` 中 CN 必须跳过全部 4 星），\*{3,} 排除 2 星闭合
# （**中文名**English* 归 FC-2 冠位粘连），避免与 CROWN_RX 重叠
# 变体：卑鄙协作型 `**卑鄙协作****(****战斗，团队****) UNDERHANDED\nTEAMWORK (COMBAT, TEAMWORK)***`
# —— 类型括号内嵌星号包裹、ENX 后跟英文括号别名，均需容忍；
# 标题前置分隔符含源数据脏点（`高2.**标题` 半角句点），lookbehind 兼容数字/字母后句点
STREAM_D_RX = re.compile(r"(?:(?<=。)|(?<=[0-9a-zA-Z]\.))\*{0,4}" + CN + r"\*{3,}"
                         + r"(?:[（(]\*{2,}" + FT + r"\*{2,}[）)])?"   # (****类型****) 星号括号类型
                         + r"\s*" + ENX   # \s* 而非 [ ]?：类型括号后可能是空格+换行（英文名在次行）
                         + r"(?:[ ]?[（(][A-Za-z][^）)\n]{0,24}[）)])?"  # (COMBAT, TEAMWORK) 英文别名
                         + r"\*{1,3}(?!\*)")

# FC-7 裸中文星号族（page_321/page_538 型）：中文名****（可有行首 **），
# 英文名单列次行；需次行英文佐证以排除小节标题（如 武器大师"近战武器掌握专长****"）
FC7_RX = re.compile(r"^" + OSTAR + CN + r"[ ]?" + STAR + r"\s*$")
NEXT_EN = re.compile(r"^" + OSTAR + ENW)
# FC-7c 裸中文行（无星号）+ 次行全大写英文短语（专长5 型《冥思启悟》）
CN_LINE_RX = re.compile(r"^[一-鿿][一-鿿·/\-]{1,}$")
ALLCAPS_RX = re.compile(r"^[A-Z][A-Z0-9'’\. ·\-]{2,}$")
# FC-7b 同行英文变体（page_321 后半）：中文名**** English（可有行首 **、尾部星号/类型），
# 英文同行本身就是佐证，无需次行检查。分类标题排除：CN 以"专长"结尾
# （位面导师系列专长 Plane-Hopper 型章节标题，专长12 L1）——真条目名不以
# "专长"收尾（魔法专攻/武器专攻均以"攻"结尾），lookbehind 定长 2 字符
FC7B_RX = re.compile(r"^" + OSTAR + CN + r"(?<![一-鿿·/\-]专长)" + STAR + r"[ ]?" + ENX)
# FC-8f 无加粗双标签粘连（page_670 型）：乐府训练你…先决条件：…专长效果：…
# 行首中文（可容忍（ 残缺闭合）、无星无括号英文名，行内含'先决条件'+'专长效果'
# 双标签是条目格式特征（正文描述不会同行双标签）
FC8F_RX = re.compile(r"^[（(]?" + CN + r"[^\n]*先决条件[^\n]*专长效果")

# FC-8e 段流英文裸奔（药剂与毒药P&P 型）：。中文名 English（类型）描述… /
# 。中文名 \nEnglish描述…（\r 断行把条目拆成'行尾中文名+行首英文名'跨行对）。
# 尾部三选一：（类型）括号 / ** 加粗闭合 / 中文描述直连；'。' 句号是条目
# 起点锚（前面是上一条目描述结尾）。条目名后必须有 1+ 空格（正文缩写粘连
# '以DC' 无空格排除）；[ ]+(?:\n[ ]*)? 容忍行尾空格+断行（英文名在次行，
# ENX 以字母开头故断行须在 CN 与 ENX 之间消化）
STREAM_E_RX = re.compile(r"(?<=。)" + OSTAR + CN + r"[ ]+(?:\n[ ]*)?" + ENX
                         + r"(?:[ ]?[（(]" + FT + r"(?:专长)?" + r"[）)][ ]?|\*\*|(?=[一-鿿]))")

# FC-8h 星包裹英文粘连（魔宠手记FF 型）：。中文名（类型）****English (Familiar)*描述
# 行内粘连——条目名后可选（类型）括号、英文名 2~4 星包裹 + 单星闭合 + 描述直连。
# 类型括号必选：与 FC-8d（.中文名****English* 无括号 4 星）互补不重叠；
# 英文名后容忍 (Familiar)/(Teamwork) 括号与跨行断行（锦囊妙计 ****Sage's\n
# Guidance (Familiar)* 型：英文包裹 2 星、' 为右单引号 U+2019）；
# 章节标题（**魔宠专长（****Familiar Feats****）****）英文后是 ****）+ 闭合
# → 单星 lookahead (?!\*) 排除；行首无 。 前缀（章节标题列行首）同样排除
FF_RX = re.compile(r"(?<=。)[】]?" + CN + r"[（(]" + FT + r"(?:专长)?" + r"[）)]"
                   + r"\*{2,}" + ENX
                   + r"(?:[ ]?[（(](?:Familiar|Teamwork)[）)])?"
                   + r"\*(?!\*)")

# FC-8k 段流变体（专长58 型）：章节标题+条目同行粘连
# （梭螺鱼人专长****盟友呼唤**（Ally\nCaller）**你…）——条目名紧跟章节标题的
# 4 星闭合后同行，行级 ^ 锚定（行首是章节标题）捕获不到，用星号 lookbehind
# 补充；与行级 FC-8k（^ 锚行首）互不重叠。lookbehind 固定 4 星宽度（Python re
# 限制）：CN 前恰为章节标题 4 星闭合（2 星加粗闭合 **中文名**（…）与 3 星描述
# 行 ***描述（English）** 型均被排除，page_527 描述行佐证过）
FF8K_STREAM_RX = re.compile(r"(?<=\*{4})" + CN + r"\*{2}" + BR_OPEN + ENX + BR_CLOSE
                             + r"\*{2}(?=[一-鿿]|\s*$)")

# FC-8e 无星裸英文粘连（水下冒险型）：深呼吸Deep\nbreath 你屏住…先决条件 行首无星无括号，
# 英文同行/跨行、无星号；需同行或后 6 行字段标签佐证（描述粘连必有先决条件）。
# 英文名捕获到 en 组：≤3 字符（PFS/GM/DC5/CMD/CRB）或紧跟数字（召唤环级 B3）是正文
# 标注/数据特征，非条目——收窄判据在 match_file 的 FC-8e 兜底处实施
FC8E_RX = re.compile(r"^" + CN + r"[ ]?(?P<en>" + EN + r")(?=$|[^A-Za-z0-9０-９])")

# FC-1o 加粗断行族（专长52 型）：**中文名English… 跨行断行、括号残缺（左括号
# 丢失/英文名断行），行内无括号、行尾无闭合星。佐证：后 3 行内出现 *** 描述
# 开头行。有括号的断行形态（**中文名（English\n））归 FC-1n 跨行窗口；类型
# 括号闭合无尾星（**撒泼打滚Tantrum（战斗））归 FC-6e。
# CN 后不容忍冒号：**先决条件：/ **专长效果： 字段标签行排除（page_321 型）
FC1O_RX = re.compile(r"^" + STAR + CN + r"[^（()）\n：:]*$")

# FC-8m 裸中文效果行（page_668 型）：'残酷施法你从不关心…效果：…' 行首中文名
# （≥2 字）+描述+行内'效果：'标签，无星无括号英文名（缩进 0-4 空格均可）。
# 排除：行首字段标签（'先决条件：…效果：'/'专长效果：' 型——武器大师手册 36 处、
# page_538 25 处、魔法战术工具箱 25 处误伤源）；前 3 行有 #/** 标题（BotB 型
# '你能变成一只狐狸…' 是条目标题的描述首行，条目已由标题簇计数）。行首空格在
# match_file 已 strip，缩进判据用原始行（lines[i]）在兜底处实施
FC8M_RX = re.compile(r"^(?!先决条件|专长效果|完成效果|前置|条件|好处|描述)"
                     + r"[一-鿿][一-鿿·/\-]{1,}" + r"[^\n]{0,120}效果[：:]")

# FC-8m 行内多条目变体（page_694 型）：同逻辑行内'条目名 + ≤120 字 + 效果：'
# 多段粘连（'大地魔法…效果：…精类表演风…效果：…'）——无 ^ 锚定，findall
# 计每段；CN 贪婪吃描述段到标点为止（lookahead 校验后 120 字内有效果标签）
# 已废弃：段级 findall 在长粘连行（page_694 一行 5 条目 47 段）上爆炸，
# 行内条目数改按"效果[：:]"标签数计（见 match_file FC-8m 行内多条目块）
FC8M_INLINE_RX = None

# 条目名规范形（CN（EN））：STREAM_RX 段流命中与行级簇命中按此去重
#（专长45 任务物品区/造物专长一览 正文引用双计源）
TITLE_RX = re.compile(CN + BR_OPEN + r"[^）)\n]*" + BR_CLOSE)

IMG_PREFIX = re.compile(r"^!\[\[[^\]]*\]\](?:\([^)]*\))?\s*")
DATA_TABLE_HDR = re.compile(r"调整值|修正|数值|[＋－±]")
# 回溯中仅字样判据（无符号）：符号（＋－±）在数据行常见（前置列"| － |"=无前置、数值列"＋2"），只有组首才用符号兜底
DATA_HDR_WORD = re.compile(r"调整值|修正|数值")
ROW_NUM = re.compile(r"[0-9０-９]")

def is_feat_table(lines, i):
    """FC-T 命中行 i：向上回溯组表头，判别条目表（True）或规则数据表（False）。
    条目表特征：表头含'专长名称/名称/前置/先决条件'（TABLE_HDR）；数据表特征：
    表头含'调整值/修正/数值'（专长.md 领袖声誉表型）或组首数据行含调整值符号/
    数字环级（'| 1环 |' 怪物召唤表型）。无特征词表头（'| 通用专长 |' 分类小节行
    / '| 召唤生物 |' 怪物表头）向下找组内 TABLE_HDR 区分；回溯允许跳过 ≤2 空行
    （page_203 表头与数据行间有 1 空行），超过即组间边界。"""
    hdr = lines[i].strip()
    j = i
    blanks = 0
    while j > 0:
        raw = lines[j - 1]
        l = raw.strip()
        if not l:
            blanks += 1
            if blanks > 2:
                break
            j -= 1
            continue
        if not l.startswith("|"):
            # 缩进续行（列断行：'       蝰蛇打击* | 用毒…' 中文含|，
            # '       dueling mastery*' 英文行）→ 跳过继续回溯。
            # 用 raw（保留缩进）判定：strip 后前导空格丢失
            if re.match(r"^[ 　]+", raw) and (re.match(r"^[A-Za-z]", l) or "|" in l):
                j -= 1
                continue
            break
        if TABLE_SEP.match(l):
            j -= 1
            continue
        blanks = 0
        # 表头行双判据：TABLE_HDR 关键词（专长名称/名称…先决条件），
        # 或"下一行是分隔行 + 表头特征词"（'| 种族专长 | 先决条件 |' 型；
        # 怪物表头'| 召唤生物 |' 无特征词 → 落入 hdr 走向下扫描）
        if TABLE_HDR.search(l) or (
            j < len(lines) and TABLE_SEP.match(lines[j].strip()) and HDR_FIELD.search(l)
        ):
            return True
        if DATA_HDR_WORD.search(l) and j < len(lines) and TABLE_SEP.match(lines[j].strip()):
            return False       # 数据表头（'| 领袖声誉 | 调整值 |' 下一行必为分隔行）；
            # 数据行描述含'调整值/修正'字样（'感知调整值'）不算
        hdr = l
        j -= 1
    # 组首（hdr）判别：数字环级行 / 调整值符号行 → 数据表
    if ROW_NUM.search(hdr.split("|")[1] if "|" in hdr else hdr) or DATA_TABLE_HDR.search(hdr):
        return False
    # 无特征词表头：向下找组内 TABLE_HDR（'| 通用专长 |' 后跟'专长名称'表头 →
    # 条目表；'| 召唤生物 |' 后跟数据行 → 数据表）。组尾=2 空行或非表格内容。
    k = i
    blanks = 0
    while k < len(lines):
        raw = lines[k]
        l = raw.strip()
        if not l:
            blanks += 1
            if blanks > 2:
                break
            k += 1
            continue
        if not l.startswith("|"):
            if re.match(r"^[ 　]+", raw) and (re.match(r"^[A-Za-z]", l) or "|" in l):
                k += 1
                continue
            break
        blanks = 0
        if TABLE_HDR.search(l):
            return True
        # 怪物召唤表数据行（'| 1环 |' 首单元格数字）→ 数据表
        if ROW_NUM.search(l.split("|")[1] if "|" in l else l):
            return False
        k += 1
    return False

def is_split_row(lines, i):
    """跨行断表配对去重：英文首单元格表格行（1| 未闭合型 page_553/361，
    或 3| 完整型 page_566）后 4 行窗口内出现 ≥2| 且首单元格以中文开头的
    闭合行 → 本行是冗余首行（同一条目双行），跳过由闭合行计数。
    判据必须「以中文开头」而非「含中文」（v2.2 决策 F 修复）：
    K5 修复（aa6b3ff）把 \r 裸断行合并为单行表「英文名+空格+中文名」后，
    单行表相邻行首单元格都含中文译名（'| Catch Off-Guard* 随手武器* |'），
    「含中文」判据会误杀整表（page_195 判别器计数 171→1）；
    真断表闭合行是纯中文首单元格（'| 鲨蜥流 |'），以中文开头——收窄后
    两者区分。窗口 4 行为 \r 裸断行时代遗留（跨行 3| 英文行拆 3 个逻辑行，
    闭合行落 +3 位），K5 后单行形态闭合在 +1 位，窗口仍覆盖无副作用。
    中文首单元格 3| 行（page_856 独立条目）、page_199/203 型
    （续行缩进无 |，无中文闭合行）不受影响。"""
    line = lines[i].strip()
    cell = line.split("|")[1] if "|" in line else ""
    if not re.match(r"^[A-Za-z]", cell.strip()):
        return False
    for k in range(i + 1, min(i + 5, len(lines))):
        l = lines[k].strip()
        if l.startswith("|") and l.count("|") >= 2:
            c = l.split("|")[1] or ""
            if re.match(r"^[一-鿿]", c.strip()):
                return True
    return False

def logical_lines(text):
    return re.split(r"\r\n|\r|\n", text)

# 字段标签佐证词：**标签**： 形态（容忍闭合星号阻隔冒号），正文提及
#（"满足先决条件"/"专长效果1次"/"以此为前提"）冒号后无闭合星号 → 不匹配。
# 无该锚定时正文段会误通过佐证（专长37 战团专长 L1/L4 根因）
FIELD_LABEL = re.compile(r"(?:先决条件|专长效果|好处|前提|描述)(?:\*{0,2}[：:])"
                         r"|前置条件(?:\*{0,2}[：:]|\*\*)"
                         r"|前置(?:\*{0,2}[：:])"
                         r"|(?<!完成)收益(?:\*{0,2}[：:])"
                         r"|效果(?:\*{0,2}[：:])")
# 收益 带 lookbehind：排除'完成收益：'（专长45 任务物品字段）——该字段是
# 魔法物品特征，若作为佐证词会放行任务物品行；**收益：**（page_744）是条目字段
# 内嵌子标题：**中文名 English（或跨行）**（类目小节正文里嵌套的子条目标题）。
# CN 后容忍：空格+英文（同行）、行尾（英文在次行）、换行；标签型 **专长效果：** 不含
SUBTITLE_RX = re.compile(r"\*\*(?!\*)" + CN + r"(?:[ ]?[A-Za-z]| *$|\n)")

def match_file(text):
    """返回 (Counter簇计数, [(行号, 行文本) 未命中候选])"""
    lines = logical_lines(text)
    counts = Counter()
    misses = []
    seen = set()   # 行级簇已计条目名规范形（CN（EN））：STREAM_RX 段流引用按此去重
    i = 0
    n = len(lines)
    while i < n:
        line = IMG_PREFIX.sub("", lines[i]).strip()
        if not line:
            i += 1; continue
        # 表格分隔行/表头行直接跳过（非条目）；表头双判据同 is_feat_table；
        # 区段表头（'| 团队专长 | 先决条件 |…'）无分隔行跟随，单列判据跳过
        if TABLE_SEP.match(line) or TABLE_HDR.search(line) or SEG_HDR.match(line) or (
            i + 1 < n and TABLE_SEP.match(lines[i + 1].strip()) and HDR_FIELD.search(line)
        ):
            i += 1; continue
        window = line
        hit = None
        for name, rx, _note in CLUSTERS:
            m = rx.match(window)
            if m:
                hit = name
                break
        if hit is None and "\n" not in window:
            # 跨行窗口（最多 4 行）只试一次，避免 N²
            for k in range(1, 4):
                if i + k >= n:
                    break
                nxt = IMG_PREFIX.sub("", lines[i + k]).strip()
                window = window + "\n" + nxt
                for name, rx, _note in CLUSTERS:
                    m = rx.match(window)
                    if m:
                        hit = name
                        break
                if hit:
                    break
        # FC-1n 佐证：真条目（**中文名（English）** 无标签）后必有字段标签
        #（前置条件/先决条件/专长效果）。10 行窗口覆盖专长28 型（标签在 +8 行）；
        # 位面谐律章节/位面小节标题（**深渊（Abyss）** 型）后是描述无标签 → 排除
        if hit == "FC-1n 单行闭合无标签":
            follow = "\n".join(lines[i + 1:i + 11])
            if not FIELD_LABEL.search(follow):
                hit = None
        # FC-1x/FC-6g/FC-1v/FC-6i 兜底簇需要"字段标签跟随"佐证（后 6 行内出现
        # 字段标签），否则视为非条目加粗/正文（如 异能选集引言段 奥利瓦罗小品曲集
        # （The Olivaro…）、专长33 召唤表生物行 小妖精（Sprite） Bestiary 型）。
        # FC-6g 另需"佐证窗口未断裂"：窗口内出现裸 4 星章节标题行（中文名****
        # 行尾闭合，专长58 型）说明窗口越界到下一章节，后续字段标签属于别条目
        # → 佐证无效。字段标签检查是组内独立 elif（对 FC-1x/FC-6g/FC-1v/FC-6i
        # 全部生效）——曾嵌在 FC-1x rest 分支内导致 FC-6g 等漏查（专长33
        # 生物行 33 条误计根因）
        if hit in ("FC-1x 单行闭合其他", "FC-6g 无加粗括号粘连",
                   "FC-1v 闭合星后括号英文", "FC-6i 无加粗中文类型"):
            follow = "\n".join(lines[i + 1:i + 7])
            if (hit == "FC-6g 无加粗括号粘连"
                    and (re.search(r"^" + CN + r"\*{2,}\s*$", follow, re.M)
                         or (m and re.search(
                             r"可获得以下|下列专长|专长如下|如下专长|以下专长",
                             window[len(m.group(0)):].split("\n")[0]))
                         or (m and re.match(
                             r"^[，,]\s*" + CN + r"[（(]",
                             window[len(m.group(0)):].split("\n")[0].lstrip("　 \t"))))):
                # 断裂：窗口越界到下一章节；介绍句：括号英文后的中文续行
                # "半精灵可获得以下专长。"（海滨后裔（Shoreborn）半精灵可
                # 获得以下专长。型小节标题，专长24）——"可获得以下专长"是
                # 种族专长文件的类别介绍句特征，真条目 rest（**PFS不可**/
                # 描述粘连）不含；逗号双名字：'静思者（Sage…）, 漫游者
                # （Wanderlust）'（专长45 推荐背景行）——同一行两个条目名
                hit = None
            elif hit == "FC-1x 单行闭合其他" and m:
                # 同行剩余佐证：闭合星后同行剩余剥全角空格后若以中文段落开头
                # （非 * / > / 空），是章节标题或术语定义（page_670 冠位专长(Vested
                # Feats) 型），非条目标题——真条目闭合后是换行、*描述 或 出处尾注。
                # 豁免：闭合星 ≥3（**闭合 2 星 + 单星 *描述* 起始，专长10 塔尔多的
                # 私掠船员（Corsair of Taldor）*****描述 型）→ 中文剩余是描述粘连，
                # 保留；恰 2 星 + 中文剩余才是章节标题
                rest = window[len(m.group(0)):].split("\n")[0].lstrip("　 \t")
                tail_star = re.search(r"[）)](\*+)$", m.group(0))
                if rest and not rest.startswith(("*", ">", "：")):
                    # PFS 标注粘连（**引导圣临（Channel Deific Essence）**PFS不可用 型）
                    # 是条目标题后置标注，非章节标题；出处尾注（**通才（Dilettante）**
                    # 出自《秘密探寻者》/ **惩戒召唤（Retributive Summoning）**
                    # Plane-Hopper's Handbook pg. 13 型）同为真条目尾注——豁免
                    # 且无需字段标签佐证（秘密探寻者SoS 型文件字段为 **需求** 无
                    # 冒号，不在 FIELD_LABEL 内，出处尾注本身就是强佐证）
                    if not (rest.startswith("PFS")
                            or re.search(r"出自|pg[.．]", rest)
                            or (tail_star and len(tail_star.group(1)) >= 3)):
                        hit = None
                elif not FIELD_LABEL.search(follow):
                    hit = None
            elif not FIELD_LABEL.search(follow):
                hit = None
        # FC-3 佐证：闭合星后同行剩余非空（中文描述粘连）→ 直接保留（战策 Combat
        # Trick**你可以花费… 型）；空（纯标题行）→ 需字段标签跟随，排除类目标题
        # （护甲大师"盔甲掌握专长Armor Mastery Feats**"型，后随正文无字段标签）。
        # 后 7 行窗口（i+1:i+8）：AG 型条目描述 5-6 行时'**前置条件**'标签落在
        # +7 行（旧 5 行窗口漏检 → 6 条欠计）
        if hit == "FC-3 无括号英文" and m:
            rest = window[len(m.group(0)):].split("\n")[0].lstrip("　 \t")
            if not rest:
                follow = "\n".join(lines[i + 1:i + 8])
                if not FIELD_LABEL.search(follow):
                    hit = None
            elif SUBTITLE_RX.search(rest):
                # 类目小节型：rest 内嵌 **中文名 English (类型)：** 子标题列表
                # （护甲大师"重甲技法 Heavy Armor Tricks **…**甲隙藏刃 Blade…"型），
                # 与条目标题（描述直连或 ***字段标签衔接）区分
                hit = None
            elif re.search(r"拥有以下|可获得以下", rest):
                # 介绍句型：'**武器技法WEAPON TRICKS**是拥有以下武器技法专长…'
                # （MAH L167 型）类目总述行——真条目描述以'你可以/你获得'开头
                hit = None
        # FC-8c 佐证：简介提及型（护甲大师手册 流派简介段"中文名 English**：一句
        # 话。**"）同行剩余以全角冒号开头 → 排除；条目型后随 *****描述 或 **（类型）**
        if hit == "FC-8c 无星粘连四星" and m:
            rest = window[len(m.group(0)):].split("\n")[0].lstrip("　 \t")
            if rest.startswith("："):
                hit = None
        # FC-8c 区段标题行（P&P 型）：前 2 行含 ## → '区段名+英文名'行（蝮血裔
        # 专长 Vishkanya）经跨行窗口误吞下行的 ** 当 STAR → 非条目，排除
        if hit == "FC-8c 无星粘连四星" and any(
            lines[k].strip().startswith("#") for k in range(max(0, i - 2), i)
        ):
            hit = None
        # 正文重复行（武术手册型：## 标题 + 正文首行粘连'中文名（类型）English**'
        # 双计）：FC-4b/FC-3b 命中行前 2 行窗口内有井号标题 → 该标题的正文，排除
        if hit in ("FC-4b 裸类型前置", "FC-3b 双段加粗") and any(
            lines[k].strip().startswith("#") for k in range(max(0, i - 2), i)
        ):
            hit = None
        # FC-6 无加粗纯文本：后 4 行内出现裸 --- 分隔线 → 正文小节标题/断行碎片
        # （位面谐律编注、漫游者推荐背景断行），非条目；括号内英文全小写
        # （坐骑职业能力（mount class feature）型）是字段内容里的译注而非条目
        # 名——真条目英文名均为 Proper Case（高原适应力（Altitude Affinity）型），
        # 全小写判据零误伤（专长57/CaC L40 各 1 条）
        if hit == "FC-6 无加粗纯文本":
            nxt = "\n".join(lines[i + 1:i + 5]).strip()
            if re.match(r"^-{3,}$", nxt, re.S):
                hit = None
            elif m:
                inner = re.search(r"[（(]([^（）()]*)[）)]\s*$", m.group(0))
                if inner and not re.search(r"[A-Z]", inner.group(1)):
                    hit = None
            elif not FIELD_LABEL.search(nxt):
                # 正文小节标题（专长14 古奥斯里昂（Ancient Osirion）等 10 条、
                # 专长28/OO 各 1 条）后随正文段落无字段标签 → 排除；真条目
                #（page_553 高原适应力（Altitude Affinity）等 26 条）后随
                # 先决条件/效果字段保留。任务物品/刺青物品（完成收益/灵光/
                # 价格/制造条件字段，FIELD_LABEL 不含且收益带 lookbehind）同被排除
                hit = None
        # FC-7 裸中文星号族：行级兜底，需下一个非空行以英文开头佐证
        if hit is None and FC7_RX.match(line):
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n and NEXT_EN.match(IMG_PREFIX.sub("", lines[j]).strip()):
                hit = "FC-7 裸中文星号"
        # FC-7c 裸中文行+全大写英文次行（专长5 型：多样尊崇\nDIVERSE\nOBEDIENCE）：
        # 无星号裸中文名行 + 次行全大写英文短语（该书的条目英文名排版为全大写分行）
        # + 后 6 行字段标签。全大写判据排除普通正文段落（中文/小写英文续行）
        if hit is None and CN_LINE_RX.match(line):
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n and ALLCAPS_RX.match(IMG_PREFIX.sub("", lines[j]).strip()):
                follow = "\n".join(lines[i + 1:i + 7])
                if FIELD_LABEL.search(follow):
                    hit = "FC-7c 中文行全大写英文"
        # FC-7d 裸中文短标题（专长57 型）：驯养植物/怪物伙伴 无星无括号无英文
        # 的 4-6 字标题行 + 空行 + 描述 + 字段标签。三重排除：行长 2-3 字
        # （感知/意志/引用/出自 型字段值与标注）、"专长"结尾（新矮人专长/
        # 黑市专长 型章节标题）、前后 2 行内字段标签行（字段值/续行误判）
        # ——真条目标题前后是空行/描述，字段标签只出现在后 6 行佐证窗口内
        if hit is None and CN_LINE_RX.match(line) and 4 <= len(line) <= 6 \
                and not re.search(r"专长$", line):
            if not any(
                re.match(r"^\*{0,2}(先决条件|效果|特殊|好处|前提|前置条件|描述)[：:]",
                         lines[k].strip())
                for k in range(max(0, i - 2), min(n, i + 3)) if k != i
            ):
                follow = "\n".join(lines[i + 1:i + 7])
                if FIELD_LABEL.search(follow):
                    hit = "FC-7d 裸中文短标题"
        # FC-8n 裸中文加粗：后行单星包裹 *描述* 佐证（page_744 型）；
        # 佐证失败回落 FC-7 判据（次行英文名——page_538 '****酩酊侠****' 型
        # 4 星包裹 + 英文名次行），与 FC-8n 后行中文描述互补；两者皆否排除
        if hit == "FC-8n 裸中文加粗":
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            nxt = lines[j].strip() if j < n else ""
            if not (nxt.startswith("*") and nxt.endswith("*") and not nxt.startswith("**")):
                if j < n and NEXT_EN.match(IMG_PREFIX.sub("", nxt)):
                    hit = "FC-7 裸中文星号"
                else:
                    hit = None
        # FC-1q/FC-1r 无闭合星变体需字段标签跟随佐证（HA '**敌对教团（Enemy
        # \nCult）（故事）' 型、闹鬼 '**作祟拾荒者（造物专长）（Haunt
        # Scavenger，Item Creation）' 型）；有闭合星（page_670/专长45 型）
        # 形态自证，直接保留
        if hit in ("FC-1q 单行闭合+（EN）（类型）", "FC-1r 中文括号前置+英文") and m:
            if not re.search(r"[）)]\*+", m.group(0)):
                follow = "\n".join(lines[i + 1:i + 7])
                if not FIELD_LABEL.search(follow):
                    hit = None
        # FC-8p 冒号加粗行：字段标签行（**先决条件：** 等）排除表排除；
        # 后 6 行字段标签佐证（正文 **重要：** 型后无字段标签；ISI 条目
        # **可信伪装：** 后随 前置/效果 字段）
        if hit == "FC-8p 冒号加粗行":
            m8p = re.match(r"^\*\*(" + CN + r")[：:]\s*\*\*$", line)
            if m8p and re.match(
                r"^(先决条件|专长效果|效果|好处|特殊|前提|前置条件|前置|来源|出处|"
                r"描述|收益|完成收益|制造收益|价格|代价|目标|要求|需求|原文|译者|注)$",
                m8p.group(1)
            ):
                hit = None
            else:
                follow = "\n".join(lines[i + 1:i + 7])
                if not FIELD_LABEL.search(follow):
                    hit = None
        # FC-8q 加粗名描述粘连：需字段标签跟随佐证（page_744 条目后随
        # **先决条件：**/**收益：**；正文 **强调**文字 型后无字段标签）
        if hit == "FC-8q 加粗名描述粘连":
            follow = "\n".join(lines[i + 1:i + 7])
            if not FIELD_LABEL.search(follow):
                hit = None
        # FC-7b 同行英文变体：英文同行即佐证
        if hit is None and FC7B_RX.match(line):
            hit = "FC-7b 同行英文"
        # FC-8m 裸中文效果行（page_668 型）：原始行首 0-4 空格 + strip 后行首中文
        # ≥2 字 + 行内'效果：'标签（strip 后 line 匹配，缩进判据用原始行 lines[i]）；
        # 前 3 行有 #/** 标题 → 条目标题的描述续行，排除
        if hit is None and FC8M_RX.match(line) and re.match(r"^[ ]{0,4}\S", lines[i]) \
                and not any(lines[k].strip().startswith(("#", "**")) for k in range(max(0, i - 3), i)):
            # 行内多条目（page_694 型：'大地魔法…效果：…精类表演…效果：…'
            # 同逻辑行多段粘连）：按行内'效果：'标签数计条目——每条目恰好 1 个
            # 效果标签（page_670 加粗字段/673/668 无加粗各 1 个、694 一行 5 个
            # 均验证）；描述段任意中文串前视'效果：'的段级 findall 会爆炸
            # （694 一行 47 段），标签数才是条目数。单条目行走常规 hit 计数
            n_inline = len(re.findall(r"效果[：:]", line))
            if n_inline > 1:
                counts["FC-8m 裸中文效果行"] += n_inline
                i += 1
                continue
            hit = "FC-8m 裸中文效果行"
        # FC-1o 加粗断行族：**中文名English 行内无括号无闭合星（跨行断行/括号
        # 残缺）+ 后 3 行窗口内出现 *** 描述开头行 → 条目（B1 型')**'续行在
        # +1、B2 型英文名续行在 +1、*** 描述在 +2）；无 *** 跟随（正文段落/
        # 字段标签行）→ 排除。佐证须恰 3 星：4 星行（****条目**** 型）是
        # FC-7 族条目标题，以 *** 前缀误纳（page_538 章节标题误计来源）。
        # 行内含 ****（**神名****描述 章节标题粘连）→ 4 星形态归 FC-7/7b
        if hit is None and "****" not in line and FC1O_RX.match(line):
            if any(
                lines[k].strip().startswith("***")
                and not lines[k].strip().startswith("****")
                for k in range(i + 1, min(i + 4, n))
            ):
                hit = "FC-1o 加粗断行"
        # FC-8e 无星裸英文粘连：描述粘连必有字段标签，同行或后 6 行佐证；
        # 英文名 ≤3 字符（PFS/GM/DC/CMD/CR/CRB 缩写）是正文标注非条目——
        # 真条目英文名 ≥4（酷寒敏捷Cold/深呼吸Deep/豭突刺Boar）；
        # 前 2 行含 ## → 区段标题行/标题下正文首行（'树蛙人专长 Grippli'
        # 区段名行、武术手册'实用形Practical Kata'标题下粘连双计型）非条目
        if hit is None:
            m8 = FC8E_RX.match(line)
            if m8 and len(m8.group("en")) >= 4 \
                    and not line.startswith(("出自", "来源", "出处")) and not any(
                lines[k].strip().startswith("#") for k in range(max(0, i - 2), i)
            ):
                follow = line + "\n" + "\n".join(lines[i + 1:i + 7])
                if FIELD_LABEL.search(follow):
                    hit = "FC-8e 无星裸英文粘连"
        # FC-8f 无加粗双标签粘连（page_670 型）：行首中文+行内双标签=条目。
        # 前 6 行窗口有标题行（##/**）→ 该行是标题条目的描述续行（野兽血脉
        # 21/武术手册 4/page_856 4 双计来源），非独立条目——page_670 真条目
        # 前文无标题不受影响
        if hit is None and FC8F_RX.match(line):
            if not any(
                lines[k].strip().startswith(("#", "**")) for k in range(max(0, i - 6), i)
            ):
                hit = "FC-8f 无加粗双标签"
        # FC-T 表格行：数据表（调整值/修正表、环级怪物表）排除 + 跨行断表
        # 配对去重（1| 英文名首行由 2| 中文闭合行代计）
        if hit == "FC-T 表格行" and (not is_feat_table(lines, i) or is_split_row(lines, i)):
            hit = None
        if hit:
            # 收集行级命中条目名（FC-T 表格行/FC-I 索引行除外：表格条目 +
            # 表格外描述条目是合法双份，其名称不应屏蔽段流引用）。m 仅在
            # CLUSTERS 命中时有效（行级兜底簇命中时 m 为 None，跳过）
            if m and hit not in ("FC-T 表格行", "FC-I 索引/聚合行"):
                tm = TITLE_RX.search(m.group(0))
                if tm:
                    seen.add(tm.group(0))
            counts[hit] += 1
        else:
            # 只记录"像标题"的未命中行（含 ** 或括号 English 或 ##）
            if ("**" in line or "（" in line or line.startswith("#")) and len(line) < 120:
                misses.append((i + 1, line[:90]))
        i += 1
    # 粘连行内标题（标题不在行首，全角双空格后）：行首匹配不到的补充计数
    glue = len(GLUE_RX.findall(text))
    if glue:
        counts["FC-G 粘连行内标题"] += glue
    # FC-2 冠位粘连（单星闭合，与行级簇不重叠）
    crown = len(CROWN_RX.findall(text))
    if crown:
        counts["FC-2 冠位粘连"] += crown
    # FC-8 段流（句号/粗体后粘连标题）：行级簇已计条目名（seen）的段流出现
    # 是正文引用（专长45 任务物品区 7 条、造物专长一览 3 条双计源）→ 按名
    # 去重；跨行英文名（行级含 \n、段流不含）提取不相等 → 不去重（宁漏勿杀）
    stream = 0
    for m2 in STREAM_RX.finditer(text):
        tm = TITLE_RX.search(m2.group(0))
        if tm and tm.group(0) in seen:
            continue
        stream += 1
    if stream:
        counts["FC-8 段流标题"] += stream
    # FC-8b/8c/8d 段流变体（初探探索者型）
    stream_x = len(STREAM_X_RX.findall(text))
    if stream_x:
        counts["FC-8b 段流跨行英文"] += stream_x
    stream_c = len(STREAM_C_RX.findall(text))
    if stream_c:
        counts["FC-8c 段流类型前置"] += stream_c
    # FC-8d 段流双段加粗：简介提及型（护甲大师流派简介 '**铁壁流**** Mobile
    # Bulwark**：该流派…' 型 page_361 6 条，条目本体由行级簇计数）——命中后
    # 同行剩余以冒号开头 → 排除，与 STREAM_E_RX 的简介过滤同判据
    stream_d = 0
    for m in STREAM_D_RX.finditer(text):
        rest = text[m.end():].split("\n", 1)[0]
        if rest.startswith(("：", ":")):
            continue
        stream_d += 1
    if stream_d:
        counts["FC-8d 段流双段加粗"] += stream_d
    # FC-8e 段流英文裸奔（药剂与毒药P&P 型）：句号后'中文名 English'同行/
    # 跨行对。与行级簇零重叠：lookbehind '。' 保证匹配位置非行首（CN 不含
    # 标点，'。'开头行不满足任何行级 ^ 模式）；与其他段流簇互补（STREAM_RX
    # 需括号英文名、STREAM_C 需星号闭合、STREAM_X 需 ** 前缀）。
    # 简介提及型排除：命中后同行剩余以冒号开头（护甲大师手册流派简介
    # '**铁壁流 Mobile Bulwark**：该流派…'型，条目本体由行级簇计数）→ 非条目
    stream_e = 0
    for m in STREAM_E_RX.finditer(text):
        rest = text[m.end():].split("\n", 1)[0]
        if rest.startswith(("：", ":")):
            continue
        stream_e += 1
    if stream_e:
        counts["FC-8e 段流英文裸奔"] += stream_e
    # FC-8h 星包裹英文粘连（魔宠手记FF 型）：行内 **中文名（类型）****English*描述
    # 单星闭合（\*(?!\*)）与 FC-8d 三星闭合（***）不重叠；findall 全文本扫描
    ff = len(FF_RX.findall(text))
    if ff:
        counts["FC-8h 星包裹英文粘连"] += ff
    # FC-8k 段流变体（专长58 型）：章节标题 4 星闭合后同行条目名
    ff8k = len(FF8K_STREAM_RX.findall(text))
    if ff8k:
        counts["FC-8k 星夹括号跨行"] += ff8k
    return counts, misses

def main():
    only = None
    show_miss = "--miss" in sys.argv
    if "--file" in sys.argv:
        only = sys.argv[sys.argv.index("--file") + 1]
    reports = [json.loads(l) for l in open(MERGED, encoding="utf-8") if l.strip()]
    total_c = Counter()
    rows = []
    for r in reports:
        rel = r["file"].removeprefix("pf_rules_md_organized/")
        if only and rel != only:
            continue
        p = os.path.join(SRC_ROOT, rel)
        if not os.path.exists(p):
            continue
        text = open(p, newline="", encoding="utf-8").read()
        counts, misses = match_file(text)
        est = r.get("estimated_count", 0)
        got = sum(counts.values())
        rows.append((rel, est, got, counts, misses, r))
        total_c.update(counts)
    print("===== 簇总计 =====")
    for name, n in total_c.most_common():
        print(f"  {n:6d}  {name}")
    print(f"  合计 {sum(total_c.values())}（estimated_count 总和 {sum(x[1] for x in rows)}）")
    print("\n===== 偏差最大文件 Top25（|命中-est|） =====")
    rows.sort(key=lambda x: -abs(x[2] - x[1]))
    for rel, est, got, counts, misses, r in rows[:25]:
        top = ", ".join(f"{k.split()[0]}:{v}" for k, v in counts.most_common(3))
        print(f"  {rel}: est={est} 命中={got} ({top})")
        if show_miss:
            for ln, t in misses[:8]:
                print(f"      L{ln}: {t!r}")
    if only:
        rel, est, got, counts, misses, r = rows[0]
        print(f"\n{rel}: est={est} 命中={got}")
        for k, v in counts.most_common():
            print(f"  {v:4d}  {k}")
        for ln, t in misses[:30]:
            print(f"  miss L{ln}: {t!r}")

if __name__ == "__main__":
    main()
