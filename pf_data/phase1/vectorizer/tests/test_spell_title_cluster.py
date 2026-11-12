from pathlib import Path
from types import SimpleNamespace

from vectorizer.formats.spell import SpellFormat
from vectorizer.processors.spell import (
    SPELL_LEVEL_A_BUCKET_WHITELIST,
    SpellProcessor,
)

PHASE1 = Path(__file__).resolve().parents[2]


def split_titles(raw):
    fmt = SpellFormat()
    promoted = fmt.promote(fmt.normalize(raw))
    return promoted, fmt.split_into_items(promoted)


def test_crossline_roman_title_keeps_full_name():
    raw = "【塑能】撕扯肢体\nI（Rend Body I）\n\n**等级**：异能者 5\n"
    _, items = split_titles(raw)
    assert [(x['name'], x['name_en']) for x in items] == [
        ('撕扯肢体 I', 'Rend Body I')
    ]


def test_nested_chinese_subschool_and_english_title():
    raw = "【咒法】藏密箱(召唤) (Secret\nCoffer)\n\n**等级**：女巫 2\n"
    _, items = split_titles(raw)
    assert [(x['name'], x['name_en']) for x in items] == [
        ('藏密箱', 'Secret Coffer')
    ]


def test_translator_prefix_does_not_drop_spell_title():
    raw = (
        "【变化】高等油腻术（Grease, Greater）\n**等级**：魔战士 5\n"
        "◎[隐藏武器]译文来自笨哈【变化】隐藏武器(Hide Weapon)\n"
        "**等级**：魔战士 1\n"
    )
    _, items = split_titles(raw)
    assert [x['name'] for x in items] == ['高等油腻术', '隐藏武器']


def test_chapter_intro_does_not_swallow_next_spell():
    raw = (
        "【死灵】暗影打击(UMBRAL STRIKE)\n**等级**：女巫 7\n"
        "你创造一支黑暗能量箭。**半影法术\n"
        "尽管许多人认为阴影与光亮─同一概念的两个极端。**◎[起舞于黯]译文引自[笨哈]"
        "【塑能】起舞于黯(Dancing Darkness)[黑暗]\n**等级**：女巫 1\n"
    )
    _, items = split_titles(raw)
    assert [x['name'] for x in items] == ['暗影打击', '起舞于黯']
    assert all(x['name'] != '半影法术' for x in items)
    assert '两个极端。**' in items[0]['text']


def test_crossline_english_with_descriptor_and_link():
    raw = "【塑能】弧焰击(Burning\nArc)[火][珂莱士人](http://example.test)\n**等级**：女巫 2\n"
    _, items = split_titles(raw)
    assert [(x['name'], x['name_en']) for x in items] == [
        ('弧焰击', 'Burning Arc')
    ]


def test_prose_roman_reference_is_not_a_new_title():
    raw = (
        "【塑能】撕扯肢体 II（Rend Body II）\n**等级**：异能者 6\n"
        "该法术的功能如同撕扯肢体 I 一般。\n"
    )
    _, items = split_titles(raw)
    assert [x['name'] for x in items] == ['撕扯肢体 II']


def test_pure_translator_note_is_still_removed():
    fmt = SpellFormat()
    assert fmt._strip_translator_notes('◎ 纯译者说明\n**火球术 (Fireball)**') == (
        '\n**火球术 (Fireball)**'
    )


def test_bold_crossline_roman_title_keeps_full_name():
    raw = "**精类形态 \nI（FEY FORM I）****学派：**变化系（变形）**等级：**德鲁伊 3\n"
    _, items = split_titles(raw)
    assert [(x['name'], x['name_en']) for x in items] == [
        ('精类形态 I', 'FEY FORM I')
    ]


