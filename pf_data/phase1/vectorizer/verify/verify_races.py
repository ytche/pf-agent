"""
verify_races.py — 种族集成验收（#100，VerifyBase 框架）

在 pipeline 全量运行后执行，八检查（对齐专长 verify_feats 形态 + 种族专属口径）：
  1. 判别器回归：race_per_file.jsonl 112 rel 的 est↔got 对账（含 KN 豁免）
  2. 召回：audit_baseline.jsonl 基线（37 种族）↔ chunk title+aliases
  3. 六字段规范化比对：基线六字段（ability_adj/bio_type/size/speed/senses）
     ↔ race_overview chunk metadata（ability_adj 数值集排序比对，属性名顺序无关；
     其余字段非空值精确比对）
  4. title 合法性：无空 title / 无 URL / 无译者标记 / 无格式噪声
  5. 字段健康度：chunk_id 唯一、doc_id 非空、component_type 合法（12 枚举）、
     format_cluster 合法（A~G）
  6. alt_trait replaces 非空率：field_status.replaces == parsed 比率 ≥ 阈值
     （当前 371/426 = 87.1%；missing 含「改变属性调整」等无替换语义的合理缺省）
  7. page_11 行级召回：源表数据行族名（37 族 × 2 表）↔ race_overview title
     （KN130 防回归——doc 级召回盲区：3 族整行静默丢失）
  8. page_752 component_type：页文件全部 alt_trait（KN131 防回归——
     M22 只修聚合文件漏页文件，52 条误标 race_trait）

豁免程序：无豁免文件（与 feat 不同——race 豁免仅 2 个 doc_id，硬编码 _EXEMPT_DOCS
并登记 KN，避免为 2 条豁免引入文档解析机制）；判别器矩阵为 JSONL 行格式
（feat 为 JSON），est 字段名 estimated_count（feat 为 est）。

用法：python3 -m vectorizer.verify.verify_races [--chunks ...] [--matrix ...] [--baseline ...]
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Set, Tuple

from vectorizer.verify.base import VerifyBase, make_row_recall_check

DEFAULT_CHUNKS = Path("vectorizer/output/种族/chunks.jsonl")
DEFAULT_MATRIX = Path("vectorizer/exploration/race/race_per_file.jsonl")
DEFAULT_BASELINE = Path("vectorizer/exploration/race/audit_baseline.jsonl")
DEFAULT_ENUM = Path("docs/种族/entity_enum.json")

# ---- KN 豁免（登记 已知问题记录.md，无豁免文件）----
# 1. 阴影血脉BoS_影生暗生种族特性：聚合文件（`<!-- BoS-source:种族特性/
#    page_386.md:__aggregate__ -->` 标记），内容与原始文件重复，原始文件
#    在其他类目（不在 race 矩阵），聚合文件设计排除，est=10 产出 0
# （page_812 阿斯托莫伊人豁免已于 M20 移除：源数据标题整理 → race_intro 产出）
_EXEMPT_DOCS: Dict[str, str] = {
    "阴影血脉BoS_影生暗生种族特性": "聚合文件（BoS-source 标记，原始文件在其他类目），设计排除，KN 登记",
}


def load_matrix(path: Path) -> List[dict]:
    if not path.exists():
        print(f"❌ 判别器矩阵不存在: {path}")
        raise SystemExit(1)
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _doc_id_of(rel: str) -> str:
    """矩阵 rel（pf_rules_md_organized/种族/.../page_752.md）→ doc_id（文件名 stem）"""
    return rel.rsplit("/", 1)[-1][:-3]


# ============================================================
#  检查 1：判别器回归（est↔got 对账，含 KN 豁免）
# ============================================================


def check_discriminator_regression(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """判别器回归：每个矩阵 rel 的产出（按 doc_id 汇总）与 est 对账。

    - 豁免 doc_id（_EXEMPT_DOCS，KN 登记）：产出可为 0，不阻断
    - 非豁免 rel est>0 但产出 0：静默丢失 → FAIL
    - 非豁免 rel 产出 < est：亚产能（既有质量差距），WARN 不阻断
    """
    matrix = ctx["matrix"]
    ok = True
    issues: List[str] = []
    got_by_doc: Counter = Counter(c.get("doc_id", "") for c in chunks)
    total_est = 0
    total_got = 0
    exempt_rows = []
    zero_loss = 0
    for e in matrix:
        rel = e["file"]
        est = e.get("estimated_count", 0)
        did = _doc_id_of(rel)
        got = got_by_doc.get(did, 0)
        if did in _EXEMPT_DOCS:
            exempt_rows.append((rel, est, got, _EXEMPT_DOCS[did]))
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
        print(f"  — KN 豁免 {len(exempt_rows)} 条：")
        for rel, est, got, reason in exempt_rows:
            print(f"    {rel}: est={est} got={got} — {reason}")
    print(f"  — 非豁免矩阵 rel 产出合计 est={total_est} got={total_got}，静默丢失 {zero_loss} 条")
    return ok, issues


# ============================================================
#  检查 2：召回（audit_baseline.jsonl 37 种族 ↔ chunk title+aliases）
# ============================================================


def check_recall(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """召回：基线 37 种族 ↔ chunk title+aliases 命中（name_zh 或 name_en）。"""
    baseline_path: Path = ctx["baseline_path"]
    if not baseline_path.exists():
        print(f"⚠️  召回基线不存在: {baseline_path}（跳过召回检查）")
        return True, []
    rows = [json.loads(l) for l in baseline_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    total = len(rows)

    titles: Set[str] = set()
    for c in chunks:
        titles.add(c.get("title", ""))
        for a in c.get("aliases", []):
            if a:
                titles.add(a)

    hit = 0
    miss = []
    for d in rows:
        zh = d.get("name_zh", "")
        en = d.get("name_en", "")
        if (zh and zh in titles) or (en and en in titles):
            hit += 1
        else:
            miss.append(f"{zh}({en})")
    pct = 100.0 * hit / total if total else 0
    print(f"  — 基线 {total} 种族 → 命中 {hit} = {pct:.1f}%")
    if miss:
        print(f"  — 未命中: {', '.join(miss)}")
        return False, [f"❌ 召回未命中 {len(miss)} 条: {', '.join(miss)}"]
    return True, []


# ============================================================
#  检查 3：六字段规范化比对（基线 ↔ race_overview chunk metadata）
# ============================================================

# 基线 ability_adj 数组属性顺序：STR/DEX/CON/INT/WIS/CHA
_ABILITY_ORDER = ["力量", "敏捷", "体质", "智力", "感知", "魅力"]
_ABILITY_EN = {"STR": "力量", "DEX": "敏捷", "CON": "体质", "INT": "智力", "WIS": "感知", "CHA": "魅力"}
# chunk 侧与基线共同的「任一属性+2」写法（半精灵/半兽人/人类），直接同串比对
_FLEXIBLE_ADJ = "任一属性"


def _norm_ability_adj_baseline(items: List[str]) -> Set[str]:
    """基线数组（STR/DEX/CON/INT/WIS/CHA 顺序，如 ['', '+2', '', '+2', '-2', '']）
    → 「±N属性」集合（属性名顺序无关）。仅纯数值形态（'+2'）按索引映射属性名；
    「任一属性+2」等非数值形态原样保留（chunk 侧同串，直接匹配）。"""
    out = set()
    for idx, v in enumerate(items):
        if not v:
            continue
        if re.match(r"^[+-]\d+$", v):
            out.add(f"{v}{_ABILITY_ORDER[idx]}")
        else:
            out.add(v)
    return out


def _norm_ability_adj_chunk(text: str) -> Set[str]:
    """chunk 字符串（'+2体质，+2感知，-2魅力' / '任一属性+2'）
    → 「±N属性」集合（顺序无关）。"""
    out = set()
    for part in re.split(r"[，、,]", text.strip()):
        part = part.strip()
        if not part:
            continue
        # 「任一属性+2」与基线同串（符号在后），直接保留
        out.add(part)
    return out


def check_six_field_consistency(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """六字段规范化比对：基线 37 种族六字段 ↔ race_overview chunk metadata。

    口径：ability_adj 按 ±N 数值集排序比对（属性名顺序无关，「任一属性+2」特判
    同串匹配）；bio_type/size/speed/senses 非空值精确比对。每个基线种族取
    title==name_zh（或 aliases 含 name_en）的 race_overview chunk 中第一个
    ability_adj 非空的比对；ability_adj 非空但其他字段缺值 → WARN 不阻断。
    """
    baseline_path: Path = ctx["baseline_path"]
    if not baseline_path.exists():
        print(f"⚠️  召回基线不存在: {baseline_path}（跳过六字段检查）")
        return True, []
    rows = [json.loads(l) for l in baseline_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    ok = True
    issues: List[str] = []
    by_title: Dict[str, dict] = {}
    for c in chunks:
        if c.get("component_type") != "race_overview":
            continue
        key = c.get("title", "")
        if key not in by_title:
            by_title[key] = c
        else:
            # 同名多 chunk 取 ability_adj 非空者（不同书重复概述）
            cur = by_title[key]
            if not cur.get("metadata", {}).get("ability_adj") and c.get("metadata", {}).get("ability_adj"):
                by_title[key] = c

    checked = 0
    for d in rows:
        zh = d.get("name_zh", "")
        en = d.get("name_en", "")
        cand = by_title.get(zh)
        if cand is None:
            # title 未命中时尝试 aliases 含 name_en
            for c in chunks:
                if c.get("component_type") == "race_overview" and en and en in c.get("aliases", []):
                    cand = c
                    break
        if cand is None:
            issues.append(f"⚠️  {zh}({en}) 无 race_overview chunk（六字段无法比对）")
            continue
        md = cand.get("metadata", {})
        base_adj = _norm_ability_adj_baseline(d.get("ability_adj", []))
        chunk_adj = _norm_ability_adj_chunk(md.get("ability_adj", ""))
        if base_adj != chunk_adj:
            ok = False
            issues.append(f"❌ {zh}: ability_adj 基线 {sorted(base_adj)} vs chunk {sorted(chunk_adj)}")
        for field in ("bio_type", "size", "speed", "senses"):
            bv = (d.get(field) or "").strip()
            cv = (md.get(field) or "").strip()
            if bv and cv != bv:
                ok = False
                issues.append(f"❌ {zh}: {field} 基线 '{bv}' vs chunk '{cv}'")
        checked += 1
    print(f"  — 六字段比对 {checked}/{len(rows)} 种族")
    if not issues:
        print("  — 六字段全一致（ability_adj 数值集排序口径）")
    return ok, issues


# ============================================================
#  检查 4：title 合法性
# ============================================================

_URL_IN_TITLE = re.compile(r"https?://")
# 纯译者标记：title 恰为"译者"/"校对"整词，或含"译者："/"翻译："标签前缀
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
    if empty:
        ok = False
        issues.append(f"❌ {len(empty)} 个空 title")
    if url:
        issues.append(f"⚠️  {len(url)} 个 title 含 URL（未整理页遗留，不阻断）")
    if trans:
        issues.append(f"⚠️  {len(trans)} 个 title 含译者标记（未整理页遗留，不阻断）")
    if noise:
        issues.append(f"⚠️  {len(noise)} 个 title 含格式噪声（未整理页遗留，不阻断）")
    return ok, issues


# ============================================================
#  检查 5：字段健康度
# ============================================================

# 11 枚举（format 层 kind 全集 + D 簇 race_sidebar→monster_block 替换，见
# processors/race.py:356；formats/race.py docstring 的「12 枚举」为笔误）
VALID_COMPONENT = {
    "race_overview", "race_trait", "race_archetype", "race_intro", "race_sidebar",
    "alt_trait", "fcb_entry", "race_item", "race_feat", "race_spell", "monster_block",
}
VALID_FORMAT = {"A", "B", "C", "D", "E", "F", "G"}


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

    fmt_dist = Counter(c.get("metadata", {}).get("format_cluster") for c in chunks)
    comp_dist = Counter(c.get("component_type") for c in chunks)
    print(f"  — format_cluster: {dict(fmt_dist)}")
    print(f"  — component_type: {dict(comp_dist)}")
    return ok, issues


# ============================================================
#  检查 6：alt_trait replaces 非空率
# ============================================================

# 阈值（#100 量化）：当前 371/426 = 87.1%；missing 含「改变属性调整」等
# 无替换语义的合理缺省（如 page_1456 灵巧），只收窄不放宽 → 85%
MIN_REPLACES_RATE = 0.85


def check_alt_trait_replaces(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """alt_trait replaces 非空率：field_status.replaces == parsed 比率 ≥ 阈值。

    哨兵行（**此特性替换XXX**）→ metadata.replaces；field_status 记录
    parsed/missing 两态。率过低说明哨兵行解析回归（alt_trait 语义=替换
    种族特性，大多数条目应带 replaces）。
    """
    alt = [c for c in chunks if c.get("component_type") == "alt_trait"]
    if not alt:
        return True, []
    parsed = sum(1 for c in alt if c.get("metadata", {}).get("field_status", {}).get("replaces") == "parsed")
    rate = parsed / len(alt)
    print(f"  — alt_trait {len(alt)} 个，replaces parsed {parsed} = {rate:.1%}（阈值 {MIN_REPLACES_RATE:.0%}）")
    if rate < MIN_REPLACES_RATE:
        missing = [c["title"] for c in alt if c.get("metadata", {}).get("field_status", {}).get("replaces") != "parsed"]
        return False, [f"❌ alt_trait replaces 非空率 {rate:.1%} < {MIN_REPLACES_RATE:.0%}（哨兵行解析回归？）示例: {missing[:8]}"]
    return True, []


# ============================================================
#  检查 7：page_11 汇总页行级召回（KN130 防回归）
# ============================================================

# page_11 两表（起始年龄/身高体重）数据行首格组别词（合并单元格，
# 每组仅首行出现；表 1 与表 2 同构——`| 核心种族 | 矮人 | 40岁 | … |`）
_PAGE11_GROUP_WORDS = {"核心种族", "常见种族", "其他种族", "罕见种族", "怪物种族"}


def _page11_race_names(source_text: str) -> Set[str]:
    """page_11 汇总页两表数据行族名提取。

    KN130 教训（2026-08-04）：doc 级召回 37 族 100% 不覆盖行级静默丢失
    ——矮人/神裔/替换儿 3 族整行未产 chunk。此处逐数据行提取族名与
    race_overview title 对账。组别词在首格 → 族名在次格（组别为合并
    单元格，每组仅首行出现）；否则族名在首格。表头/标题/分隔行
    （种族/成年/基本身高/---）无岁/尺特征天然排除。
    """
    names: Set[str] = set()
    for line in source_text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        if "岁" in line or "尺" in line:
            if cells[0] in _PAGE11_GROUP_WORDS:
                names.add(cells[1])
            else:
                names.add(cells[0])
    return names


# page_11 行级召回：复用共享层「源表数据行 ↔ chunk title」对账构建器
check_page11_row_recall = make_row_recall_check(
    name="page_11 行级召回",
    src_path=Path("pf_rules_md_organized/种族/page_11.md"),
    row_extractor=_page11_race_names,
    component_type="race_overview",
    pass_msg="源表数据行族名全命中（KN130 防回归）",
)[1]


# ============================================================
#  检查 8：page_752 component_type 全 alt_trait（KN131 防回归）
# ============================================================


def check_page752_component_type(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """page_752（ISR 核心替换特性页文件）component_type 全为 alt_trait。

    KN131 教训（2026-08-04）：M22 只修聚合文件漏页文件——同内容页文件
    52 条全标 race_trait。页文件无 intro/组标题时状态机默认态误标，
    此检查锁死「页文件条目 = alt_trait」口径。
    """
    p752 = [c for c in chunks if str(c.get("doc_id", "")) == "page_752"]
    if not p752:
        print("  — page_752 无 chunk（跳过）")
        return True, []
    bad = [c["title"] for c in p752 if c.get("component_type") != "alt_trait"]
    print(f"  — page_752 {len(p752)} 条，非 alt_trait {len(bad)} 条")
    if bad:
        return False, [f"❌ page_752 {len(bad)} 条非 alt_trait（M22 同口径回归？）: {bad[:8]}"]
    return True, []


# ============================================================
#  检查 9：race_name 实体枚举合法性（B2 产出即检/verify 常驻）
# ============================================================


def load_entity_enum(path: Path) -> Set[str]:
    """加载 race 实体枚举，返回有效 race_name 集合（实体名 ∪ 别名 ∪ 豁免）。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    valid: Set[str] = set()
    for ent in data.get("entities", []):
        valid.add(ent["name"])
        valid.update(ent.get("aliases", []))
    for ex in data.get("exemptions", []):
        valid.add(ex["value"])
    return valid


