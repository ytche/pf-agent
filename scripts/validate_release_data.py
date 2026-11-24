#!/usr/bin/env python3
"""发布数据一致性校验与打包。

发布脚本在打包前调用本模块，确保 8 个向量库与仓库内 chunks 产物一致、关键元数据
未退化，并核对 7 份清单；8 份 chunks 与 7 份清单也随向量库一并入包。任何缺失或漂移
都以非零退出，阻止更新 zip。

清单、打包文件和文件数统一由 collect_release_files() 产生，脚本不再另维护一份列表。

用法：
    python3 scripts/validate_release_data.py <data-home> <repo-root>
    python3 scripts/validate_release_data.py --package <zip> <data-home> <repo-root>
"""

import hashlib
import json
import os
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

MODULES = {
    "classes": "职业",
    "equipment": "装备",
    "feats": "专长",
    "races": "种族",
    "rules": "规则",
    "skills": "技能",
    "spells": "法术",
    "traits": "背景特性",
}

LIST_FILES = {
    "equipment_lists.json": "装备/equipment_lists.json",
    "feat_lists.json": "专长/feat_lists.json",
    "race_lists.json": "种族/race_lists.json",
    "class_tables.json": "职业/class_tables.json",
    "spell_lists.json": "法术/spell_lists.json",
    "spell_lists_union.json": "法术/spell_lists_union.json",
    "rule_tables.json": "规则/rule_tables.json",
}

EMBEDDING_DIMENSION = 1024
RULE_TABLE_BASELINE = 612

# KN-120 拆分 + AKN-028 种族特性过滤的验收锚点；0000/0001 为介绍与角色说明。
RACE_TARGET_IDS = tuple(f"race_page_812_{i:04d}" for i in range(10))
RACE_TARGET_NAME = ("阿斯托莫伊人", "Astomoi")


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    release_files: list[tuple[Path, str]] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _read_json(path: Path, errors: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path} 无法读取或不是合法 JSON：{exc}")
        return None


def _read_jsonl(path: Path, errors: list[str]) -> list[dict]:
    rows = []
    try:
        with path.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    errors.append(f"{path}:{lineno} 不是合法 JSON：{exc}")
    except OSError as exc:
        errors.append(f"{path} 无法读取：{exc}")
    return rows


def _sample(values) -> str:
    values = sorted(str(v) for v in values)
    shown = "、".join(values[:3])
    return f"{shown} 等 {len(values)} 个" if len(values) > 3 else shown


def _check_store_shape(module: str, store, errors: list[str]) -> list[dict]:
    label = f"vector_store_{module}.json"
    if not isinstance(store, dict):
        errors.append(f"[{module}] {label} 顶层不是对象（社区格式应为 chunk_id→文档对象）")
        return []
    if not store:
        errors.append(f"[{module}] {label} 为空向量库")
        return []
    docs = []
    for key, doc in store.items():
        if not isinstance(doc, dict) or not isinstance(doc.get("metadata"), dict):
            errors.append(f"[{module}] {label} 条目 {key} 缺少 metadata 对象")
            continue
        if not isinstance(doc.get("embedding"), list):
            errors.append(f"[{module}] {label} 条目 {key} 缺少 embedding 数组")
            continue
        docs.append(doc)
    return docs


