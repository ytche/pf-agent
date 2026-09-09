#!/usr/bin/env python3
"""
从 反派法典VC_专长.md 中摘出非 VC 源（HH、HHH、AM）的专长条目，并分发到对应源书聚合文件。

输出：
- 新建 治疗者手册HH_专长.md
- 追加到 炼金术手册AM_专长.md
- 追加到 闹鬼英雄手册HHH_专长.md
- 从 反派法典VC_专长.md 移除已摘出的条目
"""
import re
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1/pf_rules_md_organized/专长")
VC_FILE = BASE / "反派法典VC_专长.md"
HH_FILE = BASE / "治疗者手册HH_专长.md"
AM_FILE = BASE / "炼金术手册AM_专长.md"
HHH_FILE = BASE / "闹鬼英雄手册HHH_专长.md"


def read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    has_crlf = b'\r\n' in raw
    return raw.decode('utf-8'), ('\r\n' if has_crlf else '\n')


def write_text(path: Path, content: str, nl: str) -> None:
    path.write_bytes(content.encode('utf-8'))


def parse_entries(text: str):
    """
    把文本按 <!-- XX-source:... --> 标记切分，返回 [(marker_text, entry_body_text), ...]
    - marker_text 包含换行
    - entry_body_text 包含从下一行开始到下一个 marker 之前的所有内容
    - 第一个 marker 之前的"前导内容"也作为一个 ('', leading) 项
    """
    pattern = re.compile(r'<!--\s*([A-Z]+)-source:([^\n]*?)\s*-->', re.MULTILINE)
    matches = list(pattern.finditer(text))
    parts = []
    # 前导内容
    if matches:
        leading = text[:matches[0].start()]
        parts.append(('', leading))
    else:
        return [('', text)]

    for i, m in enumerate(matches):
        marker = text[m.start():m.end()]
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        # 把 marker 行也保留到 body 开头
        # 但 marker 的位置是 m.start()，所以 body 是 marker 之后的内容
        # 我们重新组装时把 marker 加回去
        full_block = marker + body
        parts.append((marker, full_block))

    return parts


def classify_marker(marker: str) -> str:
    """返回来源书标识: 'VC' / 'HH' / 'HHH' / 'AM' / ''"""
    m = re.match(r'<!--\s*([A-Z]+)-source:', marker)
    return m.group(1) if m else ''


def main():
    vc_text, vc_nl = read_text(VC_FILE)
    parts = parse_entries(vc_text)

    vc_kept = []  # 保留在 VC_专长 中的块（前导 + VC 条目）
    hh_entries = []
    hhh_entries = []
    am_entries = []

    for marker, body in parts:
        src = classify_marker(marker)
        if not src:
            # 前导内容
            vc_kept.append(body)
        elif src == 'VC':
            vc_kept.append(body)
        elif src == 'HH':
            hh_entries.append(body)
        elif src == 'HHH':
            hhh_entries.append(body)
        elif src == 'AM':
            am_entries.append(body)
        else:
            # 未知，按 VC 处理（保守）
            print(f"WARNING: unknown source {src}, kept in VC")
            vc_kept.append(body)

    print(f"VC kept blocks: {sum(1 for m, _ in parts if classify_marker(m) in ('', 'VC'))}")
    print(f"HH entries extracted: {len(hh_entries)}")
    print(f"HHH entries extracted: {len(hhh_entries)}")
    print(f"AM entries extracted: {len(am_entries)}")

    # 写 VC_专长（移除非 VC 条目）
    new_vc = ''.join(vc_kept)
    write_text(VC_FILE, new_vc, vc_nl)

    # 写 HH_专长（新建）
    if hh_entries:
        hh_text = '# 治疗者手册HH 专长' + vc_nl + vc_nl
        for entry in hh_entries:
            hh_text += entry.rstrip(vc_nl) + vc_nl + vc_nl
        write_text(HH_FILE, hh_text, vc_nl)
        print(f"Created {HH_FILE}")

    # 追加 AM_专长
    if am_entries:
        am_text, am_nl = read_text(AM_FILE)
        # 确保以换行结尾
        if not am_text.endswith(am_nl):
            am_text += am_nl
        for entry in am_entries:
            am_text += am_nl + entry.rstrip(am_nl) + am_nl
        write_text(AM_FILE, am_text, am_nl)
        print(f"Appended to {AM_FILE}")

    # 追加 HHH_专长
    if hhh_entries:
        hhh_text, hhh_nl = read_text(HHH_FILE)
        if not hhh_text.endswith(hhh_nl):
            hhh_text += hhh_nl
        for entry in hhh_entries:
            hhh_text += hhh_nl + entry.rstrip(hhh_nl) + hhh_nl
        write_text(HHH_FILE, hhh_text, hhh_nl)
        print(f"Appended to {HHH_FILE}")


if __name__ == '__main__':
    main()
