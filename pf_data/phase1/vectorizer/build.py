"""build.py — 数据产物可复现构建链编排器（方案：数据产物可复现构建链 20260918）

职责（仅调度/指纹/校验，不含任何处理逻辑，不重写 cicd 功能）：
  - 装载 build_manifest.json（单一事实源），装载期校验结构 + 路径存在性（不静默跳过）
  - sha256 内容指纹：inputs glob 展开 + config_deps + 脚本自身 + manifest 自身
  - build_state.json（git 入库，dvc.lock 角色）：build_id + 每 artifact 输入/产物指纹
  - 增量 skip / --force 全量 / status 查询 / check 只校验（非零退出）

用法（cwd=pf_data/phase1）：
  python3 -m vectorizer.build status            # 每个 artifact 的 fresh/stale/missing
  python3 -m vectorizer.build                   # 增量构建（= all）
  python3 -m vectorizer.build all --force       # 从 md 全量复现
  python3 -m vectorizer.build chunks.feat       # 单 artifact
  python3 -m vectorizer.build check             # 只校验不构建（CI 二期挂载点）
"""
import argparse
import fnmatch
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# phase1 根 = vectorizer/build.py → parent×2
PHASE1 = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PHASE1 / "vectorizer" / "build_manifest.json"
STATE_PATH = PHASE1 / "vectorizer" / "state" / "build_state.json"

VIA_CICD = "cicd"
VIA_DIRECT = "direct"


class ManifestError(Exception):
    """manifest 装载期错误（结构非法 / 指向不存在路径）——显式报错，不静默跳过"""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cicd_command(category: str) -> list:
    """via=cicd 步的唯一权威命令（复用四步链，禁止分叉——教训 B）"""
    return ["python3", "-m", "vectorizer.cicd", "verify", "--category", category]


def expand_inputs(patterns: list, root: Path = PHASE1) -> list:
    """inputs glob 展开为去重排序后的相对路径列表（内容指纹的输入集合）

    忽略 basename 为 `.DS_Store` 的文件（任意层级）——macOS 目录元数据，
    不属于源输入；显式 config_deps/script 不受此过滤影响。"""
    files = set()
    for pattern in patterns:
        # Python ≤3.12 的 pathlib 尾部 `**` 只匹配目录（3.13+ 才含文件）；
        # 归一为 `**/*`，保证 3.12（CI）与 3.13+/3.14（本地）展开结果一致
        if pattern.endswith("/**") or pattern == "**":
            pattern = pattern + "/*"
        for p in root.glob(pattern):
            if p.is_file() and p.name != ".DS_Store":
                files.add(p.relative_to(root).as_posix())
    return sorted(files)


def compute_fingerprint(artifact: dict, manifest_hash: str, root: Path = PHASE1) -> str:
    """输入集合 = inputs glob 展开 + config_deps + 脚本自身；外加 manifest 自身哈希。

    纯内容指纹（sha256 文件内容），mtime 变化不改变指纹。
    """
    files = set(expand_inputs(artifact.get("inputs", []), root))
    for dep in artifact.get("config_deps", []):
        p = root / dep
        if not p.is_file():
            raise ManifestError(f"artifact {artifact.get('name')}: config_dep 不存在: {dep}")
        files.add(dep)
    if artifact.get("script"):
        script = artifact["script"]
        if not (root / script).is_file():
            raise ManifestError(f"artifact {artifact.get('name')}: script 不存在: {script}")
        files.add(script)
    lines = [f"manifest:{manifest_hash}"]
    for rel in sorted(files):
        lines.append(f"{rel}:{_sha256_file(root / rel)}")
    return _sha256_text("\n".join(lines))


def _norm_glob(pattern: str) -> str:
    # 与 expand_inputs 相同的尾部 `**` 归一，保证 pattern-vs-output 比对口径一致
    if pattern.endswith("/**") or pattern == "**":
        return pattern + "/*"
    return pattern


