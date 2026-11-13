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
from app.ui.actions import Actions
from app.ui.editor import open_cell_editor
from app.ui.export import open_export_sheet
from app.ui.grid import build_grid
from app.ui.qr_dialog import open_qr_export_dialog, open_qr_import_sheet
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


def test_main_entrypoint_smoke(page, monkeypatch, tmp_path):
    import main

    monkeypatch.setattr(main, "Storage", lambda: Storage(tmp_path))
    page.width = 390
    page.height = 844
    page.route = "/"
    page.overlay = []
    page.controls = []
    page.add = lambda *c: page.controls.extend(c)
    main.main(page)
    assert page.appbar is not None
    assert len(page.controls) == 1


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
    open_export_sheet(page, ctrl, picker=ft.FilePicker(), show_result=noop_result, share=ft.Share())
    assert len(page.dialogs) == 1


def test_qr_export_dialog_opens(page, ctrl):
    open_qr_export_dialog(
        page, ctrl.workspace.active, ctrl.workspace.data.settings, noop_result, picker=ft.FilePicker(), share=ft.Share()
    )
    assert len(page.dialogs) == 1


def test_cell_and_timetable_menus_open(page, ctrl):
    actions = Actions(page, ctrl, render=lambda: None, picker=ft.FilePicker())
    actions.open_cell_menu("0-1")
    actions.open_cell_menu("2-2")  # 빈 칸
    menu = actions.timetable_menu()
    assert menu is not None
    assert menu.menu_position == ft.PopupMenuPosition.UNDER
    item_texts = [item.content for item in menu.items]
    assert "시간표 비우기" in item_texts
    assert "시간표 삭제" not in item_texts
    assert "닫기" in item_texts
    actions.confirm("덮어쓸까요?", "바뀝니다.", "덮어쓰기", lambda: None)
    actions.show_result(ActionResult(True, "삭제했어요.", undoable=True))
    assert len(page.dialogs) == 4


def test_qr_import_sheet_opens(page, ctrl):
    open_qr_import_sheet(page, ctrl, noop_result, on_imported=lambda: None)
    assert len(page.dialogs) == 1


def test_cell_editor_shows_delete_button_for_existing_cell(page, ctrl):
    open_cell_editor(page, ctrl, "0-1", on_saved=lambda: None)
    sheet = page.dialogs[-1]
    actions_row = sheet.content.content.controls[-1]
    delete_button = actions_row.controls[0]
    assert delete_button.content == "수업 삭제"


def test_drag_mode_and_hand_button_smoke(page, ctrl):
    rendered = []
    actions = Actions(page, ctrl, render=lambda: rendered.append(True))
    drag_events = []
    actions.on_drag_listener = lambda dragging, key: drag_events.append((dragging, key))
    hand_btn = actions.hand_button()
    assert isinstance(hand_btn, ft.Container)
    assert hand_btn.content.src == "pinch_icon.png"
    assert hand_btn.content.color == d.INK

    # 핀치 수정 버튼 클릭 -> 모드 켜짐 (on_drag_listener 호출 포함)
    actions.toggle_drag_mode()
    assert actions.drag_mode is True
    assert hand_btn.content.color == d.LINK
    assert len(drag_events) == 1 and drag_events[0] == (False, None)

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
    # 셀 외형의 클레이모피즘 입체 테두리(Border)와 그라데이션·그림자가 유지되는지 검증
    card_content = holder.content.content.content
    assert isinstance(card_content.border, ft.Border)
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
    # 셀 사이 빈 공간으로 커서가 빠져나와도(on_leave) 최근 셀 하이라이트가 유지됨
    tue_empty_target.on_leave(None)
    assert empty_base.content.visible is True

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


