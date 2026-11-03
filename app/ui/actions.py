"""셀 메뉴(편집/복사/붙여넣기/삭제), 시간표 메뉴(비우기/삭제/계정), 결과 스낵바와 되돌리기 (F3, F4, F7).

판단은 controller가 하고 여기서는 표시와 연결만 한다 (P5).
"""

import asyncio
from typing import Callable

import flet as ft

from app import design as d
from app.controller import ActionResult, AppController, SyncManager
from app.model import DAY_LABELS, PERIOD_MAX, PERIOD_MIN, UNDO_WINDOW, cell_key, parse_cell_key
from app.ui.account import open_account
from app.ui.editor import open_cell_editor
from app.ui.export import open_export_sheet
from app.ui.settings import open_settings
from app.ui.theme import danger_button, menu_item, menu_sheet, secondary_button, snack_bar
from app.ui.theme import dialog as theme_dialog
from app.ui.timetables import open_timetable_list

UNDO_SNACKBAR_MS = int(UNDO_WINDOW.total_seconds() * 1000)
NOTICE_SNACKBAR_MS = 3000


class Actions:
    def __init__(
        self,
        page: ft.Page,
        controller: AppController,
        render: Callable[[], None],
        picker: ft.FilePicker | None = None,
        sync: SyncManager | None = None,
    ) -> None:
        self.page = page
        self.controller = controller
        self.render = render
        self.picker = picker
        self.sync = sync
        self.drag_mode: bool = False
        self.landing_keys: set[str] = set()  # 방금 이동해 내려앉는 칸 (render가 읽는다)
        self.landing_controls: list[ft.Control] = []
        self.hand_btn = ft.IconButton(
            icon=ft.Icons.PAN_TOOL_OUTLINED,
            icon_color=d.INK,
            tooltip="수업 이동 모드 (손바닥/드래그)",
            on_click=lambda e: self.toggle_drag_mode(),
        )

    def toggle_drag_mode(self) -> None:
        self.drag_mode = not self.drag_mode
        self.hand_btn.icon = ft.Icons.PAN_TOOL if self.drag_mode else ft.Icons.PAN_TOOL_OUTLINED
        self.hand_btn.icon_color = d.LINK if self.drag_mode else d.INK
        self.hand_btn.bgcolor = d.SURFACE_STRONG if self.drag_mode else None
        self.hand_btn.tooltip = (
            "수업 이동 모드 끄기" if self.drag_mode else "수업 이동 모드 (손바닥/드래그)"
        )
        self.render()
        if self.drag_mode:
            self.show_result(
                ActionResult(
                    False, "수정 모드: 수업을 끌어서 옮기고, 가장자리를 끌어서 위·아래·양옆으로 늘리세요."
                )
            )
        else:
            self.show_result(ActionResult(False, "수업 이동 모드를 종료했어요."))

    def move_cell(self, src_key: str, dest_key: str) -> None:
        # 옮긴 수업(맞바꿨다면 상대 수업도)이 제자리로 내려앉는 애니메이션
        self._apply_with_landing(self.controller.move_cell(src_key, dest_key), {src_key, dest_key})

    def resize_block(self, day: int, start: int, end: int, new_start: int, new_end: int) -> None:
        """수정 모드에서 수업 위/아래 가장자리를 끌었을 때."""
        result = self.controller.resize_block(day, start, end, new_start, new_end)
        if not result.applied and result.message is None:
            result = ActionResult(False, "다른 수업이 있어서 더 늘릴 수 없어요.")
        periods = range(max(PERIOD_MIN, new_start), min(PERIOD_MAX, new_end) + 1)
        self._apply_with_landing(result, {cell_key(day, p) for p in periods})

    def extend_block(self, day: int, start: int, end: int, to_day: int) -> None:
        """수정 모드에서 수업 양옆 가장자리를 끌었을 때."""
        result = self.controller.extend_block_days(day, start, end, to_day)
        if not result.applied and result.message is None:
            result = ActionResult(False, "다른 수업이 있어서 옆으로 늘릴 수 없어요.")
        step = 1 if to_day > day else -1
        keys = {
            cell_key(target, start)
            for target in range(day + step, to_day + step, step)
            if 0 <= target < self.controller.workspace.data.settings.days
        }
        self._apply_with_landing(result, keys)

    def _apply_with_landing(self, result: ActionResult, keys: set[str]) -> None:
        if result.applied:
            self.landing_keys = keys
            self.landing_controls = []
        self.show_result(result)
        self.landing_keys = set()
        controls, self.landing_controls = self.landing_controls, []
        if controls and self.page is not None:
            self.page.run_task(self._settle, controls)

    async def _settle(self, controls: list[ft.Control]) -> None:
        await asyncio.sleep(0.02)  # 떠 있는 크기로 한 번 그려진 뒤에 줄여야 애니메이션이 보인다
        for control in controls:
            control.scale = 1.0
            control.update()

    def hand_button(self) -> ft.IconButton:
        return self.hand_btn

    # ---- 결과 표시

    def show_result(self, result: ActionResult) -> None:
        if result.applied:
            self.render()
        if not result.message or self.page is None:
            return
        self.page.show_dialog(
            snack_bar(
                result.message,
                action="되돌리기" if result.undoable else None,
                on_action=self._undo if result.undoable else None,
                duration=UNDO_SNACKBAR_MS if result.undoable else NOTICE_SNACKBAR_MS,
            )
        )

    def _undo(self, e: ft.Event[ft.SnackBar] | None = None) -> None:
        self.show_result(self.controller.undo())

    # ---- 셀 (F1, F3a, F4a)

    def edit_cell(self, key: str) -> None:
        open_cell_editor(
            self.page, self.controller, key, on_saved=self.render, on_deleted=self.show_result
        )

    def open_cell_menu(self, key: str) -> None:
        cell = self.controller.workspace.get_cell(key)
        day, period = parse_cell_key(key)
        sheet: ft.BottomSheet

        def item(
            icon: ft.IconData, label: str, handler: Callable[[], None], color: str = d.INK
        ) -> ft.ListTile:
            def click(e: ft.Event[ft.ListTile]) -> None:
                self._close(sheet)
                handler()

            return menu_item(icon, label, click, color=color)

        items = [item(ft.Icons.EDIT, "편집", lambda: self.edit_cell(key))]
        if cell is not None:
            items.append(
                item(ft.Icons.CONTENT_COPY, "복사", lambda: self.show_result(self.controller.copy_cell(key)))
            )
        if self.controller.has_clipboard:
            items.append(item(ft.Icons.CONTENT_PASTE, "붙여넣기", lambda: self.paste(key)))
        if cell is not None:
            items.append(
                item(
                    ft.Icons.DELETE,
                    "삭제",
                    lambda: self.show_result(self.controller.clear_cell(key)),
                    color=d.DANGER,
                )
            )

        heading = f"{DAY_LABELS[day]}요일 {period}교시 · {cell.subject if cell else '빈 칸'}"
        sheet = menu_sheet(heading, items)
        self.page.show_dialog(sheet)

    def paste(self, key: str) -> None:
        if self.controller.needs_overwrite_confirm(key):
            self.confirm(
                "덮어쓸까요?",
                "이 칸의 내용이 복사한 내용으로 바뀝니다.",
                "덮어쓰기",
                lambda: self.show_result(self.controller.paste_cell(key, overwrite=True)),
            )
        else:
            self.show_result(self.controller.paste_cell(key))

    # ---- 시간표 (F3b, F4b, F4c, F8) + 설정 (F9)

    def open_timetables(self) -> None:
        open_timetable_list(self.page, self.controller, self.show_result, self.render)

    def open_settings(self) -> None:
        open_settings(self.page, self.controller, self.show_result)

    def add_period(self) -> None:
        from dataclasses import replace
        from app.model import PERIOD_MAX
        settings = self.controller.workspace.data.settings
        if settings.periods < PERIOD_MAX:
            new_settings = replace(settings, periods=settings.periods + 1)
            self.show_result(self.controller.update_settings(new_settings))

    def open_export(self) -> None:
        if self.picker is None:
            self.show_result(ActionResult(False, "이 환경에서는 파일 저장을 쓸 수 없습니다."))
            return
        open_export_sheet(self.page, self.controller, self.picker, self.show_result)

    def open_account(self) -> None:
        open_account(self.page, self.sync, self.show_result)

    def timetable_menu(self) -> ft.PopupMenuButton:
        c = self.controller
        return ft.PopupMenuButton(
            icon=ft.Icons.MORE_VERT,
            icon_color=d.INK,
            tooltip="시간표 메뉴",
            bgcolor=d.CANVAS,
            elevation=2,
            shape=ft.RoundedRectangleBorder(radius=d.RADIUS_MD),
            items=[
                ft.PopupMenuItem(
                    "이미지로 저장", icon=ft.Icons.IMAGE, on_click=lambda e: self.open_export()
                ),
                ft.PopupMenuItem(
                    "설정", icon=ft.Icons.SETTINGS, on_click=lambda e: self.open_settings()
                ),
                ft.PopupMenuItem(
                    "계정", icon=ft.Icons.ACCOUNT_CIRCLE, on_click=lambda e: self.open_account()
                ),
                ft.PopupMenuItem(
                    "시간표 비우기", icon=ft.Icons.CLEAR_ALL,
                    on_click=lambda e: self.show_result(c.clear_timetable()),
                ),
                ft.PopupMenuItem(
                    "시간표 삭제", icon=ft.Icons.DELETE_FOREVER,
                    on_click=lambda e: self.show_result(c.delete_timetable()),
                ),
            ],
        )

    # ---- 공통

    def confirm(
        self, title: str, body: str, confirm_label: str, on_confirm: Callable[[], None]
    ) -> None:
        def cancel(e: ft.Event[ft.OutlinedButton]) -> None:
            self._close(dialog)

        def accept(e: ft.Event[ft.TextButton]) -> None:
            self._close(dialog)
            on_confirm()

        dialog = theme_dialog(
            title,
            ft.Text(body),
            [secondary_button("취소", cancel), danger_button(confirm_label, accept)],
        )
        self.page.show_dialog(dialog)

    def _close(self, dialog: ft.Control) -> None:
        # pop_dialog()는 맨 위 대화상자를 닫으므로, 스낵바가 떠 있어도 이 대화상자만 닫도록 직접 닫는다
        dialog.open = False
        self.page.update()
