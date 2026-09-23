"""설정 시트: 요일·교시 수, 교시 시간 표시 (F9). 검증은 model/controller가 한다 (P5). 스타일은 DESIGN.md."""

from dataclasses import replace
from typing import Callable

import flet as ft

from app import design as d
from app.controller import ActionResult, AppController
from app.model import DAYS_CHOICES, PERIOD_MAX, PERIOD_MIN, Settings, lunch_time
from app.palette import BACKGROUND_LABELS, BACKGROUNDS
from app.ui import theme as t

SWATCH_SIZE = 36

ShowResult = Callable[[ActionResult], None]
NOT_A_NUMBER = "수업 시간과 쉬는 시간은 숫자로 입력하세요."


def open_settings(page: ft.Page, controller: AppController, show_result: ShowResult) -> None:
    draft: Settings = replace(controller.workspace.data.settings)
    days_row = ft.Row(spacing=d.SPACE_XS)
    background_row = ft.Row(wrap=True, spacing=d.SPACE_XS, run_spacing=d.SPACE_XS)
    background_label = t.label("배경색")
    periods_row = ft.Row(wrap=True, spacing=d.SPACE_XS, run_spacing=d.SPACE_XS)
    start_time = t.text_field("1교시 시작", value=draft.start_time, helper="HH:MM")
    class_minutes = t.text_field("수업 시간(분)", value=str(draft.class_minutes))
    break_minutes = t.text_field("쉬는 시간(분)", value=str(draft.break_minutes))
    time_fields = ft.Column(
        [start_time, class_minutes, break_minutes], tight=True, spacing=d.SPACE_SM
    )
    lunch_after_row = ft.Row(wrap=True, spacing=d.SPACE_XS, run_spacing=d.SPACE_XS)
    lunch_minutes = t.text_field("점심시간(분)", value=str(draft.lunch_minutes))
    lunch_hint = t.label("")
    lunch_fields = ft.Column(
        [t.label("몇 교시 뒤"), lunch_after_row, lunch_minutes, lunch_hint],
        tight=True,
        spacing=d.SPACE_SM,
    )

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

    def choose_lunch_after(value: int) -> None:
        nonlocal draft
        draft = replace(draft, lunch_after=value)
        sync()

    def toggle_lunch(e: ft.Event[ft.Switch]) -> None:
        nonlocal draft
        draft = replace(draft, lunch=bool(e.control.value))
        sync()

    def choose_background(value: str) -> None:
        nonlocal draft
        draft = replace(draft, background=value)
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
                lunch_minutes=int(lunch_minutes.value),
            )
        except (TypeError, ValueError):
            show_result(ActionResult(False, NOT_A_NUMBER))
            return
        result = controller.update_settings(candidate)
        if result.applied:
            close()
        show_result(result)

    def switch(label: str, value: bool, on_change) -> ft.Switch:
        return ft.Switch(
            label=label,
            value=value,
            on_change=on_change,
            active_color=d.ON_PRIMARY,
            active_track_color=d.INK,
            label_text_style=t.style(d.BODY_MD, d.BODY),
        )

    show_switch = switch("교시 시간 표시", draft.show_times, toggle_times)
    lunch_switch = switch("점심시간", draft.lunch, toggle_lunch)

    def background_swatch(key: str) -> ft.Container:
        selected = draft.background == key
        return ft.Container(
            ft.Icon(ft.Icons.CHECK, color=d.INK, size=18) if selected else None,
            width=SWATCH_SIZE,
            height=SWATCH_SIZE,
            bgcolor=BACKGROUNDS[key],
            border_radius=ft.BorderRadius.all(SWATCH_SIZE / 2),
            border=ft.Border.all(2, d.INK) if selected else ft.Border.all(1, d.HAIRLINE),
            alignment=ft.Alignment.CENTER,
            tooltip=BACKGROUND_LABELS[key],
            on_click=lambda e, k=key: choose_background(k),
        )

    def sync() -> None:
        background_row.controls = [background_swatch(key) for key in BACKGROUNDS]
        background_label.value = f"배경색 · {BACKGROUND_LABELS[draft.background]}"
        days_row.controls = [
            t.chip(f"{value}일", draft.days == value, lambda v=value: choose_days(v))
            for value in DAYS_CHOICES
        ]
        periods_row.controls = [
            t.chip(f"{value}교시", draft.periods == value, lambda v=value: choose_periods(v))
            for value in range(PERIOD_MIN, PERIOD_MAX + 1)
        ]
        time_fields.visible = draft.show_times
        lunch_after_row.controls = [
            t.chip(
                f"{value}교시",
                draft.lunch_after == value,
                lambda v=value: choose_lunch_after(v),
            )
            for value in range(PERIOD_MIN, min(draft.periods, PERIOD_MAX - 1) + 1)
        ]
        lunch_fields.visible = draft.lunch
        times = lunch_time(draft)
        lunch_hint.value = (
            f"{times[0]}–{times[1]}"
            if times
            else "마지막 교시 앞에 와야 표시됩니다."
        )
        page.update()

    sheet = t.sheet(
        "설정",
        [
            t.label("요일 수"),
            days_row,
            t.label("교시 수"),
            periods_row,
            show_switch,
            time_fields,
            lunch_switch,
            lunch_fields,
            background_label,
            background_row,
            t.actions_row(
                t.secondary_button("취소", lambda e: close()),
                t.primary_button("저장", save),
            ),
        ],
    )
    page.show_dialog(sheet)
    sync()
