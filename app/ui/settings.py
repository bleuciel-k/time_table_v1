"""설정 시트: 요일·교시 수, 교시 시간 표시 (F9). 검증은 model/controller가 한다 (P5)."""

from dataclasses import replace
from typing import Callable

import flet as ft

from app.controller import ActionResult, AppController
from app.model import DAYS_CHOICES, PERIOD_MAX, PERIOD_MIN, Settings

ShowResult = Callable[[ActionResult], None]
NOT_A_NUMBER = "수업 시간과 쉬는 시간은 숫자로 입력하세요."


def open_settings(page: ft.Page, controller: AppController, show_result: ShowResult) -> None:
    draft: Settings = replace(controller.workspace.data.settings)
    sheet = ft.BottomSheet(ft.Container(), show_drag_handle=True, scrollable=True)

    days_row = ft.Row(spacing=8)
    periods_row = ft.Row(wrap=True, spacing=8, run_spacing=8)
    start_time = ft.TextField(label="1교시 시작", value=draft.start_time, helper="HH:MM")
    class_minutes = ft.TextField(label="수업 시간(분)", value=str(draft.class_minutes))
    break_minutes = ft.TextField(label="쉬는 시간(분)", value=str(draft.break_minutes))
    time_fields = ft.Column([start_time, class_minutes, break_minutes], tight=True, spacing=12)

    def close() -> None:
        sheet.open = False
        page.update()

    def choose_days(value: int) -> None:
        nonlocal draft
        draft = replace(draft, days=value)
        sync()

    def choose_periods(value: int) -> None:
        nonlocal draft
        draft = replace(draft, periods=value)
        sync()

    def toggle_times(e: ft.Event[ft.Switch]) -> None:
        nonlocal draft
        draft = replace(draft, show_times=bool(e.control.value))
        sync()

    def save(e: ft.Event[ft.FilledButton]) -> None:
        try:
            candidate = replace(
                draft,
                start_time=(start_time.value or "").strip(),
                class_minutes=int(class_minutes.value),
                break_minutes=int(break_minutes.value),
            )
        except (TypeError, ValueError):
            show_result(ActionResult(False, NOT_A_NUMBER))
            return
        result = controller.update_settings(candidate)
        if result.applied:
            close()
        show_result(result)

    show_switch = ft.Switch(
        label="교시 시간 표시", value=draft.show_times, on_change=toggle_times
    )

    def chip(label: str, selected: bool, on_click: Callable[[], None]) -> ft.Container:
        return ft.Container(
            ft.Text(label, color=ft.Colors.ON_PRIMARY if selected else ft.Colors.ON_SURFACE),
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            border_radius=ft.BorderRadius.all(20),
            bgcolor=ft.Colors.PRIMARY if selected else None,
            border=None if selected else ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            ink=True,
            on_click=lambda e: on_click(),
        )

    def sync() -> None:
        days_row.controls = [
            chip(f"{value}일", draft.days == value, lambda v=value: choose_days(v))
            for value in DAYS_CHOICES
        ]
        periods_row.controls = [
            chip(f"{value}교시", draft.periods == value, lambda v=value: choose_periods(v))
            for value in range(PERIOD_MIN, PERIOD_MAX + 1)
        ]
        time_fields.visible = draft.show_times
        page.update()

    def label(text: str) -> ft.Text:
        return ft.Text(text, weight=ft.FontWeight.BOLD)

    sheet.content = ft.Container(
        ft.Column(
            [
                ft.Text("설정", size=18, weight=ft.FontWeight.BOLD),
                label("요일 수"),
                days_row,
                label("교시 수"),
                periods_row,
                show_switch,
                time_fields,
                ft.Row(
                    [
                        ft.TextButton("취소", on_click=lambda e: close()),
                        ft.FilledButton("저장", on_click=save),
                    ],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
            tight=True,
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=ft.Padding.all(20),
    )
    page.show_dialog(sheet)
    sync()
