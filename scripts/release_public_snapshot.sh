#!/usr/bin/env bash
# 公开仓快照发布脚本
#
# 做两件事：
#   1. 代码快照：把私有仓（ytche/pf_agent）当前 HEAD 的**公开内容**快照到公开仓
#      （ytche/pf-agent）的本地克隆，生成单个 commit + tag。
#   2. 数据打包：把本机预构建向量库、chunks 与清单 JSON 打成 pf-agent-data-<日期>.zip，
#      供公开仓 Releases 的 data-* 数据包发布。
#
# 公开口径（与 0.3.0 起一致）：
#   - 代码快照只含 git 跟踪文件（gitignore 产物/密钥/本机配置天然排除）
#   - docs/ 只保留 DEPLOYMENT.md；设计/交接/评测/待办等过程文档不公开
#   - .kimi-code/ 本地 agent 配置不公开
#   - `.env.example` 是无密钥公开模板，保留；只排除实际 `.env` 与带值密钥文件
#   - 数据包：8 个 vector_store_*.json + output/ 下 8 份 chunks + 7 份清单 JSON
#   - 打包前先跑 scripts/validate_release_data.py：向量库与 chunks/清单不一致即停止；
#     文件清单、文件数与 zip 写入都由该校验器的 collect_release_files() 统一产生
#   - 公开仓提交前跑 scripts/release_public_guard.py：实际密钥、.kimi-code/、过程文档、
#     .DS_Store、构建垃圾、私钥/令牌内容命中即硬失败
#   - 提交后由 scripts/release_audit.py 生成审计清单，并把 zip/说明/审计转存到
#     RELEASE_ARCHIVE_DIR（默认 $HOME/.pf_agent_release/v<版本>），权限 0644
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
#   RELEASE_ARCHIVE_DIR  发布产物持久目录（默认 $HOME/.pf_agent_release/v<版本>）
#   TEST_REPORT   审计清单里记录的验收报告路径
#                 （默认 docs/test-reports/测试报告_v<版本>候选版发布验收_<日期>.md）
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
ARCHIVE_DIR="${RELEASE_ARCHIVE_DIR:-$HOME/.pf_agent_release/v${VERSION}}"
TEST_REPORT="${TEST_REPORT:-docs/test-reports/测试报告_v${VERSION}候选版发布验收_${DATA_DATE}.md}"

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
echo "校验并打包数据文件 → $DATA_ZIP ..."
if ! python3 "$PRIVATE_REPO/scripts/validate_release_data.py" \
    --package "$DATA_ZIP" "$PF_DATA_HOME" "$PRIVATE_REPO"; then
    echo "错误：发布数据校验或打包失败，未更新 $DATA_ZIP" >&2
    exit 1
fi

cat > "$DIST_DIR/data-release-notes-${DATA_DATE}.md" <<EOF
## 预构建数据包 ${DATA_DATE}

\`pf-agent-data-${DATA_DATE}.zip\` 内含 23 个文件：8 个 bge-m3（1024 维）预构建向量库、8 份 chunks.jsonl 与 7 份清单 JSON。

- Docker Compose：把整个 zip 解压到仓库的 \`./data/\`，得到 \`vector_store_*.json\` 与 \`output/<模块>/\`，Compose 会自动挂载两处数据目录。
- 本地运行：\`vector_store_*.json\` → \`~/.pf_agent/\`；\`output/\` 下全部模块目录 → 仓库的 \`pf_data/phase1/vectorizer/output/\`。

chunks 是条目名解析与引用链的运行时数据源，清单用于清单/表格直查；两者都不能省略。查询侧 embedding 必须与建库模型一致（bge-m3）。规则数据版权见 NOTICE.md。
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

echo "公开内容门禁 → $PUBLIC_CLONE ..."
if ! python3 "$PRIVATE_REPO/scripts/release_public_guard.py" "$PUBLIC_CLONE"; then
    echo "错误：公开内容门禁未通过，未提交、未打 tag（数据包 ${DATA_ZIP} 已生成）" >&2
    exit 1
fi

CODE_CHANGED=1
if git diff --cached --quiet; then
    echo "公开仓代码内容无变化，跳过 commit/tag（数据包已生成）"
    CODE_CHANGED=0
else
    git commit -q -m "release: v${VERSION}（快照自私有仓 $(git -C "$PRIVATE_REPO" rev-parse --short HEAD)，详见 CHANGELOG.md）"
    git tag "$TAG"
fi

# ---------------------------------------------------------------------------
# 审计清单：记录本次事实并转存到持久目录
# ---------------------------------------------------------------------------
echo "生成审计清单 → ${ARCHIVE_DIR} ..."
python3 "$PRIVATE_REPO/scripts/release_audit.py" \
    --version "$VERSION" \
    --data-date "$DATA_DATE" \
    --private-repo "$PRIVATE_REPO" \
    --public-clone "$PUBLIC_CLONE" \
    --dist-dir "$DIST_DIR" \
    --archive-dir "$ARCHIVE_DIR" \
    --data-home "$PF_DATA_HOME" \
    --test-report "$TEST_REPORT"

echo ""
echo "✅ 本地就绪："
if [ "$CODE_CHANGED" = 1 ]; then
    echo "  代码快照 ${PUBLIC_CLONE}（commit + tag ${TAG}）"
fi
echo "  数据包   ${DATA_ZIP}"
echo "  数据说明 ${DIST_DIR}/data-release-notes-${DATA_DATE}.md"
echo "  审计清单 ${DIST_DIR}/release-audit-v${VERSION}.json"
echo "  持久目录 ${ARCHIVE_DIR}（zip / 说明 / 审计，权限 0644）"
echo ""
echo "核对无误后手动外发："
if [ "$CODE_CHANGED" = 1 ]; then
    echo "  cd ${PUBLIC_CLONE} && git push origin main && git push origin ${TAG}"
fi
echo "  gh release create ${DATA_TAG} --repo ytche/pf-agent \\"
echo "    --title \"预构建数据包 ${DATA_DATE}（v${VERSION}）\" \\"
echo "    --notes-file ${DIST_DIR}/data-release-notes-${DATA_DATE}.md \\"
echo "    ${DATA_ZIP}"
