# ⚠️ SUPERSEDED（2026-09-01 · CP3）
# 本脚本逻辑已收敛为 pytest 单测 vectorizer/tests/test_profession_heading_levels.py
# （对 ProfessionProcessor.process(PAGE_55) 的块化产物断言，等价于清洗层行为回归，
# 不读产物）。保留仅作历史参考，不再在 cicd 调用。
"""heading 层级回归测试。

针对 `核心职业/圣骑士/page_55.md` 跑 PaladinProcessor.clean()，
断言所有 expected heading 仍保持预期层级，不会被 `_fix_paladin_page_55`
等专项后处理降级。

问题来源：page_55.md 中 `圣律沿循者` 段下大量 `### / ####` 嵌套标题
被 `_fix_paladin_page_55` 步骤 2 的 lookbehind 正则误判为"内嵌 heading"，
最终被错误降级为 `##`（level 2），导致下挂子能力被识别为顶层变体。
"""
import sys
from pathlib import Path

# 让脚本可直接 `python3 verify_heading_levels.py` 跑
sys.path.insert(0, str(Path(__file__).parent))

import vectorization_prep_profession as vp
from vectorization_prep_profession import PaladinProcessor


PAGE_55 = Path(__file__).parent / "pf_rules_md_organized" / "职业" / "核心职业" / "圣骑士" / "page_55.md"

# 期望的 heading 层级（按 圣律沿循者 section 内的真实结构）
# 注意：_fix_paladin_page_55 步骤 5 会把变体标记规范为【圣骑士变体】，
# 因此 L2 标题需与清洗后的实际文本保持一致。
EXPECTED = {
    2: [
        "圣律沿循者（Oathbound Paladin，又译誓缚圣武士）【圣骑士变体】",
    ],
    3: [
        "神祇（Deity）",
        "行为准则（Code of Conduct）",
        "圣律法术（Oath Spells）",
        # 10 个子誓约 — 这些是圣律沿循者的子能力，必须保持 level 3
        "反腐化誓约（Oath against Corruption）",
        "反邪魔誓约（Oath against Fiends）",
        "反野蛮誓约（Oath against Savagery）",
        "反亡灵誓约（Oath against Undeath）",
        "反邪龙誓约（Oath against the Wyrm）",
        "反混乱誓约（Oath against Chaos）",
        "仁慈誓约（Oath of Charity）",
        "贞洁誓约（Oath of Chastity）",
        "忠诚誓约（Oath of Loyalty）",
        "复仇誓约（Oath of Vengeance）",
    ],
    4: [
        # 反腐化誓约 下的子能力
        "纯净灵光（Aura of Purity, Su）",
        "净化之焰（Cleansing Flame, Sp）",
        "归于虚空（Cast into the Void, Su）",
        # 反邪魔誓约 下的子能力
        "锚定灵光（Anchoring Aura, Su）",
        "圣仆（Holy Vessel, Su）",
        # 人民民主誓约 源格式是 ``Oath of the People`s Council``（无括号），
        # promote 链路识别为 level 4，与其他 10 个子誓约不同
        "人民民主誓约 Oath of the People`s Council",
    ],
}


def _strip_md_heading(line: str) -> str:
    """去掉 `## ` / `### ` / `#### ` 前缀，返回纯标题文本。"""
    s = line.strip()
    while s.startswith("#"):
        s = s[1:]
    return s.strip()


def collect_cleaned_headings(file_path: Path) -> dict:
    """跑 PaladinProcessor.clean()，返回 {level: [title, ...]} 映射。"""
    book_lookup = vp.load_abbreviation_table(Path("规则书缩写对应表.md"))
    ctx = {
        "input_dir": Path(__file__).parent / "pf_rules_md_organized" / "职业",
        "md_mapping": {},
        "book_lookup": book_lookup,
        "class_index": {},
        "archetype_masters": {},
    }
    rel_path = Path("核心职业/圣骑士/page_55.md")
    proc = PaladinProcessor(file_path=file_path, rel_path=rel_path, ctx=ctx)
    cleaned, _ = proc.clean(file_path.read_text(encoding="utf-8").splitlines())

    headings: dict = {}
    for line in cleaned:
        s = line.lstrip()
        if not s.startswith("#"):
            continue
        # 计算 # 数量
        level = 0
        for ch in s:
            if ch == "#":
                level += 1
            else:
                break
        if level < 1 or level > 6:
            continue
        # 确保 # 后面是空格（合法 heading）
        if level >= len(s) or s[level] != " ":
            continue
        title = _strip_md_heading(line)
        if not title:
            continue
        headings.setdefault(level, []).append(title)
    return headings


def assert_headings(cleaned: dict) -> list:
    """对照 EXPECTED 检查，收集所有错误信息。"""
    errors = []
    for level, expected_titles in EXPECTED.items():
        actual = cleaned.get(level, [])
        actual_set = set(actual)
        for expected_title in expected_titles:
            if expected_title not in actual_set:
                errors.append(
                    f"  [L{level}] 缺失期望标题: {expected_title!r}\n"
                    f"        实际 level={level} 标题: {actual[:5]}{'...' if len(actual) > 5 else ''}"
                )
    return errors


def main():
    if not PAGE_55.exists():
        print(f"ERROR: 源文件不存在: {PAGE_55}")
        sys.exit(2)

    print(f"正在跑 PaladinProcessor.clean() on {PAGE_55.name} ...")
    cleaned = collect_cleaned_headings(PAGE_55)
    print(f"  清洗后 heading 统计: " + ", ".join(
        f"L{k}={len(v)}" for k, v in sorted(cleaned.items())
    ))

    errors = assert_headings(cleaned)
    if errors:
        print("\nFAILED: heading 层级回归失败:")
        for e in errors:
            print(e)
        sys.exit(1)

    print("\nPASSED: 所有期望 heading 层级正确，未被降级")
    sys.exit(0)


if __name__ == "__main__":
    main()