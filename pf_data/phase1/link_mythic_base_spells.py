#!/usr/bin/env python3
"""
KN011: Link MA (Mythic Adventures) enhanced spell chunks to their base spell chunks.

⚠️ 2026-09-01 起：实现已迁移至 vectorizer/postprocess/spell_chain.py，并内建为
SpellProcessor.POSTPROCESSORS finalize 组件（k3 裁定 3 方案 A，阶段二）。
本脚本保留为 CLI 兼容壳——内部委托 spell_chain.LinkMythicBaseSpells，
行为与独立脚本时代逐字段等价（link 257/257 保持）。

Usage:
    python3 link_mythic_base_spells.py [--input INPUT] [--output OUTPUT]

Default input/output: vectorizer/output/法术/chunks.jsonl (in-place update)

Output fields added to matching MA chunks:
    base_spell_chunk_id   — chunk_id of the base (non-MA) spell
    base_spell_title      — title of the base spell (redundant, for debugging)
    base_spell_book       — book_abbreviation of the base spell

Target: ≥95% match rate (≥240/253), verified by the --check flag.
"""

import argparse
import json
import logging
import sys

from vectorizer.postprocess.spell_chain import LinkMythicBaseSpells

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)


def link_mythic_base_spells(input_path: str, output_path: str):
    """兼容入口：读 input → link → 写 output（等价独立脚本时代的原地更新）。

    委托 LinkMythicBaseSpells.link_chunks 纯逻辑，结果与旧实现逐字段等价。
    """
    with open(input_path, encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f]

    log.info("Read %d chunks from %s", len(chunks), input_path)
    stats = LinkMythicBaseSpells().link_chunks(chunks)

    with open(output_path, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    log.info("Written %d chunks to %s", len(chunks), output_path)
    log.info("Match rate: %d/%d = %.1f%%", stats["matched"],
             stats["total"], stats["rate"])
    if stats["unmatched"]:
        log.info("Unmatched: %d", stats["unmatched_count"])
        for u in stats["unmatched"]:
            log.info("  %s | title=%s | aliases=%s",
                     u["chunk_id"], u["title"], u["aliases"])
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Link MA mythic-enhanced spell chunks to their base spells",
    )
    parser.add_argument(
        "--input",
        default="vectorizer/output/法术/chunks.jsonl",
        help="Path to input chunks.jsonl (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path (default: same as input, in-place update)",
    )
    args = parser.parse_args()

    output = args.output or args.input
    stats = link_mythic_base_spells(args.input, output)

    # Exit with non-zero if match rate below 95%
    if stats["rate"] < 95:
        log.error(
            "Match rate %.1f%% is below 95%% threshold — check unmatched list",
            stats["rate"],
        )
        sys.exit(1)

    log.info("KN011 linking complete. Match rate: %.1f%% ✓", stats["rate"])


if __name__ == "__main__":
    main()
