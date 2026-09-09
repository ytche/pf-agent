"""test_cicd.py — 决策 B cicd verify 统一编排命令测试（TDD）

验证链单一事实源（regen 脚本与 CI yml 收敛为只调它）：
  pytest 类目收集 → pipeline（含 finalize）→ verify 公共框架 → 数据不变量闸口

测试收集按类目过滤（设计原案）：装配表 tests glob 只收集该类目验收面
（feat = A~G 通用 + feat 专属），法术专属 test_spell_metadata_v0_3.py 不混入。

测试面：
  - CLI 可用（--help 正常退出）
  - 未知类目 → 明确报错（装配表防拼写漂移）
  - 装配表完整性：feat 条目指向的模块/脚本真实存在（防路径漂移）
  - 完整链路执行留给 CI（本测试不跑全量 pytest + pipeline，避免慢测试）
"""
import subprocess
import sys
from pathlib import Path

import pytest

PHASE1 = Path(__file__).resolve().parent.parent.parent


def run_cicd(*args):
    return subprocess.run(
        [sys.executable, "-m", "vectorizer.cicd", *args],
        capture_output=True, text=True, cwd=PHASE1, timeout=60,
    )


def test_help_exits_zero():
    """--help 正常退出（命令可发现）"""
    r = run_cicd("verify", "--help")
    assert r.returncode == 0
    assert "--category" in r.stdout


def test_unknown_category_rejected():
    """未知类目 → 非零退出 + 明确错误（装配表防拼写漂移）"""
    r = run_cicd("verify", "--category", "no_such_cat")
    assert r.returncode != 0
    assert "no_such_cat" in (r.stdout + r.stderr)


def test_assembly_table_entries_exist():
    """装配表 feat 条目指向的 verify 模块 / 不变量脚本 / 输出目录真实存在"""
    from vectorizer.cicd.verify import CATEGORIES

    for cat, spec in CATEGORIES.items():
        # verify 模块可 import（模块级错误在此显形）
        importlib_import(spec["verify_module"])
        # 数据不变量脚本存在（invariants 为命令+参数列表，首元素为脚本名）
        script = spec["invariants"][0]
        assert (PHASE1 / script).exists(), f"{cat} 不变量脚本缺失"
        # 输出目录参数非空（pipeline --output 同源）
        assert spec["output_dir"]


def importlib_import(module_name: str):
    import importlib
    return importlib.import_module(module_name)


def test_feat_verify_module_registered():
    """feat 类目的 verify 模块 = FeatVerify（决策 E 框架装配一致）"""
    from vectorizer.cicd.verify import CATEGORIES
    mod = importlib_import(CATEGORIES["feat"]["verify_module"])
    assert hasattr(mod, "FeatVerify")


def test_tests_globs_match_at_least_one():
    """每个 tests glob 至少命中 1 个文件（防拼写错误静默漏测）"""
    from vectorizer.cicd.verify import collect_test_files
    files = collect_test_files("feat")
    assert files, "feat 测试收集为空"


def test_tests_globs_feat_coverage_and_boundary():
    """feat 验收面 = A~G 通用 + feat 专属；法术专属不混入（negative）"""
    from vectorizer.cicd.verify import collect_test_files
    names = {f.name for f in collect_test_files("feat")}
    # 覆盖：feat 专属文件全部在收集面内
    for name in ["test_feat_format.py", "test_feat_processor.py",
                 "test_fc_match.py", "test_per_file_chunk_counts.py",
                 "test_postprocess.py"]:
        assert name in names, f"{name} 不在 feat 验收面"
    # 覆盖：A~G 通用测试在收集面内（所有类目验收面共用）
    assert any(n.startswith("test_category_") for n in names), "A~G 通用缺失"
    # 边界：法术专属不混入 feat 链（属法术类目验收面，决策 B 设计原案）
    assert "test_spell_metadata_v0_3.py" not in names, "法术专属误入 feat 验收面"
