"""
test_trait_processor.py — 背景特性 Processor 元数据 TDD 测试

测试目标（对齐 test_feat_processor.py 风格）：
  - _normalize_trait_types() 归一词表 12+1（元数据设计 §四）
  - build_chunk() component_type 三值（trait / trait_intro / trait_flaw）
  - infer_metadata() 输出 7 键 metadata + field_status 三态
  - resolve_source() 专属表冲突覆盖（FoC 错义截断）/ 文件名前缀 / 条目级缩写
  - _trait_file_condition 文件分派正确（63 文件清单）
"""

from pathlib import Path

from vectorizer.processors.trait import (
    TraitProcessor,
    _normalize_trait_types,
    _trait_file_condition,
)


def make_processor():
    """空 provider 链的 TraitProcessor（来源书解析分文件测试覆盖）"""
    from vectorizer.sources.providers import SourceResolver
    return TraitProcessor(source_resolver=SourceResolver([]))


def run_item(item: dict, doc: str = "seed.md") -> dict:
    """infer_metadata 便捷入口（component_type 走 build_chunk 真实路径）"""
    proc = make_processor()
    chunk = proc._build_chunk_template(Path(doc), 0, proc._build_source_context(Path(doc), ""))
    chunk = proc.build_chunk(chunk, item)
    return proc.infer_metadata(chunk, item).metadata


# ============================================================
#  trait_type 归一词表（设计 §四）
# ============================================================


class TestNormalizeTraitTypes:
    """26 值 → 13 值归一"""

    def test_identity_types(self):
        """词表内既有值保持（地区/社会/魔法/典范/坐骑/宇宙/缺陷/装备/派系）"""
        assert _normalize_trait_types(["地区", "社会", "魔法"]) == ["地区", "社会", "魔法"]
        assert _normalize_trait_types(["典范"]) == ["典范"]

    def test_faith_religion_to_belief(self):
        """信仰/宗教/信念 → 信念（裸标签归一）"""
        assert _normalize_trait_types(["信仰"]) == ["信念"]
        assert _normalize_trait_types(["宗教"]) == ["信念"]
        assert _normalize_trait_types(["信念"]) == ["信念"]

    def test_religion_background_to_religion(self):
        """宗教背景 → 宗教（长词优先于裸宗教→信念）"""
        assert _normalize_trait_types(["宗教背景"]) == ["宗教"]

    def test_background_suffixes_stripped(self):
        """战斗背景/地区背景/魔法背景/种族背景 → 去后缀"""
        assert _normalize_trait_types(["战斗背景", "地区背景", "魔法背景", "种族背景"]) == [
            "战斗", "地区", "魔法", "种族",
        ]

    def test_social_alt(self):
        """社交 → 社会"""
        assert _normalize_trait_types(["社交"]) == ["社会"]

    def test_basic_merged_into_type(self):
        """基础（X）并入对应类型（人工门拍板：不保留限定词）"""
        assert _normalize_trait_types(["基础（战斗）"]) == ["战斗"]
        assert _normalize_trait_types(["基础（魔法）"]) == ["魔法"]
        assert _normalize_trait_types(["基础（社会）"]) == ["社会"]

    def test_basic_alt_merged(self):
        """基本（魔法）异体 → 魔法（并入）"""
        assert _normalize_trait_types(["基本（魔法）"]) == ["魔法"]

    def test_combat_paren_suffix_stripped(self):
        """战斗背景（combat）→ 战斗（括号英文残留剥除）"""
        assert _normalize_trait_types(["战斗背景（combat）"]) == ["战斗"]

    def test_unknown_kept(self):
        """未知值保持原样（不臆造不丢弃，审计可登记）"""
        assert _normalize_trait_types(["自定义类型"]) == ["自定义类型"]

    def test_dedup_preserve_order(self):
        """去重保序（formats 层字段+标题括号多通道聚合）"""
        assert _normalize_trait_types(["地区", "地区", "社会"]) == ["地区", "社会"]

    def test_empty_and_none(self):
        assert _normalize_trait_types([]) == []
        assert _normalize_trait_types(["", " "]) == []


