#!/usr/bin/env python3
"""发布审计清单生成器。

把一次发布的事实固化成 JSON：私有/公开 commit、数据包逐文件 SHA-256、8 个向量库
条数、7 份清单统计、测试报告路径、公开内容门禁结果和外发状态；并可选地把
zip / 数据说明 / 审计清单转存到持久目录（默认权限 0644），避免 /tmp 丢失。

同一版本重复生成时，若持久目录里已有审计记录且数据包 SHA 不同，直接失败，
避免同版本混用两个不同的包。

用法：
    python3 scripts/release_audit.py --version 0.4.0 --data-date 20261119 \
        --public-clone /tmp/pf-agent-public --dist-dir /tmp/pf-agent-dist \
        --archive-dir ~/.pf_agent_release/v0.4.0 \
        --test-report docs/test-reports/xxx.md
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import release_public_guard as guard
import validate_release_data as vrd

AUDIT_MODE = 0o644
AUDIT_NAME = "release-audit-v{version}.json"


class ReleaseAuditError(Exception):
    """审计事实不成立（文件数不符、门禁未过、同版本包冲突）。"""


def _git(repo: Path, *args) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def zip_manifest(zip_path: Path) -> list[dict]:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            broken = zf.testzip()
            if broken is not None:
                raise ReleaseAuditError(f"数据包损坏，首个坏文件：{broken}")
            infos = zf.infolist()
            if len(infos) != vrd.EXPECTED_RELEASE_COUNT:
                raise ReleaseAuditError(
                    f"数据包文件数 {len(infos)}，预期 {vrd.EXPECTED_RELEASE_COUNT}"
                )
            manifest = [
                {
                    "arcname": info.filename,
                    "bytes": info.file_size,
                    "sha256": hashlib.sha256(zf.read(info.filename)).hexdigest(),
                }
                for info in infos
            ]
    except zipfile.BadZipFile as exc:
        raise ReleaseAuditError(f"数据包不是合法 zip：{exc}") from exc
    manifest.sort(key=lambda item: item["arcname"])
    return manifest


REMOTE_TIMEOUT_SECONDS = 20

_RECOVERY_HINT = (
    "公开快照 commit 与本地 tag 已就绪，优先用同样的参数手动重跑 release_audit.py，"
    "不需要重打数据包。若确需重打整个快照：先删除未 push 的本地 tag"
    "（git -C <公开克隆> tag -d v<版本>），再执行 release_public_snapshot.sh；"
    "否则发布脚本的 tag 查重会先失败。"
)


def remote_tag_refs(public_clone: Path) -> str:
    """读取公开仓远程 tag 列表；失败或超时转成带恢复指引的审计错误。"""
    try:
        proc = subprocess.run(
            ["git", "-C", str(public_clone), "ls-remote", "--tags", "origin"],
            capture_output=True,
            text=True,
            timeout=REMOTE_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired:
        raise ReleaseAuditError(
            f"读取公开仓远程 tag 超时（超过 {REMOTE_TIMEOUT_SECONDS} 秒）。\n" + _RECOVERY_HINT
        ) from None
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"exit {proc.returncode}"
        raise ReleaseAuditError(
            f"无法读取公开仓远程 tag（git ls-remote 失败）：{detail}\n" + _RECOVERY_HINT
        )
    return proc.stdout


def _remote_has_tag(remote_tags: str, tag: str) -> bool:
    """逐行精确匹配 refs/tags/<tag>，兼容附注 tag 的 ^{} 解引用行。"""
    wanted = f"refs/tags/{tag}"
    for line in remote_tags.splitlines():
        parts = line.split()
        if not parts:
            continue
        ref = parts[-1]
        if ref in (wanted, f"{wanted}^{{}}"):
            return True
    return False


def _public_facts(public_clone: Path, version: str, remote_tags: str) -> dict:
    tracked = [p for p in _git(public_clone, "ls-files", "-z").split("\0") if p]
    tag = f"v{version}"
    tag_exists_locally = (
        subprocess.run(
            ["git", "-C", str(public_clone), "tag", "-l", tag],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        != ""
    )
    return {
        "repo": "ytche/pf-agent",
        "clone": str(public_clone),
        "commit": _git(public_clone, "rev-parse", "HEAD"),
        "short": _git(public_clone, "rev-parse", "--short", "HEAD"),
        "tag": tag,
        "tag_points_at": _git(public_clone, "rev-parse", f"{tag}^{{commit}}"),
        "parent_commit": _git(public_clone, "rev-parse", "HEAD~1"),
        "tag_exists_locally": tag_exists_locally,
        "tag_exists_on_remote": _remote_has_tag(remote_tags, tag),
        "tracked_files": len(tracked),
        "docs_files": sorted(p for p in tracked if p.startswith("docs/")),
        "diffstat_vs_parent": _git(public_clone, "diff", "--shortstat", "HEAD~1", "HEAD"),
        "tracked": tracked,
    }


def build_audit(
    *,
    version: str,
    data_date: str,
    private_repo: Path,
    public_clone: Path,
    zip_path: Path,
    notes_path: Path,
    stats: dict,
    test_report: str,
    remote_tags: str = "",
) -> dict:
    private_repo = Path(private_repo)
    public_clone = Path(public_clone)
    zip_path = Path(zip_path)
    notes_path = Path(notes_path)

    facts = _public_facts(public_clone, version, remote_tags)
    tracked = facts.pop("tracked")
    guard_errors = guard.scan(public_clone, tracked)
    if guard_errors:
        raise ReleaseAuditError(
            "公开内容门禁未通过：" + "；".join(guard_errors[:5])
            + (f"（另有 {len(guard_errors) - 5} 项）" if len(guard_errors) > 5 else "")
        )

    manifest = zip_manifest(zip_path)

    return {
        "version": version,
        "data_date": data_date,
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
        "release_status": {
            "pushed": False,
            "release_uploaded": False,
            "ghcr_published": False,
            "note": "脚本只生成本地产物，未执行任何外发动作",
        },
        "private": {
            "repo": "ytche/pf_agent",
            "commit": _git(private_repo, "rev-parse", "HEAD"),
            "short": _git(private_repo, "rev-parse", "--short", "HEAD"),
            "branch": _git(private_repo, "rev-parse", "--abbrev-ref", "HEAD"),
            "worktree_clean": _git(private_repo, "status", "--porcelain") == "",
        },
        "public": facts,
        "data_zip": {
            "path": str(zip_path),
            "size_bytes": zip_path.stat().st_size,
            "size_mib": round(zip_path.stat().st_size / 1048576, 2),
            "sha256": sha256_file(zip_path),
            "file_count": len(manifest),
            "files": manifest,
        },
        "data_release_notes": {
            "path": str(notes_path),
            "bytes": notes_path.stat().st_size,
            "sha256": sha256_file(notes_path),
        },
        "vector_stores": stats["modules"],
        "lists": stats["lists"],
        "tests": {
            "acceptance_report": test_report,
            "release_data_validator": "scripts/tests/test_validate_release_data.py",
            "release_gate": (
                f"{len(vrd.MODULES)} store + {len(vrd.MODULES)} chunks + "
                f"{len(vrd.LIST_FILES)} 清单 = {vrd.EXPECTED_RELEASE_COUNT} 文件"
            ),
        },
        "public_guard": {
            "ok": True,
            "checked_files": len(tracked),
            "errors": [],
        },
    }


def _archive_existing_sha(archive_dir: Path, version: str) -> str | None:
    existing = archive_dir / AUDIT_NAME.format(version=version)
    if not existing.is_file():
        return None
    try:
        payload = json.loads(existing.read_text(encoding="utf-8"))
        return payload["data_zip"]["sha256"]
    except (OSError, json.JSONDecodeError, KeyError):
        return ""


def _copy_0644(source: Path, target: Path) -> None:
    shutil.copy2(source, target)
    target.chmod(AUDIT_MODE)


def write_audit(audit: dict, dist_dir: Path, archive_dir: Path | None = None) -> Path:
    version = audit["version"]
    name = AUDIT_NAME.format(version=version)
    dist_dir = Path(dist_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)

    if archive_dir is not None:
        archive_dir = Path(archive_dir).expanduser()
        archive_dir.mkdir(parents=True, exist_ok=True)
        existing_sha = _archive_existing_sha(archive_dir, version)
        if existing_sha is not None and existing_sha != audit["data_zip"]["sha256"]:
            raise ReleaseAuditError(
                f"持久目录 {archive_dir} 已存在 v{version} 的审计记录且数据包 SHA 不同"
                f"（{existing_sha[:12] or '无法解析'} → {audit['data_zip']['sha256'][:12]}）。"
                "同一版本不允许混用两个数据包：确认后手动清理该目录再重打。"
            )
        _copy_0644(Path(audit["data_zip"]["path"]), archive_dir / Path(audit["data_zip"]["path"]).name)
        _copy_0644(
            Path(audit["data_release_notes"]["path"]),
            archive_dir / Path(audit["data_release_notes"]["path"]).name,
        )
        audit["persistent"] = {
            "archive_dir": str(archive_dir),
            "zip": {
                "path": str(archive_dir / Path(audit["data_zip"]["path"]).name),
                "sha256": audit["data_zip"]["sha256"],
            },
            "notes": {
                "path": str(archive_dir / Path(audit["data_release_notes"]["path"]).name),
                "sha256": audit["data_release_notes"]["sha256"],
            },
            "audit": {"path": str(archive_dir / name)},
        }

    payload = json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    target = dist_dir / name
    target.write_text(payload, encoding="utf-8")
    target.chmod(AUDIT_MODE)
    if archive_dir is not None:
        archived = archive_dir / name
        archived.write_text(payload, encoding="utf-8")
        archived.chmod(AUDIT_MODE)
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成发布审计清单")
    parser.add_argument("--version", required=True)
    parser.add_argument("--data-date", required=True)
    parser.add_argument("--private-repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--public-clone", required=True)
    parser.add_argument("--dist-dir", required=True)
    parser.add_argument("--archive-dir")
    parser.add_argument("--data-home", default=str(Path.home() / ".pf_agent"))
    parser.add_argument("--test-report", required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    private_repo = Path(args.private_repo).expanduser()
    dist_dir = Path(args.dist_dir).expanduser()
    data_home = Path(args.data_home).expanduser()

    result = vrd.validate(data_home, private_repo)
    if not result.ok:
        print(f"发布数据校验失败（{len(result.errors)} 项）", file=sys.stderr)
        for error in result.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    public_clone = Path(args.public_clone).expanduser()
    try:
        remote_tags = remote_tag_refs(public_clone)
        audit = build_audit(
            version=args.version,
            data_date=args.data_date,
            private_repo=private_repo,
            public_clone=public_clone,
            zip_path=dist_dir / f"pf-agent-data-{args.data_date}.zip",
            notes_path=dist_dir / f"data-release-notes-{args.data_date}.md",
            stats=result.stats,
            test_report=args.test_report,
            remote_tags=remote_tags,
        )
        target = write_audit(
            audit, dist_dir, Path(args.archive_dir).expanduser() if args.archive_dir else None
        )
    except ReleaseAuditError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(f"  审计清单 {target}")
    if "persistent" in audit:
        print(f"  持久目录 {audit['persistent']['archive_dir']}")
    print(f"  数据包 SHA-256 {audit['data_zip']['sha256']}")
    print(f"  公开 commit {audit['public']['short']}（tag {audit['public']['tag']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
