from app import design as d
from app.model import DAY_LABELS, MAX_DAY_INDEX, Cell, Settings, Workspace, grid_cells
from app.sample import sample_data
from app.ui.grid import build_grid


def test_day_labels_cover_all_days():
    assert len(DAY_LABELS) == MAX_DAY_INDEX + 1


def test_grid_cells_shape_and_positions():
    ws = Workspace()
    ws.set_cell("0-1", Cell(subject="a"))
    ws.set_cell("4-5", Cell(subject="b"))
    grid = grid_cells(ws.active, ws.data.settings)
    assert len(grid) == 5 and all(len(row) == 5 for row in grid)
    assert grid[0][0].subject == "a"  # 1교시 월
    assert grid[4][4].subject == "b"  # 5교시 금
    assert sum(cell is not None for row in grid for cell in row) == 2


def test_grid_cells_follow_settings_and_hide_out_of_range():
    ws = Workspace()
    ws.update_settings(Settings(days=6, periods=7))
    ws.set_cell("5-7", Cell(subject="토7"))
    assert grid_cells(ws.active, ws.data.settings)[6][5].subject == "토7"
    ws.update_settings(Settings(days=5, periods=5))
    grid = grid_cells(ws.active, ws.data.settings)
    assert len(grid) == 5 and all(len(row) == 5 for row in grid)
    assert all(cell is None or cell.subject != "토7" for row in grid for cell in row)


def test_sample_data_is_displayable():
    data = sample_data()
    ws = Workspace(data)
    grid = grid_cells(ws.active, data.settings)
    assert sum(cell is not None for row in grid for cell in row) == 10


def test_today_weekday_highlight_circle():
    ws = Workspace()
    grid_control = build_grid(ws.active, Settings(days=5), today_weekday=1)
    header_row = grid_control.controls[0]
    # header_row.controls[0]은 라벨 너비용 빈 컨테이너, controls[1~5]는 요일
    mon_cell = header_row.controls[1].content
    tue_cell = header_row.controls[2].content  # 오늘(화)
    wed_cell = header_row.controls[3].content

    # 월, 수: 일반 텍스트
    assert mon_cell.value == "월" and mon_cell.color == d.MUTED
    assert wed_cell.value == "수" and wed_cell.color == d.MUTED

    # 화: 검은 동그라미 컨테이너
    assert tue_cell.bgcolor == d.INK
    assert tue_cell.content.value == "화"
    assert tue_cell.content.color == d.ON_PRIMARY


def test_today_weekday_saturday_and_sunday():
    ws = Workspace()
    # 5일제에서 토요일(5)인 경우: 동그라미 없음
    grid_5days = build_grid(ws.active, Settings(days=5), today_weekday=5)
    header_5 = grid_5days.controls[0]
    assert all(c.content.bgcolor != d.INK for c in header_5.controls[1:])

    # 6일제에서 토요일(5)인 경우: 토요일(6번째 컨트롤)에 동그라미
    grid_6days = build_grid(ws.active, Settings(days=6), today_weekday=5)
    header_6 = grid_6days.controls[0]
    sat_cell = header_6.controls[6].content
    assert sat_cell.bgcolor == d.INK
    assert sat_cell.content.value == "토"

    # 일요일(6)인 경우: 6일제여도 동그라미 없음
    grid_sun = build_grid(ws.active, Settings(days=6), today_weekday=6)
    header_sun = grid_sun.controls[0]
    assert all(c.content.bgcolor != d.INK for c in header_sun.controls[1:])


def test_add_period_button_rendered_for_seventh_period_and_above():
    ws = Workspace()
    added = []

    # 7교시 시간표: 7교시 라벨에 + 버튼이 있어야 함
    grid_7 = build_grid(
        ws.active, Settings(periods=7), on_add_period=lambda: added.append(True)
    )
    labels_7 = grid_7.controls[1].controls[0]  # index 0: 헤더, 1: 교시 묶음 Row → [교시 라벨 Column, 요일 칸...]
    period_label_7 = labels_7.controls[-1].content  # Column([first_line, ...])
    first_line_7 = period_label_7.controls[0]  # Row([num_text, add_btn])
    assert len(first_line_7.controls) == 2
    assert first_line_7.controls[0].value == "7"
    assert first_line_7.controls[1].tooltip == "교시 추가"

    # 5교시 시간표: 7교시 미만이므로 + 버튼 없음
    grid_5 = build_grid(
        ws.active, Settings(periods=5), on_add_period=lambda: added.append(True)
    )
    period_label_5 = grid_5.controls[1].controls[0].controls[-1].content
    first_line_5 = period_label_5.controls[0]
    assert first_line_5.value == "5"


def _day_stack(grid, day: int, section: int = 0):
    """day 요일 세로 칸(Stack)의 자식들. section은 점심 앞/뒤 묶음."""
    row = grid.controls[1 + section * 2]
    return row.controls[1 + day].content.controls


def test_consecutive_same_class_is_drawn_as_one_block():
    ws = Workspace()
    algo = Cell(subject="알고리즘", color="blue")
    ws.set_cell("0-1", algo)
    ws.set_cell("0-2", Cell(subject="알고리즘", color="blue"))
    ws.set_cell("1-1", algo)  # 다른 요일은 따로
    grid = build_grid(ws.active, ws.data.settings)
    monday = _day_stack(grid, 0)
    # 1~2교시가 한 덩어리 + 3,4,5교시 빈 칸 = 4개
    assert len(monday) == 4
    assert monday[0].height == 2 * 84 + d.SPACE_XXS and monday[0].top == 0
    assert len(_day_stack(grid, 1)) == 5


def test_block_splits_at_lunch():
    ws = Workspace()
    ws.update_settings(Settings(lunch=True, lunch_after=2))
    for key in ("0-2", "0-3"):
        ws.set_cell(key, Cell(subject="실험"))
    grid = build_grid(ws.active, ws.data.settings)
    # 점심 앞 묶음(1~2교시)과 뒤 묶음(3~5교시)에 각각 한 칸씩
    assert len(_day_stack(grid, 0, section=0)) == 2
    assert len(_day_stack(grid, 0, section=1)) == 3


def test_edit_mode_adds_edge_handles_only_to_classes():
    ws = Workspace()
    ws.set_cell("0-1", Cell(subject="a"))
    grid = build_grid(
        ws.active, ws.data.settings, drag_mode=True, on_move_cell=lambda s, t: None,
        on_resize_block=lambda *a: None, on_extend_block=lambda *a: None,
    )
    monday = _day_stack(grid, 0)
    # 수업 1개 + 손잡이 4개 + 빈 칸 4개
    assert len(monday) == 1 + 4 + 4
    # 평소 모드에서는 손잡이가 없다
    plain = _day_stack(build_grid(ws.active, ws.data.settings), 0)
    assert len(plain) == 5
