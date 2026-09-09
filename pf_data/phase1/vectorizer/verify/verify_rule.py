"""
verify_rule.py — 规则模块集成验收（统一验收入口，VerifyBase 框架）

在 pipeline 全量运行后执行，十检查：
  1. 判别器回归：rule_per_file.jsonl（286 文件 est 7385 冻结口径）est↔got 对账
  2. 文件级召回与边界：doc_id 全部 ∈ manifest 286（无越权处理）
  3. title 合法性：URL 0 / 译者字段 0 / 星壳 0 / 空 title ≤19（KN204）
  4. 字段健康度：chunk_id 唯一 / 枚举值域 / book '?' ≤238（KN195/196/203/211）/
     空 text ≤1（page_508 KN197）/ source_confidence 全 75
  5. 来源书一致性：同源表（manifest rel × 专属表投影，改表两处生效）+
     rule_version == book 小写
  6. toc_group 值域：4 枚举且全非空（M2 §三 3.1，KN192）
  7. 实体枚举：rule_entry/rule_table 全 title+text 非空 + S6 10 文件全产出
  8. KN159/160 防回退：text CR 0 / title 行首尾单星 0
  9. KN206 防回退：text HTML 注释 0（S1~S5 注释行消费不并入正文）
 10. KN212 防回退：text 4+ 星连排 0（BBS `[b]` 嵌套转换残渣剥壳）

豁免登记（硬编码理由，技能/专长先例）：
  - 空 title 19（KN204）：正文型无标题锚（S5 无标题形态 17 + S2 前导空行 1 +
    page_508 空文件 1），检索端 title 空回退首行摘要展示
  - 空 text 1（page_508，KN197）：0 字节空文件（CHM 法术效果图，图片丢失），
    唯一空 text 豁免
  - book '?' ≤238（KN195 page_320 神祇扩展表混排 / KN196 作祟汇总 /
    KN211 表格行独立条目 +42 全定性 /
    KN203 page_320 预拆扩散 +94）：设计保留，'?' 家族逐次 KN 登记
  - KN160 对 rule 类目只适用于 title：正文斜体（305 处全定性）是章节型全文
    排版信息（段落强调/人名/书名），不可剥——text 单星断言不启用

用法：python3 -m vectorizer.verify.verify_rule [--chunks ...]
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Set, Tuple

from vectorizer.verify.base import VerifyBase
# 同源表（检查 1/2/5）：manifest 扫描清单 + 专属表解析函数——与 processor
# 侧同一数据源，改专属表一处两处生效（技能 _B2_SOURCE_DOC_EXPECT 先例，
# 补丁 #2 同源原则，防 verify 与 processor 漂移）
from vectorizer.processors.rule import RULE_SCAN_RELS, _resolve_rule_source

DEFAULT_CHUNKS = Path("vectorizer/output/规则/chunks.jsonl")
DEFAULT_PERFILE = Path("vectorizer/exploration/rule/rule_per_file.jsonl")

# ---- 豁免登记（硬编码理由，见模块 docstring）----
_EMPTY_TITLE_MAX = 19    # KN204：正文型无标题锚 19 全定性（检索端降权）
_EMPTY_TEXT_MAX = 1      # page_508 唯一（KN197 空文件豁免）
_BOOK_UNKNOWN_MAX = 238  # KN195/196/203：page_320 预拆扩散 +94 登记上限；
                          # KN211（2026-08-09）表格行独立条目后 page_320 '?'
                          # 101→143（每行多来源混排无法单一归书，设计保留
                          # 同口径），233 = 143+90，+5 余量（闸口同源）
# S6 超大型聚合 10 文件（processor `_RULE_S6_SHAPES` 同源，改表两处生效）
from vectorizer.processors.rule import _RULE_S6_SHAPES

# ---- 枚举值域（registry_rule.py 权威，M2 拍板）----
_VALID_COMPONENT = {"rule_section", "rule_entry", "rule_table",
                    "rule_intro", "rule_reference"}
# `none（空文件）`：page_508 空文件无格式可判（CHM 法术效果图，图片丢失，
# KN197 豁免）——processor 层设计特例值，verify 白名单对齐
_VALID_FORMAT = {"s1_heading_tree", "s2_bold_title", "s3_bbs_star",
                 "s4_table_page", "s5_prose", "s6_large_aggregate",
                 "none（空文件）"}
_VALID_TOC_GROUP = {"core_rules", "rules", "retrain", "quick_reference"}

# KN160 防回退：行首单星（可带缩进）/行尾单星（format 剥星规则同形，
# 对 rule 类目只适用于 title——正文斜体合法保留，见 docstring）
_RE_STAR_LEAK = re.compile(r"^[ \t]*\*(?!\*)|(?<!\*)\*[ \t]*$", re.M)
_URL_IN_TITLE = re.compile(r"https?://|\]\(http|\[\[")
# 译者字段行（`**译者：` / `**译者**：` 前缀形态；内容性「译者」说明
# （page_586 `**PFS官方战役指南全书的译者皆为空山鸣**`）是合法正文标题，
# 不在剥除范围——M5 探针口径修正）
_RE_TRANSLATOR_FIELD = re.compile(r"^\**译者")
_RE_TITLE_STAR_SHELL = re.compile(r"^\*\*")
_CR_RESIDUE = re.compile(r"\r")
# KN206 防回退：HTML 来源注释（`<!-- X-source:... -->`）残渣——S1~S5 注释行
# 消费不并入正文（format 层 _RE_ANCHOR_COMMENT 同形）；S6 锚点语义与
# chm_toc_path 回填（feat_chain RE_ANNO 读源文件）均不受 chunk 文本剥离影响
_RE_HTML_COMMENT = re.compile(r"<!--")
# KN212 防回退：4+ 星连排碎片（BBS `[b]` 嵌套转换残渣）——format 层
# normalize 第 7 步 `_RE_STAR_FRAGMENT` 剥除，同形断言（KN160/206 先例）；
# 干净 2 星加粗 / 单星斜体（人名/书名）不在断言范围
_RE_STAR_FRAGMENT = re.compile(r"\*{4,}")


def load_perfile(path: Path) -> List[dict]:
    if not path.exists():
        print(f"❌ per_file 不存在: {path}")
        raise SystemExit(1)
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _stem(rel: str) -> str:
    """rel → doc_id（basename 无 .md 后缀）"""
    return rel.rsplit("/", 1)[-1].removesuffix(".md")


# 同源期望表：{doc_id: book_abbreviation}——manifest 每 rel 用专属表解析
# 函数投影（'?' 键原样进表，天然兼容 KN195/196 设计保留）
_SOURCE_EXPECT_BY_DOC: Dict[str, str] = {}
for _rel in RULE_SCAN_RELS:
    _hit = _resolve_rule_source(_rel)
    if _hit is None:
        raise RuntimeError(f"规则专属来源表缺失（verify 自证失败）: {_rel}")
    _SOURCE_EXPECT_BY_DOC[_stem(_rel)] = _hit[0]

# S6 10 文件 doc_id 集合（rule_entry 产出核对）
_S6_DOCS: Set[str] = {_stem(rel) for rel in _RULE_S6_SHAPES}


# ============================================================
#  检查 1：判别器回归（est↔got 对账，286 rel est 7385 冻结）
# ============================================================


def check_discriminator_regression(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """判别器回归：rule_per_file.jsonl 每文件 est↔got 对账。

    - est>0 got=0：静默丢失 → FAIL（禁止）
    - got<est：亚产能 WARN 不阻断（M4 est 口径高估已全定性，见
      产出即检报告 b) 差异定性——字段行并入 KN102 / 小块合并）
    - got≥est：est 低估增量（怪物规则 +1090 / Unchained +643 等全定性）
    """
    matrix = ctx["matrix"]
    ok = True
    issues: List[str] = []
    got_by_doc: Counter = Counter(c.get("doc_id", "") for c in chunks)
    total_est = 0
    total_got = 0
    zero_loss = 0
    sub_prod = 0
    for e in matrix:
        est = e.get("estimated_count") or 0
        got = got_by_doc.get(_stem(e["file"]), 0)
        total_est += est
        total_got += got
        if est > 0 and got == 0:
            ok = False
            zero_loss += 1
            issues.append(f"❌ {e['file']}: est={est} got=0（静默丢失）")
        elif est > 0 and got < est:
            sub_prod += 1
            if sub_prod <= 8:
                issues.append(f"⚠️  {_stem(e['file'])}: est={est} got={got}（亚产能，M4 已定性）")
    print(f"  — 矩阵 {len(matrix)} 文件 est={total_est} got={total_got}"
          f"（Δ{total_got - total_est:+} 全定性），静默丢失 {zero_loss}，亚产能 {sub_prod} 条")
    if sub_prod > 8:
        issues.append(f"⚠️  亚产能共 {sub_prod} 条（M4 est 口径高估全定性，"
                      f"见产出即检报告 b) 差异定性；其余 {sub_prod - 8} 条略）")
    return ok, issues


# ============================================================
#  检查 2：文件级召回与边界（286 权威清单，无越权）
# ============================================================


def check_file_recall(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """文件级召回：每个 manifest 文件有产出（est>0 时 got≥1，检查 1 互补）
    + doc_id 全部 ∈ manifest（manifest 外文件被处理 = 越权 FAIL）"""
    ok = True
    issues: List[str] = []
    manifest_docs = {_stem(rel) for rel in ctx["manifest_rels"]}
    got_docs = {c.get("doc_id", "") for c in chunks}
    outside = sorted(got_docs - manifest_docs)
    if outside:
        ok = False
        issues.append(f"❌ {len(outside)} 个 doc 越权产出（manifest 外）: {outside[:6]}")
    got_by_doc = Counter(c.get("doc_id", "") for c in chunks)
    no_out = sorted(d for d in manifest_docs if got_by_doc.get(d, 0) == 0)
    if no_out:
        ok = False
        issues.append(f"❌ {len(no_out)} 个 manifest 文件零产出: {no_out[:6]}")
    print(f"  — manifest {len(manifest_docs)} 文件全命中，越权 {len(outside)}，零产出 {len(no_out)}")
    return ok, issues


# ============================================================
#  检查 3：title 合法性（URL / 译者字段 / 星壳 / 空 title KN204）
# ============================================================


def check_title_health(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """title 合法性：URL/图片链接 0、译者字段 0、星壳 0、
    空 title ≤19（KN204 豁免登记）、首尾单星 0（KN160 title 适用）"""
    ok = True
    issues: List[str] = []
    url = [c for c in chunks if _URL_IN_TITLE.search(c.get("title", ""))]
    trans = [c for c in chunks if _RE_TRANSLATOR_FIELD.match(c.get("title", ""))]
    shell = [c for c in chunks if _RE_TITLE_STAR_SHELL.match(c.get("title", ""))]
    empty = [c for c in chunks if not c.get("title", "").strip()]
    star = [c for c in chunks if _RE_STAR_LEAK.search(c.get("title", ""))]
    print(f"  — title URL: {len(url)}  译者字段: {len(trans)}  星壳: {len(shell)}"
          f"  空: {len(empty)}（≤{_EMPTY_TITLE_MAX} KN204）  首尾单星: {len(star)}")
    if url:
        ok = False
        issues.append(f"❌ {len(url)} 个 title 含 URL/图片链接: {sorted({c['doc_id'] for c in url})[:5]}")
    if trans:
        ok = False
        issues.append(f"❌ {len(trans)} 个 title 含译者字段: {sorted({c['doc_id'] for c in trans})[:5]}")
    if shell:
        ok = False
        issues.append(f"❌ {len(shell)} 个 title 含星壳: {sorted({c['doc_id'] for c in shell})[:5]}")
    if len(empty) > _EMPTY_TITLE_MAX:
        ok = False
        issues.append(f"❌ 空 title {len(empty)} 超登记上限 {_EMPTY_TITLE_MAX}（KN204）")
    if star:
        ok = False
        issues.append(f"❌ KN160 {len(star)} 个 title 行首/行尾单星: {sorted({c['doc_id'] for c in star})[:5]}")
    return ok, issues


# ============================================================
#  检查 4：字段健康度（值域 / book '?' / 空 text / 置信度）
# ============================================================


def check_field_health(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """字段健康：chunk_id 唯一、doc_id 非空、component_type/format_cluster/
    toc_group 值域合法、book '?' ≤238（KN195/196/203/211）、空 text ≤1（page_508
    KN197）、source_confidence 全 75（专属表短路 conf）"""
    ok = True
    issues: List[str] = []

    ids = [c.get("chunk_id", "") for c in chunks]
    dup = {k for k, v in Counter(ids).items() if v > 1}
    if dup:
        ok = False
        issues.append(f"❌ {len(dup)} 个重复 chunk_id（示例: {sorted(dup)[:5]}）")
    else:
        print(f"  — chunk_id 唯一: {len(ids)}/{len(ids)}")

    no_doc = [c for c in chunks if not c.get("doc_id", "").strip()]
    if no_doc:
        ok = False
        issues.append(f"❌ {len(no_doc)} 个 chunk 缺 doc_id")

    bad_comp = [c for c in chunks if c.get("component_type") not in _VALID_COMPONENT]
    if bad_comp:
        ok = False
        issues.append(f"❌ 非法 component_type: {dict(Counter(c['component_type'] for c in bad_comp))}")
    bad_fmt = [c for c in chunks
               if c.get("metadata", {}).get("format_cluster") not in _VALID_FORMAT]
    if bad_fmt:
        ok = False
        fmts = Counter(c["metadata"].get("format_cluster") for c in bad_fmt)
        issues.append(f"❌ 非法 format_cluster: {dict(fmts)}")
    bad_group = [c for c in chunks
                 if c.get("metadata", {}).get("toc_group") not in _VALID_TOC_GROUP]
    if bad_group:
        ok = False
        groups = Counter(c["metadata"].get("toc_group") for c in bad_group)
        issues.append(f"❌ 非法 toc_group: {dict(groups)}")

    bookq = [c for c in chunks if c.get("book_abbreviation") == "?"]
    if len(bookq) > _BOOK_UNKNOWN_MAX:
        ok = False
        issues.append(f"❌ book '?' {len(bookq)} 超登记上限 {_BOOK_UNKNOWN_MAX}"
                      f"（KN195/196/203 棘轮不预放）")
    else:
        print(f"  — book '?' {len(bookq)}（≤{_BOOK_UNKNOWN_MAX}，"
              f"分布: {dict(Counter(c['doc_id'] for c in bookq))}）")

    empty = [c for c in chunks if not c.get("text", "").strip()]
    if len(empty) > _EMPTY_TEXT_MAX:
        ok = False
        issues.append(f"❌ 空 text {len(empty)} 超豁免上限 {_EMPTY_TEXT_MAX}"
                      f"（仅 page_508 KN197 预期）: {sorted({c['doc_id'] for c in empty})}")
    elif empty:
        print(f"  — 空 text {len(empty)}（page_508 空文件豁免 KN197）")

    low_conf = [c for c in chunks if c.get("source_confidence") != 75]
    if low_conf:
        ok = False
        issues.append(f"❌ {len(low_conf)} 个 chunk 非 conf 75（专属表短路应全 75）")

    comp_dist = Counter(c.get("component_type") for c in chunks)
    fmt_dist = Counter(c.get("metadata", {}).get("format_cluster") for c in chunks)
    print(f"  — component_type: {dict(comp_dist)}")
    print(f"  — format_cluster: {dict(fmt_dist)}")
    return ok, issues


# ============================================================
#  检查 5：来源书一致性（同源表 + rule_version 小写）
# ============================================================


def check_source_book(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """来源书一致性：doc 级 book_abbreviation 必须 = 专属表投影
    （_SOURCE_EXPECT_BY_DOC，manifest × _resolve_rule_source 同源生成）；
    rule_version == book 小写（M2）；专属表全部 doc 必须有产出。

    背景：DirectoryNameProvider 子串误命中致技能 557/557 全标 CRB（审计 P1
    系统性失实）教训——本类目专属表短路（_RULE_SOURCE_OVERRIDES 65+ 键
    conf 75），本断言保证覆盖生效且不回退。'?' 键（page_320 KN195 / 作祟
    汇总 KN196）原样进表，天然兼容设计保留。
    """
    ok = True
    issues: List[str] = []
    seen: Set[str] = set()
    for c in chunks:
        did = c.get("doc_id", "")
        if not did or did in seen:
            continue
        seen.add(did)
        book = c.get("book_abbreviation", "")
        expect = _SOURCE_EXPECT_BY_DOC.get(did)
        if expect is None:
            ok = False
            issues.append(f"❌ {did}: 未登记专属表（manifest 缺失或越权 doc）")
        elif book != expect:
            ok = False
            issues.append(f"❌ {did}: book={book} 应 {expect}（专属表短路失实）")
        rv = (c.get("metadata") or {}).get("rule_version", "")
        if rv and rv != book.lower():
            ok = False
            issues.append(f"❌ {did}: rule_version={rv} ≠ book 小写 {book.lower()}")
    missing = sorted(set(_SOURCE_EXPECT_BY_DOC) - seen)
    if missing:
        ok = False
        issues.append(f"❌ 专属表 {len(missing)} 个 doc 无产出: {missing[:6]}")
    print(f"  — 来源书一致性：{len(seen)} 个 doc 全匹配专属表（{len(_SOURCE_EXPECT_BY_DOC)} 条）"
          + ("，全部命中" if not missing else f"，缺产出 {missing[:6]}"))
    return ok, issues


# ============================================================
#  检查 6：toc_group 值域（4 枚举，KN192 manifest 显式注解）
# ============================================================


def check_toc_group(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """toc_group 值域：4 枚举且全非空（M2 §三 3.1 归属表；processor
    manifest 完整性自证已有——verify 侧复核产物级注解不回退）"""
    ok = True
    issues: List[str] = []
    no_group = [c for c in chunks
                if not (c.get("metadata") or {}).get("toc_group", "").strip()]
    if no_group:
        ok = False
        issues.append(f"❌ {len(no_group)} 个 chunk 缺 toc_group 注解"
                      f"（示例: {sorted({c['doc_id'] for c in no_group})[:5]}）")
    dist = Counter(c["metadata"].get("toc_group") for c in chunks
                   if (c.get("metadata") or {}).get("toc_group"))
    print(f"  — toc_group: {dict(dist)}（∈ {sorted(_VALID_TOC_GROUP)}，全非空）")
    return ok, issues


# ============================================================
#  检查 7：实体枚举（rule_entry/rule_table 全健康 + S6 产出）
# ============================================================


def check_entity_enum(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """实体枚举：rule_entry（S6 条目）与 rule_table（整页纯表）全 title+text
    非空；S6 10 文件全部产出 rule_entry（M4 条目化增量落地点）"""
    ok = True
    issues: List[str] = []
    entries = [c for c in chunks if c["component_type"] == "rule_entry"]
    tables = [c for c in chunks if c["component_type"] == "rule_table"]
    bad_entry = [c for c in entries
                 if not (c.get("title") or "").strip() or not (c.get("text") or "").strip()]
    bad_table = [c for c in tables if not (c.get("text") or "").strip()]
    if bad_entry:
        ok = False
        issues.append(f"❌ {len(bad_entry)} 个 rule_entry 空 title/text"
                      f"（示例: {sorted({c['doc_id'] for c in bad_entry})[:5]}）")
    if bad_table:
        ok = False
        issues.append(f"❌ {len(bad_table)} 个 rule_table 空 text"
                      f"（示例: {sorted({c['doc_id'] for c in bad_table})[:5]}）")
    entry_docs = {c.get("doc_id") for c in entries}
    no_entry = sorted(_S6_DOCS - entry_docs)
    if no_entry:
        ok = False
        issues.append(f"❌ S6 {len(no_entry)} 文件未产出 rule_entry: {no_entry}")
    print(f"  — rule_entry {len(entries)}（S6 {len(_S6_DOCS)} 文件全产出），"
          f"rule_table {len(tables)}，全 title/text 非空")
    return ok, issues


# ============================================================
#  检查 8：KN159/160 防回退（text CR / title 单星）
# ============================================================


def check_kn159_160(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """KN159/160 防回退：text CR 残迹 0（表格行行中 CR 腰斩家族）；
    title 行首/行尾单星 0（KN160——正文斜体合法保留 305，断言只对 title）。
    重跑 pipeline 后拦截复发（专长/技能家族先例）。"""
    ok = True
    issues: List[str] = []
    cr = [c for c in chunks if _CR_RESIDUE.search(c.get("text", ""))]
    if cr:
        ok = False
        issues.append(f"❌ KN159 {len(cr)} 个 chunk text 含 CR 残迹"
                      f"（示例: {sorted({c['doc_id'] for c in cr})[:5]}）")
    star = [c for c in chunks if _RE_STAR_LEAK.search(c.get("title", ""))]
    if star:
        ok = False
        issues.append(f"❌ KN160 {len(star)} 个 title 行首/行尾单星"
                      f"（示例: {sorted({c['doc_id'] for c in star})[:5]}）")
    print(f"  — text CR 残迹 {len(cr)}，title 首尾单星 {len(star)}")
    return ok, issues


# ============================================================
#  检查 9：KN206 防回退（text HTML 注释 0）
# ============================================================


def check_kn206(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """KN206 防回退：text 含 HTML 注释（`<!--`）0——S1~S5 注释行消费不
    并入正文（M6 审计 P1 修复）。重跑 pipeline 后拦截复发（KN159/160 先例）。"""
    leak = [c for c in chunks if _RE_HTML_COMMENT.search(c.get("text", ""))]
    issues: List[str] = []
    if leak:
        issues.append(f"❌ KN206 {len(leak)} 个 chunk text 含 HTML 注释"
                      f"（示例: {sorted({c['doc_id'] for c in leak})[:5]}）")
    print(f"  — text HTML 注释 {len(leak)}")
    return not issues, issues


# ============================================================
#  检查 10：KN212 防回退（text 4+ 星连排碎片 0）
# ============================================================


def check_kn212(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """KN212 防回退：text 含 4+ 星连排（`\*{4,}`）0——BBS `[b]` 嵌套转换
    残渣（`**重训（****Retraining****）******` / `**野蛮****人****（Unchained）**`），
    format 层 normalize 第 7 步剥除（KN160/206 先例）。干净 2 星加粗与
    单星斜体（305 处全定性保留）不在断言范围。"""
    leak = [c for c in chunks if _RE_STAR_FRAGMENT.search(c.get("text", ""))]
    issues: List[str] = []
    if leak:
        issues.append(f"❌ KN212 {len(leak)} 个 chunk text 含 4+ 星连排"
                      f"（示例: {sorted({c['doc_id'] for c in leak})[:5]}）")
    print(f"  — text 4+ 星连排 {len(leak)}")
    return not issues, issues


# ============================================================
#  类目装配（VerifyBase 模板）
# ============================================================


class RuleVerify(VerifyBase):
    name = "规则集成验收"
    description = "规则模块集成验收（统一验收入口，十检查）"
    DEFAULT_CHUNKS = DEFAULT_CHUNKS

    checks = [
        ("判别器回归", check_discriminator_regression, "无 est>0 静默丢失（est 7385 冻结口径）"),
        ("文件级召回与边界", check_file_recall, "manifest 286 文件全命中，无越权产出"),
        ("title 合法性", check_title_health, "title 全合法（URL/译者/星壳 0，空 ≤19 KN204）"),
        ("字段健康度", check_field_health, "字段全健康（值域/空 text/'?' 上限内）"),
        ("来源书一致性", check_source_book, "doc 级 book↔专属表全匹配（同源表）"),
        ("toc_group 值域", check_toc_group, "toc_group ∈ 4 枚举且全非空（KN192）"),
        ("实体枚举", check_entity_enum, "rule_entry/rule_table 全健康，S6 全产出"),
        ("KN159/160 防回退", check_kn159_160, "text CR 0 / title 首尾单星 0"),
        ("KN206 防回退", check_kn206, "text HTML 注释 0（S1~S5 注释消费）"),
        ("KN212 防回退", check_kn212, "text 4+ 星连排 0（BBS 嵌套转换残渣）"),
    ]

    def add_args(self, parser):
        parser.add_argument("--perfile", default=DEFAULT_PERFILE, type=Path)

    def prepare(self, args):
        self.ctx["matrix"] = load_perfile(args.perfile)
        self.ctx["manifest_rels"] = RULE_SCAN_RELS
        print(f"加载 {len(self.ctx['matrix'])} 个 per_file 矩阵 rel"
              f"（est 合计 {sum((e.get('estimated_count') or 0) for e in self.ctx['matrix'])}，"
              f"M1 人工门 1 冻结口径）")


def main():
    RuleVerify().main()


if __name__ == "__main__":
    main()
