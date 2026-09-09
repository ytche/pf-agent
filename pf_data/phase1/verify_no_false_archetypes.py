# ⚠️ SUPERSEDED（2026-09-01 · CP3）
# 本脚本逻辑已收敛进 vectorizer/verify/verify_profession.py（VerifyBase 八检查，
# cicd/verify.py profession 类目唯一验收入口）。保留仅作历史参考，不再在 cicd
# 调用；如需复跑请用 `python3 -m vectorizer.verify.verify_profession`。
import json
import re
from pathlib import Path

CHUNKS = Path('vectorization_prep_profession/chunks.jsonl')

# V001 false-positive patterns: headings that should NEVER be classified as class_archetype.
FALSE_PATTERNS = [
    # 通用职业字段
    r'阵营\s*[（(][A-Za-z][^）)]*[）)]\s*[：:]',
    r'本职技能\s*[（(][A-Za-z][^）)]*[）)]\s*[：:]',
    r'语言\s*[（(][A-Za-z][^）)]*[）)]\s*[：:]',
    r'法术\s*[（(][A-Za-z][^）)]*[）)]\s*[：:]',
    r'武器和防具擅长\s*[（(][A-Za-z][^）)]*[）)]\s*[：:]',
    r'武器和防具熟练\s*[（(][A-Za-z][^）)]*[）)]\s*[：:]',
    r'文盲\s*[（(][A-Za-z][^）)]*[）)]\s*[：:]',
    # 女巫庇护主主题
    r'^(早春|盛夏|深秋|寒冬|荆棘|林地)\s*[（(][A-Za-z][^）)]*[）)]\s*[：:]',
    # 吟游诗人
    r'占卜算命\s*[（(]',
    r'晦涩之诵\s*[（(]',
    r'精类联系网\s*[（(]',
    r'召唤精类盟友\s*[（(]',
    # 审判者
    r'神祇\s*[（(][A-Za-z][^）)]*[）)]\s*[：:]',
    # 歌者
    r'虔信\s*[（(][A-Za-z][^）)]*[）)]\s*[：:]',
    # 炼金术师
    r'寒霜炸弹\s*[（(]',
    # 秘学士
    r'强化之灵\s*[（(]',
    # 德鲁伊
    r'自然纽带\s*[（(]',
    r'野性形态\s*[（(]',
    # 女巫
    r'女巫织者\s*[（(]',
    r'女巫庇护主主题\s*[（(]',
    r'戏法\s*[（(][A-Za-z][^）)]*[）)]\s*[：:]',
    r'恶魔契约\s*[（(]',
    # 猎人动物伙伴选项（示例）
    r'^(海狸|宫廷伙伴|变色龙|鹰|狐狸|伞蜥|章鱼|浣熊|歌鸟|蝙蝠|猎鹰|鼠|枭|蚂蚁|甲虫|蠕虫)\s*[（(][A-Za-z][^）)]*[）)]\s*[：:]',
    # Bug B: 通用章节标题（无尾部冒号）
    r'^本职技能\s*[（(]',
    r'^阵营\s*[（(]',
    r'^技能\s*[（(]',
    r'^神祇\s*[（(]',
    r'^血脉\s*[（(]',
    r'^炫技\s*[（(]',
    # Bug C: 表格行残留
    r'^\d+级[【\s]',
    r'^基础购买价值|^购买限额|^吟游诗人等级',
    # Bug D: URL/译者注
    r'https?://',
    # Bug E: 前提/效果作为标题
    r'^前提[：:]\s*[^\]]',  # "前提：法师等级..." merged body
    r'^效果[：:]',           # "效果：" as title start
    r'^特殊[：:]',           # "特殊：" as title start
]


def main():
    errors = []
    with CHUNKS.open(encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            if c.get('component_type') != 'class_archetype':
                continue
            title = c.get('title', '')
            if any(re.search(p, title) for p in FALSE_PATTERNS):
                errors.append((c.get('class_name', ''), title, c.get('doc_id', '')))

    if errors:
        print(f'FAIL: 仍有 {len(errors)} 条误识别为 class_archetype 的 V001 条目：')
        for cls, title, doc_id in errors[:20]:
            print(f'  - [{cls}] {title}  ({doc_id})')
        raise SystemExit(1)
    print(f'PASS: V001 negative test 通过，未在 {CHUNKS} 中发现误识别条目。')


if __name__ == '__main__':
    main()
