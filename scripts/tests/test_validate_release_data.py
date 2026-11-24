import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import validate_release_data as vrd


MODULE_DIRS = {
    "classes": "职业",
    "equipment": "装备",
    "feats": "专长",
    "races": "种族",
    "rules": "规则",
    "skills": "技能",
    "spells": "法术",
    "traits": "背景特性",
}

LISTS = {
    "装备/equipment_lists.json": {"entries": [{"name": "长剑"}], "stats": {"total": 1}},
    "专长/feat_lists.json": {"entries": [{"name": "猛力攻击"}], "stats": {"total": 1}},
    "种族/race_lists.json": {"entries": [{"name": "矮人"}], "stats": {"total": 1}},
    "职业/class_tables.json": {"classes": {"战士": {"max_level": 20}}},
    "法术/spell_lists.json": {"classes": {"法师": {"levels": {"1": ["魔法飞弹"]}}}},
    "法术/spell_lists_union.json": {"classes": {"法师": {"levels": {"1": ["魔法飞弹"]}}}},
    "规则/rule_tables.json": {
        "counts": {"tables": 612},
        "tables": {f"table_{i:03d}": {"name": f"表{i}"} for i in range(612)},
    },
}


def _doc(chunk_id, text="正文", component_type="rule_section", **metadata):
    meta = {
        "chunk_id": chunk_id,
        "doc_id": "page_1",
        "component_type": component_type,
        "title": "标题",
    }
    meta.update(metadata)
    return {
        "id": str(uuid.uuid4()),
        "text": text,
        "embedding": [0.0] * 1024,
        "metadata": meta,
    }


def _chunk(chunk_id, component_type="rule_section", toc="规则 → 核心规则"):
    return {
        "chunk_id": chunk_id,
        "doc_id": "page_1",
        "category": "rule",
        "component_type": component_type,
        "title": "标题",
        "text": "正文",
        "chm_toc_path": toc,
    }


def _module_docs(module):
    if module == "races":
        return [
            _doc(
                f"race_page_812_{i:04d}",
                component_type="race_trait",
                race_name="阿斯托莫伊人",
                race_name_en="Astomoi",
            )
            for i in range(10)
        ]
    if module == "spells":
        return [_doc("spell_page_1_0000", component_type="spell", tocPath="法术 → CRB")]
    if module == "traits":
        return [_doc("trait_page_1_0000", component_type="trait", trait_type="社会")]
    return [_doc(f"{module}_page_1_0000")]


def _module_chunks(module):
    if module == "races":
        return [_chunk(f"race_page_812_{i:04d}", "race_trait", "种族 → 种族特性") for i in range(10)]
    if module == "spells":
        return [_chunk("spell_page_1_0000", "spell", "法术 → CRB")]
    if module == "traits":
        return [_chunk("trait_page_1_0000", "trait", "背景特性 → 社会背景")]
    return [_chunk(f"{module}_page_1_0000")]


def build_valid_dataset(root: Path):
    data_home = root / "data_home"
    repo_root = root / "repo"
    output = repo_root / "pf_data/phase1/vectorizer/output"
    data_home.mkdir(parents=True)

    for module in MODULES_KEYS:
        docs = _module_docs(module)
        store = {doc["id"]: doc for doc in docs}
        (data_home / f"vector_store_{module}.json").write_text(
            json.dumps(store, ensure_ascii=False), encoding="utf-8"
        )
        module_dir = output / MODULE_DIRS[module]
        module_dir.mkdir(parents=True)
        with (module_dir / "chunks.jsonl").open("w", encoding="utf-8") as fh:
            for chunk in _module_chunks(module):
                fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    for rel, payload in LISTS.items():
        path = output / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    return data_home, repo_root


MODULES_KEYS = list(MODULE_DIRS)


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _errors_text(result):
    return "\n".join(result.errors)


