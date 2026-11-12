"""KN233：spell_lists 黏连名拆分 + 法术条目中文别名补录。

覆盖：
1. spell_list_export.GLUED_NAME_SPLITS——「精神错乱月狂病（moonstruck）」拆为两条独立条目；
2. postprocess.spell_chain.SupplementSpellAliases——curated 中文别名补录，幂等。
"""
import json
import sys
from pathlib import Path

import pytest

PHASE1_ROOT = Path(__file__).resolve().parents[2]
if str(PHASE1_ROOT) not in sys.path:
    sys.path.insert(0, str(PHASE1_ROOT))

from spell_list_export import extract_entries, GLUED_NAME_SPLITS  # noqa: E402
from vectorizer.postprocess.spell_chain import SupplementSpellAliases  # noqa: E402


class TestGluedNameSplits:
    def test_moonstruck_glued_pair_splits_into_two(self):
        body = '类人形态 II（monstrous physique II）精神错乱月狂病（moonstruck）风之河（river of wind）'
        out = extract_entries(body, 'APG')
        cn_names = [cn for cn, _, _ in out]
        assert '精神错乱' in cn_names
        assert '月狂病' in cn_names
        assert '精神错乱月狂病' not in cn_names
        # 拆分出的两条共享同一英文名/书，各自可独立交叉到同一 chunk
        moon = [(cn, en, bk) for cn, en, bk in out if cn in ('精神错乱', '月狂病')]
        assert len(moon) == 2
        assert all(en == 'moonstruck' and bk == 'APG' for _, en, bk in moon)

    def test_unaffected_entries_pass_through(self):
        out = extract_entries('火球术（Fireball）', 'CRB')
        assert out == [('火球术', 'Fireball', 'CRB')]

    def test_split_table_keys_are_canonical(self):
        for (cn, en), parts in GLUED_NAME_SPLITS.items():
            assert cn and en and len(parts) >= 2
            assert all(p and p != cn for p in parts)


class TestSupplementSpellAliases:
    def _chunks(self):
        return [
            {'chunk_id': 'spell_Spell ISWG_0011', 'title': '不退、不悔、不降！/永固之心',
             'aliases': ['Unbreakable Heart']},
            {'chunk_id': 'spell_Spell APG_0159', 'title': '精神错乱',
             'aliases': ['Moonstruck']},
            {'chunk_id': 'spell_other', 'title': '别的法术', 'aliases': ['X']},
        ]

    def test_alias_appended_for_listed_chunk(self):
        chunks = self._chunks()
        stats = SupplementSpellAliases().supplement(chunks)
        by_id = {c['chunk_id']: c for c in chunks}
        assert '不屈之心' in by_id['spell_Spell ISWG_0011']['aliases']
        assert '月狂病' in by_id['spell_Spell APG_0159']['aliases']
        assert by_id['spell_other']['aliases'] == ['X']
        assert stats['added'] == 2

    def test_idempotent_on_second_pass(self):
        chunks = self._chunks()
        sup = SupplementSpellAliases()
        sup.supplement(chunks)
        stats = sup.supplement(chunks)
        assert stats['added'] == 0
        by_id = {c['chunk_id']: c for c in chunks}
        assert by_id['spell_Spell ISWG_0011']['aliases'].count('不屈之心') == 1
