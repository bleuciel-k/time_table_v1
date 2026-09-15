from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from app.model import (
    AppData,
    Cell,
    CellOccupiedError,
    ModelError,
    ValidationError,
    Workspace,
    cell_key,
    from_dict,
    normalize_cell,
    parse_cell_key,
    to_dict,
    validate_cell,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 15, 10, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def ws(clock: FakeClock) -> Workspace:
    ids = count(1)
    return Workspace(clock=clock, id_factory=lambda: f"tt_{next(ids):02d}")


# ---- 셀 키


def test_cell_key_roundtrip_and_range():
    assert cell_key(0, 1) == "0-1"
    assert parse_cell_key("5-7") == (5, 7)
    for bad in [(6, 1), (-1, 1), (0, 0), (0, 8)]:
        with pytest.raises(ModelError):
            cell_key(*bad)
    with pytest.raises(ModelError):
        parse_cell_key("x-1")


# ---- 과목명 검증 (F1)


@pytest.mark.parametrize("subject", ["", "   ", "가" * 31])
def test_invalid_subject(subject):
    assert "subject" in validate_cell(Cell(subject=subject))


@pytest.mark.parametrize("subject", ["가", "가" * 30, "  알고리즘  "])
def test_valid_subject(subject):
    assert validate_cell(Cell(subject=subject)) == {}


def test_optional_fields_max_50_and_color():
    assert validate_cell(Cell(subject="a", room="r" * 50, teacher="t" * 50, memo="m" * 50)) == {}
    errors = validate_cell(Cell(subject="a", room="r" * 51, memo="m" * 51, color="nope"))
    assert set(errors) == {"room", "memo", "color"}


def test_normalize_strips_and_raises():
    assert normalize_cell(Cell(subject=" 수학 ", room=" K301 ")).subject == "수학"
    with pytest.raises(ValidationError) as info:
        normalize_cell(Cell(subject=""))
    assert "subject" in info.value.errors


def test_set_cell_rejects_invalid_and_out_of_settings(ws):
    with pytest.raises(ValidationError):
        ws.set_cell("0-1", Cell(subject=""))
    with pytest.raises(ModelError):
        ws.set_cell("5-1", Cell(subject="토요일"))  # 기본 5요일
    with pytest.raises(ModelError):
        ws.set_cell("0-6", Cell(subject="6교시"))  # 기본 5교시
    ws.update_settings(days=6, periods=7)
    ws.set_cell("5-7", Cell(subject="토요일 7교시"))
    assert ws.get_cell("5-7").subject == "토요일 7교시"


def test_set_cell_updates_timestamp(ws, clock):
    clock.advance(60)
    ws.set_cell("0-1", Cell(subject="알고리즘"))
    assert ws.active.updated_at == "2026-09-15T10:01:00Z"


# ---- 색상 제안 (F2)


def test_suggest_color_from_existing_subject(ws):
    ws.set_cell("0-1", Cell(subject="알고리즘", color="red"))
    other = ws.add_timetable("다른 학기")
    ws.set_cell("1-1", Cell(subject="영어", color="green"), timetable_id=other.id)
    assert ws.suggest_color(" 알고리즘 ") == "red"
    assert ws.suggest_color("영어") == "green"
    assert ws.suggest_color("없는과목") is None
    assert ws.suggest_color("") is None


# ---- 셀 복사/붙여넣기 (F3a)


def test_copy_paste_cell(ws):
    ws.set_cell("0-1", Cell(subject="알고리즘", room="K301", color="red"))
    ws.copy_cell("0-1")
    pasted = ws.paste_cell("2-3")
    assert pasted == ws.get_cell("0-1")
    ws.get_cell("2-3").room = "변경"
    assert ws.get_cell("0-1").room == "K301"  # 깊은 복사


def test_paste_into_occupied_requires_confirm(ws):
    ws.set_cell("0-1", Cell(subject="알고리즘"))
    ws.set_cell("0-2", Cell(subject="영어"))
    ws.copy_cell("0-1")
    assert ws.needs_overwrite_confirm("0-2")
    with pytest.raises(CellOccupiedError):
        ws.paste_cell("0-2")
    assert ws.get_cell("0-2").subject == "영어"
    ws.paste_cell("0-2", overwrite=True)
    assert ws.get_cell("0-2").subject == "알고리즘"


def test_paste_without_clipboard(ws):
    assert ws.copy_cell("0-1") is None
    with pytest.raises(ModelError):
        ws.paste_cell("0-2")


# ---- 시간표 복제 (F3b)


def test_duplicate_assigns_new_id_and_copies_cells(ws):
    ws.set_cell("0-1", Cell(subject="알고리즘"))
    source = ws.active
    clone = ws.duplicate_timetable()
    assert clone.id != source.id
    assert len({t.id for t in ws.data.timetables}) == len(ws.data.timetables)
    assert clone.name == f"{source.name} (복사본)"
    assert clone.cells == source.cells
    clone.cells["0-1"].subject = "변경"
    assert source.cells["0-1"].subject == "알고리즘"
    assert ws.data.timetables.index(clone) == ws.data.timetables.index(source) + 1


def test_duplicate_with_real_ids_is_unique():
    ws = Workspace()
    ids = {ws.active.id} | {ws.duplicate_timetable().id for _ in range(20)}
    assert len(ids) == 21


# ---- 삭제 후 되돌리기 (F4)


def test_clear_cell_then_undo(ws):
    ws.set_cell("0-1", Cell(subject="알고리즘"))
    assert ws.clear_cell("0-1")
    assert ws.get_cell("0-1") is None
    assert ws.undo_label == "셀 삭제"
    assert ws.undo()
    assert ws.get_cell("0-1").subject == "알고리즘"
    assert not ws.can_undo


def test_clear_empty_cell_is_noop(ws):
    assert not ws.clear_cell("0-1")
    assert not ws.can_undo


def test_clear_timetable_then_undo(ws):
    ws.set_cell("0-1", Cell(subject="a"))
    ws.set_cell("1-2", Cell(subject="b"))
    assert ws.clear_timetable()
    assert ws.active.cells == {}
    assert ws.undo()
    assert set(ws.active.cells) == {"0-1", "1-2"}


def test_delete_timetable_is_soft_and_undoable(ws, clock):
    first = ws.active
    second = ws.add_timetable("두번째")
    ws.switch_timetable(second.id)
    clock.advance(1)
    ws.delete_timetable(second.id)
    assert ws.data.find(second.id) is None
    assert any(t.id == second.id and t.deleted for t in ws.data.timetables)
    assert ws.data.active_id == first.id
    clock.advance(1)
    assert ws.undo()
    restored = ws.data.find(second.id)
    assert restored is not None and not restored.deleted
    assert ws.data.active_id == second.id
    assert restored.updated_at == "2026-09-15T10:00:02Z"  # 삭제 기록보다 새로움


def test_delete_last_timetable_creates_empty_and_undo_restores(ws):
    only = ws.active
    ws.set_cell("0-1", Cell(subject="a"))
    ws.delete_timetable()
    assert len(ws.data.visible()) == 1
    auto = ws.active
    assert auto.id != only.id and auto.name == "새 시간표" and auto.cells == {}
    assert ws.undo()
    assert [t.id for t in ws.data.visible()] == [only.id]
    assert ws.active.cells["0-1"].subject == "a"
    assert any(t.id == auto.id and t.deleted for t in ws.data.timetables)


def test_undo_expires_after_5_seconds(ws, clock):
    ws.set_cell("0-1", Cell(subject="a"))
    ws.clear_cell("0-1")
    clock.advance(5)
    assert ws.can_undo
    clock.advance(0.001)
    assert not ws.can_undo
    assert not ws.undo()
    assert ws.get_cell("0-1") is None


def test_other_change_cancels_undo(ws):
    ws.set_cell("0-1", Cell(subject="a"))
    ws.clear_cell("0-1")
    ws.set_cell("0-2", Cell(subject="b"))
    assert not ws.undo()
    assert ws.get_cell("0-1") is None
    assert ws.get_cell("0-2").subject == "b"


def test_new_delete_replaces_undo_record(ws):
    ws.set_cell("0-1", Cell(subject="a"))
    ws.set_cell("0-2", Cell(subject="b"))
    ws.clear_cell("0-1")
    ws.clear_cell("0-2")
    assert ws.undo()
    assert ws.get_cell("0-2").subject == "b"
    assert ws.get_cell("0-1") is None


# ---- 여러 시간표 / 설정 (F8, F9)


def test_add_rename_switch(ws):
    tt = ws.add_timetable(" 2026 후기 ")
    assert tt.name == "2026 후기"
    assert ws.data.active_id != tt.id
    ws.switch_timetable(tt.id)
    assert ws.active is tt
    ws.rename_timetable(tt.id, "새 이름")
    assert tt.name == "새 이름"
    for bad in ["", "   ", "가" * 31]:
        with pytest.raises(ValidationError):
            ws.rename_timetable(tt.id, bad)
    with pytest.raises(ModelError):
        ws.switch_timetable("tt_missing")


def test_update_settings_validation_keeps_hidden_cells(ws):
    ws.update_settings(days=6, periods=7)
    ws.set_cell("5-7", Cell(subject="a"))
    ws.update_settings(days=5, periods=5)
    assert ws.get_cell("5-7") is not None
    for days, periods in [(4, 5), (7, 5), (5, 0), (5, 8)]:
        with pytest.raises(ValidationError):
            ws.update_settings(days, periods)


def test_invalid_active_id_falls_back_to_first_visible(clock):
    ws = Workspace(clock=clock)
    first_id = ws.active.id
    ws.data.active_id = "missing"
    assert Workspace(ws.data, clock=clock).active.id == first_id


# ---- 직렬화 (spec 2.4)


def test_dict_roundtrip_matches_spec_shape(ws):
    ws.active.name = "2026 후기"
    ws.set_cell("0-1", Cell(subject="알고리즘", room="K301", color="blue"))
    raw = to_dict(ws.data)
    assert raw["schema_version"] == 1
    assert raw["settings"] == {"days": 5, "periods": 5}
    assert raw["timetables"][0]["cells"]["0-1"] == {
        "subject": "알고리즘", "room": "K301", "teacher": "", "memo": "", "color": "blue",
    }
    assert set(raw["timetables"][0]) == {"id", "name", "updated_at", "deleted", "cells"}
    assert from_dict(raw) == ws.data


def test_empty_appdata_gets_default_timetable():
    data = AppData()
    ws = Workspace(data)
    assert ws.active.name == "새 시간표"
    assert data.active_id == ws.active.id