def test_linked_crossline_roman_title_keeps_full_name():
    raw = (
        "**召唤犬魔 \nII**（[Summon Barghest II](https://example.test)）\n"
        "出自Pathfinder Comics #10 pg. 26\n**学派：**咒法系（召唤）**等级：**牧师 6\n"
    )
    _, items = split_titles(raw)
    assert [(x['name'], x['name_en']) for x in items] == [
        ('召唤犬魔 II', 'Summon Barghest II')
    ]


def test_compact_crossline_roman_title_keeps_full_name():
    raw = (
        "直觉屏障（Reflexive barrier）学派：塑能系等级：异能者 3"
        "你可以眨一下眼睛。撕扯肢体 \nI（Rend body I）学派：塑能系等级：异能者 5"
    )
    _, items = split_titles(raw)
    assert ('撕扯肢体 I', 'Rend body I') in [
        (x['name'], x['name_en']) for x in items
    ]


def test_compact_same_line_roman_title_keeps_full_name():
    raw = (
        "直觉屏障（Reflexive barrier）学派：塑能系等级：异能者 3"
        "你可以眨一下眼睛。撕扯肢体 I（Rend body I）学派：塑能系等级：异能者 5"
    )
    _, items = split_titles(raw)
    assert ('撕扯肢体 I', 'Rend body I') in [
        (x['name'], x['name_en']) for x in items
    ]


def test_compact_roman_title_does_not_absorb_regenerate_note():
    raw = (
        "【塑能】撕扯肢体 I（Rend body I）\n**等级**：异能者 5\n"
        "注：再生术（Regenerate）撕扯肢体 II（Rend body II）学派：塑能系等级：异能者 6"
    )
    _, items = split_titles(raw)
    assert [(x['name'], x['name_en']) for x in items] == [
        ('撕扯肢体 I', 'Rend body I'),
        ('撕扯肢体 II', 'Rend body II'),
    ]


def test_legacy_chunk_id_ranges_restore_whitelist_lookup():
    from vectorizer.processors.spell import _legacy_spell_chunk_id

    chunk = SimpleNamespace(chunk_id='spell_page_1008_0008', doc_id='page_1008')
    assert _legacy_spell_chunk_id(chunk.chunk_id) == 'spell_page_1008_0007'
    assert SpellProcessor._a_bucket_whitelist_level({}, chunk) == (
        SPELL_LEVEL_A_BUCKET_WHITELIST['spell_page_1008_0007']
    )


def test_kn245_backfilled_entry_survives_chunk_id_shift():
    """KN245 裁定（2026-10-30）：受虐之影 解除裁除，旧 ID 顺移后照常回填。"""
    item = {
        'name': '受虐之影',
        'text': '**【死灵】受虐之影(Shadow Suffering)**\n**等级：**牧师 4\n',
        '_pre_unify_text': '【死灵】受虐之影(Shadow Suffering)**等级：**牧师 4',
    }
    chunk = SimpleNamespace(chunk_id='spell_page_1008_0018', doc_id='page_1008')
    assert SpellProcessor._rescue_inline_level(item, chunk) == [
        {'class': '牧师', 'level': 4}
    ]


def test_rescue_compact_roman_title_uses_own_level():
    item = {
        'name': '撕扯肢体 III',
        'text': '**撕扯肢体 III (Rend body III)**\n**等级：** 异能者 \n7',
        '_pre_unify_text': '说明。撕扯肢体 III（Rend body III）学派：塑能系等级：异能者 7',
    }
    chunk = SimpleNamespace(chunk_id='spell_异能选集PA_法术_0008', doc_id='异能选集PA_法术')
    assert SpellProcessor._rescue_inline_level(item, chunk) == [
        {'class': '异能者', 'level': 7}
    ]


