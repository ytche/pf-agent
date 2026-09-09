import json
import re
import random
from pathlib import Path


def normalize_text(text):
    """移除 HTML 标签、Markdown 符号和空白，用于粗略比较"""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[#*_`\[\]|]', '', text)
    text = re.sub(r'\s+', '', text)
    text = text.replace('&nbsp;', ' ')
    text = text.replace(' ', '')
    return text


def read_html_text(path):
    raw = path.read_bytes()
    for enc in ['gbk', 'utf-8', 'gb2312', 'gb18030', 'latin-1']:
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode('latin-1', errors='ignore')


def char_jaccard(a, b):
    set_a = set(a)
    set_b = set(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def main():
    mapping = json.load(open('pf_data/file_mapping.json', encoding='utf-8'))
    md_to_html = mapping['md_to_html']

    html_dir = Path('pf_data/source_chm')
    md_dir = Path('pf_data/phase1/pf_rules_md')

    # 抽样 20 个验证
    sample = random.sample(list(md_to_html.items()), 20)

    low_sim = []
    for md_name, html_name in sample:
        md_path = md_dir / md_name
        html_path = html_dir / html_name

        md_text = normalize_text(md_path.read_text(encoding='utf-8', errors='ignore'))[:500]
        html_text = normalize_text(read_html_text(html_path))[:500]

        sim = char_jaccard(md_text, html_text)
        if sim < 0.3:
            low_sim.append((md_name, html_name, sim))

    print(f"抽样验证 20 个文件")
    print(f"低相似度（<0.3）数量: {len(low_sim)}")
    for md_name, html_name, sim in low_sim:
        print(f"  {md_name} <-> {html_name}: {sim:.2f}")

    # 也验证那 19 个未匹配的 md 文件
    unmatched = mapping.get('unmatched_md', [])
    print(f"\n未匹配 TOC 的 MD 文件: {len(unmatched)} 个")
    for name in unmatched[:10]:
        print(f"  {name}")


if __name__ == '__main__':
    main()
