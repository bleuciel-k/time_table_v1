from app.model import DAY_LABELS, MAX_DAY_INDEX, Cell, Settings, Workspace, grid_cells
from app.sample import sample_data


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
