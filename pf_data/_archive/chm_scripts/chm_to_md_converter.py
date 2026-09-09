#!/usr/bin/env python3
"""
Pathfinder CHM HTML -> Markdown 转换器
====================================
将 pf_rules_chm/ 中的 HTML 文件按 CHM_FULL_TOC.md 的目录结构转换为 Markdown。

用法（在主机上执行）：
    python3 chm_to_md_converter.py

要求：
    - Python 3.6+
    - 源目录 ~/.openclaw/workspace/pf_rules_chm/ 存在
"""

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

# ==================== 配置 ====================
SRC_DIR = Path(os.path.expanduser("~/.openclaw/workspace/pf_rules_chm"))
DST_DIR = Path(os.path.expanduser("~/.openclaw/workspace/pf_rules_md"))
TOC_FILE = Path(os.path.expanduser("~/.openclaw/workspace/touniang/CHM_FULL_TOC.md"))

# 统计数据
stats = {"success": 0, "failed": 0, "skipped": 0, "errors": []}


def parse_toc(filepath):
    """解析 CHM_FULL_TOC.md，返回目录条目列表"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    items = []
    lines = content.split('\n')
    for line in lines:
        line = line.rstrip()
        match = re.match(r'^(\s*)- \s*(.+?)\s+\(([^)]+)\)\s*$', line)
        if not match:
            continue
        indent = len(match.group(1))
        title = match.group(2).strip()
        filename = match.group(3).strip()
        level = indent // 2 + 1
        items.append({
            'level': level,
            'title': title,
            'filename': unquote(filename),
        })
    return items


def resolve_folder_structure(items):
    """根据 TOC 层级确定每个文件应放入的文件夹"""
    for i, item in enumerate(items):
        has_children = False
        if i + 1 < len(items) and items[i + 1]['level'] > item['level']:
            has_children = True
        item['is_folder'] = has_children

    folder_stack = []
    for item in items:
        level = item['level']
        while len(folder_stack) >= level:
            folder_stack.pop()
        if item['is_folder']:
            folder_name = sanitize_filename(item['title'])
            folder_stack.append(folder_name)
            item['output_path'] = None
        else:
            item['output_path'] = '/'.join(folder_stack) if folder_stack else ''
    return items


def sanitize_filename(name):
    """清理文件名中的非法字符"""
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    return name.strip() or 'untitled'


def read_html_file(filepath):
    """读取 HTML 文件，自动处理 GBK/UTF-8 编码"""
    with open(filepath, 'rb') as f:
        raw = f.read()
    for enc in ['gbk', 'utf-8', 'gb2312', 'gb18030', 'latin-1']:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            pass
    return raw.decode('latin-1')


def html_to_markdown(html_content, base_filename=''):
    """将 HTML 内容转换为 Markdown（使用正则和简单解析）"""
    import re

    # 移除 script, style, noscript
    html_content = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', '', html_content, flags=re.DOTALL | re.IGNORECASE)

    # 提取 body 内容
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html_content, re.DOTALL | re.IGNORECASE)
    body = body_match.group(1) if body_match else html_content

    md_lines = []

    # 处理标题
    def heading_repl(m):
        level = m.group(1)
        text = m.group(2).strip()
        return f"{'#' * int(level)} {text}\n\n"
    body = re.sub(r'<h([1-6])[^>]*>(.*?)</h\1>', heading_repl, body, flags=re.DOTALL | re.IGNORECASE)

    # 处理表格
    def table_repl(m):
        table_html = m.group(1)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
        if not rows:
            return ''
        md_rows = []
        for i, row in enumerate(rows):
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL | re.IGNORECASE)
            if not cells:
                continue
            # 清理单元格内容
            cleaned = []
            for cell in cells:
                cell_text = strip_html_tags(cell).strip()
                cell_text = cell_text.replace('|', '\\|').replace('\n', ' ')
                cleaned.append(cell_text)
            md_rows.append('| ' + ' | '.join(cleaned) + ' |')
            if i == 0:
                md_rows.append('|' + '|'.join([' --- ' for _ in cleaned]) + '|')
        return '\n'.join(md_rows) + '\n\n'

    body = re.sub(r'<table[^>]*>(.*?)</table>', table_repl, body, flags=re.DOTALL | re.IGNORECASE)

    # 处理列表
    def ul_repl(m):
        items = re.findall(r'<li[^>]*>(.*?)</li>', m.group(1), re.DOTALL | re.IGNORECASE)
        lines = []
        for item in items:
            text = inline_process(item, base_filename).strip()
            lines.append(f'- {text}')
        return '\n'.join(lines) + '\n\n'

    def ol_repl(m):
        items = re.findall(r'<li[^>]*>(.*?)</li>', m.group(1), re.DOTALL | re.IGNORECASE)
        lines = []
        for i, item in enumerate(items, 1):
            text = inline_process(item, base_filename).strip()
            lines.append(f'{i}. {text}')
        return '\n'.join(lines) + '\n\n'

    body = re.sub(r'<ul[^>]*>(.*?)</ul>', ul_repl, body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r'<ol[^>]*>(.*?)</ol>', ol_repl, body, flags=re.DOTALL | re.IGNORECASE)

    # 处理段落和通用块
    def p_repl(m):
        text = inline_process(m.group(1), base_filename).strip()
        if text:
            return text + '\n\n'
        return '\n'

    body = re.sub(r'<p[^>]*>(.*?)</p>', p_repl, body, flags=re.DOTALL | re.IGNORECASE)

    # 处理 div
    def div_repl(m):
        text = inline_process(m.group(1), base_filename).strip()
        return text + '\n\n' if text else '\n'
    body = re.sub(r'<div[^>]*>(.*?)</div>', div_repl, body, flags=re.DOTALL | re.IGNORECASE)

    # 处理 br
    body = re.sub(r'<br\s*/?>', '\n', body, flags=re.IGNORECASE)
    body = re.sub(r'<hr\s*/?>', '\n---\n\n', body, flags=re.IGNORECASE)

    # 清理剩余标签
    body = strip_html_tags(body)

    # 清理空行
    body = re.sub(r'\n{3,}', '\n\n', body)
    body = re.sub(r'[ \t]+\n', '\n', body)

    return body.strip()


def inline_process(html, base_filename=''):
    """处理行内格式：链接、加粗、斜体、图片等"""
    import re

    # 图片 -> Markdown 图片
    def img_repl(m):
        src = m.group(1) or ''
        alt = '[图片]'
        return f'![{alt}]({src})'
    html = re.sub(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', img_repl, html, flags=re.IGNORECASE)

    # 加粗
    html = re.sub(r'<(b|strong)[^>]*>(.*?)</\1>', r'**\2**', html, flags=re.DOTALL | re.IGNORECASE)
    # 斜体
    html = re.sub(r'<(i|em)[^>]*>(.*?)</\1>', r'*\2*', html, flags=re.DOTALL | re.IGNORECASE)
    # 下划线
    html = re.sub(r'<u[^>]*>(.*?)</u>', r'\1', html, flags=re.DOTALL | re.IGNORECASE)
    # 删除线
    html = re.sub(r'<s(trike)?[^>]*>(.*?)</s\1?>', r'~~\2~~', html, flags=re.DOTALL | re.IGNORECASE)
    # 上标/下标
    html = re.sub(r'<sup[^>]*>(.*?)</sup>', r'\1', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<sub[^>]*>(.*?)</sub>', r'\1', html, flags=re.DOTALL | re.IGNORECASE)
    # 代码
    html = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<tt[^>]*>(.*?)</tt>', r'`\1`', html, flags=re.DOTALL | re.IGNORECASE)

    # 链接
    def a_repl(m):
        href = m.group(1) or ''
        text = m.group(2).strip() or m.group(2)
        href = unquote(href)
        if href.startswith('javascript:') or href == '#':
            return text
        if href.startswith(('http://', 'https://')):
            return f'[{text}]({href})'
        if href.endswith(('.html', '.htm')):
            md_href = href.rsplit('.', 1)[0] + '.md'
            return f'[{text}]({md_href})'
        return f'[{text}]({href})'
    html = re.sub(r'<a[^>]+href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', a_repl, html, flags=re.DOTALL | re.IGNORECASE)

    # span, font - 去掉标签保留内容
    html = re.sub(r'<(span|font)[^>]*>(.*?)</\1>', r'\2', html, flags=re.DOTALL | re.IGNORECASE)
    # 小标签
    html = re.sub(r'<(small|big)[^>]*>(.*?)</\1>', r'\2', html, flags=re.DOTALL | re.IGNORECASE)

    return html


def strip_html_tags(html):
    """移除剩余的 HTML 标签，保留文本"""
    import re
    # 先处理特殊字符实体
    html = html.replace('&nbsp;', ' ')
    html = html.replace('&lt;', '<')
    html = html.replace('&gt;', '>')
    html = html.replace('&amp;', '&')
    html = html.replace('&quot;', '"')
    html = html.replace('&mdash;', '—')
    html = html.replace('&ndash;', '–')
    html = html.replace('&hellip;', '…')
    html = html.replace('&bull;', '•')
    # 通用实体
    html = re.sub(r'&#[xX]?([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16 if m.group(1).lower().startswith('x') or 'a' <= m.group(1)[0].lower() <= 'f' else 10)), html)
    html = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), html)
    # 移除所有标签
    html = re.sub(r'<[^>]+>', '', html)
    return html


def convert_file(src_path, dst_path, filename):
    """转换单个 HTML 文件为 Markdown"""
    try:
        html_content = read_html_file(src_path)
        md_content = html_to_markdown(html_content, filename)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dst_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        stats["success"] += 1
        return True
    except Exception as e:
        stats["failed"] += 1
        stats["errors"].append(f"{filename}: {str(e)}")
        return False


def main():
    if not SRC_DIR.exists():
        print(f"源目录不存在: {SRC_DIR}")
        print("请确认 CHM 文件已解压到该目录。")
        sys.exit(1)
    if not TOC_FILE.exists():
        print(f"TOC 文件不存在: {TOC_FILE}")
        sys.exit(1)

    print("=" * 60)
    print("Pathfinder CHM HTML -> Markdown 转换器")
    print("=" * 60)
    print(f"源目录: {SRC_DIR}")
    print(f"输出目录: {DST_DIR}")
    print(f"TOC 文件: {TOC_FILE}")
    print()

    # 解析 TOC
    print("解析目录结构...")
    items = parse_toc(TOC_FILE)
    items = resolve_folder_structure(items)
    print(f"   找到 {len(items)} 个 TOC 条目")

    DST_DIR.mkdir(parents=True, exist_ok=True)

    # 扫描源文件
    print("扫描源文件...")
    src_files = {}
    for f in SRC_DIR.rglob('*.html'):
        src_files[f.name] = f
    for f in SRC_DIR.rglob('*.htm'):
        src_files[f.name] = f
    print(f"   找到 {len(src_files)} 个 HTML 文件")
    print()

    # 先处理示例文件
    sample_filename = 'page_300.html'
    if sample_filename in src_files:
        print(f"处理示例文件: {sample_filename}")
        sample_item = next((i for i in items if i['filename'] == sample_filename), None)
        if sample_item and sample_item.get('output_path') is not None:
            out_path = DST_DIR / sample_item['output_path'] / f"{sample_filename.rsplit('.', 1)[0]}.md"
        else:
            out_path = DST_DIR / f"{sample_filename.rsplit('.', 1)[0]}.md"
        success = convert_file(src_files[sample_filename], out_path, sample_filename)
        if success:
            print(f"   示例文件已输出: {out_path}")
            with open(out_path, 'r', encoding='utf-8') as f:
                preview = '\n'.join(f.read().split('\n')[:50])
            print(f"\n示例文件预览（前50行）:\n{'='*60}")
            print(preview)
            print(f"{'='*60}\n")
        else:
            print(f"   示例文件转换失败")
        print()

    # 批量处理 TOC 中的文件
    print("开始批量转换...")
    for item in items:
        filename = item['filename']
        if filename not in src_files:
            stats["skipped"] += 1
            continue
        if item.get('is_folder'):
            stats["skipped"] += 1
            continue
        out_rel = item.get('output_path', '')
        out_path = DST_DIR / out_rel / f"{filename.rsplit('.', 1)[0]}.md"
        convert_file(src_files[filename], out_path, filename)

    # 处理未在 TOC 中的文件
    print("处理未在 TOC 中的文件...")
    toc_filenames = {i['filename'] for i in items}
    for filename, src_path in src_files.items():
        if filename in toc_filenames:
            continue
        out_path = DST_DIR / f"{filename.rsplit('.', 1)[0]}.md"
        convert_file(src_path, out_path, filename)

    # 统计报告
    print()
    print("=" * 60)
    print("转换统计")
    print("=" * 60)
    print(f"成功: {stats['success']}")
    print(f"失败: {stats['failed']}")
    print(f"跳过: {stats['skipped']}")
    if stats['errors']:
        print(f"\n错误详情（前10条）:")
        for err in stats['errors'][:10]:
            print(f"   - {err}")

    total_size = 0
    total_files = 0
    for f in DST_DIR.rglob('*'):
        if f.is_file():
            total_size += f.stat().st_size
            total_files += 1

    print(f"\n输出目录: {DST_DIR}")
    print(f"   文件数: {total_files}")
    print(f"   总大小: {total_size / 1024 / 1024:.2f} MB")
    print("\n转换完成!")


if __name__ == '__main__':
    main()
