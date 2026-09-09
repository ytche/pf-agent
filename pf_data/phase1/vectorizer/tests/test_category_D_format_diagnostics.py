"""
D 类：格式缺陷在诊断阶段被检出

测试目标：
  - ** 断裂（奇数数量）被检出
  - 连续 N 个 **xx（English）** 段落被检出
  - URL 混入标题被检出
  - 源文件质量门对缺陷的 ERROR/WARN 分级正确

溯源于 KN004/005-E
"""

import pytest
from pathlib import Path
from vectorizer.diagnostics import DiagnosticsGate


class TestFormatDiagnostics:
    """格式缺陷诊断"""

    DIAG = DiagnosticsGate()

    def test_detect_broken_bold(self, tmp_path: Path):
        """奇数 ** 数量被 WARN 检出"""
        file_path = tmp_path / "test_broken.md"
        file_path.write_text("这是**文本（Test）**未闭合的**\n", encoding="utf-8")
        errors, warnings = self.DIAG.scan(tmp_path)
        bold_warns = [w for w in warnings if w.rule == "broken_bold_pairs"]
        assert len(bold_warns) >= 1, "未检出断裂的 **"

    def test_detect_consecutive_bold_titles(self, tmp_path: Path):
        """连续 5+ 个 Bold 段落被 ERROR 检出"""
        lines = [f"**Spell {i} (Spell {i})**" for i in range(6)]
        file_path = tmp_path / "test_consecutive.md"
        file_path.write_text("\n".join(lines), encoding="utf-8")
        errors, warnings = self.DIAG.scan(tmp_path)
        bold_errors = [e for e in errors if e.rule == "consecutive_bold_titles"]
        assert len(bold_errors) >= 1, "未检出连续 Bold 段落"

    def test_no_false_alarm_for_normal_text(self, tmp_path: Path):
        """正常文本不应触发 ERROR"""
        normal_text = (
            "# 法术列表\n\n"
            "## 引言\n\n"
            "这里是一些描述文本。\n\n"
            "**强酸箭 (Acid Arrow)**\n"
            "| 学派 咒法系 | 环位 术士/法师 2 |\n"
        )
        file_path = tmp_path / "normal.md"
        file_path.write_text(normal_text, encoding="utf-8")
        errors, warnings = self.DIAG.scan(tmp_path)
        assert len(errors) == 0, f"正常文本触发了 ERROR: {errors}"
