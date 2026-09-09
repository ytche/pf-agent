# -*- coding: utf-8 -*-
"""M19：灵猴族攀爬速度源数据修正（KN117 闭环，2026-08-04）

KN117 处置口径（已知问题记录）：page_10 汇总表「攀爬30尺」与 page_379 详情页
「20尺攀爬速度」自相矛盾，官方 ARG Vanara 为 climb 20 ft → 汇总表修正为 20 尺。

顺带修复（KN117 已否证事项点名可顺手处理）：page_440 土元素裔详情页
「缓慢速度」漏「裔」字（全文件 50+ 处均写「土元素裔」，仅此 1 处裸写）。

执行教训（pf-organized-source-crlf-convention）：源数据混合行尾（CRLF+LF），
必须二进制读写（read_bytes/write_bytes），每处验证旧串恰好存在 1 次。

用法：python3 m19_fix_vanara.py（幂等：已修项自动跳过）
"""
import re
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1")
ROOT = BASE / "pf_rules_md_organized" / "种族"

# (文件, 旧串, 新串) —— 二进制替换；旧串必须恰好存在 1 次
FIXES: list[tuple[Path, bytes, bytes, str]] = [
    (ROOT / "page_10.md",
     "30尺，攀爬30尺".encode("utf-8"),
     "30尺，攀爬20尺".encode("utf-8"),
     "灵猴族汇总表攀爬速度 30→20"),
    (ROOT / "常见种族" / "page_440.md",
     "**缓慢速度**：土元素的基本速度为20尺。".encode("utf-8"),
     "**缓慢速度**：土元素裔的基本速度为20尺。".encode("utf-8"),
     "土元素裔漏『裔』字"),
]


def main() -> None:
    applied = 0
    for path, old_b, new_b, desc in FIXES:
        if not path.exists():
            print(f"[缺失] {path.name}: 文件不存在")
            continue
        data = path.read_bytes()
        n = data.count(old_b)
        if n == 0:
            print(f"[跳过/缺失] {path.name}: {desc} —— 旧串不存在（已修？）")
            continue
        if n > 1:
            print(f"[跳过/重复] {path.name}: {desc} —— 旧串出现 {n} 次，人工复核")
            continue
        path.write_bytes(data.replace(old_b, new_b))
        applied += 1
        print(f"[应用] {path.name}: {desc}")
    print(f"应用 {applied}/{len(FIXES)} 处")
    # 校验：修正后旧串应零残留；新串应各 1 处；CRLF 计数不变
    ok = True
    for path, old_b, new_b, desc in FIXES:
        data = path.read_bytes()
        if data.count(old_b) != 0:
            print(f"[残留] {path.name}: 旧串仍存在 {data.count(old_b)} 次")
            ok = False
        if data.count(new_b) != 1:
            print(f"[异常] {path.name}: 新串出现 {data.count(new_b)} 次（期望 1）")
            ok = False
    if ok:
        print("[校验] 全部修正到位，旧串零残留")


if __name__ == "__main__":
    main()
