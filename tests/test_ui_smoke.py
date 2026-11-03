"""화면을 실제로 조립해 보는 연기 테스트 (T11).

Flet 컨트롤은 인자 이름이 틀리면 만들 때 바로 터진다. 시트를 한 번도 열지 않으면
`ft.Switch(label_style=...)` 같은 실수가 실기기에서야 드러나므로, 여기서 미리 만들어 본다.
동작이 아니라 "조립이 되는지"만 본다.
"""

from pathlib import Path

import flet as ft
import pytest

from app import design as d
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
    assert isinstance(hand_btn, ft.Container)
    assert hand_btn.content.src == "pinch_icon.png"
    assert hand_btn.content.color == d.INK

    # 핀치 수정 버튼 클릭 -> 모드 켜짐
    actions.toggle_drag_mode()
    assert actions.drag_mode is True
    assert hand_btn.content.color == d.LINK

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
    card_content = holder.content.content.content
    assert card_content.border is None
    assert isinstance(card_content.gradient, ft.LinearGradient)
    assert card_content.shadow is not None

    # 모퉁이 보조 표시(Handle)가 셀 굴곡(RADIUS)을 따르는 L자 곡선 아크인지 검증
    # _block은 [holder, *4_handles] 반환
    day_controls = grid_control.controls[1].controls[1].content.controls
    assert len(day_controls) >= 5  # holder + 4 corner handles
    top_left_handle = day_controls[1]
    arc_widget = top_left_handle.content.content.content
    assert arc_widget.border is not None
    assert arc_widget.border_radius is not None
    assert arc_widget.bgcolor == ft.Colors.TRANSPARENT

    # 드래그 시작 시 원래 자리의 모퉁이 핸들이 숨겨지는지 검증
    draggable = holder.content.content
    draggable.on_drag_start(None)
    assert top_left_handle.visible is False
    draggable.on_drag_complete(None)
    assert top_left_handle.visible is True

    # 옮겨질 빈 칸(1-2: 화요일 2교시)에 호버 시 실시간 하이라이트 및 모퉁이 보조선 검증
    tue_empty_holder = grid_control.controls[1].controls[2].content.controls[1]
    tue_empty_target = tue_empty_holder.content
    empty_base = tue_empty_target.content
    # 호버 전: 보조선 스택 숨김
    assert empty_base.content.visible is False
    # 드래그 호버 시: 선명한 테두리 및 4개 모퉁이 보조선 켜짐
    tue_empty_target.on_will_accept(None)
    assert empty_base.content.visible is True
    assert empty_base.border is not None and empty_base.border.top.color == d.LINK
    # 떠났을 때: 원래대로 복구
    tue_empty_target.on_leave(None)
    assert empty_base.content.visible is False

    # 드래그 앤 드롭 이동 테스트: 0-1(수업) -> 1-2(빈칸)
    actions.move_cell("0-1", "1-2")
    assert ctrl.workspace.get_cell("1-2").subject == "알고리즘"
    assert ctrl.workspace.get_cell("0-1") is None

    # 하단 드래그 삭제 테스트
    actions.on_drag_change(True, "1-2")
    assert actions.dragging_cell_key == "1-2"
    actions.delete_dragged_cell()
    assert ctrl.workspace.get_cell("1-2") is None
    assert actions.dragging_cell_key is None


def test_drag_feedback_keeps_cell_size_and_landing(ctrl):
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
    # 옮겨질 자리를 일체감 있게 보여주도록 피드백 카드에 4개 모퉁이 보조선이 부착됨
    assert isinstance(feedback, ft.Stack)
    assert len(feedback.controls) == 5
    # 방금 놓은 칸은 landing_controls에 등록됨
    assert len(landing) == 1


def test_multi_span_block_smart_slot_move(page, ctrl):
    from app.model import Cell
    # 설정이 5교시일 때, 월요일 1, 2교시에 2칸짜리 수업 생성
    ctrl.workspace.data.settings.periods = 7
    ctrl.workspace.set_cell("0-1", Cell(subject="캡스톤"))
    ctrl.workspace.set_cell("0-2", Cell(subject="캡스톤"))
    # 월요일 6교시에 다른 수업이 있음
    ctrl.workspace.set_cell("0-6", Cell(subject="다른수업"))
    # 월요일 4, 5교시는 비어있음
    assert ctrl.workspace.get_cell("0-4") is None
    assert ctrl.workspace.get_cell("0-5") is None

    rendered = []
    actions = Actions(page, ctrl, render=lambda: rendered.append(True))
    # 사용자가 2칸짜리 카드를 들고 가다 5교시("0-5")에 놓았을 때:
    # 5~6교시로 가면 6교시에 걸리지만, 스마트 슬롯 매칭으로 4~5교시로 자동 보정되어 안착해야 함!
    actions.move_cell("0-1", "0-5")
    assert ctrl.workspace.get_cell("0-4") is not None and ctrl.workspace.get_cell("0-4").subject == "캡스톤"
    assert ctrl.workspace.get_cell("0-5") is not None and ctrl.workspace.get_cell("0-5").subject == "캡스톤"
    assert ctrl.workspace.get_cell("0-1") is None
    assert ctrl.workspace.get_cell("0-2") is None


def test_resize_block_overlap_reverts(page, ctrl):
    from app.model import Cell
    # 월요일 1교시: 수업 A
    ctrl.workspace.set_cell("0-1", Cell(subject="수업A"))
    # 월요일 2교시: 수업 B
    ctrl.workspace.set_cell("0-2", Cell(subject="수업B"))

    rendered = []
    actions = Actions(page, ctrl, render=lambda: rendered.append(True))
    # 수업 A를 아래로 늘려 2교시(수업 B)와 겹치려고 시도
    result = actions.resize_block(day=0, start=1, end=1, new_start=1, new_end=2)
    # 실패해야 함
    assert result.applied is False
    # 실패했더라도 render()가 호출되어 모델과 UI가 일치해야 함
    assert len(rendered) > 0
    # 수업 A는 여전히 1교시만 차지해야 함
    assert ctrl.workspace.get_cell("0-1").subject == "수업A"
    assert ctrl.workspace.get_cell("0-2").subject == "수업B"

