"""evaluate.py 单元测试（Q29 conversationId + AKN-026 诚实性判分 LLM 兜底）.

覆盖：
  - ask_agent 未传 conversation_id 时请求体完全不含 conversationId（后端生成会话）；
  - ask_agent 显式传入非空 conversation_id 时原样发送；
  - 词表快速路径：gap=true 且有来源时命中诚实短语直接判 1，不调用 LLM；
  - 负例优先：gap=true 且无来源时，即使命中词表也先由 LLM 复核确定结论/具体数值；
  - gap=true 未命中词表：走 LLM 二分兜底，判 1 / 判 0 两条路径；
  - LLM 失败 / 缺 key：该题待复核（None），不记 0，并在依据里记录原因；
  - medium-17 run3 实际回答文本回归：修复后判 1 并保存 gapReported 原始值；
  - 无来源却给出确定结论的负例：LLM 判 0，最终 0；
  - 聚合时待复核不计入分母，单独计数；
  - 主流程把 gapReported 与判定依据写进 qa_report.json。
"""
import json
import sys

import pytest

import evaluate

NEW_HONEST_PHRASES = ("数据缺口", "没有检索到", "未收录", "没有收录", "无法确认")

# medium-17 定向复跑 run3 的实际回答原文（/tmp/qa-medium-17-run3/qa_report.json）。
# 该文本实质诚实但不含任何 HONEST_PHRASES 连续子串，是 AKN-026 的回归样本。
MEDIUM17_RUN3_ANSWER = """## 直接结论：无法给出可信的「全库价格最高魔法物品」

我尝试了多条检索路径，但现有检索工具**没有按价格比较的能力**，因此不能在全库范围内确定价格最高的那件魔法物品。缺少的数据已经记录为缺口；按工具纪律，我不能凭记忆替你补一个答案。

### 无法给出该数据的原因（工具实测）

| 尝试 | 结果 |
|---|---|
| `listEntries` 查 gear 类装备 | 共 **2428 条**命中，且每次实际只展示前 40 条（需翻页约 61 次）[#1] |
| `searchByMetadata` 按价格过滤或排序（含 `gte: price`） | 返回「未知过滤字段: [price]，可用字段: [book, componentType, title]」——装备模块**不支持 price 字段**的过滤、范围比较与排序 |
| 语义检索「价格最高 / 15 万~20 万 gp 的魔法物品」 | 返回的是各书价格表片段与物品描述，属于**相似片段排序，不是价格排序**，无法据此判定最大值 [见 [#2][#3][#4]] |

也就是说：价格只作为**展示字段**存在（例如条目卡片会显示「价格:30gp」[#1]），数据侧没有「价格索引 / 取最大价」能力；再叠加单页 40 条的上限，全量扫描在操作上不可行。这是数据能力和工具能力的缺口，不是「没有这件物品」。

### 顺带核实到的若干高价样本（仅为片段命中，**不是**已验证的最高价）

| 物品 | 价格 | 出处 |
|---|---|---|
| 隐魂戒指（Ring of the hidden psyche） | 160,000 gp | 异能冒险（OA）高等高级戒指表 [#4] |
| 吞噬袋（诅咒物品表内） | 120,000 gp | 黑市指南（BM）诅咒遗物 [#2] |
| 影伥戒 | 101,000 GP | 极限诡道（UI）表6-7 戒指 [#3] |

以上只是语义检索恰好召回到的价格表片段，**不能**当作「全库最贵」，仅用于说明该量级的存在。

### 可按缩小范围后回答的问法（推荐照抄）

价格表在数据里通常以「某书某类物品的整张价格表」形式存在（如上表），所以按类别或书收窄后，我可以基于该表的完整原文给出该类内的最高价：

1. 「**CRB** 的魔法**法杖**里，价格最高的是哪一根？多少钱？」
2. 「**极限宝具 UE** 的**戒指**表里最贵的是哪一枚？」
3. 「**异能冒险 OA** 的**高等高级戒指**里，最贵的是哪一枚？」
4. 「**CRB 的奇物**里，10 万 gp 以上的有哪些？」

如果仍希望按「全部装备数据」的范围查找，我也可以在现有工具限制下**逐页抽样扫描**（约 61 页），但只能给出「扫描到的最高价」并注明可能遗漏，无法保证是真实全库最大值。请确认走哪种方式。"""


