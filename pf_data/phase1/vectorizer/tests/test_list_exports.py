"""D2 权威清单导出白盒测试（方案：数据侧产物增强 20260917 §D2）

覆盖 feat/race/equipment 三份清单 JSON（feat_list_export.py / race_list_export.py /
equipment_list_export.py，独立脚本同 spell_list_export 先例，共用逻辑在
vectorizer/list_export.py）：

  - schema/header 自描述字段（version/generated_from/source_fingerprint/category）
  - 条目数与 chunks.jsonl 主条目口径一致；无空 name；chunk_id 唯一无重复；
    无 excluded component_type 混入
  - KN235-① 清洗：33 条表格碎片标题不独立出现在 entries，且每条的表格行
    数据可在所属 sink 目标（entries 或 sections 的 sunk_table_fragments）找到
  - 幂等：重跑字节一致（验收 D2.7）
  - verify 软检查构建器：缺失仅 WARN 不阻断

测试内运行导出脚本（subprocess，cwd=phase1，与 manifest command 同源）。
产物缺失（CI 裸 checkout，chunks.jsonl gitignored）时按 test_per_file_chunk_counts.py
先例 skip：产物断言由 build all 编排的 chunks 步现跑生成 + build check 对账覆盖。
"""
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from vectorizer.list_export import parse_price_gp

PHASE1 = Path(__file__).resolve().parents[2]

CASES = {
    "feat": {
        "script": "feat_list_export.py",
        "json": "vectorizer/output/专长/feat_lists.json",
        "report": "vectorizer/output/专长/feat_list_export_report.json",
        "chunks": "vectorizer/output/专长/chunks.jsonl",
        "main_types": {"feat"},
    },
    "race": {
        "script": "race_list_export.py",
        "json": "vectorizer/output/种族/race_lists.json",
        "report": "vectorizer/output/种族/race_list_export_report.json",
        "chunks": "vectorizer/output/种族/chunks.jsonl",
        "main_types": {"race_overview"},
    },
    "equipment": {
        "script": "equipment_list_export.py",
        "json": "vectorizer/output/装备/equipment_lists.json",
        "report": "vectorizer/output/装备/equipment_list_export_report.json",
        "chunks": "vectorizer/output/装备/chunks.jsonl",
        # 主条目族（含无标价神器/诅咒物品）+ AKN-025 价格表类别
        "main_types": {"gear", "weapon", "armor", "artifact", "cursed_item"}
                      | {"staff", "rod", "ring", "wondrous_item"},
    },
}

PRICE_TABLE_TYPES = {"staff", "rod", "ring", "wondrous_item"}
DIRECT_TYPES = {"gear", "weapon", "armor", "artifact", "cursed_item"}

# ---------------------------------------------------------------- 独立对账
# 逐源预期表：纯测试侧维护，不导入被测实现的表切分/表头/名称列 helper。
# 键 = 来源价格表 chunk_id，值 = 按表格块顺序给出的 [(价格列, 名称列), ...]
# （人工核对 chunks.jsonl 表头）；块内行号/名称/价格由本文件的提取器独立产出。
SOURCE_TABLE_COLUMNS = {
    "equipment_UI奇物_0000": [[(1, 0)]],
    "equipment_page_1127_0000": [[(1, 0)]],
    "equipment_page_1127_0002": [[(1, 0)]],
    "equipment_page_1127_0012": [[], [(1, 0)]],  # 块 0 为 d% 表，无价格列
    "equipment_page_1128_0000": [[(1, 0)]],
    "equipment_page_1254_0005": [[(4, 0)]],
    "equipment_page_220_0000": [[(1, 0), (5, 4)]],
    "equipment_page_221_0001": [[(1, 0), (5, 4)]],
    "equipment_page_222_0000": [[(2, 0), (7, 5)]],
    "equipment_page_223_0000": [[(1, 0), (5, 4)]],
    "equipment_page_224_0000": [[(1, 0), (5, 4)]],
    "equipment_page_225_0000": [[(1, 0), (5, 4)]],
    "equipment_page_226_0000": [[(1, 0), (5, 4)]],
    "equipment_page_227_0000": [[(1, 0), (5, 4)]],
    "equipment_page_228_0000": [[(1, 0), (5, 4)]],
    "equipment_page_229_0000": [[(1, 0), (5, 4)]],
    "equipment_page_230_0000": [[(1, 0), (5, 4)]],
    "equipment_page_231_0000": [[(1, 0), (5, 4)]],
    "equipment_page_231_0034": [[(10, 0)]],
    "equipment_page_231_0060": [[(1, 0)]],
    "equipment_page_232_0000": [[(1, 0), (5, 4)]],
    "equipment_page_233_0000": [[(1, 0), (5, 4)]],
    "equipment_page_234_0000": [[(1, 0), (5, 4)]],
    "equipment_page_568_0000": [[(1, 0)]],
    "equipment_位面冒险PA_奇物_0001": [[(1, 0)]],
    "equipment_位面冒险PA_戒指_0001": [[(1, 0)]],
    "equipment_位面冒险PA_权杖_0001": [[(1, 0)]],
    "equipment_繁星子民PotS_奇物_0001": [[(2, 0)], [(3, 0)]],
}

