"""화면을 실제로 조립해 보는 연기 테스트 (T11).

Flet 컨트롤은 인자 이름이 틀리면 만들 때 바로 터진다. 시트를 한 번도 열지 않으면
`ft.Switch(label_style=...)` 같은 실수가 실기기에서야 드러나므로, 여기서 미리 만들어 본다.
동작이 아니라 "조립이 되는지"만 본다.
"""

from pathlib import Path

import flet as ft
import pytest

from app.controller import ActionResult, AppController
from app.model import Cell
from app.storage import Storage
from app.ui.account import open_account
from app.ui.actions import Actions
from app.ui.editor import open_cell_editor
from app.ui.export import open_export_sheet
from app.ui.grid import build_grid
from app.ui.settings import open_settings
from app.ui.timetables import ask_name, confirm_delete, open_timetable_list


class FakePage:
    """show_dialog/update만 받아 적는 가짜 페이지."""

    def __init__(self) -> None:
        self.dialogs: list[ft.Control] = []

    def show_dialog(self, dialog: ft.Control) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        self.dialogs.pop()

    def update(self) -> None:
        pass

    def run_thread(self, fn) -> None:
        fn()


@pytest.fixture
def page() -> FakePage:
    return FakePage()


@pytest.fixture
def ctrl(tmp_path: Path) -> AppController:
    controller, _ = AppController.open(Storage(tmp_path))
    controller.workspace.set_cell("0-1", Cell(subject="알고리즘", room="K301"))
    controller.workspace.add_timetable("둘째")
    return controller


def noop_result(result: ActionResult) -> None:
    pass


def test_grid_builds_for_each_background(ctrl):
    from dataclasses import replace

    from app.palette import BACKGROUNDS

    for key in BACKGROUNDS:
        settings = replace(ctrl.workspace.data.settings, background=key, show_times=True)
        assert build_grid(ctrl.workspace.active, settings, lambda k: None, lambda k: None)


def test_settings_sheet_opens(page, ctrl):
    open_settings(page, ctrl, noop_result)
    assert len(page.dialogs) == 1


def test_cell_editor_opens(page, ctrl):
    open_cell_editor(page, ctrl, "0-1", on_saved=lambda: None)
    assert len(page.dialogs) == 1


def test_timetable_list_and_dialogs_open(page, ctrl):
    open_timetable_list(page, ctrl, noop_result, lambda: None)
    ask_name(page, "이름 변경", "이름", "저장", ctrl.add_timetable, noop_result)
    confirm_delete(page, "둘째", "지웁니다.", lambda: None)
    assert len(page.dialogs) == 3


def test_export_sheet_opens(page, ctrl):
    open_export_sheet(page, ctrl, picker=ft.FilePicker(), show_result=noop_result)
    assert len(page.dialogs) == 1


def test_account_without_config_reports(page, ctrl):
    messages: list[str] = []
    open_account(page, None, lambda result: messages.append(result.message or ""))
    assert messages and "config.py" in messages[0]


def test_cell_and_timetable_menus_open(page, ctrl):
    actions = Actions(page, ctrl, render=lambda: None, picker=ft.FilePicker())
    actions.open_cell_menu("0-1")
    actions.open_cell_menu("2-2")  # 빈 칸
    assert actions.timetable_menu()
    actions.confirm("덮어쓸까요?", "바뀝니다.", "덮어쓰기", lambda: None)
    actions.show_result(ActionResult(True, "삭제했어요.", undoable=True))
    assert len(page.dialogs) == 4


def test_account_sheet_signed_in_and_delete_confirm_opens(page, ctrl):
    from unittest.mock import MagicMock
    from app.controller import SyncManager, SyncStatus
    from app.ui.account import _confirm_delete_account

    manager = MagicMock(spec=SyncManager)
    manager.status = SyncStatus(signed_in=True, email="test@test.com")
    manager.controller = ctrl
    open_account(page, manager, noop_result)
    _confirm_delete_account(page, manager, noop_result)
    assert len(page.dialogs) == 2


def test_cell_editor_shows_delete_button_for_existing_cell(page, ctrl):
    open_cell_editor(page, ctrl, "0-1", on_saved=lambda: None)
    sheet = page.dialogs[-1]
    actions_row = sheet.content.content.controls[-1]
    delete_button = actions_row.controls[0]
    assert delete_button.content == "수업 삭제"


def test_drag_mode_and_hand_button_smoke(page, ctrl):
    rendered = []
    actions = Actions(page, ctrl, render=lambda: rendered.append(True))
    hand_btn = actions.hand_button()
    assert hand_btn.icon == ft.Icons.PAN_TOOL_OUTLINED

    # 손바닥 버튼 클릭 -> 모드 켜짐
    actions.toggle_drag_mode()
    assert actions.drag_mode is True
    assert hand_btn.icon == ft.Icons.PAN_TOOL

    # 그리드가 drag_mode로 정상 조립되는지 확인 (외형 유지 + Draggable/DragTarget 래핑)
    grid_control = build_grid(
        ctrl.workspace.active,
        ctrl.workspace.data.settings,
        drag_mode=True,
        on_move_cell=actions.move_cell,
    )
    assert grid_control is not None
    # 월요일 1교시(0-1: 알고리즘) 칸: 위치 컨테이너 → DragTarget → Draggable
    holder = grid_control.controls[1].controls[1].content.controls[0]
    assert isinstance(holder.content, ft.DragTarget)
    assert isinstance(holder.content.content, ft.Draggable)
    # 셀 외형의 border가 인위적인 색상 없이 기존 스타일(None)을 유지하는지 검증
    assert holder.content.content.content.border is None

    # 드래그 앤 드롭 이동 테스트: 0-1(수업) -> 1-2(빈칸)
    actions.move_cell("0-1", "1-2")
    assert ctrl.workspace.get_cell("1-2").subject == "알고리즘"
    assert ctrl.workspace.get_cell("0-1") is None


def test_drag_feedback_keeps_cell_size_and_landing_animates(ctrl):
    settings = ctrl.workspace.data.settings
    landing: list[ft.Control] = []
    grid_control = build_grid(
        ctrl.workspace.active,
        settings,
        drag_mode=True,
        on_move_cell=lambda s, t: None,
        available_width=600,
        landing_keys={"0-1"},
        landing_controls=landing,
    )
    draggable = grid_control.controls[1].controls[1].content.controls[0].content.content
    feedback = draggable.content_feedback
    # 드래그 카드는 실제 칸과 같은 높이·너비 (작아지지 않음)
    assert feedback.height == draggable.content.height
    assert feedback.width > 76
    # 방금 놓은 칸은 떠 있는 크기에서 내려앉도록 애니메이션이 걸린다
    assert len(landing) == 1 and landing[0].scale > 1 and landing[0].animate_scale is not None
