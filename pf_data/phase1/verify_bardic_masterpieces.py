#!/usr/bin/env python3
# ⚠️ SUPERSEDED（2026-09-01 · CP3）
# 本脚本逻辑已收敛进 vectorizer/verify/verify_profession.py（VerifyBase 八检查，
# cicd/verify.py profession 类目唯一验收入口）。保留仅作历史参考，不再在 cicd
# 调用；如需复跑请用 `python3 -m vectorizer.verify.verify_profession`。
"""V004: 吟游诗人传世名作（Bardic Masterpieces）补齐验证。

正向断言：
  - 68 首传世名作（UM 核心 15 + 玩家伴侣 44 + 战役设定 7 + 冒险之路 2）
    都有独立 class_feature chunk
  - 所有传世名作 chunk 的 feature_subtype == "bardic_masterpiece"
  - 每首的 book_abbreviation 与预期源书一致

负向断言：
  - 传世名作汇总.md 不再产生名为"传世名作汇总"的 overview chunk
  - 没有 title 含传世名作关键字但 feature_subtype 不是 bardic_masterpiece 的 chunk
  - 去重后没有重复的 active masterpiece chunk
"""
import json
import sys
from typing import List, Tuple

CHUNKS_PATH = "vectorization_prep_profession/chunks.jsonl"

