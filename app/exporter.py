"""시간표 → PNG/JPG 이미지 bytes (F6, spec 3.4). Flet 비의존 (P5)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from app import design as d
from app.model import (
    DAY_LABELS,
    PERIOD_MIN,
    Cell,
    Settings,
    Timetable,
    grid_cells,
    has_lunch,
    lunch_time,
    period_times,
)
from app.palette import DEFAULT_BACKGROUND, background_hex, resolve_hex, text_color

FORMATS = ("png", "jpg")
SCALES = (1, 2)
JPEG_QUALITY = 92
MAX_SUBJECT_LINES = 3
MAX_MEMO_LINES = 2

# 글자 크기 (1x 기준) — 화면 그리드와 같은 값
HEADER_SIZE = 13
PERIOD_SIZE = 13
TIME_SIZE = 8
SUBJECT_SIZE = 12
ROOM_SIZE = 10
MEMO_SIZE = 8
LUNCH_SIZE = 11
LINE_HEIGHT = 14
ELLIPSIS = "…"

# 기기에 있는 CJK 폰트를 먼저 쓰고(APK 크기 절약), 없으면 번들 폰트를 쓴다.
# 한글과 일본어를 모두 덮는 폰트여야 한다 — 예: macOS의 AppleSDGothicNeo는
# 한글은 되지만 会·応 같은 일본어 한자가 없어 두부(□)로 그려진다.
_ASSETS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
BUNDLED_FONT = str(_ASSETS / "NotoSansCJKkr-Regular.otf")
BUNDLED_FONT_MEDIUM = str(_ASSETS / "NotoSansCJKkr-Medium.otf")

FONT_CANDIDATES = (
    BUNDLED_FONT,  # 앱에 넣은 폰트 (화면과 같은 글꼴)
    "/system/fonts/NotoSansCJK-Regular.ttc",  # Android (한·중·일 통합)
    "/system/fonts/NotoSerifCJK-Regular.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",  # macOS
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",  # 최후 수단 (일본어 일부 누락)
)

# 색은 화면과 같은 토큰을 쓴다 (DESIGN.md, T11)
TRANSPARENT = (255, 255, 255, 0)  # 배경색이 기본(흰색)일 때만 PNG를 투명하게 둔다
EMPTY_CELL_BORDER = d.rgba(d.HAIRLINE)
LABEL_COLOR = d.rgba(d.MUTED)
HEADER_COLOR = d.rgba(d.MUTED)


@dataclass(frozen=True)
class ExportOptions:
    fmt: str = "png"  # png | jpg
    scale: int = 1  # 1x | 2x


@dataclass(frozen=True)
class Layout:
    """1x 기준 치수에 배율을 곱한 값."""

    settings: Settings
    scale: int = 1

    @property
    def padding(self) -> int:
        return d.SPACE_MD * self.scale

    @property
    def gap(self) -> int:
        return d.SPACE_XXS * self.scale

    @property
    def radius(self) -> int:
        return d.RADIUS_MD * self.scale

    @property
    def header_height(self) -> int:
        return 34 * self.scale

    @property
    def lunch_height(self) -> int:
        """점심시간 띠 높이 (F9). 표시하지 않으면 0."""
        return (30 * self.scale + self.gap) if has_lunch(self.settings) else 0

    @property
    def cell_width(self) -> int:
        return 104 * self.scale

    @property
    def cell_height(self) -> int:
        return 84 * self.scale

    @property
    def label_width(self) -> int:
        return (52 if self.settings.show_times else 32) * self.scale

    @property
    def width(self) -> int:
        cells = self.settings.days * self.cell_width + (self.settings.days - 1) * self.gap
        return self.padding * 2 + self.label_width + self.gap + cells

    @property
    def height(self) -> int:
        rows = self.settings.periods
        return (
            self.padding * 2
            + self.header_height
            + self.gap
            + rows * self.cell_height
            + (rows - 1) * self.gap
            + self.lunch_height
        )

    def cell_box(self, day: int, period_index: int) -> tuple[int, int, int, int]:
        left = self.padding + self.label_width + self.gap + day * (self.cell_width + self.gap)
        top = (
            self.padding
            + self.header_height
            + self.gap
            + period_index * (self.cell_height + self.gap)
            + (self.lunch_height if period_index >= self.settings.lunch_after else 0)
        )
        return left, top, left + self.cell_width, top + self.cell_height

    def lunch_box(self) -> tuple[int, int, int, int]:
        """점심시간 띠 영역 (표 전체 폭)."""
        left = self.padding + self.label_width + self.gap
        _, _, right, bottom = self.cell_box(self.settings.days - 1, self.settings.lunch_after - 1)
        top = bottom + self.gap
        return left, top, right, top + self.lunch_height - self.gap


def render(
    timetable: Timetable, settings: Settings, options: ExportOptions = ExportOptions()
) -> bytes:
    """시간표 한 개를 이미지 bytes로 그린다."""
    if options.fmt not in FORMATS:
        raise ValueError(f"지원하지 않는 형식: {options.fmt}")
    if options.scale not in SCALES:
        raise ValueError(f"지원하지 않는 배율: {options.scale}")

    layout = Layout(settings, options.scale)
    # 배경색이 기본이면 지금까지처럼 투명 PNG, 고른 색이 있으면 그 색으로 채운다 (F9, spec 3.4)
    plain = settings.background == DEFAULT_BACKGROUND
    image = Image.new(
        "RGBA",
        (layout.width, layout.height),
        TRANSPARENT if plain else d.rgba(background_hex(settings.background)),
    )
    draw = ImageDraw.Draw(image)
    _draw_header(draw, layout)
    _draw_period_labels(draw, layout)
    _draw_lunch(draw, layout)
    for period_index, row in enumerate(grid_cells(timetable, settings)):
        for day, cell in enumerate(row):
            _draw_cell(draw, layout, day, period_index, cell)
    return _encode(image, options)


def export_filename(name: str, when: date, fmt: str = "png") -> str:
    """`timetable_<이름>_<YYYYMMDD>.<ext>` (F6)."""
    if fmt not in FORMATS:
        raise ValueError(f"지원하지 않는 형식: {fmt}")
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_") or "timetable"
    return f"timetable_{safe}_{when:%Y%m%d}.{fmt}"


# ---------------------------------------------------------------- 그리기


def _draw_header(draw: ImageDraw.ImageDraw, layout: Layout) -> None:
    font = load_font(HEADER_SIZE * layout.scale, medium=True)  # 요일 머리글
    for day in range(layout.settings.days):
        left, _, right, _ = layout.cell_box(day, 0)
        center = ((left + right) // 2, layout.padding + layout.header_height // 2)
        draw.text(center, DAY_LABELS[day], font=font, fill=HEADER_COLOR, anchor="mm")


def _draw_period_labels(draw: ImageDraw.ImageDraw, layout: Layout) -> None:
    settings = layout.settings
    number_font = load_font(PERIOD_SIZE * layout.scale)
    time_font = load_font(TIME_SIZE * layout.scale)
    times = period_times(settings) if settings.show_times else None
    center_x = layout.padding + layout.label_width // 2
    for index in range(settings.periods):
        _, top, _, bottom = layout.cell_box(0, index)
        center_y = (top + bottom) // 2
        if times is None:
            draw.text((center_x, center_y), str(PERIOD_MIN + index), font=number_font,
                      fill=LABEL_COLOR, anchor="mm")
            continue
        start, end = times[index]
        line_height = 11 * layout.scale
        draw.text((center_x, center_y - line_height), str(PERIOD_MIN + index),
                  font=number_font, fill=LABEL_COLOR, anchor="mm")
        draw.text((center_x, center_y), start, font=time_font, fill=LABEL_COLOR, anchor="mm")
        draw.text((center_x, center_y + line_height), end, font=time_font,
                  fill=LABEL_COLOR, anchor="mm")


def _draw_lunch(draw: ImageDraw.ImageDraw, layout: Layout) -> None:
    """교시 사이의 점심시간 띠 (F9)."""
    settings = layout.settings
    times = lunch_time(settings)
    if times is None:
        return
    box = layout.lunch_box()
    draw.rounded_rectangle(box, radius=layout.radius, outline=EMPTY_CELL_BORDER,
                           width=max(1, layout.scale))
    caption = f"점심시간 · {times[0]}–{times[1]}" if settings.show_times else "점심시간"
    left, top, right, bottom = box
    draw.text((((left + right) // 2), (top + bottom) // 2), caption,
              font=load_font(LUNCH_SIZE * layout.scale), fill=LABEL_COLOR, anchor="mm")


def _draw_cell(
    draw: ImageDraw.ImageDraw,
    layout: Layout,
    day: int,
    period_index: int,
    cell: Cell | None,
) -> None:
    box = layout.cell_box(day, period_index)
    if cell is None:
        # 배경과 같은 색(= 칠하지 않음) + 윤곽선만 (F9)
        draw.rounded_rectangle(box, radius=layout.radius, outline=EMPTY_CELL_BORDER,
                               width=max(1, layout.scale))
        return

    left, top, right, bottom = box
    draw.rounded_rectangle(box, radius=layout.radius, fill=resolve_hex(cell.color))
    fill = text_color(cell.color)
    inner_width = (right - left) - d.SPACE_XS * 2 * layout.scale
    subject_font = load_font(SUBJECT_SIZE * layout.scale, medium=True)  # 화면 셀과 같은 크기·굵기
    room_font = load_font(ROOM_SIZE * layout.scale)

    memo_font = load_font(MEMO_SIZE * layout.scale)

    # (글자, 폰트) 순서로 쌓는다: 과목명 최대 3줄 → 강의실 1줄 → 메모 최대 2줄 (F9)
    rows: list[tuple[str, ImageFont.FreeTypeFont]] = [
        (line, subject_font) for line in wrap_text(cell.subject, subject_font, inner_width, MAX_SUBJECT_LINES)
    ]
    if cell.room:
        rows += [(line, room_font) for line in wrap_text(cell.room, room_font, inner_width, 1)]
    if cell.show_memo and cell.memo:
        rows += [
            (line, memo_font)
            for line in wrap_text(cell.memo, memo_font, inner_width, MAX_MEMO_LINES)
        ]
    line_height = LINE_HEIGHT * layout.scale
    center_x = (left + right) // 2
    start_y = (top + bottom) // 2 - (len(rows) - 1) * line_height // 2
    for index, (line, font) in enumerate(rows):
        draw.text((center_x, start_y + index * line_height), line, font=font, fill=fill,
                  anchor="mm")


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int) -> list[str]:
    """셀 폭에 맞춰 줄바꿈하고, 넘치면 마지막 줄을 말줄임한다 (spec 3.4).

    한국어·일본어는 공백이 없어 글자 단위로 끊는다.
    """
    lines: list[str] = []
    current = ""
    for char in text.strip():
        candidate = current + char
        if current and font.getlength(candidate) > max_width:
            lines.append(current)
            current = "" if char == " " else char
            if len(lines) == max_lines:
                break
        else:
            current = candidate
    else:
        if current:
            lines.append(current)
        return lines or [""]

    rest = text.strip()[sum(len(line) for line in lines) :]
    lines[-1] = _ellipsize(lines[-1] + rest, font, max_width)
    return lines


def _ellipsize(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    trimmed = text.strip()
    while trimmed and font.getlength(trimmed + ELLIPSIS) > max_width:
        trimmed = trimmed[:-1]
    return trimmed + ELLIPSIS


def _encode(image: Image.Image, options: ExportOptions) -> bytes:
    buffer = BytesIO()
    if options.fmt == "jpg":
        flattened = Image.new("RGB", image.size, "white")  # JPG는 투명도가 없다 (spec 3.4)
        flattened.paste(image, mask=image.split()[3])
        flattened.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    else:
        image.save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------- 폰트


def font_path(medium: bool = False) -> str | None:
    if medium and os.path.exists(BUNDLED_FONT_MEDIUM):
        return BUNDLED_FONT_MEDIUM
    for candidate in FONT_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return None


@lru_cache(maxsize=64)
def load_font(size: int, medium: bool = False) -> ImageFont.FreeTypeFont:
    """화면과 같은 글꼴. `medium=True`면 중간 굵기(과목명 등)."""
    path = font_path(medium)
    if path is None:  # CJK 폰트가 없으면 글자가 깨질 수 있다 (T8에서 기기 확인)
        return ImageFont.load_default(size)
    return ImageFont.truetype(path, size)


def has_cjk_font() -> bool:
    return font_path() is not None
