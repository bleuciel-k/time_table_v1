"""셀 편집 시트 (F1, F2). 입력 상태와 규칙은 `controller.CellForm`에 둔다 (P5). 스타일은 DESIGN.md."""

from typing import Any, Callable

import flet as ft

from app import design as d
from app.controller import AppController
from app.model import DAY_LABELS, FIELD_MAX, SUBJECT_MAX, parse_cell_key
from app.palette import PALETTE, resolve_hex, text_color
from app.ui import theme as t

SWATCH_SIZE = 36
SUGGESTED_HINT = "기존 과목의 색을 적용했어요."


def open_cell_editor(
    page: ft.Page,
    controller: AppController,
    key: str,
    on_saved: Callable[[], None],
    on_deleted: Callable[[Any], None] | None = None,
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

    def on_show_memo(e: ft.Event[ft.Switch]) -> None:
        form.show_memo = bool(e.control.value)
        sync()

    def on_color(color: str) -> None:
        form.choose_color(color)
        sync()

    def on_cancel(e: ft.Event[ft.OutlinedButton]) -> None:
        page.pop_dialog()

    def on_save(e: ft.Event[ft.FilledButton]) -> None:
        result = controller.save_form(form)
        if result.applied:
            page.pop_dialog()
            on_saved()
        if result.message:
            page.show_dialog(t.snack_bar(result.message))

    def on_delete(e: ft.Event[ft.TextButton]) -> None:
        page.pop_dialog()
        result = controller.clear_cell(key)
        if on_deleted is not None:
            on_deleted(result)
        else:
            on_saved()
            if result.message:
                page.show_dialog(t.snack_bar(result.message))

    subject = t.text_field(
        "과목명",
        value=form.subject,
        helper=f"필수, {SUBJECT_MAX}자 이하",
        autofocus=form.is_new,
        on_change=on_subject,
    )
    optional = {
        name: t.text_field(
            label,
            value=getattr(form, name),
            helper=f"선택, {FIELD_MAX}자 이하",
            multiline=name == "memo",
            max_lines=3 if name == "memo" else 1,
            on_change=lambda e, n=name: on_optional(n, e.control.value),
        )
        for name, label in (("room", "강의실"), ("teacher", "교수"), ("memo", "메모"))
    }
    show_memo = ft.Switch(
        label="시간표에 메모 표시 (작은 글씨 2줄)",
        value=form.show_memo,
        on_change=on_show_memo,
        active_color=d.ON_PRIMARY,
        active_track_color=d.INK,
        label_text_style=t.style(d.BODY_MD, d.BODY),
    )

    # 16개 색상 견본은 매 타이핑마다 재생성하지 않고 1회만 생성하여 재사용
    swatch_boxes: dict[str, ft.Container] = {}
    swatch_checks: dict[str, ft.Icon] = {}
    current_selected_color = [form.color]

    for color in PALETTE:
        is_sel = color == form.color
        check_icon = ft.Icon(
            ft.Icons.CHECK,
            color=text_color(color),
            size=18,
            visible=is_sel,
        )
        swatch_checks[color] = check_icon
        box = ft.Container(
            width=SWATCH_SIZE,
            height=SWATCH_SIZE,
            bgcolor=resolve_hex(color),
            border_radius=ft.BorderRadius.all(SWATCH_SIZE / 2),
            border=ft.Border.all(2, d.INK) if is_sel else ft.Border.all(1, d.HAIRLINE),
            content=check_icon,
            alignment=ft.Alignment.CENTER,
            tooltip=color,
            on_click=lambda e, c=color: on_color(c),
        )
        swatch_boxes[color] = box

    swatches = ft.Row(
        list(swatch_boxes.values()),
        wrap=True,
        spacing=d.SPACE_XS,
        run_spacing=d.SPACE_XS,
    )
    hint = t.text(SUGGESTED_HINT, d.SMALL, color=d.MUTED)
    save_button = t.primary_button("저장", on_save)

    sheet: ft.BottomSheet | None = None

    def update_swatch_selection(new_color: str) -> None:
        old_color = current_selected_color[0]
        if old_color == new_color:
            return
        if old_color in swatch_boxes:
            swatch_boxes[old_color].border = ft.Border.all(1, d.HAIRLINE)
            swatch_checks[old_color].visible = False
        if new_color in swatch_boxes:
            swatch_boxes[new_color].border = ft.Border.all(2, d.INK)
            swatch_checks[new_color].visible = True
        current_selected_color[0] = new_color

    def sync() -> None:
        """폼 상태 → 컨트롤 반영. 전체 페이지가 아닌 바텀시트만 독립적으로 업데이트한다."""
        errors = form.errors
        subject.error = errors.get("subject") if subject_touched else None
        for name, field in optional.items():
            field.error = errors.get(name)
        save_button.disabled = not form.can_save
        show_memo.visible = bool(form.memo.strip())  # 메모가 있을 때만 의미 있는 선택
        hint.visible = form.suggested
        update_swatch_selection(form.color)
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

    actions_controls: list[ft.Control] = []
    if not form.is_new:
        actions_controls.append(t.danger_button("수업 삭제", on_delete))
        actions_controls.append(ft.Container(expand=True))
    actions_controls.extend([t.secondary_button("취소", on_cancel), save_button])

    sheet = t.sheet(
        f"{DAY_LABELS[day]}요일 {period}교시",
        [
            subject,
            *optional.values(),
            show_memo,
            t.label("색상"),
            swatches,
            hint,
            t.actions_row(*actions_controls),
        ],
    )
    page.show_dialog(sheet)
    sync()
