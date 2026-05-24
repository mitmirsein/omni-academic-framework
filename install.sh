#!/usr/bin/env bash
# Omni-Academic Framework 원클릭 설치 부트스트랩.
#
# 사용:
#   curl -fsSL https://raw.githubusercontent.com/mitmirsein/omni-academic-framework/main/install.sh | bash
#   # 또는 클론한 저장소 루트에서:
#   ./install.sh
#
# 하는 일: uv 존재 확인(없으면 안내) → `uv tool install`로 격리 환경에 `omni`
# 명령을 전역 등록. 기본 렌즈는 패키지에 동봉되어 어느 디렉터리에서 실행해도
# 인식된다. API 키는 설치 후 `omni --setup`으로 설정한다.
set -euo pipefail

REPO_URL="${OMNI_REPO_URL:-https://github.com/mitmirsein/omni-academic-framework.git}"

echo "🌐 Omni-Academic Framework 설치"

if ! command -v uv >/dev/null 2>&1; then
  echo "❌ uv가 설치되어 있지 않습니다."
  echo "   먼저 설치하세요: https://docs.astral.sh/uv/getting-started/installation/"
  echo "   (예) curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

# 로컬 저장소 루트에서 실행되면 그곳을, 아니면 git 원격을 소스로 사용.
if [ -f "pyproject.toml" ] && grep -q "omni-academic-framework" pyproject.toml 2>/dev/null; then
  echo "📦 로컬 소스에서 설치: $(pwd)"
  uv tool install --force .
else
  echo "📦 원격에서 설치: $REPO_URL"
  uv tool install --force "git+$REPO_URL"
fi

echo ""
echo "✅ 설치 완료. 다음을 실행해 보세요:"
echo "   omni --status        # 진단/환경 점검"
echo "   omni --setup         # API 키 대화형 설정(.env)"
echo "   omni --list-lenses   # 동봉 렌즈 확인"
