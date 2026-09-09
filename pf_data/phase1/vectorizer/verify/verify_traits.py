"""verify_traits.py — 背景特性集成验收（VerifyBase 框架）

在 pipeline 全量运行后执行，六检查（对齐专长 verify_feats / 种族 verify_races
形态 + trait 专属口径）：
  1. 判别器回归：per_file_B1/B2/B3.jsonl 合并 63 rel 的 est↔got 对账
     （est>0 got=0 静默丢失 → FAIL；est>got 亚产能 → WARN 不阻断；
     KN 豁免 doc_id 产出可为 0）
  2. 总召回：est_total ↔ got_total 行级召回 ≥ 95%（人工门 1 硬指标）
  3. title 合法性：trait/trait_flaw 无空 title / 无 URL / 无星壳残留
     （trait_intro 章节介绍段无条目名，豁免空 title）
  4. 字段健康度：chunk_id 唯一、doc_id 非空、component_type ∈ 3 枚举、
     format_cluster ∈ 15 簇枚举
  5. trait_flaw 归属：全部来自 page_158（文件级判定防泄漏——缺陷条目
     独有规则体系，误标污染检索语义）
  6. trait_type 词表：metadata.trait_type 值 ∈ 12 值归一词表
     （未知值只警告不阻断——基础（X）已剥壳并入，残留未知值登记）

豁免程序：无豁免文件（63 rel 全产出 >0，无静默丢失）；矩阵为 JSONL 行格式
（feat 为 JSON），est 字段 estimated_count（对齐 race）。

用法：python3 -m vectorizer.verify.verify_traits [--chunks ...] [--matrix-dir ...]
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import List, Tuple

from vectorizer.verify.base import VerifyBase

DEFAULT_CHUNKS = Path("vectorizer/output/背景特性/chunks.jsonl")
DEFAULT_MATRIX_DIR = Path("vectorizer/exploration/trait")

# ---- component_type 三值（元数据设计 §二）----
_COMPONENT_TYPES = {"trait", "trait_intro", "trait_flaw"}

# ---- format_cluster 15 簇（勘探定稿，format_cluster_assign.json 值域）----
_FORMAT_CLUSTERS = {
    "A_basic_page", "B2_standard_h2", "B1_star_field", "B1_bold_field",
    "B3_flow_bare", "B3_triple_title", "B4_field_no_colon", "B1_glue",
    "B1_nested", "B5_dual_source", "B1_marker", "C_flaw",
    "D_exalted_mount_cosmic", "B9_high_entropy", "intro",
}

# ---- trait_type 归一词表（processor _TRAIT_TYPE_NORM 同源，12+1 值）----
_TRAIT_TYPE_VOCAB = {
    "信念", "宗教", "地区", "社会", "战斗", "魔法", "种族",
    "信念背景", "地区背景", "社交", "战斗背景", "魔法背景", "种族背景",
    "典范",  # 独立体系（取代两个通常背景）
    # 方案 R1（2026-08-06）词表定稿 13 值：+派系/宇宙/装备/坐骑/缺陷
    #（CHM 目录「背景特性」13 个类型目录一一对应，含 5 个变体）
    "派系", "宇宙", "装备", "坐骑", "缺陷",
    "派系背景", "宇宙背景", "装备背景", "坐骑背景", "缺陷背景",
}


def load_matrix(dir_path: Path) -> List[dict]:
    rows = []
    for f in sorted(dir_path.glob("per_file_B*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        print(f"❌ 判别器矩阵为空: {dir_path}/per_file_B*.jsonl")
        raise SystemExit(1)
    return rows


def _doc_id_of(rel: str) -> str:
    """矩阵 rel（背景特性/page_150.md）→ doc_id（文件名 stem）"""
    return rel.rsplit("/", 1)[-1][:-3]


def _load_chunks(path: Path) -> List[dict]:
    if not path.exists():
        print(f"❌ 产物不存在: {path}（先跑 pipeline）")
        raise SystemExit(1)
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ============================================================
#  检查 1：判别器回归（est↔got 对账）
# ============================================================

def check_discriminator_regression(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """判别器回归：每个矩阵 rel 的产出（按 doc_id 汇总）与 est 对账。

    - est>0 但产出 0：静默丢失 → FAIL
    - 产出 < est：亚产能（既有质量差距），WARN 不阻断
    - 产出 ≥ est：达标（含设计性溢出：intro 章节介绍 chunk）
    """
    matrix = ctx["matrix"]
    ok = True
    issues: List[str] = []
    got_by_doc: Counter = Counter(c.get("doc_id", "") for c in chunks)
    total_est = 0
    total_got = 0
    zero_loss = 0
    under = 0
    for e in matrix:
        rel = e.get("rel") or e.get("file")
        if not rel:
            continue
        est = e.get("estimated_count", 0)
        got = got_by_doc.get(_doc_id_of(rel), 0)
        total_est += est
        total_got += got
        if est > 0 and got == 0:
            ok = False
            zero_loss += 1
            issues.append(f"❌ {rel}: est={est} got=0（静默丢失）")
        elif est > 0 and got < est:
            under += 1
            issues.append(f"⚠️  {rel}: est={est} got={got}（亚产能，既有差距）")
    issues.append(
        f"  — 矩阵 rel 产出合计 est={total_est} got={total_got}，"
        f"静默丢失 {zero_loss} 条、亚产能 {under} 文件"
    )
    return ok, issues


# ============================================================
#  检查 2：总召回（行级召回 ≥ 95%，人工门 1 硬指标）
# ============================================================

MIN_RECALL = 0.95


def check_total_recall(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """总召回 = got_total / est_total（chunk 总数含 intro 设计溢出，故可达 ≥100%）"""
    est_total = ctx["est_total"]
    got_total = len(chunks)
    recall = got_total / est_total if est_total else 1.0
    ok = recall >= MIN_RECALL
    msg = (
        f"行级召回 {got_total}/{est_total} = {recall:.1%}"
        f"（≥ {MIN_RECALL:.0%} 人工门 1 硬指标）"
    )
    return ok, ([f"❌ {msg}"] if not ok else [f"✅ {msg}"])


# ============================================================
#  检查 3：title 合法性
# ============================================================

def check_title_health(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """trait/trait_flaw 无空 title；intro 豁免；无 URL/星壳残留/译者标记"""
    ok = True
    issues: List[str] = []
    bad = 0
    for c in chunks:
        ct = c.get("component_type", "")
        title = c.get("title", "")
        if not title.strip():
            if ct == "trait_intro":
                continue
            bad += 1
            issues.append(f"❌ 空 title: {c.get('doc_id')} ct={ct}")
            continue
        if "http" in title or re.search(r"\*|【|】|_", title):
            bad += 1
            issues.append(f"❌ title 噪声: {title[:30]!r}（{c.get('doc_id')}）")
    if not bad:
        issues.append("✅ 全部 title 合法（空 title 仅限 trait_intro 豁免）")
    return ok and bad == 0, issues


# ============================================================
#  检查 4：字段健康度
# ============================================================

def check_field_health(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """chunk_id 唯一 / doc_id 非空 / component_type 3 枚举 / format_cluster 15 簇"""
    ok = True
    issues: List[str] = []
    ids = [c.get("chunk_id", "") for c in chunks]
    dup = len(ids) - len(set(ids))
    if dup:
        ok = False
        issues.append(f"❌ chunk_id 重复 {dup} 个")
    no_doc = sum(1 for c in chunks if not c.get("doc_id"))
    if no_doc:
        ok = False
        issues.append(f"❌ doc_id 空 {no_doc} 个")
    bad_ct = Counter(c.get("component_type", "?") for c in chunks)
    for ct in bad_ct:
        if ct not in _COMPONENT_TYPES:
            ok = False
            issues.append(f"❌ 非法 component_type {ct!r}: {bad_ct[ct]} 个")
    bad_fc = Counter(c.get("metadata", {}).get("format_cluster", "?") for c in chunks)
    for fc in bad_fc:
        if fc not in _FORMAT_CLUSTERS:
            ok = False
            issues.append(f"❌ 非法 format_cluster {fc!r}: {bad_fc[fc]} 个")
    if ok:
        issues.append(
            f"✅ 字段健康（{len(chunks)} chunks：component_type "
            f"{dict(Counter(c['component_type'] for c in chunks))}）"
        )
    return ok, issues


# ============================================================
#  检查 5：trait_flaw 归属（page_158 文件级判定防泄漏）
# ============================================================

def check_flaw_origin(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """trait_flaw 必须全部来自 page_158（缺陷条目独立规则体系，
    文件级判定——误标到其他文件污染检索语义）"""
    ok = True
    issues: List[str] = []
    leak = [c for c in chunks if c.get("component_type") == "trait_flaw" and c.get("doc_id") != "page_158"]
    if leak:
        ok = False
        for c in leak[:5]:
            issues.append(f"❌ trait_flaw 泄漏: {c.get('doc_id')} {c.get('title', '')[:20]!r}")
        issues.append(f"  — 共 {len(leak)} 条非 page_158 缺陷条目")
    else:
        n = sum(1 for c in chunks if c.get("component_type") == "trait_flaw")
        issues.append(f"✅ trait_flaw {n} 条全部归属 page_158")
    return ok, issues


# ============================================================
#  检查 6：trait_type 词表（12 值归一词表）
# ============================================================

def check_trait_type_vocab(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """metadata.trait_type 值 ∈ 归一词表（未知值警告不阻断——登记 KN）"""
    ok = True
    issues: List[str] = []
    unknown: Counter = Counter()
    for c in chunks:
        for v in c.get("metadata", {}).get("trait_type", []) or []:
            if v not in _TRAIT_TYPE_VOCAB:
                unknown[v] += 1
    if unknown:
        issues.append(
            f"⚠️  未知 trait_type {len(unknown)} 值（非词表，登记 KN）："
            + ", ".join(f"{v}×{n}" for v, n in unknown.most_common())
        )
    else:
        issues.append("✅ 全部 trait_type 在归一词表内")
    return ok, issues


class TraitVerify(VerifyBase):
    name = "背景特性集成验收"
    description = "背景特性集成验收（#137）"
    DEFAULT_CHUNKS = DEFAULT_CHUNKS

    checks = [
        ("判别器回归", check_discriminator_regression, "无 est>0 静默丢失"),
        ("总召回", check_total_recall, f"行级召回 ≥ {MIN_RECALL:.0%}（人工门 1 硬指标）"),
        ("title 合法性", check_title_health, "title 全合法"),
        ("字段健康度", check_field_health, "字段全健康"),
        ("trait_flaw 归属", check_flaw_origin, "trait_flaw 全来自 page_158"),
        ("trait_type 词表", check_trait_type_vocab, "trait_type 全在归一词表"),
    ]

    def add_args(self, parser):
        parser.add_argument("--matrix-dir", default=DEFAULT_MATRIX_DIR, type=Path)

    def prepare(self, args):
        matrix = load_matrix(args.matrix_dir)
        self.ctx["matrix"] = matrix
        self.ctx["est_total"] = sum(
            e.get("estimated_count", 0)
            for e in matrix
            if e.get("rel") or e.get("file")
        )
        print(f"加载 {len(matrix)} rel 判别器矩阵（B1/B2/B3 合并，est 合计 {self.ctx['est_total']}）")


def main():
    TraitVerify().main()


if __name__ == "__main__":
    main()