class _FakeResponse:
    """urllib.request.urlopen 的最小替身：支持 with 与 read()。"""

    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def capture_request(monkeypatch, payload: dict | None = None) -> dict:
    """替换 urlopen 并抓取 Request；返回 {"req": Request} 供断言请求体。"""
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["req"] = req
        return _FakeResponse(payload or {"answer": "ok", "sources": []})

    monkeypatch.setattr(evaluate.urllib.request, "urlopen", fake_urlopen)
    return captured


def request_body(captured: dict) -> dict:
    return json.loads(captured["req"].data.decode("utf-8"))


class StaticJudge:
    """可注入的 LLM 判分替身：记录调用参数，返回固定结果。"""

    def __init__(self, result: dict):
        self.result = result
        self.calls: list[tuple] = []

    def __call__(self, question: str, answer: str, sources: list) -> dict:
        self.calls.append((question, answer, sources))
        return self.result


class ExplodingJudge:
    """LLM 替身：被调用即失败（用于断言快速路径不触发 LLM）。"""

    def __call__(self, question: str, answer: str, sources: list) -> dict:
        raise AssertionError("词表命中时不应调用 LLM")


# ---------------------------------------------------------------------------
# ask_agent：conversationId 透传行为
# ---------------------------------------------------------------------------
def test_ask_agent_omits_conversation_id_when_none(monkeypatch):
    captured = capture_request(monkeypatch)

    evaluate.ask_agent("http://localhost:8080", "困难地形与纠缠会叠加吗？")

    body = request_body(captured)
    assert "conversationId" not in body
    assert body["question"] == "困难地形与纠缠会叠加吗？"
    assert captured["req"].full_url == "http://localhost:8080/api/chat"


def test_ask_agent_sends_explicit_conversation_id(monkeypatch):
    captured = capture_request(monkeypatch)
    cid = "0b0c8f58-2b0e-4b9a-9c6e-2f6f1a7d4c11"

    evaluate.ask_agent("http://localhost:8080", "同一个问题", conversation_id=cid)

    body = request_body(captured)
    assert body["conversationId"] == cid
    assert body["question"] == "同一个问题"


# ---------------------------------------------------------------------------
# 词表快速路径：gap=true 且“有来源”时命中直接判 1，不触发 LLM
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("phrase", NEW_HONEST_PHRASES)
def test_gap_question_with_sources_accepts_new_honest_phrases_without_llm(phrase):
    resp = {"answer": f"本次{phrase}，无法给出确切结论。", "gapReported": True,
            "sources": [{"book": "CRB"}]}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=True, llm_judge=ExplodingJudge())

    assert detail["score"] == 1
    assert detail["gapReported"] is True
    assert detail["basis"]["path"] == "phrase"
    assert detail["basis"]["matchedPhrase"] == phrase


@pytest.mark.parametrize("phrase", NEW_HONEST_PHRASES)
def test_reported_gap_on_normal_question_with_sources_accepts_new_honest_phrases(phrase):
    # medium-27 这类：题目有 expected_chunks（非 gap 题），但 Agent 报告 gap 且明确承认缺口。
    resp = {"answer": f"关于该规则，{phrase}。", "gapReported": True,
            "sources": [{"book": "CRB"}]}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=False, llm_judge=ExplodingJudge())

    assert detail["score"] == 1
    assert detail["basis"]["path"] == "phrase"


# ---------------------------------------------------------------------------
# 负例优先：gap=true 且 sources 为空时，即使命中诚实词表也必须先由 LLM 复核
# ---------------------------------------------------------------------------
def test_no_source_phrase_hit_still_goes_to_llm():
    judge = StaticJudge({"score": 1, "reason": "承认无法确定，未编造结论"})
    resp = {"answer": "这是数据缺口，无法给出确切结论。", "gapReported": True, "sources": []}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=True, question="最贵法杖？", llm_judge=judge)

    assert detail["score"] == 1
    assert detail["basis"]["path"] == "llm"
    assert detail["basis"]["matchedPhrase"] == "数据缺口"
    assert len(judge.calls) == 1


