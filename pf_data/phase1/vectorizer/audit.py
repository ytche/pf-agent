"""
audit.py — 通用审计引擎（⚠️ 已弃用，仅保留代码不删除）

设计初衷：pipeline 进程内第四环（docstring 定义链「diagnostics（门禁）→ formats
（归一化）→ processors（分块）→ audit（审计）」，创建于 2fbc2df 骨架 / 8cd37b3
Tier 2/3）——但从未被 pipeline.run() 接线调用，实际验收走 verify_*.py 脚本路线
（verify_spells → verify_feats 复制式落地，进程外编排）。

弃用原因（v2.2 设计评审问题 E 拍板）：
  1. 进程内审计环从未接线，属死代码骨架；实际采用且被 CI 依赖的验收形态是
     verify_*.py（进程外独立验收 + 编排保证）
  2. 评审定调：verify 公共框架（vectorizer/verify/base.py 的 VerifyBase + checks
     注册表）为唯一验收形态，禁止 copy 扩展——audit 引擎路线不再演进
  3. Tier 1 六条绝对断言已并入 verify/base.py 的 GENERIC_CHECKS（按需启用）
  4. Tier 2 声明式规则的消费方缺位（get_audit_rules 无注入方），其理念由
     verify 框架的 checks 注册表承接

保留不删除：formats/base.py 的 get_audit_rules 抽象方法及 spell.py 实现为冻结
模块代码，随本文件一同保留（后续模块验收不依赖本引擎）。

职责（历史）：
  - 对 pipeline 输出的 chunks.jsonl 进行三级审计
  - Tier 1：绝对断言（告警 = 一定有问题）
  - Tier 2：声明式预期（来自各 formats/*.py）
  - Tier 3：统计偏差（仅在基线 locked 后生效）

设计（历史）：
  - 审计引擎类目无关，类目特定规则由 formats/*.py 注入
  - 输出审计报告（AuditReport）供人工复核
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AuditFinding:
    """单条审计发现"""
    tier: int  # 1 / 2 / 3
    rule: str
    chunk_id: str
    message: str
    severity: str = "WARN"  # WARN / ERROR


@dataclass
class AuditReport:
    """审计报告"""
    tier1_findings: List[AuditFinding] = field(default_factory=list)
    tier2_findings: List[AuditFinding] = field(default_factory=list)
    tier3_findings: List[AuditFinding] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(f.severity == "ERROR" for f in self.all_findings)

    @property
    def all_findings(self):
        return self.tier1_findings + self.tier2_findings + self.tier3_findings

    def summary(self) -> str:
        return (
            f"Tier 1: {len(self.tier1_findings)} 发现 | "
            f"Tier 2: {len(self.tier2_findings)} 发现 | "
            f"Tier 3: {len(self.tier3_findings)} 发现"
        )


# Tier 1 绝对断言（通用，类目无关）
TIER1_CHECKS: List[tuple] = [
    ("url_in_title",        lambda c: bool(re.search(r'https?://', c.get("title", "")))),
    ("unknown_placeholder", lambda c: "【?】" in c.get("title", "") or "【?】" in c.get("text", "")),
    ("bold_mismatch",       lambda c: c.get("text", "").count("**") % 2 != 0),
    ("unknown_source_book", lambda c: c.get("book_abbreviation", "?") in ("?", "", None)),
    ("missing_category_id", lambda c: not c.get("class_name") and not c.get("metadata", {}).get("school")),
    ("empty_text",          lambda c: len(c.get("text", "").strip()) < 10),
]


class Auditor:
    """⚠️ 已弃用 — 审计引擎（pipeline 进程内第四环，从未接线）。

    详见模块 docstring：实际验收形态为 verify 公共框架（VerifyBase），
    Tier 1 已并入 GENERIC_CHECKS。代码保留供冻结模块（法术）参考，不删除。
    """

    def __init__(self, tier2_rules: Optional[Dict] = None, baseline_path: Optional[Path] = None):
        """
        Args:
            tier2_rules: 由 formats/*.py 注入的声明式规则
            baseline_path: Tier 3 基线文件路径（.json）
        """
        self.tier2_rules = tier2_rules or {}
        self.baseline_path = baseline_path

    def audit(self, chunks_path: Path) -> AuditReport:
        """审计 chunks.jsonl 文件，返回审计报告"""
        with open(chunks_path, encoding="utf-8") as f:
            chunks = [json.loads(line) for line in f if line.strip()]

        report = AuditReport()
        report.tier1_findings = self._run_tier1(chunks)
        report.tier2_findings = self._run_tier2(chunks)
        report.tier3_findings = self._run_tier3(chunks)
        return report

    def _run_tier1(self, chunks: List[dict]) -> List[AuditFinding]:
        """Tier 1：绝对断言"""
        findings = []
        for chunk in chunks:
            cid = chunk.get("chunk_id", "?")
            for rule_name, check_fn in TIER1_CHECKS:
                if check_fn(chunk):
                    findings.append(AuditFinding(
                        tier=1, rule=rule_name, chunk_id=cid,
                        message=f"违反 {rule_name}",
                        severity="ERROR",
                    ))
        return findings

    def _run_tier2(self, chunks: List[dict]) -> List[AuditFinding]:
        """Tier 2：声明式预期 — 遍历 tier2_rules 对 chunks 做声明式检查。

        支持的规则键：
          - min_spells_per_book: dict[str, int]  每本书最少法术数
          - required_schools: list[str]          必须出现的学派
          - unknown_school_max_pct: float         未知学派最大占比
          - empty_description_max: int            空描述最大数量
        """
        findings = []
        if not self.tier2_rules:
            return findings

        # min_spells_per_book
        min_spells = self.tier2_rules.get("min_spells_per_book", {})
        if min_spells:
            by_book: Dict[str, int] = {}
            for chunk in chunks:
                book = chunk.get("book_abbreviation", "?")
                by_book[book] = by_book.get(book, 0) + 1
            for book, minimum in min_spells.items():
                actual = by_book.get(book, 0)
                if actual < minimum:
                    findings.append(AuditFinding(
                        tier=2, rule="min_spells_per_book", chunk_id=f"book:{book}",
                        message=f"{book} 仅有 {actual} 个法术（预期 ≥{minimum}）",
                        severity="WARN",
                    ))

        # required_schools
        required_schools = self.tier2_rules.get("required_schools", [])
        if required_schools:
            all_schools: set[str] = set()
            for chunk in chunks:
                school = chunk.get("metadata", {}).get("school", "")
                if school:
                    all_schools.add(school)
            for school in required_schools:
                if school not in all_schools:
                    findings.append(AuditFinding(
                        tier=2, rule="required_schools", chunk_id="all",
                        message=f"缺少学派: {school}（现有: {sorted(all_schools)}）",
                        severity="WARN",
                    ))

        # unknown_school_max_pct
        max_pct = self.tier2_rules.get("unknown_school_max_pct")
        if max_pct is not None:
            total = len(chunks)
            unknown = sum(
                1 for c in chunks
                if not c.get("metadata", {}).get("school")
            )
            if total > 0 and unknown / total > max_pct:
                findings.append(AuditFinding(
                    tier=2, rule="unknown_school_max_pct", chunk_id="all",
                    message=f"未知学派占比 {unknown/total*100:.1f}%（{unknown}/{total}），预期 ≤{max_pct*100:.0f}%",
                    severity="WARN",
                ))

        # empty_description_max
        max_empty = self.tier2_rules.get("empty_description_max")
        if max_empty is not None:
            empty_count = sum(
                1 for c in chunks
                if len(c.get("text", "").strip()) < 10
            )
            if empty_count > max_empty:
                findings.append(AuditFinding(
                    tier=2, rule="empty_description_max", chunk_id="all",
                    message=f"空描述 {empty_count} 个（预期 ≤{max_empty}）",
                    severity="WARN",
                ))

        return findings

    def _run_tier3(self, chunks: List[dict]) -> List[AuditFinding]:
        """Tier 3：统计偏差 — 与基线 法术_per_file.jsonl 比对 chunk 数。

        对每个文件，对比 actual vs estimated_count，偏离 ±20% → WARN。
        baseline_path 指向 法术_per_file.jsonl（Phase 0 恢复的基线）。
        """
        findings = []
        if not self.baseline_path or not self.baseline_path.exists():
            return findings

        try:
            with open(self.baseline_path, encoding="utf-8") as f:
                baseline = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("无法加载基线文件 %s: %s", self.baseline_path, e)
            return findings

        # 基线格式: {"files": [{"doc_id": ..., "estimated_count": ..., "count_method": ...}, ...]}
        files = baseline.get("files", [])
        if not files:
            return findings

        baseline_by_doc = {}
        for entry in files:
            doc_id = entry.get("doc_id", "")
            estimated = entry.get("estimated_count")
            if doc_id and estimated is not None:
                baseline_by_doc[doc_id] = estimated

        # 统计实际 chunk 数
        from collections import Counter
        actual_by_doc = Counter(chunk.get("doc_id", "?") for chunk in chunks)

        for doc_id, estimated in baseline_by_doc.items():
            actual = actual_by_doc.get(doc_id, 0)
            if estimated == 0:
                if actual > 0:
                    findings.append(AuditFinding(
                        tier=3, rule="unexpected_chunks", chunk_id=f"doc:{doc_id}",
                        message=f"{doc_id}: 预期 0 chunk，实际 {actual}",
                        severity="WARN",
                    ))
                continue

            deviation = abs(actual - estimated) / estimated
            if deviation > 0.2:
                direction = "多" if actual > estimated else "少"
                findings.append(AuditFinding(
                    tier=3, rule="chunk_count_deviation", chunk_id=f"doc:{doc_id}",
                    message=f"{doc_id}: 预期 {estimated}，实际 {actual}（偏{direction} {deviation*100:.0f}%）",
                    severity="WARN",
                ))

        return findings


def main():
    """CLI 入口"""
    import argparse
    parser = argparse.ArgumentParser(description="审计 chunks.jsonl")
    parser.add_argument("chunks_path", type=Path, help="chunks.jsonl 路径")
    parser.add_argument("--baseline", type=Path, help="基线文件路径")
    args = parser.parse_args()

    auditor = Auditor(baseline_path=args.baseline)
    report = auditor.audit(args.chunks_path)
    print(report.summary())
    if report.has_errors:
        for f in report.all_findings:
            if f.severity == "ERROR":
                print(f"  ERROR [{f.rule}] {f.chunk_id}: {f.message}")
        exit(1)


if __name__ == "__main__":
    main()