def test_rescue_does_not_read_following_spell_levels():
    pre = (
        '撕扯肢体 III（Rend body III）学派：塑能系等级：异能者 \n7'
        '该法术的功能如同撕扯肢体II一般。'
        '撕扯肢体 IV（Rend body IV）学派：塑能系等级：异能者 \n8'
        '该法术的功能如同撕扯肢体III一般。'
        '感官过载（Sensory overload）学派：惑控系等级：异能者 \n2，术士/法师 2'
    )
    for index, name, level in ((8, '撕扯肢体 III', 7), (9, '撕扯肢体 IV', 8)):
        item = {
            'name': name,
            'text': f'**{name} (Rend body)**\n**等级：** 异能者 \n{level}',
            '_pre_unify_text': pre,
        }
        chunk = SimpleNamespace(
            chunk_id=f'spell_异能选集PA_法术_{index:04d}', doc_id='异能选集PA_法术'
        )
        assert SpellProcessor._rescue_inline_level(item, chunk) == [
            {'class': '异能者', 'level': level}
        ]


def test_cut_exclusion_does_not_hit_new_chunk_with_same_id():
    item = {
        'name': '群体自发性散瞳',
        'text': '**群体自发性散瞳 (Mydriatic Spontaneity, Mass)**\n**等级：** 催眠师 5',
        '_pre_unify_text': '【塑能】群体自发性散瞳(Mydriatic Spontaneity, Mass)等级：催眠师 5',
    }
    chunk = SimpleNamespace(chunk_id='spell_page_1365_0413', doc_id='page_1365')
    assert SpellProcessor._rescue_inline_level(item, chunk) == [
        {'class': '催眠师', 'level': 5}
    ]


def test_whitelist_fallback_rejects_mismatched_title():
    chunk = SimpleNamespace(chunk_id='spell_page_1365_0309', doc_id='page_1365')
    assert SpellProcessor._a_bucket_whitelist_level({'name': '藏密箱'}, chunk) == []


def test_derived_legacy_id_map_matches_whitelist_state():
    import json
    from vectorizer.processors.spell import (
        _SPELL_LEVEL_CUT_EXCLUSIONS,
        _legacy_spell_chunk_id,
    )

    state = json.loads(
        (PHASE1 / 'docs/state/spell_kn249_legacy_id_map.json').read_text(encoding='utf-8')
    )
    removed = {row['legacy_chunk_id'] for row in state['removed']}
    relevant_ids = set(SPELL_LEVEL_A_BUCKET_WHITELIST) | _SPELL_LEVEL_CUT_EXCLUSIONS
    for old_id in relevant_ids:
        matches = [row for row in state['id_map'] if row['legacy_chunk_id'] == old_id]
        if old_id in removed:
            assert matches == []
        else:
            assert len(matches) == 1, old_id
            assert _legacy_spell_chunk_id(matches[0]['current_chunk_id']) == old_id
    removed_page_1365 = [row for row in state['removed'] if row['doc_id'] == 'page_1365']
    assert [(row['chunk_id'], row['legacy_chunk_id']) for row in removed_page_1365] == [
        ('spell_page_1365_0330', 'spell_page_1365_0322')
    ]
    assert _legacy_spell_chunk_id('spell_page_669_0020') == 'spell_page_669_0021'


def test_added_chunks_do_not_hit_mismatched_whitelist_titles():
    import json
    from vectorizer.processors.spell import _is_cut_exclusion, _legacy_spell_chunk_id

    state = json.loads(
        (PHASE1 / 'docs/state/spell_kn249_legacy_id_map.json').read_text(encoding='utf-8')
    )
    for row in state['id_map']:
        if row['legacy_chunk_id'] is not None:
            continue
        chunk_id = row['current_chunk_id']
        assert _legacy_spell_chunk_id(chunk_id) is None
        assert not _is_cut_exclusion(chunk_id, row['title'])
        chunk = SimpleNamespace(chunk_id=chunk_id, doc_id=row['doc_id'])
        assert SpellProcessor._a_bucket_whitelist_level({'name': row['title']}, chunk) == []
    assert _legacy_spell_chunk_id('spell_Spell FoP_0020') == 'spell_Spell FoP_0019'


