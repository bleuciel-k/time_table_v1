"""설정 (F9): 요일·교시 수, 교시별 시간 표시."""

import json
from pathlib import Path

import pytest

from app.controller import READ_ONLY_MESSAGE, ActionResult, AppController
from app.model import (
    Cell,
    ModelError,
    Settings,
    ValidationError,
    Workspace,
    format_time,
    parse_time,
    period_times,
    to_dict,
    validate_settings,
)
from app.sample import sample_data
from app.storage import DATA_FILE, Storage, StorageFormatError, parse_document


@pytest.fixture
def ctrl(tmp_path: Path) -> AppController:
    return AppController.open(Storage(tmp_path))[0]


def reopen(tmp_path: Path) -> AppController:
    return AppController.open(Storage(tmp_path))[0]


# ---- 교시 시간 계산


def test_default_period_times():
    assert period_times(Settings()) == [
        ("09:00", "09:50"),
        ("10:00", "10:50"),
        ("11:00", "11:50"),
        ("12:00", "12:50"),
        ("13:00", "13:50"),
    ]


def test_period_times_follow_settings():
    settings = Settings(periods=2, start_time="08:30", class_minutes=90, break_minutes=15)
    assert period_times(settings) == [("08:30", "10:00"), ("10:15", "11:45")]
    assert period_times(Settings(periods=1, break_minutes=0)) == [("09:00", "09:50")]


def test_period_times_wrap_past_midnight():
    settings = Settings(periods=2, start_time="23:00", class_minutes=50, break_minutes=10)
    assert period_times(settings) == [("23:00", "23:50"), ("00:00", "00:50")]


@pytest.mark.parametrize("value", ["09:00", "00:00", "23:59"])
def test_parse_time_valid(value):
    assert format_time(parse_time(value)) == value


@pytest.mark.parametrize("value", ["9:00", "24:00", "09:60", "0900", "아홉시", "09:0a", ""])
def test_parse_time_invalid(value):
    with pytest.raises(ModelError):
        parse_time(value)


# ---- 검증


def test_valid_settings():
    validate_settings(Settings(days=6, periods=7, show_times=True, start_time="08:00"))


@pytest.mark.parametrize(
    ("settings", "field"),
    [
        (Settings(days=4), "days"),
        (Settings(days=7), "days"),
        (Settings(periods=0), "periods"),
        (Settings(periods=8), "periods"),
        (Settings(start_time="25:00"), "start_time"),
        (Settings(class_minutes=0), "class_minutes"),
        (Settings(class_minutes=181), "class_minutes"),
        (Settings(break_minutes=-1), "break_minutes"),
        (Settings(break_minutes=121), "break_minutes"),
    ],
)
def test_invalid_settings(settings, field):
    with pytest.raises(ValidationError) as info:
        validate_settings(settings)
    assert field in info.value.errors


# ---- 저장


def test_settings_persist_across_restart(ctrl, tmp_path):
    settings = Settings(days=6, periods=7, show_times=True, start_time="08:30", class_minutes=45, break_minutes=5)
    assert ctrl.update_settings(settings) == ActionResult(True, "설정을 저장했어요.")
    assert reopen(tmp_path).workspace.data.settings == settings


def test_invalid_settings_are_not_saved(ctrl, tmp_path):
    result = ctrl.update_settings(Settings(days=7))
    assert not result.applied and "요일 수" in result.message
    assert ctrl.workspace.data.settings == Settings()
    assert not (tmp_path / DATA_FILE).exists()


def test_old_file_without_time_fields_gets_defaults():
    raw = to_dict(sample_data())
    raw["settings"] = {"days": 6, "periods": 6}  # 구버전 파일
    data, _ = parse_document(json.dumps(raw))
    assert data.settings == Settings(days=6, periods=6)


@pytest.mark.parametrize(
    "settings",
    [
        {"days": 5, "periods": 5, "show_times": "yes"},
        {"days": 5, "periods": 5, "start_time": 900},
        {"days": 5, "periods": 5, "class_minutes": "50"},
        {"days": 5, "periods": 5, "start_time": "24:61"},
        {"days": 5, "periods": 5, "break_minutes": 999},
    ],
)
def test_bad_settings_in_file_is_corruption(settings):
    raw = to_dict(sample_data())
    raw["settings"] = settings
    with pytest.raises(StorageFormatError):
        parse_document(json.dumps(raw))


# ---- 조작


def test_settings_change_cancels_undo(ctrl):
    form = ctrl.form_for("0-1")
    ctrl.update_subject(form, "알고리즘")
    ctrl.save_form(form)
    ctrl.clear_cell("0-1")
    assert ctrl.workspace.can_undo
    ctrl.update_settings(Settings(days=6))
    assert not ctrl.workspace.can_undo


def test_shrinking_settings_hides_cells_without_deleting(ctrl, tmp_path):
    ctrl.update_settings(Settings(days=6, periods=7))
    ws = Workspace(ctrl.workspace.data)
    ws.set_cell("5-7", Cell(subject="토요일 7교시"))
    ctrl.update_settings(Settings(days=5, periods=5))
    assert reopen(tmp_path).workspace.get_cell("5-7") is not None


def test_read_only_blocks_settings(tmp_path):
    raw = to_dict(sample_data())
    raw["schema_version"] = 99
    (tmp_path / DATA_FILE).write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    ctrl, _ = AppController.open(Storage(tmp_path))
    assert ctrl.update_settings(Settings(days=6)) == ActionResult(False, READ_ONLY_MESSAGE)
    assert ctrl.workspace.data.settings.days == 5
