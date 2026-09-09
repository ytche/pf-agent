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

五维度判分分两批：
    A 批 · 规则化（无需 golden answer，本脚本即可算）：
      1. 溯源正确性   sources[].tocPath/book 是否命中 expected_chunks（相等或前缀匹配）→ 0/1
      2. 拒绝诚实性   正常题断言 gapReported==false；sources 为空但未报告 gap → 疑似编造 → 0
      3. 回答结构     Markdown / 枚举题表格列表 / 带来源引用 → 0~3
    B 批 · LLM-as-judge（第二阶段 golden_answer_points 完成后再启用）：
      4. 事实准确性   judge(answer, golden_answer_points) → 0~2
      5. 完整性       覆盖 golden_answer_points 的比例 → 0~1
    golden_answer_points 为空时 B 批跳过并标注「待 golden answer」。

输出：
    qa_report.json   每题 5 维度得分 + 总分 + 明细
    qa_report.md     汇总表（按维度 / 按模块聚合）+ 每题明细
"""
import argparse
import json
import os
import sys
import time
import uuid
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
HONEST_PHRASES = ("未检索到", "没有找到", "未找到", "无法回答", "数据中不存在", "没有相关数据")


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
    """
    body = {"question": question, "conversationId": conversation_id or str(uuid.uuid4())}
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


def score_honesty(response: dict, is_gap_question: bool) -> int:
    """拒绝诚实性：0/1。

    - 正常题：sources 非空且 gapReported==false → 1；sources 为空且 gapReported==false
      （答了但没来源也没报缺口，疑似编造）→ 0。
    - gap 题（数据缺失，预期 reportDataGap）：gapReported==true 且 answer 含诚实短语 → 1。
    - 报告了 gap 但答案仍编造具体事实且无来源 → 0。
    """
    sources = response.get("sources") or []
    gap = bool(response.get("gapReported"))
    answer = response.get("answer") or ""
    if is_gap_question:
        if gap and any(p in answer for p in HONEST_PHRASES):
            return 1
        return 0
    # 正常题
    if gap:
        # 报告了 gap 但 answer 里没承认 → 不诚实
        return 1 if any(p in answer for p in HONEST_PHRASES) else 0
    return 1 if sources else 0


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
def judge_llm(question: str, golden_points: list, answer: str, model: str = "deepseek-chat") -> dict:
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
    """按维度与模块聚合 A/B 批得分。"""
    by_dim = defaultdict(lambda: {"total": 0, "count": 0})
    by_module = defaultdict(lambda: {"total": 0, "count": 0})
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
            by_module[m]["total"] += it["scores"].get("溯源正确性", 0) + it["scores"].get("拒绝诚实性", 0)
    return {
        "by_dimension": {d: dict(v) for d, v in by_dim.items()},
        "by_module": {m: dict(v) for m, v in by_module.items()},
    }


def render_markdown(report: dict, items: list) -> str:
    lines = ["# PF 规则问答 Agent 评测报告", ""]
    lines.append(f"评测时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"评测题数：{len(items)}")
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
        lines.append(f"**得分**：溯源={s['溯源正确性']} 诚实={s['拒绝诚实性']} 结构={s['回答结构']}"
                     + (f" 准确={s['事实准确性']} 完整={s['完整性']}" if s.get("事实准确性") is not None else "  [待 golden answer]"))
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
    args = ap.parse_args()

    items_path = Path(args.items)
    if not items_path.exists():
        print(f"[错误] 评测集文件不存在：{items_path}", file=sys.stderr)
        return 1
    data = json.loads(items_path.read_text(encoding="utf-8"))
    items = data.get("items", data if isinstance(data, list) else [])

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
                                 "error": err["error"]})
        else:
            answer = resp.get("answer") or ""
            sources = resp.get("sources") or []
            is_gap_question = not it.get("expected_chunks") or it.get("notes", "").startswith("gap")
            loose = it.get("citation_mode") == "loose"  # 聚合题（跨 chunk 综合）放宽为 page 级前缀匹配
            scores["溯源正确性"] = score_citation(sources, it.get("expected_chunks") or [], loose=loose)
            scores["拒绝诚实性"] = score_honesty(resp, is_gap_question)
            scores["回答结构"] = score_structure(answer, it.get("dimension", ""), sources)
            # B 批
            golden = it.get("golden_answer_points") or []
            if args.judge and golden:
                j = judge_llm(q, golden, answer)
                scores["事实准确性"] = j.get("accuracy")
                scores["完整性"] = j.get("completeness")
            report_items.append({**it, "scores": scores, "answer": answer,
                                 "sources": sources, "error": ""})
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
    for dim, v in report["by_dimension"].items():
        avg = f"{v['total'] / v['count']:.2f}" if v["count"] else "-"
        print(f"  {dim}: {v['total']}/{v['count']} (均值 {avg})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
