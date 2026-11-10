"""셀 메뉴(편집/복사/붙여넣기/삭제), 시간표 메뉴(비우기/삭제/계정), 결과 스낵바와 되돌리기 (F3, F4, F7).

판단은 controller가 하고 여기서는 표시와 연결만 한다 (P5).
"""

import asyncio
from typing import Callable

import flet as ft

from app import design as d
from app.controller import ActionResult, AppController
from app.model import DAY_LABELS, PERIOD_MAX, PERIOD_MIN, UNDO_WINDOW, cell_key, parse_cell_key
from app.ui.editor import open_cell_editor
from app.ui.export import open_export_sheet
from app.ui.qr_dialog import open_qr_export_dialog, open_qr_import_sheet
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
    ) -> None:
        self.page = page
        self.controller = controller
        self.render = render
        self.picker = picker
        self.drag_mode: bool = False
        self.dragging_cell_key: str | None = None
        self.on_drag_listener: Callable[[bool, str | None], None] | None = None
        self.landing_keys: set[str] = set()  # 방금 이동해 내려앉는 칸 (render가 읽는다)
        self.landing_controls: list[ft.Control] = []
        self._hand_icon = ft.Image(
            src="pinch_icon.png",
            width=22,
            height=22,
            fit=ft.BoxFit.CONTAIN,
            color=d.INK,
        )
        self.hand_btn = ft.Container(
            content=self._hand_icon,
            width=36,
            height=36,
            border_radius=ft.BorderRadius.all(18),
            ink=True,
            alignment=ft.Alignment.CENTER,
            scale=1.0,
            animate_scale=ft.Animation(140, ft.AnimationCurve.EASE_OUT_CUBIC),
            tooltip="수업 수정 모드",
            on_click=lambda e: self.toggle_drag_mode(),
        )

    def toggle_drag_mode(self) -> None:
        self.drag_mode = not self.drag_mode
        self.dragging_cell_key = None
        if self.on_drag_listener:
            self.on_drag_listener(False, None)
        self._hand_icon.color = d.LINK if self.drag_mode else d.INK
        self.hand_btn.bgcolor = d.SURFACE_STRONG if self.drag_mode else None
        self.hand_btn.scale = 1.15 if self.drag_mode else 1.0
        self.hand_btn.tooltip = (
            "수업 수정 모드 끄기" if self.drag_mode else "수업 수정 모드"
        )
        self.render()
        if self.drag_mode:
            self.show_result(
                ActionResult(
                    False, "수정 모드: 수업을 끌어서 옮기거나 하단 휴지통으로 삭제하고, 가장자리를 끌어 늘리세요."
                )
            )
        else:
            self.show_result(ActionResult(False, "수업 수정 모드를 종료했어요."))

    def on_drag_change(self, dragging: bool, key: str | None) -> None:
        """수업을 드래그하기 시작하거나 끝났을 때 상태를 기록하고 리스너에 알린다."""
        self.dragging_cell_key = key if dragging else None
        if self.on_drag_listener:
            self.on_drag_listener(dragging, key)

    def delete_dragged_cell(self, key: str | None = None) -> None:
        target_key = key or self.dragging_cell_key
        self.dragging_cell_key = None
        if self.on_drag_listener:
            self.on_drag_listener(False, None)
        if target_key:
            self.show_result(self.controller.clear_cell(target_key))

    def move_cell(self, src_key: str, dest_key: str) -> None:
        """수업을 다른 칸으로 옮기거나 맞바꾼다. 연속 수업(span >= 2) 이동 시 스마트 슬롯 매칭 적용."""
        self.dragging_cell_key = None
        if self.on_drag_listener:
            self.on_drag_listener(False, None)
        resolved_dest = dest_key
        try:
            tt = self.controller.workspace.active
            src_keys = self.controller.workspace.block_keys(src_key)
            span = len(src_keys)
            # 빈 칸으로 이동하거나 원래 자기 슬롯 내에서 시프트 이동하는 2칸 이상의 연속 수업인 경우
            if span > 1 and (dest_key not in tt.cells or dest_key in src_keys):
                dest_day, dest_start = parse_cell_key(dest_key)
                settings = self.controller.workspace.data.settings
                # 사용자가 카드의 1번째, 2번째, ... n번째 칸 중 어디를 잡고 놓았더라도
                # dest_start를 포함하는 span 크기의 빈 슬롯을 탐색하여 최적의 시작 위치를 찾음
                candidate_starts = [dest_start - offset for offset in range(span)]
                for c_start in candidate_starts:
                    if c_start < PERIOD_MIN:
                        continue
                    c_end = c_start + span - 1
                    if c_end > settings.periods:
                        continue
                    c_keys = [cell_key(dest_day, p) for p in range(c_start, c_end + 1)]
                    if not any(k in tt.cells and k not in src_keys for k in c_keys):
                        resolved_dest = cell_key(dest_day, c_start)
                        break
        except Exception:
            resolved_dest = dest_key

        # 옮긴 수업(맞바꿨다면 상대 수업도)이 제자리로 내려앉는 애니메이션
        result = self.controller.move_cell(src_key, resolved_dest)
        dest_keys = self.controller.workspace.block_keys(resolved_dest) if result.applied else {resolved_dest}
        landing_targets = set(src_keys) | set(dest_keys)
        self._apply_with_landing(result, landing_targets)

    def resize_block(self, day: int, start: int, end: int, new_start: int, new_end: int) -> ActionResult:
        """수정 모드에서 수업 위/아래 가장자리를 끌었을 때."""
        result = self.controller.resize_block(day, start, end, new_start, new_end)
        if not result.applied and result.message is None:
            result = ActionResult(False, "다른 수업이 있어서 더 늘릴 수 없어요.")
        periods = range(max(PERIOD_MIN, new_start), min(PERIOD_MAX, new_end) + 1)
        self._apply_with_landing(result, {cell_key(day, p) for p in periods})
        return result

    def extend_block(self, day: int, start: int, end: int, to_day: int) -> ActionResult:
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
        return result

    def _apply_with_landing(self, result: ActionResult, keys: set[str]) -> None:
        if result.applied:
            self.landing_keys = keys
            self.landing_controls = []
        self.show_result(result)
        self.landing_keys = set()
        self.landing_controls = []

    def hand_button(self) -> ft.Control:
        return self.hand_btn

    # ---- 결과 표시

    def show_result(self, result: ActionResult) -> None:
        self.render()  # 성공/실패 무관하게 항상 UI와 시간표 모델을 일치시켜 겹침 잔상 방지
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

    def open_qr_export(self) -> None:
        open_qr_export_dialog(
            self.page,
            self.controller.workspace.active,
            self.controller.workspace.data.settings,
            self.show_result,
            self.picker,
        )

    def open_qr_import(self) -> None:
        open_qr_import_sheet(self.page, self.controller, self.show_result, self.render)

    def timetable_menu(self) -> ft.PopupMenuButton:
        c = self.controller

        bar1 = ft.Container(
            width=4,
            height=4,
            border_radius=2,
            bgcolor=d.INK,
            animate=ft.Animation(180, ft.AnimationCurve.EASE_OUT),
        )
        bar2 = ft.Container(
            width=4,
            height=4,
            border_radius=2,
            bgcolor=d.INK,
            animate=ft.Animation(180, ft.AnimationCurve.EASE_OUT),
        )
        bar3 = ft.Container(
            width=4,
            height=4,
            border_radius=2,
            bgcolor=d.INK,
            animate=ft.Animation(180, ft.AnimationCurve.EASE_OUT),
        )
        icon_box = ft.Container(
            content=ft.Column(
                [bar1, bar2, bar3],
                spacing=3.5,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=36,
            height=36,
            alignment=ft.Alignment.CENTER,
            border_radius=ft.BorderRadius.all(18),
        )

        def set_expanded(expanded: bool) -> None:
            w = 18 if expanded else 4
            h = 2.5 if expanded else 4
            r = 1.25 if expanded else 2
            for b in (bar1, bar2, bar3):
                b.width = w
                b.height = h
                b.border_radius = r
            try:
                icon_box.update()
            except Exception:
                pass

        return ft.PopupMenuButton(
            content=icon_box,
            menu_position=ft.PopupMenuPosition.UNDER,
            tooltip="시간표 메뉴",
            bgcolor=d.CANVAS,
            elevation=3,
            shape=ft.RoundedRectangleBorder(radius=d.RADIUS_MD),
            on_open=lambda e: set_expanded(True),
            on_cancel=lambda e: set_expanded(False),
            on_select=lambda e: set_expanded(False),
            items=[
                ft.PopupMenuItem(
                    "QR코드로 공유", icon=ft.Icons.QR_CODE_2, on_click=lambda e: self.open_qr_export()
                ),
                ft.PopupMenuItem(
                    "시간표 가져오기", icon=ft.Icons.DOWNLOAD, on_click=lambda e: self.open_qr_import()
                ),
                ft.PopupMenuItem(
                    "이미지로 저장", icon=ft.Icons.IMAGE, on_click=lambda e: self.open_export()
                ),
                ft.PopupMenuItem(
                    "설정", icon=ft.Icons.SETTINGS, on_click=lambda e: self.open_settings()
                ),
                ft.PopupMenuItem(
                    "시간표 비우기",
                    icon=ft.Icons.CLEAR_ALL,
                    on_click=lambda e: self.show_result(c.clear_timetable()),
                ),
                ft.PopupMenuItem(
                    "닫기",
                    icon=ft.Icons.CLOSE,
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