def check_race_name_enum(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
    """race_name 必须属于 entity_enum.json 的（实体名 ∪ 别名 ∪ 豁免）。

    空 race_name（概述页组标题等合法落空）跳过；非空值未命中 → FAIL。
    """
    valid = ctx.get("entity_enum_set", set())
    bad = []
    for c in chunks:
        rn = (c.get("metadata") or {}).get("race_name", "")
        if not rn:
            continue
        if rn not in valid:
            bad.append((c.get("chunk_id", "?"), rn))
    print(f"  — 非空 race_name {sum(1 for c in chunks if (c.get('metadata') or {}).get('race_name'))} 个 → 命中 {len(bad)} 条违规")
    if bad:
        samples = ", ".join(f"{cid}={rn!r}" for cid, rn in bad[:10])
        return False, [f"❌ race_name 未命中枚举/豁免 {len(bad)} 条（示例: {samples}）"]
    return True, []


# ============================================================
#  类目装配（VerifyBase 模板）
# ============================================================


class RaceVerify(VerifyBase):
    name = "种族集成验收"
    description = "种族集成验收（#100）"
    DEFAULT_CHUNKS = DEFAULT_CHUNKS

    checks = [
        ("判别器回归", check_discriminator_regression, "无 est>0 静默丢失"),
        ("召回", check_recall, "37 种族全命中"),
        ("六字段规范化比对", check_six_field_consistency, "基线六字段全一致"),
        ("title 合法性", check_title_health, "title 全合法"),
        ("字段健康度", check_field_health, "字段全健康"),
        ("alt_trait replaces 非空率", check_alt_trait_replaces, f"replaces 非空率 ≥ {MIN_REPLACES_RATE:.0%}"),
        ("page_11 行级召回", check_page11_row_recall, "源表数据行族名全命中（KN130 防回归）"),
        ("page_752 component_type", check_page752_component_type, "page_752 全 alt_trait（KN131 防回归）"),
        ("race_name 实体枚举", check_race_name_enum, "race_name 全在枚举或豁免内（B2）"),
    ]

    def add_args(self, parser):
        parser.add_argument("--matrix", default=DEFAULT_MATRIX, type=Path)
        parser.add_argument("--baseline", default=DEFAULT_BASELINE, type=Path)
        parser.add_argument("--enum", default=DEFAULT_ENUM, type=Path)

    def prepare(self, args):
        self.ctx["matrix"] = load_matrix(args.matrix)
        self.ctx["baseline_path"] = args.baseline
        self.ctx["entity_enum_set"] = load_entity_enum(args.enum)
        print(f"加载 {len(self.ctx['matrix'])} rel 矩阵（JSONL，est 字段 estimated_count）")
        print(f"加载实体枚举 {args.enum}：有效值 {len(self.ctx['entity_enum_set'])} 个")


def main():
    RaceVerify().main()


if __name__ == "__main__":
    main()
