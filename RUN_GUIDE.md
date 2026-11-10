# 시간표 앱 (Timetable) 구동 및 백업 복원 가이드

## 1. 개요 및 요구사항
- **Python**: 3.12 이상 권장
- **핵심 라이브러리**: `flet==1.0.0`, `pillow==12.2.0`, `httpx==0.28.1`, `pytest`

---

## 2. 다운로드받은 백업 파일 적용 방법

백업 파일(예: `data.json`, `backup.json`, 또는 Firebase RTDB 내보내기 JSON)을 다운로드받으셨다면, 앱이 바로 인식하도록 저장소 폴더에 복원해야 합니다.

### 방법 A. 복원 스크립트 사용 (가장 편리함)
```bash
# 1) 백업 파일 경로를 직접 지정하여 복원
python3 scripts/restore_backup.py ~/Downloads/다운로드받은백업파일.json

# 2) 또는 파일명을 주지 않으면 Downloads 폴더나 작업 디렉토리에서 자동으로 탐색합니다
python3 scripts/restore_backup.py
```

### 방법 B. 수동으로 파일 배치하기
다운로드받은 백업 파일명을 `data.json`으로 변경한 후, 아래 두 위치 중 사용하는 환경의 폴더에 복사합니다:
- **Flet 실행 기본 저장소**: `.flet/storage/data/data.json`
- **일반 Python 실행 폴백 위치**: `.data/data.json`

*(기존 파일이 있을 경우 자동으로 `data.json.bak`으로 백업됩니다)*

---

## 3. 앱 실행 방법

### 방법 A. 원클릭 실행 스크립트 (`run.sh`)
가상환경(.venv) 생성, 의존성 설치, 설정 확인 후 Flet 앱을 자동으로 실행합니다:
```bash
# 일반 실행
./run.sh

# 백업 복원과 동시에 실행
./run.sh --restore ~/Downloads/백업파일.json
```

### 방법 B. 수동 가상환경 구성 및 실행
```bash
# 1. 가상환경 생성 및 활성화
python3.12 -m venv .venv
source .venv/bin/activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 앱 실행
flet run main.py
```

---

## 4. Android APK 빌드 및 기기 실행 (선택사항)
안드로이드 스마트폰 또는 에뮬레이터가 연결되어 있는 경우:
```bash
# 빌드 및 기기에 즉시 설치·실행
bash scripts/run_android.sh

# 이미 빌드된 APK만 재설치·실행
bash scripts/run_android.sh --no-build
```

---

## 5. 설정 및 Firebase 계정 동기화 (선택사항)
- `config.py`에 Firebase Web API Key 및 Realtime Database URL이 설정되어 있습니다.
- 앱 우측 상단 메뉴(⋮) -> [계정]에서 Firebase Auth 계정으로 로그인하시면 기기 간 실시간 LWW 동기화가 동작합니다.
