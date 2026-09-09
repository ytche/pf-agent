# processors — FileProcessor 模板方法 + 类目特定 Processor

import importlib
import pkgutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from vectorizer.processors.base import FileProcessor


# 处理器注册表：category → (ProcessorClass, 条件函数)
PROCESSOR_REGISTRY: Dict[str, Tuple[Type[FileProcessor], Callable[[Path], bool]]] = {}


def register(category: str, processor_cls: Type[FileProcessor], condition: Callable[[Path], bool]) -> None:
    """注册 Processor 到全局注册表"""
    PROCESSOR_REGISTRY[category] = (processor_cls, condition)


def get_processor(category: str) -> Optional[Type[FileProcessor]]:
    """按类目名查找 Processor 类（不创建实例）"""
    entry = PROCESSOR_REGISTRY.get(category)
    return entry[0] if entry else None


def get_condition(category: str) -> Optional[Callable[[Path], bool]]:
    """按类目名查找文件分派条件函数"""
    entry = PROCESSOR_REGISTRY.get(category)
    return entry[1] if entry else None


def discover_processors() -> None:
    """扫描 processors 包下所有模块，触发注册"""
    for importer, modname, ispkg in pkgutil.walk_packages(
        __path__, prefix=__name__ + ".",
        onerror=lambda _: None,
    ):
        # 跳过自身和 base
        if modname.endswith((".__init__", ".base")):
            continue
        importlib.import_module(modname)

