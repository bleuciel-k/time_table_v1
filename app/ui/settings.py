"""설정 시트: 요일·교시 수, 교시 시간 표시 (F9). 검증은 model/controller가 한다 (P5). 스타일은 DESIGN.md."""

from dataclasses import replace
from typing import Callable

import flet as ft

from app import design as d
from app.controller import ActionResult, AppController
from app.model import DAYS_CHOICES, PERIOD_MAX, PERIOD_MIN, Settings, lunch_time
from app.palette import (
    BACKGROUND_LABELS,
    BACKGROUNDS,
    FEATURED_BACKGROUNDS,
    THEME_ACCENTS,
    THEME_SWATCHES,
    darken_hex,
)
from app.ui import theme as t

ShowResult = Callable[[ActionResult], None]
NOT_A_NUMBER = "수업 시간과 쉬는 시간은 숫자로 입력하세요."


def open_settings(page: ft.Page, controller: AppController, show_result: ShowResult) -> None:
    draft: Settings = replace(controller.workspace.data.settings)
    show_all_themes = draft.background not in FEATURED_BACKGROUNDS
    days_row = ft.Row(spacing=d.SPACE_XS)
    theme_grid = ft.Column(spacing=d.SPACE_SM, tight=True)
    theme_toggle_btn = ft.TextButton(
        "더보기",
        style=ft.ButtonStyle(
            color=d.MUTED,
            padding=ft.Padding.symmetric(horizontal=d.SPACE_XS, vertical=0),
            text_style=t.style(d.SMALL, d.MUTED),
        ),
    )
    theme_header = ft.Row(
        [
            ft.Column(
                [
                    t.text("컬러 테마", d.LABEL, color=d.INK),
                    t.text("오늘의 기분에 맞는 색을 골라보세요", d.SMALL, color=d.MUTED),
                ],
                spacing=2,
                tight=True,
                expand=True,
            ),
            theme_toggle_btn,
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
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

    sheet: ft.BottomSheet | None = None

    def close() -> None:
        if sheet is not None:
            sheet.open = False
        try:
            page.update()
        except Exception:
            pass

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

    def toggle_all_themes(e: ft.Event[ft.TextButton]) -> None:
        nonlocal show_all_themes
        show_all_themes = not show_all_themes
        sync()

    theme_toggle_btn.on_click = toggle_all_themes

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

    def theme_card(key: str) -> ft.Container:
        selected = draft.background == key
        accent = THEME_ACCENTS.get(key, d.INK)
        swatch_hex = THEME_SWATCHES.get(key, BACKGROUNDS[key])
        card_bg = BACKGROUNDS[key] if selected and key != "white" else d.CANVAS
        badge = (
            ft.Container(
                ft.Icon(ft.Icons.CHECK, color=d.ON_PRIMARY, size=12),
                width=22,
                height=22,
                gradient=t.clay_gradient(accent),
                border=t.clay_border(accent, rim_width=1.0, bottom_width=1.8),
                shadow=t.clay_shadow(blur=4, y=1.5),
                border_radius=ft.BorderRadius.all(11),
                alignment=ft.Alignment.CENTER,
            )
            if selected
            else ft.Container(width=22, height=22)
        )
        swatch_bar = ft.Container(
            height=30,
            gradient=t.clay_gradient(swatch_hex),
            border=t.clay_border(swatch_hex, rim_width=1.2, bottom_width=2.2),
            shadow=t.clay_shadow(blur=5, y=2),
            border_radius=ft.BorderRadius.all(d.RADIUS_SM),
        )
        card_border = (
            ft.Border(
                top=ft.BorderSide(1.8, accent),
                left=ft.BorderSide(1.8, accent),
                right=ft.BorderSide(2.0, darken_hex(accent, 0.14)),
                bottom=ft.BorderSide(3.0, darken_hex(accent, 0.22)),
            )
            if selected
            else t.clay_border(card_bg, rim_width=1.3, bottom_width=2.4)
        )
        return ft.Container(
            ft.Column(
                [
                    ft.Row(
                        [t.text(BACKGROUND_LABELS[key], d.CAPTION, color=d.INK), badge],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    swatch_bar,
                ],
                spacing=d.SPACE_XS,
                tight=True,
            ),
            expand=True,
            padding=ft.Padding.all(d.SPACE_SM),
            gradient=t.clay_gradient(card_bg),
            border_radius=ft.BorderRadius.all(d.RADIUS_LG),
            border=card_border,
            shadow=t.clay_shadow(blur=8, y=3.5),
            ink=True,
            on_click=lambda e, k=key: choose_background(k),
        )

    def sync() -> None:
        visible_keys = list(BACKGROUNDS) if show_all_themes else list(FEATURED_BACKGROUNDS)
        theme_toggle_btn.content = "접기" if show_all_themes else f"더보기 ({len(BACKGROUNDS)})"
        card_rows: list[ft.Control] = []
        for idx in range(0, len(visible_keys), 2):
            pair = visible_keys[idx : idx + 2]
            row_controls: list[ft.Control] = [theme_card(k) for k in pair]
            if len(row_controls) == 1:
                row_controls.append(ft.Container(expand=True))
            card_rows.append(ft.Row(row_controls, spacing=d.SPACE_SM))
        theme_grid.controls = card_rows
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
        if sheet is not None:
            try:
                sheet.update()
                return
            except Exception:
                pass
        try:
            page.update()
        except Exception:
            pass

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
            theme_header,
            theme_grid,
            t.actions_row(
                t.secondary_button("취소", lambda e: close()),
                t.primary_button("저장", save),
            ),
        ],
    )
    page.show_dialog(sheet)
    sync()