# ============================================================
#  build_chunk
# ============================================================


class TestBuildChunk:
    def test_title_text_aliases(self):
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        result = proc.build_chunk(chunk, {"name": "甲胄士", "name_en": "Armor Expert", "text": "正文"})
        assert result.title == "甲胄士"
        assert result.text == "正文"
        assert result.aliases == ["Armor Expert"]

    def test_component_type_trait(self):
        """正文条目（standard）→ trait"""
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        result = proc.build_chunk(chunk, {"name": "甲胄士", "text": "正文"})
        assert result.component_type == "trait"

    def test_component_type_trait_intro(self):
        """intro 标记（章节介绍段）→ trait_intro（检索端降权）"""
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        result = proc.build_chunk(chunk, {"name": "", "format_cluster": "intro", "text": "基本背景被划分为四个子类…"})
        assert result.component_type == "trait_intro"

    def test_component_type_trait_flaw(self):
        """flaw 标记（缺陷条目）→ trait_flaw（PFS 禁用独立体系）"""
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        result = proc.build_chunk(chunk, {"name": "", "flaw": True, "text": "你的交涉检定获得-2罚值"})
        assert result.component_type == "trait_flaw"

    def test_no_name_en(self):
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        result = proc.build_chunk(chunk, {"name": "前奴隶", "text": "正文"})
        assert result.aliases == []

    def test_table_align_spaces_normalized(self):
        """表格行列对齐空格（HTML &nbsp; 产物）→ title/aliases 压缩（专长同款）"""
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        result = proc.build_chunk(chunk, {
            "name": "画眉鸟座", "name_en": "The   Thrush", "text": "正文",
        })
        assert result.title == "画眉鸟座"
        assert result.aliases == ["The Thrush"]


# ============================================================
#  infer_metadata + field_status
# ============================================================


