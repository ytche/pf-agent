"""list_export.py — D2 权威清单导出共用模块（方案：数据侧产物增强 20260917 D2）

feat/race/equipment 三模块权威清单导出的单一事实源；三个根级独立脚本
（feat_list_export.py / race_list_export.py / equipment_list_export.py，
与 spell_list_export.py 同待遇：独立脚本、不挂 pipeline finalize）只做
类目参数装配，本模块承载全部逻辑：

  - 数据源 = 各类目 chunks.jsonl（不回读 CHM 源 md，方案拍板）
  - 自描述 header：version / generated_from / source_fingerprint（chunks.jsonl
    内容 sha256，代替时间戳——保幂等，重跑字节一致，验收 D2.7）/ category
  - 条目 = 主条目 component_type 全量（title/别名/book/chunk_id 等枚举字段）
  - KN235-① 清洗（仅 equipment）：table_candidates 净增补机制产生的
    表格碎片标题（page_210/page_211 共 33 条，登记 KN235 遗留观察①）
    在导出层 sink 回所属价目表章节/条目——不独立出现在清单 entries；
    chunks.jsonl 本身不动。检测全部用通用规则（标题形态特征 + 来源机制
    标记：单表格行 text），禁止 chunk_id 特判
  - verify 软检查构建器 make_list_soft_check（WARN 不阻断，方案拍板）
  - AKN-025 价格表类别补全（include_price_tables，仅 equipment）：
    parse_price_table_entries 从价格表行生成法杖/权杖/戒指/奇物等条目，
    chunk_id 指向来源价格表 chunk；parse_price_gp 把 price 原文归一为
    可空整数 price_gp（解析失败条目保留并计入导出报告）；报告按来源表
    逐表对账（sources）并保留同名不同价/不同来源行（name_conflicts）

文本工具 fold_ws/fold_lower 自 spell_list_export.py 收敛至此（方案 D2
「抽出共用模块」），四个导出脚本同源复用。
"""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

VERSION = "1.0"


# ---------------------------------------------------------------- AKN-025
# 价格表类别（AKN-025）：只以价目表形式出现的装备类别。清单条目不由描述
# chunk 直出，而由表行生成；chunk_id 指向来源价格表 chunk（溯源口径依赖）。
# 类别键为中英文表头/表题里的类目词，值为清单 component_type。
PRICE_TABLE_CATEGORIES: Tuple[Tuple[str, str], ...] = (
    ("法杖", "staff"),
    ("权杖", "rod"),
    ("戒指", "ring"),
    ("魔杖", "wand"),
    ("卷轴", "scroll"),
    ("药水", "potion"),
    ("药剂", "potion"),
    ("奇物", "wondrous_item"),
)

_PRICE_LABEL = re.compile(r"^(价格|价钱|price)(?:[（(][^）)]*[）)])?$", re.I)
_PRICE_GP = re.compile(
    r"^([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\s*(gp|金币|金|pp)[。.;；]?$", re.I)
_PRICE_GP_BARE = re.compile(
    r"^([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\s*(gp|金币|金|pp)?[。.;；]?$", re.I)
_PRICE_TABLE_TYPES = {component for _, component in PRICE_TABLE_CATEGORIES}
_NAME_EN = re.compile(r"^(.*?)\s*[（(]([^（）()]*[A-Za-z][^（）()]*)[）)]$")
_BOOK_ABBR = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,5}$")
_VARIANT_NAME = re.compile(r"^[A-Za-z0-9IVXLC]{1,4}$")
_STAT_HEADER = re.compile(
    r"^(重量.*|CL|环位|等级|形状|灵光|效果|共振|制造需求|价格.*|\d+d\d+)$", re.I)
_VARIANT_LABELS = {"破损的", "缺陷的"}
_NAME_LABELS = {"名称", "物品", "名称（item）", "物品（item）",
                "名称(item)", "物品(item)"}


