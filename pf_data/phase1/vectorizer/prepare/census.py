"""census.py — Prepare 三闸口 ① T6.3 raw_example 逐字普查（v2.2 决策 G 参数化迁移）

源自 docs/专长/t63_census_audit.py（k3 审计用，只读）。路径参数化：
--merged <per_file.jsonl> / --source <源数据根目录>，默认值兼容专长历史行为。
firstlast / phantom 均 import 本模块复用纯函数（骨架通用，类目无关）。

口径：
- 元素 = per_file.jsonl 每份报告里每个 title_forms[i].raw_example
- raw_example 先按 \\n 切段，每段剥掉行号前缀 `L311:` / `L14~301：` / `L99-100:` 等
- 每段分别与源文件全文比对：
    exact      原样是源文子串
    whitespace 去全部空白（含 \\r \\n 空格 tab）后是子串
    lb_marker  段内含 [LB] 换行标注，去掉标注（或还原为换行）后匹配
    phantom    以上都不匹配（疑似伪造/错行/改写）
- 行号口径：open(newline='') + re.split(r'\\r\\n|\\r|\\n') 的逻辑行（与 page_203 争议裁决一致）

用法：python3 -m vectorizer.prepare.census [--merged ...] [--source ...] [--verbose]
退出码：0 = 无 phantom；1 = 有 phantom
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_MERGED = Path(__file__).parent.parent / "exploration" / "专长" / "专长_per_file.jsonl"
DEFAULT_SOURCE = Path(__file__).parent.parent.parent / "pf_rules_md_organized"

L_PREFIX = re.compile(r"^L\d+(?:[-~～/]L?\d+)*[:：]?\s*")
WS = re.compile(r"\s+")
ELIDE = re.compile(r"\.{3,}|…+")
# 全/半角与异体括号互换（仅审计归一化用，不修改任何数据）
PUNCT_MAP = str.maketrans({
    "（": "(", "）": ")", "，": ",", "：": ":", "；": ";",
    "［": "[", "］": "]", "【": "[", "】": "]",
    "〔": "[", "〕": "]", "〖": "[", "〗": "]",
    "｜": "|", "＊": "*",
})

IMG = re.compile(r"!\[\[[^\]]*\]\](?:\([^)]*\))?")


def norm(s):
    return WS.sub("", s)


def norm_p(s):
    return norm(s).translate(PUNCT_MAP)


def norm_img(s):
    """去掉图片标记（含可选 URL）后再归一"""
    return norm_p(IMG.sub("", s))


def load_source(rel, src_root):
    """读源文件全文（newline='' 保留原始换行，逻辑行口径与判别器一致）。
    file 字段两种口径并存：相对源根 / 带源根前缀"""
    rel = rel.removeprefix(os.path.basename(str(src_root)) + "/")
    p = os.path.join(src_root, rel)
    if not os.path.exists(p):
        return None
    with open(p, newline="", encoding="utf-8") as f:
        return f.read()


def elided_match(seg, cmp_src):
    """段内含 .../…… 省略号：非省略片段须按序出现于源文（单片段=前缀截断也算）"""
    frags = [f for f in ELIDE.split(seg) if f]
    if not frags:
        return False
    pos = 0
    for f in frags:
        i = cmp_src.find(f, pos)
        if i < 0:
            return False
        pos = i + len(f)
    return True


def classify_segment(seg, ctx):
    """返回 category；ctx = (src, src_norm, src_np, src_nimg)"""
    if not seg.strip():
        return "empty"
    # 纯标注段（非专长标题：无 ** 无英文，括号包裹的说明文字），如 （跨行续）（注：表格84行）
    if (re.fullmatch(r"[（(][^*A-Za-z]{1,24}[)）]", seg.strip())
            and re.search(r"跨行|下同|续|略|注|表格|索引", seg)):
        return "annotation"
    src, src_norm, src_np, src_nimg = ctx
    if seg in src:
        return "exact"
    # 换行标注变体：[LB] 或 " / "（勘探方自造标注，还原为换行/删除后比对）
    variants = []
    if "[LB]" in seg:
        variants += [seg.replace("[LB]", "\n"), seg.replace("[LB]", "")]
    if " / " in seg:
        variants += [seg.replace(" / ", "\n"), seg.replace(" / ", "")]
    for v in variants:
        if v in src or norm(v) in src_norm:
            return "lb_marker"
    if norm(seg) in src_norm:
        return "whitespace"
    if norm_p(seg) in src_np:
        return "punct"
    if IMG.search(seg) and norm_img(seg) in src_nimg:
        return "img_marker"
    if ELIDE.search(seg) and elided_match(norm_img(seg), src_nimg):
        return "elided"
    return "phantom"


def classify_element(raw, ctx):
    if isinstance(raw, list):
        parts = [str(x) for x in raw]
    else:
        # 同时按真实换行与字面 '\n' 两字符序列切段
        parts = str(raw).replace("\\n", "\n").split("\n")
    segs = [L_PREFIX.sub("", s) for s in parts]
    order = ["phantom", "elided", "img_marker", "lb_marker", "punct", "whitespace", "annotation", "exact", "empty"]
    worst = "exact"
    details = []
    for s in segs:
        cat = classify_segment(s, ctx)
        details.append((cat, s))
        if order.index(cat) < order.index(worst):
            worst = cat
    # 跨行标题被切成多段且单段都不中：拼接整段再试一次
    if worst == "phantom" and len(segs) > 1:
        joined = "".join(segs)
        j = classify_segment(joined, ctx)
        if j != "phantom":
            return j, details
        jn = classify_segment("\n".join(segs), ctx)
        if jn != "phantom":
            return jn, details
    return worst, details


def main(argv=None):
    ap = argparse.ArgumentParser(description="T6.3 raw_example 逐字普查（只读）")
    ap.add_argument("--merged", type=Path, default=DEFAULT_MERGED, help="per_file.jsonl 路径")
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="源数据根目录")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    reports = [json.loads(l) for l in open(args.merged, encoding="utf-8") if l.strip()]
    src_cache = {}
    total = 0
    verdicts = Counter()
    phantom_by_file = defaultdict(list)
    missing_src = []
    for r in reports:
        rel = r["file"]
        if rel not in src_cache:
            src_cache[rel] = load_source(rel, args.source)
        src = src_cache[rel]
        if src is None:
            missing_src.append(rel)
            continue
        ctx = (src, norm(src), norm_p(src), norm_img(src))
        for i, tf in enumerate(r.get("title_forms", [])):
            raw = tf.get("raw_example", "")
            if not raw:
                continue
            total += 1
            v, details = classify_element(raw, ctx)
            verdicts[v] += 1
            if v == "phantom":
                bad = [s for c, s in details if c == "phantom"]
                phantom_by_file[rel].append((i, bad))
            if args.verbose and v not in ("exact",):
                print(f"[{v}] {rel} title_forms[{i}] :: {str(raw)[:90]!r}")
    print("=" * 60)
    print(f"元素总数: {total}")
    for k in ("exact", "whitespace", "punct", "lb_marker", "img_marker", "elided", "annotation", "phantom"):
        print(f"  {k:12s}: {verdicts.get(k, 0)}")
    if missing_src:
        print(f"源文件缺失（未计入）: {len(missing_src)}")
        for m in missing_src:
            print("  -", m)
    if phantom_by_file:
        print(f"\nphantom 分布（{sum(len(v) for v in phantom_by_file.values())} 条 / {len(phantom_by_file)} 文件）:")
        for f, items in sorted(phantom_by_file.items(), key=lambda kv: -len(kv[1])):
            print(f"  {f}: {len(items)} 条")
            for i, bad in items:
                for b in bad:
                    print(f"    title_forms[{i}] :: {b[:100]!r}")
    sys.exit(1 if phantom_by_file else 0)


if __name__ == "__main__":
    main()
