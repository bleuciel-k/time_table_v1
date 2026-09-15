"""주간 그리드. 표시만 담당하고 배치 계산은 `model.grid_cells`에 둔다 (P5)."""

from typing import Callable

import flet as ft

from app.model import DAY_LABELS, PERIOD_MIN, Cell, Settings, Timetable, cell_key, grid_cells
from app.palette import resolve_hex, text_color

PERIOD_COL_WIDTH = 28
HEADER_HEIGHT = 32
CELL_HEIGHT = 84
GAP = 2
RADIUS = 6

KeyHandler = Callable[[str], None]


def build_grid(
    timetable: Timetable,
    settings: Settings,
    on_cell_click: KeyHandler | None = None,
    on_cell_long_press: KeyHandler | None = None,
) -> ft.Control:
    """핸들러가 None이면 해당 조작 없음 (읽기 전용)."""
    rows: list[ft.Control] = [_header(settings.days)]
    for offset, row in enumerate(grid_cells(timetable, settings)):
        period = PERIOD_MIN + offset
        cells = [
            _cell(cell, cell_key(day, period), on_cell_click, on_cell_long_press)
            for day, cell in enumerate(row)
        ]
        rows.append(ft.Row([_period_label(period), *cells], spacing=GAP))
    return ft.Column(rows, spacing=GAP, scroll=ft.ScrollMode.AUTO, expand=True)


def _header(days: int) -> ft.Row:
    labels = [
        ft.Container(
            ft.Text(DAY_LABELS[day], weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
            expand=1,
            height=HEADER_HEIGHT,
            alignment=ft.Alignment.CENTER,
        )
        for day in range(days)
    ]
    return ft.Row([ft.Container(width=PERIOD_COL_WIDTH), *labels], spacing=GAP)


def _period_label(period: int) -> ft.Container:
    return ft.Container(
        ft.Text(str(period), color=ft.Colors.ON_SURFACE_VARIANT),
        width=PERIOD_COL_WIDTH,
        height=CELL_HEIGHT,
        alignment=ft.Alignment.CENTER,
    )


def _cell(
    cell: Cell | None,
    key: str,
    on_click: KeyHandler | None,
    on_long_press: KeyHandler | None,
) -> ft.Container:
    interaction = {
        "ink": on_click is not None or on_long_press is not None,
        "on_click": (lambda e: on_click(key)) if on_click else None,
        "on_long_press": (lambda e: on_long_press(key)) if on_long_press else None,
    }
    if cell is None:
        return ft.Container(
            expand=1,
            height=CELL_HEIGHT,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=ft.BorderRadius.all(RADIUS),
            **interaction,
        )
    fg = text_color(cell.color)
    lines: list[ft.Control] = [
        ft.Text(
            cell.subject,
            color=fg,
            size=12,
            weight=ft.FontWeight.BOLD,
            max_lines=3,
            overflow=ft.TextOverflow.ELLIPSIS,
            text_align=ft.TextAlign.CENTER,
        )
    ]
    if cell.room:
        lines.append(
            ft.Text(
                cell.room,
                color=fg,
                size=10,
                max_lines=1,
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
        padding=ft.Padding.all(4),
        alignment=ft.Alignment.CENTER,
        **interaction,
    )
