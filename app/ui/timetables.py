"""시간표 목록 시트: 전환·추가·이름 변경 (F8). 판단은 controller가 한다 (P5)."""

from typing import Callable

import flet as ft

from app.controller import ActionResult, AppController
from app.model import NAME_MAX, Timetable

ShowResult = Callable[[ActionResult], None]


def open_timetable_list(
    page: ft.Page, controller: AppController, show_result: ShowResult, refresh: Callable[[], None]
) -> None:
    sheet = ft.BottomSheet(ft.Container(), show_drag_handle=True, scrollable=True)

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
        return ft.ListTile(
            leading=ft.Icon(
                ft.Icons.CHECK_CIRCLE if active else ft.Icons.RADIO_BUTTON_UNCHECKED,
                color=ft.Colors.PRIMARY if active else ft.Colors.ON_SURFACE_VARIANT,
            ),
            title=timetable.name,
            subtitle=f"{len(timetable.cells)}칸",
            trailing=ft.IconButton(
                ft.Icons.EDIT, tooltip="이름 변경", on_click=lambda e, t=timetable: rename(t)
            ),
            on_click=lambda e, t=timetable: switch(t),
        )

    sheet.content = ft.Container(
        ft.Column(
            [
                ft.Container(
                    ft.Text("시간표", size=16, weight=ft.FontWeight.BOLD),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                ),
                *[row(t) for t in controller.workspace.data.visible()],
                ft.Divider(height=1),
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.ADD), title="시간표 추가", on_click=lambda e: add()
                ),
            ],
            tight=True,
            spacing=0,
        ),
        padding=ft.Padding.only(bottom=16),
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
    field = ft.TextField(label="이름", value=initial, autofocus=True, helper=f"1~{NAME_MAX}자")
    dialog = ft.AlertDialog(modal=True, title=title, content=field)

    def cancel(e: ft.Event[ft.TextButton]) -> None:
        dialog.open = False
        page.update()

    def submit(e: ft.Event[ft.TextButton]) -> None:
        result = action(field.value or "")
        if result.applied:
            dialog.open = False
            page.update()
        show_result(result)

    dialog.actions = [
        ft.TextButton("취소", on_click=cancel),
        ft.TextButton(confirm_label, on_click=submit),
    ]
    page.show_dialog(dialog)