def test_valid_dataset_has_twenty_three_release_files(tmp_path):
    data_home, repo_root = build_valid_dataset(tmp_path)

    result = vrd.validate(data_home, repo_root)

    assert result.ok, _errors_text(result)
    assert len(result.release_files) == 23
    arcnames = sorted(arc for _, arc in result.release_files)
    expected = sorted(
        [f"vector_store_{m}.json" for m in MODULES_KEYS]
        + [f"output/{MODULE_DIRS[m]}/chunks.jsonl" for m in MODULES_KEYS]
        + [f"output/{rel}" for rel in LISTS]
    )
    assert arcnames == expected


def test_missing_rule_tables_is_rejected(tmp_path):
    data_home, repo_root = build_valid_dataset(tmp_path)
    (repo_root / "pf_data/phase1/vectorizer/output/规则/rule_tables.json").unlink()

    result = vrd.validate(data_home, repo_root)

    assert not result.ok
    assert "rule_tables" in _errors_text(result)


def test_chunk_id_mismatch_is_rejected(tmp_path):
    data_home, repo_root = build_valid_dataset(tmp_path)
    store_path = data_home / "vector_store_equipment.json"
    store = _load(store_path)
    doc = next(iter(store.values()))
    doc["metadata"]["chunk_id"] = "equipment_ghost_0000"
    _dump(store_path, store)

    result = vrd.validate(data_home, repo_root)

    assert not result.ok
    assert "equipment" in _errors_text(result)
    assert "chunk_id" in _errors_text(result)


def test_non_1024_embedding_is_rejected(tmp_path):
    data_home, repo_root = build_valid_dataset(tmp_path)
    store_path = data_home / "vector_store_skills.json"
    store = _load(store_path)
    next(iter(store.values()))["embedding"] = [0.0] * 512
    _dump(store_path, store)

    result = vrd.validate(data_home, repo_root)

    assert not result.ok
    assert "skills" in _errors_text(result)
    assert "1024" in _errors_text(result)


def test_spell_toc_path_mismatch_is_rejected(tmp_path):
    data_home, repo_root = build_valid_dataset(tmp_path)
    store_path = data_home / "vector_store_spells.json"
    store = _load(store_path)
    next(iter(store.values()))["metadata"]["tocPath"] = "法术 → 旧目录"
    _dump(store_path, store)

    result = vrd.validate(data_home, repo_root)

    assert not result.ok
    assert "tocPath" in _errors_text(result)


def test_trait_missing_trait_type_key_is_rejected(tmp_path):
    data_home, repo_root = build_valid_dataset(tmp_path)
    store_path = data_home / "vector_store_traits.json"
    store = _load(store_path)
    next(iter(store.values()))["metadata"].pop("trait_type")
    _dump(store_path, store)

    result = vrd.validate(data_home, repo_root)

    assert not result.ok
    assert "trait_type" in _errors_text(result)


def test_race_target_missing_english_name_is_rejected(tmp_path):
    data_home, repo_root = build_valid_dataset(tmp_path)
    store_path = data_home / "vector_store_races.json"
    store = _load(store_path)
    for doc in store.values():
        if doc["metadata"]["chunk_id"] == "race_page_812_0008":
            doc["metadata"].pop("race_name_en")
    _dump(store_path, store)

    result = vrd.validate(data_home, repo_root)

    assert not result.ok
    assert "race_page_812_0008" in _errors_text(result)
    assert "race_name_en" in _errors_text(result)


def test_missing_store_is_rejected(tmp_path):
    data_home, repo_root = build_valid_dataset(tmp_path)
    (data_home / "vector_store_rules.json").unlink()

    result = vrd.validate(data_home, repo_root)

    assert not result.ok
    assert "vector_store_rules.json" in _errors_text(result)