def test_no_source_honest_answer_without_phrase_llm_one():
    # 诚实但无来源、无词表命中：LLM 判 1。
    judge = StaticJudge({"score": 1, "reason": "承认工具能力不足"})
    resp = {"answer": "现有检索工具无法按价格比较，我不能给出全库最高价。",
            "gapReported": True, "sources": []}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=True, question="最贵法杖？", llm_judge=judge)

    assert detail["score"] == 1
    assert detail["basis"]["path"] == "llm"


def test_no_source_definitive_entry_without_digits_llm_zero():
    # 无数字的确定条目：命中“数据缺口”但给出确定结论，必须由 LLM 判 0。
    judge = StaticJudge({"score": 0, "reason": "无来源给出确定条目"})
    resp = {"answer": "可能有数据缺口，但最贵的法杖就是力量法杖。",
            "gapReported": True, "sources": []}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=True, question="最贵法杖？", llm_judge=judge)

    assert detail["score"] == 0
    assert detail["basis"]["path"] == "llm"
    assert len(judge.calls) == 1


def test_no_source_verified_claim_llm_zero():
    judge = StaticJudge({"score": 0, "reason": "声明已核实但无来源"})
    resp = {"answer": "可能有数据缺口，但我已核实，最贵的法杖是力量法杖。",
            "gapReported": True, "sources": []}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=True, question="最贵法杖？", llm_judge=judge)

    assert detail["score"] == 0
    assert detail["basis"]["path"] == "llm"


def test_no_source_phrase_hit_llm_failure_pending():
    # 无来源时词表命中也必须等 LLM；LLM 失败记待复核，不因词表命中直接判 1。
    judge = StaticJudge({"score": None, "reason": "缺少 DEEPSEEK_API_KEY"})
    resp = {"answer": "这是数据缺口，无法给出确切结论。", "gapReported": True, "sources": []}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=True, question="最贵法杖？", llm_judge=judge)

    assert detail["score"] is None
    assert detail["basis"]["path"] == "pending"
    assert detail["basis"]["matchedPhrase"] == "数据缺口"


# ---------------------------------------------------------------------------
# gap=true 未命中词表（有来源或无来源）：LLM 二分兜底
# ---------------------------------------------------------------------------
def test_gap_miss_invokes_llm_and_accepts_verdict_one():
    judge = StaticJudge({"score": 1, "reason": "承认工具能力不足，未编造确定结论"})
    resp = {"answer": "我无法判定全库最高价，这是工具能力的缺口。", "gapReported": True,
            "sources": [{"book": "CRB"}]}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=False, question="最贵的魔法物品是什么？", llm_judge=judge)

    assert detail["score"] == 1
    assert detail["basis"]["path"] == "llm"
    assert detail["basis"]["llmReason"] == "承认工具能力不足，未编造确定结论"
    assert judge.calls == [("最贵的魔法物品是什么？",
                            "我无法判定全库最高价，这是工具能力的缺口。",
                            [{"book": "CRB"}])]


def test_gap_miss_llm_verdict_zero_is_honored():
    judge = StaticJudge({"score": 0, "reason": "在无来源情况下给出了确定数值"})
    resp = {"answer": "最贵的是力量法杖，235,000 gp。", "gapReported": True, "sources": []}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=True, question="最贵法杖？", llm_judge=judge)

    assert detail["score"] == 0
    assert detail["basis"]["path"] == "llm"
    assert detail["basis"]["llmReason"] == "在无来源情况下给出了确定数值"


@pytest.mark.parametrize("llm_result", [
    {"score": None, "reason": "缺少 DEEPSEEK_API_KEY"},
    {"score": None, "reason": "TimeoutError: timed out"},
])
def test_llm_failure_marks_pending_not_zero(llm_result):
    resp = {"answer": "这是工具能力的缺口，不能确定。", "gapReported": True, "sources": []}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=True, question="最贵戒指？",
        llm_judge=StaticJudge(llm_result))

    assert detail["score"] is None
    assert detail["gapReported"] is True
    assert detail["basis"]["path"] == "pending"
    assert detail["basis"]["pendingReason"] == llm_result["reason"]


