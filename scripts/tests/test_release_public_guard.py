import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import release_public_guard as guard


def _touch(root: Path, rel: str, content: bytes | str = b"data"):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return path


def _scan(root: Path):
    tracked = sorted(
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file()
    )
    return guard.scan(root, tracked)


def test_clean_public_tree_passes(tmp_path):
    _touch(tmp_path, "README.md", "# 说明\n正常文本\n")
    _touch(tmp_path, ".env.example", "DEEPSEEK_PF_API=\n")
    _touch(tmp_path, "docs/DEPLOYMENT.md", "# 部署\n")
    _touch(tmp_path, "scripts/release_public_snapshot.sh", "#!/bin/bash\n")

    errors = _scan(tmp_path)

    assert errors == []


def test_real_env_file_is_rejected(tmp_path):
    _touch(tmp_path, ".env", "DEEPSEEK_PF_API=sk-real\n")

    errors = _scan(tmp_path)

    assert any(".env" in e and "密钥" in e or ".env" in e for e in errors)
    assert len(errors) == 1


def test_env_variant_is_rejected(tmp_path):
    _touch(tmp_path, "pf_agent/agent/.env.prod", "KEY=value\n")

    errors = _scan(tmp_path)

    assert errors


def test_kimi_code_directory_is_rejected(tmp_path):
    _touch(tmp_path, ".kimi-code/agents/architect.md", "# agent\n")

    errors = _scan(tmp_path)

    assert any(".kimi-code" in e for e in errors)


def test_ds_store_is_rejected(tmp_path):
    _touch(tmp_path, "docs/.DS_Store", b"\x00\x00")

    errors = _scan(tmp_path)

    assert any(".DS_Store" in e for e in errors)


def test_process_docs_are_rejected_but_deployment_allowed(tmp_path):
    _touch(tmp_path, "docs/DEPLOYMENT.md", "# 部署\n")
    _touch(tmp_path, "docs/design/方案.md", "# 方案\n")

    errors = _scan(tmp_path)

    assert any("docs/design/方案.md" in e for e in errors)
    assert not any("docs/DEPLOYMENT.md" in e for e in errors)


def test_build_artifacts_are_rejected(tmp_path):
    _touch(tmp_path, "pf_agent/agent/frontend/node_modules/a/index.js")
    _touch(tmp_path, "pf_agent/agent/target/classes/A.class")
    _touch(tmp_path, "pf_data/__pycache__/x.cpython-311.pyc")
    _touch(tmp_path, "pf_agent/agent/frontend/playwright-report/index.html")

    errors = _scan(tmp_path)

    text = "\n".join(errors)
    assert "node_modules" in text
    assert "target" in text
    assert "__pycache__" in text
    assert "playwright-report" in text


def test_key_material_files_are_rejected(tmp_path):
    _touch(tmp_path, "deploy/server.pem", "x\n")
    _touch(tmp_path, "deploy/id_rsa", "x\n")
    _touch(tmp_path, "deploy/app.jks", b"\x00\x01")

    errors = _scan(tmp_path)

    text = "\n".join(errors)
    assert "server.pem" in text
    assert "id_rsa" in text
    assert "app.jks" in text


def test_private_key_content_is_rejected(tmp_path):
    _touch(
        tmp_path,
        "docs/notes.md",
        # 分片拼接：本文件会进入公开快照，不能出现完整的私钥头字面量
        b"-----BEGIN RSA " + b"PRIVATE KEY-----\nMIIEow\n",
    )

    errors = _scan(tmp_path)

    assert any("私钥" in e for e in errors)


def test_token_content_is_rejected(tmp_path):
    _touch(tmp_path, "config/app.yml", b"token: ghp_" + b"a" * 36 + b"\n")

    errors = _scan(tmp_path)

    assert any("令牌" in e or "token" in e.lower() for e in errors)


def test_binary_files_are_not_content_scanned(tmp_path):
    _touch(
        tmp_path,
        "assets/logo.bin",
        b"\x00\x01\x02-----BEGIN RSA " + b"PRIVATE KEY-----",
    )

    errors = _scan(tmp_path)

    assert errors == []