def test_main_returns_nonzero_on_failure(tmp_path, capsys):
    data_home, repo_root = build_valid_dataset(tmp_path)
    (repo_root / "pf_data/phase1/vectorizer/output/规则/rule_tables.json").unlink()

    exit_code = vrd.main([str(data_home), str(repo_root)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "rule_tables" in captured.err


def test_main_returns_zero_on_success(tmp_path, capsys):
    data_home, repo_root = build_valid_dataset(tmp_path)

    exit_code = vrd.main([str(data_home), str(repo_root)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "23" in captured.out


@pytest.mark.parametrize("payload", [["not", "a", "dict"], "not-a-dict", 42])
def test_non_dict_store_is_rejected_without_traceback(tmp_path, payload):
    data_home, repo_root = build_valid_dataset(tmp_path)
    store_path = data_home / "vector_store_rules.json"
    _dump(store_path, payload)

    result = vrd.validate(data_home, repo_root)

    assert not result.ok
    assert "vector_store_rules.json" in _errors_text(result)


def test_empty_store_is_rejected(tmp_path):
    data_home, repo_root = build_valid_dataset(tmp_path)
    _dump(data_home / "vector_store_skills.json", {})

    result = vrd.validate(data_home, repo_root)

    assert not result.ok
    assert "vector_store_skills.json" in _errors_text(result)


def test_rule_tables_below_baseline_is_rejected(tmp_path):
    data_home, repo_root = build_valid_dataset(tmp_path)
    list_path = repo_root / "pf_data/phase1/vectorizer/output/规则/rule_tables.json"
    payload = _load(list_path)
    payload["tables"] = {f"table_{i:03d}": {} for i in range(611)}
    payload["counts"]["tables"] = 611
    _dump(list_path, payload)

    result = vrd.validate(data_home, repo_root)

    assert not result.ok
    assert "612" in _errors_text(result)


def test_duplicate_arcnames_are_rejected():
    with pytest.raises(ValueError):
        vrd._ensure_unique_arcnames(["lists/a.json", "lists/a.json"])


def test_collect_release_files_arcnames_are_unique(tmp_path):
    data_home, repo_root = build_valid_dataset(tmp_path)

    files = vrd.collect_release_files(data_home, repo_root)

    arcnames = [arc for _, arc in files]
    assert len(arcnames) == 23
    assert len(set(arcnames)) == 23


def test_package_release_writes_twenty_three_files(tmp_path):
    import zipfile

    data_home, repo_root = build_valid_dataset(tmp_path)
    zip_path = tmp_path / "dist/pf-agent-data-test.zip"

    exit_code = vrd.package_release(data_home, repo_root, zip_path)

    assert exit_code == 0
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert len(names) == 23
    assert len(set(names)) == 23


def test_package_release_validation_failure_keeps_existing_zip(tmp_path, capsys):
    data_home, repo_root = build_valid_dataset(tmp_path)
    (repo_root / "pf_data/phase1/vectorizer/output/规则/rule_tables.json").unlink()
    zip_path = tmp_path / "pf-agent-data-test.zip"
    zip_path.write_bytes(b"OLD-PACKAGE")

    exit_code = vrd.package_release(data_home, repo_root, zip_path)

    captured = capsys.readouterr()
    assert exit_code != 0
    assert zip_path.read_bytes() == b"OLD-PACKAGE"
    assert not list(tmp_path.glob("*.tmp"))
    assert "未更新" in captured.err


def test_package_release_write_failure_keeps_existing_zip_and_cleans_temp(
    tmp_path, monkeypatch, capsys
):
    data_home, repo_root = build_valid_dataset(tmp_path)
    zip_path = tmp_path / "pf-agent-data-test.zip"
    zip_path.write_bytes(b"OLD-PACKAGE")

    def boom(files, target):
        raise OSError("disk full")

    monkeypatch.setattr(vrd, "_write_zip", boom)

    exit_code = vrd.package_release(data_home, repo_root, zip_path)

    captured = capsys.readouterr()
    assert exit_code != 0
    assert zip_path.read_bytes() == b"OLD-PACKAGE"
    assert not list(tmp_path.glob("*.tmp"))
    assert "未更新" in captured.err
