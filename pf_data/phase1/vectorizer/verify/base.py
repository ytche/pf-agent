"""
base.py — verify 公共框架（v2.2 决策 E）

verify_*.py 的公共部分收敛于此，禁止在各类目脚本复制：
  - load_chunks：三个旧脚本（verify_feats / verify_spells / verify_kn011_018）逐字复制 3 份 → 收敛为模块级函数
  - VerifyBase 模板方法：argparse 解析公共参数 → prepare 载入类目数据 → 顺序执行 checks 注册表 → 汇总 exit code
  - GENERIC_CHECKS：通用检查注册表（原 audit.py Tier 1 六条，按需启用；专长首版不启用）

子类契约：
  - 类变量：name（显示名）/ description（argparse 描述）/ DEFAULT_CHUNKS（必填）/ checks: List[Check]
  - add_args(parser)：类目参数扩展（可选）
  - prepare(args)：类目数据（矩阵/基线/豁免等）载入 self.ctx（可选；加载打印放这里）
  - 检查函数签名 fn(chunks, ctx) -> (ok, issues)，内部自带 print（通过/统计行）
  - checks 元组 = (显示名, fn, 通过文案)——【N/M】序号与「✅ 通过文案」由框架统一打印
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable, List, Optional, Set, Tuple

# 检查项：显示名 + 检查函数 + 通过文案（issues 为空时框架打印）
Check = Tuple[str, Callable[[List[dict], dict], Tuple[bool, List[str]]], str]


def load_chunks(path: Path) -> List[dict]:
    """从 JSONL 加载 chunk 列表（公共，禁止在各 verify_* 复制）"""
    if not path.exists():
        print(f"❌ chunks 文件不存在: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ============================================================
#  通用检查（原 audit.py Tier 1 六条，语义原样移植；按需启用）
# ============================================================


def _make_check(name: str, predicate: Callable[[dict], bool], pass_msg: str) -> Check:
    """把逐 chunk 谓词包装成 (chunks, ctx) -> (ok, issues) 检查函数"""

    def fn(chunks: List[dict], ctx: dict) -> Tuple[bool, List[str]]:
        bad = [c for c in chunks if predicate(c)]
        if bad:
            samples = ", ".join(c.get("chunk_id", "?") for c in bad[:6])
            print(f"  — {name}: 违规 {len(bad)}/{len(chunks)}")
            return False, [f"❌ {name}: {len(bad)} 条违规（示例: {samples}）"]
        print(f"  — {name}: 全部通过")
        return True, []

    return (name, fn, pass_msg)


GENERIC_CHECKS: List[Check] = [
    _make_check("url_in_title", lambda c: bool(re.search(r"https?://", c.get("title", ""))), "无 title 含 URL"),
    _make_check("unknown_placeholder", lambda c: "【?】" in c.get("title", "") or "【?】" in c.get("text", ""), "无未知占位符"),
    _make_check("bold_mismatch", lambda c: c.get("text", "").count("**") % 2 != 0, "加粗标记全部配对"),
    _make_check("unknown_source_book", lambda c: c.get("book_abbreviation", "?") in ("?", "", None), "无未知来源书"),
    _make_check("missing_category_id", lambda c: not c.get("class_name") and not c.get("metadata", {}).get("school"), "无缺失类目标识"),
    _make_check("empty_text", lambda c: len(c.get("text", "").strip()) < 10, "无空描述"),
]


# ============================================================
#  源表数据行 ↔ chunk title 对账（行级召回通用构建器）
# ============================================================


def make_row_recall_check(
    name: str,
    src_path: Path,
    row_extractor: Callable[[str], Set[str]],
    component_type: str,
    title_field: str = "title",
    pass_msg: str = "源表数据行全命中",
) -> Check:
    """构建「源表数据行 ↔ chunk title」行级召回检查。

    类目只需注入：
      - row_extractor: 源 markdown 文本 → 数据行实体名集合
      - component_type: chunk 侧参与比对的 component_type
      - title_field: 比对字段，默认 title

    返回 (显示名, 检查函数, 通过文案)，可直接放进 VerifyBase.checks。
    检查函数额外接受可选 src_path 位置参数，便于单测传入临时文件。
    """

    def fn(
        chunks: List[dict], ctx: dict, override_src_path: Optional[Path] = None
    ) -> Tuple[bool, List[str]]:
        path = override_src_path or src_path
        if not path.exists():
            print(f"⚠️  源文件不存在: {path}（跳过{name}）")
            return True, []
        names = row_extractor(path.read_text(encoding="utf-8"))
        titles = {
            c.get(title_field, "").strip()
            for c in chunks
            if c.get("component_type") == component_type
        }
        miss = sorted(n for n in names if n not in titles)
        print(f"  — 源表数据行 {len(names)} 个 → chunk title 命中 {len(names) - len(miss)}")
        if miss:
            return False, [f"❌ {name}未命中 {len(miss)} 条（整行静默丢失？）: {', '.join(miss)}"]
        return True, []

    return (name, fn, pass_msg)


class VerifyBase:
    """verify 模板方法基类：CLI → 数据准备 → 顺序检查 → 汇总 exit code"""

    name = "verify"
    description = ""
    DEFAULT_CHUNKS: Optional[Path] = None
    checks: List[Check] = []

    def __init__(self) -> None:
        self.ctx: dict = {}

    def add_args(self, parser: argparse.ArgumentParser) -> None:
        """子类扩展类目参数（--matrix/--baseline/--exemptions 等）"""

    def prepare(self, args: argparse.Namespace) -> None:
        """子类载入类目数据进 self.ctx（加载打印放这里）"""

    def main(self, argv: Optional[List[str]] = None) -> None:
        parser = argparse.ArgumentParser(description=self.description)
        parser.add_argument("--chunks", default=self.DEFAULT_CHUNKS, type=Path)
        self.add_args(parser)
        args = parser.parse_args(argv)

        chunks = load_chunks(args.chunks)
        print(f"加载 {len(chunks)} chunks")
        self.prepare(args)

        all_ok = True
        total = len(self.checks)
        for idx, (title, fn, pass_msg) in enumerate(self.checks, start=1):
            print(f"\n【{idx}/{total}】{title}")
            ok, issues = fn(chunks, self.ctx)
            all_ok &= ok
            for issue in issues:
                print(issue)
            if not issues:
                print(f"  ✅ {pass_msg}")

        print("\n" + ("✅ 全部验收通过" if all_ok else "❌ 验收未完全通过"))
        sys.exit(0 if all_ok else 1)
