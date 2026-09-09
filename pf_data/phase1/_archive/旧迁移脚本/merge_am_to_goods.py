#!/usr/bin/env python3
"""
将 AM_物品 和 AM_毒药 内容追加到 货品服务/page_212.md（炼金物质和毒药），并删除源文件。
"""
import re
from pathlib import Path

BASE = Path("/Users/chezi/code/java/pf_agent/pf_data/phase1/pf_rules_md_organized/装备_魔法物品")
PAGE_212 = BASE / "货品服务" / "page_212.md"
AM_ITEMS = BASE / "魔法物品" / "炼金术手册AM_物品.md"
AM_POISONS = BASE / "魔法物品" / "炼金术手册AM_毒药.md"


def read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    has_crlf = b'\r\n' in raw
    return raw.decode('utf-8'), ('\r\n' if has_crlf else '\n')


def write_text(path: Path, content: str) -> None:
    raw = content.encode('utf-8')
    path.write_bytes(raw)


def strip_title_header(text: str) -> tuple[str, str]:
    """
    提取 '# 炼金术手册AM 物品' 或 '# 炼金术手册AM 毒药与毒品' 标题，返回 (title, body)。
    跳过源文件的标题，但保留其下所有内容。
    """
    lines = text.split('\n')
    # 跳过开头的空行和 # 标题
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].strip().startswith('# '):
        title = lines[i].strip()
        i += 1
        # 跳过标题后的空行
        while i < len(lines) and not lines[i].strip():
            i += 1
    else:
        title = ''
    return title, '\n'.join(lines[i:])


def main():
    page_text, page_nl = read_text(PAGE_212)

    am_items_text, _ = read_text(AM_ITEMS)
    am_poisons_text, _ = read_text(AM_POISONS)

    _, am_items_body = strip_title_header(am_items_text)
    _, am_poisons_body = strip_title_header(am_poisons_text)

    # 把 CR/CRLF 都转成 page_212 的换行
    def normalize_to_nl(text: str, target_nl: str) -> str:
        # 先把所有 \r\n 转 \n，再把单独 \r 转 \n
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        if target_nl == '\r\n':
            text = text.replace('\n', '\r\n')
        return text

    am_items_body = normalize_to_nl(am_items_body, page_nl)
    am_poisons_body = normalize_to_nl(am_poisons_body, page_nl)

    # 在追加之前，做最后一遍 source 归一化，确保 page_212 用的是它自己的换行
    items_block = (
        '\n\n---\n\n'
        '## 炼金术手册 AM 特有炼金物品\n\n'
        + am_items_body.strip() + '\n'
    )
    poisons_block = (
        '\n\n---\n\n'
        '## 炼金术手册 AM 特有毒药与毒品\n\n'
        + am_poisons_body.strip() + '\n'
    )

    # 确保 page_212 以换行结尾
    if not page_text.endswith(page_nl):
        page_text += page_nl

    new_page = page_text + items_block + poisons_block

    # 简单校验：'来源：炼金术手册' 应该出现 12（物品 4 处）+ 毒药 12 处 = 24 处
    print(f"page_212 旧长度: {len(page_text)}")
    print(f"page_212 新长度: {len(new_page)}")

    write_text(PAGE_212, new_page)
    print(f"Written {PAGE_212}")

    # 删除源文件
    AM_ITEMS.unlink()
    print(f"Deleted {AM_ITEMS}")
    AM_POISONS.unlink()
    print(f"Deleted {AM_POISONS}")


if __name__ == '__main__':
    main()
