"""
fixups/base.py — @fixup 装饰器 + 不变量校验引擎

设计：
  - 每个 fixup 函数必须声明不变量（执行前后校验）
  - 违反不变量 → 立即报错停管线
  - 溯源于 Bug 004：不变量契约可阻止回归

用法：
  @fixup(target_file="page_55.md", invariants=[
      FixupInvariant(
          description="### 层级数不减少",
          check_after=lambda text: text.count("### ") >= original_heading_count,
      ),
  ])
  def fix_paladin_page_55(text: str) -> str:
      ...
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FixupInvariant:
    """不变量声明"""
    description: str
    check_before: Optional[Callable[[str], bool]] = None
    check_after: Optional[Callable[[str], bool]] = None


def fixup(target_file: str, invariants: List[FixupInvariant]):
    """装饰器：声明修复目标文件和不变量的 fixup 函数"""
    def decorator(func):
        func._fixup_target = target_file
        func._fixup_invariants = invariants
        return func
    return decorator


class FixupEngine:
    """不变量校验引擎 — 按文件名路由 fixup"""

    def __init__(self):
        self.registry: Dict[str, Callable] = {}

    def register(self, func):
        """注册 fixup 函数（或通过 @fixup 装饰器自动注册）"""
        target = getattr(func, "_fixup_target", None)
        if target:
            self.registry[target] = func
            logger.debug("注册 fixup: %s → %s", target, func.__name__)

    def apply(self, file_path: Path, content: str) -> str:
        """对文件内容应用 fixup（如果存在），校验不变量"""
        target_name = file_path.name
        fixup_func = self.registry.get(target_name)

        if fixup_func is None:
            return content

        invariants = getattr(fixup_func, "_fixup_invariants", [])

        # 前置不变量校验
        for inv in invariants:
            if inv.check_before and not inv.check_before(content):
                raise AssertionError(
                    f"[{target_name}] 前置不变量失败: {inv.description}"
                )

        # 执行修复
        result = fixup_func(content)

        # 后置不变量校验
        for inv in invariants:
            if inv.check_after and not inv.check_after(result):
                raise AssertionError(
                    f"[{target_name}] 后置不变量失败: {inv.description}"
                )

        if result != content:
            logger.info("fixup 已应用: %s", target_name)

        return result
