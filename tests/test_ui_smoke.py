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