class TestInferMetadata:
    """7 键 metadata + field_status 三态"""

    def test_full_entry(self):
        md = run_item({
            "name": "甲胄士", "name_en": "Armor Expert",
            "trait_type": ["战斗"], "requirement": "角色等级1",
            "source": "APG", "deity": "", "pfs_eligible": True, "flaw": False,
            "format_cluster": "standard", "text": "正文",
        })
        assert set(md) == {
            "trait_type", "requirement", "source", "deity",
            "pfs_eligible", "flaw", "format_cluster", "field_status",
        }
        assert md["trait_type"] == ["战斗"]
        assert md["requirement"] == "角色等级1"
        assert md["source"] == "APG"
        assert md["pfs_eligible"] is True
        fs = md["field_status"]
        assert fs["trait_type"] == "parsed"
        assert fs["requirement"] == "parsed"
        assert fs["source"] == "parsed"
        assert fs["pfs_eligible"] == "parsed"
        assert fs["format_cluster"] == "parsed"

    def test_isg_flow_entry_deity_parsed(self):
        """ISG 流式条目：无字段行 trait_type 空（missing 不臆造）+ deity parsed"""
        md = run_item({
            "name": "亲近元素", "name_en": "Affinity for the Elements",
            "trait_type": [], "deity": "任何一位元素领主",
            "format_cluster": "B3_flow_bare", "text": "正文",
        })
        fs = md["field_status"]
        assert fs["trait_type"] == "missing"
        assert fs["deity"] == "parsed"

    def test_deity_not_applicable_non_religious(self):
        """非宗教主题条目：deity not_applicable（设计 §3.3）"""
        md = run_item({
            "name": "移情外交家", "trait_type": ["地区"], "format_cluster": "standard", "text": "正文",
        })
        assert md["field_status"]["deity"] == "not_applicable"

    def test_deity_missing_religious(self):
        """宗教主题条目（信念/宗教）缺 deity → missing（应可解析）"""
        md = run_item({
            "name": "A", "trait_type": ["信念"], "format_cluster": "standard", "text": "正文",
        })
        assert md["field_status"]["deity"] == "missing"

    def test_intro_field_family_not_applicable(self):
        """trait_intro：trait_type/requirement 恒 not_applicable（无字段行）"""
        md = run_item({"name": "", "format_cluster": "intro", "text": "基本背景被划分为四个子类…"})
        fs = md["field_status"]
        assert fs["trait_type"] == "not_applicable"
        assert fs["requirement"] == "not_applicable"
        assert fs["deity"] == "not_applicable"

    def test_flaw_entry(self):
        """trait_flaw：flaw parsed，deity not_applicable"""
        md = run_item({"name": "", "flaw": True, "format_cluster": "C_flaw", "text": "你的交涉检定获得-2罚值"})
        fs = md["field_status"]
        assert fs["flaw"] == "parsed"
        assert fs["deity"] == "not_applicable"

    def test_pfs_false_missing(self):
        """pfs_eligible False → missing（专长同款）"""
        md = run_item({"name": "A", "format_cluster": "standard", "text": "正文"})
        assert md["field_status"]["pfs_eligible"] == "missing"

    def test_page158_pfs_disabled_parsed(self):
        """R4 页面级 PFS 禁用：page_158 头部 `【PFS】PFS中不可使用缺陷系统。`
        声明整页缺陷系统 PFS 禁用 → pfs_eligible False 为显式值（parsed），
        非缺失——trait_type R2 页面级默认方案同构（2026-08-06 任务 4）"""
        md = run_item(
            {"name": "忧虑", "format_cluster": "C_flaw", "text": "正文", "flaw": True},
            doc="page_158.md",
        )
        assert md["pfs_eligible"] is False
        assert md["field_status"]["pfs_eligible"] == "parsed"

    def test_other_page_pfs_missing_unchanged(self):
        """非 page_158 条目（含 trait_flaw）pfs_eligible False → missing 不变"""
        md = run_item(
            {"name": "A", "format_cluster": "C_flaw", "text": "正文", "flaw": True},
            doc="page_150.md",
        )
        assert md["field_status"]["pfs_eligible"] == "missing"

    def test_page158_intro_pfs_parsed(self):
        """page_158 intro 同样受页面级声明约束（缺陷系统整体 PFS 禁用）"""
        md = run_item({"name": "", "format_cluster": "intro", "text": "缺陷是反向的背景特性…"}, doc="page_158.md")
        assert md["field_status"]["pfs_eligible"] == "parsed"

    def test_flaw_false_missing(self):
        md = run_item({"name": "A", "format_cluster": "standard", "text": "正文"})
        assert md["field_status"]["flaw"] == "missing"

    def test_source_from_item(self):
        md = run_item({"name": "A", "source": "Cheliax, Empire of Devils pg. 17", "format_cluster": "standard", "text": "正文"})
        assert md["source"] == "Cheliax, Empire of Devils pg. 17"
        assert md["field_status"]["source"] == "parsed"

    def test_idempotent(self):
        proc = make_processor()
        chunk = proc._build_chunk_template(Path("seed.md"), 0, proc._build_source_context(Path("seed.md"), ""))
        item = {"name": "甲胄士", "trait_type": ["战斗"], "format_cluster": "standard", "text": "正文"}
        chunk = proc.build_chunk(chunk, item)
        proc.infer_metadata(chunk, item)
        first = dict(chunk.metadata)
        proc.infer_metadata(chunk, item)
        assert chunk.metadata == first


# ============================================================
#  resolve_source
# ============================================================


