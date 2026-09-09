"""spell_chain.py — 法术后处理链（2026-09-01：KN011 link 内建，阶段二）

迁移自 phase1 根目录 link_mythic_base_spells.py，重构为「类 + run(output_dir)
-> dict」函数式接口（对齐 feat_chain.py 契约），并内建为
SpellProcessor.POSTPROCESSORS finalize 组件（k3 裁定 3 方案 A）。
原脚本 link_mythic_base_spells.py 保留为 CLI 兼容壳（import 本模块委托）。

核心约束（k3 裁定 3，硬性）：内建不得改变 link 结果本身——base_spell_* 字段
须与独立脚本时代逐字段等价（link 257/257 保持）；link 不删行 → index.json 与
chunks 行数天然一致（pipeline _write_index 先于 _finalize 执行，但 link 只改
MA 增强 chunk 的 base_spell_* 字段，不增删行）。

判定逻辑（与独立脚本逐行一致）：ALL_LEVELS 聚合表 → alias 修正 → 归一化
索引 → CRB 优先。幂等：重复执行对已带 base_spell_* 的 chunk 重写同值，结果不变。
"""
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# 报告输出默认目录（相对 phase1 cwd，与 feat_chain 约定一致）
DEFAULT_REPORT_DIR = Path("docs/法术")


