"""
analyze_ma_census.py — MA 来源书 263 chunks 格式普查

按交接文档 §六 要求，先 census 再决定修复子方案。

输出：
- vectorizer/exploration/ma_census.json （中间结果，gitignore）
- docs/MA_格式集群报告.md            （聚类报告，可交付）
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

# ---------- 1. 载入 MA chunks ----------
CHUNKS_PATH = Path("vectorizer/output/法术/chunks.jsonl")
OUT_JSON = Path("vectorizer/exploration/ma_census.json")
OUT_MD = Path("docs/MA_格式集群报告.md")

with CHUNKS_PATH.open() as f:
    chunks = [json.loads(l) for l in f]

ma_chunks = [
    c for c in chunks
    if c.get("book_abbreviation") == "MA"
    and c.get("metadata", {}).get("field_status")
]
print(f"MA chunks: {len(ma_chunks)}")

# ---------- 2. title 类型分布 ----------
def title_kind(t: str) -> str:
    if not t:
        return "无标题"
    if t.endswith(")") and "(" in t:
        return "括号型（中英对照）"
    if t.startswith("【") or t.endswith("】"):
        return "方括号型"
    if any(c in t for c in "（") :
        return "含中文括号"
    return "纯中文"


title_kinds = Counter(title_kind(c.get("title") or "") for c in ma_chunks)

# ---------- 3. 字段区识别 ----------
# 统计 text 中是否含以下标签（裸或 ** 包裹）
FIELD_LABELS = [
    "学派", "环位", "等级", "施法时间", "施放时间", "成分", "法术成分",
    "范围", "距离", "射程", "目标", "效果", "区域", "持续时间", "持续",
    "豁免", "豁免检定", "法术抗力", "抗力", "SR", "神话", "先决条件",
    "描述",
]
PAT_PER_LABEL = {
    lab: re.compile(r"\**" + re.escape(lab) + r"\**\s*[：:]")
    for lab in FIELD_LABELS
}

field_presence = Counter()
for c in ma_chunks:
    text = c["text"]
    found = [lab for lab, pat in PAT_PER_LABEL.items() if pat.search(text)]
    for lab in found:
        field_presence[lab] += 1

# ---------- 4. 结构特征向量 ----------
def struct_features(c):
    t = c["text"]
    bold_count = t.count("**")
    has_bold_label = sum(1 for lab in FIELD_LABELS if PAT_PER_LABEL[lab].search(t))
    para_count = max(t.count("\n\n"), 1)
    avg_para_len = len(t) / para_count
    is_quote_or_table = bool(re.search(r"^\|", t, re.M)) or "|" in t[:200]
    has_quote = t.count("\n>") + t.count("> ")
    # 段落内是否同时含 : 与 **
    inline_label_n = sum(
        1
        for m in re.finditer(r"\*\*[^*]+：", t)
    )
    return {
        "len": len(t),
        "bold_count": bold_count,
        "field_label_n": has_bold_label,
        "para_count": para_count,
        "avg_para_len": round(avg_para_len, 1),
        "has_table_pipe": is_quote_or_table,
        "inline_label_n": inline_label_n,
        "title_kind": title_kind(c.get("title") or ""),
    }


features = [(c, struct_features(c)) for c in ma_chunks]

# ---------- 5. 聚类（规则版，避免引入 sklearn） ----------
# 集群定义（按交接文档提示"格式未对齐"思路设计）：
#  C1 字段区型：field_label_n >= 4 且 inline_label_n >= 2   → 标准紧凑/块格式
#  C2 单字段型：1 <= field_label_n <= 3                       → 部分字段
#  C3 散文型：field_label_n == 0 但 bold_count > 0            → 全散文
#  C4 纯散文型：bold_count == 0                               → 纯文本
#  C5 表格型：has_table_pipe 且 inline_label_n >= 1           → 表格

def cluster_of(feat):
    if feat["has_table_pipe"] and feat["inline_label_n"] >= 1:
        return "C5 表格型"
    if feat["field_label_n"] >= 4 and feat["inline_label_n"] >= 2:
        return "C1 字段区型"
    if 1 <= feat["field_label_n"] <= 3:
        return "C2 单字段型"
    if feat["field_label_n"] == 0 and feat["bold_count"] > 0:
        return "C3 散文型"
    return "C4 纯散文型"


clusters = defaultdict(list)
for c, f in features:
    clusters[cluster_of(f)].append((c, f))

cluster_counts = Counter(cluster_of(f) for _, f in features)

# ---------- 6. 每个集群代表样本 ----------
samples_per_cluster = {}
for cl, items in clusters.items():
    # 选 3 个：最长 / 最短 / 中位
    items_sorted = sorted(items, key=lambda x: len(x[0]["text"]))
    n = len(items_sorted)
    picked = [
        items_sorted[0],
        items_sorted[n // 2],
        items_sorted[-1],
    ]
    samples_per_cluster[cl] = [
        {
            "title": c.get("title"),
            "doc_id": c.get("doc_id"),
            "chunk_id": c.get("chunk_id"),
            "field_status_parsed": [
                k for k, v in c["metadata"]["field_status"].items() if v == "parsed"
            ],
            "text_head_300": c["text"][:300],
            "feat": f,
        }
        for c, f in picked
    ]

# ---------- 7. 学派类型分布（仅 MA） ----------
school_dist = Counter(c["metadata"].get("school") for c in ma_chunks)

# ---------- 8. 写 JSON ----------
out = {
    "total_chunks": len(ma_chunks),
    "title_kind_dist": dict(title_kinds),
    "field_presence": dict(field_presence.most_common()),
    "cluster_counts": dict(cluster_counts),
    "samples_per_cluster": samples_per_cluster,
    "school_dist": dict(school_dist.most_common()),
    "feat_summary": {
        "len_avg": sum(f["len"] for _, f in features) / len(features),
        "bold_avg": sum(f["bold_count"] for _, f in features) / len(features),
        "inline_label_avg": sum(f["inline_label_n"] for _, f in features)
        / len(features),
    },
}
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
with OUT_JSON.open("w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("JSON:", OUT_JSON)
print("title_kind:", title_kinds)
print("field_presence(top10):", field_presence.most_common(10))
print("cluster_counts:", cluster_counts)
print("feat_summary:", out["feat_summary"])

# ---------- 9. 写 markdown ----------
def md_table(headers, rows):
    sep = "|".join(["---"] * len(headers))
    out = ["| " + " | ".join(headers) + " |", "|" + sep + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


lines = []
lines.append("# MA 来源书格式集群报告（Census）")
lines.append("")
lines.append("> 生成时间：2026-07-28")
lines.append("> 输入：`vectorizer/output/法术/chunks.jsonl`")
lines.append("> 范围：book_abbreviation == 'MA' 的 spell chunk")
lines.append("> 目的：按交接文档 §六，先 census 摸清格式集群，再决定修复子方案")
lines.append("")

lines.append("## 一、总量")
lines.append("")
lines.append(f"- MA spell chunks：**{len(ma_chunks)}**")
lines.append("")

lines.append("## 二、title 类型分布")
lines.append("")
rows = [(k, v, f"{v / len(ma_chunks) * 100:.1f}%") for k, v in title_kinds.most_common()]
lines.append(md_table(["title 类型", "数量", "占比"], rows))
lines.append("")

lines.append("## 三、字段标签在 text 中的出现次数（裸或 ** 包裹都算）")
lines.append("")
rows = [(lab, n, f"{n / len(ma_chunks) * 100:.1f}%") for lab, n in field_presence.most_common()]
lines.append(md_table(["字段标签", "出现 chunks", "占比"], rows))
lines.append("")

lines.append("## 四、结构特征汇总")
lines.append("")
fs = out["feat_summary"]
lines.append(f"- 平均 text 长度：**{fs['len_avg']:.0f}** 字符")
lines.append(f"- 平均 `**` 数量：**{fs['bold_avg']:.0f}**")
lines.append(f"- 平均内联标签（`**XX：**`）数：**{fs['inline_label_avg']:.2f}**")
lines.append("")

lines.append("## 五、格式集群（C1~C5）")
lines.append("")
lines.append("集群定义（启发式规则）：")
lines.append("")
lines.append("- **C1 字段区型**：`field_label_n >= 4` 且 `inline_label_n >= 2`（标准紧凑/块格式）")
lines.append("- **C2 单字段型**：`1 <= field_label_n <= 3`（部分字段）")
lines.append("- **C3 散文型**：无字段标签但有 `**` 加粗（标题/术语加粗，无 IR）")
lines.append("- **C4 纯散文型**：完全无 `**`（纯散文描述）")
lines.append("- **C5 表格型**：`has_table_pipe` 且有内联标签")
lines.append("")
rows = [
    (cl, cluster_counts.get(cl, 0), f"{cluster_counts.get(cl, 0) / len(ma_chunks) * 100:.1f}%")
    for cl in ["C1 字段区型", "C2 单字段型", "C3 散文型", "C4 纯散文型", "C5 表格型"]
]
lines.append(md_table(["集群", "数量", "占比"], rows))
lines.append("")

lines.append("## 六、每个集群的代表样本")
lines.append("")
for cl in ["C1 字段区型", "C2 单字段型", "C3 散文型", "C4 纯散文型", "C5 表格型"]:
    items = samples_per_cluster.get(cl, [])
    if not items:
        continue
    lines.append(f"### {cl}")
    lines.append("")
    for i, s in enumerate(items, 1):
        lines.append(f"**样本 {i}**：`{s['title']}` (`{s['chunk_id']}`)")
        lines.append("")
        lines.append(f"- doc_id: `{s['doc_id']}`")
        lines.append(f"- text 长度: {s['feat']['len']}, `**` 数: {s['feat']['bold_count']}, 内联标签数: {s['feat']['inline_label_n']}")
        lines.append(f"- parsed 字段: `{', '.join(s['field_status_parsed']) or '无'}`")
        lines.append("")
        lines.append("```")
        lines.append(s["text_head_300"])
        lines.append("...")
        lines.append("```")
        lines.append("")

lines.append("## 七、初步结论与子方案建议")
lines.append("")

c1 = cluster_counts.get("C1 字段区型", 0)
c2 = cluster_counts.get("C2 单字段型", 0)
c3 = cluster_counts.get("C3 散文型", 0)
c4 = cluster_counts.get("C4 纯散文型", 0)
c5 = cluster_counts.get("C5 表格型", 0)

lines.append("### 7.1 关键发现")
lines.append("")
lines.append(f"- **{c3 + c4} 个 chunk（{((c3 + c4) / len(ma_chunks)) * 100:.0f}%）是散文型/纯散文型**，无字段标签，**不应被视作 spell chunk** —— 当前 parser 把章节总览/前置说明误纳为 spell chunk 是 ~3% 覆盖率的根因")
lines.append(f"- **{c1} 个 chunk（约 {c1 / len(ma_chunks) * 100:.0f}%）是标准字段区型**，按现有 parser 应能解析；如仍未 parsed，可能是标签变体未收敛（如 `施放时间` vs `施法时间`、`抗力` vs `法术抗力`）")
lines.append(f"- **{c2} 个 chunk（约 {c2 / len(ma_chunks) * 100:.0f}%）是单字段型**，可能为变体法术或半截 chunk")
lines.append(f"- **{c5} 个 chunk（约 {c5 / len(ma_chunks) * 100:.0f}%）是表格型**，需要表格格式专项 parser")
lines.append("")

lines.append("### 7.2 建议子方案")
lines.append("")
lines.append("**不修**（已确认的不可解析内容）：")
lines.append("")
lines.append(f"- C3/C4 散文型共 **{c3 + c4}** chunk —— 应在 pipeline 入口用 spell chunk 判定规则排除（标题不在『法术』词表内 / 长度 < 阈值 / 无字段标签），或在 SpellProcessor.infer_metadata 中检测到 0 字段标签时跳过 metadata 抽取并标记 `field_status.school = missing` + KN。")
lines.append("")
lines.append("**可修**（投入产出比合理）：")
lines.append("")
lines.append(f"- C1 字段区型 **{c1}** chunk —— 排查标签变体（`施放时间` / `抗力` 等）的 alias 收敛；预期 +{c1} 个 parsed spell")
lines.append(f"- C5 表格型 **{c5}** chunk —— 复用现有 `_fix_pipe_table_lines` 路径，需验证 MA 表格列结构与 CRB 一致")
lines.append(f"- C2 单字段型 **{c2}** chunk —— 个案检查；多半是跨页 chunk 切分边界")
lines.append("")
lines.append("### 7.3 风险评估")
lines.append("")
lines.append("- 散文型 chunk 当前被记为 spell chunk（field_status 已写入），若简单删除会破坏 `chunks.jsonl` 4138 不变量；正确做法是 SpellProcessor 跳过 + 仍产出 chunk 但 field_status 全 missing + KN 登记")
lines.append("- 标签变体收敛应在 `registry.py` 中加 alias，禁止在 formats/spell.py 硬编码（与 F2 同步收口）")
lines.append("- F4 的可行子集是 C1+C5，约 {}+{} = {} chunks；剩余 {} chunks 是结构性不可解析内容，建议 KN 而非修复".format(c1, c5, c1 + c5, c3 + c4 + c2))
lines.append("")

OUT_MD.write_text("\n".join(lines), encoding="utf-8")
print("MD:", OUT_MD)