class TestResolveSource:
    """来源书解析：专属表冲突覆盖 / 文件名前缀 / 条目级缩写兜底"""

    @staticmethod
    def _resolve(processor, file_path: Path, content: str, item: dict = None):
        proc = processor
        ctx = proc._build_source_context(file_path, content)
        chunk = proc._build_chunk_template(file_path, 0, ctx)
        return proc.resolve_source(chunk, ctx, item or {})

    def test_file_prefix_hit(self):
        """文件名中文前缀命中专属表（ASoL 不在共享表）→ 75 档"""
        proc = make_processor()
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/背景特性/安多安ASoL_背景特性.md"),
            "# 安多安 背景特性\n",
        )
        assert chunk.book_abbreviation == "ASoL"
        assert chunk.book_name_cn == "安多安，自由之魂"
        assert chunk.book_name_en == "Andoran, Spirit of Liberty"
        assert chunk.source_confidence == 75

    def test_race_background_file(self):
        """种族背景特性后缀文件（格拉里昂系列中文名）"""
        proc = make_processor()
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/背景特性/格拉里昂的人类_种族背景特性.md"),
            "# 格拉里昂的人类 背景特性\n",
        )
        assert chunk.book_abbreviation == "格拉里昂的人类"

    def test_foC_conflict_overridden(self):
        """FoC 共享表错义截断：provider 链给「信仰之书：探索者」，专属表权威
        「堕落信念 Champions of Corruption」→ 覆盖（全 provider 链）"""
        from vectorizer.sources.providers import ALL_PROVIDERS, SourceResolver
        proc = TraitProcessor(source_resolver=SourceResolver(ALL_PROVIDERS))
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/背景特性/堕落信念FoC_背景特性.md"),
            "# 堕落信念 背景特性\n",
        )
        assert chunk.book_abbreviation == "FoC"
        assert chunk.book_name_cn == "堕落信念"
        assert chunk.book_name_en == "Champions of Corruption"

    def test_isg_shared_chain_kept(self):
        """ISG 共享表与专属表一致 → 保持 provider 链结果（不重复覆盖）"""
        from vectorizer.sources.providers import ALL_PROVIDERS, SourceResolver
        proc = TraitProcessor(source_resolver=SourceResolver(ALL_PROVIDERS))
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/背景特性/内海诸神ISG_背景特性.md"),
            "# 内海诸神 背景特性\n",
        )
        assert chunk.book_abbreviation == "ISG"
        assert chunk.book_name_cn == "内海诸神"
        assert chunk.book_name_en == "Inner Sea Gods"

    def test_item_source_abbr_fallback(self):
        """基础页【书缩写】条目：item.source=APG → 进阶玩家指南（60 档）"""
        proc = make_processor()
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/背景特性/page_150.md"),
            "# page_150\n",
            {"source": "APG"},
        )
        assert chunk.book_abbreviation == "APG"
        assert chunk.book_name_cn == "进阶玩家指南"
        assert chunk.source_confidence == 60

    def test_item_source_english_title_ignored(self):
        """条目 source 为英文书名（非纯缩写）→ 不查表（保持 '?'，后处理可补）"""
        proc = make_processor()
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/背景特性/切利亚斯EOD_背景特性.md"),
            "# 切利亚斯 背景特性\n",
            {"source": "Cheliax, Empire of Devils pg. 17"},
        )
        # 文件名前缀 EOD 专属表先命中（75 档），英文书名通道不生效
        assert chunk.book_abbreviation == "EOD"
        assert chunk.book_name_cn == "切利亚斯，魔鬼帝国"

    def test_unknown_stays_unknown(self):
        """无任何线索 → 保持 '?'（不编造来源）"""
        proc = make_processor()
        chunk = self._resolve(
            proc,
            Path("pf_rules_md_organized/背景特性/未知书X_背景特性.md"),
            "# 未知 背景特性\n",
        )
        assert chunk.book_abbreviation == "?"


class TestTraitFileCondition:
    """输入范围：condition = 格式簇分配表 rel 查表（63 文件）"""

    def test_positive_isg(self):
        assert _trait_file_condition(Path("pf_rules_md_organized/背景特性/内海诸神ISG_背景特性.md")) is True

    def test_positive_page(self):
        assert _trait_file_condition(Path("pf_rules_md_organized/背景特性/page_150.md")) is True

    def test_negative_feat_dir(self):
        """专长目录（清单外）→ 不产"""
        assert _trait_file_condition(Path("pf_rules_md_organized/专长/page_311.md")) is False

    def test_negative_race_dir(self):
        """种族目录（清单外）→ 不产"""
        assert _trait_file_condition(Path("pf_rules_md_organized/种族/核心种族/矮人/矮人.md")) is False

    def test_negative_outside_list(self):
        """背景特性目录内但不在清单（不存在文件）→ 不产"""
        assert _trait_file_condition(Path("pf_rules_md_organized/背景特性/page_999.md")) is False

    def test_negative_fake_path(self):
        assert _trait_file_condition(Path("/x/Traits.md")) is False


