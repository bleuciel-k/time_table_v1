#!/usr/bin/env bash
# ==============================================================================
# 시간표 앱 실행 및 개발 환경 셋업 스크립트
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"

# 1. 백업 복원 옵션 확인
if [[ "${1:-}" == "--restore" ]]; then
    if [[ -z "${2:-}" ]]; then
        echo "❌ 복원할 백업 파일 경로를 입력해주세요."
        echo "예: ./run.sh --restore ~/Downloads/my_backup.json"
        exit 1
    fi
    python3 scripts/restore_backup.py "$2"
    shift 2 || true
fi

# 2. config.py 확인
if [[ ! -f "config.py" ]]; then
    echo "⚠️ config.py가 없습니다. config.example.py를 복사합니다."
    cp config.example.py config.py
    echo "💡 config.py에 Firebase API Key 및 RTDB URL을 입력하면 동기화 기능을 사용할 수 있습니다."
fi

# 3. 파이썬 및 가상환경(.venv) 설정
PYTHON_BIN="python3"
if command -v python3.12 &>/dev/null; then
    PYTHON_BIN="python3.12"
elif command -v python3.13 &>/dev/null; then
    PYTHON_BIN="python3.13"
fi

if [[ ! -d ".venv" ]]; then
    echo "📦 .venv 가상환경이 없습니다. 새로 생성합니다 ($PYTHON_BIN)..."
    "$PYTHON_BIN" -m venv .venv
    echo "⬇️ 의존성 패키지를 설치합니다 (requirements.txt)..."
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

# 4. 가상환경 활성화
source .venv/bin/activate

# 5. 백업 데이터 위치 점검
if [[ ! -f ".flet/storage/data/data.json" && ! -f ".data/data.json" ]]; then
    echo "ℹ️ 로컬 시간표 데이터가 없습니다. (기본 빈 시간표로 시작)"
    echo "💡 다운로드받은 백업 JSON 파일이 있다면 다음 명령어로 적용할 수 있습니다:"
    echo "   python3 scripts/restore_backup.py <백업파일.json>"
fi

echo "🚀 시간표 앱을 실행합니다..."
flet run main.py "$@"