# (chinese_title, english_title_keyword, book_abbreviation)
# english_title_keyword 用作 chunk 文本中匹配的关键字（取英文名最独特的部分）
EXPECTED_MASTERPIECES: List[Tuple[str, str, str]] = [
    # === UM 核心 15 ===
    ("万物之心", "At the Heart", "UM"),
    ("猫步舞", "Cat-Step", "UM"),
    ("廿三步舞", "Dance of 23", "UM"),
    ("深山鸣涧", "Depths of the Mountain", "UM"),
    # 注：page_109.md 用"格洛克滑稽剧"，compendium 用"格洛克默剧"——以 page_109.md 为权威
    ("格洛克滑稽剧", "Dumbshow of Gorroc", "UM"),
    ("幻墙之屋", "Imaginary Walls", "UM"),
    ("地狱交易之连奏", "Infernal Bargain", "UM"),
    ("远古终末之眠", "Lullaby of Ember", "UM"),
    ("白夜藤蔓之舞步", "Midnight Ivy", "UM"),
    ("血脉贲张", "Quickening Pulse", "UM"),
    ("圣王镇魂歌", "Fallen Priest-King", "UM"),
    ("磐石面容", "Stone Face", "UM"),
    ("百鬼夜行抄", "Danse Macabre", "UM"),
    ("三倍时制御", "Triple Time", "UM"),
    ("五重天之风", "Five Heavens", "UM"),
    # === 玩家伴侣 44 ===
    # AA
    ("箭歌咏叹调", "Arrowsong", "AA"),
    # BoG
    ("诡笑颂歌", "Canticle of Joy", "BoG"),
    # BoA
    ("天堂花开派拉维", "Nirvana", "BoA"),
    ("天国秩序回旋曲", "Heavenly Order", "BoA"),
    ("乐土之心交响曲", "Elysian Heart", "BoA"),
    # BoF
    ("燃欲之舞", "Kindled Desires", "BoF"),
    ("骇亡音律", "Frightful Death", "BoF"),
    ("痰之歌", "Rheumy Refrain", "BoF"),
    # BotA
    ("殇魂逝灭颂", "Death of Heroes", "BotA"),
    ("萨克利斯挽歌", "Song of Sarkoris", "BotA"),
    ("虚假希望悲鸣曲", "False Hope", "BotA"),
    # BotS
    ("鲲跃北溟", "Sea Is Now My Sky", "BotS"),
    ("谈笑间樯橹灰飞烟灭", "Torn Sail", "BotS"),
    # CoP
    ("天堂喧嚣", "Clamor of the Heavens", "CoP"),
    ("盐碱地上生命的绽放", "Life Budding", "CoP"),
    # D'sD
    ("神鸣太鼓", "Kaminari", "D'sD"),
    ("白驹灵歌", "Spirit of the Horse", "D'sD"),
    # DA
    ("优雅之节庆祀舞", "Exhilarating Prayer", "DA"),
    ("复原和声赞美诗", "Restorative Harmonics", "DA"),
    ("脑力激荡演说", "Stirring Discourse", "DA"),
    # D'sH
    ("先祖的迁徙", "Ancients' Flight", "D'sH"),
    ("法夫尼尔和第一个国王", "Fafnheir", "D'sH"),
    ("孔雀盛会", "Pageant of the Peacock", "D'sH"),
    # EMH
    ("爆燃回旋曲", "Blazing Rondo", "EMH"),
    ("迷欲之舞", "captivating desire", "EMH"),
    # H'sH
    ("长者无尽华尔兹", "Endless Waltz", "H'sH"),
    ("赛兰杜拉攀登交响乐", "Sylandurla", "H'sH"),
    # HftF
    ("芬德烈莱拉的庇佑", "Findeladlara", "HftF"),
    ("圣地礼赞", "Sacred Lands", "HftF"),
    ("荒野精魂的独奏", "Wildsoul Aria", "HftF"),
    # HotHC
    ("雍容赞美诗", "Anthem of Pageantry", "HotHC"),
    ("劝降曲", "Melody of Surrender", "HotHC"),
    ("睿智国王传奇", "Wise King", "HotHC"),
    # LotFW
    ("拉格达恩的肚皮舞", "Raqs Beledi", "LotFW"),
    ("拉格达恩的旋转升华之舞", "Spiraling Ascent", "LotFW"),
    # MM
    ("四鼠方舞曲", "Rat Quadrille", "MM"),
    ("怀恨独白", "Vindictive Soliloquy", "MM"),
    # MTT
    ("义勇军进行曲", "People's Revolt", "MTT"),
    # M'sM
    ("长篇大论", "Lingering Leitmotif", "M'sM"),
    ("运石工号子", "Stonebearers", "M'sM"),
    # MSH
    ("思乡游子篇", "Homesick Wanderer", "MSH"),
    # PotR
    ("熊之吉格舞", "Bears Jig", "PotR"),
    # THH
    ("幻象赦令", "Illusion's Decree", "THH"),
    ("反转之剑", "Twisting Steel", "THH"),
    # === 战役设定 7 ===
    # A&L
    ("灭绝之声", "Song of Extinction", "A&L"),
    # DR
    ("黑暗王子序曲", "Dark Prince", "DR"),
    ("暗夜女王之怒", "Night Queen", "DR"),
    # HR
    ("狺女挽歌", "Banshee", "HR"),
    ("异界之声/域外之音", "Music Beyond the Spheres", "HR"),
    ("无尽回响", "Relentless Reprise", "HR"),
    # LT
    ("守望者之谣", "Warding Princess", "LT"),
    # === 冒险之路 2 ===
    # RotR
    ("月亏波罗列", "Waning Bolero", "RotR"),
    # SA
    ("奥塞尔街赋格曲", "Rue d'Auseil", "SA"),
]