def test_school_title_does_not_consume_level_first_group():
    raw = (
        "【变化】狩猎大师之矛(Huntmaster's Spear)\n\n"
        "**等级**：反圣武士 \n1、血脉狂怒者 \n2、游侠/猎人 1 \n"
        "、审判者 \n2、萨满 \n2**施放时间**：10分钟\n"
    )
    _, items = split_titles(raw)
    assert len(items) == 1
    assert '**等级：** 反圣武士' in items[0]['text']
    assert '、审判者' in items[0]['text']


def test_real_page_1166_splits_secret_coffer():
    source = PHASE1 / 'pf_rules_md_organized/法术/玩家伴侣/page_1166.md'
    fmt = SpellFormat()
    items = fmt.split_into_items(fmt.promote(fmt.normalize(source.read_text(encoding='utf-8'))))
    assert [(x['name'], x['name_en']) for x in items if x['name'] == '藏密箱'] == [
        ('藏密箱', 'Secret Coffer')
    ]


def test_real_source_files_restore_title_entries():
    cases = [
        ('法术/玩家伴侣/page_805.md', '隐藏武器', 'Hide Weapon'),
        ('法术/玩家伴侣/page_1008.md', '起舞于黯', 'Dancing Darkness'),
        ('法术/玩家伴侣/page_1146.md', '弧焰击', 'Burning Arc'),
        ('法术/玩家伴侣/page_1173.md', '撕扯肢体 II', 'Rend Body II'),
        ('法术/战役设定/page_1363.md', '虫类型态 II', 'Vermin Shape II'),
        ('法术/玩家伴侣/page_1365.md', '手舞足蹈', 'Calamitous Flailing'),
    ]
    for rel, title, name_en in cases:
        source = PHASE1 / 'pf_rules_md_organized' / rel
        fmt = SpellFormat()
        items = fmt.split_into_items(fmt.promote(fmt.normalize(source.read_text(encoding='utf-8'))))
        assert (title, name_en) in [(x['name'], x['name_en']) for x in items], rel


def test_level_continuation_keeps_all_class_level_groups():
    raw = {
        'spell_level': (
            '反圣武士 \n1、血脉狂怒者 \n2、德鲁伊 \n2、游侠/猎人 1 \n'
            '、审判者 \n2、魔战士 \n2、秘学士 \n2、圣武士 \n1、萨满 \n2'
        )
    }
    assert SpellProcessor._extract_spell_level(raw) == [
        {'class': '反圣武士', 'level': 1},
        {'class': '血脉狂怒者', 'level': 2},
        {'class': '德鲁伊', 'level': 2},
        {'class': '游侠', 'level': 1},
        {'class': '猎人', 'level': 1},
        {'class': '审判者', 'level': 2},
        {'class': '魔战士', 'level': 2},
        {'class': '秘学士', 'level': 2},
        {'class': '圣武士', 'level': 1},
        {'class': '萨满', 'level': 2},
    ]


def test_cut_exclusion_applies_after_all_metadata_paths():
    """裁除机制保留但已清零：KN245 项不再被拦截，值正常写入 metadata。"""
    from vectorizer.processors.base import Chunk

    _, items = split_titles('【咒法】分享皮肤(Share Skin)\n**等级：** 德鲁伊 6、女巫 6\n')
    item = items[0]
    chunk = Chunk(
        chunk_id='spell_月之血脉BotM_法术_0001', doc_id='月之血脉BotM_法术',
        category='spell', component_type='spell', title=item['name'], text=item['text'],
        book_abbreviation='?', book_name_cn='', book_name_en='', source_confidence=0,
    )
    chunk = SpellProcessor.__new__(SpellProcessor).infer_metadata(chunk, item)
    assert {(i['class'], i['level']) for i in chunk.metadata['spell_level']} == {
        ('德鲁伊', 6), ('女巫', 6)
    }


