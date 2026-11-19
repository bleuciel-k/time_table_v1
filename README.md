# 대학 시간표 (Timetable)

<p align="center">
  <b>광고 없고 복잡함 없는, 가장 심플하고 감성적인 대학 시간표 앱</b><br>
  Python과 Flet(Flutter)으로 개발된 100% 오프라인 로컬 퍼스트(Local-first) 시간표입니다.
</p>

---

## ✨ 주요 특징

- **🎨 23가지 파스텔 무드 테마 & 16가지 과목 컬러**
  - ColorHunt 기반의 부드럽고 눈이 편안한 23종 배경 테마(기본 화이트, 라벤더, 피치, 민트, 스카이, 버터 등).
  - 컴팩트한 4열 그리드 테마 선택기로 한눈에 마음에 드는 색상을 비교하고 선택할 수 있습니다.
  - WCAG 명암비 알고리즘을 통해 어떤 파스텔 색상을 골라도 텍스트가 또렷하게 표시됩니다.

- **⏱️ 내 학교와 라이프스타일에 맞춘 시간표 커스텀**
  - 1교시 시작 시각, 수업 시간(분 단위), 쉬는 시간(분 단위)을 자유롭게 설정.
  - 점심시간 위치 및 시간 설정(교시 사이에 점심시간 분리선 자동 반영).
  - 5일(월~금) 또는 6일(월~토), 최대 12교시까지 유연하게 확장.
  - 오늘 요일 자동 하이라이트 표시.

- **🖐️ 직관적인 수업 제스처 & 드래그 앤 드롭**
  - 손바닥(수정) 버튼을 누르고 원하는 위치로 드래그하여 수업 이동 및 맞바꾸기(Swap).
  - 모퉁이 조절 핸들을 아래로 끌어당겨 2연강, 3연강 수업을 손쉽게 연장.
  - 실수로 잘못 이동하거나 삭제했을 때 5초간 즉시 복구할 수 있는 '실행 취소(Undo)' 지원.

- **📷 100% 서버리스 & QR 코드 간편 공유**
  - 로그인이나 회원가입이 필요 없습니다. 모든 데이터는 내 스마트폰/PC 기기에만 안전하게 저장됩니다.
  - 친구와 시간표를 공유하거나 기기를 옮길 때 **QR 코드 스캔** 또는 **공유 링크** 하나로 즉시 복원.

- **🖼️ 선명한 고화질 이미지 내보내기**
  - 스마트폰 갤러리/사진 앨범 바로 저장 및 파일 공유 지원.
  - 1x ~ 3x 고해상도 PNG / JPG 이미지 내보내기 지원(잠금화면, 태블릿 배경화면 활용).

- **🍃 가볍고 안전한 제로 광고(Zero Ads)**
  - 배너 광고, 전면 광고, 트래커, 외부 분석 SDK가 전혀 없는 쾌적한 오픈소스 프로젝트입니다.

---

## 📁 프로젝트 구조

```text
time_table_v1/
├── app/
│   ├── model.py            # 시간표 데이터 구조, 불변성 보장, 연강 블록 계산
│   ├── controller.py       # 비즈니스 로직, 검증, 실행 취소(Undo) 히스토리
│   ├── storage.py          # 원자적 파일 I/O 및 로컬 저장소
│   ├── palette.py          # 16색 파스텔 과목 및 23종 배경 테마, 명암비 계산
│   ├── design.py           # 디자인 토큰 (여백, 타이포그래피, 모서리 곡률)
│   ├── exporter.py         # Pillow 기반 고화질 이미지 렌더러
│   ├── qr.py               # 시간표 압축/해제 및 QR 코드 생성
│   └── ui/
│       ├── grid.py         # 인터랙티브 주간 시간표 그리드 (드래그 앤 드롭, 리사이징)
│       ├── settings.py     # 시간표 설정 및 컴팩트 컬러 테마 모달 시트
│       ├── editor.py       # 과목 등록/수정/삭제 바텀 시트
│       ├── export.py       # 이미지 내보내기 및 앨범 저장 시트
│       ├── qr_dialog.py    # QR 코드 내보내기/불러오기 다이얼로그
│       ├── timetables.py   # 다중 시간표 관리 모달
│       └── theme.py        # Flet 공용 UI 컴포넌트
├── assets/                 # 앱 아이콘, 폰트(본고딕), 이미지 에셋
├── docs/                   # GitHub Pages용 웹 뷰어 및 안내 페이지
├── scripts/                # 안드로이드 빌드 및 데이터 백업/복원 유틸리티
├── tests/                  # 236개 단위/UI 스모크 테스트 (pytest)
├── main.py                 # Flet 앱 진입점
├── pyproject.toml          # 프로젝트 의존성 및 Flet/Android 빌드 설정
└── run.sh                  # 원클릭 실행 셸 스크립트
```

---

## 🚀 빠른 시작 (Getting Started)

### 사전 요구사항
- Python 3.12 이상
- (선택) Android 빌드 시: OpenJDK 17, Flutter SDK

### 1. 원클릭 실행 스크립트 (macOS / Linux)
가상환경(.venv) 생성과 패키지 설치가 자동으로 진행됩니다:
```bash
chmod +x run.sh
./run.sh
```

### 2. 수동 설치 및 실행
```bash
# 가상환경 생성 및 활성화
python3.12 -m venv .venv
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 앱 실행 (데스크톱 창)
flet run main.py

# 웹 브라우저 모드로 실행
flet run --web main.py
```

---

## 📱 Android 배포 및 AAB 빌드

Google Play Console 배포를 위한 Android App Bundle(AAB) 빌드 방법입니다.

### 1. 서명 키 설정 (`pyproject.toml`)
`upload-keystore.jks` 서명 키 파일이 프로젝트 루트에 위치해야 하며, `pyproject.toml`에 서명 정보가 등록되어 있습니다:
```toml
[tool.flet.android.signing]
key_store = "upload-keystore.jks"
key_alias = "upload"
```

### 2. AAB 빌드 명령어
Play Console 업로드 시 매 빌드마다 버전 코드(`--build-number`)를 올려서 빌드합니다:
```bash
# 버전 코드 2로 빌드
.venv/bin/flet build aab --build-number 2 --yes

# 버전 코드와 버전 이름을 함께 지정하여 빌드
.venv/bin/flet build aab --build-number 2 --build-version 1.0.1 --yes
```
빌드가 완료되면 `build/aab/timetable.aab` 파일이 생성됩니다.

---

## 🧪 테스트 실행

프로젝트 전반의 안정성을 위해 230개 이상의 단위 테스트 및 UI 스모크 테스트가 포함되어 있습니다:
```bash
.venv/bin/pytest tests/
```

---

## 🔒 개인정보 처리방침 (Privacy Policy)

- 본 앱은 사용자의 어떠한 개인정보나 기기 식별값도 외부 서버로 전송하거나 수집하지 않습니다.
- 모든 시간표 및 설정 정보는 단말기 내부 저장소에만 파일 형태로 보관됩니다.
- QR 코드 공유 기능 또한 외부 서버를 거치지 않고 데이터 자체를 URL 해시 및 QR 이미지로 인코딩하여 오프라인으로 동작합니다.

---

## 📄 라이선스

본 프로젝트는 개인 및 학습 목적으로 제작된 오픈소스 소프트웨어입니다.
사용 중 문의나 개선 제안이 있으시다면 언제든 이슈를 등록해 주세요!
