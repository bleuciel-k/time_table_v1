"""16색 프리셋과 글자색 계산 (spec 2.5). Flet 비의존 (P5)."""

# 부드러운 파스텔 16색. 모두 밝아서 글자는 먹색으로 그려진다 (text_color가 자동 결정)
PALETTE: dict[str, str] = {
    "red": "#F5A9A3",
    "pink": "#F4AFC7",
    "purple": "#D5B8E8",
    "indigo": "#B6BEEA",
    "blue": "#A7CDEF",
    "sky": "#A6DCF2",
    "cyan": "#A3E0E4",
    "slate": "#C1CAD2",
    "teal": "#A2D9CB",
    "green": "#B5DFAF",
    "lime": "#D5E8A4",
    "yellow": "#F3E7A1",
    "amber": "#F7DCA2",
    "orange": "#F8C9A4",
    "brown": "#D9BDAA",
    "gray": "#D9DDE1",
}

# 배경색 (F9). 16색 셀과 먹색 글자가 모두 잘 보이도록 아주 연한 색만 둔다 (DESIGN.md)
BACKGROUNDS: dict[str, str] = {
    # 화이트 & 뉴트럴
    "white": "#FFFFFF",
    "gray": "#F4F5F7",
    "ash": "#ECEEF0",
    "cool_gray": "#ECEFF2",
    "warm_gray": "#F3EFEB",
    # 베이지 & 옐로우
    "ivory": "#FBF6EA",
    "sand": "#F7F1E8",
    "oatmeal": "#F5EFEB",
    "butter": "#FFFBE8",
    "apricot": "#FDEBD9",
    "peach": "#FFF0E6",
    # 핑크 & 코랄 & 로즈
    "blush": "#FCF0F1",
    "coral": "#FEECE8",
    "rose": "#FCE8EE",
    # 퍼플 & 라벤더
    "lilac": "#F7EDF8",
    "lavender": "#F3F0FA",
    # 블루 & 쿨
    "sky": "#EEF3FB",
    "ice": "#E8F4F8",
    "ocean": "#E6EFF8",
    # 그린 & 네이처
    "mint": "#EDF7F1",
    "sage": "#EDF4ED",
    "matcha": "#EBF3E8",
    "olive": "#EBF0E4",
}

BACKGROUND_LABELS: dict[str, str] = {
    "white": "흰색",
    "gray": "회색",
    "ash": "애쉬",
    "cool_gray": "쿨그레이",
    "warm_gray": "웜그레이",
    "ivory": "아이보리",
    "sand": "모래",
    "oatmeal": "오트밀",
    "butter": "버터",
    "apricot": "살구",
    "peach": "피치",
    "blush": "연분홍",
    "coral": "코랄",
    "rose": "로즈",
    "lilac": "라일락",
    "lavender": "라벤더",
    "sky": "하늘",
    "ice": "아이스",
    "ocean": "바다",
    "mint": "민트",
    "sage": "세이지",
    "matcha": "말차",
    "olive": "올리브",
}

DEFAULT_BACKGROUND = "white"
DEFAULT_COLOR = "blue"
BLACK = "#000000"
WHITE = "#FFFFFF"


def background_hex(key: str) -> str:
    """배경색 key → hex. 모르는 key는 기본값(흰색)으로 본다 (spec 2.7)."""
    return BACKGROUNDS.get(key, BACKGROUNDS[DEFAULT_BACKGROUND])


def resolve_hex(color: str) -> str:
    """팔레트 key 또는 `#RRGGBB`를 hex로 변환한다."""
    if color in PALETTE:
        return PALETTE[color]
    if len(color) == 7 and color.startswith("#"):
        int(color[1:], 16)  # 형식 검사
        return color.upper()
    raise ValueError(f"알 수 없는 색상: {color!r}")


def relative_luminance(color: str) -> float:
    """WCAG 2.x 상대 휘도."""
    h = resolve_hex(color)
    channels = []
    for i in (1, 3, 5):
        c = int(h[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_color(background: str) -> str:
    """배경과의 대비가 더 큰 쪽(흑/백)을 글자색으로 고른다."""
    if contrast_ratio(background, BLACK) >= contrast_ratio(background, WHITE):
        return BLACK
    return WHITE


def lighten_hex(color: str, amount: float = 0.12) -> str:
    """hex 색상을 밝게 띄워 부드러운 하이라이트 틴트를 만든다."""
    h = resolve_hex(color).lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = min(255, int(r + (255 - r) * amount))
    g = min(255, int(g + (255 - g) * amount))
    b = min(255, int(b + (255 - b) * amount))
    return f"#{r:02X}{g:02X}{b:02X}"


def darken_hex(color: str, amount: float = 0.04) -> str:
    """hex 색상을 살짝 차분하게 눌러 깊이감을 만든다."""
    h = resolve_hex(color).lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = max(0, int(r * (1.0 - amount)))
    g = max(0, int(g * (1.0 - amount)))
    b = max(0, int(b * (1.0 - amount)))
    return f"#{r:02X}{g:02X}{b:02X}"