def test_missing_chinese_title_uses_known_spell_name():
    _, items = split_titles('【死灵】(Calamitous Flailing)[诅咒]\n**等级**：女巫 3\n')
    assert [(x['name'], x['name_en']) for x in items] == [
        ('手舞足蹈', 'Calamitous Flailing')
    ]


def test_f1_anchor_compares_normalized_class_names():
    import contextlib
    import io
    from vectorizer.processors.base import Chunk

    _, items = split_titles('【咒法】测试术(Test)\n**等级**：战争祭司 0\n')
    chunk = Chunk(
        chunk_id='spell_page_1363_0061', doc_id='page_1363', category='spell',
        component_type='spell', title='测试术', text=items[0]['text'],
        book_abbreviation='?', book_name_cn='', book_name_en='', source_confidence=0,
    )
    with contextlib.redirect_stdout(io.StringIO()) as out:
        SpellProcessor.__new__(SpellProcessor).infer_metadata(chunk, items[0])
    assert "{'class': '战斗祭司', 'level': 0}" not in out.getvalue()


def test_kn245_backfilled_entries_are_not_cut_exclusions():
    """KN245 裁定（2026-10-30）：13 条源行可解析项解除裁除。"""
    from vectorizer.processors.spell import _is_cut_exclusion

    cases = {
        'spell_Spell FoP_0009': '轻量化',
        'spell_page_1008_0018': '受虐之影',
        'spell_page_1034_0005': '异龙形态 I',
        'spell_page_1034_0008': '奇龙形态 I',
        'spell_page_1048_0003': '踏焰行者',
        'spell_page_1168_0017': '高等天界治疗',
        'spell_page_1168_0029': '液化术',
        'spell_page_1363_0030': '食尸鬼的饥饿',
        'spell_page_1365_0282': '汲取毒素',
        'spell_page_1365_0380': '高等天界治疗',
        'spell_page_1365_0392': '液化术',
        'spell_page_1365_0422': '受虐之影',
        'spell_page_1365_0480': '奇龙形态 I',
        'spell_page_1365_0499': '踏焰行者',
    }
    for chunk_id, title in cases.items():
        assert not _is_cut_exclusion(chunk_id, title), (chunk_id, title)


def test_blackguard_bracket_alias_normalizes_to_antipaladin():
    """KN245：源文件括号缩写形态 黑暗卫士(Blk) → 反圣武士（全库仅 1 处）。"""
    from vectorizer.processors.spell import _normalize_class_name

    assert _normalize_class_name('黑暗卫士(Blk)') == '反圣武士'
    assert _normalize_class_name('黑暗卫士') == '反圣武士'


def test_kn245_ghoul_hunger_backfilled_via_alias():
    """食尸鬼的饥饿：括号别名归一后 7 组职业完整回填。"""
    from vectorizer.processors.base import Chunk

    _, items = split_titles(
        '【死灵】食尸鬼的饥饿(Ghoul Hunger)\n'
        '**等级：** 牧师/先知/战斗祭司 2、术士/法师/奥能师 2、黑暗卫士(Blk) 2\n'
    )
    item = items[0]
    chunk = Chunk(
        chunk_id='spell_page_1363_0030', doc_id='page_1363', category='spell',
        component_type='spell', title=item['name'], text=item['text'],
        book_abbreviation='CAMPAIGN', book_name_cn='战役设定', book_name_en='',
        source_confidence=75,
    )
    chunk = SpellProcessor.__new__(SpellProcessor).infer_metadata(chunk, item)
    got = {(i['class'], i['level']) for i in chunk.metadata['spell_level']}
    assert got == {
        ('牧师', 2), ('先知', 2), ('战斗祭司', 2),
        ('术士', 2), ('法师', 2), ('奥能师', 2), ('反圣武士', 2),
    }, got


