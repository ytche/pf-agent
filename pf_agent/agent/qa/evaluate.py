#!/usr/bin/env python3
"""PF 规则问答 Agent 回答质量评测脚本（56 题评测集）.

评测集来源：dnd5e-srd-qa（HuggingFace datapizza-ai-lab/dnd5e-srd-qa，56 题 RAG 评测集）
迁移为 PF 1e 版，见 pf_qa_items.json 与 迁移难点_5e无法映射.md。

用法：
    # 对运行中的 Agent（mvn spring-boot:run，默认 localhost:8080）全量评测
    python3 evaluate.py

    # 抽样 5 题（观察用）
    python3 evaluate.py --sample 5

    # 指定 base-url / 输出目录
    python3 evaluate.py --base-url http://localhost:8080 --report-dir ./out

    # 启用 B 批 LLM-as-judge（需 golden_answer_points 非空 + DeepSeek key）
    DEEPSEEK_API_KEY=sk-xxx python3 evaluate.py --judge

    # 关闭 AKN-026 诚实性 LLM 兜底（默认启用、按需调用）
    python3 evaluate.py --no-honesty-llm

五维度判分分两批：
    A 批 · 规则化（无需 golden answer，本脚本即可算）：
      1. 溯源正确性   sources[].tocPath/book 是否命中 expected_chunks（相等或前缀匹配）→ 0/1
      2. 拒绝诚实性   正常题断言 gapReported==false；sources 为空但未报告 gap → 疑似编造 → 0
      3. 回答结构     Markdown / 枚举题表格列表 / 带来源引用 → 0~3
    B 批 · LLM-as-judge（第二阶段 golden_answer_points 完成后再启用）：
      4. 事实准确性   judge(answer, golden_answer_points) → 0~2
      5. 完整性       覆盖 golden_answer_points 的比例 → 0~1
    golden_answer_points 为空时 B 批跳过并标注「待 golden answer」。

AKN-026 诚实性判分（A 批第 2 维，用户拍板「负例优先」）：
    - gapReported=true 且有来源：词表 HONEST_PHRASES 命中 → 直接判 1（快速路径）；
    - gapReported=true 且无来源：即使命中词表也先由 LLM 复核是否给出确定结论/具体数值；
    - gapReported=true 且词表未命中 → 调用 LLM 做二分兜底（默认启用、按需调用）；
    - LLM 失败 / 缺 key → 该题「待复核」（分数 null），不记 0，汇总单独计数；
    - 每题保存 gapReported 原始值与判定依据（matchedPhrase / llmReason / pendingReason）。

输出：
    qa_report.json   每题 5 维度得分 + 总分 + 明细 + gapReported / honesty_basis
    qa_report.md     汇总表（按维度 / 按模块聚合）+ 每题明细
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

# macOS 上 urllib 默认读系统代理（getproxies → 127.0.0.1:7892 等本地代理软件），
# 连 localhost 也可能被代理拦截返回空 502；评测脚本直连本机 Agent，必须绕过系统代理。
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

# ---------------------------------------------------------------------------
# 常量与默认值
# ---------------------------------------------------------------------------
DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_ITEMS = "pf_qa_items.json"
DEFAULT_REPORT_DIR = "."
DIMENSIONS = ["溯源正确性", "拒绝诚实性", "回答结构", "事实准确性", "完整性"]
HONEST_PHRASES = ("未检索到", "没有找到", "未找到", "无法回答", "数据中不存在", "没有相关数据",
                  "数据缺口", "没有检索到", "未收录", "没有收录", "无法确认")
HONESTY_MODEL = "deepseek-flash"


def build_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


# ---------------------------------------------------------------------------
# 请求 Agent /api/chat
# ---------------------------------------------------------------------------
def ask_agent(base_url: str, question: str, conversation_id: str | None = None,
              timeout: int = 120) -> tuple[dict, dict]:
    """POST /api/chat，返回 (json_response, http_error)。

    json_response: {answer, sources[{book,tocPath,content}], gapReported, conversationId}
    请求失败（服务未启动 / 超时）返回 ({}, error_info)。

    conversation_id 为 None 时请求体不含 conversationId 字段，由后端生成新会话 ID；
    显式传入时原样发送（用于复用同一会话做多轮评测）。
    """
    body = {"question": question}
    if conversation_id is not None:
        body["conversationId"] = conversation_id
    req = urllib.request.Request(
        build_url(base_url, "/api/chat"),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), {}
    except Exception as e:  # 连接失败 / 超时 / 非 JSON / 5xx
        return {}, {"error": f"{type(e).__name__}: {e}"}


# ---------------------------------------------------------------------------
# A 批 · 规则化判分
# ---------------------------------------------------------------------------
def score_citation(sources: list, expected_chunks: list, loose: bool = False) -> int:
    """溯源正确性：sources[].tocPath / .book 命中 expected_chunks（相等或前缀）→ 1 否则 0。

    命中判定：
      - 相等：source 锚点值等于 expected 锚点值；
      - 前缀：expected 以「模块名 →」tocPath 形式给出时，source.tocPath 以它开头；
      - 兜底：source.book == expected（当 expected 是纯书缩写如 "CRB"）。

    loose（聚合题宽松口径）：跨 chunk 综合的聚合题（如 medium-17「全库找最高价」）
    答案分散在同一页的多个 chunk，expected 只标 page 级锚点（equipment_page_222_0000）。
    此时命中「page 级前缀」（equipment_page_222，去掉 chunk idx 末段）即算溯源——
    因为答案本身须从该页价格表的多个 chunk 排序得出，强制精确 chunk 匹配不合理。
    """
    if not expected_chunks:
        return 0
    for src in sources:
        toc = src.get("tocPath") or ""
        book = src.get("book") or ""
        cid = src.get("chunkId") or ""
        for exp in expected_chunks:
            exp = (exp or "").strip()
            if not exp:
                continue
            # chunk_id 精确匹配（Agent 返回 chunk_id 命中期望锚点）
            if cid and (cid == exp or cid.startswith(exp)):
                return 1
            # 聚合题宽松：page 级前缀匹配（equipment_page_222_0000 → equipment_page_222）
            if loose and cid and "_" in exp:
                page_prefix = exp.rsplit("_", 1)[0]
                if page_prefix and cid.startswith(page_prefix):
                    return 1
            # 相等 / 前缀（tocPath 层级锚）
            if toc == exp or toc.startswith(exp):
                return 1
            # expected 是书缩写
            if exp == book:
                return 1
            # tocPath 里包含 expected 的末段（如 chunk title 片段）
            if len(exp) > 3 and exp in toc:
                return 1
    return 0


def build_honesty_prompt(question: str, answer: str, sources: list) -> str:
    """构造诚实性二分判分提示词（AKN-026）。

    LLM 只回答「这条已报告 gap 的回答是否实质诚实」，不评价事实正确性。
    判 0 条件明确包含负例保护：无来源却给出确定结论/具体数值，措辞谦虚也判 0。
    """
    source_lines = []
    for i, src in enumerate(sources[:10], 1):
        source_lines.append(
            f"  [{i}] {src.get('book', '')} / {src.get('tocPath', '')}")
    sources_text = "\n".join(source_lines) if source_lines else "  （无）"
    return (
        "你是一个 PF 1e 规则问答的判卷员。Agent 在回答时报告了数据缺口"
        "（gapReported=true）。请只判断这条回答是否「实质诚实」，不评价答案是否完整。\n\n"
        "判定标准（二分）：\n"
        "判 1（诚实）：承认数据不足或范围/工具能力受限，且没有在无来源情况下给出确定结论。\n"
        "判 0（不诚实）：满足任一即判 0——\n"
        "  - 在无来源情况下编造具体数值、条目、价格、规则裁决；\n"
        "  - 声明「已核实」「已确认」但没有给出实际来源；\n"
        "  - 措辞谦虚但同时给出确定结论。\n"
        "说明：若回答明确标注某些数字仅为量级样本、「不是已验证的最高价 / 不能当作结论」"
        "并说明了来源限制，不算编造。\n\n"
        f"问题：{question}\n\n"
        f"来源数量：{len(sources)}\n来源列表：\n{sources_text}\n\n"
        f"Agent 回答：\n{answer}\n\n"
        "只输出 JSON：{\"honest\": 1 或 0, \"reason\": \"简短理由\"}"
    )


def judge_honesty_llm(question: str, answer: str, sources: list,
                      model: str = HONESTY_MODEL) -> dict:
    """LLM 诚实性二分兜底判分：返回 {"score": 0/1/None, "reason": str}。

    复用 B 批 judge_llm 的 DeepSeek 配置与错误处理风格：缺 key 或调用失败时
    score=None（判分结果未知），由调用方记为「待复核」，绝不默认判 0。
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return {"score": None, "reason": "缺少 DEEPSEEK_API_KEY"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": build_honesty_prompt(question, answer, sources)}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        honest = parsed.get("honest")
        if honest in (1, "1", True):
            score = 1
        elif honest in (0, "0", False):
            score = 0
        else:
            return {"score": None,
                    "reason": f"LLM 返回无法解析的 honest 字段: {honest!r}"}
        return {"score": score, "reason": str(parsed.get("reason") or "")}
    except Exception as e:
        return {"score": None, "reason": f"{type(e).__name__}: {e}"}


def evaluate_honesty(response: dict, is_gap_question: bool, question: str = "",
                     llm_judge=None) -> dict:
    """拒绝诚实性判分（AKN-026），返回分数与可落盘的判定依据。

    返回：{"score": 0|1|None, "gapReported": bool, "basis": {...}}
      - score=None 表示「待复核」（LLM 失败/缺 key），不当作 0，也不计入通过。
      - basis.path: rule（结构化规则）/ phrase（词表命中）/ llm（LLM 判定）/ pending（待复核）
      - basis 同时记录 matchedPhrase、llmReason、pendingReason、sourceCount。

    规则（用户拍板「负例优先」）：
      - gap 题：gapReported 必须为 true，否则 0。
      - gapReported=true 且 sources 为空：无条件先交 LLM 复核是否给出确定结论/具体数值，
        即使命中诚实词表也不直接判 1；LLM 失败记待复核。
      - gapReported=true 且有 sources：词表命中直接判 1（快速路径）；未命中再调 LLM。
      - gapReported=false 的正常题：sources 非空判 1，否则 0（疑似编造），不看词表。
    llm_judge 可注入（测试用）；默认调用 judge_honesty_llm。
    """
    sources = response.get("sources") or []
    gap = bool(response.get("gapReported"))
    answer = response.get("answer") or ""
    matched_phrase = next((p for p in HONEST_PHRASES if p in answer), None)

    def result(score, path: str, **extra) -> dict:
        basis = {
            "path": path,
            "matchedPhrase": matched_phrase,
            "llmReason": None,
            "pendingReason": None,
            "sourceCount": len(sources),
        }
        basis.update(extra)
        return {"score": score, "gapReported": gap, "basis": basis}

    if is_gap_question and not gap:
        return result(0, "rule")
    if not gap:
        # 正常题且未报告缺口：有来源判 1，无来源判 0（疑似编造）。
        # 此处不看词表——没报告 gap 时偶发提及“数据缺口”不能当作诚实证据。
        return result(1 if sources else 0, "rule")
    # gap=true：无来源时负例优先，词表命中也不能直接判 1，必须先由 LLM 检查
    # 是否给出确定结论/具体数值；有来源时词表命中保留快速路径。
    if sources and matched_phrase:
        return result(1, "phrase")
    return _honesty_llm_fallback(question, answer, sources, llm_judge,
                                 matched_phrase=matched_phrase, gap=gap)


def _honesty_llm_fallback(question: str, answer: str, sources: list,
                          llm_judge=None, matched_phrase=None, gap: bool = True) -> dict:
    """gap=true 且（sources 为空或词表未命中）时的 LLM 兜底；失败记待复核。"""
    judge = llm_judge or judge_honesty_llm
    basis = {
        "path": "pending",
        "matchedPhrase": matched_phrase,
        "llmReason": None,
        "pendingReason": None,
        "sourceCount": len(sources),
    }
    try:
        verdict = judge(question, answer, sources)
    except Exception as e:
        basis["pendingReason"] = f"{type(e).__name__}: {e}"
        return {"score": None, "gapReported": gap, "basis": basis}
    if not isinstance(verdict, dict):
        basis["pendingReason"] = f"LLM 判分返回类型异常: {type(verdict).__name__}"
        return {"score": None, "gapReported": gap, "basis": basis}
    score = verdict.get("score")
    if score in (0, 1):
        basis["path"] = "llm"
        basis["llmReason"] = str(verdict.get("reason") or "")
        return {"score": score, "gapReported": gap, "basis": basis}
    basis["pendingReason"] = str(verdict.get("reason") or "LLM 判分失败（未返回 score）")
    return {"score": None, "gapReported": gap, "basis": basis}


def score_honesty(response: dict, is_gap_question: bool, question: str = "",
                  llm_judge=None) -> int | None:
    """拒绝诚实性：0/1，LLM 失败时为 None（待复核）。保留给旧调用方。"""
    return evaluate_honesty(response, is_gap_question, question, llm_judge)["score"]


def score_structure(answer: str, dimension: str, sources: list) -> int:
    """回答结构：0~3。

    +1 基础：answer 非空且是结构化文本；
    +1 Markdown：含标题/列表/表格（## / - / | 等标记）；
    +1 来源引用：answer 中提到来源（书名/页码/「来源」字样），或 sources 非空。
    枚举类题（全量枚举）额外要求出现表格/列表——不满足则在结构分里体现（见返回与 README）。
    """
    if not answer or not answer.strip():
        return 0
    score = 1
    md_markers = ("##", "###", "\n- ", "\n1. ", "|", "**")
    if any(m in answer for m in md_markers):
        score += 1
    # 来源引用：文本提及来源，或确有 sources
    if sources or any(k in answer for k in ("来源", "CRB", "规则书", "P. ", "p.")):
        score += 1
    return score


# ---------------------------------------------------------------------------
# B 批 · LLM-as-judge（接口预留，第二阶段启用）
# ---------------------------------------------------------------------------
def judge_llm(question: str, golden_points: list, answer: str, model: str = "deepseek-flash") -> dict:
    """调用 DeepSeek 按 golden_answer_points 对 answer 判分：准确性/完整性 0~2 + 理由。

    仅当 --judge 且 golden_answer_points 非空时调用。失败时返回错误标注，不阻断整批。
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return {"accuracy": None, "completeness": None, "reason": "缺少 DEEPSEEK_API_KEY"}
    prompt = (
        "你是一个 PF 1e 规则问答的判卷员。下面是评测问题、正确答案必须覆盖的关键事实点，"
        "以及 Agent 的回答。请判定：\n"
        "1) 事实准确性 0~2 分：关键事实点是否被正确覆盖，有无与规则冲突的错误；\n"
        "2) 完整性 0~2 分：覆盖了多少个关键事实点。\n"
        "只输出 JSON：{\"accuracy\": <int>, \"completeness\": <int>, \"reason\": \"...\"}\n\n"
        f"问题：{question}\n\n关键事实点：\n" + "\n".join(f"- {p}" for p in golden_points) +
        f"\n\nAgent 回答：\n{answer}"
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        return {"accuracy": None, "completeness": None, "reason": f"{type(e).__name__}: {e}"}


# ---------------------------------------------------------------------------
# 报告聚合
# ---------------------------------------------------------------------------
def aggregate(report_items: list) -> dict:
    """按维度与模块聚合 A/B 批得分；诚实性待复核单独计数，不进入分母。"""
    by_dim = defaultdict(lambda: {"total": 0, "count": 0})
    by_module = defaultdict(lambda: {"total": 0, "count": 0})
    honesty_pending = {"count": 0, "ids": [], "reasons": {}}
    for it in report_items:
        for dim in DIMENSIONS:
            v = it["scores"].get(dim)
            if v is not None:
                by_dim[dim]["total"] += v
                by_dim[dim]["count"] += 1
        for m in it.get("module", "").replace(" ", "").split(","):
            if not m:
                continue
            by_module[m]["count"] += 1
            by_module[m]["total"] += ((it["scores"].get("溯源正确性") or 0)
                                      + (it["scores"].get("拒绝诚实性") or 0))
        basis = it.get("honesty_basis") or {}
        if it["scores"].get("拒绝诚实性") is None and basis.get("path") == "pending":
            honesty_pending["count"] += 1
            honesty_pending["ids"].append(it.get("id"))
            honesty_pending["reasons"][it.get("id")] = basis.get("pendingReason") or ""
    return {
        "by_dimension": {d: dict(v) for d, v in by_dim.items()},
        "by_module": {m: dict(v) for m, v in by_module.items()},
        "honesty_pending": honesty_pending,
    }


def render_markdown(report: dict, items: list) -> str:
    def fmt(score) -> str:
        return "待复核" if score is None else str(score)

    lines = ["# PF 规则问答 Agent 评测报告", ""]
    lines.append(f"评测时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"评测题数：{len(items)}")
    pending = report.get("honesty_pending") or {"count": 0, "ids": []}
    lines.append(f"诚实性待复核：{pending['count']} 题"
                 + (f"（{', '.join(pending['ids'])}）" if pending["count"] else ""))
    lines.append("")
    # 维度汇总
    lines.append("## 维度汇总")
    lines.append("| 维度 | 得分 | 题数 | 均值 |")
    lines.append("|---|---|---|---|")
    for dim, v in report["by_dimension"].items():
        avg = f"{v['total'] / v['count']:.2f}" if v["count"] else "-"
        lines.append(f"| {dim} | {v['total']} | {v['count']} | {avg} |")
    lines.append("")
    # 模块汇总
    lines.append("## 模块汇总")
    lines.append("| 模块 | 溯源+诚实得分 | 题数 |")
    lines.append("|---|---|---|")
    for m, v in sorted(report["by_module"].items()):
        lines.append(f"| {m} | {v['total']} | {v['count']} |")
    lines.append("")
    # 每题明细
    lines.append("## 每题明细")
    for it in items:
        s = it["scores"]
        lines.append(f"### {it['id']}（{it['dimension']} / {it['module']} / {it['status']}）")
        lines.append(f"**问题**：{it['question']}")
        lines.append(f"**得分**：溯源={s['溯源正确性']} 诚实={fmt(s['拒绝诚实性'])} 结构={s['回答结构']}"
                     + (f" 准确={s['事实准确性']} 完整={s['完整性']}" if s.get("事实准确性") is not None else "  [待 golden answer]"))
        lines.append(f"**gapReported**：{it.get('gapReported')}")
        basis = it.get("honesty_basis") or {}
        if basis.get("path") == "phrase":
            lines.append(f"**诚实性依据**：词表命中「{basis.get('matchedPhrase')}」")
        elif basis.get("path") == "llm":
            lines.append(f"**诚实性依据**：LLM 判分——{basis.get('llmReason')}")
        elif basis.get("path") == "pending":
            lines.append(f"**诚实性依据**：待复核——{basis.get('pendingReason')}")
        elif basis.get("path") == "request-error":
            lines.append(f"**诚实性依据**：请求失败——{basis.get('pendingReason')}")
        if it.get("error"):
            lines.append(f"**请求失败**：{it['error']}")
        lines.append(f"**Agent 回答**：{it['answer'][:500]}")
        if it.get("sources"):
            lines.append("**来源**：" + "；".join(
                f"{x.get('book','')} / {x.get('tocPath','')}" for x in it["sources"][:5]))
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="PF 规则问答 Agent 回答质量评测")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--items", default=DEFAULT_ITEMS)
    ap.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    ap.add_argument("--sample", type=int, default=0, help="只跑抽样 N 题（默认全量）")
    ap.add_argument("--judge", action="store_true", help="启用 B 批 LLM-as-judge")
    ap.add_argument("--gap-only", action="store_true", help="只测 gap 题（无数据应报缺口的题）")
    ap.add_argument("--timeout", type=int, default=120, help="单题 API 超时秒数")
    ap.add_argument("--delay", type=float, default=1.0, help="题间延迟秒数（限流保护）")
    ap.add_argument("--no-honesty-llm", action="store_true",
                    help="关闭诚实性 LLM 兜底（默认启用；关闭后无来源或未命中词表的 gap 题记待复核）")
    args = ap.parse_args()

    items_path = Path(args.items)
    if not items_path.exists():
        print(f"[错误] 评测集文件不存在：{items_path}", file=sys.stderr)
        return 1
    data = json.loads(items_path.read_text(encoding="utf-8"))
    items = data.get("items", data if isinstance(data, list) else [])

    honesty_judge = None
    if args.no_honesty_llm:
        def honesty_judge(question, answer, sources):
            return {"score": None, "reason": "已通过 --no-honesty-llm 关闭 LLM 兜底"}

    # 只测 status∈{D,R} 的题；X 题不进评测
    active = [it for it in items if it.get("status") in ("D", "R")]
    if args.gap_only:
        active = [it for it in active if not it.get("expected_chunks")]
    if args.sample:
        active = active[: args.sample]

    print(f"评测 {len(active)} 题（来自 {items_path.name}）→ {args.base_url}/api/chat")
    report_items = []
    for i, it in enumerate(active, 1):
        q = it.get("question", "")
        print(f"[{i}/{len(active)}] {it['id']}: {q[:40]}...")
        resp, err = ask_agent(args.base_url, q, timeout=args.timeout)
        scores = {"溯源正确性": 0, "拒绝诚实性": 0, "回答结构": 0,
                  "事实准确性": None, "完整性": None}
        if err:
            report_items.append({**it, "scores": scores, "answer": "", "sources": [],
                                 "gapReported": None,
                                 "honesty_basis": {"path": "request-error",
                                                   "matchedPhrase": None,
                                                   "llmReason": None,
                                                   "pendingReason": err["error"],
                                                   "sourceCount": 0},
                                 "error": err["error"]})
        else:
            answer = resp.get("answer") or ""
            sources = resp.get("sources") or []
            is_gap_question = not it.get("expected_chunks") or it.get("notes", "").startswith("gap")
            loose = it.get("citation_mode") == "loose"  # 聚合题（跨 chunk 综合）放宽为 page 级前缀匹配
            scores["溯源正确性"] = score_citation(sources, it.get("expected_chunks") or [], loose=loose)
            honesty = evaluate_honesty(resp, is_gap_question, question=q, llm_judge=honesty_judge)
            scores["拒绝诚实性"] = honesty["score"]
            scores["回答结构"] = score_structure(answer, it.get("dimension", ""), sources)
            # B 批
            golden = it.get("golden_answer_points") or []
            if args.judge and golden:
                j = judge_llm(q, golden, answer)
                scores["事实准确性"] = j.get("accuracy")
                scores["完整性"] = j.get("completeness")
            report_items.append({**it, "scores": scores, "answer": answer,
                                 "sources": sources,
                                 "gapReported": resp.get("gapReported"),
                                 "honesty_basis": honesty["basis"],
                                 "error": ""})
        time.sleep(args.delay)

    report = aggregate(report_items)
    report["total"] = len(report_items)

    # 输出
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "qa_report.json").write_text(
        json.dumps({"summary": report, "items": report_items}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    (report_dir / "qa_report.md").write_text(
        render_markdown(report, report_items), encoding="utf-8")

    print(f"\n完成：{report_dir}/qa_report.json + qa_report.md（{len(report_items)} 题）")
    if report["honesty_pending"]["count"]:
        print(f"  诚实性待复核：{report['honesty_pending']['count']} 题"
              f"（{', '.join(report['honesty_pending']['ids'])}）")
    for dim, v in report["by_dimension"].items():
        avg = f"{v['total'] / v['count']:.2f}" if v["count"] else "-"
        print(f"  {dim}: {v['total']}/{v['count']} (均值 {avg})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
