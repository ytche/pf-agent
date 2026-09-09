"""
逐文件 Chunk 数验证测试
基于 Pre-Phase 勘探结果（法术_per_file.jsonl）校验实际输出 chunk 数。

TDD 不变量（不能因实现难修而被修改）：
- 任何法术文件的实际 chunk 数应与 estimated_count 偏差在容差内
- count_method 中描述的算术加和（如 "X（管道）+ Y（加粗）"）应等于 estimated_count
- 非法术文件应登记到 NON_SPELL_FILES 或 KNOWN_UNCOVERED_FORMATS
"""

import json
import re
from collections import Counter
from pathlib import Path
import pytest

NON_SPELL_FILES = {
    "Spell index": "索引文件",
    "反派法典VC_神秘仪式": "神秘仪式（ritual）",
    "奈多_神秘仪式": "神秘仪式（ritual）",
    "惧怖冒险HA_神秘仪式": "神秘仪式（ritual）",
    "极限荒野UW_自然仪式": "神秘仪式（ritual）",
    "屠龙者手册_世界名著": "吟游诗人杰作（masterpiece）",
}

# Phase 0 修复：保留为 dict 框架，作为登记已知未覆盖文件的入口；
# 当前为空，但任何"已确认不解析"的源文件应登记在此，避免下次回归。
KNOWN_UNCOVERED_FORMATS: dict[str, str] = {}

PER_FILE_PATH = Path("vectorizer/exploration/法术/法术_per_file.jsonl")
CHUNKS_PATH = Path("vectorizer/output/法术/chunks.jsonl")


def load_per_file():
    entries = []
    with open(PER_FILE_PATH) as f:
        for line in f:
            entries.append(json.loads(line.strip()))
    return entries


def load_actual_counts():
    if not CHUNKS_PATH.exists():
        # 产物级集成测试需要法术 pipeline 产物（gitignored，CI checkout 拿不到）。
        # CI 上产物断言职责由「重跑 pipeline + verify」步骤承担，此处跳过环境守卫
        # （不改断言逻辑，产物齐全的本地环境仍全量执行）。
        pytest.skip(f"法术产物缺失: {CHUNKS_PATH}（CI 环境，产物断言由 pipeline+verify 覆盖）")
    chunks = []
    with open(CHUNKS_PATH) as f:
        for line in f:
            chunks.append(json.loads(line.strip()))
    return Counter(c["doc_id"] for c in chunks if c["doc_id"] != "Spell index")


def _stem(path_like: str) -> str:
    return path_like.replace("\\", "/").rstrip(".md").split("/")[-1]


