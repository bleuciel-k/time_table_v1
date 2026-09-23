import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.controller import READ_ONLY_MESSAGE, UNDO_EXPIRED_MESSAGE, ActionResult, AppController
from app.model import Cell, Workspace, to_dict
from app.sample import sample_data
from app.storage import DATA_FILE, Storage


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 15, 10, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def ctrl(tmp_path: Path) -> AppController:
    controller, warnings = AppController.open(Storage(tmp_path))
    assert warnings == []
    return controller


def reopen(tmp_path: Path) -> AppController:
    return AppController.open(Storage(tmp_path))[0]


def add(ctrl: AppController, key: str, subject: str, color: str = "blue") -> None:
    form = ctrl.form_for(key)
    ctrl.update_subject(form, subject)
    form.choose_color(color)
    assert ctrl.save_form(form).applied


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
    assert ctrl.save_form(form) == ActionResult(True)

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


# ---- 셀 복사/붙여넣기 (F3a)


def test_copy_paste_into_empty_cell_persists(ctrl, tmp_path):
    add(ctrl, "0-1", "알고리즘", "red")
    copied = ctrl.copy_cell("0-1")
    assert copied.applied and "알고리즘" in copied.message
    assert ctrl.has_clipboard
    assert not ctrl.needs_overwrite_confirm("1-2")

    result = ctrl.paste_cell("1-2")
    assert result.applied and not result.undoable
    assert reopen(tmp_path).workspace.get_cell("1-2") == Cell(subject="알고리즘", color="red")


def test_paste_into_occupied_cell_requires_overwrite(ctrl, tmp_path):
    add(ctrl, "0-1", "알고리즘")
    add(ctrl, "0-2", "영어")
    ctrl.copy_cell("0-1")
    assert ctrl.needs_overwrite_confirm("0-2")

    refused = ctrl.paste_cell("0-2")
    assert not refused.applied and refused.message
    assert reopen(tmp_path).workspace.get_cell("0-2").subject == "영어"

    assert ctrl.paste_cell("0-2", overwrite=True).applied
    assert reopen(tmp_path).workspace.get_cell("0-2").subject == "알고리즘"


def test_copy_empty_cell_and_paste_without_clipboard(ctrl):
    assert ctrl.copy_cell("0-1") == ActionResult(False, "복사할 내용이 없습니다.")
    assert not ctrl.has_clipboard
    result = ctrl.paste_cell("0-2")
    assert not result.applied and result.message


def test_delete_timetable_then_undo(ctrl, tmp_path):
    add(ctrl, "0-1", "a")
    ctrl.add_timetable("둘째")
    original = ctrl.workspace.active

    result = ctrl.delete_timetable()
    assert result.applied and result.undoable
    assert result.message == f"삭제했어요: {original.name}"
    assert ctrl.workspace.active.name == "둘째"
    assert reopen(tmp_path).workspace.data.find(original.id) is None

    assert ctrl.undo().applied
    again = reopen(tmp_path).workspace
    assert again.active.id == original.id
    assert len(again.data.visible()) == 2


def test_delete_last_timetable_shows_new_empty_one(ctrl):
    add(ctrl, "0-1", "a")
    assert ctrl.delete_timetable().applied
    assert ctrl.workspace.active.name == "새 시간표"
    assert ctrl.workspace.active.cells == {}


def test_undo_after_window_expires(tmp_path):
    clock = FakeClock()
    ctrl = AppController(Storage(tmp_path), Workspace(clock=clock))
    add(ctrl, "0-1", "a")
    ctrl.clear_cell("0-1")
    clock.now += timedelta(seconds=5.1)
    assert ctrl.undo() == ActionResult(False, UNDO_EXPIRED_MESSAGE)
    assert ctrl.workspace.get_cell("0-1") is None


def test_other_change_cancels_undo(ctrl):
    add(ctrl, "0-1", "a")
    ctrl.clear_cell("0-1")
    add(ctrl, "0-2", "b")
    assert ctrl.undo() == ActionResult(False, UNDO_EXPIRED_MESSAGE)


def test_storage_failure_on_delete_still_offers_undo(ctrl, monkeypatch):
    add(ctrl, "0-1", "a")
    monkeypatch.setattr(ctrl.storage, "save", lambda data: (_ for _ in ()).throw(OSError("disk")))
    result = ctrl.clear_cell("0-1")
    assert result.applied and result.undoable
    assert "저장 실패" in result.message


# ---- 읽기 전용


def test_read_only_data_cannot_be_edited(tmp_path):
    raw = to_dict(sample_data())
    raw["schema_version"] = 99
    text = json.dumps(raw, ensure_ascii=False)
    (tmp_path / DATA_FILE).write_text(text, encoding="utf-8")

    ctrl, warnings = AppController.open(Storage(tmp_path))
    assert ctrl.read_only and warnings
    form = ctrl.form_for("0-3")
    ctrl.update_subject(form, "새 과목")
    blocked = ActionResult(False, READ_ONLY_MESSAGE)
    assert ctrl.save_form(form) == blocked
    assert ctrl.copy_cell("0-1").applied  # 복사는 데이터를 바꾸지 않음
    assert ctrl.paste_cell("0-3") == blocked
    assert ctrl.clear_cell("0-1") == blocked
    assert ctrl.clear_timetable() == blocked
    assert ctrl.delete_timetable() == blocked
    assert ctrl.undo() == blocked
    assert ctrl.workspace.get_cell("0-3") is None
    assert ctrl.workspace.get_cell("0-1") is not None
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


# ---- 배경색 (F9) + 시간표별 삭제 (F4c)


def test_background_is_saved_and_restored(ctrl, tmp_path):
    from dataclasses import replace

    settings = replace(ctrl.workspace.data.settings, background="ivory")
    assert ctrl.update_settings(settings).applied
    assert reopen(tmp_path).workspace.data.settings.background == "ivory"


def test_unknown_background_is_rejected(ctrl):
    from dataclasses import replace

    result = ctrl.update_settings(replace(ctrl.workspace.data.settings, background="무지개"))
    assert not result.applied
    assert "배경색" in result.message
    assert ctrl.workspace.data.settings.background == "white"


def test_delete_timetable_by_id_keeps_active(ctrl):
    other = ctrl.workspace.add_timetable("버릴 것")
    active_id = ctrl.workspace.active.id
    result = ctrl.delete_timetable(other.id)
    assert result.applied and result.undoable
    assert "버릴 것" in result.message
    assert [t.id for t in ctrl.workspace.data.visible()] == [active_id]


def test_delete_timetable_by_id_switches_when_active_removed(ctrl):
    other = ctrl.workspace.add_timetable("남을 것")
    assert ctrl.delete_timetable(ctrl.workspace.active.id).applied
    assert ctrl.workspace.active.id == other.id


def test_delete_timetable_unknown_id(ctrl):
    result = ctrl.delete_timetable("tt_없음")
    assert not result.applied and "시간표 없음" in result.message


def test_delete_last_timetable_creates_empty_one(ctrl):
    assert ctrl.delete_timetable().applied
    visible = ctrl.workspace.data.visible()
    assert len(visible) == 1 and visible[0].cells == {}
    assert ctrl.undo().applied  # 되돌리면 원래 시간표가 돌아온다
