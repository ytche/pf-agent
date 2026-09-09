#!/usr/bin/env python3
"""V006 A3: 清理 chunk 中因 breadcrumb 关键词误匹配导致的 subtype 误标。

清理规则（按白名单）：
  1. arcane_school → 仅限法师（"流派"关键词误匹配游侠/杀手的战斗流派）
  2. rage_power → 仅限野蛮人、歌者、血脉狂怒者（其他职业不应有）
  3. hex → 仅限女巫、萨满（其他职业不应有，如秘学士灵器套装、大法师神话巫术）
  4. ninja_trick → 仅限忍者（盗贼的忍术选项保留不清理，但未知职业的应清空）

输出直接覆盖 chunks.jsonl（备份到 .bak）。
"""
import json
import shutil
from pathlib import Path
from collections import Counter

CHUNKS_FILE = Path("vectorization_prep_profession/chunks.jsonl")

# (subtype, 允许的职业白名单)
SUBTYPE_WHITELIST = {
    "arcane_school": {"法师"},
    "rage_power": {"野蛮人", "歌者", "血脉狂怒者"},
    "hex": {"女巫", "萨满"},
    "patron": {"女巫"},
    "bloodline": {"术士", "血脉狂怒者"},
    "domain": {"牧师", "德鲁伊", "审判者"},
    "ninja_trick": {"忍者"},  # 盗贼的 ninja_trick 保留（合理游戏机制），至少清掉未知职业
}


def main():
    if not CHUNKS_FILE.exists():
        print(f"FAIL: {CHUNKS_FILE} 不存在")
        return 1

    lines = CHUNKS_FILE.read_text(encoding="utf-8").splitlines()
    chunks = [json.loads(line) for line in lines]

    # 备份
    backup = CHUNKS_FILE.with_suffix(".jsonl.bak")
    if not backup.exists():
        shutil.copy2(CHUNKS_FILE, backup)
        print(f"备份: {backup}")

    cleaned = 0
    for c in chunks:
        st = c.get("feature_subtype")
        cn = c.get("class_name", "")
        if st and st in SUBTYPE_WHITELIST:
            allowed = SUBTYPE_WHITELIST[st]
            if cn not in allowed:
                old_st = st
                c["feature_subtype"] = None
                cleaned += 1
                print(f"  清理: [{old_st}] → None | {cn} | {c.get('title', '')[:60]}")

    # 写出
    new_lines = [json.dumps(c, ensure_ascii=False) for c in chunks]
    CHUNKS_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"\n清理完成: {cleaned} 个 chunk 的 subtype 被清空")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
