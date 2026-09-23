"""주간 그리드. 표시만 담당하고 배치 계산은 `model.grid_cells`에 둔다 (P5). 스타일은 DESIGN.md (T11)."""

from typing import Callable

import flet as ft

from app import design as d
from app.model import (
    DAY_LABELS,
    PERIOD_MIN,
    Cell,
    Settings,
    Timetable,
    cell_key,
    grid_cells,
    has_lunch,
    lunch_time,
    period_times,
)
from app.palette import resolve_hex, text_color
from app.ui.theme import text

PERIOD_COL_WIDTH = 28
TIME_COL_WIDTH = 46  # 교시 시간을 함께 표시할 때 (F9)
HEADER_HEIGHT = 32
CELL_HEIGHT = 84
LUNCH_HEIGHT = 30
MEMO_MAX_LINES = 2
GAP = d.SPACE_XXS
RADIUS = d.RADIUS_MD

KeyHandler = Callable[[str], None]


def build_grid(
    timetable: Timetable,
    settings: Settings,
    on_cell_click: KeyHandler | None = None,
    on_cell_long_press: KeyHandler | None = None,
) -> ft.Control:
    """핸들러가 None이면 해당 조작 없음 (읽기 전용)."""
    times = period_times(settings) if settings.show_times else None
    width = TIME_COL_WIDTH if times else PERIOD_COL_WIDTH
    rows: list[ft.Control] = [_header(settings.days, width)]
    for offset, row in enumerate(grid_cells(timetable, settings)):
        period = PERIOD_MIN + offset
        cells = [
            _cell(cell, cell_key(day, period), on_cell_click, on_cell_long_press, settings)
            for day, cell in enumerate(row)
        ]
        label = _period_label(period, times[offset] if times else None, width)
        rows.append(ft.Row([label, *cells], spacing=GAP))
        if has_lunch(settings) and period == settings.lunch_after:
            rows.append(_lunch_row(settings, width))
    return ft.Column(rows, spacing=GAP, scroll=ft.ScrollMode.AUTO, expand=True)


def _lunch_row(settings: Settings, label_width: float) -> ft.Row:
    """교시 사이의 점심시간 띠 (F9)."""
    times = lunch_time(settings)
    caption = "점심시간"
    if settings.show_times and times:
        caption = f"점심시간 · {times[0]}–{times[1]}"
    return ft.Row(
        [
            ft.Container(width=label_width),
            ft.Container(
                text(caption, d.SMALL, color=d.MUTED, text_align=ft.TextAlign.CENTER),
                expand=1,
                height=LUNCH_HEIGHT,
                border=ft.Border.all(1, d.HAIRLINE),
                border_radius=ft.BorderRadius.all(RADIUS),
                alignment=ft.Alignment.CENTER,
            ),
        ],
        spacing=GAP,
    )


def _header(days: int, label_width: float) -> ft.Row:
    labels = [
        ft.Container(
            text(DAY_LABELS[day], d.CAPTION, color=d.MUTED, text_align=ft.TextAlign.CENTER),
            expand=1,
            height=HEADER_HEIGHT,
            alignment=ft.Alignment.CENTER,
        )
        for day in range(days)
    ]
    return ft.Row([ft.Container(width=label_width), *labels], spacing=GAP)


def _period_label(period: int, times: tuple[str, str] | None, width: float) -> ft.Container:
    lines: list[ft.Control] = [text(str(period), d.CAPTION, color=d.MUTED)]
    if times:
        lines += [
            text(value, (9, 400), color=d.MUTED, text_align=ft.TextAlign.CENTER)
            for value in times
        ]
    return ft.Container(
        ft.Column(
            lines,
            spacing=0,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        width=width,
        height=CELL_HEIGHT,
        alignment=ft.Alignment.CENTER,
    )


def _cell(
    cell: Cell | None,
    key: str,
    on_click: KeyHandler | None,
    on_long_press: KeyHandler | None,
    settings: Settings | None = None,
) -> ft.Container:
    interaction = {
        "ink": on_click is not None or on_long_press is not None,
        "on_click": (lambda e: on_click(key)) if on_click else None,
        "on_long_press": (lambda e: on_long_press(key)) if on_long_press else None,
    }
    if cell is None:
        # 배경과 같은 색으로 두고 윤곽선만 남긴다 — 비어 있다는 느낌은 테두리가 낸다
        return ft.Container(
            expand=1,
            height=CELL_HEIGHT,
            border=ft.Border.all(1, d.HAIRLINE),
            border_radius=ft.BorderRadius.all(RADIUS),
            **interaction,
        )
    fg = text_color(cell.color)
    lines: list[ft.Control] = [
        text(
            cell.subject,
            (13, 500),  # 셀 안에서도 굵게가 아니라 중간 굵기 (DESIGN.md)
            color=fg,
            max_lines=3,
            overflow=ft.TextOverflow.ELLIPSIS,
            text_align=ft.TextAlign.CENTER,
        )
    ]
    if cell.room:
        lines.append(
            text(
                cell.room,
                (11, 400),
                color=fg,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
                text_align=ft.TextAlign.CENTER,
            )
        )
    if settings is not None and settings.show_memo and cell.memo:
        lines.append(
            text(
                cell.memo,
                (9, 400),  # 메모는 가장 작은 글씨로 최대 2줄 (F9)
                color=fg,
                max_lines=MEMO_MAX_LINES,
                overflow=ft.TextOverflow.ELLIPSIS,
                text_align=ft.TextAlign.CENTER,
            )
        )
    return ft.Container(
        ft.Column(
            lines,
            spacing=2,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        expand=1,
        height=CELL_HEIGHT,
        bgcolor=resolve_hex(cell.color),
        border_radius=ft.BorderRadius.all(RADIUS),
        padding=ft.Padding.all(d.SPACE_XS),
        alignment=ft.Alignment.CENTER,
        **interaction,
    )
