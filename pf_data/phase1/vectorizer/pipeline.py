"""
pipeline.py — 向量化流水线编排

职责：
  - 串联 diagnostics（门禁）→ formats（归一化）→ processors（分块）
  - 类目无关的调度器，按 category 参数分派到对应 Processor
  - 统一命令行入口

用法：
  python3 -m vectorizer.pipeline --category spell \
      --input pf_rules_md_organized/法术 \
      --output vectorizer/output/法术
"""

import argparse
import json
import logging
from pathlib import Path
from typing import List

from vectorizer.diagnostics import DiagnosticsGate
# FileProcessor 显式导入：_build_processor 注解引用它，Python <3.14 注解立即求值
# （本地 3.14 PEP 649 惰性注解曾掩盖此缺失，CI 3.12 直接 NameError）
from vectorizer.processors import discover_processors, get_processor, get_condition, PROCESSOR_REGISTRY
from vectorizer.processors.base import FileProcessor
from vectorizer.sources.providers import SourceResolver, ALL_PROVIDERS

logger = logging.getLogger(__name__)


# 自动发现所有 Processor（遍历 processors/ 包）
discover_processors()


class Pipeline:
    """向量化流水线 — 类目无关的编排器"""

    def __init__(self, category: str, input_dir: Path, output_dir: Path):
        self.category = category
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.source_resolver = SourceResolver(ALL_PROVIDERS)
        self.diagnostics = DiagnosticsGate()
        self.processor = self._build_processor()
        self.all_chunks: List[dict] = []

    def run(self) -> List[dict]:
        """执行完整流水线：加载资源 → 门禁 → 遍历 → 后处理 → 输出"""
        # 0. 加载类目特有资源（Processor 生命周期钩子）
        self.processor.load_resources(self.input_dir)

        # 1. 门禁扫描（only=类目 condition：input 为根目录时只诊断匹配文件，
        # 避免对全树非类目文件误扫；无 condition 的类目传 None 行为不变）
        condition = get_condition(self.category)
        errors, warnings = self.diagnostics.scan(self.input_dir, only=condition)
        for w in warnings:
            logger.warning("[WARN] %s", w)
        if errors:
            raise RuntimeError(f"诊断门阻断：{len(errors)} 个 ERROR")

        # 2. 遍历源文件 → 分派 Processor
        for md_file in sorted(self._walk_input()):
            if self._dispatch_processor(md_file) is None:
                logger.info("跳过 %s：无匹配 Processor", md_file.name)
                continue
            chunks = self.processor.process(md_file)
            self.all_chunks.extend(chunks)

        # 3. 类目特有后处理（Processor 生命周期钩子）
        self.all_chunks = self.processor.post_process(self.all_chunks)

        # 4. 输出
        self._write_chunks_jsonl()
        self._write_index()

        # 5. finalize（v2.2 决策 A）：类目声明的后处理步骤链，chunks.jsonl 落盘后、
        #    verify 前。从「编排保证链路」升级为「结构保证」——重生成单入口收敛为
        #    pipeline --category <类目>，regen 脚本/CI 不再维护独立后处理步骤清单。
        self._finalize()

        # 产物已含 finalize 改写（book/toc/source 字段），重读返回最终态，
        # 保证返回值与磁盘产物一致（调用方不应拿到 finalize 前的中间态）。
        self.all_chunks = self._load_chunks_jsonl()
        logger.info("流水线完成：%d 个 chunk → %s", len(self.all_chunks), self.output_dir)
        return self.all_chunks

    def _finalize(self) -> None:
        """执行类目声明的后处理步骤链（POSTPROCESSORS，顺序即声明顺序，不可变）。

        默认关闭兼容：已验收类目（spell 等）不声明 POSTPROCESSORS → 无操作，
        行为与 v2.1 完全一致（决策 A 契约③）。步骤为「类 + run(output_dir)」
        函数式接口，实现见 vectorizer/postprocess/feat_chain.py。
        """
        steps = getattr(self.processor, "POSTPROCESSORS", None) or []
        for cls in steps:
            stats = cls().run(self.output_dir)
            logger.info("[finalize] %s → %s", cls.__name__, stats)

    def _load_chunks_jsonl(self) -> List[dict]:
        """从产物文件读回 chunk 列表（finalize 后的最终态）"""
        path = self.output_dir / "chunks.jsonl"
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def _build_processor(self) -> FileProcessor:
        """根据 category 创建唯一的 Processor 实例"""
        processor_cls = get_processor(self.category)
        if processor_cls is None:
            raise ValueError(f"未知类目: {self.category}，已注册: {list(PROCESSOR_REGISTRY)}")
        return processor_cls(source_resolver=self.source_resolver)

    def _walk_input(self) -> List[Path]:
        """递归遍历输入目录下所有 .md 文件"""
        return list(self.input_dir.rglob("*.md"))

    def _dispatch_processor(self, file_path: Path):
        """检查文件是否匹配当前 Processor 的条件；不匹配返回 None"""
        condition = get_condition(self.category)
        if condition is None:
            return None
        return self.processor if condition(file_path) else None

    def _normalize_chunks(self) -> List[dict]:
        """将 Chunk dataclass 转为 dict（混合兼容）"""
        from dataclasses import asdict
        result = []
        for c in self.all_chunks:
            if hasattr(c, "__dataclass_fields__"):
                result.append(asdict(c))
            else:
                result.append(c)
        return result

    def _write_chunks_jsonl(self) -> None:
        """将 chunks 写为 JSONL 格式"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / "chunks.jsonl"
        chunks_dict = self._normalize_chunks()
        with open(path, "w", encoding="utf-8") as f:
            for data in chunks_dict:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")

    def _write_index(self) -> None:
        """输出索引摘要（供审计/验证用）"""
        chunks_dict = self._normalize_chunks()
        path = self.output_dir / "index.json"
        index = {
            "category": self.category,
            "total_chunks": len(chunks_dict),
            "files_processed": len(set(c.get("doc_id") for c in chunks_dict)),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="向量化流水线")
    parser.add_argument("--category", required=True, help="类目：spell / feat / equipment / ...")
    parser.add_argument("--input", required=True, type=Path, help="源文件目录")
    parser.add_argument("--output", default=None, type=Path, help="输出目录（默认 vectorizer/output/<category>）")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser


def main():
    args = build_arg_parser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s")

    output = args.output or Path("vectorizer/output") / args.category

    pipeline = Pipeline(category=args.category, input_dir=args.input, output_dir=output)
    pipeline.run()


if __name__ == "__main__":
    main()
