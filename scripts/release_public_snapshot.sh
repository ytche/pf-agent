#!/usr/bin/env bash
# 公开仓快照发布脚本
#
# 做两件事：
#   1. 代码快照：把私有仓（ytche/pf_agent）当前 HEAD 的**公开内容**快照到公开仓
#      （ytche/pf-agent）的本地克隆，生成单个 commit + tag。
#   2. 数据打包：把本机预构建向量库与清单 JSON 打成 pf-agent-data-<日期>.zip，
#      供公开仓 Releases 的 data-* 数据包发布。
#
# 公开口径（与 0.3.0 起一致）：
#   - 代码快照只含 git 跟踪文件（gitignore 产物/密钥/本机配置天然排除）
#   - docs/ 只保留 DEPLOYMENT.md；设计/交接/评测/待办等过程文档不公开
#   - .kimi-code/ 本地 agent 配置不公开
#   - 数据包：8 个 vector_store_*.json + lists/ 下 6 份清单 JSON
#
# 用法：
#   scripts/release_public_snapshot.sh <版本号>
#   例：scripts/release_public_snapshot.sh 0.3.0
#
# 可选环境变量：
#   PUBLIC_CLONE  公开仓本地克隆路径（默认 /tmp/pf-agent-public）
#   DIST_DIR      数据包与发布说明输出目录（默认 /tmp/pf-agent-dist）
#   DATA_DATE     数据包日期戳（默认当天 YYYYMMDD，决定 data-* tag 名）
#   PF_DATA_HOME  向量库所在目录（默认 ~/.pf_agent）
#
# 脚本只做本地 commit + tag + 数据打包，**不 push、不上传**——推送公开仓与上传
# Release 资产是外发动作，由人确认后按结尾提示的命令手动执行。

set -euo pipefail

PRIVATE_REPO="$(cd "$(dirname "$0")/.." && pwd)"
PUBLIC_CLONE="${PUBLIC_CLONE:-/tmp/pf-agent-public}"
PUBLIC_REMOTE="https://github.com/ytche/pf-agent"
DIST_DIR="${DIST_DIR:-/tmp/pf-agent-dist}"
DATA_DATE="${DATA_DATE:-$(date +%Y%m%d)}"
DATA_TAG="data-${DATA_DATE}"
PF_DATA_HOME="${PF_DATA_HOME:-$HOME/.pf_agent}"

VERSION="${1:?用法: $0 <版本号>，如 0.3.0}"
TAG="v${VERSION}"

cd "$PRIVATE_REPO"

# 前置检查：工作区干净、版本号未在公开仓使用过
if [ -n "$(git status --porcelain)" ]; then
    echo "错误：私有仓工作区不干净，先提交或 stash" >&2
    exit 1
fi

if [ ! -d "$PUBLIC_CLONE/.git" ]; then
    echo "克隆公开仓到 $PUBLIC_CLONE ..."
    git clone -q "$PUBLIC_REMOTE" "$PUBLIC_CLONE"
else
    echo "更新公开仓克隆 $PUBLIC_CLONE ..."
    git -C "$PUBLIC_CLONE" fetch -q origin
fi

# tag 查重必须在 reset/清场之前：否则重复运行会先 reset 丢掉已备好的本地发布
if git -C "$PUBLIC_CLONE" rev-parse -q --verify "refs/tags/${TAG}" >/dev/null \
    || git -C "$PUBLIC_CLONE" ls-remote --tags origin | grep -q "refs/tags/${TAG}$"; then
    echo "错误：公开仓已存在 tag ${TAG}（本地或远程）。若需重打，先删 tag：git -C ${PUBLIC_CLONE} tag -d ${TAG} && git -C ${PUBLIC_CLONE} push origin :refs/tags/${TAG}" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 1/2 数据打包（先做，代码无变化时也能单独拿到新数据包）
# ---------------------------------------------------------------------------
mkdir -p "$DIST_DIR"
DATA_ZIP="$DIST_DIR/pf-agent-data-${DATA_DATE}.zip"
echo "打包数据文件 → $DATA_ZIP ..."
python3 - "$DATA_ZIP" "$PF_DATA_HOME" "$PRIVATE_REPO" <<'PY'
import sys, zipfile, pathlib

