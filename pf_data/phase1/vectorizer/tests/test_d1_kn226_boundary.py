"""
test_d1_kn226_boundary.py — D1/KN226 独立复测补充边界测试（QA 补测）

审计 coder 测试（test_feat_book_abbreviation.py / test_rule_monster_source.py）
后补充的边界与缺口测试：

  - 箭头段为空 / 仅空白 → 实际返回空串 abbr（记录当前契约，防静默变化）
  - 箭头段含内嵌空格（'秽邪 勇士'）→ 查表未命中保留原文（中文残留由
    verify_feats.check_book_abbreviation 的 _has_chinese 兜底捕获）
  - CRLF 引用块 → 归一不受行尾影响
  - 有 ASCII 尾部即信任尾部（'武器大师手册WMH'→WMH，不回写规范 WEAPON）——
    锁定「有尾部不动」既有契约
  - config/feat_sources.json 映射表键/值完整性：无重复键、无重复 abbr 撞键、
    key 无 ASCII 尾部（否则查表通道永不命中）
  - 产物级缺口补测（对 output/专长/chunks.jsonl，若存在）：
    book_abbreviation 全 ASCII 总断言（23 值黑名单之外的非 ASCII 值显形）、
    abbr↔(cn,en) 唯一性对账（同 abbr 不得有两个 en 名；THH 失配经 KN229
    修复后转为正式断言）

这些测试全部可在链第 1 步（pytest 阶段）运行：除最后一个产物级测试外
不依赖 pipeline 重生成产物，无 bootstrap 悖论。
"""

import json
import re
from pathlib import Path

import pytest

from vectorizer.processors.feat import (
    _feat_source_from_content,
    _load_abbr_candidates,
    FEAT_SOURCES,
)
from vectorizer.processors.rule import _RULE_SOURCE_OVERRIDES, RULE_SCAN_RELS

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FEAT_CHUNKS = _REPO_ROOT / "output" / "专长" / "chunks.jsonl"

_RE_ASCII = re.compile(r"^[A-Za-z0-9&/]{2,10}$")
_RE_ASCII_TAIL = re.compile(r"[A-Za-z0-9&]+$")


# ============================================================
#  箭头段边界（_feat_source_from_content 黑盒探测契约）
# ============================================================


class TestArrowSegmentBoundary:
    def test_empty_arrow_returns_empty_abbr(self):
        # 空箭头段：正则匹配成功但箭头段为空 → 返回 ('', cn, en)
        # 当前契约如此（产物中无空 abbr，intro/index 不走此通道），锁定防变化
        r = _feat_source_from_content(
            "> 来源：测试书（Test Book），未整理 →  → 专长")
        assert r == ("", "测试书", "Test Book")

    def test_whitespace_arrow_returns_empty_abbr(self):
        r = _feat_source_from_content(
            "> 来源：测试书（Test Book），未整理 →    → 专长")
        assert r is not None and r[0] == ""

    def test_inner_space_misses_table_keeps_raw(self):
        # '秽邪 勇士' ≠ 表 key '秽邪勇士' → 保留原文（含中文），由 verify 兜底捕获
        abbr, cn, en = _feat_source_from_content(
            "> 来源：秽邪勇士（Champions of Corruption），未整理 → 秽邪 勇士 → 专长")
        assert abbr == "秽邪 勇士"
        assert cn == "秽邪勇士" and en == "Champions of Corruption"

    def test_crlf_content_resolves(self):
        r = _feat_source_from_content(
            "> 来源：秽邪勇士（Champions of Corruption），未整理 → 秽邪勇士 → 专长\r\n正文")
        assert r == ("CoC", "秽邪勇士", "Champions of Corruption")

    def test_ascii_tail_trusted_over_canonical(self):
        # 有 ASCII 尾部即信任原文尾部（既有契约：不回写规范缩写）
        abbr, _, _ = _feat_source_from_content(
            "> 来源：武器大师手册（Weapon Master's Handbook），未整理 → 武器大师手册WMH → 专长")
        assert abbr == "WMH"

    def test_no_paren_still_resolves(self):
        # 无（en）括注时 cn/en 取映射表规范值
        r = _feat_source_from_content("> 来源：秽邪勇士，未整理 → 秽邪勇士 → 专长")
        assert r == ("CoC", "秽邪勇士", "Champions of Corruption")


# ============================================================
#  config 映射表完整性（重复键/冲突在 JSON 加载层即吞，需显式断言）
# ============================================================


class TestConfigMappingIntegrity:
    def test_abbr_candidates_no_ascii_tail_key(self):
        # key 含 ASCII 尾部的条目永远不会被通道 1 命中（尾部先被截走）——即死键
        dead = [k for k in _load_abbr_candidates() if _RE_ASCII_TAIL.search(k)]
        assert dead == []

    def test_abbr_candidates_no_duplicate_abbr(self):
        # 两个中文 key 映射到同一缩写 = 潜在撞键（当前应无）
        seen = {}
        for k, e in _load_abbr_candidates().items():
            assert e["abbr"] not in seen, \
                f"abbr {e['abbr']} 双映射: {seen[e['abbr']]!r} vs {k!r}"
            seen[e["abbr"]] = k

    def test_feat_sources_abbr_ascii(self):
        # 通道 2 补充表 abbr 同样须 ASCII（与通道 1 同一 verify 兜底，此处锁定表值）。
        # 只断言 ASCII 不断言长度——'Dragonslayer'（11 字符）为人工核定值，
        # 长度形态不在 D1 归一范围。
        for key, e in FEAT_SOURCES.items():
            assert str(e["abbr"]).isascii(), \
                f"FEAT_SOURCES[{key!r}] abbr 非 ASCII: {e['abbr']!r}"

    def test_rule_overrides_cover_monster_rels(self):
        # KN226：怪物规则全部文件必须命中专属表（防新增文件落入泛化回退）
        monster = [r for r in RULE_SCAN_RELS if r.startswith("规则/怪物规则/")]
        assert len(monster) == 9
        miss = [r for r in monster
                if not any(r.startswith(p) for p in _RULE_SOURCE_OVERRIDES)]
        assert miss == []


# ============================================================
#  产物级总断言（QA 独立补测，不依赖四步链）
# ============================================================


@pytest.mark.skipif(not _FEAT_CHUNKS.exists(), reason="专长产物未生成")
class TestArtifactGlobalAssertions:
    @pytest.fixture(scope="class")
    def chunks(self):
        with open(_FEAT_CHUNKS, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_book_abbreviation_all_ascii(self, chunks):
        # 缺口补测：黑名单 23 值之外的非 ASCII abbr 也必须显形
        # （比 verify 的 _has_chinese 更强：全 ASCII 总断言）
        bad = [(c["chunk_id"], c.get("book_abbreviation"))
               for c in chunks
               if c.get("book_abbreviation")
               and not str(c["book_abbreviation"]).isascii()]
        assert bad == []

    def test_abbr_maps_to_single_en_name(self, chunks):
        by_abbr = {}
        for c in chunks:
            abbr = c.get("book_abbreviation")
            if not abbr or abbr == "?":
                continue
            pair = (c.get("book_name_cn"), c.get("book_name_en"))
            by_abbr.setdefault(abbr, set()).add(pair)
        multi = {a: p for a, p in by_abbr.items() if len(p) > 1}
        assert multi == {}
