"""
conftest.py — 共享测试 fixtures

提供：
  - 各格式变体的法术样本文本
  - SpellFormat 实例
  - SourceResolver / SourceContext 实例
"""

import pytest

from vectorizer.formats.spell import SpellFormat
from vectorizer.sources.providers import SourceContext, SourceResolver
from vectorizer.sources.providers import (
    FileNameAbbrProvider, DefaultProvider, ALL_PROVIDERS,
)


# ===== 格式变体样本 =====

@pytest.fixture
def spell_format() -> SpellFormat:
    return SpellFormat()


@pytest.fixture
def sample_crb_text() -> str:
    """格式变体 A — 管道表格（类 CRB 格式）"""
    return (
        "**强酸箭 (Acid Arrow)**\n"
        "| 学派 咒法系（创造） | 环位 魔战士 2, 术士/法师 2, 召唤师 2 |\n"
        "| 施法时间 标准动作 | 成分 语言, 姿势, 材料（箭） |\n"
        "| 范围 远程 | 目标 一个生物 | 持续时间 1轮/等级 |\n"
        "| 豁免 无 | 法术抗力 可 | 描述 你创造了一支酸液箭... |\n"
        "\n"
        "**酸雾术 (Acid Fog)**\n"
        "| 学派 咒法系（创造）[酸] | 环位 术士/法师 3, 德鲁伊 3 |\n"
        "| 施法时间 标准动作 | 成分 语言, 姿势, 材料（一点沙子） |\n"
        "| 范围 中距 | 效果 20英尺半径的雾团 | 持续时间 1轮/等级 |\n"
        "| 豁免 无 | 法术抗力 不可 | 描述 你创造了一片酸雾... |\n"
    )


@pytest.fixture
def sample_um_text() -> str:
    """格式变体 B — Bold 标签（类 UM 格式）"""
    return (
        "**酸液喷发 (Acid Spray)**\n"
        "**学派** 咒法系（创造）[酸]\n"
        "**环位** 魔战士 3, 术士/法师 3\n"
        "**施法时间** 标准动作\n"
        "**成分** 语言, 姿势, 材料（一小片枯叶）\n"
        "**范围** 锥形\n"
        "**持续时间** 立即\n"
        "**豁免** 反射, 减半\n"
        "**法术抗力** 不可\n"
        "**描述** 你喷出一道酸液...\n"
    )


@pytest.fixture
def sample_acg_text() -> str:
    """格式变体 C — 冒号标签（类 ACG 格式）"""
    return (
        "**凝胶之血（Gelatinous Blood）**\n"
        "**学派：** 变化系\n"
        "**环位：** 炼金术师 2\n"
        "**施法时间：** 标准动作\n"
        "**成分：** 语言, 姿势\n"
        "**范围：** 个人\n"
        "**目标：** 自己\n"
        "**持续时间：** 1分钟/等级\n"
        "**豁免：** 意志, 无效（无害）\n"
        "**法术抗力：** 可（无害）\n"
        "**描述：** 你的血液变得黏稠...\n"
    )


@pytest.fixture
def sample_aonprd_text() -> str:
    """格式变体 D — AONPRD（冒险之路）"""
    return (
        "**流血打击**（[Bleeding Strike](http://aonprd.com/...)）\n"
        "**学派：** 变化系\n"
        "**环位：** 审判者 2\n"
        "**施法时间：** 标准动作\n"
        "**成分：** 语言, 姿势\n"
        "**范围：** 接触\n"
        "**目标：** 接触的生物\n"
        "**持续时间：** 立即\n"
        "**豁免：** 强韧, 无效\n"
        "**法术抗力：** 可\n"
        "**描述：** 你的手发出红光...\n"
        "来源：正义之怒冒险之路\n"
    )


@pytest.fixture
def sample_compact_text() -> str:
    """格式变体 E — 紧凑内联（玩家伴侣）"""
    return (
        "**古神之臂（Arm of the Ancients）**\n"
        "学派：变化系；环位：术士/法师 2；施法时间：标准动作；"
        "成分：语言，姿势；范围：个人；目标：自己；"
        "持续时间：1分钟/等级\n"
        "描述：你的手臂覆盖上古老的力量...\n"
    )


@pytest.fixture
def sample_mtt_text() -> str:
    """格式变体 F — 换行无冒号（MTT）"""
    return (
        "## 战术突破（Tactical Breach）\n"
        "学派 咒法系\n"
        "环位 术士/法师 4\n"
        "施法时间 标准动作\n"
        "成分 语言, 姿势\n"
        "范围 中距\n"
        "持续时间 立即\n"
        "豁免 无\n"
        "法术抗力 不可\n"
        "描述 你打开一道传送门...\n"
    )


@pytest.fixture
def sample_prose_text() -> str:
    """格式变体 G — 文章体（神话法术）"""
    return (
        "## 神话法术\n"
        "神话法术是经过强化的普通法术...\n"
        "\n"
        "### 神话强酸箭 (Mythic Acid Arrow)\n"
        "你射出的酸液箭矢将造成更强的伤害...\n"
        "\n"
        "### 神话活化绳 (Mythic Animate Rope)\n"
        "你的活化绳持续时间更长...\n"
    )