zip_path = pathlib.Path(sys.argv[1])
store_home = pathlib.Path(sys.argv[2])
private_repo = pathlib.Path(sys.argv[3])
output = private_repo / "pf_data/phase1/vectorizer/output"

modules = ["classes", "equipment", "feats", "races", "rules", "skills", "spells", "traits"]
lists = [
    "装备/equipment_lists.json",
    "专长/feat_lists.json",
    "种族/race_lists.json",
    "职业/class_tables.json",
    "法术/spell_lists.json",
    "法术/spell_lists_union.json",
]

missing = [str(store_home / f"vector_store_{m}.json") for m in modules
           if not (store_home / f"vector_store_{m}.json").is_file()]
missing += [str(output / rel) for rel in lists if not (output / rel).is_file()]
if missing:
    print("错误：数据文件缺失，先重建产物：", file=sys.stderr)
    for m in missing:
        print("  " + m, file=sys.stderr)
    sys.exit(1)

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for m in modules:
        p = store_home / f"vector_store_{m}.json"
        z.write(p, arcname=p.name)
    for rel in lists:
        p = output / rel
        z.write(p, arcname=f"lists/{p.name}")
print(f"  {zip_path.stat().st_size / 1048576:.1f} MB")
PY

cat > "$DIST_DIR/data-release-notes-${DATA_DATE}.md" <<EOF
## 预构建数据包 ${DATA_DATE}

\`pf-agent-data-${DATA_DATE}.zip\` 内含 8 个 bge-m3（1024 维）预构建向量库与 6 份清单 JSON。

- \`vector_store_*.json\` → 解压到 \`~/.pf_agent/\`（Docker Compose 场景放 \`./data/\`）
- \`lists/\` 下清单 → 按 application.yml 默认路径放到 \`pf_data/phase1/vectorizer/output/<模块>/\`：
  equipment_lists.json→装备、feat_lists.json→专长、race_lists.json→种族、
  class_tables.json→职业、spell_lists.json / spell_lists_union.json→法术

查询侧 embedding 必须与建库模型一致（bge-m3）。规则数据版权见 NOTICE.md。
EOF

# ---------------------------------------------------------------------------
# 2/2 代码快照
# ---------------------------------------------------------------------------
git -C "$PUBLIC_CLONE" reset -q --hard origin/main

echo "快照私有仓 HEAD（$(git rev-parse --short HEAD)）公开文件 → 公开仓 ..."
# 清空公开仓工作区（保留 .git），再按公开口径复制：
#   排除 .kimi-code/ 与 docs/ 内部过程文档，仅保留 docs/DEPLOYMENT.md
find "$PUBLIC_CLONE" -mindepth 1 -maxdepth 1 -not -name .git -exec rm -rf {} +
{
    git ls-files -z -- . ':(exclude).kimi-code' ':(exclude)docs'
    printf 'docs/DEPLOYMENT.md\0'
} | (cd "$PRIVATE_REPO" && tar --null -cf - --files-from=-) \
    | tar -xf - -C "$PUBLIC_CLONE"

cd "$PUBLIC_CLONE"
git add -A
CODE_CHANGED=1
if git diff --cached --quiet; then
    echo "公开仓代码内容无变化，跳过 commit/tag（数据包已生成）"
    CODE_CHANGED=0
else
    git commit -q -m "release: v${VERSION}（快照自私有仓 $(git -C "$PRIVATE_REPO" rev-parse --short HEAD)，详见 CHANGELOG.md）"
    git tag "$TAG"
fi

echo ""
echo "✅ 本地就绪："
if [ "$CODE_CHANGED" = 1 ]; then
    echo "  代码快照 ${PUBLIC_CLONE}（commit + tag ${TAG}）"
fi
echo "  数据包   ${DATA_ZIP}"
echo "  数据说明 ${DIST_DIR}/data-release-notes-${DATA_DATE}.md"
echo ""
echo "核对无误后手动外发："
if [ "$CODE_CHANGED" = 1 ]; then
    echo "  cd ${PUBLIC_CLONE} && git push origin main && git push origin ${TAG}"
fi
echo "  gh release create ${DATA_TAG} --repo ytche/pf-agent \\"
echo "    --title \"预构建数据包 ${DATA_DATE}（v${VERSION}）\" \\"
echo "    --notes-file ${DIST_DIR}/data-release-notes-${DATA_DATE}.md \\"
echo "    ${DATA_ZIP}"