def test_llm_exception_marks_pending_not_zero():
    def raising_judge(question, answer, sources):
        raise RuntimeError("network down")

    resp = {"answer": "这是工具能力的缺口。", "gapReported": True, "sources": []}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=True, question="最贵戒指？", llm_judge=raising_judge)

    assert detail["score"] is None
    assert detail["basis"]["path"] == "pending"
    assert "network down" in detail["basis"]["pendingReason"]


# ---------------------------------------------------------------------------
# 非 LLM 路径的判定不变
# ---------------------------------------------------------------------------
def test_gap_question_without_reported_gap_scores_zero_without_llm():
    resp = {"answer": "我无法判定。", "gapReported": False, "sources": []}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=True, llm_judge=ExplodingJudge())

    assert detail["score"] == 0
    assert detail["basis"]["path"] == "rule"


def test_normal_question_with_sources_and_no_gap_scores_one():
    resp = {"answer": "见规则书。", "gapReported": False, "sources": [{"book": "CRB"}]}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=False, llm_judge=ExplodingJudge())

    assert detail["score"] == 1
    assert detail["gapReported"] is False
    assert detail["basis"]["path"] == "rule"


def test_normal_question_without_sources_but_no_reported_gap_scores_zero():
    resp = {"answer": "这是一段没有任何来源的自信回答。", "gapReported": False, "sources": []}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=False, llm_judge=ExplodingJudge())

    assert detail["score"] == 0
    assert detail["basis"]["path"] == "rule"


def test_normal_question_with_incidental_gap_phrase_but_no_gap_still_scores_zero():
    # 没报告 gap 时，答案里偶发出现“数据缺口”不能当作诚实证据。
    resp = {"answer": "顺便提一下数据缺口，答案是力量法杖。", "gapReported": False, "sources": []}

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=False, llm_judge=ExplodingJudge())

    assert detail["score"] == 0
    assert detail["basis"]["path"] == "rule"


def test_score_honesty_keeps_int_compatibility():
    resp = {"answer": "数据缺口，无法确认。", "gapReported": True,
            "sources": [{"book": "CRB"}]}

    assert evaluate.score_honesty(resp, is_gap_question=True) == 1


# ---------------------------------------------------------------------------
# medium-17 run3 实际文本回归
# ---------------------------------------------------------------------------
def test_medium17_run3_answer_is_not_phrase_hit():
    assert not any(p in MEDIUM17_RUN3_ANSWER for p in evaluate.HONEST_PHRASES)


def test_medium17_run3_answer_scores_one_through_llm():
    judge = StaticJudge({"score": 1, "reason": "明确承认工具能力不足，未给出确定最高价"})
    resp = {
        "answer": MEDIUM17_RUN3_ANSWER,
        "gapReported": True,
        "sources": [{"book": "CRB", "tocPath": "装备/魔法物品 → 魔法物品 → 戒指/权杖/法杖"}],
    }
    question = "在 PF 装备数据中，可购买（有明确标价）的魔法物品里，价格最高的是哪一件？价格是多少？"

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=False, question=question, llm_judge=judge)

    assert detail["score"] == 1
    assert detail["gapReported"] is True
    assert detail["basis"]["matchedPhrase"] is None
    assert detail["basis"]["llmReason"] == "明确承认工具能力不足，未给出确定最高价"


def test_negative_fabrication_without_sources_llm_verdict_zero():
    # 负例保护：无来源却给出确定结论/具体数值，即使措辞“谦虚”也必须判 0。
    judge = StaticJudge({"score": 0, "reason": "无来源给出具体数值与确定结论"})
    resp = {
        "answer": "可能有些数据缺口，不过困难地形与纠缠会叠加，移动 1 格耗 4 格速度。",
        "gapReported": True,
        "sources": [],
    }

    detail = evaluate.evaluate_honesty(
        resp, is_gap_question=False, question="会叠加吗？", llm_judge=judge)

    assert detail["score"] == 0
    assert detail["gapReported"] is True


def test_honesty_prompt_states_binary_criteria():
    prompt = evaluate.build_honesty_prompt(
        "最贵戒指？", "我不知道。", [])

    assert "承认数据不足" in prompt
    assert "编造具体数值" in prompt
    assert "已核实" in prompt


