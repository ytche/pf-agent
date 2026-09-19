"""test_build.py — 数据产物可复现构建链（build_manifest + build.py）测试

验收标准第 8、9 条：
  - manifest 结构校验（必填字段/路径存在/与 cicd 装配表一致）
  - cicd 命令串与 cicd/verify.py 装配表一致性断言
  - 指纹计算（改内容→变、改 mtime→不变）
  - 拓扑排序（导出步在依赖类目步之后）
  - negative：manifest 指向不存在路径 → 装载期报错，不静默跳过
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PHASE1 = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PHASE1))

from vectorizer import build as build_mod
from vectorizer.build import (
    ManifestError, cicd_command, compute_fingerprint, expand_inputs,
    load_manifest, artifact_command,
)

MANIFEST = PHASE1 / "vectorizer" / "build_manifest.json"


@pytest.fixture(scope="module")
def loaded():
    return load_manifest(MANIFEST, PHASE1)


# ---------- 8a. manifest 结构校验 ----------

class TestManifestStructure:
    def test_required_top_level_fields(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        assert data["build_version"]
        assert data["artifacts"], "至少登记一个 artifact"

    def test_artifact_required_fields(self, loaded):
        _, artifacts, _ = loaded
        for art in artifacts:
            for field in ("name", "kind", "outputs", "inputs", "config_deps", "schema", "via"):
                assert field in art, f"{art.get('name')} 缺字段 {field}"
            assert art["outputs"], f"{art['name']} outputs 为空"
            assert art["schema"]["file"], f"{art['name']} schema.file 为空"

    def test_unique_names(self, loaded):
        _, artifacts, _ = loaded
        names = [a["name"] for a in artifacts]
        assert len(names) == len(set(names)), "artifact 重名"

    def test_category_artifacts_registered_in_cicd(self, loaded):
        """via=cicd 的类目必须已在 cicd 装配表（装配表防拼写漂移同源）"""
        from vectorizer.cicd.verify import CATEGORIES
        _, artifacts, _ = loaded
        for art in artifacts:
            if art["via"] == "cicd":
                assert art["category"] in CATEGORIES, art["name"]

    def test_referenced_paths_exist(self, loaded):
        """装载即校验通过（config_deps/script/inputs glob 均真实存在），此处再点验"""
        _, artifacts, _ = loaded
        for art in artifacts:
            for dep in art["config_deps"]:
                assert (PHASE1 / dep).is_file(), f"{art['name']}: {dep}"
            if art.get("script"):
                assert (PHASE1 / art["script"]).is_file(), art["script"]
            assert expand_inputs(art["inputs"], PHASE1), art["name"]

    def test_nine_artifacts_including_export(self, loaded):
        _, artifacts, _ = loaded
        assert len(artifacts) >= 9
        kinds = {a["kind"] for a in artifacts}
        assert "export_script" in kinds


# ---------- 8b. cicd 命令串与装配表一致性 ----------

class TestCicdCommandConsistency:
    def test_cicd_command_string(self, loaded):
        from vectorizer.cicd.verify import CATEGORIES
        _, artifacts, _ = loaded
        for art in artifacts:
            if art["via"] != "cicd":
                continue
            assert artifact_command(art) == [
                "python3", "-m", "vectorizer.cicd", "verify",
                "--category", art["category"]]
            # 输出目录与装配表同源（防手工抄错）
            out_dir = CATEGORIES[art["category"]]["output_dir"]
            assert any(o.startswith(out_dir + "/") for o in art["outputs"])

    def test_direct_artifacts_have_command(self, loaded):
        _, artifacts, _ = loaded
        for art in artifacts:
            if art["via"] == "direct":
                assert art["command"], art["name"]


# ---------- 8c. 指纹计算 ----------

class TestFingerprint:
    @pytest.fixture()
    def sandbox(self, tmp_path):
        """独立 mini 构建目录：src/a.md + cfg.json + script.py + manifest"""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.md").write_text("hello\n", encoding="utf-8")
        (tmp_path / "cfg.json").write_text("{}", encoding="utf-8")
        (tmp_path / "script.py").write_text("pass\n", encoding="utf-8")
        art = {
            "name": "t",
            "inputs": ["src/**"],
            "config_deps": ["cfg.json"],
            "script": "script.py",
            "outputs": [],
        }
        return tmp_path, art

    def test_content_change_changes_fingerprint(self, sandbox):
        root, art = sandbox
        fp1 = compute_fingerprint(art, "m1", root)
        (root / "src" / "a.md").write_text("changed\n", encoding="utf-8")
        fp2 = compute_fingerprint(art, "m1", root)
        assert fp1 != fp2

    def test_mtime_change_keeps_fingerprint(self, sandbox):
        root, art = sandbox
        fp1 = compute_fingerprint(art, "m1", root)
        os.utime(root / "src" / "a.md", (4_000_000_000, 4_000_000_000))
        fp2 = compute_fingerprint(art, "m1", root)
        assert fp1 == fp2

    def test_manifest_hash_in_fingerprint(self, sandbox):
        root, art = sandbox
        assert compute_fingerprint(art, "m1", root) != compute_fingerprint(art, "m2", root)

    def test_config_dep_change_changes_fingerprint(self, sandbox):
        root, art = sandbox
        fp1 = compute_fingerprint(art, "m1", root)
        (root / "cfg.json").write_text('{"x": 1}', encoding="utf-8")
        assert compute_fingerprint(art, "m1", root) != fp1

    def test_script_change_changes_fingerprint(self, sandbox):
        root, art = sandbox
        fp1 = compute_fingerprint(art, "m1", root)
        (root / "script.py").write_text("# changed\n", encoding="utf-8")
        assert compute_fingerprint(art, "m1", root) != fp1


# ---------- 8d. 拓扑排序 ----------

class TestTopoOrder:
    def test_export_step_after_category_steps(self, loaded):
        _, artifacts, _ = loaded
        order = [a["name"] for a in artifacts]
        for export in (a for a in artifacts if a["kind"] == "export_script"):
            exp_idx = order.index(export["name"])
            for art in artifacts:
                shared = set(expand_inputs(export["inputs"], PHASE1)) & set(art["outputs"])
                if shared:
                    assert order.index(art["name"]) < exp_idx, (
                        f"{export['name']} 依赖 {art['name']} 的产物 {sorted(shared)}，"
                        f"必须声明在其之后")

    def test_load_rejects_dependency_after_dependent(self, tmp_path):
        """拓扑序违反（被依赖者声明在依赖者之后）→ 装载期报错"""
        root = tmp_path
        (root / "gen.py").write_text("pass\n", encoding="utf-8")
        (root / "in.md").write_text("x\n", encoding="utf-8")
        data = {
            "build_version": "1.0",
            "artifacts": [
                {"name": "export", "kind": "export_script", "via": "direct",
                 "command": ["python3", "gen.py"], "script": "gen.py",
                 "outputs": ["out.json"], "inputs": ["mid.json"],
                 "config_deps": [], "schema": {"file": "out.json", "version_field": None}},
                {"name": "mid", "kind": "category_pipeline", "via": "direct",
                 "command": ["python3", "gen.py"],
                 "outputs": ["mid.json"], "inputs": ["in.md"],
                 "config_deps": [], "schema": {"file": "mid.json", "version_field": None}},
            ],
        }
        # 让 export 的 inputs 命中 mid 的 outputs：创建 mid.json
        (root / "mid.json").write_text("{}", encoding="utf-8")
        mpath = root / "manifest.json"
        mpath.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ManifestError, match="拓扑序"):
            load_manifest(mpath, root)


# ---------- 9. negative：不存在路径 → 装载期报错 ----------

class TestLoadTimeErrors:
    def _write_manifest(self, root: Path, artifact_overrides: dict) -> Path:
        art = {
            "name": "t", "kind": "export_script", "via": "direct",
            "command": ["python3", "s.py"], "script": "s.py",
            "outputs": ["o.json"], "inputs": ["in/**"],
            "config_deps": [], "schema": {"file": "o.json", "version_field": None},
        }
        art.update(artifact_overrides)
        data = {"build_version": "1.0", "artifacts": [art]}
        p = root / "manifest.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def _sandbox(self, tmp_path):
        (tmp_path / "in").mkdir()
        (tmp_path / "in" / "a.md").write_text("x\n", encoding="utf-8")
        (tmp_path / "s.py").write_text("pass\n", encoding="utf-8")
        return tmp_path

    def test_missing_script_rejected(self, tmp_path):
        root = self._sandbox(tmp_path)
        p = self._write_manifest(root, {"script": "no_such_script.py"})
        with pytest.raises(ManifestError, match="script 不存在"):
            load_manifest(p, root)

    def test_missing_config_dep_rejected(self, tmp_path):
        root = self._sandbox(tmp_path)
        p = self._write_manifest(root, {"config_deps": ["no_such_config.json"]})
        with pytest.raises(ManifestError, match="config_dep 不存在"):
            load_manifest(p, root)

    def test_empty_inputs_glob_rejected(self, tmp_path):
        root = self._sandbox(tmp_path)
        p = self._write_manifest(root, {"inputs": ["no_such_dir/**"]})
        with pytest.raises(ManifestError, match="未命中任何文件"):
            load_manifest(p, root)

    def test_missing_required_field_rejected(self, tmp_path):
        root = self._sandbox(tmp_path)
        p = self._write_manifest(root, {"via": "bogus"})
        with pytest.raises(ManifestError):
            load_manifest(p, root)

    def test_cicd_category_not_in_assembly_rejected(self, tmp_path):
        root = self._sandbox(tmp_path)
        p = self._write_manifest(root, {"kind": "category_pipeline", "via": "cicd",
                                        "category": "no_such_cat"})
        with pytest.raises(ManifestError, match="装配表"):
            load_manifest(p, root)


# ---------- status/check CLI 冒烟 ----------

class TestCliSmoke:
    def test_status_runs_and_lists_artifacts(self):
        r = subprocess.run(
            [sys.executable, "-m", "vectorizer.build", "status"],
            capture_output=True, text=True, cwd=PHASE1, timeout=300)
        assert r.returncode == 0, r.stderr
        out = r.stdout
        for name in ("chunks.feat", "chunks.race", "chunks.trait", "chunks.equipment",
                     "chunks.rule", "chunks.spell", "chunks.profession", "chunks.skill",
                     "lists.spell"):
            assert name in out, f"status 未列出 {name}"
        # 状态栏存在；三态（fresh/stale/missing）出现哪一种都合法——
        # build_state.json 入库后干净树上常态为全 fresh，不得断言特定态
        assert "status" in out and any(s in out for s in ("fresh", "stale", "missing"))

    def test_status_fresh_stale_missing_states(self, loaded):
        """fabricated state 驱动三态判定（指纹比对，非 mtime）"""
        from vectorizer.build import _sha256_file
        _, artifacts, mh = loaded
        art = next(a for a in artifacts if a["name"] == "lists.spell")
        entry = {
            "fingerprint": compute_fingerprint(art, mh),
            "outputs": {o: _sha256_file(PHASE1 / o) for o in art["outputs"]},
        }
        assert build_mod.artifact_status(art, {"artifacts": {"lists.spell": entry}}, mh)["status"] == "fresh"
        # 产物漂移：state 记录假指纹 → stale
        drifted = {"artifacts": {"lists.spell": {**entry, "outputs": {
            o: "0" * 64 for o in art["outputs"]}}}}
        assert build_mod.artifact_status(art, drifted, mh)["status"] == "stale"
        # 输入漂移：state 指纹是别的值 → stale
        changed = {"artifacts": {"lists.spell": {**entry, "fingerprint": "0" * 64}}}
        assert build_mod.artifact_status(art, changed, mh)["status"] == "stale"
        # 无记录 / 产物缺失 → missing（sandbox 产物路径不存在）
        assert build_mod.artifact_status(art, {}, mh)["status"] == "missing"
        ghost = {"name": "ghost", "outputs": ["no_such_output.json"], "inputs": [],
                 "config_deps": [], "schema": {"file": "x", "version_field": None}}
        gone_state = {"artifacts": {"ghost": {"fingerprint": "f", "outputs": {}}}}
        assert build_mod.artifact_status(ghost, gone_state, mh)["status"] == "missing"


# ---------- 缺口补测：check 非零退出 / state 损坏 / schema 损坏态 ----------

class TestCheckAndCorruptState:
    def _sandbox_artifact(self, root: Path) -> dict:
        (root / "in").mkdir(exist_ok=True)
        (root / "in" / "a.md").write_text("x\n", encoding="utf-8")
        (root / "out.json").write_text('{"version": "1.0"}', encoding="utf-8")
        return {
            "name": "t", "kind": "export_script", "via": "direct",
            "command": ["python3", "-c", "pass"],
            "outputs": ["out.json"], "inputs": ["in/**"],
            "config_deps": [],
            "schema": {"file": "out.json", "version_field": "version", "expected": "1.0"},
        }

    def test_check_fails_on_schema_version_drift(self, tmp_path, capsys, request):
        """验收标准 6：schema version 不符 → check 非零且指明期望/实际"""
        from vectorizer.build import cmd_check
        art = self._sandbox_artifact(tmp_path)
        (tmp_path / "out.json").write_text('{"version": "0.9"}', encoding="utf-8")
        # cmd_check 内以模块级 PHASE1 为根，指向 sandbox
        monkey = request.getfixturevalue("monkeypatch")
        monkey.setattr(build_mod, "PHASE1", tmp_path)
        orig_sv = build_mod._schema_version
        monkey.setattr(build_mod, "_schema_version",
                      lambda a, root=None: orig_sv(a, tmp_path))
        state = {"build_version": "1.0",
                 "artifacts": {"t": {"fingerprint": "fp", "outputs": {"out.json": "h"}}}}
        data = {"build_version": "1.0"}
        rc = cmd_check([art], state, "mh", data)
        assert rc != 0
        out = capsys.readouterr().out
        assert "version" in out and "'0.9'" in out and "'1.0'" in out

    def test_check_fails_on_state_record_missing(self, tmp_path):
        from vectorizer.build import cmd_check
        art = self._sandbox_artifact(tmp_path)
        rc = cmd_check([art], {"build_version": "1.0"}, "mh", {"build_version": "1.0"})
        assert rc != 0

    def test_load_state_corrupt_json_exits(self, tmp_path):
        p = tmp_path / "build_state.json"
        p.write_text("not json{{{", encoding="utf-8")
        with pytest.raises(SystemExit):
            build_mod.load_state(p)

    def test_schema_version_corrupt_file_reported(self, tmp_path):
        """产物为非 JSON → _schema_version 显式 '<损坏:非JSON>'，不静默/不抛裸异常"""
        art = self._sandbox_artifact(tmp_path)
        (tmp_path / "out.json").write_text("not json{{{", encoding="utf-8")
        assert build_mod._schema_version(art, tmp_path) == "<损坏:非JSON>"