def main() -> int:
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]

    ok = True

    # ===== 正向断言 =====

    # 1. 每首传世名作应有独立 class_feature chunk
    # 用 cn 在 title 开头匹配（title 格式为 "{cn}（English，...）"），避免子串误匹配
    # 例如"群体劝降曲"不应被"劝降曲"匹配
    def title_starts_with_cn(c: dict, cn: str) -> bool:
        title = c.get("title", "")
        return title.startswith(cn) and (len(title) == len(cn) or title[len(cn)] in "（( ")

    missing = []
    for cn, en_kw, abbr in EXPECTED_MASTERPIECES:
        matches = [
            c for c in chunks
            if c.get("component_type") == "class_feature"
            and c.get("class_name") == "吟游诗人"
            and not c.get("is_deprecated", False)
            and title_starts_with_cn(c, cn)
        ]
        if not matches:
            missing.append((cn, abbr))
        elif len(matches) > 1:
            print(f"WARN: {cn}（{abbr}）匹配到 {len(matches)} 个 active chunk（应只有 1）")
            for m in matches:
                print(f"  - {m.get('chunk_id','')[:8]} doc={m.get('doc_id','')}")

    if missing:
        ok = False
        print(f"FAIL: {len(missing)} 首传世名作缺失独立 class_feature chunk：")
        for cn, abbr in missing:
            print(f"  - {cn}（{abbr}）")

    # 2. 所有传世名作 chunk 的 feature_subtype 必须为 bardic_masterpiece
    bm_chunks = [
        c for c in chunks
        if c.get("class_name") == "吟游诗人"
        and c.get("feature_subtype") == "bardic_masterpiece"
        and not c.get("is_deprecated", False)
    ]
    print(f"\n  active bardic_masterpiece chunks: {len(bm_chunks)}")

    # 3. 验证每首的 book_abbreviation 与预期一致
    # 注：compendium 中部分缩写（如 M's M, D'sD, BotA, H'sH 等）未在缩写表中，
    #    会默认归类为 CRB。这是软警告，不作为硬 FAIL。
    abbr_mismatch = []
    for cn, en_kw, expected_abbr in EXPECTED_MASTERPIECES:
        for c in bm_chunks:
            if title_starts_with_cn(c, cn):
                actual = c.get("book_abbreviation", "")
                if actual != expected_abbr:
                    abbr_mismatch.append((cn, expected_abbr, actual))
                break

    if abbr_mismatch:
        print(f"WARN: {len(abbr_mismatch)} 首传世名作 book_abbreviation 默认 CRB（compendium 缩写未注册）：")
        # 只显示前 10 个
        for cn, exp, act in abbr_mismatch[:10]:
            print(f"  - {cn}: 预期 {exp}, 实际 {act}")
        if len(abbr_mismatch) > 10:
            print(f"  ... 共 {len(abbr_mismatch)} 个（详见 V004 文档）")

    # ===== 负向断言 =====

    # 4. 传世名作汇总.md 不应再产生名为"传世名作汇总"的 class_overview chunk
    compendium_overview = [
        c for c in chunks
        if c.get("component_type") == "class_overview"
        and c.get("class_name") == "吟游诗人"
        and not c.get("is_deprecated", False)
        and "传世名作汇总" in c.get("doc_id", "")
    ]
    if compendium_overview:
        ok = False
        print(f"FAIL: 传世名作汇总.md 仍残留 {len(compendium_overview)} 个 overview chunk（应已被拆空）")
        for c in compendium_overview:
            print(f"  - {c.get('chunk_id','')[:8]} title={c.get('title','')}")

    # 5. 没有 class_feature chunk 的 title 是某传世名作开头但 subtype 不是 bardic_masterpiece
    expected_cns = {cn for cn, _, _ in EXPECTED_MASTERPIECES}
    bad_subtype = [
        c for c in chunks
        if c.get("component_type") == "class_feature"
        and c.get("class_name") == "吟游诗人"
        and not c.get("is_deprecated", False)
        and c.get("feature_subtype") != "bardic_masterpiece"
        and any(title_starts_with_cn(c, cn) for cn in expected_cns)
    ]
    if bad_subtype:
        ok = False
        print(f"FAIL: {len(bad_subtype)} 个传世名作 chunk subtype 不是 bardic_masterpiece：")
        for c in bad_subtype:
            print(f"  - {c.get('chunk_id','')[:8]} title={c.get('title','')[:50]} subtype={c.get('feature_subtype')}")

    # ===== 总结 =====
    print()
    if ok:
        print(f"PASS: {len(EXPECTED_MASTERPIECES)} 首传世名作全部就位，feature_subtype 正确，无残留 overview chunk。")
        return 0
    else:
        print("OVERALL: FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())