class TestPerFileChunkCount:
    _per_file = None
    _actual_counts = None

    @classmethod
    def _get_per_file(cls):
        if cls._per_file is None:
            cls._per_file = load_per_file()
        return cls._per_file

    @classmethod
    def _get_actual_counts(cls):
        if cls._actual_counts is None:
            cls._actual_counts = load_actual_counts()
        return cls._actual_counts

    def test_per_file_coverage_complete(self):
        seen = set()
        for entry in self._get_per_file():
            seen.add(_stem(entry["file"]))
        assert len(seen) >= 148

    def test_all_uncovered_tracked(self):
        actual = self._get_actual_counts()
        untracked = []
        seen = set()
        for entry in self._get_per_file():
            stem = _stem(entry["file"])
            if stem in seen: continue
            seen.add(stem)
            if stem in NON_SPELL_FILES or stem in KNOWN_UNCOVERED_FORMATS: continue
            if entry.get("estimated_count", 0) == 0: continue
            if actual.get(stem, 0) == 0:
                untracked.append(f"{entry['file']}: 预测 {entry['estimated_count']} → 实际 0")
        assert not untracked, "零产出文件未被收录:\n  " + "\n  ".join(untracked)

    @staticmethod
    def _tolerance(expected: int) -> int:
        if expected >= 50: return max(5, int(expected * 0.2))
        elif expected >= 10: return max(3, int(expected * 0.3))
        else: return max(1, int(expected * 0.5))

    def _build_estimate_map(self):
        mapping = {}
        for entry in self._get_per_file():
            stem = _stem(entry["file"])
            if stem not in mapping:
                mapping[stem] = entry.get("estimated_count", 0)
        return mapping

    def test_covered_files_match_estimate(self):
        actual = self._get_actual_counts()
        estimates = self._build_estimate_map()
        failures = []
        for stem, expected in estimates.items():
            if stem in NON_SPELL_FILES or stem in KNOWN_UNCOVERED_FORMATS: continue
            if expected == 0: continue
            count = actual.get(stem, 0)
            if count == 0:
                failures.append(f"{stem}: 预期 {expected} → 实际 0")
                continue
            tol = self._tolerance(expected)
            if not (expected - tol <= count <= expected + tol):
                failures.append(f"{stem}: 预期 {expected} (±{tol})，实际 {count}")
        assert not failures, f"{len(failures)} 个文件产出偏离:\n  " + "\n  ".join(failures)

    def test_no_regressions_from_known_uncovered(self):
        actual = self._get_actual_counts()
        surprises = []
        for stem, reason in sorted(KNOWN_UNCOVERED_FORMATS.items()):
            count = actual.get(stem, 0)
            if count > 0:
                surprises.append(f"{stem}: {count} chunks（{reason}）")
        if surprises:
            print(f"\n  [INFO] {len(surprises)} 个文件已有产出:")
            for s in surprises: print(f"    {s}")

    def test_count_method_consistency(self):
        """count_method 中描述的具体数字应与 estimated_count 一致。

        防止 commit 9545101 那种"改 estimated_count 不改 count_method"的篡改：
        手工估计算法术数时，count_method 通常会描述实际数字（如
        "手动计数：6 条" 或 "约 280 个独立法术"），
        若 estimated_count 被改而 count_method 不动，两者会不一致。

        检查模式：
        1. estimated_count > 0 时 count_method 必须非空
        2. 算术（X（...）+ Y（...））：X+Y 应等于 estimated_count
        3. "X 条" / "约 X" / "X 个"：X 应在 estimated_count ±30% 内
        """
        issues = []
        for entry in self._get_per_file():
            cm = entry.get("count_method", "")
            est = entry.get("estimated_count", 0)
            if not cm:
                if est > 0:
                    issues.append(f"{entry['file']}: estimated_count={est} 但 count_method 为空")
                continue

            matched = False

            # 模式 2: 算术（"63（管道）+ 198（加粗）" → 261）
            arith = re.findall(r"(\d+)\s*[（(]", cm)
            if len(arith) >= 2:
                total = sum(int(n) for n in arith)
                if total == est:
                    matched = True
                else:
                    issues.append(
                        f"{entry['file']}: count_method 加和 {total} ≠ estimated {est}（{cm[:80]}）"
                    )
                    continue

            if matched:
                continue

            # 模式 3: 具体数字（"5 条" / "约 280 个独立法术" / "27 行，再加 2 条无图片条目"）
            # 找 "N 条"、"约 N 个"、"N 行"、"N 个标记/标题/法术/段落/字段"
            # 规则：至少一个数字与 estimated_count 在 ±30% 内匹配；其他数字视为补充说明
            specific = re.findall(
                r"(?:约\s*)?(\d+)\s*(?:条|行|个标记|个标题|个独立|个法术|个段落|个字段)", cm
            )
            if specific:
                matched = any(
                    int(n) > 0 and abs(int(n) - est) / max(est, 1) <= 0.3
                    for n in specific
                )
                if not matched:
                    issues.append(
                        f"{entry['file']}: count_method 中数字 {specific} 无一与 estimated {est} 匹配（{cm[:80]}）"
                    )

        assert not issues, "count_method 与 estimated_count 不一致:\n  " + "\n  ".join(issues)