def _check_module(data_home: Path, repo_root: Path, module: str, errors: list[str]) -> int:
    label = f"vector_store_{module}.json"
    store_path = data_home / label
    chunks_path = repo_root / "pf_data/phase1/vectorizer/output" / MODULES[module] / "chunks.jsonl"

    if not store_path.is_file():
        errors.append(f"[{module}] 缺少向量库 {store_path}")
        return 0
    if not chunks_path.is_file():
        errors.append(f"[{module}] 缺少 chunks 产物 {chunks_path}")
        return 0

    store = _read_json(store_path, errors)
    docs = _check_store_shape(module, store, errors)
    chunks = _read_jsonl(chunks_path, errors)
    if not isinstance(store, dict):
        return 0

    if len(store) != len(chunks):
        errors.append(
            f"[{module}] 条目数漂移：store {len(store)} 条，chunks {len(chunks)} 行"
        )

    store_ids = [doc["metadata"].get("chunk_id") for doc in docs]
    missing_ids = [i for i, cid in enumerate(store_ids) if not cid]
    if missing_ids:
        errors.append(f"[{module}] store 有 {len(missing_ids)} 条缺少 metadata.chunk_id")
    store_id_set = {str(cid) for cid in store_ids if cid}
    chunk_ids = [str(row.get("chunk_id")) for row in chunks if row.get("chunk_id")]
    chunk_id_set = set(chunk_ids)

    only_store = store_id_set - chunk_id_set
    only_chunks = chunk_id_set - store_id_set
    if only_store:
        errors.append(f"[{module}] store 有而 chunks 无的 chunk_id：{_sample(only_store)}")
    if only_chunks:
        errors.append(f"[{module}] chunks 有而 store 无的 chunk_id：{_sample(only_chunks)}")

    bad_dims = [
        cid
        for doc in docs
        if len(doc["embedding"]) != EMBEDDING_DIMENSION
        for cid in [doc["metadata"].get("chunk_id", "?")]
    ]
    if bad_dims:
        errors.append(
            f"[{module}] 向量维度不是 {EMBEDDING_DIMENSION}：{_sample(set(bad_dims))}"
        )

    if module == "spells":
        toc_by_chunk = {str(row.get("chunk_id")): row.get("chm_toc_path") for row in chunks}
        mismatched = []
        for doc in docs:
            cid = str(doc["metadata"].get("chunk_id"))
            if cid not in toc_by_chunk:
                continue
            if doc["metadata"].get("tocPath") != toc_by_chunk[cid]:
                mismatched.append(cid)
        if mismatched:
            errors.append(
                "[spells] tocPath 与 chunks.chm_toc_path 不一致："
                + _sample(set(mismatched))
            )

    if module == "traits":
        missing = [
            doc["metadata"].get("chunk_id", "?")
            for doc in docs
            if "trait_type" not in doc["metadata"]
        ]
        if missing:
            errors.append(
                f"[traits] 有 {len(missing)} 条缺少 metadata.trait_type 键：{_sample(set(missing))}"
            )

    if module == "races":
        by_chunk = {str(doc["metadata"].get("chunk_id")): doc for doc in docs}
        for cid in RACE_TARGET_IDS:
            doc = by_chunk.get(cid)
            if doc is None:
                errors.append(f"[races] 缺少 KN-120/AKN-028 目标条目 {cid}")
                continue
            for key, expected in zip(("race_name", "race_name_en"), RACE_TARGET_NAME):
                actual = doc["metadata"].get(key)
                if actual != expected:
                    errors.append(
                        f"[races] {cid} 的 {key} 期望 {expected!r}，实际 {actual!r}"
                    )

    return len(store)


def _check_list(repo_root: Path, arcname: str, rel: str, errors: list[str]) -> dict:
    path = repo_root / "pf_data/phase1/vectorizer/output" / rel
    if not path.is_file():
        errors.append(f"缺少清单 {path}")
        return {}
    payload = _read_json(path, errors)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        errors.append(f"清单 {path} 顶层不是对象")
        return {}

    if arcname in ("equipment_lists.json", "feat_lists.json", "race_lists.json"):
        entries = payload.get("entries")
        total = (payload.get("stats") or {}).get("total")
        if not isinstance(entries, list) or not entries:
            errors.append(f"清单 {arcname} entries 为空")
        if not isinstance(total, int) or total <= 0:
            errors.append(f"清单 {arcname} stats.total 非正：{total!r}")
        return {"total": total, "entries": len(entries) if isinstance(entries, list) else 0}

    if arcname in ("class_tables.json", "spell_lists.json", "spell_lists_union.json"):
        classes = payload.get("classes")
        if not isinstance(classes, dict) or not classes:
            errors.append(f"清单 {arcname} classes 为空")
            return {"classes": 0}
        return {"classes": len(classes)}

    if arcname == "rule_tables.json":
        tables = payload.get("tables")
        counts = payload.get("counts") or {}
        declared = counts.get("tables")
        if not isinstance(tables, dict) or not tables:
            errors.append(f"清单 {arcname} tables 为空")
            return {"tables": 0}
        if declared != len(tables):
            errors.append(
                f"清单 {arcname} counts.tables={declared!r} 与实际 {len(tables)} 张不一致"
            )
        if len(tables) < RULE_TABLE_BASELINE:
            errors.append(
                f"清单 {arcname} 规则表 {len(tables)} 张，低于基线 {RULE_TABLE_BASELINE} 张"
            )
        return {"tables": len(tables)}

    return {}


EXPECTED_RELEASE_COUNT = len(MODULES) * 2 + len(LIST_FILES)


