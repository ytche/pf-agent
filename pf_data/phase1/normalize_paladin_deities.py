#!/usr/bin/env python3
"""V008 Batch C: 归一化圣骑士 deity 页面 page_562.md。

将 **中文名****** 格式替换为 ## 中文名（English）格式，
使每个 deity 条目被 classify_component 正确识别为 class_feature 而非 overview。
"""
import re

PATH = "pf_rules_md_organized/职业/核心职业/圣骑士/page_562.md"

# 6 个核心 deity 的映射
DEITY_MAP = {
    "埃拉斯蒂尔": "Erastil",
    "艾奥梅黛": "Iomedae",
    "沙伦莱": "Sarenrae",
    "纱琳": "Shelyn",
    "托拉格": "Torag",
    "阿巴达尔": "Abadar",
}

# 额外 deity（在文件后半部分）
EXTRA_DEITIES = {
    "艾瑟塔": "Alseta",
    "阿普苏": "Apsu",
}

ALL_DEITIES = {**DEITY_MAP, **EXTRA_DEITIES}


def main():
    with open(PATH, encoding="utf-8") as f:
        text = f.read()

    changed = 0
    for cn, en in ALL_DEITIES.items():
        # 匹配 **中文名****** 或 **中文名** 等变体
        old = f"**{cn}******"
        new = f"## {cn}（{en}）"
        if old in text:
            text = text.replace(old, new)
            changed += 1
        else:
            # 尝试其他变体
            for pattern in [f"**{cn}**", f"**{cn}**\n**"]:
                if pattern in text:
                    text = text.replace(pattern, new)
                    changed += 1
                    break

    with open(PATH, encoding="utf-8", newline="\n") as f:
        f.write(text)

    print(f"page_562.md: {changed} 处替换")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
