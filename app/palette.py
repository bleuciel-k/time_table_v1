"""16색 프리셋과 글자색 계산 (spec 2.5). Flet 비의존 (P5)."""

PALETTE: dict[str, str] = {
    "red": "#EF5350",
    "pink": "#EC407A",
    "purple": "#AB47BC",
    "indigo": "#5C6BC0",
    "blue": "#42A5F5",
    "sky": "#29B6F6",
    "cyan": "#26C6DA",
    "slate": "#78909C",
    "teal": "#26A69A",
    "green": "#66BB6A",
    "lime": "#D4E157",
    "yellow": "#FFEE58",
    "amber": "#FFCA28",
    "orange": "#FFA726",
    "brown": "#8D6E63",
    "gray": "#BDBDBD",
}

# 배경색 (F9). 16색 셀과 먹색 글자가 모두 잘 보이도록 아주 연한 색만 둔다 (DESIGN.md)
BACKGROUNDS: dict[str, str] = {
    "white": "#FFFFFF",
    "ivory": "#FBF6EA",
    "sand": "#F7F1E8",
    "blush": "#FCF0F1",
    "mint": "#EDF7F1",
    "sky": "#EEF3FB",
    "lavender": "#F3F0FA",
    "gray": "#F4F5F7",
}

BACKGROUND_LABELS: dict[str, str] = {
    "white": "흰색",
    "ivory": "아이보리",
    "sand": "모래",
    "blush": "연분홍",
    "mint": "민트",
    "sky": "하늘",
    "lavender": "라벤더",
    "gray": "회색",
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
