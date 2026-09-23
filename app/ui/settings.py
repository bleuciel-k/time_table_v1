"""설정 시트: 요일·교시 수, 교시 시간 표시 (F9). 검증은 model/controller가 한다 (P5). 스타일은 DESIGN.md."""

from dataclasses import replace
from typing import Callable

import flet as ft

from app import design as d
from app.controller import ActionResult, AppController
from app.model import DAYS_CHOICES, PERIOD_MAX, PERIOD_MIN, Settings
from app.ui import theme as t

ShowResult = Callable[[ActionResult], None]
NOT_A_NUMBER = "수업 시간과 쉬는 시간은 숫자로 입력하세요."


def open_settings(page: ft.Page, controller: AppController, show_result: ShowResult) -> None:
    draft: Settings = replace(controller.workspace.data.settings)
    days_row = ft.Row(spacing=d.SPACE_XS)
    periods_row = ft.Row(wrap=True, spacing=d.SPACE_XS, run_spacing=d.SPACE_XS)
    start_time = t.text_field("1교시 시작", value=draft.start_time, helper="HH:MM")
    class_minutes = t.text_field("수업 시간(분)", value=str(draft.class_minutes))
    break_minutes = t.text_field("쉬는 시간(분)", value=str(draft.break_minutes))
    time_fields = ft.Column(
        [start_time, class_minutes, break_minutes], tight=True, spacing=d.SPACE_SM
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
        label="교시 시간 표시",
        value=draft.show_times,
        on_change=toggle_times,
        active_color=d.INK,
        label_style=t.style(d.BODY_MD, d.BODY),
    )

    def sync() -> None:
        days_row.controls = [
            t.chip(f"{value}일", draft.days == value, lambda v=value: choose_days(v))
            for value in DAYS_CHOICES
        ]
        periods_row.controls = [
            t.chip(f"{value}교시", draft.periods == value, lambda v=value: choose_periods(v))
            for value in range(PERIOD_MIN, PERIOD_MAX + 1)
        ]
        time_fields.visible = draft.show_times
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
            t.actions_row(
                t.secondary_button("취소", lambda e: close()),
                t.primary_button("저장", save),
            ),
        ],
    )
    page.show_dialog(sheet)
    sync()