_SRC_PRICE_HEADER = re.compile(r"^(价格|价钱|price)(?:[（(][^）)]*[）)])?$", re.I)
_SRC_PAREN_EN = re.compile(r"^(.*?)\s*[（(]([^（）()]*[A-Za-z][^（）()]*)[）)]$")
_SRC_SHORT_VARIANT = re.compile(r"^[A-Za-z0-9IVXLC]{1,4}$")
_SRC_VARIANT_LABELS = {"破损的", "缺陷的"}


def _src_fold(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\ufeff", "")).strip()


def _src_cells(line: str):
    return [_src_fold(c) for c in line.strip().strip("|").split("|")]


def _src_table_groups(text: str):
    """独立切分 Markdown 表格块，返回 [[(源行号, 原始行), ...], ...]。"""
    groups, cur = [], []
    for line_no, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("|"):
            cur.append((line_no, line))
        elif cur:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def _src_expected_rows(chunk: dict, specs) -> list:
    """按独立预期列位从源 Markdown 提取 (源行号, 名称, 价格原文) 集合。"""
    title = _src_fold(chunk.get("title") or "")
    groups = _src_table_groups(chunk.get("text") or "")
    assert len(groups) == len(specs), (chunk["chunk_id"], len(groups), len(specs))
    rows = []
    for group, block_spec in zip(groups, specs):
        if not block_spec:
            continue  # 无价格列的块（d% 表等）
        header_idx = next(
            (k for k, (_, line) in enumerate(group)
             if any(p < len(_src_cells(line))
                    and _SRC_PRICE_HEADER.match(_src_cells(line)[p])
                    for p, _ in block_spec)), None)
        if header_idx is None:
            continue
        prev = {}  # 名称列 -> 上一条目名（破损的/缺陷的 变体承接）
        for line_no, line in group[header_idx + 1:]:
            cells = _src_cells(line)
            for p, n in block_spec:
                if p >= len(cells) or n >= len(cells):
                    continue
                price = cells[p]
                if _SRC_PRICE_HEADER.match(price):
                    continue  # 表头/分组标题行
                raw = cells[n]
                if not raw:
                    continue
                m = _SRC_PAREN_EN.match(raw)
                name = m.group(1).strip() if m and m.group(1).strip() else raw
                if name in _SRC_VARIANT_LABELS:
                    name = f"{prev[n]}（{name}）" if prev.get(n) else name
                else:
                    prev[n] = name
                    if title and _SRC_SHORT_VARIANT.match(name) and name not in title:
                        name = f"{title} {name}"
                rows.append((line_no, p, name, price))
    return rows


def _require_product(spec: dict) -> None:
    """产物级集成测试守卫（同 test_per_file_chunk_counts.py 先例）：
    导出脚本输入是 chunks.jsonl（gitignored，CI 裸 checkout 拿不到，由
    build all 编排的 chunks 步现跑生成）。产物缺失时跳过——不改断言逻辑，
    产物齐全的本地环境仍全量执行；产物对账由 build check 承担。"""
    if not (PHASE1 / spec["chunks"]).is_file():
        pytest.skip(f"产物缺失: {spec['chunks']}（CI 裸 checkout；"
                    f"由 build all 的 chunks 步生成 + build check 对账覆盖）")


def _run_export(script: str) -> None:
    r = subprocess.run([sys.executable, script], cwd=PHASE1,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"{script} 失败:\n{r.stdout}\n{r.stderr}"


def _load_json(rel: str) -> dict:
    return json.loads((PHASE1 / rel).read_text(encoding="utf-8"))


def _load_chunks(rel: str) -> list:
    return [json.loads(l) for l in (PHASE1 / rel).read_text(encoding="utf-8").splitlines() if l.strip()]


@pytest.fixture(scope="module", params=sorted(CASES))
def case(request):
    spec = CASES[request.param]
    _require_product(spec)
    _run_export(spec["script"])
    return request.param, spec


@pytest.fixture(scope="module")
def price_table_data():
    _require_product(CASES["equipment"])
    _run_export(CASES["equipment"]["script"])
    return _load_json(CASES["equipment"]["json"])


@pytest.fixture(scope="module")
def price_table_report():
    _require_product(CASES["equipment"])
    return _load_json(CASES["equipment"]["report"])


class TestSchema:
    def test_header_self_describing(self, case):
        _, spec = case
        data = _load_json(spec["json"])
        assert data["version"] == "1.0"
        assert data["generated_from"] == spec["chunks"]
        assert data["category"] == case[0]
        # 来源 artifact 指纹 = chunks.jsonl 内容 sha256（代替时间戳，保幂等）
        digest = hashlib.sha256((PHASE1 / spec["chunks"]).read_bytes()).hexdigest()
        assert data["source_fingerprint"] == f"sha256:{digest}"
        stats = data["stats"]
        assert stats["total"] == len(data["entries"])
        assert stats["chunk_id_null"] == 0
        assert set(stats["by_component_type"]) <= spec["main_types"]

    def test_entry_fields(self, case):
        _, spec = case
        data = _load_json(spec["json"])
        for e in data["entries"]:
            for field in ("name", "name_en", "book", "book_name_cn",
                          "component_type", "chunk_id", "doc_id", "aliases"):
                assert field in e, f"条目缺字段 {field}: {e.get('chunk_id')}"
            assert e["name"]
            assert e["component_type"] in spec["main_types"]
        # AKN-025：chunk_id 指向来源价格表 chunk，同一 chunk 可承载多条条目；
        # 唯一性按 (chunk_id, name, price) 判定（同名不同价是真实表行，需保留）
        keys = [(e["chunk_id"], e["name"], e.get("price", "")) for e in data["entries"]]
        assert len(keys) == len(set(keys)), "同 chunk 同名同价行重复"

    def test_entry_count_matches_chunks(self, case):
        name, spec = case
        chunks = _load_chunks(spec["chunks"])
        data = _load_json(spec["json"])
        if name == "equipment":
            from vectorizer.list_export import table_fragment_reason
            # 主条目族由 chunk 直出；价格表类别条目来自表行，按报告计数对账
            direct = [c for c in chunks if c["component_type"] in DIRECT_TYPES]
            direct = [c for c in direct if not table_fragment_reason(c)]
            assert data["stats"]["total"] == \
                len(direct) + data["stats"]["price_table_entries"]
        else:
            main = [c for c in chunks if c["component_type"] in spec["main_types"]]
            assert data["stats"]["total"] == len(main)


class TestExtras:
    def test_feat_extras(self):
        _require_product(CASES["feat"])
        data = _load_json(CASES["feat"]["json"])
        assert data["stats"]["total"] >= 3600
        with_prereq = [e for e in data["entries"] if e.get("prerequisites_raw")]
        assert with_prereq, "prerequisites_raw 应有非空值"

    def test_race_extras(self):
        _require_product(CASES["race"])
        data = _load_json(CASES["race"]["json"])
        assert data["stats"]["total"] >= 100
        for e in data["entries"]:
            for field in ("race_group", "ability_adj", "bio_type", "size", "speed", "senses"):
                assert field in e, f"race 条目缺 {field}: {e['chunk_id']}"
        # 核心字段：page_11 种族汇总页 75 条为 KN130 登记 '?' 设计保留家族，
        # 允许缺值；其余条目 ability_adj 必须非空
        off_page11 = [e for e in data["entries"] if e["doc_id"] != "page_11"]
        assert off_page11 and all(e["ability_adj"] for e in off_page11), \
            "page_11 以外 race_overview 应带 ability_adj"

    def test_equipment_extras(self):
        _require_product(CASES["equipment"])
        data = _load_json(CASES["equipment"]["json"])
        assert data["stats"]["total"] >= 2400
        for e in data["entries"]:
            for field in ("price", "weight", "slot"):
                assert field in e, f"equipment 条目缺 {field}: {e['chunk_id']}"


class TestKn235FragmentSink:
    """KN235-①：33 条 table_candidates 碎片 sink 回所属价目表章节/条目。"""

    EXPECTED_TITLES_PAGE210 = {
        "斧嘴鸟；战斗训练", "凶暴蝙蝠；战斗训练", "骑乘用壁虎；战斗训练", "狮鹫；战斗训练",
        "中型生物", "大型生物", "微型或超微型", "超小型", "小型或中型", "大型", "超大型",
        "饲料；每日",
        "类型：普通", "类型：战斗训练", "类型：警卫犬", "类型：宠物犬", "类型：骑乘用犬",
        "类型：重型", "类型：重型，战斗训练", "类型：轻型", "类型：轻型，战斗训练",
        "类型：矮种马", "类型：矮种马，战斗训练", "类型：飞鼠",
    }
    EXPECTED_TITLES_PAGE211 = {
        "轻型战车", "中型战车", "重型战车", "轻型货车", "中型货车", "重型货车",
        "普通作弊骰子", "高品质作弊骰子", "食物",
    }

    @pytest.fixture(scope="module")
    def equipment_data(self):
        _require_product(CASES["equipment"])
        _run_export(CASES["equipment"]["script"])
        return _load_json(CASES["equipment"]["json"])

    @pytest.fixture(scope="module")
    def equipment_report(self):
        _require_product(CASES["equipment"])
        return _load_json(CASES["equipment"]["report"])

    def test_exactly_33_fragments(self, equipment_report):
        assert equipment_report["fragments_sunk"] == 33
        assert not equipment_report["fragments_unsunk"]
        by_doc = {}
        for f in equipment_report["fragments"]:
            parts = f["chunk_id"].split("_")
            by_doc.setdefault("".join(parts[1:3]), []).append(f)
        assert len(by_doc.get("page210", [])) == 24
        assert len(by_doc.get("page211", [])) == 9

    def test_fragment_titles_not_in_entries(self, equipment_data):
        chunks = _load_chunks(CASES["equipment"]["chunks"])
        frag_ids = {c["chunk_id"] for c in chunks
                    if c["doc_id"] in ("page_210", "page_211")
                    and c["title"] in (self.EXPECTED_TITLES_PAGE210 | self.EXPECTED_TITLES_PAGE211)}
        assert len(frag_ids) == 33
        entry_ids = {e["chunk_id"] for e in equipment_data["entries"]}
        assert not (frag_ids & entry_ids), "碎片 chunk 仍独立出现在清单 entries"
        # 反向：page_864 攻城器械尺寸行与碎片标题同形（大型/超大型），属
        # 真条目，仍在清单内——同形标题不误伤由 chunk_id 级断言钉住

    def test_fragment_rows_findable_in_sink_target(self, equipment_data):
        chunks = _load_chunks(CASES["equipment"]["chunks"])
        frag_chunks = [c for c in chunks
                       if c["doc_id"] in ("page_210", "page_211")
                       and c["title"] in (self.EXPECTED_TITLES_PAGE210 | self.EXPECTED_TITLES_PAGE211)]
        assert len(frag_chunks) == 33
        # 清单内全部 sunk_table_fragments（entries + sections 挂载点）按 chunk_id 索引
        hosts = list(equipment_data["entries"]) + equipment_data.get("sections", [])
        sunk = {sf["chunk_id"]: (host, sf)
                for host in hosts for sf in host.get("sunk_table_fragments", [])}
        assert len(sunk) == 33
        for fc in frag_chunks:
            assert fc["chunk_id"] in sunk, f"{fc['chunk_id']} 未 sink"
            host, sf = sunk[fc["chunk_id"]]
            assert sf["title"] == fc["title"]
            assert sf["rows"] == fc["text"].strip(), "sink 行数据应保真等于碎片原文"
            assert fc["doc_id"] == host["doc_id"], "sink 目标应同属一个价目表章节"

    def test_section_hosts_carry_price_data(self, equipment_data):
        """sink 到章节条目（非 entries）的碎片：价格行在 sections 里可追到。"""
        sections = equipment_data.get("sections", [])
        assert sections, "page_210/211 碎片 sink 到 equipment_intro 章节，应有 sections 数组"
        sec_ids = {s["chunk_id"] for s in sections}
        assert "equipment_page_210_0273" in sec_ids  # 动物，坐骑和相关装备
        assert "equipment_page_211_0001" in sec_ids  # 交通工具
        for s in sections:
            for sf in s["sunk_table_fragments"]:
                assert "gp" in sf["rows"] or "sp" in sf["rows"] or "cp" in sf["rows"] \
                    or "价格" in sf["rows"], f"章节 sink 缺价格数据: {sf}"


class TestPriceGpParsing:
    """AKN-025：price 原文 → 可空整数 price_gp（仅 gp 口径，整数）。"""

    @pytest.mark.parametrize("raw,expected", [
        ("235,000 gp", 235000),
        ("7,200  gp", 7200),
        ("49800gp", 49800),
        ("4410GP", 4410),
        ("300GP。", 300),
        ("\ufeff3,000 gp", 3000),
        ("20 金币", 20),
        ("1 pp", 10),
        ("", None),
        ("-", None),
        ("—", None),
        ("可变", None),
        ("5 sp", None),
        ("1 gp-10 gp", None),
        ("+1500 GP", None),
        ("3,7,15,37gp", None),  # 全角逗号枚举（宝箱 3/7/15/37gp）不得拼成整数
        ("14,900", None),  # 默认不接受裸数字（仅价格表上下文 allow_bare）
        (None, None),
    ])
    def test_parse_price_gp(self, raw, expected):
        assert parse_price_gp(raw) == expected

    @pytest.mark.parametrize("raw,expected", [
        ("14,900", 14900),
        ("800", 800),
        ("1,000 gp", 1000),
    ])
    def test_parse_price_gp_allow_bare_in_price_tables(self, raw, expected):
        assert parse_price_gp(raw, allow_bare=True) == expected


class TestEquipmentPriceTables:
    """AKN-025：价格表类别（法杖/权杖/戒指/奇物）清单补全。"""

    def test_fixed_contract_staff_of_power(self, price_table_data):
        """跨侧固定契约：力量法杖 price_gp=235000、chunk_id=equipment_page_222_0000。"""
        hits = [e for e in price_table_data["entries"] if e["name"] == "力量法杖"]
        assert len(hits) == 1, f"力量法杖条目数 {len(hits)} != 1"
        e = hits[0]
        assert e["price_gp"] == 235000
        assert e["chunk_id"] == "equipment_page_222_0000"
        assert e["component_type"] == "staff"
        assert e["book"] == "CRB"
        assert "235,000" in e["price"]

    def test_staff_of_power_is_highest_priced(self, price_table_data):
        """Spec 答案口径：有明确标价条目中最高价 = 力量法杖 235,000 gp。"""
        priced = [e for e in price_table_data["entries"] if e["price_gp"] is not None]
        assert priced
        top = max(priced, key=lambda e: e["price_gp"])
        assert top["name"] == "力量法杖"
        assert top["price_gp"] == 235000

    def test_slot_wondrous_table_rows(self, price_table_data):
        """CRB 槽位价目表（表：腰带 等）表题不含“奇物”，按 chunk 标题归类。"""
        hits = [e for e in price_table_data["entries"] if e["name"] == "矮人腰带BELT OF DWARVENKIND"]
        assert len(hits) == 1, f"腰带价目表条目数 {len(hits)} != 1"
        e = hits[0]
        assert e["component_type"] == "wondrous_item"
        assert e["chunk_id"] == "equipment_page_223_0000"
        assert e["price"] == "14,900"
        assert e["price_gp"] == 14900
        assert e["book"] == "UE"

    def test_all_entries_carry_price_gp(self, price_table_data):
        for e in price_table_data["entries"]:
            assert "price_gp" in e, f"条目缺 price_gp: {e['chunk_id']}/{e['name']}"
            assert isinstance(e["price"], str)
            assert e["price_gp"] is None or isinstance(e["price_gp"], int)
        # 无标价条目（空/非数值原文）保留在清单，仅 price_gp 为 null
        nulls = [e for e in price_table_data["entries"] if e["price_gp"] is None]
        assert nulls, "应有无法解析价格的条目保留（不参与排序）"

    def test_table_categories_complete(self, price_table_data, price_table_report):
        counts = price_table_data["stats"]["by_component_type"]
        for t in PRICE_TABLE_TYPES:
            assert counts.get(t, 0) > 0, f"价格表类别 {t} 无条目"
        pt = price_table_report["price_tables"]
        assert pt["categories"] == {t: counts[t] for t in sorted(PRICE_TABLE_TYPES)
                                    if counts.get(t)}
        assert price_table_data["stats"]["price_table_entries"] == \
            sum(pt["categories"].values())

    def test_price_gp_report_counts_and_samples(self, price_table_data, price_table_report):
        pg = price_table_report["price_tables"]["price_gp"]
        assert pg["parsed"] + pg["failed"] == price_table_data["stats"]["total"]
        assert pg["failed"] > 0, "无标价/解析失败条目应计入报告"
        samples = pg["failed_samples"]
        assert 0 < len(samples) <= 20
        by_key = {(e["chunk_id"], e["name"], e["price"]): e
                  for e in price_table_data["entries"]}
        for s in samples:
            e = by_key[(s["chunk_id"], s["name"], s["price"])]
            assert e["price_gp"] is None, f"失败样本 price_gp 非 null: {s}"

    def test_table_entry_chunk_points_to_source_table(self, price_table_data):
        """价格表条目 chunk_id 必须指向含该行价格原文的价格表 chunk（溯源口径）。"""
        chunks = {c["chunk_id"]: c for c in _load_chunks(CASES["equipment"]["chunks"])}
        table_entries = [e for e in price_table_data["entries"]
                         if e["component_type"] in PRICE_TABLE_TYPES]
        assert table_entries
        for e in table_entries:
            chunk = chunks[e["chunk_id"]]
            assert "|" in chunk["text"], f"{e['chunk_id']} 不是表格 chunk"
            assert e["price"] in _src_fold(chunk["text"]), \
                f"{e['price']} 不在来源价格表 {e['chunk_id']} 原文中"

    def test_every_source_price_table_reconciled(self, price_table_data, price_table_report):
        """逐源独立对账：完整来源集合 + 每源（源行号,名称原文,价格原文）身份集合。"""
        chunks = _load_chunks(CASES["equipment"]["chunks"])
        by_id = {c["chunk_id"]: c for c in chunks}
        sources = {s["chunk_id"]: s["rows"]
                   for s in price_table_report["price_tables"]["sources"]}
        # 完整来源集合：报告来源 == 测试侧独立维护的源表清单
        assert set(sources) == set(SOURCE_TABLE_COLUMNS), \
            f"来源集合不一致: 缺 {set(SOURCE_TABLE_COLUMNS) - set(sources)}，" \
            f"多 {set(sources) - set(SOURCE_TABLE_COLUMNS)}"
        entries_by = defaultdict(list)
        for e in price_table_data["entries"]:
            if e["component_type"] in PRICE_TABLE_TYPES:
                entries_by[e["chunk_id"]].append(e)
        for cid, specs in SOURCE_TABLE_COLUMNS.items():
            expected = _src_expected_rows(by_id[cid], specs)
            # (源行号, 价格列, 名称, 价格) 身份唯一：并排双栏同一行可承载两条
            assert len(expected) == len(set(expected)), f"{cid} 源行身份重复"
            actual = [(e["name"], e["price"]) for e in entries_by[cid]]
            assert sources.get(cid) == len(expected), \
                f"{cid}（{by_id[cid]['title']}）预期 {len(expected)} 行 != 报告 {sources.get(cid)}"
            assert len(actual) == len(expected), \
                f"{cid}（{by_id[cid]['title']}）条目 {len(actual)} != 独立预期 {len(expected)}"
            want = Counter((name, price) for _, _, name, price in expected)
            got = Counter(actual)
            assert got == want, (
                f"{cid} 条目身份与源表不一致；缺 {list((want - got).items())[:5]}，"
                f"多 {list((got - want).items())[:5]}")

    def test_source_table_inventory_complete(self):
        """独立盘点：所有 target 类别中带价格列（>1 表行）的 chunk 必须登记在预期表内。"""
        _require_product(CASES["equipment"])
        for c in _load_chunks(CASES["equipment"]["chunks"]):
            if c["component_type"] not in PRICE_TABLE_TYPES:
                continue
            table_lines = [ln for ln in (c.get("text") or "").splitlines()
                           if ln.strip().startswith("|")]
            if len(table_lines) <= 1:
                continue
            has_price_header = any(_SRC_PRICE_HEADER.match(cell)
                                  for ln in table_lines for cell in _src_cells(ln))
            if has_price_header:
                assert c["chunk_id"] in SOURCE_TABLE_COLUMNS, \
                    f"未登记的来源价格表: {c['chunk_id']}（{c['title']}）"

    def test_empty_price_table_rows_retained(self, price_table_data, price_table_report):
        """P1（r2）：有有效名称的空价格表行保留 price=''、price_gp=null。"""
        empties = [e for e in price_table_data["entries"]
                   if e["component_type"] in PRICE_TABLE_TYPES and e["price"] == ""]
        assert {e["name"] for e in empties} == {"暗灰色（破损的）", "暗灰色（缺陷的）"}
        assert all(e["chunk_id"] == "equipment_page_1254_0005" for e in empties)
        assert all(e["price_gp"] is None for e in empties)
        # 逐源对账口径也必须覆盖空价格单元
        rows = [e for e in price_table_data["entries"]
                if e["chunk_id"] == "equipment_page_1254_0005"]
        assert len(rows) == 134
        sources = {s["chunk_id"]: s["rows"]
                   for s in price_table_report["price_tables"]["sources"]}
        assert sources["equipment_page_1254_0005"] == 134
        pg = price_table_report["price_tables"]["price_gp"]
        assert pg["parsed"] + pg["failed"] == price_table_data["stats"]["total"]

    def test_previously_missing_price_tables(self, price_table_data):
        """P1-1 回归：OA PotS 宇宙图 / 火球项链矩阵 / 护身符表必须逐行导出。"""
        entries = price_table_data["entries"]
        expected = {
            "equipment_繁星子民PotS_奇物_0001": 9,
            "equipment_page_231_0034": 7,
            "equipment_page_231_0060": 6,
        }
        for cid, n in expected.items():
            rows = [e for e in entries if e["chunk_id"] == cid]
            assert len(rows) == n, f"{cid} 条目 {len(rows)} != {n}"
        pot = {e["name"]: e["price_gp"] for e in entries
               if e["chunk_id"] == "equipment_繁星子民PotS_奇物_0001"}
        assert pot["行星型"] == 100
        assert pot["宇宙图 X250"] == 8000
        fire = {e["name"]: e["price_gp"] for e in entries
                if e["chunk_id"] == "equipment_page_231_0034"}
        assert fire["火球项链 I"] == 1650
        assert fire["火球项链 VII"] == 8700
        amulet = {e["name"]: e["price_gp"] for e in entries
                  if e["chunk_id"] == "equipment_page_231_0060"}
        assert amulet["阿克本"] == 450
        assert amulet["哈姆萨"] == 3000

    def test_no_price_artifacts_retained(self, price_table_data):
        """P1-2：神器/诅咒物品无标价也必须保留（price_gp=null）。"""
        chunks = _load_chunks(CASES["equipment"]["chunks"])
        entries = price_table_data["entries"]
        for ctype in ("artifact", "cursed_item"):
            src = [c for c in chunks if c["component_type"] == ctype]
            got = [e for e in entries if e["component_type"] == ctype]
            assert len(got) == len(src), f"{ctype} 条目 {len(got)} != 源 chunk {len(src)}"
            assert all(e["price_gp"] is None for e in got), f"{ctype} 应全部 price_gp=null"
            assert ctype not in price_table_data["excluded_component_types"]
        art = {e["chunk_id"]: e for e in entries if e["component_type"] == "artifact"}
        assert art["equipment_page_949_0001"]["name"] == "信仰灯塔"
        assert art["equipment_page_860_0000"]["name"] == "Apollyon之戒"

    def test_main_catalog_bare_prices_parsed(self, price_table_data):
        """P1-3：主目录裸数字/千分位价格按 gp 解析，不得置 null。"""
        direct = [e for e in price_table_data["entries"]
                  if e["component_type"] in DIRECT_TYPES]
        bare = [e for e in direct if re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})*", e["price"])]
        assert len(bare) >= 62, f"裸数字价格条目仅 {len(bare)} 条（应 ≥62）"
        for e in bare:
            assert e["price_gp"] == int(e["price"].replace(",", "")), e
        by_key = {(e["chunk_id"], e["name"]): e for e in direct}
        assert by_key[("equipment_格拉里昂的纯洁勇士_魔法物品_0003", "平衡者之盾")]["price_gp"] == 120830
        assert by_key[("equipment_page_210_0007", "星盘")]["price_gp"] == 1000
        # 全角逗号枚举不是合法数字，仍为 null
        chest = next(e for e in direct if e["name"] == "宝箱")
        assert chest["price_gp"] is None

    def test_name_price_conflicts_preserved(self, price_table_data, price_table_report):
        """P1-4：同名不同价/不同来源的真实表行全部保留并可溯源。"""
        table_entries = [e for e in price_table_data["entries"]
                         if e["component_type"] in PRICE_TABLE_TYPES]
        by_name = {}
        for e in table_entries:
            by_name.setdefault(e["name"], []).append(e)
        for name, expected in {
            "信仰披肩MANTLE OF FAITH": {
                ("equipment_page_234_0000", 9000), ("equipment_page_225_0000", 76000)},
            "法术抵抗披肩MANTLE OF SPELL RESISTANCE": {
                ("equipment_page_234_0000", 9000), ("equipment_page_225_0000", 90000)},
            "召唤共鸣戒指：盖丁": {
                ("equipment_page_220_0000", 7000), ("equipment_page_220_0000", 7700)},
        }.items():
            got = {(e["chunk_id"], e["price_gp"]) for e in by_name.get(name, [])}
            assert expected <= got, f"{name} 冲突行丢失: {got}"
        # 诗歌披风两条不同写法也都在（不因同名/近似名丢弃）
        cloaks = [e for e in table_entries if e["name"].startswith("诗歌披风")]
        assert {(e["chunk_id"], e["price_gp"]) for e in cloaks} >= {
            ("equipment_page_234_0000", 9750), ("equipment_page_232_0000", 9450)}
        conflicts = {c["name"]: c for c in price_table_report["price_tables"]["name_conflicts"]}
        assert "信仰披肩MANTLE OF FAITH" in conflicts
        assert "召唤共鸣戒指：盖丁" in conflicts
        for c in conflicts.values():
            assert len(c["rows"]) > 1
            assert all({"chunk_id", "price", "price_gp"} <= set(r) for r in c["rows"])


class TestIdempotent:
    def test_rerun_byte_identical(self):
        _require_product(CASES["feat"])
        spec = CASES["feat"]
        before = (PHASE1 / spec["json"]).read_bytes()
        _run_export(spec["script"])
        assert (PHASE1 / spec["json"]).read_bytes() == before

    def test_equipment_rerun_byte_identical(self):
        _require_product(CASES["equipment"])
        spec = CASES["equipment"]
        _run_export(spec["script"])
        before = (PHASE1 / spec["json"]).read_bytes()
        _run_export(spec["script"])
        assert (PHASE1 / spec["json"]).read_bytes() == before


class TestSoftCheck:
    def test_missing_file_warns_not_fails(self, tmp_path):
        from vectorizer.list_export import make_list_soft_check
        check = make_list_soft_check("D2 test", str(tmp_path / "nope_lists.json"), 1)
        _, fn, _ = check
        ok, issues = fn([], {})
        assert ok and issues == []  # 缺失仅 WARN，check 通过（软检查不阻断）
