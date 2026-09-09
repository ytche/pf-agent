#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""专长模块 Prepare Phase 勘探产出校验脚本。

校验 per_file_BNN.jsonl 是否满足《Prepare_Phase_交接文档.md》§四 字段硬要求与 §八 完成标准。

用法：
    python3 verify_prepare.py                # 全量校验 17 批并写报告
    python3 verify_prepare.py --batches 1,4,7  # 只校验指定批次（试点用，不写报告）

检查项（1~8 阻断，9 仅输出对账清单）：
    1. per_file_BNN.jsonl 存在且每行 JSON 合法
    2. 每批 file 集合精确等于 manifest（无缺/无多/无重复）
    3. 16 个必填键齐全且非 null
    4. doc_role 五选一
    5. estimated_count 为非负整数；count_basis 非空且 >=10 字
    6. estimated_count>0 时 title_forms 非空，每项含非空 pattern 与 raw_example（逐字原始行）
    7. traps[].kind 属于稳定词表或以「其他：」开头；每个 trap 有非空 risk
    8. 0 字节源文件对应 estimated_count == 0
    9. 与 machine_scan.jsonl 对账，偏差 >20% 进 deviations 清单
"""

import argparse
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PHASE1 = os.path.abspath(os.path.join(HERE, "..", "..", ".."))  # pf_data/phase1
SRC_ROOT = os.path.join(PHASE1, "pf_rules_md_organized")

BATCHES_JSON = os.path.join(HERE, "prepare_batches.json")
MACHINE_SCAN = os.path.join(HERE, "machine_scan.jsonl")
REPORT_PATH = os.path.join(HERE, "prepare_verify_report.md")

REQUIRED_KEYS = [
    "file", "batch", "size_kb", "doc_role", "title_forms", "field_layout",
    "field_labels_seen", "feat_type_tags", "estimated_count", "count_basis",
    "first_entry", "last_entry", "traps", "dedup_note", "format_cluster_hint",
    "notes",
]

VALID_DOC_ROLES = {"overview", "index_table", "aggregation", "detail", "mixed"}

# 交接文档 §四 稳定陷阱词表
VALID_TRAP_KINDS = {
    "断行英文名", "链接陷阱", "表格双语分行", "译者行", "PFS图标",
    "重复条目", "非条目表格", "无标题正文",
}

COUNT_BASIS_MIN_LEN = 10
DEVIATION_THRESHOLD = 0.20


def load_manifest():
    """返回 {batch: [相对 pf_rules_md_organized 的文件名]}。"""
    with open(BATCHES_JSON, encoding="utf-8") as f:
        batches = json.load(f)
    manifest = {}
    for b in batches:
        rels = []
        for p in b["files"]:
            # manifest 里是 pf_rules_md_organized/xxx，统一去掉前缀
            rels.append(p.split("pf_rules_md_organized/", 1)[-1])
        manifest[b["batch"]] = rels
    return manifest


def load_machine_scan():
    scan = {}
    if not os.path.exists(MACHINE_SCAN):
        return scan
    with open(MACHINE_SCAN, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            scan[rec["file"]] = rec
    return scan


def norm_file(value):
    """勘探记录里的 file 允许带/不带 pf_rules_md_organized/ 前缀。"""
    return str(value).split("pf_rules_md_organized/", 1)[-1].lstrip("./")


def read_batch(batch_no):
    """读取 per_file_BNN.jsonl，返回 (records, errors)。"""
    path = os.path.join(HERE, "per_file_B%02d.jsonl" % batch_no)
    errors = []
    if not os.path.exists(path):
        return None, ["B%02d: 缺少产出文件 %s" % (batch_no, os.path.basename(path))]
    records = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                # 显式错误处理：定位到具体行，便于子代理返工
                errors.append("B%02d L%d: JSON 解析失败 — %s" % (batch_no, lineno, exc))
    return records, errors


def check_batch(batch_no, expect_files, records, scan):
    """对单批做检查 2~9，返回 (errors, deviations, stats)。"""
    errors, deviations = [], []
    stats = {"doc_roles": Counter(), "trap_kinds": Counter(), "count": 0,
             "html_consulted": [], "files": 0}

    got_files = [norm_file(r.get("file", "")) for r in records]
    dup = [f for f, n in Counter(got_files).items() if n > 1]
    missing = sorted(set(expect_files) - set(got_files))
    extra = sorted(set(got_files) - set(expect_files))
    if len(records) != len(expect_files):
        errors.append("B%02d: 行数 %d != manifest 文件数 %d"
                      % (batch_no, len(records), len(expect_files)))
    if dup:
        errors.append("B%02d: file 重复 — %s" % (batch_no, dup))
    if missing:
        errors.append("B%02d: 缺少文件记录 — %s" % (batch_no, missing))
    if extra:
        errors.append("B%02d: 出现 manifest 之外的文件 — %s" % (batch_no, extra))

    for rec in records:
        fname = norm_file(rec.get("file", "<无 file 字段>"))
        tag = "B%02d %s" % (batch_no, fname)

        # 3. 必填键
        for key in REQUIRED_KEYS:
            if key not in rec:
                errors.append("%s: 缺少必填字段 %s" % (tag, key))
            elif rec[key] is None:
                errors.append("%s: 字段 %s 为 null" % (tag, key))

        if rec.get("batch") != batch_no:
            errors.append("%s: batch 字段为 %r，应为 %d" % (tag, rec.get("batch"), batch_no))

        # 4. doc_role
        role = rec.get("doc_role")
        if role not in VALID_DOC_ROLES:
            errors.append("%s: doc_role %r 非法（应为 %s）" % (tag, role, sorted(VALID_DOC_ROLES)))
        else:
            stats["doc_roles"][role] += 1

        # 5. estimated_count / count_basis
        est = rec.get("estimated_count")
        if not isinstance(est, int) or isinstance(est, bool) or est < 0:
            errors.append("%s: estimated_count %r 不是非负整数" % (tag, est))
            est = 0
        stats["count"] += est
        basis = (rec.get("count_basis") or "").strip()
        if len(basis) < COUNT_BASIS_MIN_LEN:
            errors.append("%s: count_basis 过短或为空（%d 字）— 空口数字视为未交付"
                          % (tag, len(basis)))

        # 6. title_forms
        forms = rec.get("title_forms")
        if est > 0:
            if not isinstance(forms, list) or not forms:
                errors.append("%s: estimated_count=%d 但 title_forms 为空" % (tag, est))
            else:
                for i, form in enumerate(forms):
                    if not isinstance(form, dict) or not str(form.get("pattern", "")).strip():
                        errors.append("%s: title_forms[%d] 缺少非空 pattern" % (tag, i))
                        continue
                    # raw_example 是硬要求：pattern 只写"逻辑形态"会漏掉断行/尾部噪声，
                    # 拿去写正则必然失配（page_196 实测标题 100% 断成两行）。
                    raw = form.get("raw_example")
                    if isinstance(raw, list):
                        raw = "".join(str(x) for x in raw)
                    if not str(raw or "").strip():
                        errors.append("%s: title_forms[%d] 缺少 raw_example（源文件逐字原始行）"
                                      % (tag, i))

        # 7. traps
        traps = rec.get("traps")
        if traps is None:
            traps = []
        if not isinstance(traps, list):
            errors.append("%s: traps 应为数组" % tag)
            traps = []
        for i, trap in enumerate(traps):
            if not isinstance(trap, dict):
                errors.append("%s: traps[%d] 应为对象" % (tag, i))
                continue
            kind = str(trap.get("kind", "")).strip()
            if kind not in VALID_TRAP_KINDS and not kind.startswith("其他："):
                errors.append("%s: traps[%d].kind %r 不在词表且未用「其他：」前缀" % (tag, i, kind))
            stats["trap_kinds"][kind] += 1
            if not str(trap.get("risk", "")).strip():
                errors.append("%s: traps[%d] 缺少 risk（必须说明会怎么坑解析器）" % (tag, i))
            if trap.get("html_consulted") is True:
                stats["html_consulted"].append(fname)

        # 8. 空文件
        src = os.path.join(SRC_ROOT, fname)
        if os.path.exists(src) and os.path.getsize(src) == 0 and est != 0:
            errors.append("%s: 源文件 0 字节但 estimated_count=%d" % (tag, est))

        # 9. 对账（非阻断）
        mrec = scan.get(fname)
        if mrec:
            labels = mrec.get("field_labels") or {}
            baseline = max([mrec.get("title_candidates", 0)] + list(labels.values()) + [0])
            if baseline == 0 and est == 0:
                pass
            else:
                denom = max(baseline, est, 1)
                dev = abs(est - baseline) / denom
                if dev > DEVIATION_THRESHOLD:
                    deviations.append({
                        "file": fname, "batch": batch_no, "estimated_count": est,
                        "machine_baseline": baseline, "deviation": round(dev, 2),
                        "doc_role": role,
                    })
        stats["files"] += 1

    return errors, deviations, stats


def write_report(all_stats, deviations, errors, batch_summary):
    lines = ["# 专长模块 Prepare Phase 勘探产出校验报告", ""]
    lines.append("- 校验批次：%d" % len(batch_summary))
    lines.append("- 勘探记录行数：%d" % sum(s["files"] for s in all_stats))
    lines.append("- estimated_count 合计：%d" % sum(s["count"] for s in all_stats))
    lines.append("- 阻断错误：%d" % len(errors))
    lines.append("- 对账偏差 >%d%% 文件数：%d" % (int(DEVIATION_THRESHOLD * 100), len(deviations)))
    lines.append("")

    roles = Counter()
    traps = Counter()
    html_files = []
    for s in all_stats:
        roles.update(s["doc_roles"])
        traps.update(s["trap_kinds"])
        html_files.extend(s["html_consulted"])

    lines += ["## doc_role 分布", "", "| doc_role | 文件数 |", "|---|---|"]
    for role, n in roles.most_common():
        lines.append("| %s | %d |" % (role, n))
    lines.append("")

    lines += ["## 陷阱类型频次", "", "| kind | 次数 |", "|---|---|"]
    for kind, n in traps.most_common():
        lines.append("| %s | %d |" % (kind, n))
    lines.append("")

    lines += ["## 逐批统计", "", "| 批 | 文件数 | 条目合计 |", "|---|---|---|"]
    for batch_no, files, count in batch_summary:
        lines.append("| B%02d | %d | %d |" % (batch_no, files, count))
    lines.append("")

    lines += ["## 对账偏差清单（>%d%%，需 k3 抽样复读）" % int(DEVIATION_THRESHOLD * 100), ""]
    if deviations:
        lines += ["| 文件 | 批 | doc_role | 勘探 | 机检基准 | 偏差 |", "|---|---|---|---|---|---|"]
        for d in sorted(deviations, key=lambda x: -x["deviation"]):
            lines.append("| %s | B%02d | %s | %d | %d | %.0f%% |" % (
                d["file"], d["batch"], d["doc_role"], d["estimated_count"],
                d["machine_baseline"], d["deviation"] * 100))
    else:
        lines.append("无。")
    lines.append("")

    lines += ["## 触发 HTML 回溯的文件", ""]
    lines.append("、".join(sorted(set(html_files))) if html_files else "无。")
    lines.append("")

    if errors:
        lines += ["## 阻断错误明细", ""]
        lines += ["- %s" % e for e in errors]
        lines.append("")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="专长 Prepare Phase 勘探产出校验")
    parser.add_argument("--batches", help="只校验指定批次，逗号分隔（如 1,4,7）")
    args = parser.parse_args()

    manifest = load_manifest()
    scan = load_machine_scan()
    if not scan:
        print("[警告] 未找到 machine_scan.jsonl，跳过对账检查", file=sys.stderr)

    if args.batches:
        targets = [int(x) for x in args.batches.split(",") if x.strip()]
        partial = True
    else:
        targets = sorted(manifest)
        partial = False

    all_errors, all_devs, all_stats, batch_summary = [], [], [], []
    for batch_no in targets:
        if batch_no not in manifest:
            all_errors.append("B%02d: manifest 中无此批次" % batch_no)
            continue
        records, errs = read_batch(batch_no)
        all_errors.extend(errs)
        if records is None:
            continue
        errs, devs, stats = check_batch(batch_no, manifest[batch_no], records, scan)
        all_errors.extend(errs)
        all_devs.extend(devs)
        all_stats.append(stats)
        batch_summary.append((batch_no, stats["files"], stats["count"]))
        print("B%02d: %d/%d 行, 条目 %d, 错误 %d, 偏差 %d"
              % (batch_no, stats["files"], len(manifest[batch_no]), stats["count"],
                 len(errs), len(devs)))

    total_files = sum(s["files"] for s in all_stats)
    total_expect = sum(len(manifest[b]) for b in targets if b in manifest)
    print("-" * 60)
    print("批次 %d/%d，记录 %d/%d，条目合计 %d"
          % (len(batch_summary), len(targets), total_files, total_expect,
             sum(s["count"] for s in all_stats)))
    print("对账偏差 >%d%%：%d 个文件" % (int(DEVIATION_THRESHOLD * 100), len(all_devs)))

    if not partial:
        write_report(all_stats, all_devs, all_errors, batch_summary)
        print("报告已写入 %s" % os.path.relpath(REPORT_PATH, PHASE1))

    if all_errors:
        print("\n❌ 阻断错误 %d 条：" % len(all_errors))
        for e in all_errors[:60]:
            print("  - %s" % e)
        if len(all_errors) > 60:
            print("  ...（另有 %d 条，见报告）" % (len(all_errors) - 60))
        return 1
    print("\n✅ 8 项阻断检查全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
