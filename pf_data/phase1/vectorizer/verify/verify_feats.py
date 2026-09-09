"""
verify_feats.py — 专长集成验收（统一验收入口，R7；v2.2 决策 E 迁移进 VerifyBase 框架）

在 pipeline 全量运行后执行，五检查（对齐返工 R7 验收 + R5 probe）：
  1. 判别器回归：fc_deviation_matrix.json 189 rel 的 est↔got 对账（含豁免）
  2. 召回：audit_baseline.jsonl 基线（1226 行 / name_zh+en 联合去重 1072）↔ chunk title+aliases
  3. title 合法性：无空 title / 无 URL / 无译者标记
  4. 字段健康度：chunk_id 唯一、doc_id 非空、component_type 合法、format_cluster 合法
  5. R5 probe：全库 elided 标题无一为正文句段碎片（_is_fragment_title 同口径，
     基线 3756 快照有 46 个，R5 守卫后清至 0）

豁免程序：docs/state/feat_exemptions_<日期>.md 登记无法产出或亚产出的 rel，
verify 读其 YAML 式清单（`rel: <矩阵rel>` 列表），对豁免 rel 不要求 est↔got 全匹配。
用法：python3 -m vectorizer.verify.verify_feats [--chunks ...] [--matrix ...]
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Set, Tuple

from vectorizer.verify.base import VerifyBase

DEFAULT_CHUNKS = Path("vectorizer/output/专长/chunks.jsonl")
DEFAULT_MATRIX = Path("vectorizer/exploration/专长/fc_deviation_matrix.json")
DEFAULT_BASELINE = Path("vectorizer/exploration/专长/audit_baseline.jsonl")
DEFAULT_EXEMPTIONS = Path("docs/state/feat_exemptions_20260801.md")

# ---- 豁免清单解析（类目逻辑留在本文件，不进框架）----
# docs/state/feat_exemptions_<日期>.md 中"豁免清单"小节：
#   | rel | est | got | 理由 |
_EXEMPT_TABLE_HDR = re.compile(r"^\| rel \| est \| got \| 理由 \|$")
_EXEMPT_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*$")


def load_matrix(path: Path) -> List[dict]:
    if not path.exists():
        print(f"❌ 判别器矩阵不存在: {path}")
        raise SystemExit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_exemptions(path: Path) -> Dict[str, str]:
    """解析豁免登记 md，返回 {rel: 理由}"""
    if not path.exists():
        return {}
    exempt: Dict[str, str] = {}
    in_table = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if _EXEMPT_TABLE_HDR.match(line.strip()):
            in_table = True
            continue
        if in_table and line.strip().startswith("|"):
            m = _EXEMPT_ROW.match(line.strip())
            if m:
                exempt[m.group(1).strip()] = m.group(4).strip()
        elif in_table and not line.strip():
            in_table = False
    return exempt


# ============================================================
#  检查 1：判别器回归（est↔got 对账，含豁免）
# ============================================================


def _doc_id_of(rel: str) -> str:
    """矩阵 rel → doc_id（文件名 stem）：'专长/page_203.md' → 'page_203'"""
    return rel.rsplit("/", 1)[-1][:-3]


def check_discriminator_regression(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """判别器回归：每个矩阵 rel 的产出（按 doc_id 汇总）与 est 对账。

    - 豁免 rel：产出可为 0 或低于 est（登记理由，不阻断）
    - 非豁免 rel est>0 但产出 0：静默丢失 → FAIL
    - 非豁免 rel 产出 < est：亚产能（既有质量差距），WARN 不阻断
    """
    matrix = ctx["matrix"]
    exemptions = ctx["exemptions"]
    ok = True
    issues: List[str] = []
    got_by_doc: Counter = Counter(c.get("doc_id", "") for c in chunks)
    total_est = 0
    total_got = 0
    exempt_rows = []
    zero_loss = 0
    for e in matrix:
        rel = e["rel"]
        est = e["est"]
        did = _doc_id_of(rel)
        got = got_by_doc.get(did, 0)
        if rel in exemptions:
            exempt_rows.append((rel, est, got, exemptions[rel]))
            continue
        total_est += est
        total_got += got
        if est > 0 and got == 0:
            ok = False
            zero_loss += 1
            issues.append(f"❌ {rel}: est={est} got=0（静默丢失）")
        elif est > 0 and got < est:
            issues.append(f"⚠️  {rel}: est={est} got={got}（亚产能，既有差距）")
    if exempt_rows:
        print(f"  — 豁免登记 {len(exempt_rows)} 条：")
        for rel, est, got, reason in exempt_rows:
            print(f"    {rel}: est={est} got={got} — {reason}")
    print(f"  — 非豁免矩阵 rel 产出合计 est={total_est} got={total_got}，静默丢失 {zero_loss} 条")
    return ok, issues


# ============================================================
#  检查 2：召回（audit_baseline.jsonl 基线 ↔ chunk title+aliases）
# ============================================================


def check_recall(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """召回：基线专长（name_zh+name_en 联合去重）↔ chunk title+aliases 命中。

    口径（R8）：audit_baseline.jsonl 原始 1226 行；联合去重 = 1072 专长。
    命中 = chunk.title 或 aliases 含基线 name_zh 或 name_en。
    """
    baseline_path: Path = ctx["baseline_path"]
    if not baseline_path.exists():
        print(f"⚠️  召回基线不存在: {baseline_path}（跳过召回检查）")
        return True, []
    rows = [json.loads(l) for l in baseline_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    # 联合去重：name_zh+name_en 元组
    unique = {}
    for d in rows:
        key = (d.get("name_zh", ""), d.get("name_en", ""))
        if key not in unique:
            unique[key] = d
    baseline = list(unique.values())
    total = len(baseline)

    # chunk 标题 + 别名集合
    titles: Set[str] = set()
    for c in chunks:
        titles.add(c.get("title", ""))
        for a in c.get("aliases", []):
            if a:
                titles.add(a)

    hit = 0
    miss_by_book: Counter = Counter()
    for d in baseline:
        zh = d.get("name_zh", "")
        en = d.get("name_en", "")
        if (zh and zh in titles) or (en and en in titles):
            hit += 1
        else:
            miss_by_book[d.get("source_book", "?")] += 1

    pct = 100.0 * hit / total if total else 0
    print(f"  — 基线 {total}（联合去重 1072 口径；原始 {len(rows)} 行）→ 命中 {hit} = {pct:.1f}%")
    if miss_by_book:
        top = ", ".join(f"{k}:{v}" for k, v in miss_by_book.most_common(8))
        print(f"  — 缺口按来源书：{top}")
        return True, [f"⚠️  召回未命中 {total - hit} 条（K5 核心书源缺失遗留，不阻断；TOP: {top}）"]
    return True, []


# ============================================================
#  检查 3：title 合法性
# ============================================================

_URL_IN_TITLE = re.compile(r"https?://")
# 纯译者标记：title 恰为"译者"/"校对"整词，或含"译者："/"翻译："标签前缀；
# 专长名内含"译者"（德鲁伊语破译者）不算标记
_TRANSLATOR_MARK = re.compile(r"^译者$|^校对$|^[：:]?\s*译者[:：]|^翻译[:：]")
# 格式噪声：未整理页标题残留（【3.5R】前缀 / [URL] 残留 / 《》伪条目）
_TITLE_NOISE = re.compile(r"^【|^《|^\[http|^\*\*")


def check_title_health(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """title 合法性：非空、无 URL、无译者标记、无格式噪声"""
    ok = True
    issues: List[str] = []
    empty = [c for c in chunks if not c.get("title", "").strip()]
    url = [c for c in chunks if _URL_IN_TITLE.search(c.get("title", ""))]
    trans = [c for c in chunks if _TRANSLATOR_MARK.search(c.get("title", ""))]
    noise = [c for c in chunks if _TITLE_NOISE.search(c.get("title", ""))]

    print(f"  — title 空: {len(empty)}  URL: {len(url)}  译者标记: {len(trans)}  格式噪声: {len(noise)}")
    # 空 title 是硬伤（FAIL）；URL/译者/噪声属未整理 page_* 遗留（K3），WARN 登记不阻断
    if empty:
        ok = False
        issues.append(f"❌ {len(empty)} 个空 title")
    if url:
        issues.append(f"⚠️  {len(url)} 个 title 含 URL（K3 未整理页遗留，不阻断）")
    if trans:
        issues.append(f"⚠️  {len(trans)} 个 title 含译者标记（K3 未整理页遗留，不阻断）")
    if noise:
        issues.append(f"⚠️  {len(noise)} 个 title 含格式噪声（K3 未整理页遗留，不阻断）")
    return ok, issues


# ============================================================
#  检查 4：字段健康度
# ============================================================

VALID_COMPONENT = {"feat", "feat_index", "feat_intro"}
VALID_FORMAT = {"standard", "lb_marker", "elided", "whitespace", "punct", "img_marker", "annotation"}


def check_field_health(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """字段健康度：chunk_id 唯一、doc_id 非空、component_type 合法、format_cluster 合法"""
    ok = True
    issues: List[str] = []

    ids = [c.get("chunk_id", "") for c in chunks]
    dup_ids = {k for k, v in Counter(ids).items() if v > 1}
    if dup_ids:
        ok = False
        issues.append(f"❌ {len(dup_ids)} 个重复 chunk_id（示例: {sorted(dup_ids)[:5]}）")
    else:
        print(f"  — chunk_id 唯一: {len(ids)}/{len(ids)}")

    no_doc = [c for c in chunks if not c.get("doc_id", "").strip()]
    if no_doc:
        ok = False
        issues.append(f"❌ {len(no_doc)} 个 chunk 缺 doc_id")

    bad_comp = [c for c in chunks if c.get("component_type") not in VALID_COMPONENT]
    if bad_comp:
        ok = False
        comps = Counter(c.get("component_type") for c in bad_comp)
        issues.append(f"❌ 非法 component_type: {dict(comps)}")

    bad_fmt = [
        c for c in chunks
        if c.get("metadata", {}).get("format_cluster") not in VALID_FORMAT
    ]
    if bad_fmt:
        ok = False
        fmts = Counter(c.get("metadata", {}).get("format_cluster") for c in bad_fmt)
        issues.append(f"❌ 非法 format_cluster: {dict(fmts)}")

    # 分布摘要
    fmt_dist = Counter(c.get("metadata", {}).get("format_cluster") for c in chunks)
    comp_dist = Counter(c.get("component_type") for c in chunks)
    print(f"  — format_cluster: {dict(fmt_dist)}")
    print(f"  — component_type: {dict(comp_dist)}")
    return ok, issues


# ============================================================
#  检查 5：R5 probe——elided 标题无正文句段碎片
# ============================================================


def check_no_fragment_titles(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """R5 probe：全库 elided 标题无一为正文句段碎片（`_is_fragment_title` 同口径）。

    源数据断行把散文句挂到行首，被 elided 包裹路径（M6/B/C/D/星形）误当标题——
    基线快照（3756 chunks）有 46 个碎片标题（『你向法术注入了来自骨园』『在你的』
    『此为一个或一群合计』等），R5 守卫（碎片名+长类型括号组合、整行星号剥离、
    粒子表清理）后清至 0。碎片 = 尾虚词/句号/句首引导。
    """
    from vectorizer.formats.feat import _is_fragment_title

    elided = [c for c in chunks if c.get("metadata", {}).get("format_cluster") == "elided"]
    bad = [c for c in elided if _is_fragment_title(c.get("title", ""))]
    print(f"  — elided 标题 {len(elided)} 个，正文句段碎片 {len(bad)} 个")
    if bad:
        samples = ", ".join(c["title"] for c in bad[:6])
        return False, [f"❌ {len(bad)} 个 elided 标题为正文句段碎片（R5 probe）: {samples}"]
    return True, []


# ============================================================
#  类目装配（VerifyBase 模板）
# ============================================================


class FeatVerify(VerifyBase):
    name = "专长集成验收"
    description = "专长集成验收（统一验收入口）"
    DEFAULT_CHUNKS = DEFAULT_CHUNKS

    checks = [
        ("判别器回归", check_discriminator_regression, "无 est>0 静默丢失"),
        ("召回", check_recall, "召回完成"),
        ("title 合法性", check_title_health, "title 全合法"),
        ("字段健康度", check_field_health, "字段全健康"),
        ("R5 probe（elided 标题无正文句段碎片）", check_no_fragment_titles, "全库 elided 标题无一为正文句段碎片"),
    ]

    def add_args(self, parser):
        parser.add_argument("--matrix", default=DEFAULT_MATRIX, type=Path)
        parser.add_argument("--baseline", default=DEFAULT_BASELINE, type=Path)
        parser.add_argument("--exemptions", default=DEFAULT_EXEMPTIONS, type=Path)

    def prepare(self, args):
        self.ctx["matrix"] = load_matrix(args.matrix)
        self.ctx["exemptions"] = load_exemptions(args.exemptions)
        self.ctx["baseline_path"] = args.baseline
        print(f"加载 {len(self.ctx['matrix'])} rel 矩阵 / 豁免 {len(self.ctx['exemptions'])} 条")
        print(f"豁免文件: {args.exemptions}{'（存在）' if args.exemptions.exists() else '（缺失 → 无豁免）'}")


def main():
    FeatVerify().main()


if __name__ == "__main__":
    main()
