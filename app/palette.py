"""16색 프리셋과 글자색 계산 (spec 2.5). Flet 비의존 (P5)."""

# ColorHunt 파스텔 톤 16색. 모두 밝고 부드러워 먹색 글자가 선명히 읽힌다 (text_color가 자동 결정)
PALETTE: dict[str, str] = {
    "red": "#F5C2C2",
    "pink": "#F4CFE0",
    "purple": "#DCD0F2",
    "indigo": "#CBD2F2",
    "blue": "#C9DDF4",
    "sky": "#C6E6F5",
    "cyan": "#C2EAE8",
    "slate": "#D5DCE4",
    "teal": "#C4E5D6",
    "green": "#CCE6CB",
    "lime": "#E0ECC2",
    "yellow": "#F7EBB9",
    "amber": "#F7DFB9",
    "orange": "#F8D5BD",
    "brown": "#E6D3C5",
    "gray": "#E3E6EA",
}

# 배경색 (F9). 16색 셀과 먹색 글자가 모두 잘 보이도록 아주 연한 파스텔 틴트만 둔다 (DESIGN.md)
BACKGROUNDS: dict[str, str] = {
    # 대표 무드 테마
    "lavender": "#F2EEFA",
    "peach": "#FDF0E8",
    "mint": "#EAF6F0",
    "sky": "#ECF3FC",
    "rose": "#FCECF1",
    "butter": "#FDF9E6",
    "oatmeal": "#F5EFE9",
    "white": "#FFFFFF",
    # 추가 파스텔 테마
    "coral": "#FDEEEB",
    "sage": "#EDF4EE",
    "lilac": "#F6EEFA",
    "ice": "#EAF5FA",
    "ivory": "#FBF7EB",
    "blush": "#FDF0F2",
    "apricot": "#FDEEE2",
    "sand": "#F6F1E9",
    "matcha": "#ECF4EA",
    "ocean": "#EAEFF9",
    "olive": "#EEF2E6",
    "warm_gray": "#F4F1EE",
    "cool_gray": "#EEF1F5",
    "gray": "#F3F4F6",
    "ash": "#ECEEF1",
}

BACKGROUND_LABELS: dict[str, str] = {
    "lavender": "라벤더",
    "peach": "피치",
    "mint": "민트",
    "sky": "스카이",
    "rose": "로즈",
    "butter": "버터",
    "oatmeal": "오트밀",
    "white": "화이트",
    "coral": "코랄",
    "sage": "세이지",
    "lilac": "라일락",
    "ice": "아이스",
    "ivory": "아이보리",
    "blush": "연분홍",
    "apricot": "살구",
    "sand": "모래",
    "matcha": "말차",
    "ocean": "바다",
    "olive": "올리브",
    "warm_gray": "웜그레이",
    "cool_gray": "쿨그레이",
    "gray": "회색",
    "ash": "애쉬",
}

# 설정 시트 대표 테마 순서 (카드 UI 2열 배치)
FEATURED_BACKGROUNDS: tuple[str, ...] = (
    "lavender",
    "peach",
    "mint",
    "sky",
    "rose",
    "butter",
    "oatmeal",
    "white",
)

# 각 테마의 대표 파스텔 단색 견본 (컬러 테마 카드 미리보기용)
THEME_SWATCHES: dict[str, str] = {
    "lavender": "#D6CCEE",
    "peach": "#F6DBC8",
    "mint": "#C6E4D4",
    "sky": "#CEE0F3",
    "rose": "#F4CFE0",
    "butter": "#F7EBB9",
    "oatmeal": "#E6D3C5",
    "white": "#F7F8FA",
    "coral": "#F5C2C2",
    "sage": "#CCE6CB",
    "lilac": "#E5CFF2",
    "ice": "#C6E6F5",
    "ivory": "#F6ECC9",
    "blush": "#F6D4DC",
    "apricot": "#F8D5BD",
    "sand": "#EAE0D5",
    "matcha": "#C9E4C5",
    "ocean": "#C9DDF4",
    "olive": "#DCE6C5",
    "warm_gray": "#E3DFDA",
    "cool_gray": "#D5DCE4",
    "gray": "#E3E6EA",
    "ash": "#DCE0E5",
}

# 선택된 테마 카드의 테두리 및 체크 배지 포인트 컬러 (부드러운 뮤트 파스텔)
THEME_ACCENTS: dict[str, str] = {
    "lavender": "#8B78B8",
    "peach": "#D48E6A",
    "mint": "#6BA88D",
    "sky": "#6D99C9",
    "rose": "#C97D9B",
    "butter": "#C7A64B",
    "oatmeal": "#A68B76",
    "white": "#181D26",
    "coral": "#D47C7C",
    "sage": "#78A37E",
    "lilac": "#9D78B8",
    "ice": "#67A6C4",
    "ivory": "#B89E68",
    "blush": "#CC829B",
    "apricot": "#D18D64",
    "sand": "#A89680",
    "matcha": "#79A372",
    "ocean": "#6E8BC4",
    "olive": "#889C68",
    "warm_gray": "#8E877F",
    "cool_gray": "#78859C",
    "gray": "#7A828E",
    "ash": "#6D7682",
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

