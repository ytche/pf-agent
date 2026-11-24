import json
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import release_audit as audit


STATS = {
    "modules": {
        "classes": 10,
        "equipment": 20,
        "feats": 30,
        "races": 40,
        "rules": 50,
        "skills": 60,
        "spells": 70,
        "traits": 80,
    },
    "lists": {
        "equipment_lists.json": {"total": 1, "entries": 1},
        "feat_lists.json": {"total": 1, "entries": 1},
        "race_lists.json": {"total": 1, "entries": 1},
        "class_tables.json": {"classes": 1},
        "spell_lists.json": {"classes": 1},
        "spell_lists_union.json": {"classes": 1},
        "rule_tables.json": {"tables": 612},
    },
}


def _git(repo: Path, *args, **env):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    ).stdout.strip()


def _init_repo(path: Path, files: dict[str, str], message="init") -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "tester")
    for rel, content in files.items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", message)
    _git(path, "commit", "-q", "--allow-empty", "-m", "baseline")
    return path


def _make_zip(path: Path, count: int = 23) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    names = (
        [f"vector_store_m{i}.json" for i in range(count - 15)]
        + [f"output/模块{i}/chunks.jsonl" for i in range(8)]
        + [f"output/清单/l{i}.json" for i in range(7)]
    )
    with zipfile.ZipFile(path, "w") as zf:
        for name in names:
            zf.writestr(name, "{}")
    return path


@pytest.fixture
def repos(tmp_path):
    private = _init_repo(
        tmp_path / "private",
        {"README.md": "# 私有\n", "docs/DEPLOYMENT.md": "# 部署\n"},
    )
    public = _init_repo(
        tmp_path / "public",
        {"README.md": "# 公开\n", "docs/DEPLOYMENT.md": "# 部署\n"},
    )
    _git(public, "tag", "v0.4.0")
    return private, public


def _build(tmp_path, repos, zip_count=23, **kwargs):
    private, public = repos
    zip_path = _make_zip(tmp_path / "dist/pf-agent-data-20261119.zip", zip_count)
    notes = tmp_path / "dist/data-release-notes-20261119.md"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("## 数据包\n", encoding="utf-8")
    params = {
        "version": "0.4.0",
        "data_date": "20261119",
        "private_repo": private,
        "public_clone": public,
        "zip_path": zip_path,
        "notes_path": notes,
        "stats": STATS,
        "test_report": "docs/test-reports/x.md",
        "remote_tags": "",
    }
    params.update(kwargs)
    return audit.build_audit(**params)


def test_build_audit_records_required_facts(tmp_path, repos):
    result = _build(tmp_path, repos)

    assert result["private"]["commit"]
    assert result["public"]["commit"]
    assert result["public"]["tag"] == "v0.4.0"
    assert result["public"]["tag_exists_on_remote"] is False
    assert result["data_zip"]["file_count"] == 23
    assert len(result["data_zip"]["files"]) == 23
    assert all(len(f["sha256"]) == 64 for f in result["data_zip"]["files"])
    assert result["vector_stores"]["classes"] == 10
    assert result["lists"]["rule_tables.json"]["tables"] == 612
    assert result["tests"]["acceptance_report"] == "docs/test-reports/x.md"
    assert result["release_status"] == {
        "pushed": False,
        "release_uploaded": False,
        "ghcr_published": False,
        "note": result["release_status"]["note"],
    }
    assert result["public_guard"]["ok"] is True
    assert result["public_guard"]["errors"] == []


def test_build_audit_rejects_wrong_file_count(tmp_path, repos):
    with pytest.raises(audit.ReleaseAuditError, match="23"):
        _build(tmp_path, repos, zip_count=14)


def test_build_audit_fails_on_sensitive_file(tmp_path, repos):
    private, public = repos
    (public / ".env").write_text("KEY=value\n", encoding="utf-8")
    _git(public, "add", "-A")
    _git(public, "commit", "-q", "-m", "leak")

    with pytest.raises(audit.ReleaseAuditError, match=".env"):
        _build(tmp_path, repos)


def test_build_audit_detects_remote_tag(tmp_path, repos):
    result = _build(tmp_path, repos, remote_tags="abc\trefs/tags/v0.4.0\n")

    assert result["public"]["tag_exists_on_remote"] is True


