"""
diagnostics.py — 源文件质量诊断门

职责：
  - 在 pipeline 处理前对源文件做只读扫描
  - ERROR 级别告警阻断 pipeline，要求先修源文件
  - WARN 级别告警记录日志，允许继续

设计：
  - 通用诊断规则（所有类目适用）在此文件定义
  - 类目特定规则由各 formats/*.py 注入
  - 溯源于 KN004/005-B/C/E
"""

import logging
import re
from pathlib import Path
from typing import Callable, Dict, List, Tuple

logger = logging.getLogger(__name__)


class Diagnostic:
    """单条诊断结果"""

    def __init__(self, rule: str, file_path: Path, message: str, line: int = None):
        self.rule = rule
        self.file_path = file_path
        self.message = message
        self.line = line

    def __str__(self):
        loc = f":{self.line}" if self.line else ""
        return f"[{self.rule}] {self.file_path}{loc} — {self.message}"

    def __repr__(self):
        return str(self)


class DiagnosticsGate:
    """源文件质量门 — 处理前只读扫描"""

    def __init__(self):
        # 注册表：规则名 → (级别, 检查函数)
        self.rules: Dict[str, Tuple[str, Callable]] = {}

        # 注册内置规则
        self._register_builtin()

    def _register_builtin(self):
        """注册通用内置规则"""
        self._add_rule("consecutive_bold_titles", "ERROR", self._check_consecutive_bold_titles)
        self._add_rule("broken_bold_pairs", "WARN", self._check_broken_bold_pairs)
        self._add_rule("url_in_headings", "WARN", self._check_url_in_headings)

    def _add_rule(self, name: str, level: str, func: Callable):
        self.rules[name] = (level, func)

    def scan(self, directory: Path, only: "Callable[[Path], bool] | None" = None) -> Tuple[List[Diagnostic], List[Diagnostic]]:
        """扫描目录下所有 .md 文件，返回 (errors, warnings)。

        only：可选文件过滤回调（Path→bool）；input 为根目录时传类目
        condition，只诊断该类目匹配的文件（避免全树非类目文件误扫阻断）。
        """
        errors, warnings = [], []
        for md_file in sorted(directory.rglob("*.md")):
            if only is not None and not only(md_file):
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning("无法读取 %s: %s", md_file, e)
                continue
            for rule_name, (level, func) in self.rules.items():
                results = func(text, md_file)
                for r in results:
                    if level == "ERROR":
                        errors.append(r)
                    else:
                        warnings.append(r)
        return errors, warnings

    def _check_consecutive_bold_titles(self, text: str, file_path: Path) -> List[Diagnostic]:
        """连续段落中 ≥5 个 **xx（xx）** 模式（阻断）"""
        results = []
        bold_pattern = re.compile(r'^\*\*[^*]+[（(][^)）]+[)）]\*\*$')
        lines = text.splitlines()
        consecutive = 0
        start_line = None
        for i, line in enumerate(lines, 1):
            if bold_pattern.match(line.strip()):
                if consecutive == 0:
                    start_line = i
                consecutive += 1
            else:
                if consecutive >= 5:
                    results.append(Diagnostic(
                        rule="consecutive_bold_titles",
                        file_path=file_path,
                        message=f"连续 {consecutive} 个 Bold 标题段落（L{start_line}~L{i - 1}）",
                    ))
                consecutive = 0
        # 文件末尾
        if consecutive >= 5:
            results.append(Diagnostic(
                rule="consecutive_bold_titles",
                file_path=file_path,
                message=f"连续 {consecutive} 个 Bold 标题段落（L{start_line}~文件末尾）",
            ))
        return results

    def _check_broken_bold_pairs(self, text: str, file_path: Path) -> List[Diagnostic]:
        """** 开闭数量不匹配（WARN）"""
        count = text.count("**")
        if count % 2 != 0:
            return [Diagnostic(
                rule="broken_bold_pairs",
                file_path=file_path,
                message=f"** 数量为奇数（{count}）",
            )]
        return []

    def _check_url_in_headings(self, text: str, file_path: Path) -> List[Diagnostic]:
        """标题行含 URL（WARN）"""
        results = []
        for i, line in enumerate(text.splitlines(), 1):
            if line.startswith("#") and re.search(r'https?://', line):
                results.append(Diagnostic(
                    rule="url_in_headings",
                    file_path=file_path,
                    message=f"标题含 URL: {line.strip()[:80]}",
                    line=i,
                ))
        return results