# ============================================================
#  R2 页面级默认 + R3 HH 段排除（方案 2026-08-06）
# ============================================================


class TestR2PageDefault:
    """R2 页面级默认填充（_PAGE_TYPE_DEFAULT）+ R3 HH 段排除

    优先级（方案定稿）：解析值 > marker 标记值 > R2 页面默认 > missing。
    intro 豁免不变（not_applicable 优先于默认填）。
    """

    @staticmethod
    def _run(doc: str, item: dict) -> dict:
        proc = make_processor()
        p = Path(f"{doc}.md")
        chunk = proc._build_chunk_template(p, 0, proc._build_source_context(p, ""))
        chunk = proc.build_chunk(chunk, item)
        return proc.infer_metadata(chunk, item).metadata

    def test_page158_default_flaw(self):
        """page_158 缺陷页无类型条目 → 默认「缺陷」"""
        md = self._run("page_158", {"name": "A", "format_cluster": "C_flaw", "text": "正文"})
        assert md["trait_type"] == ["缺陷"]

    def test_page1579_default_equipment(self):
        """page_1579 装备页无类型条目 → 默认「装备」"""
        md = self._run("page_1579", {"name": "A", "format_cluster": "standard", "text": "正文"})
        assert md["trait_type"] == ["装备"]

    def test_cosmic17_original_default_cosmic(self):
        """背景特性17 原内容段（无 _hh_section）→ 默认「宇宙」"""
        md = self._run("背景特性17", {"name": "A", "format_cluster": "D_exalted_mount_cosmic", "text": "正文"})
        assert md["trait_type"] == ["宇宙"]

    def test_cosmic17_hh_no_marker_kept_empty(self):
        """背景特性17 HH 段无标记条目（_hh_section）→ 跳过 R2 维持空"""
        md = self._run("背景特性17", {"name": "A", "_hh_section": True, "format_cluster": "standard", "text": "正文"})
        assert md["trait_type"] == []

    def test_cosmic17_hh_marker_wins(self):
        """背景特性17 HH 段标记条目 → marker 兜底优先（信念背景 → 信念）"""
        md = self._run("背景特性17", {"name": "A", "_hh_section": True, "_trait_type_from_marker": "信念背景", "format_cluster": "standard", "text": "正文"})
        assert md["trait_type"] == ["信念"]

    def test_mount_default(self):
        """坐骑背景页无类型条目（动物坐骑）→ 默认「坐骑」"""
        md = self._run("坐骑背景", {"name": "动物坐骑", "format_cluster": "standard", "text": "正文"})
        assert md["trait_type"] == ["坐骑"]

    def test_intro_exempt(self):
        """trait_intro 豁免：page_158 介绍段 → 维持空（not_applicable 优先于默认）"""
        md = self._run("page_158", {"name": "", "format_cluster": "intro", "text": "缺陷是反向的背景特性…"})
        assert md["trait_type"] == []
        assert md["field_status"]["trait_type"] == "not_applicable"

    def test_non_default_doc_kept_empty(self):
        """非默认 doc（扩展书 ISG）无类型 → 维持空（不臆造）"""
        md = self._run("内海诸神ISG_背景特性", {"name": "A", "format_cluster": "B3_flow_bare", "text": "正文"})
        assert md["trait_type"] == []

    def test_parsed_value_wins(self):
        """已有解析值优先：page_158 带类型字段条目 → 保持解析值不被默认覆盖"""
        md = self._run("page_158", {"name": "A", "trait_type": ["战斗"], "format_cluster": "standard", "text": "正文"})
        assert md["trait_type"] == ["战斗"]

    def test_marker_fallback_unchanged(self):
        """marker 兜底（既有机制）不因 R2 表受影响：TEoG 条目 marker → 地区"""
        md = self._run("塔尔多TEoG_背景特性", {"name": "骑士精神", "_trait_type_from_marker": "地区背景", "format_cluster": "standard", "text": "正文"})
        assert md["trait_type"] == ["地区"]
