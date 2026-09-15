import json
from pathlib import Path

import pytest

from app.controller import READ_ONLY_MESSAGE, AppController, SaveResult
from app.model import Cell, to_dict
from app.sample import sample_data
from app.storage import DATA_FILE, Storage


@pytest.fixture
def ctrl(tmp_path: Path) -> AppController:
    controller, warnings = AppController.open(Storage(tmp_path))
    assert warnings == []
    return controller


def reopen(tmp_path: Path) -> AppController:
    return AppController.open(Storage(tmp_path))[0]


# ---- 폼 검증 (F1)


def test_new_form_defaults_and_cannot_save_empty(ctrl):
    form = ctrl.form_for("0-1")
    assert form.is_new and form.color == "blue"
    assert not form.can_save
    assert form.errors["subject"] == "과목명을 입력하세요."


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"subject": "   "}, "subject"),
        ({"subject": "가" * 31}, "subject"),
        ({"subject": "a", "room": "r" * 51}, "room"),
        ({"subject": "a", "teacher": "t" * 51}, "teacher"),
        ({"subject": "a", "memo": "m" * 51}, "memo"),
    ],
)
def test_invalid_form_cannot_save(ctrl, changes, field):
    form = ctrl.form_for("0-1")
    for name, value in changes.items():
        setattr(form, name, value)
    assert not form.can_save
    assert field in form.errors


def test_existing_cell_form_loads_values(ctrl):
    ctrl.workspace.set_cell("0-1", Cell(subject="알고리즘", room="K301", memo="m", color="red"))
    form = ctrl.form_for("0-1")
    assert not form.is_new
    assert (form.subject, form.room, form.memo, form.color) == ("알고리즘", "K301", "m", "red")
    assert form.can_save


# ---- 색상 자동 적용 (F2)


def test_existing_subject_applies_color_until_user_chooses(ctrl):
    ctrl.workspace.set_cell("0-1", Cell(subject="알고리즘", color="red"))
    form = ctrl.form_for("1-1")

    ctrl.update_subject(form, "알고리즘")
    assert form.color == "red" and form.suggested

    ctrl.update_subject(form, "알고리즘2")
    assert form.color == "blue" and not form.suggested

    ctrl.update_subject(form, "알고리즘")
    form.choose_color("green")
    ctrl.update_subject(form, "알고리즘 ")
    assert form.color == "green" and not form.suggested


def test_editing_existing_cell_reverts_to_its_own_color(ctrl):
    ctrl.workspace.set_cell("0-1", Cell(subject="영어", color="lime"))
    ctrl.workspace.set_cell("0-2", Cell(subject="수학", color="teal"))
    form = ctrl.form_for("0-2")
    ctrl.update_subject(form, "영어")
    assert form.color == "lime"
    ctrl.update_subject(form, "수학 심화")
    assert form.color == "teal"


# ---- 저장 + 재실행 후 유지 (F5)


def test_save_form_persists_across_restart(ctrl, tmp_path):
    form = ctrl.form_for("2-3")
    ctrl.update_subject(form, " 日本語会話 ")
    form.room, form.teacher, form.memo = "L105", "田中", "과제 있음"
    form.choose_color("pink")
    assert ctrl.save_form(form) == SaveResult(True)

    cell = reopen(tmp_path).workspace.get_cell("2-3")
    assert cell == Cell(subject="日本語会話", room="L105", teacher="田中", memo="과제 있음", color="pink")


def test_invalid_form_is_not_saved(ctrl, tmp_path):
    form = ctrl.form_for("0-1")
    result = ctrl.save_form(form)
    assert not result.applied and result.message
    assert ctrl.workspace.get_cell("0-1") is None
    assert not (tmp_path / DATA_FILE).exists()


def test_storage_failure_returns_message_and_keeps_change(ctrl, monkeypatch):
    def fail(data):
        raise OSError("No space left on device")

    monkeypatch.setattr(ctrl.storage, "save", fail)
    form = ctrl.form_for("0-1")
    ctrl.update_subject(form, "알고리즘")
    result = ctrl.save_form(form)
    assert result.applied  # 화면의 변경은 유지 → 시트를 닫는다
    assert result.message is not None and "No space left" in result.message
    assert ctrl.workspace.get_cell("0-1").subject == "알고리즘"


def test_read_only_data_cannot_be_edited(tmp_path):
    raw = to_dict(sample_data())
    raw["schema_version"] = 99
    text = json.dumps(raw, ensure_ascii=False)
    (tmp_path / DATA_FILE).write_text(text, encoding="utf-8")

    ctrl, warnings = AppController.open(Storage(tmp_path))
    assert ctrl.read_only and warnings
    form = ctrl.form_for("0-3")
    ctrl.update_subject(form, "새 과목")
    assert ctrl.save_form(form) == SaveResult(False, READ_ONLY_MESSAGE)
    assert ctrl.workspace.get_cell("0-3") is None
    assert (tmp_path / DATA_FILE).read_text(encoding="utf-8") == text


# ---- 시작 데이터


def test_seed_only_on_first_run(tmp_path):
    ctrl, _ = AppController.open(Storage(tmp_path), seed=sample_data)
    assert ctrl.workspace.get_cell("0-1").subject == "알고리즘"

    form = ctrl.form_for("0-3")
    ctrl.update_subject(form, "추가")
    ctrl.save_form(form)

    again, _ = AppController.open(Storage(tmp_path), seed=lambda: pytest.fail("seed again"))
    assert again.workspace.get_cell("0-3").subject == "추가"


def test_first_run_without_seed_is_empty(ctrl):
    assert ctrl.workspace.active.cells == {}
    assert ctrl.workspace.active.name == "새 시간표"
