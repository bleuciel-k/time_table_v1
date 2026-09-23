"""DESIGN.md의 디자인 토큰 (색·타입·모서리·간격). Flet 비의존 (P5) — 화면과 exporter가 같은 값을 쓴다.

DESIGN.md는 마케팅 사이트용이라 히어로·섹션 리듬(96px)·가격표 하위 시스템은 앱에 쓰지 않는다.
가져온 것은 토큰 층(색·타입·모서리·간격)과 버튼 한 쌍(먹색 기본 + 흰 테두리 보조)이다.
테마는 라이트 고정. 폰트는 Haas(유료) 대신 앱에 넣은 본고딕 CJK를 쓴다 (한·영·일 한 벌).
"""

from __future__ import annotations

# 앱에 넣은 본문 폰트 (한국어·영어·일본어). 화면(Flet)과 이미지(Pillow)가 같은 파일을 쓴다
FONT_FAMILY = "Noto Sans CJK KR"
FONT_FILE = "fonts/NotoSansCJKkr-Regular.otf"  # assets/ 기준 경로

# ---------------------------------------------------------------- 색

INK = "#181D26"  # 본문 최강 텍스트 = 기본 버튼 배경 (primary)
INK_ACTIVE = "#0D1218"  # 기본 버튼 눌림
BODY = "#333840"  # 일반 텍스트
MUTED = "#41454D"  # 캡션·보조 텍스트
HAIRLINE = "#DDDDDD"  # 1px 테두리·구분선
BORDER_STRONG = "#9297A0"  # 비활성 보조 버튼 테두리
CANVAS = "#FFFFFF"  # 기본 배경
SURFACE_SOFT = "#F8FAFC"  # 빈 셀·연한 카드
SURFACE_STRONG = "#E0E2E6"  # 강조 밴드
ON_PRIMARY = "#FFFFFF"  # 먹색·어두운 면 위의 글자
LINK = "#1B61C9"
FOCUS = "#458FFF"  # 입력 포커스 테두리 (info-border)
DANGER = "#AA2D00"  # 오류·삭제 (signature-coral)
SUCCESS = "#006400"

# ---------------------------------------------------------------- 간격 (4px 배수)

SPACE_XXS = 4
SPACE_XS = 8
SPACE_SM = 12
SPACE_MD = 16
SPACE_LG = 24
SPACE_XL = 32

# ---------------------------------------------------------------- 모서리

RADIUS_XS = 2
RADIUS_SM = 6  # 입력창, 작은 인라인 버튼
RADIUS_MD = 10  # 내용 카드, 시간표 셀
RADIUS_LG = 12  # 기본/보조 버튼, 시트, 대화상자

# ---------------------------------------------------------------- 타입 (크기, 굵기)
# DESIGN.md 원칙: 큰 글자를 굵게 만들지 않는다. 강조는 크기와 색 대비로 한다.

TITLE_LG = (24, 400)  # 화면 제목
TITLE_MD = (20, 400)  # 시트 제목
TITLE_SM = (18, 500)  # 대화상자 제목, 앱 바 제목
LABEL = (16, 500)  # 목록 항목, 구역 이름
BUTTON = (16, 500)
BODY_MD = (14, 400)  # 본문
CAPTION = (14, 500)  # 캡션·메타
SMALL = (12, 400)  # 셀 안 보조 글자처럼 아주 좁은 곳


def rgb(hex_color: str) -> tuple[int, int, int]:
    """`#RRGGBB` → Pillow용 (r, g, b)."""
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    return (*rgb(hex_color), alpha)
