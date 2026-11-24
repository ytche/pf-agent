#!/usr/bin/env python3
"""公开快照内容门禁。

发布脚本在公开仓提交前调用：命中实际密钥、本地 agent 配置、过程文档、构建垃圾
或私钥/令牌内容即非零退出，阻止提交与打 tag。只做只读扫描。

用法：
    python3 scripts/release_public_guard.py <公开快照目录>
"""

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

# 只允许 DEPLOYMENT.md 进入公开 docs/
ALLOWED_DOCS = frozenset({"docs/DEPLOYMENT.md"})

# 目录级构建垃圾 / 本地配置
FORBIDDEN_DIRS = {
    ".kimi-code": "本地 agent 配置",
    "node_modules": "构建垃圾",
    "target": "构建垃圾",
    "__pycache__": "构建垃圾",
    ".pytest_cache": "构建垃圾",
    "playwright-report": "测试输出",
    "test-results": "测试输出",
    "dist": "构建垃圾",
    "coverage": "覆盖率产物",
    ".venv": "本地虚拟环境",
}

FORBIDDEN_SUFFIXES = {
    ".pem": "密钥类文件",
    ".key": "密钥类文件",
    ".p12": "密钥类文件",
    ".pfx": "密钥类文件",
    ".jks": "密钥类文件",
    ".keystore": "密钥类文件",
}

FORBIDDEN_NAMES = {
    "id_rsa": "SSH 私钥",
    "id_dsa": "SSH 私钥",
    "id_ecdsa": "SSH 私钥",
    "id_ed25519": "SSH 私钥",
    ".netrc": "凭据文件",
}

CONTENT_PATTERNS = (
    (re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"), "私钥"),
    (re.compile(rb"AKIA[0-9A-Z]{16}"), "AWS 访问密钥"),
    (re.compile(rb"ghp_[A-Za-z0-9]{36}"), "GitHub 个人访问令牌"),
    (re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"), "GitHub 细粒度令牌"),
    (re.compile(rb"sk-[A-Za-z0-9]{32,}"), "API 令牌"),
)

# 超过该大小的文件不做内容扫描（数据产物无密钥场景），只做路径检查
MAX_CONTENT_BYTES = 4 * 1024 * 1024
BINARY_PROBE_BYTES = 8192


def _path_errors(rel: str) -> list[str]:
    path = PurePosixPath(rel)
    parts = path.parts
    name = path.name
    errors = []

    if name == ".DS_Store":
        errors.append(f"包含 macOS 垃圾文件 .DS_Store：{rel}")
    for part in parts[:-1]:
        if part in FORBIDDEN_DIRS:
            errors.append(f"包含{FORBIDDEN_DIRS[part]}目录 {part}：{rel}")
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        errors.append(f"包含实际密钥文件（应排除，模板 .env.example 除外）：{rel}")
    if parts and parts[0] == "docs" and rel not in ALLOWED_DOCS:
        errors.append(f"docs/ 只允许 DEPLOYMENT.md，发现过程文档：{rel}")
    suffix = path.suffix.lower()
    if suffix in FORBIDDEN_SUFFIXES:
        errors.append(f"发现{FORBIDDEN_SUFFIXES[suffix]}：{rel}")
    if name in FORBIDDEN_NAMES:
        errors.append(f"发现{FORBIDDEN_NAMES[name]}：{rel}")
    return errors


def _content_errors(path: Path, rel: str) -> list[str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [f"无法读取 {rel} 做内容检查：{exc}"]
    if len(raw) > MAX_CONTENT_BYTES:
        return []
    if b"\x00" in raw[:BINARY_PROBE_BYTES]:
        return []
    errors = []
    for pattern, label in CONTENT_PATTERNS:
        match = pattern.search(raw)
        if match:
            errors.append(f"疑似{label}内容：{rel}（{match.group(0)[:40].decode('ascii', 'replace')}…）")
    return errors


def scan(root: Path, tracked: list[str]) -> list[str]:
    root = Path(root)
    errors = []
    for rel in tracked:
        errors.extend(_path_errors(rel))
        errors.extend(_content_errors(root / rel, rel))
    return errors


def tracked_files(root: Path) -> list[str]:
    # -z 关闭路径转义，中文/空格路径保持原样
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [p for p in out.split("\0") if p]


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("用法：release_public_guard.py <公开快照目录>", file=sys.stderr)
        return 2
    root = Path(argv[0]).expanduser()
    if not root.is_dir():
        print(f"错误：目录不存在 {root}", file=sys.stderr)
        return 2

    files = tracked_files(root)
    errors = scan(root, files)
    if errors:
        print(f"公开内容门禁未通过（{len(errors)} 项）：", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"公开内容门禁通过：{len(files)} 个跟踪文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