def test_kn245_backfill_yields_levels_for_former_exclusion():
    """解除裁除后，主解析路径必须真正产出环级（不能只是不再拦截）。"""
    from vectorizer.processors.base import Chunk

    _, items = split_titles(
        '【塑能】液化术(Liquefy)\n'
        '**等级：** 炼金术师/调查员 3、吟游诗人/歌者 3、德鲁伊/猎人 4\n'
    )
    item = items[0]
    chunk = Chunk(
        chunk_id='spell_page_1168_0029', doc_id='page_1168', category='spell',
        component_type='spell', title=item['name'], text=item['text'],
        book_abbreviation='?', book_name_cn='', book_name_en='', source_confidence=0,
    )
    chunk = SpellProcessor.__new__(SpellProcessor).infer_metadata(chunk, item)
    got = {(i['class'], i['level']) for i in chunk.metadata['spell_level']}
    assert got == {
        ('炼金术师', 3), ('调查员', 3), ('吟游诗人', 3), ('歌者', 3),
        ('德鲁伊', 4), ('猎人', 4),
    }, got


def test_non_spell_entry_marks_spell_level_not_applicable():
    """KN245：毒品条目混入法术目录，环级标 not_applicable 且保持空。"""
    from vectorizer.processors.base import Chunk

    _, items = split_titles(
        '**阿底顿 (adyton)**\n'
        '类型 \n  接触；成瘾性 强，强韧DC 20\n'
        '价格 2,000 \n  gp\n'
        '**效果：** 受影响的生物额外进行一次DC 20的意志豁免掷骰。\n'
    )
    item = items[0]
    chunk = Chunk(
        chunk_id='spell_page_1494_0005', doc_id='page_1494', category='spell',
        component_type='spell', title=item['name'], text=item['text'],
        book_abbreviation='BotD', book_name_cn='永罪之书', book_name_en='',
        source_confidence=75,
    )
    chunk = SpellProcessor.__new__(SpellProcessor).infer_metadata(chunk, item)
    assert chunk.metadata['spell_level'] == []
    assert chunk.metadata['field_status']['spell_level'] == 'not_applicable'


# ---- SMF010：等级/环位 标签无冒号（KN245 2026-10-30 标签容错） ----

def _entry_levels(rel, title):
    from vectorizer.processors.base import Chunk

    source = PHASE1 / 'pf_rules_md_organized' / rel
    _, items = split_titles(source.read_text(encoding='utf-8'))
    item = next(x for x in items if x['name'] == title)
    chunk = Chunk(
        chunk_id='spell_测试_0000', doc_id='测试', category='spell',
        component_type='spell', title=item['name'], text=item['text'],
        book_abbreviation='?', book_name_cn='', book_name_en='', source_confidence=0,
    )
    chunk = SpellProcessor.__new__(SpellProcessor).infer_metadata(chunk, item)
    return {(i['class'], i['level']) for i in chunk.metadata['spell_level']}


def test_smf010_label_after_semicolon():
    """典礼形态：**学派：** 变化系；等级 \n牧师1，先知1，战斗祭司1"""
    got = _entry_levels('法术/任务与战役_法术.md', '典礼')
    assert got == {('牧师', 1), ('先知', 1), ('战斗祭司', 1)}, got


def test_smf010_bare_label_with_spaces():
    """BotM 形态：…[诅咒]环位      反圣武士 \n3, 术士/法师 3, 女巫 3"""
    got = _entry_levels('法术/月之血脉BotM_法术.md', '诅咒瞪视')
    assert got == {('反圣武士', 3), ('术士', 3), ('法师', 3), ('女巫', 3)}, got
    assert _entry_levels('法术/月之血脉BotM_法术.md', '分享皮肤') == {
        ('德鲁伊', 6), ('女巫', 6)
    }


