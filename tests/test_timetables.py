"""여러 시간표 (F8): 추가·이름 변경·전환."""

import json
from pathlib import Path

import pytest

from app.controller import READ_ONLY_MESSAGE, ActionResult, AppController
from app.model import Cell, to_dict
from app.sample import sample_data
from app.storage import DATA_FILE, Storage


@pytest.fixture
def ctrl(tmp_path: Path) -> AppController:
    return AppController.open(Storage(tmp_path))[0]


def reopen(tmp_path: Path) -> AppController:
    return AppController.open(Storage(tmp_path))[0]


# ---- 추가


def test_add_timetable_persists_and_keeps_active(ctrl, tmp_path):
    first = ctrl.workspace.active
    result = ctrl.add_timetable(" 2026 후기 ")
    assert result == ActionResult(True, "추가했어요: 2026 후기")

    again = reopen(tmp_path).workspace
    assert [t.name for t in again.data.visible()] == ["새 시간표", "2026 후기"]
    assert again.active.id == first.id  # 추가해도 전환하지 않는다


def test_add_timetable_default_name(ctrl):
    assert ctrl.add_timetable().message == "추가했어요: 새 시간표"


@pytest.mark.parametrize("name", ["", "   ", "가" * 31])
def test_add_timetable_rejects_invalid_name(ctrl, tmp_path, name):
    result = ctrl.add_timetable(name)
    assert not result.applied and "이름" in result.message
    assert len(ctrl.workspace.data.visible()) == 1
    assert not (tmp_path / DATA_FILE).exists()


# ---- 이름 변경


def test_rename_timetable_persists(ctrl, tmp_path):
    target = ctrl.workspace.active
    assert ctrl.rename_timetable(target.id, " 2027 전기 ").applied
    assert reopen(tmp_path).workspace.active.name == "2027 전기"


def test_rename_rejects_invalid_name_and_unknown_id(ctrl):
    target = ctrl.workspace.active
    result = ctrl.rename_timetable(target.id, "가" * 31)
    assert not result.applied and "이름" in result.message
    assert ctrl.workspace.active.name == "새 시간표"

    missing = ctrl.rename_timetable("tt_missing", "이름")
    assert not missing.applied and missing.message


# ---- 전환


def test_switch_timetable_persists(ctrl, tmp_path):
    ctrl.add_timetable("두번째")
    second = ctrl.workspace.data.visible()[1]

    assert ctrl.switch_timetable(second.id) == ActionResult(True)
    assert ctrl.workspace.active.id == second.id
    assert reopen(tmp_path).workspace.active.id == second.id


def test_switch_to_unknown_timetable(ctrl):
    result = ctrl.switch_timetable("tt_missing")
    assert not result.applied and "시간표 없음" in result.message


def test_cells_belong_to_active_timetable(ctrl, tmp_path):
    form = ctrl.form_for("0-1")
    ctrl.update_subject(form, "알고리즘")
    ctrl.save_form(form)
    ctrl.add_timetable("두번째")
    second = ctrl.workspace.data.visible()[1]
    ctrl.switch_timetable(second.id)

    assert ctrl.workspace.get_cell("0-1") is None
    form = ctrl.form_for("0-1")
    ctrl.update_subject(form, "영어")
    ctrl.save_form(form)

    again = reopen(tmp_path).workspace
    assert again.get_cell("0-1").subject == "영어"
    first = again.data.visible()[0]
    assert first.cells["0-1"] == Cell(subject="알고리즘")


def test_switch_keeps_each_timetable_cells(ctrl):
    form = ctrl.form_for("0-1")
    ctrl.update_subject(form, "알고리즘")
    ctrl.save_form(form)
    other = ctrl.workspace.add_timetable("둘째")
    assert ctrl.switch_timetable(other.id).applied
    assert ctrl.workspace.get_cell("0-1") is None  # 새 시간표는 비어 있다


# ---- 읽기 전용


def test_read_only_blocks_timetable_changes(tmp_path):
    raw = to_dict(sample_data())
    raw["schema_version"] = 99
    (tmp_path / DATA_FILE).write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    ctrl, _ = AppController.open(Storage(tmp_path))
    blocked = ActionResult(False, READ_ONLY_MESSAGE)
    assert ctrl.add_timetable("새것") == blocked
    assert ctrl.rename_timetable(ctrl.workspace.active.id, "이름") == blocked
    assert ctrl.switch_timetable(ctrl.workspace.active.id) == blocked
    assert len(ctrl.workspace.data.visible()) == 1
