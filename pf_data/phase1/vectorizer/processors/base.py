"""
processors/base.py — FileProcessor 模板方法

设计：
  - 模板方法模式：process() 定义不可变骨架
  - 三钩子由子类覆写：build_chunk / resolve_source / infer_metadata
  - 类目无关，子类通过覆写钩子实现类目特定逻辑
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from vectorizer.formats.base import BaseFormat
from vectorizer.sources.providers import (
    MdMappingTocProvider,
    SourceContext,
    SourceResolver,
    SourceResult,
)

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """通用 chunk 数据结构"""
    chunk_id: str
    doc_id: str
    category: str
    component_type: str
    title: str
    text: str
    book_abbreviation: str
    book_name_cn: str
    book_name_en: str
    source_confidence: int
    chm_toc_path: str = ""  # 在 CHM 目录中的路径（由 MdMappingTocProvider 富化）
    aliases: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)  # 类目特有字段存这里
    extra: Dict[str, Any] = field(default_factory=dict)     # 原始额外信息


class FileProcessor(ABC):
    """文件处理器模板方法 — 类目无关"""

    # 类目可覆写：entity name 判定函数有序列表。
    # 每个 resolver 签名为 (self, chunk, item) -> Optional[str]：
    #   - 返回 str（含空串）→ 该值即最终 entity name，短路停止
    #   - 返回 None → 继续下一个 resolver
    # 默认空列表 → 行为等价于 title 兜底，spell/feat 等类目零行为变化。
    entity_name_resolvers: List[Callable[..., Optional[str]]] = []

    def resolve_entity_name(self, chunk: Chunk, item: dict) -> str:
        """执行 entity_name_resolvers 有序链，首个非 None 结果生效；
        全部返回 None 时回退到 chunk.title。子类 infer_metadata 可从
        chunk.metadata['entity_name'] 读取，确保与模板方法一致。"""
        for resolver in self.entity_name_resolvers:
            result = resolver(self, chunk, item)
            if result is not None:
                return result
        return chunk.title

    def __init__(self, source_resolver: SourceResolver, format_handler: BaseFormat):
        self.source_resolver = source_resolver
        self.format = format_handler
        # 公用 TOC 富化器：加载 md_mapping.json，按文件名填充 chm_toc_path。
        # 不进来源书链（避免激活 CHMTocPathProvider 子串误匹配），由模板方法在 resolve_source 之后调用。
        self.chm_toc_provider = MdMappingTocProvider()

    @property
    @abstractmethod
    def category(self) -> str:
        """类目标识"""
        ...

    def process(self, file_path: Path) -> List[Chunk]:
        """模板方法：处理单个文件，返回 chunk 列表"""
        text = file_path.read_text(encoding="utf-8")

        # 0. normalize 前预处理钩子：同字符（\r）跨文件语义不同（CRB 页 = 空行
        # 标记，Unchained 断点页 = 行内硬断行）时，在此按文件分派
        text = self.pre_normalize(file_path, text)

        # 1. 格式归一化
        text = self.format.normalize(text)
        text = self.format.promote(text)

        # 2. 拆分为条目（KN017：传 source_name 供丢弃告警）
        items = self.format.split_into_items(text, source_name=file_path.name)

        # 3. 构建 SourceContext
        source_ctx = self._build_source_context(file_path, text)

        # 4. 逐条目构建 chunk
        chunks = []
        for idx, item in enumerate(items):
            chunk = self._build_chunk_template(file_path, idx, source_ctx)
            chunk = self.build_chunk(chunk, item)
            # entity name 解析 stage：有序短路 + 例外前置，默认空列表 = title 兜底
            chunk.metadata["entity_name"] = self.resolve_entity_name(chunk, item)
            chunk = self.resolve_source(chunk, source_ctx, item)
            # 公用：按文件名查 md_mapping 填充 CHM 目录路径（直接写 chunk，不走 ctx，
            # 避免激活 CHMTocPathProvider 的子串缩写匹配改变来源书判定）
            chunk.chm_toc_path = self.chm_toc_provider.lookup_toc_path(file_path.name)
            chunk = self.infer_metadata(chunk, item)
            chunks.append(chunk)

        logger.debug("%s → %d chunks", file_path.name, len(chunks))
        return chunks

    # ---- 钩子 ----

    def pre_normalize(self, file_path: Path, text: str) -> str:
        """normalize 前预处理（默认原样返回）。

        文件级 CRLF 语义差异（\r = 空行标记 vs 行内断点）按文件分派的挂点：
        normalize 无文件名上下文，统一转换会丢语义，子类在此先行转换。
        """
        return text

    @abstractmethod
    def build_chunk(self, template: Chunk, item: dict) -> Chunk:
        """从条目数据构建 chunk（设置标题、正文、别名等）"""
        ...

    @abstractmethod
    def resolve_source(self, chunk: Chunk, ctx: SourceContext, item: dict) -> Chunk:
        """为 chunk 解析来源书"""
        ...

    @abstractmethod
    def infer_metadata(self, chunk: Chunk, item: dict) -> Chunk:
        """推断类目特有元数据（法术：school/level/descriptor；职业：subtype）"""
        ...

    # ---- 模板方法内部 ----

    def _build_chunk_template(self, file_path: Path, idx: int, ctx: SourceContext) -> Chunk:
        """生成 chunk 模板（公共字段）"""
        return Chunk(
            chunk_id=f"{self.category}_{file_path.stem}_{idx:04d}",
            doc_id=file_path.stem,
            category=self.category,
            component_type=self.category,
            title="",
            text="",
            book_abbreviation="?",
            book_name_cn="",
            book_name_en="",
            source_confidence=0,
        )

    def _build_source_context(self, file_path: Path, content: str) -> SourceContext:
        """构建 SourceContext（使用绝对路径以确保父目录判定正确）"""
        abs_path = file_path.absolute()
        return SourceContext(
            file_path=abs_path,
            file_content=content,
            chm_toc_path="",
            html_markers=[],
            directory_hints=list(abs_path.parts),
            aggregation_table=None,
        )

    # ---- 生命周期钩子（默认空实现，子类按需覆写） ----

    def load_resources(self, input_dir: Path) -> None:
        """流水线启动时加载类目特有资源（如 index 文件）"""
        pass

    def post_process(self, chunks: List[Chunk]) -> List[Chunk]:
        """流水线结束后追加或修改类目特有 chunk（如索引 chunk）"""
        return chunks