def test_multi_span_drag_highlights_matching_slot_size(page, ctrl):
    """2칸 이상의 연속 수업을 드래그할 때, 옮겨질 영역도 그 크기만큼 모든 칸이 동시에 하이라이트되는지 검증."""
    from app.model import Cell
    ctrl.workspace.data.settings.periods = 5
    # 월요일 1, 2교시에 2칸짜리 수업 생성
    ctrl.workspace.set_cell("0-1", Cell(subject="운영체제"))
    ctrl.workspace.set_cell("0-2", Cell(subject="운영체제"))

    grid_control = build_grid(
        ctrl.workspace.active,
        ctrl.workspace.data.settings,
        drag_mode=True,
        on_move_cell=lambda s, t: None,
        available_width=600,
    )

    # 월요일 1교시(2칸 수업)의 Draggable 컨트롤
    mon_class_holder = grid_control.controls[1].controls[1].content.controls[0]
    draggable = mon_class_holder.content.content
    # 2칸짜리 수업 드래그 시작
    draggable.on_drag_start(None)

    # 화요일 컬럼의 빈 칸들: 2교시("1-2"), 3교시("1-3")
    tue_col_controls = grid_control.controls[1].controls[2].content.controls
    tue_target_2 = tue_col_controls[1].content  # 1-2
    tue_target_3 = tue_col_controls[2].content  # 1-3
    base_2 = tue_target_2.content
    base_3 = tue_target_3.content

    # 드래그 호버 전: 둘 다 가이드 보조선 숨김
    assert base_2.content.visible is False
    assert base_3.content.visible is False

    # 1-2에 드래그 호버 진입 시: 2칸짜리 수업 크기에 맞춰 1-2와 1-3 둘 다 동시에 하이라이트 켜짐!
    tue_target_2.on_will_accept(None)
    assert base_2.content.visible is True
    assert base_3.content.visible is True
    assert base_2.border is not None and base_2.border.top.color == d.LINK
    assert base_3.border is not None and base_3.border.bottom.color == d.LINK

    # 셀 사이 빈 공간으로 커서가 빠져나와도(on_leave) 최근 하이라이트가 꺼지지 않고 유지됨
    tue_target_2.on_leave(None)
    assert base_2.content.visible is True
    assert base_3.content.visible is True

    # 드래그 종료 시 모든 하이라이트 해제
    draggable.on_drag_complete(None)
    assert base_2.content.visible is False
    assert base_3.content.visible is False


def test_multi_span_placeholder_split_into_individual_cells(page, ctrl):
    """3칸짜리 연속 수업을 드래그할 때, 원래 자리가 3개의 개별 셀로 나뉘어 표시되고 각각 하이라이트 가능한지 검증."""
    from app.model import Cell
    ctrl.workspace.data.settings.periods = 5
    # 월요일 1, 2, 3교시에 3칸짜리 수업 생성
    ctrl.workspace.set_cell("0-1", Cell(subject="캡스톤"))
    ctrl.workspace.set_cell("0-2", Cell(subject="캡스톤"))
    ctrl.workspace.set_cell("0-3", Cell(subject="캡스톤"))

    grid_control = build_grid(
        ctrl.workspace.active,
        ctrl.workspace.data.settings,
        drag_mode=True,
        on_move_cell=lambda s, t: None,
        available_width=600,
    )

    mon_class_holder = grid_control.controls[1].controls[1].content.controls[0]
    draggable = mon_class_holder.content.content
    placeholder = draggable.content_when_dragging

    # 원래 자리(placeholder)가 3개의 기본 사이즈 셀로 나뉘어 있는지 검증
    assert isinstance(placeholder, ft.Column)
    assert len(placeholder.controls) == 3
    for sub_cell in placeholder.controls:
        assert isinstance(sub_cell, ft.Container)
        assert sub_cell.height > 60

    # 3칸 수업 드래그 시작
    draggable.on_drag_start(None)

    # 원래 자리의 각 셀(0-1, 0-2, 0-3)에 대해 하이라이트가 개별적으로 등록되어 있는지 검증
    sub_base_1 = placeholder.controls[0]
    sub_base_2 = placeholder.controls[1]
    sub_base_3 = placeholder.controls[2]
    assert sub_base_1.content.visible is False
    assert sub_base_2.content.visible is False
    assert sub_base_3.content.visible is False

    # 원래 자리 위로 드래그 호버 시, 개별 서브 셀들이 정상 하이라이트되는지 검증
    # 0-1에 호버
    mon_class_holder.content.on_will_accept(None)
    assert sub_base_1.content.visible is True
    assert sub_base_2.content.visible is True
    assert sub_base_3.content.visible is True

    # 드래그 종료 시 해제
    draggable.on_drag_complete(None)
    assert sub_base_1.content.visible is False
    assert sub_base_2.content.visible is False
    assert sub_base_3.content.visible is False


