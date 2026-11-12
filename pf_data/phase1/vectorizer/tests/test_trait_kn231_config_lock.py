# -*- coding: utf-8 -*-
"""KN231 回归锁：trait_sources.json 存量中文 abbr 归一 + AA 撞键消歧配置锁定。

锁定对象（2026-09-21 处置，登记 pf_data/phase1/docs/已知问题记录.md KN231 节）：
- 7 本书中文 abbr → ASCII（每本书全部别名 key 的 abbr 必须一致）；
- 秘术选集（Arcane Anthology）AA → ArAn（4 个别名 key 同步）；
- 别名 key "Quests and Campaigns" 的 en 拼写统一为 "Quests & Campaigns"；
- trait 全表 abbr 不得含中文（KN231 口径）；
- 新缩写集不得与 feat_sources.json 全表撞键，不得复用 KN230 脏值；
- 均衡信念 en 订正（2026-09-21 用户单独审批）：Champions of Balance → Faiths of Balance，
  该书全部别名 key 的 en 一致为 Faiths of Balance；
"""
import json
import re
from pathlib import Path

import pytest

_PHASE1 = Path(__file__).resolve().parents[2]
_TRAIT_SOURCES_JSON = _PHASE1 / "vectorizer" / "config" / "trait_sources.json"
_FEAT_SOURCES_JSON = _PHASE1 / "vectorizer" / "config" / "feat_sources.json"

_CJK = re.compile(r"[一-鿿]")

# cn → 期望的统一 abbr（KN231 处置结果，含全部别名 key）
EXPECTED_ABBR = {
    "星辰之民": "PoS",
    "任务与战役": "Q&C",
    "格拉里昂的混种": "BaG",
    "格拉里昂的狗头人": "KobG",
    "格拉里昂的矮人": "DwaG",
    "格拉里昂的精灵": "EoG",
    "秽邪勇士": "CoCorr",
    "秘术选集": "ArAn",
}

# KN230 脏值，禁止在任何侧复用
KN230_DIRTY = {"CoP", "CoB", "CoC", "ArcaneAnthology", "Dragonslayer", "CAMPAIGN"}

# 均衡信念 en 已订正（2026-09-21 用户审批）：全部别名 key 的 en 锁定为 Faiths of Balance
BALANCE_ENTRY_CN = "均衡信念"
BALANCE_ENTRY_EN = "Faiths of Balance"


def _entries(doc):
    for _, v in doc.items():
        if isinstance(v, dict) and "abbr" in v:
            yield v
        elif isinstance(v, dict):
            yield from _entries(v)


@pytest.fixture(scope="module")
def trait_sources():
    return json.loads(_TRAIT_SOURCES_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def feat_abbrs():
    doc = json.loads(_FEAT_SOURCES_JSON.read_text(encoding="utf-8"))
    return {str(e["abbr"]) for e in _entries(doc)}


class TestKN231AbbrNormalization:
    @pytest.mark.parametrize("cn,abbr", sorted(EXPECTED_ABBR.items()))
    def test_all_alias_keys_synced(self, trait_sources, cn, abbr):
        group = [e for e in _entries(trait_sources) if e.get("cn") == cn]
        assert group, f"trait_sources 缺 {cn!r} 条目"
        assert len(group) >= 2, f"{cn!r} 别名 key 疑似丢失（仅 {len(group)} 条）"
        bad = [e["abbr"] for e in group if e["abbr"] != abbr]
        assert bad == [], f"{cn!r} 存在未同步别名 key: {bad}"

    def test_no_cjk_abbr_remaining(self, trait_sources):
        bad = sorted({str(e["abbr"]) for e in _entries(trait_sources) if _CJK.search(str(e["abbr"]))})
        assert bad == [], f"trait_sources 仍有中文 abbr: {bad}"

    def test_quests_alias_key_en_unified(self, trait_sources):
        hit = [e for e in _entries(trait_sources) if e.get("en") == "Quests and Campaigns"]
        assert hit == [], "别名 key 'Quests and Campaigns' 的旧 en 拼写复活"


class TestKN231NoCollision:
    def test_new_abbrs_not_in_feat(self, trait_sources, feat_abbrs):
        overlap = set(EXPECTED_ABBR.values()) & feat_abbrs
        # KN230（2026-09-21）后 CoCorr/ArAn 为跨模块同书同值（feat 侧归并时刻意
        # 对齐 trait 登记，非撞键）——仅当 feat 侧同缩写挂了不同书名才失败。
        feat_doc = json.loads(_FEAT_SOURCES_JSON.read_text(encoding="utf-8"))
        feat_en = {}
        for e in _entries(feat_doc):
            feat_en.setdefault(str(e["abbr"]), set()).add(e.get("en"))
        trait_en = {}
        for e in _entries(trait_sources):
            trait_en.setdefault(str(e["abbr"]), set()).add(e.get("en"))
        bad = {
            a: (sorted(feat_en[a]), sorted(trait_en.get(a, [])))
            for a in overlap
            if not feat_en[a] <= trait_en.get(a, set())
        }
        assert not bad, f"新缩写与 feat_sources 跨模块撞键（同缩写不同书）: {bad}"

    def test_new_abbrs_not_kn230_dirty(self):
        overlap = set(EXPECTED_ABBR.values()) & KN230_DIRTY
        assert not overlap, f"新缩写复用 KN230 脏值: {overlap}"

    def test_no_abbr_maps_to_multiple_en(self, trait_sources):
        by_abbr = {}
        for e in _entries(trait_sources):
            by_abbr.setdefault(str(e["abbr"]), set()).add(e.get("en"))
        collided = {a: sorted(es) for a, es in by_abbr.items() if len(es) > 1}
        assert collided == {}, f"trait 模块内 abbr 撞键: {collided}"


class TestBalanceEntryEnCorrected:
    def test_balance_entry_en_corrected(self, trait_sources):
        group = [e for e in _entries(trait_sources) if e.get("cn") == BALANCE_ENTRY_CN]
        assert group, f"缺条目 {BALANCE_ENTRY_CN!r}"
        bad = [e["en"] for e in group if e["en"] != BALANCE_ENTRY_EN]
        assert bad == [], (
            f"{BALANCE_ENTRY_CN!r} en 未同步为 {BALANCE_ENTRY_EN!r}: {bad}"
        )
