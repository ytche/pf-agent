"""
formats/base.py — 格式归一化抽象基类

设计：
  - Phase 1 normalize：纯去噪，不产生新 `##` 标题
  - Phase 2 promote：结构提升，依赖 Phase 1 已完成归一化
  - 两阶段分离后，新格式变体只需在 Phase 1 追加规则
  - 子类实现 _normalize_custom() 钩子追加类目特定去噪规则

溯源于 Bug 001（图片前缀标题漏判）和 Bug 005（字段标签被误提升）
"""

import re
from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class BaseFormat(ABC):
    """类目无关的格式处理基类"""

    @property
    @abstractmethod
    def category(self) -> str:
        """类目标识，如 "spell" / "feat" / "profession" """
        ...

    def get_audit_rules(self) -> dict:
        """已废弃，保留仅为兼容，新 Formatter 不要实现。

        audit 引擎已被弃用，该钩子不会再被框架调用。
        默认返回空规则集，避免历史或冻结模块外的子类被迫写死实现。
        """
        return {}

    # ---- Phase 1：纯去噪 ----

    def normalize(self, text: str) -> str:
        """Phase 1 归一化：纯去噪，不改变文档结构"""
        text = self._strip_url_lines(text)
        text = self._strip_translator_notes(text)
        text = self._normalize_blank_lines(text)
        text = self._normalize_custom(text)  # 子类钩子
        return text

    def _strip_url_lines(self, text: str) -> str:
        """剥离整行 URL 或 Markdown 链接"""
        # http:// 开头的裸 URL
        text = re.sub(r'^\s*https?://[^\s)]+\s*$', '', text, flags=re.MULTILINE)
        # [text](url) 格式的 Markdown 链接行
        text = re.sub(r'^\s*\[[^\]]*\]\(https?://[^)]+\)\s*$', '', text, flags=re.MULTILINE)
        # ** [text](url) ** 格式的加粗链接行（仅剥页头论坛链接形态：锚文本也是
        # URL——全库 150 处论坛来源行 `**[http://45.79.87.129/…](http://…)**`）。
        # KN131（2026-08-04）：此前 `[^\]]*` 过宽，把锚文本为中文正文的链接章节
        # 标题（page_398 半精灵替换特性汇总等 37 处，锚=章节名）整行剥空 → 标题
        # 消失 → 整章落默认态；收窄后此类行走 _strip_http_links 剥 URL 留锚文本
        # → 章节判定切 alt_trait 态
        text = re.sub(r'^\s*\*\*\[https?://[^\]]*\]\(https?://[^)]+\)\*\*\s*$', '', text, flags=re.MULTILINE)
        return text

    def _strip_translator_notes(self, text: str) -> str:
        """剥离译者注释行（含加粗包裹的变体）

        P1b 修复（2026-08-02）：原加粗正则 `[^*]+` 匹配不了双段加粗拼接
        `**译者：X，****Y**`（RE2 段间闭合残留，page_198/200/201/203），
        形态归一后 `**译者（：X，）**` 被标题正则误当条目标题。放宽为
        允许段间 1~4 星段（`[^*\n]*(?:\*{1,4}[^*\n]+)*`）。
        """
        # 普通译者行
        text = re.sub(r'^\s*译者[：:].*$', '', text, flags=re.MULTILINE)
        # 加粗包裹的译者行：**译者：四月** / **译者：傻豆，****Falengel**
        text = re.sub(r'^\s*\*\*译者[：:][^*\n]*(?:\*{1,4}[^*\n]+)*\*\*\s*$', '', text, flags=re.MULTILINE)
        return text

    def _normalize_blank_lines(self, text: str) -> str:
        """规范化空行：连续空行压缩为单个空行"""
        return re.sub(r'\n{3,}', '\n\n', text)

    def _normalize_custom(self, text: str) -> str:
        """子类钩子：追加类目特定的去噪规则"""
        return text

    # ---- Phase 2：结构提升 ----

    @abstractmethod
    def promote(self, text: str) -> str:
        """Phase 2 结构提升：识别条目边界、提升标题、结构化字段"""
        ...

    @abstractmethod
    def split_into_items(self, text: str, *, source_name: Optional[str] = None) -> List[dict]:
        """将提升后的文本拆分为结构化条目列表

        KN017：可选 source_name 用于丢失告警（可观测性），不改 split 行为。
        """
        ...

    # ---- 辅助工具 ----

    @staticmethod
    def _fix_broken_bold(text: str) -> str:
        """修复 ** 开闭不匹配（计数为奇数时补全）"""
        count = text.count("**")
        if count % 2 != 0:
            text += "**"
        return text