@pytest.fixture
def sample_false_positive_cases() -> str:
    """A 类误提升用例"""
    return (
        "**UM**  这条不用翻\n"
        "**极限魔法** (Ultimate Magic)\n"
        "\n"
        "**引言** (Introduction)\n"
        "\n"
        "**A**\n"
        "\n"
        "**强酸箭 (Acid Arrow)**\n"
        "**学派** 咒法系（创造）[酸]\n"
        "**环位** 魔战士 2, 术士/法师 2\n"
        "**描述** 你创造一支酸液箭...\n"
    )


# ===== Source相关 fixtures =====

@pytest.fixture
def source_resolver() -> SourceResolver:
    return SourceResolver(ALL_PROVIDERS)


@pytest.fixture
def source_context_spell_crb() -> SourceContext:
    """Spell CRB.md 的 SourceContext"""
    return SourceContext(
        file_path="/path/to/pf_rules_md_organized/法术/Spell CRB.md",
        file_content="**强酸箭 (Acid Arrow)**\n",
        html_markers=[],
        directory_hints=["法术", "Spell CRB.md"],
    )


# ===== 新格式变体 fixtures =====

@pytest.fixture
def sample_school_bracket_text() -> str:
    """【学派】格式（Cluster 5a 标准）"""
    return (
        "【咒法系】(创造)强酸箭(Acid Arrow)[酸]\n"
        "**等级**：魔战士 2、术士/法师 2\n"
        "**施法时间**：标准动作\n"
        "**描述**：你创造了一支酸液箭。\n"
        "\n"
        "【变化系】高等蛇龙术(Form of the Dragon III)[龙类]\n"
        "**等级**：术士/法师 7\n"
        "**施法时间**：标准动作\n"
        "**描述**：你化身为龙。\n"
    )


@pytest.fixture
def sample_oa_inline_text() -> str:
    """OA/UI 全内联格式（Cluster 4a）"""
    return (
        "**阿卡西构形（Akashic Form）****学派**：变化系"
        "**等级**：炼金术师 6、术士/法师 6"
        "**施法时间**：标准动作"
        "**成分**：语言、姿势"
        "**范围**：个人"
        "**目标**：自己"
        "**持续时间**：1分钟/等级"
        "**法术抗力**：不可"
        "**描述**：你从阿卡西记录中汲取知识。\n"
        "\n"
        "**梦境旅行（Dream Travel）****学派**：咒法系"
        "**等级**：术士/法师 7"
        "**施法时间**：标准动作"
        "**描述**：你进入梦境位面。\n"
    )


@pytest.fixture
def sample_unified_school_text() -> str:
    """【学派】格式（单行压缩，Cluster 7 变体）"""
    return (
        "【防护系】抵抗能量伤害(Resist Energy)\n"
        "**等级**：牧师 2、德鲁伊 2\n"
        "**施法时间**：标准动作\n"
        "\n"
        "【预言系】克敌机先(True Strike)\n"
        "等级：炼金术师 1\n"
        "施法时间：标准动作\n"
    )


@pytest.fixture
def sample_group_header_text() -> str:
    """含分组标题的需要过滤的文本"""
    return (
        "**强酸箭 (Acid Arrow)**\n"
        "**学派：** 咒法系\n"
        "**等级：** 魔战士 2\n"
        "\n"
        "**伽瑟兰法术（GATHLAIN SPELLS）**\n"
        "以下为伽瑟兰文明的法术。\n"
        "\n"
        "**原初本能 (Alpha Instinct)**\n"
        "**学派：** 变化系\n"
        "**等级：** 德鲁伊 7\n"
    )


@pytest.fixture
def sample_noise_text() -> str:
    """含各种噪声标记的文本"""
    return (
        "**强酸箭 (Acid Arrow)**\n"
        "**学派：** 咒法系\n"
        "**等级：** 魔战士 2\n"
        "**描述：** 你创造了一支酸液箭。\n"
        "\n"
        "**隆地术 (Groundswell) [矮人]**\n"
        "**学派：** 变化系\n"
        "**等级：** 德鲁伊 2\n"
        "**描述：** 大地隆起。\n"
        "\n"
        "◎ 以下为译者注\n"
        "![[图片001.png]]\n"
        "整理者：草野\n"
        "\n"
        "~~**衰老抗性 (Age Resistance)**~~\n"
        "**学派：** 变化系\n"
        "**等级：** 术士/法师 2\n"
    )


@pytest.fixture
def sample_unlabeled_field_text() -> str:
    """无加粗字段但带冒号的格式（Cluster 6 变体）"""
    return (
        "**防生物力场 (Antilife Shell)**\n"
        "学派：防护系\n"
        "等级：牧师 6、德鲁伊 6\n"
        "施法时间：标准动作\n"
        "范围：个人\n"
        "目标：自己\n"
        "持续时间：1分钟/等级\n"
        "豁免：无\n"
        "法术抗力：可\n"
        "描述：你被力场包围。\n"
    )
