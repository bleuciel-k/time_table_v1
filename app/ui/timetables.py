"""시간표 목록 시트: 전환·추가·이름 변경 (F8). 판단은 controller가 한다 (P5)."""

from typing import Callable

import flet as ft

from app import design as d
from app.controller import ActionResult, AppController
from app.model import NAME_MAX, Timetable
from app.ui import theme as t

ShowResult = Callable[[ActionResult], None]


def open_timetable_list(
    page: ft.Page, controller: AppController, show_result: ShowResult, refresh: Callable[[], None]
) -> None:
    def close() -> None:
        sheet.open = False
        page.update()

    def switch(timetable: Timetable) -> None:
        close()
        show_result(controller.switch_timetable(timetable.id))

    def rename(timetable: Timetable) -> None:
        close()
        ask_name(
            page,
            "이름 변경",
            timetable.name,
            "저장",
            lambda value: controller.rename_timetable(timetable.id, value),
            show_result,
        )

    def add() -> None:
        close()
        ask_name(page, "시간표 추가", "", "추가", controller.add_timetable, show_result)

    def row(timetable: Timetable) -> ft.ListTile:
        active = timetable.id == controller.workspace.active.id
        return t.menu_item(
            ft.Icons.CHECK_CIRCLE if active else ft.Icons.RADIO_BUTTON_UNCHECKED,
            timetable.name,
            lambda e, tt=timetable: switch(tt),
            subtitle=f"{len(timetable.cells)}칸",
            color=d.INK if active else d.MUTED,
            trailing=ft.IconButton(
                ft.Icons.EDIT,
                tooltip="이름 변경",
                icon_color=d.MUTED,
                icon_size=20,
                on_click=lambda e, tt=timetable: rename(tt),
            ),
        )

    sheet = t.menu_sheet(
        "시간표",
        [
            *[row(tt) for tt in controller.workspace.data.visible()],
            t.divider(),
            t.menu_item(ft.Icons.ADD, "시간표 추가", lambda e: add()),
        ],
    )
    page.show_dialog(sheet)
    refresh()


def ask_name(
    page: ft.Page,
    title: str,
    initial: str,
    confirm_label: str,
    action: Callable[[str], ActionResult],
    show_result: ShowResult,
) -> None:
    """이름을 입력받아 `action`을 실행한다. 실패하면 대화상자를 열어 둔 채 오류만 보여준다."""
    field = t.text_field("이름", value=initial, autofocus=True, helper=f"1~{NAME_MAX}자")

    def cancel(e: ft.Event[ft.OutlinedButton]) -> None:
        dialog.open = False
        page.update()

    def submit(e: ft.Event[ft.FilledButton]) -> None:
        result = action(field.value or "")
        if result.applied:
            dialog.open = False
            page.update()
        show_result(result)

    dialog = t.dialog(
        title,
        field,
        [t.secondary_button("취소", cancel), t.primary_button(confirm_label, submit)],
    )
    page.show_dialog(dialog)