@pytest.mark.parametrize(
    "remote_tags, expected",
    [
        ("abc\trefs/tags/v0.4.0\n", True),
        ("abc\trefs/tags/v0.4.0^{}\n", True),
        ("abc\trefs/tags/v0.4.0-rc1\n", False),
        ("abc\trefs/tags/v0.4.01\n", False),
        ("abc\trefs/tags/data-20261119\n", False),
        ("", False),
    ],
)
def test_remote_tag_detection_is_exact(tmp_path, repos, remote_tags, expected):
    result = _build(tmp_path, repos, remote_tags=remote_tags)

    assert result["public"]["tag_exists_on_remote"] is expected


def test_remote_tag_lookup_failure_is_a_clear_error(tmp_path, repos, monkeypatch):
    private, public = repos

    class Failed:
        returncode = 128
        stdout = ""
        stderr = "fatal: unable to access 'https://github.com/ytche/pf-agent/': 网络不可达"

    monkeypatch.setattr(audit.subprocess, "run", lambda *a, **k: Failed())

    with pytest.raises(audit.ReleaseAuditError, match="ls-remote"):
        audit.remote_tag_refs(public)
    with pytest.raises(audit.ReleaseAuditError, match="release_audit.py"):
        audit.remote_tag_refs(public)


def test_remote_tag_lookup_uses_short_timeout_and_no_prompt(tmp_path, repos, monkeypatch):
    private, public = repos
    captured = {}

    class Ok:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return Ok()

    monkeypatch.setattr(audit.subprocess, "run", fake_run)

    audit.remote_tag_refs(public)

    assert captured["timeout"] == audit.REMOTE_TIMEOUT_SECONDS
    assert captured["timeout"] <= 20
    assert captured["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_remote_tag_lookup_timeout_is_a_clear_error(tmp_path, repos, monkeypatch):
    private, public = repos

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    monkeypatch.setattr(audit.subprocess, "run", fake_run)

    with pytest.raises(audit.ReleaseAuditError, match="超时"):
        audit.remote_tag_refs(public)
    with pytest.raises(audit.ReleaseAuditError, match="release_audit.py"):
        audit.remote_tag_refs(public)


def test_recovery_message_does_not_claim_snapshot_rerun_skips_commit(tmp_path, repos, monkeypatch):
    private, public = repos

    class Failed:
        returncode = 128
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(audit.subprocess, "run", lambda *a, **k: Failed())

    with pytest.raises(audit.ReleaseAuditError) as excinfo:
        audit.remote_tag_refs(public)

    message = str(excinfo.value)
    assert "跳过 commit" not in message
    assert "删除" in message and "tag" in message


def test_write_audit_archives_with_0644(tmp_path, repos):
    result = _build(tmp_path, repos)
    dist = tmp_path / "dist"
    archive = tmp_path / "archive/v0.4.0"

    written = audit.write_audit(result, dist, archive)

    assert written == dist / "release-audit-v0.4.0.json"
    for name in ("pf-agent-data-20261119.zip", "data-release-notes-20261119.md",
                 "release-audit-v0.4.0.json"):
        target = archive / name
        assert target.is_file()
        assert stat.S_IMODE(target.stat().st_mode) == 0o644
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["persistent"]["archive_dir"] == str(archive)
    assert payload["persistent"]["zip"]["sha256"] == result["data_zip"]["sha256"]
    archived = json.loads((archive / "release-audit-v0.4.0.json").read_text(encoding="utf-8"))
    assert archived["data_zip"]["sha256"] == result["data_zip"]["sha256"]


def test_write_audit_refuses_different_zip_for_same_version(tmp_path, repos):
    dist = tmp_path / "dist"
    archive = tmp_path / "archive/v0.4.0"
    audit.write_audit(_build(tmp_path, repos), dist, archive)

    other = _build(tmp_path / "second", repos)
    other["data_zip"]["sha256"] = "0" * 64

    with pytest.raises(audit.ReleaseAuditError, match="已存在"):
        audit.write_audit(other, dist, archive)

    existing = json.loads((archive / "release-audit-v0.4.0.json").read_text(encoding="utf-8"))
    assert existing["data_zip"]["sha256"] != "0" * 64
