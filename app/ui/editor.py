"""셀 편집 시트 (F1, F2). 입력 상태와 규칙은 `controller.CellForm`에 둔다 (P5)."""

from typing import Callable

import flet as ft

from app.controller import AppController
from app.model import DAY_LABELS, FIELD_MAX, SUBJECT_MAX, parse_cell_key
from app.palette import PALETTE, resolve_hex, text_color

SWATCH_SIZE = 36
SUGGESTED_HINT = "기존 과목의 색을 적용했어요."


def open_cell_editor(
    page: ft.Page, controller: AppController, key: str, on_saved: Callable[[], None]
) -> None:
    form = controller.form_for(key)
    day, period = parse_cell_key(key)
    # 새 셀은 입력을 시작한 뒤부터 과목명 오류를 보여준다 (그 전에는 안내 문구만)
    subject_touched = not form.is_new

    def on_subject(e: ft.Event[ft.TextField]) -> None:
        nonlocal subject_touched
        subject_touched = True
        controller.update_subject(form, e.control.value or "")
        sync()

    def on_optional(name: str, value: str | None) -> None:
        setattr(form, name, value or "")
        sync()

    def on_color(color: str) -> None:
        form.choose_color(color)
        sync()

    def on_cancel(e: ft.Event[ft.TextButton]) -> None:
        page.pop_dialog()

    def on_save(e: ft.Event[ft.FilledButton]) -> None:
        result = controller.save_form(form)
        if result.applied:
            page.pop_dialog()
            on_saved()
        if result.message:
            page.show_dialog(ft.SnackBar(ft.Text(result.message)))

    subject = ft.TextField(
        label="과목명",
        value=form.subject,
        helper=f"필수, {SUBJECT_MAX}자 이하",
        autofocus=form.is_new,
        on_change=on_subject,
    )
    optional = {
        name: ft.TextField(
            label=label,
            value=getattr(form, name),
            helper=f"선택, {FIELD_MAX}자 이하",
            multiline=name == "memo",
            max_lines=3 if name == "memo" else 1,
            on_change=lambda e, n=name: on_optional(n, e.control.value),
        )
        for name, label in (("room", "강의실"), ("teacher", "교수"), ("memo", "메모"))
    }
    swatches = ft.Row(wrap=True, spacing=8, run_spacing=8)
    hint = ft.Text(SUGGESTED_HINT, size=12, color=ft.Colors.ON_SURFACE_VARIANT)
    save_button = ft.FilledButton("저장", on_click=on_save)

    def swatch(color: str) -> ft.Container:
        selected = color == form.color
        return ft.Container(
            width=SWATCH_SIZE,
            height=SWATCH_SIZE,
            bgcolor=resolve_hex(color),
            border_radius=ft.BorderRadius.all(SWATCH_SIZE / 2),
            border=ft.Border.all(3, ft.Colors.ON_SURFACE) if selected else None,
            content=ft.Icon(ft.Icons.CHECK, color=text_color(color), size=20) if selected else None,
            alignment=ft.Alignment.CENTER,
            tooltip=color,
            on_click=lambda e, c=color: on_color(c),
        )

    def sync() -> None:
        """폼 상태 → 컨트롤 반영."""
        errors = form.errors
        subject.error = errors.get("subject") if subject_touched else None
        for name, field in optional.items():
            field.error = errors.get(name)
        save_button.disabled = not form.can_save
        hint.visible = form.suggested
        swatches.controls = [swatch(color) for color in PALETTE]
        page.update()

    sheet = ft.BottomSheet(
        content=ft.Container(
            ft.Column(
                [
                    ft.Text(f"{DAY_LABELS[day]}요일 {period}교시", size=18, weight=ft.FontWeight.BOLD),
                    subject,
                    *optional.values(),
                    ft.Text("색상", weight=ft.FontWeight.BOLD),
                    swatches,
                    hint,
                    ft.Row(
                        [ft.TextButton("취소", on_click=on_cancel), save_button],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                tight=True,
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=ft.Padding.all(20),
        ),
        scrollable=True,
        show_drag_handle=True,
    )
    page.show_dialog(sheet)
    sync()