def _ensure_unique_arcnames(arcnames: list[str]) -> None:
    seen = set()
    duplicates = []
    for arcname in arcnames:
        if arcname in seen and arcname not in duplicates:
            duplicates.append(arcname)
        seen.add(arcname)
    if duplicates:
        raise ValueError("发布文件 arcname 重复：" + "、".join(duplicates))


def collect_release_files(data_home: Path, repo_root: Path) -> list[tuple[Path, str]]:
    output = repo_root / "pf_data/phase1/vectorizer/output"
    files = [
        (data_home / f"vector_store_{module}.json", f"vector_store_{module}.json")
        for module in MODULES
    ]
    files += [
        (
            output / module_dir / "chunks.jsonl",
            f"output/{module_dir}/chunks.jsonl",
        )
        for module_dir in MODULES.values()
    ]
    files += [(output / rel, f"output/{rel}") for rel in LIST_FILES.values()]
    _ensure_unique_arcnames([arcname for _, arcname in files])
    return files


def validate(data_home, repo_root) -> ValidationResult:
    data_home = Path(data_home).expanduser()
    repo_root = Path(repo_root).expanduser()
    result = ValidationResult()

    module_counts = {}
    for module in MODULES:
        module_counts[module] = _check_module(data_home, repo_root, module, result.errors)

    list_stats = {}
    for arcname, rel in LIST_FILES.items():
        list_stats[arcname] = _check_list(repo_root, arcname, rel, result.errors)

    try:
        result.release_files = collect_release_files(data_home, repo_root)
    except ValueError as exc:
        result.release_files = []
        result.errors.append(str(exc))

    missing = [str(src) for src, _ in result.release_files if not src.is_file()]
    if missing:
        result.errors.append("发布文件缺失：" + _sample(missing))
    if len(result.release_files) != EXPECTED_RELEASE_COUNT:
        result.errors.append(
            f"发布文件数 {len(result.release_files)}，预期 {EXPECTED_RELEASE_COUNT}"
        )

    result.stats = {"modules": module_counts, "lists": list_stats}
    return result


def _print_errors(result: ValidationResult) -> None:
    print(f"发布数据校验失败（{len(result.errors)} 项）：", file=sys.stderr)
    for error in result.errors:
        print(f"  - {error}", file=sys.stderr)


def _print_stats(result: ValidationResult) -> None:
    for module, count in result.stats["modules"].items():
        print(f"  {module:<10} {count} 条")
    rule_count = result.stats["lists"].get("rule_tables.json", {}).get("tables", 0)
    print(f"  清单 7 份，规则表 {rule_count} 张")
    print(f"发布文件数：{len(result.release_files)}")


def _write_zip(files: list[tuple[Path, str]], target: Path) -> None:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src, arcname in files:
            zf.write(src, arcname=arcname)
        names = zf.namelist()
    _ensure_unique_arcnames(names)
    if len(names) != len(files):
        raise ValueError(f"数据包文件数 {len(names)}，预期 {len(files)}")


def package_release(data_home, repo_root, zip_path) -> int:
    zip_path = Path(zip_path).expanduser()
    result = validate(data_home, repo_root)
    if not result.ok:
        _print_errors(result)
        print(f"错误：数据包未更新（{zip_path}）", file=sys.stderr)
        return 1

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=zip_path.parent, prefix=f".{zip_path.name}.", suffix=".tmp"
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        _write_zip(result.release_files, temp_path)
        os.replace(temp_path, zip_path)
    except (OSError, ValueError) as exc:
        try:
            temp_path.unlink()
        except OSError:
            pass
        print(f"错误：数据包未更新（{zip_path}）：{exc}", file=sys.stderr)
        return 1

    digest = hashlib.sha256()
    with zip_path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    _print_stats(result)
    print(f"  数据包 {zip_path}")
    print(f"  文件数 {len(result.release_files)}")
    print(f"  大小 {zip_path.stat().st_size / 1048576:.1f} MB")
    print(f"  SHA-256 {digest.hexdigest()}")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--package"]:
        if len(argv) != 4:
            print(
                "用法：validate_release_data.py --package <zip> <data-home> <repo-root>",
                file=sys.stderr,
            )
            return 2
        return package_release(argv[2], argv[3], argv[1])
    if len(argv) != 2:
        print(
            "用法：validate_release_data.py <data-home> <repo-root>",
            file=sys.stderr,
        )
        return 2

    result = validate(argv[0], argv[1])
    if not result.ok:
        _print_errors(result)
        return 1

    _print_stats(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
