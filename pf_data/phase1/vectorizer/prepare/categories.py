"""categories.py — Prepare 审计类目语义表注册（v2.2 决策 G）

骨架通用（census/firstlast/phantom/scan 类目无关），类目专属语义（STOP 词表、
机检配置）在此注册；新类目继承注册即复用整套闸口，禁止在脚本里硬编码类目词。

注册项语义：
  stop_cjk / stop_en —— phantom 取证时排除的非专有名的常见词（标题噪声/格式词）
  scan —— vectorizer.prepare.scan 五合一机检配置：
    source_dir  源数据目录（相对 phase1）
    collect     manifest（17 批清单+extra_files，专长）| glob（目录递归，默认）
    exclude_dirs glob 策略排除的子目录（如种族构建）
    field_labels 字段标签统计（**标签** 行内命中）
    official_tags 〔〕类型标记官方清单（无标记体系则为空表）
    baseline    基线表解析：file + mode（feat_table | race_overview）
"""
from typing import Dict

CATEGORIES: Dict[str, dict] = {
    "feat": {
        "stop_cjk": {
            "战斗", "团队", "专长", "战斗专长", "团队专长", "超魔", "先决条件", "好处",
            "描述", "出自", "特殊情况", "正常", "效果", "勇毅", "演武", "流派", "诅咒",
            "故事", "跨行续", "表格", "顶部索引列表",
        },
        "stop_en": {
            "Combat", "Teamwork", "Feat", "Feats", "Style", "Metamagic",
            "PFS", "PFS不可", "the", "of",
        },
        "scan": {
            "source_dir": "pf_rules_md_organized/专长",
            "collect": "manifest",
            "manifest": "vectorizer/exploration/专长/prepare_batches.json",
            "extra_files": ["pf_rules_md_organized/专长/page_202.md"],
            "field_labels": ["先决条件", "专长效果", "通常状况", "特殊", "注意"],
            "official_tags": ["战斗", "重击", "勇毅", "造物", "演武", "超魔", "派头", "流派", "故事", "团队"],
            "baseline": {"file": "pf_rules_md_organized/专长/page_202.md", "mode": "feat_table"},
        },
        "verify_prepare": {
            "title": "专长",
            "doc_roles": ["overview", "index_table", "aggregation", "detail", "mixed"],
            "trap_kinds": ["断行英文名", "链接陷阱", "表格双语分行", "译者行", "PFS图标",
                           "重复条目", "非条目表格", "无标题正文"],
            "required_keys": ["file", "batch", "size_kb", "doc_role", "title_forms",
                              "field_layout", "field_labels_seen", "feat_type_tags",
                              "estimated_count", "count_basis", "first_entry",
                              "last_entry", "traps", "dedup_note",
                              "format_cluster_hint", "notes"],
        },
    },
    "race": {
        "stop_cjk": {
            "种族", "特性", "替换", "出自", "属性", "调整", "体型", "速度", "感官",
            "语言", "名称", "社会", "体貌", "描述", "阵营", "宗教", "冒险者",
            "天赋", "职业", "奖励", "边栏", "开篇", "新规则", "变体", "概述",
            "生物", "类型", "表格", "矮人", "精灵", "人类", "侏儒", "半精灵",
            "半兽人", "半身人",
        },
        "stop_en": {
            "Race", "Races", "Racial", "Trait", "Traits", "Alternate", "Overview",
            "Size", "Speed", "Senses", "Language", "Type", "the", "of",
        },
        "scan": {
            "source_dir": "pf_rules_md_organized/种族",
            "collect": "glob",
            "exclude_dirs": ["种族构建"],
            "field_labels": ["体貌描述", "社会", "阵营与宗教", "冒险者", "属性调整",
                             "体型", "速度", "感官", "语言", "种族特性", "天赋职业奖励"],
            "official_tags": [],
            "baseline": {"file": "pf_rules_md_organized/种族/page_10.md", "mode": "race_overview"},
        },
        "verify_prepare": {
            "title": "种族",
            # 种族格式簇：完整条目（full）/替换特性汇总（alt_traits）/
            # 内联替换特性段落（alt_inline）/怪物玩法扩展（monster_play）/
            # 概述/职业变体/边栏/混合
            "doc_roles": ["race_full", "race_alt_traits", "race_alt_inline",
                          "monster_play", "overview", "class_bonus", "sidebar",
                          "mixed"],
            # 陷阱词表与专长同源（CHM 转换残留同型），「其他：」前缀可扩展
            "trap_kinds": ["断行英文名", "链接陷阱", "表格双语分行", "译者行", "PFS图标",
                           "重复条目", "非条目表格", "无标题正文"],
            "required_keys": ["file", "batch", "size_kb", "doc_role", "title_forms",
                              "field_layout", "field_labels_seen", "feat_type_tags",
                              "estimated_count", "count_basis", "first_entry",
                              "last_entry", "traps", "dedup_note",
                              "format_cluster_hint", "notes"],
        },
    },
    "skill": {
        "stop_cjk": {
            "技能", "检定", "DC", "任务", "速查", "动作", "重试", "特殊", "正常",
            "描述", "表格", "顶部索引列表", "检定结果", "对抗", "加值", "减值",
            "属性", "修正", "正文", "来源", "翻译", "校对", "制表",
        },
        "stop_en": {
            "Skill", "Skills", "Check", "DC", "the", "of", "PFS", "PFS不可",
        },
        "scan": {
            # 技能类目是跨 L1 页面集合：CRB 技能子树 + Unchained 技能与选项 +
            # 根目录孤儿页/散件 + 异能/科技/FAQ 页，全部文件显式入 manifest
            "source_dir": "pf_rules_md_organized/技能",
            "collect": "manifest",
            "manifest": "vectorizer/exploration/skill/prepare_batches.json",
            "field_labels": ["检定", "动作", "重试", "特殊"],
            # 技能无〔〕类型标记体系（【速查】块是引用标记非类型），留空
            "official_tags": [],
            # 无权威汇总表（page_162 技能详述章首非列表表；26 技能权威清单
            # 以 CHM 目录为准，见 技能模块语义切分计划.md 附录 A），暂不配置，
            # 召回基线以 CHM 目录 26 技能 + UI 8 + 巨人猎手 4 枚举
        },
        "verify_prepare": {
            "title": "技能",
            # 技能勘探角色：CRB 技能正文页（detail）/ UI 散文补充页
            # （ui_supplement）/ 巨人猎手条目页（giant_options）/ Unchained 书内
            # 规则页（unchained_rule）/ 其他书变体规则页（variant_rule：
            # 河域子民/异能/科技/FAQ）/ 导言页（overview）/ 索引汇总页
            # （index_table）/ 混合（mixed）
            "doc_roles": ["detail", "ui_supplement", "giant_options",
                          "unchained_rule", "variant_rule", "overview",
                          "index_table", "mixed"],
            # 陷阱词表与专长同源 + 技能专属两坑：DC 表跨行（`| 治疗中毒 |\n| 毒素豁免DC |`
            # 空行断裂）、速查块行内断行（【速查】**出血 (Bleed)**: \n换行继续）
            "trap_kinds": ["断行英文名", "链接陷阱", "表格双语分行", "译者行", "PFS图标",
                           "重复条目", "非条目表格", "无标题正文", "DC表跨行",
                           "速查块断行"],
            "required_keys": ["file", "batch", "size_kb", "doc_role", "title_forms",
                              "field_layout", "field_labels_seen", "feat_type_tags",
                              "estimated_count", "count_basis", "first_entry",
                              "last_entry", "traps", "dedup_note",
                              "format_cluster_hint", "notes"],
        },
    },
    "equipment": {
        "stop_cjk": {
            "装备", "物品", "武器", "防具", "护甲", "盾牌", "奇物", "戒指", "权杖",
            "法杖", "药水", "卷轴", "魔杖", "炼金", "毒药", "神器", "价格", "重量",
            "位置", "灵光", "灵氲", "施法者等级", "来源", "出处", "制造要求",
            "制造成本", "描述", "正文", "表格", "顶部索引列表", "译者", "翻译",
            "校对", "制表",
        },
        "stop_en": {
            "Item", "Items", "Equipment", "Weapon", "Armor", "Wondrous",
            "Ring", "Rod", "Staff", "Potion", "Scroll", "Wand", "Alchemical",
            "Poison", "Artifact", "Price", "Weight", "Slot", "Aura", "CL",
            "the", "of", "PFS", "PFS不可",
        },
        "scan": {
            # 装备类目 = 装备_魔法物品/ 全量（295）+ 根级内容页 2（page_234/635），
            # 跨根级需 manifest 显式清单；P3 散件批次已取消（M1.3 修正：根级
            # 装备候选全为副本，无独立增量）
            "source_dir": "pf_rules_md_organized/装备_魔法物品",
            "collect": "manifest",
            "manifest": "vectorizer/exploration/equipment/prepare_batches.json",
            "field_labels": ["位置", "价格", "重量", "灵光", "灵氲", "施法者等级",
                             "制造要求", "制造成本"],
            # 装备无〔〕类型标记体系（物品形态靠字段行/章节归类），留空
            "official_tags": [],
            # 无权威汇总表（C 形态 CHM 大页即权威枚举），召回基线以
            # CHM 装备子树 L3~L5 条目名 + 各书聚合清单一对一定
        },
        "verify_prepare": {
            "title": "装备",
            # 装备格式簇：书聚合直入（aggregation）/ CHM 大页切块
            # （chm_page）/ 价格表·索引（index_table）/ 导言（overview）/ 混合
            "doc_roles": ["aggregation", "chm_page", "index_table",
                          "overview", "mixed"],
            # 陷阱词表与专长同源 + 装备专属 15 坑（M1c 勘探 2026-08-08 扩充）：
            # 价格表跨行（`| 精金 |\n| 500gp |` 空行断裂）、星壳字段行
            # （`**位置：**颈部 **施法者等级：**1` 单行内联）、表格 `\r` 残迹
            # （KN159 管道残迹，价格表高危）；B 形态书聚合坑：单行条目字段粘连
            # （`价格 16000GPCL 10 重量 –灵光` 无分隔连排）、行内粘连（多条目
            # 连成一行 `**侍者FOOTMAN**价格 5 sp…**雇员HIRELING**…`）、HTML 残留
            # （`[/color]`/`[/size]` 转换残渣）、图片链接（`![[图片]](https://…)`
            # 论坛搬运）、独立价格行（`**强酸(Acid) **10G 1磅**` 价格与标题同行）、
            # 制造需求字段跨行（`**制造需求** \n27000gp…`）、来源块位置异常
            # （`> 来源：` 不在头部）、多来源聚合混排（一文件多书条目混排）、
            # 形态混排（同页删除线壳/裸标题并存）、迷你条目（HA 子条目：
            # 加粗标题+来源块+单段）；KN160 星壳家族：星壳残迹（标题星壳半残
            # `偷书贼之包**（Book Thief's Kit）` 或开不闭）、尾随星壳
            # （`**蟾蜍（Toad）******` 尾部多星）
            "trap_kinds": ["断行英文名", "链接陷阱", "表格双语分行", "译者行", "PFS图标",
                           "重复条目", "非条目表格", "无标题正文", "价格表跨行",
                           "星壳字段行", "表格CR残迹", "单行条目字段粘连", "行内粘连",
                           "星壳残迹", "尾随星壳", "HTML残留", "图片链接", "独立价格行",
                           "制造需求字段跨行", "来源块位置异常", "多来源聚合混排",
                           "形态混排", "迷你条目"],
            "required_keys": ["file", "batch", "size_kb", "doc_role", "title_forms",
                              "field_layout", "field_labels_seen", "feat_type_tags",
                              "estimated_count", "count_basis", "first_entry",
                              "last_entry", "traps", "dedup_note",
                              "format_cluster_hint", "notes"],
        },
    },
    "trait": {
        "stop_cjk": {
            "战斗", "信念", "魔法", "社会", "派系", "种族", "地区", "宗教", "装备",
            "宇宙", "典范", "坐骑", "缺陷", "背景", "特性", "出自", "类型", "需求",
            "描述", "正文", "正常", "特殊", "表格", "优点", "缺点", "来源", "顶部索引列表",
        },
        "stop_en": {
            "Traits", "Trait", "Combat", "Faith", "Magic", "Social", "Faction",
            "Race", "Racial", "Regional", "Religion", "Equipment", "Cosmic",
            "Exalted", "Mount", "Flaw", "the", "of", "PFS", "PFS不可",
        },
        "scan": {
            # 63 文件全平铺无子目录（2026-08-05 摸底实测），glob 直接覆盖
            "source_dir": "pf_rules_md_organized/背景特性",
            "collect": "glob",
            "field_labels": ["类型", "需求"],
            # 形态 A 用【书缩写】标记来源、形态 B 用「**类型**：」字段行——
            # 均非〔〕类型标记体系，official_tags 留空待勘探定性
            "official_tags": [],
            # 无权威汇总表（page_150~158 基础页为星壳流式枚举页，
            # 与专长 page_202 表格形态不同），machine_scan 标题候选即枚举权威
            # "baseline": {...} 暂不配置，人工门决策
        },
        "verify_prepare": {
            "title": "背景特性",
            # 背景特性格式簇：基础页星壳流式（basic_page）/来源书 H2
            # （source_book）/缺陷页（flaw）/典范·坐骑·宇宙（exalted_mount_cosmic）/
            # 混合
            "doc_roles": ["basic_page", "source_book", "flaw",
                          "exalted_mount_cosmic", "mixed"],
            # 陷阱词表与专长同源 + 背景特性专属两坑：出自行页码跨行
            # （`pg. \n18`）、删除线壳标题（`**~~缺陷~~**`）
            "trap_kinds": ["断行英文名", "链接陷阱", "表格双语分行", "译者行", "PFS图标",
                           "重复条目", "非条目表格", "无标题正文", "出自行跨行",
                           "删除线壳"],
            "required_keys": ["file", "batch", "size_kb", "doc_role", "title_forms",
                              "field_layout", "field_labels_seen", "feat_type_tags",
                              "estimated_count", "count_basis", "first_entry",
                              "last_entry", "traps", "dedup_note",
                              "format_cluster_hint", "notes"],
        },
    },
    "rule": {
        "stop_cjk": {
            "规则", "表格", "正文", "顶部索引列表", "译者", "翻译", "校对", "制表",
            "来源", "出处", "描述", "先决条件", "效果", "正常", "特殊", "概述",
            "导言", "边栏", "前言", "索引", "目录", "编注", "译注", "列表", "内容",
            "附录", "参考", "速查", "须知", "检定", "DC", "豁免", "加值", "减值",
            "动作", "类型", "需求", "价格", "重量", "灵光", "灵氲", "施法者等级",
            "等级", "类别", "分类", "数据", "摘要", "章节",
        },
        "stop_en": {
            "Rule", "Rules", "Table", "Tables", "the", "of", "PFS", "PFS不可",
            "Overview", "Introduction", "Index", "Contents", "Chapter", "Section",
            "CR", "DC",
        },
        "scan": {
            # 规则模块 = 4 个跨形态 L1 统一（核心规则 CRB/规则/重训/常用速查）：
            # 3 子目录全量 + 根级 7 唯一副本，跨目录集合 manifest 显式列出；
            # manifest files 相对 phase1（含 pf_rules_md_organized/ 前缀）
            "source_dir": "pf_rules_md_organized/规则",
            "collect": "manifest",
            "manifest": "vectorizer/exploration/rule/prepare_batches.json",
            "field_labels": ["来源", "CR", "豁免", "先决条件", "描述", "类型", "效果",
                             "需求", "速度", "感官", "语言", "价格", "重量"],
            # 规则模块无〔〕类型标记体系（章节型形态，无类型括号），留空
            "official_tags": [],
            # 无权威汇总表：召回权威 = CHM TOC 章节枚举 + 条目级标题计数
            # （作祟汇总/神恩聚合页以 BOTD-source 注释计数为权威）
        },
        "verify_prepare": {
            "title": "规则",
            # 章节型规则文本格式簇：书规则章节正文页（rule_chapter）/
            # 规则散件条目页（rule_detail）/ 超大型聚合页（aggregation）/
            # 导言页（overview）/ 表格索引页（index_table）/ BBS 翻译帖形态
            # （bbs_page）/ 混合（mixed）
            "doc_roles": ["rule_chapter", "rule_detail", "aggregation", "overview",
                          "index_table", "bbs_page", "mixed"],
            # 陷阱词表 = 勘探自由文本家族归一化全集（2026-08-09 转换脚本适配
            # verify 契约）；「其他：」前缀承接长尾自由文本
            "trap_kinds": ["断行英文名", "表格CR残迹", "星壳残迹", "译者行", "译注行",
                           "译者吐槽", "链接陷阱", "无标题正文", "行内加粗", "字段行",
                           "重复条目", "表格", "图片链接", "伪表格", "HTML残留",
                           "跨行标题", "悬挂列表符", "速查行", "空文件", "引用边栏",
                           "BBS头行", "无显著陷阱", "跨文件重复", "来源书混合",
                           "标题形态不统一", "超长行", "纯英文段落", "删除线壳",
                           "出自行跨行", "标题内容错位"],
            # required_keys 与词条型模块不同：章节型形态无 field_layout /
            # field_labels_seen / feat_type_tags（那是词条字段体系）
            "required_keys": ["file", "batch", "size_kb", "doc_role", "title_forms",
                              "estimated_count", "count_basis", "first_entry",
                              "last_entry", "traps", "dedup_note",
                              "format_cluster_hint", "notes"],
        },
    },
}


def get(category: str) -> dict:
    """取类目语义表；未知类目返回空表（不含停用词，全量取证）"""
    return CATEGORIES.get(category, {"stop_cjk": set(), "stop_en": set()})


def names() -> list:
    return sorted(CATEGORIES)
