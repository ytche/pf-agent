"""
test_fc_match.py — 判别器（fc_match.py）单元测试

背景（v2.2 决策 F 落实）：K5 修复（aa6b3ff）把 \r 裸断行表格合并为完整单行
「英文名+空格+中文名」形态后，is_split_row 的「首单元格含中文」闭合行判据
误杀字典序单行表（page_195 型）——单行表每行首单元格都含中文译名 → 全表
被跳过（判别器计数 171→1）。修复：判据收窄为「首单元格以中文开头」，
区分真跨行断表闭合行（page_361 '| 鲨蜥流 |'）与单行表（'| Catch Off-Guard* 随手武器* |'）。

四种形态回归保护：
  1. page_195 型（K5 后单行表格）：不跳过
  2. page_361 型（真跨行断表，英文首行 + 纯中文闭合行）：跳过
  3. page_856 型（中文首单元格独立条目）：不进第一层判据
  4. page_199/203 型（窗口内无闭合行）：不跳过
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../exploration/专长"))
import fc_match  # noqa: E402


def _lines(text: str) -> list:
    return text.split("\n")


def test_split_row_single_row_table_not_skipped():
    """page_195 型（K5 修复后形态）：单行表每行首单元格为「英文+空格+中文」，
    相邻行首单元格以英文开头 → 不是跨行断表，不跳过"""
    lines = _lines(
        "| Acrobatic        特技专家 |  | 特技和飞行检定+2 |\n"
        "| Alertness        警觉 |  | 察觉和察言观色检定+2 |\n"
        "| Animal         Affinity        动物亲和 |  | 驯养动物和骑术检定+2 |\n"
        "| Arcane         Armor Training*        披甲奥术训练* | 擅长轻甲 | 降低奥术施法失败率 |\n"
    )
    assert not fc_match.is_split_row(lines, 0)


def test_split_row_standard_feat_line_not_skipped():
    """字典序标准形态（带 * 译名后缀）：相邻行首单元格同样英文开头 → 不跳过"""
    lines = _lines(
        "| Blind-Fight*        盲斗* |  | 对隐蔽的对手攻击失手后重骰 |\n"
        "| Catch Off-Guard*        随手武器* |  | 使用临时近战武器无减值 |\n"
        "| Channel Smite*        导能打击* | 引导能量职业特性 | 引导能量至攻击 |\n"
    )
    assert not fc_match.is_split_row(lines, 0)


def test_split_row_split_table_skipped():
    """page_361 型（真跨行断表）：英文首单元格行后紧跟「纯中文首单元格闭合行」→
    冗余首行，跳过（同一条目双行，由闭合行计数）"""
    lines = _lines(
        "| Bulette         Charge Style | 力量13，精通闯越，猛力攻击，擅长重甲 | 在对对手进行闯越战技时获得+4加值 |\n"
        "| 鲨蜥流 |\n"
        "| Bulette Leap | 力量15，鲨蜥流，精通闯越，猛力攻击，擅长重甲 | 跳跃获得力量调整值的加值 |\n"
        "| 鲨蜥·扑 |\n"
    )
    assert fc_match.is_split_row(lines, 0)
    # 闭合行自身（中文首单元格）不是英文首行 → 不跳过
    assert not fc_match.is_split_row(lines, 1)


def test_split_row_chinese_first_cell_never_enters():
    """page_856 型（中文首单元格独立条目）：第一层英文判据不满足 → False"""
    lines = _lines(
        "| 鲨蜥流 |\n"
        "| 鲨蜥·扑 |\n"
    )
    assert not fc_match.is_split_row(lines, 0)


def test_split_row_no_closing_row_not_skipped():
    """page_199/203 型：窗口内无 ≥2| 闭合行（续行缩进无 |）→ 不跳过"""
    lines = _lines(
        "| Acrobatic        特技专家 |  | 特技和飞行检定+2 |\n"
        "这是一段正文描述，不是表格行。\n"
        "下一段正文，也没有管道符。\n"
    )
    assert not fc_match.is_split_row(lines, 0)