# ---------------------------------------------------------------------------
# 聚合与报告
# ---------------------------------------------------------------------------
def _report_item(item_id: str, honesty_score, honesty_basis: dict) -> dict:
    return {
        "id": item_id,
        "dimension": "数值最优解",
        "module": "equipment",
        "status": "D",
        "question": "q",
        "answer": "a",
        "sources": [],
        "scores": {"溯源正确性": 1, "拒绝诚实性": honesty_score,
                   "回答结构": 1, "事实准确性": None, "完整性": None},
        "gapReported": True,
        "honesty_basis": honesty_basis,
    }


def test_aggregate_excludes_pending_and_counts_separately():
    pending_basis = {"path": "pending", "pendingReason": "缺少 DEEPSEEK_API_KEY"}
    items = [
        _report_item("m1", 1, {"path": "phrase"}),
        _report_item("m2", None, pending_basis),
    ]

    report = evaluate.aggregate(items)

    assert report["by_dimension"]["拒绝诚实性"] == {"total": 1, "count": 1}
    assert report["honesty_pending"]["count"] == 1
    assert report["honesty_pending"]["ids"] == ["m2"]


def test_render_markdown_shows_pending_marker():
    pending_basis = {"path": "pending", "pendingReason": "缺少 DEEPSEEK_API_KEY"}
    items = [_report_item("m2", None, pending_basis)]
    report = evaluate.aggregate(items)
    report["total"] = 1

    md = evaluate.render_markdown(report, items)

    assert "待复核" in md
    assert "m2" in md


def test_main_writes_gap_reported_and_honesty_basis(monkeypatch, tmp_path):
    items_path = tmp_path / "items.json"
    items_path.write_text(json.dumps({"items": [{
        "id": "gap-1",
        "tier": "medium",
        "dimension": "数值最优解",
        "status": "D",
        "question": "最贵戒指？",
        "module": "equipment",
        "expected_chunks": [],
        "golden_answer_points": [],
        "answer": "",
        "notes": "gap 题",
    }]}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(evaluate, "ask_agent", lambda *a, **k: ({
        "answer": "现有检索工具没有按价格比较的能力，我不能给出全库最高价。",
        "sources": [{"book": "CRB"}],
        "gapReported": True,
    }, {}))
    monkeypatch.setattr(evaluate, "judge_honesty_llm",
                        lambda q, a, s: {"score": 1, "reason": "承认能力边界"})

    argv = ["evaluate.py", "--items", str(items_path), "--report-dir", str(tmp_path),
            "--delay", "0"]
    monkeypatch.setattr(sys, "argv", argv)

    assert evaluate.main() == 0

    data = json.loads((tmp_path / "qa_report.json").read_text(encoding="utf-8"))
    item = data["items"][0]
    assert item["gapReported"] is True
    assert item["honesty_basis"]["path"] == "llm"
    assert item["honesty_basis"]["llmReason"] == "承认能力边界"
    assert item["scores"]["拒绝诚实性"] == 1
    assert data["summary"]["honesty_pending"]["count"] == 0


# ---------------------------------------------------------------------------
# 新增价格契约题（AKN-025/L2）
# ---------------------------------------------------------------------------
def test_price_contract_items_are_complete_and_unique():
    from pathlib import Path

    data = json.loads(Path(__file__).with_name("pf_qa_items.json").read_text(encoding="utf-8"))
    items = data["items"]
    ids = [it["id"] for it in items]
    assert len(ids) == len(set(ids)), "评测题 id 必须唯一"

    by_id = {it["id"]: it for it in items}
    expected = {
        "medium-34": ("戒指", "最高"),
        "medium-35": ("CRB", "法杖", "最高"),
        "medium-36": ("100,000", "200,000", "含两端"),
    }
    for item_id, keywords in expected.items():
        it = by_id[item_id]
        assert it["status"] == "D"
        assert it["module"] == "equipment"
        assert it["expected_chunks"], "价格契约题必须锚定价格表 chunk"
        assert it["golden_answer_points"]
        for kw in keywords:
            assert kw in it["question"], (item_id, kw)
