# -*- coding: utf-8 -*-
"""M20：page_812 阿斯托莫伊人源数据整理（KN099 局部关闭，2026-08-04）

范围核查结论（audit_chm_scope_gap.py：种族 68/68 无输入缺口）：
- page_812 阿斯托莫伊人 = 合法玩家可选种族条目（ARG 罕见种族），同目录
  怪物种族 其余文件均有 chunk，唯独它因「未整理页格式」（裸两行标题
  `阿斯托莫伊人⏎astomoi这些类人像…` 无加粗标记）产出 0 → **应修复**
- BoS 影生暗生（聚合文件，内容重复）与 page_401~404（构建规则）维持豁免

修复（最小改动，对齐 page_816 舍卜提标题形态）：
1. L7 裸中文标题行 → `**阿斯托莫伊人（****Astomoi****）**`（保留 CRLF）
2. L8 行首英文残片 `astomoi` 删除（英文名已并入标题）
8 个裸文本特性保持并入主条目正文（检索可命中全部内容，粒度拆分另立任务）

执行教训（pf-organized-source-crlf-convention）：二进制读写，行尾原样保留。
用法：python3 m20_fix_astomoai.py（幂等：已修项自动跳过）
"""
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
PATH = BASE / "pf_rules_md_organized" / "种族" / "怪物种族" / "page_812.md"

# (旧串, 新串, 描述)；跨行串适配 CRLF/LF 两种行尾
FIXES: list[tuple[str, str, str]] = [
    ("阿斯托莫伊人 \r\n", "**阿斯托莫伊人（****Astomoi****）**\r\n",
     "L7 裸中文标题 → 标准加粗标题"),
    ("阿斯托莫伊人 \n", "**阿斯托莫伊人（****Astomoi****）**\n",
     "L7 裸中文标题（LF 变体）"),
    ("astomoi这些类人像是由黑暗构成的", "这些类人像是由黑暗构成的",
     "L8 行首英文残片删除"),
]


def main() -> None:
    if not PATH.exists():
        print(f"[缺失] {PATH}")
        return
    data = PATH.read_bytes()
    before_crlf = data.count(b"\r\n")
    applied = 0
    for old, new, desc in FIXES:
        old_b, new_b = old.encode("utf-8"), new.encode("utf-8")
        n = data.count(old_b)
        if n == 0:
            print(f"[跳过/缺失] {desc}")
            continue
        if n > 1:
            print(f"[跳过/重复] {desc}: 出现 {n} 次")
            continue
        data = data.replace(old_b, new_b)
        applied += 1
        print(f"[应用] {desc}")
    PATH.write_bytes(data)
    # 校验
    after_crlf = data.count(b"\r\n")
    title = data.count("**阿斯托莫伊人（****Astomoi****）**".encode("utf-8"))
    res = data.count(b"astomoi")
    print(f"应用 {applied}/{len(FIXES)} 处 | CRLF {before_crlf}→{after_crlf} "
          f"| 标题 {title} 处 | 英文残片残留 {res} 处")
    if applied == 2 and after_crlf == before_crlf and title == 1 and res == 0:
        print("[校验] 全部到位")
    else:
        print("[校验] 需人工复核（CRLF 计数或残留异常）")


if __name__ == "__main__":
    main()