class LinkMythicBaseSpells:
    """KN011：MA（神话冒险）增强摘要 chunk → 基础法术 chunk 交叉引用。

    为 MA 增强摘要 chunk 添加三个字段：
        base_spell_chunk_id — 基础（非 MA）法术的 chunk_id
        base_spell_title    — 基础法术标题（冗余，供调试）
        base_spell_book     — 基础法术书缩写

    命中率目标 ≥95%（≥240/253），由 verify_kn011_018.py KN011 指标把关
    （本步骤 run 只回报统计，不设阈值拦截，与 feat_chain 各步骤一致）。
    """

    # 报告输出默认目录（相对 phase1 cwd）
    DEFAULT_REPORT_DIR = Path("docs/法术")

    # ── Known alias corrections ──────────────────────────────────────────
    # MA aliases that differ from the canonical base spell alias (case-insensitive).
    ALIAS_CORRECTIONS = {
        "Gust of Winds": "Gust of Wind",  # trailing 's'
    }

    # ── "All-levels" aggregate chunks ────────────────────────────────────
    # These MA chunks cover I/II/III/IV variants of a spell family.
    # Map MA alias → (base_alias_I, base_chunk_id, base_title, base_book)
    ALL_LEVELS_CHUNKS = {
        "Beast Shape all": (
            "spell_Spell CRB_0038", "野兽形态 I", "CRB",
        ),
        "Elemental Body all": (
            "spell_Spell CRB_0178", "元素形态 I", "CRB",
        ),
        "Form of the Dragon all": (
            "spell_Spell CRB_0225", "巨龙形态 I", "CRB",
        ),
        "Monstrous Physique all": (
            "spell_Spell UM_0129", "类人形态 I", "UM",
        ),
    }

    # ── Spells known to have no base version ────────────────────────────
    # These are genuine MA-only spells; leaving them unmatched is correct.
    MA_ONLY_SPELLS = {
        "Boiling Blood",  # no non-MA version exists
    }

    @staticmethod
    def normalize_alias(alias: str) -> str:
        """Normalize an English alias for case-insensitive matching.

        - Lowercase
        - Chinese fullwidth comma → ASCII comma + space
        - Collapse multiple whitespace
        - Strip leading/trailing whitespace
        """
        s = alias.lower().replace("，", ", ").strip()
        return re.sub(r"\s+", " ", s)

    @classmethod
    def build_index(cls, chunks: List[dict]) -> Dict[str, List[dict]]:
        """Build a case-insensitive index: normalized_alias → [chunk, ...].

        Only indexes non-MA chunks that have a `book_abbreviation` (not MA).
        Returns all matches per alias so the caller can apply CRB priority.
        """
        index: Dict[str, List[dict]] = defaultdict(list)
        for c in chunks:
            book = c.get("book_abbreviation", "")
            if book == "MA":
                continue
            for alias in (c.get("aliases") or []):
                if not isinstance(alias, str) or not alias.strip():
                    continue
                norm = cls.normalize_alias(alias)
                index[norm].append(c)
        return index

    @staticmethod
    def pick_best_match(candidates: List[dict]) -> Optional[dict]:
        """From a list of candidate chunks, pick the best base spell match.

        Priority:
        1. CRB (Core Rulebook) — canonical source
        2. First available (preserves deterministic order from iteration)
        """
        if not candidates:
            return None
        for c in candidates:
            if c.get("book_abbreviation") == "CRB":
                return c
        return candidates[0]

    def link_chunks(self, chunks: List[dict]) -> Dict[str, Any]:
        """对 chunk 列表原位应用 KN011 link，返回统计。

        纯逻辑（无 I/O），与独立脚本时代逐字段等价（k3 裁定 3 硬约束）。
        """
        # ── Build index ───────────────────────────────────────────────
        index = self.build_index(chunks)

        # ── Identify MA enhanced chunks ────────────────────────────────
        ma_enhanced = []
        for c in chunks:
            if c.get("book_abbreviation") != "MA":
                continue
            # The intro chunk has no spell fields; skip it
            if c.get("chunk_id") == "spell_page_625_0000":
                continue
            # Enhanced chunks are those without full spell schema:
            # no `**学派：**` and no `**等级：**`
            text = c.get("text", "")
            if "**学派：" in text or "**等级：" in text:
                continue
            ma_enhanced.append(c)

        # ── Match ──────────────────────────────────────────────────────
        matched = 0
        unmatched: List[dict] = []

        for c in ma_enhanced:
            aliases = c.get("aliases") or []
            primary_alias = aliases[0] if aliases else ""

            # ── Check "all-levels" aggregate first ────────────────────
            if primary_alias in self.ALL_LEVELS_CHUNKS:
                chunk_id, title, book = self.ALL_LEVELS_CHUNKS[primary_alias]
                # Verify the target chunk still exists
                target = next(
                    (x for x in chunks if x.get("chunk_id") == chunk_id), None
                )
                if target:
                    c["base_spell_chunk_id"] = chunk_id
                    c["base_spell_title"] = title
                    c["base_spell_book"] = book
                    matched += 1
                    continue
                else:
                    log.warning(
                        "All-levels target %s for '%s' not found, falling back",
                        chunk_id, primary_alias,
                    )

            # ── Apply known alias corrections ─────────────────────────
            query = self.ALIAS_CORRECTIONS.get(primary_alias, primary_alias)
            norm = self.normalize_alias(query)

            # ── Look up in index ──────────────────────────────────────
            candidates = index.get(norm, [])

            # ── Try Chinese-comma normalization as fallback ───────────
            if not candidates and "，" in norm:
                ascii_norm = norm.replace("，", ",")
                candidates = index.get(ascii_norm, [])

            if not candidates:
                for al in aliases:
                    al_norm = self.normalize_alias(al)
                    candidates = index.get(al_norm, [])
                    if candidates:
                        break

            # ── Resolve ──────────────────────────────────────────────
            if candidates:
                best = self.pick_best_match(candidates)
                c["base_spell_chunk_id"] = best["chunk_id"]
                c["base_spell_title"] = best.get("title", "")
                c["base_spell_book"] = best.get("book_abbreviation", "")
                matched += 1
            else:
                record = {
                    "chunk_id": c["chunk_id"],
                    "title": c.get("title", ""),
                    "aliases": aliases,
                }
                if primary_alias not in self.MA_ONLY_SPELLS:
                    unmatched.append(record)
                else:
                    log.info(
                        "Known MA-only spell '%s' (%s) — no base version",
                        primary_alias, c.get("title", ""),
                    )
                c["base_spell_chunk_id"] = None
                c["base_spell_title"] = None
                c["base_spell_book"] = None

        # ── Report stats ─────────────────────────────────────────────
        total = len(ma_enhanced)
        rate = (matched / total * 100) if total > 0 else 0
        return {
            "total": total,
            "matched": matched,
            "unmatched_count": len(unmatched),
            "unmatched": unmatched,
            "rate": rate,
        }

    def run(self, output_dir: Path,
            report_dir: Optional[Path] = None) -> Dict[str, Any]:
        """finalize 步骤接口：读 chunks.jsonl → link → 写回 + 写报告。

        与独立脚本的差异仅限 I/O 外壳：不再 sys.exit(1)（pipeline 内步骤），
        命中率阈值由 verify_kn011_018.py 把关；link 逻辑逐字段等价。
        """
        chunks_path = output_dir / "chunks.jsonl"
        report_dir = report_dir or type(self).DEFAULT_REPORT_DIR

        with open(chunks_path, encoding="utf-8") as f:
            chunks = [json.loads(line) for line in f if line.strip()]

        stats = self.link_chunks(chunks)

        with open(chunks_path, "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

        # ── Report ─────────────────────────────────────────────────────
        log.info("KN011 match rate: %d/%d = %.1f%%",
                 stats["matched"], stats["total"], stats["rate"])
        if stats["unmatched"]:
            log.info("Unmatched: %d (MA-only 除外)",
                     stats["unmatched_count"])
            for u in stats["unmatched"]:
                log.info("  %s | title=%s | aliases=%s",
                         u["chunk_id"], u["title"], u["aliases"])

        report_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# KN011 MA 神话增强链接报告（finalize 内建，2026-09-01）",
            "",
            f"> 匹配 {stats['matched']}/{stats['total']} = {stats['rate']:.1f}%",
            f"> 未匹配 {stats['unmatched_count']}（MA-only 除外）",
            "",
        ]
        if stats["unmatched"]:
            lines.append("| chunk_id | title | aliases |")
            lines.append("|---|---|---|")
            for u in stats["unmatched"]:
                aliases = "、".join(str(a) for a in u["aliases"])
                lines.append(f"| {u['chunk_id']} | {u['title']} | {aliases} |")
            lines.append("")
        with open(report_dir / "kn011_link_report.md", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return stats
