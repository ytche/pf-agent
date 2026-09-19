"""
test_rule_monster_source.py — KN226 规则「怪物规则」章节 book 失真修复测试

覆盖（D1 批次 KN226，方案验收标准）：
  - 专属表不再有「规则/怪物规则/」泛化键（TOC 章节名当书名的根因）
  - 9 个怪物规则文件逐文件归属断言（B1/CRB/MC/? 勘察定性值）
  - 全 286 扫描清单专属表完备性自证不破（加载期本已保证，显式断言）
  - 产物级断言（book「怪物」0 残留）在 verify 阶段覆盖：
    verify_rule.check_kn226（四步链第 3 步，pipeline 之后执行）。此处不留
    产物级 pytest——链第 1 步（pytest）先于第 2 步（pipeline 重生成），
    产物级断言放 pytest 会对旧产物永远失败（bootstrap 悖论）。
"""

import re
from vectorizer.processors.rule import (
    _RULE_SOURCE_OVERRIDES,
    _resolve_rule_source,
    RULE_SCAN_RELS,
)

# KN226 逐文件勘察定性（2026-09-18，依据登记 KN226 条目）：
# page_299 编注「本页面包括怪物图鉴的所有动物伙伴」→ B1；
# page_300 生物类型与怪物亚种 / page_302 通用怪物规则 / page_1125 怪物进化
#   / page_1224 怪物体型修正 → Bestiary 系内容 → B1；
# page_301 魔宠和模板约 90% 魔宠基本规则（CRB 奥术联结）→ CRB；
# page_400 召唤怪物/自然盟友速查 → CRB 召唤法术列表；
# page_863 怪物志-魔改怪物（职业简单模板）→ MC 怪物志（本表首登记）；
# page_1018 扮演怪物：ARG 出版前论坛先行译文，无单行本出处 → '?'。
EXPECTED = {
    "规则/怪物规则/page_299.md": ("B1", "怪物图鉴", "Bestiary 1"),
    "规则/怪物规则/page_300.md": ("B1", "怪物图鉴", "Bestiary 1"),
    "规则/怪物规则/page_301.md": ("CRB", "核心规则书", "Core Rulebook"),
    "规则/怪物规则/page_302.md": ("B1", "怪物图鉴", "Bestiary 1"),
    "规则/怪物规则/page_400.md": ("CRB", "核心规则书", "Core Rulebook"),
    "规则/怪物规则/page_863.md": ("MC", "怪物志", "Monster Codex"),
    "规则/怪物规则/page_1018.md": ("?", "未知", "Unknown"),
    "规则/怪物规则/page_1125.md": ("B1", "怪物图鉴", "Bestiary 1"),
    "规则/怪物规则/page_1224.md": ("B1", "怪物图鉴", "Bestiary 1"),
}


class TestMonsterSourceOverrides:
    def test_no_generic_monster_key(self):
        # KN226 根因：泛化键把 TOC 章节名「怪物」当书名
        assert "规则/怪物规则/" not in _RULE_SOURCE_OVERRIDES

    def test_each_file_resolves(self):
        for rel, expected in EXPECTED.items():
            assert rel in RULE_SCAN_RELS, f"{rel} 不在 286 扫描清单"
            assert _resolve_rule_source(rel) == expected, rel

    def test_scan_rels_completeness(self):
        # 加载期自证的显式版：286 文件全部可短路命中（漏表即来源失实）
        miss = [rel for rel in RULE_SCAN_RELS if _resolve_rule_source(rel) is None]
        assert miss == []

    def test_no_chinese_book_in_overrides(self):
        for prefix, (abbr, cn, en) in _RULE_SOURCE_OVERRIDES.items():
            assert not re.search(r"[一-鿿]", abbr), f"{prefix} abbr 为中文: {abbr!r}"