def test_smf010_bare_label_same_line_as_school():
    """屠龙者形态：**学派：** 防护环位  \n炼金术士3，牧师3，德鲁伊2，术士/法师3"""
    got = _entry_levels('法术/屠龙者手册_法术.md', '龙龟之壳')
    assert got == {
        ('炼金术师', 3), ('牧师', 3), ('德鲁伊', 2), ('术士', 3), ('法师', 3)
    }, got


def test_smf010_empty_bold_label():
    """ARG 形态：**环位       ** + 空行 + 值行（诗人 需归一到吟游诗人）"""
    got = _entry_levels('法术/Spell ARG.md', '窃取呼吸')
    assert got == {('吟游诗人', 2), ('德鲁伊', 2), ('术士', 2), ('法师', 2)}, got


def test_smf010_does_not_touch_suffix_words():
    """负例：施法者等级 / 1分钟/等级 / 全部等级 不得被当成标签改写。"""
    from vectorizer.processors.spell import parse_fields
    fmt = SpellFormat()

    text = fmt.normalize(
        '**持续时间：**10分钟/等级  \n你的皮肉变灰发硬。\n'
        '**范围：** 特殊\n'
        '施法者等级  \n风力\n'
    )
    parsed = parse_fields(fmt.promote(text))
    assert "10分钟/等级" in parsed.get('duration', ''), parsed.get('duration')
    assert '**环位：**' not in text and '**等级：**' not in text.replace('**持续时间：**', '')


def _legacy_history_row(chunk_id, title, legacy_id=None, doc_id='page_1'):
    return {
        'chunk_id': chunk_id,
        'legacy_chunk_id': legacy_id if legacy_id is not None else chunk_id,
        'doc_id': doc_id,
        'title': title,
    }


def _legacy_current_row(chunk_id, title, doc_id='page_1'):
    return {'chunk_id': chunk_id, 'doc_id': doc_id, 'title': title}


def test_derived_legacy_id_map_shifts_following_rows_after_delete():
    from vectorizer.processors.spell_legacy_id_map import derive_legacy_id_state

    history = [
        _legacy_history_row('spell_page_1_0000', '甲'),
        _legacy_history_row('spell_page_1_0001', '乙'),
        _legacy_history_row('spell_page_1_0002', '丙'),
    ]
    current = [
        _legacy_current_row('spell_page_1_0000', '甲'),
        _legacy_current_row('spell_page_1_0001', '丙'),
    ]

    result = derive_legacy_id_state(history, current)

    assert [row['legacy_chunk_id'] for row in result['id_map']] == [
        'spell_page_1_0000', 'spell_page_1_0002'
    ]
    assert [row['chunk_id'] for row in result['removed']] == ['spell_page_1_0001']


def test_derived_legacy_id_map_marks_insert_without_legacy_anchor():
    from vectorizer.processors.spell_legacy_id_map import derive_legacy_id_state

    history = [
        _legacy_history_row('spell_page_1_0000', '甲'),
        _legacy_history_row('spell_page_1_0001', '乙'),
        _legacy_history_row('spell_page_1_0002', '丙'),
    ]
    current = [
        _legacy_current_row('spell_page_1_0000', '甲'),
        _legacy_current_row('spell_page_1_0001', '新增'),
        _legacy_current_row('spell_page_1_0002', '乙'),
        _legacy_current_row('spell_page_1_0003', '丙'),
    ]

    result = derive_legacy_id_state(history, current)

    assert [row['legacy_chunk_id'] for row in result['id_map']] == [
        'spell_page_1_0000', None, 'spell_page_1_0001', 'spell_page_1_0002'
    ]
    assert [row['chunk_id'] for row in result['added']] == ['spell_page_1_0001']


def test_derived_legacy_id_map_keeps_historical_added_row_unanchored():
    from vectorizer.processors.spell_legacy_id_map import derive_legacy_id_state

    row = _legacy_history_row('spell_page_1_0000', '新增')
    row['legacy_chunk_id'] = None

    result = derive_legacy_id_state([row], [_legacy_current_row('spell_page_1_0000', '新增')])

    assert result['id_map'][0]['legacy_chunk_id'] is None