def _is_output_covered(pattern: str, outputs_set: set, root: Path = PHASE1) -> bool:
    """input pattern 是否指向其他 artifact 的 outputs——这类 input 由构建顺序保证
    先生成，装载期（裸 checkout，产物尚未构建）不要求其存在。"""
    hits = expand_inputs([pattern], root)
    if hits:
        return any(h in outputs_set for h in hits)
    # 未命中任何文件（裸 checkout）：pattern 本身是否指向 declared outputs
    norm = _norm_glob(pattern)
    return any(fnmatch.fnmatchcase(o, norm) for o in outputs_set)


def _validate_manifest(data: dict, manifest_hash: str, root: Path = PHASE1) -> list:
    """装载期校验：结构 + 与 cicd 装配表一致性 + 指向路径存在性。返回 artifacts 列表。"""
    if not isinstance(data, dict):
        raise ManifestError("manifest 顶层必须为 JSON object")
    for field in ("build_version", "artifacts"):
        if field not in data:
            raise ManifestError(f"manifest 缺少必填字段: {field}")
    artifacts = data["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise ManifestError("manifest artifacts 必须为非空列表")

    # via=cicd 与装配表一致性：类目必须已注册，输出目录必须同源（防手工抄错）
    from vectorizer.cicd.verify import CATEGORIES

    seen = set()
    all_outputs = {o for art in artifacts for o in art.get("outputs", [])}
    for art in artifacts:
        name = art.get("name")
        if not name:
            raise ManifestError("artifact 缺少 name")
        if name in seen:
            raise ManifestError(f"artifact 重名: {name}")
        seen.add(name)
        via = art.get("via")
        if via not in (VIA_CICD, VIA_DIRECT):
            raise ManifestError(f"{name}: via 必须为 {VIA_CICD}/{VIA_DIRECT}，实际 {via!r}")
        if not art.get("outputs"):
            raise ManifestError(f"{name}: outputs 为空")
        if via == VIA_CICD:
            category = art.get("category")
            if category not in CATEGORIES:
                raise ManifestError(
                    f"{name}: category {category!r} 不在 cicd 装配表（已注册: {list(CATEGORIES)}）")
            out_dir = CATEGORIES[category]["output_dir"]
            if not any(o.startswith(out_dir + "/") for o in art["outputs"]):
                raise ManifestError(f"{name}: outputs 与装配表 output_dir {out_dir} 不一致")
        else:
            if not art.get("command"):
                raise ManifestError(f"{name}: via=direct 必须提供 command")
        # inputs glob 必须命中文件（指向不存在路径 → 装载期报错）；
        # 但「指向其他 artifact outputs」的 input 是构建期产物，装载期（裸 checkout）豁免。
        # 每个 pattern 独立判定：未命中且非产物 input → 报错（防止豁免掩盖真实缺失）
        other_outputs = all_outputs - set(art["outputs"])
        for pattern in art.get("inputs", []):
            if not expand_inputs([pattern], root) and not _is_output_covered(
                    pattern, other_outputs, root):
                raise ManifestError(
                    f"{name}: inputs glob 未命中任何文件: {art.get('inputs')}")
        # config_deps / script 存在性（compute_fingerprint 也会查，装载期先显形）
        for dep in art.get("config_deps", []):
            if not (root / dep).is_file():
                raise ManifestError(f"{name}: config_dep 不存在: {dep}")
        if art.get("script") and not (root / art["script"]).is_file():
            raise ManifestError(f"{name}: script 不存在: {art['script']}")
    # 拓扑序校验：inputs 引用其他 artifact 的 outputs → 被依赖者必须先出现
    for i, art in enumerate(artifacts):
        art_inputs = set(expand_inputs(art.get("inputs", []), root))
        for other in artifacts[i + 1:]:
            shared = art_inputs & set(other.get("outputs", []))
            if shared:
                raise ManifestError(
                    f"拓扑序违反: {art['name']} 的 inputs 依赖 {other['name']} 的 outputs "
                    f"（{sorted(shared)}），但被依赖者声明在前者之后")
    return artifacts


def load_manifest(path: Path = MANIFEST_PATH, root: Path = PHASE1):
    """装载 manifest + 装载期校验。返回 (data, artifacts, manifest_hash)。"""
    if not path.is_file():
        raise ManifestError(f"manifest 不存在: {path}")
    manifest_hash = _sha256_file(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ManifestError(f"manifest JSON 解析失败: {e}")
    artifacts = _validate_manifest(data, manifest_hash, root)
    return data, artifacts, manifest_hash


def artifact_command(artifact: dict) -> list:
    """解析 artifact 的执行命令：via=cicd 派生（与装配表一致），via=direct 取 command 字段"""
    if artifact["via"] == VIA_CICD:
        return cicd_command(artifact["category"])
    return artifact["command"]


def load_state(path: Path = STATE_PATH) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"❌ build_state.json 损坏（JSON 解析失败）: {e}——请重跑对应构建步或恢复 git 版本")


def write_state(state: dict, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _output_hashes(artifact: dict, root: Path = PHASE1) -> dict:
    """产物存在性 + 内容 sha256（state 与产物漂移检测依据）"""
    result = {}
    for out in artifact["outputs"]:
        p = root / out
        result[out] = _sha256_file(p) if p.is_file() else None
    return result


def _schema_version(artifact: dict, root: Path = PHASE1):
    """读取产物 schema version 实际值；version_field 为 null（jsonl 闸口登记）返回 None"""
    schema = artifact.get("schema") or {}
    field = schema.get("version_field")
    if not field:
        return None
    p = root / schema["file"]
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "<损坏:非JSON>"
    return data.get(field, "<缺失>")


def artifact_status(artifact: dict, state: dict, manifest_hash: str, root: Path = PHASE1) -> dict:
    """fresh / stale / missing 判定（指纹比对，非 mtime）"""
    name = artifact["name"]
    entry = (state.get("artifacts") or {}).get(name)
    if entry is None:
        return {"status": "missing", "reason": "state 无记录"}
    outputs = _output_hashes(artifact, root)
    missing_outs = [o for o, h in outputs.items() if h is None]
    if missing_outs:
        return {"status": "missing", "reason": f"产物缺失: {missing_outs}"}
    drifted = [o for o in artifact["outputs"] if outputs[o] != entry.get("outputs", {}).get(o)]
    if drifted:
        return {"status": "stale", "reason": f"产物内容与 state 指纹不符（被改/重建过）: {drifted}"}
    fp = compute_fingerprint(artifact, manifest_hash, root)
    if fp != entry.get("fingerprint"):
        return {"status": "stale", "reason": "输入指纹变化（源/配置/脚本/manifest 有改动）"}
    return {"status": "fresh", "reason": ""}


def cmd_status(artifacts: list, state: dict, manifest_hash: str) -> int:
    print(f"{'artifact':<20} {'kind':<18} {'via':<7} {'status':<8} schema")
    print("-" * 72)
    for art in artifacts:
        st = artifact_status(art, state, manifest_hash)
        schema = art.get("schema") or {}
        if schema.get("version_field"):
            actual = _schema_version(art)
            expected = schema.get("expected")
            schema_s = f"{schema['file']}:{schema['version_field']}={actual} (期望 {expected})"
            if actual != expected:
                st = {"status": "stale", "reason": st["reason"] + f" schema 版本不符: {actual} != {expected}"}
        else:
            schema_s = "(jsonl 闸口登记)"
        print(f"{art['name']:<20} {art['kind']:<18} {art['via']:<7} {st['status']:<8} {schema_s}")
        if st["reason"]:
            print(f"    └─ {st['reason']}")
    build_id = state.get("build_id")
    print("-" * 72)
    print(f"build_id: {build_id or '(尚无 state——从未构建)'}")
    return 0


def cmd_check(artifacts: list, state: dict, manifest_hash: str, data: dict) -> int:
    """只校验不构建：schema version 断言 + 产物存在 + 指纹一致。任一失败非零退出。"""
    problems = []
    if state.get("build_version") != data.get("build_version"):
        problems.append(f"state build_version {state.get('build_version')!r} != manifest {data.get('build_version')!r}")
    for art in artifacts:
        name = art["name"]
        entry = (state.get("artifacts") or {}).get(name)
        if entry is None:
            problems.append(f"{name}: state 无记录（未构建）")
            continue
        for out in art["outputs"]:
            if not (PHASE1 / out).is_file():
                problems.append(f"{name}: 产物缺失 {out}")
        drift = []
        for out, h in _output_hashes(art).items():
            if h is not None and h != entry.get("outputs", {}).get(out):
                drift.append(out)
        if drift:
            problems.append(f"{name}: 产物与 state 指纹漂移: {drift}")
        try:
            fp = compute_fingerprint(art, manifest_hash)
        except ManifestError as e:
            problems.append(str(e))
            continue
        if fp != entry.get("fingerprint"):
            problems.append(f"{name}: 输入指纹与 state 不符（源/配置/脚本/manifest 已改动，需重建）")
        schema = art.get("schema") or {}
        if schema.get("version_field"):
            actual = _schema_version(art)
            if actual != schema.get("expected"):
                problems.append(
                    f"{name}: schema 版本断言失败 {schema['file']}: "
                    f"version_field {schema['version_field']} 实际 {actual!r} 期望 {schema['expected']!r}")
    if problems:
        print("❌ check 失败：")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"✅ check 通过：{len(artifacts)} 个 artifact 产物存在、指纹一致、schema version 匹配")
    return 0


def cmd_build(target: str, artifacts: list, state: dict, manifest_hash: str,
              data: dict, force: bool) -> int:
    if target == "all":
        todo = artifacts
    else:
        todo = [a for a in artifacts if a["name"] == target]
        if not todo:
            sys.exit(f"❌ 未知 artifact {target!r}，已注册: {[a['name'] for a in artifacts]}")
    total, done, skipped = len(todo), 0, 0
    new_state = dict(state)
    new_state.setdefault("artifacts", {})
    for art in todo:
        name = art["name"]
        st = artifact_status(art, new_state, manifest_hash)
        if not force and st["status"] == "fresh":
            print(f"[skip] {name}（指纹未变，产物存在）")
            skipped += 1
            continue
        if force:
            print(f"[build] {name}（--force 全量）")
        else:
            print(f"[build] {name}（{st['status']}: {st['reason']}）")
        r = subprocess.run(artifact_command(art), cwd=PHASE1)
        if r.returncode != 0:
            print(f"\n❌ 失败步: {name}（退出码 {r.returncode}）——已完成 {done}/{total}，"
                  f"跳过 {skipped}；失败步不产生 state 更新，验证链终止", file=sys.stderr)
            return r.returncode or 1
        new_state["artifacts"][name] = {
            "fingerprint": compute_fingerprint(art, manifest_hash),
            "outputs": _output_hashes(art),
        }
        new_state["build_version"] = data["build_version"]
        agg = _sha256_text("\n".join(
            f"{n}:{e['fingerprint']}" for n, e in sorted(new_state["artifacts"].items())))
        new_state["build_id"] = f"{agg[:16]}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        new_state["generated_at"] = datetime.now(timezone.utc).isoformat()
        write_state(new_state)
        print(f"[ok] {name}（state 已更新）")
        done += 1
    print(f"\n✅ 构建完成：执行 {done}，skip {skipped}，共 {total}")
    return 0


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="数据产物可复现构建链（调度/指纹/校验，不含处理逻辑）")
    parser.add_argument("target", nargs="?", default="all",
                        help="all | artifact 名 | status | check")
    parser.add_argument("--force", action="store_true", help="全量重建（无视指纹）")
    args = parser.parse_args(argv)

    try:
        data, artifacts, manifest_hash = load_manifest()
    except ManifestError as e:
        sys.exit(f"❌ manifest 装载失败: {e}")

    state = load_state()
    if args.target == "status":
        sys.exit(cmd_status(artifacts, state, manifest_hash))
    if args.target == "check":
        sys.exit(cmd_check(artifacts, state, manifest_hash, data))
    sys.exit(cmd_build(args.target, artifacts, state, manifest_hash, data, args.force))


if __name__ == "__main__":
    main()