def test_multi_span_drag_hover_and_drop_on_lower_cell(page, ctrl):
    """2칸짜리 수업을 드래그하여 원래 자리의 아래 칸(2교시)에 호버 및 드롭했을 때,
    2교시와 3교시가 하이라이트되고 2교시 시작으로 정상 이동되는지 검증."""
    from app.model import Cell
    from types import SimpleNamespace
    ctrl.workspace.data.settings.periods = 5
    ctrl.workspace.set_cell("0-1", Cell(subject="네트워크"))
    ctrl.workspace.set_cell("0-2", Cell(subject="네트워크"))

    moved_records: list[tuple[str, str]] = []

    def on_move(s: str, t: str):
        moved_records.append((s, t))
        ctrl.workspace.move_block(s, t)

    grid_control = build_grid(
        ctrl.workspace.active,
        ctrl.workspace.data.settings,
        drag_mode=True,
        on_move_cell=on_move,
        available_width=600,
    )

    mon_class_holder = grid_control.controls[1].controls[1].content.controls[0]
    target = mon_class_holder.content
    draggable = target.content
    placeholder = draggable.content_when_dragging

    # 2칸 수업 드래그 시작
    draggable.on_drag_start(None)

    # 3교시 빈 칸 컨트롤
    tue_col_controls = grid_control.controls[1].controls[1].content.controls
    period_3_target = tue_col_controls[1].content  # 0-3
    base_3 = period_3_target.content

    # 아래 칸(2교시, y=160)으로 호버 이동
    # cell_height가 약 137px이므로 y=160은 2교시 칸에 해당
    move_evt = SimpleNamespace(local_position=SimpleNamespace(x=20, y=160))
    target.on_move(move_evt)

    # 원래 자리 2교시(placeholder sub_base_2)와 그 아래 3교시(base_3)가 동시에 2칸 크기로 하이라이트됨
    sub_base_1 = placeholder.controls[0]
    sub_base_2 = placeholder.controls[1]
    assert sub_base_1.content.visible is False  # 1교시는 꺼짐
    assert sub_base_2.content.visible is True   # 2교시 켜짐
    assert base_3.content.visible is True       # 3교시 켜짐

    # 아래 칸(2교시, y=160)에 드롭
    accept_evt = SimpleNamespace(
        local_position=SimpleNamespace(x=20, y=160),
        src_id=None,
        src=None,
        data="0-1",
    )
    target.on_accept(accept_evt)

    # on_move_cell("0-1", "0-2")가 정상 호출되어 2교시로 이동 완료
    assert len(moved_records) == 1
    assert moved_records[0] == ("0-1", "0-2")
    assert "0-1" not in ctrl.workspace.active.cells
    assert ctrl.workspace.get_cell("0-2").subject == "네트워크"
    assert ctrl.workspace.get_cell("0-3").subject == "네트워크"


def test_corner_handles_and_arcs_enlarged(page, ctrl):
    """모퉁이 터치 영역(HANDLE)과 표시선 크기가 확대되어 잡기 편해졌는지 검증."""
    from app.model import Cell
    from app.ui.grid import HANDLE
    assert HANDLE == 40

    ctrl.workspace.set_cell("0-1", Cell(subject="운영체제"))
    grid_control = build_grid(
        ctrl.workspace.active,
        ctrl.workspace.data.settings,
        drag_mode=True,
        on_move_cell=lambda s, t: None,
        available_width=600,
    )
    # 4개 모퉁이 핸들 컨트롤 검증
    mon_controls = grid_control.controls[1].controls[1].content.controls
    # mon_controls[0]은 holder, mon_controls[1..4]는 4개 corner_widget
    for i in range(1, 5):
        h = mon_controls[i]
        assert h.width == 40
        assert h.height == 40
        detector = h.content
        assert isinstance(detector, ft.GestureDetector)
        curved_arc = detector.content.content
        assert curved_arc.width == 22
        assert curved_arc.height == 22


def test_corner_handles_follow_resize_preview(page, ctrl):
    """수업을 늘릴 때(resize drag), 4개 모퉁이 핸들과 표시선이 카드 크기 변화에 맞춰 실시간으로 따라가는지 검증."""
    from app.model import Cell
    from types import SimpleNamespace
    from app.ui.grid import HANDLE

    ctrl.workspace.data.settings.periods = 5
    ctrl.workspace.set_cell("0-1", Cell(subject="데이터구조"))

    grid_control = build_grid(
        ctrl.workspace.active,
        ctrl.workspace.data.settings,
        drag_mode=True,
        on_resize_block=lambda d, s, e, ns, ne: None,
        available_width=600,
    )

    mon_controls = grid_control.controls[1].controls[1].content.controls
    holder = mon_controls[0]
    initial_top = holder.top
    initial_height = holder.height

    # mon_controls[1..4]: tl, tr, bl, br
    tl_handle = mon_controls[1]
    tr_handle = mon_controls[2]
    bl_handle = mon_controls[3]
    br_handle = mon_controls[4]

    # 시작 시 하단 핸들의 top 위치 기록
    initial_bl_top = bl_handle.top
    initial_br_top = br_handle.top

    # 우측 하단 핸들(br)을 아래로 70px 드래그 (on_pan_update)
    br_detector = br_handle.content
    pan_evt = SimpleNamespace(local_delta=SimpleNamespace(x=0, y=70))
    br_detector.on_pan_update(pan_evt)

    # 수업 카드가 70px만큼 늘어남
    assert holder.height == initial_height + 70

    # 모퉁이 표시선(하단 핸들)도 70px만큼 아래로 이동하여 카드 모퉁이에 정확히 밀착됨!
    assert bl_handle.top == initial_bl_top + 70
    assert br_handle.top == initial_br_top + 70

    # 상단 핸들은 그대로 유지
    assert tl_handle.top == initial_top + 2.0  # block top (0.0)
    assert tr_handle.top == initial_top + 2.0