def test_derived_legacy_id_map_rejects_replace():
    import pytest
    from vectorizer.processors.spell_legacy_id_map import derive_legacy_id_state

    with pytest.raises(ValueError, match='page_1'):
        derive_legacy_id_state(
            [_legacy_history_row('spell_page_1_0000', '旧名')],
            [_legacy_current_row('spell_page_1_0000', '新名')],
        )


def test_derived_legacy_id_map_rejects_ambiguous_duplicate_changes():
    import pytest
    from vectorizer.processors.spell_legacy_id_map import derive_legacy_id_state

    with pytest.raises(ValueError, match='重复标题'):
        derive_legacy_id_state(
            [_legacy_history_row('spell_page_1_0000', '同名')],
            [
                _legacy_current_row('spell_page_1_0000', '同名'),
                _legacy_current_row('spell_page_1_0001', '同名'),
            ],
        )
    with pytest.raises(ValueError, match='重复标题'):
        derive_legacy_id_state(
            [
                _legacy_history_row('spell_page_1_0000', '同名'),
                _legacy_history_row('spell_page_1_0001', '同名'),
                _legacy_history_row('spell_page_1_0002', '尾'),
            ],
            [
                _legacy_current_row('spell_page_1_0000', '同名'),
                _legacy_current_row('spell_page_1_0001', '尾'),
            ],
        )


def test_derived_legacy_id_map_rejects_duplicate_chunk_ids():
    import pytest
    from vectorizer.processors.spell_legacy_id_map import derive_legacy_id_state

    row = _legacy_history_row('spell_page_1_0000', '甲')
    with pytest.raises(ValueError, match='spell_page_1_0000'):
        derive_legacy_id_state([row, row], [])


def test_derived_legacy_id_state_round_trip_is_deterministic(tmp_path):
    import json
    from vectorizer.processors.spell_legacy_id_map import (
        load_legacy_id_map,
        save_derived_legacy_id_map,
    )

    baseline_path = tmp_path / 'baseline.json'
    output_path = tmp_path / 'derived.json'
    baseline_path.write_text(json.dumps({
        'id_map': [{
            'old_chunk_id': 'spell_page_1_0000',
            'new_chunk_id': 'spell_page_1_0001',
            'doc_id': 'page_1',
            'new_title': '甲',
        }],
        'added': [],
    }), encoding='utf-8')
    current = [_legacy_current_row('spell_page_1_0000', '甲')]

    first = save_derived_legacy_id_map(current, baseline_path, output_path)
    content = output_path.read_text(encoding='utf-8')
    second = save_derived_legacy_id_map(current, baseline_path, output_path)

    assert first == second == {'spell_page_1_0000': 'spell_page_1_0000'}
    assert output_path.read_text(encoding='utf-8') == content
    assert load_legacy_id_map(str(output_path)) == first
    state = json.loads(content)
    assert state['baseline_chunks'] == 1
    assert state['current_chunks'] == 1


def test_legacy_id_prescan_does_not_repeat_split_drop_logs(tmp_path, caplog):
    import logging
    from vectorizer.sources.providers import SourceResolver

    input_dir = tmp_path / '法术'
    input_dir.mkdir()
    (input_dir / 'page_1.md').write_text(
        '丢弃前言\n**等级：** 术士/法师 1\n【塑能】测试术(Test)\n**等级：** 术士/法师 3\n',
        encoding='utf-8',
    )
    processor = SpellProcessor(SourceResolver([]))

    with caplog.at_level(logging.WARNING, logger='vectorizer.formats.spell'):
        entries = processor._collect_legacy_id_current_entries(input_dir)

    assert [row['title'] for row in entries] == ['测试术']
    assert not [row for row in caplog.records if '[split_drop]' in row.getMessage()]
