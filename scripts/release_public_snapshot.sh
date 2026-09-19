#!/usr/bin/env bash
# 公开仓快照发布脚本
#
# 把私有仓（ytche/pf_agent）当前 HEAD 的全部 git 跟踪文件快照到公开仓
# （ytche/pf-agent）的本地克隆，生成单个 commit + tag。
#
# 口径与 0.1.0 基线一致：单 commit 干净历史、只含跟踪文件（gitignore 产物/
# 密钥/本机配置天然排除）。
#
# 用法：
#   scripts/release_public_snapshot.sh <版本号>
#   例：scripts/release_public_snapshot.sh 0.2.0
#
# 脚本只做本地 commit + tag，**不 push**——推送公开仓是外发动作，由人确认后
# 在提示的目录里手动 git push && git push --tags。

set -euo pipefail

PRIVATE_REPO="$(cd "$(dirname "$0")/.." && pwd)"
PUBLIC_CLONE="${PUBLIC_CLONE:-/tmp/pf-agent-public}"
PUBLIC_REMOTE="https://github.com/ytche/pf-agent"

VERSION="${1:?用法: $0 <版本号>，如 0.2.0}"
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
    git -C "$PUBLIC_CLONE" reset -q --hard origin/main
fi

if git -C "$PUBLIC_CLONE" rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    echo "错误：公开仓已存在 tag $TAG" >&2
    exit 1
fi

echo "快照私有仓 HEAD（$(git rev-parse --short HEAD)）跟踪文件 → 公开仓 ..."
# 清空公开仓工作区（保留 .git），再按跟踪文件清单复制
find "$PUBLIC_CLONE" -mindepth 1 -maxdepth 1 -not -name .git -exec rm -rf {} +
git ls-files -z | (cd "$PRIVATE_REPO" && tar --null -cf - --files-from=-) \
    | tar -xf - -C "$PUBLIC_CLONE"

cd "$PUBLIC_CLONE"
git add -A
if git diff --cached --quiet; then
    echo "公开仓内容无变化，无需发布" >&2
    exit 1
fi

git commit -q -m "release: v${VERSION}（快照自私有仓 $(git -C "$PRIVATE_REPO" rev-parse --short HEAD)，详见 CHANGELOG.md）"
git tag "$TAG"

echo ""
echo "✅ 本地就绪：${PUBLIC_CLONE}（commit + tag ${TAG}）"
echo "核对无误后手动外发："
echo "  cd ${PUBLIC_CLONE} && git push origin main && git push origin ${TAG}"
