"""
test_rule_format_m5_kn100_supplement.py — tester 白盒审计补充测试

对 coder 的 TestM5Kn100RuleFamily（9 测试，已从 pyc 还原）的覆盖盲区补充：
  1. CR 开壳汇总行（page_539 改装块 `**CR` 形态，coder 测试只覆盖 XP）
  2. 词表外新字段标签负例（`**特殊效果**：…` 不入口，仍独立成节）
  3. 3 星壳与 2 星壳混合块（两种形态同块均并入）
  4. XP/CR 非汇总行负例（`**XPT** 20` / `**CR9**` 类不含空白分界 → 不入口）
  5. 骰表行边界：`**123**、`（3 位数字超 \d{1,2}）不入口
  6. 伤害减免负例（page_302 通用怪物规则真条目，与毒素对称）
"""

from vectorizer.tests.test_rule_format import run, titles


class TestM5Kn100Supplement:
    def test_cr_open_shell_summary_row_joins_parent(self):
        """page_539 改装块 `**CR` 开壳汇总行并入所属怪物条目（正例，
        coder 只测了 XP 形态，CR 形态单独钉住）"""
        raw = ("**改装骷髅（Skeletal Champion），CR 1/2**\n"
               "**CR 1/2** **XP 200**\n"
               "**先攻** +5；**感官** 黑暗视觉 60尺\n")
        items = run(raw)
        assert len(items) == 1, titles(items)
        assert "CR 1/2" in items[0]["text"]

    def test_label_outside_lexicon_not_sunk(self):
        """词表外的新字段标签不得剥除：`**特殊效果**：…` 仍独立成节"""
        raw = ("**自定义怪物（Custom）（B1）**\n"
               "**弱点**：强光敏感。\n"
               "**特殊效果**：每轮一次额外攻击。\n")
        items = run(raw)
        # 特殊效果 ∉ 词表 → 独立成节；弱点 ∈ M5 词表 → 并入所属（怪物）节
        assert "特殊效果" in titles(items), titles(items)
        n = [i for i in items if i["title"] == "自定义怪物（Custom）（B1）"][0]
        assert "**弱点**" in n["text"]

    def test_mixed_three_star_and_two_star_block(self):
        """3 星斜粗壳与 2 星壳字段行混合同块：两种形态均并入所属节"""
        raw = ("**混合数据块**\n"
               "**防御能力**\n"
               "**AC** 15\n"
               "***弱点*** ***(Weaknesses)：***强光敏感\n"
               "正文。\n")
        items = run(raw)
        assert len(items) == 1, titles(items)
        assert "**防御能力**" in items[0]["text"]
        assert "***弱点***" in items[0]["text"]

    def test_xp_cr_like_non_summary_row_not_sunk(self):
        """`**XPT**` / `**CR9**` 非汇总行（XP|CR 后无空白分界）不得剥除"""
        raw = ("**XPT 规则变体**\n"
               "XPT 是扩展职业等级规则。\n"
               "**CR9 测试节**\n"
               "内容。\n")
        items = run(raw)
        assert "XPT 规则变体" in titles(items), titles(items)
        assert "CR9 测试节" in titles(items)

    def test_dice_row_three_digit_not_sunk(self):
        """骰表行只认 1~2 位数字：`**123**、` 超界不入口，仍独立成节"""
        raw = ("**d100 大表**\n"
               "**123**、超界行。\n")
        items = run(raw)
        # 3 位数字超出 \d{1,2} → 不剥除，独立成节（d100 大表节不被吞）
        assert "123" in titles(items), titles(items)
        assert "d100 大表" in titles(items)

    def test_dice_row_two_digit_merges_under_table(self):
        """界内 2 位骰表行并入表节（与 coder 的 d10 正例同族，d100 边界）"""
        raw = ("**d100 大表**\n"
               "**9**、界内行。\n")
        items = run(raw)
        assert titles(items) == ["d100 大表"], titles(items)
        assert "**9**、界内行" in items[0]["text"]

    def test_damage_reduction_universal_rule_not_sunk(self):
        """负例：伤害减免（page_302 通用怪物规则真条目）不入口——
        与 coder 的毒素负例对称，防词表未来误加「减免」类词"""
        raw = ("**伤害减免（Damage Reduction）**\n"
               "拥有伤害减免的生物可以忽略每次受到的一定伤害。\n")
        items = run(raw)
        assert "伤害减免（Damage Reduction）" in titles(items), titles(items)
