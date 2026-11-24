"""KN096 亚产能全量核实：判别器口径收窄回归测试。

每条用例对应一个已核实的 est 多计形态（源文证据见
`docs/专长/KN096_亚产能逐条核实_20261113.md`）：

  1. FC-6g 正文括注（`一只豺化人（Jackalwere）蹲在你的家谱上。`）不是条目标题
  2. FC-6g 冒号定义行（`威慑（Menacing）：…`）不是条目标题
  3. FC-8q 系列/章节标题（`**位面导师系列专长** Plane-Hopper's…`）不是条目
  4. FC-G 行内定义标题（`　　**领导力值（Leadership Score）**：…`）不是条目
  5. FC-7b 小写英文（`恶棍志*** pg. 27`）是出处标注，不是条目
  6. FC-8e 佐证窗口越过下一个 `##` 标题 → 标签属于别的条目，不算佐证
  7. `## 中文（English）` 标题 + 同名正文加粗重述行 → 同一条目双计，只计标题
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../exploration/专长"))
import fc_match  # noqa: E402


def _counts(text: str) -> dict:
    counts, _ = fc_match.match_file(text)
    return dict(counts)


def test_fc6g_prose_parenthetical_not_counted():
    """RM L72 / 专长53 L50：正文句中的括注不是标题（rest 直连中文）"""
    text = (
        "**豺产**Jackal Heritage（PFS不可）\n"
        "一只豺化人（Jackalwere）蹲在你的家谱上。\n"
        "**先决条件：**人类，只能在1级获取\n"
        "**专长效果：**你获得豺化人的能力。\n"
    )
    assert _counts(text).get("FC-6g 无加粗括号粘连", 0) == 0


def test_fc6g_colon_definition_not_counted():
    """专长49 L90：`威慑（Menacing）：…` 是效果子项定义行"""
    text = (
        "**专长效果：**你可以获得下列益处。\n"
        "威慑（Menacing）：你的威吓和察言观色技能检定获得＋3加值，持续1小时。\n"
        "**先决条件：**体质13\n"
    )
    assert _counts(text).get("FC-6g 无加粗括号粘连", 0) == 0


def test_fc6g_standalone_title_still_counted():
    """专长24 背水之毅：标题行后为 PFS 标注（非中文直连）→ 仍计"""
    text = (
        "背水之毅(Strength in Defeat)  **PFS不可**\n"
        "\n"
        "先决条件：体质13\n"
        "专长效果：你无视一次失败。\n"
    )
    assert _counts(text).get("FC-6g 无加粗括号粘连", 0) == 1


def test_fc8q_series_title_not_counted():
    """专长12 L1：`**位面导师系列专长** Plane-Hopper's…` 是系列章节标题"""
    text = (
        "**位面导师系列专长** Plane-Hopper's Handbook pg. 13\n"
        "**先决条件：**角色等级5\n"
    )
    assert _counts(text).get("FC-8q 加粗名描述粘连", 0) == 0


def test_fc8q_real_entry_still_counted():
    """page_744 型：`**算术占卜**通过…` 真条目描述粘连仍计"""
    text = (
        "**算术占卜**通过将文字转换为数字，你可以预测未来。\n"
        "**先决条件：**知识（奥秘）5级\n"
    )
    assert _counts(text).get("FC-8q 加粗名描述粘连", 0) == 1


def test_fc_g_colon_definition_not_counted():
    """page_950 L16：`　　**领导力值（Leadership Score）**：…` 是行内定义"""
    text = (
        "\u3000\u3000**领导力值（Leadership Score）**：人物的基本领导力值等于其等级加上魅力修正。\n"
        "\n"
        "\u3000\u3000**领导力修正（Leadership Modifiers）**：有若干因素会影响人物的领导力数值。\n"
    )
    assert _counts(text).get("FC-G 粘连行内标题", 0) == 0


def test_fc7b_lowercase_en_source_note_not_counted():
    """VC L52：`恶棍志*** pg. 27` 是出处标注（小写 pg.）不是条目"""
    text = "恶棍志*** pg. 27\n"
    assert _counts(text).get("FC-7b 同行英文", 0) == 0


def test_fc7b_proper_case_en_still_counted():
    """page_311 型：`**脉轮修行者****Chakra Adept` 同行英文条目仍计"""
    text = (
        "**脉轮修行者****Chakra Adept\n"
        "**先决条件：**脉轮初学者\n"
        "**专长效果：**…\n"
    )
    assert _counts(text).get("FC-7b 同行英文", 0) == 1


def test_fc8e_corroboration_stops_at_next_heading():
    """EMH L43：地区介绍段落后的字段标签属于下一个 `##` 条目，不算佐证"""
    text = (
        "卡塔佩什Katapesh卡塔佩什的峡谷，沙漠和群山是不少与风相关的奇怪现象之源。\n"
        "\n"
        "## 风之歌（W）\n"
        "先决条件：表演（吹奏乐）5级\n"
        "专长效果：每天3次，你可以选择一个方格。\n"
    )
    assert _counts(text).get("FC-8e 无星裸英文粘连", 0) == 0


def test_fc8e_real_entry_still_counted():
    """水下冒险型：`深呼吸Deep breath 你屏住…` 后方字段标签同条目 → 仍计"""
    text = (
        "深呼吸Deep\n"
        "breath 你屏住呼吸，延长水下活动时间。\n"
        "先决条件：体质13\n"
        "专长效果：你可以屏息更久。\n"
    )
    assert _counts(text).get("FC-8e 无星裸英文粘连", 0) == 1


def test_heading_plus_same_name_body_counted_once():
    """MTT/RM 型：`## 中文（English）` 标题 + 同名正文加粗重述 = 同一条目"""
    text = (
        "## 敏锐射击（Acute Shot）\n"
        "> 来源：魔法战术工具箱\n"
        "\n"
        "**敏锐射击 acute shot **当魔法援助你的远程攻击时，你几乎从不失手。\n"
        "先决条件：远距射击，精确射击\n"
        "专长效果：你可以将远程攻击距离减值转为伤害减值。\n"
    )
    counts = _counts(text)
    assert counts.get("FC-H 井号标题", 0) == 1
    assert counts.get("FC-3 无括号英文", 0) == 0
    assert sum(counts.values()) == 1


def test_heading_with_different_body_entry_counted_twice():
    """标题是章节名、正文是别的条目 → 不合并（两计）"""
    text = (
        "## 敏锐射击（Acute Shot）\n"
        "\n"
        "**法术寻踪（Seeking Spell）**\n"
        "先决条件：远距射击\n"
        "**专长效果：**…\n"
    )
    counts = _counts(text)
    assert counts.get("FC-H 井号标题", 0) == 1
    assert counts.get("FC-1n 单行闭合无标签", 0) == 1


def test_fc8e_book_citation_not_counted():
    """page_1564 L2585：`护甲大师手册Armor Master's Handbook pg. 12` 是书目
    引用（页码标记），不是条目"""
    text = (
        "护甲大师手册Armor Master's Handbook pg. 12\n"
        "**先决条件：**力量13\n"
        "**专长效果：**…\n"
    )
    assert _counts(text).get("FC-8e 无星裸英文粘连", 0) == 0


def test_fc6_field_value_not_counted():
    """永罪之书 L147/L157：`魔族仪典（Fiendish Obedience ）` 是
    `**先决条件：**` 的字段值，不是条目标题（同一条目内出现两次）"""
    text = (
        "**先决条件：**\n"
        "魔族仪典（Fiendish Obedience ）\n"
        "**专长效果：**你获得神恩。\n"
    )
    assert _counts(text).get("FC-6 无加粗纯文本", 0) == 0


def test_fc6_real_entry_still_counted():
    """正例：`高原适应力（Altitude Affinity）` 独立标题后随字段标签"""
    text = (
        "高原适应力（Altitude Affinity）\n"
        "**先决条件：**体质13\n"
        "**专长效果：**你适应高海拔。\n"
    )
    assert _counts(text).get("FC-6 无加粗纯文本", 0) == 1