def parse_price_gp(raw, *, allow_bare: bool = False) -> Optional[int]:
    """价格原文 → 可空整数 gp（AKN-025）：gp/金币口径，pp 按 10gp 折算。

    sp/cp/区间/可变/空/非数值（`-`、`—`、`+1500 GP` 等）一律返回 None，
    条目保留但不参与价格排序/过滤（排序在 Java 清单查询侧按 price_gp）。
    allow_bare：价格表内裸数字按 gp 计（CRB 价目表惯例，如 `| 矮人腰带 | 14,900 |`）。
    """
    if raw is None:
        return None
    s = fold_ws(str(raw).replace("\ufeff", "")).replace("，", ",")
    pattern = _PRICE_GP_BARE if allow_bare else _PRICE_GP
    m = pattern.fullmatch(s)
    if not m:
        return None
    try:
        amount = int(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return amount * 10 if (m.group(2) or "").lower() == "pp" else amount


def _table_cells(line: str) -> List[str]:
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") else s
    return [c.replace("\ufeff", "").strip() for c in s.split("|")]


def _table_blocks(text: str) -> List[List[str]]:
    """按连续 markdown 表格行切块（表题行 `| 表：X |` 同属该块）。"""
    blocks: List[List[str]] = []
    cur: List[str] = []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            cur.append(line)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    return blocks


def _price_table_category(text: str) -> Optional[str]:
    """表题/表头中的类目词 → component_type；取文本中最先出现的类目词。"""
    best: Optional[Tuple[int, str]] = None
    for keyword, component in PRICE_TABLE_CATEGORIES:
        pos = text.find(keyword)
        if pos >= 0 and (best is None or pos < best[0]):
            best = (pos, component)
    return best[1] if best else None


def _split_name(raw: str) -> Tuple[str, str]:
    """`祝福之杖 (Staff of Blessed Relief)` → (中文名, 英文名)。"""
    name = fold_ws(raw)
    m = _NAME_EN.match(name)
    if m and m.group(1).strip():
        return m.group(1).strip(), fold_ws(m.group(2))
    return name, ""


def _name_column(header: List[str], price_col: int) -> Optional[int]:
    """价格列 → 名称列：就近非空表头；就近列是数值/度量列时扩到段首。

    - `法杖 | | 价格 | ...`：就近 `法杖` 即名称列（双栏并排表各取各的）
    - `无位置 | 价格 | | 出处 | 无位置 | 价格 |`：就近块标题即名称列
    - `项链类型 | 10d6 | ... | 价格` / `星象仪 Orreries | 重量 | 价格`：
      就近是骰数/重量等数值列，扩到连续表头段最左列（名称列）
    """
    j = next((i for i in range(price_col - 1, -1, -1) if header[i]), None)
    if j is None:
        return None
    if _STAT_HEADER.match(header[j]):
        while j > 0 and header[j - 1]:
            j -= 1
    return j


def parse_price_table_entries(chunk: dict) -> List[dict]:
    """从一个 chunk 的价格表行生成清单条目（AKN-025）。

    只认带价格列表头（`价格`/`价钱`/`价格（GP）`）的表；类目优先取表题/
    表头类目词（法杖/权杖/戒指/奇物等），其次取 chunk component_type
    （staff/rod/ring/wondrous_item 等价格表类别 chunk 内的表全部按该类目），
    最后才用 chunk 标题补判。行内按表头定位名称列（见 _name_column）与出处
    列（价格列右侧最近非空单元，命中书缩写时作为条目 book）；表内裸数字
    价格按 gp 计，短变体名（`I`/`X10`）补 chunk 标题前缀。空价格但名称有效
    的表行同样保留（price=""、price_gp=null），不参与排序。chunk_id 固定为
    表格所在 chunk，供检索溯源命中来源价目表。
    """
    chunk_book = chunk.get("book_abbreviation") or ""
    chunk_book_cn = chunk.get("book_name_cn") or ""
    chunk_title = fold_ws(chunk.get("title") or "")
    rows: List[dict] = []
    for block in _table_blocks(chunk.get("text") or ""):
        header_idx = next(
            (i for i, line in enumerate(block)
             if any(_PRICE_LABEL.match(c) for c in _table_cells(line))), None)
        if header_idx is None:
            continue
        header = _table_cells(block[header_idx])
        price_idx = [i for i, c in enumerate(header) if _PRICE_LABEL.match(c)]
        category = _price_table_category(" ".join(block[:header_idx + 1]))
        if category is None and chunk.get("component_type") in _PRICE_TABLE_TYPES:
            category = chunk["component_type"]
        if category is None:
            category = _price_table_category(chunk_title)
        if category is None:
            continue
        name_idx = {p: _name_column(header, p) for p in price_idx}
        last_name = {p: "" for p in price_idx}
        for line in block[header_idx + 1:]:
            cells = _table_cells(line)
            for p in price_idx:
                if p >= len(cells):
                    continue
                price = fold_ws(cells[p])
                if _PRICE_LABEL.match(price):
                    continue  # 分组/表头行（`次等中级权杖 | 价格`）
                # 空价格但有有效名称的行仍保留（price=""、price_gp=null），
                # 如艾恩石 破损的/缺陷的 变体行（无标价，不参与排序）
                n_idx = name_idx[p]
                if n_idx is None or n_idx >= len(cells) or not cells[n_idx]:
                    continue
                name, name_en = _split_name(cells[n_idx])
                if not name or name in _NAME_LABELS:
                    continue
                if name in _VARIANT_LABELS and last_name[p]:
                    # 破损的/缺陷的 等变体行承接上一条目的名称（如艾恩石）
                    name = f"{last_name[p]}（{name}）"
                elif name not in _VARIANT_LABELS:
                    last_name[p] = name
                if chunk_title and _VARIANT_NAME.match(name) and name not in chunk_title:
                    name = f"{chunk_title} {name}"
                source = ""
                for j in range(p + 1, min(p + 3, len(cells))):
                    if cells[j]:
                        source = fold_ws(cells[j])
                        break
                book = source if _BOOK_ABBR.match(source) else chunk_book
                rows.append({
                    "name": name,
                    "name_en": name_en,
                    "book": book,
                    "book_name_cn": chunk_book_cn if book == chunk_book else "",
                    "component_type": category,
                    "chunk_id": chunk.get("chunk_id") or "",
                    "doc_id": chunk.get("doc_id") or "",
                    "aliases": [],
                    "price": price,
                    "price_gp": parse_price_gp(price, allow_bare=True),
                    "weight": "",
                    "slot": "",
                })
    return rows


# ---------------------------------------------------------------- 文本工具
# （spell_list_export.fold_ws/fold_lower 同源收敛，改这里四处生效）

def fold_ws(s: str) -> str:
    """折叠任意空白（含 \\r/\\n/多空格）为单个空格并收尾。"""
    return re.sub(r"\s+", " ", s).strip()


def fold_lower(s: str) -> str:
    """交叉匹配键：小写 + 去所有空白（对英文名折行/大小写差异鲁棒）。"""
    return re.sub(r"\s+", "", s).lower()


# ---------------------------------------------------------------- 载入/指纹

def load_chunks(path) -> List[dict]:
    path = Path(path)
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- KN235-①
# table_candidates 净增补碎片检测（equipment 导出层清洗，通用规则）：
#
# 来源机制标记：fragment 的 text 是单行 markdown 表格行（净增补补切条目的
# 定义特征——text = 表格行原文）。形态特征（命中任一即碎片）：
#   colon   首格含 ：/: 的分组行（page_210 `类型：普通` 等）——但标题以
#           散文/章节标记前缀开头（表格/表：/变体规则/边栏/特殊材质）的
#           正文段/表格标题行除外
#   semi    首格含 ；/; 的单位行/变体行（`饲料；每日`/`凶暴蝙蝠；战斗训练`）
#   size    首格括号英文纯体型分类词（Medium creature 等马具尺寸分组行）
#   vehicle (轻型|中型|重型)(战车|货车) 交通工具分组行
#   header  行内其余格全为表头标签词（`食物 | 价格 | 重量（磅）`）
#   prefix  品质前缀（普通|高品质）开头的无英文名单行行
# 全库实证恰好命中 KN235-① 登记的 33 条（page_210×24 + page_211×9），
# 零误伤（各规则命中集见 tests/test_list_exports.py 钉住）。

_SECTION_MARKER_PREFIXES = ("表格", "表：", "变体规则", "边栏", "特殊材质")
_SIZE_EN = re.compile(
    r"^(Fine|Diminutive|Tiny|Small|Medium|Large|Huge|Gargantuan|Colossal)"
    r"( (creature|or (Fine|Diminutive|Tiny|Small|Medium|Large|Huge|Smaller|Larger)))?$",
    re.I,
)
_VEHICLE_GROUP = re.compile(r"^(轻型|中型|重型)(战车|货车)$")
_QUALITY_PREFIX = re.compile(r"^(普通|高品质)")
_HEADER_LABELS = {"价格", "重量", "出处", "价格（gp）", "价格（GP）", "重量(磅)", "重量（磅）"}


def table_fragment_reason(chunk: dict) -> Optional[str]:
    """table_candidates 净增补碎片判定 → 规则名；非碎片返回 None。

    通用规则：text 为单行 markdown 表格行（来源机制标记）+ 标题形态特征。
    """
    title = (chunk.get("title") or "").strip()
    if not title:
        return None
    lines = [ln for ln in (chunk.get("text") or "").strip().splitlines() if ln.strip()]
    if len(lines) != 1 or not lines[0].lstrip().startswith("|"):
        return None  # 非单表格行（净增补补切条目的机制标记）不判碎片
    cells = [c.strip() for c in lines[0].strip("|").split("|")]
    first = cells[0] if cells else ""
    if "：" in title or ":" in title:
        if any(title.startswith(p) for p in _SECTION_MARKER_PREFIXES):
            return None
        return "colon_group_row"
    if "；" in title or ";" in title:
        return "semi_unit_row"
    m = re.search(r"[（(]([^（）()]+)[）)]", first)
    if m and _SIZE_EN.match(m.group(1).strip()):
        return "size_group_row"
    if _VEHICLE_GROUP.match(title):
        return "vehicle_group_row"
    rest = [c for c in cells[1:] if c]
    if rest and all(re.sub(r"[（(].*$", "", c) in _HEADER_LABELS for c in rest):
        return "table_header_row"
    if not re.search(r"[A-Za-z]", title) and _QUALITY_PREFIX.match(title):
        return "quality_prefix_row"
    return None


def _find_sink_target(fragment: dict, by_doc: Dict[str, List[dict]],
                      fragment_ids: Set[str]) -> Optional[dict]:
    """碎片行归属：同 doc 内 text 含碎片整行的唯一非碎片 chunk（sink 保真目标）。"""
    row = (fragment.get("text") or "").strip()
    cands = [
        c for c in by_doc.get(fragment.get("doc_id") or "", [])
        if c.get("chunk_id") not in fragment_ids and row and row in (c.get("text") or "")
    ]
    return cands[0] if len(cands) == 1 else None


# ---------------------------------------------------------------- 条目构建

def build_base_entry(chunk: dict, name_en: str = "", extras: Optional[dict] = None) -> dict:
    entry = {
        "name": (chunk.get("title") or "").strip(),
        "name_en": name_en or "",
        "book": chunk.get("book_abbreviation") or "",
        "book_name_cn": chunk.get("book_name_cn") or "",
        "component_type": chunk.get("component_type") or "",
        "chunk_id": chunk.get("chunk_id") or "",
        "doc_id": chunk.get("doc_id") or "",
        "aliases": [str(a) for a in (chunk.get("aliases") or [])],
    }
    if extras:
        entry.update(extras)
    return entry


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 主流程

def export_list(*, category: str, out_dir: str, main_types: Set[str],
                extra_fields: Optional[Callable[[dict, dict], dict]] = None,
                min_entries: int = 0, clean_table_fragments: bool = False,
                expected_fragments: Optional[int] = None,
                include_price_tables: bool = False) -> dict:
    """从 chunks.jsonl 导出权威清单 JSON + 对账报告；返回对账摘要。

    幂等：无时间戳，重跑字节一致。自校验断言：条目数 ≥ min_entries、
    无空 name、(chunk_id, name) 无重复、无 excluded component_type 混入、
    KN235-① 碎片全部 sink（clean_table_fragments 时，exact expected）。

    include_price_tables（AKN-025，仅 equipment）：额外从价格表行生成
    法杖/权杖/戒指/奇物等类别条目，chunk_id 指向来源价格表 chunk；
    报告含类目计数与 price_gp 解析成功/失败统计及失败样本。
    """
    out = Path(out_dir)
    chunks_path = out / "chunks.jsonl"
    chunks = load_chunks(chunks_path)
    fingerprint = sha256_file(chunks_path)

    table_types = ({c for _, c in PRICE_TABLE_CATEGORIES}
                   if include_price_tables else set())
    present_types = {c.get("component_type") or "" for c in chunks}
    excluded = sorted(present_types - main_types - table_types)
    by_doc: Dict[str, List[dict]] = {}
    for c in chunks:
        by_doc.setdefault(c.get("doc_id") or "", []).append(c)

    fragments: List[dict] = []
    fragment_ids: Set[str] = set()
    sink_of: Dict[str, str] = {}  # fragment chunk_id -> sink target chunk_id
    if clean_table_fragments:
        fragments = [c for c in chunks
                     if c.get("component_type") in main_types
                     and table_fragment_reason(c)]
        fragment_ids = {c.get("chunk_id") for c in fragments}
        for frag in fragments:
            target = _find_sink_target(frag, by_doc, fragment_ids)
            if target is not None:
                sink_of[frag["chunk_id"]] = target["chunk_id"]

    entries: List[dict] = []
    sections: List[dict] = []
    entry_by_id: Dict[str, dict] = {}
    for c in chunks:
        cid = c.get("chunk_id")
        if c.get("component_type") not in main_types or cid in fragment_ids:
            continue
        md = c.get("metadata") or {}
        entry = build_base_entry(
            c, name_en=str(md.get("english_name") or md.get("race_name_en") or ""),
            extras=extra_fields(c, md) if extra_fields else None,
        )
        entries.append(entry)
        entry_by_id[cid] = entry

    # AKN-025：价格表类别条目（chunk_id = 来源价格表 chunk）。只去掉表内
    # 完全相同的重复行（chunk_id+name+price+book 全同）；同名不同价/不同来源
    # 的真实表行全部保留，冲突进报告（name_conflicts）供溯源。
    table_entries: List[dict] = []
    if include_price_tables:
        seen_rows: Set[Tuple[str, str, str, str]] = set()
        for c in chunks:
            for entry in parse_price_table_entries(c):
                key = (entry["chunk_id"], entry["name"], entry["price"], entry["book"])
                if key in seen_rows:
                    continue
                seen_rows.add(key)
                table_entries.append(entry)
        entries.extend(table_entries)

    # KN235-① sink 回写：目标为主条目 → 挂 entries.sunk_table_fragments；
    # 目标为章节条目（equipment_intro 等）→ JSON sections 数组承载，价格数据
    # 在清单内仍可从所属价目表章节条目找到
    section_by_id: Dict[str, dict] = {}
    frag_by_id = {c.get("chunk_id"): c for c in fragments}
    for frag_id, target_id in sink_of.items():
        frag = frag_by_id[frag_id]
        frag_payload = {
            "chunk_id": frag_id,
            "title": (frag.get("title") or "").strip(),
            "reason": table_fragment_reason(frag),
            "rows": (frag.get("text") or "").strip(),
        }
        host = entry_by_id.get(target_id)
        if host is None:
            target = next(c for c in by_doc.get(frag.get("doc_id"), [])
                          if c.get("chunk_id") == target_id)
            host = section_by_id.get(target_id)
            if host is None:
                host = build_base_entry(target)
                sections.append(host)
                section_by_id[target_id] = host
        host.setdefault("sunk_table_fragments", []).append(frag_payload)

    by_book = Counter(e["book"] for e in entries)
    stats = {
        "total": len(entries),
        "by_book": dict(sorted(by_book.items())),
        "by_component_type": dict(sorted(Counter(
            e["component_type"] for e in entries).items())),
        "chunk_id_null": sum(1 for e in entries if not e["chunk_id"]),
    }
    report: dict = {
        "category": category,
        "generated_from": str(chunks_path),
        "issues": [],
        "fragments_sunk": len(sink_of),
        "fragments_unsunk": sorted(
            f["chunk_id"] for f in fragments if f["chunk_id"] not in sink_of),
    }
    if include_price_tables:
        stats["price_table_entries"] = len(table_entries)
        failed = [e for e in entries if e.get("price_gp") is None]
        # 失败样本优先展示有价原文（解析失败），无标价（空串）排后
        samples = sorted(failed, key=lambda e: not e.get("price"))[:20]
        stats["price_gp"] = {
            "parsed": len(entries) - len(failed),
            "failed": len(failed),
        }
        sources = Counter(e["chunk_id"] for e in table_entries)
        conflicts: Dict[Tuple[str, str], List[dict]] = {}
        for e in table_entries:
            conflicts.setdefault((fold_lower(e["name"]), e["book"]), []).append(e)
        report["price_tables"] = {
            "categories": dict(sorted(Counter(
                e["component_type"] for e in table_entries).items())),
            # 逐源价格表对账：每个来源 chunk 导出的行数（与 entries 可核）
            "sources": [
                {"chunk_id": cid, "rows": n} for cid, n in sorted(sources.items())
            ],
            # 同名同书多行（不同价/不同来源）：保留全部，此处可溯源
            "name_conflicts": [
                {"name": group[0]["name"], "book": book,
                 "rows": [{"chunk_id": e["chunk_id"], "price": e["price"],
                           "price_gp": e["price_gp"],
                           "component_type": e["component_type"]}
                          for e in group]}
                for (_, book), group in sorted(conflicts.items())
                if len(group) > 1
            ],
            "price_gp": {
                **stats["price_gp"],
                "failed_samples": [
                    {"name": e["name"], "price": e["price"],
                     "chunk_id": e["chunk_id"],
                     "component_type": e["component_type"]}
                    for e in samples
                ],
            },
        }
    if clean_table_fragments:
        stats["fragments_sunk"] = len(sink_of)
        stats["fragments_excluded"] = len(fragments)
        report["fragments"] = [
            {"chunk_id": f.get("chunk_id"), "title": (f.get("title") or "").strip(),
             "reason": table_fragment_reason(f),
             "sink_target": sink_of.get(f.get("chunk_id"))}
            for f in fragments
        ]

    payload = {
        "version": VERSION,
        "generated_from": str(chunks_path),
        "source_fingerprint": f"sha256:{fingerprint}",
        "category": category,
        "entries": entries,
        "excluded_component_types": excluded,
        "stats": stats,
    }
    if sections:
        payload["sections"] = sections

    # ---- 自校验断言 ----
    assert len(entries) >= min_entries, (
        f"{category} 清单条目数 {len(entries)} < 下界 {min_entries}")
    assert all(e["name"] for e in entries), f"{category} 清单存在空 name"
    keys = [(e["chunk_id"], e["name"], e.get("price", "")) for e in entries if e["chunk_id"]]
    assert len(keys) == len(set(keys)), f"{category} 清单同 chunk 同名同价行重复"
    assert all(e["component_type"] in main_types | table_types for e in entries), \
        f"{category} 清单混入 excluded component_type"
    if clean_table_fragments:
        assert not report["fragments_unsunk"], (
            f"KN235-① 碎片未找到唯一 sink 目标: {report['fragments_unsunk']}")
        if expected_fragments is not None:
            assert len(fragments) == expected_fragments, (
                f"KN235-① 碎片检出 {len(fragments)} 条 != 登记 {expected_fragments} 条"
                "——table_candidates 形态漂移，需人工复核检测规则")

    json_path = out / f"{category}_lists.json"
    report_path = out / f"{category}_list_export_report.json"
    _write_json(json_path, payload)
    report["summary"] = {"entries": len(entries), "by_book": stats["by_book"]}
    _write_json(report_path, report)
    print(f"{category} 清单: {len(entries)} 条（excluded types: {excluded}）"
          + (f"，KN235-① 碎片 sink {len(sink_of)}/{len(fragments)}" if clean_table_fragments else ""))
    print(f"产物 → {json_path}；对账报告 → {report_path}")
    return report["summary"]


# ---------------------------------------------------------------- verify 软检查

def make_list_soft_check(display: str, json_path: str, min_total: int):
    """D2 清单产物软检查（WARN 不阻断，方案拍板）：文件缺失 / version 不符 /
    条目数低于下界只打 WARN，check 永远通过（导出脚本独立运行，防环依赖）。
    """
    def fn(chunks: List[dict], ctx: dict):
        p = Path(json_path)
        if not p.is_file():
            print(f"  ⚠️  WARN 不阻断: {json_path} 缺失——D2 导出脚本独立运行"
                  f"（python3 {Path(json_path).stem.replace('_lists','')}_list_export.py）")
            return True, []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  ⚠️  WARN 不阻断: {json_path} 非合法 JSON: {e}")
            return True, []
        warns = []
        if data.get("version") != VERSION:
            warns.append(f"version={data.get('version')!r} != {VERSION!r}")
        total = (data.get("stats") or {}).get("total", 0)
        if not isinstance(total, int) or total < min_total:
            warns.append(f"stats.total={total} < 下界 {min_total}")
        for w in warns:
            print(f"  ⚠️  WARN 不阻断: {json_path}: {w}")
        if not warns:
            print(f"  — version={data.get('version')}，条目 {total} ≥ {min_total}")
        return True, []

    return (display, fn, "D2 清单产物软检查通过（缺失/不符仅 WARN 不阻断）")
