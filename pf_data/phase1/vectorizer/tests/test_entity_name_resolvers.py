"""
test_entity_name_resolvers.py — base.py entity_name_resolvers stage 机制 TDD

覆盖：
  - 默认空列表 = title 兜底（spell/feat 零行为变化语义）
  - 有序短路：首个非 None 结果生效
  - resolver 可返回空串显式命中（例外前置）
  - 子类注册 resolver 列表后，process() 写入 chunk.metadata['entity_name']
"""

import pytest
from pathlib import Path
from typing import Optional

from vectorizer.formats.base import BaseFormat
from vectorizer.processors.base import Chunk, FileProcessor
from vectorizer.sources.providers import SourceContext, SourceResolver


class _DummyFormat(BaseFormat):
    """最小格式处理器：只返回一个条目"""

    @property
    def category(self) -> str:
        return "dummy"

    def normalize(self, text: str) -> str:
        return text

    def promote(self, text: str) -> str:
        return text

    def split_into_items(self, text: str, source_name: str = "") -> list:
        return [{"name": "条目", "text": "正文"}]


class _NoResolverProcessor(FileProcessor):
    """默认空 resolver 列表 → title 兜底"""

    @property
    def category(self) -> str:
        return "dummy"

    def build_chunk(self, template: Chunk, item: dict) -> Chunk:
        template.title = item["name"]
        template.text = item["text"]
        return template

    def resolve_source(self, chunk: Chunk, ctx: SourceContext, item: dict) -> Chunk:
        return chunk

    def infer_metadata(self, chunk: Chunk, item: dict) -> Chunk:
        return chunk


class _ResolverProcessor(_NoResolverProcessor):
    """注册两个 resolver：第一个返回 None，第二个返回大写标题"""

    entity_name_resolvers = [
        lambda proc, chunk, item: None,
        lambda proc, chunk, item: chunk.title.upper(),
    ]


class _EmptyStringResolverProcessor(_NoResolverProcessor):
    """第一个 resolver 返回空串 → 短路停止，entity_name = """""

    entity_name_resolvers = [
        lambda proc, chunk, item: "",
        lambda proc, chunk, item: "never",
    ]


def make_processor(cls):
    return cls(source_resolver=SourceResolver([]), format_handler=_DummyFormat())


@pytest.fixture
def dummy_file(tmp_path):
    p = tmp_path / "seed.md"
    p.write_text("正文", encoding="utf-8")
    return p


def test_default_resolvers_empty_title_fallback(dummy_file):
    """默认 entity_name_resolvers = [] → entity_name = chunk.title"""
    proc = make_processor(_NoResolverProcessor)
    chunks = proc.process(dummy_file)
    assert len(chunks) == 1
    assert chunks[0].metadata["entity_name"] == "条目"


def test_resolver_chain_short_circuits(dummy_file):
    """有序短路：首个非 None resolver 结果生效"""
    proc = make_processor(_ResolverProcessor)
    chunks = proc.process(dummy_file)
    assert chunks[0].metadata["entity_name"] == "条目".upper()


def test_empty_string_resolver_short_circuits(dummy_file):
    """resolver 返回空串也视为命中（例外前置可显式落空）"""
    proc = make_processor(_EmptyStringResolverProcessor)
    chunks = proc.process(dummy_file)
    assert chunks[0].metadata["entity_name"] == ""


def test_resolve_entity_name_method_directly():
    """FileProcessor.resolve_entity_name 可被单独调用"""
    proc = make_processor(_ResolverProcessor)
    chunk = proc._build_chunk_template(Path("seed.md"), 0, None)
    chunk.title = "测试"
    assert proc.resolve_entity_name(chunk, {}) == "测试".upper()
