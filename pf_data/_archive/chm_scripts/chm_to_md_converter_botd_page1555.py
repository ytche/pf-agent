#!/usr/bin/env python3
"""
Pathfinder CHM HTML -> Markdown 转换器（BOTD page_1555 专用版）
用途：重新处理 page_1555.html，修复加粗标题跨行问题
"""

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

# ==================== 配置 ====================
SRC_HTML = Path(os.path.expanduser("~/.openclaw/workspace/pf_rules/page_1555.html"))
DST_MD = Path(os.path.expanduser("/Users/chezi/code/java/pf_agent/pf_data/phase1/page_1555_redone.md"))

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
        # 匹配两种格式：
        # 1. 有页面链接: - 标题 (`page.html`)
        # 2. 无页面链接: - 标题
        match = re.match(r'^(\s*)- \s*(.+?)\s*(?:\(`([^`]+)`\))?\s*$', line)
        if not match:
            continue
        indent = len(match.group(1))
        title = match.group(2).strip()
        filename = match.group(3).strip() if match.group(3) else ""
        level = indent // 2 + 1
        items.append({
            'level': level,
            'title': title,
            'filename': unquote(filename) if filename else "",
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
            # 先合并段落内残留换行（来自 span 内原生换行）
            text = re.sub(r'(?<=[^\r\n])\r?\n(?=[^\r\n])', ' ', text)
            text = re.sub(r'\r', '', text)
            # 合并连续半角/全角空格
            text = re.sub(r'[ 　]{2,}', ' ', text)
            # 条目标题后换行，风味描述单独一行
            text = re.sub(r'\*\*([^*]+?（[^）]+?）)\*\*[\s　]+(\*\*\*[^*]+?\*\*\*)', r'**\1**\n\2', text)
            # 先决条件/专长效果字段前后添加段落分隔
            text = re.sub(r'\s*\*\*先决条件：\*\*', '\n\n**先决条件：**\n\n', text)
            text = re.sub(r'\s*\*\*专长效果：\*\*', '\n\n**专长效果：**\n\n', text)
            return text + '\n\n'
        return '\n'

    body = re.sub(r'<p[^>]*>(.*?)</p>', p_repl, body, flags=re.DOTALL | re.IGNORECASE)

    # 处理 div
    def div_repl(m):
        text = inline_process(m.group(1), base_filename).strip()
        if text:
            text = re.sub(r'(?<=[^\r\n])\r?\n(?=[^\r\n])', ' ', text)
            text = re.sub(r'\r', '', text)
            text = re.sub(r'[ 　]{2,}', ' ', text)
            text = re.sub(r'\*\*([^*]+?（[^）]+?）)\*\*[\s　]+(\*\*\*[^*]+?\*\*\*)', r'**\1**\n\2', text)
            text = re.sub(r'\s*\*\*先决条件：\*\*', '\n\n**先决条件：**\n\n', text)
            text = re.sub(r'\s*\*\*专长效果：\*\*', '\n\n**专长效果：**\n\n', text)
            return text + '\n\n'
        return '\n'

    # 处理 br（本页已在 inline_process 中处理，此处做最终兜底）
    body = re.sub(r'(?:<br\b[^>]*>\s*){2,}', '\n\n', body, flags=re.IGNORECASE)
    body = re.sub(r'<br\b[^>]*>', ' ', body, flags=re.IGNORECASE)
    body = re.sub(r'<hr\b[^>]*>', '\n---\n\n', body, flags=re.IGNORECASE)

    # 清理剩余标签
    body = strip_html_tags(body)

    # 清理空行
    body = re.sub(r'\r\n?', '\n', body)
    body = re.sub(r'\n{3,}', '\n\n', body)
    body = re.sub(r'[ \t]+\n', '\n', body)
    # 合并多个空格（含全角空格）为单个半角空格
    body = re.sub(r'[ 　]+', ' ', body)
    body = re.sub(r'\n{3,}', '\n\n', body)

    return body.strip()


def inline_process(html, base_filename=''):
    """处理行内格式：链接、加粗、斜体、图片等"""
    import re

    # 处理 <br>：连续 BR 视为段落分隔，单个 BR 视为行内空格（合并英文跨行）
    html = re.sub(r'(?:<br\b[^>]*>\s*){2,}', '\n\n', html, flags=re.IGNORECASE)
    html = re.sub(r'<br\b[^>]*>', ' ', html, flags=re.IGNORECASE)

    # 图片 -> Markdown 图片
    def img_repl(m):
        src = m.group(1) or ''
        alt = '[图片]'
        return f'![{alt}]({src})'
    html = re.sub(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', img_repl, html, flags=re.IGNORECASE)

    # span, font - 本页仅作为样式包装，直接去掉标签保留内容
    html = re.sub(r'<(span|font)\b[^>]*>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'</(span|font)>', '', html, flags=re.IGNORECASE)

    # 加粗：合并标签内换行与多余空白，避免标题跨行
    def bold_repl(m):
        text = re.sub(r'\s+', ' ', m.group(2)).strip()
        return f'**{text}**'
    html = re.sub(r'<(b|strong)[^>]*>(.*?)</\1>', bold_repl, html, flags=re.DOTALL | re.IGNORECASE)
    # 斜体：同样合并标签内换行与多余空白
    def italic_repl(m):
        text = re.sub(r'\s+', ' ', m.group(2)).strip()
        return f'*{text}*'
    html = re.sub(r'<(i|em)[^>]*>(.*?)</\1>', italic_repl, html, flags=re.DOTALL | re.IGNORECASE)
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
    if not SRC_HTML.exists():
        print(f"源文件不存在: {SRC_HTML}")
        sys.exit(1)

    print("=" * 60)
    print("BOTD page_1555 专用 HTML -> Markdown 转换")
    print("=" * 60)
    print(f"源文件: {SRC_HTML}")
    print(f"输出文件: {DST_MD}")
    print()

    DST_MD.parent.mkdir(parents=True, exist_ok=True)
    success = convert_file(SRC_HTML, DST_MD, SRC_HTML.name)

    if success:
        print(f"转换成功: {DST_MD}")
    else:
        print(f"转换失败")
        if stats["errors"]:
            print(f"错误: {stats['errors'][0]}")
        sys.exit(1)


if __name__ == '__main__':
    main()
